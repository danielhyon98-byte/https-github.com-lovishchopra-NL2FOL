"""Integration gate 2, the class sweep at the service and command-line boundary (service/, cli.py): each endpoint that
reads a body, and the CLI's verify command, is fed the standard hostile inputs (``tests/core_hostile.py``) as the body or
the problem file, and hostile JSON (deep and unclosed nesting), under a CPU-time bound per call. Each is answered with a
refusal or a result in bounded time and never a server error. No instance of the class was found here: the body-size limit
bounds every request and the payload is parsed with a bounded strict parser before anything runs.
"""
from __future__ import annotations

import json

from epinoic_logic import cli

from ..core_hostile import N, sweep
from .conftest import AUTH, make_client, make_settings

_ENDPOINTS = ("/v1/verify", "/v1/results/verify-signature", "/v1/results/release-check", "/v1/outcomes")


def test_sweep_service_endpoints():
    client = make_client(make_settings(rate_per_minute=100_000))  # every request reaches the parser, none is rate-limited
    statuses: list[int] = []

    def entries(text: str):
        for path in _ENDPOINTS:
            yield f"POST {path} (raw)", lambda path=path: statuses.append(client.post(path, content=text.encode("utf-8", "surrogatepass"), headers={**AUTH, "Content-Type": "application/json"}).status_code)
            yield f"POST {path} (problem)", lambda path=path: statuses.append(client.post(path, json={"problem": text[:4_000]}, headers=AUTH).status_code)
    assert not sweep(entries)
    assert statuses and all(code < 500 and code != 429 for code in statuses), sorted(set(statuses))


def test_hostile_json_bodies_are_refused_without_a_server_error():
    client = make_client(make_settings(rate_per_minute=100_000))
    for body in ("[" * N + "]" * N, '{"problem":' * N + "1" + "}" * N, "[" * N, json.dumps({"problem": {"notes": "(" * N}})):
        for path in _ENDPOINTS:
            response = client.post(path, content=body.encode(), headers={**AUTH, "Content-Type": "application/json"})
            assert response.status_code < 500, (path, response.status_code)


def test_sweep_cli_verify(tmp_path, capsys):
    problem = tmp_path / "problem.json"

    def entries(text: str):
        def run():
            problem.write_text(text, encoding="utf-8", errors="surrogatepass")
            code = cli.main(["verify", str(problem)])
            capsys.readouterr()
            assert code == 0  # the CLI exits 0 for every status and prints the result (a refusal is a result)
        yield "epinoic-logic verify FILE", run
    assert not sweep(entries)
