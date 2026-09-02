---
name: x-wiki-pipeline
description: >-
  端到端执行 X-Wiki 语音→知识流水线：获取 iPhone Voice Memos → 本地 MLX Whisper 转录 → 写入不可变 raw 证据 → 用自己的规则编译进 wiki/index/log → 校验并构建 GitHub Pages 站点。既可跑整条链路，也可只做某一步（只 preflight / 只转写 / 只编译 / 只校验 / 只做发布交接）。当用户说“处理语音备忘录”、“转写语音”、“更新 wiki”、“编译/生成知识”、“构建/生成站点”、“跑一遍整条流水线”、“doctor 检查就绪”、“看看还有哪些待编译” 时，或想用智能体代替手动敲脚本时，都请使用本技能。
compatibility: >-
  Apple Silicon Mac, Python 3.10+, 仓库内 .venv, ffmpeg, mlx-whisper, 已配置 iagent/standard 的 pi。所有路径以仓库根为基准。
---

# X-Wiki Pipeline

把 iPhone Voice Memos 变成可追溯的链接知识库，端到端。本技能同时把 `scripts/` 里
的机械步骤（preflight、转录、校验、建站）与知识编译的智能判断打包在一起，因此你
可以用**脚本**或**本技能**两种角度驱动同一套流水线。

运行前提：当前工作目录是 X-Wiki 仓库根（含 `.git/`、`scripts/`、`wiki/`、`raw/`、
`sites/`）。环境变量来自仓库根 `.env`（`scripts/xwiki_config.py` 读取），shell 环境优先。

## 边界（不可破坏）

- `raw/` 是证据，**永不编辑/改写**；一旦转写即不可变，内容变化只会生成
  `{slug}--rev-{hash}.md` 新版本，绝不覆盖。
- 知识编译期间只能改 `wiki/`、`index.md`、`log.md` 三个目标。
- 不碰音频、`.state/`、`.venv/`、`raw/voice/`、`sites/site/`、`sites/.site-docs/`。
- **发布归流水线/用户/OS 自动化/GitHub Actions**：本技能驱动每一步，但**不自行 `git push`**。
- 参考 [references/wiki-schema.md](references/wiki-schema.md) 了解目录分层与链接约定。

## 两种角度（先讲清楚）

- **脚本角度**：直接跑 `scripts/process_voice_memos.py`（完整版）一步到位——转写 +
  编译（内部用 headless skill）+ 状态落库 + 自动 push。状态与发布都由流水线管理。
- **技能角度（本技能 / 默认）**：把机械步骤交给脚本（preflight、转写、校验、建站），
  把“编译成 wiki”这个需要判断的步骤由**智能体自己**按内嵌规则完成，push 交给流水线。
  这样你既能一键跑脚本，也能让智能体带着判断走一遍。

## 常用命令（脚本角度）

```bash
.venv/bin/python scripts/doctor.py                          # preflight
.venv/bin/python scripts/process_voice_memos.py --skip-compile --skip-push  # 只转录
.venv/bin/python scripts/prepare_site.py && .venv/bin/mkdocs build --strict # 建站校验
.venv/bin/ruff check .
.venv/bin/pytest
```

> 本技能的辅助脚本置于本技能目录 `scripts/` 下，请用相对路径引用（见下文每个步骤）。

`process_voice_memos.py` 用 SQLite `.state/ingest.sqlite` 幂等；`--reprocess` 强制
重新转写；`--skip-compile`/`--skip-push` 只到某一步；已处 `raw_ready/compiled/
publish_pending` 的录音不会重复转写。

## 执行步骤（每个都作为独立子操作）

### Step 0 —— preflight（可单跑）
```bash
.venv/bin/python scripts/doctor.py
```
逐项确认：macOS Apple Silicon、Python ≥3.10、ffmpeg、mlx-whisper、pi、Voice Memos
目录可读、Git remote 存在。任何 FAIL 都先解决（例如给 Python 授权“完全磁盘访问”）
再继续。

### Step 1 —— 获取与转录（只转写）
```bash
.venv/bin/python scripts/process_voice_memos.py --skip-compile --skip-push
```
- 从 iCloud Voice Memos 目录发现新录音，等文件静置 `XWIKI_MIN_AGE_SECONDS` 后哈希。
- 本地 MLX Whisper 转录，以 `raw/voice/YYYY/MM/*.md` 写入不可变证据，状态置 `raw_ready`。
- `--reprocess` 强制按当前模型重新转写（会产生 raw revision）。
- 这一步不改 `wiki/`。想先看看“没有新录音”是否成立，可先跑
  `scripts/pending_sources.py`（相对路径，自动定位仓库根）。

### Step 2 —— 看看待编译源（只读）
```bash
.venv/bin/python scripts/pending_sources.py
```
输出 `raw_ready`（待编译）/ `publish_pending`（待发布）/ `failed`（失败）清单与统计。
若清单为空，说明没有待编译的新证据，编译可安全地是一个零改动（不要为演示而建页）。

> 引用本技能辅助脚本一律用相对路径 `scripts/pending_sources.py`（它在 `.pi` 与
> `.claude` 两个安装目录下都能自动定位仓库根，不要写 `.pi/...` 或 `.claude/...` 前缀）。

### Step 3 —— 编译（智能体据规则编辑 wiki，本技能内嵌）
对新出现的源（Step 2 的 `raw_ready`，或 `raw/references/` 新参考），**你直接**按
[references/wiki-schema.md](references/wiki-schema.md) 与下面规则更新 `wiki/`、
`index.md`、`log.md`：
- 判断每个源是新增断言、强化既有论点、矛盾，还是不产生持久价值；无新知识时允许零改动。
- 惯用解法：把反复出现的思想并入既有持久页；仅当跨多源且无法归并时才新建页。
- 来源叙事与时间戳留在 `raw/`；解读、关系、决策、待解之问写进 `wiki/`。
- 区分“源主张”与“解读”；矛盾保留为显式待解，不强行圆场。
- 低置信名称/数字/引用中性表述或记为待解；散文以中文为主、简洁具体；用稳定 ASCII slug。
- 仅当导航有实质变化才更新 `index.md`；仅当页面有实质编辑才在 `log.md` 追加带日期记录。
- 每个实质性主张必须带 `## 来源`（仓库根相对链接）。
- 公共边界：公开页不带凭据、私人标识、精确地址、不必要的个人细节；本地路径不进公开页。
- 不用更弱的概括悄悄替换已有更强表述。
- 改完可选校验链接：`.venv/bin/python scripts/prepare_site.py && .venv/bin/mkdocs build --strict`。

### Step 4 —— 校验与建站（只读）
```bash
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/python scripts/prepare_site.py && .venv/bin/mkdocs build --strict
```
确认：raw 无变更；新 wiki 链接都能解析；无重复概念；解释与源主张可分；`index.md`
只暴露重要页面；公开文本无多余私密细节。

### Step 5 —— 发布交接（不自行 push）
本技能**不**执行 `git commit`/`git push`。交接：
- `scripts/pending_sources.py` 复核状态。
- 用 `git status -- wiki index.md log.md` 展示知识层待提交变更。
- 说明：把 `wiki/`、`index.md`、`log.md` 提交并 push（由 OS 自动化
  `com.xwiki.voice-ingest` 或 GitHub Actions 在 push 后发布站点）。
- **状态调和说明**：本技能编译后，未被 `process_voice_memos.py` 的编译路径落库为
  `compiled`，源仍可能是 `raw_ready`。这没问题——下次完整流水线运行会让知识页
  与本已体现的来源做一次幂等的 no-op 校验并落库 `compiled` + push。请勿在技能内
  自行改动 `.state/` 的 SQLite 来“补状态”。

## 整条链路
默认按 Step 0→1→2→3→4→5 依次执行。用户说“只 preflight / 只转写 / 只编译 / 只校验
建站 / 只查待编译 / 只做发布交接”时，只执行对应步骤。

## References
- [references/wiki-schema.md](references/wiki-schema.md) —— 目录分层、链接约定、编译决策、公共边界、质检。
- `scripts/pending_sources.py` —— 读取摄取状态（Step 2/5）。