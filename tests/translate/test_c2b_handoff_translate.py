"""Round-9 clearance, second fix pass (c2b), handoff fixer: the translator's items the overseer fixer handed over.

* The task-record path of the c1 circularity test (the overseer's handoff 7; the merged c1 record, critical): the c1 circularity test
  serves its recorded translations WITHOUT the task record, while production's verifier and the arena harness pass it on
  (``run_arena.make_verify_fn``). Delivered through a verifier that takes ``task=<TaskRecord>``, as production's does, the three claims
  read: bi-t14 s1.2 withheld (INVALID_FORMALIZATION, E112: its "each quadrat is 1 m²" premise is a task setting no record states as
  such); bi-t14 s4.7 and ph-p8b s1.1 ENTAILED (their restating premises are figures the task record states for the quantity they name,
  which the transfer auditor reads as undecided data, OVS-TRN-011, a warning, so the receipt and the audit agree: the overseer's
  ``test_the_receipt_and_the_audit_agree_on_the_c1_step_checks_under_the_task_record`` pins that side).
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.channel.bus import CLAIM_OUT_OF_SCOPE
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from ..channel import c1_core_support as C1S
from ..core_hostile import SHAPES, one, sweep


def _with_the_task_record(translations: dict):
    """The c1 fixture verifier as production's runs it: the recorded translation served to its claim, the task record passed on."""
    def verify(claim, report, task=None):
        key = claim.claim_id if claim.claim_id in translations else next((k for k in translations if k.split("@")[0] == claim.claim_id.split("@")[0]), None)
        if key is None:
            return CLAIM_OUT_OF_SCOPE
        assert task is not None and task.text, "the hub hands the verifier the task record of the request"
        obj = json.loads(json.dumps(translations[key]))
        obj["problem"]["claim_id"] = claim.claim_id
        obj["problem"]["request_id"] = claim.request_id
        provider = FixtureTranslationProvider({claim.claim_id: [json.dumps(obj), json.dumps(obj)]})
        return verify_claim(claim, report, Translator(provider), config=C1S.CFG, signing_key=C1S.KEY, task=task)
    return verify


@pytest.mark.parametrize("task,claim,status", [
    ("bi-t14", "s1.2", S.INVALID_FORMALIZATION),
    ("bi-t14", "s4.7", S.ENTAILED),
    ("ph-p8b", "s1.1", S.ENTAILED),
])
def test_the_c1_circularity_claims_under_the_task_record(task, claim, status, monkeypatch):
    monkeypatch.setattr(C1S, "_fixture_verifier", _with_the_task_record)
    hub, _ch, _reply, rc = C1S.deliver(task, translations=C1S.C1["translations"][task])
    hub.close()
    o = next(o for o in rc.outcomes if o.claim_id.split("@")[0] == claim)
    assert o.display_status is status, (task, claim, o.display_status, o.translation.diagnostics)
    e112 = [d for d in o.translation.diagnostics if "E112" in d]
    assert bool(e112) is (status is S.INVALID_FORMALIZATION), e112
    if status is S.ENTAILED:
        assert o.verification is not None and o.verification.status is S.ENTAILED


# ============================================================================================ compound units (c1 translation fidelity #7)
def test_a_unit_of_three_words_is_read_whole_and_matches_its_declared_unit():
    """The overseer's handoff 10 (major): the quantity reader kept at most two unit words, so ess-t14's "2.5 × 10⁴ kJ m⁻² yr⁻¹" was read
    as "kJ m⁻²", a kg s^-2, and the audit named a dimension conflict with a symbol declared in kJ m⁻² yr⁻¹ (kg s^-3). The whole unit is
    read now (a two-word unit with one or two further words), and a two-word unit cut before a further unit word (an exponent, or
    "per") gives no dimension, never a conflict; a unit that really differs stays a conflict (control). A unit whose first word
    carries an exponent ("7.0 dm³ min⁻¹") is read as before (its first word), so bi-t15's recorded outcomes do not move."""
    from fractions import Fraction
    from epinoic_logic.translate.quantities import SourceText, declared_reading, figures_in, literal_matches
    declared = declared_reading("gross primary productivity of the grasses (kJ m⁻² yr⁻¹)")  # as the recorded c1 translation declares it
    assert declared.kind == "unit" and declared.dim == "kg s^-3"
    stated = figures_in(SourceText("task", "ess-t14", "The grassland's net primary productivity is 2.5 × 10⁴ kJ m⁻² yr⁻¹."))
    [f] = [x for x in stated if x.value == Fraction(25000)]
    assert (f.unit, f.unit_dim) == ("kJ m⁻² yr⁻¹", "kg s^-3")
    matches, conflicts = literal_matches(Fraction(25000), stated, declared)
    assert matches and not conflicts, conflicts
    # cut before a further unit word: no dimension, so no conflict (and no match by conversion either)
    cut = figures_in(SourceText("task", "t", "The yield is 2.5 × 10⁴ kJ m⁻² per year."))
    assert not literal_matches(Fraction(25000), cut, declared)[1]
    from epinoic_logic.translate.quantities import _figure_unit
    assert _figure_unit("7.0 dm³ min⁻¹", 3)[1:4] == ("dm³", Fraction(1, 1000), "volume")  # unchanged reading (bi-t15 s3.2)
    assert _figure_unit("5 kg per day", 1)[1] == "kg per day" and _figure_unit("4200 J kg⁻¹ K⁻¹", 4)[3] == "m^2 s^-2 K^-1"
    # control: a unit that really differs is still named
    other = figures_in(SourceText("task", "t", "The store holds 2.5 × 10⁴ kJ m⁻² in all."))
    _m, conflicts2 = literal_matches(Fraction(25000), other, declared)
    assert conflicts2 and "a kg s^-2; the symbol is declared in a unit of kg s^-3" in conflicts2[0]


def _quantity_entries(text: str):
    """The quantity reader's unit runs (rule compound-units) on the hostile text, alone and after a figure with unit words."""
    from epinoic_logic.translate.quantities import SourceText, declared_reading, figures_in
    units = "2.5 × 10⁴ " + "kJ m⁻² yr⁻¹ " * 1_500 + text
    yield "figures_in", lambda: figures_in(SourceText("task", "t", text))
    yield "figures_in (unit runs)", lambda: figures_in(SourceText("task", "t", units))
    yield "figures_in (per runs)", lambda: figures_in(SourceText("task", "t", "5 kg " + "per " * 4_000 + text))
    yield "declared_reading", lambda: declared_reading("(" + text[:4_000] + ")")


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_quantity_reader(shape):
    """Round-9 c2b class sweep (``translate.quantities``, whose unit reader now reads up to four unit words)."""
    assert not sweep(_quantity_entries, texts=one(shape))
