#!/usr/bin/env python3
"""The result file and the ledger of a statistical analysis.

Import this module from the analysis script; it has no commands of its own.

    import sys
    sys.path.insert(0, "<the scripts folder of this skill>")
    import rz_results as rz

    rz.record(id="latency_drug_vs_placebo", question="Does the drug shorten sleep latency?",
              family="primary", role="primary", test="paired t test", unit="subject", n={"pairs": 12},
              estimate={"name": "mean difference, drug minus placebo", "value": diff, "units": "min"},
              interval={"low": low, "high": high, "level": 0.95},
              statistic={"name": "t", "value": t}, df=11, p=p,
              effect_size={"name": "d_z", "value": dz, "low": dz_low, "high": dz_high, "level": 0.95},
              descriptives={"drug": {"mean": m1, "sd": s1}, "placebo": {"mean": m2, "sd": s2}})
    rz.record(..., kept=False, reason="sensitivity analysis without subject 7; not reported")
    rz.correct("pairwise", method="holm")
    rz.finish(script=__file__, data=["data/trial.csv"], seed=SEED)

  record()    one analysis. A kept one goes into statistics/results.json; every one, kept or
              dropped, gets a line in statistics/ledger.jsonl with its p, estimate, interval, n
              and extra fields, so a dropped analysis keeps its numbers. It raises ValueError
              when the unit is missing, when a p-value comes without an estimate and its
              interval, or when a p-value has neither an effect size nor no_effect_size="the
              reason". An effect size
              is {"name", "value", "low", "high", "level"}, or {..., "no_interval": "the reason"},
              or the string "estimate" when the estimate is itself the effect size (r, a risk
              difference, an odds ratio). descriptives holds the other numbers the text will
              print (group means, SDs, counts). extra holds the other fields a kind of analysis
              records (a meta-analysis's heterogeneity, a causal design's diagnostics).
  adjust(pvalues, method)   adjusted p-values in the order given: bonferroni, holm, bh
              (Benjamini-Hochberg) or by (Benjamini-Yekutieli).
  correct(family, method)   adjusts every p-value recorded in the family in this run, kept and
              dropped, and stores p_adjusted. For a procedure that adjusts by itself (Tukey,
              Dunnett) pass adjusted={id: p}. Call it after the family's last record().
  finish()    stores the SHA-256 of the script and of each data file, the Python and package
              versions, the seed and settings (alpha, resamples: numbers the Methods text prints),
              and prints a JSON summary. check_results.py reports a run without it as unfinished.

The first record() of a process starts a new run: results.json starts empty, the ledger is only
ever appended to. Set rz.OUT before the first record() to write somewhere other than statistics/.

Standard library only. Portions are derived from MIT-licensed code: see LICENSE-MIT.txt next to
this file and THIRD_PARTY_NOTICES.md in the plugin.
"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

__version__ = "1.0.0"

OUT = "statistics"
ROLES = ("primary", "secondary", "exploratory")
METHODS = {"bonferroni": "bonferroni", "holm": "holm", "bh": "bh", "fdr_bh": "bh", "benjamini-hochberg": "bh",
           "by": "by", "fdr_by": "by", "benjamini-yekutieli": "by"}
PACKAGES = ("numpy", "scipy", "pandas", "statsmodels")
NOT_A_UNIT = frozenset({"row", "rows", "observation", "observations", "measurement", "measurements"})

_state = {"run": None, "results": [], "tests": [], "families": {}, "finished": False}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _plain(value):
    """numpy scalars and arrays as plain Python, so that the files are ordinary JSON."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "tolist"):
        return _plain(value.tolist())
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    return str(value)


def _number(value) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isfinite(value)


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _ledger_path() -> Path:
    return Path(OUT) / "ledger.jsonl"


def _append(line: dict) -> None:
    with _ledger_path().open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"run": _state["run"], "time": _now(), **line}, ensure_ascii=False) + "\n")


def _save(record=None) -> None:
    content = {"tool": "researchzy-statistics", "schema_version": 1, "run": _state["run"],
               "results": _state["results"], "families": _state["families"]}
    if record:
        content["record"] = record
    (Path(OUT) / "results.json").write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _begin() -> None:
    if _state["finished"]:
        raise ValueError("rz_results: finish() was already called; record every analysis before it")
    if _state["run"] is None:
        Path(OUT).mkdir(parents=True, exist_ok=True)
        runs = [0]
        if _ledger_path().exists():
            for line in _ledger_path().read_text(encoding="utf-8").splitlines():
                if line.strip():
                    runs.append(int(json.loads(line).get("run", 0)))
        _state["run"] = max(runs) + 1


def adjust(pvalues, method: str) -> list:
    """Adjusted p-values, in the order given."""
    key = METHODS.get(str(method).lower())
    if key is None:
        raise ValueError(f"rz_results.adjust: unknown method {method!r}; use bonferroni, holm, bh or by")
    p = [float(value) for value in pvalues]
    if any(not 0 <= value <= 1 for value in p):
        raise ValueError("rz_results.adjust: every p-value must lie between 0 and 1")
    m = len(p)
    if key == "bonferroni":
        return [min(1.0, value * m) for value in p]
    order = sorted(range(m), key=p.__getitem__)
    adjusted = [0.0] * m
    if key == "holm":                      # step down: the smallest p is multiplied by m, the next by m - 1
        running = 0.0
        for rank, index in enumerate(order):
            running = max(running, min(1.0, (m - rank) * p[index]))
            adjusted[index] = running
        return adjusted
    scale = m * (sum(1 / k for k in range(1, m + 1)) if key == "by" else 1.0)
    running = 1.0
    for rank in range(m - 1, -1, -1):      # step up: p times m over its rank, made monotone from the largest
        index = order[rank]
        running = min(running, scale * p[index] / (rank + 1))
        adjusted[index] = running
    return adjusted


def record(*, id, question, family, role, test, unit, n, estimate=None, interval=None, statistic=None, df=None,
           p=None, effect_size=None, no_effect_size=None, descriptives=None, notes="", extra=None, kept=True,
           reason=None) -> dict:
    """Record one analysis; see the module docstring for the fields and the refusals."""
    def refuse(message):
        raise ValueError(f"rz_results.record({id!r}): {message}")

    _begin()
    if not _text(id) or any(test_["id"] == id for test_ in _state["tests"]):
        refuse("the id is empty or was already recorded in this run")
    if family in _state["families"]:
        refuse(f"family {family!r} was already corrected: record every test of a family before correct()")
    for name, value in (("question", question), ("family", family), ("test", test)):
        if not _text(value):
            refuse(f"{name} is missing")
    if role not in ROLES:
        refuse(f"role must be one of {', '.join(ROLES)}")
    if not _text(unit) or unit.strip().lower() in NOT_A_UNIT:
        refuse("the unit of analysis is missing: name what one independent unit is (subject, animal, culture, run)")
    if p is not None and not (_number(p) and 0 <= p <= 1):
        refuse("p must be the exact p-value as a number between 0 and 1, or None when there is no test")
    if extra is not None and not isinstance(extra, dict):
        refuse("extra must be a dict of the other fields this kind of analysis records")
    if not kept:
        if not _text(reason):
            refuse("a dropped analysis needs reason='why it is not reported'")
    else:
        counts = list(n.values()) if isinstance(n, dict) else [n]
        if not counts or not all(isinstance(c, numbers.Integral) and not isinstance(c, bool) and c > 0 for c in counts):
            refuse("n must be a whole number of units, or a dict of them such as {'drug': 12, 'placebo': 11}")
        if not (isinstance(estimate, dict) and _text(estimate.get("name")) and _number(estimate.get("value"))
                and _text(estimate.get("units"))):
            refuse("estimate must be {'name', 'value', 'units'} (write 'unitless' for a ratio)"
                   + (": a p-value is not recorded without it" if p is not None else ""))
        has_interval = isinstance(interval, dict) and all(_number(interval.get(k)) for k in ("low", "high", "level"))
        if interval is not None and not (has_interval and interval["low"] <= interval["high"] and 0 < interval["level"] < 1):
            refuse("interval must be {'low', 'high', 'level'} with low <= high and a level such as 0.95")
        if p is not None and not has_interval:
            refuse("a p-value is not recorded without the interval of its estimate")
        if isinstance(effect_size, dict):
            bounds = all(_number(effect_size.get(k)) for k in ("low", "high"))
            if not (_text(effect_size.get("name")) and _number(effect_size.get("value"))):
                refuse("effect_size must have a name and a value")
            if not bounds and not _text(effect_size.get("no_interval")):
                refuse("effect_size needs low and high, or no_interval='the reason'")
        elif effect_size is not None and effect_size != "estimate":
            refuse("effect_size must be a dict, or the string 'estimate' when the estimate is the effect size")
        if p is not None and effect_size is None and not _text(no_effect_size):
            refuse("a p-value needs an effect size, or no_effect_size='why this result cannot have one'")

    entry = _plain({"id": id, "question": question, "family": family, "role": role, "test": test, "unit": unit,
                    "n": n, "estimate": estimate, "interval": interval, "statistic": statistic, "df": df, "p": p,
                    "effect_size": effect_size, "no_effect_size": no_effect_size, "descriptives": descriptives,
                    "notes": notes})
    if extra is not None:
        entry["extra"] = _plain(extra)
    _state["tests"].append({"id": id, "family": family, "p": entry["p"], "kept": bool(kept)})
    if kept:
        _state["results"].append(entry)
    _append({"id": id, "family": family, "role": role, "test": test, "status": "kept" if kept else "dropped",
             "reason": reason, "p": entry["p"], "estimate": (entry["estimate"] or {}).get("value"),
             "interval": entry["interval"], "n": entry["n"], **({"extra": entry["extra"]} if "extra" in entry else {})})
    _save()
    return entry


def correct(family: str, method: str, adjusted=None) -> dict:
    """Adjust every p-value recorded in the family in this run, kept and dropped."""
    _begin()
    tests = [test for test in _state["tests"] if test["family"] == family and test["p"] is not None]
    if not tests:
        raise ValueError(f"rz_results.correct: no test with a p-value was recorded in family {family!r}")
    ids = [test["id"] for test in tests]
    if adjusted is None:
        values = adjust([test["p"] for test in tests], method)
        method, source = METHODS[str(method).lower()], "rz_results.adjust"
    else:
        adjusted = _plain(adjusted)
        if set(adjusted) != set(ids) or not all(_number(v) and 0 <= v <= 1 for v in adjusted.values()):
            raise ValueError(f"rz_results.correct: adjusted must give one p-value for each of {', '.join(ids)}")
        values, source = [adjusted[i] for i in ids], "the test procedure"
    entry = {"method": str(method), "m": len(ids), "ids": ids, "adjusted_by": source, "p_adjusted": dict(zip(ids, values))}
    _state["families"][family] = entry
    for result in _state["results"]:
        if result["id"] in entry["p_adjusted"]:
            result["p_adjusted"] = entry["p_adjusted"][result["id"]]
    _append({"event": "correct", "family": family, "method": entry["method"], "m": entry["m"], "ids": ids})
    _save()
    return entry


def _file_entry(path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"rz_results.finish: no such file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    try:
        shown = path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        shown = path.resolve().as_posix()
    return {"path": shown, "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def finish(script=None, data=(), seed=None, packages=(), settings=None) -> dict:
    """Bind the results to the script, the data files and the environment; print a summary."""
    _begin()
    script = script or getattr(sys.modules.get("__main__"), "__file__", None)
    if not script:
        raise ValueError("rz_results.finish: pass script=__file__")
    if isinstance(data, (str, Path)) or not list(data):
        raise ValueError("rz_results.finish: pass data=[...] with every data file the script read")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, numbers.Integral)):
        raise ValueError("rz_results.finish: seed must be the whole number given to the random generator, or None")
    versions = {"rz_results": __version__}
    for name in dict.fromkeys((*PACKAGES, *packages)):
        if name in sys.modules or name in packages:      # what the analysis script imported
            try:
                versions[name] = metadata.version(name)
            except metadata.PackageNotFoundError:
                versions[name] = getattr(sys.modules.get(name), "__version__", "unknown")
    families = sorted({test["family"] for test in _state["tests"] if test["p"] is not None})
    sizes = {name: sum(1 for test in _state["tests"] if test["family"] == name and test["p"] is not None)
             for name in families}
    bound = {"finished": _now(), "script": _file_entry(script), "data": [_file_entry(path) for path in data],
             "python": platform.python_version(), "packages": versions,
             "seed": None if seed is None else int(seed), "settings": _plain(settings or {})}
    dropped = sum(1 for test in _state["tests"] if not test["kept"])
    _append({"event": "finish", "kept": len(_state["results"]), "dropped": dropped,
             "script_sha256": bound["script"]["sha256"]})
    _save(bound)
    _state["finished"] = True
    summary = {"results_file": str(Path(OUT) / "results.json"), "run": _state["run"], "kept": len(_state["results"]),
               "dropped": dropped, "tests_per_family": sizes,
               "families_without_correction": [name for name in families
                                               if sizes[name] > 1 and name not in _state["families"]]}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    print(__doc__)
