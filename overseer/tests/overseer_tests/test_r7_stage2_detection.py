"""Round-8 r7 stage 2: three losses of detection the contained run of the round-8 commit showed against the published base,
each fixed at its cause (``overseer/docs/OVERSEER_DESIGN.md`` Decision 111). Every test here runs without the recorded rounds; the
last two replay the recorded r7 chemistry target when ``EPINOIC_ARENA_ROUNDS`` names a directory that holds r7.

* rule ``declined-bound`` (Decision 96) accepted a bound recorded not applicable on its shape and the decline alone, so the
  measurement the record states ("measured 7 words") was never compared with the recount. R2 now recounts first and
  names a declined record whose stated count the response does not yield as OVS-FORM-003 (the T5c fault on a declining
  answer: the word count measured as 7 whatever the answer says);
* tampering T5 flipped only a definitive formal_status, so on a receipt whose every bound is declined it presented the
  genuine receipt and the no-op counted as a missed tampering. It now presents a declined bound as decided and
  satisfied (a decline hidden as a passed bound: OVS-RCPT-001), skips only when there is nothing to alter, and never
  presents an unchanged receipt;
* rule ``derived-figures`` (Decision 90) traced a figure through readings its own text forbids: the reciprocal of a
  precision end (1/12.5 for "12 mm³" traced a planted 80 mm³ → 0.08 conversion) and a precision end of a supplied text
  (0.005 of "±0.01 s" traced a planted 5.0 cm³ → 0.0050 dm³ conversion). A reciprocal now comes only from a figure a text
  writes, and a request's or supplied text's figures count only as written (rule ``task-and-supplied``, narrowed)."""
from __future__ import annotations

import json
import os
import sys
from fractions import Fraction
from pathlib import Path

import pytest

import epinoic_logic.channel.bus as bus
from epinoic_logic.api.channel import DECLINED_BOUND_PREFIX, TranslatorChannel, measure_answer_words
from epinoic_logic.api.channel import ConstraintResult
from epinoic_overseer.checks.translation import _as_stated, _as_written, untraced_content

from .conftest import findings
from .test_c1_handoff_bounds import SPEC, _bound_findings, _deliver
from .test_clearance_c1_overseer import _figures_ir

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import tamper as T  # noqa: E402

ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None
HAS_R7 = ROUNDS is not None and (ROUNDS / "r7" / "specialists" / "ch-t13.json").is_file()
needs_r7 = pytest.mark.skipif(not HAS_R7, reason="the recorded round r7 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")


# ------------------------------------------------------------------------------ rule declined-bound: the stated count


def _declined(rc) -> list:
    return [c for c in rc.constraint_results if str(c.detail or "").startswith(DECLINED_BOUND_PREFIX)]


def test_a_declined_bound_whose_stated_count_is_the_recount_is_accepted():
    auditor, ch, rc = _deliver("ge-t14")
    bounds = _declined(rc)
    assert bounds and all("; measured " in c.detail for c in bounds)
    audit = auditor.audit(ch.uid)
    assert not _bound_findings(audit), [(f.code, f.message[:200]) for f in _bound_findings(audit)]


def test_a_declined_bound_measured_as_seven_whatever_the_answer_says_is_form003_measured(monkeypatch):
    """T5c on a declining answer: the channel's measure patched to 7 (as the tampering does). The bound is still recorded not
    applicable (the decline is genuine), but its detail states 7 words; R2's recount with the channel's own function gives
    the answer's real length, so the record's statement is FORM-003 naming MEASURED. Before, R2 skipped the record whole."""
    monkeypatch.setattr(bus, "measure_answer_words", lambda text, excludes=(), view=None: (7, 0, 0))
    auditor, ch, rc = _deliver("ge-t14")
    bounds = _declined(rc)
    assert bounds and all("; measured 7 words; bound " in c.detail for c in bounds)
    monkeypatch.undo()
    audit = auditor.audit(ch.uid)
    named = findings(audit, "OVS-FORM-003")
    assert named and all("MEASURED" in f.message and "declined-bound" in f.message for f in named), \
        [(f.code, f.message[:200]) for f in audit.report.findings]
    real = measure_answer_words(SPEC["ge-t14"]["response_text"])[0]
    assert any("the record states 7" in f.message and f"the recount gives {real}" in f.message for f in named) or real == 7


def test_a_declined_bound_that_states_no_count_is_form003(monkeypatch):
    """A not-applicable record whose detail drops the measurement states nothing R2 can recount: FORM-003, never accepted
    on its shape alone."""
    real = TranslatorChannel._constraints

    def no_count(self, req, report, view=None):
        results, ids = real(self, req, report, view=view)
        out = [c.model_copy(update={"detail": c.detail.split("; measured ")[0]}) if str(c.detail or "").startswith(DECLINED_BOUND_PREFIX) else c
               for c in results]
        return out, ids

    monkeypatch.setattr(TranslatorChannel, "_constraints", no_count)
    auditor, ch, rc = _deliver("ge-t14")
    assert _declined(rc) and not any("; measured " in c.detail for c in _declined(rc))
    audit = auditor.audit(ch.uid)
    named = findings(audit, "OVS-FORM-003")
    assert named and any("the record states none" in f.message for f in named), [(f.code, f.message[:200]) for f in audit.report.findings]


# ------------------------------------------------------------------------------------- tampering T5 on a declined bound


def test_t5_presents_a_declined_bound_as_decided_and_the_clearance_fails_with_rcpt001():
    auditor, ch, rc = _deliver("ge-t14")
    assert _declined(rc) and not any(c.formal_status in ("ENTAILED", "COUNTEREXAMPLE") for c in rc.constraint_results)
    presented = T.t5_presented(rc)
    assert presented != rc
    changed = [p for p, c in zip(presented.constraint_results, rc.constraint_results) if p != c]
    assert len(changed) == 1 and changed[0].method == "formal" and changed[0].formal_status == "ENTAILED" and changed[0].satisfied is True
    clr = auditor.clearance(ch.uid, rc.message_id, receipt=presented)
    assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-001" in clr.codes, (clr.state, clr.codes)


def test_t5_still_flips_a_definitive_status_first():
    auditor, ch, rc = _deliver("ps-t14")
    [c] = [c for c in rc.constraint_results if c.method == "formal"]
    assert c.formal_status in ("ENTAILED", "COUNTEREXAMPLE")
    presented = T.t5_presented(rc)
    [p] = [p for p in presented.constraint_results if p.constraint_id == c.constraint_id]
    assert p.formal_status != c.formal_status and p.satisfied == (p.formal_status == "ENTAILED")
    assert [x for x in presented.constraint_results if x.constraint_id != c.constraint_id] == [x for x in rc.constraint_results if x.constraint_id != c.constraint_id]
    clr = auditor.clearance(ch.uid, rc.message_id, receipt=presented)
    assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-001" in clr.codes


def test_t5_never_presents_an_unchanged_receipt():
    """A receipt with neither a definitive status nor a not-applicable record has nothing T5 alters: SkipCase, so a no-op
    is never counted as a tampering (and so never as a miss)."""
    _auditor, _ch, rc = _deliver("ge-t14")
    only_det = rc.model_copy(update={"constraint_results": [ConstraintResult(constraint_id="c9", satisfied=True, method="deterministic", detail="present")]})
    with pytest.raises(T.SkipCase):
        T.t5_presented(only_det)


# ------------------------------------------------------------------------------------------- rule derived-figures


def test_the_reciprocal_of_a_precision_end_traces_nothing():
    """bi-t13: the answer writes "an increase of 12 mm³"; 12.5 is only the upper end of its stated precision, so 1/12.5 = 0.08
    is no figure of the texts. A translation that converts 80 mm³ to 0.08 on its own is named (OVS-TRN-005)."""
    answer = "The uptake rose by an increase of 12 mm³ between the two temperatures."
    prob, obj = _figures_ir("0.08")
    assert untraced_content(prob, obj, [answer], []) == [("P0", f"P0 uses the number {Fraction('0.08')}")]


def test_the_reciprocal_of_a_written_figure_is_still_traced():
    """The control: a figure the text writes (12.5, 8) still gives its reciprocal (Decision 90's reading)."""
    for answer, v in (("Divide each value by 12.5 to compare them.", "0.08"), ("Divide each value by 8.", "0.125")):
        prob, obj = _figures_ir(v)
        assert untraced_content(prob, obj, [answer], []) == [], (answer, v)


def test_a_precision_end_of_a_supplied_text_traces_nothing():
    """ch-t13: the supplied method states "stopwatch reading +/-0.01 s"; 0.005 is only the lower end of that stated precision,
    not a figure the supplied text states. A translation that converts 5.0 cm³ to 0.0050 dm³ on its own is named."""
    answer = "The volume of acid added was 5.0 cm³."
    supplied = ["Method: add the acid from a burette and start the stopwatch (stopwatch reading +/-0.01 s)."]
    prob, obj = _figures_ir("0.0050")
    assert untraced_content(prob, obj, [answer], [], supplied) == [("P0", f"P0 uses the number {Fraction('0.005')}")]
    prob, obj = _figures_ir("0.005")
    assert untraced_content(prob, obj, [answer], ["Find the rate."], []) == [("P0", f"P0 uses the number {Fraction('0.005')}")]


@pytest.mark.parametrize("value, supplied", [
    ("105", "| year | price | quantity |\n| 2025 | 1.90 | 105 |"),
    ("1.9", "| year | price | quantity |\n| 2025 | 1.90 | 105 |"),
    ("0.41", "41% of the sample responded."),
    ("3000000", "The town has 3 million residents."),
    ("10000", "The count is 1.0 × 10⁴ cells."),
    ("46379.41", "The account holds 46 379.41 euros."),
    ("0.01", "stopwatch reading +/-0.01 s"),
], ids=["table cell", "table cell decimal", "per cent", "scale word", "scientific", "spaced thousands", "written uncertainty"])
def test_a_figure_a_supplied_text_states_as_written_is_still_traced(value, supplied):
    """Rule task-and-supplied keeps every value a supplied text states as written (Decision 90's case of a supplied table's
    figure included); only its precision ends and conversions are no longer read."""
    prob, obj = _figures_ir(value)
    assert untraced_content(prob, obj, ["The answer uses the supplied data."], [], [supplied]) == [], (value, supplied)


def test_as_written_and_as_stated_read_no_precision_end():
    text = "stopwatch reading +/-0.01 s; 12 mm³; 41%; 3 million; 1.0 × 10⁴"
    assert Fraction(1, 200) not in _as_stated(text) and Fraction(25, 2) not in _as_stated(text)
    assert {Fraction(1, 100), Fraction(12), Fraction(41, 100), Fraction(3000000), Fraction(10000)} <= _as_stated(text)
    assert Fraction(41, 100) not in _as_written(text) and Fraction(41) in _as_written(text)


# ------------------------------------------------------------------------------------- the recorded r7 chemistry target


@needs_r7
def test_t5_and_t5c_are_detected_on_the_recorded_declining_chemistry_answer(tmp_path):
    """r7/ch-t13 declines two sections ("I cannot write the Data analysis or Conclusion sections ..."), so its word bounds
    are recorded not applicable (rule declined-bound, Decision 96) and the declining sentence is an answer note with no
    translation (the adapters' rule "notes read by what they say"). Asserted first: that decline, and its consequences on
    the cases that need a definitive bound or the declining claim's signed result (T3, T5b, T22b, T22w skip with their
    reasons, as on the round-8 commit). Then T5 presents a declined bound as decided (RCPT-001) and T5c's false count of 7
    is FORM-003 naming MEASURED, neither skipped, as at the published base."""
    item = json.loads((ROUNDS / "r7" / "specialists" / "ch-t13.json").read_text(encoding="utf-8"))
    assert "I cannot write the Data analysis or Conclusion sections" in json.dumps(item)
    m = T.run_suite(tmp_path / "out", rounds_root=ROUNDS, cases=["T3", "T5", "T5b", "T5c", "T22"], targets=("r7/ch-t13",), pack_dir=None)
    got = {e["case"]: e for e in m["faults"] if e["target"] == "r7/ch-t13"}
    for name, why in (("T3", "two verified claims"), ("T5b", "definitive status"), ("T22b", "fits T22b"), ("T22w", "fits T22w")):
        assert got[name]["skipped"] and why in got[name]["skipped"], (name, got[name]["skipped"])
    for name, code in (("T5", "OVS-RCPT-001"), ("T5c", "OVS-FORM-003")):
        e = got[name]
        assert e["skipped"] is None and e["detected"] and e["passed"] and code in e["observed_codes"], (name, e["observed_codes"], e["checks"])
        assert e["naming"].get(code), (name, e["naming"])
