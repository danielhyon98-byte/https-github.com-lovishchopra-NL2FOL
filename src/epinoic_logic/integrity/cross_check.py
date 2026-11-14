"""Formal cross-agent checks with Z3.

Two questions that only a solver can answer soundly across agents:

1. Do the formalized claims of different specialists (and the synthesis) contradict
   each other? -> joint consistency, with the conflicting claims named from the core.
2. Does a synthesized claim actually follow from the source claims it cites? ->
   entailment of the synthesized conclusion from the union of the sources' premises.

Both rely on a SHARED GLOSSARY: symbols with the same name across problems denote
the same proposition or quantity. The translator is instructed to reuse the request's
glossary; a symbol declared with different sorts in two problems is reported as a
glossary conflict (naming both claims) and the joint check is not run; a symbol
glossed with a different meaning is reported as a warning and the check still runs.

Joint problems never embed raw claim ids in assertion ids. Each pooled problem gets a
short alias (``c0``, ``c1``, ...) and a :class:`JointMap` records which claim and
which original assertion every joint assertion id stands for, so any claim id the
contracts accept (uuid hex, ``#``, spaces, ``::``, 128 characters) can be pooled and
unsat cores are mapped back exactly, never by parsing strings.

Each source's own CONCLUSION is pooled as a premise as well (a specialist's asserted
point is something others may contradict and the combinator may rely on). A pooled
conclusion is NOT an established premise: it is given a forced grounding of kind
``specialist_inference`` so the engine always reports reliance on it, and a
synthesis that rests on one is flagged (INT-SYNTH-008) unless a prior ENTAILED
result for that exact source formalization is supplied.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from ..engine.errors import NO_VERDICT_CODES
from ..engine.policies import JOINT_LIMITS
from ..engine.provenance import binding_inconsistencies, stale_reasons, verify_signature
from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import is_ungrounded, verify
from ..engine.statuses import VerificationStatus as S
from ..ir.canonical import problem_digest, sha256_hex
from ..ir.schema import ASSERTION_ID_RE, Assertion, Grounding, Limits, Problem, Symbol
from .contracts import IntegrityFinding, Synthesis

SEP = "::"
# Joint problems union many claims; the per-claim shape limits would make cross-agent checks silently stop working at
# scale, so they run under the engine's joint limits (engine.policies.JOINT_LIMITS, part of the bound policy). A joint
# result records them and binds their digest: a receiver checking it must name JOINT_LIMITS as its required policy.
_ALIAS_RE = re.compile(r"^c\d+:")
_PREMISE_PATH_RE = re.compile(r"^premises\[(\d+)\]")
_LIMIT_CODES = frozenset({"E300", "E301", "E302", "E303", "E304", "E305", "E306"})
_UNDECIDED = frozenset({S.TIMEOUT, S.UNKNOWN, S.INTERNAL_ERROR})


@dataclass
class JointMap:
    """Alias table for one joint problem: joint assertion id -> (claim id, original id, is_conclusion)."""
    joint_id: str
    claim_ids: list[str] = field(default_factory=list)
    assertions: dict[str, tuple[str, str, bool]] = field(default_factory=dict)
    premise_owner: list[str] = field(default_factory=list)   # joint premise index -> claim id

    def claim_ids_of(self, ids: list[str]) -> list[str]:
        return sorted({self.assertions[i][0] for i in ids if i in self.assertions})

    def pooled_conclusions(self, ids: list[str]) -> list[str]:
        return [i for i in ids if i in self.assertions and self.assertions[i][2]]

    def owner_of_path(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        m = _PREMISE_PATH_RE.match(path)
        if m is None:
            return None
        idx = int(m.group(1))
        return self.premise_owner[idx] if 0 <= idx < len(self.premise_owner) else None


def _norm_meaning(m: Optional[str]) -> str:
    return " ".join((m or "").split()).casefold()


#: Words a gloss may add, drop or move without changing the quantity it names: articles, the prepositions that date a
#: stock at a year ("in 1870", "by 1870", "at 1870"), approximation words and punctuation.
_GLOSS_STOP = frozenset("the a an of in by at on about around roughly approximately approx c ca circa some nearly almost and or as for its so thus then that which is are was were be been".split())
_GLOSS_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+(?:['’-][^\W\d_]+)*")
#: A part label of a question ("part (a)", "(c)", "(ii)", "part b", "question 2(b)"): content of the gloss, never the
#: article 'a' or the circa 'c' the stop list sets aside, so 'marks allocated to part (a)' and '... part (c)' differ.
_PART_LABEL_RE = re.compile(r"\((?P<p>[a-z]|[ivx]{1,4}|\d{1,2}[a-z]?)\)|\bpart\s+(?P<q>[a-z]|[ivx]{1,4}|\d{1,2})\b(?!['’])", re.IGNORECASE)
#: Round 9 (c2, rule same-gloss): synonyms of a direction of change, folded to one stem on both sides of every comparison
#: ("Kc decreases" and "Kc falls" name one quantity), a small closed table of light stems (``ledger.light_stem``). The two
#: canonical stems are the two members of the role group "rise fall", so "increases" against "decreases" stays apart.
_GLOSS_SYNONYMS: dict[str, str] = {w: canon for canon, words in (("fall", "decreas fall fell fallen drop dropp declin sink sank sunk"),
                                                                  ("rise", "increas rise ris rose risen rising grow grew grown climb climbed"))
                                   for w in words.split()}
#: Closed compounds read as their parts ("more surface runoff" and "more rain runs off the surface"), light stems.
_GLOSS_COMPOUNDS: dict[str, tuple[str, ...]] = {"runoff": ("run", "off"), "run-off": ("run", "off")}
#: Verbs that only state that the quantity holds ("more surface runoff occurs" is "more surface runoff"), light stems.
_GLOSS_FILLERS = frozenset({"occur", "occurr", "happen"})


def _gloss_stems(tok: str) -> list[str]:
    """The stems a gloss word contributes (rule same-gloss): a hyphenated compound read as its words ("worst-case" is
    "worst" and "case", "distilled-water" is "distilled water"), each light-stemmed, a synonym of a direction of change
    folded (:data:`_GLOSS_SYNONYMS`), a closed compound split (:data:`_GLOSS_COMPOUNDS`), stop words and filler verbs left
    out (:data:`_GLOSS_STOP`, :data:`_GLOSS_FILLERS`). Words are case-folded by the caller."""
    from .ledger import light_stem
    out: list[str] = []
    for part in (tok.split("-") if "-" in tok else (tok,)):
        if not part or part in _GLOSS_STOP:
            continue
        stem = light_stem(part)
        for w in _GLOSS_COMPOUNDS.get(stem, (stem,)):
            w = _GLOSS_SYNONYMS.get(w, w)
            if w not in _GLOSS_FILLERS:
                out.append(w)
    return out


def gloss_content(meaning: Optional[str]) -> frozenset[str]:
    """The content of a symbol's gloss: its words (light-stemmed, case-folded), figures (thousands separators removed)
    and part labels ("(a)", "part c", "(ii)"), without the words that never change the quantity named
    (:data:`_GLOSS_STOP`), in any order. 'pig iron output in 1928 (million tonnes, about 3.3)' and 'pig iron output in
    1928 (about 3.3 million tonnes)' have the same content, as do 'route mileage in 1870' and 'route mileage by 1870';
    'marks allocated to part (a)' and 'marks allocated to part (c)' do not. Round 9 (c2): a hyphenated compound counts as its
    words, synonyms of a direction of change are one word and filler verbs are left out (:func:`_gloss_stems`), so 'Kc
    decreases' and 'Kc falls', or 'the distilled-water cylinder' and 'distilled water', share their content."""
    out: set[str] = set()
    text = (meaning or "").casefold()
    for m in _PART_LABEL_RE.finditer(text):
        out.add(f"({m.group('p') or m.group('q')})")
    text = _PART_LABEL_RE.sub(" part ", text)
    for tok in _GLOSS_TOKEN_RE.findall(text):
        if tok[:1].isdecimal():
            out.add(re.sub(r"(?<=\d),(?=\d{3}\b)", "", tok))
        elif tok not in _GLOSS_STOP:
            out.update(_gloss_stems(tok))
    return frozenset(out)


# ------------------------------------------------------------------------------- one quantity or two (rule same-gloss)
# Round-8 clearance (c1): the round-7 rule read two claims apart whenever their glosses of one symbol differed in any content
# word, so a real contradiction between two specialists was no longer charged when one gloss added "Montgomery", "of the
# oscillation", "as the Physics specialist gives it" or "in Diagram 1" (INT-CONFLICT-004, "no contradiction is charged"), and
# paraphrases of one quantity filled the receipts with INT-GLOSSARY-005 warnings. Two glosses of one symbol name now name
# DIFFERENT quantities only when their difference names one: a negation or a shift in time or state ("after", "new") on one
# side; a figure, part label, unit, scale, proper name or role word on each side that the other lacks ("part (a)" against
# "part (c)", "1870" against "1860", "m/s" against "km/h", "before" against "after", "Lyon" against "Paris"); or content so
# far apart that what they share is fewer than three words or less than three times what either adds ("speed of the cart"
# against "speed of the ball"). An added qualifier (an attribution phrase, a place name or a figure the other gloss does not
# contradict, "per year" beside an annual figure, "in Diagram 1", "original") names no other quantity: the symbol is one
# quantity, so a contradiction over it is INT-CONFLICT-001 and no INT-GLOSSARY-005 is raised ("East German forces closed the
# sector route on 13 August 1961" and "... closed the route in the early hours of 13 August 1961" are one statement).

#: Attribution phrases a gloss may carry ("as the Economics specialist states it", ", Economics specialist", "according to the
#: task", "as the task gives it"): who states the quantity, never another quantity.
_GLOSS_ATTRIBUTION_RE = re.compile(
    r"(?:\b(?:as|according\s+to)\s+(?:the\s+)?(?:[\w'’-]+\s+){0,3}?(?:specialist|task|question|request|text|source|report|student|answer)s?\b"
    r"(?:\s+(?:states?|stated|gives?|given|says?|said|puts?|writes?|wrote|reports?|reported|has|had|shows?|showed|uses?|used))?(?:\s+(?:it|them))?"
    r"|,\s*(?:the\s+)?(?:[\w'’-]+\s+){0,2}?specialist(?:'s|’s)?\b)", re.IGNORECASE)
#: A single letter that may label a part, area, point or option ("area a:", "point B (", "from A to B"); see :func:`_letter_labels`.
_LETTER_LABEL_RE = re.compile(r"(?<![\w'’.(])([a-hA-H])(?![\w'’])")
#: "per cent" and "%" read as the unit percent.
_PER_CENT_RE = re.compile(r"\bper[ \t]?cent\b|%", re.IGNORECASE)
#: Negation words: a gloss that negates what the other states names the opposite proposition.
_GLOSS_NEGATIONS = frozenset({"not", "no", "never", "without", "non", "neither", "nor", "none", "cannot"})
#: Scale words: "$ million" and "$ billion" are different quantities of one currency.
_GLOSS_SCALES = frozenset({"thousand", "million", "billion", "trillion", "hundred"})
#: Unit words and symbols, each read as its canonical unit ("metres", "metre", "m" are one unit). A symbol of one or two
#: letters is read as a unit only after "in", "per", a figure or a slash, or before a slash ("m/s", "in m", "2.0 cm").
_UNIT_FORMS: dict[str, str] = {}
for _canon, _forms in {
    "m": "metre metres meter meters", "cm": "centimetre centimetres centimeter centimeters", "mm": "millimetre millimetres millimeter millimeters",
    "km": "kilometre kilometres kilometer kilometers", "s": "second seconds sec secs", "ms": "millisecond milliseconds", "min": "minute minutes mins",
    "h": "hour hours hr hrs", "kg": "kilogram kilograms", "g": "gram grams", "mg": "milligram milligrams", "t": "tonne tonnes ton tons",
    "n": "newton newtons", "j": "joule joules", "kj": "kilojoule kilojoules", "w": "watt watts", "kw": "kilowatt kilowatts",
    "pa": "pascal pascals", "v": "volt volts", "amp": "amp amps ampere amperes", "mol": "mole moles", "l": "litre litres liter liters",
    "ml": "millilitre millilitres milliliter milliliters", "k": "kelvin", "degc": "celsius", "hz": "hertz", "rad": "radian radians",
    "dollar": "dollar dollars", "pound": "pounds", "euro": "euro euros", "percent": "percent percentage", "day": "day days",
    "week": "week weeks", "month": "month months", "year": "year years yr yrs annual annually",
}.items():
    for _f in _forms.split():
        _UNIT_FORMS[_f] = _canon
#: Unit symbols read as units only in a unit position (see :data:`_UNIT_FORMS`).
_UNIT_SYMBOLS = frozenset("m cm mm km s ms min h kg g mg t n j kj w kw pa kpa v mol l ml dm k hz rad".split())
#: Role words: two members of one group on the two sides name different quantities ("before" against "after").
_GLOSS_ROLE_GROUPS: tuple[frozenset[str], ...] = ()
#: Words that move a quantity in time or state even when only one gloss carries them: "low after pass 1" is not "low on pass
#: 1", and "the new period" (after the mass is doubled) is not "the period". "original" is no such word: "the period of the
#: original oscillation" is the period.
_GLOSS_SHIFT_WORDS = frozenset({"before", "after", "new", "initial", "final", "previous", "next", "later", "earlier", "prior", "doubled", "halved",
                                "tripled", "changed"})
#: Proper names a gloss carries ("Calvessa", "Montgomery"): capitalised words not at the gloss's start.
_PROPER_NAME_RE = re.compile(r"(?<=[\w,;:)’'] )([A-Z][a-z][a-z'’-]+)")


@dataclass(frozen=True)
class GlossReading:
    """What a gloss names, by kind (rule ``same-gloss``): its content words and figures (:func:`gloss_content` with the
    attribution phrases and proper names set aside), and the figures, labels, units, scales, proper names, role words and
    negations it states."""
    content: frozenset[str]
    figures: frozenset[str]
    labels: frozenset[str]
    units: frozenset[str]
    scales: frozenset[str]
    names: frozenset[str]
    roles: frozenset[str]
    negated: bool
    shifts: frozenset[str] = frozenset()


def _role_groups() -> tuple[frozenset[str], ...]:
    global _GLOSS_ROLE_GROUPS
    if not _GLOSS_ROLE_GROUPS:
        from .ledger import light_stem
        _GLOSS_ROLE_GROUPS = tuple(frozenset(light_stem(w) for w in g.split()) for g in (
            "before after", "pre post", "initial final", "start end", "opening closing", "original new", "old new", "first second third fourth fifth last",
            "minimum maximum", "min max", "lower upper", "lowest highest", "input output", "import export", "demand supply", "buyer seller",
            "consumer producer", "increase decrease", "rise fall", "gain loss", "inflow outflow", "income expenditure", "nominal real",
            "gross net", "private public", "domestic foreign", "internal external", "marginal average total", "fixed variable",
            "short long", "male female", "positive negative", "red blue green yellow black white orange purple pink brown grey gray",
            "experimental control", "observed expected predicted", "actual planned budgeted forecast", "current previous next", "measured corrected",
            "past present future", "inner outer", "top bottom", "horizontal vertical", "north south east west", "left right",
            "morning afternoon evening night", "spring summer autumn winter", "primary secondary tertiary", "urban rural", "rich poor",
            "january february march april may june july august september october november december",
            "monday tuesday wednesday thursday friday saturday sunday"))
    return _GLOSS_ROLE_GROUPS


def _letter_labels(raw: str) -> set[str]:
    """The single letters of a gloss that label a part, area, point or option: a capital B to H anywhere; a capital A unless
    it opens the gloss or a sentence before a lower-case word (the article "A firm ..."); a lower-case letter only when no
    word follows it ("area a:", "curve c,"), so never the article of "a reward". A letter followed by a full stop or a
    figure ("c. 1900", "c 1900", "a 5% rise") is no label."""
    out: set[str] = set()
    for m in _LETTER_LABEL_RE.finditer(raw):
        ch = m.group(1)
        rest = raw[m.end():m.end() + 3]
        if rest[:1] == "." or rest.lstrip()[:1].isdigit():
            continue
        follows_word = bool(rest[:1].isspace() and rest.lstrip()[:1].isalpha())
        if ch.islower() and follows_word:
            continue
        if ch == "A" and follows_word and rest.lstrip()[:1].islower():
            before = raw[:m.start()].rstrip()
            if not before or before[-1] in ".!?:;":
                continue
        out.add(f"({ch.casefold()})")
    return out


def gloss_reading(meaning: Optional[str]) -> GlossReading:
    """The :class:`GlossReading` of one gloss (rule ``same-gloss``). Linear in the gloss: each pattern is a single pass
    with bounded runs."""
    from .ledger import light_stem
    raw = _PER_CENT_RE.sub(" percent ", _GLOSS_ATTRIBUTION_RE.sub(" ", meaning or ""))
    capitalised = [m.group(1) for m in _PROPER_NAME_RE.finditer(raw)]
    words = len(_GLOSS_TOKEN_RE.findall(raw))
    # a gloss in title case ("the Price of Steel") names no proper name by its capitals
    names = frozenset(light_stem(w.casefold()) for w in capitalised) if 2 * len(capitalised) <= max(words - 1, 1) else frozenset()
    text = raw.casefold()
    labels = {f"({m.group('p') or m.group('q')})" for m in _PART_LABEL_RE.finditer(text)}
    text = _PART_LABEL_RE.sub(" part ", text)
    labels |= _letter_labels(raw)
    figures: set[str] = set()
    units: set[str] = set()
    scales: set[str] = set()
    roles: set[str] = set()
    shifts: set[str] = set()
    negated = False
    content: set[str] = set()
    toks = list(_GLOSS_TOKEN_RE.finditer(text))
    groups = _role_groups()
    for i, m in enumerate(toks):
        whole = m.group(0)
        if whole[:1].isdecimal():
            fig = re.sub(r"(?<=\d),(?=\d{3}\b)", "", whole)
            figures.add(fig)
            content.add(fig)
            continue
        # round 9 (c2): a hyphenated compound is read as its words ("worst-case", "distilled-water", "non-renewable")
        for tok in (whole.split("-") if "-" in whole else (whole,)):
            if not tok:
                continue
            if tok in _GLOSS_NEGATIONS or tok.endswith(("n't", "n’t")):
                negated = True
                continue
            if tok in _GLOSS_SCALES:
                scales.add(tok)
            if tok in _GLOSS_SHIFT_WORDS:
                shifts.add(tok)
            unit = _UNIT_FORMS.get(tok)
            if unit is None and tok in _UNIT_SYMBOLS and tok == whole:
                before = text[max(0, m.start() - 2):m.start()]
                prev = toks[i - 1].group(0) if i else ""
                after = text[m.end():m.end() + 1]
                if before.endswith("/") or after == "/" or prev in ("in", "per") or prev[:1].isdecimal():
                    unit = tok
            if unit is not None:
                units.add(unit)
                content.add(f"[{unit}]")
                continue
            if tok in _GLOSS_STOP:
                continue
            for stem in _gloss_stems(tok):
                for g in groups:
                    if stem in g:
                        roles.add(stem)
                        break
                content.add(stem)
    content |= labels
    return GlossReading(frozenset(content), frozenset(figures), frozenset(labels), frozenset(units), frozenset(scales), names, frozenset(roles), negated,
                        frozenset(shifts))


def gloss_difference(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Why two glosses of one symbol name DIFFERENT quantities (rule ``same-gloss``), or None when they name one: equal
    glosses, the same content in another order, or one a qualified form of the other. Different only when the difference
    names one: a negation, or a shift in time or state (:data:`_GLOSS_SHIFT_WORDS`), on one side; a figure, part label, unit, scale, proper name or role word on each side that the
    other lacks; or content so far apart that what the glosses share is fewer than three words or less than three times
    what either adds."""
    if _norm_meaning(a) == _norm_meaning(b) or gloss_content(a) == gloss_content(b):
        return None
    ra, rb = gloss_reading(a), gloss_reading(b)
    if ra.negated != rb.negated:
        return "one gloss negates what the other states"
    if ra.shifts != rb.shifts:
        return f"a shift in time or state ({sorted(ra.shifts ^ rb.shifts)}) only one gloss states"
    for kind, xa, xb in (("figures", ra.figures, rb.figures), ("part labels", ra.labels, rb.labels), ("units", ra.units, rb.units),
                         ("scales", ra.scales, rb.scales), ("proper names", ra.names, rb.names)):
        if xa - xb and xb - xa:
            return f"{kind} {sorted(xa - xb)} against {sorted(xb - xa)}"
    for g in _role_groups():
        ga, gb = (ra.roles & g) - rb.roles, (rb.roles & g) - ra.roles
        if ga and gb:
            return f"role words {sorted(ga)} against {sorted(gb)}"
    ca, cb = ra.content, rb.content
    if ca <= cb or cb <= ca:
        return None
    shared = ca & cb
    extra = max(len(ca - cb), len(cb - ca))
    if len(shared) >= 3 and len(shared) >= 3 * extra:
        return None
    return f"content {sorted(ca - cb)} against {sorted(cb - ca)}"


#: How INT-GLOSSARY-005 ends: a joint problem that pools the symbol as one quantity (synthesis entailment) or one that
#: reads the glosses apart (the consistency check, :func:`split_by_gloss`).
_POOLED_AS_ONE = "the joint check assumes they denote the same quantity"
_READ_APART = ("the consistency check reads them as different quantities (the symbol is renamed apart per claim), so no contradiction is "
               "charged on this shared name; one name for two quantities is a translation fault, not the specialist's")


def _merge_symbols(problems: list[Problem], *, read_apart: bool = False) -> tuple[list[Symbol], list[IntegrityFinding]]:
    seen: dict[str, tuple[Symbol, str]] = {}
    findings: list[IntegrityFinding] = []
    for p in problems:
        for s in p.symbols:
            prior = seen.get(s.name)
            if prior is None:
                seen[s.name] = (s, p.claim_id)
                continue
            prior_sym, prior_claim = prior
            if prior_sym.sort != s.sort:
                findings.append(IntegrityFinding(code="INT-GLOSSARY-001", severity="error", message=f"symbol {s.name!r} declared as {prior_sym.sort} in claim {prior_claim!r} and as {s.sort} in claim {p.claim_id!r}; shared glossary violated", claim_ids=sorted({prior_claim, p.claim_id})))
            else:
                a, b = _norm_meaning(prior_sym.meaning), _norm_meaning(s.meaning)
                # the same words and figures in another order or with another "in"/"by", or one gloss a qualified form of the
                # other (rule same-gloss: an attribution, a place name, "per year", "in Diagram 1"), are one meaning
                why = gloss_difference(prior_sym.meaning, s.meaning) if a and b and a != b else None
                if why is not None:
                    ca, cb = gloss_content(prior_sym.meaning), gloss_content(s.meaning)
                    only_a, only_b = sorted(ca - cb), sorted(cb - ca)
                    what = "; ".join(x for x in (f"only the first states {only_a}" if only_a else "", f"only the second states {only_b}" if only_b else "", f"they name different quantities by {why}") if x)
                    findings.append(IntegrityFinding(code="INT-GLOSSARY-005", severity="warning", message=f"symbol {s.name!r} ({s.sort}) is glossed with different meanings across claims: {prior_sym.meaning!r} in {prior_claim!r} vs {s.meaning!r} in {p.claim_id!r} ({what}); {_READ_APART if read_apart else _POOLED_AS_ONE}", claim_ids=sorted({prior_claim, p.claim_id})))
            if not prior_sym.meaning and s.meaning:
                seen[s.name] = (s, p.claim_id)
    return [v[0] for v in seen.values()], findings


def _symbol_components(problem: Problem) -> dict[str, str]:
    """Per symbol of ``problem``, a representative of its connected component in the problem's assertions (two symbols
    are connected when one assertion, the conclusion included, uses both): the quantities computed together."""
    parent = {sym.name: sym.name for sym in problem.symbols}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a in [*problem.premises, *([problem.conclusion] if problem.conclusion is not None else [])]:
        names = sorted(n for n in _needed_symbols(a) if n in parent)
        for n in names[1:]:
            ra, rb = find(names[0]), find(n)
            if ra != rb:
                parent[rb] = ra
    return {n: find(n) for n in parent}


def split_by_gloss(problems: list[Problem]) -> tuple[list[Problem], dict[str, list[tuple[str, list[str], str]]]]:
    """The problems with symbols renamed apart wherever one name stands for different quantities:

    * a symbol whose glosses name different quantities in two claims (:func:`gloss_difference`, rule same-gloss: 'the target
      is 67' in one claim, 'the target is 20' in another; 'marks allocated to part (a)' and '... part (c)'; never a gloss
      that only qualifies the other, 'amplitude' and 'amplitude of the oscillation');
    * and, between two claims that so gloss a shared symbol differently, every other shared symbol that either claim
      computes together with it (connected to it through its own assertions: 'low on pass 1' of a search for the target
      67 is not 'low on pass 1' of a search for 20, whatever the glosses say).

    Claims that do not so differ keep one name: the first group of claims keeps the original name, each other group gets
    ``<name>_g<k>``. Two claims that gloss a symbol alike and never gloss a shared symbol differently still share all
    their symbols, so their contradictions are found as before. Returns the problems (unchanged when nothing differs)
    and, per original name that was split, ``(name used, claim ids, gloss)`` for each group."""
    n = len(problems)
    content: list[dict[str, Optional[str]]] = []
    shown: list[dict[str, str]] = []
    differs_memo: dict[tuple[str, str], bool] = {}

    def differs(x: Optional[str], y: Optional[str]) -> bool:
        """Whether two glosses (normalised meanings; None for no gloss) name different quantities (rule same-gloss)."""
        if x is None or y is None or x == y:
            return False
        key = (x, y) if x <= y else (y, x)
        if key not in differs_memo:
            differs_memo[key] = gloss_difference(x, y) is not None
        return differs_memo[key]
    comps = [_symbol_components(p) for p in problems]
    sorts: dict[str, set[str]] = {}
    holders: dict[str, list[int]] = {}
    for i, p in enumerate(problems):
        content.append({})
        shown.append({})
        for sym in p.symbols:
            sorts.setdefault(sym.name, set()).add(sym.sort)
            holders.setdefault(sym.name, []).append(i)
            content[i][sym.name] = " ".join((sym.meaning or "").split()) if _norm_meaning(sym.meaning) else None
            shown[i][sym.name] = sym.meaning or ""
    # clash[(i, j)]: the shared symbols claims i and j gloss with different content (same sort; a sort clash withholds the check)
    clash: dict[tuple[int, int], set[str]] = {}
    for name, idxs in holders.items():
        if len(idxs) < 2 or len(sorts[name]) > 1:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if differs(content[i][name], content[j][name]):
                    clash.setdefault((i, j), set()).add(name)
    if not clash:
        return list(problems), {}

    def apart(i: int, j: int, name: str) -> bool:
        i, j = min(i, j), max(i, j)
        if differs(content[i][name], content[j][name]):
            return True
        return any(comps[i].get(name) == comps[i].get(t) or comps[j].get(name) == comps[j].get(t) for t in clash.get((i, j), ()))

    taken = {sym.name for p in problems for sym in p.symbols}
    rename: dict[int, dict[str, str]] = {}
    splits: dict[str, list[tuple[str, list[str], str]]] = {}
    for name, idxs in holders.items():
        if len(idxs) < 2 or len(sorts[name]) > 1:
            continue
        groups: list[list[int]] = []
        for i in idxs:
            for g in groups:
                if not any(apart(i, j, name) for j in g):
                    g.append(i)
                    break
            else:
                groups.append([i])
        if len(groups) < 2:
            continue
        splits[name] = []
        for k, g in enumerate(groups):
            new = name
            if k:
                m = k + 1
                new = f"{name[:56]}_g{m}"
                while new in taken:
                    m += 1
                    new = f"{name[:56]}_g{m}"
                taken.add(new)
                for i in g:
                    rename.setdefault(i, {})[name] = new
            splits[name].append((new, [problems[i].claim_id for i in g], next((shown[i][name] for i in g if shown[i][name]), "")))
    out: list[Problem] = []
    for i, p in enumerate(problems):
        table = rename.get(i)
        out.append(_renamed(p, table) if table else p)
    return out, splits


def _renamed(problem: Problem, table: dict[str, str]) -> Problem:
    """``problem`` with its symbols renamed by ``table`` (declarations and every ``var`` node)."""
    data = problem.model_dump(mode="json", exclude_none=True)

    def walk(node):
        if isinstance(node, dict):
            if node.get("op") == "var" and node.get("name") in table:
                node["name"] = table[node["name"]]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    for sym in data.get("symbols", []):
        if sym.get("name") in table:
            sym["name"] = table[sym["name"]]
    walk(data.get("premises", []))
    walk(data.get("conclusion"))
    return Problem.model_validate(data)


# ------------------------------------------------------------------------- a candidate value the claim rejects (rule candidate)
# Round-8 clearance (c1, maa-t14): "x = −5 is rejected because it does not satisfy x > 4" was translated with the premise
# x = −5 on the report-wide unknown x, the same symbol and gloss under which m6.1 states the domain x > 4, so the pool charged
# the specialist an error-level contradiction (INT-CONFLICT-001) and demanded its disclosure from the synthesis
# (INT-CONFLICT-002). A claim that assigns a value and states that the value fails a condition is testing a candidate: its
# value is a hypothetical, never an assertion about the unknown the other claims solve for. Such a claim's candidate symbol, and
# every symbol its own assertions compute with it, is renamed apart before pooling (``<name>_h<k>``); a contradiction that
# exists only with the candidate pooled is INT-CONFLICT-004 (warning, nothing charged and nothing to disclose). The claim's
# own consistency is still checked: "x = 5 is rejected because it does not satisfy x > 4" refutes itself (INT-CONFLICT-005).

#: The words with which a translation describes a value the claim tests and rejects, rules out or supposes (in the
#: conclusion's label or id, or the label or id of the premise that assigns the value).
_CANDIDATE_CUE_RE = re.compile(
    r"\b(?:reject(?:s|ed|ing)?|candidate(?:s)?|extraneous|discard(?:s|ed|ing)?|rul(?:e|es|ed|ing)[ \t-]{1,3}out|not[ \t]{1,3}(?:a[ \t]{1,3})?(?:valid[ \t]{1,3})?(?:solution|root)s?"
    r"|invalid[ \t]{1,3}(?:solution|root)s?|inadmissible|does[ \t]{1,3}not[ \t]{1,3}satisfy|doesn['’]t[ \t]{1,3}satisfy|fails?[ \t]{1,3}(?:the[ \t]{1,3})?(?:domain|condition|restriction|requirement)"
    r"|(?:outside|not[ \t]{1,3}in)[ \t]{1,3}(?:the[ \t]{1,3})?domain|suppos(?:e|es|ed|ing)|trial[ \t]{1,3}value)\b", re.IGNORECASE)
_CONSTANT_OPS = frozenset({"int", "real"})


def _is_constant(node) -> bool:
    op = getattr(node, "op", None)
    return op in _CONSTANT_OPS or (op == "neg" and getattr(getattr(node, "arg", None), "op", None) in _CONSTANT_OPS)


def _assigned_symbol(expr) -> Optional[str]:
    """The symbol ``expr`` assigns a constant to (``x = -5`` or ``-5 = x``), or None."""
    if getattr(expr, "op", None) != "eq":
        return None
    left, right = expr.left, expr.right
    if getattr(left, "op", None) == "var" and _is_constant(right):
        return left.name
    if getattr(right, "op", None) == "var" and _is_constant(left):
        return right.name
    return None


def _top_conjuncts(expr) -> list:
    out, stack = [], [expr]
    while stack:
        node = stack.pop()
        if getattr(node, "op", None) == "and":
            stack.extend(reversed(node.args))
        else:
            out.append(node)
    return out


def candidate_tests(problem: Problem) -> dict[str, str]:
    """The symbols of ``problem`` whose value the claim tests as a candidate and rejects (rule ``candidate``), each with the
    id of the assertion that assigns the value. A symbol ``x`` qualifies when the problem asserts ``x = c`` for a constant
    ``c`` (a premise, or a conjunct of its conclusion), its conclusion asserts a NEGATED condition on ``x`` (a conjunct
    ``not φ``, or ``l != r`` other than ``x != c``, where ``φ`` mentions ``x`` or a Boolean symbol a premise defines from ``x``)
    and the translation describes the value as tested and rejected (:data:`_CANDIDATE_CUE_RE` in the conclusion's label or id
    or the assigning assertion's label or id). Data on data: nothing is evaluated."""
    if problem.query != "entailment" or problem.conclusion is None:
        return {}
    assigning: dict[str, Assertion] = {}
    for a in [*problem.premises, *[problem.conclusion.model_copy(update={"expr": c}) for c in _top_conjuncts(problem.conclusion.expr)]]:
        name = _assigned_symbol(a.expr)
        if name is not None:
            assigning.setdefault(name, a)
    if not assigning:
        return {}
    defined: dict[str, set[str]] = {}  # a Boolean symbol defined by a premise ("dom <-> x > 4") -> the symbols of its definition
    for pr in problem.premises:
        e = pr.expr
        if getattr(e, "op", None) in ("iff", "eq"):
            for side, other in ((e.left, e.right), (e.right, e.left)):
                if getattr(side, "op", None) == "var":
                    defined.setdefault(side.name, set()).update(_expr_symbols(other))
    negated: set[str] = set()
    for c in _top_conjuncts(problem.conclusion.expr):
        op = getattr(c, "op", None)
        if op == "not":
            inner = _expr_symbols(c.arg)
        elif op == "ne" and not ((getattr(c.left, "op", None) == "var" and _is_constant(c.right)) or (getattr(c.right, "op", None) == "var" and _is_constant(c.left))):
            inner = _expr_symbols(c)  # "x != 5" beside "x = 7" corrects a value; it tests no candidate
        else:
            continue
        for n in list(inner):
            inner |= defined.get(n, set())
        negated |= inner
    out: dict[str, str] = {}
    for name, a in assigning.items():
        if name not in negated:
            continue
        cue_text = " ".join(x for x in (problem.conclusion.label, problem.conclusion.id, a.label, a.id) if x)
        if _CANDIDATE_CUE_RE.search(cue_text):
            out[name] = a.id
    return out


def _expr_symbols(expr) -> set[str]:
    out: set[str] = set()
    stack = [expr]
    while stack:
        n = stack.pop()
        if getattr(n, "op", None) == "var":
            out.add(n.name)
        for fld in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(n, fld, None)
            if child is not None:
                stack.append(child)
        stack.extend(getattr(n, "args", None) or ())
    return out


def rename_candidates_apart(problems: list[Problem]) -> tuple[list[Problem], dict[str, list[tuple[str, str, str]]]]:
    """The problems with each candidate a claim tests and rejects (:func:`candidate_tests`) renamed apart, together with
    every symbol the claim's own assertions compute with it, and per such claim ``(name, name used, assigning assertion id)``.
    Problems with no candidate are returned unchanged."""
    taken = {sym.name for p in problems for sym in p.symbols}
    out: list[Problem] = []
    info: dict[str, list[tuple[str, str, str]]] = {}
    for p in problems:
        tested = candidate_tests(p)
        if not tested:
            out.append(p)
            continue
        comps = _symbol_components(p)
        roots = {comps[n] for n in tested if n in comps}
        table: dict[str, str] = {}
        for sym in p.symbols:
            if comps.get(sym.name) in roots:
                k = 1
                new = f"{sym.name[:56]}_h{k}"
                while new in taken:
                    k += 1
                    new = f"{sym.name[:56]}_h{k}"
                taken.add(new)
                table[sym.name] = new
        out.append(_renamed(p, table))
        info[p.claim_id] = [(n, table.get(n, n), tested[n]) for n in sorted(tested)]
    return out, info


# ----------------------------------------------------------------- a value a claim evaluates or checks at (rule evaluation-point)
# Round 9 (c2, maa-t15): "Check: at x = 0, g(0) = 3 and h(3) = 1 = 0 + 1." was translated with the premise x = 0 ("the check is
# made at x = 0") on the report-wide unknown x, which m7.1 constrains through the equation to solve ((h∘g)(x) = g⁻¹(x), whose
# root is x = −5): the pool charged the specialist an error-level contradiction (INT-CONFLICT-001) and demanded its disclosure
# from the synthesis (INT-CONFLICT-002). A claim that evaluates or checks an expression at a stated value of a variable states
# what holds AT that point: the point is a hypothetical value, never an assertion about the unknown the other claims solve
# for. Such a claim's point symbol, and every numeric symbol its own premises define from it ("gx = 2x + 3": g at the point),
# is renamed apart before pooling, into a copy keyed by the symbol and the value (``<name>_at_<value>``), so two claims that
# evaluate at the same point still share it and contradict each other there; a contradiction that exists only with the point
# pooled is INT-CONFLICT-004 (warning, nothing charged and nothing to disclose). The rule reads the translation's own labels
# (data, never evaluated): a premise that fixes a numeric symbol at a constant, where that premise's label or the
# conclusion's label states the point in the form "at x = 0" (also "when", "for", "with", "if", "where", "substituting",
# "testing", "trying", "putting", "setting"), naming the symbol or the value the premise gives. The Overseer's re-check of a
# named conflict reads the same form in the claim's text (its rule evaluation-point); its independent joint check calls this
# function, so the receipt and the audit read the pool alike.

#: An evaluation point as a label states it: a lead word, a symbol name and a value ("at x = 0", "when t = −2.5").
_EVAL_POINT_RE = re.compile(
    r"\b(?:at|when|for|with|if|where|substitut(?:e|es|ed|ing)|test(?:s|ed|ing)?|try(?:ing)?|tried|putting|setting)[ \t]{1,3}"
    r"([A-Za-z][A-Za-z0-9_]{0,15})[ \t]{0,3}=[ \t]{0,3}([−-]?)[ \t]{0,2}(\d{1,12}(?:\.\d{1,12})?)(?![\d.])", re.IGNORECASE)
_NUMERIC_SORTS = frozenset({"Int", "Real"})


def _constant_value(node) -> Optional[Fraction]:
    """The value of a constant node (``int``, ``real`` or the negation of one), or None."""
    op = getattr(node, "op", None)
    try:
        if op in _CONSTANT_OPS:
            return Fraction(str(node.value))
        if op == "neg" and getattr(getattr(node, "arg", None), "op", None) in _CONSTANT_OPS:
            return -Fraction(str(node.arg.value))
    except (ValueError, ZeroDivisionError):
        return None
    return None


def _stated_points(text: Optional[str]) -> list[tuple[str, Fraction]]:
    """``(name, value)`` for every evaluation point ``text`` (a label) states in the form of :data:`_EVAL_POINT_RE`."""
    out: list[tuple[str, Fraction]] = []
    for m in _EVAL_POINT_RE.finditer((text or "")[:1000]):
        try:
            v = Fraction(m.group(3))
        except (ValueError, ZeroDivisionError):
            continue
        out.append((m.group(1), -v if m.group(2) else v))
    return out


def evaluation_points(problem: Problem) -> dict[str, tuple[str, Fraction]]:
    """The numeric symbols of ``problem`` that a premise fixes at a value the claim evaluates or checks at (rule
    ``evaluation-point``), each with the id of that premise and the value: the premise is ``x = c`` for a constant ``c``,
    and its label or the conclusion's label states the point ("at x = 0"), naming ``x`` (case aside) or, when the name it
    states is no symbol of the problem, the value ``c`` that only this premise gives one symbol. Data on data: nothing is
    evaluated."""
    sorts = {sym.name: sym.sort for sym in problem.symbols}
    fixed: dict[str, list[tuple[Assertion, Fraction]]] = {}
    for pr in problem.premises:
        e = pr.expr
        if getattr(e, "op", None) != "eq":
            continue
        for var, lit in ((e.left, e.right), (e.right, e.left)):
            v = _constant_value(lit)
            if getattr(var, "op", None) == "var" and v is not None and sorts.get(var.name) in _NUMERIC_SORTS:
                fixed.setdefault(var.name, []).append((pr, v))
    if not fixed:
        return {}
    by_lower = {n.casefold(): n for n in sorts}
    out: dict[str, tuple[str, Fraction]] = {}
    concl_label = problem.conclusion.label if problem.conclusion is not None else None
    for name, rows in fixed.items():
        for pr, value in rows:
            for stated, v in _stated_points(pr.label) + _stated_points(concl_label):
                if v != value:
                    continue
                named = by_lower.get(stated.casefold())
                if named == name or (named is None and [n for n, rs in fixed.items() if any(x == value for _p, x in rs)] == [name]):
                    out.setdefault(name, (pr.id, value))
                    break
            if name in out:
                break
    return out


def _point_tag(value: Fraction) -> str:
    """A symbol-name tag for a value: 0 -> '0', -5 -> 'm5', 2.5 -> '2p5', 1/3 -> '1d3'."""
    sign = "m" if value < 0 else ""
    a = abs(value)
    if a.denominator == 1:
        return f"{sign}{a.numerator}"
    d = a.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:  # a terminating decimal
        whole, frac = divmod(a.numerator, a.denominator)
        digits = ""
        rest = frac
        while rest and len(digits) < 12:
            rest *= 10
            digits += str(rest // a.denominator)
            rest %= a.denominator
        return f"{sign}{whole}p{digits}"
    return f"{sign}{a.numerator}d{a.denominator}"


def rename_evaluation_points_apart(problems: list[Problem]) -> tuple[list[Problem], dict[str, list[tuple[str, str, str]]]]:
    """The problems with each value a claim evaluates or checks at (:func:`evaluation_points`) renamed apart, together with
    every numeric symbol the claim's own premises define from it, into a copy keyed by the symbol and the value
    (``x_at_0``, ``gx_at_0``), so claims evaluating at one point share it; and per such claim ``(name, name used, assigning
    premise id)``. Problems with no evaluation point are returned unchanged."""
    taken = {sym.name for p in problems for sym in p.symbols}
    keyed: dict[tuple[str, str], str] = {}
    out: list[Problem] = []
    info: dict[str, list[tuple[str, str, str]]] = {}
    for p in problems:
        points = evaluation_points(p)
        if not points:
            out.append(p)
            continue
        sorts = {sym.name: sym.sort for sym in p.symbols}
        table: dict[str, str] = {}
        rows: list[tuple[str, str, str]] = []
        for name, (aid, value) in sorted(points.items()):
            tag = _point_tag(value)
            names = [name]
            changed = True
            while changed and len(names) < len(sorts):  # a fixed point over the claim's own premises, bounded by its symbols
                changed = False
                for pr in p.premises:
                    e = pr.expr
                    if getattr(e, "op", None) != "eq":
                        continue
                    for var, rhs in ((e.left, e.right), (e.right, e.left)):
                        if getattr(var, "op", None) == "var" and sorts.get(var.name) in _NUMERIC_SORTS and var.name not in names and _expr_symbols(rhs) & set(names):
                            names.append(var.name)
                            changed = True
            for n in names:
                if n in table:
                    continue
                key = (n, tag)
                new = keyed.get(key)
                if new is None:
                    new = f"{n[:48]}_at_{tag}"[:64]
                    k = 1
                    while new in taken:
                        k += 1
                        new = f"{n[:44]}_at_{tag}"[:58] + f"_{k}"
                    taken.add(new)
                    keyed[key] = new
                table[n] = new
            rows.append((name, table[name], aid))
        try:
            out.append(_renamed(p, table))
        except Exception:  # noqa: BLE001 - a problem that cannot be renamed is pooled as it is
            out.append(p)
            continue
        info[p.claim_id] = rows
    return out, info


def _pooled_grounding(orig: Optional[Grounding]) -> Grounding:
    return Grounding(kind="specialist_inference", certainty=orig.certainty if orig is not None else "probable", verified=None, note="pooled specialist conclusion; it is an asserted point, not an established premise")


def _prefixed_premises(problems: list[Problem], jmap: JointMap) -> list[Assertion]:
    out: list[Assertion] = []
    for i, p in enumerate(problems):
        alias = f"c{i}"
        jmap.claim_ids.append(p.claim_id)
        for k, a in enumerate(p.premises):
            jid = f"{alias}{SEP}{a.id}"
            if len(jid) > 128 or not ASSERTION_ID_RE.match(jid):
                jid = f"{alias}:p{k}"
            jmap.assertions[jid] = (p.claim_id, a.id, False)
            jmap.premise_owner.append(p.claim_id)
            out.append(a.model_copy(update={"id": jid}))
        if p.conclusion is not None and p.query == "entailment":
            c = p.conclusion
            jid = f"{alias}:C:{c.id}"
            if len(jid) > 128:
                jid = f"{alias}:C"
            jmap.assertions[jid] = (p.claim_id, c.id, True)
            jmap.premise_owner.append(p.claim_id)
            out.append(c.model_copy(update={"id": jid, "grounding": _pooled_grounding(c.grounding)}))
    return out


def claim_ids_from_core(core: list[str], id_map: Optional[JointMap] = None) -> list[str]:
    """Map joint assertion ids back to claim ids through the alias table.

    Without ``id_map`` the deprecated string-splitting fallback is used; it is wrong
    for claim ids containing '::' and is kept only for callers of the old signature."""
    if id_map is not None:
        return id_map.claim_ids_of(core)
    return sorted({pid.split(SEP, 1)[0] for pid in core if SEP in pid})


def _needed_symbols(a: Assertion) -> set[str]:
    out: set[str] = set()
    stack = [a.expr]
    while stack:
        n = stack.pop()
        op = getattr(n, "op", None)
        if op == "var":
            out.add(n.name)
        for fld in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(n, fld, None)
            if child is not None:
                stack.append(child)
        for child in getattr(n, "args", []) or []:
            stack.append(child)
    return out


def _joint_problem_id(joint_id: str) -> str:
    pid = f"joint-{joint_id}"
    return pid if len(pid) <= 128 else f"joint-{sha256_hex(joint_id)[:32]}"


def joint_problem(problems: list[Problem], *, request_id: str, joint_id: str = "joint", query: str = "consistency", conclusion: Optional[Assertion] = None) -> tuple[Optional[Problem], list[IntegrityFinding], JointMap]:
    """Pool the problems under one glossary. Returns (problem or None, findings, alias map).

    Warnings (INT-GLOSSARY-005) are returned alongside a built problem; errors
    (INT-GLOSSARY-001/003/004) withhold it."""
    jmap = JointMap(joint_id=joint_id)
    if not problems:
        return None, [IntegrityFinding(code="INT-GLOSSARY-002", severity="info", message="no formalized claims to cross-check", claim_ids=[joint_id] if conclusion is not None else [])], jmap
    all_ids = [p.claim_id for p in problems]
    if len(set(all_ids)) != len(all_ids):
        dups = sorted({c for c in all_ids if all_ids.count(c) > 1})
        return None, [IntegrityFinding(code="INT-GLOSSARY-004", severity="error", message=f"joint problem could not be built: several formalizations carry the same claim id {dups}", claim_ids=dups)], jmap
    symbols, findings = _merge_symbols(problems)
    if any(f.severity == "error" for f in findings):
        return None, findings, jmap
    if conclusion is not None:
        names = {x.name for x in symbols}
        missing = sorted(s for s in _needed_symbols(conclusion) if s not in names)
        if missing:
            findings.append(IntegrityFinding(code="INT-GLOSSARY-003", severity="error", message=f"synthesized conclusion uses symbols {missing} that no cited source claim defines", claim_ids=[joint_id]))
            return None, findings, jmap
    premises = _prefixed_premises(problems, jmap)
    data = {"problem_id": _joint_problem_id(joint_id), "request_id": request_id, "claim_id": joint_id, "query": query,
            "symbols": [s.model_dump(mode="json", exclude_none=True) for s in symbols],
            "premises": [a.model_dump(mode="json", exclude_none=True) for a in premises]}
    if conclusion is not None:
        cid = conclusion.id if not _ALIAS_RE.match(conclusion.id) else "SYNTH"
        data["conclusion"] = conclusion.model_copy(update={"id": cid}).model_dump(mode="json", exclude_none=True)
    try:
        return Problem.model_validate(data), findings, jmap
    except Exception as exc:  # oversized or malformed merge
        findings.append(IntegrityFinding(code="INT-GLOSSARY-004", severity="error", message=f"joint problem could not be built from claims {all_ids}: {type(exc).__name__}: {str(exc)[:500]}", claim_ids=sorted(set(all_ids))))
        return None, findings, jmap


def _classify_failure(result: VerificationResult, jmap: JointMap, *, synthesized_claim_id: Optional[str], undecided_code: str) -> list[IntegrityFinding]:
    """Turn a non-verdict joint result into findings that name the responsible party."""
    pooled = sorted(set(jmap.claim_ids))
    base_ids = ([synthesized_claim_id] if synthesized_claim_id else []) + pooled
    if result.status in _UNDECIDED:
        detail = "; ".join(f"{d.code}: {d.message}" for d in result.diagnostics) or (result.reason_unknown or "")
        return [IntegrityFinding(code=undecided_code, severity="warning", message=f"joint check could not be decided ({result.status.value}): {detail}", claim_ids=base_ids, formal_result_id=result.result_id, deterministic=False)]
    out: list[IntegrityFinding] = []
    limits = [d for d in result.diagnostics if d.code in _LIMIT_CODES]
    if limits:
        out.append(IntegrityFinding(code="INT-GLOSSARY-006", severity="error", message=f"joint problem over {len(pooled)} claims breaches the joint limits: " + "; ".join(f"{d.code}: {d.message}" for d in limits), claim_ids=base_ids, formal_result_id=result.result_id))
    by_owner: dict[str, list[str]] = {}
    concl: list[str] = []
    other: list[str] = []
    for d in result.diagnostics:
        if d.code in _LIMIT_CODES:
            continue
        text = f"{d.code}: {d.message}" + (f" at {d.path}" if d.path else "")
        if d.path and d.path.startswith("conclusion"):
            concl.append(text)
            continue
        owner = jmap.owner_of_path(d.path)
        if owner is not None:
            by_owner.setdefault(owner, []).append(text)
        else:
            other.append(text)
    if concl and synthesized_claim_id is not None:
        out.append(IntegrityFinding(code="INT-SYNTH-010", severity="error", message=f"the synthesized conclusion is not a valid formalization ({result.status.value}): " + "; ".join(concl), claim_ids=[synthesized_claim_id], formal_result_id=result.result_id))
    elif concl:
        other += concl
    for owner, texts in sorted(by_owner.items()):
        out.append(IntegrityFinding(code="INT-GLOSSARY-007", severity="error", message=f"the formalization of source claim {owner!r} is invalid inside the joint problem ({result.status.value}): " + "; ".join(texts), claim_ids=[owner], formal_result_id=result.result_id))
    if other or not out:
        out.append(IntegrityFinding(code=undecided_code, severity="warning", message=f"joint check did not produce a verdict ({result.status.value}): " + ("; ".join(other) or "no diagnostics"), claim_ids=base_ids, formal_result_id=result.result_id, deterministic=False))
    return out


#: Claim-minimal attribution solves one small problem per claim of a core (and one per deletion); beyond this many
#: claims in a core the core's claims are named as found (a large cycle is not re-solved claim by claim).
ATTRIBUTION_MAX_CLAIMS = 16
#: Contradictions named in one joint check at most; each found is set aside and the rest re-checked, so a contradiction
#: never hides a self-refutation or a second, disjoint contradiction.
MAX_NAMED_CONFLICTS = 8


def _core_assertions(result: VerificationResult, jmap: JointMap) -> list[str]:
    return sorted({jmap.assertions[i][1] + (" (conclusion)" if jmap.assertions[i][2] else "") for i in result.premises_relied_on if i in jmap.assertions})


def _self_inconsistent(claim_id: str, assertions: list[str], result_id: str, related: list[str], prefix: list[str], assumed_readings: frozenset[str]) -> IntegrityFinding:
    """INT-CONFLICT-005 for one claim whose own assertions refute each other. When the claim's translation is an assumed
    reading (AMBIGUOUS_TRANSLATION, ``assumed_readings``) the refutation exists only under that reading, which the
    translator chose and the specialist did not state: the same code as a warning, never an error charged to the
    specialist. Neither demands a disclosure."""
    if claim_id in assumed_readings:
        return IntegrityFinding(code="INT-CONFLICT-005", severity="warning", message=f"specialist claim {claim_id!r} refutes itself only under the assumed reading of its AMBIGUOUS_TRANSLATION: its own assertions {assertions} refute each other in the pooled formalization, which is one reading the translator chose, not a fixed one, so the specialist is not charged with an inconsistency (no other claim is involved; no disclosure is demanded)", claim_ids=prefix + [claim_id], formal_result_id=result_id, related_result_ids=related, deterministic=False)
    return IntegrityFinding(code="INT-CONFLICT-005", severity="error", message=f"specialist claim {claim_id!r} is internally inconsistent: its own assertions {assertions} refute each other (no other claim is involved)", claim_ids=prefix + [claim_id], formal_result_id=result_id, related_result_ids=related, deterministic=False)


def _conflict(claims: list[str], result_id: str, related: list[str], prefix: list[str], where: str, *, minimal: Optional[bool] = None) -> IntegrityFinding:
    note = "" if minimal is None else (" (claim-minimal: the contradiction needs every claim named)" if minimal else f" (the unsat core's claims; more than {ATTRIBUTION_MAX_CLAIMS} claims, so the set was not minimised claim by claim)")
    return IntegrityFinding(code="INT-CONFLICT-001", severity="error", message=f"specialist claims {where}contradict each other under the shared glossary; conflicting claims: {claims}{note}", claim_ids=prefix + claims, formal_result_id=result_id, related_result_ids=related, deterministic=False)


def _without_conclusion(p: Problem) -> Problem:
    """``p`` with its conclusion no longer pooled (a self-refuting conclusion is set aside for the joint re-check)."""
    return p.model_copy(update={"query": "consistency", "conclusion": None})


def _check_pool(problems: list[Problem], *, request_id: str, joint_id: str, cfg: SolverConfig, limits: Limits, signing_key: Optional[bytes]) -> tuple[Optional[VerificationResult], JointMap]:
    joint, _f, jmap = joint_problem(problems, request_id=request_id, joint_id=joint_id)
    if joint is None:
        return None, jmap
    return verify(joint, cfg, limits, signing_key=signing_key, key_id="integrity", diagnose=False), jmap


def _attribute_contradiction(problems: list[Problem], result: VerificationResult, jmap: JointMap, *, request_id: str, cfg: SolverConfig, limits: Limits,
                             signing_key: Optional[bytes], synthesized_claim_id: Optional[str], assumed_readings: frozenset[str] = frozenset()) -> list[IntegrityFinding]:
    """Name a contradiction claim-minimally, whatever the order the claims were pooled in.

    The unsat core is a set of ASSERTIONS; when two claims carry identical premises (one report restating the same
    figures in two claims) the core may use either claim's copy, so the claims it touches are not the claims the
    contradiction needs. Each claim of a core of several claims is therefore checked alone (its premises with its pooled
    conclusion): a claim that refutes itself is INT-CONFLICT-005 for that claim only (no disclosure is demanded), its
    self-refuting conclusion (or the whole claim, when its premises alone already conflict) is set aside and the joint
    check is re-run on the rest. A contradiction that remains is minimised over claims by deletion, so INT-CONFLICT-001
    names a claim only when the contradiction needs it; its claims are then set aside and the rest re-checked, so one
    contradiction never hides another (at most :data:`MAX_NAMED_CONFLICTS` are named)."""
    prefix = [synthesized_claim_id] if synthesized_claim_id else []
    where = "behind this synthesis " if synthesized_claim_id else ""
    active: dict[str, Problem] = {p.claim_id: p for p in problems}
    reported: set[str] = set()
    out: list[IntegrityFinding] = []
    related: list[str] = []
    res, jm = result, jmap
    conflicts = 0

    def _recheck() -> bool:
        """Re-run the joint check on what is still active; True when it is still contradictory (``res``/``jm`` updated)."""
        nonlocal res, jm
        if not active or conflicts >= MAX_NAMED_CONFLICTS:
            return False
        res2, jm2 = _check_pool(list(active.values()), request_id=request_id, joint_id="cross-report-rest", cfg=cfg, limits=limits, signing_key=signing_key)
        if res2 is None:
            return False
        related.append(res2.result_id)
        if res2.status is S.INCONSISTENT_PREMISES:
            res, jm = res2, jm2
            return True
        if res2.status is not S.CONSISTENT:
            out.append(IntegrityFinding(code="INT-CONFLICT-004", severity="warning", message=f"after setting aside the contradictions already named, the joint check of the remaining claims {where}could not be decided ({res2.status.value})", claim_ids=prefix + sorted(active), formal_result_id=res2.result_id, related_result_ids=[result.result_id], deterministic=False))
        return False

    for _ in range(len(problems) + 1):
        claims = claim_ids_from_core(res.premises_relied_on, jm)
        if not claims:
            out.append(IntegrityFinding(code="INT-CONFLICT-004", severity="warning", message=f"the pooled claims {where}are contradictory but the conflicting set could not be attributed (no unsat core); all pooled claims are listed", claim_ids=prefix + sorted(active), formal_result_id=res.result_id, related_result_ids=related, deterministic=False))
            break
        if len(claims) > ATTRIBUTION_MAX_CLAIMS:
            out.append(_conflict(claims, res.result_id, list(related), prefix, where, minimal=False))
            conflicts += 1
            for cid in claims:
                active.pop(cid, None)
            if not _recheck():
                break
            continue
        selfish: list[tuple[str, VerificationResult, JointMap]] = []
        if len(claims) == 1:
            selfish.append((claims[0], res, jm))
        else:
            for cid in claims:
                alone, ajm = _check_pool([active[cid]], request_id=request_id, joint_id=f"alone-{sha256_hex(cid)[:24]}", cfg=cfg, limits=limits, signing_key=signing_key)
                if alone is not None:
                    related.append(alone.result_id)
                    if alone.status is S.INCONSISTENT_PREMISES:
                        selfish.append((cid, alone, ajm))
        if not selfish:
            minimal, rid = _minimise_by_deletion(claims, active, res, request_id=request_id, cfg=cfg, limits=limits, signing_key=signing_key, related=related)
            out.append(_conflict(minimal, rid, [r for r in related if r != rid], prefix, where, minimal=True))
            conflicts += 1
            for cid in minimal:  # set this contradiction aside and look for another (a self-refutation it masked, a disjoint conflict)
                active.pop(cid, None)
            if not _recheck():
                break
            continue
        for cid, alone, ajm in selfish:
            if cid not in reported:
                reported.add(cid)
                out.append(_self_inconsistent(cid, _core_assertions(alone, ajm), alone.result_id, [r for r in [res.result_id] + related if r != alone.result_id], prefix, assumed_readings))
            p = active[cid]
            refuting_conclusion = p.conclusion is not None and p.query == "entailment" and bool(ajm.pooled_conclusions(list(alone.premises_relied_on)))
            if refuting_conclusion:
                active[cid] = _without_conclusion(p)
            else:  # its premises alone conflict: nothing of it can stand in a joint check
                del active[cid]
        if not _recheck():
            break
    return out


def _minimise_by_deletion(claims: list[str], active: dict[str, Problem], res: VerificationResult, *, request_id: str, cfg: SolverConfig, limits: Limits,
                          signing_key: Optional[bytes], related: list[str]) -> tuple[list[str], str]:
    """A minimal set of claims (in claim-id order, so the answer does not depend on the pooling order) whose joint problem
    is still contradictory, and the result id that establishes it. No claim of ``claims`` is self-inconsistent here, so a
    pair is minimal as it stands."""
    current = sorted(claims)
    rid = res.result_id
    if len(current) <= 2:
        return current, rid
    for cid in list(current):
        trial = [c for c in current if c != cid]
        r, jm = _check_pool([active[c] for c in trial], request_id=request_id, joint_id="cross-report-min", cfg=cfg, limits=limits, signing_key=signing_key)
        if r is None:
            continue
        related.append(r.result_id)
        if r.status is S.INCONSISTENT_PREMISES:
            core = set(claim_ids_from_core(r.premises_relied_on, jm))
            current = sorted(c for c in trial if c in core) if len(core) >= 2 else trial
            rid = r.result_id
            if len(current) <= 2:
                break
    return current, rid


#: The bounds of the stated-precision re-check of a named contradiction (:func:`at_stated_precision`): the joint bounds with
#: the nonlinear-term gate open, since a decimal coefficient read over its rounding interval becomes a variable factor.
PRECISION_LIMITS: Limits = JOINT_LIMITS.model_copy(update={"allow_nonlinear": True})
_DECIMAL_LITERAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)\.([0-9]+)$")
#: The fields of a node whose child must stay a constant (a divisor): a literal there is never read as an interval.
_CONSTANT_FIELDS = {"div": "right", "idiv": "right", "mod": "right"}


def at_stated_precision(problems: list[Problem]) -> Optional[list[Problem]]:
    """The problems with every decimal real literal (``"9.57"``, ``"24.0"``; never an integer or a fraction, and never a
    divisor, which must stay a constant) read at the precision it is written to: a fresh Real symbol per occurrence,
    bounded to the closed interval of half a unit of its last written digit (``9.565 <= r <= 9.575``). A figure an
    agent states to three significant figures is then the interval it stands for, so two correct lines that each
    compute a quantity from rounded intermediates ("R = 230 V / 9.57 A = 24.0 ohm" and "R = (230 V)^2 / 2200 W = 24.0
    ohm") are not read as contradicting each other at a precision neither states. None when no problem has such a
    literal (nothing to read differently). The rewrite is data on data: literals and identifiers only."""
    from fractions import Fraction
    changed = False
    out: list[Problem] = []
    for i, p in enumerate(problems):
        data = p.model_dump(mode="json", exclude_none=True)
        taken = {s["name"] for s in data.get("symbols", [])}
        extra_symbols: list[dict] = []
        extra_premises: list[dict] = []
        counter = [0]

        def widen(node, parent_op: Optional[str] = None, field_name: Optional[str] = None):
            if isinstance(node, list):
                return [widen(x, parent_op, field_name) for x in node]
            if not isinstance(node, dict):
                return node
            if node.get("op") == "real" and isinstance(node.get("value"), str) and _CONSTANT_FIELDS.get(parent_op or "") != field_name:
                m = _DECIMAL_LITERAL_RE.match(node["value"])
                if m is not None:
                    value = Fraction(node["value"])
                    half = Fraction(1, 2 * 10 ** len(m.group(2)))
                    counter[0] += 1
                    name = f"rnd{i}_{counter[0]}"
                    while name in taken:
                        counter[0] += 1
                        name = f"rnd{i}_{counter[0]}"
                    taken.add(name)
                    extra_symbols.append({"name": name, "sort": "Real", "meaning": f"the figure {node['value']} read at its stated precision"})
                    lo, hi = value - half, value + half
                    extra_premises.append({"id": f"rnd_{name}", "expr": {"op": "and", "args": [
                        {"op": "ge", "left": {"op": "var", "name": name}, "right": {"op": "real", "value": f"{lo.numerator}/{lo.denominator}" if lo.denominator != 1 else str(lo.numerator)}},
                        {"op": "le", "left": {"op": "var", "name": name}, "right": {"op": "real", "value": f"{hi.numerator}/{hi.denominator}" if hi.denominator != 1 else str(hi.numerator)}}]},
                        "label": f"{node['value']} as written: half a unit of its last digit either way"})
                    return {"op": "var", "name": name}
            op = node.get("op")
            return {k: (widen(v, op, k) if k not in ("op", "name", "value") else v) for k, v in node.items()}

        for key in ("premises",):
            data[key] = [{**a, "expr": widen(a["expr"])} for a in data.get(key, [])]
        if data.get("conclusion") is not None:
            data["conclusion"] = {**data["conclusion"], "expr": widen(data["conclusion"]["expr"])}
        if not extra_symbols:
            out.append(p)
            continue
        changed = True
        data["symbols"] = [*data.get("symbols", []), *extra_symbols]
        data["premises"] = [*data["premises"], *extra_premises]
        try:
            out.append(Problem.model_validate(data))
        except Exception:
            return None  # a rewrite outside the schema (an oversized problem): the strict reading stands
    return out if changed else None


def _without_rounding_only_conflicts(findings: list[IntegrityFinding], problems: list[Problem], *, request_id: str, cfg: SolverConfig,
                                     signing_key: Optional[bytes]) -> list[IntegrityFinding]:
    """``findings`` without each INT-CONFLICT-001 whose claims are consistent once their decimal figures are read at the
    precision they are written to (:func:`at_stated_precision`, decided by the engine under :data:`PRECISION_LIMITS`): the
    contradiction exists only at a precision none of the claims states, so nothing is charged to the specialists. A
    re-check that cannot be built or decided keeps the finding. Every other finding is kept as it is."""
    from ..engine.policies import policy_config
    by_id = {p.claim_id: p for p in problems}
    out: list[IntegrityFinding] = []
    for f in findings:
        if f.code != "INT-CONFLICT-001":
            out.append(f)
            continue
        named = [by_id[c] for c in dict.fromkeys(f.claim_ids) if c in by_id]
        relaxed = at_stated_precision(named) if len(named) >= 2 else None
        if relaxed is None:
            out.append(f)
            continue
        joint, _jf, _jm = joint_problem(relaxed, request_id=request_id, joint_id="cross-report-precision")
        if joint is None:
            out.append(f)
            continue
        res = verify(joint, policy_config("nonlinear", cfg), PRECISION_LIMITS, signing_key=signing_key, key_id="integrity", diagnose=False)
        if res.status is not S.CONSISTENT:
            out.append(f)
    return out


def check_cross_report_consistency(problems: list[Problem], *, request_id: str, config: SolverConfig = SolverConfig(), signing_key: Optional[bytes] = None, limits: Limits = JOINT_LIMITS,
                                   assumed_readings: frozenset[str] | set[str] = frozenset()) -> tuple[Optional[VerificationResult], list[IntegrityFinding]]:
    """Are all specialists' formalized claims jointly consistent? Names the conflict claim-minimally
    (:func:`_attribute_contradiction`): a claim that refutes itself is INT-CONFLICT-005 for that claim alone, and
    INT-CONFLICT-001 names a claim only when the contradiction needs it.

    The unsat core is always requested, whatever the caller's configuration says,
    because a contradiction without the conflicting claim ids is not actionable.
    ``assumed_readings`` names pooled claims whose translation is AMBIGUOUS_TRANSLATION: a self-refutation of one of
    them exists only under the translator's assumed reading and is INT-CONFLICT-005 as a warning, not an error. Returns the result of the joint check
    over every problem; the findings cite the runs that established them."""
    apart, splits = split_by_gloss(problems)
    apart, candidates = rename_candidates_apart(apart)
    apart, points = rename_evaluation_points_apart(apart)
    joint, findings, jmap = joint_problem(apart, request_id=request_id, joint_id="cross-report")
    if splits:  # the glossary findings are those of the claims as translated, each saying the symbol was read apart
        _syms, glossary = _merge_symbols(problems, read_apart=True)
        findings = [f for f in glossary if f.code == "INT-GLOSSARY-005"] + [f for f in findings if f.code != "INT-GLOSSARY-005"]
    if joint is None:
        return None, findings
    cfg = config.model_copy(update={"produce_unsat_core": True})
    result = verify(joint, cfg, limits, signing_key=signing_key, key_id="integrity", diagnose=False)
    if result.status is S.INCONSISTENT_PREMISES:
        attributed = _attribute_contradiction(apart, result, jmap, request_id=request_id, cfg=cfg, limits=limits, signing_key=signing_key, synthesized_claim_id=None, assumed_readings=frozenset(assumed_readings))
        kept = _without_rounding_only_conflicts(attributed, apart, request_id=request_id, cfg=cfg, signing_key=signing_key)
        findings += kept
        if (splits or candidates or points) and any(f.code == "INT-CONFLICT-001" for f in attributed) and not any(
                f.code in ("INT-CONFLICT-001", "INT-CONFLICT-004", "INT-CONFLICT-005") for f in kept):
            findings += _glossary_only_at_stated_precision(problems, apart, attributed, splits, request_id=request_id, cfg=cfg, signing_key=signing_key,
                                                           candidates=candidates, points=points)
    elif result.status is not S.CONSISTENT:
        findings += _classify_failure(result, jmap, synthesized_claim_id=None, undecided_code="INT-CONFLICT-004")
        findings += _without_unpoolable(problems, result, jmap, request_id=request_id, config=config, signing_key=signing_key, limits=limits,
                                        assumed_readings=assumed_readings)
    elif splits or candidates or points:
        findings += _glossary_only_contradiction(problems, splits, result, request_id=request_id, cfg=cfg, limits=limits, signing_key=signing_key,
                                                 candidates=candidates, points=points)
    return result, findings


def _without_unpoolable(problems: list[Problem], result: VerificationResult, jmap: JointMap, *, request_id: str, config: SolverConfig,
                        signing_key: Optional[bytes], limits: Limits, assumed_readings) -> list[IntegrityFinding]:
    """The joint check re-run without the claims a joint problem could not pool (integration gate, round 1,
    formal-robustness-4): when the joint result is INVALID_FORMALIZATION or UNSUPPORTED and every diagnostic belongs to an
    identified pooled claim (``jmap.owner_of_path``), those claims are reported as they are (:func:`_classify_failure`,
    INT-GLOSSARY-007) and the rest are checked together, so one claim the joint policy refuses never hides a contradiction
    between the others. The re-run's own findings are returned; the pool only shrinks, so this ends."""
    if result.status not in (S.INVALID_FORMALIZATION, S.UNSUPPORTED) or not result.diagnostics:
        return []
    owners = [jmap.owner_of_path(d.path) for d in result.diagnostics]
    if any(o is None for o in owners):
        return []
    dropped = set(owners)
    rest = [p for p in problems if p.claim_id not in dropped]
    if len(rest) < 2 or len(rest) == len(problems):
        return []
    _res, again = check_cross_report_consistency(rest, request_id=request_id, config=config, signing_key=signing_key, limits=limits,
                                                 assumed_readings=frozenset(assumed_readings) - dropped)
    return [f for f in again if f.code != "INT-GLOSSARY-005"]  # the glossary findings of the full pool were reported already


def _glossary_only_at_stated_precision(problems: list[Problem], apart: list[Problem], attributed: list[IntegrityFinding],
                                      splits: dict[str, list[tuple[str, list[str], str]]], *, request_id: str, cfg: SolverConfig,
                                      signing_key: Optional[bytes], candidates: Optional[dict[str, list[tuple[str, str, str]]]] = None,
                                      points: Optional[dict[str, list[tuple[str, str, str]]]] = None) -> list[IntegrityFinding]:
    """:func:`_glossary_only_contradiction` when every contradiction the pool read apart was charged with exists only at a
    precision no claim states (each INT-CONFLICT-001 dropped by :func:`_without_rounding_only_conflicts`): the claims those
    contradictions named are read at the precision their figures are written to (:func:`at_stated_precision`), in the pool
    read apart and in the pool as translated, and both are re-decided under :data:`PRECISION_LIMITS`. A symbol glossed as two
    quantities, or a rejected candidate, then still has its contradiction named beside a rounding-only one (round-8
    clearance c1, ph-p8b: 'x0_cm', glossed as two displacements, beside the rounding-only 'period_s' pair of s4.1 and s8.2,
    whose glosses name one period). A re-check that cannot be built, or a pool read apart that is still not CONSISTENT,
    names nothing (as before)."""
    from ..engine.policies import policy_config
    named = {c for f in attributed if f.code == "INT-CONFLICT-001" for c in f.claim_ids}
    idx = [i for i, p in enumerate(apart) if p.claim_id in named]
    if not idx or len(apart) != len(problems):
        return []
    relaxed_apart_part = at_stated_precision([apart[i] for i in idx])
    relaxed_part = at_stated_precision([problems[i] for i in idx])
    if relaxed_apart_part is None or relaxed_part is None:
        return []
    relaxed_apart, relaxed = list(apart), list(problems)
    for k, i in enumerate(idx):
        relaxed_apart[i], relaxed[i] = relaxed_apart_part[k], relaxed_part[k]
    joint, _f, _jm = joint_problem(relaxed_apart, request_id=request_id, joint_id="cross-report-precision")
    if joint is None:
        return []
    pcfg = policy_config("nonlinear", cfg)
    apart_result = verify(joint, pcfg, PRECISION_LIMITS, signing_key=signing_key, key_id="integrity", diagnose=False)
    if apart_result.status is not S.CONSISTENT:
        return []
    return _glossary_only_contradiction(relaxed, splits, apart_result, request_id=request_id, cfg=pcfg, limits=PRECISION_LIMITS, signing_key=signing_key,
                                        candidates=candidates, points=points, precision=True)


def _glossary_only_contradiction(problems: list[Problem], splits: dict[str, list[tuple[str, list[str], str]]], apart_result: VerificationResult, *,
                                 request_id: str, cfg: SolverConfig, limits: Limits, signing_key: Optional[bytes],
                                 candidates: Optional[dict[str, list[tuple[str, str, str]]]] = None, precision: bool = False,
                                 points: Optional[dict[str, list[tuple[str, str, str]]]] = None) -> list[IntegrityFinding]:
    """INT-CONFLICT-004 (warning) when the claims contradict each other only if a symbol they gloss as different
    quantities is read as one, or only if a candidate value a claim tests and rejects (rule ``candidate``,
    :func:`rename_candidates_apart`) is read as a value of the shared symbol: the pool is consistent with the glosses read
    apart and the candidates read as hypotheticals, and inconsistent pooled. The finding names the claims of the pooled core,
    the symbols with their glosses and the candidates with the assertion that assigns each; no INT-CONFLICT-001 is charged
    and no disclosure is demanded (only INT-CONFLICT-001 enters the disclosure rule)."""
    joint, _f, jmap = joint_problem(problems, request_id=request_id, joint_id="cross-report-pooled")
    if joint is None:
        return []
    pooled = verify(joint, cfg, limits, signing_key=signing_key, key_id="integrity", diagnose=False)
    if pooled.status is not S.INCONSISTENT_PREMISES:
        return []
    claims = claim_ids_from_core(pooled.premises_relied_on, jmap) or sorted(set(jmap.claim_ids))
    at_precision = ("; decided with the figures of the claims a rounding-only contradiction named read at the precision they are written to, as the "
                    "pool read apart contradicts itself only at a precision no claim states") if precision else ""
    tested = {cid: rows for cid, rows in (candidates or {}).items() if cid in claims}
    evaluated = {cid: rows for cid, rows in (points or {}).items() if cid in claims}
    if evaluated and not tested and not any(set(ids) & set(claims) for groups in splits.values() for _n, ids, _g in groups):
        shown = "; ".join(f"claim {cid!r} evaluates or checks at " + ", ".join(f"the value its premise {aid!r} gives {name!r}" for name, _new, aid in rows)
                          for cid, rows in sorted(evaluated.items())[:4])
        return [IntegrityFinding(code="INT-CONFLICT-004", severity="warning",
                                 message=f"the pooled claims {claims} contradict each other only when a value a claim evaluates or checks at is read as a "
                                         f"value of the shared symbol ({shown}): what holds at a stated point is no assertion about the unknown the other "
                                         "claims state, so read as a hypothetical value it is consistent with them (rule evaluation-point); the "
                                         "contradiction is unattributable and no contradiction is charged to the specialists (an encoding that gives an "
                                         "evaluation point the shared symbol is a translation fault)" + at_precision,
                                 claim_ids=claims, formal_result_id=pooled.result_id, related_result_ids=[apart_result.result_id], deterministic=False)]
    if tested and not any(set(ids) & set(claims) for groups in splits.values() for _n, ids, _g in groups):
        shown = "; ".join(f"claim {cid!r} tests and rejects " + ", ".join(f"the value its assertion {aid!r} gives {name!r}" for name, _new, aid in rows)
                          for cid, rows in sorted(tested.items())[:4])
        return [IntegrityFinding(code="INT-CONFLICT-004", severity="warning",
                                 message=f"the pooled claims {claims} contradict each other only when a candidate value a claim tests and rejects is read as a "
                                         f"value of the shared symbol ({shown}): the claim states that the value fails a condition, which is no assertion "
                                         "about the unknown the other claims state, so read as a hypothetical value it is consistent with them (rule "
                                         "candidate); the contradiction is unattributable and no contradiction is charged to the specialists (an "
                                         "encoding that gives a rejected candidate the shared symbol is a translation fault)" + at_precision,
                                 claim_ids=claims, formal_result_id=pooled.result_id, related_result_ids=[apart_result.result_id], deterministic=False)]
    clashing, context = [], []
    for name, groups in sorted(splits.items()):
        involved = [(ids, gloss) for _new, ids, gloss in groups if set(ids) & set(claims)]
        if len(involved) < 2:
            continue
        contents = {gloss_content(g) for _ids, g in involved if _norm_meaning(g)}
        if len(contents) >= 2:
            clashing.append(f"{name!r} (" + "; ".join(f"{gloss!r} in {[c for c in ids if c in claims] or ids}" for ids, gloss in involved[:4]) + ")")
        else:
            context.append(repr(name))
    if not clashing:
        clashing = [repr(name) for name in sorted(splits)][:6]
    tail = f", and the quantities each claim computes with them ({', '.join(context[:8])}{' and more' if len(context) > 8 else ''})," if context else ""
    also = ("; claims " + ", ".join(repr(c) for c in sorted(tested)[:4]) + " also test and reject a candidate value of a shared symbol, read as a "
            "hypothetical (rule candidate)") if tested else ""
    if evaluated:
        also += ("; claims " + ", ".join(repr(c) for c in sorted(evaluated)[:4]) + " also evaluate or check at a value of a shared symbol, read as a "
                 "hypothetical (rule evaluation-point)")
    return [IntegrityFinding(code="INT-CONFLICT-004", severity="warning",
                             message=f"the pooled claims {claims} contradict each other only when symbol(s) {', '.join(clashing[:6])}, glossed as different quantities{tail} are read as one quantity{also}; read apart they are consistent, so the contradiction is unattributable and no contradiction is charged to the specialists (one symbol name for two quantities is a translation fault)" + at_precision,
                             claim_ids=claims, formal_result_id=pooled.result_id, related_result_ids=[apart_result.result_id], deterministic=False)]


def _proven_elsewhere(claim_id: str, source_problems: list[Problem], prior_results: Optional[dict[str, VerificationResult]],
                      signing_key: Optional[bytes] = None) -> bool:
    """A stored ENTAILED result establishes a pooled source conclusion only as current-policy evidence: bound to that
    exact source formalization, internally consistent, issued under this engine's versions, identity and default limits
    (an earlier release's result must be verified again), with no diagnostic that withholds the verdict, and, when the
    caller holds the key, carrying a signature that verifies."""
    if not prior_results:
        return False
    res = prior_results.get(claim_id)
    if res is None or res.status is not S.ENTAILED:
        return False
    src = next((p for p in source_problems if p.claim_id == claim_id), None)
    if src is None or res.binding.problem_digest != problem_digest(src) or res.claim_id != claim_id:
        return False
    if binding_inconsistencies(res) or stale_reasons(res) or any(d.code in NO_VERDICT_CODES for d in res.diagnostics):
        return False
    return signing_key is None or verify_signature(res, signing_key)


def check_synthesis_entailment(
    source_problems: list[Problem],
    synthesized_conclusion: Assertion,
    *,
    request_id: str,
    synthesized_claim_id: str,
    config: SolverConfig = SolverConfig(),
    signing_key: Optional[bytes] = None,
    limits: Limits = JOINT_LIMITS,
    unformalized_source_ids: tuple[str, ...] | list[str] = (),
    prior_results: Optional[dict[str, VerificationResult]] = None,
) -> tuple[Optional[VerificationResult], list[IntegrityFinding]]:
    """Does the synthesized claim follow from what the specialists actually asserted?

    ``unformalized_source_ids`` are cited sources with no formalization: the check
    then covers only a subset, a counterexample is reported as INT-SYNTH-009
    (warning) rather than as invention, and every outcome names the gap.
    When a proof relies on ungrounded premises (specialist inferences, assumptions,
    pooled conclusions) the entailment is re-run WITHOUT them; INT-SYNTH-002 /
    INT-SYNTH-008 are emitted only when that second run no longer proves the claim,
    so 'follows only via ...' is literally true."""
    unformalized = sorted(set(unformalized_source_ids))
    joint, findings, jmap = joint_problem(source_problems, request_id=request_id, joint_id=synthesized_claim_id, query="entailment", conclusion=synthesized_conclusion)
    if joint is None:
        return None, findings
    cfg = config.model_copy(update={"produce_unsat_core": True})
    result = verify(joint, cfg, limits, signing_key=signing_key, key_id="integrity", diagnose=False)
    pooled = sorted(set(jmap.claim_ids))
    coverage = f"checked against {len(pooled)} of {len(pooled) + len(unformalized)} cited sources; unformalized: {unformalized}"
    if result.status is S.COUNTEREXAMPLE:
        if unformalized:
            refuted = _refutation(joint, cfg, limits, signing_key)
            if refuted is not None and refuted.status is S.INCONSISTENT_PREMISES:
                findings.append(IntegrityFinding(code="INT-SYNTH-001", severity="error", message=f"synthesized claim is REFUTED by the formalized source claims {pooled}: together with their premises it is unsatisfiable, so no unformalized source ({unformalized}) can support it; the combinator strengthened or invented content", claim_ids=[synthesized_claim_id] + pooled + unformalized, formal_result_id=result.result_id, related_result_ids=[refuted.result_id], deterministic=False))
            else:
                findings.append(IntegrityFinding(code="INT-SYNTH-009", severity="warning", message=f"synthesized claim is not entailed by the FORMALIZED SUBSET of its cited sources ({coverage}); it is consistent with them, so the content may come from an unformalized source and could not be checked", claim_ids=[synthesized_claim_id] + unformalized + pooled, formal_result_id=result.result_id, related_result_ids=[refuted.result_id] if refuted is not None else [], deterministic=False))
        else:
            findings.append(IntegrityFinding(code="INT-SYNTH-001", severity="error", message=f"synthesized claim is NOT entailed by the cited source claims {pooled} (counterexample found): the combinator strengthened or invented content", claim_ids=[synthesized_claim_id] + pooled, formal_result_id=result.result_id, deterministic=False))
        return result, findings
    if result.status is S.INCONSISTENT_PREMISES:
        findings += _attribute_contradiction(source_problems, result, jmap, request_id=request_id, cfg=cfg, limits=limits, signing_key=signing_key, synthesized_claim_id=synthesized_claim_id)
    elif result.status is S.ENTAILED:
        findings += _reliance_findings(joint, result, jmap, source_problems, cfg, limits, signing_key, synthesized_claim_id, prior_results)
    else:
        findings += _classify_failure(result, jmap, synthesized_claim_id=synthesized_claim_id, undecided_code="INT-SYNTH-003")
    if unformalized:
        findings.append(IntegrityFinding(code="INT-SYNTH-011", severity="info", message=f"partial formal coverage: {coverage}", claim_ids=[synthesized_claim_id] + unformalized, formal_result_id=result.result_id))
    return result, findings


def _refutation(joint: Problem, cfg: SolverConfig, limits: Limits, signing_key: Optional[bytes]) -> Optional[VerificationResult]:
    """Consistency of the pooled premises together with the synthesized conclusion.
    INCONSISTENT_PREMISES means the synthesized claim contradicts the formalized sources."""
    if joint.conclusion is None:
        return None
    data = joint.model_dump(mode="json", exclude_none=True)
    data["query"] = "consistency"
    data["premises"] = data["premises"] + [{**data.pop("conclusion"), "id": "SYNTH"}]
    data["problem_id"] = _joint_problem_id(f"ref-{joint.claim_id}")
    try:
        prob = Problem.model_validate(data)
    except Exception:
        return None
    return verify(prob, cfg, limits, signing_key=signing_key, key_id="integrity", diagnose=False)


def _is_ungrounded(a: Assertion) -> bool:
    return is_ungrounded(a.grounding)  # the engine's own rule, so the two never disagree


def _reliance_findings(joint: Problem, result: VerificationResult, jmap: JointMap, source_problems: list[Problem], cfg: SolverConfig, limits: Limits, signing_key: Optional[bytes], scid: str, prior_results: Optional[dict[str, VerificationResult]]) -> list[IntegrityFinding]:
    """The first proof relied on ungrounded premises. Decide whether that reliance is
    essential: (A) does the claim follow from GROUNDED premises alone? then no finding;
    (B) does it follow without the pooled source CONCLUSIONS? then it rests on source
    inferences/assumptions (INT-SYNTH-002); otherwise it rests on unproven specialist
    conclusions (INT-SYNTH-008)."""
    if not result.ungrounded_dependencies:
        return []
    ungrounded_all = {a.id for a in joint.premises if _is_ungrounded(a)}
    grounded_only = verify(joint.model_copy(update={"premises": [a for a in joint.premises if a.id not in ungrounded_all]}), cfg, limits, signing_key=signing_key, key_id="integrity", diagnose=False)
    if grounded_only.status is S.ENTAILED:
        return []  # the claim follows from grounded premises alone; the ungrounded proof was incidental
    related = [grounded_only.result_id]
    pooled_all = {i for i in ungrounded_all if i in jmap.assertions and jmap.assertions[i][2]}
    if pooled_all:
        no_pooled = verify(joint.model_copy(update={"premises": [a for a in joint.premises if a.id not in pooled_all]}), cfg, limits, signing_key=signing_key, key_id="integrity", diagnose=False)
        related.append(no_pooled.result_id)
    else:
        no_pooled = result
    out: list[IntegrityFinding] = []
    if no_pooled.status is S.ENTAILED:
        deps = list(no_pooled.ungrounded_dependencies)
        claims = jmap.claim_ids_of(deps)
        out.append(IntegrityFinding(code="INT-SYNTH-002", severity="info", message=f"synthesized claim follows only via unverified inferences or assumptions in source claims {claims} (premises {[jmap.assertions[i][1] for i in deps if i in jmap.assertions]}); from grounded premises alone it is not proven ({grounded_only.status.value})", claim_ids=[scid] + claims, formal_result_id=result.result_id, related_result_ids=related, deterministic=False))
        return out
    pooled_ids = jmap.pooled_conclusions(list(result.ungrounded_dependencies))
    pooled_claims = [c for c in jmap.claim_ids_of(pooled_ids) if not _proven_elsewhere(c, source_problems, prior_results, signing_key)]
    other_ids = [i for i in result.ungrounded_dependencies if i not in set(pooled_ids)]
    other_claims = jmap.claim_ids_of(other_ids)
    tail = "without them the claim is not proven" if no_pooled.status is S.COUNTEREXAMPLE else f"a proof without them was not found ({no_pooled.status.value})"
    if pooled_claims:
        out.append(IntegrityFinding(code="INT-SYNTH-008", severity="warning", message=f"synthesized claim rests on the asserted CONCLUSIONS of source claims {pooled_claims}, which were pooled as premises but are not established (no ENTAILED result for them was supplied); {tail}", claim_ids=[scid] + pooled_claims, formal_result_id=result.result_id, related_result_ids=related, deterministic=False))
    if other_claims:
        out.append(IntegrityFinding(code="INT-SYNTH-002", severity="info", message=f"synthesized claim also relies on unverified inferences or assumptions in source claims {other_claims} (premises {[jmap.assertions[i][1] for i in other_ids if i in jmap.assertions]})", claim_ids=[scid] + other_claims, formal_result_id=result.result_id, related_result_ids=related, deterministic=False))
    return out


def check_paraphrase_coverage(source_problem: Problem, synthesized_conclusion: Assertion, *, request_id: str, synthesized_claim_id: str, config: SolverConfig = SolverConfig(), signing_key: Optional[bytes] = None, limits: Limits = JOINT_LIMITS) -> tuple[Optional[VerificationResult], list[IntegrityFinding]]:
    """Reverse direction for 'carried'/'paraphrased' claims: does the synthesized
    statement S alone entail the source's conclusion C? A counterexample means the
    paraphrase is strictly weaker than the source (content removed under an
    equivalence label): INT-SYNTH-007."""
    if source_problem.query != "entailment" or source_problem.conclusion is None:
        return None, []
    names = {s.name for s in source_problem.symbols}
    missing = sorted(s for s in _needed_symbols(synthesized_conclusion) if s not in names)
    if missing:
        return None, [IntegrityFinding(code="INT-GLOSSARY-003", severity="error", message=f"synthesized conclusion uses symbols {missing} that the source claim does not define", claim_ids=[synthesized_claim_id, source_problem.claim_id])]
    data = {"problem_id": _joint_problem_id(f"cov-{synthesized_claim_id}"), "request_id": request_id, "claim_id": synthesized_claim_id, "query": "entailment",
            "symbols": [s.model_dump(mode="json", exclude_none=True) for s in source_problem.symbols],
            "premises": [synthesized_conclusion.model_copy(update={"id": "SYNTH", "grounding": None}).model_dump(mode="json", exclude_none=True)],
            "conclusion": source_problem.conclusion.model_copy(update={"id": "SRC", "grounding": None}).model_dump(mode="json", exclude_none=True)}
    try:
        prob = Problem.model_validate(data)
    except Exception as exc:
        return None, [IntegrityFinding(code="INT-GLOSSARY-004", severity="error", message=f"coverage problem could not be built for {synthesized_claim_id!r} from {source_problem.claim_id!r}: {type(exc).__name__}: {str(exc)[:500]}", claim_ids=[synthesized_claim_id, source_problem.claim_id])]
    result = verify(prob, config.model_copy(update={"produce_unsat_core": True}), limits, signing_key=signing_key, key_id="integrity", diagnose=False)
    findings: list[IntegrityFinding] = []
    if result.status is S.COUNTEREXAMPLE:
        findings.append(IntegrityFinding(code="INT-SYNTH-007", severity="warning", message=f"synthesized claim is strictly WEAKER than its source {source_problem.claim_id!r}: the source's conclusion does not follow from the synthesized statement, so content was removed under a 'carried'/'paraphrased' label", claim_ids=[synthesized_claim_id, source_problem.claim_id], formal_result_id=result.result_id, deterministic=False))
    elif result.status not in (S.ENTAILED, S.INCONSISTENT_PREMISES):
        findings.append(IntegrityFinding(code="INT-SYNTH-003", severity="warning", message=f"paraphrase coverage check could not be decided ({result.status.value})", claim_ids=[synthesized_claim_id, source_problem.claim_id], formal_result_id=result.result_id, deterministic=False))
    return result, findings


def check_conflict_disclosure(synthesis: Synthesis, conflicting_sets: list[tuple[frozenset[str], Optional[str]]]) -> list[IntegrityFinding]:
    """INT-CONFLICT-002: a formal contradiction between specialist claims that the synthesis
    does not disclose. ``conflicting_sets`` are the claim-id sets named by INT-CONFLICT-001
    findings (with the result id that established each). A contradiction counts as
    disclosed only when some conflict record names at least two of the conflicting claims
    and the qualifying records together name them all; a synthesized id in a record stands
    for its ``source_claim_ids``. Shared by ``run_integrity_checks`` and the channel so the
    Overseer's report and the synthesis receipt apply one rule."""
    by_id = {c.claim_id: c for c in synthesis.claims}

    def as_sources(ids: list[str]) -> set[str]:
        out: set[str] = set()
        for i in ids:
            sc = by_id.get(i)
            out.update(sc.source_claim_ids if sc is not None and sc.source_claim_ids else [i])
        return out

    records = [as_sources(list(c.claim_ids)) for c in synthesis.conflicts]
    findings: list[IntegrityFinding] = []
    seen: set[frozenset[str]] = set()
    for conflicting, rid in conflicting_sets:
        if len(conflicting) < 2 or conflicting in seen:
            continue
        seen.add(conflicting)
        covering = [r for r in records if len(r & conflicting) >= 2]
        disclosed = conflicting <= set().union(*covering) if covering else False
        if not disclosed:
            findings.append(IntegrityFinding(code="INT-CONFLICT-002", severity="error", message=f"a formal contradiction between specialist claims {sorted(conflicting)} is not disclosed in the synthesis conflict records (a record counts only if it names at least two of the conflicting claims, and together the records must name them all)", claim_ids=sorted(conflicting), formal_result_id=rid, agent_ids=[synthesis.combinator_agent_id], deterministic=False))
    return findings


def check_conflict_records(synthesis: Synthesis, conflicting_sets: list[tuple[frozenset[str], Optional[str]]]) -> list[IntegrityFinding]:
    """INT-CONFLICT-006 (info): an unresolved conflict record of the synthesis over claims between which the hub found no
    contradiction (no claim set of ``conflicting_sets``, the INT-CONFLICT-001 sets, shares two claims with the record; a
    synthesized id in a record stands for its ``source_claim_ids``). The hub decides contradictions between formalized
    claims only, so the record may still be right (two dates in prose); it is the combinator's own statement, not a
    check, and the router is told so. A conflict the hub did find is the disclosure rule's (:func:`check_conflict_disclosure`).
    Shared by ``run_integrity_checks`` and the channel."""
    by_id = {c.claim_id: c for c in synthesis.claims}
    found = [s for s, _rid in conflicting_sets if len(s) >= 2]
    findings: list[IntegrityFinding] = []
    for record in synthesis.conflicts:
        if record.status != "unresolved":
            continue
        ids: set[str] = set()
        for i in record.claim_ids:
            sc = by_id.get(i)
            ids.update(sc.source_claim_ids if sc is not None and sc.source_claim_ids else [i])
        if any(len(ids & s) >= 2 for s in found):
            continue
        findings.append(IntegrityFinding(code="INT-CONFLICT-006", severity="info", message=(
            f"conflict record {record.conflict_id} names claims {sorted(ids)[:16]} between which the hub found no contradiction (it decides "
            "contradictions between formalized claims only): the record is the combinator's own statement, not a check, so the router must not "
            "read it as an established disagreement"), claim_ids=sorted(ids)[:16], agent_ids=[synthesis.combinator_agent_id]))
    return findings
