"""设置：保存在项目根目录的 config.json（不进 git）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    "round_size": 20,      # 每轮题数
    "time_scale": 1.0,     # 时限倍率；0 = 不限时
    "voice": True,         # 答完自动朗读整句
    "daily_goal": 40,      # 每日目标题数
    "mode": "choice",      # 上次用的模式
    "font_ja": "",         # 留空自动查找
    "font_zh": "",
    "db_path": "progress.db",
}

# 设置界面里可以调的项：(键, 名称, 可选值, 显示函数)
CHOICES = [
    ("time_scale", "时限", [0.75, 1.0, 1.5, 2.0, 0],
     lambda v: "不限时" if not v else f"× {v:g}"),
    ("round_size", "每轮题数", [10, 20, 30, 50], lambda v: f"{v} 题"),
    ("daily_goal", "每日目标", [20, 40, 60, 100, 150], lambda v: f"{v} 题"),
    ("voice", "答完自动朗读", [True, False], lambda v: "开" if v else "关"),
]


def load_config(path: Path = CONFIG_PATH) -> dict:
    cfg = dict(DEFAULTS)
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError) as e:
            print(f"[配置] config.json 读取失败，使用默认值：{e}", file=sys.stderr)
    return cfg


def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    try:
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[配置] 保存失败：{e}", file=sys.stderr)


def cycle(cfg: dict, key: str, step: int) -> None:
    for k, _, values, _ in CHOICES:
        if k == key:
            try:
                i = values.index(cfg.get(k))
            except ValueError:
                i = 0
            cfg[k] = values[(i + step) % len(values)]
            return
