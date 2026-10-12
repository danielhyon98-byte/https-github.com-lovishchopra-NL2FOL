# Dossier guide

## 1. Scope

This document describes the dossier: the one JSON object you receive for one task. It applies to every dossier.

**It covers:**

- the header you copy into your verdict
- the fields of a transfer, a receipt, a result and the links
- the index, which gives you a ready pointer for every identifier
- how to build a JSON Pointer
- lenses and modes
- a translation and its formal problem
- consolidations of the answers several agents gave to one input (informed mode)
- the facts about the system you can rely on
- how the request's constraints are written from the student's words
- answers of the science, mathematics and computer science branches (STEM answers): their claims, translations and formal checks

**It does not cover.** Other documents handle these:

- **Inspection:** what to check in these fields.
- **Evidence rule:** how pointers and quotes are used in an accusation.
- **Verdict format:** the output.

Rules marked **(enforced)** are checked by the infrastructure's code.

## 2. Quick reference

1. You may cite only what is in the dossier. **(enforced)**
2. Copy the header fields into your verdict exactly. **(enforced)**
3. Take pointers from `at` and from `index`; never compute a pointer from `seq`.
4. Arrays count from 0.
5. Quote only from the visible part of a truncated field. **(enforced)**
6. A link tells you where to look. It does not tell you that two things are equal.

## 3. The dossier at a glance

```
{
  "dossier_version": "1.0",
  "dossier_sha256": "<64 hex characters>",          copy into the verdict
  "verdict_contract": "overseer_verdict/1.0",        copy into the verdict as "contract"
  "agent_id": "<your agent id>",                      copy into the verdict
  "issue_binding": "<32 hex characters>",             do not copy: it only makes dossier_sha256 yours
  "pack": {"name": "...", "version": "...", "sha256": "..."},   copy into the verdict
  "mode": "blind" | "informed",
  "lens": "custody_results" | "content_fidelity" | "translation_fidelity" | "peer_synthesis" | "general",   copy into the verdict
  "task": {"task_id": "...", "request_id": "...", "plan": {...}},    copy task_id into the verdict
  "transfers": [ {...}, {...} ],                      every transfer, in the order issued
  "results": { "<result_id>": {...} },                engine results by id
  "links": { "forwards": [...], "peer_documents": [...], "synthesis_citations": [...], "translations": [...] },
  "index": [ {"type": "...", "id": "...", "pointer": "..."} ],
  "auditor": { "findings": [...] },                   informed mode only
  "consolidations": [ {...} ],                         informed mode only, when several agents answered one input
  "limits": { "truncated_fields": [...] }
}
```

## 4. The header

- **D1 One dossier, one task.** **(enforced)** The dossier covers one task. Cite only identifiers, fields and text that it contains.
- **D2 Copy the header.** **(enforced)** These six values go into your verdict unchanged, character for character:

| Dossier field | Verdict field |
| --- | --- |
| `verdict_contract` | `contract` |
| `pack` (the whole object: `name`, `version`, `sha256`) | `pack` |
| `agent_id` | `agent_id` |
| `task.task_id` | `task_id` |
| `dossier_sha256` | `dossier_sha256` |
| `lens` | `lens` |

  `issue_binding` is not copied. It is part of what `dossier_sha256` covers, so the digest you copy is yours alone.
- **D3 The plan.** `task.plan` is the router's plan: the task and subject, `selected_agent_ids` (the agents it chose), `allowed_document_ids` (the documents in scope; empty means unrestricted), `agent_subjects` (each agent's subject) and `agent_task_types` (each agent's task type).

## 5. Lenses

- **D4 Where to start.** Your `lens` tells you where to start:
  - `custody_results`: envelopes, receipts, engine results and formal checks.
  - `content_fidelity`: delivered claims against the response, quotations, figures and dates, and self-certifications.
  - `translation_fidelity`: the translations: each claim, the claims it cites, and the formal problem the translator proposed for it.
  - `peer_synthesis`: router forwards, peer documents, the combinator's ledger, and contradictions between claims.
  - `general`: all of the above.
- **D5 A lens never limits you.** Review every transfer. You may accuse anything you find, whatever your lens.

## 6. Modes

- **D6 Blind and informed.**
  - `blind`: you do not see the infrastructure's own audit findings. The `auditor` field is absent.
  - `informed`: `auditor.findings` lists the infrastructure's findings (codes starting `OVS-`). Do not accuse those again. Look for what they do not cover.
  - In informed mode, do not repeat the exact comparisons the checks make: payload and forward digests, peer documents word for word, quotations found or not found, figures and dates, word and paragraph counts, the status rule, and the translation checks (Inspection I71 to I77). When they find a fault, its `OVS-` code is in `auditor.findings`. Spend your review on what no check decides: whether a request says what the student asked (Inspection I13), self-certifications (Inspection I24), whether a translation says what its claim says (Inspection I78), consolidations (Inspection I84 to I87), and whether a synthesized claim keeps who acted and what was meant (Inspection I69).
  - In both modes the receipts' own findings (codes starting `INT-` and branch codes) are part of each transfer and are always shown.

## 7. A transfer

Each entry of `transfers` has these fields:

| Field | Content |
| --- | --- |
| `at` | This transfer's own pointer, for example `/transfers/3`. Build every pointer into this transfer from it. |
| `seq` | The order the transfer was issued in, starting at 1. Not the array position. |
| `kind` | `request`, `response`, `response_text`, `relay_forward`, `relay_report` or `relay_synthesis` (Inspection explains each). |
| `message_id`, `receipt_id` | The transfer's identifiers. |
| `direction` | `router_to_specialist`, `specialist_to_router` or `agent_to_agent`. |
| `sender`, `recipient` | Each has `agent_id` and `role` (`router`, `specialist`, `combinator`, ...). |
| `contract` | The payload's contract, for example `task_request/1.0`, `specialist_report/1.0`, `specialist_report_forward/1.0`, `synthesis/1.0`. |
| `in_reply_to` | The message this one answers, or null. |
| `created_at` | When the transfer's envelope was created (UTC). Order transfers by `seq`, never by this time. |
| `payload_sha256` | The digest of the payload as issued. Two transfers that carry the same payload have the same digest. |
| `payload` | The typed payload: a request, a specialist report, a forwarded report or a synthesis. For a withheld response it is `{"withheld": {"response_sha256", "response_chars"}}`: the text was refused and not parsed. |
| `raw_text` | For `response_text` only: the specialist's text exactly as received, when retained. |
| `receipt` | `status`, `findings`, `coverage`, `constraint_results`, `outcomes`, `structural_findings`, `formal_checks`, `formal_result_ids`, `summary`. |
| `cited_result_ids` | Every result id the receipt cites. |
| `pool_after` | The formalized claims pooled after this transfer: `claim_id`, `report_id`, `agent_id`, `problem_digest`, `ambiguous`. |

**The payloads you will meet.**

- A **request** (`task_request/1.0`): `to_agent_id`, `subject`, `task_type`, `user_input` (the student's words), `items` (what must be answered), `constraints` (limits such as word counts, each with `constraint_id`, `kind`, `value`, `text`), `supplied_texts` (documents, each with `document_id` and `text`).
- A **specialist report** (`specialist_report/1.0`, and `specialist_report_forward/1.0` when the router forwards one): `report_id`, `agent_id`, `original_response` (the specialist's text as received), `supplied_texts`, and `claims`. Each claim has `claim_id`, `claim_text`, `claim_role`, `materiality` (`material` or `supporting`), `certainty`, `source_refs` (each with `document_id`, `locator`, `excerpt`), and the self-report fields `advisory_verification_status` and `advisory_verification_eligibility`.
- A **synthesis** (`synthesis/1.0`): `synthesis_id`, `combinator_agent_id`, `source_report_ids`, `claims` (synthesized claims with `claim_id`, `text`, `certainty`, `materiality`, `source_claim_ids`, `transformation`, `formal_conclusion`), `ledger` (what happened to each source claim: `source_claim_ids`, `transformation`, `synthesized_claim_id`, `reason`), `conflicts` (contradictions the combinator named: `conflict_id`, `claim_ids`, `description`, `status`) and `text`.

**A receipt.**

- `status`: ACCEPTED, ACCEPTED_WITH_FINDINGS or REJECTED.
- `findings`: each has `code`, `severity` (`error`, `warning` or `info`), `message`, and the identifiers it names (`claim_ids`, `message_ids`, `report_ids`, `agent_ids`, `document_ids`, `formal_result_id`).
- `outcomes`: one per checked claim: `claim_id`, `translation` (what the translator proposed for the claim, with its `status`, `claim_id`, `claim_text_sha256` and `problem`; see §11), `verification` (the engine result as carried on the receipt, with its `result_id` and `status`), `display_status` (the status shown to the router) and `summary` (one plain statement of what was checked for that claim).
- `constraint_results` and `formal_checks`: each has `constraint_id`, `satisfied` (true, false or null), `method`, `detail`, `formal_result_id` and `formal_status`.
- `coverage`: each request item, whether it was `addressed`, and by which claim ids.
- `structural_findings`: findings of the subject branch's own deterministic checks.
- `summary`: one plain sentence of what happened. Every receipt except a request receipt ends with the sentence "Formal results concern only the encoded checks under their premises; coverage is heuristic."

## 8. Results, links, index, auditor, limits

- **D7 Results.** `results` maps each `result_id` to: `status`, `claim_id`, `request_id`, `problem_id`, `query`, `binding` (`problem_digest`, `config_digest`, `versions_digest`, `binding_digest`), `solver_config`, `premises_relied_on`, `ungrounded_dependencies`, `signature_present`, `signature_key_id`, and `problem` when retained. A result id cited on a receipt but missing from `results` is worth checking (Inspection I8).
- **D8 Links.** `links` helps you find related transfers:
  - `forwards`: each router forward with the `report_id` it carries and the `message_id` of the transfer that delivered that report.
  - `peer_documents`: each `peer:<task>` document in a request, with the earlier forwards to the same recipient.
  - `synthesis_citations`: each synthesis with the reports it cites and the transfers that delivered them.
  - `translations`: each translation the router received, with its `claim_id`, `report_id` and `message_id`, the `claim_pointer` of the claim it translates, the `cited_claim_pointers` of the claims that claim cites (what the translator was given with it), the `translation_pointer`, and the `result_id` of its engine result (null when the engine did not run).
  
  A link says where to look. It does not say that the two are equal, or that a translation is faithful. Compare them yourself.
- **D9 Index.** `index` lists every identifier in the dossier with a ready pointer. Each entry has `type` (`message`, `receipt`, `report`, `claim`, `synthesized_claim`, `result`, `document`, `conflict`), `id`, and `pointer`; a claim entry also has `report_id`, because two reports may use the same claim id. Use the index to find an identifier and to build pointers. Never guess an array position.
- **D10 Auditor.** In informed mode, `auditor.findings` holds the infrastructure's `OVS-*` findings. They are already decided. You may mention one in a statement; do not accuse it again.
- **D11 Limits.** String fields longer than 20,000 characters are shortened. `limits.truncated_fields` lists each shortened field's pointer, the digest of the full text and its length. **(enforced)** Quote only from the visible part.

## 9. Building a pointer

- **D12 JSON Pointer.** A pointer is a path into the dossier, starting with `/`, one step per key or array position. Arrays count from 0.
  - Start from a transfer's `at`, or from an `index` pointer.
  - Add the keys down to the field: `/transfers/3` + `/payload/claims/2/claim_text` gives `/transfers/3/payload/claims/2/claim_text`.
  - A result: `/results/<result_id>/status`.
  - If a key contains `/`, write it as `~1`; if it contains `~`, write it as `~0`.
- **D13 Never from seq.** `seq` starts at 1 and may skip; array positions start at 0. Never build `/transfers/N` from a `seq`. Use `at`.

## 10. Facts you can rely on

- **D14 Statuses.** A receipt status is ACCEPTED, ACCEPTED_WITH_FINDINGS or REJECTED. A REJECTED transfer was **not delivered**: nothing in it reached the recipient, the pool or any record.
- **D15 The response.** A report's `original_response` is the specialist's text as received. Every delivered claim should be carried by that text.
- **D16 Engine statuses.** Only six statuses are definitive: ENTAILED, COUNTEREXAMPLE, INCONSISTENT_PREMISES, CONSISTENT, SATISFIABLE and UNSATISFIABLE. None of them means a claim is true: each is a property of the encoded problem. Every other status (UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION, AMBIGUOUS_TRANSLATION, NOT_ELIGIBLE, INTERNAL_ERROR) is a non-result. COUNTEREXAMPLE on an entailment query means the encoded premises do not imply the encoded conclusion. It never means the claim is false, refuted or wrongly translated.
- **D17 Notes, not content.** A claim with `claim_role` `other` is a note (a label, a self-report, a task note), not content.
- **D18 Peer documents.** A supplied text named `peer:<task>` is a forwarded report's `original_response`, supplied to another specialist.
- **D19 Signatures.** You cannot verify signatures. You see only `signature_present` and `signature_key_id` (Role and trust T7).
- **D20 Claim ids.** A claim id is unique inside one report, never across reports. Each parser numbers the claims of an answer by paragraph and statement: the History parser `h1.6`, the generic parser `g4.2` (which some versions qualify with the agent: `g4.2@economics-specialist`), and the science, mathematics and computer science parsers `s1.2`, `m1.2` and `c1.2`. Two agents of one branch number their answers the same way, so one id names a claim in each of their reports: always name the `report_id` with a claim id, and the `message_id` of its transfer. A claim whose id ends in tail (g.tail, h.tail, s.tail, m.tail or c.tail) holds the statements beyond the report's claim limit (INT-REQ-013).

## 11. Translations

- **D21 A translation.** Each outcome's `translation` is what the translator proposed for one claim:
  - `status`: TRANSLATED, AMBIGUOUS_TRANSLATION, NOT_ELIGIBLE, UNSUPPORTED, INVALID_FORMALIZATION or TRANSLATION_FAILED. Only TRANSLATED and AMBIGUOUS_TRANSLATION carry a `problem`, and only those are run by the engine.
  - `eligibility`: the infrastructure's policy decision about the claim: `eligibility_class`, `eligible` and `reasons`. A claim the policy rules out is never sent to the translator.
  - `problem`: the formal problem (D22).
  - `interpretation`: the translator's `reading` of the claim, its `glossary`, and its `ambiguity_flags`, each with `code`, `message` and `alternatives`: the readings it saw.
  - `grounding_checks`: the code's checks of quotations: `target_id`, `document_id`, `method`, `verified` (true, false or null) and `detail`.
  - `provider`: present, with its `provider_name`, when a model proposed the translation; absent when the policy ruled the claim out before any model was asked (NOT_ELIGIBLE). A problem with no `provider` is reported by the checks (OVS-TRN-002), unless the operator declared its translator hand-built.
  - `diagnostics`: why an earlier attempt failed, or why the status is not TRANSLATED.
- **D22 The formal problem.** A `problem` has:
  - `symbols`: each with `name`, `sort` (Bool, Int or Real), `meaning` (in words) and `grounding`;
  - `premises`: each with `id`, `expr`, `label` (the premise in words) and `grounding`;
  - `conclusion`: the same fields: the claim, encoded;
  - `query`: `entailment` asks whether the premises imply the conclusion; `consistency` whether the premises can all hold together; `satisfiability` whether some assignment makes every premise true (a STEM branch asks it of a Boolean identity's negation, D31).
  
  An `expr` is a tree of nodes, each with an `op`: `var` (a symbol, by `name`); the constants `bool`, `int` and `real` (in `value`); `not`; `and` and `or` (with `args`); `implies` and `iff` (with `left` and `right`); the arithmetic `add`, `sub`, `mul`, `neg`, `div`, `idiv` and `mod`; and the comparisons, each with `left` and `right`: `eq` (equal), `ne` (not equal), `lt` (less than), `le` (at most), `gt` (more than) and `ge` (at least).
  
  A `grounding` says where a symbol or assertion comes from: its `kind` (`quotation`, `supplied_text`, `task_setting`, `rubric_rule`, `arithmetic_fact`, `specialist_inference`, `assumption`, `knowledge_document`, `library_source` or `general_knowledge`), its `source_refs` (each with `document_id` and `excerpt`), its `certainty`, and `verified`, which only code sets: true when the excerpt was found in the named document, false when it was not, null when nothing could be checked.
- **D23 What a result says about a translation.** ENTAILED means the premises, as encoded, imply the conclusion, as encoded. It never means that the encoding says what the claim says, nor that the claim is true. COUNTEREXAMPLE means the premises, as encoded, do not imply the conclusion, as encoded. Often a part of the claim has no support in the report, and the translator left it without a premise to show that (a missing link, Inspection I81). It never means that the claim is false or refuted, nor that the translation is wrong. An AMBIGUOUS_TRANSLATION is displayed as AMBIGUOUS_TRANSLATION whatever the engine found.

## 12. Consolidations

- **D24 When there are consolidations.** `consolidations` appears only in informed mode, and only when several agents answered one input (Role and trust T14). Each entry is the infrastructure's signed consolidated response for one input. Its own pointer is `at` (for example `/consolidations/0`). Build every pointer into it from `at`. It copies no agent text: it names transfers by `message_id` and points at them with `transfer_pointer`.
- **D25 A consolidation.** Each entry has:
  - `consolidation_id`, and `signature_present`;
  - `status`: CONSOLIDATED (one group, a clean representative, nothing excluded), CONSOLIDATED_WITH_FINDINGS (one group, with something excluded, repeated or not clean), CONFLICTING (two or more groups, or a conflict: no answer is chosen) or NO_DELIVERABLE_OUTPUT (every answer excluded);
  - `user_input_sha256` (the input) and `request_message_ids` (the requests that carried it);
  - `deliverable_message_id`: the one answer the router may deliver, or null; it is null unless the status is CONSOLIDATED or CONSOLIDATED_WITH_FINDINGS;
  - `groups`, `excluded`, `repeats`, `conflicts` and `advisory` (D26, D27).
- **D26 Groups.** A group holds answers the infrastructure found to be the same. It has `group_id`, `basis`, `members`, `canonical_message_id`, `canonical_clean` and `merge_check`.
  - `basis` is `single` (one answer), `identical_text` (the same `original_response`, apart from the typographic differences of Inspection I9) or `same_material_claims` (other wording, but the same material claims with the same figures, dates and quotations, and a `merge_check` whose `relation` is `consistent`: the engine found their encodings consistent with each other).
  - Each of the `members` has `message_id`, `agent_id`, `transfer_pointer` (the pointer of its transfer), `clean` (true when its receipt is ACCEPTED and nothing names it) and `finding_codes`.
  - `canonical_message_id` is the representative: the earliest clean member. When no member is clean, it is the earliest member, and `canonical_clean` is false.
- **D27 Excluded answers, repeats, conflicts and advisory notes.**
  - `excluded`: each answer kept out of every group, with `message_id`, `agent_id`, `transfer_pointer`, `codes` (the error codes that exclude it), `result_ids` (the signed results those findings cite), `repeated` and `reasons`.
  - `repeats`: each repeated fault: its `code`, the answer that repeats it (`message_id`, `agent_id`, `transfer_pointer`), the earlier answer it repeats (`first_message_id`, `first_agent_id`, `first_transfer_pointer`), `occurrence` (2 for the first repeat) and `same_agent` (true when the same agent resubmitted it). A repeated fault is the same kind of fault, about the same quoted words or the same claim words, with the same figures, as in an earlier answer of the task. `repeats` lists only error-level faults: an error finding on an answer's receipt, or an error-level `OVS-FID` or `OVS-TRN` finding naming the answer. A warning that recurs across answers (a paragraph count, a structure warning) is never listed.
  - `conflicts`: groups that cannot be reduced to one answer: `group_ids`, `excluded_message_id` (an excluded answer that contradicts a group), `relation` (`contradiction`, `consistent`, `undecided` or `not_checked`) and `check` (the engine run behind the relation).
  - `advisory`: answers that look the same that the engine could not confirm. They stay in separate groups and are never merged.

## 13. The request's constraints

- **D28 How constraints are written.** The infrastructure writes each request's `constraints` from the student's words by fixed rules. The constraint's `text` keeps the student's words; its `kind` and `value` follow these rules:
  - "about", "around", "approximately" or "in" N words: `max_words` N plus 10 per cent, rounded down ("about 250 words" gives 275). The student's number is a target, so the bound has a margin.
  - "no more than", "at most", "maximum of", "up to", "under" or "within" N words: `max_words` N.
  - "at least" or "minimum of" N words: `min_words` N.
  - "exactly" N words: `min_words` N and `max_words` N. "Between" A and B words: `min_words` A and `max_words` B.
  - "no more than" or "at most" N paragraphs: `max_paragraphs` N. "At least" N paragraphs: `min_paragraphs` N. "In", "write", "give" or "exactly" N paragraphs ("one paragraph", "a single paragraph"): `min_paragraphs` N and `max_paragraphs` N.
  - "quote", "quotations", "cite" or "textual evidence": `must_cite_supplied_text`.
  A value these rules give from the constraint's own `text` is not a miscommunication (Inspection I13).

## 14. STEM answers

- **D29 A STEM answer.** An answer routed to a science, mathematics or computer science specialist is read statement by statement. Each claim is one statement exactly as the answer writes it, never rewritten: a sentence, a line of working, a row of displayed mathematics, a list item, a code block, a table or a data line. A statement of mathematics may hold no words at all ("√8 = 2√2"). Its `claim_role` says what the statement does:
  - a heading with nothing of its own ("Given:", "Working:"): `structural`;
  - a given value, a law or formula, a table or a data line: `evidence`;
  - a substitution, a calculation or an algebra step: `quantitative`; the last step of each part, its result, is `material`;
  - a code block: a `material` `point`;
  - a sentence of explanation: `point`, `link` or `analysis`;
  - a note or a self-certification: `other` (D17).
- **D30 A STEM translation.** For these subjects the translator follows fixed rules:
  - every number is written exactly, with no exponent: 6.67 × 10⁻¹¹ becomes 0.0000000000667 and 3.0 × 10⁸ becomes 300000000;
  - the values the answer states are put in place of the symbols they bind, so a line of working becomes arithmetic on numbers;
  - each quantity has one symbol, named after its claim (g in claim s2.1 is s2_1_g), so the symbols of two claims never meet by accident;
  - a unit is written in words, in the symbol's `meaning` or the premise's `label`, never in an expression: the engine checks numbers, never units;
  - a square root or a trigonometric value is encoded as a comparison of squares, or the translation is UNSUPPORTED.
- **D31 A STEM formal check.** These branches check the answer's own relations themselves, with no model: arithmetic links, substitutions, algebra steps, stated roots, unit conversions, comparisons, results against the given values and the "show that" target, chemical equations, Boolean identities, truth tables and number bases. Each one is an entry of the receipt's `formal_checks`. Its `detail` says what it checks and which status it expects:
  - most say "expected ENTAILED";
  - "expected SATISFIABLE": some admissible reading of the answer's numbers gives the stated value. It never means that the value is true;
  - "expected UNSATISFIABLE": a Boolean identity, checked over its negation: no assignment makes its two sides differ.
  
  `satisfied` is true when the result's status is the one the check expects, false for any other definitive status, and null for a non-result. On a STEM check, INCONSISTENT_PREMISES and a run marked "vacuous: E108" are null too. A failed check is INT-SUBJ-001 (error). A check whose `detail` says "failure severity warning" fails only under a reading the answer did not state (a rounding, a unit), and is INT-SUBJ-004 (warning). An undecided check is INT-SUBJ-002 (warning).

## 15. Common mistakes

| Mistake | Do instead | Rule |
| --- | --- | --- |
| Writing `agent_id` from memory or inventing one | Copy `agent_id` from the dossier | D2 |
| Writing `/transfers/4` for the transfer with seq 4 | Use that transfer's `at` | D13 |
| Counting claims by hand to build a pointer | Take the claim's pointer from `index` | D9 |
| Treating a link as proof two texts are equal | Compare the two texts yourself | D8 |
| Quoting text past a truncation marker | Quote only the visible part | D11 |
| Reading a REJECTED transfer as delivered | Remember it reached no one | D14 |
| Reading ENTAILED as "the translation is faithful" | ENTAILED is about the encoding only; compare the problem with the claim | D23 |
| Treating `canonical_message_id` as the right answer | It represents answers that are the same; it says nothing about truth | D26 |
| Expecting `consolidations` in blind mode | Consolidations are shown in informed mode only | D24 |
| Reading COUNTEREXAMPLE as "the claim is false" or "the translation is wrong" | It says only that the encoded premises do not imply the encoded conclusion | D16, D23 |
| Accusing `max_words` 275 when the student wrote "about 250 words" | That is the rule for "about": the number plus 10 per cent | D28 |
| Expecting a recurring warning in `repeats` | `repeats` lists error-level faults only | D27 |
| Repeating every byte comparison in informed mode | Spend your review on what no check decides | D6 |
| Reading one claim id in two reports as one claim | Name the `report_id` and the `message_id` with it | D20 |
| Looking for units inside a STEM translation's expressions | Units are in `meaning` and `label`; the engine checks numbers only | D30 |
| Reading `satisfied` true with UNSATISFIABLE as wrong | A Boolean identity check expects UNSATISFIABLE | D31 |

Pack version 1.2 · overseer-knowledge-docs · carries brief 1.0 §2 and §3
