#!/usr/bin/env python3
"""Relay one specialist's delivered report to a peer specialist through the hub.

Usage: relay_peer.py <round_dir> <task_id> [--labeller recorded|faithful|unconfigured] [--label-key KEY]
       (the task must carry "peer_of")

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

A relay that cannot be made (a task the round does not hold, a task with no peer, a peer that has not
answered, a peer's specialist file that is not one JSON object of the round format) is refused before
anything is written, with a message naming the task or the file, and the exit status is 2
(run_arena.RoundInputError; round c3: a specialist file written as a one-element list stopped every tool
with "list indices must be integers or slices, not str").

The meaning label (meaning-check design 2.5.7): the peer's answer is labelled as the hub labels it, with ``--labeller``
(default ``EPINOIC_ARENA_LABELLER`` when set, else ``recorded``: the round's labels/ with the recording key ``--label-key`` or
``EPINOIC_ARENA_LABEL_KEY``; ``scripts/arena/arena_labels.py``). The router's file records the label's state on the peer
receipt (``selfcert_label``: state, kind, places, families; never words).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arena_labels as AL  # noqa: E402
from run_arena import RoundInputError, relay_peer  # noqa: E402

USAGE = "usage: relay_peer.py <round_dir> <task_id> [--labeller recorded|faithful|unconfigured] [--label-key KEY]"


def _options(argv: list[str]) -> tuple[list[str], dict] | None:
    """The two positional arguments and the label options, or None for a command line outside the usage."""
    pos, opts, i = [], {}, 0
    while i < len(argv):
        a = argv[i]
        if a in ("--labeller", "--label-key"):
            if i + 1 >= len(argv) or a in opts:
                return None
            opts[a] = argv[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            return None
        pos.append(a)
        i += 1
    if len(pos) != 2 or ("--labeller" in opts and opts["--labeller"] not in AL.LABELLERS):
        return None
    return pos, opts


if __name__ == "__main__":
    parsed = _options(sys.argv[1:])
    if parsed is None:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    (round_arg, task_arg), opts = parsed
    try:
        lab = AL.resolve(opts.get("--labeller"), Path(round_arg).resolve(), key=opts.get("--label-key"))
        out = relay_peer(Path(round_arg).resolve(), task_arg, labeller=lab)
    except RoundInputError as exc:
        print(f"relay_peer.py: nothing relayed, nothing written: {exc}", file=sys.stderr)
        sys.exit(2)
    except ValueError as exc:  # an unknown EPINOIC_ARENA_LABELLER: nothing relayed
        print(f"relay_peer.py: nothing relayed, nothing written: {exc}", file=sys.stderr)
        sys.exit(2)
    router = out["router"]
    receipt = router.get("peer_receipt") or {}
    print(json.dumps({"relayed_file (the dependent agent's only document of its peer)": out["relayed_file"],
                      "router_file (router only: never supplied to an agent)": out["router_file"],
                      "delivered": out["relayed"]["delivered"], "relay_status": out["relayed"]["relay_status"],
                      "request": router.get("request"), "peer_receipt": {"status": receipt.get("status"), "codes": receipt.get("codes")} if receipt else None,
                      "error": router.get("error") or (router.get("relay") or {}).get("error")}, indent=2, default=str))
    print("claims delivered:", len((out["relayed"].get("payload") or {}).get("claims", [])))
