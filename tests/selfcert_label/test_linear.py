"""T23: the label's code is linear in its input (not a stress test, no ``stress`` marker). On each hostile family of the c3b
design 2.9 (``tests/selfcert/test_linear.py``) at 8 KiB and 32 KiB, building the input and validating a reply that gates every
sentence grows at most six-fold and the 32 KiB run stays within that file's 1.5 s bound (the median of five runs, caches
emptied: ``tests/timing.py``). A 200 kB hostile answer goes through ``build_input``, the anchoring map and every exemption frame,
and a 200 kB hostile reply (and a 32 KiB one, the largest a reply may be) through ``validate_reply``: each grows at most six-fold
from a quarter of that length, and stays within the T23 bound scaled to its length (1.5 s per 32 KiB).
The rule reader the faithful fake calls is timed by the reader's own test, not here."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.selfcert_label import build_input, validate_reply
from epinoic_logic.selfcert_label.anchor import locate, visible_map
from epinoic_logic.selfcert_label.exempt import decide
from epinoic_logic.selfcert_label.fakes import TEST_KEY, reply_json
from epinoic_logic.selfcert_label.scope import Segment, own_scope

from ..selfcert.test_linear import FAMILIES
from ..timing import measure

BOUND = 1.5
#: The T23 bound scaled to a 200 kB input (1.5 s per 32 KiB).
BOUND_200K = BOUND * 200_000 / (32 * 1024)
REQ = {"subject": "physics", "task_type": "marking_feedback", "user_input": "Mark this.",
       "supplied_texts": [{"title": "Data booklet", "text": "g = 9.8 m/s^2"}],
       "items": [{"item_id": "1", "text": "Verify the value.", "command_term": "verify"}]}


def _label_once(text: str, prompt) -> int:
    inp = build_input(text, REQ, key=TEST_KEY, prompt_path=prompt)
    n = 0
    for req in inp.requests:
        gated = {it.id: [((it.text[:20].strip() or it.text)[:300], "CHECK")] for it in req.items
                 if it.segment is not None and it.text.strip()}
        raw = reply_json(req, gated)
        if len(raw.encode("utf-8")) > 32 * 1024:
            raw = reply_json(req)
        v = validate_reply(raw, "end_turn", req, inp.scope)
        n += len(v.spans) + len(v.exemptions)
    return n


@pytest.fixture(scope="module")
def prompt(tmp_path_factory):
    p = tmp_path_factory.mktemp("prompt") / "prompt.md"
    p.write_text("Fixed system text of the selfcert-label test suite.\n", encoding="utf-8")
    return p


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_a_hostile_answer_is_labelled_in_linear_time(family, prompt):
    make = FAMILIES[family]
    small = measure(lambda: _label_once(make(8 * 1024) + " ", prompt), BOUND, label=f"label {family} at 8 KiB")
    large = measure(lambda: _label_once(make(32 * 1024) + " ", prompt), BOUND, label=f"label {family} at 32 KiB")
    assert large.holds, large
    ratio = sorted(large.wall)[len(large.wall) // 2] / max(sorted(small.wall)[len(small.wall) // 2], 0.05)
    assert ratio <= 6, (family, ratio, small, large)


HOSTILE_200K = {
    "letter-spaced": ("V E R I F I E D " * 12_500),
    "quotation marks": '"' * 200_000,
    "delimiters": "<<<" * 66_000 + "⟦" * 2000,
    "zero-width": "a​" * 100_000,
    "one long token": "a" * 200_000,
    "short sentences": "Ok. " * 50_000,
}


def _grows_linearly(make, label: str) -> None:
    """``make(fraction)`` builds the call on a quarter (0.25) or all (1.0) of the input: the whole stays within the scaled bound
    and costs at most six times the quarter."""
    small = measure(make(0.25), BOUND_200K, repeat=3, label=f"{label} at 50 kB")
    large = measure(make(1.0), BOUND_200K, repeat=3, label=f"{label} at 200 kB")
    assert large.holds, large
    ratio = sorted(large.wall)[len(large.wall) // 2] / max(sorted(small.wall)[len(small.wall) // 2], 0.05)
    assert ratio <= 6, (label, ratio, small, large)


@pytest.mark.parametrize("name", sorted(HOSTILE_200K))
def test_a_200_kb_hostile_answer_through_build_input(name, prompt):
    def make(fraction):
        text = HOSTILE_200K[name][:int(200_000 * fraction)]
        return lambda: build_input(text, REQ, key=TEST_KEY, prompt_path=prompt)
    _grows_linearly(make, f"build_input {name}")


@pytest.mark.parametrize("name", sorted(HOSTILE_200K))
def test_the_anchoring_map_and_every_exemption_frame_are_linear_on_200_kb(name):
    scope = own_scope("x", REQ)

    def make(fraction):
        text = HOSTILE_200K[name][:int(200_000 * fraction)]
        seg = Segment(0, 1, 1, "paragraph 1, sentence 1", 0, len(text), text, tuple((i, i + 1) for i in range(len(text))))

        def run():
            vm = visible_map(text, ((0, 3),))
            locate("VERIFIED", vm)
            return decide(seg, 0, min(5, len(text)), "CHECK", scope, nxt=seg)
        return run
    _grows_linearly(make, f"anchor and exemptions {name}")


def _hostile_replies(req, size):
    good = json.loads(reply_json(req))
    yield "deep brackets", "[" * size
    yield "one long string", '"' + "a" * size + '"'
    yield "an unterminated string", '{"schema": "' + "\\u0041" * (size // 6)
    yield "many verdicts", json.dumps(dict(good, verdicts=good["verdicts"] * (size // 30)))
    yield "many spans", json.dumps(dict(good, verdicts=[{"id": req.ids[0], "v": "gated",
                                                         "spans": [{"quote": "x" * 30, "category": "CHECK"}] * (size // 60)}]))
    yield "duplicate keys", "{" + ", ".join(f'"k": {i}' for i in range(size // 10)) + "}"
    yield "a huge number", "{\"schema\": " + "9" * size + "}"
    yield "fences", "```\n" * (size // 4)


def test_a_hostile_reply_is_validated_in_linear_time(prompt):
    inp = build_input("The speed is 15 km/h.\n\nIt holds.", REQ, key=TEST_KEY, prompt_path=prompt)
    req = inp.requests[0]
    for size in (32 * 1024 - 64, 200_000):
        for name, raw in _hostile_replies(req, size):
            t = measure(lambda: validate_reply(raw, "end_turn", req, inp.scope), BOUND, repeat=3, label=f"reply {name} {size}")
            assert t.holds, t
            assert all(v.state == "unavailable" for v in t.results), name
