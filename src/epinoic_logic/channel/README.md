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
            (None, a number) is REJECTED with INT-REQ-009; an integrity pack that fails is INT-INTERNAL-001 on the receipt;
            raw text that opens a JSON object (bare or in a code fence) but is cut off in transit is REJECTED with
            INT-REQ-009 ("truncated or malformed JSON payload"), never parsed as prose, and a complete JSON report sent as
            text is validated and checked as a report; a reply whose request message id is not a string of 1 to 128
            characters (None, a number, a list, an over-long id) is REJECTED with INT-REQ-000 like an unknown id
agent ──relay()──► another agent (report or synthesis): envelope, sender = payload owner (INT-ENV-008), sender and
            recipient selected by the plan (INT-HANDOFF-002; the router and the Overseer are infrastructure parties, and
            an infrastructure role is held, not asserted: an id the plan selects as a specialist or combinator, or a
            "router" other than the sender of the channel's requests, is INT-ENV-007), a synthesis id reused with other
            content refused (INT-HANDOFF-015), ledger, figure/date fidelity (decades and small counts in words included),
            quotations of the synthesis located and credited to a text that holds them (INT-LEDGER-025), direction,
            polarity and who holds a view (INT-LEDGER-026), from-memory labels kept (INT-LEDGER-027), a misspelt quotation (INT-LEDGER-028), an inverted comparison or an added
            negation against one source (INT-LEDGER-030), an act given to a person the cited sources do not name for it
            (INT-LEDGER-032), a student-facing text that is not composed of its claims (INT-LEDGER-031), undisclosed
            contradictions (INT-CONFLICT-002), entailment checks, and every material paraphrase or merge left unchecked
            stated (INT-SYNTH-012); a payload handed over as a mapping is validated against the contract its shape names,
            anything else is REJECTED with INT-REQ-009 and nothing raises; a synthesis carrying a value outside one of the
            contract's closed vocabularies (a transformation written as a description of the edit) is also named,
            INT-SYNTH-014, and a synthesis object built around validation is re-validated and refused the same way
router ──relay()──► peer specialist: a DELIVERED report forwarded unchanged (`specialist_report_forward/1.0`);
            the channel checks the forward against the delivery (INT-HANDOFF-013: never delivered / altered in transit)
specialist ──relay()──► another party: only a report the channel delivered from that sender, unchanged; a report the
            sender never delivered is REJECTED with INT-HANDOFF-013 and changes no channel state (it is not held, it
            supersedes nothing, and its claims are not pooled), so the router's later forward of the delivered report
            is no circulation of a superseded one
```

A request never raises: `request()` (and `RouterHub.dispatch`) collects every problem of the request (a text that is
not a string, an empty or white-space text, a text over the contract's 400,000 characters, more request texts than
the contract holds, an agent id that is not a valid string, more than 64 distinct constraints) and returns a REJECTED
receipt with one INT-REQ-009 finding naming them all ("request REJECTED as malformed: ..."). Repeated identical
constraints are one constraint; when more than 64 distinct ones remain, the request record keeps the strongest bound of
each kind. A refused request is not stored and nothing can reply to it.

```
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
A symbol the pooled claims gloss as different quantities (the target 67 in one trace and 20 in another; the marks of
part (a) and of part (c)) is read apart per claim (`cross_check.split_by_gloss`): a contradiction that exists only when
such a symbol is pooled is the INT-CONFLICT-004 warning naming the symbols and their glosses, charged to no specialist and
never demanded of the combinator's disclosure.

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

The channel holds its own copy of the plan it was opened with (a later change to the caller's `WorkPlan` object, whose
lists are mutable, never changes the rules the channel applies). The Overseer pins the plan, the solver configuration,
the engine key id and the branch at the channel's first event: a transfer issued after any of them changed is a
custody fault (OVS-CUST-002, review round 3).

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
| `contracts.py` | `TaskRequest` (immutable user input hash, request items, constraints; a `Constraint.excludes` lists what a word bound leaves out, "working" and "diagram", when the request says so), `CoverageRecord` (method `lexical` or `part_label`), `TransmissionReceipt` (status ACCEPTED / ACCEPTED_WITH_FINDINGS / REJECTED, findings, coverage, constraint results with signed formal result ids, claim outcomes, summary). |
| `request_parser.py` | Deterministic extraction of questions/instructions and of word, paragraph and citation constraints (`extract_items(text, extra_imperatives=...)`, `count_answer_words(text, view=...)` and `measure_answer_words(text, excludes=..., view=...)` take a branch's hooks; the defaults are the general reading). A word is a run of letters, digits, apostrophes and hyphens, and a figure with internal separators ("1.9", "100,000", "63.2%") is ONE word (`count_words`). Conservative: nothing asked is dropped. A sentence that mixes a constraint with a content instruction ("Write no more than 200 words and give a judgement on which effect mattered most") yields the instruction as an item with the constraint span removed; a sentence that is only a constraint yields none. `extract_items` gives one item per labelled part of the request ("(a)", "Part (b)", "Guiding question:"; `request_parts`, `part_label`) and, outside the parts, one per question (an opening "¿" included), imperative or "Please ..." sentence. `count_answer_words` (over `measure_answer_words`, which also takes the constraint's `excludes`: equation lines are working whole, and inside a working block a line quoting an equation is too) measures a word bound over the answer proper, leaving out the note blocks and note clauses `count_paragraphs` leaves out, and the receipt says how many words were meta-text. A blank-line block opened by a note label ("Note:", "NB:", "Note on sources:") whose every sentence is about the answer (its sources or their availability, a correction of the task's marks or figures, what the writer used) is a note block (`is_note_block`): no paragraph and no words of a bound; a block so labelled that states content stays answer, except a paragraph opened by a bare note lead ("Note:", "N.B.", "Next step:", "Limit:", "Caveat:"; never "Note on ...:" or "Confidence:", `markdown.opens_note_paragraph`), which the parsers role as a note as a whole, so it is no paragraph and none of its words counts toward a bound (round-7 parsers hand-off; `tests/channel/test_r7_handoff_note_paragraphs.py`). Sentences are cut as the parsers cut them: a pasted JSON span glued into a paragraph (`markdown.split_json_spans`) is one piece of meta-text on its own, so `{"n": 1}` added to a paragraph takes only its own two words out of the count and the prose around it stays answer (a block that is nothing but a JSON span is no paragraph). "about / around / approximately N words" bounds the length on both sides, 0.9N to 1.1N (c1 the minimum, c2 the maximum, as for "between A and B words"); "in N words" stays a soft maximum of 1.1N. A sentence is a note only when nothing is left once its note clauses are set aside (`markdown.split_note_clauses`), the rule the parsers role by: a dated sentence with an inline "(from memory)" is answer, its label meta-text. Re-exports `VERDICT_CUES`. |
| `cues.py` | `VERDICT_CUES`: the lower-cased phrases that state a position on degree ("on balance", "mattered most", "matters most", "weighed by", "by the criteria", "by the criterion", "outweigh" and its inflections, "to a large extent", "therefore", ...). The channel's verdict test for INT-REQ-008 is built from it (`verdict_cue_regex()`), and the subject parsers import it (`from epinoic_logic.channel.cues import VERDICT_CUES`; the module has no imports, so no cycle) so the hub and a parser never disagree about what a judgement looks like. |
| `bus.py` | `TranslatorChannel.request / respond / relay`. Numeric constraints are encoded as IR entailments and decided by the engine, so a word-limit check is a signed, bound result rather than an ad-hoc count. A response is REJECTED (not delivered) for identity or integrity violations; findings about content (unverified quotation, failed constraint, contradiction with another agent) are delivered with the report so the router can act. The receipt summary gives the report's own formal checks as counts (naming only the checks that did not hold) and is cut to the contract limit, never raised. One excerpt, one severity: when the hub has located an excerpt's words and reported a form difference (INT-REQ-010), every branch pack error ending in `-SRC-001` for that claim is kept off the receipt, so no pack calls the same excerpt invented. |
| `events.py` | `ChannelEvent` (one immutable record per entry-point call: canonical JSON strings, digests and tuples only), `snapshot_event`, `observe_call`, `ObservationState`. Built inside the call from the channel's public state, before anything is returned; imports nothing from `bus.py` and nothing from the overseer package. |

## Observers (optional)

`TranslatorChannel(observers=[...])` and `add_observer(fn)` attach callables that receive one immutable `ChannelEvent`
per call of the four entry points (`request`, `respond_text`, `respond`, `relay`). A private decorator wraps the four
entry points; the method bodies are not edited.

- **No observer**: the method is called straight through (one attribute check). No result capture is opened, nothing is
  recorded, and the channel behaves exactly as it did without the hook (tested: identical receipts, returned messages
  and channel state).
- **With observers**: the outermost call runs inside a result capture (`engine/sink.py`), so every engine run the call
  makes (claim outcomes, constraint bounds, branch formal checks, cross-report and synthesis runs) is in its event; the
  event is built before the call returns; each observer runs inside `try/except`. An observer that raises never breaks
  a transfer: its failure is recorded in `observer_errors` (event sequence number, observer name, exception type; at
  most 64) and never reaches the caller. A method that raised emits a `raised` event and its exception is re-raised
  unchanged.
- **One router call, one event**: `respond_text` calling `respond`, or a channel call an observer makes during its own
  notification, runs straight through and emits no event of its own. (A transfer issued that way is in the log but not
  in an auditor's journal, and the audit reports it, `OVS-CUST-003`.)
- **Immutable**: every event field is a string, a number, a boolean or a tuple of frozen records, shared by every
  observer; an observer cannot change delivery, the returned objects or what another observer sees. (Deliberately
  bypassing the frozen dataclass after an auditor journaled the event breaks the journal's hash chain, `OVS-CUST-005`.)
- `channel_uid` names the channel instance (uuid4 hex, set at construction); several channels may share a task id.

The channel never imports the overseer package. The Overseer's transfer auditor is one such observer, attached by
`RouterHub(auditor=...)` (see `branches/README.md` and `overseer/README.md`).

## Codes raised by the channel

Hub integrity codes (INT-ENV, INT-HANDOFF, INT-LEDGER, INT-STALE, INT-CONFLICT, INT-GLOSSARY, INT-SYNTH) are
defined in `integrity/README.md`; the channel raises them with the identifiers of the transmission. The codes
below are the channel's own. Blocking (REJECTED): every INT-HANDOFF and INT-ENV error, INT-REQ-000/001/002/009,
INT-LEDGER-000/008; everything else is delivered with the report.

| Code | Severity | Meaning |
| --- | --- | --- |
| INT-REQ-000 | error | response replies to no accepted request on this channel |
| INT-REQ-001 | error | response came from (or raw text is stated to come from) an agent other than the request's addressee; raw text is not parsed |
| INT-REQ-002 | error | the report's supplied texts are not the request's: a document the router never sent (also when the request sent no texts) or a sent document whose text the report changed (compared by document id and SHA-256 of the text). Quotations are checked only against the texts the router sent, never against the report's own copies |
| INT-REQ-003 | error | a quotation the cited document does not contain: "not found in the supplied texts [ids]" (when one text, or the request, holds all of its words but one or two, the message names it as the nearest text and the quotation as altered), or "occurs in [other ids] (misattributed)"; a citation of a document not supplied; a locator the text cannot carry. An excerpt the request itself holds (the task's own words quoted back) is located, not invented. A quotation the parser credited to no text is refuted the same way when texts were supplied, its words occur in none of them nor in the request, its sentence carries no from-memory label, and either one supplied text (or the request) holds all of its words but one or two (an altered quotation; a relayed colleague's report counts only when no other text was supplied) or its sentence credits it by kind to the text under analysis; and a parser-uncredited quotation of three words or more that occurs in no supplied text and not in the request, whose sentence credits no source (no crediting verb or "according to" in its clause, before it or right after it: "A textbook says '...'" and "'...', according to one report" stay unverifiable), carries no from-memory label and does not mention the words as absent ("the data never say ..."), is refuted as invented ("credits it to no source") rather than left unverifiable (CORE-SRC-003) ("The narrator also insists that '...'"); the packs' "unverifiable" CORE-SRC-003 for that claim then stays off the receipt. A quotation credited to another source ("One critic writes that ...") stays unverifiable |
| INT-REQ-004 | warning / info | a request item appears unaddressed (lexical heuristic over the material claims, notes excluded; terms are read without quotation marks or a possessive 's and compared on light stems, so "the poem's 'smokeless air'" shares 'poem', 'smokeless' and 'air'; a capitalised adjective of place is read as its place, so "decolonisation in Africa" shares 'africa' with "African states"; info when the item is optional). When the request labels its parts ("(a)", "Part (b)", "Guiding question:") and the answer labels its sections with some of the same labels, an item is addressed by the material claims of its own section (`CoverageRecord.method` `part_label`); otherwise the lexical test runs per claim and then per paragraph group, and a guiding question is addressed by a point, thesis or judgement sharing one of its terms |
| INT-REQ-005 | error / warning | a constraint not satisfied (formal result for word and paragraph bounds; a paragraph overrun is a layout warning). A bound the request sets on the prose only ("200 words, excluding working and the diagram", `Constraint.excludes`) is measured without equation lines, the lines of a working block and diagram lines, and the detail says how many words were so excluded "(prose only: N words of working and diagram excluded, as the request sets them outside the bound)" |
| INT-REQ-006 | warning | claim verification failed internally for a claim, or a claim's verification gave no verdict: its outcome is displayed INVALID_FORMALIZATION, INTERNAL_ERROR, UNKNOWN, TIMEOUT or UNSUPPORTED (a vacuous or circular proof, a failed translation, a result whose signature or binding the composer rejected). The finding names the claim and its displayed status, so a non-success outcome is never delivered under a clean ACCEPTED receipt |
| INT-REQ-007 | error / warning | a claim rests on premises that contradict each other (engine), charged only when the outcome is DISPLAYED as INCONSISTENT_PREMISES or AMBIGUOUS_TRANSLATION: an engine result the composer rejected (displayed INTERNAL_ERROR) charges nothing to the specialist and is INT-REQ-006. A warning when the translation was AMBIGUOUS_TRANSLATION: the contradiction is of the translator's assumed reading, which the message names with its ambiguity flags (a rounded figure encoded as an exact value, say), not of the claim |
| INT-REQ-008 | warning | a level-3 command term (evaluate, discuss, to what extent, assess, examine, justify, recommend, give a judgement) with no judgement or position on degree in the report |
| INT-REQ-009 | error | raw text the branch adapter could not parse, raw text (or a request) carrying a lone UTF-16 surrogate code point (a truncated emoji arriving as "\ud83d"; the finding names the character offsets; nothing raises, since every hash of agent text encodes a surrogate with `surrogatepass`), or a payload that does not re-validate against the contract; not delivered. A claim whose `report_id` or `request_id` differs from its report is not this code: it is INT-HANDOFF-012 naming the claim and the fields, decided on the raw payload before validation (for a report received as a mapping, by `respond` or `relay`, the claim's `report_id`, `request_id`, `task_id` and `agent_id` are compared before the contract is validated) |
| INT-REQ-010 | warning | a quotation whose words occur in the supplied text but whose form differs (initial capital, verse line-break mark, diacritics, an elision spanning more than the window): not an invented quotation; the branch rules covering the same excerpt are named, and no branch `-SRC-001` error for the claim reaches the receipt |
| INT-REQ-011 | error | the response restates the request instead of answering it: compared on light stems (-s, -es, -ed, -ing stripped) and, for the overlap, on content stems (function words such as "in", "is", "so", "through" set aside), its text is contained in the request's, or at least 90% of its distinct stems occur in the request and it is no longer than 1.5x the request, or at least 75% do, it is no longer than 2x the request and it quotes the request's own words as if they were the text's (a quotation found in the request but in no supplied text; this rule is evaluated whatever the first rule's length cap says); no item counts as addressed, its outcomes are not pooled and it supersedes nothing |
| INT-REQ-012 | error | the response carries no answer: none of its claims is material (every claim is roled `other`: a note, a label, a self-report) or its answer proper has 0 words; no item counts as addressed and it supersedes nothing. Delivered with the report (a content finding; the empty response stays INT-REQ-009) |
| INT-REQ-013 | warning | the branch adapter merged the claims beyond the contract limit into one tail claim without roling or checking them (its `unresolved_issues` say so): the finding says how many claims and how many quotations of the original response went unchecked, and which of those quotations occur in no supplied text, so a quotation placed after the limit never crosses silently |
| INT-REQ-014 | warning | a claim credits a relayed peer specialist's report (the clause after the peer's possessive, "the History specialist's figure of ...", "in the History specialist's account, ..."; after the peer as the subject of a reporting verb, "the History specialist gives ...", "as the History specialist notes, ..."; after "according to" the peer, or the clause that "..., according to the History specialist" closes; a clause never ends at the point of a decimal, "5.2 million", or after an abbreviation, "c. 1963") and states there, outside its quotations, figures or dates (digits or words) that occur in no supplied text, the peer's report included, named with their scale word ("2.5 million", never "2"); or a date the peer gives for another event (`ledger.credited_date_repairings`: "The History specialist dates the sonnet to 1886" where the peer dates the sonnet 1883 and the statue's dedication 1886; every event word of the clause the peer dates must disagree): a colleague's figure or date misreported in an unquoted paraphrase, or the agent's own unsupported figure; also, when a peer's report (or a specialist-authored text) was supplied, any claim, notes roled `other` included, that states a check result credited to the system or to a report outside its quotations ("A formal check failed the report's ...", "the Mathematics report's own checks flag ... as not holding"): no check result is content of a report, so the relayed outcome is named as a self-report the router must not read as checked |
| INT-REQ-015 | error | a quotation whose sentence credits it (a possessive or a crediting verb after the name: "Hardy's speaker himself admits that ...", "The poem says that ...") to a source the agent was NOT supplied (a text the router supplied to another agent of the task, or a text named by kind when none was supplied), while among the agent's supplied texts its words occur only in a relayed peer specialist's report and not in the credited text (for a text named by kind: in the peer's own prose, not in a quotation the peer made): a colleague's words presented as the source's. Names the claim, the credited text and the peer document. A credit to a supplied text is the packs' rule (CORE-SRC-005, ES-SRC-008), and a claim a pack already named under CORE-SRC-005 is not named again |
| INT-REQ-016 | warning | a delivered report carries a claim id that a report of ANOTHER agent already delivered on this task holds: the router now holds two different claims under one id and a synthesis citing it cannot be accounted for by id (INT-LEDGER-014), so the collision is named at delivery with both reports. The same agent re-using its ids is a supersession (INT-HANDOFF-009), and a report already held under its id collides with nothing |
| INT-SUBJ-001 | error | a formal check the branch pack built from the report's own statement (arithmetic, chronology, elasticity, margin; a STEM step, substitution, conversion, balance, root, Boolean identity) does not hold (engine): the engine's status is definitive and not the expected one. The finding names the delivered claim(s) whose text holds the statement (the pack's own `FormalCheck.claim_ids` when it gives them; else the claims holding every figure or dated event the problem's premises state; else the claims holding the sentence the check quotes) and quotes the clause the check was built from (from the phrase of its first figure or event to the stated derived figure, thousands separators ignored, so "an increase of 6,500 miles" is reached; a period's premise "1960 begins" is read as "1960"; boundaries read by `sources.clause_boundaries`, so the quote never starts or stops inside a decimal figure, after "c." or an initial, or inside a word, and a parenthetical label after the statement is left out), so junk before the statement never stands in for it; `receipt.formal_checks` carry the same `claim_ids`; for a STEM check the message also gives the counterexample's computed value `c` and stated value `r`, and the finding of a failed substitution also names, after those claims, the claims of `FormalCheck.related_claim_ids` (the statement whose stated value it contradicts; rule `related-statements`) |
| INT-SUBJ-002 | warning | such a check was undecided (named and quoted the same way): UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION, an internal error while deciding it, a vacuous proof (E108), INCONSISTENT_PREMISES on a check that does not count them as a failure (every STEM check), an unknown policy name (never run under another policy), or the report's STEM check budget (8 s) spent |
| INT-SUBJ-003 | error | a deterministic error of a branch pack, escalated with the branch key and rule |
| INT-SUBJ-004 | warning | a check that relied on a reading the report did not state does not hold (a STEM check with `failure_severity="warning"`: a data-booklet value for an unstated symbol, a symbol's identity across request and answer, a show-that target, a step that brings in unrelated symbols, an unknown unit); names the check's claims |
| BR-INTERNAL-001 | warning (structural) | a branch pack failed internally; its findings are missing and must not be read as a pass (`branches/base.py`); raised together with the hub's PACK-INTERNAL-001 (error, `branches/README.md`) for the same failing call |
| INT-STALE-011 | error | a claim outcome whose translation does not bind to the claim as transmitted (claim id, request, report, or `claim_text_sha256` of another text): stale; neither delivered nor pooled |
| INT-SYNTH-013 | warning | the channel's synthesis-formalization hook failed internally; the entailment was not checked |
| INT-SYNTH-014 | error | a synthesis that does not validate because a synthesized claim, a ledger entry or a conflict record carries a value outside one of the synthesis contract's closed vocabularies: a transformation that is not one of `carried`, `paraphrased`, `merged`, `narrowed`, `generalized`, `new`, `dropped` (`integrity.contracts.TRANSFORMATION_MEANINGS`; a synthesized claim takes one of the first five, and a description of the edit, an alias such as 'joined' or another spelling is no transformation), a certainty, a materiality or a conflict status outside its set. Raised with the INT-REQ-009 that refuses the synthesis (not delivered, nothing stored), for a synthesis received as JSON and for a synthesis object built around validation (`model_copy`, `model_construct`), which is re-validated before any check; one finding names every such synthesized claim (and the source claims of a ledger entry), the field and the rule, quotes a one-word value and describes free text only by its length, so no agent prose is echoed. The ledger's rules are chosen by these values, so none of them ran on the synthesis |
| INT-INTERNAL-001 | error | the branch's integrity packs failed internally on this report: its subject findings and its own formal checks are missing from the receipt (the report is delivered with this finding; nothing raises into the router). Every other content check of `respond` and `relay` (claim-id collisions, quotations, peer figures, folds, echo, no answer, coverage, constraints, credits, supersession, claim verification, the cross-agent check, and on a synthesis the ledger, conflicts and entailment) runs guarded the same way: one that fails internally is "the channel's <check> check failed internally (<error>)", and the rest of the receipt is still produced |

On a synthesis receipt the channel also raises INT-SYNTH-012 (warning) for every material 'paraphrased', 'narrowed',
'merged' or 'generalized' claim whose content change no formal conclusion checked on the channel (the Overseer's
`run_integrity_checks` keeps INT-SYNTH-006, an error, for a merged or generalized one). A synthesis id is held like a
report id: the first synthesis delivered under it is kept (`TranslatorChannel.syntheses`), the same content again to a
recipient that holds it is INT-ENV-001, and other content under it is INT-HANDOFF-015 naming the fields and synthesized
claims that differ, not delivered.

Cross-agent findings (INT-GLOSSARY, INT-CONFLICT) over a pooled claim whose translation was AMBIGUOUS_TRANSLATION
say so: its pooled formalization is one assumed reading, not a fixed one.

## Branch formal checks (`_branch_checks`)

Each branch formal check runs under its named engine policy (`engine.policies`): `linear` is the
channel's configuration unchanged (every pre-STEM check; results byte-identical), `nonlinear` opens
the nonlinear-term gate under a deterministic `rlimit` (`NONLINEAR_RLIMIT`), and the signed result
records the non-default limits. An unknown policy name is never run under another policy
(INT-SUBJ-002). The status maps to `ConstraintResult.satisfied`:

| Engine status | satisfied | finding |
| --- | --- | --- |
| the expected status, with no E108 diagnostic | True | none |
| the expected status with E108 (vacuous: no premise used) | None | INT-SUBJ-002 |
| any other definitive status (COUNTEREXAMPLE, UNSATISFIABLE where SATISFIABLE is expected, SATISFIABLE where UNSATISFIABLE is expected, ...) | False | INT-SUBJ-001, or INT-SUBJ-004 for `failure_severity="warning"` |
| INCONSISTENT_PREMISES when the check sets `inconsistent_is_failure=False` | None | INT-SUBJ-002 |
| UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION, INTERNAL_ERROR | None | INT-SUBJ-002 |

Every result and finding names the delivered claims that hold the checked statement (the check's own
`claim_ids` first) and quotes its clause. A detail longer than the contract (2,000 characters)
is cut, never raised (finding messages are cut by the finding contract), and an exception while
deciding one check makes that check alone undecided. Recorded behaviour changes (design section 18):
an ENTAILED result carrying E108 is undecided, no longer ok; SATISFIABLE where UNSATISFIABLE is
expected is a failure, no longer undecided; INT-SUBJ-001 and INT-SUBJ-002 carry claim ids; INT-SUBJ-004
and BR-INTERNAL-001 are new. Non-success statuses are never shown as success.

## Branch hub hooks (STEM branches only)

A branch may lend the channel `hub_hooks` (`branches.base.BranchHooks`); only the three STEM
branches do (`stem/hub_hooks.py`), so every other branch reads requests and answers as before:

* `request_imperatives` (determine, deduce, derive, state, find, solve, sketch, estimate, predict,
  verify, show): passed to `extract_items(text, extra_imperatives=...)`, read at the start of a
  sentence or after a part label, and a line that opens with a part label starts a new sentence,
  so a multi-part STEM question is one item per part, the same items the general reading gives;
  the rubric's "Show your working (with units)." or "Show full working." is no item under them
  either (`_SHOW_WORKING_RE`);
* `coverage_terms`: words a claim offers the INT-REQ-004 heuristic beyond its own (the dimension
  names of its quantities and bound symbols: m s⁻² gives "acceleration", N "force"; the computing
  command words for a claim the engine checks), so an equation-only answer covers "Calculate the
  acceleration"; still a lexical heuristic;
* `echo_exempt`: an answer holding a planned computation link (`stem-eq`, `stem-alg`, `stem-sol`)
  whose text is not in the request is never INT-REQ-011, so a correct show-that answer is not a
  restatement;
* `word_count_view`: the text `measure_answer_words(text, excludes=..., view=...)` counts for word
  bounds (the working and diagram exclusions of the request read on it) and `count_answer_words(text,
  view=...)` for INT-REQ-012: a maths span or a code block is one word, LaTeX control words are none.

A hook that fails falls back to the channel's own reading. Raw text reaches a parser that declares
`accepts_request_text` (the STEM parser) with the request text, so the parser and the STEM pack read
one document.

Coverage of request items is a lexical heuristic until adapters tag claims with the
items they address; the receipt says so. Only material claims (not roled `other`) can
address an item. The translator and adapter are injected (`verify_claim_fn`), so the
channel runs with fixtures today and with the live pipeline when configured. A verifier that
declares a `task` parameter is called `fn(claim, report, task=...)` with the task record of the
request the report answers (`translate.contracts.TaskRecord`: the router's request text as issued),
so a premise that claims the task's authority (`arithmetic_fact`, `task_setting`, `rubric_rule`) can be
validated against the task's own wording and a fidelity reviewer is shown the original task; a
verifier with the two-argument signature is called as before, and its task-authority premises stay
unvalidated (listed as unverified dependencies; release never permitted on them). The channel
releases no answer itself: each outcome carries its release assessment (`ClaimVerificationOutcome.release`)
for the application that does.
