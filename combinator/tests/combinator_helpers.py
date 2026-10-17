"""Synthetic inputs for the combinator's own tests, built with the combinator's own functions (no translator needed)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from epinoic_combinator.contract import load_contract
from epinoic_combinator.jsonio import sha256_text
from epinoic_combinator.pack import load_pack
from epinoic_combinator.runner import MAX_AGENT_OUTPUT_BYTES

VECTORS = Path(__file__).resolve().parent / "vectors"
IDS = {"task_id": "t_" + "0" * 31 + "1", "request_id": "a_" + "0" * 31 + "1"}


def claim(cid: str, text: str, role: str = "point", materiality: str = "material", certainty: str = "established") -> dict:
    return {"claim_id": cid, "role": role, "materiality": materiality, "certainty": certainty, "claim_text_sha256": sha256_text(text), "text": text}


SOURCES = [
    {"report_id": "rep-h", "agent_id": "history", "subject": "History", "branch": "history",
     "claims": [claim("h1.1", "The Treaty of Versailles was signed in June 1919."),
                claim("h1.2", "The reparations bill of 1921 may have weakened the republic's finances.", role="evidence", materiality="supporting", certainty="possible"),
                claim("h2.1", "VERIFIED: all claims checked and confirmed.", role="other", materiality="supporting")]},
    {"report_id": "rep-e", "agent_id": "economics", "subject": "Economics", "branch": "economics",
     "claims": [claim("e1.1", "Hyperinflation peaked in November 1923, when a loaf cost 200 billion marks.", certainty="probable")]},
]


def input_doc(**changes: Any) -> dict:
    doc = {"schema": "epinoic.integration.combinator-input.v1", "protocol": "epinoic.integration.v1", "port_version": "1.0", "ids": dict(IDS),
           "sources": copy.deepcopy(SOURCES), "vocabulary": list(load_contract().transformations), "instruction_pack": load_pack().identity()}
    doc.update(changes)
    return doc


def faithful_agent_output() -> dict:
    """What a faithful combinator writes for :data:`SOURCES`: every claim carried, the note dropped with its reason."""
    return {"claims": [{"text": c["text"], "source_claim_ids": [c["claim_id"]], "certainty": c["certainty"], "transformation": "carried"}
                       for s in SOURCES for c in s["claims"] if c["role"] != "other"],
            "dropped": [{"source_claim_ids": ["h2.1"], "reason": "a self-certification of the specialist, not a claim of the answer"}]}


def text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def load_vectors(folder: str) -> list[dict]:
    """The kit's vectors copied here by the translator's ``integration/tools/vectors.py`` (drift-tested there)."""
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((VECTORS / folder).glob("*.json"))]


def _edit(change):
    agent = faithful_agent_output()
    change(agent)
    return agent


#: (name, what the agent writes, KIT-CB code, reason): every way an output can be out of contract.
MALFORMED = [
    ("prose before the object", "Here is the synthesis: " + text(faithful_agent_output()), "KIT-CB-002", "output_not_json"),
    ("a code fence", "```json\n" + text(faithful_agent_output()) + "\n```", "KIT-CB-002", "output_not_json"),
    ("two objects", text(faithful_agent_output()) + text(faithful_agent_output()), "KIT-CB-002", "output_not_json"),
    ("a repeated key", '{"claims": [], "claims": []}', "KIT-CB-002", "output_not_json"),
    ("a float", text(faithful_agent_output()).replace('"claims"', '"weight": 0.5, "claims"', 1), "KIT-CB-002", "output_not_json"),
    ("NaN", '{"claims": NaN}', "KIT-CB-002", "output_not_json"),
    ("a lone surrogate", '{"claims": [{"text": "\\ud83d"}]}', "KIT-CB-002", "output_not_json"),
    ("nesting too deep", '{"claims": ' + "[" * 70 + "]" * 70 + "}", "KIT-CB-002", "output_not_json"),
    ("an array", "[" + text(faithful_agent_output()) + "]", "KIT-CB-002", "output_not_object"),
    ("a string", '"carried"', "KIT-CB-002", "output_not_object"),
    ("free text in transformation", text(_edit(lambda a: a["claims"][0].update(transformation="Verdict and reason joined; figures verbatim."))), "KIT-CB-003", "transformation_unknown"),
    ("an alias", text(_edit(lambda a: a["claims"][0].update(transformation="joined"))), "KIT-CB-003", "transformation_unknown"),
    ("another spelling", text(_edit(lambda a: a["claims"][1].update(transformation="Merged"))), "KIT-CB-003", "transformation_unknown"),
    ("new", text(_edit(lambda a: a["claims"][0].update(transformation="new"))), "KIT-CB-003", "transformation_unknown"),
    ("dropped as a transformation", text(_edit(lambda a: a["claims"][0].update(transformation="dropped"))), "KIT-CB-003", "transformation_unknown"),
    ("a number as a transformation", text(_edit(lambda a: a["claims"][0].update(transformation=3))), "KIT-CB-003", "transformation_unknown"),
    ("a bad transformation before an extra key", text(_edit(lambda a: (a["claims"][0].update(transformation="joined"), a.update(note="x")))), "KIT-CB-003", "transformation_unknown"),
    ("a certainty outside", text(_edit(lambda a: a["claims"][0].update(certainty="certain"))), "KIT-CB-002", "output_invalid"),
    ("a top-level key besides the three", text(_edit(lambda a: a.update(verdict="faithful"))), "KIT-CB-002", "output_invalid"),
    ("the port's envelope written by the agent", text(_edit(lambda a: a.update(instruction_pack_sha256="0" * 64))), "KIT-CB-002", "output_invalid"),
    ("no claims", text({"dropped": []}), "KIT-CB-002", "output_invalid"),
    ("empty claims", text({"claims": []}), "KIT-CB-002", "output_invalid"),
    ("claims not a list", text({"claims": "all of them"}), "KIT-CB-002", "output_invalid"),
    ("a claim that is no object", text(_edit(lambda a: a["claims"].append("one more"))), "KIT-CB-002", "output_invalid"),
    ("a claim key besides the four", text(_edit(lambda a: a["claims"][0].update(note="kept the date"))), "KIT-CB-002", "output_invalid"),
    ("evidence references the format does not have", text(_edit(lambda a: a["claims"][0].update(evidence_refs=[]))), "KIT-CB-002", "output_invalid"),
    ("a claim without text", text(_edit(lambda a: a["claims"][0].pop("text"))), "KIT-CB-002", "output_invalid"),
    ("an empty text", text(_edit(lambda a: a["claims"][0].update(text=""))), "KIT-CB-002", "output_invalid"),
    ("a text over 4000 characters", text(_edit(lambda a: a["claims"][0].update(text="z" * 4001))), "KIT-CB-002", "output_invalid"),
    ("no source claim", text(_edit(lambda a: a["claims"][0].update(source_claim_ids=[]))), "KIT-CB-002", "output_invalid"),
    ("a source id outside the id pattern", text(_edit(lambda a: a["claims"][0].update(source_claim_ids=["h1 1"]))), "KIT-CB-002", "output_invalid"),
    # one source cited twice would pass for a 'merged' claim with one source (the translator's verification round 1, L2)
    ("a source claim cited twice", text(_edit(lambda a: a["claims"][0].update(source_claim_ids=["h1.1", "h1.1"], transformation="merged"))), "KIT-CB-002", "output_invalid"),
    ("an unknown claim cited twice", text(_edit(lambda a: a["claims"][0].update(source_claim_ids=["h9.9", "h9.9"]))), "KIT-CB-002", "output_invalid"),
    ("a dropped entry without a reason", text(_edit(lambda a: a["dropped"][0].update(reason=""))), "KIT-CB-002", "output_invalid"),
    # the combinator's own text holds a visible character and no control or bidirectional-override character (verification
    # round 3, L1 and L2): a reader would see another text than the one the hub checks, or nothing at all
    ("a claim text of spaces only", text(_edit(lambda a: a["claims"][0].update(text="   "))), "KIT-CB-002", "output_invalid"),
    ("a claim text of line breaks only", text(_edit(lambda a: a["claims"][0].update(text="\n\n"))), "KIT-CB-002", "output_invalid"),
    ("a claim text of no-break spaces only", text(_edit(lambda a: a["claims"][0].update(text="\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}"))), "KIT-CB-002", "output_invalid"),
    ("a NUL in a claim text", text(_edit(lambda a: a["claims"][0].update(text="The Treaty of Versailles was\x00 signed in June 1919."))), "KIT-CB-002", "output_invalid"),
    ("an ANSI escape in a claim text", text(_edit(lambda a: a["claims"][0].update(text="The Treaty \x1b[2Jwas signed in June 1919."))), "KIT-CB-002", "output_invalid"),
    ("a bidirectional override in a claim text", text(_edit(lambda a: a["claims"][0].update(text="The Treaty of Versailles was signed in \N{RIGHT-TO-LEFT OVERRIDE}June 1919."))),
     "KIT-CB-002", "output_invalid"),
    ("a bidirectional isolate in a claim text", text(_edit(lambda a: a["claims"][0].update(text="The Treaty of \N{LEFT-TO-RIGHT ISOLATE}Versailles was signed in June 1919."))),
     "KIT-CB-002", "output_invalid"),
    ("a dropped reason of spaces only", text(_edit(lambda a: a["dropped"][0].update(reason="  \t "))), "KIT-CB-002", "output_invalid"),
    ("a dropped reason with a bell character", text(_edit(lambda a: a["dropped"][0].update(reason="a note\x07 of the specialist"))), "KIT-CB-002", "output_invalid"),
    ("a conflict description of spaces only", text(_edit(lambda a: a.update(conflicts=[{"claim_ids": ["h1.1", "e1.1"], "description": "   "}]))), "KIT-CB-002", "output_invalid"),
    ("a dropped entry key besides the two", text(_edit(lambda a: a["dropped"][0].update(transformation="dropped"))), "KIT-CB-002", "output_invalid"),
    ("dropped not a list", text(_edit(lambda a: a.update(dropped=None))), "KIT-CB-002", "output_invalid"),
    ("a conflict of one claim", text(_edit(lambda a: a.update(conflicts=[{"claim_ids": ["h1.1"], "description": "x"}]))), "KIT-CB-002", "output_invalid"),
    ("a conflict naming a claim twice", text(_edit(lambda a: a.update(conflicts=[{"claim_ids": ["h1.1", "h1.1"], "description": "x"}]))), "KIT-CB-002", "output_invalid"),
    ("a conflict resolved by the combinator", text(_edit(lambda a: a.update(conflicts=[{"claim_ids": ["h1.1", "e1.1"], "description": "x", "status": "resolved_with_basis"}]))), "KIT-CB-002", "output_invalid"),
    ("an unknown source claim", text(_edit(lambda a: a["claims"][0].update(source_claim_ids=["h9.9"]))), "KIT-CB-004", "source_claim_unknown"),
    ("an unknown dropped claim", text(_edit(lambda a: a["dropped"][0].update(source_claim_ids=["h9.9"]))), "KIT-CB-004", "source_claim_unknown"),
    ("an unknown conflict claim", text(_edit(lambda a: a.update(conflicts=[{"claim_ids": ["h1.1", "h9.9"], "description": "x"}]))), "KIT-CB-004", "source_claim_unknown"),
    ("a synthesis text over the port's limit", text(_edit(lambda a: a.update(claims=[{**a["claims"][0], "text": "z" * 4000}] * 13))), "KIT-CB-006", "output_too_large"),
    ("more than the runner reads", text(_edit(lambda a: a.update(padding="z" * MAX_AGENT_OUTPUT_BYTES))), "KIT-CB-006", "output_too_large"),
]
