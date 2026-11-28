"""T2 at the package level: the faithful fake (``ReaderBackedLabeller``) on the development sets of the rule reader. The union
of the reader and the label refuses every positive the reader refuses and adds nothing on the negatives. Measured on this tree
and pinned: the label names 205 of the 208 positives (the other 3 are text the reader cannot read, hidden or letter-like runs,
which the rendering removes or cannot quote; the reader refuses them as CORE-SELF-002), and 0 of the 213 negatives."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic import selfcert
from epinoic_logic.selfcert_label.fakes import FAMILY_CATEGORY, ReaderBackedLabeller

DATA = Path(__file__).resolve().parents[1] / "selfcert" / "data"


def _records(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def _request(ctx: dict) -> tuple[dict, str]:
    """The record's context as the router's request (its task type and request text) and the writer."""
    ctx = ctx or {}
    req = {"subject": "development set"}
    for k in ("task_type", "request_text"):
        if k in ctx:
            req[k] = ctx[k]
    return req, ctx.get("writer", "specialist")


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    prompt = tmp_path_factory.mktemp("prompt") / "prompt.md"
    prompt.write_text("Fixed system text of the selfcert-label test suite.\n", encoding="utf-8")
    lab = ReaderBackedLabeller(prompt_path=prompt)
    out = {}
    for name in ("dev-positive.jsonl", "dev-negative.jsonl"):
        rows = []
        for rec in _records(name):
            req, writer = _request(rec.get("context"))
            reader = selfcert.read(rec["text"], selfcert.context_from_dict(rec.get("context"))).refuses()
            res = lab.label(rec["text"], req, writer=writer)
            rows.append((rec, reader, res))
        out[name] = rows
    return out


def test_the_union_refuses_every_positive_the_reader_refuses(measured):
    rows = measured["dev-positive.jsonl"]
    assert len(rows) == 208
    reader = sum(r for _rec, r, _res in rows)
    label = sum(res.state == "named" for _rec, _r, res in rows)
    union = sum(r or res.withholds for _rec, r, res in rows)
    assert (reader, label, union) == (208, 205, 208)
    unnamed = [rec for rec, _r, res in rows if res.state != "named"]
    assert all(rec["category"].startswith("unread-") for rec in unnamed)
    assert all(res.state in ("named", "none_named") for _rec, _r, res in rows)  # the fake's replies always validate


def test_the_label_adds_nothing_on_the_negatives(measured):
    rows = measured["dev-negative.jsonl"]
    assert len(rows) == 213
    reader = sum(r for _rec, r, _res in rows)
    label = sum(res.state != "none_named" for _rec, _r, res in rows)
    union = sum(r or res.withholds for _rec, r, res in rows)
    assert (reader, label, union) == (0, 0, 0)


def test_every_named_span_carries_a_category_mapped_from_the_readers_family(measured):
    cats = {sp.family for _rec, _r, res in measured["dev-positive.jsonl"] for sp in res.spans}
    assert cats <= set(FAMILY_CATEGORY.values())
    assert {"CHECK", "OUTCOME", "STATUS"} <= cats
    assert all(res.record["canary"]["caught"] == res.record["canary"]["positive"] >= 1
               for _rec, _r, res in measured["dev-positive.jsonl"])


# ---------------------------------------------------------------------------------------------------------------- line structure
# Check round of stage 2a: the fake read each rendered paragraph's sentences joined by spaces, so the line structure the reader
# reads was lost. A tick at the end of a marking line and a tick-bullet list were read as MARK verdicts the reader does not refuse,
# and the fake named them: a delivery decision that differed from the reader alone. The fake now reads the answer's raw text as
# the reader does and maps each hit back to the request's ids. Expected values fixed here: nothing named where the reader passes,
# and the reader's own hit named at its place where it refuses.
_PHYSICS_MARKING = (
    "Question 2(a) — calculate — 2 marks\n"
    "What the question wants: the speed from v = d/t, with d in metres and t in seconds.\n"
    "What earned credit: the relation v = d/t is right, and the distance 240 m is used.\n"
    "Provisional mark: 1 / 2 — provisional.\n"
    "Model: v = d/t = 240/16 = 15 m/s ✔\n\n"
    "Question 2(b) — explain — 2 marks\n"
    "What earned credit: the idea that a larger force gives a larger acceleration.\n"
    "Provisional mark: 1 / 2 — provisional.\n"
    "Model: The net force doubles, so the acceleration doubles ✔. The mass is unchanged, so a = F/m rises in proportion ✔")
_PHYSICS_REQUEST = {"subject": "Physics", "task_type": "marking_feedback",
                    "request_text": "My teacher set this practice question on speed and force; please mark my answer and give feedback."}
_TICK_LIST = "Ventajas de la franquicia:\n✔ expansión rápida\n✔ conocimiento local\n✘ menos control"
_TICK_REQUEST = {"subject": "Business Management", "task_type": "short_answer",
                 "request_text": "Ventajas y desventajas de la franquicia"}


@pytest.mark.parametrize("text, request_", [(_PHYSICS_MARKING, _PHYSICS_REQUEST), (_TICK_LIST, _TICK_REQUEST)],
                         ids=["marking-ticks", "tick-list"])
def test_the_fake_keeps_the_line_structure_the_reader_reads(text, request_):
    assert not selfcert.read(text, selfcert.context_for(request_)).refuses()
    res = ReaderBackedLabeller().label(text, request_)
    assert (res.state, res.spans) == ("none_named", ())


def test_the_fake_names_the_readers_hit_at_its_own_place_in_a_multi_line_paragraph():
    text = "The total is 12.\nThe mean is 4.\nThis passed the hub's checks.\nThe range is 6."
    req = {"subject": "Mathematics", "task_type": "short_answer", "request_text": "Find the total."}
    reading = selfcert.read(text, selfcert.context_for(req))
    assert reading.refuses()
    res = ReaderBackedLabeller().label(text, req)
    assert res.state == "named"
    assert {sp.place for sp in res.spans} == {"paragraph 1, sentence 3"}


def test_the_readers_directive_family_maps_to_the_directive_category():
    assert FAMILY_CATEGORY["DIRECTIVE"] == "DIRECTIVE"
