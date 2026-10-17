"""Building the flash router's request from a checks call's own records (``integration/PROTOCOL.md`` section 7a.2).

The request carries features only: the task's subjects, whether it is STEM, its request items and constraints (ids,
kinds, command terms; never their text) and its supplied texts by digest; per output its size, its claims, the engine
statuses of its claims and checks, its receipt's finding codes, its named diagnostics, its unverified dependencies,
the peer relays and the repeated faults that concern it; and the topology. Nothing here carries an answer, a claim
text, a finding message or an overseer finding: the request is validated by ``router_port.check_request``, which
refuses anything a blind dossier hides.

The repeated-fault counts come from the overseer port (``repeats``), and the named diagnostics from the argument
diagnostics: both are connected in phase 2, and the builder takes them as arguments rather than inventing them.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from .protocol import FORMAL_VALUES, NOT_ATTEMPTED, PROTOCOL, dump
from .router_port import PORT_VERSION, REQUEST_SCHEMA, RoutingRequest, check_request
from .verifier import claim_is_eligible

__all__ = ["OutputRecord", "build_routing_request", "output_features"]

_STEM_BRANCHES = frozenset({"sciences", "mathematics", "computer_science"})
_ITEM_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_DOC_ID = re.compile(r"^[A-Za-z0-9._:/-]{1,200}$")
_TERM = re.compile(r"^[a-z][a-z ]{0,39}$")
_VALUE = re.compile(r"^[0-9]{1,9}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9]{0,15}(?:-[A-Z0-9]{1,16}){1,4}(?:/[A-Z][A-Z0-9]{0,15}(?:-[A-Z0-9]{1,16}){1,4})?$")


@dataclass(frozen=True)
class OutputRecord:
    """One transfer as the checks call recorded it: the delivered (or rejected) answer and its receipt."""
    transfer_key: str
    role: str
    agent_id: str
    subject: str
    receipt: Any
    claims: Sequence[Any]
    text: str
    repeated_faults: int = 0
    peer_relays: int = 0
    diagnostics: Sequence[str] = field(default_factory=tuple)


def _stable_id(value: str, pattern: re.Pattern, prefix: str) -> str:
    return value if pattern.match(value) else f"{prefix}-{hashlib.sha256(value.encode('utf-8', 'surrogatepass')).hexdigest()[:16]}"


def output_features(rec: OutputRecord) -> dict:
    receipt = rec.receipt
    statuses: dict[str, int] = {}
    unverified = 0
    for o in getattr(receipt, "outcomes", []) or []:
        s = o.display_status.value
        statuses[s] = statuses.get(s, 0) + 1
        if o.verification is not None:
            unverified += len(o.verification.unverified_dependencies) + len(o.verification.ungrounded_dependencies)
    for fc in getattr(receipt, "formal_checks", []) or []:
        s = fc.formal_status if fc.formal_status in FORMAL_VALUES else NOT_ATTEMPTED
        statuses[s] = statuses.get(s, 0) + 1
    findings = getattr(receipt, "findings", []) or []
    errors = sorted({f.code for f in findings if f.severity == "error" and _CODE.match(f.code) and not f.code.startswith("OVS-")})
    warnings = sorted({f.code for f in findings if f.severity == "warning" and _CODE.match(f.code) and not f.code.startswith("OVS-")})
    claims = list(rec.claims)
    text = rec.text or ""
    branch = getattr(receipt, "branch", None) or "generic"
    return {
        "transfer_key": rec.transfer_key, "role": rec.role, "agent_id": rec.agent_id, "subject": rec.subject, "branch": branch,
        "stem": branch in _STEM_BRANCHES,
        "size": {"chars": len(text), "words": len(text.split()), "paragraphs": len([p for p in re.split(r"\n\s*\n", text) if p.strip()])},
        "claims": {"total": len(claims), "material": sum(1 for c in claims if c.materiality == "material"),
                   "eligible": sum(1 for c in claims if claim_is_eligible(c)),
                   "translated": sum(1 for o in getattr(receipt, "outcomes", []) or [] if o.translation.problem is not None)},
        "engine_statuses": statuses,
        "receipt": {"status": receipt.status.value, "error_codes": errors, "warning_codes": warnings},
        "diagnostics": sorted({d for d in rec.diagnostics if isinstance(d, str) and _CODE.match(d) and "/" not in d and not d.startswith("OVS-")}),
        "unverified_dependencies": min(unverified, 4096), "peer_relays": rec.peer_relays, "repeated_faults": rec.repeated_faults,
    }


def build_routing_request(*, task_id: str, request_id: str, task_request: Any, subjects: Sequence[str], outputs: Sequence[OutputRecord],
                          topology: Mapping[str, Any], max_instances: int, profiles: Sequence[str]) -> RoutingRequest:
    """The routing request of one checks call, validated (``KIT-RT-014``/``-011`` on anything out of contract)."""
    items = []
    for it in getattr(task_request, "items", []) or []:
        term = (it.command_term or "").strip().lower()
        items.append({"item_id": _stable_id(it.item_id, _ITEM_ID, "item"), "kind": it.kind, "required": it.required,
                      "command_term": term if _TERM.match(term) else None, "level": it.level})
    constraints = []
    for c in getattr(task_request, "constraints", []) or []:
        value = (c.value or "").strip()
        constraints.append({"constraint_id": _stable_id(c.constraint_id, _ITEM_ID, "constraint"), "kind": c.kind, "value": value if _VALUE.match(value) else None})
    texts = []
    for t in getattr(task_request, "supplied_texts", []) or []:
        texts.append({"document_id": _stable_id(t.document_id, _DOC_ID, "doc"),
                      "sha256": hashlib.sha256(t.text.encode("utf-8", "surrogatepass")).hexdigest(), "chars": len(t.text)})
    outs = [output_features(o) for o in outputs]
    raw = {
        "schema": REQUEST_SCHEMA, "protocol": PROTOCOL, "port_version": PORT_VERSION,
        "ids": {"task_id": task_id, "request_id": request_id},
        "request": {"subjects": list(subjects), "stem": any(o["stem"] for o in outs),
                    "task_type": task_request.task_type if re.match(r"^[a-z][a-z0-9_]{0,63}$", task_request.task_type) else "other",
                    "course_level": task_request.course_level or "unknown", "items": items, "constraints": constraints,
                    "supplied_texts": texts, "user_text_sha256": task_request.user_input_sha256},
        "outputs": outs,
        "topology": dict(topology),
        "limits": {"max_instances": max_instances, "profiles": list(profiles)},
    }
    return check_request(raw)
