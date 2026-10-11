# channel — the path every inter-agent message takes

This is the primary feature of the infrastructure. Agents never hand each other
raw text; everything crosses the `TranslatorChannel`, which makes requests explicit,
checks responses against the request they answer, and attaches a receipt.

```
router ──request()──► TaskRequest (items, constraints, texts) in a hashed envelope ──► specialist
specialist ──respond()──► SpecialistReport in an envelope replying to that request
            checks: identity (task, agent, scope) · integrity (replay, tampering)
                    request fidelity (items addressed; constraints checked, formally when numeric)
                    source integrity (quotations found in the supplied texts)
                    claim verification (translator + engine; outcomes attached)
                    cross-agent consistency (contradictions with claims already transmitted)
            ──► router receives report + TransmissionReceipt, or a REJECTED receipt and no report
agent ──relay()──► another agent (report or synthesis) with envelope, ledger and consistency checks
```

| Component | Role |
| --- | --- |
| `contracts.py` | `TaskRequest` (immutable user input hash, request items, constraints), `TransmissionReceipt` (status ACCEPTED / ACCEPTED_WITH_FINDINGS / REJECTED, findings, coverage, constraint results with signed formal result ids, claim outcomes, summary). |
| `request_parser.py` | Deterministic extraction of questions/instructions and of word, paragraph and citation constraints. Conservative: nothing asked is dropped. |
| `bus.py` | `TranslatorChannel.request / respond / relay`. Numeric constraints are encoded as IR entailments and decided by the engine, so a word-limit check is a signed, bound result rather than an ad-hoc count. A response is REJECTED (not delivered) for identity or integrity violations; findings about content (unverified quotation, failed constraint, contradiction with another agent) are delivered with the report so the router can act. |

Coverage of request items is a lexical heuristic until adapters tag claims with the
items they address; the receipt says so. The translator and adapter are injected
(`verify_claim_fn`), so the channel runs with fixtures today and with the live
pipeline when configured.
