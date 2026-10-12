# Evidence rule

## 1. Scope

This document says how every accusation and every engine statement is pinned to the dossier. It applies to every accusation you make.

**It covers:**

- the identifiers an accusation must name
- evidence items: pointers and quotes
- how to show an absence
- engine statements
- what makes an accusation unverifiable

**It does not cover.** Other documents handle these:

- **Dossier guide:** how to build a pointer (D12, D13) and the index (D9).
- **Verdict format:** where these fields go in the JSON.
- **Kinds and codes:** which kind to choose.

Rules marked **(enforced)** are checked by the infrastructure's code. An accusation that breaks one is recorded as unverifiable (OVS-AGENT-002) against you.

## 2. Quick reference

1. At least one identifier from the dossier per accusation. **(enforced)**
2. At least one evidence pointer per accusation. **(enforced)**
3. A quote is copied exactly from the field its pointer names. **(enforced)**
4. For an absence, point at the thing and at the place it is missing from.
5. An engine statement copies a status from `results`. **(enforced)**
6. No evidence, no accusation.

## 3. Identifiers

- **E1 Name at least one identifier.** **(enforced)** Every accusation names at least one identifier that appears in the dossier: a `message_id`, `receipt_id`, `claim_id`, `report_id`, `result_id` or `document_id`. Put each in its own list in the accusation.
- **E2 Name every identifier involved.** Name the transfer (`message_ids`, `receipt_ids`), the report, every claim, every result and every document the fault involves. The check that confirms or refutes your accusation is run on exactly these identifiers, so a missing one can make a true accusation unconfirmable.
- **E3 Copy identifiers exactly.** **(enforced)** Copy each identifier from the dossier character for character. Never shorten one, never change its case, never invent one. Each list holds identifiers of its own type, as `index` types them: `message_ids` message ids, `receipt_ids` receipt ids, `claim_ids` claim ids, `report_ids` report ids, `result_ids` result ids, `document_ids` document ids. A status word or any other text of the dossier is not an identifier.

## 4. Evidence items

- **E4 At least one evidence item.** **(enforced)** Every accusation carries at least one evidence item: `{"pointer": "<JSON Pointer>"}`, optionally with `"quote"`.
- **E5 Pointers resolve.** **(enforced)** Each pointer must name a field that exists in this dossier, for example `/transfers/3/payload/claims/2/claim_text`. Build it from the transfer's `at` or from `index` (Dossier guide D9, D12).
- **E6 Quotes are exact.** **(enforced)** A `quote` must be copied exactly from the field the pointer names: the same characters, the same punctuation, the same case. It must be a part of that field's text. Keep it short: the few words that show the fault.
- **E7 Visible text only.** **(enforced)** For a truncated field (Dossier guide D11), quote only from the visible part.
- **E8 Showing an absence.** When your accusation is "X is not in Y":
  - give one evidence item pointing at X, with a quote of X;
  - give one evidence item pointing at Y, **without** a quote (the words are not there to quote).
  
  Example: a claim quotes "the river carried every secret", and the supplied poem does not contain those words:
  
  ```
  {"pointer": "/transfers/1/payload/claims/2/source_refs/0/excerpt", "quote": "the river carried every secret"}
  {"pointer": "/transfers/0/payload/supplied_texts/0/text"}
  ```
- **E9 Showing a difference.** When your accusation is "A differs from B" (a forward and its delivery, a peer document and the forwarded response, a status and its result, a claim and its translation), give one evidence item for A and one for B, each with a quote of the differing words where there are words to quote. For a translation, point at the claim's words and at the part of the problem that differs, for example `/transfers/1/payload/claims/1/claim_text` and `/transfers/1/receipt/outcomes/0/translation/problem/conclusion/expr/op`.

## 5. Engine statements

- **E10 Name the result and point at the status.** **(enforced)** Every engine statement names a `result_id` of this dossier's `results` and points at the status field of that same result: `/results/<result_id>/status`. `asserted_status` is that field's value, copied exactly. Another result's status field, or a result of another task, makes the statement unverifiable.
- **E11 When to write one.** Write an engine statement for every result whose status your accusation relies on (kinds `result_unsigned_or_forged`, `formal_status_wrong`, `replay_differs`, `false_conflict`). Do not write engine statements for results you did not use.
- **E12 Never assert a status the dossier does not show.** **(enforced)** An engine statement that differs from the signed result, or names a result id that does not exist, is refuted (OVS-AGENT-001).

## 6. What the infrastructure does with your evidence

- **E13 Unverifiable.** An accusation whose identifiers do not resolve, whose pointers do not resolve, or whose quote is not in its field is **unverifiable**. It is recorded against you (OVS-AGENT-002). It never reaches the router.
- **E14 Confirmed, refuted, unresolved.** A resolvable accusation is decided by the deterministic checks for its kind (Kinds and codes):
  - **confirmed** when a check reproduces it (OVS-AGENT-003);
  - **refuted** when the checks ran on your identifiers and found nothing (OVS-AGENT-001, recorded against you);
  - **unresolved** when no check can decide it, or the kind is `translation_unfaithful` or `other` (OVS-AGENT-004, human review).
- **E15 No evidence, no accusation.** Do not accuse without evidence. Prefer a short, exact accusation to a long, vague one.

## 7. Common mistakes

| Mistake | Do instead | Rule |
| --- | --- | --- |
| An accusation with no ids, only a statement | Name the transfer, claim, report, result or document ids | E1 |
| Paraphrasing in the `quote` field | Copy the exact characters from the field | E6 |
| Quoting the missing words from the field they are missing from | Quote X where it is; point at Y with no quote | E8 |
| A pointer built by counting array positions | Take it from `at` or `index` | E5 |
| An engine statement with a status you expected | Copy the status shown in `/results/<id>/status` | E10 |
| Engine statements for every result in the dossier | Only for results your accusations rely on | E11 |

Pack version 1.0 · overseer-knowledge-docs · carries brief 1.0 §5
