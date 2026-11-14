"""Round-9 clearance, second fix pass (c2b), handoff fixer: the student-facing text of a synthesis (the harness owner's handoff,
items 1 and 2; c2 communication fidelity, ll-t15).

* The deployed combinator port composes the text (``combinator_port.student_facing_text``): the claims' texts in order, joined
  by one space, each quotation claim another claim holds verbatim rendered only inside that claim, before or after it, a one-word
  quotation included; a quotation no other claim holds stays rendered. Every claim's text still occurs in the text and the text
  stays a composition of its claims, so the hub names nothing (INT-LEDGER-017, INT-LEDGER-031).
* Rule duplicated-content reads the student-facing text: a joined text names every quotation claim whose words it states outside
  the claims that hold them (held by any other claim, not only the next: p2-q03 two claims later, p3-q01 the claim before it);
  the composed text names none. The three-word floor stays for the warning.
* The readers are linear on hostile inputs at the contract's bounds.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.integration.combinator_port import student_facing_text
from epinoic_logic.integrity.ledger import contained_claims, quotation_holders, quotations_held_verbatim
from epinoic_logic.translate.contracts import sha256_text

from ..channel.c2_core_support import C2, by_code, deliver, file_synthesis, relay
from ..core_hostile import SHAPES, one, sweep

LL = C2["syntheses"]["ll-t15"]
TEXTS = [c["text"] for c in LL["claims"]]
SOURCES = [c["source_claim_ids"][0] for c in LL["claims"]]


def _index(source: str) -> int:
    return SOURCES.index(source)


def test_the_port_renders_a_held_quotation_only_inside_the_sentence_that_quotes_it():
    composed = student_facing_text(TEXTS)
    left_out = sorted(quotations_held_verbatim(TEXTS))
    # before the sentence (p1-q01, p1-s02); two before one sentence (p2-q03, p2-q04 before p2-s05); after it (p3-q01 after
    # p3-point); a one-word quotation ('"sink"' in p1-s03)
    for q in ("p1-q01", "p2-q03", "p2-q04", "p3-q01", "p1-q02"):
        assert _index(q) in left_out, q
    assert TEXTS[_index("p1-q02")] == '"sink"'
    assert composed == " ".join(t for i, t in enumerate(TEXTS) if i not in left_out)
    assert all(" ".join(t.split()).casefold() in " ".join(composed.split()).casefold() for t in TEXTS)  # every claim still occurs


def test_control_a_quotation_no_other_claim_holds_stays_rendered():
    texts = ['"Nobody else quotes this line at all"', "The writer turns to the budget.", '"twice quoted words here"', 'She says "twice quoted words here".']
    assert quotations_held_verbatim(texts) == {2}
    assert student_facing_text(texts) == '"Nobody else quotes this line at all" The writer turns to the budget. She says "twice quoted words here".'
    # two identical quotation claims hold each other's words but are the same quotation: neither is left out
    assert quotations_held_verbatim(['"the same three words"', '"the same three words"']) == set()


def test_rule_duplicated_content_reads_the_text_the_student_reads():
    joined = " ".join(TEXTS)
    named = contained_claims(TEXTS, joined)
    assert {_index(q) for q in ("p1-q01", "p2-q03", "p2-q04", "p3-q01")} <= set(named)
    assert _index("p1-q02") not in named  # one word: below the floor of the warning
    assert contained_claims(TEXTS, student_facing_text(TEXTS)) == []
    assert quotation_holders(TEXTS)[_index("p2-q03")] == [_index("p2-s05")]
    assert quotation_holders(TEXTS)[_index("p3-q01")] == [_index("p3-point")]


def test_through_the_hub_the_composed_text_draws_no_finding_and_the_joined_one_is_named():
    hub, ch, reply, _rc = deliver("ll-t15")
    try:
        joined_doc = file_synthesis(ch, reply, "ll-t15")
        _msg, rr = relay(ch, joined_doc)
        [f] = [x for x in by_code(rr.findings, "INT-LEDGER-017") if "rule duplicated-content" in x.message]
        ids = {c["claim_id"] for c in joined_doc["claims"]}
        quoted = {joined_doc["claims"][i]["claim_id"] for i in (_index("p2-q03"), _index("p3-q01"))}
        assert quoted <= set(f.claim_ids) <= ids and f.severity == "warning"
        composed_doc = file_synthesis(ch, reply, "ll-t15", synthesis_id="syn-ll-t15-composed")
        composed_doc["text"] = student_facing_text([c["text"] for c in composed_doc["claims"]])
        composed_doc["text_sha256"] = sha256_text(composed_doc["text"])
        _msg2, rr2 = relay(ch, composed_doc)
        assert not [x for x in by_code(rr2.findings, "INT-LEDGER-017")], [x.message[:200] for x in by_code(rr2.findings, "INT-LEDGER-017")]
        assert not by_code(rr2.findings, "INT-LEDGER-031"), [x.message[:200] for x in by_code(rr2.findings, "INT-LEDGER-031")]
    finally:
        hub.close()


def test_the_readers_are_linear_at_the_contracts_bounds():
    # 512 quotation claims (the contract's bound), each held by one sentence, and a text near the contract's 400,000 characters
    quotes = [f'"{" ".join(["word"] * 3)} {k}"' for k in range(256)]
    holders = [f"The writer says {q} again." for q in quotes]
    texts = [x for pair in zip(quotes, holders) for x in pair]
    long_text = (" ".join(texts) + " ") * 8
    hostile = ['"' + "a " * 1_900 + 'b"'] * 64 + ["a " * 1_990 + "c"] * 64
    t0 = time.process_time()
    student_facing_text(texts), contained_claims(texts, long_text[:400_000]), quotations_held_verbatim(hostile), contained_claims(hostile)
    spent = time.process_time() - t0
    assert spent < 4.0, f"{spent:.2f} s"


def _ledger_entries(text: str):
    """The quotation readers of the ledger and the port on a synthesis whose claims are the hostile text, quoted and plain."""
    quoted = '"' + text[:3_990] + '"'
    texts = [quoted, text, quoted, "The writer says " + quoted + " again.", text[:4_000]]
    yield "quotation_holders", lambda: quotation_holders(texts)
    yield "quotations_held_verbatim", lambda: quotations_held_verbatim(texts)
    yield "contained_claims (joined)", lambda: contained_claims(texts)
    yield "contained_claims (text)", lambda: contained_claims(texts, text * 2)
    yield "student_facing_text", lambda: student_facing_text(texts)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_ledger_and_port_quotation_readers(shape):
    """Round-9 c2b class sweep (the ledger's and the port's quotation readers), on the standard hostile inputs."""
    assert not sweep(_ledger_entries, texts=one(shape))
