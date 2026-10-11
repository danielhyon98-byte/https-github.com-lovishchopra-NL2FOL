# Epinoic AI — Logic Translator and Z3 Verification Engine

Proprietary. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.

This repository holds Epinoic AI's logic verification program: a restricted,
typed, versioned intermediate representation (IR); a deterministic validator and
compiler to Z3; consistency, entailment and counterexample procedures with
provenance-bound results; and a translation layer that turns structured claims
from subject-specialist agents into the IR, with deterministic grounding checks
tailored to the International Baccalaureate tutoring use case.

What a result means: a definitive verdict proves a property of the ENCODED
problem under its ENCODED premises. It never establishes that the premises are
factually true, that a natural-language claim was translated faithfully, or that
a literary or historical interpretation is correct. The program is not a
universal hallucination detector; it makes explicit what was checked, how, under
which assumptions, and what remains unverified.

## Status

See `docs/STATUS.md` for what is planned, implemented, tested and deployed.
Nothing in this repository is deployed.

## Layout

- `src/epinoic_logic/ir/` — IR schema v1 and canonical digests (data, never executed)
- `src/epinoic_logic/engine/` — statuses, validator, compiler, Z3 procedures, provenance, results
- `src/epinoic_logic/translate/` — claim contracts, eligibility, grounding checks, staged translation pipeline, replaceable model providers, advisory semantic-fidelity review
- `src/epinoic_logic/adapters/` — specialist-agent adapters (English specialist first)
- `src/epinoic_logic/service/` — authenticated HTTP service boundary
- `tests/` — pytest suite
- `docs/` — audit, plan, evidence, context pack

## Development

```
python -m venv .venv && .venv/bin/pip install -e ".[dev,service,providers]"
.venv/bin/pytest
```
