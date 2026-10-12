"""Hub hooks of the STEM branches (docs/STEM_DESIGN.md, section 11.2).

The channel's request-fidelity heuristics were written for prose answers. Four readings let a
STEM answer, which is mostly equations, be judged on what it says. ``branches.base.BranchHooks``
is the protocol; :data:`STEM_HOOKS` is attached to the ``sciences``, ``mathematics`` and
``computer_science`` branches only, so every other branch behaves exactly as before.

* :meth:`StemHooks.coverage_terms`: words a claim offers the item-coverage heuristic
  (INT-REQ-004) beyond its own words: the names of the dimensions of its quantities and of the
  bound symbols it uses (m s⁻² gives "acceleration"; N gives "force", "weight", "tension"; J gives
  "energy", "work"), so ``a = (20 − 0)/4.0 = 5.0 m s⁻²`` covers "Calculate the acceleration".
  A claim that holds a planned computation (an engine check of its arithmetic, substitution,
  conversion, algebra, roots, balance, Boolean identity or based numeral) also offers the
  computing command words (calculate, determine, find, convert, solve, ...): it does compute.
  The method stays a lexical heuristic.
* :meth:`StemHooks.echo_exempt`: an answer that holds at least one planned computation link
  (``stem-eq``, ``stem-alg`` or ``stem-sol``) whose text is not in the request is never a
  restatement of the request (INT-REQ-011), so the show-that answer ``n = m/M = 36 g / 18 g mol⁻¹
  = 2.0 mol`` to "Show that 36 g of water is 2.0 mol" is an answer.
* :attr:`StemHooks.request_imperatives`: determine, deduce, derive, state, find, solve, sketch,
  estimate, predict, verify, show (each at the start of a sentence or after a part label), so a
  multi-part STEM question becomes one item per part.
* :meth:`StemHooks.word_count_view`: the text a word bound is measured on: each maths span and
  each code block counts as one word, and LaTeX control words are not words.

Every method reads the shared memoised :class:`~.document.StemDocument`, never raises on agent
text (a failure falls back to the channel's own reading), and evaluates nothing.
"""
from __future__ import annotations

import re
from typing import Optional

from .document import StemDocument, build_document
from .limits import PROFILES
from .nodes import Quantity, Sym, WithUnit, walk
from .units import Dimension

__all__ = ["STEM_HOOKS", "StemHooks", "STEM_IMPERATIVES", "dimension_terms"]

STEM_IMPERATIVES = ("determine", "deduce", "derive", "state", "find", "solve", "sketch", "estimate", "predict", "verify", "show")
_MATH_KINDS = frozenset({"latex_display", "latex_inline", "math_run", "verbal", "chem"})
_CODE_KINDS = frozenset({"code_block", "code_inline"})
_ECHO_KINDS = frozenset({"eq", "alg", "sol"})
#: planned check kinds that are computations, and the command words a computing claim offers the coverage heuristic
_COMPUTE_KINDS = frozenset({"eq", "sub", "alg", "sol", "cnv", "cmp", "res", "chem", "bool", "tt", "base"})
_COMPUTE_TERMS = ("calculate", "calculation", "determine", "find", "compute", "work", "show", "solve", "deduce", "derive", "estimate", "verify",
                  "convert", "simplify", "expand", "factorise", "factorize", "balance", "rearrange")
_LATEX_WORD_RE = re.compile(r"\\[A-Za-z]+")
_MAX_TERMS = 128


def _d(m: int = 0, kg: int = 0, s: int = 0, a: int = 0, k: int = 0, mol: int = 0, cd: int = 0) -> tuple[int, ...]:
    return (m, kg, s, a, k, mol, cd)


#: dimension (exponents over m, kg, s, A, K, mol, cd) -> words a request may use for such a quantity
_DIMENSION_TERMS: dict[tuple[int, ...], tuple[str, ...]] = {
    _d(m=1): ("length", "distance", "displacement", "height", "width", "radius", "diameter", "wavelength", "extension", "position", "depth", "range",
              "amplitude", "compression"),
    _d(kg=1): ("mass", "weight"),
    _d(s=1): ("time", "period", "duration", "interval", "half-life"),
    _d(a=1): ("current",),
    _d(k=1): ("temperature",),
    _d(mol=1): ("amount", "moles", "mole", "mol", "substance"),
    _d(m=1, s=-1): ("speed", "velocity"),
    _d(m=1, s=-2): ("acceleration", "deceleration", "gravitational", "field", "strength"),
    _d(m=1, kg=1, s=-2): ("force", "weight", "tension", "thrust", "friction", "drag", "reaction", "resultant", "load", "gravitational", "electric",
                          "electrostatic", "magnetic", "frictional", "normal", "centripetal", "buoyant", "upthrust", "applied", "net"),
    _d(m=2, kg=1, s=-2): ("energy", "work", "heat", "kinetic", "potential", "enthalpy", "torque", "moment"),
    _d(m=2, kg=1, s=-2, mol=-1): ("enthalpy", "energy", "change"),
    _d(m=2, kg=1, s=-3): ("power", "rate"),
    _d(m=-1, kg=1, s=-2): ("pressure", "stress"),
    _d(s=-1): ("frequency", "activity", "rate", "angular"),
    _d(s=1, a=1): ("charge",),
    _d(m=2, kg=1, s=-3, a=-1): ("voltage", "potential", "difference", "emf", "electromotive"),
    _d(m=2, kg=1, s=-3, a=-2): ("resistance",),
    _d(m=3): ("volume", "capacity"),
    _d(m=2): ("area", "surface"),
    _d(m=-3, kg=1): ("density",),
    _d(m=-3, mol=1): ("concentration", "molarity"),
    _d(m=1, kg=1, s=-1): ("momentum", "impulse"),
    _d(kg=1, mol=-1): ("molar", "mass"),
    _d(m=2, s=-2, k=-1): ("specific", "heat", "capacity"),
    _d(kg=1, s=-2, a=-1): ("magnetic", "field", "flux", "density"),
    _d(m=2, kg=1, s=-2, k=-1): ("heat", "capacity", "entropy"),
    _d(m=3, kg=-1, s=-2): ("gravitational", "constant"),
}


def dimension_terms(dim: Optional[Dimension]) -> tuple[str, ...]:
    """The words of :data:`_DIMENSION_TERMS` for a dimension (the angle exponent is ignored)."""
    if dim is None:
        return ()
    return _DIMENSION_TERMS.get(tuple(dim.exps), ())


def _profile(key: str) -> str:
    return key if key in PROFILES else "stem"


class StemHooks:
    """The STEM branches' :class:`~epinoic_logic.branches.base.BranchHooks` (module docstring)."""

    request_imperatives: tuple[str, ...] = STEM_IMPERATIVES

    @staticmethod
    def _doc(report_text: str, request_text: Optional[str], profile_key: str) -> StemDocument:
        return build_document(report_text, request_text, _profile(profile_key))

    def coverage_terms(self, claim_text: str, report_text: str, request_text: Optional[str], profile_key: str) -> frozenset[str]:
        """Dimension words of the quantities and bound symbols of the statement(s) holding ``claim_text``."""
        try:
            if not claim_text or not report_text:
                return frozenset()
            doc = self._doc(report_text, request_text, profile_key)
            at = report_text.find(claim_text)
            if at < 0:
                return frozenset()
            end = at + len(claim_text)
            sids = [st.id for st in doc.statements if st.start < end and at < st.end]
            terms: list[str] = []
            if any(r.kind in _COMPUTE_KINDS for sid in sids for r in doc.checks_for(sid)):
                terms.extend(_COMPUTE_TERMS)
            for sid in sids:
                for item in doc.items_for(sid):
                    for chain in item.chains:
                        for op in chain.operands:
                            for reading in op.readings:
                                for node in walk(reading):
                                    terms.extend(self._node_terms(node, doc))
                for pv in doc.prose_values:
                    if pv.statement_id == sid:
                        for node in walk(pv.node):
                            terms.extend(self._node_terms(node, doc))
                if len(terms) > _MAX_TERMS:
                    break
            return frozenset(terms[:_MAX_TERMS])
        except Exception:  # a heuristic aid: on any failure the channel's own reading stands
            return frozenset()

    @staticmethod
    def _node_terms(node: object, doc: StemDocument) -> tuple[str, ...]:
        if isinstance(node, (Quantity, WithUnit)):
            unit = node.unit
            return dimension_terms(unit.dim) if unit is not None and not unit.unknown else ()
        if isinstance(node, Sym):
            out: list[str] = []
            for b in doc.bindings.get(node.name, ()):
                if b.unit is not None and not b.unit.unknown:
                    out.extend(dimension_terms(b.unit.dim))
            return tuple(out)
        return ()

    def echo_exempt(self, report_text: str, request_text: str, profile_key: str) -> bool:
        """True when the answer holds a planned computation link whose text the request does not contain."""
        try:
            doc = self._doc(report_text, request_text, profile_key)
            ask = " ".join((request_text or "").split())
            for rel in doc.checks:
                if rel.kind not in _ECHO_KINDS:
                    continue
                link = " ".join(report_text[rel.start:rel.end].split())
                if link and link not in ask:
                    return True
            return False
        except Exception:
            return False

    def word_count_view(self, text: str, profile_key: str) -> str:
        """``text`` with each maths span and code block replaced by one word (its newlines kept, so
        paragraphs do not move) and LaTeX control words outside them removed."""
        try:
            doc = self._doc(text, None, profile_key)
            spans = sorted((sp.start, sp.end, sp.kind) for sp in doc.spans.spans if sp.kind in _MATH_KINDS or sp.kind in _CODE_KINDS)
            parts: list[str] = []
            pos = 0
            for a, b, kind in spans:
                if a < pos:
                    continue
                parts.append(_LATEX_WORD_RE.sub(" ", text[pos:a]))
                word = "Xcode" if kind in _CODE_KINDS else "Xmath"
                parts.append(f" {word} " + "\n" * text.count("\n", a, b))
                pos = b
            parts.append(_LATEX_WORD_RE.sub(" ", text[pos:]))
            return "".join(parts)
        except Exception:
            return text


STEM_HOOKS = StemHooks()
