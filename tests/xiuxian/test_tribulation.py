"""Inner-demon gate and lightning tribulation for cross-realm breakthroughs.

每次 call 都会重新装载 state，断言前一律重新取 g.player。
"""

import pytest

from xiuxian.island import IslandGame


@pytest.fixture
def g(tmp_path):
    game = IslandGame(tmp_path / "trib.db", player_key="test", player_name="渡劫修士")
    game.call("choose_route", route="qingxiao")
    yield game
    game.close()


REALM_INDEX = {"炼气": 0, "筑基": 1, "金丹": 2, "元婴": 3}


def prepare(g, realm="金丹", pill="soul_pill"):
    p = g.player
    p.update(realm=realm, stage=3, cultivation=1000, reputation=50)
    # 按境界补足气血上限，避免低上限干扰渡劫结算。
    p["max_hp"] = 100 + 20 * (REALM_INDEX[realm] * 4 + 3)
    p["techniques"] = ["basic_meditation"]
    p["method"] = "basic_meditation"
    p["inventory"][pill] = p["inventory"].get(pill, 0) + 1
    p["hp"] = p["max_hp"]
    p["qi"] = p["maxQi"]
    p["statusEffects"] = []
    p["cooldownUntil"] = 0
    p["tribulation"] = None
    g._store()


def clear_battle(g, skill="strike"):
    for _ in range(120):
        if not g.player["battle"]:
            return
        assert g.call("use_skill", skill=skill)["ok"]
    assert g.player["battle"] is None, "battle did not conclude"


def test_cross_realm_breakthrough_opens_demon_battle(g, monkeypatch):
    monkeypatch.setattr(g, "_roll", lambda purpose: 1)
    prepare(g)
    p = g.player
    stats = g._stats(p)
    r = g.call("breakthrough")
    p = g.player
    assert r["ok"]
    battle = r["result"]
    assert battle["kind"] == "demon" and battle["target"] == "inner_demon"
    assert battle["enemy"]["name"].endswith("的心魔")
    assert battle["enemy"]["hp"] == int(p["max_hp"] * 1.15) + 5
    assert battle["enemy"]["strength"] == int(stats["strength"] * 0.75)
    assert battle["enemy"]["skills"]  # 心魔会用本主会的招式
    # 修为未扣，突破材料在开劫时已投入。
    assert p["cultivation"] == 1000
    assert p["inventory"]["soul_pill"] == 0
    clear_battle(g)
    p = g.player
    assert p["realm"] == "金丹"
    assert p["tribulation"]["phase"] == "lightning"


def test_demon_battle_steals_qi(g, monkeypatch):
    monkeypatch.setattr(g, "_roll", lambda purpose: 1)
    prepare(g)
    g.call("breakthrough")
    p = g.player
    qi_before = p["qi"]
    enemy_before = p["battle"]["enemy"]["qi"]
    g.call("use_skill", skill="strike")
    p = g.player
    assert p["qi"] < qi_before
    assert p["battle"]["enemy"]["qi"] >= enemy_before
    clear_battle(g)


def test_fleeing_demon_fails_breakthrough(g, monkeypatch):
    # 打不中心魔时脱身：修为重创、冷却一天、留下伤势、劫印清除。
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 100 if purpose == "hit" else 1
    )
    prepare(g)
    g.call("breakthrough")
    while g.player["battle"]:
        assert g.call("retreat")["ok"]
    p = g.player
    assert p["realm"] == "金丹"
    assert p["cultivation"] == 1000 - (60 * 4) // 3
    assert p["tribulation"] is None
    assert any(e["type"] == "injury" for e in p["statusEffects"])
    assert p["cooldownUntil"] > g.state["minutes"]


def test_golden_core_to_nascent_soul_needs_lightning(g, monkeypatch):
    monkeypatch.setattr(g, "_roll", lambda purpose: 1)
    prepare(g)
    g.call("breakthrough")
    clear_battle(g)
    p = g.player
    # 心魔已破但未升境；再次突破引雷。
    assert p["realm"] == "金丹"
    assert p["tribulation"]["phase"] == "lightning"
    r = g.call("breakthrough")
    p = g.player
    assert r["ok"]
    assert r["result"]["kind"] == "tribulation"
    assert r["result"]["target"] == "tribulation"
    # 雷劫中不许用普通招式，也不许撤退。
    assert not g.call("use_skill", skill="strike")["ok"]
    assert not g.call("retreat")["ok"]
    for wave in range(3):
        assert g.player["battle"]["round"] == wave
        assert g.call("use_skill", skill="trib_ward")["ok"]
    p = g.player
    assert p["battle"] is None
    assert p["realm"] == "元婴"
    assert p["tribulation"] is None


def test_lightning_temper_grants_bonus_and_deepens_bolt(g, monkeypatch):
    monkeypatch.setattr(g, "_roll", lambda purpose: 1)
    prepare(g)
    g.call("breakthrough")
    clear_battle(g)
    p = g.player
    base_strength = p["strength"]
    base_max_qi = p["maxQi"]
    g.call("breakthrough")
    temper_hits = 0
    for wave in range(3):
        assert g.player["battle"]["kind"] == "tribulation"
        if wave < 2:
            # 前两重引雷淬体：成功渡劫后属性额外增长，但当轮雷伤加深。
            result = g.call("use_skill", skill="trib_temper")["result"]
            temper_hits += 1
            assert any(e.get("temper") for e in result["log"])
        else:
            assert g.call("use_skill", skill="trib_ward")["ok"]
    p = g.player
    assert p["battle"] is None and p["realm"] == "元婴"
    assert p["strength"] == base_strength + 3 + 2 * temper_hits
    assert p["maxQi"] == base_max_qi + 10 + 5 * temper_hits


def test_tribulation_skills_banned_outside_ritual(g, monkeypatch):
    monkeypatch.setattr(g, "_roll", lambda purpose: 1)
    prepare(g, realm="筑基", pill="golden_pill")
    g.call("breakthrough")
    clear_battle(g)
    prepare(g)
    g.call("breakthrough")
    # 心魔战中禁用御劫之法。
    assert not g.call("use_skill", skill="trib_ward")["ok"]
    clear_battle(g)


def test_demon_battle_persists_across_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(
        IslandGame, "_roll", lambda self, purpose: 100 if purpose == "hit" else 1
    )
    path = tmp_path / "persist.db"
    g = IslandGame(path, player_key="s", player_name="渡劫修士")
    g.call("choose_route", route="qingxiao")
    prepare(g)
    g.call("breakthrough")
    assert g.player["battle"]["kind"] == "demon"
    g.close()
    g2 = IslandGame(path, player_key="s")
    assert g2.player["battle"]["kind"] == "demon"
    assert g2.player["battle"]["enemy"]["name"].endswith("的心魔")
    # 劫机未逝，继续再战仍可突破。
    while g2.player["battle"]:
        assert g2.call("retreat")["ok"]
    assert g2.player["tribulation"] is None
    g2.close()


def test_minor_stage_breakthrough_unchanged(g, monkeypatch):
    monkeypatch.setattr(g, "_roll", lambda purpose: 1)
    p = g.player
    p.update(stage=0, cultivation=100)
    p["techniques"] = ["basic_meditation"]
    p["method"] = "basic_meditation"
    p["hp"] = p["max_hp"]
    p["statusEffects"] = []
    p["cooldownUntil"] = 0
    g._store()
    r = g.call("breakthrough")
    p = g.player
    assert r["ok"] and r["result"]["success"]
    assert p["stage"] == 1 and p["battle"] is None
    assert p["tribulation"] is None
