"""The provider interface the runner operates the combinator agent through, and the deterministic fakes of this release.

A provider is the model call: it receives a :class:`CompletionRequest` (the pack's instructions, the agent's message,
the tier) and returns the agent's text. Which model answers is the provider's own configuration, set by its owner
(decision D23 of the translator's integration kit: no model identifier is approved, so none is named here, in the pack
or in any message). The runner only accepts a provider on the cheapest tier and treats whatever it returns as untrusted
text: anything out of contract is a named refusal.

This release has **no live provider**: nothing here opens a network connection or reads a credential. The fakes are for
tests and simulations:

* :class:`ScriptedProvider` answers with the texts it is given, one per call (a text, a callable of the request, or an
  exception to raise), and records every request;
* :class:`FaithfulFakeProvider` writes the faithful synthesis of its input deterministically: every source claim that
  is not a note carried word for word with its own certainty, every note (role ``other``) listed in ``dropped``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Union, runtime_checkable

__all__ = ["CompletionRequest", "Provider", "ScriptedProvider", "FaithfulFakeProvider", "NOTE_REASON"]

#: The reason the faithful fake gives for a note it leaves out.
NOTE_REASON = "a note of the specialist (role other: a label, a self-report or a remark about the answer), not a claim of the answer"


@dataclass(frozen=True)
class CompletionRequest:
    """One call of the combinator agent."""
    tier: str
    system: str
    user: str
    instruction_pack_sha256: str
    request_id: str
    max_output_bytes: int


@runtime_checkable
class Provider(Protocol):
    """A model call on a tier. ``complete`` returns the agent's text; anything it raises is the provider's failure."""
    name: str
    tier: str

    def complete(self, request: CompletionRequest) -> str: ...


Scripted = Union[str, bytes, None, BaseException, Callable[[CompletionRequest], Any]]


class ScriptedProvider:
    """Deterministic fake: answers each call with the next scripted response (no response left is a failure)."""
    name = "scripted-fake"
    tier = "cheapest"

    def __init__(self, *responses: Scripted):
        self._responses = list(responses)
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Any:
        self.requests.append(request)
        if not self._responses:
            raise RuntimeError("the scripted provider has no response left")
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return response(request)
        return response


class FaithfulFakeProvider:
    """Deterministic fake combinator: the faithful synthesis of the request's sources (see the module docstring)."""
    name = "faithful-fake"
    tier = "cheapest"

    def __init__(self) -> None:
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        view = json.loads(request.user)
        claims: list[dict] = []
        dropped: list[dict] = []
        for source in view["sources"]:
            for c in source["claims"]:
                if c["role"] == "other":
                    dropped.append({"source_claim_ids": [c["claim_id"]], "reason": NOTE_REASON})
                else:
                    claims.append({"text": c["text"], "source_claim_ids": [c["claim_id"]], "certainty": c["certainty"], "transformation": "carried"})
        out: dict[str, Any] = {"claims": claims}
        if dropped:
            out["dropped"] = dropped
        return json.dumps(out, ensure_ascii=False)
