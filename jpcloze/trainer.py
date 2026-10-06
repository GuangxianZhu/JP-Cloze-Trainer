"""出题与统计逻辑（不依赖 Panda3D，可单独测试）。

语感 = 又快又对。所以每道题根据「最近是否答对」和「反应时间」分成几种状态，
状态决定这道题被抽到的概率和作答时限。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from statistics import mean

from .bank import Question
from .store import Attempt

FLUENT_RT = 3.0   # 连续两次在这个秒数内答对 → 有语感
SLOW_RT = 6.0     # 答对但超过这个秒数 → 偏慢，需要再练

# 状态 → (抽题权重, 作答时限秒)
STATE_RULES = {
    "new":      (3.0, 15.0),   # 没做过
    "weak":     (5.0, 15.0),   # 最近一次答错/超时
    "slow":     (3.0, 10.0),   # 答对但慢
    "learning": (1.5, 8.0),    # 答对，还不够稳定
    "fluent":   (0.3, 5.0),    # 连续快速答对
}

STATE_LABEL = {
    "new": "新题", "weak": "答错过", "slow": "偏慢", "learning": "练习中", "fluent": "有语感",
}


def question_state(attempts: list[Attempt]) -> str:
    if not attempts:
        return "new"
    last = attempts[-1]
    if not last.correct:
        return "weak"
    if last.rt > SLOW_RT:
        return "slow"
    recent = attempts[-2:]
    if len(recent) == 2 and all(a.correct and a.rt <= FLUENT_RT for a in recent):
        return "fluent"
    return "learning"


def time_limit(state: str, scale: float = 1.0) -> float:
    return STATE_RULES[state][1] * scale


def pick_round(questions: list[Question], history: dict[str, list[Attempt]],
               n: int = 20, rng: random.Random | None = None) -> list[Question]:
    """按权重不放回抽 n 题：错题、慢题、新题优先，已熟练的偶尔复习。"""
    rng = rng or random.Random()
    pool = list(questions)
    weights = [STATE_RULES[question_state(history.get(q.id, []))][0] for q in pool]
    picked: list[Question] = []
    for _ in range(min(n, len(pool))):
        i = rng.choices(range(len(pool)), weights=weights)[0]
        picked.append(pool.pop(i))
        weights.pop(i)
    return picked


def shuffled_options(q: Question, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    opts = list(q.options)
    rng.shuffle(opts)
    return opts


@dataclass
class RoundItem:
    question: Question
    chosen: str | None      # None = 超时
    rt: float
    limit: float

    @property
    def correct(self) -> bool:
        return self.chosen == self.question.answer

    @property
    def timed_out(self) -> bool:
        return self.chosen is None


@dataclass
class TagStat:
    tag: str
    n: int
    correct: int
    avg_rt: float           # 只算答对的题；没有答对时为 nan

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def weakness(self) -> float:
        """越大越弱：主要看正确率，其次看速度。"""
        speed_pen = 0.0 if self.avg_rt != self.avg_rt else min(self.avg_rt / 10.0, 1.0)
        return (1 - self.accuracy) * 2 + speed_pen


@dataclass
class RoundSummary:
    items: list[RoundItem] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.items)

    @property
    def n_correct(self) -> int:
        return sum(i.correct for i in self.items)

    @property
    def avg_rt_correct(self) -> float:
        rts = [i.rt for i in self.items if i.correct]
        return mean(rts) if rts else float("nan")

    @property
    def n_fast(self) -> int:
        return sum(1 for i in self.items if i.correct and i.rt <= FLUENT_RT)

    def tag_stats(self) -> list[TagStat]:
        return tag_stats_from_pairs((i.question, i.correct, i.rt) for i in self.items)


def tag_stats_from_pairs(pairs) -> list[TagStat]:
    acc: dict[str, list[tuple[bool, float]]] = {}
    for q, correct, rt in pairs:
        for t in q.tags:
            acc.setdefault(t, []).append((correct, rt))
    out = []
    for tag, rs in acc.items():
        ok_rts = [rt for c, rt in rs if c]
        out.append(TagStat(tag, len(rs), len(ok_rts), mean(ok_rts) if ok_rts else float("nan")))
    out.sort(key=lambda s: s.weakness, reverse=True)
    return out


def overall_tag_stats(questions: dict[str, Question], history: dict[str, list[Attempt]],
                      last_k: int = 3) -> list[TagStat]:
    """历史统计：每道题只看最近 last_k 次，反映「现在」的水平。"""
    pairs = []
    for qid, atts in history.items():
        q = questions.get(qid)
        if q is None:
            continue
        for a in atts[-last_k:]:
            pairs.append((q, a.correct, a.rt))
    return tag_stats_from_pairs(pairs)


def level_progress(questions: list[Question], history: dict[str, list[Attempt]]) -> dict[str, int]:
    counts = {s: 0 for s in STATE_RULES}
    for q in questions:
        counts[question_state(history.get(q.id, []))] += 1
    return counts
