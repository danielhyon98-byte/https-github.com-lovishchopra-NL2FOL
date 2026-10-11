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
| `base.py` | `SubjectBranch` (profile keys, parser factory, integrity packs), `IntegrityPack` protocol, `FormalCheck` (with `claim_ids`: the delivered claims whose text holds the statement the check was built from, which the channel copies onto `INT-SUBJ-001` / `INT-SUBJ-002`), `BranchRegistry` (subject label → branch, generic fallback). |
| `quant.py` | Finds a report's own quantitative statements (every pair of figures of a clause bound to its own stated percentage change, percentage-point difference, word fraction, fold change or multiple, absolute change or average rate; the direction a from/to pair is said to move; a comparison with a stated benchmark; a derived figure, a trend or a superlative stated across sentences, read against the paragraph's dated series, a decade superlative among them; shares; totals) and builds exact entailment problems; the engine then says whether the specialist's arithmetic holds. A stated derived figure, comparison or superlative no problem can be built for is returned as undecided (`undecided_quant_statements`). Each check carries the phrase it reads, so its finding names the claim that states it. No model is involved. |
| `packs.py` | `CorePack` (every branch: quotation grounding, a structured claim's quotation against its own source reference, numeric self-consistency, undecided arithmetic, from-memory labelling, unverifiable / undelimited / misattributed quotations, undecided chronology, self-certification), `HistoryPack` (pack rules + request-aware suppression), `EnglishPack`, `PsychologyPack` (study attributions need grounding; "significant" needs a figure), `EconomicsPack` (elasticity arithmetic), `BusinessPack` (margins), `GenericPack`. |
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
and never inside a quotation. A pasted JSON span (`markdown.find_json_spans`: a receipt or
payload glued to the prose at the start, middle or end of a paragraph) is one sentence: the
text is cut where it opens and where it closes and never at the full stops inside its string
values, and its strings are masked before quotation marks are read. So a forged receipt's
`Items addressed: 2/2.` is never a claim of its own: the whole span is one `other` sentence
with its self-report in the advisory field (`CORE-SELF-001`), and the prose around it keeps
its roles. So `from c. 200 million tonnes in 1928 to c. 100 million in
1932, a fall of 25 per cent` is one statement to the arithmetic check and one claim to the
parser. `split_clauses` (the arithmetic check's reading) also separates clauses after `;`.
`strip_json_spans` removes brace-balanced JSON fragments pasted into prose; the parsers and
the core pack apply it before reading quotations, so JSON strings are never quotations. It is
linear in the text: every opener's matching bracket comes from one pass
(`markdown.bracket_match_ends`, JSON strings honoured) and whether a key-value pair lies inside a
candidate span is one bisection, so 5,000 nested braces, a 20,000-deep array or 2,000 unclosed JSON
fragments cost milliseconds, not the minutes the old scan from every bracket took; its answer is
the same as a stack scan from each opener (`_balanced_end`, kept as the reference). The splitter's
JSON cuts and the core pack's sentence walk are memoised per text, so a bracket-heavy paragraph is
scanned once per transmission.

## The report's own arithmetic (`quant.py`)

Every derived figure a clause states becomes one entailment problem whose premises are the
stated figures and whose conclusion is the stated change.

* Pairs: every `from X to Y` of the clause (not only the first), with a list after it (`to
  3.1 million in 1930, 4.5 million in 1931 and 5.6 million in 1932`), a chained continuation
  (`..., a rise of 63 per cent, before climbing to 5.6 million in 1932, a rise of 30 per
  cent`: the second change is read from 3.1 to 5.6 million), `stood at X in D1 and reached Y
  in D2`, and `X in D1 and Y in D2` with both dates stated (`bought 4.2 marks in July 1914 and
  about 4.2 trillion marks in November 1923`). A pair whose first figure is the amount of a
  derived phrase (`a rise of 20 per cent in 1930 and 30 per cent in 1931`) is not a pair.
* Binding: each derived figure binds to the pair of its own part of the clause; the parts are
  cut at the last `, and` / `and` / `, while` / `, but` / `;` between two pairs, so `Output rose
  from 100 in 1929 to 120 in 1930, a rise of 20 per cent, and exports rose from 50 in 1929 to
  60 in 1930, a rise of 50 per cent` is two checks and the second fails; a derived figure before
  its pair binds to it (`roughly tripled from 1.9 million ...`). A derived figure after a list
  is read against the list's last figure.

* Dated figures are read through their dates: `fell from about 381 in September 1929 to
  about 41 in July 1932, a fall of about 50 per cent` is checked (and fails: the fall is
  89 per cent). The date group accepts a year, a year range (`in 1923-24`),
  `early`/`late`/`mid` + year, month-year, day-month-year and `January 30, 1933`.
* An optional digit-free noun phrase of up to three words may follow a figure's unit before
  its date or `to`: `200 students in 1920`, `800 million gold marks in 1924`, `6 per cent of
  members in September 1923`; a rate phrase may follow it (`500,000 tons a year in 1700`, `per
  annum`, `each year`). Qualifiers before a figure include `near`, `close to` and `just`; a
  circa may stand before the year (`by about 1700`, `in c. 1700`).
* Shared-unit elision: when only the second figure carries a unit and the first carries
  neither a unit nor a noun (`from 15 to 45 million`, `from 200 to 144 million tonnes`, `from
  3.2 to 24.9 per cent`), the unit applies to the first figure too. A first figure with its own
  noun is read as written: `from about 4.2 marks in 1914 to about 4.2 trillion marks` is 4.2
  marks, not 4.2 trillion, and `from about 18,000 marks ... to about 4.2 trillion marks` is
  18,000. A per-cent, rate or count unit on the first figure alone carries to the second (`from
  37.3 per cent to 33.1`).
* Units: scales (thousand, million, billion, trillion, quadrillion; `k`, `m`, `bn`, `tn`,
  `trn`), per cent, rates (`per thousand`, `per 1,000`, `per 100,000`, `per head`, an
  exchange rate `to the dollar`), seats, votes. A pair whose units are of different kinds, or
  whose first figure carries a scale while the second carries no recognised unit (`from 4
  billion to 4 lakh marks`: the second figure's unit word is unknown), is NOT read as a bare
  number against a scaled one: no check is built and the derived figure is reported undecided
  (`CORE-QNT-001`). Figures in words below a thousand are read (`from two hundred to two
  hundred and sixty students, an increase of forty-five per cent` fails), a scale word after
  them being the unit (`six million`); a decimal comma (`1,9 million`: one or two digits after
  the comma) is a decimal point.
* Derived figures: `a fall of 50 per cent` / `fell by 50 per cent` (relative change; a
  signed figure such as `a rise of -10 per cent` reverses the direction), `a change of 20 per
  cent` (the direction is the figures' own; `a change of 0 per cent` between different figures
  fails), `a rise of 25 percentage points` between two per-cent figures (absolute difference;
  plain `points` between other figures too), word fractions (`a fall of about a half`, `fell by
  two-thirds`), fold changes (`doubled`, `doubling`, `halved`, `halving`, `tripling`,
  `threefold`, `2.5-fold`, `1,670-fold`, `hundredfold`, `thousandfold`, `millionfold`,
  `trillionfold`) and multiples (`six times its earlier length`, `four times as large`, `twice
  its 1928 level`). A qualifier may stand before a fold word with an article between: `more
  than a tripling`, `over a threefold rise` (lower bounds), `nearly a doubling` (approached
  from below, see the tolerance rule).
* Absolute changes and average rates: `an increase of about 6,500 miles`, `a fall of 3,000
  men`, `added roughly 4,500 miles`, `adding`, `gained`, `lost`, `shed`, `rose by 2.9 million
  tonnes` (the difference of the pair, after minus before, or before minus after for a fall),
  and `an average of 450 miles a year`, `averaging`, `added 450 miles a year` (the difference
  divided by the years between the pair's dates). The amount's unit must be comparable with the
  pair's (a scale with a scale, a noun with the same noun: `4,500 miles` against figures in
  tonnes is undecided), never a per cent, point, fraction or fold (those are the relative
  readings). `from about 1,500 miles in 1840 to about 6,000 miles in 1850, an increase of about
  6,500 miles` is a COUNTEREXAMPLE.
* The direction of a pair: a from/to pair that no derived figure binds, governed by a direction
  word right before its `from` (`pig iron rising from about 3.3 million tonnes to about 6.2
  million`, `rose sharply from`) or inside a continuation (`before falling to`), is checked for
  that direction: the later figure above the earlier for a rise, below it for a fall. A list of
  pairs with no verb of their own (`..., steel from about 4.3 million to 5.9 million and coal from
  ...`) takes the direction of the pair before it. `pig iron rising from about 6.2 million tonnes
  to about 3.3 million` is a COUNTEREXAMPLE. Two figures joined by `and` (`from 2.6 per cent and
  twelve seats`) state no change and are not read; neither is a pair whose units cannot be
  compared.
* Comparisons with a stated benchmark: `fell short of`, `short of`, `exceeded`, `surpassed`,
  `outstripped`, `overtook`, `topped` before a figure (`fell short of the First Plan's original
  target of about 10 million tonnes of pig iron`), with an optional margin (`by about 10 per
  cent` of the benchmark, `by half`, `by 1.2 million tonnes`). The compared figure is the last
  figure before the verb in its clause (a pair's later figure, or a figure standing alone), or,
  when the clause's subject refers back (`These totals`, `The figures`, `They`), the later figure
  of the pair of the previous sentence whose subject the benchmark names (`of pig iron`); several
  candidates with none named is undecided. The check is the inequality (and the margin within the
  tolerance rule). In hi-t9, 6.2 million tonnes against 10 million is ENTAILED; against 5 million,
  or with a margin of 10 per cent (the shortfall is 38), it is a COUNTEREXAMPLE. A comparison whose
  compared figure cannot be read is undecided when the benchmark is named as one (`target`, `goal`,
  `quota`, `plan`, `level`, `record`, ...); a plain stated quantity (`deaths exceeded 22,000`) is not
  a comparison of two figures and is not read.
* Relations stated across sentences: a derived figure whose clause states no pair (`The annual
  average grew by roughly 60 per cent that year`), a trend (`rose in each year that followed`,
  `fell every year`) and a superlative (`the greatest proportional rise of the period`) are
  read against the paragraph's dated series: the year-dated figures of its pairs and lists
  (a month-dated peak or a year range is not an annual point), series that agree on every
  shared year being one. The years come from the clause (`from 1929 to 1930`, `in 1930`) or,
  for `that year` / `the same year`, from the one year stated before it in its clause or in
  the nearest earlier sentence that states a year (two candidate years are ambiguous); the
  change is read from the series' previous year. A trend is checked over the series' years
  from the clause's own year on (strictly rising or falling); a superlative compares the stated
  year's change with every other year-on-year change, proportionally when it says
  `proportional`/`relative`/`percentage` or the clause states a per-cent change, absolutely
  otherwise. Each such check's description says that it was stated across sentences, how the
  year was read and which sentence the figures came from. In hi-t8, `grew by roughly 60 per
  cent that year` is read as 1929-1930 (1.9 to 3.1 million, 63.2 per cent: ENTAILED); 90 per
  cent is a COUNTEREXAMPLE.
* Decades: a decade named before a derived phrase in its clause (`The 1840s, which included the
  Railway Mania of 1845 to 1847, added roughly 4,500 miles`; the years between them falling inside
  the decade) is read as its first and last year (1840 to 1850) against the paragraph's dated
  series, and it governs a phrase that follows a pair of other years (`Route mileage reached about
  13,000 in 1860 and about 15,500 in 1870, so the 1850s added about 7,000 miles` is read 1850-1860,
  not 1860-1870). Series of one measure stated in different sentences (a shared content word, no
  disagreement on a shared year) are read as one when no single series states the years needed.
  A decade superlative (`more than any other decade of the period`, `fewer than any other decade`)
  compares the decade's change with every other decade whose figures the series states at both
  ends, a year-dated figure standing alone (`took the network to about 11,000 miles by 1860`)
  included; it is decided when a stated decade refutes it or when every decade of the period (the
  paragraph's `between 1830 and 1870`) is stated, and undecided otherwise, naming the decades whose
  figures are missing. In hi-t10 the 1840s' 4,500 miles is ENTAILED, and `more than any other
  decade` is undecided because the 1850s and 1860s are stated only together; with the 1850s given
  5,000 miles it is a COUNTEREXAMPLE.
* Undecided arithmetic (`undecided_quant_statements`, reported by the core pack as
  `CORE-QNT-001`): a derived figure (relative, absolute, a rate or a multiple), a comparison with
  a named benchmark, a trend or a superlative that no problem can be built for is named with the
  reason (units that cannot be compared, no figures in its sentence and no dated series in the
  paragraph that supplies them, two series that could be meant, an anaphor with two candidate
  years, a decade whose neighbours are not stated decade by decade, a compared figure that is not
  stated), so no stated arithmetic crosses the hub silently.
* Tolerance rule (`TOLERANCE_RULE`, repeated in every check's `rule` and in the
  receipt's check description): the stated figure must lie within 5 per cent of the
  value computed from the report's own figures. The band is symmetric around the
  COMPUTED value, so a specialist who understates a change gets no wider band than one
  who overstates it (`a fall of 85 per cent` for a true 89.2 passes, `a rise of 74 per
  cent` for a true 69.9 fails, both by the same rule). Per-cent and percentage-point
  figures also pass when within 0.5 points of the computed value, so rounding to the
  nearest whole per cent is never a finding. `more than`/`over` before a stated change
  makes the check a lower bound only; `under`/`less than` an upper bound only. An approach
  qualifier sets its own band (`APPROACH_BAND`, `APPROACH_ROUNDING`): `nearly`, `almost`, `just
  under`, `not quite` make the stated figure an upper bound approached from below, so the computed
  value may exceed it by no more than 1 per cent of it (or the half-point floor of a per-cent
  figure) and must be at least 85 per cent of it (`nearly a doubling` holds for x1.83 and x1.88,
  fails for x2.1 and x1.3; `nearly a tripling` fails for x3.1; `a fall of nearly a half` holds for
  45 per cent and fails for 52); `just over`, `a little over`, `slightly more than` are the mirror
  case, from the stated figure less rounding up to the stated figure divided by 0.85. `about`,
  `roughly` and `close to` keep the symmetric band. The check's `rule` names the band applied.
* Year spans (`from 1928 to 1930`) are never read as a before/after pair of figures.
* Claim ids: every check names the delivered claims whose text holds the statement it read
  (`FormalCheck.claim_ids`), or, when the statement spans several claims (a long block the parser
  cut where the check did not), the claim holding the phrase; the description quotes the statement
  around that phrase, not only its first 160 characters, and `CORE-QNT-001` names the same claims.

## Chronology: one extractor for the proxy and the engine

`adapters/history_specialist/chronology.py` reads EVERY dated ordering a sentence asserts,
not only the first. After-type cues put the event before them later: `after`, `followed`,
`preceded by`, `later than`, `subsequent to`, `postdated`, `following`, `in the wake of`, `in
the aftermath of`; before-type cues earlier: `before`, `preceded`, `followed by`, `earlier
than`, `sooner than`, `prior to`, `previous to`, `predated`, `antedated`, `ahead of`, `on the
eve of`, `in the run-up to`, `preceding`. `no later than` is a bound, `the following year` a
date, `followed from` a consequence: none is an order. `HistoryPack`'s structural proxy `HI-CHR-001` and `CorePack`'s formal
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
  habeas corpus in March`, `Prior to the Treaty of Rapallo of April 1922, ...`) where the cue
  clause names one event and the main clause the other; an aside whose verb is the subject's
  own occurrence (`The Lushan plenum, which met in July 1959, came after ...`) is the ordered
  event, but `called` is a summons, not the meeting, so `The plenum, which had been called in
  June 1959, met after ...` is undecided.
* Intransitive `followed`/`preceded` directly before a date (`followed in July 1922`,
  `followed, on 13 January 1923,`, `followed by 1924`) dates the cue's OWN subject; the other
  event is the one dated before the cue in the sentence (across a coordinate clause:
  `The Ruhr was occupied in January 1923 and passive resistance followed in February 1923`, or
  the leading `After ...` clause), else the one date of the previous sentence (several dates
  there: undecided, since which event is followed is not stated). So `After the
  murder of Rathenau in June 1922, the Law ... followed in July 1922` is ENTAILED and the
  reversed dates a COUNTEREXAMPLE.
* Coordinated cues: in `The Ruhr was occupied in January 1923, after the London ultimatum of
  May 1921 and before the Dawes Plan of 1922` the second cue orders the clause's subject
  (January 1923), not the first cue's object, so the stated (false) `January 1923 before 1922`
  is checked; when the subject carries no date the second relation is undecided.
* An event named without a date: a side of a cue with no date in the sentence is looked up in
  the paragraph when it is a definite noun phrase headed by an event noun (`that election`,
  `the treaty`, `the Danatbank collapse`): the one date another sentence gives the noun within
  a few words in its clause (`the September 1930 election`, `Signed on 28 June 1919, the
  treaty`), never a date that bounds a range (`up to 1923`, `since 1793`) and never a mention
  whose noun carries a modifier the side does not (`The agrarian crisis that began in 1928` is
  not `the crisis`). Both sides dated: the relation is decided and its reason names the
  sentence the date came from (`That election came after the Danatbank collapse of July 1931`
  with the election dated September 1930 a sentence earlier is a COUNTEREXAMPLE). One side
  dated: undecided (`CORE-CHR-001`) when the undated side is a demonstrative that must refer
  back (`that election`) or when the dated side's date came from another sentence (`instability
  began before the treaty`: stated across sentences); a dated event and an undated,
  non-anaphoric one in the same sentence (`the budget fell after the vote of July 1930`) state
  no checkable order and yield nothing.
* A side named by a proper name dated earlier in the same sentence (`the London and Birmingham
  Railway opened in 1838, and the Great Western reached Bristol in 1841, three years before the
  London and Birmingham opened`: the whole name recurs, the date follows it in its clause) takes
  that date, so the false order is a COUNTEREXAMPLE; a name carrying a number (`Article 48`) is a
  reference, not an event, and a proper name dated only in another sentence is not looked up. An
  interval stated with the cue (`three years before`) against a named event the sentence never
  dates is undecided (`CORE-CHR-001`) rather than silent.
* Durations: `ran from D1 to D2`, `lasted from D1 until D2`, `was fought from D1 to D2` (a duration
  verb before `from`) order their ends: D2 must be later. `The Second Boer War ran from 31 May 1902 to
  the Peace of Vereeniging on 11 October 1899` is a COUNTEREXAMPLE. A bare year span with no duration
  verb is not an ordering.
* Containment (relation kind `within`): `X, including Y`, `X, which included Y`, `among them` put the
  inner date or range (after the cue) inside the outer period (before it): a decade (`the 1840s`), a
  range (`1845 to 1847`, `1899-1902`), a month-year, a year or a day. An inner date with no year takes
  the outer period's one year (`Reverses in December 1899, including ... Magersfontein on 11
  December`); `11 November` there, or `The 1840s, which included the Railway Mania of 1855 to 1857`,
  is a COUNTEREXAMPLE. `Y during X`, `Y within X`, `amid X` put a dated event inside the period after
  the cue, and an inner range need only meet it (kind `overlaps`). An inner date stated more coarsely
  than the period (a year inside a month) is undecided. The engine's problem bounds both intervals in
  day ordinals.
* Same year (relation kind `same_year`): `the poem's 1902 date falls at the war's close` places a
  date at the close (or end, outbreak, start, eve) of the duration the sentence, or the paragraph's
  one duration, states: the years must be equal. `the poem's 1899 date falls at the war's close` is
  a COUNTEREXAMPLE; with no duration stated it is undecided.
* A relation with dates on both sides that cannot be paired (an aside about the subject's
  founding, an unstated year, an equal month) is reported by the core pack as `CORE-CHR-001`
  (warning) rather than skipped. `named after`, `look after` and similar are not cues.
  `ChronologyRelation.kind` says which relation a sentence asserts (`order`, `within`, `overlaps`,
  `same_year`) and `statement` words it; `HI-CHR-001`, `CORE-CHR-001` and the formal check's label
  read it, and every formal chronology check names the claims whose text holds the sentence.

## Core pack findings

| Code | Severity | Meaning |
| --- | --- | --- |
| `CORE-SRC-001` | error | a cited excerpt was not found in the supplied text (an excerpt located in another form, such as an initial capital, a line-break mark, diacritics or a long elision, is not this finding: the channel names it `INT-REQ-010` and the subject pack warns) |
| `CORE-SRC-002` | info | figures stated without sources, library references or a from-memory label |
| `CORE-SRC-003` | warning / info | a quotation with no text to check it against: with no text supplied, every quotation; with texts supplied, a quotation that no supplied text holds and whose sentence credits it to no supplied text (the parser recorded no source reference, so the grounding check never sees it), and every quotation a parser recorded as credited to no text (the shared attribution rule's assumption), whatever its length, on every branch, the English one included. Info only when the specialist's own label says the quotation is from memory (a label in the same sentence, or a label that speaks of quotations); a figures label does not vouch for a quotation. Quotations are read in straight, curly or mixed double marks, guillemets, and delimited single marks of two or more words, after JSON fragments are removed, exactly as the parsers read them. A quotation credited to a named text that does not hold it is the channel's `INT-REQ-003`, not this finding |
| `CORE-SRC-004` | warning | a paragraph whose double marks (straight, curly, mixed, guillemets) cannot be paired; the dangling mark is located by context so the quotations the writer did delimit are still checked |
| `CORE-SRC-005` | error / warning | a quotation credited in its sentence to a named source (a supplied text's author or title, a peer agent such as `the History specialist`, `the poem` when one text was supplied) with a saying verb (`says`, `writes`, `admits`, `identifies`, `suggests`, ...), but located only in a different supplied text: the words are genuine, the credit is wrong. A credit to an author or work that was NOT supplied to this agent (`Hardy's speaker himself admits that his justification "becomes circular"`, `Hardy's poem identifies ... "exposes a motive of poverty"`, `<Name> writes`, and `the poem` / `the speaker` when no literary text was supplied and the sentence names no other source) is an error when the words occur only in a colleague's report, in the colleague's own prose rather than inside a quotation the colleague makes (the colleague quoting the poem is the poem's words, so `Hardy's speaker says he "had sold his traps"` is no finding). In a reporting clause (`The English specialist argues that Blake presents ... "..."`) the OUTER speaker is the credited source, so a colleague's words reported correctly are no finding. When the sentence names a second source before the quotation and that source holds the words, the credit is ambiguous: a warning naming both, not an error. A quotation found in no text is left to the grounding check (`INT-REQ-003`) or, when uncredited, to `CORE-SRC-003`. The finding names the claim whose source reference carries the misattributed excerpt and the sentence's own claim, never the claims of the sentence's other, correctly credited quotations |
| `CORE-SRC-006` | error | a claim whose text quotes words no supplied text holds, while the claim (or a claim it rests on) credits a supplied text through its source references and no reference or note carries those words: the claim's quotation and its reference's excerpt disagree (`"Had we two but met"` in the claim, `Had he and I but met` in the reference), so the grounding check, which reads the reference, does not vouch for the words stated. On the English branch a quotation with no reference at all, in a report on one literary text, is credited to that text as the English parser credits it. A parsed report never raises it (every quotation a parser reads is carried by a reference or recorded in an assumption); the structured contract does. The quotation is then not also reported as `CORE-SRC-003` |
| `CORE-CHR-001` | warning | a sentence orders two dated events, places a date within a period or at a point of one, but the relation could not be decided (see above: an aside date, an unstated year, an equal month or year, a coordinated cue whose subject carries no date, an event dated only in another sentence beside one the paragraph does not date, a demonstrative that refers to no identifiable dated event, an interval against a named event never dated, an inner date coarser than its period, a point of a period no duration states); the stated relation was not checked |
| `CORE-QNT-001` | warning | a derived figure, comparison, trend or superlative the sentence states could not be checked (see the arithmetic section: incomparable units, no figures in its sentence and none in the paragraph's dated series, two series that could be meant, an ambiguous `that year`, a decade superlative whose other decades are not stated, a compared figure that is not stated); one finding per sentence and reason, naming the phrases and the claim that states them; the stated arithmetic was not checked |
| `CORE-SELF-001` | warning | verification-status language or a receipt imitation in the body; agent self-reports are advisory |

## History structural source check (`HI-SRC-001`)

The History pack reads every source reference through the same grounding check the
channel uses, so it never contradicts the channel: an excerpt the channel locates in a
different form (initial capital, verse line break, diacritics, long elision: `INT-REQ-010`) is a
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

* Roles by function before surface: after the point (a body paragraph's first substantive
  sentence), a sentence that opens with a link lead (`Against this background`, `In this
  light`, `Read against`, `This is why`, or `against` with a demonstrative noun phrase: `Against
  that toll,`, `Set against these losses,`) is a `link`, and one that states a verdict (`The
  turning point was 1930.`, `1930 marked the turning point`, `the decisive year was`, `the
  most important cause was`, `mattered most`, with a singular or plural copula and a period or
  judgement noun: `The 1840s were the most decisive decade.`, `The 1840s were the decisive
  decade.`, `The most decisive decade was the 1840s.`, `The 1840s saw the most decisive
  expansion.`) or opens with the criterion of one (`Measured by what the network could do, ...`,
  `Judged by ...`, `By the criterion of ...`) a `judgement`, all material whatever they date or
  quote; a bare `Against this,` stays a counter-case lead. A degree adjective without `most` is a
  verdict only when it is one by itself (`decisive`, `pivotal`, `critical`, `crucial`, `key`,
  `formative`, `defining`), so `the significant growth was ...` stays a description. A
  counter-case (`The strongest counter-case is that ...`, `however`, `against this`, `it could be
  argued`) is `counter_evidence` whether or not it is dated, unless it also weighs the case with a
  judgement cue (`by the criterion of ...`), and the dated sentence right after an undated
  counter-case statement is its `counter_evidence`. Only then does a dated item make a sentence
  `evidence`; a year that only names an event (`the 1923 crisis`, `the September 1930
  election`) dates no statement. An undated sentence that carries one of the channel's verdict
  cues (`VERDICT_CUES`: `decisive`, `to a large extent`, `thus`, ...) is a `judgement`: the
  channel reads such a claim as a position on degree (INT-REQ-008), so the hub and the parser
  never disagree. A quotation turns only analysis into evidence, never a link or a judgement. So
  hi-t8's `The turning point was 1930.`, hi-p3's `Against this background, the "smokeless air"
  ...`, hi-t10's `The 1840s were the most decisive decade.` and its criterion `Measured by ...`,
  and hi-p4's `Against that toll, Hardy's speaker calls ...` are material, and a synthesis that
  drops any of them without a record is `INT-LEDGER-002`.
* `HI-STR-003` (opens with evidence rather than a claim) is decided from the parsed role of the
  paragraph's first claim that is not a note: an evidence or counter-evidence opening is
  evidence; the point, which the parser takes by position, is a claim unless the parser's own
  predicate (`opens_with_fact`) reads it as a bare dated fact with no causal, evaluative or
  argument word (`The sonnet was printed in January 1818.`), and the finding then says so and
  names that claim. `The Treaty of Versailles was a major but partial cause of ...` is a claim.
  A year range or a decade that scopes a claim (`between 1830 and 1870`, `from 1928 to 1941`,
  `the 1840s`) does not date it, and periodisation and shaping words (`came in phases`, `gave the
  network its shape`, `transformed`, `drove`) are argument words, so hi-t10's thesis is a claim.
* `HI-STR-004` (essay length) counts words with the channel's word (`request_parser.count_words`:
  `1.9`, `100,000` and `63.2%` are one word each), so the pack and the word-bound constraint agree.
* A substantive sentence that carries the method's own label inline keeps its role and
  eligibility (evidence, arithmetic, QUANTITATIVE_CLAIM): `markdown.split_note_clauses`
  removes the label before classification, whether it is a parenthetical (`... fell to
  about 41 in July 1932 (figures from memory; check your notes)`), a clause after a
  semicolon or dash, a sentence-initial label (`From memory, the mark stood at about 4.2 to
  the dollar ...`) or a comma-bounded one (`whose foreign loans, from memory about 800
  million gold marks, tied recovery ...`). Each distinct label is recorded once in the
  claim's assumptions. Only an empty core makes a sentence a note; task notes (`Syllabus
  version and level were not stated`) are notes.
* A sentence about how the answer was composed is a note (`is_provenance_note`, role `other`,
  never the point, never material, never addressing a request item): its subject is the answer,
  its setting, its judgement, its figures or a received report (`The historical setting`, `The
  judgement on which decade ...`, `The English specialist's paragraph`), its predicate is
  authorship or provenance (`is my own addition`, `is not part of that paragraph`, `is from memory
  as well`, `is my own`, `is from the hub`), and every other clause is a note too (`verify it
  before use`, `I have not checked its quotations`, `not part of that paragraph`). In hi-p4 `The
  historical setting is my own addition, not part of that paragraph.` is a note and the point is
  the first historical sentence (`The Second Boer War ran from ...`), so a synthesis that leaves the
  note out is not faulted (no `INT-LEDGER-019`, no `INT-LEDGER-002`); an answer made only of such
  notes and labels has no material claim and is `INT-REQ-012`. A sentence that also asserts
  something (`The judgement is my own, and it shows that ...`) is not a note.
* Only the sentence that certifies the answer's own verification, or is shaped like a
  receipt or JSON, becomes a note (role `other`, its self-report in the advisory field):
  the paragraph's other sentences keep their roles and the demotion is recorded as an
  unresolved issue naming the sentence. A paragraph that is nothing but notes or JSON is a
  note paragraph (no material point, no HI-STR findings on it).
* A quotation is attributed to the supplied text its sentence names (author, surname,
  title, or a peer specialist by name, through the English parser's `documents_named`)
  when that text holds the words, else to a text that holds them (the credit is then
  recorded as an assumption and `CORE-SRC-005` names it); a quotation held by no text is
  attributed to the one text the sentence names (so `INT-REQ-003` reports the credit); when the
  sentence names several texts the History parser passes the sentence, and the quotation is
  credited to the text whose possessive governs it, else the speaker of the reporting clause, else
  the text named nearest before it (`sources.governing_document`), so `The English specialist
  argues that Hardy presents the enemy as "a man much like himself"` with the poem and the
  colleague's report both supplied is `INT-REQ-003` naming the claim and `peer:<task>`; otherwise
  to NO text: the assumption `quotation with no supplied text to check it against: "..."` is
  recorded and the core pack reports `CORE-SRC-003`. A text is never credited merely because it
  was supplied first. The rule is `adapters/sources.attribute_excerpt`, shared with the English
  parser (which adds one step: a sentence naming no text quotes the one literary text under
  analysis) and the generic parser.
* A sentence whose subject is a peer specialist's view (`The English specialist argues
  that ...`, `The English specialist's phrase "..." fits that record`) is roled
  `perspective` with certainty capped at `probable` and an attribution assumption; it is
  not the paragraph's point. A sentence that merely cites the peer mid-way (`..., bearing
  out the English specialist's claim that "..."`) is the History specialist's own.
* Judgement and link claims are supported by the paragraph's point and other argument
  claims, so they are PROPOSITIONAL_ARGUMENT eligible like English links. Dated claims
  under a from-memory label are capped at certainty `probable`, and so is any claim whose own
  inline label the parser set aside, dated or not (`A regular private's pay of about a shilling a
  day (from memory) was a real draw ...`), so a synthesis that restates it as established is
  `INT-LEDGER-003`.

Adding a subject: write a pack (deterministic checks citing the pack's working rules,
plus any formal check templates), optionally an adapter, and register a branch. The
hub integrity never has to be touched. Receipts carry `branch`, `structural_findings`
and `formal_checks` so the router and Overseer can see which branch judged what.
