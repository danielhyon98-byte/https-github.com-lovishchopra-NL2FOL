"""Check round of meaning-check stage 2a, the service's side: a deployment configures its labeller (``SELFCERT_LABEL``; here the
faithful fake, admitted in ``sim``) and leaves the process default as it is in production, ``UnconfiguredLabeller``. A clean
answer is then delivered exactly as under the faithful default, through the test double and through the overseer's real port.

Before this round the auditor's shadow replay labelled with the process default, raised INT-SELF-002 that the receipt does not
carry, failed the task audit (OVS-RCPT-004), and the real port refused every answer (``refuse_unresolved``, KIT-DL-008,
``no_deliverable_output``). Expected values fixed here, measured on the corpus: hi-s1 and hi-s3 deliver on both ports with no
refusal, and hi-s2 is refused on both ports for the same reasons under the configured labeller as under the faithful default
(KIT-DL-002; the real port adds KIT-DL-008), so the configuration changes no decision. Like every service test, it needs the KIT
step's pin of contract 0.10 in COMPATIBILITY.json; until then its handshake fails with KIT-HS-002."""
from __future__ import annotations

import pytest

from epinoic_logic.selfcert_label import labellers as L

from . import test_turn_checker as T
from .helpers import RealPort, RecordingPort

EXPECTED = {
    ("double", "hi-s1"): ("deliver", [], None), ("real", "hi-s1"): ("deliver", [], None),
    ("double", "hi-s3"): ("deliver", [], None), ("real", "hi-s3"): ("deliver", [], None),
    ("double", "hi-s2"): ("refuse_unresolved", ["KIT-DL-002"], None),
    ("real", "hi-s2"): ("refuse_unresolved", ["KIT-DL-002", "KIT-DL-008"], "no_deliverable_output"),
}


def _decide(kind: str, name: str, **env):
    if kind == "real":
        pytest.importorskip("epinoic_overseer", reason="the real port is the overseer sub-project's", exc_type=ModuleNotFoundError)
    v, _port = T._run([name], port=RecordingPort() if kind == "double" else RealPort(), **env)
    return v["delivery"]["decision"], list(v["delivery"]["reasons"]), v["overseer"]["refusal"]


@pytest.mark.real_labeller
@pytest.mark.parametrize("kind,name", sorted(EXPECTED))
def test_a_configured_labeller_with_the_production_default_decides_as_the_faithful_default(kind, name):
    assert type(L.default_labeller()).__name__ == "UnconfiguredLabeller"
    assert _decide(kind, name, SELFCERT_LABEL="faithful") == EXPECTED[(kind, name)]


@pytest.mark.parametrize("kind,name", sorted(EXPECTED))
def test_the_faithful_default_control(kind, name):
    assert type(L.default_labeller()).__name__ == "ReaderBackedLabeller"
    assert _decide(kind, name) == EXPECTED[(kind, name)]
