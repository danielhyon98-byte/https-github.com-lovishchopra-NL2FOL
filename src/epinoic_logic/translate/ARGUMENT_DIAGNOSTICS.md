# The argument family in the translator (rules `argdiag-2`)

The engine names the shape of an encoded argument (`engine/ARGUMENT.md`). The translator adds three things around it:

- the claim and report rules of the argument family (`diag_argument.py`);
- the encoding flags that keep a counterexample of an encoding artefact, or a partial encoding, from being shown as a
  verdict on the claim (`pipeline.py`);
- the precision readings that tie an interval to the figure the claim states (`precision.py`).

It also carries the prompt that marks the writer's own links (`prompts/translate_v3.md`) and the profile line for argued
subjects (`subjects.py`).

**Scope.** Every diagnostic and every flag proves a property of the encoding and of this code only. A flag moves a
display toward "nothing verified" (AMBIGUOUS_TRANSLATION), never toward success; a diagnostic never changes a status and
can only make a result less releasable.

**Display.** Every line of an outcome's summary is one line (`named.one_line`), and the model text it shows (labels,
ambiguity flags and their alternatives, review issues, retry changes), like the model text a diagnostic message quotes
(the flag ARG-EQ-001 quotes, the request item ARG-BARE-001 quotes, the labels and excerpts the evidence rules quote), has
its forgery words written "[...]" (`named.model_text`). No label can write a summary line, a status or a release line of
its own, and evidence spans keep the text as written.

**Release.** `outcome.assess_release` reads `diagnosis_incomplete`: a claim or report rule that raised, overflowed or ran
out of budget leaves the claim unresolved ("argument diagnosis incomplete (not computed is never read as none found):
..."). An overflow keeps the blocking diagnostics first (`diag_core._bound`), and the engine release check's own "named
defect" reason is kept when the claim's list names no blocking diagnostic.

## Claim and report rules (`diag_argument.py`)

`diag_core` runs `RULES` for every outcome and `REPORT_RULES` once per delivered report. It guards every rule (one that
raises is named in `diagnosis_incomplete` and fires nothing), applies the caps and the suppression, and keeps the bounds.
The evidence rules (`diag_evidence.py`) are listed in `docs/ARGUMENT_DIAGNOSTICS.md`, section 3.2; the repair round 1
additions are EVD-SRC-005 (a task-authority premise with no excerpt that the task material does not hold, a warning in
every task), EVD-SRC-001 on a needed link with only a label, the closed source-bound phrasings ("using Text C", "compare
Sources C and D", "based on the extract"), named authorities with a verdict verb (`AUTHORITY_PERSONS`) and the periods
and dated values the cherry-picking rule reads. Repair round 2 added EVD-SRC-006 (a report rule: a source credited with
the opposite stance of what it states), months and recovery words for EVD-CHERRY-001, the form-difference exception of
EVD-SRC-003 and the notation-in-words exception of EVD-SRC-005 (each with its control in
`tests/translate/test_repair_round2_evidence.py`). Close round 3 restricted EVD-SRC-001: a task-authority premise that
restates a supposition the task sets for the answer ("Assume that ...", "Suppose ...") is not named
(`diag_evidence._supposed_by_task`; `tests/translate/test_close3_task_suppositions.py`). Accuracy round 2
(`docs/ARGUMENT_DIAGNOSTICS.md`, section 18): a label-only task-authority premise whose words a sentence the task asserts
holds is an info record of EVD-SRC-001 (`_asserted_by_task`), EVD-SRC-006 reads a stance only where every clause of the
document about what the claim's stance is about carries one (`_stance_index`, `_stance_object`), and EVD-AUTH-001 reads a
cue that introduces a quotation located in a supplied text as that text's authority (`tests/translate/test_accuracy2_readers.py`,
`tests/contract/test_accuracy_round2_cases.py`).

| Code | Layer | Sev | Fires when |
| --- | --- | --- | --- |
| ARG-EQ-001 | claim | warning | the translation's ambiguity flags include a code EQUIVOCATION, SENSE_SPLIT or TWO_SENSES (case, "-" and " " ignored). The flag's message, cut to 160 characters, is quoted. Never capped on an ambiguous translation, because the ambiguity is the defect (i03b) |
| ARG-CIRC-001 | claim | warning | the translation is INVALID_FORMALIZATION and its last attempt was refused by the pipeline's circularity rule. The restating premises and their kinds are read back from the pipeline's own rejection, whose prefix `attempt N: E112: circular: premise(s)` only `_circularity` writes (f06; f07, whose joined quotation the excerpt verifies only as an atom) |
| ARG-CIRC-001 | claim | info | the same refusal, when every restating premise is a fact stated from subject knowledge (`general_knowledge`) and the claim's text offers no reason (no reason connective): the translation restated a bare factual sentence ("Shelley's sonnet was written in 1817."), which is no circle in the claim. The refusal and its status stand; the record is no finding |
| ARG-CIRC-001 | claim | info | (close round 1) the same refusal, when every restating premise claims the task's authority (`task_setting`, `rubric_rule`), the claim's text offers no reason, and the encoding grounds its point on the task too or the claim only restates the task (a question, or every content root of the claim in the task text): a report heading that restates the task question is no circle shown in the claim. A reason given for the point, or a point of the writer's own restated under the task's label, stays a warning (`circular_refusal`, `_restates_task_words`) |
| ARG-NS-003 | claim | warning | an unbridged leap (repair round 3): a writer's link of the encoding (an implication whose premise is the writer's step) joins a reason about one named thing to a conclusion about another (both sides, read on the symbols' meanings with parentheses left out, hold a capitalised word inside them, and they share no content root), the answer joins them only by a bare connective ("so", "therefore", "thus", "hence", "consequently", "as a result", "it follows that"; "because", "since", "given that"), no sentence of the answer holds words of both sides with no connective between them, and the joining sentence carries no control cue (`unbridged_leap_reading`, bounded: eight texts, 20,000 characters each). A generic code: a more specific warning on the claim takes its place (f01b) |
| ARG-BARE-001 | report | warning | a request item asks for reasons: its command term (explain, evaluate, discuss, justify, to what extent, analyse or analyze, examine, assess, why, recommend) or its words ("with reasons", "giving reasons", "give a reason", "with justification": `REASON_TERMS`); a delivered claim of an assertion role is material, uncited, has no supporting claims and no reason connective in its own text (quotations masked; "because of" is a cause phrase); and no other claim of its answer section (its paragraph, or the whole answer when it has one) has a supporting role, a reason connective or supporting claims (i01, i01b). A claim that is one quotation wrapping two or more sentences is none (`wrapped_passage`: the parsers keep such a quotation as one claim, so the sentences the same words unwrapped give as supporting claims are inside it); one quoted sentence is read as it is unquoted. A claim whose own sentence quotes a supplied text (a quotation of three words or more located in it, `_quotes_a_supplied_text`) gives its evidence and is none either (repair round 2: a History judgement with its quotation, as in English). In a report that links no claim to any other, a judgement that ranks or grades (`RANKING_WORDS`: "the most effective", "the main reason", "better") is supported by a neighbour only through the neighbour's reason connective, never by its role (repair round 3) |

The reason connectives are one table, `engine/argument_cues.REASON_CONNECTIVES`, which the engine's ARG-CIRC-001 reads
too; `diag_argument.REASON_CONNECTIVES` is the same object.

ARG-BARE-001 needs no outcome, so it reaches a claim that was never translated (i01b). The History text parser keeps a
sole judgement line as the answer's body (a sign-off such as "Hope this helps." stays a note), so a one-line verdict is
read as the answer and named here rather than reported as an answer with no material claim. When the report holds no material
claim at all, a claim of an argued role other than a note counts as the answer's assertion: a text parser that finds no
point marks a lone sentence "supporting", and the answer then asserts that sentence and nothing else (i01 in text mode).
A non-material claim keeps its severity and gets no receipt finding, by the channel's materiality rule. Its controls are
i01c (a reasoned evaluation), c03-dich, f06's text mode, i00, c02-hist and c04-quote: each has a reason or a supporting
claim in its section.

## Encoding flags (`pipeline.py`)

They are computed after an attempt is accepted, from the grounded problem and the claim text, with internal probes that
pass `diagnose=False`. Each is an `AmbiguityFlag`: the translation becomes AMBIGUOUS_TRANSLATION, the engine still runs
for inspection, and `verify_claim` caps the engine's diagnostics as the reading of an ambiguous translation.

| Flag | When | Example |
| --- | --- | --- |
| UNLINKED_CONJUNCT (B8) | some conjuncts of the conclusion share no symbol with any premise and others do; the problem is a COUNTEREXAMPLE and its linked part is ENTAILED. The counterexample falsifies only a judgement the encoding gave no reason, so it is no verdict on the claim as written | the six psychology counterexamples and the English p4-point of the end-to-end run. The engine names each judgement with ARG-PART-001 (info) |
| UNENCODED_REASON (its guard) | no premise mentions the conclusion (the f01 shape), the problem is a COUNTEREXAMPLE, and the claim's text gives a reason clause (a reason connective, never "because of") that shares fewer than two content stems with every premise label and with every meaning of a symbol a premise uses | "X, because Y" with Y left out of the encoding. f01's "because of the Treaty" is a cause phrase, so f01 keeps its COUNTEREXAMPLE and its ARG-NS-001 warning |
| PARTIAL_ENCODING (B21) | the problem is ENTAILED, but a clause of the claim (split at "but", "however", "although", "while", "whereas" or ";", quotations masked) has at least three content stems that occur in no label or meaning of the encoding, and they are at least two thirds of its content stems. The flag names the clause and says "the encoding covers only: '<the rest>'" | "Your 0.92 and 0.62 are correct as ratios, but the dependency ratio is conventionally given per 100 people of working age", encoded for its first clause only |

A counterexample whose linked part also fails keeps its COUNTEREXAMPLE: then it is a verdict on the claim. PARTIAL_ENCODING
counts a clause as dropped when most of its content is absent, not only when all of it is. A dropped clause usually
shares its topic noun with the encoded one ("dependency ratio"), so a rule needing no shared stem at all would miss the
very shape B21 reports; the two-thirds share keeps a clause that the encoding paraphrases with a few other words from
being flagged. B21 can turn a correct ENTAILED into AMBIGUOUS when a concession clause is left out. That is honest about
what was checked, and the v3 prompt asks for every clause to be encoded.

The circularity refusal (`_circularity`) now names the authority rule and each restating premise's kind: "premise(s)
p_yr (general_knowledge) restate the conclusion ..., and no check in this process established them (whatever their
label)". Which premises count is the engine's authority rule of policy 2026.10-v5 (`authority.assumed_grounding` is
`not has_authority`): a restated `task_setting`, `rubric_rule` or text premise that carries only its label is refused as
circular, and one that a check verified against the task record or a supplied text is a transcription and is not
refused. Since repair round 2 the refusal also reads a restatement beyond the engine's normal form: a premise of the
writer's own that Z3 finds equivalent to the conclusion under every assignment ("2·dt = 82" for dt = 41, a De Morgan
form) is refused as circular "in other terms" (`runner.equivalent_premises`, the engine's own E112 rule), unless it is a
calculation over stated figures.

## What the grounding checks read (`grounding.py`, `stated_rules.py`)

| Reading | Rule |
| --- | --- |
| a quoted rule (A-FA-QUOTERULE) | an implication or biconditional premise whose two sides are conjunctions of literals is stated by its located excerpt when the excerpt is a conditional ("if" or "whenever" opening the condition, never "only if", "even if", "as if" or a reported question), a universal rule ("every firm with more than 50 employees") or a biconditional, and each side's literals are stated by the right clause: an atom by the roots of its meaning that tell it from the other side (all of them, or all but one of four or more; a year or, for a universal rule, the named case the rule leaves general aside), a comparison by a figure of the clause that establishes it. The converse, another threshold or a negated side is not stated (`relation_in_source` True). A task-authority rule with no excerpt is validated the same way by a sentence of the task record. A rule the excerpt states only hedged or in another mood ("might", "tends to", "would"), with an "or" in its consequence, with a part of its condition the premise drops, framed or denied ("It is a myth that ...", "Nobody has shown that ...", a question), limited by an opening phrase of scope or restricted after it ("but only when ...", "unless ...") or credited to someone's view is not stated as the source's own (close round 1, `stated_rules.rule_qualifier`): the excerpt refutes the premise (`relation_in_source` False) and a record sentence of it validates no rule |
| a quoted conjunction (ADV-09) | a conjunction of literals that one located excerpt states is verified as that excerpt's content (`content_in_excerpt` True) |
| a quotation that does not state its premise (ADV-01) | an excerpt that is located but states neither the premise's literal nor its point (a placeholder, the point dressed as a quotation) refuses the premise (`content_in_excerpt` False), so the circularity rules treat it as the writer's own |
| another entity or quantity (fidelity-1 variant) | a figure the excerpt states for another named subject ("Southtown" for "Northtown") or another quantity (prices for wages, exports for imports) does not ground the premise. The subject words leave out units and scale words ("million", "per cent") and split hyphenated compounds and possessives, and two figures in one unseparated clause belong to their own subjects (repair round 2: a test-retest figure no longer failed against a significance level of the same excerpt) |
| a figureless task premise | refuted when no task record holds its words (`_words_no_record_holds`), validated by a task sentence that states it as a rule, else unvalidated; (close round 2, REG-CIRC-TASK-PROPOSITION) one that shares an atom with the point is never validated by a task sentence and is left to the circularity rules, as on the committed base, since a proposition the task quotes for discussion ("'X.' Discuss.") would otherwise ground its own restatement |
| derived and pooled figures (A-FA-POOLED) | a figure the answer's own written calculation derived (the claim, its supporting claims and, since repair round 2, the report's original response: `answer_texts`) grounds when the closed reader of written arithmetic gives it, exactly or rounded to its last place ("£5.00 − £3.00 = £2.50" derives nothing); the divisor of a mean of stated addends is no figure the excerpts must state |
| a relayed report (security-2) | a peer agent's report is a peer document by its id ("peer:", "peer-", "report:"), its author (an agent or a specialist) or its provenance ("relayed"), whatever its title; its excerpts never verify a premise (`is_peer_document`) |
| a dated change (A-FA-RANGE) | "from 42% in 2014 to 18% in 2024" states each of its figures; a range ("between 15% and 18%") states no single value |

## Precision (`precision.py`)

| Reading | Rule |
| --- | --- |
| an interval tied to a stated figure by enclosure (B22) | an interval no source states, with no stated figure inside it, is tied to the one figure of the claim or a supporting claim whose stated interval (its tolerance when rounded, else its half-unit enclosure at its written precision) strictly contains it, in the unit the symbol declares. A probe at the stated interval decides: when the verdict changes, the interval is rejected with the stated bounds ("stated precision: ... it is ENTAILED as encoded but COUNTEREXAMPLE at the stated interval"). s7.2's [2,294,000, 2,298,000) for "2.3 × 10⁶" (2 s.f., [2,250,000, 2,350,000)) is rejected |
| a closure variant (B16, precision half) | an interval equal to the stated one except for the closure of an end ("[1.545, 1.555]" for "≈ 1.55", stated "[1.545, 1.555)") is accepted when the probe at the stated closure gives the same verdict (h1.2 is decided), and rejected when it does not |
| an open precision | a whole number written with trailing zeros and a bare approximation word or sign ("about 100%", "≈ 30%"), with no stated precision, reads at half a unit of its last written digit ([99.5, 100.5)) or, with its trailing zeros not significant, at half a unit of its first significant digit ([50, 150)). An encoding at either is accepted. When the two readings give different verdicts the translation is AMBIGUOUS_TRANSLATION (flag `stated_precision`), so "grew by about 100%" for 55% growth is never shown ENTAILED and the faithful encoding is never refused. A figure without trailing zeros ("about 105%") keeps its one interval |
| the reference of a retry | `reference_reading` also gives a rounded or enclosed interval that differs from the stated one its stated bounds (for an open precision, the last-digit reading). A retry that encodes exactly what a stated-precision rejection asked for compares as "unchanged" and keeps the claim. The rejection names the figure as written ("0.33"), never the interval's midpoint ("0.3325") |

Every other mismatched interval of a rounded figure is still rejected.

## The marking prompt (`prompts/translate_v3.md`) and the profile line (`subjects.py`)

`translate_v3` is `translate_v2` with one section added, "Marking the writer's links". Its ten rules are:

1. every inferential step the writer asserts is its own `specialist_inference` premise, with the note
   `link: <the connective exactly as written>` and a label in the writer's words;
2. a rule stated from subject knowledge is `general_knowledge` with the note "rule";
3. a rule a source states carries that source's kind and exact excerpt;
4. a step the writer never stated is never added;
5. one proposition, one symbol, so a restatement is visible as one;
6. one word in two senses gets two symbols and an EQUIVOCATION flag;
7. scope words and causal verbs are kept as written, and instance facts keep their instance;
8. every conclusion conjunct is linked to the claim's stated reasons, or the reading says it is not;
9. every task or text premise carries its excerpt, with `document_id` the supplied text or "task";
10. assumed constants are `assumption` premises, and "verified" is never written.

`TRANSLATE_PROMPT_VERSION` is `translate_v3`; `translate_v1`, `translate_v2` and `review_v2` stay packaged byte for byte. A
prompt name is matched whole (`fullmatch`), so "translate_v3\n" is no name. Every argued (non-STEM) profile text ends
with `ARGUMENT_MARKING_GUIDANCE`: scope words and causal verbs kept as written, instance facts kept, and the writer's
steps marked `link: <the connective as written>`. The wording is the project's own.

## The English strands rule (`adapters/english_specialist/structural.py`)

ES-STR-001 (a body paragraph needs two strands, each with its own evidence) is a rule of the analytical paragraph and the
essay. It runs when the task type names one, or when the request text passed to `structural_checks` asks for a
paragraph or an essay (`strands_apply`): a writing or answering verb (write, compose, produce, draft, give, answer,
respond) followed within the sentence by "paragraph(s)" or "essay(s)". A request that only mentions the student's own
paragraph ("Please mark my paragraph", "in my essay") asks for none, so marking feedback is not held to it; an outline,
plan or bullet deliverable stays exempt. A short answer that quotes once (c04-quote, f07) is not held to it.

## Tests

- `tests/translate/test_argument_rules.py`: ARG-EQ-001 on i03b and on every equivocation flag code, none for another code;
  the claim form of ARG-CIRC-001 on f06, at info for a bare fact restated from subject knowledge, a warning when it is
  offered as its own reason or restated by the writer's step, a warning for a restated task premise with only its label
  behind it and none once the task record validates it, none for another refusal; ARG-BARE-001 on i01 and i01b in both
  modes, none on
  i01c, c03-dich, f06, i00, c02-hist, c04-quote, a request that asks for no reasons, or a note.
- `tests/translate/test_repair_round3_reports.py`: ARG-NS-003 on f01b and on a constructed leap, none on a stated connection,
  sides that share a word or name nothing, a control cue, or c01-mp; ARG-BARE-001 in a report that links nothing, none when
  the judgement is linked, states its reason or ranks nothing; the one-sentence argument, the conclusion leads and the
  ground phrases that point back, each with its controls. `tests/translate/test_repair_round3_grounding.py` and
  `tests/translate/test_repair_round3_evidence.py`: the round's grounding readings and evidence rules, each with its control.
- `tests/translate/test_partial_encodings.py`: the seven B8 counterexamples AMBIGUOUS with ARG-PART-001 at info; f01 keeps
  its COUNTEREXAMPLE and warning; a linked part that fails keeps the counterexample; UNENCODED_REASON and its control;
  PARTIAL_ENCODING on the g4.1 shape and its controls (both clauses encoded, a one-clause claim).
- `tests/translate/test_precision_b16_b22.py`: B22 rejected with the stated bounds and the stated interval accepted; B16 h1.2
  decided, a closure variant accepted when no verdict changes and rejected when one does; "about 100%" never shown
  ENTAILED for 55% growth, decided at the last digit for a doubling, and a figure without trailing zeros unchanged; the
  recorded "about 30%" claim no longer refused; the narrow-then-stated retry keeps the claim and the rejection names the
  written figure.
- `tests/translate/test_prompt_v3.py`: packaging, byte-identical earlier prompts, v3 equal to v2 plus the section, the
  version bound into a translation, each of the ten rules, the profile guidance, whole-name matching.
- `tests/adapters/test_english_strands_scope.py`: ES-STR-001 on an analytical paragraph or a paragraph request, none on a
  short answer, an outline, a request that only mentions the student's own paragraph, c04-quote or f07.
- `tests/translate/test_repair_round1_grounding.py`: each grounding reading of the table above with its control.
- `tests/translate/test_repair_round1_evidence.py`: source-bound phrasings, authority cues and the History verdict verbs,
  periods and dated values, the sole judgement line, release with an unfinished diagnosis and the blocking-first overflow,
  and derived figures in prose, each with its control.
- `tests/translate/test_display_lines.py`: one-line summaries and masked model text, with controls shown as written.
- `tests/translate/test_repair_round2_evidence.py` (42), `tests/translate/test_repair_round2_grounding.py` (9) and
  `tests/translate/test_repair_round2_perf.py` (4): the repair round 2 evidence rules, grounding readings and the bounded
  per-claim work (the cached content stems and folded vocabularies give the same readings), each with its control;
  `tests/channel/test_repair_round2_channel.py`: the quotation in a judgement's sentence and the recommendation that asks
  for reasons.
