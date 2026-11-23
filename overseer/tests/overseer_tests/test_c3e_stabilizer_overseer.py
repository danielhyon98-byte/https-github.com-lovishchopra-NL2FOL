"""Stabilizer of the c3e clearance: a new replay worker warms the translator's self-certification reader before its first job.

The first clearance after the real port connected waited past its 250 ms pending window (about 0.3 s against 0.1 s for every later
turn) because the worker's first replay whose diagnosis reads a text paid the reader's one-time loading (lexicon, fold table,
misspelling index, patterns): a cold first turn then ended refuse_incomplete where a warm one ended refuse_integrity. The worker
now reads a few fixed sentences when it starts, before it takes a job; no reading or replay result changes.
"""
from __future__ import annotations

import queue

from epinoic_logic.api.adapters import selfcert_read
from epinoic_overseer import replay


def test_a_replay_worker_warms_the_reader_before_its_first_job(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(replay, "_warm_reader", lambda: calls.append("warm"))
    jobs: "queue.Queue" = queue.Queue()
    jobs.put(None)  # the stop message: the worker returns at once after warming
    results: "queue.Queue" = queue.Queue()
    replay._worker_main(jobs, results)
    assert calls == ["warm"] and results.empty()


def test_the_warm_up_reads_its_sentences_and_never_fails_the_worker(monkeypatch):
    replay._warm_reader()
    for sentence in replay._WARM_SENTENCES:
        assert all(h.rule != "reader-failed" for h in selfcert_read(sentence).hits), sentence

    import epinoic_logic.api.adapters as api

    def broken(_text):
        raise RuntimeError("SYNTHETIC reader failure")
    monkeypatch.setattr(api, "selfcert_read", broken)
    assert replay._warm_reader() is None  # (a failure while warming is ignored: the job's own reading loads the reader)
