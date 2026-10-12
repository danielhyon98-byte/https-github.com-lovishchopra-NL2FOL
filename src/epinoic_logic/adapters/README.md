# adapters — specialist agents to structured reports

An adapter turns a specialist agent's output into an immutable `SpecialistReport`
(original text plus its hash, supplied texts, claim records with stable ids and
roles) and runs deterministic structural checks that produce `StructuralFinding`s.

- `base.py` — the `SpecialistAdapter` protocol, `AdapterError`, and a registry by agent id
  (`register`, `get_adapter`, `registered_ids`).
- `markdown.py` — the pre-segmentation rules every text parser shares: markdown furniture,
  code fences and pasted JSON blocks removed before segmentation (`strip_markup`; CRLF and a
  lone CR are line breaks), a JSON span glued to prose located wherever it stands
  (`find_json_spans`, `mask_json_spans`, `split_json_spans`: parsers cut sentences at it and its
  strings are never quotations; brackets are matched in one linear pass per text and the answer
  is cached, so thousands of braces cost milliseconds, and `bracket_match_ends` gives the
  History splitter's typed bracket matching in the same linear time), list markers as sentence
  ends, note sentences recognised one way (`is_note_sentence`: a sentence whose core is empty
  once its labels are set aside, read with its quotations masked by `mask_quotations`, so a
  colleague's from-memory label quoted by the writer is quotation and counts toward a word
  bound; a label word inside a substantive sentence, "recalls the scene from memory, which
  ...", "is illustrative of how ...", never makes it a note), disclaimers told apart from
  self-certifications (`is_self_certification`: a positive check only, so "should be checked
  before they are cited", "have not been verified", "must be verified" and "unverified" are
  notes with no self-report; the semantic rule covers a sentence about the answer or its items,
  "every figure", "all of these figures", "the figures here", "every quotation above", with a
  checking predicate, "can be relied upon", "appears verbatim", "no errors were found" or an
  accuracy adjective right after that subject, the writer narrating a check, "I have checked",
  "I verified each figure", on every branch, and the infrastructure, "Z3 proved", "the hub has
  accepted", passing the answer), inline labels separated from a substantive sentence
  (`split_note_clauses`: parentheticals, clauses before or after a semicolon or dash, a
  sentence-initial "From memory,", a comma-bounded ", from memory" with the figure that follows
  kept, a trailing appositive or concessive label, ", a figure I give from memory", ", though
  this date is from memory", ", so check your notes", and a closing "from memory" in a dated
  sentence; a label is a clause carrying a label phrase, `LABEL_PHRASE_RE`, with nothing but
  label filler left or "from memory" as its whole predicate; each distinct label recorded once),
  and one quotation-mark discipline
  (`find_quotation_spans`: every double mark is one class, straight, curly, guillemet or low-9;
  two adjacent double marks that together open or close a quotation are one nested mark, so
  dialogue copied with its own marks inside the writer's is read as the dialogue pieces; single
  marks around two or more words, paired by context: an apostrophe inside a word, don't,
  Scrooge's, Ne'er, an aphetic 'tis or 'Change and a plural possessive followed by more of the
  sentence are not marks, so a single-quoted quotation with a contraction is read, checked and
  attributed; the one dangling mark of an unbalanced paragraph is set aside
  by `dangling_quote_offset` so the marks around it still pair, `undelimited_quote_span` names
  the span it leaves unchecked, and `undelimited_quote_spans` adds every pair of an unbalanced
  paragraph whose marks contradict their context, so the writer's prose between quotations is
  neither delivered as a quotation nor reported as invented).
- `sources.py` — the shared excerpt check (verbatim / normalized / trailing-punctuation /
  joined-span tolerance; a form difference such as an initial capital, a verse line-break
  mark, diacritics or a long elision is a located status, never "not found") used by every
  adapter's source-integrity findings, and the one attribution rule every parser applies
  (`attribute_excerpt`): the text that holds the words wins; a quotation held by no text is
  credited to the one text its sentence names, whether or not that text holds the words; when
  the sentence names several texts, the English and generic parsers pass the sentence and the
  quotation is credited to the text whose possessive governs it, else the speaker of the
  nearest reporting clause, else the text named nearest before it (`governing_document`), never
  to none; otherwise it is credited to no text and the assumption `quotation with no supplied
  text to check it against: "..."` is recorded, which the core pack reports as `CORE-SRC-003`.
  A text is never credited for being supplied first. Answers are cached per excerpt and document
  text (a bounded LRU), so a parse and its checks never locate one excerpt in one document twice.
- `generic_structured.py` — the integration contract for every specialist being
  built: accepts a report that is already structured JSON and checks source refs and
  claim links. New specialists should emit this format directly. Every located form
  difference of the shared check (long elision included) is the inexact warning code
  (`GEN-SRC-003`, `ES-SRC-006` for the English pack), never the not-found error.
- `english_specialist/` — the worked example: a heuristic parser for PETAL-style
  analytical paragraphs (point, evidence quotations, device, interpretation, link),
  structural checks derived from the agent's own knowledge documents (quotation not
  in text, invented citation, from-memory quote, misattributed quotation, strand count,
  length, first person, spelling variety), and fixtures from its model essay including
  deliberately corrupted variants (`example1_texts.py` holds the verbatim Example 1 texts).
  The parser carries the hub-stated `agent_id` into the report unchanged, roles a
  self-certifying, narrated or JSON-shaped sentence `other` with no source reference
  wherever it stands, roles a quotation-free sentence that is nothing but a note about the
  text `other` wherever it stands (so a disclaimer is never the paragraph's point; a block of
  notes of any length is meta), keeps a substantive sentence that carries the label inline
  and records the label as an assumption, roles a sentence that opens with a link signpost
  or lead (`Thus`, `Ultimately`, `Read together`, `Taken together`, `Together`, `In this
  light`, `Read against`: `LINK_LEADS`) and, in a single-paragraph answer, the closing claim
  drawn over the evidence ("... suggest that ...") as the material `link`, reads a CR-only
  paragraph break as a paragraph break, raises `ES-SRC-003` only for a disclosure (an
  unlocated quotation, a quotation word in the writer's own words, or the method's own
  label), not for "from memory" used in the argument, segments the prose before and after a pasted JSON
  span as prose (the span is one `other` sentence, and the quotations after it are grounded),
  attributes a quotation by the shared rule (the supplied text that holds it; the text the
  sentence names, by author, surname, title, or the peer specialist of a relayed
  `peer:<task>` report, when several or none hold it; when the sentence names none, the one
  literary text under analysis; otherwise no text, recorded for `CORE-SRC-003`), records an
  excerpt found in none of the supplied texts as an assumption listing every text searched,
  reports a quotation differing only in diacritics as a form warning (`ES-SRC-006`), reports
  an elided quotation whose fragments span more than the elision window as
  a form warning (`ES-SRC-006`, as the channel's INT-REQ-010) rather than an invented
  quotation, and folds claims beyond the report limit into a tail claim instead of raising,
  interpretation before evidence and evidence before material claims, carrying the source
  references of folded evidence on the tail claim so the hub still checks those quotations and
  naming in an unresolved issue how many claims and quotations were merged.
- `stem_specialist/` — `StemTextParser`, the parser of the three STEM branches (`sciences`,
  `mathematics`, `computer_science`; docs/STEM_DESIGN.md, section 9). It reads the same memoised
  `stem.document.StemDocument` as `branches/stem_pack.StemPack` (the channel passes it the request
  text: `accepts_request_text`), so claim ids and planned check ids cannot diverge. Claims are the
  document's statements (a sentence, a derivation line, a display row, a list item, a code block,
  a table, a data line), each an offset substring of the original answer cut to the contract's
  4,000 characters, with ids `s<paragraph>.<n>` (`m<paragraph>.<n>` in mathematics,
  `c<paragraph>.<n>` in Computer Science, so two STEM branches never share a claim id on one
  task); `original_response` is verbatim and nothing vanishes (statements beyond 512 merge into
  `s.tail` with the unresolved-issue text the channel turns into INT-REQ-013). Roles follow design
  section 9.2 with no new role: notes and self-certifications `other` (the shared
  `is_note_sentence` / `is_self_certification`; a statement that carries maths is never a note for
  having no words), heading lines `structural`, Given and data lines and values bound to symbols
  `evidence`/`arithmetic`, a law with no numerals `evidence`/`factual`, steps `quantitative`
  (supporting), the last chain-bearing statement of each part and a prose value after a result cue
  `quantitative` and material, code blocks material `point`s, and in an explanation paragraph the
  point, `link`s and `analysis`; assumptions ("neglecting air resistance") are copied to the
  report. Quotations are read on the quotation view (code masked; an inch mark `12"` is no
  quotation mark) and credited by the shared `attribute_excerpt`, exactly as the generic parser
  credits them. A claim whose relations the STEM pack decides records "numeric relations of this
  statement are decided by the STEM pack checks <ids>". An empty answer raises `AdapterError`; a
  code-only answer yields claims; adversarial input never raises out of the parser.
- `fixtures_multi_subject.py` — Mathematics, Physics, Economics, Computer Science,
  History and English fixtures with expected statuses.

Rule sources cited in findings are the agent's working rules, not official IB rules.
