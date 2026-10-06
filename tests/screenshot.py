"""离屏截图检查各个画面（无需显示器）：python tests/screenshot.py 输出到 shots/"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jpcloze.app import ClozeApp, configure_window, load_config  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "shots"
OUT.mkdir(exist_ok=True)

configure_window("load-display p3tinydisplay\nwindow-type offscreen\naudio-library-name null\n")
cfg = load_config()
cfg["db_path"] = str(Path(tempfile.mkdtemp()) / "shot.db")
cfg["round_size"] = 5
app = ClozeApp(cfg)


def snap(name):
    for _ in range(3):
        app.graphicsEngine.renderFrame()
    app.win.saveScreenshot(str(OUT / f"{name}.png"))
    print("saved", name)


snap("1_menu")
app.on_number(0)
snap("2_question")
q = app.round[0]
wrong = next(i for i, o in enumerate(app.cur_opts) if o != q.answer)
app.on_number(wrong)
snap("3_feedback_wrong")
app.on_next()
right = app.cur_opts.index(app.round[1].answer)
app.on_number(right)
snap("4_feedback_right")
while app.state != "summary":
    app.on_next()
    if app.state == "question":
        app.on_number(0)
snap("5_summary")
app.on_next()
snap("6_menu_after")
# 找一个有上下文的题看排版
ctx = next(q for q in app.bank.questions.values() if q.context and len(q.sentence) > 20)
app.round = [ctx]
app.idx = 0
app.show_question()
snap("7_context_question")
# 长句换行检查
from jpcloze.bank import Question  # noqa: E402
long_q = Question("T-1", 1, ("测试",), "これは折り返しの確認のための、とても長い文で、画面の幅を超えたときにちゃんと次の行に送られるかどうかを見る{blank}めのテストです。",
                  ("た", "で", "に", "を"), "这是一段很长的中文解释，用来检查解释文字在超过屏幕宽度时能不能正确换行，而不会跑到屏幕外面去，也不会和别的元素重叠在一起。", "")
app.round = [long_q]
app.idx = 0
app.show_question()
app.on_number(app.cur_opts.index("で"))
snap("8_long_wrap")
