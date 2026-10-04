"""Short independent journeys for all five routes, solely via player actions."""

import argparse, json, tempfile
from pathlib import Path
from .engine import Game


def journeys(folder):
    results = {}
    for route in ("qingxiao", "xuanheng", "danxia", "fuyao", "hehuan", "taixu", "rogue"):
        g = Game(
            Path(folder) / (route + ".db"), player_key=route, player_name="试玩修士"
        )
        tape = []

        def act(tool, **args):
            r = g.call(tool, **args)
            if not r["ok"]:
                raise RuntimeError((route, tool, args, r))
            tape.append({"tool": tool, "arguments": args, "result": r["result"]})
            return r["result"]

        def duel():
            for _ in range(30):
                p = act("get_self")
                if p["battle"] is None:
                    return
                cooldown = p["battle"]["cooldowns"]
                round = p["battle"]["round"] + 1
                if p["hp"] < 40 and p["inventory"].get("potion", 0):
                    act("use_item", item="potion")
                elif (
                    route == "xuanheng"
                    and p["inventory"].get("array_flag", 0) > 0
                    and p["qi"] >= 5
                    and round >= cooldown.get("array_bolt", 0)
                ):
                    act("use_skill", skill="array_bolt")
                elif (
                    route == "danxia"
                    and p["qi"] >= 6
                    and round >= cooldown.get("poison", 0)
                ):
                    act("use_skill", skill="poison")
                else:
                    act("use_skill", skill="strike")
            raise RuntimeError("battle did not end")

        try:
            act("inspect_route")
            act("choose_route", route=route)
            if route == "qingxiao":
                act("fight", target="sparring")
                duel()
                act("retreat", duration=4)
                act("accept_quest", quest="escort")
                act("travel", destination="wild")
                act("fight", target="bandit")
                duel()
                act("travel", destination="sect")
                act("submit_quest", quest="escort")
            elif route == "xuanheng":
                act("prepare_formation", formation="ward")
                act("fight", target="sparring")
                duel()
            elif route == "danxia":
                act("craft", recipe="potion")
                act("fight", target="sparring")
                duel()
                act("use_item", item="potion")
            elif route == "hehuan":
                act("fight", target="sparring")
                duel()
                act("trade", item="potion")  # charm-route discount applies
            elif route == "taixu":
                act("fight", target="sparring")
                duel()
            elif route == "fuyao":
                act("manage_beast", action="contract", beast="stone_ape")
                act("manage_beast", action="feed")
                act("fight", target="sparring")
                duel()
                act("manage_beast", action="heal")
            else:
                act("accept_quest", quest="delivery")
                act("trade", item="herb")
                act("trade", item="herb", side="sell")
                act("trade", item="herb")
                act("submit_quest", quest="delivery")
                act("learn_technique", technique="qingxiao_sword")
                act("cultivate", method="qingxiao_sword", duration=4)
                act("retreat", duration=1)
            results[route] = {
                "self": act("get_self"),
                "world": act("get_world"),
                "actions": tape,
            }
        finally:
            g.close()
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="xiuxian-routes-demo.json")
    a = p.parse_args()
    with tempfile.TemporaryDirectory() as d:
        r = journeys(d)
    Path(a.output).write_text(
        json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("All five routes played through their distinct mechanics using player tools.")


if __name__ == "__main__":
    main()
