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

Two shared helpers live beside the History adapter and are read by the packs and the
parser alike, so the parser's claims, the pack's sentence numbers and the engine's checks
all read the same sentence: `adapters/history_specialist/sentences.py` (the
abbreviation-aware sentence splitter and the JSON-fragment stripper) and
`adapters/history_specialist/chronology.py` (the dated-ordering extractor).

## One sentence splitter (`adapters/history_specialist/sentences.py`)

`quant.py`, `packs.py` and the History parser split sentences with one function. A
sentence ends at `.`, `?` or `!` (plus closing marks) and whitespace, and after `}` or `]`
when a capital follows (prose glued to a pasted JSON fragment); never after an
abbreviation (`c.`, `ca.`, `approx.`, `fl.`, `no.`, `vol.`, `p.`, `pp.`, `ed.`, `cf.`,
`etc.`, `e.g.`, `Mr.`, `Dr.`, `St.`, ...) or a single-letter initial (`A. J. P. Taylor`),
and never inside a quotation. So `from c. 200 million tonnes in 1928 to c. 100 million in
1932, a fall of 25 per cent` is one statement to the arithmetic check and one claim to the
parser. `split_clauses` (the arithmetic check's reading) also separates clauses after `;`.
`strip_json_spans` removes brace-balanced JSON fragments pasted into prose; the parsers and
the core pack apply it before reading quotations, so JSON strings are never quotations.

## The report's own arithmetic (`quant.py`)

A sentence that states a from/to pair and a derived figure becomes one entailment
problem whose premises are the stated figures and whose conclusion is the stated change.

* Dated figures are read through their dates: `fell from about 381 in September 1929 to
  about 41 in July 1932, a fall of about 50 per cent` is checked (and fails: the fall is
  89 per cent). The date group accepts a year, a year range (`in 1923-24`),
  `early`/`late`/`mid` + year, month-year, day-month-year and `January 30, 1933`.
* An optional digit-free noun phrase of up to three words may follow a figure's unit before
  its date or `to`: `200 students in 1920`, `800 million gold marks in 1924`, `6 per cent of
  members in September 1923`.
* Shared-unit elision: when only the second figure carries a unit (`from 15 to 45
  million`, `from 200 to 144 million tonnes`, `from 3.2 to 24.9 per cent`), the unit
  applies to the first figure too; a per-cent, rate or count unit on the first figure alone
  carries to the second (`from 37.3 per cent to 33.1`).
* Units: scales (thousand, million, billion, trillion, quadrillion; `k`, `m`, `bn`, `tn`,
  `trn`), per cent, rates (`per thousand`, `per 1,000`, `per 100,000`, `per head`), seats,
  votes. A pair whose units are of different kinds, or whose first figure carries a scale
  while the second carries no recognised unit (`from 4 billion to 4 lakh marks`: the second
  figure's unit word is unknown), is NOT read as a bare number against a scaled one: the
  pair is skipped. Figures in words below a thousand are read (`from two hundred to two
  hundred and sixty students, an increase of forty-five per cent` fails), a scale word
  after them being the unit (`six million`).
* Derived figures: `a fall of 50 per cent` / `fell by 50 per cent` (relative change; a
  signed figure such as `a rise of -10 per cent` reverses the direction), `a rise of 25
  percentage points` between two per-cent figures (absolute difference), word fractions
  (`a fall of about a half`, `fell by two-thirds`), fold changes (`doubled`, `doubling`,
  `halved`, `halving`, `tripling`, `threefold`, `2.5-fold`, `1,000-fold`, `hundredfold`,
  `thousandfold`, `millionfold`).
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
`core-chronology-N` checks both read `chronology_relations(sentence, paragraph)`, so they
can never disagree.

* Date tokens: month-year with the day when written (`July 1932`, `18 June 1815`, `January
  30, 1933`, `c. 16 October 1962`); a day-month with no year (`14 October`, `on 26
  October`); a bare month after a preposition (`in March`); a year alone (`the Act of
  1788`, a four-digit year that is not part of a figure and carries no unit word).
* Resolution: two dates are compared at the coarsest resolution they share. Different
  years decide; the same year decides only when both state a month and the months differ;
  the same month decides only when both state a day and the days differ. An equal month
  with no days, an equal year with no month, or the same day is UNDECIDED (`CORE-CHR-001`),
  never a violation: `the broadcast of 28 October 1962 came after his first letter of 26
  October 1962` is ENTAILED, the same sentence with the days reversed is a COUNTEREXAMPLE,
  and `the broadcast of October 1962 came after his letter of October 1962` is undecided
  because the order within the month is not stated. The engine's problem compares day
  ordinals (`(year*12+month)*32+day`, a missing month or day counting 0).
* An unstated year: a token with no year takes the year of the dated side when the other
  side has one and that reading satisfies the stated order (any later year would too);
  when neither side has a year, the year is taken from the sentence when it states exactly
  one, else from the paragraph's dated events (the years of its month-year dates, so a
  publication year in parentheses such as `Thirteen Days (1969)` does not compete), else
  from the paragraph when it states exactly one year of any kind (`After the U-2
  photographs of 14 October ..., Khrushchev offered on 26 October` in a paragraph whose
  dated events fall in 1962 is decided, and the check's label says where the year came
  from); otherwise the relation is undecided because the year is not stated, and the
  reason says how many years the text states.
* Shapes: the standard `<event> in D1 ... after ... <event> in D2` within one clause; a
  leading cue (`..., and after a crowd broke a window in January 1817, Parliament suspended
  habeas corpus in March`) where the cue clause names one event and the main clause the
  other; an aside whose verb is the subject's own occurrence (`The Lushan plenum, which met
  in July 1959, came after ...`) is the ordered event, but `called` is a summons, not the
  meeting, so `The plenum, which had been called in June 1959, met after ...` is undecided.
  A relation with dates on both sides that cannot be paired (an aside about the subject's
  founding, an unstated year, an equal month) is reported by the core pack as
  `CORE-CHR-001` (warning) rather than skipped; a cue with no date on one side states no
  checkable order and yields nothing. `named after`, `look after` and similar are not cues.

## Core pack findings

| Code | Severity | Meaning |
| --- | --- | --- |
| `CORE-SRC-001` | error | a cited excerpt was not found in the supplied text |
| `CORE-SRC-002` | info | figures stated without sources, library references or a from-memory label |
| `CORE-SRC-003` | warning / info | a quotation with no text to check it against: with no text supplied, every quotation; with texts supplied, a quotation that no supplied text holds and whose sentence credits it to no supplied text (the parser recorded no source reference, so the grounding check never sees it). Info only when the specialist's own label says the quotation is from memory (a label in the same sentence, or a label that speaks of quotations); a figures label does not vouch for a quotation. Quotations are read in straight, curly or mixed double marks, guillemets, and delimited single marks of two or more words, after JSON fragments are removed, exactly as the parsers read them. A quotation credited to a named text that does not hold it is the channel's `INT-REQ-003`, not this finding |
| `CORE-SRC-004` | warning | a paragraph whose double marks (straight, curly, mixed, guillemets) cannot be paired; the dangling mark is located by context so the quotations the writer did delimit are still checked |
| `CORE-SRC-005` | error / warning | a quotation credited in its sentence to a named source (a supplied text's author or title, a peer agent such as `the History specialist`, `the poem` when one text was supplied) with a saying verb, but located only in a different supplied text: the words are genuine, the credit is wrong. In a reporting clause (`The English specialist argues that Blake presents ... "..."`) the OUTER speaker is the credited source, so a colleague's words reported correctly are no finding. When the sentence names a second source before the quotation and that source holds the words, the credit is ambiguous: a warning naming both, not an error. A quotation found in no text is left to the grounding check (`INT-REQ-003`) or, when uncredited, to `CORE-SRC-003` |
| `CORE-CHR-001` | warning | a sentence orders two dated events but the pair could not be decided (see above: an aside date, an unstated year, an equal month or year); the stated order was not checked |
| `CORE-SELF-001` | warning | verification-status language or a receipt imitation in the body; agent self-reports are advisory |

## History structural source check (`HI-SRC-001`)

The History pack reads every source reference through the same grounding check the
channel uses, so it never contradicts the channel: an excerpt the channel locates in a
different form (initial capital, verse line break, long elision: `INT-REQ-010`) is a
`HI-SRC-001` WARNING naming the difference, an excerpt found nowhere is an error. Both
messages name the excerpt and the documents searched.

## Request-aware suppression in the subject packs

Packs receive the request text. `HistoryPack` drops `HI-STR-004` (essay-length guide)
when the request sets a shorter deliverable, and `HI-STR-001` (no judgement move) when
the request demands no verdict: no sentence carries a level-3 verdict command term
(`evaluate`, `discuss`, `to what extent`, `assess`, `examine`, `justify`, `recommend`)
and none asks for a judgement in plain words (`give a judgement on which effect mattered
most`). An `outline`/`describe` task is never faulted for lacking a judgement move
(`request_demands_judgement`). `EnglishPack` drops `ES-STR-002` (paragraph-length target)
when the request carries a word bound (`request_sets_word_bound`).

`HI-STR-001` itself is decided from the parsed roles first: a paragraph with a
judgement-role claim that states its criterion (`by the criterion of`, `by the criteria
of`, `weighed by`, `measured by`), or a counter-case (role `counter_evidence` or a counter
cue such as `however`, `the counter-case`) together with a judgement or verdict cue, has
made the move; failing that, the paragraph's words are searched for the move's own
vocabulary. `criteria` and `criterion` are read alike. The judgement cues include
`weighed by`, `weighs`, `by the criteria`, `on balance`, `mattered most`, `outweigh`, `more
significant than`, `carries the greater weight`; the verdict cues are the channel's own
tuple (`channel/cues.py`), so the parser, the pack and the channel never disagree about
what a verdict looks like.

## The History parser's reading of notes, labels, attributions and peers

* A substantive sentence that carries the method's own label inline keeps its role and
  eligibility (evidence, arithmetic, QUANTITATIVE_CLAIM): `markdown.split_note_clauses`
  removes the label before classification, whether it is a parenthetical (`... fell to
  about 41 in July 1932 (figures from memory; check your notes)`), a clause after a
  semicolon or dash, a sentence-initial label (`From memory, the mark stood at about 4.2 to
  the dollar ...`) or a comma-bounded one (`whose foreign loans, from memory about 800
  million gold marks, tied recovery ...`). Each distinct label is recorded once in the
  claim's assumptions. Only an empty core makes a sentence a note; task notes (`Syllabus
  version and level were not stated`) are notes.
* Only the sentence that certifies the answer's own verification, or is shaped like a
  receipt or JSON, becomes a note (role `other`, its self-report in the advisory field):
  the paragraph's other sentences keep their roles and the demotion is recorded as an
  unresolved issue naming the sentence. A paragraph that is nothing but notes or JSON is a
  note paragraph (no material point, no HI-STR findings on it).
* A quotation is attributed to the supplied text its sentence names (author, surname,
  title, or a peer specialist by name, through the English parser's `documents_named`)
  when that text holds the words, else to a text that holds them (the credit is then
  recorded as an assumption and `CORE-SRC-005` names it); a quotation held by no text is
  attributed to the one text the sentence names (so `INT-REQ-003` reports the credit) and
  otherwise to NO text: the assumption `quotation with no supplied text to check it
  against: "..."` is recorded and the core pack reports `CORE-SRC-003`. A text is never
  credited merely because it was supplied first.
* A sentence whose subject is a peer specialist's view (`The English specialist argues
  that ...`, `The English specialist's phrase "..." fits that record`) is roled
  `perspective` with certainty capped at `probable` and an attribution assumption; it is
  not the paragraph's point. A sentence that merely cites the peer mid-way (`..., bearing
  out the English specialist's claim that "..."`) is the History specialist's own.
* Judgement and link claims are supported by the paragraph's point and other argument
  claims, so they are PROPOSITIONAL_ARGUMENT eligible like English links. Dated claims
  under a from-memory label are capped at certainty `probable`.

Adding a subject: write a pack (deterministic checks citing the pack's working rules,
plus any formal check templates), optionally an adapter, and register a branch. The
hub integrity never has to be touched. Receipts carry `branch`, `structural_findings`
and `formal_checks` so the router and Overseer can see which branch judged what.
