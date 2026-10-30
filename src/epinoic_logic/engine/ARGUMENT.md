# The argument stage of the engine (rules `argdiag-2`)

*On this tree (the port onto the integrated translator, docs/ARGUMENT_DIAGNOSTICS.md, section 20):* E112 follows the
integrated authority rule (only the ungrounded kinds, an unverified `arithmetic_fact` and a refuted premise count as the
writer's own), not the feature line's `not has_authority`, and the restatement normal form beyond the integrated
`runner.circular_premises` is not ported. Where this document says otherwise, section 20 holds.

`engine/argument.py` names what is wrong with how an encoded argument reasons, as far as the bound problem, its result and
derived engine runs can tell. `engine/argument_cues.py` holds the closed cue tables it reads glosses with. The model of a
diagnostic (`NamedDiagnostic`, the code table, caps and suppression) is `epinoic_logic/named.py`; the tokenizer is
`epinoic_logic/lexis.py`.

**Scope.** Every diagnostic proves a property of the encoding and of this code only. It never shows that a premise is
true, that a translation is faithful or that an interpretation is right. An info record is a record, never an accusation.
A message or a missing link shows model text (a meaning, a label) on one line with its forgery words written "[...]"
(`named.model_text`); evidence spans keep it as written.
A diagnostic never changes the engine status, the dependency lists or the engine diagnostics; it can only make a result
less releasable (release reads the effective severity, so a capped warning still blocks).

## Where the stage runs

`runner.verify(..., diagnose=True, severity_cap=None)` calls `argument.diagnose(problem, proc, compiled, config,
limits, diagnostics)` after the decision and before the result is bound and signed. Its two outputs become
`VerificationResult.named_diagnostics` (engine layer only) and `argument_rules`:

- `argdiag-2` when the diagnosis finished, even when it found nothing;
- `argdiag-2/incomplete:<reason>` when a derived run was undecided, invalid or out of budget (`derived_undecided`,
  `derived_invalid`, `derived_runs_exhausted`, `budget_exhausted`). The rule that needed the run fires nothing.

The runner merges, suppresses dominated generic warnings, orders, bounds (32 per claim) and applies the caller's
`severity_cap` before signing, so the signed copy, the outcome, the receipt and every reader see one severity.
`diagnose` and `severity_cap` are Python keywords only; the internal probes, cross checks, branch formal checks and
constraint checks pass `diagnose=False`.

## Derived runs

A derived problem is a deterministic function of the bound problem, the rule version and the rule's tag. It is built as
data only: a subset of the bound problem's premises (copied), plus at most one new step made by copying validated
expression dicts into the wrappers `implies`, `not`, `and` and `iff`, and a conclusion of the same kind. Every derived
problem passes `Problem.model_validate`, and every one with a new step or a new conclusion also `validate_problem` under
the enforced limits (so a nonlinear problem is re-decided under the nonlinear policy); one made only of the bound
problem's premises and its conclusion (R0's runs) is a part of a problem the validator already passed and is not
validated again. Each is recorded by digest in `derived_problem_digests`. Nothing is evaluated.

It is then decided on the bound problem's own compiled terms, in one Z3 context for the whole diagnosis: the premises it
keeps reuse their compiled terms (and their tracking literals and implications, built once), the bound conclusion its
compiled term, and a new step or conclusion is compiled by `compiler.compile_expr`. The runs that report no model share
one incremental solver (the run's timeout, the configuration's rlimit and seed): every implication is asserted in it once,
and each run checks first that its premises are consistent and then whether they entail its conclusion, under the
tracking literals of its own premises as assumptions, so a premise it does not keep is left out exactly as if it were
absent. A run that reports a model (R0's D0, whose counterexample values a message shows) has a fresh solver of its own.
An identical derived problem (the same premises, conclusion and steps) is decided once per diagnosis: R0's last
minimisation trial is often the established set D0 already decided. A test compares every derived run of two problems
with `engine.verify` on the same derived problem and checks that each passes the validator. Over the 407 development
proposals the stage then costs about 7 ms of CPU per claim at the median (15.0 ms with the diagnosis against 7.9 ms
without), 10 ms on average and at most 135 ms in all of a claim's engine run (section 6 of `docs/ARGUMENT_DIAGNOSTICS.md`).

**Bounds** (`MAX_DERIVED_RUNS`, `run_budget_ms`): at most 24 derived runs per result, each under
`min(config.timeout_ms, 1000)` ms, and at most `min(4 × config.timeout_ms, 8000)` ms in all. R0 minimises at most 16
premises (`MAX_MINIMISED`); bridges are at most 8, converse and inverse runs at most 4, equivalence and tautology runs at
most 4. A 128-premise problem with every premise unverified finishes well inside the budget (about 0.2 s).

## R0: the re-check of an ENTAILED point

R0 runs only on an entailment query whose status is ENTAILED and that carries no no-verdict code (E108, E110, E111,
E112).

1. `core` is the result's unsat core (the procedures always compute it), else every premise.
2. `V` is every premise a check in this process established (`authority.has_authority`), whatever its kind. A label never
   decides authority.
3. `W` is the core's premises not in `V`, in premise order. When `W` is empty nothing is named.
4. D0 decides the conclusion from `V` alone. ENTAILED: nothing is named (the core was not minimal). Undecided: the
   diagnosis is incomplete and nothing fires.
5. Deletion minimisation over the first 16 of `W`: a premise whose removal keeps the conclusion ENTAILED is dropped. Any
   premise beyond 16 stays, and the record says "partly minimised (the first 16 were tested)".
6. What is left, `W*`, splits by expression: links (`implies`, `iff`, `or`, or a numeric relation that combines
   symbols) and facts (atoms, negations, assignments of literals). The pattern rules read every link; the records name
   a figure relation (a link whose every link-shaped part is a numeric relation, with no implication, biconditional or
   either/or: "x > y", "rate = 2.0 + 0.40 × t") with the facts, since it states no step from a reason to the point
   (`figure_relation`; repair round 5, INV-LINK-1).

| Code | Sev | Fires when |
| --- | --- | --- |
| ARG-LINK-001 | info | `W*` holds links. One diagnostic per link (8 at most, then one for the rest), each with its `missing_link`: "if <antecedent> then <consequent>", "<a> exactly when <b>" or "either <a> or <b>, and nothing else", rendered from symbol meanings, with D0's counterexample values in the message. A conjunction whose conjuncts include a link-shaped step is read part by part (`_link_parts`), so a step hidden in "and" is a link too. A causal link (a causal cue in its consequent) is not recorded when the problem states a controlled comparison (a control cue of `CONTROL` that is not negated and no comparison with another time), and a link the translation marks as a rule the writer states from subject knowledge is ARG-LINK-002 instead (repair round 2). It is a dependency record that does not discriminate: on the development corpus it is on 41 of the 57 controls (`docs/ARGUMENT_DIAGNOSTICS.md`, section 6) |
| ARG-LINK-002 | info | a link of `W*` of kind `general_knowledge` that the translation marked as a stated rule (the grounding note "rule", `translate_v3` rule 2): no missing link, but a knowledge claim no check established ("copper conducts electricity" for "the rod is made of copper, so it conducts") |
| ARG-FACT-001 | info | `W*` holds facts or figure relations (a relation of a writer's kind, or of a kind that claims a source, that no check established; a knowledge rule marked as stated stays ARG-LINK-002); they are listed for the evidence rules, and a figure relation is never given a missing link |
| ARG-CIRC-002 | warning | a premise of `W*` with the conclusion's symbols and literal values, computing nothing, is equivalent to it (`premise ⟺ conclusion` valid, a derived run) without being the same expression: an equivalence beyond the engine's normal form, such as De Morgan's "not (not a or not b)" for "a and b". The writer's own premise that cites no source may compute ("2·dt = 82" for dt = 41) unless it is a calculation over stated figures. A restatement in the normal form ("5 < x" for "x > 5") is already E112, and since repair round 2 so is an equivalence the engine's own restatement check decides (below), so R0 never runs on either; ARG-CIRC-002 names what that check left undecided (its four premises or its time ran out) |
| ARG-CIRC-003 | warning | a writer's link `A → C` derives the point `C` from an asserted fact atom `A` that no check established and that restates it (`_restates`): the same concepts, read through `lexis.root` (forms of one word share a root), the closed synonym groups and definitions (`SYNONYM_GROUPS`, `DEFINITIONS`: "achieved what it set out to achieve" reads as "success") and prefixed negations ("unreliable" is "not" plus "reliable"), the same polarity, and only frame words besides (f06b: "cannot be relied upon" for "is unreliable"). The point may drop what anaphora drops from the fact (a name, a year, a pre-modifier: `_qualifier_roots`) when the two share at least two concepts ("the 1919 Treaty of Versailles imposed harsh terms on Germany", so "the treaty imposed harsh terms on Germany"; repair round 2) |
| ARG-AC-001 b | warning (info when the rule is labelled `general_knowledge` with no grounding note marking it as a rule the writer states) | a writer's link `Q → P` is the converse of a rule `P → Q` the problem states as other than a writer's step (f03b) |
| ARG-AC-001 c | warning | a writer's link `Q → P` is the converse of a chain of stated rules: the rules entail `P → Q` and do not entail the link (two derived runs, `converse_chain`) |
| ARG-DA-001 b, c | warning | a writer's link `¬P → ¬Q` is the inverse of such a rule `P → Q`, or of a chain of stated rules (f04b) |
| ARG-FD-001 | warning (info for a disjunction labelled `general_knowledge` with no rule note) | a writer's disjunction in `W*` is no tautology (a derived run finds a counterexample) and no two options are complementary, by structure (`p`/`¬p`; `x < a`/`x ≥ a`) or by meaning (meanings that differ only by a pair of `COMPLEMENTARY_PAIRS`, "even"/"odd", "pass"/"fail", "0"/"1" beside "bit", read through word roots, so "passed"/"failed" and "converges"/"diverges" too) (f10). A source disjunction never fires (c03-dich) |
| ARG-HG-001 i | warning | a writer's link whose consequent meaning carries an open universal cue, absent from every antecedent meaning, and whose antecedent atoms are instance facts (f09b; repair round 5: cases named by a list or a label, "for the inputs 2, 5 and 9", "for input 7", `_ENUMERATED_CASES_RE`, `_LABELLED_CASE_RE`) or count a sample: a sample cue ("some", "several", "a few", "a sample of": `SAMPLE`) or a number before a plural noun that is no measurement ("two towns", not "3 kg": `MEASURE_WORDS`). "all three", "each of the four" are closed enumerations |
| ARG-HG-001 iv | warning | a writer's link from a counted sample to a claim about "most" or "the majority of" a population (`MAJORITY`), unless the consequent keeps the sample's own words ("most of the students in our class"; repair round 2) |
| ARG-CL-001 | warning | a writer's link whose consequent meaning carries a causal cue, whose antecedent holds a sequence in time (two numeric symbols whose meanings differ only by a year or month, or a sequence cue in the link's label) or a correlation (repair round 2: a cue of `CORRELATION` in the antecedent's meanings or in a fact premise that asserts them, or two comparatives of `COMPARATIVES` after a population noun of `POPULATIONS` and its relative or "with" clause: "towns with more ice cream sales have more drownings"), and no premise label, symbol meaning or conclusion label carries a control cue (i02; i02c is clean). Repair round 5: a causative verb with a result comparative in the consequent ("the new goggles make swimmers faster": `_CAUSATIVE_VERBS`, `_RESULT_COMPARATIVES`) is a causal cue, and a comparison that names no cause reads none. A control cue with a negating word within the three tokens before it ("no control group": `CONTROL_NEGATORS`), or "compared with" followed by a time word within four tokens ("compared with the months before": `TIME_WORDS`), is no control |
| ARG-EQ-003 | warning | (a) a writer's link uses a symbol whose meaning qualifies a head noun by sense ("scientific theory", "theory in the everyday sense", "theory (well-substantiated explanation)"), and the link's label is a bare generic definition of that noun ("a theory is an unproven guess") (i03a); (b) by the closed table `EQUIVOCAL_TERMS` (theory, fittest, work, power, energy, significant, normal, law, depression, demand, adaptation, organic): among the link's label and its symbols' meanings, one text selects the word's technical sense and one its everyday sense, each by a cue no negation precedes; a link whose label or consequent is negated contrasts the senses and is not read; (c) one symbol read in two senses across premises (`symbol_senses`, repair round 2): the symbol's meaning and the labels of the premises that use it select the technical and the everyday sense of one term of the table ("pushing against a wall for an hour is hard work", then "in physics, whenever work is done on an object energy is transferred to it"). The table now also holds "light" (mass or radiation) and more cues of fitness and law |

"A writer's step" is a premise of kind `specialist_inference`, `assumption` or none (`WRITER_STEP_KINDS`). A link of
another kind that no check established is still in `W*` and still gets ARG-LINK-001 ("the link l, labelled
task_setting, which no check located in a source"), but the rules that accuse a step of a fallacy read only the writer's
own steps: a rule stated from subject knowledge, or one labelled with a source, is not the writer's inference.

## The COUNTEREXAMPLE rules

They run on an entailment COUNTEREXAMPLE with at least one premise and no no-verdict code, in precedence order.

| Code | Sev | Fires when |
| --- | --- | --- |
| ARG-REFUTE-001 | warning | the established premises entail the negated point (a derived run): the stated evidence refutes it (e06b) |
| ARG-AC-001 a | warning | a rule `P → Q`, a stated fact `Q` and the point `P`, and adding the converse makes it ENTAILED (f03) |
| ARG-DA-001 a | warning | a rule `P → Q`, a stated fact `¬P` and the point `¬Q`, and adding the inverse makes it ENTAILED (f04) |
| ARG-HG-001 ii | warning | no premise mentions the point, the point's meaning carries an open universal, and every premise is an instance fact (f09) |
| ARG-NS-001 | warning | no premise mentions any symbol of the point (f01) |
| ARG-PART-001 | info | some conjuncts share no symbol with any premise, and the linked conjuncts follow (a derived run): the counterexample falsifies only the unlinked judgement (the seven B8 shapes) |
| ARG-NS-002 | warning | one bridge `E → A` from a stated fact `E` to the antecedent `A` of a rule whose consequent shares the point's symbols makes it ENTAILED; the bridge is the `missing_link` (f02) |
| ARG-EQ-002 | warning | that bridge joins two symbols whose meanings share a head noun and one of them qualifies it by sense; the missing link is "the two senses of '<noun>' are the same" (i03b) |
| ARG-INV-001 | warning | the point does not follow from reasons that mention it and no more specific shape is named |

A counterexample over figures the encoding leaves open (W110, W111) gets only ARG-REFUTE-001: no argument shape is read
into it. On a purely numeric point the counterexample is the arithmetic verdict, so only ARG-REFUTE-001 and ARG-PART-001
apply. ARG-INV-001 fires only when every derived run of the diagnosis was decided: an undecided run could have named a
more specific shape, and a generic accusation must not stand in for it.

## From the engine's own status

| Code | Sev | Fires when |
| --- | --- | --- |
| ARG-CONTRA-001 | error | INCONSISTENT_PREMISES; the unsat core is named. The receipt already carries INT-REQ-007, so no INT-ARG-001 is added |
| ARG-VAC-001 | warning | E108 on an ENTAILED result with premises: the point holds whatever the premises say, so none of them is used (f08) |
| ARG-VAC-001 | info | E108 on a result over no premise at all: a COUNTEREXAMPLE only says the point is no tautology, and an ENTAILED proof only that the point is a logical truth (an identity the task asks to show, "Show that A·B + A·NOT B = A", holds by its form). Nothing the claim rests on was encoded. A record, never an accusation |
| ARG-CIRC-001 | warning | E112 on the result: the restating premises of the core are named (f06 verified directly; f07, whose joined quotation stays unverified, as its grounded proposal verified directly; the translator refuses both translations as circular and names the claim form, `translate/ARGUMENT_DIAGNOSTICS.md`) |
| ARG-CIRC-001 | info | E112 where every restating premise is a fact stated from subject knowledge (`general_knowledge`, `KNOWLEDGE_KIND`) and neither their labels nor the conclusion's offer a reason (no reason connective): the encoding transcribes a bare factual sentence, which is no circle in the argument. E112 still withholds the verdict |

E112 itself follows the authority rule of policy 2026.10-v5 (`authority.assumed_grounding` is `not has_authority`): a
restating premise is circular when no check in this process established it, whatever kind it claims, so a
`task_setting`, `rubric_rule` or text label with no check behind it is supported by nothing but the claim itself.
Restating a premise that a check verified against the task record or a supplied text checks the claim against that
source: no E112 and no circularity code. E112 reads the restatement in the engine's normal form
(`runner.circular_premises`: ordered operands of symmetric operators, flipped and negated comparisons, double negation,
`x ≤ a and x ≥ a` for `x = a`, literal values, and arithmetic: identity elements dropped, a closed constant term folded
when at most one literal outside 0 and 1 takes part, `a − b = 0` read as `a = b`), so "5 < x" for "x > 5", and
"dt + 0 = 41", "40 + 1 = dt" or "dt − 41 = 0" for dt = 41, are E112 like the same text. "dt + 1 = 42" (two literals
to fold) is not read as a restatement by the normal form. Beyond it, the runner asks Z3 itself (repair round 2,
`runner.equivalent_premises`): a relied-on premise of the writer's own, with the conclusion's symbols, that is the
restatement shape ARG-CIRC-002 reads (it computes nothing and uses the conclusion's literal values, or it cites no
source and is no computation of the conclusion's figure) and that is equivalent to the conclusion under every
assignment ("2·dt = 82", "dt + 1 = 42", "40 < dt < 42" over Int for dt = 41; a De Morgan form) makes E112 too. At most
four premises are decided, within the time the decision left (stage `restatement` of the timings); an undecided check
finds nothing. Working that derives the point from stated figures ("rate = 2.0 + 0.40 × 60" for rate = 26) is never a
restatement.

## Precedence, suppression and caps

Each code's precedence is its row in `named.NAMED_CODES`. A generic warning (ARG-NS-001, ARG-NS-002, ARG-INV-001) gives
way to a more specific warning of the same family on the same claims that covers its assertions: ARG-HG-001 suppresses
ARG-NS-001 on f09, ARG-EQ-002 suppresses ARG-NS-002 on i03b. Info records are always kept.

The translator passes `severity_cap=("info", "ambiguous_translation")` for an AMBIGUOUS_TRANSLATION. Every ARG code is
capped then, except the equivocation codes (ARG-EQ-001, 002, 003), whose defect is the ambiguity itself. The cap is
recorded in `capped_from` and `cap_reason`, inside the signature.

## How the cue tables read text

Meanings and labels are read only through `lexis` (tokens, stems, `find_cues`, negation), by bounded linear scans. The
tables are the design's closed lists:

- **open universal**: all, every, always, never, none, no one, nobody, everyone, everybody, everything, any, each, in
  general, universally, without exception, in every case, in all cases; closed by a number or number word within three
  tokens; "any" after a negation is not open;
- **instance**: in this case, in that case, in one case, this, one, a, an, the study, this study, the experiment, the
  participants, a participant, in the study, in this study, the sample, in the sample, the trial; a possessive or a year
  also marks an instance;
- **causal**: caused, causes, cause of, causing, led to, leads to, lead to, resulted in, results in, result of, due to,
  because of, responsible for, produced, produces, brought about, brings about, (the) effect of, made or makes ... rise or
  fall, and the plain verb "cause" (repair round 2);
- **correlation** (repair round 2): correlated, correlates, correlate, correlation(s), associated with, association
  between or with, linked with, go or goes or went together, rise or rose together, move or moved together, tend or tends
  or tended to; and two comparatives (`COMPARATIVES`: more, less, fewer, higher, lower, greater, ...; not "earlier" or
  "later") after a population noun (`POPULATIONS`: countries, towns, students, people, patients, firms, ...) and the
  relative or "with" clause that opens on it. A property of a physical class ("gases with more energy") names no
  population, and "the more X, the more Y" is not read (a mechanism is often written so);
- **majority** (repair round 2): most, the majority of, a majority of, and their kin (`MAJORITY`);
- **sequence**: after, then, following, subsequently, afterwards, before, later, and "since" before a year. "then" after
  an "if" is the consequent of a conditional, not a later time;
- **control**: random, randomly, randomised, randomized, randomisation, randomization, control group(s), control
  condition, control sample, a control, the control, controlled trial(s), controlled experiment(s), controlled study,
  controlled for, controlling for, controls for, compared with, compared to, comparison group, matched, placebo, double
  blind, blind trial (a bare "control", "controlled", "controls" or "trial" is no control: "the government controlled
  prices"); negated within three tokens, or a comparison with another time, it controls nothing;
- **sample**: some, several, a few, few, a handful, many, most, a number of, a group of, a sample of, a small sample, a
  minority of, a majority of, a couple of, a pair of, certain; a number before a plural noun counts cases unless the noun
  is a measure word;
- **paraphrase**: the root reader `lexis.root` (irregular forms and derivational suffixes, `lexis.IRREGULAR_FORMS`,
  `lexis.DERIVATIONAL_SUFFIXES`), `NEGATING_WORDS`, the negating prefixes with their exceptions (`NOT_PREFIXED`),
  `SYNONYM_GROUPS` and `DEFINITIONS`;
- **complementary options**: `COMPLEMENTARY_PAIRS`, and `COMPLEMENTARY_CONTEXT` for a pair that needs a context word;
- **equivocal terms**: `EQUIVOCAL_TERMS`, each with its forms and the cues of its technical and everyday senses;
- **sense qualifiers**: scientific, everyday, ordinary, colloquial, legal, technical, mathematical, statistical, literal,
  figurative, biological, economic; and "in the ... sense". A parenthetical marks a sense only when it glosses one: it
  holds a sense qualifier or the word "sense", or it is a gloss in common words with no number and no capitalised word.
  "(the 1930 Reichstag election)" names a referent and marks no sense;
- **a bare generic definition** opens with no determiner or with a, an, every, all, any or each, then the noun and a
  definition verb (is, are, means, denotes, refers, equals). "The surge is ..." speaks of one surge and defines nothing;
- **reason connectives** (`REASON_CONNECTIVES`, shared with the claim and report rules of
  `translate/diag_argument.py`): because, since, so, therefore, thus, hence, given that, due to the fact that, which
  shows / means / suggests / proves, this shows / means / suggests, as shown by, as seen in, as demonstrated by, as
  evidenced by, "as <one to three words> shows / suggests / show", consequently, it follows that. "because of" is a
  causal cue, not a reason connective.

The tables are English. A gloss in another language matches fewer cues: a miss, never a false alarm. Changing a table
changes `build_id`.

## Where these readings tighten the design's wording

- ARG-INV-001 and the bridge rules are read for propositional points only, and ARG-INV-001 only on a complete diagnosis.
- A parenthetical counts as a sense marker only when it glosses a sense, and "the" opens no generic definition. These
  two refinements remove a false ARG-EQ-003 on a correct history claim, in which "year of the electoral surge (the 1930
  Reichstag election)" met the label "the surge is separated from the peak".
- "then" after "if" is no sequence cue.
- ARG-VAC-001 accuses only a proof that holds whatever the premises say. A counterexample over no premise is recorded at
  info: it was named as a vacuous argument on an answer whose point ("The turning point was 1930.") had its reasons in
  other sentences. A proof over no premise at all is recorded at info too (repair round 4): it was named as a vacuous
  argument on a requested Boolean identity proof ("Show that A·B + A·NOT B = A"), whose point holds by its form; with no
  premise encoded, no reason of the claim can be shown unused. E108 still withholds the verdict.
- ARG-CIRC-001 is a record at info when the restatement only transcribes a bare fact the writer states from subject
  knowledge and offers no reason for; it was named as circular on bare factual sentences of correct history answers.
- The instance and sense-qualifier tables are the design's lists ("that", "common", "formal", "informal" and "popular"
  are not cues).

Each refinement only removes a way to fire, and each has a control in `tests/engine/test_argument_diagnostics.py`.

## Tests

`tests/engine/test_argument_repair_round2.py` holds the repair round 2 readings, each with a control: paraphrase with a
qualifier dropped, complements by root, one symbol in two senses, "most" from a sample, a causal link warranted by a stated
control, a rule stated from subject knowledge (ARG-LINK-002), and causes read into correlations.
`tests/engine/test_repair_round2_restatement.py` holds E112 beyond the normal form (2·dt = 82, De Morgan, an interval
over Int) with its controls (working over stated figures, a sourced equation), and
`tests/engine/test_repair_round2_coefficients.py` the coefficient bound E307 (below).

`tests/engine/test_argument_rerun_repairs.py` holds the repair round 1 readings, each with a control: counted samples and
measurements, a link hidden in a conjunction, the equivocal-term table and its negated or one-sense controls, paraphrase
by roots and its other-content controls, arithmetic restatements and working, chains of stated rules and the link a chain
gives, unmarked knowledge recorded at info, complementary options, and negated and time-word control cues against a stated
control. `tests/data/repair_round1_cases.json` holds the review's probe cases (`tests/contract/test_repair_round1_cases.py`).

`tests/engine/test_argument_diagnostics.py` holds a positive case for every code on its development case (f01 NS-001,
f01b LINK-001 at info with the missing link, f02 NS-002 with the bridge, f03 and f03b AC-001, f04 and f04b DA-001, f05
CONTRA-001, f06 and f07 CIRC-001, f06b CIRC-003, f08 VAC-001, f09 and f09b HG-001 with NS-001 suppressed, f10 FD-001, i02
CL-001, i03a EQ-003, i03b EQ-002, e06b REFUTE-001, "either P or Q, so P" INV-001, a De Morgan restatement CIRC-002, and a restatement in the
engine's normal form E112 with CIRC-001 and no CIRC-002)
and the clean controls (c01-mp, c02-mt, c03-dich, c04-quote, c05-chem, c02-hist, c03-psych, c04-eng, i00 and i02c in
every mode; a biconditional stated both ways; "all three"; a same-head-noun bridge with no sense marker, which is NS-002
and not EQ-002; a qualified symbol used consistently; a referent parenthetical with a "the X is" label; "if ... then";
a counterexample over no premise, VAC-001 at info; a bare fact restated from subject knowledge, CIRC-001 at info, with
the same restatement offered as its own reason a warning; a restated task or text premise: E112 and CIRC-001 with only
its label behind it, neither once a check verified it).
It also pins the bounds (128 premises, a budget of zero), determinism, a derived timeout that fires nothing, the
equivalence of derived runs with `engine.verify`, the cap inside the signature and the cue tables.
No argument code warns on a control, in the engine's signed copy or on the outcome. The outcome of a control may also
carry the evidence family's records (`translate/diag_evidence.py`) about premises no check established; outside a
source-bound task each is shown at info, capped from warning (`not_source_bound`), and the test asserts that, and that
such a claim is not released.

## The coefficient bound (E307, repair round 2)

Exact linear arithmetic can grow numbers past any solver timeout, because Z3 checks its timeout only between steps and
one step on numbers of tens of thousands of digits runs for seconds: a chain of 40 linear equations, each multiplying the
previous term by a product of 25 thirty-digit literals, held one solver call for 5 s under a 2000 ms timeout. Before
compiling, `runner.verify` bounds the digits of every number the problem's exact linear arithmetic can reach, from the IR
alone (`policies.coefficient_digits`: each comparison is a row, each numeric expression a digit triple read by an
iterative walk, nothing evaluated, and by Hadamard's bound no reachable number has more digits than the largest rows
together, as many as the problem has unknowns plus one). A problem above `MAX_COEFFICIENT_DIGITS` (16,000 digits; 20
links of the chain, about 15,200 digits, decide in 0.4 s) is INVALID_FORMALIZATION with E307 (COEFFICIENTS_TOO_LARGE)
before it compiles, about 0.05 s for the 40-link chain, and is never shown as a verdict. The bound is in the policy
manifest (`max_coefficient_digits`), and the integrity layer's cross checks treat E307 as a limit like E300 to E306. A
problem of ordinary figures stays far below it (128 rows of 40-digit literals are about 5,300 digits).
