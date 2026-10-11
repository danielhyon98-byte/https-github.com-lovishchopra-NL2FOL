"""B4 rule divergence: does the Overseer's own integrity report raise a rule that no receipt of the task carries?

``run_integrity_checks`` runs over the JOURNALED inputs:

* the plan, with every agent that sent a synthesis and no report removed from ``selected_agent_ids``,
  ``agent_subjects`` and ``agent_task_types`` (so the combinator never yields a false INT-HANDOFF-007);
* the delivered reports (first delivery per report id, in delivery order), the last delivered synthesis, and the final
  pool (problems resolved from the journaled outcomes);
* as ``prior_results``, the outcome verifications issued under the channel's solver configuration whose signature
  verified at L3 and whose problem is the claim's final pooled problem (the others are L3's);
* ``config`` the channel's configuration (from the journaled event), ``synthesized_conclusions`` from the synthesis
  claims' ``formal_conclusion``;
* ``signing_key=None``: the auditor never hands an engine key to code that signs (TR5). Its engine runs are captured
  and signed under the auditor's run key instead.

Excluded from the diff:

* the INT-LEDGER, INT-CONFLICT and INT-GLOSSARY families, which B2 and B3 decide on the channel's own scope (one fault
  gives one ``OVS-*`` finding);
* INT-SYNTH-006 for a synthesized claim whose receipt shows the entailment check was performed (INT-LEDGER-011
  carrying a ``formal_result_id``);
* INT-STALE-006 ("no verification key configured"): a consequence of ``signing_key=None``; the signatures of those
  results are verified by L3 (RES-003), never skipped;
* INT-HANDOFF-007 when the task has no delivered synthesis: "a selected agent delivered no report, any synthesis is
  incomplete" has nothing to diverge from before a synthesis exists (deviation from the design text, which names the
  combinator case only);
* INT-INTERNAL-001 is not a rule: it becomes AUDIT-001.

Each remaining ``(code, claim set)`` no receipt of the task carries is classified: ``time_dependent`` (timestamps from
a harness clock: INT-HANDOFF-005/016/017; owner the harness), ``rule_ownership`` (the rule lives in the integrity
package only: INT-SYNTH-004/005/006, INT-HANDOFF-007/008/009 report-set rules, INT-STALE-*, INT-HANDOFF-004 for a
synthesized claim; owner the integrity package) or ``transmission_fault`` (anything else; owner the channel). An
error-level divergence is DIV-001 whatever its classification; a warning or info is DIV-002.
"""
from __future__ import annotations

from typing import Optional

from ...engine.provenance import config_digest
from ...integrity import run_integrity_checks
from ...integrity.contracts import IntegrityFinding
from ...ir.canonical import canonical_json, problem_digest, sha256_hex
from ..contracts import Divergence
from ..view import REPORT_KINDS
from . import CheckContext

__all__ = ["check_divergence", "classify", "EXCLUDED_FAMILIES", "TIME_DEPENDENT", "RULE_OWNERSHIP"]

EXCLUDED_FAMILIES = ("INT-LEDGER", "INT-CONFLICT", "INT-GLOSSARY")
TIME_DEPENDENT = frozenset({"INT-HANDOFF-005", "INT-HANDOFF-016", "INT-HANDOFF-017"})
RULE_OWNERSHIP = frozenset({"INT-SYNTH-004", "INT-SYNTH-005", "INT-SYNTH-006", "INT-HANDOFF-007", "INT-HANDOFF-008", "INT-HANDOFF-009"})


def classify(f: IntegrityFinding, synthesized_ids: set[str]) -> tuple[str, str]:
    if f.code in TIME_DEPENDENT:
        return "time_dependent", "harness"
    if f.code in RULE_OWNERSHIP or f.code.startswith("INT-STALE") or (f.code == "INT-HANDOFF-004" and set(f.claim_ids) & synthesized_ids):
        return "rule_ownership", "integrity"
    return "transmission_fault", "channel"


def check_divergence(ctx: CheckContext) -> list[Divergence]:
    view = ctx.view
    if view.degraded or not view.transfers:
        return []
    last = view.transfers[-1]
    plan = view.plan_at(last.seq)
    if plan is None:
        return []
    transmitted = view.transmitted_before(last.seq + 1)
    reports = [tr.report for tr in transmitted.values()]
    syntheses = [t for t in view.transfers if t.kind == "relay_synthesis" and t.delivered and t.synthesis is not None]
    syn_t = syntheses[-1] if syntheses else None
    synthesis = syn_t.synthesis if syn_t is not None else None
    reporters = {r.agent_id for r in reports}
    combinators = {t.synthesis.combinator_agent_id for t in syntheses} - reporters
    selected = [a for a in plan.selected_agent_ids if a not in combinators] or list(plan.selected_agent_ids)
    plan_in = plan.model_copy(update={"selected_agent_ids": selected, "plan_sha256": None,
                                      "agent_subjects": {k: v for k, v in plan.agent_subjects.items() if k in selected},
                                      "agent_task_types": {k: v for k, v in plan.agent_task_types.items() if k in selected}})
    cfg = view.config_at(last.seq)
    formalized = {}
    for p in last.pool_after:
        prob = view.outcome_problem(p.claim_id, p.problem_digest, last.seq)
        if prob is not None:
            formalized[p.claim_id] = prob
    prior = {}
    cfg_dig = config_digest(cfg)
    for t in view.transfers:
        if t.receipt is None:
            continue
        for o in t.receipt.outcomes:
            v = o.verification
            cur = formalized.get(o.claim_id)
            if v is None or cur is None or v.binding.config_digest != cfg_dig or v.binding.problem_digest != problem_digest(cur):
                continue
            ok, _ = ctx.keyring.verify_result(v)
            if ok:
                prior[o.claim_id] = v
    concl = {sc.claim_id: sc.formal_conclusion for sc in synthesis.claims if sc.formal_conclusion is not None} if synthesis is not None else {}
    memo_key = "B4|" + sha256_hex(canonical_json([plan_in.model_dump(mode="json", exclude_none=True), [r.model_dump(mode="json", exclude_none=True) for r in reports],
                                                  synthesis.model_dump(mode="json", exclude_none=True) if synthesis is not None else None,
                                                  sorted((k, problem_digest(p)) for k, p in formalized.items()), sorted((k, v.result_id) for k, v in prior.items()),
                                                  cfg.model_dump(mode="json")]))
    memo = ctx.store.memo_get(memo_key)
    if memo is None:
        def run():
            return run_integrity_checks(plan_in, reports, synthesis, formalized=formalized or None, synthesized_conclusions=concl or None,
                                        prior_results=prior or None, signing_key=None, config=cfg)
        report, run_ids = ctx.auditor_run(run, seq=last.seq)
        memo = ([f.model_dump(mode="json") for f in report.findings], run_ids)
        ctx.store.memo_put(memo_key, memo)
    else:
        for rid in memo[1]:
            if rid not in ctx.auditor_result_ids:
                ctx.auditor_result_ids.append(rid)
    found = [IntegrityFinding.model_validate(d) for d in memo[0]]
    carried: set[tuple[str, frozenset[str]]] = set()
    for t in view.transfers:
        if t.receipt is not None:
            carried.update((f.code, frozenset(f.claim_ids)) for f in t.receipt.findings)
    performed = set()
    if syn_t is not None and syn_t.receipt is not None:
        performed = {f.claim_ids[0] for f in syn_t.receipt.findings if f.code == "INT-LEDGER-011" and f.formal_result_id and f.claim_ids}
    synthesized_ids = {c.claim_id for c in synthesis.claims} | {synthesis.synthesis_id} if synthesis is not None else set()
    out: list[Divergence] = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for f in found:
        if f.code == "INT-INTERNAL-001":
            ctx.ovs(last.seq, "OVS-AUDIT-001", f"the integrity re-run of B4 failed internally: {f.message[:300]}", claim_ids=f.claim_ids)
            continue
        if f.code.startswith(EXCLUDED_FAMILIES) or f.code == "INT-STALE-006":
            continue
        if f.code == "INT-SYNTH-006" and f.claim_ids and f.claim_ids[0] in performed:
            continue
        if f.code == "INT-HANDOFF-007" and synthesis is None:
            continue
        key = (f.code, frozenset(f.claim_ids))
        if key in carried or key in seen:
            continue
        seen.add(key)
        classification, owner = classify(f, synthesized_ids)
        d = Divergence(int_code=f.code, severity=f.severity, classification=classification, owner=owner, claim_ids=list(f.claim_ids), message=f.message[:2000])
        out.append(d)
        mids = [syn_t.message_id] if syn_t is not None and syn_t.message_id else []
        m2, rids, aids = ctx.message_ids_for_claims(f.claim_ids)
        code = "OVS-DIV-001" if f.severity == "error" else "OVS-DIV-002"
        ctx.ovs(syn_t.seq if syn_t is not None else last.seq, code,
                f"{f.code} ({f.severity}) fires in the Overseer's integrity report but on no receipt of the task; classification {classification}, owner {owner}: {f.message[:400]}",
                claim_ids=f.claim_ids, message_ids=mids + m2, report_ids=list(f.report_ids) + rids, agent_ids=list(f.agent_ids) + aids, document_ids=f.document_ids,
                formal_result_id=f.formal_result_id, related_result_ids=f.related_result_ids)
    return out
