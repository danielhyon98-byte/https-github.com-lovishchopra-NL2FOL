"""Integration gate 3 (parsers): the direction of a currency stated against an exchange-rate unit, and the reference corpus.

Correctness lens, finding 1 (major; History, core-quant pair_direction, INT-SUBJ-001). The pair reader read 'The franc fell from
25 to the pound in 1919 to 240 to the pound by 1926' as 'the later figure is below the earlier', so a correct statement that is
standard in IB History got an engine-backed INT-SUBJ-001 error and the answer was WITHHELD. An exchange rate written 'N to the
pound' is the price of one pound in the quoted currency (the franc), so a fall of the franc is a RISE of the figure. Now
(``branches.quant``, ``_xrate_reading``):

* the sentence names the quoted currency ('The franc fell', 'the value of the mark collapsed', 'Against the pound, the franc
  fell'): its direction is read as the inverse of the figure's, and checked by the engine, so 'The franc rose from 25 to the pound
  to 240 to the pound' is still a COUNTEREXAMPLE;
* it names the base currency ('The dollar rose from 4.2 to the dollar ...'): read as written;
* it names neither ('The exchange rate fell', 'It fell'): a direction that holds as written is checked as written, and one that
  holds only of the quoted currency is named undecided (CORE-QNT-001 with the reason), never an error;
* a derived change on such a pair ('a fall of about 90 per cent', 'fell by half', 'halved') holds when it holds of the figures
  as written or of the quoted currency's value (one pound over the figure); one said of the base currency ('a rise in the
  dollar's price of about 1,670-fold') is the figures' own; a change that holds under neither reading is still an error;
* exchange rates of two currencies ('to the pound' against 'to the dollar') are never compared.

The reference corpus of the general reading (``tests/branches/data/quant_general_reference.json``): the gate-3 self-certification
rule (``adapters.markdown.self_cert_vocabulary``, finding 2) changes CORE-SELF-001 on six of its 570 texts, which only mention
self-certification or hold capital status words in a table of fixtures. They carry their earlier digest as
``sha256_before_gate3``. Hold remedy c3b (the one self-certification reader, rules ``selfcert-1``) re-referenced 29 texts
(``sha256_before_c3b``); with their CORE-SELF findings removed, they reproduce the digest the code before c3b gave them with its
CORE-SELF findings removed, so the re-referenced digests differ from the earlier ones by the self-certification rule alone.
The stabilisation of c3b re-referenced four of them again (``sha256_before_stab2``); three of the four read again as they
read before c3b.
"""
from __future__ import annotations

import re
import time

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.branches import RouterHub, packs
from epinoic_logic.branches.quant import XRATE_OPEN_REASON, _named_currency, _xrate_reading, extract_quant_checks, undecided_quant_statements
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan

from ..growth import growth
from ..timing import empty_caches
from .test_quant_si_reading import REFERENCE, _digest

KEY = b"integration-gate-3-parsers-key-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one


def _receipt(sentence: str, subject: str = "History", agent: str = "history-specialist"):
    hub = RouterHub(signing_key=KEY, key_id="k", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, "Explain the economic changes of the period.", [])
    _reply, rc = hub.receive("t", m.message_id, "Economic change was rapid. " + sentence, agent_id=agent, report_id="r1")
    return rc


def _errors(rc) -> list:
    return [(f.code, f.message[:160]) for f in list(rc.findings) + list(rc.structural_findings) if f.severity == "error"]


def _verdicts(text: str) -> list[str]:
    return [verify(q.problem, config=CFG).status.value for q in extract_quant_checks(text, request_id="r", claim_id="c")]


# --------------------------------------------------------------------------- the finding's sentences and their class

#: Correct statements of a currency's direction against an exchange-rate unit: the finding's two (the expected outcome), and the
#: other subjects, wordings and derived figures of the class. Each is decided ENTAILED by the engine.
CORRECT = [
    "The franc fell from 25 to the pound in 1919 to 240 to the pound by 1926.",
    "The mark fell from about 60 to the dollar in early 1921 to about 7,000 by the end of 1922.",
    "The mark depreciated from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "The mark collapsed from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "The value of the mark fell from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "The mark's value fell from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "Against the pound, the franc fell from 25 to the pound in 1919 to 240 to the pound by 1926.",
    "The French franc fell from 25 to the pound in 1919 to 240 to the pound by 1926.",
    "The franc fell from 25 to the pound in 1919 to 240 in 1926.",
    "The rupee fell from 2 to the pound to 10 to the pound.",
    "The mark recovered, rising from 7,000 to the dollar to 4.2 to the dollar.",
    "The franc fell from 25 to the pound in 1919 to 240 to the pound by 1926 and the mark fell from 4.2 to the dollar to 7,000 to the dollar.",
    # the base currency named, and an exchange rate that rises as written: read as written
    "The dollar rose from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "The exchange rate rose from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    # derived figures: of the quoted currency's value, or of the rate as written
    "The franc fell from 25 to the pound in 1919 to 240 to the pound by 1926, a fall of 90 per cent.",
    "The franc fell from 25 to the pound in 1919 to 240 to the pound by 1926, a fall of about 90 per cent.",
    "The franc fell from 25 to the pound in 1919 to 240 to the pound by 1926, losing about nine-tenths of its value.",
    "The franc fell by half, from 25 to the pound to 50 to the pound.",
    "The franc halved, falling from 25 to the pound to 50 to the pound.",
    "The franc fell from 25 to the pound in 1919 to 240 to the pound by 1926, a tenfold fall.",
    "The franc collapsed from 25 to the pound in 1919 to 240 to the pound by 1926, a rise of 860 per cent in its price.",
    "The mark fell from 4.2 to the dollar in July 1914 to 7,000 to the dollar in December 1922, a rise in the dollar's price of about 1,670-fold.",
]


@pytest.mark.parametrize("sentence", CORRECT)
def test_a_correct_direction_of_a_currency_against_an_exchange_rate_is_no_error(sentence):
    rc = _receipt(sentence)
    assert _errors(rc) == [], (sentence, _errors(rc))
    assert [fc.formal_status for fc in rc.formal_checks] and all(fc.formal_status == "ENTAILED" for fc in rc.formal_checks), \
        (sentence, [(fc.constraint_id, fc.formal_status) for fc in rc.formal_checks])


def test_the_finding_sentences_are_entailed_with_the_inverse_reading_named():
    """The two sentences of the finding: the engine decides the quoted currency's fall as the figure's rise, and the check says so."""
    for text, quoted, base in (("The franc fell from 25 to the pound in 1919 to 240 to the pound by 1926.", "franc", "pound"),
                               ("The mark fell from about 60 to the dollar in early 1921 to about 7,000 by the end of 1922.", "mark", "dollar")):
        [check] = extract_quant_checks(text, request_id="r", claim_id="c")
        assert check.kind == "pair_direction" and check.problem.conclusion.expr.op == "gt"
        assert f"the price of one {base} in the {quoted}" in check.problem.conclusion.label
        assert verify(check.problem, config=CFG).status.value == "ENTAILED"


#: Faults: a direction or a derived figure that holds under no reading. Each stays an engine error (INT-SUBJ-001).
FAULTS = [
    "The franc rose from 25 to the pound to 240 to the pound.",
    "The mark rose from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "The mark recovered, falling from 7,000 to the dollar to 4.2 to the dollar.",
    "The dollar fell from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "The franc fell from 25 to the pound in 1919 to 240 to the pound by 1926, a fall of 50 per cent.",
    "The franc fell from 25 to the pound in 1919 to 240 to the pound by 1926, a fall of 860 per cent.",
    "The franc fell by a third, from 25 to the pound to 50 to the pound.",
]


@pytest.mark.parametrize("sentence", FAULTS)
def test_a_wrong_direction_or_change_of_a_currency_is_still_an_engine_error(sentence):
    rc = _receipt(sentence)
    assert any(code == "INT-SUBJ-001" for code, _m in _errors(rc)), (sentence, _errors(rc), [(fc.constraint_id, fc.formal_status) for fc in rc.formal_checks])
    assert any(fc.formal_status == "COUNTEREXAMPLE" for fc in rc.formal_checks)


@pytest.mark.parametrize("sentence", [
    "The exchange rate fell from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "It fell from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "Prices fell from 4.2 to the dollar in 1914 to 7,000 to the dollar in 1922.",
    "The exchange rate rose from 7,000 to the dollar to 4.2 to the dollar.",
])
def test_a_direction_that_holds_only_of_an_unnamed_currency_is_undecided_never_an_error(sentence):
    rc = _receipt(sentence)
    assert _errors(rc) == [] and not rc.formal_checks, (sentence, _errors(rc))
    [named] = [f for f in rc.structural_findings if f.code == "CORE-QNT-001"]
    assert named.severity == "warning" and "states the direction of an exchange rate" in named.message
    assert [u.reason for u in undecided_quant_statements("Economic change was rapid. " + sentence)] == [XRATE_OPEN_REASON]


@pytest.mark.parametrize("sentence", [
    "The franc fell from 25 to the pound in 1919 to 50 to the dollar in 1926.",
    "The franc fell from 25 to the pound in 1919 to 50 per head in 1926.",
])
def test_exchange_rates_of_two_currencies_are_never_compared(sentence):
    rc = _receipt(sentence)
    assert _errors(rc) == [] and not rc.formal_checks
    assert extract_quant_checks(sentence, request_id="r", claim_id="c") == []


def test_ordinary_pairs_keep_their_reading():
    """Negative controls: a pair in another unit, a currency sign, a rate per 1,000 and a derived figure are read as before."""
    assert _verdicts("The pound fell from $4.86 in 1931 to $3.40 in 1932.") == ["ENTAILED"]
    assert _verdicts("The pound rose from $4.86 in 1931 to $3.40 in 1932.") == ["COUNTEREXAMPLE"]
    assert _verdicts("The death rate fell from 30 per 1,000 in 1800 to 20 per 1,000 in 1900.") == ["ENTAILED"]
    assert _verdicts("Unemployment fell from 6 million in 1932 to 0.3 million in 1938, a fall of 95 per cent.") == ["ENTAILED"]
    assert _verdicts("Unemployment fell from 6 million in 1932 to 0.3 million in 1938, a fall of 50 per cent.") == ["COUNTEREXAMPLE"]
    assert _verdicts("The pound rose from 25 francs in 1919 to 240 francs in 1926.") == ["ENTAILED"]


@pytest.mark.parametrize("head,base,reading", [
    ("The franc fell ", "pound", ("inverse", "franc")),
    ("Against the pound, the franc fell ", "pound", ("inverse", "franc")),
    ("The value of the Reichsmark fell ", "dollar", ("inverse", "mark")),
    ("Sterling fell ", "pound", ("written", "pound")),
    ("The dollar rose ", "dollar", ("written", "dollar")),
    ("The exchange rate rose ", "dollar", ("open", "")),
    ("Priced in dollars, the mark fell ", "dollar", ("inverse", "mark")),
    ("The value of the dollar in marks rose ", "dollar", ("written", "dollar")),
])
def test_the_subject_of_the_direction_is_the_currency_the_sentence_names(head, base, reading):
    assert _xrate_reading([head], 0, base) == reading


def test_a_continued_pair_reads_the_subject_of_the_clause():
    """'..., and later fell from': a head of connectors, adverbs and a direction word continues the head before it."""
    assert _xrate_reading(["The franc fell ", ", and later fell "], 1, "pound") == ("inverse", "franc")
    assert _xrate_reading(["The franc fell ", " and prices rose "], 1, "pound") == ("open", "")


@pytest.mark.parametrize("make", [
    lambda n: "The franc fell against" + " " * n + "x from 25 to the pound to 240 to the pound.",
    lambda n: "The franc fell " + "against the pound " * (n // 18) + "from 25 to the pound to 240 to the pound.",
    lambda n: "The franc fell in" + "\t" * n + "marks from 25 to the pound to 240 to the pound.",
    lambda n: "The " + "franc " * (n // 6) + "fell from 25 to the pound to 240 to the pound, a fall of 90 per cent.",
    lambda n: "The franc fell from 25 to the pound to 240 to the pound" + ", and the mark fell from 4.2 to the dollar to 7,000 to the dollar" * 3
              + " " * n + "x.",
])
def test_the_exchange_rate_reader_is_linear_on_long_heads(make):
    def read(text):
        extract_quant_checks(text, request_id="r", claim_id="c")
        undecided_quant_statements(text)
        _named_currency(text)
    t = time.perf_counter()
    read(make(100_000))
    assert time.perf_counter() - t < 10.0
    ratio, small, large = growth(read, make(20_000), make(80_000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


# --------------------------------------------------------------------------- the reference corpus: six texts re-referenced

def _digest_without_self_certification(text: str) -> str:
    """The reference digest of ``text`` with every CORE-SELF finding of ``CorePack().checks`` removed (the same outputs as
    :func:`tests.branches.test_quant_si_reading._digest`, which the reference was computed with)."""
    import hashlib
    import json

    from epinoic_logic.branches.generic_parser import GenericTextParser

    out: dict = {}
    qc = extract_quant_checks(text, request_id="req", claim_id="rep:core")
    out["quant"] = [[q.check_id, q.kind, q.sentence, q.problem.model_dump(mode="json"), q.rule, q.basis, q.expected_if_consistent] for q in qc]
    out["undecided"] = [[u.paragraph, u.sentence, u.sentence_text, u.phrase, u.reason] for u in undecided_quant_statements(text)]
    try:
        rep = GenericTextParser("specialist").parse_response(text, request_id="req", task_id="task", report_id="rep", subject="History", task_type="essay")
    except Exception as exc:  # noqa: BLE001 - the reference records the exception's name
        out["core"] = repr(type(exc).__name__)
        return hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    pack = packs.CorePack()
    out["core_checks"] = [f.model_dump(mode="json") for f in pack.checks(rep, "Explain the figures.") if not f.code.startswith("CORE-SELF")]
    out["core_formal"] = [[fc.check_id, fc.kind, fc.description, fc.problem.model_dump(mode="json"), fc.expected_if_sound] for fc in pack.formal_checks(rep)]
    return hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def test_the_re_referenced_corpus_texts_differ_by_the_self_certification_rule_alone():
    """Rewritten for hold remedy c3b (one self-certification reader, rules selfcert-1; stricter, never weaker).

    Before c3b this test restored the vocabulary rule of the gate's base (``markdown.SELF_CERT_RE`` and the private fragments it
    was built from, all deleted by c3b) and showed every text reproduced its digest before gate 3. CorePack no longer consults
    that vocabulary, so the history cannot be replayed; the six gate-3 texts keep their recorded earlier digests, and the c3b
    re-reference is pinned by a stronger check over every re-referenced text: with its CORE-SELF findings removed, each text
    reproduces byte for byte the digest the code before c3b gave it with its CORE-SELF findings removed (recorded as
    ``sha256_c3b_without_self_certification``), so nothing but the self-certification rule changed."""
    gate3 = [item for item in REFERENCE["items"] if "sha256_before_gate3" in item]
    # (one of the six reads under c3b as it read before gate 3, so its current digest equals its gate-3 "before" digest again;
    # the record of the six is kept as data)
    assert len(gate3) == 6 and all(len(item["sha256_before_gate3"]) == 64 for item in gate3)
    # (rewritten for attack round 3 of c3b, stricter: that one, the fixture docstring of the translator's subjects, now names the bare
    # engine status of its table of expected displays again, so it is compared through its digest before attack round 3)
    assert sum(item["sha256_before_gate3"] == item.get("sha256_before_attack3", item["sha256"]) for item in gate3) == 1
    assert sum(item["sha256_before_gate3"] == item["sha256"] for item in gate3) == 0
    changed = [item for item in REFERENCE["items"] if "sha256_before_c3b" in item]
    assert len(changed) == 29
    # Rewritten for the stabilisation of c3b (the reader settled by meaning; stricter on status labels, never weaker): four of
    # the 29 were re-referenced again and carry their c3b digest as ``sha256_before_stab2``. Rule: a description of channel
    # behaviour is no self-certification, and a status word inside an identifier is read with the identifier's words (the bare
    # engine statuses beside it stay named), so exactly these three read again as they read before c3b and their digest equals
    # ``sha256_before_c3b``; every other c3b text, the fourth ('Expected: INCONSISTENT_PREMISES', now a status label) included,
    # still differs from its digest before c3b.
    restab = [item for item in REFERENCE["items"] if "sha256_before_stab2" in item]
    assert len(restab) == 4 and all("sha256_before_c3b" in item and item["sha256_before_stab2"] != item["sha256"] for item in restab)
    as_before_c3b = sorted(item["text"][:60] for item in changed if item["sha256_before_c3b"] == item["sha256"])
    # Rewritten for attack round 1 of c3b (stricter: the list names every text, one more by name): the docstring on two-claim
    # contradictions draws no self-certification under the sentence meaning layer and reads again as it read before c3b; it carries
    # its stabilised digest as ``sha256_before_attack1``.
    # Rewritten for attack round 3 of c3b (stricter: the fixture docstring of Example 1 now names its bare engine statuses again, the
    # 'FAITHFUL_CHAIN ... ENTAILED' rows, so it no longer reads as before c3b; it carries that earlier digest as
    # ``sha256_before_attack3``, and still differs by its CORE-SELF findings alone, checked below).
    # The History sentence quoting the minister reads again as before c3b: its quotation ('a parliament that could only say no ...') is
    # the subject matter's (boundary (b)), no self-certification; it carries its c3b digest as ``sha256_before_attack3``.
    assert as_before_c3b == sorted([
        " The minister called it «a parliament that could only say no",
        "A claim consistent on its own (its own distance gives its ow",
        "Channel behaviour found wanting by the round-4 arena oversee",
        "End to end through the hub, round 4: a correct quotation wri",
    ])
    attack3 = [item for item in changed if "sha256_before_attack3" in item]
    assert sorted(item["text"][:60] for item in attack3 if item["sha256_before_attack3"] == item["sha256_before_c3b"]) == [
        "Fixtures built from Example 1 of the English specialist's kn"]
    assert all("sha256_before_stab2" in item or "sha256_before_attack1" in item or "sha256_before_attack3" in item
               for item in changed if item["sha256_before_c3b"] == item["sha256"])
    assert [item["text"][:60] for item in REFERENCE["items"] if "sha256_before_attack1" in item] == [
        "A claim consistent on its own (its own distance gives its ow"]
    assert [item["text"][:80] for item in changed
            if _digest_without_self_certification(item["text"]) != item["sha256_c3b_without_self_certification"]] == []
    # and with the c3b rule every one of them gets its new digest (the reference test checks all 570)
    assert [item["text"][:80] for item in changed if _digest(item["text"]) != item["sha256"]] == []
