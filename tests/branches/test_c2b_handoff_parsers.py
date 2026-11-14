"""Round-9 clearance, second fix pass (c2b), handoff fixer: the parsers' and packs' items the STEM and core fixers handed over, each pinned on
the recorded c2 answers (``tests/channel/data/c2_core_material.json``) with a control that keeps the rule asserted.

* A "Judgement:" line is its part's judgement, material, on the STEM and generic branches (ess-p9c s13.1: the evaluation read as stating no
  judgement, INT-REQ-008).
* A "label: value" line is a result, never a short title (ch-p9b s14.2 'Stock solution: 0.984' was a heading, role other).
* Part furniture: a "Check:" line supports the result it checks (the part's material claim), a notation set-up ("Write R for red and B
  for blue.") serves the working, and a part's title worded as its question ("(f) Why a volumetric flask is used [1]") is a heading.
* A caveat that tells the reader to check before relying on the figures is no self-certification (hi-t15 h1.19); a narrated check still is
  (bi-p9b s2.3).
* A quoted phrase introduced as a label or a definition ('Let E be "at least one blue"') is a mention, never an unverifiable quotation
  (maa-t15 m11.1, CORE-SRC-003).
* A figure stated with its noun and a year that a supplied text states with another value ('221 vecinos en 2015' for '212 vecinos') is named
  (INT-SUBJ-004, supplied_figure), on every branch but the STEM ones.
* Every reader added here is linear on the standard hostile inputs.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.adapters.markdown import JUDGEMENT_LABEL_RE, LABEL_BEFORE_RE, absent_mentions, find_quotation_spans, is_self_certification
from epinoic_logic.adapters.stem_specialist.parser import _CHECK_LEAD_RE, _NOTATION_LEAD_RE, _question_title
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import _line_heading
from epinoic_logic.branches.grounded_figures import _dated_noun_findings
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText

from ..channel.c2_core_support import by_code, codes, deliver

KEY = b"c2b-handoff-parsers-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def _claims(task: str) -> dict:
    hub, _ch, reply, rc = deliver(task)
    hub.close()
    return {c["claim_id"].split("@")[0]: c for c in reply.payload["claims"]}, rc


# ============================================================================================ judgement labels
def test_ess_p9c_the_judgement_line_is_the_parts_material_judgement():
    claims, rc = _claims("ess-p9c")
    s13 = claims["s13.1"]
    assert s13["claim_text"].startswith("Judgement:") and (s13["claim_role"], s13["materiality"]) == ("judgement", "material")
    assert not by_code(rc.findings, "INT-REQ-008"), [f.message for f in by_code(rc.findings, "INT-REQ-008")]


@pytest.mark.parametrize("line, read", [
    ("Judgement: sustainable drainage is a partial solution.", True), ("(d) Overall judgement: the policy works.", True),
    ("**Conclusion:** the policy works.", True), ("Verdict: partly.", True),
    ("The judgement of the court was harsh.", False), ("A conclusion follows below.", False),
])
def test_the_judgement_label_is_read_at_the_lines_start_only(line, read):
    assert bool(JUDGEMENT_LABEL_RE.match(line)) is read


def test_a_judgement_line_is_a_judgement_on_the_generic_branch_too():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="Economics", task_type="short_answer",
                           selected_agent_ids=["economics-specialist", "dummy-combinator"], allowed_document_ids=[]))
    m, _r, _q = hub.dispatch("t", "economics-specialist", "Evaluate the policy of raising interest rates.", [])
    reply, rc = hub.receive("t", m.message_id, "Higher rates cut borrowing and spending.\n\nJudgement: the policy works in the short run only.",
                            agent_id="economics-specialist", report_id="rep-x")
    hub.close()
    [j] = [c for c in reply.payload["claims"] if c["claim_text"].startswith("Judgement:")]
    assert (j["claim_role"], j["materiality"]) == ("judgement", "material") and not by_code(rc.findings, "INT-REQ-008")


# ============================================================================================ result lists, headings, furniture
def test_ch_p9b_every_line_of_the_result_list_is_a_result():
    claims, _rc = _claims("ch-p9b")
    assert claims["s14.2"]["claim_text"] == "Stock solution: 0.984"
    assert [claims[f"s14.{k}"]["claim_role"] for k in range(2, 7)] == ["quantitative"] * 5


@pytest.mark.parametrize("body, following, heading", [
    ("Stock solution: 0.984", True, False), ("Total: 450", True, False), ("2024 (no tax)", True, True), ("2025", True, True),
    ("Working for (b):", False, True), ("Why a volumetric flask is used", True, True), ("Why the yield rose.", True, False),
])
def test_a_label_value_line_is_no_title_and_a_question_worded_line_is_one(body, following, heading):
    assert _line_heading(body, following) is heading


def test_a_check_line_supports_the_result_it_checks_and_a_notation_line_serves_the_working():
    maa, _rc = _claims("maa-t15")
    assert (maa["m6.3"]["claim_role"], maa["m6.3"]["materiality"]) == ("quantitative", "supporting")
    assert maa["m6.2"]["materiality"] == "material" and "g⁻¹(x) = (x − 3)/2" in maa["m6.2"]["claim_text"]
    assert maa["m8.1"]["claim_text"] == "Write R for red and B for blue." and maa["m8.1"]["materiality"] == "supporting"
    mai, _rc2 = _claims("mai-t15")
    assert mai["m8.1"]["claim_text"].startswith("Check:") and mai["m8.1"]["materiality"] == "supporting"
    assert mai["m7.1"]["materiality"] == "material"
    assert _CHECK_LEAD_RE.match("Check by counting: 18 selections") and not _CHECK_LEAD_RE.match("Checking accounts pay interest.")
    assert _NOTATION_LEAD_RE.match("Write R for red and B for blue.") and not _NOTATION_LEAD_RE.match("Write the answer in standard form.")


def test_a_part_title_worded_as_its_question_is_a_heading():
    for task, cid, title in (("ch-p9b", "s12.1", "Why a volumetric flask is used"), ("ch-t15", "s16.1", "Why high pressure and a moderate temperature are used")):
        claims, rc = _claims(task)
        assert claims[cid]["claim_text"] == title and claims[cid]["claim_role"] == "other", (task, claims[cid])
        assert not by_code(rc.findings, "INT-REQ-004"), (task, [f.message for f in by_code(rc.findings, "INT-REQ-004")])
    assert _question_title("Why a volumetric flask is used [1]") and not _question_title("Why the flask is used.") and not _question_title("A flask [1]")


# ============================================================================================ caveats, labels in quotation marks
def test_a_caveat_that_asks_the_reader_to_check_is_no_self_certification():
    _claims_hi, rc = _claims("hi-t15")
    assert not [f for f in by_code(rc.findings, "INT-HANDOFF-006") if "h1.19" in f.claim_ids]
    _claims_bi, rc2 = _claims("bi-p9b")
    assert [f for f in by_code(rc2.findings, "INT-HANDOFF-006") if any(c.split("@")[0] == "s2.3" for c in f.claim_ids)]
    assert not is_self_certification("The dates above are from memory; check them against your textbook before you rely on them.")
    assert is_self_certification("Every figure above has been checked, so you can rely on them.")


def test_a_quoted_label_or_definition_is_a_mention():
    _claims_maa, rc = _claims("maa-t15")
    assert "CORE-SRC-003" not in codes(rc.structural_findings), [f.message[:160] for f in rc.structural_findings if f.code == "CORE-SRC-003"]
    t = 'Let E be "at least one blue" and F be "both blue". The author writes "the house was dark".'
    assert absent_mentions(t, find_quotation_spans(t)) == ["at least one blue", "both blue"]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="Economics", task_type="short_answer",
                           selected_agent_ids=["economics-specialist", "dummy-combinator"], allowed_document_ids=[]))
    m, _r, _q = hub.dispatch("t", "economics-specialist", "Explain the effect of inflation.", [])
    _reply, rc2 = hub.receive("t", m.message_id, 'Inflation erodes savings. The author writes "the house was dark" about the slump.',
                              agent_id="economics-specialist", report_id="rep-x")
    hub.close()
    assert "CORE-SRC-003" in codes(rc2.structural_findings)  # control: a quotation of a text with no text supplied


@pytest.mark.parametrize("sentence, mention", [
    ('We call it "the gap between the two rates".', True), ('Let us call this "the threshold value".', True),
    ('The process is called "reverse osmosis".', True), ('This is a process called "reverse osmosis".', True),
    ('One minister called it "a parliament that could only say no".', False),   # another speaker's words: a quotation
    ('Marx calls them "the gravediggers of the bourgeoisie".', False), ('Historians called the treaty "a dictated peace".', False),
])
def test_naming_is_a_mention_only_when_it_is_the_writers_own_or_has_no_speaker(sentence, mention):
    """The suite's run of the handoff fixer's first reading of rule quoted-label (any "call(ed) it") took a minister's words for a
    name: 'One minister called it "a parliament that could only say no"' drew no CORE-SRC-003 (``test_packs_regressions``) and
    the reference corpus's reading moved (``test_quant_si_reading``). Naming is a mention only when it is the writer's own ("we
    call it", "let us call") or has no speaker ("called" right before the mark); words another speaker gave stay a quotation."""
    assert (absent_mentions(sentence, find_quotation_spans(sentence)) != []) is mention, sentence


# ============================================================================================ a dated figure of a supplied text
VALDEOCA = SuppliedText(document_id="doc-valdeoca", title="Valdeoca, el pueblo que volvió a abrir su escuela", author="Diario",
                        text="En 1960, Valdeoca tenía 1.250 habitantes, dos panaderías y una escuela con más de cien alumnos. Medio siglo después, "
                             "el pueblo se había quedado casi vacío: en 2015 solo quedaban 212 vecinos, la mayoría de más de setenta años.")
SP_Q = "Según el primer párrafo, ¿cuántos habitantes tenía Valdeoca en 1960 y cuántos tenía en 2015?"
SP_A = "1. 1.250 habitantes en 1960 y 212 vecinos en 2015."


def _spanish(answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="Language B: Spanish", task_type="short_answer",
                           selected_agent_ids=["language-b-spanish-specialist", "dummy-combinator"], allowed_document_ids=["doc-valdeoca"]))
    m, _r, _q = hub.dispatch("t", "language-b-spanish-specialist", SP_Q, [VALDEOCA])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="language-b-spanish-specialist", report_id="rep-x")
    hub.close()
    return rc


@pytest.mark.parametrize("answer, named", [
    (SP_A, None), (SP_A.replace("212 vecinos", "221 vecinos"), "212 vecinos"), (SP_A.replace("1.250 habitantes", "1.520 habitantes"), "1.250 habitantes"),
    ("1. 1.250 habitantes en 1960 y 212 casas en 2015.", None),
])
def test_a_figure_stated_with_its_noun_and_year_is_set_against_the_text(answer, named):
    rc = _spanish(answer)
    found = [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004") and "supplied_figure" in f.message]
    if named is None:
        assert not found, [f.message[:200] for f in found]
    else:
        assert found and all(f.severity == "warning" for f in found), [f.message[:200] for f in found]


# ============================================================================================ the new readers stay linear
HOSTILE = {
    "blanks": " " * 20_000 + "x", "tabs": "\t" * 20_000 + "x", "line breaks": "\n" * 20_000 + "x", "stops": "." * 20_000 + "x",
    "closing marks": "]" * 20_000 + "x", "mark labels": "(A1) " * 4_000 + "x", "parentheses": "(" * 20_000 + "x", "brackets": "[" * 20_000 + "x",
    "fence openers": "```" * 7_000 + "x", "number words": " and ".join(["twenty"] * 1_800) + " x", "= links": "x = " * 5_000 + "y",
    "list markers": "- " * 10_000 + "x", "judgement labels": "Judgement " * 2_000 + ":", "let labels": 'let E be "x" and ' * 1_000 + "y",
    "dated nouns": "212 vecinos en " * 1_400 + "2015", "checks": "Check by " * 2_500 + ":", "label values": "a: 1 " * 4_000 + "x",
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_new_parser_readers_are_linear_on_hostile_inputs(name):
    text = HOSTILE[name]
    t0 = time.process_time()
    JUDGEMENT_LABEL_RE.match(text), LABEL_BEFORE_RE.search(text[-60:]), absent_mentions(text, find_quotation_spans(text))
    _line_heading(text, True), _question_title(text), _CHECK_LEAD_RE.match(text), _NOTATION_LEAD_RE.match(text)
    _dated_noun_findings("c1", text[:4000], [SuppliedText(document_id="d", text=text)])
    is_self_certification(text[:4000])
    spent = time.process_time() - t0
    assert spent < 4.0, f"{name}: {spent:.2f} s"
