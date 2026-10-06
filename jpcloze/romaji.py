"""罗马字 → 平假名（打字挖空用）。不依赖输入法。

规则和常见日文输入法一致：
- 拗音 kya/sha/cho、促音（双写辅音 tte / xtu）、nn 或 n+辅音 → ん、"-" → ー
- 小写假名 xa/la、xtu/ltu、xya…
- 末尾还没拼完的字母原样保留，方便边打边看
"""
from __future__ import annotations

_BASE = {
    "a": "あ", "i": "い", "u": "う", "e": "え", "o": "お",
    "ka": "か", "ki": "き", "ku": "く", "ke": "け", "ko": "こ",
    "ga": "が", "gi": "ぎ", "gu": "ぐ", "ge": "げ", "go": "ご",
    "sa": "さ", "si": "し", "shi": "し", "su": "す", "se": "せ", "so": "そ",
    "za": "ざ", "zi": "じ", "ji": "じ", "zu": "ず", "ze": "ぜ", "zo": "ぞ",
    "ta": "た", "ti": "ち", "chi": "ち", "tu": "つ", "tsu": "つ", "te": "て", "to": "と",
    "da": "だ", "di": "ぢ", "du": "づ", "de": "で", "do": "ど",
    "na": "な", "ni": "に", "nu": "ぬ", "ne": "ね", "no": "の",
    "ha": "は", "hi": "ひ", "hu": "ふ", "fu": "ふ", "he": "へ", "ho": "ほ",
    "ba": "ば", "bi": "び", "bu": "ぶ", "be": "べ", "bo": "ぼ",
    "pa": "ぱ", "pi": "ぴ", "pu": "ぷ", "pe": "ぺ", "po": "ぽ",
    "ma": "ま", "mi": "み", "mu": "む", "me": "め", "mo": "も",
    "ya": "や", "yu": "ゆ", "yo": "よ",
    "ra": "ら", "ri": "り", "ru": "る", "re": "れ", "ro": "ろ",
    "la": "ぁ", "li": "ぃ", "lu": "ぅ", "le": "ぇ", "lo": "ぉ",
    "xa": "ぁ", "xi": "ぃ", "xu": "ぅ", "xe": "ぇ", "xo": "ぉ",
    "wa": "わ", "wi": "うぃ", "we": "うぇ", "wo": "を",
    "nn": "ん", "n'": "ん", "xn": "ん",
    "xtu": "っ", "ltu": "っ", "xtsu": "っ", "ltsu": "っ",
    "xya": "ゃ", "xyu": "ゅ", "xyo": "ょ", "lya": "ゃ", "lyu": "ゅ", "lyo": "ょ",
    "xwa": "ゎ", "lwa": "ゎ",
    "fa": "ふぁ", "fi": "ふぃ", "fe": "ふぇ", "fo": "ふぉ",
    "va": "ゔぁ", "vi": "ゔぃ", "vu": "ゔ", "ve": "ゔぇ", "vo": "ゔぉ",
    "she": "しぇ", "je": "じぇ", "che": "ちぇ",
    "thi": "てぃ", "dhi": "でぃ", "twu": "とぅ", "dwu": "どぅ",
    "-": "ー",
}

# 拗音：ki + ya → きゃ 等
_YOON_ROWS = {
    "k": "き", "g": "ぎ", "s": "し", "z": "じ", "t": "ち", "d": "ぢ", "n": "に",
    "h": "ひ", "b": "び", "p": "ぴ", "m": "み", "r": "り",
}
for c, i_kana in _YOON_ROWS.items():
    for v, small in (("a", "ゃ"), ("u", "ゅ"), ("o", "ょ")):
        _BASE[f"{c}y{v}"] = i_kana + small
for pre, i_kana in (("sh", "し"), ("ch", "ち"), ("j", "じ"), ("cy", "ち"), ("jy", "じ")):
    for v, small in (("a", "ゃ"), ("u", "ゅ"), ("o", "ょ")):
        _BASE[f"{pre}{v}"] = i_kana + small

TABLE = _BASE
_MAXLEN = max(len(k) for k in TABLE)
_CONSONANTS = set("bcdfghjklmpqrstvwxyz")


def convert(text: str) -> str:
    """把罗马字转成平假名。末尾未完成的部分保留为罗马字。"""
    s = text.lower()
    out: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        # 促音：双写辅音（n 除外）
        if ch in _CONSONANTS and ch != "n" and i + 1 < len(s) and s[i + 1] == ch:
            out.append("っ")
            i += 1
            continue
        # nn：后面接元音或 y 时只吃掉一个 n（konnichiha → こんにちは），否则两个都吃掉
        if ch == "n" and i + 1 < len(s) and s[i + 1] == "n":
            out.append("ん")
            i += 1 if (i + 2 < len(s) and s[i + 2] in "aiueoy") else 2
            continue
        # n + 辅音（非 y、非 n） → ん
        if ch == "n" and i + 1 < len(s) and s[i + 1] in _CONSONANTS and s[i + 1] not in "ny":
            out.append("ん")
            i += 1
            continue
        for L in range(min(_MAXLEN, len(s) - i), 0, -1):
            piece = s[i:i + L]
            if piece in TABLE:
                out.append(TABLE[piece])
                i += L
                break
        else:
            out.append(s[i:])   # 剩下的还没拼完，原样保留
            break
    return "".join(out)


def finalize(text: str) -> str:
    """提交时调用：末尾单独的 n 视为 ん。"""
    s = text.lower()
    if s.endswith("n") and not s.endswith("nn"):
        s = s[:-1] + "nn"
    return convert(s)


def is_pending(text: str) -> bool:
    """末尾是否还有没拼完的字母（用来提示用户）。"""
    conv = convert(text)
    return bool(conv) and conv[-1].isascii() and conv[-1].isalpha()


_KATA_OFFSET = ord("ァ") - ord("ぁ")


def to_hiragana(s: str) -> str:
    return "".join(chr(ord(c) - _KATA_OFFSET) if "ァ" <= c <= "ヶ" else c for c in s)


def normalize_answer(s: str) -> str:
    """比较答案时：片假名转平假名，去掉空白。"""
    return to_hiragana("".join(s.split()))
