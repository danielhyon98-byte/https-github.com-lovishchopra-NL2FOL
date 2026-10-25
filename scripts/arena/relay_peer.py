#!/usr/bin/env python3
"""Relay one specialist's delivered report to a peer specialist through the hub.

Usage: relay_peer.py <round_dir> <task_id>   (the task must carry "peer_of")

Receives the peer task's genuine reply on the group's channel, relays the DELIVERED
report to the requesting agent (agent-to-agent hand-off on the same ledger) and writes two files:

- <round_dir>/relayed/<task_id>.json: the specialist_report/1.0 payload exactly as delivered, the
  document id it is supplied as (peer:<peer task>) and the relay status, nothing else
  (run_arena.RELAYED_FILE_KEYS). That file is the only thing the peer-dependent agent may read of
  its peer; the agents never see each other's raw output, and never the hub's receipts.
- <round_dir>/router/<task_id>.json: the router's record of the relay, which no agent reads: the
  plan as used, the request to the peer, the peer's delivery receipt (every finding, subject
  finding, constraint result and formal check, with its message) and the relay's own receipt.

A finding is the router's to act on, not content for the dependent agent: the round-7 router and
envelope review found a dependent agent repeating a false finding of its peer's receipt (INT-SUBJ-001)
to the student (run1), because this tool used to write the receipt into the relayed file.

The group's plan is built by run_arena.group_plan, the same function run_arena.run_round
uses, so the relay and the measured round agree on the selected agents, each agent's
subject branch and each agent's own task type (WorkPlan.agent_task_types: the History
peer's request, report and forward carry its short_answer, not the deliverable's
analytical_paragraph). The plan as used is recorded in the router's file.

run_arena.py never delivers the recorded payload in place of the peer's reply: a re-run parses
the peer's raw response_text with the code as it stands, uses the recording only for the
document the peer-dependent agent read (its original_response), and reports in results.json and
summary.md whether the recorded payload equals the current parse (recorded_relay_checks), and which
router-only fields a recorded relayed file carries (router_fields_exposed: recordings made before the
router's record had its own file).

Standard output is the router's: the two file paths, the relay status and the peer receipt's status
and codes (no finding message). Brief the dependent agent with the relayed file only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_arena import relay_peer  # noqa: E402

if __name__ == "__main__":
    out = relay_peer(Path(sys.argv[1]).resolve(), sys.argv[2])
    router = out["router"]
    receipt = router.get("peer_receipt") or {}
    print(json.dumps({"relayed_file (the dependent agent's only document of its peer)": out["relayed_file"],
                      "router_file (router only: never supplied to an agent)": out["router_file"],
                      "delivered": out["relayed"]["delivered"], "relay_status": out["relayed"]["relay_status"],
                      "request": router.get("request"), "peer_receipt": {"status": receipt.get("status"), "codes": receipt.get("codes")} if receipt else None,
                      "error": router.get("error") or (router.get("relay") or {}).get("error")}, indent=2, default=str))
    print("claims delivered:", len((out["relayed"].get("payload") or {}).get("claims", [])))
