# ARCH-00｜基线重构、统一领域模型与安全迁移

> 阶段性质：**实施中**；ARCH-00A 已合并主分支；ARCH-00B SQLite 持久化与无损迁移开发中；ARCH-00C 未实施。当前 GitHub main：2026-11-03 验证的 X-Wiki Python 脚本与 MkDocs 系统。  
> 上游：[PRD v2](../PRD-v2.md) · [需求研究](../research/PH-HN-2026.md)  
> 下游：[UX-002](./UX-002-First-Real-Value.md) · [UX-003](./UX-003-Knowledge-Review.md)

## A. 研究命题与工程问题

**命题**：将现有可运行的“语音 → 直接编译公开 Wiki → Git Push”脚本系统，转换成可演进的“不可变私有来源 → 结构化候选 → 人工批准 → 私有知识版本 → 独立选择是否公开”应用内核，同时不破坏已经验证的 Voice Memos、Git、Pages、CI 和失败恢复能力。

从真实源码核对得到的基线：
- `scripts/process_voice_memos.py::open_state` 目前只有 `recordings` SQLite 表；状态包括 `raw_ready/compiled/publish_pending/failed`，并未有 Source/Claim/Proposal/Review 等业务对象。
- `scripts/compile_wiki.py::compile_wiki` 运行 `pi --tools read,write,edit,grep,find,ls`，允许暂存工作区直接改 `wiki/`、`index.md`、`log.md`；它不是 Proposal-only。
- `scripts/process_voice_memos.py::git_publish` 提交 `wiki/index/log`；默认 `Settings.git_push=True`（来自 `scripts/xwiki_config.py`）。这只是现有单用户公开 Wiki 工作流，不可复用为新用户的默认私有发布行为。
- `scripts/compile_transaction.py` 有 fsync journal、冲突检测与恢复，但它主要处理文件写回，并未实现 Proposal CAS、用户身份授权或“私有批准”语义。
- `scripts/prepare_site.py` 从现有仓库 `wiki/` 生成公开站点，`raw/voice/` 在 `.gitignore` 中，`raw/references/` 不同：部分参考资料已跟踪于仓库。不能简单把所有 `raw/` 都当作不曾公开。
- `pyproject.toml` 目前只配置 Ruff/Pytest；`pytest` 的 `testpaths` 仅是 `scripts/tests`；`scripts/tests/conftest.py` 把 scripts 目录加到路径上。
- UI 目前是 `sites/content/demo/` 的静态六步合成演示，不能直接升级为真实审阅后端。

### 不变量（始终保证）

1. 源文件以及历史版本不可被编译器覆盖；所有衍生文件明确来源、版本、模型。
2. AI 输出不直接写 approved 知识；只可产生受校验的候选。
3. 公开 `wiki/` 是单独授权的**导出目标**，不是用户私有知识主存储。
4. 任何已批准修改都要有可重放的证据、原始版本 CAS、幂等键、撤销记录。
5. 已有 CLI、macOS Voice Memos 调用与 GitHub Pages 继续兼容，按 feature flag 迁移，不进行全量无测试重写。

## B. 目标目录与责任划分

以下路径是**待创建文件**，不是当前已存在文件。

```text
X-Wiki/
├── pyproject.toml                        # build-system, packages, pytest targets
├── src/xwiki/
│   ├── __init__.py
│   ├── cli.py                            # xwiki 子命令入口；旧 scripts/ 保留 shim
│   ├── config.py                         # typed settings, safe defaults
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── source.py                     # Source / TranscriptRevision / SourceState
│   │   ├── evidence.py                   # EvidenceSpan / Claim / EvidenceValidation
│   │   ├── knowledge.py                  # KnowledgeNode / KnowledgeRevision
│   │   ├── proposal.py                   # ChangeProposal / ReviewAction
│   │   ├── privacy.py                    # PrivacyScope / DataDestination
│   │   ├── errors.py                     # typed domain errors
│   │   └── contracts.py                  # protocols, zero I/O
│   ├── application/
│   │   ├── import_source.py              # application use case
│   │   ├── review_proposal.py            # use case, not UI state
│   │   ├── search_knowledge.py
│   │   └── publish_selection.py
│   ├── infrastructure/
│   │   ├── sqlite/
│   │   │   ├── connection.py             # WAL + transactions
│   │   │   ├── migrations.py             # numbered, idempotent
│   │   │   └── repositories.py           # sqlite implementations
│   │   ├── file_store.py                 # immutable private blobs + fsync
│   │   ├── git_publication.py            # wraps legacy release gate
│   │   └── external_provider.py          # policy-governed pi invocation
│   └── interfaces/
│       ├── http/                         # future loopback API only
│       └── desktop/                      # future UI bridge, no domain writes
├── migrations/
│   ├── 0001_knowledge_core.sql
│   └── 0002_proposal_review.sql
├── schemas/
│   ├── source.schema.json
│   ├── evidence.schema.json
│   └── change-proposal.schema.json
├── scripts/
│   ├── import_voice_memos.py             # compatibility wrapper, no deletion
│   ├── process_voice_memos.py            # legacy pipeline behind mode flag
│   ├── compile_wiki.py                   # migrate toward candidate creation
│   ├── compile_transaction.py            # reuse durable journal semantics
│   ├── staged_workspace.py               # reuse safety checks, restrict outputs
│   └── release_gate.py                   # public Git publication only
├── tests/
│   ├── unit/domain/
│   ├── integration/sqlite/
│   ├── integration/migration/
│   ├── contract/
│   └── e2e/                              # existing UX-001 retained
└── docs/product/stages/                  # 本系列设计文档
```

### 模块依赖规则

`domain` **不得** import `application/infrastructure/interfaces/scripts`。  
`application` 仅依赖 `domain` 中的 Protocol；不可直接使用 `sqlite3`、Git CLI 或 `pi`。  
`infrastructure` 实现 Port；`interfaces` 只解析请求、调用 use case、序列化响应。  
旧 `scripts/*.py` 保留为 adapter/shim，复用已有测试；不在一个 PR 中删除脚本入口。

## C. 文件级修改清单

| 文件 | 操作 | 具体职责 | 验证点 |
|---|---|---|---|
| `pyproject.toml` | MODIFY | 加 `build-system`、src package discovery、依赖组及 `tests/unit`/`tests/integration` 测试路径 | `pip install -e .`; 无需 `sys.path` 注入 |
| `src/xwiki/domain/{source,evidence,knowledge,proposal}.py` | ADD | immutable typed entities、枚举、不可变 ID、状态转换 | 纯单元测试和序列化 roundtrip |
| `src/xwiki/domain/contracts.py` | ADD | SourceStore、ProposalRepo、KnowledgeRepo、PolicyGate、Clock、ID Generator | fake adapters 单测 |
| `src/xwiki/application/*.py` | ADD | 明确事务语义、操作顺序、错误模型 | 组合测试不需要真实模型 |
| `src/xwiki/infrastructure/sqlite/{connection,migrations,repositories}.py` | ADD | SQLite Schema、版本迁移、CAS、幂等键 | 旧录音库只增迁移，不破坏原表 |
| `schemas/*.schema.json` | ADD | Source/Span/Proposal 的机器可读契约 | JSON schema 负例与迁移一致 |
| `src/xwiki/config.py` | ADD | 本地默认；外部模型/公开 Git 需要许可 | 默认配置不发网络 |
| `scripts/xwiki_config.py` | MODIFY | 逐步转接 typed settings；保留旧参数别名 | 旧配置测试全部通过 |
| `scripts/process_voice_memos.py` | MODIFY | 标记 `legacy_publish` 与 `review_first` 两条路径；不在同一事务混用 | 原 `test_pipeline.py` 保持绿 |
| `scripts/compile_wiki.py` | MODIFY | 为后续 `--proposal-only` 提供明确出口；保留旧 CLI | 不让新用户的候选直接应用 |
| `scripts/prepare_site.py` | VERIFY/MODIFY | 仍只读取 public export；强化私有内容扫描 | 私有 Source 永不进入 `sites/site` |
| `.gitignore` | MODIFY | 忽略新的本地私有工作区、SQLite WAL、数据库备份；明确既有 `raw/references` 历史状态 | diff 无私人数据 |
| `.github/workflows/quality.yml` | MODIFY | 新增 schema/migration tests；保留现有 Ruff、pytest、golden 和 Chromium | 旧新 CI 全绿 |
| `tests/integration/migration/test_old_recordings.py` | ADD | 现有 `recordings` 表迁移与回滚 | 现有数据可读、重复迁移幂等 |
| `docs/architecture/adr-00-private-public-boundary.md` | ADD | 私有源数据/批准知识/公开知识三分区 | reviewer 确认操作边界 |

## D. 推荐 SQLite v1 结构（草案）

```sql
PRAGMA foreign_keys=ON;
CREATE TABLE schema_migrations(
  version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE sources(
  source_id TEXT PRIMARY KEY,
  origin TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  captured_at TEXT,
  status TEXT NOT NULL,
  private_path TEXT NOT NULL,
  UNIQUE(origin, content_sha256)
);
CREATE TABLE transcript_revisions(
  revision_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  content_sha256 TEXT NOT NULL,
  engine TEXT NOT NULL,
  model TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE knowledge_nodes(
  node_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,
  approved_revision_id TEXT,
  privacy_scope TEXT NOT NULL DEFAULT 'private'
);
CREATE TABLE knowledge_revisions(
  revision_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL REFERENCES knowledge_nodes(node_id),
  parent_revision_id TEXT,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  review_action_id TEXT UNIQUE
);
CREATE TABLE proposals(
  proposal_id TEXT PRIMARY KEY,
  node_id TEXT REFERENCES knowledge_nodes(node_id),
  base_revision_id TEXT,
  status TEXT NOT NULL,
  candidate_kind TEXT NOT NULL,
  rationale TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE review_actions(
  action_id TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL REFERENCES proposals(proposal_id),
  idempotency_key TEXT NOT NULL UNIQUE,
  action TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

现实实现不能直接用这些表替换 `recordings`：旧表保留，新增映射/一次性迁移及 `source_id` 回填；须定义 `approved_revision_id` 外键的事务创建顺序，避免循环引用。对 Text/JSON Schema 需另外建立 Check、FK/UNIQUE、字段归一化。

数据库操作的 P0 规则：`BEGIN IMMEDIATE` 开始审批事务，CAS 比较 base revision，插入 review action/revision，并以幂等键抵御重复提交；文件写回用已有 durable journal 与 DB 状态收敛。SQLite 事务与文件系统并非单一原子事务，必须设计 restart reconciliation。

## E. 向后兼容与安全迁移顺序

1. 写定现有公开 Wiki 的备份/manifest、录音 `recordings` 状态样本（仅本地，**不得提交私有内容**）。
2. 新增 src/package 与类型模型，但保持现有脚本实际行为不变；CI 对照当前 98 个 Python 测试与 12 个 Playwright 用例。
3. 引入迁移注册表，先建新表与只读适配，不删除/更新原表。
4. 新增 `review_first` 模式并在产品新工作区默认启用；旧单用户 CLI 保持兼容，明确提示其会直接公开 Git。
5. 分批将导入、proposal、审批、检索迁移到新包，旧入口用极薄 wrapper 调用新 application。
6. 最后才考虑关闭 legacy direct-publish；此动作需要单独迁移向导、明确用户批准与回滚方案。

### 阶段不可跳过的风险

当前 `Settings.git_push=True` 是既有行为；不能简单在原配置中突然改为 False 并导致旧用户失去自动发布。建议新增 `XWIKI_PIPELINE_MODE=legacy|review_first`，新产品默认 review_first，原 CLI 明确展示所选模式，迁移时提示风险。

## F. 逐 PR 交付与测试

| PR | Files | 验收 |
|---|---|---|
| ARCH-00A — Domain contracts | `src/xwiki/domain/*`, `schemas/*`, `pyproject.toml`, `tests/unit/domain/*` | 完整 schema positive/negative；旧测试仍全绿 |
| ARCH-00B — Persistence | `src/xwiki/infrastructure/sqlite/*`, `migrations/*`, `tests/integration/migration/*` | 旧库升级、重复启动、断电/并发迁移验证 |
| ARCH-00C — Compatibility & Privacy boundary | `scripts/xwiki_config.py`, `process_voice_memos.py`, `compile_wiki.py`, `.gitignore`, `docs/architecture/adr-00-private-public-boundary.md` | 旧模式未退化，新模式不默认公开 |

**DoD**：用真实代码测试证明“新私有工作区不经过用户授权产生公开 Git 更改”；既有 GitHub Pages、release manifest、Mac smoke、PR #7 demo 仍绿。ARCH-00 不应假装 P0 的真实导入或真实审阅已经实现。

## ARCH-00A — 本阶段交付记录（2026-11-03）

- 实施范围：Python 可安装的 `src/xwiki/` 纯领域模块、八份 Draft 2020-12 JSON Schemas、严格序列化与负例测试、Linux/macOS CI 集成。
- 安全约束：`Source` 与 `KnowledgeNode` 默认只能表示 private；显式外部模型 consent 才允许领域层通过外发判定；`public_web` 仍拒绝，等待 ARCH-00C 的独立发布授权。
- 明确限制：这里的 Policy 是无 I/O 的业务判定，**尚未连接真实模型调用或 Git 发布拦截**；现有 CLI 行为不变，不能把 ARCH-00A 解释为完成真实私有化改造。
- 验收依据：新旧 pytest、JSON Schema 反例、Ruff、静态站点和浏览器 E2E；CI 结果以 GitHub Actions 为准。
- 下一项：ARCH-00B SQLite Schema + 无损迁移，再进入 ARCH-00C 发布权限边界。

## ARCH-00B — SQLite Product State（实施记录）

- 新增版本化迁移、私有 Repository、旧 recordings 的只读、可重入、保留历史快照导入；具体见 [ARCH-00B 实施说明](ARCH-00B-Implementation.md) 和 [ADR-00B](../../architecture/adr-00b-product-sqlite.md)。
- 新产品数据库为 `.state/product.sqlite`，**不修改**现有 `.state/ingest.sqlite` 或 `scripts/process_voice_memos.py` 的自动转写/发布行为。
- 旧数据库导入为显式命令；历史 hash 不合法的行完整保留在私有快照并记录问题，绝不伪造已验证来源。
- 本阶段没有消费者 UI、真实来源文件复制、模型外发权限执行器或公开发布审批。
- 下一阶段 ARCH-00C 将建立真正的私有工作空间/公开站点边界。
