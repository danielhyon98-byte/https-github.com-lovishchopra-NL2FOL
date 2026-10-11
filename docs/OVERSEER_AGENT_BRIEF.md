# Overseer agent brief (superseded)

This file holds no instructions. The overseer agent's whole configuration is the knowledge-document
pack shipped with the package:

`src/epinoic_logic/overseer/knowledge/overseer-knowledge-docs-1.0/`

- `master_prompt.txt` is read first; the numbered documents `01` to `09` follow it in order.
- Every rule of brief 1.0 is carried by the pack; the mapping is in `docs/OVERSEER_DESIGN.md`,
  section 17.3.
- How the pack is versioned, verified, exported and used to configure a model is in
  `docs/OVERSEER_DESIGN.md`, section 17.

Do not add instructions here. A change to what overseer agents are told is a change to the pack,
under a new pack version.
