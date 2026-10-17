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


def gloss_content(meaning: Optional[str]) -> frozenset[str]:
    """The content of a symbol's gloss: its words (light-stemmed, case-folded), figures (thousands separators removed)
    and part labels ("(a)", "part c", "(ii)"), without the words that never change the quantity named
    (:data:`_GLOSS_STOP`), in any order. 'pig iron output in 1928 (million tonnes, about 3.3)' and 'pig iron output in
    1928 (about 3.3 million tonnes)' have the same content, as do 'route mileage in 1870' and 'route mileage by 1870';
    'marks allocated to part (a)' and 'marks allocated to part (c)' do not."""
    from .ledger import light_stem
    out: set[str] = set()
    text = (meaning or "").casefold()
    for m in _PART_LABEL_RE.finditer(text):
        out.add(f"({m.group('p') or m.group('q')})")
    text = _PART_LABEL_RE.sub(" part ", text)
    for tok in _GLOSS_TOKEN_RE.findall(text):
        if tok[:1].isdecimal():
            out.add(re.sub(r"(?<=\d),(?=\d{3}\b)", "", tok))
        elif tok not in _GLOSS_STOP:
            out.add(light_stem(tok))
    return frozenset(out)


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
                ca, cb = gloss_content(prior_sym.meaning), gloss_content(s.meaning)
                if a and b and a != b and ca != cb:  # the same words and figures in another order or with another "in"/"by" are one meaning
                    only_a, only_b = sorted(ca - cb), sorted(cb - ca)
                    what = "; ".join(x for x in (f"only the first states {only_a}" if only_a else "", f"only the second states {only_b}" if only_b else "") if x)
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

    * a symbol whose gloss content (:func:`gloss_content`) differs between two claims ('the target is 67' in one claim,
      'the target is 20' in another; 'marks allocated to part (a)' and '... part (c)');
    * and, between two claims that so gloss a shared symbol differently, every other shared symbol that either claim
      computes together with it (connected to it through its own assertions: 'low on pass 1' of a search for the target
      67 is not 'low on pass 1' of a search for 20, whatever the glosses say).

    Claims that do not so differ keep one name: the first group of claims keeps the original name, each other group gets
    ``<name>_g<k>``. Two claims that gloss a symbol alike and never gloss a shared symbol differently still share all
    their symbols, so their contradictions are found as before. Returns the problems (unchanged when nothing differs)
    and, per original name that was split, ``(name used, claim ids, gloss)`` for each group."""
    n = len(problems)
    content: list[dict[str, Optional[frozenset[str]]]] = []
    shown: list[dict[str, str]] = []
    comps = [_symbol_components(p) for p in problems]
    sorts: dict[str, set[str]] = {}
    holders: dict[str, list[int]] = {}
    for i, p in enumerate(problems):
        content.append({})
        shown.append({})
        for sym in p.symbols:
            sorts.setdefault(sym.name, set()).add(sym.sort)
            holders.setdefault(sym.name, []).append(i)
            content[i][sym.name] = gloss_content(sym.meaning) if _norm_meaning(sym.meaning) else None
            shown[i][sym.name] = sym.meaning or ""
    # clash[(i, j)]: the shared symbols claims i and j gloss with different content (same sort; a sort clash withholds the check)
    clash: dict[tuple[int, int], set[str]] = {}
    for name, idxs in holders.items():
        if len(idxs) < 2 or len(sorts[name]) > 1:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                ci, cj = content[i][name], content[j][name]
                if ci is not None and cj is not None and ci != cj:
                    clash.setdefault((i, j), set()).add(name)
    if not clash:
        return list(problems), {}

    def apart(i: int, j: int, name: str) -> bool:
        i, j = min(i, j), max(i, j)
        ci, cj = content[i][name], content[j][name]
        if ci is not None and cj is not None and ci != cj:
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
    return verify(joint, cfg, limits, signing_key=signing_key, key_id="integrity"), jmap


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
    joint, findings, jmap = joint_problem(apart, request_id=request_id, joint_id="cross-report")
    if splits:  # the glossary findings are those of the claims as translated, each saying the symbol was read apart
        _syms, glossary = _merge_symbols(problems, read_apart=True)
        findings = [f for f in glossary if f.code == "INT-GLOSSARY-005"] + [f for f in findings if f.code != "INT-GLOSSARY-005"]
    if joint is None:
        return None, findings
    cfg = config.model_copy(update={"produce_unsat_core": True})
    result = verify(joint, cfg, limits, signing_key=signing_key, key_id="integrity")
    if result.status is S.INCONSISTENT_PREMISES:
        findings += _attribute_contradiction(apart, result, jmap, request_id=request_id, cfg=cfg, limits=limits, signing_key=signing_key, synthesized_claim_id=None, assumed_readings=frozenset(assumed_readings))
    elif result.status is not S.CONSISTENT:
        findings += _classify_failure(result, jmap, synthesized_claim_id=None, undecided_code="INT-CONFLICT-004")
    elif splits:
        findings += _glossary_only_contradiction(problems, splits, result, request_id=request_id, cfg=cfg, limits=limits, signing_key=signing_key)
    return result, findings


def _glossary_only_contradiction(problems: list[Problem], splits: dict[str, list[tuple[str, list[str], str]]], apart_result: VerificationResult, *,
                                 request_id: str, cfg: SolverConfig, limits: Limits, signing_key: Optional[bytes]) -> list[IntegrityFinding]:
    """INT-CONFLICT-004 (warning) when the claims contradict each other only if a symbol they gloss as different
    quantities is read as one: the pool is consistent with the glosses read apart and inconsistent with them pooled. The
    finding names the claims of the pooled core and the symbols with their glosses; no INT-CONFLICT-001 is charged and no
    disclosure is demanded (only INT-CONFLICT-001 enters the disclosure rule)."""
    joint, _f, jmap = joint_problem(problems, request_id=request_id, joint_id="cross-report-pooled")
    if joint is None:
        return []
    pooled = verify(joint, cfg, limits, signing_key=signing_key, key_id="integrity")
    if pooled.status is not S.INCONSISTENT_PREMISES:
        return []
    claims = claim_ids_from_core(pooled.premises_relied_on, jmap) or sorted(set(jmap.claim_ids))
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
    return [IntegrityFinding(code="INT-CONFLICT-004", severity="warning",
                             message=f"the pooled claims {claims} contradict each other only when symbol(s) {', '.join(clashing[:6])}, glossed as different quantities{tail} are read as one quantity; read apart they are consistent, so the contradiction is unattributable and no contradiction is charged to the specialists (one symbol name for two quantities is a translation fault)",
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
    result = verify(joint, cfg, limits, signing_key=signing_key, key_id="integrity")
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
    return verify(prob, cfg, limits, signing_key=signing_key, key_id="integrity")


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
    grounded_only = verify(joint.model_copy(update={"premises": [a for a in joint.premises if a.id not in ungrounded_all]}), cfg, limits, signing_key=signing_key, key_id="integrity")
    if grounded_only.status is S.ENTAILED:
        return []  # the claim follows from grounded premises alone; the ungrounded proof was incidental
    related = [grounded_only.result_id]
    pooled_all = {i for i in ungrounded_all if i in jmap.assertions and jmap.assertions[i][2]}
    if pooled_all:
        no_pooled = verify(joint.model_copy(update={"premises": [a for a in joint.premises if a.id not in pooled_all]}), cfg, limits, signing_key=signing_key, key_id="integrity")
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
    result = verify(prob, config.model_copy(update={"produce_unsat_core": True}), limits, signing_key=signing_key, key_id="integrity")
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
