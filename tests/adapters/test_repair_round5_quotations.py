"""Repair round 5, quotation roles:

* ADV5-08: a single word the writer quotes as a word the text does NOT use is a mention, in every everyday frame: an
  example offered with an indefinite article ('a gentle word such as "leaned"', 'a soft verb like "settled"') and a verb
  phrase the writer negates ('do not "crash"', 'is not "afraid"'). A word credited to the text ('calls them "ancient"'), a
  plural or definite example ('violent verbs such as "smashed"') and a contrast ('Not "bent" but "bend"'; close round 2,
  DIFF-02: also a span after "unlike", "rather than" or "instead of", whose case below was rewritten stricter) stay
  quotations and are checked. So, since close round 3 (INV-QR-1), does a word right after a reporting verb under a negation
  ('never writes "roared"'): the reading that made it a mention also took 'not only writes "..."' and 'does not just say
  "..."' out of the checks, so it was reverted to the committed base's reading, and the two cases below that asserted a
  mention were rewritten stricter (the span is a quotation and is checked).
* INV-QROLE-1: the task type a record states about itself (a report's or a claim's own ``task_type``) is advisory: it never
  widens the roles, so outside the channel a report that declares a marking task for an analysis answer cannot take an
  altered quotation after a correction frame out of the checks. The channel's plan, and a caller that states the task,
  still read correction frames in a feedback task."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import feedback_task, find_quotation_spans, quotation_role, quotation_task

from ..evidence_support import deliver
from .test_repair_round4_quotations import _codes, _poem_case


def _roles(text: str, task: str = "analytical_paragraph") -> list[tuple[str, str]]:
    with quotation_task(task):
        return [(inner, quotation_role(text, s, e)) for s, e, inner in find_quotation_spans(text)]


@pytest.mark.parametrize("text, expected", [
    ('The poet picks a gentle word such as "leaned" for the trees.', [("leaned", "mention")]),
    ('A soft verb like "settled" keeps the scene calm.', [("settled", "mention")]),
    # rewritten stricter in close round 2 (DIFF-02): a span after the contrast "unlike" is checked as a quotation, as on the
    # committed base, since what a contrast sets aside is as often the text's own words ('Unlike "the bright fields" of
    # the morning, ...') as a word the text does not use; this case asserted a mention before
    ('Unlike "tumbled", the verb "bend" is slow.', [("tumbled", "quotation"), ("bend", "quotation")]),
    # rewritten stricter in close round 3 (INV-QR-1): a word right after a negated reporting verb is checked as a quotation,
    # as on the committed base, since the reading that made it a mention also read 'not only writes "..."' as an absence;
    # this case asserted a mention before
    ('The poet never writes "roared", so the water stays quiet.', [("roared", "quotation")]),
    ('The waves do not "crash" but "whisper".', [("crash", "mention"), ("whisper", "quotation")]),
    ('The speaker is not "afraid" of the dark.', [("afraid", "mention")]),
])
def test_a_word_quoted_as_one_the_text_does_not_use_is_a_mention(text, expected):
    assert _roles(text) == expected


@pytest.mark.parametrize("text, expected", [
    ('Violent verbs such as "smashed" would break the calm.', [("smashed", "quotation")]),
    ('The poet calls them "ancient".', [("ancient", "quotation")]),
    ('Not "bent" but "bend".', [("bent", "quotation"), ("bend", "quotation")]),
])
def test_control_a_word_credited_to_the_text_stays_a_quotation(text, expected):
    assert _roles(text) == expected


ANSWER = 'The poet presents the willows as wise: they are "patient", and they "read what the slow water writes". '


@pytest.mark.parametrize("sentence", ['The poet picks a gentle word such as "leaned" for the trees, so the calm feels chosen.'])
def test_a_mention_in_a_delivered_answer_raises_no_invented_quotation(sentence):
    _case, rc = deliver(_poem_case(ANSWER + sentence), "text")
    assert not ({"INT-REQ-003", "ES-SRC-001", "INT-LEDGER-025"} & _codes(rc)), sorted(_codes(rc))


def test_a_word_after_a_negated_reporting_verb_in_a_delivered_answer_is_checked():
    """Rewritten stricter in close round 3 (INV-QR-1): this sentence was a case of the test above (no invented quotation
    named); the word after "never writes" is now checked against the poem, as on the committed base, and "roared" is not the
    poem's."""
    _case, rc = deliver(_poem_case(ANSWER + 'The poet never writes "roared", so the water stays quiet.'), "text")
    assert {"INT-REQ-003", "ES-SRC-001"} & _codes(rc), sorted(_codes(rc))


def test_control_an_invented_word_credited_to_the_poem_is_still_named():
    _case, rc = deliver(_poem_case(ANSWER + 'The poet calls them "ancient", so they seem to remember.'), "text")
    assert {"INT-REQ-003", "ES-SRC-001"} & _codes(rc)


# ------------------------------------------------------------------------------------------- INV-QROLE-1

CORRECTION = 'The image → "the silent willows bend".'


def test_a_records_own_task_type_never_widens_the_roles():
    with quotation_task("marking_feedback", advisory=True):
        assert not feedback_task()
        s, e, _inner = find_quotation_spans(CORRECTION)[0]
        assert quotation_role(CORRECTION, s, e) == "quotation"


def test_control_the_plans_task_and_a_caller_stated_task_still_read_corrections():
    with quotation_task("marking_feedback", authoritative=True):
        with quotation_task("analytical_paragraph", advisory=True):      # the record's own type yields to the plan's
            assert feedback_task()
            s, e, _inner = find_quotation_spans(CORRECTION)[0]
            assert quotation_role(CORRECTION, s, e) == "correction"
    with quotation_task("marking_feedback"):                              # a caller stating the task, as a parser's argument
        assert feedback_task()


def test_the_claim_and_report_diagnoses_read_the_records_task_type_as_advisory(monkeypatch):
    """claim_diagnostics and report_diagnostics run their rules inside the advisory reading of the record's task type."""
    from epinoic_logic.translate import diag_core
    seen: list[bool] = []
    monkeypatch.setattr(diag_core, "_run", lambda rules, ctx, layer, missing: seen.append(feedback_task()) or [])
    from epinoic_logic.translate.contracts import SpecialistReport, sha256_text
    body = "The poem is calm."
    report = SpecialistReport(request_id="req", task_id="task", report_id="rep", agent_id="english-specialist", subject="English A: Literature",
                              task_type="marking_feedback", original_response=body, response_sha256=sha256_text(body),
                              created_at="2026-10-24T00:00:00Z", claims=[], supplied_texts=[])
    diag_core.report_diagnostics(report, None, ())
    assert seen and not any(seen)
    seen.clear()
    with quotation_task("marking_feedback", authoritative=True):
        diag_core.report_diagnostics(report, None, ())
    assert seen and all(seen)
