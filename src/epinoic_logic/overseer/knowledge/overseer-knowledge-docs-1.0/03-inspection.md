# Inspection

## 1. Scope

This document says what to check on each transfer. It applies to every transfer in every dossier. Walk the transfers in `seq` order. On each one, run the common checks (§3), then the checks for its `kind` (§4 to §9).

**It covers:**

- the three questions you ask of every transfer
- the common checks: status, summary, delivery, digests, identifiers
- the checks for each kind of transfer: `request`, `response`, `response_text`, `relay_forward`, `relay_report`, `relay_synthesis`
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
- **I37 Everything else.** Run I20 to I31 on the parsed report.

## 7. `relay_forward` (router forwards a report to another agent)

The router may pass on a delivered report only exactly as it was delivered.

- **I40 Forward equals delivery.** Find the delivery of the same `report_id` (`links.forwards`). Its `payload_sha256` must equal the forward's `payload_sha256`. If the digests differ, compare `original_response` and `claims` to find what changed.
  - The channel REJECTED the forward with INT-HANDOFF-013: the channel caught it (I3). Do not accuse the forward. Check that nothing from it was used later (I5, I12).
  - The forward is ACCEPTED or ACCEPTED_WITH_FINDINGS although it differs: kind `forward_altered`, `claimed_severity` `error`.
- **I41 Forward of a delivered report.** The forwarded `report_id` must have been delivered earlier (a `response`, `response_text` or `relay_report` with a status that is not REJECTED, with lower `seq`). Not delivered, or delivered REJECTED, and the forward was not REJECTED: kind `forward_altered`.
- **I42 Sender is the router.** `sender.role` is `router` and `contract` is `specialist_report_forward/1.0`.

## 8. `relay_report` (a specialist relays its own report)

- **I45 Owner sends.** `sender.agent_id` must equal `payload.agent_id`: only a report's owner relays it. Otherwise, with no `INT-HANDOFF` or `INT-ENV` error and a status that is not REJECTED: kind `receipt_status_wrong`.
- **I46 Checked like a response.** Run I21 to I31 on it.

## 9. `relay_synthesis` (the combinator's synthesis)

- **I60 Cited reports were delivered first.** Every `source_report_ids[]` must have been delivered (not REJECTED) at a lower `seq` than the synthesis. Otherwise: kind `synthesis_ledger_fault`.
- **I61 Every material claim is accounted for.** Every `material` claim of the cited reports must appear in the `ledger` as carried, transformed (`paraphrased`, `merged`, `narrowed`, `generalized`) or `dropped` with a `reason`. A material claim missing from the ledger, or dropped without a reason, with no INT-LEDGER finding naming it: kind `synthesis_ledger_fault`.
- **I62 Figures and dates survive.** Each figure or date in a synthesized claim must occur in its `source_claim_ids` claims, with the same scale word and paired with the same event. A changed, introduced, rescaled or re-paired figure with no INT-LEDGER-023 finding: kind `figure_changed`.
- **I63 Quotations survive.** A quotation in a synthesized claim must occur in its source claims or the cited documents. Otherwise: kind `quotation_absent` (or `synthesis_ledger_fault` when the ledger misreports it).
- **I64 Certainty is not inflated.** A synthesized claim must not be more certain than its sources: `established` built only from `probable` or `possible` sources, or "certainly" where the sources say "probably". With no finding: kind `synthesis_ledger_fault`.
- **I65 Contradictions are named.** Two claims (from different specialists, or within one report) that cannot both hold under the shared meanings of their terms must be named: in `synthesis.conflicts`, or on a receipt (INT-CONFLICT-001, or INT-CONFLICT-005 for one claim that refutes itself). Unnamed: kind `contradiction_unnamed`. A difference of emphasis, interpretation or judgement is not a contradiction.
- **I66 Named conflicts are real.** A conflict a receipt or the synthesis names between claims that can in fact hold together (for example "built in 1932" and "opened in 1934", which describe different events): kind `false_conflict`.
- **I67 Required checks performed.** A `material` synthesized claim with transformation `merged` or `generalized` needs a `formal_conclusion`. Without one, the receipt should carry INT-SYNTH-006. Neither: kind `finding_missing`.
- **I68 Synthesis text.** The synthesis `text` should say what its `claims` say. A sentence in `text` that states a figure, quotation or verdict that no synthesized claim carries: kind `synthesis_ledger_fault`, `claimed_severity` `warning`.

## 10. Common mistakes

| Mistake | Do instead | Rule |
| --- | --- | --- |
| Accusing a quotation the receipt already flags with INT-REQ-003 | Leave it; the receipt said what happened | I3 |
| Accusing a forward the channel REJECTED with INT-HANDOFF-013 | Leave it; check nothing from it was used later | I40 |
| Calling ACCEPTED_WITH_FINDINGS wrong on a request receipt that has warnings | Request receipts are ACCEPTED with warnings; check for that instead | I2 |
| Accusing curly versus straight quotes | Typographic differences are not faults | I9 |
| Accusing a date because you believe it is historically wrong | Check only that the date was carried intact | I9 |
| Counting words yourself and accusing a difference of three | Accuse a count only when it is clearly impossible | I27 |
| Calling two interpretations a contradiction | A contradiction is two claims that cannot both hold | I65 |

Pack version 1.0 · overseer-knowledge-docs · carries brief 1.0 §4 (the three questions and every "Look for" entry of the kinds table)
