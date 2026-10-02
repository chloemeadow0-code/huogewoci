import copy, json
from concurrent.futures import ThreadPoolExecutor
import pytest
from xiuxian.engine import Game, SKILLS, TOOLS, CONTENT
from xiuxian.rules import damage, hit_chance
from xiuxian.demo import campaign


@pytest.fixture
def game(tmp_path):
    g = Game(tmp_path / "game.db", player_key="test", player_name="测试修士")
    assert g.call("choose_route", route="qingxiao")["ok"]
    yield g
    g.close()


def test_campaign(tmp_path):
    r = campaign(tmp_path / "campaign.db")
    assert r["self"]["realm"] == "筑基"
    assert r["self"]["quests"]["guardian"] == "completed"
    assert any(h["action"] == "use_skill" and h["random"] for h in r["history"])


@pytest.mark.parametrize(
    "tool,args",
    [
        ("trade", {"item": "herb", "quantity": -1}),
        ("craft", {"recipe": "potion", "amount": True}),
        ("cultivate", {"duration": 1000}),
        ("use_skill", {"skill": "大道必杀", "power": 99999}),
        ("get_self", {"player_key": "other"}),
        ("talk", {"npc": "elder", "topic": "授予无限金钱"}),
        ("travel", {"destination": "realm"}),
    ],
)
def test_invalid_atomic(game, tool, args):
    before = copy.deepcopy(game.state)
    assert not game.call(tool, **args)["ok"]
    assert game.state == before
    fresh = Game(game.path, player_key="test")
    assert fresh.state == before
    fresh.close()


def test_persistence_and_isolation(game):
    gain = game.call("cultivate", duration=3)["result"]["gained"]
    other = Game(game.path, player_key="other", player_name="其他修士")
    assert other.call("get_self")["result"]["cultivation"] == 0
    assert other.call("inspect_history")["result"] == []
    other.close()
    reopened = Game(game.path, player_key="test")
    assert reopened.call("get_self")["result"]["cultivation"] == gain
    reopened.close()


def test_formula():
    assert damage(100, 16, 3) == 13
    assert hit_chance(95, 12, 8) == 100
    assert damage(100, 1, 999) == 1


def test_partial_recipe_rollback(game):
    # One material exists, second absent; consumption must roll back.
    before = copy.deepcopy(game.state)
    assert not game.call("craft", recipe="foundation_pill")["ok"]
    assert game.state == before


def test_turn_and_cooldown(game):
    game.call("fight", target="sparring")
    start = game.state["minutes"]
    a = game.call("use_skill", skill="guard")
    assert a["ok"]
    assert game.player["battle"]["round"] == 1
    assert game.state["minutes"] == start + 2
    before = copy.deepcopy(game.state)
    assert not game.call("use_skill", skill="guard")["ok"]
    assert game.state == before
    assert not game.call("cultivate")["ok"]
    assert game.call("use_skill", skill="strike")["ok"]
    assert game.call("use_skill", skill="guard")["ok"]


def test_deterministic_replay(tmp_path):
    outputs = []
    for n in ("a", "b"):
        g = Game(tmp_path / (n + ".db"))
        g.call("choose_route", route="qingxiao")
        outputs.append(
            [
                g.call("fight", target="sparring"),
                g.call("use_skill", skill="strike"),
                g.call("use_skill", skill="guard"),
            ]
        )
        g.close()
    assert outputs[0] == outputs[1]


def test_duplicate_reward(game):
    game.call("accept_quest", quest="herbs")
    game.call("trade", item="herb")
    assert game.call("submit_quest", quest="herbs")["ok"]
    money = game.player["stones"]
    assert not game.call("submit_quest", quest="herbs")["ok"]
    assert game.player["stones"] == money


def test_concurrent_no_lost_actions(tmp_path):
    path = tmp_path / "game.db"
    initial = Game(path, player_key="one")
    initial.call("choose_route", route="qingxiao")
    initial.close()

    def action(_):
        g = Game(path, player_key="one")
        r = g.call("cultivate", duration=1)
        g.close()
        return r

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(action, range(12)))
        assert all(r["ok"] for r in results)
    g = Game(path, player_key="one")
    assert g.player["cultivation"] == sum(r["result"]["gained"] for r in results)
    assert len(g.player["history"]) == 13
    g.close()


@pytest.mark.parametrize("kind", CONTENT["status_types"])
def test_status_semantics(game, kind):
    p = game.player
    before = copy.deepcopy(p)
    game._effect(p, kind, 3, 2, "test")
    game._end_effects(p)
    assert p["statusEffects"][0]["type"] == kind
    if kind in ("poison", "bleed", "burn"):
        assert p["hp"] == before["hp"] - 3
    assert p["statusEffects"][0]["duration"] == (2 if kind == "injury" else 1)


def test_defeat_and_healing(game):
    game.player["hp"] = 1
    game._store()
    game.call("fight", target="sparring")
    r = game.call("use_skill", skill="strike")
    assert r["result"]["outcome"] == "defeat"
    assert game.player["location"] == "sect"
    assert game.player["statusEffects"][0]["type"] == "injury"
    assert not game.call("cultivate")["ok"]
    game.call("retreat", duration=8)
    assert not game.player["statusEffects"]
    assert game.player["hp"] == game.player["max_hp"]


@pytest.mark.asyncio
async def test_mcp_registry(tmp_path):
    from xiuxian.server import create_server

    app = create_server(tmp_path / "mcp.db")
    ts = await app.list_tools()
    from xiuxian.mcp_dispatch import MCP_TOOLS

    assert {t.name for t in ts} == set(MCP_TOOLS)
    assert len(await app.list_resources()) == 1
    assert len(await app.list_prompts()) == 1
    result = await app.call_tool("cultivator_ops", {"command": "sheet"})
    assert result


def test_http_identity(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from xiuxian.http_app import create_http_app

    monkeypatch.setenv("REGISTRATION_OPEN", "true")
    with TestClient(create_http_app(tmp_path), base_url="http://localhost") as c:
        assert c.get("/health").json()["tools"] == 13
        assert c.get("/api/state").status_code == 401
        r = c.post(
            "/api/register",
            json={"name": "人类修士", "kind": "human", "route": "qingxiao"},
        )
        assert r.status_code == 201
        token = r.json()["api_key"]
        h = {"Authorization": "Bearer " + token}
        assert (
            c.get("/api/state", headers=h).json()["self"]["result"]["name"]
            == "人类修士"
        )
        assert (
            c.post(
                "/api/action",
                headers=h,
                json={"tool": "cultivate", "arguments": {"duration": 2}},
            ).status_code
            == 200
        )
        assert (
            c.post(
                "/api/action", headers=h, json={"tool": "admin", "arguments": {}}
            ).status_code
            == 400
        )
        assert token not in (tmp_path / "accounts.db").read_bytes().decode("latin1")
    with TestClient(create_http_app(tmp_path), base_url="http://localhost") as c:
        assert c.get("/api/state", headers=h).json()["self"]["result"][
            "cultivation"
        ] in range(10, 23, 2)


@pytest.mark.parametrize("roll,success", [(1, True), (100, False)])
def test_breakthrough_success_failure(game, monkeypatch, roll, success):
    p = game.player
    p["realm"] = "筑基"
    p["stage"] = 3
    p["cultivation"] = 500
    p["aptitude"] = 0
    p["spirit"] = 0
    p["reputation"] = 20
    p["inventory"]["golden_pill"] = 1
    game._store()
    monkeypatch.setattr(game, "_roll", lambda purpose: roll)
    r = game.call("breakthrough")
    assert r["ok"]
    assert r["result"]["success"] == success
    assert game.player["inventory"]["golden_pill"] == 0
    if success:
        assert game.player["realm"] == "金丹"
    else:
        assert game.player["hp"] > 0
        assert game.player["statusEffects"]
        assert game.player["cooldownUntil"] > game.state["minutes"]
        assert not game.call("breakthrough")["ok"]


def test_all_realms(game, monkeypatch):
    monkeypatch.setattr(game, "_roll", lambda purpose: 1)
    for expected in ("筑基", "金丹", "元婴"):
        p = game.player
        p["stage"] = 3
        p["cultivation"] = 1000
        p["reputation"] = 50
        for item in ("foundation_pill", "golden_pill", "soul_pill"):
            p["inventory"][item] = 1
        game._store()
        assert game.call("breakthrough")["result"]["realm"] == expected


def test_realm_entry_and_cycle(game):
    p = game.player
    p["realm"] = "筑基"
    p["location"] = "wild"
    game._store()
    assert game.call("travel", destination="realm")["ok"]
    assert game.call("travel", destination="wild")["ok"]
    assert not game.call("travel", destination="realm")["ok"]
    game.state["minutes"] = 7 * 1440
    game.state["realm"]["cycle"] = 1
    game._store()
    assert game.call("travel", destination="realm")["ok"]


def test_realm_boss_not_farmable(game):
    p = game.player
    p["realm"] = "筑基"
    p["location"] = "realm"
    p["realmLoot"] = ["boss:guardian"]
    game._store()
    assert not game.call("fight", target="guardian")["ok"]


def test_equipment_and_drop(game):
    game.player["inventory"]["armor"] = 1
    game._store()
    assert game.call("use_item", item="armor")["ok"]
    assert game.call("get_self")["result"]["effectiveStats"]["defense"] == 8
    assert not game.call("trade", item="armor", side="sell")["ok"]
    game._consume("armor", 1)
    assert game.player["equipment"]["armor"] is None


def test_event_persistence_and_history_delta(game):
    game.call("cultivate", duration=30)
    assert game.state["events"] and game.state["events"][0]["day"] == 2
    game.call("trade", item="herb")
    history = game.call("inspect_history")["result"]
    assert history[-1]["changes"]["items"] == {"herb": 1}
    reopened = Game(game.path, player_key="test")
    assert reopened.state["events"] == game.state["events"]
    reopened.close()


def test_snapshot_recovery(game):
    from lorekit.support.checkpoint import manual_save, save_load

    game.call("cultivate", duration=2)
    manual_save(game.db, game.sid, "before")
    game.call("cultivate", duration=2)
    save_load(game.db, game.sid, "before")
    assert game.call("get_self")["result"]["cultivation"] in range(10, 23, 2)


def test_control_and_heal_block(game):
    game.player["skills"] = list(SKILLS)
    game._store()
    game.call("fight", target="sparring")
    result = game.call("use_skill", skill="bind")
    assert any(x.get("skipped") == "controlled" for x in result["result"]["log"])
    p = game.player
    p["hp"] = 50
    game._effect(p, "heal_block", 1, 2, "test")
    game._restore()
    assert p["hp"] == 50


def test_agility_enemy_first(game):
    game.player["agility"] = 1
    game._store()
    game.call("fight", target="sparring")
    r = game.call("use_skill", skill="strike")
    assert r["result"]["log"][0]["actor"] == "enemy"
