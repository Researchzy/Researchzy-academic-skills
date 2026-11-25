#!/usr/bin/env python3
"""Psychometric computations for the analysis script of researchzy-psychometrics.

Import it; it has no commands.

    import sys
    sys.path.insert(0, "<the scripts folder of this skill>")
    import pandas as pd
    import psy_tools as pt
    import rz_results as rz
    rz.OUT = "psychometrics"

    data = pd.read_csv("psychometrics/survey.scored.csv")
    items = pt.item_map("psychometrics/items.json")                       # {construct: [items]}
    a = pt.alpha(data[items["AUT"]], ci="feldt")
    pa = pt.parallel_analysis(data[every_item], n_sets=500, percentile=95, seed=SEED)
    cfa = pt.cfa_semopy(data, pt.cfa_syntax("psychometrics/items.json"), matrices="psychometrics/cfa.matrices.json")

  alpha(df, ci, level, seed, n_boot)       Cronbach's alpha, with a Feldt or a seeded percentile-bootstrap interval
  item_stats(df, scale_min, scale_max)     per item: item-rest r, alpha if deleted, floor and ceiling shares,
                                           categories used, skewness
  parallel_analysis(df, n_sets, percentile, seed, kind, criterion)
                                           observed eigenvalues against those of random normal data of the same
                                           size; the factors that parallel analysis and Kaiser's rule each give
  efa(df, n_factors, method, rotation)     statsmodels Factor: loadings, communalities, factor correlations
  omega_cr_ave(loadings, errors)           omega, CR and AVE of one factor; None with the reasons when a loading
                                           is negative or |loading| >= 1, a variance is negative, or k < 2
  validity(cfa)                            omega_cr_ave() for every factor of a cfa_semopy() record
  htmt(corr, item_map, matrices)           heterotrait-monotrait ratio of each pair of constructs
  srmr(sample_cov, implied_cov)            SRMR, with the formula used
  cfa_syntax(items)                        lavaan-style measurement syntax from items.json
  cfa_semopy(df, syntax, obj, matrices)    fit with semopy and return the CFA record
  harman(df)                               variance share of the first unrotated principal component
  marker_adjust(corr, marker, r_m)         correlations adjusted for a marker variable

Rows with a missing value in the columns used are dropped (listwise) and the n used is returned.
Results are plain numbers, lists and dicts, ready for rz.record(..., extra={"psy": {...}}). Nothing
here judges a value against a cut-off. matrices= writes the covariance or correlation matrices to
that JSON file and returns its SHA-256, so that check_psychometrics.py can recompute SRMR and HTMT
without putting the matrices into results.json.

Needs numpy, pandas and scipy; efa() needs statsmodels, and cfa_semopy() semopy, which returns
{"status": "not_checked", "reason": ...} when semopy is not installed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

SRMR_FORMULA = ("square root of the mean, over the lower triangle with the diagonal, of ((s_ij - sigma_ij) / "
                "sqrt(s_ii s_jj))^2; s is the sample covariance with divisor n")
HTMT_FORMULA = ("mean correlation between the items of two constructs / sqrt(product of the mean correlations "
                "among the items within each)")


def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_plain(v) for v in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if np.isnan(value) else float(value)
    return value


def _complete(df, columns=None) -> pd.DataFrame:
    frame = (df if columns is None else df[list(columns)]).apply(pd.to_numeric, errors="coerce").dropna()
    if frame.shape[1] < 2 or len(frame) < 3:
        raise ValueError("psy_tools: needs two or more items and three or more complete rows")
    return frame


def _alpha(x: np.ndarray) -> float:
    total = x.sum(axis=1).var(ddof=1)
    if total == 0:
        raise ValueError("psy_tools: the total score is constant, so alpha is not defined")
    k = x.shape[1]
    return k / (k - 1) * (1 - x.var(axis=0, ddof=1).sum() / total)


def _r(x, y):
    return float(np.corrcoef(x, y)[0, 1]) if x.std() > 0 and y.std() > 0 else None


def save_matrices(path, **matrices) -> dict:
    """Write matrices (and item names) to a JSON file; return its path and SHA-256 for the record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_plain(matrices)) + "\n", encoding="utf-8")
    return {"path": path.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def item_map(items) -> dict:
    """{construct: [items]} from items.json (a path or the loaded dict)."""
    spec = json.loads(Path(items).read_text(encoding="utf-8")) if isinstance(items, (str, Path)) else items
    return {name: list(c["items"]) for name, c in spec["constructs"].items()}


def alpha(df, ci="feldt", level=0.95, seed=None, n_boot=2000) -> dict:
    """Cronbach's alpha with its interval: Feldt's F-based interval, or a seeded percentile bootstrap."""
    x = _complete(df).to_numpy(float)
    n, k = x.shape
    a, q = _alpha(x), (1 - level) / 2
    out = {"alpha": a, "ci": ci, "level": level, "n": n, "k": k}
    if ci == "feldt":                       # (1 - alpha) / (1 - alpha_hat) ~ F(n - 1, (n - 1)(k - 1))
        df1, df2 = n - 1, (n - 1) * (k - 1)
        out.update(low=1 - (1 - a) * stats.f.ppf(1 - q, df1, df2), high=1 - (1 - a) * stats.f.ppf(q, df1, df2))
    elif ci == "bootstrap":
        if seed is None:
            raise ValueError("psy_tools.alpha: a bootstrap interval needs seed=")
        rng = np.random.default_rng(seed)
        draws = [_alpha(x[rng.integers(0, n, n)]) for _ in range(n_boot)]
        out.update(low=np.percentile(draws, 100 * q), high=np.percentile(draws, 100 * (1 - q)), seed=seed,
                   n_boot=n_boot, interval="percentile")
    else:
        raise ValueError("psy_tools.alpha: ci must be 'feldt' or 'bootstrap'")
    return _plain(out)


def item_stats(df, scale_min=None, scale_max=None) -> dict:
    """Corrected item-total (item-rest) r, alpha if deleted, floor and ceiling shares, categories, skewness."""
    frame = _complete(df)
    x = frame.to_numpy(float)
    total = x.sum(axis=1)
    lo, hi = (x.min() if scale_min is None else scale_min), (x.max() if scale_max is None else scale_max)
    out = {}
    for j, item in enumerate(frame.columns):
        col = x[:, j]
        out[str(item)] = {"mean": col.mean(), "sd": col.std(ddof=1), "item_rest_r": _r(col, total - col),
                          "alpha_if_deleted": _alpha(np.delete(x, j, axis=1)) if x.shape[1] > 2 else None,
                          "floor": np.mean(col == lo), "ceiling": np.mean(col == hi),
                          "categories_used": len(np.unique(col)), "skew": stats.skew(col)}
    return _plain({"n": len(frame), "scale": [lo, hi], "items": out})


def _eigen(corr: np.ndarray, kind: str) -> np.ndarray:
    if kind == "fa":                        # reduced matrix: squared multiple correlations on the diagonal
        corr = corr.copy()
        np.fill_diagonal(corr, 1 - 1 / np.diag(np.linalg.inv(corr)))
    return np.sort(np.linalg.eigvalsh(corr))[::-1]


def parallel_analysis(df, n_sets=500, percentile=95, seed=None, kind="pca", criterion="percentile") -> dict:
    """Horn's parallel analysis against random normal data of the same n and number of items, seeded.

    kind "pca" compares eigenvalues of the correlation matrix, "fa" those of the reduced matrix.
    criterion "percentile" retains factors whose eigenvalue exceeds that percentile of the random
    ones, "mean" the random mean. Kaiser's count (eigenvalues of the full matrix above 1) is
    returned beside it, as a second rule to report, not to choose by.
    """
    if seed is None:
        raise ValueError("psy_tools.parallel_analysis: pass seed= so that the analysis can be repeated")
    if kind not in ("pca", "fa") or criterion not in ("percentile", "mean"):
        raise ValueError("psy_tools.parallel_analysis: kind is 'pca' or 'fa', criterion 'percentile' or 'mean'")
    x = _complete(df).to_numpy(float)
    n, p = x.shape
    rng = np.random.default_rng(seed)
    corr = np.corrcoef(x, rowvar=False)
    observed = _eigen(corr, kind)
    random = np.array([_eigen(np.corrcoef(rng.standard_normal((n, p)), rowvar=False), kind) for _ in range(n_sets)])
    mean, upper = random.mean(axis=0), np.percentile(random, percentile, axis=0)
    reference = upper if criterion == "percentile" else mean
    suggested = next((i for i, (o, r) in enumerate(zip(observed, reference)) if o <= r), p)
    full = np.sort(np.linalg.eigvalsh(corr))[::-1]
    return _plain({"observed": observed, "random_mean": mean, "random_percentile": upper, "percentile": percentile,
                   "criterion": criterion, "n_sets": n_sets, "seed": seed, "eigen": kind, "data": "normal", "n": n,
                   "p": p, "suggested": suggested, "kaiser": {"eigenvalues": full, "count": int((full > 1).sum())}})


def efa(df, n_factors, method="pa", rotation="oblimin") -> dict:
    """Exploratory factor analysis with statsmodels' Factor on Pearson correlations.

    method "pa" (principal axis) or "ml"; rotation one of statsmodels' names ("oblimin" is its
    quartimin, an oblique rotation) or None. Each factor's sign is set so that its loadings sum to
    a positive number. Factor correlations come from the rotated and unrotated loadings, so they are
    right for any rotation (the identity for an orthogonal one).
    """
    from statsmodels.multivariate.factor import Factor
    frame = _complete(df)
    result = Factor(frame.to_numpy(float), n_factor=n_factors, method=method).fit()
    unrotated = np.real(np.asarray(result.loadings, dtype=complex))
    rotated = bool(rotation) and n_factors > 1
    if rotated:
        result.rotate(rotation)
    load = np.real(np.asarray(result.loadings, dtype=complex))
    inverse = np.linalg.pinv(load)
    phi = inverse @ unrotated @ unrotated.T @ inverse.T
    signs = np.where(load.sum(axis=0) < 0, -1.0, 1.0)
    load, phi = load * signs, phi * np.outer(signs, signs)
    names, items = [f"F{i + 1}" for i in range(n_factors)], [str(c) for c in frame.columns]
    return _plain({"n": len(frame), "correlation": "pearson", "method": method, "rotation": rotation if rotated else "none",
                   "n_factors": n_factors, "loadings": {i: dict(zip(names, row)) for i, row in zip(items, load)},
                   "communalities": dict(zip(items, np.real(np.asarray(result.communality, dtype=complex)))),
                   "factor_corr": {a: dict(zip(names, row)) for a, row in zip(names, phi)}})


def omega_cr_ave(loadings, errors) -> dict:
    """omega, CR and AVE of one factor from its items' standardized loadings and error variances.

    omega = (sum l)^2 / ((sum l)^2 + sum theta), with theta as given; CR = (sum l)^2 / ((sum l)^2 +
    sum (1 - l^2)); AVE = mean of l^2. With one loading per item, theta = 1 - l^2 and omega = CR.
    """
    if isinstance(loadings, dict):
        names, lam = list(loadings), np.array(list(loadings.values()), float)
        theta = np.array([errors[i] for i in names] if isinstance(errors, dict) else errors, float)
    else:
        lam, theta = np.asarray(loadings, float), np.asarray(errors, float)
    problems = (["fewer than two items"] if len(lam) < 2 else []) + \
        (["a standardized loading of 1 or more (Heywood case)"] if np.any(np.abs(lam) >= 1) else []) + \
        (["a negative error variance (Heywood case)"] if np.any(theta < 0) else []) + \
        (["a negative loading: reverse-score the item or check its key"] if np.any(lam < 0) else [])
    if problems:
        return {"omega": None, "cr": None, "ave": None, "k": len(lam), "problems": problems}
    s = lam.sum()
    return _plain({"omega": s ** 2 / (s ** 2 + theta.sum()), "cr": s ** 2 / (s ** 2 + (1 - lam ** 2).sum()),
                   "ave": (lam ** 2).mean(), "k": len(lam), "problems": []})


def validity(cfa: dict) -> dict:
    """omega, CR and AVE of every factor of a cfa_semopy() record (or one with the same fields)."""
    out = {"omega": {}, "cr": {}, "ave": {}, "problems": {}}
    for factor, items in cfa["loadings"].items():
        v = omega_cr_ave(items, {i: cfa["errors"][i] for i in items})
        for key in ("omega", "cr", "ave"):
            out[key][factor] = v[key]
        if v["problems"]:
            out["problems"][factor] = v["problems"]
    return out


def htmt(corr, item_map, matrices=None) -> dict:
    """Heterotrait-monotrait ratio of each pair of constructs from an item correlation matrix."""
    c = corr if isinstance(corr, pd.DataFrame) else pd.DataFrame(corr)

    def mono(items):
        block = c.loc[items, items].to_numpy(float)
        return block[np.triu_indices(len(items), 1)].mean() if len(items) > 1 else np.nan

    names, out = list(item_map), {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            product = mono(item_map[a]) * mono(item_map[b])
            value = c.loc[item_map[a], item_map[b]].to_numpy(float).mean() / np.sqrt(product) if product > 0 else np.nan
            out.setdefault(a, {})[b] = value
    record = {"matrix": out, "formula": HTMT_FORMULA, "items": item_map}
    if matrices:
        record["matrices"] = save_matrices(matrices, items=list(c.columns), corr=c.to_numpy(float))
    return _plain(record)


def srmr(sample_cov, implied_cov) -> dict:
    s, sigma = np.asarray(sample_cov, float), np.asarray(implied_cov, float)
    sd = np.sqrt(np.diag(s))
    residual = (s - sigma) / np.outer(sd, sd)
    return {"srmr": float(np.sqrt(np.mean(residual[np.tril_indices(len(s))] ** 2))), "formula": SRMR_FORMULA}


def cfa_syntax(items) -> str:
    """One line "construct =~ item + item + ..." per construct of items.json."""
    lines = []
    for name, members in item_map(items).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", name):
            raise ValueError(f"psy_tools.cfa_syntax: {name!r} is not a name lavaan or semopy accepts; use letters, "
                             "digits and _ in items.json")
        lines.append(f"{name} =~ " + " + ".join(members))
    return "\n".join(lines)


def cfa_semopy(df, syntax, obj="MLW", matrices=None) -> dict:
    """Fit a CFA with semopy and return its record; the estimator and the ordinal decision are the analyst's.

    The record holds convergence, df, free parameters, identification (semopy fixes each factor's
    first loading to 1), standardized loadings and error variances, factor correlations, other
    improper estimates (negative factor variances) under "heywood", and the fit with SRMR computed
    from the sample and model-implied covariance matrices. Add "ordinal" before recording it.
    """
    try:
        import semopy
    except ImportError:
        return {"status": "not_checked", "reason": "semopy is not installed: ask the user before installing it "
                                                   "(python3 -m pip install --user semopy), or use lavaan if R has "
                                                   "it (Rscript -e 'library(lavaan)')"}
    from importlib.metadata import version
    factors = {m.group(1): re.split(r"\s*\+\s*", m.group(2).strip())
               for m in re.finditer(r"^\s*(\w+)\s*=~\s*(.+?)\s*$", syntax, re.M)}
    frame = _complete(df, dict.fromkeys(i for items in factors.values() for i in items))
    model = semopy.Model(syntax)
    base = {"engine": "semopy", "engine_version": version("semopy"), "estimator": obj, "n": len(frame),
            "identification": "marker: the first loading of each factor fixed to 1 (semopy's default)", "factors": factors}
    try:
        result = model.fit(frame, obj=obj)
        fit = semopy.calc_stats(model).T["Value"]
    except Exception as exc:                 # semopy raises on singular matrices and on syntax it cannot read
        return {**base, "converged": False, "message": f"{type(exc).__name__}: {exc}"}
    latent = set(model.vars["latent"])
    loadings, errors, phi, heywood = {}, {}, {}, []
    for row in model.inspect(std_est=True).to_dict("records"):
        if row["op"] == "~" and row["rval"] in latent:
            loadings.setdefault(row["rval"], {})[row["lval"]] = float(row["Est. Std"])
        elif row["op"] == "~~" and row["lval"] == row["rval"] and row["lval"] not in latent:
            errors[row["lval"]] = float(row["Est. Std"])
        elif row["op"] == "~~" and row["lval"] == row["rval"] and float(row["Estimate"]) < 0:
            heywood.append(f"negative variance of {row['lval']}: {float(row['Estimate']):.4g}")
        elif row["op"] == "~~" and row["lval"] != row["rval"] and row["lval"] in latent and row["rval"] in latent:
            phi.setdefault(row["lval"], {})[row["rval"]] = float(row["Est. Std"])
    sample, implied = np.asarray(model.mx_cov, float), np.asarray(model.calc_sigma()[0], float)
    s = srmr(sample, implied)
    record = {**base, "converged": bool(result.success) and bool(np.isfinite(fit["chi2"])), "message": str(result.message),
              "iterations": int(result.n_it), "df": int(round(fit["DoF"])), "n_free": len(model.param_vals),
              "loadings": loadings, "errors": errors, "factor_corr": phi, "heywood": heywood,
              "fit": {"chi2": fit["chi2"], "df": int(round(fit["DoF"])), "p": fit["chi2 p-value"], "cfi": fit["CFI"],
                      "tli": fit["TLI"], "rmsea": fit["RMSEA"], "srmr": s["srmr"], "srmr_formula": s["formula"]}}
    if matrices:
        record["matrices"] = save_matrices(matrices, observed=list(model.vars["observed"]), sample_cov=sample,
                                           implied_cov=implied)
    return _plain(record)


def harman(df) -> dict:
    """Harman's single-factor test as usually run: the variance share of the first unrotated component."""
    frame = _complete(df)
    eigenvalues = np.linalg.eigvalsh(np.corrcoef(frame.to_numpy(float), rowvar=False))
    return _plain({"test": "harman", "share": eigenvalues[-1] / frame.shape[1], "items": frame.shape[1],
                   "n": len(frame), "extraction": "first unrotated principal component of the item correlations"})


def marker_adjust(corr, marker, r_m=None) -> dict:
    """Correlations adjusted for a marker variable: (r - r_M) / (1 - r_M).

    r_M is the smallest correlation of the marker with the other variables, floored at 0, unless
    given. corr is a correlation matrix (a DataFrame) of the composites and the marker.
    """
    c = corr if isinstance(corr, pd.DataFrame) else pd.DataFrame(corr)
    others = [v for v in c.columns if v != marker]
    if r_m is None:
        r_m, source = max(0.0, float(c.loc[marker, others].min())), "smallest correlation of the marker, floored at 0"
    else:
        source = "given"
    observed = c.loc[others, others].to_numpy(float)
    adjusted = (observed - r_m) / (1 - r_m)
    np.fill_diagonal(adjusted, 1.0)
    return _plain({"test": "marker", "marker": marker, "r_m": r_m, "r_m_source": source,
                   "adjusted": {a: dict(zip(others, row)) for a, row in zip(others, adjusted)},
                   "max_change": np.abs(adjusted - observed).max()})
