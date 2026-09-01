# X-Wiki 索引

## 当前知识地图

- [[wiki/synthesis/voice-to-knowledge-compiler|Voice to Knowledge Compiler]]
- [[wiki/concepts/freedom-and-necessity|Freedom and Necessity]]
- [[wiki/concepts/daily-operating-system|Daily Operating System]]
- [[wiki/concepts/positioning-and-agency|Positioning and Agency]]
- [[wiki/entities/li-si|Li Si]]
- [[wiki/entities/xunzi|Xunzi]]
- [[wiki/entities/han-fei|Han Fei]]
- [[wiki/entities/lu-buwei|Lu Buwei]]

## 来源清单

- [[raw/references/iphone-icloud-voice-memos-llm-wiki|Architecture Reference]]
- [[raw/voice/2025/02/2025-02-20-2351-189cd8db|Voice Memo: Li Si, Xunzi, Han Fei, Lu Buwei]]
- [[raw/voice/2025/02/2025-02-25-0840-ed71daf6|Voice Memo: Daily Habits and Goals]]
- [[raw/voice/2025/05/2025-05-12-2144-e25f1768|Voice Memo: Freedom and Necessity]]

## 待办队列

- 如果未来 Voice Memos 出现 `tsrp` transcript atom，再加入 Apple 原生转写提取。

## 自动化状态

- Apple Silicon 转写：MLX + Whisper Large V3 Turbo
- 知识编译：pi + iagent/standard + x-wiki-compiler skill
- 触发方式：Voice Memos 目录事件 + 每五分钟恢复扫描
- 发布目标：GitHub 仓库、GitHub Pages、GitHub Wiki；原始语音证据仅保留在本机
