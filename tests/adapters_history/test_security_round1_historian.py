"""Security round 1: a historian named by initials is found in linear time (``structural._HISTORIAN_RE``).

HI-SRC-003 searches each claim for a named historian and a verb of position ('A. J. P. Taylor argues'). The name of
initials was tried from every initial of a run of them, each start reading the run again: a 4,000-character claim of
initials took 0.5 s (the base's pattern alike), once per claim. A name of initials now starts only at its first initial
(an initial right after an initial is read by the name that starts before it, which the search tries first); every claim
names a historian exactly when it did.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.adapters.history_specialist import structural as S

from ..growth import growth

GUARD = "(?<!\\b[A-Z]\\.)(?<!\\b[A-Z]\\.\\s)"
OLD = re.compile(S._HISTORIAN_RE.pattern.replace(GUARD, ""), S._HISTORIAN_RE.flags)


def test_the_guard_is_in_the_pattern():
    assert GUARD in S._HISTORIAN_RE.pattern and GUARD not in OLD.pattern


def test_a_run_of_initials_is_searched_in_linear_time():
    for unit in ("A. ", "A.", "B. ", "C. D."):
        ratio, small, large = growth(S._HISTORIAN_RE.search, "The war ended in 1918. " + unit * (1000 // len(unit)) + "x",
                                     "The war ended in 1918. " + unit * (4000 // len(unit)) + "x")
        assert ratio < 8.0, (unit, ratio, small, large)


CLAIMS = ["A. J. P. Taylor argues that the war was an accident.", "A.J.P. Taylor argued it.", "E. H. Carr has shown that the record is selective.",
          "Margaret Hale has shown that it mattered.", "Karl Bracher argued so.", "Jürgen Falter argued so.", "xA. B. Smith argues that x.",
          "A. B.  C. Smith argues x", "A. A. A. A. A. Smith claims x", "The historian A. Smith finds x", "Neville Chamberlain believed x.",
          "A. B. C. D.", "U.S. Grant showed courage", "A.  Smith argues", "a. b. Smith argues", ""]


def _random_claims(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["A.", "B. ", "J.", " ", " ", "Smith", "Taylor", "Hale", "argues", "has shown", "have found", "claims", "x", "xA.", ",", "the"]
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 12))) for _ in range(n)]


def test_every_claim_is_read_as_before():
    for s in CLAIMS + _random_claims(60_000, seed=67):
        a, b = S._HISTORIAN_RE.search(s), OLD.search(s)
        assert (a and (a.span(), a.groups())) == (b and (b.span(), b.groups())), repr(s)


def test_historians_are_still_found():
    assert S._HISTORIAN_RE.search("A. J. P. Taylor argues that the war was an accident.").group(1) == "A. J. P. Taylor"
    assert S._HISTORIAN_RE.search("xA. B. Smith argues that x.").group(1) == "B. Smith"
    assert S._HISTORIAN_RE.search("Neville Chamberlain believed it.") is None
