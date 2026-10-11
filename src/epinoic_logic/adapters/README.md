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
  accepted", passing the answer; the structural rule decides by the clause's shape, not by listed
  phrases: a subject that refers to the answer's own items, a determiner, "every", "each of the",
  "all of the", "these", "my", "the", with up to two modifiers before an item noun ("every mileage
  figure above", "each of the mileage figures given above", "these quotations", "every quoted line
  above"), or the answer itself ("my reading"), followed by a copula and a checking participle
  ("has been verified", "has been formally verified") or an accuracy or reliability adjective ("are
  exact", "are reliable"), or by "need no further checking", "need not be checked"; "Nothing in this
  answer needs checking"; items "matched word for word" or checked "against the supplied" text; a
  certifying lead, "As verified,", "As checked above,"; and the router, Overseer, verifier, checker
  or any other piece of the infrastructure as the agent that passed the answer or "every item". The
  limits that keep arguments arguments: a check credited to another agent ("my reading is confirmed
  by the final stanza", "checked by the Registrar General") or one that goes on to argue ("verified in
  later scholarship") is not a self-report, an adjective must close the clause unless the items are
  anchored in the answer ("these figures are reliable because ..." and "the census figures are
  reliable" weigh a source), items in general need a checking verb ("every figure in the sculpture is
  exact"), a definite subject needs the present or perfect ("the figures were checked" narrates), and
  a dated item keeps the semantic and structural rules off ("Every date given above was checked against
  the 1929 census"), though not a certifying lead or "need no further checking"; answers are cached per
  sentence, and the structural patterns read a pathological sentence in linear time),
  notes on how the answer was composed (`is_provenance_note`: the answer, its setting, its judgement
  or a received report as subject and authorship or provenance as the whole predicate, "The
  historical setting is my own addition, not part of that paragraph.", "The English specialist's
  paragraph is from the hub", read on what is left once label clauses are set aside, so a note on
  every branch and outside the channel's word count; "The judgement is my own, and it shows that ..."
  stays substantive), inline labels separated from a substantive sentence
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
  the sentence names several texts, the English, History and generic parsers pass the sentence and the
  quotation is credited to the text whose possessive governs it, else the speaker of the
  nearest reporting clause, else the text named nearest before it (`governing_document`), never
  to none; otherwise it is credited to no text and the assumption `quotation with no supplied
  text to check it against: "..."` is recorded, which the core pack reports as `CORE-SRC-003`.
  A quotation whose sentence credits a source that is not a supplied text while its words are a
  relayed colleague's own prose ("Hardy's speaker himself admits that ...", "The poem says ...")
  keeps the colleague's report as its source and records the credit as an assumption (`CORE-SRC-005`;
  the channel's `INT-REQ-015`); `quotation_credit` names who a sentence credits a quotation to,
  `credited_agents` the specialists a text credits with a view, `peer_prose_span` whether an excerpt
  is a colleague's own prose rather than a quotation the colleague makes, and `is_peer_text` a
  relayed report.
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
  light`, `Read against`: `LINK_LEADS`) and, in a single-paragraph answer, the closing sentence
  that draws the conclusion, quoting or not, as the material `link`: a claim drawn over the
  evidence ("... suggest that ..."), a conclusion marker anywhere in it ("Direct speech thus
  supplies ...", "..., so that admiration and laughter remain held together", "..., so the
  argument moves from persuasion to urgency"; ", so much" is a degree word) or a restatement of
  the point's terms (three shared content words, half the sentence's own); after a signposted link
  only the quotation-free claim over the evidence is a second link, so a closing caveat ("The poem
  never mentions the war, so this reading rests on ...") stays supporting; ends a sentence at a
  sentence-final possessive or contraction ("... matches the enemy's. The key word ..."), which is
  not a one-letter initial; reads a CR-only paragraph break as a paragraph break, raises `ES-SRC-003` only for a disclosure (an
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
- `fixtures_multi_subject.py` — Mathematics, Physics, Economics, Computer Science,
  History and English fixtures with expected statuses.

Rule sources cited in findings are the agent's working rules, not official IB rules.
