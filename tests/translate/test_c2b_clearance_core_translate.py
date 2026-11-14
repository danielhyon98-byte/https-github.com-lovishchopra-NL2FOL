"""Translation behaviour the round-9 clearance overseers (integrated round c2) found wanting and the core fixer's second pass
fixed, tested on the rounds' recorded material (``tests/channel/data/c2_core_material.json`` and
``c2b_core_material.json``, copied verbatim):

* critical (c2 translation-fidelity, COUNTEREXAMPLEs): lit-t15 p1-point was displayed COUNTEREXAMPLE through the atom
  "the speaker holds the mother's words", which no premise mentions while the claim's own supporting claim p1-s04 ("A
  further shift comes when the speaker's own words begin to alter that authority.") states it and the encoding encodes
  nothing of it: now AMBIGUOUS_TRANSLATION (flag ``UNENCODED_SUPPORT``), an incomplete encoding, never a failed check;
* critical (c2 translation-fidelity, meaning-changing translation faults displayed ENTAILED; ``translate.fidelity``):
  ch-t15 s4.1 and c1 bm-t14 g6.1 checked another claim's figures (``neighbour_content``), cs-t15 c6.6 dropped the claim's
  bracketed qualifier "(the switch or router)" (``qualifier_not_encoded``), ph-t15 s7.4 left the claim's stated reason
  unconnected to its consequence (``reason_unconnected``) and ess-p9c s7.3 concluded, as the writer's own inference, what
  the claim only reports inside a quotation (``reported_conclusion``): each is now AMBIGUOUS_TRANSLATION with the reason
  named; c1 cs-t14 c25.1 checked the identity its supporting chain derives instead of the values the claim states ("the
  original expression gives 1, 0, 1, 0, and NOT B gives 1, 0, 1, 0"): now AMBIGUOUS_TRANSLATION (``values_not_encoded``);
* minor (c2 translation-fidelity, c1 bug r8-18): bm-t15 g5.1's "10.0%" was read as the task's mark annotation "[10]", a
  figure given exactly, and its faithful interval rejected (exactness): the precision readers skip mark annotations;
* minor (c2 translation-fidelity, E112 on step checks): maa-t15 m2.4 ("4k < 36" from m2.3's "36 − 4k > 0") and m7.2 were
  refused as restatements; the input of the step the claim writes from its previous line is no restatement (rule
  ``previous-line-step``, the transfer auditor's ``stated-input``);
* minor (c2 translation-fidelity, verbatim_match): ll-p9a p2-s10's premise "the email never names a commitment or
  consistency mechanism" was verified by the unrelated located excerpt "one more small step";
* minor (c1 translation-fidelity #15): a short quotation after a verb of saying ("the mother says 'Only this'") was refuted
  as a placeholder;
* minor (c1 translation-fidelity #17): ``partial_encoding`` fired on the reading's words about a sources line, a support
  listing or a framing label;
* minor (c2 results-audit, INT-ARG-001): bm-t15 g7.3's $59,000, the result of g7.2's written working "(0.5 × $80,000) + ... =
  $40,000 + $15,000 + $4,000 = $59,000", was an invented figure (EVD-FIG-001);
* minor (c1 results-audit #30): en-t14 p2-point's reading of the quoted word 'only' was charged as an unsourced fact
  (EVD-LACK-001).
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import fidelity as F
from epinoic_logic.translate.contracts import ClaimRecord, Interpretation, SuppliedText
from epinoic_logic.translate import diag_evidence as _evidence
from epinoic_logic.translate import grounding as _grounding
from epinoic_logic.translate import precision as _precision
from epinoic_logic.translate.diag_figures import worked_results
from epinoic_logic.translate.grounding import check_problem_grounding
from epinoic_logic.translate.pipeline import partial_encoding
from epinoic_logic.translate.quantities import SourceText
from epinoic_logic.translate.restatement import _previous_line_step, semantic_restatement

from ..channel.c2_core_support import C2, SPEC, deliver
from ..channel.c2b_core_support import deliver_recorded, supplied, translation
from ..core_hostile import SHAPES, one, sweep

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def outcome(rc, cid: str):
    return next(o for o in rc.outcomes if o.claim_id.split("@")[0] == cid.split("@")[0])


def flags(o) -> list[str]:
    return [f.code for f in (o.translation.interpretation.ambiguity_flags if o.translation.interpretation is not None else [])]


def arg_codes(rc, cid: str) -> list[str]:
    return [f.message.split("[", 1)[1].split("]", 1)[0] for f in rc.findings
            if f.code == "INT-ARG-001" and cid.split("@")[0] in [c.split("@")[0] for c in f.claim_ids] and "[" in f.message]


def claim(text: str, cid: str = "c", role: str = "point", supporting: tuple = ()) -> ClaimRecord:
    return ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="English A: Literature", task_type="analytical_paragraph",
                       claim_id=cid, claim_text=text, claim_role=role, materiality="material", supporting_claim_ids=list(supporting))


V = lambda n: {"op": "var", "name": n}  # noqa: E731
R = lambda v: {"op": "real", "value": str(v)}  # noqa: E731


def problem(symbols: list[dict], premises: list[dict], conclusion: dict, label: str = "the point") -> Problem:
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": symbols, "premises": premises,
                                   "conclusion": {"id": "concl", "expr": conclusion, "label": label}})


# ------------------------------------------------------------------- critical: a counterexample through unencoded support


def test_lit_t15_p1_point_a_counterexample_through_the_specialists_unencoded_reasoning_is_no_verdict():
    hub, _ch, _reply, rc = deliver("lit-t15", translations={"p1-point": C2["translations"]["lit-t15"]["p1-point"]})
    hub.close()
    o = outcome(rc, "p1-point")
    assert o.display_status.value == "AMBIGUOUS_TRANSLATION" and "UNENCODED_SUPPORT" in flags(o), (o.display_status, flags(o))
    [f] = [x for x in o.translation.interpretation.ambiguity_flags if x.code == "UNENCODED_SUPPORT"]
    assert "speaker_holds" in f.message and "p1-s04" in f.message


def _unlinked(meaning: str = "the speaker holds the mother's words") -> Problem:
    return problem([{"name": "e", "sort": "Bool", "meaning": "the text says the mother hands over her voice", "grounding": {"kind": "quotation"}},
                    {"name": "auth", "sort": "Bool", "meaning": "the mother holds authority over language"},
                    {"name": "holds", "sort": "Bool", "meaning": meaning}],
                   [{"id": "ev", "expr": V("e"), "label": "the mother hands over her voice"},
                    {"id": "link", "expr": {"op": "implies", "left": V("e"), "right": V("auth")}, "label": "the handing over gives the mother authority"}],
                   {"op": "and", "args": [V("auth"), V("holds")]})


def test_the_unencoded_support_rule_reads_only_reasoning_the_encoding_left_out():
    point = claim("The relationship moves from the mother's authority to a reversal in which the speaker holds the mother's words.", "p1-point",
                  supporting=("p1-s04",))
    support = claim("A further shift comes when the speaker's own words begin to alter that authority.", "p1-s04", role="interpretation")
    found = F.unencoded_support(_unlinked(), point, [support])
    assert found == (["holds"], ["p1-s04"])
    # controls: no supporting claim (the History census shape: the fact the claim adds is what the premises fail to establish);
    # an evidence line; a supporting claim the encoding encodes; an atom no supporting claim states
    assert F.unencoded_support(_unlinked(), point, []) is None
    assert F.unencoded_support(_unlinked(), point, [claim('"the speaker\'s own words begin to alter"', "p1-q05", role="evidence")]) is None
    encoded = claim("The mother hands over her voice, and the handing over gives her authority over the speaker's words.", "p1-s02", role="device")
    assert F.unencoded_support(_unlinked(), point, [encoded]) is None
    assert F.unencoded_support(_unlinked("the sea is calm at night"), point, [support]) is None


# ------------------------------------------------------------------ critical: the encoding compared with the claim (F20)


def test_ch_t15_s4_1_checks_another_claims_bond_count_and_is_no_verdict():
    hub, _ch, _reply, rc = deliver("ch-t15", translations={"s4.1": translation("c2", "ch-t15", "s4.1"), "s8.3": translation("c2", "ch-t15", "s8.3")})
    hub.close()
    o = outcome(rc, "s4.1")
    assert o.display_status.value == "AMBIGUOUS_TRANSLATION" and "neighbour_content" in flags(o), (o.display_status, flags(o))
    # control: s8.3 ("Only 1500 cm³ of H₂ is available, so hydrogen is the limiting reactant.") uses the 1800 cm³ of the line
    # before it in its own paragraph (s8.2): the working it continues, not another claim's content
    o83 = outcome(rc, "s8.3")
    assert o83.display_status.value == "ENTAILED" and "neighbour_content" not in flags(o83)


def test_c1_bm_t14_g6_1_an_instruction_verified_on_the_answer_key_of_the_claim_after_it_is_no_verdict():
    hub, _ch, _reply, rc = deliver_recorded("c1", "bm-t14", {"g6.1@business-management-specialist": translation("c1", "bm-t14", "g6.1")})
    hub.close()
    o = outcome(rc, "g6.1")
    assert o.display_status.value == "AMBIGUOUS_TRANSLATION" and "neighbour_content" in flags(o), (o.display_status, flags(o))
    # control: a conclusion whose figures no text states (the translation's own row indices, c1 cs-t14 c16.1) is no other claim's
    hub, _ch, _reply, rc = deliver_recorded("c1", "cs-t14", {"c16.1": translation("c1", "cs-t14", "c16.1")})
    hub.close()
    assert "neighbour_content" not in flags(outcome(rc, "c16.1"))


def test_ge_p9c_g4_5_compares_with_the_working_of_its_own_paragraph_and_keeps_its_verdict():
    hub, _ch, _reply, rc = deliver("ge-p9c", translations={"g4.5@geography-specialist": translation("c2", "ge-p9c", "g4.5")})
    hub.close()
    o = outcome(rc, "g4.5")
    assert "neighbour_content" not in flags(o) and o.display_status.value == "ENTAILED", (o.display_status, flags(o))


def test_cs_t15_c6_6_the_dropped_qualifier_is_named():
    hub, _ch, _reply, rc = deliver("cs-t15", translations={"c6.6": translation("c2", "cs-t15", "c6.6")})
    hub.close()
    o = outcome(rc, "c6.6")
    assert o.display_status.value == "AMBIGUOUS_TRANSLATION" and "qualifier_not_encoded" in flags(o), (o.display_status, flags(o))
    [f] = [x for x in o.translation.interpretation.ambiguity_flags if x.code == "qualifier_not_encoded"]
    assert "(the switch or router)" in f.message


def _framed(meaning: str = "each packet is placed in a frame with the next device's MAC address") -> Problem:
    return problem([{"name": "framed", "sort": "Bool", "meaning": meaning, "grounding": {"kind": "general_knowledge"}},
                    {"name": "sent", "sort": "Bool", "meaning": "the frame is sent over the cable or wireless link"}],
                   [{"id": "gk", "expr": V("framed"), "label": meaning},
                    {"id": "l", "expr": {"op": "implies", "left": V("framed"), "right": V("sent")}, "label": "the framed packet is sent over the link"}],
                   {"op": "and", "args": [V("framed"), V("sent")]}, "each packet is framed and sent over the link")


@pytest.mark.parametrize("aside", ["(see Source A)", "(e.g. Wi-Fi)", "(MAC)", "(2 marks)", "(\"hop\")", "(a)", "(for example, a hub)"])
def test_a_reference_example_label_or_abbreviation_is_no_qualifier(aside):
    text = f"Each packet is placed in a frame with the MAC address of the next device {aside} and sent over the cable or wireless link."
    assert F.dropped_qualifier(_framed(), claim(text)) is None


def test_a_qualifier_the_encoding_holds_is_encoded():
    text = "Each packet is placed in a frame with the MAC address of the next device (the switch or router) and sent over the cable or wireless link."
    assert F.dropped_qualifier(_framed(), claim(text)) is not None
    assert F.dropped_qualifier(_framed("each packet is framed with the MAC address of the next device, the switch or router"), claim(text)) is None


def test_ph_t15_s7_4_a_stated_reason_left_unconnected_is_named():
    hub, _ch, _reply, rc = deliver("ph-t15", translations={"s7.4": translation("c2", "ph-t15", "s7.4")})
    hub.close()
    o = outcome(rc, "s7.4")
    assert o.display_status.value == "AMBIGUOUS_TRANSLATION" and "reason_unconnected" in flags(o), (o.display_status, flags(o))
    # control: the same reason linked to the consequence is connected
    p = Problem.model_validate(translation("c2", "ph-t15", "s7.4")["problem"])
    data = p.model_dump(mode="json", exclude_none=True)
    data["premises"].append({"id": "s74-so", "expr": {"op": "implies", "left": V("ke_to_internal"), "right": {"op": "lt", "left": V("e_after"), "right": V("e_before")}},
                             "label": "kinetic energy turned into internal energy leaves less kinetic energy"})
    s74 = next(c for c in _claims("ph-t15") if c.claim_id == "s7.4")
    assert F.reason_unconnected(Problem.model_validate(data), s74) is None and F.reason_unconnected(p, s74) is not None


def _claims(task: str) -> list[ClaimRecord]:
    hub, _ch, reply, _rc = deliver(task)
    hub.close()
    return [ClaimRecord.model_validate(c) for c in reply.payload["claims"]]


def test_ess_p9c_s7_3_a_reported_inference_concluded_as_the_writers_own_is_named():
    hub, _ch, _reply, rc = deliver("ess-p9c", translations={"s7.3": translation("c2", "ess-p9c", "s7.3")})
    hub.close()
    o = outcome(rc, "s7.3")
    assert o.display_status.value == "AMBIGUOUS_TRANSLATION" and "reported_conclusion" in flags(o), (o.display_status, flags(o))
    # controls: the same words as the writer's own (no reporting verb), and a conclusion the translation grounds in the quotation
    p = Problem.model_validate(translation("c2", "ess-p9c", "s7.3")["problem"])
    own = claim("Drains move water off roofs more quickly than soil would, so the difference in timing comes from the catchment itself.")
    assert F.reported_conclusion(p, own) is None
    s73 = next(c for c in _claims("ess-p9c") if c.claim_id.split("@")[0] == "s7.3")
    quoted = p.model_copy(update={"symbols": [s.model_copy(update={"grounding": s.grounding.model_copy(update={"kind": "quotation"}) if s.name == "timing_from_catchment" and s.grounding else s.grounding})
                                              for s in p.symbols]})
    assert F.reported_conclusion(p, s73) is not None and F.reported_conclusion(quoted, s73) is None


# ------------------------------------------------------------------ minor: a step check from the previous line (E112)


def test_maa_t15_m2_4_and_m7_2_step_checks_read_from_their_previous_lines():
    """The rule reads the recorded m2.4 and m7.2 encodings as step checks once given the claims' previous lines (the
    pipeline's ``previous_lines``), and names them without. Turned, as the core fixer's handoff prescribed, into "ENTAILED with
    no E112" once the pipeline passes the lines and the transfer auditor's floor re-runs the rule with the same lines (the handoff
    fixer of the second fix pass changed the two together; the audit's side is pinned in the overseer's
    ``test_clearance_c2b_handoff.py``)."""
    from epinoic_logic.translate.pipeline import previous_lines
    claims = _claims("maa-t15")
    report_like = type("R", (), {"claims": claims})()
    for cid in ("m2.4", "m7.2"):
        p = Problem.model_validate({**translation("c2", "maa-t15", cid)["problem"], "claim_id": cid})
        c = next(x for x in claims if x.claim_id == cid)
        prior = previous_lines(c, report_like)
        assert semantic_restatement(p, claim_text=c.claim_text) is not None, cid
        assert semantic_restatement(p, claim_text=c.claim_text, prior_texts=prior) is None, (cid, prior)
    hub, _ch, _reply, rc = deliver("maa-t15", translations={"m2.4": translation("c2", "maa-t15", "m2.4"), "m7.2": translation("c2", "maa-t15", "m7.2")})
    hub.close()
    for cid in ("m2.4", "m7.2"):
        o = outcome(rc, cid)
        assert o.display_status.value == "ENTAILED" and not any("E112" in d for d in o.translation.diagnostics), (cid, o.display_status)


def test_the_previous_line_rule_keeps_catching_a_premise_that_restates_the_claims_own_line():
    p = Problem.model_validate(translation("c2", "maa-t15", "m2.4")["problem"])
    premise = p.premises[0].expr.model_dump(mode="json", exclude_none=True)
    conclusion = p.conclusion.expr.model_dump(mode="json", exclude_none=True)
    assert _previous_line_step(["(a) Two distinct real roots need Δ > 0", "36 − 4k > 0  A1"], "4k < 36", premise, [conclusion])
    # the claim writes the input itself (no step), no earlier line writes it (the translation's own), or the claim does not
    # write the result: no exemption, and the restatement is caught as before
    assert not _previous_line_step(["36 − 4k > 0"], "36 − 4k > 0, 4k < 36", premise, [conclusion])
    assert not _previous_line_step(["(a) Two distinct real roots need Δ > 0"], "4k < 36", premise, [conclusion])
    assert not _previous_line_step(["36 − 4k > 0"], "k < 9", premise, [conclusion])
    assert semantic_restatement(p, claim_text="4k < 36") is not None
    assert semantic_restatement(p, claim_text="4k < 36", prior_texts=["36 − 4k > 0  A1"]) is None


# ------------------------------------------------------------------------------- minor: grounding readers (F24, F42)


def test_ll_p9a_p2_s10_an_unrelated_excerpt_never_verifies_a_negative_fact():
    p = Problem.model_validate(translation("c2", "ll-p9a", "p2-s10")["problem"])
    g, checks = check_problem_grounding(p, supplied("c2", "ll-p9a"))
    [c] = [x for x in checks if x.target_id == "s10-nomech" and x.method == "content_in_excerpt"]
    assert c.verified is False and "never or does not name, mention or state something" in c.detail
    assert next(x for x in g.premises if x.id == "s10-nomech").grounding.verified is False
    # control: an excerpt whose clause holds the literal's words still states the negative fact
    doc = SuppliedText(document_id="doc-mail", text="Dear member, the email never names a commitment mechanism. Take one more small step.")
    stated = Problem.model_validate({**p.model_dump(mode="json", exclude_none=True)})
    data = stated.model_dump(mode="json", exclude_none=True)
    for pr in data["premises"]:
        if pr["id"] == "s10-nomech":
            pr["grounding"]["source_refs"] = [{"document_id": "doc-mail", "excerpt": "the email never names a commitment mechanism"}]
    g2, _checks = check_problem_grounding(Problem.model_validate(data), [doc])
    assert next(x for x in g2.premises if x.id == "s10-nomech").grounding.verified is True


def _said(meaning: str, excerpt: str) -> Problem:
    return problem([{"name": "q", "sort": "Bool", "meaning": meaning}],
                   [{"id": "pq", "expr": V("q"), "label": meaning, "grounding": {"kind": "quotation", "source_refs": [{"document_id": "poem", "excerpt": excerpt}]}}],
                   V("q"))


@pytest.mark.parametrize("meaning,excerpt", [("the mother says 'Only this'", "Only this"), ("the mother's words 'All of it'", "All of it"),
                                             ("she replies all of it", "All of it")])
def test_a_short_quotation_someone_says_is_verified_by_its_presence(meaning, excerpt):
    doc = SuppliedText(document_id="poem", text="She looks at the shelf. 'Only this,' she says, and later, 'All of it.' The A is gone.")
    g, _checks = check_problem_grounding(_said(meaning, excerpt), [doc])
    assert g.premises[0].grounding.verified is True


def test_a_placeholder_cited_as_a_fact_is_still_refuted():
    doc = SuppliedText(document_id="poem", text="She looks at the shelf. 'Only this,' she says, and the war ended in the end.")
    g, checks = check_problem_grounding(_said("the war ended in 1953", "the"), [doc])
    assert g.premises[0].grounding.verified is False and any(c.method == "content_in_excerpt" and c.verified is False for c in checks)


# ------------------------------------------------------------------------------------ minor: partial_encoding (F33)


@pytest.mark.parametrize("reading,fires", [
    ("Atom counts are premises. The \"what the question wants\" label is the specialist's framing and is not encoded.", False),
    ("Those two links are encoded; the sources line (p6-point) is not a claim and is not encoded.", False),
    ("The listing also cites p1-point as a support; it is not encoded as a premise because the point is the claim this link summarises.", False),
    ("The disclaimer that only the teacher and the IB award real marks is not a quantity and is not encoded.", False),
    ("'Slightly' is not encoded (it is a magnitude word with no stated threshold).", True),
    ("The claim also says the answer carries its unit; a unit is presentation, so that part is not encoded.", True),
])
def test_partial_encoding_reads_the_claim_part_the_reading_names(reading, fires):
    p = problem([{"name": "a", "sort": "Bool"}], [{"id": "pa", "expr": V("a")}], V("a"))
    text = ("The starting masses differ slightly, so the answer carries its unit; only your teacher and the IB award real marks; "
            "the equation is balanced, as the question wants.")
    flag = partial_encoding(p, claim(text), Interpretation(reading=reading, glossary=[], ambiguity_flags=[]))
    assert (flag is not None) is fires, (reading, flag)


# ------------------------------------------------------------------------- minor: evidence diagnostics (F4, F37)


def test_bm_t15_g7_3_a_figure_the_answers_own_working_gives_is_no_invented_figure():
    hub, _ch, _reply, rc = deliver("bm-t15", translations={"g7.3@business-management-specialist": translation("c2", "bm-t15", "g7.3")})
    hub.close()
    assert "EVD-FIG-001" not in arg_codes(rc, "g7.3"), arg_codes(rc, "g7.3")
    records = [SourceText("supplied_text", t["document_id"], t["text"]) for t in SPEC["bm-t15"]["supplied_texts"]]
    g72 = "Expected value = (0.5 × $80,000) + (0.3 × $50,000) + (0.2 × $20,000)\n= $40,000 + $15,000 + $4,000 = $59,000"
    assert {w.written for w, _t, _m in worked_results([g72], records)} >= {"$15,000", "$4,000", "$59,000"}
    # control: a chain whose first member is not anchored (an operand no record states) anchors nothing
    assert not {w.written for w, _t, _m in worked_results(["Value = (0.7 × $81,113) + (0.3 × $50,000)\n= $56,779 + $15,000 = $71,779"], records)} & {"$56,779", "$71,779"}


def test_en_t14_p2_point_the_reading_of_a_quoted_word_is_no_unsourced_fact():
    hub, _ch, _reply, rc = deliver_recorded("c1", "en-t14", {"p2-point": translation("c1", "en-t14", "p2-point")})
    hub.close()
    assert "EVD-LACK-001" not in arg_codes(rc, "p2-point"), arg_codes(rc, "p2-point")
    # control: a general-knowledge premise stating a historical fact still draws EVD-LACK-001
    data = json.loads(json.dumps(translation("c1", "en-t14", "p2-point")))
    for pr in data["problem"]["premises"]:
        if pr["id"] == "gk-only":
            pr["label"] = "the poem was written in 1962, the year the piano was sold"
    for s in data["problem"]["symbols"]:
        if s["name"] == "only_limits_one":
            s["meaning"] = "the poem was written in 1962, the year the piano was sold"
    hub, _ch, _reply, rc = deliver_recorded("c1", "en-t14", {"p2-point": data})
    hub.close()
    assert "EVD-LACK-001" in arg_codes(rc, "p2-point"), arg_codes(rc, "p2-point")


# ---------------------------------------- critical (F20, c1 case): stated values the encoding leaves out (values_not_encoded)


def test_c1_cs_t14_c25_1_a_check_whose_stated_values_the_encoding_leaves_out_is_no_verdict():
    """c1 cs-t14 c25.1 ("Check: for A, B = 00, 01, 10 and 11, the original expression gives 1, 0, 1, 0, and NOT B gives 1, 0, 1,
    0.") was encoded as the identity its supporting chain derives (NOT (A OR B) OR (A AND NOT B) iff NOT B) and displayed
    ENTAILED, so the stated values were never checked: "gives 1, 1, 1, 0" would have been ENTAILED as well. Now
    AMBIGUOUS_TRANSLATION, the reason named; c16.1 (the truth table's rows, the translation's own indices) keeps its verdict."""
    hub, _ch, _reply, rc = deliver_recorded("c1", "cs-t14", {"c25.1": translation("c1", "cs-t14", "c25.1"),
                                                             "c16.1": translation("c1", "cs-t14", "c16.1")})
    hub.close()
    o = outcome(rc, "c25.1")
    assert o.display_status.value == "AMBIGUOUS_TRANSLATION" and "values_not_encoded" in flags(o), (o.display_status, flags(o))
    [f] = [x for x in o.translation.interpretation.ambiguity_flags if x.code == "values_not_encoded"]
    assert "gives 1, 0, 1, 0" in f.message
    assert [x for x in rc.findings if x.code == "INT-REQ-006" and "c25.1" in x.claim_ids]
    o16 = outcome(rc, "c16.1")
    assert o16.display_status.value == "ENTAILED" and "values_not_encoded" not in flags(o16)


def _identity(conclusion: dict | None = None, premises: list | None = None) -> Problem:
    return problem([{"name": "orig", "sort": "Bool", "meaning": "the original expression"}, {"name": "b", "sort": "Bool", "meaning": "input B"},
                    {"name": "y", "sort": "Real", "meaning": "the mean reading"}],
                   premises if premises is not None else [{"id": "chain", "expr": {"op": "iff", "left": V("orig"), "right": {"op": "not", "arg": V("b")}}}],
                   conclusion if conclusion is not None else {"op": "iff", "left": V("orig"), "right": {"op": "not", "arg": V("b")}})


CHECK = "Check: for A, B = 00, 01, 10 and 11, the original expression gives 1, 0, 1, 0, and NOT B gives 1, 0, 1, 0."


def test_the_values_rule_reads_only_stated_values_the_encoding_encodes_none_of():
    flag = F.stated_values_not_encoded(_identity(), claim(CHECK))
    assert flag is not None and flag.code == "values_not_encoded"
    # the outputs listed with "are" and "and", and real values, are read the same way
    assert F.stated_values_not_encoded(_identity(), claim("The outputs are 0, 1, 1 and 0 for the four rows.")) is not None
    assert F.stated_values_not_encoded(_identity(), claim("The three readings were 2.1, 2.3 and 2.2 cm, so the mean is stable.")) is not None
    # controls: the conclusion checks truth values (the rows), a literal encodes a value of the run, an interval holds one
    rows = {"op": "and", "args": [{"op": "iff", "left": V("orig"), "right": {"op": "bool", "value": True}},
                                  {"op": "iff", "left": V("b"), "right": {"op": "bool", "value": False}}]}
    assert F.stated_values_not_encoded(_identity(conclusion=rows), claim(CHECK)) is None
    mean = {"op": "eq", "left": V("y"), "right": {"op": "div", "left": {"op": "add", "args": [R("2.1"), R("2.3"), R("2.2")]}, "right": R(3)}}
    assert F.stated_values_not_encoded(_identity(conclusion=mean), claim("The three readings were 2.1, 2.3 and 2.2 cm, so the mean is 2.2 cm.")) is None
    band = {"op": "and", "args": [{"op": "ge", "left": V("y"), "right": R("2.25")}, {"op": "lt", "left": V("y"), "right": R("2.35")}]}
    assert F.stated_values_not_encoded(_identity(conclusion=band), claim("The three readings were 2.1, 2.3 and 2.2 cm.")) is None
    # controls: fewer than three values, years, code numerals, number words, values not after a result word
    for text in ("The original expression gives 1 and 0.", "The wars were 1914, 1939 and 1950.", "The inputs are 00, 01 and 011.",
                 "The outputs are one, zero and one.", "Rows 1, 2 and 3 of the table hold the inputs.", "X is 1 in the rows 001, 011, 110 and 111."):
        assert F.stated_values_not_encoded(_identity(), claim(text)) is None, text


@pytest.mark.parametrize("text", ["is" + " " * 400_000 + "x", "is" + "\t" * 200_000 + ":" + " " * 200_000 + "x", "gives 1" + " ," * 200_000 + "x",
                                  "is 1 and" + " " * 400_000 + "x", "is 1, " * 60_000 + "x", "gives " * 60_000 + "x"])
def test_the_value_run_pattern_is_linear_on_the_whole_text(text):
    """The class sweep of this pass: the pattern first read blanks around an optional ':' or '=' with two adjacent blank runs,
    which split a long run of blanks every way before failing (0.23 s on 4,000 blanks, 1.0 s on 8,000: quadratic). Read on
    400,000 characters (the contract's response limit), far beyond the 4,000 a claim is read to, it stays linear."""
    import time
    t0 = time.process_time()
    list(F._VALUE_RUN_RE.finditer(text))
    assert time.process_time() - t0 < 1.0


# ----------------------------------------- minor (c2 translation-fidelity, c1 bug r8-18): a mark annotation states no figure


def test_bm_t15_g5_1_the_tasks_mark_annotation_is_no_given_figure():
    """bm-t15 g5.1 ("Pellow Cycles' sales revenue rose by 10.0%, but the market grew by 25.0%, so its market share fell from 15.0%
    to 13.2%.") encodes 10.0 as [9.95, 10.05); the exactness rule read it as the task's mark annotation "[10]", a figure given
    exactly, and rejected the faithful encoding of a correct claim on both attempts (INVALID_FORMALIZATION)."""
    hub, _ch, _reply, rc = deliver("bm-t15", translations={"g5.1@business-management-specialist": translation("c2", "bm-t15", "g5.1")})
    hub.close()
    o = outcome(rc, "g5.1")
    assert o.display_status.value == "ENTAILED", (o.display_status, o.translation.diagnostics[:2])


def test_the_precision_readers_skip_mark_annotations_only():
    from epinoic_logic.translate.precision import _stated_figures, read_sites
    task = SourceText("task", "t", "Evaluate which option Aled should choose. [10]")
    assert [f.value for f in _stated_figures(task)] == []
    kept = SourceText("task", "t", "Table 1 shows 42 sites [2 marks] and a fee of 10 dollars [about 10 in all].")
    assert [str(f.value) for f in _stated_figures(kept)] == ["1", "42", "10", "10"]
    band = problem([{"name": "g", "sort": "Real", "meaning": "the percentage rise in sales revenue"}], [],
                   {"op": "and", "args": [{"op": "ge", "left": V("g"), "right": R("9.95")}, {"op": "lt", "left": V("g"), "right": R("10.05")}]})
    [reading] = read_sites(band, [SourceText("claim", "g5.1", "Sales revenue rose by 10.0%."), task])
    assert reading.source is not None and reading.source.kind == "claim" and reading.exactness != "given"
    # control: a figure the task states outside a mark annotation is still the given figure
    [given] = read_sites(band, [SourceText("claim", "g5.1", "Sales revenue rose by 10.0%."), SourceText("task", "t", "Revenue rose by 10%. [4]")])
    assert given.source is not None and given.source.kind == "task" and given.exactness == "given"


# --------------------------------------------------------------------------- the new readers are linear (class sweep)


def _entries(text: str):
    c = claim(text[:4000])
    framed = _framed()
    unlinked = _unlinked()
    support = claim(text[:4000], "p1-s04", role="interpretation")
    yield "unencoded_support", lambda: F.unencoded_support(unlinked, c, [support] * 8)
    yield "neighbour_content", lambda: F.neighbour_content(framed, c, [], None)
    yield "dropped_qualifier", lambda: F.dropped_qualifier(framed, claim("(" + text[:3990] + ")"))
    yield "dropped_qualifier(asides)", lambda: F.dropped_qualifier(framed, claim(("(x) " * 1000)[:4000]))
    yield "reason_unconnected", lambda: F.reason_unconnected(framed, c)
    yield "reported_conclusion", lambda: F.reported_conclusion(framed, claim('The writer notes that "' + text[:3900] + '"'))
    yield "stated_values_not_encoded", lambda: F.stated_values_not_encoded(_identity(), claim(("It gives 1, " + text)[:4000]))
    yield "precision._stated_figures", lambda: _precision._stated_figures(SourceText("task", "t", "[1" + text + "] [2] " + text))
    yield "_previous_line_step", lambda: _previous_line_step([text[:4000]] * 3, text[:4000], {"op": "gt", "left": V("x"), "right": R(0)}, [{"op": "gt", "left": V("x"), "right": R(1)}])
    yield "partial_encoding", lambda: partial_encoding(framed, c, Interpretation(reading=(text + " is not encoded")[:2000], glossary=[], ambiguity_flags=[]))
    yield "worked_results", lambda: worked_results(["= 1 + " + text + " = 2"], [])
    yield "check_problem_grounding(absence)", lambda: check_problem_grounding(_absence(text), [SuppliedText(document_id="d", text="one more step " + text)])
    yield "_names_words", lambda: _grounding._names_words(text[:600], "only this")
    yield "_quoted_word_convention readers", lambda: (list(_evidence._QUOTED_PASSAGE_RE.finditer(text[:4000])), _evidence._CONVENTION_CUE_RE.search(text[:300]),
                                                       list(_evidence._QUOTED_WORD_RE.finditer(text[:300])))


def _absence(text: str) -> Problem:
    meaning = ("the text never names " + text)[:900]
    return problem([{"name": "q", "sort": "Bool", "meaning": meaning}],
                   [{"id": "pq", "expr": V("q"), "label": meaning[:400],
                     "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "d", "excerpt": "one more step"}]}}], V("q"))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c2b_translate_readers(shape):
    """Every reader this pass added to the translation layer, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_entries, texts=one(shape))


@pytest.mark.parametrize("text", ["(a b) " * 3000, "= 1 + 2 " * 2500, "'x' " * 5000, "so " * 6000, "notes \"" * 3000,
                                  "gives 1, " * 2500 + "x", "is 1 and " * 2500 + "x", "are 1, 2," * 2500, "gives 1, 0, 1 " * 1500])
def test_the_new_translate_readers_are_linear_on_their_own_worst_inputs(text):
    assert not sweep(_entries, texts={"worst": text})


# ------------------------------------------------------------- minor: a named item is no unencoded figure (F27, 'Paper 1')


@pytest.mark.parametrize("text,missing", [
    ("In a Paper 1 commentary the speaker's grip on the past loosens across the final stanza.", []),
    ("Table 1 shows 42 sites [2].", ["'42'"]),        # the table's number and the mark annotation aside, the count is a figure
    ("The poem has 3 stanzas.", ["'3'"]),
])
def test_a_named_item_or_a_mark_annotation_is_no_unencoded_figure(text, missing):
    from epinoic_logic.translate.pipeline import unencoded_claim_figures
    p = problem([{"name": "a", "sort": "Bool"}], [{"id": "pa", "expr": V("a")}], V("a"))
    assert unencoded_claim_figures(p, claim(text)) == missing


def test_a_negated_statement_translated_from_a_language_b_text_is_not_judged_an_absence():
    """Control of the absence rule (c1 sp-t14 g3.4 on the harness replay): "not all neighbours see the newcomers with good
    eyes" grounded by the Spanish words that state it shares no English word with them, and is no claim that the text never
    names something: a paraphrase is not judged here, as before."""
    doc = SuppliedText(document_id="doc-es", text="En el pueblo, no todos los vecinos ven con buenos ojos a los recién llegados.")
    p = problem([{"name": "all_good", "sort": "Bool", "meaning": "all neighbours see the newcomers with good eyes"}],
                [{"id": "ev-not-all", "expr": {"op": "not", "arg": V("all_good")}, "label": "not all neighbours see the newcomers with good eyes",
                  "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc-es", "excerpt": "no todos los vecinos ven con buenos ojos"}]}}],
                {"op": "not", "arg": V("all_good")})
    g, checks = check_problem_grounding(p, [doc])
    assert g.premises[0].grounding.verified is True and not [c for c in checks if c.method == "content_in_excerpt" and c.verified is False]
