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
| `quant.py` | Finds a report's own quantitative statements (every pair of figures of a clause bound to its own stated percentage change, percentage-point difference, word fraction or fold change; a derived figure, a trend or a superlative stated across sentences, read against the paragraph's dated series; shares; totals) and builds exact entailment problems; the engine then says whether the specialist's arithmetic holds. A stated derived figure no problem can be built for is returned as undecided (`undecided_quant_statements`). No model is involved. |
| `packs.py` | `CorePack` (every branch: quotation grounding, numeric self-consistency, undecided arithmetic, from-memory labelling, unverifiable / undelimited / misattributed quotations, undecided chronology, self-certification), `HistoryPack` (pack rules + request-aware suppression), `EnglishPack`, `PsychologyPack` (study attributions need grounding; "significant" needs a figure), `EconomicsPack` (elasticity arithmetic), `BusinessPack` (margins), `GenericPack`. |
| `registry.py` | The default registry and how subjects map to branches. |
| `generic_parser.py` | Fallback sentence-level parser for subjects without a dedicated adapter. |
| `hub.py` | `RouterHub`: open a task from a work plan, dispatch requests, receive raw text or structured reports, read receipts. Optional: `observers=` and `auditor=` (the Overseer's transfer auditor: `clearance`, `audit`, `view`, `review`, `close_task`, `closed_channels`, and for several agents answering one input `consolidate`, `repeats`, `review_pool`; see below). |

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
the core pack apply it before reading quotations, so JSON strings are never quotations.

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
  `trillionfold`). A qualifier may stand before a fold word with an article between: `more
  than a tripling`, `over a threefold rise` (lower bounds), `nearly a doubling`.
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
* Undecided arithmetic (`undecided_quant_statements`, reported by the core pack as
  `CORE-QNT-001`): a derived figure, trend or superlative that no problem can be built for is
  named with the reason (units that cannot be compared, no figures in its sentence and no
  dated series in the paragraph that supplies them, two series that could be meant, an
  anaphor with two candidate years), so no stated arithmetic crosses the hub silently.
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
* A relation with dates on both sides that cannot be paired (an aside about the subject's
  founding, an unstated year, an equal month) is reported by the core pack as `CORE-CHR-001`
  (warning) rather than skipped. `named after`, `look after` and similar are not cues.

## Core pack findings

| Code | Severity | Meaning |
| --- | --- | --- |
| `CORE-SRC-001` | error | a cited excerpt was not found in the supplied text (an excerpt located in another form, such as an initial capital, a line-break mark, diacritics or a long elision, is not this finding: the channel names it `INT-REQ-010` and the subject pack warns) |
| `CORE-SRC-002` | info | figures stated without sources, library references or a from-memory label |
| `CORE-SRC-003` | warning / info | a quotation with no text to check it against: with no text supplied, every quotation; with texts supplied, a quotation that no supplied text holds and whose sentence credits it to no supplied text (the parser recorded no source reference, so the grounding check never sees it), and every quotation a parser recorded as credited to no text (the shared attribution rule's assumption), whatever its length, on every branch, the English one included. Info only when the specialist's own label says the quotation is from memory (a label in the same sentence, or a label that speaks of quotations); a figures label does not vouch for a quotation. Quotations are read in straight, curly or mixed double marks, guillemets, and delimited single marks of two or more words, after JSON fragments are removed, exactly as the parsers read them. A quotation credited to a named text that does not hold it is the channel's `INT-REQ-003`, not this finding |
| `CORE-SRC-004` | warning | a paragraph whose double marks (straight, curly, mixed, guillemets) cannot be paired; the dangling mark is located by context so the quotations the writer did delimit are still checked |
| `CORE-SRC-005` | error / warning | a quotation credited in its sentence to a named source (a supplied text's author or title, a peer agent such as `the History specialist`, `the poem` when one text was supplied) with a saying verb, but located only in a different supplied text: the words are genuine, the credit is wrong. In a reporting clause (`The English specialist argues that Blake presents ... "..."`) the OUTER speaker is the credited source, so a colleague's words reported correctly are no finding. When the sentence names a second source before the quotation and that source holds the words, the credit is ambiguous: a warning naming both, not an error. A quotation found in no text is left to the grounding check (`INT-REQ-003`) or, when uncredited, to `CORE-SRC-003`. The finding names the claim whose source reference carries the misattributed excerpt and the sentence's own claim, never the claims of the sentence's other, correctly credited quotations |
| `CORE-CHR-001` | warning | a sentence orders two dated events but the pair could not be decided (see above: an aside date, an unstated year, an equal month or year, a coordinated cue whose subject carries no date, an event dated only in another sentence beside one the paragraph does not date, a demonstrative that refers to no identifiable dated event); the stated order was not checked |
| `CORE-QNT-001` | warning | a derived figure, trend or superlative the sentence states could not be checked (see the arithmetic section: incomparable units, no figures in its sentence and none in the paragraph's dated series, two series that could be meant, an ambiguous `that year`); one finding per sentence and reason, naming the phrases; the stated arithmetic was not checked |
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
  light`, `Read against`, `This is why`) is a `link`, and one that states a verdict (`The
  turning point was 1930.`, `1930 marked the turning point`, `the decisive year was`, `the
  most important cause was`, `mattered most`) a `judgement`, both material whatever they date
  or quote; a counter-case (`The strongest counter-case is that ...`, `however`, `against
  this`, `it could be argued`) is `counter_evidence` whether or not it is dated, unless it also
  weighs the case with a judgement cue (`by the criterion of ...`), and the dated sentence
  right after an undated counter-case statement is its `counter_evidence`. Only then does a
  dated item make a sentence `evidence`; a year that only names an event (`the 1923 crisis`,
  `the September 1930 election`) dates no statement. A quotation turns only analysis into
  evidence, never a link or a judgement. So hi-t8's `The turning point was 1930.` and hi-p3's
  `Against this background, the "smokeless air" ...` are material, and a synthesis that drops
  either without a record is `INT-LEDGER-002`.
* `HI-STR-003` (opens with evidence rather than a claim) is decided from the parsed role of the
  paragraph's first claim that is not a note: an evidence or counter-evidence opening is
  evidence; the point, which the parser takes by position, is a claim unless the parser's own
  predicate (`opens_with_fact`) reads it as a bare dated fact with no causal, evaluative or
  argument word (`The sonnet was printed in January 1818.`), and the finding then says so and
  names that claim. `The Treaty of Versailles was a major but partial cause of ...` is a claim.

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
  credited merely because it was supplied first. The rule is `adapters/sources.attribute_excerpt`,
  shared with the English parser (which adds one step: a sentence naming no text quotes the
  one literary text under analysis) and the generic parser.
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

## The hub and the Overseer (optional)

`RouterHub(observers=..., auditor=...)` attaches channel observers (`channel/README.md`, "Observers") to every channel
the hub opens. A hub built without them opens unobserved channels that behave exactly as before, and its Overseer
methods raise `AuditorNotAttached` (nothing is shown as passed without an auditor).

With `auditor=TransferAuditor(...)` (`overseer/README.md`) the auditor is attached FIRST to every channel, so its
journal is written before any other observer runs. The hub refuses an auditor that does not hold the hub's engine key
under the hub's key id (it could verify none of the hub's results). Then:

| Method | What it does |
| --- | --- |
| `clearance(task_key, message_id, receipt=None, wait_ms=0)` | The router's check immediately before acting on a transfer: custody of the message and of the transfers it depends on is re-checked against the journal, and the receipt the router presents (or the channel's own) is compared with the journaled receipt, field by field (a flipped status on the router's copy is `OVS-RCPT-001`). `wait_ms` is clamped to 250 ms. Act only when `overseer.policy.may_act(receipt, clearance)` (which also holds the clearance to the auditor's current word: its latest journaled clearance for the message, no later task audit failing it, custody re-checked at the decision); `policy.check_before_acting(hub, task_key, receipt)` does both, waits once on PENDING and holds a transfer still pending for the batch audit. |
| `audit(task_key, final=False, shadow=None)` | The signed task audit (`OverseerAudit`, scope `task`) of the channel. |
| `view(task_key)` | The authoritative view of the channel, parsed from its journal. |
| `close_task(task_key, audit=True)` | The channel leaves `channels` (under every key it was registered by) for `closed_channels`; its FINAL task audit is issued and returned, and its journal is sealed. A transfer made later on the kept channel object is reported (`OVS-CUST-003`). `policy.may_release` gates the synthesis on that FINAL audit. |
| `review(task_key, runners, mode="informed")` | Overseer agents review the task. Each runner is an `OverseerAgentRunner` built from a loaded knowledge pack. The hub takes a reference task audit (with the shadow channel run), issues each runner a dossier under its own pack (every dossier before any agent runs), runs each once, and passes every reply through the verdict intake, validation and combination. It returns a `HubReview` whose `audit` is the signed `verdicts`-scope audit, with the runs, assessments, combination and refusals. Agents never gate clearance: the verdicts audit copies the auditor's latest task audit's states, and a review changes no clearance unless the auditor itself finds a live object altered meanwhile. |
| `consolidate(task_key, request_message_ids=None, user_input_sha256=None)` | When several agents (duplicated instances of one specialist, or several specialists) answered one input: the ONE signed `consolidated_response/1.0` for the router (`overseer/consolidate.py`). Equivalent answers grouped deterministically, a representative per group (the earliest fully clean answer), every answer with an error-level finding or a repeated fault excluded with its codes and signed results, conflicts between groups disclosed (status CONFLICTING) rather than resolved. Recorded in `consolidations(task_key)`; deliver only through `consolidate.delivery_decision(resp, keyring, hub=hub)`, which re-checks at delivery that the response is the hub's latest for that input, its task audit the channel's latest, and the deliverable answer's custody intact. |
| `repeats(task_key)` | The task's repeat report (`overseer/repeats.py`) over every channel the hub opened for that task id: each error-level fault of each answer signed, every repeat `OVS-REP-001`, counted per agent. |
| `review_pool(task_keys, pool, mode=None)` | Self-duplicating review of a batch: the `OverseerPool` plans deterministically how many instances (one by default, more over the quota or on repeated faults, never past its maximum), each repeated-fault task goes to two independent instances, and each task is reviewed through `review(..., pool_plan=plan)` by exactly the instances its plan assigns; the plan is recorded in the signed verdicts audit. Informed dossiers show the channel's latest consolidated response per input. |
| `close()` / `with RouterHub(...)` | No new task or transfer afterwards; the auditor's replay worker (process mode) stops when the last hub using that auditor closes. Journals and audits stay readable. |

`task_key` is a key of `channels`, the `channel_uid` of a channel in `closed_channels`, or a channel this hub opened.
`open_task` never loses a channel: a channel it would replace (a task id opened again) moves to `closed_channels`
(keyed by `channel_uid`, at most 1024, oldest dropped first) where its journal continues, verifies and can still be
audited. It is not sealed, so a router that puts it back under its key by hand (the arena harness does) keeps using it.
