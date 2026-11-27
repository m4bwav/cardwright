import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import cw  # noqa: E402

POOL = ("name,cost,attack,health,copies\n"
        "Gem,1,4,4,2\nSlug,3,1,1,4\nOgre,4,4,4,4\nWisp,2,2,2,4\n")


def _f(tmp_path, text, name="c.csv"):
    f = tmp_path / name
    f.write_bytes(text.encode("utf-8"))
    return f


def test_greedy_deck_and_autopick(tmp_path):
    pool = cw.load_cards(_f(tmp_path, POOL))
    deck = cw.greedy_deck(pool, 6)
    assert [c["name"] for c in deck] == ["Gem", "Gem", "Wisp", "Wisp", "Wisp", "Wisp"]
    probs = cw.autopicks(pool)
    assert len(probs) == 1 and probs[0].startswith("autopick: Gem")


def test_race_is_seeded_and_weak_deck_loses(tmp_path):
    pool = cw.load_cards(_f(tmp_path, POOL))
    greedy = cw.greedy_deck(pool, 20)
    weak = [pool[1]] * 20  # Slug only
    r1 = cw.race(weak, greedy, games=50, seed=3)
    assert r1 == cw.race(weak, greedy, games=50, seed=3)
    assert r1[1] > r1[0]
    p = _f(tmp_path, POOL, "pool.csv")
    d = _f(tmp_path, "name,cost,attack,health\n" + "Slug,3,1,1\n" * 20, "deck.csv")
    assert cw.main(["baseline", str(p), "--deck", str(d), "--games", "40", "--factor", "99"]) == 1
    assert cw.main(["baseline", str(p), "--factor", "99"]) == 0


def test_matchup_ledger(tmp_path):
    log = tmp_path / "log.csv"
    for _ in range(5):
        assert cw.main(["matchup", str(log), "--record", "Red", "Blue", "Red"]) in (0, 1)
    lines, probs = cw.matchups(cw.load_cards(log))
    assert "Red: 5-0-0 (100%)" in lines
    assert probs == ["lopsided: Red beats Blue 100% over 5 games"]
    assert log.read_bytes().startswith(b"a,b,winner\n")
    rows = [{"a": "A", "b": "B", "winner": w} for w in ["A", "B", "draw", "A"]]
    lines, probs = cw.matchups(rows)
    assert "A vs B: 2-1-1 (62% for A) (under 5 games)" in lines and probs == []
    with pytest.raises(SystemExit):
        cw.matchups([{"a": "A", "b": "B", "winner": "C"}])


def test_starter_lint(tmp_path):
    f = _f(tmp_path, "name,cost,text\nA,1,Draw a card.\nB,2,Gain 2.\nC,3,Counter target spell instead.\n"
                     "D,7,Big.\nE,2," + " ".join(["word"] * 25) + "\n")
    probs = cw.starter(cw.load_cards(f), max_cards=4)
    assert "size: 5 cards, a first game wants 4 or fewer" in probs
    assert "cost: D costs 7, over the starter cap 5" in probs
    assert "complex: C uses instead, counter" in probs
    assert any(p.startswith("wordy: E has 25") for p in probs)
    ok = _f(tmp_path, "name,cost,text\nA,1,Draw.\nB,2,Gain 2.\nC,3,Hit 3.\n", "ok.csv")
    assert cw.main(["starter", str(ok)]) == 0


def test_back_slot_mirrors():
    assert [cw.back_slot(j, 3, 3) for j in range(3)] == [2, 1, 0]
    assert cw.back_slot(3, 3, 3) == 5
    assert cw.back_slot(0, 3, 3, "short") == 6
    assert cw.back_slot(8, 3, 3, "short") == 2


def test_sheet_duplex_pages(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    fronts = []
    for i, col in enumerate(["red", "green"]):
        p = tmp_path / f"f{i}.png"
        Image.new("RGB", (63, 88), col).save(p)
        fronts.append(str(p))
    back = tmp_path / "back.png"
    Image.new("RGB", (63, 88), "blue").save(back)
    out = cw.sheet(fronts, tmp_path / "s.png", dpi=50, backs=[str(back)])
    assert len(out) == 2
    pg = Image.open(out[1])
    cw_px, ch_px = cw.mm_to_px(63, 50), cw.mm_to_px(88, 50)
    x0, y0 = (pg.width - 3 * cw_px) // 2, (pg.height - 3 * ch_px) // 2
    right = pg.getpixel((x0 + 2 * cw_px + cw_px // 2, y0 + ch_px // 2))
    left = pg.getpixel((x0 + cw_px // 2, y0 + ch_px // 2))
    assert right == (0, 0, 255) and left == (255, 255, 255)
    with pytest.raises(SystemExit):
        cw.sheet(fronts, tmp_path / "x.png", dpi=50, backs=[str(back)] * 3)
