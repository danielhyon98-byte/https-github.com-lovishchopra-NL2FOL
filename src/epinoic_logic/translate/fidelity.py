"""Deterministic comparisons of an encoding with the claim it encodes (round 9, clearance c2, second fix pass).

The arena's translation-fidelity lens found encodings whose verdict was displayed although the encoding does not say what
the claim says: a COUNTEREXAMPLE that turns only on an atom the specialist's own cited reasoning supports but the
translation left unlinked (lit-t15 p1-point), and ENTAILED verdicts on encodings that check another claim's content
(ch-t15 s4.1, c1 bm-t14 g6.1), drop the claim's bracketed qualifier (cs-t15 c6.6), leave the claim's stated reason
unconnected to its consequence (ph-t15 s7.4), or conclude, as the writer's own inference, a statement the claim only
reports from another source in a quotation (ess-p9c s7.3). Each reader here compares the encoding's own texts (premise
labels, symbol meanings, the conclusion label) and literals with the claim's text, its supporting claims, the report's
other claims, the supplied texts and the task record, and names the mismatch as an ambiguity flag: the pipeline then
returns AMBIGUOUS_TRANSLATION with the reason named, so the engine's verdict is never displayed as a verdict on the claim.
A flag is never a verdict either way: it says only that the encoding and the claim differ in a way the reader can see.

* :func:`unencoded_support` (flag ``UNENCODED_SUPPORT``): the conclusion has Bool atoms no premise mentions while the
  premises reach the rest of it (the engine's "judgement not linked" shape), and a supporting claim the claim cites (not an
  evidence line) states such an atom (at least two content stems, half of the atom's) while the encoding encodes nothing
  of that supporting claim (it shares fewer than two content stems with every premise label and every meaning of a symbol
  a premise uses). The pipeline flags it only when the encoding's own verdict is a COUNTEREXAMPLE: that counterexample
  would only show that the translation left out a reason the specialist gives.
* :func:`neighbour_content` (flag ``neighbour_content``): a claim that states a figure of its own (one that is not 0, 1,
  10, 100 or 1000; a claim with none may rest on the answer's data) has a conclusion that checks none of its figures, and every
  figure it checks that no supporting claim, earlier line of the claim's own paragraph, supplied text or task record states
  is stated by claims of the report the claim does not cite: the verdict would be about another claim's content ("This
  value is for the reaction as written, which forms 2 mol of NH₃." concluded ``c_nh3 × 3 = 6``, the bond count of s3.2;
  "Next practice task: move the $3,000 kiln deposit to March ..." concluded the answer key's $4,100 of the claim after it).
  A figure no text states (the translation's own, such as a row index) is no other claim's content, so it never fires the
  rule.
* :func:`dropped_qualifier` (flag ``qualifier_not_encoded``): a bracketed qualifier of the claim (no figure, no reference
  or example cue, no quotation, not an abbreviation) none of whose content stems the encoding's labels or meanings hold,
  while the rest of the claim is encoded: the verdict would cover the claim without it ("... the MAC address of the next
  device (the switch or router) ...", the part of the claim that is false).
* :func:`reason_unconnected` (flag ``reason_unconnected``): the claim draws its consequence from a reason clause by a
  reason connective, the encoding states that reason (a premise label or a used symbol's meaning shares at least two
  content stems with it, and more than with the consequence), every conclusion symbol is mentioned by a premise (so the
  verdict is decided by premises, not by a conclusion left unlinked: that non sequitur shape is the engine's
  counterexample and ``UNENCODED_REASON``'s), and no chain of premises connects the reason's symbols to any symbol of the
  conclusion: the verdict would not depend on the claim's own inference.
* :func:`reported_conclusion` (flag ``reported_conclusion``): the conclusion is a Bool statement whose words the claim
  writes only inside a quotation it credits to another source with a reporting verb ("the Geography specialist notes that
  '..., so the difference in timing comes from the catchment itself'"), and the encoding concludes it as the writer's own
  (a writer's kind or no grounding): the verdict would present the reported inference as the claim's.
* :func:`stated_values_not_encoded` (flag ``values_not_encoded``): the claim lists, after a result word, at least three values
  its check gives ("the original expression gives 1, 0, 1, 0"), and the encoding encodes none of them (no literal, interval or,
  for truth values, truth value of the conclusion): the verdict would cover the claim's conclusion without the values it
  states (c1 cs-t14 c25.1, encoded as the identity its supporting chain derives).

Every reader is bounded (the claim read to :data:`MAX_CLAIM_CHARS`, at most :data:`MAX_REPORT_CLAIMS` claims, each a single
pass of the shared tokenizer and the figure reader) and reads the problem and the texts as data; nothing is evaluated.
"""
from __future__ import annotations

import json
import re
from fractions import Fraction
from typing import Any, Optional, Sequence

from .. import lexis
from ..ir.schema import Problem
from .common import truncate
from .contracts import AmbiguityFlag, ClaimRecord, SpecialistReport, TaskRecord

__all__ = ["MAX_CLAIM_CHARS", "MAX_REPORT_CLAIMS", "unencoded_support", "unencoded_support_flag", "neighbour_content", "dropped_qualifier",
           "reason_unconnected", "reported_conclusion", "stated_values_not_encoded", "consequence_unchecked", "conjunct_asserted",
           "reason_not_encoded", "fidelity_flags"]

#: The longest claim text read (characters).
MAX_CLAIM_CHARS = 4_000
#: At most this many claims of a report are read for figures (the contract's limit).
MAX_REPORT_CLAIMS = 512
#: Roles of a supporting claim that carry evidence rather than the specialist's reasoning.
_EVIDENCE_ROLES = frozenset({"evidence", "counter_evidence", "other"})
#: Kinds by which a symbol or premise is the writer's own (or carries no grounding at all).
_WRITER_KINDS = frozenset({None, "specialist_inference", "assumption", "general_knowledge"})


# ----------------------------------------------------------------------------------------------- shared readers

def _dump(node: Any) -> dict:
    return node.model_dump(mode="json", exclude_none=True) if hasattr(node, "model_dump") else node


def _names(node: Any) -> set[str]:
    """Every symbol name an IR expression dict mentions (iterative)."""
    out: set[str] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("op") == "var" and isinstance(n.get("name"), str):
                out.add(n["name"])
                continue
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(n)
    return out


def _literals(node: Any) -> list[tuple[str, Fraction]]:
    """``(written, value)`` of every numeric literal of an IR expression dict (a negation of one read as negative)."""
    out: list[tuple[str, Fraction]] = []
    stack: list[tuple[Any, bool]] = [(node, False)]
    while stack:
        n, neg = stack.pop()
        if isinstance(n, dict):
            op = n.get("op")
            if op in ("int", "real"):
                try:
                    v = Fraction(str(n.get("value")))
                except (ValueError, ZeroDivisionError):
                    continue
                out.append((("-" if neg else "") + str(n.get("value")), -v if neg else v))
                continue
            if op == "neg":
                stack.append((n.get("arg"), not neg))
                continue
            stack.extend((v, False) for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend((v, False) for v in n)
    return out


def _stems(text: Optional[str]) -> set[str]:
    return set(lexis.content_stems((text or "")[:MAX_CLAIM_CHARS]))


def _masked(text: str) -> str:
    from .diag_argument import mask_quotations
    return mask_quotations((text or "")[:MAX_CLAIM_CHARS])


def _used(problem: Problem) -> set[str]:
    out: set[str] = set()
    for p in problem.premises:
        out |= _names(_dump(p.expr))
    return out


def _encoded_stem_sets(problem: Problem) -> list[set[str]]:
    """The content stems of each premise label and of each meaning of a symbol a premise uses."""
    used = _used(problem)
    texts = [p.label or "" for p in problem.premises] + [s.meaning or "" for s in problem.symbols if s.name in used]
    return [st for st in (_stems(t) for t in texts) if st]


def _encoding_stems(problem: Problem) -> set[str]:
    """Every content stem the encoding's own texts hold: premise labels, symbol meanings, the conclusion label."""
    out: set[str] = set()
    for p in problem.premises:
        out |= _stems(p.label)
    for s in problem.symbols:
        out |= _stems(s.meaning)
        out |= set(lexis.content_stems(s.name.replace("_", " ")))
    if problem.conclusion is not None:
        out |= _stems(problem.conclusion.label)
    return out


def _meaning(problem: Problem, name: str) -> str:
    sym = next((s for s in problem.symbols if s.name == name), None)
    return (sym.meaning if sym is not None and sym.meaning else name.replace("_", " "))


def _flag(code: str, message: str, alternatives: Sequence[str] = ()) -> AmbiguityFlag:
    return AmbiguityFlag(code=code, message=truncate(message, 2000), alternatives=[truncate(a, 200) for a in list(alternatives)[:8]])


# ----------------------------------------------------------------------------------------------- UNENCODED_SUPPORT

def unencoded_support(problem: Problem, claim: ClaimRecord, supporting: Sequence[ClaimRecord]) -> Optional[tuple[list[str], list[str]]]:
    """``(atoms, supporting claim ids)`` when the conclusion's Bool atoms that no premise mentions (while the premises
    reach the rest of the conclusion) are stated by a supporting claim of the claim that the encoding encodes nothing of
    (module docstring), else None. The caller asks the engine whether the encoding's verdict is a COUNTEREXAMPLE."""
    if problem.query != "entailment" or problem.conclusion is None or not problem.premises or not supporting:
        return None
    concl_vars = _names(_dump(problem.conclusion.expr))
    premise_vars = _used(problem)
    sorts = {s.name: s.sort for s in problem.symbols}
    free = sorted(concl_vars - premise_vars)
    if not free or not (concl_vars & premise_vars) or any(sorts.get(v) != "Bool" for v in free):
        return None
    encoded = _encoded_stem_sets(problem)
    readings: list[tuple[str, set[str]]] = []
    for c in list(supporting)[:MAX_REPORT_CLAIMS]:
        if c.claim_id == claim.claim_id or c.claim_role in _EVIDENCE_ROLES:
            continue
        stems = _stems(_masked(c.claim_text))
        if len(stems) < 2 or any(len(stems & e) >= 2 for e in encoded):
            continue  # too short to read, or the encoding encodes it
        readings.append((c.claim_id, stems))
    atoms: list[str] = []
    ids: list[str] = []
    for v in free:
        want = _stems(_meaning(problem, v))
        if len(want) < 2:
            continue
        for cid, stems in readings:
            shared = stems & want
            if len(shared) >= 2 and 2 * len(shared) >= len(want):
                atoms.append(v)
                ids.append(cid)
                break
    return (atoms, list(dict.fromkeys(ids))) if atoms else None


def unencoded_support_flag(problem: Problem, atoms: Sequence[str], ids: Sequence[str], supporting: Sequence[ClaimRecord]) -> AmbiguityFlag:
    """The ``UNENCODED_SUPPORT`` flag of :func:`unencoded_support`'s finding (the caller decided the verdict is a
    COUNTEREXAMPLE)."""
    texts = {c.claim_id: c.claim_text for c in supporting}
    shown_atoms = ", ".join(f"{a} ({truncate(_meaning(problem, a), 80)!r})" for a in list(atoms)[:4])
    shown_claims = "; ".join(f"{cid} ({truncate(texts.get(cid, ''), 120)!r})" for cid in list(ids)[:3])
    return _flag("UNENCODED_SUPPORT",
                 f"(deterministic) the counterexample turns on conclusion atom(s) {shown_atoms} that no premise mentions, while the claim's "
                 f"supporting claim(s) {shown_claims}, which the encoding encodes nothing of, state them: the translation left out a reason the "
                 "specialist gives, so the counterexample is no verdict on the claim (an incomplete encoding, not a failed check)",
                 [f"the encoding with the reasoning of {', '.join(list(ids)[:3])} linked to the conclusion", "the encoding as given: COUNTEREXAMPLE"])


# ----------------------------------------------------------------------------------------------- neighbour_content

#: A claim id's paragraph: the letters and number before its first "." or "-" ("s8" of "s8.3", "g6" of "g6.1@agent", "p1" of
#: "p1-s04"); the parsers number claims by paragraph or part, so claims with one key stand in one paragraph of working.
_PARAGRAPH_RE = re.compile(r"^([A-Za-z]+\d+)[.-]")


def _earlier_in_paragraph(claim: ClaimRecord, report: SpecialistReport) -> list[str]:
    """The ids of the (at most three) claims of the claim's own paragraph that the report holds before it: the previous lines
    of the working the claim continues ("Hydrogen needed = 3 × 600 = 1800 cm³." before "Only 1500 cm³ of H₂ is available, so
    hydrogen is the limiting reactant.")."""
    m = _PARAGRAPH_RE.match(claim.claim_id.split("@", 1)[0])
    if m is None:
        return []
    ids = [c.claim_id for c in report.claims[:MAX_REPORT_CLAIMS]]
    if claim.claim_id not in ids:
        return []
    at = ids.index(claim.claim_id)
    out: list[str] = []
    for cid in reversed(ids[max(0, at - 3):at]):
        k = _PARAGRAPH_RE.match(cid.split("@", 1)[0])
        if k is None or k.group(1) != m.group(1):
            break
        out.append(cid)
    return out


def neighbour_content(problem: Problem, claim: ClaimRecord, supporting: Sequence[ClaimRecord], report: Optional[SpecialistReport],
                      task: Optional[TaskRecord] = None) -> Optional[AmbiguityFlag]:
    """The ``neighbour_content`` flag (module docstring), or None."""
    from .quantities import TRIVIAL_VALUES, SourceText, figures_in, literal_matches
    if problem.conclusion is None or report is None:
        return None
    lits = [(w, v) for w, v in _literals(_dump(problem.conclusion.expr)) if abs(v) not in TRIVIAL_VALUES]
    if not lits:
        return None
    own = figures_in(SourceText("claim", claim.claim_id, (claim.claim_text or "")[:MAX_CLAIM_CHARS]))
    if not any(abs(f.value) not in TRIVIAL_VALUES for f in own):
        return None  # a claim that states no figure of its own may rest on the answer's data (c1 ph-p8b s6.2: "the speed is zero, so ...")
    if any(literal_matches(v, own, conversions=True)[0] for _w, v in lits):
        return None  # the conclusion checks a figure the claim states
    cited = set(claim.supporting_claim_ids) | {claim.claim_id} | set(_earlier_in_paragraph(claim, report))
    allowed = [SourceText("supporting_claim", c.claim_id, (c.claim_text or "")[:MAX_CLAIM_CHARS]) for c in report.claims if c.claim_id in cited and c.claim_id != claim.claim_id]
    allowed += [SourceText("supplied_text", t.document_id, t.text) for t in report.supplied_texts]
    if task is not None:
        allowed.append(SourceText("task", task.task_id, task.text))
    allowed_figures = [f for s in allowed for f in figures_in(s)]
    pending = [(w, v) for w, v in lits if not literal_matches(v, allowed_figures, conversions=True)[0]]
    if not pending:
        return None
    holders: dict[str, list[str]] = {}
    for c in report.claims[:MAX_REPORT_CLAIMS]:
        if c.claim_id in cited:
            continue
        figs = figures_in(SourceText("supporting_claim", c.claim_id, (c.claim_text or "")[:MAX_CLAIM_CHARS]))
        if not figs:
            continue
        for w, v in pending:
            if literal_matches(v, figs, conversions=True)[0]:
                holders.setdefault(w, []).append(c.claim_id)
    if not holders or len(holders) < len({w for w, _v in pending}):
        return None  # a figure of the conclusion no text states (the translation's own) is not another claim's content
    shown = "; ".join(f"{w} (stated by {', '.join(ids[:3])})" for w, ids in list(holders.items())[:4])
    return _flag("neighbour_content",
                 f"(deterministic) the conclusion checks figure(s) {shown} that the claim does not state, and only claims of the report that the "
                 "claim does not cite state them (no supporting claim, earlier line of its paragraph, supplied text or task record does), while it "
                 "checks no figure the claim states: the verdict would be about another claim's content, not this claim's",
                 ["the encoding of what this claim states", "the encoding as given (another claim's figures)"])


# ----------------------------------------------------------------------------------------------- qualifier_not_encoded

#: A bracketed aside of a claim, no nested brackets, at most 120 characters.
_PAREN_RE = re.compile(r"\(([^()\n]{2,120})\)")
#: Asides that cite, label, exemplify or restate rather than qualify ("(see Source A)", "(e.g. ...)", "(Figure 2)").
_ASIDE_CUE_RE = re.compile(r"^\s*(?:see|cf\b|e\.?\s?g\b|eg\b|for\s+(?:example|instance)|such\s+as|including|source|sources|from|line|lines|p\b|pp\b|"
                           r"para|paragraph|page|figure|fig\b|table|chart|graph|part|question|q\b|mark|marks|note|ibid|ref|reference|section|"
                           r"appendix|stanza|act|scene|chapter|extract|text|doc|document|data|booklet|formula|unit|units|in\s+(?:words|full)|"
                           r"approx|about|around|roughly|nearly|almost|i\.?\s?e\b|that\s+is|or\s+)", re.IGNORECASE)
_QUOTE_MARKS = frozenset("\"'“”‘’«»")


def _qualifier_stems(inner: str) -> Optional[set[str]]:
    """The content stems of a bracketed aside that may qualify the claim, or None for one that cites, labels, exemplifies,
    quotes, abbreviates, states a figure or a single letter, or holds fewer than one content stem of three letters."""
    if any(ch.isdigit() for ch in inner) or any(ch in _QUOTE_MARKS for ch in inner) or _ASIDE_CUE_RE.match(inner):
        return None
    toks = [t for t in lexis.tokens(inner)]
    if not toks or all(len(t) <= 2 for t in toks):
        return None
    letters = [t for t in inner.split() if any(ch.isalpha() for ch in t)]
    if letters and all(t.strip(".,;:!?").isupper() for t in letters):
        return None  # an abbreviation ("(MAC)", "(GDP)")
    stems = {s for s in lexis.content_stems(inner) if len(s) >= 3}
    return stems or None


def dropped_qualifier(problem: Problem, claim: ClaimRecord) -> Optional[AmbiguityFlag]:
    """The ``qualifier_not_encoded`` flag (module docstring), or None."""
    if problem.conclusion is None:
        return None
    text = (claim.claim_text or "")[:MAX_CLAIM_CHARS]
    if "(" not in text:
        return None
    encoded = _encoding_stems(problem)
    dropped: list[str] = []
    for m in _PAREN_RE.finditer(text):
        stems = _qualifier_stems(m.group(1))
        if stems is not None and not (stems & encoded):
            dropped.append(m.group(0))
    if not dropped:
        return None
    rest = _stems(_PAREN_RE.sub(" ", text))
    if len(rest & encoded) < 2:
        return None  # the encoding is not of this claim's words at all: another reader's business
    shown = ", ".join(repr(truncate(d, 80)) for d in dropped[:3])
    return _flag("qualifier_not_encoded",
                 f"(deterministic) the claim's bracketed qualifier(s) {shown} are in no premise label, symbol meaning or conclusion label of the "
                 "encoding, while the rest of the claim is encoded: the verdict would cover the claim without them, and a qualifier can be the "
                 "part that makes the claim true or false; encode it, or flag why it does not change the claim",
                 ["the claim with its qualifier encoded", "the encoding as given (the qualifier dropped)"])


# ----------------------------------------------------------------------------------------------- reason_unconnected

def _reason_clause(text: str) -> Optional[tuple[set[str], set[str]]]:
    """``(reason stems, consequence stems)`` of the first reason connective of the claim (quotations masked), read as
    ``pipeline._unencoded_reason`` reads it ("R, so C", "C because R"), or None."""
    from .diag_argument import REASON_CONNECTIVES
    from .pipeline import _REASON_AFTER, _boundaries
    masked = _masked(text)
    spans = lexis.token_spans(masked)
    toks = tuple(t for _s, _e, t in spans)
    ends = _boundaries(masked)
    for i, cue in lexis.find_cues(toks, REASON_CONNECTIVES):
        if cue == ("because",) and i + 1 < len(toks) and toks[i + 1] == "of":
            continue
        at = spans[i][0]
        stop = next((e for e in ends if e > at), len(masked))
        start = max((e for e in ends if e < at), default=-1)
        before = [k for k in range(0, i) if spans[k][0] > start]
        after = [k for k in range(i + len(cue), len(spans)) if spans[k][0] < stop]
        reason, consequence = (after, before) if cue in _REASON_AFTER else (before, after)
        r = set(lexis.content_stems([toks[k] for k in reason]))
        c = set(lexis.content_stems([toks[k] for k in consequence]))
        if len(r) >= 2 and len(c) >= 2:
            return r, c
    return None


def reason_unconnected(problem: Problem, claim: ClaimRecord) -> Optional[AmbiguityFlag]:
    """The ``reason_unconnected`` flag (module docstring), or None."""
    if problem.query != "entailment" or problem.conclusion is None or not problem.premises:
        return None
    clause = _reason_clause(claim.claim_text or "")
    if clause is None:
        return None
    reason, consequence = clause
    concl_vars = _names(_dump(problem.conclusion.expr))
    used = _used(problem)
    if not concl_vars or not concl_vars <= used:
        return None  # a conclusion symbol no premise mentions: the non sequitur shape, the engine's and UNENCODED_REASON's to name
    reason_vars: set[str] = set()
    for p in problem.premises:
        st = _stems(p.label)
        if len(st & reason) >= 2 and len(st & reason) > len(st & consequence):
            reason_vars |= _names(_dump(p.expr))
    for s in problem.symbols:
        if s.name in used:
            st = _stems(s.meaning)
            if len(st & reason) >= 2 and len(st & reason) > len(st & consequence):
                reason_vars.add(s.name)
    if not reason_vars or reason_vars & concl_vars:
        return None
    # the symbols the premises connect to the reason's (each premise joins every symbol it mentions)
    groups = [_names(_dump(p.expr)) for p in problem.premises]
    reached = set(reason_vars)
    changed = True
    rounds = 0
    while changed and rounds <= len(groups):
        changed = False
        rounds += 1
        for g in groups:
            if g & reached and not g <= reached:
                reached |= g
                changed = True
    if reached & concl_vars:
        return None
    shown = ", ".join(sorted(reason_vars)[:6])
    return _flag("reason_unconnected",
                 f"(deterministic) the claim draws its consequence from a reason it states, and the encoding states that reason (symbol(s) {shown}) "
                 "but no premise connects it to the conclusion: the verdict would not depend on the claim's own inference; encode the claim's "
                 "link from its reason to its consequence",
                 ["the claim's reason linked to its consequence", "the encoding as given (the reason unconnected)"])


# ----------------------------------------------------------------------------------------------- reported_conclusion

#: A reporting verb or phrase that credits the words after it to another source.
_REPORTING_RE = re.compile(r"\b(?:notes?|noted|says?|said|writes?|wrote|argues?|argued|reports?|reported|states?|stated|claims?|claimed|"
                           r"suggests?|suggested|observes?|observed|concludes?|concluded|explains?|explained|insists?|insisted|"
                           r"according\s+to|in\s+(?:his|her|their|its)\s+words)\b", re.IGNORECASE)


def reported_conclusion(problem: Problem, claim: ClaimRecord) -> Optional[AmbiguityFlag]:
    """The ``reported_conclusion`` flag (module docstring), or None."""
    if problem.conclusion is None:
        return None
    expr = _dump(problem.conclusion.expr)
    concl_vars = _names(expr)
    syms = {s.name: s for s in problem.symbols}
    if not concl_vars or any(syms.get(v) is None or syms[v].sort != "Bool" for v in concl_vars):
        return None
    if any((syms[v].grounding.kind if syms[v].grounding is not None else None) not in _WRITER_KINDS for v in concl_vars):
        return None  # the translation grounds the conclusion in a source: a transcription, not the writer's own inference
    text = (claim.claim_text or "")[:MAX_CLAIM_CHARS]
    masked = _masked(text)
    if masked == text:
        return None  # no quotation
    first = next((k for k, (a, b) in enumerate(zip(text, masked)) if a != b), None)
    if first is None or _REPORTING_RE.search(masked, 0, first) is None:
        return None
    inside = _stems("".join(a if a != b else " " for a, b in zip(text, masked)))  # the quoted words (masking keeps blanks)
    outside = _stems(masked)
    want: set[str] = set()
    for v in concl_vars:
        want |= _stems(_meaning(problem, v))
    if len(want) < 2:
        return None
    shared = want & inside
    if len(shared) < 2 or 3 * len(shared) < 2 * len(want) or len(want & outside) >= 2:
        return None
    return _flag("reported_conclusion",
                 "(deterministic) the conclusion states what the claim writes only inside a quotation it credits to another source (a reporting "
                 "verb before it), while the encoding concludes it as the writer's own inference: the verdict would present the reported "
                 "inference as the claim's; encode what the claim itself asserts (that the source says it, or the claim's own point)",
                 ["the claim's own assertion encoded", "the encoding as given (the reported inference concluded)"])


# ----------------------------------------------------------------------------------------------- values_not_encoded

#: A run of at least three values the claim says its check gives, right after a result word ("the original expression gives
#: 1, 0, 1, 0", "the outputs are 0, 1, 1 and 0"): numbers joined only by a comma or "and". Each repetition consumes a
#: separator (a comma, or "and" between blanks) and a digit, and a number cannot end where a separator starts, so a run is
#: matched in one pass without backtracking over its members. The blanks before an optional ':' or '=' belong to that sign
#: (``(?:[ \t]*[:=])?[ \t]*``): two adjacent blank runs around an optional sign would split one long run of blanks every way
#: before failing (quadratic in the run; the class sweep of this pass).
_VALUE_RUN_RE = re.compile(
    r"\b(?:gives?|gave|giving|outputs?|returns?|yields?|produces?|evaluates?\s+to|equals?|are|were|is|was)(?:[ \t]*[:=])?[ \t]*"
    r"(?P<run>[-−]?\d+(?:\.\d+)?%?(?:(?:[ \t]*,[ \t]*(?:and[ \t]+)?|[ \t]+and[ \t]+)[-−]?\d+(?:\.\d+)?%?){2,})",
    re.IGNORECASE)
#: The most value runs of one claim read.
_MAX_VALUE_RUNS = 16


def _has_bool_const(node: Any) -> bool:
    """Whether an IR expression dict holds a truth value (``{"op": "bool"}``) anywhere (iterative)."""
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("op") == "bool":
                return True
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(n)
    return False


def stated_values_not_encoded(problem: Problem, claim: ClaimRecord) -> Optional[AmbiguityFlag]:
    """The ``values_not_encoded`` flag, or None. Round 9 (c2 translation-fidelity, the c1 case of the critical finding on
    meaning-changing translation faults; c1 translation-fidelity #12): c1 cs-t14 c25.1 ("Check: for A, B = 00, 01, 10 and 11,
    the original expression gives 1, 0, 1, 0, and NOT B gives 1, 0, 1, 0.") was encoded as the identity its supporting chain
    derives, so a check whose stated values were wrong ("gives 1, 1, 1, 0") would have been displayed ENTAILED as well: the
    claim lists, after a result word, at least three values its check gives (years, code numerals such as "01" and number
    words apart), and the encoding encodes none of them: no numeric literal of the problem is any of them in any typed form,
    no interval holds one, and, for values that are all 0 or 1 (truth values), the conclusion holds no truth value. The verdict
    would then cover the claim's conclusion without the values it states, so the outcome is AMBIGUOUS_TRANSLATION. An encoding
    that encodes one value of the run (the rows it checks, or a figure of the list) is untouched. Deterministic, bounded and
    linear: the claim read to :data:`MAX_CLAIM_CHARS`, at most :data:`_MAX_VALUE_RUNS` runs."""
    from .pipeline import _all_literal_values, _is_code_numeral
    from .precision import collect_sites
    from .quantities import SourceText, figures_in, is_year_like, literal_matches
    if problem.conclusion is None:
        return None
    text = (claim.claim_text or "")[:MAX_CLAIM_CHARS]
    if not any(ch.isdigit() for ch in text):
        return None
    literals: Optional[list[Fraction]] = None
    intervals: list[tuple[Fraction, Fraction]] = []
    truth_values = _has_bool_const(_dump(problem.conclusion.expr))
    for k, m in enumerate(_VALUE_RUN_RE.finditer(text)):
        if k >= _MAX_VALUE_RUNS:
            break
        a, b = m.span("run")
        figures = [f for f in figures_in(SourceText("claim", claim.claim_id, text[a:b]))
                   if not (f.word or is_year_like(f) or _is_code_numeral(f, text[a:b]))]
        if len(figures) < 3:
            continue
        if literals is None:
            literals = _all_literal_values(problem)
            intervals = [(site.lo, site.hi) for site in collect_sites(problem) if site.kind == "interval" and site.lo is not None and site.hi is not None]
        if truth_values and all(f.value * f.scale in (0, 1) for f in figures):
            continue  # truth values the conclusion checks
        if any(literal_matches(v, figures, conversions=True)[0] for v in literals):
            continue
        if any(lo <= c <= hi for f in figures for c in {f.value, f.value * f.scale} for lo, hi in intervals):
            continue
        run = text[max(0, m.start()):b]
        return _flag("values_not_encoded",
                     f"(deterministic) the claim states the values its check gives ({truncate(run, 160)!r}) and the encoding encodes none of them "
                     "(no literal, interval or truth value of the problem is one of them): the verdict would cover the claim's conclusion without "
                     "the values it states, so a wrong value would pass as well; encode each stated case with its value",
                     ["the encoding of each stated value", "the encoding as given (the stated values left out)"])
    return None


# ------------------------------------------------------------------------- round-10 clearance (c3): the claim's own point dropped
# The c3 translation-fidelity lens found three encodings displayed ENTAILED with no finding although their conclusion is not the
# claim's (fidelity reference, causes F, S and D): sp-t16 g1.22 concluded a premise restated and the rule's consequent while the
# claim's point, the correction 'vemos' -> 'veamos', sat in a declared symbol nothing used; ess-t16 s7.1 asserted its conjunct
# 'its costs fall on particular groups' as a writer's premise on the conjunct's own symbol, though the supporting claim s10.2
# states the costs it rests on; ph-t16 s2.8 ("A gas-law ratio needs kelvin, so the ratio is 308/290, not 35/17") checked only
# 308/290 != 35/17, its reason and the kelvin step dropped. Each reader below names the shape as an ambiguity flag (the outcome is
# AMBIGUOUS_TRANSLATION, never a verdict on the claim). The fourth c3 shape, a conditional claim proved from its own conditional
# (bm-t16 g15.3), is the translator's E112 (``restatement``, rule link-weakening).

#: A consequence or a correction the conclusion's label states after it: "so", "therefore", "thus", "hence", an arrow, "should read".
_CONSEQUENCE_CUE_RE = re.compile(r"(?:,[ \t]{0,3}|[ \t])(?:so|therefore|thus|hence)\b|→|->|⇒|=>|\bshould[ \t]{1,3}(?:read|be)\b", re.IGNORECASE)


def _symbol_kind(sym) -> Optional[str]:
    return sym.grounding.kind if sym.grounding is not None else None


def consequence_unchecked(problem: Problem, claim: ClaimRecord) -> Optional[AmbiguityFlag]:
    """The ``consequence_unchecked`` flag, or None (round-10 clearance c3, sp-t16 g1.22): the conclusion's label states a
    consequence or correction (after "so", "therefore", an arrow, "should read"), and some of its content stems (at least one,
    with at least two shared in all) are held only by the meaning of a declared symbol of the writer's own that no premise and
    no conclusion uses ('correction', "the verb should read 'veamos'"): the encoding declared the claim's point and dropped it,
    so the verdict is on what the expression checks, not on the consequence the label states."""
    if problem.conclusion is None:
        return None
    label = (problem.conclusion.label or "")[:MAX_CLAIM_CHARS]
    m = _CONSEQUENCE_CUE_RE.search(label)
    if m is None:
        return None
    consequence = _stems(label[m.start():])
    if len(consequence) < 2:
        return None
    used = _used(problem) | _names(_dump(problem.conclusion.expr))
    unused = [s for s in problem.symbols if s.name not in used and _symbol_kind(s) in _WRITER_KINDS]
    if not unused:
        return None
    encoded: set[str] = set()
    for pr in problem.premises:
        encoded |= _stems(pr.label)
    for s in problem.symbols:
        if s.name in used:
            encoded |= _stems(s.meaning)
    for s in unused:
        shared = _stems(s.meaning) & consequence
        if len(shared) >= 2 and shared - encoded:
            return _flag("consequence_unchecked",
                         f"(deterministic) the conclusion's label states a consequence ({truncate(label[m.start():], 120)!r}) that only the "
                         f"declared symbol {s.name!r} ({truncate(s.meaning or '', 100)!r}) holds, and no premise or conclusion uses that "
                         "symbol: the expression does not check the consequence the label states; encode the claim's own point",
                         ["the claim's consequence encoded", "the encoding as given (the consequence dropped)"])
    return None


#: Kinds of a premise that asserts content as the writer's own inference (no source behind it).
_INFERENTIAL_KINDS = frozenset({None, "specialist_inference", "assumption"})


def _bool_atom(node: dict, sorts: dict[str, str]) -> Optional[str]:
    """The Boolean symbol a conjunct is, or negates, or None."""
    if node.get("op") == "not" and isinstance(node.get("arg"), dict):
        node = node["arg"]
    if node.get("op") == "var" and sorts.get(node.get("name")) == "Bool":
        return node["name"]
    return None


def conjunct_asserted(problem: Problem, claim: ClaimRecord, supporting: Sequence[ClaimRecord]) -> Optional[AmbiguityFlag]:
    """The ``conjunct_asserted`` flag, or None (round-10 clearance c3, ess-t16 s7.1): the conclusion conjoins two or more parts,
    one of them a Boolean statement (or its negation) that only premises of the writer's own inference assert as written (no
    grounding, ``specialist_inference``, ``assumption``), and a supporting claim the claim cites (not an evidence line) states what
    that premise or its symbol says (at least two content stems in common): the encoding asserts the part the support should
    give, so that part of the conclusion is assumed, not derived."""
    if problem.query != "entailment" or problem.conclusion is None or not supporting:
        return None
    concl = _dump(problem.conclusion.expr)
    if concl.get("op") != "and" or len(concl.get("args") or []) < 2:
        return None
    sorts = {s.name: s.sort for s in problem.symbols}
    meanings = {s.name: s.meaning or "" for s in problem.symbols}
    support = [(c.claim_id, _stems(c.claim_text)) for c in list(supporting)[:MAX_REPORT_CLAIMS] if c.claim_role not in _EVIDENCE_ROLES]
    if not support:
        return None
    premises = [(pr, _dump(pr.expr)) for pr in problem.premises]
    for part in concl["args"]:
        name = _bool_atom(part, sorts)
        if name is None:
            continue
        key = json.dumps(part, sort_keys=True)
        rows = [pr for pr, e in premises if json.dumps(e, sort_keys=True) == key]
        if not rows or any((pr.grounding.kind if pr.grounding is not None else None) not in _INFERENTIAL_KINDS for pr in rows):
            continue
        said = _stems(meanings.get(name)) | {st for pr in rows for st in _stems(pr.label)}
        hit = next((cid for cid, st in support if len(st & said) >= 2), None)
        if hit is None:
            continue
        return _flag("conjunct_asserted",
                     f"(deterministic) part of the conclusion ({name!r}, {truncate(meanings.get(name) or '', 100)!r}) is asserted as written by "
                     f"the writer's own premise(s) {[pr.id for pr in rows][:4]}, while the supporting claim {hit!r} the claim cites states what "
                     "it rests on: that part is assumed, not derived; encode it from what the support states",
                     ["the part derived from the supporting claim", "the encoding as given (the part asserted)"])
    return None


def _reason_span(text: str) -> Optional[tuple[str, set[str], str]]:
    """``(reason clause text, its content stems, consequence clause text)`` of the first reason connective of the claim
    (quotations masked), read as :func:`_reason_clause` reads it, or None."""
    from .diag_argument import REASON_CONNECTIVES
    from .pipeline import _REASON_AFTER, _boundaries
    masked = _masked(text)
    spans = lexis.token_spans(masked)
    toks = tuple(t for _s, _e, t in spans)
    ends = _boundaries(masked)
    for i, cue in lexis.find_cues(toks, REASON_CONNECTIVES):
        if cue == ("because",) and i + 1 < len(toks) and toks[i + 1] == "of":
            continue
        at = spans[i][0]
        stop = next((e for e in ends if e > at), len(masked))
        start = max((e for e in ends if e < at), default=-1)
        before = [k for k in range(0, i) if spans[k][0] > start]
        after = [k for k in range(i + len(cue), len(spans)) if spans[k][0] < stop]
        reason, consequence = (after, before) if cue in _REASON_AFTER else (before, after)
        if not reason or not consequence:
            continue
        a, b = spans[reason[0]][0], spans[reason[-1]][1]
        c, d = spans[consequence[0]][0], spans[consequence[-1]][1]
        return masked[a:b], set(lexis.content_stems([toks[k] for k in reason])), masked[c:d]
    return None


#: A figure written in digits (a decimal point kept), as the consequence clause states it.
_DIGITS_RE = re.compile(r"\d{1,15}(?:\.\d{1,15})?")


def _closed(node: dict) -> bool:
    """Whether an IR expression dict mentions no symbol (a computation on numbers alone)."""
    return not _names(node)


def reason_not_encoded(problem: Problem, claim: ClaimRecord) -> Optional[AmbiguityFlag]:
    """The ``reason_not_encoded`` flag, or None (round-10 clearance c3, ph-t16 s2.8): the claim draws its consequence from a
    reason it states in words (no figure in the reason clause: "A gas-law ratio needs kelvin, so the ratio is 308/290, not
    35/17"), the encoding states nothing of that reason (fewer than two of its content stems in any premise label or any
    meaning of a symbol a premise uses), and the conclusion rests on figures alone (every symbol it mentions is numeric and a
    premise fixes it to a computation on numbers): the verdict checks the arithmetic of the figures and would hold whatever the
    reason, so the claim's inference is not checked."""
    if problem.query != "entailment" or problem.conclusion is None or not problem.premises:
        return None
    found = _reason_span(claim.claim_text or "")
    if found is None:
        return None
    reason_text, reason, consequence_text = found
    if len(reason) < 2 or any(ch.isdigit() for ch in reason_text):
        return None
    # the figures checked are the consequence's own ("the ratio is 308/290, not 35/17"): an encoding of the reason itself ("The
    # division is exact, so no extra packet is needed", checked as 6000000 mod 1500 = 0) checks the claim's reason, not this shape
    stated = {Fraction(x) for x in _DIGITS_RE.findall(consequence_text[:MAX_CLAIM_CHARS])}
    if not stated or not stated & {v for pr in problem.premises for _w, v in _literals(_dump(pr.expr))}:
        return None
    sorts = {s.name: s.sort for s in problem.symbols}
    concl_vars = _names(_dump(problem.conclusion.expr))
    if not concl_vars or any(sorts.get(v) not in ("Int", "Real") for v in concl_vars):
        return None
    fixed: set[str] = set()
    for pr in problem.premises:
        e = _dump(pr.expr)
        if e.get("op") != "eq":
            continue
        for var, rhs in ((e.get("left") or {}, e.get("right") or {}), (e.get("right") or {}, e.get("left") or {})):
            if var.get("op") == "var" and _closed(rhs):
                fixed.add(var["name"])
    if not concl_vars <= fixed:
        return None
    if any(len(st & reason) >= 2 for st in _encoded_stem_sets(problem)):
        return None
    return _flag("reason_not_encoded",
                 f"(deterministic) the claim draws its consequence from a reason it states ({truncate(reason_text, 120)!r}), and the encoding "
                 "states nothing of that reason: its conclusion rests on figures alone, so the verdict checks their arithmetic and would hold "
                 "whatever the reason; encode the claim's reason and the step it licenses",
                 ["the claim's reason and step encoded", "the encoding as given (the arithmetic of the figures alone)"])


def fidelity_flags(problem: Problem, claim: ClaimRecord, supporting: Sequence[ClaimRecord], report: Optional[SpecialistReport],
                   task: Optional[TaskRecord] = None) -> list[AmbiguityFlag]:
    """Every flag of :func:`neighbour_content`, :func:`dropped_qualifier`, :func:`reason_unconnected`,
    :func:`reported_conclusion`, :func:`stated_values_not_encoded` and, since round 10 (clearance c3),
    :func:`consequence_unchecked`, :func:`conjunct_asserted` and :func:`reason_not_encoded` that fires on the encoding (the pipeline
    adds :func:`unencoded_support` itself, since it asks the engine for the verdict first)."""
    out: list[AmbiguityFlag] = []
    for flag in (neighbour_content(problem, claim, supporting, report, task), dropped_qualifier(problem, claim), reason_unconnected(problem, claim),
                 reported_conclusion(problem, claim), stated_values_not_encoded(problem, claim), consequence_unchecked(problem, claim),
                 conjunct_asserted(problem, claim, supporting), reason_not_encoded(problem, claim)):
        if flag is not None:
            out.append(flag)
    return out
