"""tad_compare.py: dictionary counts with negation and context, and topic models that are named only after reading.

The dictionary tests need only the standard library. The topic tests need scikit-learn and numpy and skip
without them; the report of a missing scikit-learn is tested everywhere."""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import random
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts" / "tad_compare.py"
spec = importlib.util.spec_from_file_location("tad_compare", SCRIPT)
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)
HAVE_SKLEARN = tc.load_sklearn() is not None

REVIEWS = [  # id, product line, text
    ("r1", "耳机", "这款耳机价格太贵了，不值这个钱。"),
    ("r2", "耳机", "价格不贵，做工也结实。"),
    ("r3", "充电器", "比别家贵了二十元，客服还不回复。"),
    ("r4", "充电器", "The charger isn't expensive, and customer service answered fast."),
    ("r5", "数据线", "The cable is overpriced and the cost of shipping was high."),
    ("r6", "数据线", "不但价格贵，而且质量差，接口松动。"),
    ("r7", "耳机", "收到了，放在抽屉里备用。"),
]
TERMS = "category,term\n价格,贵\n价格,overpriced\n价格,cost\n价格,expensive\n质量,松动\n质量,结实\n服务,客服\n服务,customer service\n"
THEMES = {"价格": "价格 便宜 太贵 优惠 打折 降价 性价比 划算 涨价 退差价".split(),
          "质量": "质量 做工 坏了 结实 耐用 材质 粗糙 松动 开裂 掉漆".split(),
          "服务": "客服 物流 退货 回复 态度 发货 快递 售后 换货 投诉".split()}
FILLER = "这个 东西 我们 觉得 还是 然后 已经 真的".split()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dir = self.root / "text-as-data"
        self.dir.mkdir()
        self.corpus([{"id": i, "line": g, "text": t} for i, g, t in REVIEWS])
        (self.dir / "codebook.csv").write_text("code,definition,version\n价格,Price,1\n质量,Quality,1\n服务,Service,1\n无,None,1\n",
                                               encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def corpus(self, rows: list) -> None:
        with open(self.root / "docs.csv", "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (self.dir / "protocol.json").write_text(json.dumps({
            "corpus": {"file": str(self.root / "docs.csv"), "id": "id", "text": "text", "groups": ["line"]},
            "classes": ["价格", "质量", "服务", "无"], "labels": "single", "seed": 1}, ensure_ascii=False), encoding="utf-8")

    def run_cli(self, command: str, *argv):
        out, self.err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(self.err):
            code = tc.main([command, "--dir", str(self.dir), *[str(a) for a in argv]])
        return code, json.loads(out.getvalue())

    def rows(self, path: Path) -> list:
        return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


class DictionaryTests(Base):
    def setUp(self):
        super().setUp()
        (self.root / "terms.csv").write_text(TERMS, encoding="utf-8")

    def test_hits_negation_and_whole_words_in_chinese_and_english(self):
        code, out = self.run_cli("dictionary", self.root / "terms.csv", "--kwic", 10)
        self.assertEqual(code, 0)
        scores = {row["unit"]: row for row in self.rows(self.dir / "dictionary" / "scores.csv")}
        self.assertEqual((scores["r1"]["价格"], scores["r1"]["价格_negated"]), ("1", "0"))
        self.assertEqual((scores["r2"]["价格"], scores["r2"]["价格_negated"]), ("0", "1"))     # 价格不贵
        self.assertEqual(scores["r3"]["价格"], "1")                                             # 别家贵: 别 is not a negation here
        self.assertEqual((scores["r4"]["价格"], scores["r4"]["价格_negated"]), ("0", "1"))     # isn't expensive
        self.assertEqual(scores["r5"]["价格"], "2")                                             # cost matches cost, not costs
        self.assertEqual(scores["r6"]["价格"], "1")                                             # 不但 does not negate
        self.assertEqual((scores["r4"]["服务"], scores["r3"]["服务"]), ("1", "1"))
        self.assertEqual(out["coverage"], {"价格": 4, "质量": 2, "服务": 2})
        report = (self.dir / "dictionary" / "dictionary.md").read_text(encoding="utf-8")
        self.assertIn("| 价格 | 4 | 0.571 | 2 |", report)
        self.assertIn("| 耳机 | 3 | 0.333 | 0.333 | 0.000 |", report)
        self.assertIn("Not checked: no category is named like a class, or no round has been scored.", report)

    def test_the_context_sample_is_seeded_and_keeps_the_texts_punctuation(self):
        self.run_cli("dictionary", self.root / "terms.csv", "--kwic", 2, "--seed", 5)
        first = (self.dir / "dictionary" / "kwic.csv").read_text(encoding="utf-8-sig")
        self.run_cli("dictionary", self.root / "terms.csv", "--kwic", 2, "--seed", 5)
        self.assertEqual((self.dir / "dictionary" / "kwic.csv").read_text(encoding="utf-8-sig"), first)
        rows = self.rows(self.dir / "dictionary" / "kwic.csv")
        self.assertEqual(sum(row["category"] == "价格" for row in rows), 2)
        self.assertTrue(all(row["valid"] == "" for row in rows))
        self.assertTrue(any("，" in row["left"] + row["right"] for row in rows))

    def test_hits_are_compared_with_the_users_labels_of_scored_rounds(self):
        rounds = self.dir / "rounds"
        rounds.mkdir()
        units = ["r1", "r2", "r3", "r6"]
        (rounds / "round1-sample.json").write_text(json.dumps({"units": [{"unit": u} for u in units]}), encoding="utf-8")
        (rounds / "round1-user.csv").write_text("unit,text,label\nr1,,价格\nr2,,质量\nr3,,服务\nr6,,价格\n", encoding="utf-8")
        (rounds / "round1-score.json").write_text("{}", encoding="utf-8")
        code, out = self.run_cli("dictionary", self.root / "terms.csv")
        report = (self.dir / "dictionary" / "dictionary.md").read_text(encoding="utf-8")
        self.assertTrue(out["against_labels"])
        self.assertIn("| 价格 | 4 | 2 of 3 | 2 of 2 |", report)      # r3's 贵 is a hit the user labelled 服务

    def test_a_dictionary_without_terms_stops(self):
        (self.root / "empty.csv").write_text("category,term\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as caught, redirect_stderr(io.StringIO()) as err:
            tc.main(["dictionary", "--dir", str(self.dir), str(self.root / "empty.csv")])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("holds no term", err.getvalue())


class TopicTests(Base):
    def setUp(self):
        super().setUp()
        rng, rows = random.Random(7), []
        for n in range(120):
            words = rng.sample(THEMES[list(THEMES)[n % 3]], 5) + rng.sample(FILLER, 2)
            rng.shuffle(words)
            rows.append({"id": f"d{n:03d}", "line": "AB"[n % 2], "text": "".join(words), "words": " ".join(words)})
        self.corpus(rows)

    def test_without_scikit_learn_the_step_is_reported_as_not_run(self):
        with mock.patch.object(tc, "load_sklearn", return_value=None):
            code, out = self.run_cli("topics", "--k", 5)
        self.assertEqual((code, out["status"], out["reason"]), (0, "not_run", "scikit-learn missing"))
        self.assertEqual(json.loads((self.dir / "topics" / "topics.json").read_text(encoding="utf-8"))["status"], "not_run")

    def test_chinese_becomes_character_bigrams_and_english_loses_stop_words(self):
        tokens = tc.analyzer({"the", "is"}, False)("价格太贵 The cable is flimsy")
        self.assertEqual(tokens, ["cable", "flimsy", "价格", "格太", "太贵"])
        self.assertEqual(tc.analyzer(set(), True)("价格 太贵 质量"), ["价格", "太贵", "质量"])

    @unittest.skipUnless(HAVE_SKLEARN, "needs scikit-learn and numpy")
    def test_topics_are_unnamed_without_reading_and_unstable_ones_are_marked(self):
        code, out = self.run_cli("topics", "--k", "3,5", "--segmented", "words", "--iter", 30)
        models = {m["k"]: m for m in out["models"]}
        self.assertEqual((code, models[3]["unstable"]), (0, []))
        self.assertGreaterEqual(len(models[5]["unstable"]), 2)          # three themes cannot fill five stable topics
        self.assertEqual(models[5]["named"], [])
        self.assertEqual(set(models[5]["not_named"].values()), {"not named: no reading log"})
        topics = self.rows(self.dir / "topics" / "k5-topics.csv")
        self.assertTrue(all(row["name"] == "" for row in topics))
        reading = (self.dir / "topics" / "k5-reading.md").read_text(encoding="utf-8")
        shown = topics[0]["representative_units"].split(";")
        self.assertEqual(len(shown), 5)
        self.assertIn(f"- {shown[0]}: ", reading)
        log = ("k,topic,units_read,name,read_by,date\n"
               f"5,1,{';'.join(shown)},Name read from the texts,LZ,2026-11-18\n"
               "5,2,,Named from its top words,LZ,2026-11-18\n"
               f"5,3,{topics[2]['representative_units'].split(';')[0]},Read one text only,LZ,2026-11-18\n")
        (self.root / "log.csv").write_text(log, encoding="utf-8")
        code, out = self.run_cli("topics", "--k", 5, "--segmented", "words", "--iter", 30, "--reading-log", self.root / "log.csv")
        topics = self.rows(self.dir / "topics" / "k5-topics.csv")
        self.assertEqual([row["name"] for row in topics], ["Name read from the texts", "", "", "", ""])
        self.assertTrue(topics[1]["name_status"].startswith("not named: the reading log does not list"))
        read_one = topics[2]["representative_units"].split(";")
        self.assertEqual(topics[2]["name_status"], f"not named: the reading log does not list {', '.join(read_one[1:])} as read")
        self.assertEqual(topics[3]["name_status"], "not named: no name in the reading log")
        self.assertEqual(out["models"][0]["named"], [1])

    @unittest.skipUnless(HAVE_SKLEARN, "needs scikit-learn and numpy")
    def test_settings_and_coherence_are_reported(self):
        code, out = self.run_cli("topics", "--k", 3, "--seeds", "1,2", "--method", "nmf", "--iter", 30)
        self.assertEqual(out["settings"]["tokens"], "Latin words and CJK character bigrams")
        self.assertEqual(out["settings"]["seeds"], [1, 2])
        rows = self.rows(self.dir / "topics" / "k3-topics.csv")
        self.assertTrue(all(float(row["coherence_umass"]) <= 0.5 for row in rows))
        self.assertIn("Choose K by coherence and by reading", (self.dir / "topics" / "topics.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
