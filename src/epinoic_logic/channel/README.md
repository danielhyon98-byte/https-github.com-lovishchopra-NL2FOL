# channel — the path every inter-agent message takes

This is the primary feature of the infrastructure. Agents never hand each other
raw text; everything crosses the `TranslatorChannel`, which makes requests explicit,
checks responses against the request they answer, and attaches a receipt.

```
router ──request()──► TaskRequest (items, constraints, texts) in a hashed envelope ──► specialist
            never raises: a request the contract cannot carry (an id that is no string of 1 to 128 characters, a text
            that is not text, is empty, holds no visible character (only zero-width, format or control characters:
            `_asks_nothing`, repair round 2) or is over 400,000 characters, more than 16 supplied texts) is REJECTED with
            INT-REQ-009; items and constraints beyond the contract's 64 are counted (INT-REQ-018), identical
            constraints stated once; a peer document (peer:<task>) whose author delivered a report on this channel
            must be that report word for word, credited to its author (INT-HANDOFF-013: never receipt text or findings)
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
            a response handed over as a mapping (a report as JSON) is validated strictly, as the JSON it is ("yes" is no
            boolean, "1" no integer; a coerced value is INT-REQ-009 naming the field, and a field's contract error names
            the validator's own message, never the field's value: `_shape_reason`) and checked like a report, anything else
            (None, a number) is REJECTED with INT-REQ-009; an integrity pack that fails is INT-INTERNAL-001 on the receipt
agent ──relay()──► another agent (report or synthesis): envelope, sender = payload owner (INT-ENV-008), sender and
            recipient selected by the plan (INT-HANDOFF-002; the router and the Overseer are infrastructure parties, and
            an infrastructure role is held, not asserted: an id the plan selects as a specialist or combinator, or a
            "router" other than the sender of the channel's requests, is INT-ENV-007), a synthesis id reused with other
            content refused (INT-HANDOFF-015), ledger, figure/date fidelity (decades and small counts in words included),
            quotations of the synthesis located and credited to a text that holds them (INT-LEDGER-025), direction,
            polarity and who holds a view (INT-LEDGER-026), from-memory labels kept (INT-LEDGER-027), undisclosed
            contradictions (INT-CONFLICT-002), entailment checks, and every material paraphrase or merge left unchecked
            stated (INT-SYNTH-012); a payload handed over as a mapping is validated strictly against the contract its shape names,
            anything else is REJECTED with INT-REQ-009 and nothing raises; a synthesis carrying a value outside one of the
            contract's closed vocabularies (a transformation written as a description of the edit) is also named,
            INT-SYNTH-014, and a synthesis object built around validation is re-validated and refused the same way
router ──relay()──► peer specialist: a DELIVERED report forwarded unchanged (`specialist_report_forward/1.0`);
            the channel checks the forward against the delivery (INT-HANDOFF-013: never delivered / altered in transit /
            in reply to a message that is not the report's delivery); a forward naming no delivery is tied, in its own
            envelope, to the report's first delivery to that router (`forward_of`), and the gap is named (INT-HANDOFF-018,
            warning). An agent's relay hands on only a
            report its sender already delivered (INT-HANDOFF-013 otherwise; a new report arrives only through respond()).
            Parties the envelope cannot carry (an id, a role as no agent role, an in_reply_to that is no message id) are
            refused with INT-REQ-009 before the payload is read; a role given as its value ("router") is that role
relay history: a relayed or forwarded report's receipt references the report's earlier delivered receipts and carries
            what they left unresolved (INT-HIST-001), so a relay without the request, or a forward that re-checks nothing,
            never reads cleaner than the report's arrival; a synthesis carries it for the claims it cites
```

A receipt is ACCEPTED only when it has no finding and every claim outcome is a verdict a clean receipt can stand on:
an engine non-result (TIMEOUT, UNKNOWN), a claim displayed INVALID_FORMALIZATION (a vacuous or circular encoding, E108,
E110 to E112, an invalid translation), INTERNAL_ERROR (a result the composer refused: signature, binding, staleness),
AMBIGUOUS_TRANSLATION (the chosen reading's engine status is never the claim's verdict) or UNSUPPORTED (the encoding
cannot express the claim), or a TRANSLATED claim whose display is not the engine's status, makes it
ACCEPTED_WITH_FINDINGS, and the summary names those claims ("No verdict a clean receipt could stand on for claim(s)
..."). A NOT_ELIGIBLE claim was never put to the engine and is reported by its display alone.

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
request (a mapping report whose original response is one JSON object wrapping the answer, `{"answer": "..."}`, has the
words of the string values that hold a material claim's own text, so it has an answer, while a response that is only a
JSON receipt, `{"status": "ok"}`, still has none: `bus._wrapped_answer_words`, repair round 2); a response that restates the request (INT-REQ-011) is delivered, counts for no item, is
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
| `contracts.py` | `TaskRequest` (immutable user input hash, request items, constraints; a `Constraint.excludes` lists what a word bound leaves out, "working" and "diagram", when the request says so, and `Constraint.scope`, a `ConstraintScope` of kind `whole`, `part`, `each_part`, `answer_proper` or `paragraph` with its part labels, the span the bound is set on; None is the whole answer and dumps as before), `CoverageRecord` (method `lexical` or `part_label`), `TransmissionReceipt` (status ACCEPTED / ACCEPTED_WITH_FINDINGS / REJECTED, findings, coverage, constraint results with signed formal result ids, claim outcomes, summary). |
| `request_parser.py` | Deterministic extraction of questions/instructions and of word, paragraph and citation constraints (`extract_items(text, extra_imperatives=...)`, `count_answer_words(text, view=...)` and `measure_answer_words(text, excludes=..., view=...)` take a branch's hooks; the defaults are the general reading). A word is a run of letters, digits, apostrophes and hyphens, and a figure with internal separators ("1.9", "100,000", "63.2%") is ONE word (`count_words`). Conservative: nothing asked is dropped. A sentence that mixes a constraint with a content instruction ("Write no more than 200 words and give a judgement on which effect mattered most") yields the instruction as an item with the constraint span removed; a sentence that is only a constraint yields none. `extract_items` gives one item per labelled part of the request ("(a)", "Part (b)", "Guiding question:"; `request_parts`, `part_label`) and, outside the parts, one per question (an opening "¿" included), imperative or "Please ..." sentence. `count_answer_words` (over `measure_answer_words`, which also takes the constraint's `excludes`: equation lines are working whole, and inside a working block a line quoting an equation is too) measures a word bound over the answer proper, leaving out the note blocks and note clauses `count_paragraphs` leaves out, and the receipt says how many words were meta-text. A blank-line block opened by a note label ("Note:", "NB:", "Note on sources:") whose every sentence is about the answer (its sources or their availability, a correction of the task's marks or figures, what the writer used) is a note block (`is_note_block`): no paragraph and no words of a bound; a block so labelled that states content stays answer. Sentences are cut as the parsers cut them: a pasted JSON span glued into a paragraph (`markdown.split_json_spans`) is one piece of meta-text on its own, so `{"n": 1}` added to a paragraph takes only its own two words out of the count and the prose around it stays answer (a block that is nothing but a JSON span is no paragraph). "about / around / approximately N words" bounds the length on both sides, 0.9N to 1.1N (c1 the minimum, c2 the maximum, as for "between A and B words"); "in N words" stays a soft maximum of 1.1N. A sentence is a note only when nothing is left once its note clauses are set aside (`markdown.split_note_clauses`), the rule the parsers role by: a dated sentence with an inline "(from memory)" is answer, its label meta-text. One meta-text classifier, `is_meta_text(block, last=...)`, serves both counts (E2E B19): a note block, a word count on its own ("Word count: 249", "(249 words)"), a "Next step:" footer, a "Limit:" footer about the answer's sources or checks (a mathematics "Limit:" heading stays content) and a closing one-line note that addresses the reader about the answer ("paste your own paragraph and I will give provisional marks"). `bound_scope` binds a word bound to the span the request names (labels before the bound or the request part it stands in, "each", "for the answer", the paragraph the request asks for; "in total" keeps the whole answer), "N words max" and "max N words" are read, `part_section_text` gives the answer's section of a part and `deliverable_blocks` the paragraph or answer proper without a plan, meta-text and side answers to the student's other questions. `extract_items_counted` and `extract_constraints_counted` count what goes beyond the contract's 64; `is_format_instruction` tells an instruction on the answer's form or language from a content ask; `strip_constraint_spans` removes only a constraint's own words, so "Please quote my exact words" keeps "quote". Re-exports `VERDICT_CUES`. |
| `cues.py` | `VERDICT_CUES`: the lower-cased phrases that state a position on degree ("on balance", "mattered most", "matters most", "weighed by", "by the criteria", "by the criterion", "outweigh" and its inflections, "to a large extent", "therefore", ...). The channel's verdict test for INT-REQ-008 is built from it (`verdict_cue_regex()`), and the subject parsers import it (`from epinoic_logic.channel.cues import VERDICT_CUES`; the module has no imports, so no cycle) so the hub and a parser never disagree about what a judgement looks like. It also holds the closed tables of INT-REQ-017 (`SYSTEM_CHECK_PHRASES`, `FINDING_CODE_PATTERN`), of the format instructions (`FORMAT_WORDS`, `FORMAT_PHRASES`, `FORMAT_VERBS`, `FUNCTION_WORDS`, `FORMAT_SUBORDINATORS`) and of the answer's layout (`SIDE_REPLY_OPENERS`, `PLAN_HEADINGS`, `META_LABELS`, `READER_ADDRESS_CUES`), and `phrase_regex(phrases)`. The tables are English: an answer in another language gets fewer of these readings, a miss rather than a false alarm. |
| `gate.py` | The response gate (E2E B13): `assess_response(receipts, synthesis_receipt=None, *, synthesis_required, threshold=0.90) -> ResponseGate` classifies every check the receipts carry as passed, failed, unresolved or not required (rules in the module docstring: a positive display passes only on established premises, with no warning diagnosis by effective severity, a capped one included, and a release not refused; a negative display, an engine-established error and a deterministic source-integrity error fail; heuristic findings, argument diagnoses, checks that did not run, warnings and claims without a verdict, NOT_ELIGIBLE included, stay unresolved), and decides VERIFIED (every required check passed, one of them formal), DELIVERED_UNVERIFIED (labelled "not verified"; accuracy passed / (passed + failed) above the threshold) or WITHHELD. The synthesis is a required check only when the plan routes to a combinator. Never raises (fail closed: WITHHELD with the reason); `ResponseGate.invariants()` hold for every decision. |
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
| INT-REQ-002 | error | the report carries a supplied text the request did not send, or another text under a document id the request sent (compared by document id and the digest of the text, also when the request sent none), or the request's text under other metadata (another title, author, locator scheme or provenance: the record the quotation credits read): the request's texts are the only source set the channel checks quotations against, and a report never substitutes its own; not delivered |
| INT-REQ-003 | error | a quotation the cited document does not contain: "not found in the supplied texts [ids]" (when one text, or the request, holds all of its words but one or two, the message names it as the nearest text and the quotation as altered), or "occurs in [other ids] (misattributed)"; a citation of a document not supplied; a locator the text cannot carry. An excerpt the request itself holds (the task's own words quoted back) is located, not invented. A quotation the parser credited to no text is refuted the same way when texts were supplied, its words occur in none of them nor in the request, its sentence carries no from-memory label, and either one supplied text (or the request) holds all of its words but one or two (an altered quotation; a relayed colleague's report counts only when no other text was supplied) or its sentence credits it by kind to the text under analysis ("The narrator also insists that '...'"); the packs' "unverifiable" CORE-SRC-003 for that claim then stays off the receipt. A quotation credited to another source ("One critic writes that ...") stays unverifiable |
| INT-REQ-004 | warning / info | a request item appears unaddressed (lexical heuristic over the material claims, notes excluded; terms are read without quotation marks or a possessive 's and compared on light stems, so "the poem's 'smokeless air'" shares 'poem', 'smokeless' and 'air'; a capitalised adjective of place is read as its place, so "decolonisation in Africa" shares 'africa' with "African states"; info when the item is optional). When the request labels its parts ("(a)", "Part (b)", "Guiding question:") and the answer labels its sections with some of the same labels, an item is addressed by the material claims of its own section (`CoverageRecord.method` `part_label`); otherwise the lexical test runs per claim and then per paragraph group, and a guiding question is addressed by a point, thesis or judgement sharing one of its terms. An item's command words and the instructions on the form of its answer ("calculate", "find", "determine", "solve", "value", "answer", "significant figures", "exact", "given": `bus._COMMAND_STEMS`) are no evidence on their own: when the item names anything else (a quantity, "the acceleration", "the pH"), the shared terms must include one of those topic terms, or the branch's hooks must find the claim about the item (`topic_evidence`, below), so "2 + 2 = 4" addresses no "Calculate the acceleration" and one irrelevant sum leaves three requested quantities unaddressed (STEM review S3). An item whose words are all command words but which names what it asks for in notation (the hooks' `names_notation`: "Solve 3x + 5 = 20", "Simplify √50") is addressed only by a claim `topic_evidence` finds about that notation; an item that names neither keeps the plain reading. The items are the request's asks (E2E B18): a stem that asks nothing, followed by its own sub-parts that do ("1. Priya buys a car ...", "2. The Python code ... is pasted below."), and a bare part label ("(a)" before "(i)") are no items; an instruction on the form or language of the answer only ("Explain in English pls", "Please quote my exact words when you point out a mistake", `request_parser.is_format_instruction`) is listed but not required (an info finding when unaddressed); an answer section labelled "(a)(i)" or "1(a)" covers its part; a claim that is a table row offers the word "table" ("Construct the truth table"); stems match y to ies (burglary, burglaries). A request with exactly one required item (and an answer with a material claim, no restatement, an answer proper) has no other item a claim could be answering: when the lexical test finds no claim, a material claim that shares one topic word with the request text addresses it; form words, function words and the frame of the ask ("Evaluate the CLAIM that ...", `bus._NOT_TOPIC_STEMS`) are no topic words, so a bare quotation or an answer on another subject still addresses nothing |
| INT-REQ-005 | error / warning | a constraint not satisfied (formal result for word and paragraph bounds; a paragraph overrun is a layout warning). A bound the request sets on the prose only ("200 words, excluding working and the diagram", `Constraint.excludes`) is measured without equation lines, the lines of a working block and diagram lines, and the detail says how many words were so excluded "(prose only: N words of working and diagram excluded, as the request sets them outside the bound)". A word bound is measured on its scope (`Constraint.scope`, E2E B4): the answer's section of the part it names ("keep (e) under 150 words"), each listed part on its own ("(e) and (f) under 120 words each", one problem over every part), the answer proper without a plan or side answers ("max 500 words for the answer"), or the paragraph the request asks for ("ONE paragraph ... max 250 words"). A part the answer does not label is never measured on another span: the whole answer decides only what it proves about the part (a maximum the whole answer is within, a minimum it falls short of), and otherwise the bound is not checkable on its scope, a warning that says so |
| INT-REQ-006 | warning | claim verification failed internally for a claim; or the engine result of a claim reports inconsistent premises but the outcome composer did not trust it (signature, binding, staleness; displayed INTERNAL_ERROR): nothing is charged to the specialist |
| INT-REQ-007 | error / warning | a claim rests on premises that contradict each other (engine), on a result the composer trusts (an untrusted one is INT-REQ-006). A warning when the translation was AMBIGUOUS_TRANSLATION: the contradiction is of the translator's assumed reading, which the message names with its ambiguity flags (a rounded figure encoded as an exact value, say), not of the claim |
| INT-REQ-008 | warning | a level-3 command term (evaluate, discuss, to what extent, assess, examine, justify, recommend, give a judgement) with no judgement or position on degree in the report |
| INT-REQ-009 | error | raw text the branch adapter could not parse, raw text (or a request) carrying a lone UTF-16 surrogate code point (a truncated emoji arriving as "\ud83d"; the finding names the character offsets; nothing raises, since every hash of agent text encodes a surrogate with `surrogatepass`), or a payload that does not re-validate against the contract; not delivered. A claim whose `report_id` or `request_id` differs from its report is not this code: it is INT-HANDOFF-012 naming the claim and the fields, decided on the raw payload before validation (for a report received as a mapping, by `respond` or `relay`, the claim's `report_id`, `request_id`, `task_id` and `agent_id` are compared before the contract is validated) |
| INT-REQ-010 | warning | a quotation whose words occur in the supplied text but whose form differs (initial capital, verse line-break mark, diacritics, an elision spanning more than the window): not an invented quotation; the branch rules covering the same excerpt are named, and no branch `-SRC-001` error for the claim reaches the receipt |
| INT-REQ-011 | error | the response restates the request instead of answering it: compared on light stems (-s, -es, -ed, -ing stripped) and, for the overlap, on content stems (function words such as "in", "is", "so", "through" set aside), its text is contained in the request's, or at least 90% of its distinct stems occur in the request and it is no longer than 1.5x the request, or at least 75% do, it is no longer than 2x the request and it quotes the request's own words as if they were the text's (a quotation found in the request but in no supplied text; this rule is evaluated whatever the first rule's length cap says); no item counts as addressed, its outcomes are not pooled and it supersedes nothing |
| INT-REQ-012 | error | the response carries no answer: none of its claims is material (every claim is roled `other`: a note, a label, a self-report) or its answer proper has 0 words; no item counts as addressed and it supersedes nothing. Delivered with the report (a content finding; the empty response stays INT-REQ-009) |
| INT-REQ-013 | warning | the branch adapter merged the claims beyond the contract limit into one tail claim without roling or checking them (its `unresolved_issues` say so): the finding says how many claims and how many quotations of the original response went unchecked, and which of those quotations occur in no supplied text, so a quotation placed after the limit never crosses silently |
| INT-REQ-014 | warning | a claim credits a relayed peer specialist's report (the clause after the peer's possessive, "the History specialist's figure of ...", "in the History specialist's account, ..."; after the peer as the subject of a reporting verb, "the History specialist gives ...", "as the History specialist notes, ..."; after "according to" the peer, or the clause that "..., according to the History specialist" closes; a clause never ends at the point of a decimal, "5.2 million", or after an abbreviation, "c. 1963") and states there, outside its quotations, figures or dates (digits or words) that occur in no supplied text, the peer's report included, named with their scale word ("2.5 million", never "2"); or a date the peer gives for another event (`ledger.credited_date_repairings`: "The History specialist dates the sonnet to 1886" where the peer dates the sonnet 1883 and the statue's dedication 1886; every event word of the clause the peer dates must disagree): a colleague's figure or date misreported in an unquoted paraphrase, or the agent's own unsupported figure |
| INT-REQ-015 | error | a quotation whose sentence credits it (a possessive or a crediting verb after the name: "Hardy's speaker himself admits that ...", "The poem says that ...") to a source the agent was NOT supplied (a text the router supplied to another agent of the task, or a text named by kind when none was supplied), while among the agent's supplied texts its words occur only in a relayed peer specialist's report and not in the credited text (for a text named by kind: in the peer's own prose, not in a quotation the peer made): a colleague's words presented as the source's. Names the claim, the credited text and the peer document. A credit to a supplied text is the packs' rule (CORE-SRC-005, ES-SRC-008), and a claim a pack already named under CORE-SRC-005 is not named again |
| INT-REQ-016 | warning | a delivered report carries a claim id that a report of ANOTHER agent already delivered on this task holds: the router now holds two different claims under one id and a synthesis citing it cannot be accounted for by id (INT-LEDGER-014), so the collision is named at delivery with both reports. The same agent re-using its ids is a supersession (INT-HANDOFF-009), and a report already held under its id collides with nothing |
| INT-REQ-017 | warning | an answer built on a peer report (a `peer:` document among its supplied texts) hands a system check result to the reader as subject content: a closed phrase of `cues.SYSTEM_CHECK_PHRASES` ("a formal check failed ...", "the engine found ...", "own checks flag ...", "do not copy those ...") or a finding code ("INT-SUBJ-001"), outside its quotations (E2E B3). Names the claim and quotes its sentence. Bare subject words ("engine", "check", "counterexample") and the peer's own quoted words or figures are no such statement |
| INT-REQ-018 | warning | the request states more items or constraints than the contract's 64: they are counted, not extracted, so no check covers them; the first 64 of each are checked (the request is delivered) |
| INT-XENC-001 | warning | two encodings of one claim reach opposite definitive answers (E2E B20): a branch formal check of a clause the claim states fails while the translation of the whole claim is displayed ENTAILED, CONSISTENT or SATISFIABLE on a result the composer trusts. Names the claim, the check's result (`formal_result_id`) and the translation's (`related_result_ids`). Neither verdict is withdrawn (the check's INT-SUBJ-001 stays); the response gate counts the claim and the check unresolved. A check that holds beside a negative verdict is no disagreement: the claim may fail on a clause or link the check does not read |
| INT-SUBJ-001 | error | a formal check the branch pack built from the report's own statement (arithmetic, chronology, elasticity, margin; a STEM step, substitution, conversion, balance, root, Boolean identity) does not hold (engine): the engine's status is definitive and not the expected one. The finding names the delivered claim(s) whose text holds the statement (the pack's own `FormalCheck.claim_ids` when it gives them; else the claims holding every figure or dated event the problem's premises state; else the claims holding the sentence the check quotes) and quotes the clause the check was built from (from the phrase of its first figure or event to the stated derived figure, thousands separators ignored, so "an increase of 6,500 miles" is reached; a period's premise "1960 begins" is read as "1960"; boundaries read by `sources.clause_boundaries`, so the quote never starts or stops inside a decimal figure, after "c." or an initial, or inside a word, and a parenthetical label after the statement is left out), so junk before the statement never stands in for it; `receipt.formal_checks` carry the same `claim_ids`; for a STEM check the message also gives the counterexample's computed value `c` and stated value `r` |
| INT-SUBJ-002 | warning | such a check was undecided (named and quoted the same way): UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION, an internal error while deciding it, a vacuous proof (E108), INCONSISTENT_PREMISES on a check that does not count them as a failure (every STEM check), an unknown policy name (never run under another policy), or the report's STEM check budget (8 s) spent |
| INT-SUBJ-003 | error | a deterministic error of a branch pack, escalated with the branch key and rule |
| INT-HIST-001 | the original's | relay history: an unresolved finding of an earlier delivered transmission that this one builds on (a relay or forward of a report: that report's arrival and earlier relays; a synthesis: the transmissions of the reports it cites, for the claims it cites, a finding about the report's paragraphs or sentence style aside), carried with its own severity, claims, reports, agents, documents and signed result; the message names the receipt it comes from and the original code. Never blocking: a carried error is an error of the history, the report is still delivered. `TransmissionReceipt.history` references every earlier receipt with what it left unresolved (`ReceiptReference`) |
| INT-SUBJ-004 | warning | a check that relied on a reading the report did not state does not hold (a STEM check with `failure_severity="warning"`: a data-booklet value for an unstated symbol, a symbol's identity across request and answer, a show-that target, a step that brings in unrelated symbols, an unknown unit); names the check's claims |
| INT-ARG-001 | error / warning | a named diagnostic of the argument diagnosis (rules `argdiag-2`) at warning or error, on a material claim, from a claim outcome or from the report level. The finding carries the diagnostic's `defect` and severity. None is added where another finding already states the condition (ARG-CONTRA-001: INT-REQ-007). Info diagnostics never become findings. Every receipt also carries `named_diagnostics`: each outcome's, the report level's, and one for each finding labelled by `named.DEFECT_OF_CODE`. The summary counts them before the scope tail. |
| BR-INTERNAL-001 | warning (structural) | a branch pack failed internally; its findings are missing and must not be read as a pass (`branches/base.py`); raised together with the hub's PACK-INTERNAL-001 (error, `branches/README.md`) for the same failing call |
| INT-STALE-011 | error | a claim outcome whose translation does not bind to the claim as transmitted (claim id, request, report, or `claim_text_sha256` of another text): stale; neither delivered nor pooled |
| INT-SYNTH-013 | warning | the channel's synthesis-formalization hook failed internally; the entailment was not checked |
| INT-SYNTH-014 | error | a synthesis that does not validate because a synthesized claim, a ledger entry or a conflict record carries a value outside one of the synthesis contract's closed vocabularies: a transformation that is not one of `carried`, `paraphrased`, `merged`, `narrowed`, `generalized`, `new`, `dropped` (`integrity.contracts.TRANSFORMATION_MEANINGS`; a synthesized claim takes one of the first five, and a description of the edit, an alias such as 'joined' or another spelling is no transformation), a certainty, a materiality or a conflict status outside its set. Raised with the INT-REQ-009 that refuses the synthesis (not delivered, nothing stored), for a synthesis received as JSON and for a synthesis object built around validation (`model_copy`, `model_construct`), which is re-validated before any check; one finding names every such synthesized claim (and the source claims of a ledger entry), the field and the rule, quotes a one-word value and describes free text only by its length, so no agent prose is echoed. The ledger's rules are chosen by these values, so none of them ran on the synthesis |
| INT-INTERNAL-001 | error | the branch's integrity packs failed internally on this report: its subject findings and its own formal checks are missing from the receipt (the report is delivered with this finding; nothing raises into the router). Every other content check of `respond` and `relay` (claim-id collisions, quotations, peer figures, folds, echo, no answer, coverage, constraints, credits, supersession, claim verification, the cross-agent check, and on a synthesis the ledger, conflicts and entailment) runs guarded the same way: one that fails internally is "the channel's <check> check failed internally (<error>)", and the rest of the receipt is still produced |

INT-REQ-009 also refuses, never raises on: a request the contract cannot carry (above); a reply whose request message id
is no string of 1 to 128 characters (an unknown id, INT-REQ-000); raw text that is a JSON report cut short (refused
naming the truncation; a whole JSON report sent as text is read as the report, not as prose); relay parties the envelope
cannot carry. A payload that fails a model validator names its contract and the validator's own message ("synthesis:
text_sha256 does not match text", "synthesis: duplicate synthesized claim ids"), never "report: value_error" for a
synthesis. INT-HANDOFF-013 also names a peer document that is not the colleague's report as delivered, a report relayed
by an agent that never delivered it, and a forward in reply to a message that is not the report's delivery.

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
  names of its quantities and bound symbols: m s⁻² gives "acceleration", N "force"; the names of
  their units: "mm" gives "millimetre", "%" "percentage"; what its relations produce: stated roots
  "root" and "solution", an order relation "inequality", a balanced equation "equation" and
  "reaction", a truth table "truth table", a base conversion "binary", "denary", "hexadecimal"; a
  derivative "gradient"; a component's direction, `F_x` "horizontal component"; the computing
  command words for a claim the engine checks), so an equation-only answer covers "Calculate the
  acceleration"; still a lexical heuristic, and the command words count only for an item that
  names nothing else;
* `topic_evidence` (optional; read through `getattr`): whether a computing claim is about an item
  beyond the words they share: it gives a value to a symbol the item asks for ("Find S₁₀" and
  `S_{10} = 210`; "Calculate v if ..."; a show-that target; the unknowns of an equation to solve; never
  a symbol the item gives a value for) or computes with enough of the item's own figures (shared
  figures weighing three, a single-digit whole number weighing one and any other figure two, or its
  only figure when that is no single-digit whole number) while the units it states name no other
  quantity than the item names in words, so "Find the gradient of the line through (1, 3) and (5, 7)"
  is addressed by `m = (7 − 3)/(5 − 1) = 1` and not by "2 + 2 = 4" (nor is "4 m/s in 2 s"), and a
  distance computed from an item's data does not answer its acceleration;
* `names_notation` (optional; read through `getattr`): whether an item whose words are all command
  words names what it asks for in maths (a figure that is no label, mark or precision instruction, or
  a symbol); such an item then needs `topic_evidence` (with `notation_only=True`);
* `echo_exempt`: an answer holding a planned computation link (`stem-eq`, `stem-alg`, `stem-sol`)
  whose text is not in the request is never INT-REQ-011, so a correct show-that answer is not a
  restatement;
* `word_count_view`: the text `measure_answer_words(text, excludes=..., view=...)` counts for word
  bounds (the working and diagram exclusions of the request read on it) and `count_answer_words(text,
  view=...)` for INT-REQ-012: a maths span or a code block is one word, LaTeX control words are none.

A hook that fails falls back to the channel's own reading. Raw text reaches a parser that declares
`accepts_request_text` (the STEM parser) with the request text, so the parser and the STEM pack read
one document. A parser that declares `accepts_task_agents` (the STEM parser) also gets `task_agent_ids`: the agents of
the answering agent's branch that delivered on the task, and the answering agent (E2E B17). With two or more, the STEM
parser qualifies every claim id by agent (`s1.1@ess-specialist`), so Chemistry and ESS on one task never share an id
(no INT-REQ-016); one agent, or agents of different STEM branches (which number with their own letters `s`, `m`, `c`),
keep plain ids (`tests/channel/test_stem_task_agents_b17.py`).

Relay history (STEM review): every delivered transmission of a report or synthesis is recorded
(`TranslatorChannel.payload_history`). A relay of a report (it runs without the request, so no Given
or show-that check, no coverage, no word bound) and a router forward (it re-checks nothing) reference
the report's earlier receipts in `TransmissionReceipt.history` and carry each unresolved finding (an
error or warning of the receipt's own, a subject finding of warning severity) as INT-HIST-001 with
its own severity, once, unless the new receipt states it again itself; a synthesis references the
receipts of the reports it cites and carries what names a claim it cites (close round 2: no finding about the report's
paragraphs or sentence style, which stays in the history it references). A refused transmission is
no history; a clean arrival is referenced and carries nothing, so its relay stays ACCEPTED.

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

**Repair round 3.** The response gate (`gate.py`) reads only structured data: a carried finding (INT-HIST-001) is
recognised by making it again from the receipt's history with `contracts.carried_finding`, never by parsing its message,
so a report id cannot turn a carried error into a coverage record (ADV3-02); a positive display passes only when the
engine's diagnosis ran to the end (`argument_rules`), no claim or report rule is listed in `diagnosis_incomplete`, and a
release assessment was made and permits release (INV-7). The channel's peer filters use the normalised peer id test
(`adapters.sources.is_peer_text`, that is `translate.grounding.is_peer_document`, which reads the normalised id: `is_peer_id`). Tests: `tests/channel/test_repair_round3_gate.py`.

**Repair round 4.** The channel sets the plan's task type around every parse and pack run of a delivery, relay and
respond (`bus._quotation_task`, `adapters.markdown.quotation_task(..., authoritative=True)`), so the quotation roles of
a report are read in the task the router planned and a report cannot widen them by naming another task type; an altered
quotation framed as a correction in an analysis is then checked and the response gate withholds the answer. A line of
worked arithmetic is answer proper in every subject (`_worked_calculations`), so an answer that is one correct
calculation is not "no answer" (INT-REQ-012). Tests: `tests/adapters/test_repair_round4_quotations.py`,
`tests/channel/test_repair_round4_answer_words.py`.

**Repair round 5.** The text intake unwraps an answer in envelopes nested up to four levels ('{"response": {"text":
"..."}}', each level one answer key) and in one envelope tag ('<answer>...</answer>': `_answer_in_envelope`,
`_answer_in_tag`), and refuses a structured reply cut off in transit (a Python-notation envelope or an envelope tag left
unclosed, a JSON report after prose: `_cut_structured_reply`, INT-REQ-009, REJECTED); a dictionary or a JSON example an
answer writes as content is prose. Tests: `tests/channel/test_repair_round5_channel.py`.

**Close round 2** (`docs/ARGUMENT_DIAGNOSTICS.md`, sections 3.5, 7 and 13; DIFF-05). A synthesis carries no subject finding
about a report's paragraphs or sentence style as INT-HIST-001 (`bus._LAYOUT_PREFIXES`: ES-STR-, ES-STY-, HI-STR-;
`_carried(..., layout=False)` in `_synthesis_history`): it restates the claims it cites, not the report's paragraphs, and
such findings, false on many correct literary and historical answers in both trees, read as warnings on syntheses the
committed base keeps clean. The finding stays in the history the synthesis references; a relay of the report names it
again and a router forward carries it, and every other unresolved finding is carried as before. Tests:
`tests/channel/test_close2_synthesis_layout.py`.

**Accuracy round 1** (`docs/ARGUMENT_DIAGNOSTICS.md`, section 17; DV2-05). A forward or relay of a report to a peer
specialist, which builds on the report as material, and a synthesis, which restates the claims it cites, carry as
INT-HIST-001 only the decided findings of the receipts they build on: an error, and a warning that states a fault the
content was found to have (`bus._DECIDED_WARNINGS`: INT-SUBJ-004, a branch check that failed under a reading the report did
not state; INT-ARG-001, a named argument defect; INT-REQ-017, a system check result handed on as content), and a subject
finding that names a STEM defect (`bus._DECIDED_SUBJECT_WARNINGS`: a wrong formula, a missing conversion, a dimension error,
contradictory givens, ...). Every other
warning (a coverage, layout, derived-figure or parse reading) stays listed in the history the receipt references, so a
correct report's heuristic warnings no longer read as findings of the transmissions built on it. A forward or relay to the
combinator, which composes the answer from the report, still carries every unresolved finding. Tests:
`tests/channel/test_accuracy1_relay_history.py`.
