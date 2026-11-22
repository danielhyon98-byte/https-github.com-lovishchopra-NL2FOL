"""The compositional self-certification reading (design sections 3.2 to 3.9).

For every assessment TRIGGER of a clause (a word of a family of section 3.3: a check act, an outcome, an agreement, a quality, a
source evaluation, a confidence, a score, a status, an approval, an assurance, a compliance, a fidelity or a negated defect) the
reader asks four questions: WHAT is assessed (the theme and its scope class: the answer A, neutral N, outside O, the student's work T
in a marking task, implicit I), WHO is credited (the evaluator: internal, assessor, outside, a negated generic one), WHAT outcome
with WHICH polarity (negations counted, weak modals and definite defects), and in WHICH mood or frame (a question, a condition, an
instruction, a method, a worked computation, a quotation of an outside source...). A positive, asserted trigger that no frame
exempts is gated when a gate rule G1 to G9 applies. The lexicon holds only classes of words; no rule here names a sentence.

Every window is bounded (a theme NP at most 8 tokens, a quotation frame 12 tokens before and 8 after, idioms at most 6 tokens), so
the work per token is bounded and the reading is linear in the input length; a sentence longer than 4,000 characters is read in
overlapping windows.
"""
from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass, replace as _dc_replace
from typing import Optional

from .lexicon import fuzzy_target, lexicon, tags as word_tags, fold_word
from .normalise import TOKEN_WORDS, fold_table, letter_like
from .encoded import encoded_hits, join_split_sentences, spelled_hits, transformed_line_hits
from .misspelt import frame_hits

__all__ = ["Context", "Hit", "Unread", "Reading", "read_text", "plain_tick_bullets"]

# ================================================================================================================== records


@dataclass(frozen=True)
class Context:
    """The reading context. ``marking`` comes ONLY from the router's plan task type (``context_for``), never a report's own field;
    ``known_sources`` are the titles and authors of the request's supplied texts; ``peer_documents`` the names, titles and agent ids
    of supplied peer reports."""
    writer: str = "specialist"
    marking: bool = False
    known_sources: tuple[str, ...] = ()
    peer_documents: tuple[str, ...] = ()
    #: whether the ROUTER's request asks a true-or-false (correct-or-incorrect) item: then "Answer: correct" answers it (X10);
    #: otherwise such a label is a verdict on the answer (attack round 3)
    truth_item: bool = False


@dataclass(frozen=True)
class Hit:
    rule: str
    family: str
    form: str
    start: int
    end: int
    piece: str


@dataclass(frozen=True)
class Unread:
    kind: str
    start: int
    end: int
    piece: str


@dataclass(frozen=True)
class Reading:
    hits: tuple[Hit, ...]
    unread: tuple[Unread, ...]

    def self_certifies(self) -> bool:
        return bool(self.hits)

    def refuses(self) -> bool:
        return bool(self.hits or self.unread)


# ================================================================================================================== tokens
_PUNCT_CLAUSE = frozenset(";")
_DASHES = frozenset("—–")
_REL = frozenset("=≈≤≥<>≠")
_OPS = frozenset("+×*÷/^−-")


class Tok:
    __slots__ = ("raw", "w", "t", "a", "b", "cap", "upper", "num", "punct", "idiom", "parts", "init")

    def __init__(self, raw: str, a: int, b: int, *, w: Optional[str] = None, t: Optional[frozenset] = None, idiom: bool = False,
                 parts: tuple = ()):
        self.raw = raw
        self.a = a
        self.b = b
        if w is None and t is None:
            # a plain token: its word, classes and flags are a function of its spelling alone (the same spelling recurs: "(A1)" x
            # 6,000, '"a"' x 5,000), derived once per spelling
            self.w, self.punct, self.t, self.cap, self.upper, self.num, self.idiom = _tok_fields(raw)
            self.idiom = self.idiom or idiom
        else:
            self.w, self.punct, self.t, self.cap, self.upper, self.num, self.idiom = _derive_fields(raw, w, t, idiom)
        self.parts = parts
        self.init = False

    @property
    def name(self) -> bool:
        """A capitalised word not at the start of its sentence, clause or label value: a proper name."""
        return self.cap and not self.init and not self.upper

    def has(self, *tg: str) -> bool:
        return not self.t.isdisjoint(tg)

    def fam(self) -> set[str]:
        return {x[2:] for x in self.t if x.startswith("F:")}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Tok({self.w!r})"


def _derive_fields(raw: str, w: Optional[str], t: Optional[frozenset], idiom: bool) -> tuple:
    """(w, punct, t, cap, upper, num, idiom) of a token spelled ``raw`` (``w`` and ``t`` given by a merged idiom or a markup token)."""
    w = w if w is not None else fold_word(raw)
    punct = not any(c.isalnum() for c in raw) and not w.startswith("zz")
    given_t = t is not None
    t = t if given_t else (frozenset() if punct else word_tags(w))
    if not given_t and not punct and (w.endswith("'s") or w.endswith("s'")) and len(w) > 3 and \
            w not in ("it's", "that's", "let's", "here's", "there's", "what's", "who's", "he's", "she's"):
        base = w[:-2] if w.endswith("'s") else w[:-1]
        t = frozenset(t | {x for x in word_tags(base) if x.startswith("C:eval") or x in ("C:tool", "C:assess_instrument",
                                                                                     "C:src_noun", "C:genre")} | {"poss"})
    if "fuzzy" in t and not given_t:
        target = fuzzy_target(w)
        if target:
            w = target
    if not given_t and raw[-1:] in "\u00e9\u00f3\u00c9\u00d3" and "lang:es" in t:
        # a written accent on the last vowel marks the Spanish preterite ("validó", "revisé"), never the present "valido" or an
        # English imperative "revise" that the accent-folded form shares
        t = frozenset((t - {"v:es1", "C:imperative_verbs"}) | ({"v:espret1"} if raw[-1:] in "\u00e9\u00c9" else {"v:espret3"}))
    if not given_t and raw.lower() in _ES_ACCENTED_COPULA:
        t = frozenset(t | {"C:copula", "C:aux", "lang:es"})
    cap = raw[:1].isupper()
    upper = len(raw) >= 2 and raw.isupper() and any(c.isalpha() for c in raw)
    return w, punct, t, cap, upper, _number(w), idiom or "idiom" in t


@functools.lru_cache(maxsize=65536)
def _tok_fields(raw: str) -> tuple:
    return _derive_fields(raw, None, None, False)


def _number(w: str) -> bool:
    if not w:
        return False
    x = w.rstrip("%").replace(",", "").replace(".", "", 1)
    return x.isdigit() or (x[:1] == "-" and x[1:].isdigit())


_CONTRACTED = frozenset("they you he she it there that who what".split())
#: Spanish copula forms whose accent-folded spelling is another word ("esté" folds to the demonstrative "este").
_ES_ACCENTED_COPULA = frozenset("esté estés estén está están fueran fuera fuesen fuese sean sea".split())


def _tokens(s: str, a: int, b: int) -> list[Tok]:
    """The tokens of ``s[a:b]``: words (with internal apostrophes, hyphens, periods, slashes and digit commas), numbers with a
    percent sign, reading tokens, and single punctuation marks. One pass."""
    out: list[Tok] = []
    i = a
    while i < b:
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c == "_" and i - 2 >= a and i + 2 < b and s[i - 1].isalpha() and s[i - 2].isalpha() and s[i + 1].isalpha() and \
                s[i + 2].isalpha():
            # an identifier's joint ("FAITHFUL_CHAIN", "INCONSISTENT_PREMISES"): its words are read as a phrase, the attributive
            # word before the head noun included (a status word in it keeps its reading)
            i += 1
            continue
        if c.isalnum():
            j = i + 1
            while j < b:
                d = s[j]
                if d.isalnum():
                    j += 1
                    continue
                if d in "'’-./" and j + 1 < b and s[j + 1].isalnum():
                    if d == "." and (s[j - 1].islower() or s[j - 1].isdigit()) and s[j + 1].isupper() and j + 2 < b and \
                            s[j + 2].isalpha():
                        break  # a stop glued to the next sentence ("15 km/h.VERIFIED"): two words, read on each side of the stop
                    j += 1
                    continue
                if d == "," and s[j - 1].isdigit() and j + 1 < b and s[j + 1].isdigit():
                    j += 1
                    continue
                if d == "%":
                    j += 1
                break
            if j < b and s[j] in "'’" and s[j - 1] in "sS" and (j + 1 >= b or not s[j + 1].isalnum()):
                j += 1  # a plural possessive: "Participants'"
            if j < b and s[j] == "*" and j - i == 1:
                j += 1  # "A*"
            raw = s[i:j]
            if i > a and s[i - 1] == "\\":
                # a LaTeX command ("\right", "\left", "\checkmark"): markup of a formula, never a word of the language
                out.append(Tok("\\" + raw, i - 1, j, w="\\" + raw.lower(), t=frozenset()))
                i = j
                continue
            ap = max(raw.find("'"), raw.find("\u2019"))
            if ap > 0 and raw[:ap].lower() in _CONTRACTED and raw[ap + 1:].lower() in ("re", "ve", "ll", "d"):
                # a pronoun contraction ("they're", "you've"): the pronoun and the auxiliary are two words of the clause
                out.append(Tok(raw[:ap], i, i + ap))
                out.append(Tok("'" + raw[ap + 1:], i + ap, j))
            else:
                out.append(Tok(raw, i, j))
            i = j
            continue
        j = i + 1
        while j < b and s[j] == c and c not in "\u201c\u201d\"'":
            j += 1
        out.append(Tok(s[i:j] if j - i <= 3 else c * 3, i, j))
        i = j
    return out


def _merge(toks: list[Tok]) -> list[Tok]:
    """Merge the idioms of the lexicon (longest match at each position, at most six tokens) into one token each."""
    lex = lexicon()
    out: list[Tok] = []
    i = 0
    n = len(toks)
    idioms = lex.idioms
    ws = [t.w for t in toks]
    while i < n:
        t = toks[i]
        best = None
        for cand, tg in idioms.get(ws[i], ()):
            k = len(cand)
            # (the first word matches by the lookup; the second is compared before the rest is sliced)
            if k <= n - i and (k == 1 or (ws[i + 1] == cand[1] and (k == 2 or tuple(ws[i + 2:i + k]) == cand[2:]))):
                if best is None or k > len(best[0]):
                    best = (cand, tg)
        if best is not None and best[0] == ("in", "order") and i + 2 < n and ws[i + 2] in ("to", "that", "for"):
            best = None  # "in order to find and correct mistakes": a purpose, never the outcome "in order" (check round 9 of c3c)
        if best is not None:
            k = len(best[0])
            parts = tuple(toks[i:i + k])
            tg = set(best[1]) | {x for x in parts[0].t if x.startswith("v:")}
            out.append(Tok(" ".join(x.raw for x in parts), parts[0].a, parts[-1].b, w=" ".join(best[0]), t=frozenset(tg), idiom=True,
                           parts=parts))
            i += k
            continue
        out.append(t)
        i += 1
    out = _pass_frames(_stake_frames(out))
    # (the two frames of c3d are tried only on a sentence that holds their words: one look at its words, not one per frame)
    ws = {t.w for t in out}
    if not _STANDARD_NOUNS.isdisjoint(ws):
        out = _standard_frames(out)
    if not _TRY_VERBS.isdisjoint(ws):
        out = _attempt_frames(out)
    return out


_TRY_VERBS = frozenset("try tries tried trying".split())
_BREAK_VERBS = frozenset("break refute falsify disprove fault crack".split())
_TRY_ADVERBS = frozenset("hard harder really repeatedly genuinely seriously very my our best".split())


def _attempt_frames(toks: list[Tok]) -> list[Tok]:
    """An attempt to break or refute ("tried to break it", "tried hard to break it", "tried my best to refute it"; c3d): an
    adversarial test, read as the lexicon's idiom of that test (``m_check``) whatever adverbs stand between the verb and "to".
    Linear (each try verb looks at most four tokens ahead)."""
    if not any(t.w in _TRY_VERBS for t in toks):
        return toks
    out: list[Tok] = []
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t.w in _TRY_VERBS:
            j = i + 1
            while j < n and j - i <= 3 and toks[j].w in _TRY_ADVERBS:
                j += 1
            # ("hard to" is merged as one idiom token before this frame reads it)
            to = j + 1 < n and (toks[j].w == "to" and j > i + 1 or (toks[j].w.split()[-1] == "to" and toks[j].w.split()[0] in
                                                                   _TRY_ADVERBS))
            if to and toks[j + 1].w in _BREAK_VERBS:
                parts = tuple(toks[i:j + 2])
                tg = frozenset({"C:m_check", "idiom"})
                out.append(Tok(" ".join(x.raw for x in parts), parts[0].a, parts[-1].b, w="tried to break", t=tg, idiom=True,
                               parts=parts))
                i = j + 2
                continue
        out.append(t)
        i += 1
    return out


#: Nouns of a standard or grade a piece of work meets (c3d: "an examiner-standard answer", "of publishable quality", "de nivel de
#: examinador"), and the words that make one a standard of assessment when they modify it or follow it with "of"/"de".
_STANDARD_NOUNS = frozenset("standard standards level grade quality calibre caliber class nivel calidad estandar categoria".split())
_STANDARD_MODIFIERS = frozenset("high highest top professional publishable publication publication-ready exam examination examiner "
                                "examiners marker markers distinction excellent exemplary model gold alto alta maximo maxima "
                                "profesional publicable sobresaliente".split())


def _standard_frames(toks: list[Tok]) -> list[Tok]:
    """A standard of assessment (c3d, the push check of af6dfe04): a standard noun (:data:`_STANDARD_NOUNS`) modified by an
    evaluator, a quality or score word or a word of a high or publishable standard ("examiner standard", "publishable quality", "a
    high standard"), or followed by "of"/"de" and such a word ("the standard of an examiner", "de nivel de examinador"): the
    standard the work is said to meet, read as a QUALITY adjective. Whether it is said of THIS answer is the reader's scope reading,
    as for any quality word ("the examiners' standard practice" names no answer). Linear."""
    if not any(t.w in _STANDARD_NOUNS for t in toks):
        return toks

    def assessing(x: Tok) -> bool:
        return x.w in _STANDARD_MODIFIERS or x.has("C:eval_asr", "C:eval_int", "C:m_eval") or bool(x.fam() & {"QUALITY", "SCORE"})

    for i, t in enumerate(toks):
        if t.w not in _STANDARD_NOUNS or t.fam():
            continue
        before = toks[i - 1] if i > 0 else None
        ok = before is not None and not before.punct and assessing(before)
        if not ok and i + 2 < len(toks) and toks[i + 1].w in ("of", "de", "del"):
            j = i + 2
            while j < len(toks) and j - i <= 4 and toks[j].has("C:det", "C:indefinite", "C:definite"):
                j += 1
            ok = j < len(toks) and assessing(toks[j]) and not toks[j].fam() - {"QUALITY", "SCORE", "CHECK"}
        if ok:
            toks[i] = Tok(t.raw, t.a, t.b, w=t.w, t=frozenset(t.t | {"F:QUALITY", "adj"}))
    return toks


#: Spanish verbs of passing a check ("pasar", "superar") and the check nouns they take (attack round 5: "Ha pasado todas las pruebas.",
#: "Esta respuesta pasó los controles del sistema."): the verb reads as the outcome "pass" only before such a noun, so a narrative's
#: "pasó el verano" stays a narrative.
_ES_PASS = frozenset("paso pasa pasan pasado pasada pasaron pase pasamos pasaste supero supera superan superado superada superaron "
                     "supere superamos".split())
_ES_CHECK_OBJECTS = frozenset("prueba pruebas control controles test tests comprobacion comprobaciones verificacion verificaciones "
                              "revision revisiones chequeo chequeos auditoria auditorias filtro filtros validacion validaciones".split())


def _pass_frames(toks: list[Tok]) -> list[Tok]:
    if not any(t.w.split()[-1] in _ES_PASS for t in toks if t.w):
        return toks
    for i, t in enumerate(toks):
        if not t.w or t.w.split()[-1] not in _ES_PASS or t.fam() & {"OUTCOME", "CHECK"}:
            continue
        j = i + 1
        while j < len(toks) and j - i <= 4 and (toks[j].has("C:det", "C:dist", "C:definite") or toks[j].w in (
                "todas", "todos", "cada", "las", "los", "la", "el", "sus", "su")):
            j += 1
        if j < len(toks) and toks[j].w in _ES_CHECK_OBJECTS and j > i:
            nxt = toks[j + 1:j + 3]
            if nxt and nxt[0].w in ("de", "del") and len(nxt) > 1 and not nxt[1].has("C:eval_int", "C:tool", "C:anchor") and \
                    nxt[1].w not in ("calidad", "sistema", "motor", "hub"):
                continue  # "las pruebas de acceso", "los controles de seguridad": a test of the subject, no check of this answer
            toks[i] = Tok(t.raw, t.a, t.b, w=t.w, t=frozenset(t.t | {"F:OUTCOME", "v:past" if t.w.endswith(("o", "on", "ado", "ada")) else
                                                                   "v:3sg"}))
            toks[j] = Tok(toks[j].raw, toks[j].a, toks[j].b, w=toks[j].w, t=frozenset(toks[j].t | {"C:check_noun"}))
    return toks


#: Verbs of staking something on what follows ("bet", "stake", "wager", "jugarse", "apostar"); "put" and "risk" only with the
#: writer's own possession ("put my house on", "risk my life on").
_STAKE_VERBS = frozenset("stake stakes staked staking bet bets betting wager wagers wagered wagering gamble gambles gambled apuesto "
                         "apostaria apostaria apostamos apostar jugaria juego jugamos jugariamos jugarse jugarme".split())
_STAKE_OWN_VERBS = frozenset("put puts putting risk risks risked risking pongo pondria sign signs signed signing firmo firmaria "
                             "firmamos".split())
#: what is staked with no possessive ("I'd put money on every figure above", attack round 7)
_STAKE_NOUNS = frozenset("money cash everything dinero todo".split())
#: (a signature is put "under", "to" or "below" what it vouches for: "I would sign my name under every line of this")
_STAKE_PREPS = frozenset(("on", "upon", "en", "por", "a", "under", "to", "below", "beneath", "bajo"))


def _stake_frames(toks: list[Tok]) -> list[Tok]:
    """A stake frame (attack round 5): a verb of staking, a staked noun phrase of at most three words and "on" before an item of the
    answer ("I'd put my house on every line of this.", "Bet the farm on these numbers.", "Me jugaría mi reputación en estas
    cifras."): a claim of confidence in what follows, read as the lexicon's stake idiom (CONFIDENCE, ASSURE). Composed from word
    classes, never a listed sentence; linear (each verb looks at most eight tokens ahead)."""
    def verb_of(t: Tok) -> str:
        # (a merged idiom that ends in a verb of staking, "I'd bet", reads as that verb: attack round 7)
        return t.parts[-1].w if t.idiom and t.parts and t.parts[-1].w in _STAKE_VERBS else t.w

    if not any(verb_of(t) in _STAKE_VERBS or t.w in _STAKE_OWN_VERBS for t in toks):
        return toks
    out: list[Tok] = []
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        if (verb_of(t) in _STAKE_VERBS or t.w in _STAKE_OWN_VERBS) and i + 2 < n:
            j = i + 1
            while j < n and j - i <= 4 and not toks[j].punct and toks[j].w not in _STAKE_PREPS and not toks[j].fam():
                j += 1
            np_ = toks[i + 1:j]
            ok = 1 <= len(np_) <= 3 and j < n and toks[j].w in _STAKE_PREPS and not any(x.num for x in np_)
            if ok and t.w in _STAKE_OWN_VERBS:
                ok = np_[0].has("C:poss1") or (len(np_) == 1 and np_[0].w in _STAKE_NOUNS)
            if ok:
                after = toks[j + 1:j + 6]
                ok = any(x.has("C:dist", "C:dist_idioms", "C:demonstrative", "C:anchor", "C:anchor_idioms", "C:anaph") or
                         x.w in ("it", "that", "this", "eso", "esto") for x in after[:4]) and not any(
                    x.t - {"C:poss1", "C:det", "C:definite", "C:indefinite", "lang:es"} for x in np_[1:] + np_[:1] if not x.has("C:poss1", "C:det"))
            if ok:
                parts = tuple(toks[i:j])
                out.append(Tok(" ".join(x.raw for x in parts), parts[0].a, parts[-1].b, w="stake my reputation",
                               t=frozenset({"F:CONFIDENCE", "F:ASSURE", "idiom"} | {x for x in t.t if x.startswith("v:")}), idiom=True,
                               parts=parts))
                i = j
                continue
        out.append(t)
        i += 1
    return out


# ================================================================================================================== classes
_FAMS_G5 = frozenset({"CHECK", "STATUS", "APPROVE", "OUTCOME", "QUALITY", "SCORE", "CONFIDENCE", "COMPLY", "MARK", "FIDELITY", "AGREE",
                      "DEFECT", "ASSURE"})
_FAMS_MARKING_FRAG = frozenset({"CHECK", "STATUS", "APPROVE"})
_FAM_ORDER = ("CHECK", "APPROVE", "SCORE", "ASSURE", "CONFIDENCE", "COMPLY", "FIDELITY", "AGREE", "QUALITY", "SRCEVAL", "OUTCOME",
              "STATUS", "DEFECT")
_PERFORMATIVE = frozenset("confirm certify guarantee vouch assure attest confirmo certifico garantizo aseguro".split())
_COMPLETION = frozenset("done complete completed finished performed carried run hecho hecha realizada realizado".split())
_SIGNAL = frozenset("again twice independently myself ourselves thrice separately".split())
_SIGNAL_IDIOMS = frozenset({"a second time", "two times", "three times", "dos veces", "de nuevo", "otra vez"})
_CLITICS = frozenset("lo la los las me te se nos le les".split())
_ES_FIRST = frozenset("he hemos v:es1 v:espret1".split())
_COMPLEMENTIZER = frozenset("that whether que si".split())
_QUESTION_START = frozenset("is are was were do does did has have had can could will would should which what who how why where when "
                            "anything".split())
_SHORT_ANSWER = frozenset("no nothing none nope yes yep yeah correct sure nada ninguno ninguna si absolutely definitely not".split())
_SCORE_FULL_WORDS = frozenset({"zzscorefull", "zzrating"})
_STRUCTURAL_EOP = ("the proof is complete", "this completes the proof", "as required", "hence proved", "which was to be shown",
                   "quod erat demonstrandum", "as was to be shown", "which completes the proof")
_ASSESSMENT_NOUNS = frozenset("accuracy correctness precision validity reliability certainty confidence exactness trustworthiness "
                              "credibility quality exactitud correccion precision fiabilidad".split())
_INSTITUTIONS = frozenset("office ministry commission committee board court parliament senate council bureau agency institute university "
                          "archive archives census government police ons usgs ine imf oecd company firm bank ministerio gobierno "
                          "ayuntamiento comision congress cabinet league".split())
_SUBORD_BOUND = frozenset("when while because until before after once cuando mientras porque hasta whereas".split())
_BE = frozenset("is are was were be been being 's 're am es son fue fueron sido esta estan estaba era".split())
_MENTION_VERBS = frozenset("reply replies type types write enter answer respond click choose select tick mark say put "
                           "responde escribe".split())
_PRESENT_AS = frozenset("presents present presented portrays portray portrayed depicts depict depicted describes describe described shows "
                        "show showed sees see saw regards regard regarded treats treat treated paints painted frames framed casts cast "
                        "renders rendered imagines imagined".split())
_X14_LEMMAS = frozenset("shown proved proven derived established found calculated obtained demonstrated deduced seen noted stated "
                        "defined computed given".split())


def _is_frac_full(w: str) -> Optional[bool]:
    if "/" in w:
        a, _, b = w.partition("/")
        if a.replace(".", "", 1).isdigit() and b.replace(".", "", 1).isdigit():
            try:
                return float(a) == float(b) and float(b) > 0
            except ValueError:  # pragma: no cover
                return None
    return None


def _score_at(toks: list[Tok], i: int) -> int:
    """The length of a full-score expression starting at token ``i`` (0 if none): "full marks", "n/n", "[2/2]", "100%", "A*",
    "a 7" after a scoring verb, "band 7", the score and rating tokens."""
    t = toks[i]
    if t.has("F:SCORE") and t.idiom:
        if t.w in ("a 7", "a seven") and i + 1 < len(toks) and (toks[i + 1].has("C:unit") or toks[i + 1].w == "%"):
            return 0
        return 1
    if t.w in _SCORE_FULL_WORDS:
        return 1
    if _is_frac_full(t.w):
        return 1
    if t.w == "100%" or (t.w == "100" and i + 1 < len(toks) and toks[i + 1].w in ("%", "percent", "per")):
        return 1
    if t.w in ("a*", "sobresaliente", "matricula"):
        return 1
    # a score written with number words ("seven out of seven", "siete sobre siete", "10 sobre 10": attack round 5) reads as with digits
    nv = _number_value(t)
    if nv is not None and i + 2 < len(toks) and (toks[i + 1].w == "sobre" or (toks[i + 1].w == "out" and i + 3 < len(toks) and
                                                                            toks[i + 2].w == "of")):
        k_den = i + 2 if toks[i + 1].w == "sobre" else i + 3
        dv = _number_value(toks[k_den])
        if dv is not None:
            if i >= 2 and toks[i - 1].w in ("to", "-", "or", "and", "a", "y", "o") and _number_value(toks[i - 2]) is not None:
                return 0  # the top of a range ("1 to 2 out of 2"): the score may be the lower figure, no full score claimed
            after = toks[k_den + 1] if k_den + 1 < len(toks) else None
            if after is not None and not after.punct and after.w.isalpha() and len(after.w) > 2 and not after.fam() and \
                    after.w not in ("marks", "mark", "points", "point", "stars", "puntos", "estrellas", "for", "from", "on", "in", "by",
                                    "and", "with", "para", "por", "con", "en", "del", "the", "this", "esta", "este", "here", "aqui",
                                    "possible", "available", "posibles"):
                return 0  # "7 out of 7 people came": a count of the subject's people or things, no score
            return k_den - i + 1 if nv == dv and nv > 0 else 0
    if t.num and i + 2 < len(toks) and toks[i + 1].w == "/" and toks[i + 2].num:
        try:
            return 3 if float(t.w.replace(",", "")) == float(toks[i + 2].w.replace(",", "")) and float(t.w.replace(",", "")) > 0 else 0
        except ValueError:  # pragma: no cover
            return 0
    return 0


_NUMBER_WORDS = {w: n for n, ws in enumerate((
    (), ("one", "uno", "una"), ("two", "dos"), ("three", "tres"), ("four", "cuatro"), ("five", "cinco"), ("six", "seis"),
    ("seven", "siete"), ("eight", "ocho"), ("nine", "nueve"), ("ten", "diez"), ("eleven", "once"), ("twelve", "doce"),
    ("thirteen", "trece"), ("fourteen", "catorce"), ("fifteen", "quince"), ("sixteen", "dieciseis"), ("seventeen", "diecisiete"),
    ("eighteen", "dieciocho"), ("nineteen", "diecinueve"), ("twenty", "veinte"))) for w in ws}
_NUMBER_WORDS.update({"hundred": 100, "cien": 100, "a hundred": 100, "one hundred": 100})


def _number_value(t: "Tok") -> Optional[float]:
    """The value of a number token, digits or a number word up to twenty ("seven", "siete"); None otherwise."""
    if t.num:
        try:
            return float(t.w.replace(",", ""))
        except ValueError:
            return None
    return _NUMBER_WORDS.get(t.w)


# ================================================================================================================== NP classes
def nxt_is_object(toks: list[Tok], i: int) -> bool:
    """Whether the token after ``i`` opens an object noun phrase (a determiner, a possessive, a number or a name)."""
    if i + 1 >= len(toks):
        return False
    n = toks[i + 1]
    return n.has("C:det", "C:demonstrative", "C:poss1", "C:poss3") or n.num or n.name or _possessive(n)


def _unknown_name(t: Tok) -> bool:
    """A capitalised word the lexicon does not know (a name even at the start of its sentence: "Kershaw has checked ...")."""
    return t.cap and not t.upper and not t.t and not t.num and t.w.isalpha() and len(t.w) > 2


def _tool_instrument(window: list[Tok]) -> bool:
    """An instrument phrase naming an internal tool ("on my GDC", "with the calculator", "in GeoGebra"): a production verb with it
    is a check (the work redone on the writer's tool)."""
    for k, x in enumerate(window[:6]):
        if x.w in ("on", "with", "in", "using", "via", "through", "con", "en") and any(
                y.has("C:tool") or y.w in _STRONG_TOOLS for y in window[k + 1:k + 5]):
            return True
    return False


_MANNER_PAIRS = frozenset({("by", "hand"), ("on", "paper"), ("in", "my head"), ("in", "head"), ("a", "mano"), ("de", "cabeza"),
                           ("a", "lapiz"), ("con", "lapiz"), ("from", "scratch"), ("without", "calculator"), ("sin", "calculadora")})
_MANNER_WORDS = frozenset("mentally longhand manually manualmente mentalmente".split())


def _manner_of_production(window: list[Tok]) -> bool:
    """A production verb's manner ("calculated everything BY HAND", "did it all ON PAPER", "worked out mentally", "a mano"): how the
    working was produced, a method note and no check (attack round 4, boundary b), unless a check signal of its own goes with it
    ("again", "twice", "independently", a re- verb, an outcome clause)."""
    ws = [x.w for x in window if not x.punct and x.w not in ("a", "an", "the", "my", "mi") or x.w in ("a",)]
    for k, w in enumerate(ws):
        if w in _MANNER_WORDS or w in ("by hand", "on paper", "a mano"):
            return True
        if k + 1 < len(ws) and ((w, ws[k + 1]) in _MANNER_PAIRS or (w in ("without", "sin") and ws[k + 1] in ("calculator", "calculadora"))):
            return True
        if k + 2 < len(ws) and w in ("without", "sin") and ws[k + 2] in ("calculator", "calculadora", "gdc", "computer", "software"):
            return True
    return False


def _possessive(t: Tok) -> bool:
    w = t.w
    if w in ("it's", "that's", "let's", "here's", "there's", "what's", "who's", "he's", "she's", "everything's", "this's"):
        return False
    return (w.endswith("'s") or w.endswith("s'")) and len(w) > 2


def _np_end(toks: list[Tok], i: int, limit: int = 10) -> int:
    """The end of the noun phrase starting at ``i``: up to a verb, a clause mark, a complementizer, or ``limit`` tokens; "of"
    after a quantifier continues it."""
    j = i
    n = len(toks)
    while j < n and j - i < limit:
        t = toks[j]
        if t.punct and t.w not in ("-", "/", "'", "(", ")"):
            break
        if j > i and (t.has("C:aux", "C:copula") or _finite(toks, j, subject_seen=True)) and not t.has("C:det"):
            break
        if j > i and t.w in _COMPLEMENTIZER:
            break
        if j > i and t.has("C:coordinator") and t.w not in ("and", "y", "e", "or", "o"):
            break
        j += 1
    return j


#: The classes some reading of :func:`_finite` answers True from.
_FINITE_TAGS = frozenset(("C:aux", "C:copula", "F:PROVENANCE", "v:3sg", "v:past", "v:es1", "v:es3", "v:espret", "v:espret1", "v:espret3",
                          "v:base", "C:report_verb", "C:descr", "C:output_verb"))


def _finite(toks: list[Tok], i: int, subject_seen: bool = False) -> bool:
    """Whether token ``i`` is a finite verb (a lexicon verb form not used as a noun)."""
    t = toks[i]
    if t.t.isdisjoint(_FINITE_TAGS):
        return False  # no verb class at all (every reading below that answers True needs one of these classes)
    if t.has("C:aux", "C:copula"):
        return True
    if t.idiom and t.has("F:PROVENANCE") and t.w.split()[0] in ("come", "comes", "came", "rests", "rest", "derives", "derive"):
        return True
    prev = toks[i - 1] if i > 0 else None
    if prev is not None and (prev.has("poss") or _possessive(prev)):
        return False
    # a noun-capable form directly before an auxiliary or a copula heads the subject, never a finite verb ("the synthesized claims
    # are ...", "the merged results have been ...": a finite verb is not followed by a finite auxiliary)
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    if prev is not None and nxt is not None and nxt.has("C:aux", "C:copula") and t.has("C:part", "C:genre", "C:check_noun", "noun"):
        return False
    if prev is not None and prev.has("C:det", "C:dist") and prev.w not in ("that",):
        pp = toks[i - 2] if i > 1 else None
        verb_only = t.has("v:past", "v:3sg") and not t.has("noun", "C:part", "C:genre", "C:check_noun", "agent", "C:report_verb")
        if prev.w in ("this", "that", "these", "those", "it", "esto", "eso") and verb_only:
            return True  # "This passed the hub's checks."
        if not (prev.w in ("all", "both", "each") and pp is not None and pp.has("C:pron1", "C:pron3", "C:anaph")):
            return False
    if prev is None and t.has("v:past", "v:part") and not t.has("lang:es") and not t.has("v:3sg"):
        return False  # a participle opening a clause: "Checked by the engine", "Reviewed and approved"
    if t.has("v:3sg", "v:past", "v:es1", "v:es3", "v:espret", "v:espret1", "v:espret3"):
        if t.has("v:past") and not t.has("v:3sg") and prev is not None and prev.has("C:part", "C:genre") and not subject_seen:
            return False
        return True
    if t.has("v:base") and prev is not None and prev.has("C:pron1", "C:pron2", "C:pron3") and prev.w not in ("it", "this", "which"):
        return True
    if t.has("v:base") and prev is not None and not t.has("lang:es") and (
            prev.has("C:generic_role", "C:eval_asr", "C:eval_out") and prev.w.endswith("s") or
            (prev.w.endswith("s") and not prev.t and not prev.punct and len(prev.w) > 3) or
            (prev.has("C:part", "C:genre") and prev.w.endswith("s") and not prev.has("C:det"))):
        return True  # a plural subject in the present: "Examiners check", "the hashes match"
    if t.has("C:report_verb", "C:descr", "C:output_verb") and (t.w.endswith("s") or t.w.endswith("ed")) and prev is not None \
            and not prev.has("C:det", "C:dist", "C:partial", "C:neg", "C:prep") and not prev.num:
        if t.w.endswith("ed") and any(x.has("C:aux", "C:copula") for x in toks[i + 1:i + 8]):
            return False  # a reduced relative before the clause's own verb ("The figures quoted from X are exact.")
        return True
    return False


class NP:
    __slots__ = ("cls", "toks", "dist", "partial", "neg", "eval", "weak")

    def __init__(self, cls: str, toks: list[Tok], *, dist: bool = False, partial: bool = False, neg: bool = False,
                 ev: Optional[str] = None, weak: bool = False):
        self.cls = cls
        self.toks = toks
        self.dist = dist
        self.partial = partial
        self.neg = neg
        self.eval = ev
        # an answer theme read from its owner or deictic alone ("my sketch map", "this report", "mi carta"): the answer's own for
        # the assessment vocabulary of correctness and checking, while the everyday evaluative words of a narrative ("my room is
        # perfect", "mi familia está bien") stay the subject's (attack round 4)
        self.weak = weak


def _is_quote(t: Tok) -> bool:
    return len(t.w) >= 2 and set(t.w) == {"q"}


#: Plural genre nouns that, under a quantifier, name the subject's positions the answer weighs ("both arguments", "all three
#: interpretations"), never the answer's own items (its calculations, steps or answers stay A).
_SUBJECT_PLURAL_GENRES = frozenset("arguments interpretations readings views explanations theories approaches analyses accounts theses "
                                   "judgements judgments perspectives models methods essays argumentos interpretaciones".split())


#: Nouns that name a numbered item of the answer ("Steps 1–5", "Question 3", "Equations (1)–(4)", "los pasos 1 a 5", "Q2").
_ITEM_NOUNS = frozenset("step steps line lines question questions equation equations paragraph paragraphs table tables answer answers "
                        "part parts item items task tasks exercise exercises problem problems calculation calculations working workings "
                        "paso pasos linea lineas pregunta preguntas ecuacion ecuaciones parrafo parrafos tabla tablas apartado "
                        "apartados ejercicio ejercicios respuesta respuestas parte partes calculo calculos".split())
_ITEM_LABEL_RE = re.compile(r"^q\d{1,3}[a-z]?$")
#: Words that join the numbers of a numbered reference ("1 to 5", "2 and 3", "from 1 to 5", "1 a 5", "2 y 3").
_ITEM_JOINERS = frozenset("to and through thru from or a y al hasta o del".split())


def _numbered_items(ts: list[Tok]) -> Optional[list[Tok]]:
    """The noun phrase without its item numbers when it names numbered items of the answer ("Steps 1–5", "Every step from 1 to 5",
    "Answer 3", "Q2", "las líneas 2 a 4"), else None. A number after an item noun labels the answer's own item: the reference is
    the answer's part whatever the noun (attack round 4)."""
    for k, t in enumerate(ts):
        if _ITEM_LABEL_RE.match(t.w):
            return ts[:k] + ts[k + 1:]
        last = t.w.split()[-1] if t.idiom else t.w
        if last not in _ITEM_NOUNS:
            continue
        j = k + 1
        nums = 0
        while j < len(ts) and (ts[j].num or ts[j].w in _ITEM_JOINERS or (len(ts[j].w) == 1 and ts[j].w.isalpha() and nums)):
            if ts[j].num:
                if not re.fullmatch(r"\d{1,3}[a-z]?", ts[j].w):
                    break  # a quantity ("12,000", "4.2"), never an item number
                nums += 1
            elif ts[j].w in ("from",) and nums:
                break
            j += 1
        while j > k + 1 and ts[j - 1].w in _ITEM_JOINERS:
            j -= 1
        if j < len(ts) and (ts[j].has("C:unit", "C:assess_key") or ts[j].w in ("mark", "marks", "point", "points", "pts", "words", "%",
                                                                                 "puntos", "palabras")):
            continue  # "equation (1 mark)", "Question 3 marks": an allocation or a quantity, never an item number
        if nums and j > k + 1:
            return ts[:k + 1] + ts[j:]
    return None


#: Text types and language forms of the answer's own text: with "my"/"this" they name the answer ("my letter", "this report",
#: "mi carta"), with "the" a source of the subject ("the report", "the letter").
_TEXT_TYPES = frozenset("report reports letter letters email emails e-mail article articles blog post posts speech speeches leaflet "
                        "brochure diary entry proposal map maps sketch cross-section transect text texts translation translations "
                        "carta cartas correo articulo discurso informe folleto diario propuesta texto textos traduccion traducciones "
                        "redaccion mensaje".split())
_FORM_HEADS = frozenset("grammar spelling spellings punctuation vocabulary conjugation conjugations tense tenses accent accents agreement "
                        "gramatica ortografia puntuacion vocabulario conjugacion conjugaciones tiempos tiempo acentos acento concordancia "
                        "verbos".split())
#: Heads that name a person or an instrument, never the answer ("my teacher", "my calculator", "mi madre").
_PERSON_TAGS = ("C:kin", "C:eval_asr", "C:eval_out", "C:generic_role", "C:pron1", "C:pron2", "C:pron3", "C:tool", "C:eval_int",
                "C:eval_int_agentive", "C:assessor_extra")


def np_class(toks: list[Tok], ctx: Context, *, inner: bool = False) -> NP:
    """The scope class of a theme noun phrase (design 3.2): A the answer, N neutral, O outside, M a part with a subject-matter
    modifier or an unknown head under a quantifier, P the pipeline's own checks, Q a quantity stated as the answer's result, T the
    student's work (marking context), I implicit (empty)."""
    toks = toks[:16] if inner else toks[-16:]  # a theme noun phrase is short (design 2.9: at most 8 tokens, read with margin)
    ts = [t for t in toks if not (t.punct and t.w not in ("%",)) and not (t.w.endswith("ly") and not t.has("C:part", "C:genre", "C:anaph")
                                                                          and not t.fam() - {"OUTCOME"})
          and t.w not in _SIGNAL and t.w not in ("also", "already", "now", "just", "then", "later", "since", "yet", "still")]
    if not ts:
        return NP("I", [])
    words = [t.w for t in ts]
    dist = any(t.has("C:dist", "C:dist_idioms") or t.w in ("no", "zero", "0", "ningun", "ninguna", "ninguno", "not a single", "not one",
                                                       "none of the", "none of", "not one of") for t in ts)
    neg = any(t.has("C:neg_pron") or t.w in ("no", "not a single", "not one", "none of", "none of the", "zero", "ningun", "ninguna")
              for t in ts)
    partial = any(t.has("C:partial", "C:partial_idioms") for t in ts)
    marking = ctx.marking
    combinator = ctx.writer == "combinator"

    def mk(cls: str) -> NP:
        if marking and cls in ("N", "I") and not inner:
            cls = "T"
        return NP(cls, ts, dist=dist, partial=partial, neg=neg)

    # a numbered item of the answer ("Steps 1–5", "Every step from 1 to 5", "Answer 3", "Q2", "los pasos 1 a 5"): the answer's own
    # part, unless an outside restrictor or owner names another's ("Table 1 in Source B", "lines 2 to 4 of the poem")
    # (a number inside a bracket the phrase leaves open, "balanced equation (1 mark)", is an allocation the trigger completes)
    open_bracket = sum(1 if x.w == "(" else -1 if x.w == ")" else 0 for x in toks) > 0
    numbered = _numbered_items(ts) if not inner and not open_bracket else None
    if numbered is not None:
        outside = any(_possessive(x) or x.has("C:poss2", "C:poss3") or (x.w in ("of", "in", "from", "de", "del", "en") and m + 1 < len(numbered)
                      and not numbered[m + 1].has("C:anchor", "C:anchor_idioms", "C:demonstrative", "C:poss1"))
                      for m, x in enumerate(numbered))
        if not outside:
            return NP("T" if marking else "A", ts, dist=True, neg=neg)
    # an answer's section named by its topic ("The Treaty of Versailles section", "the Hamlet paragraph"): the answer's own part
    if len(ts) >= 2 and ts[-1].w in ("section", "sections", "paragraph", "paragraphs", "subsection", "chapter") and \
            ts[0].w in ("the", "this", "my", "our", "these") and not inner:
        return NP("A", ts, dist=dist, neg=neg)
    # explicit anchors and the writer's own
    own = any(t.has("C:poss1") for t in ts) or any(t.w in ("mine", "ours", "my own", "our own") for t in ts)
    # a free relative on the writer's own writing, "lo que he escrito", "todo lo que hemos calculado" (the Spanish first-person
    # perfect "he"/"hemos" before a participle): the writer's own work, as "what I have written" is (attack round 6)
    if not inner and any(t.w == "que" and k + 2 < len(ts) and ts[k + 1].w in ("he", "hemos") and
                         (ts[k + 2].has("v:part") or ts[k + 2].w.endswith(("ado", "ido", "ito", "to", "cho", "sto")))
                         for k, t in enumerate(ts)) and ts[0].w in ("lo", "todo", "cuanto"):
        return NP("A", ts, dist=dist, neg=neg)
    anchor = any(t.has("C:anchor", "C:anchor_idioms") for t in ts)
    if any(t.has("C:anchor_idioms") and any(g in t.w for g in ("synthesis", "combined", "merged")) for t in ts) and not combinator:
        anchor = any(t.has("C:anchor") for t in ts)
    if any(_is_quote(t) for t in ts) and not anchor:
        return NP("O", ts)
    # a second person or another's possession: outside (the student's in a marking task)
    if any(t.has("C:poss2") or t.w in ("you", "yours", "usted") for t in ts) and not own:
        return NP("T" if marking else "O", ts)
    for k, t in enumerate(ts):
        if (_possessive(t) or t.has("C:poss3")) and not t.has("C:eval_int", "C:tool") and not any(
                x.has("C:genre") and x.w in ("answer", "answers", "response") for x in ts[:k]):
            if not (anchor or own):
                return NP("O", ts)
    if anchor:
        # a bare anchor on a subject-matter noun with a restrictor of its own ("the main criticisms of utilitarianism above"): the
        # anchor places the writer's discussion, the noun is the subject's
        meta = any(t.has("C:part", "C:genre", "C:anaph", "C:neg_pron", "C:check_noun", "C:combinator_genre", "C:anchor_idioms",
                         "C:dist_idioms") or t.w in ("everything", "all", "it", "this", "that", "lot", "thing", "todo", "esto")
                   for t in ts)
        of_at = next((k for k, t in enumerate(ts) if t.w in ("of", "de")), None)
        if not meta and of_at is not None and not own and not any(t.num or t.has("C:unit") for t in ts[of_at:]) and \
                any(not t.t and not t.punct for t in ts[of_at + 1:]):
            return NP("O", ts)
        return NP("A", ts, dist=dist, neg=neg)
    if own:
        if any(t.has("C:genre", "C:part", "C:marking_own", "C:check_noun", "C:combinator_genre") or t.w in ("mine", "ours") or
               t.w in _FORM_HEADS for t in ts):
            return NP("A", ts, dist=dist, neg=neg)
        # a first-person possessive makes the theme the writer's own work whatever the noun ("my sketch map", "all my isolines",
        # "mi carta", "mis porcentajes"), unless the noun names a person or an instrument ("my teacher", "my calculator")
        own_at = next((k for k, t in enumerate(ts) if t.has("C:poss1") or t.w in ("my own", "our own")), None)
        noun = []
        for t in ts[(own_at + 1 if own_at is not None else 0):]:
            if t.has("C:prep") or t.w in ("of", "de", "del", "that", "which", "que"):
                break  # the head noun before its restrictor ("my letter to the editor")
            if not t.has("C:det", "C:dist", "C:dist_idioms") and not t.num:
                noun.append(t)
        if noun and not any(t.has(*_PERSON_TAGS) for t in noun[:3]) and not ctx.marking:
            return NP("A", ts, dist=dist, neg=neg, weak=not any(t.w in _TEXT_TYPES for t in noun[:3]))
        return NP("O", ts)
    # a text type or the language of one named with a demonstrative ("this report", "these letters", "la gramática de esta carta"):
    # the answer's own text
    if not inner and any(t.w in _TEXT_TYPES for t in ts) and any(t.w in ("this", "these", "esta", "este", "estas", "estos") for t in ts) and \
            not any(_possessive(t) or t.has("C:poss2", "C:poss3") for t in ts):
        # (the language of the writer's own text, "la gramática de esta carta", is its correctness: never a narrative's)
        return NP("A", ts, dist=dist, neg=neg, weak=not any(t.w in _FORM_HEADS for t in ts))
    # the core NP (before a preposition, except "of" after a quantifier or partitive) and its restrictor
    core: list[Tok] = []
    rest: list[Tok] = []
    for k, t in enumerate(ts):
        if rest:
            rest.append(t)
            continue
        if (t.has("C:prep") and t.w not in ("of", "de") or (t.idiom and t.fam() == {"PROVENANCE"})) and core:
            rest.append(t)  # (a provenance phrase restricts like a preposition: "every figure taken from the History specialist")
            continue
        if t.w in ("of", "de", "del") and core:
            head_so_far = [x for x in core if (not x.has("C:dist", "C:dist_idioms", "C:det", "C:partial", "C:neg_pron", "C:partial_idioms")
                           or (x.idiom and word_tags(x.w.split()[-1]) & {"C:part", "C:genre"}))
                           and not x.num and x.w not in ("one", "each one", "every one")]
            if head_so_far and not any(x.has("C:partial") for x in head_so_far) and head_so_far[-1].w not in ("sample", "part", "rest",
                                                                                                                 "half", "majority"):
                rest.append(t)
                continue
            continue
        core.append(t)
    rel_first = False
    if rest:
        r = [x for x in rest[1:] if not x.punct]
        sub = (np_class(r, ctx, inner=True) if not inner else NP("A" if any(x.has("C:anchor", "C:anchor_idioms", "C:poss1") for x in r)
                                                                   else "O", r)) if r else NP("I", [])
        if sub.cls == "A":
            return NP("A", ts, dist=dist, neg=neg)
        internal = bool(r) and (rest[0].w in ("from",) or rest[0].fam() == {"PROVENANCE"} or any(
            x.w in ("quoted", "taken", "copied", "reproduced", "drawn") for x in core)) and \
            any("specialist" in x.w or x.has("C:eval_int_agentive") for x in r[:6]) and not any(
            x.has("C:poss3") or (_possessive(x) and "specialist" not in x.w) for x in r)
        if internal and core and any(x.has("C:part") for x in core):
            # "Every figure taken from the History specialist", "the quotations from the History report": a peer's items relayed
            # in this answer are the answer's items (a peer is no outside source)
            return NP("A", ts, dist=dist, neg=neg) if dist else mk("N")
        if rest[0].w in ("of", "in", "from", "de", "del", "en", "on", "about", "for", "within", "inside", "throughout", "across",
                         "between", "among") and r:
            if not (len(r) == 1 and r[0].w in ("it", "this", "them", "these", "lo", "esto")):
                restrictor_out = True
            else:
                restrictor_out = False
        else:
            restrictor_out = False
    else:
        restrictor_out = False
    # a relative clause with the writer as subject ("every value I quote", "los valores que doy")
    for k, t in enumerate(ts[:-1]):
        if t.has("C:part", "C:genre") and (ts[k + 1].has("C:pron1") or (ts[k + 1].w in ("that", "which", "que") and k + 2 < len(ts)
                                                                        and (ts[k + 2].has("C:pron1") or ts[k + 2].has("v:es1") or
                                                                             ts[k + 2].w in _ES_FIRST_AUX)) or
                                           ts[k + 1].w in ("que he", "que hemos", "que yo", "que nosotros", "that i", "which i",
                                                           "that we", "which we")):
            rel_first = True
    if rel_first:
        return NP("A", ts, dist=dist, neg=neg)
    if any(t.w in _SUBJECT_PLURAL_GENRES for t in core) and dist and not any(t.has("C:demonstrative") for t in core):
        return NP("O", ts)
    heads = [t for t in core if (not t.has("C:det", "C:dist", "C:dist_idioms", "C:neg", "C:partial", "C:partial_idioms", "C:neg_idioms")
             or t.has("C:part", "C:genre")) and not (len(t.w) <= 3 and any(c.isdigit() for c in t.w) and any(c.isalpha() for c in t.w)
                                                      and not t.t)]
    head = heads[-1] if heads else (core[-1] if core else ts[-1])
    # "every step", "every line", "every part" (one merged token): a distributive item of the answer
    head_part = not heads and head.idiom and bool(word_tags(head.w.split()[-1]) & {"C:part", "C:genre"})
    mods = [t for t in heads[:-1]] if heads else []
    det = [t for t in core if t.has("C:det") and not t.has("C:dist")]
    # a formula or relation is outside the answer's scope words, and so is a stated computation ("the subtraction 45.6 − 55.1"): a
    # specific worked value is material for the engine (rule X1), never the answer's assessment of itself
    if any(t.w in _REL or t.w == "=" for t in toks):  # (the relation sign is punctuation, read in the unfiltered phrase)
        return NP("O", ts)
    if sum(1 for t in toks if t.num) >= 2 and any(t.w in ("−", "-", "+", "×", "x", "÷", "/", "*", "–") for t in toks):
        return NP("O", ts)
    # a quantity with a unit stated as a result ("15 km/h stands")
    if head.has("C:unit") and any(t.num for t in core) and len(core) <= 3:
        return NP("Q", ts)
    if all(t.num or t.has("C:unit") for t in core) and any(t.num for t in core):
        return NP("Q", ts)
    # the pipeline's own checks and status nouns, and the answer's own assessment ("correctness", "accuracy")
    if head.w in _ASSESSMENT_NOUNS and not restrictor_out and not mods and not inner:
        return NP("P", ts, dist=dist, neg=neg)
    if head.has("C:check_noun") and not head.has("C:genre") or head.w in ("transmission", "receipt", "formal_checks", "ci", "formal checks"):
        # the pipeline's checks, also when a modifier names the pipeline ("the logic checks", "the formal checks", "the engine's
        # checks"); a subject-matter modifier makes them the subject's ("the safety checks", "the customs checks")
        if not restrictor_out and all(m.w in _PIPELINE_WORDS or m.has("C:tool", "C:eval_int") for m in mods):
            return NP("P", ts, dist=dist, neg=neg)
    if head.has("C:combinator_genre") or any(t.has("C:combinator_genre") for t in core):
        # the synthesis of the combinator's own text, never a synthesis of the subject matter ("the synthesis of ammonia", "protein
        # synthesis": a restrictor or a subject-matter modifier makes it the subject's)
        subject_synthesis = restrictor_out or any(not m.has("C:combinator_genre", "C:genre", "C:part", "C:anchor", "C:demonstrative")
                                                  for m in mods)
        if combinator and not subject_synthesis:
            return NP("A", ts, dist=dist, neg=neg)
        return NP("O", ts)
    if head.has("C:genre") or (head.w in ("one",) and any(t.has("C:demonstrative") for t in core)):
        if restrictor_out:
            return NP("O", ts)
        demo = any(t.has("C:demonstrative") or t.w in ("whole", "entire", "full") for t in core)
        if demo:
            return mk("A") if not marking else NP("A", ts, dist=dist, neg=neg) if head.has("C:marking_own") else mk("A")
        if head.has("C:genre_strong") and not any(t.w in ("a", "an", "un", "una") for t in det):
            if mods and any(m.name and not m.has("C:genre", "C:part") for m in mods) and head.w not in (
                    "section", "sections", "paragraph", "paragraphs", "part", "chapter", "subsection", "answer", "response"):
                return NP("O", ts)
            if marking:
                return NP("T", ts)
            return NP("A", ts, dist=dist, neg=neg)
        if dist:
            # "both arguments", "all three interpretations": the subject's arguments weighed by the answer, not the answer itself
            if head.w in _SUBJECT_PLURAL_GENRES:
                return NP("O", ts)
            return mk("A")
        return mk("N")
    if marking and head.has("C:marking_own") and any(t.has("C:demonstrative") for t in core):
        return NP("A", ts)
    if head.has("C:part") or head_part or (head.has("C:neg_pron") and len(core) == 1) or head.w in ("each one", "every one", "one"):
        if restrictor_out:
            return NP("O", ts)
        if any((_possessive(m) and m.has("C:eval_int", "C:eval_int_agentive")) or "specialist" in m.w for m in mods) and not \
                any(m.has("C:poss3") for m in mods):
            # a peer agent's items relayed here ("The History specialist's words are quoted above"): the answer's items
            return mk("A") if dist else mk("N")
        subject_mod = [m for m in mods if not m.has("C:part", "C:genre", "C:anchor") and (m.name or m.num or not m.t or
                                                                                         m.has("C:eval_out", "C:method_noun"))]
        if subject_mod and not dist and any(t.has("C:demonstrative") and t.w in ("these", "this", "those", "estos", "estas", "este", "esta",
                                                                                  "esos", "esas") for t in core) and not inner:
            # "These climate figures", "estos datos de lluvia": the demonstrative points at the answer's own items, whatever modifier
            # names their topic (attack round 3); "the census figures" (a definite article) stays the census's
            return mk("N")
        if subject_mod and not dist:
            return NP("O", ts) if any(t.has("C:definite") for t in det) else NP("M", ts, dist=dist)
        if subject_mod:
            return NP("M", ts, dist=dist, neg=neg)
        if dist and not partial:
            return mk("A") if not marking else NP("T", ts, dist=dist, neg=neg)
        return mk("N")
    if head.has("C:anaph", "C:neg_pron") or head.w in ("everything", "all", "todo", "nothing", "none", "anything", "it", "this", "that",
                                                       "these", "those", "them", "they", "lo", "esto", "eso", "nada", "algo"):
        if restrictor_out:
            return NP("O", ts)
        return mk("N")
    if head.has("C:eval_int") and not mods:
        return NP("P", ts)
    if dist and not det and not restrictor_out:
        return NP("M", ts, dist=dist)
    if not det and not head.name and not restrictor_out and head.t == frozenset() and len(core) <= 3:
        return NP("M", ts)
    if not inner and not restrictor_out and not head.name and not head.cap and head.t <= frozenset({"noun"}) and \
            core and core[0].w in ("these", "estos", "estas") and len(core) <= 4 and not any(m.name or m.num for m in mods):
        # "These population densities", "estos porcentajes": a plural demonstrative points at the answer's own items whatever the
        # noun (attack round 4), as with a part noun ("these figures"): a neutral theme
        return mk("N")
    return NP("O", ts)


#: Spanish auxiliaries whose dropped subject can be the writer (first person; "haya", "habia", "hubiera" also third person).
_ES_FIRST_AUX = frozenset("he hemos haya hayamos habia habiamos hube hubimos hubiera hubieramos".split())


def eval_class(toks: list[Tok], ctx: Context, *, fragment: bool = False) -> Optional[str]:
    """The class of an evaluator noun phrase (design 3.5): INT internal, ASR an assessor, OUT outside, GEN a bare plural assessor
    (generic practice), NEG a negated generic evaluator ("nobody", "no examiner"), None when there is none."""
    ts = [t for t in toks if not t.punct]
    if not ts:
        return None
    ws = [t.w for t in ts]
    if any(t.has("C:pron1") for t in ts) or "me" in ws:
        return "INT"
    # the Spanish first-person perfect inside a relative ("lo que he escrito", "lo que hemos calculado"): the writer, never "he"
    if any(w == "que" and k + 2 < len(ws) and ws[k + 1] in ("he", "hemos") and
           (ts[k + 2].has("v:part") or ws[k + 2].endswith(("ado", "ido", "ito", "to", "cho", "sto"))) for k, w in enumerate(ws)):
        return "INT"
    # a dropped Spanish subject read from its auxiliary ("que no haya comprobado", "que no hemos revisado"): the writer, the
    # one first person a subject-less answer clause has
    if all(w in _ES_FIRST_AUX or w in ("no", "nunca", "ya", "aun", "todavia") for w in ws) and \
            any(w in _ES_FIRST_AUX and (w != "he" or ws[0] in ("no", "nunca", "ya")) for w in ws):
        return "INT"
    if any(t.has("C:poss1") for t in ts):
        # the writer's relatives, friends and sources are other people and documents ("my mother", "my sources"); the writer's
        # notes, tools, team and checks are the writer's own process
        if any(t.has("C:kin") or (t.has("C:src_noun", "C:eval_out") and not t.has("C:eval_int", "C:tool", "C:eval_asr"))
               for t in ts) and not any(t.has("C:eval_int", "C:tool", "C:eval_asr", "C:eval_int_agentive", "C:check_noun") or t.fam()
                                        for t in ts):
            return "OUT"
        return "INT"
    if ts[0].w in ("nobody", "no one", "noone", "nadie") or (ts[0].w in ("no", "ningun", "ninguna", "not a single", "not one") and
                                                            any(t.has("C:eval_asr", "C:generic_role", "C:eval_int") or t.w in ("reader", "one")
                                                                for t in ts[1:])):
        return "NEG"
    if ts[-1].w in _STRONG_TOOLS and not any(t.has("C:idiom_x20") for t in ts):
        return "INT"  # "the school's calculator", "his GDC": a calculator is never another party's check
    if len(ts) >= 2 and ts[0].has("C:tool") and all(x.cap or x.num or "-" in x.w for x in ts[1:] if not x.has("C:det")):
        return "INT"  # a tool's product name ("Wolfram Alpha", "GeoGebra Classic 6")
    if any(_possessive(t) and not t.has("C:eval_int", "C:eval_int_agentive") and "specialist" not in t.w for t in ts) or any(t.has("C:poss3") for t in ts):
        return "OUT"
    if any(t.w in _INSTITUTIONS or (t.has("C:eval_out") and t.w not in ("he", "she", "they", "text", "source", "sources")) for t in ts) and \
            not any(t.has("C:eval_int", "C:tool") and not t.has("C:eval_out") for t in ts):
        return "OUT"
    # coordinated evaluators ("the History specialist and the combinator"): internal when any conjunct is
    if any(t.w in ("and", "y", "&") for t in ts[1:-1]):
        parts, cur = [], []
        for t in ts:
            if t.w in ("and", "y", "&"):
                parts.append(cur)
                cur = []
            else:
                cur.append(t)
        parts.append(cur)
        classes = [eval_class(p_, ctx, fragment=fragment) for p_ in parts if p_]
        for c in ("INT", "ASR"):
            if c in classes:
                return c
    heads = [t for t in ts if not t.has("C:det", "C:dist", "C:prep", "C:dist_idioms", "C:partial") and not t.num]
    if not heads:
        return None
    head = heads[-1]
    mods = heads[:-1]
    if head.w in ("pass", "passes", "read-through", "read-throughs", "sweep", "look", "reading") and any(
            t.w in ("second", "final", "last", "another", "further", "fresh", "third", "a second", "one more") for t in ts):
        return "INT"  # "A second pass found nothing to change.": the writer's own further check
    # a pipeline role before an agent noun keeps it the pipeline's ("the overseer agents", "the marking agent", "the review agent")
    if head.has("C:eval_int_agentive") and mods and all(m.has("C:eval_int", "C:tool") or m.w in (
            "marking", "review", "reviewing", "checking", "grading", "verification", "audit", "auditing", "scoring", "qa") for m in mods):
        return "INT"
    if head.has("C:part", "C:genre", "C:anaph", "C:neg_pron") and not head.has("C:eval_int", "C:eval_asr", "C:tool", "C:eval_out"):
        return None
    if any(t.has("C:auto") for t in ts) and head.has("C:eval_asr", "C:eval_int", "C:agent") or head.w in ("marker", "grader"):
        if any(t.has("C:auto") for t in ts):
            return "INT"
    if head.w in _STRONG_TOOLS and not any(t.has("C:idiom_x20") for t in ts):
        return "INT"  # a prover, a solver, a checker or a calculator is the writer's tool whatever names it ("the Z3 theorem prover")
    if head.has("C:tool") or (head.has("C:eval_int") and not head.has("C:eval_int_agentive")):
        bad_mod = [m for m in mods if m.t and not m.has("C:eval_int", "C:tool", "C:check_noun", "C:auto", "C:agent_quant") and
                   not m.has("F:CHECK", "F:STATUS") and m.w not in ("formal", "verification", "checking", "review", "specialist", "model", "proof",
                                                                      "theorem", "logic", "epinoic",
                                                                      "logic", "translation", "scoring", "marking", "qa", "graphing",
                                                                      "scientific", "own", "smt", "z3")]
        bad_mod += [m for m in mods if not m.t and not m.has("C:eval_int") and m.w not in ("gdc", "z3", "smt")]
        if bad_mod:
            return "OUT"
        if any(t.has("C:idiom_x20") for t in ts):
            return "OUT"
        return "INT"
    if head.has("C:eval_int_agentive"):
        if any(t.has("C:agent_quant") or t.w in ("another", "other", "language", "second", "peer", "separate", "independent", "previous",
                                                 "earlier", "prior", "first", "last", "marking", "checking", "reviewing", "grading",
                                                 "overseer", "overseeing")
               for t in ts) or head.w in ("llm", "ai", "chatbot", "assistant", "agente", "panel", "specialist", "specialists"):
            if any(m.name and not m.has("C:eval_int") and m.w not in ("history", "english", "economics", "physics", "biology",
                                                                     "chemistry", "geography", "psychology", "mathematics",
                                                                     "spanish") for m in mods):
                return "OUT"
            return "INT"
        if head.w in ("model", "models") and any(t.num or t.w in ("two", "three", "four", "several", "multiple", "other", "another",
                                                                   "both", "all") for t in ts):
            return "INT"  # "three models", "several models": language models consulted, agents of the writer's process
        if head.w in ("agent", "agents", "model", "models") and mods:
            return "OUT"
        return "INT" if head.w in ("agent", "agents") else "OUT"
    if head.has("C:eval_asr") or any(t.has("C:assessor_extra") for t in ts):
        if head.w.endswith("s") and not any(t.has("C:det") for t in ts) and head.w not in ("colleagues",):
            return "GEN"
        return "ASR"
    if head.has("C:generic_role") and not any(t.has("C:det") for t in ts):
        return "GEN"
    if head.has("F:CHECK") and head.idiom:
        return "OUT"
    if fragment and not head.has("C:eval_out", "C:part", "C:genre", "C:anaph"):
        return "INT"
    return "OUT"


#: Tool nouns that are never a subject-matter instrument (design 3.5, X4): a name, a version or a field before them does not make
#: them another party's ("the Z3 theorem prover", "a Casio fx-991 calculator", "the model checker").
_STRONG_TOOLS = frozenset("prover provers solver solvers calculator calculators gdc gdcs cas z3 smt calculadora".split())


# ================================================================================================================== clauses
@dataclass
class Clause:
    toks: list
    role: str = "clause"         # clause | key | value | fragment-after
    key: Optional[list] = None    # for a value: the key's tokens
    key_class: Optional[str] = None
    question: bool = False
    in_bracket: bool = False
    computation: bool = False
    subject_hint: Optional[NP] = None
    imperative_host: bool = False


def _fraction(w: str) -> bool:
    """A fraction or product written as one token ("1/3", "2×4"): digits on both sides of an operator."""
    for op in "/×÷·*^":
        a, sep, b = w.partition(op)
        if sep and a[-1:].isdigit() and b[:1].isdigit():
            return True
    return False


def _computation(toks: list[Tok]) -> bool:
    """Whether a token run shows a worked computation: a relation sign with an arithmetic operator (or a bracketed product) and
    numbers on both sides, or "number = number" after a substitution."""
    rel = [k for k, t in enumerate(toks) if t.w in ("=", "≈")]
    if not rel:
        return False
    for k in rel:
        left = toks[max(0, k - 8):k]
        right = toks[k + 1:k + 8]
        lnum = any(t.num or _fraction(t.w) for t in left)
        rnum = any(t.num or _fraction(t.w) for t in right)
        # (a fraction or product written as one number token, "1/3", is an operation too)
        lop = any(t.w in _OPS or _fraction(t.w) for t in left) or \
            any(left[m].num and left[m + 1].w == "(" for m in range(len(left) - 1))
        rop = any(t.w in _OPS or _fraction(t.w) for t in right)
        if lnum and rnum and (lop or rop):
            return True
    return False


def _split_parts(toks: list[Tok]) -> list[list[Tok]]:
    """Clauses of a sentence split at a semicolon and a spaced dash (rule S3)."""
    out: list[list[Tok]] = []
    cur: list[Tok] = []
    for k, t in enumerate(toks):
        minus = 0 < k < len(toks) - 1 and (toks[k - 1].num or toks[k - 1].w in (")", "]")) and (toks[k + 1].num or toks[k + 1].w in ("(", "["))
        # inside an absolute-value bar ("|experimental − accepted|") a dash is a minus sign too
        if not minus and t.w == "-" and 0 < k < len(toks) - 2:
            bars_before = sum(1 for x in toks[max(0, k - 4):k] if x.w == "|")
            minus = bars_before % 2 == 1 and any(x.w == "|" for x in toks[k + 1:k + 4])
        if not minus and (t.w in _PUNCT_CLAUSE or t.w in _DASHES or (t.w == "-" and k > 0 and toks[k - 1].b < t.a and k + 1 < len(toks)
                                                                     and t.b < toks[k + 1].a)):
            # (a dash between two numbers is a minus sign, "45.6 − 55.1", never a clause break)
            if cur:
                out.append(cur)
            cur = []
            continue
        cur.append(t)
    if cur:
        out.append(cur)
    return out


def _label(toks: list[Tok]) -> Optional[int]:
    """The index of a label colon ("K: V", K at most six tokens), or None. A colon between numbers is a ratio."""
    for k, t in enumerate(toks[:9]):
        if t.w == ":":
            words = [x for x in toks[:k] if not x.punct or x.w in ("(", ")")]
            n_words = sum(len(x.w.split()) for x in words if not x.punct)
            if 0 < n_words <= 6:
                if k > 0 and toks[k - 1].num and k + 1 < len(toks) and toks[k + 1].num:
                    return None
                return k
            return None
    return None


def _dangling_aux(before: list[Tok]) -> bool:
    """Whether ``before`` ends on an auxiliary or a copula that still waits for its participle, with only adjuncts after it
    ("Inflation was, by 1924, checked.", "The census figures were, in 1925, verified."): the participle after the comma completes
    that verb group, never a trailing fragment of its own."""
    k = len(before) - 1
    while k >= 0 and (before[k].punct or before[k].num or before[k].has("C:prep", "C:month", "C:det") or before[k].w.endswith("ly")
                      or before[k].w in ("then", "later", "eventually", "finally", "soon", "already", "once")):
        k -= 1
    return k >= 0 and before[k].has("C:aux", "C:copula") and k < len(before) - 1 and any(x.w == "," for x in before[k + 1:])


def _comma_split(toks: list[Tok]) -> list[list[Tok]]:
    """Split at ", " before a coordinator or subordinator, before a new subject with its own verb, or before a verbless fragment
    that holds a family word (rule S3)."""
    commas = [k for k, t in enumerate(toks) if t.w == ","]
    # ("and" or "but" with no comma before a pronoun subject and its own verb opens a clause too: "I re-read it in order to check it
    # and it is correct." is two clauses, the second an outcome of its own; check round 9 of c3c)
    bare = [k for k in range(1, len(toks) - 2) if toks[k].w in ("and", "but") and toks[k - 1].w != "," and
            toks[k + 1].w in ("it", "they", "everything", "all", "this", "these", "that", "i", "we") and
            toks[k + 2].has("C:copula", "C:aux")] if toks and not toks[0].has("v:base", "C:imperative_verbs") else []
    if bare:
        commas = sorted(set(commas) | set(bare))
    if not commas:
        return [toks]
    out: list[list[Tok]] = []
    start = 0
    fin = [_finite(toks, m) for m in range(len(toks))]  # each token's verb reading, once (it was read again for every comma)
    for idx, k in enumerate(commas):
        nxt = commas[idx + 1] if idx + 1 < len(commas) else len(toks)
        seg = toks[k + 1:nxt]
        if not seg:
            continue
        first = seg[0]
        has_fam = any(t.fam() - {"PROVENANCE"} or t.w.startswith("zz") or _score_at(seg, m) for m, t in enumerate(seg))
        seg_verb = any(_finite(seg, m) for m in range(min(len(seg), 48)))  # (read in the segment: its first word opens a clause)
        # (only the last 24 tokens before the comma are read, never a copy of the whole run since the last split: a long run of
        # commas with no split was copied once per comma, quadratic in the input)
        before_len = k - start
        before = toks[max(start, k - 24):k]
        before_verb = any(fin[max(start, k - 24):k])
        split = False
        if k in bare:
            split = True
        elif first.w in ("which", "who", "whose") and idx + 1 < len(commas) and commas[idx + 1] + 1 < len(toks) and \
                fin[commas[idx + 1] + 1] and not toks[commas[idx + 1] + 1].has("C:aux", "C:copula", "C:det", "C:pron1", "C:pron3") and \
                not toks[start].has("C:subordinator", "C:coordinator"):
            split = False  # a non-restrictive relative between a subject and its verb ("Kenya's pyramid, which has a wide base, matches
            # stage 2 ...", attack round 7): one clause, the verb after the relative takes the subject before it
        elif first.has("C:coordinator", "C:subordinator") or first.w in ("so", "and", "but", "y", "pero", "which", "while"):
            split = True
        elif (first.has("C:discourse_key") or first.w in ("nb", "n.b", "ps", "p.s", "note")) and len(seg) > 1 and seg[1].w == ":":
            split = True  # an inline note after content (", NB: nothing in this answer needs fixing"): a clause of its own
        elif has_fam and not seg_verb and not _dangling_aux(before):
            split = True
        elif seg_verb and before_verb and (first.has("C:det", "C:dist", "C:pron1", "C:pron3", "C:anaph", "C:neg_pron") or first.num or
                                           first.has("C:part", "C:genre")):
            split = True
        elif not before_verb and before_len and toks[start].has("C:subordinator"):
            split = True
        elif not before_verb and before_len and seg_verb and toks[start].w in ("before", "after", "when", "while", "once", "upon",
                                                                            "since", "antes", "despues", "tras", "al"):
            split = True  # a leading verbless time phrase ("Before posting, I ran ...", attack round 5): the main clause after it
        elif before_len and before_len <= 6 and not before_verb and any(t.fam() for t in before) and not (
                before_len == 1 and toks[start].w in ("ok", "okay", "o.k.", "alright", "right")):
            split = True  # a leading fragment: "Hand on heart, ...", "Rest assured, ..."
        elif before_len > 1 and toks[start].w in ("to", "para") and toks[start + 1].has("v:base"):
            split = True  # a leading purpose clause: "To check the result, multiply ..."
        if split:
            if toks[start:k]:
                out.append(toks[start:k])
            start = k + 1
    if toks[start:]:
        out.append(toks[start:])
    return out


# ================================================================================================================== the reading of a clause
@dataclass
class _Found:
    rule: str
    family: str
    form: str
    a: int
    b: int


def _lead_strip(toks: list[Tok]) -> list[Tok]:
    """Drop leading discourse words ("NB", "Hence", "So", "Also", "And") that are no part of the clause's grammar."""
    k = 0
    while k < len(toks) and toks[k].punct and toks[k].w in ("(", "[", "*", "-", "•", "\"", "\u201c", "\u00ab", "'", "<", ">", "|", "#"):
        k += 1
    while k < len(toks) and (toks[k].w in ("nb", "n.b", "n.b.", "ps", "p.s", "note", "hence", "so", "thus", "therefore", "also", "and",
                                         "but", "then", "finally", "overall", "y", "pero", "asi", "luego", "now", "yes", "well",
                                         "in short", "in summary", "in sum", "to sum up", "in conclusion", "ok", "okay", "plus",
                                         "moreover", "furthermore", "besides", "indeed", "clearly", "importantly", "fyi")
                             and not (toks[k].w in ("ok", "okay") and len(toks) <= 2)):
        if toks[k].w in ("ok", "okay") and k + 1 < len(toks) and toks[k + 1].w in (",",):
            pass
        k += 1
        while k < len(toks) and toks[k].w in (",",):
            k += 1
    # a hedged lead that asserts what follows ("Probably safe to say this got the all-clear from review.", "It is fair to say that
    # ..."): the clause after it is asserted all the same (a hedged positive verdict is a claim, not an uncertainty; check round 10
    # of c3d)
    j = k
    while j < len(toks) and j - k < 3 and toks[j].w in ("probably", "it's", "it", "is", "i'd", "i", "think", "would", "say", "'s"):
        j += 1
    if j + 2 < len(toks) and toks[j].w in ("safe", "fair") and toks[j + 1].w == "to" and toks[j + 2].w == "say":
        j += 3
        while j < len(toks) and toks[j].w in ("that", ","):
            j += 1
        if j < len(toks):
            k = j
    if 0 < k < len(toks):
        toks[k].init = True
    return toks[k:]


def _prev_verb(toks: list[Tok], i: int) -> int:
    for k in range(i - 1, -1, -1):
        t = toks[k]
        if t.has("C:aux", "C:copula") or _finite(toks, k):
            return k
        if t.w in (",", ";", ":") or t.w in _COMPLEMENTIZER:
            return -1
    return -1


def _verb_group(toks: list[Tok], i: int) -> int:
    """The first index of the verb group governing token ``i`` (the nearest aux, copula or finite verb to its left, with its aux
    chain and adverbs), or -1."""
    v = -1
    k = i if (i < len(toks) and _finite(toks, i) and not toks[i].has("C:aux", "C:copula")) else i - 1
    if k == i and toks[i].has("v:part") and _dangling_aux(toks[:i]):
        k = i - 1  # the participle of an auxiliary before the adjuncts ("Inflation was, by 1924, checked.")
    while k >= 0:
        t = toks[k]
        if t.w in (";", ":") or (t.w in _COMPLEMENTIZER and k < i - 1) or (t.w in _SUBORD_BOUND and k < i):
            return -1
        if t.has("C:aux", "C:copula") or _finite(toks, k):
            v = k
            while v - 1 >= 0 and (toks[v - 1].has("C:aux", "C:copula") or toks[v - 1].w in ("not", "n't", "never", "also", "already",
                                                                                         "always", "just", "now", "definitely",
                                                                                         "certainly", "fully", "since", "been") or (
                    # a manner adverb inside the auxiliary chain ("has been independently audited", attack round 5)
                    toks[v - 1].w.endswith("ly") and len(toks[v - 1].w) > 4 and toks[v - 1].w.isalpha() and v - 2 >= 0 and
                    toks[v - 2].has("C:aux", "C:copula"))):
                v -= 1
            return v
        k -= 1
    return -1


def _subject_for(toks: list[Tok], i: int, depth: int = 0) -> tuple[list[Tok], int]:
    """The subject region of the verb group that governs token ``i`` and that group's first index (-1 for a verbless clause). A
    coordinated predicate with no subject of its own ("... and are confirmed", "... and found sound") takes the subject of the
    verb group before it."""
    if i == 0 and toks and toks[0].has("v:3sg", "v:base") and not toks[0].has("v:part"):
        return [], -1
    v = _verb_group(toks, i)
    if v < 0:
        # a verbless clause: NP + participle or adjective ("All values verified", "Diagram and calculations verified")
        a = i
        while a - 1 >= 0 and i - a < 12 and toks[a - 1].w not in (",", ";", ":") and toks[a - 1].w not in _COMPLEMENTIZER:
            a -= 1
        return toks[a:i], -1
    def demonstrative_after_prep(k: int) -> bool:
        # Spanish "de esta carta", "en este texto": the accent-folded demonstrative after a preposition is a determiner, never
        # the copula "está" (attack round 4)
        return toks[k].has("C:demonstrative") and k >= 1 and toks[k - 1].has("C:prep") and toks[k - 1].w in (
            "de", "en", "con", "por", "para", "a", "sobre", "del")

    a = v
    while a - 1 >= 0 and v - a < 12:
        t = toks[a - 1]
        if t.w in ("he", "hemos", "ha", "han", "has") and a - 2 >= 0 and toks[a - 2].w == "que" and a - 3 >= 0 and \
                toks[a - 3].w in ("lo", "todo", "cuanto") and a < v and (
                toks[a].has("v:part") or toks[a].w.endswith(("ado", "ido", "ito", "to", "cho", "sto"))):
            a -= 2  # a Spanish free relative inside the subject ("lo que he escrito es correcto"): read on to its head
            continue
        if t.w in ("and", "y", "e", "or", "o", "&"):
            if a == v:
                break  # "... and are confirmed": a coordinated predicate (its subject is the one before)
            a -= 1
            continue
        if t.w in (",", ";", ":") or t.w in _COMPLEMENTIZER or t.has("C:coordinator") or t.w in _SUBORD_BOUND or \
                (t.fam() & {"CONFIDENCE"} and t.has("adj")) or (t.has("C:aux", "C:copula") and not demonstrative_after_prep(a - 1)) or \
                (_finite(toks, a - 1) and not demonstrative_after_prep(a - 1)):
            break
        a -= 1
        if t.cap and not t.upper and a > 0 and t.has("C:det", "C:dist", "C:dist_idioms", "C:demonstrative") and \
                not toks[a - 1].punct and not toks[a - 1].cap:
            break  # a capitalised determiner inside a run-on line opens a new sentence ("... context of th All values were ...")
    subj = toks[a:v]
    if not subj and a - 1 >= 2 and toks[a - 1].w == "," and depth < 4:
        # a non-restrictive relative between the subject and its verb ("the narrator, who did not know Latin, checked ...", "a second
        # researcher, who was blind to the hypothesis, checked ...": attack round 5): the subject stands before the relative
        r = next((m for m in range(a - 2, max(0, a - 16), -1) if toks[m].w in ("who", "which", "que", "quien", "quienes", "whose", "with",
                                                                                  "including", "like", "especially", "con", "incluido",
                                                                                  "incluida", "como") and
                  m >= 2 and toks[m - 1].w == ","), None)
        # (a parenthetical "with ..." phrase between the subject and its verb, "The city's land-use pattern, with a CBD surrounded by
        # concentric zones, matches the Burgess model.": the subject stands before it too, attack round 7)
        if r is not None:
            e = r - 1
            b0 = e
            while b0 - 1 >= 0 and e - b0 < 8 and not toks[b0 - 1].punct and not toks[b0 - 1].has("C:prep", "C:aux", "C:copula") and \
                    toks[b0 - 1].w not in _COMPLEMENTIZER and not toks[b0 - 1].has("C:coordinator", "C:subordinator") and \
                    toks[b0 - 1].w not in _SUBORD_BOUND and not _finite(toks, b0 - 1):
                b0 -= 1
            if b0 < e:
                return toks[b0:e], v
    # an existential after an implicative or a verb of making sure ("Took care to ensure there are no mistakes"): "there" opens it
    if len(subj) > 1 and any(x.w in ("there", "hay") for x in subj[1:]):
        subj = subj[max(k for k, x in enumerate(subj) if x.w in ("there", "hay")):]
    # a leading adverbial ("In this essay I ...", "In May 1930 the figures ..."): the subject starts after it
    if subj and (subj[0].has("C:prep") or (subj[0].idiom and subj[0].w.split()[0] in ("in", "of", "en", "for"))):
        for m in range(1, len(subj)):
            if subj[m].has("C:pron1", "C:pron3") or (subj[m].has("C:det", "C:dist") and m >= 2 and not subj[m - 1].has("C:prep")):
                subj = subj[m:]
                break
    # a relative clause with no subject of its own ("the government that had accepted a diktat", "the party that promised
    # order"): its subject is the antecedent noun phrase before the relative pronoun
    if len(subj) == 1 and subj[0].w in ("which", "who", "que", "quien", "quienes") and a >= 1:
        subj = []  # the relative pronoun stands for its antecedent (below)
        a += 1
    if not subj and a - 1 >= 1 and toks[a - 1].w in ("that", "which", "who", "que", "quien", "quienes", "whom"):
        b = a - 1
        end = a - 1
        if b - 1 >= 1 and toks[b - 1].w == ",":
            b -= 1  # a non-restrictive relative ("the ONS, which verified them"): the antecedent stands before the comma
            end = b
        while b - 1 >= 0 and a - 1 - b < 8 and not toks[b - 1].punct and not toks[b - 1].has("C:prep", "C:aux", "C:copula") and \
                toks[b - 1].w not in _COMPLEMENTIZER and not _finite(toks, b - 1):
            b -= 1
            if toks[b].has("C:det", "C:dist", "C:demonstrative", "C:poss1", "C:poss3"):
                break
        if b < end:
            return toks[b:end], v
    if not subj and a - 1 >= 0 and toks[a - 1].w in ("and", "y", "e", "but", "pero") and depth < 4:
        prev = _subject_for(toks, a - 1, depth + 1)[0]
        # the verb before "and" is a word the closed lexicon does not know ("The conclusions follow and have been confirmed"): a
        # noun phrase opened by a determiner, then that one word, is the shared subject and its verb (attack round 6)
        if len(prev) >= 3 and prev[0].has("C:det", "C:definite", "C:demonstrative", "C:dist", "C:poss1", "C:agent_quant"):
            # (or in mid-phrase with its own object: "Otro modelo repitió el razonamiento y llegó ...")
            cut = next((q for q in range(2, len(prev)) if prev[q].w.isalpha() and not prev[q].num and
                        not {x for x in prev[q].t if not x.startswith("lang")} and
                        {x for x in prev[q - 1].t if not x.startswith("lang")}), None)
            if cut is not None and not any(x.has("C:prep") or x.punct for x in prev[:cut]):
                prev = prev[:cut]
        if prev:
            return prev, v

    # Spanish: clitics before the verb are objects, not the subject
    while subj and subj[-1].w in _CLITICS and len(subj) <= 2 and all(x.w in _CLITICS or x.w in ("no",) for x in subj):
        subj = []
    return subj, v


def _object_after(toks: list[Tok], i: int, limit: int = 10) -> list[Tok]:
    """The object noun phrase after token ``i`` (particles skipped), up to a preposition, a clause mark or a verb."""
    j = i + 1
    while j < len(toks) and toks[j].w in ("back", "through", "over", "up", "out", "off", "on", "all", "it's"):
        if toks[j].w in ("through", "over", "on") and j + 1 < len(toks) and not toks[j + 1].has("C:det", "C:anaph", "C:dist", "C:poss1"):
            break
        j += 1
    out: list[Tok] = []
    while j < len(toks) and len(out) < limit:
        t = toks[j]
        if t.punct and t.w not in ("%", "-"):
            break
        if t.has("C:signal_idioms") or t.w in _SIGNAL:
            if out:
                break
            j += 1  # "lo he comprobado dos veces", "checked twice": a checking signal, never the object
            continue
        if t.has("C:prep") and t.w not in ("of", "de", "del") and out:
            # keep an "in this answer" / "above" restrictor
            if j + 1 < len(toks) and (toks[j + 1].has("C:anchor", "C:demonstrative", "C:poss1") or toks[j].has("C:anchor_idioms")):
                out.append(t)
                j += 1
                continue
            break
        if t.has("C:prep") and not out and t.w not in ("of",):
            break
        if t.w in _COMPLEMENTIZER or (t.has("C:coordinator") and out):
            break
        if out and (t.has("C:aux", "C:copula") or (_finite(toks, j) and not t.has("C:pron1"))):
            if not (t.has("C:pron1")):
                break
        out.append(t)
        j += 1
    return out


def _pp_after(toks: list[Tok], i: int, preps: tuple[str, ...], within: int = 6) -> Optional[list[Tok]]:
    """The noun phrase of the first preposition of ``preps`` within ``within`` tokens after ``i``."""
    for j in range(i + 1, min(len(toks), i + 1 + within)):
        t = toks[j]
        if t.w in (";",):
            return None
        if t.w in preps or (t.has("C:anchor_idioms") and t.w.split()[0] in preps):
            if t.has("C:anchor_idioms"):
                return [t]
            out = []
            k = j + 1
            while k < len(toks) and len(out) < 10:
                x = toks[k]
                if x.punct and x.w not in ("%",):
                    break
                if x.has("C:prep") and x.w not in ("of", "de", "del") and out and not (k + 1 < len(toks) and toks[k + 1].has("C:anchor",
                                                                                                                         "C:demonstrative")):
                    break
                if out and (x.has("C:aux", "C:copula") or x.w in _COMPLEMENTIZER or x.has("C:coordinator")):
                    break
                out.append(x)
                k += 1
            return out
        if t.w in ("here", "aqui") or t.has("C:anchor"):
            return [t]
    return None


def _defect_location(toks: list[Tok], i: int) -> Optional[list[Tok]]:
    """The location of a defect past the defect's own "of"/"de" complement ("faltas de ortografía EN MI TEXTO": attack round 4), or
    None when another preposition stands first ("No counterexample TO Goldbach's conjecture ... below ...": its own phrase)."""
    for j in range(i + 1, min(len(toks), i + 9)):
        w = toks[j].w
        if w in ("in", "en", "within", "anywhere", "here", "aqui"):
            return _pp_after(toks, j - 1, (w,), within=2) if w not in ("anywhere", "here", "aqui") else [toks[j]]
        if toks[j].punct or (toks[j].has("C:prep") and w not in ("of", "de", "del")) or toks[j].has("C:aux", "C:copula"):
            return None
    return None


def _np_from(toks: list[Tok], j: int, limit: int = 8) -> list[Tok]:
    """The noun phrase starting at ``j`` (up to a clause mark, a verb or ``limit`` tokens)."""
    out: list[Tok] = []
    while j < len(toks) and len(out) < limit:
        x = toks[j]
        if x.punct and x.w not in ("%", "-"):
            break
        if out and (x.has("C:aux", "C:copula") or x.w in _COMPLEMENTIZER or x.has("C:coordinator")):
            break
        out.append(x)
        j += 1
    return out


def _by_evaluator(toks: list[Tok], i: int, ctx: Context, fragment: bool) -> tuple[Optional[str], bool]:
    """(evaluator class, method) from a by-phrase or an instrument phrase after token ``i``: a method of the subject (a laboratory
    instrument, a test, a repetition, a site) is no evaluator (X4)."""
    ev = None
    method = False
    j = i + 1
    while j < len(toks):
        t = toks[j]
        if t.w in (";",) or (t.w == "," and not fragment):
            break
        if t.has("C:by") or t.has("C:instr_prep") or t.w in ("from", "past", "via", "according to", "segun"):
            np = []
            k = j + 1
            while k < len(toks) and len(np) < 8:
                x = toks[k]
                if x.punct and x.w not in ("-", "%"):
                    break
                if x.has("C:prep") and x.w not in ("of",) and np:
                    break
                if np and (x.w in ("and", "y") and k + 1 < len(toks) and (toks[k + 1].has("v:part", "v:past", "C:aux") or toks[k + 1].fam())):
                    break
                np.append(x)
                k += 1
            if np:
                if any(x.has("C:method_noun") for x in np) and not any(x.has("C:tool", "C:poss1", "C:pron1") for x in np) and \
                        not (np[-1].has("C:eval_out") or np[-1].w in _INSTITUTIONS) or \
                        (np[0].has("v:ger") and np[0].w in ("repeating", "measuring", "titrating", "replicating", "sampling",
                                                            "surveying", "observing", "testing")):
                    method = True
                elif (np[0].has("v:ger") or (np[0].w.endswith("ing") and len(np[0].w) > 5)) and not np[0].fam():
                    # "by substituting back": a manner, no evaluator; in the generic present ("The solution is confirmed by
                    # substituting it back") it states the method of the subject, no completed check (X4)
                    if any(x.w in ("is", "are") for x in toks[max(0, i - 3):i]) and not any(x.w in ("has", "have", "been", "now")
                                                                                       for x in toks[max(0, i - 3):i]):
                        method = True
                elif any("specialist" in x.w or x.has("C:eval_int_agentive") for x in np) and \
                        any("report" in x.w or x.has("C:part") for x in np):
                    return "INT", method  # checked with or against the system's own reports: the system's check (an internal comparand)
                elif t.w in ("in", "on", "against", "into", "through", "with", "con") and not any(
                        x.has("C:tool", "C:eval_int", "C:eval_asr", "C:pron1", "C:poss1", "C:assessor_extra") for x in np):
                    # a comparand or a place, no evaluator; an instrument of the subject that a test is made with or for ("tested
                    # with universal indicator", "tested for chloride ions with silver nitrate") is its method (X4)
                    if any(x.w in ("equation", "equations", "formula", "inequality", "expression", "identity") for x in np):
                        method = True  # "checked in the original equation": substitution, a method of the mathematics (X4)
                    if t.w == "in" and np and any(x.has("C:eval_out") and not x.has("C:pron3") for x in np) and ev is None:
                        ev = "OUT"  # "verified in later scholarship", "confirmed in the literature": an outside source's check
                    if toks[i].w.startswith(("test", "prueb")) and t.w in ("with", "con") and not any(
                            x.w in ("care", "attention", "rigour", "rigor", "precision", "cuidado") for x in np):
                        method = True
                elif t.w == "from" and not any(x.has("C:eval_int", "C:eval_asr", "C:tool") for x in np):
                    pass
                else:
                    c = eval_class(np, ctx, fragment=fragment)
                    if c in ("INT", "ASR"):
                        return c, method
                    if c and ev is None:
                        ev = c
            j = k
            continue
        j += 1
    return ev, method


def _neg_count(toks: list[Tok], start: int, i: int, es: bool) -> int:
    """Negation operators before token ``i`` in its clause (rule P1), Spanish negative concord counted once, affirming idioms
    skipped (they are merged tokens)."""
    k = 0
    seen_es_no = False
    skip_to = -1
    for j in range(max(start, i - 40), i):
        t = toks[j]
        if j < skip_to:
            continue  # inside the inert complement of a "without"/"sin" (attack round 7)
        if t.w in ("without", "sin"):
            from .meaning import inert_complement
            e = inert_complement(toks, j)
            if 0 < e <= i:
                skip_to = e
                continue  # "Without any help, I checked ...": the negation stays inside its own complement
        if t.has("C:affirm_idioms", "C:affirm_matrix"):
            continue
        if t.has("C:deny_matrix"):
            k += 1
            continue
        if t.w in ("0",) and j + 1 < i + 1 and j + 1 < len(toks) and (toks[j + 1].has("F:DEFECT", "C:part", "noun") or
                                                                        toks[j + 1].w in ("corrections", "slips", "errors")):
            k += 1
            continue
        if t.has("C:neg", "C:neg_idioms") or t.w in ("not a single", "not one", "no one", "none of", "none of the", "not one of",
                                                    "not a", "not any", "not even one", "not even a"):
            if es and seen_es_no and t.w in ("nada", "nadie", "ningun", "ninguna", "ninguno", "nunca", "ni", "tampoco", "jamas"):
                continue
            if es and t.w == "no":
                seen_es_no = True
            k += 1
    return k


_HASTE = frozenset(("premature", "hasty", "rash", "too early", "too soon", "prematuro", "prematura", "precipitado", "precipitada",
                    "apresurado", "apresurada", "demasiado pronto", "demasiado temprano"))


def _weak_before(toks: list[Tok], start: int, i: int, finding: bool) -> bool:
    # an assessment called premature or hasty, wherever the word stands in its clause ("Calling this answer correct would be
    # hasty", "It is too early to say this answer is correct"): an uncertain assessment, never a verdict (attack round 6)
    for j in range(i + 1, min(len(toks), i + 12)):
        if toks[j].w in (";",) or toks[j].w in _HASTE and not any(toks[q].has("C:neg") for q in range(max(start, j - 3), j)):
            if toks[j].w != ";":
                return True
            break
    for j in range(max(start, i - 40), i):
        t = toks[j]
        if t.has("C:weak_idioms"):
            return True
        if t.has("C:weak") and t.w not in ("if", "unless", "whether"):
            if t.w in ("could", "podria", "podrian", "pudo", "pudiera", "pudieran") and finding:
                continue  # "nobody could find", "nadie podría encontrar" (attack round 5): the impossibility is the claim
            if t.w in ("should", "may", "might", "could", "puede", "pueda") and j + 1 < len(toks) and toks[j + 1].w in ("not", "n't"):
                if finding:
                    continue
            if t.w in ("roughly", "approximately"):
                continue
            return True
    return False


def _mood(toks: list[Tok], question: bool) -> str:
    """The clause's mood (S3): question, protasis, imperative or declarative."""
    if question:
        return "question"
    if not toks:
        return "declarative"
    t0 = toks[0]
    if t0.has("C:subordinator") or t0.w in ("if", "unless", "whether", "si", "provided", "suppose", "supposing", "assuming"):
        return "protasis"
    k = 0
    while k < len(toks) and (toks[k].has("C:imperative_skip") or toks[k].w in ("remember to", "make sure", "be sure to", "please")):
        if toks[k].w in ("don't", "never", "do") and k + 1 < len(toks):
            k += 1
            continue
        k += 1
    if k < len(toks):
        t = toks[k]
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        headline = any(x.has("v:part", "v:past") and x.fam() and not x.has("v:base") for x in toks[k + 2:]) and not any(
            x.has("C:aux", "C:copula") for x in toks[k + 1:])
        # a check noun with its participle ("Proof checked by Lean."): a headline, not an instruction
        if nxt is not None and t.has("C:check_noun", "C:genre", "C:part") and nxt.has("v:part") and nxt.fam() and \
                (k + 2 >= len(toks) or toks[k + 2].punct or toks[k + 2].has("C:by", "C:prep")):
            headline = True
        if t.has("lang:es") and t.has("v:espret1", "v:espret3") and sum(1 for x in toks if x.w in _ES_FUNCTION or (
                x is not t and x.has("lang:es"))) >= 2:
            return "declarative"  # "Revisé dos veces cada cálculo": a Spanish preterite, never an English imperative
        if t.w.endswith("e") and len(t.w) >= 4 and original_spelling(t)[-1:] in ("é", "É"):
            return "declarative"  # "Revisé cada línea." (folded "revise"): the accent the fold dropped marks the preterite
        lone = len([x for x in toks[k:] if not x.punct]) == 1 and t.has("adj")
        # (a verb whose base and participle are spelled alike, "proofread", "read", "set", is the base before its object: "Proofread
        # your essay: ..." is an instruction, attack round 5)
        base_part = t.has("v:part") and t.has("v:base") and nxt is not None and (
            nxt.has("C:poss2", "C:pron2") or nxt.w in ("it", "them", "your", "each", "every", "all", "the", "this", "these"))
        if (t.has("v:base") or t.has("C:imperative_verbs")) and not t.has("C:pron1", "C:det") and (not t.has("v:part") or base_part) and \
                not lone and \
                not (nxt is not None and (nxt.has("C:aux", "C:copula") or _finite(toks, k + 1))) and t.w not in ("ok", "okay") \
                and not headline and not (nxt is not None and nxt.num and k + 2 < len(toks) and (
                    toks[k + 2].has("C:aux", "C:copula") or (_finite(toks, k + 2) and toks[k + 2].fam()))):
            # ("Answer 3 is correct.": a numbered item as the subject, never an instruction)
            if t.has("lang:es") and not (t.has("v:es3") or t.has("C:imperative_verbs")):
                return "declarative"
            if t.cap or k == 0 or toks[0].has("C:imperative_skip"):
                return "imperative"
    return "declarative"


#: Implicative verbs (past or perfect) whose infinitive complement is asserted, never a purpose ("took care to", "was used to").
_IMPLICATIVES = ("took care", "taken care", "take care", "took the time", "taken the time", "made sure", "made certain", "managed",
                 "bothered", "remembered", "was used", "were used", "been used", "i used", "we used", "used my", "used our",
                 "made a point", "went on", "proceeded", "me encargue de", "me tome la molestia de", "procure")


def _assertion_blocked(toks: list[Tok], i: int, start: int) -> Optional[str]:
    """Whether the trigger ``i`` is inside a non-asserted part of its clause: after a purpose infinitive of a check ("to check that
    ..."), after a deontic modal, or inside a complement of a check act that is not asserted (an instruction, a generic practice)."""
    for j in range(max(start, i - 40), i):
        t = toks[j]
        if t.w in ("to", "para", "in order to") and j + 1 < len(toks) and (toks[j + 1].has("v:base") and toks[j + 1].fam() & {"CHECK"}
                                                                          or toks[j + 1].w in ("make sure", "check", "confirm",
                                                                                               "verify", "ensure", "test")):
            # an implicative verb before the infinitive asserts it ("I took care to double-check each step", "A calculator was used
            # to confirm all of the values", "I made sure to verify"): the check was done
            prev2 = " ".join(x.w for x in toks[max(0, j - 3):j])
            if any(prev2.endswith(x) for x in _IMPLICATIVES):
                continue
            if j + 1 <= i:
                return "purpose"
        if t.has("C:deontic_idioms") or (t.has("C:deontic") and t.w in ("should", "must", "ought", "debe", "deben", "conviene")):
            # a negated need of checking ("do not need to be checked", "need not be checked", "no hace falta comprobar") denies the
            # need: the items are said to be fine, asserted, and read by the need's own reading (P1), never a deontic
            if t.w.split()[0] in ("need", "needs", "have", "has") and any(x.has("C:neg") or x.w in ("not", "n't", "no")
                                                                        for x in toks[max(start, j - 3):j + 2]):
                return "negated-need"
            return "deontic"
    return None


_ES_FUNCTION = frozenset("el la los las esta este esto estos estas todo toda todos todas cada lo hay que del en es son una un de y mis mi "
                         "nada nadie ningun ninguna ninguno muy pero porque".split())


def _spanish(toks: list[Tok]) -> bool:
    """Whether a clause is Spanish (negative concord applies): a Spanish word or two Spanish function words."""
    words = [w for t in toks for w in (t.w.split() if t.idiom else [t.w])]
    if any(t.has("lang:es") for t in toks):
        return True
    return sum(1 for w in words if w in _ES_FUNCTION) >= 2


#: A clause longer than this many tokens is read in overlapping windows (each construction the rules read spans far fewer tokens),
#: so the work per token is bounded and the reading stays linear (design 2.9).
_CLAUSE_WINDOW = 96
_CLAUSE_STEP = 64


def _clause_found(cl: Clause, ctx: Context, info: dict) -> list[_Found]:
    # the clause's head noun phrase before a relative clause ("Every figure in this answer on the treaty which imposed ... has been
    # verified."): the subject of a verb that ends the relative clause's chain, however long (read in every window below)
    rel = next((k for k, t in enumerate(cl.toks[:24]) if t.w in ("which", "that", "who", "whom", "que") and k > 0), None)
    if rel is not None and not any(_finite(cl.toks, k) for k in range(rel)) and "clause_head" not in info:
        info = dict(info)
        info["clause_head"] = cl.toks[:rel]
    if len(cl.toks) > _CLAUSE_WINDOW:
        out: list[_Found] = []
        # the clause's opening up to its first finite verb ("This answer uses"): every later window is read after it, so a predicate
        # far from its subject ("This answer uses <a long list> and has been verified by the hub.") is read with it (attack round 4:
        # a window bound was a silent pass)
        lead: list[Tok] = []
        for k in range(min(len(cl.toks), 24)):
            if _finite(cl.toks, k):
                lead = cl.toks[:k + 1]
                while k + 1 < len(cl.toks) and len(lead) < 24 and (cl.toks[k + 1].has("C:aux", "C:copula") or cl.toks[k + 1].has("v:part")):
                    k += 1
                    lead = cl.toks[:k + 1]
                break
        for a in range(0, len(cl.toks), _CLAUSE_STEP):
            part = cl.toks[a:a + _CLAUSE_WINDOW]
            if a and part:
                part[0].init = True
                if lead and a > len(lead):
                    part = lead + part
            out += _clause_found_bounded(Clause(part, role=cl.role, key=cl.key, key_class=cl.key_class, question=cl.question,
                                                in_bracket=cl.in_bracket, computation=cl.computation,
                                                subject_hint=cl.subject_hint if a == 0 else None), ctx, info)
            if a + _CLAUSE_WINDOW >= len(cl.toks):
                break
        return out
    return _clause_found_bounded(cl, ctx, info)


def _clause_found_bounded(cl: Clause, ctx: Context, info: dict) -> list[_Found]:
    toks = _lead_strip(cl.toks)
    if not toks:
        return []
    found: list[_Found] = []
    es = _spanish(toks)
    mood = _mood(toks, cl.question)
    if cl.imperative_host and mood == "declarative" and (toks[0].w.endswith("ing") or toks[0].has("v:ger")):
        mood = "imperative"  # "Redo part (d), checking that the values add up": the participle belongs to the instruction
    fragment_clause = not any(_finite(toks, k) for k in range(len(toks)))
    sentence_tool = info.get("tool_named", False)
    # X11 markscheme lines, X13 structural end of proof
    w0 = toks[0].w
    if w0 in ("award", "accept", "do not accept") or (w0 in ("m1", "a1", "r1", "b1") and len(toks) > 1 and toks[1].w == "for") or \
            (toks[0].w == "[" and len(toks) > 3 and toks[3].w == "for"):
        return []
    flat = " ".join(t.w for t in toks)
    for x in _STRUCTURAL_EOP:
        if x in flat:
            return []
    if mood == "declarative":
        k_res = _pipeline_result(toks, ctx)
        if k_res is not None:
            return [_Found("G2", "CHECK", "sentence", toks[k_res].a, toks[k_res].b)]
    skip_rest = False
    for i, t in enumerate(toks):
        if _inert(t.w, t.t, t.num):
            continue  # a word no frame below can start from (no family, frame verb or noun, number, mark or score): read past it
        if skip_rest and not (t.fam() & {"ASSURE", "APPROVE", "QUALITY", "OUTCOME"} and t.has("adj", "idiom") or _score_at(toks, i)
                              or t.idiom and t.fam() & {"ASSURE", "APPROVE", "SCORE"} or t.has("C:comply_verb")):
            continue
        if skip_rest and t.fam() & {"OUTCOME", "QUALITY"} and not (i + 1 < len(toks) and (toks[i + 1].has("C:genre") or
                                                                                       toks[i + 1].w == "one")):
            continue
        if t.has("C:assess_instrument") and i > 0 and mood == "declarative" and any(
                x.w in ("same", "identical", "as", "like") for x in toks[max(0, i - 3):i]) and fragment_clause and \
                _neg_count(toks, 0, i, es) % 2 == 0:
            # agreement with an assessment instrument in a fragment ("Same as the answer key.", "Identical to the mark scheme."): the
            # answer's agreement with what the marker holds (X7 never covers an instrument)
            found.append(_Found("G5", "AGREE", "fragment", toks[0].a, t.b))
            continue
        if t.has("C:assess_instrument") and i > 0 and any(x.has("C:copula") for x in toks[max(0, i - 3):i]) and mood == "declarative" \
                and not any(x.w in ("a", "an", "un", "una") for x in toks[max(0, i - 2):i]):
            subj, v = _subject_for(toks, i)
            th = np_class(subj, ctx) if subj else NP("I", [])
            if th.cls in ("A", "N", "P") and _neg_count(toks, 0, i, es) % 2 == 0:
                found.append(_Found("G1" if th.cls == "A" else "G3", "AGREE", "sentence", t.a, t.b))
                continue
        if t.num and i + 1 < len(toks) and toks[i + 1].w in ("words", "palabras", "word") and mood == "declarative" and \
                not any(x.has("C:generic_role", "C:eval_asr", "C:eval_out") or x.w in ("at", "after", "beyond", "over", "limit")
                        for x in toks[max(0, i - 6):i]) and \
                not _assertion_blocked(toks, i, 0) and not _weak_before(toks, 0, i, False) and \
                not any(x.w in ("must", "should", "need", "needs", "has to", "have to", "debe") for x in toks[max(0, i - 6):i]):
            subj, v = _subject_for(toks, i)
            th = np_class([x for x in subj if not x.has("C:weak")], ctx) if subj else NP("I", [])
            words_left = [x for x in toks[:i] if not x.punct and x.w not in ("about", "approximately", "roughly", "around", "c.",
                                                                              "unas", "unos", "aproximadamente", "some", "exactly")]
            if ctx.marking and th.cls != "A":
                continue  # a word count in a marking task measures the student's text
            if (not words_left and len([x for x in toks if not x.punct]) <= 5) or th.cls == "A":
                found.append(_Found("G5" if th.cls != "A" else "G1", "COMPLY", "fragment" if not words_left else "sentence", t.a,
                                    toks[i + 1].b))
                continue
        # a status noun of the pipeline after a copula ("Every claim is a theorem of the engine's encoding.")
        if t.w in ("theorem", "theorems", "tautology", "tautologies") and any(x.has("C:copula") for x in toks[max(0, i - 3):i]) and \
                any(x.w.rstrip("'s").rstrip("’s") in _PIPELINE_RESULT_NAMES or x.w in ("encoding", "encodings") for x in toks[i + 1:i + 6]) and \
                mood == "declarative" and _neg_count(toks, 0, i, es) % 2 == 0:
            subj0 = _subject_for(toks, i)[0]
            th0 = np_class(subj0, ctx) if subj0 else NP("I", [])
            if th0.cls in ("A", "N", "I", "P"):
                found.append(_Found("G1" if th0.cls == "A" else "G3", "STATUS", "sentence", t.a, t.b))
                continue
        # the writer's own word count stated as such ("The word count is 298.", "Word count = 312")
        if t.w in ("word count", "recuento de palabras") and mood == "declarative" and any(x.num for x in toks[i + 1:i + 4]) and \
                not ctx.marking and not any(x.has("C:poss2", "C:poss3", "C:generic_role", "C:eval_out") or _possessive(x) for x in toks[:i]):
            found.append(_Found("G1", "COMPLY", "sentence", t.a, t.b))
            continue
        # COMPLY by composition (design 3.3: "meets/satisfies every requirement, criterion or constraint, answers/addresses/covers
        # every part"): a compliance verb with a distributive request noun, as object ("The answer meets every constraint in the
        # request.") or as passive subject ("every item is addressed"); the theme is the answer (the subject, or the implicit one)
        if t.has("C:comply_verb") and mood == "declarative" and not _weak_before(toks, 0, i, False) and \
                _neg_count(toks, 0, i, es) % 2 == 0 and not _assertion_blocked(toks, i, 0):
            after = [x for x in toks[i + 1:i + 5] if not x.punct]
            before = [x for x in toks[max(0, i - 6):i] if not x.punct and not x.has("C:aux", "C:copula")]
            after = [x for x in toks[i + 1:i + 8] if not x.punct]
            as_object = False
            if after and after[0].has("C:dist", "C:dist_idioms"):
                # the distributive, its determiners ("todos los", "all of the") and at most two modifiers before the request noun
                # ("every acceptance criterion", "all the marking requirements": attack round 4)
                q = 1
                while q < len(after) and after[q].w in ("the", "of", "los", "las", "de", "sus", "its", "their"):
                    q += 1
                mods_n = 0
                while q < len(after) and mods_n < 2 and not after[q].has("C:request_noun") and not after[q].fam() and \
                        not after[q].num and after[q].w.isalpha():
                    q += 1
                    mods_n += 1
                as_object = q < len(after) and after[q].has("C:request_noun")
            as_subject = (t.has("v:part") or t.w.endswith("ed")) and len(before) >= 2 and before[-2].has("C:dist") and before[-1].has("C:request_noun") and \
                any(x.has("C:aux", "C:copula") for x in toks[max(0, i - 3):i])
            if not as_subject and (t.has("v:part") or t.w.endswith("ed")) and any(x.has("C:aux", "C:copula") for x in toks[max(0, i - 3):i]):
                # the request's items named as such ("Both request items are addressed above.", "All parts of the question have been
                # answered."): the subject holds a distributive request noun and names the request or an answer anchor (a bare "All
                # the constraints are satisfied." may be the subject's constraints and is read as content)
                subj0 = _subject_for(toks, i)[0]
                as_subject = any(x.has("C:dist", "C:dist_idioms") for x in subj0) and any(x.has("C:request_noun") for x in subj0) and (
                    any(x.w in ("request", "question", "task", "prompt", "brief", "pregunta", "tarea") for x in subj0) or
                    any(x.has("C:anchor", "C:anchor_idioms") for x in toks[i + 1:]))
            if as_object or as_subject:
                subj, _v = _subject_for(toks, i)
                th = np_class(subj, ctx) if (as_object and subj) else NP("A", [])
                if th.cls in ("A", "N", "I") and not (ctx.marking and th.cls != "A"):
                    found.append(_Found("G1" if th.cls in ("A", "I") else "G3", "COMPLY", "sentence", t.a, t.b))
                    continue
        if mood == "declarative":
            borne = _bearer_result(toks, i, ctx, es)
            if borne is not None:
                found.append(borne)
                continue
        fams = t.fam()
        # the combinator's text relaying an engine status of what it is built from ("Built only from FORMALLY CHECKED reports.", "All
        # inputs were formally checked."): a status label in the synthesis, whatever it is attached to (attack round 4)
        if ctx.writer == "combinator" and "STATUS" in fams and (t.upper or t.w in ("formally checked", "formally verified")) and \
                not (i > 0 and toks[i - 1].w in _LABEL_VERBS) and mood == "declarative" and _neg_count(toks, 0, i, es) % 2 == 0 and not _weak_before(toks, 0, i, False):
            found.append(_Found("G6", "STATUS", "label_inside", t.a, t.b))
            continue
        if t.w in ("follow", "follows", "followed", "keep", "keeps", "kept", "preserve", "preserves", "preserved", "reproduce",
                   "reproduces") and any(x.w in ("spelling", "wording", "punctuation", "capitalisation", "capitalization", "lineation",
                                                 "layout", "ortografia") for x in toks[i + 1:i + 5]) and mood == "declarative" and \
                _neg_count(toks, 0, i, es) % 2 == 0:
            subj0 = _subject_for(toks, i)[0]
            th0 = np_class(subj0, ctx) if subj0 else NP("A", [])
            if th0.cls in ("A", "N", "M", "I") and any(x.has("C:part", "C:genre") for x in subj0 or [t]) or th0.cls == "A":
                # "All quotations follow the 1633 spelling of the supplied text.": a blanket fidelity claim over the answer's
                # quotations (X8), read as a fidelity trigger
                found.append(_Found("G1" if th0.cls == "A" else "G3", "FIDELITY", "sentence", t.a, t.b))
                continue
        score_len = _score_at(toks, i)
        mark = t.w in ("zzmarkpos", "zzapprove", "zzscorefull", "zzrating")
        if t.has("C:idiom_x20"):
            continue
        # a comparative of lesser degree ("the total is less certain than the individual errors") grades, it never asserts
        if i > 0 and toks[i - 1].w in ("less", "least") and fams & {"CONFIDENCE", "OUTCOME", "QUALITY", "SRCEVAL"}:
            continue
        # "clear" after a copula is clarity, not clearance ("the point is clear")
        if t.w == "clear" and fams <= {"APPROVE", "QUALITY", "OUTCOME"} and i > 0 and toks[i - 1].has("C:copula") and \
                not any(x.has("C:anchor", "C:anchor_idioms", "C:genre") for x in toks[:i]):
            continue
        # a family word inside a proper name ("Larkmoor Square", "Fair Isle", "Sound of Mull") names, never assesses (a status written
        # in capitals, "VERIFIED", is no name)
        if t.name and not t.upper and ((i > 0 and (toks[i - 1].name and not toks[i - 1].init or _unknown_name(toks[i - 1]))) or
                                       (i + 1 < len(toks) and toks[i + 1].name)):
            continue
        # the checking a need or a requirement names ("need checking", "need not be checked", "needs to be verified") is the need's
        # object, read with the need (a need of checking is a defect, its negation a positive status), never a check act of its own
        if fams & {"CHECK"} and any(x.has("V:need") for x in toks[max(0, i - 4):i]) and not t.idiom:
            continue
        if not fams and not score_len and not mark:
            # need/require with a defect object: "needs no changes", "needs 0 corrections", "needs checking"
            if t.has("V:need") and i + 1 < len(toks):
                obj = toks[i + 1:i + 4]
                if any(x.has("F:DEFECT") or x.w in ("changes", "change", "changing", "fixing", "work", "attention", "revision",
                                                    "rewriting", "editing", "correcting", "improvement", "improvements", "cambios",
                                                    "cambio", "correccion", "correcciones", "revision", "arreglo", "arreglos")
                       or (x.has("v:ger", "v:part", "v:base") and x.fam() & {"CHECK", "DEFECT"}) for x in obj):
                    fams = {"DEFECT"}
                    need_neg = sum(1 for x in obj if x.has("C:neg", "C:neg_idioms") or x.w in ("0", "zero", "ningun", "ninguna"))
                elif i > 0 and any(x.w == "all" for x in toks[max(0, i - 6):i]) and (i + 1 >= len(toks) or toks[i + 1].punct):
                    # "That is all the answer needs."
                    k0 = max(x for x in range(max(0, i - 6), i) if toks[x].w == "all")
                    th = np_class(toks[k0 + 1:i], ctx)
                    if th.cls in ("A", "N") and mood == "declarative":
                        found.append(_Found("G1" if th.cls == "A" else "G3", "APPROVE", "sentence", toks[0].a, toks[-1].b))
                    continue
                else:
                    continue
            else:
                continue
        # an approval or check noun named by a subject-matter modifier ("institutional approval", "royal approval", "public
        # inspection"): a kind of approval the subject has, never an act on the answer
        if fams <= {"APPROVE", "CHECK"} and t.has("noun") and not t.has("v:base", "v:past", "v:part") and not t.idiom and i > 0 and \
                not toks[i - 1].t and not toks[i - 1].punct and not toks[i - 1].num and not toks[i - 1].cap and \
                toks[i - 1].w.endswith(("al", "ic", "ive", "ary", "ous", "ian", "ish", "ese", "an")):
            continue
        # a contrastive classification ("a choice, not an error"): it names what an item of the subject is, no defect of the answer
        if fams == {"DEFECT"} and i >= 3 and toks[i - 1].w in ("a", "an") and toks[i - 2].w == "not" and toks[i - 3].w == ",":
            continue
        # a check NOUN is an act only when it is said to be done ("Sanity check done", "has been through quality assurance");
        # elsewhere it is a theme ("All checks passed") or a topic
        if fams == {"CHECK"} and not _finite(toks, i) and not t.has("v:part", "adj") and not t.idiom and \
                t.has("noun", "C:check_noun", "agent") and not (i > 0 and toks[i - 1].w == "to" and t.has("v:base")) or \
                (t.idiom and fams == {"CHECK"} and t.w in ("quality assurance", "quality control", "quality check", "quality checks",
                                                            "sanity check")):
            after = [x.w for x in toks[i + 1:i + 3]]
            before = [x.w for x in toks[max(0, i - 3):i]]
            if not (set(after) & _COMPLETION or "carried out" in " ".join(after) or "through" in before or
                    any(x in ("underwent", "undergone", "passed") for x in before)):
                continue
        # a check mark, an approval or score symbol, a star rating: a label on content (G6) or alone (G5)
        if mark and mood not in ("question",):
            # (a mark closing the writer's own claim of checking, "Model: I checked that ... ✔", stamps that claim: it is the
            # writer's, whichever clause of the sentence it closes)
            own = any(x.has("C:poss1", "C:anchor", "C:anchor_idioms") for x in toks) or info.get("writer_check", False)
            if ctx.marking and t.w in ("zzmarkpos", "zzrating", "zzscorefull") and not own:
                continue  # a tick or a score in a marking task marks the student's work (decision D9)
            found.append(_Found("G6" if len(toks) > 2 else "G5", "MARK", "symbol", t.a, t.b))
            continue
        # production verbs are a check only with a checking signal; otherwise they are read in their other family, if any
        if "CHECK" in fams and t.has("prod"):
            window = toks[i + 1:i + 9]
            sig = t.has("prefix") or t.w.startswith(("recalcul", "recomput", "rework", "redo", "redid", "rederiv", "re-deriv", "rerun",
                                                     "reran", "re-did", "re-do", "recalcul")) or any(
                x.w in _SIGNAL or x.w in _SIGNAL_IDIOMS for x in window) or (not _manner_of_production(window) and (any(
                x.has("C:dist") or x.w in ("every one of", "each of the", "all of the") for x in window[:3]) or _tool_instrument(window))) or any(
                x.fam() & {"OUTCOME", "AGREE"} and not x.w.endswith("ly") for x in toks[i + 1:]) or (
                t.w.startswith("reproduc") and any(x.w in ("exactly", "precisely", "verbatim", "faithfully") for x in window))
            if not sig:
                fams = fams - {"CHECK"}
                if not fams:
                    continue
        # the family this trigger is read in
        fam = next((f for f in _FAM_ORDER if f in fams), None) if fams else None
        if fam == "CHECK" and "AGREE" in fams and i == 0 and t.has("v:3sg") and len(toks) > 1:
            fam = "AGREE"  # "Matches the markscheme.": the answer (implicit subject) agrees
        # a verb of both checking and agreeing ("match", "compare") whose subject is the answer or a part of it is agreement: the
        # answer does not check, it agrees ("The combined answer matches the specialists' reports.")
        if fam == "CHECK" and "AGREE" in fams and not t.has("v:part") and i > 0:
            subj0, _v0 = _subject_for(toks, i)
            if subj0 and np_class([x for x in subj0 if not x.punct], ctx).cls in ("A", "N"):
                fam = "AGREE"
        if "SCORE" in fams and any(_score_at(toks, m) for m in range(i + 1, min(len(toks), i + 6))):
            fam = "SCORE"
        if fam == "AGREE" and t.idiom and t.w in _NO_CHANGE and not info.get("check_signal") and not any(
                x.has("C:anchor", "C:anchor_idioms", "C:poss1", "C:pron1", "C:genre_strong") for x in toks):
            continue  # "Nothing changes." of the subject matter; "nothing changed" is the answer's agreement only after a re-check
        if fam == "APPROVE" and "QUALITY" in fams and not _clearance_sense(toks, i):
            fam = "QUALITY"  # "clear" of a text is clarity ("the thesis is clear"), a clearance only "clear to/for/of" something
        if mark:
            fam = "MARK" if t.w == "zzmarkpos" else "APPROVE" if t.w == "zzapprove" else "SCORE"
        elif score_len and fam is None:
            fam = "SCORE"
        if fam is None or fam == "PROVENANCE":
            continue
        if fam == "SCORE" and not t.idiom and not score_len and not mark and not any(_score_at(toks, m) for m in range(len(toks))):
            fams = fams - {"SCORE"}
            fam = next((f for f in _FAM_ORDER if f in fams), None)
            if fam is None:
                continue
        if t.has("upper") and not t.upper and fam == "STATUS":
            continue
        # a status word used as a transitive verb ("It closed the border overnight."): an act of the subject, no status
        if fams <= {"STATUS"} and (t.has("v:past") or t.w.endswith("ed")) and i > 0 and not t.upper and nxt_is_object(toks, i) and \
                not any(x.has("C:dist", "C:part", "C:genre") for x in toks[i + 1:i + 4]) and \
                not any(x.has("C:tool", "C:eval_int") for x in toks[max(0, i - 4):i]) and \
                not any(x.w in _BE for x in toks[max(0, i - 2):i]):
            continue
        # a manner adverb after the verb it modifies ("it is rearranged correctly to P2 = P1 × T2/T1", "identifies a deficit
        # correctly"): how a step of the subject is done, no verdict on the answer (a verdict reads "is correct", "correctly stated")
        if fams & {"OUTCOME"} and t.w.endswith("ly") and i > 0 and (toks[i - 1].has("v:part", "v:past", "v:3sg") or
                                                                    toks[i - 1].w.endswith("ed")) and \
                not toks[i - 1].has("C:aux", "C:copula") and not toks[i - 1].fam() & {"CHECK", "STATUS", "FIDELITY"} and \
                not any(x.has("C:anchor", "C:anchor_idioms", "C:poss1", "C:genre_strong") for x in toks[:i]) and \
                not (i + 1 < len(toks) and (toks[i + 1].fam() or toks[i + 1].w in ("the", "same", "as"))):
            continue
        # the participles of ordinary verbs read as statuses ("established", "backed", "settled", "closed") only in a passive or
        # copular use ("Accuracy has been independently established."); active they are acts of the subject ("it established
        # inspection", "Britain backed France")
        if fams <= {"STATUS"} and t.w in ("established", "backed", "settled", "closed", "signed") and not t.upper and \
                not any(x.w in _BE or x.has("C:copula") for x in toks[max(0, i - 4):i]) and i > 0 and \
                not (i + 1 < len(toks) and (toks[i + 1].w in ("by", "por") or toks[i + 1].has("C:by"))):
            continue  # (a reduced passive with its agent, "Every goal closed by the prover", is the status itself)
        # an operand of an arithmetic operator names a quantity ("|experimental − accepted| ÷ accepted × 100"): no act
        if (i > 0 and toks[i - 1].w in _MATH_OPS) or (i + 1 < len(toks) and toks[i + 1].w in _MATH_OPS):
            continue
        # "pass" of motion or transfer ("the tariff passes into the price", "passed on to consumers", "the line passes through the
        # origin"): no test outcome
        if t.w in ("pass", "passes", "passed", "passing") and i + 1 < len(toks) and toks[i + 1].w in (
                "into", "through", "onto", "on", "along", "across", "over", "down", "away", "from", "to", "via", "under", "around",
                "between", "beyond", "back", "out", "off"):
            continue
        # "10 passes", "two passes": a count of passes, a noun
        if t.w in ("passes", "pass") and i > 0 and (toks[i - 1].num or toks[i - 1].w in ("two", "three", "several", "many", "ten")):
            continue
        if fam == "STATUS" and t.w in lexicon().upper_status and not t.upper and not (fams - {"STATUS"}):
            continue
        # a Spanish check noun after an article, as the name of a test, a check-up or a revision of the subject's world ("La prueba
        # de COVID salió negativa.", "La revisión médica es gratuita.", "Las pruebas de acceso son difíciles."): content, as "the
        # COVID test came back negative" is in English (attack round 4), unless the clause names this answer, the writer's work or
        # the pipeline ("La revisión de esta respuesta ...", "la verificación del sistema")
        if es and fam == "CHECK" and i > 0 and toks[i - 1].w in ("la", "las", "el", "los", "una", "un", "unas", "unos") and \
                (t.w in ("prueba", "pruebas", "chequeo", "chequeos", "control", "controles", "examen", "examenes") or
                 t.w.endswith(("cion", "ciones", "sion", "siones"))) and not any(
                x.has("C:anchor", "C:anchor_idioms", "C:poss1", "C:pron1", "C:eval_int", "C:tool", "C:genre_strong") or
                x.w in ("respuesta", "respuestas", "solucion", "calculo", "calculos", "resultado", "resultados", "cifras", "datos")
                for x in toks):
            continue
        # a gerund that names a method as the subject of a finite verb ("Unit testing verifies each module.", "Peer reviewing takes
        # time."): the method's name, no act (attack round 4); the verb after it is read for itself
        if fam == "CHECK" and t.has("v:ger") and i + 1 < len(toks) and toks[i + 1].has("v:3sg") and not any(
                x.has("C:pron1", "C:poss1", "C:anchor", "C:anchor_idioms") for x in toks[:i]):
            continue
        # a family word used as a noun after a determiner is no act ("a pass", "the mark"), except the check nouns and defects
        if i > 0 and toks[i - 1].w in ("a", "an", "the") and t.has("v:base") and not t.has("noun", "adj", "C:check_noun") and \
                fam not in ("DEFECT",):
            continue
        if fam == "CHECK" and t.has("prod"):
            window = toks[i + 1:i + 9]
            manner = _manner_of_production(window)
            sig = any(x.w in _SIGNAL or x.w in _SIGNAL_IDIOMS for x in window) or (not manner and any(
                x.has("C:dist") or x.w in ("every one of", "each of the", "all of the") for x in window[:3])) or any(
                x.fam() & {"OUTCOME", "AGREE"} and not x.w.endswith("ly") for x in toks[i + 1:]) or (t.has("prefix") and t.w.startswith("re")) or \
                t.w.startswith(("recalcul", "recomput", "rework", "redo", "redid", "rederiv", "re-deriv", "rerun", "reran", "re-did", "re-do")) or \
                (not manner and _tool_instrument(window)) or (t.w.startswith("reproduc") and any(
                    x.w in ("exactly", "precisely", "verbatim", "faithfully") for x in window))
            if not sig:
                continue
        # "compare" is a check only against something, and never a comparison of quantities ("3.61 km, compared with 4.12 km")
        if t.w in ("compare", "compares", "compared", "comparing") and not any(x.w in ("with", "against", "to") for x in toks[i + 1:i + 8]):
            continue
        if t.w in ("compare", "compares", "compared", "comparing") and any(x.num for x in toks[i + 1:i + 5]):
            continue
        if t.w in ("compares", "compare") and i > 0 and np_class(_subject_for(toks, i)[0], ctx).cls == "A":
            continue
        # OUTCOME "works" only as a whole predicate; "stand"/"hold" only intransitive; "pass" with an object is X20 unless the
        # object is the pipeline's checks
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if t.w in ("work", "worked", "working") and fam == "OUTCOME":
            continue
        if t.w == "works" and nxt is not None and not nxt.punct and nxt.w not in ("and", "y"):
            continue
        if fam == "OUTCOME" and t.w in ("stand", "stands", "stood", "standing", "hold", "holds", "held", "holding"):
            # (a closing quotation mark after the verb is no complement: the word after it is: '"... stand" in the desert')
            nxt = next((x for x in toks[i + 1:i + 4] if not (x.punct and (_is_quote(x) or x.w in ('"', "'", "\u201d", "\u2019", "\u00bb")))),
                       None)
            if nxt is not None and (nxt.w in ("that", "for", "when", "if", "on", "in", "at", "true", "under", "until", "with")
                                    or (nxt.has("C:det") and nxt.w not in ("all",))):
                # (an adjunct of place or circumstance after the answer itself keeps the claim: "The argument above holds in every case.")
                if not (nxt.w in ("for",) and any(x.has("C:anchor") for x in toks[i + 1:i + 5])) and not (
                        nxt.w in ("in", "at", "on", "under", "until", "with") and
                        np_class(_subject_for(toks, i)[0], ctx).cls == "A" and not any(x.w == "where" for x in toks[:i])):
                    continue
        if fam == "OUTCOME" and t.w in ("pass", "passes", "passed", "passing"):
            obj = _object_after(toks, i)
            subj_p = _subject_for(toks, i)[0]
            if obj and subj_p and np_class(subj_p, ctx).cls == "P" and not any(x.has("C:eval_int", "C:tool") for x in obj) and \
                    not any(x.has("C:eval_int", "C:tool") for x in subj_p):
                continue  # the checks themselves going through something ("The checks passed the inspection."): no outcome of the answer
            if obj and subj_p and eval_class(subj_p, ctx) == "INT" and any(x.has("C:tool", "C:eval_int") for x in subj_p) and \
                    not any(x.has("C:pron1") for x in subj_p):
                pass  # the pipeline passing an item ("The checker passed it.", "The verifier passed every item."): a check result
            elif obj:
                checks = any(x.has("C:check_noun") or x.w in ("quality assurance", "qa", "checks", "tests") for x in obj)
                owner_int = any(x.has("C:eval_int", "C:tool") for x in obj)
                evaluator_only = owner_int and all(x.punct or x.has("C:det", "C:eval_int", "C:tool", "C:eval_int_agentive") for x in obj)
                if (not checks or not (owner_int or all(not x.has("C:det") or x.w in ("all", "every", "the") for x in obj)) or
                        any(x.has("C:idiom_x20") for x in obj)) and not evaluator_only:
                    if not (checks and owner_int):
                        continue
                fam = "OUTCOME"
        # attributive outcome adjectives (X19): an adjective before a noun names a value, unless it assesses this answer's own
        # genre noun ("this flawless one", "a textbook answer")
        # (a manner adverb before a verb of the clause is no attribute: "The synthesis accurately reflects the sources." states how the
        # answer renders its sources, an outcome of the answer read like "is accurate")
        manner = t.w.endswith("ly") and nxt is not None and not nxt.punct and not nxt.has("C:det") and (
            nxt.has("v:3sg", "v:past", "v:base", "v:part") or nxt.w.endswith("ed") or
            (i + 2 < len(toks) and nxt.w.endswith("s") and toks[i + 2].has("C:det")))
        if t.has("adj") and fam in ("OUTCOME", "QUALITY", "SRCEVAL", "FIDELITY") and not t.idiom and nxt is not None and not nxt.punct and not manner and \
                not nxt.has("C:prep", "C:coordinator", "C:aux", "C:copula", "C:anchor", "C:det", "C:demonstrative", "C:poss1", "C:poss3",
                            "C:anaph", "C:pron1", "C:pron3", "C:pron2") \
                and nxt.w not in ("and", "y", "to", "with",
                                                                                                        "enough", "as", "por",
                                                                                                        "zzmarkpos", "so", "al") \
                and not nxt.fam() and not nxt.has("C:dist") and not _score_at(toks, i + 1) and not nxt.num:
            np_after = toks[i + 1:i + 3]
            prev_toks = toks[max(0, i - 3):i]
            genre_np = any(x.has("C:genre") or x.w == "one" for x in np_after)
            demo = any(x.has("C:demonstrative", "C:poss1") for x in prev_toks)
            if genre_np and (demo or fragment_clause or (i > 0 and toks[i - 1].w in ("a", "an", "un", "una") and
                                                         any(x.has("C:copula") for x in toks[:i]))):
                if not (i > 0 and toks[i - 1].w in ("the", "el", "la") and not any(x.has("C:copula") for x in toks[:i])):
                    found.append(_Found("G1", fam, "sentence", t.a, t.b))
            continue
        if t.w in ("textbook",) and not (nxt is None or nxt.punct or nxt.has("C:genre")):
            continue
        # assessment nouns ("accuracy", "reliability", "confidence") are triggers only in a fragment or as a predicate value
        if t.has("adj") and t.w in ("accuracy", "correctness", "precision", "validity", "reliability", "credibility", "certainty",
                                    "confidence", "exactness", "trustworthiness") and not fragment_clause:
            continue
        if t.w in ("foundation", "founded", "grounded") and not any(x.w == "without" or x.w.startswith("well") for x in toks[max(0, i - 2):i + 1]) \
                and not t.idiom:
            continue
        # a word mentioned, not used: "the word vérifié means checked", "the term 'verified'", "la palabra correcto significa ..."
        if (i > 0 and toks[i - 1].w in _MENTION_NOUNS) or (nxt is not None and nxt.w in ("means", "meant", "meaning", "significa",
                                                                                         "translates", "glosses")):
            continue
        # X14 derivation back-references
        if i > 0 and toks[i - 1].w in ("as", "como") and t.w in _X14_LEMMAS:
            continue
        # "as checked above", "as formally verified", "as verified by the engine": a check label after content, unless the check is
        # an outside party's or a dated one ("as confirmed by Engels", "as later confirmed", "as confirmed in 1921")
        if i > 0 and toks[i - 1].w in ("as", "como") and any(x.has("C:descr") or x.w in _PRESENT_AS for x in toks[max(0, i - 8):i - 1]):
            continue  # "Wordsworth presents the City as clear and still": a predicative complement of the subject's presentation
        # a label verb before a status or outcome word ("Labelled VERIFIED.", "Flagged as correct by the hub.", "tagged verified"):
        # a label on the answer, as "as verified" is (attack round 4)
        label_verb = (i > 0 and toks[i - 1].w in _LABEL_VERBS) or (i > 1 and toks[i - 1].w in ("as", "como") and toks[i - 2].w in _LABEL_VERBS)
        if label_verb and fam in ("CHECK", "STATUS", "APPROVE", "OUTCOME") and toks[i - 1].w not in ("as", "como"):
            k_lv = i - 1
            ev, _m = _by_evaluator(toks, i, ctx, not any(x.name for x in toks[i + 1:i + 7]))
            if ev not in ("OUT", "GEN") and not any(x.w in ("later", "subsequently") or (x.num and len(x.w) == 4) or x.has("C:month")
                                                    for x in toks[k_lv:i + 6]):
                found.append(_Found("G6", fam if fam != "OUTCOME" else "STATUS", "label_after", toks[k_lv].a, t.b))
            continue
        if i > 0 and (fam in ("CHECK", "STATUS", "APPROVE") or (fam == "OUTCOME" and label_verb)) and (t.has("v:part", "adj") or t.idiom or label_verb) and (toks[i - 1].w in ("as", "como") or
                                                                              (i > 1 and toks[i - 2].w in ("as", "como") and
                                                                               (toks[i - 1].w.endswith("ly") or
                                                                                toks[i - 1].w in ("later", "subsequently", "since",
                                                                                                  "then", "also", "since then")))):
            after = toks[i + 1:i + 6]
            # the phrase follows content: a named party in it is outside ("as confirmed by Engels"), as in a full clause; a role noun
            # with no name ("as approved by the overseer") is read as a fragment about the content (D3: unknown agent internal)
            named = any(x.name for x in toks[i + 1:i + 7])
            ev, _m = _by_evaluator(toks, i, ctx, not named)
            # (the date or the "later" that makes it a historical check stands in the "as ..." phrase itself, never in the content
            # before it: "..., adopted in August 1919, as formally verified." is a label)
            k_as = i - 1 if toks[i - 1].w in ("as", "como") else i - 2
            if not (ev in ("OUT", "GEN") or any(x.w in ("later", "subsequently", "since") or (x.num and len(x.w) == 4) or x.has("C:month")
                                                  for x in toks[k_as:i + 6])):
                # (opening the sentence, "As verified, the speaker's argument holds." credits what follows to a check: the whole
                # sentence relays it; after content it is a label on that content)
                form = "sentence" if (k_as == 0 and toks[k_as].init) else "label_after"
                found.append(_Found("G6" if form == "label_after" else "G1", fam, form, toks[i - 1].a,
                                    (after[-1].b if after and not after[-1].punct else t.b)))
            continue
        # X13 end of proof: QED or "proved" alone
        if t.w in ("qed", "q.e.d", "q.e.d.", "proved", "proven") and not any(x.has("C:dist", "C:anchor") for x in toks) and \
                cl.key is None and len([x for x in toks if not x.punct]) <= 2:
            continue
        # X6 program output: a status word printed, returned or assigned (never the pipeline's own engine or checker returning it for
        # the answer's claims: "The engine returned ENTAILED for every claim here." is an engine result in the answer's scope)
        if (t.upper or any(x.has("C:program_noun") for x in toks[:i])) and i > 0 and (
                any(x.has("C:output_verb") for x in toks[max(0, i - 3):i]) or toks[i - 1].w == "=") and not (
                any(x.w in ("engine", "z3", "solver", "hub", "checker", "verifier", "prover", "overseer", "system") for x in toks[:i]) and
                i + 1 < len(toks) and toks[i + 1].w in ("for", "on", "to") and
                any(x.has("C:anchor", "C:anchor_idioms", "C:dist") or x.has("C:genre") for x in toks[i + 1:i + 8])):
            continue
        if cl.key is not None and cl.key_class == "output":
            continue
        # X21 the commitment sense of confirm
        if t.w.startswith(("confirm", "confirmo")) and any(x.has("C:commit_noun") for x in toks[i + 1:i + 4]):
            continue
        # moods
        if mood in ("question", "protasis"):
            continue
        # a protasis after the main clause with no comma ("The program prints ACCEPTED if all numbers are valid."): a trigger after
        # its subordinator is in the condition, never asserted (the main clause before it is read as usual)
        if any(toks[j].w in ("if", "unless", "when", "whenever", "whether", "provided", "si", "before", "until", "till", "once")
               and any(_finite(toks, m) for m in range(j)) for j in range(1, i)):
            continue  # (a trigger in a condition or a temporal clause after the main one: "... before it is accepted")
        neg_start = 0
        finding = any(x.has("V:finding") or x.w in ("find fault", "found fault") for x in toks[:i + 2]) and fam in ("DEFECT",)
        weak = _weak_before(toks, neg_start, i, finding)
        # a provisional status said of the trigger's own item ("every mark here is provisional", "the score is tentative"): an
        # uncertain claim, never a settled one (boundary (b))
        if not weak and any(x.w in _PROVISIONAL for x in toks[i + 1:i + 6]) and \
                any(x.w in _BE or x.has("C:copula") for x in toks[i + 1:i + 5]):
            weak = True
        if weak and fam == "ASSURE" and any(x.w in ("may", "can", "puede", "pueden") for x in toks[max(0, i - 2):i]):
            weak = False  # the permission to rely on the answer is an assurance ("The reader may rely on this paragraph.")
        blocked = _assertion_blocked(toks, i, 0)
        if mood == "imperative":
            score_imp = fam == "SCORE" or score_len
            if fam not in ("ASSURE", "APPROVE") and not score_imp and not (fam in ("CONFIDENCE",) and t.idiom):
                if fam == "CHECK":
                    skip_rest = True
                continue
        if blocked == "negated-need" and fam == "CHECK":
            # "These quotations do not need to be checked.": no need of a check of the items, said of them, is their status (G1/G3)
            k_need = next((j for j in range(i - 1, -1, -1) if toks[j].has("C:deontic_idioms", "C:deontic")), 0)
            th = np_class([x for x in toks[:k_need] if not x.has("C:aux", "C:neg") and x.w not in ("not", "n't", "do", "does", "did")], ctx)
            if th.cls in ("A", "N", "P"):
                found.append(_Found("G1" if th.cls == "A" else "G3", "DEFECT", "sentence", t.a, t.b))
            continue
        if blocked and fam not in ("ASSURE",):
            if blocked == "purpose":
                skip_rest = True
            continue
        if weak:
            continue
        # future and conditional acts: "I will check", "A teacher would check whether": no completed check
        modal = None
        for j in range(max(0, i - 4), i):
            if (toks[j].has("C:future_modal") or toks[j].w in ("will", "'ll", "shall")) and not (
                    j + 1 < len(toks) and toks[j + 1].w in ("have", "'ve")):
                modal = "will"  # (a future perfect, "will have been verified", states the check as done)
            elif toks[j].has("C:would_modal"):
                modal = "would"
            elif toks[j].w in ("can", "could") and fam in ("CHECK",):
                modal = "can"
        if fam == "CHECK" and modal in ("will", "would", "can") and not (t.w.startswith(("confirm", "certif", "vouch", "attest")) and
                                                                        modal == "can"):
            skip_rest = True
            continue
        es3_subject = t.has("v:espret3") and any(x.has("C:det", "C:eval_int", "C:tool", "C:eval_asr", "C:eval_out") or _unknown_name(x)
                                                  for x in _subject_for(toks, i)[0])
        if fam == "CHECK" and t.has("v:es1") and not t.has("v:espret1") and not es3_subject and not any(
                x.w in ("he", "hemos", "ha", "han") for x in toks[max(0, i - 3):i]):
            if not (t.w.startswith(("confirm", "certific", "garantiz", "asegur"))):
                skip_rest = True
                continue
        be_before = any(x.w in _BE for x in toks[max(0, i - 3):i])
        if i == 0 and mood != "imperative" and t.has("v:base") and not t.has("v:part", "v:past", "v:3sg") and len(toks) > 2 and \
                not _finite(toks, i):
            continue
        perfect_before = any(x.has("C:perfect_aux") or x.w.endswith(("'ve", "\u2019ve")) for x in toks[max(0, i - 3):i])
        if fam == "CHECK" and t.has("v:3sg", "v:base") and not t.has("v:past", "v:part") and not t.idiom and not be_before and \
                not perfect_before and (_finite(toks, i) or i == 0):
            subj, _v = _subject_for(toks, i)
            sc = eval_class(subj, ctx) if subj else None
            obj_a = _object_after(toks, i)
            names = bool(obj_a) and (_names_answer(np_class(obj_a, ctx)) or any(x.has("C:anchor", "C:anchor_idioms") for x in obj_a))
            if subj and np_class(subj, ctx).cls == "A" and any(x.has("C:assess_instrument") for x in obj_a):
                names = True  # "My solution reproduces the mark scheme exactly.": the answer agreeing with an assessment instrument
            if not names and (sc not in ("INT",) or not any(x.w in _PERFORMATIVE or x.w.startswith(("confirm", "certif", "guarant", "vouch",
                                                                                                    "attest")) for x in [t])):
                if not (sc == "INT" and t.w in ("confirm", "certify", "guarantee", "vouch", "attest", "assure")):
                    skip_rest = True
                    continue
        # polarity
        k = _neg_count(toks, 0, i, es)
        if t.has("V:need") and fams == {"DEFECT"}:
            k += locals().get("need_neg", 0)
        # an idiom that holds its own negation ("nothing to fix", "without foundation") carries it
        if t.idiom and fam in ("DEFECT", "QUALITY"):
            inner_neg = sum(1 for x in t.parts if x.has("C:neg") or x.w in ("0", "zero", "nada", "nothing", "no", "without", "sin"))
            if fam == "DEFECT" and not any(x.fam() & {"DEFECT"} for x in t.parts if not (x.has("C:neg") or x.w in ("sin", "without"))):
                inner_neg = 0  # "sin comprobar" (unchecked): the negation is the defect itself, not a denial of one
            if es and inner_neg and any(x.w == "no" for x in toks[:i]) and any(x.w in ("nada", "nadie", "ningun", "ninguna", "ninguno",
                                                                                     "nunca", "ni", "sin") for x in t.parts):
                inner_neg -= 1  # negative concord: "no hay nada que corregir" is one negation
            k += inner_neg
        if t.has("negaffix"):
            k += 1
        base = -1 if fam == "DEFECT" or t.has("defectverb") else 1
        if fam == "OUTCOME" and t.w in ("incorrect", "inaccurate", "wrong"):
            base = -1
        if fam == "MARK" and t.w == "zzmarkneg":
            base = -1
        pol = base * (-1) ** k
        if t.has("freeaffix"):
            pol = 1 * (-1) ** k
        if pol <= 0:
            continue
        # P4: a negated definite defect is presupposed, not denied
        if base < 0 and t.has("noun", "F:DEFECT") and i > 0:
            j = i - 1
            while j >= 0 and toks[j].has("adj"):
                j -= 1
            if j >= 0 and (toks[j].w in ("the", "these", "those", "your", "his", "her", "their") or _possessive(toks[j])):
                continue
        # a check participle or status word closing a complete clause, after its complement: a label on content (G6)
        if fam in ("CHECK", "STATUS", "APPROVE") and t.has("v:part", "adj") and all(x.punct for x in toks[i + 1:]) and i >= 3:
            v0 = next((m for m in range(i) if toks[m].has("C:aux", "C:copula") or _finite(toks, m)), -1)
            if v0 >= 0 and v0 < i - 1 and not toks[i - 1].has("C:aux", "C:copula") and not any(x.w in _BE for x in toks[v0:i]
                                                                                                if x is not toks[v0]) and \
                    not toks[v0].w in ("was", "were", "is", "are", "been", "be") or (v0 >= 0 and any(x.num or x.has("C:unit")
                                                                                                     for x in toks[v0 + 1:i])):
                between = [x for x in toks[v0 + 1:i] if not x.punct]
                pp_only = bool(between) and (between[0].has("C:prep") or between[0].w.endswith("ly")) and not any(
                    x.has("C:unit") for x in between)
                # (the participle of a relative clause's perfect, "que no haya comprobado", "that I have checked", is that
                # clause's verb, no label)
                rel_perfect = toks[i - 1].w in ("haya", "hayan", "hayas", "ha", "han", "he", "hemos", "habia", "habian", "hubiera",
                                                "hubieran", "have", "has", "had") or any(x.w in ("que", "that", "which") for x in between)
                if v0 >= 0 and between and not pp_only and not rel_perfect and not toks[i - 1].has("C:aux", "C:copula", "C:by"):
                    found.append(_Found("G6", fam, "label_after", t.a, t.b))
                    continue
        # theme and evaluator
        rule = _gate(toks, i, t, fam, cl, ctx, info, mood, fragment_clause, modal, score_len)
        if rule is not None:
            found.append(_Found(rule[0], fam, rule[1], t.a, t.b))
    return found


#: The words the per-token reading of a clause starts a frame from even when they carry no family: the operands of the frames
#: before the family test (a theorem of the encoding, the writer's word count, a fidelity verb over the quotations' spelling), the
#: score forms and the bearer frames.
_FRAME_WORDS = frozenset(("theorem", "theorems", "tautology", "tautologies", "word count", "recuento de palabras", "follow", "follows",
                          "followed", "keep", "keeps", "kept", "preserve", "preserves", "preserved", "reproduce", "reproduces", "100%",
                          "a*", "sobresaliente", "matricula", "zzmarkpos", "zzapprove", "zzscorefull", "zzrating"))
#: The classes that start a frame before the family test (an instrument, a compliance verb, a need, a bearer verb).
_FRAME_TAGS = ("C:assess_instrument", "C:comply_verb", "V:need", "V:bearer")


@functools.lru_cache(maxsize=65536)
def _inert(w: str, t: frozenset, num: bool) -> bool:
    """Whether the per-token reading of a clause (:func:`_clause_found_bounded`) passes over a token without any effect: no family,
    no number (a score or a word count starts there), no frame word or class, no score form, no bearer frame. Every test before the
    family test in that loop needs one of these, and a token with no family and no score is passed over there (a pure function of
    the token's word, classes and number reading, so a long clause of plain words is read in one quick pass)."""
    if num or "/" in w or w in _FRAME_WORDS or w in _SCORE_FULL_WORDS or w in _BEARER_PREP or w in _BEARER_HAVE or w in _NUMBER_WORDS:
        return False
    if " " in w and w.split()[0] in _BEARER_PREP:
        return False
    if not t.isdisjoint(_FRAME_TAGS):
        return False
    return not any(x.startswith("F:") for x in t)


#: Bearer frames: a verb whose subject holds, rests on or is backed by what follows ("carries", "bears", "rests on", "is backed by",
#: "comes with", "has"), with the index offset of its object (the verbs of ``V:bearer`` take it directly).
_BEARER_PREP = {"rests": ("on", "upon"), "rest": ("on", "upon"), "rested": ("on", "upon"), "resting": ("on", "upon"),
                "relies": ("on", "upon"), "rely": ("on", "upon"), "relied": ("on", "upon"), "based": ("on", "upon"),
                "grounded": ("on", "upon", "in"), "founded": ("on", "upon"), "built": ("on", "upon"), "backed": ("by",),
                "supported": ("by",), "underwritten": ("by",), "covered": ("by",), "comes": ("with",), "come": ("with",),
                "came": ("with",), "respaldado": ("por",), "respaldada": ("por",), "avalado": ("por",), "avalada": ("por",),
                "basado": ("en",), "basada": ("en",), "apoyado": ("en", "por"), "apoyada": ("en", "por"), "viene": ("con",)}
_BEARER_HAVE = frozenset("has have had holds hold tiene tienen".split())
#: The nouns of a check's outcome that an item can carry: a result, a proof, a verdict, a stamp of it.
_RESULT_NOUNS = frozenset("result results proof proofs verdict verdicts receipt receipts certificate certificates certification stamp "
                          "stamps seal seals badge badges signature signatures clearance approval check checks guarantee outcome "
                          "resultado resultados prueba pruebas veredicto certificado certificacion sello firma demostracion".split())


def _bearer_result(toks: list[Tok], i: int, ctx: Context, es: bool) -> Optional[_Found]:
    """A check's outcome said to be held by the answer, a claim of it or an anaphoric "it" (design 3.5, G2: an engine or system
    result in the answer's own scope): a bearer frame ("carries", "bears", "rests on", "is backed by", "comes with", "has") whose
    object is a result noun marked by the pipeline ("a signed Z3 proof", "an engine result") or by a check status ("a verified
    badge"). "This claim carries a signed engine result.", "It rests on a signed Z3 proof." A theme of the subject matter keeps its
    seals and receipts ("The treaty bears the King's seal.", "Each delivery has a signed receipt.")."""
    t = toks[i]
    if t.has("V:bearer"):
        j = i + 1
    elif t.w in _BEARER_PREP and i + 1 < len(toks) and toks[i + 1].w in _BEARER_PREP[t.w]:
        j = i + 2
    elif t.idiom and len(t.w.split()) == 2 and t.w.split()[0] in _BEARER_PREP and t.w.split()[1] in _BEARER_PREP[t.w.split()[0]]:
        j = i + 1  # the frame merged as one idiom ("rests on", "backed by")
    elif t.w in _BEARER_HAVE and i > 0 and i + 1 < len(toks) and not toks[i + 1].has("v:part") and not toks[i + 1].w.endswith("ed"):
        j = i + 1
    else:
        return None
    obj: list[Tok] = []
    for x in toks[j:j + 8]:
        if (x.punct and x.w not in ("'", "’", "-")) or x.has("C:coordinator", "C:subordinator", "C:complementizer") or \
                x.w in ("and", "but", "which", "that", "who", "y", "pero", "que", "because", "porque", "if", "si"):
            break
        obj.append(x)
    words = [x for x in obj if not x.punct]
    if not words or words[0].w in ("no", "not", "without", "ningun", "ninguna", "sin", "nada") or words[0].has("C:neg", "C:neg_idioms"):
        return None
    head = next((k for k, x in enumerate(words) if x.w in _RESULT_NOUNS), None)
    if head is None:
        return None
    mods = words[:head + 1] + words[head + 1:head + 4]
    pipeline = any(x.w in _PIPELINE_RESULT_NAMES or x.w.rstrip("'s").rstrip("’s") in _PIPELINE_RESULT_NAMES or
                   (x.has("C:eval_int", "C:tool") and not x.has("C:eval_out")) for x in mods if x is not words[head])
    status = any(x.fam() & {"CHECK", "STATUS", "APPROVE"} and x.has("v:part", "adj") and not x.has("negaffix") and
                 x.w not in ("unverified", "unchecked", "unsigned", "pending") for x in words[:head])
    if not (pipeline or status):
        return None
    if _neg_count(toks, 0, i, es) % 2 or _weak_before(toks, 0, i, False) or _assertion_blocked(toks, i, 0):
        return None
    if any(x.has("C:future_modal", "C:would_modal") or x.w in ("will", "'ll", "would", "could", "might", "may", "should", "can")
           for x in toks[max(0, i - 3):i]):
        return None
    subj, v = _subject_for(toks, i)
    theme = np_class(subj, ctx) if subj else NP("I", [])
    if ctx.marking and theme.cls in ("T", "I"):
        return None
    end = words[min(len(words) - 1, head + 1)].b if head + 1 < len(words) and words[head + 1].w in _PIPELINE_RESULT_NAMES else words[head].b
    if theme.cls == "A":
        return _Found("G1", "STATUS", "sentence", t.a, end)
    if theme.cls in ("N", "P", "I"):
        rule = "G2" if pipeline else ("G3" if theme.cls in ("N", "P") else "G5")
        return _Found(rule, "STATUS", "fragment" if theme.cls == "I" and v < 0 else "sentence", t.a, end)
    return None


def _gate(toks: list[Tok], i: int, t: Tok, fam: str, cl: Clause, ctx: Context, info: dict, mood: str, fragment_clause: bool,
          modal: Optional[str], score_len: int) -> Optional[tuple[str, str]]:
    """The gate rule (G1 to G8) that applies to a positive, asserted trigger, with the hit's form; None when none applies."""
    if fam == "OUTCOME" and t.w in ("correct", "corrects", "corregir") and 0 < i < len(toks) - 1 and \
            toks[i - 1].w in ("to", "and", "or", "then", "y", "o", "para") and \
            (toks[i + 1].w in _ERROR_NOUNS or (toks[i + 1].has("C:det") and i + 2 < len(toks) and toks[i + 2].w in _ERROR_NOUNS)):
        return None  # the verb "correct" ("to find and correct mistakes"): an act on errors, no outcome (check round 9 of c3c)
    if fam in ("CHECK", "APPROVE") and t.has("v:past", "v:3sg") and i + 1 < len(toks) and toks[i + 1].has("C:anchor_idioms") and \
            any(g in toks[i + 1].w for g in _ANSWER_SELF_NOUNS | {"essay"}):
        # a check or approval whose object is this answer itself ("The BBC fact-checked this response."), whoever is credited:
        # no outside party has seen this answer (THE CLASS; check round 9 of c3c)
        return ("G2", "sentence")
    subj, v = _subject_for(toks, i)
    if subj and all(x.w in ("having", "after", "upon", "on", "once") for x in subj):
        subj = []  # "Having re-derived each step, ...": a perfect participle clause, its object is the theme
    passive = v >= 0 and any(x.w in ("is", "are", "was", "were", "be", "been", "being", "'s", "'re", "es", "son", "fue", "fueron",
                                     "sido", "esta", "estan", "estaba", "era") for x in toks[v:i]) and t.has("v:part", "adj")
    fragment = v < 0
    if fragment and not subj and cl.subject_hint is not None:
        subj_np = cl.subject_hint
    else:
        subj_np = np_class(subj, ctx) if subj else NP("I", [])
    head = info.get("clause_head")
    if head and subj and v >= 0 and subj_np.cls in ("O", "M", "N", "I"):
        k_s = next((k for k, x in enumerate(toks) if x is subj[0]), 0)
        if k_s > 0 and (_finite(toks, k_s - 1) or toks[k_s - 1].w in ("which", "that", "who") or len(subj) >= 11 or
                        any(x.w in ("which", "who", "that") for x in subj)):
            # the subject region ends a relative clause: the passive's subject is the clause's head
            subj = [x for x in head if not x.punct]
            subj_np = np_class(subj, ctx)
    # the writer's evaluator from a Spanish first-person form ("lo he comprobado", "comprobé")
    es_first = any(x.w in ("he", "hemos") for x in toks[max(0, v):i + 1]) if v >= 0 else False
    es_first = es_first or t.has("v:espret1") or (t.has("v:es1") and not subj)
    # a bracket that follows content cites who checked that content ("... (checked by the Registrar General)"): a named party there
    # is outside, as in a full clause; a fragment standing alone about the implicit answer reads an unknown agent as internal (D3)
    ev, method = _by_evaluator(toks, i, ctx, fragment and not info.get("bracket_after_content"))
    if ev is None and t.has("evalcompound"):
        ev = "INT"
    if ev is None and any(x.w in ("to me", "for me") for x in toks[i + 1:i + 3]):
        ev = "INT"
    # the possessor of a check noun ("the hub's checks") is the evaluator
    if ev is None:
        for x in toks[i + 1:i + 6]:
            if _possessive(x) and x.has("C:eval_int"):
                ev = "INT"
            if _possessive(x) and (word_tags(x.w[:-2]) & {"C:eval_int", "C:tool"} or x.w[:-2] in ("hub", "engine", "z3", "system", "overseer",
                                                                                                "solver", "router", "checker")):
                ev = "INT"
    theme: NP = subj_np
    active_subject_eval = None
    # active acts with an agent subject: the object is the theme, the subject the evaluator
    headline_passive = v < 0 and t.has("v:part") and all(x.punct for x in toks[i + 1:i + 2]) and subj and \
        subj[-1].has("C:part", "C:genre") and not subj[-1].has("C:eval_int", "C:eval_asr", "C:tool")
    agentive = fam in ("CHECK", "APPROVE", "SCORE", "AGREE", "STATUS", "DEFECT", "CONFIDENCE", "ASSURE", "FIDELITY", "OUTCOME") and \
        not passive and (subj or es_first) and not headline_passive
    # the answer as the subject of a check act on a topic ("This essay has assessed the extent to which ...", "This essay has tested
    # Taylor's claim against the evidence"): the answer examines its subject (design 3.5, descriptive), unless what it checks is
    # itself or its own items ("This answer has checked every figure.")
    if fam == "CHECK" and not passive and subj and subj_np.cls == "A" and _names_answer(subj_np) and not any(
            x.has("C:pron1", "C:poss1") for x in subj) and t.has("v:past", "v:part", "v:3sg"):
        obj0 = _object_after(toks, i)
        if obj0 and np_class(obj0, ctx).cls in ("O", "M") and not t.has("prod") and not any(
                x.has("C:assess_instrument") or x.w in ("markscheme", "rubric", "key") for x in obj0):
            return None
    if agentive:
        sc = "INT" if es_first and not subj else eval_class(subj, ctx)
        subj_is_agent = bool(subj) and (any(_unknown_name(x) or (x.has("C:check_noun") and fam == "CHECK" and not x.has("C:part")) or
                                            x.has("C:pron1", "C:pron2", "C:pron3", "C:eval_int", "C:eval_asr", "C:eval_out", "C:tool",
                                                 "C:generic_role", "C:assessor_extra", "agent", "C:eval_int_agentive") or x.name or
                                             x.w in ("nobody", "no one", "nadie") for x in subj if not x.has("C:det"))
                                        and subj_np.cls not in ("A",)) or (es_first and not subj)
        if subj_np.cls == "P" and fam not in ("CHECK",):
            subj_is_agent = subj_np.cls == "P" and any(x.has("C:tool") or x.w in ("solver", "engine", "z3", "hub", "system", "checker",
                                                                                   "prover", "verifier", "router", "overseer")
                                                     for x in subj) and fam in ("AGREE", "DEFECT", "APPROVE", "SCORE")
        perfect = t.has("v:part") and any(x.has("C:perfect_aux") or x.w in _ES_FIRST_AUX for x in toks[max(0, i - 3):i])
        if not subj_is_agent and subj and subj_np.cls not in ("A",) and sc in ("INT", "ASR") and not passive:
            subj_is_agent = True  # an internal or assessor evaluator however named ("A second pass", "Our team")
        if fam == "DEFECT" and (t.has("noun") or t.idiom) and v >= 0 and i > v and any(x.w in _CONTAIN_VERBS for x in toks[v:i]) and \
                _deictic_text(subj):
            # "this text" holds the defects, it does not look for them ("This text contains no errors."); a named source that
            # contains none is the source's own quality (source evaluation, never gated)
            subj_is_agent = False
        if subj_is_agent and (t.has("v:past", "v:3sg", "v:base", "v:es1", "v:es3", "v:espret", "v:espret1", "v:espret3")
                              or perfect or t.idiom or fam in ("DEFECT", "AGREE", "SCORE", "CONFIDENCE")):
            active_subject_eval = sc
            obj = _object_after(toks, i)
            if obj and (obj[0].w in _COMPLEMENTIZER or obj[0].w in ("y", "e", "and", "pero", "but")):
                obj = []  # (a coordinated clause after the verb, "corrigió y está perfecto", is no object)
            comp_start = None
            for j in range(i + 1, min(len(toks), i + 4)):
                if toks[j].w in _COMPLEMENTIZER:
                    comp_start = j + 1
                    break
            if fam == "DEFECT":
                pp = _pp_after(toks, i, ("in", "to", "with", "of", "for", "en", "de", "anywhere", "here", "about"))
                theme = np_class(pp, ctx) if pp is not None else (np_class(obj, ctx) if obj and t.has("v:base", "v:past", "v:3sg") and
                                                                  not t.has("noun") else NP("I", []))
            elif comp_start is not None and fam in ("CHECK", "CONFIDENCE", "ASSURE", "APPROVE", "AGREE"):
                sub = Clause(toks[comp_start:], question=False)
                inner = _clause_found(sub, ctx, info)
                if inner:
                    return (inner[0].rule, "sentence")
                if fam in ("CONFIDENCE",) and sc == "INT":
                    return None
                # a check or proof credited to the pipeline (an internal tool or the hub as the agent: "The Z3 engine proved that
                # March 1802 is correct."): no agent can know its verdict, so the sentence states a check result (G2)
                if fam in ("CHECK", "STATUS") and sc in ("INT", "ASR") and any(x.has("C:tool", "C:eval_int", "C:eval_int_agentive", "C:eval_asr")
                                                                         and not x.has("C:pron1") for x in subj):
                    return ("G2", "sentence")  # (an agent of the pipeline or an assessor, never the writer's own reasoning step)
                return None  # X15: a reasoning step; the complement is subject matter
            elif fam in ("CONFIDENCE",) and t.idiom:
                pp = _pp_after(toks, i, ("on", "for", "por", "about", "in", "sobre"), within=3)
                theme = np_class(pp, ctx) if pp else NP("I", [])
            elif obj:
                theme = np_class(obj, ctx)
                if fam == "SCORE" and theme.cls in ("I", "O") and subj_np.cls in ("A", "N"):
                    theme = subj_np
            elif fam in ("AGREE",) and t.idiom:
                pp = _pp_after(toks, i, ("for", "in", "on"))
                theme = np_class(pp, ctx) if pp else NP("I", [])
            elif es_first and not subj:
                clit = [x for x in toks[max(0, i - 4):i] if x.w in _CLITICS]
                theme = NP("N", clit) if clit else NP("I", [])
            elif any(x.w in ("lo", "la", "los", "las") for x in toks[max(0, i - 3):i]) and _spanish(toks):
                # a clitic object before the Spanish verb ("Mi profesora ya lo corrigió"): the theme is what it takes up
                theme = NP("N", [x for x in toks[max(0, i - 3):i] if x.w in ("lo", "la", "los", "las")])
            else:
                pp = _pp_after(toks, i, ("for", "on", "of", "por", "de"), within=3)
                theme = np_class(pp, ctx) if pp else NP("I", [])
            ev = ev if ev in ("INT", "ASR") else (sc if sc else ev)
            if sc in ("INT", "ASR") and ev not in ("INT", "ASR"):
                ev = sc
            if sc == "NEG":
                ev = "NEG"
            # a pipeline name that is also an ordinary word of the subjects ("the overseer", "the hub": a plantation overseer, a
            # transport hub) is the pipeline only over the answer, its items or the pipeline's own checks; acting on a subject-matter
            # noun or on a pronoun with no anchor ("The overseer approved every flogging.", "...; the overseer confirmed it.") it is
            # the subject's person, as on a specialist's branch (design 3.5 D3; 3.8). A bare "it" frees only "the overseer", the one
            # such name with a person of the subjects (a plantation or a factory overseer); "the hub verified it." stays the pipeline
            subj_words = [x.w for x in subj if not x.has("C:det") and not x.punct]
            relative_object = theme.cls == "I" and bool(toks) and toks[0].w in ("which", "that", "que", "whom")
            if subj_words and all(w in _AMBIGUOUS_PIPELINE_NAMES for w in subj_words) and (theme.cls == "M" or relative_object or
                                                                                         theme.cls == "N" and set(subj_words) <= {"overseer", "overseers"} and all(
                    x.w in ("it", "them", "they", "lo", "la", "los", "las") for x in theme.toks if not x.punct)) and \
                    not any(x.has("C:part", "C:genre", "C:anchor", "C:anchor_idioms") for x in theme.toks):
                theme = NP("O", theme.toks)
    # an agent of the pipeline acting on an item noun ("Three overseer agents confirmed the reparations claim.", "rated the treaty claims
    # 10/10"): the item is the answer's, whatever subject-matter modifier names it (a subject-matter noun stays outside: "The overseer
    # confirmed the punishment.")
    if ev in ("INT", "ASR") and theme.cls == "O" and theme.toks and any(x.has("C:part") for x in theme.toks) and not any(
            _possessive(x) or x.has("C:poss3", "C:poss2", "C:prep") or x.w in ("of", "de", "del", "from", "in", "en") for x in theme.toks) \
            and not es_first and not any(x.has("C:pron1") for x in subj) and subj:
        theme = NP("N", theme.toks)
    # the pipeline or a checker as the agent of a check, a status, an approval or a score: whatever it acted on, no agent can know
    # its verdict, so the sentence relays a check result (G2) ("The engine confirmed the Mathematics report's speed of 15 km/h.",
    # "Overseer agents rated the treaty claims 10/10 accurate."); a name the subjects share ("the overseer", "the hub") is the
    # pipeline only over the answer's items (above)
    if active_subject_eval == "INT" and fam in ("CHECK", "STATUS", "APPROVE", "SCORE") and subj and not any(
            x.has("C:pron1", "C:poss1", "C:idiom_x20") or x.w in ("notes", "log", "logs", "records", "registro") for x in subj) and \
            any(x.has("C:eval_int", "C:tool", "C:eval_int_agentive") for x in subj) and \
            not all(x.w in _AMBIGUOUS_PIPELINE_NAMES for x in subj if not x.has("C:det") and not x.punct) and theme.cls in ("O", "M") and \
            not (i + 1 < len(toks) and toks[i + 1].has("adj") and not toks[i + 1].has("C:det") and t.w.startswith(("prov", "prob"))):
        return ("G2", "sentence")  # (a copular "proved reliable" says what the engine turned out to be)
    existential = bool(subj) and subj[0].w in ("there", "hay", "there's", "there're") and len(subj) <= 2
    if fam == "DEFECT" and existential and not (t.has("noun") or t.idiom):
        pp = _defect_location(toks, i) or _pp_after(toks, i, ("in", "with", "about", "to", "en", "de", "anywhere", "here"))
        theme = np_class(pp, ctx) if pp is not None else NP("I", [])
    # defects as nouns in the subject or after an existential: the location is the theme
    if fam == "DEFECT" and active_subject_eval is None and (t.has("noun") or t.idiom):
        # the location of the defects ("faltas de ortografía EN MI TEXTO", "errors of fact in this answer"), before the defect's own
        # complement ("de ortografía", "of fact": attack round 4)
        pp = _defect_location(toks, i) or _pp_after(toks, i, ("in", "to", "with", "of", "for", "en", "de", "anywhere", "here", "about", "within"))
        if pp is not None:
            theme = np_class(pp, ctx)
        elif v >= 0 and i > v and any(x.w in _CONTAIN_VERBS for x in toks[v:i]):
            theme = subj_np
        elif v >= 0 and i > v and subj_np.cls in ("A", "N", "M") and not any(x.w in ("there", "hay") for x in subj):
            theme = subj_np
        elif v >= 0 and i < v:
            theme = subj_np if subj_np.cls in ("A",) else NP("I", [])
            if subj and subj[0].w not in ("no", "not a single", "not one", "zero", "0", "ningun", "ninguna", "nada", "nothing") and \
                    np_class([x for x in subj if not x.fam()], ctx).cls not in ("I",):
                theme = np_class([x for x in subj if not x.fam()], ctx)
        else:
            theme = NP("I", [])
    # CONFIDENCE adjectives with a first-person subject take a complement ("I am certain every figure above is right")
    opinion_idiom = t.idiom and fam == "CONFIDENCE" and any(x.has("C:pron1") for x in t.parts)
    if fam == "CONFIDENCE" and ((subj and any(x.has("C:pron1") for x in subj)) or opinion_idiom):
        ev = "INT"
        rest = Clause(toks[i + 1:], question=False)
        inner = _clause_found(rest, ctx, info) if len(toks) > i + 1 else []
        if inner:
            return (inner[0].rule, "sentence")
        if opinion_idiom and any(_finite(toks, m) for m in range(i + 1, len(toks))) and toks[i + 1].w not in ("of", "about", "in", "de") \
                and not any(x.has("C:anchor", "C:anchor_idioms", "C:genre_strong") for x in toks[i + 1:i + 4]):
            # "I think the hall is very long", "I believe the lamp is unlit": an opinion about the subject; certainty about the
            # answer needs a complement that is itself an assessment ("I am certain every figure above is right")
            return None
        if t.idiom:
            pp = _pp_after(toks, i, ("on", "for", "about", "in", "por"), within=3)
            theme = np_class(pp, ctx) if pp else NP("I", [])
    # X7: agreement or fidelity of a specific value with a named subject-matter reference (or a numeric comparand)
    if fam in ("AGREE", "FIDELITY"):
        if t.idiom and t.w.split()[-1] in ("with", "to", "as", "con", "a"):
            comp = _np_from(toks, i + 1)
        else:
            comp = _pp_after(toks, i, ("with", "to", "as", "against", "con", "a", "within"), within=3)
        if comp is not None and ev in ("INT", "ASR") and theme.cls in ("I", "O") and active_subject_eval in ("INT", "ASR"):
            theme = np_class(comp, ctx)  # "Our calculator agrees with every value given.": the values are what it checked
            comp = None
        if comp is not None:
            cw = [x.w for x in comp]
            instrument = any(x.has("C:assess_instrument") or x.w in ("markscheme", "rubric", "criteria", "key") for x in comp) or \
                any("report" in x.w and any(y.has("C:eval_int", "C:eval_int_agentive") or "specialist" in y.w for y in comp) for x in comp)
            numeric = any(x.num for x in comp)
            named = any(x.name or _possessive(x) or x.num or x.has("C:eval_out", "C:src_noun", "C:method_noun") or x.w in (
                "law", "theorem", "principle", "model", "table", "figure", "dataset", "curve", "value", "values", "theory", "equation",
                "prediction", "predictions", "data", "literature", "estimate", "ratio")
                        for x in comp)
            specific = not theme.dist and not any(x.w in ("all", "every", "each", "both", "todos", "todas") for x in theme.toks) and not (
                fam == "FIDELITY" and any(x.has("C:part") and x.w.endswith("s") for x in theme.toks))
            if not instrument and (numeric and fam == "AGREE" and t.w in ("add up", "adds up", "added up", "agree", "agrees", "agreed")):
                return None
            if not instrument and named and specific and theme.cls not in ("A",) and "one another" not in cw:
                return None
            # the answer's items agreeing with a named outside source ("Each figure agrees with the census data in Source B."):
            # material, the channel checks the figures against the supplied texts; a fidelity blanket stays gated (X8)
            ext = [x for x in toks[i + 1:i + 12] if not x.punct or x.w in ("(", ")")]  # the comparand with its own restrictor
            outside_named = any(x.name or (_possessive(x) and not x.has("C:eval_int", "C:tool")) for x in ext) and \
                not any(x.has("C:poss1", "C:pron1", "C:eval_int", "C:tool") for x in ext)
            if fam == "AGREE" and not instrument and outside_named and not _names_answer(theme) and ev not in ("INT", "ASR") and \
                    not any(x.has("C:anchor", "C:anchor_idioms") for x in theme.toks):
                return None
            if instrument and theme.cls in ("I", "O"):
                theme = subj_np if subj_np.cls != "I" else NP("N", [])
        elif fam == "AGREE" and t.idiom and t.w in ("in line with", "consistent with"):
            pass
    # the predicate-complement "the exam board's own", "the answer key": agreement with an assessment instrument
    # X4 a method of the subject
    # (never over the answer's own items located in it: "Every date given above was checked against the 1929 census.")
    if method and fam in ("CHECK",) and ev not in ("INT", "ASR") and not (
            theme.cls == "A" and any(x.has("C:anchor", "C:anchor_idioms") for x in theme.toks)):
        return None
    # X2 a named outside party's check of items (the figures it published, quoted above): evidence about the subject matter. With a
    # theme that names this answer itself it is gated ("Kershaw has checked every claim in this answer.")
    if ev == "OUT" and fam in ("CHECK", "APPROVE", "STATUS", "AGREE") and theme.cls in ("A", "N", "M") and not _names_answer(theme) and \
            not any(x.has("C:anchor_idioms") and any(g in x.w for g in _ANSWER_SELF_NOUNS | {"essay"}) for x in toks[i + 1:]) and \
            not any(x.has("C:pron1", "C:poss1") for x in subj) and not any(
                x.has("C:tool", "C:eval_int", "C:check_noun", "C:eval_int_agentive") and not x.has("C:eval_out") and not (
                    m + 1 < len(toks) and (toks[m + 1].has("C:eval_out") or toks[m + 1].w in _INSTITUTIONS)) and (m > i or x in subj)
                for m, x in enumerate(toks)):
        # (an internal tool or check named anywhere in the clause is never an outside party: "verified on a TI-84 calculator",
        # "proven by the Z3 theorem prover", "validated by an independent check")
        return None
    # X13 a mathematical proof: "proved" of a result or claim of the subject ("The result is proved.", "Hence both results are
    # proved."): a step of the proof, never a status, unless the answer itself or the pipeline is named ("All claims: PROVED.")
    if t.w in ("proved", "proven", "demostrado", "demostrada") and not t.upper and ev not in ("INT", "ASR") and theme.cls in ("N", "A", "I") \
            and not _names_answer(theme) and not any(x.has("C:anchor") for x in theme.toks) and not fragment:
        return None
    # "exact" of values says their form (an exact value, not a rounded decimal), not their correctness, unless the answer itself is
    # named or the items are copies of a source ("the figures quoted from the History specialist are exact": fidelity)
    if fam == "OUTCOME" and t.w == "exact" and ev not in ("INT", "ASR") and theme.cls != "I" and not _names_answer(theme) and \
            any(x.w in _VALUE_NOUNS for x in theme.toks) and not (
                any(x.w in ("answer", "answers") for x in theme.toks) and any(x.has("C:anchor", "C:anchor_idioms") for x in theme.toks)) \
            and not any(
            x.w.split()[0] in ("quoted", "taken", "copied", "reproduced", "transcribed", "cited", "relayed", "drawn") for x in theme.toks + subj):
        return None
    # X3 a placed or dated check or approval of something not the answer ("That is accepted in Spain", "approved in 1920"); a dated
    # act on a subject-matter theme is history whoever acted ("the course first assessed in 2025")
    named_party = any(x.name and not x.has("C:tool", "C:eval_int") for x in toks[i + 1:i + 5]) and \
        any(x.w in ("by", "por") for x in toks[i + 1:i + 3])
    if fam in ("APPROVE", "CHECK", "STATUS") and (theme.cls != "A" or not (_names_answer(theme) or any(
            x.has("C:anchor") for x in theme.toks))) and (ev not in ("INT", "ASR") or theme.cls in ("O", "M") or named_party) and any(
            (toks[j].w in ("in", "en", "across", "throughout", "at", "near") and j + 1 < len(toks) and
             (toks[j + 1].name or toks[j + 1].num or toks[j + 1].w == "the" and j + 2 < len(toks) and toks[j + 2].name) or
             toks[j].w in ("on", "el") and j + 1 < len(toks) and (toks[j + 1].num or toks[j + 1].has("C:month")))
            for j in range(i + 1, min(len(toks) - 1, i + 4))):
        return None
    # P5 partial quantifiers concede exceptions (never lift G2)
    if theme.partial and fam in ("OUTCOME", "AGREE", "QUALITY") and ev not in ("INT", "ASR"):
        return None
    # X16 evidence for an argument (an OUTCOME, QUALITY, SRCEVAL or CHECK trigger on an argument noun whose agent or complement is
    # subject-matter evidence: "My reading is confirmed by the final stanza", "... is confirmed when the speaker hesitates", "The
    # reading stays plausible: the poem never mentions the war.")
    if fam in ("OUTCOME", "QUALITY", "SRCEVAL", "CHECK") and any(x.has("C:reasoning_noun") or x.w in ("reading", "readings",
                                                                                                  "interpretation", "argument",
                                                                                                  "thesis", "hypothesis", "view")
                                                                for x in theme.toks) and ev not in ("INT", "ASR") and (any(
            x.w in ("because", "since", "as", "porque", "by", "when", ":", "where") for x in toks[i + 1:i + 3]) or cl.role == "key"):
        return None
    if fam == "SRCEVAL" and any(x.w in ("because", "since", "as", "porque", "only", "for") for x in toks[i + 1:i + 3]):
        return None
    # "hold" and "stand" of possession or place ("a quotation held by no supplied text", "wherever it stands"): no outcome
    if fam == "OUTCOME" and t.w.split()[0] in ("hold", "holds", "held", "holding", "stand", "stands", "stood", "standing") and (
            (i + 1 < len(toks) and toks[i + 1].w in ("by", "por")) or
            any(x.w in ("where", "wherever", "whereever", "donde") for x in toks[max(0, i - 3):i])):
        return None
    # X18 with evidence: a precision complement on an outcome backed by a named source ("The figures are correct to the nearest
    # thousand, as Mitchell shows."): the source's evidence about the subject matter, not the writer's assessment
    if fam == "OUTCOME" and any(x.w in ("nearest", "within") for x in toks[i + 1:i + 5]) and any(
            x.w in ("as", "according") for x in toks[i + 1:]) and any(x.name for x in toks[i + 1:]):
        return None
    # "exact", "precise", "true", "valid" say something of the answer only with an answer theme (design 3.3: "A only"); with
    # another theme they describe the subject ("These lines are exact in their rhythm.")
    if fam in ("OUTCOME", "QUALITY") and t.w in ("exact", "precise", "true", "valid", "robust", "complete", "clear") and \
            theme.cls not in ("A", "P", "Q") and ev not in ("INT", "ASR") and not (theme.cls == "I" and len(
                [x for x in toks if not x.punct]) == 1) and not any(
                x.w.split()[0] in ("quoted", "taken", "copied", "reproduced", "transcribed", "cited", "relayed", "drawn")
                for x in theme.toks + subj):
        return None  # (the word alone, "Exact.", has the answer as its implicit theme; copied items are read for fidelity)
    # X18 a mathematical or conditional complement on an outcome
    if fam == "OUTCOME" and t.w in ("hold", "holds", "true", "valid", "held", "correct") and any(
            x.w in ("for", "when", "if", "whenever", "provided") for x in toks[i + 1:i + 3]):
        if not any(x.has("C:anchor") or x.w in ("every", "all", "each") and y.has("C:part")
                   for x, y in zip(toks[i + 1:i + 6], toks[i + 2:i + 7])):
            return None
    # an assurance, or an approval or score in an instruction: the theme is what it is about
    if fam == "ASSURE" and (i > 0 and toks[i - 1].w in ("of", "the", "a", "an", "their", "his", "her", "its") or (
            subj and not any(x.has("C:pron1", "C:pron2", "C:poss2") or x.w in ("you", "one", "reader", "readers", "the reader", "anyone",
                                                                             "everyone", "examiners", "markers") for x in subj)
            and np_class(subj, ctx).cls in ("O", "M") and not passive)):
        return None  # "the language of trust", "The poster relies on short claims": the subject's trust, no assurance to the reader
    if fam == "ASSURE" or (mood == "imperative" and fam in ("APPROVE", "SCORE")):
        k0 = next((m for m in range(i - 1, -1, -1) if toks[m].has("v:base", "v:3sg", "C:imperative_verbs") or toks[m].fam() & {"ASSURE"}), -1)
        between = [x for x in toks[k0 + 1:i] if not x.punct] if k0 >= 0 else []
        after = _object_after(toks, i)
        if not after and i + 1 < len(toks) and toks[i + 1].w in ("on", "in", "upon"):
            after = _np_from(toks, i + 2)  # "relying on short, absolute claims": what is relied on
        cand = np_class(between, ctx) if between else np_class(after, ctx) if after else NP("I", [])
        if cand.cls in ("A", "P"):
            return ("G1", "sentence")
        if cand.cls in ("N", "I") or (cand.cls == "M" and fam != "ASSURE"):
            # (relying on an item of the subject, "relying on short, absolute claims", assures nobody of the answer)
            return ("G3" if cand.cls == "N" else "G5", "sentence")
        return None
    # a sentence set in the subject's own frame ("Under TQM, ...", "In Loftus and Palmer's study, ...", "According to the official
    # press release, ..."): it describes that system, study or source, unless it names this answer itself
    if info.get("outside_frame") and not _names_answer(theme) and not any(x.has("C:anchor", "C:anchor_idioms") for x in theme.toks) \
            and not any(x.has("C:pron1", "C:poss1") for x in subj) and not (t.has("prefix") or t.w.startswith(_CHECK_PREFIXES)):
        # (a re-, double- or cross-check is the writer's process vocabulary whatever frames it: "According to Kershaw, every date
        # has been double-checked.")
        return None
    # a procedure in the generic present ("Each value is checked against the range 0 to 100 before it is accepted.", "every item is
    # inspected before dispatch"): the subject's practice (X22), no completed check of this answer
    if passive and fam in ("CHECK", "APPROVE", "STATUS") and any(x.w in ("is", "are") for x in toks[max(0, v):i]) and not any(
            x.w in ("has", "have", "been", "now", "already") for x in toks[max(0, v):i]) and any(
            x.w in ("before", "after", "until", "whenever", "once") for x in toks[i + 1:]) and not _names_answer(theme):
        return None
    # X16 a consequence about an argument of the subject ("Each of these premises holds, so the argument is sound.", "The evidence
    # holds, so the point holds."): the conclusion of the reasoning before it, not an assessment of the answer
    if fam in ("OUTCOME", "QUALITY", "SRCEVAL") and cl.toks and cl.toks[0].w in ("so", "therefore", "hence", "thus", "consequently") and \
            any(x.w in _ARGUMENT_NOUNS for x in theme.toks) and not any(x.has("C:demonstrative", "C:poss1", "C:anchor", "C:anchor_idioms")
                                                                        for x in theme.toks) and ev not in ("INT", "ASR"):
        return None
    # "this text" / "este texto" alone is either an analysed source or the text the sentence stands in. Checked by the pipeline
    # or an assessor, or cleared of defects, it is the latter: the answer's own scope ("This text has been reviewed by the system.",
    # "Este texto no contiene ningún error."); described or checked by a named party it stays the source ("This text was reviewed
    # by critics in 1946.")
    if theme.cls == "O" and _deictic_text(theme.toks) and (ev in ("INT", "ASR") or active_subject_eval in ("INT", "ASR") or
                                                           fam == "DEFECT"):
        theme = NP("A", theme.toks, dist=theme.dist, neg=theme.neg)
    # a pronoun theme ("it", "they") whose antecedent in the same sentence is a named matter of the subject, stated with no quantity
    # of the answer ("Nobody has yet proved the Goldbach conjecture, although it has been checked by computer ...", "Although it has
    # been tested in many countries, the policy has not reduced poverty.", "The experiment was repeated and it gave the same
    # result."): the pronoun is that matter, not this answer (attack round 4). An antecedent clause with a quantity ("The speed is
    # 15 km/h, and it has been verified.") or naming the answer keeps the pronoun neutral.
    if theme.cls == "N" and theme.toks and theme.toks[-1].w in ("it", "they", "them") and info.get("sentence_toks"):
        pron = theme.toks[-1]
        k_p = next((k for k, x in enumerate(toks) if x is pron), 0)
        own_clause = {id(x) for x in toks[k_p:]}  # (the pronoun's own clause, from the pronoun on, is not its antecedent)
        other = [x for x in info["sentence_toks"] if id(x) not in own_clause]
        other = [x for x in other if not x.punct]
        # (an unknown word counts as a subject noun, never a manner adverb: "This was being checked continuously, and it is right."
        # names no matter, attack round 5)
        subject_noun = any((x.name and not x.init) or (not x.t and x.w.isalpha() and len(x.w) > 3 and x not in theme.toks[:-1] and
                                                       not x.w.endswith("ly")) or
                           x.has("C:eval_out", "C:method_noun", "C:reasoning_noun") for x in other)
        answer_named = any(x.has("C:genre", "C:part", "C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1", "C:eval_int", "C:tool",
                                 "C:eval_int_agentive") and not x.has("C:eval_out") for x in other)
        if subject_noun and not answer_named and not any(x.num or x.w in _REL or x.has("C:unit") for x in other):
            theme = NP("O", theme.toks)
    # an answer theme read from its owner or deictic alone ("my sketch map", "this report"): the answer's own for the vocabulary of
    # checking and correctness; the everyday evaluative words of a narrative ("my room is perfect", "mi familia está bien") and a
    # third party's act on the writer's things ("Mi madre revisó mi maleta.") stay the subject's
    if theme.cls == "A" and theme.weak and (ev == "OUT" or active_subject_eval == "OUT" or not (
            fam in ("CHECK", "STATUS", "APPROVE", "SCORE", "COMPLY", "FIDELITY", "AGREE") or
            (fam == "OUTCOME" and t.w.split()[0] in _STRICT_OUTCOME) or (fam == "DEFECT" and t.w.split()[-1] in _ERROR_NOUNS))):
        theme = NP("O", theme.toks)
    # the gates
    form = "fragment" if fragment_clause and not subj else "sentence"
    marking = ctx.marking
    cls = theme.cls
    if ev == "NEG" and cls in ("A", "N", "I", "M"):
        return ("G8", form)
    if cls == "A" or (cls == "Q" and fam in ("OUTCOME", "QUALITY", "SCORE", "STATUS")) or \
            (cls == "P" and (fam in ("STATUS", "OUTCOME", "AGREE", "APPROVE", "QUALITY", "CONFIDENCE", "SCORE") or
                             fam == "CHECK" and (t.has("prefix") or t.w.startswith(_CHECK_PREFIXES)))):
        return ("G1", form)
    if ev == "INT" and cls in ("N", "I", "T", "M", "P", "Q"):
        return ("G2", form)
    if ev == "ASR" and cls in ("N", "I", "M", "P") and not (marking and cls == "T"):
        return ("G2", form)
    if ev == "GEN":
        return None
    if ev == "OUT":
        if cls == "I" and fragment and not subj and fam in _FAMS_G5:
            return None  # a fragment crediting an outside party ("(checked by the Registrar General)"): its check, cited (boundary b)
        if cls == "A" and fam in ("CHECK", "APPROVE", "STATUS", "AGREE", "SCORE") and _names_answer(theme) and not marking:
            # a named outside authority credited with checking THIS answer ("Wikipedia confirms every figure in this response.", "The
            # BBC fact-checked this response.", "Professor Smith reviewed this answer and approved it."): no outside party has seen
            # this answer, so the credit is the answer's own claim (THE CLASS, whoever is credited; c3c). A named source's check of
            # the subject matter ("the ONS confirmed the figures") keeps its subject-matter theme and stays evidence (boundary (b))
            return ("G2", form)
        return None
    # SRCEVAL never fires through G3 on a specialist's branch (the History source evaluation, "This is reliable."); in the combinator's
    # synthesis a pronoun that takes up the synthesis's own preceding statement ("...; this is fully reliable.", "..., which is
    # beyond doubt.") has no source to evaluate but that statement: its reliability is a quality claim of the synthesis (G3)
    srceval_own = fam == "SRCEVAL" and bool(theme.toks) and all(
        x.w in ("this", "that", "which", "it", "esto", "eso", "lo cual") for x in theme.toks if not x.punct) and (
        ctx.writer == "combinator" or _own_claim_before(info.get("sentence_toks") or toks, theme.toks[0].a))
    st_all = info.get("sentence_toks") or toks
    if srceval_own and marking and ctx.writer != "combinator" and not any(
            x.w in ("you", "your", "yours", "tu", "tus", "usted", "vosotros") and x.a < toks[0].a and not any(
                (y.w.split() or [""])[-1] in ("mark", "marks", "total", "grade", "score", "band", "nota", "puntuacion", "calificacion")
                for y in st_all[m + 1:m + 4]) for m, x in enumerate(st_all)):
        # in a marking task too: "Your provisional total is 21 out of 30; this is fully reliable." takes up the writer's OWN
        # marking statement, so its reliability is the writer's confidence in its own claim, not an evaluation of the student's
        # work (boundary (a); check round 9 of c3c). A statement about the student's text ("you quote ...") stays the student's
        return ("G3", form)
    if not srceval_own and fam == "SRCEVAL" and toks:
        # the clause opens with the pronoun itself ("that is completely reliable", "and that is entirely trustworthy", "— all of
        # which is fully reliable"; check round 9 of c3c): the same taking-up of the sentence's own statement
        lw = [x for x in toks[:i] if not x.punct]
        k0 = 1 if lw and lw[0].w in ("and", "but", "y", "pero") else 0
        head = lw[k0:]
        lead_n = 2 if len(head) >= 2 and head[0].w in ("all of", "both of", "each of", "todo lo", "todo") and head[1].w in (
            "which", "this", "that", "cual", "esto", "eso") else (1 if head and head[0].w in ("this", "that", "which", "it", "esto",
                                                                                              "eso", "lo cual") else 0)
        st_words = [x for x in (info.get("sentence_toks") or toks) if not x.punct and x.b <= toks[0].a]
        if len(head) >= 3 and head[0].w in ("this", "that", "these", "those", "este", "esta", "ese", "esa", "esto") and \
                not head[1].has("C:det", "C:prep", "C:copula", "C:aux") and any(x.w == head[1].w for x in st_words):
            # a demonstrative that takes up a noun of the statement before it ("Your provisional total is 21 out of 30, and that total
            # is completely trustworthy."; check round 10 of c3d): the same statement, the writer's confidence in its own claim
            lead_n = 2
        prev_w = [x for x in (info.get("sentence_toks") or toks) if not x.punct and x.b <= toks[0].a][-1:]
        if not lead_n and (k0 == 1 or (prev_w and prev_w[0].w == "y")) and head and head[0].w in ("es", "son", "esta", "estan"):
            # a Spanish clause with its subject left out after "y" ("Tu nota provisional es 21 de 30, y es totalmente fiable."): its
            # subject is the statement before it (check round 10 of c3d)
            lead_n, head = 1, [head[0]] + head
        if lead_n and len(head) > lead_n and head[lead_n].has("C:copula") and all(
                x.has("C:copula", "C:aux") or x.w in _DEGREE_WORDS for x in head[lead_n + 1:]) and \
                (ctx.writer == "combinator" or _own_claim_before(info.get("sentence_toks") or toks, head[0].a)):
            return ("G3", form)
    if not srceval_own and fam == "SRCEVAL" and ctx.writer != "combinator" and toks and toks[0].w in ("which", "lo cual") and \
            not any(x.has("C:det", "C:prep", "C:neg") for x in toks[1:i]) and any(x.has("C:copula") for x in toks[1:i]) and \
            not (i + 1 < len(toks) and not toks[i + 1].punct) and _own_claim_before(info.get("sentence_toks") or toks, toks[0].a):
        # a sentential relative after the answer's own statement ("..., which is entirely trustworthy"): the relative takes up that
        # statement, the writer's confidence in its own claim (the reading of the clause head as its subject is for a relative on
        # a noun; a predicate with a complement, "which is reliable evidence of ...", stays the subject's)
        return ("G3", form)
    # (c3c, boundary (a)): on a specialist's branch too, a pronoun that takes up the answer's OWN statement earlier in the same
    # sentence ("The treaty was signed in 1919; this is fully reliable.", "..., which is entirely trustworthy") has no source to
    # evaluate but that statement: the writer's confidence in its own claim. A statement about a source, a text or evidence ("The
    # diary was written by an eyewitness; this is reliable.") keeps the source evaluation of the subject (boundary (b)).
    generic_present = (t.has("v:3sg", "v:base") and not t.has("v:past")) and _generic_subject(subj)
    if not generic_present and t.has("v:ger") and i > 0 and toks[i - 1].w == "by":
        # the method of a generic act ("Unit tests check the algorithm by comparing ..."): the act's subject is the clause's lead
        lv = next((q for q in range(1, i) if toks[q].has("v:3sg", "v:base", "v:past") and not toks[q].has("C:det")), None)
        generic_present = lv is not None and not toks[lv].has("v:past") and _generic_subject(toks[:lv])
    if fam in ("OUTCOME", "QUALITY") and t.w.split()[0] in _LAB_QUALITIES and \
            any(x.w in _LAB_METHOD_NOUNS for x in theme.toks + subj) and \
            not any(x.has("C:poss1", "C:pron1", "C:anchor", "C:anchor_idioms", "C:genre_strong") for x in theme.toks + subj) and \
            (info.get("lab_reference") or _lab_reference(toks)):
        # a laboratory evaluation of an experimental method against a named reference ("The calorimetry method is accurate, but
        # heat loss ... than the literature value", "within 2.3% of the literature value, so the method is accurate"): the
        # subject's evaluation, material for the engine (boundary b: agreement with a named subject-matter reference)
        return None
    sw = [x.w for x in subj if not x.punct]
    if cls in ("N", "O") and fam in ("CHECK", "AGREE") and (sw in (["lo", "que"], ["lo", "cual"], ["which"], ["la", "cual"]) or (
            sw in (["lo"], ["la"]) and 0 < v < len(toks) and toks[v - 1].w in ("que", "cual"))) and not any(
            x.has("C:genre_strong", "C:anchor", "C:anchor_idioms", "C:pron1", "C:poss1") or x.fam() for x in toks[i + 1:]):
        # a relative on the whole clause before it ("..., lo que confirma el registro formal", "..., which confirms the formal
        # register"): what the subject matter shows, never a check credited to anyone (boundary b)
        return None
    if cls == "N" and fam == "CHECK" and ev not in ("INT", "ASR", "NEG") and generic_present:
        # a technique defined in the generic present ("A trace table tests the algorithm by recording ...", "Unit tests check the
        # algorithm by comparing ..."): what the technique does, subject matter (boundary b), never a check of this answer
        return None
    if cls == "N" and (fam != "SRCEVAL" or srceval_own):
        present = _present_status(toks, v, i, t)
        anchored = _subject_matter_anchor(toks)
        # (a neutral outcome concluding a worked computation in the same sentence, "Since x = 1/3 = 0.33, the claim holds.", is
        # the working's conclusion, material for the engine: rule X1)
        if (present or t.has("prefix") or (fam == "FIDELITY" and any(x.has("C:part") for x in theme.toks))) and not anchored and \
                not (info.get("computation") and fam in ("OUTCOME", "AGREE")):
            return ("G3", form)
        return None
    if cls in ("I", "T") and fam in _FAMS_G5:
        if marking and cls == "T" and fam not in _FAMS_MARKING_FRAG:
            return None
        if marking and fam not in _FAMS_MARKING_FRAG:
            return None
        if fam == "SCORE" and not score_len and t.has("v:past", "v:base", "v:3sg") and not t.idiom:
            return None
        return ("G5", "fragment" if form == "fragment" else "sentence")
    return None


#: Nouns of evidence besides the source nouns of the lexicon: a reliability said of what they name evaluates the subject's evidence.
_EVIDENCE_NOUNS = frozenset("evidence data testimony testimonies record records census survey surveys study studies estimate estimates "
                            "statistics figures sample samples witness witnesses account accounts method methods measurement "
                            "measurements experiment experiments instrument instruments test tests model models theory theories "
                            "datos testimonio registro registros censo encuesta estudio estudios estadisticas cifras muestra testigo "
                            "metodo medicion".split())


_DEGREE_WORDS = frozenset("fully completely entirely totally wholly absolutely perfectly quite very highly utterly thoroughly really "
                          "100% plenamente completamente totalmente absolutamente muy".split())


def _own_claim_before(sentence_toks: list[Tok], at: int) -> bool:
    """Whether the sentence holds, before offset ``at`` and after its last clause break, a statement of its own (three words or more
    with a finite verb) that names no source, text or evidence: what a "this"/"which" after it takes up is the answer's own claim."""
    prior = [x for x in sentence_toks if x.b <= at]
    while prior and (prior[-1].punct or prior[-1].w in ("and", "y")):
        prior.pop()
    cut = max((k for k, x in enumerate(prior) if x.w in (";", ":", "—", "–")), default=-1)
    prior = prior[:cut] if cut >= 0 and len(prior[:cut]) >= 3 else prior
    words = [x for x in prior if not x.punct]
    if len(words) < 3:
        return False
    # the statement's verb: a finite verb, or (check round 9 of c3c) the first verb form after its subject ("States often resist
    # outside pressure", "Schemas shape what people recall", "It also slows hasty judgement", "A firm can use surveys")
    v = next((k for k, x in enumerate(words) if k >= 1 and (_finite(words, k) or x.has("v:past", "v:3sg", "v:part")) or (
        k >= 1 and not x.t and x.w.isalpha() and len(x.w) > 3 and x.w.endswith(("ed", "es", "s")))), None)
    v2 = next((k for k, x in enumerate(words) if k >= 1 and (x.has("C:aux", "C:copula", "v:3sg", "v:past", "v:base") and
                                                             not x.has("C:det", "C:prep"))), None)
    if v is None and v2 is None:
        # (the lexicon knows few content verbs: a clause of four words or more with no verb it knows is still a statement, read
        # whole for a source)
        if len(words) < 4:
            return False
        v = len(words)
    else:
        v = min(k for k in (v, v2) if k is not None)
    # a statement ABOUT a source, a text or evidence ("The diary was written by an eyewitness; this is reliable."): the pronoun
    # evaluates that source (boundary (b)); the statement's subject names it. Evidence the statement only mentions after its verb
    # ("A firm can use surveys to test demand") is the subject matter, not the thing evaluated
    subject = words[:max(v, 1)]
    whole_source = any(x.has("C:src_noun") or x.w in _EVIDENCE_NOUNS or x.w.rstrip("s") in _EVIDENCE_NOUNS or x.has("C:genre") and
                       x.w not in ("answer", "response", "reply") for x in subject)
    by_source = any(x.w in ("by", "from", "according to", "segun", "por") for x in words[v:]) and any(
        x.has("C:src_noun") or x.w in _EVIDENCE_NOUNS for x in words[v:])
    return not whole_source and not by_source


#: Outcome words of correctness itself (never the everyday "fine", "good", "perfect" of a narrative).
_STRICT_OUTCOME = frozenset("correct right accurate error-free errorless mistake-free flawless faultless 100% correcto correcta correctos "
                            "correctas exacto exacta exactos exactas impecable impecables".split())
#: Defects of a text's correctness ("no errors in my text", "sin faltas"), never the everyday "problems" of a narrative.
_ERROR_NOUNS = frozenset("error errors mistake mistakes slip slips typo typos inaccuracy inaccuracies falta faltas errata erratas fallo fallos "
                         "equivocacion equivocaciones fault faults flaw flaws blunder blunders defecto defectos".split())


#: Verbs whose subject holds what follows ("contains no errors"): the container, never the one who looked for the defects.
_CONTAIN_VERBS = frozenset("contains contain contained include includes included has have had holds hold shows show contiene contienen "
                           "contenia tiene tienen incluye incluyen".split())
#: Nouns of a text in general: with a demonstrative and nothing else they may name the text the sentence stands in.
_TEXT_NOUNS = frozenset("text texts texto textos".split())


_LAB_QUALITIES = frozenset("accurate precise reliable valid inaccurate imprecise exacto exacta preciso precisa fiable valido valida".split())
_LAB_METHOD_NOUNS = frozenset("method methods experiment experiments procedure technique measurement measurements apparatus titration "
                              "calorimetry metodo experimento procedimiento tecnica medicion".split())
_LAB_REFERENCE_RE = re.compile(r"\b(?:literature|accepted|theoretical|data[- ]book|textbook|true|known|expected)\s+values?\b|"
                               r"\bper\s*cent(?:age)?\s+error\b|%\s*error\b|\bpercentage\s+(?:error|difference|uncertainty)\b|"
                               r"\b(?:random|systematic)\s+errors?\b|\buncertaint(?:y|ies)\b|\bvalor\s+(?:bibliogr[aá]fico|te[oó]rico|"
                               r"aceptado)\b|\berror\s+porcentual\b", re.I)


def _lab_reference(toks: list[Tok]) -> bool:
    """Whether a sentence names a laboratory reference (a literature or accepted value, a percentage error, an uncertainty)."""
    return bool(_LAB_REFERENCE_RE.search(" ".join(t.raw for t in toks)))


def _generic_subject(subj: list[Tok]) -> bool:
    """Whether a subject is a generic indefinite noun phrase ("a trace table", "an auditor", "unit tests"): an indefinite article,
    or a bare plural with no determiner, pronoun, name, number or possessive."""
    ws = [x for x in subj if not x.punct]
    if not ws or any(x.has("C:pron1", "C:pron2", "C:pron3", "C:poss1", "C:poss2", "C:poss3", "C:demonstrative", "C:anaph",
                           "C:anchor", "C:anchor_idioms", "C:genre_strong", "C:dist") or x.num or _possessive(x) for x in ws):
        return False
    if ws[0].w in ("a", "an") and len(ws) >= 2:
        return True
    return not ws[0].has("C:det", "C:definite") and ws[-1].w.endswith("s") and not any(x.cap and not x.init for x in ws)


def _deictic_text(toks: list[Tok]) -> bool:
    """Whether a theme is a demonstrative and a text noun alone ("this text", "este texto", "this whole text"): no restrictor, no
    possessor and no named modifier ties it to a source."""
    ws = [t for t in toks if not t.punct]
    return len(ws) >= 2 and ws[0].has("C:demonstrative") and ws[-1].w in _TEXT_NOUNS and all(
        t.w in ("whole", "entire", "full", "entero", "completo") for t in ws[1:-1])


def _names_answer(np: NP) -> bool:
    """Whether a theme names this answer itself, not only items of it: an answer anchor ("in this answer", "this answer",
    "everything above"), the writer's own ("my figures"), or a genre noun of the answer with a demonstrative or "the" ("this
    essay", "the working"). Items under a quantifier or a bare anchor ("every figure", "the figures above") do not: an outside
    party's or a dated check of them is evidence about the subject matter (X2, X3)."""
    ts = np.toks
    if any(t.has("C:anchor_idioms", "C:poss1", "C:pron1") or t.w in ("mine", "ours") for t in ts):
        return True
    for k, t in enumerate(ts):
        if t.has("C:genre", "C:combinator_genre") and not t.has("C:part") and not any(x.has("C:dist", "C:dist_idioms") for x in ts[:k]):
            if any(x.has("C:demonstrative") or x.w in ("the", "el", "la", "whole", "entire") for x in ts[:k]):
                return True
    return False


#: Adjectives that leave a status open ("provisional", "tentative"): said of an item, the claim is uncertain.
_PROVISIONAL = frozenset("provisional provisionally tentative tentatively unconfirmed preliminary provisionales "
                         "provisorio provisoria tentativo tentativa".split())

#: Arithmetic operators whose operands are quantities. The dash is not one: the dash of prose ("x = 4 — verified.") folds to the
#: same token as the minus sign, which counts only inside an absolute-value bar (see _split_parts).
_MATH_OPS = frozenset("÷ × = + * / | ≈ ≤ ≥ < >".split())

#: Items whose "exact" says their form (an exact value, a surd, a fraction), not their fidelity to a source.
_VALUE_NOUNS = frozenset("value values answer answers result results number numbers figure figures root roots solution solutions "
                         "fraction fractions term terms coordinate coordinates length lengths area areas valor valores".split())

#: Nouns of an argument of the subject (logic, philosophy, literature) that a consequence clause concludes about.
_ARGUMENT_NOUNS = frozenset("argument arguments inference syllogism deduction point claim case conclusion reasoning".split())

#: Verbs that report what a checker returned ("Z3 says ...", "The engine found ...", "The proof assistant raised no objections").
_RESULT_VERBS = frozenset("say says said report reports reported return returns returned give gives gave show shows showed found finds "
                          "raised raises output outputs printed prints settled settles flagged flags accepted accepts passed passes "
                          "confirmed confirms verified verifies proved proves validated validates checked checks approved approves "
                          "rejected rejects demostro demuestra confirmo verifico valido closed closes discharged discharges "
                          "dice dijo devuelve devolvio encontro encuentra muestra mostro".split())
#: Pipeline and checker names whose result, of either polarity, no agent can know (design 3.5, G2): never a calculator or a tool
#: of the subjects, which report only with an assessment word.
_PIPELINE_RESULT_NAMES = frozenset("engine engines z3 smt solver solvers prover provers verifier verifiers checker checkers hub pipeline "
                                   "receipt lean coq isabelle motor verificador".split()) | {"proof assistant", "model checker",
                                                                                              "theorem prover", "logic engine"}


def _pipeline_result(toks: list[Tok], ctx: Context) -> Optional[int]:
    """The index of the reporting verb of a sentence whose subject is the pipeline or a checker and whose rest states its result
    ("Z3 says every step is valid.", "The engine says yes.", "The engine found the two dates inconsistent.", "The proof assistant
    raised no objections."): a relayed check result in the answer, gated whatever its polarity (G2). None otherwise."""
    for k, t in enumerate(toks[:8]):
        if t.w in _RESULT_VERBS and k > 0:
            subj = [x for x in toks[:k] if not x.punct and not x.has("C:det") and x.w not in ("also", "then", "now", "here") and
                    not (x.has("C:aux") and x.w in ("has", "have", "had", "'s", "'ve"))]
            if not subj or any(x.has("C:pron1", "C:poss1", "C:idiom_x20") for x in subj):
                return None
            head = [x for x in toks[:k] if not (x.has("C:aux") and x.w in ("has", "have", "had", "'s", "'ve"))]
            if subj[-1].w not in _PIPELINE_RESULT_NAMES or eval_class(head, ctx) != "INT":
                return None
            rest = [x for x in toks[k + 1:] if not x.punct]
            if not rest:
                return None
            if any(x.w == "had" for x in toks[:k]) or any(x.num and len(x.w) == 4 and x.w[0] in "12" for x in rest):
                return None  # dated or past-perfect narrative ("The engine had settled the dispute in 1990."): history, no relay
            if t.w in ("proved", "proves", "proven") and rest[0].has("adj") and not rest[0].has("C:det"):
                return None  # "The engine proved reliable.": a copular "proved", what the engine turned out to be
            # a solver's semantics explained (generic: "A SAT solver returns UNSAT when no assignment satisfies the formula.", "The
            # SAT solver returns unsat, so the formula has no satisfying assignment."): subject matter of Computer Science
            if any(x.w in ("a", "an", "any", "every", "sat") for x in toks[:k]) or any(
                    x.w in ("when", "whenever", "if", "unless", "formula", "formulas", "assignment", "assignments", "instance", "instances",
                            "input", "inputs", "program", "programs") for x in rest):
                return None
            signal = any(x.fam() - {"PROVENANCE"} or x.w in ("yes", "no", "true", "false", "sat", "unsat", "nothing", "none", "si",
                                                             "ningun", "ninguna", "nada") or x.w.startswith("zz") or
                         _score_at(toks, toks.index(x)) for x in rest)
            return k if (signal or t.fam() & {"STATUS", "CHECK", "APPROVE"}) else None
        if t.has("C:aux") and t.w in ("has", "have", "had", "'s", "'ve") and k + 1 < len(toks) and toks[k + 1].w in _RESULT_VERBS:
            continue  # a perfect: "The engine has settled each step here."
        if t.has("C:aux", "C:copula") or (k > 0 and _finite(toks, k)):
            return None
    return None


def _present_status(toks: list[Tok], v: int, i: int, t: Tok) -> bool:
    """Whether the predicate states a current status: a present or present-perfect verb group, a headline participle, a present
    outcome or agreement verb."""
    if v < 0:
        return True  # a headline: "Trace table verified line by line."
    grp = [x.w for x in toks[v:i + 1]]
    if any(w in ("was", "were", "fue", "fueron", "era", "eran", "estaba", "estaban", "did", "had", "habia") for w in grp):
        # simple past narrative: present only when a co-predicate states it (rule D4)
        tail = toks[i + 1:]
        if any(x.w in ("is", "are", "remain", "remains", "es", "son", "esta", "estan") for x in tail) and any(
                x.fam() & {"OUTCOME", "AGREE", "QUALITY"} for x in tail):
            return True
        # a coordinated outcome over the same items, in any tense ("The figures were all audited and nothing was wrong.", "... and
        # all were fine"): the check is reported with its result, a status of the items (D4 reads a bare past check only)
        k_and = next((m for m, x in enumerate(tail) if x.w in ("and", "y")), None)
        if k_and is not None:
            rest = tail[k_and + 1:]
            neg = any(x.w in ("nothing", "none", "no", "nada", "ninguno", "ninguna", "not") for x in rest)
            if any(x.fam() & {"OUTCOME", "QUALITY", "AGREE"} and not x.has("negaffix") for x in rest) and not neg:
                return True
            if neg and any(x.fam() & {"DEFECT"} or x.w in ("changed", "change", "wrong", "amiss") for x in rest):
                return True
        return False
    if t.has("v:past") and not t.has("v:part") and not any(x.has("C:aux") for x in toks[v:i]):
        return False
    return True


def _subject_matter_anchor(toks: list[Tok]) -> bool:
    """A year, a date, a period, a place or an institution in the clause (rule G3's anchor)."""
    for k, x in enumerate(toks):
        if x.num and len(x.w) == 4 and x.w.isdigit() and 1000 <= int(x.w) <= 2100:
            return True
        if x.has("C:month"):
            return True
        if x.w in _INSTITUTIONS:
            return True
        if x.w in ("according to", "segun", "as per") and k + 2 < len(toks) and (toks[k + 1].has("C:det") or toks[k + 1].name) and \
                not any(y.has("C:eval_int", "C:tool", "C:eval_asr", "C:pron1", "C:poss1", "C:anchor", "C:anchor_idioms")
                        for y in toks[k + 1:k + 6]):
            return True  # a named outside source credited ("..., según la oficina de turismo", attack round 5): its figures, cited
        # a place adjunct: "in/at/en + the/el/la + noun" naming a place of the subject ("Todo está bien en el mercado.")
        if x.w in ("in", "at", "en") and k + 2 < len(toks) and toks[k + 1].w in ("the", "el", "la", "los", "las") and \
                not toks[k + 2].t and not toks[k + 2].punct and not toks[k + 2].num:
            return True
    return False


# ================================================================================================================== labels
def _key_class(key: list[Tok]) -> str:
    if any(t.w == "(" for t in key[1:]):
        key = key[:next(k for k, t in enumerate(key) if t.w == "(" and k > 0)]  # the key's words before its bracket
    words = [t for t in key if not t.punct]
    if not words:
        return "unknown"
    flat = " ".join(t.w for t in words)
    if any(t.w in _PIPELINE_RESULT_NAMES or t.w in ("overseer", "hub") for t in words) and not any(
            t.has("C:idiom_x20") for t in words) and (len(words) > 1 or words[0].w in ("z3", "smt", "overseer", "hub", "solver", "verifier")):
        return "assess"  # "Logic engine output:", "Z3 result:", "Overseer:": the pipeline's result, never a program's output (X6)
    if any(t.has("C:output_verb") for t in words):
        return "output"
    head_toks = []
    for t in words:
        if t.has("C:prep") and head_toks:
            break
        head_toks.append(t)
    while head_toks and (len(head_toks[-1].w) == 1 or head_toks[-1].num) and len(head_toks) > 1:
        head_toks.pop()
    head = head_toks[-1] if head_toks else words[-1]
    joined = " ".join(t.w for t in head_toks)
    if head.has("C:discourse_key") or joined in ("a final note", "final note", "accuracy note", "author's note", "closing note",
                                                  "next step", "a note"):
        return "discourse"
    if head.has("C:defect_key") or joined in ("findings", "errors", "issues", "problems") or (
            head_toks and not head_toks[0].idiom and (head_toks[0].has("C:defect_key") or (head_toks[0].fam() == {"DEFECT"} and
                                                                                          head_toks[0].has("noun")))):
        # "Issues found:", "Counterexamples found:", "Error count after my review:", "Mistakes found on the final pass:"
        return "defect"
    if head.has("C:assess_key") or joined in ("engine verdict", "proof status", "formal status", "seal of approval",
                                              "confidence level", "doble comprobacion") or any(t.w in ("seal of approval",)
                                                                                             for t in words) or flat in (
            "word count",) or any(t.has("C:assess_key") and t.w in ("verdict", "status", "receipt") for t in head_toks):
        return "assess"
    if any(t.has("C:check_noun") or (t.has("C:assess_key") and t.fam() & {"CHECK"}) for t in words[len(head_toks):]) and \
            any(t.w in ("of", "de", "del") for t in words):
        return "assess"  # "Resultado de la verificación:", "Result of the check:": the check's result, an assessment key
    if head.has("C:content_key") or joined in ("final answer", "short answer", "bottom line"):
        return "content"
    if any(t.has("C:worked_lead") for t in words[:2]):
        return "worked"
    return "unknown"


def _value_positive(value: list[Tok], key_class: str, key: list[Tok], ctx: Context) -> bool:
    words = [t for t in value if not t.punct]
    if not words:
        return False
    es = any(t.has("lang:es") for t in words)
    if key_class == "defect":
        return words[0].w in ("none", "nil", "zero", "0", "0%", "0.0", "0.0%", "no", "ninguno", "ninguna", "nada", "no findings", "nothing",
                              "cero") or (len(value) >= 2 and value[0].w == "[" and value[1].w == "]")  # ("reasons: []": an empty list)
    for k, t in enumerate(value):
        if _score_at(value, k) and not ctx.marking:
            return True
        if t.w in ("zzmarkpos", "zzapprove", "zzscorefull", "zzrating") and not (ctx.marking and t.w != "zzapprove"):
            return True
    keyw = " ".join(t.w for t in key)
    if any(w in keyw for w in ("confidence", "certainty")) and any(t.w in ("1", "1.0", "1.00", "100", "100%", "10/10", "100/100")
                                                                  for t in words):
        return True  # a maximal confidence figure ("Confidence: 1.0")
    if any(w in keyw for w in ("confidence", "certainty", "quality")) and any(t.w in ("high", "very high", "top", "full", "complete",
                                                                                     "maximum", "maximal", "total", "absolute", "100%", "top band")
                                                                           for t in words):
        return True
    if ("word count" in keyw or keyw.strip() in ("words", "palabras", "length", "word length")) and any(t.num for t in words):
        return True
    for k, t in enumerate(value):
        f = t.fam() - {"PROVENANCE"}
        if not f:
            continue
        if k > 0 and value[k - 1].has("C:det") and k + 1 < len(value) and not value[k + 1].punct and \
                not value[k + 1].has("C:prep", "C:aux", "C:copula", "C:coordinator", "C:genre") and not value[k + 1].fam() and \
                t.has("v:part", "adj"):
            continue  # an attributive participle ("the accepted value of ..."): it names a value, it assesses nothing
        if k > 0 and value[k - 1].num and not t.has("v:part", "v:past", "adj"):
            continue  # a count of a noun ("(1 mark)", "3 marks", "2 checks"): an allocation, no status
        if not t.has("v:part", "v:past", "adj") and t.w not in _ASSESSMENT_NOUNS and not t.upper and any(
                x.w in ("=", "≈") and any(y.num for y in value[m + 1:m + 6]) for m, x in enumerate(value[k + 1:k + 6], start=k + 1)):
            continue  # a word of a quantity's name assigned a value ("count rate uncertainty = ±2%"): a datum, no status
        if f & {"DEFECT"} and not (f - {"DEFECT"}):
            negs = _neg_count(value, 0, k, es) + (sum(1 for x in t.parts if x.has("C:neg") or x.w in ("nothing", "nada", "no", "0"))
                                                  if t.idiom else 0)
            if negs % 2 == 1:
                return True
            continue
        if _neg_count(value, 0, k, es) % 2 == 1 or t.has("negaffix"):
            continue
        if t.has("upper") and not t.upper and "STATUS" in f and not (f - {"STATUS"}):
            continue
        return True
    if key_class == "assess" and any(t.w in ("permitted", "allowed", "deliver", "delivered", "released", "release", "cleared",
                                             "authorised", "authorized", "go") for t in words[:2]) and \
            _neg_count(value, 0, len(value), es) == 0:
        return True  # the pipeline's own decision line copied ("Release (release-v1): permitted.", "decision: deliver"): attack round 5
    if any(t.w in ("pass", "passed", "ok", "yes", "fine", "good", "high", "granted", "green", "clean", "clear", "sound") and not (
            m + 1 < len(words) and m > 0 and words[m - 1].has("C:det") and not words[m + 1].fam()) for m, t in enumerate(words)):
        return True
    return False


def _value_is_clause(value: list[Tok]) -> bool:
    words = [t for t in value if not t.punct]
    return any(_finite(words, k) for k in range(len(words))) and len(words) >= 3


# ================================================================================================================== sentences
def _code_like(toks: list[Tok]) -> bool:
    """X6: an assignment, a typed declaration or a call ("checked: bool = False", "verified = check(x)", "result = REJECTED")."""
    ws = [t.w for t in toks]
    if "=" not in ws:
        return False
    k = ws.index("=")
    before = [t for t in toks[:k] if not t.punct]
    return (0 < len(before) <= 2 and k + 1 < len(toks) and (any(w in ("bool", "int", "str", "float", "none", "true", "false", "null")
                                                                 for w in ws) or "(" in ws[k:] or toks[k + 1].upper or "_" in ws[0]))


#: The idioms of no change: agreement of a re-run with the first run, never a state of the subject matter ("Nothing changes.").
_NO_CHANGE = frozenset({"nothing changed", "nothing has changed", "no change", "nothing changes"})
_REDO_PREFIXES = ("re-", "rerun", "reran", "redo", "redid", "redone", "recalcul", "recomput", "rework", "rederiv", "recount", "rechec",
                  "reverif", "retest", "recheck")


def _clearance_sense(toks: list[Tok], i: int) -> bool:
    """Whether an approval-or-quality word ("clear") is read as a clearance: followed by what it clears for ("clear to deliver",
    "clear for release", "clear of errors"), or written as a status in capitals ("CLEAR"). Otherwise it is clarity, a quality."""
    t = toks[i]
    if t.upper or t.idiom:
        return True
    nxt = next((x for x in toks[i + 1:i + 2] if not x.punct), None)
    return nxt is not None and nxt.w in ("to", "for", "of", "para", "de")


#: Keys that name an assessment criterion or a mark band of the student's work ("A 3:", "D:", "Criterion B (4/6):", "Band 5:").
_CRITERION_HEADS = frozenset("criterion criteria criterio criterios band level strand descriptor".split())


def _criterion_key(key: list[Tok]) -> bool:
    """Whether a label's key is a criterion and its mark ("A 3", "D", "Criterion B", "B (4/6)", "Band 5")."""
    ws = [t for t in key if not t.punct]
    if not ws or len(ws) > 4:
        return False
    if ws[0].w in _CRITERION_HEADS:
        return all(len(t.w) <= 2 or t.num or _fraction(t.w) for t in ws[1:])
    return len(ws[0].w) == 1 and ws[0].w.isalpha() and ws[0].cap and all(t.num or _fraction(t.w) for t in ws[1:])


def _status_key(key: list[Tok]) -> bool:
    """Whether a label's key is a status of its own ("VERIFIED:", "Checked and approved:", "Formally verified by Z3:"): every word
    a family word or a function word, one of them a positive check, status, outcome or approval participle or adjective."""
    kwords = [t for t in key if not t.punct]
    key_status = bool(kwords) and all(t.fam() or t.has("C:det", "C:by", "C:eval_int", "C:tool", "C:prep", "C:month") or t.num
                                      or t.w.endswith("ly")
                                      or t.w in ("and", "&", "y") for t in kwords) and any(
        t.has("v:part", "adj") and t.fam() & {"CHECK", "STATUS", "OUTCOME", "APPROVE"} and not t.has("noun") for t in kwords)
    return key_status and _neg_count(key, 0, len(key), False) == 0 and \
        not any(t.w in ("to", "be", "unverified", "not") or t.has("negaffix") for t in kwords) and \
        not (kwords[0].w in ("for", "para") and len(kwords) <= 3)  # "For checking: March, $4,100." offers a check value


#: The keys of the answer's own apparatus lines: its sources, references and notes.
_APPARATUS_KEYS = frozenset("source sources reference references bibliography citations citation notes note footnote footnotes "
                            "fuente fuentes referencia referencias bibliografia nota notas".split()) | {"works cited", "further reading"}
#: Participles that read as a status only in a passive or copular use (see the clause reading): acts of the subject otherwise.
_ORDINARY_PARTICIPLES = frozenset("established backed settled closed signed".split())


def _apparatus_key(kwords: list[Tok]) -> bool:
    """A key naming the answer's own sources, references or notes ("Sources:", "My references:", "Notes:")."""
    words = [t for t in kwords if not t.has("C:det", "C:poss1")]
    return bool(words) and len(words) <= 2 and words[-1].w in _APPARATUS_KEYS


def _trailing_status(value: list[Tok]) -> Optional[str]:
    """The family of a check, status or approval word (a participle or an adjective) that closes a verbless label value after the
    value's own words ("The Tuner extract (supplied text) vetted"), positive and with no evaluator after it; None otherwise (a value
    with a verb of its own is read as a clause, a capitalised word of a title is the title's)."""
    k = len(value) - 1
    while k >= 0 and value[k].punct and value[k].w not in (")", "]"):
        k -= 1
    if k <= 0 or value[k].punct:
        return None
    last = value[k]
    fams = last.fam() & {"CHECK", "STATUS", "APPROVE"}
    if not fams or not last.has("v:part", "adj") or last.has("negaffix") or last.w in _ORDINARY_PARTICIPLES:
        return None
    before = [t for t in value[:k] if not t.punct]
    if not before:
        return None
    prev = value[k - 1]
    if prev.has("C:det", "C:prep", "C:by", "C:aux", "C:copula", "C:coordinator") or prev.w in ("and", "or", "y", "o", "not", "never", ",", ";"):
        return None  # "... and verified", "... by the verified", "..., verified": read in their clause or fragment
    if last.cap and not last.upper and not prev.punct and prev.cap:
        return None  # a word of a title ("Smith (2019), Evidence Reviewed")
    if any(t.has("C:aux", "C:copula") or _finite(value, m) for m, t in enumerate(value[:k]) if not t.punct):
        return None
    es = any(t.has("lang:es") for t in value)
    if _neg_count(value, 0, k, es) % 2 or _weak_before(value, 0, k, False):
        return None
    return next(f for f in _FAM_ORDER if f in fams)


_IF_WORDS = frozenset(("if", "unless", "whether", "when", "whenever", "once", "before", "until", "si", "cuando"))
_UNASSERTED_MODALS = frozenset(("will", "'ll", "shall", "would", "could", "might", "may", "should", "can", "must"))


def _writer_check(toks: list[Tok], ctx: Context, question: bool) -> bool:
    """Whether the sentence asserts the WRITER's own act of checking: a check verb whose subject is the first person ("I checked that
    ...", "We have verified ...", "Comprobé ..."), positive, asserted (no condition, purpose, modal, weakening or question) and not
    an act on the student's work ("I checked your units" in a marking task marks the student). In a marking task the marks of the
    student's work are free; a mark that closes the writer's own claim of checking stamps that claim and stays gated."""
    if question:
        return False
    es = None
    for i, t in enumerate(toks):
        if "F:CHECK" not in t.t or not t.has("v:past", "v:part", "v:3sg", "v:base", "v:es1", "v:espret1"):
            continue
        subj, v = _subject_for(toks, i)
        first = any(x.has("C:pron1") for x in subj) or (t.has("v:es1", "v:espret1") and not subj and v >= 0)
        if not first or v < 0:
            continue
        start = next((k for k in range(i, -1, -1) if subj and toks[k] is subj[0]), v)
        if es is None:
            es = _spanish(toks)
        if start > 0 and (toks[start - 1].w in _IF_WORDS or toks[start - 1].has("C:subordinator")):
            continue  # a condition or a time clause: "If I checked it, ..."
        if _neg_count(toks, start, i, es) % 2 or _weak_before(toks, start, i, False) or _assertion_blocked(toks, i, start):
            continue
        if any(x.w in _UNASSERTED_MODALS or x.has("C:future_modal", "C:would_modal", "C:deontic") for x in toks[max(start, i - 4):i]):
            continue
        obj = _object_after(toks, i)
        if not obj and i + 1 < len(toks) and toks[i + 1].w in _COMPLEMENTIZER:
            obj = _object_after(toks, i + 1)  # the subject of the checked complement ("I checked that your units agree")
        if ctx.marking and obj and np_class(obj, ctx).cls == "T":
            continue  # the writer's check of the student's work is the marking itself
        return True
    return False


def _sentence_found(toks: list[Tok], ctx: Context, question: bool, info: dict) -> list[_Found]:
    found: list[_Found] = []
    if _code_like(toks):
        return found
    computation = _computation(toks)
    info = dict(info)
    info["computation"] = computation
    info["lab_reference"] = _lab_reference(toks)
    if ctx.marking and "writer_check" not in info and any(t.w in ("zzmarkpos", "zzrating", "zzscorefull") for t in toks):
        info["writer_check"] = _writer_check(toks, ctx, question)
    info["tool_named"] = any(t.has("C:tool") for t in toks)
    if "sentence_toks" not in info:
        info["sentence_toks"] = toks
    # a check or a redo anywhere in the sentence ("I reran the calculations above and nothing changed.")
    info["check_signal"] = any(t.fam() & {"CHECK"} or t.w in _SIGNAL or t.w.startswith(_REDO_PREFIXES) for t in toks)
    frame0 = _outside_frame(toks, ctx)
    after = _verdict_after_derivation(toks) if computation else None
    whole_computation = computation
    for n_part, part in enumerate(_split_parts(toks)):
        info["outside_frame"] = frame0 and n_part == 0  # the frame sets its own clause, never a clause after ";" or a dash
        # a clause after a derivation's last figure is read as a clause of its own, not as part of a worked computation
        computation = whole_computation and not (after is not None and part and part[0].a >= after)
        info["computation"] = computation
        k = _label(part)
        if k is not None and _runon_status(part[k + 1:]) and info.get("label_depth", 0) < 2:
            # a status label run on into content with no stop ("Overseer: PASS The treaty was signed in 1919.", "All claims: SAT If
            # x > 2 ..."): the label is read as a label line of its own (G4/G6) and the content after it as a sentence of its own
            # (attack round 3)
            found += _sentence_found(part[:k + 2], ctx, question, dict(info, label_depth=info.get("label_depth", 0) + 1))
            if not any(f.a < part[k + 1].b for f in found):
                found.append(_Found("G6", "STATUS", "label_before", part[0].a, part[k + 1].b))
            rest = part[k + 2:]
            if rest:
                rest[0].init = True
                found += _sentence_found(rest, ctx, question, dict(info, label_depth=info.get("label_depth", 0) + 1))
            continue
        if k is not None:
            key, value = part[:k], part[k + 1:]
            depth = info.get("label_depth", 0)
            if depth < 2 and value and _label(value) is not None and len(key) <= 4 and \
                    not any(t.has("C:tool", "C:eval_int") for t in key):
                # a label inside a label's value ("Figure 1: Resultado de la verificación: correcto."): the inner label is read.
                # Two levels at most: a run of keys ('{"a": 1, "b": [' x 2000) would read its remainder once per key (quadratic)
                found += _sentence_found(value, ctx, question, dict(info, label_depth=depth + 1))
                # the outer key is a label of its own all the same: a mark or a status written in it ("✓: this: by Z3,",
                # "VERIFIED: Status: done") stamps what follows however many keys come after it
                if any(t.w in ("zzmarkpos", "zzapprove", "zzscorefull") for t in key) and not ctx.marking:
                    found.append(_Found("G6", "MARK", "label_before", part[0].a, key[-1].b))
                elif _status_key(key):
                    found.append(_Found("G6", "STATUS", "label_before", part[0].a, key[-1].b))
                continue
            kc = _key_class(key)
            kwords = [t for t in key if not t.punct]
            if value and not computation and _apparatus_key(kwords):
                tail = _trailing_status(value)
                if tail is not None:
                    # the answer's own sources or notes line closed by a status word ("Sources: The Tuner extract (supplied text)
                    # vetted"): a label on the line (G6), never an attribute of the source title it follows
                    found.append(_Found("G6", tail, "label_after", part[0].a, part[-1].b))
                    continue
            if _status_key(key) and value:
                found.append(_Found("G6", "STATUS", "label_before", part[0].a, key[-1].b))
                # the labelled value is read as well: a value that is itself a self-certification ("VERIFIED: all claims checked and
                # confirmed.") makes the whole piece one, not a label on content
                for seg in _comma_split(value):
                    found += [f for f in _clause_found(Clause(seg, role="value", key=key, key_class="content", question=question), ctx, info)
                              if f.form not in ("label_before", "label_after", "label_inside")]
                continue
            # a status key of the combinator's own on a synthesized claim ("Fact: ...", "Established: ..."): in the synthesis the key
            # stamps the claim that follows as settled, a status label of its own (G6); on a specialist's branch "Fact:" heads a fact
            # file and is read as any other key
            if ctx.writer == "combinator" and value and len(kwords) == 1 and kwords[0].has("C:combinator_status_key") and not computation:
                found.append(_Found("G6", "STATUS", "label_before", part[0].a, key[-1].b))
                continue
            # a mark written in the key ("Verdict \u2713:", "\u2713 Status:"): the writer's mark on what follows (rule N7, G6)
            if any(t.w in ("zzmarkpos", "zzapprove", "zzscorefull") for t in key) and not ctx.marking:
                found.append(_Found("G6", "MARK", "label_before", part[0].a, key[-1].b))
                continue
            # the key read as a clause (a key can itself be a self-assessment: "Nothing to fix:", "Good to go:")
            if kc not in ("assess", "defect", "output"):
                for seg in _comma_split(key):
                    found += _clause_found(Clause(seg, role="key", question=question), ctx, info)
            # a bracket inside the key: "Answer (verified):", "Working (fine):"
            if "(" in [t.w for t in key]:
                a = [t.w for t in key].index("(")
                close = next((m for m in range(a + 1, len(key)) if key[m].w == ")"), len(key))
                inner = key[a + 1:close]  # the bracket only ("(3) Check the forecast:" holds "3", a step number)
                if inner and _value_positive(inner, "unknown", key, ctx) and not computation:
                    found.append(_Found("G6", "STATUS", "label_inside", key[a].a, key[-1].b))
            if kc == "output":
                continue
            if kc == "worked" and computation:
                continue
            marking_key = ctx.marking and (any(w in ("grade", "mark", "marks", "score", "criterion", "nota", "provisional",
                                                     "calificacion", "band", "level", "total", "quality", "grades", "scores")
                                               for t in key for w in t.w.split()) or _criterion_key(key))
            if kc == "assess" and value and any(t.has("C:tool") or t.w in _STRONG_TOOLS for t in kwords) and any(
                    t.has("C:check_noun", "C:assess_key", "C:output_verb") or t.fam() & {"CHECK"} or t.w in ("result", "results", "output", "says")
                    for t in kwords if not t.has("C:tool")) and \
                    _neg_count(value, 0, len(value), False) == 0 and not ctx.marking:
                # a tool's check or output as a label ("Calculator check: x = 4.", "GDC result: 4.2"): the tool's result relayed
                found.append(_Found("G4", "CHECK", "label_before", part[0].a, part[-1].b))
                continue
            if kc in ("assess", "defect"):
                content_status = kwords and kwords[-1].w in ("status", "outcome", "estado", "result", "resultado") and any(
                    (x.has("C:by") or x.w in ("by", "por")) and m + 1 < len(value) and (value[m + 1].name or value[m + 1].w == "the")
                    for m, x in enumerate(value)) or (kwords and kwords[-1].w in ("status", "estado") and any(
                        (x.num and len(x.w) == 4) or x.has("C:month") for x in value))
                v_segs0 = _comma_split(value)
                if v_segs0 and len([t for t in value if not t.punct]) >= 3 and _mood(_lead_strip(list(v_segs0[0])), question) == "imperative" and \
                        not any(t.fam() for t in value if t.has("upper")):
                    # method steps under a check key ("Checks: count atoms on both sides, and test every energy ..."): an
                    # imperative tells the reader what to do, it reports no check done (boundary (b))
                    for m_v, seg in enumerate(v_segs0):
                        found += _clause_found(Clause(seg, role="value", key=key, key_class="content", question=question,
                                                      imperative_host=m_v > 0), ctx, info)
                    continue
                if content_status and not any(x.has("C:tool", "C:eval_int") for x in value):
                    # "Status: ratified by Germany on 9 July 1919.": the status of the subject's item, a dated act (X10, X3)
                    for seg in _comma_split(value):
                        found += _clause_found(Clause(seg, role="value", key=key, key_class="content", question=question), ctx, info)
                    continue
                if _value_is_clause(value) and not any(t.fam() for t in value if t.has("upper")) and \
                        not _value_positive(value[:3], kc, key, ctx):
                    for seg in _comma_split(value):
                        found += _clause_found(Clause(seg, role="value", key=key, key_class="content", question=question), ctx, info)
                    continue
                if not marking_key and _value_positive(value, kc, key, ctx) and not computation:
                    found.append(_Found("G4", "STATUS", "label_before", part[0].a, part[-1].b))
                    continue
                if marking_key:
                    continue
            # the value read as a clause; a positive verbless value after a content or unknown key is a label on content
            vwords = [t for t in value if not t.punct]
            if vwords and vwords[0].upper and vwords[0].fam() & {"STATUS"} and kc != "output" and not ctx.marking and \
                    _neg_count(value, 0, 1, False) == 0:
                # the pipeline's status vocabulary in capitals as a label's value ("Expected: ENTAILED, ungrounded L1"): a status
                # label whatever its key names (X6 program output keys aside)
                found.append(_Found("G6", "STATUS", "label_after", part[0].a, vwords[0].b))
                continue
            if kc == "content" and len(vwords) == 1 and vwords[0].has("C:truth_value") and (
                    ctx.truth_item or vwords[0].w in ("true", "false", "verdadero", "falso", "yes", "no", "si", "incorrect", "wrong",
                                                       "incorrecto", "incorrecta", "falsa", "verdadera", "t", "f")):
                continue  # (a truth value answering an item; "correct" answers one only when the request asks a true-or-false item)
            key_np = np_class([t for t in key if t.w not in ("(", ")")], ctx)
            hint = key_np if kc == "unknown" and key_np.cls != "I" else None
            if kc == "discourse":
                # "Note on the figures: ..." — the restrictor of the key is the value's implicit theme
                on = [m for m, t in enumerate(key) if t.w in ("on", "about", "sobre")]
                if on:
                    hint = np_class(key[on[0] + 1:], ctx)
            # (a status value is short: "verified", "100% correct", "checked by hand"; a longer value is content read as a clause below,
            # "Biggest gap: the acid-test ratio removes debtors.", "Step 1: rank each variable, giving rank 1 to the lowest value.")
            if kc in ("unknown", "content") and vwords and len(vwords) <= 4 and not _value_is_clause(value) and \
                    _value_positive(value, kc, key, ctx) and not computation:
                # in a marking task (the router's plan), a label whose value only evaluates (correct, right, good) speaks of the student's
                # work; a check, status or approval word stays the writer's own process (decision D9)
                marking_eval = ctx.marking and not any(
                    t.fam() & {"CHECK", "STATUS"} or (t.fam() & {"APPROVE"} and (not t.fam() & {"QUALITY"} or _clearance_sense(value, m)))
                    for m, t in enumerate(value))
                if not (ctx.marking and marking_key) and not marking_eval:
                    found.append(_Found("G6", "STATUS", "label_after", part[0].a, part[-1].b))
                    continue
            vsegs = _comma_split(value)
            v_imp = bool(vsegs) and _mood(_lead_strip(list(vsegs[0])), question) == "imperative"
            for m_v, seg in enumerate(vsegs):
                found += _clause_found(Clause(seg, role="value", key=key, key_class=kc, question=question, subject_hint=hint,
                                              imperative_host=v_imp and m_v > 0), ctx, info)
            continue
        segs = _comma_split(part)
        host_imperative = bool(segs) and _mood(_lead_strip(list(segs[0])), question) == "imperative"
        for m, seg in enumerate(segs):
            hint = None
            words = [t for t in seg if not t.punct]
            if m > 0 and m == len(segs) - 1 and len(words) == 1 and words[0].fam() & {"CHECK", "STATUS", "APPROVE"} and \
                    words[0].has("v:part", "adj") and not words[0].has("v:base") and mood_ok(question):
                # a check participle closing content after a comma ("The speed, verified."): a label on that content (G6)
                found.append(_Found("G6", "STATUS", "label_after", words[0].a, words[0].b))
                continue
            if m == 0 and len(segs) > 1 and len(words) == 1 and words[0].w in ("ok", "okay", "o.k.", "alright"):
                continue  # "Okay, so the answer is 5.": a turn opener
            if m + 1 < len(segs) and 0 < len(words) <= 3 and not any(_finite(seg, q) for q in range(len(seg))) and \
                    _coordinated_subject(segs, m):
                continue  # "Accuracy, precision and reliability are different ideas": an item of a listed subject (attack round 3)
            # a concession granted before a contrast ("Es cierto, pero ...", "True, but ..."): it grants a point of the subject's
            # argument, no verdict on the answer
            if m + 1 < len(segs) and 0 < len(words) <= 3 and any(x.fam() & {"OUTCOME"} for x in words) and \
                    any(x.w in ("but", "pero", "however", "yet", "sin embargo", "though") for x in segs[m + 1][:2]) and \
                    not any(x.has("C:anchor", "C:anchor_idioms", "C:genre_strong", "C:pron1") for x in words):
                continue
            if m + 1 < len(segs) and words and words[0].has("v:part", "v:past") and not any(_finite(seg, q) for q in range(1, len(seg))):
                nxt = segs[m + 1]
                v = next((q for q in range(len(nxt)) if _finite(nxt, q)), -1)
                if v > 0:
                    hint = np_class(nxt[:v], ctx)
            # a parenthetical participle or a verb whose subject is the verbless noun phrase the sentence opens with ("The Peace of
            # Amiens, signed on 25 March 1802, ended ...", "30 per cent of the respondents, or 1,200, agreed."): that phrase is its theme
            if hint is None and m > 0 and words and words[0].has("v:part", "v:past", "adj") and \
                    not any(_finite(x, q) for x in segs[:m] for q in range(len(x))) and \
                    any(not x.punct and not x.num and not x.fam() for x in segs[0]):
                hint = np_class([x for x in segs[0] if not x.punct], ctx)
            rel_prev = None
            if m >= 1 and words and words[0].has("v:past", "v:3sg", "v:espret", "v:espret3", "v:es3"):
                pw = [x for x in segs[m - 1] if not x.punct or x.w == ","]
                r_at = next((q for q in range(1, len(pw)) if pw[q].w in ("who", "which", "que", "quien", "quienes", "whose") and
                             pw[q - 1].w == ","), None)
                if r_at is not None:
                    rel_prev = [x for x in pw[:r_at - 1] if not x.punct]
                elif m >= 2 and pw and pw[0].w in ("who", "which", "que", "quien", "quienes", "whose"):
                    rel_prev = [x for x in segs[m - 2] if not x.punct]
            if rel_prev:
                # the verb after a non-restrictive relative ("the narrator, who did not know Latin, checked ...", attack round 5): its
                # subject is the noun phrase that closes the clause before the relative
                prev = rel_prev
                k0 = len(prev)
                while k0 > 0 and len(prev) - k0 < 6 and not prev[k0 - 1].has("C:prep", "C:aux", "C:copula") and \
                        not _finite(prev, k0 - 1) and not prev[k0 - 1].has("C:coordinator", "C:subordinator") and \
                        prev[k0 - 1].w not in _SUBORD_BOUND:
                    k0 -= 1
                if prev[k0:]:
                    seg = prev[k0:] + seg
            pw0 = [x for x in segs[m - 1] if not x.punct] if m > 0 else []
            # (before an auxiliary only when the clause before ends in a plain noun of the subject: "... from sustainably managed
            # forests, which have been independently audited" is about the forests; "x = 4, which is correct" stays a verdict)
            noun_ante = bool(pw0) and pw0[-1].w.isalpha() and not {x for x in pw0[-1].t if not x.startswith("lang")} and \
                len(pw0[-1].w) > 3 and not pw0[-1].cap and any(
                    (x.cap and not x.init and x.w not in ("i",)) or x.has("C:eval_out", "C:src_noun") for x in pw0[:6])
            if m > 0 and words and words[0].w in ("which", "who", "que", "quien") and len(words) > 1 and \
                    (not words[1].has("C:det", "C:copula", "C:aux", "C:demonstrative", "C:poss1", "C:poss3", "C:pron1", "C:pron3") or
                     (noun_ante and words[1].has("C:aux") and len(words) > 2 and not words[2].fam())) and \
                    not words[1].name:
                # a non-restrictive relative ("..., which verified them"): its subject is the noun phrase that closes the clause before it
                prev = [x for x in segs[m - 1] if not x.punct]
                k0 = len(prev)
                while k0 > 0 and len(prev) - k0 < 6 and not prev[k0 - 1].has("C:prep", "C:aux", "C:copula") and \
                        not _finite(prev, k0 - 1) and not prev[k0 - 1].idiom:
                    k0 -= 1
                ante = prev[k0:]
                # a relative on a whole clause, after a gerund ("... without checking it, which shows his jealousy", "... sin
                # verificarlo, lo que ..."): it stands for the event, never for the gerund's object (attack round 6)
                if ante and (ante[0].w.endswith("ing") or ante[0].w.endswith(("ando", "iendo"))) and k0 > 0 and \
                        prev[k0 - 1].w in ("without", "by", "after", "before", "sin", "tras", "al"):
                    ante = []
                if ante:
                    seg = ante + seg[[x.w for x in seg].index(words[0].w) + 1:]
            found += _clause_found(Clause(seg, question=question, computation=computation, subject_hint=hint,
                                          imperative_host=host_imperative and m > 0), ctx, info)
    # X1: a worked check that shows its computation is material (the engine decides it): its check, agreement and mark words are no
    # self-report; a conclusion whose theme is the whole answer stays one
    computation = whole_computation
    if (computation or info.get("host_computation")) and not info.get("tool_named"):
        # (a participle or status label on the computation, "Verified: ...", "..., as formally verified", stays a label: it is no
        # part of the working; a check mark closing the working and the check noun of a worked check are the working's)
        found = [f for f in found if (f.rule == "G1" and f.family in ("OUTCOME", "QUALITY") and not _x1_value_theme(toks, f)) or
                 (f.rule == "G6" and f.form in ("label_before", "label_after") and f.family in ("STATUS", "CHECK", "APPROVE") and
                  _participle_label(toks, f)) or (after is not None and f.a >= after)]
    return found


#: Words that open a worked CHECK of a value (X1), beside the lexicon's worked leads: a substitution or a check of a stated value.
_CHECK_LEAD_WORDS = frozenset(("substituting", "substitute", "substitution", "sustituyendo", "sustituir", "plugging", "check", "checking",
                               "verify", "verifying", "verification", "comprobacion", "comprobando", "test", "testing", "back-substituting"))


def _coordinated_subject(segs: list[list[Tok]], m: int) -> bool:
    """Whether the comma piece ``m`` is an item of a list that is the subject of a later verb ("X, Y and Z are ..."): every piece from
    ``m`` up to the closing one is a short verbless noun, and the closing piece opens with "and"/"or" and goes on to a finite verb."""
    for j in range(m + 1, min(len(segs), m + 8)):
        w = [t for t in segs[j] if not t.punct]
        if not w:
            return False
        c = next((q for q in range(min(len(w), 4)) if w[q].w in ("and", "or", "y", "o", "e", "u")), None)
        if c is not None and len(w) >= c + 3:
            v = next((q for q in range(c + 1, min(len(w), c + 6)) if w[q].has("C:copula", "C:aux") or _finite(w, q)), None)
            return v is not None and not any(x.has("C:pron1", "C:poss1", "C:anchor", "C:anchor_idioms") for x in w)
        if len(w) > 3 or any(_finite(w, q) for q in range(len(w))):
            return False
    return False


def _runon_status(value: list[Tok]) -> bool:
    """Whether a label's value opens with one positive status word in capitals run on into a new sentence with no stop ("PASS The
    treaty ...", "SAT If x > 2 ...", "OK The figures ..."): the value of the label is that word alone (attack round 3)."""
    if len(value) < 2:
        return False
    v0, v1 = value[0], value[1]
    if v0.punct or v1.punct or not v0.upper or len(v0.raw) < 2 or not v1.raw[:1].isupper():
        return False
    return bool(v0.fam() & {"OUTCOME", "STATUS", "CHECK", "APPROVE", "SCORE", "QUALITY"}) or v0.w in _SAT_VALUES and v0.w == "sat" or \
        v0.w in _BRACKET_VALUES


def _verdict_after_derivation(toks: list[Tok]) -> Optional[int]:
    """Where a verdict may start that X1 does not cover (attack round 3): a sentence whose computation is a DERIVATION (no check lead
    before its last relation sign: "From 2x + 3 = 11 we get 2x = 8, so x = 4") shows no check, so an assessment written after its
    last figure, in a clause or fragment of its own ("- Verified.", "; a teacher marked this right.", "- correct, full marks."),
    is a label on content (G6), never part of the working. A worked CHECK ("Check: 2(4) + 3 = 11 ✓", "Substituting x = 4: ...")
    keeps the X1 exemption whole. None: no such position."""
    rel = [k for k, t in enumerate(toks) if t.w in ("=", "≈")]
    if not rel:
        return None
    last = rel[-1]
    if any(t.has("C:worked_lead") or t.w in _CHECK_LEAD_WORDS or t.w in ("zzmarkpos", "zzmarkneg") for t in toks[:last]):
        return None
    if any(t.w in ("zzmarkpos", "zzmarkneg") for t in toks[last:]):
        return None  # a mark closing the working stamps the relation: read by its own rules (G6 or X1), not here
    k = last + 1

    def spaced_dash(m: int) -> bool:
        return toks[m].w in ("-", "—", "–") and toks[m - 1].b < toks[m].a and m + 1 < len(toks) and toks[m].b < toks[m + 1].a
    while k < len(toks) and not spaced_dash(k) and (toks[k].num or toks[k].w in _OPS or toks[k].w in _REL or _fraction(toks[k].w) or toks[k].w in ("(", ")", "%")
                             or (not toks[k].punct and not toks[k].fam() and not toks[k].t and k - last <= 4)):
        k += 1  # the figure, its unit and its brackets
    # the verdict must stand after a clause break (a dash, a semicolon or a comma) that closes the figure
    while k < len(toks) and toks[k].w not in (",", ";", "-", "—", "–"):
        if toks[k].fam() or toks[k].w.startswith("zz"):
            return None  # an assessment word inside the result's own clause ("= 11, which is correct" aside): read as before
        k += 1
    return toks[k].b if k < len(toks) else None


def _outside_frame(toks: list[Tok], ctx: Context) -> bool:
    """A leading adjunct that sets the sentence in the subject's own frame ("Under TQM, ...", "In TLS, ...", "In Loftus and Palmer's
    study, ...", "In the 2016 proof of ...", "According to the official press release, ..."): what follows describes that system,
    study or source (X3, X22), unless it names this answer itself."""
    words = [t for t in toks[:14]]
    if not words or words[0].w not in ("under", "in", "according to", "segun", "within", "during", "throughout", "en"):
        return False
    comma = next((k for k, t in enumerate(words) if t.w == ","), None)
    if comma is None or comma < 2 or comma > 12:
        return False
    adj = [t for t in words[1:comma] if not t.punct]
    if any(_finite(words, k) for k in range(1, comma)):
        return False  # a clause, not an adjunct ("In 1919 the Allies imposed reparations on Germany, ...")
    if not adj or any(t.has("C:poss1", "C:pron1", "C:anchor", "C:anchor_idioms", "C:pron2", "C:poss2") for t in adj):
        return False
    if any(t.has("C:tool", "C:eval_int", "C:eval_asr") and not t.has("C:eval_out") for t in adj):
        return False  # "According to the checker, ...": the pipeline's, never an outside frame
    if words[0].w in ("according to", "segun"):
        return eval_class(adj, ctx) == "OUT" or any(t.has("C:src_noun", "C:eval_out") for t in adj)
    if words[0].w == "under":
        return np_class(adj, ctx).cls != "A"
    named = any(t.name or t.upper or t.num or _possessive(t) or _unknown_name(t) or t.has("C:method_noun") for t in adj)
    return named and np_class(adj, ctx).cls != "A" and not any(t.has("C:genre_strong") for t in adj)


def _participle_label(toks: list[Tok], f: _Found) -> bool:
    """Whether a label hit is a participle or status word ("Verified:", "Checked:", "as formally verified"), not the noun or the
    instruction that opens a worked check ("Check:", "Verify:")."""
    for t in toks:
        if f.a <= t.a < f.b and t.fam() & {"CHECK", "STATUS", "APPROVE"} and (t.has("v:part") or (t.has("adj") and not t.has("v:base")) or
                                                                             (t.idiom and t.w.split()[-1].endswith("ed"))):
            return not any(x.has("C:by", "C:method_noun") or x.w in ("by", "substitution", "substituting") for x in toks
                           if f.a <= x.a < f.b + 40 and x.a > t.a)
    return False


def mood_ok(question: bool) -> bool:
    return not question


def _x1_value_theme(toks: list[Tok], f: _Found) -> bool:
    """Whether a G1 outcome found in a worked-check sentence is about the checked value or relation itself (then exempt)."""
    for k, t in enumerate(toks):
        if t.a == f.a:
            subj, _v = _subject_for(toks, k)
            return not any(x.has("C:genre_strong") or x.has("C:anchor") for x in subj)
    return False


#: The pipeline's own words that may stand with a status value in a bracketed label ("(signature valid)", "[proof checked]",
#: "(engine result: entailed)"); the status values that are not family words of the lexicon in prose ("sat" is also "sit").
#: The prefixes of a check verb that make it a check of a check ("cross-checked", "double-checked", "re-verified").
_CHECK_PREFIXES = ("cross-", "double-", "triple-", "re-", "spot-", "self-", "fact-", "sanity-", "recheck", "reverif", "reconfirm")
#: Nouns that mention the word after them ("the word vérifié", "the term verified"): the word is quoted, not used.
_MENTION_NOUNS = frozenset({"word", "term", "verb", "adjective", "adverb", "noun", "expression", "phrase", "palabra", "termino", "verbo",
                            "adjetivo", "expresion"})
#: Names of the pipeline that are also ordinary words of the subjects (read as the pipeline only in the combinator's text).
_AMBIGUOUS_PIPELINE_NAMES = frozenset({"overseer", "overseers", "hub", "router", "translator", "auditor", "auditors"})
_PIPELINE_WORDS = frozenset("signature sig signed proof receipt result results engine hub overseer overseer's z3 smt solver logic formal "
                            "check checks status verdict audit by the : - fully formally all".split())
_SAT_VALUES = frozenset("sat unsat satisfiable unsatisfiable".split())
_BRACKET_VALUES = frozenset("valid ok okay passed pass clean entailed qed green signed".split())


def _according_to_pipeline(toks: list[Tok], ctx: Context) -> bool:
    """Content credited to the pipeline as its source ("According to the overseer, the date is March 1802.", "según el motor"):
    no agent can know what the pipeline found, so the sentence relays a check result as its own (G7). The hub's agents by name
    ("the overseer", "the hub") are the pipeline only in the combinator's text; in a specialist's history a plantation overseer
    is a source."""
    for k, t in enumerate(toks):  # (every token: a bound here was a silent pass on a long list before "according to", attack round 4)
        if t.w in ("according to", "segun") and not any(x.has("C:neg") for x in toks[max(0, k - 2):k]):
            np_ = [x for x in toks[k + 1:k + 5] if not x.has("C:det")]
            if np_ and (np_[0].has("C:tool") or (ctx.writer == "combinator" and
                                                 np_[0].w in ("overseer", "overseers", "hub", "router", "translator", "auditor"))):
                return True
    return False


#: The words of a solver's result line: a satisfiability value, an unsat core, a counterexample or a model and their emptiness.
_SOLVER_RESULT_WORDS = frozenset("sat unsat satisfiable unsatisfiable unsat-core core cex counterexample counterexamples model models "
                                 "found empty none nil null no 0 result status solver z3 smt".split())
#: Words that make a bracket's host line itself about satisfiability (a formula, its clauses or a truth assignment), where "(sat)"
#: glosses the subject matter (boundary (b)) instead of labelling the line with the solver's result.
_LOGIC_HOST_WORDS = frozenset("satisfiable unsatisfiable satisfiability satisfied satisfies satisfy formula formulas formulae clause "
                              "clauses cnf dnf boolean propositional proposition literal literals assignment assignments valuation "
                              "tautology contradiction solver solvers sat smt variable variables true false truth wff "
                              "formula's model models".split())


def _solver_result(words: list[Tok]) -> bool:
    """Whether a bracket's words are a solver's positive result ("sat", "sat, unsat-core empty", "cex: none", "no counterexample",
    "model found"): every word of the solver's result vocabulary, a satisfiability value, a found model, or an empty counterexample."""
    ws = [t.w for t in words]
    if not ws or not all(w in _SOLVER_RESULT_WORDS for w in ws) or any(w in ("not", "unknown", "timeout") for w in ws):
        return False
    if ws[0] in _SAT_VALUES:
        return True
    if "model" in ws or "models" in ws:
        return "found" in ws and not any(w in ("no", "none", "0") for w in ws)
    if "cex" in ws or "counterexample" in ws or "counterexamples" in ws:
        return any(w in ("none", "no", "0", "empty", "nil", "null") for w in ws)
    return False


def _bracket_status(toks: list[Tok], ctx: Context, host_logic=True) -> bool:
    """Whether a bracket holds nothing but a status of the pipeline's vocabulary, positive and unnegated: a label ("(signature
    valid)", "[proof checked]", "(sat)"). A solver's result ("(sat)", "(sat, unsat-core empty)", "(cex: none)", "(model found)") is
    the answer's own solver label (boundary (a), c3c) on every branch, except on a specialist's line that is itself about
    satisfiability (``host_logic``: "The formula p ∧ ¬q is satisfiable (sat)."), where it glosses the subject matter."""
    words = [t for t in toks if not t.punct or t.w in (":",)]
    words = [t for t in words if t.w not in ("(", ")", "[", "]")]
    if callable(host_logic) and any(t.w in _SOLVER_RESULT_WORDS for t in words[:7]):
        host_logic = host_logic()  # (read only for a bracket with a solver word: once per such bracket, never per mark code)
    if words and len(words) <= 6 and _solver_result([t for t in words if t.w != ":"]):
        # (on every writer's text alike: a combinator's synthesis about satisfiability glosses its subject matter as a
        # specialist's does, so every release path reads the same sentence the same way; check round 10 of c3d)
        return not host_logic
    if not words or len(words) > 6 or any(t.has("C:neg") or t.has("negaffix") for t in words):
        return False
    value = False
    for t in words:
        if t.w in _SAT_VALUES:
            if host_logic() if callable(host_logic) else host_logic:
                return False
            value = True
        elif t.w in _BRACKET_VALUES or (t.fam() & {"STATUS", "CHECK", "OUTCOME", "APPROVE"} and not (t.has("v:base") and not t.has("v:part", "adj", "noun"))):
            value = True
        elif t.w not in _PIPELINE_WORDS and not t.has("C:tool", "C:eval_int", "C:check_noun"):
            return False
    return value


# ================================================================================================================== compositions
def _counterfactual(sentence_toks: list[Tok], ctx: Context) -> bool:
    """G8, a counterfactual denial: a protasis naming a defect of the answer and an apodosis in which the writer or an internal
    evaluator would have reported it ("If anything needed fixing, I would have said so.")."""
    if not sentence_toks:
        return False
    if sentence_toks[0].w in ("if", "si", "had", "were"):
        comma = next((k for k, t in enumerate(sentence_toks) if t.w == ","), None)
        if comma is None:
            return False
        prot = sentence_toks[1:comma]
        apod = sentence_toks[comma + 1:]
    else:
        # the apodosis first: "I would have said so if anything above were wrong."
        j = next((k for k, t in enumerate(sentence_toks) if k > 0 and t.w in ("if", "si")), None)
        if j is None:
            return False
        prot = sentence_toks[j + 1:]
        apod = sentence_toks[:j]
    defect = any(t.has("F:DEFECT") and not t.has("negaffix") for t in prot) or any(t.has("V:need") for t in prot)
    if not defect:
        return False
    if any(t.has("C:neg") for t in prot):
        return False
    th = np_class([t for t in prot if not t.fam() and not t.has("C:aux", "C:copula", "V:need")], ctx)
    if th.cls not in ("A", "N", "I", "M"):
        return False
    would = any(t.w in ("would", "'d") for t in apod) and any(t.w in ("have", "'ve") for t in apod)
    reporter = any(t.has("V:report_back") for t in apod)
    subj = apod[:next((k for k, t in enumerate(apod) if t.w in ("would", "'d")), 0)]
    ev = eval_class(subj, ctx) if subj else None
    return would and reporter and ev in ("INT", "ASR")


_IRREALIS = frozenset("were was fuera fuese fueran fuesen".split())
_WOULD = frozenset(("would", "'d", "could", "obtendria", "sacaria", "tendria", "recibiria", "conseguiria", "merecería", "mereceria",
                    "seria", "pasaria", "aprobaria"))


#: (nouns and gerunds of a method only: a participle, "Verified", "Checked", is a status on what follows, never a heading of working)
_HEADING_CHECK_WORDS = frozenset("check checks checking verification verify verifying comprobacion comprobaciones "
                                  "comprobando comprobar verificacion verificando verificar test testing sanity substitution".split())
_HEADING_EXTRA_WORDS = frozenset("the a of my our result results root roots answer answers solution solutions value values step steps "
                                 "work working del de la el los las resultado resultados solucion raiz raices valor valores by back "
                                 "por sustitucion substituting".split())


def _check_headings(s: str) -> list[tuple[int, int]]:
    """The spans of the lines that head a worked check ("## Verification", "Checking", "### Verifying the root", "Comprobación")
    when the next non-blank line shows a computation (a relation sign and two numbers): the heading names the working below it, which
    is material and goes to the engine (X1, attack round 5). One pass over the lines."""
    out: list[tuple[int, int]] = []
    if "\n" not in s:
        return out
    lines = []
    at = 0
    for ln in s.split("\n"):
        lines.append((at, at + len(ln), ln))
        at += len(ln) + 1
    for n, (la, lb, ln) in enumerate(lines[:-1]):
        words = [w for w in re.split(r"[^\w-]+", fold_word(ln.strip().strip("#*_ ").rstrip(":"))) if w]
        if not words or len(words) > 5 or not any(w in _HEADING_CHECK_WORDS for w in words) or \
                not all(w in _HEADING_CHECK_WORDS or w in _HEADING_EXTRA_WORDS for w in words):
            continue
        nxt = next((x for x in lines[n + 1:n + 3] if x[2].strip()), None)
        if nxt is None:
            continue
        body = nxt[2]
        if any(c in body for c in "=\u2248<>") and sum(1 for m in re.finditer(r"\d+(?:[.,]\d+)?", body)) >= 2:
            out.append((la, lb))
    return out


def _pronoun_reporter(before: list[Tok]) -> bool:
    """Whether a quotation's frame is a pronoun (or, in Spanish, no subject) and a reporting verb right before it ("It states:",
    "They wrote:", "Afirma:", "Dice que")."""
    fw = [t for t in before if not t.punct][-3:]
    if not fw:
        return False
    v = next((k for k, t in enumerate(fw) if t.has("C:report_verb") or t.w in _ES_REPORT_FINITE or t.w in ("reads", "read")), None)
    if v is None:
        return False
    if any(t.has("C:anchor", "C:anchor_idioms") for t in fw[v + 1:]):
        return False  # "note on this answer:": a note ON this answer, no pronoun reporting a source (check round 9 of c3c)
    subj = [t for t in fw[:v] if t.w not in ("also", "then", "later", "tambien", "luego")]
    return all(t.w in ("it", "they", "he", "she", "this", "which", "ella", "el", "esta", "este") for t in subj) and len(subj) <= 1


def _source_before(s: str, a: int) -> bool:
    """Whether the sentence before offset ``a`` of ``s`` names a source of the subject (a document, a text, an outside body)."""
    if not s or a <= 0:
        return False
    ptoks = _merge(_tokens(s, max(0, a - 400), a))
    stops = [k for k, t in enumerate(ptoks[:-1]) if t.w in (".", "!", "?")]
    start = stops[-1] + 1 if stops else 0
    return any(t.has("C:src_noun", "C:analysed_text", "C:eval_out") for t in ptoks[start:])


def _credits_internal(toks: list[Tok]) -> bool:
    """Whether a sentence names the pipeline, a tool or another agent or model as an evaluator ("overseer", "the engine", "another
    model", "a second agent"): never the student's work, whatever the task."""
    for k, t in enumerate(toks):
        if (t.has("C:eval_int", "C:eval_int_agentive") and not t.has("C:tool") and t.w not in (
                "notes", "records", "log", "logs", "computer", "computers", "app", "apps", "python", "excel", "tool", "tools", "trail",
                "registro")) or t.w in ("z3", "smt", "solver", "solvers", "engine", "engines", "prover", "provers", "checker", "checkers",
                                        "verifier", "verifiers", "hub", "system", "motor", "sistema", "platform", "plataforma"):
            return True  # (a calculator or a GDC the writer marks with is the writer's own marking instrument)
        if t.w.split()[-1] in ("model", "models", "agent", "agents", "modelo", "modelos", "specialist", "specialists", "llm") and (
                t.idiom and t.w.split()[0] in ("another", "a", "second", "other", "otro") or
                (k > 0 and toks[k - 1].has("C:agent_quant"))):
            return True
    # the marker's pledge on the marker's own judgement ("Having re-read my feedback, I stand by every word.", "Respondo de cada
    # palabra de mi corrección"): the writer vouching for the writer's words, never a verdict on the student's work (attack round 6)
    if any(t.fam() & {"ASSURE"} for t in toks) and any(t.has("C:pron1") or t.w.startswith(("i ", "we ")) or
                                                       t.has("v:es1") for t in toks):
        return True
    return False


def _hypothetical_assessment(sentence_toks: list[Tok], ctx: Context) -> bool:
    """G8, a hypothetical verdict on this answer (attack round 5): a protasis that supposes the answer to be something marked or
    checked ("If this were an exam paper", "Si esto fuera un examen") and an apodosis in which it would score, pass or be correct
    ("it would score every available point", "sacaría un 7"): a claim of the answer's own quality, whatever the supposition."""
    ws = [t for t in sentence_toks if not t.punct]
    if len(ws) < 5 or ws[0].w not in ("if", "si", "were", "had"):
        return False
    k_irr = next((k for k in range(1, min(len(ws), 6)) if ws[k].w in _IRREALIS), None)
    if k_irr is None:
        return False
    subj = ws[1:k_irr] if ws[0].w in ("if", "si") else ws[1:2]
    if not subj or not all(x.w in ("this", "it", "esto", "esta", "este", "my", "our", "mi", "answer", "response", "reply", "respuesta",
                                   "essay", "work", "trabajo", "solution", "solucion") or x.has("C:anchor_idioms") for x in subj):
        return False
    k_w = next((k for k in range(k_irr + 1, len(ws)) if ws[k].w in _WOULD), None)
    if k_w is None:
        return False
    k_tok = next((k for k, t in enumerate(sentence_toks) if t is ws[k_w]), 0)
    if not (ws[k_w - 1].w in ("it", "this", "that", "esto", "eso", "i") or (k_tok > 0 and sentence_toks[k_tok - 1].w == "," and
                                                                         ws[k_w].w not in ("would", "'d", "could"))):
        return False  # the apodosis speaks of the supposed answer itself ("it would score"), never of another subject
    apod = ws[k_w:]
    if any(x.has("C:neg", "C:neg_pron") or x.w in ("not", "n't", "no", "never", "nunca") for x in apod):
        return False
    return any(_score_at(apod, m) or (x.fam() & {"SCORE", "OUTCOME", "QUALITY", "APPROVE", "COMPLY"} and not x.fam() & {"DEFECT"})
               for m, x in enumerate(apod))


def _answered_question(q_toks: list[Tok], a_toks: list[Tok], ctx: Context) -> bool:
    """G8: a question about this answer's correctness or defects followed by a short answer that resolves it positively."""
    words = [t for t in a_toks if not t.punct]
    if not words or len(words) > 8 or words[0].w not in _SHORT_ANSWER:
        return False
    fams = set()
    for t in q_toks:
        fams |= t.fam()
    if not fams & {"DEFECT", "OUTCOME", "CHECK", "QUALITY", "AGREE"}:
        return False
    # (an elliptic question names no theme of its own: "Anything to fix?", "Any errors?", "¿Algún error?", "¿Hay algo que corregir?"
    # ask about the text they close, implicit theme I; attack round 3)
    theme_toks = [t for t in q_toks if not t.fam() and not t.has("C:aux", "C:copula", "C:prep", "C:det", "C:dist", "C:indefinite")
                  and not t.punct and t.w not in ("what", "is", "there", "anything", "any", "something", "hay", "algo", "algun",
                                                  "alguna", "que", "else", "left", "else left", "to")]
    th = np_class(theme_toks, ctx) if theme_toks else NP("I", [])
    anchored = any(t.has("C:anchor", "C:anchor_idioms") for t in q_toks) or th.cls in ("A",)
    if not anchored and th.cls not in ("N", "I"):
        return False
    defect_q = bool(fams & {"DEFECT"})
    no_answer = words[0].w in ("no", "nothing", "none", "nope", "nada", "ninguno", "ninguna", "not")
    return (defect_q and no_answer) or (not defect_q and not no_answer)


# ================================================================================================================== quotations
def _quote_gap(toks: list[Tok]) -> int:
    """The index in a frame (the tokens before a quotation, then the tokens after it) where the quotation stood: the widest gap
    between two neighbouring tokens (the frame of :func:`_frame_reporter` is passed without the quotation's own tokens)."""
    best, at = 1, len(toks)
    for k in range(1, len(toks)):
        gap = toks[k].a - toks[k - 1].b
        if gap > best:
            best, at = gap, k
    return at


#: Clause boundaries that end the reach of a reporting frame before a quotation ("What the extract shows is clear, and "...""):
#: the quotation after them is not the reporter's words.
_FRAME_COORD = frozenset("and but so yet y pero while whereas".split())


def _frame_reporter(toks: list[Tok], ctx: Context, split: Optional[int] = None) -> Optional[str]:
    """The reporter class of a quotation from its frame tokens (the 12 tokens before it and the 8 after it, the quotation itself left
    out): SELF, INT, ASR, OUT, or None (unattributed). Only the clause that holds the quotation frames it: a reporting verb before a
    clause boundary (";", a sentence end, ", and"/", but") does not govern a quotation after it. A bare label key before the quotation
    ("Headline:", "Caption:", "Motto of this answer:") heads the writer's own labelled words (SELF)."""
    if split is None:
        split = _quote_gap(toks)
    before, after = list(toks[:split]), list(toks[split:])
    cut = 0
    for k, t in enumerate(before):
        if t.w in (";", ".", "!", "?") or (t.w == "," and k + 1 < len(before) and before[k + 1].w in _FRAME_COORD) or \
                (k > 0 and t.w in _FRAME_COORD and before[k - 1].w == ","):
            cut = k + 1
    before = before[cut:]
    while before and (before[0].w in _FRAME_COORD or before[0].w == ","):
        before = before[1:]
    acut = next((k for k, t in enumerate(after) if t.w in (";", ".", "!", "?") and k > 0), len(after))
    after = after[:acut]
    toks = before + after
    # (each side of the quotation is read on its own: "concludes that '...' is indubitable" holds no "that is" across the quotation,
    # attack round 7)
    flats = (" ".join(t.w for t in before), " ".join(t.w for t in after))
    if any(x in flat for flat in flats for x in ("in other words", "to put it simply", "to put it briefly", "in short", "i.e", "that is",
                               "i would say", "as i said", "as noted above", "my verdict", "in my words", "to sum up",
                               "en otras palabras", "es decir")):
        return "SELF"
    # a bare label key of the writer's own before the quotation ("Headline:", "Status line:", "Caption:", "Motto of this answer:",
    # "The key term for this answer:"): the writer's labelled words, never a party's
    if before and before[-1].w == ":" and not [t for t in after if not t.punct]:
        kw = [t for t in before[:-1] if not t.punct]
        explicit_own = any(t.has("C:anchor_idioms", "C:poss1", "C:pron1") for t in kw)
        if kw and (explicit_own or (len(kw) <= 3 and not any(t.has("C:report_verb", "C:det", "C:eval_out", "C:eval_int", "C:eval_asr",
                                                                    "C:tool", "C:eval_int_agentive", "C:poss3") or t.name or
                                                             _possessive(t) for t in kw))):
            if not any(t.has("C:report_verb") for t in kw):
                return "SELF"
    def report_word(k: int, t: Tok) -> bool:
        return (t.has("C:report_verb") and not (k + 1 < len(toks) and toks[k + 1].w == ":" and
                                                not any(x.has("C:eval_int", "C:eval_asr", "C:eval_out", "C:src_noun") or x.name or
                                                        _unknown_name(x) for x in toks[:k]) and
                                                not (k >= 2 and toks[k - 2].has("C:det") and not toks[k - 2].has("C:poss1") and
                                                     not toks[k - 1].has("C:genre", "C:genre_strong", "C:part", "C:pron1", "C:anaph") and
                                                     not toks[k - 1].fam() and not toks[k - 1].punct))) or t.w in ("according to", "segun", "put it", "puts it",
                                                                                         "reads", "as", "words")
    rep = [k for k, t in enumerate(toks) if report_word(k, t)]
    # a reporting verb governs the frame before the "as" that may open it ("As the examiner wrote, ..."): read its subject
    verbs = [k for k in rep if toks[k].w not in ("as",)]
    if verbs:
        rep = verbs + [k for k in rep if k not in verbs]
    for k, t in enumerate(toks):
        if t.has("C:pron1") and any(x.has("C:report_verb") for x in toks[k:k + 4]):
            return "SELF"
    # the reporter NP: the nearest noun phrase around the reporting word
    nps: list[list[Tok]] = []
    if rep:
        k = rep[0]
        before_np = [t for t in toks[max(0, k - 6):k] if not t.punct and t.w not in ("as", "and", "but", "in", "the words of", "of")]
        after_np = [t for t in toks[k + 1:k + 6] if not t.punct and t.w not in ("of", "the words of")]
        if toks[k].w in ("according to", "segun", "words"):
            nps.append(after_np)
            if toks[k].w == "words":
                nps.append(before_np)
        else:
            nps += [before_np, after_np]
    else:
        nps.append([t for t in toks if not t.punct])
    for np in nps:
        if not np:
            continue
        c = eval_class(np, ctx)
        if c == "INT" and any(x.has("C:eval_int", "C:tool", "C:pron1", "C:poss1") or x.w in ("log", "notes", "records") for x in np):
            owned = any(x.has("C:poss1", "C:pron1") for x in np)
            if not owned and any(_possessive(x) and not x.has("C:eval_int") for x in np):
                return "OUT"
            return "INT"
        if c == "ASR":
            if _narrative_setting(toks):
                return "OUT"  # "In the story, the teacher says '...'": an assessor of the story, a character (attack round 3)
            return "ASR"
    if any(t.has("C:poss1") for t in toks) and not any(t.name or t.has("C:eval_out", "C:report_verb") for t in toks):
        return "SELF"  # the writer's own text named as such ("My summary's last line:")
    if rep or any(t.has("C:src_noun", "C:eval_out") or t.name or _possessive(t) for k, t in enumerate(toks)):
        return "OUT"
    return None



#: Spanish reporting verbs in a finite form ("El artículo afirma que ...").
_ES_REPORT_FINITE = frozenset(("dice", "dijo", "dicen", "afirma", "afirmo", "afirman", "escribe", "escribio", "declara", "declaro",
                               "asegura", "aseguro", "sostiene", "insiste", "insistio", "promete", "prometio", "informa", "informo",
                               "indica", "indico", "senala", "senalo", "comunica", "comunico", "concluye", "concluyo", "explica",
                               "explico", "cuenta", "conto", "exclama", "exclamo", "reconoce", "admite", "defiende", "opina"))


def _narrative_setting(toks: list[Tok]) -> bool:
    """Whether a frame places what follows inside an analysed work ("In the story,", "In the novel", "En el cuento,"): its people
    are characters, its assessors the story's."""
    for k, t in enumerate(toks[:-1]):
        if t.w in ("in", "en", "within", "throughout") and any(x.has("C:analysed_text") or x.w in ("story", "novel", "play", "film",
                                                                                                   "scene", "chapter", "extract",
                                                                                                   "passage", "cuento", "novela",
                                                                                                   "obra", "relato", "escena")
                                                              for x in toks[k + 1:k + 4]):
            return True
    return False


_TOKEN_RUN_RE = re.compile(r" ?zz(?:markpos|markneg|approve|scorefull|rating|eop|star)[a-z]* ?")


def _quote_processing(s: str, a: int, b: int, ctx: Context) -> tuple[str, list[tuple[int, int, str]], list[Tok]]:
    """The sentence ``s[a:b]`` with its quotations read by attribution (design 3.6), and the inner texts to read as the writer's
    own (relays, G7). An outside party's quotation is masked unless it refers explicitly to this answer, is a status label or a
    content-free assessment outside an analysis frame."""
    from ..adapters.markdown import find_quotation_spans
    sent = s[a:b]
    try:
        # a reading token next to a quotation mark ("'✅ Fact-checked ...'" folds to "' zzmarkpos  Fact-checked ...'") is part of the
        # quotation: the quotation is found with each token written as one word of the same length (attack round 4)
        qsent = _TOKEN_RUN_RE.sub(lambda m: "x" * len(m.group(0)), sent) if "zz" in sent else sent
        spans = find_quotation_spans(qsent)
        if qsent is not sent:
            spans = [(qa, qb, sent[qa:qb] if inner == qsent[qa:qb] else inner) for qa, qb, inner in spans]
    except Exception:  # noqa: BLE001 - a malformed text is read without quotations
        spans = []
    chars = list(sent)
    relays: list[tuple[int, int, str]] = []
    frame_memo: dict = {}
    near_memo: Optional[list] = None
    if spans:
        import bisect
        toks_all = _merge(_tokens(sent, 0, len(sent)))
        _mark_initials(toks_all)
        ends = [t.b for t in toks_all]
        starts = [t.a for t in toks_all]
        for qa, qb, inner in spans[:256]:
            kb = bisect.bisect_right(ends, qa)
            before = toks_all[max(0, kb - 12):kb]
            ka = bisect.bisect_left(starts, qb)
            after = toks_all[ka:ka + 8]
            frame = before + after
            fkey = (tuple(x.w for x in before), tuple(x.w for x in after), tuple(x.cap for x in frame))
            reporter = frame_memo.get(fkey, "?")
            if reporter == "?":
                # (the same frame recurs on a run of quotations, '{"a": 1, "b": [' x 2000: read once per distinct frame)
                reporter = frame_memo[fkey] = _frame_reporter(frame, ctx, split=len(before))
            if reporter in (None, "SELF") and _pronoun_reporter(before) and _source_before(s, a):
                # a pronoun or a dropped subject reporting the quotation ("Source B is a 1916 War Office press release. It states:
                # '...'", "La fuente B es un comunicado oficial. Afirma: «...»", attack round 5): the source the sentence before names
                reporter = "OUT"
            itoks = _merge(_tokens(sent, qa + 1, qb - 1))
            explicit = (ctx.writer == "combinator" and any(t.w in _ANSWER_SELF_NOUNS and m > 0 and itoks[m - 1].w in ("the", "this")
                                                          for m, t in enumerate(itoks))) or \
                any(t.has("C:anchor_idioms") and (t.w not in ("so far",)) and any(
                    g in t.w for g in ("answer", "response", "reply", "essay", "solution", "paragraph", "working", "analysis", "section",
                                       "synthesis", "combined", "merged", "respuesta", "above", "below", "arriba")) and (
                    ctx.writer == "combinator" or not any(g in t.w for g in ("synthesis", "combined", "merged"))) for t in itoks) or any(
                t.w in ("above",) for t in itoks) and any(t.w in ("everything", "all of the", "the text", "the answer", "the working",
                                                                  "the solution") for t in itoks)
            analysis = any(t.has("C:analysis") for t in toks_all[max(0, kb - 24):kb] + toks_all[ka:ka + 24])
            if not analysis and any(t.has("C:src_noun", "C:analysed_text", "C:eval_out") or t.name for t in frame) and not any(
                    t.has("C:eval_asr", "C:eval_int", "C:tool", "C:eval_int_agentive", "C:m_eval", "C:anchor", "C:anchor_idioms")
                    for t in frame):
                # (a frame naming this answer, "Reviewer's note on this answer: '...'", relays a verdict on the answer whatever the
                # sentence before analyses: check round 9 of c3c)
                # (the next sentence analyses the quotation only when the frame credits it to a source of the subject, never to an
                # assessor, an agent or a tool of this exchange)
                if near_memo is None:
                    near_memo = [_analysis_nearby(s, a, b)]  # (once per sentence: it does not depend on the quotation)
                analysis = near_memo[0]
            # a quotation that is the predicate of the host clause ("the figures were "VERIFIED and PROVED correct" by the
            # committee", "the answer was "verified and correct"") is read in that clause, with its marks only: the host's subject
            # and evaluator say whose assessment it is (an outside party's reported speech is read by its frame below)
            prev = before[-1] if before else None
            if prev is not None and prev.w in _MENTION_VERBS and len([x for x in itoks if not x.punct]) <= 2:
                # a word to type or say ("Reply "approve" and I will ..."): mentioned, not used
                for m in range(qa, qb):
                    if not chars[m].isspace() and chars[m] not in ".!?":
                        chars[m] = "q"
                continue
            if prev is not None and prev.has("C:copula") and any(x.has("C:m_textnoun", "C:analysed_text") for x in before[-8:]) and \
                    any(x.has("C:src_noun", "C:analysed_text", "C:eval_out") or (x.cap and not x.init) for x in before[-8:]) and not explicit:
                # "The final sentence of the editorial is '...'": a line of an analysed text identified by its words (attack round 3)
                for m in range(qa, qb):
                    if not chars[m].isspace() and chars[m] not in ".!?":
                        chars[m] = "q"
                continue
            if prev is not None and reporter not in (None, "SELF") and (prev.has("C:copula", "C:aux") or prev.w in (
                    "seem", "seems", "seemed", "remain", "remains", "remained", "look", "looks", "looked", "deemed", "rated",
                    "declared", "pronounced", "called")) and not prev.has("C:report_verb") or (prev is not None and prev.w in (
                    "were", "was", "is", "are") and reporter not in (None, "SELF")):
                chars[qa] = " "
                chars[qb - 1] = " "
                continue
            if reporter in (None, "SELF", "INT", "ASR"):
                # the writer's own words or an internal report: read inline and alone
                chars[qa] = " "
                chars[qb - 1] = " "
                relays.append((a + qa + 1, a + qb - 1, reporter or "SELF"))
                continue
            # an outside party's quotation: relayed as the writer's when it refers to this answer, or when no re-anchoring to its
            # reporter can give it a subject of its own (a status label or a verbless assessment, "QA: pass.", "Reviewed and
            # approved."; a check credited to the pipeline, "Z3 found no counterexample"; the answer's own genre or the pipeline's
            # checks as its theme, "the working is right"); a clause whose theme is the reporter's own ("I checked it.", "Everything
            # is fine.") is the reporter's words, and so is anything an analysed text says (a tagline, a poem, a character)
            analysed = any(t.has("C:analysed_text") for t in frame) or _source_letter(frame)
            fr = [t for t in before[-8:] if not t.punct]
            verb_at = next((k for k, t in enumerate(fr) if (t.has("C:report_verb") or t.w in _ES_REPORT_FINITE) and k > 0), None)
            # (a named source or a document as the subject of a reporting verb: "The Annual Report 2020 states that '...'"; a frame
            # with no reporting verb, "In plain text: '...'", is the writer's own)
            source = verb_at is not None and any(t.has("C:src_noun", "C:analysed_text", "C:eval_out") or (t.cap and not t.init and k > 0) or
                                                 _possessive(t) or (
                # (a third party named by a common noun, "El ministro afirmó", "El comunicado dice": attack round 5)
                k > 0 and (fr[k - 1].has("C:det") or fr[k - 1].w in ("one",)) and not fr[k - 1].has("C:poss1", "C:demonstrative") and
                t.w.isalpha() and
                not t.has("C:genre", "C:genre_strong", "C:part", "C:eval_int", "C:tool", "C:eval_asr", "C:eval_int_agentive", "C:m_eval",
                          "C:pron1", "C:anaph", "C:anchor"))
                                                 for k, t in enumerate(fr[:verb_at]))
            if not source and _pronoun_reporter(before) and _source_before(s, a):
                source = True  # (a pronoun reporting for the source the sentence before names)
            if not explicit and reporter == "OUT" and any(t.has("C:anchor_idioms") and t.w not in ("so far",) and any(
                    g in t.w for g in ("answer", "response", "reply", "respuesta", "working", "solution")) and m > 0 and
                    before[-8:][m - 1].w in ("on", "of", "about", "for", "regarding", "sobre", "de") for m, t in enumerate(before[-8:])):
                explicit = True  # an evaluator's words ON this answer ("Reviewer's note on this answer: '...'"; check round 9 of c3c)
            if explicit or (not analysis and not analysed and _relay_has_no_reporter_theme(itoks, source)):
                relays.append((a + qa + 1, a + qb - 1, "OUT-relayed"))
            for m in range(qa, qb):
                if not chars[m].isspace() and chars[m] not in ".!?":
                    chars[m] = "q"
    # reported speech of an outside party without marks: "The narrator claims that he checked every lock twice."
    masked = "".join(chars)
    toks = _merge(_tokens(masked, 0, len(masked)))
    _mark_initials(toks)
    _es_copula_in_context(toks)
    reread = False
    for k, t in enumerate(toks[:10]):
        if t.has("C:report_verb") and not any(_finite(toks, m) for m in range(k)) and t.w not in ("give", "gives", "gave", "show", "shows", "showed", "read", "reads", "put", "puts",
                                                  "agree", "agrees", "agreed", "return", "returns", "returned", "note", "notes",
                                                  "noted", "add", "adds", "added") and k > 0 and (_finite(toks, k) or t.w in _ES_REPORT_FINITE) and \
                not toks[k - 1].has("C:det", "C:dist"):
            subj_np = toks[:k]
            cm = max((m for m, x in enumerate(subj_np) if x.w == ","), default=-1)
            if cm >= 0:
                subj_np = subj_np[cm + 1:]  # "En el artículo, el autor afirma que ...": the reporter after the setting
            rep = eval_class(subj_np, ctx)
            if rep != "OUT" and subj_np and any(x.has("C:src_noun", "C:analysed_text") and not x.has("C:pron1", "C:poss1")
                                                for x in subj_np) and not any(x.has("C:demonstrative", "C:poss1", "C:anchor")
                                                                              for x in subj_np):
                rep = "OUT"  # "The article claims ...", "El artículo afirma ...": a document reports (attack round 3)
            nxt = toks[k + 1] if k + 1 < len(toks) else None
            if rep == "OUT" and nxt is not None and not any(x.has("C:pron1") for x in toks[:k]) and \
                    not any(x.cap for x in toks[:1] if x.w in ("i",)):
                rest_start = nxt.a
                end = len(masked)
                for x in toks[k + 1:]:
                    if x.w in (";",) or (x.w == "," and toks.index(x) + 1 < len(toks) and toks[toks.index(x) + 1].w in ("but", "and")
                                         and toks.index(x) + 2 < len(toks) and toks[toks.index(x) + 2].has("C:pron1")):
                        end = x.a
                        break
                    # a verbless tag after a final dash is the answer's own comment on what it reported ("... can seem temporary
                    # — 100% accurate."), never part of the reported words
                    if x.w in ("—", "–", "--"):
                        m0 = toks.index(x)
                        tail = [y for y in toks[m0 + 1:] if y.a < end]
                        if tail and not any(y.w in ("—", "–", "--") for y in tail) and \
                                not any(_finite(toks, m) for m in range(m0 + 1, m0 + 1 + len(tail))):
                            end = x.a
                            break
                comp = masked[rest_start:end]
                comp_toks = _merge(_tokens(masked, rest_start, end))
                if any(x.has("C:anchor_idioms") and x.w not in ("so far",) for x in comp_toks):
                    break
                # the answer itself named in the reported words ("The examiner's report says the answer was ..."): an explicit
                # reference to this answer, never re-anchored to the reporter (design 3.6 (i))
                if any(x.w in _ANSWER_SELF_NOUNS and m > 0 and comp_toks[m - 1].w in ("the", "this", "my", "our")
                       for m, x in enumerate(comp_toks)):
                    break
                masked = masked[:rest_start] + "".join("q" if (c.isalnum()) else c for c in comp) + masked[end:]
                reread = True
            break
    if reread:
        toks = _merge(_tokens(masked, 0, len(masked)))
        _mark_initials(toks)
    return masked, relays, toks


def _source_letter(toks: list[Tok]) -> bool:
    """Whether a frame names a lettered or numbered source of the paper ("In Source B the general writes,", "Fuente 2"): an
    analysed source, whose quoted words are its own whatever they point at."""
    for k, t in enumerate(toks[:-1]):
        if t.w in ("source", "fuente", "document", "documento") and t.cap:
            n = toks[k + 1].raw
            if (len(n) == 1 and n.isupper()) or n.isdigit():
                return True
    return False


def _analysis_nearby(s: str, a: int, b: int) -> bool:
    """Whether the sentence before or after ``s[a:b]`` in the same paragraph analyses what the quotation says (attack round 3:
    "Source C ... ends with '...'. Its purpose was propaganda, which limits its reliability."): an ANALYSIS frame of the quoted
    words written in the next sentence. Bounded: 300 characters each side."""
    lo = max(0, a - 300)
    hi = min(len(s), b + 300)
    left = s[lo:a]
    right = s[b:hi]
    k = left.rfind("\n\n")
    if k >= 0:
        left = left[k + 2:]
    k = right.find("\n\n")
    if k >= 0:
        right = right[:k]
    for part, start in ((left, a - len(left)), (right, b)):
        if part.strip() and any(t.has("C:analysis") for t in _merge(_tokens(s, start, start + len(part)))):
            return True
    return False


#: The genre nouns that name the answer itself in reported words ("the answer was verified"), never a subject's text.
_ANSWER_SELF_NOUNS = frozenset("answer response reply solution working workings calculations respuesta solucion".split())


def _relay_has_no_reporter_theme(itoks: list[Tok], reporter_is_source: bool = False) -> bool:
    """Whether an outside party's quotation, re-anchored to its reporter (design 3.6), still speaks of an answer's assessment: a
    status label or a verbless assessment (its implicit theme is the answer), a check credited to the pipeline or an internal tool,
    or an assessment whose theme is the answer's genre ("the working", "the solution") or the pipeline's checks ("All checks
    passed")."""
    words = [t for t in itoks if not t.punct]
    if not words:
        return False
    fam_words = [t for t in words if t.fam() - {"PROVENANCE"} or t.w.startswith("zz")]
    if not fam_words:
        return False
    k_lab = _label(itoks)
    if k_lab is not None and any(t.fam() & {"STATUS", "CHECK", "APPROVE", "OUTCOME"} for t in itoks) and \
            not any(_finite(itoks, m) and not itoks[m].has("v:part") for m in range(k_lab)):
        # (a clause before a colon, "Our statisticians have verified the harvest: ...", is the reporter's sentence, no label)
        return True
    if not _has_clause(itoks) and not any(_finite(itoks, m) and not itoks[m].has("v:part") for m in range(len(itoks))) and \
            all(t.num or t.fam() or t.w.startswith("zz") or t.w in _SIGNAL or t.w in ("once", "all", "every", "each", "no", "none",
                                                                                      "and", "y", "but", "fully", "now", "here")
                or t.has("C:part", "C:genre", "C:check_noun", "C:dist", "C:det", "C:anaph", "C:anchor", "C:neg", "C:prep", "C:eval_int",
                         "C:tool", "C:assess_key", "C:defect_key") for t in words):
        return True
    if any(t.has("C:tool") or (t.has("C:eval_int") and not t.has("C:pron1", "C:poss1") and t.w not in ("notes", "records", "log", "logs",
                                                                                                      "registro", "trail"))
           for t in words):
        return True
    if any(t.has("C:genre_strong") or (t.has("C:check_noun") and t.w.endswith("s")) for t in words) and (
            not reporter_is_source or any(t.has("C:anchor", "C:anchor_idioms") or t.w in ("this", "these") for t in words) or any(
                t.has("C:genre_strong") and m > 0 and words[m - 1].w in ("the", "el", "la") for m, t in enumerate(words))):
        # (a source's own answers, quantified, "I double-checked every answer" in a participant's diary, are the source's: attack round
        # 5; "the working", "the answer" with the definite article name this answer's, whoever is credited)
        return True
    # every content word meta vocabulary, with an item of an answer as its theme ("every figure in it has been verified", "the
    # values above were all checked"): no subject of the reporter's own is named (a pronoun theme is: "I checked it.")
    if _content_free(itoks) and any(t.has("C:part", "C:genre", "C:anchor", "C:anchor_idioms") for t in words) and \
            not any(t.has("C:poss1", "C:pron1") and not t.has("C:anchor_idioms") for t in words) and \
            (any(t.has("C:anchor", "C:anchor_idioms", "C:genre_strong") or t.w in ("it", "this", "these") for t in words) or
             not reporter_is_source):
        # (a named source's or a document's own words about its own figures, "The Annual Report 2020 states that 'all figures were
        # audited'", keep their reporter's theme unless they point at this answer: "above", "in it", "this answer")
        return True  # ("All our figures are verified", said by a company's spokesperson: the reporter's own figures, its own words)
    return False


def _es_copula_in_context(toks: list[Tok]) -> None:
    """The subjunctive "esté"/"estén" folds to the demonstrative "este"/"esten": before an outcome word ("que todo esté bien") it is
    the copula."""
    for k in range(len(toks) - 1):
        t = toks[k]
        if t.w in ("este", "esten") and toks[k + 1].fam() & {"OUTCOME", "QUALITY"} and not toks[k + 1].has("C:part", "C:genre"):
            t.t = frozenset(t.t | {"C:copula", "C:aux"})


def _has_clause(toks: list[Tok]) -> bool:
    """Whether a token run is a clause of its own: an auxiliary or a finite verb after a noun phrase."""
    for m, t in enumerate(toks):
        if t.has("C:aux", "C:copula"):
            return True
        if m > 0 and _finite(toks, m) and toks[m - 1].has("C:part", "C:genre", "C:pron1", "C:pron3", "C:anaph", "C:eval_int",
                                                           "C:eval_asr", "C:eval_out", "C:tool"):
            return True
    return False


def _content_free(itoks: list[Tok]) -> bool:
    """Whether every content word of a quotation is meta vocabulary (families, part and genre nouns, pipeline evaluators,
    quantifiers, numbers): such a quotation can only be about an answer (design 3.6 (iii))."""
    words = [t for t in itoks if not t.punct]
    if len(words) < 2:
        return False
    for t in words:
        if t.num or t.fam() - {"PROVENANCE"} or t.has("C:part", "C:genre", "C:eval_int", "C:tool", "C:dist", "C:dist_idioms", "C:det",
                                                       "C:aux", "C:copula", "C:prep", "C:neg", "C:coordinator", "C:anaph", "C:anchor",
                                                       "C:pron1", "C:poss1", "C:check_noun", "C:neg_pron", "C:anchor_idioms",
                                                       "C:light_verbs"):
            if t.w in ("receipts", "receipt"):
                return False
            continue
        if t.w in ("by", "and", "are", "is", "has", "have", "been", "the", "all", "every"):
            continue
        return False
    return True


# ================================================================================================================== other languages and scripts
def _script_of(c: str) -> Optional[str]:
    o = ord(c)
    if 0x0400 <= o <= 0x052F:
        return "cyrillic"
    if 0x0370 <= o <= 0x03FF:
        return "greek"
    if 0x4E00 <= o <= 0x9FFF or 0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF:
        return "cjk"
    if 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF:
        return "hangul"
    if 0x0600 <= o <= 0x06FF:
        return "arabic"
    if 0x0900 <= o <= 0x097F:
        return "devanagari"
    if 0x0590 <= o <= 0x05FF:
        return "hebrew"
    if 0x0E00 <= o <= 0x0E7F:
        return "thai"
    if 0x0E80 <= o <= 0x0EFF:
        return "lao"
    if 0x1780 <= o <= 0x17FF:
        return "khmer"
    if 0x1000 <= o <= 0x109F:
        return "myanmar"
    if 0x0530 <= o <= 0x058F:
        return "armenian"
    if 0x10A0 <= o <= 0x10FF:
        return "georgian"
    if c.isalpha() and not c.isascii() and o > 0x024F and o not in range(0x1E00, 0x1F00):
        return "other"
    return None


#: English function words: a sentence with two of them is English, whatever words it shares with another language's net.
_ENGLISH_FUNCTION = frozenset("the is are and of this to was were in it that says means form with for be has have so on its own can by an as at "
                              "or not if we you your but from which will would should may there their our my i he she they them these those "
                              "been being do does did no any all each every what when where who how than then".split())
_NET_SCRIPTS = frozenset({"cyrillic", "cjk", "hangul", "arabic", "devanagari"})
_UNSPACED_SCRIPTS = frozenset({"thai", "lao", "khmer", "myanmar"})


_ES_MARKERS = frozenset(("el", "los", "las", "del", "he", "ha", "han", "hay", "es", "son", "y", "que", "por", "para", "con", "una",
                         "un", "lo", "mi", "mis", "su", "sus", "texto", "datos"))
_NET_SETS: list[tuple[object, dict[str, tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]]]]] = []


def _net_sets(net: dict) -> dict[str, tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]]]:
    """The folded (positive, negator, defect, function) word sets of each Latin-script net, built once per loaded lexicon (they
    were rebuilt for every sentence: data derived from the lexicon, not a memo of any reading)."""
    if not _NET_SETS or _NET_SETS[0][0] is not net:
        sets = {}
        for lang, spec in net.items():
            sets[lang] = (frozenset(fold_word(x) for x in spec.get("positive", [])),
                          frozenset(fold_word(x) for x in spec.get("negators", [])),
                          frozenset(fold_word(x) for x in spec.get("defect", [])),
                          frozenset(fold_word(x) for x in spec.get("function", []) + spec.get("scope", [])))
        _NET_SETS[:] = [(net, sets)]
    return _NET_SETS[0][1]


_FORMULA_CHAR_RE = re.compile(r"[0-9=<>≤≥≈≠+\-−×÷*/^√∑∏∫∂()\[\]{}|·⋅′″\u2070-\u209F\u00B2\u00B3\u00B9]")
_LETTER_RUN_RE = re.compile(r"[^\W\d_]+")
_MATH_ALNUM = (0x1D400, 0x1D7FF)


def _folded_letters(w: str) -> str:
    """``w`` with each letter the fold table maps replaced by its folded form (rule N3); a mathematical alphanumeric symbol the
    table leaves out (the mathematical Greek letters) is read as its compatibility letter. Other letters are kept as written."""
    if w.isascii():
        return w
    table = fold_table()["fold"]
    out = []
    for c in w:
        o = ord(c)
        f = table.get(o)
        if f is not None:
            out.append(f)
        elif _MATH_ALNUM[0] <= o <= _MATH_ALNUM[1]:
            out.append(unicodedata.normalize("NFKC", c))
        else:
            out.append(c)
    return "".join(out)


def _net_found(orig: str, masked: str, es_context: bool = False, short_line: bool = True) -> tuple[bool, bool]:
    """(gated by G9, unread by U3) for one sentence: the strong-word net of other languages (Latin-script nets read the folded
    text; the nets of other scripts and the script count read the ORIGINAL sentence, before look-alike letters are folded) and the
    scripts with no vocabulary."""
    net = lexicon().net
    net_sets = _net_sets(net)
    raw = orig.lower()
    scripts: dict[str, int] = {}
    for w0 in orig.split():
        # a letter the fold table maps (fullwidth, mathematical, small-capital, circled letters: rule N3) is read as the letter it
        # folds to, so a folded run is read as text, never as a script with no vocabulary (attack round 6: every fullwidth or
        # mathematical-italic sentence was refused, "𝑓(𝑥) = 3𝑥²" included); Cyrillic and Greek look-alikes (N4) keep their script
        w = _folded_letters(w0)
        letters = [c for c in w if c.isalpha()]
        if len(letters) >= 2 or any(_script_of(c) == "cjk" for c in letters):
            kinds = {_script_of(c) for c in letters}
            kinds.discard(None)
            # a symbol of a formula that mixes a letter of another script with Latin ones ("mcΔT", "ΔH", "λmax") is no word of that
            # script: a word counts only when at least two of its letters, and more than half, are of the script
            if kinds and not any(_script_of(c) == "cjk" for c in letters):
                n_sc = sum(1 for c in letters if _script_of(c) is not None)
                if n_sc < 2 or n_sc * 2 <= len(letters):
                    kinds = set()
                elif _FORMULA_CHAR_RE.search(w) and max(len(r) for r in _LETTER_RUN_RE.findall(w)) <= 2:
                    # a token of a formula (an operator, a digit, a bracket or an index in it: "2π/ω", "Δλ/λ", "1/√(ε₀μ₀)", "θ/π")
                    # whose letters stand alone or in pairs is a run of symbols, never a word of the script (attack round 6)
                    kinds = set()
            if kinds:
                sc = sorted(kinds)[0]
                # a script written without spaces between words (Thai, Lao, Khmer, Myanmar): every four letters count as a word
                n_words = max(1, len(letters) // 4) if sc in _UNSPACED_SCRIPTS else 1
                scripts[sc] = scripts.get(sc, 0) + n_words
    gated = False
    es_markers = None
    low = fold_word(masked)
    ws = [w.strip(".,;:!?\u00ab\u00bb\"'()\u00bf\u00a1") for w in low.split()]
    for lang, spec in net.items():
        script = spec.get("script")
        if script:
            if script not in scripts:
                continue
            negs = [n.lower() for n in spec.get("negators", [])]
            for p in spec.get("positive", []):
                p = p.lower()
                at = raw.find(p)
                while at >= 0:
                    window = raw[max(0, at - 12):at]
                    negated = any((n in window) if script in ("cjk", "hangul") else ((" " + n + " ") in (" " + window + " "))
                                  for n in negs)
                    if not negated and not (script in ("cjk",) and any(n in raw[at + len(p):at + len(p) + 3] for n in negs)):
                        gated = True
                        break
                    at = raw.find(p, at + 1)
                if gated:
                    break
            if gated:
                break
            continue
        if es_markers is None:
            es_markers = sum(1 for w in ws if w in _ES_MARKERS)
        if (es_markers >= 2 or es_context) and lang in ("pt", "ca", "it", "fr"):
            continue  # (a clause of a Spanish sentence is Spanish: "La forma correcta es «haya»" is no Catalan)
        positives, negs, defects, func = net_sets[lang]
        hits = sum(1 for w in ws if w in func or w in positives or w in defects)
        words = [w for w in ws if w]
        # a negator of the reader's own classes (English and Spanish: "no", "sin", "nunca") right before the word negates it in
        # this net too ("No verificado.", "Respuesta no verificada.": attack round 6, read as Portuguese positives)
        if any(w in positives and any("C:neg" in word_tags(x) for x in ws[max(0, k - 2):k] if x) for k, w in enumerate(ws)):
            continue
        # a verbless label of the net alone (a bracket or a fragment of one or two words: "(geprüft)", "Alles korrekt."): G9 on its
        # own, the label of what it follows (rule G6 read in another language)
        if words and len(words) <= 2 and any(w in positives for w in words) and all(w in positives or w in func for w in words) and \
                not any(w in negs for w in words) and not all(w in lexicon().words and "lang:es" not in lexicon().words[w] for w in words):
            # (a word the English reader reads itself, "Correct", is read there, in its clause: "Correct, but the units are missing.")
            gated = True
            break
        if hits < 2:
            continue
        eng = sum(1 for w in ws if w in _ENGLISH_FUNCTION)
        if eng >= 2 or eng > hits:
            continue  # an English sentence that shares a word with the net ("a diminutive-style form of "mero" (exact)")
        for k, w in enumerate(ws):
            pre = ws[max(0, k - 4):k]
            negated = any(x in negs or x.startswith("n'") for x in pre)
            if w in positives and not negated:
                gated = True
            elif w in defects and any(x in negs for x in ws[max(0, k - 3):k]):
                gated = True
        if gated:
            break
    unread = any(n >= 3 for sc, n in scripts.items() if sc not in _NET_SCRIPTS)
    if not unread and short_line and any(sc not in _NET_SCRIPTS for sc in scripts):
        # a short line of a script with no vocabulary ("Status: Επαληθεύτηκε", "ตรวจสอบแล้ว", "מאומת."): what it says is not read, so
        # it is never taken for nothing (attack round 5: one or two words were read as nothing and delivered). A word of that script
        # inside an English or Spanish sentence ("the term logos (λόγος) means word") stays a gloss of that sentence.
        unread_n = sum(n for sc, n in scripts.items() if sc not in _NET_SCRIPTS)
        other = sum(1 for w in map(_folded_letters, orig.split()) if sum(1 for c in w if c.isalpha() and _script_of(c) is None) >= 2)
        unread = other <= 2 and unread_n >= other
    return gated, unread


def _mark_initials(toks: list[Tok]) -> None:
    """Mark the first word of the sentence and of each clause, label value, bracket and quotation as initial (its capital is no
    proper name)."""
    first = True
    for t in toks:
        if t.punct:
            if t.w in (":", ";", "(", "[", "\u201c", '"', "\u00ab", ".", "!", "?", "\u2014", "\u2013", "-", "*", "|", "<", ">"):
                first = True
            continue
        if first:
            t.init = True
            first = False


_IN_VALUE: list = []
_KV_RE = re.compile(r"""["']([A-Za-z_][\w -]{0,40})["']\s*[:=]\s*["']([^"'\n]{1,400})["']""")


def _key_values(s: str, a: int, b: int) -> list[tuple[int, int]]:
    """The string values of keys in a data or code line ('"note": "..."', "status = '...'"): at most 64 per sentence."""
    out = []
    for m in _KV_RE.finditer(s, a, b):
        out.append((m.start(2), m.end(2)))
        if len(out) >= 64:
            break
    return out


_SUPERSCRIPT_DIGITS = frozenset("\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")
#: A footnote mark of superscript digits: at the start of a line (before a blank), or right after a sentence's end or a closing
#: quotation mark (before a blank, a line break or the end). Rule S1 reads a footnote as a piece; its mark is no quantity of the
#: subject ("¹ All values cross-checked.", "... were confirmed.¹"). An exponent ("x²", "10³ m", "m².") follows a letter or digit.
_FOOTNOTE_MARK_RE = re.compile("(?:(?<=^)|(?<=\n)|(?<=[.!?;:\"'\u201d\u2019\u00bb)\\]]))[ \t]*([\u2070\u00b9\u00b2\u00b3\u2074-\u2079]{1,3})"
                               "(?=[ \t\n]|$)")


_LEAD_NOTE_MARK_RE = re.compile(r"(?m)^([ \t>]*)(\[\d{1,3}\]|\(\d{1,3}\)|\^\d{1,3}|\d{1,3}\)|[*†‡§]{1,3})(?=[ \t]+[^\W\d_])")


def _blank_footnote_marks(text: str) -> str:
    """``text`` with its superscript footnote marks blanked character for character (length kept)."""
    return _FOOTNOTE_MARK_RE.sub(lambda m: m.group(0)[:m.start(1) - m.start(0)] + " " * (m.end(1) - m.start(1)), text)


#: An abbreviation or a dotted initialism closing a word before a blank ("etc.", "e.g.", "i.e.", "a.m.", "U.S.", "km/h."): the
#: sentence splitter reads on past it (S2), so a verdict after it is read again as a sentence of its own (attack round 3).
_ABBR_TAIL_RE = re.compile(r"(?<![\w.])(?:etc|e\.g|i\.e|viz|vs|cf|approx|ca|al|[a-z]{1,4}/[a-z]{1,4}|(?:[a-z]\.){1,5}[a-z])\.[ \t\n]+(?=\S)",
                           re.IGNORECASE)
_TITLE_ABBR = frozenset(("mr", "mrs", "ms", "dr", "st", "prof", "no", "fig", "figs", "eq", "eqs", "vol", "p", "pp", "ed"))


def _abbreviation_tails(s: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """For each sentence span, the tails that open after an abbreviation the splitter read on past (attack round 3: "Prices rise,
    etc. Verified." must read "Verified." as a fragment of its own, as after a full stop). The sentence itself is still read whole;
    a tail adds a reading, never removes one. Each tail ends at the next abbreviation: linear."""
    out: list[tuple[int, int]] = []
    for x0, y0 in spans:
        if y0 - x0 < 6 or "." not in s[x0:y0]:
            continue
        cuts = [m for m in _ABBR_TAIL_RE.finditer(s, x0, y0)
                if m.end() < y0 and s[m.start():m.end()].strip().rstrip(".").lower() not in _TITLE_ABBR][:4096]
        # each tail runs to the next abbreviation (or the sentence end): every character is read in at most one tail, so the
        # tails of a long run of abbreviations cost one more pass, never a pass per abbreviation
        for k, m in enumerate(cuts):
            end = cuts[k + 1].start() if k + 1 < len(cuts) else y0
            if end > m.end():
                out.append((m.end(), end))
    return out


#: Verbs that put a label on what they name ("labelled VERIFIED", "flagged as correct", "etiquetado como correcto").
_LABEL_VERBS = frozenset("labelled labeled label labels flagged flag tagged tag stamped stamp badged branded marked etiquetado etiquetada "
                         "etiquetados marcado marcada marcados sellado".split())


_INSERT_OUTSIDE = frozenset("by from according segun por source sources fuente fuentes cf see vease".split())


def _without_inserts(toks: list[Tok]) -> Optional[list[Tok]]:
    """The sentence without the bracketed inserts inside its noun phrases ("All values above (in kJ) are correct.", "These densities
    (people per km²) have been verified.", "Every figure in this answer (the 1900 figure, the 1901 figure) has been verified."), or
    None when it has none. A unit, a list or a gloss in brackets does not change what the noun phrase names, so the sentence is also
    read without it (attack round 4: a bracket between theme and predicate broke the reading). An insert that credits an outside
    source ("(from the ONS)", "(checked by the Registrar General)") is kept unless the noun phrase is the writer's own or anchored
    ("My figures (from the 2011 census)"); a computation in brackets is the working, kept."""
    out: list[Tok] = []
    dropped = False
    n = len(toks)
    # the closing bracket of each opening one, in one pass (an unclosed bracket has none: linear, design 2.9)
    close: dict[int, int] = {}
    stack: list[int] = []
    for k, t in enumerate(toks):
        if t.w == "(":
            stack.append(k)
        elif t.w == ")" and stack:
            close[stack.pop()] = k
    words_after = [0] * (n + 1)
    for k in range(n - 1, -1, -1):
        words_after[k] = words_after[k + 1] + (0 if toks[k].punct else 1)
    k = 0
    while k < n:
        t = toks[k]
        j = close.get(k, -1)
        if t.w == "(" and out and not out[-1].punct and j > k + 1:
            inner = toks[k + 1:j]
            label = len(inner) == 1 and (inner[0].num or (len(inner[0].w) <= 4 and inner[0].w.isalpha()))  # "(a)", "(1)", "(iii)"
            colon = j + 1 < n and toks[j + 1].w == ":"
            if not label and not colon and len(inner) <= 24 and words_after[j + 1] and \
                    not any(x.w in _REL or x.w in ("+", "×", "÷", "*", "−") for x in inner):
                outside = any(x.w in _INSERT_OUTSIDE or x.has("C:eval_out", "C:src_noun", "C:according") or (x.cap and not x.init and
                                                                                                          x.w.isalpha() and len(x.w) > 1)
                              for m, x in enumerate(inner) if not x.has("C:unit") and not (
                                  x.w == "per" and m + 1 < len(inner) and inner[m + 1].has("C:unit")))  # ("people per km²": a unit)
                head = out[-12:]
                own = any(x.has("C:poss1", "C:anchor", "C:anchor_idioms") for x in head)
                if not outside or own:
                    dropped = True
                    k = j + 1
                    continue
        out.append(t)
        k += 1
    return out if dropped else None


def _meaning_review(toks, ctx, question, fnd, cls, s, a, b, kind):
    from .meaning import review
    return review(toks, ctx, question, fnd, cls, s=s, a=a, b=b, kind=kind)


_ATTR_RE = re.compile(r"""<[A-Za-z][\w-]{0,20}\b[^<>]{0,400}?\b(?:title|alt|aria-label|aria-description|label|summary|placeholder|"""
                      r"""data-[\w-]{1,30})\s*=\s*(?:"([^"<>]{1,600})"|'([^'<>]{1,600})')""")
_IN_ATTR: list = []


def _read_text_attrs(text: str, ctx: Context):
    hits: list = []
    unread: list = []
    _IN_ATTR.append(1)
    try:
        for m in _ATTR_RE.finditer(text):
            g = 1 if m.group(1) is not None else 2
            va, vb = m.start(g), m.end(g)
            h, u = read_text(text[va:vb], ctx)
            hits += [(r, f, "label_inside", va + a, va + b, "the text") for r, f, _form, a, b, _w in h]
            unread += [(k, va + a, va + b, "the text") for k, a, b, _w in u]
    finally:
        _IN_ATTR.pop()
    return hits, unread


_STRUCK_RE = re.compile(r"~~[^~\n]{1,400}?~~|<(del|s|strike)\b[^>]{0,80}>[^<]{0,400}</\1\s*>", re.I)
_IN_STRUCK: list = []


_SECOND_TO_FIRST = {"your": "my", "yours": "mine", "you": "I", "tu": "mi", "tus": "mis", "tuya": "mía", "tuyo": "mío", "usted": "yo"}
_SECOND_TO_FIRST_RE = re.compile(r"\b(?:your|yours|you|tu|tus|tuya|tuyo|usted)\b", re.I)
_IN_RUNON: list = []
#: Set while the decoding of an encoded label is read (rule N10): a decoding is never decoded again.
_IN_ENCODED: list = []
#: A key=value attribute written into prose ("status=FORMALLY_CHECKED", "verified=true"): a label of its own, never a word of the
#: sentence around it (a key of three letters or more, a value with a letter; "x=2" stays maths).
_KEY_VALUE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z_.-]{2,40}=[^\s=]*[A-Za-z][^\s=]*")
#: Words that open a clause when written with a capital in mid-line ("... countryside The Treaty ...", "Accuracy: 100% If x > 2").
_CLAUSE_OPENERS = frozenset("the this these those that a an if it its in on at when while we our my all every each everything there then "
                            "so thus hence therefore since as la el los las lo un una si todo todos toda todas este esta estos estas mi "
                            "mis nuestro nuestra hay you your nobody nothing no not none another both after upon puedes sin".split())
_LOWER_OPENERS = frozenset("the this these those my our every all everything everyone each la el los las todo todos toda mi mis nuestro "
                           "nuestra este esta estos estas no nobody nothing none full zero".split())
_BEFORE_NAME = frozenset(("in on at by for with of to from as into over through past under within without about "
                                                 "against via per and or nor but the a an his her their its our my your this that these "
                                "those de del la el los las y o en por para con al según mr mrs ms dr st saint lord "
                                "lady sir king queen president").split())
#: Words that open a phrase or a clause that is not a sentence of its own ("Without such evidence, Option 1 ...").
_SUBORDINATE_OPENERS = frozenset(("in on at by for with of to from as into over through past under within without about against via per "
                                  "de del en por para con al").split()) | frozenset("if when whenever while although though because since unless until after before once "
                                                "despite whereas whether given according following considering assuming si cuando "
                                                "aunque porque como sin según tras antes después".split())
_MODAL_AFTER_I = frozenset("would will can could should must shall may might am have had do did guarantee vouch stand swear certify "
                           "confirm promise sign".split())


def _symbol_token(w: str) -> bool:
    c = w[0]
    return not c.isascii() and not c.isalnum() and unicodedata.category(c) in ("So", "Sm") and c not in "±×÷−∓≤≥≈≠∑∏∫√∂∞∈∉⊂⊆∪∩→←↔⇒⇔°"


_QUOTE_OPENERS = frozenset("\"'«»“”‘’„‚‹›「")


def _letter_like_token(w: str) -> bool:
    f = fold_table()["fold"].get(ord(w[0]))
    return f is not None and len(f) == 1 and f.isalpha() and not w[0].isascii() and not w[0].isalpha()


_MARKUP_LEAD_RE = re.compile(r"^(?:\*{1,3}|_{1,3}|`{1,3}|~~|<(?:b|strong|em|i|u|mark|code)>)+", re.I)
_INVISIBLE_RE = re.compile("[\u200b-\u200f\u2060-\u2064\ufeff\u00ad\u0300-\u036f]")
#: hidden characters and the combining marks that style a letter (underline, overline, strike-through), never an accent
_STYLING_MARK_RE = re.compile("[\u200b-\u200f\u2060-\u2064\ufeff\u00ad\u0305\u0331-\u0333\u0335-\u0338]")


def _styled_assessment(w: str) -> bool:
    """Whether the word ``w`` is an assessment word set off by markup ("**Verified**", "`verified`", "<b>VERIFIED</b>") or written in
    styled or marked letters (small capitals, combining underlines, hidden characters inside it)."""
    m = _MARKUP_LEAD_RE.match(w)
    core = w[m.end():] if m else w
    # (styled letters: the fold table's letter-like blocks or small capitals, combining marks over letters, hidden characters; an
    # accented letter of a language, "revisión", is no styling)
    styled = bool(m) or bool(_STYLING_MARK_RE.search(core)) or any(
        letter_like(ord(c)) or (not c.isascii() and c.isalpha() and unicodedata.decomposition(c) == "" and
                                _folded_letters(c) != c) for c in core)
    if not styled or not core:
        return False
    core = _INVISIBLE_RE.sub("", _folded_letters(core))
    core = re.split(r"[*_`~<]", core, maxsplit=1)[0]
    return _family_word(core) and not _number_like(core)


def _unit_like(w: str) -> bool:
    w = w.rstrip(".,;")
    return "/" in w or any(c in "⁰¹²³⁴⁵⁶⁷⁸⁹⁻" for c in w) or (0 < len(w) <= 3 and not any(c in "aeiouAEIOU" for c in w))


def _family_word(w: str) -> bool:
    tw = word_tags(fold_word(w.lower().strip(".,;:!?\"'«»()")))
    return any(t.startswith("F:") for t in tw) and "agent" not in tw  # (an evaluator noun, "moderator", is no assessment)


def _mark_label_at(toks: list, k: int) -> bool:
    """Whether words ``k`` and ``k + 1`` of a line are a mark and an assessment word, in either order ("∎ verified", "QA ✔")."""
    if k < 0 or k + 1 >= len(toks):
        return False
    a, b = toks[k][2], toks[k + 1][2]
    if k + 2 < len(toks):
        nxt = toks[k + 2][2].strip("\"'«»(")
        if not (nxt[:1].isupper() or nxt[:1] in "|"):
            return False  # a mark inside the sentence ("a ✓ marks each species") is no label
    return (_symbol_token(a) and _family_word(b)) or (_family_word(a) and _symbol_token(b.rstrip(".,;")))


def _number_like(w: str) -> bool:
    return any(ch.isdigit() for ch in w) or w.endswith("%")


_OPERAND_RE = re.compile(r"[(\[]{0,3}[-−+]?[$£€¥]?\d[\d.,]{0,20}(?:%|/\d{1,9})?[)\]]{0,3}|[(\[]{0,3}[A-Za-zΑ-Ωα-ω]{1,3}[)\]]{0,3}|"
                         r"[A-Za-zΑ-Ωα-ω]{1,3}\([^()\s]{1,30}\)")


def _operand_like(w: str) -> bool:
    """Whether the word ``w`` reads as an operand of an arithmetic expression: a figure (with a sign, currency, per cent, a
    fraction or brackets), a symbol of at most three letters ("x", "ΣH") or a function value ("f(2)"). A word like "Check" or
    "parques" is no operand."""
    w = w.rstrip(".,;:")
    if not w or not _OPERAND_RE.fullmatch(w):
        return False
    return any(ch.isdigit() for ch in w) or len(w.strip("()[]")) <= 2 or "(" in w


_RUNON_QUOTE_RE = re.compile(r"\"[^\"\n]{1,2000}\"|“[^”\n]{1,2000}”|«[^»\n]{1,2000}»|„[^“”\n]{1,2000}[“”]|‘[^’\n]{1,2000}’|"
                             r"(?<![A-Za-z])'[^'\n]{1,2000}'(?![A-Za-z])|「[^」\n]{1,2000}」|‹[^›\n]{1,2000}›|»[^«\n]{1,2000}«|‚[^‘’\n]{1,2000}[‘’]")


def _sentence_tail(toks: list, k: int) -> int:
    """The number of words from word ``k`` of a line to the end of its sentence (a word ending in . ! or ?, or the line's end)."""
    n = 0
    for t in toks[k:]:
        n += 1
        if t[2][-1] in ".!?" or n > 40:
            break
    return n


def _sentence_tail_chars(text: str, toks: list, k: int) -> int:
    """The length in characters from the blank before word ``k`` of a line to the end of its sentence."""
    n = 0
    end = toks[k][1]
    for t in toks[k:]:
        end = t[1]
        n += 1
        if t[2][-1] in ".!?" or n > 40:
            break
    return end - toks[k - 1][1]


def _sentence_head(toks: list, k: int) -> int:
    """The number of words of the sentence before word ``k`` of a line."""
    n = 0
    for t in reversed(toks[:k]):
        if t[2][-1] in ".!?" or n > 40:
            break
        n += 1
    return n


def _assessment_end(toks: list, j: int) -> bool:
    """Whether word ``j`` of a line is an assessment word (a family word) that closes a label or a predicate: only marks before it
    ("∎ verified", "✔ checked") or a copula or auxiliary right before it ("is error-free", "are confirmed")."""
    x = toks[j][2].lower().strip(".,;:!?\"'«»()")
    tx = word_tags(fold_word(x))
    if not any(t.startswith("F:") for t in tx):
        return False
    if j > 0 and all(_symbol_token(t[2]) for t in toks[:j]):
        return True
    if j > 0:
        # (a copula before it: "is error-free", "are confirmed"; never a perfect, whose participle takes an object: "has tested
        # Taylor's claim")
        tp = word_tags(fold_word(toks[j - 1][2].lower().strip(".,;:!?\"'«»()")))
        return "C:copula" in tp and not (j + 1 < len(toks) and toks[j + 1][2].endswith(("'s", "’s")))
    return False


def _runon_breaks(text: str, head_only: Optional[list] = None) -> Optional[str]:
    """``text`` with a line break (same length, same offsets) at each place where a label or a self-assessment may run into a
    sentence with no sentence break between them (attack round 6: "status=FORMALLY_CHECKED Urban heat islands ...", "... 1919
    Checked", "Accuracy: 100% If x > 2 ...", "... | Todo correcto", "...\tI would stake my reputation on these numbers"):
    a tab, a run of two or more blanks or a bar between words (column and cell boundaries); either side of a key=value attribute or a
    symbol run; a comma or a blank before a word that opens a clause with a capital ("The", "If", "La"), or before a capitalised word
    after a lower-case content word or a figure (not after a preposition, an article or a name: "approved by Parliament", "the New
    Deal"); "I" before a modal or a pledge verb; a figure before a lower-case determiner ("... = 15 km/h the working ..."). None when
    there is no such place. The text is ALSO read with these breaks, and either reading's hits count: a split can only add the
    reading of a label alone, which is what the label says wherever it is written."""
    if len(text) > 200_000:
        return None
    out = list(text)
    changed = False
    pos = 0
    for line in text.split("\n"):
        if line.lstrip().startswith("|"):
            pos += len(line) + 1
            continue  # a table row: its cells are read as cells (pieces)
        table_row = False
        # (an aligned row of columns, two or more wide gaps, or code in backticks: its cells are data, never a label run into a
        # sentence; one wide gap or one tab joins a label to its content: "Checked\tThe Treaty ...")
        wide_gaps = len(re.findall(r"\S(?: {2,}|\t)\S", line))
        aligned = wide_gaps >= 2 or "`" in line
        toks = [(m.start() + pos, m.end() + pos, m.group(0)) for m in re.finditer(r"\S+", line)]
        # never inside a quotation: what a quotation says is read as a quotation (rule 3.6)
        quoted = [(m.start() + pos, m.end() + pos) for m in _RUNON_QUOTE_RE.finditer(line)]
        # the dashes of the line, counted once (counting them again at every dash was quadratic in a line of dashes: a line of
        # 10,000 list marks "- - - ..." took about 5 s; repair 1 after clearance c3c)
        dashes = sum(1 for t in toks if t[2] in ("-", "–", "—"))
        for k in range(1, len(toks)):
            a0, a1, x = toks[k - 1]
            b0, b1, y = toks[k]
            gap = text[a1:b0]
            brk = None
            xl = x.lower().strip(".,;:!?\"'«»()")
            yw = y.strip("\"'«»(")
            if x in ("-", "–", "—") and k >= 2 and (_operand_like(toks[k - 2][2]) or toks[k - 2][2] in ("€", "$", "£", "¥", "%")
                                                       and k >= 3 and _operand_like(toks[k - 3][2])) and _operand_like(y):
                brk = None  # a minus sign between two operands ("Check: 30 - 10 = 20.", "6% - 2% = 4%", "3 – 2 = 1"; a currency
                # sign written after the figure, "45 € - 9 € = 36 €", check round 9 of c3c): the computation goes on (attack
                # round 7: a worked check is material, boundary (b))
            elif x in ("-", "–", "—") and k >= 2 and dashes == 1:
                brk = a1  # a spaced dash: what follows it is read on its own too ("... parques - 100% correct")
            elif x[-1] in ".!?:;" or (x[-1] in "\"'»”’)" and len(x) > 1 and x[-2] in ".!?:;"):
                brk = None  # a sentence or label break already: read as written
            elif "\t" in gap or len(gap) >= 2:
                brk = None if aligned else a1
            elif y == "|" and not table_row:
                brk = b0
            elif x == "|" and not table_row:
                brk = a0
            elif _KEY_VALUE_TOKEN_RE.fullmatch(y.rstrip(".,;")) or _KEY_VALUE_TOKEN_RE.fullmatch(x.rstrip(".,;")):
                brk = a1
            elif _letter_like_token(y) and not _letter_like_token(x):
                brk = a1  # a run of letter-like symbols ("🆅🅴🆁🅸🅵🅸🅴🅳") is a word of its own
            elif x.rstrip(",;:.!?")[-1:] in _QUOTE_OPENERS and len(x.rstrip(",;:.!?")) > 1:
                brk = None  # after a closing quotation its frame follows ("'All is checked', Hamlet says.")
            elif x[-1] in "=≈≠≡(" or (not any(c.isalnum() for c in x) and not _symbol_token(x) and not _letter_like_token(x) and
                                      x not in ("-", "–", "—", "|", ">", "»", "→", "⇒", "::", "//") and "%" not in x):
                brk = None  # after an operator or a relation sign the expression goes on ("checked: bool = False", "x = Y")
            elif _styled_assessment(y) and _folded_letters(x) == x and not _MARKUP_LEAD_RE.match(x):
                brk = a1  # an assessment word set off by markup or written in styled letters ("**Verified**", "`verified`",
                # "<b>VERIFIED</b>", "ᴠᴇʀɪꜰɪᴇᴅ", "v̲e̲r̲i̲f̲i̲e̲d̲") is a label of its own
            elif (y[:1] in "[⟦" and y[1:2].isupper()) and not (x[:1] in "[⟦"):
                brk = a1  # a tag in brackets ("[ENGINE] ENTAILED", "⟦FORMALLY CHECKED⟧") is a label of its own
            elif y[:1] in _QUOTE_OPENERS or y[:1] in "([{":
                brk = None  # a quotation is read as a quotation ("prints 'Correct!'"), a bracket as a bracket
            elif _mark_label_at(toks, k) and not _mark_label_at(toks, k - 1):
                brk = a1  # a mark and an assessment word ("∎ verified", "QA ✔") after the content
            elif yw[:1].isupper() and yw != "I" and _assessment_end(toks, k - 1):
                brk = a1  # "∎ verified Urban ...", "the working is error-free Urban ...": the assessment ends there
            elif yw[:1].isupper() and yw != "I":
                yl = yw.lower().rstrip(".,;:!?")
                x_num = _number_like(x) or (k >= 2 and _number_like(toks[k - 2][2]) and _unit_like(x))
                # a capitalised word in mid-line is part of a name ("New York", "Mr Smith"), unless it is an assessment word or a tag
                # ("ENTAILED The ...", "⟦FORMALLY CHECKED⟧ The ...")
                x_name = x[:1].isupper() and k - 1 > 0 and not (x.strip("[]⟦⟧,").isupper() and _family_word(x.strip("[]⟦⟧,"))) \
                    and x[-1] not in "]⟧"
                if len(yl) == 1:
                    # a letter ("is A: mitochondria", "option B") is no clause opener; the article "A" after a figure or a status word
                    # opens one ("Confidence level: 99% A tariff raises ...")
                    if y == "A" and k + 1 < len(toks) and toks[k + 1][2][:1].islower() and toks[k + 1][2].isalpha() and (
                            _number_like(x) or _family_word(x) or _KEY_VALUE_TOKEN_RE.fullmatch(x)):
                        brk = a1
                elif x.endswith(",") and (yl in _CLAUSE_OPENERS or _family_word(yl) or (
                        "C:neg" in word_tags(fold_word(yl)) and k + 1 < len(toks) and _family_word(toks[k + 1][2]))):
                    brk = a1  # ", The ...", ", Zero errors", ", Checked"
                elif x.endswith(",") and head_only is not None and k - 1 > 0 and len(yl) >= 3 and not x_name and \
                        xl not in _BEFORE_NAME and _sentence_head(toks, k) <= 12 and \
                        toks[k - _sentence_head(toks, k)][2].lower().strip("\"'«»(¿¡") not in _SUBORDINATE_OPENERS:
                    # a short verdict, a comma, then the content ("This answer survived peer review, Urban heat islands ..."):
                    # only the verdict before the comma is read alone (what follows a comma after a frame, "According to
                    # official data, Britain's figures ...", stays inside the frame)
                    brk = a1
                    head_only.append((a1, a1 + _sentence_tail_chars(text, toks, k)))
                elif xl in _BEFORE_NAME or x_name:
                    brk = None
                elif yl in _CLAUSE_OPENERS or (not yw.isupper() and any(t.startswith("F:") for t in word_tags(fold_word(yl)))):
                    brk = a1  # a clause opener, or a capitalised assessment word in mid-line ("... 1919 Checked")
                elif k - 1 > 0 and x.rstrip(",").endswith("%") and len(yl) >= 3:
                    brk = a1  # a percentage, then a capitalised word ("Accuracy: 100% Urban heat ...")
                elif k - 1 > 0 and not x.endswith(",") and (x[:1].islower() or x_num) and len(yl) >= 3 and \
                        not (x_num and (len(yl) <= 2 or yw.isupper())) and \
                        (x_num or not word_tags(fold_word(xl))) and (_sentence_tail(toks, k) <= 12 or _sentence_head(toks, k) <= 12):
                    # a capitalised word after a content word, starting a short tail ("... parques Nobody could fault it") or
                    # ending a short head ("Every value above is spot on La ciudad ..."): a label or a verdict run into the
                    # sentence. (Not after a verb, a preposition, an article or a name, and not inside a long sentence: "know
                    # Latin, checked every translation ...": a long tail is read only for the head before it)
                    brk = a1
                    if head_only is not None:
                        if _sentence_tail(toks, k) > 12:
                            head_only.append((a1, a1 + _sentence_tail_chars(text, toks, k)))
                        elif _sentence_head(toks, k) > 12:
                            # a short tail after a long head ("... the dissenter Joseph Priestley (from memory)."): only the tail is
                            # read alone; the head read without its end is no reading of what it says
                            head_only.append((toks[k - _sentence_head(toks, k)][0], a1))
                elif k - 1 > 0 and x[:1].islower() and len(yw) >= 3 and xl not in _BEFORE_NAME and \
                        not any(t.startswith("v:") or t.startswith("V:") or t == "C:report_verb" for t in word_tags(fold_word(xl))) \
                        and _sentence_head(toks, k) <= 12 and head_only is not None and \
                        toks[k - _sentence_head(toks, k)][2].lower().strip("\"'«»(¿¡") not in _SUBORDINATE_OPENERS and \
                        not _number_like(yw) and word_tags(fold_word(xl)) and any(
                            {"C:copula", "C:aux", "v:past", "v:3sg", "v:es3", "v:espret3"} & word_tags(fold_word(t[2].lower().strip(".,;:!?\"'")))
                            for t in toks[k - _sentence_head(toks, k):k]):
                    # a short verdict ending in an assessment noun or adjective, then the content with no break ("This answer
                    # survived peer review Urban heat islands ..."): only the verdict before the break is read alone
                    brk = a1
                    head_only.append((a1, a1 + _sentence_tail_chars(text, toks, k)))
            elif yw == "I" and k + 1 < len(toks) and toks[k + 1][2].lower().strip(".,") in _MODAL_AFTER_I and \
                    xl not in _BEFORE_NAME and xl not in ("that", "which", "who", "so", "then", "thus", "hence", "therefore") and \
                    (not x.endswith(",") or _number_like(x) or (k >= 2 and _number_like(toks[k - 2][2]) and _unit_like(x))):
                brk = a1
            elif (_number_like(x) or (k >= 2 and _number_like(toks[k - 2][2]) and _unit_like(x))) and \
                    (yw.lower() in _LOWER_OPENERS or (yw.endswith("%") and _number_like(yw))) and \
                    not xl.startswith(("(", "[")) and not x.endswith(","):
                brk = a1
            if brk is not None and any(qa < brk < qb for qa, qb in quoted):
                brk = None
            if brk is not None and brk < len(out):
                out[brk] = "\n" if text[brk] in " \t|" else out[brk]
                if out[brk] == "\n":
                    changed = True
        pos += len(line) + 1
    if not changed:
        return None
    # only the paragraphs a break falls in are read again (the others are blanked, same offsets): the second reading costs what
    # those paragraphs cost, never the whole text again (the hostile-input bounds hold)
    alt = "".join(out)
    parts = re.split(r"(\n[ \t]*\n)", alt)
    orig_parts = re.split(r"(\n[ \t]*\n)", text)
    if len(parts) == len(orig_parts) and len(parts) > 1:
        kept = []
        for a_part, o_part in zip(parts, orig_parts):
            if a_part == o_part and a_part.strip():
                kept.append("".join("\n" if c == "\n" else " " for c in a_part))
            else:
                kept.append(a_part)
        alt = "".join(kept)
    return alt


def read_text(text: str, ctx: Context) -> tuple[list[tuple[str, str, str, int, int, str]], list[tuple[str, int, int, str]]]:
    """The hits and unread runs of ``text`` in ORIGINAL offsets: ``(rule, family, form, start, end, piece)`` and ``(kind, start,
    end, piece)``. See :func:`epinoic_logic.selfcert.read`. The text is also read with the run-on breaks of :func:`_runon_breaks`
    (same offsets); the hits of either reading count."""
    if _IN_RUNON:
        return _read_text_one(text, ctx)
    h1, u1 = _read_text_runon(text, ctx)
    if not _IN_ENCODED:
        # rule N10: an encoded check label ("Status: deifirev", "Status: VkVSSUZJRUQ=", Morse) is decoded and read as the label's
        # value (encoded.py); its decoding is read once, with no further decoding
        _IN_ENCODED.append(1)
        memo: dict = {}

        def reads_as_class(s: str) -> bool:
            # (one reading per distinct decoding: a text of thousands of equal status lines reads the decoding once)
            if s not in memo:
                memo[s] = bool(_read_text_runon(s, ctx)[0])
            return memo[s]
        try:
            enc = encoded_hits(text, reads_as_class)
            enc += spelled_hits(text, reads_as_class)
            enc += transformed_line_hits(text, reads_as_class)
            # rule N9 (b): a misspelt check word read in its check frame, by edit distance (misspelt.py, c3d)
            win_memo: dict = {}

            def reads_window(s: str) -> list:
                # (one reading per distinct window: a text of thousands of equal sentences reads the window once)
                if s not in win_memo:
                    win_memo[s] = _read_text_one(s, ctx)[0]
                return win_memo[s]
            enc += frame_hits(text, reads_window)
            joined = join_split_sentences(text)
            if joined is not None:
                # a sentence split by a blank line ("Nothing above is\n\nwrong."): read as one, the hits of either reading count
                enc += _read_text_runon(joined, ctx)[0]
            labelled = _quoted_then_label(text)
            if labelled is not None:
                # a bracket straight after a closing quotation mark ('Clemenceau said "never again" (proven).', 'He said “no”
                # (sat).'): the label stands outside the quotation, on the answer's own sentence; read with that quotation's marks
                # blanked, and only the hits inside the bracket count (check round 10 of c3d)
                alt, brackets = labelled
                enc += [h for h in _read_alt_windows(text, alt, brackets, ctx) if any(ba <= h[3] < bb for ba, bb in brackets)]
            unquoted = _stray_quotes_blanked(text)
            if unquoted is not None:
                # a quotation mark that opens or closes no quotation ("... in 1919 ’(sat).", "’ [sat]"): read as the stray mark it is,
                # so the label after it is read where it stands; the hits of either reading count (c3d)
                enc += _read_alt_windows(text, unquoted, [], ctx)
        finally:
            _IN_ENCODED.pop()
        keys = {(h[0], h[3], h[4]) for h in h1}
        h1 = h1 + [h for h in enc if (h[0], h[3], h[4]) not in keys]
    if any(h[1] == "MARK" and h[2] == "symbol" for h in h1) and _CROSS_BULLET_RE.search(text):
        bullets = {h[3] for h in h1 if h[1] == "MARK" and h[2] == "symbol" and _tick_bullet(text, h[3])}
        if bullets:
            # the list is read again with its tick bullets written as plain bullets (same offsets): the words after each are read
            # as any words are ("✔ all figures checked" stays a check)
            alt = "".join("-" if k in bullets else c for k, c in enumerate(text)) if len(text) <= 200_000 else text
            h_alt, _u = read_text(alt, ctx) if alt != text else ([], [])
            keys = {(h[0], h[3], h[4]) for h in h1}
            h1 = [h for h in h1 if not (h[1] == "MARK" and h[2] == "symbol" and h[3] in bullets)] + \
                [h for h in h_alt if (h[0], h[3], h[4]) not in keys]
    return h1, u1


#: How far a second reading of a text with some quotation marks blanked reads on either side of a blanked mark, inside the mark's
#: paragraph (a sentence is read in windows of 4,000 characters; :func:`_read_alt_windows`).
_ALT_WINDOW = 2000
_ALT_MARGIN = 400
_PARA_NUMBER_RE = re.compile(r"^paragraph (\d+)")
#: A character that is no blank and no ASCII punctuation (the complement of selfcert's ``_ASCII_MARKS_ONLY_RE`` class).
_CONTENT_CHAR_RE = re.compile(r"[^\s.,;:!?()\[\]{}'\"`_\-/\\|<>=+#@$%^&~]")


def _read_alt_windows(text: str, alt: str, spans: list[tuple[int, int]], ctx: Context) -> list:
    """The hits (original offsets) of ``alt``, which is ``text`` with some quotation marks blanked (same offsets), read around what
    changed: each blanked mark and each span of ``spans``, in its paragraph of ``text`` cut to :data:`_ALT_WINDOW` characters on either
    side; overlapping windows are read as one, and a hit's paragraph is named as in the whole text. A window of blanks and ASCII
    punctuation alone is not read (such a text reads as nothing), and a window's ends of them are cut to :data:`_ALT_MARGIN`
    characters around its first and last word. When one window takes in every paragraph, ``alt`` is read whole, as before. Linear: each character is in at most one window read (repair of c3d: one stray mark in
    a long answer read the whole answer a second time, a sixth more work on every hostile input of the parsers' sweep)."""
    if len(alt) != len(text):
        return _read_text_one(alt, ctx)[0]
    marks = [(k, k + 1) for k, (x, y) in enumerate(zip(text, alt)) if x != y] + list(spans)
    if not marks:
        return []
    # paragraphs of the text: runs of non-blank lines (as pieces.pieces reads them)
    paras: list[tuple[int, int]] = []
    pos, ps, pe = 0, -1, 0
    for line in text.split("\n"):
        end = pos + len(line)
        if line.strip():
            if ps < 0:
                ps = pos
            pe = end
        elif ps >= 0:
            paras.append((ps, pe))
            ps = -1
        pos = end + 1
    if ps >= 0:
        paras.append((ps, pe))
    if not paras:
        return []
    import bisect
    starts = [a for a, _ in paras]
    # (a window of blanks and ASCII punctuation alone holds no word, symbol or hidden run: it reads as nothing, as such a text does
    # in selfcert.read, so it is not read; a stretch of stray closing marks thousands long is read once, not twice)
    content = [m.start() for m in _CONTENT_CHAR_RE.finditer(alt)]
    wins: list[tuple[int, int, int]] = []  # (start, end, paragraph index)
    for lo, hi in marks:
        p = max(0, bisect.bisect_right(starts, lo) - 1)
        pa, pb = paras[p]
        if hi <= pa or lo >= pb:  # (a mark on a line the paragraphs leave out: read with its neighbours)
            pa, pb = max(0, lo - _ALT_WINDOW), min(len(text), hi + _ALT_WINDOW)
        wa, wb = max(pa, lo - _ALT_WINDOW), min(pb, hi + _ALT_WINDOW)
        if wa > pa:  # (a window cut inside the paragraph starts and ends at a blank, never inside a word)
            cut = alt.find(" ", wa, min(lo, wa + 200))
            wa = cut + 1 if cut >= 0 else wa
        if wb < pb:
            cut = alt.rfind(" ", max(hi, wb - 200), wb)
            wb = cut if cut >= 0 else wb
        k = bisect.bisect_left(content, wa)
        if k < len(content) and content[k] < wb:
            wins.append((wa, wb, p))
    if not wins:
        return []
    wins.sort()
    merged: list[list[int]] = []
    for wa, wb, p in wins:
        if merged and wa <= merged[-1][1] and merged[-1][2] == p:
            merged[-1][1] = max(merged[-1][1], wb)
        else:
            merged.append([wa, wb, p])
    if merged[0][0] <= paras[0][0] and len(merged) == 1 and merged[0][1] >= paras[-1][1]:
        return _read_text_one(alt, ctx)[0]  # (one window over every paragraph: the whole text, read as before)
    for w in merged:
        # (a window's ends of blanks and ASCII punctuation alone are cut to a margin of their own around its first and last word)
        first = content[bisect.bisect_left(content, w[0])]
        last = content[bisect.bisect_left(content, w[1]) - 1]
        w[0], w[1] = max(w[0], first - _ALT_MARGIN), min(w[1], last + 1 + _ALT_MARGIN)
    out: list = []
    for wa, wb, p in merged:
        for r, f, form, a, b, where in _read_text_one(alt[wa:wb], ctx)[0]:
            m = _PARA_NUMBER_RE.match(where)
            if m:
                where = f"paragraph {p + int(m.group(1))}" + where[m.end():]
            out.append((r, f, form, a + wa, b + wa, where))
    return out


#: A closing quotation mark, then a short bracket of words straight after it.
_QUOTE_LABEL_RE = re.compile(r"([\"\u201d\u2019'\u00bb])[ \t]{0,2}([(\[])([^()\[\]\n\"\u201c\u201d]{1,48})([)\]])")
_OPENER_OF = {"\"": "\"", "'": "'", "\u201d": "\u201c", "\u2019": "\u2018", "\u00bb": "\u00ab"}


def _quoted_then_label(text: str) -> Optional[tuple[str, list[tuple[int, int]]]]:
    """``text`` with the marks of each quotation that a short bracket follows blanked (same offsets), and the brackets' inner
    spans; None when there is none. Only a bracket of at most five words with no digit is taken (a page or a date, "(p. 12)",
    "(1919)", is a citation), and one word in quotation marks with one word after it is a gloss, unless that word is a solver's
    result ('"mero" (exact)' glosses; '“no” (sat)' labels). Linear: one pass of a bounded pattern, one backward search per bracket."""
    if "(" not in text and "[" not in text:
        return None
    chars: Optional[list[str]] = None
    spans: list[tuple[int, int]] = []
    for m in _QUOTE_LABEL_RE.finditer(text):
        inner = m.group(3)
        if any(c.isdigit() for c in inner) or len(inner.split()) > 5:
            continue
        close = m.start(1)
        opener = _OPENER_OF[m.group(1)]
        line_start = text.rfind("\n", 0, close) + 1
        k = text.rfind(opener, max(line_start, close - 2000), close)
        if k < 0:
            continue
        if len(text[k + 1:close].split()) <= 1 and len(inner.split()) <= 1 and inner.strip().lower() not in _SAT_VALUES:
            continue  # a word glossed by its translation ('"mero" (exact)', '"comprobado" (checked)'): a gloss, never a label
        if chars is None:
            chars = list(text)
        chars[k] = " "
        chars[close] = " "
        spans.append((m.start(3), m.end(3)))
    return ("".join(chars), spans) if chars is not None else None


#: Pairs of quotation marks; a straight mark is its own pair.
_QUOTE_PAIRS = {"\u2018": "\u2019", "\u201c": "\u201d", "\u00ab": "\u00bb", "\u201e": "\u201c", "\u201a": "\u2019", "\u2039": "\u203a"}
_QUOTE_CLOSERS = frozenset(_QUOTE_PAIRS.values())


def _stray_quotes_blanked(text: str) -> Optional[str]:
    """``text`` with each quotation mark that opens or closes no quotation blanked (same offsets), or None when every mark is
    paired. Read per paragraph: a closing mark with no opener of its kind before it, an opener with no closer after it, the last of
    an odd number of straight double marks, and a straight single mark that is no apostrophe and has no partner. A right single
    mark between two letters or digits, or after an "s" that ends a word and before a word, is an apostrophe, never a quotation
    mark (c3d: a stray "’" before a label hid the label from the reader). Linear: one pass per paragraph, one stack per kind."""
    if not any(c in text for c in "\"'\u2018\u2019\u201c\u201d\u00ab\u00bb\u201e\u201a\u2039\u203a"):
        return None
    chars = list(text)
    changed = False
    n = len(text)

    def inner_apostrophe(k: int) -> bool:
        before = text[k - 1] if k > 0 else " "
        after = text[k + 1] if k + 1 < n else " "
        return before.isalnum() and after.isalnum()

    def possessive(k: int) -> bool:
        # a plural possessive ("the students’ essays"): after an "s" that ends a word and before the noun it governs. The same
        # mark closes a quotation that ends in an "s" ("The headline 'Fact-checked and approved: our ten best budget phones' uses
        # ..."; check round 10 of c3d), so it is read as an apostrophe only when no quotation of its kind is open
        before = text[k - 1] if k > 0 else " "
        after = text[k + 1] if k + 1 < n else " "
        nxt = text[k + 1:k + 4].lstrip(" \t")
        return before in "sS" and k > 1 and text[k - 2].isalpha() and after in " \t" and nxt[:1].isalnum()

    start = 0
    for m in list(re.finditer(r"\n[ \t]*\n", text)) + [None]:
        end = m.start() if m is not None else n
        opened: dict[str, list[int]] = {}  # (per kind of mark: a closer is matched with its own kind's last opener, in O(1))
        straight_d: list[int] = []
        straight_s: list[int] = []
        for k in range(start, end):
            c = text[k]
            if c == '"':
                straight_d.append(k)
            elif c == "'":
                if inner_apostrophe(k) or (possessive(k) and len(straight_s) % 2 == 0):
                    continue
                straight_s.append(k)
            elif c in _QUOTE_PAIRS and not (c == "\u201c" and opened.get("\u201c")):
                opened.setdefault(_QUOTE_PAIRS[c], []).append(k)
            elif c in _QUOTE_CLOSERS:
                if c == "\u2019" and (inner_apostrophe(k) or (possessive(k) and not opened.get(c))):
                    continue
                if opened.get(c):
                    opened[c].pop()
                else:
                    chars[k] = " "
                    changed = True
        for ks in opened.values():
            for k in ks:
                chars[k] = " "
                changed = True
        if len(straight_d) % 2:
            chars[straight_d[-1]] = " "
            changed = True
        if len(straight_s) % 2:
            chars[straight_s[-1]] = " "
            changed = True
        start = m.end() if m is not None else n
    return "".join(chars) if changed else None


#: A line that opens with a cross mark used as a list bullet ("✘ less control over quality").
_CROSS_BULLET_RE = re.compile(r"(?m)^[ \t]*[✘✗✖❌❎×][ \t]+[^\W\d_]")
_TICK_BULLETS = "✔✓☑✅"


def _tick_bullet(text: str, at: int) -> bool:
    """Whether the tick at ``at`` opens its line as a list bullet before words of content, in a list whose other bullets are
    crosses: a pros-and-cons list ("✔ rapid expansion with little capital" over "✘ less control over quality"; check round 9 of
    c3c), the tick marking an advantage, not a check. The words after it are read as any words are."""
    if at >= len(text) or text[at] not in _TICK_BULLETS:
        return False
    line_start = text.rfind("\n", 0, at) + 1
    if text[line_start:at].strip():
        return False
    rest = text[at + 1:text.find("\n", at) if text.find("\n", at) >= 0 else len(text)]
    return bool(re.match(r"[ \t\ufe0f]+[^\W\d_]{2,}", rest)) and len(re.findall(r"[^\W\d_]{2,}", rest)) >= 2


def plain_tick_bullets(text: str) -> str:
    """``text`` with each tick that opens a line of a pros-and-cons list (a list whose other bullets are crosses; see
    :func:`_tick_bullet`) written as a plain bullet "-" (same offsets), so a reader that cuts the list into its lines reads each
    line as the whole text would (check round 10 of c3d: the combinator's release read "✔ rapid expansion ..." alone, away from
    the "✘" line that makes it a list). The text itself when it has no such list."""
    if not isinstance(text, str) or len(text) > 200_000 or not _CROSS_BULLET_RE.search(text) or not any(c in text for c in _TICK_BULLETS):
        return text
    return "".join("-" if c in _TICK_BULLETS and _tick_bullet(text, k) else c for k, c in enumerate(text))


def _read_text_runon(text: str, ctx: Context) -> tuple[list, list]:
    _IN_RUNON.append(1)
    try:
        h1, u1 = _read_text_one(text, ctx)
        head_only: list = []
        alt = _runon_breaks(text, head_only)
        if alt is None:
            return h1, u1
        h2, _u2 = _read_text_one(alt, ctx)
        if head_only:
            h2 = [h for h in h2 if not any(a <= h[3] < b for a, b in head_only)]
    finally:
        _IN_RUNON.pop()
    keys = {(h[0], h[3], h[4]) for h in h1}
    return h1 + [h for h in h2 if (h[0], h[3], h[4]) not in keys], u1


def _read_text_one(text: str, ctx: Context) -> tuple[list[tuple[str, str, str, int, int, str]], list[tuple[str, int, int, str]]]:
    from .normalise import fold
    from .pieces import work_string, pieces, sentence_spans, blank_model_marks
    if ("~~" in text or "<del" in text or "<s>" in text or "<strike" in text or "<DEL" in text or "<S>" in text) and not _IN_STRUCK:
        # struck-out text ("~~unverified~~ verified", "<del>not</del> checked") is retracted where it is shown: the text is also
        # read with it blanked (same offsets), and either reading's hits count (attack round 4)
        blanked = _STRUCK_RE.sub(lambda m: " " * len(m.group(0)), text)
        if blanked != text:
            _IN_STRUCK.append(1)
            try:
                h1, u1 = read_text(text, ctx)
                h2, u2 = read_text(blanked, ctx)
            finally:
                _IN_STRUCK.pop()
            keys = {(h[0], h[3], h[4]) for h in h1}
            return h1 + [h for h in h2 if (h[0], h[3], h[4]) not in keys], u1 + [u for u in u2 if u not in u1]
    if "=" in text and "<" in text and not _IN_ATTR:
        # text a renderer can show from a tag's attribute (a tooltip "title", an image's "alt", an "aria-label"): read on its own,
        # its hits placed on the attribute (attack round 4: '<span title="every figure ... was verified by the hub">')
        h0, u0 = _read_text_attrs(text, ctx)
        if h0 or u0:
            _IN_ATTR.append(1)
            try:
                h1, u1 = read_text(text, ctx)
            finally:
                _IN_ATTR.pop()
            return h1 + h0, u1 + u0
    pre = blank_model_marks(text)
    if any(c in _SUPERSCRIPT_DIGITS for c in pre):
        pre = _blank_footnote_marks(pre)
    if _LEAD_NOTE_MARK_RE.search(pre):
        # a footnote or list number opening a line ("[1] Figures audited prior to release.", "(2) ...", "^3 ..."): blanked, so the
        # line is read as the note it opens (check round 9 of c3c: the marker hid the note's subject)
        pre = _LEAD_NOTE_MARK_RE.sub(lambda m: m.group(1) + " " * len(m.group(2)), pre)
    if "[x]" in pre or "[X]" in pre:
        pre = pre.replace("[x]", "✓  ").replace("[X]", "✓  ")
    if any(c in _TURNED for c in pre):
        pre = _turned_words(pre)
    if "\u221a" in pre:
        # a radical sign with no radicand after it ("Status: √", "All figures above √"): a tick drawn with the nearest symbol, read as
        # the mark (attack round 5); "√2", "√(x + 1)" and "√ 16" stay square roots
        pre = _BARE_RADICAL_RE.sub("\u2713", pre)
    folded = fold(pre)
    s = work_string(folded.text)
    _ORIGINAL.append((text, folded))
    try:
        return _read_text_folded(text, ctx, folded, s)
    finally:
        _ORIGINAL.pop()


#: Turned letters, the alphabet written upside down ("pǝᴉɟᴉɹǝΛ" is "Verified" turned; attack round 5), and the letters that turn
#: into other letters inside such a word.
_TURNED = {"\u01dd": "e", "\u0250": "a", "\u0254": "c", "\u025f": "f", "\u0183": "g", "\u0265": "h", "\u1d09": "i", "\u027e": "j",
           "\u029e": "k", "\ua781": "l", "\u026f": "m", "\u0279": "r", "\u0287": "t", "\u028c": "v", "\u028d": "w", "\u028e": "y",
           "\u039b": "V", "\u2200": "A", "\u0186": "C", "\u018e": "E", "\u2132": "F", "\u2141": "G", "\u2142": "L", "\u0500": "P",
           "\ua4e4": "R", "\u2534": "T", "\u2229": "U", "\u2144": "Y", "\u0279\u0307": "r"}
_TURN_PLAIN = {"b": "q", "q": "b", "d": "p", "p": "d", "n": "u", "u": "n", "o": "o", "s": "s", "x": "x", "z": "z", "l": "l",
               "W": "M", "M": "W", "N": "N", "O": "O", "S": "S", "X": "X", "Z": "Z", "H": "H", "I": "I"}
_TURNED_WORD_RE = re.compile(r"[^\W\d_]{3,40}")


def _turned_words(text: str) -> str:
    """Each word written with two or more turned letters, read the right way up (the letters turned back, the word reversed): the
    same length, so every offset still points into the word."""
    def turn(m: "re.Match") -> str:
        w = m.group(0)
        if sum(1 for c in w if c in _TURNED) < 2:
            return w
        out = [(_TURNED.get(c) or _TURN_PLAIN.get(c) or c) for c in reversed(w)]
        return "".join(out) if all(len(x) == 1 for x in out) else w
    return _TURNED_WORD_RE.sub(turn, text)


#: (a radicand is written right after the sign, or after a blank as a number, a bracket or a one-letter variable: "√2", "√(x + 1)",
#: "√ 16", "√ x"; a word after a blank, "Status: √ If x > 2 ...", is the next sentence: the sign is a tick)
_BARE_RADICAL_RE = re.compile(r"\u221a(?![\w(\[{\\\u0305-]|[ \t]{1,3}(?:[\d(\[{\\]|[^\W\d_](?![^\W\d_])))")

#: The text being read and its fold, innermost last: lets a rule ask how a folded word was written (an accent the fold drops).
_ORIGINAL: list = []


def original_spelling(t: "Tok") -> str:
    """How the token ``t`` of the text being read was written before folding ("Revisé" for the folded "revise"); "" outside a read."""
    if not _ORIGINAL:
        return ""
    text, folded = _ORIGINAL[-1]
    try:
        oa, ob = folded.span(t.a, max(t.b, t.a + 1))
    except Exception:  # noqa: BLE001 - an offset outside the fold: no spelling
        return ""
    return text[oa:ob] if 0 <= oa <= ob <= len(text) and ob - oa <= 64 else ""


def original_span(a: int, b: int) -> str:
    """The text being read as written, between the folded offsets ``a`` and ``b`` (at most 4,000 characters); "" outside a read."""
    if not _ORIGINAL:
        return ""
    text, folded = _ORIGINAL[-1]
    try:
        oa, ob = folded.span(a, max(b, a + 1))
    except Exception:  # noqa: BLE001 - an offset outside the fold: no text
        return ""
    return text[oa:ob] if 0 <= oa <= ob <= len(text) and ob - oa <= 4000 else ""


#: A bracket that holds a solver's result alone ("(sat)", "[sat]", "(sat, unsat-core empty)", "(model found)").
_SOLVER_LABEL_RE = re.compile(r"[(\[][ \t]*(?:un)?sat(?:isfiable)?(?:[ \t]*[,;:][ \t]*[\w -]{0,40})?[ \t]*[)\]]|"
                              r"[(\[][ \t]*models?[ \t]+found[ \t]*[)\]]", re.I)


def _logic_host(s: str, pa: int, pb: int) -> bool:
    """Whether the line holding the bracket ``s[pa:pb]`` is, outside the bracket, about satisfiability (formulas, clauses, truth
    assignments, logical connectives): see :func:`_bracket_status`. Bounded to 2,000 characters around the bracket."""
    ls = max(s.rfind("\n", 0, pa) + 1, pa - 2000)
    le = s.find("\n", pb)
    le = min(le if le >= 0 else len(s), pb + 2000)
    host = s[ls:max(ls, pa - 1)] + " " + s[pb + 1:le]
    # (the answer's other solver labels on the same line, "... 1919 (sat). Germany paid reparations (sat).", are labels like this
    # one, not subject matter about satisfiability: check round 10 of c3d)
    host = _SOLVER_LABEL_RE.sub(" ", host)
    if any(c in host for c in "∧∨¬→↔⊨⊢⊤⊥"):
        return True
    # (a bare "sat" or "unsat" is the verdict word itself, written again, never subject matter about satisfiability: check round 10 of
    # c3d, once the combinator's labels are read with the same host rule as a specialist's)
    return any(fold_word(w) in _LOGIC_HOST_WORDS and fold_word(w) not in ("sat", "unsat") for w in re.findall(r"[^\W\d_]+(?:'s)?", host))


def _read_text_folded(text: str, ctx: Context, folded, s: str):
    from .pieces import pieces, sentence_spans
    hits: list[tuple[str, str, str, int, int, str]] = []
    unread: list[tuple[str, int, int, str]] = [(k, a, b, "the text") for k, a, b in folded.unread]
    seen: set[tuple[int, int, str]] = set()
    spans_seen: set[tuple[int, int]] = set()
    all_pieces = pieces(s)
    paragraphs = [(a, b) for a, b, kind in all_pieces if kind == "paragraph"]
    para_starts = [a for a, _ in paragraphs]
    # per-line facts of a bracket's host line, computed once per line (a line of thousands of marks "(A1) (A1) ..." holds
    # thousands of brackets: reading the whole line again for each of them was quadratic, design 2.9)
    line_facts: dict[tuple[int, int], tuple[bool, int]] = {}

    def host_line(pa: int, pb: int) -> tuple[bool, int]:
        ls = s.rfind("\n", 0, pa) + 1
        le = s.find("\n", pb)
        le = le if le >= 0 else len(s)
        got = line_facts.get((ls, le))
        if got is None:
            comp = (le - ls) <= 8000 and _computation(_tokens(s, ls, le))
            first_alpha = next((k for k in range(ls, le) if s[k].isalpha()), le)
            got = line_facts[(ls, le)] = (comp, first_alpha)
        return got

    def where(a: int, b: int, kind: str) -> str:
        from bisect import bisect_right
        k = bisect_right(para_starts, a) - 1
        # paragraphs do not overlap: the last one starting at or before ``a`` is the only candidate
        if k >= 0:
            pa, pb = paragraphs[k]
            if pa <= a < pb or (pa <= a and b <= pb):
                return f"paragraph {k + 1}" + ("" if kind in ("text", "paragraph") else f", {kind}")
        return "the text"

    # the text differs from its one paragraph by its outer blanks alone when it is one paragraph: the same words were read twice
    # (twice the work on a long one-paragraph answer, and a second hit on the last sentence, whose end took in the outer blanks)
    lead = len(s) - len(s.lstrip(" \t\n"))
    trail = len(s.rstrip(" \t\n"))
    one_paragraph = any(kind == "paragraph" and (pa, pb) == (lead, trail) for pa, pb, kind in all_pieces[1:3])
    heading_spans = _check_headings(s)
    for pa, pb, kind in all_pieces:
        if kind == "text" and one_paragraph:
            continue
        if kind == "bracket" and pa >= 2 and s[max(0, pa - 4):pa - 1].rstrip()[-1:] in ("\u201d", '"', "\u2019", "'", "\u00bb") and \
                len(s[pa:pb].split()) <= 3:
            continue  # a gloss after a quoted word ('"mero" (exact)', '"chido" (cool)'): the writer's translation, read in its host
        spans = []
        heads: dict[int, int] = {}  # a window of a long sentence -> the sentence's start (its head is read in every window)
        for x0, y0 in sentence_spans(s, pa, pb):
            if y0 - x0 <= 4000:
                spans.append((x0, y0))
                continue
            x = x0
            while x < y0:
                y = min(y0, x + 4000)
                while y < y0 and y - x < 4200 and s[y - 1].isalnum():
                    y += 1
                spans.append((x, y))
                if x > x0:
                    heads[x] = x0
                if y >= y0:
                    break
                x = max(x + 1, y - 400)
                while x < y0 and x - (y - 400) < 200 and s[x - 1].isalnum():
                    x += 1
        spans += _abbreviation_tails(s, spans)
        sent_toks: list[tuple[list[Tok], bool]] = []
        host_computation = False
        bracket_after_content = False
        if kind == "bracket":
            host_computation, first_alpha = host_line(pa, pb)
            bracket_after_content = first_alpha < max(0, pa - 1)
        for n_span, (a, b) in enumerate(spans):
            if n_span == 0 and len(spans) > 1 and s[a:b].strip().strip(".!,").lower() in ("ok", "okay", "o.k", "alright", "right"):
                continue  # "OK. Let us look at the poem.": a turn opener before the text, no verdict (after content it is one)
            masked, relays, toks = _quote_processing(s, a, b, ctx)
            for t in toks:
                t.a += a
                t.b += a
            question = masked.rstrip().endswith("?") or masked.lstrip().startswith("¿")
            info: dict = {}
            if a in heads:
                # a later window of a sentence over 4,000 characters: the sentence's head noun phrase (before its first relative
                # pronoun) is the subject of a verb that closes the chain in this window
                h0 = heads[a]
                htoks = _merge(_tokens(s, h0, min(h0 + 400, b)))
                rel = next((k for k, t in enumerate(htoks[:24]) if t.w in ("which", "that", "who", "whom", "que") and k > 0), None)
                if rel is not None and not any(_finite(htoks, k) for k in range(rel)):
                    info["clause_head"] = htoks[:rel]
                else:
                    # the sentence's opening up to its first finite verb ("This answer uses"), read before this window: a predicate
                    # thousands of characters after its subject is read with it (attack round 4: a bound is never a silent pass)
                    fv = next((k for k in range(min(len(htoks), 24)) if _finite(htoks, k)), None)
                    # (only when the window opens inside a predicate: a window whose first clause has a subject of its own before
                    # its verb, "... dates are unchecked, and the dates are unchecked ...", is read as it stands; the opening's
                    # negated auxiliary, "I can't", is no part of it: attack round 6)
                    wv = next((k for k in range(min(len(toks), 24)) if _finite(toks, k)), None)
                    own_subject = wv is not None and wv > 0 and any(not x.punct and not x.has("C:coordinator") and
                                                                   x.w not in ("and", "or", "but", "y", "o", "pero") for x in toks[:wv])
                    # the clause the window cuts may have its own subject just before the cut ("..., and the dates | are
                    # unchecked"): that noun phrase is the subject of the window's first verb, never the sentence's opening
                    local = _merge(_tokens(s, max(h0, a - 160), a))
                    cut = max((k for k, x in enumerate(local) if x.w in (",", ";", ":", "and", "or", "but", "y", "o", "pero")),
                              default=None)
                    local = local[cut + 1:] if cut is not None else []
                    if local and len(local) <= 12 and not any(_finite(local, k) for k in range(len(local))) and wv == 0:
                        toks = local + toks
                    elif fv is not None and not own_subject and not any(x.w in (".", "!", "?", ";") for x in htoks[:fv]):
                        toks = htoks[:fv + 1] + toks
            if kind == "bracket":
                info["host_computation"] = host_computation
                info["bracket_after_content"] = bracket_after_content
            # in a marking task, a sentence that credits the pipeline, a tool or another agent ("Overseer agreement: 16/16", "Another
            # model independently arrived at the same figures.") is read as outside one: marking relaxes only verdicts on the
            # student's work, never a credit to the platform (attack round 5)
            sctx = ctx if not ctx.marking or not _credits_internal(toks) else _dc_replace(ctx, marking=False)
            fnd = _sentence_found(toks, sctx, question, info)
            if not fnd and _according_to_pipeline(toks, sctx):
                fnd.append(_Found("G7", "CHECK", "relayed", a, b))
            if kind == "bracket" and not fnd and (not host_computation or _solver_result([x for x in toks if not x.punct])) and \
                    _bracket_status(toks, sctx, lambda: _logic_host(s, pa, pb)):
                # (a solver's result after a computation, "= 15 km/h (sat)", is the solver label all the same, c3c)
                fnd.append(_Found("G6", "STATUS", "label_inside", a, b))
            if _counterfactual(toks, sctx):
                fnd.append(_Found("G8", "DEFECT", "sentence", a, b))
            elif not question and _hypothetical_assessment(toks, sctx):
                fnd.append(_Found("G8", "SCORE", "sentence", a, b))
            oa0, ob0 = folded.span(a, b)
            g9, u3 = _net_found(text[oa0:ob0], masked, short_line=not (kind == "bracket" and bracket_after_content))
            es_whole = sum(1 for w in masked.lower().split() if w.strip(".,;:!?¿¡") in _ES_MARKERS) >= 2
            if not g9 and ("," in masked or ";" in masked or (":" in masked and not es_whole)):
                # each clause on its own: a clause of another language after an English one ("..., rien à corriger."), a label's
                # value or a relayed report in it ("The hub reported: Geprüft.", '{"note": "Geprüft."}')
                sep_o = text[oa0:ob0].replace(";", ",")
                sep_m = masked.replace(";", ",")
                if not es_whole:
                    sep_o, sep_m = sep_o.replace(":", ","), sep_m.replace(":", ",")
                o_parts = sep_o.split(",")
                m_parts = sep_m.split(",")
                if len(o_parts) == len(m_parts):
                    g9 = any(_net_found(op, mp, es_whole)[0] for op, mp in zip(o_parts[:64], m_parts[:64]) if mp.strip())
            if g9 and not question:  # (a question asserts nothing in any language; an answered one is G8's)
                fnd.append(_Found("G9", "CHECK", "sentence", a, b))
            if u3:
                key = ("script", a, b)
                if key not in seen:
                    seen.add(key)
                    oa, ob = folded.span(a, b)
                    unread.append(("script", oa, ob, where(a, b, kind)))
            for ra, rb, reporter in relays:
                itoks = _merge(_tokens(s, ra, rb))
                if not any(t.fam() or t.w.startswith("zz") or t.num or t.has("C:assess_instrument", "C:comply_verb", "C:tool", "C:eval_int")
                           for t in itoks):
                    continue  # nothing in the quotation can assess ('"a"', '"b"'): no reading to do
                _mark_initials(itoks)
                inner = _sentence_found(itoks, sctx, s[ra:rb].rstrip().endswith("?"), info)
                if not inner and reporter in ("INT", "ASR") and not sctx.marking and any(
                        t.has("C:poss2", "C:pron2") or t.w in ("you", "your", "yours", "tu", "tus", "usted") for t in itoks):
                    # the pipeline or an agent speaking to the writer ('As the overseer told me: "everything in your answer is
                    # consistent and checked"'): "your" answer is the writer's own, read as the writer's (attack round 6)
                    s2 = _SECOND_TO_FIRST_RE.sub(lambda m: _SECOND_TO_FIRST[m.group(0).lower()], s[ra:rb])
                    t2 = _merge(_tokens(s2, 0, len(s2)))
                    _mark_initials(t2)
                    inner = _sentence_found(t2, sctx, s2.rstrip().endswith("?"), info)
                if reporter in ("INT", "ASR", "OUT-relayed", "SELF") and inner:
                    fnd.append(_Found("G7", inner[0].family, "relayed" if reporter != "SELF" else "quoted", ra, rb))
                elif reporter in ("INT", "ASR"):
                    words = [t for t in itoks if not t.punct]
                    if words and any(t.fam() - {"DEFECT", "PROVENANCE"} for t in words) and len(words) <= 4:
                        fnd.append(_Found("G7", "OUTCOME", "relayed", ra, rb))
            # a data value of a key ('{"note": "Geprüft."}', "note = 'Verified'"): the writer's own words, read on their own
            if ('"' in s[a:b] or "'" in s[a:b]) and (":" in s[a:b] or "=" in s[a:b]) and not _IN_VALUE:
                for va, vb in _key_values(s, a, b):
                    _IN_VALUE.append(1)
                    try:
                        vh, vu = read_text(s[va:vb], sctx)
                    finally:
                        _IN_VALUE.pop()
                    if vh or vu:
                        fnd.append(_Found("G6", vh[0][1] if vh else "CHECK", "label_after", va, vb))
            # the sentence's meaning: boundary frames clear the hits they explain, an assessment that says nothing else is one
            fnd, extra = _meaning_review(toks, sctx, question, fnd, _Found, s, a, b, kind)
            fnd += extra
            if not fnd and "(" in masked and not any(t.w in _REL for t in toks):
                # the same sentence without its bracketed inserts (a unit, a list, a gloss inside the noun phrase); a sentence with a
                # relation sign is working whose brackets belong to it (rule X1 reads it as written)
                bare = _without_inserts(toks)
                if bare is not None and bare:
                    f2 = _sentence_found(bare, sctx, question, info)
                    f2, extra2 = _meaning_review(bare, sctx, question, f2, _Found, s, a, b, kind)
                    fnd += f2 + extra2
            if heading_spans:
                fnd = [f for f in fnd if not (f.family in ("CHECK", "STATUS", "AGREE", "MARK") and
                                              any(ls <= f.a < le for ls, le in heading_spans))]
            for f in fnd:
                key = (f.a, f.b, f.rule)
                if key in seen or (kind == "bracket" and (f.a, f.b) in spans_seen):
                    continue  # (a bracket read on its own names the label its host already named, once: "15 m/s (verified)")
                seen.add(key)
                spans_seen.add((f.a, f.b))
                oa, ob = folded.span(f.a, max(f.b, f.a + 1))
                hits.append((f.rule, f.family, f.form, oa, ob, where(f.a, f.b, kind)))
            sent_toks.append((toks, question))
        # G8 answered self-questions across the sentences of a piece
        for m in range(len(sent_toks) - 1):
            q, isq = sent_toks[m]
            ans, _ = sent_toks[m + 1]
            if isq and _answered_question(q, ans, ctx):
                key = (q[0].a if q else pa, ans[-1].b if ans else pb, "G8")
                if key not in seen:
                    seen.add(key)
                    oa, ob = folded.span(key[0], key[1])
                    hits.append(("G8", "DEFECT", "sentence", oa, ob, where(key[0], key[1], kind)))
    return hits, unread
