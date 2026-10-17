"""The specialist port ``epinoic.integration.specialist-answer.v1`` (``integration/PROTOCOL.md`` section 4).

The port wraps the specialist runtime's existing output and never changes it. The Worker builds an envelope only for
the outcome ``answer``; every other outcome maps to the website's own closed error without a checks call. The service
re-validates the envelope here: the result schema and the runtime contract (an accepted pair), the log projection of
that schema, the outcome, the gate status, the answer digest and the slug. A gate pass is a format precondition, never
evidence of verification (the runtime's own disclaimer). A self-certification key at the envelope's top level is refused.

:func:`envelope_for` is the Python mirror of the Worker's ``specialist-port.js`` projection, used by the agents driver
and by the tests on the recorded runtime fixtures.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from pydantic import ValidationError

from .canonical import CanonicalError, sha256_json, sha256_text
from .compat import COMPATIBILITY
from .errors import IntegrationError
from .protocol import PROTOCOL, SELF_CERTIFICATION_KEYS, SpecialistAnswer, dump

__all__ = ["ENVELOPE_SCHEMA", "ACCEPTED_PAIRS", "MAX_ANSWER_BYTES", "pair_for_result", "check_answer", "envelope_for", "log_projection"]

ENVELOPE_SCHEMA = "epinoic.integration.specialist-answer.v1"
#: result schema -> {"runtime": contract version, "log": log schema}, from ``COMPATIBILITY.json``.
ACCEPTED_PAIRS: Mapping[str, Mapping[str, str]] = {p["result"]: {"runtime": p["runtime"], "log": p["log"]} for p in COMPATIBILITY["specialist_pairs"]}
MAX_ANSWER_BYTES: int = COMPATIBILITY["limits"]["max_answer_bytes"]
#: Members of the runtime's log projection that never leave the Worker (the website's conversation id lives in ``turn``).
_STRIPPED_LOG_MEMBERS = ("turn", "usage")


def pair_for_result(result_schema: Any) -> Optional[Mapping[str, str]]:
    return ACCEPTED_PAIRS.get(result_schema) if isinstance(result_schema, str) else None


def _refuse(code: str, detail: str) -> IntegrationError:
    return IntegrationError(code, detail)


def check_answer(raw: Any, *, slug: Optional[str] = None) -> SpecialistAnswer:
    """Validate one envelope. Raises :class:`IntegrationError` with a ``KIT-REQ`` code naming the first problem, in the
    order of PROTOCOL.md section 4: shape, self-certification, schema and contract, log projection, outcome, gate,
    answer digest, slug. ``slug`` is the subject map's slug for the task; ``None`` skips only that last check."""
    if not isinstance(raw, dict):
        raise _refuse("KIT-REQ-001", "a specialist envelope must be a JSON object")
    certifying = sorted(SELF_CERTIFICATION_KEYS & set(raw))
    if certifying:
        raise _refuse("KIT-REQ-005", f"self-certification field(s) at the envelope's top level: {', '.join(certifying)}")
    if raw.get("schema") != ENVELOPE_SCHEMA or raw.get("protocol") != PROTOCOL:
        raise _refuse("KIT-REQ-001", "the envelope's schema or protocol is not epinoic.integration.specialist-answer.v1")
    runtime = raw.get("runtime")
    if not isinstance(runtime, dict):
        raise _refuse("KIT-REQ-001", "the envelope carries no runtime reference")
    pair = pair_for_result(runtime.get("schema"))
    if pair is None:
        raise _refuse("KIT-REQ-010", "the result schema is not an accepted specialist result schema")
    if runtime.get("contract_version") != pair["runtime"]:
        raise _refuse("KIT-REQ-011", "the runtime contract does not belong to the result schema (accepted pairs only)")
    log = raw.get("log")
    if not isinstance(log, dict):
        raise _refuse("KIT-REQ-001", "the envelope's log is not the runtime's log projection")
    if log.get("schema") != pair["log"] or log.get("resultSchema") != runtime.get("schema"):
        raise _refuse("KIT-REQ-010", "the log projection is not the one of the result schema")
    if log.get("contractVersion") != pair["runtime"]:
        raise _refuse("KIT-REQ-011", "the log projection names another runtime contract")
    stripped = [m for m in _STRIPPED_LOG_MEMBERS if m in log]
    if stripped:
        raise _refuse("KIT-REQ-001", f"the log projection still carries {', '.join(stripped)}, which never leave the Worker")
    if log.get("outcome") != "answer" or log.get("answerPresent") is not True:
        raise _refuse("KIT-REQ-012", "the specialist outcome is not an answer")
    gate = log.get("gate")
    if not isinstance(gate, dict) or gate.get("status") != "passed":
        raise _refuse("KIT-REQ-013", "the specialist runtime's gate did not pass")
    provenance = log.get("provenance")
    if not isinstance(provenance, dict):
        raise _refuse("KIT-REQ-001", "the log projection carries no provenance")
    if provenance.get("claims", None) is not None:
        raise _refuse("KIT-REQ-011", "provenance.claims is not null: claims are extracted by the translator's parsers, never by the runtime")
    answer = raw.get("answer")
    if isinstance(answer, str):
        try:
            size = len(answer.encode("utf-8"))
        except UnicodeEncodeError:
            raise _refuse("KIT-REQ-001", "the answer is not valid Unicode") from None
        if size > MAX_ANSWER_BYTES:
            raise _refuse("KIT-REQ-006", f"the answer exceeds {MAX_ANSWER_BYTES} UTF-8 bytes")
    try:
        env = SpecialistAnswer.model_validate(raw)
    except ValidationError as exc:
        raise _refuse("KIT-REQ-001", f"the envelope does not validate ({exc.error_count()} error(s))") from None
    try:
        digest = sha256_text(env.answer)
    except CanonicalError:
        raise _refuse("KIT-REQ-001", "the answer is not valid Unicode") from None
    if digest != env.answer_sha256:
        raise _refuse("KIT-REQ-014", "answer_sha256 is not the SHA-256 of the answer's UTF-8 bytes")
    if slug is not None and provenance.get("slug") != slug:
        raise _refuse("KIT-REQ-015", "the specialist's slug is not the subject map's slug for this task")
    return env


def log_projection(redacted: Mapping[str, Any]) -> dict:
    """The envelope's ``log``: the runtime's own ``redactForLog(result)`` without its ``turn`` and ``usage`` members."""
    return {k: v for k, v in redacted.items() if k not in _STRIPPED_LOG_MEMBERS}


def envelope_for(result: Mapping[str, Any], redacted: Mapping[str, Any], *, agent_id: str) -> dict:
    """The envelope of one frozen runtime result whose outcome is ``answer`` (the Python mirror of the Worker's
    projection). ``redacted`` is the runtime's own ``redactForLog(result)``. Raises :class:`IntegrationError` for a
    result the port does not accept (``KIT-REQ-010``/``-011``/``-012``), never coerces one."""
    pair = pair_for_result(result.get("schema"))
    if pair is None:
        raise _refuse("KIT-REQ-010", "the result schema is not an accepted specialist result schema")
    if result.get("contractVersion") != pair["runtime"]:
        raise _refuse("KIT-REQ-011", "the runtime contract does not belong to the result schema")
    if result.get("outcome") != "answer" or not isinstance(result.get("answer"), str):
        raise _refuse("KIT-REQ-012", "the specialist outcome is not an answer")
    env = {
        "schema": ENVELOPE_SCHEMA,
        "protocol": PROTOCOL,
        "agent_id": agent_id,
        "runtime": {"schema": result["schema"], "contract_version": result["contractVersion"]},
        "log": log_projection(redacted),
        "answer": result["answer"],
        "answer_sha256": sha256_text(result["answer"]),
        "result_sha256": sha256_json(result),
    }
    return dump(check_answer(env))
