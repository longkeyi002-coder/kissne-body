# Kissne–Hermes 需求与当前代码对齐表 V0.1

> Status: implementation baseline
> Scope: Kissne context / identity / memory / history foundation on top of Hermes runtime
> Principle: reuse Hermes runtime mechanisms; do not build a parallel Kissne runtime.

| Kissne 需求 | Hermes 当前实际实现 | 判断 / Kissne 落地方向 |
|---|---|---|
| `SOUL.md / SELF.md / MEMORY.md` 三层身份与记忆 | Hermes 已有 `SOUL.md` 身份入口；system prompt 也支持内置 memory、`USER.md` 和 external memory provider；当前没有 Kissne `SELF.md` 身份层 | **部分具备。** 保留 `SOUL`，新增独立 `SELF`；不能把现有 MEMORY 机制直接当成 Kissne 三层模型 |
| Stable Core / Session Snapshot | Hermes 已有 `stable / context / volatile` 三段 system prompt，并对完整 prompt 做 session 级缓存 | **基础很好，但概念不能直接等同。** Hermes 的 `stable` 是缓存层级，不是 Kissne Stable Core；需在其上定义 Kissne Snapshot 语义 |
| 会话开始读取 `SELF / MEMORY` | 新 session 会构造 system prompt；恢复已有 session 时也可能恢复已持久化的 cached prompt，而非无条件重新读磁盘 | **需要新增明确 Snapshot 生命周期。** 应定义 fresh session、resume、compress 各自在什么情况下重新读取 `SELF/MEMORY` |
| 普通轮次不热加载 `SELF / MEMORY` | cached system prompt 普通轮次不 rebuild；但 Hermes 另外存在每轮一次的 memory prefetch，二者不是同一机制 | **必须拆成两层。** `SELF + MEMORY Snapshot` 普通轮次冻结；`Turn Recall` 可以每轮动态查询 |
| `/compress` 刷新 Snapshot | compression 后已有 system-prompt invalidation/rebuild；rebuild 会重新加载 memory | **天然刷新边界。** 在该边界增加 `SELF.md + MEMORY.md` Snapshot refresh，不另造机制 |
| Live Delta | Hermes 已有 per-turn setup、memory prefetch、plugin/user context sidecar；但这些还不是 Kissne Live Delta | **尚未实现。** 建立结构化 request-local Live Delta；真正求值位置必须靠近每次模型 API call，不能只在 turn 开头计算 |
| 当前时间 | Hermes system prompt 有 timestamp，但设计目标是保持 prompt 稳定；当前 timestamp 是 date-only，且跟随 cached system prompt 生命周期 | **不满足 Kissne 精确时间。** 精确 Earth time 应在每次 API call 的 Live Delta 中动态生成，而非塞进 cached prompt |
| Unified History | Hermes 已有 session DB、conversation messages、工具消息及 API sidecar 等持久化基础 | **有存储骨架，没有 Kissne 统一历史语义。** 需要定义 canonical history：真实历史、request-local context、audit/sidecar 的边界 |
| Read-Time Filtering | `ContextEngine.select_context()` 已明确：每次 provider request 执行、返回结果只用于当前 request、不得修改 persisted history | **扩展点正确。** 增加 Kissne singleton / collection / budget / relevance 规则；失败回退仍必须服从模型硬 context limit |
| Turn Recall | `MemoryManager.prefetch_all()` 已存在，并在 turn setup 中针对 non-trivial prompt 调用 | **可直接复用机制。** 但当前 recall 还没有 Kissne 的 Impressions、Open Loops、Living Context 等语义 |
| MemoryProvider | Hermes 已有 provider abstraction，包括 prefetch、工具 schema、同步、compression checkpoint、session lifecycle 等 | **适合作为适配层。** 先保持 provider-neutral，再决定具体 provider 与 truth-source / backup / migration 边界 |
| 四个常驻 Meta Tools | Hermes 已实现 `tool_search / tool_describe / tool_call` progressive-disclosure bridge；它们按条件注入，并非无条件常驻 | **当前不满足“四个常驻 Meta Tools”。** 三个 bridge 可复用；需重新决定 Kissne 是否永久可见；`propose_deep_mode` 尚未确认实现 |
| Style Guard / 最终文本一致性 | Hermes 有 `transform_llm_output`、`post_llm_call`，同时 finalizer 负责 transcript shaping / persistence | **KB1 优先收口。** 需要唯一 canonical delivered assistant text，使“最终交付文本 = Unified History 中 assistant 文本”；raw model output 如需保留进入 audit/sidecar |
| Wake / Gateway / 异步投递 | Hermes 已有 gateway、session lifecycle、cron/wake 类能力、事件和投递恢复基础 | **直接复用。** 不建立第二套 Kissne runtime |
| Android / Earth / AI World | Hermes 有通用 gateway、cron、adapter、工具与 external-context 接缝 | **只有基础设施，没有 Kissne 世界模型。** Earth State / AI World State / provenance / freshness 等仍需新增 |
| 语音 | Hermes 已有语音 memo/transcription 等通用能力和相关 adapter 基础 | **后续能力，不是 KB0/KB1 阻塞项。** |
| 长期单一 Agent | Hermes 有长期 session、agent loop、turn author 等机制 | **可作为叶青栩的运行身体。** `turn_author` 不是持续身份；长期身份仍由 `SOUL + SELF + Memory` 建立 |

## 核心语义分层

```text
SOUL
稳定人格与不可轻易变化的核心
        ↓
SELF
会成长、会更新的“我是谁”
        ↓
Session Snapshot
本次会话冻结看到的 SELF + MEMORY 状态
        ↓
Turn Recall
根据当前问题动态找回相关长期信息
        ↓
Live Delta
当前这一刻的时间 / Earth / AI World / 临时状态
        ↓
Read-Time Filtering
从完整 Unified History 中决定本次 API 实际发送什么
        ↓
Model
        ↓
Style / Delivery Guard
        ↓
Canonical Assistant Message
        ├── 写入 Unified History
        └── 同一份内容交付用户
```

## 必须固定的边界

### 1. Unified History 是事实层

Unified History 保存真正发生过的事件：

- 用户消息；
- 最终交付给用户的 assistant 文本；
- 实际发生的工具调用；
- 实际工具结果；
- 必要的执行证据和 provenance。

不能为了上下文管理而删除、改写已经发生的历史。

### 2. Live Delta 是请求层

Live Delta 是 API-call-time 临时上下文，不是新的持久历史层。它可以包含：

- 精确当前时间；
- Earth State；
- AI World State；
- Turn Recall；
- Open Loops delta；
- 当前工具/环境临时结果；
- provenance / factual / sourceRefs 等结构化元数据。

Live Delta 每次模型 API call 重新求值，不写入 cached system prompt，不把同一份聚合内容重复写进 Unified History。

### 3. Read-Time Filtering 只改变“本次发什么”

`ContextEngine.select_context()` 或等价 request-selection 层负责构造模型可见投影，但不能修改 durable history。

如果过滤失败：

- 不删除、不损坏持久历史；
- 使用保守 fallback selector；
- 仍然必须遵守当前模型的硬 context/token window。

### 4. Snapshot 与 Turn Recall 必须分开

- `SOUL`：稳定核心；
- `SELF`：可演化自我模型；
- `MEMORY.md`：小型 curated resident memory；
- Session Snapshot：会话期间冻结看到的 SELF/MEMORY；
- Turn Recall：每轮按需从长期 MemoryProvider 检索。

普通轮次不得仅为了刷新 cached prompt 而重复读取 SELF/MEMORY；`/compress` 是 Snapshot 刷新的正式边界之一。

### 5. 最终交付文本是 canonical assistant history

期望顺序：

```text
raw model result
    ↓
tool loop complete
    ↓
Style / Delivery Guard
    ↓
canonical delivered assistant text
    ├── persist to Unified History
    └── deliver to user
```

如需要保存 raw model output，应进入 audit/sidecar，不得让正式 history 保存旧文本而用户看到另一份文本。

## 实施顺序

1. **KB0 — Runtime baseline**：startup / stop / restart / backup / recover / health / no-key baseline。
2. **KB1-A — Canonical History**：收口 finalizer 的交付文本与持久化一致性。
3. **KB1-B — SOUL / SELF / MEMORY Session Snapshot**：新增 SELF，固定 snapshot 生命周期和 `/compress` refresh。
4. **KB1-C — Per-model-call Live Delta**：精确当前时间 + request-local 结构化上下文。
5. **KB1-D — Read-Time Filtering**：singleton / collection / budget / fallback。
6. **MemoryProvider / Turn Recall**：确定 truth-source / backup / migration 边界，再接入 Impressions / Open Loops / Living Context。
7. **Earth / AI World / proactive / voice**：在基础语义稳定后继续。

## 开发原则

- Hermes 是 Kissne 的 runtime/body 起点，不再搭第二套 runtime。
- Hermes 已满足需求的能力直接复用。
- Hermes 有扩展点时优先扩展，不重写主循环。
- 只有语义冲突或确实缺失的部分才做最小修改。
- 长期历史保持 append-only evidence/truth；上下文选择发生在 read-time。
- Live Delta 与 cached system prompt 严格分离。
- 所有新行为必须有可验证测试，尤其是 snapshot、history consistency、per-call freshness 和 read-time non-mutation。
