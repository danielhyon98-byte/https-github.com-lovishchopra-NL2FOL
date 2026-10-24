"""Component versions bound into every result.

Bump ENGINE_VERSION on any change to compilation or procedures, POLICY_VERSION on
any change to limits, allowlist or eligibility rules, IR_VERSION on any schema
change, TRANSLATOR_VERSION on any change to the translation pipeline or prompts.
A result is only valid for the exact tuple that produced it; the binding digest in
``engine.results.Binding`` enforces this.

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
"""
IR_VERSION = "1.0"
ENGINE_VERSION = "0.3.0"
POLICY_VERSION = "2026.10-v3"
TRANSLATOR_VERSION = "0.3.0"
