"""Sect war system tests: relations web, mountain assault, ally insight."""

import pytest

from xiuxian.island import ISLAND, IslandGame
from xiuxian.mcp_dispatch import dispatch


@pytest.fixture
def war_game(tmp_path, monkeypatch):
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


def test_relations_web_complete_and_symmetric():
    import json as _json

    rel = _json.load(open("systems/xiuxian/content/routes.json", encoding="utf-8"))["sect_relations"]
    for sect in ("qingxiao", "xuanheng", "taixu", "tiangong", "canglang", "xingluo",
                 "hehuan", "youming", "fentian", "wanxiang"):
        assert sect in rel, sect
        assert "allies" in rel[sect] and "enemies" in rel[sect]
    # symmetry: if A counts B as an enemy, B counts A as an enemy too
    for sect, info in rel.items():
        for enemy in info["enemies"]:
            assert sect in rel[enemy]["enemies"], (sect, enemy)


def test_defenders_appear_only_on_enemy_ground(war_game):
    g = war_game("qingxiao", "qx")
    g.player["realm"] = "筑基"  # defenders are realm-1; juniors stay home
    g._store()
    # own sect: no defenders, only the sparring partner
    actions_local = g.available_actions()
    assert "fight" in actions_local
    enemies_local = g._local_enemies()
    assert "qingxiao_defender" not in enemies_local
    # enemy ground: the dark sect's defender shows up
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go hehuan")["ok"]
    assert "hehuan_defender" in g._local_enemies()
    # ally ground: still no defenders (they are not hostile)
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go xuanheng")["ok"]
    assert "xuanheng_defender" not in g._local_enemies()


def test_mountain_assault_rewards_and_feud(war_game):
    g = war_game("youming", "ym")
    g.player["strength"] = 9999
    g.player["realm"] = "筑基"
    g._store()
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go qingxiao")["ok"]
    rep0 = g.player["sectReputation"]
    contrib0 = g.player["contribution"]
    assert dispatch(g, "battle_ops", "fight qingxiao_defender")["ok"]
    for _ in range(40):
        if not g.player["battle"]:
            break
        r = dispatch(g, "battle_ops", "skill strike")
    assert r["result"].get("sectWar", {}).get("reputationGained") == 3
    assert g.player["sectReputation"] == rep0 + 3
    assert g.player["contribution"] == contrib0 + 3
    assert g.state["flags"]["feud:qingxiao"]["active"] is True
    # second kill same day: feud recorded, but no extra merits
    rep1 = g.player["sectReputation"]
    contrib1 = g.player["contribution"]
    assert dispatch(g, "battle_ops", "fight qingxiao_defender")["ok"]
    for _ in range(40):
        if not g.player["battle"]:
            break
        r = dispatch(g, "battle_ops", "skill strike")
    assert "sectWar" not in r["result"]
    assert g.player["sectReputation"] == rep1
    assert g.player["contribution"] == contrib1


def test_ally_cultivation_insight(war_game):
    g = war_game("qingxiao", "qx")
    cult0 = g.player["cultivation"]
    r = dispatch(g, "cultivate_ops", "meditate 2")
    assert r["ok"] and "alliedInsight" not in r["result"]  # own ground: no bonus
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go xuanheng")["ok"]  # ally ground
    r = dispatch(g, "cultivate_ops", "meditate 2")
    assert r["ok"] and r["result"]["alliedInsight"] == 4


def test_xuanheng_war_quest_full_run(war_game):
    g = war_game("xuanheng", "xh")
    g.player["strength"] = 9999
    g.player["realm"] = "筑基"
    g._store()
    assert dispatch(g, "quest_ops", "accept xuanheng_war_fentian")["ok"]
    assert dispatch(g, "npc_ops", "talk xuanheng_mentor")["ok"]
    assert dispatch(g, "quest_ops", "step xuanheng_war_fentian")["ok"]  # talk stage
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go fentian")["ok"]
    assert "fentian_defender" in g._local_enemies()
    assert dispatch(g, "battle_ops", "fight fentian_defender")["ok"]
    for _ in range(40):
        if not g.player["battle"]:
            break
        r = dispatch(g, "battle_ops", "skill strike")
    assert g.player["kills"].get("fentian_defender", 0) == 1
    assert dispatch(g, "quest_ops", "step xuanheng_war_fentian")["ok"]  # kill stage
    assert dispatch(g, "travel_ops", "go market")["ok"]
    assert dispatch(g, "travel_ops", "go xuanheng")["ok"]
    assert dispatch(g, "quest_ops", "step xuanheng_war_fentian report")["ok"]  # return
    r = dispatch(g, "quest_ops", "submit xuanheng_war_fentian")
    assert r["ok"] and r["result"]["reward"] == 90
