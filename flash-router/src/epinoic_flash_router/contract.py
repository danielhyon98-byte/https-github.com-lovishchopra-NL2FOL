"""What the flash router reads of a request, checked before it plans one, so that a request it cannot read and a fault
of its own code are told apart.

A request this router reads is JSON text (no ``NaN`` or ``Infinity``, no member named twice in one object, no string it
cannot write as UTF-8) whose every member the planners read has the type and the range the router port gives it, every
count an integer the protocol's JSON carries (at most :data:`MAX_SAFE_INTEGER`, 2^53 - 1):

* a ``routing-request.v1`` (:func:`check_routing_request`, the service's): its ``ids`` (two strings); ``request``, whose
  ``supplied_texts`` (when present) each carry ``chars``; at least one output, each with its ``transfer_key`` (no key
  named twice: port rule 1, every transfer is one output), ``stem``, ``size`` (``chars``, ``words``), ``claims``
  (``translated``), ``engine_statuses`` (a count per status), ``receipt`` (a ``status`` of the port's three, its
  ``error_codes`` and ``warning_codes``), ``diagnostics``, ``unverified_dependencies`` and ``repeated_faults``; the
  ``topology`` (its ``kind`` of the port's three, its ``sources`` for a combined answer, its ``synthesis``); the
  ``limits`` (``max_instances`` of at least 1, at least one profile of ``standard`` and ``fast``);
* a ``pool-routing-request.v1`` (:func:`check_pool_request`, the overseer pool's): a pool port version this router
  speaks (1.2 only with the flash decision maker's data); its items, each with an ``item_id`` named once in the batch,
  ``repeated_faults``, ``risk_signals``, ``risk_records`` and, when present, ``advised``; at 1.2 each item's
  ``features`` (``chars``, ``stem``, ``translations``) when present and a combined answer's ``sources`` and ``merged``
  part (each part's ``repeated_faults``, ``risk_signals`` and ``features``); the ``limits`` (``max_instances`` and
  ``per_instance_quota`` of at least 1, at least one profile).

Anything else is refused with :class:`RequestError` (a ``ValueError``), whose reason names the member and the rule it
breaks, never a value of the request. Once a request passes, the planners cannot fail on it: an exception they raise
is a fault of the router's own code, which the runner reports as such (exit status 4), never as an input it cannot read
(exit status 3).

These checks are no stricter than the router port: they read only the members the planners read, and each rule here is
implied by the port's own validation of that member (the port's is the same or stronger), so every request a caller
sends (validated against the router port before it is sent) passes and is planned exactly as before. Members the
planners do not read are left to the callers, and the number of outputs, items or sources is not bounded (a request far
beyond the port's bounds is planned, in one pass). One pass over the request, and one serialisation (the canonical text
its digest is taken of, returned for the planner to digest): linear in the request's size. Standard library only.
"""
from __future__ import annotations

import json
from typing import Any, Sequence

from .rules import canonical

__all__ = ["RequestError", "MAX_SAFE_INTEGER", "PROFILES", "TOPOLOGY_KINDS", "RECEIPT_STATUSES", "decode", "check_routing_request",
           "check_pool_request"]

#: The largest integer the protocol's JSON carries (2^53 - 1): every count the planners read is within it, so what they
#: compute from the counts (sizes, tokens, totals) stays an integer canonical JSON writes.
MAX_SAFE_INTEGER = 2**53 - 1
#: The profiles a request may offer (the router's hellos name both).
PROFILES: tuple[str, ...] = ("standard", "fast")
#: The topologies of a routing request (the router port's).
TOPOLOGY_KINDS: tuple[str, ...] = ("single", "duplicate", "combined")
#: The receipt statuses a routing request's output carries (the router port's).
RECEIPT_STATUSES: tuple[str, ...] = ("ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED")

_MISSING = object()


class RequestError(ValueError):
    """The request is not one this router reads. Its reason names the member and the rule it breaks, never a value of
    the request. A ``ValueError``, so a caller that refused a ``ValueError`` before still refuses it."""


# ----------------------------------------------------------------------------------------------- the JSON text


def _no_constant(name: str) -> Any:
    raise RequestError(f"the request holds {name}, which is not JSON")


def _no_repeats(pairs: list) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise RequestError("the request names one member twice in one object")
        out[key] = value
    return out


def decode(request_json: Any) -> Any:
    """The request's JSON text, decoded; :class:`RequestError` when it is not JSON text this router reads (text or
    bytes, no ``NaN`` or ``Infinity``, no member named twice in one object, nested no deeper than the decoder reads)."""
    if not isinstance(request_json, (str, bytes, bytearray)):
        raise RequestError("the request is not JSON text")
    try:
        return json.loads(request_json, parse_constant=_no_constant, object_pairs_hook=_no_repeats)
    except RequestError:
        raise
    except RecursionError:
        raise RequestError("the request is nested too deep to decode") from None
    except json.JSONDecodeError as exc:
        raise RequestError(f"the request is not JSON text (line {exc.lineno}, column {exc.colno})") from None
    except ValueError:  # bytes in no JSON encoding, an integer too long to convert
        raise RequestError("the request is not JSON text") from None


# ----------------------------------------------------------------------------------------------- the members


def _object(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise RequestError(f"{where} is a JSON object")
    return value


def _list(value: Any, where: str, *, what: str = "a list") -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise RequestError(f"{where} is {what}")
    return value


def _integer(value: Any, where: str, minimum: int = 0) -> None:
    if type(value) is not int or not minimum <= value <= MAX_SAFE_INTEGER:
        raise RequestError(f"{where} is an integer from {minimum} to {MAX_SAFE_INTEGER}")


def _boolean(value: Any, where: str) -> None:
    if type(value) is not bool:
        raise RequestError(f"{where} is true or false")


def _string(value: Any, where: str) -> None:
    if type(value) is not str:
        raise RequestError(f"{where} is a string")


def _strings(value: Any, where: str) -> None:
    if not isinstance(value, (list, tuple)) or not all(type(x) is str for x in value):
        raise RequestError(f"{where} is a list of strings")


def _one_of(value: Any, names: Sequence[str], where: str) -> None:
    if type(value) is not str or value not in names:
        raise RequestError(f"{where} is one of {', '.join(names)}")


def _profiles(limits: dict) -> None:
    profiles = limits.get("profiles", _MISSING)
    if not isinstance(profiles, (list, tuple)) or not profiles or not all(type(p) is str and p in PROFILES for p in profiles):
        raise RequestError(f"limits.profiles is a list of at least one of {', '.join(PROFILES)}")


def _digest_text(request: dict, what: str) -> bytes:
    """The canonical text of the request as UTF-8 (what its digest is taken of): RequestError for a value that is not
    JSON or a string with a lone surrogate, which no canonical text can carry."""
    try:
        return canonical(request).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise RequestError(f"{what} is not JSON data the router can digest (a value that is not JSON, or a string with a lone surrogate)") from None


# ----------------------------------------------------------------------------------------------- the service's request


def _output(o: Any, where: str) -> str:
    o = _object(o, where)
    key = o.get("transfer_key", _MISSING)
    _string(key, f"{where}.transfer_key")
    _boolean(o.get("stem", _MISSING), f"{where}.stem")
    size = _object(o.get("size", _MISSING), f"{where}.size")
    _integer(size.get("chars", _MISSING), f"{where}.size.chars")
    _integer(size.get("words", _MISSING), f"{where}.size.words")
    claims = _object(o.get("claims", _MISSING), f"{where}.claims")
    _integer(claims.get("translated", _MISSING), f"{where}.claims.translated")
    statuses = _object(o.get("engine_statuses", _MISSING), f"{where}.engine_statuses")
    if not all(type(n) is int and 0 <= n <= MAX_SAFE_INTEGER for n in statuses.values()):
        raise RequestError(f"{where}.engine_statuses counts each status with an integer from 0 to {MAX_SAFE_INTEGER}")
    receipt = _object(o.get("receipt", _MISSING), f"{where}.receipt")
    _one_of(receipt.get("status", _MISSING), RECEIPT_STATUSES, f"{where}.receipt.status")
    _strings(receipt.get("error_codes", _MISSING), f"{where}.receipt.error_codes")
    _strings(receipt.get("warning_codes", _MISSING), f"{where}.receipt.warning_codes")
    _strings(o.get("diagnostics", _MISSING), f"{where}.diagnostics")
    _integer(o.get("unverified_dependencies", _MISSING), f"{where}.unverified_dependencies")
    _integer(o.get("repeated_faults", _MISSING), f"{where}.repeated_faults")
    return key


def check_routing_request(request: Any) -> bytes:
    """Check a parsed ``routing-request.v1`` (the members the port planner reads, module docstring) and return its
    canonical text as UTF-8, the text its digest is taken of. :class:`RequestError` when this router does not read it."""
    req = _object(request, "the routing request")
    ids = _object(req.get("ids", _MISSING), "ids")
    _string(ids.get("task_id", _MISSING), "ids.task_id")
    _string(ids.get("request_id", _MISSING), "ids.request_id")
    features = _object(req.get("request", _MISSING), "request")
    if "supplied_texts" in features:
        for k, t in enumerate(_list(features["supplied_texts"], "request.supplied_texts")):
            _integer(_object(t, f"request.supplied_texts[{k}]").get("chars", _MISSING), f"request.supplied_texts[{k}].chars")
    outputs = _list(req.get("outputs", _MISSING), "outputs", what="a list of at least one output")
    if not outputs:
        raise RequestError("outputs is a list of at least one output")
    keys = {_output(o, f"outputs[{k}]") for k, o in enumerate(outputs)}
    if len(keys) != len(outputs):
        raise RequestError("the routing request names one transfer key twice: every transfer is one output of the request")
    topology = _object(req.get("topology", _MISSING), "topology")
    kind = topology.get("kind", _MISSING)
    _one_of(kind, TOPOLOGY_KINDS, "topology.kind")
    if kind == "combined" or "sources" in topology:
        _strings(topology.get("sources", _MISSING), "topology.sources")
    if topology.get("synthesis") is not None:
        _string(topology["synthesis"], "topology.synthesis")
    limits = _object(req.get("limits", _MISSING), "limits")
    _integer(limits.get("max_instances", _MISSING), "limits.max_instances", 1)
    _profiles(limits)
    return _digest_text(req, "the routing request")


# ----------------------------------------------------------------------------------------------- the overseer pool's request


def _signals(part: dict, where: str) -> None:
    _integer(part.get("repeated_faults", _MISSING), f"{where}.repeated_faults")
    _strings(part.get("risk_signals", _MISSING), f"{where}.risk_signals")


def _features(value: Any, where: str) -> None:
    if value is None:
        return
    f = _object(value, where)
    _integer(f.get("chars", _MISSING), f"{where}.chars")
    _boolean(f.get("stem", _MISSING), f"{where}.stem")
    _integer(f.get("translations", _MISSING), f"{where}.translations")


def _part(value: Any, where: str) -> None:
    part = _object(value, where)
    _signals(part, where)
    _features(part.get("features"), f"{where}.features")


def check_pool_request(request: Any, *, versions: Sequence[str], decision: bool) -> bytes:
    """Check a parsed ``pool-routing-request.v1`` (the members the pool planner reads, module docstring) at one of the
    pool port ``versions`` this router answers (1.2 only when ``decision``: the data carry the flash decision maker), and
    return its canonical text as UTF-8, the text its digest is taken of. :class:`RequestError` when this router does
    not read it."""
    req = _object(request, "the pool routing request")
    version = req.get("port_version", _MISSING)
    if type(version) is not str or version not in versions:
        raise RequestError(f"port_version: this router reads pool port versions {', '.join(versions)}")
    v12 = version == "1.2"
    if v12 and not decision:
        raise RequestError("pool port 1.2 needs the flash decision maker's data (rules/3): this data directory plans pool port 1.1 only")
    seen: set[str] = set()
    for k, value in enumerate(_list(req.get("items", _MISSING), "items")):
        where = f"items[{k}]"
        it = _object(value, where)
        iid = it.get("item_id", _MISSING)
        _string(iid, f"{where}.item_id")
        if iid in seen:
            raise RequestError("the pool routing request names one item_id twice: every dossier is one item of the batch")
        seen.add(iid)
        _signals(it, where)
        _strings(it.get("risk_records", _MISSING), f"{where}.risk_records")
        if "advised" in it:
            _boolean(it["advised"], f"{where}.advised")
        if v12:
            _features(it.get("features"), f"{where}.features")
            sources = _list(it.get("sources", []), f"{where}.sources", what="a list of parts")
            for j, src in enumerate(sources):
                _part(src, f"{where}.sources[{j}]")
            if sources:
                _part(it.get("merged"), f"{where}.merged")
    limits = _object(req.get("limits", _MISSING), "limits")
    _integer(limits.get("max_instances", _MISSING), "limits.max_instances", 1)
    _integer(limits.get("per_instance_quota", _MISSING), "limits.per_instance_quota", 1)
    _profiles(limits)
    return _digest_text(req, "the pool routing request")
