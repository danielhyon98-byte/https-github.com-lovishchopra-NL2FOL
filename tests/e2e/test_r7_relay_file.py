"""What a peer-dependent agent may read of its peer (``scripts/arena/run_arena.py`` ``relay_peer``; round-7 router and
envelope review, router-envelope-1, blocker).

relay_peer() wrote the router-side receipt of the peer's delivery (every finding, subject finding and formal check, with
its message) into ``<round>/relayed/<task>.json``, the only file the dependent agent may read, and a dependent agent
repeated a false INT-SUBJ-001 to the student. The relayed file must hold the delivered payload, its document id and the
relay status only; the receipt goes to the router's ``<round>/router/<task>.json``. The fuller tests are in
``scripts/arena/test_arena_rules.py`` (run by path); this one keeps the rule in the default suite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import run_arena as ra  # noqa: E402

HISTORY_PEER = {
    "task_id": "hi-y1", "group": "y1", "subject": "History", "agent_id": "history-specialist", "task_type": "short_answer",
    "question": "In one paragraph of no more than 200 words, outline the historical context of London in 1802 for a student "
                "reading a sonnet written that year, with dated evidence labelled from memory.",
    "supplied_texts": [],
    "response_text": "London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801. "
                     "Coal smoke from homes and workshops hung over the city for much of the year. "
                     "Against this background, the \"smokeless air\" of the sonnet stands out as an exception to the city's ordinary condition. "
                     "The Peace of Amiens, signed in March 1802, briefly ended the war with France.",
}
ENGLISH_DEPENDENT = {
    "task_id": "en-y1", "group": "y1", "peer_of": "hi-y1", "subject": "English A: Literature", "agent_id": "english-specialist",
    "task_type": "analytical_paragraph",
    "question": "Write one analytical paragraph of no more than 200 words: how does the History specialist's context change a reading of the "
                "sonnet's 'smokeless air'? Quote the relayed report exactly.",
    "supplied_texts": [],
    "response_text": "The History specialist's report says that \"Coal smoke from homes and workshops hung over the city for much of the year.\" "
                     "Read against that, the calm of the sonnet is an exception rather than the rule, so its praise records a moment of seeing the city differently.",
}
RECEIPT_KEYS = {"peer_receipt", "relay", "plan", "request", "error", "findings", "subject_findings", "structural_findings",
                "formal_checks", "constraints", "constraint_results", "codes", "summary"}


def _keys(value) -> set:
    if isinstance(value, dict):
        return set(value) | set().union(*(_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value)) if value else set()
    return set()


def test_the_relayed_file_holds_the_delivered_payload_only_and_the_receipt_is_the_routers(tmp_path):
    (tmp_path / "specialists").mkdir()
    (tmp_path / "specialists" / "hi-y1.json").write_text(json.dumps(HISTORY_PEER))
    (tmp_path / "specialists" / "en-y1.json").write_text(json.dumps(ENGLISH_DEPENDENT))
    ra.relay_peer(tmp_path, "en-y1")
    text = (tmp_path / "relayed" / "en-y1.json").read_text()
    relayed = json.loads(text)
    assert not _keys(relayed) & RECEIPT_KEYS, sorted(_keys(relayed) & RECEIPT_KEYS)
    assert set(relayed) == {"task_id", "peer_of", "delivered", "relay_status", "document_id", "payload"}
    assert relayed["delivered"] is True and relayed["relay_status"] == "ACCEPTED" and relayed["document_id"] == "peer:hi-y1"
    assert relayed["payload"]["original_response"] == HISTORY_PEER["response_text"]
    router = json.loads((tmp_path / "router" / "en-y1.json").read_text())
    receipt = router["peer_receipt"]
    messages = [f["message"] for f in receipt["findings"] + receipt["subject_findings"] if f.get("message")]
    assert receipt["status"] == "ACCEPTED_WITH_FINDINGS" and messages, "control: the peer's receipt carries findings with messages"
    assert not [m for m in messages if m in text] and not [c for c in receipt["codes"] if c in text]
