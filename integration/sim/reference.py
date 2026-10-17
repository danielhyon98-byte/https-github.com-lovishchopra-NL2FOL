"""The reference side of the simulation (PROTOCOL.md section 14.5, step 3): the translator's own harnesses on a COPY of the corpus.

* ``run_arena.run_round`` on the copy (the genuine pass and the arena's own mutations), exactly as the harness runs it.
  The arena's records keep no result digests, so the digests of each genuine result are captured from the same
  receipts by observing ``RouterHub.receive`` (the wrapper returns the hub's own result unchanged; it never changes
  what the harness does or decides), keyed by the delivered text (items may share a task id).
* ``run_contained.py --replay-mode process --probe-scope all`` when the overseer's contained run exists on this tree
  (``scripts/overseer/run_contained.py``); otherwise the contained comparison is NOT RUN with that reason.

Outputs per item the G-EQ projection (``compare.record_projection``), the arena's own classification of every mutation
(for G-FAULT), and, for G-DEL, the decision the kit's decision table gives on each genuine receipt of the harness. The
harness makes no delivery decision, so that decision is KIT-DERIVED: ``delivery.decide`` over the claims of the
harness's own receipt and report (``claims.claim_entries``, ``delivery.count_claims``), under ``verified-v1``, with the
overseer's FINAL audit and delivery assumed to pass (the arena runs no overseer); the report says so. The receipts are
observed by wrapping ``RouterHub.receive`` for the run, which returns the hub's own result unchanged. The copy is made by
the caller; nothing is written into the kit or into recorded rounds.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Optional

__all__ = ["run_reference", "contained_available"]


def _compare_module(sim_dir: Path) -> Any:
    spec = importlib.util.spec_from_file_location("kit_sim_compare_ref", sim_dir / "compare.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def contained_available(translator: Path) -> Optional[Path]:
    path = translator / "scripts" / "overseer" / "run_contained.py"
    return path if path.exists() else None


def run_reference(translator: Path, round_copy: Path) -> dict:
    """``{"projections": {item: projection}, "mutations": [record...], "qualified": bool, "functional": [n, total]}``."""
    arena_dir = translator / "scripts" / "arena"
    sys.path.insert(0, str(arena_dir))
    import run_arena as ra  # the harness itself
    compare = _compare_module(Path(__file__).resolve().parent)

    # The genuine deliveries (report id rep-<task>-0, raw text), observed by wrapping RouterHub.receive for the run (it
    # returns the hub's own result unchanged) and keyed by the SHA-256 of the delivered text: items of one round may
    # share a task id (an adversarial round's variants do), so a report id does not name an item, its text does.
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.translate.contracts import sha256_text
    delivered: dict[str, tuple] = {}
    original_receive = RouterHub.receive

    def observing_receive(self, task_id, request_message_id, payload, **kw):  # returns the hub's own result unchanged
        reply, rc = original_receive(self, task_id, request_message_id, payload, **kw)
        rid = kw.get("report_id")
        if isinstance(rid, str) and rid.endswith("-0") and isinstance(payload, str):
            try:
                digests = [d for d in (compare.result_digests(o.model_dump(mode="json")) for o in rc.outcomes) if d is not None]
            except Exception:  # noqa: BLE001 - an observation never changes the harness's run
                digests = []
            delivered.setdefault(sha256_text(payload), (reply, rc, payload, digests))
        return reply, rc

    RouterHub.receive = observing_receive
    try:
        out = ra.run_round(round_copy)
    finally:
        RouterHub.receive = original_receive
    projections: dict[str, dict] = {}
    decisions: dict[str, dict] = {}
    mutations = []
    for rec in out["records"]:
        stem = Path(rec.get("file", "")).stem
        if rec.get("variant") == "genuine":
            tr_path = round_copy / "translations" / f"{stem}.json"
            fixture_ids = json.loads(tr_path.read_text(encoding="utf-8"))["claims"].keys() if tr_path.exists() else None
            sp = round_copy / "specialists" / f"{stem}.json"
            got = delivered.get(sha256_text(json.loads(sp.read_text(encoding="utf-8"))["response_text"])) if sp.exists() else None
            projections[stem] = compare.record_projection(rec, digests=got[3] if got is not None else [], fixture_ids=fixture_ids)
            if got is not None:
                decisions[stem] = kit_decision(*got[:3])
        elif rec.get("variant") not in (None, "genuine", "peer_relay", "synthesis"):
            mutations.append({"item": stem, "kind": rec.get("variant"), "expected": rec.get("expected"), "functional": rec.get("functional"),
                              "named_by": [f.get("code") for f in rec.get("named_by") or []], "codes": rec.get("codes"), "status": rec.get("status")})
    genuine = [r for r in out["records"] if r.get("variant") == "genuine"]
    return {"projections": projections, "mutations": mutations, "decisions": decisions, "qualified": bool(out.get("qualified")),
            "functional": [sum(1 for r in out["records"] if r.get("functional")), len(out["records"])], "genuine": len(genuine)}


def kit_decision(reply: Any, receipt: Any, answer: str) -> dict:
    """The kit's decision table on one genuine receipt of the harness (module docstring: KIT-DERIVED, the overseer
    assumed to pass, policy ``verified-v1``): ``{decision, reasons, kit_derived: True}``."""
    from epinoic_logic.integration.claims import claim_entries
    from epinoic_logic.integration.delivery import DecisionInput, count_claims, decide
    from epinoic_logic.translate.contracts import SpecialistReport
    claims = SpecialistReport.model_validate(reply.payload).claims if reply is not None else []
    _entries, fields = claim_entries(receipt, claims, answer)
    counts = count_claims(fields)
    inp = DecisionInput(policy="verified-v1", revision_of=None, receipt_status=receipt.status.value,
                        receipt_error_codes=tuple(sorted({f.code for f in receipt.findings if f.severity == "error"})),
                        overseer_state="AUDIT_PASSED", delivery_allowed=True, overseer_refusal=None, consolidation_status="CONSOLIDATED",
                        blocking=counts["blocking"], unavailable=counts["unavailable"], budget_skipped=counts["budget_skipped"])
    decision, reasons = decide(inp)
    return {"decision": decision, "reasons": list(reasons), "kit_derived": True}
