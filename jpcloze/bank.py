"""题库：读取 data/*.json，校验格式，提供按级别查询。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

BLANK = "{blank}"


@dataclass(frozen=True)
class Question:
    id: str
    level: int
    tags: tuple[str, ...]
    sentence: str          # 含 {blank}
    options: tuple[str, ...]  # options[0] 是正确答案
    explain: str
    context: str = ""

    @property
    def answer(self) -> str:
        return self.options[0]

    def with_blank(self, blank: str = "（　　）") -> str:
        return self.sentence.replace(BLANK, blank)

    def filled(self, left: str = "", right: str = "") -> str:
        """把正确答案填进去；left/right 可传入颜色标记。"""
        return self.sentence.replace(BLANK, f"{left}{self.answer}{right}")


@dataclass
class Bank:
    questions: dict[str, Question] = field(default_factory=dict)
    titles: dict[int, str] = field(default_factory=dict)

    def levels(self) -> list[int]:
        return sorted(self.titles)

    def by_level(self, levels: list[int] | None = None) -> list[Question]:
        qs = self.questions.values()
        if levels:
            qs = [q for q in qs if q.level in levels]
        return sorted(qs, key=lambda q: q.id)


def _validate(raw: dict, src: Path) -> None:
    qid = raw.get("id", "?")
    where = f"{src.name}:{qid}"
    for key in ("id", "sentence", "options", "explain"):
        if key not in raw:
            raise ValueError(f"{where} 缺少字段 {key}")
    if raw["sentence"].count(BLANK) != 1:
        raise ValueError(f"{where} sentence 里必须恰好有一个 {BLANK}")
    opts = raw["options"]
    if len(opts) < 2 or len(set(opts)) != len(opts):
        raise ValueError(f"{where} options 至少 2 个且不能重复")


def load_bank(data_dir: Path) -> Bank:
    bank = Bank()
    files = sorted(Path(data_dir).glob("*.json"))
    if not files:
        raise FileNotFoundError(f"在 {data_dir} 里没找到题库 json")
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        level = int(doc["level"])
        bank.titles[level] = doc.get("title", f"L{level}")
        for raw in doc["questions"]:
            _validate(raw, path)
            if raw["id"] in bank.questions:
                raise ValueError(f"{path.name}: 题目 id 重复 {raw['id']}")
            bank.questions[raw["id"]] = Question(
                id=raw["id"],
                level=level,
                tags=tuple(raw.get("tags", [])),
                sentence=raw["sentence"],
                options=tuple(raw["options"]),
                explain=raw["explain"],
                context=raw.get("context", ""),
            )
    return bank


if __name__ == "__main__":  # python -m jpcloze.bank ：检查题库
    b = load_bank(Path(__file__).resolve().parent.parent / "data")
    for lv in b.levels():
        print(f"{b.titles[lv]}: {len(b.by_level([lv]))} 题")
