"""Round-8 clearance (integrated round c1), handoff fixer: where the arena's STEM mutations are placed and which codes name them (the
STEM fixer's handoff item 4; STEM-integration finding 25, minor).

* a figure inside code (a fenced block, an inline code span), inside a mark annotation ("M1", "(A1)", "[2]") or on a line that states a
  mark ("Provisional mark: 1–5 / 4") is no site: the breadth re-run had mutated '// 5' in a Python block (cs-1) and a mark range
  (cs-3), places the design never checks as working;
* a site inside a quotation of another text keeps its mutation, and INT-REQ-003 (the altered quotation the hub refutes; rule
  quoted-relation) names it beside the mutation's own code (c1 maa-p8b stem_wrong_unit, '"T = 0.63 s (2 s.f.)"');
* a term of a sum in brackets right after the value it forms keeps its mutation, and INT-SUBJ-004 (rule parenthetical-sum, a reading
  at warning severity) names it beside INT-SUBJ-001 (c1 ch-t14 stem_substitution, '7 on the left (1 + 6)');
* ``StemInjection.expected`` never changes (the round-7 test that pins every round-7 mutation to its own code reads it), and on the
  recorded rounds c1 and r7 every mutated text, expected code and marker is what it was: only the two c1 records and r7 maa-p7b's slip
  gain a site code."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from epinoic_logic.branches.registry import default_registry

from ..core_hostile import SHAPES, one, sweep

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import run_arena as ra  # noqa: E402
import stem_mutations as sm  # noqa: E402

ROUND8 = json.loads((Path(__file__).parents[1] / "fixtures" / "stem" / "round8" / "c1_answers.json").read_text(encoding="utf-8"))["answers"]
R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
RUNNER_Q = "A runner covers 120 m in 8.0 s. Calculate the average speed."


# ------------------------------------------------------------------------------------------------- no site in code or marks

@pytest.mark.parametrize("prefix", [
    "```python\nsteps = 120 / 8.0 // 5\n```\n",                 # a fenced block (cs-1: '// 5' inside a Python block)
    "The call `120 / 8.0 = 15.0` returns a float.\n",           # an inline code span
    "Provisional mark: 120 / 8.0 = 15 out of 20\n",              # a line that states a mark (cs-3: 'Provisional mark: 1–5 / 4')
])
def test_a_figure_in_code_or_a_mark_line_is_no_site(prefix):
    answer = prefix + "v = 120 m / 8.0 s = 15 m s⁻¹"
    for kind in sm.STEM_MUTATIONS:
        inj = sm.mutate_stem(answer, RUNNER_Q, kind)
        assert inj is not None, kind
        changed = next(i for i in range(len(answer)) if answer[i] != inj.text[i])
        assert changed >= len(prefix), (kind, inj.marker)  # the site moved past the code or the mark line
        assert inj.text[:len(prefix)] == prefix and not inj.site_codes


def test_a_mark_annotation_is_no_site():
    """'(M2)' beside an operator, with 2 a value of the request: the reading before the rule mutated it to '(M5)' (marker
    '12 (M5) × 1'); the site is now the request's 8.0 in the working."""
    answer = "a = 3 × 4 = 12 (M2) × 1\nv = 120 m / 8.0 s = 15 m s⁻¹"
    inj = sm.mutate_stem(answer, "A runner covers 120 m in 8.0 s, 2 laps. Calculate the average speed.", "stem_substitution")
    assert inj is not None and inj.marker == "120 m / 5.0 s" and "(M2)" in inj.text and "(M5)" not in inj.text


# ------------------------------------------------------------------------------------------------- codes that name a site by design

def test_a_site_inside_a_quotation_is_also_named_by_the_altered_quotation_code():
    answer = 'My period agrees with the Physics specialist\'s "v = 120 m / 8.0 s = 15 m s⁻¹" from the race.'
    inj = sm.mutate_stem(answer, RUNNER_Q, "stem_wrong_unit")
    assert inj is not None and inj.expected == ("ST-DIM-001", "ST-DIM-002") and inj.site_codes == ("INT-REQ-003",)
    assert ra.stem_variant(answer, RUNNER_Q, "stem_wrong_unit")[1] == "ST-DIM-001|ST-DIM-002|INT-REQ-003"
    plain = answer.replace('"', "")
    assert sm.mutate_stem(plain, RUNNER_Q, "stem_wrong_unit").site_codes == ()  # control: the same working unquoted


def test_a_term_of_a_bracketed_sum_after_its_value_is_also_named_by_the_reading_code():
    answer = "Oxygen: 7 on the left (1 + 6), so 4 + 3 = 7 on the right."
    inj = sm.mutate_stem(answer, "Balance it: 1 O₂ and 6 H₂O.", "stem_substitution")
    assert inj is not None and inj.expected == ("INT-SUBJ-001",) and inj.site_codes == ("INT-SUBJ-004",)
    assert ra.stem_variant(answer, "Balance it: 1 O₂ and 6 H₂O.", "stem_substitution")[1] == "INT-SUBJ-001|INT-SUBJ-004"
    # control: a bracket that opens a calculation is no such sum
    calc = "The uptake rises by (40 − 18) ÷ 18 × 100 = 122%."
    assert sm.mutate_stem(calc, "From 40 to 18 units.", "stem_substitution").site_codes == ()


@pytest.mark.parametrize("tid,kind,codes", [("ch-t14", "stem_substitution", ("INT-SUBJ-004",)), ("maa-p8b", "stem_wrong_unit", ("INT-REQ-003",))])
def test_the_two_c1_records_are_named_by_the_code_of_their_site(tid, kind, codes):
    a = ROUND8[tid]
    inj = sm.mutate_stem(a["response_text"], a["question"], kind)
    assert inj is not None and inj.site_codes == codes and not set(codes) & set(inj.expected)


def _stem(subject: str) -> bool:
    return default_registry().for_subject(subject)[0].key in sm.STEM_BRANCHES


def test_on_the_recorded_rounds_only_the_site_codes_change():
    """c1 and r7: every STEM mutation's text, expected codes and marker are those of the reading before the site rules (pinned by
    the round-7 test and the harness records); only c1 ch-t14 and maa-p8b and r7 maa-p7b's slip carry a site code."""
    with_codes = []
    for name, spec in (("c1", {t: a for t, a in ROUND8.items()}), ("r7", R7)):
        for tid, it in sorted(spec.items()):
            if not _stem(it.get("subject") or {"physics": "Physics"}.get(it.get("profile"), "Physics")):
                continue
            for kind in sm.STEM_MUTATIONS:
                inj = sm.mutate_stem(it["response_text"], it["question"], kind)
                if inj is not None and inj.site_codes:
                    with_codes.append((name, tid, kind, inj.site_codes))
    assert sorted(with_codes) == [("c1", "ch-t14", "stem_substitution", ("INT-SUBJ-004",)), ("c1", "maa-p8b", "stem_wrong_unit", ("INT-REQ-003",)),
                                  ("r7", "maa-p7b", "stem_arithmetic_slip", ("INT-REQ-003",))], with_codes


# ------------------------------------------------------------------------------------------------- the site readers are linear

def _entries(text: str):
    yield "mutate_stem (slip)", lambda: sm.mutate_stem(text, "Calculate 2 m and 3 s.", "stem_arithmetic_slip")
    yield "mutate_stem (unit)", lambda: sm.mutate_stem(text + " a = 2 m × 3 = 6 m", "Calculate 2 m and 3 s.", "stem_wrong_unit")
    yield "mutate_stem (substitution)", lambda: sm.mutate_stem(text + " a = 2 × 3 = 6", "Calculate 2 m and 3 s.", "stem_substitution")
    yield "sites", lambda: sm._Sites(text)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_site_readers(shape):
    """The site readers, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_entries, texts=one(shape))


@pytest.mark.parametrize("name,text", [
    ("unclosed quotation marks", '"a = 2 × 3 = 6 ' * 13_000),
    ("unclosed backticks", "`a = 2 × 3 = 6 " * 13_000),
    ("fences", "```\na = 2 × 3 = 6\n" * 10_000),
    ("bracketed sums", "7 on the left (1 + 6) and " * 7_000 + "a = 2 × 3 = 6"),
    ("mark annotations", "a = 2 × 3 = 6 (A1) M1 [2] " * 7_000),
    ("mark lines", "Provisional mark: 2 × 3 = 6\n" * 7_000 + "a = 2 × 3 = 6"),
])
def test_the_site_readers_are_linear_on_their_own_worst_inputs(name, text):
    t0 = time.process_time()
    for kind in sm.STEM_MUTATIONS:
        sm.mutate_stem(text, "Calculate 2 m and 3 s.", kind)
    assert time.process_time() - t0 < 5.0, name
