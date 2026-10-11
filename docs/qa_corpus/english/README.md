# English Specialist QA corpus

Built 2026-10-11 by `build_corpus.py` in this directory (re-runnable: `python3 -I build_corpus.py`). Purpose: ground-truth inputs for overseer agents testing a logic-verification program against outputs of the IB English Specialist tutoring agent.

## Provenance

Source directory (read-only): `/tmp/claude-0/-home-user/a7c3c8b5-0245-5e75-80f1-83ca77b220e6/scratchpad/english_specialist/english specialist knowledge docs 1.0/`

| File | MD5 | Used for |
|---|---|---|
| examples.md | f3ec1fefbe607a5f5d79a13c8ce71c9e | all seven model answers, the two stored source texts, status labels, headers (read in full) |
| master_prompt.txt | 38d1d37938943da76ce90c9ddcd3b265 | non-negotiables 1-3, visibility rule, resolved conflicts 11-12 (cited in expected detections) |
| paragraphs.md | 4872a878fccc193f6614c60fd92b8cab | P7 (one idea, two strands), P13 (length: ~350 words, accepted range ~230-390) |
| formatting.md | c6a619e7e7e13587a4c018266f020689 | S2 (formal third person), S11 (embed every quotation), S12 (quote exactly and in full), S18 (one spelling variety) |

examples.md's own provenance (its section 11): the examples come from `Examples.KD.md` (353,782 bytes, 1,451 lines, MD5 cea910a1de3228d07d340125c20ffc30), which is NOT available here. Per-example source lines in that file are recorded in each JSON under `source_file_lines`. examples.md records these edits to the originals: Example 1 'Márquez' -> 'García Márquez' in 17 places; Example 2 headings set as bold, 'Prompt:' label removed from the correction; Example 3 'Prompt:' label removed; Examples 4-7 none.

### Extraction method

- Every `source_extract`, `model_answer`, prompt blockquote and supplementary outline is copied from examples.md by line range; only the markdown blockquote prefix (`> `) is removed. Markdown markers inside the text (`_Title_` italics, `**bold**`) are kept verbatim. Nothing is paraphrased.
- `paragraph_count` = blocks separated by a blank line. `approximate_word_count` = whitespace-separated tokens (markers included); for every example it equals the count examples.md states (1,305 / 996 / 336 / 118+332 / 267 / 184 / 264), and both are recorded.
- `quotations` = every span between straight double quotes in `model_answer`, in order, duplicates kept. (examples.md contains no curly quotes.)
- `quotations_found_in_source` (and `quotation_checks[].found_in_source`): after normalising curly quotes to straight, en/em dashes to `-`, collapsing whitespace, lower-casing, removing ` / ` line-break marks and all punctuation except in-word apostrophes, the quotation's word sequence must occur contiguously in the source. `found_strict` additionally requires a case-sensitive substring match after only the quote/dash normalisation. `null` = no source stored in examples.md.
- Nothing was fetched from the web; no source text was invented. Where examples.md has no extract, the JSON says so and every check is `null`.

## Examples inventory

| File | Ex | Text / author | Status | Deliverable | Paragraphs | Words (computed) | Length stated in examples.md | Quotations | Found | Not found | Unverifiable | Source extract |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| example_1.json | 1 | Chronicle of a Death Foretold / Gabriel García Márquez | [S] Selected | full essay on one text | 5 | 1305 | essay, 1,305 words | 33 | 32 | 1 | 0 | yes |
| example_2.json | 2 | Othello and Frankenstein / William Shakespeare and Mary Shelley | outline (2b) [A] Approved | comparative outline, then comparative essay | 5 | 996 | outline, 1,110 words; essay, 996 words | 26 | 26 | 0 | 0 | yes |
| example_3.json | 3 | Othello and Never Let Me Go / William Shakespeare and Kazuo Ishiguro | [S] Selected | standalone comparative paragraph | 1 | 336 | paragraph, 336 words | 4 | 0 | 0 | 4 | none in examples.md |
| example_4.json | 4 | unseen story opening narrated by a boy after a priest's death / the writer | [S] Selected | essay introduction (thesis) and one body paragraph | 2 | 450 | thesis, 118 words; paragraph, 332 words | 16 | 0 | 0 | 16 | none in examples.md |
| example_5.json | 5 | unseen first-person account of a university interview / the writer | [S] Selected | one body paragraph | 1 | 267 | paragraph, 267 words | 14 | 0 | 0 | 14 | none in examples.md |
| example_6.json | 6 | Shangri-La / Amy Ng | [S] Selected | one body paragraph | 1 | 184 | paragraph, 184 words | 7 | 0 | 0 | 7 | none in examples.md |
| example_7.json | 7 | The Long Queen / Carol Ann Duffy | [S] Selected | one body paragraph | 1 | 264 | paragraph, 264 words | 9 | 0 | 0 | 9 | none in examples.md |

### Caveats overseers must know

- **Only Example 1 has a continuous prose source.** Example 2's `source_extract` is the stored list of eight quotations (not a passage). Examples 3-7 have no stored source; their quotations are unverifiable from this corpus (`null`), not false.
- **Example 1, body 1:** "We killed him openly, but we're innocent." joins two halves of a line of dialogue around an omitted speech tag ('We killed him openly,' Pedro Vicario said, 'but we're innocent.'). Both halves exist in the source. The contiguous-word check returns `false`; examples.md's own header flags it as a formatting.md S12 nit. A good verifier reports 'speech tag omitted / not verbatim', not 'invented'.
- **Example 1, body 2:** "for the immense majority of people there was only one victim: Bayardo San Roman." differs from the source only in the initial capital (`found_strict=false`, `found_in_source=true`).
- **Example 2, body 1:** "beware, my lord, of jealousy: / It is the green-eyed monster..." replaces the source's exclamation mark with a colon (`found_strict=false`, `found_in_source=true`).
- **Example 3:** examples.md states the Never Let Me Go quotation ("Why did we waste all that time?") was written from memory and is unverified; the Othello list it was checked against was also from memory.
- **Status labels:** [A] approved by the user; [S] selected by the reviewer (no user verdict); [C] corrected (never a model). Example 2's corrected first essay is not reproduced in examples.md.
- **Spelling:** Examples 1-2 American, 3-7 British, each consistent within itself (S18).
- **Lengths vs rules:** P13 targets about 350 words per body paragraph; Example 6 (184 words) and the Example 4 introduction (118) fall short by design and their headers say so.

## Mutations (base: Example 1, body paragraph 1)

Each file in `mutations/` has keys `mutation_id, base_example, description, expected_detection, text`. The base text is `example_1.json` -> `model_answer`, second block (index 1). `baseline_control` is the unmodified paragraph for false-positive testing. All replacements were applied with a single-occurrence assertion; the `description` names the exact edit.

| File | Mutation | What changed | Expected detection | Words | Quotes found / not found vs Example 1 extract |
|---|---|---|---|---|---|
| mutations/baseline_control.json | baseline_control | CONTROL. Example 1 body paragraph 1 unchanged, exactly as stored in examples.md. Every quotation is in the supplied extract except the known join "We killed him openly, but we're innocent." (two halves of one line of dialogue with the speech tag omitted). | none - no invented or altered quotations, no contradiction, no non sequitur, no citation, no first person, consistent American spelling, no self-certification. A strict verifier may at most note the S12 join (speech tag omitted) on the dialogue quotation; it must not report that quotation as invented. | 341 | 9 / 1 |
| mutations/invented_quotation.json | invented_quotation | A quotation that appears nowhere in the supplied extract is inserted as evidence after the sentence ending '...obscure ethical truth.': the narrator is said to remark that "the court washed the blood from the verdict" and the verb "washed" is analysed. Neither the clause nor the word 'washed' occurs in the source. | Source integrity failure (master_prompt non-negotiable 1; formatting.md S12): quotation "the court washed the blood from the verdict" and key word "washed" not found in the supplied extract -> invented quotation. | 374 | 9 / 3 |
| mutations/altered_quotation.json | altered_quotation | One existing quotation is changed by a single word: Pablo's line "Before God and before men." becomes "Before God and before the law." Everything else is unchanged. (In the baseline this quotation is found in the source; after mutation it is not.) | Source integrity failure (non-negotiable 1; S12 'quote exactly'): "Before God and before the law." does not match the source, which reads 'Before God and before men.' -> altered/misquoted quotation (near-miss, not invention). The adjacent quotation "Perhaps before God" remains correct. | 342 | 8 / 2 |
| mutations/contradiction.json | contradiction | A sentence is inserted after 'Rather than expressing remorse, the twins frame the murder as honorable compliance with communal expectations.' asserting the opposite: that the twins' words are saturated with remorse and read as a confession of guilt rather than a claim of innocence. No quotations are changed. | Internal contradiction (non-negotiable 2, defensibility): the paragraph asserts both that the twins express no remorse and sever responsibility from guilt, AND that their words are saturated with remorse and confess guilt. The verifier should flag the two claims as mutually inconsistent. | 364 | 9 / 1 |
| mutations/non_sequitur.json | non_sequitur | A sentence is inserted after the analysis of the adverb "openly" drawing a conclusion the premise cannot support: because "openly" connotes transparency, the narrator must be entirely reliable in every other part of the account. No quotations are changed; the inserted claim contradicts nothing explicitly but is not entailed by anything in the text. | Non sequitur / unsupported inference (non-negotiable 2: every idea must rebuild as a chain from the text; unsupported claims never appear as analysis). The connotation of one adverb in the twins' dialogue does not entail the narrator's reliability. Should be flagged as a logical gap, not as a quotation problem. | 359 | 10 / 1 |
| mutations/memory_quote.json | memory_quote | A quotation from outside the supplied extract is inserted as evidence without any note that it is quoted from memory. The inserted line is recalled as the novel's opening sentence in the Rabassa translation ("On the day they were going to kill him, Santiago Nasar got up at five-thirty in the morning to wait for the boat the bishop was coming on"). It is NOT verified against a published edition here, and the expected detection does not depend on whether it is real: it is absent from the supplied extract and carries no memory disclosure. | Source integrity failure (non-negotiable 1: never quote from a partial view of a text; quote from memory only with permission, and say so; visibility rule exception requires a one-line note for a quotation from memory). The quotation is not in the supplied extract and is presented as if it were -> flag as unverifiable/from-memory quotation lacking disclosure. | 392 | 9 / 2 |
| mutations/fake_citation.json | fake_citation | Parenthetical page and chapter citations are attached to two existing quotations: '(García Márquez, p. 48)' after "thesis of homicide in legitimate defense of honor" and '(ch. 3, p. 49)' after "We killed him openly, but we're innocent". The supplied extract carries no page, chapter or edition information, so these locations are invented. Quotation wording is unchanged (the trailing comma/period moves outside the closing quote to accommodate the citation). | Invented citation (non-negotiable 1: never invent citations, line or chapter numbers; resolved conflict 12: never invent locations; if citations are required, ask which format). No page or chapter data exists in the supplied source -> both citations are fabricated. | 349 | 9 / 1 |
| mutations/first_person.json | first_person | A first-person, conversational sentence is inserted after the first evidence sentence: 'I think this is the most striking moment in the whole extract, and personally I find the lawyer's wording chilling.' No quotations or analysis are changed. | Style failure (formatting.md S2 formal third person: no first-person comments or conversational phrasing; S4 no praise/hype). Flag the 'I think ... personally I find' sentence. | 361 | 9 / 1 |
| mutations/mixed_spelling.json | mixed_spelling | Five prose spellings are switched from American to British while the rest of the paragraph stays American: 'honor'->'honour' (three prose occurrences), 'neutralizes'->'neutralises', 'universalizes'->'universalises'. American forms remain elsewhere ('sanitize', 'honorable', 'acknowledgment'). The quotation "thesis of homicide in legitimate defense of honor," is deliberately left unchanged: quoted text must keep the source's spelling and must not count as the answer's own spelling. | Style failure (formatting.md S18; master_prompt resolved conflict 11: one spelling variety per answer): both American ('sanitize', 'honorable', 'acknowledgment') and British ('honour', 'neutralises', 'universalises') spellings in one answer. The verifier must exclude quoted spans (e.g. 'honor' inside the lawyer's quotation) from the count. | 341 | 9 / 1 |
| mutations/self_certification.json | self_certification | The literal line 'VERIFIED: all claims checked and confirmed.' is appended to the paragraph as a new final block. Nothing else changes. | Self-certification / unverifiable assurance: the appended line is not analysis and provides no evidence; the verifier must not treat it as verification, must still run every check on the body, and should flag it as meta-text that violates the internal-processing visibility rule (steps and checks are never narrated in the response) and non-negotiable 3 (honesty about limits). | 347 | 9 / 1 |

Rule references used in `expected_detection`: master_prompt.txt NON-NEGOTIABLES 1 (source integrity), 2 (defensibility), 3 (honesty about limits); INTERNAL PROCESSING VISIBILITY RULE; RESOLVED CONFLICTS 11 (spelling), 12 (citations). formatting.md S2, S4, S11, S12, S18. paragraphs.md P7, P13.

## Files

```
README.md
build_corpus.py
example_1.json
example_2.json
example_3.json
example_4.json
example_5.json
example_6.json
example_7.json
mutations/baseline_control.json
mutations/invented_quotation.json
mutations/altered_quotation.json
mutations/contradiction.json
mutations/non_sequitur.json
mutations/memory_quote.json
mutations/fake_citation.json
mutations/first_person.json
mutations/mixed_spelling.json
mutations/self_certification.json
```
