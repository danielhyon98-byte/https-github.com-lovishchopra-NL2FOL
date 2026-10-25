"""Whether a source states a figure as a fact, what it states about it, and whether the fact is about the symbols an
encoding left open.

Coverage (:mod:`.coverage`) withholds a counterexample (the engine's E110 and E111) only on source-linked evidence that
a source ASSERTS what the encoding left open. Mentioning a figure is not asserting it: "If n equals 17, b holds",
"Is n equal to 17?", "n could be 17", "b holds exactly when n is 17", "n is not 17", "for any integer y", "Hypothesis: n is
17" and "n = 17 ⇒ b" all mention a figure and assert nothing about it. The decision rests on the source's grammar, not on
whether a numeral occurs. A deterministic reader (nothing is executed) answers three questions for a figure at a span of
a source text:

1. **Is it asserted?** (:func:`assertion_at`) Only when its clause states it as a fact: declarative, positive,
   unconditional and the writer's own. The reader decides it in two halves, and both must agree.

   First, no construction it knows to suspend an assertion governs the figure. A clause states no fact about its
   figures when it is

   * a question: the sentence ends with "?", or opens with an inverted auxiliary ("Is n 17 ...", "Could n ...", "Had n
     been ..."), or the clause holds "whether"; or a claim put forward to be tested ("to be tested", "to check", "true or
     false", "claim to test");
   * an instruction or a supposition that opens the sentence ("Define ...", "Let ...", "Suppose ...", "Assume ...",
     "Consider ...", "Use ...", "Show ...", "Find ..."), or a sentence that continues the condition or supposition of the
     one before ("Suppose b holds. Then n = 17.");
   * a condition: "if" (with "only if", "even if", "as if"), "unless", "provided (that)", "as/so long as", "in case",
     "in the event", "on condition", "whenever", "otherwise", "necessary", "sufficient", a case restriction ("for n =
     17", "with x = 5", "in cases where", "in the scenario where"), dependence or implication in the present tense
     ("depends on", "subject to", "implies", "guarantees", "requires", "leads to"), purpose ("so that", "in order to"),
     "when" or "once" read as a condition (below), and a symbolic implication ("⇒", "→", "⟹", "⇐", "←", "⊃", "⊢", "=>",
     "->", "<-");
   * a supposition, a hypothesis, an example or a definition anywhere in the clause: "suppose", "assume", "presume",
     "imagine", "hypothesis", "hypothetical", "conjecture", "posit", "postulate", "let", "granting that", "in theory",
     "taking / treating n as 17", "for example", "e.g.", "such as", "define", "denote", "stand for", "means", "is called",
     "we say", "refers to", ":=", "≡";
   * a possibility, an obligation, an intention or a hedge: "could", "might", "may", "can", "would", "should", "must",
     "ought", "has to", "needs to", "is to be", "want", "aim", "plan", "hope", "expect", "target", "goal", "possibly",
     "perhaps", "probably", "likely", "possible", "presumably", "supposedly", "apparently", "seemingly", "it seems", "it
     appears", "seems to", "unclear", "unknown", "unconfirmed", "need not";
   * an attribution: "say", "said", "argue", "claim", "believe", "think", "suggest", "guess", "suspect", "reckon",
     "report", "according to", "rumour", "legend has it", "word is", "the story goes" (the writer reports a view, and does
     not assert it);
   * a negation: "not", "-n't", "never", "neither", "nor", "none", "nothing", "nobody", "no" (and "No" opening a
     clause), "fail to", "rather than", "instead of", "false", "¬" ("nothing else", "none other" and "no other" stress
     the figure, and negate nothing);
   * a quantification over values or occasions: "for any / all / every / each / some", "any", "every", "each of",
     "arbitrary", "whatever", "whichever", "regardless", "no matter", "unconstrained", "unspecified", "∀", "∃",
     "sometimes", "often", "usually", "typically", "generally", "in some / many / most cases", "on average", "as a rule";
   * a disjunction: "or", "either", "∨";

   and a single figure states no fact of its own when it is negated or excluded where it stands ("≠ 17", "other than
   17", "except 17") or in its own predicate ("x is not 17", "isn't 17", "was never 17", "does not equal 17"; a bound
   phrase such as "not more than 17" states a bound instead), or is one end of a range or one option of a disjunction ("between 15 and 17", "2 to 3 per cent",
   "17 or 18"); "from $4.03 to $2.80" is a change, both of whose figures are stated, and the numeral of a cue that states
   a precision is no end of a range ("x is 0.33 to 2 decimal places" states 0.33).

   Second, the reader must POSITIVELY recognise the clause as a statement (:func:`_unrecognised`); anything it does
   not recognise is no assertion, so uncertainty never withholds a verdict. The clause is recognised when every symbol
   in it is one an assertion may hold (letters, figures, units, the signs of a comparison or a sum; no logical arrow, no
   "∧", "|", "==", "?"); every closed-class word in it is one an assertion may hold (no quantifier, modal, hedge,
   frequency adverb or unrecognised subordinator: :data:`_UNRECOGNISED_WORDS`); a label before a colon presents what
   follows as given ("Given:", "Data:", "Answer:", "Formula:") or is itself a recognised statement; no verb of report,
   estimate or judgement takes the figure as its content ("Students reported 17 deaths"); and the words before the
   figure's clause are recognised frame elements: connectives, subordinators that present a fact ("since", "because",
   "given", "although"), temporal subordinators relating an episode, relative pronouns, factive frames ("We are told
   that", "It is given that", "We know", "Note that", "It turned out that", and the frames that name the task itself:
   "In this problem", "In this question", "In this task", "In this exercise"; a hypothetical frame such as "In this
   scenario" stays unrecognised), time and place adverbials ("In 1960", "On 6
   May 1882", "In Africa"), whole clauses that end where such a boundary begins, a verb of perception whose small clause
   the figure is in ("The year 1960 saw seventeen states become independent"), and a raising verb of fact before "to
   be" ("n turned out to be 17", "n is known to be 17", "n was shown to be 17": :data:`_RAISING`; verbs of seeming,
   expecting, supposing, reporting and believing are read by the first half). A frame it does not recognise ("Students
   often guess that", "Rumour has it", "In this scenario", "Claim to test:") leaves the figure unasserted.

   Scope. A sentence ends at "! ? ;", a line break, and a full stop before a capital or before a lower-case symbol that
   opens a statement ("Define b. n = 17.": two sentences; a single letter, an identifier with a digit or an underscore,
   a Greek letter, or a word a comparison sign follows), never at a full stop that closes an abbreviation ("e.g.",
   "i.e.", "approx.") or before a lower-case word that continues the sentence ("Suppose b holds. then n = 17."). A
   question, and an instruction or a supposition that opens the sentence, govern the whole sentence, except that a
   question opened by a clause that presents a fact ("Given x = 5 and y = 9, is x < y?", "Since n = 17, does b hold?")
   governs only what follows that clause's comma: the given is asserted, as before a statement or an instruction,
   unless a construction inside it suspends the whole sentence ("Given that n could be 17, does b hold?"). A
   biconditional connective ("iff", "if and only if", "exactly / precisely /
   just / only when", "just in case", "equivalent to", "↔", "⇔", "⟺", "⟷", "<->", "<=>") governs the clause before it
   (from the last comma, colon, semicolon or connective) and the clause after it (to the next comma, colon or
   semicolon). Every other construction governs its coordinate unit: the part of the sentence between a colon, a full
   stop before a lower-case word ("n = 17. b holds ..."), a comma followed by a coordinating or discourse connective
   (", and", ", but", ", so", ", hence", ", therefore", ", while", ", whereas", ", although", ...), the bare connectives
   "so", "hence", "therefore", "thus" and "but", and the comma that closes an opening subordinate clause presenting a
   fact ("Given n = 17, define b iff n = 17": the given is asserted, the instruction governs only its own clause). So in
   "n equals 17 and b holds iff n equals 17" the first 17 is asserted and the second is not; in "If n equals 17, b
   holds" neither clause is; in "There are 17 items, so b holds, where b means there are exactly 17 items" the first 17
   is asserted.

   "When" and "once" relate an episode, a fact, after a time expression ("in 1960, when seventeen African states became
   independent") or with a verb in the past tense ("when sterling was devalued from $4.03 to $2.80"); otherwise they
   state a condition ("When n equals 17, b holds"; "b holds when n is 17"). "Given", "since", "because" and "as" present
   what follows as a fact.

2. **What does it state about the figure?** (:func:`relation_at`) Equality (the default, also "exactly"), an
   approximate value ("about", "roughly", "≈"), or a bound given by the words around it ("more than", "over", "at
   least", "fewer than", "under", "nearly", "almost", "at most", "up to", "capped at", "or more", "or fewer"). A figure
   is evidence for a comparison only when what it states establishes that comparison (:func:`relation_implies`: "more
   than 17" establishes no ``n = 17``).

3. **Is the fact about the encoding's symbols?** (:func:`link`) The clause names one of them as a formula names a
   symbol ("n equals 17", "y = 9", "x < y"; the one-letter words "a", "A" and "I" only beside a comparison), or it
   shares the words that describe them (their meanings and names, the label of the premise that defines them, and the
   source's own clauses that name them): two content words, or a word the figure counts ("17 items", "seventeen African
   states"). A figure that counts something else ("I checked 3 values", "the 2 integers y we pick") is not a value of
   the symbol. When nothing describes the symbols (no meaning, name word or label word, and no source names them), the
   value is the only link the encoding offers, and an asserted figure of that value links unless it counts a generic
   quantity. That fallback serves the answer's own figures; a figure of a supplied text or of the task record, read for a
   symbol the conclusion leaves free, links only by a name, a count or shared words (``link(value_only=False)``).

The reading is deliberately conservative where it decides a verdict: a figure is evidence only when it is asserted,
states what the encoding left open, and is about its symbols; everything else, a construction the reader does not
recognise included, is no evidence, so the counterexample stands with the advisory coverage warning rather than being
withheld, and no translator is asked to add a premise on it. Its limit is that of any reading of grammar from words: it
reads no meaning, so a genuine assertion in a construction it does not recognise ("The number of states that joined
grew, in all, to 17 by spring") is read as unasserted (the conservative error), and an unknown verb of report or
opinion before a bare noun ("Pupils opine growth was 17") is the one shape it can still misread as asserted. The pipeline
also checks the retry an E110 asks for: it may add only what the evidence states (see
:func:`.precision.added_premise_support`). The cost is linear in an untrusted text: its units, constructions and words are
found once per text (up to :data:`~.quantities.MAX_TEXT_CHARS`) and looked up by bisection; each clause is read once, and
each figure within a bounded window of it.
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Literal, Optional

from .quantities import LOWER_CASE_ABBREVIATIONS, MAX_TEXT_CHARS, _sentences, in_precision_cue, sentence_of

__all__ = ["AssertionReading", "Target", "assertion_at", "asserting_clause", "relation_at", "relation_implies", "stated_as", "names_a_bound", "BOUND_NOUNS", "link", "content_words",
           "mentions", "units_of", "describing_units", "sentence_cue_at"]

Mood = Literal["asserted", "question", "instruction", "condition", "supposition", "definition", "possibility", "negation", "quantified",
               "disjunction", "range", "attribution", "example", "unrecognised"]
Relation = Literal["eq", "approx", "lt", "le", "gt", "ge"]

#: How far around a figure its own words are read (characters): a bound before it ("more than", "at least") or after it
#: ("or more"), a negation where it stands ("other than"), a range or a disjunction it is one end of.
_WINDOW = 48


@dataclass(frozen=True)
class AssertionReading:
    """How a source states a figure: ``asserted`` only when no construction suspends the assertion; otherwise ``mood``
    names the construction and ``cue`` the words (at ``cue_start``) that decided it. ``unit`` is the coordinate unit of
    the sentence that holds the figure (characters of the source)."""
    asserted: bool
    mood: Mood
    unit: tuple[int, int]
    cue: Optional[str] = None
    cue_start: Optional[int] = None

    def describe(self) -> str:
        if self.asserted:
            return "asserted"
        return f"{self.mood} ({self.cue!r})" if self.cue else self.mood


@dataclass(frozen=True)
class Target:
    """What an asserting figure must be about: the ``names`` of the symbols an encoding left open and the ``words`` that
    describe them (content words of their meanings, names and the label of the premise that defines them, and of the
    source's own clauses that name them). ``named`` is true when a source names one of the symbols as a formula does."""
    names: tuple[str, ...]
    words: frozenset[str]
    named: bool = False

    @property
    def described(self) -> bool:
        """Whether anything says what the symbols are: a description word, or a source that names them."""
        return bool(self.words) or self.named


# ------------------------------------------------------------------ words

#: Words that carry no description of what a figure is about: articles, pronouns, prepositions, conjunctions,
#: auxiliaries and common verbs, the words of the constructions above, and precision and bound words.
_FUNCTION_WORDS = frozenset("""
a an the this that these those there here it its it's they them their theirs he him his she her hers we us our ours you your
i me my mine one ones who whom whose which what where when whenever while whilst why how whether if iff unless until till
than then so thus hence therefore because since as given though although yet but and or nor not no none neither either both
each every any all some such only also even just exactly precisely about approximately approx around roughly nearly almost
circa some more most less least fewer fewest over under above below between among within without with from into onto upon
of off on in at by to for per via up down out across after before during against toward towards through throughout beyond
is are was were be been being am has have had having do does did doing done can could may might must shall should will would
ought need needs needed let lets let's suppose supposed supposing assume assumed assuming define defines defined defining
definition denote denotes denoted means mean meant stand stands call called say says said holds hold held holding equals
equal equalled equaling equalling get gets got make makes made take takes took become becomes became go goes went come comes
came give gives gave keep keeps kept seem seems seemed whose very much many few several other another same own still already
again ever never often always sometimes usually case cases event condition provided providing long matter regardless whatever
whichever arbitrary arbitrarily possibly perhaps maybe probably likely unlikely possible presumably supposedly allegedly arguably
rounded rounding round decimal decimals place places significant nearest true false necessarily necessary hold holds holding
""".split())
#: Generic quantity words: a figure that counts them counts something, but they describe no particular quantity, so they are
#: no evidence of what a symbol stands for ("I checked 3 values", "the 2 integers y we pick").
_GENERIC_WORDS = frozenset("""
number numbers value values integer integers real reals figure figures amount amounts quantity quantities total totals count counts
variable variables constant constants digit digits literal literals equality inequality bound bounds strict element elements unit units
""".split())
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[a-z]+)?|(?<![\d.,])(?:1\d{3}|20\d{2})s?(?![\d.,]\d)")
_MONTHS = frozenset("january february march april may june july august september october november december".split())
_TIME_WORDS = frozenset("""
year years day days time times period periods decade decades century centuries era eras moment moments age ages point date dates week weeks
month months season seasons morning mornings evening evenings night nights summer winter spring autumn then
""".split()) | _MONTHS


#: Number words: a figure, never a word that describes what the figure is about.
_NUMBER_WORD_SET = frozenset("""
zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty
thirty forty fifty sixty seventy eighty ninety hundred hundreds thousand thousands million millions billion billions trillion trillions
half halves third thirds quarter quarters dozen dozens percent per cent bn mn
""".split())
_SUFFIXES = (("ations", ""), ("ation", ""), ("ings", ""), ("ing", ""), ("ied", "y"), ("ies", "y"), ("ed", ""), ("es", ""), ("s", ""))


def _normal(word: str) -> str:
    w = word.lower()
    return w[:-2] if w.endswith("'s") else w


def _stem(word: str) -> str:
    """A light stem, so that inflections of one word meet ("devalued", "devaluation"; "states", "state"): a common
    suffix and a final "e" are dropped from a word that keeps at least four letters."""
    for suffix, repl in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) + len(repl) >= 4:
            word = word[: len(word) - len(suffix)] + repl
            break
    return word[:-1] if word.endswith("e") and len(word) > 4 else word


def _content(word: str) -> Optional[str]:
    """The stem of a word that describes what a text is about, or None (a function word, a generic quantity word, a
    number word, a word of fewer than three letters); a four-digit year is kept as written ("1960")."""
    w = _normal(word)
    if w[:1].isdigit():
        return w.rstrip("s")
    if len(w) < 3 or w in _FUNCTION_WORDS or w in _GENERIC_WORDS or w in _NUMBER_WORD_SET:
        return None
    return _stem(w)


def content_words(text: Optional[str]) -> frozenset[str]:
    """The (lightly stemmed) words of ``text`` that describe what it is about: words of three or more letters that are
    neither function words, generic quantity words nor number words, and four-digit years ("1960"). Underscores count as
    spaces, so a symbol name such as ``num_states_1960`` describes "states" in 1960."""
    if not text:
        return frozenset()
    out = set()
    for m in _WORD_RE.finditer(text.replace("_", " ")):
        w = _content(m.group(0))
        if w is not None:
            out.add(w)
    return frozenset(out)


# ------------------------------------------------------------------ constructions

_FLAGS = re.IGNORECASE
#: (mood, pattern, case-insensitive): every construction that suspends the assertion of its coordinate unit.
_MARKERS: tuple[tuple[Mood, str, bool], ...] = (
    ("question", r"\bwhether\b", True),
    ("condition", r"(?<!\bonly\s)(?<!\bexactly\s)(?<!\bprecisely\s)(?<!\bjust\s)\bif\b(?!\s+and\s+only\s+if\b)|(?<!and\s)\bonly\s+if\b"
                  r"|\bunless\b|\b(?:as|so)\s+long\s+as\b|\bin\s+(?:the\s+)?(?:case|event)\b(?!\s+of\b)|\bon\s+(?:the\s+)?condition\b"
                  r"|\bwhenever\b|\bwherever\b|\botherwise\b|\b(?:necessary|sufficient)\b", True),
    ("condition", r"\b(?:for|with)\s+[A-Za-z][A-Za-z0-9_]{0,2}\s*(?:=|≠|<|>|≤|≥)", True),
    ("condition", r"\b(?:cases?|scenarios?|situations?|worlds?|instances?|circumstances?|conditions?|settings?|models?)\s+(?:where|in\s+which|when)\b"
                  r"|\b(?:depends?|depending|contingent|conditional)\s+(?:up)?on\b|\bsubject\s+to\b|\b(?:implies|imply|entails?|guarantees?|ensures?"
                  r"|requires?|leads?\s+to|results?\s+in|would\s+mean)\b|\b(?:necessary|sufficient|enough)\s+for\b|\bsuffices?\b"
                  r"|\b(?:so|such)\s+that\b|\bin\s+order\s+(?:to|that)\b|\bso\s+as\s+to\b|\blest\b", True),
    ("supposition", r"\bsuppos(?:e|es|ed|ing|ition|itions)\b|\bassum(?:e|es|ed|ing|ption|ptions)\b|\bpresum(?:e|es|ed|ing)\b"
                    r"|\bimagin(?:e|es|ed|ing)\b|\bhypothe(?:sis|ses|tical|tically|sise|size|sised|sized)\b|\blet(?:'s)?\b|\bpretend\b"
                    r"|\bgrant(?:ed|ing)\s+that\b|\bin\s+(?:theory|principle)\b|\btheoretical(?:ly)?\b"
                    r"|\b(?:take|taking|treat|treating|regard|regarding|reading|setting|set|picture|picturing)\s+[\w$£€.]+\s+(?:as|to\s+be|to|equal\s+to)\b", True),
    ("definition", r"\bdefin(?:e|es|ed|ing|ition|itions)\b|\bdenot(?:e|es|ed|ing)\b|\bstands?\s+for\b|\bmeans\b(?!\s+of\b)"
                   r"|\b(?:is|are)\s+(?:called|termed|named|said\s+to)\b|\bwe\s+(?:say|call|write)\b|\brefers?\s+to\b|\bshorthand\b"
                   r"|\bdoes\s+not\s+assert\b", True),
    ("possibility", r"\b(?:could|might|would|should|can|cannot|ought|may|must)\b", False),
    ("possibility", r"\b(?:has|have|had|needs?|needed)\s+to\b|\b(?:is|are|was|were)\s+to\s+be\b|\brequired\s+to\b"
                    r"|\b(?:aims?|aimed|aiming|plans?|planned|planning|intends?|intended|wants?|wanted|wanting|wish|wishes|wished|hopes?|hoped|hoping"
                    r"|expects?|expecting|prefers?|preferred|seeks?|sought|tries|tried|trying)\b|\bwould\s+like\b|'d\s+like\b"
                    r"|\b(?:targets?|goals?|objectives?|quotas?)\b", True),
    ("possibility", r"\b(?:possibly|perhaps|maybe|probably|presumably|supposedly|allegedly|arguably|conceivably|potentially|likely|unlikely"
                    r"|possible|impossible|possibility)\b|\bneed\s+not\b|\bneedn't\b|\b(?:expected|projected|forecast|predicted|estimated)\s+to\b", True),
    ("negation", r"\bnot\b|n't\b|\bnever\b|\bneither\b|\bnor\b|\bnone\b(?!\s+other\b)|\bnobody\b|\bnothing\b(?!\s+(?:else|more|but)\b)"
                 r"|\bno\s+one\b(?!\s+else\b)|\bfail(?:s|ed|ing)?\s+to\b|\brather\s+than\b|\binstead\s+of\b|\b(?:false|untrue|incorrect)\b", True),
    ("negation", r"\bno\b(?!\s+(?:doubt|longer|sooner|later|earlier|more|less|fewer|other|one\s+else)\b)", False),
    ("possibility", r"\b(?:seem|seems|seemed|appear|appears|appeared)\s+to\b|\b(?:uncertain|unclear|unsure|unknown|doubtful|doubts?)\b", True),
    ("attribution", r"\b(?:say|says|said|argue|argues|argued|claim|claims|claimed|believe|believes|believed|think|thinks|thought|suggest|suggests"
                    r"|suggested|contend|contends|contended|allege|alleges|reportedly|rumou?red)\b", True),
    ("attribution", r"\baccording\s+to\b|\brumou?rs?\b|\bhearsay\b|\b(?:legend|tradition|folklore)\s+(?:has\s+it|says|holds)\b|\bword\s+(?:is|has\s+it)\b"
                    r"|\bthe\s+story\s+goes\b|\bguess(?:es|ed|ing)?\b|\bsuspect(?:s|ed|ing)?\b|\breckon(?:s|ed|ing)?\b|\bspeculat(?:e|es|ed|ing|ion|ions|ive)\b"
                    r"|\bpurport(?:s|ed|edly)?\b|\breport(?:s|ed|edly)?\b|\ballegations?\b|\b(?:opinion|opinions|belief|beliefs|hunch|impression)\b"
                    r"|\b(?:assert|asserts|asserted|insist|insists|insisted|maintain|maintains|maintained|propose|proposes|proposed)\s+that\b", True),
    ("supposition", r"\bconjectur(?:e|es|ed|al|ally)\b|\bpostulat(?:e|es|ed|ing)\b|\bposit(?:s|ed|ing)?\b|\bworking\s+assumption\b"
                    r"|\bwhat\s+if\b|\bthought\s+experiment\b", True),
    ("question", r"\bto\s+(?:be\s+)?(?:test(?:ed)?|check(?:ed)?|verif(?:y|ied)|prov(?:e|ed|en)|disprov(?:e|ed|en)|confirm(?:ed)?|establish(?:ed)?"
                 r"|determin(?:e|ed)|decid(?:e|ed)|evaluat(?:e|ed)|investigat(?:e|ed)|examin(?:e|ed)|assess(?:ed)?|settl(?:e|ed))\b"
                 r"|\b(?:true\s+or\s+false|right\s+or\s+wrong|open\s+question|claim\s+to\s+test)\b", True),
    ("possibility", r"\bun(?:confirmed|verified|proven|tested|checked|substantiated|attested|certain|clear)\b|\b(?:apparently|seemingly|ostensibly"
                    r"|nominally|reputedly|evidently|hopefully|ideally)\b|\bit\s+(?:seems|seemed|appears|appeared|would\s+seem|would\s+appear)\b"
                    r"|\bis\s+said\s+to\b|\bif\s+(?:true|so|correct)\b", True),
    ("quantified", r"\b(?:sometimes|often|oftentimes|usually|typically|generally|normally|commonly|frequently|occasionally|rarely|seldom|mostly"
                   r"|ordinarily|customarily|habitually|regularly|periodically|invariably|mainly|largely|chiefly|predominantly)\b"
                   r"|\bin\s+(?:general|most\s+cases|many\s+cases|some\s+cases|certain\s+cases)\b|\bas\s+a\s+(?:rule|norm)\b"
                   r"|\bon\s+average\b|\b(?:some|many|most|several|certain|various|numerous|few)\s+(?:cases?|instances?|times?|situations?|occasions?"
                   r"|scenarios?|examples?|models?|worlds?|settings?|circumstances?|contexts?|versions?|inputs?|places?|years?|readings?)\b"
                   r"|\b(?:some|many|most|several|few)\s+of\b", True),
    ("condition", r"[⇒→⟹⟶⇐←⟸⟵⊃⊢⊨]|==>|(?<!<)-->|<==|<--(?!>)|(?<![<=!])=>|(?<![<\-])->|<-(?![->])|\|-|\|=", False),
    ("definition", r":=|≔|≝|≡", False),
    ("negation", r"¬", False),
    ("disjunction", r"∨|\|\|", False),
    ("example", r"\bfor\s+(?:example|instance)\b|\be\.\s?g\.|\bsuch\s+as\b|\bsay,", True),
    ("quantified", r"\bfor\s+(?:any|all|every|each|some)\b|(?<!without\s)(?<!not\s)\bany\b|\bevery\b|\beach\s+of\b|\barbitrar(?:y|ily)\b"
                   r"|\bwhatever\b|\bwhichever\b|\bregardless\b|\bno\s+matter\b|\bun(?:constrained|restricted|specified|determined)\b|[∀∃]", True),
    ("disjunction", r"\beither\b|\bor\b(?!\s+(?:so|thereabouts|more|fewer|less|later|earlier|not)\b)", True),
)
_MARKER_RES = tuple((mood, re.compile(pattern, _FLAGS if folded else 0)) for mood, pattern, folded in _MARKERS)
#: Connectives that state a biconditional between two clauses ("b holds exactly when n equals 17"): they govern the clause
#: before them (from the last comma, colon, semicolon or connective) and the clause after them (to the next comma, colon or
#: semicolon), so "n equals 17 and b holds iff n equals 17" asserts its first 17 and not its second.
_BICONDITIONAL_RE = re.compile(r"\biff\b|\bif\s+and\s+only\s+if\b|\bwhen\s+and\s+only\s+when\b|\b(?:exactly|precisely|just|only)\s+(?:when|if|where|in\s+case)\b"
                               r"|\bjust\s+in\s+case\b|\bequivalent\s+to\b|↔|⇔|⟺|⟷|<-->|<->|<=>", _FLAGS)
_CLAUSE_START_RE = re.compile(r"[,;:]|\s(?:and|but|so|hence|therefore|thus|while|whilst|whereas|since|because|as)\s", _FLAGS)
#: "when" and "once": a condition unless they relate an episode (see the module docstring).
_WHEN_RE = re.compile(r"(?<!exactly\s)(?<!precisely\s)(?<!just\s)(?<!only\s)\b(?:when|once)\b(?!\s+and\s+only\s+when\b)", _FLAGS)
#: "provided" and "providing" state a condition when they open a clause or are followed by "that" ("the UK provided $3
#: billion" states a fact).
_PROVIDED_RE = re.compile(r"\bprovid(?:ed|ing)\b", _FLAGS)
#: "No" opening a sentence or a clause before a word negates it ("No 17 states ..."); "No:" and "No," answer, and a vote of
#: "No" in mid-sentence negates nothing.
_NO_OPENING_RE = re.compile(r"(?:^|[.!?;:(]\s*|\n\s*)(No)\b(?=\s+[A-Za-z0-9$£€])")
#: A sentence that continues the condition or supposition of the one before ("Suppose b holds. Then n = 17.").
_CONTINUES_RE = re.compile(r"[\s\"'“‘(]*(?:then|in\s+that\s+case|in\s+which\s+case|if\s+so|under\s+that\s+assumption)\b", _FLAGS)
_FRAMING = frozenset({"condition", "supposition", "instruction", "definition", "example"})
#: Words that open a subordinate clause presenting a fact: such a clause ends at its first comma.
_FACTUAL_OPENERS = frozenset({"given", "since", "because", "as", "although", "though", "whereas", "while", "whilst"})

#: A sentence that opens with one of these words is an instruction or a supposition: it asserts none of its figures.
_INSTRUCTION_WORDS = frozenset("""
define let lets let's suppose supposing assume assuming consider imagine picture say take put pick choose fix denote write call label treat
regard interpret set show prove find determine calculate compute check verify decide evaluate estimate solve grant granting
use using apply test explain justify discuss state describe examine investigate compare identify outline sketch plot draw predict deduce
derive suggest comment analyse analyze assess demonstrate confirm disprove decide try
""".split())
#: A sentence that opens with an inverted auxiliary is a question (or an inverted condition: "Had n been 17, ...").
_AUXILIARIES = frozenset("""
is are was were am do does did can could will would shall should may might must has have had isn't aren't wasn't weren't don't doesn't
didn't can't couldn't won't wouldn't shouldn't hasn't haven't hadn't
""".split())
_FIRST_WORD_RE = re.compile(r"[\s\"'“‘(\[*•\-–—]*(?:\(?[a-z0-9]{1,3}[.)]\s+)?([A-Za-z]+(?:'[a-z]+)?)")
#: Unit boundaries: a colon (not '10:30'); a comma followed by a coordinating or discourse connective; the bare
#: connectives so, hence, therefore, thus and but (not "so that", "so long", "or so", "nothing but").
_BREAK_RE = re.compile(
    r":(?![\d/])"
    r"|,(?=\s*(?:and|but|yet|so|hence|therefore|thus|while|whilst|whereas|although|though|however|consequently|accordingly|nor)\b)"
    r"|(?<=\s)(?=(?:so|hence|therefore|thus|but)\b(?![-'])(?!\s+(?:that|long|far|many|much|called|as)\b))"
    r"|(?<=[\w)\]])\.(?=\s+[a-z])",
    _FLAGS)
_NO_BREAK_BEFORE = ("or", "nothing", "all", "anything", "everything", "and")
_ABBREVIATIONS = LOWER_CASE_ABBREVIATIONS

#: Past-tense verbs that are not regular "-ed" forms (a "when" clause in the past tense relates an episode).
_PAST_IRREGULAR = frozenset("""
was were had did became began came went won lost made took gave got saw fell rose led left met paid said sold sent spent stood told thought
brought bought fought held kept knew grew drew broke chose spoke wrote ran sat struck swore threw understood wore fled found felt heard hung
arose awoke bore bent bled blew bred built burnt caught clung crept dealt dug drove drank ate fed flew forbade forgot forgave froze hid laid
lent lit meant overcame rang rode sang sank shook shone shot slept slid sought sped spun stole stuck stung strove swam swept swung taught
tore undertook upheld withdrew woke wound wept overthrew overtook withstood
""".split())
#: Present-tense forms that make a "when" clause a condition when they come first ("when n equals 17", "when n is 17").
_PRESENT_FORMS = frozenset("""
is are am has have does do equals equal holds hold exceeds exceed reaches reach becomes become falls fall rises rise comes come goes go gets
get makes make takes take gives give means contains contain includes include lies lie remains remain stays stay turns turn hits hit drops
drop grows grow stands stand lies totals total amounts amount
""".split())
_PAST_EED = frozenset({"agreed", "freed", "decreed", "guaranteed", "disagreed", "refereed"})
_NOT_PAST_ED = frozenset({"hundred", "indeed", "red", "bed", "shed", "wed", "united", "kindred"})
_TOKEN_RE = re.compile(r"[A-Za-z]+(?:'[a-z]+)?|\d[\d,.]*|[=<>≤≥≠]")


def _is_past(word: str) -> bool:
    w = word.lower()
    if w in _PAST_IRREGULAR:
        return True
    if len(w) < 4 or not w.endswith("ed") or w in _NOT_PAST_ED:
        return False
    return not w.endswith("eed") or w in _PAST_EED


def _temporal_when(text: str, start: int, end: int, unit_end: int) -> bool:
    """True when the "when" or "once" at ``start``-``end`` relates an episode (a fact): it follows a time expression,
    or the first verb after it is in the past tense (before any present-tense form)."""
    before = text[max(0, start - 40):start].rstrip(" ,")
    last = re.search(r"([A-Za-z]+|\d{4}s?)\W*$", before)
    if last is not None:
        token = last.group(1).lower()
        if token[:1].isdigit() or token in _TIME_WORDS:
            return True
    for k, m in enumerate(_TOKEN_RE.finditer(text, end, min(unit_end, end + 120))):
        if k >= 10:
            break
        word = m.group(0)
        if not word[:1].isalpha():
            if word in "=<>≤≥≠":
                return False  # a formula: "when n = 17"
            continue
        low = word.lower()
        if low in _PRESENT_FORMS:
            return False
        if _is_past(low):
            return True
    return False


@dataclass(frozen=True)
class _Index:
    """The units and constructions of one text, computed once."""
    sentence_starts: tuple[int, ...]
    sentence_ends: tuple[int, ...]
    sentence_cue: tuple[Optional[tuple[Mood, str, int]], ...]
    unit_starts: tuple[int, ...]
    unit_ends: tuple[int, ...]
    unit_cue: tuple[Optional[tuple[Mood, str, int]], ...]
    #: the spans a biconditional connective governs, disjoint and in order, with the connective that decided each
    bicond_starts: tuple[int, ...] = ()
    bicond_ends: tuple[int, ...] = ()
    bicond_cue: tuple[tuple[str, int], ...] = ()
    #: where each sentence's cue starts to govern: the sentence start, or, for a question opened by a clause that presents
    #: a fact ("Given x = 5 and y = 9, is x < y?"), the comma that ends that clause (the given is asserted, the question
    #: governs what follows it)
    sentence_cue_from: tuple[int, ...] = ()


def _sentence_cue(text: str, a: int, b: int) -> Optional[tuple[Mood, str, int]]:
    """A question, or an instruction or a supposition that opens the sentence ``a``-``b``: they govern all of it."""
    sentence = text[a:b]
    stripped = sentence.rstrip(" \t\r\n\"'”’)]")
    if stripped.endswith("?"):
        return ("question", "?", a + len(stripped) - 1)
    m = _FIRST_WORD_RE.match(sentence)
    if m is None:
        return None
    word = m.group(1)
    low = word.lower()
    if low in _INSTRUCTION_WORDS:
        return ("instruction" if low not in ("suppose", "supposing", "assume", "assuming", "imagine", "say") else "supposition", word, a + m.start(1))
    if low in _AUXILIARIES and not (low == "may" and re.match(r"\s*\d", sentence[m.end(1):])):
        return ("question", word, a + m.start(1))
    return None


@lru_cache(maxsize=256)
def _index(full: str) -> _Index:
    # read up to the bound the figure reader reads (every figure lies within it); the offsets are the full text's
    text = full[:MAX_TEXT_CHARS]
    sentences = _sentences(text)
    breaks: list[int] = []
    for m in _BREAK_RE.finditer(text):
        if m.group(0) == "" and m.start() > 0:
            prev = re.search(r"([A-Za-z]+)\s*$", text[max(0, m.start() - 16):m.start()])
            if prev is not None and prev.group(1).lower() in _NO_BREAK_BEFORE:
                continue
        if m.group(0) == ".":
            # a full stop before a lower-case word ends a statement ("n = 17. b holds ...") unless it closes an
            # abbreviation ("e.g. n", "approx. 17") or a single letter
            word = re.search(r"([A-Za-z.]+)$", text[max(0, m.start() - 8):m.start()])
            if word is not None and (word.group(1).lower().strip(".") in _ABBREVIATIONS or len(word.group(1).strip(".")) == 1):
                continue
        breaks.append(m.start())
    # an opening subordinate clause that presents a fact ends at its first comma ("Given n = 17, define b iff n = 17": the
    # given is asserted, the instruction after it governs only its own clause; "Given n = 17, does b hold?": the question
    # governs only what follows the given), unless a construction inside it suspends the whole sentence ("Since we suppose
    # n is 17, ...")
    factual_end: dict[int, int] = {}
    for a, b in sentences:
        first = _FIRST_WORD_RE.match(text, a, b)
        if first is None or first.group(1).lower() not in _FACTUAL_OPENERS:
            continue
        comma = next((c for c in range(first.end(1), min(b, first.end(1) + 400)) if text[c] == "," and not _between_digits(text, c)), None)
        if comma is None:
            continue
        opening = text[a:comma]
        if any(rx.search(opening) for _mood, rx in _MARKER_RES) or _BICONDITIONAL_RE.search(opening) or _WHEN_RE.search(opening):
            continue
        breaks.append(comma)
        factual_end[a] = comma
    breaks.sort()
    # every construction of the text, in order of position
    found: list[tuple[int, int, Mood]] = []
    for mood, rx in _MARKER_RES:
        for m in rx.finditer(text):
            found.append((m.start(), m.end(), mood))
    for m in _PROVIDED_RE.finditer(text):
        before = text[max(0, m.start() - 3):m.start()].strip()
        if not before or before[-1] in ",;:(" or re.match(r"\s+that\b", text[m.end():m.end() + 6], _FLAGS):
            found.append((m.start(), m.end(), "condition"))
    for m in _NO_OPENING_RE.finditer(text):
        found.append((m.start(1), m.end(1), "negation"))
    whens = [(m.start(), m.end()) for m in _WHEN_RE.finditer(text)]
    found.sort()
    starts_found = [f[0] for f in found]
    unit_starts: list[int] = []
    unit_ends: list[int] = []
    unit_cue: list[Optional[tuple[Mood, str, int]]] = []
    sentence_cue: list[Optional[tuple[Mood, str, int]]] = []
    cue_from: list[int] = []
    when_starts = [w[0] for w in whens]
    framing: Optional[tuple[Mood, str, int]] = None  # the condition or supposition of the sentence before
    for a, b in sentences:
        cue_s = _sentence_cue(text, a, b)
        if cue_s is None and framing is not None:
            cont = _CONTINUES_RE.match(text, a, b)
            if cont is not None:
                cue_s = (framing[0], text[a:cont.end()].strip(), a)
        sentence_cue.append(cue_s)
        # a question opened by a clause that presents a fact governs only what follows that clause
        cue_from.append(factual_end[a] if cue_s is not None and cue_s[0] == "question" and a in factual_end else a)
        framing = cue_s if cue_s is not None and cue_s[0] in _FRAMING else None
        lo, hi = bisect_right(breaks, a), bisect_left(breaks, b)
        cuts = [a, *[p for p in breaks[lo:hi] if a < p < b], b]
        for u0, u1 in zip(cuts, cuts[1:]):
            cue: Optional[tuple[Mood, str, int]] = None
            k = bisect_left(starts_found, u0)
            while k < len(found) and found[k][0] < u1:
                s, e, mood = found[k]
                if e <= u1:
                    cue = (mood, text[s:e], s)
                    break
                k += 1
            if cue is None:
                j = bisect_left(when_starts, u0)
                while j < len(whens) and whens[j][0] < u1:
                    s, e = whens[j]
                    if not _temporal_when(text, s, e, u1):
                        cue = ("condition", text[s:e], s)
                        break
                    j += 1
            unit_starts.append(u0)
            unit_ends.append(u1)
            unit_cue.append(cue)
            if framing is None and cue is not None and cue[0] in _FRAMING:
                framing = cue
    # biconditional connectives: from the start of the clause before to the end of the clause after
    has_bicond = _BICONDITIONAL_RE.search(text) is not None
    starts_b = sorted([m.end() for m in _CLAUSE_START_RE.finditer(text) if not _between_digits(text, m.start())] + [p + 1 for p in breaks]) if has_bicond else []
    ends_b = sorted([k for k in range(len(text)) if text[k] in ",;:" and not _between_digits(text, k)] + breaks) if has_bicond else []
    spans: list[tuple[int, int, str, int]] = []
    s_starts = [a for a, _b in sentences]
    for m in _BICONDITIONAL_RE.finditer(text):
        si = bisect_right(s_starts, m.start()) - 1
        sa, sb = sentences[si] if si >= 0 else (0, len(text))
        k = bisect_right(starts_b, m.start()) - 1
        left = max(sa, starts_b[k]) if k >= 0 and starts_b[k] <= m.start() else sa
        j = bisect_left(ends_b, m.end())
        right = min(sb, ends_b[j]) if j < len(ends_b) else sb
        spans.append((left, right, m.group(0), m.start()))
    spans.sort()
    merged: list[tuple[int, int, str, int]] = []
    for span in spans:
        if merged and span[0] <= merged[-1][1]:
            last = merged[-1]
            merged[-1] = (last[0], max(last[1], span[1]), last[2], last[3])
        else:
            merged.append(span)
    return _Index(sentence_starts=tuple(a for a, _b in sentences), sentence_ends=tuple(b for _a, b in sentences),
                  sentence_cue=tuple(sentence_cue), unit_starts=tuple(unit_starts), unit_ends=tuple(unit_ends), unit_cue=tuple(unit_cue),
                  bicond_starts=tuple(x[0] for x in merged), bicond_ends=tuple(x[1] for x in merged), bicond_cue=tuple((x[2], x[3]) for x in merged),
                  sentence_cue_from=tuple(cue_from))


def _between_digits(text: str, k: int) -> bool:
    """A comma between digits ('790,000') splits nothing."""
    return 0 < k < len(text) - 1 and text[k] == "," and text[k - 1].isdigit() and text[k + 1].isdigit()


def sentence_cue_at(text: str, pos: int) -> Optional[tuple[Mood, str, int]]:
    """The construction that opens the sentence holding ``pos`` and governs all of it (a question, an instruction or a
    supposition opening it, or the continuation of the sentence before), as ``(mood, cue, position)``; None when there is
    none."""
    idx = _index(text)
    s = bisect_right(idx.sentence_starts, pos) - 1
    return idx.sentence_cue[s] if s >= 0 and pos >= idx.sentence_cue_from[s] else None


def units_of(text: str) -> tuple[tuple[int, int], ...]:
    """The coordinate units of ``text`` in order (characters), as the reader splits its sentences."""
    idx = _index(text)
    return tuple(zip(idx.unit_starts, idx.unit_ends))


def _unit_index(idx: _Index, pos: int) -> int:
    k = bisect_right(idx.unit_starts, pos) - 1
    return max(k, 0)


_NUMBER_WORDS = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen"
                 r"|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)")
_NUMBER_AHEAD = r"[$£€¥]?\s?(?:[-−]?\d|" + _NUMBER_WORDS + r"\b)"
#: A figure that is one option of a disjunction or one end of a range: the words right after it, or right before it.
#: (A hyphen joins a range only unspaced, "2-3%": "5 - 3" is a subtraction.)
_OPTION_AFTER_RE = re.compile(r"(?:\s*(?:or|to|–|—)\s*|-)" + _NUMBER_AHEAD, _FLAGS)
_OPTION_BEFORE_RE = re.compile(r"(?:\d[\d,.]*|" + _NUMBER_WORDS + r")(?:\s*[%a-zA-Z]{0,3}\s*(?:or|to|–|—)\s*|-)$", _FLAGS)
_BETWEEN_RE = re.compile(r"\bbetween\s+(?:[$£€¥]?\s?)?$", _FLAGS)
_BETWEEN_AND_RE = re.compile(r"\bbetween\s+[$£€¥]?\s?(?:\d[\d,.]*|" + _NUMBER_WORDS + r")[^,;:.]{0,24}\band\s+(?:[$£€¥]?\s?)?$", _FLAGS)
_FROM_RE = re.compile(r"\bfrom\s+(?:[$£€¥]?\s?)?$", _FLAGS)
#: "from <figure> in <year>" right before the second end: a change between dated figures ("from 42% in 2014 to ...").
_FROM_DATED_RE = re.compile(r"\bfrom\s+[$£€¥]?\s?\d[\d,.]*\s*(?:%|per\s?cent|[a-zA-Z]{0,8})?\s+(?:in|during|by|at)\s+$", _FLAGS)
_YEAR_NUMERAL_RE = re.compile(r"(?:1[0-9]{3}|20[0-9]{2}|21[0-9]{2})")
#: A figure negated or excluded where it stands.
_EXCLUDED_BEFORE_RE = re.compile(r"(?:≠|!=|=/=|\bother\s+than|\bexcept(?:\s+for)?|\bapart\s+from|\bbesides|\bexcluding|\bdiffer(?:s|ed)?\s+from"
                                 r"|\bdifferent\s+from)\s*(?:[$£€¥]\s?)?$", _FLAGS)
#: A figure negated in its own predicate, by the words right before it ("x is not 0.33", "x isn't 17", "n was never 17",
#: "does not equal 17", "did not reach 17", "not exactly 17", "0.33, not 0.34"). A bound phrase is no such negation: "not
#: more than 17", "not exceeding 17" and "no fewer than 17" state a bound (:func:`relation_at`).
_NEGATED_BEFORE_RE = re.compile(
    r"(?:\bnot|n't|\bnever|\bno\s+longer)\s+(?:(?:equal|equals|equalled|equaled|reach|reached|reaches|exceed|exceeds|exceeded|surpass|surpassed|hit|total"
    r"|totals|totalled|totaled|amount|amounted|come|came|be|been|become|became|exactly|precisely|quite|just|only|even|actually|really|to)\s+){0,4}"
    r"(?:[$£€¥]\s?)?$", _FLAGS)


def _figure_mood(text: str, start: int, end: int, unit: tuple[int, int]) -> Optional[tuple[Mood, str, int]]:
    """A construction that makes this one figure state no fact of its own: negated or excluded where it stands, or one
    end of a range or one option of a disjunction ("from X to Y" is a change: both figures are stated). A numeral of a
    cue that states a precision is no end of a range: "x is 0.33 to 2 decimal places" states 0.33
    (:func:`.quantities.in_precision_cue`)."""
    before = text[max(unit[0], start - _WINDOW):start]
    after = text[end:min(unit[1], end + _WINDOW)]
    m = _EXCLUDED_BEFORE_RE.search(before) or _NEGATED_BEFORE_RE.search(before)
    if m is not None:
        return ("negation", m.group(0).strip(), start - len(before) + m.start())
    if _BETWEEN_RE.search(before) or _BETWEEN_AND_RE.search(before):
        return ("range", "between", start)
    a = _OPTION_AFTER_RE.match(after)
    if a is not None and not in_precision_cue(text, end + a.end() - 1):
        joiner = re.match(r"\s*(or|to|–|—|-)", a.group(0), _FLAGS)
        word = joiner.group(1).lower() if joiner is not None else ""
        if word == "or" or not _FROM_RE.search(before):
            return ("disjunction" if word == "or" else "range", a.group(0).strip(), end)
    b = _OPTION_BEFORE_RE.search(before)
    if b is not None and in_precision_cue(text, start - len(before) + b.start()):
        b = None
    if b is not None:
        joiner = re.search(r"(or|–|—|-|to)\s*$", b.group(0), _FLAGS)
        word = joiner.group(1).lower() if joiner is not None else ""
        if word == "or":
            return ("disjunction", b.group(0).strip(), start - len(before) + b.start())
        prior = text[max(unit[0], start - len(before) + b.start() - 40):start - len(before) + b.start()]
        lead = re.match(r"\d[\d,.]*", b.group(0))
        year_end = lead is not None and _YEAR_NUMERAL_RE.fullmatch(lead.group(0)) is not None and not _YEAR_NUMERAL_RE.fullmatch(text[start:end].strip())
        # a year before "to" dates the figure before it ("fell from 42% in 2014 to 18% in 2024": a change from one dated
        # figure to another, never the range "2014 to 18%": re-run review A-FA-RANGE)
        if not _FROM_RE.search(prior) and not year_end and not _FROM_DATED_RE.search(prior):
            return ("range", b.group(0).strip(), start - len(before) + b.start())
    return None


_LEAD_RE = re.compile(r"[\s,;:.]*(?:(?:and|but|so|hence|therefore|thus|while|whereas)\b)?[\s,]*", _FLAGS)
_TRAIL_RE = re.compile(r"[\s,;:]*(?:\b(?:and|but|or|so|while|whereas|since|because|as))?[\s,;:.]*\Z", _FLAGS)


@lru_cache(maxsize=8192)
def asserting_clause(text: str, start: int, end: int) -> tuple[int, int]:
    """The clause that states the figure at ``start``-``end``: its coordinate unit without any part a biconditional
    connective governs (the side of it that holds the figure), and without edge punctuation and connectives; the span a
    reference to the asserting source should quote ("n equals 17" of "Since n equals 17 and b holds iff n equals 17").
    Found by bisection and read in bounded windows, so quoting every figure of a long text stays linear."""
    idx = _index(text)
    k = _unit_index(idx, start)
    a, b = (idx.unit_starts[k], idx.unit_ends[k]) if idx.unit_starts else (0, len(text))
    j = bisect_right(idx.bicond_ends, start) - 1  # the last governed span that ends before the figure
    if j >= 0 and idx.bicond_ends[j] > a:
        a = idx.bicond_ends[j]
    j = bisect_left(idx.bicond_starts, end)  # the first governed span that starts after it
    if j < len(idx.bicond_starts) and idx.bicond_starts[j] < b:
        b = idx.bicond_starts[j]
    lead = _LEAD_RE.match(text, a, min(b, a + 64))
    a2 = lead.end() if lead is not None else a
    lo = max(a, b - 64)
    trail = _TRAIL_RE.search(text, lo, b)
    b2 = trail.start() if trail is not None else b
    return (a2, b2) if a2 <= start and end <= b2 else (a, b)


# ------------------------------------------------------------------ positive recognition

#: Closed-class words an asserting clause may hold: determiners, pronouns, prepositions, the connectives and subordinators
#: that present a fact, the copula and auxiliaries of the indicative, and the adverbs of degree, time and order that leave
#: a statement a statement. A closed-class word outside this set (a quantifier, a modal, a hedge, a frequency adverb, an
#: unrecognised subordinator: :data:`_UNRECOGNISED_WORDS`) leaves the clause unrecognised.
_RECOGNISED_WORDS = frozenset("""
the a an this that these those its their his her our my your whose which who whom
i me we us you he him she it they them there here itself themselves himself herself ourselves myself yourself
of in on at by to from for with without into onto upon within after before during since until till over under above below between among
amongst across through throughout against toward towards about around near beyond behind beside besides beneath along alongside despite except
excluding including inside outside past per plus minus via circa than off out up down as like
and but yet so because although though while whilst whereas given hence therefore thus however moreover furthermore also too both
then now still already again indeed together just only alone even exactly precisely approximately approx roughly nearly almost
clearly certainly obviously definitely undoubtedly actually indeed really
is are was were be been being am has have had having do does did
first firstly second secondly third thirdly finally lastly later earlier ago today yesterday respectively altogether overall
other another same own such else
""".split())
#: Closed-class words that make a clause unrecognised wherever they stand in it.
_UNRECOGNISED_WORDS = frozenset("""
some any many much few several all each every either neither enough various certain numerous
someone somebody something anyone anybody anything everyone everybody everything whoever whatever whichever
can could may might must shall should will would ought need needs dare
if unless whether where wherever whereby whenever lest providing supposing assuming
or nor surely always somewhat rather quite fairly pretty arguably
according regarding concerning versus vs unlike
""".split())
#: Comparative words that state a bound in a recognised phrase ("more than 17", "17 or more", "at least", "at most").
_BOUND_COMPARATIVES = frozenset({"more", "less", "fewer", "least", "most", "greater", "higher", "lower", "larger", "smaller"})
#: Copulas and relation words that predicate a figure of a subject ("n is 17", "the total equals 17", "x = 5").
_LINKS = frozenset("""
is are was were be been being am equals equal equalled equaled totals totalled totaled numbers numbered became becomes become remained remains
stands stood reached reaches reach rose fell dropped climbed grew increased decreased amounted amounts = < > ≤ ≥ <= >= ≈ ~ ∼ ≃
""".split())
#: Words that modify a figure where it stands ("about 17", "only one", "more than 17", "at least 5", "up to 3").
_FIGURE_MODIFIERS = frozenset("""
about around approximately approx roughly nearly almost exactly precisely only just over under above below circa least most than more less fewer
greater higher lower larger smaller up upwards at no
""".split())
#: Auxiliaries and copulas: a finite verb of the indicative.
_AUXILIARIES_INDICATIVE = frozenset("is are was were am has have had do does did".split())
#: Connectives and discourse words a frame may open with.
_CONNECTIVES = frozenset("""
and but yet so hence therefore thus also moreover furthermore indeed here now finally firstly first secondly second thirdly third lastly overall
still however consequently accordingly likewise similarly specifically namely notably then again besides clearly certainly obviously
""".split())
_CONNECTIVE_PHRASES = (("in", "fact"), ("in", "addition"), ("in", "total"), ("in", "all"), ("in", "sum"), ("in", "short"), ("of", "course"), ("as", "a", "result"),
                       ("in", "particular"), ("at", "the", "same", "time"), ("in", "other", "words"), ("that", "is"), ("in", "practice"),
                       ("in", "the", "end"), ("at", "last"))
#: Subordinators that present their clause as a fact.
_FACTUAL_SUBORDINATORS = frozenset({"since", "because", "as", "given", "although", "though", "whereas", "while", "whilst"})
_FACTUAL_PHRASES = (("given", "that"), ("even", "though"), ("now", "that"), ("seeing", "that"), ("in", "that"), ("in", "view", "of", "the", "fact", "that"))
#: Temporal subordinators: relating an episode (the deny layer has already read "when" and "once" that state a condition).
_TEMPORAL = frozenset({"when", "once", "after", "before", "until", "till"})
_RELATIVES = frozenset({"which", "who", "whom", "whose"})
#: Frames that present what follows as a fact the writer and the task share ("We are told that", "It is given that",
#: "Note that"), matched as word sequences; an optional "that" may follow.
_FACTIVE_FRAMES = tuple(tuple(f.split()) for f in """
we are told|we were told|you are told|you were told|we are given|you are given|we are shown|we know|we knew|you know|i know|we see|we saw
we note|we recall|we find|we found|it is given|it was given|it is known|it was known|it is true|it is clear|it is evident|it is established
it was established|it is a fact|the fact is|note|recall|remember|notice|observe|the task states|the task gives|the question states|the question gives
the problem states|the problem gives|the source states|the text states|the passage states|the data show|the data shows|the table shows
the record shows|the records show|the census shows|this shows|it follows|it turns out|it turned out|it has turned out|it had turned out
it was found|it has been found|it was shown|it has been shown|it was proved|it was proven|it has been proved|it has been proven
it was confirmed|it has been confirmed|it has been established|it was determined|it was demonstrated|it has been demonstrated
the answer is|the result is
in this problem|in this question|in this task|in this exercise|in the problem|in the question|in the task
""".strip().replace("\n", "|").split("|"))
#: Verbs whose subject witnessed or established what follows (a small clause or a "that" clause): "The year 1960 saw
#: seventeen states become independent".
_PERCEPTION = frozenset("""
saw see sees seen witnessed witnesses witness watched observed showed shows show shown proved proves proven demonstrated demonstrates
confirmed confirms established establishes found finds
""".split())
#: Verbs whose object is the content of a report, an estimate or a judgement, not a fact the writer states ("Students
#: reported 17 deaths", "Historians estimated n at 17", "n was deemed 17"): anywhere before the figure in its clause.
_CONTENT_VERBS = frozenset("""
reported estimated predicted projected forecast guessed claimed said quoted cited alleged rumoured rumored put placed reckoned gauged deemed
considered judged reckons gauges deems judges estimates predicts projects forecasts guesses claims quotes cites alleges
""".split())
#: Verbs that raise a factual predication of their subject before "to be" ("n turned out to be 17", "n proved to be 17",
#: "n is known to be 17", "n was found to be 17"): the writer states the figure. "turn" raises only with "out". Verbs of
#: seeming, expecting, supposing, reporting or believing are read by the deny layer first ("n seems to be 17", "n is
#: believed to be 17", "n is said to be 17"), and a verb of report or estimate makes the figure its content.
_RAISING = frozenset("""
proved proves prove proven happened happens happen known shown found confirmed established determined measured observed demonstrated
verified turned turns turn
""".split())
_RAISING_WITH_OUT = frozenset({"turned", "turns", "turn"})
#: Auxiliaries a raising verb may follow ("is known to be", "has been shown to be").
_RAISING_AUXILIARIES = frozenset("is are was were am has have had been be being".split())
#: Labels before a colon that present what follows as given ("Given: n = 17"); any other label leaves it unrecognised.
_FACTUAL_LABELS = frozenset("""
given givens data fact facts known information info note nb recall here answer result results solution conclusion summary
rule rules formula formulae formulas equation equations
""".split())
_TIME_WORDS_FRAME = _TIME_WORDS | frozenset({"war", "reign", "decades", "centuries", "months", "weeks", "days", "hours", "minutes", "seconds",
                                             "quarter", "half", "term", "session", "meantime", "meanwhile", "today", "yesterday", "tonight"})
_TIME_PREPS = frozenset({"in", "on", "at", "by", "during", "after", "before", "from", "until", "till", "since", "around", "circa", "throughout",
                         "within", "over", "between", "through", "toward", "towards", "early", "late"})
#: Characters an asserting clause may hold besides letters, digits and spaces.
_RECOGNISED_CHARS = frozenset(".,;:!'\"’‘“”()[]-–—/%$£€¥+=<>≤≥≈~∼≃×*÷^·−&°′″#@½¼¾⅓⅔…²³¹⁰⁴⁵⁶⁷⁸⁹⁻℃µΩ_")
_MULTI_SYMBOL_RE = re.compile(r"==|!=|\|\||&&|<>|\?\?")
#: A character outside letters, digits, spaces and :data:`_RECOGNISED_CHARS`.
_UNRECOGNISED_CHAR_RE = re.compile("[^\\w\\s" + "".join(re.escape(c) for c in sorted(_RECOGNISED_CHARS)) + "]")
_PTOK_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:['’][A-Za-z]+)*|\d[\d,]*(?:\.\d+)?|<=|>=|\S")
#: How far around a figure its clause is read (characters before and after it). A clause that reaches beyond the window
#: before the figure is read from the last clause boundary inside the window (a coordinator, a subordinator, a relative
#: pronoun); with no such boundary it is not recognised. So every figure costs a bounded read, however long its clause.
_WINDOW_BEFORE = 200
_WINDOW_AFTER = 100


_PHRASES_BY_FIRST: dict[str, list[tuple[tuple[str, ...], str]]] = {}


@dataclass(frozen=True)
class _PTok:
    kind: str  # "word", "num", "sym", "fig"
    text: str  # lower-cased for words
    raw: str
    start: int
    end: int


@dataclass(frozen=True)
class _ClauseProfile:
    """One clause read once: its tokens and their starts, and the positions of what the reader does not recognise in it
    (closed-class words and odd symbols), so each figure of a long clause looks them up by bisection."""
    toks: tuple[_PTok, ...]
    starts: tuple[int, ...]
    problem_starts: tuple[int, ...]
    problems: tuple[_PTok, ...]
    odd_starts: tuple[int, ...]
    odd: tuple[str, ...]


@lru_cache(maxsize=512)
def _span_tokens(text: str, a: int, b: int) -> _ClauseProfile:
    """The tokens of ``text[a:b]`` (no figure marked), their start offsets, and the unrecognised words and symbols of the
    clause, computed once per clause."""
    toks: list[_PTok] = []
    for m in _PTOK_RE.finditer(text, a, b):
        raw = m.group(0)
        kind = "word" if raw[0].isalpha() else "num" if raw[0].isdigit() else "sym"
        toks.append(_PTok(kind, raw.lower() if kind == "word" else raw, raw, m.start(), m.end()))
    first_word = next((n for n, t in enumerate(toks) if t.kind == "word"), -1)
    problems = _closed_class_problems(toks, first_word)
    odd = sorted([(m.start(), m.group(0)) for m in _UNRECOGNISED_CHAR_RE.finditer(text, a, b)]
                 + [(m.start(), m.group(0)) for m in _MULTI_SYMBOL_RE.finditer(text, a, b)])
    return _ClauseProfile(toks=tuple(toks), starts=tuple(t.start for t in toks), problem_starts=tuple(t.start for t in problems), problems=tuple(problems),
                          odd_starts=tuple(p for p, _c in odd), odd=tuple(c for _p, c in odd))


def _window_tokens(text: str, clause: tuple[int, int], window: tuple[int, int], fig: tuple[int, int]) -> list[_PTok]:
    """The tokens of ``clause`` that lie inside ``window``, with the figure at ``fig`` as one token (found by bisection in
    the clause's tokens, so reading many figures of one long clause stays linear)."""
    profile = _span_tokens(text, *clause)
    toks, starts = profile.toks, profile.starts
    lo, hi = bisect_left(starts, window[0]), bisect_left(starts, window[1])
    out: list[_PTok] = []
    placed = False
    for t in toks[lo:hi]:
        if t.end <= fig[0] or t.start >= fig[1]:
            if not placed and t.start >= fig[1]:
                out.append(_PTok("fig", text[fig[0]:fig[1]], text[fig[0]:fig[1]], fig[0], fig[1]))
                placed = True
            out.append(t)
    if not placed:
        out.append(_PTok("fig", text[fig[0]:fig[1]], text[fig[0]:fig[1]], fig[0], fig[1]))
    return out


def _ptokens(text: str, a: int, b: int, fig: tuple[int, int]) -> list[_PTok]:
    """The tokens of ``text[a:b]`` with the figure at ``fig`` as one token."""
    out: list[_PTok] = []
    pos = a
    for lo, hi in ((a, fig[0]), (fig[1], b)):
        for m in _PTOK_RE.finditer(text, lo, hi):
            raw = m.group(0)
            kind = "word" if raw[0].isalpha() else "num" if raw[0].isdigit() else "sym"
            out.append(_PTok(kind, raw.lower() if kind == "word" else raw, raw, m.start(), m.end()))
        if lo == a:
            out.append(_PTok("fig", text[fig[0]:fig[1]], text[fig[0]:fig[1]], fig[0], fig[1]))
    del pos
    return out


def _is_symbol_name(t: _PTok) -> bool:
    """A token written as a formula names a symbol: one letter (not "a", "A" or "I", which are also words), or an
    identifier with a digit or an underscore ("x1", "num_states")."""
    if t.kind != "word":
        return False
    if len(t.raw) == 1:
        return t.raw not in ("a", "A", "I")
    return any(ch.isdigit() or ch == "_" for ch in t.raw)


def _verb_like(t: _PTok) -> bool:
    """A finite verb the reader recognises: a link or an auxiliary, a past-tense form, or a present-tense form it knows."""
    if t.kind == "sym":
        return t.text in _LINKS
    return t.kind == "word" and _word_is_verb(t.text)


@lru_cache(maxsize=8192)
def _word_is_verb(w: str) -> bool:
    return w in _LINKS or w in _AUXILIARIES_INDICATIVE or w in _PRESENT_FORMS or _is_past(w)


def _closed_class_problem(toks: list[_PTok], first_word: int) -> Optional[_PTok]:
    """The first closed-class word of the clause that the reader does not recognise in an assertion (a quantifier, a
    modal, a hedge, an unrecognised subordinator), or None (see :func:`_closed_class_problems`)."""
    found = _closed_class_problems(toks, first_word, first_only=True)
    return found[0] if found else None


def _closed_class_problems(toks: list[_PTok], first_word: int, first_only: bool = False) -> list[_PTok]:
    """The closed-class words of the clause that the reader does not recognise in an assertion (a quantifier, a modal, a
    hedge, an unrecognised subordinator). A capitalised word inside the clause is a name ("the vote was No"); a comparative
    counts only in a bound or a quantity ("more than 17", "17 or more", "at least", "17 more states")."""
    out: list[_PTok] = []
    for i, t in enumerate(toks):
        if t.kind != "word":
            continue
        if i != first_word and t.raw[:1].isupper() and t.raw != "I":
            continue
        w = t.text
        bad = False
        if w in _BOUND_COMPARATIVES:
            prev = toks[i - 1] if i > 0 else None
            nxt = toks[i + 1].text if i + 1 < len(toks) else ""
            bad = not (nxt == "than" or (prev is not None and (prev.kind in ("fig", "num") or prev.text in _NUMBER_WORD_SET
                                                                or prev.text in ("at", "or", "and", "no", "not", "the"))))
        elif w == "else" and i > 0 and toks[i - 1].text in ("nothing", "no", "none", "nobody", "noone"):
            bad = False
        else:
            bad = w in _UNRECOGNISED_WORDS
        if bad:
            out.append(t)
            if first_only:
                break
    return out


def _match_words(toks: list[_PTok], i: int, phrase: tuple[str, ...]) -> bool:
    return i + len(phrase) <= len(toks) and all(toks[i + k].kind == "word" and toks[i + k].text == w for k, w in enumerate(phrase))


def _phrase_index() -> dict[str, list[tuple[tuple[str, ...], str]]]:
    """The frame phrases by their first word, longest first: ``{word: [(phrase, kind)]}`` (kind: connective, factual,
    factive), so a frame is read with one dictionary look-up per word."""
    out: dict[str, list[tuple[tuple[str, ...], str]]] = {}
    for kind, phrases in (("connective", _CONNECTIVE_PHRASES), ("factual", _FACTUAL_PHRASES), ("factive", _FACTIVE_FRAMES)):
        for phrase in phrases:
            out.setdefault(phrase[0], []).append((phrase, kind))
    for entries in out.values():
        entries.sort(key=lambda e: -len(e[0]))
    return out


def _time_phrase_end(toks: list[_PTok], i: int, limit: int) -> int:
    """The end of a time or place adverbial that starts at token ``i`` ("In 1960", "on 18 September 1949", "by mid-1952",
    "In its heaviest years", "In Africa", "That year"), or ``i`` when none starts there. It must hold a year, a date, a
    month, a decade, a word of time, or a name (a capitalised word: a place or an institution)."""
    k = i
    if k < limit and toks[k].kind == "word" and toks[k].text in _TIME_PREPS:
        k += 1
    start_content = k
    has_anchor = False
    while k < limit:
        t = toks[k]
        if t.kind == "num" or t.kind == "fig":
            if t.kind == "fig":
                break
            has_anchor = True
        elif t.kind == "sym":
            if t.text not in ("-", "–", "'", "’"):
                break
        elif t.kind == "word":
            w = t.text
            if w in _TIME_WORDS_FRAME or w in _MONTHS or re.fullmatch(r"\d{4}s?|\d+(?:st|nd|rd|th)", w):
                has_anchor = True
            elif t.raw[:1].isupper() and k > 0:
                has_anchor = True  # a name: a place, an institution, an event
            elif w in ("the", "its", "their", "his", "her", "this", "that", "these", "those", "same", "next", "following", "previous", "preceding",
                       "last", "early", "late", "mid", "middle", "end", "start", "beginning", "course", "of", "and", "heaviest", "first", "second",
                       "third", "final", "latter", "former"):
                pass
            elif w in _UNRECOGNISED_WORDS or w in _RECOGNISED_WORDS or w in _CONNECTIVES:
                break
            else:
                # an open-class word inside the phrase: only before a time word ("its heaviest years")
                nxt = toks[k + 1] if k + 1 < limit else None
                if nxt is None or nxt.kind != "word" or nxt.text not in _TIME_WORDS_FRAME:
                    break
        else:
            break
        k += 1
    if not has_anchor or k == start_content:
        return i
    if k < limit and toks[k].kind == "sym" and toks[k].text == ",":
        k += 1
    return k


def _relative_that(toks: list[_PTok], i: int) -> bool:
    """Whether the "that" at ``i`` is a relative pronoun (followed by a finite verb: "a programme that had transferred")."""
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    return nxt is not None and _verb_like(nxt)


def _clause_end(toks: list[_PTok], i: int, limit: int) -> int:
    """The end of a clause that starts at ``i`` inside a frame: the next subordinator, relative pronoun, coordinator or
    semicolon (a comma alone does not end it: appositions and participles stay inside)."""
    k = i
    while k < limit:
        t = toks[k]
        if t.kind == "word" and (t.text in _FACTUAL_SUBORDINATORS or t.text in _TEMPORAL or t.text in _RELATIVES or t.text in ("and", "but", "yet")
                                 or (t.text == "that" and _relative_that(toks, k))):
            return k
        if t.kind == "sym" and t.text == ";":
            return k
        k += 1
    return k


_PHRASES_BY_FIRST.update(_phrase_index())


def _frame_problem(toks: list[_PTok], limit: int) -> Optional[_PTok]:
    """Read ``toks[:limit]``, the words before the figure's clause, as recognised frame elements: connectives, factual
    and temporal subordinators, relative pronouns, factive frames ("We are told that"), time and place adverbials, and
    whole clauses that end where a recognised boundary begins (or with a verb of perception: "The year 1960 saw"). Returns
    the first token that no element covers, or None when every token is covered."""
    i = 0
    factive_open = False  # a factive frame or a perception verb was just read: a "that" may follow
    while i < limit:
        t = toks[i]
        if t.kind == "sym" and t.text in (",", "(", ")", "—", "–", "-", "'", "\"", "’", "‘", "“", "”", "[", "]"):
            i += 1
            continue
        if t.kind != "word":
            return t
        w = t.text
        if w == "that":
            if factive_open or _relative_that(toks, i):
                factive_open = False
                i += 1
                continue
            return t
        factive_open = False
        hit = next(((p, kind) for p, kind in _PHRASES_BY_FIRST.get(w, ()) if _match_words(toks, i, p)), None)
        if hit is not None:
            i += len(hit[0])
            factive_open = hit[1] == "factive"
            continue
        if w in _CONNECTIVES or w in _FACTUAL_SUBORDINATORS or w in _TEMPORAL or w in _RELATIVES:
            i += 1
            continue
        if w == "of" and i + 1 < limit and toks[i + 1].kind == "word" and toks[i + 1].text in _RELATIVES:
            i += 2
            continue
        end = _time_phrase_end(toks, i, limit)
        if end > i:
            i = end
            continue
        # a whole clause: it must hold a finite verb, no unrecognised embedding, and end at a recognised boundary (or with a
        # verb of perception, whose small clause the figure's clause is)
        end = _clause_end(toks, i, limit)
        run = toks[i:end]
        if not any(_verb_like(x) for x in run):
            return t
        if any(x.kind == "word" and x.text == "that" and not _relative_that(toks, i + n) for n, x in enumerate(run)):
            return next(x for x in run if x.kind == "word" and x.text == "that")
        if end >= limit:
            last = next((x for x in reversed(run) if x.kind == "word"), None)
            if last is not None and last.text in _PERCEPTION:
                return None
            return t
        i = end
    return None


def _raising_start(toks: list[_PTok], link: int) -> Optional[int]:
    """The first token of a raising phrase whose "to be" ends at the link ``link`` ("turned out to be", "is known to
    be", "has been shown to be": :data:`_RAISING`), or None when the link is no such phrase's "be"."""
    if link < 2 or toks[link].kind != "word" or toks[link].text != "be" or toks[link - 1].kind != "word" or toks[link - 1].text != "to":
        return None
    v = link - 2
    particle = toks[v].kind == "word" and toks[v].text == "out"
    if particle:
        v -= 1
    if v < 0 or toks[v].kind != "word" or toks[v].text not in _RAISING or (toks[v].text in _RAISING_WITH_OUT) is not particle:
        return None
    a = v
    while a > 0 and toks[a - 1].kind == "word" and toks[a - 1].text in _RAISING_AUXILIARIES:
        a -= 1
    return a


def _walk_back_modifiers(toks: list[_PTok], fi: int) -> int:
    """The start of the figure's phrase: the figure with the bound and degree words before it ("more than", "about",
    "only", "at least", "up to")."""
    m = fi
    while m > 0 and toks[m - 1].kind == "word" and toks[m - 1].text in _FIGURE_MODIFIERS:
        if toks[m - 1].text in ("at", "up", "no") and not (m < len(toks) and toks[m].kind == "word" and toks[m].text in ("least", "most", "to", "more", "less", "fewer")):
            break
        m -= 1
    return m


def _subject_start(toks: list[_PTok], j: int) -> int:
    """The start of the subject whose last token is ``j`` (before a link): a symbol name with the determiner and generic
    nouns before it ("the number n"), or a noun phrase back to its determiner (through "of" and prepositions inside it) or
    to the nearest clause boundary. A recognised verb or a subordinator ends it."""
    t = toks[j]
    if _is_symbol_name(t):
        s = j
        while s > 0 and toks[s - 1].kind == "word" and (toks[s - 1].text in _GENERIC_WORDS or toks[s - 1].text in ("the", "a", "an", "this", "our", "its", "their", "of")):
            s -= 1  # "the number n", "the value of n"
        return s
    if t.kind == "word" and t.text in ("there", "it", "this", "that", "they", "we", "he", "she", "i", "you"):
        return j
    s = j
    while s > 0:
        p = toks[s - 1]
        if p.kind == "sym" and p.text not in ("'", "’", "-"):
            break
        if p.kind == "word":
            w = p.text
            if w in ("the", "a", "an", "this", "these", "those", "its", "their", "his", "her", "our", "my", "your"):
                s -= 1
                before = toks[s - 1] if s > 0 else None
                if before is not None and before.kind == "word" and before.text in ("of", "in", "on", "at", "for", "from", "with", "to", "by"):
                    s -= 1  # a preposition inside the noun phrase ("the speed of the car")
                    continue
                break
            if _verb_like(p) and s >= 2 and toks[s - 2].kind == "word" and (toks[s - 2].text in _RELATIVES or toks[s - 2].text == "that"):
                s -= 2  # a relative clause inside the noun phrase ("the number of states that became independent")
                continue
            if (w in _FACTUAL_SUBORDINATORS or w in _TEMPORAL or w in _RELATIVES or w in ("and", "but", "yet", "that", "or", "nor")
                    or w in _CONNECTIVES or _verb_like(p) or w in _UNRECOGNISED_WORDS):
                break
        s -= 1
    return s


def _subject_follows(toks: list[_PTok], fi: int) -> bool:
    """Whether the figure begins a subject: within a few words after it (nouns, adjectives, "of") comes a finite verb
    ("seventeen African states became", "17 of them were")."""
    k = fi + 1
    for _ in range(7):
        if k >= len(toks):
            return False
        t = toks[k]
        if _verb_like(t):
            return True
        if t.kind == "sym" and t.text not in ("-", "'", "’"):
            return False
        if t.kind == "word" and t.text != "of" and (t.text in _RECOGNISED_WORDS or t.text in _UNRECOGNISED_WORDS):
            return t.text in ("them", "these", "those", "the", "us")
        k += 1
    return False


def _object_core(toks: list[_PTok], m: int) -> int:
    """The start of the clause that holds a figure in object position: after the nearest subordinator, relative
    pronoun, "that" or semicolon before it, or after the nearest coordinator that joins clauses (commas stay inside the
    clause; a coordinator with no verb before it joins noun phrases: "seventeen states and 17 more")."""
    k = m - 1
    while k >= 0:
        t = toks[k]
        if t.kind == "word" and (t.text in _FACTUAL_SUBORDINATORS or t.text in _TEMPORAL or t.text in _RELATIVES or t.text == "that"):
            return k + 1
        if t.kind == "sym" and t.text == ";":
            return k + 1
        if t.kind == "word" and t.text in ("and", "but", "yet"):
            j = k - 1
            while j >= 0 and not (toks[j].kind == "word" and toks[j].text in ("and", "but", "yet")) and not _boundary(toks[j], toks, j):
                if _verb_like(toks[j]):
                    return k + 1
                j -= 1
            k = j  # the coordinator joins noun phrases: go on from the start of the phrase before it
            continue
        k -= 1
    return 0


def _label_before(text: str, unit: tuple[int, int]) -> Optional[tuple[str, int]]:
    """The label before a colon that opens the unit ("Hypothesis: n is 17"): ``(label, start)``, or None."""
    lead = text[unit[0]:min(unit[1], unit[0] + 4)]
    if not lead.lstrip().startswith(":"):
        return None
    colon = unit[0] + (len(lead) - len(lead.lstrip()))
    a, _b = sentence_of(text, colon, colon + 1)
    prev = text.rfind(":", a, colon)
    lo = prev + 1 if prev >= 0 else a
    return text[lo:colon], lo


def _label_problem(text: str, label: str, at: int) -> Optional[tuple[Mood, str, int]]:
    """None when a label presents what follows as given (:data:`_FACTUAL_LABELS`, or a whole statement the reader
    recognises: "Hostility was already written into law: ..."); otherwise the construction that suspends it."""
    found = _label_reading(label)
    return None if found is None else (found[0], found[1], at + found[2])


@lru_cache(maxsize=1024)
def _label_reading(label: str) -> Optional[tuple[Mood, str, int]]:
    """:func:`_label_problem` relative to the label (read once per label text)."""
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", label)]
    if not words:
        return ("unrecognised", label.strip()[:40], 0)
    if " ".join(words) in _FACTUAL_LABELS or (len(words) <= 2 and words[-1] in _FACTUAL_LABELS and words[0] in ("the", "final", "given", "known", "our", "my")):
        return None
    for mood, rx in _MARKER_RES:
        m = rx.search(label)
        if m is not None:
            return (mood, m.group(0), m.start())
    bicond = _BICONDITIONAL_RE.search(label)
    if bicond is not None:
        return ("definition", bicond.group(0), bicond.start())
    toks = _ptokens(label, 0, len(label), (len(label), len(label)))[:-1]
    if not any(_verb_like(t) for t in toks) or _closed_class_problem(toks, 0) is not None or _UNRECOGNISED_CHAR_RE.search(label) is not None:
        return ("unrecognised", label.strip()[:60], 0)
    if any(t.kind == "word" and t.text == "that" and not _relative_that(toks, n) for n, t in enumerate(toks)):
        return ("unrecognised", label.strip()[:60], 0)
    # a statement label is read as a clause of its own: the words before its subject must be a recognised frame
    first_verb = next(n for n, t in enumerate(toks) if _verb_like(t))
    if first_verb > 0 and _frame_problem(toks, _subject_start(toks, first_verb - 1)) is not None:
        return ("unrecognised", label.strip()[:60], 0)
    return None


def _boundary(t: _PTok, toks: list[_PTok], k: int) -> bool:
    """Whether token ``k`` opens a clause of its own: a coordinator, a subordinator, a relative pronoun, a relative
    "that", or a semicolon."""
    if t.kind == "sym":
        return t.text == ";"
    w = t.text
    return (w in ("and", "but", "yet") or w in _FACTUAL_SUBORDINATORS or w in _TEMPORAL or w in _RELATIVES
            or (w == "that" and _relative_that(toks, k)))


def _unrecognised(text: str, start: int, end: int, unit: tuple[int, int]) -> Optional[tuple[Mood, str, int]]:
    """The positive half of :func:`assertion_at`: None when the reader positively recognises the clause that states the
    figure as an assertion; otherwise ``(mood, cue, position)`` of what it does not recognise (see the module docstring).
    The clause is read within :data:`_WINDOW_BEFORE` and :data:`_WINDOW_AFTER` characters of the figure."""
    label = _label_before(text, unit)
    if label is not None:
        problem = _label_problem(text, *label)
        if problem is not None:
            return problem
    ca, cb = asserting_clause(text, start, end)
    w0, w1 = max(ca, start - _WINDOW_BEFORE), min(cb, end + _WINDOW_AFTER)
    profile = _span_tokens(text, ca, cb)
    k = bisect_left(profile.odd_starts, w0)
    if k < len(profile.odd_starts) and profile.odd_starts[k] < w1:
        return ("unrecognised", profile.odd[k], profile.odd_starts[k])
    k = bisect_left(profile.problem_starts, w0)
    while k < len(profile.problem_starts) and profile.problem_starts[k] < w1:
        bad = profile.problems[k]
        if not (start <= bad.start < end):  # a word inside the figure as written is the figure's own
            return ("unrecognised", bad.raw, bad.start)
        k += 1
    cut = w0 > ca
    toks = _window_tokens(text, (ca, cb), (w0, w1), (start, end))
    if cut and toks and toks[0].kind != "fig" and toks[0].start < w0:
        toks = toks[1:]
    fi = next(n for n, t in enumerate(toks) if t.kind == "fig")
    m = _walk_back_modifiers(toks, fi)
    link = m - 1
    if link >= 0 and toks[link].kind == "word" and toks[link].text in ("to", "at", "of") and link - 1 >= 0 and toks[link - 1].text in _LINKS | {"equal", "amounted", "rose", "fell", "dropped", "came", "comes", "stood", "stands"}:
        link -= 1
    raised = _raising_start(toks, link) if link >= 0 else None
    if raised is not None and raised >= 1:
        core = _subject_start(toks, raised - 1)  # "n turned out to be 17": the raising phrase links the subject and the figure
    elif link >= 0 and (toks[link].text in _LINKS) and link - 1 >= 0:
        core = _subject_start(toks, link - 1)
    elif m == 0 or _subject_follows(toks, fi):
        core = m
        while core > 0 and toks[core - 1].kind == "word" and toks[core - 1].text in ("the", "a", "an", "its", "their", "these", "those", "only", "just", "some"):
            core -= 1
    else:
        core = _object_core(toks, m)
    frame_start = 0
    if cut:
        # the clause began before the window: read it from the last clause boundary inside the window
        local = next((k for k in range(m - 1, -1, -1) if _boundary(toks[k], toks, k)), -1)
        if local < 0:
            return ("unrecognised", "a clause longer than the reader reads", toks[0].start if toks else start)
        if core <= local:
            core = local + 1
        frame_start = next((k for k in range(core - 1, -1, -1) if _boundary(toks[k], toks, k)), local)
    # a figure in the clause of a verb of report, estimate or judgement is that verb's content, not the writer's statement
    for t in toks[frame_start:m]:
        if t.kind == "word" and t.text in _CONTENT_VERBS:
            return ("attribution", t.raw, t.start)
    problem = _frame_problem(toks[frame_start:], core - frame_start)
    if problem is not None:
        return ("unrecognised", problem.raw, problem.start)
    return None


def assertion_at(text: str, start: int, end: int) -> AssertionReading:
    """How ``text`` states the figure at ``start``-``end`` (see the module docstring)."""
    idx = _index(text)
    k = _unit_index(idx, start)
    unit = (idx.unit_starts[k], idx.unit_ends[k]) if idx.unit_starts else (0, len(text))
    s = bisect_right(idx.sentence_starts, start) - 1
    if s >= 0 and idx.sentence_cue[s] is not None and start >= idx.sentence_cue_from[s]:
        mood, cue, at = idx.sentence_cue[s]  # type: ignore[misc]
        return AssertionReading(False, mood, unit, cue, at)
    if idx.unit_starts and idx.unit_cue[k] is not None:
        mood, cue, at = idx.unit_cue[k]  # type: ignore[misc]
        return AssertionReading(False, mood, unit, cue, at)
    b = bisect_right(idx.bicond_starts, start) - 1
    if b >= 0 and start < idx.bicond_ends[b]:
        cue, at = idx.bicond_cue[b]
        return AssertionReading(False, "definition", unit, cue, at)
    own = _figure_mood(text, start, end, unit)
    if own is not None:
        return AssertionReading(False, own[0], unit, own[1], own[2])
    unknown = _unrecognised(text, start, end, unit)
    if unknown is not None:
        return AssertionReading(False, unknown[0], unit, unknown[1], unknown[2])
    return AssertionReading(True, "asserted", unit)


# ------------------------------------------------------------------ what it states

_REL_BEFORE: tuple[tuple[Relation, re.Pattern], ...] = (
    ("ge", re.compile(r"(?:\bat\s+least|\bno\s+(?:fewer|less|lower)\s+than|\bnot\s+(?:fewer|less|below)(?:\s+than)?|\b(?:a\s+)?minimum\s+of"
                      r"|\bfloor\s+of|≥|>=)\s*(?:[$£€¥]\s?)?$", _FLAGS)),
    ("le", re.compile(r"(?:\bat\s+most|\bno\s+(?:more|higher|greater)\s+than|\bnot\s+(?:more|above|exceeding)(?:\s+than)?|\bup\s+to"
                      r"|\b(?:a\s+)?maximum\s+of|\bcapped\s+at|\bcaps?\s+at|\btops?\s+out\s+at|\bpeak(?:s|ed)?\s+at|\bceiling\s+of|≤|<=)"
                      r"\s*(?:[$£€¥]\s?)?$", _FLAGS)),
    ("gt", re.compile(r"(?:\b(?:more|greater|higher|larger|bigger)\s+than|\b(?:over|above|exceeding|exceeds|exceeded|beyond|upwards\s+of)"
                      r"|\bin\s+excess\s+of|>)\s*(?:[$£€¥]\s?)?$", _FLAGS)),
    ("lt", re.compile(r"(?:\b(?:fewer|less|lower|smaller)\s+than|\b(?:under|below|beneath)|\b(?:nearly|almost)|\bjust\s+short\s+of|<)\s*(?:[$£€¥]\s?)?$",
                      _FLAGS)),
    ("approx", re.compile(r"(?:\b(?:about|approximately|approx\.?|around|roughly|circa|some)|\bc\.|[≈~∼≃])\s*(?:[$£€¥]\s?)?$", _FLAGS)),
)
_REL_AFTER: tuple[tuple[Relation, re.Pattern], ...] = (
    ("ge", re.compile(r"\s*(?:\+(?!\s*\d)|(?:or|and)\s+(?:more|over|above|upwards|greater|higher)\b)", _FLAGS)),
    ("le", re.compile(r"\s*(?:or|and)\s+(?:fewer|less|under|below|lower)\b", _FLAGS)),
    ("approx", re.compile(r"\s*(?:or\s+so|or\s+thereabouts|-?ish)\b", _FLAGS)),
)


#: Every word or sign the bound phrases before a figure are made of (a superset: a window without any of them states no
#: bound, so the ordered reading below is skipped), and the same for the phrases after it.
_ANY_REL_BEFORE = re.compile(r"least|fewer|less|lower|below|minimum|floor|most|more|higher|greater|above|exceed|up|maximum|cap|top|peak|ceiling"
                             r"|larger|bigger|over|beyond|upwards|excess|smaller|under|beneath|nearly|almost|short|about|approx|around|roughly"
                             r"|circa|some|c\.|[≥≤<>≈~∼≃]", _FLAGS)
_ANY_REL_AFTER = re.compile(r"\s*(?:\+|or|and|-?ish)", _FLAGS)


def relation_at(text: str, start: int, end: int) -> Relation:
    """What ``text`` states about the figure at ``start``-``end``: equal (the default), approximately equal, or the bound
    the words around it give (``ge`` "at least", ``le`` "at most", ``gt`` "more than", ``lt`` "fewer than", "nearly")."""
    before = text[max(0, start - _WINDOW):start]
    if _ANY_REL_BEFORE.search(before):
        for rel, rx in _REL_BEFORE:
            if rx.search(before):
                return rel
    after = text[end:end + _WINDOW]
    if _ANY_REL_AFTER.match(after):
        for rel, rx in _REL_AFTER:
            if rx.match(after):
                return rel
    return "eq"


#: What a stated relation implies about a comparison with the same literal: equal (or approximately equal) satisfies
#: = <= >=; "fewer than" satisfies < <=; "more than" > >=; "at most" <=; "at least" >=.
_IMPLIES: dict[str, frozenset[str]] = {
    "eq": frozenset({"eq", "le", "ge"}), "approx": frozenset({"eq", "le", "ge"}),
    "lt": frozenset({"lt", "le"}), "le": frozenset({"le"}), "gt": frozenset({"gt", "ge"}), "ge": frozenset({"ge"}),
}


def relation_implies(stated: str, required: Optional[str]) -> bool:
    """Whether a figure stated with relation ``stated`` (from :func:`relation_at`) establishes the comparison
    ``required`` (``symbol <op> literal``) with the same literal. ``None`` requires nothing."""
    return required is None or required in _IMPLIES.get(stated, frozenset())


_RELATION_WORDS = {"eq": "the figure itself", "approx": "an approximate figure", "lt": "a strict upper bound", "le": "an upper bound",
                   "gt": "a strict lower bound", "ge": "a lower bound"}


#: Nouns that name a bound itself: a symbol whose meaning names one stands for the bound's value, so a figure stated as a
#: strict bound ("keep youth unemployment below 10%") states it ("the government's unemployment ceiling" = 10): repair round
#: 3, V3-FALSE-SRCMISMATCH-THRESHOLD.
BOUND_NOUNS: frozenset[str] = frozenset({
    "target", "targets", "ceiling", "ceilings", "limit", "limits", "cap", "caps", "threshold", "thresholds", "maximum", "minimum",
    "floor", "cutoff", "benchmark", "goal", "goals", "requirement", "standard", "quota", "criterion", "bound", "bounds",
})


def names_a_bound(text: Optional[str]) -> bool:
    """Whether ``text`` (a symbol's meaning or a premise's label) names a bound itself (:data:`BOUND_NOUNS`; "pass mark" and
    "cut-off" too)."""
    toks = re.findall(r"[a-z]+", (text or "").lower()[:1000])
    if any(t in BOUND_NOUNS for t in toks):
        return True
    return any(a == "pass" and b == "mark" or a == "cut" and b == "off" for a, b in zip(toks, toks[1:]))


def stated_as(text: str, start: int, end: int, required: str, *, bound_symbol: bool = False) -> Optional[str]:
    """None when the figure at ``start``-``end`` of ``text``, as the text states it, establishes the comparison an
    assignment premise states about its symbol (``required``: ``eq``, ``lt``, ``le``, ``gt`` or ``ge``, read from the
    symbol's side); otherwise why it does not. Used by grounding (:mod:`.relations`), where a record's framing (a question,
    an instruction, a condition of the task) is the task's own and suspends nothing, so only the figure's own statement is
    read: negated or excluded where it stands or in its own predicate ("≠ 17", "other than 17", "is not 17"), one option of a
    disjunction or one end of a range
    ("17 or 18", "between 15 and 17") establishes nothing; an equality needs the figure stated plainly, approximately or as
    an inclusive bound (the bound's own value: "at most 350 words" states ``limit = 350``), never as a strict bound ("more
    than 17" states no ``n = 17``), except for a symbol that is the bound itself (``bound_symbol``: its meaning names a
    target, ceiling, limit, threshold, pass mark, ...: "below 10%" states a ceiling of 10); a bound needs a statement that
    implies it (:func:`relation_implies`)."""
    idx = _index(text)
    k = _unit_index(idx, start)
    unit = (idx.unit_starts[k], idx.unit_ends[k]) if idx.unit_starts else (0, len(text))
    own = _figure_mood(text, start, end, unit)
    if own is not None:
        return f"stated as {'one option of a disjunction' if own[0] == 'disjunction' else 'one end of a range' if own[0] == 'range' else 'negated or excluded'} ({own[1]!r})"
    stated = relation_at(text, start, end)
    if required == "eq":
        if stated in ("lt", "gt") and bound_symbol:
            return None  # the symbol is the bound itself: the bound's value is the figure ("below 10%" states a ceiling of 10)
        return None if stated in ("eq", "approx", "le", "ge") else f"stated as {_RELATION_WORDS[stated]}, which establishes no equality"
    if relation_implies(stated, required):
        return None
    return f"stated as {_RELATION_WORDS[stated]}, which does not establish that bound"


# ------------------------------------------------------------------ whom it is about

_RELATION_AFTER_NAME_RE = re.compile(r"\s*(?:=|≠|<|>|≤|≥|:=|↔|⇔|\bis\b|\bwas\b|\bequals?\b|\bequalled\b|\bexceeds?\b|\bof\b|\bholds\b|\bheld\b"
                                     r"|\bmeans\b|\biff\b)", _FLAGS)
_RELATION_BEFORE_NAME_RE = re.compile(r"(?:=|≠|<|>|≤|≥)\s*$")


@lru_cache(maxsize=4096)
def mentions(text: str, start: int, end: int, name: str) -> bool:
    """Whether ``text[start:end]`` names the symbol ``name`` as a formula does: the name as a whole token (the one-letter
    names "a", "A" and "I" only next to a comparison or a formula verb, "a = 3", since they are also words), or a name with
    underscores written with spaces ("tax rate" for ``tax_rate``)."""
    if not name:
        return False
    span = text[start:end]
    if name not in span and "_" not in name:
        return False
    rx = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])")
    for m in rx.finditer(span):
        if len(name) > 1 or name not in ("a", "A", "I"):
            return True
        if _RELATION_AFTER_NAME_RE.match(span, m.end()) or _RELATION_BEFORE_NAME_RE.search(span[max(0, m.start() - 8):m.start()]):
            return True
    if "_" in name:
        spaced = name.replace("_", " ").strip()
        if len(spaced) > 2 and re.search(r"(?<![A-Za-z0-9])" + re.escape(spaced) + r"(?![A-Za-z0-9])", span, _FLAGS):
            return True
    return False


@lru_cache(maxsize=4096)
def _unit_words(text: str, start: int, end: int) -> frozenset[str]:
    return content_words(text[start:end])


_PHRASE_WORD_RE = re.compile(r"[\s\-]*([A-Za-z]+(?:'[a-z]+)?)")


def _counted_words(text: str, end: int, limit: int) -> tuple[str, ...]:
    """What a figure counts: the words right after it, up to three, until a function word, a mark or the end of its unit
    ("17 items", "3 values", "seventeen African states became"), as stems; empty when none follows."""
    out: list[str] = []
    pos = end
    while len(out) < 3:
        m = _PHRASE_WORD_RE.match(text, pos, min(limit, pos + 40))
        if m is None:
            break
        word = _normal(m.group(1))
        if word in _FUNCTION_WORDS or len(word) < 2:
            break
        out.append(word if word in _GENERIC_WORDS else (_content(word) or word))
        pos = m.end()
    return tuple(out)


def link(text: str, start: int, end: int, unit: tuple[int, int], target: Target, value_only: bool = True) -> Optional[str]:
    """How the figure at ``start``-``end`` is about the ``target`` symbols, or None (see the module docstring): it does
    not count something other than they are (none of the words it counts describes them), and its unit names one of them
    or shares their words (two content words, or a word the figure counts). When nothing describes the symbols (no
    meaning, name word or label word, and no source names them) the value is the only link the encoding offers, so an
    asserted figure of that value links, unless it counts a generic quantity ("3 values"); with ``value_only`` False that
    fallback is off, and a figure links only by a name, a count or shared words (a figure of a supplied passage or of the
    task is evidence about a symbol the encoding leaves open only when its clause is about that symbol)."""
    counted = _counted_words(text, end, unit[1])
    counts_them = [w for w in counted if w in target.words]
    if counted and not counts_them and (target.described or any(w in _GENERIC_WORDS for w in counted)):
        return None  # it counts something else ("3 values", "the 2 integers y we pick")
    for name in target.names:
        if mentions(text, unit[0], unit[1], name):
            return f"names {name}"
    if counts_them:
        return f"counts {', '.join(repr(w) for w in counts_them)}, which describes {', '.join(target.names[:3])}"
    shared = sorted(_unit_words(text, unit[0], unit[1]) & target.words)
    if len(shared) >= 2 or (shared and len(target.words) == 1):
        return f"shares {', '.join(repr(w) for w in shared[:4])} with the description of {', '.join(target.names[:3])}"
    if not target.described and value_only:
        return f"its value only: nothing describes {', '.join(target.names[:3])} and no source names them"
    return None


def describing_units(texts: Iterable[str], names: Iterable[str]) -> tuple[frozenset[str], bool]:
    """``(content words, named)`` of every unit of ``texts`` that names one of ``names`` as a formula does (the source's
    own clauses about the symbols: "where b means there are exactly 17 items"); ``named`` is true when there is one."""
    wanted = [n for n in names if n]
    out: set[str] = set()
    named = False
    for text in texts:
        if not text or not any(n in text or ("_" in n and n.replace("_", " ") in text) for n in wanted):
            continue
        for a, b in units_of(text):
            if any(mentions(text, a, b, n) for n in wanted):
                named = True
                out |= _unit_words(text, a, b)
    return frozenset(out), named
