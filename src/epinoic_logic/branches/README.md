# branches — one hub, a branch per subject, an integrity pack in each

The router talks to every specialist (English, History, Psychology, Economics,
Business Management, and any subject added later) through the same hub. What differs
by subject lives in a branch:

```
                 ┌────────────────────────── hub integrity (shared) ───────────────────────────┐
router ──► RouterHub ──► TranslatorChannel: envelope · hand-off · request fidelity · constraints ·
                 │        claim verification · ledger · staleness · cross-agent consistency · signing
                 │
                 ├── branch english ............ profile + English adapter + [core pack, English pack]
                 ├── branch history ............ profile + History adapter + [core pack, History pack]
                 ├── branch psychology ......... profile + generic parser + [core pack, Psychology pack]
                 ├── branch economics .......... profile + generic parser + [core pack, Economics pack]
                 ├── branch business_management  profile + generic parser + [core pack, Business pack]
                 └── branch generic ............ profile + generic parser + [core pack, generic pack]
```

| Module | Role |
| --- | --- |
| `base.py` | `SubjectBranch` (profile keys, parser factory, integrity packs), `IntegrityPack` protocol, `FormalCheck`, `BranchRegistry` (subject label → branch, generic fallback). |
| `quant.py` | Finds a report's own quantitative statements (a from/to pair with a stated percentage change, percentage-point difference, word fraction or fold change; shares; totals) and builds exact entailment problems; the engine then says whether the specialist's arithmetic holds. No model is involved. |
| `packs.py` | `CorePack` (every branch: quotation grounding, numeric self-consistency, from-memory labelling, unverifiable / undelimited / misattributed quotations, undecided chronology, self-certification), `HistoryPack` (pack rules + request-aware suppression), `EnglishPack`, `PsychologyPack` (study attributions need grounding; "significant" needs a figure), `EconomicsPack` (elasticity arithmetic), `BusinessPack` (margins), `GenericPack`. |
| `registry.py` | The default registry and how subjects map to branches. |
| `generic_parser.py` | Fallback sentence-level parser for subjects without a dedicated adapter. |
| `hub.py` | `RouterHub`: open a task from a work plan, dispatch requests, receive raw text or structured reports, read receipts. |

## The report's own arithmetic (`quant.py`)

A sentence that states a from/to pair and a derived figure becomes one entailment
problem whose premises are the stated figures and whose conclusion is the stated change.

* Dated figures are read through their dates: `fell from about 381 in September 1929 to
  about 41 in July 1932, a fall of about 50 per cent` is checked (and fails: the fall is
  89 per cent). The date group accepts a year, `early`/`late`/`mid` + year, month-year,
  day-month-year and `January 30, 1933`.
* Shared-unit elision: when only the second figure carries a unit (`from 15 to 45
  million`, `from 200 to 144 million tonnes`, `from 3.2 to 24.9 per cent`), the unit
  applies to the first figure too.
* Units: scales (million, thousand, ...), per cent, rates (`per thousand`, `per 1,000`,
  `per 100,000`, `per head`), seats, votes.
* Derived figures: `a fall of 50 per cent` / `fell by 50 per cent` (relative change),
  `a rise of 25 percentage points` between two per-cent figures (absolute difference),
  word fractions (`a fall of about a half`, `fell by two-thirds`), fold changes
  (`doubled`, `doubling`, `halved`, `halving`, `tripling`, `threefold`, `2.5-fold`).
* Tolerance rule (`TOLERANCE_RULE`, repeated in every check's `rule` and in the
  receipt's check description): the stated figure must lie within 5 per cent of the
  value computed from the report's own figures. The band is symmetric around the
  COMPUTED value, so a specialist who understates a change gets no wider band than one
  who overstates it (`a fall of 85 per cent` for a true 89.2 passes, `a rise of 74 per
  cent` for a true 69.9 fails, both by the same rule). Per-cent and percentage-point
  figures also pass when within 0.5 points of the computed value, so rounding to the
  nearest whole per cent is never a finding. `more than`/`over` before a stated change
  makes the check a lower bound only; `under`/`less than` an upper bound only.
* Year spans (`from 1928 to 1930`) are never read as a before/after pair.

## Chronology: one extractor for the proxy and the engine

`adapters/history_specialist/chronology.py` reads EVERY dated ordering a sentence asserts
(`after`, `before`, `followed`, `followed by`, `preceded`, `preceded by`), not only the
first. `HistoryPack`'s structural proxy `HI-CHR-001` and `CorePack`'s formal
`core-chronology-N` checks both read `chronology_relations(sentence)`, so they can never
disagree. Shapes: the standard `<event> in D1 ... after ... <event> in D2` within one
clause; a leading cue (`..., and after a crowd broke a window in January 1817, Parliament
suspended habeas corpus in March`) where the cue clause names one event and the main
clause the other; a bare month that takes the year of the dated side (decided only when
that reading holds; otherwise undecided because the year is not stated); an aside whose
verb is the subject's own occurrence (`The Lushan plenum, which met in July 1959, came
after ...`) is the ordered event. A relation with dates on both sides that cannot be
paired (an aside about the subject's founding, an unstated year) is reported by the core
pack as `CORE-CHR-001` (warning) rather than skipped; a cue with no date on one side
states no checkable order and yields nothing. `named after`, `look after` and similar
are not cues.

## Core pack findings

| Code | Severity | Meaning |
| --- | --- | --- |
| `CORE-SRC-001` | error | a cited excerpt was not found in the supplied text |
| `CORE-SRC-002` | info | figures stated without sources, library references or a from-memory label |
| `CORE-SRC-003` | warning / info | a quotation with no supplied text to check it against (info only when the specialist's own label says the quotation is from memory). Quotations are read in straight, curly or mixed double marks, guillemets, and delimited single marks of two or more words, exactly as the parsers read them, so `'three years of natural disasters'` is reported like `"..."` |
| `CORE-SRC-004` | warning | a paragraph whose double marks (straight, curly, mixed, guillemets) cannot be paired; the dangling mark is located by context so the quotations the writer did delimit are still checked |
| `CORE-SRC-005` | error | a quotation credited in its sentence to a named source (a supplied text's author or title, a peer agent such as `the History specialist`, `the poem` when one text was supplied) with a saying verb, but located only in a different supplied text: the words are genuine, the credit is wrong. A quotation found in no text is left to the grounding check (`INT-REQ-003`) |
| `CORE-CHR-001` | warning | a sentence orders two dated events but the pair could not be decided (see above); the stated order was not checked |
| `CORE-SELF-001` | warning | verification-status language or a receipt imitation in the body; agent self-reports are advisory |

## Request-aware suppression in the subject packs

Packs receive the request text. `HistoryPack` drops `HI-STR-004` (essay-length guide)
when the request sets a shorter deliverable, and `HI-STR-001` (no judgement move) when
the request demands no verdict: no sentence carries a level-3 verdict command term
(`evaluate`, `discuss`, `to what extent`, `assess`, `examine`, `justify`, `recommend`)
and none asks for a judgement in plain words (`give a judgement on which effect mattered
most`). An `outline`/`describe` task is never faulted for lacking a judgement move
(`request_demands_judgement`). `EnglishPack` drops `ES-STR-002` (paragraph-length target)
when the request carries a word bound (`request_sets_word_bound`).

## The History parser's reading of notes and labels

A substantive sentence that carries the method's own label inline (`... fell to about 41
in July 1932 (figures from memory; check your notes)`) keeps its role and eligibility
(evidence, arithmetic, QUANTITATIVE_CLAIM): `markdown.split_note_clauses` removes the
label clause before classification and the label is recorded in the claim's assumptions.
Only an empty core makes a sentence a note; task notes (`Syllabus version and level were
not stated`) are notes. Any sentence that certifies the answer's own verification, or is
a forged receipt fragment, makes its whole paragraph a note paragraph (no material point,
no HI-STR findings on it). Judgement cues include `on balance`, `mattered most`,
`outweigh`, `more significant than`, `carries the greater weight`; judgement and link
claims are supported by the paragraph's point and other argument claims, so they are
PROPOSITIONAL_ARGUMENT eligible like English links. Dated claims under a from-memory
label are capped at certainty `probable`.

Adding a subject: write a pack (deterministic checks citing the pack's working rules,
plus any formal check templates), optionally an adapter, and register a branch. The
hub integrity never has to be touched. Receipts carry `branch`, `structural_findings`
and `formal_checks` so the router and Overseer can see which branch judged what.
