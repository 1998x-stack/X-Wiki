# X-Wiki Product Documentation / 产品文档中心

更新时间：2026-11-03。**产品设计文档 ≠ 功能交付报告**；下述不同阶段请勿混为一谈。

## 真实已交付的内容

- [X-Wiki 代码与运行说明](../../README.md)：Mac Voice Memos → 本地 Whisper → pi 编译 → Markdown/Git → Pages 的现有管线。
- [UX-001 — The First 90 Seconds](UX-001.md)：已部署的免注册、合成数据交互演示。六步审阅、按钮状态与版本变化**仅在浏览器内存模拟**，不是用户个人资料的真实 AI 修改。
- [现有 PRD v1](PRD.md)：第一阶段的产品范围与静态演示验收。
- [现有发布可信度架构](../architecture/deployment-verification.md)：GitHub Pages 的内容指纹/HTTPS 读回。不能用该工程机制代替产品级的每用户权限控制。

## 本次深度研究与待实现规格

1. [Product Hunt × Hacker News 评论证据与需求研究](research/PH-HN-2026.md)：逐条用户评价、原始讨论链接、证据级别、竞争性反例、优先级和调研计划。
2. [PRD v2 — Evidence-First Living Knowledge](PRD-v2.md)：价值主张、用户任务、P0/P1 优先级、真实路径、成功与失败指标。
3. [Knowledge Review Workbench 详细规格](specs/Knowledge-Review-Workbench.md)：Source/EvidenceSpan/Claim/Proposal/Revision 契约、状态机、审批与回滚、证据评测、隐私边界、分阶段 PR。
4. [Product Hunt / Hacker News 发布与用户增长计划](launch/Product-Hunt-Playbook.md)：正式发布前的 Go/No-go、定位文案、素材、用户研究、发布约束、漏斗和复盘。

## 首选工程实施顺序

**真实输入与可靠存储 → 用户可理解的数据流授权 → 独立证据与结构化 ChangeProposal → 人工审阅/批准/撤销 → 既有 Markdown 数据导入 → Decision Recall → 按需 Rediscovery。**

为什么不是先做知识图谱画布？现有评论中的主要痛点是可信度、低摩擦、检索与迁移，自动画连线在同类产品中已不具备足够差异。所有新增能力都应该先用原始评论假设 + 独立用户任务 + 对照基线验证。

**独立成功标准**：当前 UX-001 的自动化测试仅证明演示交互正确；必须再通过真实参与者的首访、可定位的证据评测和生产隐私测试，才能宣称进入可用于消费者的正式版本。
