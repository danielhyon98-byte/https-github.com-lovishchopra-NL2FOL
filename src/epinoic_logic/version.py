"""Component versions bound into every result.

Bump ENGINE_VERSION on any change to compilation or procedures, POLICY_VERSION on
any change to limits, allowlist or eligibility rules, IR_VERSION on any schema
change, TRANSLATOR_VERSION on any change to the translation pipeline or prompts.
A result is only valid for the exact tuple that produced it; the binding digest in
``engine.results.Binding`` enforces this.

The tuple is no longer the only guard: every result also binds the immutable identity
of the build that produced it (``engine.identity``: a digest of the engine and IR
source, of the result and problem schemas and of the decision policy as data). A
version left unchanged by mistake therefore cannot make a result of another build look
current, but the rules above still apply, because the version strings are what a
reader of a result sees.

History of the STEM bumps (docs/STEM_DESIGN.md, section 18):

* ENGINE_VERSION 0.3.0: a result records the non-default ``Limits`` it was decided under
  (the named ``nonlinear`` pack policy), under its signature.
* POLICY_VERSION 2026.10-v3: named pack policies (``linear``, ``nonlinear``); subject
  aliases match on word boundaries; STEM aliases and the ``stem`` profile; eligibility
  rule 4 accepts a mathematical relation sign between operands (profiles that allow
  quantitative claims only) and counts superscript and subscript digits as numerals.
* TRANSLATOR_VERSION 0.3.0: the STEM encoding guidance in the subject profile text of the
  sciences, mathematics and Computer Science profiles. The pinned prompt ``translate_v1``
  is unchanged.

History of the review-fix bumps (external review of 12 October 2026):

* ENGINE_VERSION 0.4.0: the unsat core is always computed (``produce_unsat_core`` only
  decides whether the raw core record is serialised), so the dependency lists, the
  vacuity check (E108) and the circularity check (E112) never depend on an output
  option; E110 and E111 are no-verdict diagnostics only with source-linked evidence and
  otherwise the advisory W110 and W111 (the COUNTEREXAMPLE stands); results bind the
  build, schema and policy identity (``Versions``) and the non-default effective limits
  (``Binding.limits_digest``); ``engine.release`` states the current-policy release check.
* POLICY_VERSION 2026.10-v4: premise authority. A task or source grounding kind
  (``arithmetic_fact``, ``task_setting``, ``rubric_rule`` included) establishes a premise
  only when a check in this process verified it; otherwise the premise is an unverified
  dependency, never hidden. The integrity layer's joint limits are part of the policy.
* TRANSLATOR_VERSION 0.4.0: the translation-pipeline changes of the same review release,
  which ship under one translator version with the engine and policy changes above:
  exactness and stated precision read from the source wording (never from the solver),
  with semantic retries recorded apart from syntax repairs; task authority validated
  against the supplied texts and the task record (``TaskRecord``) on a premise's whole
  content (a relation that combines symbols only by a record that states it as a given:
  ``relation_in_source``); every reference of a grounding checked, with per-reference
  support; typed quantities; the coverage decision (whether a source asserts what an
  under-determined encoding leaves open, read only from clauses the assertion reader
  positively recognises as the writer's own statements) handed to the engine as an
  application record, so E110/E111 and W110/W111 are that decision; the
  evidence-carrying, bound fidelity review; the release assessment (``release-v1``); the
  prompts ``translate_v2`` and ``review_v2`` (``translate_v1`` and ``review_v1`` stay
  packaged unchanged).

History of the self-certification bumps (round-10 clearance c3, its hold remedy c3b and the follow-ups of its push checks):

* POLICY_VERSION 2026.11-v5: eligibility rule 0 (round-10 clearance c3, fe2e639 and the hold remedy c3b): a claim that
  is nothing but a self-report of a check, an engine or system result, a review, an approval, a score or the
  answer's own correctness (``selfcert.wholly_self_certification``, rules ``selfcert-1``) is NOT_ELIGIBLE_OTHER and never
  reaches the solver; the self-certification rules are bound into the policy identity
  (``engine.identity.policy_manifest`` "eligibility_self_certification": rules version and the digest of the lexicon
  and fold table), so a change to them without a version bump still makes every result of another build stale.
  D9/D10 (decision D35): the Geography and Language B branches ship under the same component versions; they add
  deterministic packs only (profiles, aliases, eligibility, prompts and the parser are unchanged).
* POLICY_VERSION 2026.11-v6 (c3e, the push check of 2be42c48): eligibility rule 0 reads the self-certification rules
  ``selfcert-2`` (own verdicts read by their frame: a check, an approval or an agreement of this answer by any party, a fault
  nobody would find, a quality an assessor would see, a pipeline's success code; misspelt check compounds and status sentences;
  letter transforms composed with misspelling; correction-pair labels, glosses and worked checks read as boundary (b)), and
  ``selfcert.rules_digest`` now binds the rule's code (every module of ``epinoic_logic.selfcert``, by name and content) besides
  its lexicon and fold table, so a code-only change to rule 0 changes the policy identity. Contract 0.6 to 0.7.
* POLICY_VERSION 2026.11-v7 (c3f and c3g, the push checks of a9129c78 and 08c4a36b): eligibility rule 0 reads the
  self-certification rules ``selfcert-3``. Read as own verdicts, gated: an own-correctness verdict or an evaluator's approval
  beside a token computation ("The calculations are all correct: 2 × 21 = 42.", "Approved by the examiner: 2 × 3 = 6."), and a
  verdict whose scope is wider than the computation it stands beside; a tick after a cross on the answer's own value ("✗ x = 3 ✓
  x = 4"); a tick or approval on language use outside a marking or feedback task ("✓ Correct use of the subjunctive: «espero que
  vengas»."); agreement of the answer's figures with an unnamed source that states no value ("Every figure here matches the
  census.", "Las cifras coinciden con el censo."); the writer's confirmation of its own accuracy ("I can confirm this answer is
  accurate."); approval idioms with any object ("signed this response off", "dieron el visto bueno a", "the green light") and
  approvals received; a check the answer has had or undergone, read as an agentless passive; delivery to the reader as own scope;
  an evaluator credited in an apposition or a relative clause, a pass credited to an evaluator, an accuracy established by a
  tester; impersonal no-fault judgements, assessors' idioms, a redo that came out the same, nothing found to correct, a readiness
  verdict, an assessor's found quality, an award reported, a quoted word predicated of this answer in any language, a question tag,
  a question answered by a quantifier, a solver's verdict asked and answered; the answer named by its genre noun, determiners
  varying freely, a numbered range of the answer's own items; misspelt check words in more forms (several words of a sentence
  misspelt or spelt as they sound, the b/v confusion, words run together, a misspelt label key: "Evrey step hear was cheked
  twise.", "Todo esta berificado."). Own verdicts are read in every clause and every window of a sentence of any length, after a
  question and in a joined clause, so the reading never fails open on length. Read as free (boundary (b) or task text): a worked
  check under a neutral key or heading ("Check:", "Comprobación:", "Prueba:", "Checking the answer:") or the writer's own check of
  the computation shown, and a verdict whose scope is the one computation shown ("This calculation checks out: 8 × 9 = 72.");
  agreement with a NAMED source or a stated value ("The ONS confirmed the figures.", "The figures match the census figure of 4.2
  million."); agreement with a named model of the subject ("This is consistent with the Bohr model."); a restated question with
  its mark allocation ("Question 5 [4 marks]: Solve 2x + 3 = 11."); a check stated only as possible ("The values can be confirmed
  with a calculator."); an outer denial of a no-fault claim ("It is not true that nobody found an error here."); a subject-matter
  event named by its place or date; a criterion's demand; glosses in French, German and Spanish word-first forms; correction pairs
  written with emphasis, guillemets, a corrected-form key or the rejected form in brackets; a tick on language use in a marking
  or feedback task. Every word-count line, in every language and form, stays gated as a self-report under decision D7 ("Número
  de palabras: 42" as "Palabras: 25"). The policy identity binds the import closure of the reader inside the package, rule 0's
  call site and the marking context included (``selfcert.rules_closure``). Contract 0.7 to 0.8.
* POLICY_VERSION 2026.11-v8 (c3h, the push check of 67bc64ec): eligibility rule 0 reads the self-certification rules
  ``selfcert-4``. They fail closed where ``selfcert-3`` freed own-scope text or stopped reading: the exemptions it added that
  freed such text are reverted to the reading of 08c4a36b, and its bounds that failed open now read everything. Read as own
  verdicts, gated again: a check of the answer's own scope stated as possible ("Everything in this response can be verified.",
  "Every figure in this answer can be confirmed."; the possibility frame is reverted, so "The values can be confirmed with a
  calculator." is withheld again, an over-block that fails closed); a correction pair written with labels ("Wrong: x = 3. Right:
  x = 4.", "Wrong: 1918. Right: 1919.", "Mal: x = 5. Bien: x = 7."; the corrected-form key exemption is removed whole, so a label
  pair of language prose is withheld again too); agreement of the answer's figures with a source that a year, a date or a number
  alone qualifies ("The values in this answer agree with the 2022 dataset.", "Todas las cifras coinciden con la encuesta de
  2019.", "the March 2022 dataset", "the FY2019 report"): a year, a date, a month, a quarter or a fiscal year never names a source
  and is never a value the source states (decision D-a), while a named source or a stated value stays free ("The ONS confirmed
  the figures.", "The figures match the census figure of 4.2 million."). Own verdicts are read in every window of a sentence of
  any length as 08c4a36b read them: a later window is read by its own first words and is never masked whole as the words of a
  reporter that opens the sentence, and a report verb that opens the sentence is no head of a relative clause, so ", which a
  second agent checked line by line," is read at every length. The evaluator pieces of a text and the scope variants of a
  sentence are read in full, with no count or length cap (the cap of 64 pieces and the 200,000-character bounds are removed).
  Every word-count line reads as decision D7 reads "Palabras: 25", whatever sets its key off from its value (a colon, a dash,
  "=", "≈", "~") and however its key is written or abbreviated ("Nº de palabras: 87", "Words used — 312", "Cuenta de palabras:
  198", "Count of words: 199"; decision D-e, D7 itself unchanged). A party's check placed in the subject's past by a date
  ("confirmed by the 1921 census") and the other readings of ``selfcert-3`` are unchanged. The Geography and Language B
  corrections of the same run change deterministic packs only (decision D35) and carry no version reason of their own.
  Contract 0.8 to 0.9.

Argument diagnostics (ported onto this tree; docs/ARGUMENT_DIAGNOSTICS.md, section "Port onto the
integrated translator"):

* ARG_RULES_VERSION ``argdiag-2``: the rule version every named diagnostic carries
  (``named.NamedDiagnostic.rule_version``) and every diagnosed result records
  (``VerificationResult.argument_rules``). The port leaves the four component versions as they
  are: the integration kit's compatibility record pins them, and the build and policy identities
  (``engine.identity``, which bind ``named.py``, ``lexis.py``, the rules version and the
  named-code table by digest) already separate a diagnosed result from one of an earlier build.
  Whether the release that ships the diagnostics bumps them is a decision of the final
  integration (docs/handoff).
"""
IR_VERSION = "1.0"
ENGINE_VERSION = "0.4.0"
POLICY_VERSION = "2026.11-v8"
TRANSLATOR_VERSION = "0.4.0"
#: The version of the argument-diagnosis rules (``named``, ``engine.argument`` and the claim and report rule modules).
ARG_RULES_VERSION = "argdiag-2"
