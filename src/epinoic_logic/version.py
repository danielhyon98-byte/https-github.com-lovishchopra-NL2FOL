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

History of the argument-diagnosis bumps (named diagnostics, rules ``argdiag-1``). Every
change of this release ships under the versions below; the contract step sets them once:

* ENGINE_VERSION 0.5.0: the argument stage of ``verify`` (``engine.argument``): named
  diagnostics and the rule version that produced them (``argument_rules``) are part of a
  result and of its signature; the keywords ``diagnose`` and ``severity_cap`` are Python
  only; the release check refuses a named defect at warning or error (effective severity)
  and a result whose diagnosis was not computed by this build.
* POLICY_VERSION 2026.10-v5: the named-code table (``named.NAMED_CODES``, bound by digest)
  and the argument rules version in the policy manifest; release rules 8 and 9.
* TRANSLATOR_VERSION 0.5.0: premise roles in the translation record, the provider's
  asserted ``verified`` paths, claim and report diagnostics on outcomes and receipts, and
  the release assessment ``release-v2``.
* ARG_RULES_VERSION ``argdiag-1``: the rule version every named diagnostic carries
  (``named.NamedDiagnostic.rule_version``) and every diagnosed result records.

The five repair rounds and close rounds 1 and 2 of the argument diagnosis shipped under
these same versions (the release is not yet published); the build identity separated their
engine results, but a translation record of an earlier round read as current (INV7-2 in
docs/ARGUMENT_DIAGNOSTICS.md, section 7). Repair round 3 adds ARG-NS-003 and ST-STEP-003 to
the named-code table (bound by digest in the policy identity) and widens the eligibility
policy of 2026.10-v5: a claim that states its own reason ("A, so B") is an argument with no
supporting claim (``translate.eligibility``).

Close round 3 bumps the two versions whose rules changed under unchanged stamps, so that a
result of an earlier round of this release never reads as current:

* TRANSLATOR_VERSION 0.5.1: the translation-pipeline and claim-rule changes of the repair
  rounds and close rounds 1 to 3 (a translation record of an earlier round now reads as
  stale: ``outcome`` checks the translator version).
* ARG_RULES_VERSION ``argdiag-2``: the argument and evidence rules as the close rounds left
  them (EVD-SRC-001 no longer names a premise that restates a supposition the task sets). A
  result diagnosed under ``argdiag-1`` is refused by release rule 9 (another rule version),
  and the policy manifest, which binds the rules version, changes with it.

ENGINE_VERSION and POLICY_VERSION stay: no compilation, procedure, limit, allowlist or
eligibility rule changed in close round 3, and the build and policy identities already
separate every earlier engine result (``version.py`` and the rules version are bound into
them).

IR_VERSION stays 1.0: no field, operator or sort of the IR changes.
"""
IR_VERSION = "1.0"
ENGINE_VERSION = "0.5.0"
POLICY_VERSION = "2026.10-v5"
TRANSLATOR_VERSION = "0.5.1"
#: The version of the argument-diagnosis rules (``named``, ``engine.argument`` and the claim and report rule modules).
ARG_RULES_VERSION = "argdiag-2"
