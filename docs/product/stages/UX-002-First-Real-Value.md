# UX-002｜First Real Value：真实导入、来源可靠性与首次使用

> 设计状态：UX-002A 真实来源存储正在实施，UX-002B/002C/002D 尚未实现｜前置 [ARCH-00](./ARCH-00-Foundation.md)｜后续 [UX-003](./UX-003-Knowledge-Review.md)  
> 产品目标：用户不用理解 Python、SQLite、Git、Whisper、pi，能把**自己的一份真实来源**安全地导入产品、看见来源正文及真实处理状态。首个真实知识更新将在 UX-003 完成，本阶段不伪装其已交付。

## A. 研究假设、产品体验与排除项

**用户问题**：安装和权限复杂、失败不知去向、一次性录音丢失、被迫先整理目录。PH 评论中多位用户质疑录音失败、误造 Todo、移动端权限问题。本阶段首先解决“可以信任我保存了什么”，其次才是 AI。

核心场景（Mac）：
1. 安装或打开 X-Wiki → 本地欢迎页：清楚区分本地索引、Whisper 本地音频转写、可选外部 LLM。
2. 拖入一个 `.txt` 或 `.md` 文件（最小可验收路径），或 `.m4a`（音频路径）；不先要求账号、外部 token 或 GitHub 授权。
3. “导入成功”仅在源文件经安全复制、fsync、哈希核对、数据库记录后出现；UI 显示状态与时间。
4. 对音频，展示排队、转写、完成/错误；用户随时打开原始来源及转写修订，转写错误不会删除音频。
5. 可继续添加一份后续记录；两段有时间差的记录进入 UX-003 Review 候选流程（本阶段只提供清晰未来入口或无效状态，不造假）。
6. 出错可取消、重试、移除派生索引，仍可导出原始文件。用户删除其源文件须额外确认，不和“忽略建议”混淆。

### 产品成功门槛

- 独立新用户从安装到首个文本导入可见，目标中位 ≤3 分钟（目标，不是当前实测）。
- 任何标记为 `stored` 的 Source 都能经 SHA-256 校验，故障注入不得导致“成功但源文件丢失”。
- 失败重试幂等、无重复 Source；`audio→transcript→knowledge` 的不同状态不能混成一个“处理中”。
- 没有批准外发时不调用外部 LLM；无模型时仍可保留、打开、检索原始记录。

## B. UI 与状态图

```text
[Welcome]
   |
   v
[Choose source] --> [Scan & Preview] --> [Import]
                                         |
                         +---------------+-------------+
                         v                             v
                [Text stored]                    [Audio stored]
                         |                             |
                         v                       [Transcribe queued]
                [Ready to review]                /     |      \
                                                 v     v       v
                                             Running  Failed   Indexed
                                                       |
                                                  [Retry / Export]
```

UI 卡片每个状态带 source id、有限状态、发生时间和下一步。没有实时模型结果时显示“awaiting local processor”，不要把 demo 的 synthetic ChangeProposal 渲染为真实结果。

## C. 后端文件级设计

### 1. 领域与业务服务（ADD）

| 路径 | 职责与具体 API |
|---|---|
| `src/xwiki/domain/source.py` | `SourceState` enum, `Source`, `SourceRevision`；来自 ARCH-00 |
| `src/xwiki/domain/errors.py` | `SourceMissing`, `DuplicateSource`, `UnsupportedMedia`, `PermissionDenied`, `TransientProcessingError` |
| `src/xwiki/application/import_source.py` | `ImportSource.execute(file_ref, origin, idempotency_key)`；验证/复制/哈希/DB commit |
| `src/xwiki/application/process_source.py` | `ProcessSource.execute(source_id)`；分配 text/audio handler，输出真实状态，不直接编译 Wiki |
| `src/xwiki/application/retry_source.py` | `RetrySource.execute(source_id)`；只允许失败且可重试状态、带退避信息 |
| `src/xwiki/application/export_source.py` | `ExportOriginal.execute(source_id, destination)`；复制字节到用户选择的文件，不输出敏感路径到日志 |
| `src/xwiki/infrastructure/file_store.py` | `put_immutable`, `open_verified`, `list_orphans`；私有目录权限、临时写入、rename、fsync |
| `src/xwiki/infrastructure/media_probe.py` | 文件真实格式/大小/时长约束、可选 FFmpeg 探测；不只相信扩展名 |
| `src/xwiki/infrastructure/transcriber_mlx.py` | 薄包装既有 mlx-whisper，显式 `model_version` 和转写修订 |
| `src/xwiki/infrastructure/sqlite/source_repository.py` | 读取、状态 CAS、唯一 hash 和 import event |
| `src/xwiki/application/source_jobs.py` | 单进程本地任务 worker、取消/重试、崩溃扫描、任务身份 |
| `src/xwiki/interfaces/desktop/bridge.py` | 只暴露导入、查看、取消、重试、导出、数据流信息；不能让 UI 任意执行 shell |

### 2. 现有代码迁移（MODIFY/REUSE）

| 现有文件 | 具体改动 | 禁止的做法 |
|---|---|---|
| `scripts/import_voice_memos.py::discover_recordings` | 把 Apple SQLite 读库适配为 `VoiceMemoSourceAdapter`；保留独立 fallback 与 Apple epoch 转换测试 | 修改系统 Voice Memos 数据库、要求用户复制整个数据库上传 |
| `scripts/import_voice_memos.py::write_raw` | 与新 `SourceStore` 共享不可变来源契约；新增 `source_id`/hash 记录，不覆盖历史 | 用同一路径原地覆盖，导致引用位置失效 |
| `scripts/process_voice_memos.py::open_state` | 在迁移期保留旧 `recordings` 状态和 `raw_ready/publish_pending`；新增索引表映射，不立即替换 | 用全局 `update recordings set status` 破坏已有队列 |
| `scripts/process_voice_memos.py::stable_audio_hash` | 提取“扫描前后文件稳定性”方法供普通文件导入复用 | 在复制尚未完成时宣布 source stored |
| `scripts/process_voice_memos.py::transcribe` | 改为 `LocalTranscriber` adapter，可注入 fake；回传 JSON 或失败类型 | 转写失败后删除已写入的原始音频 |
| `scripts/xwiki_config.py` | 引入 local workspace path、max file bytes、model download permission、`pipeline_mode` | 将 GitHub push、远端 LLM 作为新用户默认 |
| `scripts/doctor.py` | 输出 Apple Silicon/FFmpeg/Voice Memos/Whisper 依赖和权限状态的机器可读健康结果 | 把 Mac 特有失败显示成“未知错误” |

### 3. SQLite 新增表（迁移文件；不要重写已有 `recordings`）

`migrations/0003_source_jobs.sql`：

```sql
CREATE TABLE source_jobs (
  job_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  stage TEXT NOT NULL,
  state TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_retry_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_error_code TEXT,
  UNIQUE(source_id, stage)
);
CREATE TABLE import_requests (
  idempotency_key TEXT PRIMARY KEY,
  source_id TEXT REFERENCES sources(source_id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_source_jobs_state ON source_jobs(state, next_retry_at);
```

原始 blob 的建议布局（不是公开 Wiki）：

```text
.state/
├── source-store/sha256/<first2>/<digest>.blob
├── transcripts/<source_id>/<revision_id>.json
├── source-jobs.sqlite
└── imports/tmp/                      # 崩溃恢复扫描或清理
```

Source 可以保留文件名作为 UI 展示元数据，但绝对路径只进入本地受限 DB；采集日志不得输出完整隐私路径。对音频尤其不能基于扩展名或文件名信任输入。

## D. 接口设计（先用于本机 UI，不是公网 API）

推荐从 IPC/stdin-stdout 调用 application service 起步；若采用 loopback HTTP，必须绑定 `127.0.0.1`、随机启动口令、请求来源验证，并有明确 CSRF/端口暴露防护。不得在无身份权限控制下公开 LAN 服务。

```text
ImportSource.execute(ImportRequest):
  input: file_handle, origin="manual_file", idempotency_key
  output: {source_id, source_sha256, status="stored", next_stage?}

ListSources.execute(limit, cursor):
  output: [{source_id, display_title, kind, status, error_code?}]

RetrySource.execute(source_id, expected_state):
  output: {job_id, state="queued"}

ExportSource.execute(source_id, destination_bookmark):
  output: {status="exported", sha256_verified=true}
```

UI 通过稳定 ID，而非直接从页面传任意本机路径，来请求后端文件。任意 `DELETE` 操作需审计/确认且不自动删除原始语音。

## E. Desktop 用户界面文件级设计

建议先采用**一个薄 Mac 包装层 + Python 后台 worker**。首轮只须体现真实输入、来源列表、状态反馈和来源预览；成熟后再决定 Tauri vs SwiftUI。若需确定性默认方案，先用 SwiftUI shell（对 Mac 文件权限与 Finder 导入更自然），用独立本地 worker/IPC。**这是一项架构决策建议，不是已实现的选型结果。**

```text
apps/desktop-macos/
├── XWikiApp.swift                    # 应用生命周期、开机健康检查
├── Windows/WelcomeView.swift         # 安装/模型/隐私告知
├── Windows/LibraryView.swift         # 来源队列与空态
├── Components/ImportDropZone.swift   # Drag & Drop + NSOpenPanel
├── Components/SourceRow.swift        # source_id 状态、失败和重试
├── Components/ProcessingStatus.swift # 真实阶段反馈，不假装有结果
├── Components/SourcePreview.swift    # 原文与转写历史
├── Services/PythonWorkerBridge.swift # IPC/session nonce、断线恢复
└── Tests/                           # 交互、权限、文件导入 E2E
```

首次安装不要求用户理解 `pip`、`git` 或 Python CLI。实际打包需考虑 Whisper 模型体积、首次下载、Apple 签名/公证及 FFmpeg 授权，并在 UI 告知所需空间与是否联网下载；这些将在 REL-006 单独验收。

## F. 测试与失败注入（新增文件）

| 新增测试文件 | 用例与断言 |
|---|---|
| `tests/unit/application/test_import_source.py` | 文本导入成功、重复 hash 幂等、同名不同内容、负路径 |
| `tests/unit/application/test_retry_source.py` | 只允许 retryable 错误重试，失败不显示“已完成” |
| `tests/integration/storage/test_source_blob.py` | 先 fsync 后确认；断电、磁盘满、临时目录残留、权限/符号链接 |
| `tests/integration/sqlite/test_source_jobs.py` | 多次启动恢复、状态 CAS、重复 worker 与 SQLite WAL |
| `tests/integration/voice/test_voice_adapter.py` | Apple schema 变化 fallback、WAL、权限不可读、录音修改中 |
| `tests/contract/test_source_states.py` | 不合法状态跳跃/缺失来源完整性拒绝 |
| `tests/e2e/ux-002-import.spec.cjs` | 如采用 Web UI 时：文件拖入、进度、失败重试、原文预览 |
| `apps/desktop-macos/Tests/ImportFlowTests.swift` | macOS 原生选择器/拖拽/权限对话框/中断恢复；需真实 Mac runner |
| `scripts/tests/test_pipeline.py` | 保留并扩充旧录音流水线回归 |
| `.github/workflows/macos-smoke.yml` | 合成测试和可运行 macOS smoke，真实 iCloud 授权另行人工验收 |

关键测试：**导入成功 → 进程被杀 → 重启 → hash 一致 → UI 仍可打开原文**。这应当是红线，而不是依靠单元测试中 mock 成功。

## G. 按 PR 拆解

| PR | 文件范围 | 完成判据 |
|---|---|---|
| UX-002A — SourceStore | `file_store.py`, `source.py`, `import_source.py`, `0003_source_jobs.sql`, source tests | 无源文件丢失、导入幂等、负路径测试 |
| UX-002B — Workers & Voice adapter | `process_source.py`, `source_jobs.py`, `transcriber_mlx.py`, 旧 `import_voice_memos.py/process_voice_memos.py` | 真实转写/退化/重试与失败状态准确 |
| UX-002C — Desktop first run | `apps/desktop-macos/**`, `interfaces/desktop/bridge.py`, desktop tests | 不经命令行导入 .txt/.md，可见真实来源 |
| UX-002D — Fault injection & UX QA | `tests/integration/storage/**`, `tests/e2e/**`, `docs/architecture/adr-*.md` | Apple Silicon 授权验收；无假成功、可导出 |

## H. 研究与产品价值门槛

采用 5–10 名**不熟悉该项目的人**观察安装/导入流程，记录首次成功时间、错误后的恢复情况、是否理解“本地 Whisper 与外部 LLM 的区别”、是否愿意继续输入资料。优先按“失去信任的时刻”修复，不追求无限配置选项。

### DoD（阶段结束）

- 文本和至少一种音频格式可经真实 UI 完成导入，不需要用户进入终端；
- Source 不可变、状态可审计、断电/权限错误不导致已确认文件丢失；
- 真实本地转写在支持设备上经手动可复现 E2E；其他设备提供明确不可用原因；
- 私有默认、无模型授权时能保存/读取/导出；
- `scripts/tests` 旧回归、schema 测试、macOS smoke 与 UX-001 demo 不退化。

**不要把本阶段“成功保存真实文件”宣传成“真实 AI 已经自动审阅并修改旧知识”；那是下一阶段的验收任务。**

## Implementation progress: UX-002A

- [UX-002A source import status, CLI usage and test cases](UX-002A-Implementation.md)
- 第一批实现 `SourceStore` 与 `ImportSource`：真实文件哈希校验、私有持久化、SQLite `stored` 状态、同内容去重、可核验导出。
- **尚未交付**拖拽式 Mac 安装包、真实转写队列、逐条证据审阅和权限 UI。文件状态 `stored` 仅表示原始字节已存储，不代表转写/索引或知识批准完成。
