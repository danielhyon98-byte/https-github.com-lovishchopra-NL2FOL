# integrity — communication between agents

Hallucination also enters between agents. This package checks the hand-offs:

| Check | Fault it exposes | Finding codes | Method |
| --- | --- | --- | --- |
| Envelope (`envelope.py`) | replayed, tampered or mis-threaded messages; replies that cross request/task boundaries | INT-ENV-001…005 | deterministic (content hash, message log) |
| Handoff (`handoff.py`) | a specialist answering the wrong task, an agent the router never selected, off-subject reports, citations outside the retrieval scope, late reports, self-reported status | INT-HANDOFF-001…006 | deterministic |
| Staleness (`handoff.py`) | a verification result reused for a changed representation; unsigned or forged results | INT-STALE-001…004 | digest and signature comparison |
| Ledger (`ledger.py`) | material claims dropped without record, synthesized claims with no source, certainty inflated above the weakest source, evidence references lost, 'carried' claims whose text changed, conflicts "resolved" without a basis | INT-LEDGER-000…011, INT-CONFLICT-003 | deterministic accounting |
| Cross-report consistency (`cross_check.py`) | specialists contradicting each other under a shared glossary; contradictions not disclosed in the synthesis | INT-CONFLICT-001/002/004, INT-GLOSSARY-001…004 | Z3 joint consistency with the conflicting claims named from the unsat core |
| Synthesis entailment (`cross_check.py`) | the combinator stating more than the sources support (counterexample), or a synthesis that follows only through unverified inferences | INT-SYNTH-001…005 | Z3 entailment of the synthesized conclusion from the union of source premises |

`run_integrity_checks(plan, reports, synthesis, formalized, synthesized_conclusions,
prior_results, signing_key)` runs everything applicable and returns one
`IntegrityReport` for the Overseer. Formal findings carry the `result_id` of the
signed engine result that established them. Shared-glossary requirement: symbols
with the same name across claims denote the same thing; a sort clash is reported
and the joint check is withheld.
