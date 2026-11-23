"""The closed lexical classes of the self-certification reader, loaded once from ``lexicon.json`` (design section 3.3 and
3.10).

The JSON holds classes of WORDS: family stems with an inflection class, evaluator nouns, scope words, quantifiers, negators,
and idioms of at most six tokens. This module expands the inflections, builds the lookup tables (a dict from word to its tags,
O(1) per token) and the idiom trie (at most six tokens per entry), and checks the data discipline at import: an entry of more
than six tokens, an entry ending with sentence punctuation, or an idiom with two or more open-class words besides its head
refuses to load (``ImportError``), so every gate that imports the reader fails closed instead of reading with a list of
sentences.

Tags: ``F:<FAMILY>`` (CHECK, OUTCOME, AGREE, QUALITY, SRCEVAL, CONFIDENCE, SCORE, STATUS, APPROVE, ASSURE, COMPLY, FIDELITY,
DEFECT, PROVENANCE), ``v:<form>`` (base, 3sg, past, part, ger; Spanish es1, es3, espret), ``noun``, ``agent``, ``adj``,
``prod`` (a production verb), ``C:<class>`` for every closed class, ``lang:es``, ``upper`` (a STATUS word only in capitals),
``negaffix`` (un-, in-, -free), ``prefix`` (re-, double-, cross-, ...), ``fuzzy`` (a one-edit variant, rule N9).
"""
from __future__ import annotations

import functools
import json
import re
import pathlib
import unicodedata
from dataclasses import dataclass, field

__all__ = ["Lexicon", "lexicon", "known_word", "tags", "fold_word", "PREFIXES", "build", "fuzzy_targets", "fuzzy_candidates", "fuzzy_target"]

_HERE = pathlib.Path(__file__).resolve().parent

#: Prefixes a family verb takes (design 3.3).
PREFIXES = ("double-", "cross-", "triple-", "spot-", "fact-", "self-", "sanity-", "peer-", "hand-", "stress-", "auto-", "re-", "re",
            "independently-", "formally-", "fully-")

#: Function words besides the closed classes (prepositions and the like), for the open-class count of an idiom.
_PREPOSITIONS = ("in on at by for with of to from as into over through past under within without about against up out off "
                 "de en por para con sin a al del y o que lo la el los las un una mi mis su sus tu le les ce et the a an my our "
                 "your his her their its it this that these those all every each any no not one two n").split()


@functools.lru_cache(maxsize=65536)
def fold_word(word: str) -> str:
    """A lexicon word as the reader reads it: lower case, accents folded."""
    w = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in w if not unicodedata.combining(c)).replace("’", "'")


def _en_forms(lemma: str, cls: str) -> list[tuple[str, tuple[str, ...]]]:
    """(form, verb-form tags) of an English verb of inflection class ``cls``."""
    if cls.startswith("x|"):
        forms = cls[2:].split(",")
        out = []
        for i, f in enumerate(forms):
            if i == 0:
                out.append((f, ("v:base",)))
            elif f.endswith("ing"):
                out.append((f, ("v:ger",)))
            elif f.endswith("s") and f.startswith(forms[0][:max(1, len(forms[0]) - 1)]) and len(f) <= len(forms[0]) + 2 and not f.endswith("ss"):
                out.append((f, ("v:3sg",)))
            else:
                out.append((f, ("v:past", "v:part")))
        return out
    w = lemma
    if cls == "r":
        return [(w, ("v:base",)), (w + "s", ("v:3sg",)), (w + "ed", ("v:past", "v:part")), (w + "ing", ("v:ger",))]
    if cls == "e":
        return [(w, ("v:base",)), (w + "s", ("v:3sg",)), (w + "d", ("v:past", "v:part")), (w[:-1] + "ing", ("v:ger",))]
    if cls == "y":
        return [(w, ("v:base",)), (w[:-1] + "ies", ("v:3sg",)), (w[:-1] + "ied", ("v:past", "v:part")), (w + "ing", ("v:ger",))]
    if cls == "d":
        return [(w, ("v:base",)), (w + "s", ("v:3sg",)), (w + w[-1] + "ed", ("v:past", "v:part")), (w + w[-1] + "ing", ("v:ger",))]
    if cls == "s":
        return [(w, ("v:base",)), (w + "es", ("v:3sg",)), (w + "ed", ("v:past", "v:part")), (w + "ing", ("v:ger",))]
    raise ValueError(f"unknown inflection class {cls!r} for {lemma!r}")


def _es_forms(lemma: str, cls: str) -> list[tuple[str, tuple[str, ...]]]:
    """(form, tags) of a Spanish verb (accent-folded), regular forms plus the explicit irregular ones after a bar."""
    base_cls, _, extra = cls.partition("|")
    out: list[tuple[str, tuple[str, ...]]] = [(lemma, ("v:base", "lang:es"))]
    stem = lemma[:-2]
    if base_cls == "ar":
        soft = stem[:-1] + "qu" if stem.endswith("c") else stem[:-1] + "gu" if stem.endswith("g") else stem[:-1] + "c" if stem.endswith("z") else stem
        out += [(stem + "o", ("v:es1", "v:espret3")), (stem + "as", ("v:es2",)), (stem + "a", ("v:es3",)), (stem + "amos", ("v:es1",)),
                (stem + "an", ("v:es3",)), (soft + "e", ("v:espret1", "v:es3")), (soft + "en", ("v:es3",)), (stem + "aste", ("v:espret",)),
                (stem + "aron", ("v:espret",)), (stem + "aba", ("v:espret",)), (stem + "aban", ("v:espret",)),
                (stem + "ado", ("v:part",)), (stem + "ada", ("v:part",)), (stem + "ados", ("v:part",)), (stem + "adas", ("v:part",)),
                (stem + "ando", ("v:ger",)), (stem + "acion", ("noun",)), (stem + "aciones", ("noun",))]
    elif base_cls in ("er", "ir"):
        v = "e" if base_cls == "er" else "i"
        out += [(stem + "o", ("v:es1",)), (stem + "es", ("v:es2",)), (stem + "e", ("v:es3",)), (stem + "en", ("v:es3",)),
                (stem + "i", ("v:espret1",)), (stem + "io", ("v:espret3",)), (stem + "ieron", ("v:espret",)),
                (stem + "ido", ("v:part",)), (stem + "ida", ("v:part",)), (stem + "idos", ("v:part",)), (stem + "idas", ("v:part",)),
                (stem + "iendo", ("v:ger",)), (stem + v + "mos", ("v:es1",))]
    else:
        raise ValueError(f"unknown Spanish class {cls!r} for {lemma!r}")
    for f in [x for x in extra.split(",") if x]:
        f = fold_word(f)
        if f.endswith(("o",)) and not f.endswith(("io", "ado", "ido")):
            out.append((f, ("v:es1",)))
        elif f.endswith(("io",)):
            out.append((f, ("v:espret3",)))
        elif f.endswith(("ado", "ido", "isto", "icho")):
            out.append((f, ("v:part",)))
        else:
            out.append((f, ("v:es3",)))
    return [(fold_word(f), t + ("lang:es",)) for f, t in out]


def _adj_forms(entry: str) -> list[str]:
    word, _, cls = entry.partition(":")
    if cls == "a4":
        s = word[:-1]
        return [s + "o", s + "a", s + "os", s + "as"]
    if cls == "a2":
        return [word, word + ("es" if word[-1] not in "aeiou" else "s")]
    return [word]


@dataclass
class Lexicon:
    rules: str
    words: dict[str, set[str]] = field(default_factory=dict)
    idioms: dict[str, list[tuple[tuple[str, ...], frozenset[str]]]] = field(default_factory=dict)
    upper_status: frozenset[str] = frozenset()
    net: dict = field(default_factory=dict)
    fuzzy: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, word: str, *tag: str) -> None:
        w = fold_word(word)
        if " " in w:
            self.add_idiom(w, *tag)
            return
        self.words.setdefault(w, set()).update(tag)

    def add_idiom(self, phrase: str, *tag: str) -> None:
        toks = tuple(fold_word(phrase).split())
        if not toks:
            return
        if len(toks) == 1:
            self.words.setdefault(toks[0], set()).update(tag)
            return
        lst = self.idioms.setdefault(toks[0], [])
        for i, (t, tg) in enumerate(lst):
            if t == toks:
                lst[i] = (t, frozenset(tg | set(tag)))
                return
        lst.append((toks, frozenset(tag)))


def _check_entry(text: str, where: str, closed: set[str], family_words: set[str]) -> None:
    toks = fold_word(text).split()
    if len(toks) > 6:
        raise ImportError(f"selfcert lexicon: entry {text!r} of {where} has more than six tokens (a sentence, not a class member)")
    if text.rstrip().endswith((".", "!", "?")) and not text.endswith(("o.k.", "q.e.d.", "n.b.", "p.s.")):
        raise ImportError(f"selfcert lexicon: entry {text!r} of {where} ends with sentence punctuation")
    if len(toks) > 1:
        head = toks[-1]
        open_words = [t for t in toks[:-1] if t not in closed and t not in family_words and not any(c.isdigit() for c in t)]
        if len(open_words) >= 2:
            raise ImportError(f"selfcert lexicon: idiom {text!r} of {where} has two or more open-class words besides its head "
                              f"{head!r} (a sentence in disguise)")


def _load() -> Lexicon:
    return build(json.loads((_HERE / "lexicon.json").read_text(encoding="utf-8")))


def build(raw: dict) -> Lexicon:
    """The lexicon of the parsed ``lexicon.json`` data ``raw`` (the builder of the fuzzy exclusions passes the data with an empty
    exclusion list; no file is written or patched)."""
    lex = Lexicon(rules=raw["rules"])
    classes: dict = raw["classes"]
    closed: set[str] = set(_PREPOSITIONS)
    for name in ("neg", "det", "dist", "aux", "copula", "pron1", "pron2", "pron3", "poss1", "poss2", "poss3", "anaph", "partial",
                 "coordinator", "subordinator", "light_verbs", "weak", "deontic", "anchor", "imperative_skip", "agent_quant", "by",
                 "instr_prep", "month", "unit"):
        for w in classes.get(name, []):
            closed.update(fold_word(w).split())
    family_words: set[str] = set()
    fams: dict = raw["families"]

    def fam_entries(spec: dict):
        for key, vals in spec.items():
            if key == "base":
                continue
            for v in vals:
                yield key, v

    # pass 1: the family words, for the idiom check
    for fam, spec in fams.items():
        for key, v in fam_entries(spec):
            word = v.split(":")[0]
            family_words.update(fold_word(word).split())
            if key in ("verbs", "es_verbs", "es_production", "production", "defect_verbs"):
                lemma, _, cls = v.partition(":")
                forms = _es_forms(fold_word(lemma), cls) if key.startswith("es_") else _en_forms(lemma, cls)
                family_words.update(f for f, _t in forms)
            elif key in ("es_adjectives",) or (":" in v):
                family_words.update(fold_word(f) for f in _adj_forms(v))
    # pass 2: build
    for fam, spec in fams.items():
        ftag = f"F:{fam}"
        n = 0
        for key, v in fam_entries(spec):
            _check_entry(v.split(":")[0] if key not in ("idioms",) else v, f"family {fam} {key}", closed, family_words)
            if key in ("verbs", "production", "defect_verbs"):
                lemma, _, cls = v.partition(":")
                extra = ("prod",) if key == "production" else ("defectverb",) if key == "defect_verbs" else ()
                for form, vt in _en_forms(lemma, cls):
                    lex.add(form, ftag, *vt, *extra)
                    n += 1
            elif key in ("es_verbs", "es_production"):
                lemma, _, cls = v.partition(":")
                extra = ("prod",) if key == "es_production" else ()
                for form, vt in _es_forms(fold_word(lemma), cls):
                    lex.add(form, ftag, *vt, *extra, "lang:es")
                    n += 1
            elif key in ("adjectives", "es_adjectives"):
                for form in _adj_forms(v):
                    lex.add(form, ftag, "adj", *(("lang:es",) if key.startswith("es_") or ":" in v else ()))
                    n += 1
            elif key == "nouns":
                lex.add(v, ftag, "noun")
                n += 1
            elif key == "agents":
                lex.add(v, ftag, "agent")
                n += 1
            elif key == "upper_only":
                lex.upper_status = frozenset(lex.upper_status | {v})
                n += 1
            elif key == "idioms":
                lex.add_idiom(v, ftag, "idiom")
                n += 1
            else:
                raise ImportError(f"selfcert lexicon: unknown key {key!r} in family {fam}")
        lex.counts[f"family {fam}"] = n
    for name, vals in classes.items():
        for v in vals:
            _check_entry(v, f"class {name}", closed, family_words)
            lex.add(v, f"C:{name}")
        lex.counts[f"class {name}"] = len(vals)
    for name, vals in raw.get("verb_lists", {}).items():
        for v in vals:
            lemma, _, cls = v.partition(":")
            if cls in ("ar", "er", "ir") or cls.startswith(("ar|", "er|", "ir|")):
                forms = _es_forms(fold_word(lemma), cls)
            elif cls:
                forms = _en_forms(lemma, cls)
            else:
                forms = [(lemma, ())]
            for form, vt in forms:
                lex.add(form, f"V:{name}", *vt)
        lex.counts[f"verbs {name}"] = len(vals)
    lex.net = raw.get("net", {})
    for lang, spec in lex.net.items():
        for key in ("positive", "defect", "negators", "function", "weak", "scope"):
            for v in spec.get(key, []):
                _check_entry(v, f"net {lang} {key}", closed | set(fold_word(v).split()), family_words)
    # rule N9: one deletion or one adjacent transposition of the long closed-lexicon words. The excluded variants are REAL WORDS:
    # each is a word of the committed, cited word source scripts/selfcert/real_words.txt, and the list in lexicon.json is rebuilt
    # from that source and this lexicon alone by scripts/selfcert/build_fuzzy_exclusions.py (a misspelling such as "psased" or
    # "reviewe" is never exempt: it reads as the word it misspells, c3c)
    excluded = {fold_word(x) for x in raw.get("fuzzy_excluded", [])}
    lex.counts["fuzzy_excluded"] = len(excluded)
    for w in sorted(fuzzy_targets(lex)):
        for v in _variants(w):
            if v in lex.words or v in excluded or v in lex.fuzzy:
                continue
            lex.fuzzy[v] = w
    for w in sorted(fuzzy_targets_es(lex)):
        for v in _variants_es(w):
            if v in lex.words or v in excluded or v in lex.fuzzy:
                continue
            lex.fuzzy[v] = w
    lex.counts["fuzzy"] = len(lex.fuzzy)
    return lex


def fuzzy_targets(lex: "Lexicon") -> set[str]:
    """The words rule N9 reads misspelt: the family words (a light verb's family forms too: "passed", "signed", "checks") and the
    part words of six letters or more, and "every", "nothing", "nobody", "everything" (c3f: "Evrything was verfied."). A production
    verb ("calculated") is not a target."""
    targets: set[str] = set()
    for w, tg in lex.words.items():
        if not w.isalpha() or "lang:es" in tg:
            continue
        family = any(t.startswith("F:") for t in tg) and "prod" not in tg
        # (the answer's own genre nouns too, "answer", "response", "solution": a misspelt subject, "This anwser was thoroughly
        # cheked.", names the answer as the word it misspells; check round 9 of c3c)
        if (len(w) >= 6 and (family or "C:part" in tg or "C:genre_strong" in tg)) or w in ("every", "nothing", "nobody", "everything"):
            targets.add(w)
    return targets


#: The Spanish check verbs whose participles rule N9 reads misspelt ("Aprobdo por el revisor."; check round 9 of c3c).
_ES_CHECK_STEMS = ("aprob", "comprob", "verific", "revis", "valid", "confirm", "certific", "cheque", "audit", "corrobor", "cotej")


def fuzzy_targets_es(lex: "Lexicon") -> set[str]:
    """The Spanish participles of the check verbs (:data:`_ES_CHECK_STEMS`), read misspelt with :func:`_variants_es`."""
    return {w for w, tg in lex.words.items() if "lang:es" in tg and w.isalpha() and len(w) >= 8 and w.startswith(_ES_CHECK_STEMS)
            and w.endswith(("ado", "ada", "ados", "adas", "ido", "ida", "idos", "idas")) and any(t.startswith("F:") for t in tg)}


def fuzzy_candidates(lex: "Lexicon") -> set[str]:
    """Every one-edit variant of :func:`fuzzy_targets` and :func:`fuzzy_targets_es` that is not itself a lexicon word (before any
    exclusion)."""
    return {v for w in fuzzy_targets(lex) for v in _variants(w) if v not in lex.words} | \
        {v for w in fuzzy_targets_es(lex) for v in _variants_es(w) if v not in lex.words}


def _variants_es(w: str):
    """One deletion or adjacent transposition inside a Spanish participle, never after the vowel of its ending ("-ado", "-idas"):
    the vosotros imperatives "revisad", "revisaos" are words, while "aprobdo" (the ending's vowel dropped) is a misspelling."""
    e = next(len(x) for x in ("ados", "adas", "idos", "idas", "ado", "ada", "ido", "ida") if w.endswith(x))
    last = len(w) - e  # the ending's vowel
    for i in range(1, last + 1):
        yield w[:i] + w[i + 1:]
    for i in range(1, last):
        if w[i] != w[i + 1]:
            yield w[:i] + w[i + 1] + w[i] + w[i + 2:]


def _variants(w: str):
    for i in range(1, len(w)):
        yield w[:i] + w[i + 1:]
    for i in range(1, len(w) - 1):
        if w[i] != w[i + 1]:
            yield w[:i] + w[i + 1] + w[i] + w[i + 2:]


_LEXICON: list = []


def lexicon() -> Lexicon:
    """The lexicon, loaded once per process (module docstring): data, not a memo, so emptying the package's caches keeps it."""
    if not _LEXICON:
        _LEXICON.append(_load())
    return _LEXICON[0]


@functools.lru_cache(maxsize=65536)
def tags(word: str) -> frozenset[str]:
    """The tags of one folded, lower-case word (module docstring): the word itself, or a family stem behind a prefix, a negative
    affix, an evaluator compound ("z3-verified") or a one-edit variant (rule N9)."""
    lex = lexicon()
    w = word
    got = lex.words.get(w)
    if got is not None:
        return frozenset(got)
    if "-" in w and w.count("-") <= 4:
        # an idiom spelt with hyphens ("thumbs-up", "all-clear", "sign-off-on"): read as the idiom (c3c)
        parts = tuple(x for x in w.split("-") if x)
        for toks, tg in lex.idioms.get(parts[0], ()) if len(parts) >= 2 else ():
            if toks == parts:
                return frozenset(tg)
    if "-" in w:
        head, _, last = w.rpartition("-")
        if head.isdigit():
            return frozenset({"noun"})  # "6-mark", "10-point": an allocation or a size, never an act (X12)
        t = lex.words.get(last)
        if t is not None and any(x.startswith("F:") for x in t):
            ht = lex.words.get(head, set())
            if head in ("double", "cross", "triple", "spot", "fact", "self", "sanity", "peer", "hand", "stress", "auto", "re",
                        "independently", "formally", "fully", "twice", "re-double"):
                return frozenset(t | {"prefix"})
            if head == "un" or head == "non":
                return frozenset(t | {"negaffix"})
            if ht & {"C:eval_int", "C:eval_asr", "C:tool", "C:eval_int_agentive"} or head in ("z3", "hub", "engine", "solver", "teacher",
                                                                                             "system", "gdc", "machine", "computer"):
                return frozenset(t | {"evalcompound"})
            return frozenset(t | {"compound"})
        if last in _STANDARD_LASTS and lex.words.get(head, set()) & {"C:eval_asr", "C:eval_int", "C:m_eval"}:
            # an evaluator's standard or level ("examiner-standard", "marker-level", "examiner-proof", "teacher-ready"): the standard
            # the work is said to meet, a quality word (c3d)
            return frozenset({"F:QUALITY", "adj", "evalcompound"})
        if last == "free":
            t = lex.words.get(head, set())
            if "F:DEFECT" in t:
                return frozenset({"F:OUTCOME", "adj", "freeaffix"})
        if t is not None and t & {"C:eval_int", "C:eval_asr", "C:eval_int_agentive", "C:m_eval"} and not head.isdigit() and \
                len(head) <= 24 and head.replace("-", "").isalpha():
            # an agent named with a hyphen ("history-specialist", "physics-agent", "qa-checker"): the evaluator its last part names,
            # however the subject before it is spelled (attack round 3)
            return frozenset((t & {"C:eval_int", "C:eval_asr", "C:eval_int_agentive", "C:m_eval", "C:tool"}) | {"evalname"})
    for p in ("re", "un", "in", "im", "ir", "dis", "mis"):
        if w.startswith(p) and len(w) > len(p) + 3:
            t = lex.words.get(w[len(p):])
            if t is None:
                continue
            if p == "re" and any(x.startswith("v:") for x in t) and t & {"F:CHECK", "F:APPROVE"}:
                return frozenset(t | {"prefix"})
            if p in ("un", "in", "im", "ir", "dis") and t & {"v:part", "adj"} and t & {"F:CHECK", "F:OUTCOME", "F:QUALITY", "F:SRCEVAL",
                                                                                      "F:STATUS", "F:APPROVE"}:
                return frozenset(t | {"negaffix"})
    for suf, end in (("isimos", "os"), ("isimas", "as"), ("isimo", "o"), ("isima", "a")):
        # a Spanish absolute superlative of a family adjective or participle ("comprobadísimo", "correctísima"): the word's own
        # meaning at its highest degree, read as the word
        if w.endswith(suf) and len(w) > len(suf) + 3:
            t = lex.words.get(w[:-len(suf)] + end)
            if t is not None and any(x.startswith("F:") for x in t):
                return frozenset(t)
    fz = fuzzy_target(w)
    if fz is not None:
        return frozenset(tags(fz) | {"fuzzy"})
    return frozenset()


#: The last parts of an evaluator's compound that name a standard the work meets (:func:`tags`).
_STANDARD_LASTS = frozenset("standard level grade quality calibre caliber class proof ready worthy".split())


_TRIPLED_RE = re.compile(r"([a-z])\1{2,}")


def fuzzy_target(word: str) -> "str | None":
    """The lexicon word a misspelling stands for (rule N9): a one-edit variant, or a word with a letter written three or more times
    ("veriiified", "correeeect": no English or Spanish word has a tripled letter) that is a family word once the run is one or two
    letters. None otherwise."""
    lex = lexicon()
    fz = lex.fuzzy.get(word)
    if fz is not None:
        return fz
    if _TRIPLED_RE.search(word):
        for repl in (r"\1", r"\1\1"):
            c = _TRIPLED_RE.sub(repl, word)
            t = lex.words.get(c)
            if t is not None and any(x.startswith("F:") for x in t):
                return c
            if c in lex.fuzzy:
                return lex.fuzzy[c]
    return None


def known_word(word: str) -> bool:
    """Whether ``word`` (folded, lower case) is a word of the lexicon: used by the normaliser's letter-spaced and digit rules."""
    w = fold_word(word)
    if w in lexicon().words or w in lexicon().idioms:
        return True
    return bool(tags(w) - {"fuzzy"}) and "fuzzy" not in tags(w)
