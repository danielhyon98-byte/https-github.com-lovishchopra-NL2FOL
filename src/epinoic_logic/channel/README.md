# channel — the path every inter-agent message takes

This is the primary feature of the infrastructure. Agents never hand each other
raw text; everything crosses the `TranslatorChannel`, which makes requests explicit,
checks responses against the request they answer, and attaches a receipt.

```
router ──request()──► TaskRequest (items, constraints, texts) in a hashed envelope ──► specialist
specialist ──respond()──► SpecialistReport in an envelope replying to that request
            checks: identity (task, agent, scope; the envelope's sender IS the payload's agent, INT-ENV-008)
                    integrity (replay, tampering, a report id reused with other content, INT-HANDOFF-015; a claim of
                               another report or request inside the payload, INT-HANDOFF-012, decided on a mapping
                               before contract validation; a claim id another agent's report already holds, INT-REQ-016)
                    request fidelity (items addressed by material claims only; constraints checked, formally when numeric;
                                      a response that restates the request, INT-REQ-011; one with no answer, INT-REQ-012;
                                      claims the adapter folded beyond the limit and left unchecked, INT-REQ-013)
                    source integrity (quotations found in the supplied texts; a form difference is a warning,
                                      INT-REQ-010, never an invented quotation)
                    claim verification (translator + engine; outcomes attached; a translation produced for another
                                        text of the claim is INT-STALE-011 and is neither shown nor pooled)
                    cross-agent consistency (contradictions with claims already transmitted)
            ──► router receives report + TransmissionReceipt, or a REJECTED receipt and no report
            raw text: the hub-stated agent_id is checked against the request and the plan BEFORE parsing; text carrying a
            lone UTF-16 surrogate (half an emoji) is refused with INT-REQ-009 naming its offsets, never parsed or raised;
            a response handed over as a mapping (a report as JSON) is validated and checked like a report, anything else
            (None, a number) is REJECTED with INT-REQ-009; an integrity pack that fails is INT-INTERNAL-001 on the receipt
agent ──relay()──► another agent (report or synthesis): envelope, sender = payload owner (INT-ENV-008), sender and
            recipient selected by the plan (INT-HANDOFF-002; the router and the Overseer are infrastructure parties, and
            an infrastructure role is held, not asserted: an id the plan selects as a specialist or combinator, or a
            "router" other than the sender of the channel's requests, is INT-ENV-007), a synthesis id reused with other
            content refused (INT-HANDOFF-015), ledger, figure/date fidelity (decades and small counts in words included),
            quotations of the synthesis located and credited to a text that holds them (INT-LEDGER-025), direction,
            polarity and who holds a view (INT-LEDGER-026), from-memory labels kept (INT-LEDGER-027), undisclosed
            contradictions (INT-CONFLICT-002), entailment checks, and every material paraphrase or merge left unchecked
            stated (INT-SYNTH-012); a payload handed over as a mapping is validated against the contract its shape names,
            anything else is REJECTED with INT-REQ-009 and nothing raises
router ──relay()──► peer specialist: a DELIVERED report forwarded unchanged (`specialist_report_forward/1.0`);
            the channel checks the forward against the delivery (INT-HANDOFF-013: never delivered / altered in transit)
```

Identity and integrity violations REJECT a transmission before any content check runs: nothing of a
rejected report is pooled, stored or delivered. Content findings (an unverified quotation, a failed
constraint, a contradiction with another agent, a restated request, an answer that is nothing but
notes) are delivered WITH the report so the router can act. The first report delivered under a report
id is the one the channel holds; a later payload under the same id never overwrites it. The same
content re-delivered under that id (a re-parsed retransmission: only `created_at` differs) is a
duplicate delivery (INT-ENV-001) when it reaches a recipient that already received it (the message says "only the
timestamp differs" only when `created_at` differs); the same report handed on, unchanged, to a party that never received
it (the specialist relaying its own delivered report to the combinator) is a hand-off, not a duplicate. A different
response or different claims is INT-HANDOFF-015. Only DELIVERED transmissions are recorded for the duplicate test: a
relay the channel refused (an unknown `in_reply_to`, INT-ENV-003) is no precedent for the first legitimate one.

Contradictions are named claim-minimally (`integrity/cross_check.py`): a pooled claim whose own assertions refute
each other is INT-CONFLICT-005 for that claim alone, whichever claim's identical premises the unsat core used, and
demands no disclosure; when its formalization is the assumed reading of an AMBIGUOUS_TRANSLATION (the channel passes
the pool's `ambiguous_pooled` claims) it is a warning, since the refutation is the translator's reading. INT-CONFLICT-001
names only claims the contradiction needs, and only it enters `conflicts_seen` and the INT-CONFLICT-002 disclosure rule.

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
| `request_parser.py` | Deterministic extraction of questions/instructions and of word, paragraph and citation constraints. A word is a run of letters, digits, apostrophes and hyphens, and a figure with internal separators ("1.9", "100,000", "63.2%") is ONE word (`count_words`). Conservative: nothing asked is dropped. A sentence that mixes a constraint with a content instruction ("Write no more than 200 words and give a judgement on which effect mattered most") yields the instruction as an item with the constraint span removed; a sentence that is only a constraint yields none. `count_answer_words` measures a word bound over the answer proper, leaving out the note blocks and note clauses `count_paragraphs` leaves out, and the receipt says how many words were meta-text. Sentences are cut as the parsers cut them: a pasted JSON span glued into a paragraph (`markdown.split_json_spans`) is one piece of meta-text on its own, so `{"n": 1}` added to a paragraph takes only its own two words out of the count and the prose around it stays answer (a block that is nothing but a JSON span is no paragraph). "about / around / approximately N words" bounds the length on both sides, 0.9N to 1.1N (c1 the minimum, c2 the maximum, as for "between A and B words"); "in N words" stays a soft maximum of 1.1N. A sentence is a note only when nothing is left once its note clauses are set aside (`markdown.split_note_clauses`), the rule the parsers role by: a dated sentence with an inline "(from memory)" is answer, its label meta-text. Re-exports `VERDICT_CUES`. |
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
| INT-REQ-004 | warning / info | a request item appears unaddressed (lexical heuristic over the material claims, notes excluded; terms are read without quotation marks or a possessive 's and compared on light stems, so "the poem's 'smokeless air'" shares 'poem', 'smokeless' and 'air'; a capitalised adjective of place is read as its place, so "decolonisation in Africa" shares 'africa' with "African states"; info when the item is optional) |
| INT-REQ-005 | error / warning | a constraint not satisfied (formal result for word and paragraph bounds; a paragraph overrun is a layout warning) |
| INT-REQ-006 | warning | claim verification failed internally for a claim |
| INT-REQ-007 | error | a claim rests on premises that contradict each other (engine) |
| INT-REQ-008 | warning | a level-3 command term (evaluate, discuss, to what extent, assess, examine, justify, recommend, give a judgement) with no judgement or position on degree in the report |
| INT-REQ-009 | error | raw text the branch adapter could not parse, raw text (or a request) carrying a lone UTF-16 surrogate code point (a truncated emoji arriving as "\ud83d"; the finding names the character offsets; nothing raises, since every hash of agent text encodes a surrogate with `surrogatepass`), or a payload that does not re-validate against the contract; not delivered. A claim whose `report_id` or `request_id` differs from its report is not this code: it is INT-HANDOFF-012 naming the claim and the fields, decided on the raw payload before validation (for a report received as a mapping, by `respond` or `relay`, the claim's `report_id`, `request_id`, `task_id` and `agent_id` are compared before the contract is validated) |
| INT-REQ-010 | warning | a quotation whose words occur in the supplied text but whose form differs (initial capital, verse line-break mark, diacritics, an elision spanning more than the window): not an invented quotation; the branch rules covering the same excerpt are named, and no branch `-SRC-001` error for the claim reaches the receipt |
| INT-REQ-011 | error | the response restates the request instead of answering it: compared on light stems (-s, -es, -ed, -ing stripped) and, for the overlap, on content stems (function words such as "in", "is", "so", "through" set aside), its text is contained in the request's, or at least 90% of its distinct stems occur in the request and it is no longer than 1.5x the request, or at least 75% do, it is no longer than 2x the request and it quotes the request's own words as if they were the text's (a quotation found in the request but in no supplied text; this rule is evaluated whatever the first rule's length cap says); no item counts as addressed, its outcomes are not pooled and it supersedes nothing |
| INT-REQ-012 | error | the response carries no answer: none of its claims is material (every claim is roled `other`: a note, a label, a self-report) or its answer proper has 0 words; no item counts as addressed and it supersedes nothing. Delivered with the report (a content finding; the empty response stays INT-REQ-009) |
| INT-REQ-013 | warning | the branch adapter merged the claims beyond the contract limit into one tail claim without roling or checking them (its `unresolved_issues` say so): the finding says how many claims and how many quotations of the original response went unchecked, and which of those quotations occur in no supplied text, so a quotation placed after the limit never crosses silently |
| INT-REQ-014 | warning | a claim credits a relayed peer specialist's report (the clause after the peer's possessive, "the History specialist's figure of ...", "in the History specialist's account, ..."; after the peer as the subject of a reporting verb, "the History specialist gives ...", "as the History specialist notes, ..."; after "according to" the peer, or the clause that "..., according to the History specialist" closes; a clause never ends at the point of a decimal, "5.2 million", or after an abbreviation, "c. 1963") and states there, outside its quotations, figures or dates (digits or words) that occur in no supplied text, the peer's report included, named with their scale word ("2.5 million", never "2"); or a date the peer gives for another event (`ledger.credited_date_repairings`: "The History specialist dates the sonnet to 1886" where the peer dates the sonnet 1883 and the statue's dedication 1886; every event word of the clause the peer dates must disagree): a colleague's figure or date misreported in an unquoted paraphrase, or the agent's own unsupported figure |
| INT-REQ-015 | error | a quotation whose sentence credits it (a possessive or a crediting verb after the name: "Hardy's speaker himself admits that ...", "The poem says that ...") to a source the agent was NOT supplied (a text the router supplied to another agent of the task, or a text named by kind when none was supplied), while among the agent's supplied texts its words occur only in a relayed peer specialist's report and not in the credited text (for a text named by kind: in the peer's own prose, not in a quotation the peer made): a colleague's words presented as the source's. Names the claim, the credited text and the peer document. A credit to a supplied text is the packs' rule (CORE-SRC-005, ES-SRC-008), and a claim a pack already named under CORE-SRC-005 is not named again |
| INT-REQ-016 | warning | a delivered report carries a claim id that a report of ANOTHER agent already delivered on this task holds: the router now holds two different claims under one id and a synthesis citing it cannot be accounted for by id (INT-LEDGER-014), so the collision is named at delivery with both reports. The same agent re-using its ids is a supersession (INT-HANDOFF-009), and a report already held under its id collides with nothing |
| INT-SUBJ-001 | error | a formal check the branch pack built from the report's own statement (arithmetic, chronology, elasticity, margin) does not hold (engine). The finding names the delivered claim(s) whose text holds the statement (the pack's own `FormalCheck.claim_ids` when it gives them; else the claims holding every figure or dated event the problem's premises state; else the claims holding the sentence the check quotes) and quotes the clause the check was built from (from the phrase of its first figure or event to the stated derived figure, thousands separators ignored, so "an increase of 6,500 miles" is reached; a period's premise "1960 begins" is read as "1960"; boundaries read by `sources.clause_boundaries`, so the quote never starts or stops inside a decimal figure, after "c." or an initial, or inside a word, and a parenthetical label after the statement is left out), so junk before the statement never stands in for it; `receipt.formal_checks` carry the same `claim_ids` |
| INT-SUBJ-002 | warning | such a check was undecided (named and quoted the same way) |
| INT-SUBJ-003 | error | a deterministic error of a branch pack, escalated with the branch key and rule |
| INT-STALE-011 | error | a claim outcome whose translation does not bind to the claim as transmitted (claim id, request, report, or `claim_text_sha256` of another text): stale; neither delivered nor pooled |
| INT-SYNTH-013 | warning | the channel's synthesis-formalization hook failed internally; the entailment was not checked |
| INT-INTERNAL-001 | error | the branch's integrity packs failed internally on this report: its subject findings and its own formal checks are missing from the receipt (the report is delivered with this finding; nothing raises into the router) |

On a synthesis receipt the channel also raises INT-SYNTH-012 (warning) for every material 'paraphrased', 'narrowed',
'merged' or 'generalized' claim whose content change no formal conclusion checked on the channel (the Overseer's
`run_integrity_checks` keeps INT-SYNTH-006, an error, for a merged or generalized one). A synthesis id is held like a
report id: the first synthesis delivered under it is kept (`TranslatorChannel.syntheses`), the same content again to a
recipient that holds it is INT-ENV-001, and other content under it is INT-HANDOFF-015 naming the fields and synthesized
claims that differ, not delivered.

Cross-agent findings (INT-GLOSSARY, INT-CONFLICT) over a pooled claim whose translation was AMBIGUOUS_TRANSLATION
say so: its pooled formalization is one assumed reading, not a fixed one.

Coverage of request items is a lexical heuristic until adapters tag claims with the
items they address; the receipt says so. Only material claims (not roled `other`) can
address an item. The translator and adapter are injected (`verify_claim_fn`), so the
channel runs with fixtures today and with the live pipeline when configured.
