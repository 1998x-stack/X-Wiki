# Feature Specification — Knowledge Review Workbench

> 规划中的真实产品功能（**未实现**）｜PRD v2 P0-B｜2026-11-03  
> 相关用户研究：[PH/HN 定性研究](../research/PH-HN-2026.md) · [产品 PRD v2](../PRD-v2.md)

## 1. 用户任务与防误用原则

用户从自己的真实录音、文本或 Markdown 中获取新证据，系统发现该证据可能需要修订一个已有 KnowledgeNode。用户**无需理解向量嵌入、GraphRAG、Git、YAML**，只需看见“什么变了、为什么、来源在哪里、是否要接受”。

Workbench 不是“所有笔记一律给你一份 AI 改写”，不能自动将所有来源当作有效事实，也不该默认制造待办任务。接受一份变更提案不等于自动公开发布；用户可以只保存在私有知识库。

### 不可侵犯的不变量

- **Invariant 1**：原始 Source 不可由 LLM 改写；衍生 TranscriptRevision 与 KnowledgeRevision 另存。
- **Invariant 2**：不经过用户批准，不修改已有 KnowledgeNode 的 approved revision。
- **Invariant 3**：任意 Claim 的证据引用若指向不存在的 Source 或越界的 span，则它不能进入已确认知识。
- **Invariant 4**：同一 source / proposal / approval 重试幂等；同一版本写入不能重复生成多条 Revision。
- **Invariant 5**：private/source 内容绝不能因在 Review 展示过就进入 GitHub Pages；公开发布另有独立确认。
- **Invariant 6**：如果 Source 无法断定新旧主张矛盾，则展示“未确定”或“补充信息”，不能强行声称观点被推翻。

## 2. 与当前项目模块的对接

| 已有模块 | 已有能力 | 未来新增接口，不能误称已经实现 |
|---|---|---|
| `scripts/import_voice_memos.py` / `process_voice_memos.py` | 本地数据发现/转写/状态记录 | SourceStore API + 具体来源片段定位与补充元数据 |
| `scripts/compile_wiki.py` | 暂存工作区中编译 Wiki | Proposal-only compile，不直接更新 approved 知识正文 |
| `scripts/staged_workspace.py` / `compile_transaction.py` | 暂存、验证边界与崩溃恢复 | 审批后的原子写入、版本 CAS 和幂等确认 |
| `scripts/wiki_lint.py` | 链接/schema/启发式隐私检查 | 结构化 Claim ↔ Evidence 的语义评测、引用范围审计 |
| `scripts/release_gate.py` | Git 远端确认/manifest | 审批提交与公开发布状态分离 |
| `scripts/verify_deployment.py` | GitHub Pages HTTPS 版本核验 | 私有知识不会因 Git 推送事件而默认变为公开 |
| `sites/content/demo/` | 合成、手工编排的 6 步示范 | 未来真实 Workbench 不能复用“假的 AI 计算结果” |

## 3. 领域对象与数据契约

**Source**（原始证据）：

- `id`：不可复用 UUID；`origin`：`voice_memo|file|markdown_vault|manual`；
- `content_sha256`：保存后内容哈希；`created_at`、`captured_at`、`imported_at`；
- `original_path_ref`：只在本地可信索引保存，不放公开 Web；`permission_scope`：private；
- `state`：queued/stored/transcribing/indexed/failed_retryable/failed_terminal；
- `language`、`transcript_revision_id`、`audio_duration_ms?`；私有路径、文件名和 token 不应出现在遥测。

**EvidenceSpan**（精准引用）：

- `source_id`、`transcript_revision_id`、`start_offset`、`end_offset`（Unicode codepoint 还是 UTF-8 byte 必须全局固定）；对语音可附带 `start_ms` / `end_ms`。
- `quote_sha256` 与 `source_revision_sha256`，便于发现转写改动后引用失效。
- UI 必须支持展开原文、定位、显示来源日期、证据类别；低置信转写或来源丢失必须标明。

**Claim**：
- `claim_id`、`text`、`owner`（user/source/assistant inference）、`modality`（assertion/hypothesis/question）；
- `supporting_span_ids[]`、`opposing_span_ids[]`；`confidence_bucket`（high/medium/low/unknown）。
- 不将 LLM 自己的改写伪造成 Source 的原句。

**KnowledgeNode**：
- `node_id`、`kind`（concept/decision/project/entity）、`title`、`approved_revision_id`、`privacy_level=private`；
- `status`（active/archived）、`source_claim_ids[]`、`topic_aliases[]`。
- 不需要存储绘图坐标；关系视图是可选派生展示。

**ChangeProposal**：
- `proposal_id`、`node_id`、`base_revision_id`、`candidate_kind`、`before_text`、`after_text`、`rationale`、`evidence_span_ids[]`、`uncertainty_notes[]`；
- `generator` 包含 model/provider/version/prompt_digest；`external_processing_approved` 包含明确授权标识；
- `status`：draft/proposed/needs_evidence/approved/rejected/superseded/failed；`created_at`、`reviewed_at?`、`review_action_id?`。
- `candidate_kind` 必须枚举：new/enrich/qualify/contradict/no_change/uncertain。不能把 `no_change` 意外升格为修改知识。

**KnowledgeRevision**：
- `revision_id`、`node_id`、`parent_revision_id`、`approved_from_proposal`、`content_sha256`、`committed_at`、`approved_by`；
- `undo_of_revision?`、`git_commit_sha?`、`idempotency_key`；
- 每次批准/撤销都应留下不可变审计记录，而不是删掉历史。

### 推荐 JSON 契约（示例数据为合成）

```json
{
  "schema_version": 1,
  "proposal_id": "proposal-synthetic-001",
  "node_id": "daily-systems",
  "base_revision_id": "revision-001",
  "candidate_kind": "qualify",
  "status": "proposed",
  "before_text": "A fixed schedule reduces daily decisions and increases focus.",
  "after_text": "Structure reduces decisions, while flexible time supports adaptation.",
  "rationale": "A later statement adds a condition to the earlier belief.",
  "evidence_span_ids": ["span-old-001", "span-new-002"],
  "confidence_bucket": "medium",
  "uncertainty_notes": [],
  "generator": {
    "provider": "demo-only",
    "model": "hand-authored",
    "version": "synthetic",
    "prompt_digest": null
  }
}
```

以上对象仅为 V2 契约草案；实现时需建立 JSON Schema/Pydantic 校验、字段迁移、正反例黄金数据集。

## 4. Workbench 信息架构及交互状态

桌面左侧：Capture / Review / Knowledge / Recall / Privacy；主区默认为 **Review Inbox**。不得把自动生成的全部结果按创建时间倒序灌入列表；应先过滤低价值候选。

主界面草图：

```text
Review Inbox                             Processing: Local / External consent
┌──────────────────────────────────────────────────────────────────────────┐
│ New evidence may qualify “Daily systems”                 2 sources    │
│ A note from Oct 28 adds a condition to a statement from Aug 12         │
│                                                                          │
│ Before                         Suggested revision                      │
│ A fixed schedule helps ...     A structured day with flexible ...      │
│                                                                          │
│ Why this connection?            Evidence (click to original snippet)     │
│ Same topic, new constraint       #1 Aug 12   #2 Oct 28                  │
│                                                                          │
│ [Approve] [Edit] [Keep old] [Mark uncertain] [Not relevant]             │
│                                                                          │
│ This affects PRIVATE KNOWLEDGE only. [Preview if shared publicly]       │
└──────────────────────────────────────────────────────────────────────────┘
```

### 用户操作与校验

| 动作 | 先决条件 | 结果 | 常见失败与处理 |
|---|---|---|---|
| Open proposal | source 读入成功 | 展示 before/after 和 Evidence | 来源不可访问：禁用批准，提供定位或移除提案 |
| View evidence | 引用验证通过 | 显示精确片段、时间、为何支持 | 引用边界错误：标示 unsupported，不能隐藏 |
| Edit proposal | 可编辑权限 | 生成 edited draft，保留原建议 | 编辑后引用不再支持：重新验证 |
| Approve | evidence validated、base revision 当前、用户确认 | 新 Revision + 可撤销动作 + 审计 | CAS 冲突：diff 两版本、要求重新审阅 |
| Reject | proposed 或 needs_evidence | 提案归档，已批准知识不变 | 不重新弹出相同提案，除非有新证据 |
| Mark uncertain | 证据不够 | 保留 open question，不覆盖原有主张 | 不强行产生“矛盾已经解决” |
| Ignore weak link | 用户认为无关 | 显示反馈已保存，不改知识 | 反馈不得成为私人文本泄露通道 |
| Undo | 审计记录可取 | 创建新的 revert Revision，而非删除记录 | 当前版本已变化：重新评估并显示冲突 |

**Evidence gate 不是机械地“点开过面板即可”**。当前 UX-001 合成演示仅能证明面板打开过；真实产品必须同时完成 EvidenceSpan 可定位、引用正确性与 version CAS，不能把 demo 的 `evidenceViewed` 直接当作生产授权。

## 5. 推荐的 ChangeProposal 生成协议

1. **Ingest**：源文件稳定落盘/哈希核对，重复记录归并；出错明确显示。
2. **Candidate retrieval**：FTS5+alias 检索已存在节点，语义检索可选，返回候选与检索依据。
3. **Evidence extraction**：从原始记录中定位候选主张；附偏移、时间、引用版本和置信度。
4. **Reconciliation**：将新主张与节点已有 Claim 比较，分类 `new/enrich/qualify/contradict/no_change/uncertain`。
5. **Grounding gate**：校验每个 proposed 断言是否被至少一个 SourceSpan 支持，识别数字、条件、主体、时间、否定与不同上下文。
6. **Value filter**：无新意、弱相似、重复或无法可靠判断时可输出 no_change/uncertain，不强迫产生 Review 卡片。
7. **Review**：用户批准、编辑、拒绝或保存未定。
8. **Apply**：CAS 检查 `approved_revision_id`、幂等键、可恢复文件写回；不隐式触发公开 Pages。
9. **Recall**：创建可索引的 Revision 记录，支持检索“何时改主意、为什么”。

**重要**：LLM 不应直接拥有 Git push 权限。编译器产出候选，严格审阅后由确定性命令应用，再由独立发布授权决定是否分享。

## 6. Grounding QA：测试集和失败标准

独立于生成模型冻结小型真实且获授权的黄金集。首批覆盖至少：

- 同义重述（应 no_change），词汇相近但不同问题（应 no_change）；
- 旧主张新增限定条件（qualify），真正自相矛盾（contradict），部分同意（enrich）；
- 来源是反问/假设/引述别人/笑话，不自动当用户的事实立场；
- 单位、数字、年份、姓名、主语不同；
- 录音 ASR 含噪/缺字、人名误识别；
- 存在多条互相矛盾的证据，不能隐去反例；
- 同一批次反复重试、来源版本更替、重复记录；
- 外部模型返回虚构 source ID/错 offset；
- 用户将文本手动编辑后 Source 不再支持；
- 旧提案审批时节点已被其他操作改变；
- 不需要任何更新的日常记录；
- raw 中包含本地绝对路径/密钥/个人识别字段；
- 只读模式、禁外发模式下的行为。

指标按类别报告：`EvidencePrecision`、`UnsupportedClaimRate`、`ProposalAcceptance`、`FalseContradictionRate`、`TimeToReview`、`UndoRate`、`NoChangeAccuracy`。安全门槛：**错误引用/未经批准写入/未经授权外发/意外公开须为 0**。对每个异常保留可复现实例，不能只报 overall accuracy。

## 7. 安全与隐私分区

| 内容 | 默认存储 | 可外发吗 | 可出现在 Pages 吗 |
|---|---|---|---|
| 原始录音与音频元数据 | 用户设备私有目录 | 用户单独同意后按需处理；默认否 | 否 |
| 原始转写文本 | 用户设备私有状态 | 外部 LLM 若要使用需显式授权 | 否 |
| EvidenceSpan 原文片段 | 用户设备私有索引 | 显示用途和目标，确认后最小化发送 | 默认否 |
| Claim/Proposal/Review notes | 本地工作区 | 模型推断需受控 provider | 默认否 |
| 已批准 KnowledgeNode | 本地 Markdown | 独立分享动作后可发布选定页面 | **只有明确逐页批准后** |
| Pages 发布 manifest | 公开站点 | 是，只有路径和哈希等允许公开字段 | 是 |
| API token、真实 raw 路径 | 系统密钥存储/本地受限状态 | 否 | 否 |

当前 GitHub Pages 文档只验证仓库边界的现有发布机制，**不构成“任意用户个人知识都默认有隐私保护”的产品级结论**。未来必须把“私有批准”和“公开分享”设计成两次明确动作，并运行负向安全测试。

## 8. 用户体验终止条件

成功态：建议经审阅，知识节点内容更新且显示来源和新版本；用户能原路撤销、能在 Recall 搜到变化历史。

合法空态：没有值得修订的知识，产品明确告诉用户“Nothing needs updating yet”，且可继续录入。这个状态不能被视作 AI 失败。

可恢复失败态：音频格式不支持、缺失权限、转写超时、模型不可用、索引损坏、同步中断；均应有可理解的动作提示，而不是静默 spinner。

不可恢复/需人工介入态：证据内容损坏、审阅冲突、未经授权的模型响应修改、隐私泄露风险；默认拒绝更改并保留审计材料。

## 9. 交付拆分与验收计划

**PR-UX-02 Schema**：规范 Source / Span / Claim / Node / Proposal / Revision，Golden Case 的 JSON Schema 校验和迁移，先构建最小只读记录。  
**PR-UX-03 Review API**：候选查询/生成/审阅应用的独立 API、CAS 与幂等性。  
**PR-UX-04 UI**：真实 Source 证据对齐，before/after Diff，批准/拒绝/编辑/撤销和键盘操作。  
**PR-UX-05 Eval**：独立来源验证 + 标注工具 + 性能/安全门禁。  
**PR-UX-06 Publish Boundary**：私有变更和公开分享两次审批、发布清单预览和回滚，针对外发与敏感内容的负向 E2E。

每批 PR 必须独立可评审、测试已通过，不能在未验证来源真实性时把 simulated demo 变成“正式已连接的 AI”。

## 10. Design review 的开放问题

1. EvidenceSpan 用 UTF-8 bytes、Python Unicode codepoint 还是 token index？必须一开始固定、跨实现一致。
2. 私人原文能否在屏幕上显示而不给外部 provider？离线模式需给出退化路线。
3. “修订观点”和“改变事实认定”是否采用不同证据标准？
4. 当模型不确定关联时，是显示 uncertain 卡片还是直接忽略？先通过用户研究确定。
5. 用户的拒绝意见能用于本地偏好排序吗？不能默认外传或永久推测个人特征。
6. 什么时候可以安全对外分享知识、但不公开内部具体私有来源？需要自洽的脱敏出版策略。
