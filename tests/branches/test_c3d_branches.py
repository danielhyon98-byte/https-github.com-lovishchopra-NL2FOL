"""The c3d follow-up on the Geography and Language B branches and the core pack, each expected value fixed here: the branch misses the
c3c run left open, each read by a widened frame (a figure's noun named after it, an area from its two dimensions, a relative difference
of two labelled figures, a volume from a depth over an area, an interval between two clock times of the request, the amounts, figures
per person, relative changes and complements a sentence derives from a supplied year table, a word limit stated twice; a model's
reporting verb, the byline's course, a word range credited to the task, a named speaker of a paraphrase, the scenario a writing or
marking task sets, a speaker the text names after the words or by a description, the word count of the answer's own notes), each beside
its correct twin, which stays unnamed; and an own-wording quotation, which the core pack no longer reports as unverifiable while a
bare quotation of words the answer never writes stays reported.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from epinoic_logic.branches.packs import CorePack

from . import d9d10_hub as H
from .test_c3_clearance_roles_sources import GENUINE, texts_of

_BASE: dict = {}


def _new(name: str, sentence: str):
    """The error and warning codes and the non-entailed checks that ``sentence``, appended to the recorded answer ``name``, adds."""
    if name not in _BASE:
        _BASE[name] = H.recorded(name)
    b = _BASE[name]
    rc = H.recorded(name, H.RECORDED[name][0] + "\n\n" + sentence)
    old = {(f.code, f.severity, f.message[:140]) for f in b.findings}
    new = [f.code for f in rc.findings if f.severity in ("error", "warning") and (f.code, f.severity, f.message[:140]) not in old]
    old_checks = [c for c in H.checks(b) if c[1] != "ENTAILED"]
    checks = [c for c in H.checks(rc) if c[1] != "ENTAILED" and c not in old_checks]
    return new, checks


#: (recorded answer, faulty sentence, its correct twin, the code the faulty one draws, the check family that fails)
MISSES = [
    # Geography: a figure's noun after it (the request's 'mean depth of 1.8 m') and the area of two dimensions
    ("c2/ge-p9c", "The channel was 6.0 m wide and 2.8 m deep, an area of 10.8 m².", "The channel was 6.0 m wide and 1.8 m deep, an area of 10.8 m².",
     "INT-SUBJ-001", "geography-dimension-area"),
    ("c2/ge-p9c", "The channel was 6.0 m wide and 1.8 m deep, an area of 12.8 m².", "The channel was 6.0 m wide and 1.8 m deep, an area of 10.8 m².",
     "INT-SUBJ-001", "geography-dimension-area"),
    ("c2/ge-p9c", "Storm 2 had 39 mm of rain.", "Storm 2 had 36 mm of rain.", "INT-SUBJ-004", "geography-request-figure"),
    # a relative difference of two labelled figures of the request, with no bracketed pair
    ("c2/ge-p9c", "Storm 2 had about 10% less rain than Storm 1.", "Storm 2 had about 5% less rain than Storm 1.", "INT-SUBJ-001",
     "geography-pair-comparison"),
    ("c2/ge-p9c", "Storm 2 had about 5% more rain than Storm 1.", "Storm 2 had about 5% less rain than Storm 1.", "INT-SUBJ-001",
     "geography-pair-comparison"),
    ("c2/ge-p9c", "Storm 2's peak discharge was 150% higher than Storm 1's.", "Storm 2's peak discharge was 200% higher than Storm 1's.",
     "INT-SUBJ-001", "geography-pair-comparison"),
    # rainfall depth over an area to a volume
    ("c2/ge-p9c", "Storm 1's 38 mm over 24 km² is about 91,200 m³ of water.", "Storm 1's 38 mm over 24 km² is about 912,000 m³ of water.",
     "INT-SUBJ-001", "geography-depth-volume"),
    # an interval between two clock times of the request
    ("c2/ge-p9c", "Storm 2's discharge peaked 5 hours 30 minutes after its rainfall peak.",
     "Storm 2's discharge peaked 4 hours 30 minutes after its rainfall peak.", "INT-SUBJ-001", "geography-clock-interval"),
    ("c2/ge-p9c", "The lag time of Storm 1 was 10 hours.", "The lag time of Storm 1 was 12 hours.", "INT-SUBJ-001", "geography-clock-interval"),
    # figures derived from the supplied year table
    ("c2/ge-t15", "Wind and solar supply rose from 8.2 PJ to 163.5 PJ.", "Wind and solar supply rose from 8.2 PJ to 136.5 PJ.", "INT-SUBJ-004",
     "geography-table-derived"),
    ("c2/ge-t15", "Energy supply per person rose from about 34 GJ in 2005 to about 42 GJ in 2025.",
     "Energy supply per person rose from about 38 GJ in 2005 to about 42 GJ in 2025.", "INT-SUBJ-004", "geography-table-derived"),
    ("c2/ge-t15", "The imported share rose by 16 percentage points, a relative rise of about 16%.",
     "The imported share rose by 16 percentage points, a relative rise of about 42%.", "INT-SUBJ-004", "geography-table-derived"),
    ("c2/ge-t15", "Domestic sources supplied 62% of energy in 2005 and 56% in 2025.", "Domestic sources supplied 62% of energy in 2005 and 46% in 2025.",
     "INT-SUBJ-004", "geography-table-derived"),
    # one word limit stated twice
    ("c1/ge-t14", "Examiners stop reading at 3,000 words, so you have room to spare.", "Examiners stop reading at 2,500 words, so you have room to spare.",
     "INT-SUBJ-004", "geography-case-consistency"),
    ("c1/ge-t14", "Keep within the 3,000-word limit.", "Keep within the 2,500-word limit.", "INT-SUBJ-004", "geography-case-consistency"),
    # the spacing of the supplied table's sites, and intervals and multiples between events the answer itself dates
    ("c1/ge-t14", "The sites are 150 m apart, from 0 m to 900 m.", "The sites are 100 m apart, from 0 m to 900 m.", "INT-SUBJ-004",
     "geography-table-spacing"),
    ("c1/ge-t14", "The sites are 100 m apart, from 0 m to 1,000 m.", "The sites are 100 m apart, from 0 m to 900 m.", "INT-SUBJ-004",
     "geography-table-spacing"),
    ("c3/ge-t16", "The aftershock struck about 17 months after the Darfield earthquake.", "The aftershock struck about 6 months after the Darfield earthquake.",
     "INT-SUBJ-001", "geography-event-relation"),
    ("c3/ge-t16", "The aftershock was about 5 km deep, a third of the depth of the Darfield earthquake.",
     "The aftershock was about 5 km deep, half the depth of the Darfield earthquake.", "INT-SUBJ-001", "geography-event-relation"),
    ("c3/ge-t16", "About 75 of the aftershock's 185 deaths happened outside the two collapsed buildings.",
     "About 50 of the aftershock's 185 deaths happened outside the two collapsed buildings.", "INT-SUBJ-001", "geography-event-relation"),
    # Language B: a reporting verb of the model, the byline's course, a range credited to the task
    ("c2/sp-t15", 'The model proposes that terraces close "a la una entre semana".', 'The model proposes that terraces close "a medianoche entre semana".',
     "INT-SUBJ-004", "language-b-quoted-form"),
    ("c2/sp-t15", "The byline credits a student in 1.º de Bachillerato.", "The byline credits a student in 2.º de Bachillerato.", "INT-SUBJ-004",
     "language-b-quoted-form"),
    ("c2/sp-t15", "The task asks for between 250 and 400 words.", "The task asks for between 450 and 600 words.", "INT-SUBJ-001",
     "language-b-word-range-claim"),
    # the speaker of a paraphrase of the student's email (by name, by kin word across the two languages)
    ("c3/sp-t16", "Señora Rojas says that Tomás can stay at your house.", "Your mother says that Tomás can stay at your house.", "INT-SUBJ-004",
     "language-b-quote-speaker"),
    ("c3/sp-t16", "Your grandfather said that the colours of the houses were beautiful.",
     "Your grandmother said that the colours of the houses were beautiful.", "INT-SUBJ-004", "language-b-quote-speaker"),
    ("c3/sp-t16", "Your father says that Tomás can stay at your house.", "Your mother says that Tomás can stay at your house.", "INT-SUBJ-004",
     "language-b-quote-speaker"),
    # the scenario the task sets ('tres semanas de intercambio')
    ("c3/sp-t16", "The exchange lasted two weeks.", "The exchange lasted three weeks.", "INT-SUBJ-004", "language-b-supplied-figure"),
    # a speaker the poem names after the words ('Ya merito, / she told it') or by a description ('the grill cook, Rubén,')
    ("c3/sp-p10d", '"Ya merito" is said by Rubén to the bread dough.', '"Ya merito" is said by Doña Celia to the bread dough.', "INT-SUBJ-004",
     "language-b-quote-speaker"),
    ("c3/sp-p10d", '"échale ganas, mijo" is said by Doña Celia.', '"échale ganas, mijo" is said by Rubén.', "INT-SUBJ-004", "language-b-quote-speaker"),
    ("c3/sp-p10d", '"¡Ojo, que quema!" is said by Doña Celia.', '"¡Ojo, que quema!" is said by Rubén.', "INT-SUBJ-004", "language-b-quote-speaker"),
    # the word count of the answer's own notes
    ("c3/sp-p10d", "These notes are about 400 words, within the 250-word limit.", "These notes are about 240 words, within the 250-word limit.",
     "INT-SUBJ-004", "language-b-word-count"),
]


@pytest.mark.parametrize("name,faulty,_twin,code,family", MISSES)
def test_the_faulty_statement_is_named(name, faulty, _twin, code, family):
    found, checks = _new(name, faulty)
    assert code in found and any(c[0].startswith(family) and c[1] == "COUNTEREXAMPLE" for c in checks), (faulty, found, checks)


@pytest.mark.parametrize("name,_faulty,twin,_code,_family", MISSES)
def test_its_correct_twin_is_not_named(name, _faulty, twin, _code, _family):
    found, checks = _new(name, twin)
    assert found == [] and checks == [], (twin, found, checks)


@pytest.mark.parametrize("name", sorted(H.RECORDED))
def test_the_recorded_answers_draw_no_failed_check(name):
    rc = H.recorded(name)
    assert [c for c in H.checks(rc) if c[1] != "ENTAILED"] == [] and "BR-INTERNAL-001" not in H.codes(rc), (name, H.checks(rc), H.codes(rc))


def test_a_reading_task_request_is_no_source_of_counts():
    # the request of a reading task sets statements to judge ('La escuela volvió a abrir con más de veinte alumnos', a false one): a count
    # the answer states is never compared with it
    found, checks = _new("c1/sp-t14", "La escuela volvió a abrir con catorce alumnos.")
    assert not any(c[0].startswith("language-b-supplied-figure") for c in checks), checks


def _core_unverifiable(text: str) -> list:
    g = GENUINE["ec-t16"]
    rep = H.report("Economics", "economics-specialist", text, docs=[(t.document_id, t.title, t.author, t.text) for t in texts_of(g)],
                   claims=[dict(claim_id="c1", claim_text=text[-3000:], claim_role="point", materiality="material")])
    return [f for f in CorePack._unverifiable_quotations(rep, False, request_text=g["question"]) if f.code == "CORE-SRC-003"]


def test_an_own_wording_quotation_is_no_unverifiable_quotation():
    base = GENUINE["ec-t16"]["response_text"]
    own = base + "\n\nOwners sold quotas and the fleet got smaller over time. In short, \"the fleet got smaller over time\"."
    assert _core_unverifiable(own) == []


def test_a_bare_quotation_of_words_the_answer_never_writes_stays_unverifiable():
    base = GENUINE["ec-t16"]["response_text"]
    bare = base + "\n\nIn short, \"the fleet got smaller over time\"."
    altered = base + "\n\nOwners sold quotas and the fleet got smaller over time. In short, \"the fleet shrank by half every decade\"."
    for text in (bare, altered):
        found = _core_unverifiable(text)
        assert len(found) == 1 and found[0].severity == "warning", (text[-120:], found)


#: Runs of the frames the c3d readers read, each about 20,000 characters, after the standard hostile runs.
C3D_RUNS = {
    "durations after": "Storm 1's discharge peaked 1 hour after its rainfall " * 380 + "x",
    "lag times": "the lag time of Storm 1 was 3 hours, " * 540 + "x",
    "dimensions": "6.0 m wide and 1.8 m deep, an area of " * 520 + "x",
    "depths over areas": "38 mm over 24 km² is about " * 740 + "x",
    "labelled comparisons": "Storm 2 had 5% less rain than Storm 1 and " * 480 + "x",
    "per person": "per person 34 GJ in 2005 and " * 690 + "x",
    "relative rises": "imported share, a relative rise of 16%, " * 500 + "x",
    "complements": "domestic sources 62% in 2005 and " * 600 + "x",
    "word limits": "stop reading at 2,500 words and " * 620 + "x",
    "sites apart": "the sites are 100 m apart, from 0 m to 900 m, " * 440 + "x",
    "event intervals": "On 4 September 2010 it struck. The aftershock struck 5 months after the Darfield quake, " * 220 + "x",
    "event folds": "half the depth of the Darfield earthquake, " * 480 + "x",
    "parts of totals": "It killed 185 people, more than 130 of them in the collapse, and 50 of the 185 deaths outside the collapse; " * 180 + "x",
    "said by": '"Ya merito" is said by Rubén. ' * 650 + "x",
    "named paraphrases": "Señora Rojas says that Tomás can stay. " * 510 + "x",
    "bylines": "The byline credits a student in 1.º de Bachillerato. " * 380 + "x",
    "task ranges": "The task asks for between 250 and 400 words. " * 440 + "x",
}


@pytest.mark.parametrize("name", ["c1/ge-t14", "c2/ge-p9c", "c2/ge-t15", "c3/ge-t16", "c3/sp-p10d", "c3/sp-t16"])
def test_the_c3d_readers_stay_linear(name):
    from epinoic_logic.branches import geography, language_b

    from ..adapters.hostile_inputs import all_inputs, bounded
    _answer, question, subject, agent, task_type, docs = H.RECORDED[name]
    build = geography._build if subject == "Geography" else language_b._build
    for label, text in {**all_inputs(), **C3D_RUNS}.items():
        rep = H.report(subject, agent, text, task_type=task_type, docs=docs,
                       claims=[dict(claim_id="c1", claim_text=text[:3000] or "x", claim_role="point", materiality="material")])
        took, error = bounded(lambda t, rep=rep: build(rep, question), text)
        assert error is None and took < 5.0, (name, label, took, error)
