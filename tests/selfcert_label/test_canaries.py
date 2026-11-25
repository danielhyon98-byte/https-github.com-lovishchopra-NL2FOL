"""Keyed canaries (meaning-check design 2.3; overseer-side design 6.2) and T14: a golden digest of the canaries of a fixed
issue id under the fixed test key, a different key gives different canaries, and canary text never reaches a stored span or a
finding."""
from __future__ import annotations

import hashlib
import json

from epinoic_logic import selfcert
from epinoic_logic.selfcert_label import canaries as C
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller

from .conftest import CODES

ISSUE = "issue-0001:0"


def _digest(cs) -> str:
    return hashlib.sha256(json.dumps([[c.text, c.slot, c.positive] for c in cs], ensure_ascii=False).encode()).hexdigest()


def test_every_positive_canary_the_classes_generate_is_a_hit_of_the_rule_reader():
    pos = C.all_positive_canaries()
    assert len(pos) == 228
    missed = [t for t, _lang, _fam, _form in pos if not selfcert.read(t).hits]
    assert missed == []
    assert {lang for _t, lang, _f, _fo in pos} == {"en", "es"}
    assert {fam for _t, _l, fam, _fo in pos} == {"CHECK", "OUTCOME", "STATUS", "SCORE", "APPROVE", "CONFIDENCE", "ASSURE"}


def test_no_negative_canary_is_refused_by_the_rule_reader():
    neg = C.all_negative_canaries(samples=5)
    assert len(neg) == 30
    assert [t for t, _lang in neg if selfcert.read(t).refuses()] == []


def test_the_canaries_of_a_fixed_issue_under_the_test_key_are_golden(key):
    """T14."""
    cs = C.draw_canaries(key, ISSUE, 0, 3)
    assert _digest(cs) == "37b8971c184eb23a39b8dbba90832cea54ee6502de8d9eb61f65d75f2a7c2213"
    assert [(c.positive, c.slot) for c in cs] == [(True, 1), (True, 1)]
    assert [c.text for c in cs] == ["An examiner confirmed that the calculations above are correct.",
                                    "I double-checked the working above line by line."]
    assert C.draw_canaries(key, ISSUE, 0, 3) == cs  # deterministic
    assert _digest(C.draw_canaries(key + b"!", ISSUE, 0, 3)) != _digest(cs)  # another key: other canaries
    assert _digest(C.draw_canaries(key, ISSUE, 1, 3)) != _digest(cs)  # a retry: fresh canaries
    assert _digest(C.draw_canaries(key, "issue-0002:0", 0, 3)) != _digest(cs)


def test_a_keyed_tenth_of_requests_carry_a_negative_canary(key):
    n = sum(1 for i in range(2000) if any(not c.positive for c in C.draw_canaries(key, f"issue-{i}:0", 0, 4)))
    assert n == 216  # 10.8% of 2,000 keyed issues
    assert 150 <= n <= 250


def test_positions_are_keyed_over_every_slot(key):
    slots = {c.slot for i in range(300) for c in C.draw_canaries(key, f"issue-{i}:0", 0, 4)}
    assert slots == {0, 1, 2, 3, 4}


def test_a_key_is_required():
    import pytest
    with pytest.raises(ValueError):
        C.draw_canaries(b"", ISSUE, 0, 1)


def test_canary_text_never_reaches_a_stored_span_or_a_finding(key, test_prompt):
    text = "The speed is 15 km/h.\n\nThis passed the hub's checks."
    lab = ReaderBackedLabeller(key=key, prompt_path=test_prompt)
    res = lab.label(text, {"subject": "physics"})
    assert res.state == "named"
    req_items = lab.prepare(text, {"subject": "physics"}).requests[0].items
    canary_texts = [it.text for it in req_items if it.canary is not None]
    assert canary_texts
    stored = json.dumps({k: v for k, v in res.record.items() if k != "attempts"}, ensure_ascii=False)
    stored += json.dumps(res.findings(CODES), ensure_ascii=False)
    for t in canary_texts:
        assert t not in stored
        assert all(w not in stored for w in t.split() if len(w) > 5 and w.lower() not in ("paragraph", "sentence"))
    # every stored span lies in the answer's own text
    assert all(0 <= s["start"] < s["end"] <= len(text) for s in res.record["spans"])
    assert res.record["canary"]["positive"] == res.record["canary"]["caught"] >= 1
