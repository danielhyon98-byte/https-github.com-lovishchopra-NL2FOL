"""``StemTextParser``: claims are offset substrings with stable ids, roles and materiality follow
docs/STEM_DESIGN.md section 9.2, notes and self-certifications never become material claims,
quotations are credited by the shared rule, and adversarial answers never raise out of the parser."""
from __future__ import annotations

import re
import time

import pytest

from epinoic_logic.adapters.base import AdapterError
from epinoic_logic.adapters.stem_specialist import CHECKS_ASSUMPTION, StemTextParser, stem_profile_key
from epinoic_logic.adapters.stem_specialist import parser as parser_module
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.channel.bus import _FOLDED_TAIL_RE
from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText
from epinoic_logic.translate.eligibility import decide_eligibility

OBSERVED = "The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². The acceleration is therefore 6.0 m s⁻²."
REQUEST = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."


def parse(text: str, subject: str = "Physics", request_text=None, supplied=(), mode: str = "sciences") -> SpecialistReport:
    return StemTextParser(mode=mode).parse_response(text, request_id="req", task_id="task", report_id="rep", subject=subject, task_type="short_answer",
                                                    supplied_texts=list(supplied), request_text=request_text)


def by_id(rep: SpecialistReport) -> dict:
    return {c.claim_id: c for c in rep.claims}


def assert_offset_substrings(rep: SpecialistReport) -> None:
    text = rep.original_response
    cursor = 0
    for c in rep.claims:
        assert c.claim_text and len(c.claim_text) <= 4000
        k = text.find(c.claim_text, cursor if not c.claim_id.endswith(".tail") else 0)
        assert k >= 0, c.claim_id
        cursor = k


# ----------------------------------------------------------------------------------------------------------- claims


@pytest.mark.parametrize("subject,text", [
    ("Physics", OBSERVED),
    ("Physics", "Using a = (v − u)/t:\na = (20 - 0)/4.0 = 6.0 m s⁻²\nThe acceleration is therefore 6.0 m s⁻²."),
    ("Physics", "The kinetic energy is given by\n\\[ E_k = \\frac{1}{2} m v^2 = \\frac{1}{2}(2.0)(3.0)^2 = 9.0\\,\\text{J} \\]\nThe mass therefore carries 9.0 J."),
    ("Mathematics: Analysis and Approaches", "We solve $x^2 - 5x + 6 = 0$: $(x-2)(x-3) = 0$, so $x = 2$ or $x = 3$."),
    ("Chemistry", "n(H₂O) = m/M = 36 g ÷ 18.0 g mol⁻¹ = 2.0 mol. For 2H₂ + O₂ → 2H₂O, ΔH = 2 × (−286 kJ mol⁻¹) = −572 kJ."),
    ("Physics", "**Part (a)**\nv = u + at = 0 + 9.8 × 3.0 = 29.4 m/s\n\n**Part (b)**\ns = ½at² = ½ × 9.8 × 3.0² = 44.1 m"),
    ("Computer Science", "| A | B | A AND B |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 0 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |"),
])
def test_claims_are_offset_substrings_and_the_original_is_verbatim(subject, text):
    mode = {"Computer Science": "computer_science"}.get(subject, "mathematics" if subject.startswith("Mathematics") else "sciences")
    rep = parse(text, subject, mode=mode)
    assert rep.original_response == text and rep.claims
    assert_offset_substrings(rep)
    letter = {"Computer Science": "c"}.get(subject, "m" if subject.startswith("Mathematics") else "s")
    assert all(re.fullmatch(rf"{letter}\d+\.\d+|{letter}\.tail", c.claim_id) for c in rep.claims), [c.claim_id for c in rep.claims]
    assert len({c.claim_id for c in rep.claims}) == len(rep.claims)


def test_ids_are_stable_and_shared_with_the_document():
    a, b = parse(OBSERVED, request_text=REQUEST), parse(OBSERVED, request_text=REQUEST)
    assert [(c.claim_id, c.claim_text) for c in a.claims] == [(c.claim_id, c.claim_text) for c in b.claims]
    doc = build_document(OBSERVED, REQUEST, "physics")
    assert [c.claim_id for c in a.claims] == [st.id for st in doc.statements]
    assert [c.claim_text for c in a.claims] == [doc.statement_text(st.id) for st in doc.statements]


def test_roles_and_materiality_of_a_derivation():
    rep = by_id(parse(OBSERVED, request_text=REQUEST))
    assert (rep["s1.1"].claim_role, rep["s1.1"].proposed_claim_kind) == ("evidence", "arithmetic")       # u = 0: a value bound to a symbol
    assert (rep["s1.2"].claim_role, rep["s1.2"].materiality) == ("quantitative", "supporting")          # the arithmetic step
    assert (rep["s1.3"].claim_role, rep["s1.3"].materiality) == ("quantitative", "material")            # the result
    assert any(a.startswith(CHECKS_ASSUMPTION) and "stem-eq-1" in a for a in rep["s1.2"].assumptions)


def test_a_law_with_no_numerals_is_factual_evidence():
    rep = by_id(parse("Using a = (v − u)/t:\na = (20 - 0)/4.0 = 5.0 m s⁻²"))
    assert (rep["s1.1"].claim_role, rep["s1.1"].proposed_claim_kind, rep["s1.1"].materiality) == ("evidence", "factual", "supporting")
    assert decide_eligibility(rep["s1.1"]).route_to == "evidence_service"
    assert rep["s1.2"].materiality == "material"  # the last chain of the part is its result


def test_every_part_has_a_material_result():
    rep = parse("**Part (a)**\nv = u + at = 0 + 9.8 × 3.0 = 29.4 m/s\n\n**Part (b)**\ns = ½at² = ½ × 9.8 × 3.0² = 44.1 m")
    material = [c for c in rep.claims if c.materiality == "material"]
    assert len(material) == 2 and all(c.claim_role == "quantitative" for c in material)


def test_a_bare_value_answer_is_a_material_quantitative_claim():
    rep = parse("The speed is 15 m/s.")
    assert [(c.claim_id, c.claim_role, c.materiality, c.claim_text) for c in rep.claims] == [("s1.1", "quantitative", "material", "The speed is 15 m/s.")]
    assert decide_eligibility(rep.claims[0]).eligible


def test_explanation_paragraph_point_link_and_assumption():
    rep = parse("Energy is conserved in the collision. This is because no external force acts on the system. Neglecting air resistance, the ball keeps its speed.")
    c = by_id(rep)
    assert (c["s1.1"].claim_role, c["s1.1"].materiality) == ("point", "material") and set(c["s1.1"].supporting_claim_ids) == {"s1.2", "s1.3"}
    # the reason supports the point and rests on nothing: no support cycle (round 7, CORE-STR-001)
    assert c["s1.2"].claim_role == "link" and c["s1.2"].supporting_claim_ids == [] and not CorePack._support_cycles(rep)
    assert c["s1.3"].claim_role == "analysis"
    assert rep.assumptions == ["Neglecting air resistance, the ball keeps its speed."]
    assert decide_eligibility(c["s1.1"]).eligibility_class.value == "PROPOSITIONAL_ARGUMENT"


def test_given_lines_and_taking_a_value_are_evidence():
    rep = by_id(parse("Given:\n- m = 2.0 kg\n- v = 3.0 m/s\nTaking g = 9.81 m s⁻², E = mgh."))
    assert (rep["s1.1"].claim_role, rep["s1.1"].claim_text) == ("structural", "Given:")
    assert [(rep[k].claim_role, rep[k].proposed_claim_kind, rep[k].claim_text) for k in ("s1.2", "s1.3")] == \
        [("evidence", "arithmetic", "m = 2.0 kg"), ("evidence", "arithmetic", "v = 3.0 m/s")]
    assert (rep["s1.4"].claim_role, rep["s1.4"].proposed_claim_kind) == ("evidence", "arithmetic")  # 'taking g = 9.81 ...' binds a value
    computed = by_id(parse("Given: m = 2.0 kg, v = 3.0 m/s.\nTaking g = 9.81 m s⁻², the energy is E = mgh = 2.0 × 9.81 × 5.0 = 98.1 J."))
    assert (computed["s1.1"].claim_role, computed["s1.2"].claim_role, computed["s1.2"].materiality) == ("evidence", "quantitative", "material")


def test_notes_and_self_certifications_never_become_material_claims():
    text = ("v = d/t = 120 m / 8 s = 15 m/s.\n\nI have checked all of these figures and they are accurate.\n\n"
            "All figures have been verified. Z3 proved the argument above.")
    rep = parse(text)
    others = [c for c in rep.claims if c.claim_role == "other"]
    assert len(others) == 3 and all(c.materiality == "supporting" for c in others)
    assert all(c.advisory_verification_status == "self-certified in the response text" for c in others)
    assert any("verification-status language" in u for u in rep.unresolved_issues)
    assert [c.claim_id for c in rep.claims if c.claim_role != "other"] == ["s1.1"]


def test_empty_text_raises_and_code_only_answers_yield_claims():
    for empty in ("", "   \n\t  "):
        with pytest.raises(AdapterError):
            parse(empty, "Computer Science", mode="computer_science")
    rep = parse("```python\ndef area(r):\n    return 3.14159 * r ** 2\n```", "Computer Science", mode="computer_science")
    assert [(c.claim_role, c.materiality) for c in rep.claims] == [("point", "material")]
    assert rep.claims[0].claim_text.startswith("```python")


def test_tables_and_data_lines_are_kept_as_claims():
    rep = parse("Results:\n\n| t / s | v / m s⁻¹ |\n|---|---|\n| 0 | 0 |\n| 1.0 | 9.8 |\n\nThe data [1, 2, 3] are the trials.", "Physics")
    kinds = [c.claim_text for c in rep.claims]
    assert any(t.startswith("| t / s") for t in kinds)
    assert_offset_substrings(rep)


def test_quotations_of_a_supplied_text_are_credited_and_inch_marks_are_not_quotations():
    doc = SuppliedText(document_id="doc-q", title="Data booklet", text="The acceleration of free fall near the Earth is about 9.8 m s⁻².")
    rep = parse('The booklet states "The acceleration of free fall near the Earth is about 9.8 m s⁻²". The ruler is 12" long.', supplied=[doc])
    refs = [r for c in rep.claims for r in c.source_refs]
    assert [(r.document_id, r.excerpt) for r in refs] == [("doc-q", "The acceleration of free fall near the Earth is about 9.8 m s⁻²")]
    assert not any("unbalanced quotation mark" in a for c in rep.claims for a in c.assumptions)


def test_an_uncredited_quotation_is_recorded_as_an_assumption():
    rep = parse('The textbook says "energy is conserved in every collision".')
    assert any("quotation with no supplied text to check it against" in a for a in rep.claims[0].assumptions)
    assert rep.claims[0].claim_role == "evidence"


def test_claims_beyond_the_limit_merge_into_the_tail_with_the_channel_text():
    text = "\n\n".join(f"Step {i}: x = {i}." for i in range(600))
    rep = parse(text, "Mathematics", mode="mathematics")
    assert len(rep.claims) == 512 and rep.claims[-1].claim_id == "m.tail" and rep.claims[-1].claim_role == "other"
    folded = [m for u in rep.unresolved_issues for m in [_FOLDED_TAIL_RE.search(u)] if m]
    assert folded and folded[0].group("tail") == "m.tail" and folded[0].group("limit") == "512"
    assert_offset_substrings(rep)


def test_a_long_statement_is_cut_to_the_contract_and_stays_a_substring():
    text = "The values are " + ", ".join(str(i) for i in range(3000)) + "."
    rep = parse(text)
    assert all(len(c.claim_text) <= 4000 for c in rep.claims)
    assert_offset_substrings(rep)


def test_profile_fallback_by_mode():
    assert stem_profile_key("Physics") == "physics" and stem_profile_key("Physics/Chemistry") == "stem"
    assert stem_profile_key("Underwater Basket Weaving", "mathematics") == "mathematics"
    assert stem_profile_key(None, "computer_science") == "computer_science" and stem_profile_key("History") == "stem"


def test_an_empty_document_falls_back_to_paragraph_claims(monkeypatch):
    real = parser_module.build_document

    def broken(text, request_text=None, profile="physics"):
        doc = real(text, request_text, profile)
        return doc.__class__(**{**doc.__dict__, "statements": (), "relations": ()})

    monkeypatch.setattr(parser_module, "build_document", broken)
    rep = parse("First paragraph x = 1.\n\nSecond paragraph.")
    assert [c.claim_id for c in rep.claims] == ["s1.1", "s2.1"] and [c.claim_text for c in rep.claims] == ["First paragraph x = 1.", "Second paragraph."]
    assert any("produced no statements" in u for u in rep.unresolved_issues)


def test_request_text_reaches_the_document_the_pack_reads():
    rep = parse("n = m/M = 36 g / 18 g mol⁻¹ = 2.0 mol", "Chemistry", request_text="Show that 36 g of water is 2.0 mol.")
    assert any("stem-tgt-1" in a for a in rep.claims[0].assumptions)
    relay = parse("n = m/M = 36 g / 18 g mol⁻¹ = 2.0 mol", "Chemistry")
    assert not any("stem-tgt" in a for a in relay.claims[0].assumptions)


# ------------------------------------------------------------------------------------------------- adversarial input


def _adversarial() -> list[tuple[str, str]]:
    return [
        ("malformed_latex", "$$\\begin{align} x &= \\frac{{{ \\left( \\sqrt[ \\text{ \\unknown{ $$ " * 200),
        ("unbalanced_brackets", "x = ((((((1 + 2) * [3 / {4 - 5) ] = 7)) " * 200),
        ("tower", "y = 10^10^10 = " + "10^" * 2000 + "10"),
        ("huge_exponent", "E = 1.5 × 10^99999999 J and m = 1e999999 kg. " * 50),
        ("digits_10000", "x = " + "7" * 10_000 + " m s⁻¹ and y = 2.0 × " + "9" * 10_000),
        ("nesting_500", "x = " + "(" * 500 + "1" + ")" * 500 + " = 1"),
        ("latex_nesting_500", "$" + "\\frac{" * 500 + "1" + "}{2}" * 500 + "$ = 1"),
        ("confusables", "а = 3 ν = 2 х = 5 Ꮪ = 1 ０ = １ x\u200d = 2 \u202ex = 3 " * 100),
        ("dollar_storm", "$" * 20_000),
        ("controls", "\x00\x01\x1b[31m x = 1 \ufffd \U0001f600 = 2 " * 300),
        ("relation_storm", "= " * 10_000),
        ("fences", "```\n" * 5_000),
        ("bars", "| " * 10_000 + "x = 1"),
    ]


@pytest.mark.parametrize("name,text", _adversarial(), ids=[n for n, _t in _adversarial()])
def test_adversarial_answers_never_raise_and_stay_bounded(name, text):
    clear_document_cache()
    t0 = time.perf_counter()
    rep = parse(text, "Mathematics: Analysis and Approaches", mode="mathematics")
    elapsed = time.perf_counter() - t0
    assert rep.original_response == text and rep.claims and len(rep.claims) <= 512
    assert all(c.claim_text and c.claim_text.strip() for c in rep.claims)
    assert_offset_substrings(rep)
    assert elapsed < 5.0, (name, elapsed)


def test_each_stem_branch_has_its_own_claim_id_letter():
    from epinoic_logic.adapters.stem_specialist import claim_id_for
    text = "$4a = 20 \\Rightarrow a = 5$"
    assert [c.claim_id for c in parse(text, "Physics").claims] == ["s1.1"]
    assert [c.claim_id for c in parse(text, "Mathematics: Analysis and Approaches", mode="mathematics").claims] == ["m1.1"]
    assert [c.claim_id for c in parse(text, "Computer Science", mode="computer_science").claims] == ["c1.1"]
    assert claim_id_for("s2.3", "mathematics") == "m2.3" and claim_id_for("s.tail", "computer_science") == "c.tail" and claim_id_for("s1.1") == "s1.1"
    maths = parse("Energy is conserved. This is because no force acts. So the total stays the same.", "Mathematics", mode="mathematics")
    m = by_id(maths)
    # the supports carry the branch's letter; the consequence rests on the claims before it and supports nothing (round 7)
    assert m["m1.1"].supporting_claim_ids == ["m1.2"] and m["m1.2"].supporting_claim_ids == [] and m["m1.3"].supporting_claim_ids == ["m1.1", "m1.2"]
    assert not CorePack._support_cycles(maths)


@pytest.mark.parametrize("text", ["√8 = 2√2", "$x = 5$", "2H₂ + O₂ → 2H₂O", "| A | B |\n|---|---|\n| 0 | 1 |"])
def test_maths_with_no_words_is_never_a_note(text):
    rep = parse(text, "Mathematics: Analysis and Approaches", mode="mathematics")
    assert all(c.claim_role != "other" for c in rep.claims), [(c.claim_id, c.claim_role) for c in rep.claims]


def test_a_note_clause_that_holds_maths_is_still_a_note():
    rep = parse("v = 5.0 m/s.\n\n(Figures from memory: g = 9.8.)")
    assert by_id(rep)["s2.1"].claim_role == "other" and by_id(rep)["s1.1"].claim_role != "other"


# ----------------------------------------------------------------------------------------- no evaluation (design 14)


def test_the_stem_branch_modules_evaluate_nothing():
    """The AST scan of the front end (``test_front_end_safety``) over the modules this stage adds or reads agent text in."""
    import ast
    from pathlib import Path

    from tests.stem.test_front_end_safety import FORBIDDEN_ATTRS, FORBIDDEN_NAMES

    root = Path(__file__).resolve().parents[2] / "src" / "epinoic_logic"
    files = [root / "adapters" / "stem_specialist" / "parser.py", root / "adapters" / "stem_specialist" / "__init__.py", root / "branches" / "stem_pack.py",
             root / "stem" / "si_reading.py", root / "stem" / "hub_hooks.py", root / "branches" / "quant.py"]
    banned_modules = {"pickle", "marshal", "subprocess", "importlib", "sympy", "ast", "os", "builtins", "code", "codeop", "runpy"}
    problems = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                problems.append(f"{f.name}:{node.lineno} {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
                problems.append(f"{f.name}:{node.lineno} .{node.attr}")
            elif isinstance(node, ast.Import) and any(a.name.split(".")[0] in banned_modules for a in node.names):
                problems.append(f"{f.name}:{node.lineno} import")
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] in banned_modules:
                problems.append(f"{f.name}:{node.lineno} from-import")
    assert problems == []
