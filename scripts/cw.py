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
import json
import math
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


def sheet(images, out, page="letter", dpi=300, card_mm=(63, 88), bleed_mm=0.0,
          cols=3, rows=3, marks=True):
    """Lay card images on pages, cols x rows each, centred, with crop marks.
    Cards sit edge to edge at trim size; an image with bleed_mm of bleed has
    the bleed cut off first (3x3 poker cards with bleed do not fit Letter).
    Returns the list of files written (one PNG per page, or one PDF)."""
    from PIL import Image, ImageDraw
    pages_mm = {"letter": (215.9, 279.4), "a4": (210.0, 297.0)}
    pw, ph = (mm_to_px(v, dpi) for v in pages_mm[page])
    cw, ch = (mm_to_px(v, dpi) for v in card_mm)
    if cols * cw > pw or rows * ch > ph:
        die(f"{cols}x{rows} cards of {card_mm[0]}x{card_mm[1]} mm do not fit on {page}")
    x0, y0 = (pw - cols * cw) // 2, (ph - rows * ch) // 2
    per = cols * rows
    pages = []
    for i in range(0, len(images), per):
        pg = Image.new("RGB", (pw, ph), "white")
        d = ImageDraw.Draw(pg)
        for j, path in enumerate(images[i:i + per]):
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
    v.add_argument("--tolerance", type=float, default=1.5)

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

    if a.cmd == "vanilla":
        rows = vanilla(load_cards(a.cards, mapping), a.per_cost, a.base, a.tolerance)
        for name, cost, stats, exp, delta, verdict in rows:
            print(f"{name}: cost {cost}, stats {stats}, expected {exp:g} ({delta:+g}, {verdict})")
        if not rows:
            print("ok")
        return 1 if rows else 0

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
        out = sheet(files, a.out, a.page, a.dpi, (w, h), a.bleed, cols, rows, not a.no_marks)
        for f in out:
            print(f)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
