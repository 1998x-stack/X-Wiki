# 构建日志

## 2026-09-01 知识编译（已有来源复审）

- 复核三条已摄取语音与现有 wiki 页面的一致性：2025-02-20（李斯/主动权）、2025-02-25（每日操作系统）、2025-05-12（自由与必然）。
- 现有概念页与实体页已覆盖三条来源的主干内容，无需新建页面。
- 补强 [[wiki/concepts/positioning-and-agency]]：新增“良师与益友”小节（一个良师/益友足以改变一生），以及“夺其气”小节（先示弱再示强、保持神秘、拿回主动权、掌握火候）。
- 明确区分转写层与解释层：raw 保持不可变，仅修订 wiki 层。

## 2026-09-01 Apple Silicon 自动化升级

- 将本地转写从 CPU/PyTorch Whisper `base` 升级为 Apple MLX 上的 Whisper Large V3 Turbo。
- 新增幂等 SQLite 状态、Voice Memos 目录触发与五分钟恢复扫描。
- 新增 `x-wiki-compiler` skill，并由 Python 脚本通过 `pi` 加载，固定使用 `iagent/standard` 编译知识层。
- 新增 GitHub 仓库推送与 GitHub Pages 构建配置，不启用 GitHub Wiki。
- Git 和 Pages 只发布知识层；`raw/voice/` 证据层仅保留在本机。

## 2026-09-01 自动化可靠性复审

- 移除用户名、Python 和 Homebrew 绝对路径依赖，新增可选 `.env`，默认中文转写。
- Raw 改为不可变写入；转写变化产生 revision，所有文本与状态文件使用原子写入。
- 增加文件稳定性检测、单文件失败汇总、模型超时、编译边界和自动提交白名单。
- launchd 同时使用目录监听、五分钟扫描和唤醒后的日历补偿扫描。
- GitHub Pages 增加响应式首页、深浅主题、搜索、社交分享图和本地证据隐私标识。

## 2026-09-01

- 读取用户粘贴的架构参考：iPhone 13、iCloud Voice Memos、Apple transcript、Whisper fallback、LLM Wiki 编译。
- 从 macOS 本地 iCloud Voice Memos 库读取录音元数据。
- 确认本机有 3 条 `.m4a` 录音。
- 确认本地 `CloudRecordings.db` 有录音元数据，但没有 transcript 字段。
- 安装本地 `openai-whisper`，用 `base` 模型完成 3 条录音转写。
- 创建初始 raw evidence 文件和编译后的 wiki 页面。
