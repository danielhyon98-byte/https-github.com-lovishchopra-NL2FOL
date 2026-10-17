"""Validation of a checks-port request ``epinoic.integration.turn-check.v1`` (``integration/PROTOCOL.md`` section 5).

Step 1 of the service's processing order: validate the envelope and the answers. On failure the service answers HTTP 400
with the ``KIT-REQ`` code of the first problem, and nothing runs. The checks follow the order of PROTOCOL.md: size,
strict JSON, self-certification, schema, mode, policy, ids, budget, answers per mode, the task against the subject map,
each specialist envelope (``specialist_port.check_answer``), the full model, the user-text digest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from pydantic import ValidationError

from .canonical import CanonicalError, check_value, loads_strict, sha256_text
from .compat import COMPATIBILITY, SUBJECT_MAP
from .errors import IntegrationError
from .protocol import ID_PATTERN, MODES, POLICIES, PROTOCOL, SELF_CERTIFICATION_KEYS, TurnCheckRequest
from .specialist_port import check_answer

import re

__all__ = ["REQUEST_SCHEMA", "ANSWERS_PER_MODE", "RequestLimits", "subject_entry", "check_request", "agent_slug"]

REQUEST_SCHEMA = "epinoic.integration.turn-check.v1"
ANSWERS_PER_MODE: Mapping[str, int] = {"single": 1, "duplicate": 2, "combined": 2}
_ID_RE = re.compile(ID_PATTERN)


@dataclass(frozen=True)
class RequestLimits:
    modes: Sequence[str]
    max_body_bytes: int
    checks_min_ms: int
    checks_max_ms: int
    max_user_text_bytes: int = COMPATIBILITY["limits"]["max_user_text_bytes"]


def subject_entry(*, slug: Optional[str], route: Optional[str], service_env: str) -> Optional[Mapping[str, Any]]:
    """The subject-map row for a task: by website route (whose environments must include the service's environment) or,
    for a call without a website route (the agents driver, service-side checks), by slug in a row usable by the service."""
    for e in SUBJECT_MAP["entries"]:
        if route is not None:
            if e["route"] == route and e["slug"] == slug and service_env in e["environments"]:
                return e
        elif e["slug"] == slug and ("service" in e["environments"] or service_env in e["environments"]):
            return e
    return None


def agent_slug(agent_id: str, mode: str) -> str:
    """The slug an agent id stands for: ``<slug>@a`` and ``<slug>@b`` in duplicate mode, the slug itself otherwise."""
    return agent_id.rsplit("@", 1)[0] if mode == "duplicate" else agent_id


def _nested_verified(obj: Any) -> bool:
    stack = [obj]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("verified") is True:
                return True
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return False


def check_request(raw: Any, limits: RequestLimits, *, service_env: str) -> TurnCheckRequest:
    if isinstance(raw, (bytes, bytearray, str)):
        size = len(raw.encode("utf-8", errors="surrogatepass")) if isinstance(raw, str) else len(raw)
        if size > limits.max_body_bytes:
            raise IntegrationError("KIT-REQ-006", f"the request exceeds {limits.max_body_bytes} bytes")
        try:
            raw = loads_strict(raw)
        except CanonicalError as exc:
            raise IntegrationError("KIT-REQ-001", f"the request is not protocol JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise IntegrationError("KIT-REQ-001", "the request is a JSON object")
    try:
        check_value(raw)
    except CanonicalError as exc:
        raise IntegrationError("KIT-REQ-001", f"the request is not protocol JSON: {exc}") from None
    certifying = sorted(SELF_CERTIFICATION_KEYS & set(raw))
    if certifying:
        raise IntegrationError("KIT-REQ-005", f"self-certification field(s) at the request's top level: {', '.join(certifying)}")
    if _nested_verified(raw):
        raise IntegrationError("KIT-REQ-005", "a nested verified: true is a self-certification; only deterministic checks verify")
    if raw.get("schema") != REQUEST_SCHEMA or raw.get("protocol") != PROTOCOL:
        raise IntegrationError("KIT-REQ-001", "the request's schema or protocol is not epinoic.integration.turn-check.v1")
    mode = raw.get("mode")
    if mode not in MODES or mode not in limits.modes:
        raise IntegrationError("KIT-REQ-002", "the mode is not one the service's capabilities list")
    if raw.get("policy") not in POLICIES:
        raise IntegrationError("KIT-REQ-003", "the policy is not a named delivery policy")
    ids = raw.get("ids")
    if (not isinstance(ids, dict) or set(ids) != {"task_id", "request_id"}
            or not all(isinstance(ids[k], str) and _ID_RE.match(ids[k]) for k in ("task_id", "request_id"))):
        raise IntegrationError("KIT-REQ-004", "ids must be {task_id, request_id}, each an id")
    budget = raw.get("budget_ms")
    if type(budget) is not int or not limits.checks_min_ms <= budget <= limits.checks_max_ms:
        raise IntegrationError("KIT-REQ-007", f"budget_ms must be an integer from {limits.checks_min_ms} to {limits.checks_max_ms}")
    answers = raw.get("answers")
    if not isinstance(answers, list) or len(answers) != ANSWERS_PER_MODE[mode]:
        raise IntegrationError("KIT-REQ-002", f"mode {mode} takes {ANSWERS_PER_MODE[mode]} answer(s)")
    task = raw.get("task")
    if not isinstance(task, dict):
        raise IntegrationError("KIT-REQ-001", "the request carries no task")
    user_text = task.get("user_text")
    if isinstance(user_text, str):
        try:
            if len(user_text.encode("utf-8")) > limits.max_user_text_bytes:
                raise IntegrationError("KIT-REQ-006", f"the user text exceeds {limits.max_user_text_bytes} UTF-8 bytes")
        except UnicodeEncodeError:
            raise IntegrationError("KIT-REQ-001", "the user text is not valid Unicode") from None
    entry = subject_entry(slug=task.get("slug"), route=task.get("route"), service_env=service_env)
    if entry is None or task.get("subject") != entry["subject"]:
        raise IntegrationError("KIT-REQ-015", "the task's route, slug and subject are not a row of the subject map for this environment")
    agent_ids = [a.get("agent_id") if isinstance(a, dict) else None for a in answers]
    slug = entry["slug"]
    if mode == "single":
        expected_ids, slugs = [slug], [slug]
    elif mode == "duplicate":
        expected_ids, slugs = [f"{slug}@a", f"{slug}@b"], [slug, slug]
    else:
        second = agent_ids[1] if isinstance(agent_ids[1], str) else ""
        other = subject_entry(slug=second, route=None, service_env=service_env)
        if other is None or second == slug:
            raise IntegrationError("KIT-REQ-015", "a combined answer names two different mapped specialists")
        expected_ids, slugs = [slug, second], [slug, second]
    if agent_ids != expected_ids:
        raise IntegrationError("KIT-REQ-001", f"mode {mode} names its agents {expected_ids}")
    for env, expected_slug in zip(answers, slugs):
        check_answer(env, slug=expected_slug)
    try:
        req = TurnCheckRequest.model_validate(raw)
    except ValidationError as exc:
        raise IntegrationError("KIT-REQ-001", f"the request does not validate ({exc.error_count()} error(s))") from None
    try:
        if sha256_text(req.task.user_text) != req.task.user_text_sha256:
            raise IntegrationError("KIT-REQ-001", "user_text_sha256 is not the digest of the user text")
    except CanonicalError:
        raise IntegrationError("KIT-REQ-001", "the user text is not valid Unicode") from None
    return req
