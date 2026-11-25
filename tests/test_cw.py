import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import cw  # noqa: E402

CARDS = HERE / "fixtures" / "cards.csv"


def test_curve_counts_and_gap():
    counts = cw.curve(cw.load_cards(CARDS))
    assert counts == {1: 4, 2: 3, 3: 2, 5: 1}
    probs = cw.curve_problems(counts)
    assert "gap: no cards at cost 4" in probs
    assert any(p.startswith("spike: cost 1") for p in probs)


def test_rarity_against_bands():
    rows, probs = cw.rarity(cw.load_cards(CARDS), {"common": 0.7, "uncommon": 0.2, "rare": 0.1})
    assert ("common", 7, 0.7, 0.7) in rows
    assert probs == []
    _, probs = cw.rarity(cw.load_cards(CARDS), cw.DEFAULT_BANDS)
    assert "rarity uncommon: 20% of set, target 37%" in probs


def test_vanilla_outliers():
    rows = cw.vanilla(cw.load_cards(CARDS))
    names = {r[0]: r[5] for r in rows}
    assert names == {"Brute": "strong", "Titan": "strong"}
    assert "Scout" not in names and "Shield Wall" not in names


def test_map_columns(tmp_path):
    f = tmp_path / "c.json"
    f.write_text('[{"name": "X", "mana": 2, "power": 1, "toughness": 1}]')
    cards = cw.load_cards(f, {"cost": "mana"})
    assert cw.curve(cards) == {2: 1}
    assert cw.vanilla(cards)[0][5] == "weak"


def _imgs(tmp_path, colours):
    from PIL import Image
    files = []
    for i, c in enumerate(colours):
        p = tmp_path / f"c{i}.png"
        Image.new("RGB", (60, 84), c).save(p)
        files.append(str(p))
    return files


def test_consistency_flags_odd_card(tmp_path):
    pytest.importorskip("PIL")
    files = _imgs(tmp_path, [(40, 60, 120)] * 6 + [(250, 250, 250)])
    stats = {Path(f).name: cw.image_stats(f) for f in files}
    probs = cw.outliers(stats)
    assert probs and all(p.startswith("c6.png") for p in probs)


def test_sheet_pages_and_size(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image
    files = _imgs(tmp_path, [(200, 0, 0)] * 10)
    out = cw.sheet(files, tmp_path / "s.png", dpi=100)
    assert len(out) == 2
    assert Image.open(out[0]).size == (850, 1100)
    pdf = cw.sheet(files, tmp_path / "s.pdf", dpi=100)
    assert pdf[0].read_bytes()[:4] == b"%PDF"


def test_sheet_too_big(tmp_path):
    pytest.importorskip("PIL")
    files = _imgs(tmp_path, [(0, 0, 0)])
    with pytest.raises(SystemExit):
        cw.sheet(files, tmp_path / "s.png", cols=4)


def test_cli_exit_codes(capsys):
    assert cw.main(["curve", str(CARDS)]) == 1
    assert cw.main(["rarity", str(CARDS), "--bands", '{"common":0.7,"uncommon":0.2,"rare":0.1}']) == 0


def test_sheet_with_bleed_fits_letter(tmp_path):
    pytest.importorskip("PIL")
    files = _imgs(tmp_path, [(0, 90, 0)] * 9)
    assert len(cw.sheet(files, tmp_path / "b.pdf", bleed_mm=3)) == 1
