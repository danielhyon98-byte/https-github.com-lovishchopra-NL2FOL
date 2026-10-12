# Inspection

## 1. Scope

This document says what to check on each transfer. It applies to every transfer in every dossier. Walk the transfers in `seq` order. On each one, run the common checks (§3), then the checks for its `kind` (§4 to §9). On a transfer that delivered a report, also check every translation of its claims (§10). In informed mode, when several agents answered one input, also check each consolidation and every repeated fault (§11).

**It covers:**

- the three questions you ask of every transfer
- the common checks: status, summary, delivery, digests, identifiers
- the checks for each kind of transfer: `request`, `response`, `response_text`, `relay_forward`, `relay_report`, `relay_synthesis`
- the checks for every translation of a delivered claim
- the checks for a consolidation of several answers to one input, and for repeated faults
- what is not a fault

**It does not cover.** Other documents handle these:

- **Kinds and codes:** which kind to give a fault you found.
- **Evidence rule:** how to pin it to the dossier.
- **Examples:** worked transfers with their correct verdicts.
- **When unsure:** a fault you cannot pin down.

## 2. Quick reference

1. Ask the three questions of every transfer (I1).
2. A fault the receipt already names is not a miscommunication, if the status follows from it (I3).
3. A REJECTED transfer was not delivered. It must not appear later as forwarded, cited or pooled (I5).
4. A forward must carry the same `payload_sha256` as the delivery of its report (I40).
5. Every delivered claim must be carried by `original_response` (I21).
6. A quotation must occur in the document it cites (I22).
7. A display status is never stronger than its signed result (I26).
8. A synthesis must account for every material claim and name every contradiction (I60 to I66).
9. Typographic differences are not faults (I9).
10. Every translation must say what its claim says, from the claim and the claims it cites; a conclusion found among its own premises proves nothing (I70 to I81).
11. Several answers to one input: check each group, exclusion and conflict of the consolidation, and accuse an unnamed repeated fault on every transfer that carries it (I82 to I89).

## 3. Every transfer

- **I1 The three questions.** Ask them of every transfer:
  1. Did what was asked arrive, and did what was said arrive?
  2. Does the receipt say exactly what happened?
  3. Is every engine result cited for the problem it names?
- **I2 Status follows from the findings.** Check the receipt's `status` against its own contents:
  - **Request receipts:** REJECTED when any finding has severity `error`; otherwise ACCEPTED, even with warnings. A request receipt is never ACCEPTED_WITH_FINDINGS.
  - **All other receipts:**
    1. REJECTED when any finding has severity `error` and a code that starts with one of: `INT-HANDOFF`, `INT-ENV`, `INT-REQ-000`, `INT-REQ-001`, `INT-REQ-002`, `INT-REQ-009`, `INT-LEDGER-000`, `INT-LEDGER-008`.
    2. Otherwise ACCEPTED_WITH_FINDINGS when there is any finding at all, or any structural finding of severity `error` or `warning`, or any outcome whose `verification` is present with a status that is not definitive.
    3. Otherwise ACCEPTED.
  - A status that does not follow: kind `receipt_status_wrong`.
- **I3 A named fault is not a miscommunication.** When the receipt already carries a finding for a fault (for example INT-REQ-003 naming the claim whose quotation is not found) and the status follows from the findings (I2), the receipt said exactly what happened. Do not accuse it. Review the rest of the transfer.
- **I4 The summary matches the fields.** The `summary` must agree with the structured fields:
  - the status word in the summary equals `status`;
  - every code the summary lists under "Findings" is in `findings`, and every code in `findings` is listed;
  - every receipt except a request receipt ends with "Formal results concern only the encoded checks under their premises; coverage is heuristic."
  - A summary that contradicts the fields in a way only an edit explains: kind `receipt_altered`.
- **I5 Not delivered means not used.** A REJECTED transfer was not delivered. Later in the dossier it must not be:
  - forwarded (a `relay_forward` of its `report_id` with an ACCEPTED or ACCEPTED_WITH_FINDINGS status),
  - cited by a synthesis as a delivered report,
  - pooled (its claims in a later `pool_after`).
  - Any of these: kind `receipt_status_wrong`. An accepted report that never appears as delivered when it should is the same kind.
- **I6 Same payload, same digest.** Two transfers that carry the same report or request carry the same `payload_sha256`. When the dossier shows two copies of one transfer's content (a delivery and a forward of one `report_id`, a report and a synthesis quoting its text), compare them. Copies that differ: the kind of the transfer type (I40, I45, I60) or `payload_altered`.
- **I7 Identifiers resolve.** Every identifier a receipt names (in findings, coverage, constraint results, outcomes, formal checks, `formal_result_ids`) should appear somewhere in the dossier. Look it up in `index`. An identifier that resolves nowhere: `receipt_altered` for a claim, report or message id; `result_out_of_task` for a result id.
- **I8 Cited results exist.** Every id in `cited_result_ids` should be a key of `results`. A missing one: kind `result_out_of_task`.
- **I9 Not faults.** These are not miscommunications. Never accuse them:
  - typographic differences between a claim and the response: curly or straight quotes and apostrophes, dash types, extra spaces or line breaks, markdown emphasis (`*`, `_`, `` ` ``), heading hashes and list bullets;
  - a claim that is a shortened tail of the response, where the claim text is the start of what remains;
  - a claim's `certainty` or `proposed_claim_kind` you disagree with;
  - whether a claim, reading, date or figure is true;
  - a status that is a non-result (UNKNOWN, TIMEOUT, NOT_ELIGIBLE and the others), when the receipt shows it as a non-result.

## 4. `request` (router to specialist)

- **I10 The right recipient.** `recipient.agent_id` (and `payload.to_agent_id`) must be in `task.plan.selected_agent_ids`. The request's `subject` and `task_type` should match `plan.agent_subjects` and `plan.agent_task_types` for that agent. A mismatch the receipt does not name: kind `finding_missing`.
- **I11 Documents in scope.** Each `supplied_texts[].document_id` should be in `plan.allowed_document_ids` when that list is not empty. A document out of scope with no finding: kind `finding_missing`.
- **I12 Peer documents.** A supplied text whose `document_id` starts with `peer:` must be byte-identical to the `original_response` of a report that was forwarded **earlier** (lower `seq`) to **the same recipient**. Find the forward in `links.peer_documents` and compare the texts word by word.
  - The text differs, even by one word: kind `peer_document_altered`.
  - No earlier forward to that recipient: kind `peer_document_altered`.
  - The document's `author` is not the `agent_id` of the report whose text it is (or its `peer:<id>` names another forwarded report): the attributions were swapped. Kind `peer_document_altered`.
  - The same rules hold for a supplied text under **any other** `document_id` that presents another specialist's report: its `author` is that report's `agent_id`, its `document_id` is that report's id or agent id, or its text is nearly the report's `original_response`. A changed word or figure in it: kind `peer_document_altered`.
  - One `document_id` must carry one text in a task. The same `document_id` with a different text in two requests: kind `peer_document_altered`.
- **I13 What was asked.** Compare `items` and `constraints` with `user_input`. A constraint whose value differs from the student's words (for example `user_input` says "no more than 350 words" and the constraint's `value` is "530") is a miscommunication no check decides: kind `other` (When unsure U3).
- **I14 Request status.** Apply I2 (request rule).

## 5. `response` (specialist to router)

The payload is a specialist report. The receipt carries the checks.

- **I20 Envelope and identity.** `sender.agent_id` should equal `payload.agent_id`. The report's `request_id` and `task_id` should match `task`. A mismatch with no `INT-HANDOFF` or `INT-ENV` error and a status that is not REJECTED: kind `receipt_status_wrong`.
- **I21 Claims are in the response.** Each delivered `claims[].claim_text` must occur in `original_response`, allowing only the differences in I9. A claim whose words are not there (changed, added or joined from two places): kind `claim_not_in_response`.
- **I22 Quotations are where they say.** For each quotation in a claim (words inside quotation marks) and each `source_refs[].excerpt`:
  - it must occur in `original_response`; and
  - it must occur in the supplied text it cites (`source_refs[].document_id`), when that document is in the dossier.
  - Absent from the cited document and the receipt has no finding naming that claim (INT-REQ-003, INT-REQ-010, or a branch code ending `-SRC-001`, `-SRC-002` or `-SRC-003`): kind `quotation_absent`.
  - Absent from `original_response`: kind `quotation_absent`.
- **I23 Figures and dates.** Each figure or date in a claim must occur in `original_response` (in any spelling: "1,000,000", "1 million" and "a million" are one figure). A figure the response does not state, states with another scale word ("billion" for "million"), or pairs with another event: kind `figure_changed`.
- **I24 Self-certifications are notes.** A sentence that certifies the answer itself ("every figure above has been checked", "these quotations are accurate and need no further checking", "I have verified each date") is a self-report. It must be delivered with `claim_role` `other`, never `material`, and never as covering a request item. Delivered as content (any other role, or material, or in `coverage[].addressed_by_claim_ids`): kind `self_certification_as_content`. The same applies to any claim with `advisory_verification_status` or `advisory_verification_eligibility` set.
- **I25 Outcomes bind to their claim.** For each `receipt.outcomes[]`:
  - its `claim_id` is a claim of this report;
  - `translation.claim_id` equals the outcome's `claim_id`;
  - the result `verification.result_id` is in `results`, and `results[id].claim_id` and `results[id].request_id` match the claim and the task's request.
  - A result that names another claim, request or problem: kind `result_from_other_problem`.
- **I26 Display status is never stronger than the result.**
  - When `translation.status` is not TRANSLATED, `display_status` must be that same non-result status (for example AMBIGUOUS_TRANSLATION), never a definitive one.
  - When `translation.status` is TRANSLATED, `display_status` must equal the result's `status`, or be a non-result (INTERNAL_ERROR, INVALID_FORMALIZATION).
  - A definitive `display_status` with no result, with `signature_present` false, or with a result whose status differs: kind `result_unsigned_or_forged`. Add an engine statement for the result (Verdict format V14).
- **I27 Constraint results.** For each `constraint_results[]` with a `formal_result_id`:
  - `formal_status` equals `results[formal_result_id].status`;
  - `satisfied` is true for ENTAILED, false for COUNTEREXAMPLE, and null for every other status.
  - Otherwise: kind `formal_status_wrong`, with an engine statement.
  - Word and paragraph counts: different counters treat numbers, hyphens and dashes differently, so a small difference is not evidence. Accuse a measured count only when the result's `problem` states a value that is clearly impossible for the text (for example 120 words for a response of several long paragraphs): kind `formal_status_wrong`, `claimed_severity` `warning`.
- **I28 The report's own formal checks.** For each `formal_checks[]`: `formal_status` equals the result's status; `satisfied` is false for COUNTEREXAMPLE, INCONSISTENT_PREMISES and UNSATISFIABLE, and null for every non-result. A check marked satisfied while its result is COUNTEREXAMPLE: kind `formal_status_wrong`.
- **I29 Coverage names real claims.** Every id in `coverage[].addressed_by_claim_ids` is a claim of this report (I7).
- **I30 Pool after.** After an accepted response, `pool_after` may gain this report's claims; after a REJECTED one it must not (I5).
- **I31 Supplied texts carried over.** A supplied text in the report under a `document_id` the request supplied must be identical to the request's text. A changed one: kind `peer_document_altered`.

## 6. `response_text` (raw text from a specialist)

The hub received the specialist's text and the channel parsed it into a report.

- **I35 Raw text is the response.** When the transfer is delivered, `raw_text` must equal `payload.original_response`. A difference: kind `payload_altered`.
- **I36 Withheld text.** When the payload is `{"withheld": {...}}`, the text was refused and not parsed. The status must be REJECTED. Nothing from it may be delivered, forwarded, cited or pooled later (I5).
- **I37 Everything else.** Run I20 to I31 on the parsed report, then §10 on its translations.

## 7. `relay_forward` (router forwards a report to another agent)

The router may pass on a delivered report only exactly as it was delivered.

- **I40 Forward equals delivery.** Find the delivery of the same `report_id` (`links.forwards`). Its `payload_sha256` must equal the forward's `payload_sha256`. If the digests differ, compare `original_response` and `claims` to find what changed.
  - The channel REJECTED the forward with INT-HANDOFF-013: the channel caught it (I3). Do not accuse the forward. Check that nothing from it was used later (I5, I12).
  - The forward is ACCEPTED or ACCEPTED_WITH_FINDINGS although it differs: kind `forward_altered`, `claimed_severity` `error`.
- **I41 Forward of a delivered report.** The forwarded `report_id` must have been delivered earlier (a `response`, `response_text` or `relay_report` with a status that is not REJECTED, with lower `seq`). Not delivered, or delivered REJECTED, and the forward was not REJECTED: kind `forward_altered`.
- **I42 Sender is the router.** `sender.role` is `router` and `contract` is `specialist_report_forward/1.0`.

## 8. `relay_report` (a specialist relays its own report)

- **I45 Owner sends.** `sender.agent_id` must equal `payload.agent_id`: only a report's owner relays it. Otherwise, with no `INT-HANDOFF` or `INT-ENV` error and a status that is not REJECTED: kind `receipt_status_wrong`.
- **I46 Checked like a response.** Run I21 to I31 on it, then §10 on its translations.
- **I47 Delivered before.** The same agent must have delivered this report earlier: a `response` or `response_text` with the same `report_id`, the same content (the same `payload_sha256`, or a payload that differs only in its `created_at`) and the same `sender.agent_id`, with lower `seq`. A report relayed in an agent's name that the agent never delivered (a new `report_id`, or changed content) was written by someone else: kind `forward_altered`, `claimed_severity` `error`.

## 9. `relay_synthesis` (the combinator's synthesis)

- **I60 Cited reports were delivered first.** Every `source_report_ids[]` must have been delivered (not REJECTED) at a lower `seq` than the synthesis. Otherwise: kind `synthesis_ledger_fault`.
- **I61 Every material claim is accounted for.** Every `material` claim of the cited reports must appear in the `ledger` as carried, transformed (`paraphrased`, `merged`, `narrowed`, `generalized`) or `dropped` with a `reason`. A material claim missing from the ledger, or dropped without a reason, with no INT-LEDGER finding naming it: kind `synthesis_ledger_fault`.
- **I62 Figures and dates survive.** Each figure or date in a synthesized claim must occur in its `source_claim_ids` claims, with the same scale word and paired with the same event. A changed, introduced, rescaled or re-paired figure with no INT-LEDGER-023 finding: kind `figure_changed`.
- **I63 Quotations survive.** A quotation in a synthesized claim must occur in its source claims or the cited documents. Otherwise: kind `quotation_absent` (or `synthesis_ledger_fault` when the ledger misreports it).
- **I64 Certainty is not inflated.** A synthesized claim must not be more certain than its sources: `established` built only from `probable` or `possible` sources, or "certainly" where the sources say "probably". With no finding: kind `synthesis_ledger_fault`.
- **I65 Contradictions are named.** Two claims (from different specialists, or within one report) that cannot both hold under the shared meanings of their terms must be named: in `synthesis.conflicts`, or on a receipt (INT-CONFLICT-001, or INT-CONFLICT-005 for one claim that refutes itself). Unnamed: kind `contradiction_unnamed`. A difference of emphasis, interpretation or judgement is not a contradiction.
- **I66 Named conflicts are real.** A conflict a receipt or the synthesis names between claims that can in fact hold together (for example "built in 1932" and "opened in 1934", which describe different events): kind `false_conflict`.
- **I67 Required checks performed.** A `material` synthesized claim with transformation `merged` or `generalized` needs a `formal_conclusion`. Without one, the receipt must say the check was NOT performed: INT-LEDGER-011 saying "NOT performed", INT-SYNTH-012 or INT-SYNTH-006 naming the claim. None of these: kind `finding_missing`.
- **I68 Synthesis text.** The synthesis `text` should say what its `claims` say. A figure or date in `text` that no synthesized claim states (in any spelling: "1834" where the claims say "1833", "under ten" where they say "under nine"): kind `figure_changed`, `claimed_severity` `error` (the receipt must carry INT-LEDGER-023). A quotation or verdict in `text` that no synthesized claim carries: kind `synthesis_ledger_fault`, `claimed_severity` `warning`.
- **I69 Meaning is kept.** A `carried` or `paraphrased` synthesized claim with one source must not turn the source's comparison the other way ("children under nine" becomes "children over nine"; "before 1847" becomes "after 1847") or negate what the source states ("banned" becomes "did not ban"). With no INT-LEDGER-027 finding: kind `synthesis_ledger_fault`. A negation that rewords a ban without changing it ("banned employing children" becomes "children could not be employed") is not this fault.

## 10. Translations (every outcome of a `response`, `response_text` or `relay_report`)

The translator turned each eligible claim into a formal problem, and the engine decided the problem. Check that each translation says what its claim says. Choose the kind and the severity by Kinds and codes K6.

- **I70 Find each translation.** `links.translations` lists each translation the router received. For each one read, in this order: the claim (`claim_pointer`), the claims it cites (`cited_claim_pointers`), then the translation (`translation_pointer`). The translator was given only these claims and the supplied texts. A REJECTED transfer delivered no translation: skip it (Dossier guide D14).
- **I71 Status and problem agree.** A `status` of TRANSLATED or AMBIGUOUS_TRANSLATION must carry a `problem`; every other status must not. A `verification` belongs only to a translation that carries a `problem`. Otherwise: kind `translation_invalid`.
- **I72 Eligibility agrees.** When `eligibility.eligible` is false, the `status` must be NOT_ELIGIBLE and there must be no `problem`. When it is true, the `status` must not be NOT_ELIGIBLE. Otherwise: kind `translation_invalid`.
- **I73 Ambiguity is never resolved silently.** When `interpretation.ambiguity_flags` lists any flag, the `status` must be AMBIGUOUS_TRANSLATION. A flagged translation with `status` TRANSLATED: kind `translation_invalid`.
- **I74 The problem is well formed.** `problem.claim_id` equals the outcome's `claim_id`, and every `var` names a symbol listed in `symbols`. Otherwise: kind `translation_invalid`.
- **I75 Quotations are in their documents.** Every `source_refs[].excerpt` in the `grounding` of a symbol or an assertion must occur in the supplied text its `document_id` names, allowing only the differences in I9. An excerpt that document does not contain: kind `translation_ungrounded`. When its `verified` is false, the translation already disclosed it: use `claimed_severity` `warning`. When its `verified` is true, it was overstated: use `error`.
- **I76 Nothing is invented.** Every quotation in the problem must occur in the report (in `original_response`, a claim or a source excerpt) or word for word in a supplied text. Every number in the problem must be stated in the report, in any spelling: "forty" is 40, "two-thirds" is 2/3, "a tenth" may be written 1/10 or 10 per cent, "March" is 3, and a date may be written as one number such as 19020531 for 31 May 1902. The numbers 0 and 1 need no source. A premise grounded `task_setting` may take its number from the request. A quotation or number stated nowhere: kind `translation_ungrounded`.
- **I77 The conclusion is not assumed.** Compare the conclusion's `expr` with each premise's `expr`. When the conclusion's `expr` appears exactly (the same JSON) as a premise's `expr`, or as one of the `args` of a premise whose `op` is `and`, the problem assumes what it should show, and ENTAILED then proves nothing about the specialist's reasoning: kind `translation_circular`. A premise that only means the same in another form (two `not` around it, `gt` written as a reversed `lt`) is not exact: use I78.
- **I78 The problem says what the claim says.** This is the meaning check. Compare the conclusion (its `label` and its `expr`) with the claim, and the premises with the claims it cites. Look for:
  1. **A dropped condition.** The claim says "only if", "unless", "when", "some" or "most", or limits a time or a place, and the problem drops it.
  2. **A flipped comparison or direction.** "More than" encoded with `lt`; "at least" (`ge`) encoded as "more than" (`gt`); "before" encoded as after; "A led to B" encoded as B `implies` A.
  3. **An invented premise.** A premise that neither the claim nor a claim it cites states, and that the conclusion needs, often grounded `assumption`, `general_knowledge` or `specialist_inference`.
  4. **An ambiguity resolved silently.** The claim can be read two ways, the problem encodes one, and `ambiguity_flags` is empty.
  5. **A claim forced into a problem.** The claim is a reading, a value judgement or a judgement against a rubric, or it needs what a problem cannot say (possibility, degree, change over time), and the problem presents it as a fact to prove. It should have been left UNSUPPORTED or NOT_ELIGIBLE.
  6. **A conclusion that is not the claim.** The conclusion's `label` or `expr` says something narrower, broader, or about another subject than the claim.
  
  Any of these: kind `translation_unfaithful`. Give one pointer, with a quote, to the claim's words, and one pointer, with a quote, to the part of the problem that differs. No check compares meanings, so the accusation goes to human review.
- **I79 The outcome around the translation.** Apply I25 and I26 to the outcome. Its `summary` must not state more than its translation and its result: a summary that calls the claim proven, true or verified, or names another status than `display_status`: kind `receipt_altered`.
- **I80 What a result shows.** A result's status is about the encoding (Dossier guide D23). Never accuse a translation because of its result's status alone, and never treat ENTAILED as a sign that the translation is faithful.
- **I81 Not faults in a translation.** Never accuse:
  - symbol names, premise ids or labels worded differently from the claim, when the meaning is the same;
  - an encoding other than the one you would write that says the same thing;
  - a premise that restates a claim the claim cites;
  - a quotation that widens the specialist's quoted words to the full phrase of the same supplied text;
  - a NOT_ELIGIBLE, UNSUPPORTED, INVALID_FORMALIZATION or TRANSLATION_FAILED translation without a problem, shown as that non-result;
  - whether the claim itself is true (Never N6).

## 11. Consolidations and repeated faults

These checks apply in informed mode, when the dossier has `consolidations` (Dossier guide D24). The infrastructure made each consolidation by fixed rules; you check that it agrees with the transfers it names. A consolidation fault is decided by no check: use kind `other` with `claimed_severity` `warning` (Kinds and codes K7).

- **I82 Find each consolidation.** For each entry of `consolidations`, read `request_message_ids`, then the `groups`, the `excluded` answers, the `repeats` and the `conflicts`. Open every transfer they name at its `transfer_pointer`.
- **I83 Every answer is accounted for.** Every `response` or `response_text` whose `in_reply_to` is one of `request_message_ids` must be a member of exactly one group or be listed in `excluded`. An answer missing from both, or listed twice: kind `other`, naming its `message_id`, with one pointer to the consolidation's `at` and one to the answer's transfer.
- **I84 Members say the same thing.** In a group with `basis` `identical_text`, the members' `original_response` are the same text, apart from the differences in I9. In a group with `basis` `same_material_claims`, compare each member's material claims (`materiality` `material`, `claim_role` not `other`) with the representative's: the same claims, the same figures and dates, the same quoted words, the same "not". A member whose material claim differs in a figure, a date, a quotation, a negation or a name: kind `other`, with one pointer and quote for each of the two claims (When unsure U11).
- **I85 The representative.** `canonical_message_id` must be a member of its group. When `canonical_clean` is true, that member's `clean` is true and its transfer's receipt `status` is ACCEPTED. An earlier member whose `clean` is true should have been chosen instead. Otherwise: kind `other`.
- **I86 Faulty answers are never members.** An answer whose receipt carries a finding of severity `error`, or that `repeats` lists, must be in `excluded`, never in a group, and never be `deliverable_message_id`. A faulty answer in a group: kind `other`, naming the answer, with a pointer to its error finding and one to the group.
- **I87 Conflicts are disclosed, never chosen.** With two or more groups, or any entry in `conflicts`, the `status` must be CONFLICTING and `deliverable_message_id` must be null: the router discloses the groups instead of choosing one. CONSOLIDATED or CONSOLIDATED_WITH_FINDINGS with two groups or a conflict: kind `other`. Never decide yourself which group is right (Never N13).
- **I88 Repeated faults.** A repeated fault is the same fault in a later answer of the task: the same kind of finding, about the same quoted words or the same claim words, with the same figures, from another agent, another instance of the same specialist, or the same agent resubmitting after a rejection, even reworded.
  - When the receipts name the fault and `repeats` lists the repeat, it is already recorded: do not accuse it (I3).
  - When you find the same fault in several transfers and no receipt names it (for example a self-certification delivered as content, or a figure the response does not state), accuse it on every transfer that carries it: one accusation per transfer, the same kind, each with that transfer's own identifiers and evidence. Say in `statement` which earlier transfer it repeats (Examples, Example 19).
  - Never accuse a fault only because it repeats: each accusation is about one transfer.
- **I89 Not faults in a consolidation.** Never accuse:
  - answers worded differently that a group merged with `basis` `same_material_claims` and a `merge_check` whose `relation` is `consistent`;
  - answers kept in two groups with an `advisory` note: the infrastructure does not merge what the engine could not confirm;
  - a group with one member, or the number of agents in a group: agreement is never evidence;
  - which group is true, better or more complete (Never N6, N13).

## 12. Common mistakes

| Mistake | Do instead | Rule |
| --- | --- | --- |
| Accusing a quotation the receipt already flags with INT-REQ-003 | Leave it; the receipt said what happened | I3 |
| Accusing a forward the channel REJECTED with INT-HANDOFF-013 | Leave it; check nothing from it was used later | I40 |
| Calling ACCEPTED_WITH_FINDINGS wrong on a request receipt that has warnings | Request receipts are ACCEPTED with warnings; check for that instead | I2 |
| Accusing curly versus straight quotes | Typographic differences are not faults | I9 |
| Accusing a date because you believe it is historically wrong | Check only that the date was carried intact | I9 |
| Counting words yourself and accusing a difference of three | Accuse a count only when it is clearly impossible | I27 |
| Calling two interpretations a contradiction | A contradiction is two claims that cannot both hold | I65 |
| Accusing a translation because its result is COUNTEREXAMPLE | The status is about the encoding; compare the problem with the claim | I80 |
| `translation_circular` for a premise that means the same in another form | Use `translation_unfaithful` | I77 |
| `translation_ungrounded` for words the specialist wrote in its own response | They are stated in the report; check only the document they cite | I76 |
| `other` for a flipped comparison in a translation | Use `translation_unfaithful` | I78 |
| Accusing a repeated quotation fault the receipts already name | Leave it; `repeats` records it | I88 |
| One accusation for a fault found in three answers | One accusation per transfer that carries it | I88 |
| Accusing the group fewer agents gave | Agreement is never evidence; check only that the conflict is disclosed | I87 |

Pack version 1.0 · overseer-knowledge-docs · carries brief 1.0 §4 (the three questions and every "Look for" entry of the kinds table)
