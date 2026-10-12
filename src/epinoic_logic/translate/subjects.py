"""IB subject profiles and the Z3-eligibility matrix.

Tailoring principle: the translator serves ALL subject-specialist agents, not one.
Each profile states which claim classes the restricted IR (v1: propositional logic
plus exact integer/real arithmetic) can represent for that subject, where
ineligible claims route, and what the formal check does NOT establish there.

Rules that hold for every subject (context document, sections 4 and 5):
- Interpretive judgements (literary, artistic), historical truth, and subjective
  rubric judgements are never Z3-eligible as truth claims. Their ARGUMENT
  STRUCTURE (evidence -> inference -> point) may still be checked propositionally,
  with inferential links recorded as ungrounded specialist inferences.
- Factual claims about the world or the curriculum route to the evidence service.
- Units of measurement are not checked in v1; a numeric claim is checked on its
  exact values only, and the unit assumption is carried as an explicit assumption.

The subject list below is working configuration drawn from the general structure
of the IB Diploma Programme. It must be confirmed against the official syllabus
material (the IB agent training pack referenced by the context pack is not yet
available). Profiles never assert official IB rules.

STEM (docs/STEM_DESIGN.md, section 10.1). Aliases match on word boundaries of the
normalised label (the longest match wins), so "Assessment" or "Stress and Wellness" no
longer reads as ESS and "Free fall" no longer as the Extended Essay. STEM aliases (phys,
chem, bio, cs, comp sci, software engineering, environmental science, statistics, "Maths:
AA", "AA HL", further mathematics, ...) and a ``stem`` profile (general science,
engineering, and any label that names two or more different sciences, such as
"Physics/Chemistry") route to the STEM branches. The sciences, mathematics and Computer
Science profiles state what the deterministic STEM checks decide and what nothing here
establishes, and give the model translator STEM encoding guidance
(:func:`prompt_profile_text`; the pinned prompt version is unchanged).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..ir.schema import Sort
from .contracts import EligibilityClass

SubjectGroup = Literal[
    "language_literature",   # Group 1: Studies in Language and Literature
    "language_acquisition",  # Group 2
    "individuals_societies", # Group 3
    "sciences",              # Group 4
    "mathematics",           # Group 5
    "arts",                  # Group 6
    "core",                  # TOK, Extended Essay
    "unknown",
]

_ARGUMENT = frozenset({EligibilityClass.PROPOSITIONAL_ARGUMENT, EligibilityClass.ARITHMETIC_CONSTRAINT})
_QUANTITATIVE = _ARGUMENT | frozenset({EligibilityClass.QUANTITATIVE_CLAIM})


@dataclass(frozen=True)
class SubjectProfile:
    key: str
    display_name: str
    group: SubjectGroup
    eligible_classes: frozenset[EligibilityClass]
    numeric_sorts: frozenset[Sort]
    argument_only: bool
    aliases: tuple[str, ...]
    can_check: str      # what the formal layer can establish in this subject
    cannot_check: str   # what it must never be taken to establish

    def allows(self, cls: EligibilityClass) -> bool:
        return cls in self.eligible_classes


_ARG_CANNOT = (
    "the truth of any interpretation, evaluation or judgement of quality; whether a "
    "cited source actually supports a claim; historical or factual accuracy"
)

PROFILES: dict[str, SubjectProfile] = {}


def _add(p: SubjectProfile) -> None:
    PROFILES[p.key] = p


#: What the deterministic STEM checks decide (stem.checks, decided by the engine) and what the model translator adds.
_STEM_CAN = (
    "deterministic STEM checks decide, under the STEM tolerance rule, the written arithmetic, substitutions of stated values, unit "
    "conversions, dimension consistency (warnings only), {extra}; the model translator's formalisations add propositional structure "
    "and exact arithmetic on given values but do not check units"
)
_STEM_CANNOT = (
    "physical validity of a model, whether a law applies, the truth of laws, data or constants, readings from diagrams or graphs, "
    "calculus (derivatives, integrals, limits, series), significant-figure policy, the quality of a method or explanation, factual recall"
)

# Group 5 — Mathematics
_MATHS_CAN = _STEM_CAN.format(extra="algebraic steps (rearrangements, inequality steps), stated roots and solution sets, sequences and series arithmetic, exact surds")
_add(SubjectProfile(
    key="mathematics_aa", display_name="Mathematics: Analysis and Approaches", group="mathematics",
    eligible_classes=_QUANTITATIVE, numeric_sorts=frozenset({"Int", "Real"}), argument_only=False,
    aliases=("mathematics: analysis", "math aa", "maths aa", "analysis and approaches", "mathematics aa", "maths: aa", "math: aa",
             "mathematics: aa", "aa hl", "aa sl", "further mathematics", "further maths"),
    can_check=_MATHS_CAN,
    cannot_check=_STEM_CANNOT + "; transcendental identities beyond exact values and 10^-15 enclosures; the correctness of a student's method or presentation",
))
_add(SubjectProfile(
    key="mathematics_ai", display_name="Mathematics: Applications and Interpretation", group="mathematics",
    eligible_classes=_QUANTITATIVE, numeric_sorts=frozenset({"Int", "Real"}), argument_only=False,
    aliases=("mathematics: applications", "math ai", "maths ai", "applications and interpretation", "mathematics ai", "maths: ai", "math: ai",
             "mathematics: ai", "ai hl", "ai sl", "statistics", "stats"),
    can_check=_MATHS_CAN + "; financial maths, rates and ratios on given values",
    cannot_check=_STEM_CANNOT + "; statistical inference or modelling judgements, interpretation of real-world context",
))
_add(SubjectProfile(
    key="mathematics", display_name="Mathematics (unspecified course)", group="mathematics",
    eligible_classes=_QUANTITATIVE, numeric_sorts=frozenset({"Int", "Real"}), argument_only=False,
    aliases=("mathematics", "maths", "math"),
    can_check=_MATHS_CAN,
    cannot_check=_STEM_CANNOT + "; method quality",
))

# Group 4 — Sciences
_SCIENCE_CAN = _STEM_CAN.format(extra="chemical element and charge balances, algebraic rearrangements, show-that targets (warnings), values against the request's givens (warnings)")
#: The specific science subjects: a label naming two or more of them resolves to the ``stem`` profile.
SCIENCE_SUBJECTS = ("physics", "chemistry", "biology", "ess", "sports_science", "design_technology")
for _k, _n, _al in (
    ("physics", "Physics", ("physics", "phys")),
    ("chemistry", "Chemistry", ("chemistry", "chem")),
    ("biology", "Biology", ("biology", "bio")),
    ("ess", "Environmental Systems and Societies", ("environmental systems", "ess", "environmental science")),
    ("sports_science", "Sports, Exercise and Health Science", ("sports, exercise", "sehs", "sports science")),
    ("design_technology", "Design Technology", ("design technology",)),
):
    _add(SubjectProfile(
        key=_k, display_name=_n, group="sciences",
        eligible_classes=_QUANTITATIVE, numeric_sorts=frozenset({"Int", "Real"}), argument_only=False,
        aliases=_al,
        can_check=_SCIENCE_CAN,
        cannot_check=_STEM_CANNOT + "; experimental validity",
    ))
_add(SubjectProfile(
    key="stem", display_name="General Science (STEM)", group="sciences",
    eligible_classes=_QUANTITATIVE, numeric_sorts=frozenset({"Int", "Real"}), argument_only=False,
    aliases=("science", "sciences", "general science", "stem", "engineering"),
    can_check=_SCIENCE_CAN,
    cannot_check=_STEM_CANNOT + "; experimental validity",
))
_add(SubjectProfile(
    key="computer_science", display_name="Computer Science", group="sciences",
    eligible_classes=_QUANTITATIVE, numeric_sorts=frozenset({"Int", "Real"}), argument_only=False,
    aliases=("computer science", "comp sci", "computing", "cs", "computer sci", "software engineering"),
    can_check=_STEM_CAN.format(extra="Boolean identities, stated truth-table rows, based-numeral conversions, exact integer arithmetic and bounds"),
    cannot_check="program behaviour (code is never run or checked), algorithm quality and complexity claims, " + _STEM_CANNOT,
))

# Group 3 — Individuals and Societies
for _k, _n, _al in (
    ("economics", "Economics", ("economics",)),
    ("business_management", "Business Management", ("business management", "business")),
):
    _add(SubjectProfile(
        key=_k, display_name=_n, group="individuals_societies",
        eligible_classes=_QUANTITATIVE, numeric_sorts=frozenset({"Int", "Real"}), argument_only=False,
        aliases=_al,
        can_check="exact arithmetic on given figures (elasticities, break-even, ratios, percentage change), inequality-based comparative claims under explicit assumptions, argument structure",
        cannot_check="whether the assumed economic relationships hold in reality, evaluation quality, factual data",
    ))
for _k, _n, _al in (
    ("history", "History", ("history",)),
    ("geography", "Geography", ("geography",)),
    ("psychology", "Psychology", ("psychology",)),
    ("global_politics", "Global Politics", ("global politics",)),
):
    _add(SubjectProfile(
        key=_k, display_name=_n, group="individuals_societies",
        eligible_classes=_QUANTITATIVE, numeric_sorts=frozenset({"Int", "Real"}), argument_only=False,
        aliases=_al,
        can_check="argument structure (claim -> evidence -> analysis -> judgement -> link), internal consistency of the report, exact consistency of the dates, figures, percentages and chronology it states (ordering, differences, totals), and structural constraints",
        cannot_check=_ARG_CANNOT + "; whether a stated date, figure or attribution is historically accurate (that is for the evidence service and the approved library)",
    ))
for _k, _n, _al in (
    ("philosophy", "Philosophy", ("philosophy",)),
    ("social_anthropology", "Social and Cultural Anthropology", ("anthropology",)),
    ("world_religions", "World Religions", ("world religions",)),
):
    _add(SubjectProfile(
        key=_k, display_name=_n, group="individuals_societies",
        eligible_classes=_ARGUMENT, numeric_sorts=frozenset({"Int"}), argument_only=True,
        aliases=_al,
        can_check="argument structure (evidence -> inference -> conclusion), internal consistency of the report, counts and structural constraints",
        cannot_check=_ARG_CANNOT,
    ))

# Group 1 — Studies in Language and Literature
for _k, _n, _al in (
    ("english_a_literature", "English A: Literature", ("english a: literature", "english literature", "literature")),
    ("english_a_language_literature", "English A: Language and Literature", ("language and literature", "english a: language", "lang lit", "english a")),
    ("literature_performance", "Literature and Performance", ("literature and performance",)),
    ("language_a_other", "Language A (other languages)", (
        "language a", "language a: literature", "language a: language and literature",
        "spanish a", "french a", "german a", "italian a", "portuguese a", "chinese a", "mandarin a", "japanese a",
        "korean a", "arabic a", "russian a", "hindi a", "dutch a", "swedish a", "norwegian a", "danish a",
        "finnish a", "turkish a", "polish a", "greek a", "hebrew a", "indonesian a", "malay a", "thai a",
        "vietnamese a", "swahili a", "afrikaans a",
    )),
    ("english", "English (unspecified course)", ("english",)),
):
    _add(SubjectProfile(
        key=_k, display_name=_n, group="language_literature",
        eligible_classes=_ARGUMENT, numeric_sorts=frozenset({"Int"}), argument_only=True,
        aliases=_al,
        can_check="argument structure of an analysis (quotation -> device -> interpretation -> point), internal consistency, structural counts; quotations are checked verbatim against the supplied text by deterministic code, not by Z3",
        cannot_check=_ARG_CANNOT + "; whether a reading is persuasive or well written",
    ))

# Group 2 — Language acquisition
_add(SubjectProfile(
    key="language_b", display_name="Language B / ab initio", group="language_acquisition",
    eligible_classes=_ARGUMENT, numeric_sorts=frozenset({"Int"}), argument_only=True,
    aliases=("language b", "ab initio", "french b", "spanish b", "german b", "mandarin b"),
    can_check="argument structure and structural counts (word limits, required elements)",
    cannot_check=_ARG_CANNOT + "; linguistic accuracy or register",
))

# Group 6 — Arts
for _k, _n, _al in (
    ("visual_arts", "Visual Arts", ("visual arts", "art")),
    ("music", "Music", ("music",)),
    ("theatre", "Theatre", ("theatre", "theater")),
    ("film", "Film", ("film",)),
    ("dance", "Dance", ("dance",)),
):
    _add(SubjectProfile(
        key=_k, display_name=_n, group="arts",
        eligible_classes=_ARGUMENT, numeric_sorts=frozenset({"Int"}), argument_only=True,
        aliases=_al,
        can_check="argument structure and structural counts",
        cannot_check=_ARG_CANNOT + "; aesthetic judgement",
    ))

# Core
_add(SubjectProfile(
    key="tok", display_name="Theory of Knowledge", group="core",
    eligible_classes=_ARGUMENT, numeric_sorts=frozenset({"Int"}), argument_only=True,
    aliases=("theory of knowledge", "tok"),
    can_check="argument structure (premises -> conclusion), internal consistency, detection of circular or unsupported steps as unentailed conclusions",
    cannot_check=_ARG_CANNOT + "; the truth of knowledge claims",
))
_add(SubjectProfile(
    key="extended_essay", display_name="Extended Essay", group="core",
    eligible_classes=_ARGUMENT, numeric_sorts=frozenset({"Int"}), argument_only=True,
    aliases=("extended essay", "ee"),
    can_check="argument structure, internal consistency, word-count and structural constraints",
    cannot_check=_ARG_CANNOT,
))

UNKNOWN = SubjectProfile(
    key="unknown", display_name="Unrecognised subject", group="unknown",
    eligible_classes=_ARGUMENT, numeric_sorts=frozenset({"Int"}), argument_only=True,
    aliases=(),
    can_check="argument structure and integer structural constraints only (most conservative profile)",
    cannot_check=_ARG_CANNOT + "; quantitative claims are not accepted until the subject is recognised",
)


def _norm(s: str) -> str:
    return re.sub(r" +", " ", re.sub(r"[^a-z0-9: ]+", " ", s.lower())).strip()


#: A Language A course in a language other than English ("Spanish A: Literature"): the
#: generic alias "literature" must not pull such a label onto the English profiles.
_OTHER_LANGUAGE_A_RE = re.compile(
    r"\b(?:spanish|french|german|italian|portuguese|chinese|mandarin|japanese|korean|arabic|russian|hindi|dutch|"
    r"swedish|norwegian|danish|finnish|turkish|polish|greek|hebrew|indonesian|malay|thai|vietnamese|swahili|afrikaans) a\b"
)


def _alias_patterns() -> list[tuple[int, "re.Pattern[str]", SubjectProfile]]:
    out = []
    for p in PROFILES.values():
        for raw in p.aliases:
            a = _norm(raw)
            if a:
                out.append((len(a), re.compile(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])"), p))
    return out


_ALIASES = _alias_patterns()


def resolve_profile(subject: str | None) -> SubjectProfile:
    """Match a free-text subject label (e.g. 'English A: Language and Literature HL')
    to a profile by the longest alias the label contains on word boundaries (an alias
    is never matched inside a longer word: "Assessment" is not ESS); fall back to UNKNOWN.

    Aliases and the label are normalized the same way (lower case, punctuation other
    than ``:`` dropped, whitespace collapsed), so every profile's own display name
    resolves to it. A non-English Language A label resolves to ``language_a_other``
    even though it also contains "literature". A label that names two or more different
    sciences ("Physics/Chemistry") resolves to the ``stem`` profile.
    """
    if not subject:
        return UNKNOWN
    label = _norm(subject)
    if "english" not in label and _OTHER_LANGUAGE_A_RE.search(label):
        return PROFILES["language_a_other"]
    best: tuple[int, SubjectProfile] | None = None
    sciences: set[str] = set()
    for n, rx, p in _ALIASES:
        if rx.search(label):
            if p.key in SCIENCE_SUBJECTS:
                sciences.add(p.key)
            if best is None or n > best[0]:
                best = (n, p)
    if len(sciences) >= 2 and best is not None and best[1].key in SCIENCE_SUBJECTS:
        return PROFILES["stem"]
    return best[1] if best else UNKNOWN


def route_for(cls: EligibilityClass) -> str:
    """Where an ineligible class is routed. Eligible classes return 'z3_engine'."""
    if cls in (EligibilityClass.PROPOSITIONAL_ARGUMENT, EligibilityClass.ARITHMETIC_CONSTRAINT, EligibilityClass.QUANTITATIVE_CLAIM):
        return "z3_engine"
    if cls is EligibilityClass.NOT_ELIGIBLE_FACTUAL:
        return "evidence_service"
    if cls in (EligibilityClass.NOT_ELIGIBLE_INTERPRETIVE, EligibilityClass.NOT_ELIGIBLE_RUBRIC_JUDGMENT):
        return "subject_evaluator"
    return "unresolved"


#: Profiles whose answers mix equations and prose (the STEM branches).
STEM_PROFILE_KEYS = frozenset({*SCIENCE_SUBJECTS, "stem", "mathematics_aa", "mathematics_ai", "mathematics", "computer_science"})
#: Model-facing STEM encoding guidance (TRANSLATOR_VERSION 0.3.0); the pinned prompt version is unchanged.
STEM_ENCODING_GUIDANCE = (
    "STEM encoding: write every numeral as an exact integer or decimal string with no exponent (expand scientific notation exactly); "
    "substitute the stated values for the symbols they bind instead of leaving the symbols free; use one symbol per quantity and "
    "prefix it with the claim it comes from (s<claim>_v) so the symbols of different claims never unify by accident; record a unit "
    "as an assumption, never inside an expression; encode a square root or a trigonometric value as a squared comparison, or report "
    "UNSUPPORTED. "
)


def prompt_profile_text(profile: SubjectProfile) -> str:
    """Short, model-facing description injected into translation prompts (STEM profiles add
    :data:`STEM_ENCODING_GUIDANCE`)."""
    classes = ", ".join(sorted(c.value for c in profile.eligible_classes))
    return (
        f"Subject: {profile.display_name} (IB group: {profile.group}). "
        f"Formalizable claim classes: {classes}. "
        f"The formal check can establish: {profile.can_check}. "
        f"It can never establish: {profile.cannot_check}. "
        + ("Numeric claims are not expected in this subject; encode argument structure only. "
           if profile.argument_only else
           f"Numeric sorts in use: {', '.join(sorted(profile.numeric_sorts))}; keep Int and Real distinct and write numerals as exact strings. ")
        + (STEM_ENCODING_GUIDANCE if profile.key in STEM_PROFILE_KEYS else "")
    )
