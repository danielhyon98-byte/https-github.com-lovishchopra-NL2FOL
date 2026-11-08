"""The embedded overseer port adapter (``epinoic_overseer.port``; overseer-port CONFORMANCE, pre-build NOTES items 2, 3, 6,
33 and 83): the service's default ``EPINOIC_OVERSEER_PORT``.

- ``connect`` refuses every configuration out of contract (``KIT-HS-007`` at start-up) and checks its replay worker;
- its hello is in contract: the installed pack's digest (the one the service pins), the overseer's own key ids with
  ``overseer-audit``, replay ``process``, the standard profile only (D30), agents ``async`` only with a provider (D18);
- every reason the overseer's delivery rule gives (``consolidate.delivery_decision`` and its re-check at delivery,
  ``policy.release_decision`` and its journal coverage, the adapter's own FINAL-audit rule) maps onto exactly ONE label of
  the protocol's closed refusals: the reasons are read from the code, so a new reason without a rule fails here;
- a call through the adapter: the clearance's ``receipt_sha256`` is the service's ``turn.receipt_sha256``, the FINAL audit
  is signed under ``overseer-audit`` with both scope statements, the delivery names the journaled answer by its digest;
  an edited receipt is never actable, an edited FINAL audit is ``signature_invalid``, an unmapped reason is never a
  silent ``not_deliverable``;
- ``repeats`` counts repeated faults per transfer; ``review`` queues the admitted plan and returns at once, and the review
  runs on the review worker with as many agents as the plan's most demanding transfer asks for (metadata only, D22).
"""
from __future__ import annotations

import ast
import re
import types
from pathlib import Path

import pytest

import epinoic_overseer
import epinoic_overseer.port as P
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.overseer_port import PINNED_PACK_DIGESTS, check_clearance, check_delivery, check_final_audit, check_hello, check_review_ticket
from epinoic_logic.integration.protocol import AUDIT_SCOPE_STATEMENT, OVERSEER_REFUSALS, SCOPE_STATEMENT
from epinoic_logic.integration.turn import hub_agent_id, receipt_sha256
from epinoic_overseer.contracts import AUDIT_SCOPE_SENTENCE
from epinoic_overseer.pack import installed_pack

from .conftest import CFG, DOC, EN_INPUT, english_report
from .delivery_support import ScriptedOverseer

ENGINE_KEY = b"overseer-port-adapter-test-engine-key-0123456789"
SECRET = b"overseer-port-adapter-test-overseer-secret-012345"
PACKAGE = Path(epinoic_overseer.__file__).resolve().parent


def _config(**over):
    c = {"engine_key": ENGINE_KEY, "engine_key_id": "default", "overseer_secret": SECRET, "replay_mode": "process", "agents": "off"}
    c.update(over)
    return c


@pytest.fixture(scope="module")
def port():
    p = P.connect(_config())
    yield p
    p.shutdown()


def _code(fn) -> str:
    with pytest.raises(IntegrationError) as exc:
        fn()
    return exc.value.code


# ----------------------------------------------------------------------------------------------- connect and hello
@pytest.mark.parametrize("over", [
    {"replay_mode": "inline"}, {"agents": "sometimes"}, {"engine_key": b"short"}, {"engine_key": None}, {"engine_key_id": ""},
    {"engine_key_id": "overseer-audit"}, {"overseer_secret": b"short"}, {"overseer_secret": ENGINE_KEY}, {"agent_provider_factory": "not callable"},
])
def test_connect_refuses_every_configuration_out_of_contract(over):
    assert _code(lambda: P.connect(_config(**over))) == "KIT-HS-007"
    assert _code(lambda: P.connect("not a mapping")) == "KIT-HS-007"


def test_the_hello_is_in_contract_and_names_the_pinned_pack(port):
    hello = check_hello(port.hello())
    assert hello.mode == "embedded" and hello.auditor_version == epinoic_overseer.__version__ and hello.replay_mode == "process"
    assert hello.pack_digests == [installed_pack().identity.sha256] and set(hello.pack_digests) <= PINNED_PACK_DIGESTS
    assert "overseer-audit" in hello.key_ids and hello.profiles == ["standard"] and hello.agents == "off" and hello.inline_final_release is False
    assert "SECRET" not in repr(port) and SECRET.hex() not in repr(port) and ENGINE_KEY.hex() not in repr(port)


def test_agents_async_need_a_provider_else_they_are_disabled_at_start_up():
    without = P.connect(_config(agents="async"))
    try:
        assert check_hello(without.hello()).agents == "off" and without.notices == ("async_work_disabled",)
    finally:
        without.shutdown()
    with_provider = P.connect(_config(agents="async", agent_provider_factory=lambda agent_id: ScriptedOverseer(lambda d: {})))
    try:
        assert check_hello(with_provider.hello()).agents == "async" and with_provider.notices == ()
    finally:
        with_provider.shutdown()


def test_the_scope_statements_are_the_protocols_verbatim():
    assert AUDIT_SCOPE_SENTENCE == AUDIT_SCOPE_STATEMENT
    from epinoic_logic.api.engine import SCOPE_STATEMENT as ENGINE_SCOPE
    assert ENGINE_SCOPE == SCOPE_STATEMENT


# ----------------------------------------------------------------------------------------------- the refusal map
_SAMPLES = {"state": ["AUDIT_FAILED", "AUDIT_PENDING"],  # a reason names a state only when it is not passed
             "status": ["CONFLICTING", "NO_DELIVERABLE_OUTPUT", "CONSOLIDATED"],
            "scope": ["verdicts", "transfer"]}


def _render(node: ast.AST, source: str) -> list[str]:
    """Every sample a reason expression (a string, or an f-string over the values it names) can produce."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if not isinstance(node, ast.JoinedStr):
        return []
    out = [""]
    for part in node.values:
        if isinstance(part, ast.Constant):
            out = [o + str(part.value) for o in out]
            continue
        text = ast.get_source_segment(source, part.value) or ""
        if text == "why":  # ``answer X is never delivered: {why}``: rendered from ``why``'s own assignment (see _reasons)
            return []
        if "'y' if" in text:
            values = ["y", "ies"]
        elif "len(" in text:
            values = ["1", "3"]
        elif re.search(r"\bstate\b|transfer_states", text):
            values = _SAMPLES["state"]
        elif "status" in text:
            values = _SAMPLES["status"]
        elif "scope" in text:
            values = _SAMPLES["scope"]
        elif text == "what":  # consolidate.delivery_decision: what a status that is not deliverable says (paired below)
            values = ["<WHAT>"]
        else:
            values = ["SAMPLE"]
        out = [o + v for o in out for v in values]
    what = {"CONFLICTING": "the answers conflict and are disclosed, not chosen"}
    return [re.sub(r"^status (\w+): <WHAT>$", lambda m: f"status {m.group(1)}: {what.get(m.group(1), 'no answer may be delivered')}", o) for o in out]


def _reasons() -> list[str]:
    """Every refusal reason of the overseer's delivery rule, read from the code."""
    out: list[str] = []
    targets = {"policy.py": ("release_decision", "_journal_covers"), "consolidate.py": ("delivery_decision", "_current_at_delivery"),
               "port.py": ("_final_refusal",)}
    for name, functions in targets.items():
        source = (PACKAGE / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in functions):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("PolicyDecision", "ConsolidationDecision") and len(node.args) >= 2:
                    if isinstance(node.args[0], ast.Constant) and node.args[0].value is False:
                        if isinstance(node.args[1], ast.Name):  # a reason computed above (``why``): read where it is assigned
                            continue
                        out += _render(node.args[1], source)
                elif isinstance(node, ast.Return) and node.value is not None and fn.name in ("_journal_covers", "_current_at_delivery", "_final_refusal"):
                    out += _render(node.value, source)
                elif isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "why" for t in node.targets):
                    if isinstance(node.value, ast.IfExp):
                        out += _render(node.value.body, source) + _render(node.value.orelse, source)
                        continue
                    out += _render(node.value, source)
    return [r for r in out if r]


def test_every_reason_of_the_delivery_rule_maps_onto_exactly_one_closed_refusal():
    reasons = _reasons()
    assert len(reasons) >= 45, len(reasons)
    labels = {}
    for r in reasons:
        if "repeats a fault" in r or "is excluded (" in r:  # the composed reason around ``why`` (``answer X is never delivered: <why>``)
            r = f"answer m-1 is never delivered: {r}"
        labels[r] = P.refusal_label(r)  # raises UnmappedReason unless exactly one rule maps it
    assert set(labels.values()) <= set(OVERSEER_REFUSALS) - {"internal_error"}
    assert labels["the FINAL audit does not verify under the audit key"] == "signature_invalid"
    assert labels["the FINAL audit is AUDIT_PENDING: not passed"] == "clearance_pending"
    assert labels["status CONFLICTING: the answers conflict and are disclosed, not chosen"] == "consolidation_conflicting"
    assert labels["status NO_DELIVERABLE_OUTPUT: no answer may be delivered"] == "no_deliverable_output"


@pytest.mark.parametrize("reason", ["", "something nobody wrote", "status CONFLICTING: no answer may be delivered and more"])
def test_an_unmapped_reason_is_never_a_silent_not_deliverable(reason):
    with pytest.raises(P.UnmappedReason):
        P.refusal_label(reason)


def test_every_rule_is_a_closed_label():
    assert {label for _p, label in P.REFUSAL_RULES} <= set(OVERSEER_REFUSALS) - {"internal_error"}


# ----------------------------------------------------------------------------------------------- a call through the adapter
def _call(port):
    """One single-mode call through the adapter's hub, as the checks port drives it: (hub, task id, dispatch receipt, reply,
    response receipt)."""
    from epinoic_logic.integrity import WorkPlan
    agent = hub_agent_id("english-a-literature")
    hub = port.new_hub(signing_key=ENGINE_KEY, key_id="default", verify_claim_fn=None, config=CFG)
    plan = WorkPlan(plan_id="plan-port", request_id="req-port", task_id="task-port", subject="English A: Literature", task_type="analytical_paragraph",
                    selected_agent_ids=[agent], allowed_document_ids=["doc-mill"])
    hub.open_task(plan)
    msg, _req, rc0 = hub.dispatch("task-port", agent, EN_INPUT, [DOC])
    report = english_report(request_id="req-port", task_id="task-port", agent=agent, report_id="rep-port")
    reply, rc = hub.receive("task-port", msg.message_id, report)
    return hub, "task-port", rc0, reply, rc


def test_a_call_through_the_adapter_gives_messages_in_contract(port):
    hub, task, rc0, reply, rc = _call(port)
    for receipt in (rc0, rc):
        raw = port.clearance(hub, task, receipt.message_id, receipt, wait_ms=250)
        c = check_clearance(raw, task_id=task, message_id=receipt.message_id, receipt_sha256=receipt_sha256(receipt))
        assert raw["receipt_sha256"] == receipt_sha256(receipt) and 0 <= c.waited_ms <= 250
    final = check_final_audit(port.close(hub, task), task_id=task)
    assert final.signature.key_id == "overseer-audit" and final.scope_statement == SCOPE_STATEMENT and final.audit_scope_statement == AUDIT_SCOPE_STATEMENT
    answers = [(reply.sender_agent_id, reply.message_id, __import__("epinoic_logic.integration.canonical", fromlist=["sha256_text"]).sha256_text(reply.payload["original_response"]))]
    d = check_delivery(port.deliver(hub, task, mode="single"), task_id=task, final_audit_id=final.audit_id, answers=answers)
    assert d.kind == "consolidation" and d.consolidation is not None
    if d.allowed:
        assert (d.deliverable.agent_id, d.deliverable.message_id) == (reply.sender_agent_id, reply.message_id)
    else:
        assert d.refusal in OVERSEER_REFUSALS
    assert port.repeats(hub, task) == {} and port.view(hub, task).task_id == task


def test_an_edited_receipt_is_never_actable(port):
    hub, task, _rc0, _reply, rc = _call(port)
    edited = rc.model_copy(update={"summary": rc.summary + " (edited by the router)"})
    raw = port.clearance(hub, task, rc.message_id, edited, wait_ms=250)
    assert raw["may_act"] is False and raw["receipt_sha256"] == receipt_sha256(edited)


def test_an_edited_final_audit_is_signature_invalid(port):
    hub, task, _rc0, _reply, _rc = _call(port)
    port.close(hub, task)
    call = port._call(hub)
    call.finals[task] = call.finals[task].model_copy(update={"state": "AUDIT_PASSED", "signature": "00" * 32})
    out = port.deliver(hub, task, mode="single")
    assert out["allowed"] is False and out["refusal"] == "signature_invalid"


def test_an_unmapped_reason_raises_instead_of_refusing_silently(port, monkeypatch):
    hub, task, _rc0, _reply, _rc = _call(port)
    port.close(hub, task)
    import epinoic_overseer.consolidate as C
    monkeypatch.setattr(C, "delivery_decision", lambda resp, keyring, hub=None: C.ConsolidationDecision(False, "a reason no rule knows"))
    with pytest.raises(P.UnmappedReason):
        port.deliver(hub, task, mode="single")


def test_the_hub_is_refused_another_engine_key(port):
    assert _code(lambda: port.new_hub(signing_key=b"another-engine-key-0123456789abcdef0123", key_id="default", verify_claim_fn=None, config=CFG)) == "KIT-OP-001"
    assert _code(lambda: port.new_hub(signing_key=ENGINE_KEY, key_id="another-id", verify_claim_fn=None, config=CFG)) == "KIT-OP-001"


# ----------------------------------------------------------------------------------------------- the asynchronous review
def _admission(*instances: int, origin: str = "floor"):
    plan = types.SimpleNamespace(plan_id=f"{origin}-plan-1", transfers=[types.SimpleNamespace(instances=n) for n in instances])
    return types.SimpleNamespace(origin=origin, refusal=None, effective=plan)


def test_without_agents_a_review_is_dropped_naming_the_admitted_plan(port):
    hub, task, _rc0, _reply, _rc = _call(port)
    port.close(hub, task)
    t = check_review_ticket(port.review(hub, task, _admission(2)), task_id=task, origin="floor", plan_id="floor-plan-1", refusal=None)
    assert (t.queued, t.dropped) == (False, True) and port.review_log()[-1].state == "dropped"


def test_a_queued_review_runs_the_admitted_plan_after_the_call_and_keeps_metadata_only():
    seen: list[str] = []
    provider = ScriptedOverseer(lambda d: seen.append(d["agent_id"]) or {"not": "a verdict"})
    port = P.connect(_config(agents="async", agent_provider_factory=lambda agent_id: provider))
    try:
        hub, task, _rc0, _reply, _rc = _call(port)
        port.close(hub, task)
        port.deliver(hub, task, mode="single")
        t = check_review_ticket(port.review(hub, task, _admission(1, 2)), task_id=task, origin="floor", plan_id="floor-plan-1", refusal=None)
        assert (t.queued, t.dropped) == (True, False)
        assert port.wait_for_reviews(120)
        [record] = [r for r in port.review_log() if r.ticket_id == t.ticket_id]
        assert record.state == "done" and record.instances == 2 and record.audit_id and record.error is None
        assert sorted(seen) == ["overseer-review-1", "overseer-review-2"]  # as many agents as the most demanding transfer
        assert "OVS-AGENT-005" in record.agent_codes  # the replies were no verdicts: rejected by the intake, advisory only
        assert not hasattr(record, "text") and all(not isinstance(v, (bytes, bytearray)) for v in vars(record).values())
    finally:
        port.shutdown()
