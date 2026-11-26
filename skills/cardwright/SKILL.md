---
name: cardwright
description: "Use to check a card game set as a whole: cost curve gaps and spikes, rarity mix against target bands, vanilla-test stat outliers, art that does not match the rest of the set, and print-and-play sheets (poker 63x88 mm, 3x3 per Letter or A4, crop marks); cw.py runs each check. Use on 'check my cost curve', 'is my rarity split right', 'which cards are overcosted', 'does this card art fit the set', 'make print and play sheets'. Not for writing one card's rules (the project's own kit) or generating art (comfyui-gen)."
---

# cardwright

The set-level layer for card games: is the set balanced, does its art hang together, can it be printed. Engine- and game-agnostic: it reads a card list and a folder of images.

Run as `python "${CLAUDE_PLUGIN_ROOT}/scripts/cw.py" <command>`. Card list: CSV or JSON with `name, cost, rarity, attack, health, art` (remap with `--map cost=mana,attack=power`). If the project stores cards elsewhere (engine assets, text docs), export a CSV first and keep the export script in that project.

## Balance

1. `cw.py curve cards.csv` draws the cost curve and flags gaps and any cost holding over 35% of the set. Deckbuilders usually want most cards cheap; say what the curve means for the first turns.
2. `cw.py rarity cards.csv --bands '{"common":0.6,"uncommon":0.3,"rare":0.1}'` compares the mix with the project's targets (default: Slay the Spire's 60/37/3 for normal rewards). Ask for the project's own bands if unknown.
3. `cw.py vanilla cards.csv --per-cost 2 --base 1` flags units whose attack plus health is far from the cost line. A smell test: read each flagged card's text before calling it broken, since abilities are upside the numbers cannot see. Fit `--per-cost` to the set's own median first.
4. `cw.py vanilla cards.csv --by-rarity` prints the mean stat surplus per rarity and flags a tier more than 1.0 above common. Rarity is not a power budget: assume top players own every card.
5. `cw.py dupes cards.csv` warns on exact twins (merge or differentiate) and strictly better cards at the same cost (sometimes deliberate; ask).
6. Report the flags with a suggested fix each (cost +1, stat -1, move to uncommon). Hand changes to the project's card tool; never edit engine assets from here without the person's yes.

Method notes and sources: [references/balance.md](references/balance.md).

## Rules text and prototype

- `cw.py rules rules.md --glossary terms.txt` lints rules text: other names for a glossary term (lines `term: alias1, alias2`), sentences over 40 words (`--max-words`), ambiguous phrases (cardwright's own list: "in order to", "and/or", "may not", "up to", "should"...), and with `--max-grade 8` a Flesch-Kincaid cap. Use the grade cap on rulebook paragraphs only; short card text gives noisy grades.
- `cw.py manifest cards.csv --players 5 --rules rules.md` checks the box for the top player count. Columns: `per_player` (copies each player needs), `base` (copies needed at any count, default 0), `copies` (copies in the box, default 1). Needed = base + per_player x players. With `--rules` it also lists cards the rules never name (plural `s`/`es` counts).

## Art consistency

`cw.py consistency <art folder>` measures brightness, contrast and saturation per card and flags cards more than 2 standard deviations off the set. Then look at the flagged cards beside three typical ones (artwright's contact sheet) and say what differs: palette, lighting, line weight, framing, rendering style. For pixel art run artwright-pixel on the outliers. For regeneration, hand the fix as prompt changes to the art skill the project uses.

## Print and play

`cw.py sheet <folder> --out deck.pdf --page letter --card 63x88 --bleed 3` lays 3x3 cards per page edge to edge at trim size, centred, with crop marks at the trim lines; `--bleed` says how much bleed the images carry, and it is cut off on the sheet (one cut between cards). Print houses want the full-bleed files instead. Images should be rendered at 300 DPI: 744x1039 px trim, 815x1110 px with 3 mm bleed. Tell the person to print at 100% (no "fit to page") and check one card with a ruler. Add `--backs cards.csv` (columns `deck`, `back`) to fail before rendering when two decks share a back image. Details: [references/print.md](references/print.md).

## Frames

A card frame is data, not code: keep a `frame.json` in the project (art window, title bar, cost badge, rarity border colours, text box, all in mm on the 63x88 card) and render frames with Pillow in the project's own script. Keep text 3 mm inside the trim.

## Maintenance

Evergreen unit: research in [RESEARCH.md](../../RESEARCH.md), changes in [CHANGELOG.md](../../CHANGELOG.md), lessons in [LEARNINGS.md](../../LEARNINGS.md), state in [evergreen.json](../../evergreen.json), evals in [TESTS.md](../../TESTS.md). On 'refresh cardwright', run evergreen-refresh on this unit.
