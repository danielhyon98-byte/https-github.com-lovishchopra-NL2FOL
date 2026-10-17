"""Every bound of the STEM front end, and the per-profile reading switches.

``StemLimits`` is a frozen dataclass: each loop, recursion and literal the front end
builds is bounded by one of its fields (docs/STEM_DESIGN.md, section 4.9). When a bound
is exceeded the front end records a finding (ST-LIM-001, ST-LIM-002, ST-PARSE-002,
ST-UNDEC-001 or ST-CHEM-001, as the table of section 4.9 says) and keeps the text as a
claim; it never raises and never keeps working past the bound.

``StemProfile`` carries the reading choices that depend on the subject (section 6.3 and
section 10.2): whether chemical equations are read, how a bare ``M`` after a number is
read, whether ``t`` after a number is a tonne, whether Boolean words and indented code
blocks are read, and which of the three STEM modes (``sciences``, ``mathematics``,
``computer_science``) serves the subject.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = ["DEFAULT_LIMITS", "PROFILES", "StemLimits", "StemProfile", "StemMode", "profile_for"]

StemMode = Literal["sciences", "mathematics", "computer_science"]


@dataclass(frozen=True)
class StemLimits:
    """Bounds of section 4.9. Defaults are the design's values."""

    #: the report contract's limit on ``original_response``; the contract rejects longer text first
    max_response_chars: int = 400_000
    #: characters of one math span (LaTeX inline or display, or a math run); beyond: ST-LIM-001, the span stays text
    max_span_chars: int = 2_000
    #: tokens of one math span; beyond: ST-LIM-001
    max_tokens_per_span: int = 400
    #: relation links of one chain; links after this one: ST-LIM-001
    max_chain_links: int = 12
    #: AST nodes of one expression; beyond: ST-LIM-001
    max_ast_nodes: int = 256
    #: AST depth, checked before each descent; beyond: ST-LIM-001
    max_ast_depth: int = 24
    #: integer power |n|; beyond: Unsupported (ST-UNDEC-001), except over a closed base with no unit, where a power up to
    #: 1000 is one value (a ``RealPower``, exact or enclosed by the checks stage)
    max_int_power: int = 12
    #: written scientific exponent |e|; beyond: ST-LIM-001
    max_sci_exponent: int = 99
    #: written digits per number (mantissa digits, both sides of the point); beyond: ST-LIM-001
    max_number_digits: int = 30
    #: readings of one expression; beyond: ST-PARSE-002
    max_readings_per_expression: int = 2
    #: readings of one check; beyond: ST-PARSE-002
    max_readings_per_check: int = 4
    #: bindings kept for matching per symbol; older ones are dropped from matching (ST-SCOPE-001 info)
    max_bindings_per_symbol: int = 8
    #: distinct symbols one check may use (the IR limit is 64); beyond: ST-LIM-001
    max_symbols_per_check: int = 48
    #: interval operands of one Form S check; beyond: ST-LIM-001
    max_interval_operands: int = 6
    #: STEM checks planned per report; beyond: ST-LIM-002 naming the count and the first unchecked ids
    max_checks_per_report: int = 128
    #: math spans (and display rows) read per report; the rest stay text claims and ST-LIM-002 names how many were not read
    max_math_items: int = 1024
    #: statements (claims) per report, the report contract's limit
    max_statements: int = 512
    #: species per side of a chemical equation; beyond: ST-CHEM-001
    max_species_per_side: int = 16
    #: atoms of one element in one species (count bound); beyond: ST-CHEM-001
    max_atoms_per_species: int = 999
    #: nesting of parenthesised groups in a chemical formula; beyond: ST-CHEM-001
    max_chem_group_depth: int = 3
    #: inputs of a truth table (2**5 = 32 rows); beyond: ST-UNDEC-001
    max_truth_table_inputs: int = 5
    #: memoised documents (LRU)
    document_cache_entries: int = 64
    #: recorded formulas an algebra step may include as premises
    max_formulas_per_step: int = 8
    #: digits of one IR literal after decimal-exponent factoring (the IR limit); beyond: ST-LIM-001
    max_literal_digits: int = 40
    #: letters of one letter run segmented for implicit multiplication; beyond: the run is one unknown symbol (ST-PARSE-002)
    max_letter_run: int = 12
    #: characters of one prose line the run finder scans in one pass (longer lines are scanned in windows of this size)
    max_line_chars: int = 20_000
    #: digits of a based numeral (FF₁₆, 0b1010, ...); beyond: ST-LIM-001
    max_based_digits: int = 64
    #: words of a prose label in front of a relation sign ("Energy absorbed = ...")
    max_label_words: int = 6
    #: enclosure bounds used by the checks stage (section 4.9, last row)
    max_log_argument_decimal_exponent: int = 100
    max_exp_argument: int = 700
    max_series_terms: int = 400


DEFAULT_LIMITS = StemLimits()


@dataclass(frozen=True)
class StemProfile:
    """Subject-dependent reading switches for one profile key of ``translate.subjects``."""

    key: str
    mode: StemMode
    #: chemical equations, concentration brackets, chemistry labels (``n(H₂O)``), bond notation
    chemistry: bool = False
    #: a bare ``M`` after a number: ``("molar",)``, ``("mega",)`` or both (two readings, ST-UNIT-002 info)
    bare_m: tuple[str, ...] = ("mega",)
    #: ``t`` after a number is the tonne (ESS and Design Technology only)
    tonne: bool = False
    #: Boolean words AND OR NOT XOR, ⇔ as equivalence, 4-space indented code blocks
    computer_science: bool = False
    #: only the principal (non-negative) root is taken in a step (sciences); mathematics keeps both signs
    principal_root: bool = True

    @property
    def is_mathematics(self) -> bool:
        return self.mode == "mathematics"


def _profiles() -> dict[str, StemProfile]:
    out: dict[str, StemProfile] = {}
    for key, chem, bare_m, tonne in (
        ("physics", False, ("molar", "mega"), False),
        ("chemistry", True, ("molar",), False),
        ("biology", True, ("molar",), False),
        ("ess", True, ("mega",), True),
        ("sports_science", False, ("mega",), False),
        ("design_technology", False, ("mega",), True),
        ("stem", True, ("molar", "mega"), False),
    ):
        out[key] = StemProfile(key=key, mode="sciences", chemistry=chem, bare_m=bare_m, tonne=tonne)
    for key in ("mathematics_aa", "mathematics_ai", "mathematics"):
        out[key] = StemProfile(key=key, mode="mathematics", principal_root=False)
    out["computer_science"] = StemProfile(key="computer_science", mode="computer_science", computer_science=True, principal_root=False)
    return out


#: profile key (as in ``translate.subjects.PROFILES``) -> reading switches
PROFILES: dict[str, StemProfile] = _profiles()


def profile_for(key: "str | StemProfile") -> StemProfile:
    """The reading switches for a STEM profile key. A ``StemProfile`` is returned as is.
    An unknown key raises ``ValueError``: the caller (a STEM branch) always passes a STEM
    profile key, so an unknown one is a wiring fault, not agent text."""
    if isinstance(key, StemProfile):
        return key
    try:
        return PROFILES[key]
    except KeyError:
        raise ValueError(f"unknown STEM profile {key!r}; expected one of {sorted(PROFILES)}") from None
