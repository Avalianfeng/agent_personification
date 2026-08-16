# dsh 结合评估（流程与线路）

> 写于 2026-08-16。评估对象：`D:\deepseek-harness`（DeepSeek Harness，`dsh`）。
> 结论先行的流程盘点；细节以后续实践为准。

---

## 一、结论

可以结合，且结合形态恰好符合 `00-立场与世界观.md` 的"不绑定某一 Agent 框架"立场：

- dsh 是**一切皆插件**的本地 agent harness（无特权核心，agent-loop 本身可替换），本地跑 Web UI（默认 `127.0.0.1:3080`）、headless、JSON-RPC、Python SDK、ACP；
- 原计划中 Phase 2 要自建的对话层（chat API、会话管理、事件日志），dsh 全部现成；
- 项目的魂（State Core、时间引擎、Appraisal）dsh 没有，仍需自建；
- 结合形态：**独立内核（自建、零依赖）+ 薄适配层（挂到 dsh）**。dsh 处于开发者预览、破坏性变更预期中，此形态让框架可替换。

一个契合点：`dsh-persona` 是 prefix-stable 的静态人格文本，动态内容走 `agent/pre-step` / context provider——dsh 架构天然区分「惯性层」与「实时层」，即本项目「人格是惯性而非实时结论」的工程化表达。

---

## 二、流程盘点：直接用的

| 原计划要自建 | dsh 现成对应 | 备注 |
|---|---|---|
| Phase 2 简单 chat API | Web UI / headless / CLI / JSON-RPC / Python SDK / ACP | 对话产品层整个省掉 |
| Phase 1 events 日志 | `core/session`：append-only SessionEvent + SQLite，可重放 | 附带不变量「Model-visible ⟺ logged」 |
| 用户回复回流为事件 | 订阅 `session/event` | 评价引擎的输入源 |
| 状态摘要注入对话 | `agent/pre-step` waterfall、`agent.inject()`、context provider | `time-context` 为现成参考 |
| 定时 / 周期性醒来 | `schedule` 包（会话内定时） | 硬限制：仅 live agent 时运转，见决策点 1 |
| 需求 / 目标载体 | `goal` / `todo` / `plan` | 会话级；真相层仍在自己手里 |
| 后台任务 / 周期反思 | `jobs` 包 | 沉积/反思挂载点 |
| 本地模型 | llm seam `baseURL` 可指本地 OpenAI-compatible 网关 | 完全本地成立 |
| 工程外围 | settings / credentials / storage / sandbox / guard / compaction / session-query | 不必自建 |

## 三、必须自建的

1. **State Core**：连续变量 + 衰减/耦合 + 真相层写保护（禁 LLM 直接改写）——独立包，零 dsh 依赖；
2. **时间引擎**：tick 语义与补算（衰减=时间差纯函数，读取时补算无损）；
3. **Appraisal 引擎**：事件 → 评价 → 状态，规则为主、LLM 辅助可关；
4. **摘要渲染器**：数值 → 自然语言提示（dsh 只提供注入点）；
5. **沉积/反思**：痕迹 → 强化 → 稳定特征的滞后机制；
6. **dsh 适配插件**（薄层）：事件回流 + 状态注入 + `show-state`/`apply-event` 工具。

## 四、三个架构决策点

1. **无进程时的演化**：dsh `schedule` 只在 live agent 时运转。衰减用**补算**（无损）；「主动醒来发消息」才需外部守护进程或外部 cron 调 headless。
2. **Model-visible ⟺ logged**：状态放 `storage`（非会话存储），注入渲染为状态快照的**纯函数**；或把摘要记成 session event。选前者。
3. **语言边界**：dsh 内插件必须 TS；内核语言自由。想用 Python 则走 JSON-RPC SDK 独立进程。推荐：内核独立包 + 适配层 TS。

## 五、线路调整（对 `02-计划.md` 的增量）

- **Phase 0**：本文件即新增部分。
- **Phase 1**：不变——纯程序、无 LLM、无 dsh。内核不被开发者预览绑架。
- **Phase 2**：验收标准不变，载体由「自建 chat API」改为「dsh 适配层」（事件回流 + pre-step 注入 + 工具暴露），dsh Web UI 当对话产品。
- **Phase 3 / 4**：不变；事件源来自 dsh；`goal` 作会话级需求载体。
- **Phase 5**：dsh 适配层升为默认外设，取代原 OpenClaw adapter 候选。

近期下一步：

1. Phase 1 最小 `state` + `time` 原型（主线）；
2. dsh 本地 headless 冒烟（半天内，不加状态逻辑），验证完全本地流程成立。

## 六、风险

- dsh 开发者预览、破坏性变更预期 → 适配层保持薄、版本 pin；
- `schedule` 语义与「沉默衰减」不同 → 衰减靠补算，不靠定时器；
- Windows 本地：dsh 支持（pwsh provider、drive-letter 处理），可行。

---

## 七、一句话

> dsh 补足「嘴与外设」，我们只建「体积」：独立内核自建，dsh 上只挂一层薄适配；原 Phase 0–5 路线仅 Phase 2 载体与 Phase 5 外设两处调整。
