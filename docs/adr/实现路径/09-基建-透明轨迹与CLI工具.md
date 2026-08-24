# 09-基建-透明轨迹与 CLI 工具

> 状态：**已定（ADR-006）**
> 定位：对应 `001-模块地图.md` 模块⑦——百分百可见作为设计接口；同时是本项目的「检验手段」与「尊重存在」的工程化表达。
> 承接：ADR-006、`02-基础-存储与数据模型.md` 第四/五节。

---

## 一、职责

- 任何一次「她为何这样说 / 这样做」都能从状态快照 + 事件轨迹回放解释；
- 内核侧：状态变化、事件、时间补算全部落迹（自建，真相层天然要求）；
- agent 侧：会话事件 append-only、工具调用可见（dsh session events / 审计）；
- 合并：两侧合并构成**百分百完全可见**的流程（ADR-006）。

## 二、落迹（已定）

| 数据 | 位置 | 格式 | 原则 |
|------|------|------|------|
| 状态变化 | `logs/state-changes.jsonl` | `{ts, seq, source, var, from, to, delta, reason, event_id}` | append-only |
| 事件 | `events/*.jsonl` | `{id, ts, seq, type, payload, source}` | append-only |
| 补算 | 计入 state-changes | `source=time, reason=补算...` | 每笔补算一行 |
| 评价 | 计入 state-changes + `appraisal_result` 事件 | 见 `05` | 评价链路可查 |

- **不变量**：任何状态变化必须有对应轨迹行；否则视为无效修改（ADR-006 后果）。

## 三、可回放（Phase 2）

- `replay(from)`：从 `born_at` 或任意快照，按 `seq` 重放事件与变化；
- **校验**：重放结果 == 当前状态（发现不一致 = bug 或轨迹缺失）；
- 用途：调试、解释「她为什么这么说」、功能主义实验检验（拟合是否成立，可观测）。

## 四、CLI 工具集

| 命令 | 用途 | 阶段 |
|------|------|------|
| `tick [now]` | 显式推进时间（补算 + 落迹） | Phase 1 |
| `apply-event <json>` | 提交事件（补算 → 评价 → 更新） | Phase 1（简化）/ Phase 3（完整） |
| `show-state` | 查看当前状态（含最近轨迹摘要） | Phase 1 |
| `summary` | 输出注入用摘要（纯函数） | Phase 2 |
| `replay [from]` | 轨迹重放与校验 | Phase 2 |
| `log` | 查看/过滤轨迹 | Phase 1 |

- CLI 是内核零依赖运行的证明（Phase 1 验收前置：无工具链也能「过一天、聊一句、看状态变」）。

## 五、与 dsh 轨迹的合并（Phase 2）

```
内核侧：state-changes.jsonl + events/*.jsonl
agent 侧：dsh session events（append-only，工具调用可见）
合并视图：任何一次行为 = 状态快照 + 事件轨迹 + 会话轨迹 → 可回放解释
```

## 六、验收

1. 任意状态变化可解释（from/to/来源/原因/关联事件）；
2. `replay` 重放 == 当前状态；
3. 合并轨迹可解释「她为何这样说/这样做」的完整链路；
4. 无修改、无删除：append-only 语义被 CLI 与内核强制。
