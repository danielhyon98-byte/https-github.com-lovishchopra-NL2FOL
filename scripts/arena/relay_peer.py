#!/usr/bin/env python3
"""Relay one specialist's delivered report to a peer specialist through the hub.

Usage: relay_peer.py <round_dir> <task_id>   (the task must carry "peer_of")

Receives the peer task's genuine reply on the group's channel, relays the DELIVERED
report to the requesting agent (agent-to-agent hand-off on the same ledger) and writes
<round_dir>/relayed/<task_id>.json: the relay receipt and the specialist_report/1.0
payload exactly as delivered. That file is the only thing the peer-dependent agent may
read of its peer; the agents never see each other's raw output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_arena import relay_peer  # noqa: E402

if __name__ == "__main__":
    out = relay_peer(Path(sys.argv[1]).resolve(), sys.argv[2])
    print(json.dumps({k: v for k, v in out.items() if k != "payload"}, indent=2, default=str))
    print("claims delivered:", len(out.get("payload", {}).get("claims", [])))
