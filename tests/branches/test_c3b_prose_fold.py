"""Round-10 leftover R10-STEM-REC6-14-SILENT, the prose fold (c3 bi-t16): 'Prophase falls most, from 52 to 12 cells, a fall to about one
third' crossed with no finding: the prose arithmetic reader read 'fell by a third' but not a fall TO a fraction of the earlier level.
It is now a fold change below one (new over old is the fraction), decided as the other fold changes are; a right fraction draws
nothing (controls)."""
from __future__ import annotations

import pytest

from epinoic_logic.branches.quant import extract_quant_checks
from epinoic_logic.engine import SolverConfig, verify

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def _statuses(text: str) -> list[tuple[str, str]]:
    return [(q.kind, verify(q.problem, CFG).status.value) for q in extract_quant_checks(text, request_id="r", claim_id="c")]


@pytest.mark.parametrize("text, expected", [
    ("Prophase falls most, from 52 to 12 cells, a fall to about one third.", [("fold_change", "COUNTEREXAMPLE")]),
    ("Output fell from 60 to 20 tonnes, a fall to one third.", [("fold_change", "ENTAILED")]),
    ("Exports fell to a quarter of their 2019 level, from 80 to 20 million dollars.", [("fold_change", "ENTAILED")]),
    ("Exports fell to a quarter of their 2019 level, from 80 to 40 million dollars.", [("fold_change", "COUNTEREXAMPLE")]),
])
def test_a_fall_to_a_fraction_of_the_earlier_level_is_a_fold_change(text, expected):
    assert _statuses(text) == expected


def test_the_slipped_fold_of_the_recorded_biology_answer_is_named_through_the_hub():
    from tests.channel.c3_core_support import _deliver
    question = ("Control roots: interphase 412, prophase 52, metaphase 14, anaphase 8, telophase 14. Roots grown in the extract: interphase 461, "
                "prophase 12, metaphase 21, anaphase 2, telophase 4. (d) Suggest, with reference to the data, how the extract might affect the cell cycle. [3]")
    item = {"task_id": "probe-fold", "subject": "Biology", "agent_id": "biology-specialist", "task_type": "short_answer", "question": question,
            "supplied_texts": [], "response_text": ""}

    def errors(sentence: str) -> list[str]:
        hub, _ch, _reply, rc = _deliver(item, None, "(d) " + sentence + " This suggests that fewer cells progress into mitosis.")
        hub.close()
        return [f.code for f in rc.findings if f.severity == "error" and f.code == "INT-SUBJ-001"]
    assert errors("Prophase falls most, from 52 to 12 cells, a fall to about one third, which") == ["INT-SUBJ-001"]
    assert errors("Prophase falls most, from 52 to 12 cells, a fall to under a quarter, which") == []
