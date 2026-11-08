"""Which ES-META-001 findings are an agent's self-report (rule ``meta-note``, round-8 clearance c1; its note form narrowed
to a closed allowlist after the push check held the clearance commit), and which blocks of an answer opened by a note or
sources lead are read as a note or a pure source list (rules ``lead-blocks`` and ``source-list``, after attack round 2). Rule
``non-material-text`` (:mod:`.non_material`, after attack round 3) inverts the reading and uses these readers on everything
the branch's parser reads as no claim of the answer.

The English pack names every meta-text paragraph of an answer ES-META-001 (warning), and the delivery policy's rule
``self-report-disclosed`` refuses the FORMALLY CHECKED label to an answer whose receipt carries an agent's self-report at
any severity. ES-META-001 names two kinds of meta-text: a SELF-REPORT (a self-certification, an assurance, a narrated check,
a pasted receipt, a verification label) and a NOTE (a limitation, "Note: I can't see the image.", or a study suggestion,
"Next step: write your own paragraph on the same two strands and paste it here for feedback."). The knowledge bases ask
every answer to close with such a line, so in round c1 all four English answers carried ES-META-001 for a note and none
could ever be delivered FORMALLY CHECKED.

This module reads the journaled answer again, deterministically, and frees a paragraph-level ES-META-001 from the rule only
when its paragraph is positively read as a note. The push check held the first version: its note form accepted any
paragraph holding a limitation word such as "not" or "only", so "Note: there is nothing to fix in this answer, not a single
slip." travelled under the FORMALLY CHECKED label. A first rewrite read notes through a wide grammar (provenance,
possessive, status and suggestion constructions with open noun-phrase and prepositional slots), and an attack freed most
of its assurance paragraphs through those slots ("Note: the figures come from Table 1 to the decimal place.", "Note: the
answers are the exam board's own.", "Next step: use it as your model."). The rule is now a minimal CLOSED allowlist and
prefers refusing a genuine note to freeing any assurance:

* only a PARAGRAPH-level ES-META-001 can name a note (its message opens ``paragraph N is meta-text (``, written by the
  pack's own code); a sentence-level one names a sentence that narrates a check, certifies the answer or imitates a
  receipt, which is always a self-report. The answer is segmented by the English parser itself
  (:func:`~epinoic_logic.adapters.english_specialist.parser.segment`, the reading the pack used), and paragraph N must be
  meta-text there;
* the paragraph opens with a bare note lead as the parsers read it (``Note:``, ``Notes:``, ``Please note:``, ``NB:``,
  ``N.B.``, ``Next step(s):``, ``Limit(s):``, ``Caveat(s):``;
  :func:`~epinoic_logic.adapters.markdown.opens_note_paragraph`), read as written and as normalised, and AS A WHOLE from its
  first character (attack round 5, :data:`LEAD_REGION`): before the lead only blanks, at most one bullet and the lead's own
  emphasis ("**Note:**", "- Note:"; never "> NB:", "### Note:", an emoji, a symbol or a tag),
  holds no JSON and no sentence a shared self-report reader names (the English parser's meta sentence and narration, the
  core pack's self-certification vocabulary and verification labels, and the auditor's own structural detector
  :func:`~epinoic_overseer.checks.selfcert.flags_self_certification`);
* rule ``assurance-words`` (quotations masked): no word of checking, verification, accuracy, agreement or approval in the
  affirmative, no fault denied ("none of the quotations is wrong"), no first-person check;
* rule ``evaluation-words``: no word or idiom that evaluates the answer or names a fault, a repair, an agreement, a grade
  or a commitment, in ANY polarity and anywhere in the paragraph ("sound", "slip", "fix", "in doubt", "holds", "in order";
  the Spanish and French forms too). The two vocabularies are a second line: the rule is the next one;
* rule ``note-clauses`` (:func:`note_reading`), the closed allowlist: the paragraph after its lead is cut into sentences
  and clauses, and EVERY clause must be read, each of its words from a closed word list, as one or more of exactly three
  constructions joined by "and", "or", "so", "but" or "then":

  (a) ``study-suggestion``: an imperative addressed to the student (a verb of a closed list of study verbs: "write",
      "plan", "paste", "check", "annotate", ...; no verb of using, keeping, copying, submitting, treating, ranking,
      marking, appraising, reproducing or learning by heart: no "use", "copy", "treat", "see", "notice", "redraw",
      "learn", "memorise") whose object is the student's work, "your" with a closed work noun and closed modifiers, with
      or without "own" ("your own paragraph", "your quotations", "your notes"; after every study verb but a verb of
      practice, which takes "your own" work only), a generic study item ("a practice question", "one quotation"), a question ("question 2") or a passage of the
      STRICT source list, words that name supplied material and never a written answer or a part of one ("the extract",
      "the image", "the census"; never "the table", "the text", "the opening", "the lines", "the passage", "the poem",
      "the stanza", "the article", "the speech"), and never the answer or any part of it: no "this answer", "the model
      above", "the quotations", "the figures", "the paragraph above", and "it", "them", "its" or "their" only after a
      noun phrase of that number read as the object, a yardstick or a "using" item of the suggestion's own sentence
      ("write your own paragraph ... and paste IT here"; a topic names no antecedent). A verb of practice ("practise",
      "revise") takes only the student's own work ("your own notes"), a question or a practice item ("a past paper"),
      never "your notes", a passage, a pronoun or a piece of writing. A verb of sending ("paste", "send") sends the work
      back to the tutor ("here", "back", "for feedback", "for a second provisional mark"; never a bare "send your essay",
      "for marking" or "for a mark"). What may follow is closed too: "here", "again", "now", "for feedback", "for 45
      minutes", "on"/"about" a topic ("on the same two strands", "on the final section"), a yardstick after "against",
      "with" or "in" (the student's own work or the strict source list only), "to question 2", "using" one study item,
      the student's own work or the strict source list, "focusing on" a topic (also as their own clause after a comma),
      "before you submit"; after "time/test yourself", "on" takes only a question, a practice item or the strict list;
  (b) ``no-access``: a first-person inability or access limitation: the subject "I" or "we", a negated perception or
      access verb (see, read, open, access, have, view, hear: "can't see", "could not open", "don't have", "have not
      seen", "was unable to open", "have no access to") and a NAMED source as its object, a definite determiner required
      ("the image", "the full extract", "your attachment", "the textbook library or MyLib"; never "a second source" or a
      bare "sources", which can be a search that found nothing), with at most "here", "yet", "in this session", "in this
      chat" or "in your message" after it;
  (c) ``not-checked``: named content of the answer is NOT checked or NOT verified ("the dates are unchecked here", "the
      figures are not verified", "the quotations have not been checked", "the 1924 vote share could not be confirmed"):
      a subject of a closed determiner, closed modifiers and a closed content noun (with at most "here", "above" or
      "below" after it), whose only predicate is that negative status, with at most "here" or "yet" after it and no
      modifier that claims extent, fidelity or finality ("all", "every", "exact", "final") or sets the content against
      the rest of the answer ("the remaining figures", "the other dates", "the second date": the rest was checked).

  Every other clause makes the paragraph a self-report: every provenance clause ("come from", "taken", "copied", "quoted"
  or "drawn from", "rest on", "based on", "according to", a possessive such as "the poet's own words"), every status
  other than not checked ("approximate", "fictional", "from memory": a note the rule now refuses only keeps that answer
  off the formal path, as before the rule existed), every universal or fidelity modifier ("all", "every", "each", "to the
  decimal place", "word for word", "intact", "in every case"), every finality, approval or evaluation word, the task's own
  wording, every apposition, bracket or prepositional phrase that is not part of (a) to (c), every word the lists do not
  hold (an unlisted synonym, a misspelling, a look-alike letter, a word of another language) and every character that is
  no letter, digit or clause mark (a bracket, a quotation mark left after masking, an emoji, a combining mark). Two names
  say why a clause was refused, for the record: rule ``bare-negator`` (a negator outside (b) and (c): "not a single
  slip", "not in doubt", "the quotations are not quoted from memory", "I could not find a conflicting source") and rule
  ``answer-evaluation`` (a clause whose subject is the answer or a part of it with any predicate but (c): "the quotations
  are tickety-boo", "each date lands", "the figures come from Table 1");
* rule ``note-form``: at least one clause has the kind of the lead: a study suggestion after ``Next step(s):``, a
  ``no-access`` or ``not-checked`` clause after any other lead. A negator alone ("Note: not.", "Caveat: none.") is no
  construction at all.

A paragraph that mixes a genuine limitation with any assurance is a self-report: every clause must be read and the
vocabularies veto the whole paragraph. Anything the rule cannot read (a segmentation failure, a paragraph number that names
no meta-text paragraph, a reader that fails, a paragraph over 20,000 characters) is a self-report too: the rule never frees
what it cannot read, and it frees only a paragraph it reads as a note. On its own that did not keep an assurance off the
FORMALLY CHECKED label: attack round 2 found the rule held, but the English parser keeps some note-led text out of
ES-META-001 (a one-line block after a sources lead is a 'sources' unit; a quotation-free block after a bare note lead that
is not all meta-text is a 'body' block whose sentences are all notes; a lead the parser does not read, a note holding a
quotation, a note sentence inside a body paragraph), and an assurance there reached no reader once the rule freed the
answer's genuine note. Rule ``lead-blocks`` closes that at the delivery policy, without changing the parser's
segmentation, the receipts, the claims or any finding a pack emits (:func:`lead_blocks`, :func:`unread_lead_blocks`):

* it reads the journaled answer AS WRITTEN, cut into paragraphs as the English parser cuts it, for the leads of every
  reader: the note leads (the bare leads above, "Confidence:", "Note on ...", the History parser's "Limitation(s):" and
  "Sourcing:" and its full stop in place of the colon, "Note.", and the Spanish and French forms "Nota:", "Remarque :",
  "Siguiente paso:", "Prochaine étape :" ...) and the sources leads ("Sources:", "Source:", "Sources used/consulted/cited:",
  "References:", "Bibliography:", "Works cited:", "Fuentes:", "Références :" ...), at a paragraph's start, at a line's start
  and right after a sentence's end inside a line (a stop, or the brace or bracket that closes pasted JSON). Since attack
  round 3 (:func:`lead_starts`) it reads a normalised copy (:func:`_lead_copy`: NFKC, so "Note：" and "Ｎｏｔｅ:" are "Note:";
  every format character, other default-ignorable code point and combining mark, the emphasis marks "*", "_", "`", "~" and
  an HTML-like tag read as nothing, so a word joiner, a zero-width space, a soft hyphen or a variation selector after "Note
  on", "No**te**:" and "<b>Note:</b>" are the leads they show; every run of blanks, a line break included, read as one, so
  "Note on" and ninety spaces, "N.  B." and "Next", a line break, "step:" are leads), reads a lead WHATEVER punctuation,
  bracket or dash follows its words (:data:`_LEAD_MARK`: "Note:", "Note.", "Note∶", "Sources —"; "Note on" before any mark,
  "Note on(", "Note on—", "Note on…", or before a topic of at most 80 characters that ends at the first mark that is no
  sentence stop, :data:`_NOTE_ON`; "Note that", "Note on the dates." and "NB the" are no lead), and reads it after any run of
  marks before it on its line ("> Note:", "◦ Note:", "→ Note:", "| Note:", "[Note](#note):"; :func:`_prefix_ends`).
  Since attack round 4 the copy reads each letter on its confusable skeleton (:func:`skeleton`, :data:`_CONFUSABLES`: the
  Cyrillic, Greek, Armenian and Cherokee look-alikes of Latin letters, the Latin small capitals, the dotless i and j, a
  letter with a diacritic as its base letter; digits are never mapped), so "N" and a Cyrillic о, "Nоte:", a Greek "Ν.Β.",
  "ɴᴏᴛᴇ:" and "Ṇote:" are leads; a lead only the skeleton reads opens a block that must be read and frees nothing (rule
  meta-note asks for its bare lead as written, rule ``source-list`` reads its lead with ``plain`` reading). Quotations are
  not masked: a lead after a quotation mark is no lead for any parser;
* a block runs from its lead to the next lead or the paragraph's end, so every word after a lead belongs to a block read
  AS A WHOLE: a note lead's block by rule meta-note (:func:`read_meta_paragraph`; a lead it reads no bare note lead in,
  "Confidence:", "Nota:", "__Note__:", a fullwidth colon or a list number, is refused), a sources lead's block by rule
  ``source-list`` (:func:`read_source_list`);
* rule ``source-list`` reads a PURE source list only, AS A WHOLE from the block's first character (attack round 5: it read
  only the words after its lead, so "👍 Sources:", "★★★★★ Sources:", "🆅🅴🆁🅸🅵🅸🅴🅳 Sources:", "<all verified> Sources:",
  "Sour<all good>ces:" and "Sources💯" were freed): before its lead only the closed region of :data:`LEAD_REGION` (blanks, at
  most one list mark of a closed set, one bullet "-", "*" or "•" or one list number "1.", "1)", "(1)", "a)", "(a)", and the
  lead's own emphasis), then the lead's words as written on one line and the colon the English parser requires
  (:data:`_STRICT_SOURCES_LEAD_RE`, :func:`strict_lead_end`; "Sources :" too, never "Sources —" or "Sources👍"); after it
  source names, document labels, locators and the kinds the citation rule accepts ("The Tuner extract (supplied text)", "Source A", "(paragraph 1)", "(Table 1)", "p. 12", a year),
  separated by ";", ",", ":", brackets that balance, dashes, bullets or line breaks, and a closing full stop. Every word is
  a word of a closed list (determiners, "of", "on", "and", "by", the kinds and parts of supplied texts and course material,
  their usual modifiers, locators, honorifics), or a CAPITALISED name that a supplied text's title or author writes (the
  journaled request's) or a subject's name; no word of a closed deny list, whatever names it (rule meta-note's
  vocabularies of assurance, evaluation, fault, negative forms, checking verbs and negators, and every quantifier, pronoun,
  auxiliary, clause word, affirmation, pointer to the answer and verb of consulting, using, quoting or relying); a number
  is a year or follows a locator noun (a run of them only across a dash, "&" or "and"), a letter A to H follows a label
  noun, a roman numeral an act, scene, part, book or chapter, a determiner a word; no quotation, no JSON, no sentence a
  shared self-report reader names, no word of either vocabulary. "Sources: none consulted (no retrieval in this session)"
  names no source and is refused (a quantifier and a verb), and so is a supplied title holding a deny word ("Great
  Expectations"): such an answer only falls back from the formal path. Since attack round 4 the list names sources and
  nothing else, the names the supplied texts give, the knowledge bases' fixed sources forms ("your question (supplied
  text)", "practice question (supplied text)", "your pasted answer (supplied text)", "Biology course notes (course notes)",
  "general Psychology course knowledge (course notes)", "the History specialist's context paragraph (supplied text)"),
  locators and kind tags: no word of ownership, origin, extent or fidelity and no official answer ("own", "original",
  "full", "answers", "official", "markscheme", "intact", "same" are deny words: "Sources: the examination paper's own
  answers.", "the extract's own lines" are refused), no answer but the student's pasted one, no work, results, student,
  title, heading, caption or person, a part a locator names only with its number, label or numeral (:data:`_PURE_LOCATORS`:
  "lines 3-5", never "the extract's lines"), a specialist only after a subject and an analysis only as a specialist's;
* any block not so read keeps the answer from the FORMALLY CHECKED label; the delivery policy names it by its paragraph,
  its line, whether it stands inside a line, its lead and the rule that refused it, never by its words. An answer with
  more than :data:`MAX_LEAD_BLOCKS` such blocks, or one a reader fails on, is refused as a whole (fail closed).

Rule ``lead-blocks`` reads every deliverable, whatever its subject (no parser keeps a note-led or sources-led block in the
claims the engine checks: before it, a Physics answer whose claims were all checked travelled FORMALLY CHECKED with "Note:
there is nothing to fix in this answer, not a single slip." added). It refuses genuine closing lines outside the two
readers by design: a "Next step:" outside the allowlist, a source list with a topic or a name no supplied title writes.
Every reader of this module reads its text normalised first (:func:`reader_text`, attack round 3: NFKC; every format
character, Unicode category Cf, and every other default-ignorable code point removed; every combining mark that does not
belong to a letter removed), and refuses a text that holds a Unicode tag character (:func:`hides_text`: ASCII no reader is
shown, which the removal would otherwise hide); rule meta-note asks for its bare note lead both in the text as written and
as normalised. Every reader that FREES a block (rule meta-note's allowlist, rule ``source-list``, and rule ``layout`` of
:mod:`.non_material`) reads it as a whole from its first character (attack round 5): before its lead or label only the closed
region of :data:`LEAD_REGION`, whatever the cutting reader (:func:`lead_starts`) skipped to find the lead; any other character
leaves the block unread. Assurances written with no lead are read by rule ``non-material-text`` when the branch's parser
keeps them out of the claims (a heading, a list item, a note sentence, layout furniture); those the parser reads as claims of
the answer (plain body prose, "Final note: ...", "P.S. ...", "NB" with no mark after it) reach no 6b reader. At the published
base such a claim was FORMALLY CHECKED on an answer without a closing note and withheld on one whose genuine note carried
ES-META-001; this rule frees that note, so the channel became reachable on note-carrying answers with the clearance commit
(``tests/overseer_tests/data/meta_note_attack_round4.json``). Since attack round 5 the delivery policy's rule ``unverified-claims``
narrows that channel: it refuses the label to any answer holding a claim that no signed engine result decides positively.
It does not close it: assurances inside or as verified or eligible claims stay open to the formal path, and only condition
6d (rule ``formal-label-withheld``, attack round 6) keeps them off the label. Rule ``unverified-claims`` takes two readers
of this module for a claim whose text says more than any encoding of it reads
(:func:`claim_alphabet_breach`: a character outside the claim alphabet, an emoji or a check mark glued to a verified result;
:func:`glued_note_lead`: a note lead inside a claim after a clause mark, "; note: ..."). Every reader is linear in the text: one normalising pass, one token scan (contractions written out, emphasis marks read as spaces), each
clause read forward once by three readers with a look-ahead bounded by a constant (a noun phrase is at most a determiner and
four words), each idiom of at most five tokens matched from its first; the segmentation is the pack's own; the strict lead
region is one anchored match of bounded alternation (:func:`strict_lead_end`); the lead reader builds its copy in one pass (a tag looked for at most 40 characters ahead), finds where the marks before a lead end in one
pass from the end, and matches a lead of bounded look-ahead at each place a lead can stand; the source-list reader reads
each token once in a constant context. The auditor has no reading of a note or sources block (a meta paragraph or a note-led block carries no claim the
auditor's checks read as material, and its detector reads claims; no audit check re-derives rule
``self-report-disclosed``, and the delivery receipt's verifiers check its signature only), so these rules are the only
reading; both take the auditor's own structural detector as a shared reader, so neither ever reads as a note or a source
list a block holding a sentence that detector names. Like every check, they prove a property of the text and this code
only.
"""
from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Optional

__all__ = ["META_NOTE_RULE", "ASSURANCE_RULE", "EVALUATION_RULE", "NOTE_CLAUSES_RULE", "ANSWER_EVALUATION_RULE", "BARE_NEGATOR_RULE",
           "NOTE_FORM_RULE", "SUGGESTION_RULE", "NO_ACCESS_RULE", "NOT_CHECKED_RULE", "NoteReading", "note_paragraphs", "is_note_paragraph",
           "read_meta_paragraph", "assurance_words", "evaluation_words", "note_reading", "note_form", "meta_paragraph_of", "self_report_findings",
           "LEAD_BLOCKS_RULE", "SOURCE_LIST_RULE", "MAX_LEAD_BLOCKS", "LeadBlock", "SourceListReading", "lead_blocks", "unread_lead_blocks",
           "read_source_list", "source_list_grounding", "reader_text", "hides_text", "lead_starts", "answer_paragraphs", "normalised_answer",
           "LEAD_REGION", "strict_lead_end", "lead_region_end", "claim_alphabet_breach", "glued_note_lead"]

META_NOTE_RULE = "meta-note"
ASSURANCE_RULE = "assurance-words"
EVALUATION_RULE = "evaluation-words"
NOTE_CLAUSES_RULE = "note-clauses"
ANSWER_EVALUATION_RULE = "answer-evaluation"
BARE_NEGATOR_RULE = "bare-negator"
NOTE_FORM_RULE = "note-form"
#: The three constructions of rule ``note-clauses`` (and the clause kinds :class:`NoteReading` records for them).
SUGGESTION_RULE = "study-suggestion"
NO_ACCESS_RULE = "no-access"
NOT_CHECKED_RULE = "not-checked"

#: The paragraph-level message of ES-META-001, written by the English pack's own code (``structural.meta_findings``).
_META_PARAGRAPH_RE = re.compile(r"paragraph (\d{1,6}) is meta-text \(")
#: One token: a word (apostrophes and hyphens inside it), a number, a check mark, or one clause boundary.
_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*|\d+|[✓✔☑✅]|[,;:.!?()\[\]—–]")
_BOUNDARY = frozenset(",;:.!?()[]—–")
#: Participles and adjectives of checking, verification, accuracy and approval: an assurance in the affirmative.
_ASSURANCE_WORDS = frozenset({
    "checked", "rechecked", "re-checked", "cross-checked", "crosschecked", "double-checked", "doublechecked", "triple-checked",
    "fact-checked", "factchecked", "spot-checked", "verified", "reverified", "confirmed", "validated", "certified", "approved", "audited",
    "reviewed", "tested", "proven", "proved", "guaranteed", "signed", "passed", "passes", "accurate", "accurately", "accuracy", "exact",
    "exactly", "correct", "correctly", "correctness", "reliable", "reliably", "reliability", "trustworthy", "faithful", "faithfully",
    "flawless", "flawlessly", "precise", "precisely", "authentic", "genuine", "rigorous", "rigorously", "error-free", "verbatim",
    "airtight", "watertight", "infallible", "definitive", "qa", "z", "engine", "solver", "overseer", "receipt", "receipts", "word-count",
    # third-person present of a checking act: "the engine confirms each claim", "this ensures every figure ..."
    "checks", "verifies", "confirms", "validates", "certifies", "proves", "guarantees", "ensures", "assures",
    # agreement and approval in plain words (round-8 clearance c1): "each quote matches the source", "they are fine"
    "match", "matches", "matched", "matching", "identical", "identically", "fine", "right", "okay", "ok", "perfect", "perfectly", "compared",
    "proofread", "proof-read", "tallied", "traced", "cross-referenced", "faultless", "watertight", "spotless", "impeccable",
    "✓", "✔", "☑", "✅",
})
#: Adjectives and verbs of a fault: denied anywhere in their clause ("none of the quotations is wrong", "no quotation was
#: altered", "I did not change any figure") they certify the answer. (A fault NOUN certifies only right after "no", "zero",
#: "without" or "free of": "no errors"; "does not address the issue of cost" is a limitation.)
_FAULT_WORDS = frozenset({"wrong", "incorrect", "inaccurate", "mistaken", "false", "misquoted", "misquote", "misquotes", "invented", "invent",
                          "altered", "alter", "changed", "change", "fabricated", "fabricate", "distorted", "made-up", "garbled", "erroneous",
                          "misread", "misreported", "miscounted", "miscalculated"})
#: Phrases of assurance (token sequences): "word for word", "as written", "spot on", "line(s) up", "made sure", "all good".
_ASSURANCE_PHRASES = (("word", "for", "word"), ("as", "written"), ("spot", "on"), ("line", "up"), ("lines", "up"), ("lined", "up"),
                      ("made", "sure"), ("make", "sure"), ("all", "good"), ("looks", "good"), ("all", "fine"), ("all", "clear"), ("word", "count"),
                      ("double", "checked"), ("went", "through"), ("gone", "through"), ("read", "through"), ("looked", "at"), ("looked", "over"),
                      ("letter", "for", "letter"), ("to", "the", "letter"), ("in", "full", "agreement"))
#: Past forms of a checking act after a first-person subject: "I looked at each quotation", "we read every line again".
_FIRST_PERSON_PAST = frozenset({"looked", "went", "read", "reread", "re-read", "compared", "counted", "matched", "made", "ensured", "tested",
                                "traced", "scanned", "reviewed", "proofread", "examined", "inspected", "confirmed", "checked", "verified"})
#: Stems read as assurance whatever their ending ("verification", "certificate", "validation").
_ASSURANCE_STEMS = ("verif", "certif", "validat")
#: Base forms of a checking act: an assurance after a first-person subject ("I check every quotation"), the verb of a study
#: suggestion when it opens one and takes an object ("Next step: check your quotations").
_CHECK_VERBS = frozenset({"check", "recheck", "cross-check", "double-check", "verify", "confirm", "validate", "review", "test", "prove", "compare",
                          "proofread", "certify", "audit"})
_FIRST_PERSON = frozenset({"i", "we"})
#: What may stand between a first-person subject and its checking act: "I have now carefully checked", "we also verify".
_FIRST_PERSON_GAP = frozenset({"have", "has", "had", "do", "did", "also", "now", "then", "carefully", "fully", "personally", "already", "always", "each",
                               "all", "both", "just", "to"})
#: The object a suggestion's checking verb takes ("check your ...", "verify the ...", "compare each ...").
_OBJECT_OPENERS = frozenset({"your", "the", "each", "every", "a", "an", "this", "these", "that", "those", "it", "them", "one", "two", "all", "any",
                             "whether", "how", "what", "which", "against"})
#: Nouns of a fault: "no errors", "zero mistakes", "without issues" certify the answer.
_FAULT_NOUNS = frozenset({"error", "errors", "mistake", "mistakes", "issue", "issues", "problem", "problems", "fault", "faults", "flaw", "flaws",
                          "typo", "typos", "inaccuracy", "inaccuracies", "discrepancy", "discrepancies"})
#: Negators: a negative form of an assurance word beside one of them is affirmative again ("nothing here is unverified").
_NEGATORS = frozenset({"no", "not", "nothing", "none", "never", "nobody", "neither", "nor", "without", "zero", "cannot", "unable"})
#: Negative forms of assurance words: no assurance at all, unless a negator stands in their clause.
_NEGATIVE_FORMS = frozenset({"unchecked", "unverified", "unverifiable", "unconfirmed", "unvalidated", "uncertified", "unapproved", "unaudited",
                             "unreviewed", "untested", "unproven", "unproved", "unsigned", "unreliable", "untrustworthy", "unfaithful", "inaccurate",
                             "inaccurately", "incorrect", "incorrectly", "inexact", "imprecise", "inauthentic"})
_MAX_PARAGRAPH_CHARS = 20_000


def _tokens(text: str) -> list[str]:
    return [t.lower().replace("’", "'") for t in _TOKEN_RE.findall(text)]


def _negator(tok: str) -> bool:
    return tok in _NEGATORS or tok.endswith("n't")


def _clauses(toks: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for t in toks:
        if t in _BOUNDARY:
            if out[-1]:
                out.append([])
        else:
            out[-1].append(t)
    return [c for c in out if c]


def _first_person_before(clause: list[str], i: int) -> Optional[str]:
    """The first-person subject ("i", "we", "i've", "we've", "i'd") of the act at ``i``, across the gap words, else None."""
    j = i - 1
    while j >= 0 and clause[j] in _FIRST_PERSON_GAP:
        j -= 1
    if j >= 0 and (clause[j] in _FIRST_PERSON or clause[j] in ("i've", "we've", "i'd", "we'd", "i'm")):
        return clause[j]
    return None


def assurance_words(text: str) -> list[str]:
    """The assurance words of ``text`` (rule ``assurance-words``; quotations should be masked by the caller): every word of
    the closed vocabulary read in the affirmative, every phrase of assurance ("word for word", "as written", "spot on",
    "line up", "made sure"), every negative form ("unchecked") and every fault word ("wrong", "altered", "errors") whose
    clause holds a negator (a fault denied certifies), every first-person checking act ("I check ...", "I looked at ...").
    A checking verb in its base form that opens a clause and takes an object ("check your quotations against the
    extract", "correct the second paragraph") is an imperative, the verb of a suggestion, never a check done. One linear
    scan of the tokens: each clause's negators are counted once."""
    found: list[str] = []
    for clause in _clauses(_tokens(text)):
        n = len(clause)
        negators = sum(1 for t in clause if _negator(t))
        for i, t in enumerate(clause):
            nxt = clause[i + 1] if i + 1 < n else ""
            phrase = next((ph for ph in _ASSURANCE_PHRASES if tuple(clause[i:i + len(ph)]) == ph), None)
            if phrase is not None and not (i == 0 and phrase[0] in ("make", "read", "looked")):
                found.append(" ".join(phrase))  # "word for word", "spot on", "made sure" ("make sure your ..." opening a clause is a suggestion)
                continue
            if t in _NEGATIVE_FORMS:
                if negators:
                    found.append(t)  # "nothing here is unverified": a double negative certifies
                continue
            if t in _FAULT_WORDS:
                if negators:
                    found.append(f"denied {t}")  # "none of the quotations is wrong", "I did not alter any quotation"
                continue
            if t in _FAULT_NOUNS:
                prev = clause[i - 1] if i else ""
                before2 = clause[i - 2] if i >= 2 else ""
                if prev in ("no", "zero", "without") or (before2 in ("no", "zero", "without") and prev in ("further", "more", "other", "known")) \
                        or (prev == "of" and before2 == "free"):
                    found.append(f"{prev} {t}")  # "no errors", "without issues", "free of errors"
                continue
            if t in _FIRST_PERSON_PAST and _first_person_before(clause, i):
                found.append(f"{_first_person_before(clause, i)} {t}")  # "I looked at each quotation", "we read every line again"
                continue
            if t in _CHECK_VERBS or t == "correct":
                if i == 0 and nxt in _OBJECT_OPENERS:
                    continue  # an imperative opening a clause: "check your quotations", "correct the dates" (a suggestion)
                if t == "correct":
                    if not _negated_here(clause, i, negators):
                        found.append(t)  # "all figures are correct"
                    continue
                who = _first_person_before(clause, i)
                if who:
                    found.append(f"{who} {t}")  # "I check every quotation", "we also verify": a narrated check
                continue
            if t in _ASSURANCE_WORDS or t.startswith(_ASSURANCE_STEMS):
                if _negated_here(clause, i, negators):
                    continue  # "the dates have not been checked", "these cannot be verified": a disclaimer
                found.append(t)
    return found


def _negated_here(clause: list[str], i: int, negators: int) -> bool:
    """Whether the assurance word at ``i`` is negated by a negator within the four tokens before it, with no second negator
    in its clause (``negators`` counts them once per clause: a double negative certifies)."""
    if not any(_negator(t) for t in clause[max(0, i - 4):i]):
        return False
    return negators == 1


# ============================================================================================ the note reader's tokens
#: One token of the note reader: a word of any script (apostrophes and hyphens inside it), a number, a line break, one
#: clause or sentence mark, or ANY other character on its own (a bracket, a quotation mark left after masking, a check
#: mark, an emoji, a combining mark), which no construction reads, so it is never dropped unread. Read on the text
#: normalised (NFKC, format characters such as zero-width spaces removed, curly apostrophes straightened, the markdown
#: emphasis marks "*" and "_" read as spaces).
_NOTE_TOKEN_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*(?:-[^\W\d_]+(?:'[^\W\d_]+)*)*|\d+(?:[.,]\d+)*|\n|[,;:.!?—–…]|\S")
#: Default-ignorable code points outside the format characters (category Cf, removed by category): the combining grapheme
#: joiner, the Hangul fillers, the Khmer inherent vowels, the Mongolian free variation selectors and the variation
#: selectors (their supplement, U+E0100 to U+E01EF, by range). A reader shows none of them, so none may split a word.
_IGNORABLE = frozenset(chr(c) for c in (0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180E, 0x180F, 0x3164, 0xFFA0, *range(0xFE00, 0xFE10)))


def _ignorable(ch: str) -> bool:
    """Whether ``ch`` is a format character (category Cf) or another default-ignorable code point (:data:`_IGNORABLE`)."""
    return ch in _IGNORABLE or 0xE0100 <= ord(ch) <= 0xE01EF or unicodedata.category(ch) == "Cf"


#: The Unicode tag characters (U+E0000 to U+E007F): format characters that spell ASCII no reader is shown. A block holding one
#: is never read as a note, a source list or layout (fail closed): removing them, as :func:`reader_text` does, would free the
#: visible words while the delivered text carries the hidden ones.
_TAG_CHARS_RE = re.compile("[" + chr(0xE0000) + "-" + chr(0xE007F) + "]")


def hides_text(text: str) -> bool:
    """Whether ``text`` holds a Unicode tag character (:data:`_TAG_CHARS_RE`): text a reader is not shown."""
    return _TAG_CHARS_RE.search(text or "") is not None


def reader_text(text: str) -> str:
    """``text`` as every reader of this module reads it (attack round 3): NFKC, every format character (category Cf: a
    zero-width space or joiner, a soft hyphen, a word joiner, a bidirectional mark, a byte-order mark) and every other
    default-ignorable code point (a combining grapheme joiner, a variation selector) removed, and every combining mark that
    does not belong to a letter removed (a mark after a letter, or after another mark on a letter, is the letter's and is
    kept). One linear pass; an ASCII text is returned as it is."""
    s = unicodedata.normalize("NFKC", text or "")
    if s.isascii():
        return s
    out: list[str] = []
    letter = False  # the last character kept is a letter (or a mark kept on one)
    for ch in s:
        if ch < "\x80":
            out.append(ch)
            letter = ch.isalpha()
            continue
        if _ignorable(ch):
            continue
        cat = unicodedata.category(ch)
        if cat[0] == "M":
            if letter:
                out.append(ch)
            continue
        out.append(ch)
        letter = cat[0] == "L"
    return "".join(out)


#: The confusable skeleton (attack round 4): letters of other scripts that a reader takes for a Latin letter, each read as that
#: letter wherever a lead or a label is read (``N`` and a Cyrillic ``о``, "Nоte:", is "Note:"): the Cyrillic, Greek, Armenian
#: and Cherokee look-alikes of Latin letters, the Latin small capitals ("ɴᴏᴛᴇ:") and the dotless i and j. Fullwidth and
#: mathematical letters, circled and superscript letters are read by NFKC first; a letter with a diacritic is read as its
#: base letter ("Ṇote:"). Digits are never mapped (a lead is words).
_CONFUSABLES: dict[str, str] = dict(pair for pair in (
    # Cyrillic
    ("А", "A"), ("В", "B"), ("Е", "E"), ("К", "K"), ("М", "M"), ("Н", "H"), ("О", "O"), ("Р", "P"), ("С", "C"), ("Т", "T"),
    ("У", "Y"), ("Х", "X"), ("Ѕ", "S"), ("І", "I"), ("Ј", "J"), ("Ү", "Y"), ("Һ", "H"), ("Ӏ", "I"), ("Ԛ", "Q"), ("Ԝ", "W"),
    ("Ѵ", "V"), ("Ԍ", "G"), ("а", "a"), ("в", "b"), ("е", "e"), ("к", "k"), ("м", "m"), ("н", "h"), ("о", "o"), ("р", "p"),
    ("с", "c"), ("т", "t"), ("у", "y"), ("х", "x"), ("ѕ", "s"), ("і", "i"), ("ј", "j"), ("һ", "h"), ("ԁ", "d"), ("ԛ", "q"),
    ("ԝ", "w"), ("ӏ", "l"), ("ү", "y"), ("ѵ", "v"),
    # Greek
    ("Α", "A"), ("Β", "B"), ("Ε", "E"), ("Ζ", "Z"), ("Η", "H"), ("Ι", "I"), ("Κ", "K"), ("Μ", "M"), ("Ν", "N"), ("Ο", "O"),
    ("Ρ", "P"), ("Τ", "T"), ("Υ", "Y"), ("Χ", "X"), ("Ϲ", "C"), ("Ϳ", "J"), ("Ϝ", "F"), ("α", "a"), ("γ", "y"), ("ε", "e"),
    ("η", "n"), ("ι", "i"), ("κ", "k"), ("ν", "v"), ("ο", "o"), ("ρ", "p"), ("τ", "t"), ("υ", "u"), ("χ", "x"), ("ϲ", "c"),
    ("ϳ", "j"),
    # Latin small capitals and look-alike letters
    ("ı", "i"), ("ȷ", "j"), ("ɑ", "a"), ("ɡ", "g"), ("ɩ", "i"), ("ɪ", "i"), ("ʟ", "l"), ("ɴ", "n"), ("ʀ", "r"), ("ʏ", "y"),
    ("ʙ", "b"), ("ɢ", "g"), ("ʜ", "h"), ("ᴀ", "a"), ("ᴄ", "c"), ("ᴅ", "d"), ("ᴇ", "e"), ("ᴊ", "j"), ("ᴋ", "k"), ("ᴍ", "m"),
    ("ᴏ", "o"), ("ᴘ", "p"), ("ᴛ", "t"), ("ᴜ", "u"), ("ᴠ", "v"), ("ᴡ", "w"), ("ᴢ", "z"), ("ꜰ", "f"), ("ꜱ", "s"),
    # Armenian and Cherokee
    ("օ", "o"), ("ս", "u"), ("ց", "g"), ("հ", "h"), ("ո", "n"), ("զ", "q"), ("Տ", "S"), ("Օ", "O"), ("Ս", "U"),
    ("Ꭺ", "A"), ("Ᏼ", "B"), ("Ꮯ", "C"), ("Ꭼ", "E"), ("Ꮐ", "G"), ("Ꮋ", "H"), ("Ꭻ", "J"), ("Ꮶ", "K"), ("Ꮮ", "L"), ("Ꮇ", "M"),
    ("Ꮲ", "P"), ("Ꮪ", "S"), ("Ꭲ", "T"), ("Ꮩ", "V"), ("Ꮃ", "W"), ("Ꮓ", "Z"),
))
@functools.lru_cache(maxsize=4096)
def _skeleton_char(ch: str) -> str:
    """The confusable skeleton of one character that is not ASCII (:data:`_CONFUSABLES`): a look-alike letter as its Latin
    letter, any other character read in NFKC, a letter with a diacritic as its base letter (its marks dropped), the result's
    look-alikes mapped again. Constant time (a bounded memo)."""
    got = _CONFUSABLES.get(ch)
    if got is not None:
        return got
    out: list[str] = []
    for c in unicodedata.normalize("NFKC", ch):
        m = _CONFUSABLES.get(c)
        if m is None and not c.isascii() and unicodedata.category(c)[0] == "L":
            base = "".join(d for d in unicodedata.normalize("NFKD", c) if unicodedata.category(d)[0] != "M")
            m = "".join(_CONFUSABLES.get(d, d) for d in base) or c
        out.append(c if m is None else m)
    return "".join(out)


def skeleton(text: str) -> str:
    """``text`` as the lead reader reads its letters (attack round 4): :func:`reader_text`, then every character that is not
    ASCII as its confusable skeleton (:func:`_skeleton_char`): "Nоte:" with a Cyrillic о, "Νote:" with a Greek Ν, "ɴᴏᴛᴇ:" and
    "Ṇote:" all read "Note:". Linear."""
    s = reader_text(text)
    return s if s.isascii() else "".join(ch if ch.isascii() else _skeleton_char(ch) for ch in s)


_EMPHASIS_RE = re.compile(r"[*_]")
_SENTENCE_END = frozenset({".", "!", "?", "…", "\n"})
_CLAUSE_BOUNDARY = frozenset({",", ";", ":", "—", "–"})
#: Contractions written out, so every reader sees "not" and the auxiliary ("isn't" -> "is not", "it's" -> "it is").
_EXPAND = {
    "it's": ("it", "is"), "that's": ("that", "is"), "there's": ("there", "is"), "here's": ("here", "is"), "what's": ("what", "is"),
    "who's": ("who", "is"), "i'm": ("i", "am"), "i've": ("i", "have"), "we've": ("we", "have"), "you've": ("you", "have"),
    "they've": ("they", "have"), "we're": ("we", "are"), "you're": ("you", "are"), "they're": ("they", "are"), "i'd": ("i", "would"),
    "we'd": ("we", "would"), "you'd": ("you", "would"), "they'd": ("they", "would"), "it'd": ("it", "would"), "i'll": ("i", "will"),
    "we'll": ("we", "will"), "you'll": ("you", "will"), "it'll": ("it", "will"), "they'll": ("they", "will"), "let's": ("let", "us"),
    "cannot": ("can", "not"), "can't": ("can", "not"), "won't": ("will", "not"), "shan't": ("shall", "not"), "ain't": ("is", "not"),
}
#: Pronouns whose "'s" is "is" ("everything's in order"), not a possessive.
_IS_CONTRACTED = frozenset({"everything", "nothing", "something", "anything", "all", "each", "everyone", "nobody", "this", "one", "none"})


def _normalise(text: str) -> str:
    text = reader_text(text)
    text = text.replace("’", "'").replace("‘", "'").replace("ʼ", "'").replace("`", "'")
    return _EMPHASIS_RE.sub(" ", text)


def _note_tokens(text: str) -> list[str]:
    """The note reader's tokens of ``text`` (lower case, contractions written out), in one linear scan."""
    out: list[str] = []
    for m in _NOTE_TOKEN_RE.finditer(_normalise(text)):
        t = m.group(0).lower()
        expanded = _EXPAND.get(t)
        if expanded is not None:
            out.extend(expanded)
        elif len(t) > 3 and t.endswith("n't"):
            out.extend((t[:-3], "not"))  # "isn't" -> "is not", "couldn't" -> "could not"
        elif t.endswith("'s") and t[:-2] in _IS_CONTRACTED:
            out.extend((t[:-2], "is"))
        else:
            out.append(t)
    return out


def _latin_only(tok: str) -> bool:
    """Whether every letter of ``tok`` is a Latin letter (for the record: a word with a letter of another script, a
    Cyrillic "о" inside "sоund", is named as a word the reader cannot read; no word list holds it anyway)."""
    return tok.isascii() or all(unicodedata.name(ch, "").startswith("LATIN") for ch in tok if ch.isalpha())


# ============================================================================================ rule evaluation-words
#: Rule ``evaluation-words``: words that evaluate the answer or a part of it, or name a fault, a repair, an agreement, a
#: grade or a commitment to it, read in ANY polarity and anywhere in the note (each part of a hyphenated word too): a note
#: carries none of them, whatever it says around them ("Note: all figures are sound", "not a single slip", "nothing to
#: fix", "the quotations are not unreliable"). The words of checking themselves are left to rule ``assurance-words``,
#: which reads their polarity ("not checked" is a disclaimer). English, then the Spanish and French forms (Language A
#: answers in those languages are read by the English branch).
_EVALUATION_WORDS = frozenset({
    # accuracy, truth, soundness and their opposites
    "accurate", "accurately", "accuracy", "inaccurate", "inaccurately", "inaccuracy", "inaccuracies", "correct", "correctly", "correctness",
    "incorrect", "incorrectly", "corrected", "correction", "corrections", "correcting", "exact", "exactly", "exactness", "inexact", "precise",
    "precisely", "precision", "imprecise", "imprecision", "right", "rightly", "wrong", "wrongly", "true", "truly", "truthful", "untrue", "false",
    "falsely", "faithful", "faithfully", "faithfulness", "unfaithful", "verbatim", "sound", "soundly", "soundness", "unsound", "solid", "solidly",
    "robust", "robustly", "robustness", "valid", "validly", "validity", "invalid", "reliable", "reliably", "reliability", "unreliable",
    "dependable", "trustworthy", "untrustworthy", "trust", "trusted", "trusting", "credible", "credibility", "believable", "rigorous",
    "rigorously", "rigour", "rigor", "firm", "firmly", "sturdy", "flawless", "flawlessly", "faultless", "faultlessly", "impeccable", "impeccably",
    "spotless", "perfect", "perfectly", "perfection", "immaculate", "pristine", "airtight", "watertight", "bulletproof", "infallible",
    "unimpeachable", "irreproachable", "unassailable", "incontrovertible", "indisputable", "indisputably", "undeniable", "undeniably",
    "unquestionable", "unquestionably", "conclusive", "conclusively", "definitive", "definitively", "definite", "definitely", "certain",
    "certainly", "certainty", "sure", "surely", "confident", "confidently", "confidence", "assured", "assurance", "assure", "assures",
    "guaranteed", "guarantee", "guarantees", "safe", "safely", "secure", "securely", "fine", "ok", "okay", "alright", "good", "great",
    "excellent", "fantastic", "brilliant", "superb", "outstanding", "strong", "stronger", "strongest", "clean", "cleanly", "tidy", "neat",
    "polished", "shipshape", "tiptop", "tip-top", "top-notch", "first-rate", "exemplary", "legit", "legitimate", "kosher", "proper",
    "properly", "sensible", "reasonable", "plausible", "defensible", "justified", "justifiable", "well-founded", "well-supported",
    "well-sourced", "well-grounded", "supported", "unsupported", "substantiated", "unsubstantiated", "consistent", "consistently",
    "consistency", "inconsistent", "inconsistency", "inconsistencies", "coherent", "coherence", "incoherent", "thorough", "thoroughly",
    "comprehensive", "comprehensively", "meticulous", "meticulously", "scrupulous", "scrupulously", "careful", "carefully", "diligent",
    "diligently", "painstaking", "authoritative", "reputable", "ideal", "ideally", "favourite", "favorite", "worthy", "deserve", "deserves",
    "deserved", "deserving", "merit", "merits", "impress", "impresses", "impressive", "commendable", "admirable", "praiseworthy", "ready",
    # faults and their absence
    "error", "errors", "erroneous", "error-free", "mistake", "mistakes", "mistaken", "mistake-free", "slip", "slips", "slip-free", "typo",
    "typos", "typo-free", "bug", "bugs", "glitch", "glitches", "gap", "gaps", "hole", "holes", "lapse", "lapses", "blunder", "blunders",
    "problem", "problems", "problematic", "issue", "issues", "discrepancy", "discrepancies", "omission", "omissions", "fault", "faults",
    "faulty", "flaw", "flaws", "flawed", "defect", "defects", "defective", "deficient", "deficiency", "shortcoming", "shortcomings",
    "misquote", "misquoted", "misquotes", "misquotation", "misquotations", "misread", "misreading", "misreport", "misreported", "miscount",
    "miscounted", "miscalculated", "miscalculation", "miscalculations", "misattributed", "misattribution", "fabricated", "fabrication",
    "fabrications", "invented", "made-up", "altered", "alteration", "alterations", "distorted", "distortion", "garbled", "doctored", "tampered",
    "bad", "poor", "weak", "weakness", "weaknesses", "shaky", "dubious", "doubtful", "doubt", "doubts", "undoubted", "undoubtedly",
    "questionable", "suspicious", "amiss", "awry", "astray",
    # repair (nothing to fix is an assurance), agreement, holding up, passing
    "fix", "fixes", "fixed", "fixing", "fixable", "amend", "amends", "amended", "amending", "amendment", "amendments", "tweak", "tweaks",
    "tweaked", "tweaking", "change", "changes", "changed", "changing", "unchanged", "alter", "alters", "altering", "hold", "holds", "held",
    "holding", "stand", "stands", "stood", "standing", "tally", "tallies", "tallying", "agree", "agrees", "agreed", "agreement",
    "agreeing", "mismatch", "mismatches", "align", "aligns", "aligned", "alignment", "pass", "passing", "survive", "survives", "survived",
    "withstand", "withstands", "endorse", "endorses", "endorsed", "endorsement", "approve", "approves", "approval", "vouch", "vouches",
    "vouched", "warrant", "warranted", "promise", "promises", "promised", "nailed", "nails", "works", "succeeds", "succeed", "excels", "excel",
    "shines", "shine", "convinces", "convincing", "persuasive", "satisfies", "satisfactory", "meets", "fulfils", "fulfills", "quality",
    "qualities", "love", "loves", "loved",
    # manner and appraisal ("how well it flows", "admire the craft"; "as well" is no evaluation)
    "well", "nicely", "smoothly", "beautifully", "elegantly", "effectively", "effective", "successfully", "successful", "convincingly",
    "persuasively", "fluently", "fluent", "flows", "enjoy", "enjoys", "admire", "admires", "proud", "pleased", "happy", "delighted",
    "satisfied", "polish", "flair", "masterful", "masterly", "skilful", "skillful", "skilfully", "skillfully", "expertly", "insightful",
    "sophisticated", "clever", "cleverly", "crisp", "slick", "seamless", "seamlessly", "compelling", "powerful", "tight", "best", "better",
    "exemplar", "stellar", "standout",
    # Spanish
    "correcto", "correcta", "correctos", "correctas", "correctamente", "exacto", "exacta", "exactos", "exactas", "exactamente", "exactitud",
    "preciso", "precisa", "precisos", "precisas", "precisión", "fiable", "fiables", "fiabilidad", "verdadero", "verdadera", "verdaderos",
    "verdaderas", "cierto", "cierta", "ciertos", "ciertas", "bien", "perfecto", "perfecta", "perfectos", "perfectas", "perfectamente",
    "impecable", "impecables", "sólido", "sólida", "sólidos", "sólidas", "válido", "válida", "válidos", "válidas", "errores", "errata",
    "erratas", "fallo", "fallos", "falta", "faltas", "equivocado", "equivocada", "incorrecto", "incorrecta", "inexacto", "inexacta",
    "comprobado", "comprobada", "comprobados", "comprobadas", "verificado", "verificada", "verificados", "verificadas", "revisado", "revisada",
    "revisados", "revisadas", "confirmado", "confirmada", "confirmados", "confirmadas", "coinciden", "coincide", "cuadran", "cuadra",
    "encajan", "encaja", "arreglar", "corregir", "corregido", "corregida", "corrección", "correcciones", "duda", "dudas", "seguro", "segura",
    "seguros", "seguras", "garantizado", "garantizada", "fiel", "fieles", "literal", "literales", "textual", "textuales", "intachable",
    "irreprochable", "riguroso", "rigurosa",
    # French
    "correcte", "corrects", "correctes", "correctement", "exacte", "exacts", "exactes", "exactement", "exactitude", "juste", "justes",
    "précis", "précise", "précises", "fiabilité", "vrai", "vraie", "vrais", "vraies", "parfait", "parfaite", "parfaits", "parfaites",
    "parfaitement", "solide", "solides", "valide", "valides", "erreur", "erreurs", "faute", "fautes", "coquille", "coquilles", "inexacte",
    "faux", "fausse", "fausses", "vérifié", "vérifiée", "vérifiés", "vérifiées", "contrôlé", "contrôlée", "contrôlés", "contrôlées", "relu",
    "relue", "relus", "relues", "confirmé", "confirmée", "confirmés", "confirmées", "conforme", "conformes", "fidèle", "fidèles",
    "fidèlement", "textuel", "textuelle", "textuels", "textuelles", "corriger", "corrigé", "corrigée", "doute", "doutes", "sûr", "sûre",
    "sûrs", "sûres", "certaine", "certains", "certaines", "garanti", "garantie", "irréprochables", "rigoureux", "rigoureuse",
})
#: Idioms of assurance (token sequences), any polarity: "holds water", "in order", "on the money", "checks out", "bang on".
_EVALUATION_PHRASES = (
    ("as", "is"), ("as", "it", "is"), ("as", "it", "stands"), ("as", "they", "are"), ("as", "they", "stand"), ("as", "it", "should", "be"),
    ("as", "they", "should", "be"), ("on", "the", "money"), ("on", "the", "nose"), ("on", "the", "button"), ("bang", "on"), ("dead", "on"),
    ("spot", "on"), ("on", "point"), ("on", "target"), ("above", "board"), ("in", "order"), ("in", "good", "order"), ("in", "good", "shape"),
    ("in", "shape"), ("good", "to", "go"), ("all", "set"), ("all", "good"), ("all", "fine"), ("all", "clear"), ("all", "correct"),
    ("present", "and", "correct"), ("nothing", "to", "see"), ("no", "worries"), ("add", "up"), ("adds", "up"), ("added", "up"),
    ("stack", "up"), ("stacks", "up"), ("stacked", "up"), ("check", "out"), ("checks", "out"), ("checked", "out"), ("bear", "out"),
    ("bears", "out"), ("borne", "out"), ("bore", "out"), ("back", "up"), ("backs", "up"), ("backed", "up"), ("line", "up"), ("lines", "up"),
    ("lined", "up"), ("tick", "every", "box"), ("ticks", "every", "box"), ("ticks", "all"), ("tick", "all"), ("word", "for", "word"),
    ("letter", "for", "letter"), ("to", "the", "letter"), ("word", "perfect"), ("rock", "solid"), ("right", "as", "rain"), ("clean", "bill"),
    ("beyond", "doubt"), ("beyond", "question"), ("beyond", "reproach"), ("no", "doubt"), ("in", "doubt"), ("real", "deal"),
    ("genuine", "article"), ("to", "the", "bank"), ("fit", "for", "purpose"), ("up", "to", "scratch"), ("up", "to", "standard"),
    ("up", "to", "the", "mark"), ("up", "to", "par"), ("squared", "away"), ("in", "the", "clear"), ("out", "of", "the", "woods"),
    ("full", "marks"), ("top", "marks"), ("full", "credit"), ("top", "band"), ("highest", "band"), ("maximum", "marks"), ("model", "answer"),
    ("model", "essay"), ("model", "paragraph"), ("model", "response"), ("pass", "muster"), ("passes", "muster"), ("cut", "the", "mustard"),
    ("make", "the", "grade"), ("makes", "the", "grade"), ("measure", "up"), ("measures", "up"), ("stand", "by"), ("stands", "by"),
    ("vouch", "for"), ("sign", "off"), ("signed", "off"), ("no", "need"), ("nothing", "needed"), ("needs", "nothing"), ("square", "with"),
    ("squares", "with"), ("in", "line", "with"), ("true", "to"), ("faithful", "to"), ("hang", "together"), ("hangs", "together"),
    ("holds", "together"), ("hold", "together"), ("ship", "shape"), ("tip", "top"), ("first", "class"), ("top", "notch"), ("all", "present"),
    # Spanish and French
    ("sin", "errores"), ("sin", "error"), ("nada", "que", "corregir"), ("todo", "en", "orden"), ("en", "orden"), ("al", "pie", "de", "la", "letra"),
    ("palabra", "por", "palabra"), ("sans", "erreur"), ("sans", "erreurs"), ("rien", "à", "corriger"), ("rien", "a", "corriger"), ("en", "ordre"),
    ("mot", "pour", "mot"), ("mot", "à", "mot"), ("à", "la", "lettre"), ("tout", "est", "bon"), ("tout", "est", "en", "ordre"),
)
_PHRASES_BY_FIRST: dict[str, tuple[tuple[str, ...], ...]] = {}
for _ph in _EVALUATION_PHRASES:
    _PHRASES_BY_FIRST[_ph[0]] = _PHRASES_BY_FIRST.get(_ph[0], ()) + (_ph,)
del _ph


def evaluation_words(text: str) -> list[str]:
    """The evaluation words and idioms of ``text`` (rule ``evaluation-words``; quotations should be masked by the caller),
    in any polarity: "sound", "slip", "fix", "in doubt", "holds", "in order", "on the money", "sin errores", "rien à
    corriger". Each part of a hyphenated or elided word is read too ("error-free", "l'erreur"). One linear scan (an idiom is
    at most five tokens)."""
    toks = [t for t in _note_tokens(text) if t not in _SENTENCE_END and t not in _CLAUSE_BOUNDARY]
    found: list[str] = []
    n = len(toks)
    for i, t in enumerate(toks):
        for ph in _PHRASES_BY_FIRST.get(t, ()):
            if tuple(toks[i:i + len(ph)]) == ph and not (ph == ("in", "order") and i + 2 < n and toks[i + 2] == "to"):
                found.append(" ".join(ph))  # "in order to" is a purpose, not an assurance
        if t in _EVALUATION_WORDS and not (t == "well" and i and toks[i - 1] == "as"):
            found.append(t)
        elif "-" in t or "'" in t:
            found += [p for p in re.split(r"[-']", t) if p in _EVALUATION_WORDS]
    return found


# ============================================================================================ rule note-clauses
# The closed allowlist. Every word a construction reads comes from one of the lists below; a word no list holds (an unlisted
# synonym, a misspelling, a look-alike letter, a word of another language) is read by no construction, so the clause and the
# paragraph are a self-report. There is no open slot: no "any noun phrase", no "any prepositional phrase".

#: What joins two constructions in one clause, and what may open a clause before its construction ("so", "and then").
_JOINERS = frozenset({"and", "or", "so", "but", "then"})
#: Negators, named for the record of rule ``bare-negator`` (a negator outside (b) and (c)): English, then Spanish and
#: French; "n't" is written out as "not".
_NOTE_NEGATORS = frozenset({"not", "no", "nothing", "none", "never", "nobody", "noone", "neither", "nor", "without", "zero", "nowhere", "hardly",
                            "scarcely", "barely", "ni", "nada", "ningún", "ninguna", "ninguno", "nunca", "jamás", "sin", "tampoco", "nadie", "ne",
                            "pas", "rien", "aucun", "aucune", "jamais", "sans", "nul", "nulle"})

# ---------------------------------------------------------------------------- (a) study-suggestion
#: Words that may open a suggestion before its verb ("now plan ...", "first write ...", "please paste ...").
_SUGGESTION_LEADS = frozenset({"then", "now", "first", "next", "also", "finally", "afterwards", "later", "today", "tomorrow", "secondly", "lastly",
                               "please"})
#: The verbs of a study suggestion: the student's own reading, writing and practice. No verb of using, keeping, copying,
#: submitting, ranking, marking, treating or appraising the answer ("use", "keep", "copy", "submit", "treat", "mark",
#: "rank", "see", "notice", "enjoy", "admire", "follow", "take"), none of reproducing it ("redraw") and none of learning it
#: by heart ("learn", "memorise", "rehearse": what a student learns by heart from a note is the answer's content, an
#: endorsement of it).
_SUGGESTION_VERBS = frozenset({
    "write", "rewrite", "re-write", "redraft", "draft", "plan", "paste", "send", "annotate", "underline", "highlight", "read", "reread", "re-read",
    "check", "compare", "list", "outline", "sketch", "attempt", "answer", "analyse", "analyze", "label", "identify", "summarise", "summarize",
    "find", "choose", "pick", "select", "add", "expand", "shorten", "edit", "rework", "redo", "solve", "calculate", "draw", "plot",
    "prepare", "complete", "finish", "start", "begin", "try", "practise", "practice", "revise", "time", "test", "explain", "describe",
    "compose", "translate", "paraphrase",
})
#: The verbs of practice: their object is only the student's OWN work ("revise your own notes"), a question ("practise
#: question 3") or a practice item ("practise a past paper"), never a pronoun, a passage, a piece of writing or "your"
#: work without "own" ("revise your notes", "practise your speech": what the note hands the student may be the answer).
_PRACTICE_VERBS = frozenset({"practise", "practice", "revise"})
#: The verbs of sending: their phrase must send the work back to the tutor ("paste it here", "send them back", "send it
#: for feedback", "for a second provisional mark"); a bare "send your essay" can be its submission.
_SEND_VERBS = frozenset({"paste", "send"})
_SEND_DESTINATIONS = frozenset({"here", "back", "feedback", "comments", "comment", "mark"})
#: What joins a second verb phrase to a suggestion ("... and paste it here", "..., then time yourself").
_SUGGESTION_JOIN = frozenset({"and", "or", "then", "so"})
#: The student's own work, after "your" ("your own paragraph", "your quotations", "your topic sentence").
_WORK_SG = frozenset({"paragraph", "sentence", "version", "answer", "essay", "analysis", "plan", "draft", "response", "introduction", "conclusion",
                      "thesis", "argument", "commentary", "comparison", "summary", "outline", "explanation", "interpretation", "reading",
                      "translation", "calculation", "working", "method", "graph", "table", "diagram", "timeline", "list", "question", "quotation",
                      "quote", "example", "point", "attempt", "speech", "letter", "story", "poem", "article", "opening", "ending", "title", "sketch",
                      "chart"})
_WORK_PL = frozenset({"paragraphs", "sentences", "versions", "answers", "essays", "analyses", "plans", "drafts", "responses", "introductions",
                      "conclusions", "arguments", "summaries", "outlines", "explanations", "interpretations", "readings", "translations",
                      "calculations", "methods", "graphs", "tables", "diagrams", "lists", "questions", "quotations", "quotes", "examples", "points",
                      "attempts", "notes", "words", "figures", "dates", "references", "ideas", "results", "values", "labels", "lines", "titles",
                      "sketches", "charts"})
_WORK_MODS = frozenset({"own", "topic", "first", "second", "third", "next", "new", "short", "rough", "practice", "two", "three", "opening",
                        "closing", "revised", "written", "key"})
#: A generic study item, after "a", "another", "one", "two" ... ("a practice question", "one quotation", "two more quotations").
_GENERIC_DETS = frozenset({"a", "an", "another", "one", "two", "three", "four", "five"})
_GENERIC_MODS = frozenset({"more", "new", "short", "rough", "timed", "practice", "past", "first", "second", "third", "single", "fresh", "different",
                           "sample", "mock", "further", "extra", "topic"})
_GENERIC_SG = _WORK_SG | frozenset({"paper", "exercise", "task"})
_GENERIC_PL = _WORK_PL | frozenset({"papers", "exercises", "tasks"})
#: A practice item, the object of a verb of practice ("two more questions", "a past paper", "a timed exercise"): never a
#: piece of writing ("revise one paragraph", "practise an essay": which one may be the answer's own).
_PRACTICE_SG = frozenset({"question", "paper", "exercise", "task"})
_PRACTICE_PL = frozenset({"questions", "papers", "exercises", "tasks"})
#: A study item a student draws from a source, after "using" ("using one quotation and its effect"): never an answer,
#: an essay, a paragraph, a figure or a date (what "using" would take from the answer itself).
_ITEM_SG = frozenset({"quotation", "quote", "example", "technique", "device", "detail"})
_ITEM_PL = frozenset({"quotations", "quotes", "examples", "techniques", "devices", "details"})
#: The STRICT list of the supplied source, after "the": the only passages a suggestion may take as its object or as a
#: yardstick ("against", "with", "in", "using", "test yourself on"): words that name material a task supplies and never a
#: written answer or a part of one. Every word that can name the answer's own part ("the table", "the text", "the
#: opening", "the lines", "the section", "the passage" of a descriptive-writing task, "the poem" or "the stanza" of a
#: creative one, "the article", "the letter", "the speech", "the worksheet", "the handout") is outside it: a suggestion
#: that learns, checks against or compares with such a part endorses the answer.
_STRICT_SOURCE_SG = frozenset({"extract", "excerpt", "source", "image", "picture", "photo", "photograph", "cartoon", "census", "dataset", "textbook",
                               "attachment", "recording", "video", "clip", "novel", "play"})
_STRICT_SOURCE_PL = frozenset({"extracts", "excerpts", "sources", "images", "pictures", "photos", "photographs", "cartoons", "textbooks", "attachments",
                               "recordings", "videos", "clips", "novels", "plays"})
#: A passage or feature of the source as a TOPIC only (what the student's own work is on or about, "on the final section",
#: "focusing on the verbs"), and the source a writer could not see or open (construction (b)): never the answer, its
#: paragraphs, sentences, quotations, figures or dates, and never "the essay" or "the model". A topic is never a yardstick
#: and never names what "it" or "them" refers to.
_SOURCE_SG = frozenset({"extract", "excerpt", "passage", "poem", "stanza", "line", "section", "chapter", "scene", "act", "text", "source", "table",
                        "image", "picture", "photo", "photograph", "diagram", "chart", "graph", "map", "cartoon", "poster", "advert", "advertisement",
                        "article", "novel", "play", "story", "opening", "ending", "title", "caption", "transcript", "recording", "video", "clip",
                        "speech", "document", "census", "dataset", "page", "handout", "worksheet", "textbook", "book", "attachment", "file", "link",
                        "website", "library", "mylib", "verse", "chorus", "narrator", "speaker", "setting", "structure", "tone", "rhythm", "rhyme",
                        "punctuation", "imagery", "dialogue", "character", "infographic", "slide", "scan", "letter", "diary", "memoir"})
_SOURCE_PL = frozenset({"extracts", "excerpts", "passages", "poems", "stanzas", "lines", "sections", "chapters", "scenes", "texts", "sources",
                        "tables", "images", "pictures", "photos", "photographs", "diagrams", "charts", "graphs", "maps", "cartoons", "posters",
                        "adverts", "articles", "captions", "transcripts", "recordings", "videos", "clips", "documents", "pages", "handouts",
                        "textbooks", "books", "attachments", "files", "links", "websites", "verbs", "nouns", "adjectives", "adverbs", "pronouns",
                        "metaphors", "similes", "symbols", "motifs", "verses", "characters", "slides", "scans", "letters", "speeches"})
_SOURCE_MODS = frozenset({"first", "second", "third", "fourth", "final", "last", "other", "next", "opening", "closing", "two", "three",
                          "original", "supplied"})
#: A topic after "the same" ("on the same two strands").
_TOPIC_SG = frozenset({"strand", "theme", "idea", "technique", "device", "point", "feature", "concept", "question", "method", "skill", "focus"})
_TOPIC_PL = frozenset({"strands", "themes", "ideas", "techniques", "devices", "points", "features", "concepts", "questions", "methods", "skills"})
_NUMBER_WORDS = frozenset({"two", "three", "four", "five", "six"})
#: What "its" or "their" may name after a noun phrase of the suggestion's own sentence ("one quotation and ITS effect").
_ASPECT_SG = frozenset({"effect", "meaning", "purpose", "context", "technique", "impact"})
_ASPECT_PL = frozenset({"effects", "meanings", "purposes", "techniques", "contexts"})
#: What may follow a suggestion's object (with the phrases :func:`_adjuncts` reads).
_PLACE_ADVERBS = frozenset({"here", "below", "again", "aloud", "now", "today", "tomorrow", "later", "first", "back", "next", "once", "twice"})
_FEEDBACK_MODS = frozenset({"second", "provisional", "quick", "written", "short", "more", "further", "fresh"})
#: "for feedback", "for comments"; a mark only a provisional one ("for a second provisional mark"): "for marking" or "for a
#: mark" can be a submission of the answer to the student's teacher.
_FEEDBACK_HEADS = frozenset({"feedback", "comments", "comment"})
_DURATION_UNITS = frozenset({"minutes", "minute", "mins", "min", "hours", "hour"})
_TIME_OPENERS = frozenset({"before", "after", "when", "once"})
_TIME_VERBS = frozenset({"submit", "start", "begin", "finish", "continue", "write"})
#: What may open a clause that continues the sentence's suggestion (", using one quotation and its effect").
_CONTINUATION_OPENERS = frozenset({"using", "focusing", "focussing", "concentrating"}) | _TIME_OPENERS
#: The kinds of noun phrase each slot of a suggestion takes: "own" ("your own paragraph"), "your" ("your quotations",
#: the student's work, which may also be what the note hands over), "generic" ("a practice question"), "practice" and
#: "item" (their narrower heads), "question" ("question 2"), "source" (the strict list), "topic-source" (the topic list),
#: "topic" ("the same two strands") and "aspect" ("its effect", after a phrase of its number).
_OBJECT_KINDS = frozenset({"own", "your", "generic", "question", "source", "aspect"})
_PRACTICE_KINDS = frozenset({"own", "practice", "question"})
_TOPIC_KINDS = frozenset({"own", "your", "generic", "question", "topic", "topic-source", "aspect"})
_YARDSTICK_KINDS = frozenset({"own", "source"})
_YOURSELF_KINDS = frozenset({"question", "practice", "source"})
_USING_KINDS = frozenset({"own", "item", "source", "aspect"})
_FOCUS_KINDS = frozenset({"topic", "topic-source"})

# ---------------------------------------------------------------------------- (b) no-access
#: A negated perception or access verb, in its base form (after "can't", "could not", "don't", "unable to", "not able to")
#: and as a participle (after "have not").
_ACCESS_BASE = frozenset({"see", "read", "open", "access", "have", "view", "hear"})
_ACCESS_PARTICIPLES = frozenset({"seen", "read", "opened", "accessed", "had", "viewed", "heard"})
#: A NAMED source: a definite determiner is required ("the image", "your attachment"; the one bare name is "MyLib"). An
#: indefinite or bare one ("I can't see a second source", "I don't have sources") names no source and can be read as a
#: search that found nothing.
_ACCESS_DETS = frozenset({"the", "your", "this", "that", "these", "those"})
_BARE_SOURCE_NAMES = frozenset({"mylib"})
#: What may qualify the named source ("the FULL extract", "the ATTACHED file", "the TEXTBOOK library"); "#" admits a number.
_ACCESS_MODS = frozenset({"#", "full", "original", "attached", "linked", "uploaded", "pasted", "supplied", "scanned", "printed", "first", "second",
                          "third", "other", "school", "textbook", "course", "source", "audio", "video", "online"})
#: The only phrases that may follow the source: "here", "yet", "in this session", "in this chat", "in your message".
_ACCESS_TAILS = frozenset({("this", "session"), ("this", "chat"), ("your", "message")})
_FIRST_PERSON_BE = frozenset({"am", "are", "was", "were"})

# ---------------------------------------------------------------------------- (c) not-checked
_CONTENT_DETS = frozenset({"the", "these", "those", "this", "that", "my", "our"})
#: What may qualify the named content ("the CASUALTY figures", "the 1924 VOTE share"); "#" admits a number. No word of
#: extent, fidelity or finality ("all", "exact", "final", "official"), and no word that sets the content against the rest
#: of the answer ("the REMAINING figures", "the OTHER dates", "the SECOND date", "the LATER figures"): such a note says
#: the rest was checked.
_CONTENT_MODS = frozenset({"#", "casualty", "census", "population", "emigration", "immigration", "vote", "price", "sales", "trade", "tax", "growth",
                           "historical", "numerical", "background", "contextual", "biographical", "page", "line", "visual", "key", "main", "two",
                           "three", "cited", "quoted", "economic", "financial", "monthly", "annual", "yearly", "survey", "sample", "average",
                           "percentage", "turnout", "death", "birth", "production", "export", "import", "income", "unemployment", "inflation",
                           "interest", "exchange"})
_CONTENT_SG = frozenset({"date", "figure", "quotation", "quote", "total", "number", "value", "statistic", "calculation", "citation", "reference",
                         "spelling", "translation", "name", "detail", "point", "share", "rate", "estimate", "count", "year", "source", "fact", "claim"})
_CONTENT_PL = frozenset({"dates", "figures", "quotations", "quotes", "totals", "numbers", "values", "statistics", "calculations", "citations",
                         "references", "spellings", "translations", "names", "details", "points", "shares", "rates", "estimates", "counts", "years",
                         "sources", "facts", "claims"})
_BE_STATUS = frozenset({"is", "are", "was", "were", "remain", "remains", "remained"})
#: The only predicates of (c): a negative status, or a negated participle of checking.
_NEG_STATUS = frozenset({"unchecked", "unverified", "unconfirmed"})
_CHECK_PART = frozenset({"checked", "verified", "confirmed"})

# ---------------------------------------------------------------------------- the record of a refusal
_ANSWER_PRONOUNS = frozenset({"it", "this", "these", "those", "that", "everything", "all", "each", "every", "both", "any", "they"})
_ANSWER_DETS = frozenset({"the", "my", "our", "this", "these", "those", "its", "their"})
_ANSWER_NOUNS = _CONTENT_SG | _CONTENT_PL | frozenset({"answer", "answers", "response", "essay", "analysis", "reasoning", "argument", "working",
                                                       "workings", "work", "paragraph", "paragraphs", "sentence", "sentences", "summary",
                                                       "version", "wording", "conclusion", "thesis", "evidence", "model", "reading"})

#: The clause kinds: the three constructions and what continues a suggestion in its sentence.
SUGGESTION_KINDS = frozenset({SUGGESTION_RULE})
LIMITATION_KINDS = frozenset({NO_ACCESS_RULE, NOT_CHECKED_RULE})
_CONTINUED = SUGGESTION_RULE + "-continued"


@dataclass(frozen=True)
class NoteReading:
    """How rule ``meta-note`` read one meta-text paragraph: ``note`` when it is positively read as a note; ``lead`` the kind
    of its bare note lead ("next" for "Next step(s):", "note" for every other lead, "" for none); ``clauses`` the kind the
    reader gave each construction it read, in order (``study-suggestion``, ``study-suggestion-continued``, ``no-access``,
    ``not-checked``); ``rule`` and ``detail`` the rule that keeps it a self-report and what that rule read ("" when it is a
    note)."""

    note: bool
    lead: str = ""
    clauses: tuple[str, ...] = ()
    rule: str = ""
    detail: str = ""


@dataclass
class _Sentence:
    """What the earlier clauses of a sentence established: whether a study suggestion is open (a continuation may follow
    it), and the numbers of the noun phrases its suggestions named ("it" or "its" needs a singular one before it, "them"
    or "their" a plural one)."""

    suggestion: bool = False
    singular: bool = False
    plural: bool = False

    def saved(self) -> tuple[bool, bool, bool]:
        return self.suggestion, self.singular, self.plural

    def restore(self, saved: tuple[bool, bool, bool]) -> None:
        self.suggestion, self.singular, self.plural = saved


def _at(c: list[str], k: int) -> str:
    return c[k] if 0 <= k < len(c) else ""


def _is_number(tok: str) -> bool:
    return tok[:1].isdigit()


def _negates(tok: str) -> bool:
    return tok in _NOTE_NEGATORS or tok.startswith("n'")


def _phrase(c: list[str], k: int, dets: frozenset, mods: frozenset, sg: frozenset, pl: frozenset, *, det_required: bool) -> tuple[int, str]:
    """A noun phrase at ``k``: a determiner of ``dets`` (required, or optional), at most three modifiers of ``mods`` ("#"
    there admits a number) and a head of ``sg`` or ``pl``: ``(end, "sg" or "pl")``, or ``(-1, "")``. At most five tokens
    are looked at, so a phrase costs a constant."""
    j = k
    if _at(c, j) in dets:
        j += 1
    elif det_required:
        return -1, ""

    def mod(x: str) -> bool:
        return x in mods or ("#" in mods and _is_number(x))

    run = j
    while run < len(c) and run - j < 4 and (mod(c[run]) or c[run] in sg or c[run] in pl):
        run += 1
    while run > j:  # the head is the last word of the run, every word before it a modifier (at most four tries)
        head = c[run - 1]
        if (head in sg or head in pl) and all(mod(x) for x in c[j:run - 1]):
            return run, ("sg" if head in sg else "pl")
        run -= 1
    return -1, ""


# ---------------------------------------------------------------------------- (a) study-suggestion
def _question_ref(c: list[str], k: int) -> int:
    """"question 2", "questions 1 to 5": the end, or -1."""
    if _at(c, k) not in ("question", "questions") or not _is_number(_at(c, k + 1)):
        return -1
    e = k + 2
    if _at(c, e) in ("to", "and", "or") and _is_number(_at(c, e + 1)):
        e += 2
    return e


def _one_np(c: list[str], k: int, st: _Sentence, kinds: frozenset, *, bind: bool = True) -> int:
    """One noun phrase of a suggestion of the ``kinds`` allowed at ``k`` (``_OBJECT_KINDS`` and its siblings name them: the
    student's own work, "your" work, a generic, practice or study item, a question, a passage of the strict source list,
    a topic or a passage of the topic list, or "its"/"their" with an aspect after a phrase of that number): its end, or
    -1. A phrase read where ``bind`` holds records its number for a later "it", "them", "its" or "their" (a topic never
    does: in "write your own paragraph on the table and check it", "it" can only be the paragraph)."""
    t = _at(c, k)
    e, num = -1, ""
    if t == "your":
        if "your" in kinds or ("own" in kinds and _at(c, k + 1) == "own"):
            e, num = _phrase(c, k, frozenset({"your"}), _WORK_MODS, _WORK_SG, _WORK_PL, det_required=True)
    elif t in _GENERIC_DETS:
        if "generic" in kinds:
            e, num = _phrase(c, k, _GENERIC_DETS, _GENERIC_MODS, _GENERIC_SG, _GENERIC_PL, det_required=True)
        elif "practice" in kinds:
            e, num = _phrase(c, k, _GENERIC_DETS, _GENERIC_MODS, _PRACTICE_SG, _PRACTICE_PL, det_required=True)
        elif "item" in kinds:
            e, num = _phrase(c, k, _GENERIC_DETS, _GENERIC_MODS, _ITEM_SG, _ITEM_PL, det_required=True)
    elif t == "the" and _at(c, k + 1) == "same":
        if "topic" in kinds:
            j = k + 2
            if _at(c, j) in _NUMBER_WORDS or _is_number(_at(c, j)):
                j += 1
            h = _at(c, j)
            e, num = (j + 1, "sg") if h in _TOPIC_SG else (j + 1, "pl") if h in _TOPIC_PL else (-1, "")
    elif t == "the":
        if "topic-source" in kinds:
            e, num = _phrase(c, k, frozenset({"the"}), _SOURCE_MODS, _SOURCE_SG, _SOURCE_PL, det_required=True)
        elif "source" in kinds:
            e, num = _phrase(c, k, frozenset({"the"}), _SOURCE_MODS, _STRICT_SOURCE_SG, _STRICT_SOURCE_PL, det_required=True)
    elif t in ("question", "questions"):
        if "question" in kinds:
            e, num = _question_ref(c, k), ("sg" if t == "question" else "pl")
    elif (t == "its" and st.singular) or (t == "their" and st.plural):
        if "aspect" in kinds:
            e, num = _phrase(c, k, frozenset({t}), frozenset(), _ASPECT_SG, _ASPECT_PL, det_required=True)
    if e < 0:
        return -1
    if bind:
        if num == "sg":
            st.singular = True
        else:
            st.plural = True
    return e


def _np_list(c: list[str], k: int, st: _Sentence, kinds: frozenset, *, bind: bool = True) -> int:
    """One noun phrase of ``kinds`` at ``k`` and its coordinates after "and"/"or" ("one quotation and its effect"): the end,
    or -1. An "and" that opens no such phrase is left to the caller (a joined verb phrase or construction)."""
    e = _one_np(c, k, st, kinds, bind=bind)
    if e < 0:
        return -1
    while _at(c, e) in ("and", "or"):
        e2 = _one_np(c, e + 1, st, kinds, bind=bind)
        if e2 < 0:
            break
        e = e2
    return e


def _for_phrase(c: list[str], k: int) -> int:
    """After "for": feedback ("for feedback", "for a second provisional mark": a mark only a provisional one) or a duration
    ("for 45 minutes")."""
    j = k
    if _at(c, j) in ("a", "an", "some"):
        j += 1
    m = 0
    while m < 3 and _at(c, j) in _FEEDBACK_MODS:
        j += 1
        m += 1
    if _at(c, j) in _FEEDBACK_HEADS or (_at(c, j) == "mark" and "provisional" in c[k:j]):
        return j + 1
    if _is_number(_at(c, k)) and _at(c, k + 1) in _DURATION_UNITS:
        return k + 2
    return -1


def _time_clause(c: list[str], k: int, st: _Sentence) -> int:
    """"before you submit", "once you finish your draft": the end, or -1."""
    if _at(c, k) not in _TIME_OPENERS or _at(c, k + 1) != "you" or _at(c, k + 2) not in _TIME_VERBS:
        return -1
    e = k + 3
    t = _at(c, e)
    if (t == "it" and st.singular) or (t == "them" and st.plural):
        return e + 1
    if t == "your":
        e2 = _one_np(c, e, st, frozenset({"own", "your"}))
        if e2 > 0:
            return e2
    return e


def _adjuncts(c: list[str], k: int, st: _Sentence, *, yourself: bool = False) -> int:
    """The closed phrases that may follow a suggestion's object, from ``k``: the end of the last one read (``k`` when none
    is). A topic ("on", "about", "focusing on") takes the topic list and binds no pronoun; a yardstick ("against", "with",
    "in") takes only the student's own work or the strict source list, and so does "on" after "time/test yourself" (what
    the student tests themself on is learnt by heart); "using" takes the student's own work, a study item or the strict
    source list. Each phrase reads at least one token, so the loop is linear."""
    while k < len(c):
        t = c[k]
        e = -1
        if t in _TIME_OPENERS and _at(c, k + 1) == "you":
            e = _time_clause(c, k, st)
        elif t in _PLACE_ADVERBS:
            e = k + 1
        elif t == "for":
            e = _for_phrase(c, k + 1)
        elif t in ("on", "about"):
            e = _np_list(c, k + 1, st, _YOURSELF_KINDS if yourself else _TOPIC_KINDS, bind=False)
        elif t in ("against", "with", "in"):
            e = _np_list(c, k + 1, st, _YARDSTICK_KINDS)
        elif t == "to":
            e = _question_ref(c, k + 1)
        elif t == "using":
            e = _np_list(c, k + 1, st, _USING_KINDS)
        elif t in ("focusing", "focussing", "concentrating") and _at(c, k + 1) == "on":
            e = _np_list(c, k + 2, st, _FOCUS_KINDS, bind=False)
        if e < 0:
            return k
        k = e
    return k


def _verb_phrase(c: list[str], j: int, st: _Sentence) -> int:
    """A verb of a suggestion at ``j``, its object and its adjuncts: the end, or -1. The object is required: the
    student's own work ("your" work too, but for a verb of practice only "your own"), a generic study item (for a verb of
    practice only a practice item), a passage of the strict source list (never after a verb of practice), a question,
    "yourself" (after "time" or "test"), or "it"/"them" after a noun phrase of the sentence of that number (never after a
    verb of practice). A verb of sending must send the work back to the tutor (``_SEND_DESTINATIONS`` among its
    adjuncts: "paste it here for feedback")."""
    verb = c[j]
    k = j + 1
    t = _at(c, k)
    if verb in _PRACTICE_VERBS:
        k = _np_list(c, k, st, _PRACTICE_KINDS)
        return _adjuncts(c, k, st) if k >= 0 else -1
    if t == "yourself" and verb in ("time", "test"):
        return _adjuncts(c, k + 1, st, yourself=True)
    if (t == "it" and st.singular) or (t == "them" and st.plural):
        k += 1
    else:
        k = _np_list(c, k, st, _OBJECT_KINDS)
        if k < 0:
            return -1
    e = _adjuncts(c, k, st)
    if verb in _SEND_VERBS and not any(x in _SEND_DESTINATIONS for x in c[k:e]):
        return -1  # "send your essay", "send it to your teacher": no destination back to the tutor
    return e


def _suggestion(c: list[str], i: int, st: _Sentence) -> int:
    """Construction (a) ``study-suggestion`` at ``i``: at most two leads ("now", "first"), then one or more verb phrases
    joined by "and", "or", "then" or "so" ("write your own paragraph ... and paste it here for feedback"): the end, or -1."""
    j = i
    k = 0
    while k < 2 and _at(c, j) in _SUGGESTION_LEADS:
        j += 1
        k += 1
    if _at(c, j) not in _SUGGESTION_VERBS:
        return -1
    while True:
        e = _verb_phrase(c, j, st)
        if e < 0:
            return -1
        m = e
        k = 0
        while k < 2 and _at(c, m) in _SUGGESTION_JOIN:
            m += 1
            k += 1
        if k and _at(c, m) in _SUGGESTION_VERBS:
            j = m
            continue
        st.suggestion = True
        return e


def _continuation(c: list[str], i: int, st: _Sentence) -> int:
    """What continues the sentence's suggestion in a clause of its own: "using ...", "focusing on ...", "before you
    submit" (and the adjuncts after it): the end, or -1."""
    if not st.suggestion or _at(c, i) not in _CONTINUATION_OPENERS:
        return -1
    e = _adjuncts(c, i, st)
    return e if e > i else -1


# ---------------------------------------------------------------------------- (b) no-access
def _named_source(c: list[str], k: int) -> int:
    """One NAMED source at ``k``: a definite determiner, closed modifiers and a source of the topic list ("the full
    extract", "your attachment"), or the bare name "MyLib": the end, or -1."""
    if _at(c, k) in _BARE_SOURCE_NAMES:
        return k + 1
    e, _num = _phrase(c, k, _ACCESS_DETS, _ACCESS_MODS, _SOURCE_SG, _SOURCE_PL, det_required=True)
    return e


def _source_object(c: list[str], k: int) -> int:
    """The named source(s) a writer could not see or open, and the closed tail after them: the end, or -1."""
    e = _named_source(c, k)
    if e < 0:
        return -1
    while _at(c, e) in ("and", "or"):
        e2 = _named_source(c, e + 1)
        if e2 < 0:
            break
        e = e2
    for _ in range(2):
        if _at(c, e) in ("here", "yet"):
            e += 1
        elif _at(c, e) == "in" and (_at(c, e + 1), _at(c, e + 2)) in _ACCESS_TAILS:
            e += 3
        else:
            break
    return e


def _no_access(c: list[str], i: int) -> int:
    """Construction (b) ``no-access`` at ``i``: "I" or "we", a negated perception or access verb and a named source
    ("I can't see the image", "we could not open the attachment", "I don't have the full extract", "I have not seen the
    image", "I was unable to open the file", "I have no access to the textbook library or MyLib"): the end, or -1."""
    if _at(c, i) not in ("i", "we"):
        return -1
    j = i + 1
    a, b = _at(c, j), _at(c, j + 1)
    if a in ("have", "had") and b == "no" and _at(c, j + 2) == "access" and _at(c, j + 3) == "to":
        return _source_object(c, j + 4)
    if a in ("can", "could", "do", "does", "did") and b == "not":
        k, base = j + 2, True
    elif a in ("have", "has", "had") and b == "not":
        k, base = j + 2, False
        if _at(c, k) == "yet":
            k += 1
    elif a in _FIRST_PERSON_BE and b == "unable" and _at(c, j + 2) == "to":
        k, base = j + 3, True
    elif a in _FIRST_PERSON_BE and b == "not" and _at(c, j + 2) == "able" and _at(c, j + 3) == "to":
        k, base = j + 4, True
    else:
        return -1
    v = _at(c, k)
    if v == ("have" if base else "had") and _at(c, k + 1) == "access" and _at(c, k + 2) == "to":
        return _source_object(c, k + 3)  # "I don't have access to MyLib", "I have not had access to the textbook"
    if v not in (_ACCESS_BASE if base else _ACCESS_PARTICIPLES):
        return -1
    return _source_object(c, k + 1)


# ---------------------------------------------------------------------------- (c) not-checked
def _coordinated(c: list[str], k: int, words: frozenset) -> int:
    """The end of the word at ``k`` (one of ``words``) and its coordinates ("unchecked and unverified")."""
    e = k + 1
    while _at(c, e) in ("and", "or") and _at(c, e + 1) in words:
        e += 2
    return e


def _not_checked(c: list[str], i: int) -> int:
    """Construction (c) ``not-checked`` at ``i``: named content of the answer whose only predicate is a status of not
    checked ("the dates are unchecked here", "the figures are not verified", "the quotations have not been checked",
    "the 1924 vote share could not be confirmed"): the end, or -1."""
    e, _num = _phrase(c, i, _CONTENT_DETS, _CONTENT_MODS, _CONTENT_SG, _CONTENT_PL, det_required=True)
    if e < 0:
        return -1
    while _at(c, e) in ("and", "or"):  # "the dates and figures", "the dates and the totals"
        e2, _num = _phrase(c, e + 1, _CONTENT_DETS, _CONTENT_MODS, _CONTENT_SG, _CONTENT_PL, det_required=False)
        if e2 < 0:
            break
        e = e2
    j = e + 1 if _at(c, e) in ("here", "above", "below") else e
    v, w = _at(c, j), _at(c, j + 1)
    k = -1
    if v in _BE_STATUS and w in _NEG_STATUS:
        k = _coordinated(c, j + 1, _NEG_STATUS)
    elif v in _BE_STATUS and w == "not":
        m = j + 2 + (_at(c, j + 2) == "yet")
        if _at(c, m) in _CHECK_PART:
            k = _coordinated(c, m, _CHECK_PART)
    elif v in ("has", "have", "had") and w == "not":
        m = j + 2 + (_at(c, j + 2) == "yet")
        if _at(c, m) == "been" and _at(c, m + 1) in _CHECK_PART:
            k = _coordinated(c, m + 1, _CHECK_PART)
    elif v in ("can", "could") and w == "not" and _at(c, j + 2) == "be" and _at(c, j + 3) in _CHECK_PART:
        k = _coordinated(c, j + 3, _CHECK_PART)
    if k < 0:
        return -1
    for _ in range(2):
        if _at(c, k) in ("here", "yet"):
            k += 1
    return k


# ---------------------------------------------------------------------------- the clauses
def _read_clause(c: list[str], st: _Sentence) -> tuple[list[str], int]:
    """The constructions of one clause, each after at most two joiners (a joiner between two is required): the kinds
    read and -1, or the kinds read before the position where no construction reads (rule ``note-clauses``: the
    paragraph is then a self-report). Three readers try each position, each reading forward once."""
    kinds: list[str] = []
    i = 0
    n = len(c)
    while i < n:
        j = i
        k = 0
        while k < 2 and _at(c, j) in _JOINERS:
            j += 1
            k += 1
        if (kinds and not k) or j >= n:
            return kinds, i
        kind = NO_ACCESS_RULE
        e = _no_access(c, j)
        if e < 0:
            kind, e = NOT_CHECKED_RULE, _not_checked(c, j)
        if e < 0:
            saved = st.saved()
            kind, e = SUGGESTION_RULE, _suggestion(c, j, st)
            if e < 0:
                st.restore(saved)
                kind, e = _CONTINUED, _continuation(c, j, st)
                if e < 0:
                    st.restore(saved)
        if e < 0:
            return kinds, j
        kinds.append(kind)
        i = e
    return kinds, -1


def _sentences_and_clauses(toks: list[str]) -> list[list[list[str]]]:
    """The sentences of a note, each a list of clauses (token lists), cut at the sentence and clause marks. Every other
    character stays in its clause as a token no construction reads."""
    sentences: list[list[list[str]]] = [[[]]]
    for t in toks:
        if t in _SENTENCE_END:
            if sentences[-1][-1] or len(sentences[-1]) > 1:
                sentences.append([[]])
        elif t in _CLAUSE_BOUNDARY:
            if sentences[-1][-1]:
                sentences[-1].append([])
        else:
            sentences[-1][-1].append(t)
    return [[c for c in s if c] for s in sentences if any(s)]


def _why_unread(c: list[str]) -> tuple[str, str]:
    """The rule a clause the reader could not read breaks, for the record: a negator outside (b) and (c)
    (``bare-negator``), a subject that is the answer or a part of it (``answer-evaluation``), else ``note-clauses``."""
    head = c[:40]
    text = " ".join(head)
    foreign = next((t for t in head if t[:1].isalpha() and not _latin_only(t)), None)
    if foreign is not None:
        return NOTE_CLAUSES_RULE, f"a word the reader cannot read: {foreign!r} ({text})"
    if any(_negates(t) for t in head):
        return BARE_NEGATOR_RULE, text
    i = 0
    while i < len(head) and head[i] in _JOINERS:
        i += 1
    t = _at(head, i)
    if t in _ANSWER_PRONOUNS or (t in _ANSWER_DETS and any(x in _ANSWER_NOUNS for x in head[i + 1:i + 5])):
        return ANSWER_EVALUATION_RULE, text
    return NOTE_CLAUSES_RULE, text


def note_reading(text: str) -> NoteReading:
    """Rules ``note-clauses`` and ``note-form`` on the meta paragraph ``text`` (quotations masked by the caller): every
    clause is read, word for word from closed lists, as constructions (a) ``study-suggestion``, (b) ``no-access`` or (c)
    ``not-checked`` (module docstring), and at least one has the kind of the lead (after "Next step(s):" a suggestion;
    after any other lead (b) or (c)). One pass over the tokens: each clause is read forward and the paragraph is refused
    at the first clause no construction reads."""
    from epinoic_logic.api.adapters import BARE_NOTE_LEAD_RE
    m = BARE_NOTE_LEAD_RE.match(text or "")
    if m is None:
        return NoteReading(False, rule=NOTE_FORM_RULE, detail="no bare note lead")
    lead = "next" if "next" in m.group(0).lower() else "note"
    kinds: list[str] = []
    for sentence in _sentences_and_clauses(_note_tokens(text[m.end():])):
        st = _Sentence()
        for c in sentence:
            got, fail = _read_clause(c, st)
            kinds.extend(got)
            if fail >= 0:
                rule, detail = _why_unread(c[fail:])
                return NoteReading(False, lead, tuple(kinds), rule, detail)
    wanted = SUGGESTION_KINDS if lead == "next" else LIMITATION_KINDS
    if not any(k in wanted for k in kinds):
        what = "a study suggestion addressed to the student" if lead == "next" else "a no-access or not-checked construction"
        return NoteReading(False, lead, tuple(kinds), NOTE_FORM_RULE, f"no clause is {what}")
    return NoteReading(True, lead, tuple(kinds))


def note_form(text: str) -> bool:
    """Rules ``note-clauses`` and ``note-form`` (:func:`note_reading`): whether the meta paragraph ``text`` (quotations
    masked by the caller) has the positive form of a note."""
    return note_reading(text).note


def read_meta_paragraph(text: str) -> NoteReading:
    """Rule ``meta-note`` on one meta-text paragraph: the reading and, when it is no note, the rule that keeps it a
    self-report. Never raises: a text it cannot read is no note."""
    try:
        return _read_meta_paragraph(text)
    except Exception as exc:  # noqa: BLE001 - a reader that fails frees nothing (fail closed: a self-report)
        return NoteReading(False, rule=META_NOTE_RULE, detail=f"the reader failed ({type(exc).__name__})")


def _read_meta_paragraph(text: str) -> NoteReading:
    from epinoic_logic.api.adapters import META_NARRATION_RE, is_meta_sentence, split_sentences
    from epinoic_logic.api.adapters import find_json_spans, is_json_block, mask_quotations, opens_note_paragraph, self_cert_vocabulary
    from epinoic_logic.api.adapters import verification_label
    from .checks.selfcert import flags_self_certification
    if not text or len(text) > _MAX_PARAGRAPH_CHARS:
        return NoteReading(False, rule=META_NOTE_RULE, detail="empty or over the bound")
    if hides_text(text):
        return NoteReading(False, rule=META_NOTE_RULE, detail="a tag character (text no reader is shown)")
    raw, text = text, reader_text(text)  # every reading below is of the normalised text (attack round 3)
    if not opens_note_paragraph(raw) or not opens_note_paragraph(text):
        # the bare lead as written AND as normalised: a lead that only normalisation makes bare (a fullwidth colon, a zero-width
        # space inside "Note") is refused (fail closed: such a note only keeps its answer off the formal path)
        return NoteReading(False, rule=NOTE_FORM_RULE, detail="no bare note lead")
    if strict_lead_end(raw, _STRICT_NOTE_LEAD_RE) < 0 or strict_lead_end(text, _STRICT_NOTE_LEAD_RE) < 0:
        # read AS A WHOLE (attack round 5): before the lead only blanks, at most one list mark and the lead's own emphasis ("> Note:",
        # "### Note:", "- - Note:" and every emoji, symbol or tag are refused)
        return NoteReading(False, rule=NOTE_FORM_RULE, detail="no note lead opening the block as a whole (only blanks, one list mark and the "
                                                              "lead's own emphasis may stand before it)")
    if is_json_block(text) or find_json_spans(text):
        return NoteReading(False, rule=META_NOTE_RULE, detail="JSON")
    masked = mask_quotations(text)
    if META_NARRATION_RE.search(masked):
        return NoteReading(False, rule=META_NOTE_RULE, detail="narration")
    for s in split_sentences(text):
        if is_meta_sentence(s) or self_cert_vocabulary(s) is not None or verification_label(s) is not None or flags_self_certification(mask_quotations(s)):
            return NoteReading(False, rule=META_NOTE_RULE, detail=f"a sentence a shared self-report reader names: {s[:120]!r}")
    found = assurance_words(masked)
    if found:
        return NoteReading(False, rule=ASSURANCE_RULE, detail=", ".join(found[:6]))
    found = evaluation_words(masked)
    if found:
        return NoteReading(False, rule=EVALUATION_RULE, detail=", ".join(found[:6]))
    return note_reading(masked)


def is_note_paragraph(text: str) -> bool:
    """True when the meta-text paragraph ``text`` is positively read as a note (module docstring): a bare note lead, no
    JSON, no sentence a shared self-report reader names, no assurance word, no evaluation word, every clause read as
    construction (a), (b) or (c) of rule ``note-clauses`` and one of the lead's kind. Never raises: a text it cannot read
    is no note."""
    return read_meta_paragraph(text).note


def note_paragraphs(text: str) -> frozenset[int]:
    """The 1-based indices of the English answer ``text``'s meta-text paragraphs that are notes (rule ``meta-note``), as
    the English parser segments it. Never raises: an answer it cannot segment has none."""
    try:
        from epinoic_logic.api.adapters import segment
        return frozenset(p.index for p in segment(text or "") if p.kind == "meta" and is_note_paragraph(p.text))
    except Exception:  # noqa: BLE001 - fail closed: no paragraph is freed
        return frozenset()


def meta_paragraph_of(finding: Any) -> Optional[int]:
    """The paragraph number of a paragraph-level ES-META-001 (``paragraph N is meta-text (...)``), else None (a sentence-level
    one, another code, a message the pack did not write so)."""
    if getattr(finding, "code", None) != "ES-META-001":
        return None
    m = _META_PARAGRAPH_RE.match(str(getattr(finding, "message", "") or ""))
    return int(m.group(1)) if m is not None else None


def self_report_findings(findings: Iterable[Any], report: Any) -> list[Any]:
    """``findings`` (receipt findings of the self-report codes) without the ES-META-001 findings that name a note paragraph
    of the journaled ``report``'s answer (rule ``meta-note``). The answer is read only when such a finding is present."""
    found = list(findings)
    if not any(meta_paragraph_of(f) is not None for f in found):
        return found
    text = getattr(report, "original_response", None) if report is not None else None
    notes = note_paragraphs(text) if isinstance(text, str) else frozenset()
    return [f for f in found if not (meta_paragraph_of(f) in notes and not list(getattr(f, "claim_ids", []) or []))]


# ============================================================================================ rule lead-blocks
# Attack round 2 on rule meta-note found the rule held and every remaining bypass travelled OUTSIDE it, through the English
# parser's segmentation: a one-line block after a sources lead is a 'sources' unit (no ES-META-001; c1 bug 4 put that
# branch before the meta-text test), and a quotation-free block opened by a bare note lead that is not all meta-text is a
# 'body' block whose sentences are all notes (no ES-META-001). Neither reaches rule meta-note, so an assurance after a genuine
# first sentence ("NB: I can't see the image. Nothing above needs fixing.") or after a source ("Sources: The Tuner extract
# (supplied text), every quotation verified against it.") travelled under the FORMALLY CHECKED label. Rule ``lead-blocks``
# reads the answer AS WRITTEN, independently of every parser, receipt, claim and pack finding: every block that opens with a
# note lead or a sources lead must be positively read AS A WHOLE, as a note by rule meta-note or as a pure source list by
# rule ``source-list``; any other block keeps the answer from the FORMALLY CHECKED label (the delivery policy names it).
LEAD_BLOCKS_RULE = "lead-blocks"
SOURCE_LIST_RULE = "source-list"

#: The blanks inside and around a lead: any blank the parsers' ``\s`` reads, a line break included ("Next\nstep:" is
#: "Next step:" to a parser that joins a paragraph's lines); :func:`_lead_copy` reads every other blank as a space.
_WS = r"[ \t\n]"
#: The note leads of every reader, English then Spanish and French: the parsers' note leads ("Note:", "Notes:", "Please
#: note:", "NB:", "N.B.", "Next step(s):", "Limit(s):", "Caveat(s):", "Confidence:"; the History parser's "Limitation(s):"
#: and "Sourcing:", and its full stop in place of the colon, "Note.") and the forms of the languages the English branch
#: reads ("Nota:", "Remarque :", "Siguiente paso:", "Prochaine étape :", ...).
_NOTE_LEAD_WORDS = (r"(?:please" + _WS + r"+)?note|notes|nb|next" + _WS + r"+steps?|limits?|limitations?|caveats?|confidence|sourcing"
                    r"|notas?|observaci[oó]n(?:es)?|aviso|advertencia|siguientes?" + _WS + r"+pasos?|pr[oó]ximos?" + _WS + r"+pasos?|l[ií]mites?"
                    r"|remarques?|[àa]" + _WS + r"+noter|avertissement|prochaines?" + _WS + r"+[ée]tapes?|[ée]tapes?" + _WS + r"+suivantes?|limites?")
#: The sources leads ("Sources:", "Source:", "Sources used/consulted/cited:", "References:", "Bibliography:", "Works cited:")
#: and their Spanish and French forms. "Source A:" (a source of a History paper named by its letter) is no lead.
_SOURCES_LEAD_WORDS = (r"sources?(?:" + _WS + r"+(?:used|consulted|cited))?|references|bibliography|works" + _WS + r"+cited"
                       r"|fuentes?(?:" + _WS + r"+(?:consultadas|utilizadas|citadas))?|referencias|bibliograf[ií]a|r[ée]f[ée]rences|bibliographie")
#: What follows a lead's words (attack round 3: a lead is read whatever punctuation, bracket or dash follows it): blanks, then
#: any character that is neither a word character nor a blank ("Note:", "Note.", "Note∶", "Note (", "Sources —"). A lead's
#: words followed by a word ("Note that ...", "Notebook:", "Source A:", "NB the dates hold") are no lead.
_LEAD_MARK = _WS + r"*[^\w\s]"
#: "Note on" and its topic: "Note on" followed (after blanks) by any punctuation, bracket or dash ("Note on(this answer):",
#: "Note on—the figures:", "Note on… nothing"), or by a topic of at most 80 characters that holds no sentence stop and ends at
#: the first punctuation mark that is not one ("Note on the dates:", "Note on the analysis of the piano, ..."). "Note on the
#: dates." is a sentence, not a lead; "Note one thing" is no lead.
_NOTE_ON = r"note" + _WS + r"+on(?:" + _WS + r"*[^\w\s]|" + _WS + r"[^:.!?…\n]{1,80}?[^\w\s.!?…])"
#: A lead, read where :func:`_lead_starts` puts it (after the marks before it on its line): a list number, then a sources
#: lead, "Note on", a note lead, or "N.B." written with blanks or a line break ("N. B.", "N.\nB.").
_BLOCK_LEAD_RE = re.compile(r"(?:\d{1,3}[.)][ \t]+)?(?:(?P<sources>" + _SOURCES_LEAD_WORDS + r")" + _LEAD_MARK
                            + r"|(?P<noteon>" + _NOTE_ON + r")"
                            + r"|(?P<note>" + _NOTE_LEAD_WORDS + r")" + _LEAD_MARK
                            + r"|(?P<nb>n" + _WS + r"?\." + _WS + r"?b" + _WS + r"?\.))", re.IGNORECASE)
#: Where a lead can stand: the paragraph's start, a line's start, and right after a sentence's end inside a line (its stop
#: and closing marks, or the closing brace or bracket of pasted JSON, as the English parser ends a sentence): "... can
#: seem temporary. Note: ...".
_LEAD_START_RE = re.compile(r"\n|[.!?…][\"'”’»)\]]*|[}\]]")
#: A quotation mark: a lead after one is no lead for any parser (the quotation's words, not the writer's lead).
_QUOTE_MARKS = frozenset("\"'“”‘’«»„‟‚‹›")

# ---------------------------------------------------------------------------- the lead region (attack round 5)
# Attack round 5 found that rule source-list never read what stood BEFORE its lead: the cutting reader (:func:`lead_starts`)
# takes any run of marks before a lead, an HTML-like tag inside it and any one mark in place of its colon, so "👍 Sources:",
# "★★★★★ Sources:", "🆅🅴🆁🅸🅵🅸🅴🅳 Sources:", "<all verified> Sources:", "Sour<all good>ces:" and "Sources💯" were freed whole
# with the region read by no reader. The cutting reader stays wide (it only makes more blocks that must be read); every
# reader that FREES a block now reads the block AS A WHOLE from its first character: before its lead or label only the
# closed region below, the lead's words as written, and the parsers' own colon after them.
#: Blanks inside a line (a line break is never part of a lead's region).
_BLANK = r"[^\S\n]"
#: The lead's own markdown emphasis, written against its first letter ("**Note:**", "*Sources:*", "__Task:__"): no visible
#: character, so no word an assurance could ride on.
_EMPHASIS = r"(?:\*{1,2}|_{1,2})"
#: At most ONE list mark before a lead or a label, from a closed set: one bullet ("-", "*", "•") or one list number ("1.",
#: "1)", "(1)", "a)", "a.", "(a)"; one or two digits, one lower-case letter a to h), each followed by a blank.
_LIST_MARK = r"(?:[-*•]|\d{1,2}[.)]|\(\d{1,2}\)|(?-i:[a-h])[.)]|\((?-i:[a-h])\))"
#: The whole region a freeing reader takes before a lead or a label: blanks, at most one list mark and its blank, the lead's
#: own emphasis. Any other character (an emoji, a symbol, a check mark, a star, an enclosed, squared or regional-indicator
#: letter, a letter or a digit, an HTML-like tag, a quotation mark, a heading or quote mark, a second list mark) leaves the
#: block unread, so it is refused.
LEAD_REGION = _BLANK + r"*(?:" + _LIST_MARK + _BLANK + r"+)?" + _EMPHASIS + r"?"
#: A note lead a freeing reader takes, as the parsers' own bare note lead reads it (``markdown.BARE_NOTE_LEAD_RE``), after the
#: closed region: the lead's words, its own emphasis closed before or after the colon, and the colon ("N.B." needs none).
_STRICT_NOTE_LEAD_RE = re.compile(LEAD_REGION + r"(?:(?:(?:please" + _BLANK + r"+)?note|notes|nb|next" + _BLANK + r"+steps?|limits?|caveats?)"
                                  + _EMPHASIS + r"?" + _BLANK + r"*:|n\." + _BLANK + r"?b\.)" + _EMPHASIS + r"?", re.IGNORECASE | re.ASCII)
#: A sources lead a freeing reader takes, after the closed region: the lead's words on one line ("Sources:", "Sources used:",
#: "References:", "Bibliography:", "Works cited:" and the Spanish and French forms) and the colon the English parser requires
#: (``markdown._SOURCES_LEAD_RE``): "Sources —", "Sources👍" and "Sources 💯:" are no lead a reader frees.
_STRICT_SOURCES_LEAD_RE = re.compile(LEAD_REGION + r"(?:sources?(?:" + _BLANK + r"+(?:used|consulted|cited))?|references|bibliography|works" + _BLANK
                                     + r"+cited|fuentes?(?:" + _BLANK + r"+(?:consultadas|utilizadas|citadas))?|referencias|bibliograf[iíÍ]a"
                                     + r"|r[eéÉ]f[eéÉ]rences|bibliographie)" + _EMPHASIS + r"?" + _BLANK + r"*:" + _EMPHASIS + r"?",
                                     re.IGNORECASE | re.ASCII)
_LEAD_REGION_RE = re.compile(LEAD_REGION, re.ASCII)


def strict_lead_end(text: str, pattern: "re.Pattern[str]") -> int:
    """Where the lead of ``pattern`` ends when ``text`` opens with it AS A WHOLE (attack round 5): from the first character,
    only the closed region of :data:`LEAD_REGION` (blanks, at most one list mark, the lead's own emphasis), then the lead's
    words and its colon, read case-insensitively; -1 otherwise. Anchored, bounded look-ahead: constant time."""
    m = pattern.match(text or "")
    return m.end() if m is not None else -1


def lead_region_end(text: str) -> int:
    """Where the closed lead region of :data:`LEAD_REGION` ends at the start of ``text`` (0 when none): what a freeing reader
    takes before a label (rule ``layout``)."""
    return _LEAD_REGION_RE.match(text or "").end()
#: The most blocks one answer is read for (an answer holds a handful; more is refused unread, fail closed).
MAX_LEAD_BLOCKS = 256


def _lead_copy(text: str, plain: bool = False) -> tuple[str, list[int]]:
    """``text`` as the lead reader reads it, and for each character of the copy the offset of the character of ``text`` it
    stands for (attack round 3: the copy no longer keeps the offsets of ``text`` itself). Each character is read in NFKC (a
    fullwidth colon is a colon, a fullwidth letter a letter) and, unless ``plain``, as its confusable skeleton (attack round
    4, :func:`_skeleton_char`: a Cyrillic, Greek, Armenian or Cherokee look-alike or a small capital as its Latin letter, a
    letter with a diacritic as its base letter); a format character, another default-ignorable code point
    (:func:`reader_text`), a combining mark, the emphasis marks "*", "_", "`" and "~" and an HTML-like tag ("<b>", "</b>")
    are read as nothing ("No**te**:", "<b>Note:</b>", a word joiner after "Note on"); every blank but a line break is a space
    and a run of them is one space, as the parsers collapse blanks before they read a lead ("Note on" and ninety spaces,
    "N.  B."). One linear pass: a tag is looked for at most 40 characters ahead."""
    out: list[str] = []
    idx: list[int] = []
    n = len(text)
    i = 0
    blank = False  # the last character written is a space: a run of blanks is one
    while i < n:
        ch = text[i]
        if ch == "<" and i + 1 < n and (text[i + 1].isalpha() or text[i + 1] == "/"):
            j = text.find(">", i + 1, i + 40)
            if j > 0 and "<" not in text[i + 1:j] and "\n" not in text[i + 1:j]:
                i = j + 1
                continue
        if ch in "*_`~":
            i += 1
            continue
        if ch == "\n":
            out.append("\n")
            idx.append(i)
            blank = False
        elif ch.isspace():
            if not blank:
                out.append(" ")
                idx.append(i)
                blank = True
        elif ch.isascii():
            out.append(ch)
            idx.append(i)
            blank = False
        elif not _ignorable(ch) and unicodedata.category(ch)[0] != "M":
            for c in (unicodedata.normalize("NFKC", ch) if plain else _skeleton_char(ch)):
                if c.isspace():
                    if not blank:
                        out.append(" ")
                        idx.append(i)
                        blank = True
                else:
                    out.append(c)
                    idx.append(i)
                    blank = False
        i += 1
    return "".join(out), idx


def _prefix_ends(copy: str) -> list[int]:
    """For each position of ``copy``, where the marks before a lead end: the first position at or after it that holds a word
    character, a quotation mark or a line break. A lead is read there, so any run of marks may stand before it on its line (a
    quote, a heading, a bullet, an arrow, a dash, a pipe, a bracket: "> Note:", "◦ Note:", "| Note:", "[Note](#note):"), and
    a lead after a quotation mark is no lead. One pass from the end: each start reads its prefix in constant time."""
    n = len(copy)
    ends = [n] * (n + 1)
    for i in range(n - 1, -1, -1):
        ch = copy[i]
        ends[i] = i if (ch == "\n" or ch in _QUOTE_MARKS or ch.isalnum()) else ends[i + 1]
    return ends


def lead_starts(para: str, extra: Optional["re.Pattern[str]"] = None, *, plain: bool = False) -> list[tuple[int, str, int, bool, int]]:
    """Every lead of the paragraph ``para``: ``(offset, kind, line, inline, end)`` with the offset of the lead's first mark
    in ``para`` (the marks before its words included), its kind ("sources", "note", or "extra" when ``extra``, a pattern
    matched at the same place, reads it instead), the 1-based line it stands on, whether it opens a sentence inside its line,
    and the offset in ``para`` where its words end. A lead is read at the paragraph's start, at each line's start and right
    after each sentence's end, on the normalised copy of :func:`_lead_copy` (its letters read as their confusable skeleton
    unless ``plain``: a look-alike lead is a lead, so its block must be read), after the marks before it
    (:func:`_prefix_ends`). Linear: one scan for the starts, a match of bounded look-ahead at each."""
    copy, idx = _lead_copy(para, plain)
    if not copy:
        return []
    ends = _prefix_ends(copy)
    out: list[tuple[int, str, int, bool, int]] = []
    line, counted = 1, 0
    skip = 0  # the end of the lead read last: a stop inside it ("N.B.", "1. Note:") opens no second lead
    for s in [0] + [m.end() for m in _LEAD_START_RE.finditer(copy)]:
        if s < skip or s >= len(copy):
            continue
        p = ends[s]
        if p >= len(copy) or copy[p] == "\n" or copy[p] in _QUOTE_MARKS:
            continue
        m = _BLOCK_LEAD_RE.match(copy, p)
        kind = "sources" if m is not None and m.group("sources") else "note"
        if m is None and extra is not None:
            m = extra.match(copy, p)
            kind = "extra"
        if m is None:
            continue
        skip = m.end()
        line += copy.count("\n", counted, s)
        counted = s
        start = idx[s - 1] + 1 if s > 0 else 0  # the characters the copy reads as nothing before the lead ('**') are the block's
        while start < len(para) and para[start].isspace():
            start += 1  # the blanks after a sentence's end belong to no block
        end = idx[m.end() - 1] + 1 if m.end() > 0 else start
        out.append((start, kind, line, s > 0 and copy[s - 1] != "\n", end))
    return out


# ---------------------------------------------------------------------------- inside a claim (rule unverified-claims)
#: The symbols a claim may hold beyond the mathematical, currency and modifier symbols: a closed set of scientific ones.
_CLAIM_SYMBOLS = frozenset("°℃℉△")
#: The radical signs: mathematics before an operand, a tick mark after nothing ("√ Sources:", "15 km/h √").
_RADICALS = frozenset("√∛∜")
#: Where a note glued INTO a claim opens: after a clause mark, an opening bracket or a sentence's end inside the claim.
_GLUE_START_RE = re.compile(r"[;,:—–(\[]|[.!?…][\"'”’»)\]]*")


def claim_alphabet_breach(text: str) -> Optional[str]:
    """The first character of the claim ``text`` outside the claim alphabet, as ``U+XXXX`` (the delivery policy's rule
    ``unverified-claims``, attack round 5), else None. A claim's letters, the marks on them, its numbers, punctuation and
    blanks, mathematical, currency and modifier symbols and a closed set of scientific symbols (:data:`_CLAIM_SYMBOLS`) are
    what an encoding reads; any other character (an emoji, a check mark, a star, a squared, enclosed or regional-indicator
    letter, an enclosing mark, a format, private-use or unassigned code point) is content no encoding reads, so a claim that
    holds one carries no engine outcome for it ("The speed is 15 km/h. 👍", "The speed is 15 km/h.🆅🅴🆁🅸🅵🅸🅴🅳"). A radical sign
    is mathematics only before its operand (a digit, a letter or a bracket, after blanks): with none ("The speed is 15 km/h
    √") it is a tick mark, outside the alphabet too. Linear (a radical looks ahead over its blanks once)."""
    s = text or ""
    n = len(s)
    for i, ch in enumerate(s):
        if ch in "\t\n\r" or ch in _CLAIM_SYMBOLS:
            continue
        if ch in _RADICALS:
            j = i + 1
            while j < n and s[j] in " \t":
                j += 1
            if j < n and (s[j].isalnum() or s[j] in "([{"):
                continue
            return f"U+{ord(ch):04X}"
        cat = unicodedata.category(ch)
        if cat[0] in "LNPZ" or cat in ("Mn", "Mc", "Sm", "Sc", "Sk"):
            continue
        return f"U+{ord(ch):04X}"
    return None


def glued_note_lead(text: str) -> bool:
    """Whether a note lead stands INSIDE the claim ``text``, after a clause mark, an opening bracket or a sentence's end (the
    delivery policy's rule ``unverified-claims``, attack round 5): "The speed is 15 km/h; note: all figures are sound and not in
    doubt." is one claim for the STEM parser, and the note glued into it is meta-text no encoding of the claim reads. Read on
    the lead reader's normalised copy (:func:`_lead_copy`, the confusable skeleton included) after any marks and blanks, never
    after a quotation mark; a sources lead is left out (a citation inside a claim, "(source: Table 1)", is the claim's). Linear:
    one scan of the marks, a match of bounded look-ahead after each."""
    copy, _idx = _lead_copy(text or "")
    if not copy:
        return False
    ends = _prefix_ends(copy)
    for m in _GLUE_START_RE.finditer(copy):
        p = ends[m.end()]
        if p >= len(copy) or copy[p] == "\n" or copy[p] in _QUOTE_MARKS:
            continue
        lead = _BLOCK_LEAD_RE.match(copy, p)
        if lead is not None and not lead.group("sources"):
            return True
    return False


@dataclass(frozen=True)
class LeadBlock:
    """One block of an answer opened by a note or sources lead (rule ``lead-blocks``): its paragraph (the 1-based blank-line
    block of the answer as written), the 1-based line of that paragraph its lead stands on, whether the lead opens a sentence
    inside its line, its ``kind`` ("note" or "sources"), its text (from its lead to the next lead or the paragraph's end),
    whether it is ``read`` positively (a note by rule meta-note, a pure source list by rule ``source-list``), and when it is
    not, the rule that refused it and what that rule read (the detail holds the answer's words: it never reaches a reason)."""

    paragraph: int
    line: int
    inline: bool
    kind: str
    text: str
    read: bool
    rule: str = ""
    detail: str = ""

    def where(self) -> str:
        """The block named by position, kind and rule only (no word of the answer): the delivery policy's reason."""
        at = f"paragraph {self.paragraph}" if self.paragraph else "the answer as a whole"
        if self.line > 1:
            at += f" line {self.line}"
        if self.inline:
            at += " inside the line"
        what = {"note": "a note lead", "sources": "a sources lead"}.get(self.kind, "its leads")
        return f"{at} ({what}: rule {self.rule or LEAD_BLOCKS_RULE})"


def answer_paragraphs(text: str) -> list[tuple[int, int, str]]:
    """The paragraphs of the answer ``text`` as the English parser cuts it (CR and CRLF read as line breaks, a byte-order
    mark dropped, blank lines between paragraphs): ``(start, end, paragraph)`` with offsets into the normalised text
    (:func:`normalised_answer`), each paragraph stripped."""
    from epinoic_logic.api.adapters import PARAGRAPH_SPLIT_RE as _PARAGRAPH_SPLIT_RE
    norm = normalised_answer(text)
    out: list[tuple[int, int, str]] = []
    pos = 0
    for m in list(_PARAGRAPH_SPLIT_RE.finditer(norm)) + [None]:
        end = m.start() if m is not None else len(norm)
        raw = norm[pos:end]
        lead = len(raw) - len(raw.lstrip())
        para = raw.strip()
        if para:
            out.append((pos + lead, pos + lead + len(para), para))
        pos = m.end() if m is not None else len(norm)
    return out


def normalised_answer(text: str) -> str:
    """``text`` with CR and CRLF read as line breaks and every byte-order mark dropped, as the English parser reads it."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").replace(chr(0xFEFF), "")


def lead_blocks(text: str, grounding: Iterable[str] = ()) -> list[LeadBlock]:
    """Rule ``lead-blocks``: every block of the answer ``text`` opened by a note or sources lead, each read as a whole (a
    note lead by rule meta-note, :func:`read_meta_paragraph`; a sources lead by rule ``source-list``, :func:`read_source_list`
    with ``grounding``, the words of the supplied texts' titles and authors). The answer is cut into paragraphs as the English
    parser cuts it (:func:`answer_paragraphs`); in each, a lead is read at the paragraph's start, at each line's start and
    right after each sentence's end, on a normalised copy (:func:`_lead_copy`: NFKC, format characters, other ignorable code
    points, combining marks, emphasis marks and HTML-like tags read as nothing, blank runs as one space), after any run of
    marks before it on its line, and whatever punctuation, bracket or dash follows its words (:data:`_BLOCK_LEAD_RE`); a
    block runs from its lead to the next lead or the paragraph's end, so every word after a lead belongs to a block read as
    a whole. Quotations are NOT masked: a lead after a quotation mark is no lead for any parser, and one inside a quotation
    that follows a sentence's end is read (a refused block only keeps the answer off the formal path). Linear: one scan for
    the starts of each paragraph, a lead match of bounded look-ahead at each start, each block read once by a linear
    reader. More than :data:`MAX_LEAD_BLOCKS` blocks raise ``OverflowError`` (the caller refuses the answer unread)."""
    ground = frozenset(grounding)
    out: list[LeadBlock] = []
    for paragraph, (_start, _end, para) in enumerate(answer_paragraphs(text), start=1):
        leads = lead_starts(para)
        if len(out) + len(leads) > MAX_LEAD_BLOCKS:
            raise OverflowError(f"more than {MAX_LEAD_BLOCKS} blocks opened by a note or sources lead")
        for k, (s, kind, ln, inline, _e) in enumerate(leads):
            block = para[s:leads[k + 1][0] if k + 1 < len(leads) else len(para)].strip()
            if kind == "note":
                r = read_meta_paragraph(block)
                out.append(LeadBlock(paragraph, ln, inline, kind, block, r.note, r.rule, r.detail))
            else:
                sr = read_source_list(block, ground)
                out.append(LeadBlock(paragraph, ln, inline, kind, block, sr.ok, sr.rule, sr.detail))
    return out


def unread_lead_blocks(text: str, grounding: Iterable[str] = ()) -> list[LeadBlock]:
    """The blocks of :func:`lead_blocks` that are read neither as a note nor as a pure source list; one block naming the
    answer as a whole when the answer cannot be read (more than :data:`MAX_LEAD_BLOCKS` blocks, or a reader that fails):
    fail closed. Never raises."""
    try:
        return [b for b in lead_blocks(text, grounding) if not b.read]
    except Exception as exc:  # noqa: BLE001 - a reader that fails frees nothing
        why = "more than the bound of blocks" if isinstance(exc, OverflowError) else f"the reader failed ({type(exc).__name__})"
        return [LeadBlock(0, 0, False, "", "", False, LEAD_BLOCKS_RULE, why)]


def source_list_grounding(*texts: str) -> frozenset[str]:
    """The words a source list may name a supplied text by (rule ``source-list``): the lower-cased words of ``texts``, the
    supplied texts' titles and authors as the request carries them ("The Tuner (prose extract, supplied text)",
    "Anonymous"), a possessive read as its base. At most 64 texts of 1,000 characters each are read, in one linear scan."""
    words: set[str] = set()
    for t in list(texts)[:64]:
        for m in _LIST_TOKEN_RE.finditer(_normalise(str(t or "")[:1000])):
            w = m.group(0).lower()
            if w[:1].isalpha():
                words.add(_possessive_base(w))
                words.update(p for p in w.split("-") if p)
    return frozenset(words)


# ---------------------------------------------------------------------------- rule source-list
#: One token of a source list, its case kept: a word (apostrophes and hyphens inside it, a closing apostrophe of a plural
#: possessive), a number, a line break, or any other character on its own.
_LIST_TOKEN_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*(?:-[^\W\d_]+(?:'[^\W\d_]+)*)*'?|\d+|\n|\S")
#: The closed words of a source list (lower case): determiners and the joining words of a name, the kinds of a supplied text
#: and of course material and their usual modifiers, the words of the knowledge bases' fixed sources forms ("your question
#: (supplied text)", "practice question (supplied text)", "your pasted answer (supplied text)", "Biology course notes (course
#: notes)", "general Psychology course knowledge (course notes)", "the History specialist's context paragraph (supplied
#: text)"), the locators and labels of the citation rule (``channel.citations``), honorifics. No word of a verb, a clause, an
#: evaluation, a check, an assurance, a fault or a quantifier (:data:`_LIST_DENY` is disjoint from it, which the tests
#: assert). Attack round 4 narrowed it to words that name a source: no word of ownership, origin, extent or fidelity ("own",
#: "original", "full"), no answer but the student's pasted one ("the examination paper's own answers"), no work, results or
#: student, no part of a source that names none (a title, a heading, a caption) and no person (an author, a writer, a poet:
#: a source's author is a name its title or author gives, "by Anonymous"); a part a locator names takes its number
#: (:data:`_PURE_LOCATORS`: "lines 3-5", never "the extract's lines").
_SOURCE_WORDS = frozenset({
    "the", "a", "an", "your", "of", "on", "and", "by",
    # modifiers
    "supplied", "pasted", "attached", "printed", "prescribed", "set", "prose", "unseen", "general", "course", "class",
    "practice", "past", "exam", "examination", "sample", "specimen", "visual", "statistical", "background", "historical", "literary", "primary",
    "secondary", "first", "second", "third", "fourth", "fifth", "case", "data", "context", "image", "fieldwork", "study",
    # kinds of a supplied text and of course material
    "question", "questions", "task", "tasks", "prompt", "paper", "papers", "dataset", "datasets", "table", "tables", "figure", "figures", "chart",
    "charts", "graph", "graphs", "map", "maps", "diagram", "diagrams", "extract", "extracts", "excerpt", "excerpts", "passage", "passages", "poem",
    "poems", "text", "texts", "article", "articles", "story", "stories", "novel", "novels", "novella", "play", "plays", "drama", "poetry", "fiction",
    "non-fiction", "scene", "scenes", "speech", "speeches", "letter", "letters", "diary", "memoir", "essay", "essays", "infographic", "infographics",
    "images", "picture", "pictures", "photo", "photos", "photograph", "photographs", "cartoon", "cartoons", "illustration", "illustrations",
    "advert", "adverts", "advertisement", "advertisements", "leaflet", "leaflets", "poster", "posters", "brochure", "brochures", "website", "websites",
    "webpage", "webpages", "page", "pages", "blog", "transcript", "transcripts", "recording", "recordings", "video", "videos", "clip", "clips", "film",
    "films", "podcast", "interview", "interviews", "report", "reports", "studies", "survey", "surveys", "description", "descriptions", "scenario",
    "scenarios", "cases", "source", "sources", "document", "documents", "material", "materials", "notes", "knowledge", "textbook", "textbooks",
    "book", "books", "chapter", "chapters", "section", "sections", "paragraph", "paragraphs", "line", "lines", "stanza", "stanzas", "verse", "verses",
    "appendix", "appendices", "booklet", "handout", "handouts", "worksheet", "worksheets", "slide", "slides", "lecture", "lectures", "analysis",
    "analyses", "specialist", "specialist's", "specialists", "specialists'", "edition", "volume", "message", "messages", "attachment",
    "attachments", "syllabus", "guide", "specification", "formula", "formulae", "formulas", "sheet", "sheets", "answer", "row", "rows", "column",
    "columns", "act", "acts", "part", "parts", "canto", "cantos", "item", "items",
    # locators, abbreviations and honorifics
    "para", "paras", "fig", "figs", "p", "pp", "l", "ll", "ch", "vol", "ed", "eds", "q", "mr", "mrs", "ms", "dr", "prof",
})
#: The parts of a source a locator names (attack round 4): each names a source only with its number, label or numeral after
#: it ("lines 3-5", "p. 12", "Act IV", "Appendix A"); alone ("the extract's lines", "the textbook chapter") it names none.
_PURE_LOCATORS = frozenset({"line", "lines", "l", "ll", "page", "pages", "p", "pp", "para", "paras", "paragraphs", "row", "rows", "column", "columns",
                            "act", "acts", "scene", "scenes", "stanza", "stanzas", "verse", "verses", "canto", "cantos", "chapter", "chapters", "ch",
                            "section", "sections", "part", "parts", "appendix", "appendices", "volume", "vol", "item", "items", "fig", "figs", "q"})
#: The words of the knowledge bases' fixed peer-document form, "the <Subject> specialist's report (supplied text)": a
#: specialist is named by a subject, and an analysis is a specialist's ("the specialist's own analysis" is no source).
_SPECIALIST_WORDS = frozenset({"specialist", "specialist's", "specialists", "specialists'"})
_ANALYSIS_WORDS = frozenset({"analysis", "analyses"})
#: Capitalised names a source list may use with no supplied text naming them: subjects, course parts, the school library.
_SOURCE_TITLE_WORDS = frozenset({
    "english", "literature", "language", "history", "biology", "chemistry", "physics", "economics", "geography", "psychology", "mathematics",
    "maths", "math", "business", "management", "spanish", "french", "german", "philosophy", "sociology", "anthropology", "politics", "global",
    "environmental", "systems", "societies", "ess", "computer", "science", "sciences", "design", "technology", "sports", "exercise", "health",
    "arts", "theatre", "music", "ib", "dp", "hl", "sl", "ia", "ee", "tok", "aa", "mylib", "myp",
})
#: The nouns a number may follow (a locator: "paragraph 1", "Table 1", "lines 3-5", "p. 12", "Paper 1"), the nouns a label
#: letter A to H may follow ("Source A", "Extract B"), the nouns a roman numeral may follow ("Act IV"), and the
#: abbreviations a full stop may close ("p.", "pp.", "fig.", "Mr.").
_LOCATOR_NOUNS = frozenset({"paragraph", "paragraphs", "para", "paras", "table", "tables", "figure", "figures", "fig", "figs", "line", "lines", "l", "ll",
                            "stanza", "stanzas", "section", "sections", "page", "pages", "p", "pp", "chapter", "chapters", "ch", "act", "acts", "scene",
                            "scenes", "part", "parts", "book", "canto", "verse", "verses", "appendix", "question", "questions", "q", "item", "items",
                            "source", "sources", "extract", "extracts", "text", "texts", "document", "documents", "passage", "passages", "volume", "vol",
                            "paper", "papers", "slide", "slides", "row", "rows", "column", "columns"})
_LABEL_NOUNS = frozenset({"source", "sources", "extract", "extracts", "text", "texts", "document", "documents", "passage", "passages", "appendix",
                          "figure", "table", "section", "part", "question", "item", "paper"})
_ROMAN_NOUNS = frozenset({"act", "scene", "part", "book", "canto", "chapter", "volume", "vol", "section"})
_ROMAN_RE = re.compile(r"[ivxlc]{1,8}")
_LIST_ABBREVIATIONS = frozenset({"p", "pp", "para", "paras", "fig", "figs", "l", "ll", "ch", "vol", "ed", "eds", "q", "mr", "mrs", "ms", "dr", "prof"})
#: Words a source list never holds, whatever names them (a supplied title too): the vocabularies of rule meta-note
#: (assurance, evaluation, fault, negative forms, checking verbs, negators) and every word of a quantifier, a pronoun, an
#: auxiliary, a clause, an affirmation or a pointer to the answer.
_LIST_DENY = (_ASSURANCE_WORDS | _EVALUATION_WORDS | _FAULT_WORDS | _FAULT_NOUNS | _NEGATIVE_FORMS | _CHECK_VERBS | _NOTE_NEGATORS | frozenset({
    "all", "every", "each", "any", "some", "none", "no", "both", "only", "whole", "entire", "entirely", "most", "many", "much", "few", "several",
    "either", "neither", "everything", "nothing", "anything", "something", "everyone", "sole", "solely", "just", "alone", "exclusively", "wholly",
    "fully", "completely", "throughout", "total", "totally", "always", "ever",
    "i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves", "you", "yours", "yourself", "he", "him", "his", "she", "her", "hers",
    "it", "its", "itself", "they", "them", "their", "theirs", "this", "that", "these", "those", "one", "ones",
    "is", "are", "was", "were", "be", "been", "being", "am", "has", "have", "had", "having", "do", "does", "did", "done", "can", "could", "will",
    "would", "shall", "should", "may", "might", "must", "need", "needs", "needed", "ought",
    "which", "who", "whom", "whose", "what", "where", "when", "why", "how", "whether", "if", "because", "since", "as", "so", "thus", "therefore",
    "hence", "but", "yet", "although", "though", "while", "whereas", "unless", "until", "then", "otherwise", "else", "or", "than", "like",
    "yes", "yeah", "yep", "indeed", "sure", "agreed", "complete", "completed", "finished", "final", "finally", "approved", "verified", "checked",
    "above", "below", "here", "there", "herein", "hereby", "consulted", "used", "use", "retrieved", "retrieval", "quoted", "cited", "taken",
    "drawn", "copied", "based", "according", "relied", "rely", "relies",
    # attack round 4: ownership, origin, extent and fidelity, and the official answers ("the extract's own lines", "the original
    # lines of the extract", "original and full", "the examination paper's own answers")
    "own", "original", "originals", "originally", "full", "answers", "official", "officially", "markscheme", "markschemes", "mark-scheme",
    "examiner", "examiner's", "examiners", "examiners'", "intact", "unaltered", "untouched", "unedited", "actual", "actually", "real", "same",
}))


@dataclass(frozen=True)
class SourceListReading:
    """How rule ``source-list`` read a block opened by a sources lead: ``ok`` when it is positively read as a pure source
    list; otherwise the rule that refused it and what that rule read."""

    ok: bool
    rule: str = ""
    detail: str = ""


def _possessive_base(word: str) -> str:
    """``word`` without a possessive ending ("Spearman's" -> "spearman's" base "spearman", "specialists'" -> "specialists")."""
    if word.endswith("'s"):
        return word[:-2]
    return word[:-1] if word.endswith("'") else word


def read_source_list(text: str, grounding: Iterable[str] = ()) -> SourceListReading:
    """Rule ``source-list`` on a block opened by a sources lead (module docstring): the block is a pure source list when it
    is nothing but source names, document labels, locators and the kinds the citation rule accepts ("The Tuner extract
    (supplied text)", "Source A", "(paragraph 1)", "(Table 1)", "p. 12", "1956"), separated by ";", ",", ":", brackets,
    dashes, bullets or line breaks, and a closing full stop. Every word is a word of the closed list, or a capitalised name
    that ``grounding`` holds (a word of a supplied text's title or author) or a subject's name; no word is one of
    :data:`_LIST_DENY` (a verb of checking, using or quoting, a clause word, an evaluation, check, assurance or fault word,
    a negator, a quantifier, a pronoun, an auxiliary), whatever names it; a number is a year or follows a locator, a single
    capital letter A to H a label noun, a roman numeral an act, scene, part, book or chapter; a full stop closes the list or
    an abbreviation. No quotation, no JSON, no sentence a shared self-report reader names, no word of rule meta-note's two
    vocabularies. Anything else, and anything the reader cannot read, is no pure source list. Never raises; linear."""
    try:
        return _read_source_list(text, frozenset(grounding))
    except Exception as exc:  # noqa: BLE001 - a reader that fails frees nothing (fail closed)
        return SourceListReading(False, SOURCE_LIST_RULE, f"the reader failed ({type(exc).__name__})")


def _read_source_list(text: str, grounding: frozenset) -> SourceListReading:
    from epinoic_logic.api.adapters import META_NARRATION_RE, is_meta_sentence, split_sentences
    from epinoic_logic.api.adapters import find_json_spans, find_quotation_spans, is_json_block, self_cert_vocabulary, verification_label
    from .checks.selfcert import flags_self_certification
    if not text or len(text) > _MAX_PARAGRAPH_CHARS:
        return SourceListReading(False, SOURCE_LIST_RULE, "empty or over the bound")
    if hides_text(text):
        return SourceListReading(False, SOURCE_LIST_RULE, "a tag character (text no reader is shown)")
    text = reader_text(text).strip()  # every reading below is of the normalised text (attack round 3)
    # the block AS A WHOLE (attack round 5): from its first character only the closed lead region (blanks, at most one list mark, the
    # lead's own emphasis), the lead's words as written (a lead only the confusable skeleton reads, "Sоurces:", frees nothing: attack
    # round 4) and the colon; the region before a lead is never left unread ("👍 Sources:", "<all verified> Sources:", "Sources💯")
    lead_end = strict_lead_end(text, _STRICT_SOURCES_LEAD_RE)
    if lead_end < 0:
        return SourceListReading(False, SOURCE_LIST_RULE, "no sources lead opening the block as a whole (only blanks, one list mark and the "
                                                          "lead's own emphasis before it, its colon after it)")
    if is_json_block(text) or find_json_spans(text):
        return SourceListReading(False, SOURCE_LIST_RULE, "JSON")
    if find_quotation_spans(text) or any(ch in text for ch in "\"“”«»„‟"):
        return SourceListReading(False, SOURCE_LIST_RULE, "a quotation")
    if META_NARRATION_RE.search(text):
        return SourceListReading(False, SOURCE_LIST_RULE, "narration")
    for s in split_sentences(text):
        if is_meta_sentence(s) or self_cert_vocabulary(s) is not None or verification_label(s) is not None or flags_self_certification(s):
            return SourceListReading(False, SOURCE_LIST_RULE, f"a sentence a shared self-report reader names: {s[:120]!r}")
    body = text[lead_end:]  # the lead's own words ("Works cited:") are no evaluation; everything else of the block is read
    found = assurance_words(body)
    if found:
        return SourceListReading(False, ASSURANCE_RULE, ", ".join(found[:6]))
    found = evaluation_words(body)
    if found:
        return SourceListReading(False, EVALUATION_RULE, ", ".join(found[:6]))
    return _list_items([t.group(0) for t in _LIST_TOKEN_RE.finditer(_normalise(body))], grounding)


#: The tokens that end a name and every run of numbers or letters, and those that join a run's numbers or letters ("lines
#: 3-5", "Sources A and B") without ending it.
_LIST_SEPARATORS = frozenset({"\n", ";", ",", "(", ")", "[", "]", ":", "•"})
_RUN_JOINERS = frozenset({"-", "–", "—", "&", "and"})
#: Determiners: each must be followed by a word ("a practice question"; a bare "A" is a grade, never an article).
_LIST_DETERMINERS = frozenset({"the", "a", "an", "your"})


def _list_items(toks: list[str], grounding: frozenset) -> SourceListReading:
    """The structural reading of rule ``source-list`` after the lead: one forward pass over the tokens, each read in a
    constant context (the word before it, the token after it, whether a locator or a label noun opened a run of numbers or
    letters, which only a dash, "&" or "and" continues, and whether a part a locator names still waits for its number)."""
    n = len(toks)
    last = n - 1
    while last >= 0 and toks[last] == "\n":
        last -= 1
    words = 0
    depth = 0          # open brackets: a closing bracket closes one ("(supplied text)"; never ":)")
    prev = ""          # the word read last (lower case); "" after anything else
    numbering = False  # a locator noun, or a number of its run, came last: a number may follow
    labelling = False  # a label noun, or a letter of its run, came last: a letter A to H may follow
    pending = ""       # a part a locator names came last and waits for its number, label or numeral ("lines", "p.")

    def waiting() -> SourceListReading:
        return SourceListReading(False, SOURCE_LIST_RULE, f"a part of a source with no locator after it: {pending!r}")
    for i, tok in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < n else ""
        if tok in _LIST_SEPARATORS:
            if pending:
                return waiting()
            if tok in "([":
                depth += 1
            elif tok in ")]":
                depth -= 1
                if depth < 0:
                    return SourceListReading(False, SOURCE_LIST_RULE, f"a closing bracket no bracket opens: {tok!r}")
            prev, numbering, labelling = "", False, False
            continue
        if tok in _RUN_JOINERS:
            if pending:
                return waiting()
            prev = ""  # a run goes on across a joiner; a name across "and" or "&"
            continue
        if tok == ".":
            if prev in _LIST_ABBREVIATIONS and i != last:
                prev, labelling = "", False
                continue  # "p. 12", "Mr. Abara": the number or name after the abbreviation's stop
            if i == last:
                if pending:
                    return waiting()
                prev, labelling = "", False
                continue  # the list's closing full stop
            return SourceListReading(False, SOURCE_LIST_RULE, "a sentence after the list")
        if tok[0].isdigit():
            if numbering or (len(tok) == 4 and 1000 <= int(tok) <= 2100):
                prev, labelling, pending = "", False, ""
                continue  # a locator's number ("Table 1", "lines 3-5") or a year ("Cleveland Avenue, 1956")
            return SourceListReading(False, SOURCE_LIST_RULE, f"a number no locator opens: {tok!r}")
        if not tok[0].isalpha():
            return SourceListReading(False, SOURCE_LIST_RULE, f"a character no source list holds: {tok!r}")
        low = tok.lower()
        if len(tok) == 1 and tok in "ABCDEFGH" and labelling:
            prev, numbering, pending = "", False, ""
            continue  # a label ("Source A", "Extracts A and B")
        if prev in _ROMAN_NOUNS and _ROMAN_RE.fullmatch(low):
            prev, numbering, labelling, pending = "", False, False, ""
            continue  # "Act IV", "Part ii"
        if pending:
            return waiting()
        if low in _LIST_DETERMINERS and not nxt[:1].isalpha():
            return SourceListReading(False, SOURCE_LIST_RULE, f"a determiner no name follows: {tok!r}")
        if low == "answer" and prev != "pasted":
            return SourceListReading(False, SOURCE_LIST_RULE, f"an answer that is not the student's pasted one: {tok!r}")
        if low in _SPECIALIST_WORDS and prev not in _SOURCE_TITLE_WORDS:
            return SourceListReading(False, SOURCE_LIST_RULE, f"a specialist no subject names: {tok!r}")
        if low in _ANALYSIS_WORDS and prev not in ("specialist's", "specialists'"):
            return SourceListReading(False, SOURCE_LIST_RULE, f"an analysis that is no specialist's report: {tok!r}")
        for part in ([low] if low in _SOURCE_WORDS else low.split("-")):
            base = _possessive_base(part)
            if part in _LIST_DENY or base in _LIST_DENY:
                return SourceListReading(False, SOURCE_LIST_RULE, f"a word no source list holds: {tok!r}")
            if part in _SOURCE_WORDS or base in _SOURCE_WORDS:
                continue
            if tok[0].isupper() and (base in grounding or base in _SOURCE_TITLE_WORDS):
                continue  # a name a supplied text's title or author writes ("The Tuner"), or a subject's ("Biology")
            return SourceListReading(False, SOURCE_LIST_RULE, f"a word neither the closed list nor a supplied title names: {tok!r}")
        words += 1
        if low != "and":
            numbering, labelling = low in _LOCATOR_NOUNS, low in _LABEL_NOUNS
        pending = low if low in _PURE_LOCATORS else ""
        prev = low
    if pending:
        return waiting()
    if depth:
        return SourceListReading(False, SOURCE_LIST_RULE, "a bracket left open")
    if not words:
        return SourceListReading(False, SOURCE_LIST_RULE, "no source named")
    return SourceListReading(True)
