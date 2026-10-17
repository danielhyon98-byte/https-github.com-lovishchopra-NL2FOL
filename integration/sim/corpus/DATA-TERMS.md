# Data terms of the simulation corpus

`corpus/synthetic/` holds only text written for the kit: every question starts with `SYNTHETIC:`, every answer is an
invented short answer, and every translation fixture is a hand-written encoding labelled `SYNTHETIC` in its reading.
There is no student text, no recorded model output and no content of any recorded arena round. It may be published
with the kit.

`corpus/licensed/` does not exist in this kit. A subset of the recorded rounds may be added only if Daniel approves the
data terms (decision D15); it would be re-keyed at kit build and listed here with its source and terms. Until then
the gates that need it are NOT RUN (see `integration/sim/README.md`).

The corpus is regenerated, never edited by hand: `python integration/tools/build_corpus.py` writes it and
`--check` fails on any difference; `corpus/MANIFEST.sha256` lists the SHA-256 of every corpus file.
