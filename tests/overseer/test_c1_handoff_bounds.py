"""Round-8 clearance (integrated round c1), handoff fixer: word and paragraph bounds the channel and the transfer auditor
read the same way (the core fixer's handoff item 5 and the parsers fixer's handoff item 1).

* rule ``declined-bound``: a bound set on a deliverable the answer declines (ge-t14, an academic-integrity decline against
  "about 900 words") is recorded not applicable (satisfied None, method ``not_checkable``, no formal result, no
  INT-REQ-005), naming the declining sentence; the auditor accepts exactly that record exactly when
  ``channel.bus.withheld_deliverable`` reads a decline in the journaled response, so a channel that suspends a bound on an
  answer that declines nothing is OVS-FORM-004;
* rule ``per-part-bound``: "Write no more than 250 words for each answer" (ps-t14) is measured on each answer, the longest
  for a maximum (216 against 250; the whole reply is 441), by one function both call
  (``request_parser.bound_word_measure``), so a channel that measures the whole reply instead is OVS-FORM-003;
* "about N words": a measure outside the band but within a quarter of N is INT-REQ-005 at warning, a gross miss an error, on
  the receipt and in the auditor's rule on its own recount (``request_parser.word_bound_severity``, rule about-band); a hard
  bound breached at warning is still RCPT-004.

The recorded replies are the round's own (``tests/channel/data/c1_core_material.json``)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import epinoic_logic.channel.bus as bus
from epinoic_logic.channel.bus import DECLINED_BOUND_PREFIX, TranslatorChannel, withheld_deliverable
from epinoic_logic.channel.contracts import Constraint, ConstraintResult
from epinoic_logic.channel.request_parser import (about_band, answer_parts, bound_word_measure, extract_constraints, measure_answer_words,
                                                  per_part_bound, word_bound_severity)
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.overseer.checks.formal import declined_bound
from epinoic_logic.translate.contracts import SuppliedText

from ..core_hostile import SHAPES, one, sweep
from ..timing import measure
from .conftest import findings, make_auditor, new_channel

ROOT = Path(__file__).resolve().parents[2]
C1 = json.loads((ROOT / "tests" / "channel" / "data" / "c1_core_material.json").read_text(encoding="utf-8"))
SPEC = C1["specialists"]


def _deliver(task: str, text: str | None = None, *, question: str | None = None):
    """``(auditor, observed channel, receipt)`` of one recorded reply delivered through an observed channel."""
    item = SPEC[task]
    texts = [SuppliedText(**{k: v for k, v in t.items() if k in ("document_id", "title", "author", "text")}) for t in item.get("supplied_texts", [])]
    auditor = make_auditor()
    plan = WorkPlan(plan_id=f"plan-{task}", request_id=f"req-{task}", task_id=f"task-{task}", subject=item["subject"],
                    task_type=item.get("task_type") or "short_answer", selected_agent_ids=[item["agent_id"], "combinator"],
                    allowed_document_ids=[t.document_id for t in texts])
    ch = new_channel(auditor, plan)
    m, _req, _rq = ch.request("router", item["agent_id"], question or item["question"], texts)
    _reply, rc = ch.respond_text(m.message_id, item["response_text"] if text is None else text, agent_id=item["agent_id"], report_id=f"rep-{task}-0")
    return auditor, ch, rc


def _bound_findings(audit) -> list:
    return [f for f in audit.report.findings if f.code in ("OVS-FORM-002", "OVS-FORM-003", "OVS-FORM-004", "OVS-RES-007")
            or (f.code == "OVS-RCPT-004" and "INT-REQ-005" in f.message)]


# ------------------------------------------------------------------------------------------- rule declined-bound


def test_a_bound_on_a_declined_deliverable_is_not_applicable_and_the_audit_agrees():
    auditor, ch, rc = _deliver("ge-t14")
    found = withheld_deliverable(SPEC["ge-t14"]["response_text"])
    assert found is not None and found[0] == "declined"
    bounds = [c for c in rc.constraint_results if c.detail.startswith(DECLINED_BOUND_PREFIX)]
    assert bounds and len(bounds) == len([c for c in rc.constraint_results if c.method != "deterministic"])
    assert all(c.satisfied is None and c.method == "not_checkable" and c.formal_result_id is None and "I can't write the analysis" in c.detail for c in bounds)
    assert not [f for f in rc.findings if f.code == "INT-REQ-005"]
    assert not [f for f in rc.findings if f.severity == "error"], [(f.code, f.message[:120]) for f in rc.findings if f.severity == "error"]
    audit = auditor.audit(ch.uid)
    assert not _bound_findings(audit), [(f.code, f.message[:200]) for f in _bound_findings(audit)]
    assert all(declined_bound(c, SPEC["ge-t14"]["response_text"]) for c in bounds)


def test_control_a_bound_recorded_not_applicable_on_an_answer_that_declines_nothing_is_named(monkeypatch):
    """A channel that suspends a bound on an answer that declines nothing (the same record on ps-t14, which answers both
    parts) is OVS-FORM-004: the bound has no formal result, and the auditor reads no decline in the response."""
    real = TranslatorChannel._constraints

    def suspend(self, req, report, view=None):
        results, ids = real(self, req, report, view=view)
        out = [ConstraintResult(constraint_id=c.constraint_id, satisfied=None, method="not_checkable",
                                detail=f"{DECLINED_BOUND_PREFIX} ('none'); measured 1 words; bound max_words 250") if c.method == "formal" else c for c in results]
        return out, []

    monkeypatch.setattr(TranslatorChannel, "_constraints", suspend)
    auditor, ch, rc = _deliver("ps-t14")
    assert any(c.detail.startswith(DECLINED_BOUND_PREFIX) for c in rc.constraint_results)
    audit = auditor.audit(ch.uid)
    named = findings(audit, "OVS-FORM-004")
    assert named and any("declined-bound" in f.message for f in named), [(f.code, f.message[:200]) for f in audit.report.findings]
    assert not declined_bound(next(c for c in rc.constraint_results if c.detail.startswith(DECLINED_BOUND_PREFIX)), SPEC["ps-t14"]["response_text"])


def test_control_a_decline_whose_bound_is_charged_as_before_also_passes_the_audit(monkeypatch):
    """The auditor accepts the not-applicable record, it does not demand it: a channel that decides the bound on a decline
    (the first pass's behaviour) still passes R2 (the bound has its formal result and its INT-REQ-005)."""
    monkeypatch.setattr(bus, "withheld_deliverable", lambda response: None)
    auditor, ch, rc = _deliver("ge-t14")
    assert all(c.method == "formal" for c in rc.constraint_results if c.constraint_id in ("c1", "c2"))
    audit = auditor.audit(ch.uid)
    assert not [f for f in _bound_findings(audit) if f.code != "OVS-RCPT-004"], [(f.code, f.message[:200]) for f in _bound_findings(audit)]


# ------------------------------------------------------------------------------------------ rule per-part-bound


def test_a_bound_on_each_answer_is_measured_on_each_answer_and_the_audit_agrees():
    auditor, ch, rc = _deliver("ps-t14")
    [c] = [c for c in rc.constraint_results if c.method == "formal"]
    assert c.satisfied is True and "measured 216 words" in c.detail and "(a) 216, (b) 211" in c.detail
    assert not [f for f in rc.findings if f.code == "INT-REQ-005" or f.severity == "error"], [(f.code, f.message[:120]) for f in rc.findings]
    audit = auditor.audit(ch.uid)
    assert not _bound_findings(audit), [(f.code, f.message[:200]) for f in _bound_findings(audit)]


def test_control_a_channel_measuring_the_whole_reply_for_a_bound_on_each_answer_is_named(monkeypatch):
    """The round-7 reading (the whole reply, over 400 words, against 250 for each answer) is FORM-003 in R2: the auditor recounts
    each answer with the same function, so a channel that measures otherwise is decided on a problem the response does
    not yield."""
    whole = bus.bound_word_measure

    def whole_reply(response, c, *, request_text, view=None, measure=None):
        return whole(response, c.model_copy(update={"text": "no more than 250 words"}), request_text=request_text, view=view, measure=measure)

    monkeypatch.setattr(bus, "bound_word_measure", whole_reply)
    auditor, ch, rc = _deliver("ps-t14")
    [c] = [c for c in rc.constraint_results if c.method == "formal"]
    whole_words = measure_answer_words(SPEC["ps-t14"]["response_text"])[0]
    assert whole_words > 400 and c.satisfied is False and f"measured {whole_words} words" in c.detail
    audit = auditor.audit(ch.uid)
    named = findings(audit, "OVS-FORM-003")
    assert named and any("MEASURED" in f.message for f in named), [(f.code, f.message[:200]) for f in audit.report.findings]


def test_a_longer_answer_breaches_a_bound_on_each_answer_and_a_short_one_does_not():
    """Each answer is held to the bound: one part over 250 words breaches it although the whole reply is under twice the
    bound, and the receipt names the part's measure; the whole-reply reading is kept when the parts cannot be told apart."""
    item = SPEC["ps-t14"]
    long_b = item["response_text"].replace("(b) [6]\n", "(b) [6]\n\n" + " ".join(["Reinforcement explains the pattern."] * 12) + "\n", 1)
    _auditor, _ch, rc = _deliver("ps-t14", long_b)
    [c] = [c for c in rc.constraint_results if c.method == "formal"]
    parts = answer_parts(long_b, item["question"])
    a_words, b_words = (measure_answer_words(t)[0] for _label, t in parts)
    assert a_words <= 250 < b_words and a_words + b_words < 500
    assert c.satisfied is False and f"measured {b_words} words" in c.detail and f"(a) {a_words}, (b) {b_words}" in c.detail, c.detail
    [f] = [f for f in rc.findings if f.code == "INT-REQ-005"]
    assert f.severity == "error"
    unlabelled = item["response_text"].replace("(a) [6]", "Part one").replace("(b) [6]", "Part two")
    [c2] = [c for c in _deliver("ps-t14", unlabelled)[2].constraint_results if c.method == "formal"]
    assert c2.satisfied is False and "cannot be told apart" in c2.detail and f"measured {measure_answer_words(unlabelled)[0]} words" in c2.detail


@pytest.mark.parametrize("request_text,per_part", [
    ("Write no more than 250 words for each answer.", True),
    ("For each answer, write no more than 200 words.", True),
    ("Each answer should be no more than 150 words.", True),
    ("Answer in about 300 words per question.", True),
    ("Two answers of no more than 250 words each.", True),
    ("Write between 300 and 400 words for each part.", True),
    ("Write no more than 250 words.", False),
    ("Write no more than 250 words in total for each answer.", False),
    ("Answer each question. Write no more than 300 words.", False),
    ("Write at most 100 words each day of the week.", False),
])
def test_the_scope_of_a_word_bound_is_read_from_the_request(request_text, per_part):
    cs = [c for c in extract_constraints(request_text) if c.kind.endswith("words")]
    assert cs and all(per_part_bound(c) is per_part for c in cs), [(c.kind, c.text) for c in cs]


def test_the_answer_is_cut_at_the_requests_own_labels_in_order():
    request = "(a) Explain one effect. [4] (b) Evaluate the policy. [6] Write no more than 100 words for each answer."
    answer = "(a) [4]\nOne effect.\n1. a point\n2. another\n\n(b) [6]\nThe policy works. (a) as said above.\n"
    parts = answer_parts(answer, request)
    assert [p[0] for p in parts] == ["a", "b"] and "1. a point" in parts[0][1] and "(a) as said above" in parts[1][1]
    assert answer_parts("No labels at all here.", request) == []
    assert answer_parts(answer, "Explain one effect. Write no more than 100 words for each answer.") == []
    [c] = extract_constraints(request)
    each = [measure_answer_words(t)[0] for _label, t in parts]
    assert bound_word_measure(answer, c, request_text=request)[0] == max(each) < measure_answer_words(answer)[0]
    assert bound_word_measure(answer, c.model_copy(update={"kind": "min_words"}), request_text=request)[0] == min(each)


@pytest.mark.parametrize("answer,cut", [
    ("1. X is caused by many things.\n1. first point\n2. second point\n\n2. Y is caused by other things.", True),   # a tight list inside part 1
    ("1. X is caused by many things.\n\n1. first point\n\n2. second point\n\n2. Y is caused by other things.", False),  # a list set out in paragraphs
    ("2. Y.\n\n1. X.", False),                                     # out of the request's order
    ("1. X and Y together.", False),                                 # a part left out
    ("Intro.\n\n1. X.\n\n2. Y.", True),
])
def test_the_parts_are_never_guessed(answer, cut):
    """A label that also numbers a list set out in paragraphs, labels out of order and a part left out give no cut: the whole
    answer is measured, never a laxer reading of a bound on each answer."""
    request = "1. Explain X. 2. Explain Y. Write no more than 100 words for each answer."
    [c] = extract_constraints(request)
    parts = answer_parts(answer, request)
    assert bool(parts) is cut, parts
    measured, _n, _e, note = bound_word_measure(answer, c, request_text=request)
    if not cut:
        assert measured == measure_answer_words(answer)[0] and "cannot be told apart" in note


# --------------------------------------------------------------------------------------------- about N words


def _about(target: int):
    item = SPEC["ps-t14"]
    question = item["question"].replace("Write no more than 250 words for each answer.", f"Write about {target} words in total.")
    return _deliver("ps-t14", question=question)


def test_a_measure_just_outside_an_about_band_is_a_warning_and_the_audit_agrees():
    """427 words for "about 380 words" (band 342 to 418): outside the band, within a quarter of 380, so a warning."""
    auditor, ch, rc = _about(380)
    breached = [c for c in rc.constraint_results if c.satisfied is False]
    assert breached and all("within a quarter of the target" in c.detail for c in breached)
    named = [f for f in rc.findings if f.code == "INT-REQ-005"]
    assert named and all(f.severity == "warning" for f in named)
    audit = auditor.audit(ch.uid)
    assert not _bound_findings(audit), [(f.code, f.message[:200]) for f in audit.report.findings]


def test_a_gross_miss_of_an_about_band_is_an_error_and_the_audit_agrees():
    """427 words for "about 300 words": more than a quarter over the target, so an error, as for a hard bound (and as the round-5
    regression test of en-t10, 146 words for "about 250", requires)."""
    auditor, ch, rc = _about(300)
    named = [f for f in rc.findings if f.code == "INT-REQ-005"]
    assert named and all(f.severity == "error" for f in named)
    assert not any("within a quarter of the target" in c.detail for c in rc.constraint_results)
    audit = auditor.audit(ch.uid)
    assert not _bound_findings(audit), [(f.code, f.message[:200]) for f in audit.report.findings]


def test_control_a_gross_miss_of_an_about_band_reported_at_warning_is_named(monkeypatch):
    """The live check accepts a warning for a band (its exact severity depends on the measure); R2 recounts and names a gross miss
    the channel lowered to a warning (rule about-band)."""
    monkeypatch.setattr(bus, "word_bound_severity", lambda c, measured=None: "warning")
    auditor, ch, rc = _about(300)
    assert all(f.severity == "warning" for f in rc.findings if f.code == "INT-REQ-005")
    named = [f for f in findings(auditor.audit(ch.uid), "OVS-RCPT-004") if "about-band" in f.message]
    assert named, [(f.code, f.message[:200]) for f in auditor.audit(ch.uid).report.findings]


def test_control_a_hard_bound_breached_is_still_an_error_and_lowering_it_is_named(monkeypatch):
    item = SPEC["ps-t14"]
    question = item["question"].replace("Write no more than 250 words for each answer.", "Write no more than 300 words.")
    _auditor, _ch, rc = _deliver("ps-t14", question=question)
    [f] = [f for f in rc.findings if f.code == "INT-REQ-005"]
    assert f.severity == "error"
    monkeypatch.setattr(bus, "word_bound_severity", lambda c, measured=None: "warning")
    auditor, ch, rc = _deliver("ps-t14", question=question)
    [f] = [f for f in rc.findings if f.code == "INT-REQ-005"]
    assert f.severity == "warning"
    audit = auditor.audit(ch.uid)
    assert [x for x in findings(audit, "OVS-RCPT-004") if "INT-REQ-005" in x.message], [(x.code, x.message[:200]) for x in audit.report.findings]


def test_the_band_and_its_severity_are_read_from_the_bound():
    about, hard, para = (extract_constraints(t) for t in ("Write about 900 words.", "Write no more than 900 words.", "Write no more than two paragraphs."))
    assert all(about_band(c) for c in about) and not any(about_band(c) for c in hard)
    assert [word_bound_severity(c, m) for c in about for m in (675, 1125, 674, 1126, None)] == ["warning", "warning", "error", "error", "error"] * 2
    assert all(word_bound_severity(c, 2000) == "error" for c in hard)
    assert all(word_bound_severity(c) == "warning" for c in para)
    assert word_bound_severity(None) == "error"


# ------------------------------------------------------------------------------------- the readers stay linear


def _bound_entries(text: str):
    scoped = Constraint(constraint_id="c1", kind="max_words", value="250", text="no more than 250 words for each answer")
    shortest = scoped.model_copy(update={"kind": "min_words"})
    yield "extract_constraints", lambda: extract_constraints(text)
    yield "extract_constraints after a bound", lambda: extract_constraints("Write no more than 250 words" + text)
    yield "extract_constraints before a bound", lambda: extract_constraints("Each answer " + text + " no more than 250 words.")
    yield "answer_parts", lambda: answer_parts(text, "(a) Explain. (b) Explain. " + text)
    yield "bound_word_measure (max)", lambda: bound_word_measure("(a) x\n" + text + "\n(b) y", scoped, request_text="(a) Explain. (b) Explain.")
    yield "bound_word_measure (min)", lambda: bound_word_measure(text, shortest, request_text="(a) Explain. (b) Explain. " + text)
    yield "per_part_bound", lambda: per_part_bound(scoped.model_copy(update={"text": text[:1000]}))
    yield "about_band", lambda: about_band(scoped.model_copy(update={"text": text[:1000]}))
    yield "withheld_deliverable", lambda: withheld_deliverable(text)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_bound_readers(shape):
    """Every reader the bound rules added or call, fed the standard hostile inputs (``tests/core_hostile.py``) under the
    sweep's CPU-time bound per call."""
    assert not sweep(_bound_entries, texts=one(shape))


@pytest.mark.parametrize("name,request_text,answer", [
    ("scope words after the bound", "Write no more than 250 words" + " for each" * 2_200 + " x", "(a) [6]\n" * 2_500),
    ("scope words before the bound", "each answer " * 1_600 + "no more than 250 words.", "word " * 4_000),
    ("part labels", "(a) Explain. (b) Explain. " * 770 + "Write no more than 250 words for each answer.", "(a)\n(b)\n" * 2_500),
    ("line breaks", "\n" * 20_000 + "(a) x. (b) y. Write no more than 250 words for each answer.", "\n" * 20_000 + "(a) x\n(b) y"),
])
def test_the_bound_readers_are_linear_on_their_own_worst_inputs(name, request_text, answer):
    def run():
        for c in extract_constraints(request_text):
            bound_word_measure(answer, c, request_text=request_text)
        return len(answer_parts(answer, request_text))
    timing = measure(run, bound=4.0, repeat=3, label=f"bound readers, {name}")
    assert timing.holds, timing
