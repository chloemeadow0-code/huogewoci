"""Route mechanics exercised through the same transactional player facade."""

import copy
import pytest
from xiuxian.engine import Game, CONTENT, TOOLS


@pytest.fixture
def make_game(tmp_path):
    opened = []

    def create(route, key=None):
        g = Game(tmp_path / ((key or route) + ".db"), player_key=key or route)
        assert g.call("choose_route", route=route)["ok"]
        # Compare route modifiers with identical base aptitude.
        g.player["aptitude"] = 2
        g._store()
        opened.append(g)
        return g

    yield create
    for g in opened:
        g.close()


def force_rolls(g, monkeypatch, values=None, default=1):
    values = values or {}
    monkeypatch.setattr(g, "_roll", lambda purpose: values.get(purpose, default))


def test_new_character_must_choose_and_once(tmp_path):
    g = Game(tmp_path / "new.db")
    before = copy.deepcopy(g.state)
    assert not g.call("cultivate")["ok"]
    assert g.state == before
    assert set(g.call("get_world")["result"]["routes"]) == set(CONTENT["routes"])
    assert g.call("choose_route", route="xuanheng")["ok"]
    flags = g.player["inventory"]["array_flag"]
    assert not g.call("choose_route", route="qingxiao")["ok"]
    assert g.player["inventory"]["array_flag"] == flags
    g.close()


@pytest.mark.parametrize("route", CONTENT["routes"])
def test_each_route_persists(make_game, route):
    g = make_game(route)
    g.call("cultivate", duration=1)
    other = Game(g.path, player_key=route)
    assert other.player["route"] == route
    assert other.player["sect"] == (
        None if route == "rogue" else CONTENT["routes"][route]["name"]
    )
    assert other.player["techniques"] == g.player["techniques"]
    other.close()


def test_sword_momentum_third_attack(make_game, monkeypatch):
    g = make_game("qingxiao")
    force_rolls(g, monkeypatch)
    g.call("fight", target="sparring")
    r1 = g.call("use_skill", skill="strike")["result"]
    r2 = g.call("use_skill", skill="strike")["result"]
    assert not r1["swordMomentum"]
    assert r2["swordMomentum"]
    r3 = g.call("use_skill", skill="strike")["result"]
    own = r3["log"][0]
    assert own["momentumUsed"]
    assert own["damage"] > r1["log"][0]["damage"]
    assert not r3["swordMomentum"]
    assert r1["proficiencyGained"] == 1150


def test_sword_streak_broken_by_defense_and_control(make_game, monkeypatch):
    g = make_game("qingxiao")
    force_rolls(g, monkeypatch)
    g.call("fight", target="sparring")
    g.call("use_skill", skill="strike")
    g.call("use_skill", skill="guard")
    assert not g.call("use_skill", skill="strike")["result"]["swordMomentum"]
    g.player["battle"]["swordMomentum"] = True
    g._effect(g.player, "stun", 1, 3, "test")
    g._store()
    r = g.call("use_skill", skill="strike")["result"]
    assert not r["swordMomentum"]
    assert r["log"][0]["skipped"] == "controlled"


@pytest.mark.parametrize(
    "formation,effect",
    [
        ("ward", "shield"),
        ("snare", "slow"),
        ("gather", "qi_regen"),
        ("kill", "firstDamage"),
    ],
)
def test_prearray_unique_and_fixed_effect(make_game, formation, effect):
    g = make_game("xuanheng")
    g.call("prepare_formation", formation=formation)
    assert not g.call("prepare_formation", formation="kill")["ok"]
    g.call("fight", target="sparring")
    b = g.player["battle"]
    assert b["formation"] == formation
    assert g.player["preparedFormation"] is None
    if effect == "firstDamage":
        assert b["firstDamage"] == 9
    else:
        actor = b["enemy"] if effect == "slow" else g.player
        assert any(e["type"] == effect for e in actor["statusEffects"])


def test_prearray_does_not_apply_to_surprise(make_game, monkeypatch):
    g = make_game("xuanheng")
    g.call("travel", destination="wild")
    g.call("prepare_formation", formation="ward")
    # An event discovered through explore is a real surprise encounter.
    force_rolls(g, monkeypatch, {"adventure": 100, "explore": 2, "encounter": 1})
    r = g.call("explore")
    assert r["ok"]
    assert g.player["battle"]["surprise"]
    assert g.player["battle"]["formation"] is None
    assert not any(e["type"] == "shield" for e in g.player["statusEffects"])


def test_surprise_damage_and_material_fraction(make_game, monkeypatch):
    g = make_game("xuanheng")
    force_rolls(g, monkeypatch)
    g.player["inventory"]["array_flag"] = 20
    g._store()
    g.call("fight", target="sparring")
    g.player["battle"]["surprise"] = True
    g._store()
    r = g.call("use_skill", skill="array_bolt")
    assert r["ok"]
    assert r["result"]["log"][0]["damage"] == (16 * 115 // 100) * 90 // 100
    costs = [g._material_cost("iron", 1, 10) for _ in range(10)]
    assert sum(costs) == 11


def test_disarm_anomaly_and_protected_route_quest(make_game, monkeypatch):
    g = make_game("xuanheng")
    g.call("accept_quest", quest="disarm")
    assert not g.call("accept_quest", quest="escort")["ok"]
    g.player["realm"] = "筑基"
    g.player["location"] = "wild"
    g._store()
    g.call("travel", destination="realm")
    force_rolls(g, monkeypatch, {"detect_anomaly": 30, "disarm": 65})
    r = g.call("explore")
    assert r["result"]["event"] == "anomaly"
    assert r["result"]["disarm"] == {"chance": 70, "success": True}
    g.call("travel", destination="wild")
    g.call("travel", destination="sect")
    assert g.call("submit_quest", quest="disarm")["ok"]


@pytest.mark.parametrize(
    "quality_roll,quality,expected",
    [
        (5, "superior", "potion_superior"),
        (20, "fine", "potion_fine"),
        (80, "ordinary", "potion"),
    ],
)
def test_dan_quality_genuine_items(
    make_game, monkeypatch, quality_roll, quality, expected
):
    g = make_game("danxia")
    force_rolls(g, monkeypatch, {"pill_quality": quality_roll})
    r = g.call("craft", recipe="potion")
    assert r["ok"]
    assert r["result"]["produced"] == {expected: 1}
    assert r["result"]["successChance"] == 100
    assert CONTENT["prices"][expected] >= CONTENT["prices"]["potion"]


def test_dan_pill_effect_side_effect_and_healing(make_game, monkeypatch):
    g = make_game("danxia")
    force_rolls(g, monkeypatch)
    p = g.player
    p["hp"] = 10
    p["qi"] = 0
    p["inventory"]["potion_superior"] = 1
    g._store()
    g.call("use_item", item="potion_superior")
    assert g.player["hp"] == 79
    assert g.player["qi"] == 34
    assert g.player["statusEffects"][0]["value"] == 2
    g.call("retreat", duration=8)
    g.call("fight", target="sparring")
    g.player["hp"] = 50
    g._store()
    r = g.call("use_skill", skill="heal")["result"]
    assert r["hp"] == 65


def test_dan_attack_penalty_and_furnace_explosion(make_game, monkeypatch):
    g = make_game("danxia")
    force_rolls(g, monkeypatch)
    g.call("fight", target="sparring")
    assert g.call("use_skill", skill="strike")["result"]["log"][0]["damage"] == 11
    g.player["battle"] = None
    g.player["inventory"].update(herb=20, core=5)
    g._store()
    force_rolls(g, monkeypatch, {"craft": 100, "furnace": 1})
    r = g.call("craft", recipe="golden_pill")
    assert r["ok"]
    assert r["result"]["furnaceDamage"] > 0
    assert r["result"]["outcomes"][0]["outcome"] == "exploded"
    assert g.player["hp"] > 0


def test_forging_and_alchemy_negative_apply_even_without_main_discipline(make_game):
    d = make_game("danxia")
    d.player["inventory"]["iron"] = 3
    d._store()
    assert d.call("craft", recipe="sword")["result"]["successChance"] == 85
    f = make_game("fuyao")
    assert f.call("craft", recipe="potion")["result"]["successChance"] == 87
    q = make_game("qingxiao")
    assert q._gain_proficiency("general", 1000, "production") == 900


@pytest.mark.parametrize("target,expected", [("wolf", 15), ("bandit", 12)])
def test_fuy_beast_damage_only(make_game, monkeypatch, target, expected):
    g = make_game("fuyao")
    force_rolls(g, monkeypatch)
    g.call("travel", destination="wild")
    g.call("fight", target=target)
    r = g.call("use_skill", skill="strike")["result"]
    assert r["log"][0]["damage"] == expected


def test_fuy_injury_tracking_prices(make_game, monkeypatch):
    g = make_game("fuyao")
    g.call("travel", destination="town")
    assert g.call("trade", item="herb")["result"]["unitPrice"] == 5
    g.call("travel", destination="wild")
    force_rolls(
        g,
        monkeypatch,
        {
            "tracking": 70,
            "adventure": 100,
            "explore": 5,
            "disarm": 100,
            "explore_injury": 25,
        },
    )
    assert g.call("track", target="wolf")["result"]["success"]
    before = g.player["hp"]
    r = g.call("explore")
    assert r["result"]["injuryChance"] == 20
    assert g.player["hp"] == before


def test_beast_independent_actions_growth_loyalty(make_game, monkeypatch):
    g = make_game("fuyao")
    force_rolls(g, monkeypatch)
    assert g.call("manage_beast", action="contract", beast="stone_ape")["ok"]
    assert not g.call("manage_beast", action="contract", beast="cloud_fox")["ok"]
    assert g.call("manage_beast", action="feed")["result"]["xp"] == 1200
    g.call("fight", target="sparring")
    r = g.call("use_skill", skill="strike")
    assert any(e["actor"] == "beast" and e["damage"] > 0 for e in r["result"]["log"])
    assert g.player["beast"]["xp"] == 1440
    assert g.player["beast"]["hp"] < g.player["beast"]["maxHp"]
    g.player["battle"] = None
    g._store()
    for _ in range(3):
        g.call("manage_beast", action="abuse")
    assert g.player["beast"] is None
    assert g.player["conduct"]["violations"]


def test_beast_starvation_across_restart(make_game):
    g = make_game("fuyao")
    g.call("manage_beast", action="contract", beast="cloud_fox")
    for _ in range(3):
        g.call("cultivate", duration=72)
    assert g.player["beast"] is None
    fresh = Game(g.path, player_key="fuyao")
    assert fresh.player["beast"] is None
    assert any(h["action"] == "beast_release" for h in fresh.player["history"])
    fresh.close()


def test_beast_force_and_release_registration(make_game):
    g = make_game("fuyao")
    g.call("manage_beast", action="contract", beast="cloud_fox")
    g.call("travel", destination="wild")
    assert not g.call("manage_beast", action="release")["ok"]
    g.call("travel", destination="sect")
    assert g.call("manage_beast", action="release")["result"]["registered"]


def test_rogue_costs_free_heal_absent_and_directions(make_game):
    g = make_game("rogue")
    p = g.player
    p["stones"] = 1000
    p["credibility"]["market"] = 3
    g._store()
    assert not g.call("travel", destination="sect")["ok"]
    assert g.call("trade", item="potion")["result"]["unitPrice"] == 13
    before = g.player["stones"]
    assert g.call("retreat", duration=8)["result"]["cost"] == 16
    assert g.player["stones"] == before - 16
    for t in ("qingxiao_sword", "danxia_herbal", "xuanheng_array", "beast_lore"):
        assert g.call("learn_technique", technique=t)["ok"]
    assert len(g.player["mainDisciplines"]) == 4
    assert g._discipline_rate("sword") == 60
    assert not g.call("learn_technique", technique="fuyao_body")["ok"]
    assert g.call("manage_beast", action="contract", beast="cloud_fox")["ok"]


def test_sect_direction_limit_and_cross_penalty(make_game):
    g = make_game("qingxiao")
    assert g.call("learn_technique", technique="verdant")["ok"]
    assert g._discipline_rate("medicine") == 80
    g.player["stones"] = 100
    g._store()
    assert not g.call("learn_technique", technique="danxia_herbal")["ok"]


def test_rogue_breakthrough_surcharge(make_game, monkeypatch):
    g = make_game("rogue")
    force_rolls(g, monkeypatch)
    p = g.player
    p.update(stage=3, cultivation=500, reputation=20, stones=20)
    p["inventory"]["foundation_pill"] = 1
    g._store()
    assert g.call("breakthrough")["ok"]
    assert g.player["stones"] == 8
    for _ in range(80):
        if not g.player["battle"]:
            break
        assert g.call("use_skill", skill="strike")["ok"]
    assert g.player["realm"] == "筑基"
    assert g.player["stones"] == 8


def test_rogue_blackmarket_and_adventure_probabilities(make_game, monkeypatch):
    g = make_game("rogue")
    force_rolls(g, monkeypatch, {"blackmarket_stock": 30, "adventure": 20})
    g.call("travel", destination="town", node="黑市")
    assert g.player["blackmarket"]["stock"] == CONTENT["blackmarket_stock"]
    g.call("travel", destination="wild")
    r = g.call("explore")
    assert r["result"]["event"] == "adventure"
    assert g.player["inventory"]["relic_fragment"] == 1
    fresh = Game(g.path, player_key="rogue")
    assert fresh.player["credibility"] == g.player["credibility"]
    fresh.close()


def test_reputation_bonus_and_men_rules(make_game, monkeypatch):
    g = make_game("qingxiao")
    g.call("accept_quest", quest="escort")
    g.player["kills"]["bandit"] = 1
    g._store()
    assert g.call("submit_quest", quest="escort")["result"]["reputation"] == 12
    g.player["inventory"]["forbidden_sword"] = 1
    g._store()
    assert g.call("use_item", item="forbidden_sword")["ok"]
    assert g.player["conduct"]["violations"][-1]["reason"] == "私修禁录邪剑"
    f = make_game("fuyao")
    f.call("travel", destination="wild")
    f.call("fight", target="protected_deer")
    assert f.player["conduct"]["violations"]


def test_route_atomic_failure_and_legacy_upgrade(tmp_path, make_game):
    g = make_game("xuanheng")
    g.player["inventory"]["array_flag"] = 0
    g._store()
    before = copy.deepcopy(g.state)
    assert not g.call("prepare_formation", formation="ward")["ok"]
    assert g.state == before
    p = g.player
    for key in (
        "route",
        "proficiency",
        "beast",
        "mainDisciplines",
        "materialRemainders",
    ):
        p.pop(key, None)
    p.pop("route_required", None)
    p["cultivation"] = 123
    g._store()
    old = Game(g.path, player_key="xuanheng")
    assert old.player["cultivation"] == 123
    assert old.player["route"] is None
    assert old.call("choose_route", route="danxia")["ok"]
    assert old.player["cultivation"] == 123
    old.close()


def test_five_route_journeys(tmp_path):
    from xiuxian.routes_demo import journeys

    result = journeys(tmp_path)
    assert set(result) == set(CONTENT["routes"])
    assert result["qingxiao"]["self"]["quests"]["escort"] == "completed"
    assert result["fuyao"]["self"]["beast"]["xp"] > 1200
    assert result["rogue"]["self"]["sect"] is None
    assert any(a["tool"] == "prepare_formation" for a in result["xuanheng"]["actions"])
    assert any(a["tool"] == "craft" for a in result["danxia"]["actions"])


def test_momentum_accuracy_changes_system_hit(make_game, monkeypatch):
    g = make_game("qingxiao")
    force_rolls(g, monkeypatch, {"hit": 85})
    g.call("fight", target="sparring")
    g.player["battle"]["enemy"]["agility"] = 20
    g._store()
    r1 = g.call("use_skill", skill="strike")["result"]
    r2 = g.call("use_skill", skill="strike")["result"]
    r3 = g.call("use_skill", skill="strike")["result"]
    own = lambda r: next(x for x in r["log"] if x["actor"] == "player")
    assert not own(r1)["hit"]
    assert not own(r2)["hit"]
    assert own(r3)["hit"]
    assert own(r3)["momentumUsed"]


def test_formation_removed_after_victory(make_game, monkeypatch):
    g = make_game("xuanheng")
    force_rolls(g, monkeypatch)
    g.call("prepare_formation", formation="gather")
    g.call("fight", target="sparring")
    while g.player["battle"]:
        assert g.call("use_skill", skill="strike")["ok"]
    assert not any(e["source"] == "prearray" for e in g.player["statusEffects"])


def test_kill_array_consumed_on_miss(make_game, monkeypatch):
    g = make_game("xuanheng")
    g.call("prepare_formation", formation="kill")
    g.call("fight", target="sparring")
    g.player["battle"]["enemy"]["agility"] = 30
    g._store()
    force_rolls(g, monkeypatch, {"hit": 100})
    r = g.call("use_skill", skill="strike")
    assert r["ok"]
    assert g.player["battle"]["firstDamage"] == 0
    own = next(x for x in r["result"]["log"] if x["actor"] == "player")
    assert not own["hit"]
    assert own["formationBonus"] == 9


def test_world_quote_matches_transaction_with_events(make_game):
    g = make_game("rogue")
    g.state["events"] = [{"id": "caravan", "day": g.state["minutes"] // 1440 + 1}]
    g._store()
    quoted = g.call("get_world")["result"]["shop"]["potion"]
    bought = g.call("trade", item="potion")["result"]["unitPrice"]
    assert quoted == bought == 11
