#!/usr/bin/env python3
"""Build the infrastructure's feedback on the round's genuine answers, through the audited hub.

Usage: revision_feedback.py <round_dir> [--all | <task_id> ...]

Replays each group's genuine traffic on a hub carrying a transfer auditor (the requests, the peer relays with the recorded
relayed documents, the answers) and asks, for every genuine specialist answer (standalone and peer-dependent, never a
synthesis), for the revision request the infrastructure would send (``RouterHub.request_revision``; design section 53 of
``overseer/docs/OVERSEER_DESIGN.md``). It writes one file per answer:

- <round_dir>/feedback/<task_id>.json (``run_arena.FEEDBACK_FILE_KEYS``): whether a request was issued or, if not, why
  (``no_actionable_flaw``: the answer's receipt and the task audit hold no allowlisted flaw, the counted negative
  control; ``refused_by_channel``, with the channel's INT-REV-001; an escalation); the signed block; ``rendered``, the
  exact message the specialist reads, and its digest; the flaws (code, severity, class, basis, rule, claim ids, fault
  signature); the number of advisory items.

The flaws come from the answer's receipt and a signed task audit only, as fixed text from the allowlist
(``feedback-rules/1``): never an agent's words, never another agent's text, never a claim outcome. Brief the specialist
with ``rendered`` alone, after its own answer: it never reads the block, the receipts or another agent's material.
``run_arena.py`` re-issues each request when it replays the round and reports whether the flaws, the keep list and the
rendered digest are still the recorded ones (``recorded_feedback_checks``), then delivers ``revisions/<task_id>.json``.

Standard output is the router's: one line per answer (issued or why not, and the flaw codes), never a finding message.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_arena import revision_feedback  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    rd = Path(sys.argv[1]).resolve()
    wanted = [a for a in sys.argv[2:] if a != "--all"] or None
    out = revision_feedback(rd, wanted)
    for t in out.get("tasks", []):
        print(json.dumps(t))
    print(json.dumps({"feedback_files": len(out["files"]), "issued": out["issued"], "by_reason": out["by_reason"], "directory": str(rd / "feedback")}))
