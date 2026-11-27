# Changelog

## 0.3.0 (2026-11-26)
Source: Kobold Guide to Board Game Design, p. 87-94 (playtesting and balance), plus the Story Please duplex note in the harvest list.
- `cw.py baseline POOL [--deck DECK]`: a greedy bot builds a deck by best stats per cost and plays a seeded no-blocking race. With `--deck` it reports the deck's win rate against the greedy deck and fails under `--min-win` (50%). It also flags autopicks, cards more than 1.5x the pool median stats per cost. A set or deck should beat the dumbest strategy.
- `cw.py matchup LOG [--record A B WINNER]`: a deck-vs-deck ledger (CSV `a,b,winner`, draw counts half). Prints win rates per deck and per pair, fails on a pair at 70% or more over at least 5 games.
- `cw.py starter CARDS`: lints a recommended first-game set: at most 40 cards, cost cap 5, 20 words of text per card, no high-complexity terms (our own list, replace with `--complex`), and the curve checks.
- `cw.py sheet --duplex BACK [--flip long|short]`: a back page after every front page with slots mirrored for the binding edge, so double-sided prints line up.

## 0.2.0 (2026-11-26)
Source: Kobold Guide to Board Game Design (Garfield, Jackson, Yu and others).
- `cw.py dupes`: warns on exact twins (same cost, stats and text) and strict dominance (same cost and text, every stat at least as high, one higher). Warnings only, exit 0: the book merges near-identical filler cards (p. 86) but defends some strictly better copies (p. 95).
- `cw.py vanilla --by-rarity`: mean stat surplus per rarity; flags a tier that beats common by more than `--tolerance` (default 1.0). Rarity is not a power budget (p. 96-97).
- `cw.py rules FILE.md [--glossary terms.txt]`: other names for a glossary term (`term: alias1, alias2`), sentences over 40 words, an optional Flesch-Kincaid cap (`--max-grade`), and our own list of ambiguous phrases. One term per concept, short sentences, plain grade level (p. 107-114).
- `cw.py sheet --backs CARDS`: fails when two decks (`deck` column) share a back image (`back` column), by path or identical bytes. Decks must be told apart from the back (p. 120).
- `cw.py manifest CARDS --players N [--rules FILE]`: copies needed at N players (`base + per_player * N`) against `copies` in the box, and cards the rules never name. Prototypes run short at the top player count and rules drift from new cards (p. 118-119, 125).

## 0.1.0 (2026-11-25)
- First version: hub skill (balance, art consistency, print and play, frames), references for balance methods and print sizes, `cw.py` (curve, rarity, vanilla, consistency, sheet) with 9 tests. An eval found `--bleed 3` would not fit 3x3 on Letter; sheets now cut bleed off and butt cards at trim size.
