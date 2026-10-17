# Package map

| Package | Role | Trust |
| --- | --- | --- |
| `ir/` | The restricted typed intermediate representation (data only) and canonical digests. | Untrusted input is parsed into it; it is never executed. |
| `engine/` | Validates, compiles and decides IR problems with Z3; binds and signs results. | Trusted core. Produces the only statuses the Overseer may rely on. |
| `translate/` | Turns specialist claims into IR via replaceable model providers, with deterministic eligibility, subject policy and grounding checks. A check confers task or source authority only on a premise's whole content (a relation only when a record states it), and a source asserts a figure only in a clause the reader positively recognises as the writer's own statement; every source is read for an omitted figure (the claim, its supporting claims, the supplied texts, the task record), and a figure stated as rounded grounds its exact transcription and the interval of its stated tolerance; a figure is rounded only by a cue written against it or as the result of a calculation that ends at its '='. | Model output is untrusted data until validated; a grounding label confers nothing. |
| `adapters/` | Converts a specialist agent's output into immutable structured reports and runs structural checks. | Specialist text is untrusted input. |
| `stem/` | Reads STEM answers (equations and prose in LaTeX, Unicode, ASCII and words) into one shared document and turns each stated relation into an IR problem the engine decides, or names it undecided (docs/STEM_DESIGN.md). | Agent text is data: a hand-written lexer and bounded parser, no evaluation of any string; problems leave as plain IR data and are validated again by the engine. |
| `service/`, `cli.py` | Authenticated HTTP boundary and command line. | Bearer auth, limits, signed results. |

Versions bound into every result are in `version.py`; beside them every result binds the immutable identity of
the build that produced it (`engine/identity.py`: digests of the engine and IR source, of the schemas and of the
decision policy) and any non-default validation limits, so a result of an earlier release stays inspectable but is
never current-policy evidence.
