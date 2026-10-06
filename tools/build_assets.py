"""开发用：根据题库生成语音和打字模式元数据。

  pip install pyopenjtalk-plus soundfile numpy
  python tools/build_assets.py           # 只生成新增/改动过的题
  python tools/build_assets.py --force   # 全部重新生成

产物（提交到仓库，用户那边不需要装上面这些包）：
  data/audio/<题目id>.ogg       整句朗读（填好答案）
  data/audio/manifest.json      文本哈希、时长
  data/typing.json              打字模式不适合的题（正确答案和某个干扰项读音相同）

TTS 读错的句子：在 data/tts_overrides.json 里写 {"题目id": "把误读的词改成平假名的句子"}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pyopenjtalk  # noqa: E402
import soundfile as sf  # noqa: E402

from jpcloze.bank import load_bank  # noqa: E402
from jpcloze.romaji import to_hiragana  # noqa: E402

AUDIO = ROOT / "data" / "audio"
SR_OUT = 24000


def tts_text(sentence_filled: str) -> str:
    """去掉舞台说明（…）和说话人标签，只留要读的句子。"""
    s = re.sub(r"（[^）]*）", "", sentence_filled)
    quoted = re.findall(r"「([^」]*)」?", s)
    if quoted:
        s = "".join(quoted)
    s = re.sub(r"^[^「]{1,6}「", "", s)
    return s.replace("」", "").strip()


def synth(text: str) -> tuple[np.ndarray, float]:
    x, sr = pyopenjtalk.tts(text)          # float64, 48kHz, int16 量级
    x = x.astype(np.float64)
    n = len(x) // 2 * 2
    y = (x[0:n:2] + x[1:n:2]) / 2.0        # 简单低通 + 降采样到 24kHz
    peak = np.max(np.abs(y)) or 1.0
    y = (y / peak * 0.9).astype(np.float32)
    pad = np.zeros(int(0.15 * SR_OUT), dtype=np.float32)
    y = np.concatenate([pad, y, pad])
    return y, len(y) / SR_OUT


def reading_of(word: str) -> str:
    return to_hiragana(pyopenjtalk.g2p(word, kana=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    bank = load_bank(ROOT / "data")
    AUDIO.mkdir(parents=True, exist_ok=True)
    man_path = AUDIO / "manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}

    ov_path = ROOT / "data" / "tts_overrides.json"   # TTS 读错时的手动修正（误读的词改成平假名）
    overrides = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}

    made = 0
    for q in bank.questions.values():
        text = overrides.get(q.id) or tts_text(q.filled())
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        out = AUDIO / f"{q.id}.ogg"
        old = manifest.get(q.id)
        if not args.force and old and old.get("hash") == h and out.exists():
            continue
        y, dur = synth(text)
        sf.write(str(out), y, SR_OUT, format="OGG", subtype="VORBIS")
        manifest[q.id] = {"file": out.name, "hash": h, "dur": round(dur, 2), "text": text}
        made += 1
    # 删掉已不存在的题
    for qid in list(manifest):
        if qid not in bank.questions:
            (AUDIO / manifest[qid]["file"]).unlink(missing_ok=True)
            del manifest[qid]
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    # 打字模式：答案读音和某个干扰项读音一样的题，打假名分不出对错
    no_typing = {}
    for q in bank.questions.values():
        answers = q.typing_answers()
        if not answers:
            no_typing[q.id] = "答案没有假名读音"
            continue
        ans = answers[0]
        for d in q.options[1:]:
            if reading_of(d) == ans or to_hiragana(d) == ans:
                no_typing[q.id] = f"答案和「{d}」读音相同"
                break
    (ROOT / "data" / "typing.json").write_text(
        json.dumps({"no_typing": no_typing}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"语音：新生成 {made} 条，共 {len(manifest)} 条")
    print(f"打字模式排除 {len(no_typing)} 题：{', '.join(no_typing)}")


if __name__ == "__main__":
    main()
