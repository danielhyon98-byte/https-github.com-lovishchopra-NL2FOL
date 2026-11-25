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
