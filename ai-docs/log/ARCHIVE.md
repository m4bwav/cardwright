# Log

Append-only. One line per operation: `## [YYYY-MM-DD] op | title` where op is one of add, update, supersede, verify, verify-failed, prune, handoff, index. Newest at the bottom. Never edited, only appended; this is the history the entries themselves do not carry.

## [2026-11-25] init | scaffolded
## [2026-11-25] build | first version: cw.py, hub skill
- 2026-11-25: licence check. Only claim is MIT for own code (LICENSE matches); no ORC, SRD, OGL or third-party game content bundled, nothing to attribute.
## [2026-11-26] build | 0.2.0: dupes, vanilla --by-rarity, rules, sheet --backs, manifest (Kobold Guide to Board Game Design)
## [2026-11-26] build | 0.3.0: baseline greedy bot, matchup ledger, starter lint, sheet --duplex (Kobold Guide to Board Game Design p. 87-94)
- baseline race is deliberately crude (no blocking, abilities ignored): a floor every deck must clear, not a balance proof.
