"""Integration gate 4 (critical input stalls): the claim ledger's readers are bounded on the largest syntheses the contract
admits, and a reading that stops at its bound says so.

The critical finding (deferred as a performance item by the core fixer, core-g4-perf-1): the aligned reading
(``ledger.aligned_changes``) ran ``difflib.SequenceMatcher(autojunk=False)`` over the light-stemmed tokens of a synthesized
claim against each cited claim, all of them joined and sentence by sentence. The search for each common run walks every
pair of equal tokens of its ranges, and the decomposition repeats it once per run, so a claim of 250 short sentences of
few distinct words against cited claims of 4,000 characters took 3.1 s for one cited claim, 12 s for two and 25 s for
four; a claim may cite 64 and a synthesis hold 512 claims. The reading is now its own exact decomposition
(``ledger._common_runs``, the opcodes difflib gives, held equal below) under a step bound per claim and per synthesis
(rule ``align-bound``): a reading that stops is named in INT-LEDGER-026, never read as compared.

The class sweep of ``integrity/ledger.py`` (the same kinds of pattern: a scan repeated for every token, claim or marker):

* every cited claim, and each of its sentences, was tokenized and read again for every synthesized claim citing it, and
  the aligned reading twice per claim: the per-text readings are kept per text (``ledger._KEPT_TEXT_CHARS``);
* the name rules read the other claims of every cited report again for every synthesized claim, twice
  (``_mid_capitalised``; the parser-safety lens measured 40.9 s for 195 claims of a 195-claim report), and the
  synthesized claim's own words again for every name of every cited claim (``substituted_names``);
* the per-claim readers read each claim and everything it cites, so 512 claims each citing 64 claims of 4,000 characters
  read 133 million characters (hours): they compare at most ``LEDGER_READ_BOUND`` characters per synthesis (rule
  ``read-bound``), and a claim past the bound is named;
* every quotation of a claim is searched for in every text in scope (``unlocated_quotations``,
  ``quotation_form_differences``, ``misattributed_quotations``): the searches of one synthesis are bounded by
  ``QUOTE_SCAN_BOUND`` (rule ``quote-bound``), and a claim past the bound is named;
* the both-sides sweep below found two more readers that looked a value up again for every figure: ``unit_differences``
  read every occurrence of a value in the sources for every figure of the claim, and ``_figure_differences`` every figure
  of the sources for every scaled figure (both quadratic on a repeated figure); each reads them once per value now.

Every bound is far above the largest synthesis of the recorded rounds (3,350 characters compared, under 2,000 alignment
steps per claim) and of the test corpus (31,448 characters): the receipts, findings and statuses of the recorded rounds
are unchanged. CPU-time bounds carry a wide margin (the measured times are in each test's comment).
"""
from __future__ import annotations

import random
import time
from difflib import SequenceMatcher

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity import ledger as L
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

from ..core_hostile import HOSTILE, sweep
from ..timing import empty_caches

# the finding's shape: 250 short sentences of few distinct words, and cited claims of 4,000 characters framed as views
STALL_CLAIM = " ".join(f"w0a{i} w0b{i} w0c{i}." for i in range(250))[:4000]


def stall_source(c: int) -> str:
    return " ".join(f"Taylor argues that w{c}a{i} w{c}b{i} w{c}c{i}." for i in range(125))[:4000]


def _cpu(fn):
    empty_caches()
    t0 = time.process_time()
    out = fn()
    return time.process_time() - t0, out


def _report(rid: str, agent: str, texts: list[str], *, subject: str = "History") -> SpecialistReport:
    base = dict(request_id="req", task_id="task", report_id=rid, agent_id=agent, subject=subject, task_type="short_answer")
    text = " ".join(texts)
    return SpecialistReport(**base, original_response=text, response_sha256=sha256_text(text), created_at="2026-11-01T00:00:00Z",
                            claims=[ClaimRecord(**base, claim_id=f"{rid}-c{i}", claim_text=t, claim_role="point", materiality="supporting",
                                                certainty="probable") for i, t in enumerate(texts)])


def _synthesis(reports: list[SpecialistReport], claims: list[tuple[str, list[str]]], transformation: str = "merged") -> Synthesis:
    sc = [SynthesizedClaim(claim_id=f"s{i}", text=t, source_claim_ids=ids, transformation=transformation, certainty="probable")
          for i, (t, ids) in enumerate(claims)]
    text = " ".join(t for t, _ids in claims)[:400_000]
    return Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator",
                     source_report_ids=[r.report_id for r in reports], claims=sc, text=text, text_sha256=sha256_hex(text),
                     created_at="2026-11-01T01:00:00Z")


# ===================================================================================== the alignment: exact and bounded
def _difflib_opcodes(a: list[str], b: list[str]):
    return SequenceMatcher(None, a, b, autojunk=False).get_opcodes()


def test_the_bounded_decomposition_gives_the_opcodes_difflib_gave():
    """The aligned reading's own decomposition is the one it read before (difflib without junk heuristics), on random
    token lists of few and many distinct tokens, near copies, and lists longer than difflib's 200-token junk threshold."""
    rng = random.Random(20261101)
    for _ in range(4000):
        alphabet = rng.choice([2, 3, 5, 12, 40])
        a = [str(rng.randrange(alphabet)) for _ in range(rng.randint(0, 36))]
        b = [str(rng.randrange(alphabet)) for _ in range(rng.randint(0, 36))]
        if a and rng.random() < 0.4:
            b = list(a)
            for _ in range(rng.randint(0, 4)):
                k = rng.random()
                if k < 0.4 and b:
                    b[rng.randrange(len(b))] = str(rng.randrange(alphabet + 2))
                elif k < 0.7:
                    b.insert(rng.randint(0, len(b)), str(rng.randrange(alphabet)))
                elif b:
                    del b[rng.randrange(len(b))]
        assert L._align_opcodes(a, b, L._AlignBudget(10**12)) == _difflib_opcodes(a, b), (a, b)
    for _ in range(40):
        a = [str(rng.randrange(30)) for _ in range(rng.randint(200, 500))]
        b = a[: len(a) // 3] + [str(rng.randrange(30)) for _ in range(50)] + a[len(a) // 3:]
        assert L._align_opcodes(a, b, L._AlignBudget(10**12)) == _difflib_opcodes(a, b)


_PROSE_WORDS = ("the of and to in a that was for on as with by it from were which at be this had not are but have an they their "
                "emigration closure border flow fell rose sharply route sealed government workers refugees economy wall pressure "
                "historians argue policy treaty war ended began signed peace collapse famine harvest prices wages limited large").split()


def _prose(rng: random.Random, sentences: int) -> str:
    out = []
    for _ in range(sentences):
        ws = [rng.choice(_PROSE_WORDS) for _ in range(rng.randint(6, 16))]
        if rng.random() < 0.4:
            ws.insert(rng.randint(1, len(ws) - 1), str(rng.choice([1914, 1918, 1961, 12, 40, 3.5])))
        out.append(" ".join(ws).capitalize() + ".")
    return " ".join(out)


def test_the_aligned_reading_of_ordinary_text_is_the_one_difflib_gave(monkeypatch):
    """aligned_changes and aligned_differences, read with the bounded decomposition and with difflib's opcodes, give the same
    changes on edited copies of ordinary prose (a word replaced, a negation added, a figure changed, words inserted)."""
    rng = random.Random(7)
    cases = []
    for _ in range(150):
        src = _prose(rng, rng.randint(1, 4))
        words = src.split()
        for _ in range(rng.randint(1, 3)):
            k = rng.random()
            i = rng.randrange(len(words))
            if k < 0.35:
                words[i] = rng.choice(_PROSE_WORDS + ["not", "1919", "two", "three"])
            elif k < 0.6:
                words.insert(i, rng.choice(["not", "never", "at least", "only"]))
            elif len(words) > 3:
                del words[i]
        cases.append((" ".join(words), [src, _prose(rng, 1)]))
    bounded = [(L.aligned_changes(syn, srcs[0]), L.aligned_differences(syn, srcs)) for syn, srcs in cases]
    monkeypatch.setattr(L, "_align_opcodes", lambda a, b, budget: _difflib_opcodes(list(a), list(b)))
    reference = [(L.aligned_changes(syn, srcs[0]), L.aligned_differences(syn, srcs)) for syn, srcs in cases]
    assert bounded == reference
    assert any(f or m for (f, m), _d in bounded), "the edited copies are read as changed"


def test_an_ordinary_claim_spends_a_small_part_of_the_bound():
    """The largest claim of the recorded rounds and of the test corpus spends under 2,000 steps; a claim of 4,000 characters of
    prose against a copy of itself, and against 8 cited claims of 4,000 characters, stays far under the bound."""
    rng = random.Random(3)
    claim = _prose(rng, 40)[:4000]
    sources = [_prose(random.Random(100 + c), 40)[:4000] for c in range(8)]
    for srcs in ([claim], sources):
        budget = L._AlignBudget(L.ALIGN_STEP_BOUND)
        _figures, meaning = L.aligned_differences(claim, srcs, budget=budget)
        assert not any("rule align-bound" in m for m in meaning)
        assert L.ALIGN_STEP_BOUND - budget.left < L.ALIGN_STEP_BOUND // 4


@pytest.mark.parametrize("cited", [1, 4, 64])
def test_the_finding_s_worst_case_is_bounded_and_named(cited):
    """The finding's shape: 3.1 s for one cited claim, 25 s for four before the gate; now about 0.7 s whatever the number of
    cited claims (64 included), and the reading that stopped is named."""
    sources = [stall_source(c) for c in range(cited)]
    spent, (figures, meaning) = _cpu(lambda: L.aligned_differences(STALL_CLAIM, sources))
    assert spent < 8.0, spent
    assert any("rule align-bound" in m and "not compared word for word" in m for m in meaning), meaning
    spent, described = _cpu(lambda: L.meaning_differences(STALL_CLAIM, sources, "merged"))
    assert spent < 12.0, spent  # about 0.7 s at one cited claim, 2 s at 64 (the other readers read 64 claims)
    assert any("rule align-bound" in d for d in described)


def test_one_claim_citing_64_claims_of_the_finding_s_shape_is_checked_in_seconds():
    """Before the gate this one claim took minutes; about 3 s now, with the stopped reading named in INT-LEDGER-026."""
    rep = _report("ra", "history-specialist", [stall_source(c) for c in range(64)])
    syn = _synthesis([rep], [(STALL_CLAIM, [c.claim_id for c in rep.claims])])
    spent, found = _cpu(lambda: L.check_synthesis_ledger([rep], syn))
    assert spent < 40.0, spent
    assert any(f.code == "INT-LEDGER-026" and f.severity == "warning" and "rule align-bound" in f.message for f in found)


def test_the_steps_of_one_synthesis_are_bounded_too():
    """Many claims of the finding's shape: each claim spends at most ALIGN_STEP_BOUND of the synthesis's
    ALIGN_CHECK_STEP_BOUND, then the claims after it are named with the synthesis's bound."""
    rep = _report("ra", "history-specialist", [stall_source(c) for c in range(2)])
    ids = [c.claim_id for c in rep.claims]
    syn = _synthesis([rep], [(STALL_CLAIM[:3990].replace("w0a1 ", f"w0a1 v{k} "), ids) for k in range(9)])
    spent, found = _cpu(lambda: L.check_synthesis_ledger([rep], syn))
    assert spent < 60.0, spent  # about 5 s: six claims at the claim bound, then the synthesis's bound is spent
    notes = [f for f in found if f.code == "INT-LEDGER-026" and "rule align-bound" in f.message]
    assert len(notes) == 9
    assert any("for the whole synthesis" in f.message for f in notes)


# ===================================================================================== the synthesis: read-bound and quote-bound
def _prose_source(seed: int) -> str:
    return _prose(random.Random(seed), 60)[:3990]


def test_a_synthesis_at_the_contract_caps_is_checked_in_seconds_and_every_claim_past_the_bound_is_named():
    """512 claims, each citing 64 claims of 4,000 characters: 133 million characters for the per-claim readers (about 20 s per
    claim before the gate: hours); about 5 s now. The first claim is compared; every other claim is named, and the
    structural rules still read it."""
    reports = [_report("ra", "history-specialist", [_prose_source(c) for c in range(32)]),
               _report("rb", "english-specialist", [_prose_source(100 + c) for c in range(32)], subject="English A: Literature")]
    ids = [c.claim_id for r in reports for c in r.claims]
    claim = _prose(random.Random(9), 40)[:3990]
    syn = _synthesis(reports, [(claim, ids)] * 1 + [(claim + f" v{k}.", ids) for k in range(511)])
    spent, found = _cpu(lambda: L.check_synthesis_ledger(reports, syn))
    assert spent < 90.0, spent
    named = [f for f in found if f.code == "INT-LEDGER-026" and "rule read-bound" in f.message]
    assert len(named) == 511 and all(f.severity == "warning" and "not shown as compared" in f.message for f in named)
    assert {f.claim_ids[0] for f in named} == {f"s{k}" for k in range(1, 512)}


def test_an_ordinary_synthesis_is_compared_whole():
    """A synthesis of 40 claims each citing three claims of 600 characters (72,000 characters compared) is read whole: no
    bound is named, and a changed figure in its last claim is still an error."""
    rng = random.Random(11)
    texts = [_prose(rng, 6)[:600] + " It ended in 1918." for _ in range(120)]
    rep = _report("ra", "history-specialist", texts)
    claims = [(texts[3 * k] + " " + texts[3 * k + 1], [f"ra-c{3 * k}", f"ra-c{3 * k + 1}", f"ra-c{3 * k + 2}"]) for k in range(40)]
    claims[-1] = (claims[-1][0].replace("1918", "1921"), claims[-1][1])
    found = L.check_synthesis_ledger([rep], _synthesis([rep], claims))
    assert not [f for f in found if "rule read-bound" in f.message or "rule align-bound" in f.message or "rule quote-bound" in f.message]
    assert any(f.code == "INT-LEDGER-023" and f.claim_ids[0] == "s39" and "1921" in f.message for f in found)


def test_the_quotation_searches_of_a_synthesis_are_bounded_and_named():
    """A claim of 585 invented quotations searched in four responses of 400,000 characters (and an invented quotation in an
    ordinary claim before it, still named INT-LEDGER-025): the searches stop at the synthesis's bound and the claim past it is
    named."""
    rng = random.Random(5)
    words = "the of and to in emigration closure border flow fell sharply route sealed government workers".split()
    big = [" ".join(rng.choice(words) for _ in range(70_000))[:400_000] for _ in range(4)]
    reports = [_report(f"r{k}", "history-specialist" if k == 0 else f"agent{k}-specialist", [t[:300]]) for k, t in enumerate(big)]
    reports = [r.model_copy(update={"original_response": t, "response_sha256": sha256_text(t)}) for r, t in zip(reports, big)]
    quotes = " ".join(f'"q{i}"' for i in range(600))[:3990]  # about 585 quotations
    syn = _synthesis(reports, [('The closure was "a velvet curtain of steel".', ["r0-c0"]), (quotes, ["r0-c0"])])
    spent, found = _cpu(lambda: L.check_synthesis_ledger(reports, syn))
    assert spent < 60.0, spent  # one ordinary claim; then 585 quotations x 1.6 million characters exceed the bound
    assert any(f.code == "INT-LEDGER-025" and f.claim_ids[0] == "s0" for f in found), "the ordinary claim's invented quotation is named"
    assert any(f.code == "INT-LEDGER-026" and f.claim_ids[0] == "s1" and "rule quote-bound" in f.message for f in found)
    assert not any(f.code == "INT-LEDGER-025" and f.claim_ids[0] == "s1" for f in found)


def test_the_other_claims_of_a_cited_report_are_read_once_per_check():
    """The parser-safety lens's shape (rules name-substitution and name-introduction read the other claims of the cited
    report for every synthesized claim, twice): 195 synthesized claims citing one claim of a 195-claim report of
    2,000-character claims took 37.5 s before the gate; about 1 s now, with the same findings."""
    src = "In 1923 Stresemann ended passive resistance in the Ruhr and the mark was stabilised."
    other = ((src + " ") * 30)[:1990]
    rep = _report("rh", "history-specialist", [src] + [other] * 194)
    syn = _synthesis([rep], [(src, ["rh-c0"])] * 195, transformation="paraphrased")
    spent, found = _cpu(lambda: L.check_synthesis_ledger([rep], syn))
    assert spent < 15.0, spent
    assert not [f for f in found if f.severity == "error"]


def test_the_synthesized_claim_s_words_are_read_once_for_the_name_rule():
    """substituted_names read the synthesized claim's words again for every name of every cited claim: 64 cited claims of
    many names against a claim of many names is read in well under a second now."""
    names = " ".join(f"Qa{i}x met Qb{i}y in Qc{i}z." for i in range(120))[:3990]
    sources = [" ".join(f"Rd{c}{i}u met Re{c}{i}v in Rf{c}{i}w." for i in range(110))[:3990] for c in range(64)]
    spent, _out = _cpu(lambda: L.substituted_names(names, sources, "paraphrased"))
    assert spent < 10.0, spent


# ===================================================================================== the class sweep: hostile text on both sides
_PAIR_ENTRIES = ("aligned_differences", "figure_pairing_differences", "unit_differences", "dropped_hedges", "dropped_qualifiers",
                 "dropped_attributions", "no_change_differences", "reversed_voices", "reversed_comparisons", "day_month_differences")
_LABELLED_ENTRIES = ("meaning_differences", "meaning_inversions", "substituted_names")


def _both_sides_entries(text: str):
    """Every public pair reader of the module with the hostile run on BOTH sides: the synthesized claim and its cited claims
    are the run (the cited claims each a variant of it), at the run's full length and at the contract's claim cap, and the
    ledger check over a claim citing eight variants and eight claims citing the same eight."""
    full = [text + f" w{c}." for c in range(2)]
    capped_claim = text[:3900] + " s."
    capped = [text[:3880] + f" w{c}." for c in range(8)]
    yield "aligned_changes (run against run)", lambda: L.aligned_changes(text, full[0])
    for name in _PAIR_ENTRIES:
        fn = getattr(L, name)
        yield f"{name} (runs)", lambda fn=fn: fn(text, full)
        yield f"{name} (claims at the cap)", lambda fn=fn: fn(capped_claim, capped)
    for name in _LABELLED_ENTRIES:
        fn = getattr(L, name)
        yield f"{name} (runs)", lambda fn=fn: fn(text, full, "paraphrased")
        yield f"{name} (claims at the cap)", lambda fn=fn: fn(capped_claim, capped, "merged")
    yield "introduced_names (claims at the cap)", lambda: L.introduced_names(capped_claim, capped, "merged", stated_elsewhere=set())
    if capped_claim.strip(" s.") and all(c.strip() for c in capped):
        rep = _report("ra", "history-specialist", capped)
        ids = [c.claim_id for c in rep.claims]
        yield "check_synthesis_ledger (one claim citing eight)", lambda: L.check_synthesis_ledger([rep], _synthesis([rep], [(capped_claim, ids)]))
        yield "check_synthesis_ledger (eight claims citing eight)", lambda: L.check_synthesis_ledger(
            [rep], _synthesis([rep], [(capped_claim.replace(" s.", f" s{k}."), ids) for k in range(8)]))


@pytest.mark.parametrize("shape", sorted(HOSTILE))
def test_sweep_ledger_pair_readers_with_hostile_text_on_both_sides(shape):
    """The standard hostile runs (about 20,000 characters of blanks, tabs, line breaks, stops, closing marks, mark labels,
    parentheses, brackets, fence openers, number words joined by 'and', '=' links, list markers and the gate-2 and gate-3
    shapes, each followed by a character that defeats the match) on both sides of every pair reader: a quadratic reading
    (the aligned reading of integration gate 4) needs both sides long. One test per shape; the CPU bound per call is the
    gate-2 sweep's for a reader (4 s) and for the ledger check (12 s)."""
    texts = {shape: HOSTILE[shape]}
    slow = sweep(lambda t: ((n, c) for n, c in _both_sides_entries(t) if not n.startswith("check_synthesis_ledger")), texts=texts)
    slow += sweep(lambda t: ((n, c) for n, c in _both_sides_entries(t) if n.startswith("check_synthesis_ledger")), bound=12.0, texts=texts)
    assert not slow, slow


# ===================================================================================== instances the class sweep found
@pytest.mark.parametrize("unit", ["1–2–", "$5 ", "5 kg ", "1914 BC ", "5 per cent "])
def test_the_unit_reader_reads_each_value_of_the_sources_once(unit):
    """unit_differences read every occurrence of a value in the sources again for every figure of the claim: quadratic on a
    claim and sources of one repeated figure (dashed digits: 4.5 s at 20,000 characters, 16.6 s at 40,000; '$5': 5.3 s at
    20,000). Each value's eras, units and spellings are read once now: about 0.7 s at 40,000 characters."""
    run = (unit * (40_000 // len(unit) + 1))[:40_000]
    spent, _out = _cpu(lambda: L.unit_differences(run, [run + " w0.", run + " w1."]))
    assert spent < 4.0, spent


def test_the_unit_reader_still_names_what_it_named():
    assert L.unit_differences("The mass is 0.025 g. L is the length.", ["The mass is 0.025 kg."])
    assert L.unit_differences("It was founded in 1914 BC.", ["It was founded in 1914."]) == ["'1914 BC' where its cited sources state 1914 without an era (a year moved into BC)"]
    assert L.unit_differences("It rose 13 provinces.", ["It rose 13 per cent."])
    assert L.unit_differences("The speed is 15 m/s.", ["The speed is 15 m s⁻¹."]) == []


def test_the_scale_reader_reads_each_numeral_of_the_sources_once():
    """_figure_differences read every figure of the sources again for every scaled figure of the claim (0.18 s at 10,000
    characters, 0.54 s at 20,000, quadratic); each numeral's scale words are read once now."""
    syn = ("1 million " * 8000)[:80_000]
    src_text = ("1 billion " * 8000)[:80_000]
    spent, (_introduced, _dropped, rescaled) = _cpu(lambda: L._figure_differences(syn, [src_text]))
    assert spent < 4.0, spent
    assert rescaled == ["'1 million' where the cited sources state 1 billion (a changed scale word)"]
