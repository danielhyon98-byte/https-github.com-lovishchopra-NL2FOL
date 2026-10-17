#!/usr/bin/env python3
"""Write the kit's SYNTHETIC simulation corpus in the arena round format (``integration/sim/corpus/synthetic/s1/``).

Every text here was written for the kit: no recorded round, no student text, no model output. Each item is a
specialist answer (``specialists/<item>.json``: task_id, subject, agent_id, task_type, question, supplied_texts,
response_text) and, where its claims are eligible, translation fixtures (``translations/<item>.json``: report_id, claims,
claim_text_sha256) bound to the claim texts the translator's own parser extracts (the digests are computed here with
that parser, exactly as ``scripts/arena/list_claims.py --json`` prints them). ``tasks.json`` lists the tasks without
their answers. ``python integration/tools/build_corpus.py --check`` fails when a file differs from what this script
writes (``tests/integration/test_sim_corpus.py`` runs it).

Items (what each one is for in the simulation, PROTOCOL.md section 14.5):

=========  ===========================================  =====================================================
hi-s1      History, consistent dates                     delivered; formal results of the encoding only
hi-s2      History, planted chronology error              refused: the receipt names the inconsistency
hi-s3      History, the hi-s1 claims worded differently   duplicate mode with a different second answer
en-s1      English interpretive answer                    the interpretations are not eligible (labelled so)
ph-s1      Physics, correct worked arithmetic (STEM)      the STEM check holds
ph-s2      Physics, wrong worked arithmetic (STEM)        refused: the STEM check refutes the written step
=========  ===========================================  =====================================================
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "integration" / "sim" / "corpus" / "synthetic" / "s1"

MEM = {"kind": "general_knowledge", "certainty": "probable", "note": "SYNTHETIC: stated from memory"}
INF = {"kind": "specialist_inference", "certainty": "established"}
ARITH = {"kind": "arithmetic_fact"}


def v(n: str) -> dict:
    return {"op": "var", "name": n}


def i(x: int) -> dict:
    return {"op": "int", "value": str(x)}


def r(x: int) -> dict:
    return {"op": "real", "value": str(x)}


HISTORY_Q = "SYNTHETIC: How far did the Treaty of Versailles destabilise the Weimar Republic? Answer briefly, with dates."
POINT = "The Treaty of Versailles weakened the Weimar Republic, though it does not explain its instability alone."
EVIDENCE = " The treaty was signed in 1919 and imposed reparations on Germany."
GAP_4 = " The hyperinflation peaked in 1923, four years after the treaty was signed."
GAP_2 = " The hyperinflation peaked in 1923, two years after the treaty was signed."
DEBATE = " Historians still debate how far the treaty, rather than the hyperinflation, explains the later instability of the republic."
DEBATE_3 = " How far the treaty, rather than the hyperinflation, explains the republic's later instability is still debated by historians."
#: The runtime's History gate requires a sources line; the synthetic gate of the agents repository accepts exactly this one.
SOURCES = "\nSources: none consulted (no retrieval in this session)"
ENGLISH_Q = "SYNTHETIC: In one short paragraph, how does the poem's final image comment on power?"
ENGLISH = ("The final image suggests that power does not last. The empty sands that stretch away from the broken statue make the "
           "ruler's boast sound hollow. The reader is left to judge the ruler by what remains, which is almost nothing.")
PHYSICS_Q = "SYNTHETIC: A car travels 120 km in 2 hours. Find its average speed in km/h."


def _wrap(problem: dict, reading: str) -> dict:
    return {"problem": problem, "interpretation": {"reading": f"SYNTHETIC: {reading}", "glossary": [], "ambiguity_flags": []},
            "ambiguous": False, "unsupported_reason": None}


def history_point(task: str) -> dict:
    p = {"ir_version": "1.0", "problem_id": f"{task}-h1.1", "request_id": f"req-{task}", "claim_id": "h1.1", "query": "entailment",
         "symbols": [{"name": "reparations", "sort": "Bool", "meaning": "the treaty imposed reparations on Germany", "grounding": MEM},
                     {"name": "hyperinflation", "sort": "Bool", "meaning": "the hyperinflation peaked in 1923", "grounding": MEM},
                     {"name": "weakened", "sort": "Bool", "meaning": "the treaty weakened the republic", "grounding": INF},
                     {"name": "not_alone", "sort": "Bool", "meaning": "the treaty does not explain the instability alone", "grounding": INF}],
         "premises": [{"id": "e_reparations", "expr": v("reparations"), "label": "the treaty imposed reparations on Germany", "grounding": MEM, "materiality": "supporting"},
                      {"id": "e_hyperinflation", "expr": v("hyperinflation"), "label": "the hyperinflation peaked in 1923", "grounding": MEM, "materiality": "supporting"},
                      {"id": "l_weakened", "expr": {"op": "implies", "left": v("reparations"), "right": v("weakened")},
                       "label": "reparations weakened the republic (the stated link)", "grounding": INF, "materiality": "material"},
                      {"id": "l_not_alone", "expr": {"op": "implies", "left": v("hyperinflation"), "right": v("not_alone")},
                       "label": "a second cause means the treaty does not explain the instability alone (the stated link)", "grounding": INF, "materiality": "material"}],
         "conclusion": {"id": "claim", "expr": {"op": "and", "args": [v("weakened"), v("not_alone")]}, "label": POINT, "grounding": INF, "materiality": "material"}}
    return _wrap(p, "the point follows from two remembered facts and two stated links.")


def history_gap(task: str, years: int) -> dict:
    p = {"ir_version": "1.0", "problem_id": f"{task}-h1.3", "request_id": f"req-{task}", "claim_id": "h1.3", "query": "entailment",
         "symbols": [{"name": "treaty_yr", "sort": "Int", "meaning": "the year the treaty was signed", "grounding": MEM},
                     {"name": "peak_yr", "sort": "Int", "meaning": "the year the hyperinflation peaked", "grounding": MEM}],
         "premises": [{"id": "p_treaty_yr", "expr": {"op": "eq", "left": v("treaty_yr"), "right": i(1919)}, "label": "the treaty was signed in 1919", "grounding": MEM, "materiality": "material"},
                      {"id": "p_peak_yr", "expr": {"op": "eq", "left": v("peak_yr"), "right": i(1923)}, "label": "the hyperinflation peaked in 1923", "grounding": MEM, "materiality": "material"}],
         "conclusion": {"id": "claim", "expr": {"op": "eq", "left": v("peak_yr"), "right": {"op": "add", "args": [v("treaty_yr"), i(years)]}},
                        "label": f"the peak came {years} years after the treaty", "grounding": MEM, "materiality": "material"}}
    return _wrap(p, "the interval between two remembered dates.")


def english_point(task: str) -> dict:
    p = {"ir_version": "1.0", "problem_id": f"{task}-p1-point", "request_id": f"req-{task}", "claim_id": "p1-point", "query": "entailment",
         "symbols": [{"name": "hollow", "sort": "Bool", "meaning": "the empty sands make the ruler's boast sound hollow", "grounding": INF},
                     {"name": "remains", "sort": "Bool", "meaning": "the reader judges the ruler by what remains", "grounding": INF},
                     {"name": "transient", "sort": "Bool", "meaning": "the final image suggests that power does not last", "grounding": INF}],
         "premises": [{"id": "e_hollow", "expr": v("hollow"), "label": "the empty sands make the boast sound hollow", "grounding": INF, "materiality": "supporting"},
                      {"id": "e_remains", "expr": v("remains"), "label": "the ruler is judged by what remains", "grounding": INF, "materiality": "supporting"},
                      {"id": "l_transient", "expr": {"op": "implies", "left": {"op": "and", "args": [v("hollow"), v("remains")]}, "right": v("transient")},
                       "label": "a hollow boast judged by its ruins means power does not last (the stated link)", "grounding": INF, "materiality": "material"}],
         "conclusion": {"id": "claim", "expr": v("transient"), "label": "The final image suggests that power does not last.", "grounding": INF, "materiality": "material"}}
    return _wrap(p, "the interpretive point follows from the two interpretations and the stated link; every premise is the specialist's.")


def speed(task: str, claim_id: str, value: int) -> dict:
    p = {"ir_version": "1.0", "problem_id": f"{task}-{claim_id}", "request_id": f"req-{task}", "claim_id": claim_id, "query": "entailment",
         "symbols": [{"name": "d", "sort": "Real", "meaning": "the distance in km"}, {"name": "speed", "sort": "Real", "meaning": "the average speed in km/h"}],
         "premises": [{"id": "D", "expr": {"op": "eq", "left": v("d"), "right": r(120)}, "label": "distance 120 km", "grounding": ARITH},
                      {"id": "SPEED", "expr": {"op": "eq", "left": v("speed"), "right": {"op": "div", "left": v("d"), "right": r(2)}},
                       "label": "speed is the distance over the 2 h", "grounding": ARITH}],
         "conclusion": {"id": "C", "expr": {"op": "eq", "left": v("speed"), "right": r(value)}, "label": f"the speed is {value} km/h"}}
    return _wrap(p, "average speed as distance over time.")


def physics_answer(value: int) -> str:
    return f"Average speed is distance divided by time.\nv = d / t = 120 km / 2 h = {value} km/h\nThe average speed is {value} km/h."


#: item -> (subject, agent id, task type, question, answer, {claim id: fixture})
ITEMS: dict[str, tuple] = {
    "hi-s1": ("History", "history", "short_answer", HISTORY_Q, POINT + EVIDENCE + GAP_4 + DEBATE + SOURCES,
              {"h1.1": history_point("hi-s1"), "h1.3": history_gap("hi-s1", 4)}),
    "hi-s2": ("History", "history", "short_answer", HISTORY_Q, POINT + EVIDENCE + GAP_2 + DEBATE + SOURCES,
              {"h1.1": history_point("hi-s2"), "h1.3": history_gap("hi-s2", 2)}),
    "hi-s3": ("History", "history", "short_answer", HISTORY_Q, POINT + EVIDENCE + GAP_4 + DEBATE_3 + SOURCES,
              {"h1.1": history_point("hi-s3"), "h1.3": history_gap("hi-s3", 4)}),
    "en-s1": ("English A: Literature", "english-a-literature", "analytical_paragraph", ENGLISH_Q, ENGLISH,
              {"p1-point": english_point("en-s1")}),
    "ph-s1": ("Physics", "physics", "calculation", PHYSICS_Q, physics_answer(60),
              {"s1.2": speed("ph-s1", "s1.2", 60), "s1.3": speed("ph-s1", "s1.3", 60)}),
    "ph-s2": ("Physics", "physics", "calculation", PHYSICS_Q, physics_answer(50),
              {"s1.2": speed("ph-s2", "s1.2", 50), "s1.3": speed("ph-s2", "s1.3", 50)}),
}


def _claim_texts(item: str, subject: str, agent: str, task_type: str, answer: str) -> dict[str, str]:
    from epinoic_logic.branches import default_registry
    branch, _profile = default_registry().for_subject(subject)
    report = branch.parser().parse_response(answer, request_id=f"req-{item}", task_id=item, report_id=f"rep-{item}-0", subject=subject,
                                            task_type=task_type, supplied_texts=[], agent_id=agent)
    return {c.claim_id: c.claim_text for c in report.claims}


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def outputs() -> dict[Path, str]:
    from epinoic_logic.translate.contracts import sha256_text
    files: dict[Path, str] = {}
    tasks = []
    for item, (subject, agent, task_type, question, answer, fixtures) in ITEMS.items():
        files[OUT / "specialists" / f"{item}.json"] = _dump({"task_id": item, "subject": subject, "agent_id": agent, "task_type": task_type,
                                                              "question": question, "supplied_texts": [], "response_text": answer})
        tasks.append({"task_id": item, "subject": subject, "agent_id": agent, "task_type": task_type, "question": question, "supplied_texts": []})
        texts = _claim_texts(item, subject, agent, task_type, answer)
        missing = sorted(set(fixtures) - set(texts))
        if missing:
            raise SystemExit(f"{item}: the parser extracts no claim {missing}; the corpus must be rebuilt by hand")
        files[OUT / "translations" / f"{item}.json"] = _dump({"report_id": f"rep-{item}-0", "claims": fixtures,
                                                               "claim_text_sha256": {cid: sha256_text(texts[cid]) for cid in fixtures}})
    files[OUT / "tasks.json"] = _dump(tasks)
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="write the synthetic simulation corpus")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    files = outputs()
    stale = [p for p in OUT.rglob("*.json") if p not in files] if OUT.exists() else []
    drifted = [p for p, t in files.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
    if args.check:
        for p in drifted + stale:
            print(f"drift: {p.relative_to(ROOT)}")
        return 1 if drifted or stale else 0
    for p in stale:
        p.unlink()
    for p in drifted:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(files[p], encoding="utf-8")
    print(f"corpus: {len(files)} file(s); {len(drifted)} written, {len(stale)} removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
