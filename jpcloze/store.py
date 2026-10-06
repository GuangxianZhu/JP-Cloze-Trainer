"""作答记录：SQLite（Python 自带 sqlite3）。"""
from __future__ import annotations

import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Attempt:
    qid: str
    correct: bool
    rt: float          # 反应时间（秒）；超时记为时限
    timed_out: bool
    ts: float


class Store:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS attempts(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   qid TEXT NOT NULL,
                   ts REAL NOT NULL,
                   correct INTEGER NOT NULL,
                   rt REAL NOT NULL,
                   timed_out INTEGER NOT NULL DEFAULT 0)"""
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_attempts_qid ON attempts(qid)")
        self.conn.commit()

    def record(self, qid: str, correct: bool, rt: float, timed_out: bool = False) -> None:
        self.conn.execute(
            "INSERT INTO attempts(qid, ts, correct, rt, timed_out) VALUES (?,?,?,?,?)",
            (qid, time.time(), int(correct), float(rt), int(timed_out)),
        )
        self.conn.commit()

    def history(self) -> dict[str, list[Attempt]]:
        """qid -> 按时间排序的作答列表。"""
        out: dict[str, list[Attempt]] = defaultdict(list)
        rows = self.conn.execute(
            "SELECT qid, correct, rt, timed_out, ts FROM attempts ORDER BY ts, id"
        )
        for qid, c, rt, to, ts in rows:
            out[qid].append(Attempt(qid, bool(c), rt, bool(to), ts))
        return dict(out)

    def total_attempts(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
