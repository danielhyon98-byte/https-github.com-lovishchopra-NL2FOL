"""Relay history (STEM review, docs/STEM_DESIGN.md, section 11.6): what a faithful forward or relay of a delivered
report must carry. Shared by the channel tests that forward or relay a report after its arrival."""
from __future__ import annotations

from epinoic_logic.channel import TransmissionStatus

HIST = "INT-HIST-001"


def unresolved(receipt) -> list[tuple[str, str, tuple[str, ...], str]]:
    """``(code, severity, claim ids, message)`` of what a receipt leaves unresolved: its own error and warning findings."""
    return sorted((f.code, f.severity, tuple(sorted(f.claim_ids)), f.message) for f in receipt.findings
                  if f.severity in ("error", "warning") and f.code != HIST)


def assert_carries_exactly(later, earlier) -> None:
    """A faithful forward or relay of an unchanged report adds no finding of its own here; it carries exactly what the
    earlier receipt left unresolved, as INT-HIST-001 with the same severity, claims and message; it references that
    receipt in its history; and it is ACCEPTED exactly when nothing was left open."""
    own = [f for f in later.findings if f.code != HIST]
    assert own == [], [f.model_dump() for f in own]
    expected = unresolved(earlier)
    carried = [f for f in later.findings if f.code == HIST]
    assert sorted((f.severity, tuple(sorted(f.claim_ids))) for f in carried) == sorted((sev, claims) for _code, sev, claims, _msg in expected)
    for code, sev, claims, msg in expected:
        assert any(f.severity == sev and tuple(sorted(f.claim_ids)) == claims and f"{code} ({sev})" in f.message and msg[:200] in f.message
                   for f in carried), (code, msg)
    assert earlier.receipt_id in [h.receipt_id for h in later.history]
    assert later.status is (TransmissionStatus.ACCEPTED_WITH_FINDINGS if expected else TransmissionStatus.ACCEPTED)


#: The warnings a forward to a peer specialist carries besides the errors (``channel.bus._DECIDED_WARNINGS``): the faults the
#: content itself was found to have (accuracy round 1, DV2-05).
DECIDED_WARNINGS = frozenset({"INT-SUBJ-004", "INT-ARG-001", "INT-REQ-017"})


def assert_forwards_to_a_peer(later, earlier) -> None:
    """A faithful forward of an unchanged report to a peer specialist (accuracy round 1, DV2-05) adds no finding of its own;
    it carries exactly the earlier receipt's errors and the warnings that state a fault the content was found to have
    (:data:`DECIDED_WARNINGS`), as INT-HIST-001 with the same severity, claims and message; it references that receipt in its
    history, where every other unresolved finding (a heuristic reading: coverage, layout, a derived figure not decided) stays
    listed and is not carried; and it is ACCEPTED exactly when it carries nothing. The same exactness as
    :func:`assert_carries_exactly`, under the peer rule."""
    own = [f for f in later.findings if f.code != HIST]
    assert own == [], [f.model_dump() for f in own]
    everything = unresolved(earlier)
    expected = [x for x in everything if x[1] == "error" or x[0] in DECIDED_WARNINGS]
    carried = [f for f in later.findings if f.code == HIST]
    assert sorted((f.severity, tuple(sorted(f.claim_ids))) for f in carried) == sorted((sev, claims) for _code, sev, claims, _msg in expected)
    for code, sev, claims, msg in expected:
        assert any(f.severity == sev and tuple(sorted(f.claim_ids)) == claims and f"{code} ({sev})" in f.message and msg[:200] in f.message
                   for f in carried), (code, msg)
    [ref] = [h for h in later.history if h.receipt_id == earlier.receipt_id]
    listed = sorted((f.code, f.severity, tuple(sorted(f.claim_ids)), f.message) for f in ref.unresolved_findings)
    assert listed == everything  # what is not carried stays listed in the history the forward references
    assert later.status is (TransmissionStatus.ACCEPTED_WITH_FINDINGS if expected else TransmissionStatus.ACCEPTED)


def assert_forwards_to_a_peer_exactly(later, earlier, *, carried: list[tuple[str, str]], listed: list[tuple[str, str]]) -> None:
    """:func:`assert_forwards_to_a_peer`, and the outcome as literal sets (accuracy round 2, V1-TEST-INVERTED: a rewritten
    test keeps an exact set, not only a rule): ``carried`` is exactly the ``(code, severity)`` of every finding the forward
    carries (INT-HIST-001 naming the carried code), and ``listed`` exactly those of the unresolved findings the history it
    references lists for the earlier receipt."""
    assert_forwards_to_a_peer(later, earlier)
    got = sorted((next((code for code, _sev, _claims, _msg in unresolved(earlier) if f"{code} ({f.severity})" in f.message), "?"), f.severity)
                 for f in later.findings if f.code == HIST)
    assert got == sorted(carried), got
    [ref] = [h for h in later.history if h.receipt_id == earlier.receipt_id]
    assert sorted((f.code, f.severity) for f in ref.unresolved_findings) == sorted(listed)
