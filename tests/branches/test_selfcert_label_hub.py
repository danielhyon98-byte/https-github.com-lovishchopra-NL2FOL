"""The meaning label through the router hub (meaning-check design 2.5.1 items 2 and 3, 3.3; stage 2a, owner R4).

Each answer reaches the hub as raw text, as a specialist sends it, and every label is scripted, made by the faithful fake the
suite installs, or the production default (tests marked ``real_labeller``). Expected values are fixed here:

* T4 through the hub: a scripted valid label naming paragraph 2, sentence 1 gives exactly one INT-SELF-001 with that place and
  the family OUTCOME, ACCEPTED_WITH_FINDINGS, and the response gate withholds the answer;
* T5 through the hub: a scripted valid label naming nothing gives the reader-only receipt (the faithful fake's) exactly;
* T3 and T11 through the hub (the channel's equivalents of KIT-DL-014): INT-SELF-002 ``control`` after one retry, ``timeout``,
  and ``budget`` with no call;
* the hub's ``selfcert_labeller`` reaches every channel it opens, and without one the default is looked up at each use;
* T1, the hub part: with the production default every recorded answer the repository carries for round 10 and every genuine
  answer of the recorded rounds r1 to r7 is withheld at the hub: each answer the reader passes carries INT-SELF-002
  ``not-configured``, and each answer the reader refuses keeps its reader codes (its receipt is the faithful fake's).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.channel.gate import assess_response
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.selfcert_label import BudgetedLabeller, CallFailure, UnconfiguredLabeller, using_default_labeller
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller, ScriptedLabeller, reply_json
from epinoic_logic.translate.contracts import SuppliedText

from . import d9d10_hub as D

KEY = b"hub-label-test-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
NAMED = "These shares settle the question for every year shown."
TEXT = "Revenue rose from 200,000 to 250,000, an increase of 25 per cent.\n\n" + NAMED + " The firm should therefore proceed."
QUESTION = "Calculate the percentage increase in revenue and recommend whether to proceed."
ROOT = Path(__file__).resolve().parents[2]
ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None


def _through_hub(labeller=None, text=TEXT, *, hub=None):
    hub = hub or RouterHub(signing_key=KEY, config=CFG, selfcert_labeller=labeller)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="Business Management", task_type="short_answer",
                           selected_agent_ids=["business-specialist"]))
    m, _, _ = hub.dispatch("t", "business-specialist", QUESTION)
    reply, rc = hub.receive("t", m.message_id, text, agent_id="business-specialist", report_id="rep-b")
    return hub, reply, rc


def _label(rc):
    return [(f.code, f.message) for f in rc.findings if f.code.startswith("INT-SELF-")]


def _record(hub, rc):
    rec_json, _text, _req = hub.channels["t"].label_records[rc.message_id]
    return json.loads(rec_json) if rec_json is not None else None


def _gate(sentence, category="OUTCOME"):
    def script(req, n):
        return reply_json(req, {it.id: [(sentence, category)] for it in req.items if it.canary is None and it.text == sentence})
    return script


def test_t4_through_the_hub():
    lab = ScriptedLabeller(_gate(NAMED))
    hub, reply, rc = _through_hub(lab)
    assert hub.selfcert_labeller is lab and hub.channels["t"].selfcert_labeller is lab
    label = _label(rc)
    assert len(label) == 1 and label[0][0] == "INT-SELF-001"
    assert label[0][1].startswith("paragraph 2, sentence 1 of the answer:") and "family OUTCOME" in label[0][1]
    assert "settle the question" not in label[0][1] and "settle the question" not in rc.summary
    assert reply is not None and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    assert _record(hub, rc)["state"] == "named"
    assert assess_response([rc], synthesis_required=False).display_status == "WITHHELD"
    # the label read exactly the text that is delivered: the raw answer as it arrived
    assert hub.channels["t"].label_records[rc.message_id][1] == TEXT == reply.payload["original_response"]


def test_t5_through_the_hub_is_the_reader_only_receipt():
    _hub0, _r0, base = _through_hub(ReaderBackedLabeller())
    hub, reply, rc = _through_hub(ScriptedLabeller(lambda req, n: reply_json(req, {})))
    assert _label(rc) == [] and _record(hub, rc)["state"] == "none_named"
    assert (rc.status, sorted(f.code for f in rc.findings), sorted(s.code for s in rc.structural_findings)) == \
           (base.status, sorted(f.code for f in base.findings), sorted(s.code for s in base.structural_findings))
    assert [c.satisfied for c in rc.formal_checks] == [c.satisfied for c in base.formal_checks]


def test_t3_and_t11_through_the_hub():
    lab = ScriptedLabeller(lambda req, n: reply_json(req, {}, canaries=False))
    hub, _reply, rc = _through_hub(lab)
    assert [c for c, _m in _label(rc)] == ["INT-SELF-002"] and "(control;" in _label(rc)[0][1] and len(lab.requests) == 2
    hub, _reply, rc = _through_hub(ScriptedLabeller([CallFailure("timeout"), CallFailure("timeout")]))
    assert [c for c, _m in _label(rc)] == ["INT-SELF-002"] and "(timeout;" in _label(rc)[0][1]
    inner = ScriptedLabeller(lambda req, n: reply_json(req, {}))
    hub, _reply, rc = _through_hub(BudgetedLabeller(inner, 0))
    assert [c for c, _m in _label(rc)] == ["INT-SELF-002"] and "(budget;" in _label(rc)[0][1] and inner.requests == []
    for r in (rc,):
        assert assess_response([r], synthesis_required=False).display_status == "WITHHELD"


def test_without_a_labeller_the_hub_uses_the_default_at_each_use():
    hub = RouterHub(signing_key=KEY, config=CFG)
    assert hub.selfcert_labeller is None
    with using_default_labeller(UnconfiguredLabeller()):
        _hub, _reply, rc = _through_hub(hub=hub)
    assert [c for c, _m in _label(rc)] == ["INT-SELF-002"] and "(not-configured;" in _label(rc)[0][1]
    hub2 = RouterHub(signing_key=KEY, config=CFG)
    _hub, _reply, rc2 = _through_hub(hub=hub2)  # the suite's default: the faithful fake
    assert _label(rc2) == []


def test_a_hub_refuses_a_labeller_that_is_not_one():
    with pytest.raises(TypeError):
        RouterHub(signing_key=KEY, config=CFG, selfcert_labeller="unconfigured")


# ============================================================================================ T1, the hub part
_STEM_SUBJECTS = {"physics": "Physics", "mathematics_aa": "Mathematics: Analysis and Approaches",
                  "mathematics_ai": "Mathematics: Applications and Interpretation", "chemistry": "Chemistry", "computer_science": "Computer Science",
                  "biology": "Biology", "ess": "Environmental Systems and Societies"}


def _round10_answers():
    """(name, deliver) of every recorded answer the repository carries for round 10."""
    out = []
    data = json.loads((ROOT / "tests" / "fixtures" / "stem" / "round10" / "c3_answers.json").read_text(encoding="utf-8"))["answers"]
    for tid, a in sorted(data.items()):
        def deliver(hub, a=a):
            agent = "stem-specialist"
            hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=_STEM_SUBJECTS[a["profile"]], task_type="short_answer",
                                   selected_agent_ids=[agent]))
            texts = [SuppliedText(document_id=f"doc{i}", title="supplied", text=t) for i, t in enumerate(a["supplied_texts"])]
            m, _, _ = hub.dispatch("t", agent, a["question"], texts)
            return hub.receive("t", m.message_id, a["response_text"], agent_id=agent, report_id="rep-t-0")[1]
        out.append((f"c3/{tid}", deliver))
    for name, (answer, question, subject, agent, task_type, docs) in sorted(D.RECORDED.items()):
        if not name.startswith("c3/"):
            continue

        def deliver(hub, answer=answer, question=question, subject=subject, agent=agent, task_type=task_type, docs=docs):
            return D.through_hub(answer, question, subject, agent, task_type, docs, hub=hub)
        out.append((name, deliver))
    return out


def _round_answers():
    """(name, deliver) of every genuine answer of the recorded rounds r1 to r7 (``EPINOIC_ARENA_ROUNDS``), as the harness sends it."""
    sys.path.insert(0, str(ROOT / "scripts" / "arena"))
    import run_arena as RA
    out = []
    for rd in ("r1", "r2", "r3", "r4", "r5", "r6", "r7"):
        items = RA.load_items(ROUNDS / rd / "specialists")
        for it in items:
            def deliver(hub, it=it, items=items):
                group = RA.group_of(it)
                hub.open_task(RA.group_plan(items, group))
                m, _, _ = hub.dispatch(group, it["agent_id"], it["question"], RA.supplied(it))
                return hub.receive(group, m.message_id, it["response_text"], agent_id=it["agent_id"], report_id=f"rep-{it['task_id']}-0")[1]
            out.append((f"{rd}/{it['task_id']}", deliver))
    return out


def _codes(rc):
    return (rc.status, sorted((f.code, f.severity) for f in rc.findings), sorted((s.code, s.severity) for s in rc.structural_findings))


@pytest.mark.real_labeller
@pytest.mark.skipif(ROUNDS is None or not (ROUNDS / "r7" / "specialists").is_dir(), reason="the recorded rounds are not present (EPINOIC_ARENA_ROUNDS)")
def test_t1_the_production_default_delivers_none_of_the_recorded_answers():
    """Rewritten to the stricter value of the production default on purpose (marked ``real_labeller``): with no labeller
    configured, no recorded answer is deliverable at the hub. A reader-passed answer carries INT-SELF-002 ``not-configured``
    (record ``unavailable``) and the response gate withholds it; a reader-refused answer keeps its reader codes (the receipt
    under the faithful fake, exactly) and its record is ``skipped``. No label call is made: the default makes none."""
    answers = _round10_answers() + _round_answers()
    passed, refused, rejected, deliverable = [], [], [], []
    for name, deliver in answers:
        hub = RouterHub(signing_key=KEY, config=CFG)
        rc = deliver(hub)
        ch = next(iter(hub.channels.values()))
        if rc.status is TransmissionStatus.REJECTED:
            rejected.append(name)
            continue
        rec = json.loads(ch.label_records[rc.message_id][0])
        label = _label(rc)
        if rec["state"] == "skipped":
            refused.append(name)
            assert label == [] and rec["reason"] == "reader-refused", name
            with using_default_labeller(ReaderBackedLabeller()):
                faithful = deliver(RouterHub(signing_key=KEY, config=CFG))
            assert _codes(rc) == _codes(faithful), name  # the reader's own codes stand, unchanged
        else:
            passed.append(name)
            assert (rec["state"], rec["kind"]) == ("unavailable", "not-configured"), name
            assert [c for c, _m in label] == ["INT-SELF-002"] and "(not-configured;" in label[0][1], name
            assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS, name
            if assess_response([rc], synthesis_required=False).delivered:
                deliverable.append(name)
        hub.close()
    assert len(answers) == 68  # 9 + 3 recorded round-10 answers, 56 genuine answers of r1 to r7
    assert (len(passed), len(refused), len(rejected)) == (67, 1, 0), refused
    assert deliverable == [] and refused == PINNED_REFUSED


#: The one recorded answer the rule reader refuses (measured on the recorded rounds r1 to r7 and the round-10 fixtures).
PINNED_REFUSED: list = ["r7/ch-t13"]
