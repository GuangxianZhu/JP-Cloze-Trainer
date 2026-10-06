# JP-Cloze-Trainer · 日语语感训练（挖空选择题）

纯 Python + Panda3D。不用开口，靠大量限时挖空选择题练语感：**又快又对**才算有语感。

## 运行（Windows）

**双击 `start.bat`** 就行。第一次会自动创建虚拟环境 `.venv` 并安装 Panda3D（需要联网，一两分钟），之后双击直接启动。
需要先装好 Python 3.10+（安装时勾选 "Add python.exe to PATH"）。

手动运行也可以：

```bat
pip install -r requirements.txt
python main.py
```

字体会自动从 `C:\Windows\Fonts` 查找：日文用 Yu Gothic / Meiryo，中文用微软雅黑。
找不到的话，把 `config.example.json` 复制成 `config.json`，在 `font_ja` / `font_zh` 里填字体路径。

## 功能

- **6 个级别、272 题**：L1 助词 · L2 活用・接续 · L3 固定搭配 · L4 视角・语气 · L5 职场敬語（邮件 / 会议报告 / 电话 / 客户外包 / 同事闲聊）· L6 最自然
- **三种模式**（菜单按 M 切换）
  - 选择：四选一
  - 打字：不给选项，打罗马字自动转假名（tabete → たべて），不依赖输入法。L3、L6 和同音题不参加
  - 听力：先只听不看，选出空里的词
- **知识卡**：答错自动展开（规则 + 例句 + 易错点），答对按 E 查看
- **语音**：每句都有朗读，答完自动播放，P 重听（已预先生成在 `data/audio/`，不需要额外安装）
- **今日复习**：按间隔重复安排（错题马上复习，连续答对 1/3/7/14/30 天后再出）
- **学习记录**（T）：最近 14 天每天题数、正确率、答对平均用时
- **设置**（S）：时限倍率 / 不限时、每轮题数、每日目标、自动朗读

## 操作

| 画面 | 按键 |
|---|---|
| 菜单 | 数字键开始 · M 切换模式 · T 学习记录 · S 设置 · Esc 退出 |
| 答题 | 选择/听力：1~4（也可以点鼠标）；打字：罗马字 + 回车；听力 P 重听；Esc 结束本轮 |
| 反馈 | 先在心里默读整句，再按 空格 / 回车 · E 知识卡 · P 重听 |
| 总结 | 空格 回菜单 · R 再来一轮 |
| 设置 | ↑↓ 选择 · ←→ 修改 · Esc 保存返回 |

## 出题规则

每道题根据最近的作答分成 5 种状态，决定抽到的概率和时限（打字模式时限 ×2，听力加上语音时长）：

| 状态 | 条件 | 抽题权重 | 时限 |
|---|---|---|---|
| 答错过 | 最近一次错或超时 | 最高 | 15 秒 |
| 新题 | 没做过 | 高 | 15 秒 |
| 偏慢 | 答对但超过 6 秒 | 高 | 10 秒 |
| 练习中 | 答对 | 中 | 8 秒 |
| 有语感 | 连续两次 3 秒内答对 | 很低 | 5 秒 |

作答记录在 `progress.db`（SQLite），设置在 `config.json`，都不进 git。

## 题库与素材

- 题目：`data/L*.json`，一个文件一个级别。`options` 的**第一个是正确答案**（程序会打乱）。
  可选字段：`context`（上方的情景 / 对话，多行用 `\n`）、`reading`（答案的平假名，打字模式用）、`hint`（打字模式提示）、`alt`（打字模式也算对的写法）。
- 知识卡：`data/cards/*.json`，按标签（tag）对应。
- 检查题库：`python -m jpcloze.bank`
- 改了题目后重新生成语音和打字元数据（开发用，需要 `pip install -r requirements-dev.txt`）：
  `python tools/build_assets.py`。TTS 读错的词在 `data/tts_overrides.json` 里改成平假名。

## 结构

```
main.py / start.bat     入口
jpcloze/app.py          Panda3D 界面（菜单、答题、反馈、知识卡、总结、记录、设置）
jpcloze/trainer.py      出题、状态、今日复习、统计（不依赖 Panda3D）
jpcloze/romaji.py       罗马字 → 假名
jpcloze/bank.py         题库、知识卡、语音清单
jpcloze/store.py        SQLite 作答记录
jpcloze/settings.py     设置读写
tools/build_assets.py   生成语音（pyopenjtalk）
tests/                  python -m unittest discover tests；tests/screenshot.py 离屏截图
```

## 计划

- [x] 限时答题、反馈、SQLite、弱项优先、本轮总结
- [x] L3~L6 题库、知识卡、语音、今日复习、学习记录、设置、打字 / 听力模式
- [ ] 打包成 exe
- [ ] 3D 场景 + NPC
