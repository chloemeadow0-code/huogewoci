import copy
import pytest
from starlette.testclient import TestClient
from xiuxian.birth import generate_root, generate_aptitude
from xiuxian.engine import Game, CONTENT
from xiuxian.http_app import create_http_app


@pytest.mark.parametrize(
    "roll,count",
    [
        (0, 1),
        (9, 1),
        (10, 2),
        (34, 2),
        (35, 3),
        (69, 3),
        (70, 4),
        (89, 4),
        (90, 5),
        (99, 5),
    ],
)
def test_birth_probability_boundaries(roll, count):
    rolls = iter([roll] + [0] * 5)
    root = generate_root(CONTENT["birth"], lambda size: next(rolls))
    assert len(root["rootElements"]) == count
    assert len(set(root["rootElements"])) == count
    assert set(root["rootElements"]) <= set("金木水火土")
    assert generate_aptitude(CONTENT["birth"], lambda size: roll) == count


def test_birth_is_once_and_rename_preserves_progress(tmp_path):
    g = Game(tmp_path / "profile.db", player_key="first", player_name="旧道号")
    birth = (g.player["root"], list(g.player["rootElements"]), g.player["aptitude"])
    assert g.call("rename", name="  新道号  ")["ok"]
    assert g.call("choose_route", route="qingxiao")["ok"]
    assert g.call("cultivate", duration=2)["ok"]
    before = copy.deepcopy(g.player)
    minutes, rng, tick = g.state["minutes"], g.state["rng"], g.state["tick"]
    assert g.call("rename", name="云游客")["result"]["name"] == "云游客"
    assert (g.state["minutes"], g.state["rng"], g.state["tick"]) == (minutes, rng, tick)
    after = copy.deepcopy(g.player)
    after["name"] = before["name"]
    after["history"] = before["history"]
    assert after == before
    g.close()
    g = Game(tmp_path / "profile.db", player_key="first", player_name="旧道号")
    assert g.player["name"] == "云游客"
    assert (g.player["root"], g.player["rootElements"], g.player["aptitude"]) == birth
    g.close()


@pytest.mark.parametrize(
    "name", ["", " ", "a", "长" * 25, "名字" + chr(10) + "控制", 123, None]
)
def test_invalid_rename_is_atomic(tmp_path, name):
    g = Game(tmp_path / "invalid.db")
    before = copy.deepcopy(g.state)
    assert not g.call("rename", name=name)["ok"]
    assert g.state == before
    g.close()


def test_http_rename_own_ai_and_human_only(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRATION_OPEN", "true")
    with TestClient(create_http_app(tmp_path), base_url="http://localhost") as c:
        assert c.post("/api/rename", json={"name": "冒名者"}).status_code == 401
        keys = {}
        for kind in ("human", "ai"):
            keys[kind] = c.post(
                "/api/register", json={"name": "初始" + kind, "kind": kind}
            ).json()["api_key"]
        for kind in ("human", "ai"):
            headers = {"Authorization": "Bearer " + keys[kind]}
            before = c.get("/api/state", headers=headers).json()
            assert (
                c.post(
                    "/api/rename",
                    headers=headers,
                    json={"name": "新号" + kind, "player_key": "other"},
                ).status_code
                == 400
            )
            assert (
                c.post(
                    "/api/rename", headers=headers, json={"name": "新号" + kind}
                ).status_code
                == 200
            )
            after = c.get("/api/state", headers=headers).json()
            assert after["self"]["result"]["name"] == "新号" + kind
            assert after["world"]["result"]["time"] == before["world"]["result"]["time"]
            assert after["self"]["result"]["root"] == before["self"]["result"]["root"]
            assert (
                after["self"]["result"]["aptitude"]
                == before["self"]["result"]["aptitude"]
            )
        assert (
            c.get(
                "/api/state", headers={"Authorization": "Bearer " + keys["human"]}
            ).json()["self"]["result"]["name"]
            == "新号human"
        )
