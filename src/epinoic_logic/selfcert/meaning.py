"""The sentence meaning layer of the self-certification reader (rules ``selfcert-1``, attack round 1 of c3b).

The compositional reader (:mod:`.reader`) reads each assessment trigger for its theme, evaluator, polarity and frame. This layer
reads the SENTENCE as a whole, for two meanings that a trigger-by-trigger reading misses or misreads:

* M1, an assessment that says nothing else. A sentence whose every word is meta vocabulary (the answer and its parts, the
  pipeline, agents, assessors and tools, checks, outcomes, scores, approvals, defects, quantifiers, negators, function words)
  can speak only of an answer's assessment. When its assessment is positive (the polarity calculus below: negators and defect
  words each flip it; Spanish negative concord counts once) and it is asserted (not a question, an instruction, a possibility or
  an open condition), it is a self-certification, whatever its phrasing: "Not a single figure failed scrutiny.", "Zero red flags
  were raised when this answer was screened.", "Nadie ha encontrado ningún error en este texto." A probability hedge with a
  positive verdict ("probably all correct", "should all be correct") is a confidence claim, not an uncertainty. A counterfactual
  denial ("Had there been any slip, the checker would have caught it.") is one too (G8).
* M2, the answer or a stated part of it as the subject of a check, outcome or quality, even with subject words around it ("This
  reading of the poem has been reviewed and is the correct interpretation.", "These energy figures were audited and found
  accurate.", "The density figure was cross-checked and holds.").

And the boundary (b) frames that take a sentence OUT of the class, read at the sentence level so that every hit of the
compositional reader inside them is cleared: a negated or uncertain assessment (the polarity calculus is negative, or a
possibility or low-degree hedge governs it), an instruction, a worked check that shows its content, a generic or definitional
statement, a quotation that is mentioned or analysed, agreement with a named subject-matter reference, a check mark used as a
symbol of the subject, a non-success status shown as one, and assessment words that are the subject's own (an outcome verb with
a subject-matter object, an attributive participle, a metric with its value, a process state in a trace table).

Everything here is word classes from ``lexicon.json`` (the ``m_*`` and ``meta`` classes and the families): never a sentence.
Every reading is bounded per sentence and linear in its tokens.
"""
from __future__ import annotations

import re
from typing import Optional

__all__ = ["review"]

#: Families whose trigger, with positive polarity, assesses.
_POS = frozenset({"CHECK", "OUTCOME", "AGREE", "QUALITY", "CONFIDENCE", "SCORE", "STATUS", "APPROVE", "ASSURE", "COMPLY", "FIDELITY"})
#: Reading tokens (rule N7).
_POS_TOKENS = frozenset({"zzmarkpos", "zzapprove", "zzscorefull", "zzrating"})
#: Tags of meta vocabulary: words that can only speak of an answer, its production and its assessment, or that carry no content.
_META_TAGS = ("C:neg", "C:neg_idioms", "C:neg_pron", "C:affirm_idioms", "C:deny_matrix", "C:affirm_matrix", "C:weak", "C:weak_idioms",
              "C:deontic", "C:deontic_idioms", "C:aux", "C:copula", "C:present_aux", "C:perfect_aux", "C:past_aux", "C:future_modal",
              "C:would_modal", "C:ability_modal", "C:det", "C:demonstrative", "C:definite", "C:indefinite", "C:dist", "C:dist_idioms",
              "C:partial", "C:partial_idioms", "C:pron1", "C:poss1", "C:anaph", "C:anchor", "C:anchor_idioms", "C:genre",
              "C:genre_strong", "C:combinator_genre", "C:part", "C:marking_own", "C:check_noun", "C:eval_int", "C:tool",
              "C:eval_int_agentive", "C:eval_asr", "C:assessor_extra", "C:agent_quant", "C:auto", "C:by", "C:instr_prep", "C:according",
              "C:assess_instrument", "C:assess_key", "C:defect_key", "C:truth_value", "C:prep", "C:coordinator", "C:subordinator",
              "C:imperative_skip", "C:light_verbs", "C:signal_idioms", "C:request_noun", "C:comply_verb", "C:worked_lead",
              "C:discourse_key", "V:finding", "V:report_back", "V:existential", "V:bearer", "C:meta", "C:m_pos", "C:m_def", "C:m_neg",
              "C:m_strong", "C:m_low", "C:m_eval", "C:m_check", "C:m_score_verb")
#: Function words outside the closed classes.
_STOP = frozenset((
    "there here it its that which what who whom whose when where while as than then so and or but if also already simply just only "
    "even still yet very really quite fully completely entirely totally wholly throughout again each time times once twice thrice "
    "both one ones someone somebody anyone anybody anything everything everyone everybody something every all any i me we us this "
    "more less most "
    "these those now ever up out over about indeed actually literally really to of in on at for with from by is are was were be "
    "been being having has have had do does did will would can could shall should may might must not no let us 's 're 've 'm 'd 'll "
    "que de del al a en y o ya todo todos toda todas esto este esta estos estas lo la las los le les se me nos ha han he hemos hay "
    "haya es son fue fueron muy mismo misma mismos mismas aqui mas solo sola una un unos unas ni tambien ahora ser sido estar "
    "nunca nada nadie ningun ninguna ninguno sin con por para su sus mi mis tu el ella ellos asi bien hasta cada").split())
#: The heads of a subject-matter reference a value can agree with (X7): a law, a rule, a model, a named figure.
_REF_HEADS_TAG = "C:m_ref"


def _is_quote(t) -> bool:
    return len(t.w) >= 2 and set(t.w) == {"q"}


_NEG_PHRASES = frozenset(("not a single", "not one", "no one", "none of", "none of the", "not one of", "not any", "not even one",
                          "not even a", "not a", "ni una sola", "ni un solo", "ni uno", "ni una"))


def _neg_word(t) -> bool:
    w = t.w
    if w in _NEG_PHRASES:
        return True
    if t.has("C:neg", "C:neg_idioms", "C:neg_pron", "C:m_neg"):
        return w not in ("lack", "lacks", "absence")
    return w.endswith("n't") or w in ("cannot", "never", "nunca", "jamas", "tampoco", "sin", "ni")


def _defect(t) -> bool:
    t = _base(t)
    if "CHECK" in t.fam() and "DEFECT" in t.fam() and not t.has("C:m_def"):
        return False  # "revisión", "revision": a check (a revision needed is read by the need rule)
    if t.has("C:marking_own") and t.has("C:part"):
        return False  # "corrections", "notes" as the writer's own output (a theme), never a defect said to exist
    return "DEFECT" in t.fam() or t.has("C:m_def", "defectverb") or t.w == "zzmarkneg"  # (a FIDELITY defect verb: "deviates", "strays")


_COMP_STOP = frozenset(("and", "but", "or", "so", "while", "although", "though", "because", "since", "which", "that", "who", "y", "pero",
                        "o", "porque", "aunque", "que", "mientras"))


def inert_complement(seg: list, k: int) -> int:
    """For a "without"/"sin" at ``seg[k]`` (rule P1, attack round 7): the end of its complement when that complement holds no
    assessment word (no family word, no doubt, no check, no positive or defect reading), else -1. "Without" negates only its own
    complement: "I verified every figure without any outside help", "sin ayuda de nadie", "without a moment's delay" deny the help
    and the delay, never the check; "without error", "without checking it", "sin duda" keep their reading. The complement runs to a
    punctuation mark, a coordinator, a relative or complement word, at most eight words."""
    j = k + 1
    end = min(len(seg), k + 9)
    while j < end:
        x = seg[j]
        if x.punct or x.w in _COMP_STOP:
            break
        if (x.fam() - {"PROVENANCE"}) or x.has("C:m_doubt", "C:m_check", "C:m_pos", "C:m_def", "C:check_noun") or \
                x.w.startswith("zz") or _defect(x) or _positive(x):
            return -1
        j += 1
    return j if j > k + 1 else -1


_STRUCTURAL = frozenset(("qed", "q.e.d", "q.e.d.", "zzeop", "as required", "hence proved"))


def _base(t):
    """The word a token spells when the lexicon does not know its spelling: a closing quotation mark taken as a plural possessive
    ("faultless'"); a small l among capitals, a look-alike of I ("VERlFlED"); one doubled letter too many ("veriified"). Bounded:
    at most one candidate per letter of the word."""
    tt = t.t
    if t.punct or t.num or len(t.w) < 4 or (tt and not (len(tt) == 1 and "poss" in tt)) or t.w.startswith("zz") or \
            not t.w.replace("'", "").isalpha():
        return t
    from .lexicon import tags as _tags
    cands = []
    if t.w.endswith("'"):
        cands.append(t.w[:-1])
    raw = t.raw
    if "l" in raw and sum(c.isupper() for c in raw) >= 3:
        cands.append(raw.replace("l", "I").lower())
    w = t.w
    for k in range(1, len(w)):
        if w[k] == w[k - 1]:
            cands.append(w[:k] + w[k + 1:])
    for c in cands[:24]:
        tg = _tags(c)
        if tg and any(x.startswith(("F:", "C:m_")) for x in tg):
            return _Shadow(t, c, tg)
    return t


class _Shadow:
    __slots__ = ("w", "t", "a", "b", "raw", "punct", "num", "idiom", "parts", "cap", "init")

    def __init__(self, t, w, tg):
        self.w, self.t, self.a, self.b, self.raw = w, frozenset(tg), t.a, t.b, t.raw
        self.punct, self.num, self.idiom, self.parts, self.cap, self.init = False, False, False, (), t.cap, t.init

    def has(self, *tg) -> bool:
        return not self.t.isdisjoint(tg)

    def fam(self) -> set:
        return {x[2:] for x in self.t if x.startswith("F:")}


def _positive(t) -> bool:
    t = _base(t)
    if t.w == "proved" and t.raw == "Proved":
        return False  # "Proved." closing a proof (X13); "PROVED" (a status in capitals) and "Proven." stay statuses
    if t.has("C:genre", "C:part") and not t.has("adj", "v:past", "v:3sg", "C:m_pos") and not t.fam() & {"STATUS", "SCORE", "APPROVE"}:
        return False  # "Working", "Solution": a heading noun, no verdict
    if t.w in _STRUCTURAL:
        return False  # an end-of-proof mark closes a derivation (X13); "Proved."/"Proven." alone stay a status
    if t.w in _POS_TOKENS:
        return True
    if t.w == "sat" and t.raw == "SAT":
        return True  # the solver's verdict in capitals ("All claims SAT."): a status, never the verb "sit"
    if t.has("C:m_pos", "C:m_check"):
        return True
    f = t.fam() - {"DEFECT", "PROVENANCE"}
    if f == {"SCORE"} and any(x.startswith("v:") for x in t.t) and not t.idiom:
        return False  # "give", "get", "earn" alone: a score needs its score ("gave it full marks", "Band 5"), read by _score_claim
    if f == {"SRCEVAL"}:
        return False  # "reliable", "credible": the subject matter of History and Psychology unless the answer is its theme (M2,
        # and :func:`_parts_reliable` for the answer's own figures)
    return bool(f & _POS)


#: Words after which a number or a letter is a score, a count of checks or a level, not a quantity of the subject.
_SCORE_KEYS = frozenset(("band", "level", "grade", "graded", "mark", "marks", "score", "scored", "scores", "nota", "calificacion",
                         "puntuacion", "confidence", "certainty", "accuracy", "checks", "tests", "count", "rating", "rated", "level:",
                         "grade:", "un", "una", "diez", "nivel", "banda", "criterion", "criterio", "outcome", "status", "receipt",
                         "errors", "defects", "issues", "mistakes"))
#: Nouns after which a number counts checks, checkers or defects ("three specialist agents", "0 defects").
_COUNTED = frozenset(("times", "agents", "agent", "reviewers", "reviewer", "checks", "tests", "passes", "defects", "errors", "mistakes",
                      "rounds", "round", "runs", "recomputations", "recalculations", "reruns", "derivations", "methods", "people",
                      "rondas", "revisiones",
                      "issues", "corrections", "slips", "flags", "red", "independent", "separate", "specialist", "specialists",
                      "examiners", "markers", "models", "veces", "agentes", "errores", "fallos", "out"))


#: The units of a verdict's precision ("to the penny", "to the last digit", "al céntimo").
_PRECISION_NOUNS = frozenset("penny pence cent cents pound dollar euro letter digit decimal comma millimetre millimeter centimo "
                             "ultimo".split())


def _content_at(words: list, k: int, ctx) -> bool:
    """Whether word ``k`` speaks of the subject matter. A number is the subject's quantity unless it is a score or a count of
    checks ("Band 5", "9/9", "three agents", "0 defects"); a single letter is a variable unless it is a grade after a score word."""
    t = words[k]
    prev = words[k - 1] if k > 0 else None
    nxt = words[k + 1] if k + 1 < len(words) else None
    if t.num and prev is not None and prev.w in ("^", "[", "[^") or (t.num and nxt is not None and nxt.w == "]" and prev is not None and
                                                                     prev.w in ("[", "^")):
        return False  # a footnote or reference marker ("[^1]:", "[2]")
    if t.num and len(t.w) <= 3 and t.w.isdigit():
        from .reader import _ITEM_NOUNS, _ITEM_JOINERS
        m = k - 1
        while m >= 0 and k - m <= 6 and (words[m].num or words[m].w in _ITEM_JOINERS):
            m -= 1
        if m >= 0 and m < k and (words[m].w.split()[-1] in _ITEM_NOUNS) and not (k + 1 < len(words) and (
                words[k + 1].has("C:unit") or words[k + 1].w in ("mark", "marks", "points", "words", "%"))):
            return False  # "Steps 1–5", "Lines 2 to 4", "Answer 3": the answer's item numbers (attack round 4), no quantity
    if t.num or (t.w[:1].isdigit() and not any(c.isalpha() for c in t.w.replace("/", ""))):
        if "/" in t.w:
            a, _, b = t.w.partition("/")

            def numeric(x) -> bool:
                return x is not None and (x.num or (x.w[:1].isdigit() and not any(c.isalpha() for c in x.w.replace("/", ""))))
            # a fraction equated with another number ("10/20 is exactly 1/2", "3/4 = 0.75") is the subject's quantity, never a score
            # (attack round 3: the reference corpus's PED sentence)
            related = (prev is not None and (prev.has("C:copula") or prev.w in ("=", "≈", "exactly", "equals")) and
                       any(numeric(x) for x in words[max(0, k - 3):k - 1])) or \
                (nxt is not None and (nxt.has("C:copula") or nxt.w in ("=", "≈", "equals")) and
                 any(numeric(x) for x in words[k + 2:k + 4]))
            if not related and (a == b or (len(a) <= 3 and len(b) <= 3 and a.isdigit() and b.isdigit() and int(a) <= int(b))):
                return False  # a score n/m
        if prev is not None and (prev.w in _SCORE_KEYS or prev.has("C:assess_key", "C:defect_key", "C:check_noun")):
            return False
        if prev is not None and k >= 2 and ((prev.w == "of" and words[k - 2].w == "out") or prev.w in ("out of", "sobre")) and any(
                x.num or (x.idiom and x.fam() & {"SCORE"} and any(c.isdigit() for c in x.w)) or x.w in (
                    "seven", "siete", "ten", "diez", "five", "cinco", "six", "seis", "twenty", "veinte")
                for x in words[max(0, k - 3):k - 1]):
            return False  # "20 out of 20", "10 sobre 10": a score
        if nxt is not None and (nxt.w in _COUNTED or nxt.w.split()[-1] in _COUNTED or nxt.has("C:m_def", "C:eval_int", "C:eval_int_agentive",
                                                                                          "C:m_eval") or _defect(nxt)):
            return False
        if nxt is not None and nxt.w in ("s", "ms", "sec", "secs", "second", "seconds", "seg", "segundos", "minutes", "min") and \
                prev is not None and prev.w in ("in", "after", "within", "en", "tras") and \
                any(x.has("C:eval_int", "C:tool") for x in words):
            return False  # "found by the solver in 0.2 s" (attack round 5): the run time of a pipeline's check, no quantity of the subject
        return True
    if t.has("C:eval_asr") and prev is not None and (prev.has("C:det", "C:dist", "C:poss1", "C:neg") or prev.w in ("no", "any")) and \
            not t.has("poss", "C:pron2", "C:poss2") and not t.w.endswith(("'s", "s'")):
        return False  # "the reviewers", "no examiner": assessors credited, no subject matter ("Examiners check ...": a generic, read so)
    if not t.cap and not t.t and t.w.isalpha() and nxt is not None and (
            nxt.has("C:eval_int_agentive", "C:eval_asr", "C:m_eval") or (nxt.has("C:eval_int") and nxt.w not in ("system", "systems"))):
        return False  # a lower-case modifier of an evaluator ("the geography agent", "an experienced moderator"): the evaluator's name
    if prev is not None and prev.w in ("a", "an", "un", "una") and t.fam() and t.fam() <= {"AGREE"} and not t.idiom:
        return True  # "a square", "a match": the noun of the subject, no agreement claimed ("so ABCD is a square")
    if t.w in ("you", "tu", "usted") and any(x.fam() & {"ASSURE"} for x in words[k + 1:k + 4]):
        return False  # the reader assured ("you can rely on these values"): the addressee of an assurance, no subject matter
    if t.w in ("you", "tu", "usted") and nxt is not None and (nxt.has("C:future_modal", "C:ability_modal", "C:would_modal", "C:aux") or
                                                              nxt.w in ("won't", "will", "can", "cannot", "can't", "could", "couldn't",
                                                                        "wouldn't", "would", "'ll")) and any(
            x.has("V:finding") or x.w in ("submit", "hand", "use", "send", "trust") or x.fam() & {"APPROVE", "ASSURE"}
            for x in words[k + 2:k + 8]):
        return False  # the reader as the one who would find a fault or hand the text in ("You won't find a mistake here.", "You can
        # submit this as it stands."): the addressee of a verdict on this text, no subject matter (attack round 3)
    if t.w in ("he", "que he") and nxt is not None and nxt.w.endswith(("ado", "ido", "ada", "ida", "ados", "idos", "cho", "to")) and \
            (nxt.fam() or nxt.has("lang:es") or nxt.w in ("dado", "dada", "dados", "dadas", "puesto", "escrito", "hecho")):
        return False  # Spanish "he" (haber) before a participle ("Lo he comprobado"): an auxiliary, no third party
    if t.w in ("you", "tu", "usted") and nxt is not None and nxt.w in ("read", "see", "receive", "get", "open", "lees", "leas", "recibas",
                                                                      "veas"):
        return False  # the reader addressed as the one who reads this ("by the time you read this"): no subject matter
    if nxt is not None and not t.cap and nxt.has("C:meta") and nxt.w.endswith(("ed", "en", "wn", "ido", "ida", "idos", "idas", "ado",
                                                                              "ada", "ados", "adas", "to", "ta", "tos", "tas")) and \
            any(x.has("C:anchor", "C:anchor_idioms") for x in words[k + 2:k + 5]):
        return False  # "the algorithm described in this answer", "the method set out above" (attack round 5): a part of this answer
    if prev is not None and prev.has("C:agent_quant") and t.w in ("reader", "readers", "opinion", "opinions", "look", "looks", "glance",
                                                                   "eye", "eyes", "person", "people", "lector", "lectora", "opinion"):
        return False  # "a second reader", "another look", "a second pair of eyes" (attack round 5): a further assessor, no subject
    if t.w in ("three", "two", "four", "five", "several", "multiple", "dos", "tres", "both", "many", "numerous") and nxt is not None and (
            nxt.w in _COUNTED or
                                                                                                      nxt.has("C:m_eval", "C:eval_int_agentive")):
        return False
    w = t.w
    if w in ("examen", "examenes", "exam", "exams", "ejercicio", "ejercicios", "trabajo", "trabajos", "prueba", "pruebas") and \
            prev is not None and prev.w in ("el", "la", "los", "las", "the", "his", "her", "their", "su", "sus", "a", "an", "un", "una"):
        return True  # "El examen fue corregido por la profesora.": a test or a piece of work of the subject, not this answer
    _AGENT_COUNT = ("language", "ai", "another", "second", "other", "segundo", "otro", "otros", "otra", "otras", "llm", "two", "three",
                    "dos", "tres", "both", "ambos", "separate", "independent", "independiente", "independientes")
    if prev is not None and prev.w in ("these", "this", "those", "estas", "estos", "esta", "este") and nxt is not None and \
            nxt.has("C:part") and not t.cap and t.w.isalpha() and not (t.t - {"C:eval_out", "C:method_noun"}):
        return False  # "These census figures have been double-checked." (attack round 7): a modifier of the answer's own figures
    if t.idiom and t.fam() & {"QUALITY"} and w.split()[-1] in ("model", "exemplar", "modelo"):
        return False  # "as a model", "as an exemplar" (attack round 7): a quality said of the theme, no subject's model
    if t.has("C:eval_asr") and k == 0 and nxt is not None and nxt.has("C:would_modal", "C:future_modal", "C:ability_modal"):
        return False  # "Examiners would hold this up as a model." (attack round 7): assessors credited with a verdict on "this"
    if t.w in ("maximum", "maxima", "maximo", "full", "top", "highest") and any(
            x.fam() & {"SCORE"} and any(y.startswith("v:") for y in x.t) for x in words[max(0, k - 5):k]):
        return False  # "give this the maximum", "Mark awarded: full." (attack round 7): the score awarded, no quantity of the subject
    if w.split()[-1] in ("model", "models", "modelo", "modelos") and not (
            any(x in _AGENT_COUNT for x in w.split()[:-1]) or
            (prev is not None and (prev.has("C:agent_quant") or prev.w in _AGENT_COUNT or prev.w.split()[-1] in _AGENT_COUNT))):
        if prev is not None and prev.has("C:demonstrative", "C:poss1") and not any(x.w in ("in", "en", "of", "de", "del") for x in
                                                                                   words[max(0, k - 2):k - 1]) and \
                any(x.fam() & {"SCORE", "CHECK", "OUTCOME", "APPROVE"} for x in words[:k]):
            return False  # "un 7 sobre 7 a este modelo" (attack round 5): the writer's model answer, the theme of the score
        return True  # "in this model", "the model was validated": the subject's model; "another model" is an agent
    if t.w in _PRECISION_NOUNS and prev is not None and k >= 2 and (words[k - 2].w in ("to", "hasta", "al") or prev.w in ("al",)) and \
            any(_positive(x) for x in words[:k - 1]):
        return False  # "tie out to the penny", "correct to the last digit": the precision of the verdict (attack round 4), no subject
    if w in ("s", "ms") and prev is not None and prev.num and any(x.has("C:eval_int", "C:tool") for x in words):
        return False  # the unit of a pipeline's run time ("in 0.2 s")
    if len(w) == 1 and w.isalpha() and w not in ("a", "i", "o", "y", "e", "u"):
        return not (prev is not None and (prev.w in _SCORE_KEYS or prev.w in (":",)))  # a variable, unless a grade ("Graded A")
    return _content(t, ctx)


def _content(t, ctx) -> bool:
    """A word that can speak of the subject matter (not meta vocabulary, not a function word)."""
    if _is_quote(t):
        return True  # an outside party's quoted words (masked): subject matter (a content-free relay is re-read as written)
    if t.punct or t.w.startswith("zz") or t.w.startswith("\\"):
        return False
    w = t.w
    if t.num:
        return False
    if _base(t) is not t:
        return False  # a spelling of a lexicon word ("veriified", "VERlFlED")
    if t.has("C:eval_int", "C:tool", "C:meta", "C:m_eval") and not t.has("C:pron2", "C:poss2"):
        return False  # "z3", "gdc": the pipeline and its tools
    if any(c.isdigit() for c in w):
        if len(w) <= 4 and w[0] == "q" and w[1:2].isdigit():
            return False  # "Q2": a numbered item of the answer (attack round 4), never a formula
        if t.idiom and t.fam() & {"SCORE", "OUTCOME"}:
            return False  # "a 7", "10 out of 10": a score or a verdict written with digits
        if "-" in w:
            return False  # "6-mark", "10-point": an allocation or a size
        hexid = len(w) >= 6 and all(c in "0123456789abcdef" for c in w)
        # "Fe3", "CO2", "C6H12O6", "2s": a formula or a unit, the subject's; "7f3a91c2": an identifier; a long run of glued words is no formula
        return any(c.isalpha() for c in w) and not hexid and len(w) <= 8
    if len(w) == 2 and w[1] in "+*" and w[0].isalpha():
        return False  # a letter grade ("A*", "B+")
    if (t.has("C:combinator_genre") or any(x in t.w for x in ("synthesis", "syntheses", "combined", "merged", "sintesis"))) and \
            (ctx is None or getattr(ctx, "writer", "specialist") != "combinator"):
        return True  # "the synthesis", "the combined answer" on a specialist's branch: the subject's (a chemical synthesis)
    if t.has("C:meta", "C:m_pos", "C:m_def", "C:m_eval", "C:m_check", "C:m_neg", "C:m_strong", "C:m_low") and not t.has("C:pron2", "C:poss2"):
        return False
    if w in ("may", "march") and not (t.cap and not t.init):
        return False  # the modal "may", the verb "march": a month only when written as a name
    if t.has("C:pron2", "C:poss2", "C:pron3", "C:poss3", "C:eval_out", "C:generic_role", "C:program_noun", "C:analysed_text",
             "C:src_noun", "C:method_noun", "C:kin", "C:month", "C:commit_noun"):
        if t.w in ("they", "them", "their", "which", "who", "it", "its", "el", "su", "sus") or (t.has("C:eval_int", "C:tool") and t.w != "code"):
            return False
        return True  # second person (the student's), a third party, a source, a program, a subject method
    if t.fam() - {"PROVENANCE"} or t.has(*_META_TAGS):
        return False
    if t.has("poss") or w.endswith(("'s", "s'")):
        return _content_base(w.rstrip("s").rstrip("'").rstrip("’"))
    if w in _STOP:
        return False
    if t.has("lang:es") is False and w.endswith(("arle", "erle", "irle", "arlo", "erlo", "irlo", "arla", "arlos", "arse", "erse", "irse")):
        from .lexicon import tags as _tags
        base = w[:-2] if not w.endswith(("los", "las", "les")) else w[:-3]
        if _tags(base) & {"C:meta", "V:finding"} or any(x.startswith("F:") for x in _tags(base)):
            return False  # a Spanish infinitive with an enclitic ("encontrarle un fallo")
    if "-" in w:
        parts = [p for p in w.split("-") if p]
        from .lexicon import tags as _tags
        if parts and all(p in _STOP or any(x.startswith(("F:", "C:")) for x in _tags(p)) for p in parts):
            return False
    if t.cap and not t.init and _camel(t.raw):
        return False  # a product name written CamelCase ("GeoGebra"): a tool
    return True


def _content_base(w: str) -> bool:
    from .lexicon import tags as _tags
    tg = _tags(w)
    return not (any(x.startswith("F:") for x in tg) or tg & set(_META_TAGS) or w in _STOP)


def _camel(raw: str) -> bool:
    """A word with a capital after a lower-case letter inside it ("ChatGPT", "GeoGebra", "iPad"), not a Mc/Mac/O' surname."""
    if raw.startswith(("Mc", "Mac", "O'", "D'", "De", "La", "Le", "Di", "Van", "Von")):
        return False
    return any(raw[k].isupper() and raw[k - 1].islower() for k in range(1, len(raw)))


# ------------------------------------------------------------------------------------------------------------- segments
_SEG_COORD = frozenset(("and", "but", "since", "because", "as", "so", "while", "although", "though", "whereas", "y", "pero",
                        "porque", "aunque", "ya que", "pues", "which", "when", "cuando"))


def _segments(toks: list) -> list[list]:
    """Clauses for polarity: split at , ; : and dashes, and before a coordinator or subordinator that opens a clause."""
    out: list[list] = []
    cur: list = []
    for k, t in enumerate(toks):
        if t.punct and t.w in (",", ";", "—", "–", "--", "(", ")", "[", "]"):
            if cur:
                out.append(cur)
            cur = []
            continue
        if t.w in _SEG_COORD and cur and k + 1 < len(toks) and not toks[k + 1].punct:
            # (a coordinator between two words of one noun phrase, "figures and totals", stays inside: the clause starts only when
            # what follows holds a verb before the next break)
            rest = []
            for x in toks[k + 1:k + 12]:
                if x.punct and x.w in (",", ";", ":", ".", "—"):
                    break
                rest.append(x)
            if any(x.has("C:aux", "C:copula") or x.has("v:past", "v:3sg", "v:part", "v:es3", "v:espret", "v:espret1", "v:espret3")
                   for x in rest):
                out.append(cur)
                cur = [t]
                continue
        cur.append(t)
    if cur:
        out.append(cur)
    merged: list[list] = []
    for seg in out:
        sw = [t for t in seg if not t.punct]
        if merged and sw and len(sw) <= 2 and all(_neg_word(t) or t.w in ("0", "0%", "zero", "nil", "cero", "clean", "clear") or
                                                  t.has("C:neg_pron") for t in sw):
            merged[-1] = merged[-1] + seg  # "Errors: none.", "Error count: 0": the value of the key before it
            continue
        merged.append(seg)
    return merged


def _spanish(seg: list) -> bool:
    seg = [p for t in seg for p in (t.parts if getattr(t, "idiom", False) and t.parts else (t,))]  # (an idiom's own words count)
    return sum(1 for t in seg if t.has("lang:es") or t.w in ("hay", "aqui", "nada", "nadie", "ningun", "ninguna") or t.w in ("el", "la", "los", "las", "de", "que", "y", "en", "es", "ha", "nadie",
                                                            "nada", "ningun", "ninguna", "esta", "este", "esto", "una", "un", "estas",
                                                            "estos", "se", "han", "lo", "le", "del", "al", "por", "con", "su", "sus",
                                                            "muy", "ya", "todo", "todas", "todos", "cada", "sin", "hay")) >= 2 or \
        (any(t.w == "no" for t in seg) and any(t.w in ("ningun", "ninguna", "ninguno", "nada", "nadie", "ni", "tampoco", "nunca", "jamas")
                                               for t in seg))  # (negative concord marks the clause Spanish: "No encontrarás ningún fallo.")


_NEED = frozenset(("needs", "need", "needed", "requires", "require", "required", "necesita", "necesitan", "requiere", "requieren",
                   "need to", "needs to", "needed to"))
_ES_NEG = frozenset(("no", "nadie", "nada", "ningun", "ninguna", "ninguno", "nunca", "ni", "tampoco", "jamas", "sin", "imposible"))
_DEF_DET = frozenset(("the", "these", "those", "your", "his", "her", "their", "los", "las", "el", "la", "tus", "sus"))


def _production_note(seg: list, k: int) -> bool:
    """A production verb with no check signal of its own ("calculated everything by hand", "worked out on paper", "These values were
    calculated from the data.", "a calculated value"): how a value was produced, never a check of it (c3c: before, only a verb with
    its manner was a note, so "calculated from the data" was read as a check while "computed from the census data" was not). A
    redo ("recalculated"), a check signal ("twice", "independently") or a production credited to the pipeline or a tool ("computed
    by Z3") is no note."""
    from .reader import _manner_of_production, _SIGNAL, _SIGNAL_IDIOMS
    t = seg[k]
    window = seg[k + 1:k + 9]
    if t.has("prefix") or t.w.startswith(("re", "double", "cross", "triple")):
        return False
    if any(x.w in _SIGNAL or x.w in _SIGNAL_IDIOMS for x in window):
        return False
    # ("worked" + "out" is read as two words: the phrasal verb is a production verb too; check round 9 of c3c, "These values were
    # worked out from the data in Table 1.")
    phrasal = t.w in ("worked", "work", "works", "working") and bool(window) and window[0].w == "out"
    if any(x.has("C:eval_int", "C:tool", "C:eval_int_agentive", "C:eval_asr", "C:m_eval") for x in window) or \
            not (t.w.startswith(_COMPUTE_STEMS) or phrasal):
        return _manner_of_production(window)  # (a light verb, "ran each figure past a second reader", is read for its frame)
    return True


#: The stems of the production verbs of computing a value (a production note without its manner, c3c).
_COMPUTE_STEMS = ("calculat", "comput", "deriv", "obtain", "estimat", "determin", "worked out", "work out", "works out", "calcul",
                  "obtuv", "obten", "deriv", "comput")


def _polarity(seg: list) -> tuple[int, bool, bool, bool]:
    """(sign, has_positive, has_defect, negated) of a clause (rule P1): the sign is (-1) to the number of negators and defect
    words, Spanish negative concord counted once; a denying matrix flips (P2); "needs checking" is an open check, a defect; a
    DEFINITE defect noun phrase is presupposed, never denied ("I could not find the mistakes", P4: no positive reading); a
    non-universal quantifier concedes exceptions (P5: no positive reading of an outcome)."""
    es = _spanish(seg)
    n = 0
    seen_es_neg = False
    pos = False
    dfc = False
    presupposed = False
    partial = False
    last_defect = -9
    k = 0
    while k < len(seg):
        t = seg[k]
        if t.punct:
            k += 1
            continue
        nxt = seg[k + 1] if k + 1 < len(seg) else None
        if t.has("C:affirm_idioms", "C:affirm_matrix") and not (t.fam() & {"CONFIDENCE"} and not any(
                x.w in ("that", "que", "whether", "si") for x in seg[k + 1:k + 3])):
            k += 1
            continue  # (a matrix over its that-clause affirms it; "no doubt about the result above" is a confidence of its own)
        if t.has("C:deny_matrix"):
            n += 1
            k += 1
            continue
        if t.w in ("que", "that", "which", "who", "donde", "cuyo"):
            seen_es_neg = False  # a relative or complement clause is a negation domain of its own ("No hay ningún valor que no ...")
        if t.has("C:partial", "C:partial_idioms") and t.w not in ("half",) and not (
                t.w == "most" and nxt is not None and (nxt.has("adj") or nxt.fam() & {"OUTCOME", "QUALITY", "SRCEVAL"})) and not (
                k > 0 and seg[k - 1].w in ("no", "not", "not a", "ningun", "ninguna", "ni")):
            partial = True  # ("the most accurate" is a superlative, no quantifier; "no part of this" denies every part)
        if t.has("V:need") or t.w in _NEED:
            # "needs checking", "need no further checking", "do not need to be checked": an open check is a defect (the negators
            # around it are counted where they stand)
            j = k + 1
            while j < len(seg) and j <= k + 5 and (seg[j].w in ("no", "not", "n't", "further", "more", "any", "additional", "extra",
                                                                "to", "be", "been", "re", "nada", "mas", "ser") or _neg_word(seg[j])):
                j += 1
            if j < len(seg) and (seg[j].fam() & {"CHECK", "DEFECT"} or seg[j].has("C:m_check")):
                dfc = True
                n += 1
                for q in range(k + 1, j):
                    if _neg_word(seg[q]):
                        n += 1
                k = j + 1
                continue
        if t.w == "beyond" and nxt is not None and (_defect(nxt) or nxt.has("C:m_doubt")):
            n += 2  # "beyond dispute": no dispute (the doubt noun counted with its negator)
            dfc = True
            k += 2
            continue
        if t.has("C:m_doubt") and t.idiom and t.parts and t.parts[0].w in ("no", "without", "sin", "beyond", "free"):
            dfc = True
            n += 2  # "no doubt", "sin duda": the doubt and its denial in one token ("There can be no doubt about the result above.")
            k += 1
            continue
        if t.has("C:m_doubt"):
            back = k - 1
            while back > 0 and seg[back].w in ("in", "any", "a", "the", "of", "open to", "en", "lugar a"):
                back -= 1  # "not in doubt", "not open to any doubt": the negation over the doubt phrase
            if k > 0 and (_neg_word(seg[back]) or seg[back].w in ("without", "sin")):
                dfc = True
                n += 1
            k += 1
            continue
        if t.w in ("0", "0%", "zero", "cero", "nil") and (nxt is not None and _defect(nxt) or (k > 0 and any(_defect(x) for x in seg[:k]) and
                                                                                    (nxt is None or nxt.punct))):
            n += 1
            k += 1
            continue
        if t.w in ("without", "sin") and inert_complement(seg, k) > 0:
            k = inert_complement(seg, k)
            continue  # "without any outside help", "sin ayuda de nadie": the negation stays inside its own complement (attack round 7)
        if t.w in ("without", "sin") and nxt is not None and not nxt.punct and (nxt.w.endswith("ing") or (
                es and nxt.w.endswith(("ar", "er", "ir")))) and (nxt.fam() & {"CHECK"} or nxt.has("C:m_check")):
            k += 2
            continue  # "rely on it without checking it": the gerund is a negated act of its own, the clause it adjoins stays positive
        if _neg_word(t) and nxt is not None and nxt.w in ("be", "get", "look", "sound", "seem", "ser", "estar") and k + 2 < len(seg) and \
                seg[k + 2].w in ("more", "any more", "mas", "better", "clearer", "mejor", "improved", "improved upon", "bettered",
                                 "mejorado", "mejorada"):
            k += 2
            continue  # "couldn't be more correct", "no podría ser más claro": a comparison with nothing higher, the highest degree
        if _neg_word(t) and any(seg[q].w in ("more", "better", "mas", "mejor") and q + 1 < len(seg) and (
                _positive(seg[q + 1]) or seg[q].w in ("better", "mejor")) for q in range(k + 1, min(len(seg) - 1, k + 7))) and \
                any(x.has("V:finding") or x.w in ("see", "get", "ask for", "wish for", "veras", "pedir") for x in seg[k + 1:k + 4]):
            k += 1
            continue  # "You won't find a more accurate treatment anywhere.": nothing better is found, the highest degree (attack round 3)
        if t.w in ("nor", "ni") and any(x.w in ("neither", "ni") for x in seg[:k]) and not es:
            k += 1
            continue  # "neither X nor Y": one negation over both members (the correlative "nor" adds none)
        if _neg_word(t):
            if t.w == "not" and nxt is not None and nxt.w in ("only", "just", "merely", "solo"):
                k += 1
                continue  # "not only" adds, it does not deny
            if es and t.w in _ES_NEG:
                if seen_es_neg:
                    k += 1
                    continue
                seen_es_neg = True
            n += 1
            k += 1
            continue
        if t.w in ("word count", "recuento de palabras", "word counts") and not any(x.num for x in seg):
            k += 1
            continue  # "a word count, which is a remark about the answer": the kind named, no count stated (the writer's own word count
            # is a number: decision D7)
        if t.w in ("flagged", "flag", "flags", "flagging") and nxt is not None and nxt.w in ("as", "como") and k + 2 < len(seg) and \
                _positive(seg[k + 2]):
            k += 1
            continue  # "Flagged as correct": a label put on the answer (attack round 4), never a fault flagged
        if _defect(t):
            dfc = True
            if k > 0 and seg[k - 1].w in _DEF_DET and t.has("noun") is not False and not t.idiom and not t.has("adj"):
                presupposed = True
            if k >= 2 and seg[k - 1].w in ("and", "or", "y", "o", "nor", ",") and k - 2 == last_defect:
                last_defect = k
                k += 1
                continue  # "unchecked and unverified": coordinated defect words share one polarity (one denial, not two)
            last_defect = k
            n += 1
            if t.idiom and any(x.w in ("nothing", "no", "nada", "none", "zero", "not") for x in t.parts):
                if not (es and seen_es_neg):
                    n += 1  # (Spanish negative concord: "No hay nada que corregir" denies once)
                if es:
                    seen_es_neg = True
            k += 1
            continue
        if _designation(seg, k):
            k += 1
            continue
        if (t.has("noun", "C:check_noun") or t.w.startswith("self-")) and t.fam() & {"CHECK"} and k > 0 and seg[k - 1].w in ("a", "an", "un", "una") and \
                not any(x.has("v:part", "v:past") and x.fam() & {"CHECK", "STATUS"} or x.w in ("done", "complete", "completed", "passed")
                        for x in seg if x is not t):
            k += 1
            continue  # "a self-certification of the specialist", "a review of the sources": a kind named, no check reported
        if t.w in ("proved", "proven", "proves", "prove", "proving") and nxt is not None and (nxt.has("adj") or nxt.fam() & {
                "OUTCOME", "QUALITY", "SRCEVAL"}) and not nxt.fam() & {"STATUS"}:
            k += 1
            continue  # "The engine proved reliable.": copular "prove" (turned out), no proof; the adjective is read for itself
        if k > 0 and seg[k - 1].w in ("a", "an", "un", "una") and t.fam() and t.fam() <= {"AGREE"} and not t.idiom:
            k += 1
            continue  # "a square", "a match": a noun of the subject, no agreement
        if t.has("prod") and (t.fam() <= {"CHECK", "DEFECT", "PROVENANCE"} or (t.w.startswith("work") and t.fam() <= {
                "CHECK", "OUTCOME", "DEFECT", "PROVENANCE"})) and _production_note(seg, k):
            k += 1
            continue  # "I calculated everything by hand": how the working was produced, a method note (attack round 4)
        if _positive(t) or _parts_reliable(seg, k) or _been_over(seg, k) or _score_claim(seg, k) or _awarded_score(seg, k) or (t.has("C:comply_verb") and any(x.has("C:request_noun", "C:assess_instrument") or x.w in ("any", "every", "all")
                                                            for x in seg[k + 1:k + 4])) or _comply_passive(seg, k):
            if t.has("negaffix"):
                n += 1
            if t.idiom and t.parts and t.parts[0].w in ("without", "sin") and not _defect(t) and t.fam() & {"QUALITY", "SRCEVAL"} and \
                    not t.fam() & {"OUTCOME", "FIDELITY", "CONFIDENCE", "AGREE"}:
                n += 1  # "without foundation", "without basis": the quality denied ("not without foundation" affirms it)
            pos = True
        k += 1
    if presupposed or (partial and not any(x.fam() & {"CHECK", "STATUS", "APPROVE"} for x in seg)):
        return -1, pos, dfc, True
    return (-1 if n % 2 else 1), pos, dfc, n > 0


def _mood_of(seg: list, question: bool, first: bool) -> str:
    """question, protasis, weak (a possibility, a low degree, or a probability hedge over a verdict that reports no check),
    declarative."""
    if question:
        return "question"
    words = [t for t in seg if not t.punct]
    if not words:
        return "declarative"
    w0 = words[0]
    if w0.w in ("if", "unless", "whether", "si", "provided", "suppose", "supposing", "assuming", "in case", "a menos que") or (
            w0.w in ("had", "were", "should") and len(words) > 1 and words[1].w in ("there", "it", "any", "anything", "the", "this")):
        return "protasis"
    if any(t.has("C:m_low") for t in words):
        return "weak"
    for k, t in enumerate(words[:-1]):
        if t.w in ("to", "para") and (words[k + 1].fam() & {"CHECK"} and words[k + 1].has("v:base") or
                                      (words[k + 1].w in ("be", "ser") and k + 2 < len(words) and words[k + 2].fam() & {"CHECK"})):
            flat_before = " ".join(x.w for x in words[max(0, k - 4):k])
            if not any(x in flat_before for x in ("took care", "take care", "taken care", "took the time", "taken the time", "made sure",
                                                  "managed", "remembered", "bothered", "made a point", "me encargue", "procure",
                                                  "was used", "were used", "been used", "i used", "we used", "used my", "used our",
                                                  "went on", "proceeded")):
                return "weak"  # "(to be checked)", "to verify": a purpose or a task still to do, no check reported
    if len(words) == 1 and words[0].has("v:base") and not words[0].has("v:part", "v:past", "adj") and words[0].fam() & {"CHECK"}:
        return "weak"  # "(verify)": a bare instruction
    for k, t in enumerate(words[:-1]):
        if (t.has("C:future_modal", "C:ability_modal") or t.w in ("will", "shall", "'ll", "can", "puedo", "podemos", "voy")) and \
                words[k + 1].fam() & {"CHECK"} and words[k + 1].has("v:base") and any(x.has("C:pron1") for x in words[:k + 1]):
            return "weak"  # an offer or a future act of the writer ("I will check the method"): no check reported (X22)
    check_claim = any(t.fam() & {"CHECK", "STATUS", "APPROVE"} and not t.has("prod") or t.has("C:m_check") for t in words)
    for k, t in enumerate(words[:-1]):
        if t.w in _NEED or t.has("V:need"):
            continue  # "needs checking", "need no further checking": an open check, read by the polarity (a defect), no obligation
        if (t.has("C:deontic", "C:deontic_idioms") and t.w not in ("has", "have", "had", "should", "ought")) or \
                t.w in ("must", "deben", "debe", "debes", "hay que", "tienen que", "tiene que", "need to", "needs to", "have to", "has to"):
            if any(x.fam() & {"CHECK", "STATUS", "APPROVE"} or x.has("C:m_check") for x in words[k + 1:k + 5]):
                return "weak"  # "deben ser comprobadas", "must be checked": an obligation, no check reported (deontic)
    for k, t in enumerate(words):
        if t.has("C:weak_idioms"):
            if t.w in ("could be", "can be", "could have been", "could ever be") and k + 1 < len(words) and (
                    words[k + 1].has("V:finding") or words[k + 1].w in ("found", "spotted", "detected", "identified", "seen")) and \
                    any(_defect(x) for x in words):
                continue  # "Not one error could be found.": the ability to find a defect, denied, no uncertainty
            if t.w in ("could be", "might be", "may be", "could ever be", "could have been") and any(
                    x.has("V:finding") or x.w in ("see", "imagine", "think", "veo", "imagino") for x in words[max(0, k - 6):k]) and \
                    any(_neg_word(x) for x in words[max(0, k - 8):k]) and any(_defect(x) for x in words[k + 1:k + 3]):
                continue  # "I can't see any way this could be wrong.": the finder denies the defect's very possibility
            if t.w in ("should be", "ought to be") and any(_extreme(x) for x in words[k + 1:]):
                continue  # "should be beyond reproach": a verdict at the top of its scale, a confidence claim
            return "weak"
        strong = (t.has("C:m_strong") or t.w in ("should", "ought", "likely", "probably")) and \
            t.w not in ("certainly", "definitely", "surely", "undoubtedly")
        if strong:
            if check_claim:
                continue  # "probably all verified", "should be fine, it was reviewed": the check is claimed all the same
            if any(_extreme(x) for x in words[k + 1:]):
                continue  # "should be beyond reproach", "probably flawless": a verdict at the top of its scale, a confidence claim
            return "weak"   # "should all be fine", "probably correct": an uncertain verdict (P3)
        if t.has("C:weak") and t.w not in ("if", "unless", "whether"):
            if t.w in ("may", "can", "could", "puede", "puedes") and any(x.fam() & {"ASSURE"} for x in words[k + 1:k + 4] + (
                    words[k + 1:k + 8] if k > 0 and words[k - 1].w in ("you", "tu", "usted") else [])):
                continue  # "may rely on", "can trust": a permission to rely on the answer, an assurance (ASSURE)
            if t.w in ("could", "can", "puede", "podria", "pudo") and any(x.has("V:finding") or _defect(x) or x.fam() & {"DEFECT"}
                                                                           for x in words[k + 1:k + 6]):
                continue  # "could not find a slip": ability to find a defect, no uncertainty
            if t.w in ("could", "might", "may", "podria", "pudiera") and any(
                    x.has("V:finding") or x.w in ("see", "imagine", "think", "veo", "imagino") for x in words[max(0, k - 6):k]) and \
                    any(_neg_word(x) for x in words[max(0, k - 8):k]) and any(_defect(x) for x in words[k + 1:k + 4]):
                continue  # "I can't see any way this could be wrong.": a defect whose very possibility the finder denies (attack round 3)
            if t.w in ("could", "can", "podria") and k + 3 < len(words) and _neg_word(words[k + 1]) and words[k + 2].w in ("be", "ser") and \
                    words[k + 3].w in ("improved", "improved upon", "bettered", "faulted", "more", "mejorado", "mejorada", "mas"):
                continue  # "could not be improved upon": nothing higher, the highest degree, no uncertainty
            return "weak"
    return "declarative"


#: Verdicts at the top of their scale: under a probability hedge ("should be", "probably") they remain a confidence claim.
_EXTREME = frozenset(("flawless", "faultless", "perfect", "perfectly", "impeccable", "spotless", "infallible", "unimpeachable",
                      "immaculate", "airtight", "watertight", "bulletproof", "iron-clad", "ironclad", "error-free", "mistake-free",
                      "100%", "error-proof", "foolproof", "unerring", "letter-perfect", "impecable", "perfecto", "perfecta"))


def _extreme(t) -> bool:
    return t.w in _EXTREME or (t.idiom and t.w.startswith(("beyond ", "fuera de ", "a prueba de "))) or (
        t.has("C:m_pos") and t.w.startswith("beyond"))


_IMPERATIVE_VERBS = frozenset((
    "make sure ensure double-check remember proofread check verify confirm correct fix label compare redo recalculate review test "
    "look read write use note show revisa comprueba verifica corrige asegurate make be trace run try find calculate compute plot "
    "draw state explain describe list give rewrite add remove replace send upload practise practice repeat learn revise start begin "
    "keep avoid rank sort count measure record identify underline highlight circle mark tick substitute differentiate integrate "
    "expand factorise simplify solve estimate round convert copy swap move cut paste attach submit").split()) | {"make sure", "double check"}


def _imperative(words: list, ctx) -> bool:
    """An instruction: a clause opening (after list marks and "please") with a base-form verb that no subject precedes. A verb
    followed by a colon is a label's key ("Quote:", "Check:"), no instruction."""
    raw = words
    if any(t.punct for t in words):
        raw = words
        words = [t for t in raw if not t.punct]
        first = next((m for m, t in enumerate(raw) if not t.punct), None)
        if first is not None and first + 1 < len(raw) and raw[first + 1].w == ":":
            return False
    k = 0
    while k < len(words) and (words[k].num or (len(words[k].w) == 1 and words[k].w not in ("i", "a", "y", "o")) or
                              words[k].has("C:imperative_skip") or words[k].w in (
            "please", "remember to", "be sure to", "por favor", "step", "paso") or (k == 0 and words[k].w in (
            "and", "then", "also", "y", "e", "luego", "despues", "tambien") and len(words) > 1)):
        k += 1  # (a coordinated instruction: "..., revisa el saludo y verifica la fecha", "and check the units")
    if k >= len(words):
        return False
    t = words[k]
    nxt = words[k + 1] if k + 1 < len(words) else None
    if _es_preterite1(t):
        return False  # "Revisé cada línea." (folded "revise"): the writer's own past act, never an instruction (attack round 3)
    if nxt is None and k > 0 and words[k - 1].w in ("please", "por favor") and (t.w in _IMPERATIVE_VERBS or t.has("C:imperative_verbs") or
                                                                             (t.fam() & {"CHECK"} and t.has("v:base"))):
        return True  # "Please confirm.", "Please review.": a request
    if any(x.fam() & {"CHECK", "STATUS"} and x.has("v:part", "adj") and not x.has("v:base") for x in words[k + 1:k + 4]) and \
            not any(x.has("C:aux", "C:copula") for x in words[k + 1:k + 4]) and nxt is not None and not nxt.has("C:det", "C:dist"):
        return False  # "Trace table verified line by line.": a noun and its participle, a headline
    if t.w in ("note", "nota") and nxt is not None and (nxt.raw[:1].isupper() or any(x.w == ":" for x in raw[:8] if x.punct)):
        return False  # "Note All figures ...", "Note on the figures: ...": a note's label, no instruction
    if t.w in ("consider", "regard", "deem", "treat", "take", "count", "call", "considera", "considerad", "considere", "toma", "da") and \
            any(x.has("C:anchor", "C:anchor_idioms", "C:anaph", "C:demonstrative", "C:pron3") for x in words[k + 1:k + 4]) and \
            any(_positive(x) for x in words[k + 2:]):
        return False  # "Consider this answer settled.", "Take it as correct." (attack round 7): a verdict put to the reader, asserted
    if (t.w in _IMPERATIVE_VERBS or t.has("C:imperative_verbs")) or (k > 0 and words[0].w in ("y", "e", "luego") and t.has("v:es3") and
                                                                     t.fam() & {"CHECK"}):
        if k > 0 and words[0].w in ("y", "e", "luego") and t.has("v:es3") and nxt is not None and nxt.has("C:det", "C:complementizer") or \
                (k > 0 and words[0].w in ("y", "e", "luego") and nxt is not None and nxt.w in ("que", "si", "la", "el", "los", "las")):
            return True  # "y comprueba los acentos", "y verifica la fecha": the second verb of a tú instruction
        if nxt is None or nxt.w.startswith("zz") or nxt.punct:
            return False
        if t.fam() & {"OUTCOME", "QUALITY"} and not nxt.has("C:det", "C:dist", "C:poss2", "C:anaph", "C:pron3"):
            return False  # "correct", "clear" before no determiner: an adjective, no instruction ("correct ✓")
        if nxt.has("C:aux", "C:copula") or nxt.w in ("by", "and", "out", "up") and t.w not in ("make sure",):
            return False
        if t.w in ("make", "be") and nxt.w not in ("sure", "certain", "careful"):
            return False
        return nxt.has("C:det", "C:dist", "C:poss2", "C:prep", "C:anaph", "C:pron3", "C:complementizer") or nxt.w in (
            "that", "it", "your", "the", "each", "every", "all", "sure", "whether", "both", "any", "first", "again", "la", "el", "los",
            "las", "que", "tu", "cada", "si") or nxt.has("C:part", "C:genre", "C:check_noun") or (nxt.w.endswith("s") and not nxt.t)
    return False


def _es_preterite1(t) -> bool:
    """A Spanish first-person preterite written with its accent ("Revisé", "Comprobé", "Verifiqué") whose folded spelling is an
    English base verb ("revise"): the writer's own completed act."""
    if not t.w.endswith("e") or len(t.w) < 4 or not t.w.isalpha():
        return False
    from .reader import original_spelling
    return original_spelling(t)[-1:] in ("é", "É")


# ------------------------------------------------------------------------------------------------------------- M1
def _counterfactual(segs: list[list]) -> bool:
    """A protasis that names a defect and an apodosis in which an evaluator would have caught, flagged, said or found it."""
    for m in range(len(segs) - 1):
        p = [t for t in segs[m] if not t.punct]
        if not p or not (p[0].w in ("if", "si") or (p[0].w in ("had", "were") and len(p) > 1 and p[1].w in ("there", "it", "any"))):
            continue
        if not any(_defect(t) for t in p):
            continue
        q = [t for t in segs[m + 1] if not t.punct]
        if any(t.w in ("would", "'d", "habria", "hubiera") for t in q) and any(
                t.has("V:finding", "V:report_back", "C:report_verb", "C:m_catch") or t.fam() & {"CHECK"} for t in q) and \
                not any(_neg_word(t) for t in q):
            return True
    return False


_SCORE_HEADS = frozenset(("band", "level", "grade", "nota", "calificacion", "puntuacion", "score", "mark", "marks", "rating", "nivel",
                          "banda"))
_CONF_HEADS = frozenset(("confidence", "certainty", "confidence level", "certainty level", "confianza", "certeza"))


def _designation(seg: list, k: int) -> bool:
    """"marks X as ...", "is marked as ...": a designation, no assessment."""
    t = seg[k]
    return t.w in ("marked", "marks", "mark", "marking") and any(x.w in ("as", "como") for x in seg[k + 1:k + 5]) and \
        not any(x.fam() & {"OUTCOME", "QUALITY", "SCORE"} for x in seg[k + 1:k + 7])


def _score_claim(seg: list, k: int) -> bool:
    """A score or a level given to the work ("Band 5 answer.", "Calificación: 7.", "Grade: A*", "Level 4 response"), or a
    confidence of at least 80 per cent ("Confidence level: 99%."). A lower confidence is an uncertainty (boundary (b))."""
    t = seg[k]
    if len(t.w) == 1 and t.w in "abc" and t.raw.isupper() and k + 1 < len(seg) and seg[k + 1].w in ("+", "*", "+.", "*.") and \
            (k == 0 or seg[k - 1].punct):
        return True  # a top letter grade as a fragment ("A+ work.", "A* answer.")
    nxt = next((x for x in seg[k + 1:k + 3] if not x.punct), None)
    if nxt is None:
        return False
    if t.w in _CONF_HEADS:
        v = nxt.w.rstrip("%")
        try:
            return float(v) >= (0.8 if "." in v and float(v) <= 1 else 80)
        except ValueError:
            return nxt.w in ("high", "very high", "full", "total", "complete", "absolute", "maximum", "maximal", "alta", "maxima")
    if t.w in _SCORE_HEADS:
        return nxt.num or (len(nxt.w) <= 2 and nxt.w[:1].isalpha() and nxt.w[1:] in ("", "*", "+")) or nxt.w in ("full", "top", "maximum",
                                                                                                                 "maxima")
    return False


def _awarded_score(seg: list, k: int) -> bool:
    """A score verb with the score it awards ("la ha calificado con un 10", "scored 18", "graded it a 6"): a mark stated."""
    t = seg[k]
    if not (t.fam() & {"SCORE"} and any(x.startswith("v:") for x in t.t)) and not t.has("C:m_score_verb") and \
            t.w not in ("calificado", "calificada", "puntuado", "puntuada", "graded", "marked", "scored"):
        return False
    for x in seg[k + 1:k + 5]:
        if x.punct and x.w not in ("/", ":"):
            break
        if x.num or (len(x.w) <= 2 and x.w[:1].isalpha() and x.raw[:1].isupper() and x.w[1:] in ("", "*", "+")) or x.w in (
                "diez", "nueve", "seven", "six", "full marks", "top marks", "maximum", "the maximum", "full", "top", "maxima", "maximo",
                "highest", "la maxima", "el maximo"):
            return True  # (attack round 7: "Any examiner would give this the maximum.", "Mark awarded: full.")
    return False


def _been_over(seg: list, k: int) -> bool:
    """"I have been over/through every line": a check act ("been" + over/through + a distributive or the answer's parts)."""
    return seg[k].w in ("over", "through") and k > 0 and seg[k - 1].w == "been" and k + 1 < len(seg) and (
        seg[k + 1].has("C:dist", "C:dist_idioms", "C:anaph", "C:part", "C:genre", "C:genre_strong", "C:anchor_idioms") or
        seg[k + 1].w in ("it", "this", "them", "all", "every", "each"))


_ASSERTED_PARTS = frozenset("claim claims statement statements assertion assertions account accounts argument arguments view views "
                            "interpretation interpretations afirmacion afirmaciones argumento argumentos".split())


def _parts_reliable(seg: list, k: int) -> bool:
    """A reliability word ("reliable", "trustworthy", "fiables") said of the answer's own parts in a clause of meta words ("Reliable
    figures.", "These numbers are trustworthy.", "Estos números son fiables."): a claim of the answer's own quality (boundary (a);
    attack round 3). A source, a witness or another owner's figures keep the word their subject's (History, Psychology)."""
    t = seg[k]
    if t.fam() - {"PROVENANCE"} != {"SRCEVAL"}:
        return False
    # (claims, statements, accounts and arguments are what a source asserts: "These claims are reliable." is History's source
    # evaluation, never the answer's quality; the answer's own figures, numbers, values and data keep the reading)
    # (and "the result" with no anchor is the experiment's or the study's result in the sciences, whose reliability is the subject's
    # evaluation: "It was measured twice. ... The result is reliable."; "these results above", "my results" stay the answer's)
    own = any(x.has("C:anchor", "C:anchor_idioms", "C:poss1", "C:demonstrative") for x in seg)
    if not any(x.has("C:part") and not x.has("C:src_noun") and x.w not in _ASSERTED_PARTS and
               (own or x.w not in ("result", "results", "resultado", "resultados")) for x in seg):
        return False
    return not any(x.has("C:src_noun", "C:eval_out", "C:poss3", "C:pron3", "C:analysed_text", "C:poss2", "C:pron2") or
                   (x.has("poss") and not x.has("C:poss1")) for x in seg)


def _comply_passive(seg: list, k: int) -> bool:
    """A compliance verb in the passive with its request noun before it ("Every requirement of the question is met in full.", "Todos
    los criterios se cumplen"): the request is the subject, the verb follows its auxiliary (attack round 7)."""
    t = seg[k]
    return t.has("C:comply_verb") and k > 0 and (seg[k - 1].has("C:aux", "C:copula") or seg[k - 1].w in ("se", "been", "fully", "all")) \
        and any(x.has("C:request_noun", "C:assess_instrument") for x in seg[max(0, k - 8):k])


def _assessment_of(seg: list) -> bool:
    return any(_been_over(seg, k) or _positive(t) or _parts_reliable(seg, k) or _defect(t) or t.has("C:m_doubt") or _score_claim(seg, k) or _awarded_score(seg, k) or (t.has("C:comply_verb") and any(
        x.has("C:request_noun", "C:assess_instrument") or x.w in ("any", "every", "all") for x in seg[k + 1:k + 4])) or _comply_passive(seg, k)
               for k, t in enumerate(seg))


# ------------------------------------------------------------------------------------------------------------- frames
_QMARKS = frozenset(("'", '"', "\u2018", "\u2019", "\u201c", "\u201d", "\u00ab", "\u00bb"))


def _quote_spans(toks: list) -> list[int]:
    """Masked quotations, and short quotations the masking left as words (a quoted word or two: "'Proofread' is written ..."):
    the index of the quotation's last token."""
    out = []
    for k, t in enumerate(toks):
        # one index per masked quotation: its first q-run (the runs and inner stops after it are the same quotation)
        if _is_quote(t) and not (k > 0 and (_is_quote(toks[k - 1]) or (toks[k - 1].punct and toks[k - 1].w in ".,;:!?" and k > 1 and
                                                                       _is_quote(toks[k - 2])))):
            out.append(k)
    for k, t in enumerate(toks):
        if t.w in _QMARKS:
            for m in range(k + 2, min(len(toks), k + 5)):
                if toks[m].w in _QMARKS:
                    # (a closing stop inside the marks is the quoted text's own: "'Fact-checked!'", attack round 5)
                    if any(not x.punct for x in toks[k + 1:m]) and all(not x.punct or (x.w in (".", "!", "?") and q == m - 1)
                                                                      for q, x in enumerate(toks[k + 1:m], start=k + 1)):
                        out.append(m)
                    break
    return out


#: Nouns that name an item of a language (Language A and B content): a form, a word, a tense.
#: Names of grammatical forms and constructions (a quotation after one is the form mentioned, never used).
_GRAMMAR_NOUNS = frozenset(("passive", "active", "participle", "participles", "imperative", "modal", "clause", "gerund", "infinitive",
                            "subjunctive", "pasiva", "activa", "participio", "imperativo", "gerundio", "infinitivo", "subjuntivo",
                            "voz", "perifrasis", "term", "termino", "adjective", "adjetivo", "noun", "sustantivo", "slogan", "eslogan"))
_FORM_NOUNS = frozenset(("form", "forms", "word", "words", "spelling", "spellings", "tense", "tenses", "verb", "verbs", "sentence",
                         "sentences", "phrase", "phrases", "conjugation", "ending", "endings", "construction", "usage", "preposition",
                         "article", "agreement", "plural", "forma", "formas", "frase", "frases", "palabra", "palabras", "tiempo",
                         "verbo", "verbos", "conjugacion", "terminacion", "construccion", "expresion", "uso", "preposicion",
                         "articulo", "concordancia", "oracion", "grafia", "ortografia", "acento", "tilde"))


def _language_judgement(toks: list, k: int, s: str = "") -> bool:
    """Whether the outcome or defect word at ``k`` judges an item of a language, not this answer (attack round 3, the Language A
    and B content): its subject is a quotation ("'are' is incorrect", "La frase «...» es incorrecta"), it qualifies a form noun
    ("the correct form is 'is'", "La forma correcta es «haya»"), or it is the neuter "lo correcto" identified with a quotation
    ("Lo correcto es «Si tuviera dinero, viajaría»"). An anchor or the answer's own genre in the clause keeps it the answer's."""
    lo = k
    while lo > 0 and k - lo < 10 and not (toks[lo - 1].punct and toks[lo - 1].w in (";", ".", "?", "!")):
        lo -= 1
    hi = k
    while hi + 1 < len(toks) and hi - k < 10 and not (toks[hi + 1].punct and toks[hi + 1].w in (";", ".", "?", "!")):
        hi += 1
    clause = toks[lo:hi + 1]
    if any(x.has("C:anchor", "C:anchor_idioms", "C:genre_strong", "C:pron1", "C:poss1") for x in clause):
        return False
    quote = [m for m, x in enumerate(clause) if _is_quote(x) or x.w in _QMARKS]
    if s:
        # (a quotation the reader unmasked as the writer's own is read inline: its marks stand in the text as written)
        for m, x in enumerate(clause):
            seg_a = clause[m - 1].b if m > 0 else max(0, x.a - 2)
            if any(c in "\u00ab\u00bb\"\u201c\u201d\u2018\u2019'" for c in s[seg_a:x.a]) and m not in quote:
                quote.append(m)
        if clause and any(c in "\u00ab\u00bb\"\u201c\u201d\u2018\u2019'" for c in s[clause[-1].b:clause[-1].b + 2]):
            quote.append(len(clause) - 1)
    kk = k - lo
    nb = [clause[m] for m in range(max(0, kk - 2), min(len(clause), kk + 3)) if m != kk and not clause[m].punct]
    if any(x.w in _FORM_NOUNS for x in nb) and quote:
        return True  # "the correct form is 'is'", "la forma correcta es «haya»", "La frase «...» es incorrecta"
    start = max((m + 1 for m in range(kk) if clause[m].w == ","), default=0)
    before = [x for x in clause[start:kk] if not x.punct or x.w in _QMARKS or _is_quote(x)]
    if before and len(before) <= 6 and any(start <= q < kk for q in quote) and any(x.has("C:copula") for x in clause[max(0, kk - 3):kk]):
        return True  # "'are' is incorrect in formal English": the quoted word is the subject
    if kk >= 1 and clause[kk - 1].w in ("lo",) and quote and max(quote) > kk:
        return True  # "Lo correcto es «...»": the correct form, given in quotation marks
    return False


def _analysed_frame(toks: list, s: str, a: int, b: int) -> bool:
    """Whether the sentence analyses the source it quotes: an analysis word in it or next to it, an analysed text named, or a
    lettered source of the paper (attack round 3)."""
    from .reader import _analysis_nearby, _source_letter
    if any(t.has("C:analysis", "C:analysed_text") for t in toks) or _source_letter(toks):
        return True
    return bool(s) and _analysis_nearby(s, a, b)


def _attributed_quote(toks: list, k: int, ctx) -> bool:
    """Whether the quotation at ``k`` is credited to an outside source by its frame (a source, document, speaker or character
    noun, or a name, before it)."""
    for x in toks[max(0, k - 14):k]:
        if x.has("C:src_noun", "C:analysed_text", "C:eval_out") or (x.cap and not x.init and x.w not in ("i",)) or \
                x.w in ("source", "fuente"):
            return True
    return False


def _mention_quote(toks: list, k: int) -> bool:
    """A quotation that is mentioned or analysed, not used: introduced by a source noun or "for example", the subject of an
    analysis or description verb, or the word under discussion ("'Proofread' is written as one word")."""
    start = k
    if toks[k].w in _QMARKS:
        start = k - 1
        while start > 0 and toks[start].w not in _QMARKS:
            start -= 1
    elif _is_quote(toks[k]):
        while k + 1 < len(toks) and (_is_quote(toks[k + 1]) or (toks[k + 1].punct and toks[k + 1].w in ".,;:!?" and k + 2 < len(toks) and
                                                                 _is_quote(toks[k + 2]))):
            k += 1  # the masked quotation's last run: what follows it is its frame
    before = [t for t in toks[max(0, start - 4):start] if not t.punct]
    flat_before = " ".join(t.w for t in before)
    if any(x in flat_before for x in ("other words", "in short", "that is", "i.e", "put it", "otras palabras", "es decir", "i would say",
                                      "my verdict", "as i said")):
        return False  # the writer's own words in other terms (a SELF frame), never a mention
    after = [t for t in toks[k + 1:k + 4] if not t.punct]
    if len(before) >= 2 and before[-1].has("C:copula") and any((x.has("poss") or x.has("C:poss3", "C:kin")) and not x.has(
            "C:eval_int", "C:tool", "C:eval_asr", "C:m_eval") for x in before[:-1]):
        return True  # "her husband's concession is '...'": a third party's words as the subject matter
    if any(x.has("C:eval_int", "C:eval_asr", "C:tool", "C:m_eval", "C:pron1") or (x.w.endswith(("'s", "s'")) and
                                                                                _content_base(x.w[:-2]) is False) for x in before):
        return False  # "In the examiner's words, '...'": an evaluator's words relayed, never a mention
    colon_before = any(t.w == ":" for t in toks[max(0, start - 3):start])
    own_noun = any(t.has("C:poss1") or t.w in ("own", "my", "our") for t in before)
    if colon_before or own_noun:
        # 'Headline: "..."', 'in my own phrase: "..."': the writer's own words under a label (a SELF frame), never a mention
        return False
    if any((t.has("C:src_noun", "C:analysed_text", "C:m_textnoun") and k > 0 and k >= len(before) - 1 and
            (before[k - 1].has("C:det", "C:poss3", "poss") or before[k - 1].w.endswith(("'s", "s'"))))
           or t.w in ("for example", "e.g.", "e.g", "such as", "for instance",
                                                                             "por ejemplo", "phrase", "word", "words")
           for k, t in enumerate(before)):
        return True
    if before and (before[-1].w in _FORM_NOUNS or before[-1].w in _GRAMMAR_NOUNS) and len(before) >= 2 and (
            before[-2].has("C:det") or (len(before) >= 3 and before[-3].has("C:det") and not before[-2].has(*_OWN_SCOPE_TAGS) and
                                        not before[-2].fam())):
        # "the passive 'is tested'", "la pasiva «es probado»", "the verb 'verified'" (attack round 5): a form mentioned; one modifier
        # may stand between ("the sample sentence '...'", "la oración modelo", c3c): a grammar example, language under discussion
        return True
    cop = next((m for m in range(len(before) - 1, max(-1, len(before) - 3), -1) if before[m].has("C:copula")), None)
    if cop is not None and cop >= 1 and before[-1].w in ("is", "are", "es", "son", "also", "too", "tambien", "simply", "just") and any(
            x.w in (_FORM_NOUNS | _GRAMMAR_NOUNS) - {"sentence", "sentences", "word", "words", "frase", "frases", "oracion"}
            for x in before[:cop]) and not any(x.has("C:anchor", "C:anchor_idioms", "C:demonstrative", "C:pron1", "C:poss1")
                                               for x in before[:cop]):
        return True  # "its past tense is also 'proofread'", "the plural is 'mice'" (check round 9 of c3c): a form given, mentioned
    inner_q = [t for t in toks[start + 1:k] if not t.punct]
    if toks[k].w in _QMARKS and before and before[-1].w in ("reads", "read", "says", "said", "states", "stated", "dice", "pone", "reza",
                                                             "decia") and any(
            x.has("C:src_noun", "C:analysed_text", "C:m_textnoun") for x in before[:-1]) and not any(
            x.has("C:genre", "C:genre_strong", "C:anchor", "C:anchor_idioms", "C:part") or x.w.startswith("zz") for x in inner_q):
        return True  # "The fact-checking site's post reads 'Fact-checked!'" (attack round 5): the words of an analysed text, quoted
    if after and (after[0].has("C:descr", "C:analysis", "C:m_analyse") or after[0].w in (
            "is written", "is spelt", "is spelled", "means", "meant", "is used", "uses", "used", "borrows", "suggests", "implies",
            "reinforces", "creates", "shows", "conveys", "reveals", "emphasises", "emphasizes", "echoes", "evokes", "signals",
            "create", "suggest", "imply", "reinforce", "convey", "reveal", "emphasise", "emphasize", "echo", "evoke", "signal", "mean",
            "build", "builds", "form", "forms", "establish", "establishes",
            "significa", "conjugates", "rhymes") or (len(after) > 1 and after[0].w in ("se", "is", "es") and after[1].w in (
            "conjuga", "escribe", "usa", "pronuncia", "conjugated", "conjugado", "written", "pronounced"))):
        return True  # (a word under discussion: "«Comprobar» se conjuga como «probar»", "'check' means ...")
    if before and any(t.w in ("conjuga", "conjugated", "conjugate", "conjugan", "conjugado", "como", "like") for t in before[-2:]) and \
            any(t.w.startswith(("conjug",)) for t in before):
        return True  # "se conjuga como «probar»": the model verb of a conjugation, mentioned
    if after and after[0].has("C:copula") and len(after) > 1 and after[1].w in ("written", "spelt", "spelled", "used", "a", "an",
                                                                                  "one", "the"):
        return True
    return False


_HYPOTHESIS_NOUNS = frozenset(("hypothesis", "hypotheses", "prediction", "predictions", "theory", "theories", "expectation",
                               "expectations", "hipotesis", "prediccion", "predicciones", "teoria", "teorias", "conjecture",
                               "conjectures", "suspicion", "suspicions", "model", "models"))
_AVOID_VERBS = frozenset(("avoid", "avoids", "avoiding", "prevent", "prevents", "preventing", "eliminate", "eliminates", "eliminating",
                          "minimise", "minimize", "minimises", "minimizes", "reduce", "reduces", "evitar", "evita", "evitando",
                          "prevenir", "eliminar", "minimizar", "reducir"))
_OWN_SCOPE_TAGS = ("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1", "C:genre", "C:genre_strong", "C:eval_int", "C:tool")


def _round7_frames(toks: list) -> list:
    """Boundary (b) frames of attack round 7, each a predicate over the hits it clears (word classes, linear):

    * an experiment's results or data confirming a hypothesis or a prediction ("The results confirmed the hypothesis.", "Los
      resultados confirmaron la hipótesis."): a check verb whose object is a hypothesis noun, in a sentence that names no part of
      this answer, is subject matter;
    * a purpose of avoiding a defect ("..., to avoid a zero error"): the defect is avoided, never said to exist or not;
    * a check of a third party's thing ("an independent auditor verified the firm's accounts"): a check verb whose object is a
      possessive of a subject-matter noun, in a sentence that names no part of this answer, is a check reported as subject matter.
    """
    out = []
    words = [t for t in toks if not t.punct]
    own = any(t.has(*_OWN_SCOPE_TAGS) for t in words) or any(t.w.startswith("zz") for t in words)
    # (the supplied case study is the subject's source, never this answer: "In the case study, an independent auditor verified ...")
    own_text = any(t.has(*_OWN_SCOPE_TAGS[:6]) and t.w not in ("case study", "case studies", "estudio de caso") for t in words) or \
        any(t.w.startswith("zz") for t in words)
    for k, t in enumerate(words):
        if (t.fam() & {"CHECK", "AGREE"}) and any(x.startswith("v:") for x in t.t) and not own_text:
            j = k + 1
            while j < len(words) and j - k <= 3 and (words[j].has("C:det", "C:definite", "C:poss3") or
                                                     words[j].w in ("the", "la", "el", "las", "los", "their", "his", "her", "its")):
                j += 1
            obj = words[j] if j < len(words) else None
            if obj is not None and not own and (obj.w in _HYPOTHESIS_NOUNS or (obj.has("poss") or obj.w.endswith(("'s", "s'"))) and
                                    j + 1 < len(words) and words[j + 1].w in _HYPOTHESIS_NOUNS):
                out.append(lambda f, a=t.a, b=t.b: f.family in ("CHECK", "AGREE") and f.a <= a < max(f.b, f.a + 1) or
                           (f.family in ("CHECK", "AGREE") and a <= f.a < b))
                continue
            if obj is not None and j > k + 1 and (obj.has("poss") or obj.w.endswith(("'s", "s'"))) and \
                    not obj.has("C:eval_int", "C:tool", "C:eval_asr", "C:pron1", "C:poss1", "C:anchor") and \
                    _content_base(obj.w[:-2] if obj.w.endswith(("'s", "s'")) else obj.w) is not False:
                out.append(lambda f, a=t.a, b=t.b: f.family in ("CHECK",) and (f.a <= a < max(f.b, f.a + 1) or a <= f.a < b))
        if t.w in _AVOID_VERBS:
            span = [x for x in words[k + 1:k + 5]]
            for x in span:
                if _defect(x):
                    out.append(lambda f, a=x.a, b=x.b: f.family == "DEFECT" and (f.a <= a < max(f.b, f.a + 1) or a <= f.a < b))
                    break
    return out


#: Verbs of making a defect ("the defendant made no mistakes", "committed no errors").
_MAKE_VERBS = frozenset("made make makes making committed commit commits hizo hace cometio comete cometieron".split())
#: Precision terms after "correct to" / "accurate to" ("correct to 2 s.f.", "to three decimal places", "to the nearest 10").
_PRECISION_WORDS = frozenset("s.f s.f. sf sig significant d.p d.p. dp decimal places place figures figure nearest cifras decimales "
                             "significativas".split())
_PRECISION_ADJ = frozenset("correct accurate exact precise rounded correcto correcta exacto exacta redondeado".split())
#: Anaphors that take up a noun phrase before them ("it", "all of them", "190 of them").
_ANAPHOR_SUBJECTS = frozenset("it they both all each most some none".split())
#: Arithmetic shown in words or symbols (a worked check's computation).
_ARITH_WORDS = frozenset("plus minus times divided menos mas por entre dan da son gives give equals es igual x".split())
_OUTCOME_ACTS = frozenset("passed pass passes held holds hold survived survives succeeded succeeds aprobo aprobaron supero superaron".split())


def _answer_object(toks: list, k: int) -> bool:
    """Whether the words after the check verb at ``k`` (its object, eight tokens at most) name this answer itself: "this response",
    "in this answer", "the reply above", "everything here" (an anchor of the answer's own scope, or a demonstrative or first-person
    possessive with an answer noun)."""
    obj = [x for x in toks[k + 1:k + 9] if not x.punct]
    for m, x in enumerate(obj):
        if x.w in (".", ";"):
            break
        if x.has("C:anchor", "C:anchor_idioms"):
            return True
        if x.w in ("answer", "response", "reply", "solution", "essay", "respuesta", "solucion") and m > 0 and \
                obj[m - 1].w in ("this", "my", "our", "esta", "este", "mi", "nuestra"):
            return True
    return False


def _c3c_frames(toks: list, ctx) -> list:
    """Boundary (b) frames of the c3c follow-up (attack round 8 of c3b, the correct-work and phrasings lenses), each a pair (a
    predicate over the hits it clears, a span whose meaning-layer readings it clears too, or None). Word classes, linear:

    * a check noun in a subject-matter compound that is the subject of a verb of the subject ("Checks and balances limit the power
      of the president."): the compound names a thing of the subject, no check;
    * a precision statement after a value ("42 (correct to 2 s.f.)", "3.14, accurate to three decimal places"): a rounding, no
      verdict;
    * agreement of the answer's figures with a named outside reference ("Every figure here matches the ONS release."): a material
      claim checked like any other (X7), even with the answer's own scope word, when the theme is the answer's figures and not the
      answer as a whole;
    * a defect made by a third party ("Zero mistakes were made by the defendant, the court found.", "The court found that the
      defendant made no mistakes."): a finding about a subject-matter person;
    * an outcome whose subject is a pronoun taking up a subject-matter noun earlier in the sentence ("all of them passed",
      "it held", "190 of them passed quality control"), unless what was passed is a bare check of the pipeline ("every check");
    * a label whose key is an agreement of accounts and whose value shows the computation ("Las cuentas cuadran: 250 menos 180
      dan 70."): a worked check, material for the engine.
    None applies when the sentence names the answer, its parts as the answer's own ("my", "this answer"), the writer, the pipeline
    or a tool as the agent."""
    from .reader import _finite
    out: list = []
    words = [t for t in toks if not t.punct]
    if not words:
        return out
    # ("US" in capitals is the country, never the pronoun "us")
    own_text = any(t.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1", "C:genre_strong") and t.raw != "US" for t in words) or \
        any(t.w.startswith("zz") for t in words)
    pipeline = any(t.has("C:eval_int", "C:tool", "C:eval_int_agentive", "C:m_eval") for t in words)

    def content(t) -> bool:
        return _content(t, ctx) and not t.has("C:part", "C:genre", "C:genre_strong", "C:anchor", "C:anchor_idioms")

    # (1) a check noun in a subject-matter compound, subject of a verb of the subject
    if not own_text and not pipeline:
        v = 0
        while v < len(words) and (words[v].fam() and words[v].has("noun", "C:check_noun") or words[v].w in ("and", "&", "y") or
                                  words[v].has("C:m_pos") and not words[v].fam()):
            v += 1
        if 2 <= v < len(words) - 1 and words[v].w.isalpha() and not words[v].fam() and not words[v].has(
                "C:det", "C:prep", "C:copula", "C:aux", "C:meta") and words[v + 1].has("C:det", "C:prep") or (
                2 <= v < len(words) and _finite(words, v, subject_seen=True) and not words[v].fam()):
            subj, obj = words[:v], words[v + 1:]
            fam_nouns = [x for x in subj if x.fam() and x.has("noun", "C:check_noun")]
            if fam_nouns and any(x.w in ("and", "&", "y") for x in subj) and not any(x.fam() for x in obj) and \
                    any(content(x) for x in obj) and not any(x.has("C:meta", "C:m_pos", "C:m_check") and not x.has("C:prep")
                                                              for x in obj):
                lo, hi = subj[0].a, subj[-1].b
                out.append((lambda f, lo=lo, hi=hi: lo <= f.a < hi, (lo, hi)))
    for k, t in enumerate(words):
        prev = words[k - 1] if k > 0 else None
        # (2) a precision statement after a value
        if t.w in _PRECISION_ADJ and k + 1 < len(words) and words[k + 1].w in ("to", "a", "hasta") and any(
                x.w.strip(".") in _PRECISION_WORDS or x.w in _PRECISION_WORDS for x in words[k + 2:k + 6]):
            j = k - 1
            while j >= 0 and (words[j].w in ("is", "are", "was", "es", "and", "y") or words[j].has("C:unit")):
                j -= 1
            before = [x for x in toks if x.b <= t.a][-3:]
            if j >= 0 and (words[j].num or any(c.isdigit() for c in words[j].w)) and (any(x.w in ("(", ",", "[") for x in before) or
                                                                                    words[j].b <= t.a):
                end = next((x.b for x in words[k + 2:k + 6] if x.w.strip(".") in _PRECISION_WORDS or x.w in _PRECISION_WORDS), t.b)
                out.append((lambda f, lo=t.a, hi=end: lo <= f.a < hi, (t.a, end)))
        # (3) the answer's figures agree with a named outside reference
        if (t.fam() & {"AGREE"} or t.w in ("matches", "match", "matched", "agrees", "agree", "coincide", "coinciden")) and \
                not pipeline and not any(x.has("C:genre_strong", "C:pron1", "C:poss1") for x in words):
            theme = words[max(0, k - 5):k]
            comp = words[k + 1:k + 8]
            named = [x for x in comp if ((x.cap and not x.init) or (x.raw.isupper() and len(x.raw) >= 2)) and
                     not x.has("C:eval_int", "C:tool", "C:assess_instrument", "C:eval_asr")]
            if any(x.has("C:part") for x in theme) and named and not any(x.has("C:assess_instrument", "C:eval_int", "C:tool", "C:eval_asr",
                                                                               "C:m_eval") for x in comp):
                lo, hi = theme[0].a, (comp[-1].b if comp else t.b)
                out.append((lambda f, lo=lo, hi=hi: f.family in ("AGREE", "FIDELITY", "CHECK") and lo <= f.a < hi, (lo, hi)))
        # (4) a defect made by a third party
        if _defect(t) and not own_text and not pipeline:
            agent = None
            for m in range(k + 1, min(len(words), k + 5)):
                if words[m].w in ("by", "por"):
                    agent = [x for x in words[m + 1:m + 5] if not x.has("C:det")][:2]
                    break
            if agent is None:
                mv = next((m for m in range(k - 1, max(-1, k - 5), -1) if words[m].w in _MAKE_VERBS), None)
                if mv is not None and mv > 0:
                    lo = mv - 1
                    while lo > 0 and mv - lo < 4 and not words[lo - 1].w in ("that", "que", ",", "and"):
                        lo -= 1
                    agent = [x for x in words[lo:mv] if not x.has("C:det")]
            if agent and any(content(x) or x.has("C:eval_out") for x in agent) and not any(
                    x.has("C:eval_int", "C:tool", "C:pron1", "C:poss1", "C:eval_asr", "C:genre", "C:part") for x in agent):
                out.append((lambda f, lo=t.a, hi=t.b: f.family == "DEFECT" and (f.a <= lo < max(f.b, f.a + 1) or lo <= f.a < hi), (t.a, t.b)))
        # (5) an outcome of a pronoun that takes up a subject-matter noun earlier in the sentence
        if t.w in _OUTCOME_ACTS and k > 0 and not own_text and not pipeline:
            m = k - 1
            subj = []
            while m >= 0 and k - m <= 4 and (words[m].w in _ANAPHOR_SUBJECTS or words[m].w in ("of", "them", "these", "those") or
                                             words[m].num or words[m].w in ("two", "three", "four", "five", "many", "several", "both")):
                subj.insert(0, words[m])
                m -= 1
            ante = words[:m + 1]
            if subj and any(x.w in ("it", "them", "they") for x in subj) and any(
                    content(x) or (x.has("C:part") and q > 0 and ante[q - 1].num) for q, x in enumerate(ante)):
                obj = words[k + 1:k + 5]
                bare_check = any(x.has("C:dist", "C:dist_idioms") or x.w in ("every", "all", "each", "cada", "todas", "todos")
                                 for x in obj[:2]) and any(x.has("C:check_noun") for x in obj[:3])
                pipe_poss = any((x.has("poss") or x.w.endswith("'s")) and x.has("C:eval_int", "C:tool") for x in obj)
                if not bare_check and not pipe_poss:
                    hi = obj[-1].b if obj else t.b
                    out.append((lambda f, lo=subj[0].a, hi=hi: lo <= f.a < hi and f.family in ("OUTCOME", "CHECK", "STATUS"), (subj[0].a, hi)))
    # (7) what an assessor in general looks for ("An examiner would look for a clear thesis.", "Markers reward a balanced
    # conclusion."): a generic assessor, a verb of looking for or rewarding, and an indefinite object; no anaphor, no score
    # (a genre noun after an indefinite article, "a clear thesis", is a kind of work, not this answer)
    own7 = any(x.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1") or x.w.startswith("zz") or (
        x.has("C:genre_strong") and m > 0 and words[m - 1].w not in ("a", "an", "un", "una") and not words[m - 1].has("adj"))
        for m, x in enumerate(words))
    if not own7 and (words[0].w in ("a", "an", "any", "un", "una") or words[0].has("C:eval_asr") and words[0].w.endswith("s")):
        ev = next((m for m, x in enumerate(words[:3]) if x.has("C:eval_asr", "C:assessor_extra")), None)
        if ev is not None and not any(x.has("C:anaph", "C:demonstrative") or x.fam() & {"SCORE"} for x in words):
            m = ev + 1
            while m < len(words) and (words[m].has("C:would_modal", "C:future_modal", "C:ability_modal", "C:deontic") or
                                      words[m].w in ("would", "will", "should", "might", "may", "can", "could", "usually", "often")):
                m += 1
            if m < len(words) and words[m].w in ("look", "looks", "reward", "rewards", "expect", "expects", "want", "wants", "credit",
                                                 "credits", "value", "values", "seek", "seeks", "busca", "buscan", "premia", "premian"):
                rest = [x for x in words[m + 1:m + 4] if x.w not in ("for", "to", "see", "por")]
                if rest and rest[0].w in ("a", "an", "un", "una") or (rest and rest[0].w.endswith("s") and not rest[0].has("C:det")):
                    out.append((lambda f: f.rule in ("G1", "G2", "G3", "G5"), (toks[0].a, toks[-1].b)))
    # (8) the scope statement restated: the pipeline checks ONLY something ("The engine checks only the encoding."): what the engine
    # establishes, no result on this answer
    if not own_text:
        for k, t in enumerate(words[:6]):
            if t.fam() & {"CHECK"} and t.has("v:3sg", "v:base") and k > 0 and any(x.has("C:eval_int", "C:tool") for x in words[:k]) and \
                    any(x.w in ("only", "just", "solo", "solamente", "merely") for x in words[k + 1:k + 3]) and \
                    not any(_positive(x) and x is not t for x in words[k + 1:]):
                out.append((lambda f, lo=t.a, hi=t.b: lo <= f.a < hi, (t.a, t.b)))
    # (6) an agreement of accounts as a label over a computation shown
    colon = next((m for m, t in enumerate(toks[:10]) if t.w == ":"), None)
    if colon is not None and colon > 0:
        key = [t for t in toks[:colon] if not t.punct]
        value = [t for t in toks[colon + 1:] if not t.punct]
        if key and any(x.fam() & {"AGREE", "OUTCOME"} and (x.idiom or any(tg.startswith("v:") for tg in x.t)) for x in key) and \
                not any(x.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1", "C:genre_strong", "C:eval_int", "C:tool") for x in key) and \
                sum(1 for x in value if x.num) >= 2 and (any(x.w in ("=", "+", "-", "−", "×", "*", "/", "÷", "x") for x in toks[colon + 1:]) or
                                                         any(x.w in _ARITH_WORDS for x in value)):
            cb = toks[colon].b
            out.append((lambda f, cb=cb: f.a < cb, (toks[0].a, cb)))
    return out



def _raw_mentions(s: str, a: int, b: int) -> list[tuple[int, int]]:
    """The quotations of the sentence as written that are mentioned or analysed (their absolute spans)."""
    if not s or b - a > 4000 or not any(c in s[a:b] for c in "'\"\u2018\u2019\u201c\u201d\u00ab\u00bb"):
        return []
    from ..adapters.markdown import find_quotation_spans
    from .reader import _merge, _tokens
    try:
        spans = list(find_quotation_spans(s[a:b]))
    except Exception:  # noqa: BLE001 - a malformed sentence is read without quotations
        spans = []
    spans += _simple_quote_spans(s[a:b])
    if not spans:
        return []
    raw = _merge(_tokens(s, a, b))
    out = []
    # a list of short quotations ("words such as 'tested', 'checked' and 'passed'", attack round 7): the list is one mention, framed
    # by what stands before its first member and after its last
    spans = sorted(set((qa, qb, inner) for qa, qb, inner in spans[:64]))
    groups: list[list[tuple[int, int, str]]] = []
    for sp in spans:
        if groups:
            gap = s[a + groups[-1][-1][1]:a + sp[0]].strip(" \t'\"\u2018\u2019\u201c\u201d\u00ab\u00bb").lower()
            if gap in (",", "and", "or", ", and", ", or", "y", "o", "e", ", y", "and also", "or even") and \
                    len(groups[-1][-1][2].split()) <= 3 and len(sp[2].split()) <= 3:
                groups[-1].append(sp)
                continue
        groups.append([sp])
    for grp in groups:
        hits = []
        for n_m, (qa, qb, inner) in enumerate(grp):
            low = inner.lower()
            if any(x in low for x in ("this answer", "this response", "this essay", "this solution", "above", "esta respuesta",
                                      "this reply", "this synthesis", "the combined answer")):
                hits = []
                break  # an explicit reference to this answer inside a quotation is never masked, whoever it is attributed to
            qa += a
            qb += a
            # (a list member is framed by the list's own frame: the words before its first member, after its last)
            fa = grp[0][0] + a
            fb = grp[-1][1] + a
            before = [t for t in raw if t.b <= fa][-5:]
            after = [t for t in raw if t.a >= fb][:4]
            fake = before + [_QuoteTok(qa, qb)] + after
            hits.append(((qa, qb), _mention_quote(fake, len(before))))
        if hits and (any(m for _sp, m in hits) and len(grp) > 1 or len(grp) == 1):
            out.extend(sp for sp, m in hits if m or len(grp) > 1)
    return out


def _simple_quote_spans(t: str) -> list[tuple[int, int, str]]:
    """Straight or curly quotations a reading token may sit inside ("'verified  zzmarkpos '"): an opening mark after a blank or
    the start, the next same-kind mark before a blank, a stop or the end. One pass, bounded look-ahead."""
    out = []
    i = 0
    n = len(t)
    while i < n and len(out) < 64:
        c = t[i]
        if c in "'\"\u2018\u201c" and (i == 0 or t[i - 1] in " \t([:\u2014\u2013-") and i + 1 < n and not t[i + 1].isspace():
            closers = {"'": "'\u2019", '"': '"', "\u2018": "\u2019'", "\u201c": "\u201d\""}[c]
            j = i + 1
            while j < min(n, i + 400):
                if t[j] in closers and (j + 1 >= n or not t[j + 1].isalnum()):
                    break
                j += 1
            if j < min(n, i + 400) and t[j] in closers:
                out.append((i, j + 1, t[i + 1:j]))
                i = j + 1
                continue
        i += 1
    return out


class _QuoteTok:
    __slots__ = ("w", "a", "b", "t", "punct", "raw", "cap", "init", "num", "idiom", "parts")

    def __init__(self, a: int, b: int):
        self.w, self.a, self.b, self.t, self.punct, self.raw = "qq", a, b, frozenset(), False, "qq"
        self.cap = self.init = self.num = self.idiom = False
        self.parts = ()

    def has(self, *tg) -> bool:
        return False

    def fam(self) -> set:
        return set()


def _reference_agreement(toks: list, i: int) -> bool:
    """X7: an agreement trigger at ``i`` whose comparand is a named subject-matter reference with content of its own (a law, a
    rule, a formula, a definition, a model, a named figure or value, a subject-matter description), never an assessment
    instrument, the pipeline, an agent or the answer."""
    t = toks[i]
    lo = i
    while lo > 0 and i - lo < 10 and not (toks[lo - 1].punct and toks[lo - 1].w in (",", ";", ":", "(")):
        lo -= 1
    clause = toks[lo:i]
    passive = any(x.has("C:aux", "C:copula") for x in clause[-3:])
    if (t.fam() & {"FIDELITY"} or passive) and any(x.has("C:part") and (x.w.endswith("s") or any(y.has("C:dist", "C:dist_idioms")
                                                                                                   for y in clause))
                                                   for x in clause):
        return False  # "The quotations were matched word for word against the extract": a blanket claim over the answer's parts (X8)
    rest = toks[i + 1:i + 14]
    if t.idiom and t.w.endswith((" with", " to", " con")):
        comp = rest
    else:
        comp = rest
        while comp and (comp[0].punct and comp[0].w not in (",", ":")) or (comp and comp[0].w in ("with", "to", "con", "exactly",
                                                                                                   "fully", "closely", "well")):
            comp = comp[1:]
    words = []
    for x in comp:
        if x.punct and x.w in (".", ";", "!", "?"):
            break
        if x.punct and x.w in (",", ":") and words:
            break
        words.append(x)
    if not words:
        return False
    depth = 0
    unbracketed = []
    for x in words:
        if x.w in ("(", "["):
            depth += 1
        elif x.w in (")", "]"):
            depth = max(0, depth - 1)
        elif depth == 0:
            unbracketed.append(x)
    if any(len(x.w) > 1 and (x.has("C:assess_instrument", "C:eval_int", "C:tool", "C:eval_int_agentive", "C:eval_asr", "C:m_eval",
                                   "C:anchor", "C:anchor_idioms", "C:genre_strong") or x.w in ("receipt", "hub", "engine", "answer",
                                                                                               "answers", "respuesta"))
           for x in unbracketed):
        return False
    if any(x.has(_REF_HEADS_TAG) for x in words):
        return True
    contentful = [x for x in words if not x.punct and not x.has("C:det", "C:prep", "C:dist", "C:definite", "C:indefinite") and
                  x.w not in _STOP and not x.fam()]
    if any(x.num for x in words) and contentful:
        return True
    return len(contentful) >= 2 and not any(x.has("C:part") and not x.has(_REF_HEADS_TAG) for x in words[:2])


def _symbol_content(toks: list, k: int) -> bool:
    """A check mark used as a symbol of the subject (a noun, an object, a key's symbol), not a mark on the answer."""
    prev = toks[k - 1] if k > 0 else None
    nxt = toks[k + 1] if k + 1 < len(toks) else None
    if prev is not None and prev.w == "(" and k >= 2 and (toks[k - 2].has("C:m_tick") or toks[k - 2].w in ("ticking", "tick", "ticks")):
        return True
    if prev is None or prev.w in ("[", "("):
        return False  # "[✓ ...]", "(✓ verified)": a checklist box or a bracketed status, never a symbol of the subject
    if prev is not None and (prev.has("C:det", "C:m_tick") or prev.w in ("a", "an", "the", "each", "shows", "show", "showed",
                                                                         "displays", "display", "with", "enter", "put", "draw")):
        return True
    if nxt is not None and not nxt.punct and (nxt.has("v:3sg") or nxt.w in ("marks", "means", "shows", "indicates", "box", "symbol",
                                                                             "mark", "stands")):
        return True
    return False


def _nonsuccess(value: list) -> bool:
    # (a non-success word counted zero is none: "0 error(s), 0 warning(s)", "no errors" report success, attack round 5)
    live = [t for m, t in enumerate(value) if t.has("C:m_nonsuccess") and not (m > 0 and (
        value[m - 1].w in ("0", "zero", "no", "cero", "ningun", "ninguna", "none") or value[m - 1].has("C:neg")))]
    return bool(value) and bool(live) and not any(_positive(t) for t in value if not t.has("C:m_nonsuccess"))


# ------------------------------------------------------------------------------------------------------------- the review
def _span_toks(toks: list, a: int, b: int) -> list[int]:
    return [k for k, t in enumerate(toks) if t.a < b and a < t.b]


def review(toks: list, ctx, question: bool, found: list, found_cls, *, s: str = "", a: int = 0, b: int = 0,
           kind: str = "text") -> tuple[list, list]:
    """(kept, added): the compositional reader's hits in this sentence that no boundary frame clears, and the meaning layer's own
    hits (M1, M2). ``found_cls`` builds a hit; ``s[a:b]`` is the sentence as written (its quotations unmasked) and ``kind`` the
    piece it was read in (a bracket or a table cell is read with its host line)."""
    if kind == "bracket" and s and a > 0 and (s[a - 1:a] == "(" and a >= 2 and (s[a - 2].isalnum() or s[a - 2] == "_")):
        return found, []  # "find_position(scores, 12)", "f(x)": the arguments of a call or a function, not a bracketed remark
    if kind == "bracket" and s and any(t.has("C:m_method") for t in toks):
        ls = s.rfind("\n", 0, a) + 1
        le = s.find("\n", b)
        line = s[ls:(len(s) if le < 0 else le)][:4000]
        if ("=" in line or "\u2248" in line) and sum(c.isdigit() for c in line) >= 2:
            # "(verified by substitution): x = 4, since 2(4) + 3 = 11": a check by a stated method with its computation shown (X1)
            return [f for f in found if f.family not in ("CHECK", "STATUS")], []
    kept, added = _review(toks, ctx, question, found, found_cls, s, a, b, kind)
    if not added and not kept:
        added = _clause_parts(toks, ctx, question, found_cls, s, a, b, kind)
    if (kept or added) and s and b - a <= 2000:
        para = _paradigm_span(s, a, b)
        if para is not None:
            # a conjugation statement and its paradigm ("«Comprobar» se conjuga como «probar»: yo compruebo."): the verbs quoted
            # and the forms after the colon are language under discussion, never the writer's act (attack round 6)
            pa, pb, qspans = para
            def mention(f) -> bool:
                return f.b > pa or any(qa <= f.a and f.b <= qb for qa, qb in qspans)
            kept = [f for f in kept if not mention(f)]
            added = [f for f in added if not mention(f)]
    if (kept or added) and s and "|" in s[max(0, a - 200):b + 1] and _data_table_row(s, a):
        # a row of a test plan or a state table ("| Normal | 50 | accepted |", "| Pending | payment received | Approved |"): the
        # program's or system's data, its expected and actual outputs and its states, never a verdict on this answer (X6)
        def data(f) -> bool:
            word = s[f.a:f.b].strip(" .,;:|").lower()
            return f.family in ("APPROVE", "STATUS", "OUTCOME", "QUALITY", "CHECK") and f.form in ("fragment", "sentence", "label_after") \
                and word in _DATA_VALUES and not s[f.a:f.b].strip(" .,;:|").isupper()
        kept = [f for f in kept if not data(f)]
        added = [f for f in added if not data(f)]
    if not added and s and any(_is_quote(t) for t in toks) and b - a <= 2000:
        # a quotation or reported words masked as an outside party's: the sentence as written, when it says nothing but an
        # assessment, is one whoever is credited ("Someone on the team said it had been checked and was fine.")
        from .reader import _merge, _tokens, _mark_initials
        raw = _merge(_tokens(s, a, b))
        _mark_initials(raw)
        rw = [t for t in raw if not t.punct]
        attributed = any(t.has("C:src_noun", "C:analysed_text", "C:eval_out") and m > 0 and rw[m - 1].w in (
            "the", "el", "la", "los", "las", "his", "her", "their", "su", "sus", "a", "an", "un", "una") for m, t in enumerate(rw[:12])) and \
            any(t.has("C:report_verb") for t in rw[:14])
        if not attributed:
            from .reader import _pronoun_reporter, _source_before, _ES_REPORT_FINITE
            q0 = next((m for m, t in enumerate(raw) if t.w in _QMARKS or t.raw[:1] in "'\"\u201c\u2018\u00ab"), None)
            # (a pronoun or a dropped subject reporting for the source the sentence before names: "It states: '...'", attack round 5;
            # a third party named by a common noun: "El ministro afirmó: «...»")
            if q0 is not None and q0 > 0 and (_pronoun_reporter(raw[:q0]) and _source_before(s, a) or any(
                    (t.has("C:report_verb") or t.w in _ES_REPORT_FINITE) and m >= 2 and raw[m - 2].has("C:det") and
                    not raw[m - 2].has("C:poss1", "C:demonstrative") and raw[m - 1].w.isalpha() and
                    not raw[m - 1].has("C:genre", "C:genre_strong", "C:part", "C:eval_int", "C:tool", "C:eval_asr", "C:m_eval",
                                       "C:eval_int_agentive", "C:anaph", "C:anchor")
                    for m, t in enumerate(raw[:q0]))):
                attributed = True
        # (a quotation a document or a person of the subject says, "El texto dice: «todo está comprobado»": that party's words)
        if rw and not attributed and not any(_content_at(rw, k, ctx) for k in range(len(rw))) and not _not_a_statement(raw, rw, ctx):
            _k2, add2 = _review(raw, ctx, question, [], found_cls, s, a, b, kind)
            added = add2
    if kept and kind in ("bracket", "cell", "line", "paragraph", "text") and s and kind in ("bracket", "cell"):
        # a metric with its value in brackets inside a sentence about the subject ("... (precision 0.880)"), a process state in a
        # trace table's cell: read with the host line
        ls = s.rfind("\n", 0, a) + 1
        le = s.find("\n", b)
        le = len(s) if le < 0 else le
        if le - ls <= 4000:
            from .reader import _merge, _tokens, _mark_initials
            host = _merge(_tokens(s, ls, le))
            _mark_initials(host)
            hw = [t for t in host if not t.punct]
            inner = [t for t in toks if not t.punct]
            if kind == "bracket" and len(inner) <= 3 and any(x.num for x in inner) and any(
                    x.fam() & {"OUTCOME", "QUALITY", "CHECK", "SRCEVAL"} for x in inner) and \
                    any(_content_at(hw, k, ctx) for k in range(min(len(hw), 40)) if hw[k].a < a):
                kept = [f for f in kept if f.form not in ("fragment", "label_inside")]
            if kind == "bracket" and any(t.w in ("zzmarkpos",) for t in inner):
                pos_in_host = next((m for m, x in enumerate(host) if x.a >= a), None)
                if pos_in_host is not None:
                    m0 = next((m for m in range(pos_in_host, min(len(host), pos_in_host + 4)) if host[m].w == "zzmarkpos"), None)
                    if m0 is not None and _symbol_content(host, m0):
                        kept = [f for f in kept if f.family != "MARK"]
            if kind == "bracket" and any(x.fam() & {"CHECK"} for x in inner) and any(x.has("C:m_method") for x in inner) and \
                    any(x.w in ("=", "≈") for x in host) and sum(1 for x in host if x.num) >= 2:
                kept = [f for f in kept if f.family not in ("CHECK", "STATUS")]  # "(verified by substitution): x = 4, since ..."
            if kind == "cell" and _trace_row(host):
                kept = [f for f in kept if not (f.family in ("QUALITY", "STATUS", "OUTCOME") and _process_state(toks))]
    return kept, added


_CONJ_RE = re.compile(r"\b(?:se\s+conjuga[n]?|conjugaci[oó]n|is\s+conjugated|conjugates|conjugation)\b", re.I)
_PARADIGM_RE = re.compile(r":\s*(?:yo|t[uú]|[eé]l|ella|usted|nosotros|nosotras|vosotros|ellos|ellas|ustedes|I|you|he|she|we|they)\s+"
                          r"[^\s.,;:]+\s*[.;]?\s*$", re.I)
_SIMPLE_Q_RE = re.compile(r"«[^»\n]{1,60}»|“[^”\n]{1,60}”|\"[^\"\n]{1,60}\"|'[^'\n]{1,60}'")


def _paradigm_span(s: str, a: int, b: int):
    """(colon offset, sentence end, quotation spans) when ``s[a:b]`` states a conjugation with a quoted model verb and closes on a
    paradigm form after a colon ("se conjuga como «probar»: yo compruebo"); otherwise None."""
    a = max(s.rfind("\n", 0, a) + 1, a - 400)  # the sentence's line: a label piece of it is read with the statement it ends
    le = s.find("\n", b)
    b = min(len(s) if le < 0 else le, b + 400)
    seg = s[a:b]
    m = _CONJ_RE.search(seg)
    if not m:
        return None
    pm = _PARADIGM_RE.search(seg)
    if not pm or pm.start() < m.end():
        return None
    qs = [(a + q.start(), a + q.end()) for q in _SIMPLE_Q_RE.finditer(seg)]
    if not qs:
        return None
    return a + pm.start(), b, qs


def _clause_parts(toks: list, ctx, question: bool, found_cls, s: str, a: int, b: int, kind: str) -> list:
    """M1 on each clause of a sentence cut at a semicolon or a spaced dash (rule S3; attack round 3): a clause that says nothing but
    an assessment is one wherever it stands, also after content ("From 2x + 3 = 11 we get 2x = 8, so x = 4; a teacher marked this
    right.", "..., so x = 4 - correct, full marks."). A worked CHECK (a check lead before its relation sign: "Check: 2(4) + 3 =
    11 - correct") keeps its verdict as part of the working (X1)."""
    from .reader import _split_parts, _CHECK_LEAD_WORDS
    if question or len(toks) > 400:
        return []
    parts = _split_parts(toks)
    if len(parts) < 2:
        return []
    rel = [k for k, t in enumerate(toks) if t.w in ("=", "\u2248")]
    if rel and any(t.has("C:worked_lead") or t.w in _CHECK_LEAD_WORDS for t in toks[:rel[-1]]):
        return []
    out: list = []
    for part in parts:
        pw = [t for t in part if not t.punct]
        if not pw or not _assessment_of(part):
            continue
        _k, add = _review(part, ctx, question, [], found_cls, s, a, b, kind)
        out += add
    return out


#: Column heads of a program's test plan or a system's state table: the cells under them are data of the subject (X6).
_DATA_HEADS = frozenset(("expected", "actual", "input", "inputs", "test data", "event", "next state", "state", "transition", "output",
                         "outputs", "expected output", "actual output", "expected result", "actual result", "current state",
                         "entrada", "salida", "esperado", "estado siguiente"))


#: The values a program's validation or a system's states take ("accepted", "rejected", "Pass", "Approved"): data, never in
#: the pipeline's capitals ("VERIFIED", "PASS" stay statuses).
_DATA_VALUES = frozenset(("accepted", "rejected", "pass", "passed", "fail", "failed", "approved", "declined", "valid", "invalid",
                          "ok", "true", "false", "shipped", "pending", "complete", "completed", "aceptado", "rechazado", "aprobado",
                          "valido", "correcto", "incorrecto"))


def _data_table_row(s: str, a: int) -> bool:
    """Whether offset ``a`` lies in a row of a markdown table whose header row names data columns (:data:`_DATA_HEADS`) and
    no check or verdict column of the answer's own. Bounded: 64 lines back, 4,000 characters a line."""
    ls = s.rfind("\n", 0, a) + 1
    le = s.find("\n", a)
    le = len(s) if le < 0 else le
    if s[ls:le].count("|") < 2:
        return False
    head = ls
    for _ in range(64):
        if head == 0:
            break
        p0 = s.rfind("\n", 0, head - 1) + 1
        if s[p0:head - 1].count("|") < 2:
            break
        head = p0
    he = s.find("\n", head)
    he = len(s) if he < 0 else he
    cells = [c.strip().lower() for c in s[head:min(he, head + 4000)].split("|") if c.strip()]
    if not any(c in _DATA_HEADS for c in cells) or any(c in ("claim", "claims", "afirmacion", "this answer") for c in cells):
        return False
    return not any(c in ("check", "checks", "verified", "verification", "self-check", "confidence", "my check", "status of this answer")
                   for c in cells)


#: Nouns of statistics and measurement after which "confidence", "validity", "precision" name the subject's own quantity.
_STATS_WORDS = frozenset(("interval", "intervals", "z-test", "t-test", "critical", "significance", "hypothesis", "p-value", "sample",
                          "mean", "standard", "deviation", "test", "z", "t", "chi-squared", "distribution", "estimate", "population",
                          "intervalo", "muestra", "media", "nivel de significacion"))
_TOOLS_OF_CODE = frozenset(("compiler", "compilers", "interpreter", "interpreters", "linter", "linters", "assembler", "assemblers",
                            "type checker", "type-checker", "debugger", "compilador", "interprete"))
_CODE_WORDS = frozenset(("program", "programs", "code", "syntax", "source", "machine", "statement", "statements", "function",
                         "loop", "variable", "printed", "prints", "print", "ran", "runs", "executes", "executed", "compiles", "compiled",
                         "bytecode", "programa", "codigo"))
_EVIDENCE_SUBJECTS = frozenset(("data", "evidence", "results", "figures", "statistics", "findings", "graph", "table", "survey", "census",
                                "observations", "measurements", "readings", "datos", "resultados", "cifras", "evidencias"))
_OPTION_NP_RE = __import__("re").compile(r"^(?:the |la |el )?(?:(?:correct|right|true|best) (?:answer|option|choice|response)|"
                                         r"(?:respuesta|opcion|alternativa) correcta)$")
_OPTION_NOUNS = frozenset(("answer", "option", "choice", "alternative", "response", "statement", "opcion", "respuesta", "alternativa",
                           "eleccion"))


def _subject_frames(toks: list, words: list, segs: list[list], ctx, s: str, a: int, b: int, clear0, frame_spans: list) -> None:
    """Boundary (b) frames of the subjects (attack round 2): assessment words that are the subject matter's own. Each frame clears
    the hits it explains and records its span, so that no sentence-level reading (M1, M2) re-reads the same words as an assessment."""
    def clear(pred, lo: int = -1, hi: int = -1) -> None:
        clear0(pred)
        frame_spans.append((lo, hi) if lo >= 0 else (toks[0].a if toks else 0, toks[-1].b if toks else 0))
    if words and words[0].w in ("in", "en") and len(words) > 2 and words[1].w in ("the", "this", "that", "el", "la", "este", "esta") and \
            words[2].has("C:src_noun", "C:analysed_text") and words[2].w not in ("words", "word", "palabras", "terms", "phrase", "line",
                                                                                 "lines", "label"):
        # "In the source, the editor writes 'all figures verified', ...": the analysed source's own words (boundary (b), 3.6)
        clear(lambda f: f.form in ("quoted", "relayed", "label_after", "label_inside") or f.rule in ("G6", "G7"))
    first_verb = next((k for k, t in enumerate(toks) if t.has("v:3sg", "v:past", "C:aux", "C:copula") or
                       (k > 0 and t.w.endswith("ed") and (t.fam() or not t.t))), None)
    subj = [t for t in toks[:first_verb] if not t.punct] if first_verb else []
    third_party = bool(subj) and any(_content(t, ctx) for t in subj) and not any(
        t.has("C:pron1", "C:poss1", "C:genre", "C:genre_strong", "C:part", "C:eval_int", "C:tool", "C:m_eval", "C:eval_asr",
              "C:anchor", "C:anchor_idioms", "C:demonstrative") for t in subj)
    for k, t in enumerate(toks):
        prev = toks[k - 1] if k > 0 else None
        # a participle clause of a third party's act ("Participants rated their mood, ticking one box per item"): theirs (X3)
        if third_party and t.w.endswith("ing") and (t.fam() & {"CHECK", "SCORE"} or t.has("C:m_tick")) and prev is not None and \
                prev.w == "," and first_verb is not None and k > first_verb:
            clear(lambda f, t=t: t.a <= f.a < t.b + 1 or (f.family in ("CHECK", "MARK") and f.a >= t.a))
        # a check or a score in a relative clause of a subject-matter noun ("Students who scored above 80%"): theirs (X3)
        if (t.fam() & {"CHECK", "SCORE"}) and prev is not None and prev.w in ("who", "that", "which", "que", "quien", "quienes") and \
                k >= 2 and _content(toks[k - 2], ctx) and not toks[k - 2].has("C:genre", "C:part", "C:eval_int", "C:tool"):
            clear(lambda f, t=t: t.a <= f.a < t.b + 1)
    # a generic statement about a kind of tool ("A compiler checks the syntax", "verification tools prove properties of programs"):
    # what such tools do, the subject of Computer Science, never a check of this answer (X3, X22)
    demonstrative_answer = any(t.has("C:demonstrative", "C:poss1") and m + 1 < len(words) and words[m + 1].has(
        "C:genre", "C:genre_strong", "C:part") for m, t in enumerate(words)) or any(t.has("C:anchor", "C:anchor_idioms", "C:pron1")
                                                                                  for t in words)
    if not demonstrative_answer:
        for seg in segs:
            sw = [t for t in seg if not t.punct]
            for m, t in enumerate(sw[:-1]):
                if not (t.has("C:eval_int", "C:tool") or t.w in _TOOLS_OF_CODE):
                    continue
                v = sw[m + 1]
                det = sw[m - 1] if m > 0 else None
                det2 = sw[m - 2] if m > 1 else None
                indefinite = det is not None and (det.w in ("a", "an", "any", "every", "each", "un", "una") or (
                    det2 is not None and det2.w in ("a", "an", "any", "every", "un", "una") and not det.has("C:det")))
                bare_plural = t.w.endswith("s") and (det is None or not det.has("C:det", "C:poss1", "C:poss2", "C:poss3")) and \
                    v.has("v:base") and not v.has("v:past", "v:3sg")
                if (indefinite and (v.has("v:3sg") or (v.w.endswith("s") and v.fam() & {"CHECK", "AGREE"}))) or bare_plural:
                    lo, hi = sw[0].a, sw[-1].b
                    clear(lambda f, lo=lo, hi=hi: lo <= f.a < hi and f.rule in ("G1", "G2", "G3", "G5"), lo, hi + 1)
                    break
        # a compiler or an interpreter at work on a program ("The compiler found no errors, so the program ran and printed 42"): the
        # program's behaviour, the subject matter (X6)
        if any(t.w in _TOOLS_OF_CODE for t in words) and any(t.w in _CODE_WORDS or t.has("C:program_noun") and t.w not in (
                "compiler", "test", "status", "result", "system", "validator") for t in words):
            clear(lambda f: f.rule in ("G1", "G2", "G3", "G5"))
    # the subject's evidence supporting a stated content clause ("The data confirm that rainfall increases with altitude: ..."), X16
    for k, t in enumerate(toks[:-2]):
        if t.fam() & {"CHECK", "AGREE"} and t.has("v:3sg", "v:base") and not t.has("v:past") and toks[k + 1].w in ("that", "que") and \
                k >= 1 and toks[k - 1].w in _EVIDENCE_SUBJECTS and not demonstrative_answer and \
                any(_content(x, ctx) for x in toks[k + 2:k + 12]):
            clear(lambda f, t=t: t.a <= f.a < t.b + 1)
    # "the correct answer/option is B", "la opción correcta es la b": the answer itself stated (material), not an assessment of it
    for k, t in enumerate(words[:6]):
        idiom_np = t.idiom and _OPTION_NP_RE.match(t.w) is not None
        if idiom_np or (t.fam() & {"OUTCOME"} and t.w in ("correct", "right", "correcta", "correcto", "true", "best") and k >= 1 and (
                (k + 1 < len(words) and words[k + 1].w in _OPTION_NOUNS and words[k - 1].w in ("the", "el", "la")) or
                (words[k - 1].w in _OPTION_NOUNS and k >= 2 and words[k - 2].w in ("the", "el", "la")))):
            cop = next((m for m in range(k + 1, min(len(words), k + 4)) if words[m].has("C:copula") or words[m].w in ("is", "es")), None)
            if cop is not None and cop + 1 < len(words):
                val = words[cop + 1:cop + 4]
                if not any(x.has("C:anaph", "C:anchor", "C:anchor_idioms", "C:demonstrative", "C:pron1", "C:genre") and x.w not in (
                        "la", "el", "lo") or _positive(x) or _defect(x) or x.fam() - {"PROVENANCE"} for x in val):
                    # (the value states the answer, "x = 4", "B", "la b"; an assessment word, "is verified", keeps the hit)
                    lo = words[0].a
                    clear(lambda f, lo=lo: True)
            break
    # a label whose key names a measure of the subject and whose value states it with the subject's words ("Validity: high internal
    # validity, low ecological validity", "Precision: 3 significant figures", "Confidence interval: 95%"), not a verdict on the answer
    colon = next((k for k, t in enumerate(toks[:6]) if t.w == ":"), None)
    if colon is not None and colon > 0:
        key = [t for t in toks[:colon] if not t.punct]
        value = [t for t in toks[colon + 1:] if not t.punct]
        kw = [t.w for t in key]
        after = s[b:min(len(s), b + 300)].lower() if s else ""
        stats = any(w in _STATS_WORDS for w in kw) or any(x in after for x in ("critical value", "z-test", "t-test", "interval",
                                                                                "standard deviation", "significance", "p-value"))
        if kw and kw[0].startswith(("confidence", "confianza")) and (stats or kw[0].endswith(("interval", "intervals"))):
            clear(lambda f, c=toks[colon].b: f.a < c or f.family == "CONFIDENCE")
        elif len(key) == 1 and kw[0] in ("validity", "reliability", "precision", "accuracy", "validez", "fiabilidad", "precision") and \
                value and any(_content_at(value, m, ctx) for m in range(len(value))) and not any(
                    x.has("C:pron1", "C:poss1", "C:anchor", "C:anchor_idioms", "C:genre", "C:genre_strong") for x in value):
            clear(lambda f, c=toks[colon].b: f.a < c and f.form in ("label_before", "label_inside", "label_after", "fragment"))


_PROCESS_STATES = frozenset(("complete", "completed", "done", "finished", "ready", "running", "waiting", "terminated", "idle",
                             "blocked", "empty"))


def _process_state(toks: list) -> bool:
    return any(t.w in _PROCESS_STATES for t in toks)


def _trace_row(host: list) -> bool:
    """A table row of three or more cells none of which is meta (a check, an assessment key, the answer, the pipeline)."""
    if sum(1 for t in host if t.w == "|") < 4:
        return False
    return not any(x.has("C:check_noun", "C:assess_key", "C:genre_strong", "C:eval_int", "C:m_check") for x in host)


def _lead_markers(toks: list) -> list:
    """The tokens after leading list, footnote and quotation markers ("[^1]:", "1)", "(a)", "*", ">", "-")."""
    k = 0
    while k < len(toks) and k < 8:
        t = toks[k]
        if t.punct:
            k += 1
            continue
        if (t.num or (len(t.w) == 1 and t.w.isalpha())) and k + 1 < len(toks) and toks[k + 1].w in (")", "]", ".", ":") and \
                (k == 0 or toks[k - 1].punct):
            k += 2
            continue
        break
    return toks[k:]


def _review(toks: list, ctx, question: bool, found: list, found_cls, s: str, a: int, b: int, kind: str) -> tuple[list, list]:
    toks = _lead_markers(toks) or toks
    words = [t for t in toks if not t.punct]
    if not words or len(toks) > 400:
        return found, []
    if len(words) == 1 and words[0].w in ("sat", "unsat") and kind in ("text", "paragraph", "line") and not found and not question:
        # a line that is only a solver's verdict ("sat"): a status, whatever its case (inside a bracket after content, "(sat)" is a
        # past tense on a specialist's branch and a status label on the combinator's)
        return found, [found_cls("G5", "STATUS", "fragment", words[0].a, words[0].b)]
    if not _assessment_of(toks) and not found:
        return found, []
    segs = _segments(toks)
    content = [t for k, t in enumerate(words) if _content_at(words, k, ctx)]
    kept = list(found)
    added: list = []

    # ---- frames that clear a hit (boundary (b)), each on the hits it explains
    def clear(pred) -> None:
        nonlocal kept
        kept = [f for f in kept if not pred(f)]

    # a quotation mentioned or analysed: the hits inside it and on it
    for k in _quote_spans(toks):
        if _mention_quote(toks, k):
            qa, qb = toks[k].a, toks[k].b
            if _is_quote(toks[k]):
                # the q-runs of one masked quotation are one span (its words, its inner stops)
                j0 = k
                while j0 > 0 and (_is_quote(toks[j0 - 1]) or (toks[j0 - 1].punct and toks[j0 - 1].w in ".,;:!?" and j0 > 1 and
                                                               _is_quote(toks[j0 - 2]))):
                    j0 -= 1
                j1 = k
                while j1 + 1 < len(toks) and (_is_quote(toks[j1 + 1]) or (toks[j1 + 1].punct and toks[j1 + 1].w in ".,;:!?" and
                                                                           j1 + 2 < len(toks) and _is_quote(toks[j1 + 2]))):
                    j1 += 1
                qa, qb = toks[j0].a, toks[j1].b
            if toks[k].w in _QMARKS:
                j = k - 1
                while j > 0 and toks[j].w not in _QMARKS:
                    j -= 1
                qa = toks[j].a
            raw_q = s[qa:qb].lower() if s else ""
            if any(x in raw_q for x in ("this answer", "this response", "this essay", "this solution", "esta respuesta",
                                        "this reply", "this synthesis", "the combined answer", "everything above", "all of the above",
                                        "the answer above", "the working above", "the solution above", "the text above")) or (
                    "above" in raw_q and not (_attributed_quote(toks, k, ctx) and _analysed_frame(toks, s, a, b))):
                continue  # an explicit reference to this answer inside a quotation is never masked (design 3.6 (i)); a bare
                # "above" in a quotation credited to a source refers to the source's own figures (attack round 3)
            clear(lambda f, qa=qa, qb=qb: f.a >= qa - 1 and f.b <= qb + 1 or (f.form in ("quoted", "relayed") and qa - 1 <= f.a <= qb))
            clear(lambda f, qa=qa, qb=qb: qa <= f.a < qb)
    for qa, qb in _raw_mentions(s, a, b):
        clear(lambda f, qa=qa, qb=qb: qa <= f.a < qb or (f.form in ("quoted", "relayed") and qa - 1 <= f.a <= qb))
    # a claim that is one quotation of the analysed text with words of the subject in it ('"exactly in the centre"', '"I say the
    # weather. I say it will be fine."'): evidence quoted, read by the channel's quotation checks, no assessment of the answer
    if s and b - a <= 2000:
        whole = s[a:b].strip()
        if len(whole) >= 3 and whole[0] in "\"\u201c\u2018'\u00ab" and whole.rstrip(".").endswith(("\"", "\u201d", "\u2019", "'", "\u00bb")):
            inner = whole[1:].rstrip(".").rstrip("\"\u201d\u2019'\u00bb")
            if not any(q in inner[1:] for q in "\"\u201c\u201d") and not any(x in inner.lower() for x in (
                    "this answer", "this response", "above", "esta respuesta", "this synthesis", "the combined answer")):
                from .reader import _merge, _tokens
                itoks = [t for t in _merge(_tokens(s, a, b)) if not t.punct]
                own = any(t.has("C:anchor", "C:anchor_idioms") or (t.has("C:poss1") and m + 1 < len(itoks) and itoks[m + 1].has(
                    "C:part", "C:genre", "C:genre_strong", "C:content_key")) for m, t in enumerate(itoks))
                # (an unattributed quotation of the answer's own parts, "my table", "the working here", is the writer's own words)
                if not own and any(_content_at(itoks, m, ctx) for m in range(len(itoks))) and not any(
                        t.has("C:eval_int", "C:tool", "C:m_eval") for t in itoks):
                    clear(lambda f: True)
    # attack round 7 frames (boundary (b)), each clears the hits it explains
    for f_pred in _round7_frames(toks):
        clear(f_pred)
    # a check mark used as a symbol of the subject
    for k, t in enumerate(toks):
        if t.w in ("zzmarkpos", "zzmarkneg") and content and _symbol_content(toks, k):
            clear(lambda f, t=t: f.family == "MARK" and f.a <= t.a < max(f.b, f.a + 1) or (f.family == "MARK" and f.a == t.a))
    # agreement with a named subject-matter reference
    for k, t in enumerate(toks):
        if (t.fam() & {"AGREE", "FIDELITY"} or t.w in ("matches", "matching", "match", "agrees", "agree", "coincide", "coincides")) \
                and _reference_agreement(toks, k) and not any(
                    x.has("C:anchor_idioms") or (x.has("C:demonstrative", "C:poss1") and m + 1 < k and toks[m + 1].has("C:genre_strong"))
                    for m, x in enumerate(toks[:k])):
            # (X7 needs a specific theme: "This answer is as accurate as the extract" makes the whole answer its theme, boundary (a))
            clear(lambda f, t=t: f.family in ("AGREE", "FIDELITY", "CHECK") and f.a <= t.a < max(f.b, t.a + 1))
            # an attributive participle naming the reference ("matches the accepted figure for g", "the established value"): the
            # reference's name, no approval of this answer (attack round 5)
            for m in range(k + 1, min(len(toks) - 1, k + 4)):
                if toks[m].has("v:part", "adj") and toks[m].fam() & {"APPROVE", "STATUS", "CHECK"} and toks[m - 1].has("C:det") and \
                        not toks[m + 1].punct:
                    clear(lambda f, x=toks[m]: f.a <= x.a < max(f.b, x.a + 1))
    # the subject's own uses of assessment words
    for k, t in enumerate(toks):
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        prev = toks[k - 1] if k > 0 else None
        own = False
        if t.has("v:3sg", "v:base", "v:past") and t.fam() & {"OUTCOME"} and t.w.startswith(("hold", "held", "work", "stand", "stood")) \
                and nxt is not None and not nxt.punct and _content(nxt, ctx) or (
                nxt is not None and nxt.has("C:det") and t.w.startswith(("hold", "held")) and k + 2 < len(toks) and _content(toks[k + 2], ctx)):
            own = True  # "which holds rain on the surface": a verb with a subject-matter object
        if prev is not None and (prev.has("C:det", "C:prep", "C:neg") or prev.w in ("no", "in", "of")) and nxt is not None and \
                not (nxt.w.endswith(("ed", "en", "wn", "ght")) and k + 2 < len(toks) and toks[k + 2].has("C:prep")) and \
                not (prev.w in ("this", "these", "my", "our", "este", "esta", "mi", "nuestro", "nuestra") and (
                    nxt.w in ("one", "ones", "version", "versions") or nxt.has("C:genre", "C:genre_strong", "C:part"))) and \
                not nxt.punct and _content(nxt, ctx) and t.has("adj", "v:part", "v:base") and not t.has("C:part") and \
                t.fam() & {"CHECK", "APPROVE", "STATUS", "QUALITY", "OUTCOME"} and not t.fam() & {"SCORE"} and \
                t.w not in ("correct", "right", "accurate", "verified", "checked", "approved") or (
                prev is not None and prev.w in ("no",) and t.w in ("approved", "verified", "checked") and nxt is not None and
                _content(nxt, ctx)):
            own = True  # an attributive word of a subject-matter noun ("in moderate storms", "no approved source for")
        if t.idiom and t.w.split()[-1] in ("answer", "answers", "respuesta", "respuestas") and t.fam() & {"OUTCOME"} and prev is not None and \
                (prev.has("C:dist", "C:indefinite") or prev.w in ("each", "every", "per", "a", "an", "cada", "una", "un", "for")):
            own = True  # "for each correct answer", "a right answer scores 1" (attack round 5): a kind of answer of the subject (a quiz,
            # a game, a test), no verdict on this one
        if t.fam() & {"OUTCOME", "QUALITY", "STATUS", "APPROVE", "CHECK"} and prev is not None and prev.w in _QMARKS and k >= 2 and (
                toks[k - 2].has("C:output_verb") or toks[k - 2].w in ("prints", "print", "printed", "displays", "display", "displayed",
                                                                        "outputs", "output", "returns", "return", "returned", "shows",
                                                                        "echoes", "imprime", "muestra", "devuelve")):
            own = True  # "prints 'Correct!'", "displays 'Valid'": a program's output, the subject's (X6)
        if (k == 0 or all(x.punct for x in toks[:k])) and t.has("v:part", "adj") and t.fam() & {"CHECK", "APPROVE", "STATUS"} and \
                nxt is not None and not nxt.punct and _content(nxt, ctx) and not nxt.has("C:part", "C:genre", "C:genre_strong") and \
                nxt.w not in ("by", "por", "and", "y", "as", "como") and (any(
                    x.has("C:copula", "C:aux", "C:deontic", "v:3sg") or (x.has("v:past") and not x.fam()) for x in toks[k + 2:k + 8]) or
                    _finite_any(toks, k + 2, k + 8)) and \
                not any(x.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1") for x in toks):
            own = True  # "Certified organic status allows ...", "Tested samples were stored ...", "Proven reserves are ..." (attack round
            # 5): a participle naming a kind of the subject's thing, the subject of the sentence's verb, no check of this answer
        if t.fam() & {"OUTCOME", "QUALITY", "CHECK"} and nxt is not None and nxt.num and prev is not None and prev.w in ("(", ",") and \
                any(_content(x, ctx) for x in toks[:k]):
            own = True  # a metric with its value inside a sentence about the subject ("(precision 0.880)", "(recall 0.917)")
        if t.w in ("works", "work", "worked") and prev is not None and not prev.punct and content and \
                not prev.has("C:anaph", "C:pron1", "C:genre", "C:genre_strong", "C:anchor", "C:anchor_idioms", "C:part"):
            own = True  # "that the app works": the subject's own outcome, in a sentence about the subject
        if t.w in ("marked", "marks", "mark", "marking") and any(x.w in ("as", "como") for x in toks[k + 1:k + 5]) and \
                not any(x.fam() & {"OUTCOME", "QUALITY", "SCORE"} for x in toks[k + 1:k + 7]):
            own = True  # "marked as the body of an essay", "marks its figures as 'from memory'": a designation
        if t.w in ("mark", "marks") and prev is not None and prev.w in ("answer", "method", "accuracy", "reasoning", "communication",
                                                                         "working", "follow-through", "ft"):
            own = True  # an allocation's name ("the method mark", "both answer marks"): markscheme vocabulary (X12)
        if t.w in ("pass", "passes") and prev is not None and (prev.has("C:det", "C:dist") or prev.w in ("each", "every", "first",
                                                                                                    "second", "third", "last", "one",
                                                                                                    "next", "final")):
            own = True  # "at the start of each pass": a noun of the subject (a pass of a loop)
        if k == 0 or (k > 0 and all(x.punct for x in toks[:k])):
            nx = next((x for x in toks[k + 1:k + 3] if not x.punct and x.w not in ("then", "also", "thus", "therefore", "now")), None)
            nx_i = toks.index(nx) if nx is not None else -1
            verbal = nx is not None and (nx.has("v:3sg") or (nx.w.endswith("s") and nx_i + 1 < len(toks) and toks[nx_i + 1].has("C:det"))) \
                and not nx.has("C:dist", "C:det", "lang:es") and nx.w not in ("todas", "todos")
            if nx is not None and verbal and not nx.has("C:copula", "C:aux") and content and \
                    t.fam() & {"QUALITY", "OUTCOME"} and not t.fam() & {"CHECK", "STATUS", "APPROVE"}:
                own = True  # "Sound then makes the constraint perceptible.": a noun subject of the subject's own verb
        if t.fam() & {"CHECK"} and t.has("v:3sg", "v:past") and k > 0 and content and not toks[k - 1].punct:
            subj = [x for x in toks[max(0, k - 5):k] if not x.punct]
            if subj and not any(x.has("C:copula", "C:aux") or x.num for x in subj) and not any(x.has("C:pron1", "C:poss1", "C:eval_int", "C:tool", "C:eval_int_agentive", "C:m_eval", "C:eval_asr",
                                      "C:anaph", "C:genre", "C:part", "C:check_noun") for x in subj) and _content(subj[-1], ctx) and \
                    not _answer_object(toks, k):
                own = True  # "The Bennets' dialogue tests this logic": a subject-matter agent's act (X3); a check of THIS answer by a
                # named outside party ("Wikipedia confirms every figure in this response.") is no act of the subject (c3c)
        if t.w in ("exactly", "verbatim", "exactamente") and nxt is not None and nxt.w in ("as", "como") and any(
                x.has("C:report_verb", "C:descr") or x.w in ("gives", "give", "gave", "states", "stated", "writes", "wrote", "reports",
                                                            "reported", "lists", "listed", "da", "dice")
                for x in toks[k + 2:k + 8]) and any((x.cap and not x.init) or x.has("C:eval_int_agentive", "C:eval_out") for x in toks[k + 2:k + 7]):
            own = True  # X8: values relayed "exactly as the Chemistry specialist gives them": the relay's fidelity, checked by the channel
        if (t.fam() & {"FIDELITY", "OUTCOME"} or t.w in ("exactly", "verbatim")) and nxt is not None and nxt.w in ("as", "como") and \
                k + 2 < len(toks) and toks[k + 2].w in ("printed", "written", "given", "quoted", "spelt", "spelled", "in", "it",
                                                          "they", "the", "impreso", "escrito") and \
                any(x.w in ("word", "phrase", "quotation", "quote", "line", "term", "palabra", "frase", "cita", "figure", "value")
                    for x in toks[max(0, k - 6):k]):
            own = True  # X8: the fidelity of a specific quotation ("the word is given exactly as printed"), material
        if not own and t.fam() & {"OUTCOME", "DEFECT", "QUALITY"} and _language_judgement(toks, k, s):
            own = True  # a grammar judgement of a quoted or named language item ("'are' is incorrect", "lo correcto es «...»")
        if own:
            clear(lambda f, t=t: t.a <= f.a < t.b + 1 and f.rule != "G9")  # (the hits whose trigger is this word, never a label's)
    # a leading participle clause ("Checked against the table of critical values, χ² = 2.1 is below 3.841, ...", "Comprobada la
    # hipótesis, los investigadores publicaron ...", attack round 5): its check belongs to the main clause after it, a worked comparison
    # that shows its figures (material, X1) or a third party named as the main clause's subject (X3)
    if len(segs) >= 2:
        s0 = [t for t in segs[0] if not t.punct]
        s1 = [t for t in segs[1] if not t.punct]
        if s0 and s1 and len(s0) <= 10 and s0[0].has("v:part", "adj") and s0[0].fam() & {"CHECK", "APPROVE", "STATUS"} and \
                not any(x.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1", "C:eval_int", "C:tool") and not (
                    x.w in ("below", "above") and m + 1 < len(s0 + s1) and (s0 + s1)[m + 1].num) for m, x in enumerate(s0 + s1)):
            rel = any(x.w in ("=", "<", ">", "\u2264", "\u2265", "\u2248", "below", "above", "exceeds", "exceed", "less", "greater",
                              "under", "over", "menor", "mayor", "supera", "inferior", "superior") for x in segs[1])
            worked = rel and sum(1 for x in s1 if x.num) >= 2 and s0[1:2] and s0[1].w in ("against", "with", "using", "con", "frente",
                                                                                         "contra", "mediante")
            third = len(s1) >= 3 and s1[0].has("C:det") and (_content(s1[1], ctx) or s1[1].has("C:eval_out")) and \
                not s1[1].has("C:part", "C:genre", "C:genre_strong") and _finite_any(s1, 2, 5)
            if worked or third:
                lo, hi = s0[0].a, s0[-1].b
                clear(lambda f, lo=lo, hi=hi: lo <= f.a < hi)
    frame_spans: list = []
    _subject_frames(toks, words, segs, ctx, s, a, b, clear, frame_spans)
    for f_pred, span in _c3c_frames(toks, ctx):
        clear(f_pred)
        if span is not None:
            frame_spans.append(span)
    # a check by a stated mathematical method with the computation shown (X1/X4: "verified by substitution: 2(4) + 3 = 11")
    if any(t.w in ("=", "≈") for t in toks) and sum(1 for t in toks if t.num) >= 2:
        for k, t in enumerate(toks):
            if t.fam() & {"CHECK"} and any(x.has("C:m_method") for x in toks[k + 1:k + 4]):
                clear(lambda f, t=t: f.a <= t.a < max(f.b, t.a + 1))
    # a subject's outcome: an outcome whose subject is a subject-matter noun ("the code is correct")
    for k, t in enumerate(toks):
        if t.fam() & {"OUTCOME"} and t.has("adj") and k >= 2 and toks[k - 1].has("C:copula"):
            lo = k - 1
            while lo > 0 and k - lo < 12 and not (toks[lo - 1].punct and toks[lo - 1].w in (",", ";", ":", "(")):
                lo -= 1
            subj = [x for x in toks[lo:k - 1] if not x.punct]
            # (a Spanish free relative on the writer's own writing, "lo que he escrito", is the writer's text: attack round 6)
            own_rel = any(x.w == "que" and m + 1 < len(subj) and subj[m + 1].w in ("he", "hemos") for m, x in enumerate(subj))
            if subj and _content(subj[-1], ctx) and not own_rel and not any(
                    x.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1", "C:genre_strong", "C:demonstrative") for x in subj):
                clear(lambda f, t=t: f.a <= t.a < max(f.b, t.a + 1))
    # a COMPLY verb whose object is restricted to a subject-matter domain ("covers every item in the current account")
    for k, t in enumerate(toks):
        if t.has("C:comply_verb"):
            obj = toks[k + 1:k + 10]
            if any(x.w in ("in", "of", "en", "de") for x in obj) and any(_content(x, ctx) and not x.has("C:request_noun") and
                                                                        x.w not in ("request", "question", "task", "prompt", "brief")
                                                                        for x in obj):
                clear(lambda f, t=t: f.family == "COMPLY" and f.a <= t.a < max(f.b, t.a + 1))
    # a label: its key and value
    colon = next((k for k, t in enumerate(toks[:10]) if t.w == ":"), None)
    if colon is not None and colon > 0:
        key = [t for t in toks[:colon] if not t.punct]
        value = [t for t in toks[colon + 1:] if not t.punct]
        key_w = " ".join(t.w for t in key)
        if _nonsuccess(value) and len(value) <= 6:
            clear(lambda f: True)  # "Engine status: UNKNOWN (timeout)": a non-success status shown as one
        if key and (key[0].has("C:worked_lead") or key[0].w in ("check", "checking", "checks", "comprobacion", "verification") or
                    key_w.startswith(("check,", "check for", "for checking", "to check"))) and value and \
                not (_positive(value[0]) and not _content_at(value, 0, ctx)) and not value[0].w.startswith("zz"):
            if any(_content(x, ctx) for x in value) or any(x.w in ("=", "≈", ":") for x in toks[colon + 1:]) or sum(
                    1 for x in value if x.num) >= 2:
                # a worked check that shows its content (material for the engine): the check word is the working's label
                clear(lambda f: f.form in ("label_before", "label_inside", "fragment", "sentence") and f.a < toks[colon].b and
                      f.rule in ("G2", "G4", "G5", "G6"))
                clear(lambda f: f.family in ("AGREE", "CHECK", "STATUS", "MARK") and f.rule in ("G2", "G3", "G5", "G6"))
        if key_w.startswith(("for checking", "for reference", "to check", "para comprobar", "for comparison")):
            clear(lambda f: f.a < toks[colon].b)
        if key and _imperative(value, ctx) and not any(x.fam() & {"ASSURE", "APPROVE"} for x in value):
            clear(lambda f: f.a > toks[colon].a)  # "Fix it: 1) Correct the facts first.": a method step under a key
    # an instruction (a method step) in a clause
    for seg in segs:
        sw = [t for t in seg if not t.punct]
        if sw and _imperative(seg, ctx) and not any(x.fam() & {"ASSURE", "APPROVE"} for x in sw):
            a, b = sw[0].a, sw[-1].b
            clear(lambda f, a=a, b=b: a <= f.a < b)
    # a process state in a trace table ("| 4 | P4 | 6 | 8 | 0, complete |"): a row of three or more cells, none of them meta
    if sum(1 for t in toks if t.w == "|") >= 4:
        cells, cur = [], []
        for t in toks:
            if t.w == "|":
                if cur:
                    cells.append(cur)
                cur = []
            else:
                cur.append(t)
        if cur:
            cells.append(cur)
        if len(cells) >= 3 and not any(x.has("C:check_noun", "C:assess_key", "C:genre", "C:eval_int") for c in cells for x in c):
            clear(lambda f: f.family in ("QUALITY", "STATUS", "OUTCOME") and toks[0].a <= f.a and any(
                x.w in ("complete", "completed", "done", "finished", "ready", "running", "waiting", "terminated", "idle")
                and x.a <= f.a < x.b + 1 for x in toks))
    # a generic or definitional statement (no first person, no answer anchor)
    anchored = any(t.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1") for t in words)
    if not anchored:
        ws = [t.w for t in words]
        generic = False
        if any(w in ("often", "usually", "typically", "generally", "normally", "commonly", "frequently", "tend", "tends", "suele",
                     "suelen", "generalmente") for w in ws):
            generic = True
        if any(t.w in ("process", "proceso", "method", "metodo", "procedure", "procedimiento", "way", "forma") for t in words) and any(
                t.w in ("by which", "por el que", "por la que", "whereby", "in which", "en el que", "that", "que", "by", "por") for t in words):
            if any(x.has("C:copula") for x in words[:6]):
                generic = True  # "La revisión por pares es el proceso por el que ...": a definition
        if words and words[0].w in ("in", "en") and len(words) > 1 and words[1].w.isupper() is False and words[1].raw[:1].isupper() and \
                any(t.w in ("a", "an", "un", "una") for t in words[2:5]):
            generic = True  # "In CS, a test suite that passes ...": a statement of the field
        if words[0].raw[:1].isupper() and words[0].raw[1:].islower() and words[0].w.isalpha() and len(words[0].w) <= 16 and \
                words[0].w.endswith("s") and _content(words[0], ctx) and not words[0].has("C:det") and \
                len(words) > 1 and not words[1].has("C:det", "C:prep", "C:copula", "C:aux", "v:past", "v:3sg") and \
                not words[1].w.endswith(("s", "ed")) and words[1].w.isalpha():
            generic = True  # "Respondents answer by ticking ...": a bare plural in the generic present (X22)
        if words[0].has("C:indefinite") and words[0].w in ("a", "an", "un", "una") and not any(t.has("C:eval_int", "C:tool") for t in words[:4]) \
                and any(_content(t, ctx) for t in words[:5]):
            generic = True
        if generic:
            # (a source evaluation the reader kept is a pronoun taking up the sentence's own statement, "Schemas shape what people
            # recall; this is fully reliable.": the writer's confidence in its generic claim stays its own; check round 9 of c3c)
            clear(lambda f: f.rule in ("G1", "G2", "G3", "G5") and f.family not in ("ASSURE", "SRCEVAL"))
    # the respondents of a study ("Respondents answer by ticking (✓) one box per item."): third parties' act
    # ---- polarity and mood over the whole sentence (content-free sentences)
    readings = []
    for m, seg in enumerate(segs):
        if not _assessment_of(seg):
            continue
        sign, pos, dfc, negated = _polarity(seg)
        mood = _mood_of(seg, question, m == 0)
        sw = [t for t in seg if not t.punct]
        if sw and _imperative(seg, ctx) and not any(x.fam() & {"ASSURE", "APPROVE"} for x in sw):
            mood = "imperative"
        if any(x.fam() & {"CHECK"} and x.has("v:3sg", "v:es3", "v:base") and any(y.w in ("whether", "if", "si") for y in sw[q + 1:q + 3])
               for q, x in enumerate(sw)) and not any(x.has("C:pron1", "C:poss1", "C:eval_int", "C:tool") for x in sw):
            # a method that checks WHETHER something holds ("Replication confirms whether a finding is reliable.", "La prueba de
            # hipótesis verifica si la diferencia es significativa."): an indirect question of the subject, nothing asserted
            mood = "question"
        if m > 0 and sw and sw[0].w in ("when", "while", "as", "cuando", "mientras", "al") and \
                any(x.has("V:finding") or x.fam() & {"CHECK"} for x in sw) and \
                any(x.has("C:null_result") for x in segs[m - 1]) and not any(_assessment_of([x]) for x in segs[m - 1]
                                                                          if not x.has("C:null_result")):
            # "The solver came up empty when it hunted for a counterexample to anything written here." (attack round 7): a search
            # that came up empty denies what it searched for, the clause of the search is negated by the result before it
            sign, negated = -sign, True
        readings.append((sign, pos, dfc, negated, mood, seg))
    if readings and segs:
        s0 = [t for t in segs[0] if not t.punct]
        if s0 and s0[0].w in ("once", "after", "when", "until", "before", "upon", "cuando", "tras", "hasta") and len(segs) > 1 and any(
                x.w in ("can", "could", "will", "would", "may", "might", "should", "must", "'ll", "shall", "podra", "podran", "puede",
                        "pueden", "debe", "deben", "sera", "seran") for g in segs[1:] for x in g):
            # "Once reviewed, this answer can be marked as final.", "After the tests run, the results will be reported": a pending
            # condition of a future or possible act, no check reported
            readings = [(r[0], r[1], r[2], r[3], "protasis" if r[5] is segs[0] else (
                "weak" if any(x.w in ("can", "could", "will", "would", "may", "might", "should", "must", "'ll", "shall", "podra",
                                      "podran", "puede", "pueden", "sera", "seran") for x in r[5]) and not any(
                    x.fam() & {"ASSURE", "CONFIDENCE"} for x in r[5]) else r[4]), r[5]) for r in readings]
    cf = _counterfactual(segs)
    if content and all(_name_like(t) for t in content) and _evaluator_names(words, content):
        content = []  # a product or model name credited with a check of this ("ChatGPT confirmed this."): an evaluator, no content
    if content and len(content) <= 2 and all(t.has("C:eval_out", "C:eval_asr", "C:generic_role") for t in content) and \
            any(t.has("C:anchor_idioms") or (t.has("C:anchor") and any(x.has("C:genre_strong") for x in words)) for t in words):
        content = []  # an outside body credited with an assessment of this answer named as such ("El tribunal dio por buena esta
        # respuesta."): the answer is the theme (design X2: with an A theme it is gated), the body names no subject matter
    content_free = not content and len(words) >= 1 and not _not_a_statement(toks, words, ctx) and \
        not (kind == "cell" and len(words) <= 3 and not any(x.has("upper") or x.w.startswith("zz") or x.fam() & {"STATUS", "SCORE"}
                                                            for x in words))
    if content_free and ctx.marking:
        # in a marking task an evaluation of a work speaks of the student's work (theme T); the writer's own process (a check, a
        # status, an approval, an internal evaluator) and the writer's own marks stay its own
        own = any(t.has("C:pron1", "C:poss1") for t in words) or any(
            t.has("C:demonstrative") and any(x.has("C:assess_instrument", "C:marking_own") or x.w in ("marking", "grading")
                                              for x in words[k + 1:k + 4]) for k, t in enumerate(words))
        # ("this mark scheme application", "these marks": the writer's own marking, in its own words)
        def _score_key(seg: list, m: int) -> bool:
            # "Grade: 7", "Mark: 5/6": a score label's key, the student's score in a marking task, no act of the writer's
            return seg[m].w in _SCORE_KEYS and m + 1 < len(seg) and seg[m + 1].w == ":"
        readings = [r for r in readings if own or any(((x.fam() & {"CHECK", "STATUS"} or (x.fam() & {"APPROVE"} and not
                                                                                           x.fam() & {"QUALITY"})) and not x.has("prod") or
                                                        x.has("C:m_check", "C:eval_int", "C:tool", "C:m_eval")) and not _score_key(r[5], m)
                                                       for m, x in enumerate(r[5]))]
    readings = [r for r in readings if not _narrative_past(r[5]) and not _system_generic(r[5]) and not _subject_constraints(r[5])
                and not _ambiguous_agent(r[5])]
    asserted_pos = [r for r in readings if r[0] > 0 and (r[1] or (r[2] and r[3])) and r[4] in ("declarative", "strong")]
    others = [r for r in readings if r not in asserted_pos]
    # protasis readings that precede a positive apodosis belong to it (the counterfactual), handled by cf
    if content_free:
        if cf or asserted_pos:
            seg = asserted_pos[0][5] if asserted_pos else segs[0]
            trig = next((t for t in seg if _positive(t) or _defect(t)), words[0])
            if not kept:
                added.append(found_cls("G8" if cf and not asserted_pos else "G1", "CHECK", "sentence", trig.a, trig.b))
        elif readings and all(r[4] in ("question", "protasis", "imperative", "weak") or r[0] < 0 for r in readings) and \
                any(r[0] < 0 or r[4] in ("weak", "imperative") for r in readings) and not _internal_result(words):
            es_sentence = _spanish(toks)
            clear(lambda f: (f.rule not in ("G7", "G8", "G9") or (f.rule == "G9" and es_sentence)) and
                  f.form not in ("quoted", "relayed"))
    else:
        # content around the assessment: the answer as the subject (M2)
        if not kept:
            hit = _answer_subject(toks, segs, ctx, question)
            if hit is None:
                hit = _recheck_headline(segs, question)
            if hit is not None:
                added.append(found_cls("G1", "CHECK", "sentence", hit.a, hit.b))
        # a negated or uncertain check on the answer's parts (an outside party's or nobody's) stays out
        if kept and readings and not asserted_pos and all(r[0] < 0 or r[4] in ("weak", "question", "imperative", "protasis")
                                                          for r in readings) and any(r[3] or r[4] == "weak" for r in readings) and \
                not _internal_result(words):
            # (a source evaluation the reader kept takes up the sentence's own statement in a clause of its own: a purpose or a
            # question in the statement, "A firm can use surveys to test demand; this is fully reliable.", leaves the writer's
            # confidence in it asserted; check round 9 of c3c)
            clear(lambda f: f.rule in ("G1", "G2", "G3", "G5", "G9") and f.form not in ("quoted", "relayed") and
                  not (f.family == "SRCEVAL" and _srceval_clause_asserted(toks, f)))
    if not kept and not added:
        trig = _rhetorical_verdict(toks, words, segs, question)
        if trig is not None:
            added.append(found_cls("G8", "CHECK", "sentence", trig.a, trig.b))
    if frame_spans and added:
        added = [f for f in added if not any(lo <= f.a < hi for lo, hi in frame_spans)]
    if not kept and not added and not question:
        lab = _label_on_content(toks)
        if lab is not None:
            added.append(found_cls("G6", "STATUS", "label_before", lab.a, lab.b))
    if kept and _outside_evidence_check(words):
        # a value confirmed BY outside evidence in a sentence that credits a named source ("The IPCC's report states that ... about
        # 1.1 °C ..., a figure confirmed by several independent datasets."; check round 9 of c3c): evidence about the subject
        # matter (boundary (b)), not a check of this answer
        kept = [f for f in kept if not (f.family == "CHECK" and f.rule in ("G1", "G2", "G3", "G5"))]
    if (kept or added) and _marking_criterion(words):
        # what marking rewards or what a good answer does in general ("Marks are awarded for a clear argument.", "A good answer would
        # compare the two sources."; check round 9 of c3c): a criterion, said of no answer in particular
        kept = [f for f in kept if not (f.rule in ("G1", "G2", "G3", "G5") and f.family in ("QUALITY", "OUTCOME", "CHECK", "SCORE"))]
        added = [f for f in added if not (f.rule in ("G1", "G2", "G3", "G5") and f.family in ("QUALITY", "OUTCOME", "CHECK", "SCORE"))]
    return kept, added


_EVIDENCE_AGENTS = frozenset("data dataset datasets studies study measurements observations records surveys survey experiments "
                              "experiment trials analyses research estimates satellite satellites stations".split())


def _outside_evidence_check(words: list) -> bool:
    """A check credited, by "by", to outside evidence (datasets, studies, measurements) in a sentence that names its source with a
    report verb, and with no anchor, first person, tool or internal evaluator: the source's figure, confirmed by evidence."""
    if any(t.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1", "C:eval_int", "C:tool", "C:genre_strong", "C:eval_asr")
           for t in words):
        return False
    if not any(t.has("C:report_verb") or t.w in ("states", "stated", "reports", "reported", "estimates", "estimated", "finds",
                                                   "found", "shows", "showed") for t in words):
        return False
    for m, t in enumerate(words):
        if t.fam() & {"CHECK"} and m + 1 < len(words) and words[m + 1].w in ("by", "por"):
            np = words[m + 2:m + 6]
            if any(x.w in _EVIDENCE_AGENTS for x in np):
                return True
    return False


_CRITERION_NOUNS = frozenset("answer answers response responses essay essays argument arguments candidate candidates student students "
                             "conclusion conclusions respuesta respuestas ensayo ensayos".split())
_CRITERION_MODALS = frozenset("would should will must might could can tends tend needs need usually often typically debe deben "
                              "deberia deberian suele suelen".split())
_AWARD_SUBJECTS = frozenset("marks mark points credit puntos".split())
_AWARD_VERBS = frozenset("awarded given gained earned lost deducted available otorgan otorgados dan".split())


def _srceval_clause_asserted(toks: list, f) -> bool:
    """Whether the clause holding the source-evaluation hit ``f`` (after the last ";", ",", ":" or dash before it) is a plain
    declarative with no negation, modal or question of its own."""
    lo = 0
    for k, t in enumerate(toks):
        if t.a >= f.a:
            break
        if t.punct and t.w in (";", ",", ":", "—", "–"):
            lo = k + 1
    clause = [t for t in toks[lo:] if t.a < f.b and not t.punct]
    return bool(clause) and not any(_neg_word(t) or t.has("C:weak", "C:weak_idioms", "C:deontic") or t.w in (
        "might", "may", "could", "would", "should", "if", "whether", "si", "?") for t in clause)


def _marking_criterion(words: list) -> bool:
    """A general statement of what marking rewards or what a good answer does: "Marks are awarded for ...", "Credit is given
    for ...", "A good answer would/should ...", "Strong responses compare ...". An anchor, the first person, a demonstrative or a
    possessive keeps the sentence about this answer."""
    if not words or any(t.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1", "C:demonstrative", "C:eval_int", "C:tool")
                        or (t.w.split() or [""])[0] in ("this", "these", "here", "your", "my", "our", "esta", "este", "above",
                                                         "below") for t in words):
        return False
    ws = [t.w for t in words]
    if ws[0] in _AWARD_SUBJECTS and len(ws) > 2 and ws[1] in ("are", "is", "were", "can", "may", "will", "se") and \
            any(w in _AWARD_VERBS for w in ws[1:4]) and ("for" in ws[2:6] or "para" in ws[2:6] or "por" in ws[2:6]):
        return True
    if ws[0] in ("a", "an", "un", "una") or (ws[0].endswith("s") and words[0].raw[:1].isupper()):
        head = next((m for m in range(min(len(ws), 5)) if ws[m] in _CRITERION_NOUNS), None)
        if head is not None and head + 1 < len(ws) and ws[head + 1] in _CRITERION_MODALS:
            return True
    return False


_RHET_WH = frozenset(("who", "what", "quien", "que", "how", "como"))
_MODALS = frozenset(("could", "can", "would", "might", "podria", "puede", "podrian", "pueden", "cannot", "couldn't"))
_DOUBT_VERBS = frozenset(("doubt", "question", "fault", "dispute", "challenge", "argue", "quibble", "criticise", "criticize", "dudar",
                          "objetar", "criticar", "discutir", "cuestionar", "poner en duda", "find fault", "fault it"))
_COMPARATIVE = frozenset(("more", "better", "mas", "mejor", "mejores", "any more", "less wrong"))
_ELLIPSIS_AUX = frozenset(("does", "do", "did", "has", "have", "is", "are", "was", "were", "will", "can"))


def _answer_scope(xs: list) -> bool:
    return any(x.has("C:demonstrative", "C:anchor", "C:anchor_idioms") or x.w in ("mine", "ours", "this one", "these ones", "esta",
                                                                              "este", "estas", "estos") for x in xs)


def _rhetorical_verdict(toks: list, words: list, segs: list[list], question: bool):
    """Three sentence frames that assert a positive verdict on the answer without a positive word in the assertion (attack round
    5): a rhetorical question of doubt about the answer ("Who could doubt these numbers?", "¿Quién podría dudar de estas cifras?"),
    a negated comparison with the answer ("No answer could be more accurate than this one."), and a hedge cancelled by an elliptic
    denial ("This may contain errors, but it does not."). The trigger token, or None."""
    if len(words) < 3 or len(words) > 40:
        return None
    ws = [t.w for t in words]
    if question and ws[0] in _RHET_WH and any(w in _MODALS for w in ws[1:3]):
        k = next((m for m in range(1, min(len(words), 5)) if words[m].w in _DOUBT_VERBS or words[m].has("C:m_doubt") or
                  (words[m].has("defectverb") or "DEFECT" in words[m].fam()) and words[m].has("v:base")), None)
        if k is not None and _answer_scope(words[k + 1:k + 5]) and not any(_neg_word(x) for x in words[1:k]):
            return words[k]
    if not question and words[0].w in ("no", "nothing", "none", "nobody", "ningun", "ninguna", "ninguno", "nada", "nadie"):
        k = next((m for m in range(1, min(len(words), 8)) if words[m].w in _COMPARATIVE), None)
        if k is not None and k + 1 < len(words):
            pos = words[k].w in ("better", "mejor", "mejores") or _positive(words[k + 1])
            than = next((m for m in range(k + 1, min(len(words), k + 4)) if words[m].w in ("than", "que")), None)
            if pos and than is not None and _answer_scope(words[than + 1:than + 4]):
                return words[k]
    if not question and len(segs) >= 2:
        for m in range(1, len(segs)):
            sw = [t for t in segs[m] if not t.punct]
            core = [t for t in sw if t.w not in ("but", "yet", "and", "pero", "though", "however")]
            if 2 <= len(core) <= 3 and core[-1].w in ("not", "n't") and core[-2].w in _ELLIPSIS_AUX or (
                    len(core) == 2 and core[-1].w in ("doesn't", "don't", "didn't", "isn't", "aren't", "hasn't", "haven't")):
                prev = [t for t in segs[m - 1] if not t.punct]
                if any(_defect(t) for t in prev) and any(t.has("C:weak") or t.w in ("may", "might", "could") for t in prev) and \
                        not any(_neg_word(t) for t in prev):
                    return core[-1]
    return None


def _finite_any(toks: list, a: int, b: int) -> bool:
    from .reader import _finite
    # (an unknown word in -s before a determiner is a present verb: "status allows the farm")
    return any(not toks[m].punct and (_finite(toks, m, subject_seen=True) or (
        not toks[m].t and toks[m].w.isalpha() and toks[m].w.endswith("s") and not toks[m].w.endswith("ss") and m + 1 < len(toks) and
        toks[m + 1].has("C:det")) or (toks[m].w.isalpha() and len(toks[m].w) > 5 and toks[m].w.endswith(("aron", "ieron", "aban")))
    ) for m in range(a, min(b, len(toks))))


def _name_like(t) -> bool:
    """A name written as a product or a model is: an acronym in capitals or a CamelCase word ("GPT", "ChatGPT")."""
    raw = t.raw
    return raw.isalpha() and ((raw.isupper() and len(raw) >= 2) or _camel(raw))


def _evaluator_names(words: list, names: list) -> bool:
    """The names are the subject of a check, agreement or approval whose theme is this answer or its parts (an anaphor, a
    distributive part, an anchor), never "the figures" (an outside source's check of the subject's figures is evidence, X2)."""
    first = next((k for k, t in enumerate(words) if t.fam() & {"CHECK", "AGREE", "APPROVE", "STATUS"}), None)
    if first is None or any(words.index(n) > first for n in names):
        return False
    after = [t for t in words[first + 1:] if not t.has("C:prep") and t.w not in ("with", "to", "on")]
    if not after:
        return True
    t0 = after[0]
    if any(words.index(n) > 0 and words[words.index(n) - 1].w in ("the", "el", "la") for n in names):
        return False  # "The ONS confirmed ...": an institution named with its article, an outside source (X2)
    return t0.has("C:anaph", "C:dist", "C:dist_idioms", "C:anchor", "C:anchor_idioms") and t0.w not in ("the", "these", "those") or \
        (t0.has("C:demonstrative", "C:poss1") and t0.w not in ("these", "those") and len(after) > 1 and after[1].has("C:genre"))


def _not_a_statement(toks: list, words: list, ctx) -> bool:
    """Lines that state nothing about the answer: a heading or a lead-in (ends with a colon, a question or part heading, a mark
    allocation "[7 marks]"), a markscheme line (X11), a content key with a truth value (X10, "Final answer: correct."), a model
    answer described for a question ("a model answer for a 6-mark question")."""
    last = next((t for t in reversed(toks) if not (t.punct and t.w in (".", "!", ")", "]", "*"))), None)
    if last is not None and last.w == ":":
        return True
    w0 = words[0].w
    if w0 in ("question", "part", "section", "pregunta", "parte", "award", "accept", "do not accept", "step", "paso", "task") or \
            (w0 in ("m1", "a1", "r1", "b1")):
        return True
    if any(t.has("C:according") for t in words[:3]) and not any(t.has("C:eval_int", "C:tool", "C:m_eval", "C:pron1", "C:poss1")
                                                                 for t in words[:8]):
        return True  # "According to the official press release, ...": an outside source's report (X2), not the answer's
    if words[0].w in ("hence", "therefore", "thus", "so") and any(t.w in ("proved", "proven", "shown", "established", "demonstrated")
                                                                  for t in words[1:8]):
        return True  # "Hence both results are proved.": a derivation's conclusion (X13, X14)
    if len(words) <= 6 and words[0].w in ("the", "this") and len(words) > 2 and (words[1].has("C:part", "C:reasoning_noun") or
                                                                                 words[1].w in ("theorem", "lemma", "identity")) and \
            not words[1].w.endswith("s") and words[2].has("C:copula") and len(words) > 3 and \
            words[3].w in ("proved", "proven", "shown", "established", "demonstrated") and len(words) == 4:
        return True  # "The result is proved.": a derivation's statement of its own conclusion (X13)
    if len(words) <= 6 and (words[0].has("C:dist", "C:dist_idioms") or words[0].w in ("every", "each", "all")) and \
            not any(t.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1") for t in words) and \
            any(t.w in ("exact", "precise", "valid", "consistent", "complete", "exactly") for t in words) and \
            not any(t.w in ("correct", "right", "accurate", "true", "error-free", "verified", "checked") for t in words):
        return True  # "Every value is exact.": a property of the subject's values (no rounding), no verdict on the answer
    if len(words) <= 6 and words[0].w in ("the", "this") and len(words) > 2 and words[1].w in (
            "data", "evidence", "results", "experiment", "study", "survey", "graph", "table", "trend", "census") and \
            words[2].fam() & {"CHECK", "AGREE"} and words[2].has("v:3sg", "v:past"):
        return True  # "The data confirms it.": the subject's evidence supporting a point (X16), no check of the answer
    if not any(t.has(*_OWN_SCOPE_TAGS[:4], "C:eval_int", "C:tool", "C:anaph", "C:demonstrative", "C:dist", "C:dist_idioms") or
               t.w.startswith("zz") or (t.has("C:part", "C:genre", "C:genre_strong") and k > 0 and
                                        words[k - 1].w in ("the", "this", "these", "my", "our", "la", "el", "esta", "este", "mi"))
               for k, t in enumerate(words)) and not any(t.has("v:part", "C:perfect_aux", "v:past") for t in words):
        # a generic statement about assessment, in the present ("The examiner awards marks for evaluation.", "In the IB, a 7 is the
        # highest grade.", attack round 7): an assessor or a score of the subject's practice, no claim about this answer
        v = next((k for k, t in enumerate(words) if t.has("v:3sg", "C:copula") or t.has("C:aux", "C:would_modal", "C:future_modal",
                                                                                         "C:ability_modal", "C:weak")), None)
        present = v is not None and v > 0 and (words[v].w in ("is", "are", "es", "son") or (words[v].has("v:3sg") and
                                                                                          not words[v].has("C:aux")))
        if present and (any(t.has("C:eval_asr") for t in words[:v]) or words[0].w in ("a", "an", "un", "una") or
                        any(t.w in ("a 7", "a seven", "un 7", "un siete") for t in words[:v])):
            return True
    if len(words) > 3 and words[0].w in ("the", "this", "la", "el") and words[1].w in ("case study", "case", "estudio de caso") and \
            any(t.w in ("shows", "states", "says", "suggests", "indicates", "reports", "muestra", "indica", "dice") for t in words[1:4]):
        return True  # "The case study shows that the data are reliable." (attack round 7): the case study's report, an outside source
    if any(t.w in ("fue", "fueron", "salio", "salieron", "went", "go", "goes") for t in words) and words[-1].w in ("bien", "well", "smoothly"):
        return True  # "Todo fue bien.", "It went well.": an event that went well (narrative), no verdict on the answer
    for k, t in enumerate(words):
        if t.w in ("mark", "marks", "marcas", "puntos") and k > 0 and words[k - 1].num:
            return True  # an allocation "(1 mark)", "[7 marks]" (X12)
        if t.w in ("model answer", "a model answer") and k + 1 < len(words) and words[k + 1].w in ("for", "to", "of", "para"):
            return True
    colon = next((k for k, t in enumerate(toks[:10]) if t.w == ":"), None)
    if colon is not None:
        key = [t for t in toks[:colon] if not t.punct]
        value = [t for t in toks[colon + 1:] if not t.punct]
        if key and any(t.has("C:assess_instrument") for t in key) and value and value[0].w in ("accept", "award", "do not accept", "allow",
                                                                                              "reject", "credit", "aceptar"):
            return True  # "Mark scheme: accept any answer that is verified by substitution.": the markscheme's text (X11)
        if key and key[-1].has("C:content_key") and len(value) <= 2 and any(x.has("C:truth_value") for x in value):
            return True
    return False


_SYSTEM_NOUNS = frozenset(("delivery", "deliveries", "transmission", "transmissions", "exchange", "exchanges", "turn", "turns",
                           "request", "requests", "message", "messages", "handoff", "handoffs", "entrega", "entregas"))


def _system_generic(seg: list) -> bool:
    """A statement of how the system works, never of this answer: a hypothetical ("would carry a signed engine result") or a
    generic over the system's deliveries ("Each delivery has a signed receipt."), or the no-change idiom with no re-run in it."""
    words = [t for t in seg if not t.punct]
    for k, t in enumerate(words[:-1]):
        if t.w in ("would", "'d", "could", "might") and (words[k + 1].has("V:bearer") or words[k + 1].w in ("carry", "bear", "have",
                                                                                                           "get", "receive")):
            if not any(x.fam() & {"OUTCOME", "QUALITY", "SCORE", "ASSURE"} for x in words):
                return True
    if words and words[0].w in ("each", "every", "all", "any", "cada", "toda", "todas") and len(words) > 1 and words[1].w in _SYSTEM_NOUNS:
        return True
    flat = " ".join(t.w for t in words)
    if flat in ("nothing changes", "nothing changed", "no change", "nada cambia"):
        return True
    return False


_AMBIGUOUS_AGENTS = frozenset(("overseer", "overseers", "hub", "router", "translator", "auditor", "auditors"))


def _internal_result(words: list) -> bool:
    """A result credited to the pipeline or a tool, whatever its polarity ("The engine found the two dates inconsistent."): an engine
    or system result is never the answer's to state, so no negation clears it (an act denied, "the engine did not run", is no
    result)."""
    for k, t in enumerate(words[:-1]):
        if t.has("C:eval_int", "C:tool") and len(t.w) > 2 and t.w not in _AMBIGUOUS_AGENTS:
            nxt = words[k + 1]
            if (nxt.has("V:finding", "V:report_back", "C:report_verb") or nxt.fam() & {"CHECK", "STATUS"}) and nxt.has("v:past", "v:3sg"):
                return True
    return False


def _ambiguous_agent(seg: list) -> bool:
    """"The overseer approved it.": a name the subjects share with the pipeline (a plantation overseer, a railway hub) acting on "it"
    is the subject matter's agent (design 3.5), never a check of this answer."""
    words = [t for t in seg if not t.punct]
    for k, t in enumerate(words[:-1]):
        if t.w in _AMBIGUOUS_AGENTS and words[k + 1].fam() and k + 2 < len(words) and words[k + 2].w in ("it", "them") and \
                k + 3 == len(words):
            return True
    return False


def _subject_constraints(seg: list) -> bool:
    """"All the constraints are satisfied.": the definite constraints of a problem the answer solves, stated as a result in a full
    clause (no anchor to the answer); a status fragment ("All constraints satisfied.") or an anchored one stays a self-report."""
    words = [t for t in seg if not t.punct]
    v = next((k for k, t in enumerate(words) if t.has("C:copula", "C:aux")), None)
    if v is None or v == 0:
        return False
    subj = words[:v]
    if any(t.w in ("of", "de", "del") for t in subj) and any(t.w in ("question", "task", "prompt", "brief", "pregunta", "tarea", "consigna")
                                                          for t in subj):
        return False  # "Every requirement of the question is met in full." (attack round 7): the request's own requirements, met by
        # the answer that responds to it
    return any(t.w == "the" for t in subj) and subj[-1].has("C:request_noun") and \
        not any(t.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1", "C:demonstrative") for t in words)


def _narrative_past(seg: list) -> bool:
    """D4: a simple past check of a definite part ("The figures were checked.", "The checks passed the inspection."): narrative,
    unless a present status, an outcome, a prefix, a signal or an internal evaluator says more."""
    words = [t for t in seg if not t.punct]
    if not words or words[0].w not in ("the", "los", "las", "el", "la"):
        return False
    if len(words) < 2 or not (words[1].has("C:part", "C:check_noun") or (len(words) > 2 and words[2].has("C:part", "C:check_noun"))):
        return False
    if any(t.has("C:present_aux", "C:perfect_aux", "prefix", "C:signal_idioms", "C:eval_int", "C:tool", "C:m_eval", "C:eval_asr",
                 "C:anchor", "C:anchor_idioms", "C:dist", "C:dist_idioms") or t.w in _SIGNAL_WORDS for t in words):
        return False
    if any(t.fam() & {"OUTCOME", "QUALITY", "AGREE", "SCORE", "CONFIDENCE"} and not t.w.startswith(("pass",)) or t.has("C:m_pos") and
           not t.w.startswith(("pass",)) for t in words):
        return False
    return any(t.has("C:past_aux") or t.has("v:past") for t in words)


_SIGNAL_WORDS = frozenset("again twice independently myself ourselves thrice separately".split())


def _synthesis_word(t) -> bool:
    return t.has("C:combinator_genre") or any(x in t.w for x in ("synthesis", "syntheses", "combined", "merged", "sintesis"))


def _recheck_headline(segs: list[list], question: bool) -> Optional[object]:
    """A verbless headline of a repeated check ("Stoichiometry double-checked; ...", "Totals re-verified against the table."): a check
    the writer repeated on its own work, whatever it names; an auxiliary ("was double-checked by the ONS") makes it a clause, read
    by the compositional reader."""
    if question:
        return None
    for seg in segs[:4]:
        sw = [t for t in seg if not t.punct]
        if not sw or len(sw) > 10 or any(t.has("C:aux", "C:copula") or t.w in ("by", "por") for t in sw):
            continue
        for m, t in enumerate(sw[1:5], start=1):
            if t.fam() & {"CHECK"} and t.has("v:part", "v:past") and (t.has("prefix") or t.w.startswith((
                    "double-", "cross-", "triple-", "re-", "recheck", "reverif", "reconfirm")) or any(
                    x.w in _SIGNAL_WORDS for x in sw[m + 1:m + 3])):
                if not any(x.has("C:imperative_verbs") and x.has("v:base") for x in sw[:1]) and not sw[0].has("C:det", "C:pron3"):
                    return t
    return None


#: Words that open a clause after a bare verdict word in front of the content ("CORRECT If x > 2 ...").
_CLAUSE_OPENERS = frozenset(("if", "the", "this", "these", "so", "since", "because", "let", "for", "given", "a", "an", "it", "there",
                             "then", "when", "we", "i", "si", "el", "la", "los", "las", "como", "dado", "sea"))


def _label_on_content(toks: list) -> Optional[object]:
    """A verdict word glued in front of content with no mark between, its next word opening a clause in capitals ("CORRECT If x > 2
    and y > x then y > 2.", a stylised or look-alike "correct If ..."): a label on the content (G6)."""
    words = [t for t in toks[:3]]
    if len(words) < 2 or words[0].punct or words[1].punct:
        return None
    t, nx = words[0], words[1]
    if not (t.fam() & {"OUTCOME", "STATUS", "APPROVE"} or (t.fam() & {"CHECK"} and t.has("v:part"))) or t.has("C:genre", "C:part"):
        return None
    if not nx.raw[:1].isupper() or not (nx.w in _CLAUSE_OPENERS or (len(nx.w) == 1 and nx.w.isalpha())):
        return None
    if t.raw[:1].isupper() and t.raw[1:2].islower() and nx.w in ("the", "a", "an", "el", "la", "los", "las"):
        return None  # a title in title case ("Correct The Errors"): the next word would be lower case in a label on content
    return t


def _answer_subject(toks: list, segs: list[list], ctx, question: bool) -> Optional[object]:
    """M2: the answer (a genre noun with this/my/our/an anchor, its of-phrase naming what it is about) or a stated part of it
    (these/the + a part noun with at most two modifiers, no outside owner, no date) as the subject of a positive check, outcome or
    quality, asserted; the predicate runs on over coordinated clauses ("has been reviewed and is the correct interpretation")."""
    if question:
        return None
    all_words = [t for t in toks if not t.punct]
    if all_words and _not_a_statement(toks, all_words, ctx):
        return None
    for i_seg, seg in enumerate(segs[:3]):
        sw = [t for t in seg if not t.punct]
        if len(sw) < 3:
            continue
        # (a verb idiom of the families is a verb too: "ties back", "adds up", "checks out", attack round 5)
        v = next((k for k, t in enumerate(sw) if t.has("C:aux", "C:copula") or (k > 0 and t.has("v:3sg", "v:past") and t.fam()) or (
            k > 0 and t.idiom and t.parts and t.fam() & {"AGREE", "OUTCOME", "QUALITY"} and
            t.parts[0].w.endswith(("s", "ed")) and not t.parts[0].w.endswith("ss"))), None)
        rel_own = None
        if v is not None and v >= 2 and sw[v - 1].has("C:pron1") and sw[v - 2].has("C:part", "C:genre") and not sw[v].has("C:aux", "C:copula"):
            # a relative clause with the writer as subject ("The grid references I gave are exact."): the writer's own items, and the
            # main verb comes after it (attack round 3)
            rel_own = v - 1
            v = next((k for k in range(v + 1, min(len(sw), v + 4)) if sw[k].has("C:aux", "C:copula")), None)
        if v is None or v == 0 or v > 10:
            continue
        subj = sw[:rel_own] if rel_own is not None else sw[:v]
        pred = sw[v:]
        for nxt in segs[i_seg + 1:i_seg + 3]:
            nw = [t for t in nxt if not t.punct]
            if nw and nw[0].w in ("and", "y", "e"):
                if _polarity(nw)[0] < 0:
                    # a conjunct with its own negation ("..., and it has not been checked"): a negated assessment of its own,
                    # never a second negation of the first clause
                    break
                pred = pred + nw[1:]
            else:
                break
        k_of = next((k for k, t in enumerate(subj) if t.w in ("of", "de", "del")), None)
        core = subj[:k_of] if k_of else subj
        if not core:
            continue
        if any(t.has("C:pron2", "C:poss2", "C:pron3", "C:poss3", "C:eval_out", "C:month") or t.num or (t.cap and not t.init) or
               t.has("poss") for t in core):
            continue
        if k_of and any(t.num or t.has("C:month", "C:pron2", "C:poss2") for t in subj[k_of:]):
            continue
        head = core[-1]
        if head.has("C:anchor") and len(core) >= 2:
            head = core[-2]  # "the map reading above": the noun before its anchor
        det = core[0]
        if head.idiom and head.parts:
            # a merged quantifier and noun ("every step"): its last word is the head, its first the determiner
            det = head.parts[0] if len(core) == 1 else det
            head = head.parts[-1]
        if (head.has("C:combinator_genre") or any(_synthesis_word(x) for x in subj)) and getattr(ctx, "writer", "specialist") != "combinator":
            continue  # "This synthesis" on a specialist's branch: the subject's (a chemical synthesis), never the answer
        answer = (head.has("C:genre", "C:genre_strong") and (det.has("C:demonstrative", "C:poss1") or det.w in ("this", "my", "our")) and
                  head.w not in ("arguments", "interpretations", "readings", "views", "models", "methods")) or \
            any(t.has("C:anchor_idioms") for t in subj) or (head.has("C:genre", "C:genre_strong", "C:part") and
                                                             any(t.has("C:anchor") for t in subj))
        part = head.has("C:part") and det.w in ("these", "this", "the", "estas", "estos", "esta", "este") and len(core) <= 4
        if rel_own is not None and head.has("C:part", "C:genre"):
            answer = True
        if head.has("C:part") and (det.has("C:dist", "C:dist_idioms") or det.w in ("every", "each", "all", "cada", "todos", "todas")) and \
                len(core) <= 4 and not any(x.w in ("in", "of", "from", "en", "de") for x in subj):
            answer = True  # a distributive over the answer's parts with no outside restrictor ("every step", "all the figures"): A
            unanchored = not any(x.has("C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1") for x in subj + pred)
            if any(x.w in (("exact", "precise", "valid", "complete", "consistent", "clear", "exactly", "precisely") if unanchored else
                           ("exact", "exactly", "precise", "precisely")) for x in pred) and \
                    not any(x.w in ("correct", "right", "accurate", "true", "error-free") for x in pred) and not any(
                    x.fam() & {"CHECK", "STATUS", "APPROVE"} for x in pred):
                continue  # "Every value (above) is exact.": a property of the values (no rounding), no verdict on the answer
        if not (answer or part):
            continue
        colon_at = next((x.a for x in seg if x.w == ":" and x.a > sw[v].a), None)
        pred_head = [x for x in pred if colon_at is None or x.a < colon_at]  # (what a colon introduces is the matter proved, not a complement)
        if any(x.w in ("for", "when", "whenever", "if", "provided", "para", "cuando", "si", "in", "under", "within", "en") and
               m + 1 < len(pred_head) and any(_content_at(pred_head, q, ctx) for q in range(m + 1, min(len(pred_head), m + 4)))
               for m, x in enumerate(pred_head)):
            continue  # X18: "holds for n = 2", "is correct when x > 0", "are exact in this model": a complement of the subject
        if any(x.w in ("can", "could", "may", "might", "will", "would", "shall", "must", "should", "puede", "podra") for x in pred[:3]) and \
                not any(x.fam() & {"ASSURE", "CONFIDENCE"} for x in pred):
            continue  # "this answer can be marked as final", "will be reviewed": a possible or future act, no assessment made
        whole = subj + pred
        sign, pos, dfc, negated = _polarity(whole)
        mood = _mood_of(whole, question, True)
        if sign < 0 or mood not in ("declarative", "strong"):
            continue
        sub_at = next((m for m, x in enumerate(pred) if m > 0 and x.w in ("before", "after", "until", "once", "when", "if", "unless", "antes",
                                                                            "despues", "cuando", "si")), len(pred))
        pred_b = [_base(t) for t in pred[:sub_at]]  # (a subordinate clause, "before it is accepted", is no co-predicate of the subject)
        check = [t for t in pred_b if t.fam() & {"CHECK"} and t.has("v:part", "v:past") and not t.has("prod") or t.has("C:m_check")]
        outcome = [t for m, t in enumerate(pred_b) if t.fam() & {"OUTCOME", "QUALITY", "STATUS", "AGREE"} and not t.has("C:part", "prod")
                   and t not in check and not (t.w in ("exact", "precise", "valid", "complete", "consistent", "whole", "clear") and
                                               m + 1 < len(pred_b) and not pred_b[m + 1].punct and pred_b[m + 1].has("C:part", "noun"))]
        # ("is an exact value", "a complete list": a kind of value or list named, no verdict; "the correct interpretation" stays one)
        prefixed = [t for t in check if t.has("prefix") or t.w.startswith(("cross-", "double-", "re-", "triple-"))]
        if any(x.w in ("by", "por", "in", "en") for x in pred) and any(x.has("C:eval_out") or x.num or (x.cap and not x.init) or
                                                                   x.has("C:month") for x in pred):
            continue  # an outside party's or a dated check (X2, X3)
        k_acc = next((m for m, x in enumerate(toks) if x.w in ("according to", "segun", "as per")), None)
        if k_acc is not None and k_acc + 1 < len(toks) and not any(
                x.has("C:eval_int", "C:tool", "C:eval_asr", "C:pron1", "C:poss1", "C:anchor", "C:anchor_idioms", "C:m_eval")
                for x in toks[k_acc + 1:k_acc + 6]):
            continue  # a named outside source credited ("..., according to the tourist office"): its figures, cited (attack round 5)
        if head.has("C:reasoning_noun") and any(x.w in ("by", "in", "when", "where", "because", "as", "por", "en") and m + 1 < len(pred) and
                                                any(_content_at(pred, q, ctx) for q in range(m + 1, min(len(pred), m + 4)))
                                                for m, x in enumerate(pred)):
            continue  # X16: "My reading is confirmed by the final stanza": evidence for an argument, no assessment
        if sw[0].w in ("hence", "therefore", "thus", "so") and not outcome:
            continue  # "Hence both results are proved.": a derivation's conclusion (X13, X14)
        dist_part = head.has("C:part") and (det.has("C:dist", "C:dist_idioms") or det.w in ("every", "each", "all", "cada", "todos", "todas"))
        present_passive = any(x.w in ("is", "are", "es", "son") for x in pred[:2]) and check and not outcome and \
            not any(x.has("C:anchor", "C:anchor_idioms") for x in subj + pred)
        if dist_part and present_passive:
            continue  # "Every item is inspected before dispatch.": a procedure in the generic present (X22), no check reported
        active_check = [x for m, x in enumerate(pred[:3]) if x.fam() & {"CHECK"} and x.has("v:past", "v:3sg", "v:part") and
                        (x.has("v:3sg") or (m > 0 and pred[m - 1].w in ("has", "have", "had")))]
        if answer and active_check and not outcome:
            at = pred.index(active_check[0])
            obj = pred[at + 1:at + 5]
            first = obj[0] if obj else None
            if first is not None and ((first.cap and (first.has("poss") or first.w.endswith(("'s", "s'")))) or
                                      (_content_at(pred, at + 1, ctx) and not first.has("C:anaph", "C:part", "C:genre"))):
                continue  # "This essay has tested Taylor's claim against the evidence": what the essay does with its subject
        if answer and (check or outcome):
            return (check or outcome)[0]
        if part and check and (outcome or prefixed or any(x.w in ("found", "shown", "proved", "proven") for x in pred)):
            return check[0]
    return None
