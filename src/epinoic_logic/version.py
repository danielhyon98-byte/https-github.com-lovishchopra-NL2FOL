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
"""
IR_VERSION = "1.0"
ENGINE_VERSION = "0.4.0"
POLICY_VERSION = "2026.10-v4"
TRANSLATOR_VERSION = "0.4.0"
