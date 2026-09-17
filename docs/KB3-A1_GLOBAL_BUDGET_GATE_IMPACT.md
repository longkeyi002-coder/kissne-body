# KB3-A1 Global Budget Gate：影响面盘点（合同阶段）

- 基线：`00e60228b5988c1aea69027244cd1b36687ef82a`
- 目标：只盘点入口、冻结外部合同、添加 RED 骨架；本文件不代表已接线。

## 已确认的模型调用汇聚点

| 入口 | 位置 | 当前形态 | A2 处理 |
|---|---|---|---|
| 主对话 | `agent/turn_api_call.py::perform_api_call` | 经 `run_llm_execution_middleware`，再走 streaming/non-stream transport | 首要接线点 |
| 辅助统一 API | `agent/auxiliary_client.py::call_llm` / `async_call_llm` | 负责 resolve → client → request → retry/fallback | 第二个首要接线点 |
| MoA | `agent/moa_loop.py:391,842,1109` | 多次调用 `call_llm` | 作为辅助调用计费/预算维度 |
| 压缩 | `agent/context_compressor.py:3250` | 调 `call_llm` | 不得绕过辅助 Gate |
| 微压缩 | `agent/micro_compaction.py:136` | 调 `call_llm` | 不得绕过辅助 Gate |
| 标题/oneshot | `agent/title_generator.py:297`、`agent/oneshot.py:104` | 调 `call_llm` | 使用 task/category policy |
| Profile/Goals/Kanban | `hermes_cli/profile_describer.py:153`、`hermes_cli/goals.py:880`、`hermes_cli/kanban_specify.py:162` | 调 `call_llm` | 作为非主对话任务 |
| 原生低层调用 | `agent/chat_completion_helpers.py:707,708,2106,2723`、`agent/codex_runtime.py:932` | 存在直接 SDK/Responses 调用 | A2 必须明确封口或声明豁免 |
| API Runs | `gateway/platforms/api_server_runs.py:380+` | 启动独立 run，随后进入 Agent | 预算应在实际模型调用处统一扣账，不能只在 HTTP 入站扣账 |
| Background review | `agent/background_review.py:1055` | 启动 review agent | 需继承/显式传递预算上下文 |
| Cron / Wake | `hermes_cli/cron.py`、`gateway/wake.py` | 调度或触发 Agent | 需确认最终是否进入主/辅助汇聚点；不得通过调度层绕过 Gate |

## 已有但不能直接当作 Global Gate 的能力

- `agent/turn_usage.py::record_response_usage`：记录 provider 返回后的 token/cost，不是调用前 Gate，无法阻止已发出的请求。
- `agent/aux_accounting.py::record_aux_usage`：辅助调用后的 best-effort 记账，不能承担强制预算闸门。
- `agent/retry_utils.py`：提供 retry-after/backoff 工具，不是全局 retry 上限或预算账本。
- `agent/iteration_budget.py` / `run_budget_seconds`：运行时/迭代预算，不等价于跨入口模型调用预算。
- `gateway/platforms/api_server_run_idempotency.py`：HTTP run 幂等，不等价于模型调用账本。

## A1 冻结的外部合同

1. `BudgetPolicy` 是不透明策略输入；默认额度不写死在本票。
2. 预算账本使用抽象的整数 `units`；A1 不规定 units 与 token、金额或调用次数的映射，映射由 policy/调用方提供。每次 `reserve(category, units, action_id)` 必须先建立唯一 reservation，再允许模型调用。
3. `settle(reservation_id, outcome, actual_units)` 结算成功或失败；不得把一次已建立的 reservation 重新当作新的 retry 额度。
4. 未知结果保持占用，直到显式 `reconcile(reservation_id, outcome, actual_units)`。同一 reconciliation 重放必须幂等；冲突的重复结果必须 fail closed。
5. `BudgetDecision` 必须结构化，至少区分 `allowed`、`budget_exhausted`、`rate_limited`、`invalid_policy`、`retry_blocked`。
6. Work / Learning / Life-Exploration / Social / Repair Reserve 独立记账；日常类别不能消费 Repair Reserve。
7. 每次 admit、deny、reserve、settle、reconcile 都必须留下可查询的审计记录，至少含 action/reservation、category、units、结果、时间和 reason。
8. ledger 必须跨进程/重启可恢复，使用独立于会话 `state.db` 的专用持久化存储；不得出现第二套按入口各自记账。
9. Gate 拒绝后不得再调用模型生成解释文本。
10. A1 不改变任何现有模型调用路径；A2 才逐入口接线。

## A2 前置与风险

- 先封住原生低层调用点，否则只接 `perform_api_call` 和 `call_llm` 会留下绕过路径。
- Provider Recall 以后作为调用方接入同一 Gate，不创建自己的预算账本。
- 现有 token/cost 记账保留为事实记录；预算账本不能重复替代它。
- E2E 测试需要固定、不耗尽的 policy；预算耗尽场景单独测试。
- A1 RED 测试故意在旧基线下失败；没有任何真实 provider、网络或线上配置参与。
