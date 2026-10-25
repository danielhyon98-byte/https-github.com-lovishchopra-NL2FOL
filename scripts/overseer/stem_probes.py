#!/usr/bin/env python3
"""STEM fault-class probes of the contained Overseer harness (``docs/OVERSEER_DESIGN.md`` section 31).

For every STEM fault class the harness plants ONE fault of that class into a COPY of a recorded STEM transfer of round
r7 (the round that holds STEM answers: physics, chemistry, biology, ESS, mathematics AA and AI, computer science, and
the physics-to-mathematics peer relay of group p7b) and replays it through ``RouterHub`` with the transfer auditor
attached. A recorded round is never written to: every plant is made on a one-task copy (``ovs_harness.mini_round``).

    PYTHONPATH=src python scripts/overseer/stem_probes.py --out DIR --rounds ROOT [--pack EXPORTED_PACK]

Two contexts per class, as the task names them:

* **receipt** (the STEM branch's own checks and the receipt): an ``answer`` probe changes the recorded answer's text
  (one replacement, or one added line of working) the way a specialist would get it wrong; the receipt must name the
  fault with the class's code on a claim that carries the planted text, and the overseer must agree with the receipt
  (no ``OVS-*`` error and no shadow disagreement beyond the untampered task's). A ``control`` probe writes the same
  statement correctly: no new receipt error and no ``OVS-*`` error. The receipt's own tampering for each class (a
  failure finding dropped, an ST code dropped, a check's status or statement rewritten, a STEM peer document altered)
  is the tampering suite's (``tamper.py``, the STEM cases T23a to T23z, T23aa to T23az and T23ba to T23bt on the recorded STEM targets), mapped to the class
  by :data:`TAMPER_CASES`.
* **translation** (a STEM translation): a ``translation`` probe writes a STEM translation of a delivered STEM claim
  (the round's recorded translation of that claim, re-keyed to the merged claim id by rule ``recorded-ids``, then given
  the class's fault: a converted unit, a weakened bound, a changed result, another given substituted, a formula
  rearranged, two quantities mixed) and serves it through the translator's real pipeline; the overseer's checks must
  name what a check decides (OVS-TRN-005), and a scripted overseer agent built only from the exported pack accuses
  the fault with the kind the pack prescribes: ``translation_ungrounded`` is CONFIRMED by its check, ``translation_unfaithful``
  (a meaning fault no check compares) stays UNRESOLVED for human review and is never refuted.

Outcomes per probe: ``named`` (the class's code names the planted claim, and for a receipt fault the overseer agrees),
``caught_unnamed`` (a new error or warning appears, but not the class's code on the planted claim: a later line named, a
neighbouring code), ``missed`` (nothing new), ``clean`` (a control with nothing new). A probe whose fault the STEM
translator's reading does not decide carries ``translator_gap`` (the reason, measured): its outcome is reported, and the
gate does not count it against the overseer, because the overseer checks transfers and receipts against the signed
results and cannot name a relation no check of the channel reads; those are the translator's own repair loop's.

Each probe also records what a BLIND dossier of the channel shows of the fault (``dossier``): the failed formal check
or the finding naming the planted claim, the ST code, the engine's computed and stated values, or the translation with
its result, so the measurement says whether an agent reading the dossier sees the evidence it needs.

Outputs under ``--out``: ``stem_probes.json`` (every probe, its observations and the class table) and
``stem_probes.md``. Nothing here evaluates agent text; keys are test constants; no network, no model.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ovs_harness as H  # noqa: E402

PROBES_FORMAT = "overseer-stem-probes/1.0"
ROUND = "r7"
#: The STEM fault classes, in the task's order (key -> what the class covers).
STEM_CLASSES: dict[str, str] = {
    "units": "units and conversions (including units given only in the task)",
    "precision": "significant figures and stated tolerances",
    "rounding": "rounding",
    "equations": "equations and rearrangements",
    "wrong_given": "substitutions of the wrong given",
    "arithmetic": "arithmetic slips",
    "formulas": "wrong formulas",
    "dimensions": "dimension errors",
    "givens": "contradictory givens",
    "boolean": "truth tables and Boolean items",
    "maths": "mathematical items (Mathematics AA and AI: functions, sequences, calculus, statistics, loans and finance)",
    "chemistry": "chemistry (moles, concentrations, pH, equations)",
    "physics": "physics working",
    "receipts": "STEM claim ids (s/m/c) and STEM receipts with their ST-* codes",
    "relay": "the STEM peer relay",
}
#: The tampering suite's STEM cases (``tamper.py``, T23a to T23z, T23aa to T23az and T23ba to T23bt on the recorded STEM targets r7/ph-t13, r7/maa-t13,
#: r7/p7b, r7/ch-t13 and r7/cs-t13, each on a copy that carries one of this module's planted faults) that tamper with the
#: receipt naming a fault of each class, and the suite's earlier cases that run on the STEM targets (T2b, T2d and T5d on
#: every STEM receipt; T7, T7b and T7c on the peer relay p7b).
TAMPER_CASES: dict[str, tuple[str, ...]] = {
    "units": ("T23b", "T23g", "T23ac", "T23bb"),
    "precision": ("T23k", "T23x", "T23az"),
    "rounding": ("T23i", "T23ad", "T23an", "T23as", "T23bh", "T23bt"),
    "equations": ("T23d", "T23af", "T23al", "T23au", "T23bo", "T23bp"),
    "wrong_given": ("T23f", "T23r", "T23v", "T23aa", "T23ai", "T23ap", "T23aq", "T23at", "T23aw", "T23bc", "T23bl"),
    "arithmetic": ("T23b", "T23u", "T23z", "T23bi", "T23bn"),
    "formulas": ("T23a", "T23p", "T23ao", "T23ay", "T23bd", "T23bj"),
    "dimensions": ("T23h", "T23ak"),
    "givens": ("T23c", "T23q", "T23t", "T23y", "T23ah", "T23av", "T23ax", "T23bg", "T23bm"),
    "boolean": ("T23b", "T23d", "T23i", "T23w", "T23aj", "T23be", "T23bs"),
    "maths": ("T23b", "T23d", "T23e", "T23f", "T23g", "T23ba", "T23bf", "T23bk", "T23bq", "T23br"),
    "chemistry": ("T23b", "T23d", "T23j", "T23ar"),
    "physics": ("T23e", "T23j", "T23k", "T23n", "T23ab"),
    "receipts": ("T23a", "T23l", "T23m", "T23q", "T2b", "T2d", "T5d", "T23ae", "T23ag", "T23am"),
    "relay": ("T7", "T7b", "T7c", "T23d", "T23o", "T23s"),
}


@dataclass(frozen=True)
class Probe:
    """One planted fault (or its correct control) on a copy of a recorded STEM task."""
    probe_id: str
    fault_class: str
    context: str                     # "receipt" or "translation"
    kind: str                        # "answer", "control" or "translation"
    stems: tuple[str, ...]           # the recorded tasks of the one-task copy
    key: str                         # the hub key of the channel
    description: str
    edits: tuple[tuple[str, str, str], ...] = ()   # (stem, old, new): exactly one occurrence of old is replaced
    marker: str = ""                 # text the planted claim carries
    expected: tuple[str, ...] = ()   # the codes that name the fault (any one of them)
    translation: Optional[tuple[str, str, str]] = None  # (stem, recorded claim id, plant name) of a translation probe
    agent_kind: Optional[str] = None
    agent_outcome: Optional[str] = None
    translator_gap: Optional[str] = None
    #: the words of the pack's own rule the scripted agent looks up to choose its kind (:func:`pack_kind`); ``agent_kind`` is
    #: then what the pack must give (STEM repair 1: the harness no longer hands the agent its kind)
    agent_rule: Optional[str] = None
    #: codes that must NOT appear (a correct conversion must not be graded an error)
    forbidden: tuple[str, ...] = ()


def _p(*a, **k) -> Probe:
    return Probe(*a, **k)


PH, PB, MA, MI, BI, ES, CS, CH = "ph-t13", "ph-p7b", "maa-t13", "mai-t13", "bi-t13", "ess-t13", "cs-t13", "ch-t13"
_CS_APPEND = "Next step: trace"
_CH_APPEND = "Two reminders."
_MA_APPEND = "Marks shown are a provisional allocation."
#: The answer and control probes of the receipt context (calibrated on the merged translator; each replacement occurs
#: exactly once in its recorded answer).
ANSWER_PROBES: tuple[Probe, ...] = (
    # units and conversions
    _p("units-conversion", "units", "receipt", "answer", (PB,), "p7b", "an explicit unit conversion written wrongly (h⁻¹ to s⁻¹, a factor of 100)",
       edits=((PB, "λ = 0.693/8.0 h = 0.087 h⁻¹", "λ = 0.693/8.0 h = 0.087 h⁻¹ = 0.0024 s⁻¹"),), marker="0.0024 s⁻¹", expected=("INT-SUBJ-001",)),
    _p("units-conversion-control", "units", "receipt", "control", (PB,), "p7b", "the same conversion written correctly",
       edits=((PB, "λ = 0.693/8.0 h = 0.087 h⁻¹", "λ = 0.693/8.0 h = 0.087 h⁻¹ = 0.000024 s⁻¹"),), marker="0.000024 s⁻¹"),
    _p("units-task-only", "units", "receipt", "answer", (PH,), PH, "a Given written in kΩ where the task states the internal resistance in ohms, in words only "
       "(STEM repair 1: the kΩ is read, so 500 Ω is set against the task's 0.50 ohm)",
       edits=((PH, "(a) [2]\nFor resistors", "Given: ε = 12 V, r = 0.50 kΩ.\n\n(a) [2]\nFor resistors"),), marker="r = 0.50 kΩ", expected=("INT-SUBJ-004", "INT-SUBJ-001")),
    _p("units-prefix", "units", "receipt", "answer", (PH,), PH, "a prefixed unit written in a line of working (0.50 mΩ for the 0.50 Ω internal resistance)",
       edits=((PH, "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "V = 12 V − (4.14 A × 0.50 mΩ) = 9.9 V"),), marker="0.50 mΩ", expected=("INT-SUBJ-004", "INT-SUBJ-001")),
    # significant figures and stated tolerances
    _p("precision-approx", "precision", "receipt", "answer", (PB,), "p7b", "a result stated '≈' outside its 5 per cent band (0.07 for 0.0866)",
       edits=((PB, "λ = 0.693/8.0 h = 0.087 h⁻¹", "λ = 0.693/8.0 h ≈ 0.07 h⁻¹"),), marker="≈ 0.07 h⁻¹", expected=("INT-SUBJ-001",)),
    _p("precision-approx-control", "precision", "receipt", "control", (PB,), "p7b", "a result stated '≈' within its band (0.09 for 0.0866)",
       edits=((PB, "λ = 0.693/8.0 h = 0.087 h⁻¹", "λ = 0.693/8.0 h ≈ 0.09 h⁻¹"),), marker="≈ 0.09 h⁻¹"),
    _p("precision-within-tolerance-control", "precision", "receipt", "control", (ES,), ES, "a last digit within the 1 per cent band of '=' (60.5 for 60.42)",
       edits=((ES, "= 60.4% decrease", "= 60.5% decrease"),), marker="60.5% decrease"),
    # rounding
    _p("rounding-restated", "rounding", "receipt", "answer", (PH,), PH, "a result rounded the wrong way when restated (16.4 W restated as 17 W)",
       edits=((PH, "= 16.4 W, so 16 W", "= 16.4 W\nThe power dissipated in the 6.0 Ω resistor is therefore 17 W."),), marker="therefore 17 W", expected=("INT-SUBJ-001",)),
    _p("rounding-restated-control", "rounding", "receipt", "control", (PH,), PH, "the same result rounded correctly (16 W)",
       edits=((PH, "= 16.4 W, so 16 W", "= 16.4 W\nThe power dissipated in the 6.0 Ω resistor is therefore 16 W."),), marker="therefore 16 W"),
    _p("rounding-inline", "rounding", "receipt", "answer", (PH,), PH, "the same wrong rounding written on the working line ('16.4 W, so 17 W'; rule inline-restatement)",
       edits=((PH, "= 16.4 W, so 16 W", "= 16.4 W, so 17 W"),), marker="so 17 W", expected=("INT-SUBJ-001",)),
    # equations and rearrangements
    _p("equations-rearrangement", "equations", "receipt", "answer", (PH,), PH, "ε = I(R + r) rearranged wrongly (I = ε(R + r))",
       edits=((PH, "ε = I(R + r), so I = ε/(R + r)", "ε = I(R + r), so I = ε(R + r)"),), marker="I = ε(R + r)", expected=("INT-SUBJ-001",)),
    _p("equations-factorising", "equations", "receipt", "answer", (MA,), MA, "a factorisation written wrongly (6t − 3t² = 0 as 3t(3 − t) = 0)",
       edits=((MA, "    3t(2 − t) = 0  M1", "    3t(3 − t) = 0  M1"),), marker="3t(3 − t) = 0", expected=("INT-SUBJ-001",)),
    # (STEM repair 11, rule part-condition: before, the request's '(a) … when t = 1' made t given everywhere, so part (b)'s equation had no
    # unknown and neither the factorisation nor the roots were checked; this probe carried that as a translator gap)
    # substitutions of the wrong given
    _p("wrong-given-value", "wrong_given", "receipt", "answer", (PH,), PH, "a wrong value substituted for the current the answer states (5.14 A for 4.14 A), the line's arithmetic right",
       edits=((PH, "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "V = 12 V − (5.14 A × 0.50 Ω) = 9.4 V"),), marker="5.14 A × 0.50 Ω", expected=("INT-SUBJ-001",)),
    _p("wrong-given-task-words", "wrong_given", "receipt", "answer", (PH,), PH, "the emf the task gives in words (12 V) substituted as 15 V (rule "
       "related-statements: the next line's failed substitution names the line that states the current it contradicts)",
       edits=((PH, "I = 12 V / 2.9 Ω = 4.1 A", "I = 15 V / 2.9 Ω = 5.2 A"),), marker="15 V / 2.9 Ω", expected=("INT-SUBJ-001",)),
    _p("wrong-given-other", "wrong_given", "receipt", "answer", (PH,), PH, "another given substituted (the external 2.4 Ω for the total 2.9 Ω), its arithmetic right "
       "(rule related-statements)",
       edits=((PH, "I = 12 V / 2.9 Ω = 4.1 A", "I = 12 V / 2.4 Ω = 5.0 A"),), marker="12 V / 2.4 Ω", expected=("INT-SUBJ-001",)),
    # arithmetic slips
    _p("arithmetic-slip", "arithmetic", "receipt", "answer", (PH,), PH, "2.4 Ω + 0.50 Ω written as 3.9 Ω",
       edits=((PH, "R + r = 2.4 Ω + 0.50 Ω = 2.9 Ω", "R + r = 2.4 Ω + 0.50 Ω = 3.9 Ω"),), marker="= 3.9 Ω", expected=("INT-SUBJ-001",)),
    # wrong formulas
    _p("formulas-power", "formulas", "receipt", "answer", (PH,), PH, "P = V/R used for the power, its arithmetic right and its unit W",
       edits=((PH, "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "P = V/R\nP = 9.93 V / 6.0 Ω = 1.66 W, so 1.7 W"),), marker="= 1.66 W", expected=("ST-DIM-001",)),
    _p("formulas-derivative", "formulas", "receipt", "answer", (MA,), MA, "a wrong derivative used consistently (a = 6 − 3t)",
       edits=((MA, "a = dv/dt = 6 − 6t  M1\n    At t = 1: a = 6 − 6(1) = 0\n    a = 0 m s⁻²", "a = dv/dt = 6 − 3t  M1\n    At t = 1: a = 6 − 3(1) = 3\n    a = 3 m s⁻²"),),
       marker="6 − 3t", expected=("INT-SUBJ-004",)),
    # (STEM repair 11, rule derivative: the derivative of the request's v(t) by the power rule, a warning since that dv/dt is the request's v is a
    # reading; before, every derivative was outside the encodings and this probe carried that as a translator gap)
    # dimension errors
    _p("dimensions-sum", "dimensions", "receipt", "answer", (PH,), PH, "a resistance added to a current (2.4 Ω + 0.50 A)",
       edits=((PH, "R + r = 2.4 Ω + 0.50 Ω = 2.9 Ω", "R + r = 2.4 Ω + 0.50 A = 2.9 Ω"),), marker="0.50 A", expected=("ST-DIM-002",)),
    # contradictory givens
    _p("givens-contradiction", "givens", "receipt", "answer", (PH,), PH, "a Given that contradicts the task (r = 0.40 Ω for the task's 0.50 ohm)",
       edits=((PH, "(a) [2]\nFor resistors", "Given: ε = 12 V, r = 0.40 Ω.\n\n(a) [2]\nFor resistors"),), marker="r = 0.40 Ω", expected=("INT-SUBJ-004",)),
    _p("givens-control", "givens", "receipt", "control", (PH,), PH, "a Given that agrees with the task",
       edits=((PH, "(a) [2]\nFor resistors", "Given: ε = 12 V, r = 0.50 Ω.\n\n(a) [2]\nFor resistors"),), marker="r = 0.50 Ω"),
    # truth tables and Boolean items
    _p("boolean-truth-table", "boolean", "receipt", "answer", (CS,), CS, "a truth table of A AND B with a wrong row (0, 1 gives 1)",
       edits=((CS, _CS_APPEND, "A check of the loop test as a truth table:\n\n| A | B | A AND B |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 1 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |\n\n" + _CS_APPEND),),
       marker="| 0 | 1 | 1 |", expected=("INT-SUBJ-001",)),
    _p("boolean-truth-table-control", "boolean", "receipt", "control", (CS,), CS, "the same truth table written correctly",
       edits=((CS, _CS_APPEND, "A check of the loop test as a truth table:\n\n| A | B | A AND B |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 0 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |\n\n" + _CS_APPEND),),
       marker="| 0 | 1 | 0 |"),
    _p("boolean-identity", "boolean", "receipt", "answer", (CS,), CS, "De Morgan's law written wrongly (NOT (A AND B) = NOT A AND NOT B)",
       edits=((CS, _CS_APPEND, "By De Morgan's law, NOT (A AND B) = NOT A AND NOT B.\n\n" + _CS_APPEND),), marker="NOT A AND NOT B", expected=("INT-SUBJ-001",)),
    _p("boolean-identity-control", "boolean", "receipt", "control", (CS,), CS, "De Morgan's law written correctly",
       edits=((CS, _CS_APPEND, "By De Morgan's law, NOT (A AND B) = NOT A OR NOT B.\n\n" + _CS_APPEND),), marker="NOT A OR NOT B"),
    _p("boolean-base", "boolean", "receipt", "answer", (CS,), CS, "a base conversion written wrongly (85 as 1010111 in binary)",
       edits=((CS, _CS_APPEND, "In binary, 85₁₀ = 1010111₂.\n\n" + _CS_APPEND),), marker="1010111₂", expected=("INT-SUBJ-001",)),
    _p("boolean-base-control", "boolean", "receipt", "control", (CS,), CS, "the same conversion written correctly",
       edits=((CS, _CS_APPEND, "In binary, 85₁₀ = 1010101₂.\n\n" + _CS_APPEND),), marker="1010101₂"),
    # mathematical items
    _p("maths-function", "maths", "receipt", "answer", (MA,), MA, "a function evaluated wrongly (a(1) = 6 − 6(1) = 1)",
       edits=((MA, "a = 6 − 6(1) = 0", "a = 6 − 6(1) = 1"),), marker="6 − 6(1) = 1", expected=("INT-SUBJ-001",)),
    _p("maths-calculus", "maths", "receipt", "answer", (MA,), MA, "an antiderivative written wrongly (∫3t² dt = 3t³)",
       edits=((MA, "∫3t² dt = t³", "∫3t² dt = 3t³"),), marker="∫3t² dt = 3t³", expected=("INT-SUBJ-001",)),
    _p("maths-definite-integral", "maths", "receipt", "answer", (MA,), MA, "a definite integral's arithmetic slipped ((12 − 8) − 0 = 5)",
       edits=((MA, "= (12 − 8) − 0 = 4", "= (12 − 8) − 0 = 5"),), marker="(12 − 8) − 0 = 5", expected=("INT-SUBJ-001",)),
    _p("maths-roots", "maths", "receipt", "answer", (MA,), MA, "a root stated wrongly (t = 0 or t = 3 for 3t(2 − t) = 0)",
       edits=((MA, "t = 0 or t = 2", "t = 0 or t = 3"),), marker="t = 3", expected=("INT-SUBJ-001", "ST-ALG-001")),
    # (STEM repair 11, rules part-condition and root-statement: the roots are checked against the equation they solve; before, a translator gap)
    _p("maths-sequence", "maths", "receipt", "answer", (MA,), MA, "an arithmetic sequence term written wrongly (u₅ = 3 + (5 − 1) × 4 = 21)",
       edits=((MA, _MA_APPEND, "An arithmetic sequence check: u₅ = 3 + (5 − 1) × 4 = 21\n\n" + _MA_APPEND),), marker="× 4 = 21", expected=("INT-SUBJ-001",)),
    _p("maths-sequence-control", "maths", "receipt", "control", (MA,), MA, "the same term written correctly (19)",
       edits=((MA, _MA_APPEND, "An arithmetic sequence check: u₅ = 3 + (5 − 1) × 4 = 19\n\n" + _MA_APPEND),), marker="× 4 = 19"),
    _p("maths-statistics", "maths", "receipt", "answer", (BI,), BI, "a mean computed wrongly ((18 + 27 + 40)/3 = 30)",
       edits=((BI, "an increase of 100% [1]", "an increase of 100% [1]\n\nMean uptake = (18 + 27 + 40)/3 = 30"),), marker="(18 + 27 + 40)/3 = 30", expected=("INT-SUBJ-001",)),
    _p("maths-statistics-control", "maths", "receipt", "control", (BI,), BI, "the same mean written correctly (28.3)",
       edits=((BI, "an increase of 100% [1]", "an increase of 100% [1]\n\nMean uptake = (18 + 27 + 40)/3 = 28.3"),), marker="(18 + 27 + 40)/3 = 28.3"),
    _p("maths-statistics-inline", "maths", "receipt", "answer", (BI,), BI, "the same wrong mean written on the line whose mark annotation closes the sentence "
       "before it ('... 100% [1] Mean uptake = (18 + 27 + 40)/3 = 30')",
       edits=((BI, "an increase of 100% [1]", "an increase of 100% [1] Mean uptake = (18 + 27 + 40)/3 = 30"),), marker="(18 + 27 + 40)/3 = 30",
       expected=("INT-SUBJ-001",)),
    _p("maths-statistics-inline-control", "maths", "receipt", "control", (BI,), BI, "the same mean written correctly on that line (28.3)",
       edits=((BI, "an increase of 100% [1]", "an increase of 100% [1] Mean uptake = (18 + 27 + 40)/3 = 28.3"),), marker="(18 + 27 + 40)/3 = 28.3"),
    _p("maths-finance-rate", "maths", "receipt", "answer", (MI,), MI, "a monthly rate written wrongly in a loans-and-finance item (0.036/12 = 0.03)",
       edits=((MI, "$0.036/12 = 0.003$", "$0.036/12 = 0.03$"),), marker="0.036/12 = 0.03", expected=("INT-SUBJ-001",)),
    _p("maths-finance-value", "maths", "receipt", "answer", (MI,), MI, "a compound-interest value written wrongly (4000(1.003)^60 as 4887.58)",
       # the second translator merge: the development branch's closed powers (docs/STEM_DESIGN.md section 33.1) decide 1.003^60, so the
       # cut value is checked and its fault named (before, a translator gap: a power beyond 12 was outside the encodings, ST-UNDEC-001)
       edits=((MI, "$= 4787.58\\ldots$ (A1)", "$= 4887.58\\ldots$ (A1)"),), marker="4887.58", expected=("INT-SUBJ-001",)),
    _p("maths-finance-own-model", "maths", "receipt", "answer", (MI,), MI, "a compound-interest value within the encodings written wrongly (4000(1.036)^11 as 5802.25)",
       edits=((MI, "$4000(1.036)^{11} = 5902.25$", "$4000(1.036)^{11} = 5802.25$"),), marker="5802.25", expected=("INT-SUBJ-001",)),
    # chemistry
    _p("chemistry-moles", "chemistry", "receipt", "answer", (CH,), CH, "an amount in moles computed wrongly (0.10 × 0.0500 = 0.050 mol)",
       edits=((CH, _CH_APPEND, "For example, n = cV = 0.10 mol dm⁻³ × 0.0500 dm³ = 0.050 mol of thiosulfate. " + _CH_APPEND),), marker="= 0.050 mol", expected=("INT-SUBJ-001",)),
    _p("chemistry-moles-control", "chemistry", "receipt", "control", (CH,), CH, "the same amount written correctly (0.0050 mol)",
       edits=((CH, _CH_APPEND, "For example, n = cV = 0.10 mol dm⁻³ × 0.0500 dm³ = 0.0050 mol of thiosulfate. " + _CH_APPEND),), marker="= 0.0050 mol"),
    _p("chemistry-concentration", "chemistry", "receipt", "answer", (CH,), CH, "a diluted concentration computed wrongly (0.19 mol dm⁻³ for 0.091)",
       edits=((CH, _CH_APPEND, "In the mixture, c = 0.10 mol dm⁻³ × 50.0 cm³ ÷ 55.0 cm³ = 0.19 mol dm⁻³. " + _CH_APPEND),), marker="= 0.19 mol dm⁻³", expected=("INT-SUBJ-001",)),
    _p("chemistry-ph", "chemistry", "receipt", "answer", (CH,), CH, "a pH computed wrongly (−log₁₀(0.10) = 2)",
       edits=((CH, _CH_APPEND, "For the acid alone, pH = −log₁₀(0.10) = 2. " + _CH_APPEND),), marker="−log₁₀(0.10) = 2", expected=("INT-SUBJ-001",)),
    _p("chemistry-equation", "chemistry", "receipt", "answer", (CH,), CH, "an unbalanced equation (Na₂S₂O₃ + HCl → 2NaCl + SO₂ + S + H₂O)",
       edits=((CH, _CH_APPEND, "The reaction is Na₂S₂O₃ + HCl → 2NaCl + SO₂ + S + H₂O. " + _CH_APPEND),), marker="Na₂S₂O₃ + HCl", expected=("INT-SUBJ-001",)),
    _p("chemistry-equation-control", "chemistry", "receipt", "control", (CH,), CH, "the same equation balanced",
       edits=((CH, _CH_APPEND, "The reaction is Na₂S₂O₃ + 2HCl → 2NaCl + SO₂ + S + H₂O. " + _CH_APPEND),), marker="Na₂S₂O₃ + 2HCl"),
    # physics working
    _p("physics-working", "physics", "receipt", "answer", (PH,), PH, "a line of physics working slipped (P = (9.93 V)²/6.0 Ω = 14.6 W)",
       edits=((PH, "P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "P = (9.93 V)² / 6.0 Ω = 14.6 W, so 15 W"),), marker="= 14.6 W", expected=("INT-SUBJ-001",)),
    _p("physics-decay", "physics", "receipt", "answer", (PB,), "p7b", "a decay prediction slipped (1600 × (1/2)⁴ = 200 counts min⁻¹; 'counts' is read as a count)",
       edits=((PB, "(1/2)⁴ = 100 counts min⁻¹", "(1/2)⁴ = 200 counts min⁻¹"),), marker="= 200 counts min⁻¹", expected=("INT-SUBJ-001",)),
    # STEM claim ids and receipts: the receipt of a fault with an ST code and the claim ids it names (tampering: TAMPER_CASES)
    _p("receipts-undecided", "receipts", "receipt", "answer", (MA,), MA, "a relation outside the encodings (a factorial), named undecided on its m claim",
       edits=((MA, _MA_APPEND, "The number of orderings is 5! = 120.\n\n" + _MA_APPEND),), marker="5! = 120", expected=("ST-UNDEC-001",)),
    _p("receipts-undefined", "receipts", "receipt", "answer", (MA,), MA, "an undefined expression (a division by zero), named on its m claim",
       edits=((MA, _MA_APPEND, "Note that 6/0 = 0 is undefined here.\n\n" + _MA_APPEND),), marker="6/0 = 0", expected=("ST-UNDEF-001",)),
    # STEM repair 1 (the independent test's plants, each on the class whose cause it found)
    _p("units-prefixed-ohm", "units", "receipt", "answer", (PH,), PH, "a prefixed ohm converted wrongly (2.4 Ω = 0.024 kΩ)",
       edits=((PH, "R = 2.4 Ω (the external resistance)", "R = 2.4 Ω = 0.024 kΩ (the external resistance)"),), marker="0.024 kΩ", expected=("INT-SUBJ-001",)),
    _p("units-prefixed-ohm-control", "units", "receipt", "control", (PH,), PH, "the same conversion written correctly (2.4 Ω = 0.0024 kΩ): kΩ is one unit",
       edits=((PH, "R = 2.4 Ω (the external resistance)", "R = 2.4 Ω = 0.0024 kΩ (the external resistance)"),), marker="0.0024 kΩ"),
    _p("formulas-wrong-dimension", "formulas", "receipt", "answer", (PB,), "p7b", "a wrong formula whose result has the wrong dimension (λ = ln 2 × T½ = 0.693 × 8.0 h, "
       "stated in h⁻¹)",
       edits=((PB, "T½ = ln 2/λ, so λ = ln 2/T½\nλ = 0.693/8.0 h = 0.087 h⁻¹", "λ = ln 2 × T½\nλ = 0.693 × 8.0 h = 5.5 h⁻¹"),), marker="0.693 × 8.0 h = 5.5 h⁻¹",
       expected=("ST-DIM-001",)),
    _p("dimensions-bare-factor", "dimensions", "receipt", "answer", (PB,), "p7b", "a bare number beside one quantity, the result in the wrong dimension "
       "(1 / 0.087 h⁻¹ = 11.5 h⁻¹)",
       edits=((PB, "λ = 0.693/8.0 h = 0.087 h⁻¹", "λ = 0.693/8.0 h = 0.087 h⁻¹\nThe mean life is 1 / 0.087 h⁻¹ = 11.5 h⁻¹."),), marker="= 11.5 h⁻¹",
       expected=("ST-DIM-001",)),
    _p("dimensions-bare-factor-control", "dimensions", "receipt", "control", (PB,), "p7b", "the same line in the right dimension (11.5 h)",
       edits=((PB, "λ = 0.693/8.0 h = 0.087 h⁻¹", "λ = 0.693/8.0 h = 0.087 h⁻¹\nThe mean life is 1 / 0.087 h⁻¹ = 11.5 h."),), marker="= 11.5 h."),
    _p("receipts-combination", "receipts", "receipt", "answer", (MA,), MA, "a combination written ⁵C₂, named undecided on its m claim",
       edits=((MA, _MA_APPEND, "The number of ways to choose 2 of the 5 values is ⁵C₂ = 10.\n\n" + _MA_APPEND),), marker="⁵C₂ = 10", expected=("ST-UNDEC-001",)),
    _p("receipts-combination-ascii", "receipts", "receipt", "answer", (MA,), MA, "a combination written 5C2, named undecided on its m claim",
       edits=((MA, _MA_APPEND, "The number of ways to choose 2 of the 5 values is 5C2 = 10.\n\n" + _MA_APPEND),), marker="5C2 = 10", expected=("ST-UNDEC-001",)),
    _p("receipts-combination-function", "receipts", "receipt", "answer", (MA,), MA, "a combination written C(5, 2), named undecided on its m claim",
       edits=((MA, _MA_APPEND, "The number of ways to choose 2 of the 5 values is C(5, 2) = 10.\n\n" + _MA_APPEND),), marker="C(5, 2) = 10", expected=("ST-UNDEC-001",)),
    _p("rounding-stated-place", "rounding", "receipt", "answer", (ES,), ES, "a result restated to the nearest whole number, rounded the wrong way (60.4% as 61%)",
       edits=((ES, "= 60.4% decrease [1]", "= 60.4% decrease [1]\nTo the nearest whole number, the decrease is 61%."), (ES, "The outlet is also easy", "The outlet is easy"),
              (ES, "Upgrading is also costly", "Upgrading is costly")), marker="the decrease is 61%", expected=("INT-SUBJ-001",)),
    _p("rounding-stated-place-control", "rounding", "receipt", "control", (ES,), ES, "the same restatement rounded the right way (60%)",
       edits=((ES, "= 60.4% decrease [1]", "= 60.4% decrease [1]\nTo the nearest whole number, the decrease is 60%."), (ES, "The outlet is also easy", "The outlet is easy"),
              (ES, "Upgrading is also costly", "Upgrading is costly")), marker="the decrease is 60%"),
    _p("wrong-given-prose", "wrong_given", "receipt", "answer", (PH,), PH, "prose working substitutes another given (the change of the external resistance starts "
       "from the total 2.9 Ω)",
       edits=((PH, "rises from 2.4 Ω to 4.0 Ω", "rises from 2.9 Ω to 4.0 Ω"),), marker="rises from 2.9 Ω", expected=("INT-SUBJ-004",)),
    _p("wrong-given-prose-control", "wrong_given", "receipt", "control", (PH,), PH, "the same change written from the external resistance (2.40 Ω)",
       edits=((PH, "rises from 2.4 Ω to 4.0 Ω", "rises from 2.40 Ω to 4.0 Ω"),), marker="rises from 2.40 Ω"),
    _p("arithmetic-table-change", "arithmetic", "receipt", "answer", (BI,), BI, "a change between two rows of the supplied table written wrongly in prose (an increase of "
       "24 for 80 − 58)",
       edits=((BI, "an increase of 22 mm³ per g per hour", "an increase of 24 mm³ per g per hour"),), marker="an increase of 24 mm³", expected=("INT-SUBJ-004",)),
    _p("arithmetic-table-change-control", "arithmetic", "receipt", "control", (BI,), BI, "the same change written to another precision (22.0)",
       edits=((BI, "an increase of 22 mm³ per g per hour", "an increase of 22.0 mm³ per g per hour"),), marker="an increase of 22.0 mm³"),
    _p("givens-task-words", "givens", "receipt", "answer", (PH,), PH, "a Given that contradicts the emf the task states in words (ε = 9.0 V for 'emf 12 V')",
       edits=((PH, "(a) [2]\nFor resistors", "Given: ε = 9.0 V.\n\n(a) [2]\nFor resistors"),), marker="ε = 9.0 V", expected=("INT-SUBJ-004",)),
    _p("givens-task-words-control", "givens", "receipt", "control", (PH,), PH, "a Given that agrees with the emf the task states in words",
       edits=((PH, "(a) [2]\nFor resistors", "Given: ε = 12 V.\n\n(a) [2]\nFor resistors"),), marker="ε = 12 V"),
    _p("formulas-consistent", "formulas", "receipt", "answer", (PH,), PH, "a wrong formula used consistently (V = ε + Ir), its own line's arithmetic right",
       edits=((PH, "V = ε − Ir\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "V = ε + Ir\nV = 12 V + (4.14 A × 0.50 Ω) = 14.1 V"),), marker="= 14.1 V",
       expected=("INT-SUBJ-001",)),
    # the STEM peer relay
    _p("relay-misquote", "relay", "receipt", "answer", ("ph-p7b", "maa-p7b"), "p7b", "the mathematics specialist misquotes the physics specialist's corrected rate (1700 for 1600)",
       edits=(("maa-p7b", "“t = 0 h: 1620 − 20 = 1600 ± 32 counts min⁻¹”", "“t = 0 h: 1620 − 20 = 1700 ± 32 counts min⁻¹”"),), marker="1620 − 20 = 1700",
       expected=("INT-REQ-003", "CORE-SRC-003", "INT-SUBJ-001")),
) + (
    # STEM repair 2 (design section 33): the independent test's plants and their controls, each on the class whose cause it found.
    # Integer remainders and quotients written in words or signs, and verbal arithmetic, are read whole: correct work holds (controls),
    # a slip is named; a relation written partly in words, or a relation sign no span reads, is named unchecked (ST-PARSE-001).
    _p("arithmetic-mod-control", "arithmetic", "receipt", "control", (CS,), CS, "a remainder written with the word mod, correct (17 mod 5 = 2)",
       edits=((CS, _CS_APPEND, "As a check, 17 mod 5 = 2.\n\n" + _CS_APPEND),), marker="17 mod 5 = 2"),
    _p("arithmetic-div-control", "arithmetic", "receipt", "control", (CS,), CS, "an integer quotient written with the word div, correct (17 div 5 = 3)",
       edits=((CS, _CS_APPEND, "As a check, 17 div 5 = 3.\n\n" + _CS_APPEND),), marker="17 div 5 = 3"),
    _p("arithmetic-floor-division-control", "arithmetic", "receipt", "control", (CS,), CS, "a floor division written //, correct (17 // 5 = 3)",
       edits=((CS, _CS_APPEND, "As a check, 17 // 5 = 3.\n\n" + _CS_APPEND),), marker="17 // 5 = 3"),
    _p("arithmetic-percent-mod-control", "arithmetic", "receipt", "control", (CS,), CS, "a remainder written with Python's %, correct (17 % 5 = 2)",
       edits=((CS, _CS_APPEND, "As a check, 17 % 5 = 2.\n\n" + _CS_APPEND),), marker="17 % 5 = 2"),
    _p("arithmetic-mod-slip", "arithmetic", "receipt", "answer", (CS,), CS, "a remainder written with the word mod, slipped (17 mod 5 = 3)",
       edits=((CS, _CS_APPEND, "As a check, 17 mod 5 = 3.\n\n" + _CS_APPEND),), marker="17 mod 5 = 3", expected=("INT-SUBJ-001",)),
    _p("arithmetic-quotient-remainder", "arithmetic", "receipt", "answer", (CS,), CS, "a quotient stated with a wrong remainder (17 ÷ 5 = 3 remainder 3)",
       edits=((CS, _CS_APPEND, "As a check, 17 ÷ 5 = 3 remainder 3.\n\n" + _CS_APPEND),), marker="3 remainder 3", expected=("INT-SUBJ-001",)),
    _p("arithmetic-quotient-remainder-control", "arithmetic", "receipt", "control", (CS,), CS, "the same quotient and remainder written correctly (3 remainder 2)",
       edits=((CS, _CS_APPEND, "As a check, 17 ÷ 5 = 3 remainder 2.\n\n" + _CS_APPEND),), marker="3 remainder 2"),
    _p("arithmetic-verbal-control", "arithmetic", "receipt", "control", (MA,), MA, "verbal arithmetic, correct (3 times 4 = 12: never read as '4 = 12')",
       edits=((MA, _MA_APPEND, "So 3 times 4 = 12.\n\n" + _MA_APPEND),), marker="3 times 4 = 12"),
    _p("arithmetic-verbal-slip", "arithmetic", "receipt", "answer", (MA,), MA, "verbal arithmetic slipped (3 times 4 = 13)",
       edits=((MA, _MA_APPEND, "So 3 times 4 = 13.\n\n" + _MA_APPEND),), marker="3 times 4 = 13", expected=("INT-SUBJ-001",)),
    _p("maths-mod-control", "maths", "receipt", "control", (MA,), MA, "a remainder in a mathematics answer, correct (17 mod 5 = 2)",
       edits=((MA, _MA_APPEND, "The remainder is 17 mod 5 = 2.\n\n" + _MA_APPEND),), marker="17 mod 5 = 2"),
    _p("maths-congruence", "maths", "receipt", "answer", (MA,), MA, "a congruence stated wrongly (17 ≡ 3 (mod 5))",
       edits=((MA, _MA_APPEND, "Here 17 ≡ 3 (mod 5).\n\n" + _MA_APPEND),), marker="17 ≡ 3 (mod 5)", expected=("INT-SUBJ-001",)),
    _p("maths-congruence-control", "maths", "receipt", "control", (MA,), MA, "the same congruence stated correctly (17 ≡ 2 (mod 5): never the equality 17 = 2)",
       edits=((MA, _MA_APPEND, "Here 17 ≡ 2 (mod 5).\n\n" + _MA_APPEND),), marker="17 ≡ 2 (mod 5)"),
    _p("receipts-fragment", "receipts", "receipt", "answer", (MA,), MA, "a relation written partly in words ('when 17 is divided by 5 = 2'), named unchecked, never read "
       "as '5 = 2'", edits=((MA, _MA_APPEND, "The remainder when 17 is divided by 5 = 2.\n\n" + _MA_APPEND),), marker="divided by 5 = 2", expected=("ST-PARSE-001",),
       forbidden=("INT-SUBJ-001",)),
    _p("receipts-unread-sign", "receipts", "receipt", "answer", (MA,), MA, "a relation sign no span reads (17 % 5 = 2 outside Computer Science), named unchecked",
       edits=((MA, _MA_APPEND, "As a check, 17 % 5 = 2.\n\n" + _MA_APPEND),), marker="17 % 5 = 2", expected=("ST-PARSE-001",), forbidden=("INT-SUBJ-001",)),
    _p("boolean-question", "boolean", "receipt", "answer", (CS,), CS, "a test answered wrongly in a trace ('Is 67 = 67? No.': its negation is checked)",
       edits=((CS, _CS_APPEND, "Is 67 = 67? No.\n\n" + _CS_APPEND),), marker="Is 67 = 67", expected=("INT-SUBJ-001",)),
    _p("boolean-question-control", "boolean", "receipt", "control", (CS,), CS, "the trace's test answered correctly ('Is 38 = 67? No.': never the claim 38 = 67)",
       edits=((CS, _CS_APPEND, "Is 38 = 67? No.\n\n" + _CS_APPEND),), marker="Is 38 = 67"),
    # Givens and stated values against the request (rules given-kinds, named-given, table-data for a Given), and ST-UNDEC-003 for
    # a Given no check sets against it
    _p("givens-percent", "givens", "receipt", "answer", (MI,), MI, "a Given rate that contradicts the task (r = 3.9% for 3.6%)",
       edits=((MI, "**Assumption:**", "Given: P = 4000, r = 3.9%.\n\n**Assumption:**"),), marker="r = 3.9%", expected=("INT-SUBJ-004",)),
    _p("givens-percent-control", "givens", "receipt", "control", (MI,), MI, "the same Givens as the task states them",
       edits=((MI, "**Assumption:**", "Given: P = 4000, r = 3.6%.\n\n**Assumption:**"),), marker="r = 3.6%"),
    _p("givens-currency", "givens", "receipt", "answer", (MI,), MI, "a Given amount written with its currency word that contradicts the task (5000 euros for 4000)",
       edits=((MI, "**Assumption:**", "Given: P = 5000 euros.\n\n**Assumption:**"),), marker="P = 5000 euros", expected=("INT-SUBJ-004",)),
    _p("givens-currency-control", "givens", "receipt", "control", (MI,), MI, "the same amount as the task states it",
       edits=((MI, "**Assumption:**", "Given: P = 4000 euros.\n\n**Assumption:**"),), marker="P = 4000 euros"),
    _p("givens-years", "givens", "receipt", "answer", (MI,), MI, "a Given time that contradicts the task (6 years for 5)",
       edits=((MI, "**Assumption:**", "Given: t = 6 years.\n\n**Assumption:**"),), marker="t = 6 years", expected=("INT-SUBJ-004",)),
    _p("givens-years-control", "givens", "receipt", "control", (MI,), MI, "the same time as the task states it",
       edits=((MI, "**Assumption:**", "Given: t = 5 years.\n\n**Assumption:**"),), marker="t = 5 years"),
    _p("givens-per-cent", "givens", "receipt", "answer", (MI,), MI, "a Given rate written 'per cent' that contradicts the task (3.9 per cent for 3.6%)",
       edits=((MI, "**Assumption:**", "Given: the nominal annual rate is r = 3.9 per cent.\n\n**Assumption:**"),), marker="r = 3.9 per cent", expected=("INT-SUBJ-004",)),
    _p("givens-per-cent-control", "givens", "receipt", "control", (MI,), MI, "the same rate written 'per cent' as the task states it",
       edits=((MI, "**Assumption:**", "Given: the nominal annual rate is r = 3.6 per cent.\n\n**Assumption:**"),), marker="r = 3.6 per cent"),
    _p("givens-bare", "givens", "receipt", "answer", (MI,), MI, "a bare Given number the task states nowhere (P = 5000), named unchecked: a bare number may "
       "be a conversion, so it is never failed", edits=((MI, "**Assumption:**", "Given: P = 5000.\n\n**Assumption:**"),), marker="P = 5000",
       expected=("ST-UNDEC-003",), forbidden=("INT-SUBJ-004", "INT-SUBJ-001")),
    _p("givens-bare-control", "givens", "receipt", "control", (MI,), MI, "a bare Given number the task states (P = 4000): read as the task's 4000",
       edits=((MI, "**Assumption:**", "Given: P = 4000.\n\n**Assumption:**"),), marker="P = 4000"),
    _p("givens-bare-conversion", "givens", "receipt", "answer", (MI,), MI, "bare Givens converted from the task (r = 0.036 for 3.6%, n = 12 for monthly) "
       "are named unchecked, never failed", edits=((MI, "**Assumption:**", "Given: r = 0.036, n = 12.\n\n**Assumption:**"),), marker="r = 0.036",
       expected=("ST-UNDEC-003",), forbidden=("INT-SUBJ-004", "INT-SUBJ-001")),
    _p("givens-prose", "givens", "receipt", "answer", (PH,), PH, "the prose states the battery's emf against the task's words (9.0 V for 'emf 12 V'; rule named-given)",
       edits=((PH, "(a) [2]\nFor resistors", "The battery's emf is 9.0 V.\n\n(a) [2]\nFor resistors"),), marker="The battery's emf is 9.0 V", expected=("INT-SUBJ-004",)),
    _p("givens-prose-control", "givens", "receipt", "control", (PH,), PH, "the prose states the emf as the task does",
       edits=((PH, "(a) [2]\nFor resistors", "The battery's emf is 12 V.\n\n(a) [2]\nFor resistors"),), marker="The battery's emf is 12 V"),
    _p("givens-table", "givens", "receipt", "answer", (ES,), ES, "a Given that contradicts the supplied table (dissolved oxygen at C 3.5 for 3.8)",
       edits=((ES, "= 60.4% decrease [1]", "= 60.4% decrease [1]\nGiven: dissolved oxygen at C = 3.5 mg dm⁻³."),), marker="dissolved oxygen at C = 3.5",
       expected=("INT-SUBJ-004",)),
    _p("givens-table-control", "givens", "receipt", "control", (ES,), ES, "the same Given as the table states it",
       edits=((ES, "= 60.4% decrease [1]", "= 60.4% decrease [1]\nGiven: dissolved oxygen at C = 3.8 mg dm⁻³."),), marker="dissolved oxygen at C = 3.8"),
    _p("receipts-given-unchecked", "receipts", "receipt", "answer", (PH,), PH, "a Given of a kind the task states no value of (a time), named unchecked (ST-UNDEC-003)",
       edits=((PH, "(a) [2]\nFor resistors", "Given: t = 5.0 s.\n\n(a) [2]\nFor resistors"),), marker="t = 5.0 s", expected=("ST-UNDEC-003",)),
    # another row's value substituted in working that the arithmetic gets right (rule table-operands)
    _p("wrong-given-table-row", "wrong_given", "receipt", "answer", (ES,), ES, "site B's dissolved oxygen substituted for site C's in part (a), its arithmetic right",
       edits=((ES, "(9.6 − 3.8) ÷ 9.6 × 100\n= 60.4% decrease", "(9.6 − 6.1) ÷ 9.6 × 100\n= 36.5% decrease"),), marker="(9.6 − 6.1) ÷ 9.6",
       expected=("INT-SUBJ-004",)),
    _p("wrong-given-table-line", "wrong_given", "receipt", "answer", (ES,), ES, "a line naming sites A and C that takes site B's value (9.6 − 6.1 = 3.5)",
       edits=((ES, "= 60.4% decrease [1]", "= 60.4% decrease [1]\nFrom A to C the fall is 9.6 − 6.1 = 3.5 mg dm⁻³."),), marker="9.6 − 6.1 = 3.5",
       expected=("INT-SUBJ-004",)),
    _p("wrong-given-table-line-control", "wrong_given", "receipt", "control", (ES,), ES, "the same line with site C's value",
       edits=((ES, "= 60.4% decrease [1]", "= 60.4% decrease [1]\nFrom A to C the fall is 9.6 − 3.8 = 5.8 mg dm⁻³."),), marker="9.6 − 3.8 = 5.8"),
    _p("wrong-given-table-row-p7b", "wrong_given", "receipt", "answer", (PB,), "p7b", "the line for t = 4 h takes the t = 0 h reading (1620 for 1151), its arithmetic right",
       edits=((PB, "t = 4 h: 1151 − 20 = 1131 ± 23 counts min⁻¹", "t = 4 h: 1620 − 20 = 1600 ± 32 counts min⁻¹"),), marker="t = 4 h: 1620",
       expected=("INT-SUBJ-004",)),
    # the relay: the value taken from the quote (rule restated-binding)
    _p("relay-derived-rate", "relay", "receipt", "answer", ("ph-p7b", "maa-p7b"), "p7b", "the mathematics answer quotes the corrected rate and then takes the measured one "
       "(so C(8) = 820)", edits=(("maa-p7b", "(so C(8) = 800)", "(so C(8) = 820)"),), marker="(so C(8) = 820)", expected=("INT-SUBJ-004",)),
    _p("relay-derived-initial", "relay", "receipt", "answer", ("ph-p7b", "maa-p7b"), "p7b", "the same at t = 0 (so C0 = 1620)",
       edits=(("maa-p7b", "(so C0 = 1600)", "(so C0 = 1620)"),), marker="(so C0 = 1620)", expected=("INT-SUBJ-004",)),
    # physics working with units (rule exact-carry)
    _p("physics-unit-sum", "physics", "receipt", "answer", (PB,), "p7b", "a sum of count rates written with units, slipped by 10 (100 + 20 = 130 counts min⁻¹)",
       edits=((PB, "because the background adds 20 counts min⁻¹.", "because the background adds 20 counts min⁻¹.\nCheck: 100 counts min⁻¹ + 20 counts min⁻¹ = 130 counts min⁻¹."),),
       marker="= 130 counts min⁻¹", expected=("INT-SUBJ-001",)),
    _p("physics-unit-sum-control", "physics", "receipt", "control", (PB,), "p7b", "the same sum written correctly (120 counts min⁻¹)",
       edits=((PB, "because the background adds 20 counts min⁻¹.", "because the background adds 20 counts min⁻¹.\nCheck: 100 counts min⁻¹ + 20 counts min⁻¹ = 120 counts min⁻¹."),),
       marker="= 120 counts min⁻¹"),
    _p("physics-prose-sum", "physics", "receipt", "answer", (PB,), "p7b", "the same slip in a sentence of prose (A measured rate would be 100 + 20 = 130 counts min⁻¹)",
       edits=((PB, "A measured rate would be about 120 counts min⁻¹", "A measured rate would be 100 + 20 = 130 counts min⁻¹"),), marker="100 + 20 = 130",
       expected=("INT-SUBJ-001",)),
    _p("physics-prose-sum-control", "physics", "receipt", "control", (PB,), "p7b", "the same sentence written correctly",
       edits=((PB, "A measured rate would be about 120 counts min⁻¹", "A measured rate would be 100 + 20 = 120 counts min⁻¹"),), marker="100 + 20 = 120"),
    # units and equations no longer skipped silently
    _p("units-bracketed-conversion", "units", "receipt", "answer", (ES,), ES, "a conversion in brackets after a word, wrong (greatest at C (2.0 km = 200 m))",
       edits=((ES, "greatest at C (2.0 km)", "greatest at C (2.0 km = 200 m)"),), marker="2.0 km = 200 m", expected=("INT-SUBJ-001",)),
    _p("units-bracketed-conversion-control", "units", "receipt", "control", (ES,), ES, "the same conversion written correctly (2000 m)",
       edits=((ES, "greatest at C (2.0 km)", "greatest at C (2.0 km = 2000 m)"),), marker="2.0 km = 2000 m"),
    _p("equations-premise-cue", "equations", "receipt", "answer", (CH,), CH, "a rearrangement written after 'From …,' wrongly (from c = n/V, n = c/V)",
       edits=((CH, _CH_APPEND, "From c = n/V, n = c/V = 0.10 / 0.0500 = 2.0. " + _CH_APPEND),), marker="n = c/V", expected=("INT-SUBJ-001",)),
    _p("equations-premise-cue-control", "equations", "receipt", "control", (CH,), CH, "the same rearrangement written correctly (n = cV)",
       edits=((CH, _CH_APPEND, "From c = n/V, n = cV = 0.10 × 0.0500 = 0.0050. " + _CH_APPEND),), marker="n = cV"),
)
#: Translation probes: bi-t13's recorded translation of its percentage claim (recorded as g2.1, delivered as s2.1), re-keyed
#: and given each class's fault (``_plant_translation``).
TRANSLATION_PROBES: tuple[Probe, ...] = (
    _p("units-translation", "units", "translation", "translation", (BI,), BI, "the translation converts the 30 °C uptake (80 mm³) itself, to 0.08",
       translation=(BI, "g2.1", "convert_t30"), expected=("OVS-TRN-005",), agent_kind="translation_ungrounded", agent_outcome="confirmed",
       agent_rule="A quotation or number stated nowhere"),
    # the second translator merge: the merged translator refuses the stated 100 per cent encoded as anywhere from 90 to 110 itself
    # (its exactness rule: the encoding widens a figure the source states exactly; INVALID_FORMALIZATION, no receipt carries it), so the
    # probe plants the weaker claim it delivers, displayed ENTAILED: the overseer must name it
    _p("precision-translation", "precision", "translation", "translation", (BI,), BI, "the stated 100 per cent encoded as at least 90 (a weaker claim)",
       translation=(BI, "g2.1", "at_least_90"), expected=("OVS-TRN-005",), agent_kind="translation_unfaithful", agent_outcome="unresolved",
       agent_rule="A wider interval encodes a weaker claim"),
    _p("arithmetic-translation", "arithmetic", "translation", "translation", (BI,), BI, "the translation's result written 120 for the stated 100",
       translation=(BI, "g2.1", "result_120"), expected=("OVS-TRN-005",), agent_kind="translation_ungrounded", agent_outcome="confirmed",
       agent_rule="A quotation or number stated nowhere"),
    _p("wrong-given-translation", "wrong_given", "translation", "translation", (BI,), BI, "the translation substitutes the 25 °C uptake (58) for the 20 °C one (40)",
       translation=(BI, "g2.1", "other_given"), expected=(), agent_kind="translation_unfaithful", agent_outcome="unresolved",
       agent_rule="Another stated given substituted"),
    _p("equations-translation", "equations", "translation", "translation", (BI,), BI, "the percentage rearranged over the final value (× 80) instead of the initial (× 40)",
       translation=(BI, "g2.1", "rearranged"), expected=(), agent_kind="translation_unfaithful", agent_outcome="unresolved",
       agent_rule="Another relation encoded"),
    _p("dimensions-translation", "dimensions", "translation", "translation", (BI,), BI, "the translation subtracts the temperature 20 (°C) from an uptake",
       translation=(BI, "g2.1", "mixed_quantities"), expected=(), agent_kind="translation_unfaithful", agent_outcome="unresolved",
       agent_rule="Two incompatible quantities combined"),
    _p("formulas-translation", "formulas", "translation", "translation", (BI,), BI, "the translation uses the change itself (t30 − t20) as the percentage",
       translation=(BI, "g2.1", "no_ratio"), expected=(), agent_kind="translation_unfaithful", agent_outcome="unresolved",
       agent_rule="Another relation encoded"),
    _p("rounding-translation", "rounding", "translation", "translation", (PH,), PH, "the power's rounded result encoded as 17 where the line rounds 16.4 W to 16 W",
       translation=(PH, "g4.3", "number:conclusion:16:17"), expected=("OVS-TRN-005",), agent_kind="translation_ungrounded", agent_outcome="confirmed",
       agent_rule="A quotation or number stated nowhere"),
    _p("physics-translation", "physics", "translation", "translation", (PH,), PH, "the terminal p.d. line encoded with 0.60 Ω for the 0.50 Ω internal resistance",
       translation=(PH, "g3.2", "number:any:0.50:0.60"), expected=("OVS-TRN-005",), agent_kind="translation_ungrounded", agent_outcome="confirmed",
       agent_rule="A quotation or number stated nowhere"),
    _p("chemistry-translation", "chemistry", "translation", "translation", (CH,), CH, "the 50.0 cm³ of thiosulfate converted wrongly by the translator (0.5 dm³)",
       translation=(CH, "g5.1", "number:any:50.0:0.5"), expected=("OVS-TRN-005", "OVS-TRN-004"), agent_kind="translation_ungrounded", agent_outcome="confirmed",
       agent_rule="A quotation or number stated nowhere"),
    _p("maths-translation", "maths", "translation", "translation", (MI,), MI, "the monthly rate encoded as 0.03 where the claim states 0.036/12 = 0.003",
       translation=(MI, "g5.3", "number:any:0.003:0.03"), expected=("OVS-TRN-005",), agent_kind="translation_ungrounded", agent_outcome="confirmed",
       agent_rule="A quotation or number stated nowhere"),
    _p("givens-translation", "givens", "translation", "translation", (ES,), ES, "site C's nitrate encoded as 7.9 where the claim and the table state 6.9",
       translation=(ES, "g2.3", "number:any:6.9:7.9"), expected=("OVS-TRN-005",), agent_kind="translation_ungrounded", agent_outcome="confirmed",
       agent_rule="A quotation or number stated nowhere"),
    _p("relay-translation", "relay", "translation", "translation", ("ph-p7b", "maa-p7b"), "p7b", "the physics specialist's quoted 1600 encoded as 1700 in the mathematics translation",
       translation=("maa-p7b", "g7.2", "number:any:1600:1700"), expected=("OVS-TRN-005",), agent_kind="translation_ungrounded", agent_outcome="confirmed",
       agent_rule="A quotation or number stated nowhere"),
)
#: STEM repair 1: a translation that encodes a quotation's figure converted between prefixes of its unit. Into the unit with no
#: prefix (50.0 cm³ as 0.0000500) it is the answer's own number (Inspection I91): nothing new, and never circular (rule
#: excerpt-prefix-units). Under another prefix (5.0 cm³ as 0.0050 dm³) OVS-TRN-005 names the number the answer does not state, a
#: warning, and a correct conversion is never graded the claim assumed (no OVS-TRN-006, no OVS-TRN-004).
CONVERSION_PROBES: tuple[Probe, ...] = (
    _p("units-translation-base-control", "units", "translation", "control", (CH,), CH, "the 50.0 cm³ of thiosulfate encoded in m³ (0.0000500), the unit with no prefix",
       translation=(CH, "g5.1", "number:any:50.0:0.0000500")),
    _p("units-translation-prefix", "units", "translation", "translation", (CH,), CH, "the 5.0 cm³ of acid encoded in dm³ (0.0050), a correct conversion under another prefix",
       translation=(CH, "g5.1", "number:any:5.0:0.0050"), expected=("OVS-TRN-005",), forbidden=("OVS-TRN-006", "OVS-TRN-004")),
)
#: STEM repair 2: the supplied table's figures converted into the unit with no prefix (9.6 mg dm⁻³ as 0.0096, kg m⁻³), keeping the
#: relation, are the answer's own numbers (Inspection I91; rule table-units): nothing new. Converted wrongly (0.096) they stay named.
TABLE_UNIT_PROBES: tuple[Probe, ...] = (
    _p("units-translation-table-base-control", "units", "translation", "control", (ES,), ES, "ess-t13's percentage claim with the table's 9.6 and 3.8 mg dm⁻³ "
       "encoded in kg m⁻³ (0.0096, 0.0038) and the relation kept", translation=(ES, "g1.1", "numbers:any:9.6=0.0096,3.8=0.0038")),
    _p("units-translation-table-wrong", "units", "translation", "translation", (ES,), ES, "the same claim with the figures converted wrongly (0.096, 0.038)",
       translation=(ES, "g1.1", "numbers:any:9.6=0.096,3.8=0.038"), expected=("OVS-TRN-005",), agent_kind="translation_ungrounded", agent_outcome="confirmed",
       agent_rule="A quotation or number stated nowhere"),
)
#: STEM repair 3 (design section 34): the third independent test's plants and a control for each, appended where an added line shifts
#: no recorded claim id (the answers' last lines), each on the class whose cause it found.
_BI_END = "which makes ATP. [1 spare]"
_PB_END = "Both effects make the count rate smaller than the activity."
_CH_END = "so I cannot give one yet."
_PB_D = "C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹"
REPAIR3_PROBES: tuple[Probe, ...] = (
    # rule value-at: a value stated under a condition ('<quantity> at <condition> = <value>') is the quantity's value there, never a
    # conversion between the condition and the value; a Given so stated is set against the supplied table's row, or named
    _p("givens-at-condition", "givens", "receipt", "answer", (BI,), BI, "a Given stated under a condition contradicting the supplied table (oxygen uptake at 30 °C = 85 "
       "for 80)", edits=((BI, _BI_END, _BI_END + "\n\nGiven: oxygen uptake at 30 °C = 85 mm³ per g per hour."),), marker="uptake at 30 °C = 85",
       expected=("INT-SUBJ-004",), forbidden=("INT-SUBJ-001", "ST-DIM-001")),
    _p("givens-at-condition-control", "givens", "receipt", "control", (BI,), BI, "the same Given as the table states it (80): before, the false conversion '30 °C = "
       "80 mm³' (INT-SUBJ-001, ST-DIM-001)", edits=((BI, _BI_END, _BI_END + "\n\nGiven: oxygen uptake at 30 °C = 80 mm³ per g per hour."),),
       marker="uptake at 30 °C = 80"),
    _p("givens-at-condition-symbol", "givens", "receipt", "answer", (PB,), "p7b", "a Given count rate stated under a condition on t, contradicting the table (830 for 820)",
       edits=((PB, _PB_END, _PB_END + "\nGiven: the count rate at t = 8 h = 830 counts min⁻¹."),), marker="t = 8 h = 830", expected=("INT-SUBJ-004",),
       forbidden=("INT-SUBJ-001", "ST-DIM-001")),
    _p("givens-at-condition-symbol-control", "givens", "receipt", "control", (PB,), "p7b", "the same Given as the table states it (820): before, '8 h = 820 counts min⁻¹' "
       "failed and '2%' became a false restatement", edits=((PB, _PB_END, _PB_END + "\nGiven: the count rate at t = 8 h = 820 counts min⁻¹."),),
       marker="t = 8 h = 820"),
    _p("givens-at-condition-trials", "givens", "receipt", "answer", (CH,), CH, "a Given time at a temperature that no trial of that row gives (36.1 s at 30.0 °C)",
       edits=((CH, _CH_END, _CH_END + "\n\nGiven: time at 30.0 °C = 36.1 s."),), marker="30.0 °C = 36.1 s", expected=("INT-SUBJ-004",),
       forbidden=("INT-SUBJ-001", "ST-DIM-001")),
    _p("givens-at-condition-trials-control", "givens", "receipt", "control", (CH,), CH, "the first trial's time at that row (33.1 s)",
       edits=((CH, _CH_END, _CH_END + "\n\nGiven: time at 30.0 °C = 33.1 s."),), marker="30.0 °C = 33.1 s"),
    _p("givens-values-at", "givens", "receipt", "answer", (BI,), BI, "two values under conditions outside a Given, the second against the table (88 for 80 at 30 °C)",
       edits=((BI, _BI_END, _BI_END + "\n\nThe uptake at 20 °C = 40 mm³ per g per hour, and at 30 °C = 88 mm³ per g per hour."),), marker="at 30 °C = 88",
       expected=("INT-SUBJ-004",), forbidden=("INT-SUBJ-001", "ST-DIM-001")),
    _p("givens-values-at-control", "givens", "receipt", "control", (BI,), BI, "the same two values as the table states them (before: two false conversions)",
       edits=((BI, _BI_END, _BI_END + "\n\nThe uptake at 20 °C = 40 mm³ per g per hour, and at 30 °C = 80 mm³ per g per hour."),), marker="at 30 °C = 80"),
    # rule supplied-values (with rule given-digits): a Given against the values a supplied text states in prose
    _p("givens-supplied-prose", "givens", "receipt", "answer", (PB,), "p7b", "a Given background contradicting the supplied text's 20 counts per minute (30)",
       edits=((PB, _PB_END, _PB_END + "\nGiven: background count rate = 30 counts min⁻¹."),), marker="background count rate = 30", expected=("INT-SUBJ-004",)),
    _p("givens-supplied-prose-control", "givens", "receipt", "control", (PB,), "p7b", "the same Given as the supplied text states it (20)",
       edits=((PB, _PB_END, _PB_END + "\nGiven: background count rate = 20 counts min⁻¹."),), marker="background count rate = 20"),
    _p("givens-supplied-volume", "givens", "receipt", "answer", (CH,), CH, "a Given volume contradicting the supplied text's 50.0 cm3 of thiosulfate (40.0 cm³)",
       edits=((CH, _CH_END, _CH_END + "\n\nGiven: volume of thiosulfate = 40.0 cm³."),), marker="thiosulfate = 40.0", expected=("INT-SUBJ-004",)),
    _p("givens-supplied-volume-control", "givens", "receipt", "control", (CH,), CH, "the same Given as the supplied text states it (50.0 cm³)",
       edits=((CH, _CH_END, _CH_END + "\n\nGiven: volume of thiosulfate = 50.0 cm³."),), marker="thiosulfate = 50.0"),
    # rule given-uncertainty: a Given uncertainty against the uncertainties the supplied text states, never against values of its
    # quantity; a Given written with its uncertainty at its central value (rule central-value)
    _p("givens-uncertainty", "givens", "receipt", "answer", (CH,), CH, "a Given thermometer uncertainty contradicting the supplied text's +/-0.5 °C (0.1 °C)",
       edits=((CH, _CH_END, _CH_END + "\n\nGiven: thermometer uncertainty = 0.1 °C."),), marker="uncertainty = 0.1 °C", expected=("INT-SUBJ-004",)),
    _p("givens-uncertainty-control", "givens", "receipt", "control", (CH,), CH, "the same Given as the supplied text states it (0.5 °C): before, a false "
       "INT-SUBJ-004 against the request's 20 °C and 60 °C", edits=((CH, _CH_END, _CH_END + "\n\nGiven: thermometer uncertainty = 0.5 °C."),),
       marker="uncertainty = 0.5 °C"),
    _p("givens-central", "givens", "receipt", "answer", (CH,), CH, "a Given temperature with its uncertainty, at a value the request does not state (25.0 ± 0.5 °C)",
       edits=((CH, _CH_END, _CH_END + "\n\nGiven: T = 25.0 ± 0.5 °C."),), marker="T = 25.0 ± 0.5", expected=("INT-SUBJ-004",)),
    _p("givens-central-control", "givens", "receipt", "control", (CH,), CH, "the request's lowest temperature with its uncertainty (20.0 ± 0.5 °C)",
       edits=((CH, _CH_END, _CH_END + "\n\nGiven: T = 20.0 ± 0.5 °C."),), marker="T = 20.0 ± 0.5"),
    # rule central-value: a slip within a stated uncertainty
    _p("arithmetic-within-uncertainty", "arithmetic", "receipt", "answer", (PB,), "p7b", "a subtraction slipped within its stated uncertainty (586 − 20 = 556 ± 12)",
       edits=((PB, "586 − 20 = 566 ± 12", "586 − 20 = 556 ± 12"),), marker="586 − 20 = 556", expected=("INT-SUBJ-001",)),
    # STEM repair 4: the control's uncertainty is now set against the rule the answer states for it ('2% of the measured value'):
    # ± 11 contradicts it (2% of 586 is 11.72) and is the answer probe 'arithmetic-uncertainty-rule'; ± 11.7 is the same control
    _p("arithmetic-within-uncertainty-control", "arithmetic", "receipt", "control", (PB,), "p7b", "the same line with another stated uncertainty that its "
       "stated rule gives (± 11.7: 2% of 586 is 11.72)", edits=((PB, "586 − 20 = 566 ± 12", "586 − 20 = 566 ± 11.7"),), marker="586 − 20 = 566 ± 11.7"),
    # rule processed-data: the measured value substituted for the value the answer corrected it into
    _p("wrong-given-measured", "wrong_given", "receipt", "answer", (PB,), "p7b", "(d) takes the measured 1620 for the corrected 1600, its arithmetic right",
       edits=((PB, _PB_D, "C = 1620 counts min⁻¹ × (1/2)⁴ = 101 counts min⁻¹"),), marker="1620 counts min⁻¹ × (1/2)⁴", expected=("INT-SUBJ-004",)),
    _p("wrong-given-measured-control", "wrong_given", "receipt", "control", (PB,), "p7b", "the measured 1620 in a part that asks for no corrected value (the background "
       "as a share of the first reading)", edits=((PB, _PB_END, _PB_END + "\nThe background is 20/1620 × 100 = 1.2% of the first reading."),),
       marker="20/1620 × 100"),
    # units given only in the task or its table: a header unit with ASCII exponents, a unit 'per …', rule restated-unit
    _p("units-table-restated", "units", "receipt", "answer", (BI,), BI, "a table value restated in cm³ where the table gives mm3 (the number unchanged)",
       edits=((BI, "from 18 mm³ per g per hour at 10 °C", "from 18 cm³ per g per hour at 10 °C"),), marker="18 cm³ per g", expected=("INT-SUBJ-004",)),
    _p("units-table-restated-control", "units", "receipt", "control", (BI,), BI, "the same value converted correctly (0.018 cm³)",
       edits=((BI, "from 18 mm³ per g per hour at 10 °C", "from 0.018 cm³ per g per hour at 10 °C"),), marker="0.018 cm³ per g"),
    _p("units-task-restated", "units", "receipt", "answer", (PB,), "p7b", "the background written per second where the task states 20 counts per minute",
       edits=((PB, "the background of 20 counts min⁻¹ is constant", "the background of 20 counts s⁻¹ is constant"),), marker="20 counts s⁻¹",
       expected=("INT-SUBJ-004",)),
    _p("units-task-restated-control", "units", "receipt", "control", (PB,), "p7b", "the same background written 'per minute' as the task does",
       edits=((PB, "the background of 20 counts min⁻¹ is constant", "the background of 20 counts per minute is constant"),), marker="20 counts per minute"),
    # rules percentage-change and half-lives; a stated rounding of a stated value
    _p("formulas-percentage-final", "formulas", "receipt", "answer", (ES,), ES, "a percentage decrease divided by the final value (3.8), its arithmetic right",
       edits=((ES, "(9.6 − 3.8) ÷ 9.6 × 100\n= 60.4% decrease", "(9.6 − 3.8) ÷ 3.8 × 100\n= 152.6% decrease"),), marker="(9.6 − 3.8) ÷ 3.8",
       expected=("INT-SUBJ-004",)),
    _p("formulas-percentage-final-control", "formulas", "receipt", "control", (ES,), ES, "the same decrease over the starting value, to another digit (60.42%)",
       edits=((ES, "(9.6 − 3.8) ÷ 9.6 × 100\n= 60.4% decrease", "(9.6 − 3.8) ÷ 9.6 × 100\n= 60.42% decrease"),), marker="60.42% decrease"),
    _p("formulas-half-lives", "formulas", "receipt", "answer", (PB,), "p7b", "four half-lives computed with the cube ((1/2)³ = 200), its arithmetic right",
       edits=((PB, _PB_D, "C = 1600 counts min⁻¹ × (1/2)³ = 200 counts min⁻¹"),), marker="(1/2)³ = 200", expected=("INT-SUBJ-004",)),
    _p("formulas-half-lives-control", "formulas", "receipt", "control", (PB,), "p7b", "the same decay written with 0.5⁴",
       edits=((PB, _PB_D, "C = 1600 counts min⁻¹ × 0.5⁴ = 100 counts min⁻¹"),), marker="0.5⁴ = 100"),
    _p("physics-half-lives-count", "physics", "receipt", "answer", (PB,), "p7b", "32 h stated as 5 half-lives of 8.0 h", edits=((PB, "32 h is 4 half-lives", "32 h is 5 half-lives"),),
       marker="32 h is 5 half-lives", expected=("INT-SUBJ-004",)),
    _p("physics-half-lives-count-control", "physics", "receipt", "control", (PB,), "p7b", "the same count written in words (four)",
       edits=((PB, "32 h is 4 half-lives", "32 h is four half-lives"),), marker="32 h is four half-lives"),
    _p("rounding-stated-value-sf", "rounding", "receipt", "answer", (PH,), PH, "a stated value rounded wrongly to one significant figure (2.4 Ω as 3 Ω)",
       edits=((PH, "R = 2.4 Ω (the external resistance)", "R = 2.4 Ω (the external resistance), or 3 Ω to one significant figure"),), marker="3 Ω to one significant",
       expected=("INT-SUBJ-001",)),
    _p("rounding-stated-value-sf-control", "rounding", "receipt", "control", (PH,), PH, "the same value rounded correctly (2 Ω)",
       edits=((PH, "R = 2.4 Ω (the external resistance)", "R = 2.4 Ω (the external resistance), or 2 Ω to one significant figure"),), marker="2 Ω to one significant"),
    # a percentage never restates a quantity of a dimension (the false '2%' restatement)
    _p("physics-percent-control", "physics", "receipt", "control", (PH,), PH, "a percentage uncertainty stated after a current (2%: no restatement of 4.1 A)",
       edits=((PH, "I = 12 V / 2.9 Ω = 4.1 A", "I = 12 V / 2.9 Ω = 4.1 A\nThe percentage uncertainty in I is therefore 2%."),), marker="therefore 2%"),
    # pack against code: a sum over written whole-number bounds is checked as arithmetic (pack D31, D32)
    _p("receipts-sum", "receipts", "receipt", "answer", (MA,), MA, "a sum over written bounds stated wrongly (Σ_{k=1}^{10} k = 56): expanded and checked",
       edits=((MA, _MA_APPEND, "Also Σ_{k=1}^{10} k = 56.\n\n" + _MA_APPEND),), marker="Σ_{k=1}^{10} k = 56", expected=("INT-SUBJ-001",)),
    _p("receipts-sum-control", "receipts", "receipt", "control", (MA,), MA, "the same sum stated correctly (55)",
       edits=((MA, _MA_APPEND, "Also Σ_{k=1}^{10} k = 55.\n\n" + _MA_APPEND),), marker="Σ_{k=1}^{10} k = 55"),
    _p("receipts-sum-symbolic", "receipts", "receipt", "answer", (MA,), MA, "a sum with a symbolic bound, named undecided (ST-UNDEC-001)",
       edits=((MA, _MA_APPEND, "In general Σ_{k=1}^{n} k = n(n + 1)/2.\n\n" + _MA_APPEND),), marker="Σ_{k=1}^{n} k", expected=("ST-UNDEC-001",)),
)
#: STEM repair 4 (design section 35): the fourth independent test's plants and a control for each, on the class whose cause it found.
_CS_END = "Next step: trace"
_PH_END = "from 9.9 V to 10.7 V."
_MI_END = "Next step: rework (a)"
_MI_B = "$4000(1.036)^{11} = 5902.25$ and"
_ES_END = "seasonal runoff peaks [1]."
_ES_W = "Water temperature was between 17 °C and 18 °C at every site, so it does not explain the difference."
_PB_A = "(a) [2]\nCorrected count rate"
_MP, _MP_KEY = "maa-p7b", "p7b"


def _cs(pid: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, "boolean", "receipt", kind, (CS,), CS, desc, edits=((CS, _CS_END, line + "\n\n" + _CS_END),), marker=marker, expected=expected)


def _ph(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (PH,), PH, desc, edits=((PH, _PH_END, _PH_END + "\n" + line),), marker=marker, expected=expected)


def _pb(pid: str, cls: str, kind: str, old: str, new: str, desc: str, marker: str, expected: tuple[str, ...] = (), forbidden: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (PB,), _MP_KEY, desc, edits=((PB, old, new),), marker=marker, expected=expected, forbidden=forbidden)


def _es(pid: str, cls: str, kind: str, old: str, new: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (ES,), ES, desc, edits=((ES, old, new),), marker=marker, expected=expected)


REPAIR4_PROBES: tuple[Probe, ...] = (
    # rule boolean-values: a Boolean expression evaluated under the values its statement gives its inputs (before: an identity, and
    # every correct evaluation failed with INT-SUBJ-001)
    _cs("boolean-evaluation", "answer", "With A = 1 and B = 0, NOT A OR B = 1.", "NOT A OR B evaluated wrongly at A = 1, B = 0 (1 for 0)", "NOT A OR B = 1",
        ("INT-SUBJ-001",)),
    _cs("boolean-evaluation-control", "control", "With A = 1 and B = 0, NOT A OR B = 0.", "the same evaluation, correct (before: INT-SUBJ-001, read as an identity)",
        "NOT A OR B = 0"),
    _cs("boolean-evaluation-and", "answer", "When A = 1 and B = 1, A AND B = 0.", "A AND B evaluated wrongly at A = 1, B = 1", "A AND B = 0", ("INT-SUBJ-001",)),
    _cs("boolean-evaluation-and-control", "control", "When A = 0 and B = 1, A AND B = 0.", "A AND B evaluated correctly at A = 0, B = 1 (before: INT-SUBJ-001)",
        "A AND B = 0"),
    _cs("boolean-evaluation-not-control", "control", "If A = 1, then NOT A = 0.", "NOT A evaluated correctly at A = 1 (before: INT-SUBJ-001)", "NOT A = 0"),
    _cs("boolean-evaluation-xor-control", "control", "For A = 1 and B = 1, A XOR B = 0.", "A XOR B evaluated correctly at A = 1, B = 1 (before: INT-SUBJ-001)",
        "A XOR B = 0"),
    _cs("boolean-evaluation-or-control", "control", "With A = 1 and B = 0, A OR B = 1.", "A OR B evaluated correctly at A = 1, B = 0 (before: INT-SUBJ-001)",
        "A OR B = 1"),
    _cs("boolean-evaluation-setup", "answer", "Let A = 1 and B = 0. Then NOT A OR B = 1.", "the values set up by the statement before, the evaluation wrong",
        "Then NOT A OR B = 1", ("INT-SUBJ-001",)),
    _cs("boolean-evaluation-setup-control", "control", "Let A = 1 and B = 0. Then NOT A OR B = 0.", "the values set up by the statement before, the evaluation "
        "correct", "Then NOT A OR B = 0"),
    # rule changed-value: a substitution that takes the value a stated change ends at (before: INT-SUBJ-001 on correct working)
    _ph("physics-changed-value", "physics", "answer", "V = 12 V − 3.7 A × 0.50 Ω = 10.15 V", "part (e) substitutes a current the answer never states (3.7 A)",
        "3.7 A × 0.50 Ω", ("INT-SUBJ-001",)),
    _ph("physics-changed-value-control", "physics", "control", "V = 12 V − 2.7 A × 0.50 Ω = 10.65 V", "part (e) substitutes the current the prose says the cell "
        "falls to (2.7 A; before: INT-SUBJ-001)", "2.7 A × 0.50 Ω"),
    _ph("physics-changed-value-rounded-control", "physics", "control", "V = 12 V − 2.67 A × 0.50 Ω = 10.67 V", "the same with the new current to three "
        "figures (2.67 A)", "2.67 A × 0.50 Ω = 10.67"),
    _p("physics-changed-value-earlier-part", "physics", "receipt", "answer", (PH,), PH, "part (c) takes the current part (e) states (2.7 A for 4.14 A)",
       edits=((PH, "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "V = 12 V − (2.7 A × 0.50 Ω) = 10.65 V"),), marker="(2.7 A × 0.50 Ω)", expected=("INT-SUBJ-001",)),
    _ph("rounding-changed-value", "rounding", "answer", "V = 12 V − 2.67 A × 0.50 Ω = 10.665 V, so 10.6 V to three significant figures.", "a result taken "
        "from the new current, rounded wrongly (10.665 V as 10.6 V)", "so 10.6 V", ("INT-SUBJ-001",)),
    _ph("rounding-changed-value-control", "rounding", "control", "V = 12 V − 2.67 A × 0.50 Ω = 10.665 V, so 10.7 V to three significant figures.", "the same "
        "rounded correctly (before: INT-SUBJ-001 on the substitution)", "so 10.7 V"),
    # rule given-uncertainty for '±', '%' and '+/-'
    _pb("givens-uncertainty-percent", "givens", "answer", _PB_END, _PB_END + "\n\nGiven: count rate uncertainty = ±3%.", "a Given uncertainty in per cent with "
        "'±' contradicting the supplied text's +/-2% (before: neither a check nor an ST code)", "uncertainty = ±3%", ("INT-SUBJ-004",)),
    _pb("givens-uncertainty-percent-control", "givens", "control", _PB_END, _PB_END + "\n\nGiven: count rate uncertainty = ±2%.", "the same Given as the "
        "supplied text states it", "uncertainty = ±2%"),
    _pb("givens-uncertainty-percent-start", "givens", "answer", _PB_A, "Given: uncertainty in each measured count rate = ±3%.\n\n" + _PB_A, "the same "
        "contradiction in a Given list before part (a)", "count rate = ±3%", ("INT-SUBJ-004",)),
    _pb("givens-uncertainty-percent-start-control", "givens", "control", _PB_A, "Given: uncertainty in each measured count rate = ±2%.\n\n" + _PB_A,
        "the same Given before part (a), as the supplied text states it", "count rate = ±2%"),
    _pb("givens-uncertainty-ascii", "givens", "answer", _PB_END, _PB_END + "\n\nGiven: count rate uncertainty = +/-3%.", "the contradiction written '+/-' as "
        "the supplied text writes it", "uncertainty = +/-3%", ("INT-SUBJ-004",)),
    _pb("givens-uncertainty-ascii-control", "givens", "control", _PB_END, _PB_END + "\n\nGiven: count rate uncertainty = +/-2%.", "the same written '+/-', "
        "as stated", "uncertainty = +/-2%"),
    _pb("givens-relative-uncertainty", "givens", "answer", _PB_END, _PB_END + "\n\nGiven: count rate at t = 0 h = 1620 counts min⁻¹ ± 3%.", "a Given value "
        "with a relative uncertainty the supplied text contradicts (± 3% for +/-2%)", "1620 counts min⁻¹ ± 3%", ("INT-SUBJ-004",)),
    _pb("givens-relative-uncertainty-control", "givens", "control", _PB_END, _PB_END + "\n\nGiven: count rate at t = 0 h = 1620 counts min⁻¹ ± 2%.",
        "the same Given with the stated uncertainty", "1620 counts min⁻¹ ± 2%"),
    _p("givens-central-uncertainty", "givens", "receipt", "answer", (CH,), CH, "a Given temperature whose stated uncertainty contradicts the supplied text's "
       "+/-0.5 °C (± 0.2 °C)", edits=((CH, _CH_END, _CH_END + "\n\nGiven: T = 20.0 ± 0.2 °C."),), marker="T = 20.0 ± 0.2", expected=("INT-SUBJ-004",)),
    _ph("givens-after-formula", "givens", "answer", "\nGiven: ε = 9.0 ± 0.1 V.", "a Given emf with its uncertainty after the part's ε = I(R + r), "
        "contradicting the task's 12 V (before: the formula evaluated at it, no Given check)", "ε = 9.0 ± 0.1 V", ("INT-SUBJ-004",)),
    _ph("givens-after-formula-control", "givens", "control", "\nGiven: ε = 12 ± 0.1 V.", "the same Given as the task states it (before: no stem_given check "
        "and no ST code)", "ε = 12 ± 0.1 V"),
    _pb("givens-unread-span", "givens", "answer", _PB_END, _PB_END + "\n\nGiven: count rate at t = 0 h = 1620 ± 2% counts min⁻¹.", "a Given whose maths "
        "span the branch cannot read whole (a unit after a per cent sign): named, never read in part (before: the condition t = 0 h failed against "
        "the task's t = 32 h)", "1620 ± 2% counts", ("ST-PARSE-001",), forbidden=("INT-SUBJ-004", "INT-SUBJ-001")),
    # rule rounding-cue with a word naming the unit
    _p("rounding-unit-word", "rounding", "receipt", "answer", (MI,), MI, "a result restated after ', so' with its unit word and a wrong rounding (4775 euros)",
       edits=((MI, _MI_END, "Check: 4000 × 1.036⁵ = 4773.74, so 4775 euros to the nearest euro.\n\n" + _MI_END),), marker="so 4775 euros",
       expected=("INT-SUBJ-001",)),
    _p("rounding-unit-word-control", "rounding", "receipt", "control", (MI,), MI, "the same rounded correctly (4774 euros)",
       edits=((MI, _MI_END, "Check: 4000 × 1.036⁵ = 4773.74, so 4774 euros to the nearest euro.\n\n" + _MI_END),), marker="so 4774 euros"),
    _p("rounding-unit-word-inline", "rounding", "receipt", "answer", (MI,), MI, "the recorded 5902.25 restated as 5903 euros to the nearest euro",
       edits=((MI, _MI_B, "$4000(1.036)^{11} = 5902.25$, so 5903 euros to the nearest euro, and"),), marker="so 5903 euros", expected=("INT-SUBJ-001",)),
    _p("rounding-unit-word-inline-control", "rounding", "receipt", "control", (MI,), MI, "the same restated as 5902 euros",
       edits=((MI, _MI_B, "$4000(1.036)^{11} = 5902.25$, so 5902 euros to the nearest euro, and"),), marker="so 5902 euros"),
    _p("rounding-no-unit-word", "rounding", "receipt", "answer", (MI,), MI, "the same restated with no word after the number (so 5903 to the nearest euro)",
       edits=((MI, _MI_B, "$4000(1.036)^{11} = 5902.25$, so 5903 to the nearest euro, and"),), marker="so 5903 to", expected=("INT-SUBJ-001",)),
    # found closing it: a rounding to a part of the unit the task counts in ('to the nearest cent' for euros), which had read nothing
    _p("rounding-subunit", "rounding", "receipt", "answer", (MI,), MI, "a result restated to the nearest cent, one cent off (4773.75 for 4773.7401)",
       edits=((MI, _MI_END, "Check: 4000 × 1.036⁵ = 4773.7401, so 4773.75 euros to the nearest cent.\n\n" + _MI_END),), marker="so 4773.75 euros",
       expected=("INT-SUBJ-001",)),
    _p("rounding-subunit-control", "rounding", "receipt", "control", (MI,), MI, "the same restated correctly (4773.74 euros to the nearest cent)",
       edits=((MI, _MI_END, "Check: 4000 × 1.036⁵ = 4773.7401, so 4773.74 euros to the nearest cent.\n\n" + _MI_END),), marker="so 4773.74 euros"),
    # rule row-value: a value at a lettered row of the supplied table
    _es("units-row-value", "units", "answer", _ES_W, "At site C, dissolved oxygen is 3.8 g dm⁻³.", "site C's dissolved oxygen in g dm⁻³ where the table "
        "gives mg dm-3 (the number unchanged)", "is 3.8 g dm⁻³", ("INT-SUBJ-004",)),
    _es("units-row-value-control", "units", "control", _ES_W, "At site C, dissolved oxygen is 3.8 mg dm⁻³.", "the same value in the table's unit",
        "is 3.8 mg dm⁻³"),
    _es("units-row-value-si-control", "units", "control", _ES_W, "At site C, dissolved oxygen is 0.0038 g dm⁻³.", "the same value converted correctly",
        "is 0.0038 g dm⁻³"),
    _es("units-row-statement", "units", "answer", _ES_END, _ES_END + " Dissolved oxygen at site C = 3.8 g dm⁻³.", "the same written '<column> at site C = "
        "<value>'", "site C = 3.8 g dm⁻³", ("INT-SUBJ-004",)),
    _es("units-row-reaches", "units", "answer", "where it reaches 3.8 mg dm⁻³, not at B", "where it reaches 3.8 g dm⁻³, not at B", "the recorded "
        "'where it reaches 3.8 mg dm⁻³' restated in g dm⁻³", "reaches 3.8 g dm⁻³", ("INT-SUBJ-004",)),
    _es("units-row-reaches-control", "units", "control", "where it reaches 3.8 mg dm⁻³, not at B", "where it reaches 0.0038 g dm⁻³, not at B",
        "the same converted correctly", "reaches 0.0038 g dm⁻³"),
    _es("wrong-given-row", "wrong_given", "answer", _ES_W, "At site E, nitrate is 4.1 mg dm⁻³.", "site D's nitrate given for site E", "nitrate is 4.1 mg",
        ("INT-SUBJ-004",)),
    _es("wrong-given-row-control", "wrong_given", "control", _ES_W, "At site E, nitrate is 2.3 mg dm⁻³.", "site E's own nitrate", "nitrate is 2.3 mg"),
    _es("wrong-given-row-prose", "wrong_given", "answer", "nitrate at E (2.3 mg dm⁻³) stays above", "nitrate at E (4.1 mg dm⁻³) stays above", "the recorded "
        "'nitrate at E (2.3 mg dm⁻³)' with site D's value", "nitrate at E (4.1 mg", ("INT-SUBJ-004",)),
    _pb("wrong-given-row-number", "wrong_given", "answer", _PB_END, _PB_END + "\nThe measured count rate at 8 h is 830 counts min⁻¹.", "a value at a numbered "
        "row of the supplied table that the table contradicts (830 for 820 at 8 h)", "at 8 h is 830", ("INT-SUBJ-004",)),
    _pb("wrong-given-row-number-control", "wrong_given", "control", _PB_END, _PB_END + "\nThe measured count rate at 8 h is 820 counts min⁻¹.", "the same "
        "value as the table states it", "at 8 h is 820"),
    # rule exact-carry for exact working: no rounding interval for a number that carries an exact result
    _p("precision-exact-carry", "precision", "receipt", "answer", (PB, _MP), _MP_KEY, "8 ln 2 ÷ ln(1568/816) ≈ 9.5 h (8.49), the 8 carrying the exact T = 8",
       edits=((_MP, "≈ 8.5 h", "≈ 9.5 h"),), marker="≈ 9.5 h", expected=("INT-SUBJ-001",)),
    _p("precision-exact-carry-equal", "precision", "receipt", "answer", (PB, _MP), _MP_KEY, "the same written '=' (= 9.5 h)",
       edits=((_MP, "≈ 8.5 h", "= 9.5 h"),), marker="= 9.5 h", expected=("INT-SUBJ-001",)),
    _p("precision-exact-carry-control", "precision", "receipt", "control", (PB, _MP), _MP_KEY, "≈ 8.4 h, within 5 per cent of 8.49",
       edits=((_MP, "≈ 8.5 h", "≈ 8.4 h"),), marker="≈ 8.4 h"),
    # rule stated-uncertainty: an uncertainty written with a corrected value, against the rule the answer states for it
    _pb("precision-stated-uncertainty", "precision", "answer", "t = 4 h: 1151 − 20 = 1131 ± 23", "t = 4 h: 1151 − 20 = 1131 ± 33", "a stated uncertainty that "
        "contradicts the answer's own rule (2% of 1151 is 23, written 33)", "1131 ± 33", ("INT-SUBJ-004",)),
    _pb("precision-stated-uncertainty-control", "precision", "control", "t = 4 h: 1151 − 20 = 1131 ± 23", "t = 4 h: 1151 − 20 = 1131 ± 20", "the same "
        "uncertainty to one significant figure (20)", "1131 ± 20"),
    _pb("arithmetic-uncertainty-rule", "arithmetic", "answer", "586 − 20 = 566 ± 12", "586 − 20 = 566 ± 11", "the uncertainty truncated against the answer's own "
        "rule (2% of 586 is 11.72, written 11; repair 3's control, before the rule was read)", "566 ± 11", ("INT-SUBJ-004",)),
    # rule operand-precision: a slip under 1/100 that the rounding of the written operands cannot explain
    _pb("arithmetic-exact-operands", "arithmetic", "answer", "t = 4 h: 1151 − 20 = 1131 ± 23", "t = 4 h: 1151 − 20 = 1129 ± 23", "a subtraction of whole "
        "counts slipped by 2 (0.2%: inside τ = 1/100, which their rounding cannot explain)", "1151 − 20 = 1129", ("INT-SUBJ-001",)),
    _p("maths-geometric-slip", "maths", "receipt", "answer", (MI,), MI, "a geometric sequence term 4000 × 1.036³ written 4467.74 (4447.74; 0.45%)",
       edits=((MI, _MI_END, "A geometric sequence check: u₄ = 4000 × 1.036³ = 4467.74.\n\n" + _MI_END),), marker="= 4467.74", expected=("INT-SUBJ-001",)),
    _p("maths-geometric-slip-1pct", "maths", "receipt", "answer", (MI,), MI, "the same term written 4492.00 (0.99%, to the cent)",
       edits=((MI, _MI_END, "A geometric sequence check: u₄ = 4000 × 1.036³ = 4492.00.\n\n" + _MI_END),), marker="= 4492.00", expected=("INT-SUBJ-001",)),
    _p("maths-geometric-slip-control", "maths", "receipt", "control", (MI,), MI, "the same term correct (4447.74)",
       edits=((MI, _MI_END, "A geometric sequence check: u₄ = 4000 × 1.036³ = 4447.74.\n\n" + _MI_END),), marker="= 4447.74"),
)
#: ph-t13's part (d) power line, after which the repair-5 plants of that part are written
_PH_D = "= 16.4 W, so 16 W"
#: ph-p7b's part (d) prediction, before which its repair-5 plants are written
_PB_D = "A measured rate would be about 120"
#: ph-t13's part (d) working (the formula and its evaluation), which some repair-5 plants rewrite
_PH_PART_D = "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"
#: maa-t13's closing note, before which its repair-5 plants are written
_MA_TAIL = "Marks shown are a provisional allocation."


def _phd(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = (), forbidden: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (PH,), PH, desc, edits=((PH, _PH_D, _PH_D + "\n" + line),), marker=marker, expected=expected, forbidden=forbidden)


def _pbd(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _pb(pid, cls, kind, _PB_D, line + "\n" + _PB_D, desc, marker, expected)


def _chx(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (CH,), CH, desc, edits=((CH, _CH_END, _CH_END + "\n\n" + line),), marker=marker, expected=expected)


REPAIR5_PROBES: tuple[Probe, ...] = (
    # rule rearranged-formula: after a correct rearrangement, the line that evaluates the formula is its substitution, never an algebra
    # step from the rearrangement (before: INT-SUBJ-001 on correct working, the other symbols pinned to values of other parts)
    _p("equations-rearranged-formula-control", "equations", "receipt", "control", (PH,), PH, "'From P = V²/R, R = V²/P.' before the power line (before: "
       "INT-SUBJ-001, the power line read as a step from it with R = 2.4 Ω and V = 9.9 V)", edits=((PH, "P = V²/R\n", "P = V²/R\nFrom P = V²/R, R = V²/P.\n"),),
       marker="R = V²/P"),
    _p("equations-rearranging-control", "equations", "receipt", "control", (PH,), PH, "the same written 'Rearranging, R = V²/P.'",
       edits=((PH, "P = V²/R\n", "P = V²/R\nRearranging, R = V²/P.\n"),), marker="Rearranging, R = V²/P"),
    _p("equations-rearranged-current-control", "equations", "receipt", "control", (PH,), PH, "'Rearranging, I = (ε − V)/r.' before part (c)'s substitution "
       "(before: INT-SUBJ-001 on 'V = 12 V − (4.14 A × 0.50 Ω)')", edits=((PH, "V = ε − Ir\n", "V = ε − Ir\nRearranging, I = (ε − V)/r.\n"),),
       marker="I = (ε − V)/r"),
    _p("equations-rearranged-value-control", "equations", "receipt", "control", (PH,), PH, "the power stated as a value right after the rearrangement "
       "(before: INT-SUBJ-001, a step from it)", edits=((PH, "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "P = V²/R\nFrom P = V²/R, R = V²/P.\n"
       "P = 16.4 W"),), marker="P = 16.4 W"),
    _p("equations-rearranged-wrong", "equations", "receipt", "answer", (PH,), PH, "P = V²/R rearranged wrongly (R = P/V²)",
       edits=((PH, "P = V²/R\n", "P = V²/R\nFrom P = V²/R, R = P/V².\n"),), marker="R = P/V²", expected=("INT-SUBJ-001",)),
    _p("equations-rearranged-then-slip", "equations", "receipt", "answer", (PH,), PH, "a correct rearrangement, then the power line with 9.39 V substituted "
       "for 9.93 V", edits=((PH, "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W", "P = V²/R\nRearranging, R = V²/P.\nP = (9.39 V)² / 6.0 Ω = 16.4 W"),),
       marker="(9.39 V)²", expected=("INT-SUBJ-001",)),
    # rule part-value: a symbol reused in a part for another quantity, whose value the line shows by giving the part's own result
    _phd("physics-reused-symbol-control", "physics", "control", "As a check, P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W.", "I reused in part (d) for the current in "
         "the 6.0 Ω resistor, the line re-deriving P = 16.4 W (before: INT-SUBJ-001 against the battery's 4.1 A)", "1.655 A"),
    _phd("physics-reused-symbol-vi-control", "physics", "control", "As a check, P = VI = 9.93 V × 1.655 A = 16.4 W.", "the same with P = VI", "9.93 V × 1.655 A"),
    _phd("physics-reused-symbol", "physics", "answer", "As a check, P = I²R = (1.565 A)² × 6.0 Ω = 14.7 W.", "the reused current written wrongly (1.565 A for "
         "1.655 A), its arithmetic right", "1.565 A", ("INT-SUBJ-001",)),
    # the last chain a restatement restates: the statement's own computing chain, never an older one
    _p("rounding-consequence-control", "rounding", "receipt", "control", (CS,), CS, "a count of passes after the statement's own chain (before: "
       "INT-SUBJ-001, '10' set against '1,000 ÷ 2^10 = 0.98' and naming its claim)",
       edits=((CS, _CS_END, "Also log₂ 1000 ≈ 9.97, so 10 passes.\n\n" + _CS_END),), marker="9.97"),
    _p("rounding-own-chain", "rounding", "receipt", "answer", (CS,), CS, "the statement's own result restated with a wrong rounding (9 for 9.97)",
       edits=((CS, _CS_END, "Also log₂ 1000 ≈ 9.97, so 9.\n\n" + _CS_END),), marker="so 9.", expected=("INT-SUBJ-001",)),
    # rule bound-relation: a relation the prose gives as a quantity's value, in symbols that all have stated values
    _phd("wrong-given-prose-power", "wrong_given", "answer", "The battery's power output is 12 V × I = 60 W.", "the battery's power with a wrong value, "
         "I = 4.1 A stated (before: neither a check nor an ST code)", "12 V × I = 60 W", ("INT-SUBJ-001",)),
    _phd("wrong-given-prose-power-control", "wrong_given", "control", "The battery's power output is 12 V × I = 49.7 W.", "the same with the right value",
         "12 V × I = 49.7 W"),
    _phd("arithmetic-prose-lost-volts", "arithmetic", "answer", "The lost volts are 0.50 Ω × I = 3.0 V.", "the lost volts with a wrong value (before: neither a "
         "check nor an ST code)", "0.50 Ω × I = 3.0 V", ("INT-SUBJ-001",)),
    _phd("arithmetic-prose-lost-volts-control", "arithmetic", "control", "The lost volts are 0.50 Ω × I = 2.07 V.", "the same with the right value",
         "0.50 Ω × I = 2.07 V"),
    _phd("equations-prose-solved-control", "equations", "control", "The power is 16.4 W = I² × 6.0 Ω, so I = 1.65 A.", "an equation its part solves for "
         "the reused I: no check against the battery's current", "I² × 6.0 Ω"),
    _phd("receipts-unknown-after-number", "receipts", "answer", "E = 0.5 × k × 0.04 = 1.0 J", "a product with an unknown after a spaced '×' (before: "
         "read as the magnification '0.5×', E bound to 0.5, ST-PARSE-001)", "0.5 × k", ("ST-UNDEC-002",), forbidden=("ST-PARSE-001",)),
    # rule prose-conversion
    _chx("units-prose-conversion", "units", "answer", "The mixture is 55.0 cm³, that is 0.550 dm³.", "a conversion written in prose, a factor of ten wrong "
         "(before: no relation read)", "0.550 dm³", ("INT-SUBJ-001",)),
    _chx("units-prose-conversion-control", "units", "control", "The mixture is 55.0 cm³, that is 0.0550 dm³.", "the same conversion right", "0.0550 dm³"),
    _chx("units-prose-conversion-bracket", "units", "answer", "The mixture is 55.0 cm³ (0.550 dm³).", "the same written in brackets", "(0.550 dm³)",
         ("INT-SUBJ-001",)),
    _chx("units-prose-range-control", "units", "control", "It was heated from 20.0 °C to 60.0 °C, that is 40.0 K.", "a value after a range, which may restate "
         "the change: not read as a conversion of 60.0 °C", "40.0 K"),
    # rules rounding-cue (a value stated for a symbol) and same-place
    _phd("rounding-stated-symbol", "rounding", "answer", "To 3 s.f., P = 16.5 W.", "the power restated to three significant figures with a wrong last digit "
         "(before: no check)", "P = 16.5 W", ("INT-SUBJ-001",)),
    _phd("rounding-stated-symbol-control", "rounding", "control", "To 3 s.f., P = 16.4 W.", "the same restated right", "P = 16.4 W"),
    _phd("rounding-stated-prose", "rounding", "answer", "To 3 s.f., the power is 16.5 W.", "the same in prose (before: held, the two half-widths added)",
         "the power is 16.5 W", ("INT-SUBJ-001",)),
    _phd("rounding-stated-coarser-control", "rounding", "control", "To 2 s.f., P = 16 W.", "a coarser rounding, right", "P = 16 W"),
    # rule processed-data: a percentage or a ratio of the raw cell is not its processed value; a per cent taken of a number
    _pbd("precision-percent-of-cell-control", "precision", "control", "2% of 1620 is 0.02 × 1620 = 32.4 counts min⁻¹.", "the uncertainty of the measured "
         "1620 in part (d), by the answer's own rule (before: INT-SUBJ-004, set against the corrected 1600)", "0.02 × 1620"),
    _pbd("precision-percent-sign-control", "precision", "control", "The uncertainty is 1620 × 2% = 32.4 counts min⁻¹.", "the same with the per cent sign "
         "(before: INT-SUBJ-004 and a false INT-SUBJ-001, 2% read as 2)", "1620 × 2%"),
    _pbd("precision-ratio-of-cells-control", "precision", "control", "The ratio 1620/820 = 1.98 is about 2.", "a ratio of two measured cells (before: "
         "INT-SUBJ-004 twice)", "1620/820"),
    _pbd("arithmetic-percent-of-cell", "arithmetic", "answer", "2% of 1620 is 0.02 × 1620 = 34.2 counts min⁻¹.", "the same percentage computed wrongly",
         "34.2 counts", ("INT-SUBJ-001",)),
    # the classes, closed whole (found closing the four problems): a rearrangement with no lone symbol, a reused symbol with no lone head
    # or whose value its part computes, a count after a condition or an order relation, an equation for a reused symbol about the part's
    # result, a run in a symbol with no value given as a quantity's value, a conversion with a verb or a bracketed 'or', a precision in
    # brackets or before the value without a comma, a percentage by division, a ratio to the raw cell and a '±' per cent
    _p("equations-rearranged-product-control", "equations", "receipt", "control", (PH,), PH, "'V² = P × R' before the power line (before: INT-SUBJ-001, the "
       "power line a step from it)", edits=((PH, "P = V²/R\n", "P = V²/R\nV² = P × R\n"),), marker="V² = P × R"),
    _p("equations-rearranged-difference-control", "equations", "receipt", "control", (PH,), PH, "'I × r = ε − V' before part (c)'s substitution (before: "
       "INT-SUBJ-001)", edits=((PH, "V = ε − Ir\n", "V = ε − Ir\nI × r = ε − V\n"),), marker="I × r = ε − V"),
    _phd("physics-reused-headless-control", "physics", "control", "As a check, I²R = (1.655 A)² × 6.0 Ω = 16.4 W.", "the reused current in a check line "
         "with no lone head (before: INT-SUBJ-001 against the battery's 4.1 A)", "As a check, I²R"),
    _phd("physics-reused-headless", "physics", "answer", "As a check, I²R = (1.565 A)² × 6.0 Ω = 14.7 W.", "the same with the current written wrongly",
         "(1.565 A)²", ("INT-SUBJ-001",)),
    _p("physics-reused-part-result-control", "physics", "receipt", "control", (PH,), PH, "the current in the 6.0 Ω resistor computed in the part, then "
       "substituted for I (before: INT-SUBJ-001 against the battery's 4.1 A)", edits=((PH, "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W",
       "The current in it is 9.93 V ÷ 6.0 Ω = 1.655 A.\nP = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W"),), marker="P = I²R"),
    _p("physics-reused-part-result", "physics", "receipt", "answer", (PH,), PH, "the same with another current substituted (1.565 A)",
       edits=((PH, "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "The current in it is 9.93 V ÷ 6.0 Ω = 1.655 A.\nP = I²R = (1.565 A)² × 6.0 Ω = "
       "14.7 W, so 15 W"),), marker="(1.565 A)²", expected=("INT-SUBJ-001",)),
    _p("rounding-count-after-condition-control", "rounding", "receipt", "control", (CS,), CS, "a count after a condition (before: INT-SUBJ-001, '10' "
       "set against '1,000 ÷ 2^10 = 0.98' three statements before)", edits=((CS, _CS_END, "With n = 1000 items, so 10 passes are needed.\n\n" + _CS_END),),
       marker="10 passes are needed"),
    _p("rounding-count-after-order-control", "rounding", "receipt", "control", (CS,), CS, "a count after a chain ending on an order relation (before: "
       "INT-SUBJ-001, the same older chain)", edits=((CS, _CS_END, "Also 2^10 = 1024 ≥ 1000, so 10 passes suffice.\n\n" + _CS_END),), marker="1024 ≥ 1000"),
    _phd("equations-prose-reused-control", "equations", "control", "The power in it is I² × 6.0 Ω = 16.4 W.", "an equation for the current in the 6.0 Ω "
         "resistor about the part's own P (before this repair's final form: INT-SUBJ-001 by rule bound-relation against the battery's 4.1 A)",
         "I² × 6.0 Ω = 16.4 W"),
    _phd("wrong-given-prose-power-then", "wrong_given", "answer", "The power output of the battery is then 12 V × I = 60 W.", "the battery's power after "
         "'is then', a wrong value", "12 V × I = 60 W", ("INT-SUBJ-001",)),
    _phd("receipts-unknown-prose-head", "receipts", "answer", "The energy is 0.5 × k × 0.04 = 1.0 J.", "a run given as a quantity's value in a symbol with no "
         "stated value (before: neither a check nor an ST code)", "0.5 × k", ("ST-UNDEC-002",)),
    _chx("units-prose-verb", "units", "answer", "The volume of 55.0 cm³ is 0.550 dm³.", "a conversion stated with 'is', a factor of ten wrong (before: no "
         "relation read)", "0.550 dm³", ("INT-SUBJ-001",)),
    _chx("units-prose-verb-control", "units", "control", "The volume of 55.0 cm³ is 0.0550 dm³.", "the same conversion right", "0.0550 dm³"),
    _chx("units-prose-bracket-or", "units", "answer", "The mixture is 55.0 cm³ (or 0.550 dm³).", "the same in brackets after 'or'", "(or 0.550 dm³)",
         ("INT-SUBJ-001",)),
    _phd("rounding-bracket-precision", "rounding", "answer", "P = 16.5 W (3 s.f.)", "a precision in brackets after the value, a wrong last digit (before: no "
         "check)", "P = 16.5 W (3 s.f.)", ("INT-SUBJ-001",)),
    _phd("rounding-bracket-precision-control", "rounding", "control", "P = 16.4 W (3 s.f.)", "the same right", "P = 16.4 W (3 s.f.)"),
    _phd("rounding-sf-no-comma", "rounding", "answer", "To 3 s.f. the power is 16.5 W.", "a rounding before the value with no comma after 's.f.' (before: "
         "held, the full stop of 's.f.' read as a sentence's end)", "the power is 16.5 W", ("INT-SUBJ-001",)),
    _pbd("precision-ratio-to-cell-control", "precision", "control", "The fractional uncertainty is 32.4/1620 = 0.020.", "a value set over the raw cell "
         "(before: INT-SUBJ-004, set against the corrected 1600)", "32.4/1620"),
    _pbd("precision-percent-by-division-control", "precision", "control", "The uncertainty is 1620/50 = 32.4 counts min⁻¹.", "2% of the raw cell taken as a "
         "division by 50 (before: INT-SUBJ-004)", "1620/50"),
    _pbd("precision-plus-minus-percent-control", "precision", "control", "The uncertainty in 1620 is ±2% × 1620 = ±32.4 counts min⁻¹.", "a '±' per cent "
         "of the raw cell (before: INT-SUBJ-001, 2% read as 2 or one side converted to SI)", "±2% × 1620"),
    # the classes closed whole, a second pass (found measuring each class again on the repaired front end): a rearrangement stated after
    # 'Solving for R' or 'Making R the subject', a relation given as a quantity's value after 'are equal to', a conversion after 'which
    # equals' or a semicolon, the cell processed inside the line, the bounds of the measured value and a share of it written '× 2 ÷ 100'
    _p("equations-rearranged-solving-wrong", "equations", "receipt", "answer", (PH,), PH, "a wrong rearrangement after 'Solving for R,' (before: no step read "
       "once the evaluation after it is no step)", edits=((PH, "P = V²/R\n", "P = V²/R\nSolving for R, R = P/V².\n"),), marker="R = P/V²",
       expected=("INT-SUBJ-001",)),
    _p("equations-rearranged-subject-control", "equations", "receipt", "control", (PH,), PH, "the correct rearrangement after 'Making R the subject,'",
       edits=((PH, "P = V²/R\n", "P = V²/R\nMaking R the subject, R = V²/P.\n"),), marker="R = V²/P"),
    _phd("arithmetic-prose-lost-volts-equal", "arithmetic", "answer", "The lost volts are equal to 0.50 Ω × I = 3.0 V.", "the lost volts after 'are equal to', "
         "a wrong value (before: neither a check nor an ST code)", "0.50 Ω × I = 3.0 V", ("INT-SUBJ-001",)),
    _phd("arithmetic-prose-lost-volts-equal-control", "arithmetic", "control", "The lost volts are equal to 0.50 Ω × I = 2.07 V.", "the same with the right value",
         "0.50 Ω × I = 2.07 V"),
    _chx("units-prose-which-equals", "units", "answer", "The mixture is 55.0 cm³, which equals 0.550 dm³.", "a conversion after 'which equals', a factor of ten "
         "wrong (before: no relation read)", "0.550 dm³", ("INT-SUBJ-001",)),
    _chx("units-prose-semicolon", "units", "answer", "The mixture is 55.0 cm³; that is 0.550 dm³.", "the same after a semicolon and 'that is' (before: no relation "
         "read)", "0.550 dm³", ("INT-SUBJ-001",)),
    _chx("units-prose-which-equals-control", "units", "control", "The mixture is 55.0 cm³, which equals 0.0550 dm³.", "the same conversion right", "0.0550 dm³"),
    _pbd("precision-inline-correction-control", "precision", "control", "C = (1620 − 20) × (1/2)⁴ = 100 counts min⁻¹.", "the measured 1620 corrected inside the "
         "line (before: INT-SUBJ-004, set against the corrected 1600)", "(1620 − 20) × (1/2)⁴"),
    _pbd("precision-upper-bound-control", "precision", "control", "The upper bound is 1620 + 32.4 = 1652.4 counts min⁻¹.", "the upper bound of the measured value "
         "(before: INT-SUBJ-004, set against the corrected 1600)", "1620 + 32.4"),
    _pbd("precision-share-by-hundred-control", "precision", "control", "The uncertainty is 1620 × 2 ÷ 100 = 32.4 counts min⁻¹.", "2% of the raw cell written "
         "'× 2 ÷ 100' (before: INT-SUBJ-004)", "1620 × 2 ÷ 100"),
    _pbd("wrong-given-measured-sixteenth", "wrong_given", "answer", "C = 1620 / 16 = 101 counts min⁻¹.", "(d) takes the measured 1620 for the corrected 1600, "
         "written as a division", "1620 / 16", ("INT-SUBJ-004",)),
    # the classes closed whole, a third pass (found measuring each class again on the resumed tree): a wrong rearrangement in words no
    # step reads (caught before this repair through the evaluation after it), the inverse's equation with the variables swapped, a
    # reused symbol shown by its part's prose, another part's value of its head or a computation in the line, a prose relation that is
    # its part's answer, a value after 'so' following its own statement's value or a part of it, a rounding of a prose value, measured
    # values taken on purpose, a ratio set against a number, a conversion to a unit the prose names, an applied symbol no definition
    # makes a function
    _p("equations-rearranges-to-wrong", "equations", "receipt", "answer", (PH,), PH, "a wrong rearrangement after 'This rearranges to' (before this repair "
       "caught through the evaluation after it; after rule rearranged-formula, unread until the third pass)",
       edits=((PH, "P = V²/R\n", "P = V²/R\nThis rearranges to R = P/V².\n"),), marker="R = P/V²", expected=("INT-SUBJ-001",)),
    _p("equations-rearranges-to-control", "equations", "receipt", "control", (PH,), PH, "the same rearrangement right",
       edits=((PH, "P = V²/R\n", "P = V²/R\nThis rearranges to R = V²/P.\n"),), marker="R = V²/P"),
    _p("equations-or-form-wrong", "equations", "receipt", "answer", (PH,), PH, "a wrong rearrangement after 'or' on the next line",
       edits=((PH, "P = V²/R\n", "P = V²/R\nor R = P/V²\n"),), marker="R = P/V²", expected=("INT-SUBJ-001",)),
    _p("equations-ie-form-wrong", "equations", "receipt", "answer", (PH,), PH, "a wrong rearrangement after ', i.e.' on the formula's line",
       edits=((PH, "P = V²/R\n", "P = V²/R, i.e. R = P/V²\n"),), marker="R = P/V²", expected=("INT-SUBJ-001",)),
    _p("maths-inverse-swap-control", "maths", "receipt", "control", (MA,), MA, "the inverse's equation with x and y swapped, then solved (before: "
       "INT-SUBJ-001, the swapped equation read as a step from y = 2x + 1)",
       edits=((MA, _MA_TAIL, "y = 2x + 1\nSwap x and y: x = 2y + 1.\nSo y = (x − 1)/2.\n\n" + _MA_TAIL),), marker="Swap x and y"),
    _p("maths-inverse-swap-step", "maths", "receipt", "answer", (MA,), MA, "the same, solved wrongly",
       edits=((MA, _MA_TAIL, "y = 2x + 1\nSwap x and y: x = 2y + 1.\nSo y = (x + 1)/2.\n\n" + _MA_TAIL),), marker="(x + 1)/2", expected=("INT-SUBJ-001",)),
    _p("physics-reused-prose-named-control", "physics", "receipt", "control", (PH,), PH, "the current the prose states for the 6.0 Ω resistor, then substituted "
       "for I (before: INT-SUBJ-001 against the battery's 4.1 A)", edits=((PH, _PH_PART_D, "The current in the 6.0 Ω resistor is 1.655 A.\n"
       "P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W"),), marker="1.655 A."),
    _p("physics-reused-prose-named", "physics", "receipt", "answer", (PH,), PH, "the same with another current substituted (1.565 A)",
       edits=((PH, _PH_PART_D, "The current in the 6.0 Ω resistor is 1.655 A.\nP = I²R = (1.565 A)² × 6.0 Ω = 14.7 W, so 15 W"),), marker="(1.565 A)²",
       expected=("INT-SUBJ-001",)),
    _p("physics-reused-head-other-part-control", "physics", "receipt", "control", (PH,), PH, "V = IR in part (d) re-deriving part (c)'s V with the "
       "resistor's current (before: INT-SUBJ-001 against the battery's 4.1 A)", edits=((PH, _PH_PART_D, "V = IR = 1.655 A × 6.0 Ω = 9.93 V\nP = V²/R\n"
       "P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"),), marker="V = IR"),
    _p("physics-reused-inline-control", "physics", "receipt", "control", (PH,), PH, "the resistor's current computed in the line (before: INT-SUBJ-001 against "
       "the battery's 4.1 A)", edits=((PH, _PH_PART_D, "P = I²R = (9.93 V ÷ 6.0 Ω)² × 6.0 Ω = 16.4 W, so 16 W"),), marker="(9.93 V ÷ 6.0 Ω)²"),
    _p("wrong-given-prose-asked-control", "wrong_given", "receipt", "control", (PH,), PH, "part (d)'s answer as a prose relation in the reused I (before this "
       "pass: INT-SUBJ-001 by rule bound-relation against the battery's 4.1 A)", edits=((PH, _PH_PART_D, "The power in the 6.0 Ω resistor is 9.93 V × I = 16.4 W."),),
       marker="9.93 V × I"),
    _pbd("rounding-own-value-control", "rounding", "control", "The measured rate at t = 0 h is 1620 counts min⁻¹, so the corrected rate is 1600 counts min⁻¹.",
         "a value after 'so' following its own statement's value (before: INT-SUBJ-001, 1600 set against '= 100 counts min⁻¹')", "so the corrected rate is 1600"),
    _phd("rounding-part-of-it-control", "rounding", "control", "So 4.4 W of it is lost as heat in the wires.", "a part of the power after 'So' (before: "
         "INT-SUBJ-001, 4.4 W set against '= 16.4 W')", "4.4 W of it"),
    _phd("rounding-prose-value", "rounding", "answer", "The power is 16.4 W, so 17 W to 2 s.f.", "a prose value restated with a stated rounding, a wrong digit "
         "(before: no check)", "17 W to 2 s.f.", ("INT-SUBJ-001",)),
    _phd("rounding-prose-value-control", "rounding", "control", "The power is 16.4 W, so 16 W to 2 s.f.", "the same right", "16 W to 2 s.f."),
    _pbd("precision-raw-processed-ratio-control", "precision", "control", "The ratio 1620/1600 = 1.0125.", "the raw cell over its corrected value (before: "
         "INT-SUBJ-004)", "1620/1600"),
    _pbd("precision-measured-named-control", "precision", "control", "The measured rate fell by 1620 − 820 = 800 counts min⁻¹ in 8 h.", "a line naming the measured "
         "quantity itself (before: INT-SUBJ-004)", "1620 − 820"),
    _phd("receipts-ratio-number", "receipts", "answer", "The ratio of the resistances is 4.0 : 6.0 = 0.76.", "a ratio set against a number (before: neither a check "
         "nor an ST code)", "4.0 : 6.0", ("ST-UNDEC-001",)),
    _phd("receipts-applied-unknown", "receipts", "answer", "The energy is ½k(0.20)² = 1.0 J.", "a prose relation in a symbol written as applied, which no "
         "definition makes a function (before: neither a check nor an ST code)", "½k(0.20)²", ("ST-UNDEC-002",)),
    _chx("units-prose-to-unit", "units", "answer", "Converting 55.0 cm³ to dm³ gives 0.550 dm³.", "a conversion to a unit the prose names, a factor of ten wrong "
         "(before: no relation read)", "0.550 dm³", ("INT-SUBJ-001",)),
    _chx("units-prose-to-unit-control", "units", "control", "Converting 55.0 cm³ to dm³ gives 0.0550 dm³.", "the same right", "0.0550 dm³"),
)
#: ph-t13's part (a) heading, before which the repair-6 Data lines are written
_PH_A = "(a) [2]\nFor resistors"
#: maa-p7b's part (a) result, which the repair-6 fraction-unit probes restate with a value
_MB_K = "k = (ln 2)/8 h⁻¹  A1"
#: ph-p7b's decay constant, after which the repair-6 SI fraction-unit probes are written
_PB_LAMBDA = "λ = 0.693/8.0 h = 0.087 h⁻¹"
_NAND_TABLE = "The NAND truth table:\n\n| A | B | A NAND B |\n|---|---|---|\n| 0 | 0 | 1 |\n| 0 | 1 | 1 |\n| 1 | 0 | 1 |\n| 1 | 1 | {r} |"
_XNOR_TABLE = "| A | B | A XNOR B |\n|---|---|---|\n| 0 | 0 | 1 |\n| 0 | 1 | {r} |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |"


def _pha(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (PH,), PH, desc, edits=((PH, _PH_A, line + "\n\n" + _PH_A),), marker=marker, expected=expected)


def _bix(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (BI,), BI, desc, edits=((BI, _BI_END, _BI_END + "\n\n" + line),), marker=marker, expected=expected)


def _mia(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (MI,), MI, desc, edits=((MI, _MI_END, line + "\n\n" + _MI_END),), marker=marker, expected=expected)


def _mbk(pid: str, cls: str, kind: str, new: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (PB, _MP), _MP_KEY, desc, edits=((_MP, _MB_K, new),), marker=marker, expected=expected)


#: STEM repair 6 (design section 37): the sixth independent test's plants and a control for each, on the class whose cause it found, and the
#: shapes of the same classes found closing them. Rule prose-given: a Given value written in prose in a Given statement (a data list or the
#: first clause of a Given clause) is read as the same Given written with '='; rule part-given: a symbol reused in a part for a value the
#: request states that the part names nowhere, where its question names another, is checked at warning severity; rule fraction-unit: a
#: unit written after a compact fraction may be the fraction's own; rule boolean-gates: NAND, NOR, XNOR (↑, ↓) are read.
REPAIR6_PROBES: tuple[Probe, ...] = (
    # rule prose-given (before: neither a check nor an ST code for every prose form; the agent's finding_missing refuted)
    _pha("givens-data-list", "givens", "answer", "Data: emf 15 V, internal resistance 0.50 Ω.", "a Data list with the emf contradicting the request's 12 V "
         "(before: neither a check nor an ST code)", "emf 15 V", ("INT-SUBJ-004",)),
    _pha("givens-data-list-control", "givens", "control", "Data: emf 12 V, internal resistance 0.50 Ω.", "the same list with the request's values", "emf 12 V"),
    _pha("givens-data-named", "givens", "answer", "Data: emf 12 V, internal resistance 6.0 Ω.", "the internal resistance given another value the request "
         "states (the 6.0 ohm resistor's): set against the request's internal resistance, which its words name (rule named-given)", "6.0 Ω.",
         ("INT-SUBJ-004",)),
    _pha("givens-data-juxtaposed", "givens", "answer", "Data: emf 12 V internal resistance 0.40 Ω.", "two items with no comma between them, the second "
         "contradicting", "0.40 Ω", ("INT-SUBJ-004",)),
    _bix("givens-given-copula", "givens", "answer", "Given: the mass of seeds is 12 g.", "a Given with 'is' contradicting the supplied text's 10 g (before: "
         "neither a check nor an ST code)", "is 12 g", ("INT-SUBJ-004",)),
    _bix("givens-given-copula-control", "givens", "control", "Given: the mass of seeds is 10 g.", "the same with the supplied 10 g", "is 10 g"),
    _bix("givens-given-colon", "givens", "answer", "Given: mass of seeds: 12 g.", "a Given in a colon list (before: neither a check nor an ST code)",
         "seeds: 12 g", ("INT-SUBJ-004",)),
    _bix("givens-given-colon-control", "givens", "control", "Given: mass of seeds: 10 g.", "the same with the supplied 10 g", "seeds: 10 g"),
    _chx("givens-value-of", "givens", "answer", "Given: 15.0 cm³ of acid.", "a value written before its name, contradicting the supplied 5.0 cm³ (before: "
         "neither a check nor an ST code)", "15.0 cm³ of acid", ("INT-SUBJ-004",)),
    _chx("givens-value-of-control", "givens", "control", "Given: 5.0 cm³ of acid.", "the same with the supplied 5.0 cm³", "5.0 cm³ of acid"),
    _bix("givens-we-know", "givens", "answer", "We know the mass of seeds was 12 g.", "'We know' with a quantity the request names in no words before a value "
         "(before: neither a check nor an ST code)", "was 12 g", ("INT-SUBJ-004",)),
    _bix("givens-we-know-control", "givens", "control", "We know the mass of seeds was 10 g.", "the same with the supplied 10 g", "was 10 g"),
    _chx("givens-known-concentration", "givens", "answer", "Known: the acid is 0.20 mol dm⁻³.", "a Known list item contradicting the supplied 2.0 mol dm-3",
         "0.20 mol dm⁻³", ("INT-SUBJ-004",)),
    _chx("givens-known-concentration-control", "givens", "control", "Known: the acid is 2.0 mol dm⁻³.", "the same with the supplied value", "2.0 mol dm⁻³."),
    _bix("givens-list-items", "givens", "answer", "Given:\n- mass of seeds 12 g\n- five repeats at each temperature", "an item of the list a 'Given:' line "
         "opens, contradicting the supplied 10 g", "mass of seeds 12 g", ("INT-SUBJ-004",)),
    _bix("givens-list-items-control", "givens", "control", "Given:\n- mass of seeds 10 g\n- five repeats at each temperature", "the same with the supplied 10 g",
         "mass of seeds 10 g"),
    _chx("givens-prose-uncertainty", "givens", "answer", "Given: thermometer uncertainty ±0.2 °C.", "an uncertainty written in prose with ±, against the "
         "supplied +/-0.5 °C (before: a bare 0.5 or 0.2, its unit lost)", "±0.2 °C", ("INT-SUBJ-004",)),
    _chx("givens-prose-uncertainty-control", "givens", "control", "Given: thermometer uncertainty ±0.5 °C.", "the same with the supplied +/-0.5 °C", "±0.5 °C"),
    _pha("givens-clause-result-control", "givens", "control", "Given that the emf is 12 V, the current is 4.1 A.", "a Given clause: only its first clause "
         "is a Given (the current is the statement's own result, never set against the request)", "the current is 4.1 A"),
    _mia("givens-prose-percent", "givens", "answer", "Data: interest rate 4.6% per year, principal 4000 euros.", "a percentage in a Data list contradicting the "
         "request's 3.6%", "rate 4.6%", ("INT-SUBJ-004",)),
    _mia("givens-prose-percent-control", "givens", "control", "Data: interest rate 3.6% per year, principal 4000 euros.", "the same with the request's 3.6%",
         "rate 3.6%"),
    _bix("receipts-prose-given-unset", "receipts", "answer", "Given: the volume of water is 25.0 cm³.", "a prose Given of a kind the request states no value of: "
         "named unchecked (before: neither a check nor an ST code)", "25.0 cm³", ("ST-UNDEC-003",)),
    # rule part-given (before: any value the request states passed for a symbol reused in a part, with no word)
    _p("wrong-given-part-other-resistor", "wrong_given", "receipt", "answer", (PH,), PH, "the other resistor's 4.0 Ω substituted in the part that asks for the "
       "6.0 ohm resistor (before: stem-sub ENTAILED, R dropped from the check)", edits=((PH, "P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W",
                                                                                         "P = (9.93 V)² / 4.0 Ω = 24.7 W, so 25 W"),),
       marker="24.7 W", expected=("INT-SUBJ-004",)),
    _p("wrong-given-part-internal", "wrong_given", "receipt", "answer", (PH,), PH, "the internal resistance substituted there (before: ENTAILED)",
       edits=((PH, "P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "P = (9.93 V)² / 0.50 Ω = 197 W, so 200 W"),), marker="197 W", expected=("INT-SUBJ-004",)),
    _p("wrong-given-part-current", "wrong_given", "receipt", "answer", (PH,), PH, "the other resistor in a current computed in that part",
       edits=((PH, _PH_PART_D, "I = V/R = 9.93 V / 4.0 Ω = 2.48 A\n" + _PH_PART_D),), marker="2.48 A", expected=("INT-SUBJ-004",)),
    _p("wrong-given-part-current-control", "wrong_given", "receipt", "control", (PH,), PH, "the same with the 6.0 Ω resistor the part's question names",
       edits=((PH, _PH_PART_D, "I = V/R = 9.93 V / 6.0 Ω = 1.655 A\n" + _PH_PART_D),), marker="1.655 A"),
    _phd("wrong-given-part-named-control", "wrong_given", "control", "For comparison, the 4.0 Ω resistor dissipates P = (9.93 V)² / 4.0 Ω = 24.7 W.",
         "another request value the part's working names before the line", "dissipates P"),
    # rule fraction-unit (before: ST-DIM-001 on correct working in the recorded answer's own notation, and a false INT-SUBJ-001 in SI)
    _mbk("dimensions-fraction-unit-control", "dimensions", "control", "k = (ln 2)/8 h⁻¹ = 0.0866 h⁻¹  A1", "k given its value after the recorded '(ln 2)/8 h⁻¹' "
         "(before: ST-DIM-001)", "= 0.0866 h⁻¹"),
    _mbk("dimensions-fraction-unit-slip", "dimensions", "answer", "k = (ln 2)/8 h⁻¹ = 0.0966 h⁻¹  A1", "the same with a wrong value", "= 0.0966 h⁻¹",
         ("INT-SUBJ-001",)),
    _pb("dimensions-fraction-unit-si-control", "dimensions", "control", _PB_LAMBDA, _PB_LAMBDA + "\nIn SI, λ = (ln 2)/8.0 h⁻¹ = 2.4 × 10⁻⁵ s⁻¹.",
        "the decay constant in SI after a fraction with its unit (before: INT-SUBJ-001 on the arithmetic and the substitution, two ST-DIM-001)", "In SI"),
    _pb("dimensions-fraction-unit-si-slip", "dimensions", "answer", _PB_LAMBDA, _PB_LAMBDA + "\nIn SI, λ = (ln 2)/8.0 h⁻¹ = 2.4 × 10⁻⁴ s⁻¹.",
        "the same converted wrongly", "In SI", ("INT-SUBJ-001",)),
    _chx("dimensions-fraction-rate-control", "dimensions", "control", "The rate is 1/40 s⁻¹ = 0.025 s⁻¹.", "a rate after a fraction with its unit (before: "
         "ST-DIM-001)", "1/40 s⁻¹"),
    _chx("dimensions-fraction-rate-slip", "dimensions", "answer", "The rate is 1/40 s⁻¹ = 0.25 s⁻¹.", "the same with a wrong value", "0.25 s⁻¹",
         ("INT-SUBJ-001",)),
    _chx("dimensions-fraction-both-wrong", "dimensions", "answer", "The rate is 1/40 s⁻¹ = 0.025 m.", "a fraction with a unit whose reading agrees with the "
         "other side under neither reading", "0.025 m", ("ST-DIM-001",)),
    # rule boolean-gates (before: ST-PARSE-001 or ST-UNDEC-001 on the plant and its control alike)
    _cs("boolean-nand-eval", "answer", "With A = 0 and B = 1, A NAND B = 0.", "a NAND evaluated wrongly (before: ST-PARSE-001)", "A NAND B = 0",
        ("INT-SUBJ-001",)),
    _cs("boolean-nand-eval-control", "control", "With A = 0 and B = 1, A NAND B = 1.", "the same right (before: ST-PARSE-001)", "A NAND B = 1"),
    _cs("boolean-nor-eval", "answer", "With A = 0 and B = 0, A NOR B = 0.", "a NOR evaluated wrongly (before: ST-PARSE-001)", "A NOR B = 0", ("INT-SUBJ-001",)),
    _cs("boolean-nor-eval-control", "control", "With A = 0 and B = 0, A NOR B = 1.", "the same right (before: ST-PARSE-001)", "A NOR B = 1"),
    _cs("boolean-xnor-eval", "answer", "With A = 1 and B = 0, A XNOR B = 1.", "an XNOR evaluated wrongly (before: ST-PARSE-001)", "XNOR B = 1", ("INT-SUBJ-001",)),
    _cs("boolean-xnor-eval-control", "control", "With A = 1 and B = 0, A XNOR B = 0.", "the same right (before: ST-PARSE-001)", "XNOR B = 0"),
    _cs("boolean-nor-identity", "answer", "By definition, A NOR B = NOT A OR NOT B.", "a wrong NOR identity (before: ST-PARSE-001)", "A NOR B =",
        ("INT-SUBJ-001",)),
    _cs("boolean-nor-identity-control", "control", "By definition, A NOR B = NOT (A OR B).", "the right one (before: ST-PARSE-001)", "A NOR B ="),
    _cs("boolean-nand-table", "answer", _NAND_TABLE.format(r="1"), "a NAND truth table with the row 1, 1 -> 1 (before: ST-UNDEC-001)", "A NAND B",
        ("INT-SUBJ-001",)),
    _cs("boolean-nand-table-control", "control", _NAND_TABLE.format(r="0"), "the right table (before: ST-UNDEC-001)", "A NAND B"),
    _cs("boolean-xnor-table", "answer", _XNOR_TABLE.format(r="1"), "an XNOR truth table with the row 0, 1 -> 1", "A XNOR B", ("INT-SUBJ-001",)),
    _cs("boolean-xnor-table-control", "control", _XNOR_TABLE.format(r="0"), "the right table", "A XNOR B"),
    _cs("boolean-sheffer-identity", "answer", "With the Sheffer stroke, A ↑ B = NOT A AND NOT B.", "a wrong identity of the NAND symbol (before: read from "
        "B, 'B = NOT A AND NOT B')", "A ↑ B", ("INT-SUBJ-001",)),
    _cs("boolean-sheffer-identity-control", "control", "With the Sheffer stroke, A ↑ B = NOT A OR NOT B.", "the right one (before: INT-SUBJ-001, read from B)",
        "A ↑ B"),
    _p("receipts-gate-order", "receipts", "receipt", "answer", (CS,), CS, "NAND written twice with no brackets: two readings, named (ST-PARSE-002)",
       edits=((CS, _CS_END, "So A NAND B NAND C = 1.\n\n" + _CS_END),), marker="NAND C = 1", expected=("ST-PARSE-002",)),
)
#: ph-t13's part (b) working (the law, rearranged, then evaluated), which the repair-7 plants of rule solved-law rewrite
_PH_PART_B = "ε = I(R + r), so I = ε/(R + r)\nI = 12 V / 2.9 Ω = 4.1 A"
#: ph-t13's part (c) working (the formula, then evaluated)
_PH_PART_C = "V = ε − Ir\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
#: ph-t13's part (c) evaluation, after which the repair-7 finer restatements are written
_PH_C = "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
#: ph-p7b's part (c) working: the law, rearranged, then evaluated
_PB_REARR = "T½ = ln 2/λ, so λ = ln 2/T½"
_PB_PART_C = "T½ = ln 2/λ, so λ = ln 2/T½\nλ = 0.693/8.0 h = 0.087 h⁻¹"
#: maa-t13's last line of working, after which the repair-7 derivative plants are written
_MA_DIST = "Distance travelled = 8 m  A1"
#: a derivative is named unchecked (ST-UNDEC-001), never failed
_NO_FAIL = ("INT-SUBJ-001", "INT-SUBJ-004")


def _phc(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (PH,), PH, desc, edits=((PH, _PH_C, _PH_C + line),), marker=marker, expected=expected)


def _mad(pid: str, cls: str, line: str, desc: str, marker: str, expected: tuple[str, ...], forbidden: tuple[str, ...] = (), kind: str = "answer") -> Probe:
    return _p(pid, cls, "receipt", kind, (MA,), MA, desc, edits=((MA, _MA_DIST, _MA_DIST + "\n" + line),), marker=marker, expected=expected,
              forbidden=forbidden)


#: STEM repair 7 (design section 38): the seventh independent test's plants and a control for each, on the class whose cause it found, and
#: the shapes of the same classes found closing them. Rule solved-law: a line that evaluates a symbol right after a law stating it but not
#: on its own evaluates the law solved for it (its substitution is checked, never an algebra step); rules leibniz and prime-derivative: a
#: derivative in any Leibniz form or a primed letter applied to a bracket is a derivative (ST-UNDEC-001, or its value set against the
#: answer's own derivative formula); rule finer-restatement: a value restated with a rounding finer than the chain's stated value is set
#: against the chain's written arithmetic, at warning severity.
REPAIR7_PROBES: tuple[Probe, ...] = (
    # rule solved-law (before: INT-SUBJ-001 on correct working, the evaluation read as an exact algebra step from the law)
    _p("equations-law-then-evaluation-control", "equations", "receipt", "control", (PH,), PH, "the law with I not on its own, then its evaluation "
       "(before: the algebraic step 'I = 12 V / 2.9 Ω' failed, r = 120/29)", edits=((PH, "ε = I(R + r), so I = ε/(R + r)", "ε = I(R + r)"),),
       marker="ε = I(R + r)"),
    _p("equations-law-same-line-control", "equations", "receipt", "control", (PH,), PH, "the law and its evaluation on one line, after 'so'",
       edits=((PH, _PH_PART_B, "ε = I(R + r), so I = 12 V / 2.9 Ω = 4.1 A"),), marker="so I = 12 V / 2.9 Ω"),
    _p("equations-law-sum-evaluation-control", "equations", "receipt", "control", (PH,), PH, "the evaluation written with each value put in "
       "(its substitution checked against the law solved for I)", edits=((PH, _PH_PART_B, "ε = I(R + r)\nI = 12 V / (2.4 Ω + 0.50 Ω) = 4.1 A"),),
       marker="(2.4 Ω + 0.50 Ω) = 4.1 A"),
    _p("equations-law-sum-evaluation-slip", "equations", "receipt", "answer", (PH,), PH, "the same evaluation with an arithmetic slip",
       edits=((PH, _PH_PART_B, "ε = I(R + r)\nI = 12 V / (2.4 Ω + 0.50 Ω) = 4.8 A"),), marker="(2.4 Ω + 0.50 Ω) = 4.8 A", expected=("INT-SUBJ-001",)),
    _pb("equations-product-rearrangement-control", "equations", "control", _PB_REARR, "T½ = ln 2/λ, so λT½ = ln 2", "a rearrangement solved for no "
        "symbol, then the evaluation (before: the algebraic step 'λ = 0.693/8.0 h' failed, r = 693/8000)", "λT½ = ln 2"),
    _pb("equations-product-only-control", "equations", "control", _PB_REARR, "λT½ = ln 2", "the law stated only in a form with no lone symbol, then "
        "evaluated", "λT½ = ln 2"),
    _pb("equations-product-evaluation-wrong-given", "equations", "answer", _PB_PART_C, "T½ = ln 2/λ, so λT½ = ln 2\nλ = 0.693/9.0 h = 0.077 h⁻¹",
        "the evaluation of the law solved for λ with a half-life the answer does not state (9.0 h)", "0.693/9.0 h", ("INT-SUBJ-001",)),
    _pb("equations-product-value-wrong", "equations", "answer", _PB_PART_C, "T½ = ln 2/λ, so λT½ = ln 2\nλ = 0.097 h⁻¹", "a wrong value alone "
        "after the law in λ alone (the half-life stated): its solution, a step and its stated roots", "λ = 0.097 h⁻¹", ("INT-SUBJ-001",)),
    _pb("equations-product-value-control", "equations", "control", _PB_PART_C, "T½ = ln 2/λ, so λT½ = ln 2\nλ = 0.087 h⁻¹", "the right value alone",
        "λ = 0.087 h⁻¹"),
    _p("equations-squared-law-control", "equations", "receipt", "control", (PH,), PH, "the law with no lone symbol (V² = PR), then the power "
       "evaluated (before: the algebraic step failed)", edits=((PH, _PH_PART_D, "V² = PR\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"),), marker="V² = PR"),
    _p("equations-squared-law-wrong-given", "equations", "receipt", "answer", (PH,), PH, "the other resistor substituted in that evaluation (rule "
       "part-given, as with the formula P = V²/R)", edits=((PH, _PH_PART_D, "V² = PR\nP = (9.93 V)² / 4.0 Ω = 24.7 W, so 25 W"),), marker="24.7 W",
       expected=("INT-SUBJ-004",)),
    _p("equations-sum-law-control", "equations", "receipt", "control", (PH,), PH, "the law with V not on its own (ε = V + Ir), then V evaluated",
       edits=((PH, _PH_PART_C, "ε = V + Ir\n" + _PH_C),), marker="ε = V + Ir"),
    _chx("equations-amount-law-control", "equations", "control", "n = cV\nc = 0.0050 mol ÷ 0.0550 dm³ = 0.091 mol dm⁻³", "a chemistry law, then the "
         "concentration evaluated (before: the algebraic step failed)", "0.091 mol dm⁻³"),
    _p("equations-given-after-law-control", "equations", "receipt", "control", (PH,), PH, "a Given statement right after a law: data, never a step "
       "from the law (before: the algebraic step 'ε = 12 V' failed)", edits=((PH, _PH_PART_B, "I = ε/(R + r)\nGiven: ε = 12 V.\nI = 12 V / 2.9 Ω = 4.1 A"),),
       marker="Given: ε = 12 V"),
    _p("givens-after-law-contradiction", "givens", "receipt", "answer", (PH,), PH, "the same Given contradicting the request's emf: its Given check "
       "fails (before: also the false step)", edits=((PH, _PH_PART_B, "I = ε/(R + r)\nGiven: ε = 15 V.\nI = 15 V / 2.9 Ω = 5.2 A"),),
       marker="Given: ε = 15 V", expected=("INT-SUBJ-004",)),
    _chx("equations-amount-law-slip", "equations", "answer", "n = cV\nc = 0.0050 mol ÷ 0.0550 dm³ = 0.91 mol dm⁻³", "the same with a slip",
         "0.91 mol dm⁻³", ("INT-SUBJ-001",)),
    # rules leibniz and prime-derivative (before: read as products of symbols, with neither a check nor an ST code). STEM repair 11 (rule
    # derivative): a derivative of the answer's v(t) = 6t − 3t² is set against the one the power rule forms, so a wrong one fails (INT-SUBJ-001)
    # and a right one is clean (repair 7 had named each ST-UNDEC-001, never failed)
    _mad("receipts-derivative-prime", "receipts", "    Also v'(t) = 6 + 6t", "a wrong derivative in prime notation (before repair 7: v'·t, context; "
         "repair 7: ST-UNDEC-001)", "v'(t) = 6 + 6t", ("INT-SUBJ-001",)),
    _mad("receipts-derivative-prime-correct", "receipts", "    Also v′(t) = 6 − 6t", "the right one, checked and holding (repair 7: ST-UNDEC-001)",
         "v′(t) = 6 − 6t", (), kind="control"),
    _mad("receipts-derivative-prime-premise", "receipts", "    Since v = 6t − 3t², v'(t) = 6 + 6t", "after the formula it differentiates",
         "v'(t) = 6 + 6t", ("INT-SUBJ-001",)),
    _mad("receipts-derivative-second", "receipts", "    Also d²v/dt² = 6", "a second derivative in Leibniz notation (before repair 7: d²·v/(d·t²), "
         "an equation in an unknown)", "d²v/dt² = 6", ("INT-SUBJ-001",)),
    _mad("receipts-derivative-second-correct", "receipts", "    Also d²v/dt² = −6", "the right one, checked and holding", "d²v/dt² = −6", (),
         kind="control"),
    _mad("receipts-derivative-caret", "receipts", "    Also d^2v/dt^2 = 6", "the order written with a caret", "d^2v/dt^2", ("INT-SUBJ-001",)),
    _mad("receipts-derivative-latex", "receipts", "    Also $\\frac{d^2v}{dt^2} = 6$", "in LaTeX", "frac{d^2v}{dt^2}", ("INT-SUBJ-001",)),
    _mad("receipts-derivative-value", "receipts", "    v'(1) = 6 + 6(1) = 12", "a derivative's value with no derivative formula stated, against the "
         "power rule's derivative at 1 (before repair 11: only its arithmetic checked)", "v'(1)", ("INT-SUBJ-001",)),
    _pb("receipts-derivative-letter", "receipts", "answer", _PB_LAMBDA, _PB_LAMBDA + "\nThe decay law is dN/dt = −λN.", "dN/dt (before: d·N/(d·t))",
        "dN/dt", ("ST-UNDEC-001",), _NO_FAIL),
    _mad("maths-derivative-evaluation", "maths", "    Also v'(t) = 6 − 6t\n    v'(1) = 6 + 6(1) = 12", "the derivative evaluated against a formula "
         "the answer does not state for it (its own v'(t) = 6 − 6t)", "v'(1) = 6 + 6(1)", ("INT-SUBJ-001",)),
    _mad("maths-derivative-evaluation-correct", "maths", "    Also v'(t) = 6 − 6t\n    v'(1) = 6 − 6(1) = 0", "the right evaluation: the formula "
         "checked by the power rule and the evaluation holding (repair 7: the formula named unchecked)", "v'(t) = 6 − 6t", (), kind="control"),
    # rule finer-restatement (before: set against the chain's stated 9.9 V with h(S) + h(S′), so both passed)
    _phc("rounding-finer-zero", "rounding", "answer", "\nTo 3 s.f., V = 9.90 V.", "a restatement to 3 s.f. finer than the chain's 9.9 V, against "
         "its arithmetic's 9.93", "9.90 V", ("INT-SUBJ-004", "INT-SUBJ-001")),
    _phc("rounding-finer-digit", "rounding", "answer", "\nTo three significant figures, V = 9.94 V.", "the same with a wrong last figure", "9.94 V",
         ("INT-SUBJ-004", "INT-SUBJ-001")),
    _phc("rounding-finer-control", "rounding", "control", "\nTo three significant figures, V = 9.93 V.", "the right value to 3 s.f.", "9.93 V"),
    _phc("rounding-finer-bracket", "rounding", "answer", "\nV = 9.94 V (3 s.f.).", "the precision in brackets", "9.94 V (3 s.f.)",
         ("INT-SUBJ-004", "INT-SUBJ-001")),
    _phc("rounding-finer-inline", "rounding", "answer", ", so 9.95 V to 3 s.f.", "on the line of working after ', so'", "9.95 V",
         ("INT-SUBJ-004", "INT-SUBJ-001")),
    _phc("rounding-finer-inline-control", "rounding", "control", ", so 9.93 V to 3 s.f.", "the right value there", "9.93 V to 3"),
    _phc("rounding-finer-prose", "rounding", "answer", "\nTo 3 s.f., the terminal potential difference is 9.94 V.", "named by the prose", "is 9.94 V",
         ("INT-SUBJ-004", "INT-SUBJ-001")),
    _phc("rounding-finer-prose-control", "rounding", "control", "\nTo 3 s.f., the terminal potential difference is 9.93 V.", "the right value there",
         "is 9.93 V"),
    _phc("rounding-finer-unit", "rounding", "answer", "\nTo 3 s.f., V = 9900 mV.", "in another unit", "9900 mV", ("INT-SUBJ-004", "INT-SUBJ-001")),
    _phc("rounding-finer-unit-control", "rounding", "control", "\nTo 3 s.f., V = 9930 mV.", "the right value in mV", "9930 mV"),
    _pb("rounding-finer-constant", "rounding", "answer", _PB_LAMBDA, _PB_LAMBDA + "\nTo 3 s.f., λ = 0.0867 h⁻¹.", "after a chain with a written constant "
        "(0.693/8.0 gives 0.0866)", "0.0867 h⁻¹", ("INT-SUBJ-004", "INT-SUBJ-001")),
    _pb("rounding-finer-constant-control", "rounding", "control", _PB_LAMBDA, _PB_LAMBDA + "\nTo 3 s.f., λ = 0.0866 h⁻¹.", "the right value", "0.0866 h⁻¹"),
    _phd("rounding-finer-power", "rounding", "answer", "To 4 s.f., P = 16.34 W.", "a 4 s.f. power against (9.93 V)²/6.0 Ω = 16.43", "16.34 W",
         ("INT-SUBJ-004", "INT-SUBJ-001")),
    _phd("rounding-finer-power-control", "rounding", "control", "To 4 s.f., P = 16.43 W.", "the right value", "16.43 W"),
)
#: anchors of the eighth independent test's plants in the recorded answers
_CH_R = "Two reminders."
_PH_E = "from 9.9 V to 10.7 V."
_PB_DLINE = "32 h is 4 half-lives, so C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹."
_PH_VC = "(c) [1]\nV = ε − Ir"
_PH_PC = "(c) [1]\nV = ε − Ir\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
_ES_A = "= 60.4% decrease [1]"
_ES_AA = "(a) Percentage decrease = (9.6 − 3.8) ÷ 9.6 × 100\n= 60.4% decrease [1]"
_MI_R = "$= 4788$ euros, to the nearest euro (A1)"
_PB_LINE = {k: f"t = {k} h: {c} − 20 = {c - 20} ± {u} counts min⁻¹" for k, c, u in ((4, 1151, 23), (12, 586, 12), (20, 303, 6), (24, 220, 4))}


def _chr(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (CH,), CH, desc, edits=((CH, _CH_R, line + "\n\n" + _CH_R),), marker=marker, expected=expected)


def _bie(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (BI,), BI, desc, edits=((BI, _BI_END, _BI_END + "\n" + line),), marker=marker, expected=expected)


def _phe(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (PH,), PH, desc, edits=((PH, _PH_E, _PH_E + "\n" + line),), marker=marker, expected=expected)


def _phr(pid: str, cls: str, kind: str, old: str, new: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (PH,), PH, desc, edits=((PH, old, new),), marker=marker, expected=expected)


#: STEM repair 8 (design section 39): the eighth independent test's plants and controls, on the class whose cause it found, and the shapes of
#: the same classes found closing them. Rule value-at for a computing chain, rules name-list and item-label: a value the run computes under a
#: condition, after a list or a range the prose names it by, or for a numbered item, is the named quantity's value, never a relation between
#: the condition (or the list's last value, or the item's number) and the computation (before: INT-SUBJ-001 on correct working, with
#: ST-DIM-001); rules condition-value and name-list's check: the computation's value of the condition's dimension against the condition, a
#: term of a sum of listed values against the list; rule table-terms: a number the working takes beside a supplied table's values that is no
#: cell (a row's value copied wrongly, a wrong background) is set against the row's cell or the supplied value; rule law-values: the law the
#: line evaluates at the values it puts in, against its stated value, and a failed substitution names the law it evaluates; rule
#: inline-restatement with words between the chain's value and ', so'.
REPAIR8_PROBES: tuple[Probe, ...] = (
    # rule value-at for a computing chain (the tester's seven controls had a false INT-SUBJ-001, four with ST-DIM-001)
    _chr("chemistry-value-at-mean-control", "chemistry", "control", "Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s.", "a mean computed "
         "under its condition (before: '30.0 °C = (…) ÷ 3' failed, with ST-DIM-001)", "Mean time at 30.0 °C"),
    _chr("chemistry-value-at-mean-slip", "chemistry", "answer", "Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 32.2 s.", "the same with a "
         "slip: its arithmetic fails", "32.2 s", ("INT-SUBJ-001",)),
    _chr("chemistry-value-at-rate-control", "chemistry", "control", "Rate at 20.0 °C = 1/61.7 s = 0.0162 s⁻¹.", "a rate computed under its condition "
         "(before: '20.0 °C = 1/61.7 s' failed, with ST-DIM-001)", "Rate at 20.0 °C"),
    _chr("chemistry-value-at-rate-slip", "chemistry", "answer", "Rate at 20.0 °C = 1/61.7 s = 0.162 s⁻¹.", "the same with a slip", "0.162 s⁻¹",
         ("INT-SUBJ-001",)),
    _chr("chemistry-value-at-bare-control", "chemistry", "control", "The mean time at 20.0 °C = (62.4 + 60.8 + 61.9) ÷ 3 = 61.7 s.", "bare times "
         "averaged under the condition (before: '20.0 °C = (…) ÷ 3' failed)", "mean time at 20.0 °C"),
    _bie("maths-name-list-mean-control", "maths", "control", "Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3", "a mean after the list that names it "
         "(before: '40 = (18 + 27 + 40) ÷ 3' failed)", "Mean of 18, 27 and 40"),
    _bie("maths-name-list-mean-slip", "maths", "answer", "Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 29.3", "the same with a slip", "29.3",
         ("INT-SUBJ-001",)),
    _bie("wrong_given-name-list-term", "wrong_given", "answer", "Mean of 18, 27 and 40 = (18 + 27 + 41) ÷ 3 = 28.7", "a listed value copied wrongly "
         "into the computation (41 for 40), its arithmetic consistent: rule name-list's check", "(18 + 27 + 41)", ("INT-SUBJ-004",)),
    _bie("arithmetic-value-at-uptake-control", "arithmetic", "control", "Uptake at 30 °C = 2 × 40 = 80", "a row's value computed from another row's "
         "(before: '30 °C = 2 × 40' failed, and the 40 was set against the 30 °C row's 80)", "Uptake at 30 °C"),
    _p("arithmetic-value-at-uptake-slip", "arithmetic", "receipt", "answer", (BI,), BI, "the same with a slip: its arithmetic fails, and the 40 is not "
       "set against the 30 °C row, the row of the run's result (before the condition's row was read so, a false INT-SUBJ-004 beside the slip)",
       edits=((BI, _BI_END, _BI_END + "\nUptake at 30 °C = 2 × 40 = 90"),), marker="2 × 40 = 90", expected=("INT-SUBJ-001",), forbidden=("INT-SUBJ-004",)),
    _phe("physics-value-at-current-control", "physics", "control", "The current at t = 5 s is unchanged: I at t = 5 s = 12 V / 4.5 Ω = 2.7 A.",
         "a current computed under a symbol's condition (before: '5 s = 12 V / 4.5 Ω' failed, with ST-DIM-001)", "I at t = 5 s"),
    _phe("physics-value-at-current-slip", "physics", "answer", "The current at t = 5 s is unchanged: I at t = 5 s = 12 V / 4.5 Ω = 3.7 A.", "the same "
         "with a slip", "4.5 Ω = 3.7 A", ("INT-SUBJ-001",)),
    _pb("physics-value-at-rate-control", "physics", "control", _PB_DLINE, _PB_DLINE + "\nThe corrected rate at t = 40 h = 1600 counts min⁻¹ × (1/2)⁵ = "
        "50 counts min⁻¹.", "a count rate computed under its condition (before: '40 h = 1600 counts min⁻¹ × (1/2)⁵' failed, with ST-DIM-001)",
        "rate at t = 40 h"),
    _pb("physics-value-at-rate-slip", "physics", "answer", _PB_DLINE, _PB_DLINE + "\nThe corrected rate at t = 40 h = 1600 counts min⁻¹ × (1/2)⁵ = "
        "60 counts min⁻¹.", "the same with a slip", "= 60 counts", ("INT-SUBJ-001",)),
    _pb("physics-value-at-when-control", "physics", "control", _PB_DLINE, _PB_DLINE + "\nThe corrected rate when t = 16 h = 1600 counts min⁻¹ × (1/2)² "
        "= 400 counts min⁻¹.", "the same after 'when'", "rate when t = 16 h"),
    _phe("physics-value-after-control", "physics", "control", "The charge that flows after 2.0 s = 4.1 A × 2.0 s = 8.2 C.", "a charge computed after "
         "a time (before: '2.0 s = 4.1 A × 2.0 s' failed)", "after 2.0 s"),
    _phe("wrong_given-condition-value-after", "wrong_given", "answer", "The charge that flows after 2.0 s = 4.1 A × 3.0 s = 12.3 C.", "another time put "
         "in than the condition states (3.0 s for 2.0 s): rule condition-value", "4.1 A × 3.0 s", ("INT-SUBJ-004",)),
    _phd("physics-value-in-control", "physics", "control", "The energy dissipated in 10 s = 16.4 W × 10 s = 164 J.", "an energy computed for a time "
         "(before: '10 s = 16.4 W × 10 s' failed, with ST-DIM-001)", "in 10 s"),
    _phd("wrong_given-condition-value-in", "wrong_given", "answer", "The energy dissipated in 10 s = 16.4 W × 20 s = 328 J.", "another time put in (20 s "
         "for 10 s; every digit counts)", "16.4 W × 20 s", ("INT-SUBJ-004",)),
    _chr("chemistry-name-list-range-control", "chemistry", "control", "The rise from 20.0 °C to 30.0 °C = 30.0 − 20.0 = 10.0 K.", "a change computed "
         "after the range that names it (before: '30.0 °C = 30.0 − 20.0' failed)", "from 20.0 °C to 30.0 °C"),
    _chr("wrong_given-name-list-range-term", "wrong_given", "answer", "The rise from 20.0 °C to 30.0 °C = 30.0 − 25.0 = 5.0 K.", "a value the range does "
         "not name taken in its place (25.0 for 20.0)", "30.0 − 25.0", ("INT-SUBJ-004",)),
    _chr("chemistry-item-label-control", "chemistry", "control", "Rate for trial 2 = 1/60.8 s = 0.0164 s⁻¹.", "a rate computed for a numbered trial "
         "(before: '2 = 1/60.8 s' failed)", "Rate for trial 2"),
    _chr("chemistry-item-label-slip", "chemistry", "answer", "Rate for trial 2 = 1/60.8 s = 0.164 s⁻¹.", "the same with a slip", "0.164 s⁻¹",
         ("INT-SUBJ-001",)),
    _chr("chemistry-item-label-plain-control", "chemistry", "control", "Time for trial 2 = 60.8 s.", "a value stated for a numbered trial (before: '2 = "
         "60.8 s' failed)", "Time for trial 2"),
    _mia("maths-item-label-year-control", "maths", "control", "Year 2 = 4000 × 1.036² = 4293.18 euros", "a year's value computed for the numbered year "
         "(before: '2 = 4000 × 1.036²' failed)", "Year 2"),
    _mia("maths-item-label-year-slip", "maths", "answer", "Year 2 = 4000 × 1.036² = 4393.18 euros", "the same with a slip", "4393.18",
         ("INT-SUBJ-001",)),
    _bie("maths-name-list-between-control", "maths", "control", "Difference between 40 and 80 = 80 − 40 = 40", "a difference after the pair that names "
         "it (before: '80 = 80 − 40' failed)", "Difference between 40 and 80"),
    # rule table-terms (the tester's four plants were missed: a value copied wrongly from the supplied table, the background)
    _pb("wrong_given-table-row-12", "wrong_given", "answer", _PB_LINE[12], "t = 12 h: 568 − 20 = 548 ± 11 counts min⁻¹", "the measured value at 12 h "
        "copied wrongly (568 for 586), its arithmetic consistent", "568 − 20", ("INT-SUBJ-004",)),
    _pb("wrong_given-table-row-4", "wrong_given", "answer", _PB_LINE[4], "t = 4 h: 1115 − 20 = 1095 ± 22 counts min⁻¹", "1115 for 1151", "1115 − 20",
        ("INT-SUBJ-004",)),
    _pb("wrong_given-table-row-20", "wrong_given", "answer", _PB_LINE[20], "t = 20 h: 330 − 20 = 310 ± 7 counts min⁻¹", "330 for 303", "330 − 20",
        ("INT-SUBJ-004",)),
    _pb("wrong_given-table-background", "wrong_given", "answer", _PB_LINE[24], "t = 24 h: 220 − 25 = 195 ± 4 counts min⁻¹", "the background taken as "
        "25 (the supplied text and the answer state 20)", "220 − 25", ("INT-SUBJ-004",)),
    _pb("wrong_given-table-background-control", "wrong_given", "control", _PB_LINE[24], "t = 24 h: 220 − 20.0 = 200 ± 4 counts min⁻¹", "the background "
        "written 20.0", "220 − 20.0"),
    _pb("wrong_given-table-units-background", "wrong_given", "answer", _PB_LINE[12], "t = 12 h: 586 counts min⁻¹ − 25 counts min⁻¹ = 561 counts min⁻¹",
        "the wrong background written with its unit", "− 25 counts", ("INT-SUBJ-004",)),
    _pb("wrong_given-table-units-control", "wrong_given", "control", _PB_LINE[12], "t = 12 h: 586 counts min⁻¹ − 20 counts min⁻¹ = 566 counts min⁻¹",
        "the right one with its unit", "− 20 counts"),
    _pb("wrong_given-table-value-at", "wrong_given", "answer", _PB_LINE[12], "The corrected rate at t = 12 h = 568 − 20 = 548 counts min⁻¹", "the row's "
        "value copied wrongly in a run read by rule value-at", "568 − 20", ("INT-SUBJ-004",)),
    _pb("wrong_given-table-value-at-control", "wrong_given", "control", _PB_LINE[12], "The corrected rate at t = 12 h = 586 − 20 = 566 counts min⁻¹",
        "the right value there", "586 − 20"),
    _pb("wrong_given-table-bound-control", "wrong_given", "control", _PB_LINE[12], _PB_LINE[12] + " (upper bound 586 + 11.72 = 597.72 counts min⁻¹)",
        "a bound of the measured value (2% of it added): no value of the table's quantity", "586 + 11.72"),
    _pb("wrong_given-table-back-control", "wrong_given", "control", _PB_LINE[12], "t = 12 h: 566 + 20 = 586 counts min⁻¹", "the row's cell computed "
        "back from the corrected value: the row of the line's result", "566 + 20"),
    _es("wrong_given-table-ess-consistent", "wrong_given", "answer", _ES_AA, "(a) Percentage decrease = (9.6 − 3.9) ÷ 9.6 × 100\n= 59.4% decrease [1]",
        "site C's value copied wrongly (3.9 for 3.8), the arithmetic consistent", "3.9)", ("INT-SUBJ-004",)),
    _p("wrong_given-table-bio-row", "wrong_given", "receipt", "answer", (BI,), BI, "the 20 °C value copied wrongly (41 for 40)",
       edits=((BI, "(80 − 40) ÷ 40 × 100 = 100%, an increase of 100%", "(80 − 41) ÷ 41 × 100 = 95%, an increase of 95%"),), marker="(80 − 41)",
       expected=("INT-SUBJ-004", "INT-SUBJ-001")),
    _pb("wrong_given-prose-background", "wrong_given", "answer", "the background of 20 counts min⁻¹ is constant", "the background count rate of 25 "
        "counts min⁻¹ is constant", "the background stated wrongly in prose (every digit counts: it had held by the 20's trailing zero)",
        "25 counts min⁻¹", ("INT-SUBJ-004",)),
    _pb("wrong_given-prose-background-control", "wrong_given", "control", "the background of 20 counts min⁻¹ is constant", "the background count rate "
        "of 20 counts min⁻¹ is constant", "the right one", "rate of 20 counts"),
    # rule law-values, and the law named by the failed substitution of its evaluation
    _phr("formulas-law-sign", "formulas", "answer", _PH_VC, "(c) [1]\nV = ε + Ir", "the law stated with the wrong sign, its evaluation the right one "
         "(before: named by nothing)", "V = ε + Ir", ("INT-SUBJ-004",)),
    _phr("formulas-law-sign-control", "formulas", "control", _PH_VC, "(c) [1]\nV = ε − rI", "the right law, its product written the other way",
         "V = ε − rI"),
    _phr("formulas-law-evaluation-sign", "formulas", "answer", _PH_PC, "(c) [1]\nV = ε − Ir\nV = 12 V + (4.14 A × 0.50 Ω) = 14.1 V", "the right law, its "
         "evaluation with the wrong sign (before: only its arithmetic checked, which holds)", "12 V + (4.14", ("INT-SUBJ-004", "INT-SUBJ-001")),
    _phr("formulas-law-same-line", "formulas", "answer", _PH_PC, "(c) [1]\nV = ε + Ir = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "the wrong law and its "
         "evaluation in one line", "V = ε + Ir", ("INT-SUBJ-004",)),
    _phr("formulas-law-same-line-control", "formulas", "control", _PH_PC, "(c) [1]\nV = ε − Ir = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "the right law and "
         "its evaluation in one line", "V = ε − Ir ="),
    _phr("formulas-law-so", "formulas", "answer", _PH_PC, "(c) [1]\nV = ε + Ir, so V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "the wrong law, then its "
         "evaluation after 'so'", "V = ε + Ir", ("INT-SUBJ-004",)),
    _phr("formulas-law-so-control", "formulas", "control", _PH_PC, "(c) [1]\nV = ε − Ir, so V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "the right law there",
         "V = ε − Ir,"),
    _phr("formulas-law-using", "formulas", "answer", _PH_PC, "(c) [1]\nUsing V = ε + Ir:\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "the wrong law "
         "introduced by 'Using'", "Using V = ε + Ir", ("INT-SUBJ-004",)),
    _phr("formulas-law-using-control", "formulas", "control", _PH_PC, "(c) [1]\nUsing V = ε − Ir:\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "the right law "
         "there", "Using V = ε − Ir"),
    _phr("formulas-law-power", "formulas", "answer", "P = V²/R\nP = (9.93 V)²", "P = V/R\nP = (9.93 V)²", "the power law without its square (before: the "
         "failed substitution named the evaluation and part (c)'s V only)", "P = V/R", ("INT-SUBJ-001",)),
    _phr("formulas-law-power-half", "formulas", "answer", "P = V²/R\nP = (9.93 V)²", "P = V²/(2R)\nP = (9.93 V)²", "a factor of 2 the evaluation does not "
         "take", "P = V²/(2R)", ("INT-SUBJ-001",)),
    _phr("formulas-other-law-control", "formulas", "control", "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W", "P = V²/R\nP = 9.93 V × 1.655 A = 16.4 W",
         "the power evaluated by another law (P = VI) right after P = V²/R (before: set against V²/R and failed)", "9.93 V × 1.655 A"),
    _phr("formulas-law-computed-term-control", "formulas", "control", _PH_PC, "(c) [1]\nV = ε − Ir\nV = 12 V − 2.07 V = 9.93 V", "the lost volts "
         "computed first: no pairing with the law's three symbols", "12 V − 2.07 V"),
    # rule inline-restatement with words between the chain's value and ', so'
    _es("rounding-inline-words", "rounding", "answer", _ES_A, "= 60.4% decrease, so 61% to 2 s.f. [1]", "a rounding after ', so' with 'decrease' before "
        "it (before: never read)", "so 61%", ("INT-SUBJ-001",)),
    _es("rounding-inline-words-control", "rounding", "control", _ES_A, "= 60.4% decrease, so 60% to 2 s.f. [1]", "the right rounding", "so 60%"),
    _es("rounding-inline-words-which", "rounding", "answer", _ES_A, "= 60.4% decrease, which is 61% to 2 s.f. [1]", "after ', which is'", "is 61%",
        ("INT-SUBJ-001",)),
    _p("rounding-inline-words-unit", "rounding", "receipt", "answer", (MI,), MI, "a unit word after the chain's value, then ', so'",
       edits=((MI, _MI_R, "$= 4787.58$ euros, so 4787 euros to the nearest euro (A1)"),), marker="so 4787 euros", expected=("INT-SUBJ-001",)),
    _p("rounding-inline-words-unit-control", "rounding", "receipt", "control", (MI,), MI, "the right euro",
       edits=((MI, _MI_R, "$= 4787.58$ euros, so 4788 euros to the nearest euro (A1)"),), marker="so 4788 euros"),
    _phr("rounding-inline-words-phrase", "rounding", "answer", "(4.14 A × 0.50 Ω) = 9.9 V", "(4.14 A × 0.50 Ω) = 9.93 V across the resistors, so 9.8 V to "
         "2 s.f.", "three words between the value and ', so'", "so 9.8 V", ("INT-SUBJ-001",)),
    _phr("rounding-inline-words-phrase-control", "rounding", "control", "(4.14 A × 0.50 Ω) = 9.9 V", "(4.14 A × 0.50 Ω) = 9.93 V across the resistors, so "
         "9.9 V to 2 s.f.", "the right rounding", "so 9.9 V"),
)
#: anchors of the ninth independent test's plants in the recorded answers
_PH_B2 = "I = 12 V / 2.9 Ω = 4.1 A"
_PH_CHECK = "\nAs a check, ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V."


def _phc9(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (PH,), PH, desc, edits=((PH, _PH_C, _PH_C + "\n" + line),), marker=marker, expected=expected)


def _ma9(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (MA,), MA, desc, edits=((MA, _MA_APPEND, _MA_APPEND + "\n" + line),), marker=marker, expected=expected)


def _pb9(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _pb(pid, cls, kind, _PB_DLINE, _PB_DLINE + "\n" + line, desc, marker, expected)


#: STEM repair 9 (design section 40): the ninth independent test's plants and controls, on the class whose cause it found, and the shapes of
#: the same classes found closing them. Rule part-answer: the question of a part labels its answer, never a check line or a line that names
#: another quantity at its end (before: a later change stated from the part's result was set against that line, a false INT-SUBJ-004, and a
#: substitution of a changed value a false INT-SUBJ-001); rule named-result: the value a chain gives a quantity the request names, by its
#: words, its label or a symbol the answer substituted the request's value for, is set against the request; rule given-function: a Given of a
#: function's value or of a function is set against the request's function; rule row-terms: the values a line takes from the repeats of the
#: row it names; rule decay-law: the value a line computes over a stated number of half-lives with no power of ½; rule statistics: a median,
#: mode, range or mean stated for listed values or a supplied column; rule rounded-digits: a value stated with a rounding is written to it.
REPAIR9_PROBES: tuple[Probe, ...] = (
    # rule part-answer (the tester's three controls had a false INT-SUBJ-004 through rule named-change)
    _phc9("physics-part-answer-check-control", "physics", "control", "As a check, ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V.", "a check line at the end of "
          "part (c) (before: it took the part's question words, so '… rises, from 9.9 V' was set against its 12.0 V)", "As a check, ε"),
    _phc9("physics-part-answer-lost-volts-control", "physics", "control", "The lost volts are 4.14 A × 0.50 Ω = 2.07 V.", "a line naming another "
          "quantity at the end of part (c) (before: set against '… rises, from 9.9 V')", "lost volts"),
    _phc9("physics-part-answer-emf-words-control", "physics", "control", "So the emf is 9.93 V + 4.14 A × 0.50 Ω = 12.0 V.", "the emf computed at the end "
          "of part (c), named by its words (before: set against '… rises, from 9.9 V'); now also set against the request's emf, and holds",
          "So the emf is"),
    _phc9("physics-part-answer-symbol-control", "physics", "control", "ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V", "the emf computed for its symbol, the "
          "request's value substituted for it before (rule named-result), so no answer of part (c)", "ε = 9.93 V"),
    _phc9("physics-part-answer-other-pd-control", "physics", "control", "The potential difference across the internal resistance is 4.14 A × 0.50 Ω = "
          "2.07 V.", "a potential difference other than the asked one (its words share some of the question's)", "across the internal resistance"),
    _p("physics-part-answer-changed-current-control", "physics", "receipt", "control", (PH,), PH, "a check line at the end of part (b), then the "
       "changed current substituted in part (e) (before: the change was not recorded, so the substitution failed against 4.1 A, a false "
       "INT-SUBJ-001)", edits=((PH, _PH_B2, _PH_B2 + "\nAs a check, 4.1 A × 2.9 Ω = 11.9 V, close to the emf."),
                              (PH, _PH_E, _PH_E + "\nWith the resistor removed, V = 12 V − 2.7 A × 0.50 Ω = 10.65 V.")), marker="2.7 A × 0.50 Ω"),
    _p("physics-part-answer-change-slip", "physics", "receipt", "answer", (PH,), PH, "with the check line at the end of part (c), a change stated from "
       "a wrong value ('from 9.0 V'): still set against part (c)'s 9.9 V", edits=((PH, _PH_C, _PH_C + _PH_CHECK), (PH, _PH_E, "from 9.0 V to 10.7 V.")),
       marker="from 9.0 V", expected=("INT-SUBJ-004",)),
    # rule named-result (the tester's three plants of a wrong rearrangement evaluated, and the shapes of its class)
    _phc9("equations-named-result-rearranged", "equations", "answer", "So r = (ε + V)/I = (12 V + 9.93 V)/4.14 A = 5.3 Ω.", "a wrong rearrangement "
          "of V = ε − Ir evaluated, giving the internal resistance 5.3 Ω against the request's 0.50 ohm (before: named by nothing)", "(12 V + 9.93 V)",
          ("INT-SUBJ-004",)),
    _phc9("equations-named-result-rearranged-control", "equations", "control", "So r = (ε − V)/I = (12 V − 9.93 V)/4.14 A = 0.50 Ω.", "the right "
          "rearrangement evaluated", "(12 V − 9.93 V)"),
    _phc9("equations-named-result-symbol", "equations", "answer", "r = (12 V + 9.93 V)/4.14 A = 5.3 Ω", "the value computed for r alone", "(12 V + 9.93 V)",
          ("INT-SUBJ-004",)),
    _phc9("equations-named-result-words", "equations", "answer", "So the internal resistance is (12 V + 9.93 V)/4.14 A = 5.3 Ω.", "the quantity named by "
          "its words, given a computed chain", "(12 V + 9.93 V)", ("INT-SUBJ-004",)),
    _phc9("equations-named-result-words-control", "equations", "control", "So the internal resistance is (12 V − 9.93 V)/4.14 A = 0.50 Ω.", "the right "
          "chain there", "(12 V − 9.93 V)"),
    _phc9("givens-named-result-emf", "givens", "answer", "So the emf is 9.93 V + 4.14 A × 5.0 Ω = 30.6 V.", "the emf computed with a wrong internal "
          "resistance (before: named only by the false part-answer reading)", "30.6 V", ("INT-SUBJ-004",)),
    _phc9("givens-named-result-stated", "givens", "answer", "So r = 5.3 Ω.", "a value stated for the symbol the answer substituted the request's value "
          "for (before: nothing)", "r = 5.3", ("INT-SUBJ-004",)),
    _phc9("givens-named-result-label", "givens", "answer", "Internal resistance: r = (12 V + 9.93 V)/4.14 A = 5.3 Ω", "the quantity named by its label",
          "(12 V + 9.93 V)", ("INT-SUBJ-004",)),
    # rule given-function (the tester's Given of a function's value and Given functions)
    _ma9("givens-function-value", "givens", "answer", "Given: v(1) = 4 m s⁻¹.", "a Given of the request's function at t = 1 (it gives 3): before, "
         "neither checked nor named while the pack said every Given has one or the other", "v(1) = 4", ("INT-SUBJ-004",)),
    _ma9("givens-function-value-control", "givens", "control", "Given: v(1) = 3 m s⁻¹.", "the right value, now checked", "v(1) = 3"),
    _ma9("givens-function", "givens", "answer", "Given: v(t) = 6t − 2t².", "a Given function contradicting the request's v(t) = 6t − 3t²", "6t − 2t²",
         ("INT-SUBJ-004",)),
    _ma9("givens-function-control", "givens", "control", "Given: v(t) = 6t − 3t².", "the request's function", "Given: v(t) = 6t − 3t²"),
    _ma9("givens-function-undefined", "givens", "answer", "Given: a(t) = 6 − 4t.", "a Given of a function the request defines none of: named "
         "unchecked", "6 − 4t", ("ST-UNDEC-003",)),
    _ma9("givens-function-formula", "givens", "answer", "Given: v = 6t − 2t².", "the Given function written for the symbol", "v = 6t − 2t²",
         ("INT-SUBJ-004",)),
    _ma9("givens-function-renamed-control", "givens", "control", "Given: v(x) = 6x − 3x².", "the request's function in another variable", "v(x) = 6x"),
    _ma9("givens-function-value-bare", "givens", "answer", "Given: v(1) = 4.", "the value with no unit", "v(1) = 4", ("INT-SUBJ-004",)),
    _ma9("givens-function-value-si-control", "givens", "control", "Given: v(1) = 300 cm s⁻¹.", "the right value in another unit (compared in SI)",
         "300 cm s⁻¹"),
    _ma9("givens-function-value-undefined", "givens", "answer", "Given: a(1) = 0.", "a Given value of a function the request does not define: named "
         "unchecked", "a(1) = 0", ("ST-UNDEC-003",)),
    # rule row-terms (the tester's trial value copied wrongly into a row's mean)
    _chr("wrong_given-row-repeat", "wrong_given", "answer", "Mean time at 30.0 °C = (33.1 s + 43.0 s + 32.5 s) ÷ 3 = 36.2 s.", "trial 2 copied "
         "wrongly (43.0 for 34.0) inside the mean over the row's trials, its arithmetic consistent (before: only the arithmetic checked)", "43.0 s",
         ("INT-SUBJ-004",)),
    _chr("wrong_given-row-repeat-bare", "wrong_given", "answer", "Mean time at 30.0 °C = (33.1 + 43.0 + 32.5) ÷ 3 = 36.2 s.", "the same written bare",
         "43.0 +", ("INT-SUBJ-004",)),
    _chr("wrong_given-row-other", "wrong_given", "answer", "Mean time at 30.0 °C = (33.1 s + 17.6 s + 32.5 s) ÷ 3 = 27.7 s.", "another row's trial "
         "taken (17.6, the 40.0 °C row's)", "17.6 s", ("INT-SUBJ-004",)),
    _chr("wrong_given-row-reordered-control", "wrong_given", "control", "Mean time at 30.0 °C = (32.5 s + 33.1 s + 34.0 s) ÷ 3 = 33.2 s.", "the row's "
         "trials in another order", "(32.5 s +"),
    # rule decay-law (the tester's decay divided by the number of half-lives)
    _pb9("formulas-decay-divided", "formulas", "answer", "At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 5 = 320 counts min⁻¹.", "the decay over 5 "
         "half-lives written as a division by 5 (before: only ST-SCOPE-001, an info)", "÷ 5 = 320", ("INT-SUBJ-004",)),
    _pb9("formulas-decay-divided-control", "formulas", "control", "At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 32 = 50 counts min⁻¹.", "the "
         "right decay as a division", "÷ 32 = 50"),
    _pb9("formulas-decay-power-two-control", "formulas", "control", "At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 2⁵ = 50 counts min⁻¹.", "the "
         "right decay by a power of 2", "÷ 2⁵"),
    _pb9("formulas-decay-factor", "formulas", "answer", "After 5 half-lives, C = 1600 counts min⁻¹ × 5/32 = 250 counts min⁻¹.", "a factor the decay law "
         "does not give", "5/32", ("INT-SUBJ-004",)),
    # rule statistics (the tester's wrong median in three forms, and the class's other statistics)
    _bie("maths-median-prose", "maths", "answer", "The median of 18, 27, 40, 58, 80, 92 and 61 is 61.", "a wrong median of listed values (58): before, "
         "neither checked nor named", "is 61.", ("INT-SUBJ-004",)),
    _bie("maths-median-prose-control", "maths", "control", "The median of 18, 27, 40, 58, 80, 92 and 61 is 58.", "the right median", "is 58."),
    _bie("maths-median-column", "maths", "answer", "Median uptake = 61 mm³ per g per hour", "a wrong median of the supplied table's column", "Median "
         "uptake = 61", ("INT-SUBJ-004",)),
    _bie("maths-median-column-control", "maths", "control", "Median uptake = 58 mm³ per g per hour", "the right one", "Median uptake = 58"),
    _bie("maths-median-list", "maths", "answer", "Median of 18, 27, 40, 58, 80, 92 and 61 = 61", "the median written with '=' after its list (before: "
         "'61 = 61', which held)", "and 61 = 61", ("INT-SUBJ-004",)),
    _bie("maths-median-list-control", "maths", "control", "Median of 18, 27, 40, 58, 80, 92 and 61 = 58", "the right one", "and 61 = 58"),
    _bie("maths-median-even", "maths", "answer", "The median of 18, 27, 40 and 58 is 40.", "an even count: the mean of the middle two (33.5)", "is 40.",
         ("INT-SUBJ-004",)),
    _bie("maths-median-even-control", "maths", "control", "The median of 18, 27, 40 and 58 is 33.5.", "the right one", "is 33.5."),
    _bie("maths-range", "maths", "answer", "The range of 18, 27 and 40 is 23.", "a wrong range (22)", "is 23.", ("INT-SUBJ-004",)),
    _bie("maths-range-control", "maths", "control", "The range of 18, 27 and 40 is 22.", "the right one", "is 22."),
    _bie("maths-mode", "maths", "answer", "The mode of 18, 27, 27 and 40 is 18.", "a wrong mode (27)", "is 18.", ("INT-SUBJ-004",)),
    _bie("maths-mode-control", "maths", "control", "The mode of 18, 27, 27 and 40 is 27.", "the right one", "is 27."),
    _bie("maths-mean-list", "maths", "answer", "Mean of 18, 27 and 40 = 29.3", "a mean stated after its list with no working (before: ST-PARSE-001)",
         "= 29.3", ("INT-SUBJ-004",)),
    _bie("maths-mean-list-control", "maths", "control", "Mean of 18, 27 and 40 = 28.3", "the right one, now checked", "= 28.3"),
    _bie("maths-statistic-unchecked", "maths", "answer", "The standard deviation of 18, 27 and 40 is 9.0.", "a statistic outside the encodings: named "
         "unchecked (before: nothing)", "is 9.0.", ("ST-UNDEC-001",)),
    _ma9("maths-median-maa", "maths", "answer", "The median of 0, 2 and 3 is 3.", "a wrong median of the answer's own values (2)", "is 3.",
         ("INT-SUBJ-004",)),
    _ma9("maths-median-maa-control", "maths", "control", "The median of 0, 2 and 3 is 2.", "the right one", "is 2."),
    # rule rounded-digits (the tester's values restated at a rounding they are not written to)
    _es("precision-rounded-digits-which", "precision", "answer", _ES_A, "= 60.4% decrease, which is 60.4% to 2 s.f. [1]", "a restatement at 2 s.f. "
        "written to the tenths (before: it held within the rounding's half-width)", "60.4% to 2 s.f.", ("INT-SUBJ-004",)),
    _es("precision-rounded-digits-so", "precision", "answer", _ES_A, "= 60.4% decrease, so 60.4% to 2 s.f. [1]", "the same after ', so'", "so 60.4%",
        ("INT-SUBJ-004",)),
    _es("precision-rounded-digits-which-control", "precision", "control", _ES_A, "= 60.4% decrease, which is 60% to 2 s.f. [1]", "the value rounded as "
        "stated", "60% to 2 s.f."),
    _es("precision-rounded-digits-finer", "precision", "answer", _ES_A, "= 60.4% decrease, so 60.40% to 3 s.f. [1]", "a restatement written to more "
        "figures than the rounding states", "60.40%", ("INT-SUBJ-004",)),
    _phe("precision-rounded-digits-prose", "precision", "answer", "To 3 s.f. the external resistance is 2.4 Ω.", "a value stated at 3 s.f. with the "
         "digits of 2 (before: nothing)", "is 2.4 Ω", ("INT-SUBJ-004",)),
    _phe("precision-rounded-digits-prose-control", "precision", "control", "To 3 s.f. the external resistance is 2.40 Ω.", "the same written to 3 s.f.",
         "is 2.40 Ω"),
    _phe("precision-rounded-digits-symbol", "precision", "answer", "To 3 s.f., R = 2.4 Ω.", "a value stated for a symbol at 3 s.f. with the digits of 2",
         "R = 2.4", ("INT-SUBJ-004",)),
)
#: anchors of the tenth independent test's plants in the recorded answers
_MA_END10 = "Marks shown are a provisional allocation."
_MI_12 = "$4000(1.036)^{12} = 6114.73$"
_MI_PB = "**Part (b) — find — 3 marks**"
_MA_INT = "∫₀² v dt = [3t² − t³]₀² = (12 − 8) − 0 = 4"


def _ch10(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = (), sep: str = "\n\n") -> Probe:
    return _p(pid, cls, "receipt", kind, (CH,), CH, desc, edits=((CH, _CH_R, line + sep + _CH_R),), marker=marker, expected=expected)


def _ma10(pid: str, cls: str, kind: str, line: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (MA,), MA, desc, edits=((MA, _MA_END10, line + "\n\n" + _MA_END10),), marker=marker, expected=expected)


def _mi10(pid: str, cls: str, kind: str, old: str, new: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (MI,), MI, desc, edits=((MI, old, new),), marker=marker, expected=expected)


#: STEM repair 10 (design section 41): the tenth independent test's plants and controls, on the class whose cause it found, and the shapes of
#: the same classes found closing them. Rule prose-conversion: whether a restated value ends its clause is read in its own statement (before:
#: a window of the whole text, so a conversion with a verb was read only at the end of the answer); rule table-operands: a line that names its
#: rows and its column is read in its own column; rule row-value: a value at a site's row in more shapes (the value after 'site A has', a run
#: labelled by the column after the row, 'number', a column joined to the clause's first, a count the clause leaves its column out of, the
#: column before 'of' or after the value); rule named-component: the value a working substitutes against the component its statement names by
#: its value; rule condition-result: a value computed for a symbol under a condition against the value computed for it under that condition
#: before; rule prose-base: a whole number restated in another base in prose; rule definite-integral: a definite integral of a polynomial and an
#: evaluation bracket; rule operand-precision for given data: a numeral that writes a value the request states is exact; rule ellipsis-rounding:
#: a value restated from a value written with its digits cut.
REPAIR10_PROBES: tuple[Probe, ...] = (
    # rule prose-conversion (the tester's plant before 'Two reminders.', and the shapes of D31 followed by another statement)
    _ch10("units-prose-conversion-followed", "units", "answer", "A time of 45 s is 0.45 min.", "a wrong conversion with 'is', followed by another "
          "statement (before: no check, no ST code; read only when it ended the answer)", "0.45 min", ("INT-SUBJ-001",)),
    _ch10("units-prose-conversion-followed-control", "units", "control", "A time of 45 s is 0.75 min.", "the right one", "0.75 min"),
    _ch10("units-prose-conversion-equal-followed", "units", "answer", "The volume of 55.0 cm³ is equal to 0.550 dm³.", "'is equal to', followed",
          "0.550 dm³", ("INT-SUBJ-001",)),
    _ch10("units-prose-conversion-gives-followed", "units", "answer", "Converting 55.0 cm³ to dm³ gives 0.550 dm³.", "'to <unit> gives', followed",
          "0.550 dm³", ("INT-SUBJ-001",)),
    _ch10("units-prose-conversion-about-followed", "units", "answer", "The flask holds 55.0 cm³, about 0.6 dm³.", "', about', followed", "0.6 dm³",
          ("INT-SUBJ-001",)),
    _ch10("units-prose-conversion-same-line", "units", "answer", "A time of 45 s is 0.45 min.", "followed by another sentence on the same line",
          "0.45 min", ("INT-SUBJ-001",), sep=" "),
    _ch10("units-prose-conversion-same-line-control", "units", "control", "The volume of 55.0 cm³ is 0.0550 dm³.", "the right one on the same line",
          "0.0550 dm³", sep=" "),
    _ch10("units-prose-conversion-comparison-control", "units", "control", "A length of 2.0 km is 500 m more than 1.5 km.", "a comparison its clause "
          "goes on after, followed: no conversion", "500 m more"),
    # rule table-operands (the tester's nitrate lines in the part whose question asks about dissolved oxygen)
    _es("wrong_given-line-column", "wrong_given", "answer", _ES_W, "The nitrate rise from site A to site D is (8.4 − 1.2) ÷ 1.2 × 100 = 600%.", "site B's "
        "nitrate for site A's in part (c), whose question names the dissolved oxygen (before: two columns named, nothing read)", "site A to site D",
        ("INT-SUBJ-004",)),
    _es("wrong_given-line-column-control", "wrong_given", "control", _ES_W, "The nitrate rise from site A to site D is (4.1 − 1.2) ÷ 1.2 × 100 = 242%.",
        "the rows' own cells", "site A to site D"),
    _es("wrong_given-line-column-fall", "wrong_given", "answer", _ES_W, "From A to D the nitrate falls by (8.4 − 4.1) ÷ 8.4 × 100 = 51.2%.", "the same "
        "with bare row letters", "From A to D", ("INT-SUBJ-004",)),
    _es("wrong_given-line-column-decrease", "wrong_given", "answer", _ES_W, "The percentage decrease in nitrate from B to D = (8.4 − 2.3) ÷ 8.4 × 100 = "
        "72.6%.", "site E's nitrate for site D's", "from B to D", ("INT-SUBJ-004",)),
    _es("wrong_given-line-column-decrease-control", "wrong_given", "control", _ES_W, "The percentage decrease in nitrate from B to D = (8.4 − 4.1) ÷ 8.4 "
        "× 100 = 51.2%.", "the rows' own cells", "from B to D"),
    _es("wrong_given-line-column-oxygen-control", "wrong_given", "control", _ES_W, "Oxygen falls from A to C as nitrate rises: (9.6 − 3.8) ÷ 9.6 × 100 = "
        "60.4%.", "a line whose numbers are no cells of the one column its words name: read as before (nothing)", "Oxygen falls"),
    # rule row-value (the tester's mayfly shapes, each in place of the part (c) sentence the word limit leaves room for)
    _es("givens-row-has-value", "givens", "answer", _ES_W, "Site A has 43 mayfly nymphs per kick sample.", "the value right after 'Site A has', the "
        "column after it (before: nothing)", "43 mayfly", ("INT-SUBJ-004",)),
    _es("givens-row-has-value-control", "givens", "control", _ES_W, "Site A has 34 mayfly nymphs per kick sample.", "the right count", "34 mayfly"),
    _es("givens-row-label-run", "givens", "answer", _ES_W, "At site A, mayfly nymphs = 43.", "a run labelled by the column after the row", "nymphs = 43",
        ("INT-SUBJ-004",)),
    _es("givens-row-label-run-control", "givens", "control", _ES_W, "At site A, mayfly nymphs = 34.", "the right count", "nymphs = 34"),
    _es("givens-row-number-verb", "givens", "answer", _ES_W, "The mayfly nymphs at site A number 43.", "'number' as the verb", "number 43",
        ("INT-SUBJ-004",)),
    _es("givens-row-number-verb-control", "givens", "control", _ES_W, "The mayfly nymphs at site A number 34.", "the right count", "number 34"),
    _es("givens-row-value-column-at", "givens", "answer", _ES_W, "There were 7 mayfly nymphs at site B.", "the column and the row after the value",
        "7 mayfly", ("INT-SUBJ-004",)),
    _es("givens-row-value-column-at-control", "givens", "control", _ES_W, "There were 9 mayfly nymphs at site B.", "the right count", "9 mayfly"),
    _es("givens-row-column-of", "givens", "answer", _ES_W, "The river has a nitrate concentration of 9.6 mg dm⁻³ at site C.", "the column before 'of', "
        "the row after the value (9.6 is site A's dissolved oxygen)", "9.6 mg dm⁻³ at site C", ("INT-SUBJ-004",)),
    _es("givens-row-column-of-control", "givens", "control", _ES_W, "The river has a nitrate concentration of 6.9 mg dm⁻³ at site C.", "the right cell",
        "6.9 mg dm⁻³ at site C"),
    _es("givens-row-has-quantity", "givens", "answer", _ES_W, "Site A has 2.1 mg dm⁻³ of nitrate.", "a quantity after 'Site A has', its column after it",
        "2.1 mg dm⁻³ of nitrate", ("INT-SUBJ-004",)),
    _es("givens-row-coordinated", "givens", "answer", "the most nymphs (34)", "the most nymphs (43)", "the recorded count restated wrongly in a column "
        "joined to the clause's first, named by its last word (before: nothing)", "the most nymphs (43)", ("INT-SUBJ-004",)),
    _es("givens-row-ellipsis", "givens", "answer", "and only 9 [1]", "and only 7 [1]", "the recorded count the clause leaves its column out of, "
        "restated wrongly (the table's only column with no unit)", "and only 7", ("INT-SUBJ-004",)),
    # rule named-component (the tester's resistance substituted for the resistor the sentence names)
    _ph("wrong_given-named-component", "wrong_given", "answer", "The power dissipated in the 4.0 Ω resistor is P = (9.93 V)² / 6.0 Ω = 16.4 W.", "the "
        "other resistor's 6.0 Ω substituted for the 4.0 Ω resistor the sentence names, its arithmetic and substitution right (before: nothing)",
        "dissipated in the 4.0 Ω resistor", ("INT-SUBJ-004",)),
    _ph("wrong_given-named-component-control", "wrong_given", "control", "The power dissipated in the 4.0 Ω resistor is P = (9.93 V)² / 4.0 Ω = 24.7 W.",
        "the named resistor's own value", "dissipated in the 4.0 Ω resistor"),
    _ph("wrong_given-named-component-current", "wrong_given", "answer", "The current through the 4.0 Ω resistor is I = 9.93 V / 6.0 Ω = 1.66 A.", "the "
        "same for a current", "through the 4.0 Ω resistor", ("INT-SUBJ-004",)),
    _ph("wrong_given-named-component-total-control", "wrong_given", "control", "The current through the 4.0 Ω resistor is I = 12 V / 4.5 Ω = 2.7 A.",
        "a value the answer computed (a total), not one the request states: not read", "through the 4.0 Ω resistor"),
    _ph("wrong_given-named-component-sum-control", "wrong_given", "control", "The current in the 4.0 Ω resistor is I = 12 V / (4.0 Ω + 0.50 Ω) = 2.7 A.",
        "a working that takes the named value with another", "in the 4.0 Ω resistor"),
    # rule condition-result (the tester's wrong decay law whose arithmetic is right)
    _pb("formulas-condition-result", "formulas", "answer", _PB_END, _PB_END + "\nUsing C = C₀ − λt, C = 1600 − 0.087 × 32 = 1597 counts min⁻¹ at 32 h.",
        "a wrong law evaluated right, its value at 32 h against part (d)'s 100 counts min⁻¹ there (before: only an info note)", "C = C₀ − λt",
        ("INT-SUBJ-004",)),
    _pb("formulas-condition-result-control", "formulas", "control", _PB_END, _PB_END + "\nUsing C = C₀(½)ⁿ, C = 1600 × (1/2)⁴ = 100 counts min⁻¹ at 32 h.",
        "the right law", "C = C₀(½)ⁿ"),
    _pb("formulas-condition-result-leading", "formulas", "answer", _PB_END, _PB_END + "\nAt t = 32 h, C = 1600 − 0.087 × 32 = 1597 counts min⁻¹.", "the "
        "condition before the run", "1600 − 0.087 × 32", ("INT-SUBJ-004",)),
    _pb("formulas-condition-result-leading-control", "formulas", "control", _PB_END, _PB_END + "\nAt t = 32 h, C = 1600 × (1/2)⁴ = 100 counts min⁻¹.",
        "the right one", "At t = 32 h, C"),
    # rule prose-base (the tester's base conversion in prose)
    _cs("boolean-base-prose", "answer", "The binary number 110010₂ is 48 in denary.", "a wrong conversion in prose (50 is right; before: no check, no "
        "ST code)", "110010₂", ("INT-SUBJ-001",)),
    _cs("boolean-base-prose-control", "control", "The binary number 110010₂ is 50 in denary.", "the right one", "110010₂"),
    _cs("boolean-base-prose-words", "answer", "110010 in binary is 48 in denary.", "both bases in words", "in binary is 48", ("INT-SUBJ-001",)),
    _cs("boolean-base-prose-denary", "answer", "The denary number 50 is 110011 in binary.", "from denary", "110011 in binary", ("INT-SUBJ-001",)),
    _cs("boolean-base-prose-denary-control", "control", "The denary number 50 is 110010 in binary.", "the right one", "110010 in binary"),
    _cs("boolean-base-prose-representation", "answer", "The binary representation of 50 is 110011.", "the restated value's base before the first",
        "representation of 50", ("INT-SUBJ-001",)),
    _cs("boolean-base-prose-hex", "answer", "In hexadecimal, 2F₁₆ is 45 in denary.", "hexadecimal", "2F₁₆ is 45", ("INT-SUBJ-001",)),
    _cs("boolean-base-prose-hex-control", "control", "In hexadecimal, 2F₁₆ is 47 in denary.", "the right one", "2F₁₆ is 47"),
    # rule definite-integral (the tester's wrong definite integral, and the shapes of its class)
    _ma10("maths-definite-bracket", "maths", "answer", "Also ∫₀¹ 6t dt = [3t²]₀¹ = 6.", "the evaluation of the stated antiderivative between the "
          "limits written wrongly (3; before: ST-UNDEC-001 for the wrong value and the right one alike)", "∫₀¹ 6t dt", ("INT-SUBJ-001",)),
    _ma10("maths-definite-bracket-control", "maths", "control", "Also ∫₀¹ 6t dt = [3t²]₀¹ = 3.", "the right one: both links checked, nothing undecided",
          "∫₀¹ 6t dt"),
    _ma10("maths-definite-value", "maths", "answer", "Also ∫₀¹ 6t dt = 6.", "a definite integral of a polynomial stated with no working", "∫₀¹ 6t dt",
          ("INT-SUBJ-001",)),
    _ma10("maths-definite-value-control", "maths", "control", "Also ∫₀¹ 6t dt = 3.", "the right one", "∫₀¹ 6t dt"),
    _ma10("maths-definite-antiderivative", "maths", "answer", "Also ∫₀¹ 6t dt = [6t²]₀¹ = 6.", "a wrong antiderivative between the same limits",
          "[6t²]₀¹", ("INT-SUBJ-001",)),
    _ma10("maths-definite-decimal", "maths", "answer", "Also ∫₀² t² dt = 2.6.", "a decimal value of a definite integral (8/3)", "∫₀² t² dt",
          ("INT-SUBJ-001",)),
    _ma10("maths-definite-decimal-control", "maths", "control", "Also ∫₀² t² dt = 2.67.", "the right one, to 3 s.f.", "∫₀² t² dt"),
    _p("maths-definite-recorded-bracket", "maths", "receipt", "answer", (MA,), MA, "the recorded bracket's evaluation written wrongly ((12 − 8) − 1, "
       "its arithmetic consistent; before: ST-UNDEC-001)", edits=((MA, _MA_INT, "∫₀² v dt = [3t² − t³]₀² = (12 − 8) − 1 = 3"),), marker="(12 − 8) − 1",
       expected=("INT-SUBJ-001",)),
    # rule operand-precision for given data (the tester's 0.44% slip on a 12th power of the request's rate)
    _mi10("arithmetic-given-exact-power", "arithmetic", "answer", _MI_12, "$4000(1.036)^{12} = 6141.73$", "a slip under 1/100 on a 12th power of the "
          "request's exact rate (before: held at τ = 1/100)", "6141.73", ("INT-SUBJ-001",)),
    _mi10("arithmetic-given-exact-power-cent", "arithmetic", "answer", _MI_12, "$4000(1.036)^{12} = 6114.74$", "a value rounded the wrong way by a cent",
          "6114.74", ("INT-SUBJ-001",)),
    _mi10("arithmetic-given-exact-cube-control", "arithmetic", "control", _MI_PB, "Also $4000(1.036)^{3} = 4447.74$.\n\n" + _MI_PB, "a correct power of "
          "the request's rate, rounded to the cent", "4447.74"),
    _mi10("arithmetic-given-exact-cube", "arithmetic", "answer", _MI_PB, "Also $4000(1.036)^{3} = 4447.79$.\n\n" + _MI_PB, "a slip of five cents on it",
          "4447.79", ("INT-SUBJ-001",)),
    _ph("arithmetic-stated-expression-control", "arithmetic", "control", "Also 1/6.0 Ω + 1/6.0 Ω = 0.167 Ω⁻¹ + 0.167 Ω⁻¹ = 0.333 Ω⁻¹.", "a stated side "
        "of rounded numerals whose rounding the band must carry (found closing the class: the request's 6.0 is exact, so its rounding no longer "
        "widened τ)", "0.167 Ω⁻¹ + 0.167 Ω⁻¹"),
    # rule ellipsis-rounding (the tester's wrong 'nearest euro' rounding of a value written with an ellipsis)
    _mi10("rounding-ellipsis-nearest", "rounding", "answer", _MI_R, "$= 4787$ euros, to the nearest euro (A1)", "4787.58… rounded down to the nearest "
          "euro (before: ST-UNDEC-001 'an ellipsis', whatever the rounding)", "$= 4787$", ("INT-SUBJ-001",)),
    _mi10("rounding-ellipsis-bare", "rounding", "answer", _MI_R, "$= 4787.5$ (A1)", "a restatement of 4787.58… with a wrong last digit", "4787.5$",
          ("INT-SUBJ-001",)),
    _mi10("rounding-ellipsis-bare-control", "rounding", "control", _MI_R, "$= 4787.6$, to 1 d.p. (A1)", "the right one to 1 d.p.", "4787.6$"),
    # found closing the classes. Rule row-value, the clause reading: a value at a row in any order of its row, its column and its verb
    _es("givens-row-clause-after", "givens", "answer", _ES_W, "Dissolved oxygen was 3.9 mg dm⁻³ at site C.", "the column, the verb, the value and the "
        "row after it (site C's 3.8; before: nothing)", "3.9 mg dm⁻³ at site C", ("INT-SUBJ-004",)),
    _es("givens-row-clause-after-control", "givens", "control", _ES_W, "Dissolved oxygen was 3.8 mg dm⁻³ at site C.", "the right cell",
        "3.8 mg dm⁻³ at site C"),
    _es("givens-row-clause-no-comma", "givens", "answer", _ES_W, "At site C dissolved oxygen is 3.9 mg dm⁻³.", "the row first with no comma after it",
        "At site C dissolved", ("INT-SUBJ-004",)),
    _es("givens-row-clause-apposition", "givens", "answer", _ES_W, "Dissolved oxygen at site C, 3.9 mg dm⁻³, is the lowest.", "the value as an "
        "apposition", "3.9 mg dm⁻³, is the lowest", ("INT-SUBJ-004",)),
    _es("givens-row-clause-adverb", "givens", "answer", _ES_W, "Dissolved oxygen at site C is only 3.9 mg dm⁻³.", "an adverb between the verb and the "
        "value", "is only 3.9", ("INT-SUBJ-004",)),
    _es("givens-row-clause-possessive", "givens", "answer", _ES_W, "Site C's dissolved oxygen is 3.9 mg dm⁻³.", "the row as a possessive",
        "dissolved oxygen is 3.9", ("INT-SUBJ-004",)),
    _es("givens-row-clause-possessive-control", "givens", "control", _ES_W, "Site C's dissolved oxygen is 3.8 mg dm⁻³.", "the right cell",
        "dissolved oxygen is 3.8"),
    _es("givens-row-clause-of", "givens", "answer", _ES_W, "The dissolved oxygen of site C is 3.9 mg dm⁻³.", "the row after 'of'", "of site C is 3.9",
        ("INT-SUBJ-004",)),
    _es("givens-row-difference-control", "givens", "control", _ES_W, "Dissolved oxygen at site C is 5.8 mg dm⁻³ lower than at A.", "a difference "
        "stated at a row, correct (before: set against site C's cell, a false INT-SUBJ-004)", "5.8 mg dm⁻³ lower"),
    _es("givens-row-ratio-control", "givens", "control", _ES_W, "Nitrate at B is 7 times that at A.", "a ratio stated at a row, correct (before: a "
        "false INT-SUBJ-004)", "7 times that at A"),
    # a numbered row, a column told apart by its number, and a processed or another quantity at a row
    _pb("givens-row-numbered-of", "givens", "answer", _PB_END, _PB_END + "\nThe detector gave a measured count rate of 568 counts min⁻¹ at 12 h.",
        "the table's 586 at 12 h copied as 568, the column before 'of' and the row after the value (before: a numbered row was read in no such "
        "shape)", "rate of 568 counts", ("INT-SUBJ-004",)),
    _pb("givens-row-numbered-of-control", "givens", "control", _PB_END, _PB_END + "\nThe detector gave a measured count rate of 586 counts min⁻¹ at "
        "12 h.", "the right cell", "rate of 586 counts"),
    _pb("givens-row-numbered-label", "givens", "answer", _PB_END, _PB_END + "\nAt 12 h, measured count rate = 568 counts min⁻¹.", "a run labelled by "
        "the column after the numbered row", "rate = 568", ("INT-SUBJ-004",)),
    _pb("givens-row-numbered-clause", "givens", "answer", _PB_END, _PB_END + "\nThe measured count rate was 568 counts min⁻¹ at 12 h.", "the clause "
        "reading at a numbered row", "was 568 counts", ("INT-SUBJ-004",)),
    _pb("givens-row-numbered-symbol", "givens", "answer", _PB_END, _PB_END + "\nThe measured count rate at t = 12 h is 568 counts min⁻¹.", "the "
        "row's key after its symbol and '='", "at t = 12 h is 568", ("INT-SUBJ-004",)),
    _pb("givens-row-corrected-control", "givens", "control", _PB_END, _PB_END + "\nThe corrected count rate at 12 h is 566 counts min⁻¹.", "a "
        "processed quantity at a row, correct (before: set against the measured 586, a false INT-SUBJ-004)", "corrected count rate at 12 h"),
    _pb("givens-row-corrected-change-control", "givens", "control", _PB_END, _PB_END + "\nThe corrected rate falls from 1131 counts min⁻¹ at 4 h to "
        "566 counts min⁻¹ at 12 h.", "a change of the processed quantity between rows, correct (before: both values set against the measured "
        "column, and the first against part (d)'s value at 32 h)", "falls from 1131"),
    _pb("givens-row-other-quantity-control", "givens", "control", _PB_END, _PB_END + "\nThe decay rate at 12 h is 0.087 h⁻¹.", "another quantity "
        "of the column's dimension, named by another modifier (before: set against the measured count rate, a false INT-SUBJ-004)",
        "decay rate at 12 h"),
    _ch10("givens-row-trial", "givens", "answer", "At 30.0 °C, trial 2 took 43.0 s.", "a trial's time copied wrongly (34.0), its column told apart "
          "from the other trials by its number (before: three columns of the same words, none read)", "trial 2 took 43.0", ("INT-SUBJ-004",)),
    _ch10("givens-row-trial-control", "givens", "control", "At 30.0 °C, trial 2 took 34.0 s.", "the right cell", "trial 2 took 34.0"),
    _ch10("givens-row-trial-time", "givens", "answer", "The time for trial 2 at 30.0 °C is 43.0 s.", "the same with the column's words",
          "trial 2 at 30.0 °C is 43.0", ("INT-SUBJ-004",)),
    # rule table-data: the clause is the value's own statement
    _p("wrong_given-table-data-neighbour", "wrong_given", "receipt", "answer", (ES,), ES, "B's nitrate written 6.1 (site B's dissolved oxygen) after a "
       "sentence naming the dissolved oxygen (before: the window crossed into it, two columns were named, and the line was read in none)",
       edits=((ES, "(d) Upgrading the sewage treatment works to remove nitrate controls the release at source.", "(d) Upgrading the sewage treatment "
               "works also raises the dissolved oxygen downstream."), (ES, "to 8.4 mg dm⁻³ at B, across", "to 6.1 mg dm⁻³ at B, across")),
       marker="to 6.1 mg dm⁻³ at B", expected=("INT-SUBJ-004",)),
    _p("wrong_given-table-data-neighbour-control", "wrong_given", "receipt", "control", (ES,), ES, "the same sentence before the line's right values",
       edits=((ES, "(d) Upgrading the sewage treatment works to remove nitrate controls the release at source.", "(d) Upgrading the sewage treatment "
               "works also raises the dissolved oxygen downstream."),), marker="raises the dissolved oxygen downstream"),
    # rule definite-integral: a limit with a sign, and limits after '_' and '^' in plain text
    _ma10("maths-definite-signed", "maths", "answer", "Also ∫₋₁¹ 3t² dt = 0.", "a definite integral with a signed limit, wrong (2; before: no check and "
          "no ST code at all: the span ended at the subscript minus)", "∫₋₁¹ 3t² dt", ("INT-SUBJ-001",)),
    _ma10("maths-definite-signed-control", "maths", "control", "Also ∫₋₁¹ 3t² dt = 2.", "the right one", "∫₋₁¹ 3t² dt"),
    _ma10("maths-definite-caret", "maths", "answer", "Also ∫_0^1 6t dt = 6.", "limits after '_' and '^' in plain text, wrong (3; before: no check and no "
          "ST code)", "∫_0^1 6t dt", ("INT-SUBJ-001",)),
    _ma10("maths-definite-caret-control", "maths", "control", "Also ∫_0^1 6t dt = 3.", "the right one", "∫_0^1 6t dt"),
    # rule ellipsis-rounding: a value written with its digits cut in plain text
    _ma10("rounding-ellipsis-plain", "rounding", "answer", "Also 8/3 = 2.66… = 2.6, to 2 s.f.", "a cut value restated to 2 s.f. the wrong way (2.7; "
          "before: the plain '…' ended the run, so only a false failure of '8/3 = 2.66' named the line)", "= 2.6, to 2 s.f.", ("INT-SUBJ-001",)),
    _ma10("rounding-ellipsis-plain-control", "rounding", "control", "Also 8/3 = 2.66… = 2.7, to 2 s.f.", "the right one (before: the false failure of "
          "'8/3 = 2.66')", "= 2.7, to 2 s.f."),
    _ma10("rounding-ellipsis-cut-control", "rounding", "control", "Also 8/3 = 2.66…", "a computed value written with its digits cut (before: a false "
          "INT-SUBJ-001, the cut value read as rounded)", "8/3 = 2.66…"),
    _ma10("rounding-ellipsis-latex", "rounding", "answer", "Also $\\frac{8}{3} = 2.66\\ldots = 2.6$, to 2 s.f.", "the same restatement in LaTeX (before: "
          "ST-UNDEC-001 'an ellipsis' whatever the rounding)", "2.66\\ldots = 2.6", ("INT-SUBJ-001",)),
    # rule operand-precision for given data: a slip on the request's exact data, and the slip earlier test data carried
    _ph("arithmetic-given-exact-ph", "arithmetic", "answer", "Also (12 V)² / 4.0 Ω = 36.3 W.", "a slip under 1/100 on the request's emf and "
        "resistance, both exact (36 W; before: held within τ = 1/100)", "= 36.3 W", ("INT-SUBJ-001",)),
    _ph("arithmetic-given-exact-ph-control", "arithmetic", "control", "Also (12 V)² / 4.0 Ω = 36 W.", "the right value", "= 36 W"),
    _p("arithmetic-given-exact-digit", "arithmetic", "receipt", "answer", (MI,), MI, "4000 × 1.036⁵ written 4773.7406 (4773.740074…: the fourth decimal "
       "slips; earlier tests wrote it as correct, before: held within the rounding 1.036 was taken to carry)",
       edits=((MI, _MI_END, "Check: 4000 × 1.036⁵ = 4773.7406, so 4773.74 euros to the nearest cent.\n\n" + _MI_END),), marker="4773.7406",
       expected=("INT-SUBJ-001",)),
)
_BI_ATP = "which makes ATP. [1 spare]"
_ES_TEMP = "Water temperature was between 17 °C and 18 °C at every site, so it does not explain the difference."
_CS_FEW = "That is still far fewer than 1,000."
_PH_A11 = "(a) [2]\n"
_PH_RR = "R + r = 2.4 Ω + 0.50 Ω = 2.9 Ω"
_MA_B11 = "    6t − 3t² = 0\n"
_MI_PA = "**Part (a) — find — 3 marks**"
_MI_A11 = "$4000(1.036)^{11} = 5902.25$"
_MI_N = "so $n > 11.28\\ldots$ (A1)"


def _r11(pid: str, cls: str, kind: str, stem: str, old: str, new: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (stem,), stem, desc, edits=((stem, old, new),), marker=marker, expected=expected)


#: STEM repair 11 (design section 42): the eleventh independent test's plants and a control for each, on the class whose cause it found, and
#: the shapes of the same classes found closing them. Rule exact-rounding: a rounded quotient of whole numbers stated to its last digit (two
#: or more figures) holds, a whole computed value stated otherwise fails; rule result-rounding: a rounding a line states for its own result;
#: rule given-data: the request's data, and a Given restating them, taken as written (a value one unit off fails); rules part-condition and
#: root-statement: a letter another part's question gives a value is the unknown of this part's equations, its factorisation and roots
#: checked; rule function-value: a value of the request's or the answer's function stated in prose; rule inequality-solution: the bound a step
#: solves a linear relation for; rule derivative: a polynomial's derivative by the power rule; rules same-shape and unbound-substitution: a wrong
#: given substituted where no symbol is bound to it; rule prose-base: a base phrase opening the clause.
REPAIR11_PROBES: tuple[Probe, ...] = (
    # rule exact-rounding (before: exact mode gave h = 0, so the tester's correct working failed, INT-SUBJ-001)
    _r11("arithmetic-exact-rounded-quotient-control", "arithmetic", "control", BI, _BI_ATP, _BI_ATP + "\nFrom 10 °C to 35 °C the uptake rises by "
         "(92 − 18) ÷ 18 × 100 = 411%.", "a percentage change of whole numbers rounded to its last digit (411.1%; before: a false INT-SUBJ-001)", "= 411%"),
    _r11("arithmetic-exact-rounded-quotient", "arithmetic", "answer", BI, _BI_ATP, _BI_ATP + "\nFrom 10 °C to 35 °C the uptake rises by "
         "(92 − 18) ÷ 18 × 100 = 311%.", "the same with a slip", "= 311%", ("INT-SUBJ-001",)),
    _r11("arithmetic-exact-next-digit", "arithmetic", "answer", BI, _BI_ATP, _BI_ATP + "\nFrom 10 °C to 35 °C the uptake rises by "
         "(92 − 18) ÷ 18 × 100 = 412%.", "a rounding one unit off in its last digit (411.1 is 411)", "= 412%", ("INT-SUBJ-001",)),
    _r11("arithmetic-exact-ess-control", "arithmetic", "control", ES, _ES_TEMP, "From A to B the nymph count falls by (34 − 9) ÷ 34 × 100 = 74%.",
         "the tester's ESS control in place of a sentence of the same length, so the answer keeps within its word limit (73.5%; before: a false "
         "INT-SUBJ-001)", "= 74%"),
    _r11("arithmetic-exact-third-control", "arithmetic", "control", CS, _CS_FEW, _CS_FEW + "\nOn average a linear search compares 1,000 ÷ 2 = 500 "
         "items, and 1,000 ÷ 3 = 333 items is a third of the list.", "the tester's computer science control (333.3; before: a false INT-SUBJ-001)",
         "1,000 ÷ 3 = 333"),
    _r11("arithmetic-exact-third", "arithmetic", "answer", CS, _CS_FEW, _CS_FEW + "\nOn average a linear search compares 1,000 ÷ 2 = 500 "
         "items, and 1,000 ÷ 3 = 334 items is a third of the list.", "the same rounded the wrong way (333.3 is 333)", "1,000 ÷ 3 = 334",
         ("INT-SUBJ-001",)),
    # rule result-rounding (before: a rounding written after the chain's own result was read by no rule)
    _r11("rounding-result-stated-control", "rounding", "control", BI, _BI_ATP, _BI_ATP + "\nFrom 35 °C to 40 °C the uptake falls by "
         "(92 − 61) ÷ 92 × 100 = 34% to 2 s.f.", "a result with the rounding its line states (33.7%; before: a false INT-SUBJ-001)", "= 34% to 2 s.f."),
    _r11("rounding-result-stated", "rounding", "answer", BI, _BI_ATP, _BI_ATP + "\nFrom 35 °C to 40 °C the uptake falls by "
         "(92 − 61) ÷ 92 × 100 = 33% to 2 s.f.", "the same rounded the wrong way", "= 33% to 2 s.f.", ("INT-SUBJ-001",)),
    _r11("rounding-result-other-clause-control", "rounding", "control", MI, _MI_A11, _MI_A11 + ", so 5902 euros to the nearest euro,",
         "a rounding that closes an earlier value's restatement before the next chain in its statement ('…, so 5902 euros to the nearest "
         "euro, and $4000(1.036)^{12} = 6114.73$'): the restated value's, never the next chain's result's (the eleventh tester's control; "
         "a false INT-SUBJ-004 while rule result-rounding read it as the result's)", "so 5902 euros"),
    # rule given-data (before: R7's inclusive band held a Given one unit off in its last digit)
    _r11("givens-one-unit-off", "givens", "answer", PH, _PH_A11, _PH_A11 + "Given: ε = 12 V, r = 0.49 Ω, R₁ = 4.0 Ω, R₂ = 6.0 Ω.\n",
         "a Given one unit off the request's 0.50 ohm (before: |0.49 − 0.50| ≤ h + h held)", "r = 0.49 Ω", ("INT-SUBJ-004",)),
    _r11("givens-one-unit-off-rate", "givens", "answer", MI, _MI_PA, "Given: P = 4000 euros and r = 3.7%.\n\n" + _MI_PA,
         "a Given rate one unit off the request's 3.6%", "r = 3.7%", ("INT-SUBJ-004",)),
    _r11("givens-rounded-control", "givens", "control", PH, _PH_A11, _PH_A11 + "Given: ε = 12.0 V, r = 0.5 Ω, R₁ = 4 Ω, R₂ = 6.00 Ω.\n",
         "the request's data restated to other places (each the other rounded)", "r = 0.5 Ω"),
    _p("wrong_given-given-data-substituted", "wrong_given", "receipt", "answer", (PH,), PH, "a value one unit off substituted for a Given restating "
       "the request's data (0.49 Ω for 'r = 0.50 Ω'; before: R7's band held it)",
       edits=((PH, _PH_A11, _PH_A11 + "Given: r = 0.50 Ω.\n"), (PH, _PH_RR, "R + r = 2.4 Ω + 0.49 Ω = 2.89 Ω")), marker="0.49 Ω", expected=("INT-SUBJ-001",)),
    _p("wrong_given-given-data-substituted-control", "wrong_given", "receipt", "control", (PH,), PH, "the Given's value substituted at another "
       "place (0.5 Ω, a rounding of it)", edits=((PH, _PH_A11, _PH_A11 + "Given: r = 0.50 Ω.\n"), (PH, _PH_RR, "R + r = 2.4 Ω + 0.5 Ω = 2.9 Ω")),
       marker="0.5 Ω = 2.9 Ω"),
    # rules part-condition and root-statement (before: the request's '(a) … when t = 1' made t given everywhere: no step, no roots checked)
    _r11("equations-factorising-part", "equations", "answer", MA, _MA_B11, _MA_B11 + "    so t(6 − 2t) = 0\n", "the tester's factorisation in "
         "part (b), wrong", "t(6 − 2t)", ("INT-SUBJ-001",)),
    _r11("equations-factorising-part-control", "equations", "control", MA, _MA_B11, _MA_B11 + "    so t(6 − 3t) = 0\n", "the right one", "t(6 − 3t)"),
    _r11("equations-factorising-sign", "equations", "answer", MA, "    3t(2 − t) = 0  M1", "    3t(2 + t) = 0  M1", "the tester's second "
         "factorisation, its sign wrong (and the roots it no longer gives)", "3t(2 + t)", ("INT-SUBJ-001",)),
    _r11("maths-root-statement", "maths", "answer", MA, "keeps t = 0.", "keeps t = 1.", "a root stated in prose that the equation does not have",
         "keeps t = 1", ("INT-SUBJ-001",)),
    # rule function-value (before: only a Given of a function's value was read)
    _r11("maths-function-value-prose", "maths", "answer", MA, "    a = 0 m s⁻²  A1", "    a = 0 m s⁻²  A1\n    The velocity at t = 1 is "
         "v(1) = 4 m s⁻¹.", "the tester's value of the request's v(t) in prose, wrong (3)", "v(1) = 4", ("INT-SUBJ-004",)),
    _r11("maths-function-value-prose-control", "maths", "control", MA, "    a = 0 m s⁻²  A1", "    a = 0 m s⁻²  A1\n    The velocity at t = 1 is "
         "v(1) = 3 m s⁻¹.", "the right value", "v(1) = 3"),
    _r11("maths-function-value-rest", "maths", "answer", MA, "    a = 0 m s⁻²  A1", "    a = 0 m s⁻²  A1\n    At t = 2 the particle is at rest: "
         "v(2) = 1.", "the tester's second value, wrong (0)", "v(2) = 1", ("INT-SUBJ-004",)),
    _r11("maths-function-value-rest-control", "maths", "control", MA, "    a = 0 m s⁻²  A1", "    a = 0 m s⁻²  A1\n    At t = 2 the particle is "
         "at rest: v(2) = 0.", "the right value", "v(2) = 0"),
    # rule inequality-solution (before: the bound was neither checked nor named; n had the student's value 11.46, so no step was read)
    _r11("maths-inequality-solution", "maths", "answer", MI, _MI_N, "so $n > 13.28\\ldots$ (A1)", "the tester's restatement of the solution, wrong "
         "(11.28…)", "n > 13.28", ("INT-SUBJ-001",)),
    _r11("maths-inequality-direction", "maths", "answer", MI, _MI_N, "so $n < 11.28\\ldots$ (A1)", "the direction reversed", "n < 11.28",
         ("INT-SUBJ-001",)),
    _r11("maths-inequality-solution-control", "maths", "control", MI, _MI_N, "so $n > 11.279\\ldots$ (A1)", "the bound written to one more digit",
         "n > 11.279"),
    # rule derivative (before: every derivative was ST-UNDEC-001, never failed)
    _r11("formulas-derivative-power", "formulas", "answer", MA, "    Distance travelled = 8 m  A1", "    Distance travelled = 8 m  A1\n    Also "
         "d/dt (3t²) = 3t.", "the tester's derivative of a written polynomial, wrong (6t)", "d/dt (3t²)", ("INT-SUBJ-001",)),
    _r11("formulas-derivative-power-control", "formulas", "control", MA, "    Distance travelled = 8 m  A1", "    Distance travelled = 8 m  A1\n"
         "    Also d/dt (3t²) = 6t.", "the right one", "d/dt (3t²)"),
    # rules same-shape and unbound-substitution (before: a wrong given substituted with no symbol bound had neither a check nor an ST code)
    _r11("wrong_given-model-principal", "wrong_given", "answer", MI, _MI_A11, "$4500(1.036)^{11} = 6640.03$", "the tester's principal written "
         "wrongly in the model's other evaluation (4000 euros)", "6640.03", ("INT-SUBJ-004",)),
    _r11("wrong_given-model-rate", "wrong_given", "answer", MI, _MI_A11, "$4000(1.037)^{11} = 5928.94$", "the growth factor written wrongly "
         "(1.036, the request's 3.6%)", "5928.94", ("INT-SUBJ-004",)),
    _r11("wrong_given-model-hypothesis-control", "wrong_given", "control", MI, _MI_A11, "if Kai had invested 4500 euros instead, "
         "$4500(1.036)^{11} = 6640.03$", "the same value under a hypothesis", "6640.03"),
    _r11("wrong_given-unbound-symbol", "wrong_given", "answer", PH, _PH_RR, "R + r = 2.4 Ω + 0.40 Ω = 2.8 Ω", "a value for r, which the answer "
         "gives no value but substitutes the request's 0.50 ohm for in part (c)", "0.40 Ω", ("INT-SUBJ-004",)),
    _r11("wrong_given-unbound-symbol-digit", "wrong_given", "answer", PH, _PH_RR, "R + r = 2.4 Ω + 0.49 Ω = 2.89 Ω", "the same one unit off",
         "0.49 Ω", ("INT-SUBJ-004",)),
    _r11("wrong_given-unbound-symbol-control", "wrong_given", "control", PH, _PH_RR, "R + r = 2.4 Ω + 0.5 Ω = 2.9 Ω", "the request's value to "
         "another place", "0.5 Ω = 2.9 Ω"),
    # rule prose-base, a base phrase opening the clause (before: not read)
    _cs("boolean-base-opening", "answer", "In binary, 1000 is 1111101100.", "the tester's base conversion with the base phrase opening the clause, "
        "wrong (1111101000)", "1111101100", ("INT-SUBJ-001",)),
    _cs("boolean-base-opening-control", "control", "In binary, 1000 is 1111101000.", "the right one", "1111101000"),
)
_PH_FALL = "the current from the cell falls, from 4.1 A to 2.7 A."
#: rule arithmetic-restatement's translation plants: the derivation premise removed and the conclusion restated by a writer's-own premise
_CIRC = dict(agent_kind="translation_circular", agent_outcome="confirmed", agent_rule="they do not, and a premise SHOWN not to be data")


def _r12(pid: str, cls: str, kind: str, stem: str, old: str, new: str, desc: str, marker: str, expected: tuple[str, ...] = ()) -> Probe:
    return _p(pid, cls, "receipt", kind, (stem,), stem, desc, edits=((stem, old, new),), marker=marker, expected=expected)


#: STEM repair 12 (design section 43): the twelfth independent test's plants and a control for each, on the class whose cause it found, and
#: the shapes of the same classes found closing them. Rule identity-variable: an identity checked for every value of its variable (a
#: derivative, an antiderivative, a definite integral's bracket, a Given function) takes no value for it from the request, so the request's
#: 't = 1' no longer makes a wrong one hold; rule prose-base: a hexadecimal numeral with letter digits, read where words name base 16 for it;
#: rule inline-restatement: a value restated after an approximation word ('which is about', ', about'); rule arithmetic-restatement: a STEM
#: translation whose conclusion a writer's-own premise restates with its terms moved across or both sides scaled, and a line of working on
#: numbers alone, which stays a derivation.
REPAIR12_PROBES: tuple[Probe, ...] = (
    # rule identity-variable (before: the request's 't = 1' bound the variable, so each held, ENTAILED, with no finding)
    _r12("maths-derivative-request-value", "maths", "answer", MA, _MA_APPEND, "The rate of change of a is d/dt (6 − 6t) = −6t.\n" + _MA_APPEND,
         "the tester's derivative of a written polynomial, wrong (−6), which held at the request's t = 1", "= −6t", ("INT-SUBJ-001",)),
    _r12("maths-derivative-request-value-control", "maths", "control", MA, _MA_APPEND, "The rate of change of a is d/dt (6 − 6t) = −6.\n"
         + _MA_APPEND, "the right one", "(6 − 6t) = −6."),
    _r12("maths-derivative-linear", "maths", "answer", MA, _MA_APPEND, "Also d/dt (5t + 2) = 5t.\n" + _MA_APPEND, "the tester's second derivative "
         "of a linear polynomial, wrong (5)", "(5t + 2) = 5t", ("INT-SUBJ-001",)),
    _r12("maths-derivative-linear-control", "maths", "control", MA, _MA_APPEND, "Also d/dt (5t + 2) = 5.\n" + _MA_APPEND, "the right one",
         "(5t + 2) = 5."),
    _r12("maths-antiderivative-request-value", "maths", "answer", MA, _MA_APPEND, "Also ∫4t dt = 4t.\n" + _MA_APPEND, "an antiderivative whose "
         "derivative (4) the request's t = 1 made agree with the integrand, wrong (2t²)", "∫4t dt = 4t", ("INT-SUBJ-001",)),
    _r12("maths-antiderivative-request-value-control", "maths", "control", MA, _MA_APPEND, "Also ∫4t dt = 2t² + C.\n" + _MA_APPEND,
         "the right one", "∫4t dt = 2t²"),
    _r12("maths-definite-bracket-request-value", "maths", "answer", MA, _MA_APPEND, "Also ∫₀¹ 4t dt = [4t]₀¹.\n" + _MA_APPEND, "a definite "
         "integral's evaluation bracket whose derivative the request's t = 1 made agree with the integrand, wrong ([2t²]₀¹)", "[4t]₀¹",
         ("INT-SUBJ-001",)),
    _r12("maths-definite-bracket-request-value-control", "maths", "control", MA, _MA_APPEND, "Also ∫₀¹ 4t dt = [2t²]₀¹.\n" + _MA_APPEND,
         "the right one", "[2t²]₀¹"),
    _r12("givens-function-request-value", "givens", "answer", MA, _MA_APPEND, "Given: v(t) = 3.\n\n" + _MA_APPEND, "a Given function that the "
         "request's v(t) = 6t − 3t² equals only at t = 1 (a warning: that the Given restates the request's function is a reading)", "v(t) = 3.",
         ("INT-SUBJ-004",)),
    _r12("givens-function-request-value-control", "givens", "control", MA, _MA_APPEND, "Given: v(t) = 6t − 3t².\n\n" + _MA_APPEND,
         "the request's own function", "Given: v(t)"),
    # rule prose-base, hexadecimal numerals with letter digits (before: neither a check nor an ST code)
    _cs("boolean-hex-opening", "answer", "In hexadecimal, 1000 is 3E9.", "the tester's hexadecimal restatement with letter digits after a base "
        "phrase opening the clause, wrong (3E8)", "3E9", ("INT-SUBJ-001",)),
    _cs("boolean-hex-opening-control", "control", "In hexadecimal, 1000 is 3E8.", "the right one", "3E8"),
    _cs("boolean-hex-subscript", "answer", "In hexadecimal, 1000 is 3E9₁₆.", "the same with a base subscript (before: the phrase was read as the "
        "first numeral's base, so both came out in base 16 and nothing was planned)", "3E9₁₆", ("INT-SUBJ-001",)),
    _cs("boolean-hex-subscript-control", "control", "In hexadecimal, 1000 is 3E8₁₆.", "the right one", "3E8₁₆"),
    _cs("boolean-hex-base16", "answer", "In base 16, 1000 is 3E9.", "the base phrase 'In base 16'", "3E9", ("INT-SUBJ-001",)),
    _cs("boolean-hex-words", "answer", "1000 in denary is 3E9 in hexadecimal.", "each base named right after its numeral", "3E9",
        ("INT-SUBJ-001",)),
    _cs("boolean-hex-before", "answer", "The hexadecimal number 3E9 is 1000 in denary.", "the hexadecimal numeral first, its base named before it",
        "3E9", ("INT-SUBJ-001",)),
    _cs("boolean-hex-before-control", "control", "The hexadecimal number 3E8 is 1000 in denary.", "the right one", "3E8"),
    _cs("boolean-hex-letters", "answer", "In hexadecimal, 255 is FE.", "a hexadecimal numeral of letters alone, wrong (FF)", "is FE",
        ("INT-SUBJ-001",)),
    _cs("boolean-hex-letters-control", "control", "In hexadecimal, 255 is FF.", "the right one", "is FF"),
    _cs("boolean-hex-unnamed-control", "control", "The largest byte value, 255, is FE.", "letter digits no word names the base of: never read "
        "as a numeral (no check)", "is FE"),
    # the same rule's two false failures on correct working, found closing the class: a numeral set equal with '=' to one whose base the words
    # after it name (before: written arithmetic on decimal numerals, 3E8 as 3 × 10⁸), and a base phrase opening the clause with no comma
    # (before: read as the first numeral's base only)
    _cs("boolean-hex-equals", "answer", "So 1000 = 3E9 in hexadecimal.", "a hexadecimal restatement written with '=', wrong (3E8)", "3E9 in",
        ("INT-SUBJ-001",)),
    _cs("boolean-hex-equals-control", "control", "So 1000 = 3E8 in hexadecimal.", "the right one (before: INT-SUBJ-001, 3E8 read as 3 × 10⁸)",
        "3E8 in"),
    _cs("boolean-base-no-comma", "answer", "In binary 1000 is 1111101100.", "a base phrase opening the clause with no comma, wrong (1111101000)",
        "is 1111101100", ("INT-SUBJ-001",)),
    _cs("boolean-base-no-comma-control", "control", "In binary 1000 is 1111101000.", "the right one (before: INT-SUBJ-001, the phrase read as "
        "1000's base)", "is 1111101000"),
    # rule inline-restatement after an approximation word (before: no check)
    _r12("rounding-approx-which-is", "rounding", "answer", PH, _PH_FALL, "the current from the cell falls: I = 12 V / 4.5 Ω = 2.67 A, which is "
         "about 2.6 A.", "the tester's restatement after ', which is about', rounded wrongly (2.7 A)", "about 2.6 A", ("INT-SUBJ-001",)),
    _r12("rounding-approx-which-is-control", "rounding", "control", PH, _PH_FALL, "the current from the cell falls: I = 12 V / 4.5 Ω = 2.67 A, "
         "which is about 2.7 A.", "the right one", "about 2.7 A"),
    _r12("rounding-approx-stated", "rounding", "answer", PH, _PH_FALL, "the current from the cell falls: I = 12 V / 4.5 Ω = 2.67 A, about 2.6 A "
         "to 2 s.f.", "the tester's restatement after ', about' with the rounding it states", "about 2.6 A to 2 s.f.", ("INT-SUBJ-001",)),
    _r12("rounding-approx-stated-control", "rounding", "control", PH, _PH_FALL, "the current from the cell falls: I = 12 V / 4.5 Ω = 2.67 A, about "
         "2.7 A to 2 s.f.", "the right one", "about 2.7 A to 2 s.f."),
    _r12("rounding-approx-percent", "rounding", "answer", ES, _ES_TEMP, "From B to C the dissolved oxygen falls by (6.1 − 3.8) ÷ 6.1 × 100 = "
         "37.7%, about 37%.", "the tester's percentage restated after ', about', in place of a sentence of the same length so the answer keeps within "
         "its word limit (37.7% is 38%)", "about 37%", ("INT-SUBJ-001",)),
    _r12("rounding-approx-percent-control", "rounding", "control", ES, _ES_TEMP, "From B to C the dissolved oxygen falls by (6.1 − 3.8) ÷ 6.1 × "
         "100 = 37.7%, about 38%.", "the right one", "about 38%"),
    # rule arithmetic-restatement (before: the arithmetic of the conjunct's symbols was opaque, so these restated nothing, no OVS-TRN-006, and a
    # translation_circular accusation was refuted)
    _p("equations-translation-restated-affine", "equations", "translation", "translation", (ES,), ES, "ess-t13's percentage decrease assumed as "
       "'pd − 60.4 = 0', its derivation removed (the tester's plant)", translation=(ES, "g1.1", "restate:affine:d_pd"), expected=("OVS-TRN-006",),
       **_CIRC),
    _p("maths-translation-restated-scaled", "maths", "translation", "translation", (BI,), BI, "bi-t13's percentage increase assumed as "
       "'2 × pct = 200', its derivation removed (the tester's plant)", translation=(BI, "g2.1", "restate:scaled:D-pct:2"), expected=("OVS-TRN-006",),
       **_CIRC),
    _p("physics-translation-restated-linear", "physics", "translation", "translation", (PH,), PH, "ph-t13's terminal potential difference assumed "
       "as '2 × vterm − 4.0 = 15.8', the law removed", translation=(PH, "g3.2", "restate:linear:law:2:4.0"), expected=("OVS-TRN-006",), **_CIRC),
    _p("boolean-translation-restated-affine", "boolean", "translation", "translation", (CS,), CS, "cs-t13's linear-search count assumed as "
       "'lin − 1000 = 0', its derivation removed (the class on the recorded translations the repository keeps)",
       translation=(CS, "g11.2", "restate:affine:d_lin"), expected=("OVS-TRN-006",), **_CIRC),
    _p("maths-translation-working-control", "maths", "translation", "control", (BI,), BI, "bi-t13's percentage increase from a writer's-own line "
       "of working on the table's numbers alone, 'pct = (80 − 40) ÷ 40 × 100', in place of its derivation: a derivation the engine checks, never "
       "a restatement", translation=(BI, "g2.1", "working:D-pct")),
)
PROBES: tuple[Probe, ...] = (ANSWER_PROBES + TRANSLATION_PROBES + CONVERSION_PROBES + TABLE_UNIT_PROBES + REPAIR3_PROBES + REPAIR4_PROBES
                             + REPAIR5_PROBES + REPAIR6_PROBES + REPAIR7_PROBES + REPAIR8_PROBES + REPAIR9_PROBES + REPAIR10_PROBES + REPAIR11_PROBES
                             + REPAIR12_PROBES)


# ============================================================================================ planting
def edit_answers(dest: Path, edits: tuple[tuple[str, str, str], ...]) -> None:
    """Replace exactly one occurrence of each ``old`` in the copy's answer ``stem`` (refused otherwise: a probe that no
    longer finds its site says so instead of planting nothing). A relayed record of the copy that shows a dependent agent
    the edited specialist's GENUINE answer is removed, so the dependent is shown the planted report the relay forwards
    (the record would otherwise be a stale document beside it)."""
    edited: set[str] = set()
    for stem, old, new in edits:
        p = dest / "specialists" / f"{stem}.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        n = d["response_text"].count(old)
        if n != 1:
            raise H.HarnessError(f"probe site {old[:60]!r} occurs {n} times in {stem}'s recorded answer; exactly one is required")
        d["response_text"] = d["response_text"].replace(old, new)
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        edited.add(d.get("task_id") or stem)
    rel = dest / "relayed"
    if rel.is_dir():
        for r in sorted(rel.glob("*.json")):
            if json.loads(r.read_text(encoding="utf-8")).get("peer_of") in edited:
                r.unlink()


_edit_answers = edit_answers


def probe(probe_id: str) -> "Probe":
    """The probe ``probe_id`` (the tampering suite plants its STEM faults from these definitions)."""
    found = next((p for p in PROBES if p.probe_id == probe_id), None)
    if found is None:
        raise KeyError(f"unknown STEM probe {probe_id!r}")
    return found


def _var(name: str) -> dict:
    return {"op": "var", "name": name}


def _real(v: str) -> dict:
    return {"op": "real", "value": v}


def _premise(problem: dict, pid: str) -> dict:
    return next(p for p in problem["premises"] if p["id"] == pid)


#: How each translation plant changes bi-t13's recorded translation of its percentage claim (``pct``: 100 from
#: ``D-pct: pct × 40 = (t30 − t20) × 100``, the table's uptakes T-t10 ... T-t40 as premises).
def _plant(problem: dict, plant: str, delivered_id: str) -> dict:
    p = copy.deepcopy(problem)
    if plant == "convert_t30":
        _premise(p, "T-t30")["expr"]["right"] = _real("0.08")
    elif plant == "widen":  # refused by the merged translator itself (exactness): no probe plants it since the second translator merge
        p["conclusion"]["expr"] = {"op": "and", "args": [{"op": "ge", "left": _var("pct"), "right": _real("90")},
                                                         {"op": "le", "left": _var("pct"), "right": _real("110")}]}
    elif plant == "at_least_90":
        p["conclusion"]["expr"] = {"op": "ge", "left": _var("pct"), "right": _real("90")}
    elif plant == "result_120":
        p["conclusion"]["expr"] = {"op": "eq", "left": _var("pct"), "right": _real("120")}
    elif plant == "other_given":
        _premise(p, "D-pct")["expr"]["right"]["args"][0]["right"] = _var("t25")
    elif plant == "rearranged":
        _premise(p, "D-pct")["expr"]["left"]["args"][1] = _real("80")
    elif plant == "mixed_quantities":
        _premise(p, "D-pct")["expr"]["right"]["args"][0]["right"] = _real("20")
    elif plant == "no_ratio":
        _premise(p, "D-pct")["expr"] = {"op": "eq", "left": _var("pct"), "right": {"op": "sub", "left": _var("t30"), "right": _var("t20")}}
    elif plant.startswith("number:"):
        _kind, where, old, new = plant.split(":", 3)
        if not _replace_number(p, where, old, new):
            raise H.HarnessError(f"the recorded translation has no numeral {old} in its {where} to plant {new}")
    elif plant.startswith("restate:"):
        # STEM repair 12 (rule arithmetic-restatement): the derivation premise removed and the conclusion 'x = v' assumed by a writer's-own
        # premise that restates it with its terms moved across ('affine': x − v = 0), both sides scaled ('scaled:k': k × x = k·v) or both
        # ('linear:k:b': k × x − b = k·v − b), each number written as one numeral
        _kind, how, drop, *args = plant.split(":")
        c = p["conclusion"]["expr"]
        v = _literal_value(c.get("right")) if c.get("op") == "eq" and (c.get("left") or {}).get("op") == "var" else None
        if v is None or not any(x["id"] == drop for x in p["premises"]):
            raise H.HarnessError(f"the recorded translation's conclusion is no 'symbol = number', or it has no premise {drop} to remove, for {plant}")
        x = copy.deepcopy(c["left"])
        whole = c["right"].get("op") == "int"  # an Int symbol's numerals are written as integers (the IR sorts them)

        def num(val: Fraction) -> dict:
            return {"op": "int", "value": str(val.numerator)} if whole and val.denominator == 1 else _real(_decimal(val))
        if how == "affine":
            e = {"op": "eq", "left": {"op": "sub", "left": x, "right": num(v)}, "right": num(Fraction(0))}
        elif how == "scaled":
            k = Fraction(args[0])
            e = {"op": "eq", "left": {"op": "mul", "args": [num(k), x]}, "right": num(k * v)}
        elif how == "linear":
            k, b = Fraction(args[0]), Fraction(args[1])
            e = {"op": "eq", "left": {"op": "sub", "left": {"op": "mul", "args": [num(k), x]}, "right": num(b)}, "right": num(k * v - b)}
        else:
            raise ValueError(plant)
        p["premises"] = [q for q in p["premises"] if q["id"] != drop] + [
            {"id": "P_restated", "expr": e, "label": "the claim's result", "grounding": {"kind": "specialist_inference", "source_refs": [], "certainty": "established"}}]
    elif plant.startswith("working:"):
        # STEM repair 12, the control: bi-t13's derivation replaced by a writer's-own line of working on the table's numbers alone,
        # (80 − 40) ÷ 40 × 100, arithmetic of numbers the engine evaluates (never read as a restatement)
        drop = plant.split(":", 1)[1]
        work = {"op": "mul", "args": [{"op": "div", "left": {"op": "sub", "left": _real("80"), "right": _real("40")}, "right": _real("40")}, _real("100")]}
        p["premises"] = [q for q in p["premises"] if q["id"] != drop] + [
            {"id": "P_working", "expr": {"op": "eq", "left": _var("pct"), "right": work}, "label": "percentage increase = (80 - 40) / 40 x 100",
             "grounding": {"kind": "specialist_inference", "source_refs": [], "certainty": "established"}}]
    elif plant.startswith("numbers:"):  # several numerals at once: 'numbers:any:9.6=0.0096,3.8=0.0038' (STEM repair 2)
        _kind, where, pairs = plant.split(":", 2)
        for pair in pairs.split(","):
            old, new = pair.split("=", 1)
            if not _replace_number(p, where, old, new):
                raise H.HarnessError(f"the recorded translation has no numeral {old} in its {where} to plant {new}")
    else:
        raise ValueError(plant)
    return p


def _literal_value(node: Any) -> Optional[Fraction]:
    """The value of a numeral of the IR (``int``, ``real``); None for anything else. Data only."""
    if isinstance(node, dict) and node.get("op") in ("int", "real") and isinstance(node.get("value"), str):
        try:
            return Fraction(node["value"])
        except (ValueError, ZeroDivisionError):
            return None
    return None


def _decimal(v: Fraction) -> str:
    """``v`` written as one exact decimal numeral (a value with a finite decimal expansion: the plants scale stated decimals)."""
    sign, v = ("-" if v < 0 else ""), abs(v)
    whole, rest = divmod(v.numerator, v.denominator)
    digits = ""
    while rest and len(digits) < 12:
        rest *= 10
        d, rest = divmod(rest, v.denominator)
        digits += str(d)
    if rest:
        raise H.HarnessError(f"{v} has no finite decimal of at most 12 places")
    return sign + str(whole) + ("." + digits if digits else "")


def _replace_number(problem: dict, where: str, old: str, new: str) -> int:
    """Replace every numeral ``old`` (an ``int`` or ``real`` node of that value) by ``new`` in the conclusion
    (``where`` "conclusion") or anywhere in the premises and the conclusion ("any"); the count replaced. Data only."""
    def walk(x: Any) -> int:
        n = 0
        if isinstance(x, dict):
            if x.get("op") in ("int", "real") and str(x.get("value")) == old:
                x["value"] = new
                x["op"] = "real" if "." in new or x.get("op") == "real" else "int"
                return 1
            for v in x.values():
                n += walk(v)
        elif isinstance(x, list):
            for v in x:
                n += walk(v)
        return n
    n = walk(problem.get("conclusion"))
    if where == "any":
        n += walk(problem.get("premises"))
    return n


def _plant_translation(dest: Path, stem: str, recorded_id: str, plant: str) -> str:
    """Re-key the copy's recorded translations (rule ``recorded-ids``), keep only the translation of ``recorded_id`` and
    give it the plant. Returns the delivered claim id it is served to."""
    mapping = H.rekey_translations(dest)
    moved = (mapping.get(stem) or {}).get("moved") or {}
    delivered = moved.get(recorded_id)
    if delivered is None:
        raise H.HarnessError(f"the recorded translation {recorded_id} of {stem} reaches no delivered claim on the merged parse")
    path = dest / "translations" / f"{stem}.json"
    tr = json.loads(path.read_text(encoding="utf-8"))
    fixture = tr["claims"][delivered]
    fixture = json.loads(fixture) if isinstance(fixture, str) else fixture
    fixture["problem"] = _plant(fixture["problem"], plant, delivered)
    tr["claims"] = {delivered: fixture}
    path.write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
    return delivered


# ============================================================================================ observation
def _norm(s: str) -> str:
    return H.arena().norm_text(s or "")


def _receipt_findings(rc: Any) -> list[dict]:
    """Every finding of a receipt (integrity and structural), as the arena compares them."""
    A = H.arena()
    return [A.finding_dict(f) for f in rc.findings] + [A.finding_dict(sf) for sf in rc.structural_findings]


_HEX_RE = __import__("re").compile(r"\b[0-9a-f]{16,}\b")
_TIME_RE = __import__("re").compile(r"\d{4}-\d\d-\d\d[T ][0-9:.]+(?:Z|[+-]\d\d:\d\d)?")


def _fkey(f: dict, with_message: bool = False) -> tuple:
    """A finding compared across the untampered and the planted copy: its code, severity and claims, and for an overseer
    finding its message too with generated ids and times folded (an OVS-TRN-005 names the number it found; a receipt
    finding's message changes with any plant: a word count, a claim's text)."""
    key = (f["code"], f["severity"], tuple(sorted(f["claim_ids"])))
    return key + ((_TIME_RE.sub("<time>", _HEX_RE.sub("<id>", _norm(f["message"]))),) if with_message else ())


@dataclass
class Observed:
    """What one replay of a (planted) copy shows: per delivered report transfer its receipt findings, the claims carrying
    the marker, the channel's OVS findings, and the blind dossier."""
    receipts: list[dict] = field(default_factory=list)
    ovs: list[dict] = field(default_factory=list)
    marker_claims: list[tuple[str, str]] = field(default_factory=list)   # (report id, claim id)
    dossier: Optional[dict] = None
    channel_state: Optional[str] = None
    translations: list[dict] = field(default_factory=list)
    review: Optional[dict] = None


def _observe(dest: Path, key: str, marker: str, *, pack: Any = None, agent: Optional[Callable[[dict], Any]] = None) -> Observed:
    from epinoic_logic.overseer.dossier import build_dossier
    aud = H.new_auditor(H.keyring_for("arena"))
    try:
        rr = H.replay_round(dest, aud, genuine_only=True)
        rec = rr.channel(key)
        audit = aud.audit(rec.uid)
        view = aud.view(rec.uid)
        ob = Observed(channel_state=audit.state)
        mk = _norm(marker)
        for t in view.transfers:
            if t.receipt is None or t.kind == "request":
                continue
            entry = {"kind": t.kind, "message_id": t.message_id, "report_id": t.report_id, "status": t.receipt.status.value, "findings": _receipt_findings(t.receipt),
                     "failed_checks": [(fc.constraint_id, fc.formal_status, fc.satisfied) for fc in t.receipt.formal_checks if fc.satisfied is not True]}
            if t.report is not None:
                # STEM repair 3: each finding also carries the texts of the claims it names, so a line a probe adds before them (which
                # shifts every later claim id) leaves the untampered findings matched to their own (_new)
                texts = {c.claim_id: _norm(c.claim_text) for c in t.report.claims}
                for f in entry["findings"]:
                    f["claim_texts"] = tuple(sorted(texts.get(c, c) for c in f.get("claim_ids") or ()))
            ob.receipts.append(entry)
            if t.report is not None and mk:
                for c in t.report.claims:
                    if mk in _norm(c.claim_text):
                        ob.marker_claims.append((t.report.report_id, c.claim_id))
            for o in t.receipt.outcomes:
                ob.translations.append({"report_id": o.report_id, "claim_id": o.claim_id, "translation_status": o.translation.status.value,
                                        "display_status": o.display_status.value, "diagnostics": [d[:200] for d in o.translation.diagnostics][:4]})
        ob.ovs = [{"code": f.code, "severity": f.severity, "claim_ids": list(f.claim_ids), "message_ids": list(f.message_ids), "message": f.message[:600]}
                  for f in audit.report.findings]
        from epinoic_logic.overseer.pack import installed_pack
        identity = pack.identity if pack is not None else installed_pack().identity
        ob.dossier = build_dossier(view, mode="blind", lens="general", agent_id="overseer-stem-probe-1", pack=identity)
        if agent is not None and pack is not None:
            ob.review = _review(rr.hub_for(key), key, pack, agent)
        return ob
    finally:
        aud.close()


def _review(hub: Any, key: str, pack: Any, reply: Callable[[dict], Any]) -> dict:
    """One scripted overseer agent built from the exported pack reviews the channel (blind): its accusation's outcome."""
    provider = H.ScriptedProvider(reply, name="harness-probe-overseer-stem-class-1")
    runner = H.build_runner(pack, provider, agent_id="overseer-stem-class-1", lens="translation_fidelity")
    ch = hub.channel_for(key)
    mids = [rc.message_id for rc in ch.receipts]
    before = {m: (c.state, tuple(c.codes)) for m in mids for c in [hub.clearance(key, m)]}
    review = hub.review(key, [runner], mode="blind")
    after = {m: (c.state, tuple(c.codes)) for m in mids for c in [hub.clearance(key, m)]}
    a = next((x for x in review.assessments if x.agent_id == "overseer-stem-class-1"), None)
    acc = a.accusations[0] if a is not None and a.valid and a.accusations else None
    return {"accused": acc is not None, "outcome": acc.outcome if acc is not None else None, "refuted_by": getattr(acc, "refuted_by", None) if acc is not None else None,
            "clearances_unchanged": before == after, "system_text_is_the_pack": bool(provider.calls) and all(
                c[0] == pack.system_text_for(H.dossier_of_user_text(c[1])) for c in provider.calls)}  # STEM repair 11: the dossier's composition


_KIND_RE = __import__("re").compile(r"kind `([a-z_]+)`")


def pack_kind(pack: Any, rule_words: Optional[str]) -> Optional[str]:
    """The kind the pack's own rule gives a fault (STEM repair 1): the first ``kind `...``` after ``rule_words`` in the text the
    pack configures an agent with, inside the same rule (before the next rule of the list). None when the pack states no such
    rule: the scripted agent then has no kind to accuse with, and the probe fails."""
    if pack is None or not rule_words:
        return None
    text = pack.system_text()
    k = text.find(rule_words)
    if k < 0:
        return None
    m = _KIND_RE.search(text, k)
    nxt = text.find("\n- **", k + len(rule_words))
    if m is None or (nxt >= 0 and m.start() > nxt):
        return None
    return m.group(1)


def _accuse_translation(kind: str, claim_id: str) -> Callable[[dict], Any]:
    """A scripted agent that accuses the translation of ``claim_id`` with ``kind`` (as the pack prescribes for the plant)."""
    def reply(d: dict):
        link = next((x for x in d["links"].get("translations") or [] if x.get("claim_id") == claim_id and x.get("translation_pointer")), None)
        if link is None:
            return H.verdict_dict(d)
        ev = [{"pointer": link["claim_pointer"] + "/claim_text"}, {"pointer": link["translation_pointer"] + "/problem"}]
        return H.verdict_dict(d, [H.accusation("a1", kind, ev, message_ids=[link["message_id"]], claim_ids=[claim_id], report_ids=[link["report_id"]],
                                               result_ids=[link["result_id"]] if link.get("result_id") else [],
                                               statement="The STEM translation of this claim does not encode what the claim states.")])
    return reply


def _tkey(f: dict) -> Optional[tuple]:
    """A receipt finding by its code, severity and the texts of the claims it names (None when they are not recorded)."""
    return (f["code"], f["severity"], tuple(f["claim_texts"])) if "claim_texts" in f else None


def _new(findings: list[dict], baseline: list[dict], *, with_message: bool = False) -> list[dict]:
    """The findings of the planted copy that the untampered copy does not have. A finding is matched first by the texts of the
    claims it names (STEM repair 3: a line added before a claim shifts its id, and the tester's control 'x-giv-bi-table-ctl' read
    the untampered CORE-QNT-001 of the shifted claim as new), then by its claim ids; each untampered finding matches once."""
    left = list(baseline)
    out = []
    pending: list[dict] = []
    for f in findings:
        kt = _tkey(f)
        hit = next((i for i, b in enumerate(left) if kt is not None and _tkey(b) == kt), None) if not with_message else None
        if hit is None:
            pending.append(f)
            continue
        del left[hit]
    for f in pending:
        k = _fkey(f, with_message)
        hit = next((i for i, b in enumerate(left) if _fkey(b, with_message) == k), None)
        if hit is None:
            out.append(f)
            continue
        del left[hit]
    return out


def _dossier_shows(d: Optional[dict], codes: tuple[str, ...], claim_ids: set[str], marker: str) -> dict:
    """Where a blind dossier shows the planted fault: the receipt finding of an expected code naming the planted claim (its
    pointer), the failed formal check naming it and its signed result with the problem it decided (the computed expression
    and the stated value), the structural finding, the marker in a delivered claim, and for a translation probe the
    translation the router received and its signed result."""
    out = {"finding": None, "failed_check": None, "claim": None, "result": None, "translation": None}
    if d is None:
        return out
    mk = _norm(marker)
    for link in (d.get("links") or {}).get("translations") or []:
        if link.get("claim_id") in claim_ids and out["translation"] is None:
            out["translation"] = link.get("translation_pointer")
            if link.get("result_id") and link["result_id"] in (d.get("results") or {}):
                out["result"] = f"/results/{link['result_id']}"
    for t in d["transfers"]:
        rc = t.get("receipt") or {}
        p = t.get("payload") or {}
        for j, c in enumerate(p.get("claims") or []):
            if isinstance(c, dict) and mk and mk in _norm(c.get("claim_text") or "") and out["claim"] is None:
                out["claim"] = f"{t['at']}/payload/claims/{j}"
        for field_ in ("findings", "structural_findings"):
            for i, f in enumerate(rc.get(field_) or []):
                if f.get("code") in codes and set(f.get("claim_ids") or []) & claim_ids and out["finding"] is None:
                    out["finding"] = f"{t['at']}/receipt/{field_}/{i}"
        for i, fc in enumerate(rc.get("formal_checks") or []):
            if fc.get("satisfied") is False and set(fc.get("claim_ids") or []) & claim_ids and out["failed_check"] is None:
                out["failed_check"] = f"{t['at']}/receipt/formal_checks/{i}"
                rid = fc.get("formal_result_id")
                if rid and rid in (d.get("results") or {}) and ((d["results"][rid] or {}).get("problem") is not None):
                    out["result"] = f"/results/{rid}"
    return out


def evaluate(probe: Probe, ob: Observed, base: Observed) -> dict:
    """The probe's outcome: named / caught_unnamed / missed (answer and translation probes), clean / not clean (controls)."""
    new_receipt: list[dict] = []
    planted_stems = {stem for stem, _old, _new in probe.edits} | ({probe.translation[0]} if probe.translation else set())
    for r in ob.receipts:
        # the planted answers' own receipts: the round's recorded synthesis cites the recorded parse, so a plant that adds a
        # statement changes its ledger findings whatever the plant is (not a finding about the planted fault)
        if r["kind"] not in ("response", "response_text") or not any(str(r["report_id"] or "").startswith(f"rep-{s}-") for s in planted_stems):
            continue
        b = next((x for x in base.receipts if x["kind"] == r["kind"] and x["report_id"] == r["report_id"]), {"findings": []})
        new_receipt += [dict(f, transfer=r["kind"], message_id=r["message_id"], report_id=r["report_id"]) for f in _new(r["findings"], b["findings"])]
    new_all = _new(ob.ovs, base.ovs, with_message=True)
    # rule divergences (OVS-DIV-*: an INT code the overseer's integrity report raises beside the receipts, such as the
    # time-dependent INT-HANDOFF-016) are true rule findings listed apart, as the contained run lists them: they say nothing
    # about the planted fault, so they never decide an outcome
    new_ovs = [f for f in new_all if not f["code"].startswith("OVS-DIV-")]
    rule_findings = [f for f in new_all if f["code"].startswith("OVS-DIV-")]
    planted = {cid for _rid, cid in ob.marker_claims}
    ovs_errors = [f for f in new_ovs if f["severity"] == "error"]
    shadow = [f for f in new_ovs if f["code"] in ("OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-008")]
    out: dict[str, Any] = {"probe_id": probe.probe_id, "class": probe.fault_class, "context": probe.context, "kind": probe.kind, "task": probe.key,
                           "description": probe.description, "expected": list(probe.expected), "planted_claims": sorted(planted),
                           "new_receipt_findings": [{k: f[k] for k in ("code", "severity", "claim_ids", "transfer")} | {"message": f["message"][:240]} for f in new_receipt],
                           "new_ovs_findings": [{k: f[k] for k in ("code", "severity", "claim_ids")} | {"message": f["message"][:240]} for f in new_ovs],
                           "new_rule_findings": [{k: f[k] for k in ("code", "severity", "claim_ids")} | {"message": f["message"][:240]} for f in rule_findings],
                           "channel_state": ob.channel_state, "translator_gap": probe.translator_gap}
    if probe.kind == "control":
        clean = not [f for f in new_receipt if f["severity"] in ("error", "warning")] and not ovs_errors
        if probe.translation is not None:  # a translation control: no new translation finding at all
            clean = clean and not [f for f in new_ovs if f["code"].startswith("OVS-TRN") and f["severity"] in ("error", "warning")]
            out["translations"] = ob.translations
        out.update(outcome="clean" if clean else "not_clean")
        return out
    if probe.kind == "translation":
        named = [f for f in new_ovs if f["code"] in probe.expected and (not f["claim_ids"] or set(f["claim_ids"]) & planted_claims_of(ob, probe))]
        trn_errors = [f for f in new_ovs if f["severity"] == "error" and f["code"].startswith("OVS-TRN")]
        out["translations"] = ob.translations
        if probe.expected:
            outcome = "named" if named else ("caught_unnamed" if [f for f in new_ovs if f["severity"] in ("error", "warning")] else "missed")
        else:  # a meaning fault no check compares: no check may name it as a fault of another kind, and an agent's accusation stays unresolved
            outcome = "agents_only" if not trn_errors else "caught_unnamed"
        if probe.forbidden and [f for f in new_ovs if f["code"] in probe.forbidden]:
            outcome = "forbidden_code"
        out.update(outcome=outcome, named_by=[f["code"] for f in named], forbidden_raised=sorted({f["code"] for f in new_ovs if f["code"] in probe.forbidden}))
    else:
        named = [f for f in new_receipt if f["code"] in probe.expected and set(f["claim_ids"]) & planted]
        agrees = not ovs_errors and not shadow
        if named and agrees:
            outcome = "named"
        elif named:
            outcome = "caught_unnamed"  # named by the receipt, but the overseer disagrees with it
        elif [f for f in new_receipt if f["severity"] in ("error", "warning")] or [f for f in new_ovs if f["severity"] in ("error", "warning")]:
            outcome = "caught_unnamed"
        else:
            outcome = "missed"
        # STEM repair 2: a code the probe forbids (a relation named unchecked must never also be failed) overrides any outcome
        raised = sorted({f["code"] for f in new_receipt if f["code"] in probe.forbidden})
        if raised:
            outcome = "forbidden_code"
        out.update(outcome=outcome, named_by=sorted({f["code"] for f in named}), overseer_agrees=agrees, overseer_errors=[f["code"] for f in ovs_errors],
                   shadow_disagreements=[f["code"] for f in shadow], forbidden_raised=raised)
    out["dossier"] = _dossier_shows(ob.dossier, probe.expected, planted_claims_of(ob, probe), probe.marker)
    if ob.review is not None:
        out["agent"] = {"kind": probe.agent_kind, "expected": probe.agent_outcome, **ob.review}
    elif probe.agent_kind:
        out["agent"] = {"kind": probe.agent_kind, "expected": probe.agent_outcome, "accused": False, "outcome": None}
    return out


def planted_claims_of(ob: Observed, probe: Probe) -> set[str]:
    if probe.kind == "translation":
        return {t["claim_id"] for t in ob.translations}
    return {cid for _rid, cid in ob.marker_claims}


# ============================================================================================ the run
def _base_key(probe: Probe) -> tuple:
    return (probe.stems, probe.key, probe.translation is not None)


def run_probes(out: Path, rounds_root: Path, *, pack: Any = None, probes: tuple[Probe, ...] = PROBES, work: Optional[Path] = None) -> dict:
    """Every probe on a one-task copy of r7, through an audited hub; each compared with the untampered copy of its task."""
    src = Path(rounds_root) / ROUND
    if not (src / "specialists").is_dir():
        return {"format": PROBES_FORMAT, "measured": False, "why": f"the recorded round {ROUND} is not present under {rounds_root}"}
    work = Path(work or (Path(out) / "work"))
    t0 = time.perf_counter()
    bases: dict[tuple, Observed] = {}
    results: list[dict] = []
    for probe in probes:
        started = time.perf_counter()
        try:
            bk = _base_key(probe)
            if bk not in bases:
                bdest = H.mini_round(src, work / f"base-{uuid.uuid4().hex[:8]}", probe.stems)
                if probe.translation is not None:
                    _plant_translation_none(bdest, *probe.translation[:2])
                bases[bk] = _observe(bdest, probe.key, "")
            dest = H.mini_round(src, work / f"{probe.probe_id}-{uuid.uuid4().hex[:6]}", probe.stems)
            agent = None
            marker = probe.marker
            derived = None
            if probe.translation is not None:
                stem, rid, plant = probe.translation
                delivered = _plant_translation(dest, stem, rid, plant)
                derived = pack_kind(pack, probe.agent_rule) if probe.agent_rule else probe.agent_kind
                agent = _accuse_translation(derived, delivered) if derived else None
            else:
                edit_answers(dest, probe.edits)
            ob = _observe(dest, probe.key, marker, pack=pack, agent=agent)
            res = evaluate(probe, ob, bases[bk])
            if probe.agent_rule:
                res["agent_kind_from_pack"] = derived
        except Exception as exc:
            res = {"probe_id": probe.probe_id, "class": probe.fault_class, "context": probe.context, "kind": probe.kind, "outcome": "error",
                   "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1500:], "translator_gap": probe.translator_gap}
        res["seconds"] = round(time.perf_counter() - started, 2)
        results.append(res)
    import shutil
    shutil.rmtree(work, ignore_errors=True)
    table = class_table(results)
    gate = probes_gate(results)
    doc = {"format": PROBES_FORMAT, "measured": True, "round": ROUND, "probes": results, "classes": table, "gate": gate,
           "tamper_cases_by_class": {k: list(v) for k, v in TAMPER_CASES.items()}, "wall_s": round(time.perf_counter() - t0, 2)}
    return doc


def _plant_translation_none(dest: Path, stem: str, recorded_id: str) -> None:
    """The untampered translation probe copy: the recorded translation of ``recorded_id`` re-keyed and served alone."""
    mapping = H.rekey_translations(dest)
    delivered = ((mapping.get(stem) or {}).get("moved") or {}).get(recorded_id)
    path = dest / "translations" / f"{stem}.json"
    tr = json.loads(path.read_text(encoding="utf-8"))
    tr["claims"] = {delivered: tr["claims"][delivered]} if delivered in tr["claims"] else {}
    path.write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")


def _agent_ok(r: dict) -> bool:
    a = r.get("agent")
    if a is None:
        return True
    if "agent_kind_from_pack" in r and r["agent_kind_from_pack"] != a.get("kind"):
        return False  # the pack does not give the fault the kind it must (its rule is missing or names another kind)
    return a.get("accused") and a.get("outcome") == a.get("expected") and a.get("clearances_unchanged") and a.get("system_text_is_the_pack")


def probe_ok(r: dict) -> bool:
    """Whether a probe met its expectation (a probe carrying a translator gap is reported, never counted)."""
    if r.get("outcome") == "error":
        return False
    if r["kind"] == "control":
        return r["outcome"] == "clean" and (r.get("context") != "translation" or bool((r.get("dossier") or {}).get("translation", True)))
    if r["kind"] == "translation":
        want = "named" if r.get("expected") else "agents_only"
        return (r["outcome"] == want or bool(r.get("translator_gap"))) and _agent_ok(r) and bool((r.get("dossier") or {}).get("translation"))
    if r.get("translator_gap"):
        return True
    return r["outcome"] == "named" and bool(r.get("dossier", {}).get("finding"))


def probes_gate(results: list[dict]) -> dict:
    counted = [r for r in results if not r.get("translator_gap") or r["kind"] == "control"]
    failing = [r["probe_id"] for r in results if not probe_ok(r)]
    covered = {c: sorted({r["context"] for r in results if r["class"] == c and r.get("outcome") in ("named", "agents_only", "clean")}) for c in STEM_CLASSES}
    return {"ok": not failing and all(covered[c] for c in STEM_CLASSES), "failing": failing, "probes": len(results), "counted": len(counted),
            "translator_gaps": sorted(r["probe_id"] for r in results if r.get("translator_gap") and r["kind"] != "control"),
            "classes_with_a_named_probe": covered}


def class_table(results: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for c, desc in STEM_CLASSES.items():
        rows = [r for r in results if r["class"] == c]
        out[c] = {"class": desc, "probes": {r["probe_id"]: r.get("outcome") for r in rows}, "tamper_cases": list(TAMPER_CASES.get(c, ())),
                  "translator_gaps": [r["probe_id"] for r in rows if r.get("translator_gap") and r["kind"] != "control"]}
    return out


def summary_md(doc: dict) -> str:
    if not doc.get("measured"):
        return f"# STEM fault-class probes\n\nNOT MEASURED: {doc.get('why')}\n"
    L = ["# STEM fault-class probes", "", f"Round {doc['round']} (one-task copies); {len(doc['probes'])} probes; wall {doc['wall_s']} s; gate "
         f"{'PASS' if doc['gate']['ok'] else 'FAIL'} {json.dumps({k: v for k, v in doc['gate'].items() if k not in ('ok', 'classes_with_a_named_probe')})}", "",
         "| probe | class | context | outcome | named by | overseer | dossier | agent | translator gap |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in doc["probes"]:
        dz = r.get("dossier") or {}
        ag = r.get("agent") or {}
        L.append(f"| {r['probe_id']} | {r['class']} | {r['context']} | {r.get('outcome')} | {', '.join(r.get('named_by') or []) or '-'} | "
                 f"{'agrees' if r.get('overseer_agrees') else ('-' if r['kind'] != 'answer' else 'DISAGREES ' + str(r.get('overseer_errors') or r.get('shadow_disagreements')))} | "
                 f"{dz.get('finding') or dz.get('failed_check') or dz.get('translation') or '-'} | {ag.get('outcome') or '-'} | {(r.get('translator_gap') or '')[:90]} |")
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="STEM fault-class probes: one planted fault per class on copies of recorded STEM transfers, through an audited hub.")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--rounds", required=True, type=Path)
    ap.add_argument("--pack", type=Path, default=None, help="an exported pack to build the scripted agents from (default: export the installed pack into --out/pack)")
    ap.add_argument("--probe", action="append", default=None, help="probe id (repeatable; default: every probe)")
    args = ap.parse_args(argv)
    out = H.check_output_dir(args.out, inputs=[args.rounds / n for n in H.ROUND_NAMES])
    pack = H.load_exported_pack(args.pack) if args.pack else H.export_and_load_pack(out / "pack")[0]
    probes = tuple(p for p in PROBES if not args.probe or p.probe_id in args.probe)
    doc = run_probes(out, args.rounds, pack=pack, probes=probes)
    H.write_json(out / "stem_probes.json", doc)
    (out / "stem_probes.md").write_text(summary_md(doc), encoding="utf-8")
    print(json.dumps({"gate": doc.get("gate"), "wall_s": doc.get("wall_s")}))
    return 0 if doc.get("gate", {}).get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
