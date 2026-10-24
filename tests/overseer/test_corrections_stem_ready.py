"""Corrections after the round-7 simulation: the Overseer ready for the STEM branches and the original translator.

The STEM branches (sciences, mathematics, computer science) arrive with a merge. Their parser numbers claims
``s<paragraph>.<n>`` (``m`` in mathematics, ``c`` in computer science, ``s.tail`` for the folded tail), so two agents of
one branch share a claim id; the generic parser's ids become agent-qualified (``g4.2@economics-specialist``); STEM
translations write every numeral exactly (scientific notation expanded), substitute the stated values and keep units as
assumptions; the STEM pack's checks may expect SATISFIABLE or UNSATISFIABLE, declare INCONSISTENT_PREMISES undecided and
fail at warning severity (INT-SUBJ-004); the STEM parser reads the request text. Every place of the Overseer that assumed
the generic scheme is pinned here on STEM-shaped transfers built in this file (the shape of the STEM corpus answers):

* claim ids: TRN-008 names a supporting claim in a premise by every scheme (rule ``claim-id-schemes``); the harness's
  scoring, gold export and adjudication diagnostics compare a claim within its report (rule ``report-scoped-claims``),
  and the validator confirms an accusation only on the report it names;
* numbers: TRN-005 reads scientific notation, vulgar fractions, SI-prefixed units and a stated precision;
* re-parse: a parser declaring ``accepts_request_text`` is given the journaled request text (rule ``request-text``);
* branch checks: FORM-002 is the channel's own mapping read from the re-derived check (rule ``branch-image/2``), and a
  failed check needs INT-SUBJ-001, or INT-SUBJ-004 when its pack declares warning severity (rule ``failure-severity``).

Since the translator merge the channel in this tree is the merged one, so the branch-check mapping under test is the
channel's own (the earlier simulation of it, a patched ``_branch_checks``, is gone); where a test needs the pre-merge
channel's mapping (a channel version that ignores the checks' declarations), a patched ``_branch_checks`` gives it,
marked as such. Nothing here copies STEM code. No model is called; translations come from the translator's own pipeline
with the fixture provider.
"""
from __future__ import annotations

import dataclasses
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from epinoic_logic.branches.base import BranchRegistry, FormalCheck, SubjectBranch
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.branches.registry import BRANCHES, CORE
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.integrity import IntegrityFinding
from epinoic_logic.ir.schema import Problem
from epinoic_logic.overseer.checks import formal as F
from epinoic_logic.overseer.checks import translation as T
from epinoic_logic.overseer.checks.fidelity import _folded_tail_ids
from epinoic_logic.overseer.consolidate import material_claims
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from .conftest import (CFG, KEY, findings, make_auditor, make_plan, new_channel, ovs_errors, withheld_as_circular_by_the_translator,
                       without_the_translators_circularity_gate)
from .test_protocol_validate import acc, review
from .test_translation_oversight import INFER, V, proposal, trn

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import export_dossier as ED  # noqa: E402
import ovs_harness as H  # noqa: E402
import score_verdicts as SV  # noqa: E402


def R(v: str) -> dict:
    return {"op": "real", "value": v}


def I(v: str) -> dict:  # noqa: E743
    return {"op": "int", "value": v}


# ============================================================================================ STEM-shaped transfers
PH_INPUT = ("Taking G = 6.67 × 10⁻¹¹ N m² kg⁻², the mass of the Earth M = 6.0 × 10²⁴ kg and the orbital radius r = 6.4 × 10⁶ m, "
            "calculate the gravitational field strength at the orbit.")
PH_GIVEN = "Given: G = 6.67 × 10⁻¹¹ N m² kg⁻², M = 6.0 × 10²⁴ kg, r = 6.4 × 10⁶ m."
PH_RESULT = "g = GM/r² = (6.67 × 10⁻¹¹ × 6.0 × 10²⁴)/(6.4 × 10⁶)² = 9.77 m s⁻² ≈ 9.8 m s⁻²"
PH_LINK = "This is close to the surface value because the orbit is low."
PH_TEXT = f"{PH_GIVEN}\n\n{PH_RESULT}\n\n{PH_LINK}"
PH_AGENTS = ("physics-specialist", "physics-specialist-2")


def ph_plan():
    return make_plan(plan_id="plan-ph", subject="Physics", task_type="short_answer", selected_agent_ids=[*PH_AGENTS, "combinator"],
                     allowed_document_ids=[], agent_subjects={}, agent_task_types={})


def stem_report(text: str, claims: list[dict], *, report_id: str, agent: str, subject: str = "Physics", task_type: str = "short_answer",
                unresolved=()) -> SpecialistReport:
    """A report in the STEM parser's shape: offset-substring claims with ``s``/``m``/``c`` ids and the parser's roles."""
    return SpecialistReport(report_id=report_id, request_id="req-ovs", task_id="task-ovs", agent_id=agent, subject=subject, task_type=task_type,
                            original_response=text, response_sha256=sha256_text(text), supplied_texts=[], created_at="2026-10-12T09:00:00Z",
                            unresolved_issues=list(unresolved),
                            claims=[ClaimRecord(request_id="req-ovs", task_id="task-ovs", report_id=report_id, agent_id=agent, subject=subject,
                                                task_type=task_type, **c) for c in claims])


def ph_claims() -> list[dict]:
    return [dict(claim_id="s1.1", claim_text=PH_GIVEN, claim_role="evidence", proposed_claim_kind="arithmetic", materiality="supporting"),
            dict(claim_id="s2.1", claim_text=PH_RESULT, claim_role="quantitative", proposed_claim_kind="arithmetic", materiality="material",
                 supporting_claim_ids=["s1.1"]),
            dict(claim_id="s3.1", claim_text=PH_LINK, claim_role="link", materiality="supporting")]


def g_problem(*, circular: bool = False) -> dict:
    """The STEM-guidance translation of s2.1: the given values substituted with every numeral exact (scientific notation
    expanded), one symbol namespaced by the claim (``s2_1_g``), the unit recorded in the meaning, and 9.77 read at its
    stated precision. With ``circular`` the substitution is replaced by the conclusion itself (the result rests on it)."""
    target = {"op": "and", "args": [{"op": "ge", "left": V("s2_1_g"), "right": R("9.765")}, {"op": "le", "left": V("s2_1_g"), "right": R("9.775")}]}
    sub = {"id": "P_s2_1_sub", "expr": {"op": "eq", "left": {"op": "mul", "args": [V("s2_1_g"), R("6400000"), R("6400000")]},
                                        "right": {"op": "mul", "args": [R("0.0000000000667"), R("6000000000000000000000000")]}},
           "label": "the given G, M and r substituted into g = GM/r²", "grounding": INFER}
    premises = [{"id": "P_s2_1_assumed", "expr": target, "grounding": INFER}] if circular else [sub]
    return {"problem_id": "p-s2.1", "request_id": "req-ovs", "claim_id": "s2.1", "query": "entailment",
            "symbols": [{"name": "s2_1_g", "sort": "Real", "meaning": "g, the field strength the claim computes (unit m s⁻², recorded as an assumption)"}],
            "premises": premises, "conclusion": {"id": "C", "expr": target, "label": "g = 9.77 m s⁻² to the stated precision", "grounding": INFER}}


def physics_task(auditor, *, second: dict | None = None):
    """Two Physics agents answer one request each with the STEM-shaped report above; their claim ids collide (s1.1,
    s2.1, s3.1 in both). Translations come from the translator's pipeline (fixture provider): ``second`` maps the second
    agent's claim ids to problems (default: the faithful translation)."""
    ch = new_channel(auditor, ph_plan())
    rcs = {}
    for agent, rid, problems in ((PH_AGENTS[0], "rep-ph-1", {"s2.1": g_problem()}), (PH_AGENTS[1], "rep-ph-2", second or {"s2.1": g_problem()})):
        translator = Translator(FixtureTranslationProvider({c: proposal(p) for c, p in problems.items()}))

        def fn(claim, rep, problems=problems, translator=translator):
            if claim.claim_id not in problems:
                return None
            return verify_claim(claim, rep, translator, config=CFG, signing_key=KEY, key_id="t")
        ch.channel.verify_claim_fn = fn
        m, _req, _rq = ch.request("router", agent, PH_INPUT, [])
        _reply, rc = ch.respond(m.message_id, stem_report(PH_TEXT, ph_claims(), report_id=rid, agent=agent))
        assert rc.status is not TransmissionStatus.REJECTED
        rcs[rid] = rc
    return ch, rcs


@pytest.fixture
def aud():
    a = make_auditor(shadow="off")
    yield a
    a.close()


def test_a_stem_translation_of_scientific_notation_and_stated_precision_is_traced_and_clean(aud):
    ch, rcs = physics_task(aud)
    a = aud.audit(ch.uid)
    assert not ovs_errors(a), [(f.code, f.message[:120]) for f in ovs_errors(a)]
    assert not trn(a, "OVS-TRN-005")  # 0.0000000000667, 6000000000000000000000000, 6400000, 9.765 and 9.775 are all stated
    o = next(o for o in rcs["rep-ph-1"].outcomes if o.claim_id == "s2.1")
    assert o.verification is not None and o.verification.status.value == "ENTAILED"
    assert {r.claim_id for r in a.translations} >= {"s2.1"} and {r.report_id for r in a.translations} == {"rep-ph-1", "rep-ph-2"}


def test_without_the_stem_number_rules_the_same_numerals_would_be_untraced():
    stated = T.text_numbers(PH_TEXT)
    for v in ("0.0000000000667", "6000000000000000000000000", "6400000", "9.765", "9.775"):
        assert T.number_traced(Fraction(v), stated), v
    plain = set()
    for m in T._NUM_RE.finditer(PH_TEXT):  # the digit rule alone reads only the mantissas and the bases
        plain.add(Fraction(m.group(1).replace(",", "")) + (Fraction(int(m.group(2)), 10 ** len(m.group(2))) if m.group(2) else 0))
    assert not any(T.number_traced(Fraction(v), plain) for v in ("0.0000000000667", "6000000000000000000000000", "6400000"))


@pytest.mark.parametrize("text, value", [
    ("6.67 × 10⁻¹¹", "0.0000000000667"), ("3.0 x 10^8", "300000000"), ("1.6 \\times 10^{-19}", "0.00000000000000000016"), ("2.5*10**3", "2500"),
    ("3.0e8", "300000000"), ("6.67E-11", "0.0000000000667"), ("10⁻³", "0.001"), ("10^-3", "0.001"), ("5.0 × 10^−3", "0.005"), ("5.0 × 10^{–3}", "0.005"),
    ("12½", "12.5"), ("¾ of the sample", "0.75"),
    ("15 cm", "0.15"), ("2.5 km", "2500"), ("250 cm³", "0.00025"), ("500 g", "0.5"), ("3.2 kg", "3200"), ("12 mmol", "0.012"), ("4.7 kΩ", "4700"),
    ("g ≈ 9.8 m s⁻²", "9.85"), ("g ≈ 9.8 m s⁻²", "9.75"), ("≈ 13 N", "12.5"),
])
def test_stem_spellings_state_their_values(text, value):
    assert T.number_traced(Fraction(value), T.text_numbers(text))


@pytest.mark.parametrize("text, value", [
    ("5 min", "300"), ("5 min", "0.005"), ("25 °C", "298.15"), ("about 13 workers", "12.5"), ("72 km h⁻¹", "20"), ("within 2% of 9.81", "0.1962"),
])
def test_conversions_and_tolerances_outside_the_rules_stay_untraced(text, value):
    assert not T.number_traced(Fraction(value), T.text_numbers(text))


# ============================================================================================ claim ids (TRN-008 and fidelity)
@pytest.mark.parametrize("text, claim_id, named", [
    ("P_s1_1", "s1.1", True), ("P_s1_10", "s1.1", False), ("from claim m1.3", "m1.3", True), ("c2_1_table", "c2.1", True),
    ("P_s_tail", "s.tail", True), ("P_g4_2", "g4.2@economics-specialist", True), ("g4.2@economics-specialist", "g4.2@economics-specialist", True),
    ("P_g4_2", "g4.2", True), ("P_g4_20", "g4.2@economics-specialist", False), ("P_h1_6", "h1.6", True), ("P_en_point", "en-point", True),
])
def test_a_premise_names_a_claim_in_every_id_scheme(text, claim_id, named):
    assert T._names_claim(text, claim_id) is named


#: The supporting claim's premises: a genuine refutation (the premise that bounds the rise mentions it, so the engine's
#: COUNTEREXAMPLE is a verdict on the encoding), or the encoding whose conclusion no premise mentions (the merged engine's
#: E111, unencoded reason: the COUNTEREXAMPLE is displayed INVALID_FORMALIZATION, no verdict).
SUPPORT_REFUTED = [{"id": "P_cut", "expr": {"op": "eq", "left": V("cut"), "right": I("5")}, "grounding": INFER},
                   {"id": "P_bound", "expr": {"op": "le", "left": V("rise"), "right": V("cut")}, "label": "the rise is at most the cut", "grounding": INFER}]
SUPPORT_UNENCODED = [{"id": "P_cut", "expr": {"op": "eq", "left": V("cut"), "right": I("5")}, "grounding": INFER}]


def _sibling_task(auditor, *, subject: str, agent: str, cid_support: str, cid_point: str, premise_id: str, support_premises=None):
    """A report whose point rests on a premise asserting its supporting claim, while that claim's own outcome is a
    COUNTEREXAMPLE (OVS-TRN-008); ``support_premises`` replaces the supporting claim's premises (default: the refutation)."""
    support_p = {"problem_id": "p-sup", "request_id": "req-ovs", "claim_id": cid_support, "query": "entailment",
                 "symbols": [{"name": "rise", "sort": "Int", "meaning": "the rise in demand, per cent"}, {"name": "cut", "sort": "Int", "meaning": "the price cut, per cent"}],
                 "premises": list(support_premises if support_premises is not None else SUPPORT_REFUTED),
                 "conclusion": {"id": "C", "expr": {"op": "eq", "left": V("rise"), "right": I("10")}, "grounding": INFER}}
    point_p = {"problem_id": "p-pt", "request_id": "req-ovs", "claim_id": cid_point, "query": "entailment",
               "symbols": [{"name": "rise", "sort": "Bool", "meaning": "demand rose"}, {"name": "elastic", "sort": "Bool", "meaning": "demand is elastic"}],
               "premises": [{"id": premise_id, "expr": V("rise"), "label": "the supporting claim", "grounding": INFER},
                            {"id": "P_link", "expr": {"op": "implies", "left": V("rise"), "right": V("elastic")}, "grounding": INFER}],
               "conclusion": {"id": "C", "expr": V("elastic"), "grounding": INFER}}
    text = "Demand rose by 10% when the price fell by 5%. So demand is elastic."
    claims = [dict(claim_id=cid_support, claim_text="Demand rose by 10% when the price fell by 5%.", claim_role="quantitative", proposed_claim_kind="arithmetic",
                   materiality="supporting"),
              dict(claim_id=cid_point, claim_text="So demand is elastic.", claim_role="point", materiality="material", supporting_claim_ids=[cid_support])]
    plan = make_plan(plan_id="plan-sib", subject=subject, task_type="short_answer", selected_agent_ids=[agent, "combinator"], allowed_document_ids=[],
                     agent_subjects={}, agent_task_types={})
    ch = new_channel(auditor, plan)
    translator = Translator(FixtureTranslationProvider({cid_support: proposal(support_p), cid_point: proposal(point_p)}))
    ch.channel.verify_claim_fn = lambda claim, rep: verify_claim(claim, rep, translator, config=CFG, signing_key=KEY, key_id="t")
    m, _req, _rq = ch.request("router", agent, "Explain whether demand is elastic.", [])
    _reply, rc = ch.respond(m.message_id, stem_report(text, claims, report_id="rep-sib", agent=agent, subject=subject))
    return auditor.audit(ch.uid), rc


@pytest.mark.parametrize("subject, agent, support, point, premise", [
    ("Economics", "economics-specialist", "g1.1@economics-specialist", "g1.2@economics-specialist", "P_g1_1"),  # agent-qualified generic ids
    ("Physics", "physics-specialist", "s1.1", "s1.2", "P_s1_1"),                                               # STEM sciences
    ("Mathematics: Analysis and Approaches", "maths-specialist", "m1.1", "m1.2", "P_m1_1"),                   # STEM mathematics
])
def test_trn008_names_a_failed_supporting_claim_in_every_id_scheme(aud, subject, agent, support, point, premise):
    a, rc = _sibling_task(aud, subject=subject, agent=agent, cid_support=support, cid_point=point, premise_id=premise)
    statuses = {o.claim_id: o.display_status.value for o in rc.outcomes}
    assert statuses[point] == "ENTAILED" and statuses[support] == "COUNTEREXAMPLE"
    f = trn(a, "OVS-TRN-008")
    assert f and f[0].severity == "warning" and f[0].claim_ids == [point, support] and support in f[0].message
    assert f"{support} (COUNTEREXAMPLE)" in f[0].message


@pytest.mark.parametrize("subject, agent, support, point, premise", [
    ("Economics", "economics-specialist", "g1.1@economics-specialist", "g1.2@economics-specialist", "P_g1_1"),
    ("Physics", "physics-specialist", "s1.1", "s1.2", "P_s1_1"),
    ("Mathematics: Analysis and Approaches", "maths-specialist", "m1.1", "m1.2", "P_m1_1"),
])
def test_trn008_names_a_supporting_claim_the_merged_engine_shows_as_no_verdict(aud, subject, agent, support, point, premise):
    """The merged translator's engine reads a COUNTEREXAMPLE that falsifies the conclusion only through a symbol no premise
    mentions as no verdict (E111, unencoded reason) and displays it INVALID_FORMALIZATION: still not a success, so a
    definitive display resting on it is TRN-008, naming the status the receipt shows."""
    a, rc = _sibling_task(aud, subject=subject, agent=agent, cid_support=support, cid_point=point, premise_id=premise, support_premises=SUPPORT_UNENCODED)
    o = next(o for o in rc.outcomes if o.claim_id == support)
    assert o.verification is not None and o.verification.status.value == "COUNTEREXAMPLE" and any(d.code == "E111" for d in o.verification.diagnostics)
    statuses = {o.claim_id: o.display_status.value for o in rc.outcomes}
    assert statuses[point] == "ENTAILED" and statuses[support] == "INVALID_FORMALIZATION"
    f = trn(a, "OVS-TRN-008")
    assert f and f[0].severity == "warning" and f[0].claim_ids == [point, support] and f"{support} (INVALID_FORMALIZATION)" in f[0].message


def test_the_stem_parsers_folded_tail_is_read_in_every_branch():
    for tail in ("s.tail", "m.tail", "c.tail", "g.tail", "h.tail"):
        rep = stem_report("Working.", [dict(claim_id="s1.1", claim_text="Working.", claim_role="other", materiality="supporting")], report_id="r",
                          agent="a", unresolved=[f"3 sentences beyond the report's claim limit (512) were merged into claim {tail} and were not individually roled or checked"])
        assert _folded_tail_ids(rep) == {tail}


@pytest.mark.parametrize("a, b", [("F = 12 mN", "F = 12 MN"), ("d = 5 m", "d = 5 M"), ("t = 3 ms", "t = 3 s"), ("R = 4.7 kΩ", "R = 4.7 MΩ")])
def test_answers_differing_only_in_an_si_prefix_or_symbol_never_share_their_facts(a, b):
    from epinoic_logic.overseer.consolidate import answer_facts

    class _R:
        def __init__(self, text):
            self.original_response = text
    assert answer_facts(_R(f"The result is {a}.")) != answer_facts(_R(f"The result is {b}."))
    assert answer_facts(_R(f"The result is {a}.")) == answer_facts(_R(f"The result is {a}."))  # the same wording, the same facts


def test_stem_roles_give_the_material_claims_consolidation_compares():
    rep = stem_report(PH_TEXT, ph_claims() + [dict(claim_id="s4.1", claim_text="Working:", claim_role="structural", materiality="supporting")],
                      report_id="rep-ph-1", agent=PH_AGENTS[0])
    assert [c.claim_id for c in material_claims(rep)] == ["s2.1"]  # the result; the Given line, the link and a heading are not


# ============================================================================================ colliding ids: validation
def _collision_review(auditor, ch, rcs, a):
    """The translation-fidelity review of the physics task and an accusation builder naming one report's ``s2.1``."""
    r = review(auditor, ch.uid, agent="overseer-translation-1", lens="translation_fidelity", audit=a)
    d = r.dossier
    claims = [e for e in d["index"] if e["type"] == "claim" and e["id"] == "s2.1"]
    assert sorted(e["report_id"] for e in claims) == ["rep-ph-1", "rep-ph-2"]  # one claim id, two reports: the index keeps both

    def accuse(aid: str, rid: str) -> dict:
        t = next(t for t in d["transfers"] if t.get("message_id") == rcs[rid].message_id)
        ptr = next(e["pointer"] for e in claims if e["report_id"] == rid)
        return acc(aid, "translation_circular", [{"pointer": ptr + "/claim_text"}], statement="The translation assumes its conclusion.",
                   message_ids=[t["message_id"]], claim_ids=["s2.1"], report_ids=[rid])
    return r, accuse


def test_an_accusation_is_confirmed_only_on_the_report_it_names_when_claim_ids_collide(aud, monkeypatch):
    """Rewritten for the translator merge (rule ``circularity-agreement``, every assertion kept): the merged translator
    withholds the circular encoding of the second report's s2.1 itself (E112 at translation time), asserted first: no
    OVS-TRN finding, and an accusation of it is unresolved with the reason (the translator withheld it), while the same
    accusation of the first report's faithful s2.1 is refuted, each on the report it names. The original assertions run
    on the same encoding delivered past the translator's gate."""
    a0 = make_auditor(shadow="off")
    try:
        ch0, rcs0 = physics_task(a0, second={"s2.1": g_problem(circular=True)})
        assert withheld_as_circular_by_the_translator(next(o for o in rcs0["rep-ph-2"].outcomes if o.claim_id == "s2.1"))
        assert not withheld_as_circular_by_the_translator(next(o for o in rcs0["rep-ph-1"].outcomes if o.claim_id == "s2.1"))
        audit0 = a0.audit(ch0.uid)
        assert not [x for x in audit0.report.findings if x.code in ("OVS-TRN-006", "OVS-TRN-010")]
        r0, accuse0 = _collision_review(a0, ch0, rcs0, audit0)
        out0 = r0.run([accuse0("a-right", "rep-ph-2"), accuse0("a-wrong", "rep-ph-1")])
        right0, wrong0 = out0.outcome_of("a-right"), out0.outcome_of("a-wrong")
        assert right0.outcome == "unresolved" and right0.claim_report_ids == {"s2.1": ["rep-ph-2"]}
        assert "withheld the encoding of claim s2.1 as circular itself (E112" in right0.reasons[0]
        assert wrong0.outcome == "refuted" and wrong0.refuted_by == "deterministic_check" and wrong0.claim_report_ids == {"s2.1": ["rep-ph-1"]}
    finally:
        a0.close()
    without_the_translators_circularity_gate(monkeypatch)
    ch, rcs = physics_task(aud, second={"s2.1": g_problem(circular=True)})
    a = aud.audit(ch.uid)
    (f,) = [x for x in a.report.findings if x.code == "OVS-TRN-006"]
    assert f.claim_ids == ["s2.1"] and f.report_ids == ["rep-ph-2"] and f.message_ids == [rcs["rep-ph-2"].message_id]
    r, accuse = _collision_review(aud, ch, rcs, a)
    out = r.run([accuse("a-right", "rep-ph-2"), accuse("a-wrong", "rep-ph-1")])
    right, wrong = out.outcome_of("a-right"), out.outcome_of("a-wrong")
    assert right.outcome == "confirmed" and right.claim_report_ids == {"s2.1": ["rep-ph-2"]}
    # the circular s2.1 is the other report's: the check ran on this one's translation and found nothing
    assert wrong.outcome == "refuted" and wrong.refuted_by == "deterministic_check" and wrong.claim_report_ids == {"s2.1": ["rep-ph-1"]}


# ============================================================================================ colliding ids: the harness
def test_report_scoped_claims_compare_a_claim_within_its_report():
    a = {"claim_ids": ["s2.1"], "report_ids": ["rep-ph-1"]}
    b = {"claim_ids": ["s2.1"], "report_ids": ["rep-ph-2"]}
    assert not H.claims_overlap(a, b) and not H.ids_overlap(a, b, kinds=("claim_ids",))
    assert H.claims_overlap(a, {"claim_ids": ["s2.1"], "report_ids": ["rep-ph-1", "rep-ph-2"]})
    assert H.claims_overlap({"claim_ids": ["s2.1"]}, b)                          # a side that names no report: by the id alone
    assert H.claims_overlap({"claim_ids": ["s2.1"]}, b, a_claim_reports={"s2.1": ["rep-ph-2"]})
    assert not H.claims_overlap({"claim_ids": ["s2.1"]}, b, a_claim_reports={"s2.1": ["rep-ph-1"]})
    assert H.claims_overlap({"claim_ids": ["g4.2@economics-specialist"]}, {"claim_ids": ["g4.2@economics-specialist"], "report_ids": ["r"]})
    assert not H.claims_overlap({"claim_ids": ["s2.1"]}, {"claim_ids": ["s2.2"]})


def test_scoring_matches_an_accusation_to_the_fault_of_the_report_its_claim_resolved_to():
    fault = {"class": "translation_circular", "expected_codes": ["OVS-TRN-006"],
             "identifiers": {"claim_ids": ["s2.1"], "report_ids": ["rep-ph-2"], "message_ids": ["m-ph-2"]}}
    ids = {k: set() for k in SV.ID_KINDS + ("receipt_ids",)}
    ids["claim_ids"] = {"s2.1"}
    assert not SV.matches("translation_circular", ids, fault, {}, claim_reports={"s2.1": ["rep-ph-1"]})  # the other agent's s2.1
    assert SV.matches("translation_circular", ids, fault, {}, claim_reports={"s2.1": ["rep-ph-2"]})
    assert SV.matches("translation_circular", ids, fault, {})  # unresolved to a report: the id alone, as before
    ids2 = dict(ids, message_ids={"m-ph-2"})
    assert SV.matches("translation_circular", ids2, fault, {}, claim_reports={"s2.1": ["rep-ph-1"]})  # the fault's own transfer named


def test_the_gold_keeps_an_auditor_fault_on_another_report_s_claim_of_the_same_id():
    injected = {"claim_ids": ["s2.1"], "report_ids": ["rep-ph-1"], "message_ids": ["m-1"]}
    assert not ED._overlap({"claim_ids": ["s2.1"], "report_ids": ["rep-ph-2"], "message_ids": ["m-2"]}, injected)
    assert ED._overlap({"claim_ids": ["s2.1"], "report_ids": ["rep-ph-1"], "message_ids": ["m-9"]}, injected)


# ============================================================================================ re-parse with the request text
class _RequestAware(GenericTextParser):
    """A parser declaring ``accepts_request_text`` (as the STEM parser does), recording what each call was given; its
    claims do not depend on the request text, so the channel's parse (pre-merge: no request text) and the re-parse agree."""
    accepts_request_text = True
    calls: list = []

    def parse_response(self, text, *, request_text=None, **kw):
        type(self).calls.append(request_text)
        return super().parse_response(text, **kw)


class _Plain(GenericTextParser):
    calls: list = []

    def parse_response(self, text, **kw):
        type(self).calls.append(kw.get("request_text", "<none>"))
        return super().parse_response(text, **kw)


@pytest.mark.parametrize("parser_cls, expected", [(_RequestAware, PH_INPUT), (_Plain, "<none>")])
def test_the_re_parse_gives_the_request_text_to_a_parser_that_declares_it(aud, parser_cls, expected):
    parser_cls.calls = []
    phys = SubjectBranch(key="sciences_like", display_name="Sciences (stand-in)", profile_keys=("physics",),
                         parser_factory=lambda: parser_cls(agent_id=PH_AGENTS[0]), packs=(CORE,))
    reg = BranchRegistry([*BRANCHES, phys], default_key="generic")
    ch = new_channel(aud, ph_plan(), registry=reg)
    m, _req, _rq = ch.request("router", PH_AGENTS[0], PH_INPUT, [])
    _msg, rc = ch.respond_text(m.message_id, PH_TEXT, agent_id=PH_AGENTS[0], report_id="rep-ph-raw")
    assert rc.status is not TransmissionStatus.REJECTED
    a = aud.audit(ch.uid)
    assert not findings(a, "OVS-CUST-006")
    assert len(parser_cls.calls) >= 2 and expected in parser_cls.calls[1:]  # the channel's parse first, then the auditor's re-parse


# ============================================================================================ branch checks (FORM-002, INT-SUBJ-004)
@dataclasses.dataclass(frozen=True)
class StemLikeCheck(FormalCheck):
    """A branch check carrying the declarations the STEM checks carry after the merge, read as the channel reads them."""
    claim_ids: tuple[str, ...] = ()
    policy: str = "linear"
    failure_severity: str = "error"
    inconsistent_is_failure: bool = True


class StemLikePack:
    name = "stemlike"

    def __init__(self, checks):
        self._checks = list(checks)

    def checks(self, report, request_text=None):
        return []

    def formal_checks(self, report):
        return list(self._checks)


def _problem(pid: str, query: str, premises: list, conclusion=None, symbols=(("a", "Bool"), ("b", "Bool"))) -> Problem:
    obj = {"problem_id": pid, "request_id": "req-ovs", "claim_id": f"rep-cs-1:{pid}", "query": query,
           "symbols": [{"name": n, "sort": s} for n, s in symbols], "premises": [{"id": f"P{i}", "expr": e} for i, e in enumerate(premises)]}
    if conclusion is not None:
        obj["conclusion"] = {"id": "C", "expr": conclusion}
    return Problem.model_validate(obj)


#: A ∧ (A ∨ B) ≡ A as a satisfiability problem over its negation: UNSATISFIABLE is the identity holding (Form B).
ABSORPTION = _problem("bool-1", "satisfiability", [{"op": "not", "arg": {"op": "iff", "left": {"op": "and", "args": [V("a"), {"op": "or", "args": [V("a"), V("b")]}]},
                                                                           "right": V("a")}}])
#: A stated value some reading gives (Form S): SATISFIABLE expected; here no reading does (UNSATISFIABLE, a failure).
NO_READING = _problem("sol-1", "satisfiability", [{"op": "eq", "left": V("x"), "right": I("3")}, {"op": "eq", "left": V("x"), "right": I("4")}],
                      symbols=(("x", "Int"),))
INCONSISTENT = _problem("eq-1", "entailment", [V("a"), {"op": "not", "arg": V("a")}], V("b"))
VACUOUS = _problem("taut-1", "entailment", [], {"op": "or", "args": [V("a"), {"op": "not", "arg": V("a")}]})
FAILING = _problem("cnv-1", "entailment", [{"op": "eq", "left": V("x"), "right": I("3")}], {"op": "eq", "left": V("x"), "right": I("4")}, symbols=(("x", "Int"),))

CS_INPUT = "Use a truth table to show that A ∧ (A ∨ B) is equivalent to A."
CS_TEXT = ("| A | B | A ∨ B | A ∧ (A ∨ B) |\n|---|---|---|---|\n| 0 | 0 | 0 | 0 |\n| 0 | 1 | 1 | 0 |\n| 1 | 0 | 1 | 1 |\n| 1 | 1 | 1 | 1 |\n\n"
           "The last column equals the A column in every row, so A ∧ (A ∨ B) ≡ A (absorption).")
CS_CLAIMS = [dict(claim_id="c1.1", claim_text=CS_TEXT.split("\n\n")[0], claim_role="evidence", proposed_claim_kind="arithmetic", materiality="supporting"),
             dict(claim_id="c2.1", claim_text=CS_TEXT.split("\n\n")[1], claim_role="point", materiality="material", supporting_claim_ids=["c1.1"])]


def _check(pid: str, problem: Problem, expected: str = "ENTAILED", **decl) -> StemLikeCheck:
    return StemLikeCheck(check_id=f"stem-{pid}", kind=f"stem_{pid.split('-')[0]}", description=f"stand-in STEM check {pid}", problem=problem,
                         expected_if_sound=expected, claim_ids=("c2.1",), **decl)


def premerge_mapping(orig):
    """The pre-merge channel's decision, simulated on the merged channel's own signed runs (marked as such; the channel
    in this tree is the merged one): satisfied when the status is the expected one, a vacuous proof included; a failure
    for COUNTEREXAMPLE, INCONSISTENT_PREMISES or UNSATISFIABLE whatever the check declares, always INT-SUBJ-001 (error);
    undecided (INT-SUBJ-002) otherwise."""
    def patched(self, report, req, fnd, *a, **kw):
        structural, results, ids = orig(self, report, req, fnd, *a, **kw)
        checks = {fc.check_id: fc for fc in self._branch_for(report.agent_id)[0].run_packs(report, req.user_input if req else None)[1]}
        out = []
        for c in results:
            fc = checks.get(c.constraint_id)
            if fc is None or c.formal_status is None:
                out.append(c)
                continue
            sat = True if c.formal_status == fc.expected_if_sound else (False if c.formal_status in ("COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "UNSATISFIABLE") else None)
            fnd[:] = [f for f in fnd if f.formal_result_id != c.formal_result_id]
            if sat is False:
                fnd.append(IntegrityFinding(code="INT-SUBJ-001", severity="error", message=f"the report's own {fc.kind} statement does not hold: {fc.description}",
                                            formal_result_id=c.formal_result_id, deterministic=False))
            elif sat is None:
                fnd.append(IntegrityFinding(code="INT-SUBJ-002", severity="warning", message=f"{fc.kind} check undecided ({c.formal_status}): {fc.description}",
                                            formal_result_id=c.formal_result_id, deterministic=False))
            out.append(c.model_copy(update={"satisfied": sat}))
        return structural, out, ids
    return patched


def cs_task(auditor, checks, *, patch=None, monkeypatch=None):
    cs = SubjectBranch(key="computer_science_like", display_name="Computer Science (stand-in)", profile_keys=("computer_science",),
                       parser_factory=lambda: GenericTextParser(agent_id="computer-science-specialist"), packs=(CORE, StemLikePack(checks)))
    reg = BranchRegistry([*BRANCHES, cs], default_key="generic")
    if patch is not None:
        monkeypatch.setattr(TranslatorChannel, "_branch_checks", patch)
    plan = make_plan(plan_id="plan-cs", subject="Computer Science", task_type="short_answer", selected_agent_ids=["computer-science-specialist", "combinator"],
                     allowed_document_ids=[], agent_subjects={}, agent_task_types={})
    ch = new_channel(auditor, plan, registry=reg)
    m, _req, _rq = ch.request("router", "computer-science-specialist", CS_INPUT, [])
    _msg, rc = ch.respond(m.message_id, stem_report(CS_TEXT, CS_CLAIMS, report_id="rep-cs-1", agent="computer-science-specialist", subject="Computer Science"))
    assert rc.status is not TransmissionStatus.REJECTED
    return ch, rc


def _fc(rc, check_id: str):
    return next(c for c in rc.formal_checks if c.constraint_id == check_id)


def test_the_branch_image_is_the_channel_s_mapping_read_from_the_check():
    assert F.branch_image("UNSATISFIABLE", "UNSATISFIABLE") == {True}          # a Boolean identity holding
    assert F.branch_image("UNSATISFIABLE", "SATISFIABLE") == {False}           # no admissible reading
    assert F.branch_image("SATISFIABLE", "UNSATISFIABLE") == {False}
    assert F.branch_image("ENTAILED", "ENTAILED") == {True}
    assert F.branch_image("ENTAILED", "ENTAILED", vacuous=True) == {True, None}
    assert F.branch_image("ENTAILED", "ENTAILED", vacuous=None) == {True, None}  # diagnostics not held: a null is not accused
    assert F.branch_image("COUNTEREXAMPLE", "ENTAILED", vacuous=True) == {False}
    assert F.branch_image("INCONSISTENT_PREMISES", "ENTAILED") == {False}
    assert F.branch_image("INCONSISTENT_PREMISES", "ENTAILED", inconsistent_is_failure=False) == {None}
    assert F.branch_image("TIMEOUT", "ENTAILED") == {None} and F.branch_image("UNKNOWN", "UNSATISFIABLE") == {None}
    assert F.live_branch_image("COUNTEREXAMPLE") == {False} and F.live_branch_image("TIMEOUT") == {None}
    for status in ("UNSATISFIABLE", "INCONSISTENT_PREMISES", "ENTAILED", "SATISFIABLE"):
        assert F.live_branch_image(status) is None  # the image depends on the check: decided once R2 has re-derived it
    assert F.check_rules_of(FormalCheck(check_id="x", kind="k", description="d", problem=FAILING)) == {"inconsistent_is_failure": True, "failure_severity": "error"}
    assert F.check_rules_of(_check("cnv-1", FAILING, failure_severity="warning", inconsistent_is_failure=False)) == {
        "inconsistent_is_failure": False, "failure_severity": "warning"}


def test_a_boolean_identity_expecting_unsatisfiable_is_satisfied_and_not_accused():
    a_ = make_auditor()  # shadow on: the shadow channel issues the same receipt
    try:
        ch, rc = cs_task(a_, [_check("bool-1", ABSORPTION, "UNSATISFIABLE"), _check("sol-1", NO_READING, "SATISFIABLE")])
        assert (_fc(rc, "stem-bool-1").formal_status, _fc(rc, "stem-bool-1").satisfied) == ("UNSATISFIABLE", True)
        assert (_fc(rc, "stem-sol-1").formal_status, _fc(rc, "stem-sol-1").satisfied) == ("UNSATISFIABLE", False)
        audit = a_.audit(ch.uid)
        assert not findings(audit, "OVS-FORM-002") and not ovs_errors(audit), [(f.code, f.message[:140]) for f in ovs_errors(audit)]
    finally:
        a_.close()


def test_a_boolean_identity_written_as_failed_is_form_002_from_r2(aud, monkeypatch):
    orig = TranslatorChannel._branch_checks

    def flip(self, report, req, fnd, *a, **kw):
        structural, results, ids = orig(self, report, req, fnd, *a, **kw)
        return structural, [c.model_copy(update={"satisfied": False}) if c.constraint_id == "stem-bool-1" else c for c in results], ids
    ch, rc = cs_task(aud, [_check("bool-1", ABSORPTION, "UNSATISFIABLE")], patch=flip, monkeypatch=monkeypatch)
    f = findings(aud.audit(ch.uid), "OVS-FORM-002")
    assert f and "stem-bool-1" in f[0].message and "expected_if_sound UNSATISFIABLE gives True" in f[0].message


def test_inconsistent_premises_declared_undecided_follow_the_check_s_declaration(aud):
    checks = [_check("eq-1", INCONSISTENT, inconsistent_is_failure=False)]
    ch, rc = cs_task(aud, checks)  # the merged channel's own mapping (simulated before the merge)
    assert (_fc(rc, "stem-eq-1").formal_status, _fc(rc, "stem-eq-1").satisfied) == ("INCONSISTENT_PREMISES", None)
    assert {f.code for f in rc.findings if f.formal_result_id == _fc(rc, "stem-eq-1").formal_result_id} == {"INT-SUBJ-002"}
    audit = aud.audit(ch.uid)
    assert not findings(audit, "OVS-FORM-002") and not findings(audit, "OVS-RCPT-004") and not ovs_errors(audit)


def test_inconsistent_premises_written_as_a_failure_against_the_declaration_is_form_002(aud, monkeypatch):
    # the pre-merge channel ignores the declaration (simulated: the merged channel in this tree honours it, pinned above)
    ch, rc = cs_task(aud, [_check("eq-1", INCONSISTENT, inconsistent_is_failure=False)], patch=premerge_mapping(TranslatorChannel._branch_checks),
                     monkeypatch=monkeypatch)
    assert _fc(rc, "stem-eq-1").satisfied is False
    f = findings(aud.audit(ch.uid), "OVS-FORM-002")
    assert f and "stem-eq-1" in f[0].message and "gives None" in f[0].message


def test_a_pre_stem_check_counts_inconsistent_premises_as_a_failure_as_before(aud, monkeypatch):
    plain = FormalCheck(check_id="core-eq-1", kind="core_eq", description="pre-STEM check", problem=INCONSISTENT)
    ch, rc = cs_task(aud, [plain])
    assert _fc(rc, "core-eq-1").satisfied is False and not findings(aud.audit(ch.uid), "OVS-FORM-002")


@pytest.mark.parametrize("merged", [False, True])
def test_a_vacuous_run_may_be_written_satisfied_or_undecided(aud, monkeypatch, merged):
    checks = [_check("taut-1", VACUOUS)]
    if merged:
        ch, rc = cs_task(aud, checks)  # the merged channel's own mapping: a vacuous proof is undecided
        assert {f.code for f in rc.findings if f.formal_result_id == _fc(rc, "stem-taut-1").formal_result_id} == {"INT-SUBJ-002"}
    else:
        ch, rc = cs_task(aud, checks, patch=premerge_mapping(TranslatorChannel._branch_checks), monkeypatch=monkeypatch)  # simulated pre-merge channel
    assert _fc(rc, "stem-taut-1").satisfied is (None if merged else True)
    audit = aud.audit(ch.uid)
    assert not findings(audit, "OVS-FORM-002") and not ovs_errors(audit)


def test_a_failure_its_pack_declares_at_warning_severity_carries_int_subj_004(aud):
    ch, rc = cs_task(aud, [_check("cnv-1", FAILING, failure_severity="warning")])  # the merged channel's own mapping
    assert _fc(rc, "stem-cnv-1").satisfied is False
    assert [f.code for f in rc.findings if f.formal_result_id == _fc(rc, "stem-cnv-1").formal_result_id] == ["INT-SUBJ-004"]
    audit = aud.audit(ch.uid)
    assert not findings(audit, "OVS-RCPT-004") and not ovs_errors(audit)


def test_a_failure_its_pack_declares_at_error_severity_needs_int_subj_001(aud, monkeypatch):
    def downgrade(orig):
        def patched(self, report, req, fnd, *a, **kw):
            out = orig(self, report, req, fnd, *a, **kw)
            fnd[:] = [f.model_copy(update={"code": "INT-SUBJ-004", "severity": "warning"}) if f.code == "INT-SUBJ-001" else f for f in fnd]
            return out
        return patched
    ch, rc = cs_task(aud, [_check("cnv-1", FAILING)], patch=downgrade(TranslatorChannel._branch_checks), monkeypatch=monkeypatch)
    f = [x for x in findings(aud.audit(ch.uid), "OVS-RCPT-004") if "INT-SUBJ-001" in x.message]
    assert f and "declares its failure severity error (R2)" in f[0].message


def test_a_failure_with_no_failure_finding_is_rcpt_004_live_as_before(aud, monkeypatch):
    def drop(orig):  # no failure finding at all: the merged channel writes INT-SUBJ-004 for this check, the pre-merge one INT-SUBJ-001
        def patched(self, report, req, fnd, *a, **kw):
            out = orig(self, report, req, fnd, *a, **kw)
            fnd[:] = [f for f in fnd if f.code not in ("INT-SUBJ-001", "INT-SUBJ-004")]
            return out
        return patched
    ch, rc = cs_task(aud, [_check("cnv-1", FAILING, failure_severity="warning")], patch=drop(TranslatorChannel._branch_checks), monkeypatch=monkeypatch)
    f = [x for x in findings(aud.audit(ch.uid), "OVS-RCPT-004") if "INT-SUBJ-001" in x.message]
    assert f and "or INT-SUBJ-004, warning" in f[0].message


def test_a_counterexample_written_as_satisfied_is_form_002_whatever_the_check_declares(aud, monkeypatch):
    orig = TranslatorChannel._branch_checks

    def rosy(self, report, req, fnd, *a, **kw):
        structural, results, ids = orig(self, report, req, fnd, *a, **kw)
        fnd[:] = [f for f in fnd if f.code != "INT-SUBJ-001"]
        return structural, [c.model_copy(update={"satisfied": True}) for c in results], ids
    ch, rc = cs_task(aud, [_check("cnv-1", FAILING, failure_severity="warning")], patch=rosy, monkeypatch=monkeypatch)
    f = findings(aud.audit(ch.uid), "OVS-FORM-002")
    assert f and "stem-cnv-1" in f[0].message and "COUNTEREXAMPLE" in f[0].message
