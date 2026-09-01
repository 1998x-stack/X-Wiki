# 0001 本地优先的 Voice Memo Pipeline

## 决策

使用 Mac 本地 Voice Memos 库作为 X-Wiki 的导入入口。

## 背景

iPhone 应该保持低摩擦捕捉设备的角色。Mac 能访问同步后的 `.m4a` 文件和 Voice Memos 元数据数据库，因此更适合作为自动化 worker。

当前本地数据库包含录音元数据，但没有 transcript 文本；因此首次导入使用了本地 Whisper。

## 结果

- 音频继续留在本地，不进入 wiki 仓库。
- Raw Markdown 保存转写证据、元数据和音频哈希。
- Wiki 页面可以从 raw evidence 中重新生成或持续修订。
- SQLite 状态库记录音频哈希、模型指纹和处理阶段，重复扫描不会重复编译。
- Raw Markdown 不可变；同一录音内容变化时新增 `--rev-<hash>` 版本。
- launchd 在 Mac 醒着时监听目录并定时扫描，唤醒后执行补偿扫描；它不会唤醒 Mac。
- 自动编译发现知识层存在未提交修改时暂停，避免覆盖或夹带人工工作。
- 只使用 GitHub Pages 发布知识层，不同步 GitHub Wiki。

## 来源

- [[raw/references/iphone-icloud-voice-memos-llm-wiki]]
- [[raw/voice/2025/02/2025-02-20-2351-189cd8db]]
- [[raw/voice/2025/02/2025-02-25-0840-ed71daf6]]
- [[raw/voice/2025/05/2025-05-12-2144-e25f1768]]
