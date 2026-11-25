#!/usr/bin/env python3
"""Mediation, moderation and structural-model computations for the analysis script of researchzy-path-models.

Import it; it has no commands.

    import sys
    sys.path.insert(0, "<the scripts folder of this skill>")
    import pandas as pd
    import path_tools as pt

    model = pt.read_model("paths/model.md")                    # the registered design, roles and blocks
    data = pd.read_csv("data/survey.csv", na_values=[-99])
    med = pt.bootstrap_indirect(data, model["models"]["mediation"], {"ind": "a*b"}, n_boot=5000, seed=SEED)
    fit = pt.fit_equations(data, model["models"]["moderated"], center=["aut", "sup"])
    mod = pt.probe(fit, focal="a1", interaction="a3", moderator="sup", probes=[4.25, 6.25, 7])
    imm = pt.moderated_mediation_index(data, model["models"]["moderated"], index="a3*b",
                                       conditional="(a1 + a3*{w})*b", moderator="sup", probes=[4.25, 6.25, 7],
                                       n_boot=5000, seed=SEED, center=["aut", "sup"])
    sem = pt.fit_sem(data, model["models"]["latent"])

A model is lavaan-style text: "m ~ a*x + age" is a regression whose x coefficient is labelled a;
"x:w" is a product term; "F =~ i1 + i2" and "i1 ~~ i2" belong to latent models; "ind := a*b"
defines a parameter.

  read_model(path)        model.md as check_paths.py reads it: design, roles, the ```model blocks
  fit_equations(df, model, center=None, level=0.95)
                          each regression by OLS (statsmodels) on the rows complete in every variable of
                          every equation (each equation's n alone beside it): value, SE, t, p, interval and
                          standardized value per coefficient, VIF, and each column's range, mean, SD and
                          p16, p50, p84; center= centres columns on their mean in those rows and keeps the
                          uncentred product coefficients and VIF beside them
  probe(fit, focal, interaction, moderator, probes, level=0.95)
                          simple slopes and Johnson-Neyman bounds (probe_interaction.py) on the
                          moderator's own scale; a probe is a number, mean, mean+1sd, or p16, p50
                          and p84 (percentiles of the analysed rows)
  bootstrap_indirect(df, model, defined=None, n_boot=5000, seed, method="percentile", level=0.95, center=None)
                          defined parameters ("a*b", "a1*b1 + a2*b2", "a1*d21*b2") from a seeded bootstrap
                          of cases: the full-sample value (never the mean of the draws), a percentile or
                          BCa interval, the draws that failed; a latent model is refitted with semopy
  moderated_mediation_index(df, model, index, conditional, moderator, probes, n_boot, seed, ...)
                          the index (a3*b or a*b3) and the conditional indirect effects at the probe
                          values ({w} in conditional), from one bootstrap
  fit_sem(df, model, obj="MLW")
                          semopy: convergence, df, chi-square, CFI, TLI, RMSEA, SRMR and the paths;
                          {"status": "not_checked", ...} when semopy is not installed

Every function returns plain numbers, lists and dicts for rz.record(..., extra={"paths": ...}). Columns
must be numeric: read missing-value codes as missing (pd.read_csv(..., na_values=[-99])) and make 0/1
columns for categories. Needs numpy, pandas and statsmodels; latent models need semopy.
"""

from __future__ import annotations

import hashlib
import re
import sys
import warnings
from importlib.metadata import version
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_interaction as pi  # noqa: E402
from check_paths import atoms, evaluate, parse, read_model  # noqa: E402,F401

NAME = re.compile(r"[^\W\d][\w.]*")
MEMORY = 4_000_000                  # numbers held at once by one block of resamples
NO_SEMOPY = ("semopy is not installed: ask the user before installing it (python3 -m pip install --user semopy), or fit "
             "the model with lavaan if R has it (Rscript -e 'library(lavaan)')")
SRMR_FORMULA = ("square root of the mean, over the lower triangle with the diagonal, of ((s_ij - sigma_ij) / "
                "sqrt(s_ii s_jj))^2; s is the sample covariance with divisor n")


def _num(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _rows(frame) -> str:
    return hashlib.sha256(",".join(map(str, frame.index)).encode()).hexdigest()[:16]


def _numeric(df, names: list, what: str):
    missing = [n for n in names if n not in df.columns]
    if missing:
        raise ValueError(f"path_tools: {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not a column of the data")
    text = [n for n in names if not pd.api.types.is_numeric_dtype(df[n]) or pd.api.types.is_bool_dtype(df[n])]
    if text:
        raise ValueError(f"path_tools: {', '.join(text)} {'is' if len(text) == 1 else 'are'} not numeric: read missing-value "
                         f"codes as missing and make 0/1 columns for categories ({what})")
    data = df[names].astype(float)
    return data, data[data.notna().all(axis=1)]


def _regressions(model: str) -> list:
    statements = parse(model)
    if any(op in ("=~", "~~") for _, op, _ in statements):
        raise ValueError("path_tools: =~ and ~~ belong to a latent model: use fit_sem() or bootstrap_indirect()")
    regressions = [(lhs, terms) for lhs, op, terms in statements if op == "~"]
    labels = [label for _, terms in regressions for label, _ in terms if label]
    problems = [f"{label} is not a label" for label in labels if not NAME.fullmatch(label)]
    problems += [f"label {label} is used twice" for label in sorted({x for x in labels if labels.count(x) > 1})]
    problems += [f"{part} is not a column name (make 0/1 columns for categories)" for lhs, terms in regressions
                 for part in [lhs] + [p for _, term in terms for p in term.split(":")] if not NAME.fullmatch(part)]
    if problems or not regressions:
        raise ValueError("path_tools: " + ("; ".join(problems) or "the model has no regression (y ~ x)"))
    return regressions


def _ols(frame, regressions, data, level) -> tuple:
    """The fitted equations as a record, and their design matrices for resampling."""
    record, designs = {"equations": {}, "coefficients": {}, "cov": {}, "vif": {}}, []
    for lhs, terms in regressions:
        formula = f"{lhs} ~ " + " + ".join(term for _, term in terms)
        res = smf.ols(formula, data=frame).fit()
        names = [lhs] + [p for _, term in terms for p in term.split(":")]
        record["equations"][lhs] = {"formula": formula, "n": int(res.nobs), "df_resid": int(res.df_resid),
                                    "n_alone": int(data[names].notna().all(axis=1).sum()), "r2": float(res.rsquared)}
        keys, ci, cov = {term: label or f"{lhs}~{term}" for label, term in terms}, res.conf_int(1 - level), res.cov_params()
        for term, key in keys.items():
            std = res.params[term] * frame[term].std() / frame[lhs].std() if ":" not in term else None
            record["coefficients"][key] = {"lhs": lhs, "term": term, "value": float(res.params[term]),
                                           "se": float(res.bse[term]), "t": float(res.tvalues[term]),
                                           "p": float(res.pvalues[term]), "low": float(ci.loc[term, 0]),
                                           "high": float(ci.loc[term, 1]), "std": _num(std)}
        record["cov"][lhs] = {keys[a]: {keys[b]: float(cov.loc[a, b]) for b in keys} for a in keys}
        x = res.model.exog[:, 1:]
        try:
            inverse = np.linalg.inv(np.atleast_2d(np.corrcoef(x, rowvar=False))) if x.shape[1] > 1 else np.ones((1, 1))
            record["vif"][lhs] = {n: _num(v) for n, v in zip(res.model.exog_names[1:], np.diag(inverse))}
        except np.linalg.LinAlgError:
            record["vif"][lhs] = {n: None for n in res.model.exog_names[1:]}
        designs.append((np.asarray(res.model.endog, float), np.asarray(res.model.exog, float),
                        [(keys[n], i) for i, n in enumerate(res.model.exog_names) if n in keys]))
    return record, designs


def _fit(df, model, center=None, level=0.95) -> tuple:
    regressions = _regressions(model)
    names = list(dict.fromkeys([lhs for lhs, _ in regressions] + [p for _, terms in regressions for _, term in terms
                                                                  for p in term.split(":")]))
    data, frame = _numeric(df, names, "fit_equations")
    if len(frame) <= len(names):
        raise ValueError(f"path_tools: {len(frame)} complete rows are too few for {len(names)} variables")
    if any(c not in names for c in center or ()):
        raise ValueError(f"path_tools: center names {', '.join(c for c in center if c not in names)}, not in the model")
    means = {c: float(frame[c].mean()) for c in center or ()}
    record = {"kind": "equations", "engine": f"statsmodels {version('statsmodels')} OLS", "model": model.strip(),
              "n": len(frame), "rows_sha256": _rows(frame), "rows_dropped": len(data) - len(frame), "level": level,
              "columns": {c: {"min": float(frame[c].min()), "max": float(frame[c].max()), "mean": float(frame[c].mean()),
                              "sd": float(frame[c].std()), **{f"p{q}": float(frame[c].quantile(q / 100)) for q in (16, 50, 84)}}
                          for c in names},
              "centring": {"columns": means, "around": f"mean of the {len(frame)} analysed rows" if means else "not centred"}}
    fitted, designs = _ols(frame.assign(**{c: frame[c] - m for c, m in means.items()}), regressions, data, level)
    record.update(fitted)
    if means:
        plain, _ = _ols(frame, regressions, data, level)
        record["uncentred"] = {k: c["value"] for k, c in plain["coefficients"].items() if ":" in c["term"]}
        record["vif_uncentred"] = plain["vif"]
    return record, designs


def fit_equations(df, model: str, center=None, level: float = 0.95) -> dict:
    """Every equation of an observed-variable model by OLS on the same rows; see the module docstring."""
    return _fit(df, model, center, level)[0]


def _points(probes, w: dict) -> list:
    """Probes with p16, p50 and p84 replaced by those percentiles of the moderator in the analysed rows."""
    return [w[p] if isinstance(p, str) and re.fullmatch(r"p(16|50|84)", p) else p for p in probes]


def probe(fit: dict, focal: str, interaction: str, moderator: str, probes, level: float = 0.95) -> dict:
    """Simple slopes of the focal coefficient across the moderator, from a fit_equations() record."""
    c = fit["coefficients"]
    if focal not in c or interaction not in c or c[focal]["lhs"] != c[interaction]["lhs"] or \
            moderator not in c[interaction]["term"].split(":") or moderator not in fit["columns"]:
        raise ValueError("path_tools.probe: focal and interaction must be labels of one equation, and the interaction "
                         "term must contain the moderator")
    lhs, w, cov = c[focal]["lhs"], fit["columns"][moderator], fit["cov"][c[focal]["lhs"]]
    out = pi.probe(b1=c[focal]["value"], b3=c[interaction]["value"], var_b1=cov[focal][focal],
                   var_b3=cov[interaction][interaction], cov_b13=cov[focal][interaction], df=fit["equations"][lhs]["df_resid"],
                   w_min=w["min"], w_max=w["max"], w_mean=w["mean"], w_sd=w["sd"], probes=_points(probes, w), level=level,
                   center=fit["centring"]["columns"].get(moderator, 0.0))
    record = {k: v for k, v in fit.items() if k not in ("cov", "uncentred", "columns")}
    record.update(kind="moderation", focal=focal, interaction=interaction, moderator={"column": moderator, **w}, probe=out)
    if "uncentred" in fit:
        record["b3_uncentred"] = fit["uncentred"][interaction]
    return record


def _semopy():
    try:
        import semopy
    except ImportError:
        return None
    return semopy


def _sem_parts(df, model: str) -> tuple:
    """The complete rows of a latent model's observed variables, and the model with the observed exogenous
    variables' variances and covariances declared, so that semopy counts df as lavaan does."""
    statements = [s for s in parse(model) if s[1] != ":="]
    if any(":" in term for _, _, terms in statements for _, term in terms):
        raise ValueError("path_tools: product terms in a latent model (latent interactions) are outside this skill")
    latent = {lhs for lhs, op, _ in statements if op == "=~"}
    names = {lhs for lhs, _, _ in statements} | {term for _, _, terms in statements for _, term in terms}
    data, frame = _numeric(df, [c for c in df.columns if c in names - latent] + sorted(names - latent - set(df.columns)),
                           "fit_sem")
    outcomes = {lhs for lhs, op, _ in statements if op == "~"}
    indicators = {term for _, op, terms in statements if op == "=~" for _, term in terms}
    exogenous = [c for c in frame.columns if c not in outcomes | indicators]
    have = atoms(model)
    declared = [f"{a} ~~ {b}" for i, a in enumerate(exogenous) for b in exogenous[i:]
                if f"{min(a, b)} ~~ {max(a, b)}" not in have]
    kept = [line for line in model.splitlines() if ":=" not in line.split("#", 1)[0]]      # semopy has no :=
    return data, frame, "\n".join(kept + declared), declared


def _paths(table, statements) -> dict:
    """{label or lhs~term: row} for every regression path of a fitted semopy model."""
    out = {}
    for lhs, op, terms in statements:
        for label, term in terms if op == "~" else ():
            hit = table[(table["lval"] == lhs) & (table["op"] == "~") & (table["rval"] == term)]
            if len(hit):
                out[label or f"{lhs}~{term}"] = hit.iloc[0]
    return out


def fit_sem(df, model: str, obj: str = "MLW") -> dict:
    """A latent structural model with semopy; see the module docstring."""
    semopy = _semopy()
    if semopy is None:
        return {"kind": "sem", "status": "not_checked", "reason": NO_SEMOPY, "model": model.strip()}
    data, frame, syntax, declared = _sem_parts(df, model)
    record = {"kind": "sem", "engine": f"semopy {version('semopy')}", "estimator": obj, "model": model.strip(),
              "n": len(frame), "rows_sha256": _rows(frame), "rows_dropped": len(data) - len(frame), "declared": declared}
    try:
        fitted = semopy.Model(syntax)
        result = fitted.fit(frame, obj=obj)
        with warnings.catch_warnings():              # semopy divides by df, which is 0 for a saturated model
            warnings.simplefilter("ignore", RuntimeWarning)
            stats, table = semopy.calc_stats(fitted).T["Value"], fitted.inspect(std_est=True)
        observed = list(fitted.vars["observed"])
        sample = np.cov(frame[observed].to_numpy(float), rowvar=False, bias=True)
        implied = fitted.calc_sigma()[0]
    except Exception as exc:                     # semopy raises on singular matrices and on syntax it cannot read
        return {**record, "converged": False, "message": f"{type(exc).__name__}: {exc}"}
    residual = (sample - implied) / np.sqrt(np.outer(np.diag(sample), np.diag(sample)))
    df_model = int(round(stats["DoF"]))
    fit = {"chi2": _num(stats["chi2"]), "chi2_p": _num(stats["chi2 p-value"]), "cfi": _num(stats["CFI"]),
           "tli": _num(stats["TLI"]), "rmsea": _num(stats["RMSEA"]),
           "srmr": float(np.sqrt(np.mean(residual[np.tril_indices(len(observed))] ** 2)))}
    if df_model == 0:
        fit.update(cfi=None, tli=None, rmsea=None, note="df = 0: the model reproduces the data exactly and its fit says nothing")
    paths = {key: {"lhs": row["lval"], "term": row["rval"], "value": _num(row["Estimate"]), "se": _num(row["Std. Err"]),
                   "z": _num(row["z-value"]), "p": _num(row["p-value"]), "std": _num(row["Est. Std"])}
             for key, row in _paths(table, parse(model)).items()}
    return {**record, "converged": bool(result.success), "message": str(result.message), "df": df_model, "fit": fit,
            "srmr_formula": SRMR_FORMULA, "coefficients": paths}


def _ols_solver(designs):
    def solve(rows):
        found = {}
        for y, x, keys in designs:
            xb, yb = x[rows], y[rows]
            xtx, xty = np.einsum("bij,bik->bjk", xb, xb), np.einsum("bij,bi->bj", xb, yb)
            try:
                beta = np.linalg.solve(xtx, xty[..., None])[..., 0]
            except np.linalg.LinAlgError:          # a resample without variation in a column
                beta = np.array([np.linalg.lstsq(a, b, rcond=None)[0] if np.linalg.matrix_rank(a) == len(b)
                                 else np.full(len(b), np.nan) for a, b in zip(xtx, xty)])
            found.update({key: beta[:, j] for key, j in keys})
        return found
    return solve


def _sem_solver(semopy, frame, syntax, model):
    statements = parse(model)

    def solve(rows):
        found = {}
        for i, sample in enumerate(rows):
            try:
                fitted = semopy.Model(syntax)
                if not fitted.fit(frame.iloc[sample], obj="MLW").success:
                    continue
                for key, row in _paths(fitted.inspect(), statements).items():
                    found.setdefault(key, np.full(len(rows), np.nan))[i] = float(row["Estimate"])
            except Exception:                      # a resample semopy cannot fit counts as failed
                continue
        return found
    return solve


def _draws(solve, defined, blocks):
    out = {name: [] for name in defined}
    for rows in blocks:
        found = solve(rows)
        for name, expression in defined.items():
            try:
                out[name].append(np.broadcast_to(np.asarray(evaluate(expression, found), float), (len(rows),)))
            except ValueError:                     # every draw of the block failed
                out[name].append(np.full(len(rows), np.nan))
    return {name: np.concatenate(v) for name, v in out.items()}


def _bca(draws, estimate, jack, level):
    """Bias-corrected and accelerated bounds; (None, None, reason) when they are not defined."""
    below = (np.sum(draws < estimate) + 0.5 * np.sum(draws == estimate)) / len(draws)
    if not 0 < below < 1 or not np.all(np.isfinite(jack)):
        return None, None, {"note": "BCa is not defined: every draw lies on one side of the estimate, or a jackknife fit failed"}
    normal = NormalDist()
    z0, spread = normal.inv_cdf(below), jack.mean() - jack
    acceleration = float(np.sum(spread ** 3) / (6 * np.sum(spread ** 2) ** 1.5)) if np.any(spread) else 0.0
    bounds = [normal.cdf(z0 + (z0 + z) / (1 - acceleration * (z0 + z)))
              for z in (normal.inv_cdf((1 - level) / 2), normal.inv_cdf((1 + level) / 2))]
    low, high = np.quantile(draws, bounds)
    return float(low), float(high), {"z0": z0, "acceleration": acceleration}


def bootstrap_indirect(df, model: str, defined=None, n_boot: int = 5000, seed=None, method: str = "percentile",
                       level: float = 0.95, center=None) -> dict:
    """Defined parameters with a seeded case bootstrap; see the module docstring."""
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError("path_tools: seed= must be the whole number recorded in model.md")
    n_boot = int(n_boot)
    if method not in ("percentile", "bca") or n_boot < 2:
        raise ValueError("path_tools: method must be 'percentile' or 'bca', and n_boot at least 2")
    defined = dict(defined or {name: rhs for name, op, rhs in parse(model) if op == ":="})
    if not defined:
        raise ValueError("path_tools: no defined parameter: pass defined={'ind': 'a*b'} or write ind := a*b in the model")
    if any(op in ("=~", "~~") for _, op, _ in parse(model)):
        semopy = _semopy()
        if semopy is None:
            return {"kind": "mediation", "status": "not_checked", "reason": NO_SEMOPY, "model": model.strip()}
        record = fit_sem(df, model)
        if not record.get("converged"):
            return record
        _, frame, syntax, _ = _sem_parts(df, model)
        solve, n, block = _sem_solver(semopy, frame, syntax, model), len(frame), 50
    else:
        record, designs = _fit(df, model, center, level)
        record.pop("cov")
        n = record["n"]
        solve, block = _ols_solver(designs), max(1, MEMORY // (n * max(x.shape[1] for _, x, _ in designs)))
    values = {key: c["value"] for key, c in record["coefficients"].items()}
    estimates = {name: float(evaluate(expression, values)) for name, expression in defined.items()}
    rng = np.random.default_rng(int(seed))
    sizes = [min(block, n_boot - start) for start in range(0, n_boot, block)]
    draws = _draws(solve, defined, (rng.integers(0, n, size=(size, n)) for size in sizes))
    good = np.logical_and.reduce([np.isfinite(v) for v in draws.values()])
    if method == "bca":
        everyone = np.arange(n)
        jack = _draws(solve, defined, (np.array([np.delete(everyone, i) for i in range(start, min(n, start + block))])
                                       for start in range(0, n, block)))
    out, q = {}, (1 - level) / 2
    for name, expression in defined.items():
        kept = draws[name][good]
        entry = {"expression": expression, "estimate": estimates[name], "se": float(kept.std(ddof=1)) if len(kept) > 1 else None}
        if len(kept) < 2:
            entry.update(low=None, high=None, note="fewer than two draws could be fitted")
        elif method == "percentile":
            entry.update(zip(("low", "high"), map(float, np.quantile(kept, [q, 1 - q]))))
        else:
            low, high, extra = _bca(kept, estimates[name], jack[name], level)
            entry.update(low=low, high=high, **({"bca": extra} if low is not None else extra))
        out[name] = entry
    record.update(kind="mediation", defined=out, interval={
        "method": method, "level": level, "draws": n_boot, "seed": int(seed), "failed": int((~good).sum()),
        "resampled": "cases (rows) with replacement"})
    return record


def moderated_mediation_index(df, model: str, index: str, conditional: str, moderator: str, probes, n_boot: int = 5000,
                              seed=None, method: str = "percentile", level: float = 0.95, center=None) -> dict:
    """The index of moderated mediation and conditional indirect effects; see the module docstring."""
    if "{w}" not in conditional:
        raise ValueError("path_tools: conditional must contain {w}, for example (a1 + a3*{w})*b")
    fit = fit_equations(df, model, center, level)
    if moderator not in fit["columns"]:
        raise ValueError(f"path_tools: the model does not use {moderator}")
    w, shift = fit["columns"][moderator], fit["centring"]["columns"].get(moderator, 0.0)
    points = pi.resolve(_points(probes, w), w["mean"], w["sd"])
    defined = {"index": index, **{f"at {label}": conditional.replace("{w}", f"({float(value)!r} - {float(shift)!r})")
                                  for label, value in points}}
    record = bootstrap_indirect(df, model, defined, n_boot, seed, method, level, center)
    for label, value in points:
        record["defined"][f"at {label}"]["at"] = value
    record.update(kind="moderated_mediation", index="index", moderator={"column": moderator, **w})
    return record
