"""Gameplay expansion tests: contribution hall, beast evolution, realm loot."""

import pytest

from xiuxian.island import IslandGame
from xiuxian.mcp_dispatch import dispatch


@pytest.fixture
def island(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "play.db", player_key="test", player_name="玩法修士")
    assert g.call("choose_route", route="qingxiao")["ok"]
    original = g._roll
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 100 if "incident" in purpose else original(purpose)
    )
    yield g
    g.close()


@pytest.fixture
def beast_island(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "beast.db", player_key="beast", player_name="御兽修士")
    assert dispatch(g, "sect_ops", "join fuyao")["ok"]
    original = g._roll
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 100 if "incident" in purpose else original(purpose)
    )
    yield g
    g.close()


def make_pet(g, level=3, crystals=0, stones=500, evolution=None):
    r = dispatch(g, "npc_ops", "beast contract cloud_fox")
    assert r["ok"], r
    pet = g.player["beast"]
    pet["level"] = level
    pet["xp"] = level * 5000
    pet["evolution"] = evolution
    if crystals:
        g.player["inventory"]["evolution_crystal"] = crystals
    g.player["stones"] = stones
    g._store()
    return pet


# ---- contribution hall ----

def test_sect_hall_lists_catalog_and_contribution(island):
    island.player["contribution"] = 37
    island._store()
    r = island.call("sect_hall")
    assert r["ok"] and r["result"]["contribution"] == 37
    assert r["result"]["catalog"]["evolution_crystal"] == 45


def test_redeem_deducts_contribution_and_adds_items(island):
    island.player["contribution"] = 100
    island._store()
    r = island.call("redeem", item="core", amount=2)
    assert r["ok"]
    assert r["result"]["cost"] == 24 and r["result"]["contribution"] == 76
    assert island.player["inventory"]["core"] == 2


def test_redeem_rejects_insufficient_contribution(island):
    island.player["contribution"] = 5
    island._store()
    assert not island.call("redeem", item="core")["ok"]
    assert island.player["contribution"] == 5
    assert "core" not in island.player["inventory"]


def test_redeem_requires_own_sect_location(island):
    island.player["contribution"] = 100
    island._store()
    assert dispatch(island, "travel_ops", "go market")["ok"]
    assert not island.call("redeem", item="core")["ok"]
    assert dispatch(island, "travel_ops", "go qingxiao")["ok"]
    assert island.call("redeem", item="core")["ok"]


def test_redeem_rejects_rogue_and_unknown_item(tmp_path):
    g = IslandGame(tmp_path / "rogue.db", player_key="rogue1")
    g.call("choose_route", route="rogue")
    g.player["contribution"] = 100
    g._store()
    assert not g.call("redeem", item="core")["ok"]  # rogue has no sect hall
    assert not g.call("redeem", item="fang")["ok"]  # owned item, not in catalog
    g.close()


def test_dispatch_hall_and_redeem(island):
    island.player["contribution"] = 50
    island._store()
    assert dispatch(island, "sect_ops", "hall")["ok"]
    r = dispatch(island, "sect_ops", "redeem core 1")
    assert r["ok"] and r["result"]["contribution"] == 38


# ---- beast evolution ----

def test_evolve_awaken_uses_crystals_and_stones(beast_island):
    pet = make_pet(beast_island, level=3, crystals=2, stones=500)
    max_hp0, str0 = pet["maxHp"], pet["strength"]
    r = dispatch(beast_island, "npc_ops", "beast evolve")
    assert r["ok"], r
    pet = beast_island.player["beast"]
    assert pet["evolution"] == "灵醒"
    assert pet["maxHp"] == max_hp0 + 20 and pet["strength"] == str0 + 3
    assert beast_island.player["inventory"]["evolution_crystal"] == 1
    assert beast_island.player["stones"] == 450


def test_evolve_form_requires_awakened_stage(beast_island):
    make_pet(beast_island, level=6, crystals=4, stones=600, evolution="灵醒")
    r = dispatch(beast_island, "npc_ops", "beast evolve")
    assert r["ok"], r
    assert beast_island.player["beast"]["evolution"] == "化形"
    assert beast_island.player["inventory"]["evolution_crystal"] == 1


def test_evolve_gates(island=None, beast_island=None):
    """Placeholder replaced by explicit tests below."""


def test_evolve_rejects_low_level_and_missing_crystals(beast_island):
    make_pet(beast_island, level=1, crystals=5, stones=500)
    assert not dispatch(beast_island, "npc_ops", "beast evolve")["ok"]  # level gate
    pet = beast_island.player["beast"]
    pet["level"] = 3
    beast_island.player["inventory"]["evolution_crystal"] = 0
    beast_island._store()
    assert not dispatch(beast_island, "npc_ops", "beast evolve")["ok"]  # no crystals
    assert beast_island.player["beast"].get("evolution") is None


def test_evolve_rejects_final_stage(beast_island):
    make_pet(beast_island, level=6, crystals=4, stones=600, evolution="灵醒")
    assert dispatch(beast_island, "npc_ops", "beast evolve")["ok"]  # 灵醒 -> 化形
    beast_island.player["beast"]["level"] = 9
    beast_island.player["inventory"]["evolution_crystal"] = 5
    beast_island._store()
    r = dispatch(beast_island, "npc_ops", "beast evolve")
    assert not r["ok"] and "化形" in r["error"]


def test_evolve_rejects_injured_beast(beast_island):
    make_pet(beast_island, level=3, crystals=1, stones=500)
    beast_island.player["beast"]["injuries"] = 1
    beast_island._store()
    assert not dispatch(beast_island, "npc_ops", "beast evolve")["ok"]


def test_formed_beast_combo_in_battle(beast_island, monkeypatch):
    make_pet(beast_island, level=6, crystals=4, stones=600, evolution="灵醒")
    assert dispatch(beast_island, "npc_ops", "beast evolve")["ok"]
    assert beast_island.player["beast"]["evolution"] == "化形"
    monkeypatch.setattr(
        beast_island,
        "_roll",
        lambda purpose: 100 if "incident" in purpose else 1,  # hit and combo
    )
    assert dispatch(beast_island, "travel_ops", "go market")["ok"]
    assert dispatch(beast_island, "travel_ops", "go bamboo")["ok"]
    assert dispatch(beast_island, "battle_ops", "fight wolf")["ok"]
    for _ in range(50):
        if not beast_island.player["battle"]:
            break
        r = dispatch(beast_island, "battle_ops", "skill strike")
        if any(e.get("skill") == "combo" for e in r["result"]["log"]):
            break
    else:
        pytest.fail("formed beast never landed a combo")


# ---- realm tide loot ----

def test_realm_chest_drops_evolution_crystal(island, monkeypatch):
    island.player["realm"] = "筑基"
    island.player["cultivation"] = 9999
    island.player["hp"] = island.player["max_hp"]
    island._store()
    assert dispatch(island, "travel_ops", "go market")["ok"]
    assert dispatch(island, "travel_ops", "go lake")["ok"]
    assert dispatch(island, "travel_ops", "go secret 古殿")["ok"]
    original = island._roll
    monkeypatch.setattr(
        island,
        "_roll",
        lambda purpose: 100
        if "incident" in purpose
        else {"explore": 4, "adventure": 100, "detect_anomaly": 100}.get(
            purpose, original(purpose)
        ),
    )
    r = dispatch(island, "travel_ops", "explore")
    assert r["ok"], r
    # exploration[3] is 'chest'; loot carries the tide crystal
    assert r["result"].get("loot", {}).get("evolution_crystal") == 1
    assert island.player["inventory"]["evolution_crystal"] == 1


def test_world_chest_outside_realm_stays_unchanged(island, monkeypatch):
    assert dispatch(island, "travel_ops", "go bamboo")["ok"]
    original = island._roll
    monkeypatch.setattr(
        island,
        "_roll",
        lambda purpose: 100
        if "incident" in purpose
        else {"explore": 4, "adventure": 100}.get(purpose, original(purpose)),
    )
    r = dispatch(island, "travel_ops", "explore")
    assert r["ok"]
    assert "evolution_crystal" not in r["result"].get("loot", {})
