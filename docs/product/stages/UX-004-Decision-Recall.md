# UX-004｜Decision Recall：找回过去的决定、依据和观点变化

> 状态：**设计，尚未实施**｜依赖 [UX-003](./UX-003-Knowledge-Review.md) 完成可批准、可追溯的私有知识版本  
> 研究问题：用户说“我当时为什么不采用方案 A”时，能否在不了解原文关键词的情况下，快速找到**正确决定及其当时证据**，且不会编造不存在的理由？

## A. 先设计用户任务，再选择检索模型

典型用户问题：
1. “我是在什么时候放弃每天排满日程的？”
2. “为什么上个月不使用方案 A？”
3. “某个项目的最新决定是什么？它是否推翻更早的决定？”
4. “我之前说过同一件事吗？有什么不同？”
5. “不知道具体词，只记得当时在讨论延迟和成本。”

**重点反例**：来源里出现“决定”两个字，却只是“讨论是否决定”；记录中引用别人的决定，而非本人的真实决定；现在的决定已替代历史决定；两次做了不同选择。系统应允许返回多个候选或拒绝断言。

### 非功能目标（待测）

- 本地精确/关键词搜索目标 P95 <500ms（测试设备和语料规模须固定）；进阶检索可异步。
- 任何 AI 回答中的引用能够定位到 SourceRevision/EvidenceSpan 或批准历史；无证据明确说“未找到足够依据”。
- 全部搜索与回忆默认私有，不为召回质量上传整个个人数据库。

## B. 索引设计与数据路径

```text
PRIVATE Source / TranscriptRevision
              |
              v
      Claim + EvidenceSpan  -- source permission, hash checks
              |
        Approved KnowledgeRevision / Decision
              |
      +-------+--------------------------+
      |                                  |
  SQLite FTS5                        Structured Index
  full text / alias                  decision date / topic / status
      |                                  |
      +---------- candidate join --------+
                         |
                     Re-rank
                         |
                  Source-gated results
                         |
                optional grounded answer
```

### 首选 baseline：FTS5 + 结构化过滤

现在 `scripts/process_voice_memos.py` 使用 `sqlite3` + WAL，尚未为私人知识建立独立 Search schema。应先做 FTS5，后用真实标注的 Decision Queries 判断是否需要 embedding。

中文注意事项：SQLite 默认 tokenizer 对中文无空格连续文字的召回有限；设计中提供中文字串/字符 n-gram 或 FTS5 trigram 兼容测试，同时保留 `unicode61` 英文检索。具体依赖与查询生成需在 SQLite 目标版本下验证。不要未经测试就宣称直接 FTS5 BM25 能解决中文同义表达。

## C. 文件级设计（ADD 为新路径，MODIFY 为当前文件）

| 路径 | 操作 | 精确职责 |
|---|---|---|
| `src/xwiki/domain/decision.py` | ADD | `DecisionFact`，区分提议、实际决定、撤销、替代、计划，含 source refs |
| `src/xwiki/domain/search.py` | ADD | `SearchQuery`、`SearchResult`、`Citation`、`NoEvidence` |
| `src/xwiki/application/build_index.py` | ADD | 扫描 approved 私有知识，增量索引、回填、更新与删除 |
| `src/xwiki/application/search_knowledge.py` | EXTEND | query → lexical/structured matches → 权限过滤 → 排序 |
| `src/xwiki/application/recall_decision.py` | ADD | “什么决定、何时、依据、结果”结构化回答，避免虚构 |
| `src/xwiki/application/compare_revisions.py` | ADD | 从同节点 Revision 链恢复观点变化；不依赖模型猜时间 |
| `src/xwiki/infrastructure/sqlite/search_index.py` | ADD | FTS5、索引事务、rebuild、断点恢复、索引版本 |
| `src/xwiki/infrastructure/search/query_parser.py` | ADD | alias、中文归一化、引号、日期范围、安全 MATCH 构造 |
| `src/xwiki/infrastructure/search/ranker.py` | ADD | BM25 + decision status + 证据数 + 时间字段的可解释排序 |
| `src/xwiki/infrastructure/search/embedding_adapter.py` | OPTIONAL | 可选语义 rerank，必须受隐私/模型外发权限控制 |
| `src/xwiki/infrastructure/search/citation_builder.py` | ADD | `source_id`, `span_id`, `revision_id` 校验和跳转构建 |
| `src/xwiki/interfaces/desktop/recall_api.py` | ADD | 分页搜索/按需问题回答；服务端强制权限控制 |
| `apps/desktop-macos/Windows/RecallView.swift` | ADD | 可编辑查询、逐条检索结果、准确引用、时间选择 |
| `apps/desktop-macos/Components/DecisionTimeline.swift` | ADD | 决定日期、旧新版本、依据/反对证据的事件轨迹 |
| `apps/desktop-macos/Components/CitedAnswerView.swift` | ADD | 每个可核验主张配来源，无法验证时显式说明 |
| `scripts/process_voice_memos.py` | MODIFY（桥接） | 真实 Source 处理完成触发私有索引更新；不重新启动公开 push |
| `scripts/wiki_lint.py` | VERIFY | 仅负责 public export 的质量门禁，**不**作为私有检索授权 |
| `.github/workflows/quality.yml` | MODIFY | 添加真实 FTS/rebuild/grounding 与性能基准的 smoke |

## D. 数据迁移与索引文件

`migrations/0004_decision_recall.sql`（示意）：

```sql
CREATE TABLE decision_events (
  decision_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL REFERENCES knowledge_nodes(node_id),
  revision_id TEXT NOT NULL REFERENCES knowledge_revisions(revision_id),
  decision_type TEXT NOT NULL,
  occurred_at TEXT,
  effective_at TEXT,
  superseded_by TEXT,
  rationale TEXT,
  privacy_scope TEXT NOT NULL DEFAULT 'private'
);
CREATE TABLE search_documents (
  doc_id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  foreign_id TEXT NOT NULL,
  revision_id TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  indexed_at TEXT NOT NULL,
  UNIQUE(kind, foreign_id, revision_id)
);
CREATE VIRTUAL TABLE search_fts USING fts5(
  title, body,
  content='search_documents',
  content_rowid='doc_id',
  tokenize='unicode61'
);
CREATE TABLE search_aliases (
  alias TEXT NOT NULL,
  node_id TEXT NOT NULL REFERENCES knowledge_nodes(node_id),
  PRIMARY KEY(alias, node_id)
);
```

实现期需额外添加 insert/update/delete triggers 保持 FTS 与 `search_documents` 一致、明确索引删源与版本滚动策略；对中文启用合适 tokenizer/trigram 变体并编写查询选择器。**不能**让旧 Source 删除后，孤儿片段仍被检索或被 AI 作为有效证据。

索引与事实库分离：私有的 `knowledge_revisions` 是事实源，FTS 是**可删除重建**的派生索引。允许显式 `xwiki reindex --verify`，报告 `indexed/unindexed/stale/missing`。

### 请求响应（typed，非已实现 API）

```python
search(query: str, filters: SearchFilters, limit: int = 20, cursor: str | None = None) -> SearchPage

recall_decision(query: str, as_of: datetime | None = None) -> RecallAnswer
# RecallAnswer:
# answer: string | None
# claims: [{text, cited_source_span_ids, cited_knowledge_revision_ids}]
# ambiguity: ["Multiple decisions match", "No confirmed decision"]
# evidence_status: supported | partial | insufficient

get_decision_timeline(node_id: str) -> list[DecisionEvent]
compare_decision_revisions(old_id: str, new_id: str) -> RevisionDiff
```

## E. 排序、检索退化与“拒答”原则

### 基线排序流程

1. Exact decision ID / title / alias → direct hit；
2. FTS MATCH（做安全 token 转义，不能拼接用户字符串形成 SQL）→ 前 20–50 候选；
3. 过滤权限、删除/归档、来源无效；
4. 合并相同知识节点的多个版本，按用户选择显示“当前有效”和“历史版本”；
5. 对 “when/why” 抽取日期和 `DecisionFact.rationale`，用 SourceSpan 复核；
6. 输出带证据卡片；如果没有证据则只返回相关文档列表，不能凭相似性造答案。

### 语义检索的适用条件

只有当独立黄金查询暴露“FTS5 + alias 不能找回的真实失败”时，才引入 embedding；首选本地可重建向量索引，固定嵌入模型与版本、记录回填进度。Hybrid ranking 先对离线 holdout 比较 Recall@5、MRR@10、nDCG@10，防止对小样本过拟合。

额外安全要求：引用应与原始数据权限绑定（source ACL），不因为 search index 曾包含该文本就默认允许返回。

## F. 黄金数据与指标

新建：

```text
evaluation/recall/
├── queries.jsonl                   # 查询及期望 decision_id/candidate_id
├── decisions.jsonl                 # 合成/获授权资料，禁止私人数据上传
├── annotations.jsonl               # 支持/不支持、理由、两人复核差异
├── negative-queries.jsonl
├── benchmark-config.yml            # CPU/内存/SQLite 版本/规模
└── README.md
scripts/evaluate_recall.py
```

测试文件：

| 新文件 | 关键断言 |
|---|---|
| `tests/unit/search/test_query_parser.py` | 中文、英文、混合词、日期、标点/SQL 特殊输入 |
| `tests/unit/search/test_ranker.py` | lexical tie、别名、版本去重、空查询 |
| `tests/integration/sqlite/test_search_index.py` | 重建与增量同步结果相同，索引损坏可恢复 |
| `tests/integration/sqlite/test_search_permissions.py` | 删除/私有/撤销许可的文档不被返回 |
| `tests/integration/search/test_citation_builder.py` | 每个结果的 SourceSpan 可查、正确版本 |
| `tests/contract/test_recall_answer.py` | 没证据不编造、多个决定返回歧义 |
| `tests/e2e/ux-004-recall.spec.cjs` | 搜索旧决定 → 证据跳转 → 版本时间线 |
| `tests/performance/test_fts_latency.py` | 固定可复现 corpus 下报告 p50/p95，而不硬编码成绩 |

最终指标：Recall@5、MRR@10、CitationPrecision、NoEvidenceAbstention、p95 Latency。评测必须将真正独立的 queries 作为测试集，不能使用构建别名索引时同一批问题自测。

## G. PR 分解

| PR | 主要文件 | 合并标准 |
|---|---|---|
| UX-004A — Decision schema | `domain/decision.py`、`0004_decision_recall.sql`、schema tests | 区分讨论、建议、批准决定、撤销 |
| UX-004B — FTS + Rebuild | `search_index.py`、`build_index.py`、query parser、search tests | 中英检索、增量/rebuild 一致、无孤儿索引 |
| UX-004C — Evidence-led Recall | `recall_decision.py`、`citation_builder.py`、`compare_revisions.py` | 不造事实，来源和版本可读回 |
| UX-004D — Recall UI | `RecallView.swift`、`DecisionTimeline.swift`、E2E | 按需检索、键盘、旧新版本解释 |
| UX-004E — Retrieval Evaluation | `evaluation/recall/**`、`scripts/evaluate_recall.py`、benchmark | 独立 holdout 优于或明确不优于 baseline |

**DoD**：找出至少一个在真实语料中确实存在的“历史决定 + 具体依据 + 相关修订”，且对负例可明确不回答；索引可再生、全文/向量检索不是事实源。未通过独立 Recall 评测就不推广“拥有终生 AI 记忆”。
