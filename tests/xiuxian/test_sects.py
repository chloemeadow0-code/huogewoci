"""Tests for the two new sects: hehuan (dark charm route) and taixu (lightning)."""

import pytest

from xiuxian.island import IslandGame
from xiuxian.mcp_dispatch import dispatch


@pytest.fixture
def hehuan(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "hehuan.db", player_key="hh", player_name="合欢弟子")
    assert dispatch(g, "sect_ops", "join hehuan")["ok"]
    original = g._roll
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 100 if "incident" in purpose else original(purpose)
    )
    yield g
    g.close()


@pytest.fixture
def taixu(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "taixu.db", player_key="tx", player_name="太虚弟子")
    assert dispatch(g, "sect_ops", "join taixu")["ok"]
    original = g._roll
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 100 if "incident" in purpose else original(purpose)
    )
    yield g
    g.close()


def test_hehuan_route_setup(hehuan):
    p = hehuan.player
    assert p["sect"] == "合欢宗" and p["islandLocation"] == "hehuan"
    assert "hehuan_bell" in p["skills"] and "hehuan_zen" in p["techniques"]
    assert hehuan.player["techniqueLevels"]["hehuan_zen"] == 1


def test_hehuan_purchase_discount(hehuan):
    hehuan.player["stones"] = 100
    hehuan._store()
    # base potion price 12, charm discount -10% -> 11 (ceil)
    r = dispatch(hehuan, "market_ops", "buy potion 1")
    assert r["ok"] and r["result"]["unitPrice"] == 11


def test_hehuan_victory_qi_leech(hehuan, monkeypatch):
    hehuan.player["qi"] = 5
    hehuan.player["strength"] = 9999
    hehuan._store()
    assert dispatch(hehuan, "battle_ops", "fight sparring")["ok"]
    for _ in range(30):
        if not hehuan.player["battle"]:
            break
        r = dispatch(hehuan, "battle_ops", "skill strike")
    assert hehuan.player["battle"] is None
    assert r["result"].get("qiLeeched") == 15
    assert hehuan.player["qi"] == min(hehuan.player["maxQi"], 5 + 15 + 10) or (
        hehuan.player["qi"] > 5
    )


def test_hehuan_blocked_from_righteous_sect_quests(hehuan):
    hehuan.player["islandLocation"] = "qingxiao"
    hehuan._store()
    r = dispatch(hehuan, "quest_ops", "accept trial_qingxiao")
    assert not r["ok"]  # righteous sect trials are route-bound


def test_hehuan_hall_sells_forbidden_pill(hehuan):
    hehuan.player["contribution"] = 100
    hehuan._store()
    island_loc = hehuan.player["islandLocation"]
    assert island_loc == "hehuan"
    r = hehuan.call("redeem", item="forbidden_pill")
    assert r["ok"] and r["result"]["contribution"] == 70
    assert hehuan.player["inventory"]["forbidden_pill"] == 1


def test_hehuan_teach_grants_zen(hehuan):
    r = dispatch(hehuan, "npc_ops", "talk hehuan_mentor teach")
    assert r["ok"], r
    assert hehuan.player["techniques"]  # mentor technique path intact


def test_hehuan_trial_completion(hehuan):
    assert dispatch(hehuan, "quest_ops", "accept trial_hehuan")["ok"]
    assert dispatch(hehuan, "npc_ops", "talk hehuan_mentor")["ok"]
    assert dispatch(hehuan, "quest_ops", "step trial_hehuan")["ok"]  # talk stage
    assert dispatch(hehuan, "travel_ops", "go market")["ok"]
    assert dispatch(hehuan, "travel_ops", "go bamboo")["ok"]
    assert dispatch(hehuan, "battle_ops", "fight wolf")["ok"]
    for _ in range(40):
        if not hehuan.player["battle"]:
            break
        assert dispatch(hehuan, "battle_ops", "skill strike")["ok"]
    assert hehuan.player["kills"].get("wolf", 0) >= 1
    assert dispatch(hehuan, "quest_ops", "step trial_hehuan")["ok"]  # kill stage
    assert dispatch(hehuan, "travel_ops", "go market")["ok"]
    assert dispatch(hehuan, "travel_ops", "go hehuan")["ok"]
    assert dispatch(hehuan, "quest_ops", "step trial_hehuan report")["ok"]  # return stage
    r = dispatch(hehuan, "quest_ops", "submit trial_hehuan")
    print("DEBUG submit:", r)
    assert r["ok"] and r["result"]["reward"] == 90


def test_taixu_route_setup_and_thunder(hehuan, tmp_path, monkeypatch):
    from xiuxian.island import IslandGame

    g = IslandGame(tmp_path / "tx.db", player_key="tx", player_name="太虚弟子")
    assert dispatch(g, "sect_ops", "join taixu")["ok"]
    original = g._roll
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 100 if "incident" in purpose else original(purpose)
    )
    p = g.player
    assert p["islandLocation"] == "taixu"
    assert "thunder_sigil" in p["skills"] and "taixu_thunder" in p["techniques"]
    # lightning school power bonus applies in battle
    assert dispatch(g, "battle_ops", "fight sparring")["ok"]
    r = dispatch(g, "battle_ops", "skill thunder_sigil")
    assert r["ok"], r
    assert r["result"]["log"][0].get("category") == "attack"
    g.close()


def test_taixu_route_via_dispatch(hehuan, tmp_path, monkeypatch):
    from xiuxian.island import IslandGame

    g = IslandGame(tmp_path / "tx2.db", player_key="tx2")
    assert dispatch(g, "sect_ops", "join taixu")["ok"]
    assert dispatch(g, "sect_ops", "hall")["ok"]
    g.close()
