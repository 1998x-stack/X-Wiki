# X-Wiki

> [Product PRD / 产品需求文档](docs/product/PRD.md) · [Try the interactive demo](https://1998x-stack.github.io/X-Wiki/demo/) · UX-001 — The First 90 Seconds

X-Wiki 把 iPhone Voice Memos 持续转化为可追溯的 Markdown 知识库：

```text
iPhone Voice Memos -> iCloud -> Mac Voice Memos library
  -> MLX Whisper (local) -> immutable raw Markdown
  -> pi + iagent/standard + x-wiki-compiler skill
  -> compiled wiki -> GitHub Pages
```

转写使用 Apple Silicon 上的本地 `mlx-whisper`，不调用 OpenAI API。公开仓库和
GitHub Pages 只包含编译后的 `wiki/`；音频、转写缓存、`raw/voice/` 和状态数据库
留在本机。

## 快速开始

要求：Apple Silicon Mac、Python 3.10+、`ffmpeg`、Git，以及已经配置好
`iagent/standard` 的 `pi`。

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r scripts/requirements-dev.txt
.venv/bin/pip install -r sites/requirements-site.txt
cp .env.example .env          # 可选；默认已经是中文转写
.venv/bin/python scripts/doctor.py
.venv/bin/python scripts/process_voice_memos.py
.venv/bin/python scripts/install_launch_agent.py
```

配置、权限和移植说明见 [scripts/docs/configuration.md](scripts/docs/configuration.md)，自动运行、
睡眠行为和故障恢复见 [scripts/docs/automation.md](scripts/docs/automation.md)。

## 常用命令

```bash
# 只转写，不编译、不推送
.venv/bin/python scripts/process_voice_memos.py --skip-compile --skip-push

# 强制按当前模型重新转写；raw 会生成 revision，不覆盖旧证据
.venv/bin/python scripts/process_voice_memos.py --reprocess

# 移除后台任务
.venv/bin/python scripts/install_launch_agent.py --remove

# 质量检查与站点构建
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/python scripts/evaluate_wiki.py
python scripts/wiki_lint.py --strict
.venv/bin/python scripts/prepare_site.py --strict
.venv/bin/mkdocs build --strict
```

知识入口见 [index.md](index.md)，公开页面见
[1998x-stack.github.io/X-Wiki](https://1998x-stack.github.io/X-Wiki/)。

## Verified website deployment

After GitHub Pages deployment, the workflow reads back the public
`release-manifest.json` over HTTPS and compares its full file manifest,
commit SHA, and digest with the source commit. Only after a matching read-back
is a deployment receipt uploaded as a workflow artifact. See
`docs/architecture/deployment-verification.md`.

Site navigation is generated from every published `wiki/` page by
`scripts/mkdocs_nav.py`; newly compiled pages therefore cannot silently
remain outside navigation.

## Durable compilation recovery

Writeback now creates a fsynced transaction journal in `.state/compile-transactions/` before changing any live Wiki files. Interrupted attempts are recovered on the next scan, and divergent manual edits are never silently overwritten. See `docs/architecture/durable-compile.md`.

## UX-001 — The First 90 Seconds

Try the [no-signup browser demo](https://1998x-stack.github.io/X-Wiki/demo/):
old idea → new note → connection → suggested revision → source evidence →
approval/rejection (with undo/reset). This static story uses fictional source
excerpts, runs no AI, asks for no microphone or account permissions, and
makes no analytics requests. Approval affects only in-memory demo UI.

Review the [UX-001 acceptance contract](docs/product/PRD.md) and the
[browser E2E suite](tests/e2e/ux-001.spec.cjs) before using this demo as
a Product Hunt acquisition entry point.
