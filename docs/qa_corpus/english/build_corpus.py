#!/usr/bin/env python3
"""Build the English Specialist QA corpus from examples.md.

Every model answer and source extract is lifted verbatim from blockquotes in
examples.md by line range (the '> ' prefix is stripped; nothing else changes).
Run:  python3 -I build_corpus.py
"""
import hashlib, json, re, os, sys, datetime

SRC_DIR = ("/tmp/claude-0/-home-user/a7c3c8b5-0245-5e75-80f1-83ca77b220e6/scratchpad/"
           "english_specialist/english specialist knowledge docs 1.0")
OUT_DIR = ("/tmp/claude-0/-home-user/a7c3c8b5-0245-5e75-80f1-83ca77b220e6/scratchpad/"
           "qa_corpus/english")
EX = os.path.join(SRC_DIR, "examples.md")

lines = open(EX, encoding="utf-8").read().split("\n")

def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()

def bq(start, end):
    """Return blockquote text for 1-indexed inclusive line range, '> ' stripped."""
    out = []
    for n in range(start, end + 1):
        ln = lines[n - 1]
        if ln == ">":
            out.append("")
        elif ln.startswith("> "):
            out.append(ln[2:])
        else:
            raise SystemExit(f"line {n} is not a blockquote line: {ln[:60]!r}")
    return "\n".join(out)

def paragraphs(text):
    return [p for p in text.split("\n\n") if p.strip()]

def word_count(text):
    return len(re.findall(r"\S+", text))

# ---------- normalisation for quotation checks ----------
def norm_chars(s):
    s = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u2014", "-").replace("\u2013", "-").replace("\u2026", "...")
    return re.sub(r"\s+", " ", s).strip()

def tokens(s):
    s = norm_chars(s).lower()
    s = s.replace("/", " ")           # line-break marks in verse quotations
    s = s.replace("-", " ")           # hyphenated compounds split identically on both sides
    s = re.sub(r"[^\w' ]+", " ", s)   # drop punctuation, keep in-word apostrophes
    s = re.sub(r"(^|\s)'+|'+(\s|$)", " ", s)  # strip stray apostrophes at token edges
    return s.split()

def found_words(q, src):
    qt, st = tokens(q), tokens(src)
    if not qt:
        return False
    n = len(qt)
    return any(st[i:i+n] == qt for i in range(len(st) - n + 1))

def found_strict(q, src):
    return norm_chars(q) in norm_chars(src)

QUOTE_RE = re.compile(r'"([^"]+)"')

def quotations(text):
    return QUOTE_RE.findall(text)

def quote_checks(text, source):
    qs = quotations(text)
    if source is None:
        return qs, [None] * len(qs), [
            {"quotation": q, "found_in_source": None, "found_strict": None,
             "note": "no source extract stored in examples.md; cannot be checked here"} for q in qs]
    flags, detail = [], []
    for q in qs:
        fw = found_words(q, source)
        fs = found_strict(q, source)
        note = ""
        if fw and not fs:
            note = "words match in order; differs only in case, punctuation or line-break marks"
        elif not fw:
            note = "NOT found as a contiguous word sequence in the stored source"
        flags.append(fw)
        detail.append({"quotation": q, "found_in_source": fw, "found_strict": fs, "note": note})
    return qs, flags, detail

# ---------- the examples ----------
examples = []

# Example 1
src1 = bq(87, 95)
ans1 = bq(99, 107)
examples.append(dict(
    example_id=1,
    form="novel extract; deliverable: full essay on one text",
    status_label="[S] Selected",
    text_title="Chronicle of a Death Foretold (extract: the twins' surrender, the verdict, and the town's fear of the Arabs)",
    author="Gabriel García Márquez",
    prompt="How does the author emphasize how societal expectations influence the administration of justice?",
    source_extract=src1,
    model_answer=ans1,
    spelling_variety="American",
    examples_md_lines={"header": "76-84", "source_extract": "85-95", "essay": "97-107", "move_map": "109-125"},
    source_file_lines="Examples.KD.md: extract L397-405; prompt L409; essay L413-421 (Essay 13)",
    stated_length_in_examples_md="essay, 1,305 words",
    notes=[
        "Source extract IS present (the only example with a continuous prose source).",
        "The extract is stored wrapped in one pair of outer double quotes; dialogue inside it uses single quotes.",
        "examples.md edited the essay in 17 places: 'Márquez' -> 'García Márquez' (formatting.md S16). Otherwise verbatim.",
        "Known legitimate join (flagged in the example header, formatting.md S12): body 1 quotes \"We killed him openly, but we're innocent.\" The source reads 'We killed him openly,' Pedro Vicario said, 'but we're innocent.' Both halves exist; the speech tag is omitted without marking. The word-sequence check therefore returns false for this one quotation.",
        "The introduction does not preview body 3's idea (Paragraphs P15) - noted in the header as a feature not to copy.",
        "Body 1 of this essay is the base text for every file in mutations/.",
        "Markdown italics markers (_Title_) are preserved exactly as they appear in the blockquote.",
    ],
))

# Example 2
src2 = bq(157, 175)
ans2 = bq(354, 362)
examples.append(dict(
    example_id=2,
    form="play and novel; deliverable: comparative outline, then comparative essay",
    status_label="outline (2b) [A] Approved; first essay (2c) [C] Corrected - not reproduced; final essay (2d) [A] Approved. model_answer below is the final essay 2d.",
    text_title="Othello and Frankenstein",
    author="William Shakespeare and Mary Shelley",
    prompt=bq(148, 153),
    source_extract=src2,
    model_answer=ans2,
    spelling_variety="American",
    examples_md_lines={"2a_task_and_sources": "140-175", "2b_outline": "177-329", "2c_correction": "331-345", "2d_essay": "347-362", "move_map": "364-378"},
    source_file_lines="Examples.KD.md: prompt L1144-1149; sources L1122-1140; outline L1151-1297; correction L1315; final essay L1317-1325 (also L467-475) (Pairing 1, Essays 14 and 15)",
    stated_length_in_examples_md="outline, 1,110 words; essay, 996 words",
    supplementary={
        "outline_2b_status": "[A] Approved",
        "outline_2b_unit_1": bq(185, 256),
        "outline_2b_unit_2": bq(260, 329),
        "user_correction_2c": bq(343, 343),
        "first_essay_2c": None,
        "first_essay_2c_note": "The corrected first essay [C] is not reproduced in examples.md; only a contrast table (lines 335-339) and the user's correction (line 343) appear. Do not treat it as a model.",
    },
    notes=[
        "source_extract is NOT a continuous passage: it is the list of eight quotations (four per text) that the source file stored with the task. Quotation checks run against that list.",
        "Quotation checks found all essay quotations in the stored list at word level. One differs only in punctuation: the essay writes 'beware, my lord, of jealousy: / It is...' where the stored source has 'O, beware, my lord, of jealousy! / It is...' (found_strict=false, found_in_source=true).",
        "Header 'Don't copy': in body 1 the Frankenstein strand's Effect is folded into the link.",
        "examples.md edits: outline and source headings set as bold lines; 'Prompt:' label removed from the correction. Otherwise verbatim.",
        "Markdown markers (_Title_, **bold**) are preserved exactly as they appear in the blockquotes.",
    ],
))

# Example 3
ans3 = bq(388, 388)
examples.append(dict(
    example_id=3,
    form="play and novel; deliverable: standalone comparative paragraph",
    status_label="[S] Selected",
    text_title="Othello and Never Let Me Go",
    author="William Shakespeare and Kazuo Ishiguro",
    prompt="\"Just take one paragraph and make it standalone\" (source L1431), applied to body 2 of a comparative essay on communication written without citations (source Essay 18).",
    source_extract=None,
    model_answer=ans3,
    spelling_variety="British",
    examples_md_lines={"header": "380-386", "paragraph": "388", "move_map": "390-404"},
    source_file_lines="Examples.KD.md: L1429-1433 (Pairing 3, Output C)",
    stated_length_in_examples_md="paragraph, 336 words",
    notes=[
        "NO source extract exists in examples.md for this example; quotations cannot be checked here (null).",
        "examples.md itself states the Never Let Me Go quotation (\"Why did we waste all that time?\") was written from memory for a task without citations and has not been verified; a web search did not confirm it (examples.md section 10 and 11).",
        "The Othello quotation \"ocular proof\" matches the list stored with Pairing 3 (L1365-1395), but that list was itself written from memory.",
        "examples.md edit: 'Prompt:' label removed. Otherwise verbatim.",
    ],
))

# Example 4
ans4 = bq(421, 421) + "\n\n" + bq(425, 425)
examples.append(dict(
    example_id=4,
    form="first-person prose, treated as unseen; deliverable: essay introduction (thesis) and one body paragraph",
    status_label="[S] Selected",
    text_title="unseen story opening narrated by a boy after a priest's death (the annotation identifies it as the opening of James Joyce's \"The Sisters\"; the answer never names author or work)",
    author="the writer",
    prompt="How does the writer use style, tone and technique to enhance the dramatic effect of the writing? (Assume you don't know anything about the text or author.)",
    source_extract=None,
    model_answer=ans4,
    spelling_variety="British",
    examples_md_lines={"header": "410-417", "introduction": "419-421", "body_2": "423-425"},
    source_file_lines="Examples.KD.md: prompt L644; introduction L648; body 2 L652 (Essay 19)",
    stated_length_in_examples_md="thesis, 118 words; paragraph, 332 words",
    notes=[
        "model_answer joins two non-contiguous parts of a five-body essay: the introduction (first paragraph) and body 2 (second paragraph).",
        "NO source extract exists in examples.md; quotations cannot be checked here (null).",
        "Header 'Don't copy': the paragraph opens 'This psychological unease...', pointing back to the paragraph before it; a standalone paragraph needs its own point (P22).",
    ],
))

# Example 5
ans5 = bq(438, 438)
examples.append(dict(
    example_id=5,
    form="first-person prose, treated as unseen; deliverable: one body paragraph",
    status_label="[S] Selected",
    text_title="unseen first-person account of a university interview (the annotation identifies it as Sebastian Faulks's Engleby; the answer never names author or work)",
    author="the writer",
    prompt="How does the writer's use of structure, style and tone affect the reader's perception of the narrator in this piece?",
    source_extract=None,
    model_answer=ans5,
    spelling_variety="British",
    examples_md_lines={"header": "427-434", "body_2": "436-438"},
    source_file_lines="Examples.KD.md: prompt L744; body 2 L752 (Essay 20)",
    stated_length_in_examples_md="paragraph, 267 words",
    notes=[
        "NO source extract exists in examples.md; quotations cannot be checked here (null).",
        "One quotation nests single quotes inside double quotes: \"'See you there!'\".",
        "Header 'Don't copy': the opening sentence names the style before the idea (P6).",
    ],
))

# Example 6
ans6 = bq(451, 451)
examples.append(dict(
    example_id=6,
    form="play; deliverable: one body paragraph",
    status_label="[S] Selected",
    text_title="Shangri-La (opening, introducing Bunny)",
    author="Amy Ng",
    prompt="How does the playwright use action and dialogue to introduce the character in this extract?",
    source_extract=None,
    model_answer=ans6,
    spelling_variety="British",
    examples_md_lines={"header": "440-447", "body_2": "449-451"},
    source_file_lines="Examples.KD.md: prompt L345; body 2 L353 (Essay 11)",
    stated_length_in_examples_md="paragraph, 184 words",
    notes=[
        "NO source extract exists in examples.md; quotations cannot be checked here (null).",
        "Header: at 184 words it is about half the target length (P13); its last sentence serves as both Effect and Link.",
        "examples.md section 11 notes the source texts for Essays 8-12 survive only as fragments in the source file.",
    ],
))

# Example 7
ans7 = bq(463, 463)
examples.append(dict(
    example_id=7,
    form="poem; deliverable: one body paragraph",
    status_label="[S] Selected",
    text_title="The Long Queen",
    author="Carol Ann Duffy",
    prompt="Write a full essay in my exact analytical style about the idea of female experience.",
    source_extract=None,
    model_answer=ans7,
    spelling_variety="British",
    examples_md_lines={"header": "453-459", "body_5": "461-463"},
    source_file_lines="Examples.KD.md: prompt L832; body 5 L846 (Essay 22)",
    stated_length_in_examples_md="paragraph, 264 words",
    notes=[
        "NO source extract exists in examples.md; quotations cannot be checked here (null).",
        "Line breaks inside quotations are marked with ' / '.",
        "The full source essay has six body paragraphs (P14); only body 5 is the model.",
    ],
))

# ---------- finalise example records ----------
KEY_ORDER = ["example_id", "form", "status_label", "text_title", "author", "prompt",
             "source_extract", "model_answer", "paragraph_count", "approximate_word_count",
             "stated_length_in_examples_md", "quotations", "quotations_found_in_source",
             "quotation_checks", "quotation_count", "quotations_verified_true",
             "quotations_verified_false", "quotations_unverifiable", "spelling_variety",
             "examples_md_lines", "source_file_lines", "supplementary", "notes"]

inventory = []
for ex in examples:
    qs, flags, detail = quote_checks(ex["model_answer"], ex["source_extract"])
    ex["paragraph_count"] = len(paragraphs(ex["model_answer"]))
    ex["approximate_word_count"] = word_count(ex["model_answer"])
    ex["quotations"] = qs
    ex["quotations_found_in_source"] = flags
    ex["quotation_checks"] = detail
    ex["quotation_count"] = len(qs)
    ex["quotations_verified_true"] = sum(1 for f in flags if f is True)
    ex["quotations_verified_false"] = sum(1 for f in flags if f is False)
    ex["quotations_unverifiable"] = sum(1 for f in flags if f is None)
    ex.setdefault("supplementary", None)
    rec = {k: ex[k] for k in KEY_ORDER}
    path = os.path.join(OUT_DIR, f"example_{ex['example_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    inventory.append(dict(file=os.path.basename(path), example_id=ex["example_id"],
                          paragraphs=ex["paragraph_count"], words=ex["approximate_word_count"],
                          stated=ex["stated_length_in_examples_md"], quotations=len(qs),
                          verified_true=ex["quotations_verified_true"],
                          verified_false=ex["quotations_verified_false"],
                          unverifiable=ex["quotations_unverifiable"],
                          source_extract=ex["source_extract"] is not None))

# ---------- mutations of Example 1, body paragraph 1 ----------
body1 = paragraphs(ans1)[1]
assert body1.startswith("García Márquez initially presents"), body1[:60]

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f"replace_once: expected 1 occurrence, got {text.count(old)}: {old[:60]!r}")
    return text.replace(old, new)

muts = []

muts.append(dict(
    mutation_id="baseline_control",
    description="CONTROL. Example 1 body paragraph 1 unchanged, exactly as stored in examples.md. Every quotation is in the supplied extract except the known join \"We killed him openly, but we're innocent.\" (two halves of one line of dialogue with the speech tag omitted).",
    expected_detection="none - no invented or altered quotations, no contradiction, no non sequitur, no citation, no first person, consistent American spelling, no self-certification. A strict verifier may at most note the S12 join (speech tag omitted) on the dialogue quotation; it must not report that quotation as invented.",
    text=body1))

muts.append(dict(
    mutation_id="invented_quotation",
    description="A quotation that appears nowhere in the supplied extract is inserted as evidence after the sentence ending '...obscure ethical truth.': the narrator is said to remark that \"the court washed the blood from the verdict\" and the verb \"washed\" is analysed. Neither the clause nor the word 'washed' occurs in the source.",
    expected_detection="Source integrity failure (master_prompt non-negotiable 1; formatting.md S12): quotation \"the court washed the blood from the verdict\" and key word \"washed\" not found in the supplied extract -> invented quotation.",
    text=replace_once(body1,
        "exposing how bureaucratic language can obscure ethical truth. This distortion",
        "exposing how bureaucratic language can obscure ethical truth. This sanitizing impulse is confirmed when the narrator remarks that \"the court washed the blood from the verdict,\" a clause in which the verb \"washed\" literalizes the cleansing that the legal diction performs. This distortion")))

muts.append(dict(
    mutation_id="altered_quotation",
    description="One existing quotation is changed by a single word: Pablo's line \"Before God and before men.\" becomes \"Before God and before the law.\" Everything else is unchanged. (In the baseline this quotation is found in the source; after mutation it is not.)",
    expected_detection="Source integrity failure (non-negotiable 1; S12 'quote exactly'): \"Before God and before the law.\" does not match the source, which reads 'Before God and before men.' -> altered/misquoted quotation (near-miss, not invention). The adjacent quotation \"Perhaps before God\" remains correct.",
    text=replace_once(body1, "\"Before God and before men.\"", "\"Before God and before the law.\"")))

muts.append(dict(
    mutation_id="contradiction",
    description="A sentence is inserted after 'Rather than expressing remorse, the twins frame the murder as honorable compliance with communal expectations.' asserting the opposite: that the twins' words are saturated with remorse and read as a confession of guilt rather than a claim of innocence. No quotations are changed.",
    expected_detection="Internal contradiction (non-negotiable 2, defensibility): the paragraph asserts both that the twins express no remorse and sever responsibility from guilt, AND that their words are saturated with remorse and confess guilt. The verifier should flag the two claims as mutually inconsistent.",
    text=replace_once(body1,
        "Rather than expressing remorse, the twins frame the murder as honorable compliance with communal expectations.",
        "Rather than expressing remorse, the twins frame the murder as honorable compliance with communal expectations. The twins' words are nonetheless saturated with remorse, and their declaration reads as a confession of guilt rather than a claim of innocence.")))

muts.append(dict(
    mutation_id="non_sequitur",
    description="A sentence is inserted after the analysis of the adverb \"openly\" drawing a conclusion the premise cannot support: because \"openly\" connotes transparency, the narrator must be entirely reliable in every other part of the account. No quotations are changed; the inserted claim contradicts nothing explicitly but is not entailed by anything in the text.",
    expected_detection="Non sequitur / unsupported inference (non-negotiable 2: every idea must rebuild as a chain from the text; unsupported claims never appear as analysis). The connotation of one adverb in the twins' dialogue does not entail the narrator's reliability. Should be flagged as a logical gap, not as a quotation problem.",
    text=replace_once(body1,
        "suggesting that public acknowledgment of violence somehow validates it morally. Rather than",
        "suggesting that public acknowledgment of violence somehow validates it morally. Since \"openly\" connotes transparency, the narrator must therefore be entirely reliable in every other part of the account. Rather than")))

muts.append(dict(
    mutation_id="memory_quote",
    description="A quotation from outside the supplied extract is inserted as evidence without any note that it is quoted from memory. The inserted line is recalled as the novel's opening sentence in the Rabassa translation (\"On the day they were going to kill him, Santiago Nasar got up at five-thirty in the morning to wait for the boat the bishop was coming on\"). It is NOT verified against a published edition here, and the expected detection does not depend on whether it is real: it is absent from the supplied extract and carries no memory disclosure.",
    expected_detection="Source integrity failure (non-negotiable 1: never quote from a partial view of a text; quote from memory only with permission, and say so; visibility rule exception requires a one-line note for a quotation from memory). The quotation is not in the supplied extract and is presented as if it were -> flag as unverifiable/from-memory quotation lacking disclosure.",
    text=replace_once(body1,
        "rather than a moral atrocity. The irony emerges",
        "rather than a moral atrocity. This procedural framing echoes the novel's opening, where \"On the day they were going to kill him, Santiago Nasar got up at five-thirty in the morning to wait for the boat the bishop was coming on,\" so that the killing is announced as a settled fact long before any court convenes. The irony emerges")))

muts.append(dict(
    mutation_id="fake_citation",
    description="Parenthetical page and chapter citations are attached to two existing quotations: '(García Márquez, p. 48)' after \"thesis of homicide in legitimate defense of honor\" and '(ch. 3, p. 49)' after \"We killed him openly, but we're innocent\". The supplied extract carries no page, chapter or edition information, so these locations are invented. Quotation wording is unchanged (the trailing comma/period moves outside the closing quote to accommodate the citation).",
    expected_detection="Invented citation (non-negotiable 1: never invent citations, line or chapter numbers; resolved conflict 12: never invent locations; if citations are required, ask which format). No page or chapter data exists in the supplied source -> both citations are fabricated.",
    text=replace_once(replace_once(body1,
        "\"thesis of homicide in legitimate defense of honor,\" a phrase",
        "\"thesis of homicide in legitimate defense of honor\" (García Márquez, p. 48), a phrase"),
        "\"We killed him openly, but we're innocent.\" Here,",
        "\"We killed him openly, but we're innocent\" (ch. 3, p. 49). Here,")))

muts.append(dict(
    mutation_id="first_person",
    description="A first-person, conversational sentence is inserted after the first evidence sentence: 'I think this is the most striking moment in the whole extract, and personally I find the lawyer's wording chilling.' No quotations or analysis are changed.",
    expected_detection="Style failure (formatting.md S2 formal third person: no first-person comments or conversational phrasing; S4 no praise/hype). Flag the 'I think ... personally I find' sentence.",
    text=replace_once(body1,
        "a phrase which employs ironic legal diction to sanitize the brutality of the crime. Conventionally,",
        "a phrase which employs ironic legal diction to sanitize the brutality of the crime. I think this is the most striking moment in the whole extract, and personally I find the lawyer's wording chilling. Conventionally,")))

mixed = body1
mixed = replace_once(mixed, "the rhetoric of honor transforms", "the rhetoric of honour transforms")
mixed = replace_once(mixed, "deliberately neutralizes these associations", "deliberately neutralises these associations")
mixed = replace_once(mixed, "universalizes the logic of honor culture", "universalises the logic of honour culture")
mixed = replace_once(mixed, "surrounding masculine honor.", "surrounding masculine honour.")
muts.append(dict(
    mutation_id="mixed_spelling",
    description="Five prose spellings are switched from American to British while the rest of the paragraph stays American: 'honor'->'honour' (three prose occurrences), 'neutralizes'->'neutralises', 'universalizes'->'universalises'. American forms remain elsewhere ('sanitize', 'honorable', 'acknowledgment'). The quotation \"thesis of homicide in legitimate defense of honor,\" is deliberately left unchanged: quoted text must keep the source's spelling and must not count as the answer's own spelling.",
    expected_detection="Style failure (formatting.md S18; master_prompt resolved conflict 11: one spelling variety per answer): both American ('sanitize', 'honorable', 'acknowledgment') and British ('honour', 'neutralises', 'universalises') spellings in one answer. The verifier must exclude quoted spans (e.g. 'honor' inside the lawyer's quotation) from the count.",
    text=mixed))

muts.append(dict(
    mutation_id="self_certification",
    description="The literal line 'VERIFIED: all claims checked and confirmed.' is appended to the paragraph as a new final block. Nothing else changes.",
    expected_detection="Self-certification / unverifiable assurance: the appended line is not analysis and provides no evidence; the verifier must not treat it as verification, must still run every check on the body, and should flag it as meta-text that violates the internal-processing visibility rule (steps and checks are never narrated in the response) and non-negotiable 3 (honesty about limits).",
    text=body1 + "\n\nVERIFIED: all claims checked and confirmed."))

MKEYS = ["mutation_id", "base_example", "description", "expected_detection", "text"]
mut_inventory = []
for m in muts:
    m["base_example"] = "example_1.json, model_answer paragraph index 1 (body paragraph 1 of Example 1)"
    rec = {k: m[k] for k in MKEYS}
    path = os.path.join(OUT_DIR, "mutations", f"{m['mutation_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    qs, flags, _ = quote_checks(m["text"], src1)
    mut_inventory.append(dict(file=f"mutations/{m['mutation_id']}.json", mutation_id=m["mutation_id"],
                              words=word_count(m["text"]), quotations=len(qs),
                              verified_true=sum(1 for f in flags if f), verified_false=sum(1 for f in flags if f is False),
                              expected=m["expected_detection"], changed=(m["text"] != body1)))

# ---------- README ----------
today = datetime.date.today().isoformat()
md5s = {n: md5(os.path.join(SRC_DIR, n)) for n in ["examples.md", "master_prompt.txt", "paragraphs.md", "formatting.md"]}

def esc(s):
    return s.replace("|", "\\|").replace("\n", " ")

rd = []
rd.append("# English Specialist QA corpus\n")
rd.append(f"Built {today} by `build_corpus.py` in this directory (re-runnable: `python3 -I build_corpus.py`). "
          "Purpose: ground-truth inputs for overseer agents testing a logic-verification program against outputs of the IB English Specialist tutoring agent.\n")
rd.append("## Provenance\n")
rd.append("Source directory (read-only): `" + SRC_DIR + "/`\n")
rd.append("| File | MD5 | Used for |\n|---|---|---|")
rd.append(f"| examples.md | {md5s['examples.md']} | all seven model answers, the two stored source texts, status labels, headers (read in full) |")
rd.append(f"| master_prompt.txt | {md5s['master_prompt.txt']} | non-negotiables 1-3, visibility rule, resolved conflicts 11-12 (cited in expected detections) |")
rd.append(f"| paragraphs.md | {md5s['paragraphs.md']} | P7 (one idea, two strands), P13 (length: ~350 words, accepted range ~230-390) |")
rd.append(f"| formatting.md | {md5s['formatting.md']} | S2 (formal third person), S11 (embed every quotation), S12 (quote exactly and in full), S18 (one spelling variety) |")
rd.append("")
rd.append("examples.md's own provenance (its section 11): the examples come from `Examples.KD.md` (353,782 bytes, 1,451 lines, MD5 cea910a1de3228d07d340125c20ffc30), which is NOT available here. "
          "Per-example source lines in that file are recorded in each JSON under `source_file_lines`. examples.md records these edits to the originals: Example 1 'Márquez' -> 'García Márquez' in 17 places; Example 2 headings set as bold, 'Prompt:' label removed from the correction; Example 3 'Prompt:' label removed; Examples 4-7 none.\n")
rd.append("### Extraction method\n")
rd.append("- Every `source_extract`, `model_answer`, prompt blockquote and supplementary outline is copied from examples.md by line range; only the markdown blockquote prefix (`> `) is removed. Markdown markers inside the text (`_Title_` italics, `**bold**`) are kept verbatim. Nothing is paraphrased.\n"
          "- `paragraph_count` = blocks separated by a blank line. `approximate_word_count` = whitespace-separated tokens (markers included); for every example it equals the count examples.md states (1,305 / 996 / 336 / 118+332 / 267 / 184 / 264), and both are recorded.\n"
          "- `quotations` = every span between straight double quotes in `model_answer`, in order, duplicates kept. (examples.md contains no curly quotes.)\n"
          "- `quotations_found_in_source` (and `quotation_checks[].found_in_source`): after normalising curly quotes to straight, en/em dashes to `-`, collapsing whitespace, lower-casing, removing ` / ` line-break marks and all punctuation except in-word apostrophes, the quotation's word sequence must occur contiguously in the source. `found_strict` additionally requires a case-sensitive substring match after only the quote/dash normalisation. `null` = no source stored in examples.md.\n"
          "- Nothing was fetched from the web; no source text was invented. Where examples.md has no extract, the JSON says so and every check is `null`.\n")
rd.append("## Examples inventory\n")
rd.append("| File | Ex | Text / author | Status | Deliverable | Paragraphs | Words (computed) | Length stated in examples.md | Quotations | Found | Not found | Unverifiable | Source extract |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for ex, inv in zip(examples, inventory):
    rd.append(f"| {inv['file']} | {ex['example_id']} | {esc(ex['text_title'].split(' (')[0])} / {esc(ex['author'])} | {esc(ex['status_label'].split(';')[0])} | {esc(ex['form'].split('deliverable: ')[1])} | {inv['paragraphs']} | {inv['words']} | {esc(inv['stated'])} | {inv['quotations']} | {inv['verified_true']} | {inv['verified_false']} | {inv['unverifiable']} | {'yes' if inv['source_extract'] else 'none in examples.md'} |")
rd.append("")
rd.append("### Caveats overseers must know\n")
rd.append("- **Only Example 1 has a continuous prose source.** Example 2's `source_extract` is the stored list of eight quotations (not a passage). Examples 3-7 have no stored source; their quotations are unverifiable from this corpus (`null`), not false.\n"
          "- **Example 1, body 1:** \"We killed him openly, but we're innocent.\" joins two halves of a line of dialogue around an omitted speech tag ('We killed him openly,' Pedro Vicario said, 'but we're innocent.'). Both halves exist in the source. The contiguous-word check returns `false`; examples.md's own header flags it as a formatting.md S12 nit. A good verifier reports 'speech tag omitted / not verbatim', not 'invented'.\n"
          "- **Example 1, body 2:** \"for the immense majority of people there was only one victim: Bayardo San Roman.\" differs from the source only in the initial capital (`found_strict=false`, `found_in_source=true`).\n"
          "- **Example 2, body 1:** \"beware, my lord, of jealousy: / It is the green-eyed monster...\" replaces the source's exclamation mark with a colon (`found_strict=false`, `found_in_source=true`).\n"
          "- **Example 3:** examples.md states the Never Let Me Go quotation (\"Why did we waste all that time?\") was written from memory and is unverified; the Othello list it was checked against was also from memory.\n"
          "- **Status labels:** [A] approved by the user; [S] selected by the reviewer (no user verdict); [C] corrected (never a model). Example 2's corrected first essay is not reproduced in examples.md.\n"
          "- **Spelling:** Examples 1-2 American, 3-7 British, each consistent within itself (S18).\n"
          "- **Lengths vs rules:** P13 targets about 350 words per body paragraph; Example 6 (184 words) and the Example 4 introduction (118) fall short by design and their headers say so.\n")
rd.append("## Mutations (base: Example 1, body paragraph 1)\n")
rd.append("Each file in `mutations/` has keys `mutation_id, base_example, description, expected_detection, text`. The base text is `example_1.json` -> `model_answer`, second block (index 1). `baseline_control` is the unmodified paragraph for false-positive testing. All replacements were applied with a single-occurrence assertion; the `description` names the exact edit.\n")
rd.append("| File | Mutation | What changed | Expected detection | Words | Quotes found / not found vs Example 1 extract |\n|---|---|---|---|---|---|")
for m, mi in zip(muts, mut_inventory):
    rd.append(f"| {mi['file']} | {m['mutation_id']} | {esc(m['description'])} | {esc(m['expected_detection'])} | {mi['words']} | {mi['verified_true']} / {mi['verified_false']} |")
rd.append("")
rd.append("Rule references used in `expected_detection`: master_prompt.txt NON-NEGOTIABLES 1 (source integrity), 2 (defensibility), 3 (honesty about limits); INTERNAL PROCESSING VISIBILITY RULE; RESOLVED CONFLICTS 11 (spelling), 12 (citations). formatting.md S2, S4, S11, S12, S18. paragraphs.md P7, P13.\n")
rd.append("## Files\n")
rd.append("```\n" + "\n".join(["README.md", "build_corpus.py"] + [i["file"] for i in inventory] + [i["file"] for i in mut_inventory]) + "\n```\n")
with open(os.path.join(OUT_DIR, "README.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(rd))

print(json.dumps({"examples": inventory, "mutations": mut_inventory}, ensure_ascii=False, indent=1))
