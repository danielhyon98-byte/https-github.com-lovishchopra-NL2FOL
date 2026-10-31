"""Repair round 2 (ADV2-01, ADV2-03): the caches that bound the diagnosis's cost give exactly the uncached answers, keyed by
content (never by identity, so a changed input is never served a stale answer), and the attribution rule's cost no longer
grows with claims times document length.

Ported onto the integrated translator with the caches of the diagnosis's own modules (``lexis``, ``diag_evidence``); the
engine runner's circularity cache and the markup cache of ``adapters.markdown`` are the feature line's changes to shared
modules and are not ported, so their two tests are not either (docs/ARGUMENT_DIAGNOSTICS.md, section "Port onto the
integrated translator")."""
from __future__ import annotations

import time

from epinoic_logic import lexis
from epinoic_logic.translate import diag_evidence as D


def test_the_token_cache_gives_the_uncached_readings():
    for text in ["The 1929 crash followed *speculative* buying.", "x" * 9000 + " tail words", "", "**Bold** and _it_"]:
        assert list(lexis.token_spans(text)) == list(lexis._token_spans(text))


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
