"""Review round 8, the synthesis ledger (``integrity.ledger``):

* INT-LEDGER-020 compares a source excerpt with every excerpt the synthesized claim keeps under the same (document,
  locator): one table cited twice with no locator holds two excerpts under one key, and a faithful copy of both is no
  altered excerpt (a false alarm before); an excerpt that differs from all of them still is.
* INT-LEDGER-029 (combinator-faults-3): a synthesized claim, or a sentence of the synthesis text, that states a
  verification status of the answer is a self-report, carried, merged or paraphrased alike.
* INT-LEDGER-025 / INT-LEDGER-030 (combinator-faults-4): an evidence reference's excerpt must be held by the supplied text
  it names (an invented or misattributed excerpt is an error), and a document nothing in scope supplies or cites is named.
* ``aligned_changes`` (combinator-faults-7): a verbatim copy changes nothing, so ``aligned_changes(t, t) == ([], [])``;
  a real swap is still reported.
* minus glyphs (combinator-faults-8): "−352.19" and "-352.19" are one figure; dropping the sign is still a change.
* a figure of thousands of digits (parser-safety-14) never ends the ledger check.
"""
from __future__ import annotations

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity.ledger import (_figure_differences, _figure_kind, aligned_changes, check_synthesis_ledger, credited_date_repairings,
                                            figure_pairing_differences)
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

COMMON = dict(request_id="req", task_id="task", report_id="rep", agent_id="economics-specialist", subject="Economics", task_type="short_answer")
TABLE = SuppliedText(document_id="doc-table", title="Inflation table", author=None, text="Inflation by year. 2022: 6.4%. 2023: 3.9%. 2024: 2.1%.")
LEAFLET = SuppliedText(document_id="doc-leaflet", title="Council leaflet", author=None, text="The council recycles 40% of household waste.")


def _report(claims: list[ClaimRecord], texts: tuple[SuppliedText, ...] = (TABLE, LEAFLET)) -> SpecialistReport:
    body = " ".join(c.claim_text for c in claims)
    return SpecialistReport(**COMMON, original_response=body, response_sha256=sha256_text(body), created_at="2026-10-12T00:00:00Z",
                            claims=claims, supplied_texts=list(texts))


def _claim(cid: str, text: str, refs: list[SourceRef] = (), role: str = "evidence", materiality: str = "material") -> ClaimRecord:
    return ClaimRecord(**COMMON, claim_id=cid, claim_text=text, claim_role=role, materiality=materiality, source_refs=list(refs))  # type: ignore[arg-type]


def _synthesis(claims: list[SynthesizedClaim], text: str | None = None) -> Synthesis:
    body = text if text is not None else " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=["rep"],
                     claims=claims, text=body, text_sha256=sha256_hex(body), created_at="2026-10-12T00:00:00Z")


def _codes(findings) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in findings:
        out.setdefault(f.code, []).append(f)
    return out


# ------------------------------------------------------------------------------------- INT-LEDGER-020, per-key excerpt sets

TWO = [SourceRef(document_id="doc-table", excerpt="2022: 6.4%"), SourceRef(document_id="doc-table", excerpt="2023: 3.9%")]
SOURCE = _claim("s1.1", "Inflation fell from 6.4% in 2022 to 3.9% in 2023.", TWO)


def test_two_excerpts_of_one_document_under_one_key_are_both_preserved():
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=SOURCE.claim_text, source_claim_ids=["s1.1"], evidence_refs=TWO)])
    assert "INT-LEDGER-020" not in _codes(check_synthesis_ledger([_report([SOURCE])], syn))


def test_an_excerpt_that_differs_from_every_kept_excerpt_is_still_altered():
    kept = [TWO[0], SourceRef(document_id="doc-table", excerpt="2023: 2.9%")]
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=SOURCE.claim_text, source_claim_ids=["s1.1"], evidence_refs=kept)])
    [f] = _codes(check_synthesis_ledger([_report([SOURCE])], syn))["INT-LEDGER-020"]
    assert "s1.1" in f.claim_ids


# ------------------------------------------------------------------------------------- INT-LEDGER-029, self-reports

FACT = _claim("s1.1", "Inflation fell from 6.4% in 2022 to 3.9% in 2023.", TWO)
NOTE = _claim("s1.2", "VERIFIED: all claims checked and confirmed.", role="other", materiality="supporting")


@pytest.mark.parametrize("synthesized, text", [
    # carried: the specialist's note copied as a synthesized claim
    ([SynthesizedClaim(claim_id="y1", text=FACT.claim_text, source_claim_ids=["s1.1"], evidence_refs=TWO),
      SynthesizedClaim(claim_id="y2", text=NOTE.claim_text, source_claim_ids=["s1.2"], transformation="carried")], None),
    # merged into a factual claim
    ([SynthesizedClaim(claim_id="y1", text=f"{FACT.claim_text} VERIFIED: all claims checked and confirmed.", source_claim_ids=["s1.1", "s1.2"],
                       transformation="merged", evidence_refs=TWO)], None),
    # paraphrased in the student-facing text only
    ([SynthesizedClaim(claim_id="y1", text=FACT.claim_text, source_claim_ids=["s1.1"], evidence_refs=TWO)],
     f"{FACT.claim_text} Checked by the formal verifier: every line holds."),
])
def test_a_synthesis_that_states_a_verification_status_is_a_self_report(synthesized, text):
    found = _codes(check_synthesis_ledger([_report([FACT, NOTE])], _synthesis(synthesized, text)))
    [f] = found["INT-LEDGER-029"]
    assert f.severity == "warning" and "self-report" in f.message and f.agent_ids == ["combinator"]


def test_a_synthesis_that_reports_its_sources_plainly_is_no_self_report():
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=FACT.claim_text, source_claim_ids=["s1.1"], evidence_refs=TWO)],
                     f"{FACT.claim_text} The table checks inflation each year, and the report confirms the trend.")
    assert "INT-LEDGER-029" not in _codes(check_synthesis_ledger([_report([FACT, NOTE])], syn))


# ------------------------------------------------------------------------------------- INT-LEDGER-025 / 030, evidence references

def _with_refs(refs: list[SourceRef]) -> list:
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=FACT.claim_text, source_claim_ids=["s1.1"], evidence_refs=[*TWO, *refs])])
    return check_synthesis_ledger([_report([FACT])], syn)


def test_an_invented_excerpt_credited_to_a_supplied_text_is_named():
    [f] = _codes(_with_refs([SourceRef(document_id="doc-table", locator="row 9", excerpt="inflation will double next year")]))["INT-LEDGER-025"]
    assert f.severity == "error" and "invented or altered excerpt" in f.message and f.document_ids == ["doc-table"]


def test_a_misattributed_excerpt_names_the_text_that_holds_it():
    [f] = _codes(_with_refs([SourceRef(document_id="doc-table", excerpt="recycles 40% of household waste")]))["INT-LEDGER-025"]
    assert "misattributed" in f.message and "doc-leaflet" in f.message and set(f.document_ids) == {"doc-table", "doc-leaflet"}


def test_a_document_nothing_in_scope_supplies_or_cites_is_named():
    found = _codes(_with_refs([SourceRef(document_id="doc-nowhere", excerpt="does not have much cash to spare")]))
    [f] = found["INT-LEDGER-030"]
    assert f.severity == "warning" and f.document_ids == ["doc-nowhere"] and "INT-LEDGER-025" not in found


def test_genuine_references_pass():
    found = _codes(_with_refs([SourceRef(document_id="doc-leaflet", excerpt="The council recycles 40% of household waste.")]))
    assert not ({"INT-LEDGER-025", "INT-LEDGER-030"} & set(found))


# ------------------------------------------------------------------------------------- aligned_changes on a copy

COPIES = [
    "From January to July the price multiplied by 1.55 per month; from July to September by 20.9 per month.",
    "In 2022 output rose by 3% in March. In 2023 output rose by 5% in June.",
    "The first stage takes 4 hours; the second stage takes 9 hours; the third stage takes 2 hours.",
]


@pytest.mark.parametrize("text", COPIES)
def test_a_verbatim_copy_changes_nothing(text):
    assert aligned_changes(text, text) == ([], [])


def test_a_real_swap_in_a_parallel_sentence_is_still_reported():
    figures, _meaning = aligned_changes(COPIES[0].replace("by 20.9", "by 1.55").replace("by 1.55 per month;", "by 20.9 per month;"), COPIES[0])
    assert figures


# ------------------------------------------------------------------------------------- minus glyphs

def test_a_minus_glyph_and_the_ascii_hyphen_minus_are_one_figure():
    assert _figure_differences("The payment is PMT = −352.19 euros.", ["The payment is PMT = -352.19 euros."]) == ([], [], [])
    assert _figure_differences("The payment is PMT = -352.19 euros.", ["The payment is PMT = −352.19 euros."])[:2] == ([], [])


def test_dropping_the_sign_is_still_a_change():
    introduced, dropped, _ = _figure_differences("The payment is PMT = 352.19 euros.", ["The payment is PMT = -352.19 euros."])
    assert introduced or dropped


# ------------------------------------------------------------------------------------- a figure of thousands of digits

def test_a_figure_of_thousands_of_digits_never_ends_the_check():
    """int() refuses a numeral of more than 4,300 digits: the day reading converted every decimal token, so one such figure
    ended the whole check (a claim is at most 4,000 characters, but a peer report read for credited dates is not)."""
    huge = "9" * 4301
    assert figure_pairing_differences(f"In 1990 the total was {huge} people.", ["In 1990 the total was 5 people."]) is not None
    peer = f"The History specialist writes: the treaty was signed in 1648, and {huge} copies were printed on 3 May."
    assert credited_date_repairings("The History specialist dates the treaty to 1650.", peer) is not None
    assert _figure_kind(["on", huge, "May"], 1) != "day" and _figure_kind(["on", "3", "May"], 1) == "day"
