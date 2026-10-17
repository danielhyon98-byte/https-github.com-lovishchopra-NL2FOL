"""Readiness: one refusal per required part (each KIT-HS code), what the service reports without the overseer or the
router, and the Worker's handshake rules on capabilities responses (version mismatch, each part missing)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from epinoic_logic.integration.capabilities import build_capabilities
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.handshake import evaluate
from epinoic_logic.integration.preflight import Probes, run_preflight
from epinoic_logic.integration.runtime import build_runtime
from epinoic_logic.integration.selftest import run_selftest
from tests.integration.helpers import FixtureProbes, RecordingPort, hello, settings

SRC = str(Path(__file__).resolve().parents[2] / "src")


def _code(fn) -> str:
    with pytest.raises(IntegrationError) as exc:
        fn()
    return exc.value.code


def _raise(code):
    def f(*a, **k):
        raise IntegrationError(code, "removed by the test")
    return f


def test_with_every_part_present_the_preflight_passes_and_reports_the_router_absent():
    facts = run_preflight(settings(), FixtureProbes())
    assert facts.router_caps.attached is False and facts.router_caps.required is False
    assert facts.router_caps.floor.name == "minimum-oversight-floor/1"
    assert facts.modes == ("single", "duplicate")  # no combinator is connected: the mode combined is omitted
    assert facts.stem.branches == ["computer_science", "mathematics", "sciences"]
    assert "secret" not in repr(facts.keys) and "33" * 32 not in repr(facts)


@pytest.mark.parametrize("probe,code", [
    ("versions", "KIT-HS-002"), ("stem", "KIT-HS-005"), ("subject_map", "KIT-HS-010"), ("specialist_contracts", "KIT-HS-011"),
])
def test_each_code_part_removed_alone_gives_its_code(probe, code):
    assert _code(lambda: run_preflight(settings(), FixtureProbes(**{probe: _raise(code)}))) == code


def test_on_this_tree_the_named_policies_of_contract_0_3_are_missing():
    """This pre-build sits on contract 0.2: the real probe refuses with KIT-HS-006 (phase 2 merges contract 0.3)."""
    try:
        from epinoic_logic.engine.policies import NAMED_POLICIES  # noqa: F401
    except ImportError:
        assert _code(lambda: run_preflight(settings(), FixtureProbes(missing="named_policies"))) == "KIT-HS-006"
    else:  # pragma: no cover - after phase 2's merge the allowlist is present and the real probe passes
        assert run_preflight(settings(), FixtureProbes(missing="named_policies")).named_policies == ("joint", "linear", "nonlinear")


def test_without_an_overseer_port_adapter_the_service_refuses_with_kit_hs_007():
    s = settings(OVERSEER_PORT="epinoic_overseer_absent_for_the_test.port")
    assert _code(lambda: run_preflight(s, FixtureProbes(missing="overseer"))) == "KIT-HS-007"


@pytest.mark.parametrize("bad_hello", [hello(port_version="2.0"), hello(replay_mode="inline"), hello(inline_final_release=True),
                                       hello(pack_digests=[]), hello(key_ids=["overseer-run"])])
def test_an_out_of_contract_overseer_hello_is_overseer_unavailable(tmp_path, monkeypatch, bad_hello):
    mod = tmp_path / "fake_overseer_port_for_test.py"
    mod.write_text("import json\nHELLO = json.loads(%r)\nclass _P:\n    def hello(self):\n        return HELLO\n"
                   "def connect(config):\n    return _P()\n" % __import__("json").dumps(bad_hello))
    monkeypatch.syspath_prepend(str(tmp_path))
    s = settings(OVERSEER_PORT="fake_overseer_port_for_test")
    assert _code(lambda: run_preflight(s, FixtureProbes(missing="overseer"))) == "KIT-HS-007"


_ADAPTER = """import json
from epinoic_logic.integration.errors import IntegrationError
GOOD = json.loads({good!r})
BAD = json.loads({bad!r})
class _P:
    calls = 0
    def hello(self):
        _P.calls += 1
{hello}
def connect(config):
{connect}
"""


@pytest.mark.parametrize("name,connect,hello_body,inner", [
    ("adapter_connect_refuses", "    raise IntegrationError('KIT-OP-001', 'the adapter refused')", "        return GOOD", "KIT-OP-001"),
    ("adapter_connect_exits", "    raise SystemExit(3)", "        return GOOD", "SystemExit"),
    ("adapter_hello_raises", "    return _P()", "        raise RuntimeError('hello bug')", "RuntimeError"),
    ("adapter_hello_refused", "    return _P()", "        return BAD", "KIT-OP-002"),
])
def test_every_failure_inside_the_overseer_adapter_is_overseer_unavailable_with_its_inner_code(tmp_path, monkeypatch, name, connect, hello_body, inner):
    """Start-up names KIT-HS-007 whatever the adapter does (an inner KIT code of its own included), the inner code or
    exception type kept in the detail, never a traceback and never another start-up code."""
    (tmp_path / f"{name}.py").write_text(_ADAPTER.format(good=__import__("json").dumps(hello()), bad=__import__("json").dumps(hello(port_version="2.0")),
                                                       hello=hello_body, connect=connect))
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(IntegrationError) as exc:
        run_preflight(settings(OVERSEER_PORT=name), FixtureProbes(missing="overseer"))
    assert exc.value.code == "KIT-HS-007" and inner in exc.value.detail, exc.value.detail


def test_the_overseer_hello_is_validated_once_and_that_hello_is_the_one_used(tmp_path, monkeypatch):
    """A hello that changes between two calls can no longer surface as a KIT-OP code at start-up: load_port returns the
    hello it validated, and the preflight never asks again."""
    body = "        return GOOD if _P.calls == 1 else BAD"
    (tmp_path / "adapter_changing_hello.py").write_text(_ADAPTER.format(good=__import__("json").dumps(hello()), bad=__import__("json").dumps(hello(port_version="2.0")),
                                                                      hello=body, connect="    return _P()"))
    monkeypatch.syspath_prepend(str(tmp_path))
    facts = run_preflight(settings(OVERSEER_PORT="adapter_changing_hello"), FixtureProbes(missing="overseer"))
    assert facts.overseer.port_version == "1.0" and type(facts.overseer_port).calls == 1


@pytest.mark.parametrize("overrides,code", [
    ({"SERVICE_TOKEN": None}, "KIT-HS-008"), ({"SERVICE_TOKEN": "short"}, "KIT-HS-008"),
    ({"SIGNING_KEY": None}, "KIT-HS-008"), ({"SIGNING_KEY": "aa" * 8}, "KIT-HS-008"), ({"SIGNING_KEY": "zz"}, "KIT-HS-008"),
    ({"VERDICT_KEY": None}, "KIT-HS-008"), ({"VERDICT_KEY": "11" * 32}, "KIT-HS-008"),
    ({"OVERSEER_SECRET": None}, "KIT-HS-007"), ({"OVERSEER_SECRET": "11" * 32}, "KIT-HS-007"), ({"OVERSEER_SECRET": "22" * 32}, "KIT-HS-007"),
    ({"TRANSLATION_PROVIDER": "anthropic"}, "KIT-HS-009"), ({"TRANSLATION_PROVIDER": "mystery"}, "KIT-HS-009"),
    ({"PROFILE": "integration", "SERVICE_ENV": "staging"}, "KIT-HS-009"),
    ({"PROFILE": "integration", "SERVICE_ENV": "production", "TRANSLATION_PROVIDER": "anthropic"}, "KIT-HS-009"),
    ({"SERVICE_ENV": "development"}, "KIT-HS-012"), ({"PROFILE": "integration", "SERVICE_ENV": "sim"}, "KIT-HS-012"),
    ({"PROFILE": "integration", "SERVICE_ENV": "development", "SIM_EVIDENCE_DIR": "/nonexistent-tap"}, "KIT-HS-012"),
    ({"PROFILE": "engine"}, "KIT-HS-012"), ({"SERVICE_ENV": "qa"}, "KIT-HS-012"),
    ({"MAX_BODY_BYTES": "1024"}, "KIT-HS-013"), ({"MAX_CONCURRENCY": "0"}, "KIT-HS-013"), ({"RATE_PER_MINUTE": "x"}, "KIT-HS-013"),
    ({"CHECKS_MIN_MS": "70000"}, "KIT-HS-016"), ({"CHECKS_MIN_MS": "500"}, "KIT-HS-016"), ({"CHECKS_MIN_MS": "200000", "CHECKS_MAX_MS": "300000"}, "KIT-HS-016"),
])
def test_each_configuration_part_missing_or_wrong_alone_gives_its_code(overrides, code):
    assert _code(lambda: run_preflight(settings(**overrides), FixtureProbes())) == code


def test_the_sim_profile_binds_loopback_only():
    assert _code(lambda: run_preflight(settings(host="0.0.0.0"), FixtureProbes())) == "KIT-HS-012"


def test_the_selftest_failing_refuses_with_kit_hs_004(monkeypatch):
    import epinoic_logic.integration.selftest as st
    monkeypatch.setattr(st, "EXPECTED", {k: {**v, "status": "UNKNOWN"} for k, v in st.EXPECTED.items()})
    assert _code(lambda: build_runtime(settings(), probes=FixtureProbes())) == "KIT-HS-004"


def test_the_service_entry_on_this_tree_refuses_with_one_line_and_exit_2():
    env = {k: v for k, v in os.environ.items() if not k.startswith("EPINOIC_")}
    env.update({"PYTHONPATH": SRC, "EPINOIC_PROFILE": "integration-sim"})
    out = subprocess.run([sys.executable, "-m", "epinoic_logic.integration", "preflight"], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 2
    lines = (out.stdout + out.stderr).strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith(("KIT-HS-006 named_policies_unavailable", "KIT-HS-008 signing_unconfigured"))
    assert "Traceback" not in out.stderr


# ----------------------------------------------------------------------------------------------- capabilities


def _caps(**probe_kw) -> dict:
    facts = run_preflight(settings(), FixtureProbes(**probe_kw))
    return build_capabilities(facts, run_selftest(facts.keys.engine_key, facts.keys.engine_key_id))


def test_capabilities_report_every_port_and_no_secret():
    caps = _caps()
    text = __import__("json").dumps(caps)
    for secret in ("11" * 32, "22" * 32, "33" * 32, "integration-test-token"):
        assert secret not in text
    assert caps["ports"]["router"] == {"version": "1.0", "required": False, "attached": False, "identity": None, "refusal": None,
                                       "floor": {"name": "minimum-oversight-floor/1", "rules_sha256": caps["ports"]["router"]["floor"]["rules_sha256"]}}
    assert caps["ports"]["overseer"]["inline_final_release"] is False and caps["ports"]["overseer"]["replay_mode"] == "process"
    assert caps["ports"]["translation"] == {"provider": "fixture", "tier": "cheapest", "live": False, "reviewer": "none"}
    assert caps["ports"]["combinator"]["available"] is False and "combined" not in caps["ports"]["checks"]["modes"]
    assert caps["selftest"]["passed"] is True and len(caps["selftest"]["digests"]) == 3
    assert evaluate(caps, worker_env="sim").ok


def test_capabilities_report_an_attached_router_with_its_identity(tmp_path, monkeypatch):
    from tests.integration.helpers import write_router_module
    write_router_module(tmp_path, monkeypatch, "router_for_caps_test")
    facts = run_preflight(settings(FLASH_ROUTER="router_for_caps_test"), FixtureProbes())
    caps = build_capabilities(facts, run_selftest(facts.keys.engine_key, facts.keys.engine_key_id))
    r = caps["ports"]["router"]
    assert r["attached"] is True and r["identity"]["name"] == "test-flash-router" and r["refusal"] is None
    assert evaluate(caps, worker_env="sim").ok  # the router changes nothing the Worker requires


def test_a_router_with_an_out_of_contract_hello_is_reported_absent_never_required(tmp_path, monkeypatch):
    mod = tmp_path / "bad_router_for_test.py"
    mod.write_text("def hello():\n    return '{\"schema\": \"x\"}'\ndef plan(request_json):\n    return '{}'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    facts = run_preflight(settings(FLASH_ROUTER="bad_router_for_test"), FixtureProbes())
    assert facts.router_caps.attached is False and facts.router_caps.refusal == "KIT-RT-015"


def _mutated(caps, path, value):
    import copy
    c = copy.deepcopy(caps)
    node = c
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return c


@pytest.mark.parametrize("path,value,code", [
    (("protocol",), "epinoic.integration.v2", "KIT-HS-001"),
    (("schema",), "epinoic.integration.capabilities.v2", "KIT-HS-001"),
    (("versions", "engine"), "0.5.0", "KIT-HS-002"),
    (("versions", "contract"), "0.3", "KIT-HS-002"),
    (("selftest", "passed"), False, "KIT-HS-004"),
    (("ports", "checks", "stem", "branches"), ["mathematics", "sciences"], "KIT-HS-005"),
    (("ports", "checks", "named_policies"), ["linear", "nonlinear"], "KIT-HS-006"),
    (("ports", "overseer", "mode"), "sidecar", "KIT-HS-007"),
    (("ports", "translation", "live"), True, "KIT-HS-009"),
    (("subject_map", "sha256"), "0" * 64, "KIT-HS-010"),
    (("ports", "specialist", "accepted"), [{"result": "epinoic.specialist-turn-result.v1", "runtime": "epinoic.specialist-runtime.v0.1.0", "log": "epinoic.specialist-turn-log.v1"}], "KIT-HS-011"),
    (("service_env",), "development", "KIT-HS-012"),
    (("limits", "max_body_bytes"), 100000, "KIT-HS-013"),
    (("limits", "checks_min_ms"), 120000, "KIT-HS-016"),
])
def test_the_worker_handshake_refuses_each_mismatch_with_its_code(path, value, code):
    out = evaluate(_mutated(_caps(), path, value), worker_env="sim")
    assert (out.ok, out.code) == (False, code)
    assert out.raw_code == "kit_hs_mismatch"


def test_the_hosted_handshake_requires_a_live_provider_and_base_p_fails_the_timing_invariant():
    caps = _caps()
    staging = _mutated(caps, ("service_env",), "staging")
    assert evaluate(staging, worker_env="staging").code == "KIT-HS-009"
    assert evaluate(caps, worker_env="sim", base="P").code == "KIT-HS-016"  # 20 + 3 + 5 + 2 > 25 s
