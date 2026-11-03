# UX-003｜Knowledge Review：证据对齐、知识修订与用户审批

> 状态：**设计，尚未开发**｜依赖 [ARCH-00](./ARCH-00-Foundation.md) 的私有知识边界、[UX-002](./UX-002-First-Real-Value.md) 的真实来源存储。  
> 本阶段完成 X-Wiki 的第一条**真实价值闭环**，而不是简单给静态 UX-001 接一个聊天模型。

## A. 研究命题与产品价值

**核心假设**：用户在两条不同时点的真实资料间，真正需要的是“这种新证据究竟改变了原来的哪个认识？”有来源、能修订、可拒绝/撤销的审阅过程，会比纯摘要或自动知识图谱更可信。

用户最短路径：导入两条证据 → 系统提议 `qualify/contradict/enrich/no_change` → 打开精准原句 → Before/After Diff → 选择 Approve/Keep old/Edit/Mark uncertain → 持久私有 Revision → Undo → 可查询审阅历史。

### 必须杜绝的错误

1. 用语义相似度把主题相近但不互相支持的句子当成事实。
2. 将说话者引用别人的话误认成用户自己的观点。
3. LLM 编造 Source ID、音频时间、引用片段、否定与数字。
4. 提案已过时，用户批准时覆盖了另一条新版本。
5. 批准操作意外触发 GitHub Pages 公开发布。
6. LLM 擅自修改 `wiki/`、`raw/` 或任何已批准的知识文件。

## B. 从当前代码迁移的关键决策

当前 `scripts/compile_wiki.py` 在暂存目录调用 `pi`，输出是直接改写 `wiki/`，再用 `apply_staged_changes()` 写回。对 Review-first 模式，必须**替换输出契约**：

```text
旧：Source -> pi (write/edit wiki) -> staged apply -> wiki -> git
新：Source -> Claim extraction -> EvidenceSpan verification
         -> Candidate matching -> Proposal JSON -> Review Inbox
         -> user approval -> CAS + durable revision -> private Markdown
         -> optional explicit public export -> Git/Pages
```

推荐将现有 `pi` 无结构化命令修改能力仅限旧 legacy 模式。新的模型适配器使用工具白名单 `read` 或直接非工具模型调用返回 `JSON`，然后由**确定性 schema/引用验证器**检查。在沙箱外发/进程权限不明确时，不应称 `--tools read` 等同于真实系统级安全沙箱。

私有知识推荐存在 `.state/knowledge/`、SQLite 为结构索引；`wiki/` 保持公开导出产物。对已有 `wiki/` 不能假设重新命名后公网历史就消失：如已公开，则需要单独迁移与历史风险评估。

## C. 领域契约与重要文件

| 路径 | ADD / MODIFY | 具体职责 |
|---|---|---|
| `src/xwiki/domain/evidence.py` | ADD（ARCH-00 定义，UX-003 扩展） | `EvidenceSpan`, `Claim`, source-revision hash, offsets and polarity |
| `src/xwiki/domain/proposal.py` | ADD/EXTEND | `ChangeProposal`, `CandidateKind`, `ProposalStatus`, `ReviewDecision` |
| `src/xwiki/domain/knowledge.py` | EXTEND | `KnowledgeNode`, immutable `KnowledgeRevision`, private/public scope |
| `src/xwiki/application/extract_claims.py` | ADD | 从 SourceRevision 生成候选主张并定位 source span |
| `src/xwiki/application/link_candidates.py` | ADD | 先 FTS 与 alias 选候选节点，语义相似性不能作为唯一证据 |
| `src/xwiki/application/reconcile_claims.py` | ADD | `new/enrich/qualify/contradict/no_change/uncertain`；允许零提案 |
| `src/xwiki/application/validate_evidence.py` | ADD | 断言级引用有效性、原文包含性、数字/主体/时间/否定检查 |
| `src/xwiki/application/create_proposals.py` | ADD | 成立的候选入库；无效/无新意记录原因，不混成批准知识 |
| `src/xwiki/application/review_proposal.py` | ADD/EXTEND | Approve/Reject/Edit/MarkUncertain/Undo；版本 CAS/幂等 |
| `src/xwiki/infrastructure/model_adapter.py` | ADD | 受数据传输策略约束的 LLM 结构化输出解析；超时与模型版本 |
| `src/xwiki/infrastructure/evidence_locator.py` | ADD | 以具体 SourceRevision 解析文本偏移、音频片段时间、checksum |
| `src/xwiki/infrastructure/sqlite/review_repository.py` | ADD | inbox、proposal、review action、version CAS、审计 |
| `src/xwiki/infrastructure/private_knowledge_store.py` | ADD | 仅写 `.state/knowledge/`，重用 fsync journal，但按 Source/Revision 存储 |
| `src/xwiki/interfaces/desktop/review_api.py` | ADD | 展示模型和 command handlers；本机鉴权/来源检查 |
| `scripts/compile_wiki.py` | MODIFY | `review_first` 不运行允许写 Wiki 的 Agent；改为 candidate-only |
| `scripts/staged_workspace.py` | REUSE/RESTRICT | 对 proposal JSON 与 approved Markdown 分别允许固定路径 |
| `scripts/compile_transaction.py` | REUSE/EXTEND | 写回恢复语义；额外解决 SQLite 与文件 journal 状态收敛 |
| `scripts/wiki_lint.py` | EXTEND | 对 public export 增加证据泄漏与支持状态门禁 |
| `scripts/skills/x-wiki-compiler/SKILL.md` | MODIFY | 区分 legacy compile 与 proposal generator；禁止新模式原地写公开 Wiki |

## D. 精确证据对齐：拒绝“只凭看起来像真”

### Span 规范

**明确建议用 Unicode codepoint 半开区间 `[start,end)`**，仅定位到一个冻结的、经约定统一换行符的 SourceRevision 文本。对语音另加 `start_ms/end_ms`。

```python
@dataclass(frozen=True)
class EvidenceSpan:
    span_id: str
    source_revision_id: str
    text_sha256: str
    start_cp: int
    end_cp: int
    quote_sha256: str
    start_ms: int | None = None
    end_ms: int | None = None
```

验证器必须执行以下顺序：
1. SourceRevision 存在且私有读取已授权；其 `text_sha256` 与提案引用相等；
2. `0 <= start_cp < end_cp <= len(text)`，且文本 `text[start_cp:end_cp]` 的 sha256 等于 `quote_sha256`；
3. 音频时间戳在合法范围内；时间戳不得用于凭空生成逐字精度；
4. 主张与引用句之间的语义支持独立评估：可分 supported/contradictory/ambiguous/unsupported；
5. 需要修订的每个事实从 Claim → Span 可定位；无法支持的句子必须删除、标疑问或阻止批准。

**特别注意**：offset 正确并不代表语义支持正确。一个真实存在的句子也可能只是在否定某个观点、引用别人或提出假设；这必须进入黄金负例。

### 状态机与命令

```text
DRAFT -> PROPOSED -> REVIEWING
                        |     |
                        |     +--> NEEDS_EVIDENCE -> PROPOSED (new evidence)
                        +--> REJECTED
                        +--> APPROVED -> APPLIED
                        +--> SUPERSEDED (base revision changed)
PROPOSED -> NO_CHANGE_ARCHIVED / UNCERTAIN
APPROVED/APPLIED -> UNDO_REQUESTED -> REVERSAL_APPLIED
```

生产环境不允许“证据面板打开过”就作为可批准条件。真正的 gate 是 `references_valid && review_user_confirmed && base_revision_current && privacy_policy_allows`。

推荐用例接口：

```python
create_proposals(source_ids: list[str], mode: ReviewMode) -> list[ProposalSummary]
list_review_inbox(status: ProposalStatus, cursor: str|None) -> Page[ProposalSummary]
get_proposal_detail(proposal_id: str) -> ProposalDetail
resolve_span(span_id: str, expected_revision: str) -> SourceExcerpt
approve(proposal_id: str, expected_base_revision: str, idempotency_key: str) -> RevisionResult
reject(proposal_id: str, reason: str|None, idempotency_key: str) -> ReviewResult
edit(proposal_id: str, new_text: str, idempotency_key: str) -> ProposalRevision
undo(node_id: str, expected_revision: str, idempotency_key: str) -> RevisionResult
```

### 事务 CAS 伪代码

```sql
BEGIN IMMEDIATE;
SELECT approved_revision_id FROM knowledge_nodes WHERE node_id=:node;
-- 如果不等于提案 base_revision，返回 409 STALE_PROPOSAL
INSERT INTO review_actions(action_id, proposal_id, action, idempotency_key, ...)
  VALUES (:action, :proposal, 'approve', :key, ...);
INSERT INTO knowledge_revisions(revision_id, node_id, parent_revision_id, ...)
  VALUES (:newrev, :node, :base, ...);
UPDATE knowledge_nodes
SET approved_revision_id=:newrev
WHERE node_id=:node AND approved_revision_id=:base;
-- 受影响行数 !=1 → abort + ROLLBACK
COMMIT;
```

注意 SQLite 更新成功仍不等于私有 Markdown 文件同步成功；必须使用准备日志/outbox/写后验证在重启时完成恢复。绝不能“DB 已 approved + 文件半更新 + UI 一直显示成功”。

## E. UI：真实审阅页面文件级

如果沿用 UX-002 的 SwiftUI desktop shell：

```text
apps/desktop-macos/
├── Windows/ReviewInboxView.swift     # 高价值待审阅候选（不全量 spam）
├── Windows/ReviewDetailView.swift    # 对照建议与当前节点
├── Components/RevisionDiffView.swift # before/after token or line Diff
├── Components/EvidencePanel.swift    # Source 日期/原句/来源跳转
├── Components/ClaimBadge.swift       # supported/ambiguous/unsupported
├── Components/ReviewActions.swift    # Approve/Edit/Keep/Uncertain
├── Components/UndoRevisionView.swift # 历史与撤销
├── Components/EmptyReviewState.swift # Nothing needs updating yet
├── Services/ReviewService.swift      # typed bridge, 请求签名与错误提示
└── Tests/ReviewFlowTests.swift
```

交互建议：
- 单条 Review 卡片优先显示“旧观点”和“新增条件”，不要隐藏原文只显示 AI 结论。
- Source 跳转使用可定位片段+原文高亮；来源不存在立即显示错误，而非灰色小字“此内容不可用”仍允许批准。
- 用户编辑建议后必须重新验证证据是否仍支持；拒绝和无修改操作应立即反馈，没有不存在的审批按钮。
- 审批完成展示 `Revision n`、来源和 `Undo`；公开发布另外有独立按钮、预览和权限说明。
- 三种空态：nothing new / source still processing / evidence insufficient。不得统一为 spinner。

## F. 机器评测与独立证据测试

建议基于现有 `evaluation/golden/wiki_cases.json` **新建** `evaluation/review/`，不要把“Wiki Lint 的 10 个合成案例”声称为 AI 支持率 95% 的证明。

```text
evaluation/review/
├── schema/v1.json
├── fixtures/qualify.jsonl
├── fixtures/contradict.jsonl
├── fixtures/no-change.jsonl
├── fixtures/unsupported.jsonl
├── fixtures/asr-noise.jsonl
├── fixtures/privacy.jsonl
├── fixtures/concurrency.jsonl
├── annotation-guide.md
└── adjudication.md                 # 双人标注差异和处理，不含原始私有数据
scripts/evaluate_review.py           # 独立模型输出评测, 不读实现内部答案
```

| 测试文件 | 必须包括 |
|---|---|
| `tests/unit/domain/test_evidence_span.py` | Unicode 与换行归一化、哈希、偏移边界、音频时间 |
| `tests/unit/application/test_reconciliation.py` | 6 类候选 + no-op + 虚假矛盾 |
| `tests/unit/application/test_grounding.py` | 否定、引号、引用第三人、数字/单位、主体不一致 |
| `tests/integration/sqlite/test_review_cas.py` | 并发批准同一个 base 只有一次成功 |
| `tests/integration/recovery/test_approve_crash.py` | DB/writeback crash 三种切点恢复 |
| `tests/integration/privacy/test_review_export_boundary.py` | 真实私有引用不得通过 GitHub Pages 预处理泄漏 |
| `tests/contract/test_review_api.py` | 状态码：404/409/422、幂等重复提交、无 token 请求 |
| `tests/e2e/ux-003-review.spec.cjs` | 真实源 → 提案 → 来源 → 编辑/拒绝/批准/撤销 |
| `apps/desktop-macos/Tests/ReviewFlowTests.swift` | 原生屏幕键盘/VoiceOver/来源定位 |

指标单独报告 `EvidencePrecision`、`UnsupportedClaimRate`、`FalseContradictionRate`、`NoChangeAccuracy`、`ReviewTime`、`UndoRate`。真实用户接受率只是偏好，不是验证事实正确性；至少要有独立标注人员核验支持情况。

## G. PR 拆解与完成门槛

| PR | 主要新增/修改文件 | 合并条件 |
|---|---|---|
| UX-003A — Evidence Identity | `domain/evidence.py`、`evidence_locator.py`、span schema 与 fixtures | 所有引用定位可追溯、越界/伪造被拒 |
| UX-003B — Proposal Only Compiler | `reconcile_claims.py`、`create_proposals.py`、`model_adapter.py`、`scripts/compile_wiki.py` | 新模式不写 Wiki，允许 no_change |
| UX-003C — Review Persistence | `review_repository.py`、`review_proposal.py`、migration、CAS tests | 并发审批、重复提交、断电和撤销全有确定结果 |
| UX-003D — Review UX | `ReviewInboxView.swift`、`EvidencePanel.swift`、`RevisionDiffView.swift`、Review service、E2E | 不可无证据审批，错链无法操作 |
| UX-003E — Independent Evaluation | `scripts/evaluate_review.py`、`evaluation/review/**`、`wiki_lint.py` 扩展 | 评测不依赖生成器结果自评；发布前无高危引用错误 |
| UX-003F — Public Separation | `publish_selection.py`、`scripts/prepare_site.py`、privacy negative tests | 已批准 private 不会自行进入 Git/Pages |

**最终 DoD**：真实（获授权）双来源能产生证据化候选，人工审批发生可验证的持久内容变更；不经用户许可不触发外部模型、公开页面或任务创建；错误引用/竞态/中断有明确失败和恢复。**UX-001 的静态按钮只是演示，不计入本阶段完成。**
