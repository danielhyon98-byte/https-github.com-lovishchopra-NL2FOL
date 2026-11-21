"""The development sets of the self-certification design (round-10 hold remedy c3b), committed as regression data: every record
of ``data/dev-positive.jsonl`` (a self-certification, or text the reader cannot read) is refused, every record of
``data/dev-negative.jsonl`` (boundary (b): negated, questioned, uncertain, instructions, worked checks, outside sources' checks,
subject matter, named references) is not. The expected value is fixed in each record; the reading context is the record's own
(``{"task_type": "marking_feedback"}`` read as the router's plan; ``{"writer": "combinator"}``)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.selfcert import Context, context_for, read

DATA = Path(__file__).parent / "data"


def _records(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def _ctx(d) -> Context:
    if not d:
        return Context()
    if "task_type" in d or "request_text" in d:
        # (the router's plan: its task type, and its request text, which says whether a true-or-false item is asked)
        return context_for({k: d[k] for k in ("task_type", "request_text") if k in d}, writer=d.get("writer", "specialist"))
    return Context(writer=d.get("writer", "specialist"))


POSITIVE = _records("dev-positive.jsonl")
NEGATIVE = _records("dev-negative.jsonl")


def test_the_sets_are_the_committed_sizes_and_cover_every_branch():
    assert (len(POSITIVE), len(NEGATIVE)) == (208, 213)  # (attack round 3: one positive added, 'Final answer: correct.')
    branches = {r["branch"] for r in POSITIVE + NEGATIVE}
    assert {"geography", "language_b", "history", "economics", "english", "sciences", "mathematics", "computer_science",
            "business_management", "psychology", "combinator"} <= branches
    assert all(r["expected"] is True for r in POSITIVE) and all(r["expected"] is False for r in NEGATIVE)


@pytest.mark.parametrize("record", POSITIVE, ids=lambda r: f"{r['branch']}-{r['category']}")
def test_every_positive_record_is_refused(record):
    reading = read(record["text"], _ctx(record.get("context")))
    assert reading.refuses() is True, (record["text"], record["why"])


@pytest.mark.parametrize("record", NEGATIVE, ids=lambda r: f"{r['branch']}-{r['category']}")
def test_no_negative_record_is_refused(record):
    reading = read(record["text"], _ctx(record.get("context")))
    assert reading.refuses() is False, (record["text"], record["why"], reading)


def test_the_unread_records_are_unread_runs_not_self_certifications():
    for r in POSITIVE:
        if r["category"].startswith("unread-"):
            reading = read(r["text"], _ctx(r.get("context")))
            assert reading.unread and not reading.hits, r["text"]
