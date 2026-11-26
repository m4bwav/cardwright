import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import cw  # noqa: E402

CARDS = HERE / "fixtures" / "cards.csv"


def _csv(tmp_path, text, name="c.csv"):
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return f


def test_dupes_twin_and_dominance(tmp_path):
    f = _csv(tmp_path, "name,cost,type,attack,health\n"
                       "A,2,unit,2,2\nB,2,unit,2,2\nC,2,unit,3,2\nD,2,spell,4,4\nE,3,unit,1,1\n")
    probs = cw.dupes(cw.load_cards(f))
    assert "twin: A, B have the same cost and stats/text" in probs
    assert "dominates: C is strictly better than A at cost 2" in probs
    assert not any("D" in p.split(":")[1].split()[0] for p in probs if p.startswith("dominates"))
    assert cw.main(["dupes", str(f)]) == 0  # warn only


def test_vanilla_by_rarity_flags_inflated_rares():
    rows, probs = cw.vanilla_by_rarity(cw.load_cards(CARDS))
    assert [r[0] for r in rows] == ["common", "uncommon", "rare"]
    assert any(p.startswith("rarity rare:") for p in probs)
    assert cw.main(["vanilla", str(CARDS), "--by-rarity", "--tolerance", "20"]) == 0


def test_rules_lint(tmp_path):
    long = " ".join(["word"] * 60) + "."
    text = f"# Setup\n\nDraw a card in order to start. Put the tile on the board. {long}\n"
    g = _csv(tmp_path, "tile: token, chit\n", "g.txt")
    probs = cw.rules_lint(text, cw.load_glossary(g))
    assert "term: 'tile' used 1x, glossary name is 'tile'" not in probs
    assert any(p.startswith("long: 60 words") for p in probs)
    assert any(p.startswith("ambiguous: 'in order to'") for p in probs)
    probs = cw.rules_lint("Place a chit.", cw.load_glossary(g))
    assert probs == ["term: 'chit' used 1x, glossary name is 'tile'"]
    assert cw.rules_lint("Draw a card.", max_grade=-50)[0].startswith("grade:")
    assert cw.rules_lint("Draw a card.") == []


def test_sheet_backs_shared(tmp_path):
    back = tmp_path / "back.png"
    back.write_bytes(b"same")
    copy = tmp_path / "copy.png"
    copy.write_bytes(b"same")
    other = tmp_path / "other.png"
    other.write_bytes(b"different")
    cards = [{"deck": "red", "back": str(back)}, {"deck": "blue", "back": str(copy)},
             {"deck": "green", "back": str(other)}]
    assert cw.shared_backs(cards) == ["backs: decks blue, red share a back image"]
    assert cw.shared_backs(cards[2:]) == []
    f = _csv(tmp_path, f"name,deck,back\nX,red,{back}\nY,blue,{copy}\n")
    assert cw.main(["sheet", str(tmp_path), "--out", str(tmp_path / "s.pdf"), "--backs", str(f)]) == 1


def test_manifest_shortfall_and_unmentioned(tmp_path):
    f = _csv(tmp_path, "name,per_player,base,copies\nWorker,3,0,12\nCoin,5,10,30\nCrown,0,1,\n")
    probs = cw.manifest(cw.load_cards(f), 5)
    assert probs == ["short: Worker needs 15 at 5 players, box has 12",
                     "short: Coin needs 35 at 5 players, box has 30"]
    assert cw.manifest(cw.load_cards(f), 4) == []
    probs = cw.manifest(cw.load_cards(f), 4, "Each player takes 3 workers and 5 coins.")
    assert probs == ["unmentioned: Crown is not named in the rules"]
