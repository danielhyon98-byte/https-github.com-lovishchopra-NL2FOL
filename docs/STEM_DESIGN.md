# STEM support: design

**Status: IMPLEMENTED on branch `stem-build`; not yet merged.** All five stages of section 17
(`core`, `engine`, `checks`, `branch`, `corpus-eval`) are in the code, and the full suite passes
(docs/STEM_RESULTS.md). The review rounds (overseer audits of each stage) and the STEM arena with
live specialists were **not run in this build**: the STEM build is run as one integrated system
with the main arena, which merges this branch (round 7 when it is ready, otherwise round 8) and
tests STEM there with a STEM lens and a STEM fixer. This document was revised after
implementation to match the code; where the code refined the original design, the text below
states what the code does (and section 19 lists the refinements).

This document synthesises two independent designs: the representation-outward design (R) and
the fault-outward design (F). R builds a math front end first and derives the checks from what
it reads. F starts from the faults the hub let through before STEM support and builds an engine
encoding for each. Where they disagreed, section 2 records the decision and the reason. Sections
17 and 18 split the implementation into five sequential stages that touch disjoint files.

Evidence used at design time came from read-only probes run against this worktree before
implementation (baseline suite then: 1067 passed, 12 deselected). The encodings in sections 5 and
7 were each run through `engine.runner.verify`. Each took 4 to 20 ms. Forty arithmetic checks in
a row took 327 ms. Measured results of the implementation are in docs/STEM_RESULTS.md.

---

## 1. Purpose and scope statement

The Epinoic logic translator turns what specialist agents write into IR that the Z3 engine
decides, so that no misstatement passes silently between agents (router, specialists,
combinator). STEM support is not a separate system. It is one more set of subject branches on
the same package (`epinoic_logic`), the same hub, the same channel and the same integrity
layer.

What STEM support must guarantee, for Physics, Chemistry, Biology, ESS, SEHS, Design
Technology, Mathematics (AA, AI) and Computer Science answers that mix equations and prose:

1. **Verbatim delivery.** What the router receives is what the specialist said.
   `original_response` is never altered. Every claim text is a substring of it, taken by
   offset. Code blocks, data lines and display maths become claims; they never vanish.
2. **Decided or named.** Every relation the front end recognises ends in exactly one outcome
   (`stem/relations.py`):
   - `check`: an engine check;
   - `undecided`: a finding that names it as undecided and gives the reason;
   - `binding` (a value stated for a symbol, `m = 2.0 kg`), `formula` (a stated law or
     definition, `F = ma`; its truth is out of scope) or `context` (a relation with no premise
     to check it against, such as the first line of a derivation or a domain condition
     `x > 3`): recorded, not checked.
   Nothing recognised is dropped silently.
3. **Right code, right severity.** Every fault the infrastructure can see is named on the
   receipt with a stable code and a documented severity.
4. **No false errors.** Error severity comes only from an engine result about a relation that
   rests solely on what the report and the request state, or on exact encoding devices. If
   the reading or the tolerance could be wrong, the outcome is a disjunction of readings or a
   warning, never an error.

**Scope statement** (`stem.tolerance.STEM_SCOPE`, the first sentence of every STEM problem's
`notes`; every receipt summary still ends with the channel's `_SCOPE_TAIL`): a STEM check
proves a property of its encoding only. It proves that
the written arithmetic, substitution, conversion, algebraic step, balance or Boolean identity
holds, or does not hold, under the stated premises, the documented readings and the STEM
tolerance rule. It does not establish any of the following:
- that a law applies;
- that data are true;
- that a model is physically valid;
- that a unit is the right one beyond the dimension and conversion checks named here;
- that the answer is what the question wanted.

The engine's `SCOPE_STATEMENT` applies unchanged.

**Observed before STEM support, and now.** Before this work a Physics answer
`a = (20 - 0)/4.0 = 6.0 m s⁻²` (true value 5.0) went to the generic branch and crossed the hub
ACCEPTED, with no finding and no formal check.

With STEM support the same answer (fixture `stem-phys-001`):
- goes to the `sciences` branch;
- gets a `stem-eq-1` check whose engine status is COUNTEREXAMPLE, with model `c = 5`, `r = 6`;
- receives INT-SUBJ-001 (error) naming the claim that holds the chain (`s1.2`), with the
  computed and stated values in the message;
- is still delivered (ACCEPTED_WITH_FINDINGS).

Of 13 deliberately wrong probe answers, only 1 had its equation error caught before STEM
support. The test plan (section 16) requires every one to be caught or named, and
`tests/stem/test_corpus.py` asserts that all 13 now are.

---

## 2. Synthesis decisions (conflicts resolved)

| # | Point | R (representation-outward) | F (fault-outward) | Decision |
| --- | --- | --- | --- | --- |
| D1 | Linear or nonlinear | Allow nonlinear (`allow_nonlinear`) per check whenever a product of two unknowns appears. | Keep every check linear: substitute the stated value as a literal coefficient (`σ·s` for `s²`; plug in a stated root). | **Linear by default.** A check is nonlinear only when its encoding really multiplies two unknowns: exact surds, symbolic algebra steps, completeness of solution sets, and the interval form with two or more interval operands. F's literal-substitution trick is kept for exactly one job: a stated root is checked by substituting it into the equation (linear membership). It is not used as a general device, because it bakes the value under test into the coefficients and does not compose. |
| D2 | How the nonlinear policy reaches the engine | `FormalCheck.limits: Optional[Limits]`, any value allowed. | Not needed. | **A named policy, not raw Limits.** `FormalCheck.policy` is either `"linear"` or `"nonlinear"`. The engine maps the name to a fixed `Limits` (`engine/policies.py`), so a pack can never raise `max_nodes`, the digit count and so on. The engine records any non-default Limits on the signed result. Implemented: `PACK_POLICIES` is read-only; `nonlinear` is `Limits(allow_nonlinear=True)` and nothing else; `policy_config` caps the solver's `rlimit` at `NONLINEAR_RLIMIT` (2,000,000); and the runner refuses any assertion of polynomial degree above `NONLINEAR_MAX_DEGREE` (24) with E201 before compiling, because Z3 could not be interrupted inside very high-degree polynomials. |
| D3 | Constants (g, h, c, ...) | Never supply constant values. An unbound constant stays free, so the check is undecided. | Written constants match a disjunction of data-booklet values (`g ∈ {9.8, 9.81}`). | **A constants table, used two ways.** (a) A written literal that matches a table constant at its written precision may take any value from its rounding interval up to the booklet value. This only ever widens, so it cannot cause a false error. (b) An unbound standard-constant symbol may take its booklet value only when a dimension check against the stated result unit confirms that reading. Such a check carries `failure_severity="warning"`, so a failure is INT-SUBJ-004 (warning), never an error. Its premise is grounded `assumption`, so the engine lists it in `ungrounded_dependencies`. |
| D4 | Transcendental functions and π | Exact-value table only (special angles, powers of ten). Everything else is undecided. | Use π as an enclosure symbol; linearise square roots. | **Exact table plus enclosures.** Exact values (sin 30° = 1/2, log 1000 = 3) stay exact. Any other sin, cos, tan, arcsin, arccos, arctan, ln, log10 or exp of a closed argument, and π and e, become an enclosure symbol: a deterministic `Fraction` routine computes a rational interval of relative width at most 10⁻¹⁵. A check that uses an enclosure is decided in the interval form (D6), so it can never fail correct work. Square roots stay exact (an auxiliary symbol `s ≥ 0, s·s = x` under the nonlinear policy), so `√8 = 2√2` is proved, not approximated. |
| D5 | Tolerance | Half a unit in the last digit of S, plus a relative slack τ (1/100 for `=`, 1/20 for `≈`). The band is sign-aware and centred on the computed value. | The same band, `|s − k| ≤ h + τ·|k|`. | **Converged.** R's rules R1 to R9 are kept, with three grafts: constant intervals (D3), enclosures (D4), and decimal-exponent factoring (D7). |
| D6 | One form or two | Form E (entailment) when every operand is exact; Form S (satisfiability) when carried intermediates are present. | Entailment only, with a "computed" symbol pinned so the counterexample shows it. | **Both, by one rule.** If any operand has an interval reading (a carried intermediate, a constant, an enclosure), use Form S: is there an admissible reading under which the stated value holds? Otherwise use Form E, with F's pinned symbols `c` and `r`, so a COUNTEREXAMPLE prints the computed value beside the stated one. |
| D7 | Literal size (`max_const_digits = 40`; Planck's constant to 9 significant figures has 51 digits) | Report ST-LIM-001 and build no check. | Rescale by a power of ten. | **Factor out powers of ten exactly** (section 7.3). A product or quotient `E = M × 10^K` is compared as `|M − S·10^−K| ≤ h·10^−K + τ·|M|`. This is an exact identity, and K is integer bookkeeping on written exponents. ST-LIM-001 remains only when a literal still exceeds 40 digits after factoring. |
| D8 | Closed compound divisor | Auxiliary `q` with `q·b = a` and `b ≠ 0`; Python first refuses an exact zero. | The same (probed: `1/(1/4.0 + 1/6.0)`). | **Converged.** No validator change. Python never folds a divisor to a literal, so the engine decides the division. |
| D9 | Pack shape | One `StemPack(mode)`. | Separate Science, Maths and CS packs. | **One `StemPack(mode)`** with modes `sciences`, `mathematics` and `computer_science`, served by three branches. The front end is shared, so there is nothing to duplicate. Branch keys and parser agent ids keep the subjects apart on receipts. |
| D10 | Request text for formal checks | An optional method `formal_checks_for(report, request_text)`. | Pass `request_text` into `formal_checks`, or compare from `checks()`. | **Optional method.** `run_packs` calls it when a pack defines it, so the `IntegrityPack` protocol and every existing pack stay unchanged. |
| D11 | Claim roles | No new roles. Each statement's function lives in the shared document. | Not addressed. | **No new roles** (section 9). A new role would ripple through about ten enumerations for no gain. |
| D12 | Who rules on fault severity | An engine failure is always INT-SUBJ-001. | The same. | **Add `failure_severity` to `FormalCheck`.** A failure of a check that relied on a reading the report did not state is INT-SUBJ-004 (warning) instead of INT-SUBJ-001 (error). Such readings: a booklet value for an unstated symbol, a symbol's identity across request and answer, a show-that target, or a step that brings in symbols no stated relation connects. |
| D13 | INCONSISTENT_PREMISES | Not addressed. | Not addressed. | **Undecided for STEM checks** (`inconsistent_is_failure=False`). A STEM check's premises are encoding devices and earlier relations. If they are inconsistent, the fault lies in an earlier line (which its own check reports) or in a domain outside the encodings. Example: `x² + 4 = 0 ⇒ x = ±2i` is correct complex-number work, so it must not become an error. |
| D14 | Fault catalogue | Derived from the grammar. | The 13 silent passes and the false errors observed before STEM support. | **F's catalogue becomes the mutation corpus.** It is the acceptance bar for stage `corpus-eval` (section 16). |

---

## 3. Architecture

### 3.1 Flow from agent text to receipt

```
specialist text (verbatim)                         request text (router)
        │                                                   │
        ▼                                                   ▼
RouterHub.receive ──► BranchRegistry.for_subject(label) ──► branch sciences | mathematics | computer_science
        │                                     (generic stays the default for unrecognised subjects)
        ▼
StemTextParser.parse_response ──┐   (the channel passes it the request text: accepts_request_text)
                                │   one memoised StemDocument per (sha256(text), sha256(request) or "", profile)
StemPack.checks / formal_checks_for ──┤        stem.document.build_document()
CorePack(reading=SI_READING) ───┘          reading view ─► spans ─► statements ─► lexer ─► Pratt parser
        │                                  ─► AST ─► scope (givens, bindings, formulas) ─► relations
        │                                  ─► planned checks (stable ids, claim ids)
        ▼
claims (offset substrings, roles)     StemPack: plan ─► stem.checks ─► stem.to_ir ─► Problem (IR 1.0)
        │                                       └─► StructuralFinding ST-* (undecided, dimension, notes)
        ▼                                                   │
TranslatorChannel.respond: envelope · hand-off · request fidelity (echo and coverage hooks) · constraints
        │                                                   ▼
        │                 _branch_checks: verify(problem, config, limits=policy_limits(fc.policy), key)
        │                 status ─► satisfied True / False / None ─► INT-SUBJ-001 / -004 / -002
        ▼
TransmissionReceipt: status, findings (claim_ids named), structural_findings (ST-*), formal_checks
(ConstraintResult per check id, signed formal_result_id), summary (counts, failed and undecided ids, ST histogram, scope tail)
        │
        ▼
router (delivered unless an identity or integrity violation REJECTS it; STEM findings are content findings)
```

### 3.2 Principles

- **P1. One reading.** One deterministic front end turns the response into a `StemDocument`
  holding:
  - statements, with offsets;
  - math spans, ASTs and quantities;
  - the symbol scope;
  - classified relations;
  - planned check ids with their claim ids.

  The STEM parser (claims), `StemPack` (checks) and `CorePack` in SI reading (prose
  arithmetic, quotation reading) all read this one document. This extends the "one sentence
  splitter" rule of `branches/README.md`: claim ids, sentence numbers and check ids cannot
  diverge. The document is memoised in an `lru_cache(64)`; `StemPack` also keeps its own
  32-entry cache of (findings, formal checks) per report and request.
- **P2. Text is data.** The front end is a hand-written scanner and a bounded Pratt parser over
  a closed grammar. Only allowlisted AST nodes are translated, and only into allowlisted IR
  1.0 nodes. Section 14 lists what is forbidden.
- **P3. The engine decides.** Python `Fraction` arithmetic only builds literals and refuses
  undefined encodings. It builds:
  - exact unit factors from the table;
  - half-widths from the written digits;
  - decimal exponents;
  - enclosure bounds.

  It refuses an exact zero divisor or the even root of a negative closed value. Every verdict
  on a stated relation is an engine result. The absolute value and the band are inside the IR
  (`ite`).
- **P4. Never silent, never over-flagged.** Ambiguity (unit symbols, implicit multiplication,
  as written versus SI) becomes a disjunction of at most 2 readings per expression and 4 per
  check, and correct work passes if any reading holds. If more readings would be needed, the
  relation is reported undecided (ST-PARSE-002). Ambiguity never becomes an error.
- **P5. STEM-scoped.** Every change of behaviour is reached only through the three STEM branches:
  - `StemTextParser`;
  - `StemPack`;
  - `CorePack(reading=SI_READING)`;
  - the STEM hub hooks.

  `CorePack()` with the default `GENERAL` reading runs the pre-STEM code path byte for byte. English,
  History, Psychology, Economics, Business Management and generic are therefore unchanged. The
  shared edits in section 11 are additive, and their defaults reproduce the pre-STEM behaviour.
- **P6. The original is verbatim.** Normalisation happens only in a reading view of the same
  length, a 1:1 character map. Claim texts are offset substrings of the original, truncated to
  the contract (4000 characters).

### 3.3 Module layout

New subpackage `src/epinoic_logic/stem/`. It is the front end and the encodings. It imports
nothing from `branches/`, `channel/`, `engine/` or `ir/`: problems leave it as plain IR data
(`dict`) that `StemPack` validates. The one module outside the package it reads is the shared
sentence splitter `adapters/history_specialist/sentences.py` (section 4.3).

| Module | Role | Stage |
| --- | --- | --- |
| `limits.py` | `StemLimits`, a frozen dataclass holding every bound (section 4.9) | core |
| `normalize.py` | reading view (1:1 map) and prose view (math masked by same-length placeholders) | core |
| `spans.py` | code, LaTeX, Unicode or ASCII math runs, verbal arithmetic, derivation lines, data lines | core |
| `segment.py` | statements: sentences (shared `sentence_boundaries` on the prose view plus STEM boundary rules), derivation lines, display rows, list items, code blocks, part labels | core |
| `lexer.py` | single-pass tokenizer | core |
| `numbers.py` | `ExactNumber`: exact value, significant figures, last place, half-width, exactness, scientific exponent | core |
| `units.py` | unit table, prefixes, dimension vectors, unit-expression parser, ambiguity table, exact SI factors | core |
| `nodes.py` | frozen AST nodes | core |
| `parser.py` | Pratt parser; implicit multiplication resolved against scope | core |
| `scope.py` | symbol bindings with provenance; recorded formulas | core |
| `relations.py` | link classification and check planning (kinds, stable ids, claim ids) | core |
| `chem.py` | chemical formula and equation parser; element and charge tallies | core |
| `boolean.py` | Boolean expressions, truth-table blocks, base-2, 8 and 16 numerals | core |
| `document.py` | `StemDocument` and the memoised `build_document` | core |
| `constants.py` | data-booklet constants table (values, accepted written forms, units, profiles, ambiguous letters) | checks |
| `enclosures.py` | exact-value table; rational enclosures for π, e and the functions | checks |
| `scaling.py` | decimal-exponent factoring (section 7.3) | checks |
| `tolerance.py` | `STEM_TOLERANCE_RULE` text; band builders | checks |
| `to_ir.py` | AST to IR 1.0 (section 7) | checks |
| `checks.py` | `PlannedCheck` builder: Forms E and S, ids, descriptions, claim ids, policy, failure severity, truncation; ST findings | checks |
| `si_reading.py` | `SI_READING` for `quant` and `CorePack` (section 12) | branch |
| `hub_hooks.py` | STEM coverage terms, echo exemption, request imperatives, word-count view | branch |

Elsewhere: `adapters/stem_specialist/parser.py` (`StemTextParser`) and
`branches/stem_pack.py` (`StemPack`), plus the additive shared edits listed under stage
`branch` in section 17.

---

## 4. Math front end: grammar and bounds

### 4.1 Reading view (`normalize.py`)

The reading view is a 1:1 character map, so it has the same length as the original and
offsets are preserved:

- U+2212 (minus) and U+2011 (non-breaking hyphen) become `-`.
- NBSP, U+2007, U+2009, U+200A and U+202F become a space. Zero-width characters (U+200B,
  U+200C, U+200D, U+2060, U+FEFF) also become a space, so a hidden character can split a token
  but never silently join two.
- U+22C5 and U+2219 become U+00B7, which is a multiplication marker in math and unit context and
  a hydrate dot in a chemical formula. U+2217 becomes `*`, and U+2126 (ohm sign) becomes `Ω`.
- U+00D7 `×` stays its own token.
- An en dash U+2013 or figure dash U+2012 is read as minus only after the start, a space, an
  operator, `(` or a relation sign, and before a digit or letter. `3–5 s` between two numbers
  stays a dash (a range: Unsupported, named), and so does `H–H`.
- Superscript digits and signs (⁰ to ⁹, ⁺, ⁻) and subscripts (₀ to ₉) are tokenised as they
  stand. Nothing is expanded. Letters of other scripts are left alone, so a Cyrillic `а` that
  looks like a Latin `a` is never read as one: the lexer rejects it.

The prose view masks every math span and every quantity carrying a unit with a placeholder of
the same length: an upper-case first character, then filler that is not a space, punctuation,
quotation mark or digit. The shared splitter can start a sentence at a masked span. It never
splits inside one, and it never sees a decimal point, prime, inch mark or quotation mark
inside one.

### 4.2 Spans (`spans.py`), extracted in this order

1. **Code.** Fenced ` ``` ` and `~~~` blocks (the language tag is kept; an unclosed fence runs
   to the end), inline `` `code` ``, and 4-space indented blocks in the `computer_science`
   profile. A code span is masked from maths and prose, and it is never parsed for meaning or
   run (ST-CODE-001 names it).
2. **LaTeX display.**
   - `$$…$$` and `\[…\]`;
   - the environments `equation`, `equation*`, `align`, `align*`, `gather` and `gather*`; an
     inner `aligned`, `split` or `gathered` wrapper is read through.

   Rows are split at `\\`, and `&` is dropped by the parser.
3. **LaTeX inline.** `$…$` and `\(…\)`, following TeX convention: the content is non-empty,
   has no leading or trailing space, closes in the same paragraph, is not followed by a digit,
   and is at most `max_span_chars` long. `\$` and an unclosed `$5 per kg` are currency.
4. **Chemical equations** (chemistry profiles): an arrow with species on both sides.
5. **Unicode or ASCII runs in prose.** A maximal run the math lexer can tokenise that
   contains a relation sign. It starts at an identifier, a number, `(`, `|` or a minus after a
   clean boundary, or at a relation sign right after a prose label (`Energy absorbed = 4 × 414
   + …`) or at the start of a line (a continuation). It stops before a prose word (three or
   more letters that are not a function name, a unit after a number, a Greek name or a name in
   scope, or a short English word such as `is`, `so`, `or`), before sentence punctuation, a
   comma or semicolon outside brackets, a quotation mark or a bracket it did not open. A run
   that opens with a bracket and holds its relation sign only inside it is read again from
   inside the bracket, up to three brackets deep. A number with a unit and no relation sign is
   kept as a `quantity` span (masked in the prose view, read as a prose value).
6. **Verbal arithmetic.** `<number> (plus | minus | times | multiplied by | divided by)
   <number> … (equals | is equal to | gives | makes) <number>`, with numbers only and no
   symbols. It is read as the same AST.
7. **Tables and data lines.** Markdown tables and bracketed data, vector and list lines
   (`[1, 2]`, `{2, 3}`) become text claims. A truth-table block (section 4.8) is recognised from
   a table's header row and rows of 0/1 or T/F. A JSON receipt shape (string keys) keeps the
   shared JSON rule.

Derivation lines are statements, not spans: a line is a derivation line when at least 60 % of
its non-space characters lie in one math span, and a line that begins with a relation sign
continues the previous line's chain (section 4.3). Markup (emphasis markers, heading lines, list
markers, block-quote marks, part labels at the start of a line) is recorded for blanking in the
math view. Every scan is linear: `$` signs are paired through a precomputed table, prose lines
are lexed in windows of at most `max_line_chars` characters, and the only regular expressions
are anchored, bounded line-start patterns.

### 4.3 Statements (`segment.py`)

A statement is one of the following:
- a sentence of the prose view;
- a derivation line;
- a display row;
- a list item;
- a code block;
- a table.

Sentences come from the shared `sentence_boundaries` with three STEM-only boundary rules:

- after `<number> <unit>.` and after a masked span followed by `.`, a space and a capital
  (also when a unit follows the masked span, `… $E = 3.5$ J. Next …`, through a bounded
  look-back of 16 characters);
- after a single lower-case letter that is a symbol in scope, followed by `.`, a space and a
  capital (`the speed is v. Then …`);
- neither rule applies to `c.` or `p.` followed by a digit (circa, page).

Part labels (`(a)`, `b)`, `(b)(ii)`, `Part (c)`, `Question 2`, Markdown headings) are recorded
as structure, not claims, and scope a part's checks. A Markdown heading, or a part label alone
on its line, starts a paragraph. A list item holding several sentences is split into them.
Statement ids are `s<paragraph>.<statement>`, both counted from 1; statements beyond
`max_statements` merge into one `s.tail`. History's splitter and its `ABBREVIATIONS` are
untouched; the wrapper lives only in `stem/segment.py`.

Since the merge with the round-7 development branch, the line rules are the generic parser's
(section 20.1): an equation continued on lines that open with `=` is one statement, label-only
lines and mark annotations are furniture, and a table is one statement per row.

### 4.4 Lexer (`lexer.py`): one forward pass, no backtracking regex

- **NUMBER.**
  - Digits with an optional decimal point.
  - A decimal comma only when 1 or 2 digits follow and no space follows outside a coordinate
    pair.
  - Thousands groups with `,`, a thin space or the LaTeX thin space `\,` (`21\,131.40`), in groups
    of exactly three, one kind of separator throughout (section 21).
  - Scientific notation: `1.2 × 10⁶`, `1.2 x 10^6`, `1.2×10^{6}`, `1.2*10**6`, `1.2e6`,
    `6.0E-3`, with a Unicode minus allowed in mantissa and exponent.
  - Base-marked integers: `FF₁₆`, `0xFF`, `0b1010`, `1010₂`, `(255)₁₀`.
- **IDENT.**
  - A Latin letter, or a Greek letter (Unicode or `\alpha` and its kin).
  - Subscripts are part of the name (`v_0`, `v₀`, `v_{max}`), and so are primes.
  - A `Δ` or `\Delta` prefix fuses into one symbol.
- **FUNC.** `sin cos tan arcsin arccos arctan sin⁻¹ cos⁻¹ tan⁻¹ ln log lg exp sqrt √ ∛`, and
  `\sin \cos \tan \arcsin \arccos \arctan \ln \log \exp \sqrt`.
- **LaTeX allowlist.**
  - Structure: `\frac \dfrac \tfrac \sqrt \sqrt[2] \left \right`.
  - Operators: `\cdot \times \div \pm \mp`.
  - Spacing: `\, \; \! \quad`.
  - Text: `\text \mathrm \operatorname`.
  - Greek letters and `\pi`.
  - Relations: `\approx \neq \ne \leq \le \geq \ge \lt \gt \Rightarrow \implies \to \rightarrow
    \rightleftharpoons \therefore`.

  Any other command makes the span Unparsed (ST-PARSE-001), with the command named.
- **OP and REL** tokens (REL also takes `≡` and `∝`), grouping `() [] {}`, COMMA, PERCENT,
  DEGREE `°`, primes `′ ″` (arc minutes and seconds or inches only directly after a number),
  ABS bars, `!`, ratio `:` between numbers, a magnification suffix `×` after a number at the end
  of an operand, and the Boolean operators `∧ ∨ ¬ ⊕` and words `AND OR NOT XOR` (the words in CS
  only).
- **UNSUP** marks the start of a construct outside the encodings, with its reason (`∫ Σ ∏ ∂ ∇
  lim d/dx \int \sum \lim \vec \mathbf \partial \binom \ldots`, matrices); **ERROR** is an
  unknown LaTeX command or a letter of another script (a confusable). The lexer never raises,
  and every token records whether space preceded it, so `m s` (metre second) and `ms`
  (millisecond) stay different.

### 4.5 Grammar (`parser.py`): Pratt, lowest to highest precedence

```
sequence  := chain ( connective chain )*        connective: ⇒ ∴ , ; or and so hence gives ... (\text{or})
chain     := expr ( relop expr ){1,12}          (a chain may open with a relop: a continuation or a prose label)
relop     := = | ≈ | ≃ | ~ | ≡ | ≠ | < | > | ≤ | ≥ | <= | >= | ⇒ | ∴ | → | ⇌ | ⇔ | \approx | \neq | \leq | \geq | \Rightarrow
             (→ and ⇌ are reaction arrows only in chemistry mode between two species lists; ⇔ is Boolean equivalence only in CS)
expr      := term ( ( + | - | ± | ∓ ) term )*
term      := unary ( ( × | · | * | / | ÷ | \cdot | \times | \div | juxtaposition ) unary )*
unary     := ( - | + | ± | ¬ ) unary | power
power     := postfix [ ( ^ | ** | superscript ) exponent ]           right-associative
exponent  := signed integer literal (|n| ≤ 12; up to 1000 over a closed base) | ½ | 1/2   (½ is read as a square root)
postfix   := primary [ % | ° | ! | × (magnification) | base subscript ]
primary   := number [unit] | symbol | func_app | ( expr ) [unit] | { expr } | [ expr ] (concentration in chemistry)
           | \frac{expr}{expr} | \sqrt{expr} | √primary | √(expr) | | expr | | ratio
unit      := unit_expr                 (after a space, or \text{…}/\mathrm{…}, Ω, °C; the unit must end the operand:
                                        next is an operator, a relation, a close, a separator or the end)
ratio     := number : number           (only directly beside a relation sign: a:b = c:d)
func_app  := FUNC ( (expr) | {expr} | primary )
```

A glued unit (`1.5kg`) is read only for a common multi-letter unit that does not also split
into names in scope, so `2as` stays `2·a·s`. After a known unit atom, an unknown atom with an
exponent (`yr⁻¹`) is kept as an unknown unit (ST-UNIT-001). A broken bound or an unreadable
operand makes that operand an error (ST-LIM-001 or ST-PARSE-001) and the parser resynchronises
at the next relation sign; an unknown LaTeX command or a confusable letter makes the whole span
Unparsed (ST-PARSE-001, the command named). Nothing raises out of `parse_math`.

A power whose exponent is no integer is one value, a `RealPower`, when its base and its exponent
are both closed and carry no unit (`10^(−8.2)`, `10^(8.2 − 7.8)`, `(3465/250)^(1/6)`): figures,
signs, brackets and `\frac` in the exponent, no symbol, unit, angle or per cent in either
(section 21). So is an integer power beyond 12, up to 1000, of a closed base with no unit
(`(1 + 0.065/12)^{-60}`, `1.003^{144}`, `2^{20}`).

Unsupported, each as a named `Unsupported(reason)` node (the relation that holds one is
ST-UNDEC-001 with the reason):
- a symbolic power, a non-integer power of anything but a closed value with no unit, an integer
  power beyond 12 of anything but a closed value with no unit (and any beyond 1000), a cube root;
- `!`;
- `Σ` (except over integer bounds with at most 24 terms, which is read as its terms), `∫` and
  `lim`;
- `d/dx` and `dy/dx`;
- `f′(x)` and `f''(x)` (derivative; the node keeps the function's name and argument);
- vectors in bold, arrows or `\vec`;
- matrices, and a tuple `(x, y)`;
- `i` beside a number or `±` (complex number);
- asymptotic notation (`O(…)`, Computer Science);
- an evaluation bracket `[F(x)]₀²` and infinity.

### 4.6 Implicit multiplication and scope

- **Segmentation.** A letter run inside a math span is segmented by the longest prefix over
  the names in scope:
  - declared symbols;
  - formula left-hand sides;
  - the STEM name table (`parser.STEM_NAMES`: `KE PE GPE EPE EMF emf pH pOH pKa pKb Ka Kb Kw
    Kc Kp Mr Ar NA Ek Ep RMM RFM NPP GPP SV HR BMI RQ`);
  - function names.

  A name pre-pass (`scope.prescan_names`) collects the names a text declares before anything
  is parsed: a letter run directly before `=` or `≈` at the start of a relation (`PV = 5000`),
  and every subscripted, primed or Δ-prefixed symbol and Greek letter. With scope
  `{u, v, a, t}`, `at` is `a·t`; `mgh` is `m·g·h`; `½mv²` is `½·m·v²`; `2πr` is `2·π·r`. A run
  that matches no name splits into single letters, except an all-capital run of three or four
  letters (`GPP`), which is one name; a run longer than `max_letter_run` (12) is one unknown
  symbol. If two segmentations both match the scope, both are kept as readings (at most 2);
  with more readings, ST-PARSE-002.
- **Numbers, units and symbols.**
  - A number followed by a space and a unit token is a Quantity when the unit token ends the
    operand.
  - A number directly followed by a declared symbol is multiplication.
  - A letter at the start of an expression is a symbol: in `m = 2.0 kg`, `m` is a symbol and
    `kg` a unit.
- **Bindings** (`scope.py`): `symbol → [Binding(value, number, unit, source, statement_id)]`.
  Sources:
  - `request`: the request text (read by the same front end, bound first);
  - `given`: a `Given:`, `Data:` or `Known:` statement;
  - `let`: `let`, `take`, `taking`, `using`, `with x = …`;
  - `result`: the final value of the answer's own chain;
  - `statement`: a bare value binding elsewhere in the answer (including a value the answer
    states for a constant);
  - `root`: a stated solution of an equation in the symbol (`x = 5 or x = −2` is no rebinding);
  - `substitution`: a value substituted into a symbol bound nowhere else. Such a binding only
    widens what a later substitution may match and is never a premise of its own check.

  A value after `at`, `when` or `if` in the answer (`At x = 1:`) is an evaluation point, not a
  binding. The front end never adds a constant value to scope; see D3 for the guarded booklet
  reading in checks. Rebinding adds a binding (ST-SCOPE-001 info when the value differs beyond
  rounding). A substituted value passes if it matches any binding of that symbol, so part (b)
  reusing part (a)'s letter is never flagged.
- **Formulas.** A left-hand symbol or `f(x)` maps to an expression, recorded from definition
  and law links.

### 4.7 Relations (`relations.py`)

A chain `L0 op1 E1 … opk Ek` may continue across lines. Each link is classified by its two
endpoints: *value* (a single number or quantity), *closed* or *numeric* (no symbol, possibly with
units), *bound* (every symbol has a binding) or *symbolic* (a symbol with no binding). The
link's claim ids are the statements that hold its two endpoints. Every recognised relation ends
in one outcome: `check`, `binding`, `formula`, `context` or `undecided` (section 1).

| Link | Example | Outcome |
| --- | --- | --- |
| symbolic = symbolic, first link with a lone left-hand side | `F = ma`, `a = \frac{v-u}{t}` | law or definition: recorded as a formula, not checked (its truth is out of scope) |
| symbolic → symbolic later, or across `⇒`, `∴`, "rearranging", "so", "gives", or a display row | `v² = u² + 2as ⇒ s = (v² − u²)/(2a)` | `stem-alg` |
| symbolic → numeric | `(v − u)/t = (20 − 0)/4.0` | `stem-sub` (substitution fidelity) |
| numeric → value, numeric → numeric | `(20 − 0)/4.0 = 6.0` | `stem-eq` |
| value → value, both with units | `72 km h⁻¹ = 20 m s⁻¹` | `stem-cnv` |
| `<`, `>`, `≤`, `≥`, `≠` between values or bound symbols | `T₁ = 300 K > T₂ = 250 K` | `stem-cmp` |
| prose value after `therefore`, `so`, `hence` or "the answer is", against the chain's final value | "The acceleration is therefore 6.0 m s⁻²." | `stem-res` |
| equation, then a stated root set | `x² − 5x + 6 = 0 ⇒ x = 2 or x = 3` | `stem-sol` |
| an equality with an application of an exponential model (the model's letter glued to its bracket) | `P(t + 1) = P₀e^(k(t + 1))` after `P = P₀e^(kt)` | `stem-mod` (section 21, item 5) |
| answer `Given:` binding against a request binding of the same symbol, or a request quantity of the same dimension | `Given: v = 20 m s⁻¹` | `stem-giv` |
| final value against a show-that target in the request | "Show that n ≈ 2.0 mol" | `stem-tgt` |
| chemical equation | `2H₂ + O₂ → 2H₂O` | `stem-chem` |
| Boolean equivalence | `¬(A ∧ B) = ¬A ∨ ¬B` | `stem-bool` |
| truth-table block | header `A B A∧B` | `stem-tt` |
| based numerals | `FF₁₆ = 255` | `stem-base` |
| a relation whose endpoints contain Unsupported | `f′(x) = 3x + 2` | ST-UNDEC-001 (reason) |
| a numeric relation whose operands include a symbol with no binding and no admissible booklet reading | `E = hf = 3.3e-19` with f unbound | ST-UNDEC-002 |

A bare value binding with no relation stated (`The speed is 15 m/s.`, `m = 2.0 kg`) is a
binding, not a check. That keeps the existing Physics fixtures free of new findings. An order
chain is read (`T₁ = 300 K > T₂ = 250 K`), a factorisation inside a chain is checked as an
identity, a ratio equality `a:b = c:d` is compared by cross products, and a function or
derivative evaluated at a point is checked against the stated formula when one is recorded.
An evaluation of a function at a value (`f(2) = …`, and `N(15) = …` for a letter the text defines
as a function, `N(t) = …` or a model; section 21, item 5) is no step from the preceding line, and a
step over a function of an unknown is ST-UNDEC-001. Complex values are named undecided.

Check ids are planned here, deterministically, in document order: `stem-eq-1`, `stem-eq-2`,
… per kind. Parser and pack therefore agree on them. A planned check that `to_ir` cannot
encode keeps its id: the undecided finding names the id instead of a check being built.

### 4.8 Chemistry and Computer Science readings

- **Chemistry** (`chem.py`, chemistry, biology, ESS and the multi-science `stem` profiles):
  - Formulas with element symbols from the periodic-table symbol list (symbols only, no masses),
    counts (subscript or digit: `H₂O`, `H2O`, `H_2O`, `H_{2}O`), parenthesised or bracketed
    groups nested at most 3 deep, and hydrate dots (`CuSO₄·5H₂O`).
  - Charges `²⁺`, `⁻`, `^{2+}`, `^-`, and a glued ASCII charge at the end of a species
    (`Fe2+`, `SO42-`, `[Cu(NH3)4]2+`); electrons `e⁻`.
  - State symbols `(s) (l) (g) (aq)` are read and ignored.
  - Arrows `→`, `⇌`, `->`, `<=>`, `\rightarrow` and `\rightleftharpoons`; coefficients as
    integers, decimals or fractions (`½O₂`, `1/2 O2`).

  Isotope notation, an unknown element symbol and a bound exceeded give ST-CHEM-001. The module
  reads structure only; whether an equation balances is decided by the engine.
- **Computer Science** (`boolean.py`):
  - Boolean expressions with `∧ ∨ ¬ ⊕`, `AND OR NOT XOR`, `·`, `*` and `+` in Boolean context,
    and overbar or prime negation. Variables are single capital letters; a glued run of
    capitals (`AB`) is their AND. Precedence, lowest first: equivalence (`=`, `≡`, `⇔`), OR,
    XOR, AND, NOT. Boolean context: the profile is Computer Science and the span uses a Boolean
    operator, or every identifier is a single capital letter and every number is 0 or 1.
  - Truth tables of at most 5 inputs (32 rows), from a Markdown table or a plain block whose
    header names the inputs and one or more output expressions.
  - Based numerals (`FF₁₆`, `0xFF`, `0b1010`, `1010₂`; a hexadecimal numeral may open with a
    digit, `2A₁₆`).
  - Code is never read for meaning (ST-CODE-001 info).

### 4.9 Bounds (`StemLimits`)

| Bound | Value | When exceeded |
| --- | --- | --- |
| response characters | 400,000 (the report contract) | the contract rejects it first |
| math span characters | 2,000 | ST-LIM-001; the span stays a text claim |
| tokens per span | 400 | ST-LIM-001 |
| chain links | 12 | links after the 12th: ST-LIM-001 |
| AST nodes per expression | 256 | ST-LIM-001 |
| AST depth | 24 (checked before each descent; IR depth after encoding stays under 40) | ST-LIM-001 |
| integer power | \|n\| ≤ 12; over a closed base with no unit, \|n\| ≤ 1000 (one value; beyond about 10^±300 it is not computed) | ST-UNDEC-001 |
| scientific exponent | \|e\| ≤ 99 | ST-LIM-001 |
| written digits per number | 30 | ST-LIM-001 |
| readings per expression / per check | 2 / 4 | ST-PARSE-002 |
| bindings per symbol | 8 | the oldest are dropped from matching; ST-SCOPE-001 info |
| symbols per check | 48 (the IR limit is 64) | ST-LIM-001 |
| interval operands per Form S check | 6 | ST-LIM-001 |
| STEM checks per report | 128 | ST-LIM-002 names the count and the first unchecked ids |
| math spans (and display rows) read per report | 1,024 | the rest stay text claims; ST-LIM-002 names how many were not read |
| statements (claims) | 512 (the report contract) | overflow merges into `s.tail` with the unresolved-issue text the bus turns into INT-REQ-013 |
| chemistry species per side; atoms per species; group nesting | 16; 999; 3 | ST-CHEM-001 |
| truth-table inputs | 5 | ST-UNDEC-001 |
| digits of a based numeral | 64 | not read as a based numeral (the scan stays bounded) |
| letters of one run segmented for implicit multiplication | 12 | the run is one unknown symbol |
| recorded formulas an algebra step includes | 8 | no further formula is added as a premise |
| digits of one IR literal after factoring | 40 (`scaling.MAX_LITERAL_DIGITS`) | ST-LIM-001 |
| IR bounds per check (checks stage) | 48 symbols, 128 premises, 2,000 nodes, depth 40, 32 n-ary arguments, polynomial degree 24 (`to_ir.IR_LIMITS`) | ST-LIM-001 |
| characters of a prose line the run finder scans in one pass | 20,000 | scanned in windows |
| document cache | 64 entries | LRU eviction |
| enclosure arguments | trig \|x\| ≤ 10⁹ rad, reduced modulo 2π; ln and log10 over [10⁻¹⁰⁰, 10¹⁰⁰]; exp over \|x\| ≤ 700; ≤ 400 series terms | ST-UNDEC-001 |

The front-end bounds are fields of `StemLimits` (`stem/limits.py`). The checks stage keeps its
IR bounds in `to_ir.IR_LIMITS` and `scaling.MAX_LITERAL_DIGITS`, and the enclosure routines
their argument bounds in `enclosures.py`.

---

## 5. Numbers, significant figures and tolerance

### 5.1 Exact numbers (`numbers.py`)

An `ExactNumber` holds:
- the exact `Fraction` value as written (scientific notation expanded exactly);
- the significant figures: leading zeros are not significant, trailing zeros after the point
  are, and scientific notation counts the mantissa;
- `last_place`, the power of ten of the last written digit;
- `half_width = ½·10^last_place`;
- `exact`: true when the written form has no decimal point anywhere (an integer, a vulgar
  fraction, a based numeral, an integer mantissa). This describes the written form only: a
  number that carries a unit is a measurement, and the checks never put it in exact mode
  (`200 km ÷ 3 h = 67 km h⁻¹` is measured data, fixture `stem-phys-030`);
- the decimal exponent, for scaling.

`scan_number` is the one number reader of the front end (the ledger's figure extraction uses
it too). It accepts only ASCII digits and checks the digit and exponent bounds before any
integer is built, so `10^999999` costs one linear scan and yields a named error.

A bare `0` is exact zero. `0.0` has a half-width of 0.05.

**Trailing zeros of an integer** (no decimal point): they are significant only up to the
smallest significant-figure count among the expression's measured operands, with at least 1.
So `= 1200` with 2-s.f. operands has h = 50. With no measured operands, `h = ½·10^k` for k
trailing zeros.

### 5.2 The STEM tolerance rule (`tolerance.py`; repeated in every check description)

Let E be the written expression, S the written value it is said to equal, and C the exact
value of E. Values are compared under the reading in force (section 6.4).

- **R1 Half-width h(S).** Half a unit in the last written digit of S's mantissa, times its
  power of ten: 5.0 gives 0.05; 1.20 × 10³ gives 5; 3/4 or a surd gives 0. Section 5.1 gives
  the integer trailing-zero rule.
- **R2 Relative slack τ.**
  - `=` with any measured operand (written with a decimal point, in scientific notation, or
    with a unit) or a decimal S: 1/100. This covers constants written to fewer digits than were
    used (9.8 against 9.81 is 0.1 %; 3.00 × 10⁸ against 2.998 × 10⁸ is 0.07 %). It stays well
    below the error classes this design must catch (a wrong formula, substitution, digit or
    power of ten, typically 5 % or more).
  - `≈`, `≃` or `~`, or `=` after "approximately", "approx.", "about", "roughly", "estimate",
    "around" or "nearly": 1/20.
  - **Exact mode** (every operand and S exact, and `=`): τ = 0 and h = 0. So `7/3 = 2` fails,
    while `√2 = 1.41` (S is a decimal) passes under R1.
- **R3 Interval readings.** These operands may take any value in an interval:
  - a carried intermediate: an operand whose written value is the answer's own earlier result
    (traced by symbol, or by an equal numeral with the same unit), or one marked approximate,
    ranges over `[w − h(w), w + h(w)]`;
  - a written constant: a literal matching a table constant at its written precision ranges
    over the hull of `[w − h(w), w + h(w)]` and the booklet value (D3a);
  - an unbound standard-constant symbol with an admissible booklet reading ranges over the
    hull of its accepted values, for example g in [9.80, 9.81] (D3b, warning on failure);
  - an enclosure symbol (π, e or a function value) ranges over its enclosure (D4).

  Given data, constants whose value the answer states, and exact coefficients are taken as
  written.
- **R4 Band.** The check passes iff there are operand values under R3 with `|C − S| ≤ h(S) +
  τ·|C|`. The band is symmetric around the computed value and sign-aware, because `|·|` is
  encoded with `ite`. Negative values and zero need no special case beyond R1's exact zero.
  When a single written value is set against another (a conversion, `72 km h⁻¹ = 20 m s⁻¹`),
  the left value's own half-width is added to the band.
  - **Form E** (no interval operand): an entailment. Symbols `c` and `r`; premises
    `C_DEF: c = ⟦E⟧` and `R: r = S`, plus auxiliaries and guards; conclusion `STATED: |c − r| ≤ h
    + τ·|c|`; expected ENTAILED. A COUNTEREXAMPLE's model shows `c` beside `r`. The core contains
    `C_DEF` and `R`, so E108 (vacuous) cannot arise.
  - **Form S** (one or more interval operands): a satisfiability query. Interval premises
    `X_LO` and `X_HI`, the definitions, and `BAND` as a premise; expected SATISFIABLE.
    UNSATISFIABLE means no admissible reading of the rounded values gives the stated value, and
    the core names the intervals and the band. The description says exactly that, so
    SATISFIABLE is never read as "true". Builder invariant: every symbol is pinned,
    interval-bounded, or an auxiliary defined by a premise, so a free symbol can never make
    Form S vacuously satisfiable.
- **R5 Conversions.** `2.5 km = 2500 m`, `72 km h⁻¹ = 20 m s⁻¹` and `25 °C = 298 K` use τ = 0
  (1/20 when the conversion is marked approximate). The factors are exact, so the only slack is
  the half-widths of the two written values, `|C − S| ≤ h(S) + h(C)` in SI. Unknown unit atoms
  that are the same on both sides cancel; otherwise an unknown unit is checked as written only,
  at warning severity.
- **R6 Comparisons** (`<`, `≤`, `>`, `≥`, `≠`) between written values are exact, with no slack,
  as in quant's series checks.
- **R7 Substitution fidelity.** A substituted numeral w matches a binding b iff `|w − b| ≤ h(b) +
  h(w)`, in b's written unit or in SI. The two readings are a disjunction, so 2500 and 2.5
  both match 2.5 km. τ = 0.
- **R8 Restated result.** A prose value S′ matches the chain's final value S iff `|S − S′| ≤
  h(S) + h(S′)`, in SI, with τ = 0.
- **R9 Prose relations** (per cent, fold, share and total) keep quant's `TOLERANCE_RULE`: 5 %
  and the 0.5-point floor. In SI reading the band is made sign-aware (section 12). Those
  statements are approximate by nature; equations are precise statements.
- **R10 Roots.** A stated decimal root r of a polynomial equation passes iff a real root lies
  in `[r − h(r), r + h(r)]` (Form S). An exact root passes iff it satisfies the equation exactly
  (linear substitution, D1).

**The observed case.** C = 5, S = 6.0, h = 0.05, τ = 1/100, and |5 − 6| = 1 > 0.05 + 0.05, so
the check fails. Under quant's 5 % rule it would have passed anything from 4.76 to 5.26.

**Short form** (`tolerance.SHORT_RULE`, the `[rule]` suffix of every description, 300
characters or fewer): "STEM tolerance: S must lie within h + τ·|C| of the value C computed
from the written expression; h is half a unit in S's last digit; τ is 1% for '=', 5% for
'≈'/about, 0 for conversions, comparisons and exact work; rounded intermediates, constants and
functions range over their intervals." The full rule is `tolerance.STEM_TOLERANCE_RULE`.

---

## 6. Units and dimensions (`units.py`)

### 6.1 Table

- **Dimensions.** A 7-tuple of ints over (m, kg, s, A, K, mol, cd), plus an angle flag.
- **Base units.** m, g (kg is the base), s, A, K, mol, cd.
- **Derived units.** N, J, W, Pa, Hz, C, V, Ω and ohm, F, H, T, Wb, S, Bq, Gy, Sv, lm, lx, rad, sr.
- **Accepted units.**
  - Time: min, h, d.
  - Volume: L and l, dm³, cm³.
  - t (tonne): ESS and Design Technology only.
  - Energy and mass: eV, u and Da.
  - Length: Å, AU, ly, pc.
  - Pressure: bar, atm, mmHg.
  - Angle: °, ′, ″.
  - Ratio: %, ppm.
- **Affine units.** °C and °F.
- **Spelled-out units.** metre and meter, seconds, newtons, "metres per second squared",
  "per cent", and so on.
- **Prefixes.** Q R Y Z E P T G M k h da d c m µ/μ/u n p f a z y r q, applied by longest
  match, and only to units that take a prefix. SI binding applies: `ms` is a millisecond, `m s`
  is metre second, and `Nm` and `N m` are newton metre.
- **Unit expressions.** Space, `·`, `*`, `/`, and exponents `⁻²`, `^-2`, `^{-2}`, `**-2`. For
  example `m s⁻²`, `m/s/s`, `J mol⁻¹ K⁻¹`, `mol dm⁻³`, `kg·m/s`, `kJ mol⁻¹`. After a number, an
  exponent written in ASCII and glued to its atom is read too: a hyphen-minus or plus and one digit
  (`m s-1`, `mol dm-3`, `J kg-1 K-1`), one digit 2 to 9 after an atom of two or more letters (`cm3`,
  `mol2 dm-6`) or after a slash (`m/s2`, `kg/m3`); never more digits (`300 K-273`), a spaced sign, a
  sign followed by an atom of the same dimension (`5 m-3 m`), or a one-letter atom's digit right after
  the number (`2 m2`, `H2`), which keep their reading (section 21, item 6).
- **Factors.** SI conversion factors are exact `Fraction`s. Where no exact rational factor
  exists (the degree, which is π/180 rad, and the parsec) the factor is `None` and the unit still
  has a dimension. The affine offset (273.15 for °C, 459.67 for °F) is applied only in explicit
  °C/K conversion checks. It is never applied to a Δ-prefixed symbol, or to a quantity the
  sentence calls a change, difference, rise or fall. Inside a compound unit (`J kg⁻¹ °C⁻¹`) °C
  is a temperature interval, like K.
- **Not in the table.** `yr` (a known gap: ST-UNIT-001, see docs/STEM_RESULTS.md) and any unit
  not listed above.

### 6.2 Where a unit is read

A unit is read only after a number, after a closing group that contains a number, or inside
`\text{}` or `\mathrm{}`. Elsewhere a letter is a symbol.

### 6.3 Ambiguity table (one reading per profile; an ambiguity that matters to a check becomes two readings)

| Token | After a number | Elsewhere |
| --- | --- | --- |
| g | gram | symbol (gravity) |
| M | molar in chemistry and biology; molar or mega in physics (two readings, ST-UNIT-002 info) | symbol |
| h | hour | symbol (height, Planck) |
| t | tonne in ESS and Design Technology only | symbol |
| A | ampere (never the article inside math) | symbol |
| K / k | kelvin / kilo- only as a prefix | symbol |
| T, F, L / l | tesla, farad, litre | symbol |
| ms⁻¹ (a glued two-unit token with a negative exponent) | two readings: per millisecond (SI binding) and the writer's evident metre per second | — |

### 6.4 Readings: as written or SI

- Every quantity in the link carries a unit, or is a symbol bound with a unit: compare **in
  SI only**. So `2.0 km / 4.0 s = 0.5 m s⁻¹` fails, as it should.
- Some operands are bare numbers and some carry units: **disjunction {as written, SI}**. So
  `v = 72 km h⁻¹ ÷ 3.6 = 20 m s⁻¹` (3.6 is a bare factor) and `4.5/6.0 × 100 = 75 %` both pass.
- No operand carries a unit: compare as written, and S is read both as its number and in SI
  (`20 × 25 = 0.5 km` passes in SI).
- One exception: a lone power of ten with no unit (`10^(−8.2)`, `10^(−7)`) set against a value in a
  unit of concentration is the antilogarithm of a concentration scale, the concentration in mol dm⁻³
  (the unit pH, pOH, pKa and pKb are defined in), compared in SI only. Read as a bare number in SI it
  would match a stated value 10³ times too small, the factor an exponent 3 too small reproduces
  (section 21, item 1).
- An unknown unit word: ST-UNIT-001 warning. The relation is checked as written only, with
  `failure_severity="warning"`.

### 6.5 Dimension checks (deterministic integer-vector arithmetic; warnings only)

- **ST-DIM-001.** The two sides of a stated relation have different dimensions, where every
  operand's unit is read unambiguously or is a bound symbol's unit. Example: `a = (v − u)/t =
  5.0 m s⁻¹` with v in m s⁻¹ and t in s.
- **ST-DIM-002.** A sum or difference of terms with different dimensions.
- Bare numbers are "unitless as written", not dimensionless, so they never trigger a
  dimension finding.
- Dimension findings are warnings because unit reading is the least certain part of the
  front end. The arithmetic check of the same link is still built and decided by the engine.

---

## 7. IR translation (`to_ir.py`): IR 1.0, no schema change

### 7.1 Sorts and literals

- **Sorts.** Real for physical and mathematical values. Int for stoichiometric counts, based
  numerals and truth-table rows. Bool for CS logic.
- **Literals.** Exact: an `a/b` text, an integer, or a decimal (`RealConst` accepts all three).
  Scientific notation is expanded exactly, after factoring (7.3).

### 7.2 Symbols

- Names map one-to-one into `^[a-z][a-z0-9_]{0,63}$` (`to_ir.ir_name`): v → `s_v`, V →
  `s_cap_v`, v₀ → `s_v_0` (the lexer names it `v_0`), Δv → `s_delta_v`, θ → `s_theta`, f′ →
  `s_f_prime`, with a numeric suffix on collision. Per-reading copies carry `_r2`, `_r3`.
- `Symbol.meaning` carries the original token and what it stands for.
- Auxiliaries are `q_<n>` (quotient), `p_<n>` (power base), `sq_<n>` (root), `enc_<n>`
  (enclosure), `x_<n>` (interval operands), `w_<n>` (substituted values), `root_<n>`, `k_<n>`,
  `t_<el>_<l|r>` (balance tallies), `o_<row>_<col>` (truth-table outputs), and `c`, `r`, `l`
  (the compared values). User symbols always start with `s_`, so they never collide with these.

### 7.3 Decimal-exponent factoring (`scaling.py`)

Each subtree is normalised to `(mantissa AST, integer exponent K)`:
- products and quotients add and subtract exponents;
- integer powers multiply them;
- sums align to the smallest exponent of their terms, scaling the other mantissas by exact
  powers of ten.

The stated value is scaled by the same exact factor, `S′ = S·10^−K`, `h′ = h·10^−K`. Then
`|C − S| ≤ h + τ·|C| ⇔ |M − S′| ≤ h′ + τ·|M|`, because 10^K > 0. So `h c / λ` with h =
6.62607015 × 10⁻³⁴ is decided with small literals. `notes` records "decimal exponent factored:
10^K". ST-LIM-001 is reported only when a literal still has more than 40 digits after
factoring.

### 7.4 Node encodings

| Construct | Encoding | Policy |
| --- | --- | --- |
| Quantity | literal × exact SI factor, folded into the mantissa and exponent | linear |
| `+ − unary−` | `add` (n-ary, flattened up to 32 arguments, nested beyond), `sub`, `neg` | linear |
| `× · *` and juxtaposition | `mul` | linear if at most one factor is not closed |
| `a / b`, b a single literal | `div` (validator policy satisfied) | linear |
| `a / b`, b closed but compound | auxiliary q: `Q_DEF q·b = a`, `GUARD b ≠ 0`. Precheck: b exactly 0 gives ST-UNDEF-001 and no check; a closed b whose admissible values include 0 gives ST-UNDEC-001 | linear |
| `a / b`, b contains symbols | `Q_DEF q·b = a`, `GUARD b ≠ 0` (grounded `assumption`). Never a `div` by a variable (E202) | nonlinear |
| `xⁿ`, 2 ≤ n ≤ 12 | `mul` of n copies; a compound base first gets `p = x` | linear if x is closed |
| `x¹`, `x⁰` | x; `1` with `GUARD x ≠ 0` (0⁰ gives ST-UNDEF-001) | — |
| `xⁿ`, n < 0 | `q·x^|n| = 1`, `GUARD x ≠ 0` | linear if x is closed |
| `√x`, `x^½` | `sq ≥ 0`, `sq·sq = x`. Precheck: a closed negative x gives ST-UNDEF-001 | nonlinear |
| `bⁿ`, b closed with no unit, n an integer beyond 12 and up to 1000 (`RealPower`) | its exact value when it fits one literal (`2^{20} = 1048576`; a negative base takes the sign of n's parity); otherwise the outward-rounded interval power of b (`Interval.power`, cross-checked against `math.pow`), which forces Form S; a value beyond about 10^±300 is ST-UNDEC-001 and a zero base under a power that is not positive ST-UNDEF-001; an algebra step that holds the enclosed form is ST-UNDEC-001 | linear |
| `b^x`, b and x closed with no unit, x no integer (`RealPower`) | its exact value when it is rational (`16^(3/4) = 8`: b's numerator and denominator are exact q-th powers for x = p/q); otherwise an enclosure symbol `enc` of `exp(x·ln b)` for b > 0 (grounded `arithmetic_fact`, cross-checked against `math.pow`), which forces Form S, and an algebra step that holds one is ST-UNDEC-001. `0^x` with x > 0 is 0; a base that is zero under an exponent that is not positive gives ST-UNDEF-001, one that is or may be negative ST-UNDEC-001 (no real power is chosen) | linear |
| `B^X`, B e (mathematics and Computer Science readings) or a positive rational, X a polynomial in symbols with rational coefficients, in a model evaluation only (`stem-mod`) | with X = c + Σ qᵢ·mᵢ: the closed factor B^c (exact or enclosed) times Π uᵢ^(qᵢ/sᵢ), one positive variable uᵢ = B^(sᵢ·mᵢ) per base and monomial (`U_POS uᵢ > 0`, or `U_LO`/`U_HI` the enclosure of B^(sᵢ·range) when every symbol of mᵢ has stated values; grounded `arithmetic_fact`). A relaxation: every real solution gives such uᵢ, so only UNSATISFIABLE decides; Form S | nonlinear |
| `\|x\|` | `ite(x ≥ 0, x, −x)` | linear |
| `n %` | n/100 (SI reading); n (as written) | linear |
| `±`, `∓` inside a formula | the sign of the reading: `eq` and `sub` require both choices (AND); a step's relations take either (OR); roots expand to two | as the operands |
| `value ± uncertainty` | an interval binding | — |
| ratio `a:b = c:d` | `a·d = b·c` over closed terms | linear |
| exact-table function | the exact value (rational, or a surd through `sq` of 2 or 3): sin, cos and tan of multiples of 30° and 45° (and the same angles as rational multiples of π), log₁₀ and log_b of exact powers, ln 1, exp 0, inverse functions at table values | as the surd |
| other sin, cos, tan, arcsin, arccos, arctan, ln, log10, exp of a closed argument; π; e | enclosure symbol `enc` with `ENC_LO ≤ enc ≤ ENC_HI` (grounded `arithmetic_fact`, note "enclosure computed by the STEM pack; the engine decides the stated relation over every admissible value"); forces Form S | linear |
| a function of a non-closed argument | ST-UNDEC-001 ("function of an unknown") | — |
| Boolean `∧ · AND`, `∨ + OR`, `¬ ′ overbar NOT`, `⊕ XOR` | `and`, `or`, `not`, `not(iff)` | — |
| based numeral | `IntConst` of its value | — |

### 7.5 Enclosures (`enclosures.py`)

- **Method.** Interval arithmetic over exact `Fraction` endpoints, every operation rounded
  outward to 192 significant bits, so the true value always stays inside. Series with explicit
  remainder bounds: Machin's formula for π, the exponential series after halving the argument,
  the inverse-hyperbolic-tangent series for the logarithm after reduction by powers of two,
  Taylor series for sine and cosine after reduction modulo 2π, and Euler's accelerated series
  for the arctangent. The result is `[lo, hi]` with `hi − lo ≤ 10⁻¹⁵·max(1, |mid|)`; bounds are
  written with 25 significant digits.
- **Cross-check.** The routine checks `lo ≤ libm(x) ≤ hi`, within 10⁻⁹ relative, using the
  standard `math` module. A mismatch gives ST-INTERNAL-001 and no check. `math` is used for
  nothing else.
- **Bounds.** Iterations and argument ranges are bounded (section 4.9). Outside a function's
  domain (the logarithm of a non-positive value, arcsin of 1.5, the tangent at a pole) the
  relation is ST-UNDEF-001; beyond an argument bound it is ST-UNDEC-001.
- **Angles.** An argument written with `°` is in degrees; an argument holding π is in radians;
  otherwise the angle is ambiguous and two readings are built, degrees and radians. The result
  of an inverse function is likewise read in both units.

### 7.6 Grounding of premises (provenance the engine reports, never judges)

| Premise | Grounding |
| --- | --- |
| a value located in the request text | `task_setting`, `verified=True` (located deterministically) |
| the report's own figures, `C_DEF`, `R`, `W`, `L_DEF`/`R_DEF` of compared values, and a carried intermediate's rounding interval | `supplied_text`, `verified=True`, note "figure stated in the report itself" (quant's convention) |
| a stated law (`FORMULA`), or the preceding relation used as an algebra premise (`PREV`) | `specialist_inference` |
| guards (`GUARD_*`) and step side conditions (`SIDE_ROOT`, the principal root) | `assumption` |
| auxiliary definitions (`Q_DEF`, `S_SQ`, `P_DEF`), tallies, enclosures (`ENC_*`) and a written constant widened to its booklet value (D3a) | `arithmetic_fact`, note "encoding device: defines the auxiliary as the written expression; not a claim of the report" (enclosures: "enclosure computed by the STEM pack; the engine decides the stated relation over every admissible value") |
| a booklet value for an unstated symbol (D3b) | `assumption`, with a note that the STEM pack supplied it and the report did not state it |

The engine then lists laws, guards, side conditions and supplied constants in
`ungrounded_dependencies`. A passing check therefore never hides what it relied on.
Since engine 0.4.0 (policy 2026.10-v4) a premise of a task or source kind that no check in
this process verified is an unverified dependency whatever its kind, so the encoding devices
grounded `arithmetic_fact` above are listed in `unverified_dependencies` of the STEM results that
rely on them. No STEM decision reads the dependency lists: a STEM check's finding rests on the
engine status of its own encoding, under the tolerance rule.

### 7.7 Problem fields

- `problem_id`: `stem-<kind>-<report>-<n>`, at most 128 characters; a long one is cut and
  given a 12-character sha256 suffix.
- `claim_id`: `<report_id>:<first statement id>`, bounded the same way.
- `query`: `entailment` (Form E, truth tables), or `satisfiability` (Form S, Boolean
  identities).
- `notes` (at most 4,000 characters): the scope statement `STEM_SCOPE` first; "policy:
  nonlinear" when used; "decimal exponent factored: 10^F" when a frame other than 0 is used;
  the readings in force.

`notes` is part of the problem digest, so the binding covers them.

### 7.8 What is never encoded

- Truth of a law or a datum.
- Unit correctness beyond section 6.5 and the explicit conversion checks.
- Calculus: derivatives, integrals, limits, series.
- Σ with symbolic bounds.
- Vectors, matrices and complex numbers.
- Factorials and combinatorics with `!`.
- Symbolic powers, non-integer powers of anything but a closed value with no unit (a closed one is
  decided exactly when its value is rational, else through an enclosure, section 21), and integer
  powers beyond 12 of anything but a closed value with no unit. A power of e or of a positive rational
  with an exponent in symbols is read only inside a model evaluation (`stem-mod`, section 21, item 5),
  through positive variables that can refute a link but never prove it for every value.
- A function of an unknown (an exponential model applied to an argument is the one reading, `stem-mod`;
  no algebra step is read over an application of a letter the text defines as a function, section 21,
  item 5).
- Probability distributions.
- Asymptotic notation.
- Code behaviour.
- Diagram or graph readings.
- Molar masses from formulas (that would be our data; it goes to the evidence service).

Each of these, when stated as a relation, is ST-UNDEC-001 with its reason.

---

## 8. Checks, finding codes and severities

### 8.1 Engine checks (`stem.checks.PlannedCheck`, converted to `FormalCheck` by `StemPack`)

New `FormalCheck` fields, all with defaults that keep every existing pack unchanged:
- `claim_ids: tuple[str, ...] = ()`;
- `policy: str = "linear"`;
- `failure_severity: Literal["error", "warning"] = "error"`;
- `inconsistent_is_failure: bool = True`.

Every STEM check sets `inconsistent_is_failure=False` (D13).

| Id (kind) | What is decided | Form, expected | Policy | Failure severity |
| --- | --- | --- | --- | --- |
| `stem-eq-N` (`stem_arithmetic`) | a numeric link `E = S` (and `≈`) | E: ENTAILED; S: SATISFIABLE | linear unless surds or two interval operands are multiplied | error; warning when a D3b booklet value was used or a unit was unknown |
| `stem-sub-N` (`stem_substitution`) | substituted numerals against the symbols' bindings (R7). When the symbolic and numeric sides have the same tree shape, each aligned symbol is checked (a value written in another order of the same product or sum also matches, by bounded injective matching); otherwise, if every symbol is bound, the symbolic side under its bindings is checked against the numeric side (Form S over the binding intervals). A symbol with no binding takes a D3b booklet reading admitted by a dimension check, or the relation is ST-UNDEC-002 | E (pairs); E or S (evaluation) | as needed | error; warning when a D3b booklet value was used or a unit was unknown |
| `stem-alg-N` (`stem_algebra`) | the next relation follows from the preceding one, plus scope bindings of the symbols involved, plus at most 8 recorded formulas mentioning them, plus side conditions: divisors ≠ 0; a principal (non-negative) root in sciences profiles | E: ENTAILED | nonlinear when needed | error when the step is a pure manipulation (its symbols are a subset of the premise's symbols, bound symbols and included formulas); warning when it brings in unrelated symbols (an unstated law may be at work) |
| `stem-sol-N` (`stem_solution`) | membership: each stated root satisfies the equation (exact: linear substitution; decimal: R10). Completeness: the equation entails the disjunction of the stated roots, built only when the statement claims the full set, the parameters are exact and neither the statement nor the request restricts the domain ("positive", "x > 0", "length", "time", "reject", ...). A root may also be a decimal the answer states in prose for the quantity it named by the symbol ("Let $M$ be the monthly payment" … "Her monthly payment is €352.19"; section 21, item 4): membership only, over its rounding interval widened by τ = 1/100 | E; S for decimal roots | as needed (membership of an exact root is linear; completeness is nonlinear) | error |
| `stem-mod-N` (`stem_model`) | an equality with an application of an exponential model, the model's expression at the written argument against the other side: some value of the variables (the model's variable, every symbol with no stated value) and of the stated symbols within their stated values satisfies it, every power of an exponent in symbols read through positive variables (section 21, item 5) | S: SATISFIABLE (UNSATISFIABLE: no value satisfies the link) | nonlinear | error |
| `stem-cnv-N` (`stem_conversion`) | an explicit unit conversion (R5) | E | linear | error; warning when a unit was unknown |
| `stem-cmp-N` (`stem_comparison`) | a stated order or inequality between values (R6); bound symbols with several values pass when some admissible values satisfy it; also inequality-solving steps, checked as `alg` | E (or S) | as needed | error |
| `stem-res-N` (`stem_result`) | a prose restatement against the chain's final value (R8) | E | linear | error; warning when a unit was unknown |
| `stem-giv-N` (`stem_given`) | an answer's `Given:` value against the request's binding of that symbol, or a request quantity of the same dimension | E | linear | warning (symbol identity across texts is a reading) |
| `stem-tgt-N` (`stem_target`) | the final value of a show-that answer against the request's target | E | linear | warning |
| `stem-chem-N` (`stem_balance`) | element and charge balance. Coefficients are pinned; tally symbols `t_<el>_l` and `t_<el>_r` are defined per element; the conclusion is a conjunction of equalities, so the counterexample model shows the unbalanced tallies | E (Int, or Real for fractional coefficients) | linear | error |
| `stem-bool-N` (`stem_boolean`) | Boolean identity: premise `NEG: ¬(lhs ⇔ rhs)` | satisfiability, expected UNSATISFIABLE; SATISFIABLE is a failure whose witness is a distinguishing assignment | linear | error |
| `stem-tt-N` (`stem_truth_table`) | every row's stated output: stated outputs are pinned Bool symbols; the conclusion is the conjunction over rows of `o_r ⇔ expr(row inputs)` | E | linear | error |
| `stem-base-N` (`stem_base`) | a base conversion as exact Int arithmetic | E | linear | error |

The policy is read from the built IR (`to_ir.inspect_ir`): `nonlinear` exactly when a `mul` has
two factors that hold variables (the validator's rule; the tests compare it with
`engine.policies.required_policy`). The column says when that happens. A check whose encoding
would exceed polynomial degree 24 is not built (ST-LIM-001).

Each description has the form `<what was checked>: '<statement, ≤ 160 chars>' [claims s2.3,
s2.4] [<short rule>] <form; policy; readings; details>`, at most 1,200 characters. Descriptions
name readings, factored exponents, supplied constants and side conditions. `StemPack` rewrites
the statement ids in a description to the report's own claim ids.

Withheld relations. The checks stage decides only relations whose two sides are whole, so a
misreading by the front end can never become an error. A relation is withheld (ST-PARSE-001,
warning, the check id named) when an arithmetic operator adjoins one of its operands in the text
(`xy + y = …` read as `+ y = …`), when an operand opens with a sign right after a symbol-like
token or a stray character, or when prose stands between the two sides of one link. These
guards only ever withhold a check; none decides one (`stem/ENCODINGS.md`).

### 8.2 Finding codes

The column "Decided by" means:
- **engine**: a signed Z3 result;
- **deterministic**: rule-based reading;
- **numeric**: exact `Fraction` precheck or bookkeeping.

The STEM pack itself emits **no error-severity structural finding**. Every STEM error comes
from an engine result.

| Code | Severity | Decided by | Meaning |
| --- | --- | --- | --- |
| INT-SUBJ-001 | error | engine | a check of the report's own STEM statement does not hold, and it rested only on what the report or request states plus exact encoding devices (existing code; now carries `claim_ids`; for a STEM check the message gives the counterexample's computed value `c` and stated value `r`) |
| INT-SUBJ-002 | warning | engine | such a check is undecided: UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION, INTERNAL_ERROR, a vacuous result (E108), or INCONSISTENT_PREMISES on a check with `inconsistent_is_failure=False`; also (deterministic) an unknown policy name, an exception while deciding the check, or the report's STEM check budget (8 s) spent (existing code; now carries `claim_ids`) |
| INT-SUBJ-003 | error | deterministic | an error-severity pack finding, escalated (existing; STEM never produces one) |
| INT-SUBJ-004 | warning | engine | NEW: a check that relied on a reading the report did not state does not hold: a booklet value for an unstated symbol, symbol identity across request and answer, a show-that target, a step bringing in unrelated symbols, or an unknown unit |
| BR-INTERNAL-001 | warning | deterministic | NEW (`SubjectBranch.run_packs`): pack `<name>` failed internally (`<type>`) during `<checks or formal checks>`; its findings are missing from this receipt, and the router must not treat the pack as passed |
| ST-PARSE-001 | warning | deterministic | a math span uses notation outside the grammar (named: unknown LaTeX command, unbalanced group, a symbolic power); its relations are not checked |
| ST-PARSE-002 | warning | deterministic | an expression has more than 2 readings (or a check more than 4): implicit multiplication or unit/symbol ambiguity; not checked |
| ST-UNDEC-001 | warning | deterministic | a recognised relation outside the encodings (calculus, limits, Σ, vectors, matrices, complex numbers, `!`, asymptotic notation, a function of an unknown, an approximation step such as sin θ ≈ θ, an angle range); the reason is named |
| ST-UNDEC-002 | warning | deterministic | a numeric relation depends on a symbol with no stated value and no admissible booklet reading |
| ST-UNDEF-001 | warning | numeric | a written expression is undefined (division by an exact zero, an even root of a negative value, the logarithm of a non-positive value, 0⁰, tan at a pole, arcsin or arccos outside [−1, 1]); no check is built |
| ST-UNIT-001 | warning | deterministic | a unit expression is not recognised; the relation is checked as written only, at warning severity |
| ST-UNIT-002 | info | deterministic | an ambiguous unit symbol (M: molar or mega) is checked under both readings |
| ST-DIM-001 | warning | deterministic | the two sides of a stated relation have different dimensions (units read unambiguously) |
| ST-DIM-002 | warning | deterministic | a sum or difference of terms with different dimensions |
| ST-ALG-001 | warning | deterministic | a mathematics step takes only the non-negative square root, and no domain restriction is stated (the algebra is still checked under that side condition) |
| ST-CHEM-001 | warning | deterministic | a chemical equation cannot be read (unknown element symbol, isotope notation, a bound exceeded); its balance is not checked |
| ST-CODE-001 | info | deterministic | a code block is present; it was not executed and not checked |
| ST-SCOPE-001 | info | deterministic | a symbol is rebound to a different value inside the answer; substitutions match any binding |
| ST-LIM-001 | warning | numeric | an expression or literal exceeds a front-end or IR bound (span, links, nodes, depth, exponent, digits after factoring, symbols, intervals); not checked |
| ST-LIM-002 | warning | deterministic | more relations than the per-report check cap (128), or more math spans than the per-report reading cap (1,024); the count and the first unchecked ids or statements are named |
| ST-INTERNAL-001 | warning | deterministic | the STEM pack failed internally while building checks, an enclosure failed its cross-check against `math`, or a built problem was refused by `Problem.model_validate`; the affected checks are missing and must not be read as passed |
| CORE-QNT-001 | warning | deterministic | existing; in SI reading, new reasons: different dimensions, "a relative change on an offset temperature scale is not defined" |

Severity semantics are unchanged:
- an engine check that does not hold: INT-SUBJ-001 (error) or INT-SUBJ-004 (warning);
- undecided: INT-SUBJ-002 (warning);
- ST warnings make the status ACCEPTED_WITH_FINDINGS;
- info changes nothing.

All of these are content findings: the report is delivered, never REJECTED.

---

## 9. Claim extraction, roles and eligibility

### 9.1 `StemTextParser` (`adapters/stem_specialist/parser.py`, implements `ReportParser`)

- **Claims.** Claims come from `StemDocument` statements: a sentence, a derivation line, a
  display row, a list item, a code block, a table or a data line. Ids are
  `s<paragraph>.<statement>` in the `sciences` branch and the same numbering with the branch's
  own letter in the other two (`m1.2` in `mathematics`, `c1.2` in `computer_science`), so a
  Physics and a Mathematics report on one task never share a claim id (the combinator's ledger
  refuses shared ids, INT-LEDGER-014). Ids are stable and deterministic. `StemTextParser` takes
  `agent_id` and `mode`, declares `accepts_request_text`, and the channel passes it the
  request text, so the parser and the pack read the same document.
- **Overflow.** Claims beyond 512 merge into `s.tail` (`m.tail`, `c.tail`) with the
  unresolved-issue text the bus turns into INT-REQ-013, as in the generic parser.
- **Empty text** still raises `AdapterError` (`tests/channel/test_channel_robustness.py:57`).
  A code-only answer yields claims; it does not raise.
- **Markup.** `markdown.strip_markup` is not applied wholesale, because it drops code fences
  and some bracket lines. Headings become part labels. Emphasis is dropped only in the prose
  view. Code blocks, tables and data lines are kept.
- **Notes.** Notes and self-certification use the shared `is_note_sentence` and
  `is_self_certification` (role `other`). A statement that carries maths is never taken for a
  note because it has no words (`√8 = 2√2`).
- **Quotations** of supplied texts and peer reports are found and credited by the rule every
  parser shares (`sources.attribute_excerpt`), on the quotation view of the answer (code masked;
  an inch or arcsecond mark after a number is not a quotation mark).
- **Assumptions.** A claim whose numeric relations the pack decides carries the assumption
  "numeric relations of this statement are decided by the STEM pack checks <ids>". The ids
  are planned in the shared document.
- **Structured reports.** For a report that arrives structured (JSON), `StemPack` maps
  statements to the report's own claims by offset when the claim texts are offset substrings,
  else by the shared two-way substring rule (`_claims_mentioning`).

### 9.2 Roles (no new `ClaimRole`; D11)

| Statement | claim_role | proposed kind | materiality | Eligibility (existing rules) |
| --- | --- | --- | --- | --- |
| Given or data line; a binding whose value is in the request | evidence | arithmetic | supporting | QUANTITATIVE_CLAIM |
| Law or formula with no numerals (`F = ma`, "Using v² = u² + 2as") | evidence | factual | supporting | NOT_ELIGIBLE_FACTUAL, route `evidence_service` |
| Substitution or arithmetic step; symbolic algebra step | quantitative | arithmetic | supporting | QUANTITATIVE_CLAIM / ARITHMETIC_CONSTRAINT (rule 4 extended, 9.3) |
| Result: the last chain-bearing statement of a part, or a prose value after therefore/so/hence/"the answer is" | quantitative | arithmetic | material | QUANTITATIVE_CLAIM |
| Explanation paragraph: first substantive sentence | point | unknown | material | PROPOSITIONAL_ARGUMENT when supporting claims exist |
| Explanation sentence with because/since/so/therefore/hence/thus and no value | link (supports earlier claims of the paragraph) | unknown | supporting | PROPOSITIONAL_ARGUMENT |
| Other explanation | analysis | unknown | supporting | NOT_ELIGIBLE_INTERPRETIVE |
| Assumption ("neglecting air resistance"), also copied to `report.assumptions` | analysis | unknown | supporting | NOT_ELIGIBLE_INTERPRETIVE |
| Assumption that binds a value ("taking g = 9.81 m s⁻²") | evidence | arithmetic | supporting | QUANTITATIVE_CLAIM |
| Code block (text truncated by `truncate_claim_text`; ST-CODE-001 names it) | point | unknown | material when it answers the item | not eligible (no supports) |
| Table, data or vector line | evidence | arithmetic | supporting | QUANTITATIVE_CLAIM when it carries figures |
| Notes, self-certification | other | — | supporting | never material |
| A heading line with no content of its own ("Given:", "Working:") | structural | unknown | supporting | NOT_ELIGIBLE_OTHER (no numerals) |

Every chain-bearing part yields a material result, so INT-REQ-012 ("no answer") never fires
on a derivation.

Since the merge with the round-7 development branch, roles, materiality and supports are the
generic branch's round-7 reading, with the refinements of this table applied only where round 7
did not rule (section 20.2): a link supports the point and rests on nothing, and a consequence
rests on the claims before it.

### 9.3 Eligibility (`translate/eligibility.py`)

Rule 4 (COUNT_ROLES) also accepts a text with a mathematical relation sign between operands
(`=`, `≠`, `<`, `>`, `≤`, `≥`, `≈`). In the same profiles `has_numeral(text, scripts=True)`
also counts superscript and subscript digits (`x²`, `v₀`). Both apply only when the profile
allows QUANTITATIVE_CLAIM, so argument-only profiles are unchanged. POLICY_VERSION is bumped.
Eligibility classes for the sciences, mathematics and CS profiles remain `_QUANTITATIVE`.

---

## 10. Routing and profiles

### 10.1 `translate/subjects.py`

1. **Word-boundary aliases.** Alias matching uses word boundaries on the normalised label,
   `(?<![a-z0-9])alias(?![a-z0-9])`, keeping the longest match. This fixes:
   - "Assessment", "Process" and "Stress and Wellness" resolving to `ess`;
   - "Free fall" and "Software engineering" resolving to `extended_essay`.

   Every display name and "display name + HL" must still resolve to its own profile, and
   "Underwater Basket Weaving" must stay UNKNOWN (`tests/translate/test_overseer_round1.py`).
2. **STEM aliases.**
   - phys → physics; chem → chemistry; bio → biology.
   - cs, comp sci, computer sci, software engineering (and the existing computer science,
     computing) → computer_science.
   - environmental science, environmental systems → ess.
   - statistics, stats → mathematics_ai.
   - maths: aa, math: aa, mathematics: aa, aa hl, aa sl → mathematics_aa, and the AI
     equivalents (maths: ai, math: ai, mathematics: ai, ai hl, ai sl) → mathematics_ai.
   - further mathematics, further maths → mathematics_aa (working configuration, recorded as
     such).
3. **A new profile `stem`** ("General Science (STEM)", group sciences, `_QUANTITATIVE`, Int
   and Real). It covers "science", "sciences", "general science", "stem" and "engineering". It
   also covers labels that name two or more different sciences ("Physics/Chemistry"): when
   matches fall in two or more of the six science profiles and the longest match is one of
   them, the label resolves to `stem` rather than the longest.
4. **`can_check` and `cannot_check`** for the sciences, mathematics and CS profiles are
   rewritten to the truth.
   - Deterministic STEM checks decide the written arithmetic, substitutions, conversions,
     dimensions (warnings), balances, algebraic steps and Boolean identities.
   - The model translator's formalisations do not check units.
   - Nothing establishes physical validity, the truth of laws or data, diagram or graph
     reading, or calculus.
5. **STEM encoding guidance** in `prompt_profile_text` for the STEM profiles, used by the
   model translator path:
   - exact numerals with no exponents;
   - substitute given values;
   - one symbol per quantity, namespaced per claim (`s<claim>_v`) to avoid cross-claim unification;
   - units as assumptions;
   - `sqrt` and trig as squared comparisons or UNSUPPORTED.

   This is `subjects.STEM_ENCODING_GUIDANCE`, added for every key of `STEM_PROFILE_KEYS`. It
   bumps TRANSLATOR_VERSION. The pinned prompt version `translate_v1` and its file are
   unchanged.

### 10.2 `branches/registry.py`

`CORE_SI = CorePack(reading=SI_READING)`. Its `name` is still `"core"` and it comes first in
every STEM branch (`tests/branches/test_quant_and_packs.py:77-79`).

| Branch key | Profile keys | Parser | Packs |
| --- | --- | --- | --- |
| `sciences` | physics, chemistry, biology, ess, sports_science, design_technology, stem | `StemTextParser(agent_id="science-specialist", mode="sciences")` | (CORE_SI, StemPack("sciences")) |
| `mathematics` | mathematics_aa, mathematics_ai, mathematics | `StemTextParser(agent_id="maths-specialist", mode="mathematics")` | (CORE_SI, StemPack("mathematics")) |
| `computer_science` | computer_science | `StemTextParser(agent_id="cs-specialist", mode="computer_science")` | (CORE_SI, StemPack("computer_science")) |

`generic` stays the default for `unknown`. The reading profile follows the report's subject
(`stem_profile_key`): its own profile when that is a STEM profile, else the branch mode's
fallback (`stem`, `mathematics` or `computer_science`). The per-profile switches are in
`stem.limits.PROFILES`: chemical equations for chemistry, biology, ESS and `stem`; a bare `M`
after a number is molar in chemistry and biology, molar or mega in physics and `stem`, mega
elsewhere; the tonne in ESS and Design Technology; Boolean words and indented code blocks in
Computer Science; only the principal root in the sciences. Each STEM branch sets
`hub_hooks=STEM_HOOKS` (section 11).

**Recorded behaviour change.** Two existing assertions encoded the pre-STEM routing:
- `tests/branches/test_hub.py:46`: `branch_for("Chemistry") == "generic"`;
- `tests/branches/test_quant_and_packs.py:76`: `for_subject("Physics")[0].key == "generic"`.

The user's goal and the observed defect are exactly this routing, so it must change. Stage
`branch` replaced each with an assertion of equal strength for the new branch (`"sciences"`)
and added an unknown → generic assertion beside it (`"Underwater Basket Weaving"`). Nothing was
deleted; each changed line carries a comment naming this section. The change is recorded for
the overseer audit and the user's sign-off, which happen in the integrated arena. Every other
existing test that runs a Physics plan passes unchanged. In particular `StemPack` emits nothing
on `The speed is 15 m/s.` (no relation is stated) and only info for unchecked code.

---

## 11. Hub, channel and receipts

### 11.1 `branches/base.py`

- `FormalCheck` gains the four fields of section 8.1.
- `SubjectBranch` gains `hub_hooks: Optional[BranchHooks] = None`.
- `SubjectBranch.run_packs` guards each pack call (its `checks` and its formal checks
  separately). On an exception it adds BR-INTERNAL-001 (warning: the pack, the exception type
  and the stage, never the exception's text) and continues with the next pack.
- It prefers `pack.formal_checks_for(report, request_text)` when the pack defines it.
- On relay (`req=None`, so `request_text=None`) STEM checks bind only to the answer's own
  values, and `stem-giv` and `stem-tgt` are not built (`StemPack.formal_checks` is this relay
  form).
- `BranchHooks` is a protocol of plain-data methods, each given the subject profile key the
  channel resolved for the agent: `request_imperatives` (a tuple), `coverage_terms(claim_text,
  report_text, request_text, profile_key)`, `echo_exempt(report_text, request_text,
  profile_key)` and `word_count_view(text, profile_key)`.

### 11.2 `channel/bus.py`

`_branch_checks`:
- calls `verify(fc.problem, policy_config(fc.policy, cfg), limits=policy_limits(fc.policy),
  signing_key, key_id)`, where `cfg` is the channel config. For the `linear` policy that is
  `cfg` itself; for `nonlinear` it is `cfg` with `rlimit` at most `NONLINEAR_RLIMIT` (a
  caller's lower `rlimit` is kept), so cutoffs are deterministic. An unknown policy name gives
  INT-SUBJ-002 "unknown policy"; it is never run under some other policy.
- runs the STEM checks of one report (kinds `stem_*`) under a wall-clock budget
  (`STEM_CHECK_BUDGET_S`, 8 s): checks left when it is spent are not run and are INT-SUBJ-002
  ("check budget"), never success. Other packs' checks are not budgeted.
- maps the status as follows:
  - `satisfied = True` iff the status equals `expected_if_sound` and no E108 diagnostic is
    present;
  - `satisfied = False` iff the status is definitive and not the expected one, except
    INCONSISTENT_PREMISES when `inconsistent_is_failure` is False;
  - `None` otherwise.

  Before this change the False list missed SATISFIABLE for checks expecting UNSATISFIABLE, and
  an ENTAILED result carrying E108 showed as satisfied. Existing ENTAILED-expecting checks with
  non-vacuous proofs keep their behaviour.
- maps `False` with `failure_severity="error"` to INT-SUBJ-001, `False` with `"warning"` to
  INT-SUBJ-004, and `None` to INT-SUBJ-002. Each carries `claim_ids=list(fc.claim_ids)`. For a
  STEM check with a counterexample, the message adds the model's `c` (the value computed from
  the written expression) and `r` (the stated value).
- truncates `ConstraintResult.detail` and finding messages with `translate.common.truncate`
  (2000 each), so a long description can never raise out of `hub.receive`. Each verify call
  and result construction is guarded: an exception becomes INT-SUBJ-002 "internal" for that
  check alone.
- **Degrades safely.** If the policy pass-through were missing, nonlinear checks would come
  back UNSUPPORTED (E201) and show as undecided, never as success.

Hooks (`stem/hub_hooks.py`, `STEM_HOOKS`; none for other branches, so their behaviour is
unchanged). The channel calls each through a guard: a hook that fails falls back to the
channel's own reading, because a hook only ever refines a heuristic.
- `coverage_terms`, read by `_coverage`: quantity names keyed by the dimensions of the claim's
  quantities (m s⁻² → acceleration; N → force, weight, tension; J → energy, work; …) and of the
  bound symbols it uses. A claim that holds a planned computation (an engine check of its
  arithmetic, substitution, conversion, algebra, roots, balance, Boolean identity or based
  numeral) also offers the computing command words (calculate, determine, find, convert,
  solve, …): it does compute. An equation-only correct answer then does not get a heuristic
  INT-REQ-004 warning. The method stays `lexical_heuristic`.
- `echo_exempt`, read by `_request_echo`: a STEM answer containing at least one planned
  computation link (`stem-eq`, `stem-alg` or `stem-sol`) that is absent from the request is
  never INT-REQ-011. This fixes the false error on the correct show-that answer
  `n = m/M = 36 g / 18 g mol⁻¹ = 2.0 mol`.
- `request_imperatives` (`STEM_IMPERATIVES`), passed to `extract_items(text,
  extra_imperatives=…)`: determine, deduce, derive, state, find, solve, sketch, estimate,
  predict, verify, show, at the start of a sentence or after a part label. Multi-part STEM
  questions then become one item per part.
- `word_count_view`, read by `count_answer_words`: LaTeX control words are not words, and each
  math span and each code block counts as one word. This avoids a false INT-REQ-005.

### 11.3 `channel/request_parser.py`

`extract_items(text, *, extra_imperatives=())` and `count_answer_words(text, *, view=None)`.
With extra imperatives, a request line that opens with a part label (`(a)`, `b)`, `(ii)`,
`Part (c)`) also starts a new sentence. The defaults reproduce the general reading exactly.

### 11.4 Receipts

Receipts are unchanged in shape:
- `formal_checks` holds `ConstraintResult(constraint_id=check_id, method="formal",
  formal_result_id, formal_status)`;
- `structural_findings` holds the ST findings;
- the summary keeps counts "N (ok, FAILED, undecided)", names at most 8 FAILED and 8
  undecided ids, shows the code histogram (ST-* included), and ends with `_SCOPE_TAIL`.

Check ids are short and stable, as in section 8.1.

### 11.5 `integrity/ledger.py`

Synthesis-fidelity figure extraction (INT-LEDGER-0xx) reads scientific notation (`3.0e8`,
`6.67 × 10⁻¹¹`, `1.2*10**6`) through `stem.numbers.scan_number`. Such a figure is one figure
whose spellings are its exact decimal value and its normalised mantissa-exponent form, so
`3.0e8`, `3.0 × 10⁸` and `300000000` are the same figure. Before this change `3.0e8` yielded no
figure and `6.67 × 10⁻¹¹` yielded 6.67 and 10. A figure beyond the scanner's bounds (an exponent
over 99) is not read, and neither are its parts. Figures with no exponent are read as before.

---

## 12. CorePack and quant in SI reading

`quant.py` gains a keyword-only `reading: QuantReading` parameter on `extract_quant_checks`
and `undecided_quant_statements`. `QuantReading(name, si, profile)` is a frozen, hashable
dataclass (`stem/si_reading.py`) and is part of the extractor's cache key; `si` switches every
SI rule below on, and `for_profile(key)` gives the reading for one subject profile. The
SI-specific figure patterns, unit reader, views and statement splitter live in
`stem/si_reading.py`, which imports nothing from `branches` or `channel`. `GENERAL`
(`quant.GENERAL`) is the pre-STEM extractor byte for byte, and every existing quant test runs on
it; `tests/branches/test_quant_si_reading.py` pins it against a 570-text reference corpus
recorded before `QuantReading` existed. `SI_READING` changes the following:

- **Scale words.** Only spelled-out words (thousand, million, billion, trillion, quadrillion,
  bn) are scales. m, k, K, M, A and g are never scales, so `500 mm to 2 m` and `300 K` are read
  correctly.
- **Units.** A figure followed by a unit symbol is read through `stem.units` into an SI value
  and a dimension.
  - Pairs are comparable when their dimensions are equal: `500 g to 1.0 kg` is a doubling,
    `2 kg to 500 g` is a fall of 75 per cent, and `3.0 A to 1.5 A` pairs.
  - Different dimensions are undecided, with the reason named.
  - A relative change on an affine scale is undecided.
- **Numbers.** Scientific notation, `−` and `-` are read, and a U+2212 sign on a stated change
  is honoured. A relative change is taken against the magnitude of the earlier figure, so a
  rise from −4.0 to −2.0 is a rise of 50 per cent. Repeated folds are read: "halved twice" is
  ×¼; "doubled three times" is ×8.
- **Band.** The band is sign-aware, `|C − S| ≤ tol·|C| + floor`, encoded with `ite`. `S = 0` is
  decided by the same inequality.
- **View.** quant reads the SI quant view (`si_quant_view`), in which every relation-bearing
  math span (LaTeX, a math run, verbal arithmetic, chemistry, code, tables) is a placeholder
  while quantities (`500 g`) stay readable. quant sees only prose relations and `StemPack` only
  math relations; the same statement is never checked twice.
- **Sentences.** Statements are split by the STEM segmenter (`si_statements`), so CORE-QNT-001
  paragraph and sentence numbers match the STEM claims `s<paragraph>.<n>`.

`CorePack(reading)` reads two more views of the same length, both of which mask an inch or
arcsecond mark attached to a number: `si_prose_view` (math, code and quantities masked) and
`si_quote_view` (the original with code masked). It uses them for three things:
- the quotation reading (CORE-SRC-003, -004, -005), where inch and arcsecond marks attached to
  numbers (`12″`, `0.5"`) are masked, so CORE-SRC-004 no longer fires on them;
- chronology, so `1500 K` is never a year;
- CORE-SELF-001 and `_sentences_with_paragraph`.

CORE-SRC-001 (per `source_ref`) is unchanged. The default `GENERAL` keeps every other branch
unchanged.

---

## 13. Performance

- **Front end.** Linear in the response length: one lexer pass per span, a bounded parser,
  and no backtracking regex on unbounded text. The document is built once per (text,
  request, profile) and shared by parser, pack and CorePack.
- **Engine.** About 4 to 20 ms per check, measured on the design-time probes. Probe totals:
  - 40 linear arithmetic checks: 327 ms;
  - a five-interval nonlinear Form S check: 8 to 9 ms;
  - nonlinear rearrangement, square-root and solution-set checks: 5 to 15 ms each;
  - a 150-step derivation (150 checks) through the hub: about 0.95 s.
- **Budget.**
  - At most 128 STEM checks per report (ST-LIM-002 beyond).
  - Nonlinear checks run with a deterministic `rlimit` (`NONLINEAR_RLIMIT`, calibrated in
    stage `engine`), and their cutoffs read as undecided.
  - A per-report wall-clock guard of 8 s for STEM checks marks the remaining checks undecided
    (INT-SUBJ-002, "check budget"). It only ever degrades to undecided, never to success.
- **Targets** (asserted by stage `corpus-eval` stress tests, `-m stress`):
  - p95 hub receive for a typical 3-part Physics answer below 250 ms;
  - a 128-check answer below 2.5 s;
  - an adversarial 400,000-character input (nested brackets, unclosed `$`, `1e1e1e`, 30-digit
    numbers) through the front end below 1.5 s;
  - unchanged suite time for the non-STEM tests.
- **Measured** (`tests/stress/test_stem_stress.py`, figures in `tests/stress/results/stem.json`
  and docs/STEM_RESULTS.md): every target is met. A typical 3-part Physics answer: p95 188 ms
  over 60 answers. A 128-check answer: 1.22 s. The mixed adversarial input: best of 5 runs
  1.09 s. Two single-pattern inputs at 400,000 characters (`1e1e…`, unclosed `$`) take 1.6 to
  1.8 s; the target is for the mixed input, and these are recorded, not asserted.

---

## 14. Safety (no eval)

- **No string evaluation.** No `eval`, `exec`, `compile` (only `re.compile` of constant
  patterns), `__import__`, `importlib`, `pickle`, `marshal`, `sympify`, `parse_expr`,
  `ast.literal_eval`, `subprocess` or `os.system`, and no library that evaluates strings. No
  sympy dependency.
- **`Fraction` input.** `Fraction` is constructed only from integer pairs, or from digit
  strings the lexer has already validated.
- **Enforcement.** Three tests parse source with the standard `ast` module (the tests use
  `ast`; the package does not):
  - `tests/stem/test_front_end_safety.py` scans every module of `stem/`. It fails on a
    forbidden name (`eval`, `exec`, `compile`, `__import__`, `globals`, `locals`, `vars`,
    `open`, `input`, `breakpoint`, `setattr`, `delattr`, …), a forbidden attribute (`.eval`,
    `.sympify`, `.parse_expr`, `.literal_eval`, `.loads`, `.system`, `.import_module`,
    `__globals__`, …), a `getattr` or `hasattr` with a computed attribute name, or an import
    off the allowlist. The allowlist is the standard-library modules `re`, `fractions`,
    `dataclasses`, `functools`, `typing`, `hashlib`, `unicodedata`, `math`, `enum` and
    `types`, the package's own modules, and one shared module,
    `adapters.history_specialist.sentences`. A meta-test checks that the scan catches each
    forbidden form.
  - `tests/stem/test_checks_safety.py` scans the checks-stage modules again: `math` only in
    `enclosures.py` (the cross-check), and no `Fraction` built from a string constant.
  - `tests/stem/test_parser_claims.py` scans `adapters/stem_specialist/`,
    `branches/stem_pack.py`, `stem/si_reading.py`, `stem/hub_hooks.py` and `branches/quant.py`
    for the forbidden names and attributes and for imports of `pickle`, `marshal`,
    `subprocess`, `importlib`, `sympy`, `ast`, `os`, `builtins`, `code`, `codeop` and `runpy`.
- **Audit at the end of the build.** A search of all of `src/epinoic_logic` for `eval(`,
  `exec(`, bare `compile(`, `sympify`, `parse_expr`, `__import__`, `pickle`, `marshal`,
  `literal_eval`, `globals()`/`locals()`, `subprocess`/`os.system`, sympy or numexpr imports,
  `ast` use and dynamic `getattr` found none used on agent text: every `compile(` is a
  `re.compile` of a constant pattern; the one `eval(` is Z3's `model.eval` on an already
  compiled symbol (`engine/procedures.py`); `importlib.import_module` appears only in `cli.py`
  and `service/app.py`, on fixed names or an adapter id from the operator's configuration within
  the `epinoic_logic.adapters` namespace; and every `getattr` uses a literal attribute name or
  iterates a fixed tuple of schema fields.
- **Closed outputs.** Only allowlisted AST nodes are translated, and only into IR 1.0 nodes.
  `Problem.model_validate` runs on every built problem, and the validator runs again inside
  `verify`.
- **Bounded work.** Every loop is bounded by `StemLimits` (section 4.9). Recursion depth is
  checked before descent, and exponent and digit bounds prevent `Fraction` blow-up
  (`10^999999`).
- **Code is inert.** Code spans are never parsed for meaning, run, imported or written to disk.
- **Verbatim original.** `original_response` is never altered.
- **Trust.** The engine discards any `verified=True` in untrusted payloads (E505). The STEM
  pack builds problems in-process, as quant does, and agent self-reports stay advisory.
- **Repository rules.** No code or prompt text is copied from other projects. No model names
  or session ids appear in code or docs.

---

## 15. Out of scope

1. The truth of laws, data, constants or definitions, and whether a model applies or is
   physically valid (the evidence service and subject evaluator).
2. Symbolic calculus (derivatives, integrals, limits, series, differential equations): named
   undecided (ST-UNDEC-001), never decided.
3. Vectors, matrices, complex numbers, factorials or combinatorics written with `!`, Σ with
   symbolic bounds, probability distributions, and asymptotic notation: named undecided.
4. Exact proof of identities between transcendental values. Enclosures establish agreement to
   10⁻¹⁵ relative only, and the description says so.
5. Unit correctness beyond dimension consistency (warnings) and explicit conversion checks.
   Significant-figure policy (penalising too many figures) is not checked.
6. Molar masses from formulas and any check against our own data tables, except the D3
   readings. Constants are used only to widen a written value or, at warning severity, to read
   an unstated standard symbol.
7. Program behaviour. Code is never executed, interpreted or checked (ST-CODE-001 info).
   Algorithm quality and complexity claims are not checked.
8. Diagrams, graphs, sketches, images and handwriting; reading values from a graph.
9. The completeness or quality of the method, presentation and mark-scheme matching. Only a
   show-that target value is compared (warning).
10. Uncertainty-propagation rules. Their arithmetic is checked as arithmetic; whether the
    right rule was used is not.
11. Cross-agent symbol unification in the model-translator pool (`integrity/cross_check.py`).
    Deterministic STEM checks are not pooled. The STEM profile text asks the translator to
    namespace symbols per claim, but no glossary rule changes.
12. Quotation-grounding normalisation of minus, en dash and × in `translate/grounding.py`.
    It is deferred; STEM answers rarely quote supplied texts.
13. Adding the Limits digest into `Binding.binding_digest`. At the STEM merge the engine recorded
    non-default Limits on the signed result only, which kept the hand-off binding formula unchanged.
    Done since engine 0.4.0 (external review of 12 October 2026): the binding carries
    `limits_digest` for non-default limits (appended to the binding digest; the default formula is
    unchanged), and `check_result_binding(..., limits=...)` compares them with the policy the
    receiver requires, so a nonlinear STEM result passes only a receiver that names `nonlinear`.
14. Non-SI conventions beyond the table (imperial units except °F and the inch mark), and
    locale number formats beyond the decimal-comma rule.

---

## 16. Test plan

New tests are added. No existing test is weakened or deleted. The two recorded routing
assertions (section 10.2) are replaced by assertions of equal strength.

Every file named below exists. The implementation added these test files beyond the plan:
`tests/stem/test_hub_hooks.py` and `tests/stem/test_si_reading.py` (stage `branch`),
`tests/stem/test_reading_extensions.py` (99 tests pinning the module fixes the corpus found,
stage `corpus-eval`), `tests/stem/test_arena_stem_mutations.py` (19 tests of the arena
mutations), `tests/branches/data/quant_general_reference.json` (the 570-text reference of the
general quant reading), the corpus builder `tests/stem/data/` (`build_stem_corpus.py`,
`corpus_dsl.py`, `corpus_items.py`, `corpus_items_more.py`, `corpus_lib.py`) and the labelled
fixture corpus `tests/fixtures/stem/corpus/` (84 answers written before implementation; see its
README). The corpus has 558 items (236 correct, 292 mutants, 30 rounding-only controls), above
the 120 and 240 floors below.

**Stage `core`** (no engine). `tests/stem/`:
- `test_normalize.py`: the length-preserving map; masked views keep offsets; quotation and
  inch marks inside spans are masked.
- `test_spans.py`: every span kind; `$` versus currency; derivation-line continuation;
  tables; truth-table blocks; code spans recorded and masked.
- `test_segment.py`: `The ball falls 5.0 m. It then stops.` splits; `is v. Then` splits;
  `c. 1500` and `p. 12` do not split; `\frac{1}{2} M v^2` is never cut; History splitter
  outputs are byte-identical on the History corpus.
- `test_lexer.py`: every number form in 4.4; Unicode minus; superscripts and subscripts;
  LaTeX allowlist; an unknown command is Unparsed.
- `test_numbers.py`: significant figures, last place, half-width, the integer trailing-zero
  rule, exactness, a bare zero.
- `test_units.py`: prefixes, `ms` versus `m s`, unit expressions, the ambiguity table per
  profile, exact factors, affine handling, dimensions.
- `test_parser.py`: precedence, right-associative powers, implicit multiplication against
  scope (`at`, `mgh`, `½mv²`, `2πr`), two readings, ST-PARSE-002 at three, Unsupported
  reasons, depth and node bounds.
- `test_scope.py`: binding sources, rebinding, any-binding matching.
- `test_relations.py`: link classification for every row of 4.7; deterministic check ids;
  claim ids.
- `test_chem_parse.py`, `test_boolean_parse.py`: tallies, hydrates, charges, fractional
  coefficients, truth tables, based numerals.
- `test_document.py`: memoisation keys; one document shared by every reader.
- `test_front_end_safety.py`: the AST scan of section 14; adversarial inputs within time bounds.

**Stage `engine`.** `tests/engine/`:
- `test_pack_policies.py`:
  - the named policies map to exact Limits;
  - an unknown name is refused;
  - a default-policy result has no `limits` field and an unchanged signable text;
  - a nonlinear result records its Limits under the signature, so tampering fails
    `verify_signature`;
  - the hand-off binding check is unaffected;
  - `NONLINEAR_RLIMIT` turns a hard polynomial system into TIMEOUT or UNKNOWN, never success.
- `test_stem_shapes.py`: every STEM encoding shape through `verify` with its expected status.
  - Linear: Form E pass and fail; the sign-aware band at −9.8 against −9.81; zero; an
    auxiliary closed divisor; Int balance; a Boolean identity by satisfiability; inequality
    steps; enclosure Form S.
  - Nonlinear: a surd; a symbolic divisor; rearrangement correct and wrong; completeness of a
    solution set, complete and with a missing root; a decimal root; Form S with five
    intervals.
  - Each shape is UNSUPPORTED (E201) under `linear` where it is nonlinear.
  - Median time per shape below 50 ms.

**Stage `checks`.** `tests/stem/`:
- `test_constants.py`: table integrity; written-constant recognition; the dimension guard of
  D3b.
- `test_enclosures.py`: enclosure width and containment against `math`, over grids including
  special angles, at both ends of the bounds; the exact table.
- `test_scaling.py`: the factoring identity on random monomials and sums; literals at most 40
  digits; ST-LIM-001 beyond.
- `test_tolerance.py`: R1 to R10, including the integer trailing-zero rule and the observed
  case.
- `test_to_ir.py`: every row of 7.4; symbol naming is injective; grounding kinds per premise;
  `Problem.model_validate` passes; policy chosen exactly when needed.
- `test_checks_engine.py`: every check kind of 8.1, correct and wrong, through `verify`, with
  expected status, `failure_severity`, `claim_ids` and description bounds.
- `test_checks_no_false_errors.py`: rounding to the written precision; booklet constants
  (9.8 against 9.81; 6.6 against 6.63 × 10⁻³⁴); carried intermediates (4.85 → 4.9);
  approximate chains; conversions inside chains (`0.0125 m³ = 12.5 dm³`); bare conversion
  factors (`÷ 3.6`); percentages both ways; physics positive roots; sign conventions
  (g = −9.81); part (b) reusing part (a)'s letters. None may yield a failed check.
- `test_checks_safety.py`: undefined expressions give ST-UNDEF-001 with no problem built; no
  free symbol in a Form S problem; literal bounds.

**Stage `branch`.**
- `tests/stem/test_parser_claims.py`: claims are offset substrings; ids are stable; roles and
  materiality per 9.2; empty text raises; a code-only answer yields claims; data lines and
  tables are kept; INT-REQ-012 never fires on a derivation.
- `tests/branches/test_stem_pack.py`: ST findings with codes and severities; check ids match
  the parser's assumption text; nothing on `The speed is 15 m/s.`; ST-INTERNAL-001 on an
  injected failure.
- `tests/branches/test_stem_routing.py`: every alias of 10.1; word boundaries; the misroutes
  fixed; `Physics/Chemistry` → stem; every display name; unknown → generic; packs[0] is core.
- `tests/branches/test_quant_si_reading.py`:
  - the false errors fixed: `500 mm to 2 m`, `2 kg to 500 g`, `halved twice`, `300 K`,
    `3.0 A to 1.5 A`;
  - a negative and a signed change;
  - GENERAL byte-identical on the History, Economics and Business corpora.
- `tests/channel/test_branch_check_mapping.py`: the status mapping table of 11.2 for
  ENTAILED, SATISFIABLE and UNSATISFIABLE expectations; E108; INCONSISTENT_PREMISES under both
  flags; INT-SUBJ-004; claim ids; truncation of a 5,000-character description; BR-INTERNAL-001
  on a raising pack; an unknown policy.
- `tests/channel/test_stem_channel.py`:
  - the observed case end to end (INT-SUBJ-001 on the chain claim, delivered);
  - the 13 probe answers;
  - echo exemption for show-that answers;
  - coverage on symbol-only answers;
  - STEM imperatives split items;
  - the LaTeX word count;
  - relay (`req=None`).
- `tests/translate/test_stem_subjects.py`, `tests/translate/test_stem_eligibility.py`: the
  profiles, the prompt profile text, and rule 4 with relation signs.
- `tests/integrity/test_stem_ledger_figures.py`: scientific-notation figures; plain figures
  unchanged.
- `tests/e2e/test_stem_e2e.py`: multi-agent Physics + Maths + combinator through `RouterHub`;
  receipts signed; the scope tail present.
- The full existing suite stays green.

**Stage `corpus-eval`.**
- `tests/stem/data/stem_corpus.json`: at least 120 correct answers across Physics, Chemistry,
  Biology, ESS, SEHS, Design Technology, Mathematics AA/AI and CS, in LaTeX inline and
  display, Unicode, ASCII and mixed prose, plus at least 240 mutants.
- **Mutation classes** (F's fault catalogue, D14), each mapped to its expected code, check
  kind and claim id:
  - arithmetic slip;
  - wrong operator;
  - power-of-ten error;
  - wrong substitution;
  - dropped factor (½, 2);
  - wrong rearrangement;
  - lost root;
  - unit-conversion error;
  - wrong prose restatement;
  - unbalanced equation (atom and charge);
  - wrong Boolean identity;
  - wrong truth-table row;
  - wrong base conversion;
  - sign error;
  - wrong comparison;
  - misstated given;
  - show-that target mismatch;
  - dimension error (warning);
  - plus rounding-only "mutants" that must pass.
- `tests/stem/test_corpus.py` acceptance criteria:
  - every correct answer: no INT-SUBJ-001, no INT-SUBJ-003, no INT-SUBJ-004, no error of any
    kind, and the original delivered verbatim;
  - every mutant in a decidable class: INT-SUBJ-001 (or the warning code its class
    specifies) on the right claim with the right check kind;
  - every relation in an out-of-scope class: named undecided with its reason;
  - the undecided rate on correct answers is reported per subject and stays under 10 % of
    relations;
  - the 13 silent passes observed before STEM support are all caught or named.
- `scripts/arena/stem_mutations.py` and `scripts/arena/run_arena.py`: STEM subjects and
  mutation injection in the arena harness for contained multi-agent runs. Overseer audits
  read receipts only.
- `tests/stress/test_stem_stress.py` (`-m stress`): the targets of section 13.
- `docs/STEM_RESULTS.md`: the measured results of the contained run, with no claims beyond
  them.

**Not run in this build.** The overseer audits of each stage's tests and the STEM arena with
live specialists. The STEM build runs as one integrated system with the main arena, which merges
this branch (round 7 when it is ready, otherwise round 8) and tests STEM there with a STEM lens
and a STEM fixer; its results go to docs/STEM_RESULTS.md, section "Integrated arena results".

---

## 17. Implementation stages (sequential; disjoint files)

`core` and `engine` may run in parallel. `checks` needs both. `branch` needs `checks`.
`corpus-eval` needs `branch`. Each stage ends with the full suite green, plus an overseer
audit of its own tests. No stage writes a file another stage owns.

**Status.** All five stages are implemented on `stem-build` and the full suite is green
(docs/STEM_RESULTS.md, section 8). The per-stage overseer audits were not run in this build;
they are folded into the integrated arena (section 16, "Not run in this build"). Beyond the
lists below, stage `corpus-eval` also touched front-end modules to fix readings the corpus
exposed (`checks.py`, `document.py`, `lexer.py`, `nodes.py`, `numbers.py`, `parser.py`,
`relations.py`, `scope.py`, `segment.py`, `spans.py`, `units.py`; docs/STEM_RESULTS.md,
section 7), each fix pinned by `tests/stem/test_reading_extensions.py`. The labelled fixture
corpus was committed right after this design and before any implementation.

### Stage `core`: math front end (no engine changes)

- `src/epinoic_logic/stem/__init__.py`
- `src/epinoic_logic/stem/README.md`
- `src/epinoic_logic/stem/limits.py`
- `src/epinoic_logic/stem/normalize.py`
- `src/epinoic_logic/stem/spans.py`
- `src/epinoic_logic/stem/segment.py`
- `src/epinoic_logic/stem/lexer.py`
- `src/epinoic_logic/stem/numbers.py`
- `src/epinoic_logic/stem/units.py`
- `src/epinoic_logic/stem/nodes.py`
- `src/epinoic_logic/stem/parser.py`
- `src/epinoic_logic/stem/scope.py`
- `src/epinoic_logic/stem/relations.py`
- `src/epinoic_logic/stem/chem.py`
- `src/epinoic_logic/stem/boolean.py`
- `src/epinoic_logic/stem/document.py`
- `tests/stem/__init__.py`
- `tests/stem/test_normalize.py`
- `tests/stem/test_spans.py`
- `tests/stem/test_segment.py`
- `tests/stem/test_lexer.py`
- `tests/stem/test_numbers.py`
- `tests/stem/test_units.py`
- `tests/stem/test_parser.py`
- `tests/stem/test_scope.py`
- `tests/stem/test_relations.py`
- `tests/stem/test_chem_parse.py`
- `tests/stem/test_boolean_parse.py`
- `tests/stem/test_document.py`
- `tests/stem/test_front_end_safety.py`

Exit: the front end reads every probe answer into a document with the expected statements,
ASTs, scope and planned check ids. The safety scan passes.

### Stage `engine`: named pack policies and the policy record (no IR schema change, no compiler change)

- `src/epinoic_logic/engine/policies.py` (`PACK_POLICIES = {"linear": DEFAULT_LIMITS,
  "nonlinear": Limits(allow_nonlinear=True)}`, `policy_limits(name)`, `NONLINEAR_RLIMIT`)
- `src/epinoic_logic/engine/results.py` (`VerificationResult.limits: Optional[Limits] = None`,
  set only when the Limits differ from `DEFAULT_LIMITS`; omitted from dumps when None, so
  existing results and signatures are byte-identical)
- `src/epinoic_logic/engine/runner.py` (records the non-default Limits on every result path)
- `src/epinoic_logic/engine/README.md`
- `tests/engine/test_pack_policies.py`
- `tests/engine/test_stem_shapes.py`

Exit: every encoding shape of sections 5 and 7 is decided as expected under its named policy,
within time; default results are unchanged.

Since the end-to-end simulation of 16 October 2026 a caller outside the process names the same
policy: `POST /v1/verify` and `epinoic-logic verify` take `policy` (`linear`, `nonlinear` or the
integrity layer's `joint`; `engine.policies.NAMED_POLICIES`, `named_policy`), applied exactly as
the channel applies it (the `rlimit` cap included), so a STEM check decides over HTTP as it did on
the channel. In that simulation seven STEM checks the channel decided under `nonlinear` came back
UNSUPPORTED (E201) over HTTP, because the request could not name the policy
(`tests/service/test_named_policy_over_http.py`). A pack still names only `linear` or `nonlinear`.

### Stage `checks`: AST to IR, the checks, and the data-booklet and constants tables

- `src/epinoic_logic/stem/constants.py`
- `src/epinoic_logic/stem/enclosures.py`
- `src/epinoic_logic/stem/scaling.py`
- `src/epinoic_logic/stem/tolerance.py`
- `src/epinoic_logic/stem/to_ir.py`
- `src/epinoic_logic/stem/checks.py`
- `src/epinoic_logic/stem/ENCODINGS.md`
- `tests/stem/test_constants.py`
- `tests/stem/test_enclosures.py`
- `tests/stem/test_scaling.py`
- `tests/stem/test_tolerance.py`
- `tests/stem/test_to_ir.py`
- `tests/stem/test_checks_engine.py`
- `tests/stem/test_checks_no_false_errors.py`
- `tests/stem/test_checks_safety.py`

Exit: every check kind of section 8.1 is built as a `PlannedCheck` and decided correctly
through `verify`. No false error appears on the no-false-error set. Undecided cases carry the
right ST code.

### Stage `branch`: parser, pack, registry, profiles, eligibility, channel, end to end

- `src/epinoic_logic/adapters/stem_specialist/__init__.py`
- `src/epinoic_logic/adapters/stem_specialist/parser.py`
- `src/epinoic_logic/adapters/README.md`
- `src/epinoic_logic/stem/si_reading.py`
- `src/epinoic_logic/stem/hub_hooks.py`
- `src/epinoic_logic/branches/stem_pack.py`
- `src/epinoic_logic/branches/base.py`
- `src/epinoic_logic/branches/registry.py`
- `src/epinoic_logic/branches/packs.py`
- `src/epinoic_logic/branches/quant.py`
- `src/epinoic_logic/branches/README.md`
- `src/epinoic_logic/channel/bus.py`
- `src/epinoic_logic/channel/request_parser.py`
- `src/epinoic_logic/channel/README.md`
- `src/epinoic_logic/translate/subjects.py`
- `src/epinoic_logic/translate/eligibility.py`
- `src/epinoic_logic/integrity/ledger.py`
- `src/epinoic_logic/integrity/README.md`
- `src/epinoic_logic/version.py`
- `README.md`
- `tests/stem/test_parser_claims.py`
- `tests/branches/test_stem_pack.py`
- `tests/branches/test_stem_routing.py`
- `tests/branches/test_quant_si_reading.py`
- `tests/branches/test_hub.py` (line 46 only: recorded behaviour change)
- `tests/branches/test_quant_and_packs.py` (line 76 only: recorded behaviour change)
- `tests/channel/test_branch_check_mapping.py`
- `tests/channel/test_stem_channel.py`
- `tests/translate/test_stem_subjects.py`
- `tests/translate/test_stem_eligibility.py`
- `tests/integrity/test_stem_ledger_figures.py`
- `tests/e2e/test_stem_e2e.py`

Exit: the observed case and the 13 probe answers behave as section 16 states. The suite is
green. The stage report lists the two routing assertions.

### Stage `corpus-eval`: corpus, arena mutations, stress

- `tests/stem/test_corpus.py`
- `tests/stem/data/stem_corpus.json`
- `scripts/arena/stem_mutations.py`
- `scripts/arena/run_arena.py`
- `tests/stress/test_stem_stress.py`
- `docs/STEM_RESULTS.md`

Exit: the acceptance criteria of section 16 are met and measured; the results are written
with no claim beyond what was run.

---

## 18. Version bumps and recorded behaviour changes

All version bumps are made in stage `branch`, in `version.py`:
- **ENGINE_VERSION 0.2.0 → 0.3.0:** the result records non-default Limits (stage `engine`).
- **POLICY_VERSION 2026.10-v2 → 2026.10-v3:** named pack policies; alias and word-boundary
  changes; the new `stem` profile; eligibility rule 4.
- **TRANSLATOR_VERSION 0.2.0 → 0.3.0:** the STEM profile text.

IR_VERSION stays 1.0.

The fixes of the external review of 12 October 2026 bumped all three again (ENGINE_VERSION 0.4.0,
POLICY_VERSION 2026.10-v4, TRANSLATOR_VERSION 0.4.0; history in `version.py`), and every result now
also binds the build, schema and policy identity (`engine/identity.py`), so a STEM result of an
earlier release is never taken as current. For the STEM checks: the unsat core is always computed,
the binding covers non-default limits (item 13 of section 15), and the encoding devices grounded
`arithmetic_fact` are listed as unverified dependencies (section 7.6). No STEM decision changed.

Recorded behaviour changes, for the overseer audit and the user's sign-off:
1. STEM subjects route to the `sciences`, `mathematics` and `computer_science` branches
   instead of `generic`, which changes two existing assertions (section 10.2).
2. A branch check whose ENTAILED result carries E108 is now undecided, not ok.
3. A check expecting UNSATISFIABLE that comes back SATISFIABLE is now failed, not undecided.
4. Subject aliases match on word boundaries.
5. INT-SUBJ-001 and INT-SUBJ-002 now carry claim ids.
6. New codes: INT-SUBJ-004 and BR-INTERNAL-001.

Every other non-STEM behaviour is unchanged by construction (P5).

---

## 19. Refinements made during implementation

The sections above now describe the code. These are the points where the implementation
refined or departed from the original design text, collected for the overseer audit:

1. **Relation outcomes.** Five outcomes, not three: `check`, `undecided`, `binding`, `formula`
   and `context` (section 1, item 2; section 4.7).
2. **Claim ids per branch.** `s<p>.<n>` in `sciences`, `m<p>.<n>` in `mathematics`, `c<p>.<n>` in
   `computer_science`, so two STEM branches never share a claim id on one task. The parser
   takes the request text from the channel (`accepts_request_text`), and a heading line with
   no content of its own is role `structural` (section 9).
3. **Hub hooks.** Every hook method takes the subject profile key; `coverage_terms` also offers
   computing command words for a claim that holds a planned computation; the channel guards
   every hook call (section 11).
4. **Engine bounds for the nonlinear policy.** `rlimit` is capped at `NONLINEAR_RLIMIT`
   (a lower caller value is kept), and assertions above polynomial degree 24
   (`NONLINEAR_MAX_DEGREE`) are refused with E201 before compiling (D2).
5. **Check budget.** The STEM checks of one report run under an 8 s wall-clock budget; checks
   left when it is spent are INT-SUBJ-002 (section 11.2).
6. **Failure severity.** `stem-sub`, `stem-cnv` and `stem-res` also fail at warning severity
   (INT-SUBJ-004) when a D3b booklet value was used or a unit was unknown, as `stem-eq` does
   (section 8.1).
7. **Truth tables** are decided as an entailment (Form E), not a satisfiability query
   (sections 7.7 and 8.1).
8. **Withheld relations.** A relation whose operands the front end may have cut is withheld
   with ST-PARSE-001 rather than decided (section 8.1).
9. **Readings added by the corpus.** Σ over integer bounds (at most 24 terms) is read as its
   terms; order chains, ratio equalities, factorisations inside a chain, functions and
   derivatives evaluated at a point, Boolean name definitions and truth-table columns they
   head are read; `ms⁻¹` has two readings; complex values are named undecided (sections 4.5,
   4.7, 6.3; docs/STEM_RESULTS.md, section 7).
10. **Spans and statements.** Chemical equations and bare quantities are span kinds;
    derivation lines are statements, not spans (sections 4.2 and 4.3).
11. **Bounds.** ST-LIM-002 also names math spans beyond 1,024 per report; the IR bounds of the
    checks stage are in `to_ir.IR_LIMITS` (section 4.9).
12. **Safety enforcement.** `stem/` imports nothing from `ir/` or `engine/` (problems leave it
    as data); three AST scans enforce the rules over `stem/`, the STEM adapter, the STEM pack,
    the hub hooks, the SI reading and `quant.py` (section 14).
13. **Quant reading.** `QuantReading(name, si, profile)` switches the SI rules; the SI patterns,
    views and statements live in `stem/si_reading.py` (section 12).

Known gaps measured at the end of the build (for example `yr` missing from the unit table,
function names other than `f`, `g` and `h` read as products, `|\vec{v}|` unparsed, exponential
equations undecided) are listed in docs/STEM_RESULTS.md, section 9.

---

## 20. Merged with the round-7 development branch (one translator)

The STEM branches were built on a fork taken at arena round 4. The merge into the development
branch, which carries the verified round-5 to round-7 arena fixes, makes them one translator:
Physics, Chemistry, Biology, ESS, Mathematics (AA and AI) and Computer Science answers go through
`StemTextParser`, and every rule round 7 added to the generic parser for those subjects is kept
by it. On the round-7 answers the STEM parser delivers the generic parser's claims claim by
claim (the same texts, roles, proposed kinds, figures, quotations, materiality and supports)
under the STEM ids, and the hub reads the same request items
(`tests/stem/test_merge_round7.py`).

### 20.1 Layout rules (`stem/layout.py`, `spans.py`, `segment.py`)

The round-7 rules that decide where a claim starts and ends are the generic parser's, restated
in `stem/layout.py` (the STEM package imports nothing from `branches`;
`tests/stem/test_layout.py` asserts the patterns are the same):

- a line that opens with `=` or `≈` continues the equation of the line before it, and a line
  after a comma or a connective, or a soft-wrapped prose line, continues its line; every other
  line break ends a statement, so each line of working, list item, table row and result is a
  statement of its own (an equation continued over three lines is one derivation statement,
  its links still read across the lines);
- part labels and label-only lines (`(a) [2]`, `Part (a) — find — 3 marks`) and mark
  annotations (`[1]`, `[1 spare]`, `  M1`, `(A1)`) are furniture: blanked from the statements
  (and from the claim texts, which leave interior markup out), never read as maths;
- a table is one statement per row; the separator row is furniture.

### 20.2 Roles (`adapters/stem_specialist/parser.py`)

The roles, materiality and supports are the generic branch's round-7 reading
(`generic_parser.assign_roles`, run on units built from the STEM statements): notes, questions
and headings are `other`; the answer of each part is material; a consequence or a judgement
rests on the claims before it; a caveat is no support; supports never form a cycle. The STEM
refinements of section 9.2 apply on top only where round 7 did not rule: a code block is a
material point; a "Given:" or "Working:" heading and a table header row with no words are
`structural`; a binding or a law is `evidence` when the answer presents it as given (under a
"Given:" heading, led by "Given", "Taking" or "Using", or where the generic reading would take it
for the paragraph's point), while a law or a binding written as a line of working ("V = ε − Ir"
over its substitution, "At rest means v = 0:") keeps the round-7 role; a judgement that restates
a checked result is `quantitative`; a reason sentence is a `link`. Two section 9.2 behaviours
change with the merge: a link supports the point and rests on nothing (no support cycle,
CORE-STR-001), and a consequence rests on the claims before it.

### 20.3 Request items

A multi-part request yields one item per part on every branch (the round-7 rule). The STEM
imperatives still split sentences, but the rubric's "Show your working (with units)." or "Show
full working." is no item (`channel/request_parser._SHOW_WORKING_RE`).

### 20.4 Readings corrected (false INT-SUBJ-001 on genuine round-7 answers)

Each was fixed where the reading went wrong; the same fault written into the same line is still
named (`tests/stem/test_round7_false_errors.py`):

1. A thousands group inside brackets is one numeral when it is an operand of arithmetic
   (`(1,000 ÷ 2^10 = 0.98)`); a list or a pair stays separate numbers (`lexer._thousands_operand`).
2. A stated value with its absolute uncertainty (`1620 − 20 = 1600 ± 32 counts min⁻¹`) is a band:
   the computed value must lie in it (`checks._uncertainty`; only a binary `±` between two written
   values stated for a computed side with no `±`).
3. A power written after a value continues the run (`1600 e^(−8k)`, `C0 e^(−kt)`).
4. A line that writes the preceding relation with values put in (`1/R = 1/R₁ + 1/R₂`, then
   `1/R = 1/4.0 Ω + 1/6.0 Ω`) reads the written values for the symbols (substitution readings),
   so the step is checked with them (`relations._premise_substitution`).
5. A symbol reused in a later part for a value the request gives (`R = 2.4 Ω` in (a), the 6.0 Ω
   resistor in (d)) is read there, not checked against the other part's binding; a value the
   request does not give is still checked (`relations._given_in_another_part`).
6. The order relations of a sentence stated under a condition (`For 2 < t ≤ 3, …, so v < 0.`) are
   context, not claims about the values stated for t and v elsewhere (`_CONDITIONAL_RE`).
7. A prose value after a result cue restates the last chain before it in its part, and only a
   chain that computes a value: never an older chain past one that ends on an order relation,
   never a value stated for a symbol (`relations._results`).

### 20.5 Readings added (the round-7 STEM mutations)

All 15 STEM mutations of the round-7 answers are named with their code on the injected claim
(`tests/stem/test_round7_mutations.py`):

1. A word formula in brackets (`(final − initial) ÷ initial × 100 = (80 − 40) ÷ 40 × 100 = 100%`)
   is part of its run (`spans._RunFinder.mathy_operand`).
2. A written evaluation of a formula the answer states in the part, in a shape the formula does
   not repeat (`a = dv/dt = 6 − 6t`, then `At t = 1: a = 6 − 6(1)`), is checked as the formula under
   the stated values (a `sub` check that evaluates, Form S over the bindings); a formula with `±`
   is not evaluated (its roots are checked by `stem-sol`). The formula stated through a derivative
   is kept; the derivative itself stays undecided (section 7.8).
3. An indefinite integral of a polynomial with the antiderivative the answer states
   (`∫6t dt = 3t²`, a constant of integration allowed) is an `alg` check from the trivially true
   premise `D = D` to `D = integrand`, where D is the derivative of the stated antiderivative.
   **The STEM pack forms D by the power rule (`stem/calculus.py`, exact rational coefficients),
   not the engine**; the check description says so, and the engine decides that the two
   polynomials agree for every value of the variable. Definite integrals, non-polynomial
   integrands and derivatives stay outside the encodings.
4. A step between two relations in which one unknown appears only in powers of e with integer
   multiples of it of one sign (`800 = 1600 e^(−8k)`, then `e^(−8k) = 1/2`) is read in
   `u = e^(−k)` with `u > 0` (an exact change of variable; the relation records it in
   `positive` and the check adds the side condition).
5. Computer Science: a trace step that gives a variable a value in prose ("mid = 1 gives 3 < 9,
   so low moves to 2") is checked against the update rule the answer states for that variable
   earlier in the part (`low = mid + 1`), when the step's own clause states a value for every
   other variable of the rule (`relations._assignments`).

The arena harness's marker for a substitution stays inside one statement: it stops at the end of
its sentence and leaves a closing mark annotation out (`scripts/arena/stem_mutations._link_marker`),
as every claim does under the round-7 rules; the mutated texts and the expected codes are
unchanged.

### 20.6 Tests changed by the merge

Each was rewritten to assert the same behaviour as strictly or more strictly, or to the round-7
rule where the two branches disagreed (listed with the reason in the merge record):
`tests/adapters/test_overseer_round7.py` (claim-id test: STEM letters plus claim-by-claim
equivalence with the generic parser), `tests/channel/r7_support.py` and
`tests/channel/test_round7_fixes.py` (recorded ids resolved through the generic parser's numbering
of the same claims), `tests/channel/test_stem_channel.py` and `tests/stem/test_hub_hooks.py` (one
item per part on the default reading), `tests/stem/test_parser_claims.py` (no support cycle; a
consequence rests on earlier claims), `tests/stem/test_segment.py` and
`tests/stem/test_relations.py` (an equation continued over lines is one statement; one statement
per table row), and `tests/branches/data/quant_general_reference.json` (the GENERAL reading's
reference regenerated on the development branch; byte identity still required).

---

## 21. Detection fixes from the end-to-end simulation (run1)

The end-to-end simulation of the website-to-backend flow (sixteen specialists, the arena harness on
their genuine answers) left six injected faults unnamed. Each was traced to its cause; the answers
are kept as test data (`tests/channel/data/e2e_run1_material.json`) and every fix is pinned by
`tests/stem/test_e2e_run1_detection.py`. All six are now named, each as the harness injects it (the
injection is the base one; 21.3), and none is excused: an injection no finding names is a miss.

### 21.1 Gaps in the checks

1. **Decimal and fractional powers of a closed value** (ch-e1b: `[H⁺] = 10^(−8.2) = 9.31 × 10⁻⁹`,
   and the same line with the pH substituted wrongly). The exponent reader named every non-integer
   exponent 'a fractional or decimal power', so no pH line was checked. A closed base with no unit
   raised to a closed exponent that is no integer is now a `RealPower` node (`nodes.py`,
   `parser._real_power`): the exponent's tokens may be figures, signs, operators, brackets and
   `\frac` only, and the base and the exponent must hold no symbol, unit, angle, per cent or `±`.
   A rational value is exact, as the exact-value table gives `sin 30° = 1/2`: a positive rational
   base whose numerator and denominator are exact q-th powers for the exponent p/q
   (`16^(3/4) = 8`, `4^1.5 = 8`, `(8/27)^(2/3) = 4/9`; `enclosures.exact_real_power`, exact integer
   roots, at most 30 digits), so `x² = 16^(3/4) ⇒ x = ±2√2` is proved exactly. Any other value
   (`10^(−8.2)`, `2^(−3.5)`) is the enclosure of `exp(x·ln b)` for a positive base (`to_ir._real_power`),
   cross-checked against `math.pow` within 10⁻⁹ of the value; `0^x` with x > 0 is 0; a zero base
   under an exponent that is not positive is ST-UNDEF-001 and a base that is or may be negative
   ST-UNDEC-001 (which real power the writer means is not chosen). A check that uses the enclosure
   is Form S, so correct work within the tolerance band passes (`10^(−8.2) = 6.31 × 10⁻⁹` holds) and
   the slip does not. An algebra or inequality step that holds such an irrational power stays
   undecided (ST-UNDEC-001, the power named), as every step did before the power was read: a step is
   compared exactly (only a side that is one written value gets a band, section 8.1), so
   `I = I₀ × 2^(−3.5) = 0.088 I₀`, correct to 2 s.f., could only become a false error. A symbolic
   exponent (`10^(−pH)`) and a symbolic or dimensioned base stay undecided as before (a power of e of
   an expression in symbols is read in a model evaluation only, item 5).

   **The antilogarithm of a concentration scale** (the ch-e1b substitution as injected:
   `[H⁺] = 10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³`, the pH 8.2 substituted as 5.2). A calculation with no unit
   stated in a unit is read as written and in SI (section 6.4). For a lone power of ten that reading
   is blind to a class of faults: every unit prefix is an integer power of ten, so the power read as a
   bare number in SI (10^(−5.2) mol m⁻³) matched the stated 6.31 × 10⁻⁹ mol dm⁻³ exactly, and an
   exponent 3 too small, the injected substitution, passed. A lone power of ten with no unit
   (`10^(−8.2)`, `10^{-5.8}`, and the integer `10^(−7)` too) set against a value in a unit of
   concentration is now the concentration in mol dm⁻³, the unit the pH, pOH, pKa and pKb scales are
   defined in, and is compared with the stated value in SI only (`checks._antilog_as_concentration`;
   the reading is named "the power of ten read in mol dm⁻³"). The recorded injection is UNSATISFIABLE
   (INT-SUBJ-001 on s1.2), and so are the same fault 10³ the other way (`= 6.31 × 10⁻¹² mol dm⁻³`) and
   an integer pH substituted (`10^(−4) = 1.0 × 10⁻⁷ mol dm⁻³`); the genuine lines hold, and so does the
   same concentration stated in any unit of concentration (`10^(−3.3) = 0.501 mmol dm⁻³`,
   `10^(−8.2) = 6.31 × 10⁻⁶ mol m⁻³`, `5.01 × 10⁻⁴ M` in chemistry). Every other calculation keeps both
   readings of section 6.4: a power of ten stated in a unit of another dimension (`E = 10^(13.8) =
   63 TJ`, the Richter energy in joules; `V = 10^(−3) = 1 dm³`), a per cent, `M` where it may be mega,
   and a product or quotient (`[OH⁻] = 10^(−14)/10^(−8.2)`). So a unitless product stated in a prefixed
   unit still absorbs an error of exactly the unit's factor (`c = 0.25 × 4 = 0.001 mol dm⁻³` passes in
   SI): the documented reading, which no injection of the harness produces.
2. **The LaTeX thin space between digit groups** (mai-e1: `21\,131.40 - 18\,000 = 6131.40`). The
   number reader knew the Unicode thin spaces but not `\,`, so every operand written with it was cut
   ("unexpected '131.40' after an operand") and the answer had no check at all. `scan_number` now
   reads `\,` between an integer part of one to three digits and groups of exactly three as a
   thousands separator, one kind of separator throughout; anything else stays LaTeX spacing.
3. **A relayed specialist named by its subject** (hi-e1a: `The Mathematics specialist states that
   "the model is not aly good fit for 1923"`). A relayed report authored by
   `mathematics-aa-specialist` was named only "mathematics aa specialist", so the router's own name
   for the colleague in its hand-off ("attribute them to the Mathematics specialist") named no text:
   the misquotation was credited to none and only reported unverifiable (CORE-SRC-003, a warning).
   `adapters.sources.specialist_names` adds the subject's first word ("mathematics specialist") when
   the agent id names a course or qualifier after it, and for Mathematics the spellings "maths
   specialist" and "math specialist"; the History, English and STEM parsers and the
   crediting rules share it, so the quotation is credited to the colleague's report and refuted
   there (INT-REQ-003, naming the altered word). A sentence that names no text keeps the earlier
   rule (unverifiable unless an own supplied text holds the words).
4. **An integer power beyond 12 of a closed value, and a value stated in prose for a named
   quantity** (mai-e1 substitution: `18\,000 = M \times \frac{1-(1+\frac{0.065}{12})^{-60}}{\frac{0.065}{12}}`
   → `\frac{4-…}`). Two gaps kept the changed equation from any check. First, the integer-power
   bound (12, section 4.9) made `(1 + 0.065/12)^{-60}` unsupported although its base is a closed
   value. A closed base with no unit raised to an integer beyond 12, up to 1000, is now one value: a
   `RealPower` whose exponent is the written integer (`parser._make_pow`). The encoder writes its
   exact value when it fits one literal (`2^{20} = 1048576`, `(−1.5)^{13} = −1594323/8192`: an
   integer power of a negative base takes the sign of its parity), and otherwise the outward-rounded
   interval power of the base (`Interval.power`, decided in Form S: `1.003^{144}`), refusing a value
   beyond about 10^±300 (ST-UNDEC-001) and a zero base under a power that is not positive
   (ST-UNDEF-001). A power of an expression in symbols keeps the bound (it is a polynomial of that
   degree), so the nonlinear policy's degree bound is unchanged; a step that holds an enclosed power
   stays undecided, as one holding an irrational power does (item 1). Second, the answer states M's
   value only in prose, under the name it gave the symbol: "Let $M$ be the monthly payment in
   euros." … "Her monthly payment is €352.19." Such a value is now a stated root of the equation in
   that symbol (`relations.named_quantities`, `_described_roots`): checked by `stem-sol`
   (membership), so the changed equation, whose root is 29.75, is refuted with INT-SUBJ-001 on m3.1
   and m5.1, and the genuine one (root 352.1907) holds. The reading is narrow, so a misreading never
   decides anything:
   - the definition is one letter, in inline maths or not, after "let" or "letting" (with be,
     denote, represent or stand for), after "where" or "with" (with is, =, denotes, represents,
     stands for, or no verb), or opening its statement (with is, denotes, represents or stands for),
     then a determiner and words only; the description stops at a figure, sign or bracket and
     before a relative clause or a conjunction, and a trailing "in <unit>" also gives the shorter
     name ("monthly payment in euros", "monthly payment");
   - the clause that states the value is that description word for word, with at most a connective
     and a determiner or possessive before it and a verb of identity (and a currency sign) after it;
     its sentence opens with no condition ("If the rate is 5%, the monthly payment is …" is not
     read); and nothing follows the value to the end of the sentence but a currency, time or count
     word, a rounding note or a mark annotation: no qualifier, negation, comparison or question;
   - the value is a decimal with no unit (a whole number in prose may be a count the context
     rounds up or down, as 16 buses for 15.3); the symbol has no value stated in maths anywhere in
     the answer; the definition is in the value's part (or in none), and the equation is the latest
     one written before the value in that part whose one unknown is the symbol, with no unit, sign
     choice, construct outside the encodings or function of the unknown;
   - a prose value is approximate by nature, so the root ranges over its rounding interval widened
     by the '=' slack of R2 (τ = 1/100 of the value): a payment rounded up a cent holds, the changed
     annuity factor (twelve times the payment) does not. The failure severity is error: both
     statements are the report's own, read word for word.
5. **An exponential model evaluated at an argument** (the maa-e1a substitution:
   `(b) P(t + 1) = P₀e^(k(t + 1))` → `P(t + 4)`). Three readings kept the changed link from any
   check: `P(t + 4)` was the product P·(t + 4) (a function name other than f, g and h is no function
   to the parser), a power of e of an expression in symbols was outside the encodings, and the request's
   model `P = P₀e^(kt)` names no variable. A **model** is now a function of one variable defined with
   a power of e, or of a positive closed base, whose exponent holds symbols: `P = P₀e^(kt)` in the
   request, `C(t) = C0 e^(−kt)` or `A(t) = 500 × 2^(t/3)` in the answer (`models.py`; kept apart
   from the formulas, which are premises of steps and substitutions). Its variable is the one it names,
   else the one symbol of its expression that the answer's applications put an argument in for
   (`P(t + 1)` and `P(t)` name t; a run the answer declared as one name, `kt` after `kt = ln 2`, is read
   as the product of its letters when only that names the variable). An **application** is the model's
   letter glued to a bracket that holds exactly the argument (`P(t + 4)`, `P(6)`; not `P (t + 4)`), told
   apart from a product by the written text alone. An equality with an application becomes a
   `stem-mod` check, the model's expression at the written argument against the other side: some value
   of the variables (the model's variable and every symbol with no stated value), and of the stated
   symbols within their stated values, must satisfy it (Form S). The encoder reads every power B^X of
   an exponent in symbols through positive variables: with X = c + Σ qᵢ·mᵢ (c rational, qᵢ rational,
   mᵢ distinct monomials) and sᵢ the largest step of which every coefficient of mᵢ in the link is an
   integer multiple, B^X = B^c · Π uᵢ^(qᵢ/sᵢ), uᵢ = B^(sᵢ·mᵢ) > 0, bounded by the enclosure of
   B^(sᵢ·range) when every symbol of mᵢ has stated values. Every real solution gives such uᵢ, so the
   reading only widens the solutions: UNSATISFIABLE proves that no value satisfies the link, and
   SATISFIABLE never claims that it holds for every value. The changed link asks
   `P₀e^(k(t + 4)) = P₀e^(k(t + 1))`, that is 250·u₁·u₂⁴ = 250·u₁·u₂ with u₂ = e^k in [e^2.045, e^2.055]
   (k = 2.05 to 3 s.f.) and u₁ = e^(kt) > 0: UNSATISFIABLE, INT-SUBJ-001 on m3.1. The genuine
   `P(t + 1) = P₀e^(k(t + 1))` and `P(6) = 250e^(6k)` hold, and round 7's maa-p7b gains three such
   checks (`C(8) = 800`, `C(T) = ½C0`, `C(40) = 1600 × 2^(−5)`), each satisfiable. The reading is
   narrow, so a misreading never decides anything: only `=`; no written decimal on either side or in
   the model (a rounded figure would need its rounding interval: `N(t + 5) = 0.5 N(t)` holds only
   within it), no unit and no other construct outside the encodings; exponents are polynomials with
   rational coefficients (degree at most 4, at most 8 monomials per base, no power beyond 12 of one
   variable); a base is e (mathematics and Computer Science readings only: in the sciences e may be
   the elementary charge) or a positive rational; the model's own definition is no check; and a model
   whose variable no application names (`P(6)` alone could stand for t or for k) gives none. A
   description ("Let t be the number of months") is not read for the variable: it can name a
   parameter as readily. The superscript letter of `eᵏ` is still outside the grammar (the span ends
   there), so the rest of that chain keeps its reading.

   A letter defined as two models (`Model A: N = 100e^(t/5)`, `Model B: N = 100 × 2^(t/3)`) is read in
   each definition: one pair of sides per combination of the definitions of the letters a link applies
   (at most 4), and the link must hold in one of them, so no definition is chosen for the answer
   (`Model B: N(t + 3) = 2N(t)` holds whichever is stated last; `N(t + 3) = 3N(t)` holds under neither).
   A definition whose variable nothing names (`P = 250e^(6k)`, an evaluation written as a definition)
   is none.

   **Steps over applications** (found while measuring this item; at 22d6a5b too). Every application of
   a letter other than f, g and h is a product to the parser, so consecutive evaluations of a function
   were an algebra step under that reading and refuted: `N(10) = 200`, then `N(15) = 100`, was
   `10N = 200 ⊢ 15N = 100`, an error on correct work, and so were `C(2) = 13`, `C(3) = 18` after
   `C(t) = 5t + 3` and `N(t + 1) = 2N(t)`, `N(t + 2) = 4N(t)` after `N(t) = 100 × 2^t`. A letter the
   request or the answer defines as a function of one variable (`C(t) = …`, the letter glued to a
   bracket holding one symbol that the right side uses; or `P = P₀e^(kt)`, `V = 20000 × 0.8^t`, a power
   whose exponent holds symbols) is now read as f is (section 4.7): an evaluation at a value
   (`N(15) = …`) is no step, and a step whose relations hold an application at an unknown is
   ST-UNDEC-001 ("a step involving an application of a function the text defines"). Each evaluation is
   still checked by itself where the model reading covers it (`stem-mod`), and a bracket after a letter
   the text does not define as a function keeps its product reading and its steps (`ε = I(R + r)`, then
   `I = ε/(R + r)`).
6. **Unit exponents written in ASCII** (the independent verification of this repair). `3 m s-1` was
   `3 m s − 1`, a subtraction of a bare number from a quantity, so correct work in ASCII units was an
   error before any of these fixes (`v = 6 ÷ 2 = 3 m s-1` refuted with c = 3, r = 2;
   `c = 0.5 × 2 = 1 mol dm-3` with r = −2), and the decimal powers of item 1 stated that way
   (`[H+] = 10^(-3.3) = 5.01e-4 mol dm-3`) became errors as soon as the power was read. An exponent
   glued to its atom is now the atom's power (`parser._ascii_unit_exponent`, `units.parse_unit(...,
   ascii_exponents=True)`): a hyphen-minus or plus and one digit (`s-1`, `dm-3`, `J kg-1 K-1`,
   `mol2 dm-6`), one digit 2 to 9 after an atom of two or more letters (`cm3`, `dm3`), and one such digit
   after a slash (`m/s2`, `kg/m3`). Never read so: more digits or a decimal (`300 K-273`), a space on
   either side of the sign, a sign followed by an atom of the same dimension (`5 m-3 m = 2 m` stays a
   subtraction of lengths), and a one-letter atom's glued digit right after a number (`2 m2` may be
   2·m₂, and `H2` is a formula). The span finder reads such a digit as part of the unit, and only the
   parser asks for the reading: the translator's typed quantities, the SI reading and the segmenter
   read a digit inside a unit as before.

### 21.2 A harness defect (`scripts/arena`)

7. **The part label in the marker** (maa-e1a substitution: `(b) P(t + 1) = P₀e^(k(t + 1))` →
   `P(t + 4)`). The marker kept the part label "(b) ", which no claim carries, so no injected claim
   was found; it now leaves a part label out as it leaves a mark annotation out, and m3.1 carries it.
   With the model evaluation (item 5) the injection is named on m3.1.

### 21.3 A rule withdrawn: no injection is excused

An earlier fix for items 4 and 6 reported a STEM injection no finding names as NOT APPLICABLE
(outside the transport count) when the harness's own regular-expression reading found a symbol with no
"x = value" binding in the changed expression and no formal check moved. An independent
verification showed that it excused real misses: values stated in prose ("a ball of mass 0.50 kg",
"a spring of constant 200 N m⁻¹") were never read, so a substitution of the request's g in
`E = m × 6.81 × 20 = 98.1 J` and a slip in `E = 0.5 × k × 0.15² = 5.25 J` were reported not
applicable (27 of 27) where 22d6a5b counts both as misses (27 of 29). In maa-e1a, k and P₀ are
stated, and in mai-e1 the answer states M's value in prose: both misses came from limits of the
encodings (items 4 and 6), not from injections that cannot apply. The rule is withdrawn: every injection no finding names is a failure, and when the receipt names the injected
claim undecided the reason quotes it (`run_arena.undecided_on`, `undecided_on_injected_claims`).
Those two probe misses remain gaps of the encodings (a value stated in the request's prose for a
symbol the answer uses without naming it), counted as misses.

A second change of the harness is withdrawn as well. An earlier version of item 1 changed the
injection instead of the reading: a figure written as the exponent of a power of ten moved its first
decimal digit (`10^(−8.2)` → `10^(−8.5)`) and an exponent with no decimal digit was no site, because a
change of the leading digit (8.2 → 5.2) is a factor of 10³ that the SI reading absorbed. That made
the run1 count rise while the recorded fault, `10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³`, still passed as a
satisfied check, and a test asserted that it passed. The injection is again the base one (the leading
digit of every figure moved by 3, an exponent of ten included; `stem_mutations.py`), the fault is named
at its cause (item 1), and the test asserts the error.

### 21.4 Tests changed

- `tests/fixtures/stem/corpus/stem-math-020.json` (and its copy in `tests/stem/data/stem_corpus.json`):
  the fractional-power fault `16^(3/4) = 16 × 3/4` was expected as undecided (ST-PARSE-001 or
  ST-UNDEC-001); the engine now refutes it (16^(3/4) is exactly 8), so it is expected as
  INT-SUBJ-001 alone from the arithmetic check (`FIXTURE_LABELS` in `tests/stem/data/corpus_items.py`
  pins the check kind `eq`), a stronger label. The fixture README records the change.
- `tests/stem/data/corpus_items_more.py` (`math-fracpow-1`): the relation
  `16^{3/4} = (\sqrt[4]{16})^3` is still named undecided with ST-UNDEC-001, now for the fourth root
  alone ('root of index 4'), since `16^{3/4}` is read; the corpus was rebuilt (two labels changed,
  558 items as before).
- `tests/stem/test_e2e_run1_detection.py`: the tests of the withdrawn rule (21.3), which asserted that
  the maa-e1a and mai-e1 substitutions were not applicable, are replaced by stricter ones: the mai-e1
  substitution is named INT-SUBJ-001 on m3.1, the verification's two probe misses are counted (27 of
  29), and with no finding allowed to name anything every injection of the round is a failure.
- The same file, after the second verification: the tests of the withdrawn injection change (21.3)
  are replaced by stricter ones. The test that asserted that `10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³` is no
  error now asserts that it is one, with six more faults of that kind; the ten cases of the withdrawn
  `figure_change` are replaced by four injections the base harness makes into exponents of ten, each
  named; the ch-e1b substitution is asserted as recorded (`10^(−5.2)`, UNSATISFIABLE on s1.2); and the
  tests that asserted the maa-e1a substitution as a miss now assert it named (INT-SUBJ-001 on m3.1 by
  `stem-mod`), with the genuine answer's model evaluations holding and the contained round naming all
  six faults (stem_substitution 3 of 3). Controls pin the concentration reading's limits (a volume,
  an energy, a per cent and an ambiguous `M` keep both readings of section 6.4). The test that a
  contained round with no finding allowed to name anything fails every injection now also asserts
  the failure reason of every injection the receipt names undecided (it quotes the receipt's
  ST-UNDEC findings and still counts the miss), which the replaced maa-e1a miss test asserted for
  that record.
- New: `tests/stem/test_ascii_unit_exponents.py` (item 6: correct work in ASCII units holds, faults in
  them are errors, the subtractions and the one-letter forms that keep their reading, and the unit
  table read with the exponents only when the parser asks) and `tests/stem/test_model_evaluations.py`
  (item 5: model evaluations with no solution are errors, correct ones hold, a letter defined as two
  models is read in either, round 7's maa-p7b gains three checks that hold, the links the reading
  does not cover keep their old reading, consecutive evaluations of a function the text defines are
  no algebra step while a fault in one of them is still named, and a bracket after a letter that is
  no function keeps its product reading and its step).
