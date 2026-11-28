"""The meaning label on every overseer release path (stage 2a of the meaning check; meaning-check design 2.5.6, 2.5.7 and 3.3).

The label's record is read through the one gate (``label_gate``) after every existing read, on every path: the overseer-selected
fallback (``_integrity``: never deliverable, whatever the accuracy; a claim the label names leaves the accuracy), the not-checked
delivery, the formal path, the router's documented decision (``consolidate.delivery_decision``), the combined answer
(``policy.release_decision``) and the overseer port's refusal map. Every expected value is fixed here:

* a usable ``none_named`` record allows nothing by itself: a clean answer decides exactly as before;
* a ``named`` record refuses as a reader hit does (rule ``self-certification-gate``, ``not_deliverable``), named by place and family,
  never by a word of the answer;
* an unavailable, missing or non-revalidating record refuses as an outage (rule ``meaning-label-unavailable``,
  ``selfcert_label_unavailable``); the auditor names a missing or non-revalidating record OVS-FID-010 (error) (T6, T7);
* T1: with the production default (marked ``real_labeller``) no recorded answer is deliverable on any path;
* T18: a claim the label names never shows a success status in the overseer's re-derivation (RES-009, TRN-007, the policy's own),
  and a non-success status is never changed;
* T19: whatever the pool's plan (IN_DEPTH, DUPLICATE, SPLIT, N_FOLD), a label-blocked candidate is never deliverable;
* T22: in duplicate mode the router's decision refuses a label-blocked canonical answer; the delivery policy's fallback selects the
  other member;
* the delivery receipt's ``selfcert_label`` member (delivery-v2) holds states, places, families, kinds, codes and counts only.

Labels are scripted (``ScriptedLabeller``) or the faithful fake's (``ReaderBackedLabeller``); no provider is called. Reached through
the translator's public API only.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from epinoic_logic.api.branches import RouterHub
from epinoic_logic.api.engine import VerificationStatus as S
from epinoic_logic.api.integrity import WorkPlan
from epinoic_logic.api.label import (
    ReaderBackedLabeller, ScriptedLabeller, UnconfiguredLabeller, check_t24, default_labeller, set_default_labeller,
)
from epinoic_logic.api.translate import ClaimRecord, SuppliedText, sha256_text

import epinoic_overseer.port as P
from epinoic_overseer import export_pack, load_pack
from epinoic_overseer.checks.results import composed_display_status
from epinoic_overseer.consolidate import delivery_decision
from epinoic_overseer.delivery_policy import DELIVERY_POLICY_VERSION, DeliveryConfig, DeliveryPolicy
from epinoic_overseer.label_gate import LabelUnavailable, label_gate, label_member, label_refusal
from epinoic_overseer.meta_notes import LABEL_AUDIT_CODES, audit_label_reports, audit_self_reports
from epinoic_overseer.pack import PACK_VERSION

from .conftest import CFG, KEY, make_auditor
from .delivery_support import Agents, FakeClock, Verifier, physics_report, run_task
from .test_c2_hold_self_certification_gate import SUBJECTS
from .translator_checkout import translator_root

HISTORY = SUBJECTS[0]
#: The History base answer's second sentence: the scripted label names it (a material sentence, never a self-certification: the
#: label is scripted here to exercise the paths, never measured).
NAMED_FRAGMENT = "It imposed reparations on Germany"
SCHEMA = "selfcert-label/1"
ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    """The overseer agents are built from the pack exported with the exporter and loaded back from the zip."""
    return load_pack(export_pack(tmp_path_factory.mktemp("export"), zip_archive=True).zip_path)


def naming(fragment, category: str = "OUTCOME") -> ScriptedLabeller:
    """A scripted labeller whose every reply names ``fragment`` wherever an answer unit holds it (category ``category``), names
    every positive canary with its own text, and names nothing else: a schema-valid reply the validator accepts."""
    def script(req, _n):
        verdicts = []
        for it in req.items:
            if it.canary is not None and it.canary.positive:
                verdicts.append({"id": it.id, "v": "gated", "spans": [{"quote": it.text, "category": "CHECK"}]})
            elif fragment is not None and fragment in it.text:
                verdicts.append({"id": it.id, "v": "gated", "spans": [{"quote": fragment, "category": category}]})
            else:
                verdicts.append({"id": it.id, "v": "none", "spans": []})
        return json.dumps({"schema": SCHEMA, "verdicts": verdicts}, ensure_ascii=False)
    return ScriptedLabeller(script)


@dataclasses.dataclass
class Delivered:
    hub: object
    rc: object
    decision: object
    router: object
    event: object
    audit: object

    @property
    def candidate(self):
        [c] = self.decision.receipt.fallback.candidates
        return c


def deliver(text: str, *, labeller=None, config=None, subject=HISTORY, question: str = "Answer the question.", texts=()) -> Delivered:
    """``text`` delivered as the specialist's answer through an audited hub (``labeller``, else the default at each use) with a
    delivery session open from the answer to the decision (no overseer agent), then the router's documented decision on a fresh
    consolidation, the journaled event and the task audit. The hub is closed by the caller (``close``)."""
    subj, agent, task_type, _base = subject
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor(), selfcert_labeller=labeller)
    plan = WorkPlan(plan_id="p-c3k", request_id="r-c3k", task_id="t-c3k", subject=subj, task_type=task_type, selected_agent_ids=[agent],
                    allowed_document_ids=[t.document_id for t in texts])
    ch = hub.open_task(plan)
    m, _req, rq = hub.dispatch(plan.task_id, agent, question, list(texts))
    assert m is not None, rq.findings
    session = DeliveryPolicy(clock=FakeClock(), config=config).start(hub, plan.task_id)
    session.install()
    _reply, rc = hub.receive(plan.task_id, m.message_id, text, agent_id=agent, report_id="rep-c3k")
    decision = session.decide(request_message_ids=[m.message_id], receipts={rc.message_id: rc})
    resp = hub.consolidate(plan.task_id)
    router = delivery_decision(resp, hub.auditor.keyring, hub=hub)
    view = hub.auditor.view(ch.channel_uid)
    event = view.by_message[rc.message_id].event
    audit = hub.auditor.audit(ch.channel_uid)
    return Delivered(hub, rc, decision, router, event, audit)


def close(d: Delivered) -> None:
    d.hub.close()


def _no_words(text: str, *words: str) -> None:
    for w in words:
        assert w not in text, (w, text)


# ============================================================================================ the gate itself
def test_a_clean_answer_reads_none_named_and_decides_as_before():
    """The faithful fake (the suite's default) names nothing in a clean answer: the record re-validates, reads ``none_named``,
    allows nothing by itself, and every path decides exactly as the reader alone decided (the router allows the clean answer)."""
    d = deliver(HISTORY[3])
    try:
        reading = label_gate(d.event)
        assert (reading.state, reading.places, reading.blocks) == ("none_named", (), False)
        assert label_refusal(d.event, d.rc) is None
        assert d.router.allowed, d.router.reason
        c = d.candidate
        assert c.deliverable and c.selfcert_label == {"state": "none_named", "counts": {"places": 0}}
        assert not [f for f in d.audit.report.findings if f.code in LABEL_AUDIT_CODES]
        assert d.decision.receipt.policy_version == DELIVERY_POLICY_VERSION == "delivery-v2"
        assert check_t24(d.decision.receipt) == ()
    finally:
        close(d)


def test_a_named_sentence_refuses_on_every_path_by_place_and_family_never_by_its_words():
    """T4 on the overseer side: a scripted valid label naming paragraph 1, sentence 2 (OUTCOME). The gate reads it ``named``; the
    fallback candidate is never deliverable (whatever the accuracy), the not-checked mode withholds it, the formal path names it,
    and the router's documented decision refuses it as a reader hit (``not_deliverable``); every reason names the place and the
    family, never a word of the answer."""
    lab = naming(NAMED_FRAGMENT)
    d = deliver(HISTORY[3], labeller=lab)
    try:
        assert [f.code for f in d.rc.findings if f.code.startswith("INT-SELF-")] == ["INT-SELF-001"]
        reading = label_gate(d.event, labeller=lab)
        assert (reading.state, reading.places, reading.families) == ("named", ("paragraph 1, sentence 2",), (("OUTCOME",),))
        c = d.candidate
        named = [r for r in c.integrity_reasons if "meaning label names" in r]
        assert not c.deliverable and named == [
            "the meaning label names a self-certification in it (paragraph 1, sentence 2, OUTCOME): a fallback delivery never contains a "
            "claim about its own checking (rule self-certification-gate)"]
        assert c.selfcert_label == {"state": "named", "rule": "self-certification-gate", "places": ["paragraph 1, sentence 2"],
                                    "families": ["OUTCOME"], "counts": {"places": 1}}
        assert any(r.startswith("the meaning label names a self-certification in the answer (paragraph 1, sentence 2, OUTCOME)")
                   for r in d.decision.receipt.formal.reasons)
        assert not d.router.allowed and d.router.reason == (
            "the meaning label names a self-certification in the deliverable answer (paragraph 1, sentence 2, OUTCOME): a delivered answer "
            "never contains a claim about its own checking (rule self-certification-gate)")
        assert P.refusal_label(d.router.reason) == "not_deliverable"
        for text in [*c.integrity_reasons, *d.decision.receipt.formal.reasons, d.router.reason, json.dumps(c.selfcert_label)]:
            _no_words(text, NAMED_FRAGMENT, "reparations", "Germany")
        assert check_t24(d.decision.receipt) == () and not d.decision.delivered
    finally:
        close(d)
    nd = deliver(HISTORY[3], labeller=naming(NAMED_FRAGMENT), config=DeliveryConfig(on_overseer_timeout="deliver_canonical_not_checked"))
    try:
        assert nd.decision.mode == "withheld" and not nd.decision.delivered, nd.decision.mode
        assert any("not deliverable" in s and "meaning label" in s for s in nd.decision.receipt.fallback.selection)
    finally:
        close(nd)


def test_an_unavailable_label_refuses_as_an_outage_on_every_path():
    """A labeller that fails (its every reply malformed): the record is ``unavailable`` (INT-SELF-002); every path refuses it as an
    outage, ``selfcert_label_unavailable``, never as a fault of the answer, and the auditor does not name it (OVS-FID-010 is for a
    missing or non-revalidating record)."""
    lab = ScriptedLabeller(lambda _req, _n: "not json at all")
    d = deliver(HISTORY[3], labeller=lab)
    try:
        assert [f.code for f in d.rc.findings if f.code.startswith("INT-SELF-")] == ["INT-SELF-002"]
        with pytest.raises(LabelUnavailable) as exc:
            label_gate(d.event, labeller=lab)
        assert (exc.value.reason, exc.value.kind, exc.value.describe()) == ("unavailable", "malformed", "unavailable: malformed")
        c = d.candidate
        assert not c.deliverable and "it has no usable meaning label (unavailable: malformed): it is not delivered unlabelled (rule " \
                                      "meaning-label-unavailable)" in c.integrity_reasons
        assert c.selfcert_label == {"state": "unavailable", "rule": "meaning-label-unavailable", "counts": {"places": 0}, "kind": "malformed",
                                    "code": "INT-SELF-002"}
        assert not d.router.allowed and P.refusal_label(d.router.reason) == "selfcert_label_unavailable", d.router.reason
        assert not [f for f in d.audit.report.findings if f.code in LABEL_AUDIT_CODES]
        assert check_t24(d.decision.receipt) == ()
    finally:
        close(d)


def test_t6_a_missing_record_is_ovs_fid_010_and_withholds_as_an_outage():
    """T6: an answer event that carries no label record (the channel's records dropped before the event was journaled). The gate
    raises ``LabelUnavailable('missing')``; the auditor names OVS-FID-010 (error) on the answer; the task audit's entry reads as an
    unusable label on every path (``audit_self_reports`` reads it; ``audit_label_reports`` splits it out); the fallback candidate is
    withheld as unlabelled; the refusal for a missing record maps to ``selfcert_label_unavailable`` (KIT-DL-014)."""
    class _Dropped(dict):
        def __setitem__(self, key, value):  # the channel's record of the answer is never kept
            return None
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        subj, agent, task_type, base = HISTORY
        plan = WorkPlan(plan_id="p-t6", request_id="r-t6", task_id="t-t6", subject=subj, task_type=task_type, selected_agent_ids=[agent])
        ch = hub.open_task(plan)
        ch.label_records = _Dropped()
        m, _r, _rq = hub.dispatch(plan.task_id, agent, "Answer the question.", [])
        session = DeliveryPolicy(clock=FakeClock()).start(hub, plan.task_id)
        session.install()
        _reply, rc = hub.receive(plan.task_id, m.message_id, base, agent_id=agent, report_id="rep-t6")
        decision = session.decide(request_message_ids=[m.message_id], receipts={rc.message_id: rc})
        event = hub.auditor.view(ch.channel_uid).by_message[rc.message_id].event
        assert (event.label_json, event.labelled_text) == (None, None)
        with pytest.raises(LabelUnavailable) as exc:
            label_gate(event)
        assert exc.value.reason == "missing"
        audit = hub.auditor.audit(ch.channel_uid)
        fid = [f for f in audit.report.findings if f.code == "OVS-FID-010"]
        assert len(fid) == 1 and fid[0].severity == "error" and fid[0].message_ids == [rc.message_id] and "(missing)" in fid[0].message
        entries = audit_self_reports(audit, rc.message_id)
        assert audit_label_reports(entries) == ([], ["OVS-FID-010"])
        [c] = decision.receipt.fallback.candidates
        assert not c.deliverable and c.selfcert_label["state"] == "unavailable" and c.selfcert_label["code"] == "OVS-FID-010"
        assert any("meaning-label record as missing or not reproducing (OVS-FID-010" in r for r in c.integrity_reasons), c.integrity_reasons
        reason = f"the deliverable answer has no usable meaning label ({exc.value.describe()}): it is not delivered unlabelled (rule meaning-label-unavailable)"
        assert P.refusal_label(reason) == "selfcert_label_unavailable"
        resp = hub.consolidate(plan.task_id)
        assert not delivery_decision(resp, hub.auditor.keyring, hub=hub).allowed
    finally:
        hub.close()


class _Tampering(ReaderBackedLabeller):
    """The faithful fake whose results reach the channel with one byte of the first stored raw reply changed (T7)."""

    def result(self, handle):
        res = super().result(handle)
        record = json.loads(json.dumps(res.record))
        for a in record.get("attempts") or []:
            if isinstance(a.get("raw_reply"), str) and a["raw_reply"]:
                raw = a["raw_reply"]
                a["raw_reply"] = raw[:-1] + ("}" if raw[-1] != "}" else " ")
                break
        return dataclasses.replace(res, record=record)


def test_t7_one_byte_of_the_raw_reply_changed_does_not_revalidate():
    """T7: the journaled record carries one byte of its raw reply changed. The gate reports the re-validation mismatch (never a
    reading); the auditor names OVS-FID-010; the candidate is withheld."""
    lab = _Tampering()
    d = deliver(HISTORY[3], labeller=lab)
    try:
        rec = json.loads(d.event.label_json)
        assert rec["state"] == "none_named" and rec["attempts"]
        with pytest.raises(LabelUnavailable) as exc:
            label_gate(d.event, labeller=lab)
        assert exc.value.reason == "revalidation" and {"seal", "raw_sha256"} & set(exc.value.mismatches), exc.value.mismatches
        fid = [f for f in d.audit.report.findings if f.code == "OVS-FID-010"]
        assert len(fid) == 1 and fid[0].severity == "error" and "revalidation" in fid[0].message
        c = d.candidate
        assert not c.deliverable and c.selfcert_label["state"] == "unavailable"
        assert not d.router.allowed
    finally:
        close(d)


def test_the_gate_refuses_a_text_or_record_that_is_not_the_journaled_one_and_a_skipped_record_that_does_not_reproduce():
    d = deliver(HISTORY[3])
    try:
        ev = d.event
        with pytest.raises(LabelUnavailable) as exc:
            label_gate(dataclasses.replace(ev, labelled_text=ev.labelled_text + " "))
        assert exc.value.reason == "text-mismatch"
        with pytest.raises(LabelUnavailable) as exc:
            label_gate(dataclasses.replace(ev, label_json=ev.label_json.replace('"none_named"', '"named"')))
        assert exc.value.reason == "record-mismatch"
        forged = json.loads(ev.label_json)
        forged["state"] = "named"
        forged_json = json.dumps(forged)
        with pytest.raises(LabelUnavailable) as exc:
            label_gate(dataclasses.replace(ev, label_json=forged_json, label_sha256=hashlib.sha256(forged_json.encode()).hexdigest()))
        assert exc.value.reason == "revalidation"
        with pytest.raises(LabelUnavailable) as exc:  # a record re-validated with another labeller (another model digest) is a mismatch
            label_gate(ev, labeller=naming(None))
        assert exc.value.reason == "revalidation" and "model_digest" in exc.value.mismatches
        with pytest.raises(LabelUnavailable) as exc:  # the production default never re-validates anything
            label_gate(ev, labeller=UnconfiguredLabeller())
        assert exc.value.reason == "revalidation"
    finally:
        close(d)
    refused = deliver(HISTORY[3] + "\n\nThis passed the hub's checks.")
    try:
        ev = refused.event
        assert json.loads(ev.label_json)["state"] == "skipped"
        assert label_gate(ev).state == "skipped" and label_gate(ev).blocks
        clean = HISTORY[3]
        moved = dataclasses.replace(ev, labelled_text=clean, labelled_text_sha256=hashlib.sha256(clean.encode()).hexdigest())
        with pytest.raises(LabelUnavailable) as exc:
            label_gate(moved)
        assert exc.value.reason == "skipped-not-reproduced"
        assert not refused.candidate.deliverable and refused.candidate.selfcert_label["state"] == "skipped"
    finally:
        close(refused)


def test_the_member_holds_states_places_families_kinds_codes_and_counts_only():
    assert label_member(None) == {"state": "none_named", "counts": {"places": 0}}
    for member in (label_member(None), {"state": "named", "rule": "self-certification-gate", "places": ["paragraph 3, sentence 1"],
                                        "families": ["CHECK"], "counts": {"places": 1}}):
        rec = {"contract": "delivery_receipt/1.0", "fallback": {"candidates": [{"message_id": "m", "deliverable": False, "selfcert_label": member}]}}
        assert check_t24(rec) == ()
    worded = {"contract": "delivery_receipt/1.0", "fallback": {"candidates": [{"message_id": "m", "deliverable": False,
                                                                               "selfcert_label": {"state": "named", "places": ["every figure checked"]}}]}}
    assert check_t24(worded)  # words in the member are a T24 violation: the member never carries them


# ============================================================================================ T1: the production default
def _texts(name: str) -> dict:
    """The literal string and tuple constants of a translator test-material module, read as data (never imported)."""
    root = translator_root()
    out = {}
    for node in ast.parse((root / "tests" / "branches" / f"{name}.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return out


_STEM_SUBJECTS = {"physics": "Physics", "mathematics_aa": "Mathematics: Analysis and Approaches",
                  "mathematics_ai": "Mathematics: Applications and Interpretation", "chemistry": "Chemistry", "computer_science": "Computer Science",
                  "biology": "Biology", "ess": "Environmental Systems and Societies"}


def _t1_answers() -> list[tuple[str, dict]]:
    """The answers of the hub part of T1 (``tests/branches/test_selfcert_label_hub.py``): the recorded round-10 answers the repository
    carries (nine STEM fixtures and the three c3 D9/D10 recordings) and every genuine answer of the recorded rounds r1 to r7."""
    root = translator_root()
    out = []
    data = json.loads((root / "tests" / "fixtures" / "stem" / "round10" / "c3_answers.json").read_text(encoding="utf-8"))["answers"]
    for tid, a in sorted(data.items()):
        out.append((f"c3/{tid}", dict(subject=_STEM_SUBJECTS[a["profile"]], agent="stem-specialist", task_type="short_answer", question=a["question"],
                                      text=a["response_text"], texts=[SuppliedText(document_id=f"doc{i}", title="supplied", text=t)
                                                                      for i, t in enumerate(a["supplied_texts"])], others=[])))
    T = _texts("d9d10_texts")
    geo, spb = ("Geography", "geography-specialist"), ("Language B: Spanish", "language-b-spanish-specialist")
    for name, (answer, question, subj, task_type, docs) in sorted({
            "c3/ge-t16": ("GE_T16", "GE_T16_Q", geo, "essay", ()),
            "c3/sp-p10d": ("SP_P10D", "SP_P10D_Q", spb, "language_notes", ("SP_P10D_DOC",)),
            "c3/sp-t16": ("SP_T16", "SP_T16_Q", spb, "marking_feedback", ("SP_T16_DOC",))}.items()):
        texts = [SuppliedText(document_id=d[0], title=d[1], author=d[2], text=d[3]) for d in (T[x] for x in docs)]
        out.append((name, dict(subject=subj[0], agent=subj[1], task_type=task_type, question=T[question], text=T[answer], texts=texts,
                               others=["dummy-combinator"])))
    sys.path.insert(0, str(root / "scripts" / "arena"))
    import run_arena as RA
    for rd in ("r1", "r2", "r3", "r4", "r5", "r6", "r7"):
        items = RA.load_items(ROUNDS / rd / "specialists")
        for it in items:
            group = RA.group_of(it)
            plan = RA.group_plan(items, group)
            out.append((f"{rd}/{it['task_id']}", dict(plan=plan, agent=it["agent_id"], question=it["question"], text=it["response_text"],
                                                       texts=RA.supplied(it), report_id=f"rep-{it['task_id']}-0")))
    return out


def _t1_one(spec: dict, *, not_checked: bool):
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        plan = spec.get("plan") or WorkPlan(plan_id="p", request_id="q", task_id="t", subject=spec["subject"], task_type=spec["task_type"],
                                            selected_agent_ids=[spec["agent"], *spec["others"]],
                                            allowed_document_ids=[t.document_id for t in spec["texts"]])
        ch = hub.open_task(plan)
        m, _r, _rq = hub.dispatch(plan.task_id, spec["agent"], spec["question"], list(spec["texts"]))
        config = DeliveryConfig(on_overseer_timeout="deliver_canonical_not_checked") if not_checked else None
        session = DeliveryPolicy(clock=FakeClock(), config=config).start(hub, plan.task_id)
        session.install()
        _reply, rc = hub.receive(plan.task_id, m.message_id, spec["text"], agent_id=spec["agent"], report_id=spec.get("report_id", "rep-t-0"))
        decision = session.decide(request_message_ids=[m.message_id], receipts={rc.message_id: rc})
        router = delivery_decision(hub.consolidate(plan.task_id), hub.auditor.keyring, hub=hub)
        event = hub.auditor.view(ch.channel_uid).by_message[rc.message_id].event
        return rc, decision, router, event
    finally:
        hub.close()


@pytest.mark.real_labeller
@pytest.mark.skipif(ROUNDS is None or not (ROUNDS / "r7" / "specialists").is_dir(), reason="the recorded rounds are not present (EPINOIC_ARENA_ROUNDS)")
def test_t1_the_production_default_delivers_none_of_the_recorded_answers_on_any_overseer_path():
    """T1, the overseer part (marked ``real_labeller``: the production default, ``UnconfiguredLabeller``), on the same answers and the
    same pinned counts as the hub part: 68 answers, 67 the rule reader passes (record ``unavailable``, ``not-configured``) and one it
    refuses (``r7/ch-t13``, record ``skipped``). On each overseer release path none is deliverable: the fallback candidate
    (``deliverable=False`` for all 68), the overseer-selected and not-checked deliveries (0 delivered in either configuration),
    the formal path (never complete), and the router's documented decision (0 allowed), whose refusal maps to
    ``selfcert_label_unavailable`` for each reader-passed answer it reaches with the label and never to anything that delivers."""
    assert isinstance(default_labeller(), UnconfiguredLabeller)
    answers = _t1_answers()
    passed, refused, deliverable, delivered, allowed = [], [], [], [], []
    refusals: dict[str, int] = {}
    for name, spec in answers:
        for not_checked in (False, True):
            rc, decision, router, event = _t1_one(spec, not_checked=not_checked)
            state = json.loads(event.label_json)["state"]
            [c] = decision.receipt.fallback.candidates
            if c.deliverable:
                deliverable.append(name)
            if decision.delivered:
                delivered.append((name, not_checked))
            if router.allowed:
                allowed.append(name)
            assert not decision.receipt.formal.complete
            assert c.selfcert_label["state"] == state and state in ("unavailable", "skipped"), (name, c.selfcert_label)
            if not not_checked:
                (passed if state == "unavailable" else refused).append(name)
                label = P.refusal_label(router.reason)
                refusals[label] = refusals.get(label, 0) + 1
                if state == "unavailable":
                    assert c.selfcert_label["kind"] == "not-configured", (name, c.selfcert_label)
                assert check_t24(decision.receipt) == ()
    assert len(answers) == 68  # 9 + 3 recorded round-10 answers, 56 genuine answers of r1 to r7
    assert (len(passed), len(refused)) == (67, 1) and refused == ["r7/ch-t13"]
    assert (deliverable, delivered, allowed) == ([], [], [])
    assert refusals == PINNED_T1_REFUSALS, refusals


#: The refusal labels of the router's documented decision on the 68 answers under the production default (measured on a copy of
#: the recorded rounds r1 to r7 and on the round-10 fixtures): 58 unlabelled answers reach the label and are refused as an outage;
#: 9 are refused earlier, every answer of their consolidation excluded by an error-level finding (the reader-passed answers whose
#: receipts or audits carry an error, unchanged by the label); the reader-refused one is an integrity refusal.
PINNED_T1_REFUSALS: dict = {"selfcert_label_unavailable": 58, "no_deliverable_output": 9, "not_deliverable": 1}


@pytest.mark.real_labeller
def test_t1_the_combined_answer_and_the_port_refuse_under_the_production_default():
    """T1 on the two paths that need their own set-up: a combined answer is never released (``selfcert_label_unavailable``), and the
    overseer port's single delivery refuses (``selfcert_label_unavailable``) with the FINAL audit passed (an unavailable record is an
    outage, never OVS-FID-010)."""
    from .test_c2_hold_round3_gate import _release
    from .test_port_adapter import _call, _config
    assert isinstance(default_labeller(), UnconfiguredLabeller)
    d = _release("")
    assert not d.allowed and d.reason == ("the synthesis has no usable meaning label (unavailable: not-configured): it is not released "
                                          "unlabelled (rule meaning-label-unavailable)"), d.reason
    assert P.refusal_label(d.reason) == "selfcert_label_unavailable"
    port = P.connect(_config())
    try:
        hub, task, _rc0, _reply, rc = _call(port)
        assert [f.code for f in rc.findings if f.code.startswith("INT-SELF-")] == ["INT-SELF-002"]
        final = port.close(hub, task)
        assert "OVS-FID-010" not in final["error_codes"]
        out = port.deliver(hub, task, mode="single")
        assert (out["allowed"], out["refusal"]) == (False, "selfcert_label_unavailable"), out
    finally:
        port.shutdown()


def test_under_the_faithful_fake_the_combined_answer_and_the_port_decide_as_before():
    """Control for the test above: with the suite's faithful fake the same combined answer is released and the port delivers."""
    from .test_c2_hold_round3_gate import _release
    from .test_port_adapter import _call, _config
    assert isinstance(default_labeller(), ReaderBackedLabeller)
    d = _release("")
    assert d.allowed, d.reason
    port = P.connect(_config())
    try:
        hub, task, _rc0, _reply, _rc = _call(port)
        port.close(hub, task)
        out = port.deliver(hub, task, mode="single")
        assert out["allowed"] is True, out
    finally:
        port.shutdown()


# ============================================================================================ T18: the overseer's display surfaces
@pytest.fixture
def default_is(request):
    """Install the labeller a test names as the default for its duration (the channels, the auditor and the gates of
    ``delivery_support.run_task``'s hub read the default at each use), and put the previous one back."""
    installed = []

    def install(lab):
        installed.append(set_default_labeller(lab))
        return lab
    yield install
    for prev in reversed(installed):
        set_default_labeller(prev)


def test_t18_a_claim_the_label_names_never_shows_success_in_the_overseers_re_derivation(default_is, pack):
    """T18 on the overseer's surfaces: the label names the Physics answer's ENTAILED claim (INT-SELF-001 with claim p1.1). The
    channel withholds its success display (NOT_ELIGIBLE); the auditor's re-derivation agrees (no OVS-RES-009, no OVS-TRN-007), the
    delivery policy's formal path re-derives NOT_ELIGIBLE for it, and the claim leaves the accuracy (numerator and denominator).
    ``composed_display_status`` withholds a success display for a labelled claim and never changes a non-success one."""
    default_is(naming("The speed is 15 km/h"))
    clock = FakeClock()
    policy = DeliveryPolicy(clock=clock, pack=pack, provider_factory=Agents(clock))
    run = run_task(policy, [("physics-specialist", physics_report("physics-specialist", "rep-a", evidence=False))], verify=Verifier(clock))
    try:
        [rc] = list(run.receipts.values())
        assert [(f.code, f.claim_ids) for f in rc.findings if f.code.startswith("INT-SELF-")] == [("INT-SELF-001", ["p1.1"])]
        [o] = [o for o in rc.outcomes if o.claim_id == "p1.1"]
        assert o.display_status is S.NOT_ELIGIBLE and o.verification is not None and o.verification.status is S.ENTAILED
        audit = run.hub.auditor.audit(next(iter(run.hub.channels.values())).channel_uid)
        codes = {f.code for f in audit.report.findings}
        assert not codes & {"OVS-RES-009", "OVS-TRN-007"}, sorted(codes)
        rec = run.decision.receipt
        [formal] = [c for c in rec.formal.claims if c.claim_id == "p1.1"]
        assert formal.display_status == "NOT_ELIGIBLE" and formal.outcome != "clean"
        [c] = rec.fallback.candidates
        assert (c.material_claims, c.accurate) == (0, 0) and not c.deliverable and c.selfcert_label["state"] == "named"
        assert not run.decision.delivered
        claim = next(cl for cl in run.messages[rc.message_id].payload["claims"] if cl["claim_id"] == "p1.1")
        cr = ClaimRecord.model_validate(claim)
        assert composed_display_status(cr, o.translation, o.verification, KEY, "hub") is S.ENTAILED
        assert composed_display_status(cr, o.translation, o.verification, KEY, "hub", labelled=True) is S.NOT_ELIGIBLE
    finally:
        run.close()


def test_t18_a_non_success_display_is_never_changed_by_the_label():
    from .delivery_support import refuted_outcome
    report = physics_report("physics-specialist", "rep-r", (("p1.1", "The value 5 is more than 9."),), evidence=False)
    claim = report.claims[0]
    o = refuted_outcome(claim, report)
    assert o.display_status is S.COUNTEREXAMPLE
    for labelled in (False, True):
        assert composed_display_status(claim, o.translation, o.verification, KEY, "t", labelled=labelled) is S.COUNTEREXAMPLE
        assert composed_display_status(claim, o.translation, None, KEY, "t", labelled=labelled) is not S.ENTAILED


# ============================================================================================ T22: duplicate mode
def test_t22_the_routers_decision_refuses_a_label_blocked_canonical_answer_and_the_fallback_selects_the_other_member(default_is, pack):
    """T22: two agents give the same answer (the same material claim; their texts differ in letter case only, so the label reads two
    texts). Both carry the same unclaimed sentence, so neither is clean and the earliest is the canonical answer. The label names the
    canonical answer's claim sentence and nothing in the other: the router's documented decision refuses the canonical answer (it never
    falls back to the other member), and the delivery policy's fallback, which considers every member, selects the other one."""
    default_is(naming("The speed is 15 km/h"))
    clock = FakeClock()
    extra = " Speed is distance divided by time."
    a = physics_report("physics-specialist", "rep-a", (("p1.1", "The speed is 15 km/h."),), evidence=False)
    b = physics_report("physics-specialist-2", "rep-b", (("p1.1", "the speed is 15 km/h."),), evidence=False)
    a = a.model_copy(update={"original_response": a.original_response + extra})
    b = b.model_copy(update={"original_response": b.original_response + extra})
    a = a.model_copy(update={"response_sha256": sha256_text(a.original_response)})
    b = b.model_copy(update={"response_sha256": sha256_text(b.original_response)})
    policy = DeliveryPolicy(clock=clock, pack=pack, provider_factory=Agents(clock))
    run = run_task(policy, [("physics-specialist", a), ("physics-specialist-2", b)], verify=Verifier(clock))
    try:
        ma, mb = run.message_of("physics-specialist"), run.message_of("physics-specialist-2")
        resp = run.hub.consolidate(run.plan.task_id)
        assert len(resp.groups) == 1 and resp.deliverable_message_id == ma, (resp.status, [g.members for g in resp.groups])
        d = delivery_decision(resp, run.keyring, hub=run.hub)
        assert not d.allowed and d.reason.startswith("the meaning label names a self-certification in the deliverable answer"), d.reason
        assert P.refusal_label(d.reason) == "not_deliverable"
        cands = {c.message_id: c for c in run.decision.receipt.fallback.candidates}
        assert not cands[ma].deliverable and cands[ma].selfcert_label["state"] == "named"
        assert cands[mb].deliverable and cands[mb].selfcert_label["state"] == "none_named"
        assert run.decision.delivered and run.decision.message_id == mb and run.decision.mode == "overseer_selected"
    finally:
        run.close()


# ============================================================================================ T19: every pool method
@pytest.mark.parametrize("method", ["IN_DEPTH", "DUPLICATE", "SPLIT", "N_FOLD"])
def test_t19_whatever_the_pools_plan_a_label_blocked_candidate_is_never_deliverable(method, default_is, pack):
    """T19: the flash router plans the overseer agents' review (it reads no answer text). With the released router attached in
    process, its plan rewritten so that every dossier is reviewed by ``method`` (a plan the port refuses runs the minimum-oversight
    floor plan instead, as a deployment would), the agents' review counts every claim accurate; the label names the answer, so the
    candidate is never deliverable and nothing is delivered, whatever the plan."""
    from epinoic_logic.integration.router_pool import attach_pool_router_in_process
    from .flash_router_support import require_flash_router
    import importlib
    port = importlib.import_module(require_flash_router())

    def rewritten(request_json: str) -> str:
        plan = json.loads(port.pool_plan(request_json))

        def walk(v):
            if isinstance(v, dict):
                for k, x in list(v.items()):
                    if k == "method" and x in ("IN_DEPTH", "DUPLICATE", "SPLIT", "N_FOLD"):
                        v[k] = method
                    else:
                        walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk(plan)
        return json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    router = attach_pool_router_in_process(port.pool_hello, rewritten)
    assert router.attached, router.detail
    default_is(naming("The speed is 15 km/h"))
    clock = FakeClock()
    policy = DeliveryPolicy(clock=clock, pack=pack, provider_factory=Agents(clock), router=router)
    run = run_task(policy, [("physics-specialist", physics_report("physics-specialist", "rep-a", evidence=False))], verify=Verifier(clock))
    try:
        rec = run.decision.receipt
        assert rec.fallback.overseer.ran, rec.fallback.overseer
        [c] = rec.fallback.candidates
        assert not c.deliverable and c.selfcert_label["state"] == "named" and not run.decision.delivered
        assert any("meaning label names" in r for r in c.integrity_reasons)
    finally:
        run.close()


def test_the_installed_pack_states_t17():
    """Pack 2.3 (the installed pack) states trust rule T17 and the label's codes; 2.2 stays pinned unchanged."""
    from epinoic_overseer.pack import installed_pack
    pack = installed_pack()
    assert PACK_VERSION == pack.identity.version == "2.3"
    text = pack.system_text()
    assert "**T17 Withholding evidence.**" in text and "only to WITHHOLD" in text
    for code in ("INT-SELF-001", "INT-SELF-002", "OVS-FID-010"):
        assert code in text, code


def test_the_overseers_test_fixture_that_names_the_label_package_is_pinned():
    """Interface (a): of the overseer's test tree, exactly its session conftest names the label package, and it installs the
    faithful fake through the one switch, reaching the translator only through ``epinoic_logic.api``. (This half of the
    translator's ``tests/selfcert_label/test_identity.py`` pin lives here: a translator test may not build a path to the
    overseer's tests.)"""
    tests_root = Path(__file__).resolve().parents[1]
    conftests = {p.relative_to(tests_root).as_posix() for p in tests_root.rglob("conftest.py")
                 if "__pycache__" not in p.parts and "selfcert_label" in p.read_text(encoding="utf-8", errors="replace")}
    assert conftests == {"overseer_tests/conftest.py"}
    text = (tests_root / "overseer_tests" / "conftest.py").read_text(encoding="utf-8")
    assert "set_default_labeller" in text and "ReaderBackedLabeller" in text
    assert "epinoic_logic.selfcert_label" not in text and "from epinoic_logic import selfcert_label" not in text
