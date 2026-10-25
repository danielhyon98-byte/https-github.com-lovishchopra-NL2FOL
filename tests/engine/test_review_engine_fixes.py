"""Regression tests for the engine findings of the external review of 12 October 2026.

Each test encodes the review's acceptance criterion, with negative controls where the rejected conclusion really is
wrong:

* premise authority (finding 2): a model-chosen task or source grounding kind confers nothing until an application
  check verified it; an unchecked one is an unverified dependency, never hidden, and formal entailment stays separate
  from release eligibility;
* the core setting (finding 3): ``produce_unsat_core`` is an output option only; dependency evidence, vacuity (E108),
  circularity (E112) and release eligibility are the same with it on or off;
* stale results (finding 5): genuine results signed by earlier releases (``data/``) stay inspectable but never pass a
  current-policy check, and unchanged version strings cannot make another build's result current;
* coverage diagnostics (finding 6): structural underdetermination is the advisory W110/W111 and the COUNTEREXAMPLE
  stands, unless source-linked evidence (a grounding a check in this process verified) shows that the source asserted
  what the translation omitted, which is E110/E111 (no verdict);
* the limits binding (finding 8): the effective validation limits are bound, separately from the version identity, and
  compared with the receiver's required policy.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from epinoic_logic.engine import identity as identity_mod
from epinoic_logic.engine.authority import has_authority, is_unverified
from epinoic_logic.engine.errors import ADVISORY_CODES, NO_VERDICT_CODES
from epinoic_logic.engine.policies import JOINT_LIMITS, NONLINEAR_LIMITS
from epinoic_logic.engine.provenance import (
    binding_digest_of,
    binding_inconsistencies,
    compute_versions,
    limits_digest,
    sign_result,
    stale_reasons,
    verify_signature,
    versions_digest,
)
from epinoic_logic.engine.release import release_check
from epinoic_logic.engine.results import SolverConfig, VerificationResult
from epinoic_logic.engine.runner import verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity.handoff import check_result_binding
from epinoic_logic.ir.canonical import problem_digest
from epinoic_logic.ir.schema import DEFAULT_LIMITS, Limits, Problem
from epinoic_logic.translate.contracts import EligibilityDecision, TranslationResult, sha256_text
from epinoic_logic.translate.outcome import display_status_for
from epinoic_logic.version import ENGINE_VERSION, IR_VERSION, POLICY_VERSION, TRANSLATOR_VERSION

from .conftest import I, R, V, cmp, make_problem

KEY = b"review-engine-key-0123456789abcd"
KEY_ID = "review"
CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)
NO_CORE = CFG.model_copy(update={"produce_unsat_core": False})
DATA = Path(__file__).parent / "data"
TRUSTED_KINDS = ("arithmetic_fact", "task_setting", "rubric_rule")


def P(data: dict) -> Problem:
    return Problem.model_validate(data)


def codes(result: VerificationResult) -> list[str]:
    return [d.code for d in result.diagnostics]


def translated(problem: Problem) -> TranslationResult:
    # A record as this translator makes it: its version and the digest of the claim text it read (contract 0.2). A record
    # without that digest is from before 0.2 and is displayed INTERNAL_ERROR (re-run review finding correctness-5).
    return TranslationResult(translation_id="tr", request_id=problem.request_id, report_id="rep1", claim_id=problem.claim_id, status="TRANSLATED",
                             eligibility=EligibilityDecision(eligibility_class="PROPOSITIONAL_ARGUMENT", eligible=True, decided_by="deterministic",
                                                             policy_version=POLICY_VERSION),
                             claim_text_sha256=sha256_text(f"the claim {problem.claim_id} encodes"),
                             problem=problem, translator_version=TRANSLATOR_VERSION, policy_version=POLICY_VERSION, created_at="2026-10-12T00:00:00Z")


def chain(kind: str | None, *, verified: bool | None = None) -> Problem:
    """p, p -> q |= q with both premises grounded as ``kind`` (``None``: no grounding)."""
    g = None if kind is None else {"kind": kind, **({} if verified is None else {"verified": verified})}
    meta = {} if g is None else {"grounding": g}
    return P(make_problem("entailment", [("p", "Bool"), ("q", "Bool")],
                          [("P", V("p"), meta), ("L", {"op": "implies", "left": V("p"), "right": V("q")}, meta)], ("C", V("q"))))


def distance(km: int, *, verified: bool | None = None) -> Problem:
    """The review's arithmetic case: distance ``km`` over 8 hours, speed = distance / 8, conclusion speed = 20 (or 15)."""
    g = {"kind": "arithmetic_fact", **({} if verified is None else {"verified": verified})}
    return P(make_problem("entailment", [("d", "Real"), ("speed", "Real")],
                          [("D", cmp("eq", V("d"), R(km)), {"label": f"Distance is {km} km", "grounding": g}),
                           ("SPEED", cmp("eq", V("speed"), {"op": "div", "left": V("d"), "right": R(8)}), {"grounding": g})],
                          ("C", cmp("eq", V("speed"), R(km // 8)))))


# =========================================================================== finding 2: premise authority


@pytest.mark.parametrize("kind", TRUSTED_KINDS)
@pytest.mark.parametrize("config", [CFG, NO_CORE], ids=["core-on", "core-off"])
def test_a_model_chosen_trusted_kind_is_an_unverified_dependency_never_hidden(kind: str, config: SolverConfig):
    r = verify(chain(kind), config, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.ENTAILED and codes(r) == []          # formal entailment is kept ...
    assert r.premises_relied_on == ["P", "L"]
    assert r.ungrounded_dependencies == [] and r.unverified_dependencies == ["P", "L"]
    check = release_check(r, chain(kind), signing_key=KEY, key_id=KEY_ID)
    assert not check.eligible                                   # ... and is not permission to release
    assert any("authority not validated" in why and "P, L" in why for why in check.reasons), check.reasons


@pytest.mark.parametrize("kind", TRUSTED_KINDS + ("supplied_text", "knowledge_document", "library_source", "quotation"))
def test_only_an_application_verified_record_confers_authority(kind: str):
    """Negative control: the same premises verified by a check in this process are established and release-eligible."""
    problem = chain(kind, verified=True)
    r = verify(problem, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.ENTAILED and r.ungrounded_dependencies == [] and r.unverified_dependencies == []
    check = release_check(r, problem, signing_key=KEY, key_id=KEY_ID)
    assert check.eligible, check.reasons
    assert has_authority(problem.premises[0].grounding) and not is_unverified(problem.premises[0].grounding)


@pytest.mark.parametrize("kind", TRUSTED_KINDS)
def test_a_payload_cannot_grant_itself_authority(kind: str):
    """A problem that arrives as data asserting verified=true is demoted (E505): its premises stay unverified."""
    raw = json.loads(chain(kind, verified=True).model_dump_json(exclude_none=True))
    r = verify(raw, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.ENTAILED and "E505" in codes(r)
    assert r.unverified_dependencies == ["P", "L"]
    assert not release_check(r, signing_key=KEY, key_id=KEY_ID).eligible


def test_the_altered_distance_is_an_unresolved_dependency_and_a_failed_check_is_ungrounded():
    """The review's 120-to-160 substitution: the invented 160 km 'arithmetic_fact' proves speed 20, but it is listed as
    an unresolved dependency and the result is not release-eligible; a grounding check that refutes it makes it an
    ungrounded dependency (an evidence failure)."""
    invented = distance(160)
    r = verify(invented, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.ENTAILED and sorted(r.unverified_dependencies) == ["D", "SPEED"] and r.ungrounded_dependencies == []
    assert not release_check(r, invented, signing_key=KEY, key_id=KEY_ID).eligible
    refuted = distance(160, verified=False)
    rf = verify(refuted, CFG, signing_key=KEY, key_id=KEY_ID)
    assert rf.status is S.ENTAILED and sorted(rf.ungrounded_dependencies) == ["D", "SPEED"]
    assert not release_check(rf, refuted, signing_key=KEY, key_id=KEY_ID).eligible


def test_the_authentic_distance_still_supports_its_speed():
    """Control: 120 km over 8 hours still entails 15 km/h. Unchecked it is unresolved; verified against the source (an
    application record) it is established and release-eligible. A wrong conclusion from the authentic figure fails."""
    authentic = distance(120)
    r = verify(authentic, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.ENTAILED and sorted(r.unverified_dependencies) == ["D", "SPEED"]
    checked = distance(120, verified=True)
    rc = verify(checked, CFG, signing_key=KEY, key_id=KEY_ID)
    assert rc.status is S.ENTAILED and rc.unverified_dependencies == [] and release_check(rc, checked, signing_key=KEY, key_id=KEY_ID).eligible
    wrong = P({**json.loads(checked.model_dump_json(exclude_none=True)), "conclusion": {"id": "C", "expr": cmp("eq", V("speed"), R(20))}})
    rw = verify(wrong, CFG, signing_key=KEY, key_id=KEY_ID)
    assert rw.status is S.COUNTEREXAMPLE and not release_check(rw, wrong, signing_key=KEY, key_id=KEY_ID).eligible


def test_the_invented_distance_through_the_translator_is_an_evidence_failure_and_names_every_dependency():
    """The review's end-to-end probe: a fixture translation substitutes 160 for the supplied 120 and labels the premises
    arithmetic_fact without sources. The outcome is still the formal ENTAILED, but no relied-on premise is hidden: the
    translation layer's authority check (an application record) refutes the invented 160 against the supplied 120 km, so
    D is an ungrounded dependency (an evidence failure) in the signed result and the summary, SPEED (speed = d / 8, a
    relation no record states) is an unverified dependency, and the release check refuses the result.

    Rewritten at the integration of the review fixes (stricter): the engine-only version asserted that both premises were
    unverified (unchecked); with the translation layer's checks the invented figure is refuted, not merely unchecked, and
    every relied-on premise is either listed as a dependency or carries a passing application check. Rewritten again at
    the second repair (stricter still, verifier finding 2): SPEED had counted as established because its figure 8 occurs
    in the supplied text ("8 hours"); a figure occurring in a record is no evidence for the relation that combines it, so
    SPEED is now listed as an unverified dependency instead of carrying a passing check."""
    from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
    from epinoic_logic.translate.outcome import verify_claim
    from epinoic_logic.translate.pipeline import Translator
    from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Physics", task_type="calculation")
    claim = ClaimRecord(**ids, claim_id="c", claim_text="The speed is 20 km/h.", claim_role="quantitative", proposed_claim_kind="arithmetic",
                        supporting_claim_ids=["support"])
    support = ClaimRecord(**ids, claim_id="support", claim_text="Distance 120 km over 8 hours.", claim_role="evidence")
    text = "Distance 120 km over 8 hours."
    report = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), claims=[claim, support],
                              supplied_texts=[SuppliedText(document_id="doc", text=text)], created_at="2026-10-11T00:00:00Z")
    problem = json.loads(distance(160).model_dump_json(exclude_none=True))
    problem.update(request_id="r", claim_id="c", problem_id="p")
    output = dict(problem=problem, interpretation=dict(reading="Speed is distance divided by time", glossary=[], ambiguity_flags=[]),
                  ambiguous=False, unsupported_reason=None)
    outcome = verify_claim(claim, report, Translator(FixtureTranslationProvider({"c": output})), config=CFG, signing_key=KEY, key_id=KEY_ID)
    v = outcome.verification
    assert v is not None and v.status is S.ENTAILED and outcome.display_status is S.ENTAILED   # formal entailment is kept ...
    assert v.premises_relied_on == ["D", "SPEED"]
    # ... the invented figure is refuted, and (rewritten to a stricter rule, repair 2 of the integration) the relation
    # speed = d / 8, which no record states, is an unverified dependency: the 8 of "8 hours" in the text is no evidence for it
    assert v.ungrounded_dependencies == ["D"] and v.unverified_dependencies == ["SPEED"]
    checks = {c.target_id: c for c in outcome.translation.grounding_checks if c.method == "numeric_in_task"}
    assert checks["D"].verified is False and "160" in checks["D"].detail and "120 km" in checks["D"].detail and "doc" in checks["D"].detail
    relation = next(c for c in outcome.translation.grounding_checks if c.target_id == "SPEED" and c.method == "relation_in_source")
    assert relation.verified is None and "8 hours" in relation.detail and "no record states the premise's relation" in relation.detail
    assert "SPEED" not in checks or checks["SPEED"].verified is not True
    # nothing hidden: every relied-on premise is a listed dependency or carries a passing application check
    premises = {p.id: p for p in outcome.translation.problem.premises}
    for pid in v.premises_relied_on:
        assert pid in v.ungrounded_dependencies + v.unverified_dependencies or (premises[pid].grounding.verified is True and checks[pid].verified is True)
    assert "Ungrounded dependencies (relied on but not established by the supplied material): D (" in outcome.summary
    assert "grounding check failed" in outcome.summary and "Failed grounding checks: D" in outcome.summary
    assert "Ungrounded dependencies: none; unverified dependencies: none" not in outcome.summary
    check = release_check(v, outcome.translation.problem, signing_key=KEY, key_id=KEY_ID)
    assert not check.eligible and any("ungrounded" in why and "D" in why for why in check.reasons), check.reasons
    assert outcome.release is not None and not outcome.release.permitted and not outcome.release.evidence_resolved


def test_direct_self_assumption_is_still_circular():
    """E112 (an improvement the review asked to preserve) is unchanged, with cores on and off."""
    p = P(make_problem("entailment", [("p", "Bool")], [("P", V("p"), {"grounding": {"kind": "assumption"}})], ("C", V("p"))))
    for config in (CFG, NO_CORE):
        r = verify(p, config, signing_key=KEY, key_id=KEY_ID)
        assert r.status is S.ENTAILED and codes(r) == ["E112"] and r.premises_relied_on == ["P"] and r.ungrounded_dependencies == ["P"]
        assert display_status_for(translated(p), r, KEY, KEY_ID) is S.INVALID_FORMALIZATION


# =========================================================================== finding 3: the core setting


def _evidence(r: VerificationResult) -> tuple:
    return (r.status, r.premises_relied_on, r.ungrounded_dependencies, r.unverified_dependencies, codes(r))


PROBLEMS: dict[str, Any] = {
    "assumption-chain": lambda: chain("assumption"),
    "trusted-chain": lambda: chain("task_setting"),
    "verified-chain": lambda: chain("task_setting", verified=True),
    "tautology": lambda: P(make_problem("entailment", [("p", "Bool")], [], ("C", {"op": "or", "args": [V("p"), {"op": "not", "arg": V("p")}]}))),
    "self-assumption": lambda: P(make_problem("entailment", [("p", "Bool")], [("P", V("p"), {"grounding": {"kind": "assumption"}})], ("C", V("p")))),
    "inconsistent": lambda: P(make_problem("entailment", [("x", "Int")], [("A", cmp("gt", V("x"), I(3)), {"grounding": {"kind": "rubric_rule"}}),
                                                                          ("B", cmp("lt", V("x"), I(2)), {"grounding": {"kind": "assumption"}})],
                                           ("C", cmp("eq", V("x"), I(0))))),
    "unsatisfiable": lambda: P(make_problem("satisfiability", [("x", "Int")], [("A", cmp("gt", V("x"), I(3))), ("B", cmp("lt", V("x"), I(2)))])),
}


@pytest.mark.parametrize("name", sorted(PROBLEMS))
def test_toggling_core_output_changes_no_evidence_vacuity_or_release_eligibility(name: str):
    problem = PROBLEMS[name]()
    on = verify(problem, CFG, signing_key=KEY, key_id=KEY_ID)
    off = verify(problem, NO_CORE, signing_key=KEY, key_id=KEY_ID)
    assert _evidence(on) == _evidence(off)
    assert release_check(on, problem, signing_key=KEY, key_id=KEY_ID) == release_check(off, problem, signing_key=KEY, key_id=KEY_ID)
    assert display_status_for(translated(problem), on, KEY, KEY_ID) is display_status_for(translated(problem), off, KEY, KEY_ID)
    # the flag only decides whether the raw core record is serialised
    assert off.unsat_core is None
    if on.status in (S.ENTAILED, S.INCONSISTENT_PREMISES, S.UNSATISFIABLE) and on.premises_relied_on:
        assert on.unsat_core is not None and on.unsat_core.premise_ids == on.premises_relied_on


def test_the_premise_free_tautology_is_vacuous_with_cores_off():
    problem = PROBLEMS["tautology"]()
    off = verify(problem, NO_CORE, signing_key=KEY, key_id=KEY_ID)
    assert off.status is S.ENTAILED and codes(off) == ["E108"]
    assert display_status_for(translated(problem), off, KEY, KEY_ID) is S.INVALID_FORMALIZATION
    assert any("no verdict on the claim: E108" in why for why in release_check(off, problem, signing_key=KEY, key_id=KEY_ID).reasons)


def test_the_assumption_chain_keeps_its_dependencies_with_cores_off():
    off = verify(chain("assumption"), NO_CORE, signing_key=KEY, key_id=KEY_ID)
    assert off.status is S.ENTAILED and off.premises_relied_on == ["P", "L"] and off.ungrounded_dependencies == ["P", "L"]


def test_a_conflicting_set_is_named_with_cores_off():
    off = verify(PROBLEMS["inconsistent"](), NO_CORE, signing_key=KEY, key_id=KEY_ID)
    assert off.status is S.INCONSISTENT_PREMISES and sorted(off.premises_relied_on) == ["A", "B"]
    assert off.ungrounded_dependencies == ["B"] and off.unverified_dependencies == ["A"]


def test_an_established_proof_is_release_eligible_with_cores_on_and_off():
    """Negative control: the release check is not merely always false."""
    problem = PROBLEMS["verified-chain"]()
    for config in (CFG, NO_CORE):
        assert release_check(verify(problem, config, signing_key=KEY, key_id=KEY_ID), problem, signing_key=KEY, key_id=KEY_ID).eligible


# =========================================================================== finding 5: stale results


def _previous() -> dict[str, dict]:
    return json.loads((DATA / "release_0_3_0_signed_results.json").read_text())


PREVIOUS_KEY = b"upgrade-test-key-0123456789abcdef"
BASELINE_KEY = b"probe-signing-key-0123456789012345"


def test_the_component_versions_are_bumped_by_the_version_rules():
    # the pin moves with each release and stays exact: the argument-diagnosis release (rules argdiag-1) bumped the engine,
    # the policy and the translator once, and left the IR unchanged; close round 3 of that release moved the translator to
    # 0.5.1 with the rules (argdiag-2), so a translation record of an earlier round reads as stale
    assert (IR_VERSION, ENGINE_VERSION, POLICY_VERSION, TRANSLATOR_VERSION) == ("1.0", "0.5.0", "2026.10-v5", "0.5.1")
    v = compute_versions()
    assert v.engine_version == ENGINE_VERSION and v.policy_version == POLICY_VERSION
    assert all(isinstance(getattr(v, k), str) and len(getattr(v, k)) == 64 for k in ("build_id", "schema_id", "policy_id"))


@pytest.mark.parametrize("case", sorted(_previous()))
def test_a_real_previous_release_result_is_inspectable_but_never_current(case: str):
    entry = _previous()[case]
    old = VerificationResult.model_validate(entry["result"])
    problem = P(entry["problem"])
    config = SolverConfig.model_validate(entry["config"])
    # inspectable: it parses, re-serialises byte-identically and its signature still verifies
    assert old.versions.engine_version == "0.3.0" and old.versions.policy_version == "2026.10-v3" and old.versions.build_id is None
    assert json.loads(old.model_dump_json()) == entry["result"]
    assert verify_signature(old, PREVIOUS_KEY) and binding_inconsistencies(old) == []
    # never current: every current-policy check refuses it
    stale = stale_reasons(old)
    assert stale and "identity" in stale[0]
    findings = check_result_binding(old, problem, PREVIOUS_KEY, config=config, limits=Limits.model_validate(entry["limits"]))
    assert [f.code for f in findings] == ["INT-STALE-005"] and "versions" in findings[0].message
    check = release_check(old, problem, signing_key=PREVIOUS_KEY, key_id="upgrade", required_limits=Limits.model_validate(entry["limits"]))
    assert not check.eligible and any(why.startswith("stale:") for why in check.reasons)
    assert display_status_for(translated(problem), old, PREVIOUS_KEY, "upgrade") is S.INTERNAL_ERROR
    # revalidation under the current policy produces a current result that passes the same checks
    fresh = verify(problem, config, Limits.model_validate(entry["limits"]), signing_key=PREVIOUS_KEY, key_id="upgrade")
    assert check_result_binding(fresh, problem, PREVIOUS_KEY, config=config, limits=Limits.model_validate(entry["limits"])) == []
    assert stale_reasons(fresh, required_limits=Limits.model_validate(entry["limits"])) == []


def test_revalidation_applies_the_current_policy_to_the_previous_release_cases():
    prev = _previous()
    taut = prev["tautology_without_core_output"]
    assert taut["result"]["status"] == "ENTAILED" and taut["result"]["diagnostics"] == []          # 0.3.0 signed it as a verdict
    now = verify(P(taut["problem"]), SolverConfig.model_validate(taut["config"]))
    assert codes(now) == ["E108"]
    chain_case = prev["trusted_kind_chain"]
    assert chain_case["result"]["unverified_dependencies"] == []                                       # 0.3.0 hid both premises
    assert verify(P(chain_case["problem"]), SolverConfig.model_validate(chain_case["config"])).unverified_dependencies == ["P", "L"]
    nl = prev["nonlinear_permissive"]
    default_binding = verify(P(nl["problem"]), SolverConfig.model_validate(nl["config"])).binding
    assert verify(P(nl["problem"]), SolverConfig.model_validate(nl["config"]), Limits.model_validate(nl["limits"])).binding.binding_digest != default_binding.binding_digest
    definition = prev["definition_counterexample"]
    assert [d["code"] for d in definition["result"]["diagnostics"]] == ["E110"]
    assert codes(verify(P(definition["problem"]), SolverConfig.model_validate(definition["config"]))) == ["W110"]


def test_the_reviewed_baseline_signed_result_cannot_satisfy_a_current_check():
    """The review's own upgrade case: a result signed by the published baseline (engine 0.2.0) for p |= p has no E112.
    It stays inspectable (valid signature) but is displayed as INTERNAL_ERROR, never as ENTAILED, and every current
    check names it stale; the current build decides the same problem as E112."""
    raw = json.loads((DATA / "release_0_2_0_baseline_signed_result.json").read_text())
    old = VerificationResult.model_validate(raw)
    problem = P(make_problem("entailment", [("p", "Bool")], [("P", V("p"), {"grounding": {"kind": "assumption"}})], ("C", V("p")),
                             problem_id="p1", request_id="r1", claim_id="c1"))   # the review's version probe, verbatim
    assert old.versions.engine_version == "0.2.0" and old.status is S.ENTAILED and old.diagnostics == []
    assert verify_signature(old, BASELINE_KEY) and old.binding.problem_digest == problem_digest(problem)
    assert display_status_for(translated(problem), old, BASELINE_KEY, "probe") is S.INTERNAL_ERROR
    assert [f.code for f in check_result_binding(old, problem, BASELINE_KEY, config=old.solver_config)] == ["INT-STALE-005"]
    assert not release_check(old, problem, signing_key=BASELINE_KEY, key_id="probe").eligible
    current = verify(problem, old.solver_config, signing_key=BASELINE_KEY, key_id="probe")
    assert codes(current) == ["E112"] and display_status_for(translated(problem), current, BASELINE_KEY, "probe") is S.INVALID_FORMALIZATION


def test_unchanged_version_strings_cannot_make_another_build_current():
    """The failure the review found: two builds with identical version strings. A result whose identity names another
    build (re-signed, internally consistent) is stale although every version string matches."""
    problem = chain("task_setting", verified=True)
    r = verify(problem, CFG, signing_key=KEY, key_id=KEY_ID)
    other = r.versions.model_copy(update={"build_id": "0" * 64})
    vd = versions_digest(other)
    forged = r.model_copy(update={"versions": other, "binding": r.binding.model_copy(update={
        "versions_digest": vd, "binding_digest": binding_digest_of(r.binding.problem_digest, r.binding.config_digest, vd, r.binding.limits_digest)})})
    forged = sign_result(forged, KEY, KEY_ID)
    assert (forged.versions.engine_version, forged.versions.policy_version) == (ENGINE_VERSION, POLICY_VERSION)
    assert verify_signature(forged, KEY) and binding_inconsistencies(forged) == []
    assert any("build_id" in why for why in stale_reasons(forged))
    assert [f.code for f in check_result_binding(forged, problem, KEY, config=CFG)] == ["INT-STALE-005"]
    assert not release_check(forged, problem, signing_key=KEY, key_id=KEY_ID).eligible
    assert display_status_for(translated(problem), forged, KEY, KEY_ID) is S.INTERNAL_ERROR
    assert release_check(r, problem, signing_key=KEY, key_id=KEY_ID).eligible                         # control: the genuine current result


def test_the_build_identity_changes_with_any_decision_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # rewritten for the argument diagnosis, stricter: the copy holds every entry of BUILD_SOURCES (the shared named.py and
    # lexis.py included, which the engine's diagnosis depends on), and a change to the engine source and a change to the
    # named-code module each change the build id
    package = Path(identity_mod.__file__).resolve().parent.parent
    copy = tmp_path / "epinoic_logic"
    copy.mkdir()
    for entry in identity_mod.BUILD_SOURCES:
        if (package / entry).is_dir():
            shutil.copytree(package / entry, copy / entry, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(package / entry, copy / entry)
    assert {"version.py", "named.py", "lexis.py", "ir", "engine"} <= set(identity_mod.BUILD_SOURCES)
    monkeypatch.setattr(identity_mod, "_PACKAGE", copy)
    identity_mod.build_id.cache_clear()
    try:
        same = identity_mod.build_id()
        assert same == identity_mod.build_id.__wrapped__() and len(same) == 64
        runner = copy / "engine" / "runner.py"
        runner.write_text(runner.read_text() + "\n# a change to the engine source\n")
        identity_mod.build_id.cache_clear()
        changed = identity_mod.build_id()
        assert changed != same and len(changed) == 64
        named = copy / "named.py"
        named.write_text(named.read_text() + "\n# a change to the named-code table module\n")
        identity_mod.build_id.cache_clear()
        again = identity_mod.build_id()
        assert again not in (same, changed) and len(again) == 64
    finally:
        identity_mod.build_id.cache_clear()
    monkeypatch.undo()
    assert identity_mod.build_id() == compute_versions().build_id


def test_the_policy_identity_covers_the_decision_rules():
    manifest = identity_mod.policy_manifest()
    assert manifest["policy_version"] == POLICY_VERSION
    assert manifest["dependencies"]["authority"] == "verified-in-process-only"
    assert set(manifest["no_verdict_diagnostics"]) == NO_VERDICT_CODES and set(manifest["advisory_diagnostics"]) == ADVISORY_CODES
    assert manifest["default_limits"] == DEFAULT_LIMITS.model_dump(mode="json") and manifest["joint_limits"] == JOINT_LIMITS.model_dump(mode="json")
    assert "always computed" in manifest["evidence"]["unsat_core"]


# =========================================================================== finding 6: coverage diagnostics


def definition(*, figure_grounding: dict | None = None, label: str = "Define b to hold iff n equals 17; this definition does not assert b.") -> Problem:
    """Define b iff n = 17; does b necessarily hold?"""
    n = ("n", "Int", {"grounding": figure_grounding}) if figure_grounding is not None else ("n", "Int")
    return P(make_problem("entailment", [("b", "Bool"), n],
                          [("D", {"op": "iff", "left": V("b"), "right": cmp("eq", V("n"), I(17))}, {"label": label, "grounding": {"kind": "task_setting"}})],
                          ("C", V("b"), {"label": "b necessarily holds"})))


def arbitrary(*, y_grounding: dict | None = None) -> Problem:
    """Given x = 5, is x < y for an arbitrary integer y?"""
    y = ("y", "Int", {"grounding": y_grounding}) if y_grounding is not None else ("y", "Int")
    return P(make_problem("entailment", [("x", "Int"), y],
                          [("P", cmp("eq", V("x"), I(5)), {"label": "x equals 5; y is an arbitrary integer.", "grounding": {"kind": "task_setting"}})],
                          ("C", cmp("lt", V("x"), V("y")), {"label": "x is necessarily less than arbitrary y"})))


STATED = {"kind": "task_setting", "verified": True, "source_refs": [{"document_id": "task", "excerpt": "n is 17"}]}


def test_a_definition_that_asserts_nothing_keeps_its_counterexample():
    """Intentionally unconstrained: the definition does not assert b, so 'b need not hold' is the right answer."""
    p = definition()
    r = verify(p, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["W110"]
    assert {a.symbol: a.value for a in r.counterexample.assignments}["b"] == "false"
    assert "advisory" in r.diagnostics[0].message and "definition is not an assertion" in r.diagnostics[0].message
    assert "must assert" not in r.diagnostics[0].message                       # never an instruction to add the premise
    assert display_status_for(translated(p), r, KEY, KEY_ID) is S.COUNTEREXAMPLE


def test_a_figure_the_source_asserts_and_the_translation_omits_is_no_verdict():
    """Source asserted and omitted: an application check located the figure's value in the task, yet no premise asserts
    it, so the counterexample (n = 2) is no verdict on the claim."""
    p = definition(figure_grounding=STATED)
    r = verify(p, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E110"]
    assert "a source states n" in r.diagnostics[0].message and "verified against task" in r.diagnostics[0].message
    assert display_status_for(translated(p), r, KEY, KEY_ID) is S.INVALID_FORMALIZATION


def test_a_payload_cannot_supply_source_evidence_for_itself():
    raw = json.loads(definition(figure_grounding=STATED).model_dump_json(exclude_none=True))
    r = verify(raw, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E505", "W110"]


def test_a_model_label_or_kind_is_not_source_evidence():
    """A label saying the figure is stated, or an unchecked grounding on the figure, is the translation's own claim."""
    p = definition(figure_grounding={"kind": "supplied_text", "source_refs": [{"document_id": "task", "excerpt": "n is 17"}]},
                   label="n equals 17, as the task states")
    assert codes(verify(p, CFG)) == ["W110"]


def test_an_arbitrary_variable_keeps_its_counterexample():
    """Intentionally unconstrained: y is arbitrary, so x < y does not follow (x = 5, y = 0)."""
    p = arbitrary()
    r = verify(p, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["W111"]
    assert {a.symbol: a.value for a in r.counterexample.assignments}["x"] == "5"
    assert display_status_for(translated(p), r, KEY, KEY_ID) is S.COUNTEREXAMPLE


def test_a_value_the_source_states_and_the_translation_omits_is_an_unencoded_reason():
    p = arbitrary(y_grounding={"kind": "supplied_text", "verified": True, "source_refs": [{"document_id": "doc", "excerpt": "y is 9"}]})
    r = verify(p, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E111"] and "a source states y" in r.diagnostics[0].message
    assert display_status_for(translated(p), r, KEY, KEY_ID) is S.INVALID_FORMALIZATION


def test_an_encoded_value_decides_the_claim_with_no_coverage_warning():
    """Negative controls with the value encoded: y = 9 entails x < y; y = 2 refutes it, a COUNTEREXAMPLE with no warning."""
    for value, status in ((9, S.ENTAILED), (2, S.COUNTEREXAMPLE)):
        data = json.loads(arbitrary().model_dump_json(exclude_none=True))
        data["premises"].append({"id": "Y", "expr": cmp("eq", V("y"), I(value)), "grounding": {"kind": "task_setting", "verified": True}})
        r = verify(P(data), CFG)
        assert r.status is status and not set(codes(r)) & (NO_VERDICT_CODES | ADVISORY_CODES)


def test_an_asserted_definition_decides_the_claim():
    """Negative control: the definition plus the asserted figure entails b; with another figure it refutes b."""
    for value, status in ((17, S.ENTAILED), (2, S.COUNTEREXAMPLE)):
        data = json.loads(definition().model_dump_json(exclude_none=True))
        data["premises"].append({"id": "N", "expr": cmp("eq", V("n"), I(value)), "grounding": {"kind": "task_setting", "verified": True}})
        r = verify(P(data), CFG)
        assert r.status is status and not set(codes(r)) & (NO_VERDICT_CODES | ADVISORY_CODES), codes(r)


# =========================================================================== finding 8: the limits binding


def square() -> Problem:
    return P(make_problem("satisfiability", [("x", "Int")], [("P", cmp("eq", {"op": "mul", "args": [V("x"), V("x")]}, I(4)))]))


def test_effective_limits_are_bound_and_compared_with_the_required_policy():
    p = square()
    default = verify(p, CFG, signing_key=KEY, key_id=KEY_ID)
    permissive = verify(p, CFG, NONLINEAR_LIMITS, signing_key=KEY, key_id=KEY_ID)
    assert default.status is S.UNSUPPORTED and permissive.status is S.SATISFIABLE
    assert default.binding.binding_digest != permissive.binding.binding_digest
    # separate from the version identity: same versions, the limits digest alone tells the two policies apart
    assert default.binding.versions_digest == permissive.binding.versions_digest
    assert default.binding.limits_digest is None and permissive.binding.limits_digest == limits_digest(NONLINEAR_LIMITS)
    b = permissive.binding
    assert b.binding_digest == binding_digest_of(b.problem_digest, b.config_digest, b.versions_digest, b.limits_digest)
    # a default-policy receiver refuses the permissive result; a receiver that requires the permissive policy accepts it
    found = check_result_binding(permissive, p, KEY, config=CFG)
    assert [f.code for f in found] == ["INT-STALE-005"] and "validation policy" in found[0].message and "allow_nonlinear=True" in found[0].message
    assert check_result_binding(permissive, p, KEY, config=CFG, limits=NONLINEAR_LIMITS) == []
    assert [f.code for f in check_result_binding(default, p, KEY, config=CFG, limits=NONLINEAR_LIMITS)] == ["INT-STALE-005"]
    assert check_result_binding(default, p, KEY, config=CFG) == []
    assert any("required policy" in why for why in release_check(permissive, p, signing_key=KEY, key_id=KEY_ID).reasons)
    assert not any("required policy" in why for why in release_check(permissive, p, signing_key=KEY, key_id=KEY_ID, required_limits=NONLINEAR_LIMITS).reasons)


def test_a_stripped_or_swapped_limits_record_is_inconsistent_with_its_binding():
    p = square()
    permissive = verify(p, CFG, NONLINEAR_LIMITS, signing_key=KEY, key_id=KEY_ID)
    for forged in (None, DEFAULT_LIMITS, Limits(allow_nonlinear=True, max_nodes=10 ** 6)):
        edited = permissive.model_copy(update={"limits": forged})
        assert "limits_digest != digest(limits)" in binding_inconsistencies(edited)
        assert {"INT-STALE-002", "INT-STALE-007"} <= {f.code for f in check_result_binding(edited, p, KEY, config=CFG, limits=NONLINEAR_LIMITS)}


def test_joint_results_bind_the_joint_limits():
    from epinoic_logic.integrity.cross_check import check_cross_report_consistency
    a = P(make_problem("consistency", [("v", "Int")], [("P", cmp("gt", V("v"), I(0)))], claim_id="a-1", problem_id="pa"))
    b = P(make_problem("consistency", [("v", "Int")], [("Q", cmp("lt", V("v"), I(9)))], claim_id="b-1", problem_id="pb"))
    res, findings = check_cross_report_consistency([a, b], request_id="req1", config=CFG, signing_key=KEY)
    assert res is not None and res.status is S.CONSISTENT and findings == []
    assert res.limits == JOINT_LIMITS and res.binding.limits_digest == limits_digest(JOINT_LIMITS)
    assert stale_reasons(res, required_limits=JOINT_LIMITS) == [] and stale_reasons(res) != []


def test_a_proof_from_a_stale_prior_result_is_not_evidence_for_a_synthesis():
    """The synthesis check accepts a pooled source conclusion only on current-policy evidence: an otherwise valid prior
    ENTAILED result issued under another build identity no longer counts (INT-SYNTH-008 stays)."""
    from epinoic_logic.integrity.cross_check import check_synthesis_entailment
    from epinoic_logic.ir.schema import Assertion
    good = P(make_problem("entailment", [("d", "Real"), ("v", "Real")],
                          [("D", cmp("eq", V("d"), R(120)), {"grounding": {"kind": "task_setting", "verified": True}}),
                           ("V", cmp("eq", V("v"), {"op": "div", "left": V("d"), "right": R(8)}), {"grounding": {"kind": "task_setting", "verified": True}})],
                          ("C", cmp("eq", V("v"), R(15))), claim_id="ph-1", problem_id="p-ph-1", request_id="req1"))
    concl_only = P({**json.loads(good.model_dump_json(exclude_none=True)), "premises": []})
    prior = verify(concl_only, CFG, signing_key=KEY, key_id=KEY_ID)
    entailed_prior = prior.model_copy(update={"status": S.ENTAILED, "diagnostics": []})
    entailed_prior = sign_result(entailed_prior, KEY, KEY_ID)
    target = Assertion(id="S", expr=cmp("eq", V("v"), R(15)))
    _, ok = check_synthesis_entailment([concl_only], target, request_id="req1", synthesized_claim_id="s-1", config=CFG, signing_key=KEY,
                                       prior_results={"ph-1": entailed_prior})
    assert "INT-SYNTH-008" not in [f.code for f in ok]
    other = entailed_prior.versions.model_copy(update={"build_id": "1" * 64})
    vd = versions_digest(other)
    stale = entailed_prior.model_copy(update={"versions": other, "binding": entailed_prior.binding.model_copy(update={
        "versions_digest": vd, "binding_digest": binding_digest_of(entailed_prior.binding.problem_digest, entailed_prior.binding.config_digest, vd)})})
    stale = sign_result(stale, KEY, KEY_ID)
    _, refused = check_synthesis_entailment([concl_only], target, request_id="req1", synthesized_claim_id="s-1", config=CFG, signing_key=KEY,
                                            prior_results={"ph-1": stale})
    assert "INT-SYNTH-008" in [f.code for f in refused]
    forged = entailed_prior.model_copy(update={"signature": "0" * 64})
    _, unsigned = check_synthesis_entailment([concl_only], target, request_id="req1", synthesized_claim_id="s-1", config=CFG, signing_key=KEY,
                                             prior_results={"ph-1": forged})
    assert "INT-SYNTH-008" in [f.code for f in unsigned]
