"""Session set-up of the translator's suite for the meaning label (meaning-check design 3.3 and 3.4; stage 2a, interface (a)).

1. **The faithful fake as the default labeller.** ``pytest_configure`` installs :class:`ReaderBackedLabeller` through the one
   switch, ``selfcert_label.set_default_labeller``, before any fixture of any scope runs, and sets ``EPINOIC_ARENA_LABELLER`` to
   ``faithful`` (the arena's labeller). The faithful fake names exactly what the rule reader names, so every delivery decision
   of the suite is the reader's, as before the label was wired. It is never a label measurement. ``pytest_unconfigure`` puts
   both back.
2. **The real default on request.** A test marked ``real_labeller`` runs with the production default (the unconfigured
   labeller: every answer the reader passes is withheld, ``not-configured``) and without ``EPINOIC_ARENA_LABELLER``; a fixture
   of a wider scope that needs the real default asks for it explicitly (``selfcert_label.using_default_labeller(None)`` or an
   ``UnconfiguredLabeller()`` passed as its labeller), because this restore is function-scoped.
3. **T24 over everything the suite produces.** One session-level hook records every transmission receipt, delivery receipt,
   delivered answer and channel event made while a test of this tree is set up, run or torn down, and checks each with
   ``selfcert_label.check_t24`` when that phase ends: a violation fails the test that produced it (an error in its set-up or
   tear-down when a fixture produced it). A test that builds a violating record on purpose carries the marker
   ``t24_expected_violation`` and must itself assert that ``check_t24`` detects the violation.

The shared calls of the label package (its in-flight table and cache of successes) are emptied before each test, so no test sees
another's labels. Nothing here calls a provider or opens a connection.
"""
from __future__ import annotations

import collections
import os

import pytest

from epinoic_logic.selfcert_label import labellers as _labellers
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller
from epinoic_logic.selfcert_label.t24 import T24_EXPECTED_VIOLATION, check_t24

#: The arena's labeller switch (its value here: the faithful fake).
ARENA_LABELLER_ENV = "EPINOIC_ARENA_LABELLER"
#: The marker of a test that runs with the production default labeller.
REAL_LABELLER = "real_labeller"

_SESSION: dict = {}
_OVERSEER_REASON = "the overseer sub-project (package epinoic_overseer) is not installed: T24 reads the translator's records only"


# ---------------------------------------------------------------------------------------------------------- 1. the default
def pytest_configure(config):
    config.addinivalue_line("markers", f"{REAL_LABELLER}: run with the production default labeller (UnconfiguredLabeller) and no "
                                       f"{ARENA_LABELLER_ENV}, in place of the suite's faithful fake")
    config.addinivalue_line("markers", f"{T24_EXPECTED_VIOLATION}: the test builds a record that violates T24 on purpose and "
                                       "asserts that selfcert_label.check_t24 detects it")
    if "labeller" in _SESSION:
        return  # configured once per process
    _SESSION["labeller"] = _labellers.set_default_labeller(ReaderBackedLabeller())
    _SESSION["env"] = os.environ.get(ARENA_LABELLER_ENV)
    os.environ[ARENA_LABELLER_ENV] = "faithful"
    _T24.install()


def pytest_unconfigure(config):
    if "labeller" not in _SESSION:
        return
    _T24.uninstall()
    _labellers.set_default_labeller(_SESSION.pop("labeller"))
    env = _SESSION.pop("env")
    if env is None:
        os.environ.pop(ARENA_LABELLER_ENV, None)
    else:
        os.environ[ARENA_LABELLER_ENV] = env


# ---------------------------------------------------------------------------------------------------------- 2. per test
@pytest.fixture(autouse=True)
def _selfcert_label_per_test(request):
    """Empties the label package's shared calls; for a ``real_labeller`` test, the production default and no arena labeller."""
    _labellers.clear_shared_calls()
    if request.node.get_closest_marker(REAL_LABELLER) is None:
        yield
        return
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv(ARENA_LABELLER_ENV, raising=False)
        with _labellers.using_default_labeller(None):
            yield


# ---------------------------------------------------------------------------------------------------------- 3. T24
class _T24Hook:
    """Records what the suite produces while a phase of a test of this tree runs, and checks it when the phase ends."""

    #: How many specialist payload digests by message id, and delivery receipts by id, are kept for the delivered-answer rule.
    MEMORY = 50_000

    def __init__(self):
        self.active = False
        self.produced: list = []
        self.payloads: "collections.OrderedDict[str, set]" = collections.OrderedDict()
        self.receipts: "collections.OrderedDict[str, object]" = collections.OrderedDict()
        self._patched: list = []
        self.checked: "collections.Counter[str]" = collections.Counter()

    # -- recording
    def _targets(self):
        from epinoic_logic.channel.contracts import TransmissionReceipt
        from epinoic_logic.channel.events import ChannelEvent
        out = [(TransmissionReceipt, True), (ChannelEvent, False)]
        # the overseer through its public package only, guarded as tests/overseer_attach.py guards it: where it is not
        # installed its records are not produced either, and an overseer that is installed but fails to import still fails
        try:
            ovs = pytest.importorskip("epinoic_overseer", reason=_OVERSEER_REASON, exc_type=ModuleNotFoundError)
        except pytest.skip.Exception:
            return out
        return out + [(ovs.DeliveryReceipt, True), (ovs.DeliveredAnswer, True)]

    def install(self) -> None:
        for cls, pydantic in self._targets():
            original_init = cls.__dict__.get("__init__")
            base_init = cls.__init__

            def init(obj, *a, _base=base_init, **k):
                _base(obj, *a, **k)
                if self.active:
                    self._record(obj)
            cls.__init__ = init
            self._patched.append((cls, "__init__", original_init))
            if pydantic:
                original_copy = cls.__dict__.get("model_copy")
                base_copy = cls.model_copy

                def model_copy(obj, *a, _base=base_copy, **k):
                    out = _base(obj, *a, **k)
                    if self.active:
                        self._record(out)
                    return out
                cls.model_copy = model_copy
                self._patched.append((cls, "model_copy", original_copy))

    def uninstall(self) -> None:
        for cls, name, original in reversed(self._patched):
            if original is None:
                delattr(cls, name)
            else:
                setattr(cls, name, original)
        self._patched.clear()

    def _record(self, obj) -> None:
        self.produced.append(obj)
        if type(obj).__name__ == "ChannelEvent":
            mid, digest = getattr(obj, "message_id", None), getattr(obj, "payload_sha256", None)
            if mid and digest:
                self.payloads.setdefault(mid, set()).add(digest)
                self.payloads.move_to_end(mid)
                while len(self.payloads) > self.MEMORY:
                    self.payloads.popitem(last=False)

    # -- checking
    def begin(self) -> None:
        self.produced = []
        self.active = True

    def end(self) -> list:
        self.active = False
        produced, self.produced = self.produced, []
        return produced

    def violations(self, produced: list) -> list[str]:
        out: list[str] = []
        for obj in produced:
            if type(obj).__name__ == "DeliveryReceipt":
                rid = getattr(obj, "receipt_id", None)
                if rid:
                    self.receipts[rid] = obj
                    self.receipts.move_to_end(rid)
                    while len(self.receipts) > self.MEMORY:
                        self.receipts.popitem(last=False)
        for obj in produced:
            self.checked[type(obj).__name__] += 1
            kwargs = {}
            if type(obj).__name__ == "DeliveredAnswer":
                kwargs["specialist_payload_sha256"] = self.payloads.get(getattr(obj, "message_id", None) or "")
                kwargs["delivery_receipt"] = self.receipts.get(getattr(obj, "delivery_receipt_id", None) or "")
            for v in check_t24(obj, **kwargs):
                out.append(f"{type(obj).__name__}: {v}")
        return list(dict.fromkeys(out))

    def phase(self, item, when: str):
        self.begin()
        try:
            result = yield
        finally:
            produced = self.end()
        found = self.violations(produced)
        if found and item.get_closest_marker(T24_EXPECTED_VIOLATION) is None:
            raise AssertionError(f"T24 ({when}): {len(found)} violation(s) in what this test produced:\n  " + "\n  ".join(found[:20]))
        return result


_T24 = _T24Hook()


def pytest_terminal_summary(terminalreporter):
    if _T24.checked:
        counts = ", ".join(f"{n} {k}" for k, n in sorted(_T24.checked.items()))
        terminalreporter.write_line(f"T24 (selfcert_label.check_t24): checked {counts}")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    return (yield from _T24.phase(item, "set-up"))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    return (yield from _T24.phase(item, "call"))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    return (yield from _T24.phase(item, "tear-down"))
