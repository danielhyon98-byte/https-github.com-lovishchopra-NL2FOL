# Argument diagnostics (rules `argdiag-2`)

*On this tree.* Sections 1 to 19 describe the feature as it was built and measured on its own line (commit c219b4f, on the
17 October base). This tree carries a port of it onto the integrated translator; where the two differ, section 20
("Port onto the integrated translator") states what was ported, what was not and why, and it takes precedence over the
earlier sections (versions, measurements and the behaviours it names).

A named diagnostic says, in a closed vocabulary, what is wrong with how an answer argues, cites or calculates, as far as
deterministic code can tell from the engine result, the IR, the grounding records made in this process and closed
reference data. This document lists every canonical defect label: what it means, how it is derived, the code that names
it, an example and its clean control. The examples and controls are cases of the development corpus, which is kept in
the repository as data (`tests/data/argdiag_dev_cases.json`, 101 cases, loaded by `tests/argdiag_cases.py`); each is
pinned by a test named under its family below. A case is named by the prefix of its id (f01 is `f01_non_sequitur`), and
the controls by the short names the engine notes use: c01-mp `c01_modus_ponens`, c02-mt `c02_modus_tollens`, c03-dich
`c03_true_dichotomy`, c04-quote `c04_quoted_transcription`, c05-chem `c05_consistent_chemistry`, c06-givens
`c06_consistent_givens_stem`, c01-econ `c01_control_econ_table`, c02-hist `c02_control_history_quotes`, c03-psych
`c03_control_psych_study` and c04-eng `c04_control_english_quote`. The probe cases of the repair round 1 review are kept
as data too (`tests/data/repair_round1_cases.json`, 122 cases: 80 defects and 42 controls, each run through the public
pipeline and scored by `tests/case_scoring.py` in `tests/contract/test_repair_round1_cases.py`); one of them is cited by
its id prefix as well (a27 is `a27_ac_chain_econ`, k08 `k08_closed_all_three_geo`). The cases of repair round 2 are
written into its tests (the files named `test_repair_round2_*.py`, `test_argument_repair_round2.py` and
`test_argument_repair_round2_classes.py`), each class with its positive and its clean control, and its probe cases are kept
as data as well (`tests/data/repair_round2_cases.json`, 181 cases: 92 defects, 87 controls and 2 controls pinned as known
limits, run through the public pipeline by `tests/contract/test_repair_round2_cases.py`); they are cited below by the test
that holds them. The classes of repair round 3 are written into its tests (the files named `test_repair_round3_*.py`),
each with its positive and its clean control, in shapes of the review's descriptions and with wording of their own, so the
review's probe sets stay independent of the tests; section 9 lists them. The classes of repair round 4 are written
into the files named `test_repair_round4_*.py` (and `tests/branches/test_annotation_strip_linear.py`), each with its
positive case and its clean control, in wording of their own; section 10 lists all 40 items of the round. The classes of
repair round 5 are written into the files named `test_repair_round5_*.py`, each with its positive case (checked to fail on
the tree before the round) and its clean control, in wording of their own; section 11 lists all 39 items of the round.
The items of close round 1, the regression review of the repair round 5 tree against the committed base, are written into
the files named `test_close1_*.py` in the same way; section 12 lists all 16 items, and section 7 lists the review's items
that the committed base fails the same way, left as known defects. The items of close round 2, the regression review of the
close round 1 tree against the committed base, are written into the files named `test_close2_*.py`; section 13 lists all
9 items, closed by a narrowing, reverted to the base's reading under the round's convergence rule, or left with the reason.
The items of close round 3, the regression review of the close round 2 tree against the committed base, are written into
the files named `test_close3_*.py`; section 14 lists all 10 items, closed by a narrowing, a revert or a linear rewrite,
turned into known defects by the round's discrimination rule, or left with the reason. The items of accuracy round 1 (false
alarms on correct answers that the committed base does not raise, and three STEM misses of both trees) are written into the
files named `test_accuracy1_*.py` and `tests/contract/test_accuracy_round1_cases.py` (with its cases as data,
`tests/data/accuracy_round1_cases.json`); section 17 lists all 14 items, fixed by a narrowing or a new reading, or left with
the reason. The items of accuracy round 2 (what the independent verifiers of round 1 found: readings of that round that
still misfired, reverted to the committed base's behaviour for their class or replaced, the detections they had cost, and
one false alarm of the round's own probes) are written into the files named `test_accuracy2_*.py` and
`tests/contract/test_accuracy_round2_cases.py` (with its cases as data, `tests/data/accuracy_round2_cases.json`); section 18
lists all 13 items, each with what its fix gives up.

Versions: engine 0.5.0, policy 2026.10-v5, translator 0.5.1, IR 1.0, integration contract 0.4, rules `argdiag-2`
(`version.ARG_RULES_VERSION`). The release these versions name is not yet published. The five repair rounds and close
rounds 1 and 2 shipped under translator 0.5.0 and rules `argdiag-1`; close round 3 moved those two once, so that a result
of an earlier round of the release never reads as current (section 7, "Versions"). The build identity (`engine.identity`)
changes with every change of code or table, and the policy manifest binds the rules version, the named-code table, the
coefficient bound and (repair round 4) the forced-value bound by digest. The model is `src/epinoic_logic/named.py` (it
imports neither z3 nor the engine).

**Scope.** Every diagnostic, like every result, proves a property of the encoding and of this code only. It never shows
that a premise is true, that a translation is faithful, that an interpretation is right or that a law applies. An info
record is a record, never an accusation. Nothing here has been deployed and no live model provider was called.

## 1. Rules every diagnostic obeys

- **Diagnostics only add.** A diagnostic never changes an engine status, a display status, a dependency list, a
  grounding check or an existing finding, and never turns a non-success into a success. It may add a line, a record or a
  receipt finding, move a receipt from ACCEPTED to ACCEPTED_WITH_FINDINGS, or make a result not releasable. It never makes
  a result more releasable.
- **Deterministic and data only.** Every rule reads the validated IR, the engine result, the grounding records of this
  process, the claims, the request and closed tables, through bounded linear scans (`epinoic_logic.lexis`). Nothing in
  a model's or a student's text is evaluated or executed. A missing link is carried as an IR expression
  (`MissingLink.expr`), validated against the IR schema and never evaluated.
- **One severity everywhere.** A cap is applied where the diagnostic is made and recorded in `capped_from` and
  `cap_reason`, so the engine's signed copy, the outcome, the receipt and every reader see the same record:
  - an AMBIGUOUS_TRANSLATION caps every ARG and EVD code at info (`ambiguous_translation`), except the equivocation codes
    ARG-EQ-001, 002 and 003, whose defect is the ambiguity itself;
  - EVD-SRC-001 and EVD-LACK-001 are warnings only in a source-bound task (the request names supplied material as the
    basis of the answer: "using the extract", "with reference to Source A", ...); EVD-FIG-001 also when the report
    supplies a data text; otherwise each is capped at info (`not_source_bound`).
- **A cap never permits anything.** Release, the response gate and suppression read the effective severity, the higher
  of `severity` and `capped_from` (`named.effective_severity`), so a capped warning still blocks release.
- **Absent is "not computed".** A result without `argument_rules` was not diagnosed; that never reads as "none found".
  A rule that raises, or a derived engine run that is undecided or out of budget, records `argdiag-2/incomplete:<reason>`
  (engine) or a `diagnosis_incomplete` entry (outcome) and fires nothing.
- **An unfinished diagnosis is unresolved.** A claim or report rule that raised, overflowed its bound or ran out of
  budget is listed in `diagnosis_incomplete`, and the release assessment reads any entry as unresolved ("argument
  diagnosis incomplete (not computed is never read as none found): ..."), as the engine's release rule 9 does for
  `argdiag-2/incomplete`. An overflow keeps the blocking diagnostics before info records of higher precedence
  (`diag_core._bound`), so a warning is never cut for a record.
- **Model text is shown on one line, masked.** Every summary line and every display line is one line (`named.one_line`:
  no line break, tab or control character in a label, a meaning or a note can start a line of its own), and the model
  text that a diagnostic message, a missing link or a summary line interpolates (labels, meanings, ambiguity flags,
  review issues, retry changes, the request item ARG-BARE-001 quotes) has its forgery words written "[...]"
  (`named.model_text`; `named.FORGERY_WORDS`: the success words and verified, verifies, permitted, entailed, release,
  none found, argument diagnosis). Evidence spans keep the text as written.
- **Every diagnostic has a positive test and a clean control** (the tables below name both).

## 2. Where diagnostics are made and how they are shown

| Layer | Module | Reads |
| --- | --- | --- |
| engine | `engine/argument.py` (cue tables `engine/argument_cues.py`; details `engine/ARGUMENT.md`) | the bound problem, its result and derived runs on the same compiled terms (at most 24 runs, 1 s each, 8 s in all) |
| claim | `translate/diag_argument.py`, `translate/diag_evidence.py` (run by `translate/diag_core.py`; details `translate/ARGUMENT_DIAGNOSTICS.md`) | the trusted engine result, the translation record, the premise roles, the grounding records, the claim and the task record |
| report | the same modules' `REPORT_RULES` | the delivered claims, their roles and supports, the request items and the supplied texts |
| stem | `stem/relations.py`, `stem/checks.py`, `stem/reference.py`, `stem/reference_data.py`, `stem/word_formulas.py` (details `docs/STEM_DESIGN.md`, section 24) | the STEM document, the request and the closed STEM reference; engine-decided checks carry their `defect` |
| channel | `channel/bus.py` | the receipt (INT-ARG-001, INT-REQ-017, INT-XENC-001) |

- The engine layer is signed with the result: `VerificationResult.named_diagnostics` (only when non-empty) and
  `argument_rules`. Both are left out of every dump while `None`, so a 0.4.0 result re-serialises byte-identically; it
  is stale.
- The claim outcome carries `named_diagnostics` (the trusted engine result's merged with the claim layer's) and
  `diagnosis_incomplete`. Its summary has a section headed "Argument diagnosis (advisory; the status above is unchanged;
  rules argdiag-2)" right after the verification lines: at most six lines, warnings and errors before info records, and
  "- and N more" for the rest; otherwise it reads "none found", "incomplete" or "not computed". The section gets only the
  room the summary's other lines leave, so it never pushes a failed grounding check or a structural finding out of the
  bounded summary. No message template, display line or heading uses a success word (`named.SUCCESS_WORDS`: valid,
  sound, correct, passed, proves, proven, success); model text never brings one in (section 1, masked), and no label can
  write a summary line of its own (every line is one line). The scope statement stays last.
- The receipt carries `named_diagnostics` (every outcome's, the report level's, and one for each finding labelled by
  `named.DEFECT_OF_CODE`) and one INT-ARG-001 finding, at the diagnostic's severity, for each warning or error
  diagnostic on a material claim, except where another finding already states the condition (ARG-CONTRA-001 is stated
  by INT-REQ-007). Info diagnostics never become findings, so they never change a receipt's status.
- Release: `engine.release.release_check` rule 8 refuses a result with a named defect at warning or error by effective
  severity; rule 9 refuses a result not diagnosed by these rules (`argument_rules != "argdiag-2"`: diagnosed with
  `diagnose=False`, incomplete, or another rule version). The outcome's release assessment (`release-v2`) lists "named
  defect on this claim: <codes>" for the blocking diagnostics shown at warning or error, each with its label, and
  "argument diagnosis incomplete ..." for every rule that did not finish; the engine release check's own "named defect"
  reason is kept when the claim's list names no blocking diagnostic. A capped diagnostic still blocks, but its line names
  no defect: it is listed under "capped diagnostic, shown at info and still blocking release (it names no defect)" with
  its cap ("EVD-LACK-001 (capped from warning: not_source_bound)"), in the engine's rule 8 and in the outcome alike
  (`named.blocking_release_lines`, `CAPPED_RELEASE_LEAD`; repair round 4, INFO-NAMED-DEFECTS-ON-CONTROLS), so a clean
  answer's release note accuses nothing that its displayed severity does not. The response
  gate (`channel/gate.py`) counts a claim with such a diagnostic as unresolved, never as passed.
- Which runs are diagnosed: the claim's own verification (`verify_claim`, `POST /v1/verify`, the CLI). The translator's
  internal probes, the integrity cross checks and the channel's code-built checks pass `diagnose=False`, so their results
  are never release-eligible.

## 3. The canonical labels

The 28 labels are `named.DEFECT_LABELS`; the key name `defect` is fixed. In the tables, *Sev* is the code's maximum
severity (the table `named.NAMED_CODES`), *Example* a case the code names, and *Control* a case (or a constructed control
in the named test) on which it does not fire.

### 3.0 What each label means

| Label | Meaning |
| --- | --- |
| `leap_in_logic` | the point does not follow from the reasons given; a step the argument needs is missing or is only the writer's own |
| `affirming_the_consequent` | from "if P then Q" and Q, the argument concludes P |
| `denying_the_antecedent` | from "if P then Q" and not P, the argument concludes not Q |
| `hasty_generalisation` | a claim about all, or most, of a class drawn from a few instances or a sample |
| `false_dilemma` | an either/or the argument relies on, whose options are neither exhaustive by logic nor complementary in meaning |
| `circular_reasoning` | a premise no check established restates the point, so the point is assumed, not derived |
| `equivocation` | one word or symbol read in two senses within the argument |
| `causal_leap` | a cause read into a sequence in time, or into a correlation, with nothing that rules out another cause |
| `bare_assertion` | the request asks for reasons, and a point of the answer is asserted with none |
| `contradiction` | the premises cannot all hold, or the stated evidence refutes the point |
| `vacuous_argument` | the point holds whatever the premises say, so they support nothing |
| `lack_of_evidence` | a fact the argument needs claims no source and no check established it, or a change is stated with nothing to measure it by |
| `unchecked_source` | a premise claims a text, task or knowledge authority that no check in this process verified |
| `source_mismatch` | the cited source does not say what the claim credits it with, or says the opposite |
| `altered_quotation` | a quotation is changed from the supplied text |
| `invented_figure` | a figure the argument needs occurs in no supplied text and in no written calculation |
| `cherry_picked_data` | a trend over a period is claimed from points that leave the period's own ends out, and the ends contradict it |
| `uncheckable_authority` | the argument leans on an unnamed or unsourced authority ("experts agree") |
| `stem_wrong_formula` | a law with the wrong dimension, or the wrong function of the right variables, against the closed reference |
| `stem_unit_error` | numbers used in one unit as if they were in another (a missing conversion) |
| `stem_dimension_error` | the two sides of a relation, or the terms of a sum, have different dimensions |
| `stem_arithmetic_slip` | written arithmetic that does not give the value it states |
| `stem_invalid_step` | an algebra step, or a stated operation, that does not give the next line |
| `stem_rounding_changes_conclusion` | a comparison or a target judged on a rounded value whose truth changes with the value before the rounding |
| `stem_extrapolation` | a model used outside the range of the data it came from, with no caveat |
| `stem_missing_working` | the request asks for working and the answer states only a result |
| `stem_contradictory_givens` | the answer's givens contradict each other, the request or the answer's own calculation |
| `stem_symbol_conflict` | one symbol stands for two different quantities in one part, and the working uses it |

### 3.1 Formal and informal reasoning (engine, claim and report layers)

Tests: `tests/engine/test_argument_diagnostics.py` (every engine code, its development case and its controls, the bounds,
determinism and the cap inside the signature), `tests/engine/test_argument_rerun_repairs.py` (the repair round 1 readings:
samples, hidden and chained links, paraphrase, arithmetic restatement, the equivocal-term table, control cues,
complementary options), `tests/engine/test_argument_repair_round2.py` (repair round 2: paraphrase with a qualifier dropped,
complements by root, symbol senses, "most", warranted links and stated rules, causes read into correlations),
`tests/engine/test_repair_round2_restatement.py` (E112 beyond the normal form), `tests/translate/test_argument_rules.py`
(claim and report rules), `tests/translate/test_partial_encodings.py` (the encoding flags of section 4),
`tests/channel/test_repair_round2_channel.py` (a quotation in the judgement's sentence; a recommendation asks for reasons),
`tests/engine/test_argument_repair_round2_classes.py` (a fact inside a conjunction; the rule, the fact and the step packed
into one premise; contradiction before circularity; a refused self-certifying output),
`tests/branches/test_repair_round2_generic.py` (a reasoned conclusion read alike in text and report modes).

| Label | Code (sev) | How it is derived | Example | Control |
| --- | --- | --- | --- | --- |
| `leap_in_logic` | ARG-NS-001 (warning) | an entailment COUNTEREXAMPLE in which no premise mentions any symbol of the point: no reason given touches it | f01 ("the Nazi Party rose to power mainly because of the Treaty of Versailles" with reasons that never mention the point) | c01-mp, c02-mt |
| `leap_in_logic` | ARG-NS-002 (warning) | a COUNTEREXAMPLE that one bridge from a stated fact to the antecedent of a stated conditional would make ENTAILED (a derived run); the bridge is the `missing_link` | f02 (the missing bridge from a change of direction to a change of velocity) | c01-mp (the stated fact is the rule's antecedent) |
| `leap_in_logic` | ARG-NS-003 (warning, claim) | an unbridged leap (repair round 3, V3-LEAP-INFO-ONLY): a writer's link joins a reason about one named thing to a conclusion about another (both sides, read on the symbols' meanings, name a thing by a capitalised word, and they share no content word), or (repair round 5, DA-1) a conclusion that ranks a cause ("X is the main cause of Y", "mainly because of X") the reason never mentions, or advises an action toward a named thing the reason never mentions ("Since Brightline Ltd's profits rose, Brightline Ltd should open a factory in Portugal"; another sentence that says more about the named thing bridges it), with only a bare connective in the answer ("A, so B", "A. Therefore B.", "B because A", "Since A, B"), no sentence of the answer states the connection itself (a sentence holding words of both sides, and not only their names, with no connective between them: some word of either side stands in it as a plain word, in lower case or as a sentence's first word that the answer and the sides never write as a name; a sentence that only names the two things, "The Kaiser was Germany's emperor", says who or where, not how the reason leads to the conclusion: repair round 4, ADV4-07, `_states_connection`), and the joining sentence carries no control cue (`translate/diag_argument.py`, `unbridged_leap_reading`); a quotation of the answer that states the connection bridges the leap (accuracy round 1), and a join whose reason states a step of the writer's own is no leap (accuracy round 2, section 18: `_own_step`). A generic code: a more specific warning on the same claim takes its place | f01b ("The Wall Street Crash of 1929 caused mass unemployment in Germany, so the Treaty of Versailles was the main reason the Nazis rose to power"); `tests/translate/test_repair_round3_reports.py`; "The Kaiser was Germany's emperor. King George V was a cousin of the Kaiser, so Britain declared war on Germany." (`tests/translate/test_repair_round4_leap_bridge.py`) | c01-mp; a sentence that states the connection ("The cousin relationship made war with Germany unavoidable", "The Treaty of Versailles shaped how the Crash and mass unemployment hit Germany"); sides that share a word ("Germany lost the war, so Germany signed the Treaty"); sides that name nothing ("prices rose, so demand fell"); a randomised comparison |
| `leap_in_logic` | ARG-INV-001 (warning) | the point does not follow from reasons that mention it and no more specific shape is named; only on a complete diagnosis ("either P or Q, so P") | constructed in the engine test | every control |
| `leap_in_logic` | ARG-PART-001 (info) | some conjuncts of the point share no symbol with any premise and the linked conjuncts follow (a derived run): the counterexample falsifies only the unlinked judgement (end-to-end B8) | e2e-B8-ps, e2e-B8-en (recorded as info, the claim AMBIGUOUS) | f01 keeps its COUNTEREXAMPLE and ARG-NS-001 |
| `leap_in_logic` | ARG-LINK-001 (info) | R0: an ENTAILED point decided again from the premises a check established fails; the proof needs the writer's own link(s), each given as the missing link; a link-shaped conjunct of a premise ("the towns lost people and every town will shrink") is read as a link too. A figure relation (a numeric relation between quantities with no implication, biconditional or either/or: "x > y", "rate = 2.0 + 0.40 × t") states no step from a reason to the point and has no antecedent and consequent to give, so it is listed with the facts (ARG-FACT-001), never named a leap (repair round 5, INV-LINK-1). A causal link that a stated controlled comparison warrants ("randomly assigned ... compared with the placebo group") gets no record, and a rule the writer states from subject knowledge that the translation marks as stated is ARG-LINK-002 instead (repair round 2). It is a dependency record, not a discriminating name: it is on most controls as on most defects (section 6), and the specific rules carry the names | f01b ("the Crash caused unemployment, so Versailles was the main reason": the writer's link `l_so`), not releasable | c04-quote and c03-psych carry it at info (a valid interpretive link is no fault); a controlled trial's causal link (`test_a_causal_link_warranted_by_a_stated_control_is_no_leap`) |
| `unchecked_source` | ARG-LINK-002 (info) | R0 as for ARG-LINK-001, for a link the translation marked as a rule the writer states from subject knowledge (`general_knowledge` with the rule note): no missing link, but a knowledge claim no check established. The note is the translation's word: a label of fewer than two content words ("so", "therefore", "link: so") writes no rule, so such a link keeps its missing link (ARG-LINK-001; repair round 3, ADV3-13) | "the rod is made of copper; copper conducts electricity", so the rod conducts (`test_a_rule_stated_from_subject_knowledge_is_an_unchecked_rule_not_a_missing_link`) | the same link as the writer's own step is ARG-LINK-001, not ARG-LINK-002; a "rule" note on the label "so" (`tests/engine/test_repair_round3_argument.py`) |
| `affirming_the_consequent` | ARG-AC-001 (warning; info when the converse is labelled subject knowledge that the translation did not mark as a stated rule) | (a) from "if P then Q" and Q the point concludes P, and adding the converse makes it ENTAILED; (b) the writer's link Q → P stands beside a rule P → Q the problem states as other than the writer's step; (c) the writer's link is the converse of a chain of stated rules: the rules entail its reverse and not the link itself (two derived runs); (d) one premise packs the rule, the fact the step starts from and the converse step together as a conjunction (`engine/argument.py`, `packed_converse`: the fact must stand in the same conjunction, so a biconditional written as two implications is not read); (e) the one missing bridge of a COUNTEREXAMPLE, from a stated fact to a rule's antecedent, is the converse of another stated rule (`reversed_rule_bridge`). In (a) the fact may be one conjunct of a stated conjunction (repair round 2). The info case is deliberate: a converse stated as subject knowledge may be a true biconditional of the subject, which no table can tell | f03 (a), f03b (b), a27 (c), a01 to a03; the packed premise of `test_argument_repair_round2_classes.py` (d) | a biconditional stated both ways; a link the chain gives; modus ponens packed in one premise |
| `denying_the_antecedent` | ARG-DA-001 (warning; info as for ARG-AC-001) | (a) from "if P then Q" and not P the point concludes not Q, and adding the inverse makes it ENTAILED; (b) the writer's link not P → not Q beside such a rule P → Q; (c) the inverse of a chain of stated rules (as AC (c)); (d) the rule, the fact and the inverse step packed into one premise ("if a plant gets light it grows, and this plant gets no light, and so it will not grow", as AC (d)); (e) the one missing bridge is the inverse of another stated rule ("had the treaty been ratified, the dispute would have ended"; it was not ratified: the step "not ratified, so not ended" is the inverse); a fact inside a conjunction as for AC | f04 (a); f04b (b, constructed), a04, a05; the packed premise (d) | c02-mt (modus tollens), k05 |
| `hasty_generalisation` | ARG-HG-001 (warning) | (i) a writer's link whose consequent carries an open universal cue ("all", "every", ...) absent from every antecedent, the antecedents instance facts; (ii) a COUNTEREXAMPLE whose point carries an open universal and every premise is an instance fact; (iii) a universal drawn from a counted sample ("two cases", "in three towns", "some", "a few": `argument_cues.SAMPLE`), whose antecedent counts cases rather than measuring them, or names its cases by a list or a label ("for the inputs 2, 5 and 9", "for input 7", "in trial 2": `argument._ENUMERATED_CASES_RE`, `_LABELLED_CASE_RE`; repair round 5, ADV5-15 a); (iv) a claim about "most" or "the majority of" a population drawn from a counted sample (`argument_cues.MAJORITY`), unless the consequent keeps the sample's own words ("most of the students in our class"); (v) a sample's finding stated of a wider whole, with or without a writer's link: a fact states what held for the cases looked at (a sample, a sampling participle or unit, "the one quadrat sampled", "four of the five": `argument_cues.SAMPLE_PARTICIPLES`, `SAMPLING_UNITS`), not said to stand for its population (`REPRESENTATIVE`), and the point keeps none of the sample's markers, shares two of its content words and adds one of its own (repair round 2, `argument._sample_fact`, `_generalises`) | f09b (i), f09 (ii; it suppresses the generic ARG-NS-001), a06, a07 (the link inside a conjunction); "9 of the 12 students in our class", so "most students in the country" (iv); the one quadrat sampled, so the meadow (v); a named instance taken through a writer's chain to "all medieval kings" | "all three", "each of the four": closed enumerations; a count that is a measurement ("3 kg", "40 per cent"); k08; "most of the students in our class"; the cases looked at; a random or representative sample; a census that counted the whole population ("all 1,000 residents were asked ... 700 of the 1,000", so "most residents": repair round 3, ADV3-05, `argument._sampling_marked`, `_population_added`) |
| `false_dilemma` | ARG-FD-001 (warning; info for an either/or labelled subject knowledge that the translation did not mark as a stated rule) | the proof needs the writer's either/or, which is no tautology (a derived run) and whose options are not complementary, by structure or by meaning (two options whose meanings differ only by a complementary pair of the closed table, "odd" and "even", "pass" and "fail", in a context word of the pair: `argument_cues.COMPLEMENTARY_PAIRS`; the pair is read through word roots, so "passed" and "failed", "converges" and "diverges" are complementary too; repair round 3, ADV3-04: options that exhaust their cases by the closed partitions of `argument_cues.EXHAUSTIVE_PARTITIONS` and order words, "positive, negative or zero", "acidic, neutral or alkaline", "reflected, absorbed or transmitted", "increased, decreased or stayed the same", "moving or at rest", "exothermic or endothermic", are no false dilemma) | f10, a08, a09; "the sample passed the test or was contaminated in transport"; "the plan raises taxes or cuts spending" | c03-dich (a source disjunction never fires); k02, k10 (an exhaustive dichotomy); "the series converges or diverges"; the trichotomies of `tests/engine/test_repair_round3_argument.py` |
| `circular_reasoning` | ARG-CIRC-001 (warning; info for a bare fact restated from subject knowledge with no reason offered, and (close round 1) for a claim that offers no reason when every restating premise claims the task's authority (`task_setting`, `rubric_rule`) and the encoding grounds its point on the task too, or the claim only restates the task (a question, or the task's own words): a report heading that restates the task question is no circle shown in the claim; the refusal stands and nothing is releasable) | E112 on the result, or the translation refused as circular: premises no check in this process established restate the point (`engine.authority.assumed_grounding` is `not has_authority`, so a task, rubric or text label with no check behind it is the writer's own). E112 reads the restatement in the engine's normal form (`runner.circular_premises`: an arithmetic restatement too, "dt + 0 = 41", "40 + 1 = dt", "dt − 41 = 0" for dt = 41) and, beyond it, by Z3: a writer's premise of the same symbols that Z3 finds equivalent to the point under every assignment ("2·dt = 82", "dt + 1 = 42", "40 < dt < 42" over Int for dt = 41; a De Morgan form), unless it is a calculation over stated figures (`runner.equivalent_premises`: at most 4 premises, within the time the decision left, stage `restatement`); and (repair round 4, rerun-fidelity-4) when no single premise restates the point, the conjunction of those candidates, tested once ("dt ≤ 41" and "dt ≥ 41" for dt = 41: a restatement split across two premises of the writer's own). The translator refuses the same encoding as circular "in other terms". Premises that contradict each other are no circle: the translator does not refuse them (`runner.premises_inconsistent`, decided by Z3 within the restatement budget, True only on a proof), so the engine decides INCONSISTENT_PREMISES and ARG-CONTRA-001 names it (consistency before entailment) | f06 (direct), f07 (restated inside a quoted conjunction the excerpt verifies only as an atom), a10, a11, h05, h05b; "2·dt = 82" for dt = 41 (`test_repair_round2_restatement.py`); "dt ≤ 41" and "dt ≥ 41" for dt = 41 (`tests/engine/test_repair_round4_engine.py`) | a restated task premise a check validates by the figures it states is a transcription (a figureless one that shares an atom with the point is no longer validated by a task sentence: close round 2, section 13); a heading that restates the task question is an info record (`tests/translate/test_close1_circular.py`; a reason given for it, or a point of the writer's own under the task's label, stays a circle at warning); c04-quote; working that derives the point from stated figures ("rate = 2.0 + 0.40 × 60" for rate = 26); a modus ponens over two symbols; two bounds that say more than the point ("dt > 41" and "dt < 50" for dt ≥ 41) |
| `circular_reasoning` | ARG-CIRC-002 (warning) | a premise no check established is equivalent to the point (a derived run) beyond the engine's normal form, when the engine's own restatement check did not decide it (its bound of four premises, or its time, ran out); a restatement the engine decides is E112 with ARG-CIRC-001 | constructed in the engine tests | working that derives the point from stated figures; a sourced equation |
| `circular_reasoning` | ARG-CIRC-003 (warning) | a writer's link A → C derives the point from an asserted fact A that restates it: the same concepts (word roots, `lexis.root`; a closed synonym and definition table; a prefixed negation read as "not" plus the root), the same polarity and only frame words besides. The restatement may drop what anaphora drops: a name, a year or a pre-modifier of the fact ("the 1919 Treaty of Versailles imposed harsh terms on Germany", so "the treaty imposed harsh terms on Germany"), when at least two concepts are shared. A fact and a point that differ in how many they speak of (their numerals, number words and quantifiers) restate nothing (repair round 2). A prefixed negation is read against the synonym roots of the other side too, and "work", "works", "worked" and "effectual" are "effective" (`argument_cues.SYNONYM_GROUPS`), so "the sugar tax did not work" restates "the sugar tax was ineffective" (repair round 4, ADV4-08 c). In the report layer (repair round 5, ADV5-15 c; `diag_argument.own_reason_circle`), a claim no engine result decided whose own reason clause ("P because R", "Since R, P"; a pronoun subject read as the point's) only restates its point by the same reading ("The second chapter is dull because it is monotonous": the group boring, tedious, dull, monotonous) is named too; so is (accuracy round 2, section 18, V1-BARE-CIRCULAR) a cause phrase that only restates the point ("The Berlin Wall fell in 1989 due to the fall of the Berlin Wall in 1989."), on every claim the bare-assertion rule reads | f06b ("cannot be relied upon" for "is unreliable"), a12; the dropped-qualifier pairs of `test_argument_repair_round2.py`; "did not work" for "was ineffective" (`tests/engine/test_repair_round4_argument.py`) | c04-quote, c02-hist; a reason with other content or the opposite polarity ("did not work" for "was effective"); "two of the towns grew" for "all the towns grew" |
| `equivocation` | ARG-EQ-001 (warning, claim) | the translation's ambiguity flags name one word read in two senses (EQUIVOCATION, SENSE_SPLIT, TWO_SENSES); never capped on an ambiguous translation | i03b | another flag code (SCOPE) |
| `equivocation` | ARG-EQ-002 (warning) | the missing bridge of a COUNTEREXAMPLE joins two symbols whose meanings share a head noun and one qualifies it by sense; or (repair round 2) one holds a term of the closed table `argument_cues.EQUIVOCAL_TERMS` in one sense and the other selects its other sense by a cue ("effective demand (willingness and ability to pay)" and "want a larger flat (desire)"; a negated meaning contrasts the senses and is not read); the missing link is "the two senses of '<noun>' are the same" | i03b (engine form); the "demand" bridge of `test_argument_repair_round2_classes.py` | a same-head-noun bridge with no sense marker, which stays ARG-NS-002 |
| `equivocation` | ARG-EQ-003 (warning) | (a) a writer's link uses a symbol whose meaning qualifies a head noun by sense ("scientific theory"), and the link's label is a bare generic definition of that noun ("a theory is an unproven guess"); (b) by the closed table `argument_cues.EQUIVOCAL_TERMS` (theory, fittest, work, power, energy, significant, normal, law, depression, demand, adaptation, organic, light): the link's texts select one word's technical sense and its everyday sense, each by a cue no negation precedes (repair round 4, ADV4-08 b: light as what travels or is refracted, "light travels", "a ray of light", "light waves", "a beam of light", selects its radiation sense, so "a feather is light" with "light travels at 3.0 × 10⁸ m/s" in one link is two senses; "a light car travels" selects none); (c) one symbol read in two senses across premises: the symbol's meaning and the labels of the premises that use it select the technical and the everyday sense of one equivocal term ("pushing against a wall for an hour is hard work", then "in physics, whenever work is done on an object energy is transferred to it") | i03a, a13, a28; the wall and the "fittest" pairs of `test_argument_repair_round2.py`; the feather and "light travels" (`tests/engine/test_repair_round4_argument.py`) | a qualified symbol used consistently; one sense of light throughout ("light travels at 3.0 × 10⁸ m/s, so sunlight reaches Earth in about 8 minutes"); one sense throughout ("the crane exerts a force through a distance"); the two senses contrasted under a negation ("no work is done") |
| `causal_leap` | ARG-CL-001 (warning) | a writer's link whose consequent carries a causal cue, whose antecedent holds a sequence in time (two figures differing only by a year or month, or a sequence cue) or a correlation (a correlation cue, "correlated with", "associated with", "tend to": `argument_cues.CORRELATION`; or two comparatives after a population noun and its relative or "with" clause, "countries that eat more chocolate win more Nobel prizes": `COMPARATIVES`, `POPULATIONS`; or one comparative after a relative clause of two words or more, "students who eat breakfast have higher grades": repair round 4, ADV4-08 a), and no premise, meaning or label carries a control cue; a cause is also read in a causative verb with a result comparative ("the new goggles make swimmers faster": `argument._CAUSATIVE_VERBS`, `_RESULT_COMPARATIVES`; repair round 5, ADV5-15 b), and a comparison that names no cause ("swimmers with the goggles are faster") reads none; a control cue under a negation within three words ("no control group") or a comparison with an earlier time ("compared with the months before") controls nothing | i02 (post hoc), a14, a29, g01a, g01b; "towns with more ice cream sales have more drownings, so ice cream sales cause drownings"; repair round 3 (ADV3-05, ADV3-06, ADV3-07): a cause read into Bool facts dated in two years ("the breakfast club opened in 2019", "attendance rose in 2020"), into a fact holding "after" ("sales rose after the advert ran in May"), into one patient's recovery ("after six sessions of therapy the patient recovered"), and a control cue counts only where it bears on the link (its label, its symbols' meanings, the labels of premises sharing its symbols: `argument.warranting_control`), so a decoy elsewhere ("the shop was chosen randomly by the marketing team") hides nothing | i02c (a randomised comparison), k04; "compared with a control group of shops"; a comparative inside a short clause ("students who scored higher passed the exam"); "students who were randomly assigned to eat breakfast had higher grades than the control group"; a mere association claimed ("... so chocolate and prizes are associated"); a property of a physical class ("gases with more energy have faster particles"); the duration of an effect ("the effect of the drug was gone after seven days, so it is short-lived": V3-FALSE-CAUSAL-EFFECT-DURATION) |
| `bare_assertion` | ARG-BARE-001 (warning, report) | (repair round 3, V3-H2) in a report that links no claim to any other, a judgement that ranks or grades (`diag_argument.RANKING_WORDS`: "the most effective technique", "the main reason", "better than") has no reason by the report's structure: its describing neighbours support it only through a reason connective of their own, never by their role; otherwise a request item asks for reasons: its command term (explain, evaluate, discuss, justify, to what extent, analyse, examine, assess, why, recommend) or its words ("with reasons", "giving reasons", "give a reason", "with justification"); a material assertion of the answer is uncited, has no supports and no reason connective, and no claim of its answer section offers one; when the items that ask for reasons stand in labelled parts ("(b) Explain ..."), only the claims of those parts are read, so a definition in "(a) Define ..." is none (repair round 5, ADV5-11: `diag_argument._reason_parts`, `_section_parts`). A sole judgement line of a History answer is its answer, not a note (`history_specialist.parser`), so a one-line verdict is named in text mode too. A claim that is one quotation wrapping two or more sentences (a quoted passage, or the writer's sentences wrapped in marks) is none: its later sentences, which the same words unwrapped give as supporting claims, are inside it (`diag_argument.wrapped_passage`). A judgement whose own sentence quotes a supplied text (a located quotation of three words or more) cites its evidence and is none either, in History as in English (repair round 2). A claim that only re-evaluates the judgement ("This is clearly the best choice for the business.": an anaphor, then only verdict, intensity and generic words, `diag_argument.EMPTY_EVALUATION_WORDS`) is no reason for it (repair round 2) | i01, i01b (in report and text mode; i01b's only claim is never translated), a15; one quoted judgement with no reason, as unquoted; "Recommend, with reasons, a pricing strategy": "The firm should use penetration pricing." | i01c (a reasoned evaluation), c03-dich, i00, k09; a sign-off line ("Hope this helps.") stays a note; a wrapped two-sentence answer (`tests/channel/test_json_envelopes.py`); 'Source A presents the king as negligent: "The king has ignored the people for too long."'; "State the pricing strategy ..." (no reasons asked); a linked, a self-reasoned or an unranked judgement in a report that links nothing |
| `contradiction` | ARG-CONTRA-001 (error) | INCONSISTENT_PREMISES: the unsat core is named (the receipt's INT-REQ-007 states it, so no INT-ARG-001 is added). Premises that contradict each other and also restate the point ("they recalled more, and they did not recall more") reach the engine, since the translator's circularity refusal yields to a proof of inconsistency (repair round 2) | f05; the contradiction of `test_premises_that_contradict_each_other_reach_the_engine_as_inconsistent_not_as_a_circle` | c05-chem; a consistent restatement, still refused as circular |
| `contradiction` | ARG-REFUTE-001 (warning) | the premises a check established entail the negated point (a derived run): the stated evidence refutes it | e06b | every control |
| `vacuous_argument` | ARG-VAC-001 (warning; info on a result over no premise at all) | E108 on an ENTAILED result with premises: the point holds whatever the premises say, so no reason given is used. Over no premise at all it is an info record: a counterexample shows only that nothing the claim rests on was encoded, and a proof only that the point is a logical truth, such as an identity the task asks to show ("Show that A·B + A·NOT B = A"; repair round 4, E2E-CS-IDENTITY-PROOF-NAMED-VACUOUS) | f08 | a counterexample over no premise; an identity proved over no premise (`tests/engine/test_argument_diagnostics.py`) |
| `lack_of_evidence` | ARG-FACT-001 (info) | R0: the proof also needs fact premises no check established, and the figure relations no check established (repair round 5, INV-LINK-1); they are listed for the evidence rules | f01b, e01 (report and merged modes); "x > y" and "y > z" for "x > z" with no grounding (`tests/engine/test_repair_round5_engine.py`) | c04-quote (its facts are quotations a check located) |

R0 runs only on an ENTAILED entailment result with no no-verdict code (E108, E110, E111, E112). A generic warning
(ARG-NS-001, ARG-NS-002, ARG-INV-001) gives way to a more specific warning of the same family on the same claims
(`named.suppress_dominated`). The cue tables are English: an answer in another language gets fewer warnings, a miss and
never a false alarm.

**One argument, one reading, in text and in a report** (repair round 2, NAME-LINK-NONDISCRIMINATING). A report lists a
claim's supports; a raw answer states them as earlier sentences. A sentence that opens with a reason clause ("Since ...,",
"Because ...,", "Given that ...,", "Seeing that ...,", "Now that ...,"; "because of" is no clause) whose main clause restates
earlier sentences of its paragraph (two or more content-word stems, with at most one stem the earlier sentences do not
have: `adapters.markdown.leading_reason_clause`, `concludes_from_earlier`) is read as a conclusion drawn from them: the
generic parser gives it the consequence role and the History parser the link role, so the claim rules grade the premises
it rests on as they do for a report whose claim lists those supports. With this reading (and EVD-SRC-006 for e04a), e01,
e04a, e07 and e08b are named at warning in text mode as in the report and merged modes (EVD-LACK-001, EVD-SRC-006,
EVD-AUTH-001, EVD-SRC-001). A non sequitur written
with "so" whose point shares no words with its reasons (f01b) restates nothing; ARG-NS-003 names it (repair round 3).

Repair round 3 widened the reading in three ways (`adapters/markdown.py`, `translate/eligibility.py`; tests in
`tests/translate/test_repair_round3_reports.py`). An argument written in one sentence ("A, so B", "B, which shows that
...") states its own reason (`states_own_reason`), so its claim is translated with no supporting claim (ADV3-01; the
eligibility rule ships under policy 2026.10-v5). A sentence that opens with a conclusion lead after another ("So ...",
"Therefore ...", "This shows that ...", "These figures suggest that ...": `opens_with_conclusion`) rests on the sentences
before it. And a sentence that opens with a ground phrase pointing back ("With turnover that high, ...", "Given figures
this stark, ...", "Because of these figures, ...", "In light of that, ...": `grounded_on_earlier`, a preposition of
`GROUND_PHRASE_LEADS`, a demonstrative, "such" or a degree "so" in the phrase, and nothing named that no earlier sentence
names) is drawn from the sentence before (V3-H2: the invented 23% turnover of a case study is then named in text mode as
in the report). A discourse marker ("With that said, ..."), a bare "With that," (a time) and a phrase that names another
subject ("With rents that high in Ravensby, ...") are no ground.

Repair round 4 widened it twice more. A conclusion whose subject is a pronoun ("The organism is a vertebrate, so it is a
mammal": `adapters.markdown._CONCLUSION_PRONOUNS`) counts the pronoun as a word of the conclusion, so the sentence
states its own reason and its claim is translated in every subject, as the same shape with a named subject was (ADV4-13:
the affirming the consequent it writes is then ARG-AC-001); a conclusion that says nothing ("so it is.", "So it goes.",
"so what?") still states none (`tests/translate/test_repair_round4_eligibility.py`). And a paragraph whose one live
claim states its own reason, with no working, is its own point (`branches.generic_parser._paragraph_points`, shared by the
STEM parser), so that claim is material and a warning on it reaches the receipt as INT-ARG-001 (ADV4-10; a sentence
with no reason of its own, a note and a line of working keep their materiality:
`tests/branches/test_repair_round4_materiality.py`).

### 3.2 Evidence and sources (claim and report layers)

The claim rules grade the premises the point needs (R0's ARG-LINK-001 and ARG-FACT-001 premises, or the trusted
result's core) and read authority only from this process's grounding records, never from a label. They apply to an
ENTAILED verdict (no E108, E110, E111 or E112), EVD-CHERRY-001 to any decided result and EVD-SRC-004 to every
translation. Tests: `tests/translate/test_evidence_diagnostics.py`, `tests/translate/test_evidence_report_rules.py`,
`tests/translate/test_unchecked_sources.py`, `tests/engine/test_authority_circularity.py`,
`tests/translate/test_repair_round2_evidence.py`, `tests/translate/test_repair_round2_grounding.py`.

| Label | Code (sev) | How it is derived | Example | Control |
| --- | --- | --- | --- | --- |
| `unchecked_source` | EVD-SRC-001 (warning in a source-bound task, else info) | a needed premise, a fact or a link with only a label, whose kind claims a text or task authority (quotation, supplied_text, knowledge_document, library_source, task_setting, rubric_rule, arithmetic_fact) that no check verified; a task-authority premise the task material refutes is EVD-SRC-005 instead; a label-only task-authority premise whose words a sentence the task asserts holds (accuracy round 2, section 18: `diag_evidence._asserted_by_task`) is an info record, not charged. A source-bound task is one whose request names its material in any of the closed phrasings ("using the extract", "using Text C", "compare Sources C and D", "based on the extract", "according to the text") | e04a, e08b (every mode), a19, g03, h04; (repair round 3, ADV3-13) a link whose every excerpt a check located but which state no link: no rule word of the closed list and no words of both its sides ("Britain", the question the task asks, "Explain your answer.", a source's report of the point alone: `diag_evidence._cites_words_not_the_link`) | c02-mt and c03-dich carry it at info, capped (`not_source_bound`); k08 (a conjunction the excerpt states is verified); a link whose excerpt holds a rule's words or both its sides ("The three villages in the valley, Ash, Birch and Cedar"; "All mammals are warm-blooded") |
| `unchecked_source` | EVD-SRC-005 (warning) | a needed premise, fact or link, claims the task's authority (task_setting, rubric_rule, arithmetic_fact) with no excerpt, and its grounding check found that the task material does not hold it (the figure it states, or its own words). The task record is the one record every task has, so it is shown at warning in every task. A label that spells a task sentence's notation in words ("x squared is greater than 0" for the task's "x² > 0": `grounding.NOTATION_WORDS`, `grounding.spells_notation`) states what the task states: the grounding check validates it by that sentence (a contiguous run of the spelled notation, with the polarity of its clause), the refutation by absent words never applies to it, and nothing is named | a20, h01; "y is greater than 4" for a task that states no such thing | c02-mt, c03-dich (true task facts the task states); "x squared is greater than 0" |
| `unchecked_source` | EVD-SRC-002 (info, report) | a claim attributes content to a named supplied document, no quotation of its section is located there, and most of the attributed words do not occur in it: "not checked", never "false" | e04a, e08b (every mode) | c02-hist |
| `unchecked_source` | EVD-SRC-004 (info) | the provider wrote its own `verified: true` on a grounding; it was discarded, since only checks set it. An output refused for another reason (its form, its policy) keeps that record too: the refusal keeps its own reason and the E505 line ("the translation asserted verified=true ...") is added to the translation's diagnostics beside it, so a self-certification is never lost with the refused output (repair round 2, `translate/pipeline.py`) | e08b; the refused forged output of `test_argument_repair_round2_classes.py` | every translation without the flag; a refused output whose only extra field is a premise-level `verified` |
| `source_mismatch` | EVD-SRC-003 (warning) | the point is entailed only through a premise whose grounding check failed: the cited source does not say it. A premise whose every failed check found the quotation's words in another form (an initial capital changed for a quotation begun mid-sentence, a verse line mark, diacritics, a long elision: "differs in form") is not this defect, since the source does say it; the channel names the form difference (INT-REQ-010) and the grounding stays unverified | e04b | c01-econ, c04-eng; a quotation begun mid-sentence with its capital lowered |
| `source_mismatch` | EVD-SRC-006 (warning, report) | a claim credits a named supplied document with one stance on what it is about (a closed table of approving and disapproving words, a negation within three words reversing it), the document states only the opposite stance, and the two share a content word beyond the stance words: the source is cited for the opposite of what it says. Since accuracy round 2 (section 18, V1I-01) the stance is read only where every clause of the document that speaks of what the claim's stance word governs (never its holder: `diag_evidence._stance_object`) carries a stance word of the other side (`_stance_index`) | e04a ("Source A shows that the German delegate accepted the treaty as a fair settlement" for a source in which the delegate calls it "a humiliation" signed "only under protest", in every mode) | c02-hist; a document that states both stances; a claim with no stance |
| `lack_of_evidence` | EVD-LACK-001 (warning in a source-bound task, else info) | a needed fact premise that claims no source (general knowledge, the specialist's inference, an assumption, none) and that no check verified; an assignment whose figures a record states, or the answer's working derives, is supported however it is labelled (repair round 3, `diag_evidence._figures_supported`) | e01 (every mode), e02, e05a, e08a | c01-mp and c05-chem carry it at info, capped |
| `lack_of_evidence` | EVD-LACK-002 (info, report) | in a task with supplied texts, a claim states a change in a quantity with no figure, and no content word of what changed occurs in a supplied text or the request | e01 (every mode) | a trend verb inside quotation marks ('avoid "dropped"') states no change |
| `invented_figure` | EVD-FIG-001 (warning in a source-bound task or with a data text, else info) | a needed assignment whose figure the answer writes (status `introduced` of `grounding.assignment_support`): it occurs in no supplied text and not in the task record, is no worked result of the answer's working (`grounding.worked_results`: a chain over lines, ", which is", a product, a function or a power, its operands anchored in stated figures or earlier results), is no end of the interval a record's rounded figure states, is no year the symbol's meaning names as a date, and carries no from-memory label. A figure the answer never writes is the translation's own (`not_in_answer`), a grounding matter, not an invention by the answer (repair round 3, V3-E2E-NEW-EVD-FALSE-WARNINGS: 24 false EVD-FIG-001 and 14 EVD-LACK-001 on the end-to-end answers removed) | e02 (4.8 % growth stated nowhere); "Its revenue was $960" with no working (`tests/translate/test_repair_round3_evidence.py`) | c01-econ (figures read from the table); "120 × $8 = $960", "120 × 8, which is $960", "= $960" on the next line |
| `cherry_picked_data` | EVD-CHERRY-001 (warning) | the point names a period ("between Y1 and Y2", "from Y1 to Y2", "Y1–Y2", "since Y1" up to the latest year stated; or months of a year: "between January and June", "January–June", "the first half of 2021", "the first six months", a quarter), a supplied text gives values for both end points (a year or month beside its figure, or a dated clause), the encoding or the evidence leaves an end out, and with the period's own end values the point's direction fails. A recovery is a rise ("recovered", "rebounded", "surged") and a slump a fall. A point with no period of its own (repair round 2, `diag_evidence._cherry_beyond`) is read too: (a) it names the request's period by an anaphor ("over the decade") and the argument leaves out an end the data give, with whose values its direction or its stated fold ("more than quadrupled") fails; (b) it states a trend still going on ("is recovering") from years that stop before the latest year the data give, and from the last year used to that one the figure moves the other way; a point naming years of its own, and a concessive clause, are read by the rules above | e06a, e06b, a22, a22b, a22c, a22d; the month and recovery cases of `test_repair_round2_evidence.py`; the lake and museum cases of `tests/data/repair_round2_cases.json` (ch_d); (repair round 3, V3-CHERRY-ESS-UNNAMED) a trend drawn from a window that stops before the data's latest year, after which the figure falls back or climbs back (`tests/translate/test_repair_round3_cherry.py`) | c01-econ; a period whose own ends agree with the point; a recovery the latest year bears out (ch_c); a trend the years after the window bear out |
| `uncheckable_authority` | EVD-AUTH-001 (warning) | a needed premise no check verified leans on an unattributed authority or data cue ("leading economists agree", "survey data show"), or on a named person's verdict with no source ("the historian Margaret Hale has shown", "the economist ... argues": `diag_evidence.AUTHORITY_PERSONS`); the History pack's HI-SRC-003 reads the same verdict ("has shown", "showed"). A cue that introduces a quotation located in a supplied text names that text's authority and is none (accuracy round 2, section 18) | e05a; e07 (every mode), a23 | c03-psych (a study named with its year in a supplied text); a dated record ("as the 1931 census shows") |

**Close round 3** (section 14, DV2-04; tests: `tests/translate/test_close3_task_suppositions.py`). EVD-SRC-001 does not name
a task-authority premise that restates a supposition the task sets for the answer: one sentence of the task record that
opens with a supposition ("Assume that ...", "Suppose ...", "Imagine that ...", "Assuming that ...": the supposition mood
of `assertion.sentence_cue_at`) holds every content root of the premise's words (its symbols' meanings, else its label,
without the words that name an authority), with the premise's polarity (`diag_evidence._supposed_by_task`). Correct work
that takes the task's supposition as given was named `unchecked_source` at warning, where the committed base names
nothing. A plain restriction of the rule's trigger set: the grounding record is unchanged (the supposition is not
validated as a task fact, so the answer stays not releasable on it, as on the base), and a hedged, conditional or
reported task sentence, a supposition of something else and one of the opposite polarity still name the premise.

The authority rule behind issue 1 is `engine/authority.py`: only a record created by a check in this process confers task
or source authority, and for circularity too (`assumed_grounding` is `not has_authority`). What a check reads
(`translate/grounding.py`, `translate/stated_rules.py`):

- a located excerpt verifies a premise only when it states it: a literal; a conjunction of literals the excerpt states
  (the check `content_in_excerpt`: "Ash, Birch and Cedar each lost population"); or a rule the excerpt states as a
  conditional ("If X, Y", "Y if X"), a universal rule ("every firm with more than 50 employees") or a biconditional,
  side by side (a converse or another threshold is not stated). A premise that joins a located literal to the writer's
  own proposition stays unverified (`relation_in_source` names the connective as the writer's). A rule is stated only as
  the source's own (close round 1, ADV6-01; `stated_rules.rule_qualifier`): a hedge or another mood in its consequence
  ("may", "tends to", "usually", "would"), an "or" there, a part of its condition the premise drops ("and wages are
  frozen"), a frame before it (a clause ending in "that", "whether" or a verb of a view that holds a word of reported view,
  denial, doubt or scope: "Some politicians claim that", "It is a myth that", "Nobody has shown that", "Economists disagree
  about whether"; a short opening phrase of scope, "In some economies,"; a question), a restriction after it ("but only
  when", "unless") or an attribution tag naming no document ("..., some say") keeps it from being stated: the located
  excerpt then refutes the premise (`relation_in_source` False, EVD-SRC-003, `source_mismatch`), and a record sentence of it
  validates no task-authority rule. A hedge the consequent's own meaning holds, a restriction or a verb of a view the
  premise's own meaning writes ("every player except the goalkeeper gets a bonus"), a reason or an endorsing credit after the
  rule ("because ...", "as the report argues") and a negation in another coordinated clause qualify nothing;
- a quotation whose excerpt is located but does not state the premise (the point dressed as a quotation, a placeholder)
  is refused (`content_in_excerpt` False), and so is an excerpt about another entity or another quantity ("Southtown" for
  "Northtown", prices for wages, exports for imports), or about the opposite part of what is counted (repair round 3,
  fidelity-1 class beyond the year: "3 of the 12 games before the change" for the games after it,
  `grounding.OPPOSED_QUALIFIERS` read in the figure's subject and its clause). A conjunction is stated only when each
  conjunct is held, with its own polarity, by the excerpt's sentence or one of its clauses, and a clause may miss one of
  four or more words of a conjunct but never the word that tells it from the others ("Oak never lost leaves early,
  though beech lost leaves early" states no "oak lost leaves early": repair round 3, INV-5). A figure after "compared
  with" belongs to its own clause's subject (V3-FALSE-SRCMISMATCH-COMPARED), and a bound ("keep ... below 10%") states the
  figure of a symbol whose meaning names the bound (a ceiling, a limit, a target) and of no other (THRESHOLD). The subject words are read without units and scale words
  ("million", "per cent"), with hyphenated compounds and possessives split ("the test-retest correlation" shares "test"
  with "the test's", but a figure stated for another subject in the same clause, "0.0312 stated for significance", is
  another subject's figure), and an abbreviation whose letters are the initials of the subject's words ("PED" for "the
  price elasticity of demand", `grounding._initials_of`) names the same subject, not another (repair round 2). Within one
  sentence or one table line too (repair round 4, rerun-fidelity-1 same-sentence variant): when the premise's subject and
  the figure's share the quantity's words but each has a word the other lacks ("unemployment" against "inflation" when
  both say "rate"), and another figure of the record carries the premise's distinguishing words together with the shared
  ones, the figure is that other subject's and the premise is refused (`grounding._subject_conflict`; an owner the premise
  names that another figure's clause also holds, "the firm's", tells no quantity apart); and a figure stated for one month
  or day of the week ("Rainfall (mm): January 85; February 62") states nothing for another (`grounding._period_conflict`);
- a figureless task premise with no excerpt is validated by a task sentence that states it (`content_in_task`): as a
  rule, or as literals, each literal's meaning or the premise's label held with its polarity by one asserted sentence or
  clause of the task, or a label that spells the sentence's notation in words; a question, a hedged or suspended
  sentence and a condition state nothing (repair round 2), nor does a report of a view the answer is to weigh ("Many
  students claim ...", "It is often said that ...", "Critics described ... Evaluate this view."), unless the premise
  reports the same view (repair round 3, INV-1, INV-3). It is refuted when no task record holds its words, read from its
  label or its meanings; when one sentence the task states as a given holds its words in another order or with another
  polarity ("Germany caused the war" from "The Allies caused the war to end and made Germany pay": a misreading,
  `grounding._task_sentence_misread`); and when it is an "if", "iff" or "or" that no record states as a rule (its
  connective is the translation's own). An "or" the task states is a rule it states (repair round 4,
  FA-TASK-EITHER-OR-REFUTED; `stated_rules.disjunction_shape`, `stated_disjunction`): a disjunction of literals, or an
  exclusive one ("A or B but not both", written as an "or" with its "not both" or as "A iff not B"), is validated by an
  asserted task sentence that holds "or" between each option's distinct words, the options' shared words and each
  option's polarity, with a word of exclusion for an exclusive premise; a sentence that holds "or" between the options'
  words but in other shared words, or "either ... or" with no word of exclusion, leaves the premise unvalidated rather
  than refuted (`grounding._disjunction_near_records`). A task sentence restated with its pronoun resolved, in the
  passive, or with its modifiers moved states the premise (repair round 4, ADV4-06; `grounding._role_pattern`: the heads
  before and after the verb are read in active order, the modifiers after a preposition free). A figureless task premise
  that shares an atom with the point is never validated by a task sentence: it is left to the circularity rules (E112), as
  on the committed base (close round 2, REG-CIRC-TASK-PROPOSITION: the stricter reading repair round 4 gave it, ADV4-06,
  which made a premise the task states a transcription, also validated a proposition the task quotes for the student to
  weigh, "'X.' Discuss.", so 'X, as the question states; therefore X' cleared; reverted under the round's convergence
  rule). A unit conversion the task gives, even
  inside an instruction's parenthesis ("(take 1 month = 30 days)", "a year has 365 days"), validates the premise that
  applies it (repair round 4, E2E-MAA; `relations.stated_conversion`). These restore the refutations made before repair round 2 (repair round 3,
  INV-3: no check is weakened). It is unvalidated otherwise (a paraphrase whose words the records hold only across
  sentences); a premise that is the point itself is left to the circularity rules. A rule premise with no excerpt is
  validated only by a sentence the task states as a given, never by a question or a supposition (INV-2). A sentence that
  holds the premise's words with another time ("next year", "this year" for "last year"), another tense ("will raise" for
  "raised") or the opposite direction of change ("cut" for "raised": a closed table of verbs of rise and fall) does not
  state it: the premise is refuted (`content_in_task` False; close round 1, INV7-1, `grounding._task_conflict`), and a time
  the premise dates that the sentence does not date leaves it unvalidated. Deictics that point to one time ("the past year",
  "the previous year" and "last year") are no conflict. The month "May" written with a capital inside a
  task sentence is no modal (close round 1, ADV6-09, `grounding._suspending_tokens`);
- a figure is read with its whole unit, a unit of two or three words included ("21 m³ s⁻¹", "4200 J kg⁻¹ K⁻¹": the
  longest reading first; repair round 2, `translate/quantities.py`);
- a figure grounds when the excerpts state it, when the answer's own written calculation derived it (the claim, its
  supporting claims and the report's original response are read: `check_problem_grounding(..., answer_texts=...)`; the
  calculation must give the figure, exactly or rounded to its last place, by the closed reader of written arithmetic,
  so "£5.00 − £3.00 = £2.50" derives nothing), or when it is the divisor of a mean of stated addends; a dated change
  ("fell from 42% in 2014 to 18% in 2024") states each of its figures, a range states none. A figure a record's list
  gives grounds too (repair round 4, E2E-BI, E2E-CS; `grounding._aggregate_source`): the count of the list's figures for
  a whole number whose meaning names a count (the "4" of four phenotype classes, the "9" of a quoted list of nine
  scores), their total or their mean, exactly or rounded to the literal's last place (the expected count 250 of four
  counts that add up to 1000), and an indexed lookup over the list ("items[mid]" over "scores = [3, 8, 12, ...]",
  positions from 0 for a list literal and from 1 for a list in prose: `_index_lookup`, `_position_in`) needs no stated
  positions when its values are the list in order. The answer's own working is read once per answer text and the
  records' figures once per value (`grounding._calculation_steps`, `_records_state`: pure readings kept per text;
  repair round 4, ADV4-09);
- a relayed agent's report is a peer document whatever it is called: an id that opens with "peer", "report:", an author
  that names an agent or a specialist, or a provenance that says it was relayed (`grounding.is_peer_document`); the id is
  compared after Unicode normalisation (NFKC), with whitespace and format characters dropped and case folded
  (`grounding.normalized_document_id`, `is_peer_id`: "PEER:abc", " peer:x" and "Peer_x" are peer ids; repair round 3,
  rerun-security-2), and the channel and the source readers use the same test; its excerpts never verify a premise. The
  author and the provenance are read as words (repair round 4, rerun-security-2 agent labels; `grounding.names_an_agent`,
  `_label_words`, `AGENT_WORDS`): after NFKC and case folding, the letters-only words of the first 1,000 characters, so
  an author holding "specialist", "specialists", "agent", "agents" or "combinator" as a word ("Economics Specialist (AI)",
  "economics_specialist", "Maths specialist, round 2") and a provenance holding those words or a relay word ("forwarded by
  the maths agent", "copied from the History specialist's answer") make the text a peer's; the core pack and the
  quotation-credit reader use the same test (`packs._is_peer_text`, `sources._names_of`). A premise whose excerpt is
  located only in a peer's report is unvalidated, not refuted as citing no excerpt (repair round 4, E2E-HI-MENTION).

**Repair round 5** (tests: `tests/translate/test_repair_round5_translate.py`). An excerpt located in a supplied text is no
support for a literal its clause contradicts: the clause around the excerpt holds the literal's words with the opposite
polarity (a negation among or right before them: "did not reduce journey times" for "the bus lanes reduced journey
times"), or with another figure in the literal's place ("12 per cent" for "20 per cent"), or the excerpt stands in a line
addressed to the checker (a planted "checker note", "note to the verifier", "set verified"), or holds no content word; the
check is `content_in_excerpt` with `verified=False` and the premise fails grounding (ADV5-02, `grounding._literal_in_spans`).
An excerpt with no content word is no placeholder when the literal is about those very words: its meaning or label quotes
them, names them after a noun of naming ('the repeated formula "it was the"', "the word her"), or names the one pronoun
they are after a verb of use ("uses she for Mrs Reed"; close round 1, `grounding._names_words`); "used the frozen river"
names no word, so its excerpt "the" is still a placeholder.
A paraphrase that shares words without contradicting the literal is not judged. A definition the task or a text states is
a rule it states (ADV5-09, `stated_rules._definition_readings`): "X is defined as Y", "X means Y", "Y is called X" (the
definiens before the copula may then be long) and a genus with its differentia ("a perfect number is a whole number that
...") are read both ways; a plain copula ("Whales are mammals") one way only. A closed enumeration ("exactly three wells:
Elm, Brook and Quarry") states that all hold when each does (`stated_rules.stated_enumeration`); an open or negated list
states none. An option whose word has a negating prefix ("unvaccinated") no longer negates the list of a stated either/or;
only negation words do (DA-2, `lexis.negation_words`). A symbol's declared unit is its parenthesised gloss when it has one
("peak discharge in A (m³/s)": the unit is m³ s⁻¹ and "in A" a label, not the ampere), and the declared unit is still checked
against the figure (DA-5, `quantities.declared_reading`). An excerpt that gives several quantities their figures (a list,
a comma-cut qualifier, a table row with its header) grounds a premise only with the figure of its own quantity
(rerun-fidelity-1, `grounding._subject_conflict`, `_table_cell`). Another figure of the same value and unit, and a figure
stated for the opposite part ("After the tax" for a premise about the price before it), give the premise's quantity no
other figure (close round 1, arena run1 ec-e1: a table repeating "$1.60" refuted the excerpt that states it). A relayed agent's text is a peer document, never a
primary source, under the labels "relay:", "rep-", an author that names an AI system ("AI tutor", "ChatGPT", "chatbot") or
the router (rerun-security-2, `grounding.is_peer_document`, `names_an_ai_system`); a person's name such as "Claude Monet" is
no AI author.

### 3.3 Quotations, attributions and figures that existing codes name

These labels are carried by existing finding codes through `named.DEFECT_OF_CODE` (first matching row wins):

| Label | Codes | Example | Control |
| --- | --- | --- | --- |
| `altered_quotation` | INT-REQ-003, ES-SRC-001, CORE-SRC-001, GEN-SRC-001 whose message says "altered" | e03 ('indifferent' for 'unfeeling') | c04-eng, c02-hist |
| `source_mismatch` | INT-REQ-003, ES/CORE/GEN-SRC-001 otherwise; CORE-SRC-005, ES-SRC-008 (credited to the wrong text), INT-LEDGER-025 (an evidence reference the named text does not hold), INT-REQ-015; CORE-SRC-007 when the table states the figure for another year | e04b (a Source B quotation credited to Source A); "Unemployment in Country P was 8.9% in 2019." against a table giving 6.4 for 2019 and 8.9 for 2020 | c04-eng; the table's own figure, rounded ("about 9% in 2020") or in another scale ("1,900,000" for 1.9 million) |
| `invented_figure` | CORE-SRC-007 (warning) whose message ends "for no year": a figure the answer states for a year of a supplied data table (a text of three or more "YEAR: value" lines, which the request or the sentence names by its title: "Using Table 1", "According to Figure 2") that the table states for no year, in a clause about the table's quantity (a word of its title, or only trend words); a change ("rose by 2.5 points") is no level and is not read. Repair round 4, ADV4-12 (`branches/packs.py`, `table_figure_mismatches`); it reads the delivered report, so it names the figure whether or not the claim is translated | "then rose sharply to 11.4% in 2020" against a table whose figures for 2015 to 2021 hold no 11.4 (`tests/branches/test_repair_round4_table_figures.py`) | the table's figures; a figure of another quantity in its own clause; a change; a year the table does not hold; a table nothing names |
| `unchecked_source` | CORE-SRC-003 (unverifiable quotation), CORE-SELF-001 (self-certification) | e08a | c04-quote |
| `lack_of_evidence` | CORE-SRC-002, HI-SRC-004 | e07 | i00 |
| `uncheckable_authority` | PS-SRC-001, HI-SRC-003 | e05b (a named study no supplied text holds) | c03-psych |
| `contradiction` | INT-REQ-007, INT-CONFLICT-001, INT-CONFLICT-005 | f05 | c05-chem |
| `stem_dimension_error` | ST-DIM-001, ST-DIM-002 | s03c | s00 |
| `stem_symbol_conflict` | ST-SCOPE-001 (info) | s06, f05b | s06c |

A quoted span is checked as a quotation unless a closed frame gives it another role (`adapters.markdown`,
`_span_roles`), and the correction and suggestion roles are read only in a task whose type is a marking, feedback,
correction, proofreading, redrafting or editing task (repair round 4, INV-Q1; `markdown.FEEDBACK_TASK_RE`,
`corrections_apply`). The channel sets the plan's task type around every parse and pack run of a delivery
(`markdown.quotation_task(..., authoritative=True)`), so a report cannot widen the roles by naming another task type of
its own; a parser, pack or rule called on its own reads the task type it was given, and with no task known no correction
or suggestion role is read. In such a task, the corrected form after an arrow, a correction label ("correct form:",
"correction:"), a feedback frame with no original before it ("it should read", "the corrected sentence is", "a better
version would be", "rewrite it as", "becomes"), a correction in words after an original span ('"x" should be "y"', '"x"
becomes "y"', 'change "x" to "y"', 'replace "x" with "y"', 'Not "x" but "y"'), what a correction gives (', giving
"..."'), or a span that directly follows a "Model:", "Corrected:" or "Better:" label is a correction; a span after "you
could write", "instead write" or an imperative "write", "use", "say", "put", "choose", "try" or "add" at the start of a
clause, or on a "Suggestion:" line, is a suggestion (repair round 4, ADV4-04). A frame whose subject is a quotation of a
text ('the last quotation should read "..."', 'the poem's exact words are "..."': `_QUOTATION_SUBJECT_RE`) prescribes the
text's words, so its span stays a quotation and is checked even there. In any other task (a literary analysis, a source
analysis, an essay) every such span stays a quotation and is checked, so an altered quotation framed by an arrow, a
"Model:" label, an imperative, 'Not "x" but "y"' or '"x" should be "y"' is still named. A mention is read in every task:
a quoted function word of the closed list, a connective a naming frame names ('the word "although"', 'the connective
"however"'), a span after a frame that says the text does not use the words ("never uses", "does not use", "avoids",
"omits", "leaves out", "could have used", "chose not to use", "instead of using": repair round 4, ADV4-03), a negated
report ('It does not say that the plan has "failed"'), or a short span after a negating frame (`without "like" or "as"`);
none is an invented quotation (end-to-end B5, B6; y01). A bare quoted connective may cite the text and stays a
quotation, and a span the writer credits to a text, before it or with a citation after it, is checked in every task
(`tests/adapters/test_quotation_roles.py`, `tests/adapters/test_repair_round4_quotations.py`).
A quotation's excerpt is compared without the punctuation the writer put inside the closing mark (`"... too long."`), in
the History, generic and STEM parsers as in English.

A quotation is credited to a supplied text by its author, its surname, its title, a proper name in its title's
parenthetical ("The Northern Courier reports" for "Plastic waste rising (newspaper article, The Northern Courier,
2021)"), or the kind of text its title names, with up to three words before the kind ("the newspaper", "the bread price
table"), and by a showing verb as well as a reporting one ("Source B shows", "indicates", "demonstrates", "highlights",
"reveals": `adapters.sources._CREDIT_VERBS`), so a specialist's words credited that way are INT-LEDGER-025 in a
synthesis and a wrong credit in a report (`adapters.sources.quotation_credit`; `tests/adapters/test_credit_by_title.py`,
`tests/integrity/test_repair_round2_credit.py`). When no credit stands before the quotation, a credit after its closing
mark is read (repair round 4, rerun-combinator-faults-5; `sources._credit_after`): a name and a crediting verb ('"...",
the leaflet says.'), the inverted form ('"...", says the leaflet.'), "according to" ('"...", according to the leaflet.'),
"as X put it" and a bracketed citation that names one text ('"..." (Churchill, 1940)'); the kinds of text the titles
name count as crediting nouns. INT-LEDGER-029 names a synthesis that states a verification status ("All
checks passed.", the self-certification vocabulary of the reports) or a check result in either polarity with the checks
of the process or of a report as its subject ("the Mathematics report's own checks flag its written lines ... as not
holding": `integrity.ledger._CHECK_STATUS_RE`; `tests/integrity/test_ledger_check_status.py`). The self-certification
vocabulary (CORE-SELF-001, `adapters.markdown`) reads status lines ("Verification: passed."), automated, proof and
symbolic checkers, provers and validators ("confirmed correct by the engine", "the calculations passed the checker"),
and "proven correct", "certified correct", "mathematically verified" (`tests/adapters/test_repair_round2_self_certification.py`,
with 20 argument controls that use the same words about the subject). Repair round 4 (rerun-combinator-faults-3) adds
the short and symbolic forms (`markdown.SELF_CERT_RE`): "all steps (calculations, figures, results, ...) checked", a
sentence that is only a check participle ("Formally verified ✓", "Fully checked."), a status line opening a sentence
("Status: VALID."), and the answer itself as the subject of a passed check ("This answer has passed every quality
check."). A figure's sign is read the same whatever its glyph:
the minus sign U+2212, the small and full-width hyphen-minus, and a hyphen or en dash in a sign's place sign it as the
ASCII hyphen-minus does, and a fall stated in words ("fell 12.50%") restates the signed figure, so a synthesis that drops
a source figure's sign is a change (INT-LEDGER-023) in every spelling, while a range or a difference written with a dash
is no sign (`tests/integrity/test_repair_round2_figures.py`). One figure in two notations is one figure (repair round 4,
rerun-combinator-faults-8; `integrity/ledger.py`): decimals grouped by spaces ("0.000 42", "1.138 429…"), thousands
grouped by apostrophes ("12'500"), a power of ten written "10^(−3)", "10^{-3}" or "10^-3", a unit's caret exponent
("dm^-3") that is no figure, and a minus spaced after a relation sign or a bracket. A synthesis that keeps a source's
words around a figure keeps its statement (repair round 4, rerun-combinator-faults-7; `ledger._copied_with_context`): a
figure or month swap is charged only when the words before and after it in the synthesis are not a statement of the
cited sources, and the rows of a truth table are read against the source's table cells (`ledger._bits_in_cells`).

**Repair round 5** (tests: `tests/adapters/test_repair_round5_quotations.py`, `tests/integrity/test_repair_round5_ledger.py`,
`tests/service/test_repair_round5_cli.py`, `tests/contract/test_quotation_stub.py`). Mentions: a word the writer quotes as one
the text does NOT use is a mention in every everyday frame (ADV5-08): an example offered with an indefinite article ("a
gentle word such as 'leaned'"), "unlike" (reverted by close round 2: a span after a contrast is checked again), a verb
phrase the writer negates ('do not "crash"', 'is not "afraid"') and a
reporting verb under a negation ('never writes "roared"', 'the text never says "ayudar"'; reverted by close round 3: a span
right after a negated reporting verb is checked again); a word credited to the text, a
plural or definite example ('violent verbs such as "smashed"') and a contrast ('Not "bent" but "bend"') stay quotations.
Quotation roles in a task: the task type a record states about itself (a report's or a claim's own `task_type`) is
advisory and never widens the roles (INV-QROLE-1, `markdown.quotation_task(..., advisory=True)` in
`diag_core.claim_diagnostics`, `report_diagnostics` and `branches.base.run_packs`); the channel's plan and a caller that
states the task (`check-report --task-type`, or an envelope's `task_type`) still read correction frames in a feedback task.
The ledger (combinator readings): a figure is excused as copied context only when the source states the whole synthesized
run back to the start of its sentence, so a swap between parallel statements whose telling word stands far before the
figure is charged INT-LEDGER-023 (`ledger._copied_with_context`, `context_swaps`); a step label written as a numeral for the
source's ordinal ("Trial 1" for "the first trial") is the same label (`ledger.step_labels`); accounting parentheses for a
negative money amount ("(2,400.50)") and a precision note ("(2 s.f.)") are notations, not figures; short status forms are
self-certification (a check mark with a verdict, "QA: passed", "Correctness guaranteed.", "(Checked.)", "Result: correct.",
"This has been reviewed and approved.", the hub or the router finding no problems), and a word-count line ("Word count:
52", "(48 words)") is a measurement, never INT-LEDGER-029 (ADV5-12); a quotation credited by "As X puts it:", "In X's words,",
'"..." — X.', "X:" opening a sentence or the author's role ("The President declares that") is credited to that text
(`sources.quotation_credit`).

**Close round 1** (section 12; tests: `tests/adapters/test_close1_quotation_roles.py`,
`tests/adapters/test_close1_selfcert_linear.py`, `tests/integrity/test_close1_ledger.py`). The negated-verb frame of repair
round 5 is a mention only for one quoted word ('the speaker is not "afraid"'); a longer span after a negated verb is a
quotation and is checked against the texts ('The willows are not "bowed by grief"'), and a credit to a source right after a
span (", as the chronicle claims", "(as the poet puts it)": `markdown._CREDIT_AFTER_RE`) keeps it a quotation whatever frame
stands before it (rerun-verify6-weakened-negated-quotation-mention). The status forms of `markdown.SELF_CERT_RE` that
repair rounds 1 to 5 added are read in linear time: every whitespace run is consumed once (possessive quantifiers, an
optional bracket or mark read with its own run) and the list of an elliptical status ("Checked and signed off by the
overseer.") is read as words and separators, each consumed once; the pattern gives the old answer on every string (a
differential check of 900,000 random strings of its vocabulary), and "Verified" followed by 60,000 spaces is read well
under a second (ADV6-08, rerun-verify6-parser-safety-3-regression-selfcert). In the ledger, a figure whose words after it,
to the end of its clause, are a source's own statement of that same figure keeps its statement: a summary that skips an
intermediate figure ("from 2.6 per cent ... in May 1928 to 37.3 per cent and 230 seats in July 1932") is no swap
(`ledger._states_own_figure`; arena r1 hi-t1), while a figure spliced into another statement's words is still
INT-LEDGER-023.

**Close round 2** (section 13; tests: `tests/adapters/test_close2_quotation_roles.py`). The quotation-role reader reads a
text in linear time (SEC-QROLE-QUADRATIC): the line starts, the sentence marks of each line and the label heads are read
once (`markdown._LineIndex`; a label governs a span when nothing but spaces and markup stands between its colon and the
span), an earlier correction on a span's line is known from the end of the last correction span, the gap patterns between
two spans consume each run of spaces and markup once (possessive quantifiers), and one answer's roles are read once however
many readers ask (`markdown._roles_cached`). The roles are the old reader's: a differential check over random label lines
and over the role lists of the generated texts gave the same answer on every input. A span after a contrast ("unlike",
"rather than", "instead of") is a quotation again and is checked, as on the committed base (DIFF-02): what a contrast sets
aside is as often the text's own words as words the text does not use, and the mention read there hid an invented
quotation presented as the text's own; the frames that say the words are absent ("without", "with no", "no") keep their
mentions.

**Close round 3** (section 14; tests: `tests/adapters/test_close3_quotation_roles.py`,
`tests/integrity/test_close3_ledger_linear.py`, `tests/integrity/test_close3_joint_memo.py`). A span right after a reporting
verb under a negation is an attribution like any other, so it is a quotation and is checked, as on the committed base
(INV-QR-1): the repair round 5 reading made it a mention with one word allowed between the negation and the verb, so 'not
only writes "..."', 'does not just say "..."' and 'not only says "..."', which affirm the attribution, took an invented
quotation out of the checks. The mention frames of repair round 5 had been narrowed by close round 1, so the reading is
reverted for its whole class (`markdown._NEGATED_ATTRIBUTION_RE` is gone); a negated report with words between its verb and
the span ('It does not say that the plan has "failed"', 'never calls it "a success"': `_MENTION_NEGATED_REPORT_RE`, repair
round 1) keeps its mention, and the core pack's own absent-word reading still keeps 'never says "x"' out of CORE-SRC-003.
The synthesis ledger's figure readers are linear in the two texts and give the old answers (DV2-06): the copied-context
swap reader indexes the places of every run of four source tokens and of every source figure with the words after it once,
extends a run one token at a time on demand and reads once what follows every place of a run (`ledger._RunPlaces`), skips
a figure with fewer than two content words before it, and keeps one reading per sequence of preceding tokens; the figure
index keeps one answer per set of spellings and per figure as written (`_FigureIndex.spelled`, `carries`); the aligned
reading is kept per pair of texts (`aligned_differences`, read twice for one synthesized claim). A differential check of
the 786 ledger inputs of every arena round and their swap, repetition and hostile variants gave the same answers. The
cross-report consistency check keeps a definitive joint result per identical joint problem, configuration, limits and
signing key (`cross_check.verify`, DV2-07), so a contradiction named on one transmission is not attributed again from the
start on every later one; an undecided result is decided again.

### 3.4 STEM method (stem layer and the closed STEM reference)

The closed reference (`stem/reference_data.py`, read by `stem/reference.py`) holds 79 symbol entries (profile, quantity,
dimension, SI unit, ambiguity), 15 formulas and 102 data-booklet laws (the physics, chemistry, biology, sports science,
Environmental Systems and Societies and mathematics laws of the data booklets, each a law of one quantity, read by the
front end as exact data; repair round 2 added the Lincoln index of a capture-mark-recapture estimate, a dilution,
c₁V₁ = c₂V₂, solved for each of its symbols, and physics pressure, p or P = F/A, which shares its letters with momentum
and power and so is fixed only by its result's unit or the request). A symbol's quantity is fixed only when it is unambiguous in the profile,
decided by its result's unit or named by the request, and the dimension guard agrees; otherwise no ST-REF code can follow
(a miss, never a false alarm). Tests: `tests/stem/test_reference_formulas.py`, `tests/stem/test_units_symbolic.py`,
`tests/stem/test_steps_operations.py`, `tests/stem/test_rounding_range_working.py`, `tests/stem/test_givens_symbols.py`,
`tests/stem/test_repair_round1_variants.py`, `tests/stem/test_repair_round2_stem.py`, `tests/stem/test_repair_round2_layouts.py`,
`tests/stem/test_repair_round2_classes.py`
and the STEM cases of `tests/data/repair_round1_cases.json` (t, u and w).

Three of the codes are the codes of engine-decided checks rather than findings: ST-UNIT-003 (the `u` companion of an
`eq` or `sub` check, `stem-<kind>-<n>u`), ST-STEP-001 (the `op` check) and ST-ROUND-001 (the `rnd` check). Each is planned
with its defect, and its failure reaches the receipt as INT-SUBJ-001 (error: the check rested only on what the report
states) or INT-SUBJ-004 (warning: it relied on a reading the report did not state) carrying that defect. The other STEM
codes are findings of the front end.

| Label | Code (sev) | How it is derived | Appears as | Example | Control |
| --- | --- | --- | --- | --- | --- |
| `stem_wrong_formula` | ST-REF-001 (warning) | the answer's law for a symbol whose quantity is fixed has a right-hand dimension, coefficients dropped, other than that quantity's; the booklet formula is named. Only a pure coefficient is dropped (a small integer or a simple fraction: a decimal, a figure in scientific notation or a value equal to a stated quantity is a fitted constant with a unit, so a fitted law such as v = 1.5t names nothing). The dimension of a result also follows from the final line of its chain and from the request's quantity for a substituted numeral. A symbol on both sides makes an equation, not a law. Sciences profiles only | ST-REF-001 | s02, s02b (E_k = ½mv), t01 to t05, w10 (P = IR), w12 (an inverted pendulum ratio), w14 (v = f/λ); "P = F × A = 600 × 0.30 = 180 Pa" for a pressure | s00 (E_k = ½mv²); an ambiguous p with no unit; u10, w01 to w03 (fitted laws); w11, w13, w15; "F = k x" read whole, not as "F = k"; "P = F/A", "P = W/t = 5.0 W", "p = mv = 6.0 kg m/s" |
| `stem_wrong_formula` | ST-REF-002 (warning) | the answer's law has exactly the variables of the booklet laws for its quantity, with the dimension they give, and differs from each of them as a function: interval enclosures of both sides at two sample points of the variables do not meet (a dropped coefficient, which ST-REF-001 cannot see). A word equation is read as the formula it spells ("kinetic energy = 0.5 × mass × speed²": `stem/word_formulas.py`, through the reference quantities' names) | ST-REF-002 | E_k = mv² (the ½ dropped); "kinetic energy = mass × speed²"; N = MR/C (an inverted Lincoln index); c₂ = c₁V₂/V₁ (an inverted dilution) | E_k = ½mv²; the correct word equation; N = MC/R; c₂ = c₁V₁/V₂ |
| `stem_unit_error` | ST-UNIT-003, written (warning) | both sides carry units of one dimension with different factors, or a per cent sign converts one side only; the companion fails exactly when the numbers hold as written and fail in SI | INT-SUBJ-001 | s03b (2.5 km / 10 min = 0.25 m s⁻¹), s03d | s03k, s03dk |
| `stem_unit_error` | ST-UNIT-003, traced (warning) | the working's bare numbers repeat the numbers of bindings stated in non-SI units (d = 2.5 km, t = 10 min, then v = 2.5/10 = 0.25 m s⁻¹), or of quantities the request states with their units (a volume in cm³ used as dm³); each is read in its binding's unit. A unitless binding (a magnification) is dimensionless as written, and a bare ratio of one kind of quantity given in two units (I = 40 mm, A = 20 µm, M = I/A = 40/20 = 2) is read in them. The law's coefficients count as accounted for when the law stands on a line of its own ("E = ½kx²", then "E = ½ × 250 × 4.0² = 2000 J" with x given as 4.0 cm), and a computation set out over lines is one chain (below). A bare stated result whose unit the prose gives in the same or the next statement ("= 5000. The elastic potential energy stored is 5000 J.") is read in that unit (`relations._prose_unit_of`; repair round 2). A number the substitution introduces for a symbol bound nowhere else ("ΔEp = mgΔh = 250 × 9.8 × 2.0" with only g bound) is traced too, to the request's quantity with that number (a mass of 250 g, a current of 300 mA) | INT-SUBJ-004 | s03a, t06, t08, w08, w16; the spring and magnification cases of the round 2 tests; the 250 g and 300 mA substitutions of `test_repair_round2_classes.py` | s03k, u05, u06, w17; the same working with 0.040 m; "0.250 × 9.8 × 2.0", "0.300 × 20" |
| `stem_dimension_error` | ST-DIM-001, ST-DIM-002 (warning; existing codes) | the two sides of a relation, or the terms of a sum, have different dimensions | ST-DIM-001, ST-DIM-002 | s03c (momentum labelled J) | s00 |
| `stem_arithmetic_slip` | the arithmetic checks (`eq`, `sub`, `res` and the other arithmetic kinds) | the engine decides the written arithmetic against the stated value under the STEM tolerance rule; a failure is labelled by the check's own `defect`, else by its kind (`named.DEFECT_OF_CHECK_KIND`: a conversion names `stem_unit_error`, an algebra step `stem_invalid_step`, a given `stem_contradictory_givens`, a comparison, target or balance nothing, every other STEM or arithmetic kind `stem_arithmetic_slip`). A computation set out over lines is checked as the chain it spells: a line that states a value for the symbol heading the line before, whose computation that line left unevaluated ("v = 8.4 / 2.0", then "v = 5.2 m/s"), continues it as "= 5.2 m/s" would, in the same part and at most two statements on; a product of quantity letters written with spaces ("E = ½ k x²", "F = k x") is read as the product (`stem/spans.py`). A 0-and-1 numeral the request or the answer calls a two's complement number is read with its leading digit weighing −2ⁿ⁻¹, and a Boolean evaluation chain ("NOT (A AND B) = NOT (1 AND 0) = NOT 0 = 1") is checked link by link, at most 16 links (repair round 2) | INT-SUBJ-001, INT-SUBJ-004 | s01 (0.5 × 2.0 × 3.0² = 18); "v = 8.4 / 2.0", then "v = 5.2 m/s"; "11010011 = −128 + 64 + 16 + 2 + 1 = −47"; "NOT (1 AND 0) = NOT 1 = 0" | s00; the same lines with 4.2 m/s; another part or another symbol continues nothing; "So E = 5 k." (a bare letter after a number) is not read; "= −45"; "NOT (1 AND 0) = NOT 0 = 1" |
| `stem_invalid_step` | ST-STEP-001 (warning) | the operation the prose states for a step ("adding 4 to both sides", "Dividing by x,"), applied to each side of the previous line, must give the next line for every value of the unknowns (an identity decided by the engine); exactly one stated operation is read, and the first step may start from the request's one equation. A rearrangement substituted with the task's values ("V = IR, so R = 6.0 / 0.50 = 12 Ω") binds its symbols to the request's quantities of their reference dimension, so it is a valid step, while a wrong rearrangement still fails | INT-SUBJ-004 | s05 (x/4 = 2, "adding 4 to both sides", x = 8), t10, t11; "R = 0.50 / 6.0" | s05c, u08, u09; "V = IR, so R = 6.0 / 0.50 = 12 Ω" |
| `stem_invalid_step` | ST-STEP-003 (warning) | a rewrite inside a chain (repair round 3, V3-H2-STEM-MISSES) is no identity: the two sides of an equals sign between two expressions of the unknown, both with the same unbound symbols and with a further link after them, differ at a sample point of the unknown, decided by rational interval enclosures that do not meet (`stem/reference.difference_witness`; `relations._false_rewrite`) | ST-STEP-003 | "log₁₀ x + log₁₀ 2 = log₁₀(x + 2) = 1" | "log₁₀ x + log₁₀ 2 = log₁₀(2x) = 1"; "(x + 3)² = x² + 6x + 9" (`tests/stem/test_repair_round3_stem.py`) |
| `stem_invalid_step` | ST-STEP-002 (info) | a step divides by an expression of the unknown with no `≠ 0` stated, the division written as "Dividing by x" or as a cancellation ("Cancelling x,", "cancelling a factor of x": repair round 3, rerun-stem-soundness-11); the step's own check, or the root check, decides whether the solution sets differ | ST-STEP-002 | x² = 3x, then "Dividing both sides by x: x = 3"; "x² = 5x / Cancelling x, x = 5" | the same with `(x ≠ 0)` stated; the factorised working that keeps both roots |
| `stem_rounding_changes_conclusion` | ST-ROUND-001 (warning) | a comparison with a threshold, or a statement that a value meets or misses a target, uses a value the working itself rounded (repair round 3, ADV3-09: also a comparison written with the rounded value's symbol, "5.97 ≈ 6.0 Ω. R is not below 6.0 Ω", `relations._symbol_prose_comparisons`); it must keep its truth with the value before the rounding. The rounding may be a chain's "≈" or stated in words ("which is 0.7 to one s.f.", "To 1 s.f. this is 80%"); the comparison may be in prose, in symbols ("so η ≥ 0.70"), a clause after the rounded value, or a target clause ("so the target of at least 80% is met", "which meets the target", "falls short of the target": `TARGET_NOUNS` and the reach, exceed and miss verbs of `stem/reference_data.py`), the target's value read from the clause or, when the clause states none, the one value the request states beside a target noun or later in that noun's sentence ("meets the standard only if its efficiency is at least 70%"). Repair round 2 also reads the rounded value restated at the start of the next sentence ("≈ 90%. The yield is 90%, so the batch passes ..."), a value glued into the target's noun phrase ("the above-90% requirement", "the at-least-70% standard"), the nouns standard, criterion, cut-off and quota, and a strict bound equal to the rounded value read inclusively. The condition a request sets on a value is a target too: a predicate made conditional ("The method is acceptable only if the mean titre is at least 24.45 cm³", "provided that", "as long as"), when the clause after the rounded value asserts or denies that predicate ("so the method is acceptable", "so the bridge is not safe", "unsafe"). A chain that writes its unit or per cent sign once, after the rounded value ("= 24.447 ≈ 24.45 cm³"), has the value before the rounding in that unit too, when it is within a tenth of the rounded value as written | INT-SUBJ-004 | s04 (a mean of 0.2457 s written 0.246 s ≈ 0.25 s, then "not less than 0.25 s"); "78.96% ≈ 80%, which meets the target" (a target of at least 80%); "24.447 ≈ 24.45 cm³, so the method is acceptable" | s04c; "82.4% ≈ 82%, so the target of at least 80% is met"; "78.96%, which is below 80%, so the target is not met" (nothing rounded); "24.447 ≈ 24.4 cm³, so the method is not acceptable"; "= 0.7896 ≈ 79%, so the target is not met" (a conversion in the rounding step) |
| `stem_extrapolation` | ST-RANGE-001 (warning; repair round 3: a fitted line the request states with the range of its input, used outside that range, is named in every subject, Geography included, through the core pack's request reading `branches/packs.request_model_extrapolation`) | a model the answer states (a law, or a binding near the evaluation) is evaluated outside [min, max] of a series the request gives (three or more values of one quantity in one unit, a list that writes its unit once, "at 10, 20 and 30 °C", included; years only from the request's data statements), at a value stated in a binding, a condition ("At t = 12 min") or the prose, with no caveat; a caveat under a negation ("this is not unreliable") is none. A law whose head carries a subscript digit (CO₂) is a law, and a trend stepped in arithmetic past the data ("each decade adds 15 ppm, so in 2100 ...") is evaluated too. Sciences profiles; in Mathematics only a dated series is data: two or more years the request dates with a time word ("in 2010", "from 2010 to 2020", "between 2018 and 2021", a year range), so an amount of money or the terms of a sequence are never years. A model the request itself states, with the range of its input in words ("hours of practice h (from 1 to 8 hours) ... s = 6.5h + 30"), substituted outside that range is named in any STEM profile (`relations._request_law_ranges`) | ST-RANGE-001 | s07 (a fit on 10–30 °C used at 60 °C), t12, w05, w06, g02, g02b; the CO₂ and stepped-trend cases of `test_repair_round2_stem.py`; the regression line at 20 hours, a population from 2010 and 2020 estimated for 2060 | s07c (interpolation), u10, w04; u11 (a caveat); the line at 5 hours; the population in 2015; compound interest on 1000 dollars |
| `stem_missing_working` | ST-WORK-001 (warning) | the request asks for working ("show your working", or a calculate, determine or show item worth two or more marks) and the answer states one result with no formula, substitution or working line (a value binding such as "x = 5." is working; a check built from the request's own givens or target is not). Computer Science only when the request asks for the method in words ("showing your method", `reference_data.WORKING_CUES`); a "Show that" answered with the result alone, whose values are all the request's numerals, is missing working (repair round 3, V3-H2) | ST-WORK-001 | s08, t14; a bare "−54" for a two's complement conversion "showing your method"; "The curve has a local minimum at (1, −2)." for a "Show that" | s08c, u07; the conversion worked; the request with no method asked; the derivative and second-derivative test written |
| `stem_contradictory_givens` | ST-GIVEN-002 (warning) | a symbol of a Given or Data statement is bound again to another value in the same part, with no new symbol, and a later substitution uses it; or a given value lies outside the enclosure of the value the working computes for it from the other givens (its decimal width taken into account); or (repair round 2) a symbol the answer binds twice in one part, with nothing saying which object either value is about, to the value the request states and to one it does not, and a later substitution, written as a pair or inside an evaluation, uses the second (`relations._unlabelled_rebindings`) | ST-GIVEN-002 | f05b (m = 2.0 kg given, later m = 3.0 kg used), t15, w18; "t = 3.0 s, and t = 2.0 s. a = (v − u)/t = 6.0 / 2.0" for a request that gives 3.0 s | c06-givens; a rebinding in part (b); the request's own time used; two times the request both states |
| `stem_contradictory_givens` | ST-GIVEN-004 (warning) | (repair round 3, ADV3-09) the givens of a definition law of the reference contradict it (`reference_data.DEFINITION_GIVENS_LAWS`: ρ = m/V with the answer's ρ, V and m), and a uniform motion's givens are read against every motion law they fix; or the values the answer states fix every variable of a law of uniform motion (v = u + at, s = ut + ½at², s = ½(u + v)t), the request or the answer says the motion is uniform or is a free fall ("dropped", "falls freely", "released from rest", "under gravity", unless air resistance, drag or friction is said to act and not to be neglected), and the law fails beyond the stated values' rounding and 2% (outside Mathematics and Computer Science); or the request's counts of two sets in one sentence (a total, each set, both, neither) do not add up and the answer computes with them. Silent when the answer says the givens disagree (repair round 2, `relations._overdetermined_givens`, `_set_counts`) | ST-GIVEN-004 | "from rest at 2.0 m s⁻² for 5.0 s, reaching 12 m s⁻¹"; "a stone is dropped from rest and falls for 2.0 s, reaching 25 m/s"; 50 + 45 − 15 + 5 = 85 members of a club of 90 | the same with 10 m s⁻¹ or 19.6 m/s; a skydiver against air resistance; an answer that says the values are inconsistent; counts that add up |
| `stem_contradictory_givens` | ST-GIVEN-003 (warning) | a probability stated outside [0, 1], or events the answer treats as mutually exclusive or independent against the request's own joint figures | ST-GIVEN-003 | a probability given against the task's intersection | an addition-rule answer that uses the stated intersection |
| `stem_symbol_conflict` | ST-SCOPE-002 (warning) | one symbol is bound in one part to two values whose noun phrases name different quantities ("the car's speed", "the speed of sound", or one object and another by an ordinal: "the second trolley", or by a label: "trolley A", "trolley B"), with no change marker before the second binding, and a later substitution uses one of them. The phrase is read in the binding's own clause (after punctuation that is no decimal point, a relation sign or a joining "and", "while", "but"), and after the value when nothing before it names a quantity ("Let m = 2.0 kg be the mass of trolley A", "m = 2.0 kg (trolley A)"). A use is judged by the object its working is about (repair round 2, `relations._scoped_use`): the one its statement's scope phrase names ("Momentum of A:", "For car P,", "n = 0.0300 mol of HNO₃"), else the one its other twice-bound symbols take their values from, else the one the request asks about; a working that keeps each object's values is scoped and clean, one that takes the other object's value is a conflict, and after a value the answer derived for another object an earlier value used with no object named is a conflict (a stale quantity). Two symbols each bound twice in one part, in parallel and with nothing saying which object either set of values is about ("m = 0.50 kg and v = 4.0 m/s, and m = 0.20 kg and v = 6.0 m/s"), are a conflict too when one substitution takes one symbol from each set (`relations._mixed_groups`; one finding per pair of symbols; "R = 10 Ω" and "R = 20 Ω" are two values even though a whole number read at one significant figure would let them meet) | ST-SCOPE-002 | s06, t16; the trolley cases of `test_repair_round2_layouts.py`; "p = mv = 0.50 × 6.0"; "V = IR = 0.50 × 10" with the two resistors' values | s06c, u13; a rebinding after "Next,"; m₁ and m₂; a substitution that keeps to one set of values |

An engine-decided STEM diagnostic carries its defect on the check (`PlannedCheck.defect`, copied to `FormalCheck.defect`),
so the channel's INT-SUBJ-001 or INT-SUBJ-004 for its failure is labelled with it. A STEM check, like every check, proves
a property of its encoding only: that the written arithmetic, step, conversion or balance holds or does not under the
stated premises and readings, never that a law applies or that data are true.

**Repair round 5** (tests: `tests/stem/test_repair_round5_stem.py`). A unit given only in the request (a specific heat per
kilogram) is traced through the working, so grams substituted against it are a missing conversion (ST-UNIT-003,
`stem_unit_error`; ADV5-03, `relations._unit_companion`). A given written inline in a substitution ("F = ma = 4.0 kg × ...")
that contradicts the request's value is a contradictory given (ADV5-04, `relations._inline_givens`). A conclusion drawn from
a rounded value in any of its common shapes ("20.4 kN ≈ 20 kN, so the beam is safe" against "at most 20 kN", "to 2 s.f., so
...") is ST-ROUND-001 (ADV5-05). A formula written as adjacent letters ("½mv", "1/2 mv", "2πrh") is read as the product it
writes, so a wrong law is ST-REF-001/002 and never only "'mv' has no stated value" (ADV5-06, `spans._quantity_run`,
`parser._juxtaposable`). One symbol rebound to another quantity and then used in the wrong sense is ST-SCOPE-002 (ADV5-07,
`relations._dimension_rebindings`). A reasoned proof of a property ("Show that 14 is even, giving your reason"; a dichotomy
argument) is no missing working, while a bare property or result still is (ADV5-10). A unit symbol that also writes a
short English word ("at", "as", "am", "us") never continues a unit already begun, so a prediction far beyond the measured
range is ST-RANGE-001 (ADV5-16, `spans._UNIT_HOMOGRAPHS`). A count the request states in a sentence ("contains 600
undecayed nuclei") is the value of N₀ (ADV5-18). A '±' step inside a chain ("x + 2 = ±3 ⇒ x = 1 or x = −5") is read as two
equations (rerun-stem-soundness-10, `relations._roots_candidate`, `checks._sol`).

**Close round 1** (section 12; tests: `tests/stem/test_close1_stem.py`). A prose value of the other sign than its own
statement's chain states the magnitude in the words of a direction ("a = (0 − 16)/4.0 = −4.0 m s⁻², so the deceleration is
4.0 m s⁻²"; "= −8.0 J, so friction does 8.0 J of work against the motion") and is no restatement of the signed value, so
no `res` check is planned for it (ADV6-02); a wrong restatement of the same sign is still checked. A value in prose is where
a model is evaluated only when the prose gives it as the input: a preposition or conjunction of a condition before it,
with at most a determiner and three words between ("at 60 °C", "for a storm of 120 mm", "when the temperature is 90 °C";
`relations._INPUT_BEFORE_RE`), and no rate or step after it ("0.05 °C per year", "2 ppm a year": `_RATE_AFTER_RE`). A rate,
a step, a result ("13.4 A, which is 13 A to 2 s.f.") or a value of the model's output in prose is no evaluation point, so
it raises no ST-RANGE-001 (ADV6-07). Bindings ("T = 90 °C") and conditions ("At t = 12 min") are read as before.

**Close round 2** (section 13; tests: `tests/stem/test_close2_boolean_dot.py`). A Computer Science answer that writes a
Boolean constant with the AND dot (`lexer.writes_constant_dot`: an operand of one or two capitals, or a closing bracket,
glued by a full stop to a lone 0 or 1: "A.0", "(A + B).1") is read without the AND dot and without the guard against a
relation glued to a dot between letters (`checks._truncated_operand`), as before both readings (DIFF-04): the lexer reads
the dot before a digit as a decimal point, so the AND-dot reading left such an expression half read and the guard withheld
the rest, and a wrong step ("Since A.0 = A, ...") went unchecked. The check that then names it is the committed base's
reading of the full stops, which charges a correct step written the same way too ("Since A.1 = A, we get A.B + A.1 = A.B +
A = A"; section 7); every answer that writes no constant with the AND dot keeps the AND dot, so a correct absorption
written with it stays checked and clean.

### 3.5 Channel codes (receipt findings only, no label of their own)

| Code | Sev | When |
| --- | --- | --- |
| INT-ARG-001 | the diagnostic's | a warning or error named diagnostic on a material claim (section 2); it carries the diagnostic's `defect` |
| INT-REQ-017 | warning | an answer built on a peer report hands a system check result to the reader as subject content ("a formal check failed ...", a finding code) outside its quotations (end-to-end B3) |
| INT-XENC-001 | warning | two encodings of one claim reach opposite definitive answers: a branch formal check of a clause fails while the translation of the whole claim is displayed ENTAILED, CONSISTENT or SATISFIABLE (end-to-end B20); neither verdict is withdrawn, and the gate counts both unresolved |

Tests: `tests/contract/test_receipt_plumbing.py`, `tests/channel/test_relay_b3.py`,
`tests/channel/test_encoding_disagreement_b20.py`. Repair round 2 also tightened three channel readings with their controls
(`tests/channel/test_repair_round2_channel.py`): a mapping report whose original response is one JSON object wrapping the
answer has an answer (no INT-REQ-012), while a bare JSON receipt still has none; a request made only of zero-width,
format or control characters asks nothing and is REJECTED (INT-REQ-009); and a contract error of one field names the
validator's own message, never the field's value.

Close round 2 (section 13, DIFF-05; `tests/channel/test_close2_synthesis_layout.py`): the relay history (INT-HIST-001,
`docs/STEM_DESIGN.md` section 11.6) carries onto a synthesis no subject finding about a report's paragraphs or sentence
style (`bus._LAYOUT_PREFIXES`: ES-STR-, ES-STY-, HI-STR-), since a synthesis restates the claims it cites and not the
report's paragraphs; the finding stays in the history the synthesis references, a relay of the report names it again and
a router forward carries it. Every other unresolved finding is carried as before.

## 4. The missing link written in as a premise (issue 2)

For "A, so B" a translation that encodes "if A then B" as a premise makes the encoding valid, and Z3 rightly says so. The
defect is the writer's unstated assumption, and R0 names it: the engine decides the point again from the premises a
check established, minimises the rest of the core by deletion (the first 16), and names each remaining link
(ARG-LINK-001, info, with its `missing_link` rendered from the symbols' meanings) and fact (ARG-FACT-001). A link marked as
the writer's step (`specialist_inference`, `assumption` or no grounding) is then read by the pattern rules of 3.1:
converse and inverse of a stated rule, an either/or that is no tautology, an open universal or a majority from instances
or a sample, a cause read into a sequence or a correlation, a paraphrase restating the point, a generic definition of a
sense-qualified noun or one symbol read in two senses. The generic record is info by design: structure alone cannot tell a
non sequitur written with "so" (f01b) from a valid interpretive link written with "which shows" (c03-psych, c04-eng).
Every such claim is still not releasable, because the dependency rule refuses a load-bearing premise that is the writer's
own. A causal link that a stated controlled comparison warrants gets no record, and a rule the writer states from subject
knowledge, marked as stated by the translation, is ARG-LINK-002 (repair round 2); neither makes the claim releasable.

The translation prompt in use, `translate_v3`, asks the provider to mark every step the writer asserts as its own
`specialist_inference` premise with the connective as written, to keep scope words and causal verbs, and to encode every
clause (`translate/prompts/translate_v3.md`; `translate_v1` and `translate_v2` stay packaged unchanged). Two encoding flags
keep an artefact of the encoding from being shown as a verdict on the claim (`translate/pipeline.py`):

- UNLINKED_CONJUNCT (B8): the point's falsified conjuncts share no symbol with any premise while the linked part is
  ENTAILED; the claim is AMBIGUOUS_TRANSLATION and the engine names ARG-PART-001. A reason the claim states but the
  encoding left out (UNENCODED_REASON) is handled the same way; f01, which states no reason, keeps its COUNTEREXAMPLE.
- PARTIAL_ENCODING (B21): an ENTAILED encoding that covers only part of the claim (a clause after "but", "however",
  "although", "while", "whereas" or ";" whose content is mostly absent from the encoding) is AMBIGUOUS_TRANSLATION, and
  the flag names the clause.

Both move a display toward "nothing verified", never toward success. The response gate counts an AMBIGUOUS_TRANSLATION
claim as unresolved, so a COUNTEREXAMPLE the encoding flags as an artefact (UNLINKED_CONJUNCT) leaves the gate's accuracy
instead of failing it; this is the end-to-end decision B13 pins (`tests/channel/test_response_gate_b13.py`: a correct
answer whose counterexamples come from dropped links is delivered labelled "not verified"). A judgement the writer really
left without a reason is then recorded only at info (ARG-PART-001); see section 7 (repair round 3, INV-4).

## 5. False alarms removed on correct work

Each of these was a false finding on a correct answer; each fix keeps the check and names the real fault:

| Item | Fix | Where |
| --- | --- | --- |
| B2 (STEM misreadings) | counts before an operator, mixed-unit compounds ("4 min 30 s"), values restated in brackets, truncated numerals ("…"), restatements of another chain or a named scale ("0.1 pH"), bit groups, a comparison the answer says fails, pairs ending in an expression | `stem/` (design section 24.4) |
| B4, B19 (word and paragraph bounds) | a bound binds to the part, each part, the answer or the paragraph the request names, and one meta-text classifier sets plans, notes and side answers aside | `channel/request_parser.py`, `channel/bus.py` |
| B5, B6 (corrections, mentions) | quotation roles (3.3) | `adapters/markdown.py`, `adapters/sources.py` |
| B7 (pooled derived figures) | a figure two claims derive by their own routes is pooled at its stated precision; claims whose stated intervals do not meet still contradict each other (INT-CONFLICT-001: 24.0 against 24.1 at one decimal) | `integrity/cross_check.py` |
| B8, B21, B22, B16 (encodings) | section 4; an interval tied to a stated figure by its enclosure; a closure variant; written-precision grounding | `translate/pipeline.py`, `translate/precision.py`, `translate/grounding.py`, `translate/quantities.py` |
| B13 (the response gate) | `channel/gate.py`: VERIFIED, DELIVERED_UNVERIFIED ("not verified") or WITHHELD from the receipts alone; an ENTAILED claim on unestablished premises is unresolved, never passed | `channel/gate.py` |
| B17 (STEM claim ids) | two agents of one STEM branch on one task get agent-qualified ids | `adapters/stem_specialist/parser.py`, `channel/bus.py` |
| B18 (request items) | stems, bare labels and form instructions are no required items | `channel/request_parser.py` |
| B20 | INT-XENC-001 (3.5) | `channel/bus.py` |
| B23 (request figures) | the request's own words cited as a supplied document are re-checked against the task record | `translate/grounding.py` |
| B25 (worked equations in prose branches) | the STEM chain checker decides them (`core-stem-*`) | `branches/packs.py`, `branches/quant.py` |
| INT-LEDGER-020, GROUNDING:FAILED on task facts | per-key excerpt sets; a figureless task premise is validated by a task sentence that states it, refuted only when no task record holds its words | `integrity/ledger.py`, `translate/grounding.py` |
| Quoted rules (repair round 1, A-FA-QUOTERULE) | a rule the located excerpt states as a conditional, a universal rule or a biconditional grounds its premise (3.2); a converse never does | `translate/stated_rules.py`, `translate/grounding.py` |
| Dated changes (A-FA-RANGE) | "fell from 42% in 2014 to 18% in 2024" is a change between two dated figures, not a range "2014 to 18%" | `translate/assertion.py` |
| Pooled and derived figures (A-FA-POOLED) | the divisor of a mean of stated addends, and a figure the answer's own written calculation derived, are no figures the excerpts must state | `translate/grounding.py`, `translate/pipeline.py` |
| Derived figures in prose (A-FA-QNT) | CORE-QNT-001 reads a period anaphor ("over the twenty years", "in that decade"), labelled and year-led points ("2019: 610"), a series' dated end points and the pair stated in the sentence before | `branches/quant.py`, `branches/packs.py` |
| STEM statements (A-FA-STEMPARSE and the re-run STEM findings) | condition items, binary literals and input words after a result cue; a comparison the answer calls false (", which is false"); space-grouped thousands beside signs; a spaced AND dot | `stem/` (design section 24) |
| Feedback quotations (A-FA-MENTION, ADV-07) | the quotation roles of 3.3 | `adapters/markdown.py` |
| A quoted conjunction (ADV-09) | a conjunction the located excerpt states is verified as its content | `translate/grounding.py` |
| Complementary options (ADV-13) | an either/or whose options differ only by a complementary pair is no false dilemma | `engine/argument.py` |
| Wrapped answers (rc-7) | a quotation wrapping two or more sentences is no bare assertion, and the History chronology proxy reads its sentences as the core pack does; the wrapped answer stays a quotation, so its quotation checks still run | `translate/diag_argument.py`, `adapters/history_specialist/` |
| Root sets (INV-6) | bare members of a stated set ("x = 0, 2 or −2") are read, so a correct set is decided on every member and a step to it concludes the set; a set read in part, or a root called one of several, claims no full set | `stem/relations.py` (design section 24.11) |
| A shared subject word (repair round 2, FA-ROUND-MAI) | units and scale words are no subject words, compounds and possessives are split, and two figures in one unseparated clause belong to their own subjects, so a test-retest figure no longer fails against a significance level in the same excerpt | `translate/grounding.py` |
| Folds and hedges (FA-AUTH-ESS-FOLD-INVERTED, I2) | "more than halved", "nearly halved", "fell threefold" are read with the bound on the right side, a repeated fold ("halved twice") in both readings, "close to doubling" as a symmetric approach band, and "it did not double" as negated; the end-to-end run1 Geography answer "close to doubling, but it did not double" loses its false INT-SUBJ-001 | `branches/quant.py` |
| Worked results in the next sentence (FA-ARITH-ECON-CROSS-SENTENCE, I1) | a per-cent change that restates the previous sentence's worked result is checked against it; a link after a bare figure stays in the worked view, so its equation is decided, not marked as covered | `branches/quant.py`, `branches/packs.py` |
| A dated series (FA-ALLDATA-GEO-SERIES) | a list of figures between two years is the consecutive years' series when the counts match | `branches/quant.py` |
| A figure derived in an earlier sentence (FA-SUPPORTED-BM-DERIVED) | the report's original response is read for the written calculation that derives a figure | `translate/pipeline.py`, `translate/grounding.py` |
| A quoted equation (I3) | an equation inside quotation marks (another report's) is no arithmetic of the answer's own | `branches/packs.py` |
| A task value substituted into a rearrangement (ADV2-02) | the step's symbols are bound to the request's quantities | `stem/checks.py` |
| A condition named, not asserted (FA-IFF-CS-MENTION) | a comparison after "condition", "test", "guard" is a named condition (context), unless the words after it evaluate it ("(2 <= 1) fails") | `stem/document.py` |
| A lowered capital (ADV2-05) | 3.2, EVD-SRC-003 | `translate/diag_evidence.py` |
| Notation in words (ADV2-11) | 3.2, EVD-SRC-005: the grounding check validates the label by the task sentence it spells, so neither EVD-SRC-005 nor a failed grounding check remains | `translate/grounding.py`, `translate/diag_evidence.py` |
| A word equation (ADV2-07) | a correct word equation is read as the formula it spells, not as a parse error; "0.5 × m × v" is no magnification suffix | `stem/word_formulas.py`, `stem/spans.py` |
| A time converted in brackets (ADV2-12) | "E = Pt = 2000 W × (3.0 × 3600 s)" binds the law's variable | `stem/nodes.py` |
| An evaluated equation after a preposition | "in 2000 C = 340 + 1.75 × 20 = 375 ppm" and "At 60 °C R = …" start at the equation's head; the value is when it is evaluated | `stem/spans.py` |
| A History quotation in the judgement's sentence | 3.1, ARG-BARE-001 | `translate/diag_argument.py`, the parsers |
| A spaced product (repair round 2, own probes) | "E = ½ k x² = …" was cut to "E = ½", so the item looked unaddressed (INT-REQ-004) and "F = k x" was read as the wrong law "F = k" (ST-REF-001) | `stem/spans.py` |
| A task fact in other words (own probes) | a figureless task premise the task states in other words is validated by its sentence (each literal's meaning or its label), and refuted only when no task record holds its label or its meanings | `translate/grounding.py` (3.2) |
| An abbreviation of a subject (own probes) | "PED" for "the price elasticity of demand" names the same subject, not another one whose figure conflicts | `translate/grounding.py` |
| A unit of several words (own probes) | "21 m³ s⁻¹" was read as 21 m³ and "4200 J kg⁻¹ K⁻¹" as 4200 J; the longest reading of two or three unit words is taken first | `translate/quantities.py` (`tests/translate/test_repair_round2_readings.py`) |
| An item answered in notation (own probes) | "Calculate the pH" answered by "pH = −log₁₀[H⁺] = 2.60", a Boolean identity verified by evaluation, and a formula the item itself states ("Simpson's diversity index D = 1 − ...") were read as unaddressed (INT-REQ-004); the branch's evidence now stands in for the shared terms, while an answer that does not address the item is still INT-REQ-004 | `channel/bus.py`, `stem/hub_hooks.py` (`tests/translate/test_repair_round2_readings.py`) |
| A change across sentences (own probes) | a per-cent change rests on the pair of the sentence before it read from that pair's own sub-clause, so a later clause's year ("with a sharp dip in 2020") picks no other pair | `branches/quant.py` (`tests/translate/test_repair_round2_readings.py`) |
| An equation after a condition (own probes) | "At t = 5.0 min T = 80 − 4 × 5.0 = 60 °C" read "min T" as one unit, a false INT-SUBJ-001; the symbol after the condition's value heads its own equation | `stem/spans.py` |

## 6. Measured

Measured on the tree of repair round 5 (every argument-diagnosis change and the repairs of rounds 1 to 5, staged on
`7991e8b`, which holds the end-to-end fixes of `8a78efe`), on 24 October 2026: the suite, both corpora and the arena
replay once each, on the staged tree, in one run. No model provider was called: every translation is a recorded
proposal. The rows before it are the earlier rounds' measurements, kept for comparison; where a paragraph reports an
earlier round only, it says so. The measurement found three false alarms that this round's changes make on genuine
answers of the arena replay; they are reported below and in section 7, and no code was changed after the measurement, so
the measured tree is the staged one.

**Development corpus** (101 cases: 44 defects, 57 controls; `tests/data/argdiag_dev_cases.json`). A defect is *named*
when a signal at warning or error carries its expected label; a control is a *false alarm* when it is refused or flagged
at warning or error. Not being releasable is recorded for a control but is no false alarm: an unreleased answer is still
delivered, labelled not verified.

| Tree | Named | Caught, not named | Missed | False alarms | Clean controls | Controls not releasable |
| --- | --- | --- | --- | --- | --- | --- |
| `22d6a5b` (before the argument diagnosis) | 9 | 25 | 10 | 41 | 16 | 48 |
| `8a78efe` (the end-to-end fixes, the base of these changes) | 9 | 25 | 10 | 41 | 16 | 48 |
| integrated | 44 | 0 | 0 | 0 | 57 | 48 |
| repair round 1 | 44 | 0 | 0 | 0 | 57 | 47 |
| repair round 2 | 44 | 0 | 0 | 0 | 57 | 47 |
| repair round 3 | 44 | 0 | 0 | 0 | 57 | 47 |
| repair round 4 | 44 | 0 | 0 | 0 | 57 | 47 |
| repair round 5 | 44 | 0 | 0 | 0 | 57 | 47 |

Repair rounds 3 to 5 keep every development case: 44 of 44 named, 57 of 57 controls clean, and e01, e04a, e07 and e08b
stay named at warning in text mode too (since round 2; 3.1, a reasoned conclusion). The rules were written against this
corpus, so it shows that every label fires on its case and stays quiet on its controls, not how far the rules
generalise.

The 35 end-to-end cases count only the signals in each case's scope. Outside those scopes, the evidence rules raise 13
warnings on these real answers where repair round 2 raised 45 (EVD-FIG-001 12 and EVD-LACK-001 7 to none, EVD-SRC-005 23
to 10, EVD-SRC-003 2 and EVD-SRC-001 1 as before): the worked, dated and rounded figures of V3-E2E-NEW-EVD-FALSE-WARNINGS
(3.2). The 13 left are on five cases: EVD-SRC-005 on the chi-squared working of two Biology answers (each term and the
sum, over an expected count of 250 that the translation computes and labels `arithmetic_fact`, and the number of
phenotype classes it labels `task_setting`; none cites an excerpt and no task sentence holds them); EVD-SRC-003 on a
ratio that two History answers' translations label `arithmetic_fact` with no excerpt, whose grounding check fails; and
EVD-SRC-001 on the "1 month = 30 days" relation of a Maths answer, which no check verified. Each names what the
translation's label claims and no check established, so each stays (section 7). In repair round 4 the evidence rules
raise no warning on these answers outside their scopes: the expected count 250 and the four phenotype classes are the
mean and the count of the task's list (E2E-BI), the ratio of the History answers cites the Mathematics report, a peer's,
and is unvalidated rather than refuted (E2E-HI), and "take 1 month = 30 days" is the task's conversion (E2E-MAA).

**The repair round 1 probes** (`tests/data/repair_round1_cases.json`, 122 cases: 80 defects, 42 controls, written by the
review of the integrated tree): 80 named and 42 clean (`tests/contract/test_repair_round1_cases.py`), as before. The
repairs of round 1 were written against these cases.

**The repair round 2 probes** (`tests/data/repair_round2_cases.json`, 181 cases: the review's adversarial probes and the
round's own, 92 defects and 89 controls): 92 named and 87 clean, and the two controls pinned as known limits stay flagged
by the rules their pins name (section 7; `tests/contract/test_repair_round2_cases.py`). The repairs of round 2 were
written against these cases, so they show the classes are closed on their probes, not how far they generalise. Both probe
files give the same results on the repair round 3 and repair round 4 trees (their tests pass in the suite below).

**Hold-out corpus** (134 cases: 66 defects, 68 controls), written apart from the rules and run once per round:

| Tree | Named | Caught, not named | Missed | False alarms | Clean controls | Controls not releasable |
| --- | --- | --- | --- | --- | --- | --- |
| `22d6a5b` | 13 | 35 | 18 | 23 | 45 | 40 |
| integrated | 48 | 9 | 9 | 13 | 55 | 40 |
| repair round 1 | 60 | 6 | 0 | 6 | 62 | 38 |
| repair round 2 | 65 | 1 | 0 | 0 | 68 | 38 |
| repair round 3 | 65 | 1 | 0 | 1 | 67 | 38 |
| repair round 4 | 65 | 1 | 0 | 1 | 67 | 38 |
| repair round 5 | 65 | 1 | 0 | 0 | 68 | 37 |

| Family (repair round 5; rounds 3 and 4 as in brackets) | Defects: named, caught not named, missed | Controls: clean, false alarms |
| --- | --- | --- |
| formal (19 defects, 14 controls) | 19, 0, 0 | 14, 0 (13, 1) |
| evidence (14, 18) | 14, 0, 0 | 18, 0 |
| informal (8, 8) | 7, 1, 0 | 8, 0 |
| STEM (25, 28) | 25, 0, 0 | 28, 0 |

- **Repair round 5** (run once on the staged tree, not used to change any rule): 65 of 66 named (98.5%), the one caught
  but not named the case error below, none missed; 68 of 68 controls clean, so the acceptance rule is **met**. The
  control flagged in rounds 3 and 4 (the psychology either/or) is clean: an option word with a negating prefix no longer
  negates the list the task states (DA-2, 3.2). Against round 4, no verdict changes besides that control; 17 hold-out
  controls lose ARG-LINK-001 for a figure relation and 14 gain ARG-FACT-001 in its place (INV-LINK-1), one defect gains
  ARG-NS-003 (a ranked cause, DA-1) and one gains a STEM given check (INT-SUBJ-004). The repairs of this round were made
  from the review's issue descriptions and tests written for the round; the hold-out files were not read.
- **Repair round 4** (run once on the staged tree, not used to change any rule): 65 of 66 named (98.5%), the one caught
  but not named the case error below, none missed; 67 of 68 controls clean. The acceptance rule is **met**. The flagged
  control is the one of round 3, unchanged: the psychology control whose translation records the task's either/or as an
  "or" premise labelled `task_setting` with no excerpt is still refuted (GROUNDING:FAILED, EVD-SRC-005 at warning,
  INT-ARG-001). This round's reading of a task-stated either/or (3.2, FA-TASK-EITHER-OR-REFUTED) validates the shapes
  the review described, and the review's own probe of that control with its request rewritten ("Participant 12 was in
  either the caffeine group or the control group.") is now clean, but the hold-out case itself is not: the reading does
  not reach it. The hold-out was not read to find why, and no rule was changed after this run (section 7).

- **Repair round 3**: the acceptance rule (95% of the defects named, at most one control flagged) was **met** on its
  run: 65 of 66 named (98.5%) and one control flagged (repair round 2: 65 named, none flagged; repair round 1: 60 named,
  6 flagged).
- The flagged control was a regression of repair round 3, made by restoring a check (INV-3), and was left as found: a
  psychology control of the false-dilemma family whose translation records a genuine either/or between two groups as an
  "or" premise labelled `task_setting` with no excerpt. No rule the task states gives that connective, so the restored
  refutation of figureless task premises refutes it (GROUNDING:FAILED and EVD-SRC-005 at warning, carried as
  INT-ARG-001); the point was not releasable before and is not now. The tree before the argument diagnosis (`22d6a5b`)
  flags this control by the same failed grounding check (and one more failed premise); repair rounds 1 and 2 had left
  the premise unverified, which is the weakening INV-3 names. Nothing was changed after this run (section 7).
- The one defect caught but not named is the hold-out case error of section 7 (CASE-LEAP-LL-SLOGAN-REPORT): its text mode
  names `leap_in_logic`; its report mode cites no supporting claims, so the point is NOT_ELIGIBLE ("no supporting
  claims") and only caught as not releasable.
- Independence: the repairs of round 4 were made from the review's issue descriptions (section 10) and from tests written
  for the round, and the hold-out files were not read. As in rounds 1 and 2, the repairs of round 3 were made from the
  review's issue descriptions (section 9), several of which describe classes the review saw on the repair round 2 tree's hold-out runs (a writer's leap left at
  info, worked and dated figures, givens against a law, an extrapolation of a request's model, a rewrite that is no
  identity, missing working, a judgement with no reason in a report that links nothing, a ground phrase pointing back),
  and from tests written for this round. The hold-out files were not read and no rule was tuned on them, but this run
  does not measure the rules apart from those descriptions; the second blind hold-out (below) was not run again.

These hold-out results were not used to change any rule.

**The second hold-out of the round 2 review.** The review of the repair round 1 tree also ran a second blind hold-out
outside the gate (70 defects, 66 controls) and found 44 named and 19 controls flagged. Its cases were not read for this
round and no rule was tuned on them. The repairs of round 2 were made from the review's description of its missed
classes (a missing conversion in symbolic working, magnification, inverted formulas, symbol conflicts, contradictory
givens, extrapolation, a rounding against a target, a bare recommendation, and unnamed hasty generalisations,
equivocations, affirming the consequent, denying the antecedent, a causal claim and cherry-picked months) and from probes
written for this round in the shapes those names describe; the probes are the tests cited in section 3. That hold-out
was not run again, so how far these repairs generalise to it is not measured here.

**The supplementary hold-out of the round 3 review** (its V3-H2 items, section 9). The repairs of round 3 for its misses
were made from the review's descriptions and tests written for this round. After the measurement above, the 18 cases
the review reported (7 defects missed or not named, 11 flagged controls) were run once on the staged tree: the 7
defects are named, 10 of the controls carry the same heuristic flags as on the round 2 tree (section 7), and one gains
an evidence false alarm that a change of this round makes, recorded in section 7 (a declared unit read from an entity's
label) and not fixed after the measurement. The rest of that hold-out was not run, so how far these repairs generalise
to it is not measured here.

**Link records.** ARG-LINK-001 is on 34 of the 57 development controls and 27 of the 68 hold-out controls in the repair
round 5 measurement, where it was on 41 and 35 in rounds 2 to 4 (42 of 57 and 37 of 68 in repair round 1): a figure
relation is now listed under ARG-FACT-001 (on 33 and 17 of those controls, 28 and 9 in round 4). It is on most defects too, so it
does not tell a fault from a valid link. It stays an info record of what the proof rests on: never a finding, never a named
defect, never counted as detection. ARG-LINK-002 fires on none of the corpus cases, whose recorded proposals predate the
rule note of `translate_v3`; it is pinned by its test. ARG-NS-003 (repair round 3) fires on one development defect (f01b,
which it names `leap_in_logic` in text mode) and on no control of either corpus, in repair round 4 as in round 3; in
repair round 5 it also names one hold-out defect (a ranked cause) and still no control.

**Suite**: 8728 passed and 45 deselected (the stress selection, not run), with no failure, no skip and no expected
failure, in 426 s (one serial run on the staged tree, repair round 5). Repair round 4 gave 8565 passed and 45 deselected
in 403 s; repair round 3 8249 passed and 45 deselected in 434 s; repair round 2 8062 passed and 45 deselected in 443 s.

**Arena replays, repair round 5** (every recorded round and run1, on fresh copies): r1 30/30, r1-adv 150/151, r2 to r6
46/46 each, r7 177/177 and run1 120/134, the functional counts of round 4, and no receipt changes status. Against the
round 4 replay, two planted STEM faults gain a check (INT-SUBJ-004 on the inline given of r7's ph-t13 wrong-unit variant
and of run1's ph-e1 substitution variant), and three false alarms of this round's changes appear on genuine answers,
each with the planted variants of the same answer (section 7): r2's en-t4 and r6's en-t11 (seven records each) gain an
INT-ARG-001 warning (EVD-SRC-003) because an excerpt made only of function words ("it was the", "she"), which the answer
analyses as words, is refuted as a placeholder (ADV5-02); run1's ec-e1 (six records) gains the same warning because a
figure stated after a lead phrase ("Before the tax, a litre of sugar-sweetened drink sold for $1.60 on average") is read
as another quantity's (rerun-fidelity-1); and r1's hi-t1 synthesis gains INT-LEDGER-023 (error) because a correct summary
that skips an intermediate value ("from 2.6 per cent ... in May 1928 to 37.3 per cent and 230 seats in July 1932", the
source stating 18.3 per cent in 1930 between them) is read as a swap (rerun-combinator-faults-7).

**Arena replays, repair round 4** (every recorded round and run1, on fresh copies): r1 30/30, r1-adv 150/151, r2 to r6
46/46 each, r7 177/177 and run1 120/134, the functional counts of round 3. Against the round 3 replay, r1 to r7 give
every record the same receipt status and the same finding codes. In run1 no receipt changes status: the five records of
hi-e1a whose planted fault is not arithmetic (the genuine answer and four planted variants) lose the INT-SUBJ-001 that
read its quotation of the Mathematics report's line as its own arithmetic (E2E-HI-MENTION), seven hi-e1a records gain
CORE-QNT-001 for that line (not decided, as a mention), and the planted wrong-arithmetic and chronology variants keep
their INT-SUBJ-001; four records of cs-e1 (the genuine answer and three planted variants) lose an INT-ARG-001 that the
check tip and the derived counts raised (E2E-CS). Every planted fault is caught as before.

**Arena replays, repair round 3** (every recorded round and the end-to-end simulation's run1, on fresh copies of the
recordings): r1 30/30, r1-adv 150/151 (the planted empty answer is still REJECTED), r2 to r6 46/46 each, r7 177/177 and
run1 120/134, the functional counts of the repair round 2 tree. Against the round 2 replay, r1 to r7 give every record
the same receipt status and the same finding codes. In run1 no receipt changes status, and 15 records of maa-e1a and
hi-e1a (the genuine answers and their planted variants) lose one INT-ARG-001 warning, which carried EVD-FIG-001 on figures
the answer works out in writing ("2.050511…" and the figures computed from it) or on dates (1929, 1930): the false class
of V3-E2E-NEW-EVD-FALSE-WARNINGS. Those claims stay not releasable (their ungrounded dependencies, and EVD-SRC-001 or
EVD-LACK-001 where they apply).

**Arena replays, repair round 2** (every recorded round and the end-to-end simulation's run1 on fresh copies, run again
after the harness fix of section 7 that the first replay showed was needed): r1 30/30, r1-adv 150/151 (the planted
empty answer is still REJECTED), r2 to r6 46/46 each, r7 177/177 and run1 120/134, the functional counts of the repair round 1 tree and of
the base tip. Against the repair round 1 tree's replay, r1 to r6 give every record the same receipt status and the same
finding codes. In r7, eight records of cs-t13 lose the info note ST-SCOPE-001 of "The passes test mid = 4, 1 and 2", a
named condition (FA-IFF-CS-MENTION), and the recordings made under bare claim ids now reach the agent-qualified claims of
the generic branch (76 of 224 served; 22 on the base tip and in round 1): three genuine receipts on which nothing was
verified before (bm-t13, ge-t13 and sp-t13) carry translated claims, some AMBIGUOUS_TRANSLATION, and are
ACCEPTED_WITH_FINDINGS, and 35 records of bm-t13, bm-p7a, ec-t13, ec-p7a and ge-t13 gain the warnings the integrity
checks raise over the newly served formalizations (INT-CONFLICT-005 under an ambiguous reading, which charges the
specialist with nothing, and INT-GLOSSARY-005, one symbol glossed two ways: a translation fault). These recordings carry
no claim-text digest, so they are bound by claim id only (the harness's FIXTURES_UNBOUND qualification). run1 serves all
224 of its recorded translations (218 in round 1); against round 1's run1 no receipt changes status, the Geography
answer ge-e1 loses its false INT-SUBJ-001 ("close to doubling, but it did not double") and its CORE-QNT-001 (a "doubling
time" is a name, not a fold) in its records (section 5, folds and hedges), and ess-e1b's
records regain the INT-CONFLICT-004 and INT-GLOSSARY-005 warnings over its served formalizations that the base tip gives.

**Cost.** On the repair round 5 tree (the same method, two interleaved pairs after the measurement, no change of code,
load average 0.5 to 1.0): about 1.55 times the CPU time of `22d6a5b` on the development corpus (14.15 and 14.09 s; this
tree 22.19 and 21.38 s, about 0.075 s more per case; the review measured 1.6 on the round 4 tree), and about 1.6 times
on the largest end-to-end answers (e2e-B2-cs 1.0 to 1.6 s, e2e-B18-cs 1.06 to 1.65 s; the review measured 2.2 and 1.85
times), e2e-B18-mai about 1.9 times (0.35 to 0.45 s against 0.74 to 0.78 s; 2.55 in the review). The round caches the
pure readers the profile showed repeated (`lexis.stem`, `lexis.root`, `quantities.stated_exactness`,
`grounding._enclosures`), drops the consistency check of a derived run made only of bound premises once the engine has
found them consistent, reads each text's tokens once in the symbol-sense rule, and gives the two mark readers an exact
fast path; most of what is left is the derived runs of R0 themselves (one entailment per writer's premise).

**Cost, repair round 4.** End to end, through the public pipeline on the development corpus (101 cases from recorded proposals, two
interleaved pairs, CPU time of the run, after the measurement and with no change of code), the repair round 4 tree takes
about 1.6 times the CPU time of the tree before the argument diagnosis and the end-to-end fixes (`22d6a5b`: 14.7 and
15.4 s; this tree: 23.6 and 24.1 s; load average 0.5 to 1.3 on four cores), about 0.09 s more per case. Under the
profiler, on three end-to-end answers, the claim verification takes about 57 ms per claim (71 ms before this round's
change, 26 ms on `22d6a5b`) and the grounding checks 0.84 s in all (1.99 s before): the answer's own working is read once
per answer text and the records' figures once per value (`grounding._calculation_steps`, `_records_state`; ADV4-09),
with the same findings and messages; the argument stage and the STEM branch checks are the rest of the added cost. The
repair round 3 tree measured about 1.7 times (`22d6a5b`: 17.0 and 15.7 s; 28.6 and 27.6 s) on a loaded host, about 0.12
s more per case; repair round 2 about 1.6 times (27.3 and 26.4 s against 17.0 and 17.4 s). Other processes loaded the
host during these runs (load average 3.7 to 4.8 on four cores), so the ratio carries that noise: a wall-clock pair on
the same day gave 1.59 and 2.12 times. These timing runs gave the same scores as the measurement above. The earlier
per-claim figure (about 7 ms of CPU at the median, repair round 1) measured only the engine's argument stage; the rest is
the grounding checks, the claim and report rules, the derived engine runs and the channel's readings (ADV2-03). Repair
round 2 computes the circularity answer once for the translator's refusal and the engine's E112 (`runner._CIRCULAR_CACHE`,
by content) and each supplied text's tables once (ADV2-01). Repair round 3 adds readings (the refutations of task premises
it restores, the unbridged-leap and ground-phrase readings, the reading of the answer's own working for its figures) and
makes the History chronology reader linear in the answer's length (ADV3-10); no reading was made cheaper for this
measurement.

## 7. Known limits

- **Recorded fixtures and qualified ids** (I5, fixed in the harness). On a task with more than one agent of one STEM
  branch, claim ids are qualified with the agent (`s1.1@ess-specialist`, end-to-end B17), while the fixtures recorded
  before the qualification are keyed by the bare ids. The arena harness now serves a bare recorded id to the
  agent-qualified id of the same claim and agent, and to nothing else, with its problem naming the id the claim now
  carries, as a provider asked for that claim writes it (`scripts/arena/run_arena.py`, `fixture_claim_ids`,
  `fixture_for_claim`; `tests/e2e/test_arena_measures.py`): the translator's check that a problem is about the claim being
  translated still refuses a problem about any other claim. The run1 replay serves all 224 of its recorded translations
  again (218 before), and r7 serves 76 of 224 (22 before; the rest of r7's recordings match no claim of the current
  parses).
- **A hold-out case the round cannot change** (CASE-LEAP-LL-SLOGAN-REPORT). One hold-out defect, a slogan given as a
  point in a structured report, cites no supporting claims; the case file cannot be edited (the hold-out is read only to
  measure). Its point is still caught (not releasable) by the dependency rule; ARG-BARE-001 deliberately yields to a
  section whose other claims offer reasons.
- **Long answers** (parser-safety-11). Repair round 5 made the generic branch parser linear on answers made of list items
  or numbered parts (`tests/branches/test_repair_round5_generic_lists.py`). The per-line work of the STEM front end is bounded and faster (repair round 2), but
  a 400,000-character list answer still takes about 3.4 to 3.7 s to read on this machine (it took about 4 to 5 s; 100,000
  characters take about 1.1 s), not under 2 s: the read stops at 512 statements, but the span finder and the segmenter
  still pass over every line (`tests/translate/test_repair_round2_perf.py` pins the readings, not the time).
- **Two controls of the round's probe cases stay flagged by rules other tests pin** (`KNOWN_LIMITS` in
  `tests/contract/test_repair_round2_cases.py`): a quotation that lowers its source's initial capital is a form
  difference (INT-REQ-010, and its grounding stays unverified, by the quotation-form rule that earlier tests pin), though
  it is no longer named `source_mismatch` (ADV2-05); and an answer made only of the request's own words is a restatement
  (INT-REQ-011), though its exhaustive pass-or-fail options are no longer a false dilemma (ADV2-04).
- **A link written with "so" is not judged** (NAME-LINK-NONDISCRIMINATING). Telling a sound "A, so B" from a non
  sequitur needs knowledge of the subject that no closed table holds: ARG-LINK-001 stays a record on most controls, and
  only the shapes that structure can tell are named (ARG-NS-001 to ARG-NS-003, the converse, inverse, causal, hasty and
  circular readings). Repair round 4 measured the limit (section 10, ADV4-07): see "Left by repair round 4" below.
- **Readings this round leaves undecided** (each a miss, never a false alarm): a precision note inside a chain ("79.0%
  (3 s.f.) ≈ 80%") ends the chain, so a rounding written that way is not read, nor is a rounding "to the nearest 10%"; a
  spaced product is read only for the quantity letters of the profile's reference and never for a bare letter after a
  number; a converse or an inverse stated as subject knowledge is recorded at info (3.1); a cause read into "the more X,
  the more Y" is not read as a correlation, since a mechanism is often written that way too; a condition the request
  sets with two values, or two conditions, plans no rounding check; a fall the request says meets air resistance is no
  uniform motion, even when the answer then treats it as one.

- **Left by repair round 3, each with its reason** (section 9 lists every item of the round):
  - *A lowered initial capital* (ADV3-11). An exact quotation whose only difference is a lowered initial capital ("after
    the crash of 1929, ..." for "After the crash of 1929, ...") stays a form difference: INT-REQ-010 and HI-SRC-001 at
    warning, its grounding unverified. Verifying it would change the quotation-form rule that earlier tests pin
    (`tests/translate/test_overseer_round1.py::test_inexact_match_sets_detail_but_never_verified`,
    `tests/channel/test_round2_fixes.py`, `tests/branches/test_r3_quant_chronology.py`, the known limit xk04 of
    `tests/contract/test_repair_round2_cases.py`); weakening those pins is not allowed, so the false alarm stays.
  - *An unlinked judgement's counterexample is unresolved, not failed* (INV-4). Section 4: the end-to-end decision B13
    pins that a correct answer whose counterexamples come from links the translation dropped is delivered "not
    verified"; counting those claims as failed withholds that answer and breaks the pin (an attempt was reverted). A
    judgement the writer gave no reason for is then named only at info (ARG-PART-001) and is never verified or released.
    Telling a dropped link from an unsupported judgement needs a reading of the writer's reasons this round does not have.
  - *Heuristic readings on clean answers* (V3-H2-CONTROL-FALSE-ALARMS). The supplementary hold-out's flagged controls carry
    only codes the corpus treats as non-defect: ST-UNDEC-001 (a derivative, a logarithm or a Σ outside the encodings: a
    statement of what was not checked, which must stay visible), ES-STR-001 and HI-STR-001 (the writing structure the
    working rules expect), INT-REQ-008 (a position on degree with no verdict cue: "is highly reliable"), INT-REQ-004 (the
    coverage heuristic) and CORE-QNT-001 ("roughly doubled" read against figures of the sentence before). Each is a
    heuristic the gate counts unresolved, never failed; quietening them is outside the argument diagnosis and would weaken
    checks other tests pin.
  - *Two naming gaps* (ADV3-13 a, b). An equivocation on a word outside the closed table with no sense cue ("evolution is
    only a theory, and a theory is just a guess") and a circle through irregular word formation ("tragic" for "a
    tragedy") are caught (not releasable, ARG-LINK-001 at info), not named: the paraphrase and equivocation readings are
    closed tables, and widening the word formation reader risks false circles. A shared-subject leap ("A, so B" about one
    named thing) stays an info record, as ARG-NS-003 reads only leaps between two named things.
  - *Hold-out cases with no supporting links* (V3-CASE-REPORT-NO-SUPPORTING). Report-mode hold-out cases whose point cites
    no supports are NOT_ELIGIBLE ("no supporting claims") and their controls are trivially clean; the hold-out is read-only,
    so the cases are not changed. A report that links nothing at all now has its ranking judgements read as bare
    assertions (3.1), but these cases link their claims partly.
  - *Two false alarms this round makes, found by measuring and left as found* (no rule was changed after the
    measurement, so the measured tree is the staged one):
    - A task's either/or that the translation records as an "or" premise with the task's authority and no excerpt is
      refuted again (one hold-out control; section 6). The refutation is the base tip's, restored for INV-3; repair rounds
      1 and 2 had left such a premise unverified. Telling a task sentence that states the either/or from a connective
      the translation adds belongs to the stated-rule reader and is left for a later round, written from probes of its
      own, since the case was found on the hold-out.
    - A declared unit read from an entity's label. This round lets a symbol's meaning declare its unit by "in <unit>"
      when a parenthesis follows (`quantities._DECL_UNIT_RE`, whose lookahead now admits " ("), so "peak discharge in
      A (m³/s)" reads the catchment's label A as the ampere; a figure stated in m³ s⁻¹ then conflicts with
      the declared unit, the premise fails its grounding check and EVD-SRC-003 names a source mismatch on a correct
      answer (one control of the review's supplementary hold-out, run after the measurement). The repair, preferring the
      unit the parenthesis states and never reading a lone capital that labels a thing as a unit symbol, is left for the
      next round with its own test and control.
  - *Cost* (ADV3-12) and *timing bounds under load* (INV-8): see section 6; the wall-clock tests of the suite can exceed
    their bounds on a loaded host (four parallel shards on four cores), on this tree and on the base tip alike, and pass
    when run alone. The bounds are not relaxed.

- **Left by repair round 4, each with its reason** (section 10 lists every item of the round):
  - *A leap about one named subject* (LEAP-NAMED-ONLY-BY-NONDISCRIMINATING-RECORD, ADV4-07). A writer's "A, so B" whose
    two sides share their subject and nothing else ("Mitochondria contain their own circular DNA, so mitochondria are the
    site of aerobic respiration"; the three leap defects of the hold-out) is caught (not releasable) and recorded by
    ARG-LINK-001 at info, not named at warning. Over the development corpus and the review's adversarial case sets, 145
    writer's links of controls and 42 of defects have that shape (the sides share the subject's words and their other
    words share none); c01-mp's "E. coli cells lack a membrane-bound nucleus, so E. coli is a prokaryote" is one of the
    controls, and "Germany lost the war, so Germany signed the Treaty of Versailles" is a pinned control of ARG-NS-003
    (`tests/translate/test_repair_round3_reports.py`). A rule that read the shape would accuse sound answers, so the
    shape stays a record; the round names what structure can tell instead (a leap between two named things is no longer
    bridged by a sentence that only names them, 3.1).
  - *A lowered initial capital* (ADV4-05, ADV3-11). Unchanged: an exact excerpt or quotation whose only difference is a
    lowered sentence-initial capital stays a form difference (unverified grounding, INT-REQ-010 and HI-SRC-001 at
    warning), pinned by the tests named in round 3's item. An attempt that verified an excerpt the writer lowered
    mid-sentence flipped the round-2 pin (`tests/translate/test_repair_round2_grounding.py`) and was reverted. A
    one-sentence argument translated since round 3 can now meet it: in the review's adversarial sets it is the
    GROUNDING:FAILED on two clean answers that quote an extract's sentence from its second word.
  - *An unlinked judgement* (INV-B8, as INV-4 of round 3). A COUNTEREXAMPLE whose falsified conjunct no premise links is
    displayed AMBIGUOUS_TRANSLATION with ARG-PART-001 at info; it is never verified or released, and the end-to-end
    decision B13 pins it. Telling a dropped link from a judgement given no reason needs a reading of the writer's reasons
    that the round does not have.
  - *Wall-clock tests under load* (INV-T1). In this round's sharded runs (four shards on a loaded host) 13 time-bound
    tests exceeded their wall-clock bounds while their CPU time stayed well inside them, and all 48 tests of those files
    passed when run alone; the serial measurement of section 6 is the reference. The bounds are kept.
  - *The hold-out case with no supporting links* (CASE-LEAP-LL-SLOGAN-REPORT): unchanged, the hold-out is read-only.
  - *The task either/or of one hold-out control* (FA-TASK-EITHER-OR-REFUTED). The round validates an "or" the task
    states (3.2), in the shapes of the review's description and in its probe of the control, but the measured hold-out
    control is still refuted (section 6). The hold-out is not read to tune a rule, and nothing was changed after the
    measurement; finding what keeps the reading from that case belongs to a later round, with probes of its own.
  - *Cost* (ADV4-09): made cheaper where the profile showed repeated work, and still above the tree before the argument
    diagnosis (section 6).

- **Left by repair round 5** (section 11; each with its reason):
  - *A source figure at its written precision* (ADV5-17). A premise that encodes a source's "3.47 million" as [3.465,
    3.475) is still refused as widening a figure given exactly. Three pinned tests state the rule that a given figure
    with no cue states no interval (`tests/translate/test_stated_precision_grounding.py`,
    `test_record_coverage_and_rounded_givens.py`, `test_repair_round3_evidence.py`), and the precision step's own
    message says a figure stated exactly is never widened; an attempt that read the half-unit enclosure of such a figure
    contradicted all three and was reverted. A retry at the exact value passes, so the cost is a provider retry and the
    display of the first attempt, never a wrong verdict.
  - *A lowered initial capital* (ADV5-14, as ADV4-05): unchanged, pinned as above.
  - *A report point whose evidence is never linked to it* (DA-3, as CASE-LEAP-LL-SLOGAN-REPORT). The hold-out case's
    report omits its supporting links, and its paired control omits them in the same way, so no structural reading
    separates the two; a text reading that named it would be tuned on a hold-out case. The point stays NOT_ELIGIBLE and
    not releasable; the "not computed" state is shown, never a pass.
  - *Defect labels on info records* (DA-4). Figure relations are no longer named leaps (INV-LINK-1), which removes the
    leap label from computations and comparisons. The record of a writer's interpretive link stays ARG-LINK-001 at info,
    by design and pinned (`tests/engine/test_argument_diagnostics.py`,
    `test_a_valid_interpretive_link_is_an_info_record_never_a_warning`): structure cannot tell a valid interpretive step
    from a leap. An info record is a listing for the evidence rules, never an accusation: the release lines name only
    warnings and errors (section 2).
  - *Affirming the consequent over a nonlinear condition* (ADV5-15 d). "If n² > 100 then ..." needs nonlinear integer
    arithmetic, which the linear policy refuses (E201, UNSUPPORTED): no derived run is made, so no pattern is named.
  - *The rest of DA-5*. One hold-out-2 control was named `source_mismatch` (the ampere reading, fixed). Its other flagged
    controls carry non-defect structure or coverage codes (ES-STR-001, HI-STR-001, INT-REQ-008, INT-REQ-004,
    ST-UNDEC-001), and five of its defects are named only at info; that corpus is not read to tune a rule.
  - *Cost* (ADV5-13). The repeated work the profile showed is cached and one repeated solver call per derived run is
    dropped; the remaining cost is the derived runs themselves (one per writer's premise, R0's minimisation), which a
    cheaper algorithm would change the links named (section 6 has the measured ratio).
  - *A leap about one shared subject* (DA-1, as LEAP-NAMED-ONLY-BY-NONDISCRIMINATING-RECORD): two more shapes are named
    (3.1); the one-subject shape stays a record.
- **False alarms the repair round 5 measurement found**, closed by close round 1 (section 12): the excerpt of function words
  analysed as words (r2's en-t4, r6's en-t11: a literal that quotes or names the excerpt's words is about them, 3.2), the
  figure after a lead phrase (run1's ec-e1: another figure of the same value, or a figure stated for the opposite part, gives
  the quantity no other figure, 3.2) and the summary that skips an intermediate value (r1's hi-t1 synthesis: a figure whose
  words after it are the source's own statement of it is no swap, 3.3). The repros of these records raise none of the three
  findings on this tree (section 12).

- **Left by close round 1** (section 12; each with its reason):
  - *An evaluation point stated with no input cue* (ADV6-07). A prose value is read as the model's input only after a
    preposition or conjunction of a condition ("at", "for", "when", "if", "with"); a value written as an attribute ("a 40 N
    load stretches the spring by ...") or after "of" is no longer read, since "of" also introduces the model's output ("an
    extension of 12 cm"). The repair round 5 reading named such an extrapolation; the measured hold-out case
    `ho_d_extrap_phys` is caught (not releasable) but no longer named, which is its verdict on the committed base. The
    hold-out is not read to tune the cue.
  - *A magnitude after its own signed chain is not checked* (ADV6-02). A prose value of the other sign than its own
    statement's chain is read as a magnitude and planned no check, so a wrong magnitude ("so the deceleration is 5.0 m s⁻²"
    after "= −4.0 m s⁻²") or a dropped sign ("so the acceleration is 4.0 m s⁻²") in that statement goes unchecked, as on
    the committed base, which reads no chain of the value's own statement. Checking the magnitude instead would charge a
    value of another quantity of the other sign ("ΔH = −286 kJ mol⁻¹, so 143 kJ is released by 0.5 mol").
  - *A circle written as a restatement of the task* (arena r7 lit-t13). An encoding whose restating premises and point all
    claim the task's authority, for a claim with no reason connective, is an info record of ARG-CIRC-001, not a warning; the
    refusal stands and nothing is releasable, so such a circle is recorded rather than named at warning (the committed base
    names no circle there at all).
  - *A request series that takes a year into a unit's series* ("18 to 2010 °C" read as one series of temperatures). A range
    too wide only makes misses, never a false alarm; unchanged, as on the committed base.
  - *Whitespace runs in other self-certification patterns* (found while making `SELF_CERT_RE` linear; not an item of the
    review). `markdown._SELF_CLOSING_RE`, `_CHECK_END_RE`, `_FIDELITY_END_RE`, `_QUOTED_LABEL_RE`, `_SELF_PERFECT_RE`,
    `_SELF_PREDICATE_TAIL_RE`, `_TRAILING_BARE_LABEL_RE` and `_CLAUSE_RE` put an optional whitespace run beside another, so
    their work at one anchor is quadratic in a hostile run ("These figures are accurate" followed by 1,000, 2,000 and 4,000
    spaces: 0.02, 0.07 and 0.26 s in `is_self_certification`). The committed base has the same patterns at the same cost
    (measured on both trees); they are left for round 8, to be made linear with a timing test of their own.
  - *Versions.* Close round 1 changes rules of the translation pipeline and of the argument rules under the unchanged
    stamps (engine 0.5.0, policy 2026.10-v5, translator 0.5.0, rules `argdiag-1`), as repair rounds 1 to 5 did: the release
    these stamps name is not published, `version.py` sets them once for the whole argument-diagnosis release, and every
    result of the committed base carries engine 0.4.0, policy 2026.10-v4 and translator 0.4.0 and reads as stale. The engine
    build identity of this round differs from repair round 5's (`engine/argument.py` and `version.py` changed), so a signed
    engine result of the round-5 tree reads as another build; a translation record of that tree would still read as
    current, which is INV7-2 below.

- **Known defects of the close round 1 review** (its GAP and IMPROVED items, not changed by close round 1 and left for
  round 8; each line gives the id, what fails, and how the committed base fails; the repros were run on this tree and give
  what the review found, except where a line says otherwise):
  - ADV6-03 is closed: on the STEM branches by accuracy round 1 (section 17), on the general branches by accuracy round 2
    (section 18, V1I-06).
  - ADV6-10: "W = ½m(v² − u²) = 0.5 × 1200 × (25² − 10²) = 315000 J" with m given in the request is not verified clean
    (gate "not verified"); the committed base fails the same way.
  - ADV6-11: a correct application of a rule the task states reuses the request's words and is an INT-REQ-011 restatement
    (error) with INT-REQ-004, so the gate withholds it; the committed base fails the same way.
  - ADV6-13: a source rule over a figure applied correctly ("If inflation exceeds 5%, ..." with 6%; "Every firm with more
    than 50 employees pays the levy" with 80) is not verified as stated (ENTAILED, not releasable); the committed base fails
    the same way.
  - ADV6-14: an equivocation on "bank", a quotation cut from "Not all ...", and "does not fall much" encoded as "falls" are
    caught but not named; "x² = 6x, so x = 6" is named `stem_arithmetic_slip` rather than `stem_invalid_step`; "√(a² + b²) =
    a + b − 2" is missed; the committed base fails the same way or worse, except the "does not fall much" case, which the
    base flags at warning through its refutation of a true task fact (close round 2 found it: DIFF-03, left below).
  - INV7-2: a translation record's identity does not cover the translate modules (`engine.identity.BUILD_SOURCES` is
    version.py, named.py, lexis.py, ir and engine), so a record made under a changed grounding rule with the same translator
    version reads as current; the committed base has no translation staleness check at all.
  - INV7-3: a located excerpt "raised interest rates sharply last year" verifies a premise meaning "cut ...", "will raise
    ... next year" or "... this year" (`verbatim_match`); close round 1 reads that conflict in task sentences only (INV7-1);
    the committed base verifies all four the same way.
  - rerun-verify6-ss4-variant-boolean-constants: a wrong Boolean constant identity (A·0 = A, X·1 = 0, P·0 = P) is not
    checked as such; the committed base checks none either. Close round 2 found that the base still charges a wrong step
    written with the AND dot and a constant ("Since P.0 = P, we get ...") through its reading of the full stops, so that
    shape was a regression of the close round 1 tree (DIFF-04, section 13).
  - rerun-verify6-fidelity-2-variant-int-literals: an open-precision whole number ("about 300" for 260) over Int literals is
    ENTAILED on one assumed reading and releasable; the committed base does the same. Its variant over `to_real` of the
    count was AMBIGUOUS_TRANSLATION and not releasable on the close round 1 tree, a regression closed by close round 2
    (DIFF-06, section 13).
  - rerun-verify6-weakened-definition-converse: "A whale is a mammal that lives in the sea" grounds the converse rule
    (verified, releasable); the committed base does the same.
  - rerun-verify6-weakened-show-that-property: "91 is odd, so 91 is prime" is ACCEPTED with no finding; the committed base
    does the same.
  - rerun-verify6-ss12-variant-power-laws: "(a²)³ = a⁵", "x²·x³ = x⁶" and "√(a² + b²) = a + b" are not checked (INT-REQ-004
    only); the committed base the same.
  - rerun-verify6-fidelity-1-variant-respectively-colon: a premise that takes another item's figure under "respectively"
    or from a colon list is verified and releasable; the committed base the same.
  - rerun-verify6-cf3-variant-status-forms: "Proof status — complete.", "Validated against the mark scheme." and three
    other appended status lines are not named INT-LEDGER-029; the committed base the same.
  - rerun-verify6-cf5-variant-credit-forms: a specialist's words credited to the poem by "In the sonnet we read:", "Shelley's
    line", "(l. 14)" and four other forms are not named misattributed; the committed base the same.
  - rerun-verify6-cf8-variant-notations: "3·5 tonnes" for 3.5 and "3/4" for 0.75 in a correct synthesis raise
    INT-LEDGER-023; the committed base the same.
  - rerun-verify6-security-2-variant-labels: a premise resting only on a document labelled as agent- or machine-written
    ("agent:<task>", "answer-<task>", "automated assistant") is verified and releasable; the committed base the same.
  - rerun-verify6-rc7-variant-fenced-envelope: a JSON envelope inside a code fence is not read as its answer; the committed
    base the same.
  - rerun-verify6-response-bound-after-parse: an over-size reply is parsed before it is refused (400,000 characters: about
    16 s; 2.3 million: about 58 s, then REJECTED); the committed base does the same about 17 times slower.
  - V6-DA-01: `ho_d_leap_bm_since` is named only by ARG-LINK-001 at info, not ARG-NS-003 at warning; the committed base does
    not name it, but flags it at warning through its CORE-QNT-001 false error (close round 2, DIFF-07, left below).
  - V6-DA-02: leaps carry ARG-LINK-001 at info on defects and clean controls alike, with no warning-level leap name; the
    committed base names no leap either.
  - V6-DA-03: the slogan-to-audience leap is named only at info in text mode and caught but unnamed in report mode; the
    committed base the same or worse.
  - V6-DA-06: `ho_d_sym_chem` is named `stem_symbol_conflict` but also carries the misdescribing warnings ST-REF-001 and
    INT-SUBJ-004; the committed base does not name it.
  - arena run1 base-only findings (214 items) and the r7 and r1-adv items of the same kind: improved, the triage found
    nothing left failing (the base's false findings on correct work are gone and the replacement checks pass); the
    committed base raises them.
  - arena staged-only findings (147 items: INT-REQ-017, INT-CONFLICT-005, INT-GLOSSARY-005, ARG-BARE-001, INT-SUBJ-004,
    INT-XENC-001, INT-REQ-005 on lit-e1's variants, INT-HIST-001 carrying shared findings, INT-REQ-004 demotions): improved,
    true added findings; the committed base raises none of them. Close round 2 found that the INT-HIST-001 carries of
    findings false in both trees are not improvements (DIFF-05): those of layout findings onto syntheses are closed, the
    rest is left below.
  - arena status and display changes (20 statuses, 55 displays): improved, release unchanged in every case; the committed
    base shows the older statuses.
  - corpus cases (168 items): improved, control_clean or named; `ho_d_leap_ll_slogan` stays caught but unnamed in report
    mode, as on the committed base.

- **Left by close round 2** (section 13; each with its reason):
  - *A plainly stated source rule with a qualifier word elsewhere in its sentence* (DIFF-01): a hedge in a later conjunct
    ("borrowing falls and firms may delay investment"), "can" in a relative clause on the object, an "or" inside the object,
    "cannot" in a consequence whose premise also negates, an affirming frame ("There is no doubt that", "Nobody disputes
    that", "Few doubt that") is refuted as `source_mismatch` (EVD-SRC-003 and INT-ARG-001 at warning, GROUNDING:FAILED, not
    releasable), where the committed base verifies the located excerpt and releases the claim. The cause is close round 1's
    `stated_rules.rule_qualifier` (ADV6-01). The convergence rule forbids narrowing it again; reverting the stated-rule
    reading to the base's (a located excerpt verifies the rule premise) would reopen ADV6-01, because the base blocks those
    hedged-rule answers only through its refutation of every figureless task fact (a true fact the task states, which the
    staged tree rightly validates): the hedged rule would then be released. Neither path leaves the tree no worse than the
    base on both classes; left for round 8 with the review's probe cases.
  - *A rule whose consequence the excerpt negates* (DIFF-03: "If the price of tea rises, demand for tea does not fall much"
    cited for "if the price rises, demand falls"): the premise is left unvalidated (not releasable; `leap_in_logic` at info),
    not refuted as `source_mismatch`. The committed base flags the case at warning only through its refutation of the true
    task fact, and verifies the contradicting rule by its location. Naming it needs a new refutation reading (a negated
    consequence refutes the rule), which the convergence rule does not allow; restoring the base's refutation of
    figureless task facts would revert the task-fact validation in every task.
  - *A leap joined by "since" before a possessive* (DIFF-07, the hold-out case `ho_d_leap_bm_since`: "Since its sales grew
    at home, Solara Ltd should expand into Spain"): named `leap_in_logic` only at info (ARG-LINK-001), not releasable, where
    the committed base flags it at warning through its CORE-QNT-001 false error on the correct figure (end-to-end B25,
    removed by the staged tree). The leap reader takes "since" before a possessive as the time preposition ("since its
    founding"), so it finds no connective and names no ARG-NS-003; reading it as a reason would widen the connective reading
    (a new reading), on a hold-out case no rule is tuned on.
  - *The rest of DIFF-05*: six peer relays (r3 hi-p2, r4 en-p3, r7 bm-p7a, r7 lit-p7c, run1 ess-e1b, run1 hi-e1a) and the
    synthesis of r5 hi-p4 carry, as INT-HIST-001, findings their source receipts raise falsely in both trees (ES-STR-001,
    CORE-SRC-003, CORE-QNT-001, INT-SUBJ-001, ST-PARSE-001, and INT-REQ-003 on a quotation from memory), so they read
    ACCEPTED_WITH_FINDINGS where the base reads ACCEPTED. A relay hands on the same text, and the synthesis cites the very
    claim the finding names: carrying what an earlier receipt left unresolved is the class INT-HIST-001 was written for (a
    later transmission that re-checks less never erases an earlier finding), so the carry stays, and the false findings are
    their source checks' (both trees raise them; round 8).
  - *Frames that say the words are absent* (beside DIFF-02): a short span after "no" or "with no", and one word after a
    negated verb, stays a mention (the review's 'no "mercy for sailors"' and 'not "drowsy"', and 'with no "warm September
    light"' of its end-to-end probes, which it calls arguable scare-quote mentions): such a frame says the text does not
    use the words, and checking them would bring back the base's false errors on correct mentions (end-to-end B5, B6).
  - *Given up by the round* (section 13): a short word set aside by a contrast as one the text does not use ('Unlike
    "tumbled", the verb "bend" is slow') is checked again and can raise INT-REQ-003 on correct work, as on the base
    (DIFF-02); a figureless task fact that the point restates ("State what the central bank did") is no longer a
    transcription the task validates (repair round 4, ADV4-06) and is left to the circularity rules, as on the base
    (REG-CIRC-TASK-PROPOSITION); an answer that writes a Boolean constant with the AND dot is read with its full stops as the
    base reads them, so a correct step written that way ("Since A.1 = A, we get A.B + A.1 = A.B + A = A") is charged
    INT-SUBJ-001 as on the base (DIFF-04); a synthesis no longer carries a layout finding that is true of its source report,
    which stays in the history it references (DIFF-05).
  - *Cost near the review's bound* (found by the measurement, section 13; no item of the review): 36,000 characters of
    digit groups spaced as thousands ("1 000 1 000 ...") cost about 3.6 s of CPU against the base's 1.3 s (2.9 to 3.3
    times; the review measured 3.1 times before this round), a bounded cost that grows slowly with the text (3.3, 3.5 and
    4.9 s at 12,000, 36,000 and 108,000 characters) and that no quotation reader takes part in; 12,000 characters of
    one-character quotations ('{"{"{"...') cost 0.27 s more than the base (3.2 times on a cold process, 2.0 times on a warm
    one, 1.7 times at 36,000 characters), the linear cost of reading their roles. Left for round 8, with a profile.
  - *Versions.* Close round 2 changes readings of the translation pipeline (`grounding`, `precision`), of the STEM reader
    and of the channel under the unchanged stamps (engine 0.5.0, policy 2026.10-v5, translator 0.5.0, rules `argdiag-1`), as
    the earlier rounds of this release did: the release these stamps name is not published, `version.py` sets them once for
    the whole argument-diagnosis release, and every result of the committed base carries engine 0.4.0, policy 2026.10-v4
    and translator 0.4.0 and reads as stale. No engine source changed (`engine.identity.BUILD_SOURCES`), so the engine build
    identity is close round 1's and an engine result decides the same encoding the same way; a translation record or a
    receipt of an earlier staged tree would still read as current, which is INV7-2.

- **Known defects of the close round 2 review**: the review handed this round its 9 regression items only, not its GAP and
  IMPROVED items, so the list of close round 1 above stands as the known-defect list for round 8, with the corrections the
  review's findings made to five of its lines (ADV6-14, the two rerun-verify6 variants, V6-DA-01 and the INT-HIST-001
  carries) and the items left above.

- **Left by close round 3** (section 14; each with its reason). Three items are regressions the round could not close (and
  a part of a fourth, DV2-07, below): the convergence rule forbids narrowing their reading again, and a revert to the
  committed base's reading would turn detections that earlier tests pin into misses, which would weaken those tests
  (`CLAUDE.md`: no test is weakened or deleted to make code pass; a test is rewritten only to a stricter base behaviour).
  They need a decision outside this round: an instruction to rewrite the named tests to the base's outcome, or a new
  reading.
  - DV2-03, DV2-05 and DV2-08 are closed by accuracy round 1 (section 17), each by a narrower reading that keeps every pinned
    detection; what that round leaves of them is listed there.
  - *The remaining cost of the r7 answers* (DV2-07, in part): the repeated joint checks are gone (the r7 round takes 2.4 to
    2.6 times the base's time, 3.1 before the round: section 14), but one r7 answer group still takes 24 to 25 s against
    the base's 2.1 s (11 to 12 times; 32 s before the round), because the base's parser serves none of r7's 418 claim
    outcomes: the cost is the verification of claims the base never verifies (translation, engine runs with their
    diagnosis, the branch formal checks), linear in the claims. The bm-p7a group makes 294 claim verifications, 210 of
    them distinct (the identical repeats cost 3.1 of 22 s), with 778 engine runs and 875 fresh solver contexts.
    Removing the cost would remove the served outcomes; a cheaper engine context per run would change the engine.
  - *Found by the measurement* (no item of the review; round 8): 'The bulbs are not "glittering" for nothing', an idiom that
    affirms the quoted word, is read as a mention (one quoted word after a negated verb, the frame close round 1 narrowed and
    close round 2 left so as to keep the base's false errors on correct mentions away, end-to-end B5 and B6), so the
    invented word is not checked, where the base names it (ES-SRC-001). The plain-rule control the measurement also found
    held back, A02 ('When the river floods, farmland is damaged, which may take years to recover.', applied to farmland near
    the Tamar), is released by accuracy round 2 (section 18, V1I-05), and its companion s04 by accuracy round 1.
  - *Given up by the round*: a word the writer says the text never uses, written right after a negated reporting verb ('The
    grandfather never once says "I love you"', 'The poet never writes "roared"', 'the text never says "ayudar"'), is
    checked again and can be named an invented quotation on correct work, as on the base (INV-QR-1); a negated report with
    words before the span keeps its mention.
  - *Versions.* Close round 3 bumps the translator to 0.5.1 and the rules to `argdiag-2` (`version.py`), so a translation
    record of any earlier round of this release reads as stale (the outcome checks the translator version: INV7-2 no longer
    holds within this release) and a result diagnosed under `argdiag-1` is refused by release rule 9. Engine 0.5.0 and policy
    2026.10-v5 stay: no compilation, procedure, limit, allowlist or eligibility rule changed in the round, and the build and
    policy identities bind `version.py` and the rules version.

- **Known defects of the close round 3 review** (the review's items that the round's discrimination rule turns into gaps: the
  committed base flags the defective input and its matched correct control alike, so its outcome on the defect is no
  detection; each defect was run on both trees beside its matched control, a probe case of the round's own wording that
  differs from it only in the defect; not fixed):
  - DV2-01: a task sentence that reports a forecast, hope, fear, promise, plan, estimate or hypothesis ("Analysts expect
    that ...", "Economists forecast that ...", "Savers hope that ...", "The finance minister promised that ...", "The central
    bank plans to raise ...", "Most estimates show ...", "A student hypothesises that ...") validates a `task_setting` premise
    that states it as fact, so the answer is ENTAILED and released (Economics) or caught but unnamed (Biology). The committed
    base gives its matched control (the task states the fact: "Interest rates in Country Q will rise next year.", "The
    central bank has announced that ...", "The enzyme is denatured at 70 °C.") the same outcome as the defect: NOT_ELIGIBLE
    and not releasable in Economics, GROUNDING:FAILED (its refutation of every figureless task fact) in Biology; the staged
    tree releases the controls (Economics) or keeps them clean.
  - DV2-02: a capitalised "May" in a title-case headline ("Interest Rates In Country Q May Rise Next Year") is read as the
    month, so the headline validates the premise "interest rates ... will rise next year" and the answer is released. The
    committed base gives the control headline with "Will" the same outcome as the defect (NOT_ELIGIBLE, not releasable).
  - DV2-09: "If the price of tea rises, demand for tea does not fall much", cited for "if the price rises, demand falls", is
    caught but named only at info; the committed base names it at warning through its refutation of the true task fact "The
    price of tea rose in 2024", which it raises alike on the control that cites "If the price of tea rises, demand for tea
    falls" (a false alarm there; the staged tree keeps that control clean and releasable).

- **Left or given up by accuracy round 2** (section 18; each a detection the tree before round 1 made that a revert to the
  committed base's behaviour gives up, or a case every tree fails the same way):
  - *Stance in other words* (V1I-01): a document that states its stance on the claim's subject only in other words than the
    claim's ("its delegates welcomed the settlement as fair" for a claim about the treaty) or by a subject pronoun is not
    read, so the opposite stance credited to it is missed, as on the base.
  - *A circle with words of its own, a vague cause* (V1-BARE-CIRCULAR): "because of the consolidation of his power over the
    party by 1929" for "Stalin consolidated power by 1929", "due to their faster growth in the greenhouse", and a cause
    phrase whose object names no cause ("due to many different economic problems", "after a very difficult year") pass,
    as on the base; a cause phrase that only restates the point is ARG-CIRC-003.
  - *A near restatement that misreads the task* (V1I-02): a label-only task premise that holds all of an asserted task
    clause's words but one ("will raise interest rates again" beside "which raised interest rates last year") is an info
    record of EVD-SRC-001, not a warning; it stays unvalidated and the answer not releasable.
  - *An own step that bridges nothing* (V1I-07): a "so" sentence whose reason adds a step of the writer's own is no
    unbridged leap (ARG-NS-003), whether or not the step bridges; ARG-LINK-001 still records the writer's link.
  - *A replaced given that is no miscopy* (V1-STEM-GIV-FA): a value of other digits than the request's quantity in its
    place ("(10 − 2.5)/3.0" for 4.0 m s⁻¹), or half or twice it ("R = 12/3.0" for 24 V), is not compared, as on the base.
  - *Left as accuracy round 1 left them*: a fact from the writer's own knowledge that the request invites but that is
    invented (l09, vp_lack_invented_gk_bad) is an info record of EVD-LACK-001, still not releasable (DIFF3-06); a quotation
    that denies the link (n07: 'Historian K writes that "the occupation of the Ruhr did not reduce German industrial
    output", so ...') is read by round 1's quotation bridge as stating the connection, so the leap keeps only ARG-LINK-001
    and stays not releasable (DIFF3-02).
  - *Left as before the round*: s09 (a dropped "while" condition, section 17) stays refuted; a sonar depth worked with the
    speed of sound in water ("d = v × t / 2 = 1500 × 0.40 / 2" for a boat at 5.0 m s⁻¹) keeps the tree's ST-REF-002
    (`stem_wrong_formula`) with its INT-HIST-001 carry, as before round 1 (the base raises nothing; round 1's `giv` false
    alarm on it is gone); "n = m/M = 1.00/40.0" for NaOH, with the request's M of HCl beside it, keeps the base's own
    INT-SUBJ-001 error.

## 8. For the overseer build (pack text, not implemented here)

End-to-end item B11 is pack text for the overseer knowledge pack, written here for the overseer build to take over:

- **A confirmable kind `finding_false`**: a receipt finding that is false on the answer. It is confirmed only
  deterministically, by re-running the rule that the finding misapplied:
  - re-read the claim substring the check encoded, and check that the relation it decided is the one the answer states;
  - the quotation roles of 3.3: in a marking, feedback, correction or editing task, a corrected form after an arrow,
    "should be", "change ... to" or a "Model:" label is no quotation, and in every task a mention (a quoted function
    word, a short span after a negating frame, a word the text is said not to use) is none; in any other task a
    correction frame leaves the span a quotation, so a finding on it is no false finding;
  - a restatement is of the same quantity: the same symbol, unit or chain, and a value in a named scale restates only a
    value in that scale;
  - the B2 classes of 5;
  - the response gate's list of heuristic findings, which never fail an answer.
- **Restrict rule I3** ("a named fault is not accused") to findings that are true.
- **Info records are no faults**: ARG-LINK-001 on a valid interpretive link, ARG-LINK-002 on a stated rule, EVD-SRC-002 and
  EVD-LACK-002 ("not checked"), and every capped line, which still blocks release but accuses nothing.

## 9. Repair round 3

The review of the repair round 2 tree (35 items: corpus, invariants, adversarial and re-run lenses) and what this round did
about each. Tests are the files named `test_repair_round3_*.py` (and the stricter pins named in each row).

| Item | What was wrong | What changed (cause) | Tests |
| --- | --- | --- | --- |
| V3-LEAP-INFO-ONLY | a writer's leap was only an info record | ARG-NS-003 (3.1) | `translate/test_repair_round3_reports.py`; pins in `contract/test_named_model.py`, `translate/test_argument_rules.py` (stricter) |
| V3-FALSE-SRCMISMATCH-COMPARED | a figure after "compared with" was tied to the wrong word | comparison words are figure frame words (3.2) | `translate/test_repair_round3_grounding.py` |
| V3-E2E-NEW-EVD-FALSE-WARNINGS | EVD-FIG-001 and EVD-LACK-001 on real answers' worked, dated and rounded figures | `assignment_support`, `worked_results` (3.2) | `translate/test_repair_round3_evidence.py` |
| INV-1 | a task premise validated by a bag of words | the stating sentence must hold the words in order with their polarity; reported views state nothing | `translate/test_repair_round3_grounding.py` |
| INV-2 | a rule a question asks about validated as a given | the rule reader skips questions and suppositions | the same |
| ADV3-01 | "A, so B" in one sentence never diagnosed | `states_own_reason`, `opens_with_conclusion`, eligibility (3.1) | `translate/test_repair_round3_reports.py` |
| ADV3-02 | the gate parsed agent-controlled text | the gate re-makes each carried finding from the receipt's structured history | `channel/test_repair_round3_gate.py` |
| ADV3-03 | a unit companion on a percentage rounding | one quantity written once is no unit change | `stem/test_repair_round3_stem.py` |
| rerun-fidelity-1-variant | an excerpt's figure given to another quantity or entity | subject words, names and openers read on both sides; opposed qualifiers (3.2) | `translate/test_repair_round3_grounding.py` |
| V3-CHERRY-ESS-UNNAMED | a trend from a window before a reversal unnamed | EVD-CHERRY-001 reads the years after the window | `translate/test_repair_round3_cherry.py` |
| V3-FALSE-CAUSAL-EFFECT-DURATION | a duration read as a post hoc | sequence read from the facts' meanings, two times needed | `engine/test_repair_round3_argument.py` |
| V3-FALSE-SRCMISMATCH-THRESHOLD | a bound grounded no ceiling symbol | a bound states the figure of a symbol that names it | `translate/test_repair_round3_grounding.py` |
| V3-CASE-REPORT-NO-SUPPORTING | hold-out cases cite no supports | left: case faults in a read-only corpus (section 7) | none |
| V3-H2-STEM-MISSES | six STEM and report misses | ST-GIVEN-004 laws, request-model ranges in every subject, ST-STEP-003, ST-WORK-001 cues, ARG-BARE-001 in unlinked reports, ground phrases | `stem/test_repair_round3_stem.py`, `translate/test_repair_round3_reports.py` |
| INV-3 | refutations of figureless task premises weakened | refutation restored for views, questions, misreadings and unstated connectives (one hold-out control is flagged again, as on the base tip: sections 6 and 7) | `translate/test_repair_round3_grounding.py` |
| INV-4 | B8 flags take a COUNTEREXAMPLE out of the gate's accuracy | left: pinned end-to-end decision B13 (sections 4 and 7) | none (a reverted attempt) |
| INV-5 | a negated conjunct read as stated | per-conjunct polarity; a conjunct's distinguishing word is required | `translate/test_repair_round3_grounding.py` |
| ADV3-04 | exhaustive options read as a false dilemma | closed exhaustive partitions | `engine/test_repair_round3_argument.py` |
| ADV3-05 | a census, a source's "many" and a post hoc read as hasty | census reading; a post hoc is a causal leap | the same |
| ADV3-06 | a decoy control cue hid the causal link | a control cue counts where it bears on the link | the same |
| ADV3-07 | post hoc over Bool or "after" facts unnamed | sequence from meanings and dates | the same |
| ADV3-08 | an exact quotation of a list refused as circular | the excerpt's sentence states each member | `translate/test_repair_round3_grounding.py` |
| ADV3-09 | givens against a reference law; a symbol comparison after rounding | definition laws; symbol comparisons | `stem/test_repair_round3_stem.py` |
| ADV3-10 | quadratic chronology reading | each cue reads a window of its sentence | `adapters_history/test_repair_round3_chronology_scale.py` |
| ADV3-11 | a lowered capital fails grounding | left: pinned quotation-form rule (section 7) | none |
| rerun-stem-soundness-11-variant | "Cancelling x" lost a root unnoticed | a cancellation is a division by the unknown | `stem/test_repair_round3_stem.py` |
| rerun-combinator-faults-5-variant | quotation credit missed common names | organisation names, document kinds, match-only kinds | `integrity/test_repair_round3_ledger.py` |
| rerun-combinator-faults-8-variant | one figure in two notations | grouped thousands read as one number | the same |
| V3-H2-CONTROL-FALSE-ALARMS | heuristics on clean answers | left: non-defect heuristics (section 7); one of these controls gains a false alarm this round makes (a declared unit read from an entity's label, section 7), found after the measurement | none |
| INV-6 | a legacy signature verified after a key-id relabel | `signature_form`; a key id is attested only by the bound form | `engine/test_repair_round3_signatures.py`, `service/test_repair_round3_signatures_http.py`; `service/test_review_service_fixes.py` rewritten stricter |
| INV-7 | an undiagnosed claim read as passed | the gate reads the rule version, `diagnosis_incomplete` and the release | `channel/test_repair_round3_gate.py` |
| INV-8 | timing bounds fail under load | documented (section 7); bounds kept | none |
| ADV3-12 | cost | measured again (section 6: about 1.7 times the CPU time of `22d6a5b` on a loaded host) | none |
| ADV3-13 | naming gaps | (c) a chained instance is hasty; (d) a "rule" note on a bare label keeps the missing link; (e) EVD-SRC-001 for links on located excerpts that state no link; (a, b) left (section 7) | `engine/test_repair_round3_argument.py`, `translate/test_repair_round3_evidence.py` |
| rerun-security-2-variant-case | a peer id escaped by case or whitespace | normalised ids, one test everywhere | `translate/test_repair_round3_peer_ids.py` |

One existing test was rewritten to a stricter rule besides those named: `tests/channel/test_round3_fixes.py`
(`test_an_echo_of_the_request_never_supersedes_the_genuine_report_or_its_pool`) now asserts that the genuine report's
ranking judgement with no reason, in a report that links nothing, is named ARG-BARE-001 and carried on the relay, where it
asserted an ACCEPTED relay before; every other assertion is the earlier one.

## 10. Repair round 4

The review of the repair round 3 tree (40 items: corpus, invariants, adversarial and re-run lenses) and what this round did
about each. Tests are the files named `test_repair_round4_*.py` and `tests/branches/test_annotation_strip_linear.py` (and
the stricter pins named in each row); every class has its positive case and its clean control, written for this round in
wording of its own. The hold-out was not read.

| Item | What was wrong | What changed (cause) | Tests |
| --- | --- | --- | --- |
| FA-TASK-EITHER-OR-REFUTED | an either/or the task states was refuted as the translation's connective | an "or" (or an exclusive one with its word of exclusion) a task sentence states is a rule it states; a near statement is unvalidated (3.2). Partly resolved: the review's probe is clean, the hold-out control itself is still flagged (sections 6 and 7) | `translate/test_repair_round4_grounding.py` |
| INV-Q1 | correction and suggestion frames hid altered quotations in any task | the roles are read only in marking, feedback, correction, proofreading and editing tasks, set by the channel from the plan (3.3) | `adapters/test_repair_round4_quotations.py`; `adapters/test_quotation_roles.py` and `contract/test_quotation_stub.py` rewritten stricter |
| INV-Q2 | the response gate showed such an answer as verified | the same cause: the altered quotation is checked and named, and the gate withholds the answer | `adapters/test_repair_round4_quotations.py` |
| ADV4-01 | a Celsius temperature in a law that needs kelvin passed | the laws of the absolute temperature (`stem/reference_data.py`, `ABSOLUTE_TEMPERATURE_LAWS`: pV = nRT and the combined gas laws, ΔG = ΔH − TΔS, E = (3/2)kT, the Stefan-Boltzmann law and Wien's law; `relations.applies_absolute_temperature_law`): a temperature written in °C or °F and substituted for their T is read in kelvin (`relations._kelvin_binding`), so the unconverted substitution fails as a unit error (INT-SUBJ-004, `stem_unit_error`) | `stem/test_repair_round4_stem.py` |
| ADV4-02 | a time given only in the request in minutes or hours passed unconverted | a numeral the working already writes in SI ("240 000" for the request's "240 kJ", "2000" for "2.0 kW") is accounted for as that quantity converted (`relations._si_form_binding`), so the other numerals are read with the request's units and an unconverted time fails as a unit error | the same |
| ADV4-03 | words the text does not use were read as invented quotations | mention frames: avoids, omits, leaves out, could have used, chose not to use, instead of using (3.3) | `adapters/test_repair_round4_quotations.py` |
| LEAP-NAMED-ONLY-BY-NONDISCRIMINATING-RECORD | the hold-out's leaps were named only by an info record | left: a leap about one named subject is not told from a sound link by word overlap (measured, section 7) | none |
| E2E-HI-MENTION-READ-AS-OWN-ARITHMETIC | a quoted line of another report was checked as the answer's arithmetic | an equation whose relation sign stands inside quotation marks is a mention (`packs._worked_view`); a premise cited only to a peer's report is unvalidated, not refuted (3.2) | `branches/test_repair_round4_mentions.py`, `translate/test_repair_round4_grounding.py` |
| E2E-CS-SOURCE-MISMATCH-ON-DERIVED-COUNT | a count read off a quoted list was charged as a source mismatch | the count of a stated list, and an indexed lookup over it, ground their figures (3.2) | `translate/test_repair_round4_grounding.py` |
| E2E-CS-FALSE-BARE-ASSERTION | a check tip was read as the section's judgement | a check tip's "should" is no judgement (`generic_parser._CHECK_TIP_RE`) | `branches/test_repair_round4_mentions.py` |
| E2E-BI-UNCHECKED-SOURCE-ON-DERIVED-FIGURES | the count and the expected count of a stated list were unchecked task figures | the count, total and mean of a stated list ground their figures, in every list form (a last item after "and" included: `grounding._closing_list_gap`) (3.2) | `translate/test_repair_round4_grounding.py` |
| E2E-MAA-TASK-INSTRUCTION-GIVEN-UNCHECKED | a conversion given in an instruction's parenthesis was unchecked | `relations.stated_conversion` (3.2) | the same |
| INV-D1 | the docs did not match the quotation roles | 3.3 describes the roles as implemented, scoped to tasks | none (documentation) |
| ADV4-04 | corrected forms of marking feedback were unverifiable quotations | feedback frames ("becomes", "it should read", "the corrected sentence is", "rewrite it as", a "Model:" label governing the span after it) in feedback tasks; a prescribed quotation of a text stays checked | `adapters/test_repair_round4_quotations.py` |
| ADV4-05 | a lowered initial capital fails grounding | left: pinned quotation-form rule (section 7) | none (a reverted attempt) |
| ADV4-06 | a task fact restated with its pronoun resolved or in the passive was refuted | the role pattern reads the sentence in active order (3.2); giving the act to another agent stays refuted | `translate/test_repair_round4_grounding.py` |
| ADV4-07 | blatant "A, so B" leaps were named only at info | a sentence that only names the two things no longer bridges a leap between them (3.1); the one-subject shape is left (section 7) | `translate/test_repair_round4_leap_bridge.py` |
| ADV4-08 | three naming gaps (one comparative after a relative clause; "light" as radiation; "did not work" for "ineffective") | ARG-CL-001, ARG-EQ-003 and ARG-CIRC-003 readings (3.1); the cue tables gain the "light" cues and one synonym group | `engine/test_repair_round4_argument.py`; `engine/test_argument_diagnostics.py::test_the_cue_tables_are_pinned` (the added data pinned exactly) |
| ADV4-09 | the new checks made a claim about 2.8 times slower | the answer's working is read once per text and the records' figures once per value (`grounding._calculation_steps`, `_records_state`), with the same results (section 6) | `translate/test_repair_round4_grounding.py` |
| rerun-fidelity-1-variant-same-sentence | one sentence stating two quantities verified one with the other's figure | the distinguishing words of each subject, and months and days, are read within a sentence or a table line (3.2) | `translate/test_repair_round4_grounding.py` |
| rerun-combinator-faults-8-variant-decimal-grouping | one figure in two notations was two figures | spaced decimals, apostrophe thousands, caret exponents, a unit's caret exponent, a spaced minus (3.3) | `integrity/test_repair_round4_ledger.py` |
| rerun-combinator-faults-7-variant-parallel-paraphrase | a paraphrased parallel step was a figure swap | a swap is charged only when the synthesis's words around it are no source statement; truth-table rows against table cells (3.3) | the same |
| rerun-combinator-faults-5-variant-post-attribution | credit after a quotation was not read | `sources._credit_after` (3.3) | the same |
| rerun-combinator-faults-3-variant-short-selfcert | short and symbolic self-certification passed | `markdown.SELF_CERT_RE` (3.3) | the same |
| rerun-stem-soundness-12-variant-neutral-request | a false identity was checked only under a cue word | an identity's shape is checked under any request (`relations._identity_shape`, `_cued_identity`); a request asking for values is excluded, and an equation solved later is no identity | `stem/test_repair_round4_stem.py` |
| rerun-parser-safety-13-variant-grouping-and-scale | space-grouped figures and a scale word against scientific notation misread | the general reader reads space groups and scale words with scientific notation, and compares a scaled figure with a whole one of the same noun phrase (`quant._same_noun_phrase`, `_sci_pair_number`) | `branches/test_repair_round4_quant.py` |
| rerun-stem-precision-11-variant-other-subjects | a line of correct arithmetic was "no answer" outside STEM | a worked calculation is answer proper in every subject (`bus._worked_calculations`) | `channel/test_repair_round4_answer_words.py` |
| rerun-parser-safety-3-variant-generic-parser | a whitespace run was quadratic in the generic parser | the trailing-annotation reader is linear (`generic_parser._strip_annotations`, `_trailing_annotation_span`) | `branches/test_annotation_strip_linear.py` |
| rerun-formal-robustness-1-variant-squaring-chain | a chain of squarings held a solver call far past its timeout | the values a nonlinear problem's products force are bounded from the IR (`policies.forced_value_digits`, `MAX_FORCED_VALUE_DIGITS` = 2,000), E307 before compiling; the bound is in the policy manifest | `engine/test_repair_round4_engine.py` |
| rerun-fidelity-4-variant-split-restatement | a restatement split across two premises escaped E112 | the candidates are tested together once when none restates the point alone (3.1) | the same; `engine/test_rerun_review_runner.py` and `engine/test_repair_round2_restatement.py` rewritten stricter |
| CASE-LEAP-LL-SLOGAN-REPORT | a hold-out case cites no supports | left: read-only corpus (section 7) | none |
| E2E-CS-IDENTITY-PROOF-NAMED-VACUOUS | a required identity proof was named vacuous | a proof over no premise at all is an info record (3.1) | `engine/test_argument_diagnostics.py` |
| INFO-NAMED-DEFECTS-ON-CONTROLS | release notes named a defect for capped records | capped diagnostics are listed under their own line with their cap and no label, still blocking (section 2) | `contract/test_release_rules.py` rewritten stricter |
| INV-T1 | a timing test failed under load | documented (section 7); bounds kept | none |
| INV-B8 | an unlinked judgement is named only at info | left: pinned decision B13 (section 7) | none |
| ADV4-10 | a one-sentence point of the generic parser was "supporting" | a paragraph's one live claim that states its own reason is its own point, material (3.1) | `branches/test_repair_round4_materiality.py` |
| ADV4-11 | values the request gives were "no stated value" for a law | a bare numeral substituted for a symbol the request states with an SI unit ("radius 5.0 m", "a mass of 0.20 kg") carries the request's unit, and π or e written as a rounded decimal ("3.14") aligns with the symbol (`stem/nodes._rounded_constant`): a wrong area formula is named by its dimension (ST-DIM-001), and a correct period raises no ST-UNDEC-002 | `stem/test_repair_round4_stem.py` |
| ADV4-12 | a figure credited to a data table that states otherwise was misnamed or unchecked | CORE-SRC-007 (3.3); a chained trend read link by link (`quant._CONT_ADVERB`, `_unread_figure_between`) | `branches/test_repair_round4_table_figures.py` |
| ADV4-13 | a pronoun conclusion hid a one-sentence argument from the rules | a pronoun subject counts as a word of the conclusion (3.1) | `translate/test_repair_round4_eligibility.py` |
| rerun-security-2-variant-agent-labels | agent labels escaped the peer test | author and provenance read as words (3.2) | `translate/test_repair_round4_peer_labels.py` |

Tests rewritten to a stricter rule (each named in its row): `tests/adapters/test_quotation_roles.py` (the roles are read in
a task, and outside a feedback task every frame leaves the span a quotation), `tests/contract/test_quotation_stub.py` (each
text in its task; the pinned role counts gain the mentions with their reason), `tests/contract/test_release_rules.py`
(capped diagnostics under their own line, no label), `tests/engine/test_rerun_review_runner.py` and
`tests/engine/test_repair_round2_restatement.py` (two bounds of the writer's own that together restate the point are a
circle, E112, where they were a control; a new control: two premises that entail the point without restating it), and
`tests/engine/test_argument_diagnostics.py::test_the_cue_tables_are_pinned` (16 to 17 synonym groups and the "light"
cues, pinned exactly). No test was weakened or removed.

## 11. Repair round 5

The review of the repair round 4 tree (39 items: corpus, invariants, adversarial and re-run lenses) and what this round did
about each. Tests are the files named `test_repair_round5_*.py` (and the stricter pins named in each row); every class has
its positive case and its clean control, written for this round in wording of its own, and each positive case was checked
to fail on the tree before the round. The hold-out was not read.

| Item | What was wrong | What changed (cause) | Tests |
| --- | --- | --- | --- |
| DA-1 | leaps were named only by the info record | two more unbridged-leap shapes (3.1, ARG-NS-003: a ranked cause, an advised action toward a new named thing). Partly resolved: a leap about one shared subject is still not told from a sound link (section 7) | `translate/test_repair_round5_translate.py` |
| ADV5-01 | the leap reader's sentence pattern was quadratic | one linear pass with the old pattern's exact matches (`diag_argument._sentence_spans`); each answer text read once | the same |
| ADV5-02 | a quotation premise was grounded by any occurrence of its excerpt | the clause around the excerpt is read: the opposite polarity, another figure, a planted checker note or no content word refute the literal (3.2) | the same; `translate/test_joined_quotation.py` rewritten stricter |
| ADV5-03 | grams against a specific heat per kilogram passed | the task's unit is traced through the working (3.4) | `stem/test_repair_round5_stem.py` |
| ADV5-04 | a contradictory given written inline passed | inline givens are read against the request (3.4) | the same |
| ADV5-05 | a conclusion from a rounded value passed in common shapes | the rounding shapes and targets are read (3.4) | the same |
| ADV5-06 | "½mv" was read as one symbol | adjacent quantity letters are a product (3.4) | the same |
| ADV5-07 | one symbol for two quantities passed | rebinding by dimension (3.4) | the same |
| ADV5-08 | single words quoted as mentions were invented quotations | the mention frames of 3.3 | `adapters/test_repair_round5_quotations.py`; `contract/test_quotation_stub.py` gains one pinned mention with its reason |
| rerun-combinator-faults-7 (weakened swap check) | a swap whose telling word stood far before the figure was excused | copied context is read back to the sentence start; `context_swaps` (3.3) | `integrity/test_repair_round5_ledger.py` |
| rerun-fidelity-2 (cross-multiplied) | a ratio encoded cross-multiplied escaped the precision decision | `precision._bound` and `_scaled` read "L >= c*S and L < d*S" as a ratio site; the scale is kept in rewrites | `translate/test_repair_round5_translate.py` |
| DA-2 | a prefixed option word negated a stated either/or | only negation words negate the list (3.2) | the same |
| DA-3 | a report point with unlinked evidence was caught but unnamed | left: the case's report cites no supports and its paired control has the same structure (section 7) | none |
| DA-4 | defect labels on clean answers at info | figure relations are no longer named leaps (INV-LINK-1); the interpretive-link record is pinned by design (section 7) | `engine/test_repair_round5_engine.py` |
| DA-5 | "in A" read as the ampere | a parenthesised unit gloss is the declared unit (3.2); the rest of the item (non-defect structure codes and info-only names on a corpus this round may not read) is left (section 7) | `translate/test_repair_round5_translate.py` |
| ADV5-09 | a definition the task states was refuted | definitions and closed enumerations are stated rules (3.2) | the same |
| ADV5-10 | ST-WORK-001 on reasoned proofs | a reasoned answer to a property show-that, or a yes/no "calculate whether" answered with the request's figures, is no missing working (3.4) | `stem/test_repair_round5_stem.py` |
| ADV5-11 | a definition in another part was a bare assertion | ARG-BARE-001 reads only the parts whose items ask for reasons (3.1) | `translate/test_repair_round5_translate.py` |
| ADV5-12 | a word count was a self-certification in the ledger | INT-LEDGER-029 skips word-count lines (3.3); the report side's pinned compliance reading is unchanged | `integrity/test_repair_round5_ledger.py` |
| ADV5-13 | the new checks cost about 1.6 times the CPU time | pure readers cached (`lexis.stem`, `lexis.root`, `quantities.stated_exactness`, `grounding._enclosures`), a derived run of bound premises skips the consistency check the engine already made, one token read per text in `symbol_senses`. Partly resolved: measured in section 6 | `engine/test_repair_round5_engine.py` |
| ADV5-14 | a lowered initial capital fails grounding | left: pinned quotation-form rule (section 7) | none |
| ADV5-15 | four naming gaps | (a) cases named by a list or a label are instances (ARG-HG-001); (b) a causative verb with a result comparative is a cause (ARG-CL-001); (c) a reason clause that restates its point is ARG-CIRC-003 in the report layer, and "boring", "tedious", "dull", "monotonous" form one synonym group; (d) left: nonlinear arithmetic (section 7) | `engine/test_repair_round5_engine.py`, `translate/test_repair_round5_translate.py`; `translate/test_argument_rules.py` and `engine/test_argument_diagnostics.py::test_the_cue_tables_are_pinned` pin the added rule and group exactly |
| ADV5-16 | an extrapolation far beyond chemistry data passed | unit homographs never continue a unit (3.4) | `stem/test_repair_round5_stem.py` |
| rerun-fidelity-1 (list and qualifier) | an excerpt verified one quantity with another's figure | list items, comma-cut qualifiers and table cells are read (3.2) | `translate/test_repair_round5_translate.py` |
| rerun-parser-safety-11 (generic lists) | list answers were quadratic in the generic parser | lines and paragraphs read once, supports indexed and found by bisection, earlier sentences grown in one pass | `branches/test_repair_round5_generic_lists.py` |
| rerun-stem-soundness-10 (nested ±) | a correct "±" chain was charged | a "±" equation is two equations (3.4) | `stem/test_repair_round5_stem.py` |
| rerun-robustness-and-contracts-7 (nested JSON) | a nested envelope was "no answer" | envelopes nested up to four levels and one envelope tag are unwrapped | `channel/test_repair_round5_channel.py` |
| rerun-robustness-and-contracts-8 (truncated) | a cut structured reply was read as prose | an unclosed Python-notation envelope, an unclosed tag or a JSON report after prose is INT-REQ-009 | the same |
| rerun-combinator-faults-3 (status forms) | short status forms passed | the forms of 3.3 | `integrity/test_repair_round5_ledger.py` |
| rerun-combinator-faults-5 (credit forms) | credit forms escaped the miscredit check | the credit forms of 3.3 | the same |
| rerun-combinator-faults-7 (ordinal labels) | numeral step labels were introduced figures | step labels compared in any notation (3.3) | the same |
| rerun-combinator-faults-8 (notations) | accounting parentheses and precision notes were figures | both are notations (3.3) | the same |
| rerun-security-2 (labels) | relayed labels were primary sources | the labels of 3.2 | `translate/test_repair_round5_translate.py` |
| DA-6 | the measured tree's base was not stated | stated below (traceability) | none (documentation) |
| INV-DOC-1 | the contract's section 8 example did not match the code | the example now shows the CLI's output, with its named record (`docs/integration-contract.md`) | none (documentation); `engine/test_repair_round5_engine.py` pins the record |
| INV-LINK-1 | a figure relation was named the writer's leap with an empty consequent | figure relations are listed with the facts (3.1) | `engine/test_repair_round5_engine.py` |
| INV-QROLE-1 | a report's own task type widened the quotation roles outside the channel | the record's task type is advisory (3.3); `check-report --task-type` states it | `adapters/test_repair_round5_quotations.py`, `service/test_repair_round5_cli.py` |
| ADV5-17 | a source figure encoded at its written precision was refused | left: pinned exactness rule (section 7) | none (a reverted attempt) |
| ADV5-18 | N₀ stated in a sentence was "no stated value" | the request's count binds N₀ (3.4) | `stem/test_repair_round5_stem.py` |

The measurement (section 6) found three false alarms that this round's readings make on genuine answers of the arena
replay (an excerpt of function words analysed as words, a figure after a lead phrase, a summary that skips an
intermediate value); they are left as found and described in section 7, since no code was changed after the measurement.

Tests rewritten or extended this round, each to a rule at least as strict: `tests/translate/test_joined_quotation.py` (the
negated literal whose excerpt states the atom is refuted, where it was verified), `tests/contract/test_quotation_stub.py`
(one more pinned mention, with its reason; every other role unchanged and still pinned exactly),
`tests/translate/test_argument_rules.py` (the report rules pinned exactly, with the added rule) and
`tests/engine/test_argument_diagnostics.py::test_the_cue_tables_are_pinned` (17 to 18 synonym groups, pinned exactly). No
test was weakened or removed.

Close round 1 (section 12) narrowed five readings of this round at their cause: the placeholder rule of ADV5-02 (a literal
about the excerpt's own words), the subject reading of rerun-fidelity-1 (a figure of the same value, or of the opposite
part), the copied-context reading of rerun-combinator-faults-7 (a figure kept with its own words), the negated-verb mention
frame of ADV5-08 (one quoted word; a credit after the span) and the status forms of rerun-combinator-faults-3 (the same
forms, read in linear time). No test of this round pinned a regressed behaviour, so none was rewritten.

Close round 2 (section 13) reverted the contrast frames of the mention reading ("unlike" of ADV5-08, with "rather than" and
"instead of") to the committed base's reading, since the mention frames had been narrowed by close round 1 (DIFF-02). The
case of `tests/adapters/test_repair_round5_quotations.py` that pinned the span after "unlike" as a mention ('Unlike
"tumbled", the verb "bend" is slow') pinned that regressed behaviour, so it is rewritten to the stricter base behaviour:
both spans are quotations and are checked. The test says so beside the case and in its docstring; no other case of the
file changed.

Close round 3 (section 14) reverted the negated-reporting-verb frame of the mention reading of ADV5-08 ('never writes
"roared"', 'the text never says "ayudar"') to the committed base's reading, since the mention frames had been narrowed by
close round 1 and the frame, with one word allowed before its verb, also took 'not only writes "..."' and 'does not just say
"..."' out of the checks (INV-QR-1). Three tests pinned that regressed behaviour and are rewritten to the stricter base
behaviour (the span is a quotation and is checked), each saying so beside the case and in its docstring:
`tests/adapters/test_repair_round5_quotations.py` (the "never writes" role case, and its delivered-answer case, moved to a
test that asserts the invented word is named), `tests/adapters/test_close1_quotation_roles.py` (the same sentence, moved
out of the controls that stay mentions into a test of its own) and `tests/contract/test_quotation_stub.py` (the pinned
mention of "ayudar" is gone from the pinned roles: the span is a quotation; every other role is unchanged and still pinned
exactly). No other case changed, and no test was weakened, skipped or removed.

**Traceability** (DA-6). The measured tree is the commit `7991e8b` (the verified line `22d6a5b` and the eleven commits after
it: the end-to-end fixes `0d28eba`, `dae3265` and `8a78efe`, and eight progress notes) with the argument-diagnosis
integration and its five repair rounds staged on top, uncommitted; the staged diff is relative to `7991e8b`. Commits made
on the development branch after `7991e8b` by other work are not part of this tree.

## 12. Close round 1

The regression review of the repair round 5 tree compared it with the committed base (`7991e8b`) input by input against
the correct outcome, and found 16 items on which it was worse than the base. This round closes each at its cause, so that
the new reading fires, or stays silent, only inside the class it was written for; no reading was reverted, and three
narrowings give up part of what the round-5 reading also caught (ADV6-02, ADV6-07, arena r7 lit-t13: section 7, "Left by
close round 1"). The review's
GAP and IMPROVED items, which the base fails the same way, are not changed and are listed in section 7 for round 8. Tests
are the files named `test_close1_*.py`; each positive case was checked to fail on the tree before the round and each
clean control passes, in wording of this round's own. The hold-out was not read to tune a rule.

| Item | What was wrong | What changed (cause) | Tests |
| --- | --- | --- | --- |
| ADV6-01 | a source rule the excerpt states only hedged ("prices might fall"), framed or denied ("It is a myth that ..."), as a question, with a part of its condition the premise drops, with an "or" in its consequence, limited by an opening phrase or restricted after it was verified as stated (`relation_in_source` True), so a wrong conclusion was released; the base blocked it only by an unrelated refusal | `stated_rules.rule_qualifier` reads those shapes (3.2): the located excerpt refutes the premise (EVD-SRC-003, `source_mismatch`, not releasable), and a record sentence of such a rule validates no task-authority rule; a hedge, a restriction or a view the premise's own meaning writes is its own, and the plain rules of the controls are still verified and released | `translate/test_close1_stated_rules.py` |
| ADV6-02 | a magnitude stated after its own signed chain ("= −4.0 m s⁻², so the deceleration is 4.0 m s⁻²") was checked as a restatement and failed (INT-SUBJ-001 error, the answer withheld) | `relations._Planner._results`: a value of the other sign than its own statement's chain is no restatement; one of the same sign is checked as before (3.4). Given up: a wrong magnitude in that statement goes unchecked, as on the base (section 7) | `stem/test_close1_stem.py` |
| ADV6-08 (security) | `SELF_CERT_RE` was quadratic or cubic in a hostile whitespace run (two optional runs around an optional bracket or mark) | every run consumed once (possessive quantifiers), the elliptical status list read as words and separators; the old answer on every string of a 900,000-string differential check (3.3) | `adapters/test_close1_selfcert_linear.py`: 14 hostile shapes of 60,000 characters each under a second, a doubling ratio, the 20 forms the pattern names and 7 controls |
| INV7-1 | a task sentence with the premise's words at another time ("next year", "this year" for "last year") validated the premise, and the opposite direction ("cut" for "raised") left it only unvalidated | `grounding._task_conflict`: another time, another tense or the opposite direction of change is no statement of the premise; a sentence that states the conflict refutes it (`content_in_task` False, a failed grounding check), one that leaves the premise's time undated does not validate it, and deictics of one time ("the past year", "last year") are no conflict (3.2) | `translate/test_close1_task_facts.py` |
| rerun-verify6-weakened-negated-quotation-mention | any span of up to three words after a negated verb was a mention, so an invented span credited to the source ('The king does not "rule with mercy", as the chronicle claims') was never checked | the negated-verb frame is a mention for one quoted word only, and a credit to a source right after a span keeps it a quotation (3.3) | `adapters/test_close1_quotation_roles.py` |
| arena-r1-hi-t1-synthesis-INT-LEDGER-023 | a summary that skips an intermediate figure ("from 2.6 per cent in May 1928 to 37.3 per cent in July 1932") was charged a swap (error) | `ledger._states_own_figure`: a figure whose words after it are a source's own statement of it is no swap; a figure spliced into another statement's words still is (3.3) | `integrity/test_close1_ledger.py` |
| ADV6-07 | a rate ("0.08 °C per year"), a step or a result in prose ("13.3 A") was read as the model's input and named an extrapolation on correct work | a prose value is an evaluation point only after an input cue and with no rate after it (`relations._INPUT_BEFORE_RE`, `_RATE_AFTER_RE`; 3.4). Given up: an evaluation written as an attribute ("a 40 N load ...") is not read (section 7) | `stem/test_close1_stem.py` |
| ADV6-09 | the month "May" was read as the modal: a task sentence dated in May was suspended, a correct answer was named `unchecked_source` (EVD-SRC-001), and a rule "... in May" read as hedged | a capitalised "May" inside a sentence is the month (`grounding._suspending_tokens`, `stated_rules._hedge_word`); the defect twin is named for the restriction its excerpt cuts off (3.2) | `translate/test_close1_stated_rules.py` |
| rerun-verify6-parser-safety-3-regression-selfcert (security) | the same pattern on the hub's path (a History answer with a 20,000-space run: 24.9 s) | as ADV6-08 | `adapters/test_close1_selfcert_linear.py::test_a_history_answer_with_a_long_whitespace_run_is_received_quickly` |
| arena-r2-en-t4-INT-ARG-001+EVD-SRC-003 | an excerpt of the very words the premise analyses ("it was the") was refuted as a placeholder | `grounding._names_words`: a literal whose meaning or label quotes the excerpt's words, names them after a noun of naming, or names the one pronoun they are after a verb of use, is about them (3.2); an excerpt of function words cited for a fact ("used the frozen river" for "the") is still refuted | `translate/test_close1_grounding_words.py` |
| arena-r6-en-t11-INT-ARG-001+EVD-SRC-003 | the same for the pronouns "she" and "I" | the same | the same |
| arena-run1-ec-e1-INT-ARG-001+EVD-SRC-003 | the excerpt that states the pre-tax price was refuted because a table repeats that price and states the price after the tax | another figure of the same value and unit, or one stated for the opposite part, gives the premise's quantity no other figure (`grounding._subject_conflict`, 3.2); a different figure for the same quantity still refutes | the same |
| arena-r7-lit-t13-INT-ARG-001+ARG-CIRC-001 | a report heading that restates the task question was named a circle at warning | ARG-CIRC-001 is an info record when every restating premise claims the task's authority, the claim gives no reason, and the encoding grounds its point on the task too or the claim only restates the task (3.1); the refusal stands and nothing becomes releasable; a reason given, or a point of the writer's own under the task's label, stays a circle at warning. Given up: a circle labelled throughout with the task's authority, in a claim with no reason, is recorded at info (section 7) | `translate/test_close1_circular.py`; `translate/test_argument_rules.py` keeps its pin unchanged |
| V6-DA-05 | the rule text of the leap reader (repair round 5, DA-1) quoted names found only in the hold-out | the examples in `diag_argument.py` and `engine/argument.py` are written for the rules; no hold-out-only name is left in the source | `translate/test_close1_rule_examples.py` |
| the carried INT-HIST-001 of r2 en-t4, r6 en-t11 and r7 lit-t13 | the syntheses carried the false findings above | closed with their causes; INT-HIST-001 is unchanged | the tests of the rows above |
| the 22 injected-variant records of en-t4, en-t11, ec-e1 and lit-t13 | each variant carried the genuine claim's false finding | closed with their causes; the planted faults stay caught (measured below) | the same |

No existing test was rewritten, weakened or removed this round: no pinned test held a regressed behaviour, and the
ARG-CIRC-001 narrowing is written so that the pinned warning of
`tests/translate/test_argument_rules.py::test_a_restated_task_premise_is_a_circular_refusal_unless_a_check_validated_it`
stands. The versions are unchanged (section 7, "Left by close round 1").

**Measured** (once, at the end, on a fresh copy of the staged tree; section 6 holds the earlier rounds' measurements):
- **Suite**: 8847 passed, 1 failed and 45 deselected (the stress selection, not run) in 457 s, one serial run. The failure is
  the wall-clock bound of `tests/engine/test_stem_shapes.py::test_median_time_per_shape_is_below_50_ms` (51.6 ms against
  50 ms for one shape, on a host where another workload held two of the four cores); run alone on the same copy it passed
  three times of three, as on the repair round 5 tree. The bound is not relaxed.
- **Development corpus** (101 cases): 44 of 44 defects named, 57 of 57 controls clean, 47 controls not releasable. No case is
  worse than on the committed base (9 named, 41 false alarms there), and every verdict is that of repair round 5.
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 64 of 66 defects named, 2 caught but not named,
  none missed; 68 of 68 controls clean, 37 not releasable. No case is worse than on the base (13 named, 23 false alarms
  there); one verdict differs from repair round 5: `ho_d_extrap_phys` is caught but no longer named, its base verdict
  (section 7).
- **Arena replays** on fresh copies: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177, run1 120/134 functional,
  each count the base's. Compared with the base answer by answer, close round 1 adds no difference that the repair round 5
  tree did not already have; the review's 29 regression records give the base's outcome (28 identical; the r6 en-t11
  synthesis keeps only the channel history's carry of ES-STR-001, a finding the base raises on its source receipt); no
  planted fault loses its detection (no record is functional on the base and not on this tree); and the 9 findings at
  warning on genuine answers that the base does not raise are the review's IMPROVED items (ARG-BARE-001 on a lone-quotation
  answer, translation-fault records on r7, INT-REQ-017 on two relayed answers).
- **Repros**: each item's repro, run on the fresh copy and on the committed base, gives the base's outcome or a stricter one
  (ADV6-01: 22 defects named `source_mismatch` and the three controls clean and releasable, where the base flagged two
  controls and released one defect; INV7-1: the stated fact validated, the three misread premises refuted; ADV6-09: the
  control clean and releasable, the twin named; ADV6-02, ADV6-07 and the arena records: clean as on the base).
- **Cost of the security items**: `SELF_CERT_RE` reads runs of 10,000 and 40,000 spaces in 0.013 and 0.038 s (the base's
  pattern 0.005 and 0.018 s: 2.0 to 2.7 times, linear); a History answer with a 20,000-space run is received in 0.41 s
  (the base 55 s, the repair round 5 tree 24.9 s).

After the measurement only documentation changed (this section, section 7's references to it and
`REVIEW_FIXES_README.md`).

**Traceability.** The measured tree is the commit `7991e8b` with the argument-diagnosis integration, its five repair
rounds and close round 1 staged on top, uncommitted; the staged diff is relative to `7991e8b`.

Close round 2 (section 13) reviewed this tree against the committed base the same way; its 9 items, and what was closed,
reverted or left, are there.

## 13. Close round 2

The regression review of the close round 1 tree compared it with the committed base (`7991e8b`) input by input against the
correct outcome, and found 9 items on which it was worse than the base (one a security item). This round works under a
convergence rule: a reading that close round 1 had already narrowed, or that would have to be narrowed a second time, is
not narrowed again; its effect is reverted to the base's reading for its whole class, the regression test keeps the
base's outcome, and the improvement given up is recorded (section 7, "Left by close round 2"). A reading no close round
had touched is narrowed only by a plain restriction (a smaller trigger set), never by a new reading, and the security item
is made linear with a timing test. Tests are the files named `test_close2_*.py`; each positive case was checked to fail on
the tree before the round and each clean control passes, in wording of this round's own. The hold-out was not read to tune
a rule.

| Item | What was wrong | What changed (cause) | Tests |
| --- | --- | --- | --- |
| SEC-QROLE-QUADRATIC (security) | the quotation-role reader (`markdown._span_roles`, read six to nine times per answer) read the whole line before each span and every earlier span for each span, and its gap patterns read a long run of spaces again from every position of it: quadratic in the spans of one line (an English feedback answer of 189,000 characters took 46 s of CPU against the base's 5.2 s) | closed, linear: line starts, the sentence marks of each line and the label heads are read once per text (`markdown._LineIndex`), an earlier correction on a span's line is known from the end of the last correction span, the gap patterns are possessive (each run consumed once), and one answer's roles are read once however many readers ask (`markdown._roles_cached`). The roles are the old reader's (a differential check on 4,000 random label lines and on the role lists of every span of the generated hostile texts) | `adapters/test_close2_quotation_roles.py`: five hostile shapes at four times the size within eight times the time and under 6 s, runs of 200,000 spaces between two quotations under a second, one answer read once |
| DIFF-02 | a short span after "unlike" or "rather than" was a mention and never checked, so an invented quotation presented as the text's own words passed (the base named it: INT-REQ-003, ES-SRC-001, CORE-SRC-003) | reverted under the convergence rule (the mention frames of ADV5-08 had been narrowed by close round 1): a span after a contrast ("unlike", "rather than", "instead of") is a quotation and is checked, as on the base; the frames that say the words are absent ("without", "with no", "no") keep their mentions (3.3) | `adapters/test_close2_quotation_roles.py` (controls: real quotations after a contrast, mentions after "without", "with no" and "no"); `adapters/test_repair_round5_quotations.py` rewritten stricter (section 11) |
| REG-CIRC-TASK-PROPOSITION | a proposition the task quotes for the student to weigh ("'X.' Discuss.", "X. To what extent do you agree?") validated a `task_setting` or `rubric_rule` premise restating X (the stricter `content_in_task` reading repair round 4 gave a premise that shares an atom with the point, ADV4-06), so 'X, as the question states; therefore X' cleared with no E112 and was releasable; the base named the circle (issue 1) | reverted under the convergence rule (the task-fact reading had been narrowed by close round 1, INV7-1): a premise that shares an atom with the point is never validated by a task sentence (`grounding._literals_in_task`) and is left to the circularity rules, as on the base (3.2) | `translate/test_close2_task_proposition.py` (four prompt forms, both task kinds; controls: a task fact that grounds another point is validated, a reported view restated as the point stays a circle) |
| DIFF-04 | a wrong Boolean step written with the AND dot and a constant ("Since A.0 = A, we get A.B + A.0 = ...") went unchecked: the dot before the constant stayed a decimal point to the lexer, the expression was read only in part, and the guard against a relation cut from a longer expression withheld the rest; the base charged it (INT-SUBJ-001) | narrowed (the AND-dot reading of re-run review stem-soundness-4, untouched by close round 1): an answer that writes a Boolean constant with the AND dot (`lexer.writes_constant_dot`) is read without the AND dot and without the glued-dot guard (`checks._truncated_operand`), as before both readings, so the base's check names the step again; every other answer keeps the AND dot (3.4). What this gives up is in section 7 | `stem/test_close2_boolean_dot.py` (controls: a correct absorption written with the AND dot stays checked and clean; the correct step "A.0 = 0, so A.B + A.0 = A.B + 0 = A.B" raises no error) |
| DIFF-06 | "about 300" for a stated 260, compared over `to_real` of a count, was AMBIGUOUS_TRANSLATION (`stated_precision`) and not releasable: the open precision of a trailing-zero whole number also read it at half a unit of its last digit; the base, and the same claim over Int, showed it ENTAILED | narrowed (the open-precision reading, untouched by close round 1): a term that takes only whole values (`precision._takes_whole_values`: Int symbols, integer literals, sums, differences, products, negations, integer quotients and remainders of them, perhaps cast to a real; a bounded walk) is read at its first significant digit alone, as over Int; a ratio or a measured quantity keeps both readings | `translate/test_close2_precision_counts.py` (controls: the same count over Int; "about 100%" for a growth of 52% stays AMBIGUOUS_TRANSLATION and not releasable) |
| DIFF-05 | syntheses and peer relays carried, as INT-HIST-001, findings their source receipts raise falsely in both trees, so the base's clean transmissions read with warnings (13 syntheses with layout findings, one synthesis with an error, six peer relays) | closed in part, narrowed (INT-HIST-001, untouched by close round 1): a synthesis, which restates the claims it cites and not the report's paragraphs, carries no subject finding about paragraphs or sentence style (`bus._LAYOUT_PREFIXES`: ES-STR-, ES-STY-, HI-STR-; 3.5); the relays and the synthesis carry of a flagged claim are left (section 7) | `channel/test_close2_synthesis_layout.py` (controls: a relay names the finding again and a forward carries it; a synthesis still carries a failed Given check) |
| DIFF-01 | a plainly stated source rule with a hedge, an "or", a negation or a frame word elsewhere in its sentence was refuted as `source_mismatch` (warning, not releasable) | left: the cause is close round 1's `rule_qualifier`; it may not be narrowed again, and reverting the stated-rule reading would reopen ADV6-01 (section 7) | none (left) |
| DIFF-03 | an excerpt that negates the rule's consequence left the premise unvalidated instead of naming `source_mismatch` | left: naming it needs a new refutation reading; the base flags it only through its refutation of a true task fact (section 7) | none (left) |
| DIFF-07 | the hold-out leap `ho_d_leap_bm_since` is named at info only, where the base flags it at warning | left: the base's flag is its CORE-QNT-001 false error (B25); naming it at warning would widen the connective reading, on a hold-out case (section 7) | none (left) |

Tests rewritten this round: the "unlike" case of `tests/adapters/test_repair_round5_quotations.py`, to the stricter base
behaviour (section 11). No test was weakened, skipped or removed. The versions are unchanged (section 7, "Left by close
round 2").

**Measured** (once, at the end, on a fresh copy of the staged tree; the base's corpus and arena figures are the review's
runs on the committed base, and the repros and timings were run on the base beside this tree):
- **Suite**: 8912 passed and 45 deselected (the stress selection, not run) in 453 s, one serial run, no failure.
- **Development corpus** (101 cases): 44 of 44 defects named, 57 of 57 controls clean, 47 controls not releasable. Every
  verdict is close round 1's, and no case is worse than on the committed base (9 named, 41 false alarms there).
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 64 of 66 defects named, 2 caught but not named,
  none missed; 68 of 68 controls clean, 37 not releasable. Every verdict is close round 1's, and no case is worse than on
  the base (13 named, 23 false alarms there); the one defect mode the base flags and this tree does not is
  `ho_d_leap_bm_since` in text mode (DIFF-07, left: the base's flag is its CORE-QNT-001 false error).
- **Arena replays** on fresh copies: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177, run1 120/134 functional,
  each count the base's, and no record functional on the base is not functional here (no planted fault lost). Compared
  with the base answer by answer, the round adds no difference: 12 differences of close round 1 are gone, the INT-HIST-001
  layout carries on the syntheses of r1 en-t1, en-t2 and hi-t2, r3 en-t5, en-t6 and hi-p2, r4 en-t7 and en-t8, r6 en-t11
  and en-t12, r7 en-t13 and hi-t13, and r6 hi-t12's synthesis lost its HI-STR-001 carry and keeps a CORE-SRC-003 one; the
  12 INT-HIST-001 differences left (relays and non-layout carries) are the rest of DIFF-05 (section 7). The findings at
  warning or error on genuine answers that the base does not raise are close round 1's 9, the review's IMPROVED items
  (ARG-BARE-001 on a lone-quotation answer, INT-CONFLICT-005 and INT-GLOSSARY-005 on r7 answers, INT-REQ-017 on two relayed
  answers).
- **Repros** of every item, on the fresh copy and on the base: SEC-QROLE-QUADRATIC, the reading of every role of 8,000,
  16,000 and 32,000 spans on one line takes 0.84, 1.82 and 3.40 s (the review's 2.33, 7.3 and 25.7 s), and the English
  feedback answer of 15,800 to 189,000 characters 0.57, 1.36, 2.50, 4.82 and 7.67 s of CPU through the hub (the base
  0.50, 1.14, 1.73, 3.45 and 4.65 s; the review's 1.04 to 46.33 s); the review's quotation shapes are at most 1.9 times the
  base (rd_quotes_english 8.42 against 4.44 s at 72,000 characters, rd_curly_english 10.45 against 6.93 s at 90,000);
  over the review's 57 hostile shapes of 12,000 to 84,000 characters the median is 1.15 times the base, the highest 3.3
  times on 36,000 characters of grouped digits (rd_space_digits: a bounded cost of no quotation reader, 3.6 against 1.3 s
  on a warm process, which the review measured at 3.1 times before this round) and 3.2 times on 12,000 characters of
  one-character quotations (0.27 s more; 2.0 times on a warm process, 1.7 times at 36,000). DIFF-02: the invented
  quotations after "unlike", "rather than" and "instead of" are named as on the base (INT-REQ-003, ES-SRC-001), the History
  ones caught as on the base (CORE-SRC-003), the real quotations clean. REG-CIRC-TASK-PROPOSITION: the three prompts give
  E112 and ARG-CIRC-001 at warning, not releasable (the base E112, not releasable). DIFF-04: the wrong step is INT-SUBJ-001
  with a failed `stem-bool` check, as on the base. DIFF-06: the count over `to_real` is ENTAILED and releasable, as on the
  base. ADV6-01 is not reopened: every hedged rule of its repro is still named `source_mismatch`. The left items give what
  section 7 says (DIFF-01: 11 controls refuted that the base keeps clean and one held back, its four defects named where
  the base misses three; DIFF-03 and DIFF-07 caught, not releasable, not named at warning).

After the fresh copy was taken, only documentation changed (sections 3, 7, 11, 12 and 13 of this file, the package
READMEs, `docs/DESIGN.md`, `docs/STEM_DESIGN.md`, `docs/integration-contract.md` and `REVIEW_FIXES_README.md`), with one
comment of `adapters/markdown.py` and the docstring of `tests/stem/test_close2_boolean_dot.py`; no code or test logic.

**Traceability.** The measured tree is the commit `7991e8b` with the argument-diagnosis integration, its five repair
rounds and close rounds 1 and 2 staged on top, uncommitted; the staged diff is relative to `7991e8b`.

Close round 3 (section 14) reviewed this tree against the committed base the same way; its 10 items, and what was closed,
reverted, turned into known defects or left, are there.

## 14. Close round 3

The regression review of the close round 2 tree compared it with the committed base (`7991e8b`) input by input against
the correct outcome, and found 10 items on which it was worse than the base (two of them security items). This round
works under the convergence rule of close round 2 (section 13: a reading an earlier close round narrowed, or that would
have to be narrowed a second time, is not narrowed again; its effect is reverted to the base's reading for its whole
class, the regression test keeps the base's outcome and the improvement given up is recorded; a reading no close round had
touched is narrowed only by a plain restriction, never by a new reading; a security item is made linear with a timing
test) and under a discrimination rule: a base outcome counts as a detection only when the base tells the defective input
from its matched correct control (the same input with the defect removed or the premise made true). Where the base flags
the two alike (through its refutation of every figureless task fact, or a false error the staged tree removed), the
staged tree's miss is a known gap: it is listed in section 7 with the control evidence and not fixed. A false alarm on
correct work that the base does not raise stays a regression, whatever the base does on the defective twin. Tests are the
files named `test_close3_*.py`; each positive case was checked to fail on the tree before the round and each clean control
passes, in wording of this round's own. The hold-out was not read to tune a rule.

| Item | What was wrong | What changed (cause) | Tests |
| --- | --- | --- | --- |
| DV2-01 | a task sentence that reports a forecast, hope, fear, promise, plan, estimate or hypothesis ("Analysts expect that ...", "The central bank plans to raise ...", "A student hypothesises that ...") validated a `task_setting` premise that states it as fact, so the answer was released (Economics) | a known defect (section 7): the committed base gives the matched control, in which the task states the fact, the same outcome as the defect (NOT_ELIGIBLE and not releasable in Economics; GROUNDING:FAILED, its refutation of every figureless task fact, in Biology), so its outcome on the defect is no detection; not changed | none (the control evidence is in section 7) |
| DV2-02 | a capitalised "May" in a title-case headline ("Interest Rates In Country Q May Rise Next Year") was read as the month, so the headline validated "... will rise next year" and the answer was released | a known defect (section 7): the base gives the control headline with "Will" the same outcome as the defect; not changed | none |
| DV2-03 | a plainly stated source rule with a hedge or a frame word elsewhere in its sentence ("... and mining firms can hire more staff", "Nobody doubts that if ...") was refuted as `source_mismatch` (EVD-SRC-003 and INT-ARG-001 at warning, not releasable), where the base verifies it and releases the answer | left (section 7): the cause is close round 1's `stated_rules.rule_qualifier`, which may not be narrowed again. A trial revert (the qualifier off) clears the 13 refuted controls of the review's probe sets and makes the 17 cases of `tests/translate/test_close1_stated_rules.py` fail (the hedged, alternative, dropped-condition, framed, questioned, limited, restricted, credited and cut rules it pins as refuted); no test may be weakened | none (left) |
| DV2-04 | a task that sets a supposition ("Assume that X.", "Suppose X.") made correct work that takes X as given raise EVD-SRC-001 (`unchecked_source`) and INT-ARG-001 at warning; the base names nothing | narrowed (EVD-SRC-001, which no close round had touched): a task-authority premise that restates a supposition the task sets (one task sentence in the supposition mood of `assertion.sentence_cue_at` holds every content root of the premise, with its polarity: `diag_evidence._supposed_by_task`) is not named. Its grounding record is unchanged, so the answer stays not releasable on it, as on the base (3.2) | `translate/test_close3_task_suppositions.py` (four supposition forms, another subject and task type; controls: a hedged, a conditional and a reported task sentence, a supposition of something else and one of the opposite polarity still name the premise) |
| DV2-05 | six peer relays and six syntheses carried, as INT-HIST-001, findings their source receipts raise falsely in both trees (three of the carries at error), so the relays read ACCEPTED_WITH_FINDINGS where the base reads ACCEPTED | left (section 7): INT-HIST-001 was narrowed by close round 2 (DIFF-05), and the base has no relay history; a trial revert (nothing carried) makes 20 tests of seven channel files fail that pin the carry of true findings (`test_relay_history.py`, `test_repair_round3_gate.py`, `test_close2_synthesis_layout.py` and four more). The false findings are their source checks' (both trees raise them on the arrival) | none (left) |
| DV2-06 (security) | the synthesis ledger's figure readers cost more than three times the base's time on hostile answers of 10,000 to 36,000 characters (digit groups spaced as thousands, chains of unit figures): the swap reader read again every place of the last copied word for every figure, the figure index listed every figure of a spelling for every figure, and the aligned reading was made twice per synthesized claim | closed, linear: the copied-context swap reader indexes the places of every run of four source tokens and of every source figure with the words after it once and extends a run one token at a time on demand (`ledger._RunPlaces`), skips a figure with fewer than two content words before it, and keeps one reading per sequence of preceding tokens; the figure index keeps one answer per set of spellings and per figure as written (`_FigureIndex`); the aligned reading is kept per pair of texts (`aligned_differences`). A differential check over the 786 ledger inputs of every arena round and their swap, repetition and hostile variants gave the old answers (3.3) | `integrity/test_close3_ledger_linear.py`: digit groups and unit chains of 48,000 characters under 3 s and within eight times the cost of a quarter of the text; 2,000 repeated statements with every swap named under 4 s; controls (a spliced swap, a statement with its own figure, copied words followed once by the synthesis figure, a dropped and a changed figure, the aligned reading copied per call) |
| DV2-07 (security) | the r7 round took 3.1 times the base's time and one r7 answer group 11 to 13 times: a channel decided the same joint consistency problem again on every later transmission (the pool of every report so far, the claim-by-claim attribution of a contradiction it had named, the rest after a contradiction is set aside) | closed in part: a definitive joint result is kept per identical problem, configuration, limits and signing key (`cross_check.verify`), and the same signed result is cited again; an undecided result is decided again; the findings are unchanged (3.3). The r7 round is now 2.4 to 2.6 times the base's time. Left: one r7 answer group still costs 11 to 12 times the base's, the verification of claim outcomes the base's parser never serves (section 7) | `integrity/test_close3_joint_memo.py` (an identical check decided once, citing the same signed result; a growing pool costs its new problems only; controls: another key or configuration is another check, an undecided result is not kept) |
| INV-QR-1 | a span right after a reporting verb under a negation was a mention, with one word allowed between the negation and the verb, so 'not only writes "..."', 'does not just say "..."' and 'not only says "..."' took an invented quotation out of the checks; the base names it | reverted under the convergence rule (the mention frames of ADV5-08 had been narrowed by close round 1): a span right after a negated reporting verb is a quotation and is checked, as on the base (`markdown._NEGATED_ATTRIBUTION_RE` is gone); a negated report with words before the span keeps its mention (3.3) | `adapters/test_close3_quotation_roles.py` (the affirming negations, each named on a delivered answer; controls: negated reports with words before the span stay mentions, a genuine quotation after "not only writes" raises nothing); three tests rewritten stricter (section 11) |
| DV2-08 | "about 300 g" for a stated 260 g, a measured quantity over Real, was AMBIGUOUS_TRANSLATION and not releasable, where the base shows it ENTAILED | left (section 7): the open precision of a trailing-zero figure was narrowed by close round 2 (DIFF-06); a trial revert makes 5 tests fail that pin "about 100%" for a growth of 52 or 55 per cent as never ENTAILED, a doubling decided at its last written digit and the recorded "about 30%" claim (end-to-end B8) no longer refused (`tests/translate/test_precision_b16_b22.py`, `tests/translate/test_close2_precision_counts.py`) | none (left) |
| DV2-09 | "If the price of tea rises, demand for tea does not fall much", cited for "if the price rises, demand falls", was caught but named only at info, where the base names it at warning | a known defect (section 7): the base names it through its refutation of the true task fact "The price of tea rose in 2024", which it raises alike on the control that cites the plain rule (a false alarm there, which the staged tree does not raise); not changed | none |

Tests rewritten this round, to the stricter base behaviour (INV-QR-1; section 11): the "never writes" cases of
`tests/adapters/test_repair_round5_quotations.py`, the same sentence in `tests/adapters/test_close1_quotation_roles.py`
and the "ayudar" role of `tests/contract/test_quotation_stub.py` (each span is a quotation and is checked, where they
pinned a mention). The exact version pins moved with the versions and stay exact (`tests/contract/test_versions_identity.py`,
`tests/engine/test_review_engine_fixes.py`, `tests/translate/test_stem_subjects.py`, and the rules string `argdiag-2` in
nine contract, channel and translate tests). No test was weakened, skipped or removed. The trial reverts named in the
table were run on scratch copies only; none of them is in this tree.

Versions: the translator moves to 0.5.1 and the rules to `argdiag-2` (section 7, "Versions"). The translation pipeline and
the argument and evidence rules had changed under unchanged stamps in every round of this release, so a translation
record or a diagnosed result of an earlier round read as current (INV7-2); now a translation record of an earlier round
reads as stale (the outcome checks the translator version), a result diagnosed under `argdiag-1` is refused by release
rule 9, and the policy manifest, which binds the rules version, changes with it. Engine 0.5.0, policy 2026.10-v5, IR 1.0
and contract 0.4 stay.

**Measured** (once, at the end, on a fresh copy of the staged tree; the base's corpus and arena figures are the review's
runs on the committed base, and the repros and timings were run on the base beside this tree, both trees back to back;
another workload held two to three of the four cores from the third minute of the measurement on):
- **Suite**: 8946 passed and 45 deselected (the stress selection, not run) in 443 s, one serial run, no failure.
- **Development corpus** (101 cases): 44 of 44 defects named, 57 of 57 controls clean, 47 controls not releasable. Every
  verdict and every releasability is close round 2's, and no case is worse than on the committed base (9 named, 41 false
  alarms there).
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 64 of 66 defects named, 2 caught but not named,
  none missed; 68 of 68 controls clean, 37 not releasable. Every verdict and every releasability is close round 2's; no
  case is worse than on the base (13 named, 23 false alarms there); the one defect mode the base flags and this tree does
  not is still `ho_d_leap_bm_since` in text mode (DIFF-07: the base's flag is its CORE-QNT-001 false error).
- **Arena replays** on fresh copies: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177, run1 120/134 functional,
  each count the base's, and no record functional on the base is not functional here (no planted fault lost). Compared
  with the base answer by answer, the replay is close round 2's on every record (no finding, status, display or release
  differs); the findings at warning or error on genuine answers that the base does not raise are close round 2's 9
  IMPROVED items, and the 12 INT-HIST-001 carries are DV2-05 (left).
- **Repros** of every item, on the fresh copy and on the base. INV-QR-1: the review's invented quotations after "not only
  writes", "not only says", "does not just write" and "does not just say" are named as on the base (ES-SRC-001, with
  INT-REQ-003 where the base raises it), as are its two controls; the genuine mention 'never once says "I love you"' is
  named as on the base (given up). DV2-04: the six supposition controls (Economics, Biology, Geography and History; data
  response and source analysis) are clean and, as on the base, not releasable (the Biology one is a false alarm on the
  base); the five defect twins (a "may", a "could", a condition, a fear and a supposition of another premise) are named
  `unchecked_source`. DV2-06: rd_space_digits_physics takes 0.74, 0.98 and 1.80 s of CPU at 11,912, 36,035 and 72,038
  characters (the base 1.02, 1.28 and 1.77 s; the review's staged tree 2.88 and 3.97 s at the first two),
  rd_units_physics 0.46, 0.50 and 1.30 s (the base 0.47, 0.64 and 1.08 s) and rd_space_digits_history 0.51, 1.40 and
  2.43 s (the base 0.76, 1.47 and 2.21 s); on a warm process the medians are 0.41, 0.24 and 1.05 s against the base's
  0.81, 0.29 and 1.20 s: at most 1.2 times the base. DV2-07: the r7 round takes 47.2 and 47.6 s on its own (the base 18.0
  and 19.8 s; the tree before the round 56.2 s), 2.4 to 2.6 times; one r7 answer group takes 24 to 25 s (the base 2.1 s;
  32 s before the round), left (section 7). The known-defect and left items give what section 7 says: DV2-01, the
  review's nine Economics forecasts, hopes, fears, promises, plans and estimates are released where the base's NOT_ELIGIBLE
  is the same on their controls; DV2-02, the two title-case headlines are released; DV2-03, 13 plain-rule controls are
  refuted where the base keeps them clean; DV2-08, E04 is AMBIGUOUS_TRANSLATION; DV2-09, ra05 is caught at info and its
  control is clean and releasable, where the base flags both. ADV6-01 is not reopened: its 22 qualified rules (hedged,
  framed, questioned, counterfactual, alternative and cut) are named `source_mismatch` and its three controls are clean
  and releasable (the base flags two of them, and releases one defect).

After the fresh copy was taken, only documentation changed (this section, section 7's items of close round 3 and
`REVIEW_FIXES_README.md`); no code or test.

**Traceability.** The measured tree is the commit `7991e8b` with the argument-diagnosis integration, its five repair
rounds and close rounds 1 to 3 staged on top, uncommitted; the staged diff is relative to `7991e8b`.

## 15. Security round 1

The security review of the close round 3 tree found that the figure reader's thousands grouped by spaces (repair round 4,
`quant._DIGITS`) made reading figures quadratic (SEC-1). This round makes it linear and sweeps every pattern and reader loop
the staged diff adds or changes under `src` for the same fault: a pattern or reader whose time grows faster than its text,
or that takes more than 1 s on a bounded input where the base takes under 0.1 s. The rule of the round: change only what
makes a pattern or reader super-linear, and keep every outcome. Each fix gives the same matches as before (spans and
groups, or the same yes or no where the code reads the pattern as one); a test pins it against the old pattern, kept as data
in the test, on representative and random inputs, and a timing test compares the cost of the reader at two sizes of the same
input (a ratio, not a wall-clock bound that load can break: a linear reader costs about four times as much on four times the
text; each old pattern cost 11 to 19 times as much, so every timing test fails on the tree before the round; the shared helper
is `tests/growth.py`). No other finding of the verification of close round 3 is touched: its false-alarm items DIFF3-01 to
DIFF3-08 and DV2-03, DV2-05 and DV2-08 (section 7) stay known defects, and DV2-07, the verification the base never does,
stays (its cost is measured below). Tests are the files named `test_security_round1_*.py`.

**SEC-1.** A space-grouped figure ('45 000', '1 800 000') was read by the alternative `\d{1,3}(?:[ ]\d{3})+` (four space
characters), so every group of a long run ('000 000 000 ...') passed the guard against starting inside a run of digits and
became a new start that read the run again to its end. A group that follows two groups of three digits of its run no longer
starts a space-grouped figure: the figure from there reads the same groups to the same end, with the same text after it, as
the figure from the group before, which every scan of the run has already tried; the run's head and the two groups after it
still start one, so a scan that starts right after a head another reader took ('= 138 349 800') reads every figure as
before. The guard is in all 39 compiled patterns built on the figure reader. A prose reading of ' 000' repeated 4,000 times
took 3.2 s (1,000 times: 0.20 s); it now takes 0.07 s (0.01 s). Besides the pinning tests, the round replayed every call of
those patterns the two corpora, every arena round and the suite make (46,317 calls, the longest text 200,064 characters) on
the old and the new patterns: no match differs.

**The sweep.** Every compiled pattern was inventoried on both trees: 290 new and 57 changed module-level patterns and 138
inline patterns on added lines are on the list (465 distinct patterns once aliases are merged), with 997 reader loops that
have added lines. Each pattern was timed on its own on adversarial inputs built from its syntax (long runs of each literal and
class character, each repeated or optional group pumped, nested and overlapping optional groups, matches repeated) at
6,250, 25,000, 100,000 and 400,000 characters (the response bound), scanning and anchored, a changed one also in its base
version; 119 grew faster than linearly or stopped early. Each of those was read at its call sites (method, and the bound on
the text it reads) and timed at the windows its sites read; the hub was driven by 749 hostile families (characters and
tokens repeated inside an answer, a request or a supplied text, in nine subjects) at two sizes with the time of every pattern
call site, the super-linear families again at a third size, on the base and on the fixed tree, and by targeted probes for
shapes no family holds. Most flagged patterns are linear where they are used (anchored at disjoint places, or bounded by a
window of 24 to 4,000 characters); the others are fixed:

| Reading | What was super-linear | Fix (the same matches) | Before | After |
| --- | --- | --- | --- | --- |
| `sentences._WRAP_CLOSE_RE` (every sentence of a non-STEM report) | searched from every closing mark of a run; the space after the marks split between two quantifiers | starts at the first mark of a run only; possessive | 2.2 s at 8,000 marks | 0.0002 s |
| `packs._dated_series` (a supplied data text) | a year, a long run of spaces and a word split between the quantifiers around the optional separator and unit | every quantifier possessive (`_DATED_LINE_RE`) | 0.91 s at 8,000 characters in one line | 0.0000 s |
| `packs._REQUEST_RELATION_RE` | searched from every letter of a long word | a yes or no read from the start of a word | 3.5 s at 19,000 letters (request[:20000]) | 0.0006 s |
| `relations._PROPERTY_SHOW_RE` | three quantifiers that all take space between 'that' and 'is' | a yes or no: the space runs to 'is', or a core of 1 to 40 characters with visible ends stands between two runs | 10 s at 4,000 characters (req[:4000]) | 0.0004 s |
| `relations._PROSE_RANGE_RE` | a range tried from every digit of a run of digits and commas | `_prose_ranges`: the pattern's own matches, a failed run passed over | 10 s at 20,000 digits | 0.0017 s |
| `relations._ASK_SENTENCE_RE` | an asking sentence tried after every line break of a blank run | `_ask_sentences`: the pattern's own matches, a failed start's run passed over | 29 s at 20,000 line breaks | 0.0042 s |
| `quant._RATE_RES` | the unbracketed tail made white space and 'annually' a pattern of its own, tried from every space | that alternative starts where its run starts (`_RATE_SCAN_TAIL`) | 2.0 s at 8,000 spaces | 0.017 s |
| `quant._AND_DATED_RE`, `_LIST_ITEM_RE` (and their SI forms), `_UNDATED_ITEM_RE` | the space after a figure split between '\s*' and '\s+and' | the run read once (`_AND_LINK`, `_ITEM_LEAD`) | prose reading 2.7 s at 16,000 spaces after a pair | 0.09 s |
| `request_parser._META_LABEL_RE`, `_WORD_COUNT_LINE_RE` (word bounds) | the space after a footer label split between two quantifiers | possessive | 1.4 s and 2.0 s at 16,000 and 8,000 spaces; a word-bound check 27 s on 'Word count' and 16,000 spaces | 0.0000 s |
| `request_parser._LEAD_MARKS_RE`, `_MARKS_RE`, `relations._MARKS_RE`, `bus._MARK_ANNOTATION_RE`, `hub_hooks._FORM_RE` | the spaces after '[1' split between two or three quantifiers | possessive | 1.5 s at 32,000 (the part lead), 0.35 s at 16,000 (bus, request parser, item form; the STEM request's is read on its first 4,000 characters: 0.02 s) | 0.0002 s |
| `request_parser._PART_LABEL_RE`, `_PART_END_RE` (the base's patterns, read by this tree's new `_part_spans` too) | the space after a sentence's end split between '\s+' and '[ \t]*' | possessive | a request of 32,000 spaces after a full stop held the hub 86 s (the base 29 s) | 0.04 s |
| `sources._CREDIT_GAP_RE` (the base's pattern alike), `sources._SENTENCE_OPEN_RE` | a gap of spaces split between two or three quantifiers; an opening searched from every end mark | possessive, '\s*,?\s+' as one run; `_opens_sentence` read from the end | 3.6 s at a gap of 2,000; 0.87 s at 16,000 | 0.0000 s |
| `hub_hooks._GIVEN_RE`, `translate.relations._CONVERSION_RE`, `diag_argument._PART_LABEL_RE`, `ledger._DECREASE_AFTER_RE` | the space around '=', after 'in', before a label, or after a figure split between two quantifiers | possessive | 1.7 s, 2.7 s, 2.7 s and 2.1 s at 16,000, 16,000, 8,000 and 8,000 characters | under 0.001 s |
| `structural._HISTORIAN_RE` (the base's pattern alike) | a name of initials tried from every initial of a run | starts at the first initial of a run only | 0.09 s at 4,000 (one claim) | 0.0005 s |

In context, the families that had grown faster than their text on the staged tree read in time proportional to it on this
one: 8,000 closing quotation marks in History 0.07 s (5.9 s before), 32,000 2.1 s (100 s before); a request of 32,000 spaces
after a full stop 0.04 s (86 s; the base 29 s); 32,000 straight quotation marks in English 3.0 s (54 s; the base 119 s).

**Left** (not changed: outside the diff, or linear):
- *Quadratic readers of the base.* The prose reading reads, for every derived phrase without a pair of its own, the figures
  and years of its whole clause (`quant._no_pair_reason`, `_target_years`): 'rose by 10% ' repeated 1,322 times takes 51 s
  (the base 43 s), quadratic in both; this tree adds work of the same order per phrase (the period anaphor and the figure's
  own subclause, about 1.2 times the base's cost). The STEM segmentation joins each line to the whole logical line before it
  (`stem.segment._joins`): '> quote' repeated 3,992 times takes 21 s on both trees. A note label followed by a long run of
  spaces (`markdown._NOTE_LABEL_RE`, unchanged): 0.25 s at 4,000 (the base 0.38 s).
- *Linear but heavy.* Above about 20,000 characters the self-certification reading of English and History answers reads the
  whole answer about twenty times (`markdown._self_certification` through `_split_note_clauses` and `is_self_report`):
  5 to 16 s at 128,000 characters and four times that at four times the text. The base's own reading steps up at the same
  length (its pattern read about seventeen times): on runs of dots, colons, dashes and minus signs of 32,000 characters it
  takes 0.4 to 1.0 s where this tree takes 1.2 to 1.9 s (at most 4.2 times), on runs of quotation marks far longer (119 to
  173 s, where this tree takes 2 to 4 s).
- *DV2-07* (section 14): the verification of claim outcomes the base's parser never serves stays; its cost is measured below.

**Measured** (once, at the end, on a fresh copy of the staged tree; the base's timings were run beside it on the same
machine):
- **Suite**: 9014 passed and 45 deselected (the stress selection, not run) in 484 s, one serial run, no failure (close
  round 3's 8946 tests and this round's 68).
- **Development corpus** (101 cases): 44 of 44 defects named, 57 of 57 controls clean, 47 controls not releasable. Every
  case is close round 3's in every field but its time and the receipt, message and result identifiers each run draws.
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 64 of 66 defects named, 2 caught but not named,
  none missed; 68 of 68 controls clean, 37 not releasable; every case is close round 3's, as above.
- **Arena replays** on fresh copies: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177, run1 120/134
  functional. Compared with close round 3 answer by answer, no record differs in any finding, message, status, display,
  release or metric (time and the per-run identifiers aside).
- **DV2-07** (left, section 14): the r7 round alone takes 49.7 and 49.6 s (the base 20.9 and 18.5 s; close round 3 47.2
  and 47.6 s), 2.4 to 2.7 times the base's time.
- **The fixed readers**: the times in the table above, on the tree before the round and on this one.

After the fresh copy was taken, only text changed: this section, one comment (`packs._REQUEST_RELATION_RE`) and the module
docstrings of three of this round's test files, whose timing figures were corrected to the measurement; the syntax trees of
the code and the tests are the measured ones.

**Traceability.** The measured tree is close round 3's tree with this round staged on top, uncommitted; the staged diff is
relative to `7991e8b`.

## 16. Security round 2

The independent verification of security round 1 found five readers of the staged diff that still grew faster than their
text (SEC-V1 to SEC-V5), and confirmed SEC-1's fix. This round fixes them and sweeps every pattern and reader loop the staged
diff adds or changes under `src` again, with a generator round 1 did not have: inputs built by inserting a run of one or two
characters at every place of a string the pattern matches (with and without the text after the run), and inputs that put
many items before one long text (the product shapes of SEC-V1 and SEC-V2). The rule of the round is round 1's: change only
what makes a pattern or reader super-linear, keep every outcome. Each fix gives the same matches as before (spans and
groups, or the same yes or no where the code reads the pattern as one), pinned against the old pattern or reader, kept as
data in the test, on representative and random inputs; and a timing test compares the cost of the reader at two sizes of
the same input (`tests/growth.py`: a linear reader costs about four times as much on four times the text; on the tree before
the round the old readers cost 8.8 to 55 times as much, so every timing test fails there). No other finding of the
verification is touched: DIFF3-01 to DIFF3-08, DV2-03, DV2-05 and DV2-08 (section 7) stay known defects, and DV2-07 stays
(its cost is measured below). Tests are the files named `test_security_round2_*.py`.

**SEC-1** (round 1's fix, re-verified): the space-grouped thousands guard is in all 39 patterns built on the figure reader and
the round-1 tests pass; the sweep found no other start inside a run of digit groups.

| Finding | What was super-linear | Fix (the same matches) | Before (the tree before the round) | After |
| --- | --- | --- | --- | --- |
| SEC-V1 `packs._transcribed` (CORE-QNT-001, every subject) | each derived figure's transcription test read its whole sentence and every supplied text into words again: figures times text | `_transcribed_all`: the distinct sentences once, each text once; phrases and the windows around them found by one automaton of word sequences (`_PhraseFinder`) | the test of 600 figures beside a text of 600 sentences 4.9 s (150: 0.27 s); the verification's 400 figures beside 399,000 characters held the hub 34 s (the base 0.45 s) | 0.017 s (150: 0.004 s); 1.4 s in the hub |
| SEC-V2 `quant._analyse` (the prose arithmetic reading) | for every derived figure, comparison or figure, its clause, or the clause up to it, was read again: the figures and amounts before it, its decades, spans and years, its subclause, its worked equations, the pairs and phrases read so far | `_clause_index`: each clause read once and kept; a question about the clause up to a place answered from the whole clause's reading, only the last few runs before the place read again (`_PrefixScan`, `_years_cut`, `_decade_cut`); the spans read so far kept in indexes (`_Stab`, `_GrowingSpans`, `_LastBefore`) | 'that year it rose by 5%, ' in one clause: 0.21 s, 3.3 s and 53 s at 2,000, 8,000 and 32,000 characters; 'rose by 10% ': 0.11 s and 1.5 s at 1,000 and 4,000, and an Economics answer of it over 12,000 characters 18 s in the hub (the base 13 s) | 0.013 s, 0.049 s and 0.20 s; 0.010 s and 0.037 s, and 1.1 s in the hub |
| SEC-V3 `markdown._SELF_SUBJECT_KINDS_RE`, `_SELF_SOURCED_RE` (the structural self-report) | read with `finditer`, a modifier tried at every letter after an apostrophe or a hyphen of a run such as "'b'b'b...", each try reading the run to its end | the scans (`_self_subjects`, `_self_sourced`, below) try the patterns only where a match can start, a run of letters read once | the subject scan of 8,000 characters of "'b" 0.87 s (2,000: 0.058 s); an English answer of 8,000 1.0 s in the hub | 0.030 s (0.007 s); 0.22 s |
| sweep: the same scans on item lists | a try that starts inside a long list of items ('statistics or x statistics or ...') reads the list to its end before it fails for want of an anchor or a source after it, and so does the try at every later item | `_subject_matches`: the patterns tried at the places a subject may start (near an item noun, or an answer word), and only where one reading of the sentence (where each item may end, which item follows an 'and' or 'or', whether a list reaches an anchor or a source) says one can match; the pattern gives each match | self-certification of a sentence of 8,000 characters 2.4 s (2,000: 0.14 s); a History answer of one such sentence of 18,000 characters held the hub 161 s (6,000: 1.6 s; the base 138 s and 1.3 s) | 0.060 s (0.015 s); 2.1 s in the hub (6,000: 0.31 s, 36,000: 4.0 s, 54,000: 5.9 s) |
| SEC-V4 `markdown._SELF_LEAD_RE` ('As verified against the census, ...') | the white space after 'against' or 'with' read by three quantifiers (`\s+[^,;:.]{1,60}\s*`) | each run read once: the leading run, a core of 1 to 60 characters that starts and ends on a visible character (or at least two white-space characters when the complement is white space alone), the trailing run; only whether it matches is read, and it matches the same strings | 26 s at 8,000 spaces (2,000: 1.6 s); a History answer 26 s in the hub (the base 58 s) | under 0.0001 s; 0.31 s |
| SEC-V5 `quant._SHARE_RE` and the SI reading's share ('5 per cent of the 200 seats, or 10') | the white space after 'of' split between two quantifiers and the link's between three (quadratic after 'of', cubic after the comma) | every run of the links read once (possessive): what a run may stand before never starts with white space | twenty shares with 200 spaces after the comma 20 s (50: 0.37 s); after 'of the' 15 s at 2,000 (500: 0.94 s); an Economics answer with one such share of 400 spaces 8.6 s in the hub (the base 7.2 s) | 0.0004 s; 0.0013 s; 0.55 s |
| sweep: the SI reading's total (`quant._build_patterns`, 'a total of about 5.0 kg') | the white space between the word of the total and its figure split between two quantifiers around the optional qualifier | each run read once (`_TOTAL_LINK`, possessive) | one try 0.65 s at 1,000 spaces and 11 s at 4,000; a Physics answer with one such total of 4,000 spaces 7.9 s in the hub (1,000: 1.2 s; the base 7.2 s and 1.0 s) | 0.0001 s; 0.81 s in the hub (1,000: 0.76 s) |
| sweep: `sources.quotation_credit` (the credit of a quotation) | for every text named before the quotation, the sentence up to the name copied three times and searched, the gap to the quotation copied and its rest searched for a clause end: the names times the sentence; two gap patterns split a run of white space between two quantifiers | the text before a name read from its end, the gap with the patterns' own bounds, the clause ends up to the quotation once, the gap patterns' runs read once | 'Ashdown writes ' before a quotation: 0.61 s at 16,000 characters (4,000: 0.035 s), 30 s at 120,000; after 'according to' a name and a run of spaces 0.81 s at 16,000 | 0.0061 s (0.0016 s), 0.026 s at 64,000; 0.002 s |

**The sweep.** The inventory of the round's tree (the module-level patterns, the patterns its tuples and readings build, and
the inline patterns of added lines) holds 389 distinct patterns that are new or changed against the base (287 new, 58
changed, 4 new names of unchanged patterns, 40 inline literals); 97 further inline calls build their pattern at run time
(compiled module patterns built from pieces, inventoried by name, and patterns of escaped names, years or options with fixed
guards, each one alternation of literals or a bounded window). Each pattern was timed on its own, scanning and anchored (and
in `fullmatch` mode for the 27 the code reads that way), on round 1's generator, the verification's and the insertion
generator, screened at 300 characters and timed at about 1,000, 4,000 and 16,000; a changed one also in its base version and
in its version before the round. 74 grew more than x6.5 per x4 above 0.02 s or took more than 0.5 s at 16,000 characters
(one, cubic on its own, was timed by hand: its bench did not end). Each of those was read at its call sites: 60 are the
patterns round 1 read (bounded windows of 24 to 4,000 characters, anchored at disjoint places, or fixed by round 1: the
scan-mode growth is not how the code reads them), and the others are this round's own (`_ORDINAL_AFTER_RE`, anchored after
each figure), the definition a linear reader reproduces (`generic_parser._ACCURACY_MARK_RE`), bounded (`diag_argument`'s
'because' in `masked[:2000]`, a symbol meaning of at most 1,000 characters, a supplied text's author of at most 200, the
rounding words after a value read on 48 characters, `stem.relations._ROUNDING_WORDS_AFTER_RE`, cubic on its own but 0.0004 s
on its window, and three patterns round 1's bench left unfinished, each read on a bounded window: the gap after a quotation,
at most 60 characters, the gap between part labels, at most 120 with its white space collapsed, and a statement's lead, at
most 160), linear where the code reads them (the SI list item and dated pair, anchored: x4.0), or fixed above (the subject
scans, the SI total). The 36 patterns this round's fixes added (the subject reading, the credit reader's bounded forms) were
benched the same way afterwards: the 11 that grow faster than linearly when scanned are read only anchored, at places the
readers visit once (x3.8 to x4.8 per x4 there, under 0.01 s at 16,000).

In context, the hub (`RouterHub.dispatch` and `receive`) was driven by round 1's 749 hostile families and 328 new ones
(derived figures, comparisons, rates, shares, totals and parts repeated in one clause in five subjects; two-character pumps;
links followed by a run of spaces; many sentences beside a long supplied text; quotation runs) at 4,000 and 16,000
characters, the growing ones at 64,000 and on the base and the tree before the round, and by product shapes on six recorded
tasks (many derived figures, quotations, citations or claims beside a long supplied text; many names before a quotation; item
lists; years, equations, self-reports and words repeated) at two sizes: no product shape grew faster than its text, and every
family that did is a reader of the base the diff leaves as it was (below; the base as slow or slower) or the
self-certification step round 1 found (linear beyond it). The list with every pattern's times and the screens' results is the
round's working file (patterns.md).

The clause index of SEC-V2 holds about 22 bytes per character of its clause; the indexes of the last 32 clauses are kept (the
prose reading asks only about the clause it reads) and the worked equations of the last 32 texts, so the round keeps at most
about 0.3 GB of earlier analyses' texts in the worst case of 32 clauses of 400,000 characters (the base's own analysis cache
keeps 128 analyses).

**Left** (not changed: outside the diff, or linear):
- *Quadratic readers of the base, unchanged by the diff* (the base as slow or slower). Parts after 'of which'
  (`quant._part_specs`): each 'of which' lists the figures after it, so 'of which 5, ' repeated states a quadratic number of
  parts: an Economics answer of 2,000, 4,000 and 8,000 characters 2.3 s, 7.1 s and 27 s in the hub (the base 2.4 s, 7.8 s and
  32 s). The share after a total's parts (`quant._SHARE_OF_TOTAL_RE`, the base's pattern, read by `_part_specs`): the white
  space before a share split between quantifiers: 'Of the $13 billion' or 'of which' followed by a run of spaces 4.6 s and 75
  s at 4,000 and 16,000 characters (the base 7.2 s and 141 s). A difference between two named parties (`_part_specs` through
  `quant._entity_figures`, which reads the paragraph's figures for each): 'about $2 billion more than France ' repeated 2.1 s
  and 12 s at 4,000 and 16,000 characters, 98 s at 64,000 (the base 1.3 s and 9.1 s; the extra time is the solver's set-up: a
  Z3 context costs 1 to 7 ms with the allocator's trim threshold, the same on every tree once it is raised). A share stated
  for a named party (`quant._party_share`) searches the clause up to the share for the party ('about two-thirds of the total'
  and 'and' repeated: 1.1 s at 32,000 characters, the tree before the round 29 s, the base 28 s). The claims a CORE-QNT-001
  finding names (`packs._claims_for_statement`), looked up with the whole sentence for each phrase: 'fell by 5% ' repeated in
  one History sentence 1.0 s and 6.2 s at 16,000 and 64,000 characters (the base 26 s at 16,000). The mark annotations of a
  STEM line (`stem.layout.annotation_ranges`, `TRAILING_ANNOTATION_RE` searched over each sentence): a Physics answer with
  'As verified with', '[1' or 'Note:' and a run of spaces 1.5 s and 21 s at 4,000 and 16,000 characters (the base 2.3 to 9.0
  s and 55 s). A Physics request of a long run of spaces: 5.4 s at 16,000 characters, the reading of its answer the same on
  the base (5.3 s; the base reads the request 6.7 s more). The statements of a STEM paragraph matched to their spans
  (`stem.segment._attach`): 0.03 s at 32,000 characters. The STEM segmentation's `_joins` (round 1: '> quote' repeated 5.3 s
  at 16,000, the base 4.9 s).
- *Linear but heavy.* The comparison reading ('short of 5 ' repeated in one clause): 2.8 s, 7.0 s and 11 s at 4,000, 16,000
  and 64,000 characters in a History answer (the base 1.6 s and 8.2 s at 4,000 and 16,000). The self-certification reading of
  an English or History answer of one long sentence steps up between 4,000 and 16,000 characters, as round 1 found (the base
  alike), and grows linearly beyond: 1.2 s and 5.2 s at 16,000 and 64,000 characters ('the figures are accurate ' repeated in
  an English answer; the base 0.73 s and 2.7 s). A quotation credit is read per quotation (`quotation_credit` finds the
  sentence's quotations and names once per call; the hub's sentences of many names and quotations read linearly: 1.1 s at
  33,000 characters).
- *DV2-07* (section 14): the verification of claim outcomes the base's parser never serves stays; its cost is measured below.

**Measured** (once, at the end, on a fresh copy of the staged tree; the base's timings were run beside it on the same
machine):
- **Suite**: 9058 passed and 45 deselected (the stress selection, not run) in 548 s, one serial run, no failure (security
  round 1's 9014 tests and this round's 44).
- **Development corpus** (101 cases): 44 of 44 defects named, 57 of 57 controls clean, 47 controls not releasable. Every case
  is close round 3's in every field but its time and the receipt, message and result identifiers each run draws.
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 64 of 66 defects named, 2 caught but not named,
  none missed; 68 of 68 controls clean, 37 not releasable; every case is close round 3's, as above.
- **Arena replays** on fresh copies: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177, run1 120/134 functional.
  Compared with close round 3 answer by answer, no record differs in any finding, message, status, display, release or metric
  (time and the per-run identifiers aside).
- **DV2-07** (left, section 14): the r7 round alone takes 48.4 and 44.7 s (the base 17.4 and 17.2 s; security round 1 49.7
  and 49.6 s), 2.6 to 2.8 times the base's time.
- **The fixed readers**: the times in the table above, on the tree before the round, on this one and on the base.

After the fresh copy was taken, only text changed: this section's measured figures; the syntax trees of the code and the
tests are the measured ones.

**Traceability.** The measured tree is close round 3's tree with security rounds 1 and 2 staged on top, uncommitted; the
staged diff is relative to `7991e8b`.

## 17. Accuracy round 1

The fixer's items of the accuracy round (the owner's rule: fix what hurts response accuracy, leave the rest): false alarms on
correct answers that the committed base does not raise (A), and STEM misses that let a wrong answer pass on both trees (B).
A correct answer must come out as on the base (no warning or error, the same releasability or better), every defective twin
the staged tree caught before the round stays caught, and every diagnostic only adds information. Each A item narrows the
reading that raised the false alarm so that it fires only inside the class it was written for; none is reverted to the
base's behaviour. Each B item adds the smallest deterministic reading that names the fault, with clean controls. Every new
or changed pattern and reader is linear in its input, with a growth test (two sizes, a ratio of CPU times). Tests:
`tests/contract/test_accuracy_round1_cases.py` (27 cases of the round's own wording in `tests/data/accuracy_round1_cases.json`:
each A item's correct answer clean, and released where the item is about release, beside its defective twin, named),
`tests/stem/test_accuracy1_stem.py` (the B items: 9 wrong answers named, 19 controls clean, the growth of the STEM readings),
`tests/channel/test_accuracy1_relay_history.py` (DV2-05) and `tests/translate/test_accuracy1_growth.py`.

| Item | What was wrong | Fix | Left or given up |
| --- | --- | --- | --- |
| DV2-03 | a plainly stated source rule with a hedge or frame word elsewhere in its sentence ('... the price of copper rises and mining firms can hire more staff', 'Nobody doubts that if ...') was refuted as `source_mismatch` (EVD-SRC-003, INT-ARG-001, not releasable) | `stated_rules.rule_qualifier` reads what qualifies the rule itself: a hedge or an "or" counts only in the conjunct of the consequence that holds the consequent's own words (`_conjunct_pieces`: a later conjunct, or a relative clause after those words, is another statement); an "or" between two complements of one preposition is none (`_parallel_complements`); an affirming frame before the rule or opening a side ('Nobody doubts that', 'There is no question that': a negation and a word of doubt, an even count, no universal and no other frame word, `_affirming_frame`, `_without_affirming_lead`) endorses it; with a negated consequent its own negation ('cannot') is no frame. Every refutation `tests/translate/test_close1_stated_rules.py` pins still holds | A02 (the premise applies the rule to farmland near the Tamar, words the rule does not state) stays held back with no finding, as before the round; s09 (a dropped 'while' condition) stays refuted: it is the class the reading was written for |
| DIFF3-01 | a correct one-sentence explanation whose reason is a cause phrase ('because of', 'due to', 'as a result of', 'following', 'by', 'thanks to') was named `bare_assertion` | `diag_argument.offers_cause` (the module docstring): the claim's own words before a cause phrase of `CAUSE_PHRASES` and an event or means of at least three content words after it (a gerund after 'by') offer a cause, so ARG-BARE-001 does not fire | none; the base's own misses stay (ba06: 'rose in 2024 and this was bad for consumers' is missed on every tree) |
| DIFF3-02 | ARG-NS-003 (unbridged leap) fired when the bridging link is stated in a quotation ('Historian K writes that "the occupation ... crippled German industry", so ...') or in the reason clause of the sentence that ends 'so ...' | `diag_argument.unbridged_leap_reading`: a quotation of the answer (`_quotations`, at most 64) or the reason clause of a joining sentence (`_Sentence.reasons`) that holds words of the reason and of the conclusion's target, and every name the conclusion has that the reason lacks, bridges the leap (`_bridges`) | none |
| DIFF3-03 | a true task fact stated with a phrasal verb ('brought interest rates down', 'went down') beside a verb of the other direction ('After inflation rose, ...') was refuted (EVD-SRC-005) | `grounding.direction_verbs`: a phrasal verb of a change (its particle at most four tokens after it, `_PHRASAL_UP_VERBS`, `_PHRASAL_DOWN_VERBS`, `_PHRASAL_BACK_VERBS`) states its direction, and `_task_conflict` refutes only when the sentence holds no verb of the premise's direction | tc06 ('has said it is going to raise ...', a reported intention): EVD-SRC-001 as before the round |
| DIFF3-04 | a task fact restated with a synonym or in other words ('increased' for 'raised', 'troops' for 'forces') was named `unchecked_source` (EVD-SRC-001) | `diag_evidence._restated_by_task`: a label-only task-authority premise that restates in other words a statement the task asserts as its own (`_task_restatements`: the asserted sentences, or the clauses before a suspending word; the engine's synonym groups and the round's closed ones, every verb of a rise one word and every verb of a fall another, 'washed away', the relative time words of `_RELATIVE_TIME_RE`, a pronoun continuing the clause before; the polarity and `_task_conflict` read) is not named. Its grounding record is unchanged: the answer is no more releasable | none |
| DIFF3-05 | a document's approving word about another subject ('The delegates welcomed the end of the fighting, but the treaty's terms crushed ...') counted as its stance on the claim's subject (EVD-SRC-006) | `diag_evidence._stance_clauses`: the document's opposite stance must stand in a clause about what the claim's stance is about (the clause's stems, the clause before when it continues by a pronoun) | none |
| DIFF3-06 | a correct own-knowledge fact was named `lack_of_evidence` (EVD-LACK-001) when the request asks for own knowledge | `diag_evidence.evd_lack_001`: a general-knowledge fact of a request that invites own knowledge (`OWN_KNOWLEDGE_CUES`) is an info record capped `not_source_bound` ('stated from the writer's own knowledge, which the request invites; no check verified it in this process'); it still blocks release | lk02 (a request for the source only, then a fact from outside it) stays named: the item is about a request that invites own knowledge |
| DIFF3-07 | a source rule quoted verbatim with 'when' ('When demand for copper rises, the price of copper rises') was not verified as the source's rule (not releasable) | `stated_rules._readings`: 'when' opens a rule's condition in a generic statement (`_generic_statement`: no past form of the closed list, no '-ed' past a participle lead does not precede), never after a word that makes it a time, a restriction, a biconditional or a report (`_BLOCKING_BEFORE_WHEN`); the reading's qualifiers are read as for 'if', so a hedged 'when' rule is refuted (wh05 is now named; before, caught but unnamed) | none |
| DV2-05 | peer relays and syntheses carried, as INT-HIST-001, warning-level findings their source receipts raise falsely on correct work | `channel.bus._carried(decided_only=True)` for a forward or relay to a peer specialist and for a synthesis: an error, a warning that states a fault the content was found to have (`_DECIDED_WARNINGS`: INT-SUBJ-004, INT-ARG-001, INT-REQ-017) and a subject finding that names a STEM defect (`_DECIDED_SUBJECT_WARNINGS`: the STEM rows of the named-code table, ST-DIM-001, ST-DIM-002, ST-SCOPE-001) are carried; every other warning stays listed in the history the receipt references. A forward or relay to the combinator, which composes the answer, still carries everything | an error a relay repeats is carried by rule even when both trees raise it falsely on the arrival (r7 lit-p7c INT-SUBJ-001, r5 hi-p4 INT-REQ-003): those are their source checks' |
| DV2-08 | 'about 300 g' for a stated 260 g (a measured quantity over Real), encoded at [250, 350), was AMBIGUOUS_TRANSLATION and held back | `precision.read_sites`: for a figure whose significant digits are not a lone 1 the last-digit reading is denied as an alternative (`Reading.alt_denied`), so an encoding at the first significant digit stands on its own; an encoding at the last written digit is still probed at the stated interval (the recorded 'about 30%' claim of end-to-end B8 unchanged) and a power of ten keeps both readings ('about 100%') | none |
| DIFF3-08 (low) | warning-severity records on genuine r7 answers that charge the specialist with nothing: INT-CONFLICT-005 'refutes itself only under the assumed reading of its AMBIGUOUS_TRANSLATION', and INT-GLOSSARY-005 reading 'dependency ratio in 2020 (dependants per 100 of working age)' and 'dependency ratio in 2020' as different quantities | not fixed | INT-CONFLICT-005 at warning under an assumed reading is the base's own rule, pinned by its round-4 tests (`tests/channel/test_round4_fixes.py`, `tests/integrity/test_round4_integrity.py`); it shows on these answers because the staged tree decides claims the base never decides (DV2-07). The gloss reading also decides what the consistency check pools (`cross_check.split_by_gloss`), so reading a parenthesised definition as the same quantity could charge a new contradiction, and silencing the warning alone would hide that the check reads the symbols apart. Receipt statuses are unchanged |
| ADV6-03 (B) | task quantities in different units combined with no conversion passed ('Total = 2.5 + 300 = 302.5 J' for 2.5 kJ and 300 J; 'A = 30 × 20 = 600 m²' for 30 cm by 20 cm; 'A = 20 × 20 = 400', then 'p = 50/400 = 0.125 Pa') | the traced ST-UNIT-003 companion (`stem_unit_error`, warning) for a working that substitutes into no symbol (`relations._request_traced_companion`: every numeral repeats one of the request's quantities, one number with one unit, or states it in SI; none on an offset scale; at least one unit of another factor than 1; the stated value has a unit and the working, read in those units, its dimension; at most 12 numerals), and the unit of a bare result worked from the request's quantities alone (`_derived_binding`: products, quotients, integer powers and sums of one unit) | the Geography shapes ('1.2 + 300 = 301.2 m', '50 × 12 = 600 m³'): the general branches check worked equations without the request and build no unit companion by design (`packs.worked_formal_checks`: a geography rate per 1,000 divided by 10 is per cent as written); reading the request's units there needs the request passed to the general packs' formal checks |
| ADV6-04 (B) | a request value replaced by another number in a substitution with no symbol of its own passed ('(25 − 15)/5.0' for a car that speeds up from 10 to 25 m s⁻¹; '8.55/58.5' for 5.85 g; 'ΔT = 80 − 30' for 20 °C to 80 °C) | `relations._bare_givens` (a `giv` check, `stem_contradictory_givens`, warning): a bare value substituted for a symbol the STEM reference fixes and the answer binds nowhere else (no constant of the same dimension: g, c, R), in a substitution whose other values all repeat the request's quantities, against the one quantity of that dimension those values leave unused (the request states at most two), or the other end of a written change whose one end repeats the request's quantity in that unit; never a value that repeats a request quantity as written, in SI or as their change, lies within a factor of 10ⁿ, 2 × 10ⁿ or ½ × 10ⁿ of it, is zero, or that the answer states anywhere else; the request's whole number is read to the significant figures of its other quantities (section 5.1's trailing-zero rule) | none |
| ADV6-05 (B) | a conclusion drawn from a rounding worded 'which rounds to 50', '38.4 °C to the nearest whole number is 38 °C' or '13.3 A, which is 13 A to 2 s.f., so the cable is safe' passed | the rounding words before a value include 'rounds' and 'to the nearest' (`_ROUNDING_WORDS_BEFORE_RE`); a rounding of the value the prose states right before it, with only a rounding phrase between (`_PROSE_ROUNDING_BETWEEN_RE`, `_prose_rounding_source`); a request condition stated by 'has a … if' or 'can …ly' when no other is (`_CONDITION_EXTRA_RE`), 'exceeds' a strict bound (`_EXCEEDS_BEFORE_RE`); a limit the answer names takes the request's condition value when the request states no target value. The same `rnd` check decides it | none |

*Superseded by accuracy round 2* (section 18): the readings of DIFF3-05 (`_stance_clauses`), DIFF3-04 (`_restated_by_task`,
`_task_restatements`, `_restatement_roots`) and DIFF3-02's reason-clause bridge (`_Sentence.reasons`) are removed, and
DIFF3-03's conflict reading yields to a phrasal verb the lists do not hold; A02 of the DV2-03 row is released, ADV6-03 is
closed on the general branches too, ADV6-04 reads only a miscopy of the request's quantity and ADV6-05 plans no check
against the value before the rounding. The rows above describe round 1 as it was measured.

The tests that pinned a false alarm were rewritten to the correct outcome, each saying so in its text (DV2-05): the forward
to a peer in `tests/channel/test_peer_exchange.py` and the two in `tests/channel/test_round2_fixes.py` now carry no heuristic
warning (`history_support.assert_forwards_to_a_peer`), and
`tests/channel/test_response_gate_b13.py::test_a_finding_carried_from_a_receipt_the_gate_reads_is_not_counted_twice` checks
that nothing heuristic is carried while every finding stays in the forward's history; its mechanism (a carried finding read
with its source receipt is counted once) is pinned on a forward that carries a decided fault in
`tests/channel/test_accuracy1_relay_history.py`. No other test was changed. The readers the round makes linear on the way:
the stance reading's clause start (`diag_evidence._clause_start`, read back at most as far as the stance window needs: the
same answers).

**Measured** (once, at the end, on a fresh copy of the staged tree; after the copy was taken only this text changed. "The
base" is the committed code, "before" the staged tree at the start of the round; two unrelated test runs shared the
machine's four cores throughout):
- **Suite**: 9132 passed and 45 deselected (the stress selection, not run) in 648 s, no failure (security round 2's 9058
  tests and this round's 74).
- **Corpora**, case by case: development (101 cases) 44 of 44 defects named, 57 of 57 controls clean, 47 not releasable;
  hold-out (134) 64 of 66 named, 2 caught but not named, none missed, 68 of 68 controls clean, 37 not releasable; second
  hold-out (136) 70 of 70 named, 55 of 66 controls clean, 20 not releasable. No case is worse than before the round
  (development 1 and second hold-out 6 better, each by an INT-HIST-001 carry gone: DV2-05) or than the base (78, 75 and 73
  better).
- **Arena replays** on fresh copies (r1, r1-adv, r2 to r7, run1), answer by answer against before the round: the functional
  counts are the same (30/30, 150/151, 46/46 on r2 to r6, 177/177, 120/134); no genuine answer gains a finding at warning or
  above, and no planted fault loses its flag or its functional mark. Genuine relays and syntheses carrying INT-HIST-001 at
  warning or above: r2 2 to 0, r3 1 to 0, r4 1 to 0, r5 2 to 1, r6 1 to 0, r7 3 to 2, run1 2 to 0 (the base keeps no relay
  history). The peer relays of r3 hi-p2, r4 en-p3, r7 bm-p7a, run1 ess-e1b and run1 hi-e1a are ACCEPTED, as on the base; the
  carries left are errors the relay repeats (r5 hi-p4 INT-REQ-003 on the synthesis, r7 lit-p7c INT-SUBJ-001 on the relay
  and on the synthesis); the relays of r7 bm-p7a and lit-p7c no longer carry the DIFF3-08 records (INT-CONFLICT-005,
  INT-GLOSSARY-005), which stay on the arrivals' receipts.
- **Probe groups** of the items on the base, before the round and on the copy: no control became a false alarm and no
  defective twin lost its name. DV2-03: A01 and A04 clean and released (A04 and A09 released where the base holds them
  back), A06 and A07 named, A02 clean but held back where the base releases it; the rules group as before; the rule probes
  of the first differential review (three groups): 16 false alarms of before the round clean and released, 7 twins named,
  r03 and s08 left with the base's own CORE-QNT-001, s09 still refuted ('while its membrane is intact' is a condition the
  answer never establishes). DIFF3-01: ba03, ba08, ba10, bb01, bb05, bb06, bb08 and bb09 clean, bb02 named; ba06 is missed
  and bb07 carries CORE-QNT-001 on every tree. DIFF3-02: ns02 clean, ns03 named, ns01 without ARG-NS-003 and INT-ARG-001
  (its HI-SRC-001 and INT-REQ-010 are the base's). DIFF3-03: tc01, tc02, tc07, tc08, tc09, tc12, tc13, tf01, tf02, tf04
  and tf07 clean (the base raises a false alarm on each), tc04, tc05, tc10 and tf05 named, tc06 left. DIFF3-04: pa02 and
  pa03 clean, pa04 and pa05 named. DIFF3-05: st01 and st04 clean, st02 named. DIFF3-06: lk01's EVD-LACK-001 is an info
  record (its warnings are the base's), lk03 named, lk02 left. DIFF3-07: wh01, wh03 and wh04 released, as on the base; wh05
  named (caught but not named before the round, missed by the base). DV2-08: E04 ENTAILED and released, as on the base;
  E02, E03 and E06 caught but not named on every tree; the INT-REQ-004 of E01, E04 and E05 is the base's.
- **B repros** on the three trees: the base and the tree before the round miss every defect the round names (ADV6-03 q09,
  q11 and r04, `stem_unit_error`; ADV6-04 r09, r10 and q23, `stem_contradictory_givens`; ADV6-05 q18, r07 and r08,
  `stem_rounding_changes_conclusion`); q08, q10, q12 and q22 stay named; r05 and r06 (Geography) are missed on every tree.
  The twins k05, k23, j08, j10, k18, k13 and j06 are clean (the base raises a false alarm on j10); j09 ('12 mm = 0.012 m, so
  V = 50 × 0.012 = 0.60 m³') carries the coverage heuristic's INT-REQ-004 on every tree (the item asks for the volume, the
  answer names it only as V), which no reading of this round touches.
- **Time** (wall clock, shared machine): the arena rounds took 6.5, 9.8, 11.4, 9.0, 14.5, 9.0, 13.0, 49.4 and 71.9 s (before
  the round 6.6, 10.5, 12.0, 9.2, 14.0, 9.0, 13.1, 45.9 and 66.1 s); the three corpora 57, 22 and 19 s beside the suite (31,
  12 and 9 s before the round, run without the suite). The growth tests bound each changed reader by a ratio of CPU times,
  not by these figures.

*Versions.* The round changes rules of the translation pipeline, the argument rules, the relay history and the STEM front
end under the unchanged stamps (engine 0.5.0, policy 2026.10-v5, translator 0.5.1, rules `argdiag-2`), as repair rounds 1
to 5 and close rounds 1 and 2 did. No engine source changed (`engine.identity.BUILD_SOURCES`: `version.py`, `named.py`,
`lexis.py`, `ir`, `engine`), so the engine build identity is close round 3's and an engine result decides the same encoding
the same way; a translation record or a receipt of the tree before the round still reads as current.

## 18. Accuracy round 2

The items of accuracy round 2 are what the independent verifiers of round 1 found (V1I-01 to V1I-07 on the round's items,
and the global findings V1-STEM-GIV-FA, V1-BARE-CIRCULAR, V1-RESTATE-SUSPENDED, V1-STANCE-QUADRATIC and V1-TEST-INVERTED),
and one false alarm the round's own probes found. The round's rule: a reading already narrowed in round 1 that still
misfires is reverted to the committed base's behaviour for its class, not narrowed again, and what detection the revert gives
up is recorded below; a correct answer comes out as on the base (no warning or error, the same releasability or better);
every defective twin the staged tree caught before round 1 stays caught unless a revert gives it up; every diagnostic only
adds information. Every new or changed pattern and reader is linear in its input, with a growth test (two sizes, a ratio of
CPU times). Tests: `tests/contract/test_accuracy_round2_cases.py` (22 cases of the round's own wording in
`tests/data/accuracy_round2_cases.json`: 10 defective twins named; 12 controls clean, one of them released where the tree
before the round held it back and one recorded at info), `tests/translate/test_accuracy2_readers.py` (each reader of the
round on its own, and its growth) and `tests/stem/test_accuracy2_stem.py` (the STEM items: 7 wrong answers named, 11
controls clean, the miscopy reading and the growth of the STEM readings). Run on the tree of round 1, 21 of the contract and
STEM tests fail, each a fixed item's control or twin (the reader tests import readers the round adds).

| Item | What was wrong | Fix | Given up or left |
| --- | --- | --- | --- |
| V1I-01 (DIFF3-05, EVD-SRC-006) | round 1's clause reading (`_stance_clauses`) counted the stance holder's word ('farmer', 'resident', 'worker') as what the stance is about, so a document's approving clause about another subject still counted: 'Farmers welcomed the heavy rain in April, but the new water tax angered them deeply.', cited for 'farmers opposed the water tax', was named `source_mismatch` (EVD-SRC-006, INT-ARG-001) where the base raises nothing | reverted to the base's behaviour for its class: the stance is decided only where every clause of the document that speaks of what the claim's stance is about holds a stance word of the other side (`diag_evidence._stance_index`, one pass over the document; a clause whose stance word governs an object pronoun, 'Farmers welcomed it warmly.', speaks of what the clause before it names), and what the stance is about is what the claim's stance word governs, never its holder (`_stance_object`; for a passive, the words before it; for a stance word that ends its clause, the words after the judging verb: 'the German delegate thought the treaty fair' is about the treaty). A document that speaks of it anywhere without a stance word of the closed lists ('angered' is none) states a stance the lists cannot read, so nothing is diagnosed there, as on the base. `_stance_clauses` is removed | given up: a document that states its stance on the subject only in other words than the claim's (vp_stance_settlement_bad: its delegates 'welcomed the settlement as fair', for a claim about the treaty; named before the round, missed now, as on the base) or by a subject pronoun |
| V1-STANCE-QUADRATIC | `_stances` read each stance word's clause back to the clause's start, and `_stance_clauses` copied a clause's stems for every stance word: time and memory quadratic in a supplied text (up to 400,000 characters) whenever a claim attributes a stance to it (the verifier's document of 100,000 characters took 117 s; one of 399,000 more than 20 minutes) | `diag_evidence._stance_side` reads a stance word's clause back at most as far as the stance window (three tokens), and the index reads each clause's stems once | none |
| V1I-02 (DIFF3-03, DIFF3-04) | a true task fact stated with a phrasal verb outside the closed lists ('drove its costs down', 'knocked its prices down', 'put their prices up') was refuted (EVD-SRC-005, GROUNDING:FAILED, INT-ARG-001), and one restated in other words named `unchecked_source` (tc06: EVD-SRC-001), where the base raises nothing | (a) `grounding._words_no_record_holds`: the premise's own verb of a change is held when a clause of the task states a change of its direction, in any words, of the premise's own subject (`_task_change_clauses`, `change_marks`: a listed verb, a listed phrasal verb, or a particle 'up', 'down' or 'back'; `clause_direction`: the word of a change nearest to the premise's other words; `_held_change_roots`), so 'lowered its costs' is no word the task lacks beside 'drove its costs down', while 'lowered interest rates' is not held by 'After inflation fell, the central bank raised interest rates'; a change held in other words stands for no other missing word, so 'unemployment in Country Y declined in 2022' for 'Unemployment in Country Z fell in 2022' is refuted as before. (b) `grounding._task_conflict`: a sentence that holds a particle the listed phrasal verbs do not read (`_unread_particles`) refutes no direction, as on the base (round 1's phrasal reading is reverted for that class; the time and tense readings still run first). (c) EVD-SRC-001: round 1's restatement reader of synonym tables (`_restated_by_task`, `_task_restatements`, `_restatement_roots` and their closed lists) is removed; a label-only task-authority premise whose words a sentence the task asserts holds (`_asserted_by_task`: all of its content roots but one, at least two, its own verb of a change held by an asserted clause of that sentence as in (a), and then, when held only in other words, every other root held but one a pronoun of the sentence stands for; the same polarity, no suspending word) is recorded at info ('recorded, not charged; it is still unvalidated in this process'), not charged at warning. Its grounding record is unchanged, so the answer is no more releasable | given up: a premise that holds all of an asserted task clause's words but one while misreading it ('will raise interest rates again' beside 'which raised interest rates last year') is recorded at info rather than named at warning; it stays unvalidated and not releasable. The twins t07, t08, t10, t11 and y06 stay named; t09 and t12 (the other direction stated of another subject) keep their EVD-SRC-001 warning, and p10, p12 and p13 (another country, year or tax beside a verb in other words) their refutation or warning |
| V1-RESTATE-SUSPENDED | a premise that states as done what the task says was only expected ('the central bank in Country Q increased interest rates' for 'kept interest rates unchanged, although commentators had expected it to raise interest rates') lost its EVD-SRC-001 | `diag_evidence._task_statements`: a clause that holds a word of `_UNREALISED_WORDS` (expect, anticipate, predict, forecast, hope, intend and their forms; 'than expected' and 'as expected' state what happened, and after a determiner the word names a thing: 'the expected rise') suspends, as the grounding reader's closed lists do; a suspending relative clause suspends only itself; and the premise's own change must be the statement's ('increased' is not held by 'kept ... unchanged'). vq2 is named at warning again | none |
| V1I-03, V1-BARE-CIRCULAR (DIFF3-01) | since round 1 a cause phrase counts as a reason (`offers_cause`), so a cause phrase that only restates the point ('The Berlin Wall fell in 1989 due to the fall of the Berlin Wall in 1989.', b13; c05; vp_bare_circular_cause) or a vague one passed with no flag, where the tree before round 1 named them `bare_assertion` | round 1's cause-phrase reading stays: it is the base's behaviour for its class (the base names no bare assertion), and the rule forbids narrowing it again. The circle is named by the report-layer circle rule instead: `diag_argument.own_reason_circle` (ARG-CIRC-003, `circular_reasoning`) reads a cause phrase as the claim's reason (`_point_and_reason`: 'P due to R', 'Due to R, P') on every claim the bare-assertion rule reads, and names it when the reason only restates the point by the engine's closed tables; b13, c05 and vp_bare_circular_cause are named | given up: a circle whose reason adds words of its own (vb1 'over the party', vb2 'their faster growth') and a vague cause (vb3 'many different economic problems', vp_bare_after_date 'a very difficult year in Germany', vp_bare_vague_cause): named before round 1, missed now, as on the base |
| V1I-04 (ADV6-05) | an answer that mentions a rounding and then draws its conclusion from the value before it ('30.4 m s⁻¹, which rounds to 30 m s⁻¹; but 30.4 m s⁻¹ exceeds 30 m s⁻¹') was named `stem_rounding_changes_conclusion` (r07, z02 and z03; z01 also on the tree before round 1) | `stem.relations._restates_unrounded`: no `rnd` check is planned when the comparison's other side is the value before the rounding (the same unit, or both bare) | none: the round-1 repros q18, r07 and r08 stay named |
| V1I-05 (DV2-03, DIFF3-07) | a source rule quoted verbatim and applied to the case the question names ('When the river floods, farmland is damaged' for 'farmland near the Tamar was damaged in 2021'; 'If interest rates rise, borrowing falls.' for 'borrowing in Country P fell in 2022'; 'the enzyme denatured in the experiment') was not verified (ENTAILED, held back, ARG-LINK-001 at info) where the base releases it | `stated_rules.stated_rule` reads the rule a second time when its first reading (round 1's, unchanged) finds none: a setting phrase of a side's meaning is an instance word (`_setting_words`: a preposition of `_SETTING_PREPOSITIONS` and its determiners, then up to three names, or after a determiner one head noun with the closed ordinal modifiers before it; never a verb form, a word the excerpt holds, or a word that carries a rule's content); the two sides must place the same case or one side none ('in Country Q' beside 'in Country P' places two; a year is the year rule's); the second reading only verifies an unqualified rule | none: A02, w04, x1, x3, d01, d02 and acc2_rule_ok_instance_place are released; a hedged rule applied to a case stays unverified, as before the round; s09 stays refuted (section 17) |
| V1I-06 (ADV6-03) | on a general branch (Geography), quantities the request gives in different units combined without conversion ('Total distance = 1.2 + 300 = 301.2 m' for 1.2 km and 300 m; 'V = 50 × 12 = 600 m³' for 12 mm of rain on 50 m²) were missed on every tree: the general packs' formal checks were built without the request | `CorePack.formal_checks_for(report, request_text)`, which `SubjectBranch.run_packs` prefers, adds `packs.request_unit_formal_checks`: the worked-equation view read again with the request (`stem.build_document`), keeping only the traced unit companions whose every traced number is a quantity the request states with its unit (`core-req-stem-…`, `stem_unit_error`, warning); a number of the answer's own, a conversion factor or a rate per 1,000 builds none | none: r05 and r06 are named |
| V1I-07 (DIFF3-02, ARG-NS-003) | a prose bridge ending 'so ...' whose reason clause states a step of the writer's own that shares no word with the conclusion's target ('The Crash made American banks recall their loans to Germany, so German unemployment rose.', n04) was named an unbridged leap where the base raises nothing | round 1's reason-clause bridge (`_Sentence.reasons`, `_bridges` on the reason clause) is reverted; a join whose reason side holds a content root of the writer's own beside the leap's reason and its conclusion (a number or a month aside: `diag_argument._own_step`) is not read as the leap's join, as on the base, which names no unbridged leap; in a sentence that quotes, the words around the quotation attribute it and are no step of the writer's own, and round 1's quotation bridge decides, as before the round (n06 keeps its ARG-NS-003) | given up: a 'so' sentence whose reason adds a step of its own that bridges nothing (n08: 'The occupation of the Ruhr angered German workers, so the Weimar Republic collapsed.') is no longer ARG-NS-003; it keeps ARG-LINK-001 and is not releasable. ns03, n06, n07, n08, n09 and k04 stay named |
| V1-STEM-GIV-FA (ADV6-04) | a value of the answer's own that the subject supplies (the boiling point of water beside a room at 25 °C; the speed of sound, 340 m s⁻¹, beside a car at 20 m s⁻¹) was read as a replaced given (FORMAL:stem-giv, INT-SUBJ-004 and the synthesis's INT-HIST-001: `stem_contradictory_givens`) where the base and the tree before round 1 are clean | `stem.relations._miscopied`: the bare-given reading compares a value with the request's quantity only when it is a miscopy of it: the same number of significant digits, one digit changed or the digits in another order, the same sign and a size within a factor of ten | given up: a replaced given that is no miscopy ('(10 − 2.5)/3.0' for 4.0 m s⁻¹) is not named, as on the base; g03 ('R = 12/3.0' for 24 V, half the value) is missed on every tree, by the reading's exclusion of a factor of two |
| V1-TEST-INVERTED | round 1 rewrote four channel tests to a new outcome with weaker assertions: an inverted `carried and ...`, a check of the carried findings dropped, and three forwards moved from an exact rule to a weaker peer rule | each is exact again, and says so in its text: `tests/channel/test_response_gate_b13.py::test_a_finding_carried_from_a_receipt_the_gate_reads_is_not_counted_twice` pins the carried findings (none), the arrival's notes and the forward's history as literal lists, and restores its assertions of before round 1 on a forward built with the carried finding (a carried finding read with its source receipt is counted once); the forwards of `tests/channel/test_peer_exchange.py` and `tests/channel/test_round2_fixes.py` (two) assert the carried and the listed findings as literal sets (`history_support.assert_forwards_to_a_peer_exactly`), with the arrival's INT-REQ-004 and its status | none |
| EVD-AUTH-001 (the round's own probes) | an authority cue that introduces a quotation located in a supplied text ('Historian M argues that "the Crash drove German unemployment up"', quoting Source A) was named `uncheckable_authority` (EVD-AUTH-001, INT-ARG-001 at warning; m03 and n05 of the verifier's probes) | `diag_evidence.evd_auth_001`: a cue followed within 600 characters by a quotation the located-quotation reader finds in a supplied text names that text's authority, which is attributed and checked | none: an appeal to unnamed experts the source does not hold stays named |

The A and B items of round 1 are as section 17 gives them, with the changes above (its superseded note); DIFF3-08 (low) is
left for the reason given there. Moved out of the known limits (section 7): ADV6-03's general-branch shapes and A02.

Tests rewritten, each stricter and saying so in its text: the two tests of `tests/translate/test_accuracy1_growth.py` that
measured readers the round removes (`_stance_clauses`; `_task_restatements` and `_restatement_roots`) measure, on the same
inputs and on an input of distinct words besides, the readers that replace them; the four channel tests of V1-TEST-INVERTED.
No other test was changed.

**Measured** (at the end, on a fresh copy of the staged tree; after the copy was taken only this text changed. "The base" is
the committed code, "before" the staged tree at the start of accuracy round 1; other test runs shared the machine. The
measurement was run three times: the first was stopped after the corpora, the second ran in full and its probe comparison
found regressions the round then fixed (e04b's EVD-SRC-006; the warnings of t09, t12, p10, p12 and p13; tc12; n06's
ARG-NS-003); the figures below are the third run's, on the tree as staged):
- **Suite**: 9191 passed and 45 deselected (the stress selection, not run) in 709 s, no failure (round 1's 9132 tests and
  this round's 59). In the second run three wall-clock bounds failed under load
  (`tests/engine/test_stem_shapes.py::test_median_time_per_shape_is_below_50_ms` and two parameters of
  `tests/translate/test_coverage_assertion.py::test_reading_every_figure_of_a_long_untrusted_text_stays_linear`); they
  passed alone on that copy and on the tree before round 1, and in the third run.
- **Corpora**, case by case: development (101 cases) 44 of 44 defects named, 57 of 57 controls clean, 47 not releasable;
  hold-out (134) 64 of 66 named, 2 caught but not named, none missed, 68 of 68 controls clean, 37 not releasable; second
  hold-out (136) 70 of 70 named, 55 of 66 controls clean, 20 not releasable. Every case gives the outcome it gave after
  round 1, so none is worse than before round 1 (development 1 and second hold-out 6 better: the INT-HIST-001 carries
  DV2-05 removed) or than the base (78, 75 and 73 better).
- **Arena replays** on fresh copies (r1, r1-adv, r2 to r7, run1), answer by answer: the functional counts are those of
  before round 1 (30/30, 150/151, 46/46 on r2 to r6, 177/177, 120/134); no genuine answer gains a finding at warning or
  above and no planted fault loses its flag or its functional mark; every answer has the findings it had after round 1
  (DV2-05's relays and syntheses as section 17 gives them).
- **Probe groups** (435 cases in 48 groups: the round-1 verifiers' groups, the review groups the items name and this round's
  own; base / before round 1 / the copy): controls clean 181 / 131 / 225 of 268 (false alarms 87 / 137 / 43); defects named
  9 / 94 / 128 of 167, caught but not named 68 / 24 / 20, missed 90 / 49 / 19. No control the base keeps clean warns on the
  copy but s09 and the sonar depth, both as before round 1, and none is less releasable than on the base. The defects
  caught before round 1 and missed now are the given-up ones (vb1, vb2, vb3, vp_bare_after_date, vp_bare_vague_cause,
  vp_stance_settlement_bad) and v_dv205's p06 and p07, whose answer is a correct History explanation by a cause phrase
  under a STEM label, caught before round 1 only by ARG-BARE-001's false alarm (DIFF3-01). By item: V1I-01 s01, s03,
  u01, u05, st01 and st04 clean, s06, s07, s08, st02 and the two pronoun twins named, e04a and e04b keep EVD-SRC-006;
  V1I-02 t01 to t06, y01 to y05 and tc01 to tc13 (the controls) clean, every twin named or caught with its warning; vq2
  named at warning (V1-RESTATE-SUSPENDED); b13 and c05 named `circular_reasoning` (V1I-03); V1I-04 r07 and z01 to z04
  clean, q18, r07 and r08 named; V1I-05 A02, w04, x1, x3, d01, d02 and the round's instance case released, A06, A07, w08,
  w09 and d08 named; V1I-06 r05 and r06 named, u08 to u16 clean but for u13's coverage warning, which every tree raises;
  V1I-07 n04 and ns02 clean, ns03, n06 to n09 and k04 named; V1-STEM-GIV-FA s01, s20 and the round's two knowledge cases
  clean, every ADV6-04 twin named but g03; EVD-AUTH-001 m03 clean and n05 without it.
- **B repros** on the copy: ADV6-03 q08 to q12, r04, r05 and r06 named (r05 and r06 for the first time), k05, k23, j08 and j10
  clean, j09 with the coverage heuristic's INT-REQ-004, as on every tree; ADV6-04 r09, r10, q22 and q23 named, k18 clean;
  ADV6-05 q18, r07 and r08 named, k13 and j06 clean.
- **Time**: V1-STANCE-QUADRATIC's cases, one case a run (wall clock, the process start included): 1.7, 1.8, 2.1 and 1.9 s at
  12,500, 25,000, 50,000 and 100,000 characters, 3.2 s at 399,000 (the verifier measured 1.7, 7.6, 28.7 and 117 s on
  round 1's tree, and more than 20 minutes at 399,000). The readers alone, in CPU time on a document of distinct words of
  2,000, 8,000, 32,000 and 128,000 characters: `_stance_index` 0.002, 0.008, 0.033 and 0.141 s, an EVD-SRC-006 call 0.012,
  0.057 and 0.255 s from 8,000 characters on (round 1's `_stance_clauses`: 0.004, 0.033, 0.83 and 13.2 s). The arena rounds
  took 7.1, 11.2, 12.4, 9.6, 14.4, 9.7, 15.0, 48.1 and 78.4 s wall clock (before round 1 6.6, 10.5, 12.0, 9.2, 14.0, 9.0,
  13.1, 45.9 and 66.1 s); r7 and run1 took 46.5 and 74.7 s of CPU time (user and system), 53.8 and 74.1 s on the tree before
  round 1; the corpora 70, 26 and 22 s beside the suite. The growth tests bound each changed reader by a ratio of CPU
  times, not by these figures.

*Versions.* As in round 1: rules of the translation pipeline, the argument rules and the STEM front end change under the
unchanged stamps (engine 0.5.0, policy 2026.10-v5, translator 0.5.1, rules `argdiag-2`). No engine source changed
(`engine.identity.BUILD_SOURCES`: `version.py`, `named.py`, `lexis.py`, `ir`, `engine`), so the engine build identity is close
round 3's.

## 19. Scope statement

Every result and every diagnostic proves a property of the encoding and of this code only: what the encoded premises do
or do not entail under the stated configuration, which premises a check in this process established, and which shapes
the encoding has. It does not establish that a premise is factually true, that a natural-language claim was translated
faithfully, that a literary, historical or rubric judgement is correct, that a law applies or that data are true.
Grounding and semantic-fidelity information is reported separately and is advisory.

## 20. Port onto the integrated translator

The feature was built on its own line (c219b4f, on the 17 October base 7991e8b). The integrated translator fixed many of
the same review and arena findings independently and differently, so a merge conflicts in 48 files. The feature is
therefore ported, not merged, under one rule (the owner's): **the integrated translator's behaviour wins every
contradiction.** Where c219b4f carries its own version of a fix the integrated tree already has (request validation,
signatures and provenance, translation staleness, word counting, worked arithmetic on general branches, figure subjects
and years in grounding, precision readings, peer documents, unit readings, parser and pack readers made linear, ledger
readings, relay history, ...), the integrated version stays and the duplicate is not ported. In particular a request over
the contract's limits stays REJECTED with INT-REQ-009 (never truncated with INT-REQ-018), and the STEM tolerance keeps the
sum rule |w - b| <= h(b) + h(w).

The port has two steps. **Step 1** (this section) ports everything of the feature outside `src/epinoic_logic/stem/`:
unchecked sources (issue 1) and unstated links (issue 2). **Step 2** (sections 20.6 to 20.9) ports the STEM method faults
(issue 3: `stem/reference.py`, `stem/reference_data.py`, `stem/word_formulas.py` and their hooks), on the integrated STEM
front end and checks; where section 3.4 describes a reading of the feature line's own front end that this tree reads its own
way, section 20.7 says so.

### 20.1 What step 1 ports

* **Modules of the feature** (new files): `named.py` (the named-code table, display lines, release lines), `lexis.py`,
  `engine/argument.py` and `engine/argument_cues.py` with `engine/ARGUMENT.md`, `translate/diag_core.py`,
  `translate/diag_argument.py`, `translate/diag_evidence.py`, `translate/roles.py`, `translate/stated_rules.py` with
  `translate/ARGUMENT_DIAGNOSTICS.md`, `channel/gate.py`, and the prompt `translate/prompts/translate_v3.md` (packaged,
  not in use: see 20.3). `translate/diag_figures.py` is new on this tree: it holds the figure readings the evidence rules
  were measured with (EVD-FIG-001, EVD-LACK-001), kept apart so that they decide no grounding.
* **Hooks in existing modules**, adapted to the integrated code: the argument stage of `engine.verify` and its
  `named_diagnostics` and `argument_rules` on `VerificationResult` (signed with the result); release rules 8 (no named
  defect at effective warning or error) and 9 (diagnosed by these rules) in `engine/release.py`; `named.py`, `lexis.py`,
  the rules version and the named-code digest bound into the build and policy identities (`engine/identity.py`);
  `ARG_RULES_VERSION` in `version.py`; premise roles and the provider's asserted `verified` paths on the translation
  record (`translate/contracts.py`, `pipeline.py`, `parsing.py`); claim and report diagnostics on outcomes and receipts
  (`translate/outcome.py`, `channel/bus.py`, `channel/contracts.py`); the task-fact readings of `grounding._check_authority` (a rule or a proposition a task
  sentence states validates a task-authority premise); the UNENCODED_REASON encoding flag; the readers the diagnosis
  uses in `adapters/markdown.py` (reason and conclusion leads, `cited_quotation_spans`); the overseer's reading of the
  new receipt fields (`overseer/checks/receipts.py`, `translation.py`, `delivery_policy.py`) and its shadow channel,
  which verifies a recorded ambiguous translation with the same info cap as `translate.outcome.verify_claim`
  (`overseer/checks/shadow.py`; without it the shadow re-derived INT-ARG-001 warnings the receipts rightly carry at
  info, `tests/overseer/test_rebuild_rekeyed_r7.py`); the integrity and branch
  hooks that carry the records.
* **Diagnostics only add information**: no status is upgraded, release only becomes stricter (rules 8 and 9), and the
  signed result covers the named diagnostics and the rules version.

### 20.2 Versions

The four component versions stay as the integrated tree has them (engine 0.4.0, policy 2026.10-v4, translator 0.4.0,
IR 1.0): the integration kit's compatibility record pins them. The build and policy identities already separate a
diagnosed result from one of an earlier build (they bind `named.py`, `lexis.py`, the rules version `argdiag-2` and the
named-code digest). The release assessment keeps its name `release-v1` with rules 8 and 9 added. Whether the release that
ships the diagnostics bumps the versions, and moves the prompt in use to `translate_v3`, is a decision of the final
integration.

### 20.3 What is not ported, and why

Behaviours of c219b4f that contradict the integrated translator (the integrated behaviour stays):

* **UNLINKED_CONJUNCT (end-to-end item B8).** On the feature line an encoding whose conclusion has a conjunct no premise
  mentions, while its linked part follows, became AMBIGUOUS_TRANSLATION. On this tree it keeps its COUNTEREXAMPLE, so a
  refuted answer is withheld with its score (`tests/e2e/test_arena_deliveries.py`, `test_a_refuted_answer_is_withheld_with_its_score`
  and `test_the_pass_never_goes_through_a_replaced_verifier`). The engine's ARG-PART-001 info record still names the
  unlinked judgement.
* **Authority for circularity.** The feature made every premise no check established the writer's own for circularity
  (`engine.authority.assumed_grounding` = `not has_authority`), so a label-only `task_setting` restating the point was a
  circle even with no task record. On this tree such a premise is unvalidated, not a circle, and is shown as the
  encoding's result, never released (`tests/engine/test_round7_engine.py::test_a_restated_task_setting_is_a_transcription_not_a_circle`,
  `tests/translate/test_review_2026_10_12_translate.py::test_a_restated_trusted_kind_is_a_transcription_only_when_the_task_states_it`,
  `tests/translate/test_round7_translate.py::test_a_transcription_of_the_task_is_no_circle`).
* **A figure-free task premise that restates the point, with the task record given.** The feature left a figure-free
  task-authority premise no check verified unvalidated (`verified=None`) whenever the records hold its words, and relied
  on its authority rule (above) to keep a restatement of the point a circle. This tree keeps the integrated grounding's
  refutation ("no record validates it") for a premise that restates the point (every atom it mentions is the
  conclusion's), so the restatement stays a circle (E112) under the integrated authority rule; a proposition the task
  only quotes for discussion is refuted and its restatement is a circle, as `tests/translate/test_close2_task_proposition.py`
  expects. Every other figure-free task premise stays unvalidated and is named `unchecked_source`, as on the feature
  line.
* **A located quotation that restates the point.** The feature refuted a premise that restates the point when its
  located excerpt does not state the point's words (`content_in_excerpt`, re-run review ADV-01). On this tree a verified
  quotation premise identical to the conclusion is a transcription, not a circle and no finding
  (`tests/overseer/test_review1_content_checks.py::test_a_verified_quotation_premise_identical_to_the_conclusion_is_a_transcription_not_circular`,
  `tests/overseer/test_rebuild_merged_translator.py::test_control_a_restatement_whose_excerpt_the_check_locates_is_a_transcription_with_no_finding`),
  so that check is not ported.
* **The prompt in use.** `translate_v3` is packaged but the prompt in use stays `translate_v2`, which the integrated tests
  pin (`tests/translate/test_pipeline.py`, `tests/translate/test_stem_subjects.py`); the marking guidance of the argued
  profiles (`subjects.ARGUMENT_MARKING_GUIDANCE`) goes with v3 and is not ported.

Duplicates (the integrated tree's own fix stays; the feature line's version is not ported): the engine's arithmetic
restatement normal form and the coefficient and forced-value digit bounds (E307), result signing and provenance, the
service's and the command line's signature and key handling, request validation, the figure-subject, year, list, mean
and conversion readings of grounding and the grounding from the answer's own worked arithmetic
(`grounding.answer_derived_figures`), precision readings, peer-document labels, unit readings, the quotation-role reader
in the parsers (end-to-end items B5 and B6), quotation credit, self-certification readers, the parsers' conclusion-lead
reading, the linear-time rewrites of shared readers, the synthesis ledger's readings, relay history (INT-HIST-001),
request items, word-bound scopes and meta-text, JSON envelopes, and the STEM review's claim ids and coverage.

`docs/DESIGN.md` of the feature line is not ported: it describes that line as a whole, under its own versions.

### 20.4 Tests

Every test of the integrated tree is kept. Two pin exactly what the port adds to, and are updated no less strictly:
`tests/engine/test_pack_policies.py::test_the_result_model_gained_exactly_one_field` still pins the result model's field
set exactly, now with the two signed diagnosis fields (`named_diagnostics`, `argument_rules`, each defaulting to None),
and `tests/engine/test_review_engine_fixes.py::test_the_build_identity_changes_with_any_decision_source` copies every
entry of `BUILD_SOURCES` (now with `named.py` and `lexis.py`) and also asserts that a change to `named.py` changes the
build id. The feature's test files that test its modules and behaviour are
ported, adapted where the integrated code differs (a helper that passes no answer texts, the release name `release-v1`,
the prompt in use). The tests below are not ported, each with its reason.

Contradicted (the test pins the feature line's own version of a behaviour the integrated translator decides otherwise):

* `tests/translate/test_partial_encodings.py`: `test_no_b8_claim_is_counted_as_a_counterexample_on_the_receipt` and
  `test_the_seven_b8_counterexamples_are_ambiguous_with_the_unlinked_judgement_named` (UNLINKED_CONJUNCT, above).
* `tests/translate/test_close1_circular.py::test_a_heading_question_is_an_info_record_with_no_task_record_too`,
  `tests/engine/test_argument_diagnostics.py::test_a_restated_task_or_text_premise_is_a_circle_unless_a_check_validated_it`,
  `tests/translate/test_argument_rules.py::test_a_restated_task_premise_is_a_circular_refusal_unless_a_check_validated_it`
  and `::test_the_circularity_rejection_names_the_authority_rule`, and the whole of
  `tests/engine/test_authority_circularity.py` (the feature's authority rule for circularity, above).
* `tests/translate/test_unchecked_sources.py::test_a_figureless_task_premise_with_no_excerpt_is_unvalidated_and_a_conflicting_figure_still_refutes`
  and `tests/translate/test_repair_round4_grounding.py::test_a_task_premise_citing_only_a_peer_report_is_unvalidated_not_refuted`
  (each pins as unvalidated a figure-free task premise that restates the point; this tree refutes it, above).
* `tests/translate/test_repair_round1_grounding.py::test_a_quotation_whose_excerpt_does_not_state_the_premise_is_refused`
  (the restated-point excerpt check, above).
* `tests/translate/test_prompt_v3.py`: `test_v3_is_packaged_and_in_use_and_the_earlier_prompts_are_byte_identical`,
  `test_the_version_is_bound_into_every_translation`, `test_a_prompt_name_is_matched_whole` and
  `test_argued_profiles_carry_the_marking_guidance_and_stem_profiles_do_not` (v3 in use; the prompt in use stays v2).
* `tests/channel/test_response_gate_b13.py`: `test_the_correct_answers_are_delivered_not_verified` and
  `test_the_other_correct_answers_are_delivered_not_verified_once_the_false_findings_are_gone` (they pin how the gate
  shows end-to-end answers once the feature line's own versions of the channel and pack fixes, and B8, removed their
  false findings; on this tree those answers keep the integrated tree's findings and display), and
  `test_a_finding_carried_from_a_receipt_the_gate_reads_is_not_counted_twice` (relay history).

Duplicates (the test pins the feature line's version of a fix the integrated tree makes its own way):

* `tests/engine/test_argument_diagnostics.py::test_an_equivalent_restatement_is_circular_circ_002` and
  `tests/engine/test_argument_rerun_repairs.py::test_a_restatement_in_arithmetic_form_is_e112` and
  `::test_an_equation_equivalent_to_the_point_is_circular_beyond_the_normal_form` (the engine runner's restatement normal
  form); `tests/engine/test_argument_diagnostics.py::test_e06b_the_verified_table_refutes_the_point_refute_001` (it
  needs the feature line's year-and-subject reading of the table excerpt, which the integrated grounding decides its own
  way).
* Grounding readings: `tests/translate/test_repair_round1_grounding.py` (`test_clean_control_the_converse_or_another_threshold_is_not_stated_by_the_rule`,
  `test_an_excerpt_about_another_entity_or_quantity_does_not_ground_the_figure`, `test_each_figure_of_a_dated_change_is_stated`,
  `test_the_divisor_of_a_mean_is_no_figure_the_excerpts_must_state`, `test_a_figure_the_answers_written_calculation_derived_grounds`,
  `test_clean_control_a_figure_nothing_derived_is_refused`), `tests/translate/test_repair_round2_grounding.py`
  (`test_an_exports_figure_cited_to_the_imports_clause_is_refuted`, `test_a_calculation_derives_its_result_only_when_it_gives_it`,
  `test_a_figure_the_answer_works_out_in_an_earlier_sentence_grounds_the_relation`), `tests/translate/test_repair_round3_grounding.py`
  (`test_a_bound_states_the_figure_of_a_symbol_that_names_the_bound`, `test_an_excerpt_states_its_figure_only_for_its_own_entity`,
  `test_an_excerpt_states_its_figure_only_for_its_own_quantity`, `test_control_the_compared_figure_is_not_the_other_quantitys`),
  `tests/translate/test_repair_round4_grounding.py` (`test_a_conversion_the_task_gives_in_an_instruction_validates_the_premise`,
  `test_a_figure_one_sentence_states_for_another_quantity_is_refused`, `test_the_answers_working_is_read_once_per_text_and_gives_the_same_figures`,
  `test_the_count_total_and_mean_of_a_stated_list_give_its_figures`, `test_the_length_of_a_quoted_list_is_read_off_the_excerpt`),
  `tests/translate/test_repair_round5_translate.py::test_an_excerpt_grounds_only_the_figure_of_its_own_quantity` and
  `tests/translate/test_close1_grounding_words.py::test_control_a_record_that_gives_the_quantity_another_figure_still_refutes_the_excerpt`.
* Precision, units and peers: `tests/translate/test_repair_round5_translate.py` (`test_a_cross_multiplied_ratio_at_its_wide_reading_is_a_precision_site`,
  `test_a_unit_glossed_in_parentheses_is_the_declared_unit_and_in_a_is_a_label`, `test_a_relayed_agents_text_is_a_peer_document_under_its_labels`).
* Parsers and packs: `tests/translate/test_repair_round1_evidence.py` (`test_a_derived_figure_is_checked_where_its_figures_are_stated`,
  `test_a_sole_judgement_line_is_the_answer_and_a_sign_off_is_a_note`, `test_the_history_pack_reads_a_historians_verdict_with_has_or_have`)
  and `tests/translate/test_repair_round3_reports.py` (`test_a_sentence_that_opens_with_a_conclusion_lead_rests_on_the_one_before`,
  `test_the_text_parsers_rest_a_ground_phrase_on_the_sentence_before`).
* Partial encodings: `tests/translate/test_partial_encodings.py::test_a_claim_with_only_its_first_clause_encoded_is_a_partial_encoding`
  (this tree's own `partial_encoding` rule decides it).
* Shared-module caches: `tests/translate/test_repair_round2_perf.py::test_the_circularity_cache_answers_by_content` and the
  markup half of `::test_the_token_and_markup_caches_give_the_uncached_readings` (the engine runner's and
  `adapters.markdown`'s caches are not ported; the token-cache half is kept as `test_the_token_cache_gives_the_uncached_readings`).
* Relay history (not on the integrated channel): the ADV3-02 half of `tests/channel/test_repair_round3_gate.py`
  (`test_a_carried_error_stays_failed_whatever_the_report_id_says`, `test_a_carried_finding_the_history_does_not_make_is_classified_as_itself`,
  `test_a_carried_warning_is_unresolved_and_the_constructor_is_the_channels_own`,
  `test_a_correct_answer_relayed_carries_nothing_and_is_not_withheld_for_history`; its INV-7 half is ported, with the
  clean control `i00_control_valid_rule` in place of `c01_control_econ_table`, whose table excerpt for another year the
  integrated grounding refutes), and the whole of `tests/channel/test_accuracy1_relay_history.py`,
  `tests/channel/test_close2_synthesis_layout.py`, `tests/channel/test_relay_history.py`.
* Whole files of the feature line's own fixes outside the feature, not ported: the quotation-role reader in the parsers
  (`tests/adapters/test_quotation_roles.py`, `test_close1_quotation_roles.py`, `test_close2_quotation_roles.py`,
  `test_close3_quotation_roles.py`, `test_repair_round4_quotations.py`, `test_repair_round5_quotations.py`,
  `tests/contract/test_quotation_stub.py`); quotation credit and self-certification (`tests/adapters/test_credit_by_title.py`,
  `test_sources_round8.py`, `test_security_round1_credit.py`, `test_security_round2_credit.py`,
  `test_repair_round2_self_certification.py`, `test_security_round2_self_certification.py`, `test_close1_selfcert_linear.py`,
  `tests/integrity/test_repair_round2_credit.py`); linear-time readers (`tests/adapters/test_linear_text_readers.py`,
  `test_note_clauses_linear.py`, `tests/adapters_history/test_repair_round3_chronology_scale.py`, `test_rerun_review_sentences.py`,
  `test_security_round1_historian.py`, `test_security_round1_wrap.py`, `tests/branches/test_accuracy_marks_linear.py`,
  `test_annotation_strip_linear.py`, `test_repair_round5_generic_lists.py`, `test_security_round1_dated_series.py`,
  `test_security_round1_digits.py`, `test_security_round1_lists.py`, `test_security_round1_rates.py`,
  `test_security_round1_request_relation.py`, `test_security_round2_clause_index.py`, `test_security_round2_share.py`,
  `test_security_round2_total.py`, `test_security_round2_transcribed.py`, `tests/channel/test_request_scope_linear.py`,
  `test_security_round1_marks.py`, `test_security_round1_meta.py`, `test_security_round1_parts.py`,
  `tests/integrity/test_close3_ledger_linear.py`, `test_security_round1_decrease.py`,
  `tests/translate/test_security_round1_conversion.py`); identifiers and contracts (`tests/adapters/test_whole_identifiers_sweep.py`,
  `tests/adapters/test_english_strands_scope.py`, `tests/branches/test_rerun_review_hub.py`, `tests/channel/test_strict_mappings.py`,
  `test_json_envelopes.py`, `test_resupplied_metadata.py`, `test_forward_reply_link.py`, `test_arena_conflicts.py`,
  `test_receipt_no_verdict.py`, `test_lens_round_d.py`, `test_repair_round2_channel.py`, `test_repair_round5_channel.py`,
  `tests/integrity/test_rerun_review_course_level.py`, `tests/translate/test_provider_output_bound.py`,
  `test_rerun_review_records.py`); end-to-end items of the channel, the branches and the ledger (`tests/branches/test_core_equations_b25.py`,
  `test_lens_rerun_c_branches.py`, `test_repair_round2_generic.py`, `test_repair_round2_packs.py`, `test_repair_round2_quant.py`,
  `test_repair_round4_mentions.py`, `test_repair_round4_quant.py`, `test_repair_round4_table_figures.py`, `test_stem_ids_b17.py`,
  `test_stem_review_claim_map.py`, `tests/channel/test_constraint_scopes_b4.py`, `test_meta_text_b19.py`, `test_relay_b3.py`,
  `test_request_items_b18.py`, `test_repair_round4_answer_words.py`, `test_stem_review_coverage.py`, `test_stem_task_agents_b17.py`,
  `tests/integrity/test_close1_ledger.py`, `test_close3_joint_memo.py`, `test_joint_invalid_claim_fr4.py`,
  `test_ledger_check_status.py`, `test_ledger_round8.py`, `test_pooled_precision_b7.py`, `test_pooled_precision_disjoint.py`,
  `test_repair_round2_figures.py`, `test_repair_round3_ledger.py`, `test_repair_round4_ledger.py`, `test_repair_round5_ledger.py`,
  `test_stem_review_ledger.py`); engine and service robustness, signatures and provenance (`tests/engine/test_repair_round2_coefficients.py`,
  `test_repair_round2_restatement.py`, `test_repair_round3_signatures.py`, `test_repair_round4_engine.py`,
  `test_rerun_review_provenance.py`, `test_rerun_review_runner.py`, `tests/service/test_e505_contract_b15.py`,
  `test_repair_round3_signatures_http.py`, `test_repair_round5_cli.py`, `test_rerun_review_cli.py`,
  `test_rerun_review_signatures.py`, `test_security_round8.py`); translation readings (`tests/translate/test_close2_precision_counts.py`,
  `test_grounding_round8.py`, `test_precision_b16_b22.py`, `test_repair_round2_readings.py`, `test_repair_round3_peer_ids.py`,
  `test_repair_round4_peer_labels.py`, `test_request_figures_b23.py`, `test_stated_precision_grounding.py`).

Deferred to step 2 (they score whole corpora whose cases include STEM method faults): `tests/contract/test_repair_round1_cases.py`,
`test_repair_round2_cases.py`, `test_accuracy_round1_cases.py` and `test_accuracy_round2_cases.py` (their data files are
already carried), and every STEM test of the feature (`tests/stem/`). Both are ported in step 2 (section 20.8).

### 20.5 Measured on this tree (step 1)

Measured with the recorded arena rounds available to the round-dependent tests (`EPINOIC_ARENA_ROUNDS` set to a copy),
on the directories step 1 touches and every ported test file: `tests/translate` and `tests/contract` 1792 passed;
`tests/engine`, `tests/channel`, `tests/branches`, `tests/integrity`, `tests/e2e` and `tests/service` 2581 passed,
3 xfailed, 1 deselected (by the suite's own configuration); `tests/overseer`, `tests/adapters` and
`tests/adapters_history` 3260 passed. No failure. The full suite, the arena harness on every recorded round, the
overseer's contained run and the three argument-diagnosis corpora are measured once, after step 2.

### 20.6 What step 2 ports (STEM method faults)

* **Modules of the feature** (new files, unchanged): `stem/reference_data.py` (the closed reference: 83 symbol entries, 15
  formulas, 109 data-booklet laws, and the cue tables of the named checks), `stem/reference.py` (its readers) and
  `stem/word_formulas.py` (word equations read in symbols, in the 1:1 reading view).
* **The front end's named findings** (`stem/relations.py`): the feature's readers of the method faults, added to the
  integrated planner as its own methods and run after every integrated post-pass (`_Planner.run`): ST-REF-001 and ST-REF-002
  (`_reference_formulas`, `_booklet_form`), ST-ROUND-001 (`_rounding_comparisons` and the rounding, target and condition
  readers it uses), ST-RANGE-001 (`_extrapolation`, `_request_law_ranges`), ST-WORK-001 (`_working`), ST-GIVEN-002,
  ST-GIVEN-003, ST-GIVEN-004 and ST-SCOPE-002 (`_rebindings`, `_dimension_rebindings`, `_unlabelled_rebindings`,
  `_mixed_groups`, `_inline_givens`, `_bare_givens`, `_overdetermined_givens`, `_set_counts`, `_probabilities`), ST-STEP-001,
  ST-STEP-002 and ST-STEP-003 (`_stated_operation`, `_division_note`, `_false_rewrite`), and the ST-UNIT-003 companions
  (`_unit_companion`, `_request_traced_companion`), with the module-level patterns and helpers they read (the feature's
  `_clause_tail` is kept as `_named_clause_tail`, beside the integrated `_clause_tail` of rule row-value). Their severities
  join `ST_SEVERITY`.
* **Hooks in the integrated planner**, adapted: the unit companion after the `eq` check of written arithmetic (with or
  without the integrated rule result-rounding), after a `sub` check that evaluates and after a formula evaluated at its
  stated values; the false-rewrite check before an undecided function of an unknown; the stated operation of a step
  (`_step`, also from the request's own equation when the answer's first line states the operation applied to it, and the
  operation read as a step cue in `_step_cues`); the condition points a chain evaluates at (kept for ST-RANGE-001); the
  final value of the chain each operand stands in and the chains that end in a rounding; a bare numeral substituted for a
  symbol bound nowhere else carries the request's SI unit for that quantity; the inline givens after the integrated
  givens; the request's data series and years (`document._request_series`, new fields `RequestReading.series` and
  `RequestReading.years`; the feature's own reading of `RequestReading.values` is replaced by the integrated one, whose
  entries carry a fourth field); `plan_relations` receives the whole answer (for the extrapolation caveats) and the
  reference-checks switch, and gives a companion the id of the check it accompanies with `u` appended.
* **Checks** (`stem/checks.py`): the builders `unit`, `op` and `rnd`, their kind names and titles, the companion's readings
  (`both` in `_readings` and `_reading_modes`), the `implies` combination and the SI pairs of a traced companion in
  `_compare`, and `PlannedCheck.defect` (the STEM pack already copies it to `FormalCheck.defect`, step 1).
* **The document** (`stem/document.py`): the word-equation view in the sciences profiles and the `reference_checks`
  switch of `_build` (off while the closed table of booklet laws is itself read; it is part of the document cache key).
* **The core pack** (`branches/packs.py`): `request_model_extrapolation`, ST-RANGE-001 on a general branch when the request
  states a model and the range of its data.
* **Adaptations to the integrated tree**, each found by an integrated test and made where the feature's reading met it:
  ST-WORK-001 reads no result in a Given or in a value the integrated rule named-given sets against the request ("Given:
  u = 0", "The battery's emf is 12 V.": a restatement of the data); ST-REF-001 and ST-REF-002 read what a symbol stands for
  from the values the answer substitutes for it with a unit too ("V = 12 V − (4.14 A × 0.50 Ω)" after "V = ε − Ir": r is a
  resistance, never the radius the table gives the letter; recorded arena answer ph-t13); a stated operation the prose
  negates ("Factorising, rather than dividing by t, keeps t = 0.") is a mention, no step (recorded arena answer maa-t13,
  whose receipt stays as recorded); a year-shaped figure of the supplied data ("The uncertainty in 1620 is ±2% × 1620",
  a count rate of the supplied table) is no year a model is evaluated at; no `written` companion is planned (20.7).
  `ST_SEVERITY` also lists the codes of the engine-decided checks (ST-UNIT-003, ST-STEP-001, ST-ROUND-001, warning), which
  name no front-end finding, so the overseer pack's table of ST codes is the STEM package's own.
* **The overseer pack** (pack 1.3, corrected in place): dossier guide D32 (`02-dossier.md`) lists the thirteen new ST
  codes with their severities and defect labels; the manifest is regenerated with `python -m epinoic_logic.overseer.export
  --refresh-source` and the new pack digest pinned in `overseer/pack.PACK_DIGESTS`. The schemas are unchanged (no contract
  changed). *Corrected by the integration step (31 October; `docs/OVERSEER_DESIGN.md` section 47, decision 79):* a pinned
  pack version never changes, so 1.3 is restored to the digest it was released under (`b44776a1…`, pinned again) and this
  correction is released as pack 1.4, with the overseer's reading of everything the translator emits (the argument
  diagnosis on outcomes, receipts and signed results, release rules 8 and 9, every code with its severity).
* Docs: `stem/README.md` and `stem/ENCODINGS.md` (the three modules and the `unit`, `op` and `rnd` kinds).

### 20.7 What step 2 does not port, and why

Contradicting the integrated translator:

* **No `written` unit companion.** On the feature line the check a `written` ST-UNIT-003 companion accompanies was decided
  under the as-written and the SI readings alike (so it held when the numbers held as written, and only the companion
  failed, naming `stem_unit_error`). The integrated checks admit no as-written reading that the relation's own units
  contradict (`checks._as_written_consistent`), so that check already decides the relation in SI alone and fails on the
  unit error (INT-SUBJ-001, labelled by its kind); a companion would only repeat its verdict, and the integrated tests pin
  that such a relation plans one check (`tests/stem/test_round7_arena_fixes.py`, `test_stem_repair6.py`). So only the
  `traced` companion is ported: bare numbers that repeat the numbers of non-SI bindings or of the request's quantities,
  which the integrated check reads as written. The name the companion gave is kept on the one integrated check instead
  (section 20.10): a check decided in SI alone whose numbers hold as written names its failure `stem_unit_error`.
* **The STEM tolerance rule.** The feature's tolerance policy (request intents for exactness and rounding, the measured-
  operand rule, `max(h, h')` for a value set against a value, the angle hint, the degrees-against-radians rule) is not
  ported: the sum rule |w − b| <= h(b) + h(w) and every integrated tolerance reading stay. A ported `op` or `rnd` check
  uses only the half-width of the value it compares, as on the feature line.

Duplicates of the integrated STEM readings, or readings of the feature line's own front end that this tree makes its own
way (the integrated reading stays; the named checks run on what it reads):

* Simultaneous equations (`sys`, `_systems`, `_equations_solved_later`), stated root sets and their members
  (`_root_set_members`, `_listed_members`), factorising and named identities (`_cued_identity`, its `inferred` alg checks),
  Boolean evaluation and the AND dot (`_boolean_values` of the feature, `boolean._chain_links`, `lexer.writes_constant_dot`),
  two's complement and binary literals (`_binary_operand`, `_binary_literals`), trig angles in degrees and radians, affine
  temperatures (`to_ir.affine_role`, `checks._affine_mode`), approximation words (`tolerance.approx_qualifies`), the
  restatement and result readings (`_results` with its sign and scale rules, `_scale_after`), comparisons the answer says
  fail (`negated` cmp checks), conditions and inequalities about another part's symbol (`_bound_in_part`), named conditions
  (`document._names_a_condition`), and the units, numbers, lexer, layout, segment, span and parser changes of the feature
  line (space-grouped numerals `numbers.scan_grouped_based`, the spaced product of quantity letters `spans._quantity_run`
  and `parser._juxtaposable`, a computation continued by its head on the next line `_repeats_head` and `head_gap`, a
  symbol after a condition's value, emphasis and markup indexes, nuclear equations, compound quantities read from the span
  finder's tokens).
* The feature's dimension reading from substitutions (`dimension_of(..., substitutions=True)`, `_chain_dimension`) and its
  coefficient reading in `_dim`: the integrated dimension check (ST-DIM-001, rule bare-factor) stays as it is.
* The request's unit companions on general branches (`packs.request_unit_formal_checks`, `_request_unit_checks`,
  `_worked_view`): they rest on the feature line's own reader of worked equations on general branches, a duplicate of the
  integrated worked-arithmetic reader (`branches/worked.py`).

A consequence: some shapes section 3.4 names are not named on this tree because the integrated front end reads them its own
way (a rounding stated in words after a value is a checked restatement, a space-grouped numeral is ST-PARSE-001, a word
equation whose figures are space-grouped keeps that finding on its new line). Each is listed with its test in 20.8.

### 20.8 Tests (step 2)

Ported, adapted where the integrated code differs (each test is the feature line's, with the cases this tree decides
otherwise taken out and listed below): `tests/stem/test_reference_formulas.py`, `test_units_symbolic.py`,
`test_steps_operations.py`, `test_rounding_range_working.py`, `test_givens_symbols.py`, `test_repair_round1_variants.py`,
`test_repair_round2_stem.py`, `test_repair_round2_layouts.py`, `test_repair_round2_classes.py`, `test_repair_round3_stem.py`,
`test_repair_round4_stem.py`, `test_repair_round5_stem.py`, `test_accuracy1_stem.py`, `test_accuracy2_stem.py`,
`test_close1_stem.py`, `test_security_round1_relations.py`; and the corpus scorings `tests/contract/test_repair_round1_cases.py`,
`test_repair_round2_cases.py`, `test_accuracy_round1_cases.py`, `test_accuracy_round2_cases.py`, each with a `NOT_PORTED`
table of the cases left out of its scoring and the reason (the corpus files are unchanged). No test of the integrated tree is
changed.

Not ported, contradicted (the integrated behaviour wins):

* `tests/stem/test_units_symbolic.py::test_written_units_that_hold_only_as_written_are_labelled_stem_unit_error` and
  `::test_a_lost_prefix_fails_its_companion` (they pin that the check beside a written companion holds as written; 20.7).
* `tests/stem/test_givens_symbols.py::test_control_consistent_givens_are_clean` (the integrated givens name a Given the
  request states no quantity for, ST-UNDEC-003).
* `tests/stem/test_accuracy2_stem.py::test_a_general_branch_names_the_requests_quantities_combined_without_their_conversion`
  and the general-branch half of `::test_the_rounds_stem_readings_are_linear` (the request's unit companions on general
  branches, 20.7).

Not ported, duplicates or readings the integrated front end makes its own way (20.7):

* Whole files: `tests/stem/test_close2_boolean_dot.py` (Boolean AND dot), `test_e2e_b2_classes.py` (the feature line's
  false-error fixes of end-to-end B2), `test_lens_rerun_c.py` (the rerun lens review's STEM fixes), `test_review_stem_checks.py`
  (the external STEM review: temperatures, exactness intents, angles, part scope), `test_review_merge_interaction.py` (the
  STEM topic evidence of the channel). The feature's changes to integrated test files (`test_boolean_parse.py`,
  `test_checks_no_false_errors.py`, `test_e2e_run1_detection.py`, `tests/stem/data/corpus_items.py`,
  `tests/translate/test_stem_subjects.py`, `tests/channel/test_stem_channel.py`, `tests/integrity/test_stem_ledger_figures.py`)
  follow its own readings and are not ported; those files stay as the integrated tree has them.
* `tests/stem/test_repair_round1_variants.py`: `test_a_simplification_of_the_requests_expression_is_no_restatement`,
  `test_an_incomplete_or_wrong_solution_set_fails`, three layouts of `test_clean_control_a_complete_set_in_any_layout_holds`
  and one of `test_clean_control_no_full_set_is_claimed_...` (root sets), and nine variants of
  `test_each_variant_is_decided_as_its_working_reads` (the Boolean AND dot, space-grouped numerals, '4380 = 4400 (1 s.f.)').
* `tests/stem/test_repair_round2_stem.py`: `test_the_wrong_rearrangement_still_fails` (the feature's request bindings of a
  rearranged step, `checks._request_step_bindings`), `test_a_law_whose_head_has_a_subscript_digit_evaluated_past_the_data_is_an_extrapolation`
  and `test_the_same_law_evaluated_inside_the_data_is_clean` (the integrated reading of `CO₂ = 340 + 1.75(t − 1980)` fails its
  arithmetic, as before the port), `test_a_time_converted_inline_in_brackets_binds_the_law` (ST-UNDEC-002, an integrated
  reading), the worded case of `test_a_comparison_made_with_a_rounded_value_is_named` (a rounding stated in words is a
  checked restatement here), and its bounded per-line work tests (`test_the_fast_paths_give_the_readings_of_the_full_readers`,
  `test_the_markup_index_finds_exactly_the_overlapping_ranges`, `test_a_long_answer_of_list_items_is_read_in_bounded_time`:
  the feature's own linear-time readers).
* `tests/stem/test_repair_round2_layouts.py`: `test_a_wrong_value_after_its_computation_on_the_line_before_is_an_arithmetic_slip`,
  `test_a_spaced_product_of_quantity_letters_is_read_and_addresses_the_item`, `test_a_spaced_product_with_a_wrong_value_is_checked`,
  `test_the_spaced_product_is_one_span`, two layouts of `test_a_length_in_centimetres_used_as_metres_is_a_unit_error_whatever_the_layout`,
  three cases of `test_a_symbol_after_a_conditions_value_heads_its_own_equation` and one of
  `test_one_symbol_for_two_labelled_objects_is_a_symbol_conflict` (the spaced product, the head continued on the next line,
  a symbol after a condition's value).
* `tests/stem/test_repair_round2_classes.py`: `test_twos_complement_place_values_are_read_and_checked`,
  `test_a_boolean_evaluation_chain_is_checked_link_by_link`, `test_a_dated_trend_evaluated_past_its_years_is_an_extrapolation`
  (space-grouped numerals: ST-PARSE-001 on this tree).
* `tests/stem/test_repair_round4_stem.py`: `test_a_false_identity_is_checked_under_a_neutral_request` (named identities),
  `test_a_wrong_area_formula_over_a_radius_the_request_gives_is_named` and `test_an_inverted_period_over_a_mass_the_request_gives_is_named`
  (they pin ST-DIM-001 and ST-REF-001 from the dimension of substitutions; ST-REF-002 still names both laws here),
  `test_control_the_correct_formula_over_values_the_request_gives_raises_nothing` (the integrated ST-UNDEC-002 on the same
  working), the case 'minutes in P = E/t' and the controls 'seconds' and 'seconds for hours' (space-grouped numerals).
* `tests/stem/test_repair_round5_stem.py`: `test_a_count_the_request_states_in_a_sentence_is_the_value_of_n0`,
  `test_a_plus_minus_step_inside_a_chain_is_two_equations` (roots), `test_grams_substituted_against_a_specific_heat_per_kilogram_is_a_missing_conversion`
  (a space-grouped result), and the 'one-half glyph' and 'slash half' cases of `test_a_wrong_formula_written_as_adjacent_letters_is_a_wrong_formula`
  (adjacent letters read as a product).
* `tests/stem/test_close1_stem.py::test_control_a_restatement_of_the_same_sign_is_still_checked` (the result readings).
* Corpus cases (`NOT_PORTED` in each scoring file, with the reason): repair round 1 t07_unit_symbolic_density and repair
  round 2 xs07_kwh_written (a unit error written in units: caught by the integrated check and named by its kind, not as
  stem_unit_error, since no written companion is planned, 20.7); repair round 1 h05b and h06 (the restated-point excerpt
  check, 20.3), k04, k07, k09, y01, y04; repair round 2 ws05 and ws06 (a rounding stated in words), wc07, xc13 and yc03
  (integrated STEM readings of correct working), xk02, xk05, xk10, yk01, yk05, zk14, zk15, zk16, zk18 and ch_c_lake_recovered_then;
  accuracy round 1 acc1_phrasal_ok_brought_down, acc1_phrasal_ok_went_down, acc1_stance_ok_other_subject,
  acc1_precision_ok_about_300_g; accuracy round 2 acc2_units_bad_geography_km_m (general-branch unit companions),
  acc2_stance_ok_two_sentences, acc2_task_ok_unlisted_phrasal, acc2_task_ok_short_synonym, acc2_authority_ok_quoted_source.
  The integrated request-item, support, ledger, quotation, word-bound, precision,
  core-pack and English-structure readings flag those clean controls, where the feature line's own duplicates of those
  fixes did not. Every one fails on the step 1 tree too (t07 and xs07 as missed there), and no case the step 1 tree
  scores correctly is scored wrongly after step 2.

### 20.9 Measured on this tree (step 2)

Measured with the recorded arena rounds available to the round-dependent tests (`EPINOIC_ARENA_ROUNDS` set to a fresh copy
for each run): `tests/stem`, `tests/e2e` and the four ported corpus scorings 4157 passed, 28 deselected (by the suite's own
configuration); `tests/overseer` (with `test_stem_completion.py`, `test_stem_probe_bases.py` and the knowledge pack's drift,
export and loader tests), `tests/branches`, `tests/channel`, `tests/integrity` and `tests/translate/test_stem_subjects.py`
3940 passed. No failure. The full suite, the arena harness on every recorded round, the overseer's contained run and the
three argument-diagnosis corpora as a whole are not measured here; they are the next step of the final integration.


### 20.10 Verification findings (repair 1)

The verification of steps 1 and 2 found one failing test of the integrated tree and corpus cases the port named less well
than the feature line. Each is fixed at its cause in the port, or, when the integrated translator's own reading causes it,
recorded here with its case id.

**Fixed in the port.**

* `tests/integration/test_stem_budget.py::test_a_spent_budget_leaves_the_stem_checks_undecided_never_success` (an
  integrated test, unchanged). The ported `_inline_givens` planned a `giv` check for every value the working substitutes
  inline, so `v = d / t = 120 km / 2 h = 60 km/h` carried two Given checks beside its arithmetic, where the integrated
  translator plans the arithmetic check alone. A value that repeats one of the request's candidates exactly (the same
  value in the same unit, or the same SI value) now plans no check: such a check could only hold. A value that contradicts
  the request is still checked and named `stem_contradictory_givens` (repair round 5's ADV5-04 tests are unchanged).
* `ho_d_step_maa` (missed, now named `stem_invalid_step`). On a line of working the integrated reader keeps no prose value
  but a restated result (rule inline-restatement), so the operand of "Subtracting 4 from both sides then gives x = 8 − 4"
  was never read and no `op` check was planned. `_operand_at` now reads a plain numeral from the operation's own words when
  no prose value lies there.
* `h2_d_step_maa_divide_by_x` (caught without a name, now named). `_division_note` (ST-STEP-002 on a root line that divides
  by the unknown with no guard), listed as ported in 20.6, had not been carried: the feature called it from its own root
  reader, which is not ported. It is now called from the integrated `_roots_candidate`, for roots of the answer's own
  equation in mathematics, as on the feature line; a negated operation is no step, as for ST-STEP-001.
* `s03b_unit_no_conversion_units`, `s03d_unit_symbolic_bindings`, `ho_d_ue_phys_minutes`, `h2_d_unit_chem_cm3_inline`
  (caught without a name, now named `stem_unit_error`). The feature named these through its `written` companion, which is
  not ported (20.7). The integrated check, decided in SI alone because its units contradict the as-written reading or every
  value carries a unit, now carries the name itself: when its numbers hold as written (exact rational bookkeeping on the
  written numerals and, for a substitution, the one value each symbol is bound to), its failure names `stem_unit_error`
  (ST-UNIT-003) instead of `stem_arithmetic_slip`. The check, its readings, its verdict and its severity are the integrated
  ones, no check is added, and a slip that is wrong as written too stays an arithmetic slip.

Tests: `tests/stem/test_port_verification_fixes.py` (each fix with its clean controls).

**Not fixed: the integrated translator's own readings cause them.** In every case below the port's verdict equals the
integrated base's (5990526), and no case of the three corpora is worse on the port than on the base.

* Controls the feature leaves clean and the integrated readings flag (the feature line's own duplicates of these fixes are
  not ported, 20.3):
  * grounding of a table or figure excerpt refused by the integrated grounding (GROUNDING:FAILED, which the port's
    EVD-SRC-003 names): `c01_control_econ_table`, `c01b_control_econ_table_short_excerpts`, `e2e-B23-bm`,
    `ho_c_alldata_geo`, `ho_c_alldata_mai`, `ho_c_auth_ess`, `ho_c_supported_bm`, `h2_c_dated_figures_econ_landline`;
  * the synthesis ledger's readings (INT-LEDGER-020 an excerpt that differs under the same locator, INT-LEDGER-032 a name
    the sources do not give): `c02_control_history_quotes`, `c03_control_psych_study` (also PS-SRC-001),
    `c04_control_english_quote`, `ho_c_attribution_hist`, `ho_c_controlled_bio`, `ho_c_excerpt_lit`,
    `ho_c_quote_restated_ll`, `ho_c_rubric_sp`, `ho_c_stated_links_geo`, `ho_c_supported_ess`, `h2_c_fullrange_ess_reef`;
  * the request-item heuristic (INT-REQ-004, end-to-end item B18): `c03_true_dichotomy`, `c04_quoted_transcription`
    (also ES-STR-001), `e2e-B18-cs`, `e2e-B18-ge`, `e2e-B18-lit`, `e2e-B18-mai`, `e2e-B18-sp`, `i02c_control_rct_cause`
    (also CORE-QNT-001), `h2_c_bio_chi_squared_decision`, `h2_c_mai_p_value_decision`, `h2_c_mt_bio_starch_test`,
    `h2_c_quote_hist_right_source`, `h2_c_samesense_bio_fitness`, `h2_c_fullrange_geog_tourism` (also CORE-QNT-001 and
    INT-LEDGER-020), `h2_c_cs_de_morgan` and `h2_c_phys_heater_chain` (both also ST-PARSE-001);
  * word and paragraph bounds (INT-REQ-005 and the request constraint, end-to-end items B4, B13 and B19): `e2e-B4-bm`,
    `e2e-B4-ec`, `e2e-B4-en`, `e2e-B4-ps`, `e2e-B13-ec` (also an INT-SUBJ-001 of pair_direction), `e2e-B13-ll`,
    `e2e-B13-ps` (also a COUNTEREXAMPLE display), `e2e-B19-ll`;
  * quotation roles and credit (INT-REQ-003, ES-SRC-001, CORE-SRC-003, end-to-end items B5, B6 and B13): `e2e-B13-sp`,
    `e2e-B5-sp`, `e2e-B6-en`, `ho_c_mention_ll` (also INT-LEDGER-020);
  * claims whose verification gave no verdict (INT-REQ-006): `e2e-B21-ge`, `e2e-B22-ph`;
  * UNLINKED_CONJUNCT (20.3: a refuted conjunct keeps its COUNTEREXAMPLE): `e2e-B8-en`, `e2e-B8-ps`;
  * the core pack's figure readings (CORE-QNT-001): `ho_c_arith_econ`, `ho_c_derived_bm`, `ho_c_paraphrase_geo`,
    `ho_c_stated_rule_bm`, `h2_c_consistent_hist_turnout`, `h2_c_derived_mean_econ_inflation`,
    `h2_c_geog_runoff_interpolation`, `h2_c_sourced_geog_rainfall` (also INT-LEDGER-020);
  * the integrated STEM readings of correct working (20.7, 20.8): `c06_consistent_givens_stem` (ST-UNDEC-003, a Given
    the request states no quantity for), `ho_c_arith_cs` and `h2_c_cs_twos_complement_worked` (a binary literal set
    equal to its place values), `ho_c_iff_cs` and `ho_c_trichotomy_maa` (a condition inside a stated rule, 'if Δ < 0',
    read as a stated comparison: named conditions), `ho_c_interp_ess` (a bare sum set equal to a value in ppm, read in
    SI), `h2_c_maa_radical_checked` (a root the answer checks and rejects: root sets), `h2_c_bio_magnification_convert`
    (a space-grouped numeral, ST-PARSE-001).
* Defects named in the report delivery and caught without a name in the text delivery, because the integrated text
  parsers read the answer their own way (the feature line's parser fixes are not ported, 20.3): `ho_d_bare_hist` (its one
  sentence is roled a note, INT-REQ-012), `ho_d_unch_rubric_sp` (the judgement is left with no supporting claim, so it is
  not translated), `h2_d_inv_bm_turnover` (the conclusion is roled analysis, not eligible for a solver question).
* `h2_d_arith_phys_heater_chain` (missed): the slip is in '21 990 J', a space-grouped numeral the integrated front end
  names ST-PARSE-001 and does not check (20.7).
* `ho_d_ue_bio_magnification` (missed, as on the base): 'A = I/M = 0.030 μm' with I = 12 mm and M = 400. The integrated
  substitution check (Form S, satisfiability) holds for every stated value, because the half-width of the stated value is
  taken in its written unit and compared in SI ('0.5' for '99 μm' against values in metres). This is a defect of the
  integrated check, reported here and not changed by the port (the integrated behaviour stays). The feature's `written`
  companion named it on the feature line; on this tree a companion inherits the same band, so porting it would not name
  this case and would only repeat the main check's verdict elsewhere.

**Measured after repair 1** (`EPINOIC_ARENA_ROUNDS` set to a fresh copy of the recorded rounds): the full suite 12544
passed, 45 deselected (by the suite's own configuration), 3 xfailed, no failure. Corpora (the feature line's figures in
brackets): development 44/44 defects named [44/44], 27/57 controls clean [57/57]; hold-out 61 named, 4 caught without a
name, 1 missed [64 named, 2 caught without a name], 48/68 controls clean [68/68]; second hold-out 68 named, 1 caught
without a name, 1 missed [70/70 named], 38/66 controls clean [55/66]. Every remaining difference is listed above, and no
case is worse than on the integrated base.
