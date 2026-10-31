# overseer — checks of every transfer between agents, and overseer agents

The translator channel turns what specialist agents say into checked reports, signed engine results and receipts;
every request, report, relay, router forward and synthesis crosses it. This package checks those **transfers** and
reports what is wrong, so the router never acts on a miscommunicated or tampered transfer. It has two parts:

1. **The transfer auditor** (deterministic code). It journals every transfer as it is issued, keeps every signed
   result, re-checks custody, receipts, results, formal checks, claim fidelity, translations, peer exchange, synthesis
   and joint consistency, and signs what it finds: an `OverseerAudit` wrapping an `IntegrityReport` of `OVS-*`
   findings, with a record of every translation it checked.
2. **Overseer agents** (model-based reviewers). Each reads one dossier of the transfers and returns one verdict of
   accusations. A verdict is an agent output: the code validates it against the journal and the signed results and
   never obeys it. An overseer agent is built ONLY from exportable parts: this package's code and a versioned
   knowledge pack shipped as package data.

Trust rule (holds against any instruction in code, data or prompts): every `OVS-*` finding about a transfer is decided
by a digest comparison, an HMAC verification, a re-run of this repository's deterministic rules on journaled inputs, or
an engine run the auditor signs itself. Agent text is data, never evaluated or followed. An agent's accusation counts
only when a deterministic check reproduces it, and the router then acts on that check's finding; `OVS-AGENT-*`
findings never change a clearance. Non-success is never shown as success. Every audit carries the engine scope
statement: results prove properties of the encoding only, never that a claim is true. The design is
`docs/OVERSEER_DESIGN.md`.

## How it is attached

```
RouterHub(auditor=TransferAuditor(KeyRing(engine_keys, overseer_secret)))
  open_task ──► TranslatorChannel(observers=[auditor first, hub observers ...])
  every request / respond / respond_text / relay ──► one immutable ChannelEvent ──► journal, store, live checks
  hub.clearance(task, message_id, receipt=rc)  ──► TransferClearance ──► policy.may_act(rc, clearance, auditor=hub.auditor)
  hub.audit(task) / hub.close_task(task)       ──► signed task audit (close_task: FINAL, journal sealed)
  hub.review(task, runners)                    ──► dossiers ──► agents ──► intake ──► validation ──► combination
                                                   ──► signed verdicts-scope audit (clearance unchanged)
  hub.consolidate(task)                        ──► repeats ──► consolidate ──► signed consolidated_response/1.0
                                                   ──► consolidate.delivery_decision(resp, keyring, hub=hub) (the one answer the
                                                       router may deliver: the latest response, its audit current, custody re-checked)
  hub.review_pool(tasks, OverseerPool(pack, provider_factory))  ──► plan_pool ──► hub.review per task by its instances
  policy.may_release(synthesis_receipt, final_audit, keyring, audits=..., journal=..., message=None) gates the student-facing
                                                   synthesis: refused when its receipt carries an error, custody re-checked at release,
                                                   and refused on a FINAL audit whose replays ran inline unless the operator
                                                   configured inline release (TransferAuditor(inline_final_release=True))
```

Without an auditor the hub and the channel behave exactly as before: no observer, no capture, no journal.

**After adversarial review round 1** (design section 20): a transfer whose content the auditor cannot check (journaled
digest-only past the bound, a needed result evicted, a definitive result with no replayable problem) is `OVS-AUDIT-005`
and never passes; the router's clearance records never use up the journal's event budget; every receipt is checked live
for the findings its own structured results and identity imply (`OVS-RCPT-004`); a fault decided live, and every
finding of an issued task audit, stays in every later audit and clearance; the joint check pools the journaled outcomes,
not the channel's pool; a relayed report must reproduce its sender's delivery and a peer document its attribution
(`OVS-PEER-001`, `OVS-PEER-002`); every raw-text response is re-parsed by the auditor (`OVS-CUST-006`); accusations match
findings by (report, claim), message and report, and identifier lists resolve by type; the intake accepts a bare object or
exactly one fence; consolidation keeps apart answers whose figures differ anywhere (`material-claim-key/2`).

**After adversarial review round 2** (design section 21): a local engine result must carry the channel's journaled
solver configuration and the running engine's versions (`OVS-RES-004`, live), is replayed under the channel's
configuration, from the journaled capture when the store has evicted it, and a definitive status the replay cannot
reproduce is `OVS-AUDIT-005`, never the `OVS-RES-008` warning; results behind formal checks and constraint results are
always replayed, and a transfer citing a result sampled out of live replay carries `OVS-AUDIT-003`, never
`AUDIT_PASSED`; the live implied findings re-derive a reused report id (INT-HANDOFF-015), the plan's scope rules
(INT-HANDOFF-002/004) and the branch packs' error-level structural findings; a supplied text that presents a forwarded
report is held to byte identity whatever its document id, and one document id carries one text (`OVS-PEER-002`); claims
that occur verbatim in a response laid out with markdown structure, list numbers carried in a claim, a U+FEFF, the
contract's advisory fields on a structured report and a re-timestamped hand-off no longer give false errors; no
agent-chosen text reaches a signed finding; a contradiction with a signed result is `OVS-AGENT-001` whatever the pointer;
a confirmation covers only what its findings name; an unresolved accusation always reaches human review; the intake's
dossiers carry a keyed `issue_binding`; consolidation reads every figure as written and never folds superscripts; a
returning invented quotation is a repeat under any weaker check; the pool's hard maximum holds for any configuration.

**After adversarial review round 3** (design section 22): the student-facing synthesis text must be composed of its
synthesized claims (INT-LEDGER-028 then, INT-LEDGER-031 since the translator merge, so `may_release` refuses a negated, renamed or
extended text) and an exchange of the
Acts' names is a re-pairing (`name-partner`); the plan, solver configuration, key id and branch are pinned at the
channel's first event (a change is `OVS-CUST-002`, every rule applies the first ones, and a starved budget is RES-004
and, in R2, RES-007); the live implied findings re-derive the coverage records, the relay parties, ROLE_CONTRACTS,
INT-REQ-002, a captured INCONSISTENT joint run and a request's bounds against its own user input, and the shadow
compares finding multisets and structured fields; R2 reads an evicted result's problem from the journaled capture; a
padded false conflict is `OVS-JOINT-003`; a forwarded answer padded with background is linked and held to byte identity,
while a source the answer quotes is never linked to it; the re-parse compares whole claims; a claim of markup only and a
quoted claim of accuracy no longer give false errors; the journal counts each result once and sizes its bound from the
plan; `may_act` refuses a held or router-built clearance the auditor journaling its channel no longer stands by, and `delivery_decision(...,
hub=)` a stale consolidation; only a reply carrying the issued digest uses up an intake issue, and no refusal returns
it; a verdict's pack identity is recorded as attested by the runner or self-reported; consolidation reads eras, signs,
Roman numerals, ordinals, units and multipliers; a returning invented quotation is a repeat in any form; a padded
confirmation covers only the reports, results and documents its findings name; and a contradiction with another task's
signed result is `OVS-AGENT-001`.

**After the contained round c1** (design section 23): a `carried`, `paraphrased` or `merged` synthesized claim that gives
an act to a person its cited sources do not name for it (a name exchanged, or put where the source says "he") is
INT-LEDGER-032 (rule `name-substitution`, an error, so `may_release` refuses it; B2 and the shadow re-derive it; numbered INT-LEDGER-029 before
the second translator merge, whose INT-LEDGER-029 names a self-report); the
translation checks are no longer gated on who proposed the IR (the eligibility re-derivation and the tracing run on every
translation, and a problem with no provider is TRN-002 unless the operator declared its translator hand-built:
`TransferAuditor(hand_built_translators=...)`, recorded in the audit's coverage); two translation warnings, OVS-TRN-008
(a definitive display resting on unsuccessful sibling claims) and OVS-TRN-009 (one fact a premise in one translation and
unsupported in another); a FINAL audit whose replays ran inline is not released unless inline release was configured; and
the knowledge pack is version 1.1 (1.0 stays pinned beside it).

**After the recorded round-7 simulation** (design section 24): a premise identical to the conclusion is decided by the
engine, never assumed (rule `restatement-necessity`): the auditor runs the problem without the restating premise(s)
through the engine's validator, compiler and procedures, signs that run under its own key and stores it; ENTAILED makes
the restatement redundant (`OVS-TRN-010`, a warning naming the premise and citing the run), anything else, an undecided
run included, keeps `OVS-TRN-006`, the error. For the STEM branches and the original translator alike: TRN-008 names a
supporting claim in every claim id scheme (`h1.6`, `g4.2`, `g4.2@agent`, `s1.2`, `m1.2`, `c1.2`, the folded tails;
rule `claim-id-schemes`); TRN-005 reads scientific notation, vulgar fractions, SI-prefixed units and a stated precision;
the re-parse gives the request text to a parser that declares it reads it (rule `request-text`); FORM-002 reads the
re-derived check's expected status and declarations (`branch-image/2`: SATISFIABLE and UNSATISFIABLE expectations,
INCONSISTENT_PREMISES declared undecided, vacuous runs) and a failed check may carry INT-SUBJ-004 when its pack declares
warning severity (`failure-severity`); consolidation compares SI unit symbols with their case (`si-unit-symbol`). The
knowledge pack is version 1.2 (1.0 and 1.1 stay pinned beside it): it teaches the necessity rule and how to read STEM
answers, their translations and their formal checks.

**After the translator merge** (design section 25: the development branch's STEM-merged translator merged into this
branch, its behaviour unchanged): the overseer's circularity rule is never looser than the translator's own (rule
`circularity-agreement`: `circular_premises` and `assumed_grounding`, the engine's E112, on the IR as the grounding check
re-derives it) and takes no grounding kind label as evidence (rule `grounded-transcription`, restored by the repair of
design section 26 and made exact by the third repair, section 28: a restating premise is a transcription only when the
deterministic grounding check verified its located excerpt, which states its figures and none of them only as a target;
no number match is evidence, so the second repair's rule `figure-transcription` is withdrawn; any other label, a
`task_setting` included, is the writer's own, although the merged translator delivers it as a success; since the second translator merge, design section 44, also a task-authority premise the translator marks verified by its check of the task's numbers with no located excerpt, `checks.translation._located_only`). Rule
`data-standing` records what a check shows of each such premise: the writer's own by its grounding, refuted (rule
`same-quantity`: the request or a named document states a figure nowhere, only as a "show that" target, only for another
quantity, or only as a bound the premise states as a value; rule `frequency-words` reads "monthly" as 12; or the
translation's own declarations), uncheckable (shown not to be data: a source no check reads, or, since the fourth
repair, section 29, decision 56, content only a kind label presents as data: Boolean content whatever the translation
declares of it, anything but values of quantities, a structural figure, a figure its source states only bare; and,
since the fifth repair, section 30, decision 57, a figure its source states only where it asks, denies, offers
alternatives, puts up for examination or requires it, rule `statement-context`: in a yes/no question, under a negation,
as one of alternatives, inside a claim the answer must examine, as a requirement on the answer or the value of a limit
the premise's words do not name; every constraint text of the request is a requirement), or undecided (only values of
quantities, each figure read by rule `same-quantity` in its source for the quantity the premise names, a table's by its
column and row, rule `table-cells`, and stated there as a statement). A premise
restating the conclusion in another form restates it (rule `semantic-restatement`: Boolean structure, the order of
numbers, an identity element beside a symbol, and since STEM repair 12 the arithmetic of the conjunct's own symbols, rule
`arithmetic-restatement`; never the arithmetic of numbers alone, a line of working), a tautology conjoined to the conclusion needs no premise,
and a writer's-own premise restating only part of it under ENTAILED is graded when the receipt presents it as given with
the task (rule `receipt-disclosure`). A translation the translator withheld as circular (INVALID_FORMALIZATION with E112)
gets no finding, and one delivered with its problem is graded by `restatement-necessity` and rule `engine-shown`:
TRN-006 only when the result rests on a premise a check shows is not data, TRN-010 when it does not rest on the
restatement, TRN-011 (a warning that leaves an agent's `translation_circular` accusation unresolved) when it rests only on
undecided data premises, which shows only that a data conjunct needs its data premise. Each of these findings gives its
evidence first (what is restated, the auditor's signed run, the rules) and then as many whole premises' reasons as fit
under the 2,000-character finding cap, saying how many are left out; its audit note gives every reason (`fit_reasons`,
design section 28, Z-6). Every
check that re-derives a channel rule calls the merged channel's own code with the inputs it gives it: word bounds measured
with `measure_answer_words` under the constraint's `excludes` on the branch's word-count view, and one range problem for a
minimum and a maximum one span states (`merged-measure`, `range-bound`); a claim quoting the request covered as the channel
counts it (`request-quotation`); the coverage rule with the branch's hub hooks (`merged-coverage`) and the relay rule with
the router identity; a branch check run under a named engine policy is a run of the channel's engine and is replayed under
that policy's limits (`policy-configs`, `policy-limits`); the pipeline's unsigned probes replay under their own
configuration (`unsigned-probe`); INT-REQ-007 is an error except under AMBIGUOUS_TRANSLATION (`ambiguous-reading`); the
fixed severities follow the merged channel (INT-SUBJ-004, INT-REQ-016, the renumbered INT-LEDGER-030 and -031). Fidelity
reads the merged parsers' claims (`mark-annotation`, `same-form-figures`, `no-quotation-to-verify`, a list number after a
colon), the self-certification detector reads an offer to check the reader's work as no certification (`offered-check`),
and a consolidation member whose only findings are INT-REQ-016 collisions with other answers to the same input is clean
(`duplicate-collision`; the representative's `canonical_basis` then says so). The synthesis ledger keeps this branch's
polarity reading beside the merged aligned comparison (rule `unaligned-polarity`: a negation added or dropped under an
equivalence label is the INT-LEDGER-026 warning). The adjudicated genuine faults record is version 7 (version 6's adjudication, its evidence re-derived on the second translator merge: p7a's run without T-q25 and C-g4.2 gives the merged engine's W111 for E111), with three entries:
r7 lit-t13 p1-point in the genuine pass and mai-t13 m1.1 and m7.1 on r7's re-keyed pass, each OVS-TRN-006 (each result
rests on a Boolean task setting only its label presents as data); version 5 had retired them on that label reading, and
each keeps that retirement, which the harness re-derives to fail. Three retirements stand: the two pre-merge entries (the
merged translator no longer delivers either encoding; the merged parse and the pipeline run are re-derived from the
recorded answer, plan and proposal each retirement embeds) and version 3's r7 p7a g4.1@economics-specialist, retired by
the overseer's corrected rules (OVS-TRN-010 for C-g4.2 and OVS-TRN-011 for T-q25, its figure read in the supplied
table); the contained run replays and gates r7's re-keyed pass, serving a recorded fixture only to the claim
it was written for (rule `recorded-ids/2`; `scripts/overseer/README.md`), and since the fifth repair (decision 58) the
dossier export issues that pass's dossiers and the contained run's probe agents review it, so the agents are shown the
recorded STEM translations (gate `recorded_stem_translations_reviewed_by_agents`). The knowledge pack was then version 1.3 (1.0, 1.1 and
1.2 pinned beside it; 1.4 since the integration step, below): it describes the merged translator's STEM and original translations as they reach a dossier
(a STEM unit recorded as an assumption, never inside an expression, in the guidance's own words; what the code enforces
of a STEM translation apart from what the translator is only told, decision 59), and teaches exactly the circularity
rules of the checks (a kind is a label, not evidence, and no number match is; a restatement in another form or in part; a
`Bool` premise is never undecided; when an undecided premise is the request's statement; a number the request states
only in a question, under a negation, as one of alternatives, in a claim to examine or as a requirement is never data;
Examples 26 to 30).

**After the STEM completion** (design section 31, decision 60): every part the STEM branches put on a receipt is
re-derived. R2's rule `stem-structural` compares the ST codes the STEM packs re-derive from the journaled report with the
receipt's (code, severity, claims and message): one dropped, at a lower severity or moved is `OVS-RCPT-004`, one the
packs do not give `OVS-RCPT-005`. Rule `check-statements` holds each branch check's claims and `detail`, and the failure
finding naming its result (INT-SUBJ-001, -004, -002), to the channel's own statement of the check and its signed run (a
failed check written "solver ENTAILED", moved to another claim, or with its engine values rewritten is `OVS-RCPT-007`).
Rule `mark-annotation` reads a response with the parsers' own line rule, so an annotation closing a sentence inside a
line no longer makes a faithful STEM claim FID-001, nor its figures a parse loss (FID-006); TRN-005 reads no factor of 100 in a STEM answer (rule
`stem-exact-scale`) and reads a ratio with a decimal on either side (`0.036/12`) as its quotient and both sides (rule
`decimal-ratio`). The tampering suite runs on five recorded STEM tasks of r7 with the STEM receipt cases T23a to T23o (T23p since STEM repair 1, T23q to T23s since STEM repair 2, T23t to T23v since STEM repair 3, T23w to T23z since STEM repair 4, T23aa to T23ag since STEM repair 5, T23ah to T23ak since STEM repair 6, T23al to T23an since STEM repair 7, T23ao to T23at since STEM repair 8, T23au to T23ba since STEM repair 9, T23bb to T23bi since STEM repair 10, T23bj to T23bp since STEM repair 11),
and the contained run measures one planted fault per STEM fault class (`scripts/overseer/stem_probes.py`, gate
`stem_fault_classes_named`). Pack 1.3 teaches the STEM receipt: the ST codes and their severities, how to read a STEM
check and the tolerance rule, what the translator is told about tolerances and enclosures (nothing), checking a STEM
receipt against its results, Examples 31 and 32. The dossier contract is unchanged.

**After STEM repair 1** (design section 32, decision 61): an independent test of the STEM completion found STEM faults
the translator's reading did not see and one overseer escalation. Rule `excerpt-prefix-units` (`checks.translation`): a
quotation's located excerpt states each of its figures under the prefixes of its unit (in steps of a thousand, the metre
also in centimetres, a volume in litres too), so a translation that encodes "50.0 cm3" as 0.0000500 is neither an
ungrounded quotation (OVS-TRN-004) nor the claim assumed (OVS-TRN-006); a wrong conversion keeps both, and OVS-TRN-005
still names a number the answer does not state. Rule `check-statements` recomposes the claims of a failed substitution's
finding, which now names the statements whose values it contradicts (the channel's rule `related-statements`; T23p).
Pack 1.3 states the tolerance rule as the checks apply it (D31) and recognises the agent-only STEM translation faults
(Inspection I78 items 7 to 9: another stated given substituted, another relation encoded, two incompatible quantities
combined); the probe agents take their kind from the exported pack's own rule.

**After STEM repair 2** (design section 33, decision 62): a second independent test found a false error on correct
integer working, STEM statements the branch skipped with neither a check nor an ST code, and a pack that read that
silence as checked. The STEM front end now reads integer arithmetic, questions, Givens of every kind, the values working
takes from a supplied table, values taken after a quote, asides and premise cues (`docs/STEM_DESIGN.md` section 22), and
names what it reads but cannot check: ST-UNDEC-003 for a Given it cannot set against the request (re-derived by rule
`stem-structural`, so a dropped one is OVS-RCPT-004), ST-PARSE-001 for a relation sign no span reads or a relation written
partly in words. Rule `table-units` (`checks.translation`, STEM answers only): a supplied table's figure the answer states,
and a figure written with a compound unit, in the unit with no prefix and in the coherent SI unit are the answer's own
numbers for TRN-004 and TRN-005. The tampering suite adds T23q, T23r and T23s; pack 1.3 says exactly what is checked, what
is named and what neither (D31, D32, I97, I98, Example 34).

**After STEM repair 3** (design section 34, decision 63): a third independent test found a false error on correct work (a
value stated under a condition, `oxygen uptake at 30 °C = 80 mm³ per g per hour`, read as the conversion `30 °C = 80 mm³`),
an arithmetic slip passed inside a stated uncertainty, fault forms the STEM front end did not read, and pack text that
said an ST code never calls a claim wrong. The STEM front end now reads a value under a condition, a value with its
uncertainty at its central value, the processed value of a table row, the values and uncertainties a supplied text states
in prose, values restated in another unit, percentage changes, numbers of half-lives and stated roundings
(`docs/STEM_DESIGN.md` section 23); no ST or OVS code was added. The tampering suite adds T23t (a value-at Given's failure finding
dropped: OVS-RCPT-004), T23u (a failed central-value check restated as the band holding: OVS-RCPT-007) and T23v (a failed
processed-data check reported as holding: OVS-FORM-001 and OVS-FORM-002); pack 1.3 states each reading and says which
three ST codes call a relation wrong as written (D31, D32, I97, I98, the master prompt, Example 35). The probe module
matches a planted finding to the untampered copy's by the texts of its claims before their ids.

**After STEM repair 4** (design section 35, decision 64): a fourth independent test found two false errors on correct work (a
Boolean expression evaluated under the values its statement gives, read as an identity; a later part's substitution of the
value the prose says a quantity changes to), a Given uncertainty written "±3%" with neither its check nor its ST code (so an
agent following I98 was refuted by the deterministic check), fault forms the STEM front end did not read, and the contained
run's adjudication gate counting an entry raised in the other pass. The STEM front end now evaluates Boolean expressions under
stated values, lets a substitution take the value a stated change ends at, reads Given uncertainties written with "±", "+/-"
and "%", reads a rounding with a word naming the value's unit or a part of it ("to the nearest cent"), sets values at a lettered
row against the table, carries exact
working exactly, sets an uncertainty against the rule the answer states for it and bounds τ by what the rounding of the written
operands allows (`docs/STEM_DESIGN.md` section 24); no ST or OVS code was added. `adjudication_gate` and `finding_matches_entry`
match an adjudicated entry in the pass it names only. The tampering suite adds T23w (a failed Boolean evaluation restated as an
identity holding: OVS-RCPT-007), T23x (a stated-uncertainty INT-SUBJ-004 dropped: OVS-RCPT-004), T23y (a failed '±3%'
Given-uncertainty check reported as holding: OVS-FORM-001 and OVS-FORM-002) and T23z (an operand-precision τ restated as 1/100:
OVS-RCPT-007); pack 1.3 states each reading (D31, D32, I95, I98, the master prompt, Example 36), and an agent that follows I98
literally accuses nothing on the planted Givens the independent test's pack agent was refuted on.

**After STEM repair 5** (design section 36, decision 65): a fifth independent test found four false errors on correct work (the
evaluation after a correct rearrangement read as a step from it, a symbol reused for another quantity set against the other
part's value, a count after "so" paired with a chain three statements before), a prose relation the branch read with neither a
check nor an ST code while the pack said it names what it reads and cannot check, a conversion and a rounded restatement written in
prose missed, and a false warning on 2% of a raw table cell. The STEM front end now reads a formula's evaluation after any
rearrangement of it as its substitution, lets a reused symbol take its part's own result or a result its part computes, restates a
bare number only from an adjacent chain, checks a relation the prose gives as a quantity's value (naming a symbol with no value
ST-UNDEC-002, and leaving the equations its part solves or that concern its part's own result unread), reads conversions and
roundings the prose states (with a verb, in brackets, a precision in brackets, the full stop of "s.f."), requires a restatement to
the same place to equal what it restates, and leaves a percentage, a ratio, the bounds or an inline processing of a raw cell unread;
measured again class by class, it also reads a rearrangement after "Making R the subject", "Solving for R" or "Transposing" as a
step, the verbs "equal", "is equal to" and "is given by" before a prose relation, and conversions after "which equals", a semicolon
or a dash before "that is", "converts to" and a comma with "about"; and in a third pass, measured against the staged tree before the
repair, it checks a rearrangement in any words before the formula's evaluation as a step from the formula (the evaluation
reading had taken that check away), reads the inverse's swapped equation as no step, lets a reused symbol take a value its
part's prose names otherwise, another part's value of the line's quantity or a computation in its place, leaves a prose relation
giving its part's asked quantity in a reused symbol unread, restates no older chain after a value following its own statement's
value or a part of it ("4.4 W of it"), checks a prose value restated with a stated rounding and a conversion to a unit the prose
names, leaves a ratio of the raw cell to its processed value and a line naming the measured quantity unread, names a ratio set
against a number ST-UNDEC-001 and an applied symbol no definition makes a function ST-UNDEC-002 (`docs/STEM_DESIGN.md` section
25); no ST or OVS code was added. The tampering suite adds T23aa (a bound-relation INT-SUBJ-001 dropped: OVS-RCPT-004), T23ab (a failed
part-value substitution restated as holding: OVS-RCPT-007), T23ac (a failed prose-conversion check reported as holding:
OVS-FORM-001 and OVS-FORM-002), T23ad (a failed same-place restatement restated with the two half-widths: OVS-RCPT-007) and T23ae
(a prose-headed run's ST-UNDEC-002 dropped: OVS-RCPT-004), and from the third pass T23af (a failed rearranged-formula step restated
as holding: OVS-RCPT-007) and T23ag (a ratio's ST-UNDEC-001 dropped: OVS-RCPT-004); pack 1.3 states each reading and each equation
it leaves unread (D31, D32, I97, the master prompt, Example 37), and a test executes every such statement against the front end.

**After STEM repair 6** (design section 37, decision 66): a sixth independent test found a Given written in prose ("Data: emf 15 V,
internal resistance 0.50 Ω.", "Given: the mass of seeds is 12 g.", "Given: 15.0 cm³ of acid.", "We know …") with neither a check
nor an ST code while the pack said every Given has its check or ST-UNDEC-003 (an agent's true `finding_missing` was refuted), a
symbol reused in a part passing with any value the request states ("P = (9.93 V)² / 4.0 Ω" in the part that asks for the 6.0 ohm
resistor, R dropped from the check), a false ST-DIM-001 on the recorded answer's own notation ("k = (ln 2)/8 h⁻¹ = 0.0866 h⁻¹"),
and NAND, NOR and XNOR outside the Boolean grammar, on which the pack was silent. The STEM front end now reads every value of a data
list whose head ends with a colon, of the list a "Given:" line opens and of a Given clause's first clause as a Given value, named by
its item's words and checked as the same Given written with "=" (rule `prose-given`); checks a reused symbol given a request value
its part's question and working do not name at warning severity, in a check of its own (rule `part-given`); reads the unit after a
compact fraction as the fraction's own when that gives the relation one dimension (rule `fraction-unit`); and reads the gates as the
negations of AND, OR and XOR, naming a gate's order with no brackets ST-PARSE-002 (rule `boolean-gates`; `docs/STEM_DESIGN.md`
section 26); no ST or OVS code was added. The tampering suite adds T23ah (a prose Given's INT-SUBJ-004 dropped: OVS-RCPT-004),
T23ai (a failed part-given substitution restated as holding: OVS-RCPT-007), T23aj (a failed NAND evaluation reported as holding:
OVS-FORM-001 and OVS-FORM-002) and T23ak (an ST-DIM-001 the packs do not derive added on a relation read with a fraction's unit:
OVS-RCPT-005); pack 1.3 states each reading (D31, D32, I95, I97, I98, the master prompt, Example 38), and a test executes every such
statement against the front end.

**After STEM repair 7** (design section 38, decision 67): a seventh independent test found a law written with the symbol it evaluates
not on its own, its evaluation on the next line, read as an exact algebra step from the law ("ε = I(R + r)" then "I = 12 V / 2.9 Ω =
4.1 A"; "T½ = ln 2/λ, so λT½ = ln 2" then "λ = 0.693/8.0 h = 0.087 h⁻¹"), so correct working failed with the overseer agreeing; derivatives
in prime notation ("v'(t)", "v'(1)") and second derivatives in Leibniz notation ("d²v/dt²") with neither a check nor an ST code while
the pack said ST-UNDEC-001 names a derivative; and a value restated more finely than the chain's value ("To 3 s.f., V = 9.90 V." after
"… = 9.9 V", whose arithmetic gives 9.93) passing against that value alone. The STEM front end now reads such a line as the law
solved for its symbol by exact inverse operations, its substitution checked and no step read (rule `solved-law`; a symbol with no
stated value set against the values substituted for it before; ST-ALG-001 in mathematics for a principal root; a Given statement
never a step); names every Leibniz form and every primed letter applied to a bracket a derivative, its value at a point set against
the answer's own formula of it (rules `leibniz` and `prime-derivative`); and sets a finer restatement against the chain's written
arithmetic at warning severity beside the unchanged check against the chain's value (rule `finer-restatement`; `docs/STEM_DESIGN.md`
section 27); no ST or OVS code was added. The tampering suite adds T23al (a failed solved-law substitution restated as holding:
OVS-RCPT-007), T23am (a derivative's ST-UNDEC-001 dropped: OVS-RCPT-004; since STEM repair 11 a derivative the branch does not
check, `dN/dt = −λN`) and T23an (a failed finer-restatement check's
INT-SUBJ-004 dropped: OVS-RCPT-004); pack 1.3 states each reading (D31, D32, I97, the master prompt, the mistakes rows), and a test
executes every such statement against the front end.

**After STEM repair 8** (design section 39, decision 68): an eighth independent test found a value a run computes under a condition
("Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s", "I at t = 5 s = 12 V / 4.5 Ω = 2.7 A", "Speed after 2.0 s = …") or
right after the list that names it ("Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3") read as a relation between the condition (or
the list's last value) and the computation, so correct working failed (with ST-DIM-001) and the overseer agreed; a value copied wrongly
from the supplied table ("t = 12 h: 568 − 20 = 548 ± 11" for the table's 586) and a wrong background ("220 − 25") neither checked nor
named, while D31 said a value the working takes from the table is set against its row; a law its evaluation does not follow ("V = ε +
Ir" then "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V") named by nothing, and a failed substitution not naming its law ("P = V/R"); and a
rounding after ", so" with a describing word before it ("= 60.4% decrease, so 61% to 2 s.f.") not read. The STEM front end now reads
such a run as the named quantity's value (rules `value-at` for a computing chain, `name-list` and `item-label`), sets the value of the
condition's dimension the computation takes against the condition (rule `condition-value`) and a term that is no listed value against
the list, a number the working takes beside a supplied table's cells against the row's cell or the stated value of its quantity (rule
`table-terms`) and a law against the line that evaluates it at the values the line puts in (rule `law-values`), each at warning
severity, names a failed substitution's law, and reads up to three describing words before ", so" (`docs/STEM_DESIGN.md` section 28);
no ST or OVS code was added. The tampering suite adds T23ao (a failed law-values check restated as holding: OVS-RCPT-007), T23ap (a
failed table-terms check's INT-SUBJ-004 dropped: OVS-RCPT-004), T23aq (a failed condition-value check reported as holding: OVS-FORM-001
and -002), T23ar (an ST-DIM-001 the packs do not derive added on a mean computed under its condition: OVS-RCPT-005), T23as (a failed
restatement's INT-SUBJ-001 dropped: OVS-RCPT-004) and T23at (a failed name-list check restated as holding: OVS-RCPT-007); pack 1.3
states each reading (D31, I97, the master prompt, the mistakes rows, Example 39), and a test executes every such statement against
the front end and regenerates Example 39 through the channel.

**After STEM repair 9** (design section 40, decision 69): a ninth independent test found a correct check line at the end of a part
("As a check, ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V.") taking the part's question words, so a later change stated from the part's
result was set against it (a false INT-SUBJ-004 the overseer agreed with); a Given of a function's value ("Given: v(1) = 4 m s⁻¹.")
with neither a check nor an ST code while the pack said every Given has one or the other, so an agent's true `finding_missing` was
refuted; a trial copied wrongly into a row's mean, a wrong rearrangement evaluated for a quantity the request names, a decay over
stated half-lives divided by their number, a Given function contradicting the request's, a wrong median and a value restated at a
rounding it is not written to, each named by nothing; and D31's list of what the branch checks written as one line of 14,871 bytes.
The STEM front end now takes a part's answer from its last value that is no check and names no other quantity (rule `part-answer`),
sets the value a line gives a quantity the request names against the request (rule `named-result`), a Given of a function's value or
of a function against the request's function, or names it ST-UNDEC-003 (rule `given-function`), the terms of a sum over a supplied
row's repeats against the row (rule `row-terms`), a value computed over stated half-lives with no power of ½ against the decay law
(rule `decay-law`), a median, mode, range or mean against the statistic it forms (rule `statistics`; another statistic ST-UNDEC-001)
and a value stated with a rounding against the place the rounding names (rule `rounded-digits`), each at warning severity
(`docs/STEM_DESIGN.md` section 29); no ST or OVS code was added. The tampering suite adds T23au (a failed named-result check's
INT-SUBJ-004 dropped: OVS-RCPT-004), T23av (a failed given-function check restated as holding: OVS-RCPT-007), T23aw (a failed
row-terms check reported as holding: OVS-FORM-001 and -002), T23ax (an undefined Given function's ST-UNDEC-003 dropped:
OVS-RCPT-004), T23ay (a failed decay-law check restated as holding: OVS-RCPT-007), T23az (a failed rounded-digits check's
INT-SUBJ-004 dropped: OVS-RCPT-004) and T23ba (a failed statistics check restated as holding: OVS-RCPT-007); pack 1.3 states each
reading (D31, now one kind of relation to a bullet and one statement to a line, D32, I97, I98, the master prompt, the mistakes rows,
Example 40), a test executes every such statement against the front end and regenerates Example 40 through the channel, and a test
bounds the length of every line of the pack's STEM rules.

**After STEM repair 10** (design section 41, decision 70): a tenth independent test found a wrong conversion the prose states with a
verb ("A time of 45 s is 0.45 min.") checked only when it ended the whole answer, whether it ends its clause having been read in a
60-character window of the whole text; a line naming its rows and its column read in no column when its part's question named
another; values at a supplied table's row restated wrongly in common shapes ("Site A has 43 mayfly nymphs per kick sample."), another
resistor's value substituted for the one a sentence names, a wrong law evaluated right at a condition its part had computed, a base
conversion in prose and a definite integral (ST-UNDEC-001 whatever its value) each named by nothing; and, among its documented
limits, a 0.44% slip on a power of the request's exact rate holding under τ = 1/100 and a value restated from a decimal written with
its digits cut ST-UNDEC-001 whatever its rounding. The STEM front end now reads whether a restated value ends its clause in its own
statement (rule `prose-conversion`), a line's column by its own words when they name exactly one (rule `table-operands`), a value at
a supplied row stated in its own clause in any order of row, column and verb, numbered rows and columns told apart by a number, and
never a comparison, an operation, a processed quantity or a value under a condition, a hypothesis, a target, a modal verb or a
bound as a cell (rule `row-value`; rule `table-data` chooses its column in the
value's own statement too), a change's own start under its own condition as restating nothing (rule `named-change`), and sets a
working naming a component by a request value against that component (rule `named-component`), a value under a condition against
the value computed for its symbol under the same condition (rule `condition-result`), a whole number restated in another base
against the numeral read in its base, a base named only after the first numeral read both ways (rule `prose-base`), a
definite integral of a polynomial with whole-number limits, signed or
written in plain text, against its evaluation bracket or a closed value (rule `definite-integral`), a numeral writing the request's
data as exact (rule `operand-precision` for given data) and a value restated from a cut decimal, or a closed expression set equal
to one, against the cut digits (rule `ellipsis-rounding`, "2.66…" now read as cut, not rounded) (`docs/STEM_DESIGN.md` section 30);
no ST or OVS code was added. The tampering suite adds T23bb (a failed prose conversion followed by another statement, its
INT-SUBJ-001 dropped: OVS-RCPT-004), T23bc (a failed named-component check restated as holding: OVS-RCPT-007), T23bd (a failed
condition-result check reported as holding: OVS-FORM-001 and -002), T23be (a failed base conversion in prose, its INT-SUBJ-001
dropped: OVS-RCPT-004), T23bf (a failed definite-integral check restated as holding: OVS-RCPT-007), T23bg (a failed row-value check
at a numbered row, its INT-SUBJ-004 dropped: OVS-RCPT-004), T23bh (a failed ellipsis-rounding restatement reported as holding:
OVS-FORM-001 and -002) and T23bi (a failed arithmetic check on the request's exact data restated at τ = 1/100: OVS-RCPT-007); the
STEM probes add 94 (54 answers, 40 controls; 606 in all); pack 1.3 states each reading (D31, a paragraph after D32 on the integrals
and ellipses now checked, I97, the master prompt, the mistakes rows; Examples 37 and 39 regenerated through the channel, three of
their checks' τ now reading the request's data as exact), and a test executes every such statement against the front end.

**After STEM repair 11** (design section 42, decision 71): an eleventh independent test found correct working failed as an error
when every operand is whole and the result a rounded quotient written with "=" (exact mode gave h = 0: "(92 − 18) ÷ 18 × 100 =
411%", "1,000 ÷ 3 = 333", "= 34% to 2 s.f."); a Given one unit off the request's data in its last digit held (R7's inclusive band);
part (b)'s factorisation and roots in a letter part (a)'s question gives a value, a function's value stated in prose, a wrong
restatement of an inequality's solution, a wrong derivative (only ST-UNDEC-001), a wrong given substituted where no symbol is bound
and a base phrase opening the clause each named by nothing; and the pack's one system text of 472,563 characters for every dossier,
too large for the cheapest agents. The STEM front end now states exact work to its last digit when the value has two or more
figures (rule `exact-rounding`) and reads a rounding a line states for its own result (rule `result-rounding`); takes the request's
data and a Given restating them as written, |w − b| ≤ max(h(w), h(b)) (rule `given-data`); gives a letter a part's question binds
that value in that part only (rule `part-condition`) and keeps the equation a root statement solves as the relation the next line
steps from (rule `root-statement`), each named in the step's detail; and sets a function's value against the function the request
or the answer defines (rule `function-value`), a solved bound against the relation before it solved exactly (rule
`inequality-solution`), a polynomial's derivative against the one the STEM pack forms by the power rule (rule `derivative`), a
numeral in the place the answer's other evaluation of the same expression writes the request's value (rule `same-shape`), a value
substituted for a symbol the answer substitutes the request's value for elsewhere (rule `unbound-substitution`) and a base phrase
opening the clause (rule `prose-base`) (`docs/STEM_DESIGN.md` section 31); no ST or OVS code was added. The pack's agent documents
mark the parts that concern STEM answers or translations as modules; the manifest records the digest of every composition
(`system_modules`, `system_compositions`), and an agent is sent the core and the modules its dossier's content needs, read from the
dossier as data (`KnowledgePack.system_text_for`, `dossier_modules`): the runner records the composition and its digest with every
run, and the contained run checks that every call's system text is its dossier's composition. The tampering suite adds T23bj (a
failed derivative check restated as holding: OVS-RCPT-007), T23bk (a failed function-value check's INT-SUBJ-004 dropped:
OVS-RCPT-004), T23bl (a failed unbound-substitution check reported as holding: OVS-FORM-001 and -002), T23bm (a failed given-data
check restated as holding: OVS-RCPT-007), T23bn (a failed exact-rounding check's INT-SUBJ-001 dropped: OVS-RCPT-004), T23bo (a
failed step from the equation a root statement keeps, restated as holding: OVS-RCPT-007) and T23bp (a failed part-condition step's
INT-SUBJ-001 dropped: OVS-RCPT-004); the STEM probes add 35 (20 answers, 15 controls; 641 in all) and the three translator gaps
equations-factorising, maths-roots and formulas-derivative are probes counted now; pack 1.3 states each reading (D31, D32, I97, the
master prompt, the mistakes rows) and its modules (README section 4), and a test executes every such statement against the front
end.

**After STEM repair 12** (design section 43, decision 72): a twelfth independent test found a wrong derivative ENTAILED and
satisfied with no finding ("Also d/dt (6 − 6t) = −6t." beside the request's "t = 1": the identity's variable took that value as
one it substitutes, so the identity was decided at it only), as were an antiderivative, a definite integral's bracket and a Given
function of the same shape; hexadecimal restatements with letter digits in prose ("In hexadecimal, 1000 is 3E9.") and
restatements after an approximation word ("= 2.67 A, which is about 2.6 A") named by nothing; and a circular translation in
affine or scaled form ("contrib − 2.00 = 0", "2 × contrib = 4.00") named by no check, a correct `translation_circular`
accusation of it refuted. The STEM front end now decides an identity from the trivially true premise for every value of its own
variables, which take no binding and no formula (rule `identity-variable`, named in the check's detail; an antiderivative's
check states what it compares), reads a numeral with letter digits in base 16 where the words beside it name that base, a
numeral set equal to one whose base the words after it name as a base conversion, and a base phrase opening the clause with no
comma (rule `prose-base`; the last two were false failures on correct working, found closing the class), and reads a value
after an approximation word, a rounding verb or "approximately equal to" on its chain's line as that chain restated, with no τ
(rule `inline-restatement`, R8) (`docs/STEM_DESIGN.md` section 32). The overseer reads a premise equivalent to a conjunct by the
arithmetic of the conjunct's own symbols as restating it (rule `arithmetic-restatement`: arithmetic of numbers alone, a line of
working, stays the derivation the engine checks), and names an identity step whose held problem gives the variable its
statement says it holds for every value of a value or a formula, signed as the success it expects (**OVS-FORM-005**, rule
`identity-statement`, kind `formal_status_wrong`): it reads the problem the engine decided, so a pack that binds the variable is
named although the re-derivation, running the same pack, agrees. The tampering suite adds T23bq (the identity decided with rule
identity-variable undone in the pack the channel and the re-derivation both run: OVS-FORM-005), T23br (a failed antiderivative
check restated as holding without its identity-variable reading: OVS-RCPT-007), T23bs (a failed hexadecimal restatement's
INT-SUBJ-001 dropped: OVS-RCPT-004), T23bt (a failed restatement after "which is about" reported as holding: OVS-FORM-001 and
-002) and, on the synthetic task, T22ag to T22ai (the conclusion assumed with its terms moved across or both sides scaled:
OVS-TRN-006) with the control T22-working; the STEM probes add 36 (16 answers, 16 controls, 4 translation plants; 677 in all);
pack 1.3 states each reading (D31, I77, I97, I98, K6, the kinds table, the master prompt, the mistakes rows), and a test
executes every such statement against the front end and the overseer's readings.

**After the round-7 arena findings** (design section 45): a replay's budget runs from when the worker TAKES the job, never
from when it was queued, so a correct replay waiting behind others is never budget exceeded (twenty queued at once had
six or seven marked so, OVS-AUDIT-005 on results the replay reproduces); a drain without a timeout waits for every
outstanding job, a job still running at its budget is budget exceeded and its worker replaced so the jobs behind it still
run, and a worker that exits or never takes a job leaves an error, never agreement. The intake never raises on agent
output and always records a bound reply's outcome: a verdict holding a lone UTF-16 surrogate (a provider's decoding of a
truncated emoji escape) is `unparseable` with OVS-AGENT-005, whatever the parser raises is `unparseable`, and an unexpected
error at a later stage is refused under that stage's reason; the runner's record keeps such a reply serialisable (U+FFFD)
with the digest of the reply as received.

**After the round-7 core hand-offs** (design section 46): every signature comparison of the overseer (a consolidated
response, a signed audit, a key ring MAC) is total on untrusted input, so a forged value holding non-ASCII or surrogate
text reads False and never raises; the overseer's mirrors read the channel's rule that quotations are checked against the
router's texts only (rule `request-quotation` reads no text a report supplies itself, and the INT-REQ-002 expectation is a
report text the request did not send, or changed, also when the request sent none); FID-009 also names a dependent
agent's claim stating a check result credited to the system or to a report that no INT-REQ-014 names, since a relayed
check result is a self-report (advisory), never evidence. The channel's widened codes (INT-REQ-000, -002, -003, -006, -007,
-009, -014, INT-HANDOFF-013, INT-LEDGER-025, INT-CONFLICT-001) are listed in design section 46.2.

## Translator oversight

The translator is an agent like any other: for each eligible claim a provider PROPOSES a formal problem (the IR), and
that proposal is untrusted data. Every translation crosses the channel inside an outcome of the receipt of the report
that carries its claim, so the journal holds, for each one, the delivered claim, the proposed IR, the translation's own
validation outcome and the cited result (signature-verified in the store). `checks/translation.py` re-checks every
translation of a delivered claim from the journal (design section 18):

| Code | Severity | Decided by |
| --- | --- | --- |
| `OVS-TRN-001` | error | the IR re-validated as untrusted JSON: the engine's parser and validator (schema, identifiers, sorts, operator allowlist, limits), its claim and request ids, the subject profile's sorts |
| `OVS-TRN-002` | error | status, eligibility and engine run re-derived from the validation: a problem under a status that forbids one, ambiguity flags under TRANSLATED (an ambiguity resolved silently), an eligibility the policy does not re-derive (a claim forced into IR), whoever proposed the translation, and a problem with no provider or under another policy version from a translator not declared hand-built |
| `OVS-TRN-003` | error | a `verified` grounding the re-run of the translator's grounding check does not reproduce |
| `OVS-TRN-004` | warning | a quotation excerpt absent from the supplied text it names (disclosed as unverified) |
| `OVS-TRN-005` | warning | a quotation or number of a translation (whoever proposed it) that the specialist's report never states (fixed spelling rules, each extension a named rule with its own test; in a STEM answer no factor of 100 is read, rule `stem-exact-scale`) |
| `OVS-TRN-006` | error | circular: the conclusion, or part of it, is restated by premises that are the writer's own for the overseer (rule `circularity-agreement`: never looser than the translator's E112; rule `semantic-restatement`: as written or in another form, by Boolean structure, the order of numbers or the arithmetic of the conjunct's own symbols (rule `arithmetic-restatement`), never by the arithmetic of numbers alone; rule `grounded-transcription`: every grounding but a located excerpt the deterministic grounding check verified (its figures stated, none only as a target); a kind label or a number match alone is the writer's own; rule `receipt-disclosure`: a premise restating only part of the conclusion counts when the receipt presents it as given with the task), at least one of them SHOWN not to be data (rule `data-standing`: the writer's own by its grounding, refuted by its source, rule `same-quantity`, or by the translation's own declarations, naming no source the overseer holds, or presented as data on a kind label alone: a `task_setting` or `supplied_text` with no located excerpt whose content no check reads in its source, such as Boolean content, a relation, a structural figure or a figure stated there only bare, decision 56, or only where the source asks, denies, offers alternatives, puts up for examination or requires it, rule `statement-context`, decision 57), and the auditor's own signed engine run of the problem without the shown ones, keeping the undecided ones, does not give ENTAILED, or could not decide (rules `restatement-necessity` and `engine-shown`); a restatement the overseer upholds is a transcription (a coverage note), and a translation the translator withheld as circular gets no finding |
| `OVS-TRN-007` | error | the outcome's summary is not the deterministic statement of its translation and its signed result |
| `OVS-TRN-008` | warning | a display ENTAILED or CONSISTENT whose premises assert supporting claims whose own outcomes in the same receipt are not successful (rule `sibling-status`) |
| `OVS-TRN-009` | warning | one fact asserted as a premise in one translation of a receipt and left an unsupported conjunct in another's own check (rule `same-fact-premise`) |
| `OVS-TRN-010` | warning | a redundant restatement: the rule of TRN-006 holds for a delivered translation whose conclusion is restated as a whole, but the auditor's own signed engine run without the restating premise(s) still gives ENTAILED (rule `restatement-necessity`), from the other premises or from undecided data premises (then also TRN-011): the result does not rest on the claim assumed |
| `OVS-TRN-011` | warning | a restatement under an undecided data grounding: the result rests only on premises restating the conclusion, or part of it, as data the request or a supplied text holds (a `task_setting`, or a `supplied_text` naming a supplied document, with no excerpt) whose whole content rule `same-quantity` reads there (values of quantities, each figure stated in the source for the quantity the premise names, as the premise states it, in a table in the row the premise names, rule `table-cells`, and as a statement, rule `statement-context`; never Boolean content) but that no check verifies or refutes (rule `data-standing`); the run without them shows only that a data conjunct needs its data premise (rule `engine-shown`), so a `translation_circular` accusation of it is unresolved (a meaning question) |

The task audit records every translation it checked (`TranslationAudit`: the claim text, the claims it cites, the
proposed IR as journaled with its digest, status, eligibility, ambiguity flags, failed grounding checks, diagnostics,
the re-validation, the signed result's id, status, digest and signature, which checks ran, and the `OVS-*` codes naming
it); `TransferAuditor.translations(channel_uid)` returns the same records with the full translation. Live, the
translation checks run in the asynchronous tier with fidelity, so a transfer is AUDIT_PENDING until they have run.

Overseer agents receive each translation with its claim in the dossier (`links.translations`: the claim, the claims it
cites, the translation, the result) and may accuse it under four kinds: `translation_invalid` (TRN-001, 002),
`translation_ungrounded` (TRN-003, 004, 005), `translation_circular` (TRN-006), and `translation_unfaithful` (a dropped
condition, a flipped comparison or direction, an invented premise, an ambiguity resolved in words, a claim forced into
IR, a conclusion that is not the claim), which no check decides: it is always unresolved and goes to human review. The
lens `translation_fidelity` starts an agent on the translations. An accusation is refuted only when the checks its kind
needs actually ran on the named claim's translation; their verdicts stay advisory, and only the deterministic checks
and the signed results decide.

## What the translator emits (the integration step before arena round 8)

The overseer knows everything the merged translator and its channel can put on a transfer (design section 47):

- **Code tables** (`emitted.py`): every receipt code with every severity it is raised at and the defect labels its
  finding can carry, every named diagnostic (`ARG-*`, `EVD-*`, the STEM method codes) with its label, highest severity,
  layers and caps, the 28 labels, every engine, translation and receipt status, every engine diagnostic code, every reason
  of the release check (rules 1 to 9, rules 8 and 9 the argument diagnosis's) and of the outcome's release assessment, the
  named engine policies and the named rejections (INT-SYNTH-014 among them). Drift tests hold the tables to the
  translator's own sources (`tests/overseer/test_integration_codes.py`).
- **The audit reads them** (nothing is downgraded): rule `argument-image` (OVS-RCPT-004) holds every receipt's labels,
  INT-ARG-001 findings, `named_diagnostics`, overflow count and INT-XENC-001 to what the channel derives, the report level
  re-run on the journaled report (a failed branch check's label, the check's own first, is compared in R2 with the check
  the branch pack re-derives, since the receipt does not journal it); rule `diagnosis-image` (OVS-TRN-007, widened) holds every outcome's `named_diagnostics`,
  `diagnosis_incomplete` and `release` to its translation and signed result. A load-bearing writer's assumption, an
  unchecked source or a STEM method error dropped, lowered or relabelled fails the transfer.
- **Dossiers** show a receipt's argument diagnosis and a signed result's `named_diagnostics` and `argument_rules` (each only
  when present); **pack 1.4** teaches them (Dossier guide D33 to D37, Inspection I99, K8, the Kinds and codes §8 table of
  every code, N14); pack 1.3 stays pinned to the digest it was released under.
- **The pool** reads each task's risk signals and records from the journal (`emitted.risk_reading`): a signal sends the
  dossier to two independent instances, a record weighs two review units; neither ever makes a plan smaller.

## Parts of the package

| Part | Module | What it does |
| --- | --- | --- |
| Codes | `codes.py` | every `OVS-*` code with one severity and one stage (`OVS-AGENT-*` included) |
| Contracts | `contracts.py` | `JournalEntry`, `StoredResult`, `TransferClearance`, `OverseerAudit`, `AuditCoverage`, `Divergence`, `TranslationAudit`; the audit scope sentence |
| Keys | `keys.py` | `KeyRing`: engine keys for verification only (local or external), one overseer secret and its derived subkeys (journal, audit, runs, sampling, intake, consolidation, delivery) |
| Journal | `journal.py` | `ChannelJournal`: append-only, hash-chained, HMAC'd, bounded, sealed on a FINAL audit, `close_task` or garbage collection |
| Result store | `store.py` | `ResultStore`: signed results by id, signature verified at put, bounded, tombstones after eviction |
| View | `view.py` | `OverseerView.from_journal` (authoritative) and `from_channel` (degraded) |
| Replay | `replay.py` | `Replayer`: every stored problem re-run on a fresh engine in a worker process (inline for tests), each job's budget from when the worker takes it, keyed sampling on overflow |
| Checks | `checks/*.py` | custody, receipts, results, formal, fidelity, self-certification, translation (translator oversight), peer, synthesis, joint, divergence, shadow channel |
| Auditor | `audit.py` | `run_overseer_checks` (the pure function), `TransferAuditor` (live use), `sign_audit`, `verify_audit` |
| Router policy | `policy.py` | `may_act`, `check_before_acting` (bounded PENDING wait, 250 ms), `may_release` |
| Dossier | `dossier.py` | `build_dossier`: the redacted view one agent reads, with pointers and an index; `resolve_pointer` |
| Verdict contract | `verdicts.py` | `overseer_verdict/1.0`: `AgentVerdict`, `Accusation`, `EngineStatement`, `PackIdentity`, `KIND_CHECKS` |
| Intake | `intake.py` | `VerdictIntake`: issues dossiers under accepted packs, parses replies strictly, signs accepted verdicts under the intake key |
| Validation | `validate.py` | `validate_overseer_verdict`: each accusation confirmed, refuted, unverifiable or unresolved by checks and signed results |
| Combination | `combine.py` | `combine_verdicts`: several agents' verdicts grouped without voting on facts; a human review queue |
| Knowledge pack | `knowledge/overseer-knowledge-docs-1.4/` | the agent's whole configuration (below); 1.0 to 1.3 stay beside it, pinned |
| Emitted codes | `emitted.py` | everything the translator and the channel emit, as the overseer knows it: every receipt code with its severities and labels, every named diagnostic, the 28 labels, every status and engine code, every release refusal (rules 1 to 9, `release-v1`), the named policies and rejections; `risk_reading` (the risk signals and records a task carries) |
| Pack loader | `pack.py` | `load_pack`, `installed_pack`, `KnowledgePack`, `PACK_DIGESTS` (the trust anchor), schema and manifest generation |
| Exporter | `export.py` | `python -m epinoic_logic.overseer.export --out DIR [--zip]`, `--verify PATH`, `--refresh-source` (maintainers) |
| Agent runner | `runner.py` | `OverseerAgentRunner`: model input from a loaded pack and one dossier, one provider call, the reply handed to the intake as data |
| Fidelity normalisation | `faithful.py` | the fixed text normalisation the fidelity checks use |
| Repeated faults | `repeats.py` | a deterministic signature for every error-level fault of an answer (code, normalised offending claim or quoted phrase, figures); `detect_repeats` over a task's answers: `OVS-REP-001`, counts per agent |
| Consolidation | `consolidate.py` | `consolidate`: ONE signed `consolidated_response/1.0` for answers several agents gave to one input (groups, representative, exclusions, conflicts disclosed); `delivery_decision`, `check_consolidation` (`OVS-CONS-*`) |
| Overseer pool | `pool.py` | `plan_pool` / `OverseerPool`: how many overseer-agent instances review a batch (one by default, two or more on repeated faults or over the quota, never past the maximum), all from one loaded pack |
| Delivery policy | `delivery_policy.py` | `DeliveryPolicy`: for one deliverable, FORMALLY CHECKED within the 240 s translation budget, else the overseer-selected fallback (validated accuracy above 0.90), NOT CHECKED only when configured, else withheld; the signed `delivery_receipt/1.0` (key id `overseer-delivery`) and `delivered_answer/1.0` (`docs/DELIVERY.md`) |

The observer hook itself lives outside this package, which the channel never imports: `channel/events.py`
(`ChannelEvent`, `snapshot_event`, `observe_call`), the private decorator on the four entry points of
`channel/bus.py` (`observers=`, `add_observer`, `channel_uid`, `observer_errors`), the result sink `engine/sink.py`, and
the hub integration in `branches/hub.py` (`observers=`, `auditor=`, `closed_channels`, `close_task`, `clearance`,
`audit`, `view`, `review`, and for consolidation `consolidate`, `consolidations`, `repeats`, `review_pool`).

## The knowledge pack

`knowledge/overseer-knowledge-docs-1.4/` is the overseer agent's whole configuration, laid out like the specialists'
knowledge documents: `master_prompt.txt` (read first), the numbered documents `01-role-and-trust.md` to
`09-when-unsure.md` (role and trust rule, the dossier, what to inspect per transfer type and per translation, the
evidence rule, the verdict format, the kinds and codes, 32 worked examples, what never to do, what to do when unsure,
and, since the consolidation stage, how to review consolidations and repeated faults as one of several instances; since
pack 1.2, how to read STEM answers: their claim ids and roles, the numbers and units of their translations, significant
figures and tolerances, lines of working, truth tables and Boolean identities, mathematical items and the branch's own
formal checks; since pack 1.3, the merged translator's translations as they reach a dossier: its claim ids, the encodings
it withholds itself, the engine's withheld verdicts, the merged rules for word bounds and the ledger codes as the merged
channel raises them; since the STEM completion, a STEM receipt: the ST codes with their severities, a STEM check's
detail, the tolerance rule and enclosures, the engine's values in a failure finding, and the receipt held to its
results; since pack 1.4, the argument diagnosis and every code the translator and the channel emit: D33 to D37, I99, K8,
the kinds-and-codes §8 table and N14),
the generated
`verdict.schema.json` and `dossier.schema.json`, and `manifest.json` (every file's SHA-256, the system order and digest,
the pack digest). No instruction text for agents lives in code, scripts or `docs/`; `docs/OVERSEER_AGENT_BRIEF.md` is
only a pointer to the pack.

- **Loader** (`pack.py`): checks every file against the manifest and the manifest's pack digest against the digest
  pinned in the code (`PACK_DIGESTS`); refuses a tampered, unlisted, unpinned or mismatched pack (`PackError` with its
  reason) and never executes anything from a pack.
- **Exporter** (`export.py`): writes the pack out as a self-contained directory (and a deterministic zip) and loads the
  written copy back to the same identity.
- **Deployer README**: `knowledge/overseer-knowledge-docs-1.4/README.md`, exported with the pack. It tells whoever
  deploys the pack how to configure any model with it (`master_prompt.txt` plus the documents as the system
  configuration, one dossier JSON in, one verdict JSON out, validated by this code) and is never sent to a model.
- **Runner** (`runner.py`): builds the system text from a loaded pack by the manifest's fixed rule and the user text
  from the dossier alone, calls a provider once through `translate.providers.base.CompletionProvider`, and hands the
  reply to the intake unchanged. No live provider is claimed or required; tests use fake providers. Deployed overseer
  agents are meant to run on the cheapest model tier: correctness rests on this code and the signed engine results,
  never on the agent.

Every verdict names the pack it was produced under (copied from its dossier); the intake and validation reject a
verdict whose pack is unknown or differs from the dossier's (`OVS-AGENT-005`).

## Tests

`tests/overseer/`: `test_audit_*` (the auditor, one positive test and one control per code), `test_protocol_*` (dossier,
verdicts, intake, validation, combination), `test_knowledge_*` (pack loading and every refusal, drift of schemas,
manifest, kinds table and examples, export round trips, the runner with fake providers), `test_hook_*` (non-interference
and equivalence of the bus hook, the hub's wiring and task lifecycle, clearance and router policy, `hub.review`),
`test_translation_*` (translator oversight: every `OVS-TRN-*` code with a control and tampering cases through the real
translation pipeline, the signed translation record, live clearance, the spelling rules; the dossier's translation
links, the translation kinds' validation outcomes and a hub review over translations), `test_consolidation_*`
(duplicated and near-duplicate answers, exclusions, conflicts disclosed, delivery, tampering and staleness of a
consolidated response; repeated faults across agents, resubmissions and reopened tasks; the pool plan for 1, 10 and 60
dossiers and the maximum never exceeded; `hub.review_pool` end to end; consolidations in informed dossiers), and
`test_rebuild_*` (the overseer on the merged translator: every rule the merge needed, each with a control; with the
recorded rounds, r7's translations served under the merged claim ids), and `test_stem_completion.py` (the STEM
completion's rules on every recorded STEM receipt the repository keeps, the STEM tampering cases with their planted
controls, the fault-class probes, and the pack's STEM statements beside the code).

## Consolidation, repeated faults and self-duplication

When several agents answer one input, the infrastructure (never an agent) consolidates their answers into one signed
`consolidated_response/1.0` (`consolidate.py`). Answers are excluded when not delivered, when an error-level finding of
their receipt or of the task audit names them, when their clearance is not passed, or when they repeat a fault; the rest
are grouped by identical normalised text, then by equal material-claim keys only when a signed engine run finds the
members' encodings consistent (every pooled claim renamed per answer, so duplicated agents' claim ids never collide).
Each group records its agents and a representative (the earliest clean member; `canonical_basis` says whether it is fully
clean, clean but for INT-REQ-016 collisions with other answers to the same input, or, when no member is clean, the
earliest member with findings). Two or more groups, or a
contradiction with an excluded answer, make the status CONFLICTING: disclosed, none chosen. The router delivers only the
`deliverable_message_id` of a response that verifies (`delivery_decision(resp, keyring, hub=hub)`: the issuing hub
re-checks at delivery that the response is its latest for that input, that its task audit is the channel's latest, and
that the deliverable answer's custody still holds).

A repeated fault (`repeats.py`, `OVS-REP-001`, error) is an error-level fault whose signature already occurred in the task:
the same code about the same quoted phrase or claim words with the same figures, whoever repeats it and however trivially
reworded. It is never delivered or consolidated and is counted per agent; it never enters a task audit, so no clearance
changes.

The overseer pool (`pool.py`) plans how many overseer-agent instances review a batch: one by default; more when the review
units (a repeated-fault dossier counts twice) exceed the per-instance quota; at least two when any dossier has a repeated
fault (it goes to two independent instances, combined by `combine_verdicts`); never more than `max_instances` (default
4). Every instance is an `OverseerAgentRunner` from the pool's one loaded pack, deployed on the cheapest model tier;
instances never certify anything or change a status. Design section 19.

## The delivery policy

`delivery_policy.py` decides what the router may hand on for one deliverable and records why in a signed
`delivery_receipt/1.0`. The formal path: within `translation_budget_s` (240 s, the founder's limit, on an injectable
monotonic clock) every material eligible claim clean (translated, definitive, the release rule re-derived from the journal
and the signed result, no `OVS-TRN-*` finding naming it, the clearance actionable). Otherwise the fallback: the policy's
`OverseerPool` reviews the task through `hub.review_pool`, every verdict validated as in production; a verdict that
contradicts a signed result is rejected; each candidate's accuracy is the share of its material claims counted verdicts
examined with no fault pinned down, no check naming them and no signed refutation; the best acceptable candidate is
delivered only strictly above 0.90 (exact fractions), never one with a signed-refuted material claim while another has
none. The overseer stage has its own deadline (withheld by default). Labels other than FORMALLY CHECKED say "not formally
checked, not verified"; the payload is the journaled one, byte for byte. See `docs/DELIVERY.md`.

## Contained harness

`scripts/overseer/` (outside the package, never installed with it) tests all of this in a contained environment: the
tampering suite T1-T23 with its ground-truth manifest (on recorded STEM tasks too), the STEM fault-class probes, the
dossier export under an exported pack, the verdict scorer, the contained run that replays recorded arena rounds through
an audited hub and builds every overseer agent from a pack the exporter wrote, the mutation gate and the pytest plugin
that attaches an auditor to every channel. See
`scripts/overseer/README.md`; measured results are in `docs/OVERSEER_RESULTS.md`.
