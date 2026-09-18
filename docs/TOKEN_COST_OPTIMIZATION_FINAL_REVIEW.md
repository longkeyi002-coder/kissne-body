# Hermes / Kissne Token Cost Optimization — Final Review

## Scope

This branch consolidates the token-cost work previously split across PR #27 and PR #28.

### 1. Historical images

- Historical image payloads are replaced with short deterministic asset fingerprints.
- A completed turn becomes eligible for projection immediately on the next user turn.
- The current turn stays lossless so image retry/recovery paths still have the original bytes.
- Durable/persisted history is not rewritten.

### 2. Historical tool inputs

- Small tool-call arguments remain byte-for-byte unchanged.
- Large historical arguments are replaced by bounded, valid JSON metadata.
- The projection never slices serialized JSON into invalid syntax.
- Sensitive-looking keys are redacted inside the compact preview.

### 3. Historical tool results

- Small results remain unchanged.
- Large historical tool results keep a bounded head/tail projection with size and digest metadata.
- Multimodal tool results receive the same text bound and historical-image replacement.
- Tool-call ids and assistant→tool structure are preserved.

### 4. Tool schema overhead

Hermes already has session-stable Tool Search progressive disclosure. This branch extends its
curated default defer set for low-frequency core capabilities:

- browser diagnostics: `browser_console`, `browser_cdp`, `browser_dialog`
- browser image/vision helpers: `browser_get_images`, `browser_vision`
- browser vault tools: `browser_vault_*`
- `text_to_speech`
- `skill_manage`

Common working-set tools remain eager, including terminal/file/web tools,
`browser_navigate`, `browser_click`, memory, clarify, execute_code, and delegation.

No per-turn toolset mutation is introduced; prompt-cache stability is preserved.

## Deliberately not changed

### Reasoning replay

Reasoning is already stripped for providers that do not require replay. DeepSeek/Kimi/MiMo
thinking routes explicitly require reasoning echo and can reject requests if it is removed.
This branch therefore does not add a blanket reasoning truncation.

### Durable transcript

The database/session transcript remains lossless. All compaction in this branch is request-only.

### Global Budget Gate

KB3-A1 / PR #22 is a separate global-call-budget contract and remains independent. It controls
whether calls may occur; this branch reduces how many input tokens are paid when calls do occur.
Mixing the two would make review and rollback materially harder.

## Review invariants

1. Current-turn images/tool payloads are not projected.
2. Previous completed turns are projected on the next turn.
3. Small historical tool arguments/results remain unchanged.
4. Large projected tool arguments remain valid JSON.
5. Projected tool results are bounded while retaining head/tail context.
6. Persisted messages are never mutated by request projection.
7. Common browser actions remain direct; only low-frequency schemas are deferred.
8. Tool Search remains session-stable and does not mutate the toolset per request.
9. Provider-required reasoning replay remains intact.
