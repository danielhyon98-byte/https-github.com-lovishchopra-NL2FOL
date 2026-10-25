"""Security round 2, SEC-V2: the prose arithmetic reading (``quant._analyse``) reads a clause once for all the derived
figures, comparisons and figures it states (``quant._clause_index``).

For every derived figure ('rose by 10%', 'doubled', 'an average of 900,000 a year') the reading asked its clause the same
questions again (its figures up to the phrase, its worked equations, its decades, spans and years up to the phrase, the
subclause around the phrase, the pairs and phrases read so far), and answered each by reading the clause, or the clause up
to the phrase, again: quadratic in the phrases of one clause (2,000 'rose by 10%' in one sentence held a branch for
minutes). Each clause is now read once and kept; a question about the clause up to a place is answered from the whole
clause's reading, with only the last few runs of characters before the place read again; the spans read so far are kept in
indexes (a bisection per question). These tests pin the growth of the reading and that every reader answers as before, at
every place of every clause.
"""
from __future__ import annotations

import bisect
import random
import re
from fractions import Fraction

import pytest

from epinoic_logic.branches import quant
from epinoic_logic.stem.si_reading import SI_READING

from ..growth import growth


def _clear() -> None:
    for cached in (quant._analyse, quant._clause_index, quant._worked_equations_of, quant._content_words_of):
        cached.cache_clear()


#: The verification's shapes and this round's: one derived figure (or comparison, rate, decade, anaphor) repeated in one
#: clause, joined by spaces, commas or 'and'.
FAMILIES = [
    ("rose by 10%", " ", "general"), ("doubled", " ", "general"), ("a rise of 5 per cent", " and ", "general"),
    ("an increase of 1,200 tonnes", " ", "general"), ("an average of 900,000 a year", ", ", "general"), ("short of 5", " ", "general"),
    ("the 1840s added 4,500 miles", " ", "general"), ("that year it rose by 5%", ", ", "general"), ("tripled", " and ", "si"),
    ("1840sincrease of 5%", " ", "si"), ("not a rise of 12 per cent", " ", "si"), ("from 3.2e4 to 7.5e3", " ", "general"),
]


@pytest.mark.parametrize("unit,sep,reading", FAMILIES, ids=[f"{u}|{s!r}|{r}" for u, s, r in FAMILIES])
def test_many_derived_figures_in_one_clause_are_read_in_linear_time(unit, sep, reading):
    """Four times the clause costs about four times as much (before the round: up to about sixteen times)."""
    read = SI_READING if reading == "si" else quant.GENERAL

    def text(n: int) -> str:
        part = unit + sep
        return "The figures follow. " + (part * (n // len(part) + 1))[:n] + " The end."
    ratio, small, large = growth(lambda t: quant.undecided_quant_statements(t, reading=read), text(1000), text(4000), clear=_clear)
    assert ratio < 8.0, (unit, sep, reading, ratio, small, large)


# ---- the readers before the round, kept as data to pin that every answer is as before -------------------------------------

def _old_magnitudes(text: str) -> list:
    out = []
    for m in quant._LONE_FIG_RE.finditer(text):
        f = quant._fig_of(m, 1)
        if not f.num[:1].isdigit() or quant._is_pct(f.unit) or quant._year_like(f.num, f.unit or f.cur) or quant._MONTH_NOUN_RE.match(f.noun):
            continue
        if re.match(r"\s*(?:s\b|-|–|st\b|nd\b|rd\b|th\b)", text[m.end("n1"):]) and quant._year_like(f.num, None):
            continue
        out.append(f)
    return out


def _old_amounts(clause: str, end: int, spans: list) -> list:
    """``_amounts`` before the round (``spans``: the clause's derived phrases, which it read on every call)."""
    return [f for f in _old_magnitudes(clause[:end]) if not any(a <= f.start < b for a, b in spans) and not quant._RATE_PHRASE_RE.search(clause[f.start: f.end])]


def _old_lone(clause: str, end: int) -> list:
    """The figures a comparison is read from, before the round (``_comparison_spec``)."""
    head = clause[:end]
    return [quant._fig_of(m, 1) for m in quant._LONE_FIG_RE.finditer(head) if m.group("n1")[:1].isdigit() and not quant._year_like(m.group("n1"), m.group("u1"))]


def _old_own_subclause(clause: str, start: int, end: int) -> str:
    a = max(clause.rfind(c, 0, max(start, 0)) for c in ",;:") + 1
    ends = [k for k in (clause.find(c, end) for c in ",;:") if k >= 0]
    return clause[a:min(ends) if ends else len(clause)]


def _old_decade_before(clause: str, at: int):
    decades = list(quant._DECADE_TOKEN_RE.finditer(clause, 0, at))
    if not decades:
        return None
    d = decades[-1]
    d0 = int(d.group("d"))
    between = clause[d.end(): at]
    if quant._YEAR_SPAN_RE.search(between):
        return None
    if any(not (d0 <= int(y) < d0 + 10) for y in quant._YEAR_TOKEN_RE.findall(between)):
        return None
    return d


def _old_earlier_year(sentences: list, index: int, clause: str, phrase_start: int):
    years = sorted({int(y) for y in quant._YEAR_TOKEN_RE.findall(clause[:phrase_start])})
    if len(years) == 1:
        return years[0], ""
    if years:
        return None, f"'that year' could refer to {len(years)} years stated before it in its sentence"
    for j in range(index - 1, -1, -1):
        years = sorted({int(y) for y in quant._YEAR_TOKEN_RE.findall(sentences[j])})
        if len(years) == 1:
            return years[0], ""
        if years:
            return None, f"'that year' could refer to {len(years)} years ({', '.join(map(str, years[:6]))}) stated in the sentence before it"
    return None, "'that year' refers to no year stated earlier in the paragraph"


def _old_target_years(sentences: list, index: int, clause: str, at: int, series_years: list):
    decade = _old_decade_before(clause, at)
    if decade is not None:
        d0 = int(decade.group("d"))
        return (d0, d0 + 10), f"'{decade.group(0).strip()}' read as {d0} to {d0 + 10}"
    span = quant._YEAR_SPAN_RE.search(clause)
    if span:
        return (int(span.group(1)), int(span.group(2))), f"the years {span.group(1)} and {span.group(2)} stated in the sentence"
    own = _old_own_subclause(clause, at, at) if 0 <= at <= len(clause) else clause
    lead = clause[:max(at, 0)] + " " + own
    period = quant._PERIOD_ANAPHOR_RE.search(lead)
    if period and len(series_years) >= 2 and not quant._YEAR_TOKEN_RE.search(lead):
        first, last = min(series_years), max(series_years)
        length = quant._number_of_years(period.group("n"), period.group("unit"))
        if length is not None and length != last - first:
            return None, f"'{period.group(0)}' names {length} years, but the paragraph's dated figures run from {first} to {last}"
        return (first, last), f"'{period.group(0)}' read as the paragraph's dated span, {first} to {last}"
    anaphor = quant._THAT_YEAR_RE.search(clause)
    if anaphor:
        year, why = _old_earlier_year(sentences, index, clause, anaphor.start())
        if year is None:
            return None, why
        how = f"'{anaphor.group(0)}' read as {year}, the one year stated before it"
    else:
        stated = sorted({int(y) for y in quant._YEAR_TOKEN_RE.findall(lead)})
        if len(stated) != 1:
            return None, ("the sentence states no year and no anaphor such as 'that year'" if not stated else f"the sentence states {len(stated)} years and no span between them")
        year, how = stated[0], f"the year {stated[0]} stated in the sentence"
    earlier = [y for y in series_years if y < year]
    if not earlier:
        return None, f"the paragraph's dated figures state no year before {year}"
    return (max(earlier), year), how + f", against the previous dated figure ({max(earlier)})"


def _old_no_pair_reason(clause: str, d) -> str:
    span = (d.start, d.end) if d is not None else (-1, -1)
    figs = [f for f in quant._stated_figures(clause) if not (span[0] <= f.start < span[1])]
    if not figs:
        return "no figures are stated with it in its sentence"
    working = quant._read_worked_equations(clause)
    if working:
        return (f"its sentence states its figures only as written arithmetic ('{working[0].phrase[:100]}'), which this reader does not decide, "
                f"and no pair of figures in words it can be read against")
    shown = [quant._shown(f, f.unit).replace(" %", "%") for f in figs[:3]]
    return f"its sentence states no pair of figures it can be read against (only {', '.join(shown)})"


def _old_unread_figure_between(clause: str, start: int, end: int, pat, cont, spans: list) -> bool:
    """``_unread_figure_between`` before the round (``spans``: the clause's derived phrases, read once per call)."""
    if not quant._DIGIT_RUN_RE.search(clause, start, end):
        return False
    kind = (quant._level_unit(cont.unit), cont.cur)
    for f in pat.figure.finditer(clause, start, end):
        num = f.group("n9") or ""
        if not quant._DIGIT_RUN_RE.search(num) or quant._YEAR_RUN_RE.fullmatch(num) or (quant._level_unit(f.group("u9")), quant._cur_key(f.group("c9") or "")) != kind:
            continue
        if any(a <= f.start("n9") < b for a, b in spans):
            continue
        return True
    return False


def _old_total_rate_spec(clause: str, d, tolerance: Fraction):
    q = quant
    if d.kind != "rate_change" or d.per not in ("year", "annum"):
        return None, ""
    head = clause[: d.start]
    if len(_old_magnitudes(head)) != 1:
        return None, ""
    figs = _old_amounts(clause, d.start, [(x.start, x.end) for x in q._derived_phrases(clause)])
    if len(figs) != 1:
        return None, ""
    total = figs[0]
    decades = list(q._DECADE_TOKEN_RE.finditer(head))
    span = q._YEAR_SPAN_RE.search(head)
    years = {int(y) for y in q._YEAR_TOKEN_RE.findall(head)}
    if len(decades) == 1 and span is None and all(int(decades[0].group("d")) <= y < int(decades[0].group("d")) + 10 for y in years):
        counts, over = (10,), f"'{decades[0].group(0).strip()}' (ten years)"
    elif span is not None and not decades and int(span.group(2)) > int(span.group(1)):
        y1, y2 = int(span.group(1)), int(span.group(2))
        counts, over = (y2 - y1, y2 - y1 + 1), f"{y1} to {y2} ({y2 - y1} or {y2 - y1 + 1} years, counted either way)"
    else:
        return None, ""
    shown = q._shown(total, total.unit)
    if (d.cur or total.cur or q._cur_of_noun(total.noun) or q._cur_of_noun(d.noun)) and not q._cur_compatible(total.cur, total.noun, d.cur, d.noun):
        return None, f"the currency of '{d.words}' and of the total it averages ({shown}) differ"
    if {q._unit_kind(d.unit), q._unit_kind(total.unit)} - {None, "scale", "count"}:
        return None, f"the unit of '{d.words}' and of the total it averages ({shown}) cannot be compared"
    if d.noun and total.noun and not ({w.rstrip("s") for w in d.noun.lower().split()} & {w.rstrip("s") for w in total.noun.lower().split()}):
        return None, f"'{d.words}' counts {d.noun.split()[-1]} while the total it averages ({shown}) counts {total.noun}"
    premises = (("TOTAL", {"op": "eq", "left": q._v("total"), "right": q._real(q._frac(total.num, total.unit))}, f"total = {shown}"),)
    rates = [q._within({"op": "div", "left": q._v("total"), "right": q._real(Fraction(n))}, d.stated, tolerance, Fraction(0), d.side) for n in counts]
    concl = rates[0] if len(rates) == 1 else {"op": "or", "args": rates}
    label = f"stated average of {q._fmt(d.stated)} a year against the total {shown} over {over}"
    spec = q._Spec("rate_change", clause.strip(), (("total", "the total as stated"),), premises, ("STATED_RATE", concl, label), Fraction(0), d.side,
                   "figure stated in the report itself", f"a yearly average of the total its clause dates by {over}", d.words)
    return (q._negated_spec(spec, tolerance) if d.negated else spec), ""


# ---- clauses ---------------------------------------------------------------------------------------------------------------

CLAUSES = [
    "About 5.2 million people entered the United States in the 1880s, an average of about 900,000 a year.",
    "The 1840s, which included the Railway Mania of 1845 to 1847, added roughly 4,500 miles of track.",
    "Output rose from 1.9 million in 1929 to 3.1 million in 1930, a rise of 63 per cent, before climbing to 5.6 million in 1932.",
    "In 1990 it was 5 and in 2000 it was 7; that year it rose by 40%.",
    "Pig iron output fell short of the target of about 10 million tonnes of pig iron.",
    "Of the $13 billion, the United Kingdom received about $3.2 billion and France about $2.7 billion.",
    "Prices rose by 12 per cent over the twenty years from 1990 to 2010.",
    "The percentage change is (54 − 48) ÷ 48 × 100 = 12.5%, so the price rose by 12.5%.",
    "Unemployment fell from 3.1 million to 2.4 million, a fall of 700,000 people, in 1924.",
    "That is a fall of 157 mm, about 19% of the 1990 total.",
    "Rainfall rose from 610 mm in 2019 to 640, 655, 690 and 720 mm in 2023, peaking at 11.4% in 2020, before falling to 8.1%.",
    "The 1880s saw 500,000 a year in the 1880s, an average of 450,000 a year from 1881 to 1890.",
    "Between 1990 and 2000 exports doubled, and in the 1990s imports added 3,000 tonnes.",
    "It reached 6.2 million tonnes in 1932, short of the 7 million tonnes planned, and exceeded 5 tonnes by 1934.",
    "the 1840s 1845 1850s 1855 from 1850 to 1860 that year 1870s increase of 5%",
    "1840sincrease of 5% and the 1850s1860s a rise of 3 per cent in 1859-60, then 1861",
    "5 in 1990 and 6 in 2000, a change of 0 per cent; x = 3 + 4 = 7; it doubled over the period",
    "Herman increase of 5% 1990s, 2001 and 1999: an average of about 5 a year in the 1880s",
]


def _random_clauses(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    derived = ["rose by 10%", "fell by 5%", "a rise of 5 per cent", "an increase of 2 points", "doubled", "halved twice", "tripled",
               "an average of 900,000 a year", "an average of about 5 a year", "an increase of 1,200 tonnes", "added 3,000 men", "lost 22,000 men",
               "a fall of a third", "a 12 per cent rise", "not a rise of 12 per cent", "did not double", "averaging 40 a year"]
    pairs = ["rose from 10 to 20", "from 1.9 million in 1929 to 3.1 million in 1930", "5 in 1990 and 6 in 2000", "before falling to 5",
             "then rose to 8.1%", "rising from 5 to 9", "from 3.2e4 to 7.5e3", "peaking at 11.4% in 2020", "from 45.2 per cent to 33.1"]
    other = ["short of 5", "exceeded 6 tonnes", "the greatest rise", "rose every year", "of which 5", "a total of 9 billion dollars",
             "about two-thirds of the total", "x = 3 + 4 = 7", "(12 − 8) ÷ 8 × 100 = 50%", "These figures", "that year", "the same year",
             "the 1840s", "the 1880s", "1840s", "from 1990 to 2000", "between 1990 and 2000", "over the period", "over the twenty years",
             "In 1990", "2019: 610", "by 1870", "about 13,000 miles by 1870", "45.2 per cent", "5 seats", "$5", "1 000", "twenty five",
             "c. 1700", "in early 1932", "on 18 June 1815", "1923-24", "1990,", "5,", "per cent", "%", "1850s1860s", "18th", "1990s,"]
    glue = ["the", "and", "of", "it", "prices", "exports", "output", "in", "by", "which", "so", "but", "then", "a", "that", "was", "France", "year"]
    seps = [" ", " ", " ", ", ", "; ", ": ", "  ", " , ", " (", ") ", " — ", "", "-"]
    out = []
    for _ in range(n):
        toks = []
        for _ in range(rnd.randint(1, 30)):
            x = rnd.random()
            toks.append(rnd.choice(derived if x < 0.3 else pairs if x < 0.45 else other if x < 0.75 else glue))
            toks.append(rnd.choice(seps))
        out.append("".join(toks))
    return out


def _figs(seq) -> list:
    return [(f.num, f.unit, f.noun, f.date, f.start, f.end, f.cur) for f in seq]


def _sig(m):
    return None if m is None else (m.span(), m.group(0))


CONTS = [quant._Fig("5", "%", "", "", 0, 1, ""), quant._Fig("5", "per cent", "", "", 0, 1, ""), quant._Fig("5", None, "", "", 0, 1, ""),
         quant._Fig("5", "million", "", "", 0, 1, ""), quant._Fig("5", None, "", "", 0, 1, "$"), quant._Fig("5", "mm", "", "", 0, 1, "")]


def test_the_clause_readers_answer_as_before_at_every_place():
    """At every place of every clause (every run of characters, and places in between), the readers of the clause up to a
    place give what the readers before the round gave: the figures, amounts and comparison figures before it, the decade
    that governs it, the years a derived figure with no pair speaks of, the year 'that year' refers to, the subclause
    around it and whether an unread figure stands before it; and for every derived figure, why it has no pair and the
    check of a yearly average against its total."""
    rnd = random.Random(8)
    sentences_sets = [["In 1990 it was 5.", "x"], ["Prices were 4 in 1990 and 5 in 1991.", "In 2001 and 2002 it was flat.", "x"], []]
    compared = 0
    for clause in CLAUSES + _random_clauses(100, seed=13):
        _clear()
        spans = [(d.start, d.end) for d in quant._derived_phrases(clause)]
        n = len(clause)
        starts = [m.start() for m in re.finditer(r"\S+", clause)]
        places = sorted({0, n, *rnd.sample(starts, min(len(starts), 24)), *(rnd.randint(0, n) for _ in range(4))})
        memos: list = [{}, {}, {}]
        for at in places:
            assert _figs(quant._figure_run(clause, at, "magnitude")) == _figs(_old_magnitudes(clause[:at])), (clause, at)
            assert _figs(quant._amounts(clause, at)) == _figs(_old_amounts(clause, at, spans)), (clause, at)
            assert _figs(quant._figure_run(clause, at, "lone")) == _figs(_old_lone(clause, at)), (clause, at)
            assert _sig(quant._decade_before(clause, at)) == _sig(_old_decade_before(clause, at)), (clause, at)
            for start in (at, max(0, at - 7)):
                assert quant._own_subclause(clause, start, at) == _old_own_subclause(clause, start, at), (clause, start, at)
            for k, extra in enumerate(sentences_sets):
                sentences = [*extra, clause]
                index = len(extra)
                memo = memos[k]   # one per paragraph, kept between its questions as the reading keeps it
                assert quant._earlier_year(sentences, index, clause, at, memo) == _old_earlier_year(sentences, index, clause, at), (clause, at)
                for series_years in ([], [1990, 2000], [1840, 1850, 1860, 1870]):
                    got = quant._target_years(sentences, index, clause, at, series_years, memo if k else None)
                    assert got == _old_target_years(sentences, index, clause, at, series_years), (clause, at, series_years)
            pat = (quant._GENERAL_PATTERNS, quant._si_patterns())[at % 2]
            for start in (0, max(0, at - 30)):
                for cont in CONTS[at % 2::2]:
                    got = quant._unread_figure_between(clause, start, at, pat, cont)
                    assert got == _old_unread_figure_between(clause, start, at, pat, cont, spans), (clause, start, at, cont)
            compared += 1
        for d in [None, *quant._derived_phrases(clause), *quant._derived_phrases(clause, True)]:
            assert quant._no_pair_reason(clause, d) == _old_no_pair_reason(clause, d), (clause, d)
            if d is not None:
                assert repr(quant._total_rate_spec(clause, d, Fraction(1, 20))) == repr(_old_total_rate_spec(clause, d, Fraction(1, 20))), (clause, d)
    assert compared > 2000


def test_the_span_indexes_answer_as_a_scan_of_every_span():
    rnd = random.Random(2)
    for _ in range(400):
        n = rnd.randint(0, 60)
        spans = [(a, a + rnd.randint(0, 12)) for a in (rnd.randint(0, n) for _ in range(rnd.randint(0, 12)))]
        stab = quant._Stab(spans)
        grow = quant._GrowingSpans(n + 12)
        seen: list = []
        for a, b in spans:
            for x in range(0, n + 14):   # the places of a text
                assert stab.covers(x) == any(p <= x < q for p, q in spans)
                assert grow.furthest(x) == max((q for p, q in seen if p <= x), default=-1)
                for e in (x, x + 3):
                    assert stab.meets(x, e) == any(p < e and x < q for p, q in spans)
                    assert grow.meets(x, e) == any(p < e and x < q for p, q in seen)
            grow.add(a, b)
            seen.append((a, b))
        pairs = [quant._Pair(a, b, CONTS[0], CONTS[0]) for a, b in spans]
        last = quant._LastBefore(pairs)
        for x in range(0, n + 14):
            prior = [p for p in pairs if p.end <= x]
            assert last.last(x) is (prior[-1] if prior else None)


def test_the_prefix_scan_lists_the_matches_of_the_cut_text():
    """``_PrefixScan.upto(end)`` holds the matches of the scan of the clause cut at ``end``, for the figure patterns it is
    used with, at every end of every clause."""
    for clause in CLAUSES + _random_clauses(60, seed=17) + ["1 " * 300 + "x", "twenty " * 120 + "five", "a " * 200 + "5 per cent"]:
        _clear()
        index = quant._clause_index(clause)
        n = len(clause)
        for pattern in (quant._LONE_FIG_RE, quant._GENERAL_PATTERNS.figure, quant._si_patterns().figure):
            for pos in (0, n // 3):
                scan = index.scan(pattern, pos)
                for end in (range(pos, n + 1) if n <= 160 else sorted({*range(pos, n + 1, 7), *range(max(pos, n - 40), n + 1)})):
                    k, tail = scan.upto(end)
                    want = [(m.span(), m.groups()) for m in pattern.finditer(clause, pos, end)]
                    assert [(m.span(), m.groups()) for m in [*scan.full[:k], *tail]] == want, (clause, pos, end)


def test_derived_figures_are_still_read_and_checked():
    """Clean controls of the readers the round changed: a yearly average against its decade's total, a derived figure
    through a decade, a continuation after a derived figure, an anaphor, and a derived figure with no pair, named."""
    kinds = lambda text: sorted(c.kind for c in quant.extract_quant_checks(text, request_id="r", claim_id="c"))
    assert kinds("About 5.2 million people entered the United States in the 1880s, an average of about 900,000 a year.") == ["rate_change"]
    assert "percent_change" in kinds("Output rose from 1.9 million in 1929 to 3.1 million in 1930, a rise of 63 per cent, before climbing to 5.6 million in 1932.")
    text = "Exports were 40 in 1990 and 44 in 1991. That year they rose by 10%."
    assert kinds(text) == ["percent_change"]
    [u] = quant.undecided_quant_statements("Exports rose by 10% over the period.")
    assert u.phrase == "rose by 10%" and "no figures" in u.reason
    assert bisect.bisect_left([1, 2, 3], 2) == 1   # the module's bisection is the standard library's
