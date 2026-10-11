# Third-party notices

## Z3 Theorem Prover (dependency)

This software uses the Z3 theorem prover through the `z3-solver` Python package.
Z3 is Copyright (c) Microsoft Corporation and is licensed under the MIT License.
Z3 is an existing solver, not an Epinoic AI invention; it is consumed as a
dependency and is not modified or redistributed by this repository.

## NL2FOL (design inspiration only; no code included)

The staged natural-language-to-logic translation approach in `epinoic_logic.translate`
is inspired by the method described in:

  Lovish Chopra et al., "NL2FOL: Translating Natural Language to First-Order Logic
  for Logical Fallacy Detection", arXiv:2405.02318 (2024).
  Reference implementation: https://github.com/lovishchopra/NL2FOL (MIT License,
  Copyright (c) 2025 Lovish Chopra).

No source code, prompt text, data or other copyrightable material from that
project is included in this repository. Only the published method (staged
decomposition of a claim into grounded entities and properties before
formalization, and counterexample-based explanation) informed the design, and
this repository's implementation is an independent, original work.

## Other Python dependencies

pydantic (MIT), FastAPI (MIT), uvicorn (BSD-3-Clause), httpx (BSD-3-Clause),
anthropic SDK (MIT), pytest (MIT), hypothesis (MPL-2.0). Each is used unmodified
as a dependency under its own licence.
