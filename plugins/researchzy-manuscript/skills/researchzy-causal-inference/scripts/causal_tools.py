#!/usr/bin/env python3
"""Estimators and design checks for a causal analysis, imported by the analysis script next to rz_results.

    import sys
    sys.path.insert(0, "<the scripts folder of this skill>")
    import rz_results as rz
    import causal_tools as ct
    rz.OUT = "causal"

  first_treated, event_dummies, event_path   cohorts; binned event dummies with ref (-1) omitted
  callaway_santanna      group-time ATTs without covariates, aggregations, cluster bootstrap, sup-t
  twfe                   two-way fixed effects with cluster-robust errors: a benchmark
  relative_magnitude     the simplified relative-magnitude sensitivity and its breakdown M
  iv_2sls, anderson_rubin   2SLS with the first stage, robust F, reduced form and OLS; the AR set
  ri_pvalue              randomization inference with the +1, by cluster and stratum
  synth_weights, sc_placebos   simplex weights; in-space placebos with RMSPE ratios
  ipw                    propensity weighting: overlap, trimming by dropping, balance
  spec                   rz_results.record() with the causal fields checked, in extra["causal"]
  simulate_staggered     a staggered panel with a known ATT, for tests and dry runs

Errors are CR1, G/(G-1) * (N-1)/(N-K), with t(G-1) intervals, or HC1 without clusters; unit effects
removed by demeaning are not counted in K. Bad input raises ValueError with a plain message.

Needs numpy, pandas and statsmodels (which brings scipy); spec() and relative_magnitude() work
without them. Portions are derived from MIT-licensed code: see LICENSE-MIT-causal_tools.txt next to
this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import importlib
import math
import numbers
import sys
from statistics import NormalDist

try:
    import numpy as np
    import pandas as pd
except ImportError:        # spec() and relative_magnitude() work without them
    np = pd = None

__version__ = "1.0.0"
STATUSES = ("pass", "fail", "not_checked")
SENSITIVITY_LABEL = "simplified version, not the Rambachan–Roth confidence set"
BLOCK = 200                # bootstrap draws computed at once, to bound memory


def _need():
    if np is None or pd is None:
        raise ImportError("causal_tools needs numpy, pandas and statsmodels; ask the user before installing them")


def _z(level):
    return NormalDist().inv_cdf(0.5 + level / 2)


def _row(b, se, dof, level):
    """Estimate, standard error, interval (t with dof, normal without) and two-sided p."""
    from scipy import stats
    c = float(stats.t.ppf(0.5 + level / 2, dof)) if dof else _z(level)
    tail = stats.t.sf(abs(b / se), dof) if dof else stats.norm.sf(abs(b / se))
    return {"estimate": float(b), "se": float(se), "low": float(b - c * se), "high": float(b + c * se),
            "p": float(2 * tail)}


def _num(x):
    x = float(x)
    return int(x) if x.is_integer() else x


def _codes(values):
    codes, uniques = pd.factorize(pd.Series(values), sort=True)
    if (codes < 0).any():
        raise ValueError("a cluster or stratum value is missing")
    return codes, len(uniques)


def _sandwich(X, u, bread, groups):
    """CR1 covariance (HC1 without groups) and the t degrees of freedom: G - 1, or None."""
    n, k = X.shape
    scores = X * u[:, None]
    if groups is None:
        return n / (n - k) * bread @ (scores.T @ scores) @ bread, None
    codes, G = _codes(groups)
    if G < 2:
        raise ValueError("cluster-robust errors need at least two clusters")
    summed = np.zeros((G, k))
    np.add.at(summed, codes, scores)
    return G / (G - 1) * (n - 1) / (n - k) * bread @ (summed.T @ summed) @ bread, G - 1


def _ols(y, X, groups=None):
    if np.linalg.matrix_rank(X) < X.shape[1]:
        raise ValueError("the regressors are collinear: one is constant, duplicated or absorbed by the fixed effects")
    bread = np.linalg.inv(X.T @ X)
    beta = bread @ X.T @ y
    return (beta, *_sandwich(X, y - X @ beta, bread, groups))


def _cohorts(values, periods):
    """Cohorts as floats, never-treated as NaN: missing, infinite, or 0 when 0 is not a period."""
    try:
        g = pd.to_numeric(pd.Series(values)).astype(float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"cohorts must be periods or missing: {exc}") from exc
    if (g == 0).any() and 0 in set(periods):
        raise ValueError("cohort 0 is also a period: code never-treated units as missing")
    return g.mask(np.isinf(g) | (g == 0))


def first_treated(df, *, unit, time, treat):
    """The first period with treat == 1 of each row's unit; NaN for never-treated units."""
    _need()
    d = df[[unit, time, treat]].dropna().sort_values([unit, time])
    if not d[treat].isin([0, 1]).all():
        raise ValueError(f"{treat} must be 0 or 1: continuous or multi-valued treatments are outside this skill")
    off = d.groupby(unit)[treat].diff().lt(0)
    if off.any():
        raise ValueError(f"{treat} switches off again for {d.loc[off, unit].nunique()} unit(s): designs where "
                         "treatment turns on and off are outside this skill")
    return df[unit].map(d[d[treat] == 1].groupby(unit)[time].min())


def _name(k):
    return f"lead{-k}" if k < 0 else f"lag{k}"


def event_dummies(df, *, time, cohort, window=(-5, 4), ref=-1):
    """Binned event-time dummies (lead5 ... lag4, ref omitted): (a copy of df with them, their names).

    Event time is time - cohort in consecutive integer periods; never-treated rows get zeros. Times
    beyond the window fall into its end bins, since a row left at zero reads as the reference period.
    ValueError unless ref rows have no dummy, other treated rows one, never-treated rows none.
    """
    _need()
    lo, hi = window
    if not lo < ref < hi:
        raise ValueError(f"ref {ref} must lie strictly inside the window {window}, or an end bin merges with it")
    out = df.copy()
    g = _cohorts(out[cohort], out[time].unique())
    g.index = out.index
    ever, binned, names = g.notna(), (out[time] - g).clip(lower=lo, upper=hi), []
    for k in (k for k in range(lo, hi + 1) if k != ref):
        names.append(_name(k))
        out[names[-1]] = ((binned == k) & ever).astype(int)
    on, at_ref = out[names].sum(axis=1), ever & (binned == ref)
    if not ((on[at_ref] == 0).all() and (on[ever & ~at_ref] == 1).all() and (on[~ever] == 0).all()):
        raise ValueError("event dummies: a treated row has no dummy or several (are the periods consecutive "
                         "integers?), or a never-treated row has one")
    return out, names


def event_path(coef, se, *, window=(-5, 4), ref=-1):
    """[(event time, coefficient, standard error)] over the window, ref put back as an exact 0."""
    return [(k, 0.0, 0.0) if k == ref else (k, float(coef[_name(k)]), float(se[_name(k)]))
            for k in range(window[0], window[1] + 1)]


def twfe(df, *, unit, time, outcome, regressors, cluster=None, level=0.95):
    """OLS of outcome on regressors with unit effects (demeaned, exact when unbalanced) and period
    dummies, CR1 by cluster (default unit): {"coef": {name: {estimate, se, low, high, p}}, "G", ...}."""
    _need()
    cluster, regressors = cluster or unit, list(regressors)
    d = df[list(dict.fromkeys([unit, time, outcome, cluster, *regressors]))].dropna()
    X = pd.concat([d[regressors].astype(float),
                   pd.get_dummies(d[time], prefix="_period", drop_first=True, dtype=float)], axis=1)
    y = d[outcome].astype(float)
    Xd, yd = X - X.groupby(d[unit]).transform("mean"), y - y.groupby(d[unit]).transform("mean")
    beta, V, dof = _ols(yd.to_numpy(), Xd.to_numpy(), d[cluster].to_numpy())
    return {"estimator": "twfe", "coef": {name: _row(beta[i], math.sqrt(V[i, i]), dof, level)
                                          for i, name in enumerate(regressors)},
            "n_obs": len(d), "units": int(d[unit].nunique()), "cluster": cluster, "G": dof + 1, "level": level}


def callaway_santanna(df, *, unit, time, cohort, outcome, control="never_treated", cluster=None, B=999,
                      seed=None, level=0.95, balance_e=None):
    """Group-time ATTs without covariates (Callaway and Sant'Anna 2021) and their aggregations.

    ATT(g, t): the change from g - 1 (the same base for every t) to t, cohort g minus controls, which
    are never-treated units or, with control="not_yet_treated", also units adopting after max(t,
    g - 1). Units treated in the first period are dropped. "overall" weighs treated unit-periods
    equally, "group" treated units, "event" averages by event time (balance_e=E: cohorts seen up to
    e = E) and "event_average" over e >= 0. The bootstrap resamples clusters (default units) B times.
    """
    _need()
    if control not in ("never_treated", "not_yet_treated"):
        raise ValueError("control must be 'never_treated' or 'not_yet_treated'")
    if B and seed is None:
        raise ValueError("pass seed= so that the bootstrap gives the same numbers on every run")
    cluster = cluster or unit
    d = df[list(dict.fromkeys([unit, time, cohort, outcome, cluster]))]
    if d.duplicated([unit, time]).any():
        raise ValueError("several rows share a unit and a period: make one row per unit and period")
    for col in {cohort, cluster} - {unit}:
        if (d.groupby(unit)[col].nunique(dropna=False) > 1).any():
            raise ValueError(f"{col} must be the same in every row of a unit")
    periods = np.sort(d[time].dropna().unique())
    wide = d.pivot(index=unit, columns=time, values=outcome).reindex(columns=periods)
    g = _cohorts(d.groupby(unit)[cohort].first().reindex(wide.index), periods).to_numpy()
    keep = ~(g <= periods[0])
    clusters = (wide.index.to_numpy() if cluster == unit else
                d.groupby(unit)[cluster].first().reindex(wide.index).to_numpy())[keep]
    Y, gv, pos = wide.to_numpy(float)[keep], g[keep], {p: i for i, p in enumerate(periods)}
    cohorts = list(np.unique(gv[~np.isnan(gv)]))
    if any(c not in pos for c in cohorts):
        raise ValueError("every cohort must be one of the periods")
    cells, missing = [], []
    for c in cohorts:
        base = pos[c] - 1
        for it in (i for i in range(len(periods)) if i != base):
            ctrl = np.isnan(gv) | ((gv > periods[max(it, base)]) & (gv != c) & (control == "not_yet_treated"))
            ok = ~np.isnan(Y[:, it]) & ~np.isnan(Y[:, base])
            if ((gv == c) & ok).any() and (ctrl & ok).any():
                cells.append((c, periods[it], it - pos[c], Y[:, it] - Y[:, base], (gv == c) & ok, ctrl & ok))
            else:
                missing.append([_num(c), _num(periods[it])])
    if not any(cell[2] >= 0 for cell in cells):
        raise ValueError("no post-treatment group-time cell has both treated and control units"
                         + ("; there are no never-treated units: use control='not_yet_treated'"
                            if control == "never_treated" and not np.isnan(gv).any() else ""))
    G_, T_, E_ = (np.array([cell[i] for cell in cells]) for i in range(3))
    DY = np.column_stack([np.nan_to_num(cell[3]) for cell in cells])
    TM, CM = (np.column_stack([cell[i] for cell in cells]).astype(float) for i in (4, 5))
    post, in_event = E_ >= 0, np.ones(len(cells), bool)
    if balance_e is not None:
        in_event = (E_ <= balance_e) & np.array([pos[c] + balance_e <= len(periods) - 1 for c in G_])
    events = np.unique(E_[in_event])
    with_post = [c for c in cohorts if ((G_ == c) & post).any()]
    CO = np.column_stack([gv == c for c in with_post]).astype(float)

    def estimate(W):
        nt, nc = W @ TM, W @ CM
        with np.errstate(invalid="ignore", divide="ignore"):
            att = (W @ (DY * TM)) / nt - (W @ (DY * CM)) / nc
            event = np.column_stack([(att[:, m] * nt[:, m]).sum(1) / nt[:, m].sum(1)
                                     for m in (in_event & (E_ == e) for e in events)])
            by_g, ng = np.column_stack([att[:, (G_ == c) & post].mean(1) for c in with_post]), W @ CO
            return {"att": att, "overall": ((att * nt)[:, post].sum(1) / nt[:, post].sum(1))[:, None],
                    "event": event, "event_average": event[:, events >= 0].mean(1)[:, None],
                    "by_cohort": by_g, "group": ((by_g * ng).sum(1) / ng.sum(1))[:, None]}

    est, (codes, n_clusters) = estimate(np.ones((1, len(gv)))), _codes(clusters)
    draws, rng = {key: np.empty((0, value.shape[1])) for key, value in est.items()}, np.random.default_rng(seed)
    for start in range(0, B, BLOCK):
        counts = rng.multinomial(n_clusters, np.full(n_clusters, 1 / n_clusters), size=min(BLOCK, B - start))
        for key, value in estimate(counts[:, codes].astype(float)).items():
            draws[key] = np.vstack([draws[key], value])
    se = {key: np.nanstd(value, axis=0, ddof=1) if B > 1 else np.full(value.shape[1], np.nan)
          for key, value in draws.items()}
    z = _z(level)

    def summary(key, j):
        b, s = float(est[key][0, j]), float(se[key][j])
        return {"estimate": b, **({"se": None, "low": None, "high": None} if math.isnan(s) else
                                  {"se": s, "low": b - z * s, "high": b + z * s})}

    def sup_t(key, cols):
        """Critical value of the largest |t| over cols, the observed largest |t|, its p and the verdict."""
        if B < 2 or not cols.any() or not (se[key][cols] > 0).all():
            return None
        x, e, s = draws[key][:, cols], est[key][0, cols], se[key][cols]
        tmax = np.abs((x[~np.isnan(x).any(1)] - e) / s).max(1)
        critical, observed = float(np.quantile(tmax, level)), float(np.abs(e / s).max())
        return {"critical": critical, "max_abs_t": observed, "reject": observed > critical,
                "p": float((1 + np.sum(tmax >= observed)) / (1 + len(tmax)))}

    bands, rows = {"pre": sup_t("event", events <= -2), "post": sup_t("event", events >= 0)}, []
    for j, e in enumerate(events):
        row, band = {"e": int(e), **summary("event", j)}, bands["pre" if e < 0 else "post"]
        row["cohorts"] = int(len(set(G_[in_event & (E_ == e)])))
        if band and row["se"] is not None:
            row.update(band_low=row["estimate"] - band["critical"] * row["se"],
                       band_high=row["estimate"] + band["critical"] * row["se"])
        rows.append(row)
    return {"estimator": "callaway_santanna", "control_group": control, "base_period": "g - 1 for every t",
            "level": level, "B": B, "seed": seed, "cluster": cluster, "G": n_clusters,
            "cohorts": {str(_num(c)): int((gv == c).sum()) for c in cohorts},
            "never_treated": int(np.isnan(gv).sum()), "dropped_always_treated": int((~keep).sum()),
            "cells_without_controls": missing,
            "overall": {**summary("overall", 0), "treated_unit_periods": int(TM[:, post].sum())},
            "group": {"overall": summary("group", 0),
                      "by_cohort": [{"cohort": _num(c), **summary("by_cohort", j)} for j, c in enumerate(with_post)]},
            "event": sorted(rows + [{"e": -1, "estimate": 0.0, "se": 0.0, "reference": True}], key=lambda r: r["e"]),
            "event_average": {**summary("event_average", 0), "event_times": [int(e) for e in events if e >= 0]},
            "att_gt": [{"g": _num(G_[j]), "t": _num(T_[j]), "e": int(E_[j]), **summary("att", j),
                        "n_treated": int(TM[:, j].sum()), "n_control": int(CM[:, j].sum())} for j in range(len(cells))],
            "sup_t": bands, "pretrend": bands["pre"],
            "pretrend_by_cohort": {str(_num(c)): sup_t("att", (G_ == c) & (E_ <= -2)) for c in cohorts},
            "bootstrap_failed_draws": int(np.isnan(draws["att"]).any(1).sum())}


def relative_magnitude(estimate, se, pre, *, Ms=(0.5, 1, 2), level=0.95):
    """Post-treatment bias at most M times the largest pre-period deviation D = max |pre| (pre: the
    pre-period event-study estimates, base left out): the interval estimate -/+ (z se + M D) per M and
    the breakdown M, the smallest M whose interval holds 0 (None when D is 0). Below 1: fragile.
    Labelled SENSITIVITY_LABEL: a simplified version, not the Rambachan-Roth confidence set."""
    half = _z(level) * float(se)
    D = max((abs(float(v)) for v in pre), default=0.0)
    breakdown = None if D == 0 else max(0.0, (abs(float(estimate)) - half) / D)
    return {"label": SENSITIVITY_LABEL, "estimate": float(estimate), "se": float(se), "level": level,
            "largest_pre_deviation": D, "breakdown_M": breakdown, "fragile": breakdown is not None and breakdown < 1,
            "rows": [{"M": M, "low": estimate - half - M * D, "high": estimate + half + M * D} for M in Ms]}


def _iv_data(df, outcome, treatment, instruments, covariates, cluster):
    covariates = list(covariates)
    d = df[list(dict.fromkeys([outcome, treatment, *instruments, *covariates] + ([cluster] if cluster else [])))].dropna()
    W = np.column_stack([np.ones(len(d))] + [d[c].to_numpy(float) for c in covariates])
    return (d[outcome].to_numpy(float), d[treatment].to_numpy(float), d[list(instruments)].to_numpy(float), W,
            d[cluster].to_numpy() if cluster else None)


def iv_2sls(df, *, outcome, treatment, instruments, covariates=(), cluster=None, level=0.95):
    """2SLS in one step with CR1 (HC1) errors; the first stage with the robust F on the excluded
    instruments (Wald / k; with one instrument it equals the effective F of Montiel Olea and Pflueger
    2013); the reduced form; and OLS of the outcome on the treatment for the table beside it."""
    _need()
    y, d, Z, W, groups = _iv_data(df, outcome, treatment, instruments, covariates, cluster)
    k, names = Z.shape[1], list(instruments)
    ZW, X = np.column_stack([Z, W]), np.column_stack([d, W])
    (pi, Vpi, dof), (rf, Vrf, _), (ols, Vols, _) = _ols(d, ZW, groups), _ols(y, ZW, groups), _ols(y, X, groups)
    Xhat = ZW @ np.linalg.lstsq(ZW, X, rcond=None)[0]
    bread = np.linalg.inv(Xhat.T @ Xhat)
    beta = bread @ Xhat.T @ y
    V, _ = _sandwich(Xhat, y - X @ beta, bread, groups)

    def coefs(b, V_):
        return {"coef": {z: float(b[i]) for i, z in enumerate(names)},
                "se": {z: math.sqrt(V_[i, i]) for i, z in enumerate(names)}}

    return {"estimator": "2sls", **_row(beta[0], math.sqrt(V[0, 0]), dof, level), "n": len(y), "level": level,
            "G": None if dof is None else dof + 1, "errors": f"CR1 by {cluster}" if cluster else "HC1",
            "first_stage": {**coefs(pi, Vpi), "F": float(pi[:k] @ np.linalg.solve(Vpi[:k, :k], pi[:k]) / k),
                            "df": [k, dof]},
            "reduced_form": coefs(rf, Vrf), "ols": _row(ols[0], math.sqrt(Vols[0, 0]), dof, level)}


def anderson_rubin(df, *, outcome, treatment, instruments, covariates=(), cluster=None, level=0.95,
                   grid=None, points=2001):
    """The Anderson-Rubin set (Anderson and Rubin 1949): the b at which a CR1 (HC1) Wald test that
    the instruments do not enter the regression of outcome - b * treatment is not rejected. Default
    grid: 2SLS +/- 20 SE. A set touching a grid edge is unbounded there (one instrument: when the
    first-stage F is below the critical value, 3.84 at 95%)."""
    _need()
    from scipy import stats
    y, d, Z, W, groups = _iv_data(df, outcome, treatment, instruments, covariates, cluster)
    k, ZW = Z.shape[1], np.column_stack([Z, W])
    if np.linalg.matrix_rank(ZW) < ZW.shape[1]:
        raise ValueError("the instruments and covariates are collinear")
    if grid is None:
        fit = iv_2sls(df, outcome=outcome, treatment=treatment, instruments=instruments, covariates=covariates,
                      cluster=cluster, level=level)
        grid = (fit["estimate"] - 20 * fit["se"], fit["estimate"] + 20 * fit["se"])
    bs, bread = np.linspace(grid[0], grid[1], points), np.linalg.inv(ZW.T @ ZW)
    gy, gd = bread @ ZW.T @ y, bread @ ZW.T @ d
    wald, dof = np.empty(points), None
    for i, b in enumerate(bs):
        V, dof = _sandwich(ZW, (y - ZW @ gy) - b * (d - ZW @ gd), bread, groups)
        gz = (gy - b * gd)[:k]
        wald[i] = gz @ np.linalg.solve(V[:k, :k], gz) / k
    critical = float(stats.f.ppf(level, k, dof) if dof else stats.chi2.ppf(level, k) / k)
    accept = wald <= critical
    edges = np.flatnonzero(np.diff(np.concatenate([[0], accept.astype(int), [0]])))
    return {"set": [[float(bs[a]), float(bs[b - 1])] for a, b in zip(edges[::2], edges[1::2])],
            "bounded": not (accept[0] or accept[-1]), "empty": not accept.any(), "level": level,
            "critical": critical, "grid": [float(bs[0]), float(bs[-1]), points]}


def ri_pvalue(assignment, statistic, *, B, seed, clusters=None, strata=None):
    """Two-sided randomization-inference p, (1 + #{|T*| >= |T|}) / (B + 1), never below 1/(B + 1).
    statistic(a) gives the statistic for an assignment a (0/1 per row); clusters are permuted whole
    (treatment constant within each), only within strata when strata are given."""
    _need()
    if B < 1:
        raise ValueError("B must be a positive number of permutations")
    a = np.asarray(assignment)
    codes, G = _codes(clusters if clusters is not None else np.arange(len(a)))
    per = pd.DataFrame({"c": codes, "a": a, "s": 0 if strata is None else _codes(strata)[0]}).groupby("c")
    if (per["a"].nunique() > 1).any():
        raise ValueError("treatment is not constant within clusters: permute at the level it was assigned")
    if (per["s"].nunique() > 1).any():
        raise ValueError("a cluster lies in several strata")
    ca, cs = per["a"].first().to_numpy(), per["s"].first().to_numpy()
    rng, observed, draws = np.random.default_rng(seed), float(statistic(a)), np.empty(B)
    for b in range(B):
        perm = ca.copy()
        for s in np.unique(cs):
            perm[cs == s] = rng.permutation(ca[cs == s])
        draws[b] = statistic(perm[codes])
    hits = int(np.sum(np.abs(draws) >= abs(observed) - 1e-12 * max(1.0, abs(observed))))
    return {"statistic": observed, "p": (1 + hits) / (B + 1), "B": B, "min_p": 1 / (B + 1), "seed": seed,
            "permuted": "clusters" if clusters is not None else "units", "clusters": G,
            "strata": int(len(np.unique(cs)))}


def synth_weights(treated_pre, donors_pre):
    """Non-negative donor weights summing to one that best reproduce the treated unit's pre-period
    outcomes from the donors' (the columns of donors_pre), by least squares."""
    _need()
    from scipy.optimize import minimize
    y, X = np.asarray(treated_pre, float), np.asarray(donors_pre, float)
    J, s = X.shape[1], max(float(np.abs(y).mean()), 1e-12)
    if J < 2:
        raise ValueError("a synthetic control needs at least two donors")
    res = minimize(lambda w: float(np.sum(((y - X @ w) / s) ** 2)), np.full(J, 1 / J),
                   jac=lambda w: -2 * X.T @ (y - X @ w) / s ** 2, method="SLSQP", bounds=[(0, 1)] * J,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1, "jac": lambda w: np.ones(J)}],
                   options={"maxiter": 1000, "ftol": 1e-12})
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def sc_placebos(wide, *, treated, T0):
    """A synthetic control (Abadie, Diamond and Hainmueller 2010) and its in-space placebos, each
    donor in turn treated as if treated, the others as its pool. wide: a row per period in time order,
    a column per unit; T0: pre-periods. p = rank of the treated post/pre RMSPE ratio among J + 1 over
    J + 1, never below 1/(J + 1); pre_fit_rank ranks its pre-period RMSPE (1 = best fit)."""
    _need()
    Y, units = wide.to_numpy(float), list(wide.columns)
    if np.isnan(Y).any() or treated not in units or not 2 <= T0 < len(Y):
        raise ValueError("sc_placebos needs every unit in every period, the treated column, two or more "
                         "pre-periods and one or more post-periods")
    donors = [u for u in units if u != treated]
    if len(donors) < 3:
        raise ValueError("in-space placebos need at least three donors")

    def fit(target, pool):
        i, idx = units.index(target), [units.index(u) for u in pool]
        w = synth_weights(Y[:T0, i], Y[:T0, idx])
        gap = Y[:, i] - Y[:, idx] @ w
        pre, post = math.sqrt(np.mean(gap[:T0] ** 2)), math.sqrt(np.mean(gap[T0:] ** 2))
        return w, gap, pre, post, post / pre if pre > 0 else math.inf

    w, gap, pre, post, ratio = fit(treated, donors)
    placebos = [dict(zip(("unit", "pre_rmspe", "post_rmspe", "ratio"), (u, *fit(u, [v for v in donors if v != u])[2:])))
                for u in donors]
    rank, J = 1 + sum(p["ratio"] >= ratio for p in placebos), len(donors)
    for p in placebos:
        p["ratio"] = None if math.isinf(p["ratio"]) else p["ratio"]
    return {"weights": {u: float(x) for u, x in zip(donors, w)}, "gap": [float(x) for x in gap],
            "pre_rmspe": pre, "post_rmspe": post, "ratio": None if math.isinf(ratio) else ratio, "J": J,
            "rank": rank, "p": rank / (J + 1), "min_p": 1 / (J + 1),
            "pre_fit_rank": 1 + sum(p["pre_rmspe"] < pre for p in placebos), "placebos": placebos}


def _ipw_once(D, Y, X, estimand, trim, doubly_robust):
    import statsmodels.api as sm
    Xc = np.column_stack([np.ones(len(D)), X])
    try:
        e = sm.Logit(D, Xc).fit(disp=0).predict(Xc)
    except Exception as exc:  # perfect separation and the like
        raise ValueError(f"the propensity model did not fit ({type(exc).__name__}): a covariate may predict "
                         "treatment perfectly, so the groups do not overlap") from exc
    keep = np.ones(len(D), bool) if trim is None else (e >= trim[0]) & (e <= trim[1])
    t, c = keep & (D == 1), keep & (D == 0)
    if not t.any() or not c.any():
        raise ValueError("no treated or no control unit is left after trimming")
    with np.errstate(divide="ignore"):
        w = np.where(D == 1, 1.0 if estimand == "ATT" else 1 / e, e / (1 - e) if estimand == "ATT" else 1 / (1 - e))
    wt, wc = w[t] / w[t].sum(), w[c] / w[c].sum()
    if not doubly_robust:
        return float(wt @ Y[t] - wc @ Y[c]), e, keep, w
    mu0 = Xc @ np.linalg.lstsq(Xc[c], Y[c], rcond=None)[0]
    if estimand == "ATT":
        return float(np.mean(Y[t] - mu0[t]) - wc @ (Y[c] - mu0[c])), e, keep, w
    mu1 = Xc @ np.linalg.lstsq(Xc[t], Y[t], rcond=None)[0]
    return float(np.mean((mu1 - mu0)[keep]) + wt @ (Y[t] - mu1[t]) - wc @ (Y[c] - mu0[c])), e, keep, w


def ipw(df, *, treatment, outcome, covariates, estimand="ATT", trim=(0.1, 0.9), doubly_robust=False, B=0,
        seed=None, level=0.95):
    """Propensity-score weighting (logit score on pre-treatment covariates) with overlap in numbers.

    trim=(low, high) drops units scored outside the range (None keeps all), never clips scores; the
    estimand moves to the units kept, so ate_allowed is False when more than half are dropped.
    Weights are normalised within group; doubly_robust adds a linear outcome model (AIPW); B > 0 gives
    a bootstrap SE refitting the score. Balance: standardised differences over the unweighted pooled SD.
    """
    _need()
    if estimand not in ("ATT", "ATE"):
        raise ValueError("estimand must be 'ATT' or 'ATE'")
    if B and seed is None:
        raise ValueError("pass seed= with B so that the bootstrap gives the same numbers on every run")
    covariates = list(covariates)
    d = df[list(dict.fromkeys([treatment, outcome, *covariates]))].dropna()
    if not d[treatment].isin([0, 1]).all():
        raise ValueError(f"{treatment} must be 0 or 1")
    D, Y, X = d[treatment].to_numpy(int), d[outcome].to_numpy(float), d[covariates].to_numpy(float)
    est, e, keep, w = _ipw_once(D, Y, X, estimand, trim, doubly_robust)
    draws, failed, rng = [], 0, np.random.default_rng(seed)
    for _ in range(B):
        idx = rng.integers(0, len(D), len(D))
        try:
            draws.append(_ipw_once(D[idx], Y[idx], X[idx], estimand, trim, doubly_robust)[0])
        except ValueError:
            failed += 1
    se = float(np.std(draws, ddof=1)) if len(draws) > 1 else None
    t, c, n, kept = keep & (D == 1), keep & (D == 0), len(D), int(keep.sum())
    sd = np.sqrt((X[D == 1].var(0, ddof=1) + X[D == 0].var(0, ddof=1)) / 2)
    with np.errstate(invalid="ignore", divide="ignore"):
        smd = zip(covariates, (X[D == 1].mean(0) - X[D == 0].mean(0)) / sd,
                  (w[t] @ X[t] / w[t].sum() - w[c] @ X[c] / w[c].sum()) / sd)
    balance = [{"covariate": name, "smd_before": None if math.isnan(b) else float(b),
                "smd_after": None if math.isnan(a) else float(a)} for name, b, a in smd]
    lo, hi = {g: float(e[D == g].min()) for g in (0, 1)}, {g: float(e[D == g].max()) for g in (0, 1)}
    inside = {g: float(np.mean((e[D == g] >= lo[1 - g]) & (e[D == g] <= hi[1 - g]))) for g in (0, 1)}
    after = [abs(row["smd_after"]) for row in balance if row["smd_after"] is not None]
    return {"estimator": "aipw" if doubly_robust else "ipw", "estimand": estimand, "estimate": est, "se": se,
            "low": None if se is None else est - _z(level) * se, "high": None if se is None else est + _z(level) * se,
            "level": level, "population": "all units" if kept == n else f"units with scores in [{trim[0]}, {trim[1]}]",
            "n": {"before": n, "after": kept, "treated": int(t.sum()), "control": int(c.sum())},
            "trimming": {"method": "drop", "range": None if trim is None else list(trim), "dropped": n - kept,
                         "trimmed_share": (n - kept) / n},
            "ate_allowed": estimand == "ATT" or (n - kept) / n <= 0.5,
            "overlap": {"treated_scores": [lo[1], hi[1]], "control_scores": [lo[0], hi[0]],
                        "controls_in_treated_range": inside[0], "treated_in_control_range": inside[1]},
            "balance": balance, "max_abs_smd_after": max(after) if after else None,
            "max_weight_share": {"treated": float(w[t].max() / w[t].sum()), "control": float(w[c].max() / w[c].sum())},
            "B": B, "seed": seed, "bootstrap_failed_draws": failed}


def spec(*, design, estimator, headline=False, label=None, estimand=None, control_group=None, cluster=None,
         diagnostics=None, permutation=None, null=0.0, **record):
    """Record one specification, kept or dropped: rz_results.record(**record) with the causal fields
    checked and kept in extra["causal"], so that ledger.jsonl holds every specification run (the
    specification ledger check_causal.py reads). role defaults to primary for the headline, else
    secondary; effect_size to "estimate". Fields: cluster {"level", "basis", "G", "G_treated"};
    diagnostics {name: {"status": pass | fail | not_checked, "reason", "value", ...}}; permutation
    {"B", "p"}; null, the no-effect value."""
    rz = sys.modules.get("rz_results") or importlib.import_module("rz_results")

    def refuse(message):
        raise ValueError(f"causal_tools.spec({record.get('id')!r}): {message}")

    if not all(isinstance(v, str) and v.strip() for v in (design, estimator)):
        refuse("design and estimator are names, such as 'staggered_did' and 'callaway_santanna'")
    if headline and not record.get("kept", True):
        refuse("a headline is kept: drop another specification, or make this one not the headline")
    for key, entry in (diagnostics or {}).items():
        if not (isinstance(entry, dict) and entry.get("status") in STATUSES):
            refuse(f"diagnostic {key!r} needs a status: pass, fail or not_checked")
        if entry["status"] == "not_checked" and not str(entry.get("reason") or "").strip():
            refuse(f"diagnostic {key!r} is not_checked without a reason")
    if cluster is not None and not (isinstance(cluster, dict) and str(cluster.get("level") or "").strip()
                                    and isinstance(cluster.get("G"), numbers.Integral) and cluster["G"] > 0):
        refuse("cluster must be {'level', 'basis', 'G', 'G_treated'} with G a whole number of clusters")
    if permutation is not None and not (isinstance(permutation, dict) and isinstance(permutation.get("B"), numbers.Integral)
                                        and isinstance(permutation.get("p"), numbers.Real)):
        refuse("permutation must be {'B': number of draws, 'p': p-value}")
    record.setdefault("role", "primary" if headline else "secondary")
    if "effect_size" not in record and "no_effect_size" not in record:
        record["effect_size"] = "estimate"
    causal = {"design": design, "estimator": estimator, "headline": bool(headline), "label": label or record.get("id"),
              "estimand": estimand, "control_group": control_group, "cluster": cluster,
              "diagnostics": diagnostics or {}, "permutation": permutation, "null": null}
    return rz.record(extra={**(record.pop("extra", None) or {}), "causal": causal}, **record)


def simulate_staggered(*, cohorts=None, never=15, periods=range(2010, 2022), slope=0.5, pretrend=None, noise=0.3,
                       seed=1):
    """A balanced panel with a known ATT: (frame of unit, period, cohort, treated, effect, y; true ATT).
    The effect is slope * (e + 1) in event time e >= 0; cohorts maps adoption periods to unit counts
    (default 15 each in 2014, 2016, 2018), `never` units are never treated; pretrend={cohort: (start,
    rise)} adds rise per period from start until adoption. True ATT: mean over treated unit-periods."""
    _need()
    cohorts = cohorts or {2014: 15, 2016: 15, 2018: 15}
    periods = np.array(list(periods), float)
    g = np.concatenate([np.full(n, float(c)) for c, n in cohorts.items()] + [np.full(never, np.nan)])
    rng = np.random.default_rng(seed)
    G, P = np.meshgrid(g, periods, indexing="ij")
    treated = ~np.isnan(G) & (P >= G)
    effect, trend = np.where(treated, slope * (P - G + 1), 0.0), np.zeros(G.shape)
    for c, (start, rise) in (pretrend or {}).items():
        trend[g == c] = rise * np.clip(np.minimum(P[g == c], c - 1) - start + 1, 0, None)
    y = rng.normal(0, 1, (len(g), 1)) + 0.05 * (P - periods[0]) + trend + effect + rng.normal(0, noise, G.shape)
    frame = pd.DataFrame({"unit": np.repeat(np.arange(len(g)), len(periods)), "period": P.ravel().astype(int),
                          "cohort": G.ravel(), "treated": treated.ravel().astype(int), "effect": effect.ravel(),
                          "y": y.ravel()})
    return frame, float(effect[treated].mean())
