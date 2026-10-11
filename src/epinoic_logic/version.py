"""Component versions bound into every result.

Bump ENGINE_VERSION on any change to compilation or procedures, POLICY_VERSION on
any change to limits, allowlist or eligibility rules, IR_VERSION on any schema
change, TRANSLATOR_VERSION on any change to the translation pipeline or prompts.
A result is only valid for the exact tuple that produced it; the binding digest in
``engine.results.Binding`` enforces this.
"""
IR_VERSION = "1.0"
ENGINE_VERSION = "0.1.0"
POLICY_VERSION = "2026.10-v1"
TRANSLATOR_VERSION = "0.1.0"
