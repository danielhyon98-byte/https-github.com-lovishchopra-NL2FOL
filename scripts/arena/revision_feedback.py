#!/usr/bin/env python3
"""Build the infrastructure's feedback on the round's genuine answers, through the audited hub.

Usage: revision_feedback.py <round_dir> [--revision-rounds N] [--all | <task_id> ...]

Replays each group's genuine traffic on a hub carrying a transfer auditor (the requests, the peer relays with the recorded
relayed documents, the answers) and asks, for every genuine specialist answer (standalone and peer-dependent, never a
synthesis), for the revision request the infrastructure would send (``RouterHub.request_revision``; design section 53 of
``overseer/docs/OVERSEER_DESIGN.md``). It writes one file per answer:

- <round_dir>/feedback/<task_id>.json (``run_arena.FEEDBACK_FILE_KEYS``): whether a request was issued or, if not, why
  (``no_actionable_flaw``: the answer's receipt and the task audit hold no allowlisted flaw, the counted negative
  control; ``refused_by_channel``, with the channel's INT-REV-001; an escalation); the signed block; ``rendered``, the
  exact message the specialist reads, and its digest; the flaws (code, severity, class, basis, rule, claim ids, fault
  signature); the number of advisory items; ``max_rounds``, the revision budget the request was issued under.

The revision budget. ``--revision-rounds N`` issues the feedback under N revision rounds (1 to the hard maximum; the
round-9 exercise used 1) and records N in the round first: ``revision_rounds`` of every covered task in
<round_dir>/tasks.json, the round's setting the harness reads, so a replay re-issues each request exactly as the
specialist read it ('Revision request 1 of 1'). A task that already records another budget (in tasks.json or in its
specialist file) is refused with exit status 2 before anything is written; nothing is overwritten. Without the option
the round's own setting applies, else the channel's default (2). Arena round 9 (c2) issued its feedback under one round
while its tasks.json recorded none, so the harness's revision pass re-issued every request under the default and its gate
feedback_as_read failed on configuration for all 15 revisions; the harness now also reads the budget from each recorded
feedback file's signed block (``run_arena.replay_budgets``).

The flaws come from the answer's receipt and a signed task audit only, as fixed text from the allowlist
(``feedback-rules/1``): never an agent's words, never another agent's text, never a claim outcome. Brief the specialist
with ``rendered`` alone, after its own answer: it never reads the block, the receipts or another agent's material.
Record the specialist's revision in <round_dir>/revisions/<task_id>.json with ``feedback_sha256``, the digest of the
message it read (``rendered_sha256`` of the feedback file it was sent): without it the harness cannot show that the
specialist read the feedback as issued, and its gate feedback_as_read fails (``run_arena.UNRECORDED_READ_FLAG``).
``run_arena.py`` re-issues each request when it replays the round and reports whether the flaws, the keep list and the
rendered digest are still the recorded ones (``recorded_feedback_checks``), then delivers ``revisions/<task_id>.json``;
``run_arena.py --fail-on-revision-gates`` exits with status 1 when a gate of that pass fails.

Standard output is the router's: one line per answer (issued or why not, and the flaw codes), never a finding message.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_arena import revision_feedback  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the infrastructure's feedback on a round's genuine answers (feedback/<task>.json).")
    ap.add_argument("round_dir", type=Path)
    ap.add_argument("task_ids", nargs="*", help="the answers to build feedback on (default, or --all: every genuine answer)")
    ap.add_argument("--all", action="store_true", help="every genuine answer of the round (the default)")
    ap.add_argument("--revision-rounds", type=int, metavar="N",
                    help="issue the feedback under N revision rounds and record N as the round's revision_rounds in tasks.json first")
    args = ap.parse_args(argv)
    rd = args.round_dir.resolve()
    try:
        out = revision_feedback(rd, args.task_ids or None, revision_rounds=args.revision_rounds)
    except ValueError as exc:  # a budget out of range, or one the round already records otherwise: nothing was written
        print(json.dumps({"error": str(exc)}))
        return 2
    for t in out.get("tasks", []):
        print(json.dumps(t))
    print(json.dumps({"feedback_files": len(out["files"]), "issued": out["issued"], "by_reason": out["by_reason"], "directory": str(rd / "feedback"),
                      "revision_budget": out.get("budget")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
