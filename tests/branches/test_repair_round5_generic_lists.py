"""Repair round 5, rerun-parser-safety-11 variant: an answer made mostly of list items or numbered parts is parsed by the
generic branch parser in time linear in its length. The lines and paragraphs are read once, the supports of the parts are
indexed, each part finds its eligible supports by bisection, and the role pass grows its list of earlier sentences in one
pass (bounded), where each part used to rebuild them over every unit. A short list keeps its claims, roles and supports."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches.generic_parser import GenericTextParser


def _parse(text: str):
    return GenericTextParser("economics-specialist").parse_response(text, request_id="req", task_id="task", report_id="rep", subject="Economics",
                                                                     task_type="short_answer")


@pytest.mark.parametrize("text", ["".join("(%s) z = 2\n" % ("iv" if i % 2 else "ix") for i in range(20_000)),
                                  "".join("%d. y = %d\n" % (i, i) for i in range(10_000)),
                                  "- x = 1\n" * 25_000], ids=["roman parts", "numbered parts", "list items"])
def test_a_long_answer_of_parts_or_items_is_parsed_in_linear_time(text):
    # about 150,000 to 220,000 characters: before the round the list items took about 18 s at 200,000 characters and the
    # numbered parts about 10 s at 150,000 (quadratic); now each takes a few seconds
    t0 = time.perf_counter()
    report = _parse(text)
    assert time.perf_counter() - t0 < 8.0 and report.claims


def test_control_a_short_list_keeps_its_claims_roles_and_supports():
    report = _parse("(a) Demand rose because incomes rose.\n(b) Supply fell, so prices rose.\n- One effect: firms raised output.\n- Another: imports grew.")
    assert [(c.claim_role, c.claim_text, [s.split("@")[0] for s in c.supporting_claim_ids]) for c in report.claims] == [
        ("point", "Demand rose because incomes rose.", []),
        ("point", "Supply fell, so prices rose.", ["g1.3", "g1.4"]),
        ("analysis", "One effect: firms raised output.", []),
        ("analysis", "Another: imports grew.", []),
    ]
