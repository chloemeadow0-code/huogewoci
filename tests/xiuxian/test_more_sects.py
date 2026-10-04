"""Mechanism tests for the six expansion sects."""

import pytest

from xiuxian.island import IslandGame
from xiuxian.mcp_dispatch import dispatch


@pytest.fixture
def game_for(tmp_path, monkeypatch):
    def _make(route, key):
        g = IslandGame(tmp_path / (route + ".db"), player_key=key)
        assert dispatch(g, "sect_ops", "join " + route)["ok"]
        original = g._roll
        monkeypatch.setattr(
            g,
            "_roll",
            lambda purpose: 100 if "incident" in purpose else original(purpose),
        )
        return g

    return _make


def fight_once(g, monkeypatch, hp):
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 1 if purpose == "hit" else 100
    )  # always land, no ailments
    g.player["strength"] = 50
    g.player["max_hp"] = 100
    g.player["hp"] = hp
    g._store()
    assert dispatch(g, "battle_ops", "fight sparring")["ok"]
    damage = None
    for _ in range(30):
        if not g.player["battle"]:
            break
        r = dispatch(g, "battle_ops", "skill strike")
        for e in r["result"]["log"]:
            if e.get("damage"):
                damage = max(damage or 0, e["damage"])
    return damage


def test_youming_desperation_power(game_for, monkeypatch):
    g = game_for("youming", "ym")
    normal = fight_once(g, monkeypatch, 90)  # above the 30% line
    desperate = fight_once(g, monkeypatch, 20)  # below it: 借煞
    assert desperate >= normal + normal // 3  # +60% power shows through floors


def test_wanxiang_sell_premium(game_for):
    g = game_for("wanxiang", "wx")
    g.player["inventory"]["fang"] = 1
    g._store()
    # fang base 6 -> sell floor 3 -> +50% premium = 4 (floor 4.5)
    r = dispatch(g, "market_ops", "sell fang 1")
    assert r["ok"] and r["result"]["unitPrice"] == 4


def test_tiangong_equipment_power(game_for):
    g = game_for("tiangong", "tg")
    g.player["inventory"]["sword"] = 1
    g._store()
    g.call("use_item", item="sword")  # equips, strength effect +8
    boosted = g._stats(g.player)["strength"]
    plain = 16 + 8  # base strength 16 + sword 8 without boost
    assert boosted == plain + 8 * 40 // 100  # +40% equipment power


def test_canglang_escape_bonus(game_for, monkeypatch):
    g = game_for("canglang", "cl")
    g._store()
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go bamboo")["ok"]
    assert dispatch(g, "battle_ops", "fight wolf")["ok"]
    monkeypatch.setattr(g, "_roll", lambda purpose: 70)  # 60 base fails, 80 bonus passes
    r = g.call("retreat")
    assert r["ok"] and g.player["battle"] is None and r["result"]["outcome"] == "escaped"


def test_fentian_ignite_on_hit(game_for, monkeypatch):
    g = game_for("fentian", "ft")
    g._store()
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go bamboo")["ok"]
    assert dispatch(g, "battle_ops", "fight wolf")["ok"]
    monkeypatch.setattr(g, "_roll", lambda purpose: 1)  # hit and ignite
    r = dispatch(g, "battle_ops", "skill cinder_fist")
    assert r["ok"]
    assert r["result"]["log"][0].get("ailment") == "burn"


def test_xingluo_bounty_first_kill_only(game_for):
    g = game_for("xingluo", "xl")
    g.player["strength"] = 9999
    g._store()
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go bamboo")["ok"]
    assert dispatch(g, "battle_ops", "fight wolf")["ok"]
    for _ in range(40):
        if not g.player["battle"]:
            break
        r = dispatch(g, "battle_ops", "skill strike")
    first = r["result"]
    assert first.get("bounty") == 8
    stones = g.player["stones"]
    assert dispatch(g, "battle_ops", "fight wolf")["ok"]
    for _ in range(40):
        if not g.player["battle"]:
            break
        r = dispatch(g, "battle_ops", "skill strike")
    assert "bounty" not in r["result"]
    assert g.player["stones"] == stones + r["result"]["stones"]


def test_all_new_sect_trials_are_sect_bound(game_for, tmp_path):
    from xiuxian.island import ISLAND

    g = game_for("youming", "ym2")
    g.player["islandLocation"] = "qingxiao"
    g._store()
    r = dispatch(g, "quest_ops", "accept trial_qingxiao")
    assert not r["ok"]  # righteous trials closed to dark sects
    assert ISLAND["quests"]["trial_wanxiang"]["sect"] == "wanxiang"


def test_dispatch_join_every_new_sect(game_for):
    for route in ("youming", "wanxiang", "tiangong", "canglang", "fentian", "xingluo"):
        g = game_for(route, "join_" + route)
        assert dispatch(g, "sect_ops", "hall")["ok"]
        g.close()
