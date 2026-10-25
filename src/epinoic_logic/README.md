# Package map

| Package | Role | Trust |
| --- | --- | --- |
| `ir/` | The restricted typed intermediate representation (data only) and canonical digests. | Untrusted input is parsed into it; it is never executed. |
| `engine/` | Validates, compiles and decides IR problems with Z3; binds and signs results. | Trusted core. Produces the only statuses the Overseer may rely on. |
| `translate/` | Turns specialist claims into IR via replaceable model providers, with deterministic eligibility, subject policy and grounding checks. A check confers task or source authority only on a premise's whole content (a relation only when a record states it), and a source asserts a figure only in a clause the reader positively recognises as the writer's own statement; every source is read for an omitted figure (the claim, its supporting claims, the supplied texts, the task record), and a figure stated as rounded grounds its exact transcription and the interval of its stated tolerance; a figure is rounded only by a cue written against it or as the result of a calculation that ends at its '='. | Model output is untrusted data until validated; a grounding label confers nothing. |
| `adapters/` | Converts a specialist agent's output into immutable structured reports and runs structural checks. | Specialist text is untrusted input. |
| `stem/` | Reads STEM answers (equations and prose in LaTeX, Unicode, ASCII and words) into one shared document and turns each stated relation into an IR problem the engine decides, or names it undecided (docs/STEM_DESIGN.md). | Agent text is data: a hand-written lexer and bounded parser, no evaluation of any string; problems leave as plain IR data and are validated again by the engine. |
| `named.py`, `lexis.py` | The shared contract of the argument diagnosis (rules `argdiag-2`). `named.py` holds the named-diagnostic record, the closed code table, the 28 canonical defect labels, and the caps, display and release reading. `lexis.py` is the linear token reader the rules share: tokens, a light stemmer, negation read by parity, and cue tables, with no regular expressions. | Diagnostics are advisory data. They never change a status and can only make a result less releasable. Neither module imports z3 or the engine, so the layers above the engine work without Z3 and read "not computed" for the engine layer. |
| `service/`, `cli.py` | Authenticated HTTP boundary and command line. | Bearer auth, limits, signed results. A signature covers its key id. The command line signs only with a key of at least 16 bytes, the service's floor, given in a file (`--signing-key-file`) or an environment variable (`--signing-key-env`); `--signing-key-hex` puts it in the process list. |

Versions bound into every result are in `version.py`; beside them every result binds the immutable identity of
the build that produced it (`engine/identity.py`: digests of the engine and IR source and of `named.py` and `lexis.py`, of
the schemas, and of the decision policy, which binds the argument rules version and the named-code table) and any non-default validation limits, so a result of an earlier release stays inspectable but is
never current-policy evidence.
