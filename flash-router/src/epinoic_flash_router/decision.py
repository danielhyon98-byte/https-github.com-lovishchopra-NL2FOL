"""The flash decision maker: the flash router's first decision, made for every response it is asked about.

For one response (a specialist's output in the service's routing request, or one dossier of an overseer-pool batch),
read from the user's request record and the output's own features, it decides between the router's two methods of
oversight:

* the **in-depth examination method**: one overseer instance examines the whole response (``IN_DEPTH``);
* the **duplication method**: the work split across several overseer instances in parallel (``SPLIT``, one output in
  parts; ``N_FOLD``, a combined answer whose specialists' responses are each reviewed on an instance of their own), with
  independent duplicate reviews (``DUPLICATE``) where a risk signal calls for agreement.

It chooses the **cheapest method that keeps accuracy**, by the recorded cost data (rules D1 to D7 of the current rules
file):

* **agreement** (D3): the caller says how many independent complete reviews the response needs, from its risk signals
  (port rule 2, pool rule P2); a risk signal or an escalation only ever raises that number, never lowers it;
* **fit** (D4): an instance keeps accuracy only when it reads what it examines whole: the system text of the knowledge
  pack's composition the content needs (``system_text_chars``: the core, with the STEM module, with the translations
  module, with both), the dossier and the output budget must fit the instance budget (``instance_budget_tokens``). A
  response that does not fit is divided into the fewest parts that fit (``SPLIT``, or ``DUPLICATE`` with parts under
  agreement) where the caller can divide it; where it cannot (the pool reviews one dossier whole), the decision says so
  (reason ``over_budget``) and never shortens anything;
* **cost** (D5): every candidate is priced per call (the system text, what the call reads, the output budget, at
  ``chars_per_token`` characters a token, rounded up) and in agent-seconds (``seconds_per_call`` a call); among the
  candidates that keep accuracy the cheapest wins (tokens, then agent-seconds, then calls, then the method's place in
  :data:`METHOD_ORDER`). One instance reading the whole response is the cheapest whenever it keeps accuracy, since every
  further call repeats the system text.

The decision is code: deterministic, instant (integer arithmetic over the request's features and the data loaded at
start), with no network, no clock, no randomness and no model. A model never decides duplication; the overseer's
optional escalation advisor can only add escalations, which reach this code as the request's ``advised`` flag.

Every decision is recorded (D7): :func:`decide` returns the method with the features it read, every candidate it
priced (whether it keeps accuracy, and why it was or was not chosen) and its reasons, all closed vocabularies and
integers: :data:`DECISION_REASONS`, :data:`CANDIDATE_WHY`. The pool plan carries the record for each dossier (pool port
1.2); the service's plan records each transfer's method, reasons, features used and estimated cost (router port 1.0).

The decision is advice: each caller holds it to its own minimum-oversight floor, so a decision below the floor is
refused there and the floor plan runs. Standard library only.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

__all__ = [
    "APPROACHES", "METHOD_ORDER", "DECISION_REASONS", "CANDIDATE_WHY", "composition_key", "system_tokens", "read_tokens", "call_tokens",
    "port_dossier_chars", "decide", "n_fold_decision",
]

#: The flash decision maker's two methods, as recorded: ``in_depth`` (one instance examines the whole response) and
#: ``duplication`` (the work split across several instances in parallel, with duplicates where risk calls for agreement).
APPROACHES: tuple[str, ...] = ("in_depth", "duplication")
#: The tie order of the methods (the last key of the choice).
METHOD_ORDER: tuple[str, ...] = ("IN_DEPTH", "DUPLICATE", "SPLIT", "N_FOLD")
#: Why a decision was made (closed): the cheapest method that keeps accuracy is one instance reading the whole response;
#: agreement called for by a risk signal, by an escalation this router adds, or by the escalation advisor; a combined
#: answer reviewed N_FOLD; a response divided to fit one instance's budget; a response no method makes fit (disclosed);
#: no size features in the request (fit not assessed).
DECISION_REASONS: tuple[str, ...] = (
    "in_depth_cheapest", "agreement_risk", "agreement_escalation", "agreement_advised", "combined_n_fold", "split_to_fit", "over_budget",
    "size_not_measured",
)
#: Why a candidate was or was not chosen (closed).
CANDIDATE_WHY: tuple[str, ...] = ("chosen", "costlier", "agreement_needed", "exceeds_budget", "combined_needs_n_fold")


def _ceil_div(a: int, b: int) -> int:
    return -(-int(a) // int(b))


def composition_key(stem: bool, translations: bool) -> str:
    """The knowledge pack's composition a dossier's content needs: ``core``, then ``+stem``, then ``+translations``."""
    return "core" + ("+stem" if stem else "") + ("+translations" if translations else "")


def system_tokens(stem: bool, translations: bool, cost: Mapping[str, Any]) -> int:
    """The tokens of the system text one call is sent: the recorded size of its composition, at ``chars_per_token``."""
    return _ceil_div(int(cost["system_text_chars"][composition_key(stem, translations)]), int(cost["chars_per_token"]))


def read_tokens(chars: int, cost: Mapping[str, Any]) -> int:
    return _ceil_div(max(0, int(chars)), int(cost["chars_per_token"]))


def call_tokens(system: int, chars: int, cost: Mapping[str, Any]) -> int:
    """One call: its system text, what it reads, and the output budget."""
    return system + read_tokens(chars, cost) + int(cost["output_tokens"])


def port_dossier_chars(answer_chars: int, supplied_chars: int, translated: int, cost: Mapping[str, Any]) -> int:
    """The characters of the dossier an overseer instance reads for one output of the service's routing request,
    estimated from its features (the cost data's planning estimates; an output's own size is known, its dossier's is
    not until it is issued)."""
    d = cost["dossier"]
    return (int(d["base_chars"]) + int(d["chars_per_answer_char"]) * max(0, int(answer_chars)) + max(0, int(supplied_chars))
            + int(d["chars_per_translation"]) * max(0, int(translated)))


def _priced(method: str, reviews: int, parts: int, *, chars: Optional[int], system: int, cost: Mapping[str, Any]) -> dict:
    calls = reviews * parts
    tokens = None if chars is None else reviews * parts * call_tokens(system, _ceil_div(chars, parts), cost)
    return {"method": method, "reviews": reviews, "parts": parts, "calls": calls, "tokens": tokens, "seconds": calls * int(cost["seconds_per_call"]),
            "keeps_accuracy": False, "why": "costlier"}


def _cheapest_key(c: Mapping[str, Any]) -> tuple:
    return (c["tokens"] if c["tokens"] is not None else 0, c["seconds"], c["calls"], METHOD_ORDER.index(c["method"]))


def decide(*, reviews: int, chars: Optional[int], stem: bool, translations: bool, cost: Mapping[str, Any], cap: int, max_parts: int,
           methods: Sequence[str] = ("IN_DEPTH", "DUPLICATE", "SPLIT"), reasons: Sequence[str] = ()) -> dict:
    """The decision for one response (module docstring).

    ``reviews`` is the number of independent complete reviews its risk calls for (at least 1; agreement is 2 or more);
    ``chars`` the characters one instance reads to examine it whole (``None`` when the request does not measure it: fit
    is then not assessed); ``stem`` and ``translations`` select the pack composition; ``cap`` bounds the instances one
    entry may use; ``methods`` are the methods the caller can run (the pool does not divide one dossier: no ``SPLIT``);
    ``reasons`` are the caller's agreement reasons (``agreement_risk``, ``agreement_escalation``, ``agreement_advised``).

    Returns the decision record: ``approach``, ``method``, ``reviews``, ``parts``, ``instances``, ``calls``,
    ``need_tokens`` (one instance reading the whole response, or ``None``), ``budget_tokens``, ``fits``, ``candidates``
    (each priced, with ``keeps_accuracy`` and ``why``), ``reasons`` (closed codes, in :data:`DECISION_REASONS` order) and
    ``estimated_cost`` (``tokens`` or ``None``, ``seconds``)."""
    need = max(1, int(reviews))
    dup = max(2, need)
    budget = int(cost["instance_budget_tokens"])
    system = system_tokens(stem, translations, cost)
    whole = None if chars is None else call_tokens(system, chars, cost)
    fits = None if whole is None else whole <= budget
    cands: list[dict] = []
    if "IN_DEPTH" in methods:
        c = _priced("IN_DEPTH", 1, 1, chars=chars, system=system, cost=cost)
        c["keeps_accuracy"] = need == 1 and fits is not False
        c["why"] = "agreement_needed" if need > 1 else ("exceeds_budget" if fits is False else "costlier")
        cands.append(c)
    if "DUPLICATE" in methods and cap >= 2:
        r = min(dup, int(cap))
        c = _priced("DUPLICATE", r, 1, chars=chars, system=system, cost=cost)
        c["keeps_accuracy"] = fits is not False and r >= need
        c["why"] = "exceeds_budget" if fits is False else ("agreement_needed" if r < need else "costlier")
        cands.append(c)
    if "SPLIT" in methods and fits is False and chars is not None:
        top = max(2, min(int(max_parts), int(cap) // (1 if need == 1 else dup)))
        p = next((k for k in range(2, top + 1) if call_tokens(system, _ceil_div(chars, k), cost) <= budget), None)
        parts = p if p is not None else top
        method, r = ("SPLIT", 1) if need == 1 else ("DUPLICATE", dup)
        if r * parts <= cap:
            c = _priced(method, r, parts, chars=chars, system=system, cost=cost)
            c["keeps_accuracy"] = p is not None
            c["why"] = "costlier" if p is not None else "exceeds_budget"
            cands.append(c)
    keepers = [c for c in cands if c["keeps_accuracy"]]
    if keepers:
        chosen = min(keepers, key=_cheapest_key)
    else:
        # no method keeps accuracy (the response fits no instance however it is divided, or the caller cannot divide it, or
        # the cap allows fewer reviews than risk calls for): the method nearest to it, the most of the reviews risk calls
        # for first (risk only escalates), then the most parts, then the cheapest
        meeting = [c for c in cands if c["reviews"] >= need] or cands
        chosen = min(meeting, key=lambda c: (-min(c["reviews"], need), -c["parts"], *_cheapest_key(c)))
    chosen["why"] = "chosen"
    out_reasons = set(reasons)
    if chosen["method"] == "IN_DEPTH" and chosen["keeps_accuracy"]:
        out_reasons.add("in_depth_cheapest")
    if chosen["parts"] >= 2:
        out_reasons.add("split_to_fit")
    if not keepers and fits is False:
        out_reasons.add("over_budget")
    if chars is None:
        out_reasons.add("size_not_measured")
    return {"approach": "in_depth" if chosen["method"] == "IN_DEPTH" else "duplication", "method": chosen["method"], "reviews": chosen["reviews"],
            "parts": chosen["parts"], "instances": chosen["reviews"] * chosen["parts"], "calls": chosen["calls"], "need_tokens": whole,
            "budget_tokens": budget, "fits": fits, "candidates": cands, "reasons": [r for r in DECISION_REASONS if r in out_reasons],
            "estimated_cost": {"tokens": chosen["tokens"], "seconds": chosen["seconds"]}}


def n_fold_decision(*, sources: Sequence[Mapping[str, Any]], merged: Mapping[str, Any], whole: Mapping[str, Any], cost: Mapping[str, Any],
                    reasons: Sequence[str] = ()) -> dict:
    """The decision for a combined answer (D6): N_FOLD, the floor's method for it, recorded with the decision of each part.

    ``sources`` and ``merged`` are the parts' own decisions (:func:`decide` with ``methods=("IN_DEPTH", "DUPLICATE")``:
    each part examined whole, by the reviews its own risk calls for); ``whole`` is the decision the dossier would get
    examined as one response (the candidate the floor refuses for a combined answer, priced for the record). The N
    source reviews run in parallel, then the merged review; the N_FOLD candidate is the sum of the parts' calls."""
    parts = [*sources, merged]
    tokens = None if any(p["estimated_cost"]["tokens"] is None for p in parts) else sum(p["estimated_cost"]["tokens"] for p in parts)
    seconds = sum(p["estimated_cost"]["seconds"] for p in parts)
    calls = sum(p["calls"] for p in parts)
    n_fold = {"method": "N_FOLD", "reviews": merged["reviews"], "parts": len(sources), "calls": calls, "tokens": tokens, "seconds": seconds,
              "keeps_accuracy": True, "why": "chosen"}
    refused = [dict(c, keeps_accuracy=False, why="combined_needs_n_fold") for c in whole["candidates"]]
    out_reasons = set(reasons) | {"combined_n_fold"} | {r for p in parts for r in p["reasons"] if r in ("over_budget", "size_not_measured")}
    fits = None if any(p["fits"] is None for p in parts) else all(p["fits"] for p in parts)
    return {"approach": "duplication", "method": "N_FOLD", "reviews": merged["reviews"], "parts": len(sources),
            "instances": sum(p["instances"] for p in sources), "calls": calls, "need_tokens": whole["need_tokens"], "budget_tokens": whole["budget_tokens"],
            "fits": fits, "candidates": [n_fold, *refused], "reasons": [r for r in DECISION_REASONS if r in out_reasons],
            "estimated_cost": {"tokens": tokens, "seconds": seconds}}
