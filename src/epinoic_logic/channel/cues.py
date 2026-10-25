"""Cue phrases shared by the channel and the subject parsers.

The channel decides whether a report states a position on degree (INT-REQ-008) from the
same phrases the History parser uses to role a sentence as a judgement, so the two never
disagree about what a verdict looks like. This module has no imports, so any adapter can
import it without a cycle: ``from epinoic_logic.channel.cues import VERDICT_CUES``.
"""
from __future__ import annotations

#: Phrases that state a position on degree or a weighing of factors, lower-cased, matched on word boundaries
#: (``verdict_cue_regex``) or by substring on a lower-cased sentence. A bare claim ("X was responsible for Y") is not one;
#: a degree of responsibility ("partly responsible") or a ranked cause ("the main cause", "a minor factor") is.
#: Inflections are spelled out so a plain substring test works without stemming.
VERDICT_CUES: tuple[str, ...] = (
    "therefore", "thus",
    "to a large extent", "to a great extent", "to a limited extent", "to a lesser extent", "to some extent", "to a considerable extent",
    "to a degree",
    "decisive",
    "necessary but not sufficient", "necessary but sufficient", "necessary and sufficient", "necessary and not sufficient",
    "outweigh", "outweighs", "outweighed", "outweighing",
    "on balance",
    "more significant than", "more important than", "more decisive than",
    "less significant than", "less important than",
    "matters most", "mattered most",
    "the most significant", "the most important", "the most decisive",
    "by the criteria", "by the criterion", "by this criterion", "by that criterion",
    "weighed by", "weighs more", "weighed against", "carries the greater weight", "carry the greater weight",
    "holds for", "does not hold", "fails",
) + tuple(
    # repair round 1 (re-run review k09, A-INF-BARE): a degree of responsibility, or a ranked cause, is a position on degree
    # ("Appeasement was partly responsible ...; Hitler's aim was the main cause"); a bare "X was responsible for Y" still is not
    f"{degree} {head}"
    for degree in ("partly", "partially", "largely", "mainly", "mostly", "chiefly", "primarily", "principally", "wholly", "entirely", "solely",
                   "only partly", "in part", "more", "less", "most", "least")
    for head in ("responsible", "to blame")
) + tuple(
    f"{rank} {head}"
    for rank in ("the main", "the primary", "the principal", "the chief", "the key", "the biggest", "the greatest", "the underlying",
                 "the immediate", "the long-term", "the short-term", "a major", "a minor", "a contributing", "a secondary", "the most significant",
                 "the most important", "the decisive")
    for head in ("cause", "causes", "reason", "reasons", "factor", "factors")
)


def verdict_cue_regex() -> str:
    """A regular-expression alternation of :data:`VERDICT_CUES`, longest phrase first, for use between ``\\b``."""
    import re  # local: the module stays import-free for its consumers
    return "|".join(re.escape(c) for c in sorted(VERDICT_CUES, key=len, reverse=True))


def phrase_regex(phrases: tuple[str, ...]) -> str:
    """A regular-expression alternation of lower-cased ``phrases`` (longest first), each word separated by any run of
    spaces, for use between ``\\b`` with ``re.IGNORECASE``. Matching is linear in the text: the alternation has no nested
    quantifier."""
    import re  # local: the module stays import-free for its consumers
    return "|".join(r"\s+".join(re.escape(w) for w in p.split()) for p in sorted(phrases, key=len, reverse=True))


# ----------------------------------------------------------------------------------------------------- INT-REQ-017 (B3)

#: Phrases that state a result of the system's own checks (the hub, the engine, a receipt) rather than subject content,
#: lower-cased and matched on word boundaries outside quotations. A peer-dependent specialist that writes one of these in
#: its answer hands a router-side finding to the student as if it were subject advice: the student cannot weigh it, and
#: the finding may be false (INT-REQ-017). Closed and deliberately narrow: bare subject words ("engine", "check",
#: "counterexample") are content in physics, economics and mathematics, so only their system-check phrasings are listed.
SYSTEM_CHECK_PHRASES: tuple[str, ...] = (
    "a formal check", "the formal check", "a formal checker", "formal check failed", "formal check fails", "formal check found",
    "formal check flagged", "formal check flags", "formal check shows", "formal checks failed", "formal checks found",
    "formal checks flag", "formal checks flagged", "formal checks show",
    "the check failed", "the check fails", "the check holds", "the check held", "the checks failed", "the checks fail",
    "the checks hold", "the check flagged", "the checks flagged", "own check", "own checks", "checks flag", "check flags",
    "the engine found", "the engine finds", "the engine shows", "the engine showed", "the engine returned", "the engine returns",
    "the engine decided", "the engine flagged", "the engine flags", "the engine reports", "the engine reported",
    "the engine confirmed", "the engine confirms", "engine result", "engine results", "engine check", "engine checks",
    "engine counterexample", "engine verdict", "solver result", "the solver found", "the solver shows",
    "the receipt", "hub receipt", "the hub's receipt", "the hub flagged", "the hub found",
    "was flagged", "were flagged", "is flagged", "are flagged",
    "do not copy those", "don't copy those", "do not copy these", "don't copy these",
)
#: A finding code written into an answer ("INT-SUBJ-001", "CORE-SRC-003"): always a system result, never subject content.
FINDING_CODE_PATTERN = r"\b[A-Z]{2,5}-[A-Z]{2,8}-\d{3}\b"


# ----------------------------------------------------------------------------------------------------- B18: format items

#: Words that name the FORM of an answer (its language, its quotations, its parts, its length or manner) and never what it is
#: about. An unlabelled request item whose main clause holds nothing but these, function words and command or form verbs is
#: an instruction on how to answer ("Explain in English pls", "Please quote my exact words when you point out a mistake",
#: "Can you write my thesis statement properly and then ONE body paragraph proving it with exact quotes?"), not a content
#: item: it stays listed, but not as a required item of the coverage heuristic. Subject words that can be content
#: ("statement", "plan", "table", "structure", "point") are deliberately absent, so "Prove the statement." stays content.
FORMAT_WORDS: tuple[str, ...] = (
    "english", "spanish", "french", "german", "italian", "portuguese", "mandarin", "chinese", "japanese", "korean", "arabic",
    "russian", "hindi", "dutch", "language",
    "quote", "quotes", "quoting", "quoted", "quotation", "quotations", "cite", "cites", "citing", "citation", "citations", "verbatim",
    "paragraph", "paragraphs", "essay", "thesis", "answer", "answers", "response", "reply", "format", "layout", "sentence",
    "sentences", "bullet", "bullets", "words", "word", "exact", "exactly", "short", "brief", "briefly", "concise", "concisely",
    "simple", "simply", "clear", "clearly", "properly", "full", "fully", "neat", "neatly", "working", "workings",
    "please", "pls", "plz", "thanks", "thank",
)
#: Several words of form read as one ("thesis statement", "body paragraph"); consumed before the single words.
FORMAT_PHRASES: tuple[str, ...] = (
    "thesis statement", "body paragraph", "body paragraphs", "exact words", "exact quotes", "exact quotations", "word for word",
    "full sentences", "bullet points", "bullet point", "step by step", "point form", "own words", "significant figures",
    "decimal places",
    # a participle whose only object is the deliverable itself ("ONE body paragraph proving it"): its purpose, no new content
    "proving it", "supporting it", "arguing it", "showing it", "explaining it", "backing it up", "to prove it", "to support it",
)
#: Verbs of form: what a format instruction asks the writer to do with the answer itself. Verbs that ask about the
#: student's work ("check", "fix", "correct", "mark") are content asks and are deliberately absent.
FORMAT_VERBS: tuple[str, ...] = (
    "write", "use", "keep", "give", "make", "put", "show", "answer", "reply", "respond", "explain", "include", "add", "do",
    "try", "set", "lay", "quote", "cite", "rewrite",
)
#: Function words a format instruction may carry around its form words.
FUNCTION_WORDS: tuple[str, ...] = (
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for", "with", "by", "at", "from", "into", "as", "so", "then",
    "also", "just", "only", "too", "it", "its", "it's", "this", "that", "these", "those", "them", "they", "me", "my", "mine", "i",
    "you", "your", "we", "our", "us", "he", "she", "him", "her", "can", "could", "would", "will", "should", "shall", "may",
    "might", "must", "is", "are", "was", "were", "be", "been", "being", "do", "does", "did", "not", "no", "one", "all", "every",
    "each", "some", "any", "more", "most", "very", "really", "here", "there", "now", "again", "out", "up", "down", "how", "what",
)
#: Subordinators that end a format instruction's main clause ("Please quote my exact words WHEN you point out a mistake"):
#: what follows says when the form applies, not what the answer is about. Never read at the start of the item.
FORMAT_SUBORDINATORS: tuple[str, ...] = ("when", "whenever", "while", "if", "because", "so that", "where", "wherever")


# ----------------------------------------------------------------------------------------------- B4 / B19: answer layout

#: Second-person openers of a side answer, a reply to the student's own question or work ("Your thesis does not survive
#: the extract.", "On your 30% figure: ...", "Your friend is right."): a block that opens with one of these at the start or
#: the end of an answer is not part of the paragraph or the answer a word bound is set on.
SIDE_REPLY_OPENERS: tuple[str, ...] = (
    "your", "on your", "as for your", "about your", "regarding your", "to answer your", "in answer to your", "you asked",
    "you are right", "you're right", "you were right", "you are correct", "you're correct", "quick answer", "short answer",
    "and on your", "also, your", "also on your",
)
#: Headings of a plan or outline block ("Plan", "Essay plan", "Outline:"): with the plan lines that follow them, not part
#: of "the answer" a word bound is set on.
PLAN_HEADINGS: tuple[str, ...] = ("plan", "essay plan", "answer plan", "short plan", "brief plan", "outline", "essay outline", "planning")
#: Labels that open a block of meta-text about the answer, never answer content ("Limit: no library was available",
#: "Next step: rewrite ...", "Word count: 249"). A "Limit:" block is meta-text only when it speaks about the answer's
#: sources, checks or availability (a mathematics "Limit:" heading is content).
META_LABELS: tuple[str, ...] = ("limit", "limits", "limitation", "limitations", "next step", "next steps", "word count")
#: Phrases by which a closing one-line block addresses the reader about the answer itself ("This model is written to the
#: house standard ...: paste your own paragraph and I will give provisional marks"): a trailing note, not a paragraph.
READER_ADDRESS_CUES: tuple[str, ...] = (
    "paste your own", "send me your", "send it back", "send them back", "send me", "i will give", "i'll give", "i can give",
    "i will mark", "i'll mark", "i can mark", "i will check", "i can check", "i'll check", "provisional mark", "provisional marks",
    "let me know", "if you want me", "if you would like me", "word count",
)
