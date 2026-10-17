# Integration fixtures: where each file comes from

Small real outputs of the components the integration protocol wraps, produced by running their own code on their
own SYNTHETIC test inputs (no provider was called; every id, count and model label is synthetic). They are copied here
so the specialist-port tests run without the other repositories. No secret is involved anywhere.

| File | Produced by | Source |
|---|---|---|
| `runtime-v1-results.json` | the agents repository's specialist runtime v0.1.0, `createOfflineTestRuntime` with its synthetic manifest, bundle and gate configuration (`specialist-runtime/fixtures/synthetic/harness.js`) and its fake callbacks (`callbacks.js`): outcomes `answer`, `refusal`, `declined`, `incomplete`, `gate_failed`; each with the runtime's own `redactForLog(result)` | danielhyon98-byte/epinoic-agent-training-api-connector, branch `claude/eloquent-euler-1kuwtf`, commit `5b60229b6f08bea88f7cf28316282469942ce46d` |
| `runtime-v2-results.json` | the specialist runtime v0.2.0 that the website's pull request #24 vendors (`vendor/specialist-runtime/`, from Epinoic-AI/Epinoic-Agent-Training `dfb81442b0cb712c3905b5025094fbdb9c019802`), `createOfflineTestRuntime` with the vendored synthetic manifest and bundle and the real `HISTORY_GATE_CONFIG`; the callback returns a synthetic website-03 generation result: outcomes `answer`, `declined`, `gate_unverifiable` (and `incomplete`, which this synthetic reply makes a `failed` callback-contract violation); each with `redactForLog(result)` | Epinoic-AI/epinoic-ai-website pull request #24 head `a18ad80` (`feature/history-pilot-package`), read from a scratch fetch |
| `website-chat-results.json` | the website's mock orchestrator (`src/chat/mock-orchestrator.js`) at `main`: scenarios `answer-history`, `answer-review-not-required`, `clarification`, `unreviewed-answer`. These are website ChatResults, not specialist runtime results: the specialist port must refuse them | Epinoic-AI/epinoic-ai-website `main` at `2cd318208980e5b236d16b4281dfc0560a7b9610` |

Regenerating them needs those checkouts; the files are pinned as they are, and the tests read them as data.
