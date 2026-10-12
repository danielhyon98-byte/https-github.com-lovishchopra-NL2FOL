# Package map

| Package | Role | Trust |
| --- | --- | --- |
| `ir/` | The restricted typed intermediate representation (data only) and canonical digests. | Untrusted input is parsed into it; it is never executed. |
| `engine/` | Validates, compiles and decides IR problems with Z3; binds and signs results. | Trusted core. Produces the only statuses the Overseer may rely on. |
| `translate/` | Turns specialist claims into IR via replaceable model providers, with deterministic eligibility, subject policy and grounding checks. | Model output is untrusted data until validated. |
| `adapters/` | Converts a specialist agent's output into immutable structured reports and runs structural checks. | Specialist text is untrusted input. |
| `stem/` | Reads STEM answers (equations and prose in LaTeX, Unicode, ASCII and words) into one shared document and turns each stated relation into an IR problem the engine decides, or names it undecided (docs/STEM_DESIGN.md). | Agent text is data: a hand-written lexer and bounded parser, no evaluation of any string; problems leave as plain IR data and are validated again by the engine. |
| `service/`, `cli.py` | Authenticated HTTP boundary and command line. | Bearer auth, limits, signed results. |

Versions bound into every result are in `version.py`.
