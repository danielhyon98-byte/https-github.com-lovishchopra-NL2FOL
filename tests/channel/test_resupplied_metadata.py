"""A report may carry the request's supplied texts only as the router sent them, metadata included (repair round 1,
re-run review security-3 variant): the same text under another author, title, locator scheme or provenance is another
record, which would replace the router's and mislead the quotation credits that read the title and author. It is
INT-REQ-002 (blocking), as another text under the same document id is. Control: the request's own record is delivered."""
from __future__ import annotations

import pytest

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus

from . import test_channel as C

TEXT = C.EXTRACT[:60]
CLAIMS = [dict(claim_id="en-point", claim_text=TEXT, claim_role="point")]


def _respond(docs):
    ch = TranslatorChannel(C.plan(), signing_key=C.KEY)
    msg, req, _ = ch.request("router", "english-specialist", "Analyse how the writer presents justice. Use quotations.", [C.DOC])
    reply, rc = ch.respond(msg.message_id, C.english_report(TEXT, CLAIMS, docs=docs))
    return req, reply, rc


@pytest.mark.parametrize("change, field", [({"author": "Someone Else"}, "author"), ({"title": "Another title"}, "title"),
                                           ({"provenance": "typed by the specialist"}, "provenance"), ({"locator_scheme": "line"}, "locator_scheme"),
                                           ({"author": None}, "author")])
def test_the_requests_text_under_other_metadata_is_refused(change, field):
    _req, reply, rc = _respond((C.DOC.model_copy(update=change),))
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    [f] = [f for f in rc.findings if f.code == "INT-REQ-002"]
    assert f.severity == "error" and f.document_ids == ["doc-cdf"] and field in f.message and "metadata" in f.message


def test_clean_control_the_requests_own_record_is_delivered_with_its_metadata():
    req, reply, rc = _respond((C.DOC,))
    assert reply is not None and "INT-REQ-002" not in {f.code for f in rc.findings}
    assert [(t["author"], t["title"]) for t in reply.payload["supplied_texts"]] == [(t.author, t.title) for t in req.supplied_texts]
