"""The memoised StemDocument (docs/STEM_DESIGN.md, sections 4 and 9)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from epinoic_logic.stem import StemDocument, build_document, clear_document_cache, document_cache_info
from epinoic_logic.stem.limits import PROFILES, StemLimits
from epinoic_logic.stem.nodes import render

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "stem" / "corpus"
PROFILE_OF = {"Physics": "physics", "Chemistry": "chemistry", "Biology": "biology", "Environmental Systems and Societies": "ess",
              "Mathematics: Analysis and Approaches": "mathematics_aa", "Mathematics: Applications and Interpretation": "mathematics_ai"}
#: prose relations ('a rise of 20 per cent', 'doubled from 20 °C to 40 °C') are read by the branch stage (quant), not by the math front end
BRANCH_STAGE_FAULTS = {("stem-phys-009", "prose_percent_change"), ("stem-phys-026", "offset_scale_relative_change")}
#: warnings a correct answer may legitimately carry: notation outside the encodings, an unrecognised unit word
ALLOWED_ON_CORRECT = {"ST-UNDEC-001", "ST-UNIT-001", "ST-UNIT-002", "ST-SCOPE-001", "ST-CODE-001"}


def corpus_items() -> list[dict]:
    if not CORPUS.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CORPUS.glob("stem-*.json"))]


ITEMS = corpus_items()


def build(item: dict) -> StemDocument:
    return build_document(item["response_text"], item["question"], PROFILE_OF[item["subject"]])


# ---------------------------------------------------------------- memoisation

def test_memoised_by_text_request_and_profile():
    clear_document_cache()
    a = build_document("v = 5.0 m s⁻¹", "Find v.", "physics")
    assert build_document("v = 5.0 m s⁻¹", "Find v.", "physics") is a
    assert build_document("v = 5.0 m s⁻¹", "Find v.", PROFILES["physics"]) is a
    assert build_document("v = 5.0 m s⁻¹", "Find u.", "physics") is not a
    assert build_document("v = 5.0 m s⁻¹", "Find v.", "chemistry") is not a
    assert a.key[2] == "physics" and len(a.key[0]) == 64 and len(a.key[1]) == 64
    assert build_document("v = 5.0 m s⁻¹", None, "physics").key[1] == ""
    info = document_cache_info()
    assert info.hits >= 2 and info.maxsize == 64


def test_cache_is_lru_bounded():
    clear_document_cache()
    first = build_document("x = 0", None, "physics")
    for i in range(1, 70):
        build_document(f"x = {i}", None, "physics")
    assert document_cache_info().currsize == 64
    assert build_document("x = 0", None, "physics") is not first     # evicted, rebuilt
    clear_document_cache()
    assert document_cache_info().currsize == 0


def test_unknown_profile_is_a_wiring_fault():
    with pytest.raises(ValueError, match="unknown STEM profile"):
        build_document("x = 1", None, "history")


# ---------------------------------------------------------------- the document contract

def test_statement_texts_are_offset_substrings():
    text = "Given: m = 2.0 kg.\n\n(a) KE = ½mv² = ½ × 2.0 × 3.0² = 9.0 J\n- so v = 3.0 m s⁻¹.\n$$x = 1 \\\\ = 1$$"
    d = build_document(text, None, "physics")
    assert d.statements
    for st in d.statements:
        assert d.statement_text(st.id) == text[st.start:st.end] and d.statement(st.id) is st
    for rel in d.relations:
        assert all(d.statement(s) is not None for s in rel.statement_ids)
    for c in d.checks:
        assert d.check(c.check_id) is c and c in d.checks_for(c.statement_ids[0])
    assert d.check("stem-eq-999") is None


def test_document_views_and_accessors():
    text = "So v = 5.0 m s⁻¹. Then it stops."
    d = build_document(text, None, "physics")
    assert len(d.reading) == len(d.prose) == len(text)
    assert d.items and d.items[0].statement_id == "s1.1" and d.items_for("s1.1")
    assert d.relations_for("s1.1") and not d.relations_for("s1.2")
    assert d.findings_for("s1.1") == ()
    assert d.overflow == 0 and d.limits == StemLimits()


def test_request_reading():
    d = build_document("v = d/t = 100/9.58 = 10.4 m s⁻¹", "A runner covers d = 100 m in 9.58 s. Show that v is about 10 m s⁻¹.", "physics")
    req = d.request
    assert [b.symbol for b in req.bindings] == ["d"] and req.bindings[0].source == "request"
    assert any(render(n) == "9.58 [s]" for n, _a, _b in req.quantities)
    assert req.targets and req.text.startswith("A runner")


def test_observed_case_phys_001():
    item = json.loads((CORPUS / "stem-phys-001.json").read_text(encoding="utf-8")) if CORPUS.exists() else None
    if item is None:
        pytest.skip("corpus not present")
    d = build(item)
    eq = d.check("stem-eq-1")
    assert eq is not None and render(eq.left.node) == "(20 - 0) / 4.0" and render(eq.right.node) == "6.0 [m s⁻²]"
    assert d.statement_text(eq.statement_ids[0]).startswith("Using a = Δv/Δt")
    assert not [f for f in d.findings if f.severity != "info"]


# ---------------------------------------------------------------- the labelled corpus

@pytest.mark.skipif(not ITEMS, reason="corpus not present")
def test_corpus_builds_without_internal_failures_and_fast():
    clear_document_cache()
    t = time.perf_counter()
    for item in ITEMS:
        d = build(item)
        assert not [f for f in d.findings if f.code == "ST-INTERNAL-001"], item["id"]
        assert all(f.severity in ("info", "warning") for f in d.findings)
    assert time.perf_counter() - t < 5.0


@pytest.mark.skipif(not ITEMS, reason="corpus not present")
def test_every_fault_is_covered_by_a_planned_check_or_a_named_finding():
    missing = []
    for item in ITEMS:
        d = build(item)
        text = item["response_text"]
        for fault in item["gold"]["faults"]:
            a = text.index(fault["step"])
            b = a + len(fault["step"])
            covered = [r for r in d.relations if r.start < b and a < r.end and r.outcome in ("check", "undecided")]
            named = [f for f in d.findings if f.start < b and a < f.end]
            if not covered and not named and (item["id"], fault["kind"]) not in BRANCH_STAGE_FAULTS:
                missing.append((item["id"], fault["kind"]))
    assert missing == []


@pytest.mark.skipif(not ITEMS, reason="corpus not present")
def test_correct_answers_carry_no_dimension_algebra_chemistry_or_parse_warnings():
    noisy = []
    for item in ITEMS:
        if item["gold"]["faults"]:
            continue
        d = build(item)
        extra = sorted({f.code for f in d.findings} - ALLOWED_ON_CORRECT)
        if extra:
            noisy.append((item["id"], extra))
    assert noisy == []


# ---------------------------------------------------------------- bounds and failure modes

def test_response_bound_and_math_item_bound():
    d = build_document("x" * 400_001, None, "physics")
    assert [f.code for f in d.findings] == ["ST-LIM-001"] and not d.statements
    small = StemLimits(max_math_items=3)
    d = build_document("\n".join(f"x = {i}" for i in range(10)), None, "physics", limits=small)
    lim = [f for f in d.findings if f.code == "ST-LIM-002"]
    assert len(d.items) == 3 and lim and "7 math spans" in lim[0].message


def test_statement_bound_merges_into_the_tail():
    d = build_document(" ".join(f"Point {i} holds." for i in range(600)), None, "physics")
    assert len(d.statements) == 512 and d.statements[-1].id == "s.tail" and d.overflow == 89


def test_internal_failure_is_contained(monkeypatch):
    import epinoic_logic.stem.document as document

    def boom(*_a, **_k):
        raise RuntimeError("simulated")

    clear_document_cache()
    monkeypatch.setattr(document, "_build", boom)
    d = build_document("x = 1", None, "physics")
    assert [f.code for f in d.findings] == ["ST-INTERNAL-001"] and "RuntimeError" in d.findings[0].message
    assert not d.checks and not d.statements
    clear_document_cache()
