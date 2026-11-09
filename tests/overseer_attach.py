"""The overseer attached in the translator's own tests, through the overseer's public package API only.

The overseer is a separate sub-project (``overseer/``, package ``epinoic_overseer``) that depends on the translator; the
translator never imports it, and after the documented split the translator is a project of its own whose suite runs
with at most the overseer installed as a package. A translator test that attaches the overseer (a transfer audit, the
delivery policy, the overseer's table of the codes the translator raises) reaches it only through this module, or, for a
public module of the overseer this module does not name, with ``pytest.importorskip(<module>, reason=REASON)`` inside
the test that needs it:

* every function here imports the package with ``pytest.importorskip`` first (:func:`overseer`), so a test that needs
  the overseer is SKIPPED, with :data:`REASON`, where the overseer is not installed: never a collection error and never
  a failure, and the tests beside it, which need only the translator, still run;
* it names only the package's public API (its top-level exports, and the public modules in :data:`PUBLIC_MODULES`),
  never the overseer's test package (``overseer_tests``) or a private name.

It sat in ``tests/channel/`` while only the channel's tests used it; since the other packages' tests use it too (the
handoff fixer of the architecture review after arena round 8) it is shared from ``tests/``.

``tests/channel/test_without_the_overseer.py`` holds the rule: for the core packages' tests (channel, integrity,
translate, engine, service) with the overseer off the path they collect and every test that attaches it is skipped,
with the overseer installed without its tests those tests pass, and no core test reaches the overseer otherwise; for the
whole translator suite, no module fails to collect, every import of the overseer is guarded, no test reaches its test
package or a private name, and the tests that failed without it before that fix now pass or are skipped with
:data:`REASON`.

The keys and the solver configuration are the values the overseer's own suite uses, so the hub signs and the auditor
verifies exactly as there. Nothing here calls a model or the network.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

import pytest

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

#: Why a test that attaches the overseer is skipped where the overseer is not installed.
REASON = ("the overseer sub-project (package epinoic_overseer) is not installed; the translator's suite runs without it "
          "and this test attaches it")
#: The overseer's public modules this module may import: the package (its top-level exports) and the public table of
#: everything the translator emits (``emitted``, which the package does not re-export).
PUBLIC_MODULES = ("epinoic_overseer", "epinoic_overseer.emitted")

#: The engine key the hub signs with and the auditor verifies with (the overseer suite's test key).
KEY = b"overseer-test-engine-key-0123456789abcdef"
#: The overseer's own secret (the auditor signs only under subkeys derived from it).
SECRET = b"overseer-test-secret-0123456789abcdef-0123"
#: The solver configuration of the hub's channels, the one the auditor replays under.
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
#: Every key id an engine result of these tests is signed under.
ENGINE_IDS = ("hub", "channel", "default", "integrity", "t")
#: The ``translator_version`` of fixture translations, declared hand-built to the auditor as an operator declares them.
HAND_BUILT_TRANSLATORS = ("test", "harness")


def overseer() -> ModuleType:
    """The overseer package, or SKIP the calling test where it is not installed."""
    return pytest.importorskip("epinoic_overseer", reason=REASON)


def overseer_module(name: str) -> ModuleType:
    """A public module of the overseer (one of :data:`PUBLIC_MODULES`), or SKIP the calling test where the overseer is
    not installed. Any other name is refused: the tests never reach a private or test module of the overseer."""
    if name not in PUBLIC_MODULES:
        raise ValueError(f"not a public module of the overseer this module reads: {name!r}")
    return pytest.importorskip(name, reason=REASON)


def make_keyring() -> Any:
    """The auditor's key ring: :data:`KEY` under every engine key id, and :data:`SECRET`."""
    ov = overseer()
    return ov.KeyRing({kid: ov.EngineKey(KEY) for kid in ENGINE_IDS}, SECRET)


def make_auditor(**kw: Any) -> Any:
    """A transfer auditor as the overseer's own suite builds one: replays inline and says so (contained testing, so the
    FINAL audit's inline release is configured explicitly), eager, every transfer shadowed, the fixture translators
    declared hand-built. ``kw`` overrides any of these (``keyring=`` replaces the key ring)."""
    ov = overseer()
    opts: dict[str, Any] = dict(replay_mode="inline", eager=True, shadow="always", hand_built_translators=HAND_BUILT_TRANSLATORS,
                                inline_final_release=kw.get("replay_mode", "inline") != "process")
    opts.update(kw)
    keyring = opts.pop("keyring", None) or make_keyring()
    return ov.TransferAuditor(keyring, **opts)


def observed_channel(auditor: Any, plan: WorkPlan, *, key_id: str = "hub", config: SolverConfig = CFG, **kw: Any) -> TranslatorChannel:
    """A channel whose transfers ``auditor`` observes through the channel's own hook (``add_observer``), as
    ``RouterHub(auditor=...)`` attaches it; the audit of its transfers is ``auditor.audit(channel.channel_uid)``."""
    overseer()
    channel = TranslatorChannel(plan, signing_key=KEY, key_id=key_id, config=config, **kw)
    channel.add_observer(auditor.observer_for(channel))
    return channel


def findings(audit: Any, code: str) -> list:
    """The findings of ``audit``'s signed report that carry ``code``."""
    return [f for f in audit.report.findings if f.code == code]
