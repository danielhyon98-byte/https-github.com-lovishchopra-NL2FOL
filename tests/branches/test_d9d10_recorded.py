"""D9/D10 (decision D35): the eight recorded Geography and Language B answers of rounds c1, c2 and c3 through the hub, as the harness delivers
them (subject, agent, task type, request and supplied texts), pinned: the receipt status, the error and warning codes, the constraint results,
the item coverage and every formal check with its status (design sections 6.5 and 7.3). The new branches add only ENTAILED checks; no
recorded answer gains INT-SUBJ-001, -003 or -004. (INT-REQ-006, which the harness also reports, comes from the recorded translations
and is not part of a delivery with no translator.)"""
from __future__ import annotations

import pytest

from .d9d10_hub import RECORDED, checks, codes, recorded

_E = "ENTAILED"
EXPECTED = {
    "c1/ge-t14": ("ACCEPTED_WITH_FINDINGS", ["INT-REQ-004"], [("c1", None), ("c2", None)], [("i1", False), ("i2", False)],
                  [("geography-worked-1", _E), ("geography-worked-2", _E), ("geography-worked-3", _E)]),
    "c1/sp-t14": ("ACCEPTED_WITH_FINDINGS", ["INT-REQ-010"], [], [(f"i{k}", True) for k in range(1, 9)],
                  [("language-b-supplied-figure-1", _E), ("language-b-supplied-figure-2", _E), ("language-b-supplied-figure-3", _E)]),
    # stricter (attack round 2 of c3b): the answer's "threefold increase (16.2 ÷ 5.4 = 3.0)" gains the fold-word check, ENTAILED
    # stricter (attack round 3 of c3b): a change stated "by N" with its pair in the sentence gains the change-by check, ENTAILED
    # stricter (c3d): the lag times of (a), "Result: lag time of 12 hours for Storm 1 and 4.5 hours for Storm 2", read against the
    # request's clock times (09:30 to 21:30, 09:30 to 14:00), gain two clock-interval checks, both ENTAILED
    "c2/ge-p9c": ("ACCEPTED_WITH_FINDINGS", [], [], [(f"i{k}", True) for k in range(1, 5)],
                  [("core-quant-1", _E), ("core-quant-2", _E), ("geography-clock-interval-1", _E), ("geography-clock-interval-2", _E),
                   ("geography-change-by-1", _E), ("geography-fold-1", _E)]
                  + [(f"geography-worked-{k}", _E) for k in range(1, 7)]),
    # (and the year table's from-to pairs with no year, "coal down from 46% to 28%", read against the row's two years: four more
    # core-figure checks; and a change "by 18 percentage points" of a row read against its two cells: two table-change checks)
    "c2/ge-t15": ("ACCEPTED_WITH_FINDINGS", [], [], [(f"i{k}", True) for k in range(1, 5)],
                  [(f"core-quant-{k}", _E) for k in range(1, 6)] + [(f"core-figure-{k}", _E) for k in range(1, 9)]
                  + [("geography-change-by-1", _E), ("geography-table-change-1", _E), ("geography-change-by-2", _E)]
                  # stricter (c3d): "coal supply fell by 22.1%, from 377.2 PJ in 2005 to 294.0 PJ in 2025" read as the coal share × the
                  # total for each year: two table-derived checks, both ENTAILED
                  + [("geography-table-derived-1", _E), ("geography-table-derived-2", _E), ("geography-table-change-2", _E)]
                  # stricter (check round 12 of c3f): "Imports rose from 38% to 54% of Ostrel's primary energy supply" read against the
                  # imported share's cells for the table's two years (the from-to pair's per cents read together): two table-derived
                  # checks, both ENTAILED
                  + [("geography-table-derived-3", _E), ("geography-table-derived-4", _E)]
                  # stricter (attack round 4, was range(1, 5)): the products in brackets "311.6 PJ (0.38 × 820 PJ)" and its 2025 twin are
                  # now decided (worked-5, worked-6), both ENTAILED
                  + [(f"geography-worked-{k}", _E) for k in range(1, 7)]),
    # stricter (selfcert-1 c3b, was ACCEPTED): decision D7 gates the answer's own word-count note "Word count: about 513 including
    # headline and byline ..., inside the 450–600 range." (design 6.4, SELF_MEASURES), a warning, so the receipt has findings
    "c2/sp-t15": ("ACCEPTED_WITH_FINDINGS", [], [("c1", True), ("c2", True)], [("i1", True), ("i2", True)],
                  [("language-b-word-count-1", _E), ("language-b-word-count-2", _E), ("language-b-word-range-claim-1", _E)]),
    "c3/ge-t16": ("ACCEPTED_WITH_FINDINGS", ["INT-REQ-004"], [("c1", True), ("c2", True)], [("i1", True), ("i2", False)], []),
    "c3/sp-p10d": ("ACCEPTED", [], [("c1", True), ("c2", True)], [("i1", True)], []),
    "c3/sp-t16": ("ACCEPTED_WITH_FINDINGS", ["INT-REQ-010"], [], [("i1", True), ("i2", True)],
                  [(f"core-marks-{k}", _E) for k in range(1, 5)] + [("language-b-word-count-1", _E), ("language-b-word-range-claim-1", _E),
                                                                     ("language-b-address-form-1", _E), ("language-b-address-form-2", _E),
                                                                     ("language-b-listed-count-1", _E)]
                  # attack round 8 (c3c, a stricter pin): the answer's counts of its own corrections by category ("agreement (three)",
                  # "the subjunctive ... (two)", "one ser/estar error") are now decided too, each ENTAILED against the correction lines
                  + [(f"language-b-listed-count-{k}", _E) for k in range(2, 5)]),
}
#: New for hold remedy c3b: the claims each recorded answer's self-certification findings (CORE-SELF-001, INT-HANDOFF-006) name, pinned
#: for the records whose receipt the c3b gate changed. c2/sp-t15: the word-count note g11.1 only; the concession "Es cierto, pero el
#: problema no es el turismo en sí, sino el modo en que se gestiona." (g7.2) is content, an argument's "true, but", never an assessment
#: of the answer.
SELF_NAMED = {
    "c2/sp-t15": ["g11.1@language-b-spanish-specialist"],
}


@pytest.mark.parametrize("name", list(RECORDED))
def test_recorded_answer_receipt_is_pinned(name):
    rc = recorded(name)
    assert rc.branch == ("geography" if "/ge-" in name else "language_b")
    got = (rc.status.value, codes(rc), [(c.constraint_id, c.satisfied) for c in rc.constraint_results], [(c.item_id, c.addressed) for c in rc.coverage], checks(rc))
    assert got == EXPECTED[name]
    if name in SELF_NAMED:
        named = sorted({cid for f in list(rc.findings) + list(rc.structural_findings) if f.code in ("CORE-SELF-001", "INT-HANDOFF-006")
                        for cid in f.claim_ids})
        assert named == SELF_NAMED[name], (name, named)
    assert not [f for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-003", "INT-SUBJ-004")]
    assert not [f for f in rc.structural_findings if f.code in ("BR-INTERNAL-001", "PACK-INTERNAL-001", "CORE-INTERNAL-001")]
    assert not [c for c, _s in checks(rc) if c.startswith("generic-")]
