"""sr_prisma.py: every PRISMA 2020 count comes from the ledger, and each identity is OK, FAIL or NOT_ASSESSED.

The review is the one test_sr_ledger.py builds from the invented records in tests/fixtures."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_sr_ledger import LedgerTestCase  # noqa: E402

SCRIPT = Path(__file__).parents[1] / "scripts" / "sr_prisma.py"
spec = importlib.util.spec_from_file_location("sr_prisma", SCRIPT)
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


class PrismaTests(LedgerTestCase):
    def prisma(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = sp.main(["--dir", str(self.dir), *argv])
        return code, json.loads(out.getvalue())

    def test_counts_identities_and_files(self):
        self.build()
        code, out = self.prisma("--svg")
        self.assertEqual((code, out["identities_failed"], out["not_assessed"]), (0, [], []))
        f = json.loads((self.dir / "prisma.json").read_text())
        self.assertEqual([(i["source"], i["kind"], i["records"]) for i in f["identification"]],
                         [("Embase", "database", 2), ("PubMed", "database", 2), ("Researchzy index", "database", 4),
                          ("ClinicalTrials.gov", "register", 2)])
        counts = {k: f[k] for k in ("records_identified", "duplicates_removed", "records_screened", "records_excluded",
                                    "reports_sought", "reports_not_retrieved", "reports_assessed", "reports_excluded",
                                    "reports_included", "studies_included")}
        self.assertEqual(counts, {"records_identified": 10, "duplicates_removed": 3, "records_screened": 7,
                                  "records_excluded": 3, "reports_sought": 4, "reports_not_retrieved": 1,
                                  "reports_assessed": 3, "reports_excluded": 1, "reports_included": 2, "studies_included": 1})
        self.assertEqual(list(f["records_excluded_by_code"].items()), [("E3", 2), ("E2", 1)])   # in the protocol's order
        self.assertEqual(f["screened_by"]["ta"], {"model": 6, "user": 1})
        self.assertEqual(f["registration"], "The protocol was not registered.")
        table = (self.dir / "prisma.md").read_text()
        for row in ("| Records identified: ClinicalTrials.gov (register) | 2 |", "| - E3 animal study | 2 |",
                    "| Reports not retrieved | 1 |", "| Studies included | 1 |", "| Reports of included studies | 2 |",
                    "| R0002 | Time of the last meal and sleep in older adults: a synthetic crossover trial | E1 | p. 2 |"):
            self.assertIn(row, table)
        drawing = ET.fromstring((self.dir / "prisma.svg").read_text())
        texts = [t.text for t in drawing.iter("{http://www.w3.org/2000/svg}text")]
        self.assertIn("Reports excluded (n\u00a0=\u00a01)", texts)
        self.assertIn("E1 not a randomised trial (n\u00a0=\u00a01)", texts)

    def test_an_unfinished_screening_fails_an_identity(self):
        self.build()
        self.write("one.ris", "TY  - JOUR\nTI  - A further invented record on meal timing\nPY  - 2024\nER  - \n")
        self.run_cli("search", "--source", "Scopus", "--kind", "database", "--interface", "export", "--query", "q", "--total", "1")
        self.run_cli("records", str(self.base / "one.ris"), "--search", "s5", "--format", "ris")
        code, out = self.prisma()
        self.assertEqual((code, out["identities_failed"]), (1, ["records screened - records excluded = reports sought for retrieval"]))

    def test_an_update_counts_new_records_and_the_previous_version(self):
        self.build()
        self.run_cli("search", "--source", "Researchzy index", "--kind", "database", "--interface", "search_papers",
                     "--query", '"evening meal" sleep', "--filter", "yearFrom=2026", "--total", "2", "--last-page",
                     "--round", "2", "--date", "2027-05-01")
        update = {"papers": [{"corpusId": 900001, "title": "Evening Meal Timing and Sleep Quality: A Synthetic Randomised Trial",
                              "year": 2021, "doi": "10.5555/fixture.001"},
                             {"corpusId": 900077, "title": "A new invented trial of evening meal timing and sleep", "year": 2027,
                              "abstract": "Synthetic adults were randomised to an early meal."}]}
        self.run_cli("records", str(self.write("update.json", update)), "--search", "s5", "--format", "researchzy")
        self.decide({"record": "R0012", "stage": "ta", "decision": "include", "reviewer": "model"})
        self.decide({"record": "R0012", "stage": "ft", "decision": "include", "reviewer": "model"})
        code, out = self.prisma("--round", "2", "--svg")
        f = json.loads((self.dir / "prisma.json").read_text())
        self.assertEqual((code, f["records_identified"], f["duplicates_removed"], f["records_screened"]), (0, 2, 1, 1))
        self.assertEqual((f["previous"], f["total"]), ({"studies": 1, "reports": 2}, {"studies": 2, "reports": 3}))
        self.assertIn("Total studies included in review (n\u00a0=\u00a02)", (self.dir / "prisma.svg").read_text())
        _, out = self.prisma("--round", "2", "--previous-studies", "4")
        self.assertEqual(out["not_assessed"], ["studies included <= reports of included studies"])

    def test_registration_wording_follows_the_dates(self):
        ledger = {"searches": [{"kind": "database", "date": "2026-11-10T09:00Z", "round": 1},
                               {"kind": "other", "date": "2026-11-01", "round": 1}]}
        reg = {"status": "registered", "registry": "a registry", "id": "X-1", "date": "2026-11-03"}
        self.assertIn("prospectively registered", sp.registration({"registration": reg}, ledger))
        self.assertIn("after the first search on 2026-11-10",
                      sp.registration({"registration": dict(reg, date="2026-11-12")}, ledger))
        self.assertIn("the day of the first search", sp.registration({"registration": dict(reg, date="2026-11-10")}, ledger))
        self.assertEqual(sp.registration({"registration": {"status": "planned"}}, ledger),
                         "The protocol was not registered (registration is planned).")

    def test_without_a_ledger_it_stops_with_exit_code_2(self):
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()) as err, redirect_stdout(io.StringIO()):
            sp.main(["--dir", str(self.dir)])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("no ledger", err.getvalue())


if __name__ == "__main__":
    unittest.main()
