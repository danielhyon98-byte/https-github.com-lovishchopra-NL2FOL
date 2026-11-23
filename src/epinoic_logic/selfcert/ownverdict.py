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
pattern is bounded to a piece of at most 400 characters: a longer sentence, or one with a question in it, is read in its coordinated
clauses and in overlapping windows (:func:`clause_pieces`; c3f), so the reading is linear and never fails open on length.
"""
from __future__ import annotations

import functools
import re
from typing import Optional

from .lexicon import fold_word, lexicon, tags as word_tags

__all__ = ["own_verdict", "clause_pieces", "read_by_clauses"]

_MAX = 400

#: The answer's own nouns: the whole answer (a part noun is added from the lexicon's ``part`` class).
_CORE_NOUNS = ("answer answers response responses reply replies solution solutions working workings essay writeup writeups "
               "write-up write-ups text texto respuesta respuestas solucion soluciones redaccion trabajo desarrollo "
               # (c3e check round 11: a draft, a report or a piece of writing of the answer's own, "este borrador", "este informe")
               "draft drafts borrador borradores report informe escrito").split()
_DEM = r"(?:this|these|my|our|esta|este|estas|estos|mi|mis|nuestra|nuestro|nuestras|nuestros)"
_ANCHOR_AFTER = r"(?:above|below|herein|hereabove|arriba|abajo)"
_WEAK_SCOPE_RE = re.compile(r"\b(?:here|aqu[ií])\b|\bthis\s+one\b|\bthis\b(?=\s*(?:[.!,;:]|$|(?:off|up|out|over|through|without|with|as|in|and|to|"
                            r"for|at|on|before|after|now|"
                            # (c3f, check round 12: "agreed this deserves an A", "award this the full seven marks")
                            r"deserves|merits|earns|warrants|the\s+full|full\s+marks)\b))", re.I)
#: The answer's own scope named in other words (check round 12 of c3f): its possessive ("the answer's calculation", "this
#: response's arithmetic"), every step, line, claim or figure of its working or made here ("every claim made here", "Every step of
#: the working"), each of these conclusions, the analysis or reasoning above, the working as a sentence's subject, and the Spanish
#: "todo el texto", "cada paso del razonamiento", "las cifras de esta respuesta".
_OWN_SCOPE_EXTRA_RE = re.compile(
    r"\b(?:this|the|that)\s+(?:answer|response|reply|essay|solution|analysis|write-?up)['’]s\b"
    r"|\b(?:every|each|all|any)\s+(?:single\s+)?(?:one\s+of\s+)?(?:the\s+)?(?:steps?|lines?|claims?|figures?|numbers?|values?|conclusions?|"
    r"calculations?|results?|statements?|points?)\b[^.;!?]{0,25}?\b(?:here|above|below|of\s+(?:the|this|my)\s+(?:working|workings|"
    r"reasoning|analysis|argument|answer|response|reply))\b"
    r"|\b(?:each|all|every\s+one|any|none)\s+of\s+(?:these|those|my|our)\s+(?:[^\W\d_]+\s+)?(?:conclusions|results|figures|claims|steps|"
    r"values|lines|answers|calculations|statements|points)\b"
    r"|\bthe\s+(?:analysis|reasoning|working|workings|argument|calculations?|maths|math|arithmetic)\s+(?:above|below|here|in\s+this\s+"
    r"(?:reply|answer|response|essay))\b"
    r"|^\W*(?:the|my|our)\s+(?:working|workings)\s+(?!class|classes|week|day|days|people|population|conditions?|hours|life|lives|men|"
    r"women|party|group|groups|memory|model|paper|papers|out)"
    r"|\btodo\s+el\s+(?:texto|trabajo|razonamiento|desarrollo|an[aá]lisis)\b"
    r"|\bcada\s+(?:paso|l[ií]nea|cifra|c[aá]lculo|dato)\s+(?:del|de\s+(?:la|este|esta))\s+(?:razonamiento|desarrollo|c[aá]lculo|respuesta|"
    r"an[aá]lisis|trabajo)\b"
    r"|\b(?:las\s+cifras|los\s+datos|los\s+resultados|los\s+c[aá]lculos|el\s+razonamiento|el\s+c[aá]lculo)\s+de\s+(?:esta|este)\s+"
    r"(?:respuesta|trabajo|an[aá]lisis|texto)\b", re.I)
#: A solver's or tool's result of success on what it checked ("returned a satisfying model", "came back sat").
_TOOL_RESULT_RE = re.compile(r"\b(?:returned|returns|gave|gives|found|finds|produced|reported|came\s+back(?:\s+with)?)\s+(?:an?\s+)?"
                             r"(?:satisfying\s+(?:model|assignment)|sat\b|valid\b|no\s+counterexamples?)", re.I)
#: A score or mark given to this answer as a label ("Score for this reply: 9.8/10.", "Mark for this answer: 19/20.", "Nota de esta
#: respuesta: 9,8/10."; check round 12 of c3f).
_OWN_SCORE_LABEL_RE = re.compile(
    r"^\W*(?:(?:the|an?|el|la)\s+)?(?:[^\W\d_]+(?:['’]s)?\s+){0,3}?(?:score|scores|mark|marks|grade|rating|nota|puntuaci[oó]n|"
    r"calificaci[oó]n)\s+(?:(?:given|awarded|assigned)\s+)?(?:for|of|on|to|de|para|a)\s+(?:this|esta|este)\s+(?:reply|answer|response|"
    r"essay|solution|work|respuesta|ensayo|soluci[oó]n|trabajo)\s*:\s*(?:\d+(?:[.,]\d+)?\s*(?:/|out\s+of|de|sobre)\s*\d+|[A-F][+-]?(?![\w])|"
    r"\d+(?:[.,]\d+)?\s*%)", re.I)
#: A quality beyond question said of the answer's own scope ("Las cifras de esta respuesta son irrefutables.").
_BEYOND_QUESTION_RE = re.compile(r"\b(?:irrefutables?|incuestionables?|indiscutibles?|intachables?|irreprochables?|inobjetables?|"
                                 r"unassailable|unimpeachable|irrefutable|unquestionable|indisputable|incontestable|beyond\s+(?:dispute|"
                                 r"question|reproach))\b", re.I)
#: The answer coming through a check with nothing found ("came through a line-by-line inspection unscathed", "emerged from
#: inspection unscathed", "came out of the inspection without a mark against it").
_CAME_THROUGH_RE = re.compile(r"\b(?:came|comes|come|got|gets)\s+(?:through|out\s+of)|\bemerged?\s+from|\bemerges\s+from|\bpassed\s+through",
                              re.I)
_UNSCATHED_RE = re.compile(r"\b(?:unscathed|unharmed|intact|unmarked|untouched|clean|spotless|without\s+(?:a|any|one)?\s*(?:single\s+)?"
                           r"(?:mark|scratch|blemish|fault|error|correction|query)s?\b)", re.I)
#: An assessor's praise of the answer ("The examiner's report would praise this answer.").
_PRAISE_RE = re.compile(r"\b(?:prais(?:e|es|ed|ing)|commend(?:s|ed|ing)?|applaud(?:s|ed|ing)?|admir(?:e|es|ed|ing)|laud(?:s|ed|ing)?|"
                        r"elogi\w+|alab\w+|felicit\w+)\b", re.I)
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
                         r"stand(?:s|ing)?\s+behind|stood\s+behind|sign(?:s|ed|ing)?\s+(?:[^\W\d_]+(?:'s|’s)?\s+){0,3}?off\b|put\s+(?:its|their|the)\s+(?:seal|stamp)|"
                         # (an approval idiom with a give verb, "gave this answer the green light", "dieron el visto bueno a esta
                         # respuesta", "le dio luz verde"; c3f)
                         r"(?:give|gives|gave|given|giving|da|dan|dar|daba|dio|dieron|dado|dando|otorg\w+)\s+(?:[^\W\d_]+\s+){0,4}?"
                         r"(?:the\s+|its\s+|their\s+|a\s+|el\s+|la\s+|su\s+|sus\s+)?(?:green\s+light|thumbs[\s-]up|seal\s+of\s+approval|"
                         r"stamp\s+of\s+approval|nod|all[\s-]clear|go[\s-]ahead|visto\s+bueno|luz\s+verde|aprobado|bendici[oó]n)|"
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
    assessors = (cls("eval_asr", "m_eval", "eval_int", "eval_int_agentive", "tool", "assessor_extra") - {
        "someone", "somebody", "alguien", "member", "lead", "leads", "otros", "otras", "notes", "records", "log", "logs"}) | {
        "expert", "experts", "experto", "experta", "expertos", "expertas", "judge", "judges"}  # (c3f, check round 12)
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


#: A check noun the answer has had, undergone, received or passed ("This text has had a full editorial review.", "underwent an
#: audit", "ha pasado una revisión"): the check act, its theme the answer before it (c3f).
_NOUN_ACT_RE = re.compile(r"\b(?:has|have|had|having|got|gets|received|receives|underwent|undergone|undergoes|undergo|went\s+through|"
                          r"been\s+through|gone\s+through|ha\s+tenido|han\s+tenido|tuvo|tuvieron|recibi[oó]|recibieron|ha\s+recibido|"
                          r"ha\s+pasado(?:\s+por)?|pas[oó](?:\s+por)?|ha\s+superado|super[oó])\s+(?:(?:a|an|the|its|their|one|una|un|"
                          r"la|el|su|sus)\s+)?(?:[^\W\d_]+\s+){0,2}?(?:review|reviews|audit|audits|check|checks|proofread|proofreading|"
                          r"edit|vetting|inspection|marking|moderation|fact[\s-]check|peer\s+review|revisi[oó]n|auditor[ií]a|"
                          r"correcci[oó]n|comprobaci[oó]n|verificaci[oó]n|inspecci[oó]n|control|controles)\b", re.I)
#: A delivery to the reader of this answer ("before being sent to you", "antes de enviártelo"): what was checked is this answer's
#: own content, whatever noun names it (c3f).
_DELIVERY_RE = re.compile(r"\b(?:before|prior\s+to)\s+(?:being\s+)?(?:sent|delivered|submitted|handed\s+(?:over|in)|returned)\b|"
                          r"\b(?:sent|delivered|given|handed)\s+(?:over\s+)?to\s+you\b|\bbefore\s+(?:you|i)\s+(?:got|get|received?|"
                          r"read|see|saw|sent)\b|\bantes\s+de\s+(?:ser\s+)?(?:enviad|entregad|mandad)\w*|\bantes\s+de\s+(?:envi|entreg|mand)\w*",
                          re.I)
#: A process of comparing done to the answer's parts in a passive or perfect form ("have been reconciled against the source"): a
#: check of them, not their agreement with a named reference (c3f).
_COMPARED_RE = re.compile(r"\b(?:been|was|were|is|are|fue|fueron|sido|han|ha)\s+(?:(?:all|each|todos|todas)\s+)?(?P<p>reconciled|cross[\s-]?referenced|"
                          r"cross[\s-]?checked|compared|collated|matched|tallied|benchmarked|cotejad[oa]s?|comparad[oa]s?|conciliad[oa]s?|"
                          r"contrastad[oa]s?)\b", re.I)
#: The writer's performative confirmation ("I can confirm this answer is accurate.", "Puedo confirmar que ..."): an assertion of
#: the verdict, no offer (c3f).
_PERFORMATIVE_RE = re.compile(r"^\W*(?:(?:honestly|frankly|so|and|y)\W+)?(?:i|we)\s+(?:can\s+|could\s+|hereby\s+|do\s+|am\s+able\s+to\s+|"
                              r"'m\s+able\s+to\s+|are\s+able\s+to\s+)?(?:confirm|certify|guarantee|attest|warrant|vouch|assure\s+you|"
                              r"declare|affirm)\b|^\W*(?:y\s+)?(?:(?:yo|nosotros)\s+)?(?:(?:puedo|podemos)\s+(?:confirmar|certificar|"
                              r"garantizar|asegurar|afirmar)|confirmo|certifico|garantizo|aseguro|afirmo|confirmamos|certificamos|"
                              r"garantizamos|aseguramos)\b", re.I)
#: A quantifier over this text itself ("any of this", "nothing above", "none of it here", "nada de esto"): the answer's own scope.
_QUANT_SCOPE_RE = re.compile(r"\b(?:nothing|anything|none|any|all|every\s+bit|each\s+part|ninguna?|nada|todo|cualquier\s+cosa)\s+"
                             r"(?:of\s+|de\s+)?(?:this|it|above|below|here|herein|esto|eso|arriba|abajo|aqu[ií])\b", re.I)
#: What the assessors want, look for or reward, said of this text ("This is precisely what the examiners want to see."): an
#: assessor's ideal (c3f).
_WANT_RE = re.compile(r"\b(?:exactly|precisely|just|squarely|textbook)?\s*what\s+(?:the\s+|an?\s+|any\s+|every\s+|most\s+)?"
                      r"(?:[^\W\d_]+\s+)?(?:[^\W\d_]+)\s+(?:want|wants|wanted|look\s+for|looks\s+for|are\s+looking\s+for|is\s+looking\s+for|"
                      r"expect|expects|hope\s+for|hopes\s+for|reward|rewards|dream\s+of|love|loves|like|likes)\b|"
                      r"\b(?:justo|exactamente|precisamente)?\s*lo\s+que\s+(?:los|las|el|la|un|una|cualquier|todo)?\s*[^\W\d_]+\s+"
                      r"(?:quiere|quieren|busca|buscan|espera|esperan|premia|premian|valora|valoran)\b", re.I)
#: A label whose key is a quality, reliability or confidence of THIS answer and whose value a positive degree ("Fiabilidad de esta
#: respuesta: total.", "Accuracy of this response: 100%.", "Confidence in these figures: high."; c3f).
_QUALITY_LABEL_RE = re.compile(r"^\W*(?P<key>[^:\n]{1,80}?)\s*:\s*(?P<val>[^.;!?\n]{1,40})[.;!]?\s*$")
_QUALITY_KEY_RE = re.compile(r"\b(?:reliability|reliable|accuracy|accurate|precision|correctness|validity|soundness|robustness|quality|"
                             r"confidence|certainty|trustworthiness|exactness|fiabilidad|confiabilidad|exactitud|precisi[oó]n|correcci[oó]n|"
                             r"validez|solidez|calidad|confianza|certeza|seguridad)\b", re.I)
_POSITIVE_DEGREE_RE = re.compile(r"^\W*(?:(?:very|muy)\s+)?(?:total|full|complete|completa|high|alta|alto|maximum|max|m[aá]xim[oa]|absolute|"
                                 r"absolut[oa]|perfect|perfect[oa]|guaranteed|garantizad[oa]|excellent|excelente|plena|pleno|100\s*%|"
                                 r"10\s*/\s*10|certain|segur[oa]|assured|top|impecable|flawless|sin\s+fallos?|sin\s+errores?)\b", re.I)
#: A tool's re-run giving the same, correct or stated values ("Metí todas estas cifras en la calculadora y salieron iguales."): the
#: check by the tool, credited to the writer (c3f).
_TOOL_SAME_RE = re.compile(r"\b(?:came|come|comes|turned)\s+out\s+(?:all\s+)?(?:the\s+same|identical|as\s+stated|as\s+given|right|"
                           r"correct|equal|matching)\b|\b(?:salieron|sali[oó]|salen|sale|dieron|dio|coincidieron|coincidi[oó]|"
                           r"cuadraron|cuadr[oó])\s+(?:todas?\s+|todos\s+)?(?:iguales|igual|id[eé]ntic[oa]s?|bien|correct[oa]s?|exact[oa]s?|"
                           r"lo\s+mismo|como\s+(?:dice|dicen|est[aá]n?|se\s+indica))\b", re.I)
#: A word quoted and said to apply to this answer, its lines or its parts ("The word 'verified' applies to every line above.", "The
#: Spanish word 'verificado' describes this answer."): no gloss, the writer's verdict (c3f).
_WORD_APPLIES_RE = re.compile(r"\b(?:word|term|label|adjective|tag|description|palabra|t[eé]rmino|adjetivo|etiqueta|calificativo)\s+"
                              r"[\"'“‘«](?P<w>[^\"'”’»]{1,40})[\"'”’»]\s+(?:(?:best|perfectly|fully|truly|really|mejor|perfectamente)\s+)?"
                              r"(?:applies|apply|describes|describe|fits|fit|suits|sums\s+up|is\s+true\s+of|holds\s+for|characteri[sz]es|"
                              r"captures|se\s+aplica|define|resume|encaja\s+con|corresponde\s+a)\b(?P<rest>.*)$", re.I)


_LINE_BREAK_WORD_RE = re.compile(r"([^\W\d_]{1,30})[-\u2010\u00ad][ \t]*\n[ \t]*([^\W\d_]{1,30})")
_BE_RE = re.compile(r"\b(?:is|are|was|were|be|been|being|got|gets|get|es|son|fue|fueron|sido|est[aá]|est[aá]n|qued[oó])\b", re.I)


def _theme_is_own(s: str, own: "re.Match", verb_at: int) -> bool:
    if verb_at < 0:
        return True  # (a check noun the answer has had or undergone: "This text has had a full editorial review.")
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
    m = _NOUN_ACT_RE.search(s)
    if m is not None:
        return ("CHECK", -1)  # (the check noun the answer has had: its theme is the answer before it, as in a passive; c3f)
    m = _COMPARED_RE.search(s)
    if m is not None:
        return ("CHECK", m.start("p"))
    offsets = [mm.start() for mm in _WORD_RE.finditer(s)]
    for k, w in enumerate(words):
        tg = word_tags(w)
        if "prod" in tg or tg & {"negaffix", "fuzzy"} or not any(t.startswith("v:") or t == "adj" for t in tg):
            continue
        if "v:base" in tg and not tg & {"v:past", "v:part", "adj", "v:3sg", "v:es3", "v:espret", "v:espret1", "v:espret3"} and \
                not (k > 0 and words[k - 1] in ("would", "i'd", "we'd", "he'd", "she'd", "they'd", "it'd")):
            continue  # a base form is an instruction or an infinitive ("then check it against ..."), unless "would" governs it
        if "adj" in tg and not tg & {"v:past", "v:part"} and k > 0 and words[k - 1] in ("a", "an", "the", "un", "una", "el", "la") and \
                k + 1 < len(words):
            continue  # an attributive adjective ("A marker would look for a clear definition of elasticity here."): no act (c3f)
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


#: A deduction or penalty an assessor takes from the answer: a criticism word of V2 ("with no deductions"; c3f).
_DEDUCTION_WORDS = frozenset("deduction deductions penalty penalties descuento descuentos".split())
_MARK_DOWN_RE = re.compile(r"\bmark(?:s|ed|ing)?\s+(?:[^\W\d_]+\s+){0,4}?down\b", re.I)


def _governs(s: str, words: list[str], neg: int, crit: int) -> bool:
    """Whether the negator ``words[neg]`` governs the criticism word ``words[crit]``: no semicolon or bracket stands between them (a
    negator in another clause or outside an aside, "He governed without a majority (the specialist flags these dates as from memory)."),
    and a "without"/"sin" negates only its own complement of at most three words ("without a single error", never "without a majority;
    the specialist flags these dates"; check round 12 of c3f)."""
    if words[neg] in ("without", "sin") and crit - neg > 3:
        return False
    spans = [m.span() for m in _WORD_RE.finditer(s)]
    if len(spans) != len(words):
        return True
    return re.search(r"[;()\[\]]", s[spans[neg][1]:spans[crit][0]]) is None


def _criticism(words: list[str]) -> bool:
    return any(_crit_at(words, k) for k in range(len(words))) or \
        _has_any(words, frozenset(("red pen", "red ink", "point off", "points off", "un punto", "ni un punto", "deduction", "deductions",
                                   "penalty", "penalties", "descuento", "descuentos")))


#: Words, besides the lexicon's assessment classes, that one of the frames turns on (a stake, an ideal, an exit code, quoted words).
_FRAME_WORDS = frozenset("bet bets wager stake swear apuesto apostaria juego pondria dream delight ideal joy favourite favorite wish "
                         # (c3f: a quality label, a tool's same values, an assessor's want, a deduction, a confirmation, a word applied)
                         "reliability accuracy precision correctness validity soundness confidence certainty fiabilidad confiabilidad "
                         "exactitud precision validez solidez calidad confianza certeza seguridad salieron salio salen coincidieron "
                         "coincidio cuadraron iguales identical want wants wanted deduction deductions penalty penalties descuentos "
                         "confirm certify guarantee attest confirmo certifico garantizo aseguro confirmar certificar garantizar "
                         "applies describes fits aplica describe "
                         "paradise heaven exit exited exits returned return returns code status words verdict comment comments note "
                         "remark remarks feedback survive survives survived surviving withstand withstands withstood stand weather "
                         "weathered resiste resisten resistiria aguanta aguantaria vouch vouches vouched back backs backed bear bears "
                         "bore borne sign signs signed da dar dio daria respalda respaldo avala avalo "
                         # (c3f, check round 12: a score label, a quality beyond question, praise)
                         "score scores mark marks grade rating nota puntuacion calificacion irrefutable irrefutables incuestionable "
                         "incuestionables indiscutible indiscutibles intachable intachables irreprochable irreprochables inobjetable "
                         "inobjetables unassailable unimpeachable unquestionable indisputable incontestable praise praises praised "
                         "commend commends commended applaud applauds applauded admire admires admired laud lauds lauded "
                         "elogiaria elogiarian alabaria alabarian unscathed satisfying".split())
_TRIGGER_TAGS = frozenset({"C:m_def", "C:m_pos", "C:m_check", "C:m_doubt", "defectverb", "negaffix"})


@functools.lru_cache(maxsize=65536)
def _trigger(w: str) -> bool:
    tg = word_tags(w)
    return w in _FRAME_WORDS or bool(tg & _TRIGGER_TAGS) or any(t.startswith("F:") for t in tg)


@functools.lru_cache(maxsize=65536)
def trigger_word(raw: str) -> bool:
    """Whether the word ``raw`` (as written) is one a frame of this module turns on (cached per spelling)."""
    return _trigger(fold_word(raw))


#: A question the sentence asks: a Spanish "¿ ... ?", or the words before a "?" back to the last stop, colon, semicolon or question.
_QUESTION_SPAN_RE = re.compile(r"¿[^?¿]*\?|[^.!?;:¿]*\?")
#: A boundary between coordinated clauses, each a statement of its own (", and", ", y", ", so", "; ", a spaced dash); an adversative
#: (", but", ", pero") concedes the clause before it, so its clauses are read together (in windows when the sentence is long).
_COORD_RE = re.compile(r"\s*(?:;|,\s*(?:and|so|y|e|as[ií]\s+que)\b|\s[—–]\s|\s-\s)\s*", re.I)
#: A sentence that opens with a condition, a concession or a hedge: its clauses are read together, never apart.
_CONDITION_LEAD_RE = re.compile(r"^\W*(?:if|unless|when|whenever|whether|although|though|suppose|supposing|assuming|provided|once|"
                                r"si|cuando|aunque|a\s+menos|siempre\s+que|en\s+caso|it\s+is\s+not\s+true|no\s+es\s+cierto)\b", re.I)
_WORD_SPAN_RE = re.compile(r"\S+")


def clause_pieces(sentence: str) -> list[str]:
    """The pieces of ``sentence`` a frame of this module reads besides the sentence itself (c3f, the push check of a9129c78: a
    sentence over 400 characters or with a "?" anywhere was passed over whole, so an own verdict joined to long content or after a
    question was delivered). A question frees only the words that ask it; the rest is read in its coordinated clauses (", and this
    is a marker's dream of an answer"), and a clause over 400 characters in windows of at most 400 characters that overlap by half,
    so every own verdict of 400 characters or fewer lies whole in one window. Each piece is at most 400 characters and the pieces
    hold at most twice the sentence's characters: the reading stays linear."""
    if not isinstance(sentence, str):
        return []
    rest = _QUESTION_SPAN_RE.sub(" ; ", sentence) if ("?" in sentence or "¿" in sentence) else sentence
    if _CONDITION_LEAD_RE.match(rest):
        parts = [rest]
    else:
        parts = [p for p in _COORD_RE.split(rest) if p and p.strip()]
    out: list[str] = []
    for p in parts:
        p = p.strip(" ,;")
        if not p or not any(c.isalpha() for c in p):
            continue
        if len(p) <= _MAX:
            out.append(p)
            continue
        spans = [(m.start(), m.end()) for m in _WORD_SPAN_RE.finditer(p)]
        k = 0
        while k < len(spans):
            j = k
            while j + 1 < len(spans) and spans[j + 1][1] - spans[k][0] <= _MAX:
                j += 1
            out.append(p[spans[k][0]:spans[j][1]])
            if j + 1 >= len(spans):
                break
            # (the next window starts half way through this one: an own verdict of up to 200 characters is whole in one of them)
            half = spans[k][0] + _MAX // 2
            k2 = next((q for q in range(k + 1, j + 1) if spans[q][0] >= half), j + 1)
            k = max(k + 1, k2 if k2 <= j else j + 1)
    return [x for x in out if x != sentence]


def read_by_clauses(sentence: str, read_one) -> Optional[tuple[str, str]]:
    """``read_one(piece)`` of the sentence whole (when it is at most 400 characters and asks no question), else of the first of
    :func:`clause_pieces` that reads as an own verdict; None when none does. A safety reading never fails open on a sentence's
    length or punctuation."""
    if not isinstance(sentence, str):
        return None
    if len(sentence) <= _MAX and "?" not in sentence and "¿" not in sentence:
        got = read_one(sentence)
        if got is not None:
            return got
        if not _COORD_RE.search(sentence):
            return None
    for piece in clause_pieces(sentence):
        got = read_one(piece)
        if got is not None:
            return got
    return None


def own_verdict(sentence: str, ctx) -> Optional[tuple[str, str]]:
    """``(rule, family)`` of an own verdict of frames V1 to V4 (module docstring) in ``sentence`` as written, or None. A sentence
    with no word any frame turns on is passed over after one lookup per word (most sentences of an answer). A long sentence, or one
    with a question in it, is read in its clauses (:func:`read_by_clauses`)."""
    if not isinstance(sentence, str):
        return None
    return read_by_clauses(sentence, lambda piece: _own_verdict_one(piece, ctx))


def _own_verdict_one(sentence: str, ctx) -> Optional[tuple[str, str]]:
    try:
        return _own_verdict_cached(sentence, ctx)
    except TypeError:  # (an unhashable context: read uncached)
        return _own_verdict(sentence, ctx)


@functools.lru_cache(maxsize=8192)
def _own_verdict_cached(sentence: str, ctx) -> Optional[tuple[str, str]]:
    return _own_verdict(sentence, ctx)


def _own_verdict(sentence: str, ctx) -> Optional[tuple[str, str]]:
    if "\n" in sentence:
        # a word broken at a line end ("revi-\nsado", "re-\nvisado") is read joined when the joined letters are a word of the lexicon,
        # as the reader's normaliser reads it (check round 12 of c3f)
        sentence = _LINE_BREAK_WORD_RE.sub(lambda m: m.group(1) + m.group(2) if word_tags(fold_word(m.group(1) + m.group(2))) else m.group(0),
                                           sentence)
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
    delivered = _DELIVERY_RE.search(s) is not None
    # (the answer's own content named as what was delivered to the reader, "These results were validated before being sent to
    # you.": its own scope whatever noun names it; c3f)
    strong = sets["strong"].search(s) is not None or (delivered and (sets["parts_dem"].search(s) is not None or
                                                                     _pronoun_subject(words) or _QUANT_SCOPE_RE.search(s) is not None)) or \
        _OWN_SCOPE_EXTRA_RE.search(s) is not None
    weak = strong or _WEAK_SCOPE_RE.search(s) is not None or sets["parts_dem"].search(s) is not None or _pronoun_subject(words) or \
        _QUANT_SCOPE_RE.search(s) is not None  # (a quantifier over this text itself, "any of this", "nothing above"; c3f)
    assessor = _has_any(words, sets["assessors"])
    internal = _has_any(words, sets["internal"])
    finder = any(w in ("nobody", "noone", "nadie", "anyone", "anybody", "cualquiera") for w in words) or "no one" in s.lower()
    negs, es = _neg_count(words, s)
    hedged = _HEDGE_RE.search(s) is not None
    deontic = _DEONTIC_RE.search(s) is not None
    first_imperative = "C:imperative_verbs" in word_tags(words[0]) and not word_tags(words[0]) & {"C:pron1", "C:det", "C:anaph"} and \
        len(words) > 1 and words[0] not in ("this", "that", "these", "all", "every", "each", "nothing", "no", "my", "our")

    # V4: a pipeline's success code on this answer (a solver's success result too: "Z3 returned a satisfying model for every claim
    # made here"; check round 12 of c3f)
    if (internal or any(w in _RUNNERS for w in words)) and weak and negs == 0 and not hedged and (
            _SUCCESS_CODE_RE.search(s) or _TOOL_RESULT_RE.search(s)):
        return ("G5", "STATUS")
    # (c3f, check round 12) a score or mark given to this answer as a label, a decimal one included
    if not marking and _OWN_SCORE_LABEL_RE.match(written):
        return ("G1", "SCORE")
    # (c3f, check round 12) a quality beyond question said of the answer's own scope
    if strong and negs == 0 and not hedged and _BEYOND_QUESTION_RE.search(s) and _BE_RE.search(s):
        return ("G1", "QUALITY")
    # (c3f, check round 12) the answer's own scope coming through a check with nothing found against it; its "without" is the
    # verdict's own, never a negator of it
    if weak and not hedged and _CAME_THROUGH_RE.search(s) and _SCRUTINY_RE.search(s) and _UNSCATHED_RE.search(s) and \
            _neg_count(words, _UNSCATHED_RE.sub(" ", s))[0] == 0:
        return ("G1", "QUALITY")
    # (c3f, check round 12) an assessor's praise of this answer
    if assessor and strong and negs == 0 and not hedged and not marking and _PRAISE_RE.search(s):
        return ("G1", "QUALITY")
    # V3 (quoted): an assessor's own words about the answer, read as the writer's
    m = _QUOTED_WORDS_RE.search(written)
    if m is not None and not marking and _has_any(_words(m.group("who")), sets["assessors"]):
        from .reader import read_text
        from .reader import Context as _Ctx
        inner = m.group("q")
        if read_text(inner, ctx if isinstance(ctx, _Ctx) else _Ctx())[0]:
            return ("G7", "QUALITY")
    # (c3f) a quality, reliability or confidence label of this answer with a positive degree ("Fiabilidad de esta respuesta: total.")
    lab = _QUALITY_LABEL_RE.match(written)
    if lab is not None and not marking and _QUALITY_KEY_RE.search(lab.group("key")) and \
            _POSITIVE_DEGREE_RE.match(lab.group("val")) and (sets["strong"].search(lab.group("key")) is not None or
                                                             sets["parts_dem"].search(lab.group("key")) is not None):
        return ("G4", "STATUS")
    # (c3f) a word quoted and said to apply to this answer, its lines or its parts: the writer's verdict, no gloss
    wa = _WORD_APPLIES_RE.search(written)
    if wa is not None and not marking and _family(fold_word(wa.group("w").strip().split()[-1] if wa.group("w").strip() else "")) & \
            {"CHECK", "STATUS", "OUTCOME", "QUALITY", "APPROVE"} and negs == 0 and not hedged:
        rest = wa.group("rest")
        if sets["strong"].search(rest) is not None or _QUANT_SCOPE_RE.search(rest) is not None or (
                sets["blanket"].search(rest) is not None and re.search(r"\b(?:above|below|here|arriba|abajo|aqu[ií])\b", rest, re.I)):
            return ("G1", "STATUS")
    # (c3f) the writer's performative confirmation of a verdict on this answer ("I can confirm this answer is accurate.")
    perf = _PERFORMATIVE_RE.search(s)
    if perf is not None and not marking and (strong or weak) and negs == 0 and not hedged and not deontic:
        after = _words(s[perf.end():])
        if _RIGHT_RE.search(s, perf.end()) or any(_family(w) & {"OUTCOME", "QUALITY", "CHECK", "STATUS", "APPROVE"} for w in after):
            return ("G2", "CHECK")
    # (c3f) a tool's re-run of this answer's values giving the same or the stated ones
    if internal and (strong or weak) and negs == 0 and not hedged and _TOOL_SAME_RE.search(s):
        return ("G2", "CHECK")
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
        if not (assessor or internal) and not sets["named_answer"].search(s) and not delivered:
            party_ok = False  # an outside party's check of the figures "above" or "quoted above" is a named source's check of the
            # subject matter the answer cites ("The World Bank has verified every figure above.", boundary (b)); only a check of
            # the answer named by its own noun is read ("... the numbers in this reply", "Este texto ...")
        if not (assessor or internal) and _TEXT_ONLY_RE.search(s) and not sets["strong_answer"].search(s) and \
                not _NAMED_AGENT_RE.search(s) and not (act[1] < 0 and not re.search(r"\b(?:by|por)\b", s, re.I)):
            # (a check noun this text has had with no agent, "This text has had a full editorial review.", is read as the
            # agentless passive "This text has been reviewed." is; c3f)
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
                           w in _DEDUCTION_WORDS or
                           (w in ("mark", "marks", "marked", "marking") and "down" in words[k + 1:k + 6]) or
                           (single_crit and "F:CHECK" in word_tags(w) and k > 0 and words[k - 1] in ("sola", "solo", "single", "una", "un",
                                                                                                   "one", "a"))), None)
        crit_w = words[first_crit] if first_crit is not None else ""
        act_not_done = crit_w.startswith(_ACT_STEMS) and word_tags(crit_w) & {"v:part", "v:past", "v:espret", "v:espret1", "v:espret3",
                                                                               "v:3sg", "v:es3"} and \
            not _CONDITIONAL_RE.search(s) and not re.search(r"\b(?:nothing|nada|anything|algo)\s+(?:to|que)\b", s, re.I)
        if first_neg is not None and first_crit is not None and first_neg < first_crit and not act_not_done and \
                _governs(s, words, first_neg, first_crit):
            return ("G8", "DEFECT")
    if negs:
        return None
    # V3: a quality an assessor would see, the answer surviving scrutiny, the writer's stake
    if assessor and weak and _IDEAL_RE.search(s):
        return ("G1", "QUALITY")
    if assessor and weak and _DELIGHT_RE.search(s):
        return ("G1", "QUALITY")
    if assessor and weak and _WANT_RE.search(s) and ":" not in s:
        return ("G1", "QUALITY")  # (what the assessors want, said of this text; c3f)
    if assessor and _TOP_GRADE_RE.search(s):
        return ("G1", "SCORE")
    if weak and _SURVIVE_RE.search(s) and _SCRUTINY_RE.search(s):
        return ("G1", "QUALITY")
    if _STAKE_RE.search(s) and _RIGHT_RE.search(s) and (weak or re.search(r"\b(?:it|esto|eso|todo)\b", s, re.I)):
        return ("G1", "CONFIDENCE")
    return None
