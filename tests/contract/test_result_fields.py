"""The argument diagnosis on the engine result: ``named_diagnostics`` and ``argument_rules``, their place in the dumps,
their signed binding, the ``diagnose`` and ``severity_cap`` keywords, and results of the previous release."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig, verify, verify_signature
from epinoic_logic.engine import argument as argument_module
from epinoic_logic.engine.provenance import stale_reasons
from epinoic_logic.engine.release import release_check
from epinoic_logic.engine.results import VerificationResult
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Limits, Problem
from epinoic_logic.named import NamedDiagnostic, named_diagnostic

from .helpers import CFG, KEY, KEY_ID, established_problem, stub_engine, writer_link_problem

DATA = Path(__file__).resolve().parent.parent / "engine" / "data"
PREVIOUS_KEY = b"upgrade-test-key-0123456789abcdef"


def _dumps(r: VerificationResult) -> list[dict]:
    return [r.model_dump(), r.model_dump(mode="json"), r.model_dump(exclude_none=True), json.loads(r.model_dump_json())]


def test_a_diagnosed_result_records_its_rules_and_leaves_out_an_empty_diagnosis():
    r = verify(established_problem(), CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.ENTAILED and r.argument_rules == "argdiag-2" and r.named_diagnostics is None
    for dump in _dumps(r):
        assert dump["argument_rules"] == "argdiag-2" and "named_diagnostics" not in dump
    assert verify_signature(r, KEY)
    assert [t.stage for t in r.timings][-1] == "diagnose"


def test_an_undiagnosed_or_undecided_result_carries_no_rules_key_at_all():
    off = verify(established_problem(), CFG, signing_key=KEY, key_id=KEY_ID, diagnose=False)
    bad = verify(b"{not json", CFG, signing_key=KEY, key_id=KEY_ID)
    for r in (off, bad):
        assert r.argument_rules is None and r.named_diagnostics is None
        for dump in _dumps(r):
            assert "argument_rules" not in dump and "named_diagnostics" not in dump
    assert off.status is S.ENTAILED and bad.status is S.INVALID_FORMALIZATION


def test_signing_binds_the_diagnostics_and_the_rules(monkeypatch):
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), ("ARG-LINK-001", None)))
    r = verify(writer_link_problem(), CFG, signing_key=KEY, key_id=KEY_ID)
    assert [d.code for d in r.named_diagnostics] == ["ARG-AC-001", "ARG-LINK-001"] and verify_signature(r, KEY)
    assert all(d.claim_ids == ["c"] for d in r.named_diagnostics)        # a diagnostic is given the result's claim
    first, second = r.named_diagnostics
    tampered = [
        r.model_copy(update={"named_diagnostics": None}),
        r.model_copy(update={"named_diagnostics": [second]}),
        r.model_copy(update={"named_diagnostics": [first.model_copy(update={"severity": "info"}), second]}),
        r.model_copy(update={"named_diagnostics": [first.model_copy(update={"message": "nothing to see"}), second]}),
        r.model_copy(update={"argument_rules": None}),
        r.model_copy(update={"argument_rules": "argdiag-2/incomplete:budget"}),
    ]
    for t in tampered:
        assert not verify_signature(t, KEY)


def test_the_severity_cap_is_applied_before_signing_and_covers_only_its_codes(monkeypatch):
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), ("ARG-EQ-002", None)))
    r = verify(writer_link_problem(), CFG, signing_key=KEY, key_id=KEY_ID, severity_cap=("info", "ambiguous_translation"))
    by = {d.code: d for d in r.named_diagnostics}
    assert (by["ARG-AC-001"].severity, by["ARG-AC-001"].capped_from, by["ARG-AC-001"].cap_reason) == ("info", "warning", "ambiguous_translation")
    assert by["ARG-EQ-002"].severity == "warning" and by["ARG-EQ-002"].capped_from is None   # the ambiguity is its defect
    assert verify_signature(r, KEY)
    stripped = by["ARG-AC-001"].model_copy(update={"capped_from": None, "cap_reason": None})
    assert not verify_signature(r.model_copy(update={"named_diagnostics": [stripped, by["ARG-EQ-002"]]}), KEY)
    bad = verify(writer_link_problem(), CFG, severity_cap=("info", "because"))
    assert bad.argument_rules == "argdiag-2/incomplete:invalid_severity_cap" and bad.named_diagnostics is None and bad.status is S.ENTAILED


def test_a_diagnosis_never_changes_the_status_the_dependencies_or_the_engine_diagnostics(monkeypatch):
    plain = verify(writer_link_problem(), CFG, diagnose=False)
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), ("ARG-CONTRA-001", None)))
    named = verify(writer_link_problem(), CFG)
    for field in ("status", "premises_relied_on", "ungrounded_dependencies", "unverified_dependencies", "counterexample", "unsat_core"):
        assert getattr(named, field) == getattr(plain, field), field
    assert [d.code for d in named.diagnostics] == [d.code for d in plain.diagnostics]
    assert named.binding.binding_digest == plain.binding.binding_digest


@pytest.mark.parametrize("stub, reason", [
    (lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret detail")), "argdiag-2/incomplete:internal_runtimeerror"),
    (lambda *a, **k: ([named_diagnostic("ARG-EQ-001", derivation="ir_glosses", message="m")], "argdiag-2"), "argdiag-2/incomplete:not_engine_layer"),
    (lambda *a, **k: (["not a diagnostic"], "argdiag-2"), "argdiag-2/incomplete:not_engine_layer"),
    (lambda *a, **k: ([], "argdiag-7"), "argdiag-2/incomplete:unknown_rules"),
    (lambda *a, **k: ([], "argdiag-2/incomplete:budget"), "argdiag-2/incomplete:budget"),
])
def test_a_stage_that_fails_or_breaks_the_contract_is_recorded_incomplete_and_fires_nothing(monkeypatch, stub, reason):
    monkeypatch.setattr(argument_module, "diagnose", stub)
    r = verify(writer_link_problem(), CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.argument_rules == reason and r.named_diagnostics is None and r.status is S.ENTAILED
    assert "secret" not in r.model_dump_json() and verify_signature(r, KEY)


def test_more_diagnostics_than_the_bound_keep_the_first_and_mark_the_diagnosis_incomplete(monkeypatch):
    many = [named_diagnostic("ARG-LINK-001", assertion_ids=[f"p{i:02d}"], derivation="engine_recheck", message="m") for i in range(40)]
    monkeypatch.setattr(argument_module, "diagnose", lambda *a, **k: (many, "argdiag-2"))
    r = verify(writer_link_problem(), CFG)
    assert len(r.named_diagnostics) == 32 and r.argument_rules == "argdiag-2/incomplete:overflow_8"


def test_the_keywords_are_python_only():
    import inspect
    params = inspect.signature(verify).parameters
    assert params["diagnose"].kind is inspect.Parameter.KEYWORD_ONLY and params["diagnose"].default is True
    assert params["severity_cap"].kind is inspect.Parameter.KEYWORD_ONLY and params["severity_cap"].default is None
    assert "diagnose" not in SolverConfig.model_fields and "severity_cap" not in SolverConfig.model_fields


def _previous() -> dict:
    return json.loads((DATA / "release_0_4_0_signed_results.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", sorted(_previous()))
def test_a_result_of_the_previous_release_reserialises_byte_identically_and_is_never_current(case):
    entry = _previous()[case]
    old = VerificationResult.model_validate(entry["result"])
    assert old.versions.engine_version == "0.4.0" and old.argument_rules is None and old.named_diagnostics is None
    assert json.loads(old.model_dump_json()) == entry["result"] and verify_signature(old, PREVIOUS_KEY)
    problem = Problem.model_validate(entry["problem"])
    assert stale_reasons(old) and any("identity" in why or "versions" in why for why in stale_reasons(old))
    check = release_check(old, problem, signing_key=PREVIOUS_KEY, key_id="upgrade", required_limits=Limits.model_validate(entry["limits"]))
    assert not check.eligible and any(w.startswith("stale:") for w in check.reasons)
    assert any(w.startswith("argument diagnosis not computed") for w in check.reasons)
    fresh = verify(problem, SolverConfig.model_validate(entry["config"]), signing_key=PREVIOUS_KEY, key_id="upgrade")
    assert fresh.argument_rules == "argdiag-2" and stale_reasons(fresh) == []
    eligible = release_check(fresh, problem, signing_key=PREVIOUS_KEY, key_id="upgrade").eligible
    assert eligible is (case == "established_modus_ponens")   # the writer's own link stays an unresolved dependency


def test_a_named_diagnostic_on_a_result_parses_back_as_the_same_record(monkeypatch):
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None)))
    r = verify(writer_link_problem(), CFG, signing_key=KEY, key_id=KEY_ID)
    again = VerificationResult.model_validate_json(r.model_dump_json())
    assert again == r and isinstance(again.named_diagnostics[0], NamedDiagnostic) and verify_signature(again, KEY)
