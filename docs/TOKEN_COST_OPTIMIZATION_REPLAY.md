# KB3-B2 token optimization evidence

This change is request-only. The durable transcript is unchanged; only older
messages projected into a provider request are eligible for compaction.

## Baseline and scope

- Baseline: `main` at `5e81053d1d` (PR #29 already merged).
- History replay retained PR #29's one-turn recovery grace and generic 1536
  character tool-result bound.
- This increment adds typed terminal receipts, explicit protection for failed
  and later-referenced receipts, and keeps the current turn exact.
- The default deferred-tool catalog listing is reduced from 4000 to 1800
  estimated tokens. Full schemas remain available through `tool_describe`.

## Measurement contract

| Measure | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Fixed listing cap | 4000 tokens | 1800 tokens | 2200 tokens less whenever the listing is embedded |
| Large historical generic result | full request copy | ≤1536 chars | Triggered only for older, unprotected results |
| Large historical terminal receipt | full request copy | ≤1536 chars | Command, exit status, recovery pointer, stdout head/tail retained |
| Current-turn result | exact | exact | No compression while the active tool loop can still consume it |
| Failed or later-referenced result | eligible for generic trim | exact | Recovery/reference safety takes precedence over savings |

Character counts are measured on the request projection, before provider
tokenization. The token estimate for the listing uses the existing cheap
`characters / 4` catalog rule; behavior tests are the acceptance gate.

The focused fixture measured a 10,077-character structured terminal receipt at
1,536 characters after projection (84.8% fewer characters). The equivalent
untyped 10,005-character receipt projects to 1,364 characters (86.4% fewer).
The listing ceiling itself falls from 4,000 to 1,800 estimated tokens (55%
fewer when the ceiling is reached); smaller catalogs naturally consume less.

## Persistent-kernel audit

`execute_code` keeps variables, imports, and loaded data in the child kernel's
`GLOBALS` namespace between cells. The host returns only the cell result JSON
(`status`, cleaned stdout/error, duration, and optional kernel metadata) to the
model. No namespace dump, state summary, or automatic `repr(GLOBALS)` is added
to `build_api_messages` or the request history. Therefore persistent state is a
runtime-memory and state-contamination concern, not a fixed prompt-token cost.
It becomes a token cost only when code explicitly prints/serializes the state;
that output is then subject to the normal tool-result and stdout bounds.

## System-prompt audit

This ticket does not rewrite execution-policy wording. The system-prompt rules
remain byte-stable while their fixed size and any repeated canonical phrases can
be measured separately in a follow-up change. This keeps tool selection,
parameter filling, prerequisite checks, mandatory tool use, verification, and
failure recovery behavior isolated from replay compression.
