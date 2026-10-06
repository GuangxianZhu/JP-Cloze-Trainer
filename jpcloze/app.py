"""Panda3D 界面。

画面：菜单 → 答题（选择 / 打字 / 听力）→ 反馈（知识卡）→ 本轮总结；另有 学习记录、设置。

按键：
  菜单    数字键开始 · M 切换模式 · T 学习记录 · S 设置 · Esc 退出
  答题    选择/听力：1~4 作答；打字：打罗马字，回车提交；听力：P 再听一遍；Esc 放弃本轮
  反馈    空格/回车 下一题 · E 知识卡 · P 再听一遍
  总结    空格 返回菜单 · R 再来一轮
"""
from __future__ import annotations

import math
import random
import sys
import time
from pathlib import Path

from direct.gui.DirectGui import DGG, DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (Filename, LineSegs, NodePath, TextNode, TextProperties,
                          TextPropertiesManager, loadPrcFileData)

from .bank import Bank, Question, load_bank
from .fonts import JA_CANDIDATES, ZH_CANDIDATES, font_candidates
from .romaji import convert, finalize, normalize_answer
from .settings import CHOICES, ROOT, cycle, load_config, save_config
from .store import Store
from .trainer import (MODE_LABEL, MODE_TIME_FACTOR, MODES, STATE_LABEL, RoundItem,
                      RoundSummary, daily_stats, due_questions, eligible, level_progress,
                      overall_tag_stats, pick_round, question_state, shuffled_options,
                      study_streak_days, time_limit, today_count)

# 配色
BG = (0.11, 0.12, 0.15, 1)
PANEL = (0.16, 0.17, 0.21, 1)
FG = (0.93, 0.93, 0.95, 1)
DIM = (0.60, 0.62, 0.68, 1)
ACCENT = (0.98, 0.78, 0.35, 1)
OK = (0.40, 0.85, 0.50, 1)
NG = (0.95, 0.42, 0.42, 1)
BTN = (0.20, 0.22, 0.28, 1)
BTN_HOVER = (0.27, 0.30, 0.38, 1)

NUM_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]


def configure_window(extra_prc: str = "") -> None:
    loadPrcFileData("", """
        window-title 日语语感训练 · 挖空选择题
        win-size 1280 720
        framebuffer-multisample 1
        multisamples 4
        sync-video 1
        vfs-case-sensitive 0
    """ + extra_prc)


def panda_path(p: Path) -> str:
    try:
        p = p.resolve()
    except OSError:
        pass
    return Filename.fromOsSpecific(str(p)).getFullpath()


class ClozeApp(ShowBase):
    def __init__(self, cfg: dict | None = None, persist_config: bool = True):
        super().__init__()
        self.cfg = cfg or load_config()
        self.persist_config = persist_config
        self.setBackgroundColor(*BG)
        self.disableMouse()

        self.font_ja = self._load_font(self.cfg.get("font_ja"), JA_CANDIDATES, "日文")
        self.font_zh = self._load_font(self.cfg.get("font_zh"), ZH_CANDIDATES, "中文") or self.font_ja
        self._setup_text_colors()

        self.bank: Bank = load_bank(ROOT / "data")
        db = Path(self.cfg["db_path"])
        self.store = Store(db if db.is_absolute() else ROOT / db)
        self.rng = random.Random()

        self.nodes: list = []
        self.state = "menu"
        self.round: list[Question] = []
        self.round_title = ""
        self.round_spec: tuple = ()
        self.idx = 0
        self.combo = 0
        self.summary = RoundSummary()
        self.cur_opts: list[str] = []
        self.opt_buttons: list[DirectButton] = []
        self.answer_nodes: list = []
        self.card_nodes: list = []
        self.card_shown = False
        self.q_start = 0.0
        self.q_limit: float | None = 15.0
        self.timer_fill = None
        self.typed = ""
        self.sound = None
        self.settings_sel = 0

        for i, k in enumerate(NUM_KEYS):
            self.accept(k, self.on_number, [i])
        self.accept("space", self.on_space)
        self.accept("enter", self.on_enter)
        self.accept("escape", self.on_escape)
        for k in ("arrow_up", "arrow_down", "arrow_left", "arrow_right"):
            self.accept(k, self.on_arrow, [k])
        if self.buttonThrowers:          # 离屏测试时没有键盘
            self.buttonThrowers[0].node().setKeystrokeEvent("keystroke")
        self.accept("keystroke", self.on_key)
        self.taskMgr.add(self._tick, "tick")

        self.show_menu()

    # ================= 基础 =================
    @property
    def mode(self) -> str:
        return self.cfg.get("mode", "choice") if self.cfg.get("mode") in MODES else "choice"

    def _load_font(self, override, candidates, label):
        for path in font_candidates(override, candidates):
            try:
                font = self.loader.loadFont(panda_path(path))
            except (OSError, IOError) as e:
                print(f"[字体] {label}字体加载失败，换下一个：{path}（{e}）", file=sys.stderr)
                continue
            font.setPixelsPerUnit(72)
            font.setPageSize(1024, 1024)
            return font
        print(f"[字体] 没找到可用的{label}字体，文字会显示成方块。请在 config.json 里设置字体路径。",
              file=sys.stderr)
        return None

    def _setup_text_colors(self):
        tpm = TextPropertiesManager.getGlobalPtr()
        for name, color in (("ok", OK), ("ng", NG), ("acc", ACCENT), ("dim", DIM), ("fg", FG)):
            tp = TextProperties()
            tp.setTextColor(*color)
            tpm.setProperties(name, tp)

    @staticmethod
    def c(name: str, text: str) -> str:
        return f"\1{name}\1{text}\2"

    def save_cfg(self):
        if self.persist_config:
            save_config(self.cfg)

    def clear(self):
        self.stop_sound()
        for n in self.nodes:
            if hasattr(n, "destroy"):
                n.destroy()
            else:
                n.removeNode()
        self.nodes = []
        self.opt_buttons = []
        self.answer_nodes = []
        self.card_nodes = []
        self.card_shown = False
        self.timer_fill = None

    def text(self, s, pos, scale=0.06, ja=False, fg=FG, align=TextNode.ALeft, wrap=None,
             group: list | None = None):
        t = OnscreenText(text=s, pos=pos, scale=scale, fg=fg, align=align,
                         font=self.font_ja if ja else self.font_zh, wordwrap=wrap, mayChange=True)
        self.nodes.append(t)
        if group is not None:
            group.append(t)
        return t

    @staticmethod
    def height(t: OnscreenText) -> float:
        return t.textNode.getHeight() * t.getScale()[1]

    def left(self) -> float:
        return -self.getAspectRatio() + 0.12

    def width(self) -> float:
        return 2 * self.getAspectRatio() - 0.24

    def footer(self, s: str, fg=DIM):
        return self.text(s, (self.left(), -0.92), 0.045, fg=fg)

    def toast(self, msg: str):
        t = self.text(msg, (0, -0.8), 0.06, fg=ACCENT, align=TextNode.ACenter)

        def _hide(task):
            try:
                t.setText("")
            except Exception:
                pass
            return task.done
        self.taskMgr.doMethodLater(2.5, _hide, "toast")

    # ---------- 声音 ----------
    def play(self, q: Question) -> float:
        """播放整句语音，返回时长（没有语音时返回 0）。"""
        self.stop_sound()
        info = self.bank.audio.get(q.id)
        if not info:
            return 0.0
        try:
            self.sound = self.loader.loadSfx(panda_path(info[0]))
            self.sound.play()
        except Exception as e:  # 没有声卡等
            print(f"[语音] 播放失败：{e}", file=sys.stderr)
            self.sound = None
        return info[1]

    def stop_sound(self):
        if self.sound is not None:
            try:
                self.sound.stop()
            except Exception:
                pass
            self.sound = None

    # ---------- 数据 ----------
    def history(self):
        return self.store.history()

    def pool(self, levels: list[int] | None = None) -> list[Question]:
        audio = set(self.bank.audio)
        return [q for q in self.bank.by_level(levels)
                if eligible(q, self.mode, self.bank.no_typing, audio)]

    # ================= 菜单 =================
    def show_menu(self):
        self.clear()
        self.state = "menu"
        hist = self.history()
        now = time.time()
        L = self.left()
        A = self.getAspectRatio()

        self.text("日语语感训练", (L, 0.84), 0.1, fg=ACCENT)
        done = today_count(hist, now)
        goal = int(self.cfg.get("daily_goal", 40))
        streak = study_streak_days(hist, now)
        goal_txt = self.c("ok", f"{done} / {goal} 题  已完成！") if done >= goal else f"{done} / {goal} 题"
        self.text(f"今天 {goal_txt}    连续学习 {streak} 天", (A - 0.12, 0.86), 0.05,
                  fg=DIM, align=TextNode.ARight)

        modes = "   ".join(self.c("acc", f"[{MODE_LABEL[m]}]") if m == self.mode
                           else MODE_LABEL[m] for m in MODES)
        self.text(f"模式：{modes}      M 切换", (L, 0.7), 0.055, fg=DIM)
        tips = {"choice": "四选一，凭感觉快速作答",
                "typing": "不给选项，打罗马字自动转假名（L3、L6 不参加）",
                "listening": "先只听不看，选出空里的词"}
        self.text(tips[self.mode], (L, 0.62), 0.045, fg=DIM)

        self.menu_choices: list[tuple] = []
        y = 0.47
        due = due_questions(self.pool(), hist, now)
        self.menu_choices.append(("review",))
        n_due = len(due)
        due_txt = self.c("acc", f"{n_due} 题到期") if n_due else "暂无到期的题"
        self.text(f"1   今日复习", (L, y), 0.062)
        self.text(due_txt, (L + 1.0, y), 0.05, fg=DIM)
        y -= 0.115

        for lv in self.bank.levels():
            qs = self.pool([lv])
            prog = level_progress(qs, hist)
            self.menu_choices.append(("levels", [lv]))
            n = len(self.menu_choices)
            self.text(f"{n}   {self.bank.titles[lv]}", (L, y), 0.062)
            if qs:
                self.text(f"{len(qs)} 题 · " + self.c("ok", f"有语感 {prog['fluent']}") +
                          f" · 练习中 {prog['learning'] + prog['slow']} · " +
                          self.c("ng", f"答错 {prog['weak']}") + f" · 新 {prog['new']}",
                          (L + 1.0, y), 0.045, fg=DIM)
            else:
                self.text("这个模式下没有题", (L + 1.0, y), 0.045, fg=DIM)
            y -= 0.115
        self.menu_choices.append(("levels", self.bank.levels()))
        self.text(f"{len(self.menu_choices)}   全部混合", (L, y), 0.062)
        y -= 0.13

        weak = [s for s in overall_tag_stats(self.bank.questions, hist) if s.n >= 3][:2]
        if weak:
            parts = []
            for s in weak:
                rt = "—" if math.isnan(s.avg_rt) else f"{s.avg_rt:.1f}秒"
                parts.append(f"{s.tag}（{s.accuracy:.0%}，{rt}）")
            self.text("最近弱项：" + "  ".join(parts), (L, y), 0.045, fg=DIM)

        self.footer("数字键开始 · M 切换模式 · T 学习记录 · S 设置 · Esc 退出")

    # ================= 答题 =================
    def start_spec(self, spec: tuple):
        hist = self.history()
        if spec[0] == "review":
            qs = due_questions(self.pool(), hist, time.time())[: int(self.cfg["round_size"])]
            if not qs:
                self.toast("今天没有到期要复习的题，先去做新题吧")
                return
            self.rng.shuffle(qs)
            title = "今日复习"
        else:
            levels = spec[1]
            pool = self.pool(levels)
            if not pool:
                self.toast("这个模式下没有题")
                return
            qs = pick_round(pool, hist, int(self.cfg["round_size"]), self.rng)
            title = self.bank.titles[levels[0]] if len(levels) == 1 else "全部混合"
        self.round_spec = spec
        self.round = qs
        self.round_title = title
        self.idx = 0
        self.combo = 0
        self.summary = RoundSummary()
        self.show_question()

    def show_question(self):
        self.clear()
        self.state = "question"
        q = self.round[self.idx]
        st = question_state(self.history().get(q.id, []))
        scale = float(self.cfg.get("time_scale", 1.0) or 0)
        self.q_limit = time_limit(st, scale) * MODE_TIME_FACTOR[self.mode] if scale > 0 else None
        L, A, W = self.left(), self.getAspectRatio(), self.width()

        combo = f" · 连对 {self.combo}" if self.combo >= 2 else ""
        self.text(f"{self.round_title} · 第 {self.idx + 1}/{len(self.round)} 题{combo}",
                  (L, 0.88), 0.05, fg=DIM)
        self.text(f"{MODE_LABEL[self.mode]} · {STATE_LABEL[st]}", (A - 0.12, 0.88), 0.05,
                  fg=DIM, align=TextNode.ARight)

        if self.q_limit:
            bar_bg = DirectFrame(frameColor=(0.2, 0.21, 0.25, 1), frameSize=(0, W, -0.012, 0.012),
                                 pos=(L, 0, 0.8))
            fill = DirectFrame(frameColor=ACCENT, frameSize=(0, W, -0.012, 0.012), pos=(L, 0, 0.8))
            self.nodes += [bar_bg, fill]
            self.timer_fill = fill

        y = 0.62
        if q.context:
            ct = self.text(q.context, (L, y), 0.06, ja=True, fg=DIM, wrap=W / 0.06)
            y -= self.height(ct) + 0.06
        y = min(y, 0.38)
        if self.mode == "listening":
            self.sentence_node = self.text("（先听，再选出空里的词）    P 再听一遍", (L, y), 0.07,
                                           fg=ACCENT, wrap=W / 0.07)
        else:
            self.sentence_node = self.text(q.with_blank(self.c("acc", "（　　　）")), (L, y), 0.09,
                                           ja=True, wrap=W / 0.09)
        self.sentence_y = y

        if self.mode == "typing":
            self._build_typing(q)
            self.hint_node = self.footer("打罗马字（tabete → たべて）· 回车 提交 · 退格 删除 · Esc 放弃本轮")
        else:
            self._build_options(q)
            extra = " · P 再听一遍" if self.mode == "listening" else ""
            self.hint_node = self.footer(f"按 1~4 作答（也可以点鼠标）{extra} · Esc 放弃本轮")

        if self.mode == "listening":
            dur = self.play(q)
            if self.q_limit:
                self.q_limit += dur
        self.q_start = self.clock.getFrameTime()

    def _build_options(self, q: Question):
        self.cur_opts = shuffled_options(q, self.rng)
        long_opt = max(len(o) for o in self.cur_opts) > 9
        for i, opt in enumerate(self.cur_opts):
            if long_opt:    # 长选项：一列四行
                x, y, half = 0.0, -0.02 - i * 0.175, self.getAspectRatio() - 0.15
                ts = 0.062
            else:
                x = -0.78 if i % 2 == 0 else 0.78
                y, half, ts = -0.12 - (i // 2) * 0.3, 0.7, 0.08
            b = DirectButton(text=f"{i + 1}    {opt}", text_font=self.font_ja, text_scale=ts,
                             text_fg=FG, text_align=TextNode.ALeft, text_pos=(-half + 0.08, -0.025),
                             frameSize=(-half, half, -0.075 if long_opt else -0.11,
                                        0.075 if long_opt else 0.11),
                             frameColor=(BTN, BTN_HOVER, BTN_HOVER, BTN),
                             relief=DGG.FLAT, pos=(x, 0, y),
                             command=self.answer, extraArgs=[i])
            self.nodes.append(b)
            self.opt_buttons.append(b)

    def _build_typing(self, q: Question):
        L, W = self.left(), self.width()
        self.typed = ""
        self.cur_opts = []
        if q.hint:
            self.text(f"提示：{q.hint}", (L, -0.02), 0.055, ja=True, fg=DIM, group=self.answer_nodes)
        box = DirectFrame(frameColor=BTN, frameSize=(0, W, -0.1, 0.1), pos=(L, 0, -0.25))
        self.nodes.append(box)
        self.answer_nodes.append(box)
        self.typed_node = self.text("", (L + 0.06, -0.28), 0.09, ja=True, group=self.answer_nodes)
        self.raw_node = self.text("", (L + W - 0.04, -0.29), 0.045, fg=DIM, align=TextNode.ARight,
                                  group=self.answer_nodes)
        self._refresh_typed()

    def _refresh_typed(self):
        kana = convert(self.typed)
        self.typed_node.setText(kana + self.c("acc", "|"))
        self.raw_node.setText(self.typed)

    def _tick(self, task):
        if self.state == "question" and self.timer_fill is not None and self.q_limit:
            elapsed = self.clock.getFrameTime() - self.q_start
            frac = max(0.0, 1.0 - elapsed / self.q_limit)
            self.timer_fill.setSx(max(frac, 0.0001))
            if frac < 0.3:
                self.timer_fill["frameColor"] = NG
            if elapsed >= self.q_limit:
                if self.mode == "typing":
                    self.submit_typing(timeout=True)
                else:
                    self.answer(None)
        return task.cont

    def _elapsed(self) -> float:
        rt = self.clock.getFrameTime() - self.q_start
        return min(rt, self.q_limit) if self.q_limit else rt

    def answer(self, i: int | None):
        if self.state != "question" or self.mode == "typing":
            return
        q = self.round[self.idx]
        chosen = None if i is None else self.cur_opts[i]
        self._finish(RoundItem(q, chosen, self._elapsed(), self.q_limit or 0), chosen_i=i)

    def submit_typing(self, timeout: bool = False):
        if self.state != "question" or self.mode != "typing":
            return
        q = self.round[self.idx]
        typed = normalize_answer(finalize(self.typed))
        if timeout and not typed:
            item = RoundItem(q, None, self._elapsed(), self.q_limit or 0, ok=False)
        else:
            if not typed:
                return      # 空着回车不算
            item = RoundItem(q, typed, self._elapsed(), self.q_limit or 0,
                             ok=typed in q.typing_answers())
        self._finish(item, chosen_i=None)

    def _finish(self, item: RoundItem, chosen_i: int | None):
        self.summary.items.append(item)
        self.store.record(item.question.id, item.correct, item.rt, item.timed_out, self.mode)
        self.combo = self.combo + 1 if item.correct else 0
        self.show_feedback(item, chosen_i)

    # ================= 反馈 =================
    def show_feedback(self, item: RoundItem, chosen_i: int | None):
        self.state = "feedback"
        q = item.question
        L, W = self.left(), self.width()
        if self.timer_fill is not None:
            self.timer_fill.hide()

        if self.mode == "listening":
            self.sentence_node["scale"] = 0.09
            self.sentence_node["font"] = self.font_ja
            self.sentence_node["wordwrap"] = W / 0.09
            self.sentence_node["fg"] = FG
        self.sentence_node.setText(q.filled("\1ok\1", "\2"))

        if item.timed_out:
            verdict = self.c("ng", "时间到")
        elif item.correct:
            fast = "  很快！" if item.rt <= 3.0 else ""
            verdict = self.c("ok", f"正确 · {item.rt:.1f} 秒{fast}")
        else:
            verdict = self.c("ng", f"不对 · {item.rt:.1f} 秒")
        if self.mode == "typing" and item.chosen:
            verdict += "    你打的：" + self.c("ok" if item.correct else "ng", item.chosen)
        self.text(verdict, (L, 0.72), 0.058)

        if self.mode == "typing":
            for n in self.answer_nodes:
                n.hide()
            ans = q.answer if not q.reading else f"{q.answer}（{q.reading}）"
            g: list = []
            self.text("正确答案：" + self.c("ok", ans), (L, -0.05), 0.065, ja=True, group=g)
            self.answer_nodes = g
        else:
            for j, b in enumerate(self.opt_buttons):
                b["state"] = DGG.DISABLED
                if self.cur_opts[j] == q.answer:
                    b["frameColor"] = (0.18, 0.40, 0.24, 1)
                elif j == chosen_i:
                    b["frameColor"] = (0.45, 0.18, 0.18, 1)
                else:
                    b["text_fg"] = DIM

        self.explain_node = self.text(q.explain, (L, -0.69), 0.05, wrap=W / 0.05)

        has_card = self.bank.card_for(q) is not None
        tail = " · P 再听一遍" if q.id in self.bank.audio else ""
        self.hint_node.setText(("E 知识卡 · " if has_card else "") +
                               f"先在心里把整句默读一遍，再按 空格 继续{tail}")
        self.hint_node.setFg(ACCENT)

        if not item.correct and has_card:
            self.toggle_card()
        if self.cfg.get("voice", True):
            self.play(q)

    def toggle_card(self):
        if self.state != "feedback":
            return
        q = self.round[self.idx]
        card = self.bank.card_for(q)
        if card is None:
            return
        if self.card_shown:
            for n in self.card_nodes:
                n.destroy()
                if n in self.nodes:
                    self.nodes.remove(n)
            self.card_nodes = []
            for n in self.opt_buttons + self.answer_nodes:
                n.show()
            self.explain_node.show()
            self.card_shown = False
            return

        for n in self.opt_buttons + self.answer_nodes:
            n.hide()
        self.explain_node.hide()
        L, W = self.left(), self.width()
        top = min(0.2, self.sentence_y - self.height(self.sentence_node) - 0.02)
        panel = DirectFrame(frameColor=PANEL, frameSize=(-0.05, W + 0.05, -0.86 - top, 0.02),
                            pos=(L, 0, top))
        self.nodes.append(panel)
        self.card_nodes.append(panel)
        g = self.card_nodes
        y = top - 0.07
        t = self.text("本题：" + q.explain, (L, y), 0.05, wrap=W / 0.05, group=g)
        y -= self.height(t) + 0.05
        t = self.text(self.c("acc", f"知识卡 · {card.title}"), (L, y), 0.055, group=g)
        y -= self.height(t) + 0.035
        t = self.text(card.rule, (L, y), 0.047, wrap=W / 0.047, group=g)
        y -= self.height(t) + 0.04
        for ja, zh in card.examples:
            if y < -0.7:
                break
            t = self.text(ja, (L + 0.04, y), 0.055, ja=True, group=g)
            t2 = self.text(zh, (L + 0.06 + t.textNode.getWidth() * 0.055 + 0.05, y), 0.042,
                           fg=DIM, group=g)
            y -= max(self.height(t), self.height(t2)) + 0.03
        if card.pitfall and y > -0.8:
            self.text(self.c("ng", "易错：") + card.pitfall, (L, y - 0.01), 0.045,
                      wrap=W / 0.045, group=g)
        self.card_shown = True

    # ================= 总结 =================
    def show_summary(self):
        self.clear()
        self.state = "summary"
        s = self.summary
        L, W = self.left(), self.width()
        hist = self.history()
        self.text(f"本轮结束 · {self.round_title} · {MODE_LABEL[self.mode]}", (L, 0.82), 0.08, fg=ACCENT)
        rt = "—" if math.isnan(s.avg_rt_correct) else f"{s.avg_rt_correct:.1f} 秒"
        self.text(f"正确 {s.n_correct}/{s.n}    答对平均 {rt}    3 秒内答对 {s.n_fast} 题",
                  (L, 0.68), 0.06)
        done = today_count(hist, time.time())
        goal = int(self.cfg.get("daily_goal", 40))
        msg = self.c("ok", "今日目标完成！") if done >= goal else f"还差 {goal - done} 题"
        self.text(f"今天已做 {done} / {goal} 题  {msg}", (L, 0.58), 0.05, fg=DIM)

        y = 0.45
        self.text("各类题目（弱的在前）", (L, y), 0.05, fg=DIM)
        y -= 0.085
        for t in s.tag_stats()[:5]:
            rt = "—" if math.isnan(t.avg_rt) else f"{t.avg_rt:.1f} 秒"
            color = "ok" if t.accuracy >= 0.85 else ("ng" if t.accuracy < 0.6 else "acc")
            self.text(t.tag, (L + 0.05, y), 0.048)
            self.text(self.c(color, f"{t.correct}/{t.n}") + f"   {rt}", (L + 1.6, y), 0.048)
            y -= 0.07

        wrong = [i for i in s.items if not i.correct]
        if wrong:
            y -= 0.03
            self.text("答错的句子", (L, y), 0.05, fg=DIM)
            y -= 0.085
            for it in wrong[:4]:
                t = self.text(it.question.filled("\1ok\1", "\2"), (L + 0.05, y), 0.055, ja=True,
                              wrap=(W - 0.1) / 0.055)
                y -= self.height(t) + 0.025
            if len(wrong) > 4:
                self.text(f"…还有 {len(wrong) - 4} 题，会进入今日复习", (L + 0.05, y), 0.045, fg=DIM)
        self.footer("空格 返回菜单 · R 再来一轮", fg=ACCENT)

    # ================= 学习记录 =================
    def show_stats(self):
        self.clear()
        self.state = "stats"
        hist = self.history()
        now = time.time()
        L, W = self.left(), self.width()
        total = sum(len(v) for v in hist.values())
        self.text("学习记录", (L, 0.84), 0.09, fg=ACCENT)
        self.text(f"累计 {total} 题 · 连续学习 {study_streak_days(hist, now)} 天 · "
                  f"今天 {today_count(hist, now)} 题", (L, 0.72), 0.05, fg=DIM)

        days = daily_stats(hist, 14, now)
        # --- 每天题数（柱）---
        top, bottom = 0.56, 0.12
        self.text("每天做题数（颜色 = 正确率）", (L, 0.6), 0.045, fg=DIM)
        mx = max([d.n for d in days] + [10])
        bw = W / len(days)
        for i, d in enumerate(days):
            x = L + i * bw
            h = (top - bottom) * d.n / mx
            if d.n:
                col = OK if d.accuracy >= 0.85 else (NG if d.accuracy < 0.6 else ACCENT)
                bar = DirectFrame(frameColor=col, frameSize=(0, bw * 0.7, 0, h),
                                  pos=(x + bw * 0.15, 0, bottom))
                self.nodes.append(bar)
                self.text(str(d.n), (x + bw * 0.5, bottom + h + 0.015), 0.035, fg=DIM,
                          align=TextNode.ACenter)
            if i % 2 == 1 or i == len(days) - 1:
                self.text(d.day[5:].replace("-", "/"), (x + bw * 0.5, bottom - 0.05), 0.033,
                          fg=DIM, align=TextNode.ACenter)

        # --- 答对平均用时（折线）---
        top2, bottom2 = -0.2, -0.62
        self.text("答对平均用时（秒，越低越好）", (L, -0.1), 0.045, fg=DIM)
        pts = [(L + (i + 0.5) * bw, d.avg_rt) for i, d in enumerate(days) if not math.isnan(d.avg_rt)]
        ymax = max([p[1] for p in pts] + [8.0])
        axis = LineSegs()
        axis.setColor(0.3, 0.32, 0.38, 1)
        axis.moveTo(L, 0, bottom2)
        axis.drawTo(L + W, 0, bottom2)
        for sec in (3.0,):      # 3 秒参考线（语感线）
            yy = bottom2 + (top2 - bottom2) * sec / ymax
            axis.moveTo(L, 0, yy)
            axis.drawTo(L + W, 0, yy)
            self.text("3 秒", (L + W, yy + 0.01), 0.032, fg=DIM, align=TextNode.ARight)
        np_axis = NodePath(axis.create())
        np_axis.reparentTo(self.aspect2d)
        self.nodes.append(np_axis)
        if pts:
            ls = LineSegs()
            ls.setThickness(2.5)
            ls.setColor(*ACCENT)
            for j, (x, v) in enumerate(pts):
                yy = bottom2 + (top2 - bottom2) * v / ymax
                (ls.moveTo if j == 0 else ls.drawTo)(x, 0, yy)
            np_line = NodePath(ls.create())
            np_line.reparentTo(self.aspect2d)
            self.nodes.append(np_line)
            for x, v in pts:
                yy = bottom2 + (top2 - bottom2) * v / ymax
                self.text(f"{v:.1f}", (x, yy + 0.025), 0.032, fg=FG, align=TextNode.ACenter)
        else:
            self.text("还没有数据", (L + W / 2, (top2 + bottom2) / 2), 0.05, fg=DIM,
                      align=TextNode.ACenter)

        # --- 各级别掌握度 ---
        parts = []
        for lv in self.bank.levels():
            qs = self.bank.by_level([lv])
            prog = level_progress(qs, hist)
            parts.append(f"L{lv} " + self.c("ok", str(prog["fluent"])) + f"/{len(qs)}")
        self.text("有语感的题：" + "   ".join(parts), (L, -0.74), 0.048)
        self.footer("空格 / Esc 返回")

    # ================= 设置 =================
    def show_settings(self):
        self.clear()
        self.state = "settings"
        L = self.left()
        self.text("设置", (L, 0.84), 0.09, fg=ACCENT)
        y = 0.55
        for i, (key, label, _, fmt) in enumerate(CHOICES):
            sel = i == self.settings_sel
            if sel:
                hl = DirectFrame(frameColor=BTN, frameSize=(-0.04, 1.9, -0.045, 0.085), pos=(L, 0, y))
                self.nodes.append(hl)
            self.text(label, (L, y), 0.06, fg=FG if sel else DIM)
            val = fmt(self.cfg.get(key))
            self.text(("◀  " if sel else "") + self.c("acc" if sel else "fg", val) + ("  ▶" if sel else ""),
                      (L + 1.0, y), 0.06)
            y -= 0.17
        self.text("时限：练熟的题时限会自动缩短；觉得太紧就调大倍率。\n"
                  "答完自动朗读：答完播放整句语音（任何时候都可以按 P 重听）。",
                  (L, y - 0.05), 0.045, fg=DIM)
        self.footer("↑↓ 选择 · ←→ 修改 · Esc 保存并返回")

    # ================= 按键 =================
    def on_number(self, i: int):
        if self.state == "menu":
            if i < len(self.menu_choices):
                self.start_spec(self.menu_choices[i])
        elif self.state == "question" and self.mode != "typing":
            if i < len(self.cur_opts):
                self.answer(i)

    def on_space(self):
        if self.state in ("feedback", "summary"):
            self.on_next()
        elif self.state == "stats":
            self.show_menu()

    def on_enter(self):
        if self.state == "question" and self.mode == "typing":
            self.submit_typing()
        elif self.state == "settings":
            key = CHOICES[self.settings_sel][0]
            cycle(self.cfg, key, 1)
            self.show_settings()
        else:
            self.on_space()

    def on_next(self):
        if self.state == "feedback":
            self.idx += 1
            if self.idx >= len(self.round):
                self.show_summary()
            else:
                self.show_question()
        elif self.state == "summary":
            self.show_menu()

    def on_arrow(self, k: str):
        if self.state != "settings":
            return
        if k == "arrow_up":
            self.settings_sel = (self.settings_sel - 1) % len(CHOICES)
        elif k == "arrow_down":
            self.settings_sel = (self.settings_sel + 1) % len(CHOICES)
        else:
            cycle(self.cfg, CHOICES[self.settings_sel][0], -1 if k == "arrow_left" else 1)
        self.show_settings()

    def on_key(self, ch: str):
        """字符输入：打字模式下是答案，其他画面是快捷键。"""
        if self.state == "question" and self.mode == "typing":
            if ch == "\b":
                self.typed = self.typed[:-1]
            elif len(ch) == 1 and (ch.isascii() and (ch.isalpha() or ch in "-'")):
                if len(self.typed) < 40:
                    self.typed += ch.lower()
            else:
                return
            self._refresh_typed()
            return
        k = ch.lower()
        if self.state == "menu":
            if k == "m":
                self.cfg["mode"] = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
                self.save_cfg()
                self.show_menu()
            elif k == "t":
                self.show_stats()
            elif k == "s":
                self.settings_sel = 0
                self.show_settings()
        elif self.state == "feedback":
            if k == "e":
                self.toggle_card()
            elif k == "p":
                self.play(self.round[self.idx])
        elif self.state == "question" and self.mode == "listening" and k == "p":
            self.play(self.round[self.idx])
        elif self.state == "summary" and k == "r" and self.round_spec:
            self.start_spec(self.round_spec)

    def on_escape(self):
        if self.state == "menu":
            self.stop_sound()
            self.store.close()
            self.userExit()
        elif self.state == "settings":
            self.save_cfg()
            self.show_menu()
        elif self.state == "question" or self.state == "feedback":
            # 中途放弃：已经答过的题也给个总结
            if self.summary.items:
                self.show_summary()
            else:
                self.show_menu()
        else:
            self.show_menu()


def main():
    configure_window()
    ClozeApp().run()
