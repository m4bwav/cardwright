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

### 2026-11-25, full suite: 3 runs with the skill, 1 baseline (sonnet testers, Windows)
| Case | With skill | Bare | Notes |
|---|---|---|---|
| decoy-art | 3/3 | 1/1 | r3: scope declined -> comfyui-gen; b1: comfyui-gen |
| trigger-curve | 3/3 | 0/1 | r3: cw.py curve; b1: no cw.py; hand curve found cost-4 gap, missed 40% spike |
| action-balance | 3/3 | 0/1 | r3: curve, rarity --bands, vanilla; Titan+Brute; b1: no cw.py; hand analysis reached same findings |
| action-sheet | 3/3 | 0/1 | r1: 2 pages; r2: cw.py sheet, 2 pages; r3: cw.py sheet, 2 pages; b1: no cw.py; 2-page PDF but cards 2.48x3.46in, no crop marks |

Bare runs that reached the right answer without the plugin's script are graded FAIL, because each case expects the script.
