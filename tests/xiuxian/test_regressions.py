"""Regression tests for the hardening fixes (S1/S2/S3/H3/M1/M2/M3/M4).

Each test targets a finding from the audit; tests marked PROTECTION only pin
existing behavior so a fix cannot regress it."""

import copy
import json
import logging

import pytest

from xiuxian.engine import CONTENT, Game
from xiuxian.island import IslandGame, ISLAND
from xiuxian.mcp_dispatch import dispatch

try:
    from xiuxian.rules import rng_value
except ImportError:  # pre-fix tree: rng_value tests report the gap instead of erroring
    rng_value = None

from pathlib import Path


def need_rng():
    if rng_value is None:
        pytest.fail("xiuxian.rules.rng_value missing (S3 not applied)")


@pytest.fixture
def island(tmp_path, monkeypatch):
    g = IslandGame(tmp_path / "regress.db", player_key="test", player_name="回归修士")
    assert g.call("choose_route", route="qingxiao")["ok"]
    original = g._roll
    monkeypatch.setattr(
        g, "_roll", lambda purpose: 100 if "incident" in purpose else original(purpose)
    )
    yield g
    g.close()


# 1. teach reputation is capped once per NPC per game day
def test_teach_reputation_once_per_day(island):
    rep0 = island.player["reputation"]
    gained = []
    for _ in range(10):
        r = dispatch(island, "npc_ops", "talk qingxiao_mentor teach")
        assert r["ok"], r
        gained.append(r["result"]["reputation_gained"])
    assert island.player["reputation"] - rep0 <= 3  # +2 once, +1 special event
    assert gained.count(2) == 1 and gained[-1] == 0
    island.state["minutes"] += 3 * 1440  # three days later
    island._store()
    r = dispatch(island, "npc_ops", "talk qingxiao_mentor teach")
    assert r["ok"] and r["result"]["reputation_gained"] == 2
    r = dispatch(island, "npc_ops", "talk qingxiao_mentor teach")
    assert r["ok"] and r["result"]["reputation_gained"] == 0


# 2. PROTECTION: teach still works and grants the mentor technique
def test_teach_still_grants_technique(island):
    island.player["reputation"] = 5
    before = list(island.player["techniques"])
    r = island.call("talk", npc="qingxiao_mentor", topic="teach")
    assert r["ok"]
    mentor_technique = ISLAND["npcs"]["qingxiao_mentor"].get("technique")
    assert mentor_technique and mentor_technique in island.player["techniques"]
    assert set(before) <= set(island.player["techniques"])  # nothing lost
    assert r["result"]["relationship"]["trust"] >= 1


# 3. villain pays on first kill only, later kills still count
def test_villain_pays_once(island):
    island.player["realm"] = "金丹"
    island.player["stage"] = 0
    island.player["cultivation"] = 999999
    island.player["hp"] = island.player["max_hp"] = 9999
    island.player["qi"] = island.player["maxQi"] = 999
    island.player["strength"] = 9999
    island.player["stones"] = 0
    island.player["skills"] = list(
        dict.fromkeys(island.player["skills"] + ["strike"])
    )
    island._store()
    assert dispatch(island, "travel_ops", "go bamboo")["ok"]
    assert dispatch(island, "battle_ops", "fight exile")["ok"]
    for _ in range(50):
        if not island.player["battle"]:
            break
        r = island.call("use_skill", skill="strike")
        assert r["ok"]
    stones1 = island.player["stones"]
    iron1 = island.player["inventory"].get("iron", 0)
    assert stones1 >= ISLAND["villains"]["exile"]["enemy"]["reward"]
    # second kill: counts but pays nothing
    assert dispatch(island, "battle_ops", "fight exile")["ok"]
    for _ in range(50):
        if not island.player["battle"]:
            break
        assert island.call("use_skill", skill="strike")["ok"]
    assert island.player["kills"]["exile"] == 2
    assert island.player["stones"] == stones1
    assert island.player["inventory"].get("iron", 0) == iron1
    assert "没有再得到战利品" in str(island.player["history"][-1]["result"].get("message", ""))


# 4. PROTECTION: normal enemies pay every kill
def test_normal_enemy_pays_every_kill(island):
    island.player["realm"] = "金丹"
    island.player["hp"] = island.player["max_hp"] = 9999
    island.player["qi"] = island.player["maxQi"] = 999
    island.player["strength"] = 9999
    island.player["skills"] = list(dict.fromkeys(island.player["skills"] + ["strike"]))
    island._store()
    assert dispatch(island, "travel_ops", "go bamboo")["ok"]
    stones = []
    for _ in range(2):
        assert dispatch(island, "battle_ops", "fight wolf")["ok"]
        for _ in range(50):
            if not island.player["battle"]:
                break
            assert island.call("use_skill", skill="strike")["ok"]
        stones.append(island.player["stones"])
    assert stones[1] > stones[0] >= CONTENT["enemies"]["wolf"]["reward"]


# 5. failed request is not cached; corrected retry under same id works
def test_failed_request_not_cached(island):
    r = dispatch(island, "cultivate_ops", "meditate 999", request_id="fix-me")
    assert not r["ok"]
    assert not island.db.execute(
        "SELECT 1 FROM idempotency WHERE request_id='fix-me'"
    ).fetchone()
    good = dispatch(island, "cultivate_ops", "meditate 2", request_id="fix-me")
    assert good["ok"]
    again = dispatch(island, "cultivate_ops", "meditate 2", request_id="fix-me")
    assert again == good
    conflict = dispatch(island, "cultivate_ops", "meditate 3", request_id="fix-me")
    assert not conflict["ok"]


# 6. PROTECTION: a failed request leaves minutes/rng/tick untouched
def test_failed_request_no_state_change(island):
    before = copy.deepcopy(island.state)
    assert not dispatch(island, "bag_ops", "use herb", request_id="nope")["ok"]
    after = island.storage.load()
    assert after["minutes"] == before["minutes"]
    assert after["rng"] == before["rng"]
    assert after["tick"] == before["tick"]
    assert island.player["stones"] == before["players"]["test"]["stones"]


# 7. island explore honors the collapse block
def test_island_explore_respects_collapse(island):
    assert dispatch(island, "travel_ops", "go bamboo")["ok"]
    day = island.state["minutes"] // 1440 + 1
    island.state["events"].append({"id": "collapse", "blocked": "wild", "day": day})
    island._store()
    r = dispatch(island, "travel_ops", "explore")
    assert not r["ok"] and "坍塌" in r["error"]


# 8. incident resolution generates skipped day events and keeps total cost
def test_resolve_time_goes_through_advance(island):
    island.player["incidents"].append(
        {
            "id": 1,
            "type": "deviation",
            "name": "走火",
            "status": "open",
            "opened": island.state["minutes"],
        }
    )
    island.state["minutes"] = 1440 - 30
    island.state["events"] = []
    island._store()
    r = dispatch(island, "world_ops", "resolve 1 care")
    assert r["ok"] and r["result"]["status"] == "closed"
    assert r["changes"]["minutes"] == 2 * 60 + 60  # care hours + base tick
    assert len(r["new_events"]) >= 1  # the crossed midnight event is not lost
    state = island.storage.load()
    assert state["minutes"] == 1440 - 30 + r["changes"]["minutes"]


# 9. auctions never leak other players' internal keys
def test_auctions_redact_owner(island, tmp_path):
    a = IslandGame(tmp_path / "leak.db", player_key="player_aaa")
    assert a.call("choose_route", route="rogue")["ok"]
    a.player["stones"] = 1000
    a._store()
    b = IslandGame(tmp_path / "leak.db", player_key="player_bbb")
    assert b.call("choose_route", route="rogue")["ok"]
    b.player["stones"] = 1000
    b._store()
    b.close()
    a.db.execute(
        "INSERT OR REPLACE INTO market_listings VALUES ('t1','herb',10,1,?,?)",
        (a.state["minutes"] + 5000, json.dumps({"name": "测试", "source": "x"})),
    )
    a.db.commit()
    assert a.call("market_bid", listing="t1", amount=11)["ok"]
    text = json.dumps(a.call("market_catalog"), ensure_ascii=False)
    assert "player_aaa" not in text and "player_bbb" not in text
    world = json.dumps(a.call("get_world"), ensure_ascii=False)
    assert "player_aaa" not in world and "player_bbb" not in world
    lot = [x for x in a.call("market_catalog")["result"]["auctions"] if x["id"] == "t1"][0]
    assert lot["has_bid"] is True and lot["is_mine"] is True
    b = IslandGame(tmp_path / "leak.db", player_key="player_bbb")
    lot = [x for x in b.call("market_catalog")["result"]["auctions"] if x["id"] == "t1"][0]
    assert lot["has_bid"] is True and lot["is_mine"] is False
    b.close()
    a.close()


# 10. rolls come from the keyed stream, not the old LCG
def test_rolls_use_keyed_stream(island):
    need_rng()
    key = island.state["rngKey"]
    start = island.state["rng"]
    values = [island._roll("probe") for _ in range(30)]
    assert values == [rng_value(key, start + i + 1) for i in range(30)]
    # explicitly differs from the retired LCG stream
    x = 1234567
    lcg = []
    for _ in range(30):
        x = (1664525 * x + 1013904223) % 4294967296
        lcg.append(x % 100 + 1)
    assert values != lcg


# 11. keyed rolls are uniform-ish and key-separated
def test_rng_value_distribution():
    need_rng()
    key = "11" * 32
    buckets = {}
    for i in range(20000):
        v = rng_value(key, i)
        buckets[v] = buckets.get(v, 0) + 1
    assert len(buckets) >= 95
    assert all(120 <= c <= 290 for c in buckets.values()), sorted(buckets.values())[:5]
    other = {rng_value("22" * 32, i) for i in range(200)}
    assert other != {rng_value(key, i) for i in range(200)}


# 12. the key never reaches any client-visible payload
def test_rng_key_never_leaks(island):
    need_rng()
    key = island.state["rngKey"]
    payloads = [
        island.call("get_self"),
        island.call("get_world"),
        island.call("inspect_history", limit=30),
        island.call("world_log", limit=50),
        island.call("market_catalog"),
        dispatch(island, "cultivator_ops", "sheet"),
        dispatch(island, "relay_manual"),
    ]
    for p in payloads:
        assert key not in json.dumps(p, ensure_ascii=False, default=str)


# 13. the key persists and regenerates when lost
def test_rng_key_persistence_and_recovery(tmp_path):
    need_rng()
    path = tmp_path / "key.db"
    g = IslandGame(path, player_key="p1")
    g.call("choose_route", route="qingxiao")
    g.close()
    g = IslandGame(path, player_key="p1")
    key1 = g.state["rngKey"]
    g.close()
    g = IslandGame(path, player_key="p1")
    assert g.state["rngKey"] == key1
    g.close()
    import sqlite3

    con = sqlite3.connect(path)
    con.execute("UPDATE world_state SET rng_key=NULL WHERE id=1")
    con.commit()
    con.close()
    g = IslandGame(path, player_key="p1")
    assert g.state["rngKey"]
    assert g.db.execute("SELECT rng_key FROM world_state WHERE id=1").fetchone()[0]
    assert g.call("cultivate", duration=1)["ok"]
    g.close()


# 14. unexpected exceptions are logged with tool and player context
def test_unexpected_exception_logged(island, caplog, monkeypatch):
    def boom(*a, **k):
        raise KeyError("内部字段缺失")

    monkeypatch.setattr(island, "cultivate", boom)
    with caplog.at_level(logging.ERROR, logger="xiuxian.engine"):
        r = island.call("cultivate", duration=1)
    assert r["ok"] is False
    assert any(
        "tool=cultivate" in rec.getMessage() and "player=test" in rec.getMessage()
        and rec.exc_info
        for rec in caplog.records
    )


# 15. operator snapshots round-trip the key; legacy snapshots regenerate it
def test_operator_snapshot_preserves_rng_key(island):
    need_rng()
    from xiuxian.operator import operate

    key_before = island.state["rngKey"]
    operate(island.path, "save", "snap")
    island.call("rename", name="改名后")
    operate(island.path, "load", "snap")
    island.state = island.storage.load()
    assert island.state["rngKey"] == key_before
    # forge a legacy snapshot body without rng_key
    import sqlite3

    con = sqlite3.connect(island.path)
    body = json.loads(
        con.execute("SELECT body FROM snapshots WHERE name='snap'").fetchone()[0]
    )
    for record in body["tables"]["world_state"]:
        record.pop("rng_key", None)
    con.execute(
        "UPDATE snapshots SET body=? WHERE name='snap'",
        (json.dumps(body, ensure_ascii=False, separators=(",", ":")),),
    )
    con.commit()
    con.close()
    operate(island.path, "load", "snap")
    island.state = island.storage.load()
    assert island.state["rngKey"]  # regenerated, non-null
    island.call("rename", name="再生后")
    assert (
        island.storage.load()["rngKey"] == island.state["rngKey"]
    )  # and persisted
