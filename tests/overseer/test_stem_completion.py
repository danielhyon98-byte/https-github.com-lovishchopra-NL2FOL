"""The STEM completion of the overseer (``docs/OVERSEER_DESIGN.md`` section 31, decision 60).

The recorded STEM answers of round 7 that the repository keeps (``tests/channel/data/r7_material.json``: every answer,
identical to the recorded round's, with its synthesis, and the recorded fixtures of six tasks) are replayed through an
audited hub, as the contained harness replays them, to pin what the STEM completion closed:

* rule ``stem-structural`` (``checks.formal``, R2): the ST codes the STEM packs re-derive from the journaled report against
  the receipt's, as multisets of code, severity, claims and message. A dropped or moved ST warning is OVS-RCPT-004, one
  the packs do not give OVS-RCPT-005;
* rule ``check-statements`` (``checks.formal``, R2): a branch check's claims and ``detail``, and the message and claims of
  the finding naming its result, against the channel's statement of the check and its signed run (the engine's computed
  and stated values from the result's counterexample). Any other is OVS-RCPT-007;
* rule ``mark-annotation`` read with the parsers' own line rule (``checks.fidelity``): a mark annotation that closes a
  sentence inside a line is no part of the claim, so FID-001 no longer fails a STEM claim the parser delivered faithfully,
  and FID-006 no longer reads the annotation as a figure the parse lost;
* rule ``stem-exact-scale`` (``checks.translation``, TRN-005): in a STEM answer, rule ``percent-as-fraction`` is not
  applied, so a number the translator wrote 100 times or a hundredth of any number the answer states is named; and rule
  ``decimal-ratio``: a ratio with a decimal on either side (``0.036/12``) states its quotient and both sides, so a
  translation dividing by the stated 12 is not named;
* the tampering suite's STEM receipt cases T23a to T23s, each on a copy planted with one STEM fault, with the planted copy
  as its clean control and an agent built from the exported pack confirmed by the check, and the earlier cases on the
  STEM targets (prepared under the channel as shipped: a case's patch never reaches the copy's re-keying);
* the STEM fault-class probes (``scripts/overseer/stem_probes.py``) on the recorded answers;
* the pack's STEM statements beside the code they describe (the ST codes and their severities, the tolerance rule, what
  the translator is told about tolerances and enclosures).

Every recorded answer stays a read-only input: the rounds built here are copies of the repository's material.
"""
from __future__ import annotations

import json
import re
import sys
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import stem_probes as SP  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.overseer import OVS_CODES  # noqa: E402
from epinoic_logic.overseer.checks.fidelity import strip_mark_annotations  # noqa: E402
from epinoic_logic.overseer.checks.translation import STEM_BRANCH_KEYS, number_traced, stem_report, text_numbers  # noqa: E402
from epinoic_logic.overseer.pack import installed_pack_dir  # noqa: E402

R7_DATA = Path(__file__).resolve().parents[1] / "channel" / "data"
#: The STEM receipt cases, the codes each must raise naming the tampered transfer, and the STEM targets it runs on.
STEM_CODES = {
    "T23a": ["OVS-RCPT-004"], "T23b": ["OVS-RCPT-004"], "T23c": ["OVS-RCPT-004"], "T23d": ["OVS-FORM-001", "OVS-FORM-002"], "T23e": ["OVS-RCPT-007"],
    "T23f": ["OVS-RCPT-007"], "T23g": ["OVS-RCPT-007"], "T23h": ["OVS-RCPT-004"], "T23i": ["OVS-RES-007"], "T23j": ["OVS-RES-003"], "T23k": ["OVS-FORM-003"],
    "T23l": ["OVS-RCPT-005"], "T23m": ["OVS-RCPT-006"], "T23n": ["OVS-FORM-003"], "T23o": ["OVS-PEER-002"],
    "T23p": ["OVS-RCPT-007"],
    "T23q": ["OVS-RCPT-004"], "T23r": ["OVS-RCPT-004"], "T23s": ["OVS-RCPT-007"],
    "T23t": ["OVS-RCPT-004"], "T23u": ["OVS-RCPT-007"], "T23v": ["OVS-FORM-001", "OVS-FORM-002"],
    "T23w": ["OVS-RCPT-007"], "T23x": ["OVS-RCPT-004"], "T23y": ["OVS-FORM-001", "OVS-FORM-002"], "T23z": ["OVS-RCPT-007"],
    "T23aa": ["OVS-RCPT-004"], "T23ab": ["OVS-RCPT-007"], "T23ac": ["OVS-FORM-001", "OVS-FORM-002"], "T23ad": ["OVS-RCPT-007"],
    "T23ae": ["OVS-RCPT-004"], "T23af": ["OVS-RCPT-007"], "T23ag": ["OVS-RCPT-004"],
    "T23ah": ["OVS-RCPT-004"], "T23ai": ["OVS-RCPT-007"], "T23aj": ["OVS-FORM-001", "OVS-FORM-002"], "T23ak": ["OVS-RCPT-005"],
    "T23al": ["OVS-RCPT-007"], "T23am": ["OVS-RCPT-004"], "T23an": ["OVS-RCPT-004"],
    "T23ao": ["OVS-RCPT-007"], "T23ap": ["OVS-RCPT-004"], "T23aq": ["OVS-FORM-001", "OVS-FORM-002"], "T23ar": ["OVS-RCPT-005"],
    "T23as": ["OVS-RCPT-004"], "T23at": ["OVS-RCPT-007"],
    "T23au": ["OVS-RCPT-004"], "T23av": ["OVS-RCPT-007"], "T23aw": ["OVS-FORM-001", "OVS-FORM-002"], "T23ax": ["OVS-RCPT-004"],
    "T23ay": ["OVS-RCPT-007"], "T23az": ["OVS-RCPT-004"], "T23ba": ["OVS-RCPT-007"],
    "T23bb": ["OVS-RCPT-004"], "T23bc": ["OVS-RCPT-007"], "T23bd": ["OVS-FORM-001", "OVS-FORM-002"], "T23be": ["OVS-RCPT-004"],
    "T23bf": ["OVS-RCPT-007"], "T23bg": ["OVS-RCPT-004"], "T23bh": ["OVS-FORM-001", "OVS-FORM-002"], "T23bi": ["OVS-RCPT-007"],
    "T23bj": ["OVS-RCPT-007"], "T23bk": ["OVS-RCPT-004"], "T23bl": ["OVS-FORM-001", "OVS-FORM-002"], "T23bm": ["OVS-RCPT-007"],
    "T23bn": ["OVS-RCPT-004"], "T23bo": ["OVS-RCPT-007"], "T23bp": ["OVS-RCPT-004"],
    "T23bq": ["OVS-FORM-005"], "T23br": ["OVS-RCPT-007"], "T23bs": ["OVS-RCPT-004"], "T23bt": ["OVS-FORM-001", "OVS-FORM-002"],
}
STEM_TARGETS_OF = {
    "T23a": {"r7/ph-t13", "r7/maa-t13"}, "T23b": set(T.STEM_TARGETS), "T23c": {"r7/ph-t13"}, "T23d": set(T.STEM_TARGETS), "T23e": {"r7/ph-t13", "r7/maa-t13"},
    "T23f": {"r7/ph-t13", "r7/maa-t13"}, "T23g": {"r7/maa-t13", "r7/p7b"}, "T23h": {"r7/ph-t13"}, "T23i": {"r7/ph-t13", "r7/cs-t13"},
    "T23j": {"r7/ph-t13", "r7/ch-t13"}, "T23k": {"r7/ph-t13", "r7/p7b"}, "T23l": {"r7/ph-t13"}, "T23m": {"r7/maa-t13"}, "T23n": {"r7/ph-t13"}, "T23o": {"r7/p7b"},
    "T23p": {"r7/ph-t13"},
    "T23q": {"r7/ph-t13"}, "T23r": {"r7/p7b"}, "T23s": {"r7/p7b"},
    "T23t": {"r7/p7b", "r7/ch-t13"}, "T23u": {"r7/p7b"}, "T23v": {"r7/p7b"},
    "T23w": {"r7/cs-t13"}, "T23x": {"r7/p7b"}, "T23y": {"r7/p7b"}, "T23z": {"r7/p7b"},
    "T23aa": {"r7/ph-t13"}, "T23ab": {"r7/ph-t13"}, "T23ac": {"r7/ch-t13"}, "T23ad": {"r7/ph-t13"}, "T23ae": {"r7/ph-t13"},
    "T23af": {"r7/ph-t13"}, "T23ag": {"r7/ph-t13"},
    "T23ah": {"r7/ph-t13"}, "T23ai": {"r7/ph-t13"}, "T23aj": {"r7/cs-t13"}, "T23ak": {"r7/ch-t13"},
    "T23al": {"r7/p7b"}, "T23am": {"r7/p7b"}, "T23an": {"r7/ph-t13"},  # T23am on r7/p7b since STEM repair 11 (a derivative the branch does not check)
    "T23ao": {"r7/ph-t13"}, "T23ap": {"r7/p7b"}, "T23aq": {"r7/ph-t13"}, "T23ar": {"r7/ch-t13"}, "T23as": {"r7/ph-t13"}, "T23at": {"r7/ch-t13"},
    "T23au": {"r7/ph-t13"}, "T23av": {"r7/maa-t13"}, "T23aw": {"r7/ch-t13"}, "T23ax": {"r7/maa-t13"}, "T23ay": {"r7/p7b"}, "T23az": {"r7/ph-t13"},
    "T23ba": {"r7/maa-t13"},
    "T23bb": {"r7/ch-t13"}, "T23bc": {"r7/ph-t13"}, "T23bd": {"r7/p7b"}, "T23be": {"r7/cs-t13"}, "T23bf": {"r7/maa-t13"}, "T23bg": {"r7/p7b", "r7/ch-t13"},
    "T23bh": {"r7/maa-t13"}, "T23bi": {"r7/ph-t13"},
    "T23bj": {"r7/maa-t13"}, "T23bk": {"r7/maa-t13"}, "T23bl": {"r7/ph-t13"}, "T23bm": {"r7/ph-t13"}, "T23bn": {"r7/cs-t13"}, "T23bo": {"r7/maa-t13"},
    "T23bp": {"r7/maa-t13"},
    "T23bq": {"r7/maa-t13"}, "T23br": {"r7/maa-t13"}, "T23bs": {"r7/cs-t13"}, "T23bt": {"r7/ph-t13"},
}
#: Earlier cases run on the STEM targets beside T23 (the channel patched inside the replay, never inside the copy's
#: preparation; T22 on the recorded STEM translations the material keeps).
EARLIER_ON_STEM = ("T2b", "T2c", "T5d", "T7b", "T22")


def material_round(root: Path) -> Path:
    """A round directory ``root/r7`` built from the round-7 material the repository keeps: every recorded answer, its
    synthesis, and the recorded translation fixtures the material holds (a copy; the material is never written)."""
    material = json.loads((R7_DATA / "r7_material.json").read_text(encoding="utf-8"))
    translations = json.loads((R7_DATA / "r7_translations.json").read_text(encoding="utf-8"))
    rnd = Path(root) / "r7"
    for sub in ("specialists", "syntheses", "translations"):
        (rnd / sub).mkdir(parents=True)
    for tid, spec in material["specialists"].items():
        (rnd / "specialists" / f"{tid}.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    for tid, syn in material["syntheses"].items():
        (rnd / "syntheses" / f"{tid}.json").write_text(json.dumps(syn, ensure_ascii=False), encoding="utf-8")
    for tid, tr in translations.items():
        (rnd / "translations" / f"{tid}.json").write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
    return rnd


@pytest.fixture(scope="module")
def material(tmp_path_factory) -> Path:
    return material_round(tmp_path_factory.mktemp("r7-material") / "rounds")


@pytest.fixture(scope="module")
def stem_suite(tmp_path_factory, material):
    """The STEM receipt cases and the earlier cases named above on the five STEM targets, once per module."""
    out = tmp_path_factory.mktemp("tamper-stem")
    m = T.run_suite(out / "suite", rounds_root=material.parent, cases=sorted(STEM_CODES) + list(EARLIER_ON_STEM), targets=T.STEM_TARGETS)
    return m, out / "suite"


def _audit_task(rnd: Path, work: Path, stems: tuple[str, ...], key: str):
    dest = H.mini_round(rnd, work, stems)
    aud = H.new_auditor(H.keyring_for("arena"))
    try:
        rr = H.replay_round(dest, aud, genuine_only=True)
        rec = rr.channel(key)
        return aud.audit(rec.uid), aud.view(rec.uid)
    finally:
        aud.close()


# ============================================================================================ the rules on genuine STEM receipts
STEM_TASKS = ((("ph-t13",), "ph-t13"), (("maa-t13",), "maa-t13"), (("mai-t13",), "mai-t13"), (("bi-t13",), "bi-t13"), (("ch-t13",), "ch-t13"),
              (("ess-t13",), "ess-t13"), (("cs-t13",), "cs-t13"), (("ph-p7b", "maa-p7b"), "p7b"))
#: What each recorded STEM answer gives the two rules to compare: its formal checks with a signed run (the chemistry
#: answer states no relation the STEM checks plan) and the ST codes its receipt carries. STEM repair 1 (design section 32)
#: added checks that hold on four answers: ph-t13 five restatements (13 → 18: rules named-change and inline-restatement),
#: bi-t13 four and ess-t13 two values taken from their supplied tables (1 → 5, 1 → 3: rule table-data), and p7b the decay
#: line in counts min⁻¹ (24 → 25); every other count and every ST code set is unchanged. STEM repair 2 (design section 33)
#: added checks that hold on three: bi-t13 and ess-t13 two values each of their working set against the cells of the
#: table's named column (5 → 7, 3 → 5: rule table-operands), and p7b seven such values of the physics answer's corrected
#: rates and the two values the mathematics answer takes after quoting them (25 → 34: rules table-operands and
#: restated-binding); every other count and every ST code set is unchanged. STEM repair 3 (design section 34) added two checks
#: that hold on p7b: the time '32 h is 4 half-lives' as four times its T½ and the power (1/2)⁴ written after it (34 → 36: rule
#: half-lives); every other count and every ST code set is unchanged.
#: STEM repair 4: ess-t13 5 -> 11 (rule row-value: six values the answer gives at a site, each holding), p7b 36 -> 43 (rule
#: stated-uncertainty: the seven uncertainties ph-p7b writes with its corrected rates, each 2% of the measured value, holding).
#: STEM repair 10: maa-t13 9 -> 11 (rule definite-integral: the recorded evaluation bracket's two links, each holding; the two
#: ST-UNDEC-001 of the integral of v, which is no polynomial, stay), mai-t13 5 -> 8 (rule ellipsis-rounding: the restatement of
#: 4787.58… to the nearest euro and the computed value against 135.36…, each holding, and rule rounded-digits' place of the
#: restatement, holding), ess-t13 11 -> 13 (rule row-value: 'the most nymphs (34)' and 'only 9', each holding)
#: STEM repair 11: maa-t13 gains its derivative and part (b)'s step and roots (five holding checks; its ST-SCOPE-001 on t's rebinding is gone, t
#: being part (b)'s unknown), mai-t13 the two inequality-solution checks of its recorded bound (holding)
STEM_TASK_CONTENT = {"ph-t13": (18, set()), "maa-t13": (16, {"ST-UNDEC-001"}), "mai-t13": (10, {"ST-UNDEC-001"}), "bi-t13": (7, set()),
                     "ch-t13": (0, set()), "ess-t13": (13, set()), "cs-t13": (3, {"ST-SCOPE-001", "ST-UNDEC-001"}),
                     "p7b": (43, {"ST-SCOPE-001", "ST-UNDEC-001"})}


@pytest.mark.parametrize("stems, key", STEM_TASKS, ids=[k for _s, k in STEM_TASKS])
def test_every_recorded_stem_receipt_is_the_image_of_its_re_derivation(tmp_path, material, stems, key):
    """The STEM control of rules stem-structural and check-statements: on every recorded STEM answer the receipt's ST codes
    are the packs' and every formal check is stated as the channel states it, so neither rule raises anything; the rules
    are not vacuous here (the receipts carry formal checks with signed runs, and ST codes on the tasks that have them)."""
    audit, view = _audit_task(material, tmp_path / key, stems, key)
    named = [f for f in audit.report.findings if f.code in ("OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-007")]
    assert named == [], [(f.code, f.message[:200]) for f in named]
    assert not [f for f in audit.report.findings if f.severity == "error"], [(f.code, f.message[:160]) for f in audit.report.findings if f.severity == "error"]
    reports = [t for t in view.transfers if t.kind in ("response", "response_text") and t.receipt is not None]
    checks = sum(1 for t in reports for fc in t.receipt.formal_checks if fc.formal_result_id)
    codes = {sf.code for t in reports for sf in t.receipt.structural_findings if sf.code.startswith("ST-")}
    assert reports and (checks, codes) == STEM_TASK_CONTENT[key]


# ============================================================================================ the STEM receipt tamperings
@pytest.mark.timeout(1800)
def test_every_stem_receipt_case_ran_on_its_targets_and_passed(stem_suite):
    m, _out = stem_suite
    got = {(e["case"], e["target"]): e for e in m["faults"]}
    for case, targets in STEM_TARGETS_OF.items():
        for target in T.STEM_TARGETS:
            e = got[(case, target)]
            if target not in targets:
                assert e["skipped"], (case, target)
                continue
            assert not e["skipped"] and not e["error"], (case, target, e["skipped"], e["error"])
            assert e["passed"] and e["detected"], (case, target, e["naming"], [c for c in e["checks"] if not c["ok"]])
    assert m["controls"] == {t: [] for t in T.STEM_TARGETS}
    assert all(g["ok"] for g in m["gates"].values()), m["gates"]


@pytest.mark.parametrize("case", sorted(STEM_CODES))
def test_each_stem_receipt_case_raises_exactly_its_codes_naming_the_tampered_transfer(stem_suite, case):
    """The codes at the severity of the code table, naming the tampered transfer; an error leaves the transfer
    AUDIT_FAILED, a warning never AUDIT_PASSED; the planted copy without the tampering is clean; a probe agent built from
    the exported pack that accuses the tampering with the fault's kind is CONFIRMED by the check (RCPT-005 alone confirms
    no kind, so T23l, T23ak and T23ar have no agent)."""
    m, out = stem_suite
    for e in [x for x in m["faults"] if x["case"] == case and not x["skipped"]]:
        assert e["expected_codes"] == STEM_CODES[case]
        assert all(e["naming"][c] for c in STEM_CODES[case]), (e["fault_id"], e["naming"])
        rec = H.load_record(out / e["record"])
        for code in STEM_CODES[case]:
            found = [f for f in rec.audit.report.findings if f.code == code]
            assert found and all(f.severity == OVS_CODES[code][0] for f in found), (e["fault_id"], code)
        if any(OVS_CODES[c][0] == "error" for c in STEM_CODES[case]):
            assert e["transfer_state"] == "AUDIT_FAILED", e["fault_id"]
        assert e["transfer_state"] != "AUDIT_PASSED"
        checks = {c["check"]: c["ok"] for c in e["checks"]}
        planted = [k for k in checks if k.startswith("the planted copy without the tampering")]
        assert all(checks[k] for k in planted)
        if T.STEM_TARGETS and case in ("T23b", "T23d", "T23k", "T23ah", "T23ai", "T23aj", "T23ak", "T23al", "T23am", "T23an", "T23ao", "T23ap", "T23aq",
                                       "T23ar", "T23as", "T23at", "T23au", "T23av", "T23aw", "T23ax", "T23ay", "T23az", "T23ba", "T23bb", "T23bc",
                                       "T23bd", "T23be", "T23bf", "T23bg", "T23bh", "T23bi", "T23bj", "T23bk", "T23bl", "T23bm", "T23bn",
                                       "T23bo", "T23bp", "T23bq", "T23br", "T23bs", "T23bt"):
            assert planted, e["fault_id"]  # every planted case has its planted control
        agent = [k for k in checks if k.startswith("an agent built from the exported pack")]
        assert (agent == []) == (case in ("T23l", "T23ak", "T23ar")) and all(checks[k] for k in agent), e["fault_id"]


def test_earlier_cases_run_on_the_stem_targets_and_their_patches_never_reach_the_copy_s_re_keying(stem_suite):
    """A STEM target's copy is re-keyed by parsing its recorded answers through a hub of its own; the cases' patches of the
    channel apply to the replay only (``tamper._pristine_channel``), so T2b, T2c, T5d and T7b name the target channel's own
    transfers on every STEM target they apply to (T5d on every one whose recorded answer has a branch formal check: all
    but the chemistry answer, which states no relation the STEM checks plan, so T5d has nothing to suppress there), and T22
    tampers with the recorded STEM translations re-keyed to the merged claims."""
    m, _out = stem_suite
    ran = [e for e in m["faults"] if e["group"] in EARLIER_ON_STEM and not e["skipped"]]
    assert ran and all(e["passed"] for e in ran), [(e["fault_id"], [c for c in e["checks"] if not c["ok"]], e["error"]) for e in ran if not e["passed"]]
    with_checks = {t for t in T.STEM_TARGETS if STEM_TASK_CONTENT[t.split("/", 1)[1]][0]}
    assert with_checks == set(T.STEM_TARGETS) - {"r7/ch-t13"}
    assert {e["target"] for e in ran if e["group"] == "T5d"} == with_checks
    assert [e["skipped"] for e in m["faults"] if e["group"] == "T5d" and e["target"] not in with_checks] == \
        ["no report of this task has a branch pack formal check to suppress"]
    assert [e["fault_id"] for e in ran if e["group"] == "T7b"] == ["T7b@r7/p7b"]
    assert any(e["case"].startswith("T22") and e["target"] == "r7/cs-t13" for e in ran)


def test_the_planted_faults_of_the_stem_cases_are_the_probe_module_s(stem_suite):
    """Every class the probe module maps to a T23 case plants, on some STEM target, a fault of that class (the cases take
    their plants from ``stem_probes`` by probe id), and every T23 case is mapped to a class."""
    m, _out = stem_suite
    mapped = {c for cases in SP.TAMPER_CASES.values() for c in cases if c.startswith("T23")}
    assert mapped == set(STEM_CODES)
    for cls, cases in SP.TAMPER_CASES.items():
        assert any(e["case"] in cases and e["passed"] for e in m["faults"] if not e["skipped"]), cls


# ============================================================================================ rule mark-annotation
def test_mark_annotations_are_read_with_the_parsers_own_line_rule():
    """An annotation that closes a sentence inside a line is left out as the parsers leave it out (the claim
    "... 100% Mean uptake = ..." is the response's line read without "[1]"); the forms the rule read before are read the
    same; an annotation inside a sentence stays (the parsers keep it), and text without annotations is unchanged."""
    line = "an increase of 100% [1] Mean uptake = (18 + 27 + 40)/3 = 28.3"
    assert strip_mark_annotations(line) == "an increase of 100% Mean uptake = (18 + 27 + 40)/3 = 28.3"
    assert strip_mark_annotations("only 9 [1].") == "only 9."
    assert strip_mark_annotations("3t(2 − t) = 0  M1\nt = 0 or t = 2  A1") == "3t(2 − t) = 0\nt = 0 or t = 2"
    assert strip_mark_annotations("$= 4787.58\\ldots$ (A1)") == "$= 4787.58\\ldots$"
    assert strip_mark_annotations("the [1] grade of the scale is used") == "the [1] grade of the scale is used"
    text = "The Factory Act of 1833 banned the employment of children under nine."
    assert strip_mark_annotations(text) == text


def test_a_stem_claim_cut_at_a_sentence_closing_annotation_is_faithful_and_a_changed_one_is_not(tmp_path, material):
    """End to end on the recorded biology answer: a line whose mark annotation closes its first sentence, the parser
    delivering the claim without it, gives no FID-001 (the receipt names the planted wrong mean, INT-SUBJ-001, and the
    overseer agrees); the same claim changed after delivery is still FID-001 (the control: the rule reads annotations,
    nothing else)."""
    p = SP.probe("maths-statistics-inline")
    for probe in (p, SP.probe("maths-statistics-inline-control")):
        dest = H.mini_round(material, tmp_path / probe.probe_id, probe.stems)
        SP.edit_answers(dest, probe.edits)
        aud = H.new_auditor(H.keyring_for("arena"))
        try:
            rr = H.replay_round(dest, aud, genuine_only=True)
            rec = rr.channel(probe.key)
            audit = aud.audit(rec.uid)
            assert not [f for f in audit.report.findings if f.code == "OVS-FID-001"], probe.probe_id
            if probe.kind == "answer":
                rc = next(t.receipt for t in aud.view(rec.uid).transfers if t.kind == "response_text")
                assert any(f.code == "INT-SUBJ-001" for f in rc.findings)
        finally:
            aud.close()
    from epinoic_logic.overseer.checks.fidelity import claim_occurs
    from epinoic_logic.overseer.checks import normalise, plain_form
    response = "(a) Percentage change = 100%, an increase of 100% [1] Mean uptake = (18 + 27 + 40)/3 = 28.3"
    unmarked = strip_mark_annotations(response)
    assert claim_occurs(strip_mark_annotations("an increase of 100% Mean uptake = (18 + 27 + 40)/3 = 28.3"), normalise(unmarked), plain_response=plain_form(unmarked),
                        raw_response=unmarked)
    assert not claim_occurs(strip_mark_annotations("an increase of 100% Mean uptake = (18 + 27 + 40)/3 = 30"), normalise(unmarked),
                            plain_response=plain_form(unmarked), raw_response=unmarked)


def test_the_recorded_biology_answer_s_sentence_closing_annotations_are_no_parse_loss(tmp_path, material):
    """The recorded biology answer closes eight sentences with "[1]", four of them inside a line ("... at 35 °C. [1] The
    rise is ..."), which its parser leaves out of the claims. Read with the parsers' own line rule, none is a figure the
    parse lost: the genuine transfer has no OVS-FID-006 (the fifth repair's reading warned "figures ['1', '1', '1', '1']"
    on it and on its seven fault variants). FID-006's positive cases, content a parse really lost, stay pinned in
    ``test_audit_fidelity.py`` and ``test_review1_content_checks.py``."""
    audit, view = _audit_task(material, tmp_path / "bi-t13", ("bi-t13",), "bi-t13")
    assert not [f for f in audit.report.findings if f.code == "OVS-FID-006"], [f.message[:200] for f in audit.report.findings if f.code == "OVS-FID-006"]
    raw = next(t.report.original_response for t in view.transfers if t.kind == "response_text" and t.report is not None)
    assert raw.count("[1]") == 8 and len(re.findall(r"\. \[1\] [A-Z]", raw)) == 4 and "[1]" not in strip_mark_annotations(raw)


# ============================================================================================ rule stem-exact-scale
def test_percent_as_fraction_is_not_read_in_a_stem_answer():
    """0.03 is 100 times nothing a STEM answer states but its "3 marks": traced only by rule percent-as-fraction, which a
    STEM answer does not read; a percentage the answer writes with its sign is still read as both numbers, and the rule
    is unchanged for every other answer."""
    known = text_numbers("Part (a) — find — 3 marks. The rate per period is 0.036/12 = 0.003, from a nominal rate of 3.6%.")
    assert number_traced(Fraction("0.03"), known) and not number_traced(Fraction("0.03"), known, exact_scale=True)
    for stated in ("0.036", "3.6", "0.003", "12"):
        assert number_traced(Fraction(stated), known, exact_scale=True), stated
    quarter = text_numbers("a quarter of the workers")  # rule fraction-words: 1/4, its numerator and its denominator
    assert number_traced(Fraction(25), quarter) and not number_traced(Fraction(25), quarter, exact_scale=True)


def test_a_decimal_ratio_states_its_quotient_and_both_sides():
    """Rule decimal-ratio: ``0.036/12`` states 0.036, 12 and 0.003 (the digit rule alone read only 0.036, so a translation
    dividing by the stated 12 was named for it); a decimal denominator is read whole, never in part; a ratio of whole
    numbers and a date are read as before (the rule adds nothing to them)."""
    for text, values in (("0.036/12", ("0.036", "12", "0.003")), ("0.036 / 12 = 0.003", ("0.036", "12", "0.003")), ("9.81/2", ("9.81", "2", "4.905")),
                         ("6/2.5", ("6", "2.5", "2.4")), ("0.5/12.5", ("0.5", "12.5", "0.04"))):
        known = text_numbers(text)
        assert all(number_traced(Fraction(v), known, exact_scale=True) for v in values), text
    assert not number_traced(Fraction(12), text_numbers("0.5/12.5"), exact_scale=True)
    assert not number_traced(Fraction(12), text_numbers("0.036 per month"), exact_scale=True)
    assert text_numbers("3/4") == {Fraction(3), Fraction(4), Fraction(3, 4)}
    assert text_numbers("12/03/2024") == {Fraction(12), Fraction(3), Fraction(4), Fraction(2024)}


@pytest.mark.parametrize("subject, stem", [("Physics", True), ("Mathematics: Analysis and Approaches", True), ("Computer Science", True), ("Chemistry", True),
                                            ("History", False), ("English A: Literature", False), ("Economics", False)])
def test_a_stem_report_is_one_a_stem_branch_reads(subject, stem):
    plan = SimpleNamespace(agent_subjects={"a1": subject}, subject=subject)
    ctx = SimpleNamespace(view=SimpleNamespace(plan_at=lambda seq: plan), registry=None)
    t = SimpleNamespace(report=SimpleNamespace(agent_id="a1", subject=subject), seq=1)
    assert stem_report(ctx, t) is stem
    assert STEM_BRANCH_KEYS == {"sciences", "mathematics", "computer_science"}


def _rate_fixture(report, claim, value: str) -> dict:
    return {"problem": {"ir_version": "1.0", "problem_id": "mai-rate", "request_id": report.request_id, "claim_id": claim.claim_id, "query": "entailment",
                        "symbols": [{"name": "m_r", "sort": "Real", "meaning": "the monthly rate"}],
                        "premises": [{"id": "P1", "expr": {"op": "eq", "left": {"op": "var", "name": "m_r"},
                                                           "right": {"op": "div", "left": {"op": "real", "value": "0.036"}, "right": {"op": "real", "value": "12"}}},
                                      "label": "the rate per period is 0.036/12", "grounding": {"kind": "specialist_inference"}}],
                        "conclusion": {"id": "C", "expr": {"op": "eq", "left": {"op": "var", "name": "m_r"}, "right": {"op": "real", "value": value}},
                                       "label": "the rate per period"}},
            "interpretation": {"reading": "the monthly rate as the claim states it", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
            "unsupported_reason": None}


def test_trn005_names_a_stem_translation_number_the_answer_states_only_at_another_scale(tmp_path, material):
    """End to end on the recorded Mathematics AI answer: its monthly rate "0.036/12 = 0.003" translated with 0.03 is
    OVS-TRN-005 (before this rule the heading's "3 marks" traced it, and an agent's true translation_ungrounded accusation
    was refuted); translated with 0.003 nothing is named."""
    base = H.mini_round(material, tmp_path / "base", ["mai-t13"])
    items = H.arena().load_items(base / "specialists")
    report, _rc = H.deliver_recorded_answer(items, items[0])
    claim = next(c for c in report.claims if "0.036/12 = 0.003" in c.claim_text)
    for value, named in (("0.003", False), ("0.03", True)):
        dest = H.mini_round(material, tmp_path / f"rate-{value}", ["mai-t13"])
        (dest / "translations").mkdir(exist_ok=True)
        (dest / "translations" / "mai-t13.json").write_text(json.dumps({"report_id": report.report_id, "claims": {claim.claim_id: _rate_fixture(report, claim, value)}}),
                                                            encoding="utf-8")
        aud = H.new_auditor(H.keyring_for("arena"))
        try:
            rr = H.replay_round(dest, aud, genuine_only=True)
            rec = rr.channel("mai-t13")
            audit = aud.audit(rec.uid)
            outcomes = [o for t in aud.view(rec.uid).transfers if t.receipt is not None for o in t.receipt.outcomes if o.claim_id == claim.claim_id]
            assert outcomes and outcomes[0].translation.problem is not None, value
            trn5 = [f for f in audit.report.findings if f.code == "OVS-TRN-005" and claim.claim_id in f.claim_ids]
            assert bool(trn5) is named, (value, [f.message[:200] for f in trn5])
            if named:
                assert "uses the number 3/100" in trn5[0].message
        finally:
            aud.close()


# ============================================================================================ the STEM fault-class probes
@pytest.mark.timeout(1200)
def test_the_stem_probes_name_every_class_on_the_recorded_answers(tmp_path, material):
    """The probes' receipt context on the recorded answers (their translation context needs recorded fixtures the
    repository does not keep): every counted fault is named by the receipt with the overseer agreeing and the dossier
    showing it, every control is clean, every class has a named probe, and each translator gap is reported with its
    reason, never counted."""
    doc = SP.run_probes(tmp_path / "probes", material.parent, probes=SP.ANSWER_PROBES)
    assert doc["measured"] and doc["gate"]["ok"], doc["gate"]
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for p in SP.ANSWER_PROBES:
        r = rows[p.probe_id]
        if p.kind == "control":
            assert r["outcome"] == "clean", (p.probe_id, r.get("new_ovs_findings"), r.get("new_receipt_findings"))
        elif p.translator_gap:
            assert r["probe_id"] in doc["gate"]["translator_gaps"]
        else:
            assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"], (p.probe_id, r)
    assert rows["maths-statistics-inline"]["outcome"] == "named" and rows["maths-statistics-inline-control"]["outcome"] == "clean"
    assert set(doc["gate"]["classes_with_a_named_probe"]) == set(SP.STEM_CLASSES) and all(doc["gate"]["classes_with_a_named_probe"].values())


def test_the_contained_run_gates_the_stem_probes_when_r7_is_run():
    import run_contained as RC
    ok = {"measured": True, "gate": {"ok": True, "failing": [], "probes": 3, "counted": 3, "translator_gaps": [], "classes_with_a_named_probe": {}}}
    bad = {"measured": True, "gate": {"ok": False, "failing": ["x"], "probes": 3, "counted": 3, "translator_gaps": [], "classes_with_a_named_probe": {}}}
    missing = {"measured": False, "why": "the recorded round r7 is not present"}
    assert RC.gates({"stem_probes": ok})["stem_fault_classes_named"]["ok"]
    assert not RC.gates({"stem_probes": bad})["stem_fault_classes_named"]["ok"]
    g = RC.gates({"stem_probes": missing})["stem_fault_classes_named"]
    assert not g["ok"] and "NOT MEASURED" in g["state"]
    assert "stem_fault_classes_named" not in RC.gates({})  # a run that does not ask for r7 has no STEM gate
    assert "r7" in H.ROUND_NAMES  # an output directory inside the recorded r7 is refused like any other round's


# ============================================================================================ the pack beside the code
def _pack_text(name: str) -> str:
    return (installed_pack_dir("1.3") / name).read_text(encoding="utf-8")


def test_the_pack_lists_every_st_code_with_the_severity_the_stem_package_gives_it():
    """Dossier guide D32's table is the STEM front end's own table of codes and severities (``stem.relations.ST_SEVERITY``),
    and every ST code the STEM package's source names is in it."""
    import re
    from epinoic_logic.stem.relations import ST_SEVERITY
    d32 = _pack_text("02-dossier.md").split("**D32 ", 1)[1].split("\n## ", 1)[0]
    rows = dict(re.findall(r"^\s*\| (ST-[A-Z]+-\d{3}) \| (warning|info|error) \|", d32, flags=re.MULTILINE))
    assert rows == ST_SEVERITY
    src = Path(__file__).resolve().parents[2] / "src" / "epinoic_logic"
    named = {c for p in [*(src / "stem").glob("*.py"), src / "branches" / "stem_pack.py"] for c in re.findall(r"ST-[A-Z]+-\d{3}", p.read_text(encoding="utf-8"))}
    assert named <= set(rows), sorted(named - set(rows))


def _decided(text: str, request: str = None, profile: str = "physics", data: tuple = ()) -> list[tuple[str, str, str]]:
    """Every STEM check the front end plans for ``text``, decided by the engine: (kind, status, description)."""
    from epinoic_logic.engine import SolverConfig
    from epinoic_logic.engine.policies import policy_config, policy_limits
    from epinoic_logic.engine.runner import verify
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.stem import build_document, clear_document_cache
    from epinoic_logic.stem.checks import build_checks
    clear_document_cache()
    cfg = SolverConfig(timeout_ms=8000, memory_max_mb=None)
    plan = build_checks(build_document(text, request, profile, **({"data": data} if data else {})), report_id="r", request_id="q")
    return [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, cfg), limits=policy_limits(pc.policy)).status.value,
             pc.description) for pc in plan.checks]


def test_the_pack_states_the_stem_tolerance_rule_as_the_checks_apply_it():
    """D31's tolerance rule and the short form every check's ``detail`` carries, each statement executed against the code that
    applies it (STEM repair 1: the short form said "h is half a unit in S's last digit" and "0 for conversions", and D31 said
    "1/20 for '≈'" beside "0 for unit conversions", while the checks applied R1's trailing-zero rule, R2's precedence of '≈'
    over every check kind, and the half-width of a stated value set against another)."""
    from epinoic_logic.stem.numbers import scan_number
    from epinoic_logic.stem.tolerance import SHORT_RULE, TAU_APPROX, TAU_EQUAL, half_width, tau_for
    d31 = _pack_text("02-dossier.md").split("**D31 ", 1)[1].split("\n- **D32", 1)[0]
    assert TAU_EQUAL == Fraction(1, 100) and TAU_APPROX == Fraction(1, 20)
    for words in ("|C − S| ≤ h + τ·|C|", "half a unit in S's last written digit", "5.0 gives 0.05 and 1.20 × 10³ gives 5",
                  "count only up to the smallest number of significant figures among the expression's measured operands",
                  "1200 against two-figure operands gives 50", "110 against the operands 80 and 40 gives 5, not 0.5",
                  "none of its trailing zeros count: in a conversion or a restatement, 600 gives 50", "h adds C's own half-width",
                  "|w − b| ≤ h(b) + h(w)", "|S − S′| ≤ h(S) + h(S′)", "1/2 for the nearest whole number and for 60 to two significant figures, 5 for 60 to one",
                  "τ is 1/20 for a relation written \"≈\", \"≃\" or \"~\"", "whatever the check: a conversion written \"≈\" gets 1/20 too",
                  "τ is 1/100 for \"=\" in written arithmetic", "and 0 for unit conversions, comparisons, substitutions, restated results, Given values, roots",
                  "every operand and S exact: then h is 0 too", "only h(S) bands it", "10⁻¹⁵·max(1, |value|)", "Form E (entailment, expected ENTAILED)",
                  "Form S (satisfiability, expected SATISFIABLE)", "(engine counterexample: c = "):
        assert words in d31, words
    for words in ("|C − S| ≤ h + τ·|C|", "half a unit in S's last digit (integer trailing zeros only to the operands' s.f.)", "plus C's own h if C is a stated value",
                  "1/20 for ≈/about, any check", "1/100 for = in arithmetic", "0 for conversions, comparisons, substitutions, restatements, exact work"):
        assert words in SHORT_RULE, words
    # h (R1), as both state it
    def num(s):
        return scan_number(s, 0).number
    assert half_width(num("5.0")) == Fraction(1, 20) and half_width(num("1.20 × 10³")) == 5
    assert half_width(num("1200"), min_sig_figs=2) == 50 and half_width(num("110"), min_sig_figs=1) == 5 and half_width(num("600")) == 50
    assert half_width(num("1200"), min_sig_figs=4) == Fraction(1, 2)
    # τ (R2): 1/20 for '≈' whatever the check but a restated result (R8: STEM repair 12, the approximation word before a restated value
    # names its rounding, as the restatement check has always applied: executed below); else 1/100 for '=' in arithmetic and 0 for every
    # other kind and for exact work
    for kind in ("eq", "cnv", "cmp", "res", "giv", "sub-match", "sol-root", "tgt"):
        assert tau_for(kind, approx=True, exact_mode=False) == (0 if kind == "res" else TAU_APPROX), kind
        assert tau_for(kind, approx=False, exact_mode=False) == (TAU_EQUAL if kind == "eq" else 0), kind
        assert tau_for(kind, approx=False, exact_mode=True) == 0, kind
    assert "A restated result is the one exception" in d31
    chain60, chain64 = "D = (9.6 − 3.8) ÷ 9.6 × 100 = 60.4%\n", "D = (9.6 − 3.42) ÷ 9.6 × 100 = 64.4%\n"
    cases = [
        ("x = (80 − 40) ÷ 40 × 100 ≈ 110%", "eq", "ENTAILED"),  # D31's worked example: h 5, τ 1/20, a band of 10
        ("x = (80 − 40) ÷ 40 × 100 = 110%", "eq", "COUNTEREXAMPLE"),  # '=' with every operand exact: exact mode, h = τ = 0
        ("n = 7 × 8 = 57", "eq", "COUNTEREXAMPLE"),  # exact mode (h 1/2 and τ 1/100 would have reached 57)
        ("a = 2.5 × 4.8 = 12.1", "eq", "ENTAILED"), ("a = 2.5 × 4.8 = 12.2", "eq", "COUNTEREXAMPLE"),  # h 0.05 + 12/100
        ("t = 2.0 h ≈ 7500 s", "cnv", "ENTAILED"), ("t = 2.0 h = 7500 s", "cnv", "COUNTEREXAMPLE"),  # a conversion written '≈' gets 1/20 too
        ("R = 2.4 Ω = 0.0025 kΩ", "cnv", "ENTAILED"), ("R = 2.4 Ω = 0.0026 kΩ", "cnv", "COUNTEREXAMPLE"),  # h(S) + h(C), τ 0
        ("R = 2.4 Ω\nI = V/R = 12 V / 2.45 Ω = 4.9 A", "sub", "ENTAILED"), ("R = 2.4 Ω\nI = V/R = 12 V / 2.46 Ω = 4.9 A", "sub", "COUNTEREXAMPLE"),
        (chain60 + "Therefore the decrease is 60.5%.", "res", "ENTAILED"), (chain60 + "Therefore the decrease is 60.6%.", "res", "COUNTEREXAMPLE"),
        (chain64 + "Therefore the decrease is 60%.", "res", "ENTAILED"),  # none of 60's zeros count: h 5
        (chain64 + "To 1 s.f., the decrease is 60%.", "res", "ENTAILED"),
        (chain64 + "To 2 s.f., the decrease is 60%.", "res", "COUNTEREXAMPLE"), (chain64 + "To the nearest whole number, the decrease is 60%.", "res", "COUNTEREXAMPLE"),
        (chain60 + "To the nearest whole number, the decrease is 60%.", "res", "ENTAILED"),
        # R8 after an approximation word: no τ (60.6 is outside h(60.6) + h(60.4) = 0.1, and would be inside 0.1 + 60.4/20)
        (chain60 + "Therefore the decrease is about 60.6%.", "res", "COUNTEREXAMPLE"), (chain60 + "Therefore the decrease is about 60%.", "res", "ENTAILED"),
    ]
    for text, kind, status in cases:
        got = [(k, st) for k, st, _d in _decided(text) if k == kind]
        assert got == [(kind, status)], (text, got)
        assert all(f"[{SHORT_RULE}]" in d for _k, _st, d in _decided(text)), text  # the rule each check's detail carries
    # STEM repair 11 (rule exact-rounding): a stated value of two or more figures that closes rational written arithmetic has half a unit in
    # its last written digit (57 for 56 still fails: a whole computed value is stated exactly); a single figure keeps h = 0 ('7/3 = 2' fails)
    detail = _decided("n = 7 × 8 = 57")[0][2]
    assert ("exact mode: every operand and the stated value are exact (τ = 0); the stated value, of two or more significant figures, closes "
            "rational written arithmetic, so h is half a unit in its last written digit") in detail and "(rule exact-rounding)" in detail, detail
    assert [(k, st) for k, st, _d in _decided("n = 7/3 = 2")] == [("eq", "COUNTEREXAMPLE")]
    assert "exact mode: every operand and the stated value are exact (τ = 0, h = 0)" in _decided("n = 7/3 = 2")[0][2]
    assert "τ = 1/100" in _decided(chain64)[0][2]
    # a value taken from a supplied table: the table's cells as written, only h(S) bands it (23 is outside 22 ± 1/2)
    material = json.loads((R7_DATA / "r7_material.json").read_text(encoding="utf-8"))["specialists"]["bi-t13"]
    data = tuple(t["text"] for t in material["supplied_texts"])
    for stated, statuses in (("22", ["ENTAILED"] * 4), ("23", ["COUNTEREXAMPLE"] + ["ENTAILED"] * 3)):
        text = material["response_text"].replace("an increase of 22 mm³", f"an increase of {stated} mm³")
        assert text != material["response_text"] or stated == "22"
        decided = [(st, d) for k, st, d in _decided(text, material["question"], "biology", data) if k == "giv"]
        assert sorted(st for st, d in decided if "rule table-operands" not in d) == statuses, stated
        # STEM repair 2: part (a)'s two operands are also set against the rows its question names (rule table-operands), and hold
        assert [st for st, d in decided if "rule table-operands" in d] == ["ENTAILED"] * 2, stated


def test_what_the_pack_says_the_translator_is_told_about_tolerances_and_enclosures_is_the_translator_s_profile():
    """D30 quotes the subject descriptions the translator is given (``translate.subjects``): the checks decide under the
    STEM tolerance rule, the translator's formalisations do not check units, significant-figure policy is never
    established, and for Mathematics: Analysis and Approaches neither are transcendental identities beyond 10^-15
    enclosures. The encoding guidance itself says nothing of tolerances or enclosures."""
    from epinoic_logic.translate.subjects import PROFILES, STEM_ENCODING_GUIDANCE, prompt_profile_text
    d30 = _pack_text("02-dossier.md").split("**D30 ", 1)[1].split("\n- **D31", 1)[0]
    physics, maa = prompt_profile_text(PROFILES["physics"]), prompt_profile_text(PROFILES["mathematics_aa"])
    for quote in ("under the STEM tolerance rule", "add propositional structure and exact arithmetic on given values but do not check units",
                  "significant-figure policy"):
        assert f"\"{quote}\"" in d30 and quote in physics, quote
    quote = "transcendental identities beyond exact values and 10^-15 enclosures"
    assert f"\"{quote}\"" in d30 and quote in maa and quote not in physics
    assert "toleran" not in STEM_ENCODING_GUIDANCE.lower() and "enclosure" not in STEM_ENCODING_GUIDANCE.lower()
    assert "The translator is told nothing about tolerances or enclosures" in d30


def test_the_pack_teaches_the_stem_receipt_checks():
    inspection, kinds = _pack_text("03-inspection.md"), _pack_text("06-kinds-and-codes.md")
    i98 = inspection.split("**I98 ", 1)[1].split("\n## ", 1)[0]
    for words in ("`finding_missing`", "`receipt_altered`", "INT-SUBJ-001", "INT-SUBJ-004", "solver"):
        assert words in i98, words
    assert "Dossier guide D32" in kinds and "Inspection I98" in kinds
