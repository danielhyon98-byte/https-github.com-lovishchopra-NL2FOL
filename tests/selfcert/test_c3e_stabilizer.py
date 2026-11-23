"""Stabilizer of the c3e clearance: the self-certification reader's per-sentence costs (selfcert, adapters.markdown, stem.lexer).

The fix run's verifications failed only on wall-clock bounds, and the History parser's hostile-input sweep came within 20 s of its
120 s timeout, its time spread over the reader's reading of each sentence. These steps are made cheaper without changing what any
of them reads; each is shown here to agree with the form it replaced:

1. The letter transforms of a transformed line (``encoded._caesar_text``, ``_atbash_text``) are translation tables, not a generator
   per character; a line with no word of four letters or more tries none of them (no reading of theirs can be kept), Pig Latin aside.
2. A clause holds a label phrase only if it holds one of the phrase's words (``markdown._LABEL_PHRASE_HINT_RE``, read with the same
   case folding, the dotted and dotless i and the long s included).
3. ``pieces.sentence_spans`` passes over a run of characters none of its steps reads in one step.
4. The other-language net (``reader._net_found``) is a pure function of its arguments and is memoised.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.adapters import markdown as md
from epinoic_logic.selfcert import encoded as e
from epinoic_logic.selfcert import pieces as P
from epinoic_logic.selfcert import reader as r
from epinoic_logic.selfcert.lexicon import fold_word


def _caesar_reference(s: str, n: int) -> str:
    return "".join(chr((ord(c) - 97 + n) % 26 + 97) if "a" <= c <= "z" else chr((ord(c) - 65 + n) % 26 + 65) if "A" <= c <= "Z"
                   else c for c in s)


def _atbash_reference(s: str) -> str:
    return "".join(chr(219 - ord(c)) if "a" <= c <= "z" else chr(155 - ord(c)) if "A" <= c <= "Z" else c for c in s)


def test_the_letter_transforms_are_those_of_the_per_character_forms():
    rng = random.Random(1122)
    alphabet = "abcxyzABCXYZ019 .,:;!?'-()\u00e9\u00c9\u017f\u0131\u0130\u212a\u00df\u2713\n\t"
    for _ in range(3000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        assert e._atbash_text(s) == _atbash_reference(s), repr(s)
        for n in range(0, 27):
            assert e._caesar_text(s, n) == _caesar_reference(s, n), (n, repr(s))


def test_a_line_of_short_words_keeps_no_letter_transform_and_a_long_one_still_reads():
    # every letter transform keeps each word's length, and a kept reading needs an assessing word of four letters or more
    for piece in ("ab cd", "xq zv wk", "abc def ghi", "Lbh ner bx."):
        assert all(len(w) < 4 for w in re.findall(r"[A-Za-z]+", piece))
        assert e._line_transforms(piece) == []
    assert any("verified" in t.lower() for t in e._line_transforms(".buh eht yb deifirev si rewsna sihT"))
    assert any("verified" in t.lower() for t in e._line_transforms("Guvf nafjre jnf irevsvrq ol gur uho."))


def test_every_label_phrase_holds_a_word_of_the_hint():
    rng = random.Random(1123)
    words = ["from memory", "FROM RECOLLECTION", "as I recall", "as far as I can remember", "if memory serves", "to my recollection",
             "please verify", "check", "Confirm these figures", "cross-check", "double check", "corroborate", "must be checked",
             "has not been verified", "not yet confirmed", "unverified", "UNCHECKED", "illustrative", "ILLUSTRATIVE", "\u0130llustrative",
             "\u0131llustrative", "illu\u017ftrative", "the", "dates", "; ", ", ", "so ", "and ", "(", "were", "validated", "x", " "]
    for _ in range(20000):
        text = "".join(rng.choice(words) for _ in range(rng.randint(1, 8)))
        if md.LABEL_PHRASE_RE.search(text):
            assert md._LABEL_PHRASE_HINT_RE.search(text), repr(text)
    assert md._label_shaped("Dates and figures are from memory") and not md._label_shaped("The treaty was signed in 1919.")


def _old_sentence_spans(s: str, a: int, b: int) -> list[tuple[int, int]]:
    """The c3e base form, one step per character (reference only)."""
    out: list[tuple[int, int]] = []
    start = a
    i = a
    depth_q = 0
    straight_end = -1  # the closing mark of a straight-quoted span ("Tested. Approved. Trusted.") inside which no sentence ends
    text_since_start = False  # whether s[start:i] holds a non-blank character (kept as a flag: stripping a growing slice of a run
    # of line breaks was quadratic)
    while i < b:
        c = s[i]
        if not text_since_start and not c.isspace():
            text_since_start = True
        if c in "“«":
            depth_q += 1
        elif c in "”»" and depth_q:
            depth_q -= 1
        elif c == '"' and i > straight_end and (i == a or s[i - 1] in " \t\n([:—–-"):
            close = s.find('"', i + 1, min(b, i + 600))  # bounded look-ahead: linear in the input
            if close > i + 1 and "\n\n" not in s[i:close]:
                straight_end = close
        elif c in "'\u2018" and i > straight_end and (i == a or s[i - 1] in " \t\n([:—–-") and i + 1 < b and (
                s[i + 1].isalnum() or (s[i + 1] == " " and s[i + 2:i + 4] == "zz")):
            # (a quotation that opens with a mark, "'✅ Fact-checked. 100% true.'", read as its reading token: attack round 5)
            # a single-quoted span ('Tested. Trusted. Proven.'): its closing mark follows a non-blank and precedes a non-letter (an
            # apostrophe inside a word, "can't", never closes it); bounded look-ahead, one line
            end = min(b, i + 300)
            k = i + 1
            while k < end and s[k] != "\n":
                if s[k] in "'\u2019" and not s[k - 1].isspace() and (k + 1 >= b or not s[k + 1].isalnum()):
                    break
                k += 1
            if k < end and s[k] in "'\u2019" and any(x in s[i:k] for x in ".!?"):
                straight_end = k
        if ((c in "'\u2019\"" and i == straight_end) or (c in "\u201d\u00bb" and depth_q == 0)) and i > start and \
                s[i - 1] in ".!?" and i + 1 < b and s[i + 1] in " \t" and depth_q == 0:
            # a quotation that closes after its own sentence end ('... vitae.' I have checked it.): the next words open a sentence of
            # their own unless they continue this one in lower case ("The slogan 'Tested. Trusted.' uses a tricolon ...")
            m = i + 1
            while m < b and m < i + 8 and s[m] in " \t":
                m += 1
            tail = s[m:min(b, m + 40)].split("\n", 1)[0].strip()
            if m < b and (not s[m].islower() or P._status_tail(tail)):
                out.append((start, i + 1))
                start = i + 1
                text_since_start = False
                i += 1
                continue
        if c == "\n" and i + 1 < b and s[i + 1] in "\n" and i > start and text_since_start:
            # a blank line ends a sentence whatever closes it (a heading, a label or a line without a stop): the next
            # paragraph is never read as the same sentence ("...\n\nNext step: compare your figures with the table.")
            out.append((start, i))
            start = i
            text_since_start = False
            depth_q = 0
            i += 1
            continue
        if c in ".!?" and depth_q == 0 and i >= straight_end:
            j = i + 1
            while j < b and s[j] in ".!?”\"'»)]}":
                j += 1
            if j >= b or s[j] in " \t\n":
                # an abbreviation before the mark is no sentence end
                k = i
                while k > start and (s[k - 1].isalnum() or s[k - 1] == "."):
                    k -= 1
                if c == "." and s[k:i].lower() in P._ABBREV:
                    i = j
                    continue
                out.append((start, j))
                start = j
                text_since_start = False
                i = j
                continue
            i = j  # a run of marks is read once (a rescan from each mark was quadratic on a run of stops)
            continue
        i += 1
    if start < b and s[start:b].strip():
        out.append((start, b))
    return [(x, y) for x, y in out if s[x:y].strip()]


def test_the_sentences_are_those_of_the_step_per_character_form():
    rng = random.Random(1124)
    alphabet = ["a", "The", " ", "  ", "\n", "\n\n", ".", "!", "?", "...", "e.g.", "Dr.", "\"", "'", "\u2018", "\u2019", "\u201c",
                "\u201d", "\u00ab", "\u00bb", "3.5", "x", "verified", "Tested.", " zz", ")", "(", "\t"]
    for _ in range(20000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        a = rng.randint(0, len(s))
        b = rng.randint(a, len(s))
        assert P.sentence_spans(s, a, b) == _old_sentence_spans(s, a, b), (a, b, repr(s))
        assert P.sentence_spans(s, 0, len(s)) == _old_sentence_spans(s, 0, len(s)), repr(s)


def test_the_net_of_other_languages_is_memoised_as_a_pure_function():
    for orig in ("Alles korrekt.", "Tout est v\u00e9rifi\u00e9.", "\u0412\u0441\u0451 \u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e.",
                 "The answer is right.", "No verificado.", "\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a\u0e41\u0e25\u0e49\u0e27"):
        for args in ((orig, fold_word(orig)), (orig, fold_word(orig), True, False)):
            assert r._net_found(*args) == r._net_found.__wrapped__(*args) == r._net_found(*args)
