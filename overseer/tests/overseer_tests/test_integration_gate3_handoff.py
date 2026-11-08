"""Integration gate 3, handoff fixer: the overseer's fidelity checks (overseer/checks/fidelity.py).

* The stem fixer's handoff (item 1, pre-existing): a correct STEM answer whose result is wrapped in ``__…__``
  ('a = (20 - 0)/4.0 = __5.0 m s⁻²__.') was AUDIT_FAILED with OVS-FID-003 ("claim s1.2 states figures or dates the
  original_response states under no spelling: ['5.0']"). The STEM parser leaves the markup inside a statement out of its
  claim, so the claim states "5.0", while the figure reader reads no figure glued to an underscore (a word character).
  Rule ``emphasis-figures``: the response's figures are also read with every run of emphasis markers that opens or closes a
  word left out; a run between two letters or digits stays, so no figure is made up by joining digits. A figure the response
  states under no spelling is still FID-003.
* The class sweep of the module the fix changed: every public entry point on the standard hostile inputs and on runs of
  emphasis markers, under a CPU-time bound per call far above a linear reader's time.
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.integrity import WorkPlan
from epinoic_overseer.checks import fidelity as F
from epinoic_overseer.checks import normalise, plain_form, strip_list_markers
from epinoic_logic.translate.contracts import SuppliedText

from .core_hostile import INPUTS, N, one, sweep
from .growth import growth
from .conftest import CFG, DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, KEY, english_report, findings, make_auditor, new_channel

REQUEST = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."
ANSWER = "The trolley starts from rest, so u = 0. a = (20 - 0)/4.0 = {} m s⁻²{}."


def _physics(answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist"]))
        m = hub.dispatch("t", "physics-specialist", REQUEST)[0]
        _reply, rc = hub.receive("t", m.message_id, answer, agent_id="physics-specialist", report_id="r1")
        return rc, hub.audit("t")
    finally:
        hub.close()


def _state(audit) -> str:
    return getattr(audit.state, "value", audit.state)


@pytest.mark.parametrize("value", ["__5.0", "**5.0", "*5.0", "_5.0", "***5.0"])
def test_a_correct_result_in_emphasis_passes_its_audit(value):
    marker = value.rstrip("5.0")
    rc, audit = _physics(ANSWER.format(value, marker))
    assert rc.status.value == "ACCEPTED", [(f.code, f.message[:120]) for f in rc.findings]
    assert [(c.constraint_id, c.satisfied) for c in rc.formal_checks] == [("stem-eq-1", True)]
    assert not findings(audit, "OVS-FID-003"), [f.message for f in findings(audit, "OVS-FID-003")]
    assert _state(audit) == "AUDIT_PASSED", [(f.code, f.message[:160]) for f in audit.report.findings]


def test_a_wrong_result_in_emphasis_is_the_engines_error_and_passes_its_audit():
    rc, audit = _physics(ANSWER.format("__6.0", "__"))
    assert [f.code for f in rc.findings if f.severity == "error"] == ["INT-SUBJ-001"]
    assert [(c.constraint_id, c.satisfied) for c in rc.formal_checks] == [("stem-eq-1", False)]
    assert not findings(audit, "OVS-FID-003") and _state(audit) == "AUDIT_PASSED"


def _send(text: str, claim_text: str):
    claim = dict(claim_id="en-fig", claim_text=claim_text, claim_role="evidence", materiality="supporting")
    auditor = make_auditor()
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    ch.respond(m.message_id, english_report(text, [dict(c) for c in EN_CLAIMS] + [claim]))
    return auditor.audit(ch.uid)


def test_control_a_figure_the_response_states_under_no_spelling_is_still_fid_003():
    audit = _send(EN_TEXT + " The shifts lasted __12__ hours.", "The shifts lasted 14 hours.")
    f = findings(audit, "OVS-FID-003")
    assert f and f[0].claim_ids == ["en-fig"] and "14" in f[0].message


def test_control_digits_joined_by_markers_make_up_no_figure():
    # "2**10" is no emphasis: the run between two digits stays, so the response states no 210
    audit = _send(EN_TEXT + " The shifts lasted 2**10 hours.", "The shifts lasted 210 hours.")
    assert [f.claim_ids for f in findings(audit, "OVS-FID-003")] == [["en-fig"]]
    assert F.strip_edge_emphasis("2**10 = 1024, x_1 and x__5 and 1_000") == "2**10 = 1024, x_1 and x__5 and 1_000"


def test_control_a_figure_in_emphasis_that_the_claim_states_without_markers_is_known():
    audit = _send(EN_TEXT + " The shifts lasted __12__ hours.", "The shifts lasted 12 hours.")
    assert not findings(audit, "OVS-FID-003")


@pytest.mark.parametrize("text,plain", [("a = __5.0 m s⁻²__.", "a = 5.0 m s⁻²."), ("**12** and *5*", "12 and 5"), ("***5***", "5"), ("(**5**)", "(5)"),
                                        ("_5.0 m s⁻²_", "5.0 m s⁻²"), ("* 5 apples", " 5 apples"), ("x__5", "x__5"), ("", "")])
def test_rule_emphasis_figures_leaves_out_the_markers_at_a_words_edge(text, plain):
    assert F.strip_edge_emphasis(text) == plain


def test_the_rule_is_listed():
    assert "emphasis-figures" in F.FIDELITY_RULES and F.FIDELITY_RULES[-1] == "emphasis-figures"


# --------------------------------------------------------------------------- the class sweep: every public entry point


#: Runs of emphasis markers, the shapes the new reading scans, beside the standard hostile inputs.
EMPHASIS_RUNS: dict[str, str] = {
    "stars": "*" * N + "x", "underscores": "_" * N + "x", "stars between letters": "a" + "*" * N + "b", "underscores between digits": "1" + "_" * N + "2",
    "star words": "*a" * (N // 2), "bold figures": "**5** " * (N // 6), "glued underscores": "__5.0__" * (N // 7), "digit stars": "1*" * (N // 2),
}
TEXTS: dict[str, str] = {**INPUTS, **EMPHASIS_RUNS}


def _fidelity_entries(text: str):
    docs = [SuppliedText(document_id="d1", title="T", author="A", text=text)]
    yield "claim_occurs", lambda: F.claim_occurs(text[:4000], normalise(text), plain_response=plain_form(text), raw_response=text)
    yield "claim_occurs(tail)", lambda: F.claim_occurs(text[:3997] + "...", normalise(text), tail=True, plain_response=plain_form(text), raw_response=text)
    yield "strip_enclosing_quotes", lambda: F.strip_enclosing_quotes(text)
    yield "strip_trailing_punctuation", lambda: F.strip_trailing_punctuation(text)
    yield "located_anywhere", lambda: F.located_anywhere(text[:2000], docs)
    yield "located_anywhere(in the text)", lambda: F.located_anywhere("the river ran", docs)
    yield "uncut_text", lambda: F.uncut_text(text[:3997] + "...")
    yield "unmarked_cut_text", lambda: F.unmarked_cut_text(text[:4000], text)
    yield "response_list_numbers", lambda: F.response_list_numbers(text)
    yield "strip_mark_annotations", lambda: F.strip_mark_annotations(text)
    yield "figure_text", lambda: F.figure_text(text)
    yield "no_quotation_to_verify", lambda: F.no_quotation_to_verify([text[:200], "the river"], text, set())
    yield "strip_edge_emphasis", lambda: F.strip_edge_emphasis(text)
    yield "the response's figures, both readings", lambda: (F.figure_spellings(F.figure_text(text)), F.figure_spellings(F.figure_text(F.strip_edge_emphasis(text))))
    yield "a claim's figures", lambda: F._claim_figures(text[:4000], F.response_list_numbers(text))
    yield "normalise, plain_form, strip_list_markers", lambda: (normalise(text), plain_form(text), strip_list_markers(text))


@pytest.mark.parametrize("shape", tuple(TEXTS))
def test_sweep_the_fidelity_readers(shape):
    assert not sweep(_fidelity_entries, texts=one(shape, TEXTS))


def test_the_emphasis_reading_is_linear():
    ratio, small, large = growth(F.strip_edge_emphasis, "a" + "*_" * 10000 + "b", "a" + "*_" * 40000 + "b")
    assert large < 0.05 and ratio < 8, (ratio, small, large)
