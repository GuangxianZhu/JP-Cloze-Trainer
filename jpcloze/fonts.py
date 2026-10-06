"""找系统里的日文/中文字体。Panda3D 默认字体不含汉字和假名，必须指定。

日文题目用日文字体（汉字字形正确），中文解释用中文字体（简体字齐全）。
可以在 config.json 里用 font_ja / font_zh 手动指定路径。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_WIN = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

JA_CANDIDATES = [
    _WIN / "YuGothM.ttc", _WIN / "YuGothR.ttc", _WIN / "meiryo.ttc", _WIN / "msgothic.ttc",
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),
]

ZH_CANDIDATES = [
    _WIN / "msyh.ttc", _WIN / "msyh.ttf", _WIN / "simhei.ttf", _WIN / "simsun.ttc",
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),
]


def font_candidates(override: str | None, candidates: list[Path]) -> list[Path]:
    """返回存在的字体路径（配置的优先）。

    路径会用 resolve() 换成磁盘上的真实大小写：Windows 的 WINDIR 常常是
    "C:\\WINDOWS"，而真实目录是 "C:\\Windows"，Panda3D 会因为大小写不一致而拒绝加载。
    """
    found: list[Path] = []
    if override:
        p = Path(override).expanduser()
        if p.exists():
            found.append(p)
        else:
            print(f"[字体] 配置里的字体不存在：{p}，改为自动查找", file=sys.stderr)
    for p in candidates:
        if p.exists():
            found.append(p)
    out: list[Path] = []
    for p in found:
        try:
            p = p.resolve()
        except OSError:
            pass
        if p not in out:
            out.append(p)
    return out
