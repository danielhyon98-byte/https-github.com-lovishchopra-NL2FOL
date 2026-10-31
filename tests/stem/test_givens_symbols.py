"""ST-GIVEN-002 (stem_contradictory_givens): a symbol given a value ('Given: m = 2.0 kg') is bound again to another value in
the same part with no change marked. ST-SCOPE-002 (stem_symbol_conflict): one symbol stands for two different quantities
(the car's speed and the speed of sound, both v), the noun phrases before the bindings saying so. A rebinding in another
part, or one the answer marks as a change ('the new mass'), is no conflict.
"""
from __future__ import annotations

from .argdiag_hub import deliver, stem_flags, structural
from .. import argdiag_cases as C


def test_a_given_value_bound_again_is_st_given_002():
    rc = deliver("f05b_contradictory_givens_stem")
    [f] = structural(rc, "ST-GIVEN-002")
    assert f.severity == "warning" and f.defect == "stem_contradictory_givens" and "2.0 kg" in f.message and "3.0 kg" in f.message


def test_control_a_rebinding_in_another_part_is_clean():
    case = C.load_case("f05b_contradictory_givens_stem")
    parts = ("(a) Given: the trolley's mass is m = 2.0 kg and a = 1.5 m s⁻².\nUsing F = ma, F = 2.0 × 1.5 = 3.0 N.\n\n"
             "(b) In the second run the trolley's mass is m = 3.0 kg.\nUsing F = ma, F = 3.0 × 1.5 = 4.5 N.")
    assert not structural(deliver(case, answer=parts), "ST-GIVEN-002")


def test_a_given_bound_again_is_named_whatever_the_wording():
    # a Given is the problem's datum: binding it again is a contradiction even when the answer words it as a change
    case = C.load_case("f05b_contradictory_givens_stem")
    changed = case["answer"].replace("Later in the run the trolley's mass is m = 3.0 kg.", "A load is added, so the new mass is m = 3.0 kg.")
    assert structural(deliver(case, answer=changed), "ST-GIVEN-002")


def test_one_symbol_for_two_quantities_is_st_scope_002():
    rc = deliver("s06_stem_equivocation")
    [f] = structural(rc, "ST-SCOPE-002")
    assert f.severity == "warning" and f.defect == "stem_symbol_conflict" and "12 m s⁻¹" in f.message and "340 m s⁻¹" in f.message


def test_control_distinct_symbols_are_clean():
    assert stem_flags(deliver("s06c_control_distinct_symbols")) == []


def test_control_a_rebinding_the_answer_marks_as_a_change_is_no_symbol_conflict():
    case = C.load_case("s06_stem_equivocation")
    marked = case["answer"].replace("The speed of sound is v = 340 m s⁻¹.", "Next, the speed of sound is v = 340 m s⁻¹.")
    assert not structural(deliver(case, answer=marked), "ST-SCOPE-002")
