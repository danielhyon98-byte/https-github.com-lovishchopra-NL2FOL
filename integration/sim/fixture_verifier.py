"""The arena's fixture-serving rule as the simulation applies it (PROTOCOL.md section 14.5; integration/README.md, T8).

The service's fixture provider (``epinoic_logic.integration.verifier.FixtureCorpus``) serves a corpus item's
translation fixtures exactly as ``scripts/arena/run_arena.py`` does for the same item: by claim id, bound to the claim
text each fixture was produced for (a changed text is refused as stale), nothing for a claim id outside the fixtures,
and called as ``fn(claim, report)`` without a task. This module delivers one item's recorded answer on a fresh hub the
way the arena's genuine pass does, so ``tests/integration/test_fixture_parity.py`` can show, item by item, that both
serve the same fixtures to the same claims, leave the same ones unserved and reach the same statuses.

It never edits the arena harness and never stands in for it: the parity test runs ``run_arena.run_round`` itself on a
copy of the corpus and compares.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

__all__ = ["load_corpus", "deliver_genuine", "unsupported_item"]


def load_corpus(directory: str | Path) -> Any:
    from epinoic_logic.integration.verifier import FixtureCorpus
    return FixtureCorpus.load(directory)


def unsupported_item(item: dict) -> Optional[str]:
    """Why the simulation's fixture verifier cannot replay ``item`` alone (peer relays and groups need the arena's own
    multi-agent pass), or ``None``."""
    if item.get("peer_of"):
        return "peer-dependent item (its peer's report is relayed through the hub)"
    if item.get("group"):
        return "grouped item (several agents share one hub task)"
    return None


def deliver_genuine(corpus: Any, item: dict, plan: Any, *, config: Any, signing_key: bytes, key_id: Optional[str] = None,
                    supplied: Optional[list] = None) -> tuple[Any, Any]:
    """Deliver ``item``'s recorded answer under ``plan`` on a fresh hub whose channel verifies with the corpus's fixtures,
    as the arena's genuine pass does (report id ``rep-<task>-0``). Returns ``(reply, receipt)``."""
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.translate.contracts import sha256_text
    why = unsupported_item(item)
    if why is not None:
        raise ValueError(f"item {item.get('task_id')!r}: {why}")
    fn, _provider = corpus.verifier_for(sha256_text(item["response_text"]), config=config, signing_key=signing_key, key_id=key_id)
    hub = RouterHub(signing_key=signing_key, config=config)
    channel = hub.open_task(plan)
    channel.verify_claim_fn = fn
    msg, _req, receipt = hub.dispatch(plan.task_id, item["agent_id"], item["question"], list(supplied or []))
    if msg is None:
        return None, receipt
    return hub.receive(plan.task_id, msg.message_id, item["response_text"], agent_id=item["agent_id"], report_id=f"rep-{item['task_id']}-0")
