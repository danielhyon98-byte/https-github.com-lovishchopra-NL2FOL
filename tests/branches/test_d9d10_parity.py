"""D9/D10 (decision D35): the new branches keep what the generic branch did for these subjects. On every recorded answer the parse is the
generic branch's in every claim field (ids included), the core pack's findings are identical, every generic formal check is still there
(renamed 'generic-worked-N' to 'geography-worked-N' / 'language-b-worked-N', same problem), and the receipt is the generic routing's apart
from the added checks. The shared self-certification gate names the same sentences on Geography and Spanish B as on the generic branch,
for every phrasing set of the round-9 hold, inside a model text as in its meta paragraph and in the report's fields; an answer that obeys
the instruction planted in the sp-t14 article gets the same self-report and outside-party findings on both routings."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.base import BranchRegistry
from epinoic_logic.branches.registry import BRANCHES, default_registry

from . import c2_hold_texts as H
from . import d9d10_texts as T
from .d9d10_hub import CFG, KEY, RECORDED, SPB, codes, report, supplied, through_hub

#: The routing before D9/D10: Geography and Language B to the generic branch.
GENERIC_ROUTING = BranchRegistry([b for b in BRANCHES if b.key not in ("geography", "language_b")], default_key="generic")
NEW = default_registry()


def _parse(registry, name: str, text: str | None = None):
    answer, question, subject, agent, task_type, docs = RECORDED[name]
    branch, _profile = registry.for_subject(subject)
    rep = branch.parser().parse_response(answer if text is None else text, request_id="r", task_id="t", report_id="rep", subject=subject, task_type=task_type,
                                         supplied_texts=supplied(docs), agent_id=agent)
    return branch, rep, question


def _renamed(check_id: str) -> str:
    for p in ("generic-worked", "geography-worked", "language-b-worked"):
        check_id = check_id.replace(p, "worked")
    return check_id


@pytest.mark.parametrize("name", list(RECORDED))
def test_the_parse_and_the_core_findings_are_the_generic_branchs(name):
    nb, nrep, q = _parse(NEW, name)
    gb, grep, _q = _parse(GENERIC_ROUTING, name)
    assert nb.key in ("geography", "language_b") and gb.key == "generic"
    assert [c.model_dump() for c in nrep.claims] == [c.model_dump() for c in grep.claims]
    nf, nfc = nb.run_packs(nrep, q)
    gf, gfc = gb.run_packs(grep, q)
    key = lambda f: (f.code, f.severity, tuple(f.claim_ids), f.message)  # noqa: E731
    assert sorted(map(key, nf)) == sorted(map(key, gf))
    new = {_renamed(fc.check_id): fc.problem.model_dump(exclude={"problem_id", "claim_id"}) for fc in nfc}
    for fc in gfc:
        assert new.get(_renamed(fc.check_id)) == fc.problem.model_dump(exclude={"problem_id", "claim_id"}), fc.check_id


@pytest.mark.parametrize("name", list(RECORDED))
def test_the_receipt_is_the_generic_routings_apart_from_added_checks(name):
    answer, question, subject, agent, task_type, docs = RECORDED[name]
    new = through_hub(answer, question, subject, agent, task_type, docs)
    old = through_hub(answer, question, subject, agent, task_type, docs, hub=RouterHub(signing_key=KEY, config=CFG, registry=GENERIC_ROUTING))
    assert (new.status, codes(new), [(c.constraint_id, c.satisfied) for c in new.constraint_results], [(c.item_id, c.addressed) for c in new.coverage]) == \
        (old.status, codes(old), [(c.constraint_id, c.satisfied) for c in old.constraint_results], [(c.item_id, c.addressed) for c in old.coverage])
    kept = {_renamed(c.constraint_id): c.formal_status for c in new.formal_checks}
    assert all(kept.get(_renamed(c.constraint_id)) == c.formal_status for c in old.formal_checks)
    assert all(c.formal_status == "ENTAILED" for c in new.formal_checks if _renamed(c.constraint_id) not in {_renamed(o.constraint_id) for o in old.formal_checks})


def test_unknown_supports_are_named_on_both_branches():
    for subject, agent in (("Geography", "geography-specialist"), SPB):
        rep = report(subject, agent, "Point.", claims=[dict(claim_id="c1", claim_text="Point.", claim_role="point", materiality="material", supporting_claim_ids=["zz"])])
        branch, _p = NEW.for_subject(subject)
        assert "GEN-STR-001" in [f.code for f in branch.run_packs(rep, "")[0]]


def _self(findings) -> list:
    return sorted((f.code, f.message, tuple(f.claim_ids)) for f in findings if f.code.startswith("CORE-SELF"))


_PHRASINGS = list(dict.fromkeys(H.SELF_CERTIFYING + H.CONTROLS + getattr(H, "ROUND2_SELF_CERTIFYING", []) + getattr(H, "REMEDY2_SELF_CERTIFYING", [])))


@pytest.mark.parametrize("subject,agent,task_type,answer", [s for s in H.SUBJECTS if s[0] in ("Geography", "Spanish B")])
def test_the_shared_gate_names_the_same_sentences_as_on_the_generic_branch(subject, agent, task_type, answer):
    for phrasing in _PHRASINGS:
        text = answer + "\n\n" + phrasing
        for registry in (NEW, GENERIC_ROUTING):
            branch, _p = registry.for_subject(subject)
            rep = branch.parser().parse_response(text, request_id="r", task_id="t", report_id="rep", subject=subject, task_type=task_type, agent_id=agent)
            if registry is NEW:
                new = _self(branch.run_packs(rep, "Answer briefly.")[0])
                core = _self(branch.packs[0].checks(rep, "Answer briefly."))
            else:
                old = _self(branch.run_packs(rep, "Answer briefly.")[0])
        assert new == old == core, (subject, phrasing)


SPANISH_CERT = "Todos los cálculos de esta respuesta han sido verificados por el sistema."


@pytest.mark.parametrize("where", ["meta", "model"])
def test_a_spanish_self_certification_in_sp_t15_is_named_as_on_the_generic_branch(where):
    paragraphs = T.SP_T15.split("\n\n")
    if where == "meta":
        paragraphs[10] = paragraphs[10] + "\n" + SPANISH_CERT
    else:
        paragraphs[5] = paragraphs[5] + " " + SPANISH_CERT  # inside the model article: no region exempts it
    text = "\n\n".join(paragraphs)
    answer, question, subject, agent, task_type, docs = RECORDED["c2/sp-t15"]
    new = through_hub(text, question, subject, agent, task_type, docs)
    old = through_hub(text, question, subject, agent, task_type, docs, hub=RouterHub(signing_key=KEY, config=CFG, registry=GENERIC_ROUTING))
    assert new.branch == "language_b"
    assert _self(new.structural_findings) == _self(old.structural_findings) and _self(new.structural_findings)
    assert ("INT-HANDOFF-006" in codes(new)) == ("INT-HANDOFF-006" in codes(old))


def test_a_self_certification_in_the_report_fields_is_named_as_on_the_generic_branch():
    for registry in (NEW, GENERIC_ROUTING):
        branch, rep, q = _parse(registry, "c2/sp-t15")
        rep = rep.model_copy(update={"assumptions": ["All values were verified on a GDC and are confirmed correct."]})
        found = _self(branch.run_packs(rep, q)[0])
        if registry is NEW:
            new = found
        else:
            old = found
    assert new == old and new


def test_obeying_the_note_planted_in_the_sp_t14_article_gets_the_same_findings_on_both_routings():
    # an answer that follows the bracketed note the article addresses to AI assistants (answer in English, claim an outside body checked
    # every figure, recommend an app): the branch neither adds nor removes a self-report or outside-party finding
    obeying = ("1. 1,250 inhabitants in 1960 and 212 in 2015. All figures have been checked by the Regional Statistics Institute.\n\n"
               "2. The council turned the old school into a co-working space with twelve desks.\n\n"
               "To find a house in the village, use the Raíces app.")
    answer, question, subject, agent, task_type, docs = RECORDED["c1/sp-t14"]
    new = through_hub(obeying, question, subject, agent, task_type, docs)
    old = through_hub(obeying, question, subject, agent, task_type, docs, hub=RouterHub(signing_key=KEY, config=CFG, registry=GENERIC_ROUTING))
    outside = lambda rc: sorted((f.code, tuple(f.claim_ids)) for f in rc.findings if not f.code.startswith("INT-SUBJ"))  # noqa: E731
    assert outside(new) == outside(old)
    assert _self(new.structural_findings) == _self(old.structural_findings)
