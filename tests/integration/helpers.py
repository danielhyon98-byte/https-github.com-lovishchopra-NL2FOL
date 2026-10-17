"""Shared helpers of the integration tests. Everything runs in process, with test keys and no network.

``RecordingPort`` is a TEST DOUBLE of the overseer port adapter: it hands out a plain ``RouterHub`` and answers the
port's operations with fixture messages, so the tests can exercise the TurnChecker's normative order, its budget and its
refusals before the real embedded adapter exists (it is connected in phase 2, which runs these same tests against it).
It is not part of the package and nothing outside the tests can import it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from epinoic_logic.integration.canonical import sha256_text
from epinoic_logic.integration.preflight import Probes
from epinoic_logic.integration.protocol import AUDIT_SCOPE_STATEMENT, PROTOCOL, SCOPE_STATEMENT
from epinoic_logic.integration.settings import IntegrationSettings
from epinoic_logic.integration.specialist_port import envelope_for
from epinoic_logic.integration.turn import receipt_sha256

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "integration"
TOKEN = "integration-test-token-0123456789"
ENGINE_KEY_HEX = "11" * 32
VERDICT_KEY_HEX = "22" * 32
OVERSEER_SECRET_HEX = "33" * 32
PACK_DIGEST = "ab" * 32


def runtime_fixture(version: int) -> dict:
    return json.loads((FIXTURES / f"runtime-v{version}-results.json").read_text(encoding="utf-8"))


def website_fixture() -> dict:
    return json.loads((FIXTURES / "website-chat-results.json").read_text(encoding="utf-8"))


def env(**overrides: Optional[str]) -> dict[str, str]:
    base = {
        "EPINOIC_PROFILE": "integration-sim", "EPINOIC_SERVICE_ENV": "sim", "EPINOIC_SERVICE_TOKEN": TOKEN,
        "EPINOIC_SIGNING_KEY": ENGINE_KEY_HEX, "EPINOIC_VERDICT_KEY": VERDICT_KEY_HEX, "EPINOIC_OVERSEER_SECRET": OVERSEER_SECRET_HEX,
        "EPINOIC_FLASH_ROUTER": "none", "EPINOIC_TRANSLATION_PROVIDER": "fixture",
    }
    for k, v in overrides.items():
        name = k if k.startswith("EPINOIC_") else f"EPINOIC_{k}"
        if v is None:
            base.pop(name, None)
        else:
            base[name] = v
    return base


def settings(host: str = "127.0.0.1", **overrides: Optional[str]) -> IntegrationSettings:
    return IntegrationSettings.from_env(env(**overrides), host=host)


def hello(**changes: Any) -> dict:
    h = {"schema": "epinoic.integration.overseer-hello.v1", "protocol": PROTOCOL, "port_version": "1.0", "mode": "embedded",
         "auditor_version": "1.3.0", "pack_digests": [PACK_DIGEST], "key_ids": ["overseer-run", "overseer-audit", "overseer-intake", "overseer-consolidation"],
         "replay_mode": "process", "inline_final_release": False, "max_pending_wait_ms": 250, "agents": "off", "profiles": ["standard"]}
    h.update(changes)
    return h


@dataclass
class RecordingPort:
    """Test double of the overseer port (module docstring). ``clearance_state``, ``final_state``, ``deliver_refusal`` and
    ``representative`` shape its answers; ``calls`` records the order of operations; ``fail_on`` raises in one of them."""
    hello_message: dict = field(default_factory=hello)
    clearance_state: str = "AUDIT_PASSED"
    final_state: str = "AUDIT_PASSED"
    final_codes: list = field(default_factory=list)
    deliver_refusal: Optional[str] = None
    consolidation_status: str = "CONSOLIDATED"
    representative: int = 0
    repeats_by_key: dict = field(default_factory=dict)
    fail_on: Optional[str] = None
    calls: list = field(default_factory=list)
    replies: list = field(default_factory=list)
    reviewed: list = field(default_factory=list)

    def _maybe_fail(self, op: str) -> None:
        self.calls.append(op)
        if self.fail_on == op:
            raise RuntimeError(f"SYNTHETIC failure in {op}")

    def hello(self) -> dict:
        return dict(self.hello_message)

    def new_hub(self, *, signing_key: bytes, key_id: str, verify_claim_fn: Any, config: Any) -> Any:
        self._maybe_fail("new_hub")
        from epinoic_logic.branches import RouterHub

        port = self

        class _Hub(RouterHub):
            def receive(self, task_id, request_message_id, payload, **kw):  # noqa: ANN001 - records the delivered replies
                reply, rc = super().receive(task_id, request_message_id, payload, **kw)
                port.replies.append((reply, rc))
                return reply, rc
        return _Hub(signing_key=signing_key, key_id=key_id, verify_claim_fn=verify_claim_fn, config=config)

    def clearance(self, hub: Any, task_id: str, message_id: str, receipt: Any, *, wait_ms: int) -> dict:
        self._maybe_fail("clearance")
        state = self.clearance_state
        return {"schema": "epinoic.integration.overseer-clearance.v1", "protocol": PROTOCOL, "task_id": task_id, "message_id": message_id,
                "receipt_sha256": receipt_sha256(receipt), "state": state, "may_act": state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"),
                "error_codes": [], "waited_ms": 0}

    def close(self, hub: Any, task_id: str) -> dict:
        self._maybe_fail("close")
        return {"schema": "epinoic.integration.overseer-final-audit.v1", "protocol": PROTOCOL, "task_id": task_id, "audit_id": f"audit-{task_id}",
                "channel_uid": f"ch-{task_id}", "scope": "FINAL", "state": self.final_state, "error_codes": list(self.final_codes),
                "journal_head": "cd" * 32, "scope_statement": SCOPE_STATEMENT, "audit_scope_statement": AUDIT_SCOPE_STATEMENT,
                "signature": {"alg": "hmac-sha256", "key_id": "overseer-audit", "value": "ef" * 32}}

    def deliver(self, hub: Any, task_id: str, *, mode: str, synthesis: Any = None) -> dict:
        self._maybe_fail("deliver")
        delivered = [(reply, rc) for reply, rc in self.replies if reply is not None]
        allowed = self.deliver_refusal is None and bool(delivered)
        deliverable = None
        if allowed:
            reply, _rc = delivered[min(self.representative, len(delivered) - 1)]
            text = reply.payload.get("original_response", "")
            deliverable = {"agent_id": reply.sender_agent_id, "message_id": reply.message_id, "answer_sha256": sha256_text(text)}
        status = self.consolidation_status if allowed else ("CONFLICTING" if self.deliver_refusal == "consolidation_conflicting" else "NO_DELIVERABLE_OUTPUT")
        return {"schema": "epinoic.integration.overseer-delivery.v1", "protocol": PROTOCOL, "task_id": task_id, "kind": "consolidation",
                "allowed": allowed, "refusal": None if allowed else (self.deliver_refusal or "no_deliverable_output"),
                "final_audit_id": f"audit-{task_id}", "consolidation": {"id": f"cons-{task_id}", "status": status, "basis": "single" if mode == "single" else "identical_text"},
                "deliverable": deliverable}

    def view(self, hub: Any, task_id: str) -> Any:
        self.calls.append("view")
        return None

    def repeats(self, hub: Any, task_id: str) -> dict:
        self.calls.append("repeats")
        return dict(self.repeats_by_key)

    def review(self, hub: Any, task_id: str, admission: Any) -> dict:
        self._maybe_fail("review")
        self.reviewed.append(admission)
        return {"schema": "epinoic.integration.overseer-review-ticket.v1", "protocol": PROTOCOL, "ticket_id": f"ticket-{task_id}", "task_id": task_id,
                "queued": True, "dropped": False, "plan": {"origin": admission.origin, "plan_id": admission.effective.plan_id, "refusal": admission.refusal}}


class FixtureProbes(Probes):
    """The real probes, except for the two parts other work streams are still building: the named-policy allowlist of
    contract 0.3 and the overseer port adapter, which these tests supply as fixtures (``missing`` makes one probe raise
    its refusal instead, to show each code)."""

    def __init__(self, port: Optional[RecordingPort] = None, *, missing: Optional[str] = None, **overrides: Any) -> None:
        self.port = port or RecordingPort()
        self.missing = missing
        self.overrides = overrides

    def named_policies(self) -> tuple[str, ...]:
        if self.missing == "named_policies":
            return super().named_policies()
        return ("joint", "linear", "nonlinear")

    def overseer(self, settings: Any, keys: Any):
        from epinoic_logic.integration.overseer_port import check_hello
        if self.missing == "overseer":
            return super().overseer(settings, keys)
        return check_hello(self.port.hello()), self.port

    def __getattribute__(self, name: str) -> Any:
        overrides = object.__getattribute__(self, "overrides")
        if name in overrides:
            return overrides[name]
        return object.__getattribute__(self, name)


def answer_envelope(version: int = 1, *, case: str = "answer", agent_id: str = "history", answer: Optional[str] = None,
                    slug: Optional[str] = None) -> dict:
    """A specialist envelope built from a recorded runtime result (``answer`` replaces the text and its digests; ``slug``
    the specialist slug its provenance names, for a specialist other than the recorded History one)."""
    rec = runtime_fixture(version)[case]
    result, log = json.loads(json.dumps(rec["result"])), json.loads(json.dumps(rec["log"]))
    if answer is not None:
        result["answer"] = answer
    if slug is not None:
        result["provenance"]["slug"] = slug
        log["provenance"]["slug"] = slug
    return envelope_for(result, log, agent_id=agent_id)


def turn_request(answers: list[dict], *, mode: str = "single", user_text: str = "How far did the Treaty of Versailles destabilise Germany in the 1920s?",
                 policy: str = "verified-v1", budget_ms: int = 30000, route: Optional[str] = "history", slug: str = "history",
                 subject: str = "History", task_id: str = "t_" + "0" * 31 + "1", request_id: str = "a_" + "0" * 31 + "1") -> dict:
    return {"schema": "epinoic.integration.turn-check.v1", "protocol": PROTOCOL, "mode": mode,
            "ids": {"task_id": task_id, "request_id": request_id},
            "task": {"route": route, "slug": slug, "subject": subject, "course_level": "unknown", "task_type": "short_answer",
                     "user_text": user_text, "user_text_sha256": sha256_text(user_text), "supplied_texts": []},
            "answers": answers, "policy": policy, "budget_ms": budget_ms, "revision_of": None}


# ----------------------------------------------------------------------------------------------- flash-router fixtures

ROUTER_IDENTITY = {"name": "test-flash-router", "version": "0.1", "rules_sha256": "a1" * 32, "cost_data_sha256": "b2" * 32}


def router_hello(**changes: Any) -> dict:
    h = {"schema": "epinoic.integration.router-hello.v1", "protocol": PROTOCOL, "port_version": "1.0", "router": dict(ROUTER_IDENTITY),
         "methods": ["IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD"], "profiles": ["standard", "fast"], "tier": "cheapest", "deterministic": True}
    h.update(changes)
    return h


def output_features(key: str, *, role: str = "answer", agent_id: str = "history", subject: str = "History", branch: str = "history",
                    stem: bool = False, status: str = "ACCEPTED", errors: tuple = (), warnings: tuple = (), statuses: Optional[dict] = None,
                    repeated: int = 0, chars: int = 900) -> dict:
    return {"transfer_key": key, "role": role, "agent_id": agent_id, "subject": subject, "branch": branch, "stem": stem,
            "size": {"chars": chars, "words": chars // 6, "paragraphs": 2}, "claims": {"total": 6, "material": 4, "eligible": 3, "translated": 2},
            "engine_statuses": dict(statuses or {"ENTAILED": 2}), "receipt": {"status": status, "error_codes": list(errors), "warning_codes": list(warnings)},
            "diagnostics": [], "unverified_dependencies": 0, "peer_relays": 0, "repeated_faults": repeated}


def routing_request(outputs: Optional[list] = None, *, topology: Optional[dict] = None, max_instances: int = 8, profiles=("standard", "fast")) -> dict:
    outputs = outputs if outputs is not None else [output_features("m-1")]
    return {"schema": "epinoic.integration.routing-request.v1", "protocol": PROTOCOL, "port_version": "1.0",
            "ids": {"task_id": "t_" + "0" * 31 + "1", "request_id": "a_" + "0" * 31 + "1"},
            "request": {"subjects": ["History"], "stem": any(o["stem"] for o in outputs), "task_type": "short_answer", "course_level": "unknown",
                        "items": [{"item_id": "i1", "kind": "question", "required": True, "command_term": "to what extent", "level": 3}],
                        "constraints": [{"constraint_id": "k1", "kind": "max_words", "value": "350"}],
                        "supplied_texts": [{"document_id": "src-a", "sha256": "c3" * 32, "chars": 1200}], "user_text_sha256": "d4" * 32},
            "outputs": outputs, "topology": topology or {"kind": "single", "sources": [], "synthesis": None},
            "limits": {"max_instances": max_instances, "profiles": list(profiles)}}


def combined_request(**kw: Any) -> dict:
    outs = [output_features("m-h"), output_features("m-e", agent_id="english-a-literature", subject="English A: Literature", branch="english"),
            output_features("m-s", role="synthesis", agent_id="synthesis", subject="History", branch="history")]
    return routing_request(outs, topology={"kind": "combined", "sources": ["m-h", "m-e"], "synthesis": "m-s"}, **kw)


def plan_for(request: dict, entries: list[dict], *, identity: Optional[dict] = None) -> dict:
    """A router plan over ``request`` with the given transfer entries (cost filled in, totals summed)."""
    from epinoic_logic.integration.router_port import request_digest
    transfers = []
    for e in entries:
        t = {"transfer_key": e["transfer_key"], "method": e.get("method", "IN_DEPTH"), "reviews": e.get("reviews", 1), "parts": e.get("parts", 1),
             "instances": e.get("instances", e.get("reviews", 1) * e.get("parts", 1)), "profile": e.get("profile", "fast"), "tier": e.get("tier", "cheapest"),
             "sources": e.get("sources", []), "context": e.get("context"), "reasons": e.get("reasons", ["cost_cheapest"]),
             "features_used": e.get("features_used", ["size"]), "estimated_cost": e.get("estimated_cost", {"tokens": 60000, "seconds": 45})}
        for k in [k for k in e if k.startswith("_")]:
            t[k[1:]] = e[k]
        transfers.append(t)
    tokens = sum(t["estimated_cost"]["tokens"] for t in transfers if t.get("estimated_cost"))
    seconds = sum(t["estimated_cost"]["seconds"] for t in transfers if t.get("estimated_cost"))
    return {"schema": "epinoic.integration.routing-plan.v1", "protocol": PROTOCOL, "port_version": "1.0", "origin": "router",
            "plan_id": "plan-router-test", "ids": dict(request["ids"]), "request_sha256": request_digest(request),
            "router": dict(identity or ROUTER_IDENTITY), "transfers": transfers,
            "totals": {"instances": sum(t["instances"] for t in transfers), "estimated_cost": {"tokens": tokens, "seconds": seconds}}}


NFOLD_CONTEXT = {"scope": "request", "contents": "validated_outcomes", "max_bytes": 32768, "discard": "after_request"}


def write_router_module(tmp_path: Path, monkeypatch: Any, name: str, *, plan_body: Optional[str] = None) -> str:
    """A minimal flash router written as a separate module (JSON text in, JSON text out), for attachment tests: it plans
    every transfer at the floor (IN_DEPTH, or DUPLICATE x2 when the receipt has error codes) unless ``plan_body`` is given."""
    body = plan_body or (
        "    req = json.loads(request_json)\n"
        "    ts = []\n"
        "    for o in req['outputs']:\n"
        "        risky = bool(o['receipt']['error_codes']) or o['receipt']['status'] == 'REJECTED' or o['repeated_faults'] > 0\n"
        "        n = 2 if risky else 1\n"
        "        ts.append({'transfer_key': o['transfer_key'], 'method': 'DUPLICATE' if risky else 'IN_DEPTH', 'reviews': n, 'parts': 1,\n"
        "                   'instances': n, 'profile': 'standard', 'tier': 'cheapest', 'sources': [], 'context': None,\n"
        "                   'reasons': ['risk_error_findings' if risky else 'cost_cheapest'], 'features_used': ['receipt'],\n"
        "                   'estimated_cost': {'tokens': 1000 * n, 'seconds': 10 * n}})\n"
        "    digest = hashlib.sha256(json.dumps(req, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()\n"
        "    return json.dumps({'schema': 'epinoic.integration.routing-plan.v1', 'protocol': 'epinoic.integration.v1', 'port_version': '1.0',\n"
        "                       'origin': 'router', 'plan_id': 'plan-' + digest[:16], 'ids': req['ids'], 'request_sha256': digest,\n"
        "                       'router': IDENTITY, 'transfers': ts,\n"
        "                       'totals': {'instances': sum(t['instances'] for t in ts), 'estimated_cost': {'tokens': sum(t['estimated_cost']['tokens'] for t in ts), 'seconds': sum(t['estimated_cost']['seconds'] for t in ts)}}})\n")
    src = ("import hashlib, json\n"
           f"IDENTITY = {ROUTER_IDENTITY!r}\n"
           f"HELLO = {router_hello()!r}\n"
           "def hello():\n    return json.dumps(HELLO)\n"
           "def plan(request_json):\n" + body)
    (tmp_path / f"{name}.py").write_text(src)
    monkeypatch.syspath_prepend(str(tmp_path))
    return name
