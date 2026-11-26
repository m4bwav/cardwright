# cardwright

![cardwright banner](.github/images/banner.jpg)

Set-level checks for card games, as a Claude Code plugin. Point it at a card list and an art folder and it tells you where the cost curve has holes, whether the rarity mix matches your targets, which cards are overstatted for their cost, which illustrations do not match the rest of the set, and it lays out print-and-play sheets.

## What it does

- **Curve**: `cw.py curve cards.csv` draws the cost curve and flags gaps and spikes.
- **Rarity**: `cw.py rarity cards.csv --bands '{"common":0.6,"uncommon":0.3,"rare":0.1}'`.
- **Vanilla test**: `cw.py vanilla cards.csv` flags units whose stats are far off the cost line.
- **Rarity power**: `cw.py vanilla cards.csv --by-rarity` flags rares whose stats beat commons on average.
- **Duplicates**: `cw.py dupes cards.csv` warns on twins and strictly better cards at the same cost.
- **Rules text**: `cw.py rules rules.md --glossary terms.txt` flags other names for a term, long sentences, ambiguous phrases, and an optional grade cap.
- **Box manifest**: `cw.py manifest cards.csv --players 5 --rules rules.md` checks copies (`per_player`, `base`, `copies` columns) and cards the rules never name.
- **Art consistency**: `cw.py consistency art/` flags images whose brightness, contrast or saturation stand out from the set.
- **Print and play**: `cw.py sheet art/ --out deck.pdf --page letter --bleed 3` puts 3x3 poker cards (63x88 mm) per page with crop marks; `--backs cards.csv` fails when two decks share a back image.

Card lists are CSV or JSON with `name, cost, rarity, attack, health`; remap columns with `--map cost=mana`. Balance checks need only Python 3.9+. Image commands need Pillow.

## Install

```
/plugin marketplace add m4bwav/cardwright
/plugin install cardwright
```

Or run the script directly: `python scripts/cw.py --help`.

## Develop

`python -m pytest -q`. Rules: [AGENTS.md](AGENTS.md).

## Licence

MIT.
