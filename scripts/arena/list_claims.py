#!/usr/bin/env python3
"""Print the claim records the infrastructure extracts from a specialist output file,
so a dummy combinator can cite them and a translation provider can formalize them.
Usage: list_claims.py <specialist.json> [--eligible] [--json]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from epinoic_logic.branches import default_registry
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.subjects import resolve_profile

item = json.loads(Path(sys.argv[1]).read_text())
only_eligible = "--eligible" in sys.argv
as_json = "--json" in sys.argv
branch, profile = default_registry().for_subject(item["subject"])
texts = [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"], locator_scheme=t.get("locator_scheme", "none")) for t in item.get("supplied_texts", [])]
report = branch.parser().parse_response(item["response_text"], request_id=f"req-{item['task_id']}", task_id=item["task_id"], report_id=f"rep-{item['task_id']}-0",
                                        subject=item["subject"], task_type=item.get("task_type", "analytical_paragraph"), supplied_texts=texts, agent_id=item["agent_id"])
rows = []
for c in report.claims:
    e = decide_eligibility(c)
    eligible = e.eligible and profile.allows(e.eligibility_class)
    if only_eligible and not eligible:
        continue
    rows.append({"claim_id": c.claim_id, "role": c.claim_role, "certainty": c.certainty, "eligible": eligible, "eligibility_class": e.eligibility_class.value,
                 "supporting_claim_ids": c.supporting_claim_ids, "source_refs": [r.model_dump(exclude_none=True) for r in c.source_refs], "text": c.claim_text})
if as_json:
    print(json.dumps({"report_id": report.report_id, "request_id": report.request_id, "branch": branch.key, "claims": rows}, indent=2, ensure_ascii=False))
else:
    print(f"report_id={report.report_id} request_id={report.request_id} branch={branch.key} claims={len(report.claims)}")
    for r in rows:
        print(f"{r['claim_id']:8} {r['role']:16} {'ELIGIBLE' if r['eligible'] else '-':9} {r['eligibility_class']:28} supports={r['supporting_claim_ids']} :: {r['text'][:140]}")
