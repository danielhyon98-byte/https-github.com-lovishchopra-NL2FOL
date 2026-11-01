"""Integration gate 3: the claim ledger's findings (integrity/ledger.py).

* blocker, critical (input stall): ``check_synthesis_ledger`` read ``incidental_figures(c.claim_text)`` again for every
  figure of every cited source claim, and ``incidental_figures`` tested every figure against every incidental span, so a
  cited claim of formula constants ("× 10" repeated) cost about n³: 34 s for one 3,900-character claim, multiplied by every
  synthesized claim citing it. A claim's figures and incidental figures are now read once per check, and a figure's place
  is found by bisection over the spans' starts.
* the class sweep (same kinds of pattern, ledger): the mark-annotation alternative of ``_INCIDENTAL_FIGURE_RE`` split a
  blank run between two runs ("[1" before a long blank run); ``_figures`` rebuilt the text once per figure it blanked;
  ``_word_figures`` tested every small number word against every span taken before it; ``_COMPARISON_RE`` and
  ``_RATHER_THAN_RE`` split a blank run after "more", "less" or "rather" every way (10 s per call on one 3,900-character
  source claim, read again for every synthesized claim citing it) and read the rest of a long word from every letter.
  Each is linear now and reads exactly what it read before (the old forms are kept below as the specification).
* majors (combinator faults): invented content (a new person, place or body; small counts and relative dates in words; a
  changed multiplier verb), dropped or strengthened qualifiers (an approximation in front of a word, "tended to",
  "reportedly", "every few days", a part quantifier widened), a credit by a reporting verb after a name ("Kapp admitted
  that", "Stresemann himself said"), and the false finding on "largely" restated as "to a large extent".
"""
from __future__ import annotations

import random
import re
import time

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity import ledger as L
from epinoic_logic.integrity.ledger import check_synthesis_ledger
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from ..timing import empty_caches


def codes(findings) -> list[str]:
    return sorted({f.code for f in findings})


def _report(rid: str, agent: str, subject: str, claims: list[tuple[str, str]], docs=()) -> SpecialistReport:
    text = " ".join(t for _c, t in claims)
    base = dict(request_id="req", task_id="task", report_id=rid, agent_id=agent, subject=subject, task_type="short_answer")
    return SpecialistReport(**base, original_response=text, response_sha256=sha256_text(text), created_at="2026-11-01T00:00:00Z", supplied_texts=list(docs),
                            claims=[ClaimRecord(**base, claim_id=c, claim_text=t, claim_role="evidence", materiality="material") for c, t in claims])


def _synthesis(reports: list[SpecialistReport], claims: list[tuple[str, str, list[str], str]]) -> Synthesis:
    sc = [SynthesizedClaim(claim_id=c, text=t, source_claim_ids=s, transformation=tr) for c, t, s, tr in claims]
    text = " ".join(c.text for c in sc)
    return Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator",
                     source_report_ids=[r.report_id for r in reports], claims=sc, text=text, text_sha256=sha256_hex(text),
                     created_at="2026-11-01T01:00:00Z")


def _cpu(call) -> tuple[float, object]:
    empty_caches()
    c0 = time.process_time()
    out = call()
    return time.process_time() - c0, out


_SOURCE = "In 1990 the total was 5 people."


# ============================================================================================ blocker: the finding's input
def _constants_case(chars: int, citing: int):
    claim = ("× 10" * (chars // 4 + 1))[:chars]
    rep = _report("rep-h", "history-specialist", "History", [("h1.1", claim)])
    return rep, _synthesis([rep], [(f"s{i}", _SOURCE, ["h1.1"], "paraphrased") for i in range(citing)])


def test_a_cited_claim_of_formula_constants_is_read_in_linear_time():
    """The finding's input: a History report whose one claim is "× 10" repeated to 3,900 characters (under the 4,000 claim
    cap), cited by paraphrased synthesized claims. 34.3 s for one citation before the fix (eight citations exceeded the
    four-minute turn budget); the ledger result is unchanged (INT-LEDGER-023 only)."""
    rep, syn = _constants_case(3_900, 8)
    spent, findings = _cpu(lambda: check_synthesis_ledger([rep], syn))
    assert spent < 12.0, spent  # linear: about 2 s on the gate machine
    assert codes(findings) == ["INT-LEDGER-023"]
    small, _f = _cpu(lambda: check_synthesis_ledger(*(lambda r, s: ([r], s))(*_constants_case(975, 8))))
    assert spent < 6 * small + 1.0  # four times the text, never sixteen or sixty-four times the work


def _old_incidental_figures(text: str) -> set[str]:
    """``incidental_figures`` before integration gate 3 (the specification): every figure tested against every span."""
    old_re = re.compile(
        r"(?:[×÷*/x]\s*(?P<k>10{1,3})(?![\d.,]))"
        r"|(?:\b(?:paragraphs?|paras?|parts?|lines?|stanzas?|sections?|tables?|figures?|figs?\.?|diagrams?|questions?|papers?|items?|pages?|pp?\.|steps?|criteri(?:on|a)|units?|topics?)\s+(?P<r>\d{1,3})(?![\d.,]\d))"
        r"|(?:\[\s*(?P<m>\d{1,2})\s*(?:marks?|spare)?\s*\])", re.IGNORECASE)
    plain = L._ungroup(text)
    out: set[str] = set()
    spans: list[tuple[int, int]] = []
    for m in old_re.finditer(plain):
        g = m.group("k") or m.group("r") or m.group("m")
        if g:
            out.add(g)
            key = "k" if m.group("k") else "r" if m.group("r") else "m"
            spans.append(m.span(key))
    if not out:
        return out
    for m in L._FIGURE_RE.finditer(plain):
        if m.group(0) in out and not any(a <= m.start() < b for a, b in spans):
            out.discard(m.group(0))
    return out


_PIECES = [" ", "  ", "\t", "\n", "x", "×", "÷", "/", "*", "10", "100", "1000", "5", "17", "1990", "[", "]", "[1]", "[2 marks]", "[1", "marks", "spare",
           "paragraph", "line", "Table", "part", "question", "3", ".", ",", "1,500", "3 000", "2.5", "10³", "10^6", "2e5", "one", "two", "twelve", "under",
           "nine", "ten", "hours", "a", "half", "million", "per cent", "more", "less", "rather", "than", "cats", "dogs", "ab", "so", "but", "-", "–",
           "don't", "well-known", "(", ")", "the", "of", "in", "May", "1923", "1840s", "about", "roughly", "three-quarters"]


def _texts(seed: int, n: int):
    rng = random.Random(seed)
    for _ in range(n):
        sep = rng.choice(["", " ", " ", "  "])
        yield sep.join(rng.choice(_PIECES) for _ in range(rng.randint(1, 24)))


def test_incidental_figures_read_exactly_what_the_old_reading_read_in_linear_time():
    for t in _texts(301, 6_000):
        assert L.incidental_figures(t) == _old_incidental_figures(t), repr(t)
    for hostile in ("× 10" * 100_000, "[1" + " " * 400_000 + "x", "paragraph 1 " * 30_000):
        spent, _out = _cpu(lambda: L.incidental_figures(hostile))
        assert spent < 4.0, (hostile[:12], spent)  # "[1" + 8,000 blanks took 0.12 s and grew with the square


def _old_figures(text: str):
    """``_figures`` before integration gate 3 (the specification): the text rebuilt once per figure it blanked."""
    text = text or ""
    if not text.isascii():
        text = L._MINUS_GLYPH_RE.sub("-", text)
    if "\\" in text:
        text = L._LATEX_ELLIPSIS_RE.sub("…", text)
    plain = L._ungroup(L._strip_list_markers(text))
    out = []
    masked = plain
    if "10" in plain or "e" in plain or "E" in plain:
        for start, end, exact, spellings, surface in L._scientific_figures(plain):
            if exact is not None:
                out.append((exact, None, surface, tuple(sorted(spellings))))
            masked = masked[:start] + " " * (end - start) + masked[end:]
    if "^" in masked or "**" in masked or not masked.isascii():
        for start, end, mantissa, spellings, surface in L._power_figures(masked):
            out.append((mantissa, None, surface, tuple(sorted(spellings))))
            masked = masked[:start] + " " * (end - start) + masked[end:]
    for start, end, mantissa, scale, surface in _old_word_figures(masked):
        out.append((mantissa, scale, " ".join(surface.split()), ()))
        masked = masked[:start] + " " * (end - start) + masked[end:]
    return out, masked


def _old_word_figures(text: str, *, pairing: bool = False):
    """``_word_figures`` before integration gate 3 (the specification): every small number word against every span taken."""
    taken: list[tuple[int, int]] = []
    for m in L._WORD_FIGURE_RE.finditer(text):
        taken.append((m.start(), m.end()))
    extra = []
    for rx, group in ((L._SMALL_AFTER_RE, "anum"),) + (((L._SMALL_BEFORE_NOUN_RE, "bnum"),) if pairing else ()):
        for m in rx.finditer(text):
            a, b = m.start(group), m.end(group)
            if any(x < b and a < y for x, y in taken):
                continue
            taken.append((a, b))
            extra.append((a, b, str(L._SMALL_VALUES[m.group(group)]), None, m.group(group)))
    new = [w for w in L._word_figures(text, pairing=pairing) if w not in extra]  # the main reader is unchanged
    return sorted(new + extra)


def test_the_figure_reader_blanks_once_per_stage_and_reads_what_it_read_before():
    for t in _texts(302, 6_000):
        old, _masked = _old_figures(t)
        new = [(f.mantissa, f.scale, f.label, tuple(sorted(f.keys - {f.mantissa} - ({f"{f.mantissa} {f.scale}"} if f.scale else set())))) for f in L._figures(t)]
        assert [x[:3] for x in old] == [x[:3] for x in new[:len(old)]], repr(t)
        assert L._word_figures(t) == _old_word_figures(t) and L._word_figures(t, pairing=True) == _old_word_figures(t, pairing=True), repr(t)
    for unit in ("2 × 10³ ", "10^3 ", "twelve ", "twelve under nine ", "twelve ten hours "):
        hostile = unit * (400_000 // len(unit))
        spent, _out = _cpu(lambda: (L._figures(hostile), L._word_figures(hostile, pairing=True)))
        assert spent < 12.0, (unit, spent)  # 3.1-3.5 s at 400,000 and growing with the square; 'twelve under nine' about 35 s


#: The comparison patterns before integration gate 3 (the specification).
_OLD_COMPARISON_RE = re.compile(r"\b(?P<cmp>more|less|rather)\s+(?P<x>[^,;:.!?()]{3,80}?)\s+than\s+(?P<y>[^,;:.!?()]{3,80}?)(?=\s*(?:[,;:.!?()]|$|\b(?:but|so|while|whereas|because|when|which)\b))", re.IGNORECASE)
_OLD_RATHER_THAN_RE = re.compile(r"(?P<x>(?:[^\W\d_]+(?:['’-][^\W\d_]+)*\s+){1,6}?)rather\s+than\s+(?P<y>[^,;:.!?()]{3,80}?)(?=\s*(?:[,;:.!?()]|$|\b(?:but|so|while|whereas|because|when|which)\b))", re.IGNORECASE)


def _old_comparisons(text: str):
    out = []
    for m in _OLD_COMPARISON_RE.finditer(text):
        if m.group("cmp").casefold() == "rather":
            continue
        x, y = L._content_keys(m.group("x")), L._content_keys(m.group("y"))
        if x and y:
            out.append((m.group("cmp").casefold(), x, y, " ".join(m.group(0).split())))
    for m in _OLD_RATHER_THAN_RE.finditer(text):
        x, y = L._content_keys(m.group("x")), L._content_keys(m.group("y"))
        if x and y:
            out.append(("rather", x, y, " ".join(m.group(0).split())))
    return out


def test_the_comparison_readers_read_what_they_read_before_in_linear_time():
    for t in _texts(303, 8_000):
        assert L._comparisons(t) == _old_comparisons(t), repr(t)
    assert L._RATHER_THAN_RE.search("the war rather than the treaty, as the specialist says").group("x") == "the war "
    for hostile in ("more" + " " * 3_900 + "x", "rather" + " " * 3_900 + "x", "a" * 3_900 + " rather than b"):
        spent, _out = _cpu(lambda: (L.reversed_comparisons(_SOURCE, [hostile]), L.meaning_differences(_SOURCE, [hostile], "paraphrased")))
        assert spent < 2.0, (hostile[:8], spent)  # 10 s per call at 3,900 before the fix
    claim = "Inflation hurt savers more" + " " * 3_874
    rep = _report("rep-h", "history-specialist", "History", [("h1.1", claim)])
    spent, findings = _cpu(lambda: check_synthesis_ledger([rep], _synthesis([rep], [(f"s{i}", _SOURCE, ["h1.1"], "paraphrased") for i in range(8)])))
    assert spent < 12.0, spent  # every citing claim read the source's comparisons again: minutes before the fix
    assert "INT-INTERNAL-001" not in codes(findings)


# ============================================================================================ majors: invented content
_DAWES = "The Dawes Plan of 1924 largely stabilised the currency."
_KAPP = "Only a minority of Germans supported the Kapp Putsch in 1920."
_PRICES = "Prices roughly doubled every few days in late 1923."
_STRESEMANN = "Stresemann probably saved the republic from collapse in 1923."
_UNEMPLOYMENT = "Unemployment reached about 6 million in 1932."


def _one(source: str, synthesized: str, transformation: str = "paraphrased", *, docs=(), extra=()):
    rep = _report("rep-e", "economics-specialist", "Economics", [("e1", source)], docs=docs)
    return check_synthesis_ledger([rep], _synthesis([rep], [("s0", synthesized, ["e1"], transformation)]), extra_texts=extra)


def _named(findings, code: str) -> list[str]:
    return [f.message for f in findings if f.code == code]


@pytest.mark.parametrize("source,synthesized,name", [
    (_DAWES, "The Dawes Plan of 1924, negotiated by Hjalmar Schacht, largely stabilised the currency.", "Hjalmar Schacht"),
    (_KAPP, "Only a minority of Germans supported the Kapp Putsch in Munich in 1920.", "Munich"),
    (_DAWES, "The Dawes Plan of 1924, backed by the League of Nations, largely stabilised the currency.", "League"),
])
def test_a_person_place_or_body_no_text_of_the_exchange_names_is_an_introduced_name(source, synthesized, name):
    found = _named(_one(source, synthesized), "INT-LEDGER-032")
    assert found and f"'{name}" in found[0] and "an introduced name" in found[0] and "name-introduction" in found[0], found


@pytest.mark.parametrize("source,synthesized,kw", [
    (_DAWES, "The Dawes Plan of 1924 largely stabilised the currency.", {}),  # carried
    (_KAPP, "In 1920, only a minority of Germans supported the Kapp Putsch.", {}),  # reordered
    (_DAWES, "The Dawes Plan of 1924 largely stabilised the currency in Berlin.", {"extra": ("Explain the recovery of Berlin's finances.",)}),  # the request names it
    (_DAWES, "The Dawes Plan of 1924 largely stabilised the German currency.", {}),  # an adjective of nationality is no actor
    (_DAWES, "The Dawes Plan of 1924 largely stabilised the currency, as Keynes argued.",
     {"docs": (SuppliedText(document_id="d", title="Keynes on reparations", text="Keynes argued that reparations were too high."),)}),  # a supplied text names it
    (_DAWES, "According to the Economics specialist, the Dawes Plan of 1924 largely stabilised the currency.", {}),  # a credit to its specialist
    (_DAWES, "In September 1924 the Dawes Plan largely stabilised the currency.", {}),  # a month is no name
    (_DAWES, "Source A shows that the Dawes Plan of 1924 largely stabilised the currency.", {}),  # a part of the task is no actor
    (_DAWES, "The Dawes Plan of 1924 largely stabilised the UK currency.", {}),  # a short acronym is no introduced name
])
def test_names_the_exchange_states_months_and_specialist_credits_are_no_introduced_names(source, synthesized, kw):
    found = [m for m in _named(_one(source, synthesized, **kw), "INT-LEDGER-032") if "introduced name" in m]
    assert not found, found


@pytest.mark.parametrize("source,synthesized,figure", [
    (_KAPP, "Only a minority of Germans supported the Kapp Putsch, which lasted four days, in 1920.", "four"),
    (_KAPP, "Only a minority of Germans, three in ten, supported the Kapp Putsch in 1920.", "three"),
    (_KAPP, "Only a minority of Germans supported the Kapp Putsch, in which dozens died, in 1920.", "dozens"),
    (_DAWES, "The Dawes Plan of 1924, signed two years later, largely stabilised the currency.", "two years later"),
    (_UNEMPLOYMENT, "Unemployment reached about 6 million in 1932, a decade later.", "a decade later"),
])
def test_a_count_or_relative_date_written_in_words_and_stated_by_no_source_is_an_introduced_figure(source, synthesized, figure):
    found = _named(_one(source, synthesized), "INT-LEDGER-023")
    assert found and f"'{figure}'" in found[0] and "occur in none of its cited sources" in found[0], found


@pytest.mark.parametrize("source,synthesized", [
    ("The putsch lasted four days in March 1920.", "In March 1920 the putsch lasted four days."),  # the source states the count
    ("Two years later, in 1926, Germany joined the League.", "Germany joined the League in 1926, two years later."),
    ("The two poems differ in tone and form.", "The two poems differ in form and in tone."),  # a determiner: no count
    (_KAPP, "The two specialists agree that only a minority of Germans supported the Kapp Putsch in 1920."),
    (_KAPP, "Two reasons explain why only a minority of Germans supported the Kapp Putsch in 1920."),  # a count of reasons is no figure
])
def test_counts_the_sources_state_and_prose_numbers_are_no_introduced_figures(source, synthesized):
    assert not _named(_one(source, synthesized, "merged"), "INT-LEDGER-023")


def test_a_changed_multiplier_verb_is_a_changed_figure():
    found = _named(_one(_PRICES, "Prices roughly tripled every few days in late 1923."), "INT-LEDGER-023")
    assert found and "'tripled every' (3) where its cited sources state 'doubled every' (2)" in found[0], found
    assert L.aligned_changes("Prices roughly tripled every few days in late 1923.", _PRICES)[0]
    assert L.aligned_changes("Output halved in the slump of 1931.", "Output doubled in the slump of 1931.")[0]
    assert not _named(_one(_PRICES, _PRICES, "carried"), "INT-LEDGER-023")  # control


# ============================================================================================ majors: dropped qualifiers
@pytest.mark.parametrize("source,synthesized,word", [
    (_PRICES, "Prices doubled every few days in late 1923.", "roughly"),
    (_PRICES, "Prices exactly doubled every few days in late 1923.", "roughly"),
    ("Prices nearly doubled in 1923.", "Prices doubled in 1923.", "nearly"),
    ("Workers tended to vote SPD in 1928.", "Workers voted SPD in 1928.", "tended to"),
    ("Reportedly, the plan stabilised the currency in 1924.", "The plan stabilised the currency in 1924.", "Reportedly"),
    (_PRICES, "Prices roughly doubled every day in late 1923.", "every few days"),
    (_KAPP, "Many Germans supported the Kapp Putsch in 1920.", "a minority of"),
    (_KAPP, "Germans supported the Kapp Putsch in 1920.", "a minority of"),
    (_KAPP, "Half of Germans supported the Kapp Putsch in 1920.", "a minority of"),
])
def test_a_dropped_or_strengthened_qualifier_is_named(source, synthesized, word):
    found = _named(_one(source, synthesized), "INT-LEDGER-026")
    assert found and f"'{word}'" in found[0] and ("drops the qualifier" in found[0] or "drops the hedge" in found[0]), found


@pytest.mark.parametrize("source,synthesized", [
    (_DAWES, "The Dawes Plan of 1924 stabilised the currency to a large extent."),  # the finding's false finding
    (_DAWES, "The Dawes Plan of 1924 stabilised the currency in large part."),
    (_DAWES, "The Dawes Plan of 1924 mainly stabilised the currency."),
    (_DAWES, "The Dawes Plan of 1924 mostly stabilised the currency."),
    (_DAWES, "The currency was largely stabilised by the Dawes Plan of 1924."),
    (_PRICES, "Prices approximately doubled every few days in late 1923."),
    (_KAPP, "In 1920, only a minority of Germans supported the Kapp Putsch."),
    ("The network then grew from almost nothing: the line opened in 1838, and the Great Western reached Bristol in 1841.",
     "The line opened in 1838, and the Great Western reached Bristol in 1841."),  # the qualified word is not restated
    ("A few years later the strike ended in Hamburg.", "A few years later the strike ended in Hamburg."),
])
def test_a_qualifier_kept_in_other_words_or_not_restated_is_clean(source, synthesized):
    found = [m for m in _named(_one(source, synthesized), "INT-LEDGER-026") if "qualifier" in m or "hedge" in m]
    assert not found, found


# ============================================================================================ majors: a credit by a reporting verb
@pytest.mark.parametrize("source,synthesized,who", [
    (_KAPP, "Kapp admitted that only a minority of Germans supported the Kapp Putsch in 1920.", "Kapp"),
    (_STRESEMANN, "Stresemann himself said he probably saved the republic from collapse in 1923.", "Stresemann"),
    (_STRESEMANN, "Stresemann later conceded that he probably saved the republic from collapse in 1923.", "Stresemann"),
])
def test_a_statement_credited_by_a_reporting_verb_to_a_person_the_source_only_names_is_named(source, synthesized, who):
    found = [m for m in _named(_one(source, synthesized), "INT-LEDGER-026") if "credits the statement" in m]
    assert found and f"to '{who}'" in found[0], found


@pytest.mark.parametrize("source,synthesized", [
    ("Stresemann said that he had saved the republic in 1923.", "Stresemann said he had saved the republic in 1923."),  # the source gives the credit
    ("Many workers joined the strike in Hamburg in 1923.", "Workers admitted that they joined the strike in Hamburg in 1923."),  # no name
])
def test_a_credit_the_source_gives_or_a_word_that_is_no_name_is_clean(source, synthesized):
    found = [m for m in _named(_one(source, synthesized), "INT-LEDGER-026") if "credits the statement" in m]
    assert not found, found


def test_the_new_readers_are_linear_on_long_hostile_text():
    for hostile in ("Kapp admitted that " * 20_000, "roughly " * 50_000, "a minority of " * 30_000, "two years later " * 25_000,
                    "Hjalmar Schacht " * 25_000, "four days " * 40_000):
        spent, _out = _cpu(lambda: (L.dropped_qualifiers(hostile, [_KAPP, _PRICES]), L._count_figures(hostile), L._reported_speech_credits(hostile, [hostile]),
                                    L.introduced_names(hostile[:4_000], [_DAWES], "paraphrased", stated_elsewhere=set())))
        assert spent < 8.0, (hostile[:16], spent)
