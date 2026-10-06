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


class RomajiTest(unittest.TestCase):
    def test_convert(self):
        from jpcloze.romaji import convert, finalize
        cases = {"tabete": "たべて", "konnichiha": "こんにちは", "kitte": "きって",
                 "benkyousuru": "べんきょうする", "chotto": "ちょっと", "shinbun": "しんぶん",
                 "furarete": "ふられて", "sanpo": "さんぽ", "kyou": "きょう", "oyasumi": "おやすみ"}
        for r, k in cases.items():
            self.assertEqual(finalize(r), k, r)
        self.assertEqual(convert("tab"), "たb")       # 没拼完的保留
        self.assertEqual(finalize("hon"), "ほん")      # 末尾 n → ん


class ReviewAndModesTest(unittest.TestCase):
    def test_due(self):
        from jpcloze.trainer import DAY, due_questions, next_due
        b = load_bank(ROOT / "data")
        q1, q2, q3 = b.questions["L1-001"], b.questions["L1-002"], b.questions["L1-003"]
        now = 100 * DAY
        hist = {
            q1.id: [Attempt(q1.id, False, 3, False, now - 10)],                     # 错 → 到期
            q2.id: [Attempt(q2.id, True, 2, False, now - 0.5 * DAY)],               # 对 1 次，间隔 1 天 → 未到期
            q3.id: [Attempt(q3.id, True, 2, False, now - 2 * DAY)],                 # 对 1 次，2 天前 → 到期
        }
        due = {q.id for q in due_questions([q1, q2, q3], hist, now)}
        self.assertEqual(due, {q1.id, q3.id})
        self.assertIsNone(next_due([]))

    def test_eligible(self):
        from jpcloze.trainer import eligible
        b = load_bank(ROOT / "data")
        audio = set(b.audio)
        typing = [q for q in b.questions.values() if eligible(q, "typing", b.no_typing, audio)]
        self.assertGreater(len(typing), 100)
        self.assertTrue(all(q.level not in (3, 6) for q in typing))
        self.assertTrue(all(q.typing_answers() for q in typing))
        self.assertEqual(len([q for q in b.questions.values()
                              if eligible(q, "listening", b.no_typing, audio)]), len(audio))

    def test_cards_cover_tags(self):
        b = load_bank(ROOT / "data")
        missing = {t for q in b.questions.values() for t in q.tags if t not in b.cards}
        self.assertEqual(missing, set())

    def test_store_migration(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "old.db"
            c = sqlite3.connect(p)
            c.execute("CREATE TABLE attempts(id INTEGER PRIMARY KEY AUTOINCREMENT, qid TEXT NOT NULL,"
                      " ts REAL NOT NULL, correct INTEGER NOT NULL, rt REAL NOT NULL,"
                      " timed_out INTEGER NOT NULL DEFAULT 0)")
            c.execute("INSERT INTO attempts(qid, ts, correct, rt) VALUES ('L1-001', 1, 1, 2.0)")
            c.commit()
            c.close()
            s = Store(p)
            s.record("L1-002", False, 3.0, mode="typing")
            self.assertEqual(s.total_attempts(), 2)
            s.close()


if __name__ == "__main__":
    unittest.main()
