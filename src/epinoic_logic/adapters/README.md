# adapters — specialist agents to structured reports

An adapter turns a specialist agent's output into an immutable `SpecialistReport`
(original text plus its hash, supplied texts, claim records with stable ids and
roles) and runs deterministic structural checks that produce `StructuralFinding`s.

- `base.py` — the `SpecialistAdapter` protocol, `AdapterError`, and a registry by agent id
  (`register`, `get_adapter`, `registered_ids`).
- `markdown.py` — the pre-segmentation rules every text parser shares: markdown furniture,
  code fences and pasted JSON blocks removed before segmentation (`strip_markup`), list
  markers as sentence ends, note sentences recognised one way (`is_note_sentence`: from-memory
  label, self-certification including the semantic rule of `is_self_certification` for a
  sentence whose subject is the answer itself, task-setting note), inline labels separated from
  a substantive sentence (`split_note_clauses`), and one quotation-mark discipline
  (`find_quotation_spans`: every double mark is one class, straight, curly, guillemet or low-9;
  single marks around two or more words; the one dangling mark of an unbalanced paragraph is
  set aside by `dangling_quote_offset` so the marks around it still pair, and
  `undelimited_quote_span` names the span it leaves unchecked).
- `sources.py` — the shared excerpt check (verbatim / normalized / trailing-punctuation /
  joined-span tolerance) used by every adapter's source-integrity findings.
- `generic_structured.py` — the integration contract for every specialist being
  built: accepts a report that is already structured JSON and checks source refs and
  claim links. New specialists should emit this format directly.
- `english_specialist/` — the worked example: a heuristic parser for PETAL-style
  analytical paragraphs (point, evidence quotations, device, interpretation, link),
  structural checks derived from the agent's own knowledge documents (quotation not
  in text, invented citation, from-memory quote, misattributed quotation, strand count,
  length, first person, spelling variety), and fixtures from its model essay including
  deliberately corrupted variants (`example1_texts.py` holds the verbatim Example 1 texts).
  The parser carries the hub-stated `agent_id` into the report unchanged, roles a
  self-certifying, narrated or JSON-shaped sentence `other` with no source reference
  wherever it stands, attributes a quotation to the supplied text the sentence names
  (author, surname, title, or the peer specialist of a relayed `peer:<task>` report) when
  several or none contain it, records an excerpt found in none of the supplied texts as an
  assumption listing every text searched, and folds claims beyond the report limit into a
  tail claim instead of raising.
- `fixtures_multi_subject.py` — Mathematics, Physics, Economics, Computer Science,
  History and English fixtures with expected statuses.

Rule sources cited in findings are the agent's working rules, not official IB rules.
