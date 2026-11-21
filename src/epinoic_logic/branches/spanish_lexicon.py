"""Spanish readers for the Language B branch (D9/D10, decision D35): pure data and bounded, linear readers.

Nothing here evaluates agent text. Every reader is one pass (or one ``finditer`` of one alternation pattern) over a bounded prefix of
its input, so a long hostile answer is read in time linear in its length:

* :func:`is_spanish` / :func:`spanish_paragraphs`: whether a text (a paragraph) is Spanish, by a closed set of function words and the
  inverted marks ``¿`` / ``¡``;
* :func:`spanish_numeral_readings`: every value a written numeral can have (``1.250`` is 1250 in Spanish text and 1.25 in English
  text; ``2,5`` is 2.5; a thin or no-break space groups thousands). A check holds when ANY reading holds, the worked reader's rule;
* :func:`spanish_number_figures`: figures written in Spanish words (the ledger's reader, re-exported under a public name);
* :data:`SPANISH_CREDIT_RE`: a credit to the supplied text ("según el texto", "el texto dice", "(línea 4)");
* :data:`CONNECTORS`, :data:`TEXT_TYPES`, the layout readers and the address-form markers: closed tables written in this module's
  own words (forms only, never copied text);
* :func:`inverted_mark_spans`: each ``¿`` / ``¡`` paired with the next ``?`` / ``!`` in one pass, so a question is never read as a
  claim about a production.

These readers find things; they never judge the quality of the Spanish (register, accuracy and text-type fit are the subject
evaluator's and the overseer's, the profile's ``cannot_check``).
"""
from __future__ import annotations

import re
from fractions import Fraction
from typing import Optional

__all__ = ["ADDRESS_FORMS", "CONNECTORS", "SPANISH_CREDIT_RE", "TEXT_TYPES", "address_markers", "closing_line", "connector_forms",
           "english_ratio", "greeting_line", "inverted_mark_spans", "is_spanish", "spanish_number_figures", "spanish_numeral_readings",
           "spanish_paragraphs", "text_type_of"]

#: How much of a text :func:`is_spanish` reads, and how much of one paragraph :func:`spanish_paragraphs` reads.
MAX_DETECT_CHARS = 20_000
MAX_PARAGRAPH_CHARS = 4_000
_PARA_RE = re.compile(r"\n[ \t]*\n")
#: A word: a run of letters (no digits); bounded so a joined token is one token, read once.
_WORD_RE = re.compile(r"[^\W\d_]{1,40}+")

#: Spanish function words (closed set). A text is Spanish when enough of its words are these.
SPANISH_FUNCTION_WORDS = frozenset("""de la que el en los las del por una con para es se su al lo como más pero muy también porque está son""".split())
#: English function words, to tell an English meta paragraph from a target-language one.
ENGLISH_FUNCTION_WORDS = frozenset("""the and of to in is that for it with as on this are be you your from by was have has not but which an at or so""".split())


def _tokens(text: str) -> list[str]:
    return [w.casefold() for w in _WORD_RE.findall(text)]


def is_spanish(text: Optional[str]) -> bool:
    """Whether ``text`` is Spanish: at least 8 of its words are Spanish function words and they make up at least 12 % of its words, or
    it holds ``¿`` / ``¡`` at least three times with at least 4 function-word hits. One pass over the first 20,000 characters."""
    s = (text or "")[:MAX_DETECT_CHARS]
    toks = _tokens(s)
    if not toks:
        return False
    hits = sum(1 for t in toks if t in SPANISH_FUNCTION_WORDS)
    if hits >= 8 and hits * 100 >= 12 * len(toks):
        return True
    return (s.count("¿") + s.count("¡")) >= 3 and hits >= 4


def english_ratio(text: Optional[str]) -> tuple[int, int, int]:
    """``(english hits, spanish hits, words)`` of ``text`` (first 4,000 characters)."""
    toks = _tokens((text or "")[:MAX_PARAGRAPH_CHARS])
    return (sum(1 for t in toks if t in ENGLISH_FUNCTION_WORDS), sum(1 for t in toks if t in SPANISH_FUNCTION_WORDS), len(toks))


def spanish_paragraphs(text: Optional[str]) -> list[int]:
    """The indices (0-based, blank-line paragraphs) of the Spanish paragraphs of ``text``. A paragraph is read on its first 4,000
    characters; a short paragraph passes on fewer hits (at least 3, and 25 % of its words) or with an inverted mark and 2 hits."""
    out: list[int] = []
    for i, para in enumerate(p for p in _PARA_RE.split((text or "")[:200_000]) if p.strip()):
        chunk = para[:MAX_PARAGRAPH_CHARS]
        toks = _tokens(chunk)
        hits = sum(1 for t in toks if t in SPANISH_FUNCTION_WORDS)
        en = sum(1 for t in toks if t in ENGLISH_FUNCTION_WORDS)
        if en > hits:
            continue
        if is_spanish(chunk) or (toks and hits >= 3 and hits * 4 >= len(toks)) or (("¿" in chunk or "¡" in chunk) and hits >= 2):
            out.append(i)
    return out


# ------------------------------------------------------------------------------------------------------------------ numerals
_MAX_TOKEN = 24
_NUMERAL_RE = re.compile(r"[−-]?\d{1,3}(?:[.,   ]\d{3})++(?:[.,]\d{1,6})?|[−-]?\d{1,12}(?:[.,]\d{1,6})?")


def spanish_numeral_readings(token: str, language: Optional[str] = None) -> frozenset[Fraction]:
    """Every value the numeral ``token`` can have. ``language``: ``"es"`` (Spanish text: ``.`` groups thousands, ``,`` marks
    decimals), ``"en"`` (English text: the reverse) or None (unknown: both). A thin or no-break space groups thousands. A token over
    24 characters or not a numeral has no reading."""
    t = (token or "").strip()
    if not t or len(t) > _MAX_TOKEN or _NUMERAL_RE.fullmatch(t) is None:
        return frozenset()
    sign = -1 if t[0] in "−-" else 1
    t = t.lstrip("−-")
    t = t.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    if " " in t:
        t = t.replace(" ", "")
    out: set[Fraction] = set()

    def reading(thousands: str, decimal: str) -> Optional[Fraction]:
        s = t
        if thousands in s:
            groups = s.split(decimal)[0].split(thousands)
            if any(len(g) != 3 for g in groups[1:]) or not groups[0] or len(groups[0]) > 3:
                return None
            s = s.replace(thousands, "")
        if s.count(decimal) > 1:
            return None
        try:
            return Fraction(s.replace(decimal, "."))
        except (ValueError, ZeroDivisionError):
            return None

    langs = ("es", "en") if language not in ("es", "en") else (language,)
    for lang in langs:
        v = reading(".", ",") if lang == "es" else reading(",", ".")
        if v is not None:
            out.add(sign * v)
    if language == "es" and "," in t and "." not in t:
        # '1,250' in Spanish text: a decimal comma (1.25) or an English-style group (1250); both readings
        alt = reading(",", ".")
        if alt is not None:
            out.add(sign * alt)
    return frozenset(out)


def spanish_number_figures(text: str) -> list[tuple[int, int, str]]:
    """``(start, end, value)`` for every figure written in Spanish words in ``text`` ("dos mil trescientos cuarenta y cinco", a small
    count before a count noun): the ledger's one-pass reader (``integrity.ledger``), re-exported under a public name."""
    from ..integrity.ledger import _spanish_word_figures
    t = (text or "")[:200_000]
    if t and _SENTENCE_NUMBER_RE.search(t):
        # a number word that opens a sentence is capitalised ("Quince alumnos volvieron ...", "Mil doscientos cincuenta habitantes
        # tenía ...") and the ledger's reader reads number words in lower case only (a capitalised "Once" is English): lower its
        # first letter, length kept, so the figure is read at its place
        t = _SENTENCE_NUMBER_RE.sub(lambda m: m.group(1) + m.group(2)[0].lower() + m.group(2)[1:], t)
    return _spanish_word_figures(t)


#: A capitalised Spanish number word at the start of a sentence, a line or a quotation (not "Once", which English writes).
_SENTENCE_NUMBER_RE = re.compile(
    r"((?:^|(?<=\n)|(?<=[.!?¿¡:;«\"“(])\s{0,3}|(?<=[.!?:;]\s)\s{0,2})(?:\d{1,3}[.)]\s{1,3})?)"
    r"((?:Un|Una|Uno|Dos|Tres|Cuatro|Cinco|Seis|Siete|Ocho|Nueve|Diez|Doce|Trece|Catorce|Quince|Dieciséis|Dieciseis|Diecisiete|"
    r"Dieciocho|Diecinueve|Veinte|Veinti\w{2,6}|Treinta|Cuarenta|Cincuenta|Sesenta|Setenta|Ochenta|Noventa|Cien|Ciento|"
    r"Doscientos|Doscientas|Trescientos|Trescientas|Cuatrocientos|Cuatrocientas|Quinientos|Quinientas|Seiscientos|Seiscientas|"
    r"Setecientos|Setecientas|Ochocientos|Ochocientas|Novecientos|Novecientas|Mil)(?![\w-]))")


# ------------------------------------------------------------------------------------------------------------------ credits
#: A credit to the supplied text, read like grounded_figures' English credits.
SPANISH_CREDIT_RE = re.compile(
    r"(?<![\w-])(?:seg[uú]n\s++(?:el|la)\s++(?:texto|art[ií]culo|autora?|primer\s++p[aá]rrafo|p[aá]rrafo|fragmento|extracto|entrevista|carta|lectura)"
    r"|(?:el|la)\s++(?:texto|art[ií]culo|autora?)\s++(?:dice|indica|afirma|se[nñ]ala|explica|menciona|cuenta)"
    r"|como\s++dice\s++el\s++texto|en\s++el\s++texto|\((?:l[ií]nea|p[aá]rrafo)\s++\d{1,3}\))(?![\w-])", re.IGNORECASE)

# ------------------------------------------------------------------------------------------------------------------ connectors
#: Spanish connectors with their function (closed table).
CONNECTORS: tuple[tuple[str, str], ...] = tuple(
    (form, function) for function, forms in (
        ("addition", "además|asimismo|también|igualmente|del mismo modo|por otra parte|por otro lado|incluso|encima"),
        ("contrast", "sin embargo|no obstante|en cambio|aunque|mientras que|por el contrario|a pesar de|pero|sino|aun así|ahora bien|con todo"),
        ("cause", "porque|ya que|puesto que|debido a|dado que|como consecuencia de|a causa de|gracias a"),
        ("consequence", "por lo tanto|por eso|así que|por consiguiente|de este modo|así|por ello|en consecuencia|de ahí que|por esta razón"),
        ("sequence", "en primer lugar|en segundo lugar|primero|segundo|tercero|luego|después|por último|finalmente|para empezar|a continuación"),
        ("example", "por ejemplo|es decir|o sea|en otras palabras|como por ejemplo"),
        ("conclusion", "en conclusión|en resumen|para concluir|para terminar|en definitiva|en suma"),
        ("opinion", "en mi opinión|desde mi punto de vista|a mi juicio|creo que|considero que"),
    ) for form in forms.split("|"))
_CONNECTOR_RE = re.compile(r"(?<![\w-])(?:" + "|".join(sorted((re.escape(f) for f, _ in CONNECTORS), key=len, reverse=True)) + r")(?![\w-])", re.IGNORECASE)


def connector_forms(text: str) -> list[str]:
    """The Spanish connectors ``text`` writes, in order (one ``finditer``)."""
    return [m.group(0).casefold() for m in _CONNECTOR_RE.finditer((text or "")[:200_000])]


# ------------------------------------------------------------------------------------------------------------------ text types
#: Text types a Paper 1 request names: (key, Spanish names and aliases, register expected, layout parts).
TEXT_TYPES: tuple[tuple[str, tuple[str, ...], str, tuple[str, ...]], ...] = (
    ("formal_letter", ("carta formal",), "formal", ("date", "greeting", "closing", "signature")),
    ("informal_letter", ("carta informal", "carta a un amigo", "carta a una amiga"), "informal", ("greeting", "closing", "signature")),
    ("letter_to_editor", ("carta al director", "carta al editor"), "formal", ("greeting", "closing", "signature")),
    ("email", ("correo electrónico", "correo", "email", "e-mail", "mensaje"), "either", ("subject", "greeting", "closing", "signature")),
    ("article", ("artículo de opinión", "artículo"), "either", ("headline", "byline")),
    ("blog", ("entrada de blog", "blog"), "informal", ("headline", "date")),
    ("diary", ("entrada de diario", "diario"), "informal", ("date", "greeting")),
    ("speech", ("discurso", "charla"), "either", ("audience", "thanks")),
    ("leaflet", ("folleto",), "either", ("headline",)),
    ("report", ("informe",), "formal", ("headline", "date")),
    ("interview", ("entrevista",), "either", ("headline",)),
    ("review", ("reseña", "crítica"), "either", ("headline",)),
    ("proposal", ("propuesta",), "formal", ("headline",)),
)
_TEXT_TYPE_RE = re.compile(r"(?<![\w-])(?P<t>" + "|".join(sorted({re.escape(a) for _k, al, _r, _p in TEXT_TYPES for a in al}, key=len, reverse=True))
                           + r")(?![\w-])", re.IGNORECASE)


def text_type_of(request_text: Optional[str]) -> Optional[str]:
    """The text type a request names ("Escribe un artículo de opinión ..."): its key, or None. One search of the first 20,000
    characters."""
    m = _TEXT_TYPE_RE.search((request_text or "")[:MAX_DETECT_CHARS])
    if m is None:
        return None
    name = m.group("t").casefold()
    return next((k for k, al, _r, _p in TEXT_TYPES if name in al), None)


#: Layout parts, each read on one line (the first 200 characters).
_GREETING_RE = re.compile(r"^\s*+(?:(?:estimad[oa]s?|querid[oa]s?|apreciad[oa]s?)\s[^\n]{0,80}:|¡hola[^\n]{0,60}!|hola[^\n]{0,60}[:,]|"
                          r"(?:queridos?|queridas?)\s+compañer[oa]s[^\n]{0,40}[:,]?|señoras\s+y\s+señores[^\n]{0,40}[:,]?)\s*+$", re.IGNORECASE)
_CLOSING_RE = re.compile(r"^\s*+(?:atentamente|un\s+cordial\s+saludo|saludos(?:\s+cordiales)?|un\s+(?:fuerte\s+)?abrazo(?:\s+muy\s+fuerte)?|besos|"
                         r"hasta\s+pronto|un\s+saludo|muchos\s+besos|cordialmente|gracias\s+por\s+su\s+atención)\s*+[,.!]?\s*+$", re.IGNORECASE)
_BYLINE_RE = re.compile(r"^\s*+(?:por|by)\s++[^\W\d_][^\n]{1,120}$", re.IGNORECASE)
_SUBJECT_LINE_RE = re.compile(r"^\s*+(?:asunto|para|de|fecha)\s*+:", re.IGNORECASE)


def greeting_line(line: str) -> bool:
    return _GREETING_RE.match((line or "")[:200]) is not None


def closing_line(line: str) -> bool:
    return _CLOSING_RE.match((line or "")[:200]) is not None


def byline(line: str) -> bool:
    return _BYLINE_RE.match((line or "")[:200]) is not None


def header_line(line: str) -> bool:
    return _SUBJECT_LINE_RE.match((line or "")[:200]) is not None


# ------------------------------------------------------------------------------------------------------------------ address forms
#: The address forms a production may use, and their UNAMBIGUOUS markers. ``su``, ``sus``, ``le``, ``les`` and third-person verb
#: forms are ambiguous (usted, ustedes, él, ellos), so they are never markers: a check never fails on an ambiguous form.
ADDRESS_FORMS = ("tú", "vos", "usted", "vosotros", "ustedes")
_NOT_VOSOTROS = frozenset("""país maíz raíz oís reís leís freís maís""".split())
_VOSOTROS_WORDS = frozenset("""vosotros vosotras os vuestro vuestra vuestros vuestras""".split())
_ADDRESS_RES = {
    "tú": re.compile(r"(?<![\w-])(?:tú|contigo|te|tus?(?=\s++[^\W\d_]))(?![\w-])", re.IGNORECASE),
    "vos": re.compile(r"(?<![\w-])vos(?![\w-])", re.IGNORECASE),
    "usted": re.compile(r"(?<![\w-])(?:usted|ud\.|vd\.)(?![\w-])", re.IGNORECASE),
    "vosotros": re.compile(r"(?<![\w-])(?:vosotr[oa]s|os|vuestr[oa]s?)(?![\w-])|(?<![\w-])[^\W\d_]{1,36}(?:áis|éis|ís)(?![\w-])", re.IGNORECASE),
    "ustedes": re.compile(r"(?<![\w-])(?:ustedes|uds\.|vds\.)(?![\w-])", re.IGNORECASE),
}
#: The names of the address forms as an answer writes them ("vosotros forms", "usted", "tuteo").
ADDRESS_NAME_RE = re.compile(r"(?<![\w-])(?P<f>tú|tu|vos|usted|ustedes|vosotros|tuteo|voseo|ustedeo)(?![\w-])", re.IGNORECASE)
_ADDRESS_ALIASES = {"tu": "tú", "tuteo": "tú", "voseo": "vos", "ustedeo": "usted"}


def address_name(word: str) -> Optional[str]:
    w = (word or "").casefold()
    w = _ADDRESS_ALIASES.get(w, w)
    return w if w in ADDRESS_FORMS else None


def address_markers(text: str, form: str) -> list[str]:
    """The unambiguous markers of ``form`` in ``text`` (one ``finditer``; first 200,000 characters). A word ending -áis/-éis/-ís is
    a vosotros marker only when it has at least four letters and is not a noun of the stop list (país, maíz, raíz, ...)."""
    rx = _ADDRESS_RES.get(form)
    if rx is None:
        return []
    out: list[str] = []
    for m in rx.finditer((text or "")[:200_000]):
        w = m.group(0)
        low = w.casefold()
        if form == "vosotros" and low not in _VOSOTROS_WORDS and (len(low) < 4 or low in _NOT_VOSOTROS):
            continue  # a verb ending -áis/-éis/-ís on a short word or a noun of the stop list is no marker
        out.append(w)
        if len(out) >= 64:
            break
    return out


# ------------------------------------------------------------------------------------------------------------------ inverted marks
_MAX_MARK_DEPTH = 8


def inverted_mark_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of every question or exclamation opened by ``¿`` / ``¡`` and closed by the next ``?`` / ``!`` of its kind: one
    left-to-right pass with a stack of depth at most 8; an unmatched mark is dropped, never rescanned."""
    out: list[tuple[int, int]] = []
    stack: list[tuple[str, int]] = []
    s = (text or "")[:200_000]
    for i, ch in enumerate(s):
        if ch in "¿¡":
            if len(stack) < _MAX_MARK_DEPTH:
                stack.append(("?" if ch == "¿" else "!", i))
        elif ch in "?!":
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0] == ch:
                    out.append((stack[k][1], i + 1))
                    del stack[k:]
                    break
    return sorted(out)
