"""G-EQ comparison of the simulation, field by field (PROTOCOL.md section 14.5; ``integration/sim/VOLATILE.md``).

The website-path call's evidence (from the evidence tap: the response receipt of each answer) and the reference
harness's genuine pass on the same corpus item are reduced to the SAME projection, and the projections must be equal:

* the receipt status;
* the multiset of finding codes (integrity findings and branch structural findings together);
* the per-claim display statuses;
* for every result: ``problem_digest``, ``config_digest``, ``limits_digest`` and ``binding_digest``;
* the branch formal checks (constraint id, engine status, satisfied);
* the sets of served and unserved fixtures.

Everything else is either volatile (listed in ``VOLATILE.md``: ids, timestamps, signatures, latencies, report ids) or
not part of the gate. Nothing here decides a verdict; it only says whether two records of the same item agree.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Optional

__all__ = ["VOLATILE_FIELDS", "GATED_FIELDS", "NORMALIZED_REQUEST_ID", "result_digests", "receipt_projection", "record_projection", "differences"]

#: Fields that legitimately differ between two runs of the same item (VOLATILE.md gives the reason for each).
VOLATILE_FIELDS: tuple[str, ...] = (
    "receipt_id", "message_id", "request_id", "task_id", "report_id", "outcome_id", "translation_id", "result_id",
    "created_at", "issued_at", "signature", "key_id", "latency_ms", "timings", "channel", "summary", "smt2", "versions_digest",
)
GATED_FIELDS: tuple[str, ...] = ("status", "finding_codes", "claim_statuses", "result_digests", "formal_checks", "fixtures_served", "fixtures_unserved")


def _codes(findings: Iterable[Mapping[str, Any]]) -> list[str]:
    return [str(f.get("code")) for f in findings or [] if isinstance(f, Mapping)]


#: The request id an encoded problem is normalised to before hashing (VOLATILE.md: a website-path call's request id is
#: the website's attempt id, the arena's is req-<item>; the fixture provider serves each fixture under the call's id).
NORMALIZED_REQUEST_ID = "kit-normalized-request"


def result_digests(outcome: Mapping[str, Any], *, normalize_request_id: bool = True) -> Optional[tuple]:
    """``(claim_id, problem_digest, config_digest, limits_digest, binding_digest)`` of one outcome's signed result, or
    ``None`` without a result. With ``normalize_request_id`` the problem digest is the engine's own ``problem_digest`` of
    the encoded problem with its request id set to :data:`NORMALIZED_REQUEST_ID`, and the binding digest is recomputed
    from it with the engine's own ``binding_digest_of``: every other byte of the problem, the configuration, the
    versions and the limits still count."""
    b = ((outcome.get("verification") or {}).get("binding") or {})
    if not b:
        return None
    pd, bd = b.get("problem_digest"), b.get("binding_digest")
    problem = (outcome.get("translation") or {}).get("problem")
    if normalize_request_id and isinstance(problem, Mapping):
        from epinoic_logic.engine.provenance import binding_digest_of
        from epinoic_logic.ir.canonical import problem_digest
        from epinoic_logic.ir.schema import Problem
        model = Problem.model_validate({**problem, "request_id": NORMALIZED_REQUEST_ID})
        pd = problem_digest(model)
        bd = binding_digest_of(pd, b.get("config_digest"), b.get("versions_digest"), b.get("limits_digest"))
    return (outcome.get("claim_id"), pd, b.get("config_digest"), b.get("limits_digest"), bd)


def receipt_projection(receipt: Mapping[str, Any], *, fixture_ids: Optional[Iterable[str]] = None, normalize_request_id: bool = True) -> dict:
    """The gated projection of one receipt (``TransmissionReceipt.model_dump(mode="json")``). ``fixture_ids`` are the
    item's fixture claim ids; a fixture is served when its claim has an outcome whose translation was not refused."""
    outcomes = [o for o in receipt.get("outcomes") or [] if isinstance(o, Mapping)]
    codes = Counter(_codes(receipt.get("findings")) + _codes(receipt.get("structural_findings")))
    digests = [d for d in (result_digests(o, normalize_request_id=normalize_request_id) for o in outcomes) if d is not None]
    served = {o.get("claim_id") for o in outcomes if ((o.get("translation") or {}).get("status") not in (None, "TRANSLATION_FAILED"))}
    proj = {
        "status": receipt.get("status"),
        "finding_codes": sorted(codes.elements()),
        "claim_statuses": sorted((str(o.get("claim_id")), str(o.get("display_status"))) for o in outcomes),
        "result_digests": sorted(digests, key=lambda t: tuple("" if x is None else str(x) for x in t)),
        "formal_checks": sorted(((str(fc.get("constraint_id")), fc.get("formal_status"), fc.get("satisfied")) for fc in receipt.get("formal_checks") or []),
                                key=lambda t: (t[0], str(t[1]), str(t[2]))),
    }
    if fixture_ids is not None:
        ids = set(fixture_ids)
        proj["fixtures_served"] = sorted(ids & served)
        proj["fixtures_unserved"] = sorted(ids - served)
    return proj


def record_projection(record: Mapping[str, Any], *, digests: Optional[Iterable[tuple]] = None, fixture_ids: Optional[Iterable[str]] = None) -> dict:
    """The same projection of a ``run_arena.run_round`` genuine-pass record. The arena's record keeps no result digests,
    so ``reference.py`` captures them from the same receipts (``digests``) without changing what the harness does."""
    outcomes = [o for o in record.get("outcomes") or [] if isinstance(o, Mapping)]
    codes = Counter(_codes(record.get("findings")) + _codes(record.get("subject_findings")))
    served = {o.get("claim_id") for o in outcomes if o.get("translation_status") not in (None, "TRANSLATION_FAILED")}
    proj = {
        "status": record.get("status"),
        "finding_codes": sorted(codes.elements()),
        "claim_statuses": sorted((str(o.get("claim_id")), str(o.get("display_status"))) for o in outcomes),
        "result_digests": sorted(list(digests or []), key=lambda t: tuple("" if x is None else str(x) for x in t)),
        "formal_checks": sorted(((str(c[0]), c[1], c[2]) for c in record.get("formal_checks") or []), key=lambda t: (t[0], str(t[1]), str(t[2]))),
    }
    if fixture_ids is not None:
        ids = set(fixture_ids)
        proj["fixtures_served"] = sorted(ids & served)
        proj["fixtures_unserved"] = sorted(ids - served)
    return proj


def differences(item: str, website: Mapping[str, Any], reference: Mapping[str, Any]) -> list[dict]:
    """Every gated field on which the two projections of ``item`` differ (empty when they agree)."""
    out = []
    for field in GATED_FIELDS:
        if field not in website and field not in reference:
            continue
        a, b = website.get(field), reference.get(field)
        if a != b:
            out.append({"item": item, "field": field, "website": a, "reference": b})
    return out
