"""Round-8 clearance (integrated round c1), handoff fixer: the three STEM warnings of the parsers fixer's handoff item 6 (minors),
pinned on the round's recorded answers.

The recorded c1 receipts carried three warnings on correct working, each telling the router something that is not so:

* ch-t14 s3.24: a fill-in model skeleton, 'n = 1.15 ÷ 46.08 = ____ mol', was read as maths with a symbol '____' (INT-SUBJ-004
  stem_algebra on '−Q ÷ n = ____ kJ' and ST-UNDEC-002 "'o' has no stated value"); a run of underscores is a blank, so the line is a
  template, not working;
* cs-t14 c6.1: '(12 × 16) + 4 = 196' was set against '(3 × 16) + 15 = 63', another conversion of the same shape, as if its '12' were
  a miscopied request value (INT-SUBJ-004 stem_given, rule same-shape);
* ph-t14 s6.1: the energy condition '½mv² − GMm/R = 0' was read as the show-that target's final value (INT-SUBJ-004 stem_target
  against '0').

The STEM fixer's readings removed all three; these tests keep them removed, beside the rules' own positives
(``tests/stem/test_stem_repair11.py``, rule same-shape; ``tests/stem/test_clearance_c1_stem.py::test_template_blanks_are_no_maths_and_no_emphasis``).
Each test first checks that the claim it reads is delivered under the id the recorded receipt named, so it cannot pass vacuously."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem.document import clear_document_cache
from epinoic_logic.translate.contracts import SuppliedText

from .test_clearance_c1_stem import CFG, KEY, ROUND8, SUBJECTS


def _receive(tid: str):
    """The recorded answer through a fresh hub, as ``test_clearance_c1_stem.recorded`` sends it: ``(delivered claim id -> claim
    text, receipt)``."""
    a = ROUND8[tid]
    texts = (ROUND8[a["peer"]]["response_text"],) if a["peer"] else ()
    clear_document_cache()
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[a["profile"]], task_type="short_answer", selected_agent_ids=[agent]))
    supplied = [SuppliedText(document_id=f"peer:doc{i}", title="peer", text=t) for i, t in enumerate(texts)]
    m, _, _ = hub.dispatch("t", agent, a["question"], supplied)
    reply, rc = hub.receive("t", m.message_id, a["response_text"], agent_id=agent, report_id="rep-t-0")
    hub.close()
    claims = {c["claim_id"]: c["claim_text"] for c in (reply.payload.get("claims", []) if reply is not None else [])}
    return claims, rc


@pytest.mark.parametrize("tid,claim,line,codes,kind", [
    ("ch-t14", "s3.24", "= ____ mol", ("INT-SUBJ-004", "ST-UNDEC-002"), None),
    ("cs-t14", "c6.1", "(12 × 16) + 4 = 196", ("INT-SUBJ-004",), "stem_given"),
    ("ph-t14", "s6.1", "= 0", ("INT-SUBJ-004",), "stem_target"),
])
def test_the_recorded_answer_carries_no_warning_on_correct_working(tid, claim, line, codes, kind):
    claims, rc = _receive(tid)
    assert claim in claims and line in claims[claim], (claim, sorted(claims)[:40])
    named = [f for f in [*rc.findings, *rc.structural_findings] if f.code in codes and claim in f.claim_ids and (kind is None or kind in f.message)]
    assert not named, [f.message[:300] for f in named]
