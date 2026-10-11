#!/usr/bin/env python3
"""Print the claim records the infrastructure extracts from a specialist output file,
so a dummy combinator can cite them and a translation provider can formalize them.
Usage: list_claims.py <specialist.json> [--eligible] [--json]

A peer-dependent task (``peer_of``) is listed with the peer's report supplied as the document
``peer:<task>`` when <round>/relayed/<task_id>.json exists, as the hub supplies it. Every source
reference says whether its excerpt was LOCATED in the named document; an unlocated excerpt is
attributed to the first document only so the hub can report it (INT-REQ-003), not as a claim
that the words are there."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from epinoic_logic.adapters.sources import check_excerpt
from epinoic_logic.branches import default_registry
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.subjects import resolve_profile

spec_path = Path(sys.argv[1]).resolve()
item = json.loads(spec_path.read_text())
if item.get("peer_of"):
    relayed = spec_path.parent.parent / "relayed" / f"{item['task_id']}.json"
    if relayed.exists():
        rel = json.loads(relayed.read_text())
        if rel.get("delivered") and rel.get("payload"):
            item["supplied_texts"] = [*item.get("supplied_texts", []), {"document_id": rel.get("document_id", f"peer:{item['peer_of']}"), "title": "peer report relayed through the hub", "author": rel["payload"].get("agent_id"), "text": rel["payload"]["original_response"]}]
only_eligible = "--eligible" in sys.argv
as_json = "--json" in sys.argv
branch, profile = default_registry().for_subject(item["subject"])
texts = [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"], locator_scheme=t.get("locator_scheme", "none")) for t in item.get("supplied_texts", [])]
group = item.get("group") or spec_path.stem  # tasks of one group share one hub task and request, as in run_arena.py
report = branch.parser().parse_response(item["response_text"], request_id=f"req-{group}", task_id=group, report_id=f"rep-{item['task_id']}-0",
                                        subject=item["subject"], task_type=item.get("task_type", "analytical_paragraph"), supplied_texts=texts, agent_id=item["agent_id"])
rows = []
for c in report.claims:
    e = decide_eligibility(c)
    eligible = e.eligible and profile.allows(e.eligibility_class)
    if only_eligible and not eligible:
        continue
    docs = {t.document_id: t for t in texts}
    refs = [{**r.model_dump(exclude_none=True), "located": bool(r.excerpt) and r.document_id in docs and check_excerpt(r.excerpt, r.document_id, docs).located} for r in c.source_refs]
    rows.append({"claim_id": c.claim_id, "role": c.claim_role, "materiality": c.materiality, "certainty": c.certainty, "eligible": eligible, "eligibility_class": e.eligibility_class.value,
                 "supporting_claim_ids": c.supporting_claim_ids, "source_refs": refs, "text": c.claim_text})
if as_json:
    print(json.dumps({"report_id": report.report_id, "request_id": report.request_id, "branch": branch.key, "claims": rows}, indent=2, ensure_ascii=False))
else:
    print(f"report_id={report.report_id} request_id={report.request_id} branch={branch.key} claims={len(report.claims)}")
    for r in rows:
        unlocated = [x["document_id"] for x in r["source_refs"] if not x["located"]]
        print(f"{r['claim_id']:8} {r['role']:16} {r['materiality']:11} {'ELIGIBLE' if r['eligible'] else '-':9} {r['eligibility_class']:28} supports={r['supporting_claim_ids']}{' UNLOCATED-EXCERPT' if unlocated else ''} :: {r['text'][:140]}")
