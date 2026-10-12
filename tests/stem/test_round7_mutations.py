"""The round-7 STEM mutations of the arena harness (scripts/arena/stem_mutations.py) on the genuine round-7 answers: each
of the 15 is named with its code on the claim that carries the injected fault, and the genuine answer stays clean.
Seven were not named when the STEM branches first read the round-7 answers; each is named by a reading of what the
answer writes, never by loosening what counts as named:

* bi-t13 (slip and substitution): a word formula in brackets (``(final − initial) ÷ initial × 100 = (80 − 40) ÷ 40 × 100
  = 100%``) ended the run, so the arithmetic was never read;
* ph-t13 (substitution in the formula line): a line that substitutes into the preceding relation is a step with the
  written values (tests/stem/test_round7_false_errors.py);
* maa-t13 (substitution): ``a = dv/dt = 6 − 9t`` then ``At t = 1: a = 6 − 6(1)``: the formula the answer states through a
  derivative is set against the evaluation it writes;
* maa-t13 (slip): ``∫6t dt = 6t²``: an indefinite integral of a polynomial is checked through the derivative of the
  stated antiderivative (the STEM pack differentiates by the power rule; the engine decides the identity);
* maa-p7b (substitution): ``800 = 1600 e^(−5k)`` then ``e^(−8k) = 1/2``: a step in which the unknown appears only in
  powers of e is read in ``u = e^(−k) > 0``;
* cs-t13 (substitution in the update rule): ``low = mid + 4`` then "mid = 1 gives 3 < 9, so low moves to 2": a trace
  step is read against the update rule stated for its variable;
* the harness's marker for a substitution now stays inside one statement: it stops at the end of its sentence and leaves
  a closing mark annotation out ("6 − 9t  M1" is "6 − 9t"), as every claim does."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.translate.contracts import SuppliedText

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import stem_mutations as sm  # noqa: E402

R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))
SPEC: dict[str, dict] = R7["specialists"]
STEM_TASKS = sorted(tid for tid, it in SPEC.items() if default_registry().for_subject(it["subject"])[0].key in sm.STEM_BRANCHES)
KEY = b"round7-stem-mutations-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
MATH = "Mathematics: Analysis and Approaches"


def receive(subject: str, answer: str, request: str = "Answer the question.", docs=()):
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent],
                           allowed_document_ids=[d.document_id for d in docs]))
    m, _, _ = hub.dispatch("t", agent, request, list(docs))
    reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return reply, rc


def engine_errors(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]


def norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def _docs(tid: str) -> list[SuppliedText]:
    it = SPEC[tid]
    docs = [SuppliedText(**t) for t in it.get("supplied_texts", [])]
    if it.get("peer_of"):
        peer = SPEC[it["peer_of"]]
        docs.append(SuppliedText(document_id=f"peer:{it['peer_of']}", title="peer report", author=peer["agent_id"], text=peer["response_text"]))
    return docs


CASES = [(tid, kind) for tid in STEM_TASKS for kind in sm.STEM_MUTATIONS if sm.mutate_stem(SPEC[tid]["response_text"], SPEC[tid]["question"], kind)]


def test_round_7_has_fifteen_stem_mutations():
    assert len(CASES) == 15
    assert {tid for tid, _k in CASES} == {"bi-t13", "cs-t13", "maa-p7b", "maa-t13", "mai-t13", "ph-p7b", "ph-t13"}


@pytest.mark.parametrize("tid,kind", CASES)
def test_each_round7_stem_mutation_is_named_on_its_claim(tid, kind):
    it = SPEC[tid]
    inj = sm.mutate_stem(it["response_text"], it["question"], kind)
    _r, genuine = receive(it["subject"], it["response_text"], it["question"], _docs(tid))
    reply, rc = receive(it["subject"], inj.text, it["question"], _docs(tid))
    claims = reply.payload["claims"]
    injected = {c["claim_id"] for c in claims if norm(inj.marker) in norm(c["claim_text"])}
    assert injected, (inj.marker, [c["claim_text"][:60] for c in claims])  # the marker lies inside one claim
    before = {(f.code, tuple(sorted(f.claim_ids)), f.message) for f in list(genuine.findings) + list(genuine.structural_findings)}
    named = [f for f in list(rc.findings) + list(rc.structural_findings) if f.code in inj.expected and set(f.claim_ids) & injected
             and (f.code, tuple(sorted(f.claim_ids)), f.message) not in before]
    assert named, (tid, kind, sorted(injected), [(f.code, f.claim_ids) for f in rc.findings if f.code.startswith("INT-SUBJ")])
    assert not engine_errors(genuine)


def test_the_substitution_marker_stays_inside_one_statement():
    q = "Find the rate at t = 8 h and at t = 6 h."
    assert sm.mutate_stem("a = dv/dt = 6 − 6t  M1\nAt t = 1: a = 6 − 6(1) = 0", q, "stem_substitution").marker == "6 − 9t"
    assert sm.mutate_stem("800 = 1600 e^(−8k)  M1\ne^(−8k) = 1/2", q, "stem_substitution").marker == "1600 e^(−5k)"
    crossing = sm.mutate_stem("so low = mid + 6 is safe. In a list, mid = 1 gives 3.", "Use 6 items.", "stem_substitution")
    assert crossing.marker == "mid + 9 is safe"


def test_a_bracketed_word_formula_is_read_with_its_arithmetic():
    line = "(a) Percentage change = (final − initial) ÷ initial × 100 = (80 − 40) ÷ 40 × 100 = 100%, an increase of 100% [1]"
    doc = build_document(line, None, "biology")
    assert [r.kind for r in doc.checks] == ["eq"] and line[doc.checks[0].start:doc.checks[0].end] == "(80 − 40) ÷ 40 × 100 = 100%"
    assert not engine_errors(receive("Biology", line)[1])
    for wrong in (line.replace("= 100%,", "= 400%,"), line.replace("(80 − 40)", "(80 − 70)")):
        assert engine_errors(receive("Biology", wrong)[1]), wrong
    for prose in ("The values (see the table) are 3 and 4.", "It rose (mainly water) by 20%."):
        assert not [s for s in build_document(prose, None, "biology").spans.spans if s.kind == "math_run"]


def test_a_step_with_the_unknown_only_in_powers_of_e_is_read_in_one_positive_variable():
    good = "800 = 1600 e^(−8k)  M1\ne^(−8k) = 1/2"
    doc = build_document(good, None, "mathematics_aa")
    [step] = [r for r in doc.checks if r.kind == "alg"]
    assert step.positive == ("e^(−k)",) and step.statement_ids == ("s1.1", "s1.2")
    assert not engine_errors(receive(MATH, good)[1])
    [err] = engine_errors(receive(MATH, good.replace("e^(−8k)  M1", "e^(−5k)  M1"))[1])
    assert set(err.claim_ids) == {"m1.1", "m1.2"}
    # two unknowns in the exponent, or the unknown outside a power of e: no step is read
    assert not [r for r in build_document("½C0 = C0 e^(−kT), so e^(−kT) = ½", None, "mathematics_aa").relations if r.kind == "alg"]
    assert not [r for r in build_document("e^(−8k) = 1/2\n−8k = ln(1/2)", None, "mathematics_aa").relations if r.kind == "alg" and r.positive]


def test_a_written_evaluation_is_set_against_the_formula_the_answer_states():
    good = "(a) a = dv/dt = 6 − 6t\nAt t = 1: a = 6 − 6(1) = 0"
    assert not engine_errors(receive(MATH, good, "(a) Find the acceleration when t = 1.")[1])
    [err] = engine_errors(receive(MATH, good.replace("6 − 6t", "6 − 9t"), "(a) Find the acceleration when t = 1.")[1])
    assert set(err.claim_ids) == {"m1.1", "m1.2"} and "stem_substitution" in err.message
    # a formula with ± has two values: a written root takes one of them and is no evaluation to check
    roots = "Here a = 2, b = −3 and c = −1.\nΔ = b² − 4ac = 17\nx = (−b ± √Δ)/(2a) = (3 ± √17)/4\n\nSo x = (3 + √17)/4 ≈ 1.78."
    assert not [r for r in build_document(roots, "Solve 2x² − 3x − 1 = 0.", "mathematics_aa").relations if r.kind == "sub" and r.evaluate and r.formula]


@pytest.mark.parametrize("text, ok", [("∫6t dt = 3t²", True), ("∫6t dt = 6t²", False), ("∫(6t − 3t²) dt = 3t² − t³ + C", True),
                                      ("∫(6t − 3t²) dt = 3t² − 2t³ + C", False), ("$\\int 6t\\,dt = 3t^2$", True), ("∫ x dx = x²/2", True)])
def test_an_indefinite_integral_of_a_polynomial_is_checked_through_its_antiderivative(text, ok):
    doc = build_document(text, None, "mathematics_aa")
    [check] = [r for r in doc.checks if r.kind == "alg"]
    assert "antiderivative" in check.reason and "power rule" in check.reason
    assert (not engine_errors(receive(MATH, text)[1])) is ok


@pytest.mark.parametrize("text", ["∫₀¹ x dx = 1/2", "d/dx (x²) = 2x", "∫ sin x dx = −cos x", "∫ 2kx dx = kx²"])
def test_other_calculus_stays_outside_the_encodings(text):
    doc = build_document(text, None, "mathematics_aa")
    assert not doc.checks and any(r.outcome == "undecided" for r in doc.relations)


def test_a_trace_step_is_read_against_the_update_rule_of_its_variable():
    text = ("If items[mid] < target, every item to the left of mid is smaller too, so low = mid + 1 is safe. "
            "For example, with [9, 3, 7] and target 9: mid = 1 gives 3 < 9, so low moves to 2; the next middle item is 7, so low moves to 3.")
    doc = build_document(text, None, "computer_science")
    [step] = [r for r in doc.checks if r.kind == "sub" and r.evaluate]
    assert text[step.start:step.end] == "mid = 1 gives 3 < 9, so low moves to 2"  # the second step states no value of mid: not read
    assert not engine_errors(receive("Computer Science", text)[1])
    [err] = engine_errors(receive("Computer Science", text.replace("mid + 1", "mid + 4"))[1])
    assert set(err.claim_ids) == {"c1.1", "c1.2"}
    # the reading belongs to the Computer Science branch
    assert not [r for r in build_document(text, None, "physics").relations if r.kind == "sub" and r.evaluate]
