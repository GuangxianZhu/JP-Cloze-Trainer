# JP-Cloze-Trainer · 日语语感训练（挖空选择题）

纯 Python + Panda3D。不用开口，靠大量限时挖空选择题练语感：**又快又对**才算有语感。

## 运行（Windows）

```bat
pip install -r requirements.txt
python main.py
```

字体会自动从 `C:\Windows\Fonts` 查找：日文用 Yu Gothic / Meiryo，中文用微软雅黑。
找不到的话，把 `config.example.json` 复制成 `config.json`，在 `font_ja` / `font_zh` 里填字体路径。

## 操作

| 画面 | 按键 |
|---|---|
| 菜单 | 数字键选级别，Esc 退出 |
| 答题 | 1~4 作答（也可以点鼠标），Esc 放弃本轮 |
| 反馈 | 先在心里默读整句，再按 空格 / 回车 |
| 总结 | 空格 回菜单，R 同级别再来一轮 |

## 出题规则

每道题根据你最近的作答分成 5 种状态，状态决定抽到的概率和时限：

| 状态 | 条件 | 抽题权重 | 时限 |
|---|---|---|---|
| 答错过 | 最近一次错或超时 | 最高 | 15 秒 |
| 新题 | 没做过 | 高 | 15 秒 |
| 偏慢 | 答对但超过 6 秒 | 高 | 10 秒 |
| 练习中 | 答对 | 中 | 8 秒 |
| 有语感 | 连续两次 3 秒内答对 | 很低（偶尔复习） | 5 秒 |

时限太紧就在 `config.json` 里把 `time_scale` 调成 1.5 之类。作答记录保存在 `progress.db`（SQLite）。

## 题库

`data/*.json`，一个文件一个级别。每题 `options` 的**第一个是正确答案**，程序会打乱顺序：

```json
{"id": "L1-009", "tags": ["が（对象）"], "sentence": "私は犬{blank}好きです。",
 "options": ["が", "を", "に", "で"], "explain": "好き・嫌い・上手 等的对象用が。"}
```

可选 `context`：显示在题目上方的上下文（如对话的上一句）。
检查题库格式：`python -m jpcloze.bank`

当前：L1 助词 52 题，L2 活用・接续 50 题。

## 结构

```
main.py              入口
jpcloze/app.py       Panda3D 界面
jpcloze/trainer.py   出题、状态、统计（不依赖 Panda3D）
jpcloze/store.py     SQLite 作答记录
jpcloze/bank.py      题库读取与校验
jpcloze/fonts.py     字体查找
data/                题库
tests/               python -m unittest discover tests；tests/screenshot.py 离屏截图
```

## 计划

- [x] P0/P1：限时答题、反馈、SQLite 记录、弱项优先、本轮总结
- [ ] L3 固定搭配、L4 授受・语气、L5 敬語、L6 最自然
- [ ] 答后播放整句语音（pyopenjtalk）
- [ ] 打字挖空模式
- [ ] 3D 场景 + NPC
