"""Full Lingxi journey using only aggregate player commands, without state grants."""

import argparse
import json
import logging
import tempfile
from pathlib import Path
from .island import IslandGame
from .mcp_dispatch import dispatch

logger = logging.getLogger(__name__)


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

    def ensure_breakthrough_ready():
        """Cultivate/heal/restock until a breakthrough attempt is fully
        affordable: enough cultivation, full hp, cooldown elapsed and, at
        stage 3, a foundation pill in stock (every attempt consumes one)."""
        for _ in range(40):
            care()
            s = act("cultivator_ops", "sheet")
            if s["cultivation"] < s["cultivation_required"]:
                act("cultivate_ops", "method qingxiao_sword 24")
            elif (
                g.player["stage"] == 3
                and g.player["inventory"].get("foundation_pill", 0) < 1
            ):
                if g.player["stones"] >= 80:
                    act("market_ops", "buy foundation_pill 1")
                else:
                    act("travel_ops", "go bamboo")
                    battle("wolf")
                    act("travel_ops", "go qingxiao")
            elif g.player["hp"] < g.player["max_hp"] or g.player["statusEffects"]:
                act("cultivate_ops", "retreat 8")
            elif g.state["minutes"] < g.player["cooldownUntil"]:
                act("cultivate_ops", "retreat 24")
            else:
                return
        context = json.dumps(
            {
                "root": g.player["root"],
                "aptitude": g.player["aptitude"],
                "cultivation": g.player["cultivation"],
                "required": s["cultivation_required"],
                "stage": g.player["stage"],
                "stones": g.player["stones"],
            },
            ensure_ascii=False,
        )
        logger.error("island demo breakthrough preparation did not converge: %s", context)
        raise RuntimeError(
            "breakthrough preparation did not converge after 40 rounds: " + context
        )

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
            for retry in range(30):
                ensure_breakthrough_ready()
                r = act("realm_ops", "breakthrough")
                if r["success"]:
                    break
            else:
                context = json.dumps(
                    {
                        "root": g.player["root"],
                        "aptitude": g.player["aptitude"],
                        "stage": g.player["stage"],
                        "cultivation": g.player["cultivation"],
                        "stones": g.player["stones"],
                    },
                    ensure_ascii=False,
                )
                logger.error("island demo breakthrough loop exhausted: %s", context)
                raise RuntimeError(
                    "breakthrough did not converge after 30 attempts: " + context
                )
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
