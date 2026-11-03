# REL-006｜Product Hunt Release：真实产品验收、安装、隐私与发布工程

> 状态：**设计方案，尚未完成**｜前置 UX-002/003 的真实可用链路与 UX-004/005 的明确取舍。  
> 价值检验：**用户能完成真实工作，且知道什么是当前已实现的能力**；Product Hunt 排名不是产品质量保证。

## A. 发布路径与停止条件

有两条绝不混淆的发布路线：

**A / 开源开发者预览**：现有 Mac Voice Memos → 本地 MLX Whisper → Markdown → GitHub Pages 管道，经真实 Apple Silicon 设备实测后，以开源工具形式发布；`/demo/` 清楚标记 synthetic。无需宣传“真实 AI 审阅工作台已上线”。

**B / 面向普通用户的正式 Product Hunt 上线**：必须完成真实文件导入、外发授权、证据可定位的修订建议、人工批准与撤销、独立的公开分享权限、可迁移 Markdown；真实产品行为经过用户测试，不依赖合成页面作主证据。

发布任何一条路线前先执行 **Launch Gate**。安全门槛为零容忍：未经同意外发、原始文件丢失、公开私有内容、错误引用直接变成已批准事实。失败必须 fail closed，不以“稍后补救”为上线理由。

## B. 文件级发布工程

| 文件/目录 | 操作 | 内容 | 验收 |
|---|---|---|---|
| `apps/desktop-macos/Package.swift` 或原生 Xcode project | ADD | Mac 桌面构建、应用名、权限和资源打包 | 签名运行、干净 Mac 可启动 |
| `apps/desktop-macos/Resources/Info.plist` | ADD | 麦克风/文件/模型网络权限说明（按真实使用能力） | 真实系统弹窗说明准确 |
| `apps/desktop-macos/Services/PythonWorkerBridge.swift` | EXTEND | worker 生命周期、安装版本、错误恢复、权限状态 | 终止 worker 后 UI 不谎报成功 |
| `scripts/doctor.py` | MODIFY | JSON diagnostics、FFmpeg/Whisper/Apple permission 状态；能在 App 内诊断 | 没有 Shell 技能的用户也看懂错误 |
| `src/xwiki/application/healthcheck.py` | ADD | 检测 DB migration、模型可用性、source store、private/public 规则 | 明确 supported/degraded/blocked |
| `src/xwiki/application/export_portability.py` | ADD | Markdown/来源/历史的导出清单 + checksum；不自动推送 | 迁出再导入可校验 |
| `src/xwiki/application/privacy_preflight.py` | ADD | 调用前展示发送对象、字段范围、provider 目的、权限 | 未批准不能实际调用外部模型 |
| `src/xwiki/application/publication_preflight.py` | ADD | 逐页选择公开、来源脱敏、精确 preview、人工确认 | 私有内容不因 review approved 而进入 Pages |
| `src/xwiki/infrastructure/publication/public_exporter.py` | ADD | 从 private approved 节点生成 allowlisted public bundle | 公共 URL 与私有数据分离 |
| `scripts/wiki_lint.py` | MODIFY | 高风险字段/绝对路径/私人引用检测与 negative tests | 所有 public export 通过 |
| `scripts/prepare_site.py` | MODIFY | 只接受显式发布 bundle、拒绝私有路径 | 无暗中从 `.state/` 拷贝内容 |
| `scripts/release_gate.py` | REUSE | Git branch & content fingerprint; push 状态核验 | 代码与内容版本明确 |
| `scripts/verify_deployment.py` | REUSE | HTTPS 读回 manifest 证明实际公网内容版本 | 不将 Git push 成功当公网部署成功 |
| `docs/security/data-flow.md` | ADD | 精确描述本地存储、provider 外发、日志、遥测、分享 | 用户能解释数据去向 |
| `docs/security/threat-model.md` | ADD | STRIDE/攻击面、local IPC、文件/符号链接、token、注入 | 风险追踪与发布阻断 |
| `docs/legal/privacy-policy.md` | ADD | 根据真实数据流撰写，不捏造“无数据收集” | 各项与可测实现相符 |
| `docs/user/install-macos.md` | ADD | 下载→安装→模型选择→首次导入→回滚/卸载 | 外部用户无终端完成 |
| `docs/user/migrate-markdown.md` | ADD | 导入/导出及与 Obsidian 的兼容边界 | 不宣称未实测全兼容 |
| `docs/launch/PH.md` | ADD | 与 PRD v2 保持一致的发布素材和 Maker 文案 | 产品实际能力一致 |
| `.github/workflows/release-desktop.yml` | ADD | 构建、签名/公证、测试、SBOM/checksum、手动发布 | 缺 secret 报错，不伪造签名 |
| `.github/workflows/privacy-gate.yml` | ADD | 严格扫描 public bundle、不泄漏测试数据、错误外发 E2E | 隐私失败直接阻断 |
| `.github/workflows/pages.yml` | MODIFY | 继承已存在 Quality+Playwright+HTTP readback | 演示页面和公开知识都可用 |
| `tests/e2e/rel-006-publish.spec.cjs` | ADD | 公开前预览、默认私有、取消、确认发布、撤销 | 关闭页面不会意外发布 |
| `tests/integration/privacy/test_network_consent.py` | ADD | 未许可出站拦截、拒绝后不发送、撤回后不重试 | 一次非法外发即 FAIL |
| `tests/integration/privacy/test_public_bundle.py` | ADD | raw/audio/transcript/private token/真实路径全部不进入 public | allowlist 必须正确 |
| `tests/integration/export/test_roundtrip.py` | ADD | Markdown 导出再导入，source/revision refs 一致 | 可迁移性而非只是下载 ZIP |
| `evaluation/product/onboarding-research.csv` | ADD（仅同意的匿名指标） | 研究计时结果、任务状态、误解类型 | 无个人私有录音/标识 |
| `docs/product/launch/Product-Hunt-Playbook.md` | MODIFY | 根据真实产品能力更新发布页文案，不夸大 | Maker 评论可核对 |

## C. Release Gate 五层验证

```text
L1 | Correctness   schema + migration + unit/integration + CI
L2 | Safety        private/public boundary + permission + fault injection
L3 | Experience    UX-001 synthetic demo + REAL import/review on target device
L4 | Evidence      blinded claim evaluation + user usability + retrieval holdout
L5 | Distribution  signed macOS installer + public URL live read-back + docs
```

### 各层自动化必须承担的责任

1. **L1**：旧 `scripts/tests`、新增 `tests/unit`、`tests/integration`、`evaluation/review` 均绿；安装/升级 SQLite 不能静默损失旧数据。
2. **L2**：模拟“原始数据包含绝对路径、账号、邮件、token、私人姓名”时，公开预览/导出不可泄漏；未经授权的 provider 网络请求必须被拦截。
3. **L3**：至少一次真实 Apple Silicon Mac 系统端到端导入、转录、Proposal、审批、撤销、隐私选择、可导出。现有 macOS Core Smoke 是合成测试，不等价。
4. **L4**：评测结果必须使用冻结的独立数据与人工 adjudication；15–20 名没有提前学过页面的受试者做真实任务。不能把 demo 的 12 个 Playwright 测试等同用户验证。
5. **L5**：GitHub Release 资产附源码版本/依赖/校验和；Pages manifest 实际 HTTPS 读回；安装包来源可靠且版本匹配。

### CLI 设计（目标，未实现）

```text
xwiki doctor --json
xwiki import <path> --dry-run
xwiki source verify --all
xwiki proposals evaluate --fixture evaluation/review/
xwiki review audit --private
xwiki export --dry-run --selected <node_ids>
xwiki publish preview --selected <node_ids>
xwiki release check --target producthunt-b
```

最终 `release check` 输出机器可读 `gate_id/pass/fail/evidence_uri/checked_at/commit_sha`，对未采集的真人测试不得填 true。

## D. Threat Model（发布前必须落地）

| 风险 | 攻击路径 / 错误 | 所需防护 |
|---|---|---|
| Model prompt injection | 私有来源夹带指令，要求读取其他文件或执行 Git/网络 | Candidate-only adapter、最小权限、structured output、独立审批 |
| Local service abuse | 其他网页利用 localhost API 读取私人文件 | Loopback + origin + nonce + CSRF/permission、优先系统 IPC |
| Hidden publish | 审批知识时误触 Git push | 审批与公开发布两次明确操作，默认 private |
| Private metadata in public | 原始音频名/路径/地理信息从 Markdown 或日志泄漏 | 允许字段白名单、人工预览、负向测试 |
| Crash during review apply | DB 已 approved、文件未写全 | outbox + durable journal + restart reconcile |
| Broken citation | Source transcript 更新后 old span offset 失效 | SourceRevision hash、quote hash、引用有效性检测 |
| Release supply chain | 不可靠依赖/下载/未签名安装器 | 依赖锁定、SBOM、资产 SHA、签名/公证、下载路径透明 |
| Analytics privacy | 访客追踪 SDK 偷偷发送私人文本 | 默认不收集内容、取得授权后只记最低限度事件 |

## E. Product Hunt 与 HN 两种沟通方式

**Product Hunt** 展示具体用户价值：两个相隔时间的真实记录与可验证的观点变化，不从系统图开场。素材 4 张截图、45–60 秒真实演示，描述用户如何审阅证据与撤销修改。提供一条明确的 `Try demo`，并在有真实产品后提供 `Get Mac app`。

**Hacker News** 强调可复现性：源码、示例 fixture、false-positive 负例、LLM 外发说明、为什么不直接做 Obsidian 插件、怎样保护用户 Markdown、什么情况下明确 no_change。公开技术负例比空泛准确率更有说服力。

必须遵守 Product Hunt 当前发布条款与活动边界：不能买票、交换投票、用奖励换 upvote；发布日期/标签/媒体上限临近发布重新核验。具体文案在 [发布手册](../launch/Product-Hunt-Playbook.md)。

## F. 发布前后的实验指标

目标指标属于**假设门槛**：

| 指标 | 推荐门槛 | 外部裁判 |
|---|---|---|
| 演示首次价值理解率 | ≥80% 新受试者能用自己的话复述有证据修订 | 非引导式用户研究 |
| 真实导入成功且 hash 可验证 | 100% 标记成功的样本 | 故障注入与重读校验 |
| 错误 source citation 进入 approved | 0 | 独立证据负例 |
| 未授权外发或公开 | 0 | 网络拦截与 public diff |
| Review 被真正使用 | 测量批准/拒绝/跳过并分场景 | 用户自愿参与的匿名 cohort |
| 28 天知识复用 | 与普通摘要基线做对照，不能虚构成绩 | 真实任务与自愿标注 |
| 安装失败后恢复 | 用户能明确理解下一步 | 外部受试者 |
| Product Hunt 排名 | 仅观察，不作为放行条件 | 平台实际结果 |

如果用户看完 demo 只觉得“动画不错”，但导入自己两段资料后没得到值得确认的知识变更，则应迭代 UX-002/003；不能靠增加通知和图谱掩盖核心价值失败。

## G. 逐 PR 交付和最终结论

| PR | 文件/范围 | DoD |
|---|---|---|
| REL-006A — macOS distribution | `apps/desktop-macos/**`, `release-desktop.yml`, `install-macos.md` | 干净系统安装、卸载、真实模型下载透明 |
| REL-006B — Data/Privacy Gate | `privacy_preflight.py`, `publication_preflight.py`, `public_exporter.py`, `privacy-gate.yml`, `tests/integration/privacy/**` | 未授权外发/公开=0 |
| REL-006C — Export & Recovery | `export_portability.py`, `roundtrip` 与故障测试、文档 | 私有知识和版本可以真实迁移 |
| REL-006D — Launch Analytics & Validation | `evaluation/product/**`, `docs/launch/PH.md`, 发布手册更新 | 同意后匿名指标、外部人类任务、真实素材 |
| REL-006E — Release Candidate | RC tag、`release check`、所有 Actions、Pages read-back、安装包校验 | 5 层门禁全部 PASS |

**最终 DoD**：对外的每一句产品描述都能找到对应真实 UI、可复现真实输入、可查询来源、明确权限与回滚机制。没达到路径 B 的条件时，只能发布为开发者预览，不标榜消费者完整产品上线。
