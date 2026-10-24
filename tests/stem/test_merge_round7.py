"""The STEM branches merged with the round-7 development branch: one parser per subject (docs/STEM_DESIGN.md, section 9).

Physics, Chemistry, Biology, ESS, Mathematics (AA and AI) and Computer Science answers go through the STEM parser, which
keeps the round-7 reading the generic parser gave the same answers: the same claims, with the same texts, roles, kinds,
figures, quotations, materiality and supports, under the STEM branch's own ids (``s``, ``m``, ``c``), and the same
request items (one per part; the rubric's "Show your working." is no item). The material is the genuine round-7 answers
(tests/channel/data/r7_material.json)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.channel.request_parser import extract_items
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem.hub_hooks import STEM_IMPERATIVES
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText

R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))
SPEC: dict[str, dict] = R7["specialists"]
STEM_BRANCHES = {"sciences": "s", "mathematics": "m", "computer_science": "c"}
STEM_TASKS = sorted(tid for tid, it in SPEC.items() if default_registry().for_subject(it["subject"])[0].key in STEM_BRANCHES)
KEY = b"round7-stem-merge-test-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def supplied(tid: str) -> list[SuppliedText]:
    it = SPEC[tid]
    docs = [SuppliedText(**t) for t in it.get("supplied_texts", [])]
    peer = it.get("peer_of")
    if peer:
        docs.append(SuppliedText(document_id=f"peer:{peer}", title="peer report relayed through the hub", author=SPEC[peer]["agent_id"], text=SPEC[peer]["response_text"]))
    return docs


def reports(tid: str) -> tuple[SpecialistReport, SpecialistReport]:
    """``tid``'s answer read by its branch's parser and by the generic parser (the round-7 reading)."""
    it = SPEC[tid]
    kw = dict(request_id=f"req-{tid}", task_id=tid, report_id=f"rep-{tid}-0", subject=it["subject"], task_type=it.get("task_type", "short_answer"),
              supplied_texts=supplied(tid), agent_id=it["agent_id"])
    branch, _ = default_registry().for_subject(it["subject"])
    stem = branch.parser().parse_response(it["response_text"], request_text=it["question"], **kw)
    return stem, GenericTextParser(it["agent_id"]).parse_response(it["response_text"], **kw)


def test_every_stem_subject_of_round_7_is_read_by_a_stem_branch():
    assert STEM_TASKS == ["bi-t13", "ch-t13", "cs-t13", "ess-t13", "maa-p7b", "maa-t13", "mai-t13", "ph-p7b", "ph-t13"]


@pytest.mark.parametrize("tid", STEM_TASKS)
def test_a_stem_answer_yields_the_round7_claims_under_the_branch_letter(tid):
    stem, generic = reports(tid)
    letter = STEM_BRANCHES[default_registry().for_subject(SPEC[tid]["subject"])[0].key]
    assert all(c.claim_id[0] == letter and c.claim_id[1:2].isdigit() for c in stem.claims), [c.claim_id for c in stem.claims]
    assert len(stem.claims) == len(generic.claims), (len(stem.claims), len(generic.claims))
    to_stem = {g.claim_id: s.claim_id for s, g in zip(stem.claims, generic.claims)}
    for s, g in zip(stem.claims, generic.claims):
        assert (s.claim_text, s.claim_role, s.proposed_claim_kind, s.materiality) == (g.claim_text, g.claim_role, g.proposed_claim_kind, g.materiality), (s.claim_id, g.claim_id)
        assert [(r.document_id, r.excerpt) for r in s.source_refs] == [(r.document_id, r.excerpt) for r in g.source_refs], s.claim_id
        assert s.supporting_claim_ids == [to_stem[x] for x in g.supporting_claim_ids], s.claim_id
    assert not CorePack._support_cycles(stem)


@pytest.mark.parametrize("tid", STEM_TASKS)
def test_a_stem_request_has_the_round7_items(tid):
    it = SPEC[tid]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id=f"p-{tid}", request_id=f"q-{tid}", task_id=tid, subject=it["subject"], task_type=it.get("task_type", "short_answer"),
                           selected_agent_ids=[it["agent_id"]]))
    _, req, _ = hub.dispatch(tid, it["agent_id"], it["question"])
    assert [(i.text, i.kind, i.command_term) for i in req.items] == [(i.text, i.kind, i.command_term) for i in extract_items(it["question"])]


@pytest.mark.parametrize("rubric", ["Show your working with units.", "Show full working.", "Show all working.", "Show your working."])
def test_the_rubric_asking_for_working_is_no_item_under_the_stem_imperatives(rubric):
    request = f"A car accelerates from rest. (a) Find its speed after 2.0 s. [2] (b) Show that it travels 4.0 m. [2] {rubric}"
    items = [i.text for i in extract_items(request, extra_imperatives=STEM_IMPERATIVES)]
    assert items == ["(a) Find its speed after 2.0 s. [2]", "(b) Show that it travels 4.0 m. [2]"] == [i.text for i in extract_items(request)]
    # an instruction to show something else is still an item under the STEM imperatives
    assert [i.text for i in extract_items("Show the forces on the block.", extra_imperatives=STEM_IMPERATIVES)] == ["Show the forces on the block."]
