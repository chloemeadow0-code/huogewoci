"""Aggregate commands and common SQLite retry entrypoint.

_call_ops adapts allotment-relay/server/mcp_dispatch.py (MIT); see third_party.
"""

from __future__ import annotations
import asyncio
import logging
import shlex
import sqlite3
from starlette.concurrency import run_in_threadpool
from .island import IslandGame, ISLAND
from .engine import CONTENT
from .rules import require, RuleError

logger = logging.getLogger(__name__)

HELP = {
    "cultivator_ops": "身份与个人记录。空=sheet。sheet；rename 云游客；history 20；incidents；resolve 1 care。改名不改凭证、信誉或出生属性。",
    "sect_ops": "宗门与路线。空=status。status；join qingxiao；task list；task accept trial_qingxiao；task step trial_qingxiao report；task submit trial_qingxiao；hall 查看贡献殿；redeem <物品> [数量] 用贡献兑换。只能选择一次路线；散修join rogue。",
    "cultivate_ops": "修炼与长期功法。空=status。meditate 4；method qingxiao_sword 4；retreat 8；learn qingxiao_sword；ask 林青枝。单位游戏小时，不是现实等待；功法与技能分开。",
    "travel_ops": "山海行路。空=map。map；go 青竹林；go 潮生秘境 古殿；explore。只能沿相邻出口；筑基解锁高级区域。",
    "battle_ops": "逐回合斗法。空=status。fight wolf；skill 青云剑诀；item 回气丹；retreat；formation ward。fight只开战；技能效果来自固定配置，禁止追加数值。",
    "bag_ops": "背包、装备与履历。空=list。list；use 回气丹；equip 青云剑；ledger 青云剑。use/equip只使用已持有物品。",
    "refine_ops": "炼丹炼器与制符。空=list。list；pill 回气丹 2；weapon 青云剑 1；craft paper_talisman 1。检查功法、境界、材料，结果由代码判定。",
    "npc_ops": "附近人物与关系。空=list。list；talk 林青枝；talk 林青枝 teach；gift 林青枝 灵草；beast contract cloud_fox；beast feed；beast train；beast evolve 进化灵兽；track wolf。人类与AI共用关系和灵兽。",
    "quest_ops": "阶段任务。空=list。list；accept trial_qingxiao；step trial_qingxiao；step trial_qingxiao report；submit trial_qingxiao。阶段必须由实际行动达成；终幕report/protect二选一。",
    "market_ops": "灵石交易与竞价。空=list。list；buy 回气丹 1；sell 灵草 2；auction；bid auction:0 50。竞价托管，到期交付，被超价退还。黑市须亲自前往。",
    "realm_ops": "境界与潮生秘境。空=status。status；breakthrough；enter；leave。小境界突破掷点判定；跨大境界先斩心魔（属性镜像自身的幻影），金丹渡元婴还需引雷三重：凝罡御雷/不动如山/引雷淬体（淬体加深雷伤但渡劫后力与灵上限额外增长）。",
    "world_ops": "世界变化和灾档闭环。空=status。status；log 20；incidents；resolve 1 materials。未处理坏事会持续限制相应行动；处置cost和success见灾档。",
}
MCP_TOOLS = ("relay_manual", *HELP)
HINTS = {
    "get_self": ("cultivator_ops", "sheet"),
    "get_world": ("world_ops", "status"),
    "choose_route": ("sect_ops", "join <route>"),
    "cultivate": ("cultivate_ops", "meditate 4"),
    "retreat": ("cultivate_ops", "retreat 8"),
    "travel": ("travel_ops", "go <地点>"),
    "explore": ("travel_ops", "explore"),
    "fight": ("battle_ops", "fight <目标>"),
    "use_skill": ("battle_ops", "skill <已学招式>"),
    "use_item": ("bag_ops", "use <物品>"),
    "craft": ("refine_ops", "craft <配方> 1"),
    "talk": ("npc_ops", "talk <人物>"),
    "trade": ("market_ops", "buy <物品> 1"),
    "accept_quest": ("quest_ops", "accept <任务>"),
    "quest_step": ("quest_ops", "step <任务>"),
    "submit_quest": ("quest_ops", "submit <任务>"),
    "breakthrough": ("realm_ops", "breakthrough"),
    "incident_resolve": ("world_ops", "resolve <编号> <选项>"),
    "prepare_formation": ("battle_ops", "formation ward"),
    "manage_beast": ("npc_ops", "beast feed"),
    "beast_evolve": ("npc_ops", "beast evolve"),
    "sect_hall": ("sect_ops", "hall"),
    "redeem": ("sect_ops", "redeem <物品>"),
    "rename": ("cultivator_ops", "rename <道号>"),
}


def manual():
    return {
        "world": "灵汐岛",
        "principle": "AI选择行动；代码判定结果。网页与MCP同一凭证、同一修士。",
        "commands": HELP,
        "routes": {k: v["name"] for k, v in CONTENT["routes"].items()},
        "first_loop": [
            "cultivator_ops sheet",
            "sect_ops join qingxiao",
            "cultivate_ops meditate 4",
            "npc_ops talk 林青枝 teach",
            "quest_ops accept trial_qingxiao",
            "travel_ops go 青竹林",
            "battle_ops fight wolf",
            "battle_ops skill 青云剑诀",
        ],
        "birth": CONTENT["birth"],
        "incidents": "world_ops incidents 查看2至3个处置选项，world_ops resolve 编号 care|materials|self。",
        "request_id": "修改操作可附request_id，重试原请求编号与参数会返回同一结果；编号不可用于其他命令。",
        "realm": "炼气/筑基/金丹/元婴，各初期、中期、后期、圆满。筑基材料为筑基丹；秘境一周前两日开放。跨大境界突破须先斩心魔：它会用你的招式、反噬你的灵力，斩之心魔方证大道；金丹渡元婴另有三重雷劫，凝罡御雷可挡、不动如山硬抗、引雷淬体搏造化，渡劫失败修为重创并留伤。",
    }


def resolve(value, catalog):
    if value in catalog:
        return value
    found = [k for k, v in catalog.items() if v.get("name") == value]
    require(len(found) == 1, "未知或有歧义的名称，请先查看列表并使用ID")
    return found[0]


def parse(group, command, game):
    require(group in HELP, "未知聚合工具")
    require(
        isinstance(command, str) and len(command) <= 512, "command须为512字以内字符串"
    )
    try:
        words = shlex.split(command)
    except ValueError:
        raise RuleError("引号不完整")
    if not words:
        return "help", {}
    action = words.pop(0).lower()
    if action == "help":
        return "help", {}

    def take():
        require(bool(words), "参数不足，请调用help")
        return words.pop(0)

    def number(default=1):
        if not words:
            return default
        value = take()
        require(value.isascii() and value.isdecimal(), "数量须为整数")
        return int(value)

    def finish(tool, **args):
        require(not words, "存在多余参数，不能通过文本改变规则")
        return tool, args

    def item():
        return resolve(take(), CONTENT["items"])

    def npc():
        return resolve(take(), ISLAND["npcs"])

    if group == "cultivator_ops":
        if action == "sheet":
            return finish("get_self")
        if action == "rename":
            return finish("rename", name=take())
        if action == "history":
            return finish("inspect_history", limit=number(20))
    if action == "incidents" and group in ("cultivator_ops", "world_ops"):
        return finish("incident_list")
    if action == "resolve" and group in ("cultivator_ops", "world_ops"):
        return finish("incident_resolve", incident=number(), choice=take())
    if group == "sect_ops":
        if action == "status":
            return finish("inspect_route")
        if action == "hall":
            return finish("sect_hall")
        if action == "redeem":
            return finish("redeem", item=item(), amount=number(1))
        if action == "join":
            return finish("choose_route", route=resolve(take(), CONTENT["routes"]))
        if action == "task":
            return parse("quest_ops", " ".join(words), game)
    if group == "cultivate_ops":
        if action == "status":
            return finish("get_self")
        if action == "meditate":
            return finish("cultivate", method=game.player["method"], duration=number(1))
        if action == "method":
            return finish(
                "cultivate",
                method=resolve(take(), CONTENT["techniques"]),
                duration=number(1),
            )
        if action == "retreat":
            return finish("retreat", duration=number(8))
        if action == "learn":
            return finish(
                "learn_technique", technique=resolve(take(), CONTENT["techniques"])
            )
        if action == "ask":
            return finish("talk", npc=npc(), topic="teach")
    if group == "travel_ops":
        if action == "map":
            return finish("get_world")
        if action == "go":
            return finish(
                "travel",
                destination=resolve(take(), ISLAND["locations"]),
                node=take() if words else None,
            )
        if action == "explore":
            return finish("explore")
    if group == "battle_ops":
        if action == "status":
            return finish("get_self")
        if action == "fight":
            return finish("fight", target=resolve(take(), game._local_enemies()))
        if action == "skill":
            return finish("use_skill", skill=resolve(take(), CONTENT["skills"]))
        if action == "item":
            return finish("use_item", item=item())
        if action == "retreat":
            return finish("retreat")
        if action == "formation":
            return finish("prepare_formation", formation=take())
    if group == "bag_ops":
        if action == "list":
            return finish("get_self")
        if action in ("use", "equip"):
            return finish("use_item", item=item())
        if action == "ledger":
            return finish("item_ledger", item=item() if words else None)
    if group == "refine_ops":
        if action == "list":
            return "recipes", {}
        if action in ("pill", "weapon", "craft"):
            value = take()
            recipes = CONTENT["recipes"]
            if value not in recipes:
                out = resolve(value, CONTENT["items"])
                value = out if out in recipes else None
            require(value in recipes, "没有对应配方")
            return finish("craft", recipe=value, amount=number())
    if group == "npc_ops":
        if action == "list":
            return finish("npc_list")
        if action == "talk":
            return finish("talk", npc=npc(), topic=take() if words else "greeting")
        if action == "gift":
            return finish("talk", npc=npc(), topic="gift", item=item())
        if action == "track":
            return finish("track", target=take())
        if action == "beast":
            sub = take()
            if sub == "train":
                return finish("beast_train")
            args = {"action": sub}
            if sub == "contract":
                args["beast"] = take()
            if sub == "stance":
                args["stance"] = take()
            return finish("manage_beast", **args)
    if group == "quest_ops":
        if action == "list":
            return finish("quest_list")
        if action in ("accept", "submit", "step"):
            quest = resolve(take(), CONTENT["quests"] | ISLAND["quests"])
            if action == "step":
                return finish(
                    "quest_step", quest=quest, branch=take() if words else None
                )
            return finish(
                "accept_quest" if action == "accept" else "submit_quest", quest=quest
            )
    if group == "market_ops":
        if action in ("list", "auction"):
            return finish("market_catalog")
        if action in ("buy", "sell"):
            return finish("trade", item=item(), quantity=number(), side=action)
        if action == "bid":
            return finish("market_bid", listing=take(), amount=number())
    if group == "realm_ops":
        if action == "status":
            return finish("get_self")
        if action == "breakthrough":
            return finish("breakthrough")
        if action == "enter":
            return finish("travel", destination="secret")
        if action == "leave":
            return finish("travel", destination="lake")
    if group == "world_ops":
        if action == "status":
            return finish("get_world")
        if action == "log":
            return finish("world_log", limit=number(20))
    raise RuleError("未知command，请调用本工具help")


def dispatch(game, group, command="", request_id=None):
    if group == "relay_manual":
        return {
            "ok": True,
            "result": manual(),
            "changes": {},
            "new_events": [],
            "available_actions": [],
        }
    defaults = {
        "cultivator_ops": "sheet",
        "sect_ops": "status",
        "cultivate_ops": "status",
        "travel_ops": "map",
        "battle_ops": "status",
        "bag_ops": "list",
        "refine_ops": "list",
        "npc_ops": "list",
        "quest_ops": "list",
        "market_ops": "list",
        "realm_ops": "status",
        "world_ops": "status",
    }
    try:
        tool, args = parse(group, command.strip() or defaults.get(group, "help"), game)
        if tool == "help":
            return {
                "ok": True,
                "result": HELP[group],
                "changes": {},
                "new_events": [],
                "available_actions": [],
            }
        if tool == "recipes":
            return {
                "ok": True,
                "result": CONTENT["recipes"],
                "changes": {},
                "new_events": [],
                "available_actions": [],
            }
        result = game.call(tool, request_id=request_id, **args)
        result["available_actions"] = [
            {"tool": HINTS[a][0], "command": HINTS[a][1]}
            for a in result.get("available_actions", [])
            if a in HINTS
        ]
        result.pop("availableActions", None)
        return result
    except RuleError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "changes": {},
            "new_events": [],
            "available_actions": [{"tool": group, "command": "help"}],
        }


async def _call_ops(fn, *args, **kwargs):
    for attempt in range(5):
        try:
            return await run_in_threadpool(fn, *args, **kwargs)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            if attempt == 4:
                logger.warning(
                    "database busy, giving up after 5 retries: %s",
                    args[0] if args else getattr(fn, "__name__", fn),
                )
                return {
                    "ok": False,
                    "error": "数据库正忙，请用相同request_id稍后重试。",
                }
            await asyncio.sleep(0.08 * (2**attempt))
