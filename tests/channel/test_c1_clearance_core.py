"""Channel behaviour found wanting by the round-8 clearance overseers (integrated round c1), fixed by the core fixer and
tested here on the round's recorded material (``data/c1_core_material.json``, copied verbatim; ``c1_core_support``):

* critical: a citation by paragraph, by table, a figure taken from a supplied table or quoted code satisfied no "cite the
  text" constraint (breadth ec-1, ge-2, cs-3: INT-REQ-005 error, "no claim carries a source reference");
* critical: a rejected candidate root ("x = −5 is rejected because it does not satisfy x > 4", maa-t14 m7.7) was pooled as
  an assertion about the unknown m6.1 constrains to x > 4: an error-level INT-CONFLICT-001 on the genuine receipt and
  INT-CONFLICT-001 and -002 on the synthesis;
* critical: a quotation whose final punctuation sits inside the quotation marks was not located (bm-p8a g2.2, INT-REQ-003);
* major: a decline (ge-t14) and a plan that waits for the student's approval (ps-p8d) were delivered as if every request
  item had been answered, and the decline's guidance was charged against the deliverable's word bound;
* minor: a receipt carried the pool's glossary warnings about pairs of another agent's claims.
"""
from __future__ import annotations

import pytest

from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.channel.bus import DECLINED_BOUND_PREFIX, withheld_deliverable
from epinoic_logic.channel.citations import citation_evidence, code_spans, locators_in, table_cells
from epinoic_logic.translate.contracts import ClaimRecord, SuppliedText
from epinoic_logic.translate.grounding import check_claim_sources, locate_excerpt, trim_trailing_punctuation
from epinoic_logic.ir.schema import SourceRef

from .c1_core_support import C1, SPEC, by_code, codes, deliver, relay_synthesis, supplied

from ..core_hostile import SHAPES, one, sweep


def constraint(rc, kind_word: str = "c2"):
    return next(c for c in rc.constraint_results if c.constraint_id == kind_word)


# ---------------------------------------------------------------------------------------- critical: citations (F13/F14)


@pytest.mark.parametrize("task,kind,shown", [
    ("b1/ec-1", "locator", "Table 1"),                 # "Cite the text by paragraph and the data by table": "(paragraph 1)", "(Table 1)"
    ("b1/ge-2", "table_figures", "31.0"),              # "Quote figures from the table": the table's own figures
    ("b1/cs-3", "code", "for i in range(1, len(scores)):"),  # "Quote my code exactly": the student's code in backticks
])
def test_a_citation_by_locator_table_figure_or_quoted_code_satisfies_the_constraint(task, kind, shown):
    _hub, _ch, _reply, rc = deliver(task)
    c2 = constraint(rc)
    assert c2.satisfied is True, c2.detail
    assert "INT-REQ-005" not in codes(rc.findings) or all("c2" not in f.message for f in by_code(rc.findings, "INT-REQ-005"))
    item = SPEC[task]
    ev = citation_evidence(item["response_text"], supplied(task), quotation_asked=kind != "locator")
    assert ev is not None and ev.kind == kind and any(shown in s for s in ev.shown), ev


def _without(text: str, *spans: str) -> str:
    for s in spans:
        text = text.replace(s, "")
    return text


def test_negative_controls_cite_nothing():
    # an answer to ec-1's request that cites nothing: no quotation, no locator, no figure of the supplied table
    bare = ("A specific tax shifts supply up by the amount of the tax and corrects overconsumption only if the rate matches the external "
            "cost. Demand for sugary drinks is price inelastic, so consumers bear most of the tax. The tax is regressive, because poorer "
            "households spend a larger share of their income on these drinks. On balance, the tax is justified only to a limited extent.")
    _h, _c, _r, rc = deliver("b1/ec-1", bare)
    assert constraint(rc).satisfied is False and "INT-REQ-005" in codes(rc.findings)
    # a locator the supplied texts do not resolve (there is no paragraph 9 and no Table 7) is no citation
    texts = supplied("b1/ec-1")
    assert citation_evidence("As paragraph 9 and Table 7 show, the tax failed.", texts, quotation_asked=False) is None
    # a request that asks for quotations is not satisfied by a bare locator
    assert citation_evidence("As paragraph 1 shows, the tax was introduced.", texts, quotation_asked=True) is None
    assert citation_evidence("As paragraph 1 shows, the tax was introduced.", texts, quotation_asked=False) is not None
    # figures that are no cells of the supplied table, and code that is not the student's
    assert citation_evidence("The share fell from 33.3% to 12.5%.", supplied("b1/ge-2"), quotation_asked=True) is None
    assert citation_evidence("Use `best_index = i` instead.", supplied("b1/cs-3"), quotation_asked=True) is None
    # one figure of a table is no evidence of quoting it, and a one-digit whole number never is
    assert citation_evidence("It was 31.0 in 1 year.", supplied("b1/ge-2"), quotation_asked=True) is None


def _citation_entries(text):
    texts = supplied("b1/ec-1") + supplied("b1/ge-2") + supplied("b1/cs-3")
    hostile_doc = [SuppliedText(document_id="doc-hostile", text=text)]
    return [("citation_evidence(cite)", lambda: citation_evidence(text, texts, quotation_asked=False)),
            ("citation_evidence(quote)", lambda: citation_evidence(text, texts, quotation_asked=True)),
            ("citation_evidence(hostile document)", lambda: citation_evidence("As paragraph 2 and Table 1 show, `x = 1` and 31.0 and 15.9.", hostile_doc, quotation_asked=False)),
            ("locators_in", lambda: locators_in(text)), ("table_cells", lambda: table_cells(text)), ("code_spans", lambda: code_spans(text)),
            ("withheld_deliverable", lambda: withheld_deliverable(text)),
            ("withheld_deliverable(after a reply)", lambda: withheld_deliverable("Reply and I will write the full " + text))]


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c1_channel_readers(shape):
    """Every reader this clearance added to the channel, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_citation_entries, texts=one(shape))


@pytest.mark.parametrize("text", ["paragraph " * 4000 + "x", "(Table 1 " * 3000 + "x", "`" * 20000, "` " + "x" * 20000, "31.0 " * 4000 + "x",
                                  "| 1 | 2 " * 3000 + "x", "Source A " * 3000 + "x", "lines " * 4000 + "x", "para. " * 4000 + "x",
                                  "Reply " * 4000 + "x", "Reply and I will write the full " * 1500, "Once you confirm " * 3000 + "x",
                                  "Shall I write the full " * 2000 + "x", "Would you like me to write the essay " * 1500 + "x"])
def test_the_new_channel_readers_are_linear_on_their_own_worst_inputs(text):
    assert not sweep(_citation_entries, texts={"worst": text})


# ------------------------------------------------------------------- critical: a rejected candidate is no contradiction


def _domain_statement() -> dict:
    """m6.1's domain as a bare statement the pool holds (a consistency problem, "x > 4" on the report-wide unknown): the
    candidate rule tested on the plainest form of the domain (the recorded encodings are tested below)."""
    rec = C1["translations"]["maa-t14"]["m6.1"]
    problem = {k: v for k, v in rec["problem"].items() if k != "conclusion"}
    problem.update(query="consistency", premises=[{"id": "domain", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "4"}},
                                                  "label": "domain: x > 4", "grounding": {"kind": "specialist_inference", "source_refs": [], "certainty": "established"}}])
    return {**rec, "problem": problem}


def test_a_rejected_candidate_root_is_not_charged_as_a_contradiction_and_needs_no_disclosure():
    _hub, ch, reply, rc = deliver("maa-t14", translations={"m6.1": _domain_statement(), "m7.7": C1["translations"]["maa-t14"]["m7.7"]})
    assert {"m6.1", "m7.7"} <= set(ch.formalized)
    assert "INT-CONFLICT-001" not in codes(rc.findings), [f.message for f in by_code(rc.findings, "INT-CONFLICT-001")]
    [unattributable] = [f for f in by_code(rc.findings, "INT-CONFLICT-004") if set(f.claim_ids) == {"m6.1", "m7.7"}]
    assert unattributable.severity == "warning" and "rule candidate" in unattributable.message and "no contradiction is charged" in unattributable.message
    assert ch.conflicts_seen == []
    _msg, rr = relay_synthesis(ch, reply.payload["report_id"], [
        ("Domain: x + 4 > 0 and x − 4 > 0, so x > 4.", ["m6.1"], "carried"),
        ("x = −5 is rejected because it does not satisfy x > 4.", ["m7.7"], "carried")])
    assert rr.status is not TransmissionStatus.REJECTED
    assert "INT-CONFLICT-001" not in codes(rr.findings) and "INT-CONFLICT-002" not in codes(rr.findings)


def test_the_recorded_m6_1_and_m7_7_pool_with_no_contradiction_charged_or_demanded():
    """The round's own case, both recorded translations served (m6.1, a stated step, is displayed again since the clearance's
    second pass): the pool names the rejected candidate unattributable (INT-CONFLICT-004, warning) and charges nothing; the
    synthesis that carries both claims with no conflict record is demanded no disclosure."""
    _hub, ch, reply, rc = deliver("maa-t14", translations={k: C1["translations"]["maa-t14"][k] for k in ("m6.1", "m7.7")})
    assert {"m6.1", "m7.7"} <= set(ch.formalized)
    assert "INT-CONFLICT-001" not in codes(rc.findings) and ch.conflicts_seen == []
    assert any(set(f.claim_ids) == {"m6.1", "m7.7"} and f.severity == "warning" and "rule candidate" in f.message for f in by_code(rc.findings, "INT-CONFLICT-004"))
    _msg, rr = relay_synthesis(ch, reply.payload["report_id"], [
        ("Domain: x + 4 > 0 and x − 4 > 0, so x > 4.", ["m6.1"], "carried"),
        ("x = −5 is rejected because it does not satisfy x > 4.", ["m7.7"], "carried")])
    assert "INT-CONFLICT-001" not in codes(rr.findings) and "INT-CONFLICT-002" not in codes(rr.findings)


# --------------------------------------------------------- critical: sentence punctuation inside the closing quotation mark


def test_a_quotation_with_its_full_stop_inside_the_marks_is_located_as_the_adapter_locates_it():
    peer = C1["peer_documents"]["bm-p8a"]
    doc = SuppliedText(document_id=peer["document_id"], text=peer["text"])
    excerpt = "I assume, as the data show, that the whole $150 tariff passes into the price paid in Calvessa."
    match = locate_excerpt(excerpt, doc.text)
    assert match is not None and (match.start, match.end) == (69, 162) and "punctuation" in (match.note or "")
    claim = ClaimRecord(claim_id="g2.2", request_id="req-p8a", task_id="p8a", report_id="rep-bm", agent_id="business-management-specialist",
                        subject="Business Management", task_type="structured_question", claim_role="evidence", materiality="material",
                        claim_text=f'The Economics specialist\'s analysis states: "{excerpt}"', source_refs=[SourceRef(document_id=doc.document_id, excerpt=excerpt)])
    [check] = check_claim_sources(claim, [doc])
    assert check.method == "verbatim_match" and check.detail.startswith("peer_report: found verbatim") and "at characters 69-162" in check.detail
    assert trim_trailing_punctuation(excerpt) == excerpt[:-1]
    # control: a quotation whose words differ is still not located
    altered = ClaimRecord(**{**claim.model_dump(), "source_refs": [SourceRef(document_id=doc.document_id, excerpt=excerpt.replace("$150", "$200"))]})
    [bad] = check_claim_sources(altered, [doc])
    assert bad.verified is False


def test_the_bm_p8a_reply_draws_no_int_req_003_for_g2_2():
    _hub, _ch, _reply, rc = deliver("bm-p8a")
    assert not [f for f in by_code(rc.findings, "INT-REQ-003") if any(c.startswith("g2.2") for c in f.claim_ids)]


# --------------------------------------------------------------------- major: a decline or a deferred deliverable


def test_a_decline_is_named_and_no_item_reads_as_addressed_and_its_bound_is_not_applicable_naming_the_decline():
    """ge-t14 declines the IA sections it was asked for: no item reads as addressed and each item is INT-REQ-004 naming the
    decline. The word bounds set on the declined deliverable do not apply to the decline: each is recorded not applicable
    (satisfied None, method not_checkable, no formal result), its detail naming the declining sentence, and no INT-REQ-005
    is raised for it. Rewritten by the clearance's handoff fixer to the rule this test's first version waited for (the
    core fixer's handoff, item 5): the first version asserted the interim behaviour (the bounds decided and charged at
    error, naming the decline) because the transfer auditor did not yet accept a not-applicable bound; it now does, exactly
    when ``withheld_deliverable`` reads a decline in the journaled response (rule declined-bound,
    ``overseer/tests/overseer_tests/test_c1_handoff_bounds.py``, which also asserts the audit agrees and names the same record on an
    answer that declines nothing)."""
    _hub, _ch, _reply, rc = deliver("ge-t14")
    assert rc.coverage and not any(c.addressed for c in rc.coverage)
    named = by_code(rc.findings, "INT-REQ-004")
    assert len(named) == len(rc.coverage) and all("declines the deliverable" in f.message and "I can't write the analysis" in f.message for f in named)
    assert all(f.severity == "warning" for f in named)
    bounds = [c for c in rc.constraint_results if c.detail.startswith(DECLINED_BOUND_PREFIX)]  # the word and paragraph bounds
    assert bounds and all(c.satisfied is None and c.method == "not_checkable" and not c.formal_result_id and "I can't write the analysis" in c.detail for c in bounds)
    assert not [c for c in rc.constraint_results if c.detail.startswith("measured ")]  # no bound decided on the decline
    assert not by_code(rc.findings, "INT-REQ-005")
    assert not [f for f in rc.findings if f.severity == "error"]


def test_a_plan_that_waits_for_the_students_approval_is_named_pending():
    _hub, _ch, _reply, rc = deliver("ps-p8d")
    assert rc.coverage and not any(c.addressed for c in rc.coverage)
    [named] = by_code(rc.findings, "INT-REQ-004")
    assert "defers the deliverable" in named.message and 'Reply "approve"' in named.message


@pytest.mark.parametrize("text,kind", [
    ("I can't write your conclusion, because the conclusion must be your own work. I can help you plan it.", "declined"),
    ('Here is a plan.\n\nReply "approve" and I will write the full evaluation within 500 words.', "deferred"),
    ("Here is the outline. Once you confirm, I will write the full essay.", "deferred"),
    ("Here is the outline. Shall I write the full answer now?", "deferred"),
    ("Would you like me to write the essay from this plan?", "deferred"),
])
def test_declines_and_deferrals_are_read(text, kind):
    found = withheld_deliverable(text)
    assert found is not None and found[0] == kind, found


@pytest.mark.parametrize("text", [
    "The tax is regressive (paragraph 4). Let me know and I can add an example.",
    "Reply to each point in your next draft, and I will be glad to look at it.",
    "Answer: x = 5. If you want, I can explain the method again.",
    "I cannot stress enough that the conclusion must answer the question.",
])
def test_a_complete_answer_with_an_offer_is_no_deferral(text):
    assert withheld_deliverable(text) is None


# ------------------------------------------------------------------ minor: pool warnings about other agents' claims


def test_a_receipt_carries_only_the_glossary_warnings_that_name_its_own_claims():
    _hub, ch, reply, rc = deliver("maa-t14", translations=C1["translations"]["maa-t14"])
    own = {c["claim_id"] for c in reply.payload["claims"]}
    for f in by_code(rc.findings, "INT-GLOSSARY-005"):
        assert set(f.claim_ids) & own


# ------------------------------------- critical (regression of the round-7 glossary fix): the r7 controls F1 and F2 restored


def _closure_fixture(claim_id: str, meaning: str, *, denied: bool) -> dict:
    """A translation of a claim about the 13 August 1961 closure: the History specialist's statement (``denied`` False) or
    the Literature specialist's denial of it, each glossing the closure in its own words (round-7 control F1)."""
    g = {"kind": "specialist_inference", "certainty": "probable"}
    closed = {"op": "var", "name": "closed_1961"}
    fact = {"op": "not", "arg": closed} if denied else closed
    then = "sunday_imagined" if denied else "route_sealed"
    return {"problem": {"ir_version": "1.0", "problem_id": f"p7c-{claim_id}", "request_id": "req-p7c", "claim_id": claim_id, "query": "entailment",
                        "symbols": [{"name": "closed_1961", "sort": "Bool", "meaning": meaning, "grounding": g},
                                    {"name": then, "sort": "Bool", "meaning": "the poem's Sunday is imagined" if denied else "the main route out was sealed", "grounding": g}],
                        "premises": [{"id": "pr", "expr": fact, "label": "the sector border was not closed on 13 August 1961" if denied else "East German forces closed that route",
                                      "grounding": g, "materiality": "material"},
                                     {"id": "link", "expr": {"op": "implies", "left": fact, "right": {"op": "var", "name": then}}, "label": "so", "grounding": g,
                                      "materiality": "material"}],
                        "conclusion": {"id": "concl", "expr": {"op": "var", "name": then}, "label": "the consequence", "grounding": None, "materiality": "material"}},
            "interpretation": {"reading": "the closure, stated or denied", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}


def _p7c_with_denial():
    """hi-p7c and lit-p7c on one hub task (round 7's material), the Literature reply adding a denial of the closure the
    History specialist dates; each closure claim translated as above, every other claim outside the replay's scope."""
    import json as _json

    from epinoic_logic.integrity import AgentRole as _Role
    from epinoic_logic.translate.contracts import SpecialistReport
    from epinoic_logic.translate.outcome import verify_claim
    from epinoic_logic.translate.pipeline import Translator
    from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.channel.bus import CLAIM_OUT_OF_SCOPE

    from . import r7_support as R

    denial = " The sector border was not closed on 13 August 1961, so the poem's Sunday is imagined."
    texts = {"lit-p7c": R.SPEC["lit-p7c"]["response_text"].replace("in the words they keep.", "in the words they keep." + denial, 1)}
    fixtures = {"In the early hours of 13 August 1961": "East German forces closed the sector route on 13 August 1961",
                "was not closed on 13 August 1961": "East German forces closed the route in the early hours of 13 August 1961"}

    def verify(claim, report, task=None):
        for words, meaning in fixtures.items():
            if words in claim.claim_text:
                obj = _closure_fixture(claim.claim_id, meaning, denied=words.startswith("was not"))
                obj["problem"]["request_id"] = claim.request_id
                provider = FixtureTranslationProvider({claim.claim_id: [_json.dumps(obj), _json.dumps(obj)]})
                return verify_claim(claim, report, Translator(provider), config=R.CFG, signing_key=R.KEY)
        return CLAIM_OUT_OF_SCOPE

    hub = RouterHub(signing_key=R.KEY, config=R.CFG)
    ch = hub.open_task(R.plan_for("p7c"))
    ch.verify_claim_fn = verify
    delivered, receipts = {}, {}
    for it in R.members("p7c"):
        tid, docs = it["task_id"], R.supplied(it)
        if it.get("peer_of"):
            pm = delivered[it["peer_of"]]
            fwd, _frc = ch.relay("router", _Role.ROUTER, it["agent_id"], _Role.SPECIALIST, SpecialistReport.model_validate(pm.payload), in_reply_to=pm.message_id)
            docs = [*docs, SuppliedText(document_id=f"peer:{it['peer_of']}", text=fwd.payload["original_response"])]
        m, _req, _rq = hub.dispatch("p7c", it["agent_id"], it["question"], docs)
        reply, rc = hub.receive("p7c", m.message_id, texts.get(tid, it["response_text"]), agent_id=it["agent_id"], report_id=f"rep-{tid}-0")
        delivered[tid], receipts[tid] = reply, rc
    return ch, delivered, receipts


def test_r7_f1_f2_a_denial_between_peers_is_charged_and_must_be_disclosed():
    """Round-7 controls F1 and F2, which the round-7 glossary fix had turned into INT-CONFLICT-004 (the two glosses of the
    closure differ by 'sector' and 'in the early hours of'): the denial is INT-CONFLICT-001 on the Literature receipt, and
    a synthesis that carries both claims with no conflict record is INT-CONFLICT-002; with a record naming them, it is not."""
    from epinoic_logic.integrity import ConflictRecord, Synthesis, SynthesizedClaim
    from epinoic_logic.integrity import AgentRole as _Role
    from epinoic_logic.translate.contracts import sha256_text

    from .r7_support import COMB

    ch, delivered, receipts = _p7c_with_denial()
    hi = next(c for c in delivered["hi-p7c"].payload["claims"] if "In the early hours of 13 August 1961" in c["claim_text"])
    lit = next(c for c in delivered["lit-p7c"].payload["claims"] if "was not closed on 13 August 1961" in c["claim_text"])
    charged = [f for f in by_code(receipts["lit-p7c"].findings, "INT-CONFLICT-001") if {hi["claim_id"], lit["claim_id"]} <= set(f.claim_ids)]
    assert charged and charged[0].severity == "error", codes(receipts["lit-p7c"].findings)
    assert "INT-CONFLICT-004" not in codes(receipts["lit-p7c"].findings) and "INT-GLOSSARY-005" not in codes(receipts["lit-p7c"].findings)

    def synthesis(sid, conflicts=()):
        claims = [SynthesizedClaim(claim_id="s1", text=hi["claim_text"], certainty="established", source_claim_ids=[hi["claim_id"]], transformation="carried"),
                  SynthesizedClaim(claim_id="s2", text=lit["claim_text"], certainty="probable", source_claim_ids=[lit["claim_id"]], transformation="carried")]
        text = " ".join(c.text for c in claims)
        return Synthesis(synthesis_id=sid, request_id=ch.plan.request_id, task_id=ch.plan.task_id, combinator_agent_id=COMB,
                         source_report_ids=[delivered["hi-p7c"].payload["report_id"], delivered["lit-p7c"].payload["report_id"]], claims=claims, ledger=[],
                         text=text, text_sha256=sha256_text(text), created_at="2026-11-06T09:00:00Z", conflicts=list(conflicts))
    _m, rr = ch.relay(COMB, _Role.COMBINATOR, "router", _Role.ROUTER, synthesis("syn-f2"))
    [undisclosed] = by_code(rr.findings, "INT-CONFLICT-002")
    assert undisclosed.severity == "error" and {hi["claim_id"], lit["claim_id"]} <= set(undisclosed.claim_ids)
    record = ConflictRecord(conflict_id="k1", claim_ids=[hi["claim_id"], lit["claim_id"]], description="History dates the closure to 13 August 1961; Literature denies it")
    _m, rr = ch.relay(COMB, _Role.COMBINATOR, "router", _Role.ROUTER, synthesis("syn-f3", [record]))
    assert "INT-CONFLICT-002" not in codes(rr.findings)


def test_a_peers_glossary_warning_stays_on_the_peers_receipt():
    """Glossary noise (minor): bm-p8a's receipt carried eleven INT-GLOSSARY-005 warnings about pairs of the Economics
    specialist's claims, maa-p8b's the Physics specialist's. Here the History specialist's two claims gloss one symbol in two
    units (a real INT-GLOSSARY-005 on its own receipt); the Literature specialist's receipt, delivered after it on the same
    hub task with a translated claim of its own in the pool, carries no warning about that pair."""
    import json as _json

    from epinoic_logic.integrity import AgentRole as _Role
    from epinoic_logic.translate.contracts import SpecialistReport
    from epinoic_logic.translate.outcome import verify_claim
    from epinoic_logic.translate.pipeline import Translator
    from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.channel.bus import CLAIM_OUT_OF_SCOPE

    from . import r7_support as R

    def fixture(claim, meaning, value):
        g = {"kind": "specialist_inference", "certainty": "probable"}
        v = {"op": "var", "name": "flow_rate"}
        return {"problem": {"ir_version": "1.0", "problem_id": f"p7c-{claim.claim_id}", "request_id": claim.request_id, "claim_id": claim.claim_id,
                            "query": "consistency", "symbols": [{"name": "flow_rate", "sort": "Real", "meaning": meaning, "grounding": g}],
                            "premises": [{"id": "pr", "expr": {"op": "eq", "left": v, "right": {"op": "real", "value": value}}, "label": "the rate", "grounding": g,
                                          "materiality": "material"}]},
                "interpretation": {"reading": "a rate", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}

    served = {"The closure of the sector border on 13 August 1961": ("emigrants leaving per day", "2000"),
              "In the early hours of 13 August 1961": ("emigrants leaving per year", "200000")}
    added = " The sector border was not closed on 13 August 1961, so the poem's Sunday is imagined."

    def verify(claim, report, task=None):
        obj = None
        for words, (meaning, value) in served.items():
            if claim.claim_text.startswith(words):
                obj = fixture(claim, meaning, value)
        if "the poem's Sunday is imagined" in claim.claim_text:  # the Literature claim pooled beside them (no shared symbol)
            obj = _closure_fixture(claim.claim_id, "the sector border stayed open on 13 August 1961", denied=True)
            obj["problem"]["request_id"] = claim.request_id
            for sym in obj["problem"]["symbols"]:
                sym["name"] = sym["name"].replace("closed_1961", "border_open")
            obj = _json.loads(_json.dumps(obj).replace('"closed_1961"', '"border_open"'))
        if obj is None:
            return CLAIM_OUT_OF_SCOPE
        provider = FixtureTranslationProvider({claim.claim_id: [_json.dumps(obj), _json.dumps(obj)]})
        return verify_claim(claim, report, Translator(provider), config=R.CFG, signing_key=R.KEY)

    hub = RouterHub(signing_key=R.KEY, config=R.CFG)
    ch = hub.open_task(R.plan_for("p7c"))
    ch.verify_claim_fn = verify
    delivered, receipts = {}, {}
    for it in R.members("p7c"):
        tid, docs = it["task_id"], R.supplied(it)
        if it.get("peer_of"):
            pm = delivered[it["peer_of"]]
            fwd, _frc = ch.relay("router", _Role.ROUTER, it["agent_id"], _Role.SPECIALIST, SpecialistReport.model_validate(pm.payload), in_reply_to=pm.message_id)
            docs = [*docs, SuppliedText(document_id=f"peer:{it['peer_of']}", text=fwd.payload["original_response"])]
        m, _req, _rq = hub.dispatch("p7c", it["agent_id"], it["question"], docs)
        text = it["response_text"].replace("in the words they keep.", "in the words they keep." + added, 1) if tid == "lit-p7c" else it["response_text"]
        reply, rc = hub.receive("p7c", m.message_id, text, agent_id=it["agent_id"], report_id=f"rep-{tid}-0")
        delivered[tid], receipts[tid] = reply, rc
    hi_ids = {c["claim_id"] for c in delivered["hi-p7c"].payload["claims"]}
    lit_ids = {c["claim_id"] for c in delivered["lit-p7c"].payload["claims"]}
    assert {"h1.1", "h1.4"} <= set(ch.formalized) and any(c in ch.formalized for c in lit_ids)
    own = [f for f in by_code(receipts["hi-p7c"].findings, "INT-GLOSSARY-005") if set(f.claim_ids) <= hi_ids]
    assert own and "units" in own[0].message  # the History specialist's own pair, on its own receipt
    for f in by_code(receipts["lit-p7c"].findings, "INT-GLOSSARY-005"):
        assert set(f.claim_ids) & lit_ids, f.message  # never a pair of the peer's claims alone
