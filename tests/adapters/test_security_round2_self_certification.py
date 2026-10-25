"""Security round 2, SEC-V3, SEC-V4 and the item lists of the sweep: the self-certification readers of
``adapters.markdown`` are linear in the sentence.

SEC-V3 and the item lists. The subject scans (``_SELF_SUBJECT_KINDS_RE`` and ``_SELF_SOURCED_RE``, read with ``finditer``)
try a match at every place of a sentence. A try that starts inside a long list of items ('statistics or x statistics or
...') reads the list to its end before it fails for want of an anchor ('here', 'above') or a source ('of the History
report') after it, and so does the try at every later item: quadratic in the list (a History answer of one such sentence of
18,000 characters held the hub for 132 s, the base 113 s). A modifier may also start at any letter after an apostrophe or a
hyphen, so a run such as "'b'b'b..." was read again from each of its letters. The readers (``_self_subjects``,
``_self_sourced``) now try the patterns only where a match can start, decided from one reading of the sentence (where the
item nouns stand, where each item a list may hold ends, which item follows a list's 'and' or 'or', and whether a list from
an item's end reaches an anchor or a source); the pattern itself gives each match, so the matches are the ones ``finditer``
gave.

SEC-V4. The certifying lead ('As verified against the census, ...') read the white space after 'against' or 'with' with
three quantifiers (``\\s+[^,;:.]{1,60}\\s*``), so a long run of white space with no comma after it cost about sixty times
the square of the run. Each run is now read once; the lead matches the same strings.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.adapters import markdown

from ..growth import growth

#: The modifiers of the subject patterns, as they were before the round (the patterns themselves are unchanged).
OLD_SELF_MOD = (r"(?:(?!(?:is|are|was|were|has|have|had|been|be|being|and|or|but|nor|of|in|on|at|to|for|from|with|by|that|which|who|here"
                r"|above|below|given|not|no|as|than|so|its|it|this|these|those|the|a|an)\b)[a-z][a-z'’-]*\s+){0,2}")
INFRA = markdown._INFRASTRUCTURE
#: The lead's place words, complement and closing mark after this round, and before it (kept as data).
NEW_LEAD_MIDDLE = (r"(?:\s++(?:above|here|below|earlier|before|already|throughout|in\s+full)){0,3}"
                   rf"(?:\s++by\s++{INFRA}|\s++(?:against|with)(?:\s++[^,;:.\s](?:[^,;:.]{{0,58}}[^,;:.\s])?|\s(?=\s)))?\s*+[,:]")
OLD_LEAD_MIDDLE = (r"(?:\s+(?:above|here|below|earlier|before|already|throughout|in\s+full)){0,3}"
                   rf"(?:\s+(?:by\s+{INFRA}|(?:against|with)\s+[^,;:.]{{1,60}}))?\s*[,:]")
OLD_LEAD = re.compile(markdown._SELF_LEAD_RE.pattern.replace(NEW_LEAD_MIDDLE, OLD_LEAD_MIDDLE), markdown._SELF_LEAD_RE.flags)


def test_the_subject_patterns_are_the_ones_before_the_round():
    assert markdown._SELF_MOD == OLD_SELF_MOD
    assert markdown._SELF_SUBJECT_KINDS_RE.pattern == markdown._subject_kinds(OLD_SELF_MOD)
    assert markdown._SELF_SOURCED_RE.pattern == rf"\b(?P<sourced>{markdown._sourced(OLD_SELF_MOD)})\b"
    assert NEW_LEAD_MIDDLE in markdown._SELF_LEAD_RE.pattern and OLD_LEAD.pattern != markdown._SELF_LEAD_RE.pattern


# ---- growth ---------------------------------------------------------------------------------------------------------------

RUNS = ["'b", "-b", "’b", "b'", "x'y-"]


def test_the_subject_scans_read_a_run_of_marked_letters_in_linear_time():
    """Four times the run costs about four times as much (before the round: about sixteen times)."""
    for unit in RUNS:
        make = lambda n: "These figures " + unit * (n // len(unit)) + " here are accurate, and the quotations " + unit * (n // len(unit)) + " are exact."
        for scan in (markdown._self_subjects, markdown._self_sourced):
            ratio, small, large = growth(lambda s: sum(1 for _m in scan(s)), make(2000), make(8000))
            assert ratio < 8.0, (unit, scan.__name__, ratio, small, large)


def test_the_self_certification_of_a_sentence_with_a_long_run_grows_linearly():
    clear = markdown._self_certification.cache_clear
    for unit in ("'b", "-b"):
        make = lambda n: "The quotations of the History report " + unit * (n // len(unit)) + " are exact."
        ratio, small, large = growth(markdown.is_self_certification, make(2000), make(8000), clear=clear)
        assert ratio < 8.0, (unit, ratio, small, large)


#: Item lists no subject reads to their end with a match: no determiner before them, and no anchor or source after them.
LISTS = {
    "or": lambda n: "Statistics" + " or x statistics" * (n // 16) + " are accurate.",
    "and": lambda n: "Figures" + ", and dates" * (n // 11) + " have been checked.",
    "modified": lambda n: "Census figures" + " or well-known x quotations" * (n // 27) + " were verified, from the report.",
    "determiners": lambda n: "My figures" + " or my figures" * (n // 14) + " end of the report.",
    "white space": lambda n: "Statistics" + " \n or \t x  statistics" * (n // 20) + " end.",
}


def test_the_subject_scans_read_a_long_item_list_in_linear_time():
    """Four times the list costs about four times as much (before the round: about sixteen times)."""
    for shape, make in LISTS.items():
        for scan in (markdown._self_subjects, markdown._self_sourced):
            ratio, small, large = growth(lambda s: sum(1 for _m in scan(s)), make(2000), make(8000))
            assert ratio < 8.0, (shape, scan.__name__, ratio, small, large)


def test_the_self_certification_of_a_long_item_list_grows_linearly():
    clear = markdown._self_certification.cache_clear
    for shape in ("or", "modified", "determiners"):
        ratio, small, large = growth(markdown.is_self_certification, LISTS[shape](2000), LISTS[shape](8000), clear=clear)
        assert ratio < 8.0, (shape, ratio, small, large)


def test_a_certifying_lead_with_a_long_run_of_white_space_is_read_in_linear_time():
    shapes = [
        lambda n: " As already checked above against " + " " * n + "x",
        lambda n: "As verified with" + " " * n + "x" + " " * n + ";",
        lambda n: "As confirmed against\t" + "\t " * (n // 2) + "the census" + " " * n + "x",
        lambda n: "As verified above" + " " * n + "here" + " " * n + "x",
    ]
    for make in shapes:
        ratio, small, large = growth(lambda s: markdown._SELF_LEAD_RE.match(s) is not None, make(2000), make(8000))
        assert ratio < 8.0, (make(10), ratio, small, large)


# ---- the same answers ------------------------------------------------------------------------------------------------------

SENTENCES = [
    "Every mileage figure above has been checked against the Board of Trade railway returns.",
    "Each of the mileage figures given above has been verified.",
    "Each quotation of the History specialist above is exact.",
    "All quotations from the History specialist above are accurate.",
    "My quotations of both texts are exact.",
    "These figures are accurate.",
    "The figures here are accurate.",
    "The poet's so-called figures are vivid.",
    "The well-known quotations above are exact.",
    "The census figures are reliable.",
    "x-called figures above are exact.",
    "rock-'n'-roll figures here are checked.",
    "The writer's own quotations from the poem are quoted verbatim.",
    "Every figure taken from the History specialist has been reproduced exactly.",
    "My reading is confirmed by the final stanza.",
    "The whole answer has been verified.",
    "'these figures are accurate'",
    "-the figures above are exact.",
    "o'er-the figures here are checked",
    "the man's-best figures above are exact",
    "it's-figures above are verified and 'a'b dates here are exact",
    "the 'so-called' figures in this answer are exact",
    "half-remembered dates and well-worn quotations above have been checked",
    "every ex-post figure, and the re-used dates, given above are exact",
    "these mis-quoted quotations from the Poem above are accurate",
    "The figures of the History report are accurate.",
    "’tis-the figures of the History specialist above are checked",
    "And-the figures here; or-the figures above; the-figures below",
]


def _random_sentences(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    words = ["every", "each", "each of the", "all", "all of the", "the", "these", "those", "my", "our", "this", "a",
             "figure", "figures", "date", "dates", "quotation", "quotations", "quotes", "statistics", "claims", "paragraph", "answer",
             "reading", "argument", "above", "here", "below", "given above", "in this answer", "of", "from", "taken from", "History",
             "specialist", "report", "poem", "texts", "both", "is", "are", "has been", "have been", "checked", "verified", "exact",
             "accurate", "and", "or", "mileage", "census", "so-called", "well-known", "poet's", "o'er", "ex-post", "it's", "’tis", "x",
             "'b", "-b", "b'", "'", "-", "’", ",", ".", ";"]
    spaces = [" ", " ", " ", "", "  ", "\n", "-", "'"]
    out = []
    for _ in range(n):
        toks = []
        for _ in range(rnd.randrange(2, 22)):
            w = rnd.choice(words)
            toks.append(w.capitalize() if rnd.random() < 0.1 else w)
            toks.append(rnd.choice(spaces))
        out.append("".join(toks))
    return out


def _list_sentences(n: int, seed: int) -> list[str]:
    """Sentences of item lists: items with modifiers and determiners joined by 'and' or 'or', with an anchor, a source or
    neither after them, an answer named among them, and runs of letters with apostrophes and hyphens."""
    rnd = random.Random(seed)
    items = ["figures", "dates", "quotations", "x statistics", "census figures", "well-known quotes", "so-called x figures", "quoted lines",
             "cited  line", "my figures", "every date", "each one of the totals", "all of the steps", "the claims", "these details",
             "o'er-the figures", "b'b'b figures", "x-'y items", "the islands", "is figures", "it's dates", "x y z figures", "figurehead"]
    seps = [" or ", " and ", ", and ", ",or ", " , or ", "\n and\t", " plus ", "  or  "]
    tails = [" here", " above", " given above", " in this answer", " of the paragraph above", " of the History specialist",
             " taken from the history report above", " from the poem", " from both texts", " are accurate.", " end.", "", " herein",
             " of the History specialist's report", " of my colleague's answer"]
    heads = ["", "", "Every ", "Each one of the ", "All ", "The ", "These ", "My ", "This paragraph and ", "my reading or ", "'", "-"]
    out = []
    for _ in range(n):
        k = rnd.choice([1, 1, 2, 3, 6, 12, 30])
        parts = [rnd.choice(heads), rnd.choice(items)]
        for _ in range(k - 1):
            parts += [rnd.choice(seps), rnd.choice(items)]
        parts.append(rnd.choice(tails))
        if rnd.random() < 0.3:
            parts += [" and ", rnd.choice(heads), rnd.choice(items), rnd.choice(tails)]
        out.append("".join(parts))
    return out


def _sig(m):
    return (m.span(), m.lastgroup, m.groupdict()) if m.re.groupindex else (m.span(), m.groups())


def test_every_determiner_form_is_read():
    """The determiner forms the readers try (``_DET_FORM_RES``) give every end the determiner groups of the patterns can
    take before an item: for each place no white space follows (an item starts with a letter), one form ends there exactly
    when the group, matched whole up to there, does."""
    group = re.compile(rf"(?:{markdown._SELF_UNIVERSAL_DET}\s+|(?:the|these|those|my|our)\s+)", re.IGNORECASE)
    rnd = random.Random(5)
    words = ["each", "one", "of", "the", "all", "every", "these", "those", "my", "our", "its", "figures", "Each", "ALL", "x"]
    for _ in range(3000):
        s = "".join(rnd.choice(words) + rnd.choice([" ", "  ", "\n", " \t "]) for _ in range(rnd.randint(1, 5)))
        want = {e for e in range(len(s) + 1) if group.fullmatch(s, 0, e) and not re.match(r"\s", s[e:e + 1])}
        got = {m.end() for m in (rx.match(s) for rx in markdown._DET_FORM_RES) if m is not None}
        assert got == want, s


def test_the_subject_scans_find_the_matches_finditer_found():
    """``_self_subjects`` and ``_self_sourced`` give, match for match (spans and groups), what scanning the patterns with
    ``finditer`` gives: on the sentences above, on random sentences of the readers' words, apostrophes and hyphens, and on
    item lists of every length with and without what a subject needs after them."""
    compared = inner = 0
    texts = SENTENCES + _random_sentences(4000, seed=3) + _list_sentences(3000, seed=9)
    for s in texts:
        for scan, rx in ((markdown._self_subjects, markdown._SELF_SUBJECT_KINDS_RE), (markdown._self_sourced, markdown._SELF_SOURCED_RE)):
            got, want = [_sig(m) for m in scan(s)], [_sig(m) for m in rx.finditer(s)]
            assert got == want, (scan.__name__, s)
            inner += sum(1 for (a, _b), *_rest in want if a > 0 and s[a - 1] in "'’-")
            compared += 1
    assert compared == 2 * len(texts)
    assert inner > 20   # matches that open right after an apostrophe or a hyphen


def _lead(rnd: random.Random) -> str:
    def ws(must=False):
        w = rnd.choice(["", " ", "  ", "\t", "\n", "   ", " \n "][1 if must else 0:])
        return w if rnd.random() < 0.85 else w * rnd.randint(2, 30)

    def core():
        n = rnd.choice([0, 0, 1, 1, 2, 3, 5, 10, 20, 40, 55, 58, 59, 60, 61, 62, 63, 70])
        chars = list("abcxyz ABC\t\n '\"()-0123456789")
        return "".join(rnd.choice(chars if rnd.random() < 0.9 else chars + [",", ";", ":", "."]) for _ in range(n))
    p = [rnd.choice(["", " ", "**", "\"", "(", "- ", "1. "]), rnd.choice(["As", "as", "AS", "A"]), ws(True)]
    if rnd.random() < 0.3:
        p += [rnd.choice(["already", "now", "formally", "fully"]), ws(True)]
    p.append(rnd.choice(["checked", "verified", "confirmed", "compared with", "matched against", "shown to be correct", "proved", "certified",
                         "accepted", "noted", "double-checked"]))
    for _ in range(rnd.choice([0, 0, 1, 2, 3, 4])):
        p += [ws(True), rnd.choice(["above", "here", "below", "earlier", "already", "in full", "in  full"])]
    c = rnd.random()
    if c < 0.25:
        p += [ws(True), "by", ws(True), rnd.choice(["the engine", "Z3", "the hub", "Engels", "the verification layer"])]
    elif c < 0.7:
        p += [ws(rnd.random() < 0.95), rnd.choice(["against", "with", "Against", "within"]), ws(rnd.random() < 0.9), core(), ws()]
    p += [ws(), rnd.choice([",", ":", ";", ".", "", " ,", "x"]), rnd.choice(["", " the figures hold.", ","])]
    return "".join(p)


def test_the_certifying_lead_matches_what_it_matched():
    """Only whether the lead matches is read (``_self_certification``): it matches exactly the sentences it matched before
    the round, on leads built from its words with white space, complements of every length about the bound of sixty
    characters, and marks."""
    rnd = random.Random(11)
    hits = 0
    for _ in range(20000):
        s = _lead(rnd)
        a, b = OLD_LEAD.match(s) is not None, markdown._SELF_LEAD_RE.match(s) is not None
        assert a == b, s
        hits += a
    assert 2000 < hits < 18000


def test_the_self_reports_and_leads_are_still_named():
    """Clean controls of the readers the round changed."""
    for s in ("Every mileage figure above has been checked against the Board of Trade railway returns.",
              "Each quotation of the History specialist above is exact.", "My quotations of both texts are exact.",
              "As verified against the census, the figures hold.", "As checked above, the dates are right.",
              "As confirmed by the engine, the answer is valid."):
        assert markdown.is_self_certification(s), s
    for s in ("The census figures are reliable.", "As confirmed by Engels, the workers were poor.",
              "The figures of the History report are accurate.", "My reading is confirmed by the final stanza."):
        assert not markdown.is_self_certification(s), s
