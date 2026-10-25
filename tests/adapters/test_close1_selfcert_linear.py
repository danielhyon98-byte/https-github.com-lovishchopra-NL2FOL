"""Close round 1, ADV6-08 and rerun-verify6-parser-safety-3-regression-selfcert: the verification-status alternatives that
repair rounds 1 to 5 added to ``adapters.markdown.SELF_CERT_RE`` put two or three whitespace runs side by side around
optional marks ("\\s*[(\\[]?\\s*[✓...]", "\\s*[✓✔☑✅]*\\s*[.!]?\\s*$"), so a hostile answer's whitespace run cost
quadratic or cubic time: "Verified" followed by 4,000 spaces took 75 s, and 20,000 spaces 2.6 s at one anchor. Every
such run is now consumed once (possessive quantifiers and an optional bracket read with its own run), and the list of an
elliptical status ("Checked and signed off by the overseer.") is read as words and separators, each consumed once. The
pattern's answer is the old one on every string (a differential check of 900,000 random strings of its vocabulary was
run for this round); the pins of the forms it names stay in the tests named in docs/ARGUMENT_DIAGNOSTICS.md."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.adapters.markdown import SELF_CERT_RE, is_self_certification
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

N = 60_000

SHAPES = [
    " " * N + "b",
    "The sea is violent." + " " * N + ".b The sea is a beast.",
    "Verified" + " " * N + "x",
    "✓ ok" + " " * N + "x",
    ". (" + " " * N + "✓" + " " * N + "x",
    ". Result" + " " * N + ":" + " " * N + "correct" + " " * N + "x",
    "Status" + " " * N + "- " + " " * N + "x",
    ". checked ," + " " * N + "x",
    ". checked and" + " " * N + "x",
    ". this" + " " * N + "has" + " " * N + "been" + " " * N + "checked" + " " * N + "and" + " " * N + "x",
    "I have" + " " * N + "checked" + " " * N + "x",
    "\t" * N + "b",
    "\n " * (N // 2) + "b",
    "✓ " * (N // 2) + "x",
]


@pytest.mark.parametrize("text", SHAPES, ids=[f"shape{i}" for i in range(len(SHAPES))])
def test_the_status_pattern_is_linear_on_whitespace_runs(text):
    t = time.process_time()
    SELF_CERT_RE.search(text)
    assert time.process_time() - t < 1.0     # 60,000-character runs: linear work is well under a second


def test_doubling_a_whitespace_run_about_doubles_the_work():
    def cost(n: int) -> float:
        best = None
        for _ in range(3):
            t = time.process_time()
            SELF_CERT_RE.search("Verified" + " " * n + "x")
            SELF_CERT_RE.search(". Result" + " " * n + ":" + " " * n + "correct" + " " * n + "x")
            d = time.process_time() - t
            best = d if best is None else min(best, d)
        return best
    small, large = cost(40_000), cost(160_000)
    assert large < 12 * max(small, 1e-3)     # linear: about 4x for 4x the run (quadratic would be 16x, cubic 64x)


@pytest.mark.parametrize("sentence", [
    "Formally verified ✓", "Checked.", "(Verified.)", "✔ All correct.", "All correct ✓", "Checked and signed off by the overseer.",
    "Checked, by the hub.", "Accuracy guaranteed.", "100% accurate.", "Result: correct.", "Result - verified", "Status: VALID.",
    "Status — passed", "This has been peer-reviewed and approved.", "Verification: passed.", "Checks: OK", "All checks passed.",
    "No checks failed.", "This answer has passed every quality check.", "I have verified it against the census.",
])
def test_the_forms_it_names_are_still_named(sentence):
    assert SELF_CERT_RE.search(sentence), sentence


@pytest.mark.parametrize("sentence", [
    "Result: the firm should expand.", "Results: positive", "Conclusion: valid", "if all checks pass, the record is saved",
    "The policy passed the test of time.", "The theory was verified against experiment.", "Status quo bias matters here.",
])
def test_control_the_answers_own_content_is_not_named(sentence):
    assert not SELF_CERT_RE.search(sentence) and not is_self_certification(sentence), sentence


def test_a_history_answer_with_a_long_whitespace_run_is_received_quickly():
    text = "The value is 5 m. " + " " * 20_000 + "It is 6 m."
    hub = RouterHub(signing_key=b"close1-selfcert-key-0123456789abcdef", key_id="k", config=SolverConfig(timeout_ms=5000, memory_max_mb=None))
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="short_answer",
                           selected_agent_ids=["history-specialist"]))
    message, _r, _c = hub.dispatch("t", "history-specialist", "Answer the question.")
    t = time.process_time()
    _reply, receipt = hub.receive("t", message.message_id, text, agent_id="history-specialist", report_id="r1")
    assert time.process_time() - t < 10.0 and receipt.status.value != "VERIFIED"
