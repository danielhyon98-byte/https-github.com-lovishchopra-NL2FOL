"""Integration gate, round 1 (before arena round 8): the overseer's fixes, each tested at its cause.

* blocker, ``checks/fidelity.py``: the figure reader of a whole response rescanned a run of blank lines from every line
  start inside it (``ledger._LIST_MARKER_RE``), so 40,000 blank lines cost about 19 s per receive and per audit, and the
  400,000-character response bound about 30 minutes each; ``fidelity.figure_text`` gives the reader at most two line starts
  per run, and the same figures (rule ``linear-readers``);
* blocker, ``checks/fidelity.py``: ``_MARK_ANNOTATION_RE`` restarted at every space or tab of a run, so 20,000 spaces cost
  about 7 s per call (two calls per audit); ``strip_mark_annotations`` reads each run of annotations once, and gives the
  same text as the reference pattern;
* major, ``delivery_policy.py``: an answer whose receipt names a STEM relation that was not checked (ST-UNDEC-002,
  ST-PARSE-001) was delivered FORMALLY CHECKED (rule ``unchecked-working``);
* major, ``delivery_policy.py``: an answer carrying a self-report or a relayed check result (CORE-SELF-001, INT-REQ-014)
  was delivered FORMALLY CHECKED with the self-report intact (rule ``self-report-disclosed``);
* major, ``checks/receipts.py`` and ``replay.py``: a contradiction the channel drops as rounding-only (two correct lines
  giving 24.0 ohm by two routes) was OVS-RCPT-004 (the absent conflict) and OVS-RES-007 (the precision re-check replayed
  under the joint limits, UNSUPPORTED); rules ``stated-precision-conflict`` and ``precision-limits``;
* major, ``checks/translation.py``: the task's own equation as a premise of its solved form was OVS-TRN-006, circular
  (rule ``task-equation``);
* minors: an overlong numeral in the request failed the translation check internally (OVS-AUDIT-001, rule
  ``figure-digits``); the STEM folded tail read as absent from its response (OVS-FID-001, rule ``folded-tail`` line by
  line); a structured report's located citation that its prose paraphrases was OVS-FID-002 (rule ``located-citation``);
  a contained run missing a requested round passed every gate (``requested_rounds_present``).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.integrity.ledger import figure_spellings
from epinoic_logic.ir.schema import Problem, SourceRef
from epinoic_logic.overseer.checks import fidelity as F
from epinoic_logic.overseer.checks import receipts as RCPT
from epinoic_logic.overseer.checks import translation as T
from epinoic_logic.overseer.delivery_policy import NOT_CHECKED_CODES, SELF_REPORT_CODES, DeliveryPolicy
from epinoic_logic.overseer import replay as R
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from ..timing import measure
from .conftest import CFG, DOC, EN_INPUT, EN_TEXT, KEY, english_report, make_auditor, new_channel, problems_fn
from .delivery_support import PHYSICS, FakeClock, Verifier, physics_report, run_task, speed_translation

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "overseer"))
import run_contained as RC  # noqa: E402


def _audited(subject: str, agent: str, answer: str, request: str = "Answer the question."):
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m = hub.dispatch("t", agent, request)[0]
    return hub, m


def _receive_and_audit(subject: str, agent: str, answer: str, request: str = "Answer the question."):
    hub, m = _audited(subject, agent, answer, request)
    try:
        _msg, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
        audit = hub.audit("t")
        return rc, audit
    finally:
        hub.close()


# ============================================================================================ blocker: blank lines
FIGURE_CASES = [
    "a.\n\n\n1. x", "1.\n\n2. x", "\n\n\n1. x", "x 1.\n\n\n\n2) y", "March\n\n\n1902", "two\n\n million", "2.5\n\n× 10^3", "3.\n \n\t\n 4. five",
    "Item 1.\n\n", " \n\n 12. a\n\n\n(3) b 1,000\n\n7", "1.\r\n\r\n2. x 9", "a\n \n 1. b", "under\n\n nine", "5\n\n\nmillion",
]


@pytest.mark.parametrize("text", FIGURE_CASES)
def test_figure_text_gives_the_reader_the_figures_of_the_response(text):
    assert figure_spellings(F.figure_text(text)) == figure_spellings(text)


def test_figure_text_gives_the_same_figures_on_random_texts():
    tokens = ["1.", "2)", "(3)", "12.", " ", "  ", "\t", "\n", "\n\n", "\n \n", " \n\t\n ", "\r\n", " ", " ", "March", "1902", "two", "million",
              "thousand", "5", "2.5", "×", "10^3", "10³", "1,000", "-", "−", "per cent", "%", "a", "half", "x", "1840s", "e5", "3e8", "hundred", "and",
              "twenty", "-five", "under", "nine", "Item", ".", "1", "(", ")"]
    rng = random.Random(20261031)
    for _ in range(3000):
        text = "".join(rng.choice(tokens) for _ in range(rng.randint(0, 30)))
        assert figure_spellings(F.figure_text(text)) == figure_spellings(text), repr(text)


def test_the_figure_reading_of_a_long_run_of_blank_lines_is_linear():
    text = "The value is 5 m. " + "\n" * 100_000 + "It is 6 m."
    timing = measure(lambda: figure_spellings(F.figure_text(text)), bound=1.0, label="figures of 100,000 blank lines")
    assert timing.holds, timing
    assert all(dict(r) == dict(figure_spellings("The value is 5 m. \n\nIt is 6 m.")) for r in timing.results)


def test_a_fault_anchor_joining_claims_of_blank_lines_reads_its_figures_linearly():
    from epinoic_logic.overseer.repeats import figures_of
    text = ("x 5." + "\n" * 4000) * 50 + "7"  # fifty structured claims of 4,000 blank lines each, joined as a fault's anchor
    timing = measure(lambda: figures_of(text), bound=1.0, label="figures of a joined anchor of blank lines")
    assert timing.holds, timing
    assert all(r == ("5", "7") for r in timing.results)


def test_an_audited_physics_hub_receives_and_audits_forty_thousand_blank_lines_in_seconds():
    answer = "The value is 5 m. " + "\n" * 40_000 + "It is 6 m."
    timing = measure(lambda: _receive_and_audit("Physics", "physics-specialist", answer), bound=4.0, repeat=3, label="audited hub, 40,000 blank lines")
    assert timing.holds, timing  # before the fix: receive 18.96 s and audit 18.33 s
    for rc, audit in timing.results:
        assert rc.status.value.startswith("ACCEPTED") and audit.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")


# ============================================================================================ blocker: spaces and tabs
STRIP_CASES = [
    "only 9 [1].", "3t(2 − t) = 0  M1\nt = 0 or t = 2  A1", "$= 4787.58\\ldots$ (A1)", "the [1] grade of the scale is used", "x [1] [2]\n", "x  M1 (A1).",
    "[1] [1] [1] x", "x [1]  M1 y", "a (3 marks)", "b\t(M2)", "c\tM2.", "d  (M1", "e [ 12 marks ] ;", "f [1] M1", "g  AG", "x" + " " * 50 + "[1]",
    "x" + "\t" * 30 + "\n" + "y [2]", "[1]. (M1)", "z (2 marks)\n\n(3 marks)",
]


def _reference_strip(text: str) -> str:
    return F._MARK_ANNOTATION_RE.sub("", F._parser_unmarked(text))


@pytest.mark.parametrize("text", STRIP_CASES)
def test_strip_mark_annotations_gives_the_reference_patterns_text(text):
    assert F.strip_mark_annotations(text) == _reference_strip(text)


def test_strip_mark_annotations_gives_the_reference_text_on_random_texts():
    tokens = ["[1]", "[2 marks]", "[ 3 ]", "[1 spare]", "(3 marks)", "(M1)", "(A1)", "M1", "A2", "AG", "(R1", "N3)", "[", "]", "(", ")", " ", "  ", "\t",
              " \t", ".", ". ", ";", ",", "\n", "\n\n", "x", "only 9", "Mean", "=", "3t", "0", "M", "A", "[12]", "(12 marks)", "\r"]
    rng = random.Random(31102026)
    for _ in range(3000):
        text = "".join(rng.choice(tokens) for _ in range(rng.randint(0, 30)))
        assert F.strip_mark_annotations(text) == _reference_strip(text), repr(text)


@pytest.mark.parametrize("fill", [" ", "\t"])
def test_strip_mark_annotations_is_linear_on_a_hundred_thousand_spaces_or_tabs(fill):
    text = "The value is 5 m." + fill * 100_000 + "\nIt is 6 m."
    timing = measure(lambda: F.strip_mark_annotations(text), bound=1.0, label=f"strip_mark_annotations, 100,000 x {fill!r}")
    assert timing.holds, timing  # the reference pattern took 7.4 s on 20,000 spaces
    assert all(r == text for r in timing.results)


def test_strip_mark_annotations_reads_a_long_run_of_annotations_once():
    text = "y" + " [1]" * 40_000 + " x"  # one run that ends no sentence: the reference pattern rescans it from each annotation
    timing = measure(lambda: F.strip_mark_annotations(text), bound=1.0, label="a run of 40,000 annotations")
    assert timing.holds, timing
    assert all(r == text for r in timing.results)
    assert F.strip_mark_annotations("y" + " [1]" * 50 + " x") == _reference_strip("y" + " [1]" * 50 + " x")


def test_an_audited_english_hub_audits_twenty_thousand_spaces_in_seconds():
    answer = "The value is 5 m. " + " " * 20_000 + "It is 6 m."
    timing = measure(lambda: _receive_and_audit("English A: Literature", "english-specialist", answer), bound=2.0, repeat=3,
                     label="audited English hub, 20,000 spaces")
    assert timing.holds, timing


# ============================================================================================ major: unchecked STEM working
def _formal(extra: str):
    clock = FakeClock()
    rep = physics_report("physics-specialist", "rep-a", claims=(("p1.1", "The speed is 15 km/h."), ("p1.2", extra)))
    run = run_task(DeliveryPolicy(clock=clock), [("physics-specialist", rep)], verify=Verifier(clock, translations={"p1.2": speed_translation("p1.2")}))
    return run


@pytest.mark.parametrize("extra,code", [("The kinetic energy is Ek = ½mv² = 0.5 × 2.0 × 3.0 = 3.0 J.", "ST-UNDEC-002"),
                                        ("The total is 1 500 × 2 = 30.", "ST-PARSE-001")])
def test_a_stem_relation_not_checked_never_travels_under_the_formal_label(extra, code):
    run = _formal(extra)
    try:
        [rc] = run.receipts.values()
        assert code in {sf.code for sf in rc.structural_findings} and code in NOT_CHECKED_CODES
        d = run.decision
        assert d.mode != "formally_checked" and not d.receipt.formal.complete
        assert any("not checked" in r and code in r and "p1.2" in r for r in d.receipt.formal.reasons), d.receipt.formal.reasons
        assert not d.label.lower().startswith("formally checked")
    finally:
        run.close()


def test_control_an_answer_whose_working_is_all_checked_is_still_formally_checked():
    clock = FakeClock()
    run = run_task(DeliveryPolicy(clock=clock), [("physics-specialist", physics_report("physics-specialist", "rep-a"))], verify=Verifier(clock))
    try:
        [rc] = run.receipts.values()
        assert not ({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings}) & (NOT_CHECKED_CODES | SELF_REPORT_CODES)
        assert run.decision.mode == "formally_checked" and run.decision.receipt.formal.reasons == []
    finally:
        run.close()


# ============================================================================================ major: self-reports
SELF_REPORTS = [("A formal check of the hub verified every figure in this answer.", "other", "INT-REQ-014"),
                ("The engine confirmed the Mathematics report's speed of 15 km/h.", "evidence", "INT-REQ-014"),
                ("This answer was verified by Z3.", "other", "CORE-SELF-001")]
PEER_DOC = SuppliedText(document_id="doc-ma", title="Mathematics specialist notes", author="mathematics-specialist",
                        text="A car travels 120 km in 8 hours, so its speed is 15 km/h.")


@pytest.mark.parametrize("sentence,role,code", SELF_REPORTS)
def test_an_answer_carrying_a_self_report_never_travels_under_the_formal_label(sentence, role, code):
    agent = "physics-specialist"
    rep = physics_report(agent, "rep-a")
    claims = list(rep.claims) + [ClaimRecord(**PHYSICS, report_id="rep-a", agent_id=agent, claim_id="p1.9", claim_text=sentence, claim_role=role,
                                             materiality="supporting")]
    text = rep.original_response + " " + sentence
    rep = rep.model_copy(update={"claims": claims, "original_response": text, "response_sha256": sha256_text(text)})
    clock = FakeClock()
    run = run_task(DeliveryPolicy(clock=clock), [(agent, rep)], verify=Verifier(clock), supplied=[PEER_DOC])
    try:
        [rc] = run.receipts.values()
        assert code in {f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings}
        d = run.decision
        assert d.mode != "formally_checked" and not d.receipt.formal.complete
        assert any("self-report" in r and code in r for r in d.receipt.formal.reasons), d.receipt.formal.reasons
    finally:
        run.close()


def test_control_the_same_answer_without_the_self_report_is_formally_checked():
    clock = FakeClock()
    run = run_task(DeliveryPolicy(clock=clock), [("physics-specialist", physics_report("physics-specialist", "rep-a"))], verify=Verifier(clock),
                   supplied=[PEER_DOC])
    try:
        assert run.decision.mode == "formally_checked"
    finally:
        run.close()


# ============================================================================================ major: rounding-only conflict
IDS = dict(request_id="req-r", task_id="task-r", subject="Physics", task_type="calculation")
QUESTION = "A 2.2 kW kettle runs on 230 V mains and draws 9.57 A. Calculate the resistance of its heating element."
_RES = {"name": "heater_res", "sort": "Real", "meaning": "resistance of the heating element in ohms"}


def _v(n):
    return {"op": "var", "name": n}


def _r(x):
    return {"op": "real", "value": str(x)}


def _by_current(cid: str) -> Problem:
    """R = V/I written as 9.57 x R = V (the current rounded to 9.57 A), R stated to 3 s.f."""
    return Problem.model_validate({
        "problem_id": f"p-{cid}", "request_id": "req-r", "claim_id": cid, "query": "entailment",
        "symbols": [{"name": "mains_volts", "sort": "Real", "meaning": "mains voltage in volts"}, _RES],
        "premises": [{"id": "pv", "expr": {"op": "eq", "left": _v("mains_volts"), "right": _r(230)}, "grounding": {"kind": "arithmetic_fact"}},
                     {"id": "rv", "expr": {"op": "eq", "left": {"op": "mul", "args": [_r("9.57"), _v("heater_res")]}, "right": _v("mains_volts")},
                      "grounding": {"kind": "arithmetic_fact"}}],
        "conclusion": {"id": "C", "expr": {"op": "and", "args": [{"op": "ge", "left": _v("heater_res"), "right": _r("23.95")},
                                                                  {"op": "lt", "left": _v("heater_res"), "right": _r("24.05")}]}}})


def _by_power(cid: str, power: int) -> Problem:
    """R = V²/P written as P x R = 230 x 230."""
    return Problem.model_validate({
        "problem_id": f"p-{cid}", "request_id": "req-r", "claim_id": cid, "query": "entailment", "symbols": [_RES],
        "premises": [{"id": "rp", "expr": {"op": "eq", "left": {"op": "mul", "args": [_r(power), _v("heater_res")]},
                                           "right": {"op": "mul", "args": [_r(230), _r(230)]}}, "grounding": {"kind": "arithmetic_fact"}}],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": _v("heater_res"), "right": _r(0)}}})


def _two_routes(power: int = 2200):
    aud = make_auditor()
    ch = new_channel(aud, WorkPlan(plan_id="plan-r", selected_agent_ids=["physics-a", "physics-b"], **IDS))
    ra = physics_report("physics-a", "rep-a", (("a1.1", "R = V/I = 230 V / 9.57 A = 24.0 Ω."),), prefix="a1", ids=IDS)
    rb = physics_report("physics-b", "rep-b", (("b1.1", f"R = V²/P = (230 V)² / {power} W = {52900 / power:.1f} Ω."),), prefix="b1", ids=IDS)
    ch.channel.verify_claim_fn = problems_fn({"a1.1": _by_current("a1.1"), "b1.1": _by_power("b1.1", power)})
    m, _r1, _q1 = ch.request("router", "physics-a", QUESTION, [])
    _msg, _rc1 = ch.respond(m.message_id, ra)
    m2, _r2, _q2 = ch.request("router", "physics-b", QUESTION, [])
    _msg2, rc2 = ch.respond(m2.message_id, rb)
    return aud, ch, rc2


def _conflict_errors(audit) -> list:
    return [f for f in audit.report.findings if (f.code == "OVS-RCPT-004" and "INT-CONFLICT-001" in f.message) or f.code in ("OVS-RES-007", "OVS-AUDIT-005")]


def test_a_contradiction_only_at_a_precision_no_claim_states_is_audited_clean():
    aud, ch, rc2 = _two_routes()
    try:
        assert not [f for f in rc2.findings if f.code.startswith("INT-CONFLICT")]  # the channel drops it (rounding only)
        audit = aud.audit(ch.uid)
        assert not _conflict_errors(audit), [(f.code, f.message[:200]) for f in _conflict_errors(audit)]
        assert audit.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")
    finally:
        aud.close()


def test_before_the_rules_the_same_transfer_was_two_audit_errors(monkeypatch):
    """The regression's own control: without rule ``stated-precision-conflict`` the absent conflict is OVS-RCPT-004, and a
    replay that ignores the recorded precision bounds cannot reproduce the signed CONSISTENT (now OVS-AUDIT-005, never the
    OVS-RES-007 accusation of another definitive status)."""
    from epinoic_logic.engine.policies import PACK_POLICIES
    from epinoic_logic.ir.schema import DEFAULT_LIMITS
    monkeypatch.setattr(RCPT, "_rounding_only", lambda ctx, t: False)
    monkeypatch.setattr(R, "recorded_policy", lambda res: "" if res.limits is None else next(
        (n for n, lim in sorted(PACK_POLICIES.items()) if lim != DEFAULT_LIMITS and lim == res.limits), ""))
    aud, ch, _rc2 = _two_routes()
    try:
        codes = [f.code for f in aud.audit(ch.uid).report.findings]
        assert "OVS-RCPT-004" in codes and "OVS-AUDIT-005" in codes and "OVS-RES-007" not in codes
    finally:
        aud.close()


def test_control_a_real_contradiction_is_named_on_the_receipt_and_audited_clean():
    aud, ch, rc2 = _two_routes(power=2000)
    try:
        assert "INT-CONFLICT-001" in {f.code for f in rc2.findings}
        assert not _conflict_errors(aud.audit(ch.uid))
    finally:
        aud.close()


def test_a_channel_that_drops_a_real_conflict_behind_a_forged_precision_run_is_still_rcpt_004(monkeypatch):
    """An insider on the channel's side drops the INT-CONFLICT-001 of a real contradiction and runs a CONSISTENT
    'precision re-check' on a problem of its own choosing (one claim only): the auditor re-derives the channel's rule on the
    journaled pool itself, finds the conflict, and names the absence."""
    import epinoic_logic.channel.bus as bus
    from epinoic_logic.engine.policies import policy_config
    from epinoic_logic.engine.runner import verify
    from epinoic_logic.integrity.cross_check import PRECISION_LIMITS, at_stated_precision, joint_problem
    real = bus.check_cross_report_consistency

    def insider(problems, **kw):
        res, findings = real(problems, **kw)
        kept = [f for f in findings if f.code != "INT-CONFLICT-001"]
        if len(kept) != len(findings):
            one = at_stated_precision([problems[0]]) or [problems[0]]
            joint, _f, _m = joint_problem(one, request_id=kw.get("request_id", "req-r"), joint_id="cross-report-precision")
            verify(joint, policy_config("nonlinear", kw["config"]), PRECISION_LIMITS, signing_key=kw.get("signing_key"), key_id="integrity")
        return res, kept
    monkeypatch.setattr(bus, "check_cross_report_consistency", insider)
    aud, ch, rc2 = _two_routes(power=2000)
    try:
        assert not [f for f in rc2.findings if f.code.startswith("INT-CONFLICT")]
        f4 = [f for f in aud.audit(ch.uid).report.findings if f.code == "OVS-RCPT-004" and "INT-CONFLICT-001" in f.message]
        assert f4 and f4[0].severity == "error"
    finally:
        aud.close()


def test_rule_precision_limits_names_the_precision_bounds_only_on_a_joint_problem():
    from epinoic_logic.engine.policies import policy_config
    from epinoic_logic.engine.runner import verify
    from epinoic_logic.integrity.cross_check import PRECISION_LIMITS, at_stated_precision, joint_problem
    from epinoic_logic.ir.canonical import canonical_json
    relaxed = at_stated_precision([_by_current("a1.1"), _by_power("b1.1", 2200)])
    joint, _f, _m = joint_problem(relaxed, request_id="req-r", joint_id="cross-report-precision")
    cfg = policy_config("nonlinear", CFG.model_copy(update={"produce_unsat_core": True}))
    res = verify(joint, cfg, PRECISION_LIMITS, signing_key=KEY, key_id="integrity")
    assert res.status.value == "CONSISTENT" and R.recorded_policy(res) == R.PRECISION_POLICY and not R.unreplayable_limits(res)
    pj, cj = canonical_json(joint.model_dump(mode="json", exclude_none=True)), canonical_json(cfg.model_dump(mode="json"))
    assert json.loads(R.replay_problem(pj, cj, R.PRECISION_POLICY))["status"] == "CONSISTENT"
    assert json.loads(R.replay_problem(pj, cj))["status"] == "UNSUPPORTED"  # the joint bounds refuse its nonlinear terms
    # controls: the same bounds on a problem that is no joint problem are no rule's, and are never trusted for a replay
    other = res.model_copy(update={"problem_id": "p-single"})
    assert R.recorded_policy(other) == "" and R.unreplayable_limits(other)


def test_a_definitive_status_whose_limits_no_rule_names_is_audit_005_when_its_replay_refuses_it():
    from epinoic_logic.overseer.checks import Replay
    base = dict(result_id="r", replay_result_id="rr", original_status="CONSISTENT", replay_status="UNSUPPORTED", problem_digest_ok=True,
                config_digest_ok=True, versions_changed=False, budget_exceeded=False)
    assert R.classify(Replay(**base, unreplayable_limits=True)) == "OVS-AUDIT-005"
    assert R.classify(Replay(**base)) == "OVS-RES-007"  # control: limits a rule names, refused on replay: another status
    assert R.classify(Replay(**{**base, "replay_status": "INCONSISTENT_PREMISES"}, unreplayable_limits=True)) == "OVS-RES-007"


# ============================================================================================ major: the task's own equation
DISJ_ANSWER = "x = 1 or x = 5. Since |x − 3| = 2, either x − 3 = 2 or x − 3 = −2."


def _abs_premise(kind: str = "task_setting") -> dict:
    d = {"op": "sub", "left": _v("x"), "right": _r(3)}
    return {"id": "e_abs", "expr": {"op": "eq", "left": {"op": "ite", "cond": {"op": "ge", "left": d, "right": _r(0)}, "then": d, "otherwise": {"op": "neg", "arg": d}},
                                    "right": _r(2)}, "label": "|x − 3| = 2", "grounding": {"kind": kind, "source_refs": [], "certainty": "established"}}


def _equation_problem(premise: dict, conclusion: dict, *, request_id: str = "req-ovs", claim_id: str = "m1.1") -> Problem:
    return Problem.model_validate({
        "problem_id": f"p-{claim_id}", "request_id": request_id, "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": "x", "sort": "Real", "meaning": "the unknown", "grounding": {"kind": "task_setting"}}],
        "premises": [premise], "conclusion": {"id": "C", "expr": conclusion, "label": "the solution",
                                              "grounding": {"kind": "specialist_inference"}}})


SOLVED = {"op": "or", "args": [{"op": "eq", "left": _v("x"), "right": _r(1)}, {"op": "eq", "left": _v("x"), "right": _r(5)}]}
SQUARE = {"id": "e_sq", "expr": {"op": "eq", "left": {"op": "mul", "args": [_v("x"), _v("x")]}, "right": _r(9)}, "label": "x^2 = 9",
          "grounding": {"kind": "task_setting"}}
SQUARE_SOLVED = {"op": "or", "args": [{"op": "eq", "left": _v("x"), "right": _r(3)}, {"op": "eq", "left": _v("x"), "right": _r(-3)}]}


def _standing(premise: dict, conclusion: dict, request: str) -> str:
    p = _equation_problem(premise, conclusion)
    rep = SpecialistReport(report_id="r", request_id="q", task_id="t", agent_id="a", subject="Mathematics: Analysis and Approaches", task_type="worked_solution",
                           original_response=DISJ_ANSWER, response_sha256=sha256_text(DISJ_ANSWER), claims=[], created_at="2026-10-20T00:00:00Z")
    return T.premise_standing(p.premises[0], rep, [request], {"x": "Real"}, (), p).kind


@pytest.mark.parametrize("premise,conclusion,task", [(_abs_premise(), SOLVED, "Solve |x − 3| = 2."), (SQUARE, SQUARE_SOLVED, "Solve x^2 = 9."),
                                                     (_abs_premise(), SOLVED, "For which x is |x − 3| = 2?")])
def test_rule_task_equation_reads_the_tasks_own_equation_as_its_data(premise, conclusion, task):
    p = _equation_problem(premise, conclusion)
    assert T.task_equation(p.premises[0], p, [task], {"x": "Real"}) is not None
    assert _standing(premise, conclusion, task) == T.TRANSCRIPTION


@pytest.mark.parametrize("premise,conclusion,task", [
    (_abs_premise(), SOLVED, "Solve |x − 4| = 2."),                                   # another equation
    (_abs_premise(), SOLVED, "Find x."),                                              # no equation stated
    (_abs_premise(), SOLVED, "Show that |x − 3| = 2."),                               # a target the answer must derive
    (_abs_premise(), SOLVED, "Show that x = 1 or x = 5 when |x − 3| = 2."),           # inside a show-that clause
    (_abs_premise(), SOLVED, "Is |x − 3| = 2 when x = 5?"),                           # asked, not stated
    (_abs_premise(), _abs_premise()["expr"], "Solve |x − 3| = 2."),                   # the conclusion restates it, no solved form
    (_abs_premise("specialist_inference"), SOLVED, "Solve |x − 3| = 2."),             # the writer's own
])
def test_control_rule_task_equation_never_reads_anything_else_as_data(premise, conclusion, task):
    assert _standing(premise, conclusion, task) != T.TRANSCRIPTION


def _equation_task(premise: dict, request: str):
    aud = make_auditor()
    plan = WorkPlan(plan_id="plan-m", request_id="req-m", task_id="task-m", subject="Mathematics: Analysis and Approaches", task_type="worked_solution",
                    selected_agent_ids=["mathematics-aa-specialist"])
    ch = new_channel(aud, plan)
    report = SpecialistReport(report_id="rep-m", request_id="req-m", task_id="task-m", agent_id="mathematics-aa-specialist", subject=plan.subject,
                              task_type="worked_solution", original_response=DISJ_ANSWER, response_sha256=sha256_text(DISJ_ANSWER), created_at="2026-10-20T00:00:00Z",
                              claims=[ClaimRecord(request_id="req-m", task_id="task-m", report_id="rep-m", agent_id="mathematics-aa-specialist", subject=plan.subject,
                                                  task_type="worked_solution", claim_id="m1.1", claim_text="x = 1 or x = 5.", claim_role="quantitative",
                                                  proposed_claim_kind="arithmetic")])
    ch.channel.verify_claim_fn = problems_fn({"m1.1": _equation_problem(premise, SOLVED, request_id="req-m")})
    m, _r, _q = ch.request("router", "mathematics-aa-specialist", request, [])
    ch.respond(m.message_id, report)
    return aud, ch


def test_a_solved_equation_resting_on_the_tasks_own_equation_is_not_circular():
    aud, ch = _equation_task(_abs_premise(), "Solve |x − 3| = 2.")
    try:
        assert "OVS-TRN-006" not in {f.code for f in aud.audit(ch.uid).report.findings}
    finally:
        aud.close()


def test_control_the_same_equation_grounded_by_the_writer_alone_stays_circular():
    aud, ch = _equation_task(_abs_premise("specialist_inference"), "Solve |x − 3| = 2.")
    try:
        assert "OVS-TRN-006" in {f.code for f in aud.audit(ch.uid).report.findings}
    finally:
        aud.close()


def test_control_a_task_setting_the_request_does_not_state_stays_circular():
    aud, ch = _equation_task(_abs_premise(), "Solve the equation in the textbook.")
    try:
        assert "OVS-TRN-006" in {f.code for f in aud.audit(ch.uid).report.findings}
    finally:
        aud.close()


def _circular_accusation_outcome(premise: dict):
    from .test_protocol_validate import acc, review
    from .test_translation_agents import link, response
    aud, ch = _equation_task(premise, "Solve |x − 3| = 2.")
    try:
        r = review(aud, ch.uid)
        t = response(r.dossier)
        lk = link(r.dossier, "m1.1")
        a = acc("a1", "translation_circular", [{"pointer": lk["claim_pointer"] + "/claim_text"}, {"pointer": lk["translation_pointer"] + "/problem/conclusion/expr"}],
                statement="The translation assumes its conclusion.", message_ids=[t["message_id"]], receipt_ids=[t["receipt_id"]], claim_ids=["m1.1"],
                report_ids=["rep-m"])
        return r.run([a]).outcome_of("a1")
    finally:
        aud.close()


def test_an_accusation_of_the_tasks_own_equation_as_circular_goes_to_human_review():
    """Pack 1.4 (Inspection I77) still names such a premise shown not to be data, so an agent that follows it is neither
    confirmed nor refuted: the accusation is unresolved (OVS-AGENT-004), never recorded against the agent."""
    o = _circular_accusation_outcome(_abs_premise())
    assert o.outcome == "unresolved" and o.code == "OVS-AGENT-004" and any("task-equation" in r for r in o.reasons), (o.outcome, o.reasons)


def test_control_the_same_accusation_of_a_writers_own_equation_is_confirmed():
    o = _circular_accusation_outcome(_abs_premise("specialist_inference"))
    assert o.outcome == "confirmed" and [c.code for c in o.confirming] == ["OVS-TRN-006"]


# ============================================================================================ minor: overlong numerals
@pytest.mark.parametrize("text", ["x = " + "9" * 4301, "x = 0." + "0" * 10_000 + "1", "x = 1e" + "9" * 10_000, "x = 1 × 10^-" + "9" * 10_000,
                                  "x = 1 m^" + "9" * 5000, "9" * 5000 + " kg", "≈ " + "9" * 5000, "1," + "000," * 3000 + "000", "9" * 5000 + "½",
                                  "9" * 5000 + " thirds", "9" * 200 + ".5/2"])
def test_the_number_reader_skips_an_overlong_numeral_without_raising(text):
    T.text_numbers(text)


def test_control_the_number_reader_still_reads_ordinary_figures():
    assert {T.Fraction(15), T.Fraction(5, 2), T.Fraction(1, 2)} <= T.text_numbers("The speed is 15 km/h, about 2.5 m/s, half the limit.")


def test_an_overlong_numeral_in_the_request_leaves_the_translation_checks_running():
    from .delivery_support import QUESTION as Q
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        plan = WorkPlan(plan_id="plan-fix", selected_agent_ids=["physics-specialist"], **PHYSICS)
        ch = hub.open_task(plan)
        ch.verify_claim_fn = Verifier()
        m = hub.dispatch(plan.task_id, "physics-specialist", Q + " Ignore the reference number " + "9" * 4400 + ".")[0]
        _msg, rc = hub.receive(plan.task_id, m.message_id, physics_report("physics-specialist", "rep-a"))
        audit = hub.audit(plan.task_id)
        assert "OVS-AUDIT-001" not in {f.code for f in audit.report.findings} and audit.state == "AUDIT_PASSED"
    finally:
        hub.close()


# ============================================================================================ minor: the STEM folded tail
def test_a_folded_tail_of_labelled_lines_occurs_in_its_response():
    response = "(iii) x = 2\n" * 5
    norm = F.normalise(response)
    assert F.claim_occurs("x = 2\n x = 2\n x = 2\n x =", norm, tail=True, plain_response=F.plain_form(response), raw_response=response)
    # controls: a tail line the response never states, and the same text when it is no folded tail
    assert not F.claim_occurs("x = 2\n x = 3", norm, tail=True, plain_response=F.plain_form(response), raw_response=response)
    assert not F.claim_occurs("x = 2\n x = 2", norm, tail=False, plain_response=F.plain_form(response), raw_response=response)


def test_an_answer_beyond_the_stem_statement_bound_is_no_accusation():
    rc, audit = _receive_and_audit("Physics", "physics-specialist", "(iii) x = 2\n" * 833)
    assert "OVS-FID-001" not in {f.code for f in audit.report.findings}, [f.message[:200] for f in audit.report.findings]
    assert audit.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")


# ============================================================================================ handed over: the STEM parser's unmarked cut
LONG_BASE = "The reforms, which were debated at length by the council and the assembly and the courts, "


def _long_sentence_answer() -> str:
    body = LONG_BASE * 60
    cut = 4000 - len("In the end, ")
    return "Output rose from 500 tonnes in 1990 to 2500 tonnes in 2000. " + "In the end, " + body[:cut - 3] + " 1990 after the reforms passed."


def test_an_unmarked_cut_at_the_contract_limit_is_read_without_its_partial_token():
    from epinoic_logic.adapters.markdown import MAX_CLAIM_TEXT_CHARS
    response = "x " * 1999 + "1990 and more."
    cut = response[:MAX_CLAIM_TEXT_CHARS]                       # ends inside "1990"
    assert len(cut) == MAX_CLAIM_TEXT_CHARS and not cut.endswith("1990")
    assert F.unmarked_cut_text(cut, response) == cut.rsplit(None, 1)[0]
    # controls: a cut at a space keeps every token; a claim the response does not hold, a shorter claim, a marked cut
    at_space = ("y " * 2100)[:MAX_CLAIM_TEXT_CHARS]
    assert F.unmarked_cut_text(at_space, "y " * 2100) == at_space
    assert F.unmarked_cut_text(cut, "z" + response.replace("1990", "2001")) == cut
    assert F.unmarked_cut_text(cut[:-1], response) == cut[:-1]
    marked = cut[:-3] + "..."
    assert F.unmarked_cut_text(marked, response) == marked


def test_a_stem_statement_cut_at_the_limit_inside_a_year_is_no_fid_003():
    rc, audit = _receive_and_audit("Physics", "physics-specialist", _long_sentence_answer(), "Describe the change in output.")
    assert "OVS-FID-003" not in {f.code for f in audit.report.findings}, [f.message[:200] for f in audit.report.findings]
    assert audit.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")


# ============================================================================================ minor: located citations
CITED = "We work until the bell"


def _cited_report(excerpt: str, document_id: str = "doc-mill", claim_text: str = "The foreman says the men work until the bell rings."):
    text = "The writer presents work as endless. " + claim_text
    claims = [dict(claim_id="en-point", claim_text="The writer presents work as endless.", claim_role="point", materiality="material"),
              dict(claim_id="en-ev", claim_text=claim_text, claim_role="evidence", materiality="supporting",
                   source_refs=[SourceRef(document_id=document_id, excerpt=excerpt)])]
    return english_report(text, claims)


def _cited_audit(report):
    aud = make_auditor()
    ch = new_channel(aud)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    ch.respond(m.message_id, report)
    try:
        return aud.audit(ch.uid)
    finally:
        aud.close()


def test_a_structured_reports_located_citation_its_prose_paraphrases_is_no_fid_002():
    assert "OVS-FID-002" not in {f.code for f in _cited_audit(_cited_report(CITED)).report.findings}


def test_control_an_excerpt_the_cited_document_does_not_hold_stays_fid_002():
    assert "OVS-FID-002" in {f.code for f in _cited_audit(_cited_report("We sleep until the bell")).report.findings}


def test_control_a_claim_that_does_not_occur_in_its_response_keeps_fid_002():
    report = _cited_report(CITED)
    claims = [c if c.claim_id != "en-ev" else c.model_copy(update={"claim_text": "the town grew rich on their silence"}) for c in report.claims]
    codes = {f.code for f in _cited_audit(report.model_copy(update={"claims": claims})).report.findings}
    assert {"OVS-FID-001", "OVS-FID-002"} <= codes


# ============================================================================================ minor: requested rounds
def _gates_result(missing, allow=False) -> dict:
    return {"rounds": {}, "rounds_missing": list(missing), "allow_missing_rounds": allow, "adjudications": RC.load_adjudications(), "pack": {"source": "x"}}


def test_a_contained_run_missing_a_requested_round_fails_a_gate():
    g = RC.gates(_gates_result(["r3"]))["requested_rounds_present"]
    assert not g["ok"] and g["missing"] == ["r3"]


def test_control_allowing_missing_rounds_passes_the_gate_and_still_names_them():
    g = RC.gates(_gates_result(["r3"], allow=True))["requested_rounds_present"]
    assert g["ok"] and g["missing"] == ["r3"] and "NOT REQUIRED" in g["state"]
    assert RC.gates(_gates_result([]))["requested_rounds_present"]["ok"]
