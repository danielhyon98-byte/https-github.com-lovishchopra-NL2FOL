"""Round-8 clearance (integrated round c1), handoff fixer: the branch readers the parallel fixers handed over, and the input
stalls found on their path.

* prose shares (critical finding "a wrong percentage crosses silently", the STEM fixer's handoff item 3a): '$40m, which is 25%
  of total sales of $200m', 'Labour costs of $30,000 are 30% of total costs of $120,000' and 'Of the 60 households surveyed,
  27 owned a car (40%)' are decided by the engine in the general reading (INT-SUBJ-001 when wrong, nothing when right);
* criterion marks (the core fixer's handoff item 1): an English A feedback stating "Criterion A: 6/5 ... Total: 14/20" (6 over
  its maximum, criteria summing to 17) is INT-SUBJ-001 twice;
* the English pack that cannot be loaded reports ES-INTERNAL-001 (the overseer fixer's handoff item 4);
* a near miss of a name the supplied case states (rule case-name, CORE-SRC-008, warning; the core fixer's handoff item 2 and the
  parsers fixer's item 7, breadth item 19): 'Tidewater Kayaks' on the Tidewell Kayaks case, and 'If Brackwood buys ...' in the
  recorded bm-p8a answer that elsewhere writes the case's Brackwater, crossed the hub with no finding;
* two quadratic scans of an answer's quotations, fixed at their cause: the core pack compared every quotation key with every
  other (``_absorbed_quotation_keys``, held to the pairwise reading on random keys) and ``nearest_text`` read every supplied
  text again for every quotation (``folded_vocabulary``)."""
from __future__ import annotations

import random
import re
import sys

import pytest

from epinoic_logic.adapters.sources import folded_vocabulary, nearest_text
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches import quant
from epinoic_logic.branches.packs import EnglishPack, _absorbed_quotation_keys
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

from ..core_hostile import SHAPES, one, sweep
from ..timing import measure

KEY = b"c1-handoff-branches-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def deliver(subject: str, agent: str, text: str, *, request: str = "Explain the figures.", task_type: str = "short_answer", texts=()):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type=task_type, selected_agent_ids=[agent, "combinator"],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _req, _rq = hub.dispatch("t", agent, request, list(texts))
    _reply, rc = hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-t-0")
    return rc


def errors(rc) -> list[str]:
    return [f.message for f in rc.findings if f.severity == "error"]


# ---------------------------------------------------------------------------------------------- prose shares


@pytest.mark.parametrize("subject,agent,wrong,right", [
    ("Economics", "economics-specialist", "Exports were $40m, which is 25% of total sales of $200m.", "Exports were $40m, which is 20% of total sales of $200m."),
    ("Business Management", "business-management-specialist", "Labour costs of $30,000 are 30% of total costs of $120,000.",
     "Labour costs of $30,000 are 25% of total costs of $120,000."),
    ("Geography", "geography-specialist", "Of the 60 households surveyed, 27 owned a car (40%).", "Of the 60 households surveyed, 27 owned a car (45%)."),
    ("Economics", "economics-specialist", "Imports came to $30m, which represented about 40% of the $60m deficit.",
     "Imports came to $30m, which represented about 50% of the $60m deficit."),
])
def test_a_share_stated_in_prose_is_decided(subject, agent, wrong, right):
    rc = deliver(subject, agent, wrong)
    named = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert named and "share" in named[0].message, [(f.code, f.message[:120]) for f in rc.findings]
    rc = deliver(subject, agent, right)
    assert not errors(rc), errors(rc)
    assert any(fc.satisfied is True and "share" in fc.detail for fc in rc.formal_checks), rc.formal_checks


@pytest.mark.parametrize("text", [
    "The tax raised $5bn in 2019, which is 2% of GDP.",                                   # no figure for the whole
    "Unemployment was 5%, which is 2% of the labour force of 40 million.",               # the part is itself a per cent
    "In 1990, 2000 was 50% of 4000 in the series.",                                     # a year is no part
])
def test_control_a_share_with_no_comparable_figures_is_not_decided(text):
    rc = deliver("Economics", "economics-specialist", text)
    assert not [fc for fc in rc.formal_checks if "share" in fc.detail and "50% of 4000" not in text] or not errors(rc)
    assert not errors(rc), errors(rc)


def test_the_share_readers_are_bounded_and_read_only_the_general_reading():
    assert quant._IS_SHARE_OF_RE.search("$40m, which is 25% of total sales of $200m")
    assert not quant._IS_SHARE_OF_RE.search("5%, which is 2% of the labour force of 40 million")
    spec_text = "Exports were $40m, which is 25% of total sales of $200m."
    checks = quant.extract_quant_checks(spec_text, request_id="r", claim_id="c")
    assert any(c.kind == "share" for c in checks)


# ------------------------------------------------------------------------------------------------ criterion marks


def test_criterion_marks_are_decided_against_their_maxima_and_the_total():
    wrong = "Criterion A: 6/5. Criterion B: 4/5. Criterion C: 4/5. Criterion D: 3/5. Total: 14/20.\n\nThe essay analyses the poem well."
    rc = deliver("English A: Literature", "english-specialist", wrong, request="Mark my essay against the criteria and give a total.", task_type="marking_feedback")
    named = [f.message for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert any("Criterion A: 6/5" in m for m in named) and any("the sum of the 4 part marks" in m for m in named), named
    right = "Criterion A (Knowledge and understanding): 4 out of 5\nCriterion B – 4/5\nCriterion C: 3/5\nCriterion D: 3/5\nTotal: 14/20\n\nThe essay analyses the poem well."
    rc = deliver("English A: Literature", "english-specialist", right, request="Mark my essay against the criteria and give a total.", task_type="marking_feedback")
    assert not errors(rc) and len([fc for fc in rc.formal_checks if "-marks-" in fc.constraint_id]) == 6
    rc = deliver("English A: Literature", "english-specialist", wrong, request="Write an essay.", task_type="essay")
    assert not [fc for fc in rc.formal_checks if "-marks-" in fc.constraint_id]  # outside a marking task the marks are not read


# --------------------------------------------------------------------------------- the English pack that fails to load


def test_an_english_pack_that_cannot_be_loaded_is_named(monkeypatch):
    text = "The writer presents work as endless."
    report = SpecialistReport(report_id="rep", request_id="r", task_id="t", agent_id="english-specialist", subject="English A: Literature",
                              task_type="analytical_paragraph", original_response=text, response_sha256=sha256_text(text), claims=[],
                              created_at="2026-11-06T10:00:00Z")
    monkeypatch.setitem(sys.modules, "epinoic_logic.adapters.english_specialist.structural", None)  # the import raises
    [f] = EnglishPack().checks(report)
    assert f.code == "ES-INTERNAL-001" and f.severity == "warning" and "could not be loaded" in f.message


# ------------------------------------------------------------------------- near-miss names of the supplied case (case-name)

TIDEWELL = SuppliedText(document_id="doc-tidewell", title="Tidewell Kayaks (case study)", author="Task data",
                        text="Tidewell Kayaks is a small firm in Port Elsa that makes sea kayaks. Its owner, Mara Quillon, sells 1,200 kayaks "
                             "a year at $45 each to shops in Calvessa and in the Calvessan capital.")


def case_names(rc) -> list:
    return [f for f in rc.structural_findings if f.code == "CORE-SRC-008"]


def test_a_near_miss_of_the_case_business_name_is_named():
    """Breadth probe B19: the business written 'Tidewater Kayaks' on the Tidewell Kayaks case."""
    rc = deliver("Business Management", "business-management-specialist", "Tidewater Kayaks should keep its price at $45.",
                 request="Should the firm keep its price? Use the case.", texts=(TIDEWELL,))
    [f] = case_names(rc)
    assert f.severity == "warning" and "'Tidewater'" in f.message and "'Tidewell'" in f.message and "doc-tidewell" in f.message, f.message
    assert f.claim_ids and not errors(rc)
    # control: the name as the case writes it
    rc = deliver("Business Management", "business-management-specialist", "Tidewell Kayaks should keep its price at $45.",
                 request="Should the firm keep its price? Use the case.", texts=(TIDEWELL,))
    assert not case_names(rc)


@pytest.mark.parametrize("answer", [
    "Tidewell Kayaks sells to the Calvessan shops, so the Calvessans pay $45.",          # a derived form of a case name
    "Tidewell Kayaks could follow the pricing of Tidewater Marine, which the question names.",   # a name the request states
    "Mara Quillon should keep the price of Tidewell Kayaks at $45.",                     # every name as the case writes it
    "Tidewater regions flood often, so Tidewell Kayaks sells more kayaks in spring.",   # a capital a sentence opening gives
    'The case says "Tidewater Kayaks is a small firm", so it should keep its price.',   # inside a quotation: INT-REQ-003's fault
    "Tidewell Kayaks should copy Calvert Boats, a rival.",                              # four shared letters: another name
    "Tidewell Kayaks should keep its price; Port Elsa shops agree.",                    # a two-word place the case states
])
def test_control_a_name_the_case_or_the_request_states_or_another_name_is_not_named(answer):
    rc = deliver("Business Management", "business-management-specialist", answer,
                 request="Should the firm keep its price? Compare it with Tidewater Marine. Use the case.", texts=(TIDEWELL,))
    assert not case_names(rc), [f.message for f in case_names(rc)]


def test_the_recorded_bm_p8a_answer_with_brackwood_for_brackwater_is_named():
    """The round's results audit: 'If Brackwater buys on the strength' changed to 'If Brackwood buys ...' in the recorded bm-p8a
    answer drew no finding. The answer writes Brackwater elsewhere, so the near miss is named; the recorded answer is clean."""
    import json
    import pathlib
    material = json.loads((pathlib.Path(__file__).resolve().parents[1] / "channel" / "data" / "c1_core_material.json").read_text(encoding="utf-8"))
    item = material["specialists"]["bm-p8a"]
    texts = tuple(SuppliedText(**t) for t in item["supplied_texts"])
    genuine = item["response_text"]
    assert "If Brackwater buys on the strength" in genuine
    kw = dict(request=item["question"], task_type=item["task_type"], texts=texts)
    rc = deliver("Business Management", "business-management-specialist", genuine, **kw)
    assert not case_names(rc)
    rc = deliver("Business Management", "business-management-specialist", genuine.replace("If Brackwater buys", "If Brackwood buys", 1), **kw)
    [f] = case_names(rc)
    assert "'Brackwood'" in f.message and "'Brackwater'" in f.message and "the answer also writes 'Brackwater'" in f.message


def _letters(n: int, k: int = 3) -> str:
    """``n`` written in ``k`` lower-case letters: distinct words for distinct numbers (a name holds no digit)."""
    return "".join(chr(97 + n // 26 ** i % 26) for i in range(k))


@pytest.mark.parametrize("name,response,case_text,found,unread", [
    ("15,000 distinct names sharing the case names' opening",
     " ".join(f"and Abcdef{_letters(n)}" for n in range(15_000)), " ".join(f"and Abcdeg{_letters(n)}" for n in range(15_000)), 0, 15_000 - 2048),
    ("one run of 20,000 capitalised words (the run writes the case's 'Abcdexy' too)", " ".join(f"Abcde{_letters(n, 2)}" for n in range(20_000)),
     "The Abcdexy Kayaks firm. " * 2000, 16, 0),
    ("a near miss on every name, each beside the same word",
     " ".join(f"and Qwertyv{_letters(n)} Garden" for n in range(15_000)), " ".join(f"and Qwertyu{_letters(n)} Garden" for n in range(15_000)), 16,
     15_000 - 2048),
], ids=["distinct names", "one run", "near misses"])
def test_the_case_name_reader_is_bounded_on_hostile_names(name, response, case_text, found, unread):
    """The reader compares an answer name only with the case names that share its first five letters, at most 32 of them, reads
    at most 2,048 such answer names and reports at most 16 near misses: hostile input costs at most their product, and the names
    past the read bound are counted, never passed over unsaid."""
    from epinoic_logic.branches.packs import near_miss_names
    doc = SuppliedText(document_id="d", title="Case", text=case_text)
    timing = measure(lambda: near_miss_names(response, [doc], "Use the case."), bound=4.0, repeat=3, label=f"case names, {name}")
    assert timing.holds, timing
    assert all((len(r.found), r.unread) == (found, unread) for r in timing.results), [(len(r.found), r.unread) for r in timing.results]


def test_names_past_the_read_bound_are_reported_not_passed_over():
    """An answer with 3,000 names that share their opening with the case's names and that no supplied text states: the first 2,048
    are compared, and the 952 others are named on the receipt as not compared (CORE-SRC-008, warning), never dropped unsaid."""
    from epinoic_logic.branches.packs import CorePack
    text = " ".join(f"and Abcdef{_letters(n)}" for n in range(3000))
    doc = SuppliedText(document_id="d", title="Case", text=" ".join(f"and Abcdeg{_letters(n)}" for n in range(100)))
    rep = SpecialistReport(report_id="r", request_id="q", task_id="t", agent_id="a", subject="Business Management", task_type="short_answer",
                           original_response=text, response_sha256=sha256_text(text), supplied_texts=[doc], claims=[], created_at="2026-11-06T10:00:00Z")
    [f] = CorePack._near_miss_case_names(rep, "Use the case.")
    assert f.code == "CORE-SRC-008" and f.severity == "warning" and "952 more" in f.message and "not compared" in f.message, f.message
    small = text[: text.index(" and Abcdef" + _letters(2000))]
    assert not CorePack._near_miss_case_names(rep.model_copy(update={"original_response": small, "response_sha256": sha256_text(small)}), "Use the case.")


# ------------------------------------------------------------------------------------- the quotation scans are linear


def _pairwise(keys):
    return {k for k in keys if any(k != o and re.search(rf"(?<!\w){re.escape(k)}(?!\w)", o) for o in keys)}


def test_the_absorbed_quotations_are_those_of_the_pairwise_reading():
    rng = random.Random(8)
    vocab = ["a", "b", "killed", "we", "him", "openly", "¿qué", "x-y", "día", "the", "it's"]
    for _ in range(3000):
        keys = [" ".join(rng.choice(vocab) for _ in range(rng.randint(1, 4))) for _ in range(rng.randint(1, 12))]
        assert _absorbed_quotation_keys(keys) == _pairwise(keys), keys
    assert _absorbed_quotation_keys(["killed", "we killed him openly", "the verb"]) == {"killed"}


@pytest.mark.parametrize("name,keys", [
    ("two words", [" ".join(random.Random(n).choice(["a", "b"]) for _ in range(1 + n % 14)) for n in range(16_000)]),
    ("distinct", [f"w{n} zz{n}" for n in range(16_000)]),
    ("one long and many short", ["a " * 4000] + [f"a{n}" for n in range(16_000)]),
])
def test_the_absorbed_quotations_are_found_in_linear_time(name, keys):
    timing = measure(lambda: len(_absorbed_quotation_keys(keys)), bound=4.0, repeat=3, label=f"absorbed quotations, {name}")
    assert timing.holds, timing


def test_nearest_text_reads_each_supplied_text_once():
    rng = random.Random(1)
    words = ["".join(rng.choice("abcdefghijklmnop") for _ in range(6)) for _ in range(3000)]
    doc = SuppliedText(document_id="d1", text=" ".join(words))
    assert nearest_text(f"{words[0]} {words[1]} zzqq", {"d1": doc}) == ("d1", ["'zzqq'"])
    timing = measure(lambda: [nearest_text(f"{words[i % 3000]} zzqq{i}", {"d1": doc}) for i in range(4000)], bound=4.0, repeat=3,
                     label="nearest_text, 4,000 quotations against a 21,000-character text")
    assert timing.holds, timing
    assert folded_vocabulary.cache_info().currsize >= 1


@pytest.mark.parametrize("label,severity", [("From memory, the text says", "info"), ("The text says", "warning")])
def test_quotations_in_labelled_sentences_are_read_in_linear_time(label, severity):
    """Every quotation was searched for in every sentence (quadratic when each quotation's sentence carries a from-memory label,
    the case where the search cannot stop early); the labelled sentences are now searched once, as one text."""
    from epinoic_logic.branches.packs import CorePack
    rng = random.Random(2)
    words = ["".join(rng.choice("abcdefghijklmnop") for _ in range(6)) for _ in range(3000)]
    doc = SuppliedText(document_id="d1", text=" ".join(words))
    text = " ".join(f"{label} «{words[i % 3000]} zz{i}»." for i in range(8000))
    rep = SpecialistReport(report_id="r", request_id="q", task_id="t", agent_id="a", subject="Economics", task_type="short_answer",
                           original_response=text, response_sha256=sha256_text(text), supplied_texts=[doc], claims=[], created_at="2026-11-06T10:00:00Z")
    timing = measure(lambda: CorePack._unverifiable_quotations(rep, True), bound=4.0, repeat=3, label=f"8,000 quotations, {label!r}")
    assert timing.holds, timing
    [f] = timing.results[0]
    assert f.code == "CORE-SRC-003" and f.severity == severity


def test_an_answer_of_many_short_quotations_crosses_the_hub_in_linear_time():
    """2,000 short altered quotations against a 21,000-character text took 10 s to receive (18 s of it in the core pack's
    pairwise comparison, 10 s in nearest_text under the profiler); 4,000 now take about 2 s."""
    rng = random.Random(1)
    words = ["".join(rng.choice("abcdefghijklmnop") for _ in range(6)) for _ in range(3000)]
    doc = SuppliedText(document_id="d1", text=" ".join(words))
    answer = " ".join(f"The text says «{words[i % 3000]} zzqq{i}»." for i in range(4000))
    timing = measure(lambda: deliver("Language B: Spanish", "spanish-specialist", answer, request="Lee el texto y responde.", texts=(doc,)),
                     bound=20.0, repeat=1, label="4,000 short altered quotations through the hub")
    assert timing.holds, timing
    rc = timing.results[0]
    assert len([f for f in rc.findings if f.code == "INT-REQ-003"]) >= 500


# --------------------------------------------------------------------------------------------- the class sweep


def _branch_entries(text: str):
    report = SpecialistReport(report_id="rep", request_id="r", task_id="t", agent_id="english-specialist", subject="English A: Literature",
                              task_type="marking_feedback", original_response="Criterion A: 4/5. " + text[:200_000],
                              response_sha256=sha256_text("Criterion A: 4/5. " + text[:200_000]), claims=[], created_at="2026-11-06T10:00:00Z")
    from epinoic_logic.branches.packs import _marks_formal
    yield "share of (part first)", lambda: list(quant._IS_SHARE_OF_RE.finditer("$40m, which is 25% of " + text))
    yield "share of (whole last)", lambda: list(quant._IS_SHARE_OF_RE.finditer(text + " 40 is 25% of total sales of $200m"))
    yield "share in brackets", lambda: quant._PAREN_SHARE_AFTER_RE.match(" owned" + text + " (40%)")
    yield "quant checks", lambda: quant.extract_quant_checks("Of the 60 households, 27 owned " + text, request_id="r", claim_id="c")
    yield "criterion marks", lambda: _marks_formal(report, "core")
    yield "absorbed quotations", lambda: _absorbed_quotation_keys(text.split()[:20_000] or [text])
    yield "nearest_text", lambda: nearest_text(text[:2000], {"d": SuppliedText(document_id="d", text=text)})
    from epinoic_logic.branches.packs import CorePack
    quoted = SpecialistReport(report_id="rep", request_id="r", task_id="t", agent_id="a", subject="Economics", task_type="short_answer",
                              original_response="From memory, «" + text[:200_000] + "»", response_sha256=sha256_text("From memory, «" + text[:200_000] + "»"),
                              supplied_texts=[SuppliedText(document_id="d", text="a text")], claims=[], created_at="2026-11-06T10:00:00Z")
    yield "unverifiable quotations", lambda: CorePack._unverifiable_quotations(quoted, True)
    from epinoic_logic.branches.packs import near_miss_names
    case = SuppliedText(document_id="d", title="Tidewell Kayaks", text="Tidewell Kayaks sells kayaks. " + text[:200_000])
    yield "case names (answer)", lambda: near_miss_names("Tidewater Kayaks " + text[:200_000], [case], "Use the case.").found
    yield "case names (case)", lambda: near_miss_names("The firm Tidewater Kayaks sells.", [case], text[:200_000]).found


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_handoff_branch_readers(shape):
    """Every reader this handoff added or rewrote in the branches, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_branch_entries, texts=one(shape))
