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
* :class:`FaithfulFakeProvider` writes the faithful synthesis of its input deterministically, as the instructions ask
  (pack 1.3): every source claim that is not a note carried word for word with its own certainty; every note (role
  ``other``) listed in ``dropped``, except a note that declines or defers the work the student asked for
  (:func:`withheld_work`, rule 7), which is carried word for word like a claim so that the student still learns that
  the work was withheld (round 9, integrated round c2: the ps-t15 synthesis dropped the specialist's decline of the
  proposal and the student never read it).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, Union, runtime_checkable

__all__ = ["CompletionRequest", "Provider", "ScriptedProvider", "FaithfulFakeProvider", "NOTE_REASON", "withheld_work"]

#: The reason the faithful fake gives for a note it leaves out.
NOTE_REASON = "a note of the specialist (role other: a label, a self-report or a remark about the answer), not a claim of the answer"

# The faithful fake's reading of rule 7 (a decline or a deferral of the requested work). It is the fake's, never a check:
# the runner never reads faithfulness and the hub reads a synthesis with its own rules. It follows the forms the hub records
# as a decline or a deferral (the translator's ``adapters.markdown.declined_deliverable`` and ``channel.bus._DEFERRAL_RE``:
# the first three sentences of the first paragraph, no digit in a declining sentence, the same verbs and deferred
# objects), so the faithful fake carries what the hub reads as withheld work and nothing else; this package never imports
# the translator, so the forms are restated here, with every blank run bounded. Every pattern is anchored at a sentence or
# line start and every gap is bounded and stops at a sentence end, so a reading is linear in the text.
#: A sentence that declines part of the work, read from its start: "I can't write your introduction ...", "I cannot answer
#: part (c).", "I will not complete the essay ...".
_DECLINE_RE = re.compile(
    r"I[ \t\n]{1,3}(?:can['’]t|cannot|can[ \t\n]{1,3}not|won['’]t|will[ \t\n]{1,3}not|am[ \t\n]{1,3}(?:not[ \t\n]{1,3}able|unable)[ \t\n]{1,3}to"
    r"|must[ \t\n]{1,3}not|should[ \t\n]{1,3}not|shouldn['’]t)[ \t\n]{1,3}(?:write|calculate|do|complete|produce|give[ \t\n]{1,3}you|provide|draft"
    r"|answer|carry[ \t\n]{1,3}out|work[ \t\n]{1,3}out|compute|finish|submit|prepare|create)\b", re.IGNORECASE)
#: What a deferral holds back: "the full ...", "your essay", "the evaluation".
_DEFERRED_OBJECT = (r"(?:the|a|your|my)[ \t\n]{1,3}(?:(?:full|complete|whole|entire|final)\b[^.!?\n]{0,40}?"
                    r"|(?:essay|answer|response|evaluation|report|analysis|draft|section|sections|paragraph|commentary|discussion)\b)")
_WILL = r"I(?:['’]ll|[ \t\n]{1,3}(?:will|can|shall))[ \t\n]{1,3}(?:write|draft|produce|give|send|complete|finish)[ \t\n]{1,3}(?:you[ \t\n]{1,3})?"
#: Work held back until the student replies, at a sentence or line start: "Reply 'approve' and I will write the full
#: evaluation.", "Once you confirm, I will write the full essay.", "Shall I write the full answer?", "Would you like me to
#: write the essay from this plan?".
_DEFERRAL_RE = re.compile(
    r"(?:\A|(?<=[.!?:\n]))[ \t\n]{0,3}(?:"
    r"(?:reply|respond|answer|write[ \t\n]{1,3}back|say|tell[ \t\n]{1,3}me|let[ \t\n]{1,3}me[ \t\n]{1,3}know|confirm)\b[^.!?\n]{0,120}?"
    r"\b(?:and|then|so)[ \t\n]{1,3}" + _WILL + _DEFERRED_OBJECT
    + r"|(?:once|when|if|after)[ \t\n]{1,3}you[ \t\n]{1,3}(?:approve|confirm|agree|reply|say[ \t\n]{1,3}so|let[ \t\n]{1,3}me[ \t\n]{1,3}know"
    r"|are[ \t\n]{1,3}happy)\b[^.!?\n]{0,120}?\b" + _WILL + _DEFERRED_OBJECT
    + r"|(?:shall|should)[ \t\n]{1,3}I[ \t\n]{1,3}(?:write|draft|produce|go[ \t\n]{1,3}ahead[ \t\n]{1,3}(?:and|with))\b[^.!?\n]{0,40}?"
    + _DEFERRED_OBJECT + r"[^.!?\n]{0,80}?\?"
    + r"|(?:do[ \t\n]{1,3}you[ \t\n]{1,3}want|would[ \t\n]{1,3}you[ \t\n]{1,3}like)[ \t\n]{1,3}me[ \t\n]{1,3}to[ \t\n]{1,3}(?:write|draft|produce)"
    r"[ \t\n]{1,3}" + _DEFERRED_OBJECT + r"[^.!?\n]{0,80}?\?)", re.IGNORECASE)
#: The first paragraph ends at the first blank line; a sentence ends at a stop followed by blanks and a capital letter.
_PARAGRAPH_END_RE = re.compile(r"\n[ \t\r\f\v]{0,64}\n")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])[ \t\n]{1,64}(?=[A-Z])")
#: The end of a sentence: stops, closing marks and blanks.
_TERMINAL_CHARS = ".!?…\"'”’»)] \t\n"
_DIGIT_RE = re.compile(r"\d")
#: A source text is at most 4,000 characters in contract; the reading looks no further than this.
_READ_CHARS = 4000


def withheld_work(text: str) -> Optional[str]:
    """``"declined"`` when one of the first three sentences of the first paragraph of ``text`` declines part of the work the
    student asked for ("I can't write your introduction or your ethical safeguards, because the proposal must be your own
    work.", "I cannot answer part (c)."; a sentence holding a digit is not read as one, as the hub reads it), ``"deferred"``
    when ``text`` holds that work back until the student replies ("Reply 'approve' and I will write the full
    evaluation.", "Once you confirm, I will write the full essay.", "Shall I write the full answer?"), else None. The
    faithful fake's reading of rule 7 of the instructions; linear in the text, and it reads at most the first 4,000
    characters (a source text's limit in contract)."""
    if not isinstance(text, str) or not text:
        return None
    head = text[:_READ_CHARS]
    start = len(head) - len(head.lstrip())
    m = _PARAGRAPH_END_RE.search(head, start)
    first = head[start:m.start() if m is not None else len(head)]
    for k, sentence in enumerate(_SENTENCE_END_RE.split(first)):
        if k >= 3:
            break
        body = sentence.strip().rstrip(_TERMINAL_CHARS)
        if body and not _DIGIT_RE.search(body) and _DECLINE_RE.match(body.partition(";")[0].strip()):
            return "declined"
    if _DEFERRAL_RE.search(head):
        return "deferred"
    return None


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
                if c["role"] == "other" and withheld_work(c["text"]) is None:
                    dropped.append({"source_claim_ids": [c["claim_id"]], "reason": NOTE_REASON})
                else:  # a claim of the answer, or a note that declines or defers the requested work (rule 7): carried as written
                    claims.append({"text": c["text"], "source_claim_ids": [c["claim_id"]], "certainty": c["certainty"], "transformation": "carried"})
        out: dict[str, Any] = {"claims": claims}
        if dropped:
            out["dropped"] = dropped
        return json.dumps(out, ensure_ascii=False)
