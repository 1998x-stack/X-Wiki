# UX-005｜Calm Rediscovery：低打扰的知识重新发现

> 状态：**设计，未实施**｜前置 [UX-003](./UX-003-Knowledge-Review.md) 的可靠知识修订与 [UX-004](./UX-004-Decision-Recall.md) 的可核验召回  
> 最重要原则：**优先按需，默认静默；用户不是为了养一个越来越吵的 AI 助理而开始记录。**

## A. 用户研究假设与产品价值

HN 的部分用户明确反对“第二大脑”不断提醒；另一部分希望系统主动呈现高质量连接。这不是一个可由产品经理单方面裁决的统一偏好。

**核心假设**：在同一真实任务上，用户自己打开“值得重新看一眼”页面并看到少数与当前项目/决策相关的旧知识，其感知价值将高于无解释的定时随机提醒，且干扰更低。

最小可用产品：用户打开 `Rediscover` → 系统展示 0–3 张经过证据校验的相关知识卡片 → 每张有“为什么现在推荐”“原始依据”“之前何时出现过”“Dismiss/Save/Not relevant” → 用户可设置永不提醒某类话题。允许空白：`Nothing useful to revisit today`。

### 必须满足的非目标

- 不用每日打卡、连续天数、强制通知来制造使用压力。
- 不把每一条新笔记都推送；不把真正的个人反思强制转为任务或成长积分。
- 不根据敏感个人内容生成营销画像或通知文案。
- 不因先前用户 Dismiss 就把它当作永久人格特征；仅用于本地排序或显式关闭的主题。

## B. 信息架构：基于触发条件而非“每天一条”

```text
Approved Knowledge/Decision + Revisits History
                   |
             Recall Index
                   |
           Candidate Generation
         /        |         \
  Current task  Explicit tag  Recent change
         \        |         /
            Privacy / Source ACL
                   |
         Weak-link rejection filter
                   |
         Rank and cap (0..3 results)
                   |
       Evidence + Why-now explanation
                   |
       Pull-first Rediscovery Inbox
                   |
   [Open] [Useful] [Dismiss] [Never this]
                   |
        Local opt-in feedback, no push
```

如果用户没有当前上下文（项目、话题、主动打开目标），不得编造“为什么现在”。该情况下优先显示“最近实际更新了什么”或返回空列表，不强制凑满卡片。

## C. 文件级架构

| 路径 | ADD/MODIFY | 具体职责 |
|---|---|---|
| `src/xwiki/domain/rediscovery.py` | ADD | `RediscoveryCandidate`, `WhyNowEvidence`, `VisibilityScope`, `FeedbackAction` |
| `src/xwiki/domain/privacy.py` | EXTEND | notification consent、private metadata access |
| `src/xwiki/application/generate_rediscovery.py` | ADD | 从当前任务/最近审阅变化生成候选；最多 3 张 |
| `src/xwiki/application/rank_rediscovery.py` | ADD | relevance、novelty、evidence、user feedback、重复曝光惩罚 |
| `src/xwiki/application/record_rediscovery_feedback.py` | ADD | Useful/NotRelevant/Dismiss/Never；幂等保存 |
| `src/xwiki/application/get_rediscovery_inbox.py` | ADD | 数据权限过滤、结果可解释、已关闭主题过滤 |
| `src/xwiki/application/notification_opt_in.py` | ADD | 默认关闭周回顾/提醒；明确授权后才调度 |
| `src/xwiki/infrastructure/sqlite/rediscovery_repository.py` | ADD | 曝光历史、反馈、抑制规则、授权偏好 |
| `src/xwiki/infrastructure/rediscovery/rules.py` | ADD | 基于显式上下文的候选规则，先于 LLM 排序 |
| `src/xwiki/infrastructure/rediscovery/scheduler.py` | OPTIONAL | 只有用户开启推送后才做本地定时检查 |
| `src/xwiki/interfaces/desktop/rediscovery_api.py` | ADD | GET inbox、POST feedback、GET/PUT consent，调用时验证本机身份 |
| `apps/desktop-macos/Windows/RediscoverView.swift` | ADD | 默认按需访问、结果 0..3 张 |
| `apps/desktop-macos/Components/RediscoveryCard.swift` | ADD | 原文/为什么现在/时间/反馈操作 |
| `apps/desktop-macos/Components/RediscoveryPreferences.swift` | ADD | 不提醒、主题屏蔽、周回顾完全 opt-in |
| `scripts/process_voice_memos.py` | VERIFY | 导入和编译不触发“默认推送提醒” |
| `.github/workflows/quality.yml` | MODIFY | 增加排序与隐私负例的确定性测试 |

## D. 状态、隐私与指标契约

### 推荐卡片最小结构

```json
{
  "schema_version": 1,
  "candidate_id": "rediscovery-synthetic-01",
  "node_id": "daily-systems",
  "source_revision_ids": ["revision-001", "revision-002"],
  "reason_kind": "relevant_to_current_project",
  "reason_text": "A new discussion of focus relates to your older schedule decision.",
  "rank_score_components": {
    "topic_match": 0.8,
    "evidence_support": 1.0,
    "revisit_penalty": 0.0
  },
  "evidence_status": "supported",
  "privacy_scope": "private",
  "suggestion_status": "unseen"
}
```

这仅为**合成示例**；生产前应增加与现有 Source/Revision 数据契约一致的机器校验。不要向 Web 公共日志输出主题或用户原文。

### 建议排序公式（算法假设，需消融）

\[
score = \alpha R_{\text{topic}} + \beta R_{\text{evidence}}
+ \gamma R_{\text{novelty}} - \delta C_{\text{repeat}}
- \epsilon C_{\text{interruption}}
\]

- `R_topic`：与用户当前打开项目/搜索意图的相关度；
- `R_evidence`：源引用是否完整；
- `R_novelty`：是否真正提供新视角，而非简单重复；
- `C_repeat`：用户最近已经看过几次；
- `C_interruption`：通知打扰成本（Pull 模式可视为 0）。

权重、阈值不应来自拍脑袋的“0.9 置信”，需要根据可公开的合成评测和获授权用户反馈校准。先实现无大模型的确定性规则 baseline，后续观察是否确实需要 LLM rerank。

### 状态规则

`candidate`：generated → eligible → exposed → opened | dismissed | irrelevant | saved → archived。  
`notification_consent`：disabled（默认）→ enabled_explicitly → disabled_by_user；默认无系统通知权限请求。  
`topic_mute` 与 `global_opt_out` 独立存储，不能通过重新安装外发旧追踪 ID 来绕开退出。

### 接口示例（不代表已实现）

```python
get_inbox(context: QueryContext | None, max_cards: int = 3) -> list[RediscoveryCard]
record_feedback(candidate_id: str, action: "opened|useful|irrelevant|dismissed", idempotency_key: str) -> None
set_preferences(push_enabled: bool, muted_topic_ids: list[str]) -> Preferences
explain_candidate(candidate_id: str) -> {why_now, source_refs, ranking_features}
```

模型不应根据没有证据的私人情感状态给用户贴标签；建议理由只使用用户明确输入的上下文与可核对的知识记录。

## E. SQLite 与测试数据

新增 `migrations/0005_rediscovery.sql`（示例）：

```sql
CREATE TABLE rediscovery_candidates (
  candidate_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL REFERENCES knowledge_nodes(node_id),
  reason_kind TEXT NOT NULL,
  explanation TEXT NOT NULL,
  evidence_revision_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  state TEXT NOT NULL
);
CREATE TABLE rediscovery_events (
  event_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES rediscovery_candidates(candidate_id),
  event_type TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  idempotency_key TEXT UNIQUE
);
CREATE TABLE rediscovery_preferences (
  user_scope TEXT PRIMARY KEY,
  push_enabled INTEGER NOT NULL DEFAULT 0,
  frequency TEXT NOT NULL DEFAULT 'none',
  updated_at TEXT NOT NULL
);
CREATE TABLE muted_topics (
  user_scope TEXT NOT NULL,
  node_id TEXT NOT NULL REFERENCES knowledge_nodes(node_id),
  PRIMARY KEY (user_scope, node_id)
);
```

默认本地单用户 `user_scope=local-owner`，如果未来加入账户体系，需迁移为真实 per-user ACL 和设备隔离，不能把所有用户写到同一个 SQLite 实例。

## F. 测试与用户研究

| 测试文件 | 必须覆盖 |
|---|---|
| `tests/unit/rediscovery/test_ranking.py` | 有来源的相关信息优先、最近重复曝光降权 |
| `tests/unit/rediscovery/test_weak_links.py` | 相同关键词但不同语义、空结果、不强制补 3 张 |
| `tests/unit/rediscovery/test_feedback.py` | Dismiss/Not relevant/Never/撤销反馈、幂等 |
| `tests/integration/sqlite/test_rediscovery_preferences.py` | 默认 disabled；重启后仍 disabled；mute 可重复提交 |
| `tests/integration/privacy/test_no_push_by_default.py` | 没授权不启动 scheduler、不建立外发网络请求 |
| `tests/e2e/ux-005-rediscovery.spec.cjs` | 按需打开、查看解释、跳源、关闭提示、空状态 |
| `evaluation/rediscovery/pairs.jsonl` | 相关/噪声/重复/权限受限候选对（经允许的合成数据） |
| `scripts/evaluate_rediscovery.py` | nDCG、Precision@3、MuteViolation、UsefulFeedbackRate |

### A/B 或双组实验建议

15–25 名目标用户，7–14 天，区分：
- Control：普通最近打开知识页；
- A：按需 Rediscover（默认）；
- B：用户主动 opt-in 后的每周精选（绝不强制）。

记录“真的帮助复用旧知识”的匿名可解释反馈、“不相关/打扰”的理由和跳转成功。**不要**以通知发送量、打卡天数或随机停留时长作为核心成功。

## G. 按 PR 交付

| PR | 文件 | 通过条件 |
|---|---|---|
| UX-005A — Candidate engine | `domain/rediscovery.py`、`generate_rediscovery.py`、`rank_rediscovery.py`、`rules.py` | 0..3 有依据候选，噪声和隐私负例 |
| UX-005B — Feedback & Preferences | `rediscovery_repository.py`、`0005_rediscovery.sql`、`record_rediscovery_feedback.py`、`notification_opt_in.py` | 关闭、mute、幂等，重启保留 |
| UX-005C — Calm UI | `RediscoverView.swift`、`RediscoveryCard.swift`、preferences、E2E | 无默认提醒，用户可按需获取 |
| UX-005D — Independent evaluation | `evaluation/rediscovery/**`、`evaluate_rediscovery.py`、实验设计 | 与简单基线比较，有显式反例 |

**DoD**：用户不需要主动维护链接，系统只在能解释“为何值得看”时输出建议；默认不推送，所有推荐可回到确切证据且可以安静关闭。若真实用户更偏好完全不打扰，应允许其完全不使用此模块而仍继续使用 X-Wiki。
