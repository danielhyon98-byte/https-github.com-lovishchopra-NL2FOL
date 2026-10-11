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

from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import is_ungrounded, verify
from ..engine.statuses import VerificationStatus as S
from ..ir.canonical import problem_digest, sha256_hex
from ..ir.schema import ASSERTION_ID_RE, Assertion, Grounding, Limits, Problem, Symbol
from .contracts import IntegrityFinding, Synthesis

SEP = "::"
# Joint problems union many claims; the per-claim shape limits would make cross-agent
# checks silently stop working at scale, so they get their own, larger bounds.
JOINT_LIMITS = Limits(max_symbols=1024, max_premises=4096, max_nodes=200_000, max_depth=40, max_nary_args=64)
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


def _merge_symbols(problems: list[Problem]) -> tuple[list[Symbol], list[IntegrityFinding]]:
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
                if a and b and a != b:
                    findings.append(IntegrityFinding(code="INT-GLOSSARY-005", severity="warning", message=f"symbol {s.name!r} ({s.sort}) is glossed differently across claims: {prior_sym.meaning!r} in {prior_claim!r} vs {s.meaning!r} in {p.claim_id!r}; the joint check assumes they denote the same quantity", claim_ids=sorted({prior_claim, p.claim_id})))
            if not prior_sym.meaning and s.meaning:
                seen[s.name] = (s, p.claim_id)
    return [v[0] for v in seen.values()], findings


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


def _contradiction_findings(result: VerificationResult, jmap: JointMap, *, synthesized_claim_id: Optional[str]) -> list[IntegrityFinding]:
    claims = claim_ids_from_core(result.premises_relied_on, jmap)
    prefix = [synthesized_claim_id] if synthesized_claim_id else []
    where = "behind this synthesis " if synthesized_claim_id else ""
    if not claims:
        return [IntegrityFinding(code="INT-CONFLICT-004", severity="warning", message=f"the pooled claims {where}are contradictory but the conflicting set could not be attributed (no unsat core); all pooled claims are listed", claim_ids=prefix + sorted(set(jmap.claim_ids)), formal_result_id=result.result_id, deterministic=False)]
    if len(claims) == 1:
        orig = sorted({jmap.assertions[i][1] + (" (conclusion)" if jmap.assertions[i][2] else "") for i in result.premises_relied_on if i in jmap.assertions})
        return [IntegrityFinding(code="INT-CONFLICT-005", severity="error", message=f"specialist claim {claims[0]!r} is internally inconsistent: its own assertions {orig} refute each other (no other claim is involved)", claim_ids=prefix + claims, formal_result_id=result.result_id, deterministic=False)]
    return [IntegrityFinding(code="INT-CONFLICT-001", severity="error", message=f"specialist claims {where}contradict each other under the shared glossary; conflicting claims: {claims}", claim_ids=prefix + claims, formal_result_id=result.result_id, deterministic=False)]


def check_cross_report_consistency(problems: list[Problem], *, request_id: str, config: SolverConfig = SolverConfig(), signing_key: Optional[bytes] = None, limits: Limits = JOINT_LIMITS) -> tuple[Optional[VerificationResult], list[IntegrityFinding]]:
    """Are all specialists' formalized claims jointly consistent? Names the conflict.

    The unsat core is always requested, whatever the caller's configuration says,
    because a contradiction without the conflicting claim ids is not actionable."""
    joint, findings, jmap = joint_problem(problems, request_id=request_id, joint_id="cross-report")
    if joint is None:
        return None, findings
    cfg = config.model_copy(update={"produce_unsat_core": True})
    result = verify(joint, cfg, limits, signing_key=signing_key, key_id="integrity")
    if result.status is S.INCONSISTENT_PREMISES:
        findings += _contradiction_findings(result, jmap, synthesized_claim_id=None)
    elif result.status is not S.CONSISTENT:
        findings += _classify_failure(result, jmap, synthesized_claim_id=None, undecided_code="INT-CONFLICT-004")
    return result, findings


def _proven_elsewhere(claim_id: str, source_problems: list[Problem], prior_results: Optional[dict[str, VerificationResult]]) -> bool:
    if not prior_results:
        return False
    res = prior_results.get(claim_id)
    if res is None or res.status is not S.ENTAILED:
        return False
    src = next((p for p in source_problems if p.claim_id == claim_id), None)
    return src is not None and res.binding.problem_digest == problem_digest(src) and res.claim_id == claim_id


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
        findings += _contradiction_findings(result, jmap, synthesized_claim_id=synthesized_claim_id)
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
    pooled_claims = [c for c in jmap.claim_ids_of(pooled_ids) if not _proven_elsewhere(c, source_problems, prior_results)]
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
