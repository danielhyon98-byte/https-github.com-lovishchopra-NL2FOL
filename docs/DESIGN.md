# Design

This is the design overview of the logic translator and Z3 verification engine as implemented. It states the principles
every component follows, how a specialist's answer travels through the system, where trust comes from, and how the named
diagnostics of the argument diagnosis fit in. Each section points to the document that holds the detail. Nothing here is
deployed, and no live model provider is called by the tests or by the measurements reported in these documents.

Versions: IR 1.0, engine 0.5.0, policy 2026.10-v5, translator 0.5.1, argument-diagnosis rules `argdiag-2`, integration
contract 0.4 (`src/epinoic_logic/version.py`, `docs/integration-contract.md`).

## 1. Principles

- **Models propose; code enforces; the engine decides the encoding.** A model proposes a typed logic problem for a claim.
  The proposal is data: it is parsed strictly, validated against a closed schema and compiled only through allowlisted
  nodes. Nothing in a model's or a student's text is evaluated or executed.
- **Consistency before entailment.** The engine checks that the premises are consistent before it asks whether they
  entail the point, so a contradiction never proves anything.
- **No non-success is shown as success.** The status set is closed; only six statuses are definitive and none means
  "the claim is true". A vacuous, circular or under-determined encoding (E108, E110, E111, E112) is never displayed as a
  verdict, and a problem whose exact arithmetic could outgrow the solver's time bound is refused before it compiles
  (E307, `engine/policies.py`), never left to time out mid-step.
- **A result proves a property of the encoding only.** Every result carries the scope statement (section 8).
- **Authority comes from checks, never from labels.** A grounding kind (`quotation`, `task_setting`, `rubric_rule`, ...)
  is the proposer's claim. Only a deterministic check in this process sets `verified`, so only it establishes a premise
  or confers task or source authority, for the dependency lists and for circularity alike
  (`engine/authority.py`). A payload that certifies itself is refused or discarded (E505).
- **Agent self-reports are advisory.** The Overseer, the release check and the response gate trust only signed engine
  results that bind to the problem, are current for this build and verify under the key.
- **Diagnostics only add.** A named diagnostic never changes a status, a dependency list or a check, and can only make a
  result less releasable (section 5).

## 2. Components

| Component | Package | Role | Detail |
| --- | --- | --- | --- |
| IR | `ir/` | the typed problem (Bool, Int, Real; 24 allowlisted operators; exact numerals as text) and canonical digests | `src/epinoic_logic/ir/README.md` |
| Engine | `engine/` | validate, compile (one Z3 call per node, a fresh context), decide (consistency, entailment with tracked unsat cores, exact models), diagnose the argument, bind to digests of the problem, configuration, versions and build identity, and sign | `src/epinoic_logic/engine/README.md`, `engine/ARGUMENT.md` |
| Translator | `translate/` | eligibility, subject profiles, the provider proposal, strict parsing, grounding checks, the pipeline's checks (coverage, circularity, stated precision, bounded retries, encoding flags), the advisory fidelity review, the claim outcome and its release assessment, and the claim and report diagnostics | `src/epinoic_logic/translate/README.md`, `translate/ARGUMENT_DIAGNOSTICS.md` |
| STEM front end | `stem/` | reads answers that mix equations and prose without evaluating them, plans checks the engine decides under a tolerance rule, and holds the closed STEM reference | `docs/STEM_DESIGN.md`, `src/epinoic_logic/stem/README.md` |
| Adapters | `adapters/` | turn a specialist's output into an immutable report with stable claim ids and roles; structural checks; quotation roles | `src/epinoic_logic/adapters/README.md` |
| Branches | `branches/` | the router hub and one branch per subject with its integrity pack | `src/epinoic_logic/branches/README.md` |
| Channel | `channel/` | the path every inter-agent message takes: explicit requests, envelopes, request fidelity, constraints decided by the engine, claim verification, cross-agent consistency, receipts, relay history and the response gate | `src/epinoic_logic/channel/README.md` |
| Integrity | `integrity/` | envelopes, hand-offs, the synthesis ledger, staleness, cross-report consistency and synthesis entailment | `src/epinoic_logic/integrity/README.md` |
| Service and CLI | `service/`, `cli.py` | the authenticated HTTP boundary (tested in process and over a local socket) and the command line | `src/epinoic_logic/service/README.md`, `docs/integration-contract.md` |

## 3. The path of an answer

1. The router opens a task from a work plan and sends the specialist an explicit request (items, word and paragraph
   bounds with their scopes, supplied texts) in a hashed envelope.
2. The specialist's answer arrives as text or as a structured report. The branch adapter parses text into claims; a
   mapping is validated strictly against the report contract. Identity and integrity violations reject it before any
   content check.
3. The channel checks request fidelity (items addressed, constraints decided by the engine as signed results), source
   integrity (quotations located in the supplied texts, in their roles), the branch pack's subject checks (for STEM, the
   front end's engine-decided checks) and cross-agent consistency.
4. Each eligible claim is translated: the provider's proposal is parsed as data, validated, grounded against the
   supplied texts and the task record, and checked by the pipeline. The engine decides it, diagnoses the argument, binds
   and signs the result.
5. The outcome composer trusts only a result that binds, is current and verifies. It derives the display status, the
   release assessment (`release-v2`) and a bounded summary that ends with the scope statement.
6. The receipt carries every outcome, finding, constraint result, formal check and named diagnostic. The router
   receives the report with its receipt, or a rejection and no report. Relays and syntheses carry the history of the
   receipts they build on (INT-HIST-001).
7. The response gate (`channel/gate.py`) decides from the receipts alone what the student is shown: VERIFIED only when
   every check passed and one of them is formal; otherwise "not verified" above the accuracy threshold, or withheld.

## 4. Trust and provenance

- Every result is bound to the problem digest, the solver configuration, the component versions, the build, schema and
  policy identity and any non-default validation limits, and is HMAC-signed with its key id under the signature
  (`engine/provenance.py`). A result of another build stays inspectable but is never current, and is never released
  until the problem is verified again.
- `engine.release.release_check` is the engine's part of the release decision: authentic, bound, current, a positive
  verdict on the claim, its evidence computed, resting on established premises only, no named defect at warning or error
  by effective severity (rule 8) and diagnosed by this build's rules (rule 9). Formal entailment is never permission to
  release on its own.
- The integrity layer checks what agents say about each other: envelopes and replays, hand-offs, the synthesis ledger,
  staleness, and contradictions under a shared glossary named claim-minimally.

## 5. Named diagnostics (the argument diagnosis)

The three accuracy issues this design answers:

1. **Unchecked source labels.** A premise whose only support is a source or task label no check verified was treated as
   grounded, so "p, therefore p" or an unsupported premise could clear. Now only a check in this process confers
   authority, for circularity too (`assumed_grounding` is `not has_authority`), and the evidence rules name the premise
   (EVD-SRC-001, EVD-LACK-001, EVD-SRC-003, EVD-FIG-001, EVD-AUTH-001, EVD-CHERRY-001).
2. **The missing link written in as a premise.** For "A, so B" the encoding "if A then B" is valid, and Z3 rightly says
   so. The engine's R0 decides the point again from the premises a check established, names each of the writer's links
   with the missing link (ARG-LINK-001), and the pattern rules name the shape: affirming the consequent, denying the
   antecedent, a false dilemma, a hasty generalisation, a causal leap, a circular paraphrase, an equivocation.
3. **No reference knowledge for STEM method.** The closed STEM reference names a wrong formula (ST-REF-001 by
   dimension, ST-REF-002 by form against the data-booklet laws), and engine-decided checks name a missing unit
   conversion, an invalid step, a rounding that changes a conclusion; the front end names extrapolation, missing
   working, contradictory givens (ST-GIVEN-002, and ST-GIVEN-003 for probabilities) and symbol conflicts.

How they are built:

- **One model** (`named.py`): a closed table of codes, each with its canonical defect label (28 labels), its maximum
  severity, its layer and its caps; the key name `defect` is fixed. Existing finding codes are labelled through
  `named.DEFECT_OF_CODE`.
- **Layers**: the engine (signed with the result), the claim and report rules of the translator, the STEM front end and
  checks, and the channel's receipt findings (INT-ARG-001, INT-REQ-017, INT-XENC-001).
- **Determinism and bounds**: every rule reads the IR, the engine result, the grounding records and closed tables
  through bounded linear scans; the engine's derived runs are data-built subsets of the bound problem, decided on its
  own compiled terms, at most 24 per result, 1 s each and 8 s in all (the runs that need no model share one incremental
  solver under assumptions, and an identical derived problem is decided once). A run that is undecided or out of budget
  makes the diagnosis incomplete, and the rule that needed it fires nothing; release reads an incomplete diagnosis as
  unresolved, never as "none found". The cue tables are English: another language gets fewer diagnostics, a miss and
  never a false alarm.
- **One severity everywhere**: a cap (an ambiguous translation; a source-bound warning outside a source-bound task) is
  applied where the diagnostic is made and recorded in `capped_from`, so the signed copy, the outcome, the receipt and
  every reader agree. Release and the response gate read the effective severity, so a capped warning still blocks.
- **Display**: the claim summary's diagnosis section, after the verification lines, fits the room the other lines leave
  and lists blocking diagnostics first; no message template, display line or heading uses a success word
  (`named.SUCCESS_WORDS`). Every summary line is one line, and the model text a line or a message shows (a label, a
  meaning, a flag, a review issue) has its forgery words masked (`named.model_text`), so model text can write neither a
  line of its own nor a status.
- **What a check reads**: a located excerpt verifies a premise only when it states it (a literal, a conjunction of
  literals, or a rule it states as a conditional, a universal rule or a biconditional, `translate/stated_rules.py`); an
  excerpt that does not state its premise refuses it (`content_in_excerpt`), so a point dressed as a quotation is the
  writer's own and the circularity rules read it so. A relayed agent's report is a peer document whatever it is called,
  and its excerpts verify nothing.
- **Circularity in other terms**: besides the engine's normal form, Z3 itself decides whether a premise of the writer's
  own is equivalent to the point under every assignment ("2·dt = 82" for dt = 41); such a proof is E112, no verdict, and
  the translator refuses the encoding as circular (repair round 2, `engine/runner.py`).
- **Repair round 2** added three codes (ARG-LINK-002, a rule stated from subject knowledge, info; EVD-SRC-006, a source
  credited with the opposite stance, warning; ST-GIVEN-004, givens that cannot all hold under a law of uniform motion or a
  two-set count, warning) and widened the readings of the existing rules at their causes: paraphrase, complements, one
  symbol in two senses, "most" from a sample and a sample stated of a wider whole, a cause read into a correlation, a
  converse or inverse step packed into one premise or hidden in a bridge, an equivocal bridge, a recommendation that asks
  for reasons and an evaluation that gives none, months, recoveries and trends past the data's end, a reasoned
  conclusion read alike in a raw answer and in a report, premises that contradict each other named as a contradiction
  rather than refused as a circle, a self-certification kept beside a refusal, the STEM layouts that hid a defect (a
  computation over lines, a spaced product, a law on its own line, a condition before an equation), labelled and
  unlabelled objects, a given rebound against the request, rounded values against targets and the request's conditions,
  a request's own model past its range and a dated trend in Mathematics, free fall, two's complement and Boolean chains,
  and pressure and the dilution law in the closed reference. Each is in `docs/ARGUMENT_DIAGNOSTICS.md`, section 3, with
  its positive case and its control.
- **Repair round 3** added two codes (ARG-NS-003, an unbridged leap between two named things joined only by a connective,
  warning; ST-STEP-003, a rewrite inside a chain whose two sides differ at a sample point of the unknown, warning) and
  fixed the review's items at their causes (`docs/ARGUMENT_DIAGNOSTICS.md`, section 9, lists all 35 with their tests): an
  argument written in one sentence is read and translated; a sentence opening with a conclusion lead or a ground phrase
  that points back rests on the sentences before it; a report that links nothing gives a ranking judgement no reason;
  the refutations of figureless task premises made before repair round 2 are restored (a reported view, a question, a
  misreading of the task's words, an unstated connective); a quoted conjunction is stated conjunct by conjunct with each
  conjunct's own polarity; an excerpt's figure belongs to its own quantity, entity and period; a figure the answer works
  out, dates or rounds is no invention; a control cue warrants only the causal link it bears on; exhaustive options,
  censuses and durations are no fallacies; definition laws and symbol comparisons in STEM; the response gate reads only
  structured data and never reads an undiagnosed claim as passed; a legacy signature attests no key id; peer ids are
  normalised; the chronology reader is linear. Three items are left with their reasons (a lowered initial capital and
  the B8 gate decision, both pinned by earlier tests, and heuristic readings on clean answers; section 7 there).
- **Repair round 4** adds no code to the named table and fixes the review's 40 items at their causes
  (`docs/ARGUMENT_DIAGNOSTICS.md`, section 10, lists them with their tests). The correction and suggestion roles of a
  quoted span are read only in a marking, feedback, correction or editing task, which the channel sets from the plan, so
  an altered quotation framed as a correction in an analysis is named and the response gate withholds it; mentions
  ("avoids", "could have used") are read in every task. An either/or the task states, a task fact in other words (a
  pronoun resolved, the passive), a conversion given in an instruction, and the count, total and mean of a stated list
  ground their premises; one sentence that states two quantities gives each its own figure. A one-sentence argument
  with a pronoun conclusion is translated, and a paragraph's one reasoned claim is material. A leap between two named
  things is not bridged by a sentence that only names them. The cue tables read one comparative after a relative clause,
  "light" as radiation, and "did not work" for "ineffective". The engine bounds the values a nonlinear problem's products
  force (E307 by `policies.forced_value_digits`, in the policy manifest) and tests a restatement split across premises
  together (E112). A figure credited to a named data table that states it for another year, or for none, is CORE-SRC-007.
  STEM reads the absolute temperature, quantities already in SI, values the request gives and identities under any
  request. Capped diagnostics no longer name a defect in a release note. Left with their reasons (section 7 there): a
  leap about one named subject (word overlap cannot tell it from a sound link, measured), a lowered initial capital and
  the B8 decision (both pinned), the wall-clock bounds under load, and the hold-out case error.
- **Repair round 5** adds no code to the named table (ARG-CIRC-003 is also made in the report layer) and fixes the
  review's 39 items at their causes, or says why not (`docs/ARGUMENT_DIAGNOSTICS.md`, section 11, lists them with their
  tests). Two more shapes of an unbridged leap are named (a ranked cause, an advised action toward a new named thing); an
  excerpt whose clause contradicts the literal it is cited for refutes it; a definition or a closed enumeration a record
  states is a rule it states; a figure relation is listed with the facts, never named a leap; a claim whose reason clause
  only restates its point is circular; cases named by a list or a label make a hasty generalisation, and a causative verb
  reads a cause. The task type a report states about itself never widens the quotation roles; mentions are read in more
  frames. The ledger reads swaps between parallel statements, ordinal labels, accounting parentheses, precision notes,
  more status forms, word counts and credit forms. STEM reads units given only in the request, inline givens, rounded
  conclusions, adjacent letters, rebound symbols, reasoned proofs, unit homographs, counts in sentences and '±' chains.
  The channel unwraps nested envelopes and refuses cut structured replies; the generic parser is linear on list answers.
  Left with their reasons (section 7 there): a figure at its written precision and a lowered initial capital (both
  pinned), a report point with unlinked evidence (the hold-out case), info labels on interpretive links (pinned by
  design), a nonlinear condition, and part of the cost. The round's measurement (all 68 hold-out controls clean, 65 of
  66 defects named) also found three false alarms its own readings make on genuine arena answers (an excerpt of function
  words analysed as words, a figure after a lead phrase, a summary that skips an intermediate value), left as found and
  described there, since no code was changed after the measurement.
- **Close round 1** compares the repair round 5 tree with the committed base input by input and closes the 16 items on
  which it was worse (`docs/ARGUMENT_DIAGNOSTICS.md`, section 12, lists them with their tests), each at its cause: a source
  rule stated only hedged, framed, restricted or with a dropped condition is no longer verified as stated; a task sentence
  of another time or direction no longer validates a premise; the month "May" is no modal; the self-certification pattern
  is linear; a span after a negated verb is a mention only for one word; the three false alarms of round 5 are gone; a
  heading that restates the task is an info record, not a circle; a magnitude after a signed chain and a rate in prose are
  no STEM errors; the rule text no longer quotes hold-out names. The review's items that the base fails the same way are
  listed as known defects (section 7 there). No version changes.
- **Close round 2** compares the close round 1 tree with the committed base the same way and takes its 9 items under a
  convergence rule (`docs/ARGUMENT_DIAGNOSTICS.md`, section 13): a reading an earlier close round narrowed is not narrowed
  again but reverted to the base's reading for its whole class. Reverted: a span after a contrast ("unlike", "rather
  than", "instead of") is a quotation and is checked again, and a task premise that shares an atom with the point is never
  validated by a task sentence (a proposition the task quotes for discussion no longer grounds its own restatement).
  Narrowed: the quotation-role reader is linear (the security item); an answer that writes a Boolean constant with the AND
  dot is read without the AND dot; a count's "about 300" is read at its first significant digit; a synthesis carries no
  layout finding of its source reports. Left, with the reasons in section 7 there: a plainly stated source rule with a
  qualifier word elsewhere in its sentence (close round 1's reading, which may not be narrowed again and whose revert
  would reopen its own item), a rule whose consequence the excerpt negates, a hold-out leap after "since its", and the
  relay carries of findings false in both trees. No version changes.
- **Close round 3** compares the close round 2 tree with the committed base the same way and takes its 10 items under the
  convergence rule and a discrimination rule (`docs/ARGUMENT_DIAGNOSTICS.md`, section 14): a base outcome counts as a
  detection only when the base tells the defective input from its matched correct control. Reverted: a span right after a
  reporting verb under a negation is a quotation and is checked again ('not only writes "..."' no longer hides an invented
  quotation). Narrowed: EVD-SRC-001 no longer names a premise that restates a supposition the task sets ("Assume that
  ..."). Made linear (security), with the old answers: the ledger's swap reader and figure index, and the pooled
  consistency check, which no longer re-solves a joint problem it already decided. Turned into known defects by the
  discrimination rule (the base flags their correct controls alike): a task sentence that reports a forecast, hope or
  plan, a title-case "May", and a rule whose excerpt negates the consequence. Left, with the reasons in section 7 there: a
  plainly stated rule with a qualifier word elsewhere, the relay carries, "about 300 g" for 260 g (each needs a second
  narrowing the convergence rule forbids, or a revert that would weaken the tests pinning its detections), and the cost of
  verifying r7's claims, which the base never verifies. The translator moves to 0.5.1 and the rules to `argdiag-2`, so a
  result of an earlier round never reads as current.

Every label, with its derivation, code, example and clean control, is in `docs/ARGUMENT_DIAGNOSTICS.md`, with the
measured results.

## 6. False alarms on correct work

The same checks that catch faults must not accuse correct answers. The end-to-end simulation of 16 October 2026 found
false errors on correct work (STEM misreadings, word bounds measured on the wrong part, corrections and mentions read as
invented quotations, figures derived by two routes pooled exactly, dropped links giving false counterexamples, figures
at their stated precision). Each is fixed at its cause with a clean control and a wrong twin that still fails
(`docs/ARGUMENT_DIAGNOSTICS.md`, section 5; `docs/STEM_DESIGN.md`, sections 21 and 24). Repair round 1 of the argument
diagnosis removed the false alarms its review found the same way (quoted rules, dated changes, pooled and derived
figures, CORE-QNT-001 readings, STEM statement readings, feedback quotations, quoted conjunctions, complementary options,
answers wrapped in quotation marks, root sets listed after their first member), each with its control; the review's probe cases are kept as data (`tests/data/repair_round1_cases.json`). Repair round 2 removed the false alarms its review
and its own probes found (a subject word shared by two figures, folds and hedges, a worked result restated in the next
sentence, a dated series, a figure derived in an earlier sentence, a quoted equation, a task value substituted into a
rearrangement, a condition named but not asserted, a lowered capital, notation spelled in words, word equations, a time
converted in brackets, a value after a preposition, a History quotation in the judgement's sentence, a spaced product,
an equation after a condition, a task fact in other words, an abbreviation of a subject, a unit of several words, an
item answered in notation and a change across sentences), each with its control in the round's tests. Repair round 3
removed the false alarms its review found (a figure after "compared with", a bound read for a ceiling, an exact quotation
of a list read as circular, worked, dated and rounded figures charged as invented on real answers, exhaustive options,
a census, a source's "many", a duration, a percentage rounding read as a unit change), each with its control in the
`test_repair_round3_*.py` files. Its measurement found two false alarms the round itself makes, left as found so that
the measured tree is the staged one: an either/or the task sets, which the restored refutation of task premises refutes
again as the base tip did, and a declared unit read from an entity's label ("in A (m³/s)" read as amperes)
(`docs/ARGUMENT_DIAGNOSTICS.md`, section 7). Repair round 4 removed the false alarms its review found (the either/or the
task states, a task fact in other words, a count read off a quoted list, the count and the expected count of a stated
list, a conversion given in an instruction, another report's quoted line, a check tip read as a judgement, an identity
proof named vacuous, mentions and marking corrections read as quotations, one figure in two notations, a paraphrased
parallel trace, a correct period over a mass the request gives, an answer that is one line of arithmetic), each with its
control in the `test_repair_round4_*.py` files. Repair round 5 removed the false alarms its review found (a definition the
task states, a word quoted as a mention, a word count read as a self-certification, a bare assertion read in a part that
asks for none, a reasoned proof read as missing working, ordinal labels, notations and a '±' chain read as changes or
errors, a catchment label read as the ampere: the round-3 false alarm above), each with its control in the
`test_repair_round5_*.py` files.

## 7. Not implemented here

- The Overseer's knowledge pack: end-to-end items B11 (a confirmable `finding_false`, written as pack text in
  `docs/ARGUMENT_DIAGNOSTICS.md`, section 7), B12 and O1 to O3 belong to the overseer build.
- A published JSON Schema, non-zero CLI exit codes for non-definitive statuses, `translator_version` in the engine
  result and a dependency lock (`docs/integration-contract.md`, section 11).
- `docs/STATUS.md`, which `CLAUDE.md` and the README name, does not exist; `docs/BASELINE_REVIEW.md` records the gap.
- Deployment: none. The providers' adapters are implemented and untested live.

## 8. Scope statement

Every result carries this statement verbatim:

> This result concerns only the formal encoding it is bound to, under the encoded premises and the stated solver
> configuration. It does not establish that the premises are factually true, that the natural-language claim was
> translated faithfully, or that any interpretive judgement is correct. Grounding and semantic-fidelity information is
> reported separately and is advisory.

A named diagnostic, like a check, is a property of the encoding and of this code only.
