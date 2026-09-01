# X-Wiki

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
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -r requirements-site.txt
cp .env.example .env          # 可选；默认已经是中文转写
.venv/bin/python scripts/doctor.py
.venv/bin/python scripts/process_voice_memos.py
.venv/bin/python scripts/install_launch_agent.py
```

配置、权限和移植说明见 [docs/configuration.md](docs/configuration.md)，自动运行、
睡眠行为和故障恢复见 [docs/automation.md](docs/automation.md)。

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
.venv/bin/python scripts/prepare_site.py
.venv/bin/mkdocs build --strict
```

知识入口见 [index.md](index.md)，公开页面见
[1998x-stack.github.io/X-Wiki](https://1998x-stack.github.io/X-Wiki/)。
