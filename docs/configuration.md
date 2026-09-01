# 配置与移植

## 支持范围

转写层针对 Apple Silicon Mac 优化，依赖 `mlx-whisper`，不支持 Intel Mac 和 Linux。
站点构建、Wiki 编译脚本和测试本身可在其他平台运行。推荐 Python 3.12，最低 3.10。

需要安装：

- `ffmpeg`：读取 Voice Memos 的 `.m4a`。
- `pi`：加载仓库内的 `x-wiki-compiler` skill，并访问 `iagent/standard`。
- Git/GitHub CLI：首次建仓和排障时使用；日常脚本只依赖 Git。

MLX Whisper 在本机推理，不使用 OpenAI API key。`pi` 的模型凭据由 `pi` 自己的
配置管理，不应写入本仓库或 `.env`。

## `.env`

`.env` 是可选文件并被 Git 忽略。默认值已经适合中文 Voice Memos：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `XWIKI_LANGUAGE` | `zh` | Whisper 转写语言 |
| `XWIKI_WHISPER_MODEL` | `mlx-community/whisper-large-v3-turbo` | 本地 MLX 模型 |
| `XWIKI_LLM_PROVIDER` | `iagent` | pi provider |
| `XWIKI_LLM_MODEL` | `iagent/standard` | Wiki 编译模型 |
| `XWIKI_RECORDINGS_DIR` | 从 `Path.home()` 自动发现 | Voice Memos 目录 |
| `XWIKI_PI_BIN` | `PATH` → `~/.local/bin/pi` → Homebrew 前缀 | pi 可执行文件 |
| `XWIKI_MIN_AGE_SECONDS` | `60` | 文件静置多久后才处理 |
| `XWIKI_SCAN_INTERVAL_SECONDS` | `300` | 醒着时的恢复扫描间隔 |
| `XWIKI_COMPILE_TIMEOUT_SECONDS` | `900` | pi 编译超时 |
| `XWIKI_GIT_PUSH` | `true` | 是否自动推送 |
| `XWIKI_GIT_REMOTE` | `origin` | 推送 remote |
| `XWIKI_GIT_BRANCH` | `main` | 推送分支 |

Shell 环境变量优先于 `.env`。不要在 `.env` 中保存 GitHub token、模型密钥或其他
秘密；后台任务会继承必要的非秘密 X-Wiki 配置。

## 通用性（无需 `.env`）

默认值在任何 Mac 上均可直接运行：转写目录和 `pi` 都从 `Path.home()`/`PATH`
自动发现，默认语言是中文（`zh`），模型为本地 MLX Whisper。`.env` 只用于覆盖，
不是必需文件。唯一的机器相关前提是四个外部依赖已安装：Apple Silicon、`ffmpeg`、
`mlx-whisper`（python 依赖）和 `pi`（含 `iagent/standard` 凭据）。`pi` 默认按
`PATH` → `~/.local/bin/pi` → `/opt/homebrew/bin/pi` → `/usr/local/bin/pi` 查找，
装在别处时用 `XWIKI_PI_BIN` 指定。

## 权限

运行 `.venv/bin/python scripts/doctor.py` 会显示当前解释器和 Voice Memos 检查结果。
若访问失败，在“系统设置 → 隐私与安全性 → 完全磁盘访问权限”中添加 doctor 输出的
Python 可执行文件。Homebrew 的 `Python.app` 和命令行解释器可能是不同的授权对象，
应以脚本打印的解析后路径为准。

每台 Mac 的用户名、Homebrew 位置和 Voice Memos 容器路径都可能不同；代码不会固定
`/Users/x` 或 `/opt/homebrew`。确有差异时只需覆盖对应环境变量。
