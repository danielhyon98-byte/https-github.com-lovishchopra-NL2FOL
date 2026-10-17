"""What the service attaches: ``hello()`` and ``combine(input_json)``.

* the hello is in contract, stable for a release, and names this release, its pack, the contract digest, the cheapest
  tier and the closed vocabulary;
* ``combine`` returns the runner's text: an output in contract, or a refusal (no provider: ``provider_unavailable``).
"""
from __future__ import annotations

import json

from combinator_helpers import input_doc
from epinoic_combinator import NAME, __version__, port
from epinoic_combinator.contract import load_contract
from epinoic_combinator.jsonio import canonical_json
from epinoic_combinator.pack import load_pack
from epinoic_combinator.providers import FaithfulFakeProvider
from epinoic_combinator.runner import run

CONTRACT = load_contract()


def test_the_hello_is_in_contract_and_names_this_release():
    text = port.hello()
    hello = json.loads(text)
    assert CONTRACT.check_hello(hello) is None and text == canonical_json(hello) == port.hello()
    assert hello["combinator"] == {"name": NAME, "version": __version__} and hello["instruction_pack"] == load_pack().identity()
    assert hello["contract_sha256"] == CONTRACT.sha256 and hello["tier"] == "cheapest" and hello["vocabulary"] == list(CONTRACT.transformations)


def test_combine_returns_the_runners_text():
    doc = input_doc()
    assert port.combine(json.dumps(doc), FaithfulFakeProvider()) == run(doc, FaithfulFakeProvider()).text
    refusal = json.loads(port.combine(json.dumps(doc)))
    assert (refusal["code"], refusal["reason"]) == ("KIT-CB-002", "provider_unavailable") and CONTRACT.check_refusal(refusal, doc) is None
