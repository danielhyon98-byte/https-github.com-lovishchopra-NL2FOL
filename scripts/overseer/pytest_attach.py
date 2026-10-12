"""pytest plugin of the contained Overseer harness (``docs/OVERSEER_DESIGN.md`` section 13.3): a transfer auditor
attached to EVERY translator channel the test suite creates, so the full existing suite shows that the observer hook and
the live audit never change what the channel does.

    PYTHONPATH=src:scripts/overseer python -m pytest -q -p pytest_attach

Every ``TranslatorChannel`` constructed while the plugin is loaded gets one more observer, added after the observers the
test configured: the observer of a ``TransferAuditor`` of its own, whose keyring declares the channel's engine key under
the channel's key id and the usual ids (so the auditor verifies the channel's results), with inline replay that runs only
when asked (``eager=False``) and no shadow channel. The auditor journals every transfer, stores and verifies every
captured result and runs the live tier; nothing it decides reaches the test.

At the end of the session the plugin prints one line: channels attached, transfers journaled, observer failures (an
observer that raised; expected 0) and the auditors' internal failures (``OVS-AUDIT-001``; expected 0). With
``EPINOIC_ATTACH_REPORT=<path>`` it also writes these counts as JSON to that path (outside the repository).

Tests that assert the observer mechanics themselves (that a channel built with no observer has none, or opens no
capture) cannot pass with an observer added to every channel; the plugin leaves the channels of those tests alone and
says which (``SKIP_ATTACH`` below, by test node id prefix). The auditors' own shadow channels (key id ``overseer-run``)
are not channels the suite created and are left alone too. Every other test runs with an auditor attached. The plugin
holds no instruction text and configures no overseer agent.
"""
from __future__ import annotations

import json
import os
import threading
import weakref
from typing import Any

import pytest

ATTACH_SECRET = b"overseer-pytest-attach-secret-0123456789abcdef"
_OTHER_SECRET = b"overseer-pytest-attach-secret-alternate-01234567"
#: Tests whose subject is a channel's own observer list (no observer at all, exactly one, the auditor first): an observer
#: added to every channel would change what they assert about, so their channels are left alone. Every other test runs
#: with an auditor attached.
SKIP_ATTACH = (
    "tests/overseer/test_hook_noninterference.py::test_no_observer_calls_straight_through_without_a_capture",
    "tests/overseer/test_hook_noninterference.py::test_an_observer_must_be_callable",
    "tests/overseer/test_hook_equivalence.py::test_the_hook_and_the_manual_helper_give_identical_journals_and_audits",
    "tests/overseer/test_hook_hub.py::test_a_hub_without_observers_or_auditor_opens_unobserved_channels_and_refuses_overseer_methods",
    "tests/overseer/test_hook_hub.py::test_the_auditor_is_attached_first_and_journals_every_transfer",
)

_state: dict[str, Any] = {"channels": [], "auditors": [], "attached": 0, "skipped": 0, "shadow": 0, "current": "", "errors": []}
_lock = threading.Lock()
_original_init = None


def _keyring_for(channel: Any):
    from epinoic_logic.overseer import EngineKey, KeyRing
    key = channel.key
    secret = ATTACH_SECRET if key != ATTACH_SECRET else _OTHER_SECRET
    ids = {k: EngineKey(key) for k in ("hub", "channel", "default", "integrity", "t")}
    ids[channel.key_id] = EngineKey(key)
    return KeyRing(ids, secret)


def _attach(channel: Any) -> None:
    from epinoic_logic.overseer import RUN_KEY_ID, TransferAuditor
    if channel.key_id == RUN_KEY_ID:  # an auditor's own shadow channel (B5), not a channel the suite created
        _state["shadow"] += 1
        return
    if any(_state["current"].startswith(p) for p in SKIP_ATTACH):
        _state["skipped"] += 1
        return
    try:
        auditor = TransferAuditor(_keyring_for(channel), replay_mode="inline", eager=False, shadow="off")
        channel.add_observer(auditor.observer_for(channel))
    except Exception as exc:  # never break a test: record and carry on (reported at the end)
        _state["errors"].append(f"{type(exc).__name__}: {str(exc)[:200]}")
        return
    with _lock:
        _state["attached"] += 1
        _state["channels"].append(weakref.ref(channel))
        _state["auditors"].append(auditor)


def pytest_configure(config: Any) -> None:
    global _original_init
    from epinoic_logic.channel.bus import TranslatorChannel
    if _original_init is not None:
        return
    _original_init = TranslatorChannel.__init__

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _original_init(self, *args, **kwargs)
        _attach(self)
    __init__.__wrapped__ = _original_init  # type: ignore[attr-defined]
    TranslatorChannel.__init__ = __init__


def pytest_unconfigure(config: Any) -> None:
    global _original_init
    if _original_init is None:
        return
    from epinoic_logic.channel.bus import TranslatorChannel
    TranslatorChannel.__init__ = _original_init
    _original_init = None


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: Any) -> None:
    _state["current"] = item.nodeid


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: Any, nextitem: Any) -> None:
    _collect()


_totals = {"transfers_journaled": 0, "auditor_observer_failures": 0, "auditor_internal_failures": 0}


def _collect() -> None:
    """Fold the counts of the auditors and channels of the test that ended into the totals, then release them."""
    with _lock:
        auditors, channels = _state["auditors"], _state["channels"]
        _state["auditors"], _state["channels"] = [], []
    for a in auditors:
        for uid in a.channel_uids():
            try:
                _totals["transfers_journaled"] += len(a.journal(uid).events())
                _totals["auditor_internal_failures"] += sum(1 for _s, f in a._channels[uid].sticky if f.code == "OVS-AUDIT-001")
            except Exception:
                pass
        try:
            a.close()
        except Exception:
            pass
    for ref in channels:
        ch = ref()
        if ch is not None:
            _totals["auditor_observer_failures"] += sum(1 for _seq, name, _exc in ch.observer_errors if "TransferAuditor" in str(name))


def summary() -> dict:
    _collect()
    return {"channels_attached": _state["attached"], "channels_left_alone": _state["skipped"], "auditor_shadow_channels": _state["shadow"], **_totals,
            "attach_errors": len(_state["errors"])}


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    s = summary()
    terminalreporter.write_line("overseer pytest_attach: " + json.dumps(s, sort_keys=True))
    path = os.environ.get("EPINOIC_ATTACH_REPORT")
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(s, fh, indent=2, sort_keys=True)
