# X-Wiki Product Documentation / 产品文档中心

更新时间：2026-11-03。**产品设计文档 ≠ 功能交付报告**；下述不同阶段请勿混为一谈。

## 真实已交付的内容

- [X-Wiki 代码与运行说明](../../README.md)：Mac Voice Memos → 本地 Whisper → pi 编译 → Markdown/Git → Pages 的现有管线。
- [UX-001 — The First 90 Seconds](UX-001.md)：已部署的免注册、合成数据交互演示。六步审阅、按钮状态与版本变化**仅在浏览器内存模拟**，不是用户个人资料的真实 AI 修改。
- [现有 PRD v1](PRD.md)：第一阶段的产品范围与静态演示验收。
- [现有发布可信度架构](../architecture/deployment-verification.md)：GitHub Pages 的内容指纹/HTTPS 读回。不能用该工程机制代替产品级的每用户权限控制。

## 当前工程演进

- [UX-002A 真实文件可靠导入](stages/UX-002A-Implementation.md)：独立私有 Blob Store、验证后保存、重复导入幂等、错误回滚。尚无 Mac 桌面 UI。

- [ARCH-00C 私有与公开执行边界](../architecture/adr-00c-private-public-boundary.md)：私有候选、人工文件审批、公开提升分离；仅代码级阶段，无真实用户身份授权。

- [ARCH-00B SQLite 持久化与旧库只读迁移](stages/ARCH-00B-Implementation.md)：新产品数据库与已有 Voice Memos 处理记录隔离；尚未完成私有发布授权。

## 本次深度研究与待实现规格

1. [Product Hunt × Hacker News 评论证据与需求研究](research/PH-HN-2026.md)：逐条用户评价、原始讨论链接、证据级别、竞争性反例、优先级和调研计划。
2. [PRD v2 — Evidence-First Living Knowledge](PRD-v2.md)：价值主张、用户任务、P0/P1 优先级、真实路径、成功与失败指标。
3. [Knowledge Review Workbench 详细规格](specs/Knowledge-Review-Workbench.md)：Source/EvidenceSpan/Claim/Proposal/Revision 契约、状态机、审批与回滚、证据评测、隐私边界、分阶段 PR。
4. [Product Hunt / Hacker News 发布与用户增长计划](launch/Product-Hunt-Playbook.md)：正式发布前的 Go/No-go、定位文案、素材、用户研究、发布约束、漏斗和复盘。

## 每阶段代码文件级工程设计

- [六阶段总览与 27 个建议 PR](stages/README.md)
- [ARCH-00 — 包架构、领域模型与迁移](stages/ARCH-00-Foundation.md)
- [UX-002 — First Real Value：真实导入](stages/UX-002-First-Real-Value.md)
- [UX-003 — Knowledge Review：证据与审批](stages/UX-003-Knowledge-Review.md)
- [UX-004 — Decision Recall：检索与引用](stages/UX-004-Decision-Recall.md)
- [UX-005 — Calm Rediscovery：低打扰重新发现](stages/UX-005-Calm-Rediscovery.md)
- [REL-006 — 产品验收、Mac 发布与 Product Hunt](stages/REL-006-Product-Hunt-Release.md)

每份文档均区分真实现状与待实现路径，并细化到 ADD/MODIFY 文件、函数职责、SQL、测试文件、失效路径、独立验收。

## 首选工程实施顺序

**真实输入与可靠存储 → 用户可理解的数据流授权 → 独立证据与结构化 ChangeProposal → 人工审阅/批准/撤销 → 既有 Markdown 数据导入 → Decision Recall → 按需 Rediscovery。**

为什么不是先做知识图谱画布？现有评论中的主要痛点是可信度、低摩擦、检索与迁移，自动画连线在同类产品中已不具备足够差异。所有新增能力都应该先用原始评论假设 + 独立用户任务 + 对照基线验证。

**独立成功标准**：当前 UX-001 的自动化测试仅证明演示交互正确；必须再通过真实参与者的首访、可定位的证据评测和生产隐私测试，才能宣称进入可用于消费者的正式版本。
