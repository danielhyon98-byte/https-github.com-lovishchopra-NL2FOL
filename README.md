# Epinoic AI — Logic Translator and Z3 Verification Engine

Proprietary. See `LICENSE` and `THIRD_PARTY_NOTICES.md`. Status of every component
(planned / implemented / tested / deployed) is in `docs/STATUS.md`. Nothing in this
repository is deployed.

## What this program does, in plain language

Epinoic AI's tutor is a set of subject-specialist agents (English, Mathematics,
Physics, Economics, History and so on) that write structured answers for
International Baccalaureate students. Language models can state things confidently
that do not follow from the evidence, invent quotations, or contradict themselves.
This program makes those failures **visible and checkable** without pretending to
judge whether an interpretation is "true".

It does three separate things and never blurs them:

1. **Structural checks (deterministic code).** Is the specialist's report well
   formed, are its claim ids stable, is the original text unchanged (hash), and does
   every quotation it cites actually occur, word for word, in the text the student
   supplied? Invented quotations and invented line citations are flagged here.
2. **Translation (model-proposed, code-validated).** For claims that *can* be
   formalized, a model proposes a small typed logic problem: the atomic propositions
   the specialist relied on, where each one is grounded (a quotation, a task setting,
   an inference the specialist made, an outright assumption), the inferential links
   the specialist asserted, and the point being argued. The proposal is **data**: it
   is parsed strictly, validated against a closed schema, and never executed.
3. **Formal verification (Z3).** The engine checks whether the premises are
   consistent, and if so whether they entail the point. It reports exactly which
   premises the proof relied on and which of those are unverified inferences or
   assumptions. If the point does not follow, it shows a concrete counterexample. If
   the premises contradict each other, it names the conflicting ones.

A verified result therefore says: *given these encoded premises, under this
configuration, this conclusion does or does not follow*. It never says the premises
are factually true, that the translation captured the claim faithfully, or that a
literary or historical reading is correct. Every result carries that scope
statement. This is deliberate: the system is not a universal hallucination
detector; it is an auditable way to show what was checked, how, under which
assumptions, and what remains uncertain.

## The primary feature: every message between agents goes through the translator

The translator is a **branching infrastructure**: one hub that every specialist
(English, History, Psychology, Economics, Business Management, and any subject
added later) communicates with the primary router through, and one branch per
subject carrying an **integrity pack** of subject-specific checks. The hub integrity
(envelopes, hand-off, request fidelity, claim ledger, staleness, cross-agent
consistency, signing) is shared; the packs add what each subject's knowledge
documents demand, such as quotation integrity for literature, chronology and dated
figures for history, study attributions for psychology, elasticity arithmetic for
economics and margins for business. See `src/epinoic_logic/branches/README.md`.

STEM subjects (Physics, Chemistry, Biology, ESS, SEHS, Design Technology, Mathematics AA and AI,
Computer Science) are three more branches of the same hub: `sciences`, `mathematics` and
`computer_science` (`docs/STEM_DESIGN.md`). A deterministic front end (`src/epinoic_logic/stem/`)
reads answers that mix equations and prose in LaTeX, Unicode, ASCII and words, without evaluating
any text, and turns every relation it recognises into an IR problem the engine decides (written
arithmetic, substitutions, unit conversions, algebra steps, stated roots, balances, Boolean
identities, based numerals) under a documented tolerance rule, or names it undecided with the
reason. A wrong step such as `a = (20 - 0)/4.0 = 6.0 m s⁻²` reaches the router as an INT-SUBJ-001
error naming the claim, with the engine's computed and stated values; correct work is never an
error. A STEM check proves a property of its encoding only: that the written arithmetic, step or
balance holds or does not under the stated premises and readings, never that a law applies, that
data are true or that a model is physically valid.

Agents do not pass raw text to each other. The `channel` package
(`src/epinoic_logic/channel/`) sits on the communication path. When the router sends
a student's request to a specialist, the request is made explicit (what is asked,
word and paragraph limits, which texts may be used) and wrapped in a hashed envelope.
When the specialist answers, the response must reply to that exact request and is
checked before the router sees it: right task and agent, no replay or tampering,
quotations found in the supplied texts, numeric constraints decided by the engine as
signed results, eligible claims verified, items of the request covered, and
contradictions with claims already transmitted by other agents named. The router
receives the report together with a receipt, or a rejection and no report. The same
channel carries agent-to-agent transmissions, such as the English specialist's output
reaching the combinator, with the claim ledger checked on the way. See
`channel/README.md` and `integrity/README.md`.

Integrity properties the channel holds on every transmission and relay:

- The envelope's sender is bound to the payload's owner: a specialist cannot relay a colleague's report, or a copy of it, under its own name (INT-ENV-008).
- A report the router already holds is never overwritten: a report id re-delivered with a different payload is refused and the first delivery kept (INT-HANDOFF-015).
- A response that merely echoes the request is named as such and counts for no request item (INT-REQ-011).
- A quotation whose words occur in the supplied text but whose form differs (initial capital, a verse line break written " / ", a long elision, accents such as 'Román' for 'Roman') is a warning, never an invented quotation (INT-REQ-010).
- A quotation credited to one source but found only in another supplied text, a peer specialist's report included, is a wrong attribution and is named with both texts (CORE-SRC-005, ES-SRC-008).

## STEM subjects: equations and prose (`src/epinoic_logic/stem/`)

STEM specialists write a mix of equations and prose: given values, a law, a substitution, a
result with its unit and a sentence of explanation, in LaTeX, Unicode, ASCII or words. The
STEM branches carry that mix across the hub the same way the English and History branches carry
prose. They are three more branches of the same hub, channel and integrity layer, not a
separate system. Design: `docs/STEM_DESIGN.md`. Measured results: `docs/STEM_RESULTS.md`.

What the STEM branches do:

- **Route.** Physics, Chemistry, Biology, ESS, SEHS, Design Technology and general science go to
  `sciences`; Mathematics AA, AI and an unspecified course to `mathematics`; Computer Science to
  `computer_science`. An unrecognised subject still goes to `generic`.
- **Read, never evaluate.** A deterministic front end (a single-pass lexer and a bounded Pratt
  parser over a closed grammar) reads the answer into one shared document: statements,
  formulas, symbol bindings with their source, and every relation stated. No agent text is
  evaluated: no `eval`, `exec`, `compile`, `sympify`, `parse_expr` or any library that evaluates
  strings, and three AST scans in the tests enforce it. Claims are offset substrings of the
  answer (`s1.2`; `m1.2` in Mathematics, `c1.2` in Computer Science), and the router receives
  the answer verbatim.
- **Decide what can be decided.** Every relation the front end recognises becomes an IR 1.0
  problem the Z3 engine decides, or is named undecided with the reason, or is recorded as a
  binding, a law or a premise-free context line. Nothing recognised is dropped silently. The
  checks:

  | Check | What the engine decides |
  | --- | --- |
  | `stem-eq` | written arithmetic, `E = S` |
  | `stem-sub` | substituted values against the bindings of their symbols |
  | `stem-alg` | an algebra step follows from the line before it |
  | `stem-sol` | stated roots satisfy the equation, and the full set when it is claimed |
  | `stem-cnv` | an explicit unit conversion |
  | `stem-cmp` | a stated order or inequality, or an inequality step |
  | `stem-res` | a result restated in prose against the chain's final value |
  | `stem-giv` | a Given value against the request (warning) |
  | `stem-tgt` | a show-that answer's final value against the request's target (warning) |
  | `stem-chem` | element and charge balance of a chemical equation |
  | `stem-bool` | a Boolean identity |
  | `stem-tt` | the stated rows of a truth table |
  | `stem-base` | a conversion between number bases |

  A stated value passes when it lies within `h + τ·|C|` of the value `C` computed from the
  written expression: `h` is half a unit in the stated value's last digit; `τ` is 1 % for `=`,
  5 % for `≈` or "about", and 0 for conversions, comparisons and exact work; rounded
  intermediates, data-booklet constants and function values range over their rounding or
  enclosure intervals. The band is computed inside the IR, so the engine, not Python, decides
  whether a value lies in it.
- **Name every fault it can see, and never flag correct work as an error.** An error comes only
  from an engine result about a relation that rests on what the answer and the request state.
  Anything that depends on a reading the answer did not state (a booklet value for an unstated
  symbol, a symbol's identity across request and answer, a show-that target, an unknown unit)
  can only be a warning. Ambiguous notation becomes alternative readings or a warning, never an
  error.

**A worked step translated into an engine problem.** Before STEM support this answer crossed the
hub ACCEPTED with no finding and no check (the true acceleration is 5.0 m s⁻²):

```
request  A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.
answer   The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻².
         The acceleration is therefore 6.0 m s⁻².

claims   s1.1  evidence      "The trolley starts from rest, so u = 0."          u = 0: a binding
         s1.2  quantitative  "Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻²."   a = Δv/Δt: a law, recorded
                                                                           (20 - 0)/4.0 = 6.0: check stem-eq-1
         s1.3  quantitative  "The acceleration is therefore 6.0 m s⁻²."      restatement: check stem-res-1
```

`stem-eq-1` is this IR problem (shown in a compact notation; the problem itself is JSON data,
validated against the closed IR schema):

```
problem  stem-eq-r1-1   query: entailment   policy: linear   expected: ENTAILED
symbols  c : Real    the computed value (as written)
         r : Real    the stated value (as written)
premise  C_DEF   c = 20 / 4        grounding: supplied_text, verified ("figure stated in the report itself")
premise  R       r = 6             grounding: supplied_text, verified
goal     STATED  ite(c − r ≥ 0, c − r, −(c − r)) ≤ 0.05 + 1/100 · ite(c ≥ 0, c, −c)
                 (|c − r| ≤ h + τ·|c|, with h = 0.05 for "6.0" and τ = 1/100 for "=")
notes    STEM check: proves a property of its encoding only. ... readings: as written
```

The written zero term is dropped as an exact identity (`20 − 0` is `20`) and `4.0` is written as
its exact value; the division itself is left to the engine. Z3 answers COUNTEREXAMPLE with
`c = 5`, `r = 6`, and the receipt says:

```
Transmission ACCEPTED_WITH_FINDINGS via branch sciences. ... Report's own formal checks: 2 (1 ok, 1 FAILED,
0 undecided); FAILED: stem-eq-1. ... Findings: INT-SUBJ-001.
INT-SUBJ-001 (error) on claim s1.2: the report's own stem_arithmetic statement does not hold (engine
counterexample: c = 5, r = 6; c is the value computed from the written expression, r the stated value) ...
```

`stem-res-1` holds (the restatement agrees with the chain), so only the faulty step is named.
The result is signed and bound to the exact problem, and the report is still delivered. With
`= 5.0 m s⁻²` the same answer is ACCEPTED with both checks ENTAILED.

**Finding codes.** Errors come only from the engine; the STEM pack itself emits no error.

| Code | Severity | Meaning |
| --- | --- | --- |
| INT-SUBJ-001 | error | an engine check of the answer's own statement does not hold (with the computed and stated values) |
| INT-SUBJ-002 | warning | such a check is undecided (unknown, timeout, unsupported, vacuous, inconsistent premises, the 8 s check budget spent) |
| INT-SUBJ-004 | warning | a check that relied on a reading the answer did not state does not hold |
| ST-PARSE-001 | warning | notation outside the grammar, or a relation withheld because its operands may be cut; not checked |
| ST-PARSE-002 | warning | too many readings (implicit multiplication, unit or symbol ambiguity); not checked |
| ST-UNDEC-001 | warning | a relation outside the encodings (calculus, limits, Σ with symbolic bounds, vectors, matrices, complex numbers, `!`, asymptotic notation, a function of an unknown), with the reason |
| ST-UNDEC-002 | warning | a numeric relation depends on a symbol with no stated value and no admissible booklet value |
| ST-UNDEF-001 | warning | an undefined expression (division by zero, even root of a negative, log of a non-positive value, 0⁰); no check built |
| ST-UNIT-001 | warning | an unrecognised unit; the relation is checked as written, at warning severity |
| ST-UNIT-002 | info | an ambiguous unit symbol (`M`: molar or mega) checked under both readings |
| ST-DIM-001 / ST-DIM-002 | warning | the two sides of a relation, or the terms of a sum, have different dimensions |
| ST-ALG-001 | warning | a mathematics step takes only the non-negative root with no stated domain restriction |
| ST-CHEM-001 | warning | a chemical equation that cannot be read; its balance is not checked |
| ST-CODE-001 | info | a code block: never run, never checked |
| ST-SCOPE-001 | info | a symbol rebound to a different value; substitutions match any binding |
| ST-LIM-001 / ST-LIM-002 | warning | a bound exceeded (expression, literal, IR size; more than 128 checks or 1,024 math spans per answer) |
| ST-INTERNAL-001 | warning | the STEM pack failed internally; its checks are missing and must not be read as passed |
| BR-INTERNAL-001 | warning | a pack of any branch raised; its findings are missing and must not be read as passed |

**Scope statement** (in every STEM problem's `notes`): a STEM check proves a property of its
encoding only. It proves that the written arithmetic, substitution, conversion, algebraic step,
balance or Boolean identity holds, or does not hold, under the stated premises, the documented
readings and the STEM tolerance rule. It does not establish that a law applies, that data are
true, that a model is physically valid, that a unit is the right one beyond the dimension and
conversion checks, or that the answer is what the question wanted.

**Measured here** (`docs/STEM_RESULTS.md`): on the 84 labelled answers written before
implementation, 38 of 38 injected faults are named with the right code and none of the 46
correct answers gets an error; on the 558-item corpus, 293 of 293 faults are named with no error
on correct work. These answers were written for the tests. The STEM arena with live
specialists (cheapest model tier, each configured only from its own v4 knowledge base, no
textbook library) and the review rounds were not run in this build; they run in the integrated
arena that merges this branch.

## Features of the logic translator (`src/epinoic_logic/translate/`)

| Feature | What it does | Where |
| --- | --- | --- |
| Claim-record input | Works on structured claims from a specialist report (ids, role, subject, source refs, assumptions), not on raw student text. | `contracts.py` |
| Deterministic eligibility | Code, not the model, decides whether a claim may be formalized: argument structure (point + supporting claims), structural counts, exact numeric claims. Interpretive, factual and rubric judgements are routed elsewhere. | `eligibility.py` |
| IB subject policy | Per-subject profiles say which claim classes are allowed (quantitative claims in Mathematics, Sciences, Economics, Business; argument structure only in Literature, History, Arts, TOK). The profile text is injected into the prompt so the model knows what cannot be established in that subject. | `subjects.py` |
| Staged decomposition | The prompt asks the model to list grounded atomic propositions first, then the specialist's inferential links, then assemble the problem. Inspired by the NL2FOL method; no code or prompt text copied. | `prompts/translate_v1.md` |
| Grounding checks | Quotations cited as grounding are matched verbatim (then with typographic normalization, and through stated form-difference tiers such as a long elision or different accents) against the supplied text; `verified` is set only by this code. Each text's normalised forms and each located excerpt are cached in bounded caches keyed by the text's digest, so an answer never depends on the cache. | `grounding.py` |
| Strict parsing | Model output is parsed with a plain JSON parser only (code fences stripped); anything else is a failed attempt. | `parsing.py` |
| Bounded retries | Validation diagnostics are fed back for at most one retry; the status then becomes INVALID_FORMALIZATION rather than looping. | `pipeline.py` |
| Ambiguity flags | The model must declare materially different readings; the result becomes AMBIGUOUS_TRANSLATION and is never shown as verified. | `pipeline.py` |
| Replaceable providers | Fixture provider for tests; Anthropic and OpenAI-compatible adapters behind one interface (untested live here). | `providers/` |
| Advisory semantic review | An independent reviewer rates translation fidelity; the verdict is labelled advisory and never changes the formal status. | `review.py` |
| Outcome for the Overseer | One record per claim: translation, signed engine result, structural findings, review, a derived display status and a plain-language summary ending with the scope statement. | `outcome.py` |

## Communication between agents (`src/epinoic_logic/integrity/`)

Miscommunication between the router, specialists, combinator and Overseer is
checked as well as hallucination inside one answer. Deterministic code checks
message envelopes (replay, tampering, mis-threaded replies), router hand-offs
(wrong task, unselected agent, off-subject, citations outside the retrieval scope),
result staleness (a verification result reused after the claim's representation
changed, or unsigned), and the combinator's claim ledger (material claims dropped
without record, claims with no source, certainty inflated above the weakest source,
evidence references lost, conflicts "resolved" without a basis). Z3 then checks
whether specialists' formalized claims contradict each other under a shared glossary,
naming the conflicting claims, and whether each synthesized claim is actually
entailed by the source claims it cites, producing a counterexample when the
combinator stated more than its sources support. See `integrity/README.md`.

## The verification engine (`src/epinoic_logic/engine/`)

Restricted IR 1.0 (Bool, Int, Real; 24 allowlisted operators; exact numerals as
text) → validator (sorts, identifiers, limits, policy; collects all diagnostics) →
compiler (one Z3 call per node, fresh context) → procedures (consistency first,
then entailment with tracked unsat cores; exact models) → result bound to a digest of
the exact problem, solver configuration and component versions, and HMAC-signed so
the Overseer can reject anything an agent fabricates. Statuses form a closed set;
only six are definitive and none means "the claim is true".

## Repository layout

- `src/epinoic_logic/ir/` — IR schema and canonical digests (`README.md` inside)
- `src/epinoic_logic/engine/` — validator, compiler, procedures, provenance, runner
- `src/epinoic_logic/translate/` — contracts, eligibility, subjects, grounding, pipeline, providers, review, outcome
- `src/epinoic_logic/branches/` — the router hub, subject branches and integrity packs (primary infrastructure)
- `src/epinoic_logic/channel/` — the translator channel every inter-agent message passes through
- `src/epinoic_logic/integrity/` — inter-agent envelope, hand-off, ledger, staleness and formal cross-checks
- `src/epinoic_logic/adapters/` — specialist adapters (generic structured; English specialist as worked example; History; the STEM parser; multi-subject fixtures)
- `src/epinoic_logic/stem/` — the STEM front end, checks, SI reading and hub hooks (`README.md` and `ENCODINGS.md` inside)
- `src/epinoic_logic/service/` and `cli.py` — authenticated HTTP boundary and command line
- `tests/` — unit, end-to-end, service and `stress/` suites
- `docs/` — audit, plan, design, status, stress results, STEM design and results (`STEM_DESIGN.md`, `STEM_RESULTS.md`), evidence, context pack

## Running

```
python -m venv .venv && .venv/bin/pip install -e ".[dev,service,providers]"
.venv/bin/pytest                      # unit, e2e and service tests
.venv/bin/pytest -m stress tests/stress   # load, concurrency, adversarial volume, soak
epinoic-logic verify problem.json     # one verification from the command line
```

## What it does not do

It does not decide literary, historical or rubric judgements; it does not check
quantifiers or symbolic calculus (these are reported as UNSUPPORTED or, for STEM answers,
named undecided); units are checked only by the STEM branches' dimension warnings and explicit
conversion checks, and nonlinear algebra only under the named `nonlinear` engine policy the STEM
checks use; it does not run inside a Cloudflare Worker (see `docs/AUDIT.md` for
the runtime evidence); and it does not call any model provider in its tests.

## Arena: real agents, contained environment

Isolated specialist agents configured only from their subjects' knowledge documents answer
router tasks; every output crosses the hub as in production, independent overseer lenses judge
fidelity and fault naming, and fixes are regression-tested before the next round. Rounds 1 to 6
used the English and History specialists; round 7 used sixteen specialists across fifteen IB
subjects, added a fourth lens on translation fidelity, and attached overseer agents that judged
blind dossiers. No round reached the target of 0.98 from every lens: round 7's four lenses gave
0.532, 0.4246, 0.7477 and 0.6384. Each round's material, verdicts, findings, fixes, harness
figures and what remains open are in `docs/ARENA_RESULTS.md`. Rounds 8 to 10 run after the STEM
and overseer builds merge, and the optimisation checks run last, after every bug-testing round.
Stress figures for the engine, channel and hub are in `docs/STRESS_RESULTS.md`; no stress iteration
was run after the bug-fix rounds. The harness's functional rate checks that the hub delivered and
decided every transmission and named every injected fault; it does not judge whether a
finding is true. Its summary therefore states, under the headline, how many genuine receipts
carry error-level findings and are still counted functional, and names every definitive
verdict other than ENTAILED shown on a genuine claim with what it rests on, beside the
number of genuine claims whose encoding got no verdict (vacuous, circular, an unasserted
figure, an unencoded reason, a rounded figure encoded as exact). Every group of a round
that carries syntheses has exactly one synthesis record, whatever happened to its members,
so the number of transmissions never depends on what crashed. Whether the receipts are
right is judged by the overseers.

The test layers and a running log of bug and stress testing are in `tests/README.md`; the per-round arena record is `docs/ARENA_RESULTS.md`.

What the engine accepts and returns, and what a result establishes, is the integration contract in `docs/integration-contract.md`. The baseline review in `docs/BASELINE_REVIEW.md` records the checks run on the baseline commit, its known limits and the next milestone.
