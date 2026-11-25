"""The DA-1 task of the design, simulated with a fixed seed (standard library only, so that every test can use it).

640 nodules from 450 patients, 190 of them with two nodules; columns patient_id, nodule_id, site, scan_date,
biomarker, clinical_score, eight predictors, biopsy (the reference standard, 1 = malignant) and split, which
the user assigned by patient. Planted, as the design lists them:

  1. 31 patients have one nodule in development and one in test;
  8. in the test split, 14% of the nodules whose biomarker is below the planned cut-off have no biopsy;
  10. two nodules per patient.

The user's model.py (problem 2: a scaler and a univariate filter fitted on all rows before the split) and a
case-control file with 50% cases (problem 7) are built here too. The remaining problems sit in results and
draft text, which each test writes for itself.
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

SEED = 20261118
PATIENTS, WITH_TWO, CROSSING, DEVELOPMENT = 450, 190, 31, 270
CUTOFF = 2.5                         # the cut-off the user's plan fixes for the biomarker
UNVERIFIED = 0.14                    # share of index-negative test nodules without a biopsy
PREDICTORS = ["age", "size_mm", "spiculated", "upper_lobe", "pack_years", "emphysema", "family_history",
              "nodule_count"]
COLUMNS = ["patient_id", "nodule_id", "site", "scan_date", "biomarker", "clinical_score", *PREDICTORS, "biopsy",
           "split"]

MODEL_PY = '''"""The user's model script, as received."""
import pandas as pd
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

PREDICTORS = ["age", "size_mm", "spiculated", "upper_lobe", "pack_years", "emphysema", "family_history", "nodule_count"]
df = pd.read_csv("nodules.csv").dropna(subset=["biopsy"])
X = StandardScaler().fit_transform(df[PREDICTORS])
selector = SelectKBest(f_classif, k=4)
X = selector.fit_transform(X, df["biopsy"])
dev = (df["split"] == "development").to_numpy()
model = LogisticRegression().fit(X[dev], df["biopsy"][dev])
print(model.coef_)
'''


def _expit(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def rows(seed: int = SEED) -> list:
    """The 640 rows as dicts, with the planted problems."""
    rng = random.Random(seed)
    two = sorted(rng.sample(range(PATIENTS), WITH_TWO))
    crossing = set(rng.sample([p for p in two if p < DEVELOPMENT], CROSSING))
    out = []
    for p in range(PATIENTS):
        age, pack, emph, fam = round(rng.gauss(64, 9)), round(max(0.0, rng.gauss(25, 15)), 1), int(rng.random() < 0.3), \
            int(rng.random() < 0.15)
        site, count = rng.choice("ABC"), 2 if p in two else 1
        for k in range(count):
            size, spic, upper = round(math.exp(rng.gauss(2.1, 0.45)), 1), int(rng.random() < 0.25), int(rng.random() < 0.55)
            risk = -3.4 + 0.03 * (age - 64) + 0.15 * (size - 8) + 1.3 * spic + 0.5 * upper + 0.015 * pack + 0.4 * emph \
                + 0.3 * fam
            biopsy = int(rng.random() < _expit(risk))
            day = rng.randrange(0, 4 * 365)
            out.append({"patient_id": f"P{p + 1:04d}", "nodule_id": f"N{p + 1:04d}-{k + 1}", "site": site,
                        "scan_date": f"{2019 + day // 365}-{1 + (day % 365) // 31:02d}-{1 + (day % 365) % 28:02d}",
                        "biomarker": round(1.7 + 1.2 * biopsy + 0.05 * size + rng.gauss(0, 0.75), 2),
                        "clinical_score": round(2.0 + 1.1 * biopsy + rng.gauss(0, 1.3), 1),
                        "age": age, "size_mm": size, "spiculated": spic, "upper_lobe": upper, "pack_years": pack,
                        "emphysema": emph, "family_history": fam, "nodule_count": count, "biopsy": biopsy,
                        "split": "development" if p < DEVELOPMENT and not (p in crossing and k == 1) else "test"})
    negative = [r for r in out if r["split"] == "test" and r["biomarker"] < CUTOFF]
    for r in rng.sample(negative, round(UNVERIFIED * len(negative))):
        r["biopsy"] = ""
    return out


def write(folder: Path, name: str = "nodules.csv", table=None) -> Path:
    path = Path(folder) / name
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows() if table is None else table)
    return path


def case_control(folder: Path, seed: int = SEED + 1) -> Path:
    """Problem 7: a case-control sample, 120 cases and 120 controls, biomarker and biopsy only."""
    rng, path = random.Random(seed), Path(folder) / "case_control.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["patient_id", "biomarker", "biopsy"])
        for i in range(240):
            case = int(i < 120)
            writer.writerow([f"C{i + 1:04d}", round(1.7 + 1.2 * case + 0.4 + rng.gauss(0, 0.75), 2), case])
    return path
