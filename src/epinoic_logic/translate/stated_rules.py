"""Whether a located excerpt states a premise's rule: a conditional, a universal rule or a biconditional quoted from a record
(repair round 1 of the argument diagnosis, re-run review A-FA-QUOTERULE).

A located excerpt verifies a proposition only as a literal (:mod:`.grounding`, "literals only"), and a relation only when a
record states the same formula (:func:`.relations.stated_relation`). A rule the record states in words was therefore never
verified, so a clean answer that quotes "If domestic sales grow by more than 5% in 2024, we will expand into Europe" and
applies it had an unverified link, labelled leap_in_logic, and was not releasable. This module reads such a rule from the
excerpt's own characters, and only these shapes:

* a **conditional**: "if" or "whenever" opens the condition, which runs to the next clause break (a comma, a semicolon, a
  colon, "then" or the excerpt's end); the consequence is the rest of the excerpt ("If X, Y", "Y if X"); "only if",
  "even if", "as if", "unless" and a reported question ("asked if") open no condition here (a reversed, conceded, compared,
  negated or reported rule is not read), and neither do "when" and "once" ("When the war ended, unemployment rose" reports
  two events, not a rule);
* a **universal rule**: "every", "all", "any" or "each", a noun of up to three tokens and a restrictor ("with", "that",
  "who", "which", "whose", "having", "where"): the condition is what follows the restrictor and the consequence what stands
  outside it ("the new levy applies to every firm with more than 50 employees");
* a **biconditional**: "if and only if", "exactly when" or "precisely when" between its two sides, for an ``iff`` premise.

The premise must be an implication (or a biconditional) whose two sides are conjunctions of literals: an atom or its
negation, or a comparison of one symbol with one literal. A side is stated by a clause when each of its literals is:

* an atom: every root (:func:`epinoic_logic.lexis.root`) of its symbol's meaning that tells it from the rule's other side
  occurs in the clause, or all but one of four or more ("If demand for steel rises, steel prices rise" states demand ->
  prices, never prices -> demand, though both sides say "steel" and "rise"; the roots the sides share, their common
  subject, are not required: the record may say "we" for "the firm"), leaving out the instance words a rule leaves
  general (a year when the excerpt states none; for a universal rule, the capitalised words and single letters the
  excerpt does not hold: "Firm Z" against "every firm"); a negated atom, or a negated meaning, needs a negation word in
  the clause, and an atom that is neither needs none;
* a comparison ``x op c``: a figure of the clause states ``c`` (typed, :func:`.quantities.literal_matches`) so that it
  establishes ``op`` (:func:`.assertion.stated_as`), and a root of ``x``'s meaning that the other side does not share
  occurs in the clause.

The antecedent must be stated by the condition and the consequent by the consequence; a converse ("expand -> growth > 5")
has its sides in the wrong clauses and is not stated. Instantiating a universal rule to the named case of the meaning
("Firm Z") is what the instance-word rule allows; nothing else is. Everything is read from the excerpt's characters as
data with the shared tokenizer and closed word lists; nothing is evaluated.

A rule whose sides are stated is stated as the source's own only when nothing in its sentence qualifies it (close round 1,
ADV6-01: a hedged, framed or cut rule was verified as "if A then B"). :func:`rule_qualifier` reads the sentence that holds
the excerpt, inside the excerpt and around it, by closed word lists:

* a hedge or another mood in the consequence's clause (:data:`RULE_HEDGES`: "Y might fall", "Y tends to fall", "Y would
  fall"), or an "or" there ("Y falls or savings fall"), unless the consequent's own meaning holds the word;
* a condition the premise drops: a part of the condition joined by "and", "but" or "while" that shares no word with the
  antecedent ("If taxes rise and wages are frozen, ...");
* a frame before the rule: a clause ending in "that" or "whether", or in a verb of a view, that holds a word of
  :data:`RULE_FRAMES` or a negation ("Some politicians claim that ...", "It is a myth that ...", "Nobody has shown that
  ...", "Economists disagree about whether, ..."), a short opening phrase with a word of scope ("In some economies, ..."), or
  a question ("Is it really true that ...");
* after the rule, a restriction (:data:`RULE_RESTRICTIONS`: "..., but only when the water is warm", "unless ...") or an
  attribution tag with a verb of a view that names no document ("..., some say", "..., a minister warned"), unless the
  premise's own meaning writes that restriction or that verb ("every player except the goalkeeper gets a bonus").

Such a rule is returned with its ``qualifier``: the source does not state the premise's rule as a given, so a located excerpt
of it refutes the premise (``source_mismatch``) and a record sentence of it validates nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Optional, Sequence

from .. import lexis
from .quantities import SourceText, declared_reading, figures_in, literal_matches, sentence_of

__all__ = ["CONDITION_CUES", "BLOCKING_BEFORE_IF", "UNIVERSAL_CUES", "RESTRICTORS", "BICONDITIONAL_CUES", "RULE_CONTENT_WORDS", "StatedRule",
           "meaning_roots", "stated_rule", "stated_enumeration", "EXCLUSIVE_CUES", "disjunction_shape", "stated_disjunction",
           "RULE_HEDGES", "RULE_FRAMES", "RULE_RESTRICTIONS", "rule_qualifier"]

#: Words that open the condition of a conditional rule ("when" and "once" are left out: "When the war ended, unemployment
#: rose" reports two events, not a rule; "when" opens one in a generic statement only, :data:`WHEN_CUE`).
CONDITION_CUES: frozenset[str] = frozenset({"if", "whenever"})
#: A word right before "if" that makes it no plain condition ("only if" reverses the rule, "even if" concedes, "as if"
#: compares, "asked if" reports a question).
BLOCKING_BEFORE_IF: frozenset[str] = frozenset({"only", "even", "as", "asked", "ask", "asks", "wondered", "wonder", "know", "knew", "see",
                                                "check", "checked", "decide", "unclear", "doubt", "sure", "whether"})
#: "when" opens a rule's condition only in a generic statement (accuracy round 1, DIFF3-07): an excerpt that states no past
#: event in either clause ("When demand for copper rises, the price of copper rises"; "The enzyme denatures when the
#: temperature rises above 40 °C"), never a report of two events ("When the war ended, unemployment rose":
#: :func:`_generic_statement`).
WHEN_CUE = "when"
#: Words right before "when" that make it no plain condition: those that block "if", a restriction or a biconditional
#: ("except when", "exactly when", "precisely when"), a time it names ("the year when", "at a time when") or a report of
#: when something happened ("said when").
_BLOCKING_BEFORE_WHEN: frozenset[str] = BLOCKING_BEFORE_IF | frozenset({
    "exactly", "precisely", "except", "until", "since", "say", "says", "said", "time", "times", "year", "years", "day", "days", "month",
    "months", "week", "weeks", "moment", "moments", "period", "periods", "era", "age", "decade", "decades", "century", "season", "hour",
    "hours", "point", "stage", "date", "occasion", "occasions", "night", "morning", "evening", "summer", "winter", "spring", "autumn"})
#: Past forms of common verbs whose past is not written with "-ed" (closed list): an excerpt holding one reports an event.
_PAST_FORMS: frozenset[str] = frozenset("""
was were had did became began came went rose fell grew took made gave got saw said found kept held brought thought told ran won
sold built fought met sent spent stood struck wrote broke chose drove froze sank shrank left felt heard meant knew threw flew drew
wore tore shook rode woke spoke stole forgot caught taught bought sought hung dug stuck spun slid hid fled shot dealt slept swept
wept crept lent sat rang sang swam drank arose awoke overcame underwent undertook withdrew forbade forgave mistook
""".split())
#: Words that end in "-ed" and are no past form ("speed", "hundred", "exceeds" aside, "exceed" is present).
_NOT_PAST_ED: frozenset[str] = frozenset({"hundred", "kindred", "sacred", "naked", "wicked", "hatred", "rugged", "ragged", "jagged",
                                          "crooked", "embed", "infrared", "beloved"})
#: Past forms in "-eed" ("agreed", "freed"); every other "-eed" word is a present or a noun ("exceed", "need", "speed").
_PAST_EED: frozenset[str] = frozenset({"agreed", "freed", "decreed", "guaranteed", "disagreed", "refereed"})
#: A word before an "-ed" form that makes it a participle or an adjective, not a past ("is heated", "has raised", "when
#: heated", "the saturated ground").
_PARTICIPLE_LEADS: frozenset[str] = frozenset({
    "is", "are", "am", "be", "being", "been", "gets", "get", "getting", "becomes", "become", "has", "have", "having", "remains", "remain",
    "stays", "stay", "seems", "seem", "looks", "look", "feels", "feel", "when", "whenever", "if", "once", "unless", "the", "a", "an", "its",
    "their", "this", "these", "those", "his", "her", "our", "your", "any", "each", "every", "all", "fully", "partly", "well", "not", "newly",
    "freshly", "properly", "badly", "correctly", "highly", "poorly"})
#: Universal quantifiers and the restrictors after their noun (a universal rule).
UNIVERSAL_CUES: frozenset[str] = frozenset({"every", "all", "any", "each"})
RESTRICTORS: frozenset[str] = frozenset({"with", "that", "who", "which", "whose", "having", "where"})
#: Token sequences between the two sides of a biconditional.
BICONDITIONAL_CUES: tuple[tuple[str, ...], ...] = (("if", "and", "only", "if"), ("exactly", "when"), ("precisely", "when"))
#: Characters of the text between two tokens that end a clause.
_BREAK_CHARS = frozenset(",;:")
_MAX_EXCERPT = 2000


@dataclass(frozen=True)
class StatedRule:
    """Where a located excerpt states a premise's rule: the source, the excerpt's characters, the cue that shapes the rule,
    and (``qualifier``) what in its sentence keeps the rule from being the source's own statement (:func:`rule_qualifier`),
    or None when nothing does."""
    source: SourceText
    start: int
    end: int
    cue: str
    qualifier: Optional[str] = None

    @property
    def written(self) -> str:
        return self.source.text[self.start:self.end]

    def where(self) -> str:
        label = {"supplied_text": "supplied text", "task": "task"}.get(self.source.kind, self.source.kind)
        return f"{label} {self.source.ident} characters {self.start}-{self.end} ({self.written[:160]!r}, a rule opened by '{self.cue}')"


@dataclass(frozen=True)
class _Tok:
    start: int
    end: int
    text: str
    word: str


def _tokens(text: str, a: int, b: int) -> list[_Tok]:
    return [_Tok(a + s, a + e, text[a + s:a + e], t) for s, e, t in lexis.token_spans(text[a:b])]


def _break_after(text: str, toks: list[_Tok], i: int) -> bool:
    """Whether a clause ends after token ``i``: a break character before the next token, or the next token is "then"."""
    if i + 1 >= len(toks):
        return True
    gap = text[toks[i].end:toks[i + 1].start]
    return any(ch in _BREAK_CHARS for ch in gap) or toks[i + 1].word == "then"


def _clause_end(text: str, toks: list[_Tok], i: int) -> int:
    """The index after the last token of the clause that starts at token ``i``."""
    j = i
    while j < len(toks) and not _break_after(text, toks, j):
        j += 1
    return min(j + 1, len(toks))


#: A definition's copula and its explicit cues ("X is defined as Y", "X means Y", "Y is called X"): repair round 5, ADV5-09.
_COPULAS = frozenset({"is", "are"})
_DEFINING_AFTER_COPULA: tuple[tuple[str, ...], ...] = (("defined", "as"), ("the", "name", "for"))
_DEFINING_VERBS = frozenset({"means", "mean", "denotes", "denote"})
_NAMING_AFTER_COPULA: tuple[tuple[str, ...], ...] = (("called",), ("known", "as"), ("termed",), ("named",))
_ARTICLES = frozenset({"a", "an"})
#: At most this many tokens name the term a definition defines.
_MAX_DEFINED_TOKENS = 6
#: At most this many tokens state the definiens before the copula of a naming form ("A shape with four equal sides and four
#: right angles is called a square"), where the defined term stands after the copula.
_MAX_DEFINIENS_TOKENS = 24


def _definition_readings(text: str, toks: list[_Tok]) -> list[tuple[str, set[int], set[int], bool]]:
    """``(cue, definiens indices, defined-term indices, both ways)`` for a sentence that states what a term is (repair round 5,
    ADV5-09: a definition the task states, encoded as 'iff' or 'if ... then', was refuted as the translation's own link):

    * "X is defined as Y", "X means Y", "Y is called X", "Y is known as X": a definition, read both ways;
    * "A X is a Y that/whose/which/who/with ...": a term given its kind and what tells it apart (a genus and a differentia),
      a definition, read both ways ("A prime number is a whole number greater than 1 whose only divisors are 1 and itself");
    * "X is Y", "Xs are Ys": what every X is, read one way only (X -> Y: "Whales are mammals" never gives mammal -> whale).

    The defined term is at most :data:`_MAX_DEFINED_TOKENS` tokens before the copula; nothing in the sentence may open a
    condition ("if", a universal rule's restrictor before the copula) and the sentence is one clause up to the copula."""
    words = [t.word for t in toks]
    out: list[tuple[str, set[int], set[int], bool]] = []
    if any(w in CONDITION_CUES or w in ("unless", "when", "whenever", "suppose", "assume") for w in words):
        return out
    k = next((i for i, w in enumerate(words) if w in _COPULAS or w in _DEFINING_VERBS), None)
    # a naming form ("Y is called X") puts the defined term after the copula, so what stands before it is the definiens and
    # may be longer than a term
    naming = k is not None and k > 0 and words[k] in _COPULAS and any(tuple(words[k + 1:k + 1 + len(c)]) == c for c in _NAMING_AFTER_COPULA)
    before = _MAX_DEFINIENS_TOKENS if naming else _MAX_DEFINED_TOKENS + 3
    if k is None or k == 0 or k > before or any(_break_after(text, toks, j) for j in range(0, k - 1)):
        # the copula opens the sentence, comes late, or a clause mark stands before it ("In this question, a prime number
        # is ...": the lead is cut at its comma below)
        lead_cut = next((j + 1 for j in range(0, k - 1) if _break_after(text, toks, j)), None) if k is not None and k > 0 else None
        if lead_cut is None or k - lead_cut < 1 or k - lead_cut > before - 2:
            return out
        first = lead_cut
    else:
        first = 0
    end = len(toks)
    defined = [i for i in range(first, k) if words[i] not in _ARTICLES and words[i] != "the"]
    if not defined or (len(defined) > _MAX_DEFINED_TOKENS and not naming):
        return out
    after = k + 1
    if words[k] in _DEFINING_VERBS:
        out.append((words[k], set(range(after, end)), set(defined), True))
        return out
    for cue in _DEFINING_AFTER_COPULA:
        if tuple(words[after:after + len(cue)]) == cue:
            out.append((f"{words[k]} {' '.join(cue)}", set(range(after + len(cue), end)), set(defined), True))
            return out
    for cue in _NAMING_AFTER_COPULA:
        if tuple(words[after:after + len(cue)]) == cue:
            named = [i for i in range(after + len(cue), end) if words[i] not in _ARTICLES and words[i] != "the"]
            if 0 < len(named) <= _MAX_DEFINED_TOKENS:
                out.append((f"{words[k]} {' '.join(cue)}", set(defined), set(named), True))
            return out
    rest = [i for i in range(after, end)]
    if not rest:
        return out
    genus_differentia = (words[first] in _ARTICLES and words[after:after + 1] and words[after] in _ARTICLES
                         and any(words[i] in RESTRICTORS for i in rest[1:]))
    out.append((words[k], set(rest), set(defined), bool(genus_differentia)))
    return out


def _generic_statement(words: Sequence[str]) -> bool:
    """Whether an excerpt's words state no past event (accuracy round 1, DIFF3-07): no past form of the closed list
    (:data:`_PAST_FORMS`) and no "-ed" form that a participle lead does not precede ("is damaged", "has raised", "when
    heated" and "the treated plants" are no past). "When demand for copper rises, the price of copper rises" is generic;
    "When the war ended, unemployment rose" reports two events. Linear in the words."""
    for i, w in enumerate(words):
        if w in _PAST_FORMS:
            return False
        if len(w) > 4 and w.endswith("ed") and w not in _NOT_PAST_ED and not (w.endswith("eed") and w not in _PAST_EED):
            if not (i > 0 and words[i - 1] in _PARTICIPLE_LEADS):
                return False
    return True


def _readings(text: str, toks: list[_Tok], biconditional: bool) -> list[tuple[str, set[int], set[int]]]:
    """``(cue, condition token indices, consequence token indices)`` for every rule shape of the excerpt. A definition
    (:func:`_definition_readings`) gives its definiens as the condition and its defined term as the consequence, and for a
    definition read both ways the converse too. "when" opens a condition only in a generic statement
    (:func:`_generic_statement`, accuracy round 1, DIFF3-07), and as "if" does, never after a word that makes it a
    restriction, a biconditional, a time or a report (:data:`_BLOCKING_BEFORE_WHEN`)."""
    out: list[tuple[str, set[int], set[int]]] = []
    words = [t.word for t in toks]
    every = set(range(len(toks)))
    definitions = _definition_readings(text, toks)
    if biconditional:
        for k in range(len(words)):
            for cue in BICONDITIONAL_CUES:
                if tuple(words[k:k + len(cue)]) == cue:
                    left = set(range(0, k))
                    right = set(range(k + len(cue), _clause_end(text, toks, k + len(cue)) if k + len(cue) < len(toks) else len(toks)))
                    out.append((" ".join(cue), left, right))
        # a definition states the biconditional of its term and its definiens; a plain copula states one way only
        out += [(f"{cue} (a definition)", definiens, term) for cue, definiens, term, both in definitions if both]
        return out
    for cue, definiens, term, both in definitions:
        out.append((f"{cue} (a definition)" if both else f"{cue} (what every such thing is)", term, definiens))  # term -> definiens
        if both:
            out.append((f"{cue} (a definition)", definiens, term))  # definiens -> term
    generic: Optional[bool] = None
    for k, w in enumerate(words):
        if w == WHEN_CUE:
            if k > 0 and words[k - 1] in _BLOCKING_BEFORE_WHEN:
                continue
            if generic is None:
                generic = _generic_statement(words)
            if not generic or k + 1 >= len(toks):
                continue
            cond = set(range(k + 1, _clause_end(text, toks, k + 1)))
            out.append((w, cond, every - cond - {k}))
        elif w in CONDITION_CUES:
            if w == "if" and k > 0 and words[k - 1] in BLOCKING_BEFORE_IF:
                continue
            if w == "if" and tuple(words[k:k + 4]) == ("if", "and", "only", "if"):
                continue
            if k + 1 >= len(toks):
                continue
            cond = set(range(k + 1, _clause_end(text, toks, k + 1)))
            out.append((w, cond, every - cond - {k}))
        elif w in UNIVERSAL_CUES:
            for r in range(k + 2, min(k + 5, len(toks))):
                if words[r] in RESTRICTORS:
                    cond = set(range(r + 1, _clause_end(text, toks, r + 1))) if r + 1 < len(toks) else set()
                    if cond:
                        out.append((f"{w} ... {words[r]}", cond, every - cond - {k, r}))
                    break
    return out


def _is_year(t: str) -> bool:
    return len(t) == 4 and t.isdecimal() and 1000 <= int(t) <= 2199


#: Prepositions that open a phrase placing a case in a setting ("near the Tamar", "in Country P", "in the experiment", "during
#: the trial"): a general rule leaves its setting out (accuracy round 2, V1I-05).
_SETTING_PREPOSITIONS = frozenset({"in", "near", "at", "on", "during", "within", "across", "throughout", "around", "inside", "outside", "along",
                                   "beside", "among"})
#: Words a setting phrase may hold besides its content words: determiners and possessives.
_SETTING_DETERMINERS = frozenset({"the", "a", "an", "this", "that", "these", "those", "its", "their", "his", "her", "our", "your"})
#: The most names one setting phrase holds ("in the River Tamar Valley").
_MAX_SETTING_WORDS = 3
#: The prepositions' roots, set aside when two sides' settings are compared.
_SETTING_ROOTS = frozenset(lexis.root(w) for w in _SETTING_PREPOSITIONS)
#: Words that may stand between a setting's determiner and its head noun ("in the second trial").
_SETTING_MODIFIERS = frozenset({"first", "second", "third", "fourth", "fifth", "final", "last", "same", "whole"})


def _setting_name(raw: str, start: int) -> bool:
    """A word of a setting's name: capitalised (never the meaning's first word), a single letter or a number ("Country P",
    "the Tamar", "Trial 2")."""
    return (raw[:1].isupper() and start > 0) or (len(raw) == 1 and raw.isalpha()) or raw.isdecimal()


def _setting_head(t: str) -> bool:
    """A lowercase word that may be a setting's head noun after its determiner ("in the experiment"): no verb form the
    shared word lists read as one (an irregular form of :data:`lexis.IRREGULAR_FORMS`, a word ending in "-ed"), so a
    meaning's own verb is never read as its setting ("the patient in the trial recovered" places it in the trial; its verb
    stays a word the rule must state)."""
    return not (t in lexis.IRREGULAR_FORMS or (len(t) > 4 and t.endswith("ed")))


def _setting_words(meaning: str, excerpt: set[str]) -> set[str]:
    """The roots of the setting phrases of a meaning that the excerpt does not hold (accuracy round 2, V1I-05): a preposition
    of :data:`_SETTING_PREPOSITIONS` (not the meaning's first word) and its determiners, then one to
    :data:`_MAX_SETTING_WORDS` names (:func:`_setting_name`: "farmland near the Tamar was damaged" places its case near the
    Tamar, "borrowing in Country P fell" in Country P), or, after a determiner, a head noun (:func:`_setting_head`) with the
    closed modifiers before it and names after it ("the enzyme denatured in the experiment", "in the second trial"). The
    phrase ends at the meaning's end, a comma, another such preposition, a word the excerpt holds, a function or frame word,
    or any other word, which stays a word the rule must state. A phrase with a word that carries a rule's content
    (:data:`RULE_CONTENT_WORDS`: "in the only trial"), a negation or more names than the bound places no case, and neither
    does a preposition the excerpt holds itself ("near the river" against "farmland near the river"). Read once over the
    meaning's tokens; the prepositions' roots are returned with the phrases'."""
    spans = lexis.token_spans(meaning)
    toks = [t for _a, _b, t in spans]
    out: set[str] = set()
    k, n = 1, len(toks)

    def stops(j: int) -> bool:  # the phrase cannot go on at token j
        t = toks[j]
        return (t in _SETTING_PREPOSITIONS or "," in meaning[spans[j - 1][1]:spans[j][0]] or t in lexis.FUNCTION_WORDS or t in lexis.FRAME_WORDS
                or lexis.root(t) in excerpt)

    def carries(j: int) -> bool:  # a word that makes the phrase part of what the rule states
        t = toks[j]
        return t in RULE_CONTENT_WORDS or t in lexis.NEGATION_WORDS or t.endswith("n't")

    def name(j: int) -> bool:
        return _setting_name(meaning[spans[j][0]:spans[j][1]], spans[j][0])

    while k < n:
        if toks[k] not in _SETTING_PREPOSITIONS or lexis.root(toks[k]) in excerpt:
            k += 1
            continue
        j = k + 1
        determined = False
        while j < n and toks[j] in _SETTING_DETERMINERS:
            j += 1
            determined = True
        content: list[str] = []
        names = 0
        bad = False
        if determined:
            m = j
            while m < n and toks[m] in _SETTING_MODIFIERS:
                m += 1
            if m < n and not stops(m) and not carries(m) and not name(m) and _setting_head(toks[m]):
                content += toks[j:m + 1]  # the closed modifiers and the head noun ("the second trial")
                j = m + 1
        while j < n and not stops(j):
            if carries(j):
                bad = True
                break
            if not name(j):
                break
            if names == _MAX_SETTING_WORDS:
                bad = True  # a name longer than a setting's
                break
            content.append(toks[j])
            names += 1
            j += 1
        if content and not bad and not (j < n and carries(j)):
            out |= {lexis.root(t) for t in content} | {lexis.root(toks[k])}
        k = max(j, k + 1)
    return out


def _instance_words(meaning: str, excerpt: set[str], universal: bool, settings: bool = False) -> set[str]:
    """The words of a meaning a general rule leaves out: a year when the excerpt states no year (the rule is timeless,
    the meaning dates its case), with ``settings`` a setting phrase the excerpt does not hold (:func:`_setting_words`:
    "near the Tamar", "in Country P", "in the experiment"; accuracy round 2, V1I-05: a rule quoted verbatim and applied to
    the case the question names was held back), and, for a universal rule only, the capitalised words and single letters
    the excerpt does not hold (the named case, "Firm Z", that instantiates "every firm"). A name the excerpt holds is a word
    of the rule; a name absent from a conditional is content the excerpt does not state, unless a setting phrase places it."""
    out: set[str] = set(_setting_words(meaning, excerpt)) if settings else set()
    excerpt_years = any(_is_year(r) for r in excerpt)
    for s, e, t in lexis.token_spans(meaning):
        raw = meaning[s:e]
        r = lexis.root(t)
        if r in excerpt:
            continue
        if _is_year(t):
            if not excerpt_years:
                out.add(r)
        elif universal and ((raw[:1].isupper() and s > 0) or len(t) == 1):
            out.add(r)
    return out


#: Closed-class words that still carry a rule's content ("a number is even", "more than", "both", "two"): kept when a
#: meaning is read for a rule, though :data:`epinoic_logic.lexis.FUNCTION_WORDS` holds them.
RULE_CONTENT_WORDS: frozenset[str] = frozenset({
    "even", "more", "less", "most", "least", "few", "many", "all", "every", "each", "some", "any", "both", "either", "neither", "one",
    "two", "three", "only", "over", "under", "up", "down", "against", "out", "off", "near", "within", "before", "after"})


def meaning_roots(meaning: str) -> set[str]:
    """The roots of a meaning's words: its tokens without the function words (:data:`RULE_CONTENT_WORDS` kept), the frame
    words and the negation words."""
    out: set[str] = set()
    for t in lexis.tokens(meaning):
        if (t in lexis.FUNCTION_WORDS and t not in RULE_CONTENT_WORDS) or t in lexis.FRAME_WORDS or t in lexis.NEGATION_WORDS or t.endswith("n't"):
            continue
        r = lexis.root(t)
        if r:
            out.add(r)
    return out


def _clause_roots(toks: list[_Tok], idx: set[int]) -> set[str]:
    return {lexis.root(toks[i].word) for i in idx}


def _clause_negated(toks: list[_Tok], idx: set[int]) -> bool:
    return lexis.negation_markers([toks[i].word for i in sorted(idx)]) > 0


def _literals(node: Any) -> Optional[list[Any]]:
    """The conjuncts of a rule side when each is a literal (an atom, its negation, or a comparison of a symbol with a
    literal), else None."""
    out: list[Any] = []
    stack = [node]
    while stack:
        n = stack.pop()
        op = getattr(n, "op", None)
        if op == "and":
            stack.extend(reversed(n.args))
            continue
        if op == "var" or (op == "not" and getattr(n.arg, "op", None) == "var"):
            out.append(n)
            continue
        if op in ("eq", "lt", "le", "gt", "ge"):
            left, right = n.left, n.right
            if getattr(left, "op", None) == "var" and getattr(right, "op", None) in ("int", "real"):
                out.append(n)
                continue
            if getattr(right, "op", None) == "var" and getattr(left, "op", None) in ("int", "real"):
                out.append(n)
                continue
        return None
    return out if out else None


_FLIP = {"eq": "eq", "lt": "gt", "le": "ge", "gt": "lt", "ge": "le"}


def _meaning_of(lit: Any, symbols: dict[str, Any]) -> str:
    op = getattr(lit, "op", None)
    if op in ("var", "not"):
        atom = lit if op == "var" else lit.arg
        name = atom.name
    else:
        name = lit.left.name if getattr(lit.left, "op", None) == "var" else lit.right.name
    sym = symbols.get(name)
    return (sym.meaning if sym is not None else None) or name.replace("_", " ")


def _words_of(lit: Any, symbols: dict[str, Any], excerpt: set[str], universal: bool, settings: bool = False) -> set[str]:
    """The roots a literal's clause must hold: its symbol's meaning without the instance words (with ``settings``, its
    setting phrases too: :func:`_instance_words`)."""
    meaning = _meaning_of(lit, symbols)
    return meaning_roots(meaning) - _instance_words(meaning, excerpt, universal, settings)


def _enough(found: int, needed: int) -> bool:
    """Every distinct root, or all but one of four or more."""
    return needed > 0 and (found == needed or (needed >= 4 and found >= needed - 1))


def _states_literal(lit: Any, symbols: dict[str, Any], src: SourceText, toks: list[_Tok], idx: set[int], other: set[str], universal: bool,
                    settings: bool = False) -> bool:
    """Whether the clause (tokens ``idx``) states the literal (module docstring). ``other``: the roots of the rule's other
    side; the roots that tell this side from it must be in this clause ("If demand for steel rises, steel prices rise"
    states demand -> prices, never prices -> demand, though both sides say "steel" and "rise"), and the roots the two
    sides share (their common subject, often a pronoun in the record: "we will expand" for "the firm will expand") are
    not required. With ``settings`` a setting phrase of the meaning is an instance word (:func:`_instance_words`)."""
    from .assertion import stated_as  # imported here: the assertion reader imports this package's quantities
    if not idx:
        return False
    op = getattr(lit, "op", None)
    wanted = _words_of(lit, symbols, _clause_roots(toks, set(range(len(toks)))), universal, settings)
    have = _clause_roots(toks, idx)
    if op in ("var", "not"):
        meaning = _meaning_of(lit, symbols)
        distinct = wanted - other
        if not _enough(len(distinct & have), len(distinct)):
            return False
        negated = (op == "not") != lexis.negated(meaning)
        return negated == _clause_negated(toks, idx)
    left, right = lit.left, lit.right
    if getattr(left, "op", None) == "var":
        name, node, required = left.name, right, op
    else:
        name, node, required = right.name, left, _FLIP[op]
    try:
        value = Fraction(node.value)
    except (ValueError, ZeroDivisionError):
        return False
    meaning = _meaning_of(lit, symbols)
    lo, hi = min(toks[i].start for i in idx), max(toks[i].end for i in idx)
    figures = [f for f in figures_in(src) if lo <= f.start and f.end <= hi]
    matches, _why = literal_matches(value, figures, declared_reading(meaning))
    if not any(stated_as(src.text, m.figure.start, m.figure.end, required) is None for m in matches):
        return False
    return bool((wanted - other) & have)


#: Words that close an enumeration: the things a sentence lists are all there are ("exactly three bridges: North, Mill and
#: Station", "the only two shifts are ...", "consists of", "namely").
_CLOSING_ENUMERATION = frozenset({"exactly", "only", "just", "namely", "consists", "consist", "comprises", "comprise"})
_NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12}
_UNIVERSALS = frozenset({"all", "every", "each", "both"})


def stated_enumeration(expr: Any, symbols: dict[str, Any], src: SourceText, span: tuple[int, int]) -> Optional[StatedRule]:
    """Where the excerpt ``span`` of ``src`` closes an enumeration that the premise uses (repair round 5, ADV5-09: "The town
    has exactly three bridges: North, Mill and Station" states that all the bridges are safe exactly when each of the three
    is, and the premise was refuted as the translation's own link). The premise is ``and(A1, ..., Ak) -> U`` or ``U <->
    and(A1, ..., Ak)`` (k >= 2, atoms only, either orientation of the biconditional), where ``U``'s meaning holds a universal
    word ("all", "every", "each", "both"); the sentence holds a closing word (:data:`_CLOSING_ENUMERATION`) and, when it
    gives a count, the count k; the word that tells each ``Ai`` from the others (its name: "North") stands in the sentence;
    and a word ``U`` and every ``Ai`` share (what is enumerated: "bridge") stands in it too. What the premise says of every
    item ("safe") is the premise's own predicate and need not stand in the sentence. No negation word may stand in it.
    None otherwise."""
    op = getattr(expr, "op", None)
    if op not in ("implies", "iff"):
        return None
    a, b = span
    if b <= a or b - a > _MAX_EXCERPT:
        return None
    sides = [(expr.left, expr.right)] if op == "implies" else [(expr.left, expr.right), (expr.right, expr.left)]
    for conj, univ in sides:
        if getattr(conj, "op", None) != "and" or getattr(univ, "op", None) != "var":
            continue
        items = list(conj.args)
        if len(items) < 2 or any(getattr(x, "op", None) != "var" for x in items):
            continue
        u_meaning = _meaning_of(univ, symbols)
        if not set(lexis.tokens(u_meaning)) & _UNIVERSALS:
            continue
        item_roots = [meaning_roots(_meaning_of(x, symbols)) for x in items]
        common = set.intersection(*item_roots)
        names = [r - common for r in item_roots]
        if any(not n for n in names):
            continue
        toks = _tokens(src.text, a, b)
        words = [t.word for t in toks]
        roots = {lexis.root(w) for w in words}
        if lexis.negation_words(words) or not set(words) & _CLOSING_ENUMERATION:
            continue
        counts = [int(w) for w in words if w.isdecimal() and len(w) <= 2] + [_NUMBER_WORDS[w] for w in words if w in _NUMBER_WORDS]
        if counts and len(items) not in counts:
            continue
        enumerated = common & meaning_roots(u_meaning) & roots
        if not enumerated or not all(n & roots for n in names):
            continue
        return StatedRule(source=src, start=a, end=b, cue="a closed enumeration")
    return None


# ------------------------------------------------------------------------------------- what qualifies a stated rule

#: Words in a rule's consequence clause that hedge it or put it in another mood (close round 1, ADV6-01): "If X, Y might
#: fall" states a possibility, "Y tends to fall" a tendency, "Y usually falls" a habit, "Y would fall" a counterfactual;
#: none of them states "if X then Y". "May" written with a capital inside a sentence is the month, not the modal.
RULE_HEDGES: frozenset[str] = frozenset({
    "might", "may", "could", "can", "would", "should", "often", "usually", "sometimes", "occasionally", "rarely", "seldom",
    "frequently", "generally", "typically", "normally", "tend", "tends", "tended", "likely", "unlikely", "probably", "possibly",
    "perhaps", "maybe", "potentially"})
#: Words of a clause around a rule that present it as a view, a denial, a doubt, a question or a limited case rather than
#: the source's own statement ("Some politicians claim that ...", "It is a myth that ...", "Few economists now believe that
#: ...", "Nobody has shown that ...", "The report rejects the idea that ...", "Economists disagree about whether, ...").
RULE_FRAMES: frozenset[str] = frozenset({
    "some", "few", "nobody", "none", "myth", "myths", "wrong", "false", "untrue", "incorrect", "mistaken", "misconception", "fallacy",
    "reject", "rejects", "rejected", "deny", "denies", "denied", "dispute", "disputes", "disputed", "doubt", "doubts", "doubted",
    "doubtful", "question", "questions", "questioned", "questionable", "disagree", "disagrees", "disagreed", "debate", "debated",
    "debatable", "contested", "unclear", "uncertain", "unproven", "whether", "claim", "claims", "claimed", "allege", "alleges",
    "alleged", "allegedly", "supposedly", "assume", "assumes", "assumed", "assuming", "assumption", "believe", "believes", "believed",
    "belief", "think", "thinks", "thought", "suggest", "suggests", "suggested", "according", "ask", "asks", "asked", "wonder",
    "wonders", "wondered"}) | RULE_HEDGES
#: What restricts a rule beyond its condition ("..., but only when the water is warm", "unless ...", "provided that ...").
RULE_RESTRICTIONS: tuple[tuple[str, ...], ...] = (
    ("unless",), ("except",), ("only", "when"), ("only", "if"), ("only", "where"), ("only", "while"), ("provided",), ("providing",),
    ("as", "long", "as"), ("so", "long", "as"), ("but", "only"))
#: Words of scope that make a short opening phrase limit the rule ("In some economies, ...", "Sometimes, ...").
_SCOPE_WORDS: frozenset[str] = RULE_HEDGES | frozenset({"some", "few", "certain", "whether"})
#: A sentence that opens with one of these before a subject word is a question ("Is it really true that ...").
_QUESTION_OPENERS: frozenset[str] = frozenset({"is", "are", "was", "were", "do", "does", "did", "can", "could", "would", "should", "will",
                                               "has", "have", "had", "must", "might", "may"})
_QUESTION_SUBJECTS: frozenset[str] = frozenset({"it", "this", "that", "there", "they", "we", "you", "he", "she", "the", "a", "an", "such",
                                                "any", "all", "these", "those"})
#: Verbs of a view: a clause ending in one frames the rule after it ("Some say if ..."), and an attribution tag after the rule
#: with one says whose view the rule is ("..., some say", "..., a minister warned").
_VIEW_VERBS: frozenset[str] = frozenset({"say", "says", "said", "claim", "claims", "claimed", "argue", "argues", "argued", "believe", "believes",
                                         "believed", "warn", "warns", "warned", "think", "thinks", "suggest", "suggests", "insist", "insists",
                                         "maintain", "maintains", "allege", "alleges", "alleged", "contend", "contends"})
#: Nouns of a document: a tag that credits the rule to one ("..., the report says") gives the source's own statement.
_DOCUMENT_NOUNS: frozenset[str] = frozenset({"report", "text", "extract", "source", "study", "article", "document", "passage", "author", "writer",
                                             "table", "data", "survey", "book", "chapter", "paper"})
#: Words that open a new clause of a sentence for the segment reading.
_SEGMENT_WORDS: frozenset[str] = frozenset({"but", "although", "though", "whereas", "while", "because", "unless", "except"})
#: Words that join parts of a condition: a part that shares no word with the antecedent is a condition the premise drops.
_CONDITION_JOINS: frozenset[str] = frozenset({"and", "but", "while", "whereas"})
#: How much of a sentence around an excerpt is read, and how short an opening phrase is.
_SENTENCE_REACH = 600
_MAX_OPENING_PHRASE = 6
_MAX_TAG_TOKENS = 12


def _sentence_tokens(src: SourceText, a: int, b: int) -> tuple[int, int, list[_Tok]]:
    """``(start, end, tokens)`` of the sentence of ``src`` that holds ``a``-``b``, read at most :data:`_SENTENCE_REACH`
    characters beyond the span on each side."""
    sa, sb = sentence_of(src.text, a, b)
    sa, sb = max(sa, a - _SENTENCE_REACH, 0), min(sb, b + _SENTENCE_REACH, len(src.text))
    sa, sb = min(sa, a), max(sb, b)
    return sa, sb, _tokens(src.text, sa, sb)


def _segments(text: str, toks: list[_Tok]) -> list[int]:
    """The clause segment of every token: a new segment starts after a clause mark (a comma, a semicolon, a colon) and at a
    word of :data:`_SEGMENT_WORDS`."""
    out: list[int] = []
    seg = 0
    for i, t in enumerate(toks):
        if i > 0 and (any(ch in _BREAK_CHARS for ch in text[toks[i - 1].end:t.start]) or t.word in _SEGMENT_WORDS):
            seg += 1
        out.append(seg)
    return out


def _hedge_word(text: str, tok: _Tok, first: bool) -> bool:
    """Whether a token is a hedge of :data:`RULE_HEDGES` as written: "May" with a capital inside a sentence is the month."""
    if tok.word not in RULE_HEDGES:
        return False
    return not (tok.word == "may" and text[tok.start:tok.start + 1].isupper() and not first)


# ------------------------------------------------------------------ accuracy round 1 (DV2-03): what qualifies the rule itself

#: Words that open another conjunct of a consequence clause ("..., borrowing falls and firms may delay investment",
#: "... and so spending can weaken"): a hedge or an "or" in a conjunct that holds none of the consequent's own words
#: qualifies another statement of the sentence, not the premise's consequence.
_CONJUNCT_OPENERS: frozenset[str] = frozenset({"and", "so", "thus", "hence"})
#: Words that open a relative clause once the consequent's own words have begun ("it burns with a white flame that can
#: damage the eyes"): what the clause says of an object is no hedge on the consequence.
_RELATIVE_OPENERS: frozenset[str] = frozenset({"that", "which", "who", "whom", "whose", "where"})
#: Prepositions of a complement: an "or" right before one that also follows the consequent's own words in its conjunct
#: ("it loses customers to rivals or to substitutes") joins two complements of one statement, each of which states it.
_PARALLEL_PREPOSITIONS: frozenset[str] = frozenset({"to", "in", "into", "on", "onto", "at", "for", "from", "by", "with", "through", "via",
                                                     "under", "over", "across", "towards", "toward", "among", "between"})
#: An affirming frame: a negation and a word of doubt or denial together endorse what follows ("Nobody doubts that",
#: "There is no doubt that", "Few doubt that", "Economists have shown beyond question that", "It cannot be denied that").
_FRAME_NEGATORS: frozenset[str] = frozenset({"no", "not", "nobody", "none", "never", "few", "little", "hardly", "scarcely", "beyond", "without",
                                             "cannot"})
_DOUBT_WORDS: frozenset[str] = frozenset({"doubt", "doubts", "doubted", "doubtful", "dispute", "disputes", "disputed", "deny", "denies", "denied",
                                          "question", "questions", "questioned", "questionable", "contest", "contests", "contested", "challenge",
                                          "challenges", "challenged", "debate", "debated", "debatable"})
#: Modal words an affirming frame may hold ("Few would doubt that", "Nobody could deny that").
_FRAME_MODALS: frozenset[str] = frozenset({"would", "could", "can", "might", "may", "should", "will"})
#: Quantifiers that make a negated doubt no endorsement ("Not all economists doubt that").
_FRAME_UNIVERSALS: frozenset[str] = frozenset({"all", "every", "each", "everyone", "everybody", "always"})


def _affirming_frame(words: Sequence[str]) -> bool:
    """Whether the words of a frame endorse the rule after it (accuracy round 1, DV2-03): they hold a negation
    (:data:`_FRAME_NEGATORS`, or a word ending in "n't") and a word of doubt or denial (:data:`_DOUBT_WORDS`), an even number
    of the two together, no universal quantifier and no other frame word (a view, a belief, a hedge, "some", "whether":
    "Some economists doubt that", "Nobody has shown that", "Few economists now believe that" and "It is not true that" stay
    frames). Read as words of a closed list; linear."""
    negators = doubts = 0
    for w in words:
        if w in _FRAME_UNIVERSALS:
            return False
        if w in _DOUBT_WORDS:
            doubts += 1
        elif w in _FRAME_NEGATORS or w.endswith("n't"):
            negators += 1
        elif (w in RULE_FRAMES or w in lexis.NEGATION_WORDS) and w not in _FRAME_MODALS:
            return False
    return negators >= 1 and doubts >= 1 and (negators + doubts) % 2 == 0


def _without_affirming_lead(toks: list[_Tok], idx: set[int]) -> set[int]:
    """The consequence's tokens without an affirming frame that opens it ("If interest rates rise, there is no question that
    borrowing falls": the frame endorses "borrowing falls", and its "no" negates nothing of it)."""
    order = sorted(idx)
    for k, i in enumerate(order[:16]):
        if toks[i].word == "that":
            if k + 1 < len(order) and _affirming_frame([toks[j].word for j in order[:k + 1]]):
                return set(order[k + 1:])
            break
    return idx


def _conjunct_pieces(words: Sequence[str], seg: Sequence[int], idxs: Sequence[int], own: set[int]) -> dict[int, int]:
    """``{token index: conjunct number}`` for the consequence's tokens ``idxs`` (in order): a new conjunct starts at a clause
    segment's change, at a word of :data:`_CONJUNCT_OPENERS`, and at a relative word once a word of the consequent's own
    (``own``) has stood before it (:data:`_RELATIVE_OPENERS`)."""
    out: dict[int, int] = {}
    piece, seen_own, prev = 0, False, None
    for i in idxs:
        if prev is not None and (seg[i] != seg[prev] or words[i] in _CONJUNCT_OPENERS or (words[i] in _RELATIVE_OPENERS and seen_own)):
            piece += 1
        out[i] = piece
        seen_own = seen_own or i in own
        prev = i
    return out


def _parallel_complements(words: Sequence[str], own: set[int], piece: dict[int, int]) -> set[int]:
    """The indices of the "or"s that join two complements of one statement: the preposition after the "or" also stands
    between the consequent's last own word before it, in its conjunct, and the "or" ("loses customers to rivals or to
    substitutes"). One pass: per conjunct, the words seen since its last own word."""
    out: set[int] = set()
    since: dict[int, set[str]] = {}
    for i, w in enumerate(words):
        p = piece.get(i)
        if p is None:
            continue
        if i in own:
            since[p] = set()
            continue
        if w == "or" and p in since and i + 1 < len(words) and words[i + 1] in _PARALLEL_PREPOSITIONS and words[i + 1] in since[p]:
            out.add(i)
        if p in since:
            since[p].add(w)
    return out


def rule_qualifier(src: SourceText, span: tuple[int, int], cond: set[int], cons: set[int], cue_at: set[int], conditional: bool,
                   left_words: set[str], right_words: set[str], allowed: set[str], premise_words: Optional[set[str]] = None,
                   premise_text: str = "", consequent_negated: bool = False) -> Optional[str]:
    """What in the sentence of a stated rule keeps it from being the source's own statement (module docstring), or None.
    ``cond``, ``cons`` and ``cue_at`` are the reading's token indices in the excerpt ``span`` (:func:`_readings`);
    ``left_words`` and ``right_words`` the roots the antecedent and the consequent need; ``allowed`` the words the
    consequent's own meanings hold (a hedge the consequent's meaning states is the premise's own). ``premise_words`` (the
    words of both sides' meanings, default ``allowed``) and ``premise_text`` (their tokens, space-joined) say what the
    premise itself states: a verb of a view it holds, or a restriction its meaning writes word for word ("every player except
    the goalkeeper gets a bonus"), is the premise's own. Read from the characters as data, by closed word lists; linear in
    the sentence.

    Accuracy round 1 (DV2-03) narrows what qualifies the rule to the rule itself: a hedge or an "or" counts only in the
    conjunct of the consequence that holds the consequent's own words (:func:`_conjunct_pieces`: "..., the price of copper
    rises and mining firms can hire more staff" states its rule plainly), an "or" between two parallel complements of the
    consequence is none (:func:`_parallel_complements`), an affirming frame ("Nobody doubts that", "There is no doubt that",
    "Few doubt that": :func:`_affirming_frame`) endorses the rule, and with ``consequent_negated`` the consequent's own
    negation ("it cannot photosynthesise" for "does not photosynthesise") is no frame and "can not" no hedge."""
    premise_own = allowed if premise_words is None else premise_words
    written = f" {premise_text} "
    text = src.text
    a, b = span
    sa, sb, sent = _sentence_tokens(src, a, b)
    if not sent:
        return None
    index = {t.start: i for i, t in enumerate(sent)}
    ex = _tokens(text, a, b)

    def mapped(idx: set[int]) -> set[int]:
        return {index[ex[i].start] for i in idx if 0 <= i < len(ex) and ex[i].start in index}

    cond_s, cons_s, cue_s = mapped(cond), mapped(cons), mapped(cue_at)
    if cue_s and cons_s:
        k0 = min(cue_s)
        after_cue = {i for i in cons_s if i > k0}
        if any(lexis.root(sent[i].word) in right_words for i in after_cue):
            cons_s = after_cue  # "If X, Y": what stands before the cue is the rule's lead, not its consequence
    rule = cond_s | cons_s | cue_s
    if not rule:
        return None
    first, last = min(rule), max(rule)
    seg = _segments(text, sent)
    words = [t.word for t in sent]

    # a hedge, another mood or an alternative in the consequence's clause (also where the clause runs on after the excerpt),
    # read in the conjunct that holds the consequent's own words (accuracy round 1, DV2-03)
    cons_segs = {seg[i] for i in cons_s if lexis.root(words[i]) in right_words} or {seg[i] for i in cons_s}
    own_all = {i for i in cons_s if lexis.root(words[i]) in right_words}
    piece = _conjunct_pieces(words, seg, [i for i in range(len(sent)) if seg[i] in cons_segs], own_all)
    owned = {piece[i] for i in own_all if i in piece}
    parallel = _parallel_complements(words, own_all, piece)
    for i, t in enumerate(sent):
        if seg[i] not in cons_segs or i in cond_s or i in cue_s or t.word in allowed:
            continue
        if owned and piece.get(i) not in owned:
            continue  # another conjunct, or a relative clause on an object: it qualifies another statement of the sentence
        if _hedge_word(text, t, i == 0):
            if consequent_negated and t.word in ("can", "could") and i + 1 < len(sent) and words[i + 1] == "not":
                continue  # "can not" states the consequent's own negation as an impossibility
            return f"the consequence is hedged ('{t.word}'): the source states what may or tends to happen, not that it does"
        if t.word in ("or", "either"):
            if t.word == "or" and i in parallel:
                continue  # two complements of one statement ("to rivals or to substitutes"): each states the consequence
            return "the consequence is an alternative ('or'): the source states that one of several things happens"
    # a frame that opens the consequence's clause before its own words ("few economists believe that spending falls if ...")
    for sg in cons_segs:
        own = [i for i in cons_s if seg[i] == sg and lexis.root(words[i]) in right_words]
        if not own:
            continue
        lead_in = [i for i in range(len(sent)) if seg[i] == sg and i < min(own) and i not in cond_s and i not in cue_s]
        lead_words_in = [words[i] for i in lead_in]
        if lead_words_in and lead_words_in[-1] == "that" and _affirming_frame(lead_words_in):
            continue  # an affirming frame ("there is no question that ..."): the source endorses the consequence
        hits = [i for i in lead_in if (words[i] in RULE_FRAMES or words[i] in lexis.NEGATION_WORDS) and words[i] not in allowed]
        if consequent_negated:
            # the consequent's own negation ("it cannot photosynthesise", "it can not ...") is what the premise states
            hits = [i for i in hits if words[i] not in lexis.NEGATION_WORDS and not (words[i] in ("can", "could") and i + 1 < len(sent) and words[i + 1] == "not")]
        if hits:
            return f"the consequence is framed ('{words[hits[0]]}'): the source reports or doubts it rather than stating it"
    # a part of the condition the premise drops ("If taxes rise and wages are frozen, ...")
    if conditional and cond_s:
        parts: list[list[int]] = [[]]
        for i in sorted(cond_s):
            if words[i] in _CONDITION_JOINS:
                parts.append([])
            else:
                parts[-1].append(i)
        for part in parts[1:]:
            roots = meaning_roots(" ".join(words[i] for i in part))
            if roots and not roots & left_words:
                shown = text[sent[part[0]].start:sent[part[-1]].end]
                return f"the condition has a part the premise drops ({shown[:80]!r}): the source states the rule only when it holds too"
    # a frame before the rule: a question, a clause ending in "that" / "whether" / a verb of a view, or a short opening phrase
    sentence_text = text[sa:sb].strip()
    if sentence_text.endswith("?") or (len(words) > 1 and words[0] in _QUESTION_OPENERS and words[1] in _QUESTION_SUBJECTS):
        return "the rule stands in a question: the source asks whether it holds"
    start = 0
    for i in range(first - 1, 0, -1):
        gap = text[sent[i - 1].end:sent[i].start]
        if ";" in gap or ":" in gap or ("," in gap and words[i] in ("and", "but", "so", "yet", "or")):
            start = i
            break
    lead = list(range(start, first))
    lead_words = [words[i] for i in lead if words[i] not in ("and", "but", "so", "yet", "or") or i != start]
    if lead_words:
        shown = text[sent[lead[0]].start:sent[lead[-1]].end]
        if lead_words[-1] in ("that", "whether") or lead_words[-1] in _VIEW_VERBS:
            hit = next((w for w in lead_words if (w in RULE_FRAMES or w in lexis.NEGATION_WORDS) and w not in allowed), None)
            if hit is not None and not (lead_words[-1] == "that" and _affirming_frame(lead_words)):
                return f"the rule is framed ({shown[:80]!r}): the source reports, denies or doubts it rather than stating it"
        elif len(lead_words) <= _MAX_OPENING_PHRASE and "," in text[sent[lead[-1]].end:sent[first].start]:
            hit = next((w for w in lead_words if w in _SCOPE_WORDS and w not in allowed), None)
            if hit is not None:
                return f"the rule is limited by its opening phrase ({shown[:80]!r}): the source states it only for some cases"
    # after the condition: a restriction; after the rule: an attribution tag that names no document
    after = [i for i in range(len(sent)) if i > (max(cond_s) if cond_s else first) and i not in cond_s]
    after_words = [words[i] for i in after]
    for seq in RULE_RESTRICTIONS:
        if f" {' '.join(seq)} " in written:
            continue  # the premise's own meaning writes this restriction: it encodes the rule with it
        n = len(seq)
        for k in range(len(after_words) - n + 1):
            if tuple(after_words[k:k + n]) == seq:
                return f"the rule is restricted ('{' '.join(seq)}'): the source states it only under a further condition"
    tail = [i for i in range(last + 1, len(sent))]
    by_seg: dict[int, list[int]] = {}
    for i in tail:
        by_seg.setdefault(seg[i], []).append(i)
    for idxs in by_seg.values():
        tag = [words[i] for i in idxs]
        views = set(tag) & _VIEW_VERBS
        if tag and tag[0] != "as" and len(tag) <= _MAX_TAG_TOKENS and views and not views <= premise_own and not set(tag) & _DOCUMENT_NOUNS:
            shown = text[sent[idxs[0]].start:sent[idxs[-1]].end]
            return f"the rule is credited to someone's view ({shown[:80]!r}): the source reports it rather than stating it"
    return None


def stated_rule(expr: Any, symbols: dict[str, Any], src: SourceText, span: tuple[int, int]) -> Optional[StatedRule]:
    """Where the located excerpt ``span`` of ``src`` states the rule of the premise ``expr`` (an implication or a
    biconditional of literals: module docstring; a definition; a closed enumeration, :func:`stated_enumeration`), or None."""
    op = getattr(expr, "op", None)
    if op not in ("implies", "iff"):
        return None
    a, b = span
    if b <= a or b - a > _MAX_EXCERPT:
        return None
    enumeration = stated_enumeration(expr, symbols, src, span)
    if enumeration is not None:
        return enumeration
    left, right = _literals(expr.left), _literals(expr.right)
    if left is None or right is None:
        return None
    toks = _tokens(src.text, a, b)
    if len(toks) < 3:
        return None
    excerpt = {lexis.root(t.word) for t in toks}
    found = _stated_rule_pass(op, left, right, symbols, src, (a, b), toks, excerpt, settings=False)
    if found is not None:
        return found  # stated, or stated with a qualifier: read exactly as before accuracy round 2
    # the rule applied to the case the question names (accuracy round 2, V1I-05: "When the river floods, farmland is damaged"
    # for "farmland near the Tamar was damaged in 2021"): its setting phrases are instance words. A setting phrase places one
    # case, so the two sides must place the same one, or one side none, never two others ("in Country Q" beside "in Country
    # P"; a year is the year rule's). This reading only verifies: a rule it reads with a qualifier is left unverified, as before
    def placed(lits: list[Any]) -> set[str]:
        return {r for l in lits for r in _setting_words(_meaning_of(l, symbols), excerpt) if not _is_year(r)} - _SETTING_ROOTS
    left_setting, right_setting = placed(left), placed(right)
    if not (left_setting or right_setting) or (left_setting - right_setting and right_setting - left_setting):
        return None
    found = _stated_rule_pass(op, left, right, symbols, src, (a, b), toks, excerpt, settings=True)
    return found if found is not None and found.qualifier is None else None


def _stated_rule_pass(op: str, left: list[Any], right: list[Any], symbols: dict[str, Any], src: SourceText, span: tuple[int, int], toks: list[_Tok],
                      excerpt: set[str], settings: bool) -> Optional[StatedRule]:
    """One reading of :func:`stated_rule` over the excerpt's rule shapes: the rule stated with no qualifier, else the first
    qualified one, else None; with ``settings`` the sides' setting phrases are instance words (:func:`_instance_words`)."""
    a, b = span
    words = [t.word for t in toks]
    allowed_left = {w for l in left for w in lexis.tokens(_meaning_of(l, symbols))}
    allowed_right = {w for l in right for w in lexis.tokens(_meaning_of(l, symbols))}
    premise_text = " | ".join(" ".join(lexis.tokens(_meaning_of(l, symbols))) for l in (*left, *right))
    qualified: Optional[StatedRule] = None
    left_negated = any((getattr(l, "op", None) == "not") != lexis.negated(_meaning_of(l, symbols)) for l in left)
    right_negated = any((getattr(l, "op", None) == "not") != lexis.negated(_meaning_of(l, symbols)) for l in right)
    for cue, cond, cons in _readings(src.text, toks, op == "iff"):
        universal = "..." in cue or "(a definition)" in cue or "(what every such thing is)" in cue
        left_words = set().union(*(_words_of(l, symbols, excerpt, universal, settings) for l in left))
        right_words = set().union(*(_words_of(l, symbols, excerpt, universal, settings) for l in right))
        conditional = cue in CONDITION_CUES or cue == WHEN_CUE
        cue_at = {k for k, w in enumerate(words) if w == cue} if conditional else set()
        # an affirming frame that opens a side ("there is no question that borrowing falls") endorses it and negates
        # nothing of it (accuracy round 1, DV2-03)
        cond_eff, cons_eff = _without_affirming_lead(toks, cond), _without_affirming_lead(toks, cons)

        def holds(lits: list[Any], idx: set[int], other: set[str]) -> bool:
            return all(_states_literal(l, symbols, src, toks, idx, other, universal, settings) for l in lits)

        sides = []
        if holds(left, cond_eff, right_words) and holds(right, cons_eff, left_words):
            sides.append((cond_eff, cons_eff, left_words, right_words, allowed_right, right_negated))
        if op == "iff" and holds(left, cons_eff, right_words) and holds(right, cond_eff, left_words):
            sides.append((cons_eff, cond_eff, right_words, left_words, allowed_left, left_negated))
        for c_idx, k_idx, c_words, k_words, allowed, k_negated in sides:
            # the cue the reading opened, nearest before its condition
            cue_tok = {max((k for k in cue_at if k < min(c_idx)), default=-1)} - {-1} if c_idx else set()
            qualifier = rule_qualifier(src, (a, b), c_idx, k_idx, cue_tok, conditional, c_words, k_words, allowed, allowed_left | allowed_right,
                                       premise_text, consequent_negated=k_negated)
            if qualifier is None:
                return StatedRule(source=src, start=a, end=b, cue=cue)
            if qualified is None:
                qualified = StatedRule(source=src, start=a, end=b, cue=cue, qualifier=qualifier)
    return qualified


# ------------------------------------------------------------------------------------------------ stated disjunctions

#: Token sequences that state that the options of a disjunction exclude each other ("exactly one of two groups", "only one
#: of", "one and only one", "but not both").
EXCLUSIVE_CUES: tuple[tuple[str, ...], ...] = (("exactly", "one"), ("only", "one"), ("one", "and", "only", "one"), ("not", "both"))
#: Words that negate a whole list of options ("neither ... nor", "none of"): such a sentence states no disjunction.
_LIST_NEGATORS: frozenset[str] = frozenset({"neither", "none", "nor"})
#: Words that make a sentence a universal statement, so the case a premise names (a numbered participant, a lettered firm)
#: is an instance of it.
_UNIVERSAL_WORDS: frozenset[str] = frozenset({"every", "all", "each", "any", "everyone", "everybody"})


def _option_literal(node: Any) -> bool:
    op = getattr(node, "op", None)
    if op == "var" or (op == "not" and getattr(node.arg, "op", None) == "var"):
        return True
    return _literals(node) is not None and op in ("eq", "lt", "le", "gt", "ge")


def disjunction_shape(expr: Any) -> Optional[tuple[list[Any], bool]]:
    """``(options, exclusive)`` when ``expr`` is a disjunction of literals (``or`` of two or more atoms, negated atoms or
    comparisons of a symbol with a literal), or an exclusive one: ``and(or(a, b, ...), not(and(a, b)))`` or ``iff(a,
    not(b))``; None otherwise."""
    op = getattr(expr, "op", None)
    if op == "or":
        opts = list(expr.args)
        return (opts, False) if len(opts) >= 2 and all(_option_literal(o) for o in opts) else None
    if op == "and" and len(expr.args) == 2:
        for k in (0, 1):
            dis, other = expr.args[k], expr.args[1 - k]
            shape = disjunction_shape(dis) if getattr(dis, "op", None) == "or" else None
            if shape is None or getattr(other, "op", None) != "not" or getattr(other.arg, "op", None) != "and":
                continue
            from ..ir.canonical import canonical_json
            opts = shape[0]

            def key(x: Any) -> str:
                return canonical_json(x.model_dump(mode="json"))

            if sorted(key(x) for x in other.arg.args) == sorted(key(x) for x in opts):
                return opts, True
        return None
    if op == "iff":
        left, right = expr.left, expr.right
        for a, b in ((left, right), (right, left)):
            if getattr(b, "op", None) == "not" and getattr(b.arg, "op", None) == "var" and getattr(a, "op", None) == "var":
                return [a, b.arg], True
        return None
    return None


def _instance_words_of(meaning: str, sentence: set[str], universal: bool) -> set[str]:
    """The words of an option's meaning that name the case a universal sentence speaks of in general: a year the sentence
    does not state, and in a universal sentence a capitalised word, a single letter or a numeral it does not hold
    ("participant 12" under "every participant")."""
    out: set[str] = set()
    sentence_years = any(_is_year(r) for r in sentence)
    for s, e, t in lexis.token_spans(meaning):
        raw = meaning[s:e]
        r = lexis.root(t)
        if r in sentence:
            continue
        if _is_year(t):
            if not sentence_years:
                out.add(r)
        elif universal and ((raw[:1].isupper() and s > 0) or len(t) == 1 or t.isdecimal()):
            out.add(r)
    return out


def stated_disjunction(expr: Any, symbols: dict[str, Any], src: SourceText, span: tuple[int, int]) -> tuple[Optional[StatedRule], bool]:
    """Whether the sentence ``span`` of ``src`` states the disjunction ``expr`` (:func:`disjunction_shape`): ``(rule,
    near)``.

    The sentence states it when it holds "or" (no "neither", "nor" or "none" negating the list), each option's distinct
    words (the roots of its symbol's meaning that tell it from the other options: all of them, or all but one of four or
    more) stand in its own segment of the list (the segments are cut at "or" and at commas), the options' shared words are
    held by the sentence (the case a universal sentence speaks of in general set aside: "participant 12" under "every
    participant"), each option's segment is negated exactly when the option is, nothing before the first option negates the
    list, and, for an exclusive disjunction, the sentence says the options exclude each other (:data:`EXCLUSIVE_CUES`).
    ``near`` is True when the sentence holds "or" between every option's distinct words but its shared words differ (a
    paraphrase of what the options are about), or an exclusive premise meets "either ... or" with no word of exclusion: the
    connective may be the record's own, so the premise is unvalidated, not refuted. A list the sentence negates, or an
    option of the other polarity, is no statement of the premise (``near`` False). Read from the sentence's characters as data; nothing is evaluated."""
    shape = disjunction_shape(expr)
    if shape is None:
        return None, False
    options, exclusive = shape
    a, b = span
    if b <= a or b - a > _MAX_EXCERPT:
        return None, False
    toks = _tokens(src.text, a, b)
    words = [t.word for t in toks]
    if "or" not in words or any(w in _LIST_NEGATORS for w in words):
        return None, False
    roots = {lexis.root(w) for w in words}
    universal = any(w in _UNIVERSAL_WORDS for w in words)
    # the list's segments: cut at "or" and at a comma, semicolon or colon between tokens
    seg_of: list[int] = []
    seg = 0
    for i, t in enumerate(toks):
        if t.word == "or":
            seg += 1
            seg_of.append(-1)
            continue
        if i > 0 and any(ch in _BREAK_CHARS for ch in src.text[toks[i - 1].end:t.start]):
            seg += 1
        seg_of.append(seg)
    meanings = [_meaning_of(o, symbols) for o in options]
    wanted = [meaning_roots(m) - _instance_words_of(m, roots, universal) for m in meanings]
    distinct = [w - set().union(*(x for j, x in enumerate(wanted) if j != k)) for k, w in enumerate(wanted)]
    if any(not d for d in distinct):
        return None, False
    placed: list[int] = []
    for d in distinct:
        hits = [i for i, t in enumerate(toks) if seg_of[i] >= 0 and lexis.root(t.word) in d]
        if not hits or not _enough(len({lexis.root(toks[i].word) for i in hits}), len(d)):
            return None, False
        placed.append(seg_of[hits[0]])
    if len(set(placed)) != len(placed):
        return None, False
    first, last = min(placed), max(placed)
    or_between = any(t.word == "or" and toks_index_between(toks, i, placed, seg_of) for i, t in enumerate(toks))
    if not or_between:
        return None, False
    exclusive_cue = next((cue for cue in EXCLUSIVE_CUES for k in range(len(words)) if tuple(words[k:k + len(cue)]) == cue), None)
    cue_tokens = {k + j for cue in EXCLUSIVE_CUES for k in range(len(words)) if tuple(words[k:k + len(cue)]) == cue for j in range(len(cue))}
    head = [words[i] for i in range(len(toks)) if 0 <= seg_of[i] < first and i not in cue_tokens]
    if lexis.negation_words(head) > 0:
        # the record negates the list ("No volunteer was in ... or ..."): it does not state the premise. Only a negation word
        # negates the list: a modifier with a negating prefix before it ("In an independent-groups experiment, every
        # participant was allocated to ... or ...") names a kind of thing (repair round 5, DA-2)
        return None, False
    for opt, sg in zip(options, placed):
        seg_words = [words[i] for i in range(len(toks)) if seg_of[i] == sg and i not in cue_tokens]
        negated = (getattr(opt, "op", None) == "not") != lexis.negated(_meaning_of(opt, symbols))
        if negated != (lexis.negation_markers(seg_words) > 0):
            return None, False  # an option of the other polarity: the record states another disjunction
    # from here the sentence holds "or" between every option's own words with their polarity: a failed test leaves the
    # premise unvalidated
    shared = set().union(*wanted) - set().union(*distinct)
    if shared and not _enough(len(shared & roots), len(shared)):
        return None, True
    if exclusive and exclusive_cue is None:
        # "either A or B" is often meant exclusively but does not say so: the exclusion is unvalidated, not refuted
        return None, "either" in words
    cue = "or" + (f" ({' '.join(exclusive_cue)})" if exclusive and exclusive_cue else "")
    return StatedRule(source=src, start=a, end=b, cue=cue), False


def toks_index_between(toks: list[_Tok], i: int, placed: list[int], seg_of: list[int]) -> bool:
    """Whether the "or" token ``i`` stands between the segments of the first and the last option."""
    before = max((seg_of[j] for j in range(i) if seg_of[j] >= 0), default=-1)
    after = min((seg_of[j] for j in range(i + 1, len(toks)) if seg_of[j] >= 0), default=-1)
    return before >= min(placed) and 0 <= after <= max(placed)
