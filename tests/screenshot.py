"""离屏截图检查各个画面（无需显示器）：python tests/screenshot.py 输出到 shots/"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jpcloze.app import ClozeApp, configure_window  # noqa: E402
from jpcloze.settings import DEFAULTS  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "shots"
OUT.mkdir(exist_ok=True)

configure_window("load-display p3tinydisplay\nwindow-type offscreen\naudio-library-name null\n")
cfg = dict(DEFAULTS)
cfg["db_path"] = str(Path(tempfile.mkdtemp()) / "shot.db")
cfg["round_size"] = 5
app = ClozeApp(cfg, persist_config=False)

# 造一些历史数据，让学习记录和今日复习有内容
qs = list(app.bank.questions.values())
now = time.time()
for d in range(13, -1, -1):
    for k in range(5 + (d * 7) % 25):
        q = qs[(d * 31 + k * 7) % len(qs)]
        app.store.record(q.id, (k + d) % 4 != 0, 2.0 + (d % 5) * 0.8 + (k % 3), ts=now - d * 86400 - 3600 - k)


def snap(name):
    for _ in range(3):
        app.graphicsEngine.renderFrame()
    app.win.saveScreenshot(str(OUT / f"{name}.png"))
    print("saved", name)


def find_q(pred):
    return next(q for q in app.bank.questions.values() if pred(q))


def run_one(q):
    app.round = [q]
    app.round_title = "测试"
    app.idx = 0
    app.show_question()


app.show_menu()
snap("01_menu")

# 选择模式：答错 → 自动展开知识卡
q = app.bank.questions["L5-004"]
run_one(q)
snap("02_choice_question")
app.on_number(next(i for i, o in enumerate(app.cur_opts) if o != q.answer))
snap("03_choice_wrong_card")
app.toggle_card()
snap("04_choice_wrong_card_off")

# 长选项（单列）
q = find_q(lambda q: max(len(o) for o in q.options) > 9 and q.context)
run_one(q)
snap("05_long_options")
app.on_number(app.cur_opts.index(q.answer))
snap("06_long_options_right")

# 打字模式
app.cfg["mode"] = "typing"
q = app.bank.questions["L2-038"]
run_one(q)
for ch in "furare":
    app.on_key(ch)
snap("07_typing_input")
for ch in "te":
    app.on_key(ch)
app.on_enter()
snap("08_typing_right")
q = app.bank.questions["L2-015"]
run_one(q)
for ch in "furetara":
    app.on_key(ch)
app.on_enter()
snap("09_typing_wrong_card")

# 听力模式
app.cfg["mode"] = "listening"
q = find_q(lambda q: q.context and "\n" in q.context)
run_one(q)
snap("10_listening_question")
app.on_number(0)
snap("11_listening_feedback")

# 其它画面
app.cfg["mode"] = "choice"
app.start_spec(("levels", [4]))
while app.state != "summary":
    if app.state == "question":
        app.on_number(0)
    else:
        app.on_next()
snap("12_summary")
app.show_menu()
snap("13_menu_after")
app.show_stats()
snap("14_stats")
app.show_settings()
app.on_arrow("arrow_down")
app.on_arrow("arrow_right")
snap("15_settings")
app.on_escape()
app.on_number(0)   # 今日复习
snap("16_review_question")
