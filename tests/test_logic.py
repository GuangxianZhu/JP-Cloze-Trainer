"""逻辑测试（不需要窗口）：python -m unittest discover tests"""
import random
import tempfile
import unittest
from pathlib import Path

from jpcloze.bank import load_bank
from jpcloze.store import Attempt, Store
from jpcloze.trainer import (RoundItem, RoundSummary, overall_tag_stats, pick_round,
                             question_state, shuffled_options)

ROOT = Path(__file__).resolve().parent.parent


def att(correct, rt):
    return Attempt("x", correct, rt, False, 0.0)


class BankTest(unittest.TestCase):
    def test_load(self):
        b = load_bank(ROOT / "data")
        self.assertGreaterEqual(len(b.questions), 100)
        for q in b.questions.values():
            self.assertIn(q.answer, q.filled())
            self.assertNotIn("{blank}", q.with_blank())


class StateTest(unittest.TestCase):
    def test_states(self):
        self.assertEqual(question_state([]), "new")
        self.assertEqual(question_state([att(True, 1)]), "learning")
        self.assertEqual(question_state([att(True, 1), att(False, 1)]), "weak")
        self.assertEqual(question_state([att(True, 9)]), "slow")
        self.assertEqual(question_state([att(True, 2), att(True, 2.5)]), "fluent")
        self.assertEqual(question_state([att(True, 5), att(True, 2.5)]), "learning")


class PickTest(unittest.TestCase):
    def test_round_unique_and_prefers_weak(self):
        b = load_bank(ROOT / "data")
        qs = b.by_level([1])
        fluent = {q.id: [att(True, 1), att(True, 1)] for q in qs[:-5]}
        weak_ids = {q.id for q in qs[-5:]}
        hist = dict(fluent)
        hist.update({qid: [att(False, 3)] for qid in weak_ids})
        hits = 0
        rng = random.Random(0)
        for _ in range(50):
            r = pick_round(qs, hist, 20, rng)
            self.assertEqual(len({q.id for q in r}), 20)
            hits += len(weak_ids & {q.id for q in r})
        self.assertGreater(hits / 50, 4.0)  # 5 道错题几乎每轮都出现

    def test_shuffle_keeps_options(self):
        q = load_bank(ROOT / "data").questions["L1-001"]
        self.assertEqual(sorted(shuffled_options(q)), sorted(q.options))


class StoreAndStatsTest(unittest.TestCase):
    def test_roundtrip(self):
        b = load_bank(ROOT / "data")
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "t.db")
            s.record("L1-001", True, 2.0)
            s.record("L1-001", False, 15.0, timed_out=True)
            s.record("L1-009", True, 4.0)
            h = s.history()
            self.assertEqual([a.correct for a in h["L1-001"]], [True, False])
            self.assertTrue(h["L1-001"][1].timed_out)
            stats = {t.tag: t for t in overall_tag_stats(b.questions, h)}
            self.assertEqual(stats["は・が"].n, 2)
            self.assertEqual(stats["は・が"].correct, 1)
            s.close()

    def test_summary(self):
        b = load_bank(ROOT / "data")
        q1, q2 = b.questions["L1-001"], b.questions["L2-001"]
        s = RoundSummary([RoundItem(q1, q1.answer, 2.0, 15), RoundItem(q2, None, 15, 15)])
        self.assertEqual(s.n_correct, 1)
        self.assertEqual(s.n_fast, 1)
        self.assertEqual(s.tag_stats()[0].tag, q2.tags[0])  # 错的排在前面


if __name__ == "__main__":
    unittest.main()
