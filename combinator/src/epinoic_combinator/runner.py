"""The runner: operates the combinator agent as a sub-agent on the cheapest tier, and lets out only what is in contract.

``run(input_doc, provider)`` takes one ``combinator-input.v1`` document (the service's request) and returns a
:class:`RunResult` holding exactly one of:

* ``output``: a ``combinator-output.v1`` document (its text is its canonical JSON), validated against the published
  contract (:mod:`.contract`) before it leaves: the schema, the closed transformation and certainty values, the
  request it answers, the pinned instruction pack, citations of source claims the input holds, and its size;
* ``refusal``: a ``combinator-refusal.v1`` document with a closed ``reason`` and its ``KIT-CB`` code.

The steps, each of which can only refuse:

1. the input is read as the port reads it (``input_not_json``, ``input_invalid``: ``KIT-CB-001``) and must name this
   release's instruction pack (``pack_mismatch``: ``KIT-CB-005``);
2. the provider must exist and be on the cheapest tier (``provider_unavailable``); it is called once with the pack's
   instructions and the request's sources (:mod:`.prompt`); whatever it raises is ``provider_failed``, anything but
   text is ``provider_no_text`` (all ``KIT-CB-002``);
3. the agent's text must be exactly one JSON object in the agent's format, ``{claims, dropped?, conflicts?}`` with
   ``{text, source_claim_ids, certainty, transformation}`` claims, ``{source_claim_ids, reason}`` dropped entries and
   ``{claim_ids, description}`` conflicts (prose or a code fence around it is ``output_not_json``; another key at any
   level, a missing key or a value of the wrong kind is ``output_invalid``; more than :data:`MAX_AGENT_OUTPUT_BYTES`
   is ``output_too_large``); a transformation outside the closed vocabulary is ``transformation_unknown``
   (``KIT-CB-003``), decided first, as the port decides it; a synthesized claim citing a source claim twice is
   ``output_invalid``; a citation of a claim the input does not hold is
   ``source_claim_unknown`` (``KIT-CB-004``); a synthesis text over the port's limit is ``output_too_large``
   (``KIT-CB-006``);
4. the runner wraps it into the port message (the request's ids, the pack's digest; ``evidence_refs`` null, so the
   service attaches the references it keeps) and checks the whole message once more against the contract.

Nothing here judges whether the synthesis is faithful: a dropped qualifier, an inflated certainty, a merged
contradiction, an invented figure, a wrong attribution, a carried self-certification or a verification label on a
claim is in contract and leaves; the hub, the independent checker of every synthesis, names it. ``run`` never raises: an unexpected error is the refusal
``internal_error``. No retry, no second call: one input, at most one provider call, one result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .contract import Contract, ContractUnavailable, Problem, load_contract
from .jsonio import JsonError, canonical_json, loads_strict
from .pack import TIER, Pack, PackUnavailable, load_pack
from .prompt import render
from .providers import CompletionRequest, Provider
from .schema import shown

__all__ = ["MAX_AGENT_OUTPUT_BYTES", "AGENT_OUTPUT_KEYS", "AGENT_CLAIM_KEYS", "AGENT_DROPPED_KEYS", "AGENT_CONFLICT_KEYS",
           "NO_PACK_SHA256", "RunResult", "run"]

#: The most of the agent's text the runner reads (UTF-8 bytes): more is ``output_too_large`` before any parsing.
MAX_AGENT_OUTPUT_BYTES = 262144
AGENT_OUTPUT_KEYS: tuple[str, ...] = ("claims", "dropped", "conflicts")
AGENT_CLAIM_KEYS: tuple[str, ...] = ("text", "source_claim_ids", "certainty", "transformation")
AGENT_DROPPED_KEYS: tuple[str, ...] = ("source_claim_ids", "reason")
AGENT_CONFLICT_KEYS: tuple[str, ...] = ("claim_ids", "description")
#: The pack digest a refusal names when this release's own pack cannot be read (an installation defect).
NO_PACK_SHA256 = "0" * 64

_OUTPUT_SCHEMA = "epinoic.integration.combinator-output.v1"
_REFUSAL_SCHEMA = "epinoic.integration.combinator-refusal.v1"
_PROTOCOL = "epinoic.integration.v1"


@dataclass(frozen=True)
class RunResult:
    """One run: the output in contract, or the named refusal, and the canonical JSON text of whichever it is."""
    output: Optional[dict]
    refusal: Optional[dict]
    text: str
    provider_calls: int = 0

    @property
    def ok(self) -> bool:
        return self.output is not None


def _detail(text: str, limit: int = 300) -> str:
    text = " ".join(str(text).split()) or "refused"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _refused(problem: Problem, ids: Optional[Mapping[str, str]], pack_sha256: str, contract: Optional[Contract], calls: int) -> RunResult:
    doc = {"schema": _REFUSAL_SCHEMA, "protocol": _PROTOCOL, "port_version": "1.0", "ids": dict(ids) if ids is not None else None,
           "instruction_pack_sha256": pack_sha256, "code": problem.code, "reason": problem.reason, "detail": _detail(problem.detail)}
    if contract is not None and contract.check_refusal(doc) is not None:  # a refusal out of contract is a defect of this release
        doc = {**doc, "ids": None, "code": "KIT-CB-002", "reason": "internal_error", "detail": "the combinator could not state its refusal in contract"}
    return RunResult(output=None, refusal=doc, text=canonical_json(doc), provider_calls=calls)


def _shape_problem(data: Mapping[str, Any]) -> Optional[Problem]:
    """The agent's own format, stricter than the port message it is wrapped into: exactly the keys it is told."""
    extra = [k for k in data if k not in AGENT_OUTPUT_KEYS]
    if extra:
        return Problem("KIT-CB-002", "output_invalid", f"the agent's output has {len(extra)} key(s) besides claims, dropped and conflicts "
                                                       f"({', '.join(shown(k) for k in extra[:3])})")
    if "claims" not in data:
        return Problem("KIT-CB-002", "output_invalid", "the agent's output has no claims")
    for key, wanted in (("claims", AGENT_CLAIM_KEYS), ("dropped", AGENT_DROPPED_KEYS), ("conflicts", AGENT_CONFLICT_KEYS)):
        items = data.get(key)
        if not isinstance(items, list):
            continue  # the contract names it
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue  # the contract names it
            extra = [k for k in item if k not in wanted]
            missing = [k for k in wanted if k not in item]
            if extra or missing:
                what = []
                if missing:
                    what.append("no " + ", ".join(missing))
                if extra:
                    what.append(f"{len(extra)} key(s) besides {', '.join(wanted)} ({', '.join(shown(k) for k in extra[:3])})")
                return Problem("KIT-CB-002", "output_invalid", f"{key}[{i}]: " + "; ".join(what))
    return None


def _agent_output(text: str, inp: Mapping[str, Any], pack: Pack, contract: Contract) -> tuple[Optional[dict], Optional[Problem]]:
    size = len(text.encode("utf-8", "surrogatepass"))
    if size > MAX_AGENT_OUTPUT_BYTES:
        return None, Problem("KIT-CB-006", "output_too_large", f"the agent wrote {size} UTF-8 bytes, more than {MAX_AGENT_OUTPUT_BYTES}")
    try:
        data = loads_strict(text)
    except JsonError as exc:
        return None, Problem("KIT-CB-002", "output_not_json", f"the agent's output is not exactly one protocol JSON object ({exc}); "
                                                              "nothing may come before or after it")
    if not isinstance(data, dict):
        return None, Problem("KIT-CB-002", "output_not_object", f"the agent's output is a JSON {type(data).__name__}, not an object")
    problem = contract.transformation_problem(data) or _shape_problem(data)
    if problem is not None:
        return None, problem
    claims = data["claims"]
    message = {
        "schema": _OUTPUT_SCHEMA, "protocol": _PROTOCOL, "port_version": contract.port_version, "ids": dict(inp["ids"]),
        "instruction_pack_sha256": pack.sha256,
        "claims": [{**c, "evidence_refs": None} if isinstance(c, dict) else c for c in claims] if isinstance(claims, list) else claims,
        "dropped": data.get("dropped", []), "conflicts": data.get("conflicts", []),
    }
    problem = contract.check_output(message, inp)
    return (None, problem) if problem is not None else (message, None)


def run(input_doc: Any, provider: Optional[Provider], *, pack: Optional[Pack] = None, contract: Optional[Contract] = None) -> RunResult:
    """Run the combinator agent once on ``input_doc`` (JSON text, bytes or a parsed object). Never raises."""
    calls = 0
    pack_sha = NO_PACK_SHA256
    ids: Optional[Mapping[str, str]] = None
    try:
        try:
            pack = pack if pack is not None else load_pack()
            pack_sha = pack.sha256
            contract = contract if contract is not None else load_contract()
        except (PackUnavailable, ContractUnavailable) as exc:
            return _refused(Problem("KIT-CB-002", "internal_error", str(exc)), None, pack_sha, None, calls)
        inp, problem = contract.check_input(input_doc)
        if problem is not None:
            return _refused(problem, None, pack_sha, contract, calls)
        ids = inp["ids"]
        if inp["instruction_pack"] != pack.identity():
            return _refused(Problem("KIT-CB-005", "pack_mismatch", f"the input pins the instruction pack {shown(inp['instruction_pack']['name'])} "
                                                                   f"{shown(inp['instruction_pack']['version'])} with another digest than this release's "
                                                                   f"{pack.name} {pack.version}"), ids, pack_sha, contract, calls)
        if provider is None:
            return _refused(Problem("KIT-CB-002", "provider_unavailable", "no provider is configured for the combinator agent"), ids, pack_sha, contract, calls)
        if getattr(provider, "tier", None) != TIER:
            return _refused(Problem("KIT-CB-002", "provider_unavailable", "the provider is not on the cheapest tier"), ids, pack_sha, contract, calls)
        request = CompletionRequest(tier=TIER, system=pack.instructions, user=render(inp), instruction_pack_sha256=pack.sha256,
                                    request_id=inp["ids"]["request_id"], max_output_bytes=MAX_AGENT_OUTPUT_BYTES)
        calls = 1
        try:
            text = provider.complete(request)
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # noqa: BLE001 - a provider that raises (SystemExit included) never raises into the caller
            return _refused(Problem("KIT-CB-002", "provider_failed", f"the provider raised {type(exc).__name__}"), ids, pack_sha, contract, calls)
        if not isinstance(text, str) or not text.strip():
            what = "empty text" if isinstance(text, str) else f"a value of type {type(text).__name__}"
            return _refused(Problem("KIT-CB-002", "provider_no_text", f"the provider returned {what}, not the agent's text"), ids, pack_sha, contract, calls)
        message, problem = _agent_output(text, inp, pack, contract)
        if problem is not None:
            return _refused(problem, ids, pack_sha, contract, calls)
        final = contract.check_output(message, inp)  # the last gate: nothing out of contract leaves
        if final is not None:
            return _refused(final, ids, pack_sha, contract, calls)
        return RunResult(output=message, refusal=None, text=canonical_json(message), provider_calls=calls)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - run never raises
        return _refused(Problem("KIT-CB-002", "internal_error", f"the combinator failed internally ({type(exc).__name__})"), ids, pack_sha, contract, calls)
