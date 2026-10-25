"""Security round 2 (the sweep): a stated total of the SI reading ('2.0 kg and 3.0 kg, a total of about 5.0 kg') is read in
linear time (``quant._si_patterns().total``).

The total pattern the readings build (``quant._build_patterns``) read the white space between the word of the total and its
figure with two quantifiers around the optional qualifier (``\\s+(?:about|around|roughly)?\\s*``). Before a long run of white
space that no figure follows, each try split the run between them in every way: quadratic in the run, and the reading
searches each sentence of a STEM answer with it (one try took 0.7 s on 1,000 characters and 15 s on 4,800). Each run is now
read once (possessive): neither the qualifier nor a figure starts with white space, so a run read in part leaves the same
match or none. The general reading's ``_TOTAL_RE`` reads its qualifier with its own white space and was not affected.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.branches import quant
from epinoic_logic.stem.si_reading import SI_READING

from ..growth import growth

#: The link before this round, kept as data to pin that every total is read as before.
OLD_LINK = r"\s+(?:about|around|roughly)?\s*"
NEW = quant._si_patterns().total
OLD = re.compile(NEW.pattern.replace(quant._TOTAL_LINK, OLD_LINK), NEW.flags)


def test_the_link_is_in_the_si_total_pattern():
    assert quant._TOTAL_LINK in NEW.pattern and OLD.pattern != NEW.pattern


def _hostile(n: int) -> str:
    return "-5.5e-5 quadrillion and aa -5.5e-5 quadrillion a total" + " " * n + " of about -5.5e-5 quadrillion"


def test_a_long_run_of_white_space_after_the_word_of_a_total_is_read_in_linear_time():
    """Four times the run costs about four times as much (before the round: about sixteen times)."""
    for read in (lambda s: NEW.match(s), lambda s: NEW.search(s), lambda s: sum(1 for _m in NEW.finditer(s))):
        ratio, small, large = growth(read, _hostile(1000), _hostile(4000))
        assert ratio < 8.0, (ratio, small, large)


def test_the_si_prose_reading_of_a_total_with_a_long_run_grows_linearly():
    text = lambda n: "The masses follow. " + ("2.0 kg and 3.0 kg a total" + " " * n + " of about 5.0 kg. ") * 4 + "The end."
    ratio, small, large = growth(lambda t: quant.undecided_quant_statements(t, reading=SI_READING), text(400), text(1600),
                                 clear=quant._analyse.cache_clear)
    assert ratio < 8.0, (ratio, small, large)


SENTENCES = [
    "2.0 kg and 3.0 kg, a total of about 5.0 kg.",
    "The two masses, 2.0 kg and 3.0 kg, give a total of 5.0 kg.",
    "1.2 × 10³ J plus 800 J makes in total roughly 2.0 × 10³ J.",
    "4 seats and 5 seats totalling 9 seats",
    "4 and 5 together 9",
    "-5.5e-5 quadrillion and -2e-5 quadrillion a total of about -7.5e-5 quadrillion",
    "12 000 m and 3 000 m, giving a total of around 15 000 m",
    "ten and twenty five making thirty five",
    "3 kg and 4 kg total  about\t7 kg",
    "3 kg and 4 kg totals aboutx 7 kg",
    "3 kg and 4 kg a total of\n\n7 kg",
    "5 % and 6 % in total 11 %",
]


def _random_texts(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["5", "-5.5e-5", "3 × 10³", "1,200", "12 000", "ten", "twenty five", "quadrillion", "million", "kg", "m", "%", "and", "plus",
              "a total of", "totalling", "together", "in total", "making", "giving", "total", "totals", "about", "around", "roughly", "x", ".",
              ";", "seats"]
    spaces = [" ", "  ", "", "\t", "\n", "   "]
    return ["".join(rnd.choice(pieces) + rnd.choice(spaces) for _ in range(rnd.randrange(3, 16))) for _ in range(n)]


def _sig(m):
    return None if m is None else (m.span(), m.groups())


def test_every_total_is_read_as_before():
    """The SI total pattern finds the same matches, with the same groups, as before the round: scanning the whole text,
    and searched and anchored from every place of it."""
    texts = SENTENCES + _random_texts(500, seed=8)
    for s in texts:
        assert [_sig(m) for m in NEW.finditer(s)] == [_sig(m) for m in OLD.finditer(s)], s
        for i in range(len(s) + 1):
            assert _sig(NEW.search(s, i)) == _sig(OLD.search(s, i)), (s, i)
            assert _sig(NEW.match(s, i)) == _sig(OLD.match(s, i)), (s, i)


def test_stated_totals_are_still_read():
    """Clean controls: the totals the SI reading reads, with their figures."""
    m = NEW.search("The two masses, 2.0 kg and 3.0 kg, give a total of 5.0 kg.")
    assert m is not None and m.group(0).endswith("5.0 kg")
    assert NEW.search("1.2 × 10³ J plus 800 J makes in total roughly 2.0 × 10³ J.") is not None
    assert NEW.search("2.0 kg and 3.0 kg, the total.") is None
