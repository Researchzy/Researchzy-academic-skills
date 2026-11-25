"""rz_survival.py against an independent implementation, statsmodels' defaults made explicit, and the record fields.

The reference values below were computed once with lifelines 0.30.3 (pandas 2.3.3, numpy 2.5.3) in a separate
environment, never part of the skill, on the cohorts that cohort() generates here with the same seeds: KaplanMeierFitter
(estimate and its log(-log) band, median and its interval from the bands), logrank_test and multivariate_logrank_test,
CoxPHFitter (Efron ties; strata; entry_col), proportional_hazard_test, restricted_mean_survival_time and
AalenJohansenFitter. lifelines has no global proportional-hazards test or stratified log-rank test: the global value
applies the same formula to lifelines' own Schoenfeld residuals and covariance, and the stratified log-rank value comes
from the textbook sums of observed minus expected events and their variance over the strata. Tolerance: relative
1e-6 for the closed-form estimates, 1e-5 for the iterative fits and the tests built on them. With tied event times
statsmodels' Schoenfeld residuals use the full risk-set mean, so the test there is pinned within 0.1 of lifelines'.
"""
from __future__ import annotations

import importlib.util
import io
import json
import math
import os
import random
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"


def available(*names) -> bool:
    return all(importlib.util.find_spec(name) is not None for name in names)


def load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rs = load("rz_survival", "rz_survival_under_test")
HAVE = available("numpy", "pandas", "scipy", "statsmodels")
NEEDS = unittest.skipUnless(HAVE, "numpy, pandas, scipy or statsmodels is not installed")
FIGURES = unittest.skipUnless(HAVE and available("matplotlib"), "matplotlib is not installed")
if HAVE:
    import numpy as np
    import pandas as pd
    from statsmodels.duration.hazard_regression import PHReg


def cohort(seed, n=160, arms="AB", crossing=False, whole=False, entry=False, competing=False):
    """Rows (arm, age, marker, time, event, entry): exponential event times whose rate depends on arm, age and
    marker, or crossing hazards; uniform censoring from 5 to 45. random.random() keeps its stream across versions."""
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        arm = arms[i % len(arms)]
        age = round(45 + 30 * rnd.random(), 1)
        marker = int(rnd.random() < 0.4)
        e = -math.log(1 - rnd.random())
        if crossing:
            rate, late = (0.18, 0.018) if arm != arms[0] else (0.06, 0.06)
            t = e / rate if e <= rate * 8 else 8 + (e - rate * 8) / late
        else:
            t = e / (0.04 * math.exp(0.5 * arms.index(arm) + 0.03 * (age - 60) + 0.4 * marker))
        code = 1
        if competing:
            other = -math.log(1 - rnd.random()) / 0.02
            code, t = (1, t) if t <= other else (2, other)
        c = 5 + 40 * rnd.random()
        time, event = (t, code) if t <= c else (c, 0)
        start = 10 * rnd.random() if entry else 0.0
        if whole:
            time = float(math.ceil(time))
        if entry and time <= start:
            continue
        rows.append({"id": f"S{i + 1:03d}", "arm": arm, "age": age, "marker": marker, "time": round(time, 6),
                     "event": event, "entry": round(start, 6)})
    return rows


def prepared(rows, **options):
    options.setdefault("mapping", {"0": 0, "1": 1, "2": 2})
    return rs.prepare(pd.DataFrame(rows), time="time", event="event", time_unit="months", time_zero="randomisation",
                      **options)


def at(curve, t):
    """The Kaplan-Meier value of a km_table curve at time t: (S, low, high)."""
    i = int(np.searchsorted(curve["time"], t, side="right")) - 1
    return curve["surv"][i], curve["low"][i], curve["high"][i]


class Close(unittest.TestCase):
    def close(self, got, want, rel=1e-6):
        self.assertTrue(math.isclose(got, want, rel_tol=rel, abs_tol=rel * 1e-3), f"{got!r} is not {want!r}")


@NEEDS
class KaplanMeierTests(Close):
    def test_curve_band_and_median_match_lifelines(self):
        km = rs.km_table(prepared(cohort(20261118)), "arm", times=[0, 10, 20])
        reference = {"A": {5: (0.775, 0.6669299733617, 0.8518097399896083),
                           10: (0.5779691144420799, 0.4574181783351001, 0.6809459107685646),
                           20: (0.3512650107571631, 0.23830399164651522, 0.4661798416406134),
                           "median": (13.024195, 8.86867, 18.750012)},
                     "B": {5: (0.6875, 0.5736164995650086, 0.7767763511633011),
                           10: (0.45423424112607125, 0.33873674704145007, 0.5625543557856592),
                           20: (0.14322582315080123, 0.066319544445182, 0.24860795089997192),
                           "median": (9.052666, 6.572316, 11.488)}}
        for arm, values in reference.items():
            group = km["groups"][arm]
            for t in (5, 10, 20):
                for got, want in zip(at(group["_curve"], t), values[t]):
                    self.close(float(got), want)
            m = group["median"]
            for got, want in zip((m["estimate"], m["low"], m["high"]), values["median"]):
                self.close(got, want)
        self.assertEqual(km["groups"]["B"]["lowest"], 0.0)
        self.assertEqual((km["groups"]["A"]["n"], km["groups"]["A"]["events"] + km["groups"]["B"]["events"]), (80, 122))
        self.assertIn("log(-log)", km["band"])

    def test_number_at_risk_counts_times_at_or_after_t(self):
        rows = [{"time": t, "event": e, "arm": "A"} for t, e in ((2, 1), (4, 0), (4, 1), (6, 1), (8, 0))]
        km = rs.km_table(prepared(rows), "arm", times=[0, 4, 5, 8, 9])
        self.assertEqual(km["groups"]["A"]["at_risk"]["counts"], [5, 4, 2, 1, 0])     # an event at t is at risk at t
        late = prepared([dict(r, start=s) for r, s in zip(rows, (0, 1, 3, 4, 5))], entry="start")
        self.assertEqual(rs.km_table(late, "arm", times=[1, 4, 5])["groups"]["A"]["at_risk"]["counts"], [1, 2, 1])

    def test_a_median_that_is_not_reached(self):
        rows = [{"time": t, "event": int(t in (3, 9)), "arm": "A"} for t in range(1, 21)]
        m = rs.km_table(prepared(rows), "arm", times=[0])["groups"]["A"]
        self.assertEqual((m["median"]["estimate"], m["median"]["high"]), ("not_reached", "not_reached"))
        self.assertFalse(m["below_half"])
        self.assertGreater(m["lowest"], 0.5)

    def test_a_curve_that_sits_at_one_half(self):
        # Arm B of this cohort equals 0.5 over an interval: lifelines (first time <= 0.5) gave 4.154303;
        # statsmodels takes the first time below 0.5, and the record says so.
        km = rs.km_table(prepared(cohort(7, n=200, crossing=True)), "arm", times=[0])
        a, b = km["groups"]["A"]["median"], km["groups"]["B"]["median"]
        self.close(a["estimate"], 12.387587)
        self.close(a["low"], 9.947321)
        self.close(a["high"], 19.42352)
        self.assertGreater(b["estimate"], 4.154303)
        self.assertIn("equals 0.5", b["note"])

    def test_codes_one_and_two_are_mapped_never_used_as_weights(self):
        rows = cohort(20261118)
        plain = rs.km_table(prepared(rows), "arm", times=[0])["groups"]["A"]["median"]
        coded = [dict(r, event=r["event"] + 1) for r in rows]
        with self.assertRaises(ValueError) as caught:
            prepared(coded, mapping={"0": 0, "1": 1})
        self.assertIn("event code '2' is not in the mapping", str(caught.exception))
        mapped = rs.km_table(prepared(coded, mapping={"1": 0, "2": 1}), "arm", times=[0])["groups"]["A"]["median"]
        self.assertEqual(mapped, plain)

    def test_competing_events_need_cif(self):
        with self.assertRaises(ValueError) as caught:
            rs.km_table(prepared(cohort(91, n=150, competing=True)), "arm", times=[0])
        self.assertIn("Use cif()", str(caught.exception))


@NEEDS
class PrepareTests(unittest.TestCase):
    def test_bad_rows_are_named_and_drop_needs_reasons(self):
        rows = cohort(20261118, n=20)
        rows[3]["time"], rows[7]["time"], rows[9]["event"] = -2.0, "", 5
        with self.assertRaises(ValueError) as caught:
            prepared(rows)
        message = str(caught.exception)
        for part in ("event code '5' is not in the mapping (rows 10)", "time is negative (rows 4)",
                     "time is missing (rows 8)"):
            self.assertIn(part, message)
        data = prepared(rows, drop={4: "entry error (user)", 8: "no follow-up (user)", 10: "unknown code (user)"})
        self.assertEqual([e["row"] for e in data["context"]["excluded"]], [4, 8, 10])
        self.assertEqual(len(data["frame"]), 17)
        with self.assertRaises(ValueError):
            prepared(rows, drop={4: "", 8: "x", 10: "y"})
        with self.assertRaises(ValueError):
            prepared(rows, drop={99: "not a row"})
        with self.assertRaises(ValueError):
            rs.prepare(pd.DataFrame(rows), time="time", event="event", mapping={"0": 0, "1": 1}, time_unit="",
                       time_zero="randomisation")

    def test_repeated_ids_need_start_stop_rows_that_do_not_overlap(self):
        rows = cohort(20261118, n=12)
        twice = rows + [dict(rows[2])]
        with self.assertRaises(ValueError) as caught:
            prepared(twice, id="id")
        self.assertIn("the id repeats", str(caught.exception))
        spans = [{"id": "P1", "start": 0, "time": 5, "event": 0, "x": 0},
                 {"id": "P1", "start": 5, "time": 9, "event": 1, "x": 1},
                 {"id": "P2", "start": 0, "time": 7, "event": 1, "x": 0}]
        self.assertEqual(rs.prepare(pd.DataFrame(spans), time="time", event="event", mapping={"0": 0, "1": 1},
                                    time_unit="days", time_zero="diagnosis", id="id", entry="start")["context"]["id"], "id")
        spans[1]["start"] = 4
        with self.assertRaises(ValueError) as caught:
            rs.prepare(pd.DataFrame(spans), time="time", event="event", mapping={"0": 0, "1": 1}, time_unit="days",
                       time_zero="diagnosis", id="id", entry="start")
        self.assertIn("overlap", str(caught.exception))


@NEEDS
class LogrankTests(Close):
    def test_two_and_three_groups_and_ties(self):
        for seed, extra, want in ((20261118, {}, (7.8259612444233255, 0.005150104959337009)),
                                  (20261118, {"whole": True}, (7.674977779657212, 0.005599178284630802)),
                                  (31, {"n": 180, "arms": "ABC"}, (17.393521897112056, 0.0001671262658072272))):
            result = rs.logrank(prepared(cohort(seed, **extra)), "arm")
            self.close(result["statistic"], want[0])
            self.close(result["p"], want[1])
            self.assertEqual(result["df"], len(result["groups"]) - 1)
        self.assertIn("log-rank", result["weights"])

    def test_stratified(self):
        rows = [r for r in cohort(31, n=180, arms="ABC") if r["arm"] != "C"]
        self.close(rs.logrank(prepared(rows), "arm", strata="marker")["statistic"], 0.8028594255690022)
        with self.assertRaises(ValueError):
            rs.logrank(prepared(rows), "arm", weight_type="fh")                     # fh needs its exponent
        late = prepared(cohort(55, n=200, entry=True), entry="entry")
        with self.assertRaises(ValueError):
            rs.logrank(late, "arm", strata="marker")


@NEEDS
class CoxTests(Close):
    LIFELINES = {"arm[B]": (0.6448202638611746, 0.18917739983229034, 0.0006530957395291276, 1.3152665878694765,
                            2.7610226990291094),
                 "age": (0.022337377520988886, 0.010850301766101994, 0.039524211797584, 1.00107175075285,
                         1.0445681832052334),
                 "marker": (0.5780527032065489, 0.18786540816603703, 0.002091294971440767, 1.2334847198332966,
                            2.5760626720365662)}

    def test_efron_estimates_match_lifelines(self):
        fit = rs.cox(prepared(cohort(20261118)), ["arm", "age", "marker"], reference={"arm": "A"})
        for p in fit["parameters"]:
            for key, want in zip(("coef", "se", "p", "low", "high"), self.LIFELINES[p["name"]]):
                self.close(p[key], want, rel=1e-5)
        self.assertEqual((fit["ties"], fit["n"], fit["events"], fit["converged"]), ("efron", 160, 122, True))
        self.assertEqual(fit["parameters"][0]["reference"], "A")
        self.assertEqual(fit["events_per_parameter"], {"events": 122, "parameters": 3, "ratio": 40.67})

    def test_tied_times_use_efron_not_the_breslow_default(self):
        data = prepared(cohort(20261118, whole=True))
        fit = rs.cox(data, ["arm", "age", "marker"], reference={"arm": "A"})
        want = {"arm[B]": (0.6401580657505904, 0.18905084273579803), "age": (0.02184296947155847, 0.010851332755928589),
                "marker": (0.5843854244521052, 0.18767611916332355)}
        for p in fit["parameters"]:
            self.close(p["coef"], want[p["name"]][0], rel=1e-5)
            self.close(p["se"], want[p["name"]][1], rel=1e-5)
        frame = data["frame"]
        x = np.column_stack([(frame.arm == "B").astype(float), frame.age.astype(float), frame.marker.astype(float)])
        breslow = PHReg(frame["_time"].to_numpy(float), x, status=frame["_event"].to_numpy(float), ties="breslow").fit()
        self.assertGreater(abs(breslow.params[0] - fit["parameters"][0]["coef"]), 1e-3)

    def test_strata_and_entry_times_match_lifelines(self):
        rows = [r for r in cohort(31, n=180, arms="ABC") if r["arm"] != "C"]
        fit = rs.cox(prepared(rows), ["arm"], reference={"arm": "A"}, strata="marker")
        self.close(fit["parameters"][0]["coef"], 0.19433476066276528, rel=1e-5)
        self.close(fit["parameters"][0]["se"], 0.21721502904952386, rel=1e-5)
        late = prepared(cohort(55, n=200, entry=True), entry="entry")
        fit = rs.cox(late, ["arm", "age"], reference={"arm": "A"})
        self.assertEqual(fit["n"], 137)
        for p, coef, se in zip(fit["parameters"], (0.3194727139313419, 0.035756533697990936),
                               (0.2196527610950294, 0.012368946743468843)):
            self.close(p["coef"], coef, rel=1e-5)
            self.close(p["se"], se, rel=1e-5)
        km = rs.km_table(late, "arm", times=[0])
        for arm, values in (("A", (0.555219519026303, 0.3228447110914638, 0.1847044260571355)),
                            ("B", (0.5615033315864342, 0.24184926658897452, 0.1791476048807218))):
            for t, want in zip((10, 20, 30), values):
                self.close(float(at(km["groups"][arm]["_curve"], t)[0]), want)

    def test_an_entry_time_equal_to_an_event_time_counts_from_just_after(self):
        # Two rows enter at 5, when another row has its event. lifelines (entry_col) gave -0.9843495296101153: a row
        # is at risk when entry < t <= exit. PHReg given the raw entry times counts them at 5 as well.
        rows = [{"time": t, "start": s, "event": e, "x": x} for t, s, e, x in
                ((5, 0, 1, 1), (8, 0, 1, 0), (12, 5, 0, 1), (3, 0, 1, 0), (10, 2, 1, 1), (7, 0, 0, 0), (11, 5, 1, 1))]
        fit = rs.cox(prepared(rows, entry="start"), ["x"])
        self.close(fit["parameters"][0]["coef"], -0.9843495296101153, rel=1e-5)
        later = rs.cox(prepared([dict(r, start=r["start"] + 0.01 * (r["start"] > 0)) for r in rows], entry="start"), ["x"])
        self.close(fit["parameters"][0]["coef"], later["parameters"][0]["coef"], rel=1e-7)
        frame = pd.DataFrame(rows)
        same_time = PHReg(frame.time.to_numpy(float), frame[["x"]].to_numpy(float), status=frame.event.to_numpy(float),
                          entry=frame.start.to_numpy(float), ties="efron").fit()
        self.assertGreater(abs(same_time.params[0] - fit["parameters"][0]["coef"]), 1e-3)

    def test_missing_values_are_listed_and_levels_without_events_refused(self):
        rows = cohort(20261118)
        for i in (3, 20, 33, 47, 88, 120, 151):
            rows[i]["marker"] = ""
        fit = rs.cox(prepared(rows), ["arm", "age", "marker"], reference={"arm": "A"})
        self.assertEqual(fit["n"], 153)
        self.assertEqual([e["row"] for e in fit["excluded"]], [4, 21, 34, 48, 89, 121, 152])
        self.assertEqual({e["reason"] for e in fit["excluded"]}, {"missing marker"})
        self.assertIn("missing='raise'", fit["missing"])
        with self.assertRaises(ValueError) as caught:
            rs.cox(prepared([dict(r, arm="C") if r["event"] == 0 and r["arm"] == "A" else r for r in cohort(20261118)][:40] +
                            [{"arm": "C", "age": 50, "marker": 0, "time": 3.0, "event": 0}]),
                   ["arm"], reference={"arm": "A"})
        self.assertIn("arm = C has no events", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            rs.cox(prepared(cohort(20261118)), ["arm"])
        self.assertIn("reference={'arm': ...}", str(caught.exception))


@NEEDS
class ProportionalHazardsTests(Close):
    STATISTICS = {"km": {"arm[B]": 0.8996856718677178, "age": 0.17043179474326317, "marker": 0.0019356542630373794},
                  "rank": {"arm[B]": 0.7830184197227095, "age": 0.24162688977482843, "marker": 0.00028702101241635927},
                  "identity": {"arm[B]": 1.3883003242747405, "age": 0.0077080554971393715, "marker": 0.061069743170622255},
                  "log": {"arm[B]": 1.9416605385730328, "age": 0.009635638403142154, "marker": 0.7204075189660886}}
    GLOBAL = {"km": 1.2202551521254539, "rank": 1.173820941323042, "identity": 1.6176008001586464, "log": 2.5057220497392794}
    P = {"km": 0.342866008047185, "rank": 0.376219586556258, "identity": 0.2386923439607702, "log": 0.1634883488051748}

    def test_every_transform_matches_lifelines(self):
        fit = rs.cox(prepared(cohort(20261118)), ["arm", "age", "marker"], reference={"arm": "A"})
        for transform, statistics in self.STATISTICS.items():
            ph = rs.ph_test(fit, model="cox", transform=transform, plot=False)
            for p in ph["parameters"]:
                self.close(p["statistic"], statistics[p["name"]], rel=1e-5)
            self.close(ph["parameters"][0]["p"], self.P[transform], rel=1e-5)
            self.close(ph["global"]["statistic"], self.GLOBAL[transform], rel=1e-5)
            self.assertEqual((ph["global"]["df"], ph["events"], ph["model"], ph["plot"]), (3, 122, "cox", "not drawn"))
            self.assertNotIn("note", ph)

    def test_crossing_hazards_show_in_the_test(self):
        fit = rs.cox(prepared(cohort(7, n=200, crossing=True)), ["arm"], reference={"arm": "A"})
        self.close(fit["parameters"][0]["coef"], 0.5911551226215714, rel=1e-5)
        for transform, statistic, p in (("km", 15.213358287095165, 9.602177892608931e-05),
                                        ("rank", 13.699948489769648, 0.00021446036850271513)):
            ph = rs.ph_test(fit, model="cox", transform=transform, plot=False)
            self.close(ph["parameters"][0]["statistic"], statistic, rel=1e-5)
            self.close(ph["parameters"][0]["p"], p, rel=1e-5)
            self.close(ph["global"]["statistic"], statistic, rel=1e-5)          # one parameter: global = its test
        self.assertIn("1994 approximation", ph["method"])

    def test_tied_times_stay_close_and_say_why(self):
        fit = rs.cox(prepared(cohort(20261118, whole=True)), ["arm", "age", "marker"], reference={"arm": "A"})
        ph = rs.ph_test(fit, model="cox", transform="km", plot=False)
        lifelines = {"arm[B]": 0.9654343099115033, "age": 0.16519547604989807, "marker": 0.0036116211370544053}
        for p in ph["parameters"]:
            self.assertLess(abs(p["statistic"] - lifelines[p["name"]]), 0.1)
        self.assertLess(abs(ph["global"]["statistic"] - 1.2888856461043199), 0.1)
        self.assertIn("tied event times", ph["note"])
        with self.assertRaises(ValueError):
            rs.ph_test(fit, model="cox", transform="spline")
        with self.assertRaises(ValueError):
            rs.ph_test(fit, model="cox", plot=["arm[C]"])


@NEEDS
class RmstAndCifTests(Close):
    def test_rmst_matches_lifelines_and_a_hand_computation(self):
        result = rs.rmst(prepared(cohort(20261118)), "arm", tau=30, reference="A")
        self.close(result["groups"]["A"]["rmst"], 14.53233014323541)
        self.close(result["groups"]["B"]["rmst"], 10.596308306180354)
        self.close(result["differences"]["B"]["value"], 10.596308306180354 - 14.53233014323541)
        rows = [{"time": t, "event": e} for t, e in ((2, 1), (4, 0), (5, 1), (7, 1), (9, 0))]
        one = rs.rmst(prepared(rows), tau=8)["groups"]["all"]
        s = (0.8, 0.8 * 2 / 3, 0.8 * 2 / 3 * 1 / 2)                            # KM after the events at 2, 5 and 7
        area = 2 * 1 + 3 * s[0] + 2 * s[1] + 1 * s[2]
        rest = (3 * s[0] + 2 * s[1] + 1 * s[2], 2 * s[1] + 1 * s[2], 1 * s[2])  # area from each event time to tau
        variance = rest[0] ** 2 / (5 * 4) + rest[1] ** 2 / (3 * 2) + rest[2] ** 2 / (2 * 1)
        self.close(one["rmst"], area)
        self.close(one["se"], math.sqrt(variance))
        with self.assertRaises(ValueError) as caught:
            rs.rmst(prepared(rows), tau=10)
        self.assertIn("within every group's follow-up", str(caught.exception))

    def test_cumulative_incidence_matches_lifelines(self):
        result = rs.cif(prepared(cohort(91, n=150, competing=True)), times=[10, 20, 30])
        group = result["groups"]["all"]
        for point, want in zip(group["at"], (0.3971500071331739, 0.595459475950312, 0.6701189086025254)):
            self.close(point["cif"], want)
            self.assertLess(point["low"], point["cif"])
            self.assertGreater(point["high"], point["cif"])
        self.assertEqual(group["events"], {"1": 84, "2": 27})
        before = rs.cif(prepared(cohort(91, n=150, competing=True)), cause=2, times=[0])["groups"]["all"]["at"][0]
        self.assertEqual(before["cif"], 0.0)


class EventsTests(unittest.TestCase):
    def test_schoenfeld_formula(self):
        z = rs.NormalDist().inv_cdf
        out = rs.schoenfeld_events(0.7)
        self.assertAlmostEqual(out["events_exact"], (z(0.975) + z(0.8)) ** 2 / (0.25 * math.log(0.7) ** 2), places=9)
        self.assertEqual(out["events"], math.ceil(out["events_exact"]))
        unequal = rs.schoenfeld_events(0.7, allocation=2 / 3, power=0.9, sides=1)
        self.assertAlmostEqual(unequal["events_exact"], (z(0.95) + z(0.9)) ** 2 / (2 / 9 * math.log(0.7) ** 2), places=9)
        with self.assertRaises(ValueError):
            rs.schoenfeld_events(0.7, event_probability=0.4)                       # the probability needs its source
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "survival" / "power-events.json"
            done = rs.schoenfeld_events(0.7, event_probability=0.4, probability_source="user's registry, 2024", path=path)
            self.assertEqual(done["patients"], math.ceil(done["events"] / 0.4))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["patients"], done["patients"])
        for bad in ({"hr": 1.0}, {"hr": 0.7, "sides": 3}, {"hr": 0.7, "allocation": 1.0}):
            with self.assertRaises(ValueError):
                rs.schoenfeld_events(**bad)


@NEEDS
class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path("analysis.py").write_text("print('survival')\n", encoding="utf-8")
        Path("cohort.csv").write_text("time,event\n1,1\n", encoding="utf-8")

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_every_kind_records_through_rz_results_and_passes_check_survival(self):
        rz = load("rz_results", "rz_results_for_survival")
        rz.OUT = "survival"
        data = prepared(cohort(20261118))
        km = rs.km_table(data, "arm", times=[0, 10, 20, 30])
        for arm in km["groups"]:
            rz.record(id=f"km_{arm}", question="OS by arm", family="km", role="secondary", **rs.fields(km, group=arm))
        rz.record(id="logrank", question="OS by arm", family="logrank", role="secondary",
                  **rs.fields(rs.logrank(data, "arm")))
        fit = rs.cox(data, ["arm", "age"], reference={"arm": "A"})
        rz.record(id="cox", question="OS by arm", family="os", role="primary", **rs.fields(fit, parameter="arm[B]"))
        rz.record(id="cox_ph", question="PH of cox", family="ph", role="secondary",
                  **rs.fields(rs.ph_test(fit, model="cox", plot=False)))
        rz.record(id="rmst", question="RMST by arm", family="rmst", role="secondary",
                  **rs.fields(rs.rmst(data, "arm", tau=30, reference="A")))
        rz.record(id="cif", question="Incidence", family="cif", role="secondary",
                  **rs.fields(rs.cif(prepared(cohort(91, n=150, competing=True)), times=[10, 20])))
        with redirect_stdout(io.StringIO()):
            rz.finish(script="analysis.py", data=["cohort.csv"])
        results = {r["id"]: r for r in json.loads(Path("survival/results.json").read_text(encoding="utf-8"))["results"]}
        self.assertEqual(results["cox"]["estimate"]["name"], "hazard ratio, arm B vs A")
        self.assertEqual(results["cox"]["effect_size"], "estimate")
        self.assertIsNone(results["logrank"]["p"])                           # a description: its p stays in extra
        self.assertEqual(results["logrank"]["df"], 1)
        self.assertIsNotNone(results["logrank"]["extra"]["survival"]["p"])
        self.assertEqual(results["km_A"]["extra"]["survival"]["group"], {"column": "arm", "value": "A"})
        self.assertNotIn("_curve", json.dumps(results))
        self.assertEqual(results["rmst"]["extra"]["survival"]["reported"], "B")
        check = load("check_survival", "check_survival_for_records")
        out = io.StringIO()
        with redirect_stdout(out):
            code = check.main([])
        summary = json.loads(out.getvalue())
        self.assertEqual(code, 0, summary["problems"])
        self.assertEqual([summary["checks"][k] for k in ("survival", "ph", "rmst")], ["ok"] * 3)
        with self.assertRaises(ValueError):
            rs.fields(km, group="C")

    @FIGURES
    def test_figures_are_saved_with_their_record(self):
        data = prepared(cohort(20261118), source="cohort.csv")
        km = rs.km_table(data, "arm", times=[0, 10, 20, 30, 40], labels={"A": ["arm A"]})
        png = rs.km_figure(km, "km-arm")
        record = json.loads(Path("survival/km-arm.figure.json").read_text(encoding="utf-8"))
        self.assertTrue(Path(png).is_file() and Path("survival/km-arm.pdf").is_file())
        self.assertEqual((record["axis_findings"], record["data"][0]["path"]), ([], "cohort.csv"))
        fit = rs.cox(data, ["arm", "age"], reference={"arm": "A"})
        ph = rs.ph_test(fit, model="cox arm", plot=["arm[B]"])
        self.assertEqual(ph["plot"], "survival/ph-cox-arm.png")
        self.assertTrue(Path(ph["plot"]).is_file())


if __name__ == "__main__":
    unittest.main()
