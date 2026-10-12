"""Single-pass tokenizer for STEM math (section 4.4 of docs/STEM_DESIGN.md).

One forward pass over a region of the reading view; every character is consumed once,
lookahead is bounded (the number scanner's scientific forms, a LaTeX command name, a
subscript), and no backtracking regular expression runs on unbounded text. The lexer
never raises: a character or command outside the grammar becomes an ``ERROR`` token whose
``value`` names it (the parser turns it into ST-PARSE-001), and a span with more tokens
than ``max_tokens`` stops with ``overflow`` set (ST-LIM-001).

Token kinds:

``NUM``      a numeral (``value``: :class:`~epinoic_logic.stem.numbers.ExactNumber`), incl.
             scientific forms, a bare power of ten, a vulgar fraction ``½`` and based numerals
             (``0xFF``, ``0b1010``, ``FF₁₆``, ``1010₂``)
``NUMERR``   a numeral breaking a bound (``value``: ``(code, message)``)
``IDENT``    a run of Latin letters, or one Greek letter; ``sub`` is its subscript (``v₀``,
             ``v_0``, ``v_{max}``, ``Q1``, ``T½``, ``W∥``), ``primes`` its primes, ``delta`` a
             fused ``Δ``/``\\Delta`` prefix (``Δv``, ``ΔKE``)
``FUNC``     sin cos tan arcsin arccos arctan (and ``sin⁻¹`` ...), ln, log (``value``: its base:
             ``log₂``, ``log_{10}``, ``lg``), exp, sqrt, ``√``, ``∛``
``OP``       ``+ - × · * / ÷ ± ∓`` (LaTeX ``\\cdot \\times \\div \\pm \\mp``)
``REL``      ``= ≈ ≃ ≠ < > ≤ ≥ ⇒ ∴ → ⇌ ⇔ ≡ ∝`` and their ASCII and LaTeX spellings
``BOOL``     ``∧ ∨ ¬ ⊕`` and, with ``cs``, the words AND OR NOT XOR
``LPAR`` ``RPAR``   ``( [ {`` and ``) ] }`` (``\\left(``, ``\\{`` ...); in LaTeX a bare brace is a group:
``LGROUP`` ``RGROUP``
``COMMA SEMI COLON PERCENT DEGREE PRIME BAR BANG AMP ROWSEP CARET DSTAR``
``SUP``      a superscript integer (``value``: int) or a lone superscript sign (``value`` None)
``SUB``      a subscript not attached to a letter (``value``: its text): ``(255)₁₀``, ``]_0^2``
``TEXT``     ``\\text{…}``, ``\\mathrm{…}``, ``\\operatorname{…}`` (``value``: inner offsets)
``LATEX``    ``\\frac \\dfrac \\tfrac \\sqrt``
``INF``      ``∞``, ``\\infty``
``UNSUP``    the start of a construct outside the encodings (``value``: the reason): ``∫ Σ ∏ ∂ ∇
             lim d/dx \\int \\sum \\lim \\vec \\mathbf \\partial \\binom \\ldots``, matrices
``PUNCT``    a full stop that is not a decimal point, ``?``, ``…``
``QUOTE``    a quotation mark
``OTHER``    any other single character (``✓``, ``#``, an en dash between numbers ...)
``ERROR``    an unknown LaTeX command or a character of another script (a confusable)

Every token records ``space`` (whitespace or LaTeX spacing right before it), so ``m s``
(metre second) and ``ms`` (millisecond) stay different and juxtaposition can be told from
a gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, NamedTuple, Optional

from .limits import DEFAULT_LIMITS, StemLimits
from .numbers import (
    SUBSCRIPT_DIGITS, SUPERSCRIPT_DIGITS, SUPERSCRIPT_SIGNS, VULGAR_FRACTIONS, exact_integer, exact_vulgar, is_ascii_digit, scan_based, scan_number,
    superscript_int,
)

__all__ = ["FUNCTIONS", "GREEK", "LATEX_GREEK", "LexResult", "Token", "lex"]

LexMode = Literal["plain", "latex"]


class Token(NamedTuple):
    """One token (immutable; a named tuple, so a long answer's tokens are cheap to build)."""

    kind: str
    text: str
    start: int
    end: int
    space: bool = False
    value: Any = None
    sub: str = ""
    primes: int = 0
    delta: bool = False

    def __repr__(self) -> str:  # compact, for test failure messages
        extra = ""
        if self.sub:
            extra += f"_{self.sub}"
        if self.primes:
            extra += "'" * self.primes
        if self.delta:
            extra = "Δ" + extra
        return f"{self.kind}({self.text!r}{extra}@{self.start})"


@dataclass(frozen=True)
class LexResult:
    tokens: tuple[Token, ...]
    overflow: bool = False

    @property
    def errors(self) -> tuple[Token, ...]:
        return tuple(t for t in self.tokens if t.kind in ("ERROR", "NUMERR"))


#: Greek letters (Unicode), lower and upper case, plus the micro sign read as mu
GREEK = frozenset("αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ") | {"µ", "ϕ", "ϵ", "ϑ"}
LATEX_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ",
    "vartheta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "varrho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
}
#: function names (letter runs and LaTeX commands) -> canonical name
FUNCTIONS = {"sin": "sin", "cos": "cos", "tan": "tan", "arcsin": "arcsin", "arccos": "arccos", "arctan": "arctan", "ln": "ln", "log": "log",
             "lg": "log10", "exp": "exp", "sqrt": "sqrt"}
_INVERSE = {"sin": "arcsin", "cos": "arccos", "tan": "arctan"}
_LATEX_REL = {"approx": "≈", "neq": "≠", "ne": "≠", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "lt": "<", "gt": ">", "leqslant": "≤",
              "geqslant": "≥", "Rightarrow": "⇒", "implies": "⇒", "to": "→", "rightarrow": "→", "longrightarrow": "→",
              "rightleftharpoons": "⇌", "therefore": "∴", "iff": "⇔", "Leftrightarrow": "⇔", "equiv": "≡", "sim": "≈", "simeq": "≃",
              "propto": "∝", "Longrightarrow": "⇒"}
_LATEX_OP = {"cdot": "·", "times": "×", "div": "÷", "pm": "±", "mp": "∓"}
_LATEX_BOOL = {"land": "∧", "wedge": "∧", "lor": "∨", "vee": "∨", "lnot": "¬", "neg": "¬", "oplus": "⊕"}
_LATEX_SPACE = {"quad", "qquad", "displaystyle", "textstyle", "big", "Big", "bigl", "bigr", "Bigl", "Bigr", "nonumber", "notag", "hfill"}
_LATEX_TEXT = {"text", "mathrm", "operatorname", "textrm", "rm", "mbox", "textit", "mathit"}
_LATEX_STRUCT = {"frac": "\\frac", "dfrac": "\\frac", "tfrac": "\\frac", "sqrt": "\\sqrt"}
_LATEX_UNSUP = {"int": "an integral", "iint": "an integral", "oint": "an integral", "sum": "a sum (Σ)", "prod": "a product (∏)",
                "lim": "a limit", "vec": "a vector", "mathbf": "a vector or matrix in bold", "boldsymbol": "a vector in bold",
                "partial": "a partial derivative", "nabla": "a vector operator", "binom": "a binomial coefficient", "ldots": "an ellipsis",
                "cdots": "an ellipsis", "dots": "an ellipsis", "overrightarrow": "a vector", "hat": "a unit vector or estimator",
                "underbrace": "an annotation brace", "overbrace": "an annotation brace", "mathcal": "a calligraphic symbol",
                "det": "a determinant", "max": "a maximum", "min": "a minimum", "infty": "infinity", "circ": "a composition"}
_LATEX_FUNC = {"sin": "sin", "cos": "cos", "tan": "tan", "arcsin": "arcsin", "arccos": "arccos", "arctan": "arctan", "ln": "ln", "log": "log",
               "exp": "exp", "lg": "log10"}
_PLAIN_REL = {"=": "=", "≈": "≈", "≃": "≃", "≠": "≠", "<": "<", ">": ">", "≤": "≤", "≥": "≥", "⩽": "≤", "⩾": "≥", "⇒": "⇒", "∴": "∴",
              "→": "→", "⟶": "→", "⇌": "⇌", "⇔": "⇔", "⟺": "⇔", "≡": "≡", "∝": "∝", "⟹": "⇒", "↔": "⇔", "≅": "≈"}
_PLAIN_OP = {"+": "+", "-": "-", "×": "×", "·": "·", "*": "*", "/": "/", "÷": "÷", "±": "±", "∓": "∓", "∕": "/"}
_PLAIN_BOOL = {"∧": "∧", "∨": "∨", "¬": "¬", "⊕": "⊕"}
_UNSUP_CHARS = {"∫": "an integral", "∑": "a sum (Σ)", "∏": "a product (∏)", "∂": "a partial derivative", "∇": "a vector operator",
                "∮": "an integral", "⃗": "a vector"}
_QUOTES = frozenset("\"“”„‟«»‘’‚‛")
_SUBSCRIPT_LETTERS = {"ₐ": "a", "ₑ": "e", "ₒ": "o", "ₓ": "x", "ₕ": "h", "ₖ": "k", "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₚ": "p", "ₛ": "s", "ₜ": "t", "ᵢ": "i",
                       "ⱼ": "j", "ᵣ": "r"}
_SUB_SYMBOLS = {"∥": "par", "⊥": "perp", "½": "half", "∞": "inf", "⊙": "sun"}
_PRIMES = {"′": 1, "″": 2, "‴": 3}
_BOOL_WORDS = {"AND": "∧", "OR": "∨", "NOT": "¬", "XOR": "⊕", "NAND": "NAND", "NOR": "NOR"}
#: one-character punctuation tokens
_SIMPLE = {",": "COMMA", ";": "SEMI", ":": "COLON", "%": "PERCENT", "°": "DEGREE", "|": "BAR", "!": "BANG", "&": "AMP", "?": "PUNCT", "…": "PUNCT",
           ".": "PUNCT"}
#: the characters a subscript may open with (``_subscript_text`` reads nothing at any other character)
_SUB_START = frozenset(SUBSCRIPT_DIGITS) | frozenset(_SUBSCRIPT_LETTERS) | frozenset(_SUB_SYMBOLS) | {"_"}
_MAX_COMMAND = 24
_MAX_SUB = 16
_MAX_TEXT = 400


def _is_latin(ch: str) -> bool:
    return "a" <= ch <= "z" or "A" <= ch <= "Z"


def _is_greek(ch: str) -> bool:
    return ch in GREEK


def _subscript_text(s: str, i: int, n: int, mode: LexMode) -> tuple[int, str]:
    """A subscript right after a letter: ``₀₁``, ``ₖ``, ``_0``, ``_{max}``, ``_net``, ``∥``, ``½``,
    or 1–2 ASCII digits glued to a single letter (``Q1``). Returns ``(end, text)``."""
    if i >= n:
        return i, ""
    ch = s[i]
    if ch in SUBSCRIPT_DIGITS or ch in _SUBSCRIPT_LETTERS:
        j = i
        out = []
        while j < n and (s[j] in SUBSCRIPT_DIGITS or s[j] in _SUBSCRIPT_LETTERS) and j - i < _MAX_SUB:
            out.append(SUBSCRIPT_DIGITS.get(s[j]) or _SUBSCRIPT_LETTERS[s[j]])
            j += 1
        return j, "".join(out)
    if ch in _SUB_SYMBOLS:
        return i + 1, _SUB_SYMBOLS[ch]
    if ch == "_":
        j = i + 1
        if j < n and s[j] == "{":
            k = j + 1
            depth = 1
            while k < n and k - j <= _MAX_SUB * 2:
                if s[k] == "{":
                    depth += 1
                elif s[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            if k < n and s[k] == "}" and depth == 0:
                inner = s[j + 1:k]
                clean = "".join(c for c in inner if c.isalnum() or c in "/,") or ""
                if clean and all(c.isascii() for c in clean):
                    return k + 1, clean
                if inner.startswith("\\text{") or inner.startswith("\\mathrm{"):
                    body = inner[inner.index("{") + 1:].rstrip("}")
                    body = "".join(c for c in body if c.isalnum())
                    if body:
                        return k + 1, body
            return i, ""
        if mode == "latex":
            if j < n and (s[j].isascii() and s[j].isalnum()):
                return j + 1, s[j]
            return i, ""
        k = j
        while k < n and s[k].isascii() and s[k].isalnum() and k - j < _MAX_SUB:
            k += 1
        if k > j:
            return k, s[j:k]
        return i, ""
    return i, ""


def lex(s: str, start: int = 0, end: Optional[int] = None, *, mode: LexMode = "plain", orig: Optional[str] = None, cs: bool = False,
        limits: StemLimits = DEFAULT_LIMITS, max_tokens: Optional[int] = None, values: bool = True) -> LexResult:
    """Tokenize ``s[start:end]`` (offsets stay absolute). ``orig`` is the original text (same
    length) for thin-space thousands groups. ``cs`` reads the Boolean words AND OR NOT XOR.
    With ``values`` False numerals carry no value (``NUM`` tokens with ``value`` None): the span
    finder and the name pre-pass need only extents, and building exact values for a whole answer
    would cost a ``Fraction`` per numeral."""
    n = len(s) if end is None else min(end, len(s))
    i = start
    toks: list[Token] = []
    space = False
    bracket_depth = 0
    cap = max_tokens

    append = toks.append

    def emit(kind: str, text: str, a: int, b: int, value: Any = None, sub: str = "", primes: int = 0, delta: bool = False) -> None:
        nonlocal space
        append(Token(kind, text, a, b, space, value, sub, primes, delta))
        space = False

    while i < n:
        ch = s[i]
        # ------------------------------------------------------------- whitespace and LaTeX spacing
        if ch in " \t\r\n ":
            space = True
            i += 1
            continue
        if mode == "latex" and ch == "~":
            space = True
            i += 1
            continue
        if cap is not None and len(toks) >= cap:   # a token remains beyond the cap (trailing space is none)
            return LexResult(tuple(toks), overflow=True)
        if ch in "([)]":
            # brackets first: no other branch below reads them (they are the commonest one-character tokens of a long input)
            if ch in "([":
                bracket_depth += 1
                append(Token("LPAR", ch, i, i + 1, space))
            else:
                bracket_depth = max(0, bracket_depth - 1)
                append(Token("RPAR", ch, i, i + 1, space))
            space = False
            i += 1
            continue
        # ------------------------------------------------------------- LaTeX commands
        if ch == "\\":
            if i + 1 >= n:
                emit("ERROR", "\\", i, i + 1, value="a lone backslash")
                i += 1
                continue
            nxt = s[i + 1]
            if nxt == "\\":
                emit("ROWSEP", "\\\\", i, i + 2)
                i += 2
                continue
            if nxt in ",;:! >":
                space = True
                i += 2
                continue
            if nxt in "{}":
                emit("LPAR" if nxt == "{" else "RPAR", nxt, i, i + 2)
                i += 2
                continue
            if nxt == "%":
                emit("PERCENT", "%", i, i + 2)
                i += 2
                continue
            if nxt in "()[]":
                # \( \) \[ \] delimit LaTeX spans; inside a span they are an error the span finder should have consumed
                emit("ERROR", "\\" + nxt, i, i + 2, value=f"a math delimiter \\{nxt} inside math")
                i += 2
                continue
            if nxt == "|":
                emit("BAR", "|", i, i + 2)
                i += 2
                continue
            if not _is_latin(nxt):
                emit("ERROR", "\\" + nxt, i, i + 2, value=f"unknown LaTeX command \\{nxt}")
                i += 2
                continue
            j = i + 1
            while j < n and _is_latin(s[j]) and j - i <= _MAX_COMMAND:
                j += 1
            name = s[i + 1:j]
            if j < n and _is_latin(s[j]):
                emit("ERROR", "\\" + name, i, j, value="an overlong LaTeX command")
                while j < n and _is_latin(s[j]):
                    j += 1
                i = j
                continue
            cmd_end = j
            if name in ("left", "right"):
                k = cmd_end
                while k < n and s[k] == " ":
                    k += 1
                if k < n and s[k] in "([":
                    emit("LPAR", s[k], i, k + 1)
                    bracket_depth += 1
                    i = k + 1
                elif k < n and s[k] in ")]":
                    emit("RPAR", s[k], i, k + 1)
                    bracket_depth = max(0, bracket_depth - 1)
                    i = k + 1
                elif k < n and s[k] == "|":
                    emit("BAR", "|", i, k + 1)
                    i = k + 1
                elif k < n and s[k] == ".":
                    i = k + 1  # \left. / \right. : an invisible delimiter
                elif k + 1 < n and s[k] == "\\" and s[k + 1] in "{}":
                    emit("LPAR" if s[k + 1] == "{" else "RPAR", s[k + 1], i, k + 2)
                    i = k + 2
                elif s.startswith("\\lvert", k) or s.startswith("\\rvert", k) or s.startswith("\\vert", k):
                    e = k + (6 if s.startswith("\\lvert", k) or s.startswith("\\rvert", k) else 5)
                    emit("BAR", "|", i, e)
                    i = e
                else:
                    emit("ERROR", "\\" + name, i, cmd_end, value=f"\\{name} without a delimiter")
                    i = cmd_end
                continue
            if name in ("lvert", "rvert", "vert"):
                emit("BAR", "|", i, cmd_end)
                i = cmd_end
                continue
            if name in _LATEX_SPACE:
                space = True
                i = cmd_end
                continue
            if name in ("Sigma",):
                emit("UNSUP", "\\Sigma", i, cmd_end, value="a sum (Σ)")
                i = cmd_end
                continue
            if name == "Delta" or name in LATEX_GREEK:
                letter = LATEX_GREEK.get(name, "Δ")
                if letter == "Δ":
                    # \Delta fuses with the letter run that follows (LaTeX needs a space after the command name)
                    k = cmd_end
                    while k < n and s[k] == " " and k - cmd_end < 2:
                        k += 1
                    if k < n and (_is_latin(s[k]) or (s[k] == "\\" and s[k + 1:k + 2].isalpha())):
                        nested = _ident_at(s, k, n, mode, cs)
                        if nested is not None and nested[1].kind == "IDENT":
                            end_k, t = nested
                            emit("IDENT", t.text, i, end_k, sub=t.sub, primes=t.primes, delta=True)
                            i = end_k
                            continue
                sub_end, sub = _subscript_text(s, cmd_end, n, mode)
                primes, p_end = _primes_at(s, sub_end, n)
                emit("IDENT", letter, i, p_end, sub=sub, primes=primes)
                i = p_end
                continue
            if name in _LATEX_REL:
                emit("REL", _LATEX_REL[name], i, cmd_end)
                i = cmd_end
                continue
            if name in _LATEX_OP:
                emit("OP", _LATEX_OP[name], i, cmd_end)
                i = cmd_end
                continue
            if name in _LATEX_BOOL:
                emit("BOOL", _LATEX_BOOL[name], i, cmd_end)
                i = cmd_end
                continue
            if name in _LATEX_FUNC:
                func = _LATEX_FUNC[name]
                k, base = _log_base(s, cmd_end, n, mode) if func == "log" else (cmd_end, None)
                k, func = _inverse(s, k, n, func, mode)
                emit("FUNC", func, i, k, value=base)
                i = k
                continue
            if name in _LATEX_STRUCT:
                emit("LATEX", _LATEX_STRUCT[name], i, cmd_end)
                i = cmd_end
                continue
            if name in _LATEX_TEXT:
                k = cmd_end
                while k < n and s[k] == " ":
                    k += 1
                if k < n and s[k] == "{":
                    close = _brace_close(s, k, n, _MAX_TEXT)
                    if close is None:
                        emit("ERROR", "\\" + name, i, cmd_end, value=f"\\{name} with an unbalanced group")
                        i = cmd_end
                        continue
                    emit("TEXT", s[k + 1:close], i, close + 1, value=(k + 1, close))
                    i = close + 1
                    continue
                emit("ERROR", "\\" + name, i, cmd_end, value=f"\\{name} without a group")
                i = cmd_end
                continue
            if name == "infty":
                emit("INF", "∞", i, cmd_end)
                i = cmd_end
                continue
            if name == "circ" and toks and toks[-1].kind == "CARET":
                toks.pop()
                emit("DEGREE", "°", i, cmd_end)
                i = cmd_end
                continue
            if name == "degree":
                emit("DEGREE", "°", i, cmd_end)
                i = cmd_end
                continue
            if name in ("begin", "end"):
                close = _brace_close(s, cmd_end, n, 40) if cmd_end < n and s[cmd_end] == "{" else None
                env = s[cmd_end + 1:close] if close is not None else ""
                stop = (close + 1) if close is not None else cmd_end
                if env.endswith("matrix") or env in ("array", "cases"):
                    emit("UNSUP", "\\" + name + "{" + env + "}", i, stop, value="a matrix or array" if env != "cases" else "a piecewise definition")
                else:
                    emit("ERROR", "\\" + name, i, stop, value=f"an environment \\{name}{{{env}}} inside math")
                i = stop
                continue
            if name in ("pi",):
                emit("IDENT", "π", i, cmd_end)
                i = cmd_end
                continue
            if name in _LATEX_UNSUP:
                emit("UNSUP", "\\" + name, i, cmd_end, value=_LATEX_UNSUP[name])
                i = cmd_end
                continue
            if name in ("checkmark",):
                emit("OTHER", "✓", i, cmd_end)
                i = cmd_end
                continue
            if name == "boxed":
                space = True  # \boxed{x}: the group that follows is read as a group
                i = cmd_end
                continue
            if name in ("label", "tag", "hspace", "vspace"):
                close = _brace_close(s, cmd_end, n, 80) if cmd_end < n and s[cmd_end] == "{" else None
                i = (close + 1) if close is not None else cmd_end
                space = True
                continue
            if name == "overline" or name == "bar":
                emit("UNSUP", "\\" + name, i, cmd_end, value="an overline (a mean, a recurring decimal or a negation)")
                i = cmd_end
                continue
            emit("ERROR", "\\" + name, i, cmd_end, value=f"unknown LaTeX command \\{name}")
            i = cmd_end
            continue
        # ------------------------------------------------------------- numbers (based numerals first)
        digit = "0" <= ch <= "9"
        if digit or (cs and ch in "abcdefABCDEF" and _based_ahead(s, i, n)) or (ch == "." and i + 1 < n and "0" <= s[i + 1] <= "9" and not (toks and toks[-1].kind == "NUM" and not space)):
            if mode == "latex" and digit and toks and toks[-1].kind == "CARET":
                # TeX: '^23' raises only the first digit
                emit("NUM", ch, i, i + 1, value=_digit(ch) if values else None)
                i += 1
                continue
            based = None
            if ch != "." and ((ch == "0" and s.startswith(("0x", "0b", "0o", "0X", "0B", "0O"), i)) or not digit or _base_mark_after_digits(s, i, n)
                              or (cs and _based_ahead(s, i, n))):  # '2A₁₆': a hexadecimal numeral may open with a decimal digit
                based = scan_based(s, i, limits=limits)
            if based is not None:
                k, num, _digits = based
                emit("NUM", s[i:k], i, k, value=num)
                i = k
                continue
            if not digit and ch != ".":
                pass  # a hex letter that is no based numeral: read as a letter below
            else:
                scan = scan_number(s, i, limits=limits, orig=orig, decimal_comma=bracket_depth == 0 and mode == "plain",
                                   thousands_comma=bracket_depth == 0 or _thousands_operand(s, i, n), build=values)
                if scan is not None:
                    if scan.number is None and (values or scan.error):
                        emit("NUMERR", s[i:scan.end], i, scan.end, value=(scan.code or "ST-LIM-001", scan.error))
                        # swallow the rest of an over-long digit run so it cannot re-enter as more numerals
                        k = scan.end
                        while k < n and (is_ascii_digit(s[k]) or (s[k] == "." and k + 1 < n and is_ascii_digit(s[k + 1]))):
                            k += 1
                        i = k
                    else:
                        emit("NUM", s[i:scan.end], i, scan.end, value=scan.number)
                        i = scan.end
                    continue
        if ch in VULGAR_FRACTIONS:
            emit("NUM", ch, i, i + 1, value=exact_vulgar(ch))
            i += 1
            continue
        # ------------------------------------------------------------- letters
        if ch == "Σ":
            emit("UNSUP", ch, i, i + 1, value="a sum (Σ)")
            i += 1
            continue
        if "a" <= ch <= "z" or "A" <= ch <= "Z" or ch in GREEK or ch == "Δ":
            res = _ident_at(s, i, n, mode, cs)
            if res is None:
                emit("OTHER", ch, i, i + 1)
                i += 1
                continue
            k, t = res   # t spans [i, k) and carries no preceding space: reuse it unless a space precedes
            append(t if not space else Token(t.kind, t.text, i, k, True, t.value, t.sub, t.primes, t.delta))
            space = False
            i = k
            continue
        # ------------------------------------------------------------- operators and relations
        two = s[i:i + 2] if ch in "<>!=-*" else ""   # every two- and three-character operator opens with one of these
        if ch == "<" and s.startswith(("<=>", "<->"), i):
            emit("REL", "⇔", i, i + 3)
            i += 3
            continue
        if two in ("<=", ">=", "!=", "=>", "->", "==", "**"):
            if two == "**":
                emit("DSTAR", "**", i, i + 2)
            else:
                emit("REL", {"<=": "≤", ">=": "≥", "!=": "≠", "=>": "⇒", "->": "→", "==": "="}[two], i, i + 2)
            i += 2
            continue
        if ch in _PLAIN_REL:
            emit("REL", _PLAIN_REL[ch], i, i + 1)
            i += 1
            continue
        if ch == "~":
            emit("REL", "≈", i, i + 1)
            i += 1
            continue
        if ch in _PLAIN_OP:
            emit("OP", _PLAIN_OP[ch], i, i + 1)
            i += 1
            continue
        if ch in _PLAIN_BOOL:
            emit("BOOL", ch, i, i + 1)
            i += 1
            continue
        if ch in "([":
            bracket_depth += 1
            emit("LPAR", ch, i, i + 1)
            i += 1
            continue
        if ch in ")]":
            bracket_depth = max(0, bracket_depth - 1)
            emit("RPAR", ch, i, i + 1)
            i += 1
            continue
        if ch == "{":
            bracket_depth += 1
            emit("LGROUP" if mode == "latex" else "LPAR", "{", i, i + 1)
            i += 1
            continue
        if ch == "}":
            bracket_depth = max(0, bracket_depth - 1)
            emit("RGROUP" if mode == "latex" else "RPAR", "}", i, i + 1)
            i += 1
            continue
        if ch == "^":
            if s.startswith("^\\circ", i) or s.startswith("^{\\circ}", i):
                k = i + (6 if s.startswith("^\\circ", i) else 8)
                emit("DEGREE", "°", i, k)
                i = k
                continue
            emit("CARET", "^", i, i + 1)
            i += 1
            continue
        if ch in SUPERSCRIPT_DIGITS or ch in SUPERSCRIPT_SIGNS:
            k, digits = superscript_int(s, i, n)
            if digits is None:
                emit("SUP", ch, i, i + 1, value=None)
                i += 1
            else:
                emit("SUP", s[i:k], i, k, value=int(digits))
                i = k
            continue
        if ch in SUBSCRIPT_DIGITS:
            k = i
            while k < n and s[k] in SUBSCRIPT_DIGITS and k - i < _MAX_SUB:
                k += 1
            emit("SUB", "".join(SUBSCRIPT_DIGITS[c] for c in s[i:k]), i, k, value="".join(SUBSCRIPT_DIGITS[c] for c in s[i:k]))
            i = k
            continue
        if ch == "_":
            k, sub = _subscript_text(s, i, n, mode)
            if k > i:
                emit("SUB", sub, i, k, value=sub)
                i = k
            else:
                emit("OTHER", "_", i, i + 1)
                i += 1
            continue
        if ch in _SIMPLE:
            kind = _SIMPLE[ch]
            if ch == "°" and i + 1 < n and s[i + 1] in "CF" and not (i + 2 < n and _is_latin(s[i + 2])):
                emit("DEGREE", "°" + s[i + 1], i, i + 2)
                i += 2
                continue
            emit(kind, ch, i, i + 1)
            i += 1
            continue
        if ch in _PRIMES or ch == "'":
            k = i
            while k < n and (s[k] in _PRIMES or s[k] == "'") and k - i < 4:
                k += 1
            emit("PRIME", s[i:k], i, k, value=sum(_PRIMES.get(c, 1) for c in s[i:k]))
            i = k
            continue
        if ch in _QUOTES:
            emit("QUOTE", ch, i, i + 1)
            i += 1
            continue
        if ch == "√":
            emit("FUNC", "sqrt", i, i + 1)
            i += 1
            continue
        if ch == "∛":
            emit("FUNC", "cbrt", i, i + 1)
            i += 1
            continue
        if ch == "∞":
            emit("INF", "∞", i, i + 1)
            i += 1
            continue
        if ch in _UNSUP_CHARS:
            emit("UNSUP", ch, i, i + 1, value=_UNSUP_CHARS[ch])
            i += 1
            continue
        if ch == "Σ":
            emit("UNSUP", ch, i, i + 1, value="a sum (Σ)")
            i += 1
            continue
        if ch.isalpha():
            # a letter of another script, or a mathematical alphanumeric symbol: never read as a Latin letter
            k = i + 1
            while k < n and s[k].isalpha() and not _is_latin(s[k]) and not _is_greek(s[k]) and k - i < 32:
                k += 1
            emit("ERROR", s[i:k], i, k, value=f"letters outside the Latin and Greek alphabets ({s[i:k][:8]!r})")
            i = k
            continue
        emit("OTHER", ch, i, i + 1)
        i += 1
    return LexResult(tuple(toks), overflow=False)


#: what stands beside an operand of an arithmetic expression: an operator or a relation sign
_EXPRESSION_SIGNS = frozenset("×÷*/+-−·=≈<>≤≥^")


def _thousands_operand(s: str, i: int, n: int) -> bool:
    """Inside brackets, ``1,000`` is one numeral with a thousands group when it is an operand of an arithmetic expression:
    an operator or a relation sign follows it or precedes it (``(1,000 ÷ 2^10 = 0.98)``, ``(2 × 1,000)``). A list or a
    pair (``[100,200]``, ``(1,000)``, ``(3,000, 4,000)``) stays separate numbers. Looks at most 40 characters ahead and 8
    back (a bound on the work per numeral)."""
    k, end = i, min(n, i + 40)
    while k < end and "0" <= s[k] <= "9":
        k += 1
    if not 1 <= k - i <= 3 or s[i] == "0":
        return False
    groups = 0
    while k + 3 < end and s[k] == "," and all("0" <= s[k + j] <= "9" for j in (1, 2, 3)) and not (k + 4 < n and "0" <= s[k + 4] <= "9"):
        groups += 1
        k += 4
    if not groups or (k < n and s[k] == ","):
        return False
    if k + 1 < end and s[k] == "." and "0" <= s[k + 1] <= "9":  # '1,000.5'
        k += 1
        while k < end and "0" <= s[k] <= "9":
            k += 1
    after = k
    while after < end and s[after] in " \t":
        after += 1
    before = i - 1
    while before >= max(0, i - 8) and s[before] in " \t":
        before -= 1
    return (after < n and s[after] in _EXPRESSION_SIGNS) or (before >= 0 and s[before] in _EXPRESSION_SIGNS)


def _digit(ch: str):
    return exact_integer(int(ch))


def _base_mark_after_digits(s: str, i: int, n: int) -> bool:
    """A base subscript right after a run of decimal digits (``1010₂``, ``377_8``): cheap, so only then is a based numeral read."""
    k = i
    while k < n and "0" <= s[k] <= "9" and k - i < 66:
        k += 1
    return k < n and (s[k] in "₂₈₁" or (s[k] == "_" and k + 1 < n and (s[k + 1] in "128" or s[k + 1] == "{")))


def _based_ahead(s: str, i: int, n: int) -> bool:
    """A hexadecimal letter starts a based numeral only when a base subscript follows its digit run (``FF₁₆``)."""
    k = i
    while k < n and s[k] in "0123456789abcdefABCDEF" and k - i < 66:
        k += 1
    return k < n and (s.startswith("₁₆", k) or s.startswith("₂", k) or s.startswith("₈", k) or s.startswith("_16", k) or s.startswith("_{16}", k)
                      or s.startswith("₁₀", k) or s.startswith("_2", k) or s.startswith("_8", k))


def _brace_close(s: str, k: int, n: int, limit: int) -> Optional[int]:
    """Offset of the brace closing the one at ``k`` (within ``limit`` characters), or None."""
    if k >= n or s[k] != "{":
        return None
    depth = 0
    j = k
    while j < n and j - k <= limit:
        c = s[j]
        if c == "\\" and j + 1 < n:
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return None


def _primes_at(s: str, i: int, n: int) -> tuple[int, int]:
    k = i
    count = 0
    while k < n and (s[k] in _PRIMES or s[k] == "'") and k - i < 4:
        count += _PRIMES.get(s[k], 1)
        k += 1
    return count, k


def _log_base(s: str, k: int, n: int, mode: LexMode) -> tuple[int, Optional[int]]:
    """``log₂``, ``log_2``, ``log_{10}``, ``log₁₀``: returns ``(end, base)``."""
    if k < n and s[k] in SUBSCRIPT_DIGITS:
        j = k
        while j < n and s[j] in SUBSCRIPT_DIGITS and j - k < 3:
            j += 1
        digits = "".join(SUBSCRIPT_DIGITS[c] for c in s[k:j])
        return j, int(digits)
    if k < n and s[k] == "_":
        j = k + 1
        if j < n and s[j] == "{":
            e = j + 1
            while e < n and is_ascii_digit(s[e]) and e - j < 4:
                e += 1
            if e > j + 1 and e < n and s[e] == "}":
                return e + 1, int(s[j + 1:e])
            return k, None
        e = j
        limit = 1 if mode == "latex" else 3
        while e < n and is_ascii_digit(s[e]) and e - j < limit:
            e += 1
        if e > j:
            return e, int(s[j:e])
    return k, None


def _inverse(s: str, k: int, n: int, func: str, mode: LexMode) -> tuple[int, str]:
    """``sin⁻¹`` and ``\\sin^{-1}`` are the inverse functions."""
    if func not in _INVERSE:
        return k, func
    if s.startswith("⁻¹", k):
        return k + 2, _INVERSE[func]
    for form in ("^{-1}", "^-1", "^{−1}"):
        if s.startswith(form, k):
            return k + len(form), _INVERSE[func]
    return k, func


def _ident_at(s: str, i: int, n: int, mode: LexMode, cs: bool) -> Optional[tuple[int, Token]]:
    """An identifier, function or Boolean word starting at ``i`` (a Latin or Greek letter or Δ)."""
    ch = s[i]
    delta = False
    j = i
    if ch == "Δ":
        k = i + 1
        if k < n and (_is_latin(s[k]) or (_is_greek(s[k]) and s[k] != "Δ")):
            delta = True
            j = k
        else:
            sub_end, sub = _subscript_text(s, k, n, mode)
            primes, p_end = _primes_at(s, sub_end, n)
            return p_end, Token("IDENT", "Δ", i, p_end, sub=sub, primes=primes)
    if s[j] in GREEK:
        letter = "μ" if s[j] == "µ" else s[j]
        k = j + 1
        sub_end, sub = _subscript_text(s, k, n, mode)
        primes, p_end = _primes_at(s, sub_end, n)
        return p_end, Token("IDENT", letter, i, p_end, sub=sub, primes=primes, delta=delta)
    k = j
    while k < n and ("a" <= s[k] <= "z" or "A" <= s[k] <= "Z") and k - j < 64:
        k += 1
    word = s[j:k]
    if k < n and ("a" <= s[k] <= "z" or "A" <= s[k] <= "Z"):
        # an overlong letter run: one unknown word
        while k < n and _is_latin(s[k]):
            k += 1
        return k, Token("IDENT", s[j:k], i, k, delta=delta)
    if not delta:
        if cs and word in _BOOL_WORDS:
            return k, Token("BOOL", _BOOL_WORDS[word], i, k)
        if word in FUNCTIONS and not (k < n and s[k] == "_" and word not in ("log",)):
            func = FUNCTIONS[word]
            e, base = _log_base(s, k, n, mode) if func == "log" else (k, None)
            e, func = _inverse(s, e, n, func, mode)
            return e, Token("FUNC", func, i, e, value=base)
    sub_end, sub = _subscript_text(s, k, n, mode) if k < n and s[k] in _SUB_START else (k, "")
    if sub_end < n and s[sub_end] == "°" and not (sub_end + 1 < n and s[sub_end + 1] in "CF") and (delta or len(word) == 1):
        # a standard-state mark glued to a symbol (ΔH°, E°, S°) is part of its name, not degrees
        sub = (sub + "°") if sub else "°"
        sub_end += 1
    if not sub and len(word) == 1 and mode == "plain" and k < n and "0" <= s[k] <= "9":
        # 'Q1', 'V2': one or two ASCII digits glued to a single letter, not followed by more digits, a point or a letter
        e = k
        while e < n and "0" <= s[e] <= "9" and e - k < 3:
            e += 1
        if e - k <= 2 and not (e < n and (s[e].isalnum() or (s[e] == "." and e + 1 < n and "0" <= s[e + 1] <= "9"))):
            sub_end, sub = e, s[k:e]
    primes, p_end = _primes_at(s, sub_end, n) if sub_end < n and (s[sub_end] in _PRIMES or s[sub_end] == "'") else (0, sub_end)
    return p_end, Token("IDENT", word, i, p_end, False, None, sub, primes, delta)
