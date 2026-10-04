import copy
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from starlette.testclient import TestClient
from xiuxian.engine import Game
from xiuxian.island import IslandGame, ISLAND
from xiuxian.mcp_dispatch import dispatch, MCP_TOOLS
from xiuxian.http_app import create_http_app


@pytest.fixture
def island(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "island.db", player_key="test", player_name="岛上修士")
    assert g.call("choose_route", route="qingxiao")["ok"]
    # Incidents are exercised separately; pin ordinary replay to safe incident rolls.
    original = g._roll
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 100 if "incident" in purpose else original(purpose)
    )
    yield g
    g.close()


def test_content_scope():
    assert (
        len(ISLAND["locations"]) == 22
        and len(ISLAND["npcs"]) == 26
        and len(ISLAND["villains"]) == 6
    )
    assert len(MCP_TOOLS) == 13
    for npc in ISLAND["npcs"].values():
        assert all(
            k in npc
            for k in (
                "identity",
                "duty",
                "background",
                "personality",
                "positive",
                "negative",
                "location",
                "functions",
                "initialRelationship",
                "personalQuest",
                "specialEvent",
            )
        )
    for loc in ISLAND["locations"].values():
        for dest in loc["exits"]:
            assert loc["id"] in ISLAND["locations"][dest]["exits"]


@pytest.mark.parametrize("group", MCP_TOOLS)
def test_all_bundles_have_defaults_and_help(island, group):
    assert dispatch(island, group, "")["ok"]
    if group != "relay_manual":
        assert dispatch(island, group, "help")["ok"]


def test_command_rejects_number_injection(island):
    before = copy.deepcopy(island.state)
    assert not dispatch(island, "battle_ops", "skill strike 99999")["ok"]
    assert island.state == before
    assert not dispatch(island, "cultivate_ops", "meditate -10")["ok"]


@pytest.mark.parametrize("kind", ISLAND["incidents"])
def test_incident_persistent_block_resolve_once(island, kind):
    island._open_incident(kind)
    island._store()
    e = island.player["incidents"][-1]
    blocked = ISLAND["incidents"][kind]["blocks"][0]
    assert not island.call(blocked)["ok"]
    reopened = IslandGame(island.path, player_key="test")
    assert reopened.player["incidents"][-1]["status"] == "open"
    before = reopened.player["stones"]
    assert reopened.call("incident_resolve", incident=e["id"], choice="care")["result"][
        "success"
    ]
    assert reopened.player["stones"] == before - 8
    assert not reopened.call("incident_resolve", incident=e["id"], choice="care")["ok"]
    assert reopened.player["stones"] == before - 8
    reopened.close()


def test_relational_tables_and_migration(tmp_path):
    old = Game(tmp_path / "legacy.db", player_key="old", player_name="旧修士")
    old.call("choose_route", route="danxia")
    old.call("cultivate", duration=2)
    saved = copy.deepcopy(old.player)
    old.close()
    g = IslandGame(tmp_path / "legacy.db", player_key="old")
    assert (
        g.player["name"] == saved["name"]
        and g.player["cultivation"] == saved["cultivation"]
    )
    assert (
        g.player["root"] == saved["root"] and g.player["aptitude"] == saved["aptitude"]
    )
    assert g.player["islandLocation"] == "danxia"
    assert (
        g.db.execute("SELECT location FROM cultivators WHERE id='old'").fetchone()[0]
        == "danxia"
    )
    assert (
        g.db.execute(
            "SELECT quantity FROM cultivator_inventory WHERE cultivator_id='old' AND item='herb'"
        ).fetchone()[0]
        == 2
    )
    assert (
        g.db.execute(
            "SELECT cultivation FROM cultivator_stats WHERE cultivator_id='old'"
        ).fetchone()[0]
        == saved["cultivation"]
    )
    # Old blob remains untouched as a migration recovery source, not authoritative state.
    old_json = g.db.execute(
        "SELECT value FROM session_meta WHERE key='xiuxian_state'"
    ).fetchone()[0]
    g.call("rename", name="新修士")
    assert (
        g.db.execute(
            "SELECT value FROM session_meta WHERE key='xiuxian_state'"
        ).fetchone()[0]
        == old_json
    )
    g.close()
    g = IslandGame(tmp_path / "legacy.db", player_key="old")
    assert g.player["name"] == "新修士"
    g.close()


def test_atomic_idempotency_and_conflict(island):
    a = dispatch(island, "cultivate_ops", "meditate 2", request_id="same")
    before = copy.deepcopy(island.state)
    b = dispatch(island, "cultivate_ops", "meditate 2", request_id="same")
    assert a == b and island.state == before
    assert not dispatch(island, "cultivate_ops", "meditate 3", request_id="same")["ok"]
    assert island.state == before


def test_concurrent_idempotency(tmp_path):
    seed = IslandGame(tmp_path / "concurrent.db", player_key="one")
    seed.call("choose_route", route="qingxiao")
    seed.close()

    def run(_):
        g = IslandGame(tmp_path / "concurrent.db", player_key="one")
        try:
            return dispatch(g, "cultivate_ops", "meditate 2", "request-1")
        finally:
            g.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(8)))
    assert all(r == results[0] for r in results)
    g = IslandGame(tmp_path / "concurrent.db", player_key="one")
    assert len([h for h in g.player["history"] if h["action"] == "cultivate"]) == 1
    g.close()


def test_stage_condition_and_branch(island):
    assert island.call("accept_quest", quest="trial_qingxiao")["ok"]
    assert not island.call("quest_step", quest="trial_qingxiao")["ok"]
    island.call("talk", npc="qingxiao_mentor", topic="teach")
    assert island.call("quest_step", quest="trial_qingxiao")["result"]["stage"] == 1
    island.call("travel", destination="bamboo")
    island.call("fight", target="wolf")
    for _ in range(50):
        if not island.player["battle"]:
            break
        island.call("use_skill", skill="strike")
    assert island.player["kills"]["wolf"] == 1
    assert island.call("quest_step", quest="trial_qingxiao")["ok"]
    island.call("travel", destination="qingxiao")
    assert not island.call("quest_step", quest="trial_qingxiao", branch="I won")["ok"]
    assert island.call("quest_step", quest="trial_qingxiao", branch="protect")["ok"]
    assert island.call("submit_quest", quest="trial_qingxiao")["result"]["reward"] == 73
    assert not island.call("submit_quest", quest="trial_qingxiao")["ok"]


def test_notable_item_lifecycle(island):
    island.player["stones"] = 200
    island._store()
    island.call("trade", item="foundation_pill")
    assert (
        island.call("item_ledger", item="foundation_pill")["result"][0]["status"]
        == "held"
    )
    island.call("trade", item="foundation_pill", side="sell")
    ledger = island.call("item_ledger", item="foundation_pill")["result"][0]
    assert ledger["status"] == "sold" and len(ledger["entries"]) == 2


def test_shared_web_key_idempotency_and_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRATION_OPEN", "true")
    with TestClient(create_http_app(tmp_path), base_url="http://localhost") as c:
        key = c.post(
            "/api/register",
            json={"name": "共号修士", "kind": "ai", "route": "qingxiao"},
        ).json()["api_key"]
        h = {"Authorization": "Bearer " + key, "Idempotency-Key": "one"}
        assert c.get("/api/v1/state").status_code == 401
        payload = {"tool": "cultivate_ops", "command": "meditate 2"}
        a = c.post("/api/v1/command", headers=h, json=payload)
        b = c.post("/api/v1/command", headers=h, json=payload)
        assert a.status_code == 200 and a.json() == b.json()
        status = c.get("/api/v1/state", headers=h).json()
        assert status["readOnly"] is False
        assert status["self"]["result"]["cultivation"] == a.json()["result"]["gained"]


def test_world_events_persist_and_map_gate(island):
    island.call("cultivate", duration=24)
    assert island.state["events"] and island.state["flags"]
    assert not island.call("travel", destination="secret")["ok"]
    assert island.call("travel", destination="market")["ok"]
    assert not island.call("travel", destination="lake")["ok"]
    old = copy.deepcopy(island.state["events"])
    island.close()
    g = IslandGame(island.path, player_key="test")
    assert g.state["events"] == old
    g.close()


def test_auction_escrow_outbid_and_settlement(tmp_path):
    g = IslandGame(tmp_path / "auction.db", player_key="first")
    g.call("choose_route", route="rogue")
    g.player["stones"] = 300
    g._store()
    other = IslandGame(g.path, player_key="second")
    other.call("choose_route", route="rogue")
    other.player["stones"] = 300
    other._store()
    other.close()
    assert g.call("market_bid", listing="auction:0", amount=50)["ok"]
    first = g.player["stones"]
    other = IslandGame(g.path, player_key="second")
    assert other.call("market_bid", listing="auction:0", amount=60)["ok"]
    assert other.state["players"]["first"]["stones"] == first + 50
    assert other.player["stones"] == 240
    other.state["minutes"] = 7 * 1440
    other._advance("travel", {})
    other._store()
    assert other.player["inventory"].get("sword") == 1
    assert other.player["ledgers"][-1]["entries"][0]["source"] == "auction"
    assert not other.call("market_bid", listing="auction:0", amount=65)["ok"]
    other.close()
    g.close()


def test_npc_special_event_once_and_villain_phase_effect(island):
    for _ in range(5):
        assert island.call("talk", npc="qingxiao_mentor")["ok"]
    assert "npc_event:qingxiao_mentor" in island.state["flags"]
    reputation = island.player["reputation"]
    island.call("talk", npc="qingxiao_mentor")
    assert island.player["reputation"] == reputation
    island.player["islandLocation"] = "bamboo"
    island.player["location"] = "wild"
    base = island._current_event().get("exploreDamage", 0)
    island.state["flags"]["villain_exile"] = {"stage": 2, "branch": ""}
    assert island._current_event()["exploreDamage"] == base + 2
    island.state["flags"]["villain_exile"] = {"stage": 4, "branch": "report"}
    assert island._current_event().get("exploreDamage", 0) == base


def test_foreign_sect_resources_blocked(island):
    island.call("travel", destination="market")
    assert island.call("travel", destination="danxia")["ok"]
    assert not island.call("cultivate")["ok"]
    assert "cultivate" not in island.available_actions()
    assert island.call("get_world")["result"]["shop"] == {}


def test_sqlite_lock_retry_then_success():
    import asyncio, sqlite3
    from xiuxian.mcp_dispatch import _call_ops

    calls = []

    def operation():
        calls.append(True)
        if len(calls) < 3:
            raise sqlite3.OperationalError("database is locked")
        return {"ok": True}

    assert asyncio.run(_call_ops(operation)) == {"ok": True}
    assert len(calls) == 3


def test_fixed_skill_categories_and_escape(island, monkeypatch):
    from xiuxian.engine import CONTENT

    assert {s["type"] for s in CONTENT["skills"].values()} == {
        "attack",
        "defense",
        "heal",
        "buff",
        "debuff",
        "control",
        "movement",
        "escape",
    }
    island.call("travel", destination="bamboo")
    island.call("fight", target="wolf")
    monkeypatch.setattr(island, "_roll", lambda purpose: 1)
    r = island.call("use_skill", skill="escape_step")
    assert r["ok"] and island.player["battle"] is None
    assert island.player["islandLocation"] == "qingxiao"


def test_relational_operator_restores_progress_and_idempotency(island):
    from xiuxian.operator import operate

    before = island.call("cultivate", duration=2, request_id="before-save")
    operate(island.path, "save", "checkpoint")
    island.call("rename", name="快照之后")
    island.call("cultivate", duration=3, request_id="after-save")
    operate(island.path, "load", "checkpoint")
    result = island.call("cultivate", duration=2, request_id="before-save")
    assert result == before
    assert island.player["name"] != "快照之后"
    assert island.player["cultivation"] == before["result"]["gained"]
    assert not island.db.execute(
        "SELECT 1 FROM idempotency WHERE request_id='after-save'"
    ).fetchone()
    assert operate(island.path, "list")[0]["name"] == "checkpoint"


def test_relational_beast_contract_growth_and_restart(tmp_path):
    g = IslandGame(tmp_path / "beasts.db", player_key="owner")
    assert dispatch(g, "sect_ops", "join fuyao")["ok"]
    g.player["stones"] = 100
    g._store()
    pet = dispatch(g, "npc_ops", "beast contract cloud_fox")["result"]
    assert pet["contract_owner"] == "owner" and pet["species"] == "cloud_fox"
    assert dispatch(g, "npc_ops", "beast train")["ok"]
    xp = g.player["beast"]["xp"]
    g.close()
    g = IslandGame(tmp_path / "beasts.db", player_key="owner")
    assert g.player["beast"]["xp"] == xp and g.player["beast"]["hunger"] >= 0
    assert (
        g.db.execute(
            "SELECT species,level FROM spirit_beasts WHERE cultivator_id='owner'"
        ).fetchone()[0]
        == "cloud_fox"
    )
    assert dispatch(g, "npc_ops", "beast release")["ok"]
    g.close()


def test_relational_craft_and_all_technique_types(island, monkeypatch):
    from xiuxian.engine import CONTENT

    assert {t["type"] for t in CONTENT["techniques"].values()} == {
        "心法",
        "剑诀",
        "阵诀",
        "体修",
        "丹道",
        "符道",
        "器道",
        "御兽",
        "魅道",
        "雷法",
        "煞道",
        "商道",
        "锻造",
        "水道",
        "炎道",
        "缉道",
    }
    island.player["inventory"]["iron"] = 3
    island._store()
    monkeypatch.setattr(
        island, "_roll", lambda purpose: 100 if "incident" in purpose else 1
    )
    result = dispatch(island, "refine_ops", "weapon sword 1")
    assert result["ok"] and island.player["inventory"].get("sword") == 1
    island.close()
    g = IslandGame(island.path, player_key="test")
    assert (
        g.player["inventory"]["sword"] == 1
        and g.player["inventory"].get("iron", 0) == 0
    )
    assert g.player["ledgers"][-1]["item"] == "sword"
    g.close()


def test_blackmarket_villain_and_outdoor_quest_available(island):
    assert island.call("travel", destination="market")["ok"]
    assert island.call("travel", destination="blackmarket")["ok"]
    quest = next(
        k for k, q in ISLAND["quests"].items() if q["location"] == "blackmarket"
    )
    assert dispatch(island, "quest_ops", "accept " + quest)["ok"]
    assert dispatch(island, "battle_ops", "fight owner")["ok"]
    island.player["battle"] = None
    island.player["islandLocation"] = "ruins"
    island.player["location"] = "wild"
    island._store()
    quest = next(k for k, q in ISLAND["quests"].items() if q["location"] == "ruins")
    assert dispatch(island, "quest_ops", "accept " + quest)["ok"]
