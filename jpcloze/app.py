"""Panda3D 界面：菜单 → 限时答题 → 反馈 → 本轮总结。

操作：
  菜单    数字键选择级别，Esc 退出
  答题    1~4 选答案（也可以点鼠标），Esc 放弃本轮
  反馈    空格 / 回车 下一题
  总结    空格 返回菜单，R 同级别再来一轮
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from direct.gui.DirectGui import DGG, DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (Filename, TextNode, TextProperties, TextPropertiesManager,
                          loadPrcFileData)

from .bank import Bank, Question, load_bank
from .fonts import JA_CANDIDATES, ZH_CANDIDATES, find_font
from .store import Store
from .trainer import (STATE_LABEL, RoundItem, RoundSummary, level_progress,
                      overall_tag_stats, pick_round, question_state, shuffled_options,
                      time_limit)

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG = {
    "round_size": 20,      # 每轮题数
    "time_scale": 1.0,     # 时限倍率：觉得太紧就调大，比如 1.5
    "font_ja": "",         # 留空自动查找
    "font_zh": "",
    "db_path": "progress.db",
}

# 配色
BG = (0.11, 0.12, 0.15, 1)
FG = (0.93, 0.93, 0.95, 1)
DIM = (0.60, 0.62, 0.68, 1)
ACCENT = (0.98, 0.78, 0.35, 1)
OK = (0.40, 0.85, 0.50, 1)
NG = (0.95, 0.42, 0.42, 1)
BTN = (0.20, 0.22, 0.28, 1)
BTN_HOVER = (0.27, 0.30, 0.38, 1)

KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = ROOT / "config.json"
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError) as e:
            print(f"[配置] config.json 读取失败，使用默认值：{e}", file=sys.stderr)
    return cfg


def configure_window(extra_prc: str = "") -> None:
    loadPrcFileData("", """
        window-title 日语语感训练 · 挖空选择题
        win-size 1280 720
        framebuffer-multisample 1
        multisamples 4
        sync-video 1
    """ + extra_prc)


class ClozeApp(ShowBase):
    def __init__(self, cfg: dict | None = None):
        super().__init__()
        self.cfg = cfg or load_config()
        self.setBackgroundColor(*BG)
        self.disableMouse()

        self.font_ja = self._load_font(self.cfg.get("font_ja"), JA_CANDIDATES, "日文")
        self.font_zh = self._load_font(self.cfg.get("font_zh"), ZH_CANDIDATES, "中文")
        self._setup_text_colors()

        self.bank: Bank = load_bank(ROOT / "data")
        db = Path(self.cfg["db_path"])
        self.store = Store(db if db.is_absolute() else ROOT / db)
        self.rng = random.Random()

        self.nodes: list = []          # 当前画面上的元素
        self.state = "menu"
        self.levels: list[int] = []
        self.round: list[Question] = []
        self.idx = 0
        self.combo = 0
        self.summary = RoundSummary()
        self.cur_opts: list[str] = []
        self.opt_buttons: list[DirectButton] = []
        self.q_start = 0.0
        self.q_limit = 15.0
        self.timer_fill = None

        for i, k in enumerate(KEYS):
            self.accept(k, self.on_number, [i])
        for k in ("space", "enter"):
            self.accept(k, self.on_next)
        self.accept("r", self.on_retry)
        self.accept("escape", self.on_escape)
        self.taskMgr.add(self._tick, "tick")

        self.show_menu()

    # ---------- 基础 ----------
    def _load_font(self, override, candidates, label):
        path = find_font(override, candidates)
        if path is None:
            print(f"[字体] 没找到{label}字体，文字会显示成方块。请在 config.json 里设置字体路径。",
                  file=sys.stderr)
            return None
        font = self.loader.loadFont(Filename.fromOsSpecific(str(path)).getFullpath())
        font.setPixelsPerUnit(72)
        font.setPageSize(1024, 1024)
        return font

    def _setup_text_colors(self):
        tpm = TextPropertiesManager.getGlobalPtr()
        for name, color in (("ok", OK), ("ng", NG), ("acc", ACCENT), ("dim", DIM)):
            tp = TextProperties()
            tp.setTextColor(*color)
            tpm.setProperties(name, tp)

    @staticmethod
    def c(name: str, text: str) -> str:
        """给一段文字上色（OnscreenText 内联标记）。"""
        return f"\1{name}\1{text}\2"

    def clear(self):
        for n in self.nodes:
            n.destroy()
        self.nodes = []
        self.opt_buttons = []
        self.timer_fill = None

    def text(self, s, pos, scale=0.06, ja=False, fg=FG, align=TextNode.ALeft, wrap=None):
        t = OnscreenText(text=s, pos=pos, scale=scale, fg=fg, align=align,
                         font=self.font_ja if ja else self.font_zh, wordwrap=wrap,
                         mayChange=True)
        self.nodes.append(t)
        return t

    def left(self) -> float:
        return -self.getAspectRatio() + 0.12

    # ---------- 菜单 ----------
    def show_menu(self):
        self.clear()
        self.state = "menu"
        history = self.store.history()
        L = self.left()
        self.text("日语语感训练", (L, 0.78), 0.11, fg=ACCENT)
        self.text("挖空选择题 · 凭感觉又快又对才算语感", (L, 0.66), 0.055, fg=DIM)

        self.menu_choices: list[list[int]] = []
        y = 0.45
        for lv in self.bank.levels():
            qs = self.bank.by_level([lv])
            prog = level_progress(qs, history)
            self.menu_choices.append([lv])
            n = len(self.menu_choices)
            self.text(f"{n}   {self.bank.titles[lv]}", (L, y), 0.075)
            self.text(f"{len(qs)} 题 · " + self.c("ok", f"有语感 {prog['fluent']}") +
                      f" · 练习中 {prog['learning'] + prog['slow']} · " +
                      self.c("ng", f"答错过 {prog['weak']}") + f" · 新题 {prog['new']}",
                      (L + 0.12, y - 0.08), 0.048, fg=DIM)
            y -= 0.22
        if len(self.bank.levels()) > 1:
            self.menu_choices.append(self.bank.levels())
            self.text(f"{len(self.menu_choices)}   全部混合", (L, y), 0.075)
            y -= 0.22

        weak = [s for s in overall_tag_stats(self.bank.questions, history) if s.n >= 3][:4]
        if weak:
            self.text("最近的弱项", (L, y - 0.02), 0.055, fg=ACCENT)
            y -= 0.1
            for s in weak:
                rt = "—" if math.isnan(s.avg_rt) else f"{s.avg_rt:.1f} 秒"
                self.text(f"{s.tag}    正确率 {s.accuracy:.0%} · 平均 {rt}", (L + 0.05, y), 0.048)
                y -= 0.07
        self.text("按数字键开始 · Esc 退出", (L, -0.92), 0.045, fg=DIM)

    # ---------- 答题 ----------
    def start_round(self, levels: list[int]):
        self.levels = levels
        qs = self.bank.by_level(levels)
        self.round = pick_round(qs, self.store.history(), self.cfg["round_size"], self.rng)
        self.idx = 0
        self.combo = 0
        self.summary = RoundSummary()
        self.show_question()

    def round_title(self) -> str:
        if len(self.levels) == 1:
            return self.bank.titles[self.levels[0]]
        return "全部混合"

    def show_question(self):
        self.clear()
        self.state = "question"
        q = self.round[self.idx]
        hist = self.store.history().get(q.id, [])
        st = question_state(hist)
        self.q_limit = time_limit(st, float(self.cfg["time_scale"]))
        L = self.left()
        A = self.getAspectRatio()

        combo = f" · 连对 {self.combo}" if self.combo >= 2 else ""
        self.text(f"{self.round_title()} · 第 {self.idx + 1}/{len(self.round)} 题{combo}",
                  (L, 0.88), 0.05, fg=DIM)
        self.text(STATE_LABEL[st], (A - 0.12, 0.88), 0.05, fg=DIM, align=TextNode.ARight)

        # 倒计时条
        w = 2 * A - 0.24
        bar_bg = DirectFrame(frameColor=(0.2, 0.21, 0.25, 1), frameSize=(0, w, -0.012, 0.012),
                             pos=(L, 0, 0.8))
        fill = DirectFrame(frameColor=ACCENT, frameSize=(0, w, -0.012, 0.012), pos=(L, 0, 0.8))
        self.nodes += [bar_bg, fill]
        self.timer_fill = fill

        if q.context:
            self.text(q.context, (L, 0.58), 0.07, ja=True, fg=DIM, wrap=(2 * A - 0.3) / 0.07)
        self.sentence_node = self.text(q.with_blank(self.c("acc", "（　　　）")), (L, 0.36),
                                       0.1, ja=True, wrap=(2 * A - 0.3) / 0.1)

        self.cur_opts = shuffled_options(q, self.rng)
        for i, opt in enumerate(self.cur_opts):
            col, row = i % 2, i // 2
            x = -0.78 if col == 0 else 0.78
            y = -0.12 - row * 0.3
            b = DirectButton(text=f"{i + 1}    {opt}", text_font=self.font_ja, text_scale=0.08,
                             text_fg=FG, text_align=TextNode.ALeft, text_pos=(-0.62, -0.025),
                             frameSize=(-0.7, 0.7, -0.11, 0.11),
                             frameColor=(BTN, BTN_HOVER, BTN_HOVER, BTN),
                             relief=DGG.FLAT, pos=(x, 0, y),
                             command=self.answer, extraArgs=[i])
            self.nodes.append(b)
            self.opt_buttons.append(b)

        self.hint_node = self.text("按 1~4 作答（也可以点鼠标）", (L, -0.92), 0.045, fg=DIM)
        self.q_start = self.clock.getFrameTime()

    def _tick(self, task):
        if self.state == "question" and self.timer_fill is not None:
            elapsed = self.clock.getFrameTime() - self.q_start
            frac = max(0.0, 1.0 - elapsed / self.q_limit)
            self.timer_fill.setSx(max(frac, 0.0001))
            if frac < 0.3:
                self.timer_fill["frameColor"] = NG
            if elapsed >= self.q_limit:
                self.answer(None)
        return task.cont

    def answer(self, i: int | None):
        if self.state != "question":
            return
        rt = self.clock.getFrameTime() - self.q_start
        q = self.round[self.idx]
        chosen = None if i is None else self.cur_opts[i]
        rt = min(rt, self.q_limit)
        item = RoundItem(q, chosen, rt, self.q_limit)
        self.summary.items.append(item)
        self.store.record(q.id, item.correct, rt, item.timed_out)
        self.combo = self.combo + 1 if item.correct else 0
        self.show_feedback(item, i)

    def show_feedback(self, item: RoundItem, chosen_i: int | None):
        self.state = "feedback"
        q = item.question
        L = self.left()
        A = self.getAspectRatio()
        if self.timer_fill is not None:
            self.timer_fill.hide()

        # 句子换成填好答案的完整句
        self.sentence_node.setText(q.filled("\1ok\1", "\2"))

        for j, b in enumerate(self.opt_buttons):
            b["state"] = DGG.DISABLED
            if self.cur_opts[j] == q.answer:
                b["frameColor"] = (0.18, 0.40, 0.24, 1)
            elif j == chosen_i:
                b["frameColor"] = (0.45, 0.18, 0.18, 1)
            else:
                b["text_fg"] = DIM

        if item.timed_out:
            verdict = self.c("ng", "时间到")
        elif item.correct:
            fast = "  很快！" if item.rt <= 3.0 else ""
            verdict = self.c("ok", f"正确 · {item.rt:.1f} 秒{fast}")
        else:
            verdict = self.c("ng", f"不对 · {item.rt:.1f} 秒")
        self.text(verdict, (L, 0.68), 0.06)

        self.text(q.explain, (L, -0.72), 0.055, wrap=(2 * A - 0.3) / 0.055)
        self.hint_node.setText("先在心里把整句默读一遍，再按 空格 继续")
        self.hint_node.setFg(ACCENT)

    def on_next(self):
        if self.state == "feedback":
            self.idx += 1
            if self.idx >= len(self.round):
                self.show_summary()
            else:
                self.show_question()
        elif self.state == "summary":
            self.show_menu()

    # ---------- 总结 ----------
    def show_summary(self):
        self.clear()
        self.state = "summary"
        s = self.summary
        L = self.left()
        A = self.getAspectRatio()
        self.text(f"本轮结束 · {self.round_title()}", (L, 0.82), 0.08, fg=ACCENT)
        rt = "—" if math.isnan(s.avg_rt_correct) else f"{s.avg_rt_correct:.1f} 秒"
        self.text(f"正确 {s.n_correct}/{s.n}    答对平均 {rt}    3 秒内答对 {s.n_fast} 题",
                  (L, 0.68), 0.06)

        y = 0.52
        self.text("各类题目（弱的在前）", (L, y), 0.055, fg=DIM)
        y -= 0.09
        for t in s.tag_stats()[:6]:
            rt = "—" if math.isnan(t.avg_rt) else f"{t.avg_rt:.1f} 秒"
            color = "ok" if t.accuracy >= 0.85 else ("ng" if t.accuracy < 0.6 else "acc")
            self.text(f"{t.tag}", (L + 0.05, y), 0.05)
            self.text(self.c(color, f"{t.correct}/{t.n}") + f"   {rt}", (L + 1.1, y), 0.05)
            y -= 0.075

        wrong = [i for i in s.items if not i.correct]
        if wrong:
            y -= 0.04
            self.text("答错的句子", (L, y), 0.055, fg=DIM)
            y -= 0.09
            for it in wrong[:4]:
                self.text(it.question.filled("\1ok\1", "\2"), (L + 0.05, y), 0.06, ja=True,
                          wrap=(2 * A - 0.4) / 0.06)
                y -= 0.09
            if len(wrong) > 4:
                self.text(f"…还有 {len(wrong) - 4} 题，下一轮会优先出现", (L + 0.05, y), 0.045, fg=DIM)

        self.text("空格 返回菜单 · R 同级别再来一轮", (L, -0.92), 0.045, fg=ACCENT)

    # ---------- 按键 ----------
    def on_number(self, i: int):
        if self.state == "menu":
            if i < len(self.menu_choices):
                self.start_round(self.menu_choices[i])
        elif self.state == "question":
            if i < len(self.cur_opts):
                self.answer(i)

    def on_retry(self):
        if self.state == "summary":
            self.start_round(self.levels)

    def on_escape(self):
        if self.state == "menu":
            self.store.close()
            self.userExit()
        else:
            self.show_menu()


def main():
    configure_window()
    ClozeApp().run()
