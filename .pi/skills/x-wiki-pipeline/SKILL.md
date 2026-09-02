---
name: x-wiki-pipeline
description: >-
  端到端执行 X-Wiki 语音→知识流水线：获取 iPhone Voice Memos → 本地 MLX Whisper 转录 → 写入不可变 raw 证据 → 编译进 wiki 知识层 → 用自己的规则编辑 wiki/index/log → 校验并构建 GitHub Pages 站点。既可跑整条链路，也可执行单个子操作（preflight / 转写 / 编译 / 校验 / 发布交接）。无论用户说“处理语音备忘录”、“转写”、“更新 wiki”、“编译知识”、“生成/构建站点”、“跑一遍整个流水线”、“doctor 检查就绪与否”，还是想把脚本式操作交给智能体自动完成，都请使用本技能。
compatibility: >-
  Apple Silicon Mac, Python 3.10+, 仓库内 .venv, ffmpeg, mlx-whisper, 已配置 iagent/standard 的 pi。所有路径以仓库根为基准。
---

# X-Wiki Pipeline

把 iPhone Voice Memos 变成可追溯的链接知识库，端到端。本技能把 `scripts/` 里的机械步骤（preflight、转录、校验、建站）与知识编译的智能判断打包在一起，因此你可以“用脚本”或“用本技能”两种角度驱动同一套流水线。

运行前提：当前工作目录是 X-Wiki 仓库根（含 `.git/`、`scripts/`、`wiki/`、`raw/`、`sites/`）。
环境变量来自仓库根 `.env`（`scripts/xwiki_config.py` 读取），shell 环境优先。

## 边界（不可破坏）

- `raw/` 是证据，**永不编辑/改写**；一份录音一旦转写就是不可变文件。若内容变化只会生成 `{slug}--rev-{hash}.md` 新版本，绝不覆盖。
- wiki 编译期间只能改 `wiki/`、`index.md`、`log.md` 这三个目标。
- 不要碰音频、`.state/`、`.venv/`、`raw/voice/`、`sites/site/`、`sites/.site-docs/`。
- **发布是流水线拥有的**：本技能驱动每一步但**不自行 `git push`**；最终提交+推送交给用户/OS 自动化/GitHub Actions。
- 仓库根只保留 `raw/ wiki/ scripts/ sites/` 四个内容目录；必要时参考 [references/wiki-schema.md](references/wiki-schema.md) 了解目录约定。

## 常用命令（脚本角度）

```bash
.venv/bin/python scripts/doctor.py                     # preflight
.venv/bin/python scripts/process_voice_memos.py --skip-compile --skip-push   # 只转录
.venv/bin/python scripts/prepare_site.py && .venv/bin/mkdocs build --strict # 建站校验
.venv/bin/ruff check .                                   # 静态检查
.venv/bin/pytest                                         # 离线测试
```
`process_voice_memos.py` 用 SQLite `.state/ingest.sqlite` 做幂等；`--reprocess` 重新转写；`--skip-compile`/`--skip-push` 只到某一步。

## 执行步骤

### Step 0 —— preflight（可选单跑）
跑 `.venv/bin/python scripts/doctor.py`。按输出确认：macOS Apple Silicon、Python ≥3.10、ffmpeg、mlx-whisper、pi、Voice Memos 目录可读、Git remote 存在。若某检查失败，按提示处理（例如给 Python 文件授权“完全磁盘访问”）后再继续。

### Step 1 —— 获取与转录（只转写）
```bash
.venv/bin/python scripts/process_voice_memos.py --skip-compile --skip-push
```
- 从 iCloud Voice Memos 目录发现新录音，等文件静置 `XWIKI_MIN_AGE_SECONDS` 后哈希。
- 本地 MLX Whisper 转录（无网络 key），以 `raw/voice/YYYY/MM/*.md` 写入不可变证据，状态置 `raw_ready`。
- 用 `--reprocess` 强制按当前模型重新转写（会产生 raw revision）。
- 这一步不改 `wiki/`。

### Step 2 —— 编译（编辑 wiki，智能判断，本技能内嵌规则）
读取 `raw/voice/`（及 `raw/references/`）里新的或 `raw_ready` 的源，然后**你直接**按 [references/wiki-schema.md](references/wiki-schema.md) 与下面的编译规则更新 `wiki/`、`index.md`、`log.md`：
- 判断每个源是新增断言、强化既有论点、矛盾，还是不产生持久价值；没有新知识时允许零改动（不要为演示而建页）。
- 惯用解法：把反复出现的思想并入既有持久页；只有跨多源且无法归并时才新建页。
- 来源叙事与时间戳留在 `raw/`；解读、关系、决策、悬而未决之问写进 `wiki/`。
- 区分“源主张”与“解读”；矛盾保留为显式待解，而不是强行圆场。
- 低置信的名称/数字/引用要中性表述或记为待解。
- 散文简洁具体、以中文为主；用稳定 ASCII 小写 slug。
- 仅当导航有实质变化才更新 `index.md`；仅当页面被实质编辑才在 `log.md` 追加带日期的记录。
- 每个实质性主张必须有 `## 来源`（仓库根相对的 wiki 链接）。
- 尊重公共边界：公开页不带凭据、私人标识、精确地址、不必要的个人细节；用户隐私本地路径不进入公开页。
- 不要用更弱的概括悄悄替换已有更强表述。

### Step 3 —— 校验
```bash
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/python scripts/prepare_site.py && .venv/bin/mkdocs build --strict
```
确认：raw 无任何变更；新 wiki 链接都能解析；没有重复概念；解释与源主张可分；`index.md` 只暴露重要页面；公共文本无多余私密细节。

### Step 4 —— 发布交接（不自行 push）
本技能**不**执行 `git commit`/`git push`（发布归流水线/用户/GitHub Actions）。完成后做交接：
- 用 `git status` 展示待提交的知识层变更。
- 把需要提交的文件（`wiki/`, `index.md`, `log.md`）列给用户，并提示：提交并 push（可由 OS 自动化 `com.xwiki.voice-ingest` 或 GitHub Actions 在 push 后自动发布站点）。
- 循用户/流水线决定，不要在技能内自行推送。

## 整条链路
默认按 Step 0→1→2→3→4 依次执行；可用“只做 preflight / 只转写 / 只编译 / 只校验 / 只做发布交接”等子句限定只执行其中一步或几步。

## References
- [references/wiki-schema.md](references/wiki-schema.md) —— 目录分层、链接约定、编译决策、公共边界与质检。