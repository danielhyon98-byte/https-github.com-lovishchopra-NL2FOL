# branches — one hub, a branch per subject, an integrity pack in each

The router talks to every specialist (English, History, Psychology, Economics,
Business Management, the STEM subjects, and any subject added later) through the same hub.
What differs by subject lives in a branch:

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
                 ├── branch sciences ........... STEM parser + [core pack (SI reading), StemPack("sciences")] + STEM hooks
                 ├── branch mathematics ........ STEM parser + [core pack (SI reading), StemPack("mathematics")] + STEM hooks
                 ├── branch computer_science ... STEM parser + [core pack (SI reading), StemPack("computer_science")] + STEM hooks
                 └── branch generic ............ profile + generic parser + [core pack, generic pack]
```

| Module | Role |
| --- | --- |
| `base.py` | `SubjectBranch` (profile keys, parser factory, integrity packs, optional `hub_hooks`; `run_packs` runs each pack's checks and formal checks on their own, so a pack that fails internally adds `PACK-INTERNAL-001` (error) naming the pack and the call, with the branch infrastructure's `BR-INTERNAL-001` (warning) beside it, while every other pack's findings and formal checks still reach the receipt; it prefers a pack's `formal_checks_for(report, request_text)`), `IntegrityPack` protocol, `BranchHooks` protocol, `FormalCheck` (with `claim_ids`: the delivered claims whose text holds the statement the check was built from, which the channel copies onto `INT-SUBJ-001` / `INT-SUBJ-002` / `INT-SUBJ-004`; the named engine `policy`, `failure_severity`, `inconsistent_is_failure`), `BranchRegistry` (subject label → branch, generic fallback). |
| `quant.py` | Finds a report's own quantitative statements (every pair of figures of a clause bound to its own stated percentage change, percentage-point difference, word fraction, fold change or multiple, absolute change or average rate; the direction a from/to pair is said to move; a comparison with a stated benchmark; a derived figure, a trend or a superlative stated across sentences, read against the paragraph's dated series, a decade superlative among them; shares; totals; the parts of a stated total, after it ('of which', 'alone') or opening the clause ('Of the $13 billion, ...'); a share of the total; a yearly average of a total dated by a decade or a span; a difference between two named parties' figures; a stated length of years against its span, in any wording and with day or month dates; a rate verb between a one-year count and a multi-year count; a signed change; a share written 'N of the M, about <fraction>'; figures written with a currency sign) and builds exact entailment problems; the engine then says whether the specialist's arithmetic holds. A stated derived figure, comparison or superlative no problem can be built for is returned as undecided (`undecided_quant_statements`), and so is every worked equation (`worked_equations`: written arithmetic in '=' form, which no reader on these branches decides), so no stated arithmetic crosses the hub silently. Each check carries the phrase it reads, so its finding names the claim that states it. No model is involved. Every statement is read in the general reading, or in the SI reading of the STEM branches (`reading`: SI units, scientific notation, signs, repeated folds, a sign-aware band, the SI quant view with the maths masked; the module docstring lists what each reading reads). |
| `packs.py` | `CorePack(reading=...)` (every branch, in the general reading but on the STEM branches, which run `CORE_SI = CorePack(reading=SI_READING)`: quotation grounding, a structured claim's quotation against its own source reference, numeric self-consistency, undecided arithmetic, from-memory labelling, unverifiable / undelimited / misattributed quotations, undecided chronology, self-certification, support cycles in any delivered report, parsed or structured; each check runs on its own, a failing one being `CORE-INTERNAL-001`; at most `MAX_FORMAL_CHECKS` (500) formal checks per transmission, the rest named as undecided), `HistoryPack` (pack rules + request-aware suppression), `EnglishPack`, `PsychologyPack` (study attributions need grounding; "significant" needs a figure), `EconomicsPack` (elasticity arithmetic: the term in full or as PED, YED, XED or PES, an ASCII or Unicode minus, stated in prose with its two percentage changes on its line or worked as a division, 'PED = −12.50 ÷ 18.75 = −0.67', whose sign is checked too), `BusinessPack` (margins: in prose, or worked as '(A ÷ B) × 100 = m%' under a margin label), `GenericPack`. A worked equation a subject pack decides (`pack_decided_equations`) is not also named undecided by the core pack. |
| `stem_pack.py` | `StemPack(mode)`: the STEM pack of the `sciences`, `mathematics` and `computer_science` branches (ST findings and the STEM engine checks of `stem.checks`, see below). |
| `registry.py` | The default registry and how subjects map to branches (`CORE` in the general reading; `CORE_SI = CorePack(reading=SI_READING)` first in every STEM branch). |
| `generic_parser.py` | Fallback parser for subjects without a dedicated adapter. Claim ids are qualified by the agent, `g{paragraph}.{unit}@{agent_id}` (`g4.2@economics-specialist`), so two generic-branch reports of one task (Economics with Business, Physics with Mathematics) never share an id (no INT-REQ-016, no INT-LEDGER-014); the fold claim of an oversized answer keeps `g.tail`. A paragraph is read line by line: a line that opens with `=` continues the equation of the line before it (one claim per equation chain), a soft-wrapped prose line or a line ending on a comma or connective continues its line, and every other line break ends a claim, so each line of working, list item and result is a claim of its own; a sentence also ends after a closing quotation mark ('."', '.”'). Part labels ("(a) [2]", "(i) [2 marks]", "Part (a) — find — 3 marks") and mark annotations ("[1]", "[1 spare]", "M1", "(A1)") are no claims (`original_response` keeps them). Notes (`markdown.NOTE_LEAD_RE`: "Note:", "Note on ...:", "N.B.", "Next step:", "Confidence:", and "Limit:" on this branch; a paragraph opened by a bare note lead is a note as a whole), questions and headings ("Measure: ..." stating no working, "Working for (b):", "Diagram 1: ...", a short title such as "2024 (no tax)") are roled `other`; a line of working or a bare value is never a note for having no letters. Each part's answer is a material `point`: a line led by "Answer:", "Result(s):", "Total:" or credited with an accuracy mark ("A1"), else the last line of the part's first run of working with the rows before it that give the same quantity for another case, else the part's opening claim (every sentence of it when the part carries a "Why:" justification); a bare value opening a part ("(-1, 3)") always. Supports follow the stated direction and never cycle: a point opening its paragraph or part rests on the plain claims after it, a closing answer, judgement or consequence ("Therefore ...", "Consumers therefore pay ...") on the claims before it; caveats ("However ...") and "Assumption:" lines support nothing and an assumption is never a derived point; two labelled answers opening a paragraph ("Binary search: ... Linear search: ...") are coordinate. |
| `hub.py` | `RouterHub`: open a task from a work plan, dispatch requests, receive raw text or structured reports, read receipts. Nothing raises into the router: a structured report received as a mapping takes its sender and report id from its own fields when the call states none, any other non-text payload goes to the channel's payload path (REJECTED, `INT-REQ-009`), raw text with no stated sender or report id is REJECTED unparsed (`INT-REQ-009`), and a task id no plan opened gets a REJECTED receipt from a quarantine channel (`INT-HANDOFF-001` for a dispatch, `INT-REQ-009` naming the task for a reply); `receipts()` of such a task lists those receipts. |

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
  `early`/`late`/`mid` + year, month-year, day-month-year, `January 30, 1933` and a decade (`from
  about 2.8 million in the 1870s to about 5.2 million in the 1880s, a tripling` is a
  COUNTEREXAMPLE; a decade dates the decade's total, never an annual point or a year of a rate).
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
* Currency signs: a figure may carry `$`, `US$`, `£`, `€`, `¥`, `A$`, `C$` before its digits
  (`from $4.03 to $2.80`, `about $13 billion`, `an increase of about $1.4 billion`, `£600 million`).
  The sign is the figure's unit of account: `$4.03` and `4.03 dollars` are one unit, a sign on one
  figure carries to a bare figure beside it (`from $4 billion to 6 billion`), and a sign against a
  noun naming something else (`from $4 billion to 6 billion marks`) or another sign is not
  comparable (undecided, `CORE-QNT-001`). So a change in dollars is decided exactly as the same
  sentence written in `billion dollars`: in hi-t11 `devalued from $4.03 to $2.80` is a checked fall,
  `devalued from $2.80 to $4.03` and `rose from $4.03 to $2.80` are COUNTEREXAMPLEs, and `a fall of
  about 50 per cent` on that pair (true 30.5) is a COUNTEREXAMPLE.
* Figure length: a numeral of more than `MAX_FIGURE_DIGITS` (1,000) digits is never converted; the
  statement holding it is reported undecided (`CORE-QNT-001`, 'too large to check') and the report's
  other checks still run. A figure never starts inside another (`4.03` is not `03`, `1234,567` is not
  `4,567`), so a run of 200,000 digits is read, and refused, in linear time.
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
  signed figure such as `a rise of -10 per cent` reverses the direction, with an ASCII or a Unicode
  minus), `a change of 20 per cent` / `changed by 20 per cent` (the direction is the figures' own
  unless a sign states it: `a change of −36 per cent` is a fall, `+36` a rise; `a change of 0 per
  cent` between different figures fails), `a rise of 25 percentage points` between two per-cent figures (absolute difference;
  plain `points` between other figures too), word fractions (`a fall of about a half`, `fell by
  two-thirds`), fold changes (`doubled`, `doubling`, `halved`, `halving`, `tripling`,
  `threefold`, `2.5-fold`, `1,670-fold`, `hundredfold`, `thousandfold`, `millionfold`,
  `trillionfold`) and multiples (`six times its earlier length`, `four times as large`, `twice
  its 1928 level`). A qualifier may stand before a fold word with an article between: `more
  than a tripling`, `over a threefold rise` (lower bounds), `nearly a doubling` (approached
  from below, see the tolerance rule).
* Absolute changes and average rates: `an increase of about 6,500 miles`, `a fall of 3,000
  men`, `added roughly 4,500 miles`, `adding`, `gained`, `lost`, `shed`, `rose by 2.9 million
  tonnes` (the difference of the pair, after minus before, or before minus after for a fall), and a
  signed change `changed by −6 per 1,000, from 11 in 1990 to 7 in 2020` or `a change of −6` (a minus
  a fall, a plus a rise, unsigned the figures' own direction: `changed by −6` against 11 to 7 is a
  COUNTEREXAMPLE, `−4` is ENTAILED),
  and `an average of 450 miles a year`, `averaging`, `added 450 miles a year` (the difference
  divided by the years between the pair's dates). The amount's unit must be comparable with the
  pair's (a scale with a scale, a noun with the same noun: `4,500 miles` against figures in
  tonnes is undecided), never a per cent, point, fraction or fold (those are the relative
  readings). `from about 1,500 miles in 1840 to about 6,000 miles in 1850, an increase of about
  6,500 miles` is a COUNTEREXAMPLE.
* A yearly average of a dated total: `About 5.2 million people entered the United States in the 1880s,
  an average of about 900,000 a year` reads the one total its clause dates by a decade (ten years) or a
  span (`from 1881 to 1890`: nine or ten years, either count accepted) over those years, so 900,000 is a
  COUNTEREXAMPLE and 520,000 is ENTAILED. A figure that is itself a rate (`500,000 people a year`) or the
  amount of a derived phrase is no total, and the average is then undecided.
* The direction of a pair: a from/to pair that no derived figure binds, governed by a direction
  word right before its `from` (`pig iron rising from about 3.3 million tonnes to about 6.2
  million`, `rose sharply from`; a fall also `devalued`, `depreciated`, `reduced`, `cut`,
  `lowered`; a rise also `revalued`, `appreciated`, `raised`) or inside a continuation (`before
  falling to`), is checked for that direction: the later figure above the earlier for a rise, below it for a fall. A list of
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
* Parts of a stated total (kind `parts`): `..., of which the United Kingdom received about $3.2
  billion and France about $2.7 billion` after `about $13 billion` (also `most of which`, `of whom`),
  and `1882 alone brought nearly 790,000` after `About 5.2 million people entered ... in the 1880s`
  (a year inside the decade or range the total covers, or a named party: `the United Kingdom alone
  received`): the parts may not exceed the total by more than the tolerance (each figure may be
  rounded). `about $23.2 billion` of $13 billion, or `nearly 7.9 million` of 5.2 million, is a
  COUNTEREXAMPLE. A total that opens its clause (`Of the $13 billion, Britain received about $3.2
  billion and France about $2.7 billion`, `Out of about 5.2 million arrivals in the 1880s, about 790,000
  came in 1882`, `Of the 608 seats in July 1932, the NSDAP won 230 and the SPD 133`) bounds the figures
  after its comma the same way; those parts end at a comparison or a change (`more than the $2.7
  billion of France`, `up from`, `against`), which states no part. A verb right after a figure is not
  the noun of the thing counted (`790,000 came in 1882` counts arrivals like its total). Parts whose
  units, nouns or currency cannot be compared with the total are undecided (`CORE-QNT-001`).
* A share of the total (kind `share`): `<part>, about a quarter of the decade's total`, `about 60
  per cent of the total`, `about two-thirds of the total` (also `sum`, `whole`, `aggregate`, `the
  decade's arrivals`) is read as the figure right before it over the figure before that in its
  sentence, within the tolerance rule; hi-p5's `nearly 790,000, about a quarter of the decade's
  total` (15 per cent of 5.2 million) is a COUNTEREXAMPLE. A share stated for a named party with no
  figure right before it (`..., so the United Kingdom alone received about two-thirds of the total`)
  is read as the one figure the paragraph states for that party (`the United Kingdom received about
  $3.2 billion`) over the total its parts are stated `of which`: a COUNTEREXAMPLE there, ENTAILED for
  `about a quarter`. A share whose part or total is not stated as a figure (a party with no figure, or
  several) is undecided (`CORE-QNT-001`). `N per cent of M, or P` is read as before. A share written `N of the M <noun>, about
  <fraction or per cent>` (`356 of the 535 seats, about three-quarters`, `... (about 67 per cent)`) is N over M, and a share stated right
  after the one part of a total that opens the clause (`Of the 535 seats, the list was guaranteed 356, about three-quarters`) is that part
  over that total: both COUNTEREXAMPLEs (66.5 per cent), `about two-thirds` ENTAILED.
* Totals: `A and B ..., a total of C` (`totalling`, `together`, `in total`, `making`, `giving`) with
  a currency sign or a noun after any figure (`3.2 billion dollars and France about 2.7 billion
  dollars, a total of about 9 billion dollars` is a COUNTEREXAMPLE). A stated total that no check
  reads while its parts are meant is undecided (`CORE-QNT-001`), naming why: a subject that refers to
  parts it does not state (`The two received a total of about 9 billion dollars`, `Both received a
  combined $5.9 billion`), or a single figure before it (`Britain received about $3.2 billion, a total
  of about $9 billion`). A plain stated quantity (`The famine killed a total of about 1 million
  people`) states no arithmetic and is not read.
* Differences (kind `difference`): `the United Kingdom received about $2 billion more than France`
  (`less`, `fewer`, `higher`, `lower`, `larger`, `smaller`, `greater`) is read against the one figure
  the paragraph states right after each named party (`the United Kingdom received about $3.2
  billion`, `France about $2.7 billion`); a party with no figure, or several, is undecided.
* Durations (kind `duration`): a stated length of years (`for ten years`, `lasted five years`, `had run for more than twelve
  years`, `which lasted about five years`; a duration verb with or without `for`) is checked against its span (`from D1 to D2`,
  `between D1 and D2`, `after ... D1, until D2`, after the length or opening its clause; years, month-years or day-month-years). In
  years alone the length is the difference or the difference plus one (both end years counted): `for ten years, from 1882 to 1902`
  is a COUNTEREXAMPLE. With day or month dates it is the elapsed days / 365.2425 over every day the dates allow. `more than`, `over`,
  `at least`, `less than`, `under` are exact bounds (`more than twelve years, from 7 October 1949 to 13 August 1961`: 11 years 10
  months, a COUNTEREXAMPLE); `nearly`/`almost` approach the length from below (the approach band); `about`, `roughly` and no qualifier
  allow the tolerance rule or half a year (`lasted for about five years, from 1949 to 1961` is a COUNTEREXAMPLE, `twelve years, from
  7 October 1949 to 13 August 1961` ENTAILED). A sentence that states no span of its own is read against the one span an adjacent
  sentence states when that span shares a year with the sentence's dates, its bare year read as the day the sentence dates in it
  (hi-p7c: `ended a drain that had run for more than twelve years` with `Between the founding of the German Democratic Republic on 7
  October 1949 and 1961` next, 1961 read as 13 August 1961: a COUNTEREXAMPLE whose description says it was stated across sentences).
  A length whose sentence states two or more dates that cannot be paired into a span (a span in another clause), or whose dates are too
  coarse to decide it (`more than twelve years, from 7 October 1949 to 1961`: 11.2 to 12.2 years), is undecided (`CORE-QNT-001`); a
  length with one date or none (`ruled for ten years until his death in 1953`) states no arithmetic.
* Rate trends (kind `rate_trend`): `From 1961 the flow slowed to roughly fifteen states by 1968`
  (`slackened`, `eased`, `dwindled`; `quickened`, `accelerated`, `sped up`, `picked up`) compares
  the multi-year count per year of its span (both end years counted) with the one-year count the
  paragraph states for the year before the span (`in 1960, when seventeen African states became
  independent`): hi-t12's `slowed` is ENTAILED, `quickened` a COUNTEREXAMPLE; a rate verb whose
  counts cannot be read is undecided.
* Worked equations (`worked_equations`): a statement of a line of working (with the lines after it that open with `=` or `≈`; a
  line is cut at semicolons and full stops) whose `=` links put an arithmetic operator (`+ − × ÷ / * ^`, a spaced hyphen) between two
  figures before a link whose value is a figure with no further arithmetic (`$6,000 ÷ $2.00 = 3,000 loaves per month`, `(12 − 8) − 0 =
  4`, `= 31 ÷ 69 × 100 = 44.9`, `2.4 Ω + 0.50 Ω = 2.9 Ω`). This reader does not decide written arithmetic, so each one is returned
  undecided with that reason and named by the core pack (`CORE-QNT-001`, 'states worked arithmetic'), never passed silently and never
  given the reason that no pair of figures is stated; the Economics and Business packs decide the elasticities and margins they read.
  A formula with no figure on both sides of an operator (`(aged 0–14 + aged 65 and over) ÷ aged 15–64`), algebra (`a = 6 − 6t`) and a
  stated value (`PED = −0.67`) are not worked equations. (Decided readings of worked steps belong to the STEM branches' math front end.)
* Undecided arithmetic (`undecided_quant_statements`, reported by the core pack as
  `CORE-QNT-001`): a derived figure (relative, absolute, a rate or a multiple), a comparison with
  a named benchmark, a trend or a superlative that no problem can be built for is named with the
  reason (units that cannot be compared, no figures in its sentence and no dated series in the
  paragraph that supplies them, two series that could be meant, an anaphor with two candidate
  years, a decade whose neighbours are not stated decade by decade, a compared figure that is not
  stated, a part, share, total or difference whose figures cannot be read, a figure too large to
  check), so no stated arithmetic crosses the hub silently. The reason is true to the sentence: `no
  figures are stated with it in its sentence` only when it states none (`The United Kingdom thus
  received twice as much as France.`), and otherwise `its sentence states no pair of figures it can be
  read against (only 5.2 million)`, naming the figures it does state, per cents included (ec-p7a: `fell by
  $34.50 million per year (17.97%) between 2024 and 2025` is `only 17.97%`); when its sentence states its figures only in
  lines of working (`Result: the krona appreciated by 20.00%` under them), the reason says so and names the first worked equation.
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
  there: undecided, since which event is followed is not stated). A year that opens the cue's own
  clause (`In 1958 Guinea followed on 2 October`: `In <year>`, a short noun phrase, the cue) dates
  the subject too (2 October 1958), never the event it follows; that event is then taken from
  before the clause or from the previous sentence, whose one yearless day takes its one year (`In
  1957 ... Ghana, on 6 March.` is 6 March 1957). So hi-t12's `In 1958 Guinea followed on 2 October`
  is ENTAILED and `In 1956 Guinea followed` a COUNTEREXAMPLE; with no dated event before it the
  relation is undecided (`CORE-CHR-001`), never read against its own year. So `After the
  murder of Rathenau in June 1922, the Law ... followed in July 1922` is ENTAILED and the
  reversed dates a COUNTEREXAMPLE. A comma right after an intransitive `followed` or `preceded` ends
  the verb: in `From 1961 to 1968 roughly fifteen more states followed, including Botswana in 1969`
  the dates after the comma belong to the list's cue (`including`: 1969 outside 1961 to 1968), never to
  an order.
* Coordinated cues: in `The Ruhr was occupied in January 1923, after the London ultimatum of
  May 1921 and before the Dawes Plan of 1922` the second cue orders the clause's subject
  (January 1923), not the first cue's object, so the stated (false) `January 1923 before 1922`
  is checked; when the subject carries no date the second relation is undecided.
* Coordinated objects: every dated item of a list after a cue is ordered against the subject, not
  only the first: `Kenya became independent in 1963, after Tanganyika in 1961 and Botswana in 1966`
  checks 1961 and 1966 (a COUNTEREXAMPLE), `..., before Kenya in 1963 and Ghana in 1957` checks
  both. The list (`_list_items`) is cut at commas, `and`, `as well as` (never inside a date such as
  `October 12, 1962`) and ends before a fragment that reads as a clause (`and peaked in 1932`, `and
  before the Dawes Plan of 1922`). Two years joined by `and` are a period only after `between` (`between 1961 and 1968`), so `including
  peaks in 1953 and 1963` is two items and `HI-CHR-001` names 1963 alone.
* An event named without a date: a side of a cue with no date in the sentence is looked up in
  the paragraph when it is a definite noun phrase headed by an event noun (`that election`,
  `the treaty`, `the Danatbank collapse`): the one date another sentence gives the noun within
  a few words in its clause (`the September 1930 election`, `Signed on 28 June 1919, the
  treaty`), in a comma-bounded participial aside after it (`The Economic Cooperation Act, signed on
  3 April 1948, launched ...`), or by a date that opens its clause and governs a verb of enactment
  whose object it is (`on 6 May 1882 President Chester A. Arthur signed the Chinese Exclusion
  Act`), never a date that bounds a range (`up to 1923`, `since 1793`) and never a mention
  whose noun carries a modifier the side does not (`The agrarian crisis that began in 1928` is
  not `the crisis`). Both sides dated: the relation is decided and its reason names the
  sentence the date came from (`That election came after the Danatbank collapse of July 1931`
  with the election dated September 1930 a sentence earlier is a COUNTEREXAMPLE). One side
  dated: undecided (`CORE-CHR-001`) when the undated side is a demonstrative that must refer
  back (`that election`) or when the dated side's date came from another sentence (`instability
  began before the treaty`: stated across sentences); a dated event and an undated,
  non-anaphoric one in the same sentence (`the budget fell after the vote of July 1930`) state
  no checkable order and yield nothing, unless the undated side names an event by a proper name
  (`before the Marshall Act`), which is undecided (`CORE-CHR-001`: a named event the paragraph does
  not date). A pronoun subject (`..., and it came before the Economic Cooperation Act was signed`)
  takes the one date of the clause before it in the same sentence (`West Germany's currency reform
  of 20 June 1948 ...`), so that hi-t11 variant is a COUNTEREXAMPLE.
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
* Containment (relation kind `within`): `X, including Y`, `X, which included Y` put EVERY dated
  item of the list after the cue (`including Tanganyika in 1961, Kenya in 1963 and Botswana in
  1966`: three relations) inside the outer period read from the clause before it: a decade (`the
  1840s`), a range (`1845 to 1847`, `1899-1902`, `from 1961 to 1968`, `between 1961 and 1968`), the
  span `From 1961 ... by 1968` (1961 to 1968), a bare `by 1968` / `until 1968` as an upper bound with
  an open start (`the period up to 1968`: only the end is checked), a bare `from 1961` as a lower
  bound with an open end, else the clause's last date (a month-year, a year or a day). So hi-t12's
  `From 1961 the flow slowed to roughly fifteen states by 1968, including ...` is ENTAILED, and
  `Kenya in 1973` or `Botswana in 1971` is a COUNTEREXAMPLE naming that item. `among them` (`among
  these`, `among which`) with its list BEFORE the cue (`..., when seventeen African states became
  independent, Nigeria on 1 October and the Belgian Congo on 30 June among them`) puts every item of
  that list inside the period of the clause governing it (1960); with the list after the cue it is
  read like `including`. The items of one list are one engine problem (every item inside the one
  period), so a list costs one engine call; its description names first any item the dates place
  outside the period (`1973 within 1961 to 1968; ...`), and `HI-CHR-001` names each such item. An inner date with no year takes
  the outer period's one year (`Reverses in December 1899, including ... Magersfontein on 11
  December`); `11 November` there, or `The 1840s, which included the Railway Mania of 1855 to 1857`,
  is a COUNTEREXAMPLE. `Y during X`, `Y within X`, `amid X` put a dated event inside the period after
  the cue, and an inner range need only meet it (kind `overlaps`).
* `<period>, when <clause>` (relation kind `within`, cue `when`): a date the `when` clause gives an
  occurrence (`The pace changed in 1960, when Nigeria became independent on 1 October`) lies within the
  period standing right before `when`; `on 1 October 1961` there is a COUNTEREXAMPLE. A beginning dated
  in an aside or relative clause of it (`for 1950 to 1952, when ... demand from the Korean War, begun on
  25 June 1950, lifted orders`; `In 1960, when the war that began in 1954 ...`) or an occurrence in the
  pluperfect (`In 1919, when the war had ended in November 1918, ...`) lies no later than the period's
  end, an open start: hi-t11's genuine sentence is ENTAILED and `begun on 25 June 1953` a
  COUNTEREXAMPLE. A date after an ordering cue in the clause belongs to that cue, and a date after
  `would` or `later`, a bound (`until 1968`) or a period that is itself a bound (`By 1968, when ...`)
  states nothing about the period and is not read. A date inside a `when` clause that follows an
  ordering cue's object is the `when` clause's, never that object's. An inner date stated more coarsely
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
| `CORE-SRC-003` | warning / info | a quotation with no text to check it against: with no text supplied, every quotation; with texts supplied, a quotation that no supplied text holds and whose sentence credits it to no supplied text (the parser recorded no source reference, so the grounding check never sees it), and, texts supplied or not, every quotation a parser recorded as credited to no text (the shared attribution rule's assumption), whatever its length ('Me ne frego'), on every branch, the English one included. Info only when the specialist's own label says the quotation is from memory (a label in the same sentence, or a label that speaks of quotations); a figures label does not vouch for a quotation. Quotations are read in straight, curly or mixed double marks, guillemets, and delimited single marks of two or more words, after JSON fragments are removed, exactly as the parsers read them. A quotation credited to a named text that does not hold it is the channel's `INT-REQ-003`, not this finding. Words the request itself holds are located there and are no unverifiable quotation (the guiding question's 'returning home', a true/false statement's 'toda', the pasted question's 'complete years'), and neither is a word the sentence says the text lacks ('the bruise comparison has no "like" or "as"', 'the text never says "ayudar"': a mention) or a word quoted from a quotation the answer already gives ('the verb "killed"' after '"We killed him openly"': counted once) |
| `CORE-SRC-004` | warning | a paragraph whose double marks (straight, curly, mixed, guillemets) cannot be paired; the dangling mark is located by context so the quotations the writer did delimit are still checked |
| `CORE-SRC-005` | error / warning | a quotation credited in its sentence to a named source (a supplied text's author or title, a peer agent such as `the History specialist`, `the poem` when one text was supplied) with a saying verb (`says`, `writes`, `admits`, `identifies`, `suggests`, ...), but located only in a different supplied text: the words are genuine, the credit is wrong. A credit to an author or work that was NOT supplied to this agent (`Hardy's speaker himself admits that his justification "becomes circular"`, `Hardy's poem identifies ... "exposes a motive of poverty"`, `<Name> writes`, and `the poem` / `the speaker` when no literary text was supplied and the sentence names no other source) is an error when the words occur only in a colleague's report, in the colleague's own prose rather than inside a quotation the colleague makes (the colleague quoting the poem is the poem's words, so `Hardy's speaker says he "had sold his traps"` is no finding). In a reporting clause (`The English specialist argues that Blake presents ... "..."`) the OUTER speaker is the credited source, so a colleague's words reported correctly are no finding. When the sentence names a second source before the quotation and that source holds the words, the credit is ambiguous: a warning naming both, not an error. A quotation found in no text is left to the grounding check (`INT-REQ-003`) or, when uncredited, to `CORE-SRC-003`. The finding names the claim whose source reference carries the misattributed excerpt and the sentence's own claim, never the claims of the sentence's other, correctly credited quotations |
| `CORE-SRC-006` | error | a claim whose text quotes words no supplied text holds, while the claim (or a claim it rests on) credits a supplied text through its source references and no reference or note carries those words: the claim's quotation and its reference's excerpt disagree (`"Had we two but met"` in the claim, `Had he and I but met` in the reference), so the grounding check, which reads the reference, does not vouch for the words stated. On the English branch a quotation with no reference at all, in a report on one literary text, is credited to that text as the English parser credits it. A parsed report never raises it (every quotation a parser reads is carried by a reference or recorded in an assumption); the structured contract does. The quotation is then not also reported as `CORE-SRC-003` |
| `CORE-CHR-001` | warning | a sentence orders two dated events, places a date within a period or at a point of one, but the relation could not be decided (see above: an aside date, an unstated year, an equal month or year, a coordinated cue whose subject carries no date, an event dated only in another sentence beside one the paragraph does not date, a demonstrative that refers to no identifiable dated event, an interval against a named event never dated, a named event the paragraph does not date, an intransitive `followed` with no dated event before it, an inner date coarser than its period, a point of a period no duration states, a relation beyond the per-transmission check limit); the stated relation was not checked |
| `CORE-QNT-001` | warning | a derived figure, comparison, trend or superlative the sentence states could not be checked, or a worked equation this reader does not decide ('states worked arithmetic'), or a stated length of years whose dates cannot be paired or are too coarse (see the arithmetic section: incomparable units, no figures in its sentence and none in the paragraph's dated series, two series that could be meant, an ambiguous `that year`, a decade superlative whose other decades are not stated, a compared figure that is not stated, a part, share, total, difference or rate trend whose figures cannot be read (a total whose parts are meant but not stated as figures), a figure too large to check, a statement beyond the per-transmission check limit); one finding per sentence and reason, naming the phrases (at most about 900 characters of them, the rest counted) and the claims that state them; the stated arithmetic was not checked |
| `CORE-SELF-001` | warning | verification-status language or a receipt imitation in the body, or a verification label on a sentence ('Verified: ...', '... (verified).', '[verified] ...', 'Checked: ...', '..., as formally verified.', 'Verified.'; `markdown.verification_label`): a label attached to content leaves the content a claim with its own role, and the finding names the claim that holds the label; agent self-reports are advisory |
| `CORE-STR-001` | error | a claim supports itself, or claims form a cycle through `supporting_claim_ids`, in a delivered report on any branch, parsed or structured (the same cycle reading as the generic structured adapter's `GEN-STR-002`): none of them can be evidence for the others; the finding names the claims of each cycle |
| `CORE-INTERNAL-001` | error | one check of the core pack failed internally; its findings (and the formal checks built from the same reading) are missing, the other checks ran |
| `PACK-INTERNAL-001` | error | a pack's `checks` or `formal_checks` failed internally (`SubjectBranch.run_packs`); the other packs' findings and formal checks are on the receipt |
| `BR-INTERNAL-001` | warning | raised beside `PACK-INTERNAL-001` for the same failing call: the pack, the exception type and the stage (`checks` or `formal checks`), never the exception's text; the router must not treat the pack as passed |

The core pack sends at most `MAX_FORMAL_CHECKS` (500) formal checks to the engine per transmission
(arithmetic first, then chronology), so an answer far beyond any request's length cannot hold the hub
for seconds; the arithmetic statements and dated relations beyond the limit are reported as
`CORE-QNT-001` / `CORE-CHR-001` ('not checked: the limit of 500 formal checks per transmission was
reached'), naming their claims.

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
  most important cause was`, `mattered most`, `1960 marked the decisive break`, a degree adjective
  standing alone as the predicate (`1960 was decisive.`), `The year of decision was 1960.`, `The
  real break came in 1960.`, a verb of standing as before the turning point, a verdict noun or the
  watershed (`1960 stands out as the turning point.`, `1960 emerged as the decisive year.`, `1960 ranks
  as the watershed.`; `1960 ranks as a year of change.` stays a description), with a singular or plural copula and a period or judgement noun: `The 1840s were the most decisive decade.`, `The 1840s were the decisive
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
* An answer with no prose sentence (only a pasted JSON report or receipt, or markup) is one `other`
  claim holding the text, never material (its self-report in the advisory field when it imitates a
  receipt), so the hub delivers it and names the fault (`INT-REQ-012`, and `CORE-SELF-001` for a
  receipt imitation), as on the English branch, whatever the nesting depth of a bracket-only answer.
  An empty answer is still an adapter error (`INT-REQ-009`).
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
* A closing note is a note, never a body paragraph (`has_note_lead`, `is_source_caveat`): a sentence opened by a bare note lead
  (`Note:`, `N.B.`, `Next step:`, `Confidence:`, `Limit:`, `Caveat:`) is role `other`, and a paragraph whose first sentence it opens is a
  note paragraph as a whole, whatever its length, dates or figures (`Note on ...:` names a subject and is not a bare lead). A caveat about
  the answer's own sources or library (`my sources do not confirm the exact emigration total`, `the textbook library and MyLib were
  unavailable`, `no approved source here confirms ...`) is a note with or without a lead, unless the sentence goes on to state a dated item
  or a figure. The caveat is recorded as an assumption, with certainty capped at `probable`, on every claim that carries the figure it
  says the answer gives in its place (its quoted words; what it says is not confirmed is no figure the answer states): hi-p7c's `Note: my sources do not confirm the exact emigration
  total, so the figure is given as 'millions'` caps h1.2 (`millions of East Germans left`) and stays h2.1, `other`, so a faithful synthesis
  that leaves the note out carries no `INT-LEDGER-019`, the note is never judged as a body paragraph (no `HI-STR-001`/`HI-STR-002` on it),
  and `HI-SRC-004` says what the note says.
* Only the sentence that certifies the answer's own verification, or is shaped like a
  receipt or JSON, becomes a note (role `other`, its self-report in the advisory field):
  the paragraph's other sentences keep their roles and the demotion is recorded as an
  unresolved issue naming the sentence. A paragraph that is nothing but notes or JSON is a
  note paragraph (no material point, no HI-STR findings on it).
* A quotation is attributed to the supplied text its sentence names (author, surname,
  title, or a peer specialist by name, through the English parser's `documents_named`; a
  specialist is named by its agent id and, for an id with a course or qualifier, by its subject's
  first word as well, "the Mathematics specialist" for `mathematics-aa-specialist`:
  `sources.specialist_names`)
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
* Support links follow the argument and never form a cycle (`CORE-STR-001` would name one): a
  body paragraph's point is supported by the paragraph's evidence, analysis, counter-case and
  reported views (`evidence`, `analysis`, `counter_evidence`, `perspective`), never by a judgement or
  a link; a judgement or link is supported by the point and the claims before it, never by a later
  judgement (in hi-t12 the judgement `The decisive turning point was 1960.` rests on the point and the
  evidence before it, and the point no longer rests on the judgement). Judgement and link claims are
  therefore PROPOSITIONAL_ARGUMENT eligible like English links. Dated claims
  under a from-memory label are capped at certainty `probable`, and so is any claim whose own
  inline label the parser set aside, dated or not (`A regular private's pay of about a shilling a
  day (from memory) was a real draw ...`), so a synthesis that restates it as established is
  `INT-LEDGER-003`.

## STEM branches (docs/STEM_DESIGN.md)

Physics, Chemistry, Biology, ESS, SEHS, Design Technology and the `stem` profile (general
science, engineering, a label naming two or more sciences) route to `sciences`; Mathematics AA,
AI and an unspecified course to `mathematics`; Computer Science to `computer_science`.
`generic` stays the default for an unrecognised subject. Each STEM branch runs:

* `StemTextParser` (`adapters/stem_specialist`): claims are the shared `StemDocument`'s
  statements, offset substrings of the answer with ids `s<paragraph>.<n>` (`m` in mathematics,
  `c` in Computer Science, so two STEM branches never share a claim id on one task);
* `CORE_SI`: the core pack in SI reading (`quant` module docstring, `stem/si_reading.py`): only
  spelled-out scale words scale a figure (`300 K`, `500 mm to 2 m` read as written), units of
  the STEM table convert exactly and pair only when their dimensions agree, scientific
  notation and signs are read, `halved twice` is a factor of 1/4, the band is sign-aware, and
  the prose extractor reads the SI quant view (maths masked) so it never checks the maths the
  STEM pack checks; quotations are read on the quotation view (an inch mark `12"` is not a
  quotation mark), chronology and self-certification on the prose view (`1500 K` is no year);
  findings name the STEM claim ids. `CORE` (the general reading) is byte-identical to before
  on every other branch (`tests/branches/test_quant_si_reading.py` pins it on a 570-text
  reference corpus);
* `StemPack(mode)`: the front end's and the checks stage's ST findings (codes and severities of
  design section 8.2; never an error: every STEM error is an engine result) and one
  `FormalCheck` per planned check (`stem-eq-N`, `stem-sub-N`, `stem-alg-N`, ...) with its claim
  ids, its named policy (`linear` or `nonlinear`), its failure severity (`warning` for checks
  that relied on a reading the report did not state) and `inconsistent_is_failure=False`. On
  relay (no request) `stem-giv` and `stem-tgt` are not built. A failure inside the pack is
  ST-INTERNAL-001, never an exception and never a silent pass;
* the STEM hub hooks (`stem/hub_hooks.py`): coverage words from the dimensions of a claim's
  quantities, the echo exemption for an answer that computes, the STEM imperatives, and the
  word-count view (a maths span or a code block is one word).

### What the STEM pack checks

One shared `StemDocument` per (answer, request, profile) is read by the parser, the pack and
`CORE_SI`, so claim ids, sentence numbers and check ids cannot diverge. The front end
(`stem/`) reads LaTeX, Unicode, ASCII and verbal arithmetic with a hand-written lexer and a
bounded Pratt parser; nothing evaluates agent text. Every relation it recognises ends as a
planned check, a binding, a law (`formula`), a premise-free `context` line, or an undecided
relation named with its ST code and reason. The checks stage (`stem/checks.py`,
`stem/to_ir.py`; encodings in `stem/ENCODINGS.md`) turns each planned check into an IR 1.0
problem:

| Kind | Check | Decided | Failure |
| --- | --- | --- | --- |
| `stem_arithmetic` | `stem-eq-N` | written arithmetic `E = S` within the STEM tolerance band | INT-SUBJ-001 (INT-SUBJ-004 after a booklet value or an unknown unit) |
| `stem_substitution` | `stem-sub-N` | substituted values against their symbols' bindings, or the symbolic side under its bindings | as above |
| `stem_algebra` | `stem-alg-N` | the step follows from the preceding relation (with bindings, up to 8 stated formulas, guards) | INT-SUBJ-001; INT-SUBJ-004 when the step brings in symbols nothing connects |
| `stem_solution` | `stem-sol-N` | stated roots satisfy the equation; the full set when it is claimed and the domain is not restricted; a root may be a decimal the answer states in prose for the quantity it named by the symbol (membership only, within the '=' band) | INT-SUBJ-001 |
| `stem_model` | `stem-mod-N` | an exponential model of the answer or the request applied at an argument (`P(t + 4) = P₀e^(k(t + 1))` after `P = P₀e^(kt)`) has a solution: Form S over the variables, every power of an exponent in symbols read through positive variables (a letter defined as two models: either), so UNSATISFIABLE proves that no value satisfies it and SATISFIABLE never shows that it holds | INT-SUBJ-001 |
| `stem_conversion` | `stem-cnv-N` | an explicit unit conversion with exact factors | INT-SUBJ-001 (INT-SUBJ-004 with an unknown unit) |
| `stem_comparison` | `stem-cmp-N` | a stated order or inequality, or an inequality step | INT-SUBJ-001 |
| `stem_result` | `stem-res-N` | a prose restatement against the chain's final value | INT-SUBJ-001 (INT-SUBJ-004 with an unknown unit) |
| `stem_given` | `stem-giv-N` | a Given value against the request | INT-SUBJ-004 (warning) |
| `stem_target` | `stem-tgt-N` | the final value against a show-that target | INT-SUBJ-004 (warning) |
| `stem_balance` | `stem-chem-N` | element and charge balance (tallies per element and side) | INT-SUBJ-001 |
| `stem_boolean` | `stem-bool-N` | a Boolean identity (`¬(lhs ⇔ rhs)` must be unsatisfiable) | INT-SUBJ-001 |
| `stem_truth_table` | `stem-tt-N` | every stated truth-table row | INT-SUBJ-001 |
| `stem_base` | `stem-base-N` | a based-numeral conversion as exact integer arithmetic | INT-SUBJ-001 |

Every STEM check has `inconsistent_is_failure=False` (inconsistent premises point to an earlier
line, which its own check reports, or to a domain outside the encodings, so they are undecided:
INT-SUBJ-002), a policy read from the built IR (`nonlinear` exactly when a product has two
factors that hold variables), and a description that names the statement, the claims, the
tolerance rule, the readings and any constant the pack supplied. Undecided outcomes are
INT-SUBJ-002; the channel also runs a report's STEM checks under an 8 s wall-clock budget, and
checks left when it is spent are INT-SUBJ-002, never success. Statement ids map to the report's
claims by id (`s1.2`, or `m1.2`/`c1.2` in the other two branches), else by offset overlap, else
by the shared two-way substring rule, and descriptions and messages are relabelled to the
report's own claim ids. The pack keeps a 32-entry cache per report and request; the front end
keeps a 64-entry document cache.

Worked example (the case observed before STEM support): in `a = (20 - 0)/4.0 = 6.0 m s⁻²`
(claim `s1.2`) the link `(20 - 0)/4.0 = 6.0` becomes `stem-eq-1`, the entailment
`c = 20/4, r = 6 ⊢ |c − r| ≤ 0.05 + (1/100)·|c|` under the linear policy. Z3 returns
COUNTEREXAMPLE with `c = 5`, `r = 6`; the receipt carries INT-SUBJ-001 (error) on `s1.2` with
those values, and the report is delivered ACCEPTED_WITH_FINDINGS. The top-level `README.md`
shows the full problem.

Every STEM problem's `notes` opens with the scope statement (`stem.tolerance.STEM_SCOPE`): a
STEM check proves a property of its encoding only, namely that the written arithmetic,
substitution, conversion, algebraic step, balance or Boolean identity holds, or does not hold,
under the stated premises, the documented readings and the STEM tolerance rule. It does not
establish that a law applies, that data are true, that a model is physically valid, that a unit
is the right one beyond the dimension and conversion checks, or that the answer is what the
question wanted. The ST finding codes and severities are listed in the top-level `README.md`
and in design section 8.2; none of them is an error. Measured results:
`docs/STEM_RESULTS.md`.

Recorded behaviour change (design section 18, item 1, for the overseer audit and sign-off):
STEM subjects route to these branches instead of `generic`; the two routing assertions that
encoded the old routing (`tests/branches/test_hub.py`, `tests/branches/test_quant_and_packs.py`)
were replaced by assertions of equal strength for `sciences`, each with an unknown → `generic`
assertion beside it.

## Pack isolation (`PACK-INTERNAL-001`, `BR-INTERNAL-001`)

`SubjectBranch.run_packs` calls every pack's `checks` and formal checks in a guard. A pack that
raises is named by the hub's PACK-INTERNAL-001 error and by a BR-INTERNAL-001 warning (the pack,
the exception type, the stage; never the exception's text), its findings are missing from the
receipt and the router must not read them as a pass; the other packs still run.

Adding a subject: write a pack (deterministic checks citing the pack's working rules,
plus any formal check templates), optionally an adapter, and register a branch. The
hub integrity never has to be touched. Receipts carry `branch`, `structural_findings`
and `formal_checks` so the router and Overseer can see which branch judged what.
