# Hermes / Kissne Token Cost Optimization — Final Review

## Scope

This branch consolidates the token-cost work previously split across PR #27 and PR #28.

### 1. Historical images

- Historical image payloads are replaced with short deterministic asset fingerprints after a one-turn recovery grace.
- The immediately previous completed turn stays byte-exact for one turn so 413 and corrupt-image recovery can inspect/strip the rejected image bytes.
- Older turns are projected; the current turn is never projected.
- The projection boundary is computed against the canonicalized prefix, so replay cleanup cannot shift the current user row under the historical boundary.
- Durable/persisted history is not rewritten.

### 2. Historical tool inputs

- Small tool-call arguments remain byte-for-byte unchanged.
- Large historical arguments are replaced by bounded, valid JSON metadata.
- The projection never slices serialized JSON into invalid syntax.
- Sensitive-looking keys are redacted inside the compact preview.

### 3. Historical tool results

- Small results remain unchanged.
- Large historical tool results keep a bounded head/tail projection with size and digest metadata.
- Persisted oversized terminal results keep their `Full output saved to: ...` recovery pointer inside the retained head.
- Multimodal tool results receive the same text bound and historical-image replacement after the recovery grace.
- Tool-call ids and assistant→tool structure are preserved.

### 4. Tool schema overhead

Hermes already has session-stable Tool Search progressive disclosure. This branch extends its
curated default defer set only for low-frequency capabilities that have no runtime behavior
depending on direct schema visibility:

- browser diagnostics: `browser_console`, `browser_cdp`, `browser_dialog`
- browser image/vision helpers: `browser_get_images`, `browser_vision`
- `text_to_speech`

The following remain eager deliberately:

- browser vault tools, because direct browser input guidance references them
- `skill_manage`, because background skill-review counters use its direct visibility as a capability check
- common working-set tools including terminal/file/web tools, `browser_navigate`, `browser_click`, memory, clarify, execute_code, and delegation

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

### Ticket ordering

This PR is an explicit ordering exception: it remains review-only and must not merge until its
ticket face is registered in the detailed plan. This exception is recorded here so the code can
finish CI/review without pretending the ticket-registration step already happened.

## Review invariants

1. Current-turn images/tool payloads are never projected.
2. The immediately previous completed turn retains one recovery grace turn.
3. Older historical payloads are projected only after that grace.
4. Replay cleanup cannot move the current user row under the projection boundary.
5. Small historical tool arguments/results remain unchanged.
6. Large projected tool arguments remain valid JSON.
7. Projected tool results are bounded while retaining head/tail context and persisted-output recovery pointers.
8. Persisted messages are never mutated by request projection.
9. Vault and skill-management schemas remain direct; only safe low-frequency schemas are deferred.
10. Tool Search remains session-stable and does not mutate the toolset per request.
11. Provider-required reasoning replay remains intact.
