"""The one tokenizer of the lexical rules (``epinoic_logic.lexis``): its tables pinned, its stems, negation, cue matching,
and its linear cost on long untrusted text."""
from __future__ import annotations

import hashlib
import time

from epinoic_logic import lexis as L


def test_the_tables_are_pinned():
    assert L.FRAME_WORDS == frozenset({"be", "is", "are", "was", "cannot", "upon", "shown", "true", "indeed", "really", "clearly"})
    assert L.FRAME_PHRASES == (("can", "not"), ("the", "fact", "that"), ("in", "fact"))
    assert L.NEGATION_WORDS == frozenset({"not", "no", "never", "cannot", "nor"})
    assert L.NEGATING_PREFIXES == ("non", "dis", "un", "in", "im", "il", "ir")
    assert L.NEGATABLE_SUFFIXES == ("able", "ible", "ful", "ent")
    assert L.NOT_NEGATED == frozenset({"intelligent", "insistent", "indulgent", "ingredient", "incandescent", "insurgent"})
    assert L.STRIPPED_SUFFIXES == ("able", "ible", "ing", "ed", "es", "ly", "s")
    assert L.WILDCARD == "*"
    assert len(L.FUNCTION_WORDS) == 155
    assert hashlib.sha256(" ".join(sorted(L.FUNCTION_WORDS)).encode()).hexdigest() == "61447ebbdc0054a64098b852ed4075fe4fff704a9036b402c363bcb5b6dbde28"
    assert {"the", "of", "and", "because", "therefore", "is", "would", "every", "all"} <= L.FUNCTION_WORDS
    assert not ({"never", "not", "without", "cause", "rose"} & L.FUNCTION_WORDS)


def test_the_root_reader_and_its_tables_are_pinned():
    """Repair round 1 (re-run review A-INF-CIRC, A-FA-QUOTERULE): a coarser root for readings that compare two texts word by
    word. Its two tables are data, pinned here."""
    assert L.IRREGULAR_FORMS["driven"] == "drive" and L.IRREGULAR_FORMS["rose"] == "rise" and L.IRREGULAR_FORMS["succeeded"] == "success"
    assert len(L.IRREGULAR_FORMS) == 92
    assert L.DERIVATIONAL_SUFFIXES[:3] == (("ibility", "ible"), ("ability", "able"), ("ically", "ic")) and len(L.DERIVATIONAL_SUFFIXES) == 19
    assert {L.root(w) for w in ("drives", "driven", "drove")} == {"driv"}
    assert L.root("stability") == L.root("stable") == "stabl"
    assert L.root("political") == L.root("politics") == L.root("politically") == "polit"
    assert L.root("successful") == L.root("succeeded") == L.root("success") == "success"
    assert L.root("rose") == L.root("rises") == L.root("risen") == "rise" and L.root("aims") == "aim" and L.root("2024") == "2024"
    assert L.root("class") == "class" and L.root("status") == "status"     # a final s of ss, us, is is kept


def test_tokens_are_lower_case_words_and_numbers_with_their_offsets():
    text = "In Loftus and Palmer’s study, 45 students (non-random) didn't see 2.5 km; it's 1,800."
    assert L.tokens(text) == ("in", "loftus", "and", "palmer's", "study", "45", "students", "non", "random", "didn't", "see", "2.5", "km",
                              "it's", "1,800")
    for start, end, tok in L.token_spans(text):
        assert text[start:end].casefold().replace("’", "'") == tok
    assert L.tokens("") == () and L.tokens(None) == ()  # type: ignore[arg-type]
    assert L.tokens("x² = 4") == ("x", "4")              # a superscript is no decimal digit
    assert L.tokens("1960s, 3rd") == ("1960", "s", "3", "rd")


def test_stems_share_a_root_across_inflections_and_the_negating_prefix():
    for word in ("relied", "relies", "reliable", "unreliable", "relying", "rely"):
        assert L.stem(word) == "rely", word
    assert L.stem("cells") == "cell" and L.stem("studies") == L.stem("studied") == "study"
    assert L.stem("impossible") == L.stem("possible") and L.stem("inconsistent") == "consistent"
    for word in ("class", "status", "analysis", "family", "supply", "this"):
        assert L.stem(word) == word, word                 # short or non-inflected endings stay whole
    assert L.stem("Palmer's") == "palmer" and L.stem("1,800") == "1,800" and L.stem("don't") == "don't"
    assert L.stem("investment") == "investment" and L.stem("intelligent") == "intelligent"


def test_negation_is_read_by_parity():
    assert L.negated("the source is unreliable") and L.negated("the source is not reliable") and L.negated("it cannot be relied upon")
    assert not L.negated("the source is not unreliable") and not L.negated("the source is reliable")
    assert L.negated("the study isn't random") and L.negated("a non random sample") and L.negated(["never"])
    assert not L.negated("an intelligent reader") and not L.negated("an incident occurred") and not L.negated("the investment grew")
    assert L.negation_markers("not unreliable, never") == 3


def test_content_stems_leave_out_function_frame_and_negation_words():
    assert L.content_stems("It is true that the source is unreliable, in fact.") == ("source", "rely")
    assert L.content_stems("the source cannot be relied upon") == ("source", "rely")
    assert L.content_stems("The fact that the walls fell shows nothing") == ("wall", "fell", "show", "noth")
    assert L.content_stems("Cells, cells and more cells") == ("cell",)
    assert L.content_stems(["The", "Treaty", "caused", "war"]) == ("treaty", "caus", "war")


def test_cues_match_on_word_boundaries_with_a_wildcard():
    table = L.cue_table(["led to", "because of", "made * rise", "in general", ("all",)])
    hits = L.find_cues("The tax made prices rise and led to unrest because of it; in general.", table)
    assert hits == ((2, ("made", "*", "rise")), (6, ("led", "to")), (9, ("because", "of")), (12, ("in", "general")))
    assert not L.has_cue("a ball, ledger and tolled bells", table)      # 'all' and 'led' only as whole words
    assert L.has_cue("All three parts", table) and L.has_cue(["all"], ["all"])
    assert L.cue_table(["", "  "]).phrases == ()


def test_the_tokenizer_is_linear_in_a_long_untrusted_text():
    text = ("an unreliable source led to it, " * 12_000)[:400_000]
    t0 = time.perf_counter()
    toks = L.tokens(text)
    stems = L.content_stems(toks)
    found = L.has_cue(toks, L.cue_table(["led to nowhere"]))
    elapsed = time.perf_counter() - t0
    assert len(toks) > 70_000 and stems and not found
    assert elapsed < 5.0
    hostile = "'" * 50_000 + "a" + "-" * 50_000
    t0 = time.perf_counter()
    assert L.tokens(hostile) == ("a",)
    assert time.perf_counter() - t0 < 2.0
