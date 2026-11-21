"""D9/D10 (decision D35): every new reader is linear in its input. Each entry point of the Geography and Language B packs and of the Spanish
lexicon, and the full parse plus packs of both branches, runs over the standard hostile inputs (``tests/adapters/hostile_inputs``: runs of
about 20,000 characters of one shape, the prefixed runs and the joined word runs) and long Spanish and Geography shapes (``¿¿¿``, ``¡a¡a``,
``1.250.250``, ``dos mil dos mil``, ``«a «a``, ``Estimado: Estimado:``, ``km² km²``, ``per 1,000 per 1,000``, ``site 1 site 1``, a 60-row
table of joined words), each call under a bound far above what a linear reader takes, with no exception. A growth check at 20,000 and
80,000 characters keeps the ratio under 8 (a quadratic reader gives about 16). Found while building: a blank run at a line start under
MULTILINE ('^\\s*+' reads line breaks too) and blanks before an optional currency sign were rescanned from every position."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import spanish_lexicon as es
from epinoic_logic.branches.geography import _CACHE as GEO_CACHE, GeographyPack
from epinoic_logic.branches.language_b import _CACHE as LB_CACHE, LanguageBPack, model_regions
from epinoic_logic.branches.registry import default_registry

from ..adapters import hostile_inputs as H
from . import d9d10_texts as T
from .d9d10_hub import GEO, SPB, report

N = 20_000
SHAPES = {
    "inverted question marks": lambda n: "¿" * n + "x",
    "inverted bangs": lambda n: "¡a" * (n // 2),
    "spanish thousands groups": lambda n: "1.250" + ".250" * (n // 4),
    "spanish number words": lambda n: "dos mil " * (n // 8),
    "guillemets": lambda n: "«a " * (n // 3),
    "greetings": lambda n: "Estimado: " * (n // 10),
    "areas": lambda n: "km² " * (n // 4),
    "rates per thousand": lambda n: "per 1,000 " * (n // 10),
    "site labels": lambda n: "site 1 " * (n // 7),
    "densities": lambda n: "With 2.4 million people on 1,200 km², the density is 2,000 people per km². " * (n // 75),
    "word counts": lambda n: "Word count: about 513 " * (n // 22),
    "arrow lines": lambda n: "\n" + '"a" → "b"' * (n // 9),
    "line breaks after a note": lambda n: "This synthesis" + "\n" * n + "x",
    "tabs after a share": lambda n: "20 per cent of" + "\t" * n + "x",
}
TABLE = ("Site | Mean pedestrian count (per 10 min)\n" + "\n".join(f"{'-'.join(['A'] * 30)} | {k}" for k in range(60)))
INPUTS = {**H.all_inputs(), **H.word_runs(), **{k: f(N) for k, f in SHAPES.items()}, "joined-word table": TABLE}


def _report(subject, text, docs):
    return report(*subject, text, docs=docs, claims=[dict(claim_id="c1", claim_text=text[:3000] or "x", claim_role="point", materiality="material")])


def _timed(fn) -> float:
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


@pytest.mark.parametrize("name", list(INPUTS))
def test_the_pack_entry_points_are_linear(name):
    text = INPUTS[name]
    for subject, pack, cache, docs in ((GEO, GeographyPack(), GEO_CACHE, (T.GE_T14_DOC, ("doc-t", "Table", "Task", TABLE))),
                                       (SPB, LanguageBPack(), LB_CACHE, (T.SP_T14_DOC,))):
        cache.clear()
        rep = _report(subject, text, docs)
        assert _timed(lambda: (pack.formal_checks_for(rep, T.SP_T15_Q), pack.checks(rep, T.SP_T15_Q))) < 3.0, (name, subject[0])
        assert not [f for f in pack.checks(rep, T.SP_T15_Q) if f.code == "BR-INTERNAL-001"], (name, subject[0])


@pytest.mark.parametrize("name", list(INPUTS))
def test_the_spanish_lexicon_readers_are_linear(name):
    text = INPUTS[name]
    calls = [lambda: es.is_spanish(text), lambda: es.spanish_paragraphs(text), lambda: es.spanish_number_figures(text),
             lambda: list(es.SPANISH_CREDIT_RE.finditer(text)), lambda: es.connector_forms(text), lambda: es.inverted_mark_spans(text),
             lambda: es.text_type_of(text), lambda: [es.address_markers(text, f) for f in es.ADDRESS_FORMS],
             lambda: [es.spanish_numeral_readings(tok, "es") for tok in text.split()[:2000]],
             lambda: model_regions(text, task="writing", spanish_context=True), lambda: model_regions(text, task="marking")]
    for k, call in enumerate(calls):
        assert _timed(call) < 3.0, (name, k)


@pytest.mark.parametrize("name", list(H.HOSTILE) + list(H.WORD_RUNS) + list(SHAPES) + ["joined-word table"])
def test_parse_and_packs_of_both_branches_are_bounded(name):
    text = INPUTS[name]
    reg = default_registry()
    for subject in (GEO, SPB):
        branch, _p = reg.for_subject(subject[0])

        def run():
            try:
                rep = branch.parser().parse_response(text, request_id="r", task_id="t", report_id="rx", subject=subject[0], task_type="writing_task", agent_id=subject[1])
            except Exception as exc:  # noqa: BLE001 - only the parsers' refusal of an empty answer is an answer
                assert type(exc).__name__ == "AdapterError", (name, type(exc).__name__)
                return
            findings, _formal = branch.run_packs(rep, "Write.")
            assert not [f for f in findings if f.code in ("PACK-INTERNAL-001", "BR-INTERNAL-001")], (name, subject[0])
        assert _timed(run) < 10.0, (name, subject[0])


@pytest.mark.parametrize("shape", ["line breaks after a note", "tabs after a share", "guillemets", "densities", "inverted question marks", "arrow lines",
                                   "word counts", "site labels"])
def test_growth_from_20k_to_80k_characters_stays_linear(shape):
    for subject, pack, cache, docs in ((GEO, GeographyPack(), GEO_CACHE, (T.GE_T14_DOC,)), (SPB, LanguageBPack(), LB_CACHE, (T.SP_T14_DOC,))):
        times = []
        for n in (N, 4 * N):
            text = SHAPES[shape](n)
            best = None
            for _ in range(2):
                cache.clear()
                rep = _report(subject, text, docs)
                t = _timed(lambda: (pack.formal_checks_for(rep, T.SP_T15_Q), pack.checks(rep, T.SP_T15_Q)))
                best = t if best is None else min(best, t)
            times.append(best)
        assert times[1] < max(0.05, times[0]) * 8, (shape, subject[0], times)
