# Overseer agent brief (superseded)

> Moved into the overseer sub-project (`overseer/docs/`, architecture step 2 of phase 2). Paths in this document
> are as they were when each part was written: `src/epinoic_logic/overseer/` is now `overseer/src/epinoic_overseer/`
> (module `epinoic_overseer`), `tests/overseer/` is `overseer/tests/overseer_tests/`, `scripts/overseer/` is
> `overseer/scripts/`, and `docs/<name>` of an overseer document is `overseer/docs/<name>`.

This file holds no instructions. The overseer agent's whole configuration is the knowledge-document
pack shipped with the package:

`src/epinoic_logic/overseer/knowledge/overseer-knowledge-docs-1.1/` (the installed version; 1.0 stays beside it, pinned)

- `master_prompt.txt` is read first; the numbered documents `01` to `09` follow it in order.
- Every rule of brief 1.0 is carried by the pack; the mapping is in `docs/OVERSEER_DESIGN.md`,
  section 17.3.
- How the pack is versioned, verified, exported and used to configure a model is in
  `docs/OVERSEER_DESIGN.md`, section 17.

Do not add instructions here. A change to what overseer agents are told is a change to the pack,
under a new pack version.
