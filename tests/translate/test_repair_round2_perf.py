"""Repair round 2 (ADV2-01, ADV2-03): the caches that bound the diagnosis's cost give exactly the uncached answers, keyed by
content (never by identity, so a changed input is never served a stale answer), and the attribution rule's cost no longer
grows with claims times document length."""
from __future__ import annotations

import time

from epinoic_logic import lexis
from epinoic_logic.adapters.markdown import _strip_markup, strip_markup
from epinoic_logic.engine.runner import _circular_premises, circular_premises
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import diag_evidence as D


def _problem(premise: dict, conclusion: dict, pid: str = "p") -> Problem:
    return Problem.model_validate({"problem_id": pid, "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "a", "sort": "Bool"}, {"name": "b", "sort": "Bool"}],
                                   "premises": [{"id": "p1", "expr": premise}], "conclusion": {"id": "C", "expr": conclusion}})


A, NB = {"op": "var", "name": "a"}, {"op": "var", "name": "b"}


def test_the_circularity_cache_answers_by_content():
    restating = _problem(A, A)
    other = _problem(NB, A)
    for _ in range(3):
        assert circular_premises(restating) == _circular_premises(restating) == ["p1"]
        assert circular_premises(other) == _circular_premises(other) == []
    # the same content under another problem id is the same answer; a changed premise is a new one
    assert circular_premises(_problem(A, A, pid="q")) == ["p1"]
    assert circular_premises(restating, ["p1"]) == ["p1"] and circular_premises(restating, []) == []


def test_the_token_and_markup_caches_give_the_uncached_readings():
    for text in ["The 1929 crash followed *speculative* buying.", "x" * 9000 + " tail words", "", "**Bold** and _it_"]:
        assert list(lexis.token_spans(text)) == list(lexis._token_spans(text))
        assert strip_markup(text) == _strip_markup(text)


def test_the_stem_cache_gives_the_content_stems():
    for text in ["Source A shows that the delegate accepted the treaty.", "", "rates rose in 2020"]:
        assert D._text_stems(text) == frozenset(D._stems(text)) or D._text_stems(text) == D._stems(text)


def test_attributions_over_many_claims_and_a_long_document_are_read_in_bounded_time():
    from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

    doc = SuppliedText(document_id="source-a", title="Source A", author=None, text=" ".join(f"word{k} sentence about trade." for k in range(12_000)))
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="history-specialist", subject="History", task_type="short_answer")
    claims = [ClaimRecord(**ids, claim_id=f"c{k}", claim_text=f"Source A shows that merchants in port {k} traded spices with distant kingdoms.",
                          claim_role="evidence") for k in range(400)]
    text = " ".join(c.claim_text for c in claims)
    report = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), claims=claims, supplied_texts=[doc],
                              created_at="2026-10-17T10:00:00Z")

    class Ctx:
        pass
    ctx = Ctx()
    ctx.report, ctx.task, ctx.outcomes, ctx.items, ctx.source_bound, ctx.data_texts, ctx.task_text = report, None, (), (), True, True, None
    t0 = time.perf_counter()
    out = list(D.evd_src_002(ctx))
    assert time.perf_counter() - t0 < 10.0          # measured under 1 s; before the stem cache, about 100 s
    assert len(out) == 400
