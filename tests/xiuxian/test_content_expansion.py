"""Tests for the world-expansion batch: shard loader, new enemies, recipes,
equipment, realm loot."""

import json

import pytest

from xiuxian.data import load_pack
from xiuxian.engine import CONTENT
from xiuxian.island import ISLAND, IslandGame
from xiuxian.mcp_dispatch import dispatch


def test_shard_loader_merges_domains():
    content = load_pack("content")
    island = load_pack("island")
    # every domain key from the monolith era is present after the split
    for key in ("routes", "skills", "items", "recipes", "enemies", "techniques",
                "locations", "quests", "sect_hall", "birth", "realms", "beasts"):
        assert key in content, key
    for key in ("name", "locations", "npcs", "quests", "villains", "incidents", "events"):
        assert key in island, key
    assert CONTENT["enemies"]["heart_guardian"]["realm"] == 2
    assert ISLAND["locations"]["heart_island"]["requiredRealm"] == 2


def test_new_recipe_crafts_tide_pill(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "craft.db", player_key="alc")
    assert dispatch(g, "sect_ops", "join danxia")["ok"]
    g.player["inventory"].update({"herb": 10, "tide_dew": 2})
    g._store()
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 100 if "incident" in purpose else 1
    )  # craft always succeeds
    r = dispatch(g, "refine_ops", "pill tide_pill 1")
    assert r["ok"], r
    made = sum(n for k, n in r["result"]["produced"].items() if k.startswith("tide_pill"))
    assert made == 1  # danxia quality roll may promote it, still a tide pill
    g.close()


def test_new_forge_recipe_makes_heavy_sword(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "forge.db", player_key="smith")
    assert dispatch(g, "sect_ops", "join tiangong")["ok"]
    g.player["inventory"].update({"iron": 10, "core": 2})
    g._store()
    monkeypatch.setattr(g, "_roll", lambda purpose: 100 if "incident" in purpose else 1)
    r = dispatch(g, "refine_ops", "weapon heavy_sword 1")
    assert r["ok"], r
    assert g.player["inventory"].get("heavy_sword") == 1
    g.close()


def test_new_equip_grants_boosted_stats(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "equip.db", player_key="wear")
    assert dispatch(g, "sect_ops", "join tiangong")["ok"]
    g.player["inventory"]["cold_jade"] = 2
    g._store()
    monkeypatch.setattr(g, "_roll", lambda purpose: 100 if "incident" in purpose else 1)
    assert dispatch(g, "refine_ops", "craft cold_jade_pendant 1")["ok"]
    plain = g._stats(g.player)["spirit"]
    assert g.call("use_item", item="cold_jade_pendant")["ok"]
    boosted = g._stats(g.player)["spirit"]
    assert boosted == plain + 7 + 7 * 40 // 100  # spirit 7 with +40% gear power
    g.close()


def test_new_enemy_young_viper_fight(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "viper.db", player_key="hunter")
    assert dispatch(g, "sect_ops", "join fuyao")["ok"]
    g.player["strength"] = 9999
    g._store()
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go bamboo")["ok"]
    assert dispatch(g, "battle_ops", "fight young_viper")["ok"]
    for _ in range(40):
        if not g.player["battle"]:
            break
        r = dispatch(g, "battle_ops", "skill strike")
    assert g.player["kills"].get("young_viper", 0) == 1
    assert g.player["inventory"].get("tide_dew", 0) >= 1  # its drop
    g.close()


def test_heart_island_boss_gate_and_fight(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "heart.db", player_key="challenger")
    assert dispatch(g, "sect_ops", "join taixu")["ok"]
    g.player["strength"] = 9999
    g.player["max_hp"] = 9999
    g.player["hp"] = 9999
    g._store()
    # 金丹 gate: a 筑基 challenger cannot even reach the island heart
    g.player["realm"] = "筑基"
    g._store()
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go lake")["ok"]
    r = dispatch(g, "travel_ops", "go heart_island")
    assert not r["ok"]  # requiredRealm 2
    g.player["realm"] = "金丹"
    g._store()
    assert dispatch(g, "travel_ops", "go heart_island")["ok"]
    assert dispatch(g, "battle_ops", "fight heart_guardian")["ok"]
    for _ in range(60):
        if not g.player["battle"]:
            break
        r = dispatch(g, "battle_ops", "skill strike")
    assert g.player["kills"].get("heart_guardian", 0) == 1
    assert g.player["inventory"].get("thunderstone", 0) >= 2  # boss drop
    g.close()


def test_new_events_present_in_rotation_pool():
    ids = {e["id"] for e in CONTENT["events"]}
    assert {"thunderstorm", "blossom"} <= ids
