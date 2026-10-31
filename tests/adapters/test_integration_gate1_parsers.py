"""Integration gate 1 (before arena round 8): the shared text readers of the parsers (``adapters/markdown.py``).

Linear time (critical findings parser-safety-3 and -5, which stalled the History hub and the STEM front end):

* the note-clause splitter reads a sentence end from the end of the text (``markdown._terminal_len``), and its trailing
  "from memory" label and its parentheticals start only where no blank precedes, so a run of blanks is read once;
* the emphasis markers are removed in one pass (``markdown.strip_emphasis``), character for character what
  ``EMPHASIS_RE.sub(r"\\2", text)`` gives;
* the accuracy mark of a line of working (``branches.generic_parser._ACCURACY_MARK_RE``, which the STEM parser reads for every
  line) starts only where no blank precedes.

Each is held to an equality test against the old pattern, to the finding's worst-case input with a wide time bound and to a
growth ratio.

Quotation roles (majors, end-to-end B5 and B6): the parsers read the quotations of an answer with
``markdown.parser_quotation_spans`` under the task type they are given, and the packs read them again under the same task:
a corrected form in a marking task ('"una mujer muy simpático" → "una mujer muy simpática"') is the writer's own words,
never checked as a quotation, while the student's words are checked and an altered quotation in the same task is still an
error. A mention of words the text lacks ('without "like" or "as"', 'Source A has no "apology"') stays a quotation claim,
as the Overseer's rules expect, but the shared credit rule (``sources.attribute_excerpt``, every parser) credits it to no
text when no supplied text holds it (``markdown.absent_word_mentions``: both quotation-role readers must call it such a
mention, and it has at most three words), so it is no invented quotation of the poem or the source; a quoted word of the
text under a naming frame ('the conjunction "But"'), a negated reporting verb ('never says "x"'), a long span joined to a
mention and a quoted content word the text lacks are still checked.

The one-line History answer (hold-out ho_d_bare_hist): an answer whose only prose is one short line is that answer, not an aside."""
from __future__ import annotations

import random
import re
import time

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches import generic_parser as gp
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

from ..growth import growth
from ..timing import empty_caches

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
KEY = b"integration-gate-1-parsers-markdown-key-01"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)

OLD_TERMINAL_RE = re.compile(r"[.!?…]*[\"'”’»)\]]*\s*$")
OLD_TRAILING_BARE_LABEL_RE = re.compile(r"\s+(?:(?:quoted|given|cited|stated|recalled)\s+)?from (?:memory|recollection)(?=[.!?]?[\"'”’»)\]]*\s*$)", re.IGNORECASE)
OLD_PAREN_SPAN_RE = re.compile(r"\s*\([^()]*\)")
OLD_ACCURACY_MARK_RE = re.compile(r"(?:(?:\s{2,}|\t)\(?A\d{1,2}\)?|\s*\(A\d{1,2}\))(?:\s*(?:\(?[MARN]\d{1,2}\)?|AG))*[.;,]?\s*$")


def _random_texts(alphabet, seed: int, n: int, longest: int = 24):
    rng = random.Random(seed)
    for _ in range(n):
        yield "".join(rng.choice(alphabet) for _ in range(rng.randint(0, longest)))


def _clear():
    empty_caches()  # every memo of the package: the readers the splitter calls keep their own, by text length


# --------------------------------------------------------------------------- blanks in the note-clause splitter (parser-safety-3)


def test_the_sentence_end_is_read_from_the_end_as_the_old_search_read_it():
    alphabet = [".", "!", "?", "…", '"', "'", "”", "’", "»", ")", "]", " ", "\t", "\n", "\r", " ", "a", "b", "(", ",", "x."]
    for text in _random_texts(alphabet, 1, 20000):
        assert md._terminal_len(text) == len(OLD_TERMINAL_RE.search(text).group(0)), repr(text)


def test_the_trailing_label_and_the_parentheticals_match_what_the_unanchored_patterns_matched():
    words = [" ", "  ", "\t", "\n", "from memory", "From Memory", "from recollection", "quoted", "given", " stated", ".", "!", '"', ")", "(", "x", "a (b)",
             "In 1931", " from memory.", "(c. 1.9 million, from memory)", "x(", "()", "( )"]
    for text in _random_texts(words, 2, 20000, longest=10):
        old, new = OLD_TRAILING_BARE_LABEL_RE.search(text), md._TRAILING_BARE_LABEL_RE.search(text)
        assert (old and old.span()) == (new and new.span()), repr(text)
        assert [m.span() for m in md._PAREN_SPAN_RE.finditer(text)] == [m.span() for m in OLD_PAREN_SPAN_RE.finditer(text)], repr(text)


@pytest.mark.parametrize("blank", [" ", "\t", "\n", " \t"])
def test_the_note_clause_splitter_reads_a_run_of_blanks_in_linear_time(blank):
    # the finding's input; before the gate 0.96 s at 5,000 blanks, 4.06 s at 10,000, 16.16 s at 20,000
    make = lambda n: "It is 5 m; " + blank * (n // len(blank)) + "x."  # noqa: E731
    _clear()
    t = time.perf_counter()
    md._split_note_clauses(make(20000))
    assert time.perf_counter() - t < 1.0
    ratio, small, large = growth(md._split_note_clauses, make(4000), make(16000), clear=_clear)
    assert ratio < LINEAR, (ratio, small, large)
    for text in ("In 1990 it was 5" + blank * 5000 + "from memory x", "It is 5 m (" + blank * 5000 + "x) y.", "It is 5 m," + blank * 5000 + "from memory."):
        _clear()
        t = time.perf_counter()
        md._split_note_clauses(text)
        assert time.perf_counter() - t < 1.0


@pytest.mark.parametrize("case", ["ws_sp_embedded", "ws_tab_embedded", "ws_sp_num"])
@pytest.mark.parametrize("subject,agent", [("History", "history-specialist"), ("Physics", "physics-specialist")])
def test_a_run_of_20000_blanks_crosses_the_hub_in_seconds(case, subject, agent):
    # before the gate: History over 45 s (all three), Physics 9.3 s, 8.3 s and over 45 s
    texts = {"ws_sp_embedded": "The value is 5 m. " + " " * 20000 + "It is 6 m.", "ws_tab_embedded": "The value is 5 m. " + "\t" * 20000 + "It is 6 m.",
             "ws_sp_num": "In 1990 it was 5" + " " * 20000 + "and 6 in 2000."}
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, "Answer the question.")
    t = time.perf_counter()
    _reply, rc = hub.receive("t", m.message_id, texts[case], agent_id=agent, report_id="r1")
    assert time.perf_counter() - t < 10.0
    assert rc.status.value.startswith("ACCEPTED")


def test_the_accuracy_mark_matches_what_the_unanchored_pattern_matched_in_linear_time():
    alphabet = [" ", "  ", "\t", "A1", "(A1)", "A12", "M1", "(M2)", "R1", "AG", "x", "=", "4", ".", ";", ",", "\n", "(", ")"]
    for text in _random_texts(alphabet, 3, 20000, longest=12):
        old, new = OLD_ACCURACY_MARK_RE.search(text), gp._ACCURACY_MARK_RE.search(text)
        assert (old and old.span()) == (new and new.span()), repr(text)
    # before the gate: 3.2 s of a 4.0 s Physics crossing of 20,000 blanks were this search, once per line
    t = time.perf_counter()
    gp._ACCURACY_MARK_RE.search("x" + " " * 40000 + "y")
    assert time.perf_counter() - t < 0.5
    ratio, small, large = growth(gp._ACCURACY_MARK_RE.search, "x" + " " * 4000 + "y", "x" + " " * 16000 + "y")
    assert ratio < LINEAR, (ratio, small, large)
    assert gp._ACCURACY_MARK_RE.search("a = 6 − 6t  A1") and gp._ACCURACY_MARK_RE.search("x = 4 (A1).") and not gp._ACCURACY_MARK_RE.search("x = 4 A1")


# --------------------------------------------------------------------------- emphasis markers (parser-safety-5)


def test_the_emphasis_markers_are_removed_as_the_substitution_removed_them():
    alphabet = ["*", "**", "_", "__", "`", "a", "b", " ", "\n", "1", "é", ".", "-", "\t", "x_y", "*a*", "**b**", "_c_", "`d`", "ü", "٣", " ", "(", ")"]
    for text in _random_texts(alphabet, 4, 40000, longest=18):
        assert md.strip_emphasis(text) == md.EMPHASIS_RE.sub(r"\2", text), repr(text)
    assert md.strip_markup("**What the question wants:** the value, *in* `x`.") == "What the question wants: the value, in x."


def test_the_emphasis_markers_of_an_unclosed_line_are_removed_in_linear_time():
    # the finding's input ('**a ' * k); before the gate strip_markup took 0.87 s at 10,000 characters and 3.74 s at 20,000
    t = time.perf_counter()
    md.strip_markup("**a " * (400000 // 4))
    assert time.perf_counter() - t < 2.0
    ratio, small, large = growth(md.strip_emphasis, "**a " * 2000, "**a " * 8000)
    assert ratio < LINEAR, (ratio, small, large)


def test_a_history_answer_of_unclosed_emphasis_crosses_the_hub_in_seconds():
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"]))
    m, _, _ = hub.dispatch("t", "history-specialist", "Answer the question.")
    t = time.perf_counter()
    hub.receive("t", m.message_id, "**a " * 5000, agent_id="history-specialist", report_id="r1")
    assert time.perf_counter() - t < 10.0  # before the gate: over 45 s


# --------------------------------------------------------------------------- quotation roles in the parsers (B5, B6)


SP_LINES = ('1. "*una mujer muy simpático*" → "*una mujer muy simpática*" (the adjective agrees with *mujer*).\n'
            '5. "*te recomiendo que participas*" → "*te recomiendo que participes*", or "*os recomiendo que participéis*" in *vosotros*.\n'
            'Also: "*Fue muy cansado*" → "*Fue muy agotador*".')


def _inners(text: str, task: str | None) -> list[str]:
    with md.quotation_task(task, authoritative=True):
        return [inner.strip("*") for _a, _b, inner in md.parser_quotation_spans(text)]


def test_a_correction_in_a_marking_task_is_the_writers_own_words_and_the_students_words_stay_quotations():
    assert _inners(SP_LINES, "marking_feedback") == ["una mujer muy simpático", "te recomiendo que participas", "Fue muy cansado"]
    # in any other task, or with no task known, every span stays a quotation and is checked (repair round 4, INV-Q1)
    for task in ("analytical_paragraph", "essay", None):
        assert len(_inners(SP_LINES, task)) == 7, task


@pytest.mark.parametrize("sentence,absent", [
    ('The bulbs are named as fists without "like" or "as".', ["like", "as"]),
    ('It is a metaphor: the bulbs are called fists with no "like" or "as" to mark the comparison.', ["like", "as"]),
    ('The bruise comparison has no "like" or "as", so it is a metaphor.', ["like", "as"]),
    ('The poet never uses "I" in the poem.', ["I"]),
    ('The turn then arrives with the conjunction "But", which exposes that premise.', []),  # names the text's word: checked
    ('The image "each one a closed fist" is a metaphor.', []),
    ('The speaker says "like a fist" here.', []),
    ('The poem never says "the sky wept blood" at all.', []),  # a negated reporting verb attributes (close round 3, INV-QR-1)
    ('The writer avoids "very" throughout.', []),               # a mention for one reader only: credited and checked as before
    ('Unlike "the bright fields" of the morning, the river is dark.', []),  # a contrast is no absence frame
    # a long span joined to a mention may be words the sentence gives as the text's: only a span of at most three words is one
    ('Source A has no "apology", and "the treaty was a crime of revenge" is its verdict.', ["apology"]),
])
def test_a_mention_of_words_the_text_lacks_is_read_by_both_readers_and_stays_a_quotation_span(sentence, absent):
    for task in ("analytical_paragraph", "marking_feedback", None):
        with md.quotation_task(task, authoritative=True):
            assert [inner for _a, _b, inner in md.absent_word_mentions(sentence)] == absent, (sentence, task)
            # every mention stays a span the parsers carry as a quotation claim (the Overseer's rules read it as a mention)
            assert md.parser_quotation_spans(sentence) == md.find_quotation_spans(sentence), (sentence, task)


def test_the_absence_frames_the_packs_read_are_the_markdown_ones():
    from epinoic_logic.branches import packs
    assert packs._absent_mentions is md.absent_mentions
    assert packs._ABSENT_BEFORE_RE is md.ABSENT_BEFORE_RE and packs._ABSENT_JOIN_RE is md.ABSENT_JOIN_RE
    text = 'The bruise comparison has no "like" or "as", so it is a metaphor; the poem never says "ayudar".'
    assert md.absent_mentions(text, md.find_quotation_spans(text)) == ["like", "as", "ayudar"]


def _dev_verdict(case_id: str) -> str:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests import argdiag_cases as C, case_scoring as S
    return S.run_case(C.load_cases([case_id])[0])["verdict"]


@pytest.mark.parametrize("case_id", ["e2e-B5-sp", "e2e-B13-sp", "e2e-B6-en"])
def test_the_end_to_end_answers_with_corrections_and_mentions_are_clean(case_id):
    # before the gate: false alarms (seven INT-REQ-003 'altered quotation' errors on sp-e1; INT-REQ-003 and ES-SRC-001 on en-e1)
    assert _dev_verdict(case_id) == "control_clean"


BLOG = ("El verano pasado he trabajado como voluntario en un banco de alimentos. Al principio, era un poco nervioso, pero conocí a "
        "una mujer muy simpático que me ayudó mucho. La gente es muy agradecidos. Fue muy cansado, pero me gustó.")
SP_REQUEST = "Mark my blog post and list my grammar mistakes with the correction. Quote my exact words."


def _sp_receipt(answer: str, task_type: str = "marking_feedback"):
    from epinoic_logic.translate.contracts import SuppliedText
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    agent = "language-b-spanish-specialist"
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Language B: Spanish", task_type=task_type, selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, SP_REQUEST, [SuppliedText(document_id="doc-blog", title="Blog post", author="student", text=BLOG)])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return [(f.code, f.severity, f.message) for f in list(rc.findings) + list(rc.structural_findings)]


def test_a_marking_answer_with_corrections_gets_no_altered_quotation_error_and_an_altered_quotation_still_does():
    correct = ('Your blog is clear. Corrections:\n'
               '1. "una mujer muy simpático" → "una mujer muy simpática" (the adjective agrees with mujer).\n'
               '2. "Fue muy cansado" → "Fue muy agotador" (cansado means tired).')
    codes = _sp_receipt(correct)
    assert not [c for c in codes if c[1] == "error"], codes
    # control: the student's words altered and given as the student's (no correction frame) are still an error in the same task
    altered = ('Your blog is clear, but you wrote "una mujer muy simpatiquísima que me ayudó mucho", which needs the feminine form.\n'
               '1. "una mujer muy simpático" → "una mujer muy simpática".')
    errors = [c for c in _sp_receipt(altered) if c[1] == "error"]
    assert any("simpatiquísima" in c[2] for c in errors), errors


POEM = "The bulbs lie under frost, each one a closed fist. In spring the fists begin to open."


def _en_receipt(answer: str, poem: str = POEM):
    """The English parser's quotation claims (claim text -> credited documents, assumptions) and the hub's findings at warning
    or error severity, for one answer about one supplied poem (the one text under analysis)."""
    from epinoic_logic.adapters.english_specialist.parser import parse_response
    from epinoic_logic.translate.contracts import SuppliedText
    doc = SuppliedText(document_id="doc-allotment", title="Allotment", author="poet", text=poem)
    rep = parse_response(answer, request_id="q", task_id="t", report_id="r1", task_type="analytical_paragraph", supplied_texts=[doc])
    quotes = {c.claim_text: ([r.document_id for r in c.source_refs], list(c.assumptions)) for c in rep.claims if c.claim_role == "evidence"}
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    agent = "english-a-literature-specialist"
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="English A: Literature", task_type="analytical_paragraph", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, "Analyse the imagery of the poem.", [doc])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    flags = [(f.code, f.severity, f.message) for f in list(rc.findings) + list(rc.structural_findings) if f.severity in ("warning", "error")]
    return quotes, flags


def test_a_quoted_content_word_absent_from_the_text_stays_an_error_beside_a_mention():
    answer = ('The image "each one a closed fist" is a metaphor, since the bulbs are named as fists without "like" or "as". '
              'The word "glimmering" shows the hope beneath the cold.')
    quotes, flags = _en_receipt(answer)
    # the mentioned words stay quotation claims, credited to no text (before the gate: to the poem, refuted by ES-SRC-001 and INT-REQ-003)
    for word in ('"like"', '"as"'):
        refs, assumptions = quotes[word]
        assert refs == [] and any("the sentence says the text lacks these words" in a for a in assumptions), (word, quotes[word])
    assert not any("'like'" in msg or "'as'" in msg or '"like"' in msg or '"as"' in msg for _c, _s, msg in flags), flags
    # control: a quoted content word the poem lacks, presented as the poem's, is still refuted
    assert quotes['"glimmering"'][0] == ["doc-allotment"]
    assert {c for c, s, msg in flags if s == "error" and "glimmering" in msg} >= {"ES-SRC-001"}, flags


SOURCE_A_TEXT = "The treaty was signed in 1919 and imposed reparations."
ECB_TEXT = "Inflation fell to 2.4% in 2024 as energy prices eased."


def _hub_flags(subject: str, agent: str, doc, answer: str):
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="essay", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, "Answer the question using the source.", [doc])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return [(f.code, f.severity, f.message) for f in list(rc.findings) + list(rc.structural_findings) if f.severity in ("warning", "error")]


def test_the_shared_credit_rule_credits_a_mention_of_words_the_text_lacks_to_no_text():
    from epinoic_logic.adapters import sources
    from epinoic_logic.translate.contracts import SuppliedText
    docs = {"doc-src": SuppliedText(document_id="doc-src", title="Source A", author="a minister", text=SOURCE_A_TEXT)}
    sentence = 'Source A has no "apology" or "regret".'
    for word in ("apology", "regret"):
        doc_id, notes = sources.attribute_excerpt(word, ["doc-src"], docs, sentence=sentence)
        assert doc_id is None and sources.uncredited_excerpt(notes[0]) == word, (word, notes)
    # controls: a negated reporting verb attributes (close round 3, INV-QR-1), and a mentioned word the source holds is credited
    assert sources.attribute_excerpt("apology", ["doc-src"], docs, sentence='Source A never says "apology".')[0] == "doc-src"
    assert sources.attribute_excerpt("reparations", ["doc-src"], docs, sentence='Source A has no "reparations".') == ("doc-src", [])
    assert sources.attribute_excerpt("apology", ["doc-src"], docs, sentence='Source A speaks of "apology".')[0] == "doc-src"
    joined = 'Source A has no "apology", and "the treaty was a crime of revenge" is its verdict.'
    assert sources.attribute_excerpt("the treaty was a crime of revenge", ["doc-src"], docs, sentence=joined)[0] == "doc-src"
    assert sources.attribute_excerpt("apology", ["doc-src"], docs, sentence=joined)[0] is None


@pytest.mark.parametrize("subject,agent,title,text,mention,invented", [
    ("History", "history-specialist", "Source A", SOURCE_A_TEXT,
     'Source A has no "apology" or "regret", which shows the treaty was imposed in 1919.',
     'Source A calls the treaty "a dictated peace of revenge", which shows it was imposed in 1919.'),
    ("Economics", "economics-specialist", "ECB bulletin", ECB_TEXT,
     'The ECB bulletin never uses "deflation", so it does not expect falling prices. Inflation fell to 2.4% in 2024.',
     'The ECB bulletin warns of "a deflationary spiral" in 2024, although inflation fell to 2.4%.'),
])
def test_a_mention_of_words_the_source_lacks_is_no_invented_quotation_on_the_history_and_generic_branches(subject, agent, title, text, mention, invented):
    from epinoic_logic.translate.contracts import SuppliedText
    doc = SuppliedText(document_id="doc-src", title=title, author="author", text=text)
    # before the gate: HI-SRC-001 and INT-REQ-003 errors on 'apology' and 'regret', INT-REQ-003 on 'deflation'
    assert not [f for f in _hub_flags(subject, agent, doc, mention) if f[1] == "error"]
    # control: words the sentence presents as the source's, which the source lacks, are still refuted, alone or joined to a mention
    assert any(code == "INT-REQ-003" and sev == "error" for code, sev, _m in _hub_flags(subject, agent, doc, invented))
    joined = mention.split(",")[0] + ', and "the treaty was a crime of revenge" is its verdict.'
    assert any(code == "INT-REQ-003" and sev == "error" for code, sev, _m in _hub_flags(subject, agent, doc, joined))


def test_a_mention_the_text_holds_is_credited_and_a_negated_reporting_verb_is_still_checked():
    # a mentioned word the poem does use is credited to the poem by the ordinary rule, and found there
    quotes, flags = _en_receipt('The image "each one a closed fist" is first a simile, but the second image has no "like", so it is a metaphor.',
                                poem="The bulbs lie under frost, each one a closed fist, like a stone. In spring the fists begin to open.")
    assert quotes['"like"'] == (["doc-allotment"], [])
    assert not [f for f in flags if f[1] == "error"], flags
    # 'never says "x"' is an attribution for the role reader (close round 3, INV-QR-1): credited to the poem and refuted, as before
    quotes, flags = _en_receipt('The poem never says "the sky wept blood", but the frost is a closed fist.')
    assert quotes['"the sky wept blood"'][0] == ["doc-allotment"]
    assert {c for c, s, msg in flags if s == "error" and "the sky wept blood" in msg} >= {"ES-SRC-001"}, flags


def test_the_packs_read_a_report_under_the_task_its_parse_read_it_in():
    report = gp.GenericTextParser("lb").parse_response(SP_LINES, request_id="r", task_id="t", report_id="x", subject="Language B: Spanish",
                                                       task_type="marking_feedback")
    assert md.parse_task_of(report) == "marking_feedback"
    # a copy of the parsed report (the overseer's journaled one) is read under the same task
    assert md.parse_task_of(report.model_validate(report.model_dump(mode="json"))) == "marking_feedback"
    # a report this process did not parse has no task, whatever task type it names (INV-QROLE-1): its quotations are read in none
    assert md.parse_task_of(report.model_copy(update={"report_id": "y"})) is None
    assert md.parse_task_of(report.model_copy(update={"original_response": SP_LINES + " "})) is None
    assert md.parse_task_of(report.model_copy(update={"claims": report.claims[:1]})) is None


# --------------------------------------------------------------------------- a one-line History answer (hold-out ho_d_bare_hist)


@pytest.mark.parametrize("text,roles", [
    ("Stalin's Five-Year Plans were a complete success.", [("point", "material")]),
    ("Stalin's Five-Year Plans were a complete success.\n\nHope this helps.", [("point", "material"), ("other", "supporting")]),
    ("Hope this helps.", [("other", "supporting")]),       # a closing remark alone is no answer
    ("Thanks!", [("other", "supporting")]),
])
def test_an_answers_only_short_line_is_the_answer_not_an_aside(text, roles):
    rep = HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="x", task_type="essay")
    assert [(c.claim_role, c.materiality) for c in rep.claims] == roles
