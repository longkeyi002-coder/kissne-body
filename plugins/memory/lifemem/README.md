# Kissne Lifemem admission and recall

Lifemem remains one persistent SQLite store. Raw turns are evidence, not long-term facts. No database wipe is performed by this update.

## Admission

Both auto extraction and `lifemem_remember` pass the shared evidence gate. Records carry category, subject, scope, admission reason and status. Categories: fact, preference, agreement, event, project, relationship, temporary.

Uncertain, sensitive without an explicit request, non-extractive summaries, and long inputs become candidates. Candidates never enter automatic recall. Casual acknowledgements are rejected. Temporary records require review; this version does not automatically approve an expiry.

Explicit writes require a real user quote from a stored turn of the current session. An optional `turn_id` disambiguates the evidence; otherwise an exact quote is located in stored user turns. `turn_id` refers to the Lifemem evidence turn, not a Gateway turn identifier. Assistant text cannot serve as evidence. The optional decision bridge receives at most 1200 characters of current user input and two preceding user snippets of at most 400 characters each. Oversized turns are quarantined rather than silently truncated into active facts.

## Recall and lifecycle

Recall scans active, unexpired records beyond the old 200-row cutoff. A lexical coverage of 0.5 or cosine similarity of 0.65 is required before importance and recency rank candidates. These are conservative initial thresholds, not measured production accuracy. Real and hashed embedding scores require further calibration on user examples. Zero results is valid. Retrieval no longer confirms or reinforces a memory. Reality-facing tools and automatic recall exclude AI World facts.

A replacement must identify an active record with the same subject, scope and memory space. The old record becomes superseded, preserving evidence. Archives remain recoverable. Existing records remain intact and retain their existing admission state; this release does not certify or re-admit the old library.

## Validation and remaining work

Tests cover admission, durable evidence, candidate exclusion, unrelated zero recall, expired and superseded records, old-record retrieval, and session writer lifecycle. No automatic whole-conversation LLM summarizer is introduced. Topic synthesis, reviewed candidate promotion, memory-editor UI, correction-to-recalled-ID feedback and production threshold calibration remain required before calling this a complete ChatGPT-like memory experience.

## Recall feedback and review tools

`lifemem_review` lists candidates, approves/rejects one candidate, or audits up to 100 legacy active records per call. Approval may repair summary/type/subject/scope but cannot replace the original quote or bypass the evidence gate. Legacy audit is explicit, bounded and repeatable; it is not run silently at startup.

Automatic and explicit recalls retain query, session, memory IDs and timestamp. Explicit memory-correction language links to the most recent receipt within 30 minutes and suppresses its IDs only in that session. Generic “不对” does not classify unrelated memories as globally false. Multiple returned memories remain ambiguous: the receipt records disputed use, not proof that every item is wrong. There is no production-library audit performed by this code change, and no memory editor UI yet.
