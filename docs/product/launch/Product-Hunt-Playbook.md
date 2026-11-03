# X-Wiki — Product Hunt & Hacker News Go-to-Market Playbook

> 版本：L2026-11-03 | 性质：待验证的发布计划，不代表已经在 Product Hunt 上线或获得排名  
> 关联：[深度产品 PRD](../PRD-v2.md) · [用户评论研究](../research/PH-HN-2026.md) · [Workbench 规格](../specs/Knowledge-Review-Workbench.md)

## 0. 先确定“发布什么”，而不是先确定榜单名次

**发布目标**：首批高质量目标用户能在真实任务中体验 X-Wiki 如何把时间分散的新旧记录变为可审阅、有证据、有历史版本的知识，并愿意继续使用。Product Hunt 是获取访问、访谈与早期用户的渠道，不是产品价值的唯一裁判。

### 两条发布路径，必须择其一并如实叙述

**路径 A — 开源开发者工具早期展示**：
- 目标人群：Mac + Voice Memos + Markdown/技术用户；
- 产品真实能力：现有的本地 pipeline（必须经过独立实际 Mac E2E）、合成 UX-001 展示、代码和架构；
- 所有 Maker 文案明确“demo 是 synthetic，不是实时 AI 审阅”，且桌面 UI、文件导入/Review 未实现；
- 目的：获得工程贡献者、合成演示的反馈；**不能**据此宣传完整消费者 AI App。

**路径 B — 首次正式消费者产品发布（推荐在达到 P0 后）**：
- 必须有无命令行文件导入、Source 保存真实可靠性、至少一个真实 Evidence-linked Review、用户批准/撤销、外发权限控制、可导出；
- 如果只有漂亮 landing 和模拟交互，不能冒充该路径的成品。
- 把“知识演化”而不是语音识别精度作为产品主画面。

### Go / No-go Gate

| 门槛 | A 开源工具展示 | B 消费产品发布 |
|---|---|---|
| 合成演示真实可点击、加载快速、公开说明 | 必须 | 必须 |
| GitHub repo 真实可复现、安装手册准确 | 必须 | 必须 |
| 实际 Apple Silicon 转写及 Git/Pages 端到端 | 强烈建议 | 必须 |
| 无命令行导入用户自己的资料 | 不要求，但须明示未实现 | 必须 |
| Source → Claim → Proposal → Review 用户批准写回 | 不要求，但不能假称具备 | 必须 |
| 故障注入、私有数据负面测试和透明外发授权 | 技术链路范围内完成 | 必须 |
| 15–20 人无引导的首访任务测试 | 建议 | 必须 |
| 模型引用评测、人工核验 | 可标记路线图 | 必须 |
| 公网 Pages read-back 与有效源代码链接 | 必须 | 必须 |

## 1. 产品心智：不要叫“another second brain”

### 一句话差异

**X-Wiki turns scattered notes into revisable knowledge — with evidence and your approval.**

这比“AI 语音笔记”“自动知识图谱”“与所有笔记对话”更接近真实可检验结果，因为每句话都能在 UI 找到对应动作：Source、Diff、Evidence、Approve、History。

### 可做 A/B 研究的三种定位

- **M1（较具体）**：“See how your thinking changes, with the notes that prove it.”
- **M2（技术用户）**：“Version control for your ideas — not another notes app.”
- **M3（可信控制）**：“Your thoughts evolve. Your knowledge should too.”

请 15 人浏览陌生首页 10 秒后，用自己的话解释产品做什么。指标：理解率、与已有笔记工具的区别是否说对、是否认为是静态展示。不要自称 M3 必定最好。

## 2. Product Hunt 发布页草案（正式版本须按真实能力收窄）

**Name**：X-Wiki  
**Tagline**：Your thoughts evolve. Your knowledge should too.  
**Description**（英文，核对 Product Hunt 当前 260 字符上限）：

> X-Wiki connects new notes with old ideas, shows the evidence behind suggested changes, and lets you approve what becomes knowledge. Try the interactive demo, explore the open-source Mac pipeline, and keep your thinking under your control.

**本段是路线图版本的营销草案，不可在真实 Change Review 未实现时暗示导入任意用户资料就能产生真实审批；若近期发布路径 A，需改为**：

> Explore an open-source Mac voice-to-Markdown knowledge pipeline and a fictional, interactive preview of evidence-linked knowledge revision. The demo runs entirely in your browser; production review features are still in development.

### 发布媒体的顺序

1. 第 1 张：一句“Your notes shouldn't stay frozen.”，可见旧观点与新证据之间的对应关系；不能只展示抽象知识图谱。
2. 第 2 张：界面 screenshot：Before / Proposed / Evidence，两条引用都能点击定位。
3. 第 3 张：用户批准后知识节点内容变化 + Revision History + Undo。
4. 第 4 张：Private-by-default Data Flow（Whisper local / configured pi provider / export / public sharing），避免含糊声称“全本地”。
5. 45–60 秒演示视频：从旧观点、新记录、关联、建议、来源、批准，到历史版本；区分合成与真实功能，禁止用不可实际执行的动作装作实机。

注意 Product Hunt 目前官方指引：tagline ≤60 字符、description ≤260 字符、最多 3 个话题、可附 GIF/视频、Maker 第一条评论、发布从预定日期太平洋时间 00:01 开始；官方明确禁止索取 upvote 或为投票提供奖励。最新规则需临近发布再核验：
- https://help.producthunt.com/en/articles/17350772-launch-guide
- https://www.producthunt.com/launch
- https://www.producthunt.com/launch/preparing-for-launch

## 3. Maker 第一条评论模版（需与实际交付一致）

> Hi Product Hunt! I'm building X-Wiki because I kept collecting voice notes, yet my thinking never seemed to get any clearer. I'd end up with more transcripts, not a better understanding of what had changed.
>
> The idea is simple: when you encounter new evidence, your existing knowledge should be revisable. But AI should never silently rewrite your point of view. You should be able to see the original source, the proposed change, and decide what becomes part of your knowledge.
>
> Today we're sharing [state the real available product: an open-source Mac pipeline / a complete user-facing beta]. You can also try a clearly labeled fictional browser demo that shows the intended experience without uploading personal data.
>
> I'd love feedback on one question: would you rather have suggestions pushed to you, or only see them when you decide to review your notes? I'd also love to hear where your current notes workflow breaks.

如果真实 Beta 尚未具备 Evidence-linked Review，不能把评论中 “AI proposes a revision” 描述为已交付。

## 4. HN 社区策略与 PH 的不同

HN 用户更容易追问：
- 源码能否核对？本地模型与外部 provider 的边界是什么？
- 为什么自动连边不是语义噪声？独立负例测试和数据集在哪里？
- 为什么不用 Obsidian 插件？为什么要迁移用户的 Markdown？
- 文件损坏/撤销/冲突后能恢复吗？
- 数据路径有哪些，模型拿到了什么明文？
- 所谓“AI 知识进化”到底是可复现算法还是 Demo 演戏？

**HN 正确叙事**：问题、架构权衡、可复现实验、失败案例与数据边界，不是流行语堆砌。标题示例：

- 路径 A：`Show HN: X-Wiki, a voice-to-Markdown knowledge pipeline with versioned releases`
- 路径 B：`Show HN: X-Wiki – review evidence before your AI updates your notes`（B 真实存在后才使用）

发布中应主动披露“合成 demo”“pi external provider 可选”“当前支持 Mac”及许可证/系统要求。准备 README 中一条 5 分钟可复现的真实路径；如果需要数十行装机命令，公开地展示限制并寻求反馈，不要隐藏。

## 5. 发布前 4 周执行路线

| 时间 | 具体动作 | 可检查的交付 |
|---|---|---|
| T-28～T-21 | 冻结产品目标用户、挑选 5 位高风险怀疑者访谈；理解为什么不信任 AI 关联 | 访谈记录、需求反例、优先级变化 |
| T-20～T-14 | 运行 15–20 人无提示 Demo 测试，找出误解、临界点、隐私疑问；发布对照反例 | 首次价值耗时、理解率、掉队点 |
| T-13～T-8 | 完成路径 A/B 对应的真实功能 Gate；安全/可靠/无障碍/安装 E2E | Release Candidate + 独立测试报告 |
| T-7～T-4 | 编写英文 landing，准备四张真实截图、短视频、FAQ、Maker 评论；预审产品页 | 可验证的发布素材、无假图片 |
| T-3～T-1 | 用生产 URL/当前发布版本做最终回归，确保 webhook、下载与演示均可用 | HTTP 读回、手工浏览器走查、撤销可用 |
| T-0 | Product Hunt 启动，Maker 在线回答真实质疑，收集需求不是索票 | 真实用户评论和有效产品事件 |
| T+1～T+7 | 发布透明回顾：留存、首次成功、阻塞、最想解决的问题，逐条改产品 | Retro + 用户证据汇总 + 下一次决定 |

发布规则：不要购买票数、互投、索要 upvote 或要求用户投票换福利；应邀请他们试用并给出评论/具体意见。绝不发布伪造支持者 logo、伪造用户评价或伪造基准成绩。

## 6. 增长漏斗与仪表盘：优化真正的价值

**认知层**：查看访客来源与产品定位是否理解；当前 UX-001 演示刻意**不采集任何遥测**。在用户同意前不能暗中加追踪。首阶段用可见手工测试；未来只有在匿名化告知/同意机制下才增加漏斗事件。

**转化层**（真实产品 Beta）：
- `visit → demo_start → evidence_open → demo_complete`：网页 Demo 完成，不代表真实功能激活；
- `installer_start → local_source_stored → first_real_proposal → first_approved_revision`：真实用户激活；
- `approved_revision → revisited_revision within 28d`：长期价值。
- 容忍“no_change”合法结果，不能以没有生成提案将其算为管道失败。

**北极星**：真正重用过的、经用户批准的知识节点（按有效用户计）。辅助指标：引用正确率、错误自动行动率、隐私事件数、提案拒绝理由、未处理建议累积量、卸载/导出成功率。

**分组/质量**：按新用户 vs 已有 Vault、Mac vs 其他系统、语音 vs 文字输入、当地设备模型 vs 可选外部 provider 比较。不要把不同路径的数据混在一条转化率中。

### 推荐的停止条件

- 用户无法区分合成 Demo 和真实模型：**停止发布宣传**，修正文案；
- 原始录音导入成功却丢失、私密材料外泄、未授权发布：**阻断正式发布**；
- 关联错误高、用户拒绝率高、独立评审无法复核来源：**停止扩展自动化**，优先优化 evidence gate；
- 引入真实传输或分析前没有隐私授权：**禁止启用**；
- 仅有 Product Hunt 排名、没有真实产品启用：不得宣称已证明 PMF。

## 7. 价格策略（假设，不是已有结论）

对本地开源用户，收费要换回可衡量的价值，而不是只为“AI”命名收费。按以下顺序测试：
1. 免费：可导出 Markdown、自己掌握数据、基础演示与本地原理文档；
2. 可选择的付费便利：桌面免配置、可靠导入、可审阅的历史视图与导出工具；
3. 自选的云/托管模式：在明确的许可、保留与隐私条款下才支持。

不要在缺少真实支付实验和模型推理成本数据前发明 ARR、GMV、付费转化率。

## 8. FAQ：需要提前准备的质疑

**Q：为什么不直接用 ChatGPT 处理转录？**  
A：X-Wiki 的目标是长期可审计的来源、知识版本、用户审批和直接拥有文件。如果这些效果不能比手工 ChatGPT 更好，应让用户继续使用已有工具。

**Q：它是完全本地的吗？**  
A：当前 Whisper 转录在支持的 Mac 本地运行，但知识编译链可能调用用户配置的外部 LLM provider。绝不能笼统写“完全离线/所有数据留在本地”。未来需按功能显示真实数据流和权限。

**Q：它已经会自动更新我的真实知识库了吗？**  
A：目前的静态浏览器 Demo 是人工合成故事，批准操作只更新页面内存。真实可审阅工作台是规划中的产品阶段，不可把 Demo 当成已上线能力。

**Q：我可以导出/继续使用 Obsidian 吗？**  
A：底层知识使用 Markdown/Git。正式 Vault 兼容与无损批量导入仍需独立测试，不能保证所有 Obsidian 插件语法无损。

**Q：AI 连接错了怎么办？**  
A：应支持来源定位、拒绝、标记无关、恢复旧版本与明确未知；在真实 Workbench 未完成前，这是产品验收要求而非既有 UI。

**Q：为何还要一个软件？**  
A：只有在“长期、可验证、可撤销的知识修订”对真实用户工作有明显收益时才有理由；否则更好的方案可能是已有软件的插件。

## 9. 成功与失败的复盘

Product Hunt 当日排名、票数及榜单展示受外部因素影响，不能保证 Top 1。产品上线后 7 天、28 天分别汇报：

- 首次操作完成率、有效知识修订率、真实用户的案例；
- 任务成功与失败场景、人工审阅耗时；
- Evidence 假阳性与无来源幻觉；
- 用户主动回访和重新使用旧知识；
- 用户离开/卸载/不愿导入的具体理由；
- 发现的竞品反例和导致路线改变的用户评论。

**决策门槛**：如果用户只说“设计很漂亮”但没有真实导入或复用，继续打磨 First Real Value，**不要为第二次榜单冲刺而优先堆营销功能**。
