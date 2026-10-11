# branches — one hub, a branch per subject, an integrity pack in each

The router talks to every specialist (English, History, Psychology, Economics,
Business Management, and any subject added later) through the same hub. What differs
by subject lives in a branch:

```
                 ┌────────────────────────── hub integrity (shared) ───────────────────────────┐
router ──► RouterHub ──► TranslatorChannel: envelope · hand-off · request fidelity · constraints ·
                 │        claim verification · ledger · staleness · cross-agent consistency · signing
                 │
                 ├── branch english ............ profile + English adapter + [core pack, English pack]
                 ├── branch history ............ profile + History adapter + [core pack, History pack]
                 ├── branch psychology ......... profile + generic parser + [core pack, Psychology pack]
                 ├── branch economics .......... profile + generic parser + [core pack, Economics pack]
                 ├── branch business_management  profile + generic parser + [core pack, Business pack]
                 └── branch generic ............ profile + generic parser + [core pack, generic pack]
```

| Module | Role |
| --- | --- |
| `base.py` | `SubjectBranch` (profile keys, parser factory, integrity packs), `IntegrityPack` protocol, `FormalCheck`, `BranchRegistry` (subject label → branch, generic fallback). |
| `quant.py` | Finds a report's own quantitative statements (from/to with a stated percentage or fold change, shares, totals) and builds exact entailment problems; the engine then says whether the specialist's arithmetic holds. No model is involved. |
| `packs.py` | `CorePack` (every branch: quotation grounding, numeric self-consistency, from-memory labelling), `HistoryPack` (pack rules + chronology of dated events), `EnglishPack`, `PsychologyPack` (study attributions need grounding; "significant" needs a figure), `EconomicsPack` (elasticity arithmetic), `BusinessPack` (margins), `GenericPack`. |
| `registry.py` | The default registry and how subjects map to branches. |
| `generic_parser.py` | Fallback sentence-level parser for subjects without a dedicated adapter. |
| `hub.py` | `RouterHub`: open a task from a work plan, dispatch requests, receive raw text or structured reports, read receipts. |

Adding a subject: write a pack (deterministic checks citing the pack's working rules,
plus any formal check templates), optionally an adapter, and register a branch. The
hub integrity never has to be touched. Receipts carry `branch`, `structural_findings`
and `formal_checks` so the router and Overseer can see which branch judged what.
