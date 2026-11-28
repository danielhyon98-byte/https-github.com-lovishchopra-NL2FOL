"""The block-only meaning label for the self-certification class (meaning-check design, decision 1; stage 2a: wired).

A small labeller reads one answer at a time, sentence by sentence, and names any sentence in which the answer certifies its OWN
checking, verification, review, testing, quality or correctness. It can only withhold: its result never releases, selects or
labels an answer, never raises a status and never adds text. The gate it is built for is ``reader OR validated label``: the
rule reader (:mod:`epinoic_logic.selfcert`) stays, and either one can withhold.

What this package does (built in stage 1):

* :func:`build_input` turns the raw answer and the ROUTER's request into the label request: the answer's own sentences with
  ids and places, code-located placeholders, the context block, keyed canaries, content-derived delimiters (:mod:`.scope`,
  :mod:`.canaries`, :mod:`.render`). The same inputs render byte-identical requests.
* :func:`validate_reply` checks a reply deterministically and keeps only offsets and categories (:mod:`.validate`,
  :mod:`.anchor`, :mod:`.exempt`); :mod:`.record` turns attempts into a :class:`LabelResult` with its record, and
  :func:`revalidate` recomputes a stored record from its raw replies.
* :mod:`.labellers`: the unconfigured default, a provider labeller over an injected transport, recorded replies, the cache,
  the call budget and the circuit breaker; :mod:`.fakes`: the faithful reader-backed fake and a scripted fake.

Stage 2a adds what the release paths use: :func:`default_labeller` looked up at use time with its one switch
:func:`set_default_labeller`; shared submission (a module-level in-flight table and cache of successes, so two submissions of
the same answer make one call); :meth:`Labeller.revalidate_record` with the labeller's own key and model digest; bounded work at
the oversized cap; and :func:`check_t24`, the invariant the test suite applies to every receipt it produces.

What it never does: it never calls a provider or opens a connection itself; it never puts label text into the IR, the engine,
a receipt message, a log or a payload; it never treats a failure as ``none_named``. It is not yet called by any release path.
"""
from __future__ import annotations

import hashlib
import pathlib
from typing import Optional

from .render import LABEL_VERSION

__all__ = ["LABEL_VERSION", "label_digest", "covered_files", "build_input", "LabelInput", "validate_reply", "Validation",
           "LabelResult", "LabelSpan", "revalidate", "Revalidation", "FINDING_STATES", "STATES", "KINDS",
           "Labeller", "UnconfiguredLabeller", "CallingLabeller", "ProviderLabeller", "RecordedLabeller", "CachingLabeller",
           "BudgetedLabeller", "CircuitBreakerLabeller", "CallBudget", "CallFailure", "Reply", "default_labeller", "model_digest",
           "set_default_labeller", "restore_default_labeller", "production_default_labeller", "using_default_labeller",
           "LabelHandle", "clear_shared_calls", "shared_calls_state", "check_t24", "T24_EXPECTED_VIOLATION",
           "CATEGORIES", "EXEMPTIONS"]

_HERE = pathlib.Path(__file__).resolve().parent
#: The data files the digest covers, by name (``prompt.md`` is the prompt author's; the rest are this package's).
DATA_FILES = ("prompt.md", "schema.json", "canaries.json", "exemptions.json")


def covered_files(root: Optional[pathlib.Path] = None) -> tuple[str, ...]:
    """The files :func:`label_digest` covers, relative to the package: the data files and every ``.py`` of the package."""
    base = pathlib.Path(root) if root is not None else _HERE
    code = sorted(p.relative_to(base).as_posix() for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    return DATA_FILES + tuple(code)


def label_digest(root: Optional[pathlib.Path] = None) -> str:
    """SHA-256 over :data:`LABEL_VERSION`, ``prompt.md``, ``schema.json``, the canary class data, the exemption frames, every
    ``.py`` of the package and :func:`epinoic_logic.selfcert.rules_digest` (validation calls the reader), each file by name and
    content as stored, in a fixed order. A missing file is hashed as absent, so it changes the digest too."""
    from .. import selfcert
    base = pathlib.Path(root) if root is not None else _HERE
    h = hashlib.sha256()
    h.update(b"selfcert-label-digest/1\0" + LABEL_VERSION.encode())
    for name in covered_files(base):
        p = base / name
        h.update(b"\0file\0" + name.encode() + b"\0")
        try:
            data = p.read_bytes()
        except OSError:
            h.update(b"\0absent")
            continue
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    h.update(b"\0rules\0" + selfcert.rules_digest().encode())
    return h.hexdigest()


from .exempt import EXEMPTIONS  # noqa: E402
from .inputs import LabelInput, build_input  # noqa: E402
from .labellers import (BudgetedLabeller, CachingLabeller, CallBudget, CallFailure, CallingLabeller,  # noqa: E402
                        CircuitBreakerLabeller, LabelHandle, Labeller, ProviderLabeller, RecordedLabeller, Reply,
                        UnconfiguredLabeller, clear_shared_calls, default_labeller, model_digest, production_default_labeller,
                        restore_default_labeller, set_default_labeller, shared_calls_state, using_default_labeller)
from .record import FINDING_STATES, KINDS, STATES, LabelResult, LabelSpan, Revalidation, revalidate  # noqa: E402
from .validate import CATEGORIES, Validation, validate_reply  # noqa: E402
from .t24 import T24_EXPECTED_VIOLATION, check_t24  # noqa: E402
