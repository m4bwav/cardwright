# Tests

Unit tests: `python -m pytest -q` (cw.py, made-up cards and solid-colour images).

Skill evals: [evals/evals.json](evals/evals.json), four cases (one trigger, one decoy, two actions). Run with evergreen-test: three runs with the skill and a no-skill baseline.

## Runs

### 2026-11-25, one run per case, sonnet testers, Windows
| Case | With skill | Bare |
|---|---|---|
| action-balance | pass: curve, rarity --bands, vanilla; gap, Brute, Titan | pass by hand (own script) |
| action-sheet | pass after retry: `--bleed 3` did not fit Letter (fixed in 0.1.0: bleed cut off, cards at trim) | pass, 2 pages, no crop marks |
| trigger-curve, decoy-art | not run | not run |

Baseline is strong on one-off scripts; the skill adds crop marks, the art-consistency check and repeatable commands. Owed: three runs per case and the trigger cases.
