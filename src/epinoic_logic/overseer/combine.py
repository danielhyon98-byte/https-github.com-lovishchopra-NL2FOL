"""Combining the assessed verdicts of several overseer agents on one task, without voting on facts.

:func:`combine_verdicts` takes the :class:`~epinoic_logic.overseer.validate.VerdictAssessment` of each agent's verdict
(each already validated against the journal and the signed results) and returns a :class:`CombinedAssessment`:

* **Only accepted verdicts are combined.** An assessment that failed the binding re-check (AGENT-005), or (when the
  intake is given) one whose envelope the intake did not accept, is listed with its reason and contributes no
  accusation. Every combined verdict was therefore produced under an accepted pack; verdicts under different accepted
  pack versions may be combined (a pack upgrade), and each agent's pack identity is recorded.
* **Union and grouping.** The union of the accusations of valid verdicts (unverifiable ones are listed apart: they
  resolve nowhere and are recorded against their agent as AGENT-002) is grouped by kind family (the ``KIND_CHECKS``
  code set: one family per kind) and overlapping identifier sets (the same identifier in the same list, transitively).
  An unresolved member whose named ``(report, claim)`` pairs (or, naming no claim, whose named transfers) the group's
  confirming findings do not cover is split off into its own group, so it reaches human review instead of riding on a
  confirmation about another claim or transfer (review round 2). A group's **support** is the number of distinct agents
  in it; its **outcome support** the number whose own accusation has the group's outcome (a dissenter or an unresolved
  member never backs a confirmation); the review queue orders by outcome support first.
* **No voting on facts.** A group's outcome is the outcome of its check: **confirmed** when any member was confirmed
  (the router acts on the confirming ``OVS-*`` finding; a dissenting agent never vetoes it); otherwise **unresolved**
  when any member was unresolved (the group joins the human review queue); otherwise **refuted** (every member was
  refuted, and AGENT-001 stands for every accusing agent). Support never upgrades an unresolved group, and silence
  (a transfer listed as reviewed without an accusation) is never evidence of a clean transfer.
* **Review queue**: unresolved groups ordered by outcome support, then support (descending), then the highest claimed severity, then the
  earliest sequence number. A reliability history keyed by ``(agent_id, pack name, pack version)`` may break ties; it
  never confirms or refutes anything, and an agent's figure under one pack version is never applied to its verdict
  under another.
* **Determinism.** Assessments are taken in ``agent_id`` order, accusations in ``(kind, sorted identifiers,
  accusation_id)`` order, and group ids are digests of their members, so the combined assessment is identical under
  any permutation of the verdicts. It carries no timestamp and no random id; the signed audit that carries it does.

:func:`combined_audit` emits the combination as a signed ``verdicts``-scope ``OverseerAudit``, whose state and transfer
states are the task audit's, unchanged: ``OVS-AGENT-*`` findings never change a clearance (decision 16).

Deviations from ``docs/OVERSEER_DESIGN.md`` section 10, listed as each stage requires:

* a group mixing confirmed, refuted and unresolved members is confirmed when any member is (each member keeps its own
  outcome and AGENT code), unresolved when none is confirmed and any is unresolved, refuted only when all are refuted;
* unverifiable accusations are not grouped (they name nothing the checks could run on);
* the reliability history is the last ordering key before the group id (after support, severity and sequence).
"""
from __future__ import annotations

from typing import Iterable, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ..integrity.contracts import IntegrityFinding
from ..ir.canonical import canonical_json, sha256_hex
from .contracts import OverseerAudit
from .keys import KeyRing
from .validate import AccusationAssessment, FindingRef, VerdictAssessment, build_verdicts_audit
from .verdicts import ID_FIELDS, KIND_CHECKS, PackIdentity

__all__ = ["combine_verdicts", "combined_audit", "CombinedAssessment", "AccusationGroup", "GroupMember", "AgentRecord", "GroupOutcome", "combined_digest"]

GroupOutcome = Literal["confirmed", "refuted", "unresolved"]
_SEVERITY_RANK = {"error": 0, "warning": 1}


class GroupMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    agent_id: str
    verdict_id: Optional[str] = None
    accusation_id: str
    kind: str
    outcome: str
    code: str
    claimed_severity: str
    refuted_by: Optional[str] = None
    first_seq: Optional[int] = None
    pack: Optional[PackIdentity] = None


class AccusationGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: str
    kind: str
    checks: list[str] = Field(default_factory=list)
    identifiers: dict[str, list[str]] = Field(default_factory=dict)
    members: list[GroupMember] = Field(default_factory=list)
    support: int
    #: The distinct agents whose own accusation has the group's outcome (a refuted or unresolved member never backs a
    #: confirmed group; review round 2). The review queue orders unresolved groups by it.
    outcome_support: int = 0
    outcome: GroupOutcome
    claimed_severity: str
    first_seq: Optional[int] = None
    confirming: list[FindingRef] = Field(default_factory=list)
    refuted_agents: list[str] = Field(default_factory=list)


class AgentRecord(BaseModel):
    """One agent's verdict in the combination, with the pack identity it was produced under."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    agent_id: str
    verdict_id: Optional[str] = None
    intake_message_id: Optional[str] = None
    pack: Optional[PackIdentity] = None
    lens: Optional[str] = None
    mode: Optional[str] = None
    valid: bool
    excluded_reason: Optional[str] = None
    transfers_reviewed: int = 0
    accusations: int = 0


class CombinedAssessment(BaseModel):
    """The combination of several agents' assessed verdicts on one task (deterministic: no timestamp, no random id)."""
    model_config = ConfigDict(extra="forbid")
    task_id: str
    channel_uid: str
    task_audit_ids: list[str] = Field(default_factory=list)
    superseding_audit_ids: list[str] = Field(default_factory=list)
    packs: list[PackIdentity] = Field(default_factory=list)
    agents: list[AgentRecord] = Field(default_factory=list)
    groups: list[AccusationGroup] = Field(default_factory=list)
    review_queue: list[str] = Field(default_factory=list)
    unverifiable: list[GroupMember] = Field(default_factory=list)
    findings: list[IntegrityFinding] = Field(default_factory=list)

    def group(self, group_id: str) -> Optional[AccusationGroup]:
        return next((g for g in self.groups if g.group_id == group_id), None)


def combined_digest(combined: CombinedAssessment) -> str:
    return sha256_hex(canonical_json(combined.model_dump(mode="json", exclude_none=True)))


def _typed_ids(ids: dict[str, list[str]], claim_reports: Optional[Mapping[str, list[str]]] = None) -> set[tuple[str, str]]:
    """The accusation's identifiers as ``(list, id)``; a claim id is qualified by the report(s) it resolved to (claim ids
    repeat across reports, so a bare claim id would group accusations about different transfers)."""
    out: set[tuple[str, str]] = set()
    for name in ID_FIELDS:
        for i in ids.get(name, []):
            reps = (claim_reports or {}).get(i) if name == "claim_ids" else None
            if reps:
                out.update((name, f"{r}\u001f{i}") for r in reps)
            else:
                out.add((name, i))
    return out


def _acc_ids(a: AccusationAssessment) -> set[tuple[str, str]]:
    return _typed_ids(a.identifiers, a.claim_report_ids)


def _acc_sort_key(agent_id: str, a: AccusationAssessment) -> tuple:
    return (a.kind, tuple(sorted(_acc_ids(a))), agent_id, a.accusation_id)


def _member(agent: VerdictAssessment, a: AccusationAssessment) -> GroupMember:
    return GroupMember(agent_id=agent.agent_id, verdict_id=agent.verdict_id, accusation_id=a.accusation_id, kind=a.kind, outcome=a.outcome, code=a.code,
                       claimed_severity=a.claimed_severity, refuted_by=a.refuted_by, first_seq=a.first_seq, pack=agent.pack)


def _excluded(a: VerdictAssessment, intake) -> Optional[str]:
    if not a.valid:
        return f"invalid verdict ({a.invalid_reason})"
    if intake is not None:
        acc = intake.accepted(a.intake_message_id) if a.intake_message_id else None
        if acc is None or acc.verdict.verdict_id != a.verdict_id or acc.verdict.pack != a.pack or acc.issue.agent_id != a.agent_id:
            return "not a verdict this intake accepted"
    return None


def _content_key(a: VerdictAssessment) -> str:
    """A digest of what an assessment decided (not its id or time), so duplicates are chosen deterministically."""
    return sha256_hex(canonical_json(a.model_dump(mode="json", include={"accusations", "engine_statements", "findings"}, exclude_none=True)))


def _finding_key(f: IntegrityFinding) -> tuple:
    return (tuple(f.agent_ids), f.code, tuple(f.message_ids), tuple(f.claim_ids), tuple(f.report_ids), f.formal_result_id or "", f.message)


def combine_verdicts(assessments: Sequence[VerdictAssessment], *, intake=None,
                     reliability: Optional[Mapping[tuple[str, str, str], float]] = None) -> CombinedAssessment:
    """Combine the assessments of one task (see the module docstring). Raises ``ValueError`` when the assessments
    belong to different tasks or channels."""
    items = list(assessments)
    if not items:
        raise ValueError("nothing to combine")
    tasks = {(a.task_id, a.channel_uid) for a in items}
    if len(tasks) != 1:
        raise ValueError("verdicts of different tasks or channels are never combined")
    task_id, channel_uid = next(iter(tasks))
    # one assessment per verdict envelope; deterministic order
    unique: dict[tuple, VerdictAssessment] = {}
    for a in sorted(items, key=lambda x: (x.agent_id, x.verdict_id or "", x.intake_message_id or "", x.valid, _content_key(x))):
        unique.setdefault((a.agent_id, a.verdict_id, a.intake_message_id, a.valid, a.invalid_reason), a)
    ordered = list(unique.values())
    agents: list[AgentRecord] = []
    valid: list[VerdictAssessment] = []
    for a in ordered:
        why = _excluded(a, intake)
        agents.append(AgentRecord(agent_id=a.agent_id, verdict_id=a.verdict_id, intake_message_id=a.intake_message_id, pack=a.pack, lens=a.lens, mode=a.mode,
                                  valid=why is None, excluded_reason=why, transfers_reviewed=len(a.transfers_reviewed), accusations=len(a.accusations)))
        if why is None:
            valid.append(a)
    # accusations: unverifiable apart, the rest grouped per kind by overlapping identifiers
    unverifiable: list[GroupMember] = []
    pool: list[tuple[VerdictAssessment, AccusationAssessment]] = []
    for a in valid:
        for acc in a.accusations:
            if acc.outcome == "unverifiable":
                unverifiable.append(_member(a, acc))
            else:
                pool.append((a, acc))
    pool.sort(key=lambda p: _acc_sort_key(p[0].agent_id, p[1]))
    unverifiable.sort(key=lambda m: (m.kind, m.agent_id, m.accusation_id))
    groups: list[AccusationGroup] = []
    by_kind: dict[str, list[tuple[VerdictAssessment, AccusationAssessment]]] = {}
    for p in pool:
        by_kind.setdefault(p[1].kind, []).append(p)
    for kind in sorted(by_kind):
        members = by_kind[kind]
        parent = list(range(len(members)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        owner: dict[tuple[str, str], int] = {}
        for i, (_a, acc) in enumerate(members):
            for key in sorted(_acc_ids(acc)):
                if key in owner:
                    ri, rj = find(owner[key]), find(i)
                    if ri != rj:
                        parent[max(ri, rj)] = min(ri, rj)
                else:
                    owner[key] = i
        clusters: dict[int, list[int]] = {}
        for i in range(len(members)):
            clusters.setdefault(find(i), []).append(i)
        for idx in clusters.values():
            for part in _split_uncovered([members[i] for i in idx]):
                groups.append(_group(kind, part, reliability))
    groups.sort(key=lambda g: (g.kind, g.group_id))
    rel = reliability or {}

    def queue_key(g: AccusationGroup) -> tuple:
        best = max((rel.get((m.agent_id, m.pack.name, m.pack.version), 0.0) for m in g.members if m.pack is not None), default=0.0)
        return (-g.outcome_support, -g.support, _SEVERITY_RANK.get(g.claimed_severity, 2), g.first_seq if g.first_seq is not None else 1 << 30, -best, g.group_id)

    queue = [g.group_id for g in sorted((g for g in groups if g.outcome == "unresolved"), key=queue_key)]
    findings: dict[tuple, IntegrityFinding] = {}
    for a in ordered:
        for f in a.findings:
            findings.setdefault(_finding_key(f), f)
    packs = sorted({a.pack for a in valid if a.pack is not None}, key=lambda p: p.key())
    return CombinedAssessment(task_id=task_id, channel_uid=channel_uid, task_audit_ids=sorted({a.task_audit_id for a in ordered if a.task_audit_id}),
                              superseding_audit_ids=sorted({a.superseding_audit_id for a in ordered if a.superseding_audit_id}), packs=packs,
                              agents=agents, groups=groups, review_queue=queue, unverifiable=unverifiable,
                              findings=[findings[k] for k in sorted(findings)])


def _covered_by(acc: AccusationAssessment, refs: list[FindingRef]) -> bool:
    """Whether the confirming findings ``refs`` cover what ``acc`` names: every named (report, claim) pair, every named
    message, and every named report, result and document (a member about another claim, transfer, report, result or
    document is not covered by a confirmation of this one; review round 3: an accusation naming only a report is not
    covered vacuously)."""
    pairs = {(r, c) for f in refs for r in (f.report_ids or [""]) for c in f.claim_ids}
    claims = {c for _r, c in pairs}
    msgs = {m for f in refs for m in f.message_ids}
    reports = {r for f in refs for r in f.report_ids}
    results = {x for f in refs for x in ([f.formal_result_id] if f.formal_result_id else []) + list(f.related_result_ids)}
    docs = {d for f in refs for d in f.document_ids}
    for c in acc.identifiers.get("claim_ids", []):
        reps = acc.claim_report_ids.get(c) or [""]
        if not any((r, c) in pairs or ("", c) in pairs or (r == "" and c in claims) for r in reps):
            return False
    if not acc.identifiers.get("claim_ids") and any(m not in msgs for m in acc.identifiers.get("message_ids", [])):
        return False
    claim_reports = {r for c in acc.identifiers.get("claim_ids", []) for r in (acc.claim_report_ids.get(c) or [])}
    if any(r not in reports and r not in claim_reports for r in acc.identifiers.get("report_ids", [])):
        return False
    if any(x not in results for x in acc.identifiers.get("result_ids", [])):
        return False
    if any(d not in docs for d in acc.identifiers.get("document_ids", [])):
        return False
    return True


def _split_uncovered(members: list[tuple[VerdictAssessment, AccusationAssessment]]) -> list[list[tuple[VerdictAssessment, AccusationAssessment]]]:
    """An unresolved member of a group that another member's confirmation decides is kept in the group only when the
    group's confirming findings cover what it names; otherwise it is split off into its own group, so it reaches human
    review instead of riding on a confirmation about another claim or transfer."""
    refs = [r for _a, acc in members if acc.outcome == "confirmed" for r in acc.confirming]
    if not refs:
        return [members]
    keep, apart = [], []
    for m in members:
        (apart if m[1].outcome == "unresolved" and not _covered_by(m[1], refs) else keep).append(m)
    return [keep] + [[m] for m in apart] if apart else [members]


def _group(kind: str, members: list[tuple[VerdictAssessment, AccusationAssessment]], reliability) -> AccusationGroup:
    mem = sorted((_member(a, acc) for a, acc in members), key=lambda m: (m.agent_id, m.accusation_id))
    ids: dict[str, set[str]] = {name: set() for name in ID_FIELDS}
    for _a, acc in members:
        for name in ID_FIELDS:
            ids[name].update(acc.identifiers.get(name, []))
    outcomes = {acc.outcome for _a, acc in members}
    outcome: GroupOutcome = "confirmed" if "confirmed" in outcomes else ("unresolved" if "unresolved" in outcomes else "refuted")
    confirming: dict[tuple, FindingRef] = {}
    for _a, acc in members:
        if acc.outcome == "confirmed":
            for r in acc.confirming:
                confirming.setdefault((r.audit_id or "", r.index, r.code), r)
    seqs = [m.first_seq for m in mem if m.first_seq is not None]
    gid = "grp-" + sha256_hex(canonical_json([kind, [[m.agent_id, m.verdict_id or "", m.accusation_id] for m in mem]]))[:16]
    severity = min((m.claimed_severity for m in mem), key=lambda s: _SEVERITY_RANK.get(s, 2))
    return AccusationGroup(group_id=gid, kind=kind, checks=list(KIND_CHECKS.get(kind, ())), identifiers={k: sorted(v) for k, v in ids.items() if v},
                           members=mem, support=len({m.agent_id for m in mem}), outcome_support=len({m.agent_id for m in mem if m.outcome == outcome}),
                           outcome=outcome, claimed_severity=severity,
                           first_seq=min(seqs) if seqs else None, confirming=[confirming[k] for k in sorted(confirming)],
                           refuted_agents=sorted({m.agent_id for m in mem if m.outcome == "refuted"}))


def combined_audit(combined: CombinedAssessment, *, task_audit: Optional[OverseerAudit], keyring: KeyRing,
                   assessments: Iterable[VerdictAssessment] = ()) -> OverseerAudit:
    """The combination as a signed ``verdicts``-scope audit referencing the task audit; agent findings never change a
    clearance, so the state and transfer states are the task audit's."""
    notes = []
    if task_audit is not None:
        notes.append(f"references task audit {task_audit.audit_id}")
    for sid in combined.superseding_audit_ids:
        notes.append(f"targeted re-runs issued task audit {sid}")
    for r in combined.agents:
        pk = f"{r.pack.name} {r.pack.version} {r.pack.sha256}" if r.pack is not None else "none"
        vref = ("sha256:" + sha256_hex(r.verdict_id)[:12]) if r.verdict_id else "none"  # agent-chosen: shown as a digest
        notes.append(f"agent {r.agent_id} verdict {vref} (intake message {r.intake_message_id}) under pack {pk}: "
                     f"{'combined' if r.valid else 'excluded (' + str(r.excluded_reason) + ')'}")
    notes.append(f"combined assessment sha256 {combined_digest(combined)}")
    notes.append(f"groups {len(combined.groups)}; human review queue {len(combined.review_queue)}; no voting on facts")
    message_ids = list(task_audit.message_ids) if task_audit is not None else []
    return build_verdicts_audit(reference=task_audit, channel_uid=combined.channel_uid, task_id=combined.task_id,
                                request_id=task_audit.request_id if task_audit is not None else "", findings=list(combined.findings), keyring=keyring,
                                message_ids=message_ids, notes=notes)
