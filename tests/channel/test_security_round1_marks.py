"""Security round 1: mark annotations and given values are read in linear time.

Five patterns read a mark annotation ('[2 marks]', '[2 + 2]', '(4 marks)') or a value given for a symbol ('d = 120') with two
or three white-space quantifiers side by side, which split a run of spaces between them in every way before failing:
``bus._MARK_ANNOTATION_RE`` (an item's furniture), ``request_parser._MARKS_RE`` (a part that earns marks),
``relations._MARKS_RE`` (the marks of a STEM request), ``hub_hooks._FORM_RE`` (an item's answer form) and
``hub_hooks._GIVEN_RE`` (a given value). Each run is now read possessively, and every text is read as before.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.channel import bus, request_parser as RP
from epinoic_logic.stem import hub_hooks as H, relations as R

from ..growth import growth

#: The patterns before this round, kept as data.
OLD_MARK_ANNOTATION = re.compile("\\[\\s*\\d{1,3}(?:\\s*\\+\\s*\\d{1,3}){0,4}\\s*(?:marks?)?\\s*\\]|\\(\\s*\\d{1,3}\\s*marks?\\s*\\)", re.IGNORECASE)
OLD_PARSER_MARKS = re.compile("\\[\\s*\\d+(?:\\s*\\+\\s*\\d+)*\\s*(?:marks?)?\\s*\\]|\\(\\s*\\d+\\s*marks?\\s*\\)", re.IGNORECASE)
OLD_STEM_MARKS = re.compile("\\[\\s*(\\d{1,2})\\s*(?:marks?)?\\s*\\]|\\(\\s*(\\d{1,2})\\s*marks?\\s*\\)")
OLD_FORM = re.compile(H._FORM_RE.pattern.replace("\\[\\s*+\\d++\\s*+(?:marks?+)?+\\s*+\\]|\\(\\s*+\\d++\\s*+marks?+\\s*+\\)",
                                                 "\\[\\s*\\d+\\s*(?:marks?)?\\s*\\]|\\(\\s*\\d+\\s*marks?\\s*\\)"), H._FORM_RE.flags)
OLD_GIVEN = re.compile(H._GIVEN_RE.pattern.replace("\\s*+=\\s*+[-\u2212+]?\\s*+\\d", "\\s*=\\s*[-\u2212+]?\\s*\\d"), H._GIVEN_RE.flags)

#: (name, pattern after the round, before it, how its readers apply it)
PAIRS = [("bus._MARK_ANNOTATION_RE", bus._MARK_ANNOTATION_RE, OLD_MARK_ANNOTATION, "sub"),
         ("request_parser._MARKS_RE", RP._MARKS_RE, OLD_PARSER_MARKS, "sub"),
         ("relations._MARKS_RE", R._MARKS_RE, OLD_STEM_MARKS, "finditer"),
         ("hub_hooks._FORM_RE", H._FORM_RE, OLD_FORM, "sub"),
         ("hub_hooks._GIVEN_RE", H._GIVEN_RE, OLD_GIVEN, "finditer")]


def test_the_old_patterns_are_rebuilt():
    for name, new, old, _how in PAIRS:
        assert new.pattern != old.pattern, name
        assert not re.search(r"(?<!\\)[*+?}]\+", old.pattern), name


def _apply(p: re.Pattern, how: str, text: str):
    if how == "sub":
        return p.sub(" ", text)
    return [(m.span(), m.groups()) for m in p.finditer(text)]


def test_a_long_run_in_a_mark_annotation_is_read_in_linear_time():
    for name, new, _old, how in PAIRS:
        shapes = ("x = {}y", "u\u2081 ={}+{}y") if "GIVEN" in name else ("(a) Explain why. [1{}x", "[1 +{}x", "(2{}x", "[2 marks{}x")
        for shape in shapes:
            ratio, small, large = growth(lambda t, new=new, how=how: _apply(new, how, t), shape.replace("{}", " " * 2000), shape.replace("{}", " " * 8000))
            assert ratio < 8.0, (name, shape, ratio, small, large)


TEXTS = ["(a) Explain why prices rose. [2 marks]", "[3]", "[2 + 2]", "[ 2 + 2 + 1 marks ]", "(4 marks)", "( 4  marks )", "[1234]", "[12]", "[1 mark]",
         "[2 MARKS] and (3 Marks)", "[1 + 2 + 3 + 4 + 5 + 6]", "[1 +]", "[ 2", "(3 mark)", "[2]]", "[[2]]", "to 3 significant figures", "3 s.f.",
         "2 d.p.", "3 sf", "Calculate v if d = 120 m and t = 8 s.", "u\u2081 = 3", "x_{ab} = \u2212 5", "y_1=+2", "F = ma", "k = -0.5", "a = b",
         "2x = 6", "\u03b1 = 30\u00b0", "x =\n4", "x = - 3", ""]


def _random_texts(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["[", "]", "(", ")", "1", "23", "1234", "+", " ", "  ", "\t", "mark", "marks", "MARKS", "s", "x", "=", "-", "\u2212", "u\u2081", "_",
              "{ab}", "d", "sig figs", "d.p.", "significant figures", "."]
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 14))) for _ in range(n)]


def test_every_annotation_and_given_value_is_read_as_before():
    for s in TEXTS + _random_texts(30_000, seed=47):
        for name, new, old, how in PAIRS:
            assert _apply(new, how, s) == _apply(old, how, s), (name, s)
            assert (new.search(s) is None) == (old.search(s) is None), (name, s)


def test_annotations_and_given_values_are_still_read():
    assert bus._MARK_ANNOTATION_RE.sub(" ", "Explain why [2 marks]").strip() == "Explain why"
    assert RP._MARKS_RE.search("(b) Calculate the speed. [3]") is not None
    assert [m.group(1) or m.group(2) for m in R._MARKS_RE.finditer("[2 marks] and (3 marks)")] == ["2", "3"]
    assert H._FORM_RE.sub(" ", "Give your answer to 3 significant figures. [2]").split() == ["Give", "your", "answer", "to", "."]
    assert [m.group(0) for m in H._GIVEN_RE.finditer("Calculate v if d = 120 m and t = 8 s.")] == ["d = 1", "t = 8"]
