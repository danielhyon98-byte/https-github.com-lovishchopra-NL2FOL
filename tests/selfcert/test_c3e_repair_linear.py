"""Repair 2 of the c3e clearance: the encoded-label reader's costs (selfcert/encoded.py).

1. A label position of a line (``_spots``) is read in linear time: the value standing alone was matched by a lazy pattern before a
   run of closing marks, which rescanned the run at each length it tried, and the key pattern was tried on lines with no
   separator; a line of 1,600 blanks around a stop took about 17 s (the c3e verification's history sweep timed out in it).
   ``_alone`` reads the same value in one pass: it agrees with the pattern on every string here.
2. A sentence written whole in a letter transform (``_line_transforms``) is spelt against the check words only when one of its
   words can be spelt (five letters or more and no lexicon word): a 16,000-line answer of two-letter words took 40% longer to
   cross the audited hub than at the base commit, which spelt nothing.
3. The tick of a correction pair (reader ``_tick_of_correction_pair``) reads at most 21 words after the tick and finds the clause's
   first cross once: every tick of a run of 20,000 ticks collected all the words after it, and a run of check marks took 8% longer
   to read than at the base commit (the c3e verification of the check-marks bound failed at 2.39 s against 2.0 s). It reads as
   the c3e check round's condition on every clause here.
"""
from __future__ import annotations

import random

import pytest

from epinoic_logic.selfcert import encoded as e

from ..growth import growth

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one


@pytest.mark.parametrize("make", [
    lambda n: " " * n + "..." + " " * n + "x",
    lambda n: "\t" * n + "x",
    lambda n: ")" * n + "ab" + "!" * n,
    lambda n: "> " * (n // 2) + "- " + " " * n + "ok" + " " * n,
    lambda n: " " * n + ":" + " " * n + "x",
], ids=["blanks around stops", "tabs", "closing marks", "a bullet after quote marks", "a key separator after blanks"])
def test_the_label_positions_of_a_line_are_read_in_linear_time(make):
    ratio, small, large = growth(e._spots, make(100), make(400))
    assert ratio < LINEAR, (ratio, small, large)


def test_a_line_of_blanks_at_the_piece_bound_is_read_at_once():
    import time
    line = " " * 800 + "..." + " " * 800 + "x"
    c0 = time.process_time()
    e._spots(line)
    assert time.process_time() - c0 < 0.5  # about 17 s before the repair (quadratic in the blanks)


def _reference(line: str):
    a = e._ALONE_RE.match(line)
    return (a.group(1), a.start(1), a.end(1)) if a else None


def test_the_value_standing_alone_is_the_patterns_value_on_every_string():
    rng = random.Random(20261122)
    alphabet = list(" \t>*#_`|([\"'«“-+•)]»”!ab.:é")
    lines = ["", "a", "ab", "- ab", "-  ab", "• x", "+\t\tyes", "(ok)", "**VERIFIED**", "> “Approved” !", "-", "- ", "-x", " ab  ))",
             "a" * 1600, "a" * 1601, " " * 5 + "a" * 1599 + ")))", "- " + "b" * 1600, "\"\"" + "c" * 1602 + "!!"]
    for _ in range(20_000):
        pick = rng.sample(alphabet, rng.randint(1, 6))
        lines.append("".join(rng.choice(pick) for _ in range(rng.choice([0, 1, 2, 3, 5, 9, 17, 33]))))
    for _ in range(300):
        lines.append("".join(rng.choice(" \t>*([") for _ in range(rng.randint(0, 20))) + rng.choice(["", "- ", "+\t ", "• ", "-x"])
                     + "".join(rng.choice("ab .-") for _ in range(rng.choice([0, 1, 2, 1597, 1598, 1599, 1600, 1601, 1602])))
                     + "".join(rng.choice(" )]!»*") for _ in range(rng.randint(0, 20))))
    for line in lines:
        assert e._alone(line) == _reference(line), repr(line[:80])
    assert e._alone("a\nb") == _reference("a\nb")  # (a line break: the pattern itself reads it)


class _NoSpelling:
    def sub(self, *_a, **_k):  # pragma: no cover - reached only if the gate lets a transform through
        raise AssertionError("a transform with no word of five letters was spelt")


def test_a_sentence_of_short_words_is_never_spelt(monkeypatch):
    monkeypatch.setattr(e, "_MISSPELT_WORD_RE", _NoSpelling())
    assert e._line_transforms("ab cd") == []
    assert e._line_transforms("xq zv wk") == []


def test_control_a_misspelt_transformed_check_word_is_still_spelt():
    # "delcehc lla :serugif", reversed, is "figures: all checled": the misspelt check word is read as "checked"
    assert any("checked" in t.lower() for t in e._line_transforms("delcehc lla :serugif"))


def _pair_reference(toks: list, i: int) -> bool:
    """The tick-pair condition as the c3e check round wrote it (every word after the tick collected, the clause before it scanned
    for each cross)."""
    from epinoic_logic.selfcert.reader import _PAIR_QUOTES
    after_tick = [x for x in toks[i + 1:] if not x.punct and x.w not in _PAIR_QUOTES]
    return bool(after_tick and len(after_tick) <= 20 and
                not any(x.fam() - {"PROVENANCE"} or x.has("C:anchor", "C:anchor_idioms", "C:genre_strong") for x in after_tick) and
                any(x.w == "zzmarkneg" and any(not y.punct for y in toks[k + 1:i]) for k, x in enumerate(toks[:i])))


def test_the_tick_of_a_correction_pair_is_read_as_before_from_one_pass_over_the_clause():
    from epinoic_logic.selfcert.reader import _pair_word_after_cross, _tick_of_correction_pair, _tokens
    rng = random.Random(1122)
    pieces = ["zzmarkpos", "zzmarkneg", '"', "«", "»", ",", ".", "→", "ella", "es", "está", "cansada", "the", "answer", "this",
              "verified", "checked", "la", "primera", "semana", "x"]
    texts = ['zzmarkneg "Ella es cansada" → zzmarkpos "Ella está cansada"', "zzmarkpos " * 30, "zzmarkneg zzmarkpos zzmarkpos x",
             "zzmarkneg , zzmarkpos x", "x zzmarkneg . , zzmarkpos ella"]
    texts += [" ".join(rng.choice(pieces) for _ in range(rng.randint(1, 40))) for _ in range(4000)]
    for s in texts:
        toks = _tokens(s, 0, len(s))
        cut = _pair_word_after_cross(toks)
        for i, t in enumerate(toks):
            if t.w == "zzmarkpos":
                assert _tick_of_correction_pair(toks, i, cut) == _pair_reference(toks, i), (s, i)
