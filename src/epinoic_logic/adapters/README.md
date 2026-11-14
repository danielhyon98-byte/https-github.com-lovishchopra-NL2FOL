# adapters — specialist agents to structured reports

An adapter turns a specialist agent's output into an immutable `SpecialistReport`
(original text plus its hash, supplied texts, claim records with stable ids and
roles) and runs deterministic structural checks that produce `StructuralFinding`s.

- `base.py` — the `SpecialistAdapter` protocol, `AdapterError`, and a registry by agent id
  (`register`, `get_adapter`, `registered_ids`).
- `markdown.py` — the pre-segmentation rules every text parser shares: markdown furniture,
  code fences and pasted JSON blocks removed before segmentation (`strip_markup`; CRLF and a
  lone CR are line breaks; a fence with no language or a text or markdown tag whose body is prose,
  at least 20 words and two sentence ends with no JSON shape, keeps its body, so an answer wrapped
  in a fence is counted as the answer by the channel as the English parser reads it, while code, a
  receipt in a fence tagged `json` and a short decoration are removed whole), a JSON span glued to prose located wherever it stands
  (`find_json_spans`, `mask_json_spans`, `split_json_spans`: parsers cut sentences at it and its
  strings are never quotations; brackets are matched in one linear pass per text and the answer
  is cached, so thousands of braces cost milliseconds, and `bracket_match_ends` gives the
  History splitter's typed bracket matching in the same linear time), list markers as sentence
  ends, note sentences recognised one way (`is_note_sentence`: a sentence whose core is empty
  once its labels are set aside, read with its quotations masked by `mask_quotations`, so a
  colleague's from-memory label quoted by the writer is quotation and counts toward a word
  bound; a label word inside a substantive sentence, "recalls the scene from memory, which
  ...", "is illustrative of how ...", never makes it a note; a sentence opened by a note lead,
  `NOTE_LEAD_RE`: "Note:", "Note on ...:", "N.B.", "NB:", "Next step:", "Confidence:", "Limit:",
  "Caveat:", is a note as a whole on the English, History and generic branches and outside the
  channel's word and paragraph counts, so hi-t13's closing "Note: Paper 2 essays are marked out of 15
  ..." is no second body paragraph and counts toward no bound, while "Note that ..." with no colon
  stays the argument's own signpost and "Limitation:" an evaluation point; a paragraph opened by a
  bare lead, `BARE_NOTE_LEAD_RE` / `opens_note_paragraph` ("Note:", "N.B.", "Next step:", "Limit:",
  "Caveat:"; not "Note on ...:"), is a note as a whole on the generic branch as on the History
  branch, and the generic branch also roles a caveat about the answer's own sources
  (`history_specialist.parser.is_source_caveat`: "My sources do not confirm the exact total, ...")
  as a note), disclaimers told apart from
  self-certifications (`is_self_certification`; a verification label, `verification_label`: "Verified: ...",
  "... (verified).", "[verified] ...", "..., as formally verified.", a sentence that is nothing but the label being
  a self-certification and a label on content leaving the content a claim; a positive check only, so "should be checked
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
  certifying lead, "As verified,", "As checked above,"; items named with the source they were taken
  from, "each quotation of the History specialist above", "all quotations from the History specialist
  above", "the quotations of the poem above", "my quotations of both texts", "the quotations from the
  History report", "every figure taken from the History specialist" (a source is a colleague, a
  qualified report, "the History report", or, for quotations only, the supplied text), with a checking
  participle, an accuracy adjective (anchored items, quotations, or items taken by a quoting participle:
  "the figures of the History report are accurate" may be the writer vouching for a source and is not
  one) or a reproduction-fidelity predicate ("reproduced exactly", "quoted verbatim", "copied word for
  word", and "The History specialist's words are quoted above exactly", the predicate closing the clause
  or saying how the words stand, so "The speaker's words are quoted exactly by Love." is the poem's own
  quoting and "... reproduced exactly in the final line" a repetition in the text); compliance self-reports, a
  sentence that opens on the answer, its quotations or the request's items and says nothing but that
  the answer satisfies the request ("The paragraph is under the word limit.", "This paragraph stays
  within the 300-word limit and answers every part of the question.", "The answer meets every
  constraint in the request.", "This response complies with the router's instructions.", "Both request
  items are addressed above.", "All quotations follow the 1633 spelling of the supplied text."), decided
  before the dated-item guard since such numbers date nothing, and word-count lines ("Word count: 258.",
  "258 words.", "(about 250 words)", "The paragraph has 320 words."); and the router, Overseer, verifier, checker
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
  paragraph is from the hub"; a received report named anaphorically and labelling its items, "That
  account marks its figures as "from memory", so they are reported unverified." (a quotation whose
  words are nothing but a label, "from memory", "unverified", "approximate", is read as the label it
  is: `is_label_quotation`), "That account labels its figures from memory"; a report's items or the
  answer's located items with a verification status, "The History specialist's figures are from memory",
  "Its figures are marked "from memory""; where the answer's items come from, the supplied text, a
  received report, the hub or memory, "Quotations are from the supplied extract", "The figures above
  come from the History specialist's paragraph, not from the poem."; and "The word count is
  approximate."; closing clauses that are notes themselves, ", not from the poem", ", so they are
  reported unverified", "I have not checked them", are set aside first; read on what is left once
  label clauses are set aside, so a note on every branch and outside the channel's word count; "The
  judgement is my own, and it shows that ...", "The census figures are approximate" and "The figures are
  from the 1851 census" stay substantive), a colleague's reported view (`is_peer_attribution`: a
  sentence whose subject is a colleague's view, "The History specialist states that ...", "The History
  specialist's reading ...", the same shape as the History parser's attribution rule, or the colleague as the
  subject of a verb reporting what it gave, "The History specialist gives about 8 million arrivals", "... dates
  the sonnet to 1886", "... also puts the figure at ..." (verbs that are also nouns, "dates", "counts", "quotes",
  are read only without the possessive, so "The History specialist's dates are from memory" stays a note); a colleague cited
  mid-way, "..., bearing out the History specialist's claim", is the writer's own), inline labels separated from a substantive sentence
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
  neither delivered as a quotation nor reported as invented). The parsers read the quotations of a
  claim with `parser_quotation_spans`: every quoted span except the writer's own words, a correction
  or a suggestion in a marking, feedback, correction or editing task (`_span_roles`: '"una mujer
  muy simpático" → "una mujer muy simpática"', '"x" should be "y"', a "Model:" label); in any
  other task every span, read without the roles, so an altered quotation framed that way is still
  checked (integration gate 1, end-to-end B5). A mention stays a quotation claim. A mention of words
  the text lacks ('without "like" or "as"', 'has no "like"', 'never uses "I"'), read so by both readers
  (`absent_word_mentions`: the role reader and the absence frames `ABSENT_BEFORE_RE` /
  `absent_mentions` that the core pack, the channel and the Overseer read mentions by, moved here
  from `branches/packs.py` unchanged; a span of at most three words, so a longer span joined to a
  mention by "and" stays credited), is credited to no text when no supplied text holds it (the
  shared rule, `sources.attribute_excerpt`; end-to-end B6); 'never says "x"' (an attribution, close
  round 3 INV-QR-1), a quoted word under a naming frame ('the conjunction "But"') and a mention one
  reader alone reads are credited and checked as before. Each text parser's `parse_response` reads in the task type it is given
  (`in_quotation_task`) and remembers it for the report it returns (`parse_task_of`, keyed by the
  report's content, so a copy such as the overseer's journaled one finds it too), so the branch's
  packs read the same report under the same task; a report delivered as a mapping has none, and its
  own `task_type` field never widens the roles (repair round 5, INV-QROLE-1). The
  shared readers are linear on hostile input (integration gate 1, each with an equality test
  against the old reading): a sentence's end is read back from the end (`_terminal_len`), the
  trailing "from memory" label and the parentheticals of the note-clause splitter start only where
  no blank precedes, and emphasis markers are removed in one pass (`strip_emphasis`, which gives
  `EMPHASIS_RE.sub(r"\2", text)` character for character; `EMPHASIS_RE` itself is unchanged).
  Integration gate 2 made the rest of the shared readers linear the same way, each held to its old
  reading by an equality test (`tests/adapters/test_integration_gate2_parsers.py`): fences are paired
  in one pass (`fence_blocks`: a lazy pattern read to the end of the text from every opener with no
  closer), and the pasted JSON blocks likewise (`_json_block_spans`); a sentence's quotation spans are
  read once per text however long (`_long_quotation_spans`); the closing of an accuracy adjective
  (`_SELF_CLOSING_RE`) and the synthesis's proof and verdict labels (`_SYNTH_PROOF_LABEL_RE`,
  `_SYNTH_VERDICT_LABEL_RE`) read their blank runs once (adjacent runs around an optional comma or stop:
  0.2 s for a label followed by 4,000 blanks). The combinator's own verdict on what it
  wrote ("The answer is correct.", "(signed engine result)", "Overseer verdict: pass.", "Correct: <claim>",
  "<claim>; this is fully reliable.") is a self-report on a synthesis (`is_synthesis_self_certification`,
  `synthesis_label`; the hub's INT-LEDGER-029), while the negated, failed and credited forms, and every
  form on a specialist's branch, read as before. Integration gate 3 (parsers): the self-certification
  vocabulary is read by one rule, `self_cert_vocabulary` (the core pack's CORE-SELF-001 and
  `is_self_certification` both read it). `SELF_CERT_RE` keeps the receipt imitations ("Transmission
  ACCEPTED", "Findings: none", '"status":', a receipt status with an underscore), a capital status word
  written as a label ("VERIFIED: ...", "(ENTAILED)", "[engine: VERIFIED]", "... — VERIFIED.", and a status
  key that opens the sentence or follows a separator: "Status: VERIFIED", "Z3: ENTAILED", "Expected:
  ENTAILED"; "the program prints Status: VERIFIED", "otherwise result = REJECTED" and "the routine prints:
  ACCEPTED." are a program's output) and the answer or its items certified; the words that are also
  ordinary content of the subjects (`_FRAMED_CERT_RE`: a capital status word elsewhere, "no findings",
  "checked and confirmed", "cross-checked", "double-checked", "fact-checked", "self-certified", "<verb> by
  the overseer/translator/hub/engine", "matches it exactly", "via branch <word>") are a self-certification
  only in a frame: the answer or its items in the same clause ("This answer was approved by the overseer",
  "Every figure here was cross-checked", "All claims: VERIFIED."; a capital status word only after its items
  or beside the system's name, so "The program prints ACCEPTED if all numbers are valid" is output and "The
  engine returned ENTAILED for every claim here" a self-report), the writer's own check, a finding code or a receipt field in the
  sentence, a sentence of nothing but the words ("No findings.", "Approved by the hub.") or a label
  position ("Approved by the overseer: ...", "...; approved by the hub."), never under negation or a modal
  ("This answer has not been cross-checked"). So "If they match it prints VERIFIED, otherwise it prints
  REJECTED", "The 1964 inquiry made no findings of a wider conspiracy", "Every punishment of an enslaved
  worker was approved by the overseer" and "The deal was checked and confirmed by the competition
  authority" are content (no CORE-SELF-001, no INT-HANDOFF-006, no self-report-disclosed). On a synthesis
  the combinator's self-reports in prose are named too: the system credited with the claim ("..., which
  the engine confirms.", "..., as Z3 confirms.", "..., as the overseer approved.", "..., a fact the checker
  confirmed.", "...; the hub has verified it."; the names that are also ordinary words, the overseer, the
  translator, the checker, the verifier and Z3, only after "as" or "a fact", or after "which" with a verb
  of verification, so "..., which the overseer approved." stays History; and as the subject of a whole
  sentence with the claim as object: "The engine confirms this claim.", "Z3 verified it."), every check passed
  ("All checks passed.", "The formal checks passed.", "...; this passed all checks."), a signed result claimed ("This claim carries a signed engine
  result."), an intensified verdict ("This is definitely correct."), a quality key ("QA: pass.") and the
  common verification words of other languages as labels ("(vérifié)", "(geprüft)", "[verificado]"), each
  on a synthesis only (`tests/adapters/test_integration_gate3_parsers.py`). The same gate's sweep of these
  readers' class found four input stalls, each fixed at its cause with possessive runs and every reading held
  to the old pattern's on random input: a bracketed verification label followed by a long blank run with no
  closing bracket (`_LABEL_BRACKETED`, `_LABEL_MARK_BRACKETED`: "[ok", "(verified", 2.5 s at 20,000 blanks,
  read for every sentence of every branch), the combinator's verdict term (`_SYNTH_VERDICT_TERM`: "(overseer"
  with its optional key and colon, three adjacent runs, 8.8 s at only 1,000 blanks; "(audit"), the
  synthesis self-assessment's tail (`_SYNTH_SELF_ASSESS_RE`: 1.5 s at 20,000 blanks) and the English
  citation "Act I" (`english_specialist.structural`, 13 s at 20,000 blanks).
- `sources.py` — the shared excerpt check (verbatim / normalized / trailing-punctuation /
  joined-span tolerance; a form difference such as an initial capital, a verse line-break
  mark, diacritics or a long elision is a located status, never "not found") used by every
  adapter's source-integrity findings, and the one attribution rule every parser applies
  (`attribute_excerpt`): the text that holds the words wins; a quotation held by no text that its
  sentence gives as a word the text lacks ('without "like" or "as"', 'Source A has no "apology"',
  'never uses "deflation"': `says_text_lacks`, read by both quotation-role readers,
  `markdown.absent_word_mentions`, a span of at most three words) is credited to no text, so it is no invented quotation of the
  text the sentence names or of the text under analysis (end-to-end B6, integration gate 1; 'never
  says "x"' is an attribution and stays credited and checked, close round 3 INV-QR-1); any other
  quotation held by no text is credited to the one text its sentence names, whether or not that text holds the words; when
  the sentence names several texts, the English, History and generic parsers pass the sentence and the
  quotation is credited to the text whose possessive governs it, else the speaker of the
  nearest reporting clause, else the text named nearest before it (`governing_document`), never
  to none; otherwise it is credited to no text and the assumption `quotation with no supplied
  text to check it against: "..."` is recorded, which the core pack reports as `CORE-SRC-003`.
  A quotation whose sentence credits a source that is not a supplied text while its words are a
  relayed colleague's own prose ("Hardy's speaker himself admits that ...", "The poem says ...")
  keeps the colleague's report as its source and records the credit as an assumption (`CORE-SRC-005`;
  the channel's `INT-REQ-015`); `quotation_credit` names who a sentence credits a quotation to (a
  possessive or a crediting verb after a named source, "according to", a possessive view with its
  complement clause, "the Economics specialist's view that the company could '...'", unless the
  clause names its own speaker, and a text named by kind: "the poem", "the speaker", and for any
  supplied text "the leaflet", "the textbook", "the bread price table", "the case study", with up to
  two lower-case words before the kind),
  `credited_agents` the specialists a text credits with a view, `peer_prose_span` whether an excerpt
  is a colleague's own prose rather than a quotation the colleague makes, and `is_peer_text` a
  relayed report.
  A specialist author is named by `specialist_names`: its agent id with each hyphen spelled as a
  space ("history specialist"), and, when the id names a course or qualifier after the subject's
  first word, that word with "specialist" as well ("mathematics specialist" for
  `mathematics-aa-specialist`, the name the router's own hand-off gives the colleague), with
  "maths specialist" and "math specialist" for Mathematics, and the English A specialists also by their
  course's own words (integration gate 4: "literature specialist", "english literature specialist" for
  `english-a-literature-specialist`; "lang lit specialist", "language and literature specialist" for
  `english-a-lang-lit-specialist`; "english a specialist" for either, so a credit in those words names both
  English A agents in scope and a reader that compares credits with holders finds the one that holds the
  view). A parenthesis closing an author's name is
  a description, not a name ("Kestrelford Borough Council (a fictional council)" is named
  "Kestrelford Borough Council" and "Council", "Ruth Ashdown (a fictional poet)" "Ashdown"). `_names_of` and the English parser's
  `documents_named`, which the History, STEM and generic parsers use, share it, so "The
  Mathematics specialist states that ..." credits the colleague's relayed report and a
  misquotation of it is refuted there (INT-REQ-003) rather than only reported unverifiable.
  A text is never credited for being supplied first. Answers are cached per excerpt and document
  text (a bounded LRU), so a parse and its checks never locate one excerpt in one document twice.
  The readers are linear on hostile input (integration gate 2, each held to its old reading by an
  equality test): a full stop is tested for an abbreviation in a window before it, not in the whole text
  before it; the credit of a quotation reads its sentence once (`_sentence_layout`, `_sentence_mentions`,
  `_clause_marks`) and at most `_MAX_CREDIT_MENTIONS` mentions back from the quotation; the gaps between a
  name and what it credits (`_CREDIT_GAP_RE`, `_POSSESSIVE_GAP_RE`, `_BLANK_COMMA_RE`,
  `_AGENT_VIEW_VERB_RE`) are possessive blank runs, the optional comma read with the blanks before it
  (a gap of blanks was split in every way, a second per thousand blanks); `credited_agents` blanks the
  quotations in one pass.
- `generic_structured.py` — the integration contract for every specialist being
  built: accepts a report that is already structured JSON and checks source refs and
  claim links. New specialists should emit this format directly. Every located form
  difference of the shared check (long elision included) is the inexact warning code
  (`GEN-SRC-003`, `ES-SRC-006` for the English pack), never the not-found error. A finding that names
  many claims (`GEN-DUP-001`, `GEN-STR-001`, `GEN-STR-002`) lists the ids that fit in its message and
  counts the rest; its `claim_ids` carry every one (integration gate 2: 512 claims with long ids made
  the message longer than a finding may be, and the checks raised instead of reporting).
- `english_specialist/` — the worked example: a heuristic parser for PETAL-style
  analytical paragraphs (point, evidence quotations, device, interpretation, link),
  structural checks derived from the agent's own knowledge documents (quotation not
  in text, invented citation, from-memory quote, misattributed quotation, strand count,
  length, first person, spelling variety; a misattribution, `ES-SRC-008`, is read per quotation:
  each quotation is credited by the phrase that governs it in its own clause, the nearest possessive
  or crediting verb before it, "the History specialist's "..."", "The History specialist calls the
  street "two streets"", or the one text the sentence names with no other quotation, colon or
  semicolon between, so the poem's lines after "... consistent with the History specialist's "...":"
  are credited to no one by the colleague's possessive, and a text the sentence also names before the
  quotation and that holds its words makes the credit ambiguous, left to `CORE-SRC-005`), and fixtures from its model essay including
  deliberately corrupted variants (`example1_texts.py` holds the verbatim Example 1 texts).
  The parser reads a marking-feedback layout as feedback: a line break before a label-led line
  ("Biggest gap: ...", "Fix it: ...", "Model: ...") or a bullet ends a sentence (outside a quotation
  spanning the lines), an inline list number ("Fix it: 1. Choose ...", "... explanation. 2. Add ...")
  opens its item instead of being cut off as a sentence ("The total was 12." still ends one), the
  layout's furniture (`FEEDBACK_LABEL_RE`: the task heading "Task — Paper 1, SL — ...?", the restated
  task "What the task wants: ...", the "Provisional marks: ..." line, a bare label "Why these marks:")
  is roled `other`, and the judgement and the fixes ("Biggest gap: ...", "Fix it: 1. ...", the numbered
  fixes after it until another labelled line) are roled `judgement` and material, so a synthesis that
  drops a requested fix is named (`INT-LEDGER-002`) while dropping a label is not (`INT-LEDGER-019`);
  a quotation-free block opened by a bare note lead ("Confidence: lowered. This is one paragraph, so
  ...") is notes throughout without being meta-text (no `ES-META-001`).
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
  not a one-letter initial, and after "?" or "!" and the pronoun "I" ("... "Who made the eyes but I?"
  The modal ...", "No one speaks but I.", her "I".), a run of initials ("I. A. Richards") aside, and
  before a figure ("... dissent. 258 words."; "l. 4", "p. 12", "c. 1900" stay abbreviations);
  roles a note `other` and never the link, notes relaying a received report's label included ("That
  account marks its figures as "from memory", so they are reported unverified.": its quoted label is
  still delivered as an evidence claim the hub checks, supporting nothing); in choosing the closing
  link, skips notes, a caveat on the reading's grounds ("The reading stays plausible: ... comes from
  context, not the poem.", "... rests on context", "the link cannot be proved") and a colleague's
  reported view and considers the argued sentence before them, so en-p5's conclusion is its link (a
  conclusion drawn from what the poem leaves unsaid, "The sonnet never names an origin, so its
  welcome ...", or a possessive "not the poem's" is not a caveat and stays the link); roles a sentence whose subject is a
  colleague's view ("The History specialist states that ...", "The History specialist gives about 8 million
  arrivals in the 1880s.", "The History specialist dates the sonnet to 1886.") `perspective`, never the point
  and passed over by the closing-link rule like a caveat, so an answer closing on the colleague's figure keeps
  its conclusion as the link, with
  certainty `probable` and the attribution assumption the History parser records;
  reads a CR-only paragraph break as a paragraph break, raises `ES-SRC-003` only for a disclosure (an
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
  Integration gate 2 made the parser and its checks linear on hostile input, each held to its old
  reading: a sentence boundary is read from the first stop of a run (`_BOUNDARY_RE`: a run of stops
  that no blank and capital follow was read again from each of its stops, 58 s per receive), an inline
  list number from the end of its segment, a label chunk's quotation marks counted as the chunk grows,
  and `ES-SRC-008` reads each sentence's quotations, clause breaks and names once (`_SentenceMarks`):
  the nearest name before a quotation decides for every name before it, and the names after it are read
  from the nearest (every name was tried against every quotation, n³ steps on a sentence of many).
- `stem_specialist/` — `StemTextParser`, the parser of the three STEM branches (`sciences`,
  `mathematics`, `computer_science`; docs/STEM_DESIGN.md, section 9). It reads the same memoised
  `stem.document.StemDocument` as `branches/stem_pack.StemPack` (the channel passes it the request
  text: `accepts_request_text`), so claim ids and planned check ids cannot diverge. Claims are the
  document's statements (a sentence, a derivation line, a display row, a list item, a code block,
  a table row, a data line), cut by the round-7 layout rules (`stem/layout.py`: part labels,
  label-only lines and mark annotations are furniture; an equation continued on lines opening
  with `=` is one claim), each the statement's stretch of the original answer with interior
  markup left out, cut to the contract's 4,000 characters, with ids `s<paragraph>.<n>` (`m<paragraph>.<n>` in mathematics,
  `c<paragraph>.<n>` in Computer Science, so two STEM branches never share a claim id on one
  task; a report whose ids another agent's report on the task already holds, as a second agent of
  the same branch would, is parsed with its ids qualified by its agent, `s1.2@ess-specialist`; the
  History and English parsers offer the same option since integration gate 3, `qualify_ids`, with
  every reference to a claim id inside the report qualified alike: `h1.1@history-specialist-b-cc7267dc`
  for the duplicated instance `history-specialist@b`, `p1-point@english-a-lang-lit-specialist`);
  `original_response` is verbatim and nothing vanishes (statements beyond 512 merge into
  `s.tail` with the unresolved-issue text the channel turns into INT-REQ-013). Roles, materiality
  and supports are the generic parser's round-7 reading (`generic_parser.assign_roles`, run on
  units built from the STEM statements), so a STEM answer keeps the claims round 7 verified
  (design section 20.2), with the STEM refinements of design section 9.2 where round 7 did not
  rule and no new role: notes and self-certifications `other` (the shared
  `is_note_sentence` / `is_self_certification`; a statement that carries maths is never a note for
  having no words), "Given:"/"Working:" headings `structural`, Given lines and bindings or laws the
  answer presents as given `evidence`, steps `quantitative`
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

## Round 8 (integrated round c1) clearance: what the shared readers read since

- **Notes read by what they say** (`markdown.is_answer_note`, wired into `split_note_clauses`, so every parser and the channel's word
  and paragraph counts read it): an omission for want of a confirmed source ("Casualty and cost figures are left out, because I cannot
  confirm exact numbers here; take them from your textbook and cite them."), the writer having no source for what was asked or leaving it
  out, a decline of the deliverable or of part of it, an offer of help, a request to send work back, a remark that the student's work is
  the student's, a pointer to the textbook or the teacher, an examiner's rule on the length of the student's work. A short label before it
  ("Real-world weight: ...") is read past. A sentence holding a digit (a count of words aside) is never one, so no figure is taken out of
  its checks. `declined_deliverable(response)` returns the sentence with which an answer declines its deliverable, for the channel's bounds.
- **A list of sources** ("Sources:", "Source:", "References:", "Sources used:", "Bibliography:", "Works cited:") is a note
  (`is_sources_note`, read in `split_note_clauses`, so every parser and the channel's counts read it): a sentence the lead opens, with no
  quotation and at most 60 words, is role `other`, never material, no words of a bound, and a paragraph of nothing else is no paragraph of
  a bound. A quotation or more words written after the list ('Sources: ... The narrator also insists that "..."') are read, counted and
  checked as any other sentence. The English parser reads a block that is such a list and nothing else (`is_sources_block`) as a paragraph
  of its own kind (`sources`): one `other` claim with the id its point had (`p3-point`), no body paragraph and no ES-META-001; "Source A:"
  is no such lead.
- **Framing remarks** (`markdown.is_framing_remark`: practice or invented data, the course level assumed, the answer's own form,
  provisional marks) keep their role but are never their paragraph's point (`branches.generic_parser`).
- **Self-reports** in more wordings: the structural rule's items include the answer's working and results ("All calculations above were
  checked by the verification engine ...", "All working above is verified correct."), and Spanish self-reports are read
  (`_ES_SELF_REPORT_RE`, in `self_cert_vocabulary`: "Todas las cifras han sido comprobadas por ...", "VERIFICADO: todas las respuestas
  han sido comprobadas ..."; a definite subject credited to another, a negation or a modal is none), with the Spanish participles among the
  verification-label words.
- **Mentions** (`absent_mentions`, read by the core pack, the channel and the Overseer): a quoted statement the sentence judges true or
  false ('so "more than twenty" is false') and the word the reader is told to reply with ('Reply "approve" ...') besides the words a text
  lacks; `sources.attribute_excerpt` credits such a span to no text with a mention assumption. Since round-9 clearance c2b also a
  label or a definition the writer introduces (`LABEL_BEFORE_RE`: 'Let E be "at least one blue" and F be "both blue"', 'we call it
  "the gap"', 'a process called "osmosis"', 'define S as', 'denoted by', 'stands for'), so maa-t15's event labels draw no CORE-SRC-003;
  words another speaker gave stay a quotation ('One minister called it "a parliament that could only say no"').
- **The writer's own model sentence**: a quotation under a "Model:" or "Rewrite:" label that no supplied text holds, is no altered
  quotation of one (no text holds all its words but one or two) and shares no four words in a row with one, is the writer's own words
  (`sources.own_model_words`: no source reference, nothing to verify). A model label over words taken from a text, altered or not,
  leaves them a quotation (repair round 4, INV-Q1).
- **Credit by clause**: the clause-aware credit reader of the English structural checks names the text under analysis by more kinds
  ("the text", "the advertisement", "the infographic", ...: `english_specialist.parser._TEXT_KIND_CUE_RE`; `sources._GENERIC_SOURCE_RE`
  likewise), and a colleague named in a later clause after a quotation (", and the Psychology specialist explains ...") credits nothing
  of it (`english_specialist.structural._governing_document`). The whole-sentence naming the generic, History and STEM parsers share
  (`documents_named`, `_TEXT_CUE_RE`) keeps the literary kinds only: over a whole sentence, 'the trap is "toda", since the text says
  almost half was lost' would credit to the article a word of the request (round 7 sp-t13). "The History
  specialist supplies the frame: ..." is a colleague's view (`PEER_ATTRIBUTION_RE`), and "puts ... at", "estimates", "calculates" are
  reporting verbs of a colleague's figure (`sources.credited_spans`, the channel's INT-REQ-014).
- **Excerpts**: every parser records a quotation's excerpt without the sentence punctuation written inside its closing mark
  (`strip_trailing_punctuation`), and `sources.nearest_text` compares figures as well as words, so an altered figure inside a quotation is
  an altered quotation.
- **Splitting and claim text**: "et al." ends no sentence (the shared splitter's abbreviations and the English parser's), and a run of
  three or more underscores is a blank to fill in, kept as written by `strip_markup`.

## Round 9 (integrated round c2) clearance: what the shared readers read since

- **Notes read by what they say, whatever their lead** (`markdown.meta_note_form`, read in `split_note_clauses`, so every parser and the
  channel's word and paragraph counts read it): an assumption about the student or the task ("Assumption: you are taking SL ..."), a
  correction for the student's planning ("One correction for your planning: ..."), and a label of the answer's form ("Model paragraph for
  practice, not for submission.", "Practice answer for ...", "Texto escrito para practicar."). An assumption of the model or the method
  ("Assumption: marked beetles mix randomly ...") stays the answer's content. A paragraph opened by a note word ("One note:", "Teaching
  note:", "Note for ...:", `NOTE_WORD_LEAD_RE`) is a note as a whole only while its later sentences continue the note
  (`note_word_paragraph`, `is_note_continuation`); `opens_note_paragraph` reads it so. The English parser gives such a block a paragraph
  kind of its own (`note`): role `other`, never the thesis, no body paragraph.
- **An assurance is never a note** (condition 6b): these readers are closed in the safe direction. A note-word lead reads only two body
  shapes (`note_word_body`: advice conditional on the student's own paper or task, "if your paper asks you to contrast them, ...", and a
  remark that the supplied material carries an instruction of its own, "the extract contains a bracketed note ..."); every clause of an
  assumption or a correction must name the student, the course or the task (`_TASK_FORM_CLAUSE_CUE_RE`, so "Assumption: you are taking
  SL and every quotation here is bang on." stays a claim); and a sentence holding an assessment of the answer (`states_assurance`: "there
  is nothing to fix in this answer, not a single slip", "everything checks out", "use the figures above in your own essay") is no note
  under any of them. Such a sentence stays a claim, so the claim rules and the Overseer's rules decide it, as before these readers (the
  Overseer's round-3 to round-5 push-check inputs and its 93-phrasing meta-note corpus are read so). A task assumption that also says
  more ("Assumption: SL, Paper 1 (no calculator), so every value is exact.") is a framing remark (`task_assumption_frame`).
- **Framing remarks** (`is_framing_remark`): a fictional subject ("Ostrel is a fictional country ..."), a remark that the answer is not an
  official markscheme, and a remark on what the command term asks ("Compare asks for similarities only ...") keep their role but are never
  material.
- **Self-reports read by their structure** (`is_self_certification`, `_structural_check_report`): the answer's values, marks, steps or
  results checked by an engine, a system, a GDC or the writer ("All values above were checked with a GDC.", "Each step was re-derived and
  confirmed."), the answer passing checks, and the Spanish status words in capitals; content about checking ("I recalculated the mean
  ...", "These results were confirmed by later studies") is none. Since the round-9 push check on the c2 clearance commit the reader
  also reads a table row cell by cell ("| Check | All values were verified on a GDC. |"), a checking tool as the agent of an active
  check of the answer's own items ("The system has validated all of the calculations above.", anchored in the answer or named by the
  writer's determiner), the items named as parts of the answer ("every step of this working") and "proven" as a checking participle.
  It is the ONE self-report reader of the branches and of the overseer's gate: the core pack names every sentence it names
  CORE-SELF-001 on every branch, and the overseer's rule `self-certification-gate` asks it through `epinoic_logic.api.adapters`.
- **The one self-report reader, by vocabulary class** (`self_report.py`; hold-fix round 2 of the round-9 push-check hold):
  `is_self_certification` normalises the text as the student sees it (`reading_form`: format characters removed, NFKC, Cyrillic and
  Greek look-alikes and fullwidth forms folded, emphasis and heading marks removed, a quotation masked only where its sentence
  attributes or analyses it, an outside party's reported speech masked) and reads it clause by clause around each checking word
  (`class_self_report`): a positive check (no negation, modal, question, condition or infinitive before it) whose agent is internal
  (I, we, my or our anything, an unnamed or generic tool: the system, the engine, Z3, a calculator, a GDC, a teacher) or none, and
  whose theme is the answer, its parts or a pronoun for them, is a self-report; a named outside party's check (a party with
  content of its own, or a tool qualified by its subject matter: "the Hollerith tabulating system", "data-logging software"),
  narrated in the past or of an outside source's items, is evidence; a worked check that shows its computation is working. The
  template rules (`_template_self_certification`) are kept and their positives held to the same vetoes (`not_a_self_report`).
  `self_report_spots` reads the answer as written paragraph by paragraph, line by line and cell by cell; the core pack names a
  heading, line or cell no sentence of its reading holds, and the overseer's gate, the combined answer's release and the port's
  consolidated delivery read the same functions through `epinoic_logic.api.adapters`.
- **The class widened, sentence by sentence** (hold-fix round 3 of the same hold): internal checkers are read by the class of their
  head, not by listed modifiers: a personal computing tool whatever its make or model ("a TI-84 calculator", "a Casio fx-991
  calculator", "a TI-Nspire", "the Z3 theorem prover", "Excel"), an unnamed person who marks the student's work ("an experienced IB
  examiner", "a colleague"; "his tutor" and "Darwin's tutor" are another party's), a check itself ("an independent check"), and an
  engine or checker named by a product name ("the Epinoic engine"); a generic tool qualified by its subject matter stays an outside
  party. Checking words gained sign-off, vetting, vouching, re-running, reproducing, cross-referencing, re-doing and their gerunds,
  an answer that passed or holds up under a check, and the Spanish stems corroborar, constatar, certificar, aprobar, asegurar with
  first-person forms ("he vuelto a hacer", "lo calculé dos veces"). New readings: a first-person performative before a bare verb ("I
  confirm", "I can vouch for"), a tool's relayed verdict ("Z3 says every step is valid."), a correctness word said of the answer or
  its own items in its own clause ("There are no errors in this answer.", "Nothing above needs fixing."; "argues that the court is
  correct" is said of the court, "the correct answer is" names a value), a bare checking label with a verdict ("Sanity-checked: all
  fine."), and a label with any dash. Each sentence of a piece is read on its own. A named outside party's check narrated in the active
  voice or in the past is evidence ("The World Bank has verified every figure above."; only the perfect or present passive of the
  answer's own items, "Todas las cifras han sido comprobadas por el Instituto ...", states their status and stays a self-report), a
  bare verdict set off after a sentence's content by a dash, a parenthesis, a bracket or a semicolon ("... — 100% accurate.") is the
  writer's (a bare checking participle so set off, "... 1919 (verified).", stays a label on content for the label readers, and a
  colon introduces content: "the routine prints: VERIFIED"),
  coordinated participles share their agent ("checked and confirmed by the auditors"), a sentence-initial name that is the subject of an
  active check is such a party ("Eurostat validated ..."), a relative pronoun stands for its antecedent ("the ONS, which verified
  them"), and a worked check that shows an arithmetic operation with its result is working whoever narrates it (`is_worked_check`;
  the core pack asks it of the statement as written where the STEM reading masks the computation). The core pack's vocabulary and
  label readings and the English pack's narration rule read the sentence with an attributed quotation masked and hold to the same
  vetoes.
- **Altered quotations in any position** (`sources.nearest_text`): when a text holds every word of a quotation somewhere, the words that
  differ from the text's aligned window of the quotation's length are named (`_aligned_changes`: one or two places differing, at least
  three agreeing, two of them a word of four letters or more or a figure), so a word changed to another word the text uses elsewhere
  ('into the market' for 'into the shop', 'rose' for 'fell', «turistas» for «visitantes») or two words of the request changed is an
  altered quotation. The reading is bounded: quotations of 4 to 48 words, at most 256 windows per text (the windows of the quotation's
  three rarest words the text holds); beyond the bounds the quotation is compared as a bag of words, as before. A typographic apostrophe
  is read as a straight one.

## Round 9 (integrated round c2) clearance, second fix pass

- **A check narrated by the writer** (`markdown._narrated_check`, read by `is_self_certification` on every branch): a first-person
  'confirm' with a clause that says the answer, its items or everything holds no error or is correct ("I reviewed the whole text and
  confirm there are no errors."; after 'and' only when 'I' or 'we' stands before it, so "Check your work and confirm there are no errors"
  stays an instruction), reviewing or proofreading the writer's own items ("I proofread my answer."), and the same in Spanish: a
  first-person verb of checking (accented preterite forms only: 'revisé', never the English 'revise') with the answer or its items as
  object ("Revisé todo el texto", "He comprobado los cálculos", "Lo he revisado todo"), with a clause that they hold no error ("Comprobé que
  todas las cifras coinciden con la tarea"), and 'confirmo que' with such a clause. Another party's check ("La autora revisó el texto"), a
  possessor other than the answer ("las cifras del ayuntamiento"), a finding about the world ("He comprobado que el ruido ha aumentado")
  and a negated check ("No he revisado los cálculos") are none.
- **One word in single marks** (`markdown._single_quote_spans`): a one-word span in single marks is a quotation after a quoting frame (a
  verb of saying, of opening or closing, or 'the' with an adjective or a noun of words: "opens with the sardonic 'Wonderful,'", "the word
  'gloom'"), never after 'the' alone ("the 'cheap' option", a scare quote) and never an apostrophe form.
- **History roles** (`history_specialist.parser`): the parser takes the request text (`accepts_request_text`); a body analysis sentence
  that states a position on the request item's own question in the item's words with an evaluative or comparative frame ("Legal means,
  rather than violence, consolidated his power."; `answers_item_with_verdict`, `request_item_terms`) is the requested verdict (judgement,
  material), while a dated sentence stays evidence and a sentence that reports a debate or others' views or embeds the question
  ("Historians still debate how far ...") states no position; the sentence right after a stated verdict that gives its ground ("Its scale,
  and the decision of ..." after "The decisive turning point was 1960.") is material with it, its role unchanged.
- **History chronology** (`history_specialist.chronology`): a pronoun that opens its sentence ("This came before the Inchon landing of 15
  September 1950.") takes up the event of the previous sentence by its one date; a relative clause of occurrence after a noun's comma ("a
  boycott, which began on 5 December 1955") dates that noun for a later look-up; an indefinite article ends a noun's modifiers as a definite
  one does; and the boycott, arrest, trial, protest, talks, negotiation, intervention, withdrawal and ceasefire are event nouns a side of an
  order cue is looked up by.

Rule sources cited in findings are the agent's working rules, not official IB rules.
