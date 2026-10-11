"""The report's own arithmetic, decided by the engine with no model involved, per subject pack."""
from epinoic_logic.branches import default_registry, extract_quant_checks
from epinoic_logic.branches.packs import BusinessPack, CorePack, EconomicsPack, PsychologyPack
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def status(problem):
    return verify(problem, CFG).status.value


def test_percent_fold_share_total_arithmetic():
    ok = {"Revenue rose from 200,000 to 260,000, an increase of 30 per cent.": "ENTAILED",
          "Revenue rose from 200,000 to 260,000, an increase of 45 per cent.": "COUNTEREXAMPLE",
          "Sales fell from 80 to 60 units, a fall of 25 per cent.": "ENTAILED",
          "Membership doubled from 1,200 to 2,400.": "ENTAILED",
          "Output trebled from 1,000 to 2,000 units.": "COUNTEREXAMPLE",
          "30 per cent of the 4,000 respondents, or 1,200, agreed.": "ENTAILED",
          "30 per cent of the 4,000 respondents, or 1,500, agreed.": "COUNTEREXAMPLE",
          "Fixed costs of 50,000 and variable costs of 30,000 gave a total of 80,000.": "ENTAILED",
          "Fixed costs of 50,000 and variable costs of 30,000 gave a total of 90,000.": "COUNTEREXAMPLE"}
    for sentence, expected in ok.items():
        checks = extract_quant_checks(sentence, request_id="r", claim_id="c")
        assert len(checks) == 1, sentence
        assert status(checks[0].problem) == expected, sentence


def report(subject, agent, text, roles=None):
    sents = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    claims = [ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id=agent, subject=subject, task_type="short_answer", claim_id=f"c{i}", claim_text=s.rstrip(".") + ".",
                          claim_role=(roles or {}).get(i, "analysis")) for i, s in enumerate(sents)]
    return SpecialistReport(report_id="rep", request_id="r", task_id="t", agent_id=agent, subject=subject, task_type="short_answer", original_response=text, response_sha256=sha256_text(text), created_at="2026-10-11T14:00:00Z", claims=claims)


def test_economics_elasticity_formal_check():
    good = report("Economics", "economics-specialist", "Quantity demanded fell by 10 per cent when price rose by 20 per cent, so the price elasticity of demand is 0.5.")
    bad = report("Economics", "economics-specialist", "Quantity demanded fell by 10 per cent when price rose by 20 per cent, so the price elasticity of demand is 2.")
    pack = EconomicsPack()
    g, b = pack.formal_checks(good), pack.formal_checks(bad)
    assert len(g) == 1 and status(g[0].problem) == "ENTAILED"
    assert len(b) == 1 and status(b[0].problem) == "COUNTEREXAMPLE"
    assert any(f.code == "EC-STR-002" for f in pack.checks(report("Economics", "economics-specialist", "Demand is elastic, so revenue falls. The price elasticity is high.", {1: "analysis"})))


def test_business_margin_formal_check():
    good = report("Business Management", "business-specialist", "With a profit of 50,000 on revenue of 250,000 the profit margin is 20 per cent.")
    bad = report("Business Management", "business-specialist", "With a profit of 50,000 on revenue of 250,000 the profit margin is 35 per cent.")
    pack = BusinessPack()
    assert status(pack.formal_checks(good)[0].problem) == "ENTAILED"
    assert status(pack.formal_checks(bad)[0].problem) == "COUNTEREXAMPLE"


def test_psychology_study_attribution_and_significance():
    rep = report("Psychology", "psychology-specialist", "Loftus and Palmer (1974) showed leading questions change speed estimates. The effect was significant.")
    codes = {f.code for f in PsychologyPack().checks(rep)}
    assert {"PS-SRC-001", "PS-STR-001"} <= codes


def test_chronology_formal_check_runs_for_every_subject():
    ok = report("History", "history-specialist", "The vote fell in November 1932, after the party had become the largest in July 1932.")
    bad = report("History", "history-specialist", "The vote fell in November 1931, after the party had become the largest in July 1932.")
    pack = CorePack()
    assert status([c for c in pack.formal_checks(ok) if c.kind == "chronology"][0].problem) == "ENTAILED"
    assert status([c for c in pack.formal_checks(bad) if c.kind == "chronology"][0].problem) == "COUNTEREXAMPLE"


def test_registry_routes_every_known_subject_and_falls_back():
    r = default_registry()
    assert r.for_subject("History HL")[0].key == "history"
    assert r.for_subject("English A: Language and Literature")[0].key == "english"
    assert r.for_subject("Psychology SL")[0].key == "psychology"
    assert r.for_subject("Economics")[0].key == "economics"
    assert r.for_subject("Business Management HL")[0].key == "business_management"
    assert r.for_subject("Physics")[0].key == "generic" and r.for_subject(None)[0].key == "generic"
    for key in r.keys():
        b = r.get(key)
        assert b.packs and b.packs[0].name == "core"
