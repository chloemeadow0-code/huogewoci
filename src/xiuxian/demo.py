"""Playable campaign executed solely through the player action facade."""

import argparse, json, tempfile
from pathlib import Path
from .engine import Game


def campaign(db, record=None):
    g = Game(db, player_key="demo", player_name="问道修士")

    def act(name, **args):
        r = g.call(name, **args)
        if not r["ok"]:
            raise RuntimeError((name, args, r))
        if record is not None:
            record.append({"tool": name, "arguments": args, "response": r})
        return r["result"]

    def finish_battle():
        for _ in range(40):
            p = act("get_self")
            if not p["battle"]:
                break
            if p["hp"] < 35 and p["inventory"].get("potion", 0):
                act("use_item", item="potion")
            else:
                act("use_skill", skill="strike")
        assert g.player["battle"] is None

    def battle(target):
        act("fight", target=target)
        finish_battle()

    try:
        act("choose_route", route="qingxiao")
        act("get_self")
        act("get_world")
        act("accept_quest", quest="herbs")
        act("cultivate", duration=30)
        act("travel", destination="wild")
        for _ in range(20):
            if g.player["inventory"].get("herb", 0) >= 3:
                break
            if g.player["location"] == "sect":
                act("retreat", duration=8)
                act("travel", destination="wild")
            if g.player["hp"] < 60:
                act("travel", destination="sect")
                act("retreat", duration=8)
                act("travel", destination="wild")
            r = act("explore")
            finish_battle()
        if g.player["location"] == "sect":
            act("retreat", duration=8)
            act("travel", destination="wild")
        if g.player["hp"] < 50:
            act("travel", destination="sect")
            act("retreat", duration=8)
            act("travel", destination="wild")
        battle("wolf")
        act("travel", destination="sect")
        if g.player["inventory"].get("herb", 0) < 3:
            act("trade", item="herb", quantity=3 - g.player["inventory"].get("herb", 0))
        act("submit_quest", quest="herbs")
        act("talk", npc="elder", topic="teach")
        act("trade", item="sword")
        act("use_item", item="sword")
        # Material trade finances the breakthrough resource without admin grants.
        if g.player["stones"] < 80:
            act("travel", destination="wild")
            for _ in range(8):
                battle("wolf")
                act("travel", destination="sect")
                act("retreat", duration=8)
                act("travel", destination="wild")
            act("travel", destination="sect")
        act("trade", item="foundation_pill")
        act("retreat", duration=8)
        for _ in range(4):
            r = act("breakthrough")
            while not r["success"]:
                act("retreat", duration=24)
                act("cultivate", method="qingxiao_sword", duration=24)
                r = act("breakthrough")
        assert g.player["realm"] == "筑基"
        act("accept_quest", quest="guardian")
        while g.state["minutes"] % (7 * 1440) > 24 * 60:
            act("retreat", duration=24)
        act("travel", destination="wild")
        act("travel", destination="realm", node="古殿")
        act("explore")
        finish_battle()
        battle("guardian")
        assert g.player["kills"].get("guardian", 0) >= 1
        act("travel", destination="wild")
        act("travel", destination="sect")
        act("submit_quest", quest="guardian")
        return {
            "self": act("get_self"),
            "history": act("inspect_history", limit=100),
            "world": act("get_world"),
        }
    finally:
        g.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="xiuxian-demo.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        result = campaign(Path(folder) / "game.db")
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "Campaign complete: foundation established, guardian defeated, quest submitted."
    )


if __name__ == "__main__":
    main()
