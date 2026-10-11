# ir — intermediate representation 1.0

`schema.py` defines the only language the solver ever sees: three sorts (Bool, Int,
Real), 24 allowlisted operators, numerals written as exact text (`"7"`, `"-3/2"`,
`"0.25"`), symbols with optional natural-language glosses, premises and an optional
conclusion, and `Grounding` metadata saying where each premise comes from
(quotation, supplied text, task setting, rubric rule, arithmetic fact, specialist
inference, assumption) with a certainty level and a `verified` flag that only
deterministic grounding checks may set. `Limits` bounds symbols, premises, nodes,
depth, arity and numeral length, and gates nonlinear terms and division policy.

`canonical.py` serializes a problem deterministically and hashes it. Any change,
including a changed gloss, changes the digest, which is how old results are
prevented from being reused for a modified representation.

Unknown operators, unapproved fields, bad literals and bad identifiers are rejected
at parse time; the schema forbids extra fields everywhere.
