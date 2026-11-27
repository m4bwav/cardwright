#!/usr/bin/env python3
"""cardwright CLI: balance and art checks for a card set, and print-and-play sheets.

Standard library for the stats; Pillow only for `sheet` and `consistency`.

Card list: CSV or JSON (a list of objects). Columns used when present:
  name, cost, rarity, type, attack, health (or power, toughness), art (image path)
Column names can be remapped with --map cost=mana,attack=power.

Exit 0 ok, 1 problems found, 2 usage or input error.
"""
import argparse
import colorsys
import csv
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path

DEFAULT_BANDS = {"common": 0.60, "uncommon": 0.37, "rare": 0.03}  # Slay the Spire normal fights
MM_PER_IN = 25.4


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def load_cards(path, mapping=None):
    p = Path(path)
    if p.suffix.lower() == ".json":
        cards = json.loads(p.read_text(encoding="utf-8"))
    else:
        with open(p, encoding="utf-8-sig", newline="") as f:
            cards = list(csv.DictReader(f))
    mapping = mapping or {}
    out = []
    for c in cards:
        c = dict(c)
        for ours, theirs in mapping.items():
            if theirs in c:
                c[ours] = c[theirs]
        out.append(c)
    return out


def num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


# ---- curve ----------------------------------------------------------------

def curve(cards):
    counts = {}
    for c in cards:
        cost = num(c.get("cost"))
        key = "none" if cost is None else cost
        counts[key] = counts.get(key, 0) + 1
    return counts


def curve_problems(counts, max_share=0.35):
    total = sum(counts.values())
    numeric = sorted(k for k in counts if k != "none")
    probs = []
    if numeric:
        for k in range(int(min(numeric)), int(max(numeric)) + 1):
            if k not in counts:
                probs.append(f"gap: no cards at cost {k}")
    for k, n in counts.items():
        if total and n / total > max_share:
            probs.append(f"spike: cost {k} holds {n}/{total} ({n / total:.0%}), over {max_share:.0%}")
    return probs


def bar_chart(counts, width=30):
    peak = max(counts.values()) if counts else 1
    keys = sorted((k for k in counts if k != "none"), key=float) + (["none"] if "none" in counts else [])
    return "\n".join(f"{str(k):>5} | {'#' * max(1, round(counts[k] / peak * width))} {counts[k]}" for k in keys)


# ---- rarity ---------------------------------------------------------------

def rarity(cards, bands, tolerance=0.10):
    counts = {}
    for c in cards:
        r = (c.get("rarity") or "none").strip().lower()
        counts[r] = counts.get(r, 0) + 1
    total = sum(counts.values()) or 1
    rows, probs = [], []
    for r in sorted(set(counts) | set(bands)):
        share = counts.get(r, 0) / total
        target = bands.get(r)
        rows.append((r, counts.get(r, 0), share, target))
        if target is None:
            probs.append(f"rarity {r}: not in target bands")
        elif abs(share - target) > tolerance:
            probs.append(f"rarity {r}: {share:.0%} of set, target {target:.0%}")
    return rows, probs


# ---- vanilla test ----------------------------------------------------------

def vanilla(cards, per_cost=2.0, base=1.0, tolerance=1.5):
    """Stat total against cost: expected = base + per_cost * cost. A smell test,
    not a verdict: abilities are upside the numbers cannot see."""
    rows = []
    for c in cards:
        cost = num(c.get("cost"))
        a = num(c.get("attack", c.get("power")))
        h = num(c.get("health", c.get("toughness")))
        if cost is None or a is None or h is None:
            continue
        expected = base + per_cost * cost
        delta = (a + h) - expected
        if abs(delta) > tolerance:
            verdict = "strong" if delta > 0 else "weak"
            rows.append((c.get("name", "?"), cost, a + h, expected, delta, verdict))
    return rows


# ---- images (Pillow) -------------------------------------------------------

def need_pillow():
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        die("this command needs Pillow: pip install pillow")


def image_stats(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((128, 128))
    raw = im.tobytes()
    px = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    lum, sat, hx, hy = [], [], 0.0, 0.0
    for r, g, b in px:
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        lum.append(l)
        sat.append(s)
        hx += math.cos(2 * math.pi * h) * s
        hy += math.sin(2 * math.pi * h) * s
    hue = (math.degrees(math.atan2(hy, hx)) + 360) % 360
    return {"brightness": statistics.mean(lum), "contrast": statistics.pstdev(lum),
            "saturation": statistics.mean(sat), "hue": hue}


def outliers(stats, z=2.0):
    """Cards whose brightness, contrast or saturation sits more than z
    standard deviations from the set, or whose hue is far from the set's."""
    probs = []
    names = list(stats)
    if len(names) < 3:
        return probs
    for key in ("brightness", "contrast", "saturation"):
        vals = [stats[n][key] for n in names]
        mu, sd = statistics.mean(vals), statistics.pstdev(vals)
        if sd == 0:
            continue
        for n in names:
            score = (stats[n][key] - mu) / sd
            if abs(score) > z:
                probs.append(f"{n}: {key} {stats[n][key]:.2f}, set {mu:.2f} (z {score:+.1f})")
    return probs


def mm_to_px(mm, dpi):
    return round(mm / MM_PER_IN * dpi)


def back_slot(j, cols, rows, flip="long"):
    """Grid slot on the back page for the card in front slot j. Long-edge
    flip mirrors the column order, short-edge flip mirrors the row order."""
    r, c = divmod(j, cols)
    if flip == "long":
        return r * cols + (cols - 1 - c)
    return (rows - 1 - r) * cols + c


def sheet(images, out, page="letter", dpi=300, card_mm=(63, 88), bleed_mm=0.0,
          cols=3, rows=3, marks=True, backs=None, flip="long"):
    """Lay card images on pages, cols x rows each, centred, with crop marks.
    Cards sit edge to edge at trim size; an image with bleed_mm of bleed has
    the bleed cut off first (3x3 poker cards with bleed do not fit Letter).
    With backs (one image for all, or one per card) each front page is
    followed by its back page, slots mirrored for the flip edge, so a duplex
    print lines each back up behind its front.
    Returns the list of files written (one PNG per page, or one PDF)."""
    from PIL import Image, ImageDraw
    pages_mm = {"letter": (215.9, 279.4), "a4": (210.0, 297.0)}
    pw, ph = (mm_to_px(v, dpi) for v in pages_mm[page])
    cw, ch = (mm_to_px(v, dpi) for v in card_mm)
    if cols * cw > pw or rows * ch > ph:
        die(f"{cols}x{rows} cards of {card_mm[0]}x{card_mm[1]} mm do not fit on {page}")
    x0, y0 = (pw - cols * cw) // 2, (ph - rows * ch) // 2
    per = cols * rows
    if backs is not None and len(backs) not in (1, len(images)):
        die(f"--duplex: {len(backs)} back images for {len(images)} cards (give 1 or one per card)")
    jobs = []
    for i in range(0, len(images), per):
        chunk = images[i:i + per]
        jobs.append(list(enumerate(chunk)))
        if backs is not None:
            bk = [backs[0] if len(backs) == 1 else backs[i + j] for j in range(len(chunk))]
            jobs.append([(back_slot(j, cols, rows, flip), b) for j, b in enumerate(bk)])
    pages = []
    for job in jobs:
        pg = Image.new("RGB", (pw, ph), "white")
        d = ImageDraw.Draw(pg)
        for j, path in job:
            card = Image.open(path).convert("RGB")
            if bleed_mm:
                bx = round(card.width * bleed_mm / (card_mm[0] + 2 * bleed_mm))
                by = round(card.height * bleed_mm / (card_mm[1] + 2 * bleed_mm))
                card = card.crop((bx, by, card.width - bx, card.height - by))
            card = card.resize((cw, ch))
            x, y = x0 + (j % cols) * cw, y0 + (j // cols) * ch
            pg.paste(card, (x, y))
        if marks:
            b = 0
            tick = mm_to_px(4, dpi)
            xs = sorted({x0 + c * cw + off for c in range(cols) for off in (b, cw - b)})
            ys = sorted({y0 + r * ch + off for r in range(rows) for off in (b, ch - b)})
            for x in xs:
                d.line([(x, y0 - tick), (x, y0 - 2)], fill="black", width=2)
                d.line([(x, y0 + rows * ch + 2), (x, y0 + rows * ch + tick)], fill="black", width=2)
            for y in ys:
                d.line([(x0 - tick, y), (x0 - 2, y)], fill="black", width=2)
                d.line([(x0 + cols * cw + 2, y), (x0 + cols * cw + tick, y)], fill="black", width=2)
        pages.append(pg)
    out = Path(out)
    if out.suffix.lower() == ".pdf":
        pages[0].save(out, save_all=True, append_images=pages[1:], resolution=dpi)
        return [out]
    written = []
    for n, pg in enumerate(pages, 1):
        f = out.with_name(f"{out.stem}-{n}{out.suffix or '.png'}")
        pg.save(f, dpi=(dpi, dpi))
        written.append(f)
    return written


# ---- dupes ----------------------------------------------------------------

STAT_KEYS = ("attack", "health", "power", "toughness")
SKIP_KEYS = {"name", "cost", "rarity", "art", "back", "deck", "copies", "per_player", "base", "id"}


def _stats(c):
    return {k: num(c.get(k)) for k in STAT_KEYS if num(c.get(k)) is not None}


def _rest(c):
    """Non-identity, non-stat fields (type, text, ...) normalised."""
    return {k.lower(): str(v).strip().lower() for k, v in c.items()
            if k and k.lower() not in SKIP_KEYS and k.lower() not in STAT_KEYS
            and v not in (None, "")}


def dupes(cards):
    """Exact twins (same cost, stats and text) and strict dominance (same cost,
    same other text, every stat >= and one >). Warnings only: a strictly better
    near-copy can be deliberate (Kobold Guide p. 95)."""
    probs = []
    seen = {}
    for c in cards:
        key = (num(c.get("cost")), tuple(sorted(_stats(c).items())), tuple(sorted(_rest(c).items())))
        seen.setdefault(key, []).append(c.get("name", "?"))
    for names in seen.values():
        if len(names) > 1:
            probs.append(f"twin: {', '.join(names)} have the same cost and stats/text")
    for i, a in enumerate(cards):
        for b in cards[i + 1:]:
            cost = num(a.get("cost"))
            if cost is None or cost != num(b.get("cost")):
                continue
            sa, sb = _stats(a), _stats(b)
            if not sa or set(sa) != set(sb) or _rest(a) != _rest(b):
                continue
            for hi, lo, shi, slo in ((a, b, sa, sb), (b, a, sb, sa)):
                if all(shi[k] >= slo[k] for k in shi) and any(shi[k] > slo[k] for k in shi):
                    probs.append(f"dominates: {hi.get('name', '?')} is strictly better than "
                                 f"{lo.get('name', '?')} at cost {cost}")
    return probs


# ---- vanilla by rarity -----------------------------------------------------

RARITY_ORDER = ["common", "uncommon", "rare", "mythic", "legendary"]


def vanilla_by_rarity(cards, per_cost=2.0, base=1.0, tolerance=1.0):
    """Mean stat surplus (stats minus base + per_cost * cost) per rarity. Warn
    when a rarer tier beats common by more than tolerance: rarity is not a
    power budget (Kobold Guide p. 96-97)."""
    groups = {}
    for c in cards:
        cost = num(c.get("cost"))
        a = num(c.get("attack", c.get("power")))
        h = num(c.get("health", c.get("toughness")))
        if cost is None or a is None or h is None:
            continue
        r = (c.get("rarity") or "none").strip().lower()
        groups.setdefault(r, []).append((a + h) - (base + per_cost * cost))
    means = {r: statistics.mean(v) for r, v in groups.items()}
    probs = []
    if "common" in means:
        for r, m in means.items():
            if r != "common" and m - means["common"] > tolerance:
                probs.append(f"rarity {r}: mean surplus {m:+.2f}, common {means['common']:+.2f} "
                             f"(over by {m - means['common']:.2f}, tolerance {tolerance:g})")
    order = sorted(means, key=lambda r: RARITY_ORDER.index(r) if r in RARITY_ORDER else 99)
    return [(r, len(groups[r]), means[r]) for r in order], probs


# ---- rules text lint --------------------------------------------------------

# Our own list: phrases that read two ways in rules text.
AMBIGUOUS = {
    "in order to": "can read as a sequence; say 'to'",
    "and/or": "say 'or', 'and', or 'one or both'",
    "may not": "permission or possibility? say 'cannot'",
    "up to": "say whether zero counts",
    "should": "rule or advice? say 'must' or 'may'",
    "each other": "say which players or cards",
    "end of turn": "whose turn? say 'the end of this turn'",
    "next turn": "whose turn? say 'your next turn'",
    "etc": "list every case",
}


def load_glossary(path):
    """Lines 'term: alias1, alias2'. Returns {alias: term}."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        term, aliases = line.split(":", 1)
        for al in aliases.split(","):
            al = al.strip().lower()
            if al:
                out[al] = term.strip()
    return out


def _sentences(text):
    text = re.sub(r"^\s*#+ .*$", "", text, flags=re.M)  # headings are not sentences
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _syllables(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups, prev = 0, False
    for ch in w:
        v = ch in "aeiouy"
        if v and not prev:
            groups += 1
        prev = v
    if w.endswith("e") and groups > 1 and not w.endswith("le"):
        groups -= 1
    return max(1, groups)


def fk_grade(text):
    sents = _sentences(text)
    words = [w for s in sents for w in s.split()]
    if not sents or not words:
        return 0.0
    syl = sum(_syllables(w) for w in words)
    return 0.39 * len(words) / len(sents) + 11.8 * syl / len(words) - 15.59


def rules_lint(text, glossary=None, max_words=40, max_grade=None):
    """Other names for a glossary term, long sentences, ambiguous phrases, and
    optionally a Flesch-Kincaid grade cap (Kobold Guide p. 107-114)."""
    probs = []
    low = text.lower()
    for alias, term in (glossary or {}).items():
        n = len(re.findall(r"\b" + re.escape(alias) + r"\b", low))
        if n:
            probs.append(f"term: '{alias}' used {n}x, glossary name is '{term}'")
    for s in _sentences(text):
        n = len(s.split())
        if n > max_words:
            probs.append(f"long: {n} words: {s[:60]}...")
    for phrase, why in AMBIGUOUS.items():
        n = len(re.findall(r"\b" + re.escape(phrase) + r"\b", low))
        if n:
            probs.append(f"ambiguous: '{phrase}' {n}x, {why}")
    if max_grade is not None:
        g = fk_grade(text)
        if g > max_grade:
            probs.append(f"grade: Flesch-Kincaid {g:.1f}, cap {max_grade:g}")
    return probs


# ---- deck backs -------------------------------------------------------------

def shared_backs(cards):
    """Decks (deck column) that use the same back image (back column), by path
    or by identical file bytes. Players must tell decks apart from the back
    (Kobold Guide p. 120)."""
    decks = {}
    for c in cards:
        d, b = (c.get("deck") or "").strip(), (c.get("back") or "").strip()
        if d and b:
            decks.setdefault(d, set()).add(b)
    owners = {}
    for d, backs in decks.items():
        for b in backs:
            p = Path(b)
            key = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else b.lower()
            owners.setdefault(key, set()).add(d)
    return [f"backs: decks {', '.join(sorted(ds))} share a back image"
            for ds in owners.values() if len(ds) > 1]


# ---- manifest ---------------------------------------------------------------

def manifest(cards, players, rules_text=None):
    """Copies needed at max players against supplied (Kobold Guide p. 118-119,
    125). Columns: per_player (copies each player needs), base (copies needed
    at any count, default 0), copies (copies in the box, default 1).
    Needed = base + per_player * players. With rules text, also lists cards
    whose name never appears in it."""
    probs = []
    for c in cards:
        pp, base = num(c.get("per_player")) or 0, num(c.get("base")) or 0
        supplied = num(c.get("copies"))
        supplied = 1 if supplied is None else supplied
        need = base + pp * players
        if need > supplied:
            probs.append(f"short: {c.get('name', '?')} needs {need:g} at {players} players, "
                         f"box has {supplied:g}")
    if rules_text is not None:
        low = rules_text.lower()
        for c in cards:
            n = (c.get("name") or "").strip()
            if n and not re.search(r"\b" + re.escape(n.lower()) + r"(e?s)?\b", low):
                probs.append(f"unmentioned: {n} is not named in the rules")
    return probs


# ---- baseline (greedy bot) --------------------------------------------------

def card_value(c):
    return sum(_stats(c).values())


def value_ratio(c):
    cost = num(c.get("cost")) or 0
    return card_value(c) / max(cost, 1)


def greedy_deck(pool, size):
    """The greedy baseline: take the best stats-per-cost card again and again
    (respecting copies, default 1 each; cycles the pool if it runs out)."""
    ranked = sorted(pool, key=lambda c: (-value_ratio(c), num(c.get("cost")) or 0))
    out = []
    for c in ranked:
        n = num(c.get("copies"))
        out += [c] * int(1 if n is None else n)
    if not out:
        return []
    while len(out) < size:
        out += out
    return out[:size]


def _attack(c):
    v = c.get("attack")
    return num(v if v not in (None, "") else c.get("power")) or 0


def race(deck_a, deck_b, games=200, seed=1, life=20, hand=3, max_turns=30):
    """Seeded no-blocking race: mana = turn number (cap 10), play the best
    stats-per-cost cards that fit, every unit hits the opponent each turn.
    Players alternate going first. Returns (wins_a, wins_b, draws)."""
    import random
    rng = random.Random(seed)
    tally = [0, 0, 0]
    for g in range(games):
        decks = [list(deck_a), list(deck_b)]
        for d in decks:
            rng.shuffle(d)
        hands = [[d.pop() for _ in range(min(hand, len(d)))] for d in decks]
        board, hp = [0, 0], [life, life]
        order = (0, 1) if g % 2 == 0 else (1, 0)
        winner = None
        for turn in range(1, max_turns + 1):
            for me in order:
                if decks[me]:
                    hands[me].append(decks[me].pop())
                mana = min(turn, 10)
                for c in sorted(hands[me], key=lambda c: -value_ratio(c)):
                    cost = num(c.get("cost")) or 0
                    if cost <= mana:
                        mana -= cost
                        hands[me].remove(c)
                        board[me] += _attack(c)
                hp[1 - me] -= board[me]
                if hp[1 - me] <= 0:
                    winner = me
                    break
            if winner is not None:
                break
        tally[2 if winner is None else winner] += 1
    return tuple(tally)


def autopicks(pool, factor=1.5):
    """Cards whose stats per cost beat the pool median by `factor`: the greedy
    bot takes them first every time."""
    ratios = [value_ratio(c) for c in pool if _stats(c)]
    if not ratios:
        return []
    med = statistics.median(ratios)
    return [f"autopick: {c.get('name', '?')} gives {value_ratio(c):.2f} stats per cost "
            f"(pool median {med:.2f})" for c in pool if _stats(c) and value_ratio(c) > med * factor]


# ---- matchup ledger ---------------------------------------------------------

def matchups(rows, min_games=5, lopsided=0.70):
    """Rows with a, b, winner (a deck name, or draw). Returns per-deck lines,
    per-pair lines and problems for pairs at or past `lopsided` either way.
    A draw counts half a win."""
    decks, pairs = {}, {}
    for r in rows:
        a, b = (r.get("a") or "").strip(), (r.get("b") or "").strip()
        w = (r.get("winner") or "").strip()
        if not a or not b:
            continue
        if w not in (a, b, "draw"):
            die(f"matchup: winner '{w}' is neither {a}, {b} nor draw")
        for x in (a, b):
            decks.setdefault(x, [0, 0, 0])
        key = tuple(sorted((a, b)))
        pairs.setdefault(key, [0, 0, 0])
        if w == "draw":
            decks[a][2] += 1
            decks[b][2] += 1
            pairs[key][2] += 1
        else:
            loser = b if w == a else a
            decks[w][0] += 1
            decks[loser][1] += 1
            pairs[key][0 if w == key[0] else 1] += 1

    def rate(w, l, d):
        return (w + d / 2) / max(w + l + d, 1)

    lines, probs = [], []
    for d, t in sorted(decks.items(), key=lambda kv: (-rate(*kv[1]), kv[0])):
        lines.append(f"{d}: {t[0]}-{t[1]}-{t[2]} ({rate(*t):.0%})")
    for (x, y), (wx, wy, dr) in sorted(pairs.items()):
        n, r = wx + wy + dr, rate(wx, wy, dr)
        line = f"{x} vs {y}: {wx}-{wy}-{dr} ({r:.0%} for {x})"
        if n < min_games:
            line += f" (under {min_games} games)"
        elif r >= lopsided or r <= 1 - lopsided:
            hi, lo, rr = (x, y, r) if r >= 0.5 else (y, x, 1 - r)
            probs.append(f"lopsided: {hi} beats {lo} {rr:.0%} over {n} games")
        lines.append(line)
    return lines, probs


# ---- starter set lint -------------------------------------------------------

DEFAULT_COMPLEX = ("instead", "copy", "stack", "interrupt", "replace", "any time",
                   "respond", "counter", "swap", "steal")


def starter(cards, max_cards=40, max_cost=5, max_words=20, complex_terms=DEFAULT_COMPLEX,
            max_share=0.35):
    """A first-game set: small, cheap, plain text, an even curve. Flags size,
    costs over max_cost, cards with more than max_words of text, text with a
    high-complexity term, and the curve problems from `curve`."""
    probs = []
    if len(cards) > max_cards:
        probs.append(f"size: {len(cards)} cards, a first game wants {max_cards} or fewer")
    for c in cards:
        n = c.get("name", "?")
        cost = num(c.get("cost"))
        if cost is not None and cost > max_cost:
            probs.append(f"cost: {n} costs {cost:g}, over the starter cap {max_cost:g}")
        text = str(c.get("text") or "")
        words = len(text.split())
        if words > max_words:
            probs.append(f"wordy: {n} has {words} words of text (cap {max_words})")
        low = text.lower()
        hits = [t for t in complex_terms if re.search(r"\b" + re.escape(t.lower()) + r"\b", low)]
        if hits:
            probs.append(f"complex: {n} uses {', '.join(hits)}")
    probs += curve_problems(curve(cards), max_share)
    return probs


# ---- main -----------------------------------------------------------------

def parse_map(s):
    if not s:
        return {}
    return dict(kv.split("=", 1) for kv in s.split(","))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cw.py", description=__doc__.split("\n")[0])
    ap.add_argument("--map", help="column remap, e.g. cost=mana,attack=power")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("curve", help="cost curve with gaps and spikes")
    c.add_argument("cards")
    c.add_argument("--max-share", type=float, default=0.35)

    r = sub.add_parser("rarity", help="rarity mix against target bands")
    r.add_argument("cards")
    r.add_argument("--bands", help='JSON, e.g. {"common":0.6,"uncommon":0.3,"rare":0.1}')
    r.add_argument("--tolerance", type=float, default=0.10)

    v = sub.add_parser("vanilla", help="stat total against cost, outliers only")
    v.add_argument("cards")
    v.add_argument("--per-cost", type=float, default=2.0)
    v.add_argument("--base", type=float, default=1.0)
    v.add_argument("--tolerance", type=float, default=None,
                   help="outlier tolerance (1.5); with --by-rarity, rare-over-common tolerance (1.0)")
    v.add_argument("--by-rarity", action="store_true", help="mean stat surplus per rarity")

    du = sub.add_parser("dupes", help="exact twins and strictly better cards (warnings)")
    du.add_argument("cards")

    ru = sub.add_parser("rules", help="rules text lint")
    ru.add_argument("file")
    ru.add_argument("--glossary", help="lines 'term: alias1, alias2'")
    ru.add_argument("--max-words", type=int, default=40)
    ru.add_argument("--max-grade", type=float, help="Flesch-Kincaid grade cap (rulebook prose only)")

    mf = sub.add_parser("manifest", help="copies needed at max players, cards the rules never name")
    mf.add_argument("cards")
    mf.add_argument("--players", type=int, required=True)
    mf.add_argument("--rules", help="rules file to search for card names")

    bl = sub.add_parser("baseline", help="greedy bot every deck must beat")
    bl.add_argument("pool", help="card pool the greedy bot builds from")
    bl.add_argument("--deck", help="deck list to race against the greedy deck")
    bl.add_argument("--size", type=int, default=20)
    bl.add_argument("--games", type=int, default=200)
    bl.add_argument("--seed", type=int, default=1)
    bl.add_argument("--min-win", type=float, default=0.5)
    bl.add_argument("--factor", type=float, default=1.5, help="autopick: ratio over pool median")

    mu = sub.add_parser("matchup", help="deck-vs-deck win/loss ledger")
    mu.add_argument("log", help="CSV with a, b, winner (deck name or draw)")
    mu.add_argument("--record", nargs=3, metavar=("A", "B", "WINNER"), help="append one result first")
    mu.add_argument("--min-games", type=int, default=5)
    mu.add_argument("--lopsided", type=float, default=0.70)

    st = sub.add_parser("starter", help="recommended first-game set lint")
    st.add_argument("cards")
    st.add_argument("--max-cards", type=int, default=40)
    st.add_argument("--max-cost", type=float, default=5)
    st.add_argument("--max-words", type=int, default=20)
    st.add_argument("--complex", help="comma-separated high-complexity terms (replaces the default list)")

    k = sub.add_parser("consistency", help="art outliers across a set (Pillow)")
    k.add_argument("images", nargs="+", help="image files or one folder")
    k.add_argument("--z", type=float, default=2.0)
    k.add_argument("--json", action="store_true")

    s = sub.add_parser("sheet", help="print-and-play sheets (Pillow)")
    s.add_argument("images", nargs="+", help="image files or one folder")
    s.add_argument("--out", required=True, help="sheet.pdf, or sheet.png for one PNG per page")
    s.add_argument("--page", choices=["letter", "a4"], default="letter")
    s.add_argument("--dpi", type=int, default=300)
    s.add_argument("--card", default="63x88", help="card size in mm, WxH")
    s.add_argument("--bleed", type=float, default=0.0, help="bleed in mm included in each image")
    s.add_argument("--grid", default="3x3")
    s.add_argument("--no-marks", action="store_true")
    s.add_argument("--backs", metavar="CARDS",
                   help="card list with deck and back columns; fail if two decks share a back")
    s.add_argument("--duplex", nargs="+", metavar="BACK",
                   help="back image(s): one for all, or one per card; adds mirrored back pages")
    s.add_argument("--flip", choices=["long", "short"], default="long",
                   help="duplex binding edge (long: columns mirrored, short: rows)")

    a = ap.parse_args(argv)
    mapping = parse_map(a.map)

    if a.cmd == "curve":
        counts = curve(load_cards(a.cards, mapping))
        print(bar_chart(counts))
        probs = curve_problems(counts, a.max_share)
        for p in probs:
            print(p)
        return 1 if probs else 0

    if a.cmd == "rarity":
        bands = json.loads(a.bands) if a.bands else DEFAULT_BANDS
        rows, probs = rarity(load_cards(a.cards, mapping), bands, a.tolerance)
        for name, n, share, target in rows:
            t = f"target {target:.0%}" if target is not None else "no target"
            print(f"{name:>10} {n:>4} {share:>5.0%}  {t}")
        for p in probs:
            print(p)
        return 1 if probs else 0

    if a.cmd == "vanilla" and a.by_rarity:
        tol = 1.0 if a.tolerance is None else a.tolerance
        rows, probs = vanilla_by_rarity(load_cards(a.cards, mapping), a.per_cost, a.base, tol)
        for r, n, m in rows:
            print(f"{r:>10} {n:>4} mean surplus {m:+.2f}")
        for p in probs:
            print(p)
        return 1 if probs else 0

    if a.cmd == "vanilla":
        tol = 1.5 if a.tolerance is None else a.tolerance
        rows = vanilla(load_cards(a.cards, mapping), a.per_cost, a.base, tol)
        for name, cost, stats, exp, delta, verdict in rows:
            print(f"{name}: cost {cost}, stats {stats}, expected {exp:g} ({delta:+g}, {verdict})")
        if not rows:
            print("ok")
        return 1 if rows else 0

    if a.cmd == "dupes":
        probs = dupes(load_cards(a.cards, mapping))
        for p in probs:
            print(f"warning: {p}")
        if not probs:
            print("ok")
        return 0

    if a.cmd in ("rules", "manifest"):
        if a.cmd == "rules":
            gloss = load_glossary(a.glossary) if a.glossary else None
            probs = rules_lint(Path(a.file).read_text(encoding="utf-8"), gloss, a.max_words, a.max_grade)
        else:
            rules = Path(a.rules).read_text(encoding="utf-8") if a.rules else None
            probs = manifest(load_cards(a.cards, mapping), a.players, rules)
        for p in probs:
            print(p)
        if not probs:
            print("ok")
        return 1 if probs else 0

    if a.cmd == "baseline":
        pool = load_cards(a.pool, mapping)
        greedy = greedy_deck(pool, a.size)
        if not greedy:
            die("baseline: empty pool")
        probs = autopicks(pool, a.factor)
        if a.deck:
            w, l, d = race(load_cards(a.deck, mapping), greedy, a.games, a.seed)
            rate = (w + d / 2) / a.games
            print(f"deck vs greedy: {w}-{l}-{d} over {a.games} games ({rate:.0%})")
            if rate < a.min_win:
                probs.append(f"baseline: deck wins {rate:.0%} against the greedy bot "
                             f"(needs {a.min_win:.0%})")
        else:
            print("greedy picks: " + ", ".join(c.get("name", "?") for c in greedy))
        for p in probs:
            print(p)
        return 1 if probs else 0

    if a.cmd == "matchup":
        log = Path(a.log)
        if a.record:
            new = not log.exists() or log.stat().st_size == 0
            with open(log, "a", encoding="utf-8", newline="") as f:
                wr = csv.writer(f, lineterminator="\n")
                if new:
                    wr.writerow(["a", "b", "winner"])
                wr.writerow(a.record)
        lines, probs = matchups(load_cards(log), a.min_games, a.lopsided)
        for x in lines + probs:
            print(x)
        return 1 if probs else 0

    if a.cmd == "starter":
        terms = [t.strip() for t in a.complex.split(",") if t.strip()] if a.complex else DEFAULT_COMPLEX
        probs = starter(load_cards(a.cards, mapping), a.max_cards, a.max_cost, a.max_words, terms)
        for p in probs:
            print(p)
        if not probs:
            print("ok")
        return 1 if probs else 0

    if a.cmd == "sheet" and a.backs:
        probs = shared_backs(load_cards(a.backs, mapping))
        for p in probs:
            print(p)
        if probs:
            return 1

    files = a.images
    if len(files) == 1 and Path(files[0]).is_dir():
        files = sorted(str(p) for p in Path(files[0]).iterdir()
                       if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    if not files:
        die("no images")
    need_pillow()

    if a.cmd == "consistency":
        stats = {Path(f).name: image_stats(f) for f in files}
        probs = outliers(stats, a.z)
        if a.json:
            print(json.dumps({"stats": stats, "outliers": probs}, indent=2))
        else:
            for p in probs:
                print(p)
            if not probs:
                print(f"ok: {len(stats)} images, no outliers at z {a.z}")
        return 1 if probs else 0

    if a.cmd == "sheet":
        w, h = (float(x) for x in a.card.lower().split("x"))
        cols, rows = (int(x) for x in a.grid.lower().split("x"))
        out = sheet(files, a.out, a.page, a.dpi, (w, h), a.bleed, cols, rows, not a.no_marks,
                    a.duplex, a.flip)
        for f in out:
            print(f)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
