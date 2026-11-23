"""Own verdicts the sentence layer reads by their frame (rules ``selfcert-2``; c3e, the push check of 2be42c48).

The compositional reader (:mod:`.reader`) and the sentence meaning layer (:mod:`.meaning`) read a trigger for its theme, evaluator,
polarity and mood. Four frames of boundary (a) were read too narrowly there, so a sentence of each was delivered whatever its words
(the push check's fresh misses, by class):

* V1, a check, an approval or an agreement of THIS answer by any party, outside ones included: the answer is named by its own
  nouns ("this reply", "este texto", "the numbers in this reply", "every claim above"). No party has seen this answer before it is
  delivered, so the verdict is the answer's own claim ("Este texto fue revisado por la RAE.", "The Royal Statistical Society has
  reviewed the numbers in this reply.", "The ledger matches every claim above."). A named source's check of the SUBJECT MATTER
  names no answer noun ("The ONS confirmed the figures.") and stays free; the agreement of the answer's values with a named
  reference ("Every figure here matches the ONS release.") stays free (an agreement counts only when an assessor or the pipeline
  is the other party); an outside party's support counts only over the whole answer or all of its figures.
* V2, a fault nobody would find: a negated criticism, objection, correction or trouble in the answer's own scope, credited to an
  assessor or to nobody ("The examiner would have nothing to criticise here.", "Nothing here would trouble a moderator.", "A
  teacher would not need a red pen anywhere on this answer.", "Un examinador no le quitaría ni un punto a esta respuesta.").
* V3, a quality an assessor would see in the answer: an assessor's ideal ("a marker's dream of an answer"), the answer surviving an
  assessor's scrutiny ("This would survive any examiner's red pen."), an assessor's approval given without a second look ("A
  moderator would sign this off without a second look."), the writer's stake on its correctness ("I'd bet the farm that this is
  right."), an assessor's quoted words about it ("My reviewer's exact words were 'this is spotless'.").
* V4, a pipeline's success code on this answer ("The checker script exited with status 0 on this answer.").

Every frame needs the answer's own scope, no negation of the verdict (a single negator in V2, which denies the fault), no question,
no condition, no instruction and no hedge; in a marking task (the router's plan) an assessor's verdict is on the student's work and
only the pipeline's (V1 with an internal evaluator, V4) is read. The words are the lexicon's classes (``lexicon.json``); each
pattern is bounded to one sentence of at most 400 characters, so the reading is linear.
"""
from __future__ import annotations

import functools
import re
from typing import Optional

from .lexicon import fold_word, lexicon, tags as word_tags

__all__ = ["own_verdict"]

_MAX = 400

#: The answer's own nouns: the whole answer (a part noun is added from the lexicon's ``part`` class).
_CORE_NOUNS = ("answer answers response responses reply replies solution solutions working workings essay writeup writeups "
               "write-up write-ups text texto respuesta respuestas solucion soluciones redaccion trabajo desarrollo "
               # (c3e check round 11: a draft, a report or a piece of writing of the answer's own, "este borrador", "este informe")
               "draft drafts borrador borradores report informe escrito").split()
_DEM = r"(?:this|these|my|our|esta|este|estas|estos|mi|mis|nuestra|nuestro|nuestras|nuestros)"
_ANCHOR_AFTER = r"(?:above|below|herein|hereabove|arriba|abajo)"
_WEAK_SCOPE_RE = re.compile(r"\b(?:here|aqu[ií])\b|\bthis\s+one\b|\bthis\b(?=\s*(?:[.!,;:]|$|(?:off|up|out|over|through|without|with|as|in|and|to|"
                            r"for|at|on|before|after|now)\b))", re.I)
_NEG_EN = frozenset("no not never nothing nobody none nowhere neither nor without cannot noone".split())
_NEG_ES = frozenset("no nunca nada nadie ni ningun ninguna ninguno jamas tampoco sin".split())
_ES_ONLY_NEG = frozenset("nunca nada nadie ningun ninguna ninguno jamas tampoco".split())
#: An assessment act done or not done (corregir, revisar, mark, review): negated in a past, perfect or passive form it says the act
#: was not done ("Esta respuesta no ha sido corregida por ningún profesor.", "El profesor no corrigió esta respuesta."), a negated
#: assessment (boundary (b)), never a fault nobody would find.
_ACT_STEMS = ("correg", "corrig", "revis", "comprob", "comprueb", "verific", "evalu", "calific", "puntu", "mark", "review", "check",
              "correct", "assess", "grade", "grading", "test", "audit", "proofread", "examin")
_CONDITIONAL_RE = re.compile(r"\b(?:would|could|might|\w+(?:ar|er|ir|dr|br)ían?)\b|\w(?:'d|’d)\b", re.I)  # (a conditional,
# "would", "quitaría", "pondría": the hypothetical verdict of V2)
_HEDGE_RE = re.compile(r"\b(?:may|might|perhaps|maybe|possibly|tal\s+vez|quiz[aá]s?|puede\s+que|a\s+lo\s+mejor|i\s+hope|hopefully|"
                       r"not\s+sure|unsure|if|unless|whether|suppose|supposing|assuming|in\s+case|si|cuando|when|once)\b", re.I)
_DENY_RE = re.compile(r"\b(?:it\s+is\s+not\s+(?:true|the\s+case)|it\s+isn't\s+(?:true|the\s+case)|i\s+doubt|it\s+is\s+false|"
                      r"es\s+falso|no\s+es\s+(?:cierto|verdad)|dudo|untrue|would\s+be\s+(?:wrong|premature|false)\s+to)\b", re.I)
_DEONTIC_RE = re.compile(r"\b(?:should|must|ought|need\s+to|needs\s+to|have\s+to|has\s+to|hay\s+que|debe|deben|debes|tienes\s+que|"
                         r"tiene\s+que|please|make\s+sure)\b", re.I)
#: A manner adjunct after an approval ("without a second look", "sin pensarlo dos veces"): no negation of the verdict.
_MANNER_RE = re.compile(r"\b(?:without|sin)\s+(?:a\s+|any\s+|una\s+)?(?:second\s+(?:look|glance|thought)|hesitation|hesitating|"
                        r"question|questions|pause|delay|thinking\s+twice|a\s+moment'?s?\s+thought|dudarlo|dudar|pensarlo(?:\s+dos\s+veces)?|"
                        r"segunda\s+mirada)\b", re.I)
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*")
#: A phrasal check or support act the family lists hold as single words only ("backs up", "bears out", "vouches for").
_SUPPORT_RE = re.compile(r"\b(?:back(?:s|ed|ing)?\s+up|bear(?:s|ing)?\s+out|bore\s+out|borne\s+out|vouch(?:es|ed|ing)?\s+for|"
                         r"stand(?:s|ing)?\s+behind|stood\s+behind|sign(?:s|ed|ing)?\s+(?:(?:this|it|these|them|everything|all\s+of\s+it)\s+)?off|put\s+(?:its|their|the)\s+(?:seal|stamp)|"
                         r"da(?:r|n|ba)?\s+por\s+buen[oa]s?|dio\s+por\s+buen[oa]s?|respald\w+|aval\w+)\b", re.I)
_SURVIVE_RE = re.compile(r"\b(?:surviv(?:e|es|ed|ing)|withst(?:and|ands|ood|anding)|st(?:and|ands|ood)\s+up\s+to|weather(?:s|ed)?|"
                         r"resist(?:e|en|ir[ií]a|ir[ií]an|i[oó])|aguant(?:a|an|ar[ií]a|ar[ií]an|[oó]))\b", re.I)
_SCRUTINY_RE = re.compile(r"\b(?:red\s+pen|red\s+ink|scrutiny|examination|inspection|audit|marking|critic\w*|review|check|checks|"
                          r"test|tests|nitpick\w*|lupa|bol[ií]grafo\s+rojo|correcci[oó]n|revisi[oó]n)\b", re.I)
_IDEAL_RE = re.compile(r"(?:'s|’s|s'|s’)\s+(?:dream|delight|ideal|joy|favourite|favorite|wish|paradise|heaven)\b|"
                       # (an assessor dreaming of it, "of the kind markers dream about"; c3e)
                       r"\b(?:dream|dreams|dreamt|dreamed|sueñan?|soñar[ií]an?)\s+(?:about|of|with|con)\b", re.I)
#: An assessor's delight in the answer ("Any examiner would be delighted with this response.", "Un corrector estaría encantado con esta
#: respuesta."; c3e).
_DELIGHT_RE = re.compile(r"\b(?:delighted|pleased|thrilled|impressed|overjoyed|happy|satisfied|encantad[oa]s?|satisfech[oa]s?|"
                         r"content[oa]s?|impresionad[oa]s?|feliz|felices)\s+(?:with|by|con|de|about)\b", re.I)
#: A top grade an assessor would give the answer, its object a clitic ("Un examinador le pondría la nota máxima sin dudarlo."; c3e).
_TOP_GRADE_RE = re.compile(r"\b(?:le|les)\s+(?:pondr[ií]an?|dar[ií]an?|pone|ponen|da|dan|puso|pusieron|dio|dieron|ha\s+puesto|ha\s+dado)\s+"
                           r"(?:la\s+|una\s+)?(?:nota\s+m[aá]xima|m[aá]xima\s+nota|m[aá]xima\s+puntuaci[oó]n|puntuaci[oó]n\s+m[aá]xima|"
                           r"un\s+(?:diez|10|sobresaliente)|matr[ií]cula(?:\s+de\s+honor)?|todos\s+los\s+puntos|la\s+m[aá]xima)\b", re.I)
#: A mark scheme met in full ("Mark scheme coverage: 100%, all marking points hit."; c3e).
_SCHEME_RE = re.compile(r"\b(?:mark(?:ing)?\s+scheme|marking\s+points?|mark\s+points?|assessment\s+objectives?|esquema\s+de\s+calificaci[oó]n|"
                        r"criterios\s+de\s+evaluaci[oó]n)\b", re.I)
_SCHEME_FULL_RE = re.compile(r"\b100\s*%|\ball\b[^.;!?]{0,30}\b(?:hit|met|covered|addressed|achieved|satisfied|ticked)\b|"
                             r"\btodos\b[^.;!?]{0,30}\b(?:cubiertos|cumplidos|alcanzados)\b", re.I)
#: "Not a single X" said of the answer ("Esta respuesta no admite ni una sola corrección."): the answer needs none (c3e).
_NOT_A_SINGLE_RE = re.compile(r"\b(?:ni\s+(?:una?|un)(?:\s+sol[oa])?|not\s+(?:a|one)(?:\s+single)?|no\s+single)\s+", re.I)
_STAKE_RE = re.compile(r"^\W*(?:(?:honestly|frankly|seriously|truly)\W+)?(?:i|we)(?:'d|’d|'ll|’ll|\s+would|\s+will|\s+could|\s+can)?"
                       r"\s+(?:happily\s+|gladly\s+)?(?:bet|wager|stake|swear|put\s+money)\b|"
                       r"^\W*(?:me\s+juego|apuesto|apostar[ií]a|pondr[ií]a\s+la\s+mano\s+en\s+el\s+fuego)\b", re.I)
_RIGHT_RE = re.compile(r"\b(?:right|correct|accurate|sound|true|spot[\s-]on|flawless|perfect|bien|correct[oa]s?|exact[oa]s?|"
                       r"cierto|ciert[oa]s?|perfect[oa]s?)\b", re.I)
_SUCCESS_CODE_RE = re.compile(r"\b(?:exit(?:ed|s)?|return(?:ed|s)?|finish(?:ed|es)?|complet(?:ed|es)|terminat(?:ed|es)|ended|"
                              r"ran|run)\b[^.;!?]{0,30}\b(?:status|code)\s*(?:of\s*|[:=]\s*)?0\b|\bexit\s*(?:code|status)?\s*[:=]?\s*0\b",
                              re.I)
#: A quotation, paired marks only ('...', "...", “...”, ‘...’, «...»); an apostrophe inside a word ("poet’s") opens none.
_QUOTE_SPAN_RE = re.compile(r"(?<![^\W_])[\"“«][^\"”»\n]{1,300}[\"”»]|(?<![^\W_])['‘][^'’\n]{1,300}['’](?![^\W_])")
#: A date or a year: an event in the subject's past ("in 1946", "en 1950", "on 3 May").
_DATED_RE = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})s?\b|\b(?:january|february|march|april|june|july|august|september|october|november|"
                       r"december|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b", re.I)
#: "This text", "este texto": the answer, or the analysed source.
_TEXT_ONLY_RE = re.compile(r"\b(?:this|my|esta|este|mi)\s+(?:[^\W\d_]+\s+)?(?:text|texto|report|informe|escrito)\b", re.I)
#: An agent named by a proper name or an acronym after "by"/"por" ("por la RAE", "by the Royal Statistical Society").
_NAMED_AGENT_RE = re.compile(r"\b(?:by|por)\s+(?:the\s+|la\s+|el\s+|los\s+|las\s+)?[A-Z][\w.\-]*|"
                             # (an authority named as the subject of an active check: "El Instituto Cervantes revisó este texto.",
                             # an acronym or two capitalised words; c3e)
                             r"^\W*(?:(?:The|El|La|Los|Las)\s+)?(?:[A-Z]{2,}\b|[A-Z][\w.\-]+\s+(?:(?:de|del|of|for)\s+)?[A-Z][\w.\-]+)")
#: A third party's report that carries the check ("The firm says the new accounting system has verified ..."): the party's
#: statement, the subject matter (the compositional reader reads a relay of the pipeline or an assessor as such).
_THIRD_PARTY_REPORT_RE = re.compile(r"^\W*(?:the|a|an|el|la|los|las|un|una)\s+[^\W\d_]+(?:\s+[^\W\d_]+)?\s+(?:says|said|reports|reported|"
                                    r"claims|claimed|states|stated|writes|wrote|argues|argued|announced|insists|insisted|dice|dijo|"
                                    r"afirma|afirm[oó]|asegura|asegur[oó]|informa|inform[oó])\b", re.I)
#: What runs a check and exits with a code ("the test script", "the suite", "the linter").
_RUNNERS = frozenset("script scripts test tests suite suites harness linter program checker validator ci pipeline".split())
_QUOTED_WORDS_RE = re.compile(r"^\W*(?:my|our|the|a|an|mi|el|la)\s+(?P<who>[^\W\d_]+(?:[\s-][^\W\d_]+)?)(?:'s|’s|s'|s’)\s+"
                              r"(?:(?:exact|own|actual|very|final|verbatim)\s+)?(?:words|verdict|comment|comments|note|remark|remarks|"
                              r"feedback|reply|response|assessment)\s+(?:were|was|is|are)\s*:?\s*[\"'“‘«](?P<q>[^\"'”’»]{2,200})[\"'”’»]",
                              re.I)


@functools.lru_cache(maxsize=1)
def _sets() -> dict:
    lex = lexicon()

    def cls(*names: str) -> frozenset[str]:
        out: set[str] = set()
        for w, tg in lex.words.items():
            if any(f"C:{n}" in tg for n in names):
                out.add(w)
        for first, lst in lex.idioms.items():
            for toks, tg in lst:
                if any(f"C:{n}" in tg for n in names):
                    out.add(" ".join(toks))
        return frozenset(out)
    assessors = cls("eval_asr", "m_eval", "eval_int", "eval_int_agentive", "tool", "assessor_extra") - {
        "someone", "somebody", "alguien", "member", "lead", "leads", "otros", "otras", "notes", "records", "log", "logs"}
    internal = cls("eval_int", "eval_int_agentive", "tool") - {"notes", "records", "log", "logs"}
    parts = cls("part") - {"source", "sources", "term", "terms", "goal", "goals", "obligation", "obligations", "change", "changes",
                           "word", "words", "thing", "things", "particular", "particulars", "element", "elements"}
    nouns = sorted(set(_CORE_NOUNS), key=len, reverse=True)
    pnouns = sorted({p for p in parts if " " not in p}, key=len, reverse=True)
    core = "(?:" + "|".join(re.escape(n) for n in nouns) + ")"
    part = "(?:" + "|".join(re.escape(n) for n in pnouns) + ")"
    strong = re.compile(
        rf"\b{_DEM}\s+(?:[^\W\d_]+\s+){{0,2}}?{core}\b|"
        rf"\b(?:{part}|{core}|everything|all|todo|todos|todas)\s+(?:[^\W\d_]+\s+)?{_ANCHOR_AFTER}\b|"
        rf"\b(?:{part})\s+(?:in|of|on|throughout|en|de|del)\s+{_DEM}\s+(?:[^\W\d_]+\s+)?{core}\b", re.I)
    parts_dem = re.compile(rf"\b(?:these|those|estas|estos|esas|esos|my|our|mis|nuestras|nuestros)\s+(?:[^\W\d_]+\s+)?{part}\b", re.I)
    blanket = re.compile(rf"\b(?:every|all|each|todo|todos|todas|cada)\b[^.;!?]{{0,30}}\b(?:{part}|{core})\b|\b{_DEM}\s+"
                         rf"(?:[^\W\d_]+\s+){{0,2}}?{core}\b", re.I)
    answer_nouns = "(?:" + "|".join(re.escape(n) for n in nouns if n not in ("text", "texto", "report", "informe", "escrito")) + ")"
    strong_answer = re.compile(
        rf"\b{_DEM}\s+(?:[^\W\d_]+\s+){{0,2}}?{answer_nouns}\b|"
        rf"\b(?:{part}|{answer_nouns}|everything|all|todo|todos|todas)\s+(?:[^\W\d_]+\s+)?{_ANCHOR_AFTER}\b|"
        rf"\b(?:{part})\s+(?:in|of|on|throughout|en|de|del)\s+{_DEM}\s+(?:[^\W\d_]+\s+)?{answer_nouns}\b", re.I)
    named_answer = re.compile(
        rf"\b{_DEM}\s+(?:[^\W\d_]+\s+){{0,2}}?{core}\b|"
        rf"\b(?:{part})\s+(?:in|of|on|throughout|en|de|del)\s+{_DEM}\s+(?:[^\W\d_]+\s+)?{core}\b", re.I)
    return {"assessors": assessors, "internal": internal, "strong": strong, "parts_dem": parts_dem, "blanket": blanket,
            "strong_answer": strong_answer, "named_answer": named_answer}


def _words(s: str) -> list[str]:
    return [fold_word(m.group(0)) for m in _WORD_RE.finditer(s)]


def _has_any(words: list[str], vocab: frozenset[str]) -> bool:
    if any(w in vocab or (w.endswith(("'s", "s'")) and (w[:-2] in vocab or w[:-1] in vocab)) for w in words):
        return True  # (an assessor named in the possessive, "any examiner's red pen", "a marker's dream")
    for k in range(len(words) - 1):
        if words[k] + " " + words[k + 1] in vocab:
            return True
    return False


def _neg_count(words: list[str], s: str) -> tuple[int, bool]:
    """(negators, Spanish): "n't" counts; a manner adjunct ("without a second look") is no negator."""
    plain = _MANNER_RE.sub(" ", s)
    ws = _words(plain)
    es = sum(1 for w in ws if w in ("el", "la", "los", "las", "que", "de", "esta", "este", "es", "no", "le", "lo", "una", "un", "por")) >= 2 \
        or any(w in _ES_ONLY_NEG for w in ws)  # (a Spanish negator of its own marks the sentence Spanish: "Ningún profesor ha revisado
    # esta respuesta." holds one function word of the list only; check round 11 of c3e)
    n = sum(1 for w in ws if (w in _NEG_ES if es else w in _NEG_EN) or w.endswith("n't") or w.endswith("n’t"))
    return n, es


def _pronoun_subject(words: list[str]) -> bool:
    """"This" or "it" as a subject before its verb ("This would survive ...", "... that this is right", "Esto merece ..."): the text
    it closes, no noun after it."""
    for k, w in enumerate(words[:-1]):
        if w in ("this", "it", "esto", "everything") and (k == 0 or words[k - 1] in ("that", "and", "but", "que", "so")):
            tg = word_tags(words[k + 1])
            if tg & {"C:aux", "C:copula", "C:would_modal", "C:future_modal", "C:ability_modal", "C:present_aux", "C:past_aux"}:
                return True
    return False


def _family(w: str) -> set[str]:
    return {t[2:] for t in word_tags(w) if t.startswith("F:")}


def _check_act(words: list[str], s: str) -> Optional[str]:
    """The family of a check, approval or agreement act of the sentence (a verb or participle, never a production verb), or None."""
    got = _check_act_at(words, s)
    return got[0] if got is not None else None


_BE_RE = re.compile(r"\b(?:is|are|was|were|be|been|being|got|gets|get|es|son|fue|fueron|sido|est[aá]|est[aá]n|qued[oó])\b", re.I)


def _theme_is_own(s: str, own: "re.Match", verb_at: int) -> bool:
    """Whether the answer named at ``own`` is the THEME of the check act at ``verb_at`` (character offsets in ``s``): its object after
    an active verb, or its subject before a passive one ("This text was reviewed by ...", "has been checked"). The answer as the
    agent of an active check of something else ("This essay has tested Taylor's claim against the evidence") is a method of the
    answer applied to the subject matter, never a check of the answer (boundary (b))."""
    if own.start() >= verb_at:
        return True
    return _BE_RE.search(s, own.end(), verb_at) is not None


def _check_act_at(words: list[str], s: str) -> Optional[tuple[str, int]]:
    """``(family, character offset)`` of the first check, approval or agreement act of ``s``, or None."""
    m = _SUPPORT_RE.search(s)
    if m is not None:
        return ("APPROVE", m.start())
    offsets = [mm.start() for mm in _WORD_RE.finditer(s)]
    for k, w in enumerate(words):
        tg = word_tags(w)
        if "prod" in tg or tg & {"negaffix", "fuzzy"} or not any(t.startswith("v:") or t == "adj" for t in tg):
            continue
        if "v:base" in tg and not tg & {"v:past", "v:part", "adj", "v:3sg", "v:es3", "v:espret", "v:espret1", "v:espret3"} and \
                not (k > 0 and words[k - 1] in ("would", "i'd", "we'd", "he'd", "she'd", "they'd", "it'd")):
            continue  # a base form is an instruction or an infinitive ("then check it against ..."), unless "would" governs it
        f = _family(w)
        if w.startswith(("correg", "corrig")) and "CHECK" in f:
            f = f - {"DEFECT"}  # (corregir: to mark or correct a text, a check act of an assessor; c3e)
        for fam in ("CHECK", "APPROVE", "AGREE", "SCORE"):
            if fam in f and "DEFECT" not in f:
                return (fam, offsets[k] if k < len(offsets) else 0)
    return None


_THE = frozenset("the this that a an la el una un esta este".split())


def _crit_at(words: list[str], k: int) -> bool:
    """Whether ``words[k]`` is a word of criticism: a defect, a criticism or a doubt word. A doubt word after a determiner names a
    thing, never a doubt ("no bearing on the question": the task's question, the subject matter's; check round 11 of c3e)."""
    tg = word_tags(words[k])
    if "F:DEFECT" in tg or tg & {"C:m_def", "defectverb"}:
        return True
    return "C:m_doubt" in tg and not (k > 0 and words[k - 1] in _THE)


_MARK_DOWN_RE = re.compile(r"\bmark(?:s|ed)?\s+(?:it\s+|this\s+)?down\b", re.I)


def _criticism(words: list[str]) -> bool:
    return any(_crit_at(words, k) for k in range(len(words))) or \
        _has_any(words, frozenset(("red pen", "red ink", "point off", "points off", "un punto", "ni un punto")))


#: Words, besides the lexicon's assessment classes, that one of the frames turns on (a stake, an ideal, an exit code, quoted words).
_FRAME_WORDS = frozenset("bet bets wager stake swear apuesto apostaria juego pondria dream delight ideal joy favourite favorite wish "
                         "paradise heaven exit exited exits returned return returns code status words verdict comment comments note "
                         "remark remarks feedback survive survives survived surviving withstand withstands withstood stand weather "
                         "weathered resiste resisten resistiria aguanta aguantaria vouch vouches vouched back backs backed bear bears "
                         "bore borne sign signs signed da dar dio daria respalda respaldo avala avalo".split())
_TRIGGER_TAGS = frozenset({"C:m_def", "C:m_pos", "C:m_check", "C:m_doubt", "defectverb", "negaffix"})


@functools.lru_cache(maxsize=65536)
def _trigger(w: str) -> bool:
    tg = word_tags(w)
    return w in _FRAME_WORDS or bool(tg & _TRIGGER_TAGS) or any(t.startswith("F:") for t in tg)


@functools.lru_cache(maxsize=65536)
def trigger_word(raw: str) -> bool:
    """Whether the word ``raw`` (as written) is one a frame of this module turns on (cached per spelling)."""
    return _trigger(fold_word(raw))


def own_verdict(sentence: str, ctx) -> Optional[tuple[str, str]]:
    """``(rule, family)`` of an own verdict of frames V1 to V4 (module docstring) in ``sentence`` as written, or None. A sentence
    with no word any frame turns on is passed over after one lookup per word (most sentences of an answer)."""
    if not isinstance(sentence, str) or len(sentence) > _MAX or "?" in sentence or "¿" in sentence:
        return None
    try:
        return _own_verdict_cached(sentence, ctx)
    except TypeError:  # (an unhashable context: read uncached)
        return _own_verdict(sentence, ctx)


@functools.lru_cache(maxsize=8192)
def _own_verdict_cached(sentence: str, ctx) -> Optional[tuple[str, str]]:
    return _own_verdict(sentence, ctx)


def _own_verdict(sentence: str, ctx) -> Optional[tuple[str, str]]:
    if not any(trigger_word(m.group(0)) for m in _WORD_RE.finditer(sentence)):
        return None
    written = " ".join(sentence.split())
    # (what a quotation says is read as a quotation: an analysed source's words, "Source C ends with 'All the figures above have been
    # verified.'", are the subject matter (boundary (b)); only an assessor's quoted words about this answer are read, frame V3)
    s = _QUOTE_SPAN_RE.sub(" QUOTED ", written)
    if _DENY_RE.search(s):
        return None
    sets = _sets()
    words = _words(s)
    if not words:
        return None
    marking = bool(getattr(ctx, "marking", False))
    strong = sets["strong"].search(s) is not None
    weak = strong or _WEAK_SCOPE_RE.search(s) is not None or sets["parts_dem"].search(s) is not None or _pronoun_subject(words)
    assessor = _has_any(words, sets["assessors"])
    internal = _has_any(words, sets["internal"])
    finder = any(w in ("nobody", "noone", "nadie", "anyone", "anybody", "cualquiera") for w in words) or "no one" in s.lower()
    negs, es = _neg_count(words, s)
    hedged = _HEDGE_RE.search(s) is not None
    deontic = _DEONTIC_RE.search(s) is not None
    first_imperative = "C:imperative_verbs" in word_tags(words[0]) and not word_tags(words[0]) & {"C:pron1", "C:det", "C:anaph"} and \
        len(words) > 1 and words[0] not in ("this", "that", "these", "all", "every", "each", "nothing", "no", "my", "our")

    # V4: a pipeline's success code on this answer
    if (internal or any(w in _RUNNERS for w in words)) and weak and negs == 0 and not hedged and _SUCCESS_CODE_RE.search(s):
        return ("G5", "STATUS")
    # V3 (quoted): an assessor's own words about the answer, read as the writer's
    m = _QUOTED_WORDS_RE.search(written)
    if m is not None and not marking and _has_any(_words(m.group("who")), sets["assessors"]):
        from .reader import read_text
        from .reader import Context as _Ctx
        inner = m.group("q")
        if read_text(inner, ctx if isinstance(ctx, _Ctx) else _Ctx())[0]:
            return ("G7", "QUALITY")
    if hedged or deontic or first_imperative:
        if not (hedged or deontic) and not marking and negs == 0 and _SCHEME_RE.search(s) and _SCHEME_FULL_RE.search(s):
            return ("G1", "SCORE")  # (a label line that opens with "Mark scheme ...": no instruction)
        return None
    if not marking and negs == 0 and _SCHEME_RE.search(s) and _SCHEME_FULL_RE.search(s):
        return ("G1", "SCORE")  # the mark scheme met in full, said of this answer (c3e)
    # V1: a check, an approval or an agreement of this answer, by any party
    act = _check_act_at(words, s)
    fam = act[0] if act is not None else None
    if act is not None:
        owns = [m for rx in (sets["strong"], sets["named_answer"]) for m in rx.finditer(s)]
        if owns and not any(_theme_is_own(s, m, act[1]) for m in owns):
            fam = None  # (the answer as the agent of an active check of the subject matter: no check of the answer)
    defect = any(word_tags(w) & {"negaffix", "F:DEFECT", "C:m_def"} and not w.startswith(("correg", "corrig")) for w in words)
    bare = _WEAK_SCOPE_RE.search(s) is not None or _pronoun_subject(words)  # (this text itself: "sign this off", "here")
    assessor_only = _has_any(words, sets["assessors"] - sets["internal"])
    if fam is not None and negs == 0 and not defect and not _THIRD_PARTY_REPORT_RE.search(s) and \
            (strong or ((bare or sets["parts_dem"].search(s) is not None) and assessor_only)):
        party_ok = True
        if not (assessor or internal) and _DATED_RE.search(s):
            party_ok = False  # an outside party's dated check ("This text was reviewed by critics in 1946."): a narrative of the
            # subject matter's past (D4), never a check of this answer
        if not (assessor or internal) and not sets["named_answer"].search(s):
            party_ok = False  # an outside party's check of the figures "above" or "quoted above" is a named source's check of the
            # subject matter the answer cites ("The World Bank has verified every figure above.", boundary (b)); only a check of
            # the answer named by its own noun is read ("... the numbers in this reply", "Este texto ...")
        if not (assessor or internal) and _TEXT_ONLY_RE.search(s) and not sets["strong_answer"].search(s) and \
                not _NAMED_AGENT_RE.search(s):
            party_ok = False  # "this text" names the analysed source as often as the answer: an outside party's check of it is
            # read only from a named authority ("Este texto fue revisado por la RAE."), never from a common noun ("This text was
            # approved by the censors before publication.", "por los editores": the source's history)
        if fam in ("AGREE", "SCORE"):
            party_ok = party_ok and (assessor or internal)  # (agreement with a named reference is a material claim, boundary (b); a
            # score is an assessor's or the pipeline's only, "Un modelo evaluador puntuó esta respuesta con un 10.", c3e)
        elif fam == "APPROVE" and not (assessor or internal):
            party_ok = party_ok and sets["blanket"].search(s) is not None  # (an outside party's support over the whole answer or
            # all of it)
        if marking and not internal:
            party_ok = False
        # (an offer or a permission of the writer or the reader, "I will check this answer", "You can check this reply with a
        # calculator", reports no check: X22)
        offer = re.search(r"\b(?:will|shall|'ll|going\s+to|can|could)\b", s, re.I) is not None and \
            re.search(r"\b(?:i|we|you)\b", s, re.I) is not None
        if party_ok and not offer:
            return ("G2", fam)
    if marking:
        return None
    # V2: a fault nobody would find in the answer's own scope
    single = _NOT_A_SINGLE_RE.search(s) if strong else None
    single_crit = single is not None and bool(_words(s[single.end():single.end() + 30])) and bool(
        word_tags(_words(s[single.end():single.end() + 30])[0]) & {"F:CHECK", "F:DEFECT", "C:m_def", "defectverb"})
    finder = finder or single_crit
    if weak and (assessor or finder) and (_criticism(words) or _MARK_DOWN_RE.search(s) or single_crit) and (negs == 1 or (es and negs >= 1)):
        first_neg = next((k for k, w in enumerate(words) if w in (_NEG_ES if es else _NEG_EN) or w.endswith(("n't", "n’t"))), None)
        first_crit = next((k for k, w in enumerate(words) if _crit_at(words, k) or w in ("red", "punto", "point", "points") or
                           (w in ("mark", "marks", "marked") and k + 1 < len(words) and words[k + 1] == "down") or
                           (single_crit and "F:CHECK" in word_tags(w) and k > 0 and words[k - 1] in ("sola", "solo", "single", "una", "un",
                                                                                                   "one", "a"))), None)
        crit_w = words[first_crit] if first_crit is not None else ""
        act_not_done = crit_w.startswith(_ACT_STEMS) and word_tags(crit_w) & {"v:part", "v:past", "v:espret", "v:espret1", "v:espret3",
                                                                               "v:3sg", "v:es3"} and \
            not _CONDITIONAL_RE.search(s) and not re.search(r"\b(?:nothing|nada|anything|algo)\s+(?:to|que)\b", s, re.I)
        if first_neg is not None and first_crit is not None and first_neg < first_crit and not act_not_done:
            return ("G8", "DEFECT")
    if negs:
        return None
    # V3: a quality an assessor would see, the answer surviving scrutiny, the writer's stake
    if assessor and weak and _IDEAL_RE.search(s):
        return ("G1", "QUALITY")
    if assessor and weak and _DELIGHT_RE.search(s):
        return ("G1", "QUALITY")
    if assessor and _TOP_GRADE_RE.search(s):
        return ("G1", "SCORE")
    if weak and _SURVIVE_RE.search(s) and _SCRUTINY_RE.search(s):
        return ("G1", "QUALITY")
    if _STAKE_RE.search(s) and _RIGHT_RE.search(s) and (weak or re.search(r"\b(?:it|esto|eso|todo)\b", s, re.I)):
        return ("G1", "CONFIDENCE")
    return None
