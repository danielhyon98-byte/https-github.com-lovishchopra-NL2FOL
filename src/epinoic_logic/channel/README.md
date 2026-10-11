# channel — the path every inter-agent message takes

This is the primary feature of the infrastructure. Agents never hand each other
raw text; everything crosses the `TranslatorChannel`, which makes requests explicit,
checks responses against the request they answer, and attaches a receipt.

```
router ──request()──► TaskRequest (items, constraints, texts) in a hashed envelope ──► specialist
specialist ──respond()──► SpecialistReport in an envelope replying to that request
            checks: identity (task, agent, scope; the envelope's sender IS the payload's agent, INT-ENV-008)
                    integrity (replay, tampering, a report id reused with other content, INT-HANDOFF-015; a claim of
                               another report or request inside the payload, INT-HANDOFF-012)
                    request fidelity (items addressed by material claims only; constraints checked, formally when numeric;
                                      a response that restates the request, INT-REQ-011; one with no answer, INT-REQ-012;
                                      claims the adapter folded beyond the limit and left unchecked, INT-REQ-013)
                    source integrity (quotations found in the supplied texts; a form difference is a warning,
                                      INT-REQ-010, never an invented quotation)
                    claim verification (translator + engine; outcomes attached; a translation produced for another
                                        text of the claim is INT-STALE-011 and is neither shown nor pooled)
                    cross-agent consistency (contradictions with claims already transmitted)
            ──► router receives report + TransmissionReceipt, or a REJECTED receipt and no report
            raw text: the hub-stated agent_id is checked against the request and the plan BEFORE parsing
agent ──relay()──► another agent (report or synthesis): envelope, sender = payload owner (INT-ENV-008), sender and
            recipient selected by the plan (INT-HANDOFF-002; the router and the Overseer are infrastructure parties),
            ledger, figure/date fidelity, undisclosed contradictions (INT-CONFLICT-002) and entailment checks
router ──relay()──► peer specialist: a DELIVERED report forwarded unchanged (`specialist_report_forward/1.0`);
            the channel checks the forward against the delivery (INT-HANDOFF-013: never delivered / altered in transit)
```

Identity and integrity violations REJECT a transmission before any content check runs: nothing of a
rejected report is pooled, stored or delivered. Content findings (an unverified quotation, a failed
constraint, a contradiction with another agent, a restated request, an answer that is nothing but
notes) are delivered WITH the report so the router can act. The first report delivered under a report
id is the one the channel holds; a later payload under the same id never overwrites it. The same
content re-delivered under that id (a re-parsed retransmission: only `created_at` differs) is a
duplicate delivery (INT-ENV-001); a different response or different claims is INT-HANDOFF-015.

Notes are not answers. A claim roled `other` (a from-memory label, a self-certification, a task note)
never addresses a request item in the coverage heuristic, never carries a verdict (INT-REQ-008) and
never makes a report supersede an earlier one. A response whose claims are all notes, or whose
answer proper has no words, is delivered with the error INT-REQ-012 so it never reads as covering the
request; a response that restates the request (INT-REQ-011) is delivered, counts for no item, is
verified for the record but never pooled, and never supersedes the agent's genuine report.

Supersession (INT-HANDOFF-009) is decided on content: a later report of the same agent re-states a
claim when its text equals an earlier claim's (under the same or another id) and revises one when it
keeps an earlier id with another text; the finding says which. The copies of the superseded report
still in circulation (INT-HANDOFF-014) are named with deduplicated identifiers, and a quoting report's
excerpt is said to "no longer occur" only when it occurred in the superseded text; one that never
occurred there "was never located in the superseded report either".

Several subjects on one task. A plan may consult a specialist of another subject (a History
specialist giving context for a Literature task): `WorkPlan.agent_subjects` names that agent's
subject, and the channel addresses its requests, parses its raw text and runs the integrity
packs through that subject's branch while the ledger, the hand-off checks and the cross-agent
consistency pool stay shared. `WorkPlan.agent_task_types` likewise gives an agent its own task
type (a peer asked for a short answer on an analytical-paragraph task), carried on its requests
and parsed reports and compared by INT-HANDOFF-010. The peer's forwarded report is supplied to the requesting agent as
a document (`peer:<task>`), so its quotations of the peer are checked like any other quotation
and an altered citation of a colleague reaches the router as an error finding (INT-REQ-003) naming the claim.

| Component | Role |
| --- | --- |
| `contracts.py` | `TaskRequest` (immutable user input hash, request items, constraints), `TransmissionReceipt` (status ACCEPTED / ACCEPTED_WITH_FINDINGS / REJECTED, findings, coverage, constraint results with signed formal result ids, claim outcomes, summary). |
| `request_parser.py` | Deterministic extraction of questions/instructions and of word, paragraph and citation constraints. Conservative: nothing asked is dropped. A sentence that mixes a constraint with a content instruction ("Write no more than 200 words and give a judgement on which effect mattered most") yields the instruction as an item with the constraint span removed; a sentence that is only a constraint yields none. `count_answer_words` measures a word bound over the answer proper, leaving out the note blocks and note clauses `count_paragraphs` leaves out, and the receipt says how many words were meta-text. A sentence is a note only when nothing is left once its note clauses are set aside (`markdown.split_note_clauses`), the rule the parsers role by: a dated sentence with an inline "(from memory)" is answer, its label meta-text. Re-exports `VERDICT_CUES`. |
| `cues.py` | `VERDICT_CUES`: the lower-cased phrases that state a position on degree ("on balance", "mattered most", "matters most", "weighed by", "by the criteria", "by the criterion", "outweigh" and its inflections, "to a large extent", "therefore", ...). The channel's verdict test for INT-REQ-008 is built from it (`verdict_cue_regex()`), and the subject parsers import it (`from epinoic_logic.channel.cues import VERDICT_CUES`; the module has no imports, so no cycle) so the hub and a parser never disagree about what a judgement looks like. |
| `bus.py` | `TranslatorChannel.request / respond / relay`. Numeric constraints are encoded as IR entailments and decided by the engine, so a word-limit check is a signed, bound result rather than an ad-hoc count. A response is REJECTED (not delivered) for identity or integrity violations; findings about content (unverified quotation, failed constraint, contradiction with another agent) are delivered with the report so the router can act. The receipt summary gives the report's own formal checks as counts (naming only the checks that did not hold) and is cut to the contract limit, never raised. One excerpt, one severity: when the hub has located an excerpt's words and reported a form difference (INT-REQ-010), every branch pack error ending in `-SRC-001` for that claim is kept off the receipt, so no pack calls the same excerpt invented. |

## Codes raised by the channel

Hub integrity codes (INT-ENV, INT-HANDOFF, INT-LEDGER, INT-STALE, INT-CONFLICT, INT-GLOSSARY, INT-SYNTH) are
defined in `integrity/README.md`; the channel raises them with the identifiers of the transmission. The codes
below are the channel's own. Blocking (REJECTED): every INT-HANDOFF and INT-ENV error, INT-REQ-000/001/002/009,
INT-LEDGER-000/008; everything else is delivered with the report.

| Code | Severity | Meaning |
| --- | --- | --- |
| INT-REQ-000 | error | response replies to no accepted request on this channel |
| INT-REQ-001 | error | response came from (or raw text is stated to come from) an agent other than the request's addressee; raw text is not parsed |
| INT-REQ-002 | error | response cites supplied texts that were not in the request |
| INT-REQ-003 | error | a quotation the cited document does not contain: "not found in the supplied texts [ids]", or "occurs in [other ids] (misattributed)"; a citation of a document not supplied; a locator the text cannot carry |
| INT-REQ-004 | warning / info | a request item appears unaddressed (lexical heuristic; info when the item is optional) |
| INT-REQ-005 | error / warning | a constraint not satisfied (formal result for word and paragraph bounds; a paragraph overrun is a layout warning) |
| INT-REQ-006 | warning | claim verification failed internally for a claim |
| INT-REQ-007 | error | a claim rests on premises that contradict each other (engine) |
| INT-REQ-008 | warning | a level-3 command term (evaluate, discuss, to what extent, assess, examine, justify, recommend, give a judgement) with no judgement or position on degree in the report |
| INT-REQ-009 | error | raw text the branch adapter could not parse, or a payload that does not re-validate against the contract; not delivered. A claim whose `report_id` or `request_id` differs from its report is not this code: it is INT-HANDOFF-012 naming the claim and the fields, decided on the raw payload before validation |
| INT-REQ-010 | warning | a quotation whose words occur in the supplied text but whose form differs (initial capital, verse line-break mark, diacritics, an elision spanning more than the window): not an invented quotation; the branch rules covering the same excerpt are named, and no branch `-SRC-001` error for the claim reaches the receipt |
| INT-REQ-011 | error | the response restates the request instead of answering it: compared on light stems (-s, -es, -ed, -ing stripped), its text is contained in the request's, or at least 90% of its distinct stems occur in the request and it is no longer than 1.2x the request, or at least 75% do and it quotes the request's own words as if they were the text's (a quotation found in the request but in no supplied text); no item counts as addressed, its outcomes are not pooled and it supersedes nothing |
| INT-REQ-012 | error | the response carries no answer: none of its claims is material (every claim is roled `other`: a note, a label, a self-report) or its answer proper has 0 words; no item counts as addressed and it supersedes nothing. Delivered with the report (a content finding; the empty response stays INT-REQ-009) |
| INT-REQ-013 | warning | the branch adapter merged the claims beyond the contract limit into one tail claim without roling or checking them (its `unresolved_issues` say so): the finding says how many claims and how many quotations of the original response went unchecked, and which of those quotations occur in no supplied text, so a quotation placed after the limit never crosses silently |
| INT-SUBJ-001 | error | a formal check the branch pack built from the report's own statement (arithmetic, chronology, elasticity, margin) does not hold (engine) |
| INT-SUBJ-002 | warning | such a check was undecided |
| INT-SUBJ-003 | error | a deterministic error of a branch pack, escalated with the branch key and rule |
| INT-STALE-011 | error | a claim outcome whose translation does not bind to the claim as transmitted (claim id, request, report, or `claim_text_sha256` of another text): stale; neither delivered nor pooled |
| INT-SYNTH-013 | warning | the channel's synthesis-formalization hook failed internally; the entailment was not checked |

Cross-agent findings (INT-GLOSSARY, INT-CONFLICT) over a pooled claim whose translation was AMBIGUOUS_TRANSLATION
say so: its pooled formalization is one assumed reading, not a fixed one.

Coverage of request items is a lexical heuristic until adapters tag claims with the
items they address; the receipt says so. Only material claims (not roled `other`) can
address an item. The translator and adapter are injected (`verify_claim_fn`), so the
channel runs with fixtures today and with the live pipeline when configured.
