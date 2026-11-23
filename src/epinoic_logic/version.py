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

History of the self-certification bump (round-10 clearance c3 and its hold remedy c3b):

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
POLICY_VERSION = "2026.11-v6"
TRANSLATOR_VERSION = "0.4.0"
#: The version of the argument-diagnosis rules (``named``, ``engine.argument`` and the claim and report rule modules).
ARG_RULES_VERSION = "argdiag-2"
