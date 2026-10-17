"""The simulation gates of the integration kit (PROTOCOL.md section 14.5) as pure functions of the simulation's records.

Every gate returns ``{"gate", "status", "reason", "denominator", "cases"}`` with ``status`` one of ``PASS``, ``FAIL`` or
``NOT RUN``. **The NOT RUN rule:** a gate that has no material is NOT RUN, never PASS, and its reason names what is
missing. ``exit_status`` is 0 only when no gate FAILs and all eight gates are PASS; the summary lists every gate.

Nothing here runs a harness, edits a gate or a vector, or decides a verdict: ``run_sim.py`` collects the records, and
these functions only judge them.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

__all__ = ["GATES", "PASS", "FAIL", "NOT_RUN", "not_run", "g_eq_arena", "g_eq_contained", "g_fault", "g_inv", "g_hon", "g_del", "g_tamper",
           "g_ovs", "exit_status", "summary_lines"]

PASS, FAIL, NOT_RUN = "PASS", "FAIL", "NOT RUN"
GATES: tuple[str, ...] = ("G-EQ-ARENA", "G-EQ-CONTAINED", "G-FAULT", "G-INV", "G-HON", "G-DEL", "G-TAMPER", "G-OVS")
#: Words no displayed label may carry (PROTOCOL.md section 8; G-HON).
FORBIDDEN_LABEL_WORDS: tuple[str, ...] = ("reviewed", "verified", "true", "proven")
POSITIVE = frozenset({"ENTAILED", "CONSISTENT", "SATISFIABLE"})
DEFINITIVE = POSITIVE | {"COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "UNSATISFIABLE"}
TAMPER_CASES: tuple[str, ...] = tuple(f"W-T{i}" for i in range(1, 9))


def _gate(gate: str, status: str, reason: str, denominator: int = 0, cases: Optional[list] = None) -> dict:
    return {"gate": gate, "status": status, "reason": reason, "denominator": denominator, "cases": list(cases or [])}


def not_run(gate: str, reason: str) -> dict:
    """A gate without material (the NOT RUN rule): the reason names what is missing."""
    if not reason:
        raise ValueError("a NOT RUN gate names its reason")
    return _gate(gate, NOT_RUN, reason)


def g_eq_arena(website: Optional[Mapping[str, Mapping]], reference: Optional[Mapping[str, Mapping]], differences: Any) -> dict:
    """``website`` and ``reference`` map each corpus item to its projection (compare.py); ``differences`` is
    ``compare.differences``. PASS only with material on both sides for every item and 0 differences."""
    if not website or not reference:
        return not_run("G-EQ-ARENA", "no website-path evidence" if not website else "no reference-harness records")
    items = sorted(set(website) | set(reference))
    diffs: list[dict] = []
    for item in items:
        if item not in website or item not in reference:
            diffs.append({"item": item, "field": "presence", "website": item in website, "reference": item in reference})
            continue
        diffs.extend(differences(item, website[item], reference[item]))
    if diffs:
        return _gate("G-EQ-ARENA", FAIL, f"{len(diffs)} difference(s)", len(items), diffs)
    return _gate("G-EQ-ARENA", PASS, "0 differences", len(items), items)


def g_eq_contained(contained: Optional[Mapping[str, Any]]) -> dict:
    """``contained``: ``{exit_status, gates: {name: PASS|FAIL|NOT RUN}, states_equal: bool, non_interference_equal: bool}``
    from ``run_contained.py`` on the corpus copy; None when the contained run is not available."""
    if contained is None:
        return not_run("G-EQ-CONTAINED", "the contained run (the overseer's run_contained.py) is not available on this tree")
    applicable = {k: v for k, v in (contained.get("gates") or {}).items() if v != NOT_RUN}
    if not applicable:
        return not_run("G-EQ-CONTAINED", "no gate of the contained run has material on this corpus")
    failed = [k for k, v in applicable.items() if v != PASS]
    if contained.get("exit_status") != 0 or failed or not contained.get("states_equal") or not contained.get("non_interference_equal"):
        return _gate("G-EQ-CONTAINED", FAIL, "the contained run disagrees", len(applicable), failed or ["states or non-interference"])
    return _gate("G-EQ-CONTAINED", PASS, "every applicable gate PASS; states and non-interference equal", len(applicable), sorted(applicable))


def g_fault(records: Optional[Sequence[Mapping[str, Any]]]) -> dict:
    """Each record: ``{case, caught_by_arena, website_refused, website_codes, arena_codes, website_labelled_checked,
    same_behaviour}``. A caught mutation must be refused on the website path with the arena's finding codes; a miss must
    behave identically and is never labelled checked."""
    if not records:
        return not_run("G-FAULT", "no mutation was sent through the website path")
    bad = []
    for r in records:
        if r.get("caught_by_arena"):
            if not r.get("website_refused") or not set(r.get("arena_codes") or ()) <= set(r.get("website_codes") or ()):
                bad.append(r.get("case"))
        elif r.get("website_labelled_checked") or not r.get("same_behaviour"):
            bad.append(r.get("case"))
    if bad:
        return _gate("G-FAULT", FAIL, f"{len(bad)} mutation(s) behave differently", len(records), bad)
    misses = sum(1 for r in records if not r.get("caught_by_arena"))
    return _gate("G-FAULT", PASS, f"every caught mutation refused; {misses} known miss(es), none labelled checked", len(records), [r.get("case") for r in records])


def g_inv(invariants: Optional[Mapping[str, Optional[bool]]]) -> dict:
    """``invariants``: name -> True (held), False (broken) or None (no material for it)."""
    if not invariants or all(v is None for v in invariants.values()):
        return not_run("G-INV", "no website-path turn was run")
    broken = sorted(k for k, v in invariants.items() if v is False)
    unmeasured = sorted(k for k, v in invariants.items() if v is None)
    if broken:
        return _gate("G-INV", FAIL, f"broken: {', '.join(broken)}", len(invariants), broken)
    if unmeasured:
        return not_run("G-INV", f"no material for: {', '.join(unmeasured)}")
    return _gate("G-INV", PASS, "every invariant held", len(invariants), sorted(invariants))


def label_problem(display: Mapping[str, Any]) -> Optional[str]:
    """Why one displayed answer breaks the honesty rules, or None. ``display``: ``{review, labels: [{formal, text}],
    scope_statement_shown, simulated}``, and, when the page shows one, ``badge`` (its text) with ``summary`` (the
    answer's ``checksSummary``): the badge says "passed" only for ``formally_checked`` (PROTOCOL.md section 9, rule 13)."""
    if display.get("review") != "checks:integration.v1":
        return "a delivered answer does not say review checks:integration.v1"
    if display.get("simulated") is not True:
        return "a simulated answer is not marked simulated"
    if "badge" in display:
        badge = str(display.get("badge") or "").lower()
        if any(w in badge.replace("(", " ").replace(")", " ").split() for w in FORBIDDEN_LABEL_WORDS):
            return f"the answer badge claims more than the encoding: {badge[:80]}"
        if "passed" in badge and display.get("summary") != "formally_checked":
            return "the answer badge says passed although not every material eligible claim has a permitted positive result"
    labels = list(display.get("labels") or [])
    for lab in labels:
        text = str(lab.get("text", ""))
        lowered = text.lower()
        if any(w in lowered.replace(":", " ").replace(".", " ").split() for w in FORBIDDEN_LABEL_WORDS):
            return f"a label claims more than the encoding: {text[:80]}"
        if lab.get("formal") not in POSITIVE and lowered.startswith("formally checked"):
            return "a non-definitive status is labelled checked"
    if any(lab.get("formal") in DEFINITIVE for lab in labels) and not display.get("scope_statement_shown"):
        return "a formal status is shown without the scope statement"
    return None


def g_hon(displays: Optional[Sequence[Mapping[str, Any]]]) -> dict:
    if not displays:
        return not_run("G-HON", "no delivered answer was displayed")
    bad = [(i, p) for i, p in ((i, label_problem(d)) for i, d in enumerate(displays)) if p]
    if bad:
        return _gate("G-HON", FAIL, bad[0][1], len(displays), [b[0] for b in bad])
    return _gate("G-HON", PASS, "every displayed label is allowed for its status", len(displays))


def g_del(verdicts: Optional[Sequence[Mapping[str, Any]]], rederived: Optional[Sequence[Mapping[str, Any]]]) -> dict:
    """``verdicts``: the website-path verdicts; ``rederived``: ``{item, decision, kit_derived: True}`` from the reference
    harness's own records (the existing harnesses make no delivery decision, so this part is kit-derived)."""
    if not verdicts:
        return not_run("G-DEL", "no checks call returned a verdict")
    bad = []
    for v in verdicts:
        d = v.get("delivery", {})
        o = v.get("overseer", {})
        if d.get("decision") == "deliver" and (o.get("state") not in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS") or o.get("delivery_allowed") is not True):
            bad.append(v.get("verdict_id"))
        if d.get("decision") != "deliver" and not d.get("reasons"):
            bad.append(v.get("verdict_id"))
    if bad:
        return _gate("G-DEL", FAIL, "a delivery without a passed FINAL audit, or a refusal without its reason", len(verdicts), bad)
    if not rederived:
        return not_run("G-DEL", "the reference harness's records were not re-derived")
    return _gate("G-DEL", PASS, "every delivery had a passed FINAL audit and an allowed decision (re-derivation: kit-derived)", len(verdicts))


def g_tamper(results: Optional[Mapping[str, Mapping[str, Any]]]) -> dict:
    """``results``: case -> {expected, got} for W-T1..W-T8 through the website path."""
    if not results:
        return not_run("G-TAMPER", "the website path is not available (no verified backend in the export)")
    missing = [c for c in TAMPER_CASES if c not in results]
    if missing:
        return not_run("G-TAMPER", f"cases not run: {', '.join(missing)}")
    bad = [c for c in TAMPER_CASES if results[c].get("got") != results[c].get("expected")]
    if bad:
        return _gate("G-TAMPER", FAIL, f"not refused as expected: {', '.join(bad)}", len(TAMPER_CASES), bad)
    return _gate("G-TAMPER", PASS, "W-T1 to W-T8 each refused with the expected code", len(TAMPER_CASES), list(TAMPER_CASES))


def g_ovs(probes: Optional[Sequence[Mapping[str, Any]]]) -> dict:
    """``probes``: ``{kind, website_outcome, contained_outcome, clearance_changed, delivery_changed}``."""
    if not probes:
        return not_run("G-OVS", "the overseer's asynchronous review and its probe providers are not available on this tree")
    bad = [p.get("kind") for p in probes if p.get("website_outcome") != p.get("contained_outcome") or p.get("clearance_changed") or p.get("delivery_changed")]
    if bad:
        return _gate("G-OVS", FAIL, "a probe outcome differs, or the review changed a clearance or a delivery", len(probes), bad)
    return _gate("G-OVS", PASS, "every probe outcome equals the contained run's; no clearance or delivery changed", len(probes))


def exit_status(results: Iterable[Mapping[str, Any]]) -> int:
    """0 only when no gate FAILs and all eight gates are PASS; 1 otherwise."""
    by = {r["gate"]: r["status"] for r in results}
    if any(s == FAIL for s in by.values()):
        return 1
    return 0 if all(by.get(g) == PASS for g in GATES) else 1


def summary_lines(results: Sequence[Mapping[str, Any]]) -> list[str]:
    out = ["# Simulation gates", "", "| Gate | Status | Denominator | Reason |", "|---|---|---|---|"]
    by = {r["gate"]: r for r in results}
    for g in GATES:
        r = by.get(g) or not_run(g, "not evaluated")
        out.append(f"| {g} | {r['status']} | {r['denominator']} | {r['reason']} |")
    out += ["", f"Exit status: {exit_status(results)} (0 only when no gate FAILs and all eight gates are PASS)."]
    return out
