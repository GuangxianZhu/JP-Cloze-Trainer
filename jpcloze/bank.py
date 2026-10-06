"""题库：读取 data/L*.json、知识卡 data/cards/*.json、语音清单和打字元数据。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .romaji import normalize_answer

BLANK = "{blank}"
_KANA = re.compile(r"^[ぁ-ゖァ-ヶー]+$")


@dataclass(frozen=True)
class Question:
    id: str
    level: int
    tags: tuple[str, ...]
    sentence: str               # 含 {blank}
    options: tuple[str, ...]    # options[0] 是正确答案
    explain: str
    context: str = ""
    reading: str = ""           # 答案含汉字时的平假名读音（打字模式用）
    hint: str = ""              # 打字模式的提示（原形等）
    alt: tuple[str, ...] = ()   # 打字模式也算对的其他写法

    @property
    def answer(self) -> str:
        return self.options[0]

    def with_blank(self, blank: str = "（　　）") -> str:
        return self.sentence.replace(BLANK, blank)

    def filled(self, left: str = "", right: str = "") -> str:
        return self.sentence.replace(BLANK, f"{left}{self.answer}{right}")

    def typing_answers(self) -> list[str]:
        """打字模式接受的答案（平假名）。答案含汉字又没有读音时为空。"""
        main = self.reading or self.answer
        out = []
        for s in (main, *self.alt):
            s = normalize_answer(s)
            if _KANA.match(s) and s not in out:
                out.append(s)
        return out


@dataclass(frozen=True)
class Card:
    tag: str
    title: str
    rule: str
    examples: tuple[tuple[str, str], ...]
    pitfall: str


@dataclass
class Bank:
    questions: dict[str, Question] = field(default_factory=dict)
    titles: dict[int, str] = field(default_factory=dict)
    cards: dict[str, Card] = field(default_factory=dict)
    audio: dict[str, tuple[Path, float]] = field(default_factory=dict)   # qid -> (文件, 秒)
    no_typing: set[str] = field(default_factory=set)

    def levels(self) -> list[int]:
        return sorted(self.titles)

    def by_level(self, levels: list[int] | None = None) -> list[Question]:
        qs = self.questions.values()
        if levels:
            qs = [q for q in qs if q.level in levels]
        return sorted(qs, key=lambda q: q.id)

    def card_for(self, q: Question) -> Card | None:
        for t in q.tags:
            if t in self.cards:
                return self.cards[t]
        return None


def _validate(raw: dict, src: Path) -> None:
    where = f"{src.name}:{raw.get('id', '?')}"
    for key in ("id", "sentence", "options", "explain"):
        if key not in raw:
            raise ValueError(f"{where} 缺少字段 {key}")
    if raw["sentence"].count(BLANK) != 1:
        raise ValueError(f"{where} sentence 里必须恰好有一个 {BLANK}")
    opts = raw["options"]
    if len(opts) < 2 or len(set(opts)) != len(opts):
        raise ValueError(f"{where} options 至少 2 个且不能重复")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_bank(data_dir: Path) -> Bank:
    data_dir = Path(data_dir)
    bank = Bank()
    files = sorted(data_dir.glob("L*.json"))
    if not files:
        raise FileNotFoundError(f"在 {data_dir} 里没找到题库 L*.json")
    for path in files:
        doc = _read_json(path)
        level = int(doc["level"])
        bank.titles[level] = doc.get("title", f"L{level}")
        for raw in doc["questions"]:
            _validate(raw, path)
            if raw["id"] in bank.questions:
                raise ValueError(f"{path.name}: 题目 id 重复 {raw['id']}")
            bank.questions[raw["id"]] = Question(
                id=raw["id"], level=level, tags=tuple(raw.get("tags", [])),
                sentence=raw["sentence"], options=tuple(raw["options"]),
                explain=raw["explain"], context=raw.get("context", ""),
                reading=raw.get("reading", "") or "", hint=raw.get("hint", "") or "",
                alt=tuple(raw.get("alt", [])),
            )

    for path in sorted((data_dir / "cards").glob("*.json")):
        for tag, c in _read_json(path).get("cards", {}).items():
            bank.cards[tag] = Card(
                tag=tag, title=c.get("title", tag), rule=c.get("rule", ""),
                examples=tuple((e.get("ja", ""), e.get("zh", "")) for e in c.get("examples", [])),
                pitfall=c.get("pitfall", ""),
            )

    man = data_dir / "audio" / "manifest.json"
    if man.exists():
        for qid, info in _read_json(man).items():
            f = data_dir / "audio" / info["file"]
            if qid in bank.questions and f.exists():
                bank.audio[qid] = (f, float(info.get("dur", 3.0)))

    typ = data_dir / "typing.json"
    if typ.exists():
        bank.no_typing = set(_read_json(typ).get("no_typing", {}))
    return bank


if __name__ == "__main__":  # python -m jpcloze.bank ：检查题库
    b = load_bank(Path(__file__).resolve().parent.parent / "data")
    for lv in b.levels():
        qs = b.by_level([lv])
        missing = sorted({t for q in qs for t in q.tags if t not in b.cards})
        print(f"{b.titles[lv]}: {len(qs)} 题" + (f"（缺知识卡：{missing}）" if missing else ""))
    print(f"知识卡 {len(b.cards)} 张，语音 {len(b.audio)} 条，打字排除 {len(b.no_typing)} 题")
