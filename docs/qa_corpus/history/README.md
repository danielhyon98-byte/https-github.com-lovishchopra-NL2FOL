# History specialist QA corpus

Provenance: `ib-specialist-knowledge-docs-3.0/history/examples.md`, section 4, Example 1 (Paper 2 essay, status [S]).
The pack itself notes that the essay's dates and figures are from memory and must be verified; the corpus
tests whether the program makes that visible, not whether the figures are historically accurate.

| File | Content |
| --- | --- |
| example_1.json | question, full model essay (5 paragraphs, ~1129 words), extracted figures and dates |
| mutations/*.json | body paragraph 1 with one injected fault each |

| Mutation | Expected detection |
| --- | --- |
| certainty_inflation | certainty label mismatch; if synthesized, INT-LEDGER-003 |
| chronology_error | chronology constraint violated: 'came only after' with November 1931 < July 1932 -> COUNTEREXAMPLE on the ordering claim |
| contradictory_figures | INCONSISTENT_PREMISES naming both evidence claims when both are formalized as established facts |
| inflated_figure | quantitative inconsistency with other agents/paragraphs citing six million; if formalized against a library figure, COUNTEREXAMPLE/INCONSISTENT |
| invented_historian | source-integrity finding: named attribution without knowledge-document/library grounding (general_knowledge or unsupported) |
| missing_judgement | structural finding: no judgement/counter-evidence claim for a 'to what extent' item (INT-REQ-008 / HI-STR-001) |
| proves_wording | style/certainty finding (application §5: never write 'proves') |
| self_certification | no effect on any status; INT-HANDOFF-006 if carried as advisory status |