"""The reference side of the simulation (PROTOCOL.md section 14.5, step 3): the translator's own harnesses on a COPY of the corpus.

* ``run_arena.run_round`` on the copy (the genuine pass and the arena's own mutations), exactly as the harness runs it.
  The arena's records keep no result digests, so the digests of each genuine result are captured from the same
  outcomes by observing ``run_arena.outcome_record`` (the wrapper returns the harness's record unchanged; it never
  changes what the harness does or decides).
* ``run_contained.py --replay-mode process --probe-scope all`` when the overseer's contained run exists on this tree
  (``scripts/overseer/run_contained.py``); otherwise the contained comparison is NOT RUN with that reason.

Outputs per item the G-EQ projection (``compare.record_projection``) and the arena's own classification of every
mutation (for G-FAULT). The copy is made by the caller; nothing is written into the kit or into recorded rounds.
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

    captured: dict[tuple[str, str], tuple] = {}
    original = ra.outcome_record

    def observing(o):  # returns the harness's own record unchanged
        rec = original(o)
        try:
            d = compare.result_digests(o.model_dump(mode="json"))
            if d is not None:
                captured[(o.report_id, o.claim_id)] = d
        except Exception:  # noqa: BLE001 - an observation never changes the harness's run
            pass
        return rec

    ra.outcome_record = observing
    try:
        out = ra.run_round(round_copy)
    finally:
        ra.outcome_record = original
    projections: dict[str, dict] = {}
    mutations = []
    for rec in out["records"]:
        stem = Path(rec.get("file", "")).stem
        if rec.get("variant") == "genuine":
            tr_path = round_copy / "translations" / f"{stem}.json"
            fixture_ids = json.loads(tr_path.read_text(encoding="utf-8"))["claims"].keys() if tr_path.exists() else None
            digests = [d for (rid, _cid), d in captured.items() if rid == f"rep-{rec['task_id']}-0"]
            projections[stem] = compare.record_projection(rec, digests=digests, fixture_ids=fixture_ids)
        elif rec.get("variant") not in (None, "genuine", "peer_relay", "synthesis"):
            mutations.append({"item": stem, "kind": rec.get("variant"), "expected": rec.get("expected"), "functional": rec.get("functional"),
                              "named_by": [f.get("code") for f in rec.get("named_by") or []], "codes": rec.get("codes")})
    genuine = [r for r in out["records"] if r.get("variant") == "genuine"]
    return {"projections": projections, "mutations": mutations, "qualified": bool(out.get("qualified")),
            "functional": [sum(1 for r in out["records"] if r.get("functional")), len(out["records"])], "genuine": len(genuine)}
