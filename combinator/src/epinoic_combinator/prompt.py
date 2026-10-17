"""What the combinator agent is given: the instruction pack as its instructions, and the request's sources as one JSON
document (the input's claims without their digests, the port's envelope or the pack reference, which are the runner's
business and never the agent's).
"""
from __future__ import annotations

import json
from typing import Any, Mapping

__all__ = ["agent_view", "render"]


def agent_view(inp: Mapping[str, Any]) -> dict:
    """The part of a checked combinator input the agent reads, in the input's own order."""
    return {
        "request": {"task_id": inp["ids"]["task_id"], "request_id": inp["ids"]["request_id"]},
        "sources": [{"report_id": s["report_id"], "agent_id": s["agent_id"], "subject": s["subject"], "branch": s["branch"],
                     "claims": [{"claim_id": c["claim_id"], "role": c["role"], "materiality": c["materiality"],
                                 "certainty": c["certainty"], "text": c["text"]} for c in s["claims"]]}
                    for s in inp["sources"]],
    }


def render(inp: Mapping[str, Any]) -> str:
    """The agent's message: :func:`agent_view` as indented JSON (deterministic: the same input gives the same text)."""
    return json.dumps(agent_view(inp), indent=2, ensure_ascii=False)
