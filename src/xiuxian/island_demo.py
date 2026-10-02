"""Full Lingxi journey using only aggregate player commands, without state grants."""

import argparse
import json
import tempfile
from pathlib import Path
from .island import IslandGame
from .mcp_dispatch import dispatch


def campaign(db, record=None):
    g = IslandGame(db, player_key="demo", player_name="竹间客")

    def invoke(group, command):
        r = dispatch(g, group, command)
        if record is not None:
            record.append({"tool": group, "command": command, "response": r})
        if not r["ok"]:
            raise RuntimeError((group, command, r))
        return r["result"]

    def care():
        if g.player["battle"]:
            return
        for e in list(g.player["incidents"]):
            if e["status"] != "open":
                continue
            option = (
                "care"
                if g.player["stones"] >= 8
                else (
                    "materials" if g.player["inventory"].get("herb", 0) >= 2 else "self"
                )
            )
            for _ in range(10):
                result = invoke("world_ops", f"resolve {e['id']} {option}")
                if result["success"]:
                    break

    def act(group, command):
        care()
        return invoke(group, command)

    def battle(target):
        act("battle_ops", "fight " + target)
        for _ in range(60):
            if not g.player["battle"]:
                break
            if g.player["hp"] < 35 and g.player["inventory"].get("potion", 0):
                act("battle_ops", "item potion")
            else:
                act("battle_ops", "skill strike")
        assert not g.player["battle"]
        assert g.player["kills"].get(target, 0) > 0

    try:
        act("cultivator_ops", "sheet")
        act("sect_ops", "join qingxiao")
        act("quest_ops", "accept trial_qingxiao")
        act("cultivate_ops", "meditate 24")
        act("npc_ops", "talk qingxiao_mentor teach")
        act("quest_ops", "step trial_qingxiao")
        act("travel_ops", "go bamboo")
        act("travel_ops", "explore")
        if g.player["battle"]:
            for _ in range(60):
                if not g.player["battle"]:
                    break
                act("battle_ops", "skill strike")
        if g.player["hp"] < 50:
            act("travel_ops", "go qingxiao")
            act("cultivate_ops", "retreat 8")
            act("travel_ops", "go bamboo")
        battle("wolf")
        act("quest_ops", "step trial_qingxiao")
        act("travel_ops", "go qingxiao")
        act("quest_ops", "step trial_qingxiao report")
        act("quest_ops", "submit trial_qingxiao")
        act("market_ops", "buy foundation_pill 1")
        act("cultivate_ops", "method qingxiao_sword 72")
        act("cultivate_ops", "retreat 8")
        for _ in range(4):
            for retry in range(15):
                care()
                if g.state["minutes"] < g.player["cooldownUntil"]:
                    act("cultivate_ops", "retreat 24")
                if g.player["hp"] < g.player["max_hp"] or g.player["statusEffects"]:
                    act("cultivate_ops", "retreat 8")
                r = act("realm_ops", "breakthrough")
                if r["success"]:
                    break
                act("cultivate_ops", "method qingxiao_sword 24")
            else:
                raise RuntimeError("Repeated breakthrough failure")
        assert g.player["realm"] == "筑基"
        act("travel_ops", "go market")
        act("quest_ops", "accept realm_journey")
        act("quest_ops", "step realm_journey")
        act("travel_ops", "go qingxiao")
        while g.state["minutes"] % (7 * 1440) > 1440:
            act("cultivate_ops", "retreat 24")
        act("travel_ops", "go market")
        act("travel_ops", "go lake")
        act("travel_ops", "go secret 古殿")
        act("travel_ops", "explore")
        for _ in range(60):
            if not g.player["battle"]:
                break
            if g.player["hp"] < 35 and g.player["inventory"].get("potion", 0):
                act("battle_ops", "item potion")
            else:
                act("battle_ops", "skill strike")
        act("quest_ops", "step realm_journey")
        # Opening the realm is the v1 milestone; stronger adversary chains remain optional.
        return {
            "self": act("cultivator_ops", "sheet"),
            "history": act("cultivator_ops", "history 100"),
            "world": act("world_ops", "status"),
        }
    finally:
        g.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="lingxi-demo.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        result = campaign(Path(folder) / "game.db")
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "Lingxi campaign complete: sect task, battle, rewards, foundation, Moon Lake, Tide Realm."
    )


if __name__ == "__main__":
    main()
