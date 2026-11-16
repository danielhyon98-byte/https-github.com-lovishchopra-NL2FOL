"""Round-10 clearance (integrated round c3), handoff pass: the overseer's side of the items handed to the translator.

* Rule model-marks (the round's critical records on the mark-point tick): the gate reads the tick after a marking point of a model line
  as a mark annotation, as the translator's one reader does (``epinoic_logic.api.adapters.blank_model_marks``), so the correct ph-t16 is
  no self-certifying answer; a tick after a point about checking, or outside a model line, still keeps an answer from the fallback.
  The auditor's claim-occurrence rule (OVS-FID-001) reads a claim the STEM parser cut such a tick from as it reads one cut of "[1]".
* One reader of the writer's own words in quotation marks (overseer handoff 1(b)): ``checks.fidelity.own_text_quotations`` and
  ``own_model_quotations`` are the translator's reader (``own_text_spans``, ``own_model_spans``) with this module's normalisation.
* One display rule (overseer handoff 3b): rule composed-display asks the translator's exported ``claim_display_status``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.api.adapters import blank_model_marks, own_model_spans, own_text_spans
from epinoic_overseer.checks import normalise
from epinoic_overseer.checks.fidelity import own_model_quotations, own_text_quotations, strip_mark_annotations
from epinoic_overseer.meta_notes import self_certifying_sentences

#: The recorded answers, copied verbatim into the sub-project's own data (its tests read nothing above it: test_subproject_layout.py).
C3 = json.loads((Path(__file__).parent / "data" / "c3_handoff_material.json").read_text(encoding="utf-8"))["specialists"]


def test_the_gate_reads_the_ticks_of_a_model_line_as_marks():
    assert self_certifying_sentences(C3["ph-t16"]["response_text"]) == []
    kb = ("Model: Fission releases fast neutrons ✔. They collide with nuclei of the moderator and lose kinetic energy until they are slow ✔. "
          "Slow neutrons are much more likely to cause fission of uranium-235 nuclei, so the chain reaction is sustained ✔.")
    assert self_certifying_sentences(kb) == [] and "✔" not in blank_model_marks(kb)


@pytest.mark.parametrize("text", ["Model: I checked every value ✔.", "The treaty was signed in 1919 ✓.",
                                  "Model: The pressure rises ✔. All values verified ✔"])
def test_controls_a_tick_after_a_check_or_outside_a_model_line_keeps_the_answer_from_the_fallback(text):
    assert self_certifying_sentences(text) == ["paragraph 1"]


def test_the_auditor_reads_a_claim_cut_of_a_model_tick_as_occurring():
    text = C3["ph-t16"]["response_text"]
    unmarked = strip_mark_annotations(text)
    for claim in ("Model: A higher temperature means faster molecules, so their mean kinetic energy rises.",
                  "Model: T1 = 290 K; T2 = 308 K. P2 = P1 × T2/T1 = 3.0 × 10⁵ × 308/290 = 3.2 × 10⁵ Pa"):
        assert claim not in text and claim in unmarked, claim


@pytest.mark.parametrize("task", ["sp-t16", "ll-t16", "ec-t16", "ph-t16", "en-t16"])
def test_the_auditors_own_text_readers_are_the_translators_reader(task):
    text = C3[task]["response_text"]
    assert own_text_quotations(text) == {normalise(i.strip()) for _a, _b, i in own_text_spans(text) if i.strip()}
    assert own_model_quotations(text) == {normalise(i.strip()) for _a, _b, i in own_model_spans(text) if i.strip()}


def test_rule_composed_display_asks_the_translators_display_rule():
    import inspect

    from epinoic_overseer.checks import results
    assert "claim_display_status(" in inspect.getsource(results.composed_display_status)
