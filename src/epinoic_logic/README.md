# Package map

| Package | Role | Trust |
| --- | --- | --- |
| `ir/` | The restricted typed intermediate representation (data only) and canonical digests. | Untrusted input is parsed into it; it is never executed. |
| `engine/` | Validates, compiles and decides IR problems with Z3; binds and signs results. | Trusted core. Produces the only statuses the Overseer may rely on. |
| `translate/` | Turns specialist claims into IR via replaceable model providers, with deterministic eligibility, subject policy and grounding checks. | Model output is untrusted data until validated. |
| `adapters/` | Converts a specialist agent's output into immutable structured reports and runs structural checks. | Specialist text is untrusted input. |
| `service/`, `cli.py` | Authenticated HTTP boundary and command line. | Bearer auth, limits, signed results. |

Versions bound into every result are in `version.py`.
