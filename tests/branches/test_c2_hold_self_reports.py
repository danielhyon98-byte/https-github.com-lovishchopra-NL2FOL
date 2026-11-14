"""The round-9 push-check hold on the c2 clearance commit, on the translator's side (results-audit bug 13 with adversarial-live
bug 10, critical): a self-certifying sentence added to a History or Economics short answer ("All calculations have been verified
by the system and are confirmed.", "All values were verified on a GDC and are confirmed correct.", "I recalculated every one of
these values myself and confirm that all are correct.") was named on the receipt only by the parser's advisory status
(INT-HANDOFF-006, info), which no gate read; the core pack's CORE-SELF-001 read only the verification vocabulary and labels, not
the shared self-report reader (``markdown.is_self_certification``) every parser reads.

The core pack, which every branch carries, now names every sentence the shared reader names (CORE-SELF-001), so every subject
branch names the same sentences the same way. These tests pin, for every subject branch and every subject that routes to one
(History, Global Politics, Economics, Business Management, Psychology, both English A courses, the three sciences, Mathematics,
Computer Science, and through the generic branch Geography, Language B and an unlisted subject):

* the push check's three phrasings and 22 more of the class, and the same sentence after a line break and in a table cell, are
  named CORE-SELF-001 on the receipt, the claims holding them carry the advisory status (INT-HANDOFF-006), and none is material;
* the controls (a source's own check reported as evidence, a self-report quoted inside a source, a negated or questioned check,
  a method step, an instruction, a later study's confirmation) draw no CORE-SELF-001 and no advisory status;
* the shared reader itself names every phrasing and none of the controls, and reads a table row cell by cell.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.branches.registry import default_registry

from .c2_hold_texts import BRANCH_OF, CONTROLS, LAYOUT, MORE, REPORTED, SELF_CERTIFYING, SUBJECTS
from .test_c2_clearance_parsers import codes, through_hub

QUESTION = "Answer the question."
IDS = [s[0] for s in SUBJECTS]


def _key(sentence: str) -> str:
    """A run of the sentence that a claim holding it keeps (the last line, without table and emphasis marks)."""
    return sentence.split("\n")[-1].strip("|*()¹ ").split("|")[-1].strip()[:24]


def test_every_branch_of_the_registry_is_covered_and_each_subject_routes_as_listed():
    reg = default_registry()
    assert set(BRANCH_OF.values()) == set(reg.keys())
    for subject, *_ in SUBJECTS:
        assert reg.for_subject(subject)[0].key == BRANCH_OF[subject], subject


@pytest.mark.parametrize("sentence", REPORTED + MORE + [x.split("\n")[-1] for x in LAYOUT])
def test_the_shared_reader_names_every_phrasing(sentence):
    assert md.is_self_certification(md.mask_quotations(sentence)), sentence


@pytest.mark.parametrize("sentence", CONTROLS)
def test_the_shared_reader_names_no_control(sentence):
    assert not md.is_self_certification(md.mask_quotations(sentence)), sentence


def test_a_table_row_is_read_cell_by_cell():
    row = "| Check | All values were verified on a GDC and are confirmed correct. |"
    assert md.is_self_certification(row)
    assert not md.is_self_certification("| Item | Value |") and not md.is_self_certification("| Total | 45 |")


@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_the_base_answers_carry_no_self_report(subject, agent, task_type, base):
    reply, rc = through_hub(base, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert not {"CORE-SELF-001", "INT-HANDOFF-006", "ES-META-001"} & set(codes(rc)), codes(rc)


@pytest.mark.parametrize("sentence", SELF_CERTIFYING)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_self_certification_is_named_core_self_001_on_every_branch_and_never_material(subject, agent, task_type, base, sentence):
    reply, rc = through_hub(base + "\n\n" + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert "CORE-SELF-001" in codes(rc), (subject, sentence, codes(rc))
    holding = [c for c in reply.payload["claims"] if _key(sentence) in c["claim_text"]]
    assert not [c for c in holding if c["materiality"] == "material"], holding
    for c in holding:  # the parser's advisory status, named INT-HANDOFF-006
        assert c.get("advisory_verification_status") is not None, c
        assert [f for f in rc.findings if f.code == "INT-HANDOFF-006" and c["claim_id"] in f.claim_ids], codes(rc)


@pytest.mark.parametrize("sentence", REPORTED)
@pytest.mark.parametrize("subject", ["History", "Economics"])
def test_the_push_checks_reproduction_on_history_and_economics(subject, sentence):
    """The reproduction as the push check gave it: before the fix the receipt named no CORE-SELF-001 on these branches."""
    _subject, agent, task_type, base = next(s for s in SUBJECTS if s[0] == subject)
    _reply, rc = through_hub(base + "\n\n" + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    found = [f for f in rc.structural_findings if f.code == "CORE-SELF-001"]
    assert found and all(f.severity == "warning" for f in found), codes(rc)
    assert all(sentence[:20] not in f.message for f in found)  # the message never repeats the certifying words


@pytest.mark.parametrize("sentence", CONTROLS)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_controls_draw_no_self_report_finding(subject, agent, task_type, base, sentence):
    reply, rc = through_hub(base + "\n\n" + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert "CORE-SELF-001" not in codes(rc), (subject, sentence, [f.message for f in rc.structural_findings if f.code == "CORE-SELF-001"])
    holding = [c for c in reply.payload["claims"] if _key(sentence) in c["claim_text"]]
    assert not [c for c in holding if c.get("advisory_verification_status") is not None], holding
