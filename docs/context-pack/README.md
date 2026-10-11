# Epinoic AI — Claude Code Context Pack

This bundle packages the project context and the specifications developed for Claude Code to continue work on Epinoic AI.

## Quick start

1. Extract this directory into or alongside your Epinoic AI repository. Do not overwrite your actual application files.
2. Open the repository in Claude Code.
3. Use the configured model you intend to code with. If model selection is uncertain, verify the model actually selected in Claude Code rather than relying on this pack to select it.
4. Open `01_CLAUDE_CODE_START_HERE.md` and paste its content as the first instruction.
5. Ask Claude Code to read `00_PROJECT_CONTEXT_AND_ARCHITECTURE.md`, `specifications/02_Z3_Logic_Verification_Engine_Specification.md`, and `specifications/03_Overseer_Agent_Specification.md` in full before it presents the audit.
6. Review the audit and phased implementation plan before allowing substantial changes.

## Contents

- `00_PROJECT_CONTEXT_AND_ARCHITECTURE.md` — project vision, design decisions, intended architecture, known constraints, scaling principles, commercial context, and implementation order.
- `01_CLAUDE_CODE_START_HERE.md` — copy-and-paste kickoff prompt.
- `specifications/02_Z3_Logic_Verification_Engine_Specification.md` — detailed requirements for the restricted logic translator and Z3 verification service.
- `specifications/03_Overseer_Agent_Specification.md` — detailed requirements for the independent Overseer.
- `specifications/04_Claude_Code_Implementation_Kickoff.md` — the general implementation kickoff prompt created for Claude Code.
- `references/ib-agent-training-pack-v2/` — extracted reference copy of the IB agent training pack, including its subject guides, shared instructions, coverage matrix, README, and audit report.
- `references/IB_Agent_Training_Pack_v2.zip` — original archive preserved unchanged.

## Important notes

The original Z3 file is named as a Codex specification, but its technical requirements are intended to be model-independent and should be followed by Claude Code. The other prompts should be read as supporting implementation instructions, not as a reason to duplicate or conflict with the master architecture.

The context pack summarizes decisions made in the conversation; it is not a verbatim transcript. The actual repository is authoritative for current implementation status. Claude Code must inspect code and tests before asserting that any component already exists or works.

The IB agent training pack is a partial knowledge base, not a complete official IB curriculum. Its own coverage/audit files identify missing curriculum content, unconfirmed facts, provisional working rubrics, and syllabus-version cautions. Do not instruct agents to invent missing official assessment details.

## Recommended priority

1. Audit the actual repository.
2. Establish schemas, provenance, and interfaces.
3. Implement and test the restricted Z3 path.
4. Integrate the Overseer and combinator.
5. Connect the service end to end to the Cloudflare-hosted backend.
6. Apply latency, security, load, and operational hardening based on test results.
