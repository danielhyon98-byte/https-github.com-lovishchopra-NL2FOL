"""Round-8 clearance (integrated round c1), handoff fixer: the overseer fixer's handoff item 6, a shadow disagreement on the
genuine p8a channel that every replay of c1 showed (OVS-RCPT-004: "re-derived on the journaled inputs, response_text ... raises
INT-ARG-001 (warning) for claims ['g1.2@economics-specialist'], which its receipt lacks").

It was handed over as a time- or order-dependent INT-ARG-001 on the channel's side. Its cause is the shadow's: production's
verifier (``translate.outcome.verify_claim``) composes each outcome with the report it verifies and the task record, and the
argument diagnosis reads them (EVD-AUTH-001: the claim's "as the data show" is attributed when a text was supplied), while the
shadow composed every outcome without them, as the hand-built fixtures of the overseer's tests do. The shadow now reproduces
the composition whose argument diagnosis is the journaled outcome's (rule ``composition``): the fixture's first, as before,
production's when the fixture's is not the journaled one. The recorded ec-p8a answer, its supplied text and the recorded
translation of g1.2 are the round's own (``data/c1_ec_p8a_g1_2.json``)."""
from __future__ import annotations

import json
from pathlib import Path

import epinoic_logic.overseer.checks.shadow as shadow
from epinoic_logic.channel.bus import CLAIM_OUT_OF_SCOPE
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.outcome import compose_outcome, verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from .conftest import CFG, KEY, findings, make_auditor, new_channel

DATA = json.loads((Path(__file__).parent / "data" / "c1_ec_p8a_g1_2.json").read_text(encoding="utf-8"))
ITEM = DATA["item"]
TEXTS = [SuppliedText(**{k: v for k, v in t.items() if k in ("document_id", "title", "author", "text")}) for t in ITEM["supplied_texts"]]
seen: dict[str, object] = {}


def _production(claim, report, task=None):
    """The production verifier: ``verify_claim`` with the report and the task record, serving the recorded translation of g1.2."""
    if claim.claim_id.split("@")[0] != DATA["claim_id"].split("@")[0]:
        return CLAIM_OUT_OF_SCOPE
    obj = json.loads(json.dumps(DATA["translation"]))
    obj["problem"]["claim_id"], obj["problem"]["request_id"] = claim.claim_id, claim.request_id
    provider = FixtureTranslationProvider({claim.claim_id: [json.dumps(obj), json.dumps(obj)]})
    out = verify_claim(claim, report, Translator(provider), config=CFG, signing_key=KEY, key_id="t", task=task)
    seen["outcome"], seen["claim"] = out, claim
    return out


def _deliver(auditor):
    plan = WorkPlan(plan_id="plan-ec", request_id="req-ec", task_id="task-ec", subject=ITEM["subject"], task_type="short_answer",
                    selected_agent_ids=[ITEM["agent_id"], "combinator"], allowed_document_ids=[t.document_id for t in TEXTS])
    ch = new_channel(auditor, plan, verify_claim_fn=_production)
    m, _req, _rq = ch.request("router", ITEM["agent_id"], ITEM["question"], TEXTS)
    _reply, rc = ch.respond_text(m.message_id, ITEM["response_text"], agent_id=ITEM["agent_id"], report_id="rep-ec-p8a-0")
    return ch, rc


def test_the_shadow_composes_an_outcome_as_production_composed_it():
    auditor = make_auditor()
    ch, rc = _deliver(auditor)
    live = seen["outcome"]
    assert not [d for d in live.named_diagnostics if d.code == "EVD-AUTH-001"]  # "as the data show": the supplied data's
    bare = compose_outcome(seen["claim"], live.translation, live.verification, signing_key=KEY, key_id="t")
    assert [d for d in bare.named_diagnostics if d.code == "EVD-AUTH-001" and d.severity == "warning"]  # composed without the report
    assert not [f for f in rc.findings if f.code == "INT-ARG-001" and any(c.startswith("g1.2") for c in f.claim_ids)]
    audit = auditor.audit(ch.uid)
    assert not findings(audit, "OVS-RCPT-004") and not findings(audit, "OVS-RCPT-005"), [(f.code, f.message[:200]) for f in audit.report.findings]


def test_control_the_shadow_that_composes_without_the_report_fails_the_genuine_channel(monkeypatch):
    """With rule composition off (every outcome composed as a fixture composes it: the shadow before this clearance), the genuine
    channel fails its audit exactly as every replay of c1 did."""
    monkeypatch.setattr(shadow, "_diagnosis_of", lambda outcome: [])  # every composition reads as the journaled one: the first is served
    auditor = make_auditor()
    ch, _rc = _deliver(auditor)
    named = findings(auditor.audit(ch.uid), "OVS-RCPT-004")
    assert named and "INT-ARG-001" in named[0].message and "g1.2" in named[0].message, named


def test_control_a_dropped_diagnosis_is_still_named():
    """A channel that drops the INT-ARG-001 its outcome's diagnosis gives is still named (RCPT-004): the shadow serves a composition
    whose diagnosis is the journaled outcome's, and derives the finding from it."""
    from epinoic_logic.channel.bus import TranslatorChannel
    auditor = make_auditor()
    real = TranslatorChannel._argument_diagnosis

    def drop(self, *a, **kw):
        named, arg, info = real(self, *a, **kw)
        return named, arg[1:], info

    plan = WorkPlan(plan_id="plan-ec", request_id="req-ec", task_id="task-ec", subject=ITEM["subject"], task_type="short_answer",
                    selected_agent_ids=[ITEM["agent_id"], "combinator"], allowed_document_ids=[t.document_id for t in TEXTS])

    def without_report(claim, report, task=None):
        out = _production(claim, report, task)
        if out is CLAIM_OUT_OF_SCOPE:
            return out
        return compose_outcome(claim, out.translation, out.verification, signing_key=KEY, key_id="t")  # EVD-AUTH-001 at warning

    ch = new_channel(auditor, plan, verify_claim_fn=without_report)
    TranslatorChannel._argument_diagnosis = drop
    try:
        m, _req, _rq = ch.request("router", ITEM["agent_id"], ITEM["question"], TEXTS)
        _reply, rc = ch.respond_text(m.message_id, ITEM["response_text"], agent_id=ITEM["agent_id"], report_id="rep-ec-p8a-0")
    finally:
        TranslatorChannel._argument_diagnosis = real
    named = findings(auditor.audit(ch.uid), "OVS-RCPT-004")
    assert named and "INT-ARG-001" in named[0].message, [(f.code, f.message[:160]) for f in auditor.audit(ch.uid).report.findings]
