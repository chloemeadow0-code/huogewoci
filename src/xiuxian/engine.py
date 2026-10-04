from __future__ import annotations
import inspect
import copy
import json
import logging
import threading
from pathlib import Path
from lorekit.db import init_schema, get_db
from .data import load_pack
from .rules import require, bounded_int, RuleError, new_rng_key, rng_value
from datetime import datetime, timezone
from .models import Player, StatusEffect
from .routes import RouteRules
from .birth import generate_root, generate_aptitude

logger = logging.getLogger(__name__)

LOCK = threading.RLock()
CONTENT = load_pack("content")

TOOLS = (
    "get_self",
    "get_world",
    "cultivate",
    "travel",
    "explore",
    "talk",
    "fight",
    "use_skill",
    "use_item",
    "craft",
    "trade",
    "accept_quest",
    "submit_quest",
    "breakthrough",
    "retreat",
    "inspect_history",
    "choose_route",
    "inspect_route",
    "learn_technique",
    "prepare_formation",
    "manage_beast",
    "track",
    "rename",
)
READ_ONLY = {"get_self", "get_world", "inspect_history", "inspect_route"}
LOCATIONS = CONTENT["locations"]
SKILLS = CONTENT["skills"]
NPCS = CONTENT["npcs"]
ENEMIES = CONTENT["enemies"]
QUESTS = CONTENT["quests"]
PRICES = CONTENT["prices"]
RECIPES = CONTENT["recipes"]


class Game(RouteRules):
    pack = CONTENT
    _extra_minutes = 0

    def __init__(self, db_path, player_key=None, player_name="无名修士"):
        self.path = str(Path(db_path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.key = player_key or "local"
        with LOCK:
            init_schema(self.path)
            self.db = get_db(self.path)
            row = self.db.execute(
                "SELECT id FROM sessions WHERE system_type='xiuxian'"
            ).fetchone()
            if row:
                self.sid = row[0]
                self.state = json.loads(
                    self.db.execute(
                        "SELECT value FROM session_meta WHERE session_id=? AND key='xiuxian_state'",
                        (self.sid,),
                    ).fetchone()[0]
                )
                require(self.state["version"] == 1, "不支持的存档版本")
            else:
                self.sid = self.db.execute(
                    "INSERT INTO sessions(name,setting,system_type) VALUES ('青云问道','修仙','xiuxian')"
                ).lastrowid
                self.state = {
                    "version": 1,
                    "tick": 0,
                    "minutes": 0,
                    "rng": 1234567,
                    "rngKey": new_rng_key(),
                    "players": {},
                    "events": [],
                    "realm": {"cycle": 0},
                }
            if self.key not in self.state["players"]:
                self.state["players"][self.key] = self.new_player(player_name)
            self._upgrade()
            self._store()

    @staticmethod
    def new_player(player_name):
        return dict(
            route_required=True,
            name=player_name,
            sect="青云宗",
            realm="炼气",
            level=1,
            **generate_root(CONTENT["birth"]),
            aptitude=generate_aptitude(CONTENT["birth"]),
            method="青云吐纳诀",
            cultivation=0,
            hp=100,
            mp=50,
            max_hp=100,
            max_mp=50,
            stones=30,
            reputation=0,
            location="sect",
            inventory={"herb": 2, "potion": 2},
            skills=["strike", "guard"],
            relationships={},
            quests={},
            kills={},
            battle=None,
            history=[],
        )

    @property
    def player(self):
        return self.state["players"][self.key]

    def close(self):
        self.db.close()

    def _store(self):
        self.db.execute(
            "INSERT INTO session_meta(session_id,key,value) VALUES (?,'xiuxian_state',?) ON CONFLICT(session_id,key) DO UPDATE SET value=excluded.value",
            (self.sid, json.dumps(self.state, ensure_ascii=False)),
        )
        self.db.commit()

    def _load_state(self):
        row = self.db.execute(
            "SELECT value FROM session_meta WHERE session_id=? AND key='xiuxian_state'",
            (self.sid,),
        ).fetchone()
        return json.loads(row[0])

    def call(self, tool, **kwargs):
        with LOCK:
            self.state = self._load_state()
            before = copy.deepcopy(self.state)
            self._rolls = []
            self._extra_minutes = 0
            try:
                require(tool in TOOLS, "未知工具")
                require(
                    self.player.get("route") is not None
                    or not self.player.get("route_required", False)
                    or tool in READ_ONLY | {"choose_route", "rename"},
                    "请先choose_route选择修行路线",
                )
                bound = inspect.signature(getattr(self, tool)).bind(**kwargs)
                bound.apply_defaults()
                kwargs = dict(bound.arguments)
                require(
                    not self.player["battle"]
                    or tool
                    in READ_ONLY | {"use_skill", "use_item", "retreat", "rename"},
                    "战斗中只能使用招式、物品或撤退",
                )
                start = self.state["minutes"]
                location = self.player["location"]
                in_battle = self.player["battle"] is not None
                result = getattr(self, tool)(**kwargs)
                if tool not in READ_ONLY:
                    if tool != "rename":
                        self.state["tick"] += 1
                        self._advance(tool, kwargs, in_battle)
                    old_player = before["players"][self.key]
                    delta = {
                        k: self.player["inventory"].get(k, 0)
                        - old_player["inventory"].get(k, 0)
                        for k in set(self.player["inventory"])
                        | set(old_player["inventory"])
                        if self.player["inventory"].get(k, 0)
                        != old_player["inventory"].get(k, 0)
                    }
                    self.player["history"].append(
                        {
                            "changes": {
                                "items": delta,
                                "hp": self.player["hp"] - old_player["hp"],
                                "stones": self.player["stones"] - old_player["stones"],
                            },
                            "tick": self.state["tick"],
                            "time": start,
                            "location": location,
                            "action": tool,
                            "arguments": kwargs,
                            "result": copy.deepcopy(result),
                            "random": copy.deepcopy(self._rolls),
                        }
                    )
                    self._store()
                return {
                    "ok": True,
                    "result": copy.deepcopy(result),
                    "random": copy.deepcopy(self._rolls),
                    "availableActions": self.available_actions(),
                }
            except RuleError as error:
                self.db.rollback()
                self.state = before
                return {"ok": False, "error": str(error)}
            except (TypeError, KeyError) as error:
                self.db.rollback()
                self.state = before
                logger.exception(
                    "game call failed: tool=%s player=%s kwargs=%s tick=%s",
                    tool,
                    self.key,
                    kwargs,
                    self.state["tick"],
                )
                return {"ok": False, "error": str(error)}
            except Exception:
                self.db.rollback()
                self.state = before
                logger.exception(
                    "game call failed: tool=%s player=%s kwargs=%s tick=%s",
                    tool,
                    self.key,
                    kwargs,
                    self.state["tick"],
                )
                raise

    def rename(self, name: str):
        require(isinstance(name, str), "道号须为2至24字")
        name = name.strip()
        require(
            2 <= len(name) <= 24 and all(ord(c) >= 32 for c in name),
            "道号须为2至24字，不得包含控制字符",
        )
        previous = self.player["name"]
        self.player["name"] = name
        return {"previousName": previous, "name": name}

    def inspect_history(self, limit: int = 20):
        return self.player["history"][-bounded_int(limit, 1, 100) :]

    def _add(self, item, n):
        inv = self.player["inventory"]
        inv[item] = inv.get(item, 0) + n

    def _consume(self, item, n):
        require(self.player["inventory"].get(item, 0) >= n, "物品不足")
        self._add(item, -n)
        if self.player["inventory"][item] == 0:
            for slot, equipped in self.player["equipment"].items():
                if equipped == item:
                    self.player["equipment"][slot] = None

    def trade(self, item: str, quantity: int = 1, side: str = "buy"):
        quantity = bounded_int(quantity, 1, 100)
        p = self.player
        require(p["location"] in ("town", "sect"), "交易需到宗门商店或青石镇")
        require(item in PRICES and side in ("buy", "sell"), "无效交易")
        price = PRICES[item] if side == "buy" else max(1, PRICES[item] // 2)
        if side == "sell":
            price = self._percent(price, self._bonus("sellBonus"))
        price = self._shop_price(item, side, price)
        if side == "buy":
            require(p["stones"] >= price * quantity, "灵石不足")
            p["stones"] -= price * quantity
            self._add(item, quantity)
        else:
            require(item not in p["equipment"].values(), "已装备物品不能出售")
            self._consume(item, quantity)
            p["stones"] += price * quantity
        self._after_trade(item, side)
        return dict(
            stones=p["stones"], item=item, quantity=quantity, side=side, unitPrice=price
        )

    def accept_quest(self, quest: str):
        require(
            quest in QUESTS and self.player["location"] == QUESTS[quest]["location"],
            "请到任务发布地领取任务",
        )
        self._route_quest(quest)
        require(quest not in self.player["quests"], "任务已领取")
        self.player["quests"][quest] = "active"
        return QUESTS[quest]

    def _upgrade(self):
        self.state.setdefault("rngKey", new_rng_key())
        p = self.player
        defaults = dict(
            id=self.key,
            stage=0,
            qi=p.get("mp", 50),
            maxQi=p.get("max_mp", 50),
            spirit=10,
            strength=16,
            agility=12,
            defense=3,
            techniques=["basic_meditation"],
            equipment={
                "weapon": None,
                "armor": None,
                "accessory": None,
                "artifact": None,
            },
            statusEffects=[],
            createdAt=datetime.now(timezone.utc).isoformat(),
            explores=0,
            realmVisit=-1,
            realmLoot=[],
            cooldownUntil=0,
            rootElements=["木", "火"],
        )
        for k, v in defaults.items():
            p.setdefault(k, v)
        p.pop("mp", None)
        p.pop("max_mp", None)
        if p["method"] not in CONTENT["techniques"]:
            p["method"] = "basic_meditation"
        self._upgrade_routes()

    def _roll(self, purpose):
        # Keyed roll stream: the save only stores a counter and a server-side
        # key; clients see individual rolls, not a state they can roll forward.
        self.state["rng"] += 1
        value = rng_value(self.state["rngKey"], self.state["rng"])
        self._rolls.append({"purpose": purpose, "value": value})
        return value

    def _advance(self, tool, args, in_battle=False):
        minutes = (
            60 * args.get("duration", args.get("hours", 1))
            if tool in ("cultivate", "retreat")
            else 2 if tool in ("use_skill", "use_item") else 60
        )
        if in_battle:
            minutes = 2
        minutes += self._extra_minutes
        self._extra_minutes = 0
        old_day = self.state["minutes"] // 1440
        self.state["minutes"] += minutes
        self._advance_beasts(self.state["minutes"] - minutes, self.state["minutes"])
        self.state["realm"]["cycle"] = self.state["minutes"] // (7 * 1440)
        for day in range(old_day + 1, self.state["minutes"] // 1440 + 1):
            e = copy.deepcopy(
                CONTENT["events"][
                    (self._roll("world_event") - 1) % len(CONTENT["events"])
                ]
            )
            e["day"] = day + 1
            self.state["events"].append(e)

    def available_actions(self):
        p = self.player
        if p["route"] is None and p.get("route_required", False):
            return [
                "get_self",
                "get_world",
                "inspect_history",
                "rename",
                "inspect_route",
                "choose_route",
            ]
        if p["battle"]:
            return [
                "get_self",
                "get_world",
                "inspect_history",
                "rename",
                "use_skill",
                "use_item",
                "retreat",
            ]
        actions = [
            "get_self",
            "get_world",
            "inspect_history",
            "rename",
            "travel",
            "talk",
            "use_item",
        ]
        if p["location"] == "sect":
            actions += [
                "cultivate",
                "retreat",
                "breakthrough",
                "craft",
                "accept_quest",
                "submit_quest",
                "fight",
                "trade",
            ]
        if p["location"] == "town":
            actions += ["trade", "accept_quest", "submit_quest"]
        if p["location"] in ("wild", "realm"):
            actions += ["explore", "fight"]
        actions.append("inspect_route")
        if p["location"] in ("sect", "town"):
            actions.append("learn_technique")
        if p["route"] is None:
            actions.append("choose_route")
        if p["route"] == "xuanheng" and p["location"] in ("sect", "wild", "realm"):
            actions.append("prepare_formation")
        if (
            p["route"] == "fuyao"
            or self._is_rogue()
            and "beast_lore" in p["techniques"]
        ):
            actions.append("manage_beast")
        if p["location"] == "wild":
            actions.append("track")
        if self._is_rogue():
            if p["location"] == "town":
                actions += ["cultivate", "craft", "retreat", "breakthrough"]
            actions = [
                a
                for a in actions
                if not (
                    a in ("cultivate", "craft", "retreat", "breakthrough")
                    and p["location"] != "town"
                )
            ]
        return list(dict.fromkeys(actions))

    def _realm_index(self):
        return next(
            i
            for i, r in enumerate(CONTENT["realms"])
            if r["name"] == self.player["realm"]
        )

    def _current_event(self):
        return (
            self.state["events"][-1]
            if self.state["events"]
            and self.state["events"][-1]["day"] == self.state["minutes"] // 1440 + 1
            else {}
        )

    def get_self(self):
        p = copy.deepcopy(self.player)
        p.pop("history", None)
        p["realmStage"] = ["初期", "中期", "后期", "圆满"][p["stage"]]
        p["cultivationRequired"] = CONTENT["realms"][self._realm_index()]["cost"] * (
            p["stage"] + 1
        )
        p["money"] = p["stones"]
        for relation in p["relationships"].values():
            relation.pop("dialogueState", None)
        p["effectiveStats"] = self._stats(self.player)
        return p

    def get_world(self):
        p = self.player
        loc = LOCATIONS[p["location"]]
        phase = self.state["minutes"] % (7 * 1440)
        return self._route_world(
            dict(
                time={
                    "day": self.state["minutes"] // 1440 + 1,
                    "hour": self.state["minutes"] // 60 % 24,
                },
                region=p["location"],
                location=loc,
                events=[self._current_event()] if self._current_event() else [],
                npcs={k: v for k, v in NPCS.items() if self._npc_present(k)},
                enemies={
                    k: v for k, v in ENEMIES.items() if v["location"] == p["location"]
                },
                shop=PRICES if p["location"] in ("town", "sect") else {},
                skills={k: SKILLS[k] for k in p["skills"]},
                quests={
                    k: v for k, v in QUESTS.items() if v["location"] == p["location"]
                },
                realm={
                    "open": phase < 2 * 1440,
                    "cycle": self.state["realm"]["cycle"],
                    "requiredRealm": "筑基",
                    "nextOpenMinutes": 0 if phase < 2 * 1440 else 7 * 1440 - phase,
                },
                nearbyActions=self.available_actions(),
            )
        )

    def _npc_present(self, npc):
        if npc not in NPCS:
            return False
        n = NPCS[npc]
        hour = self.state["minutes"] // 60 % 24
        return (
            n["location"] == self.player["location"]
            and n["schedule"]["start"] <= hour < n["schedule"]["end"]
            and self._current_event().get("absent") != npc
        )

    def _stats(self, actor):
        stats = {k: actor[k] for k in ("strength", "defense", "agility", "spirit")}
        if actor is self.player:
            equip_boost = self._bonus("equipmentPower")
            for item in actor["equipment"].values():
                if item:
                    for k, v in CONTENT["items"][item]["effects"].items():
                        stats[k] = stats.get(k, 0) + (
                            self._percent(v, equip_boost) if equip_boost else v
                        )
            for k, v in CONTENT["techniques"][actor["method"]][
                "passiveEffects"
            ].items():
                if k in stats:
                    stats[k] += v
        for e in actor["statusEffects"]:
            if e["type"] == "haste":
                stats["agility"] += e["value"]
            if e["type"] == "slow":
                stats["agility"] = max(1, stats["agility"] - e["value"])
            if e["type"] == "weakness":
                stats["strength"] = max(1, stats["strength"] - e["value"])
        return stats

    def cultivate(self, method: str = "basic_meditation", duration: int = 1):
        duration = bounded_int(duration, 1, 72)
        p = self.player
        require(self._can_cultivate(), "需在宗门或散修客舍修炼")
        require(method in p["techniques"], "尚未学会功法")
        require(
            not any(e["type"] == "injury" for e in p["statusEffects"]),
            "重伤需先闭关疗伤",
        )
        t = CONTENT["techniques"][method]
        require(self._realm_index() >= t["requiredRealm"], "境界不足")
        p["method"] = method
        p["maxQi"] = 50 + self._realm_index() * 20 + p["stage"] * 5 + t["qiBonus"]
        affinity = 2 if set(p["rootElements"]) & set(t["compatibleRoots"]) else 0
        gain = duration * (
            4
            + p["aptitude"]
            + t["cultivationBonus"]
            + p["techniqueLevels"].get(method, 1)
            - 1
            + affinity
            + self._realm_index()
            + self._current_event().get("cultivationBonus", 0)
        )
        gain = self._route_cultivation_gain(gain, method)
        p["cultivation"] += gain
        p["qi"] = min(p["maxQi"], p["qi"] + duration * 5)
        return dict(gained=gain, cultivation=p["cultivation"], duration=duration)

    def travel(self, destination: str, node: str | None = None):
        p = self.player
        require(destination in LOCATIONS, "未知地点")
        self._route_travel(destination, node)
        require(
            destination == p["location"]
            or destination in LOCATIONS[p["location"]]["exits"],
            "地点不相连",
        )
        require(node is None or node in LOCATIONS[destination]["nodes"], "未知地图节点")
        if destination == "realm" and p["location"] != "realm":
            require(self._realm_index() >= 1, "秘境需筑基")
            require(self.state["minutes"] % (7 * 1440) < 2 * 1440, "秘境关闭")
            require(p["realmVisit"] != self.state["realm"]["cycle"], "本周期已进入秘境")
            p["realmVisit"] = self.state["realm"]["cycle"]
            p["realmLoot"] = []
        p["location"] = destination
        p["node"] = node or LOCATIONS[destination]["nodes"][0]
        self._blackmarket_refresh()
        return dict(location=destination, node=p["node"])

    def explore(self):
        p = self.player
        require(p["location"] in ("wild", "realm"), "这里没有探索点")
        require(
            self._current_event().get("blocked") != p["location"],
            "区域因坍塌暂时无法探索",
        )
        require(p["hp"] > 10, "气血不足")
        p["explores"] += 1
        event = self._explore_route_event()
        if p["location"] == "realm":
            require(self.state["minutes"] % (7 * 1440) < 2 * 1440, "秘境已关闭，请离开")
            node = p.get("node", "入口")
            require(node not in p["realmLoot"], "该节点本周期已探索")
            p["realmLoot"].append(node)
        result = {"event": event}
        if event == "herb":
            self._add("herb", 1 + self._current_event().get("extraHerb", 0))
            result["item"] = "herb"
        elif event == "enemy":
            enemies = [k for k, v in ENEMIES.items() if v["location"] == p["location"]]
            target = enemies[(self._roll("encounter") - 1) % len(enemies)]
            result["battle"] = self._open_battle(target, surprise=True)
        elif event == "npc":
            result["npcs"] = [k for k in NPCS if self._npc_present(k)]
        elif event == "chest":
            self._add("iron", 1)
            p["stones"] += 8
            result["loot"] = {"iron": 1, "stones": 8}
        elif event in ("trap", "anomaly"):
            pass
        elif event == "cave":
            self._add("herb", 2)
            result["item"] = "herb"
        self._explore_extra(event, result)
        p["hp"] = max(1, p["hp"] - self._current_event().get("exploreDamage", 0))
        return result

    def talk(self, npc: str, topic: str = "greeting", item: str | None = None):
        require(self._npc_present(npc), "人物不在这里")
        require(
            topic
            in (
                "greeting",
                "quest",
                "teach",
                "rumor",
                "gift",
                "help",
                "insult",
                "spar",
            ),
            "未知交谈选项",
        )
        p = self.player
        r = p["relationships"].setdefault(
            npc, {"friendliness": 0, "trust": 0, "hostility": 0, "dialogueState": []}
        )
        if topic == "gift":
            require(item in CONTENT["items"], "未知礼物")
            self._consume(item, 1)
            r["friendliness"] += 3
            r["trust"] += 1
        elif topic == "insult":
            r["hostility"] += 3
            r["trust"] -= 2
        elif topic == "teach":
            require(
                npc in ("elder", "hermit")
                and p["reputation"] >= 5
                and r["hostility"] < 3,
                "尚未获得传授资格",
            )
            technique = (
                self._route().get("technique")
                if npc == "elder" and p["route"]
                else "verdant" if npc == "elder" else "sword_art"
            )
            require(technique is not None, "散修需寻找私人传承")
            self._adopt_discipline(
                CONTENT["techniques"][technique].get("school", "general")
            )
            if technique not in p["techniques"]:
                p["techniques"].append(technique)
            p["skills"] = list(
                dict.fromkeys(p["skills"] + self._route().get("skills", list(SKILLS)))
            )
        elif topic == "spar":
            require(npc == "elder", "这里不能切磋")
            return self.fight("sparring")
        elif topic == "help":
            require(r["trust"] >= 2, "尚未取得信任")
            p["hp"] = min(
                p["max_hp"], p["hp"] + self._percent(10, self._bonus("healingEffect"))
            )
        else:
            r["friendliness"] = min(20, r["friendliness"] + 1)
            r["trust"] = min(10, r["trust"] + 1)
        r["dialogueState"].append({"topic": topic, "time": self.state["minutes"]})
        return dict(
            npc=(
                self._route().get("teacher", NPCS[npc]["name"])
                if npc == "elder" and p["route"]
                else NPCS[npc]["name"]
            ),
            relationship=r,
            message="筑基前可购买筑基丹；筑基后灵溪秘境每七日开放两日，每周期仅可进入一次。",
            techniques=p["techniques"],
        )

    def _effect(self, actor, kind, value, duration, source):
        require(kind in CONTENT["status_types"], "未知状态")
        actor["statusEffects"] = [
            e for e in actor["statusEffects"] if e["type"] != kind
        ]
        actor["statusEffects"].append(
            dict(type=kind, value=value, duration=duration, source=source)
        )

    def fight(self, target: str):
        return self._open_battle(target, surprise=False)

    def _open_battle(self, target: str, surprise: bool):
        p = self.player
        require(p["battle"] is None, "已经在战斗中")
        require(
            target in ENEMIES and ENEMIES[target]["location"] == p["location"],
            "敌人不在这里",
        )
        require(
            p["hp"] > 0 and not any(e["type"] == "injury" for e in p["statusEffects"]),
            "重伤需先疗养",
        )
        if p["location"] == "realm":
            require(self.state["minutes"] % (7 * 1440) < 2 * 1440, "秘境关闭")
            require("boss:" + target not in p["realmLoot"], "此敌人本周期已击败")
        e = copy.deepcopy(ENEMIES[target])
        e.update(max_hp=e["hp"], spirit=8, statusEffects=[], cooldowns={})
        p["battle"] = dict(target=target, enemy=e, round=0, cooldowns={})
        if p["route"] == "fuyao" and target in CONTENT["protected_enemies"]:
            self._violate("猎杀宗门保护种群")
        self._begin_route_battle(surprise)
        return copy.deepcopy(p["battle"])

    def _enemy_skill(self, e, b):
        if (
            e["hp"] < e["max_hp"] // 2
            and "heal" in e["skills"]
            and e["qi"] >= SKILLS["heal"]["cost"]
            and b["round"] >= e["cooldowns"].get("heal", 0)
        ):
            return "heal"
        if (
            "poison" in e["skills"]
            and e["qi"] >= SKILLS["poison"]["cost"]
            and b["round"] >= e["cooldowns"].get("poison", 0)
        ):
            return "poison"
        return "strike"

    def _apply_skill(
        self, actor, target, skill, rank, target_rank, cooldowns, round_number
    ):
        from .rules import damage, hit_chance, escape_chance

        s = SKILLS[skill]
        stats = self._stats(actor)
        other = self._stats(target)
        if any(e["type"] in ("freeze", "stun", "root") for e in actor["statusEffects"]):
            return {"skill": skill, "skipped": "controlled"}
        if actor is self.player:
            self._material_for_skill(skill)
        power, accuracy, route_info = self._combat_power(actor, skill, round_number)
        actor["qi"] -= s["cost"]
        cooldowns[skill] = round_number + s["cooldown"] + 1
        result = {"skill": skill, "category": s["type"], **route_info}
        if s["type"] == "escape":
            result["escaped"] = self._roll("escape") <= escape_chance(
                stats["agility"], other["agility"], s["power"]
            )
            return result
        if s["type"] in ("attack", "debuff", "control"):
            if self._roll("hit") > hit_chance(
                accuracy, stats["agility"], other["agility"]
            ):
                result["hit"] = False
                return result
            result["hit"] = True
        if s["type"] == "attack":
            hit = damage(power, stats["strength"], other["defense"], rank - target_rank)
            hit = self._combat_damage(actor, skill, hit, route_info)
            result.update(route_info)
            shields = [e for e in target["statusEffects"] if e["type"] == "shield"]
            if shields:
                absorbed = min(hit, shields[0]["value"])
                hit -= absorbed
                shields[0]["value"] -= absorbed
            target["hp"] = max(0, target["hp"] - hit)
            result["damage"] = hit
            if s.get("effect") and self._roll("skill_ailment") <= s.get(
                "effectChance", 0
            ):
                self._effect(
                    target,
                    s["effect"],
                    max(1, power // 4),
                    s.get("duration", 2),
                    skill,
                )
                result["ailment"] = s["effect"]
        elif s["type"] == "heal":
            if not any(e["type"] == "heal_block" for e in actor["statusEffects"]):
                actor["hp"] = min(actor["max_hp"], actor["hp"] + power)
        elif s["type"] == "defense":
            self._effect(actor, "shield", power, s["duration"], skill)
        elif s["type"] in ("buff", "movement"):
            self._effect(actor, "haste", power, s["duration"], skill)
        elif s["type"] in ("control", "debuff"):
            if self._roll("effect") <= s["effectChance"]:
                self._effect(
                    target, s.get("effect", "stun"), max(1, power), s["duration"], skill
                )
                result["effect"] = s.get("effect", "stun")
        return result

    def _end_effects(self, actor):
        for e in actor["statusEffects"]:
            if e["type"] in ("poison", "bleed", "burn"):
                actor["hp"] = max(0, actor["hp"] - e["value"])
            if e["type"] == "qi_regen":
                actor["qi"] = min(actor["maxQi"], actor["qi"] + e["value"])
            if e["type"] != "injury":
                e["duration"] -= 1
        actor["statusEffects"] = [
            e
            for e in actor["statusEffects"]
            if e["duration"] > 0 and (e["type"] != "shield" or e["value"] > 0)
        ]

    def use_skill(self, skill: str):
        p = self.player
        b = p["battle"]
        require(b is not None, "没有正在进行的战斗")
        require(skill in p["skills"] and skill in SKILLS, "未学会招式")
        s = SKILLS[skill]
        require(p["qi"] >= s["cost"], "灵力不足")
        require(b["round"] + 1 >= b["cooldowns"].get(skill, 0), "招式冷却中")
        require(self._realm_index() >= s["requirements"]["realm"], "境界不足")
        return self._turn(skill)

    def _pays_victory_reward(self, target, first_kill):
        """Whether a victory pays stones and drops; overridable per world."""
        return True

    def _turn(self, skill=None, item=None, escape=False):
        from .rules import escape_chance

        p = self.player
        b = p["battle"]
        e = b["enemy"]
        b["round"] += 1
        log = []
        rank = self._realm_index()
        first = self._stats(p)["agility"] >= self._stats(e)["agility"]
        for side in (("player", "enemy") if first else ("enemy", "player")):
            if p["hp"] <= 0 or e["hp"] <= 0:
                break
            if side == "enemy":
                choice = self._enemy_skill(e, b)
                log.append(
                    {
                        "actor": "enemy",
                        **self._apply_skill(
                            e, p, choice, e["realm"], rank, e["cooldowns"], b["round"]
                        ),
                    }
                )
            else:
                controlled = any(
                    x["type"] in ("freeze", "stun", "root") for x in p["statusEffects"]
                )
                if item:
                    if controlled:
                        log.append({"actor": "player", "skipped": "controlled"})
                    else:
                        self._consume(item, 1)
                        self._restore(item)
                        log.append({"actor": "player", "item": item})
                elif escape:
                    escape_odds = escape_chance(
                        self._stats(p)["agility"], self._stats(e)["agility"]
                    ) + self._bonus("escapeBonus")
                    escaped = not controlled and self._roll("retreat") <= min(
                        95, max(10, escape_odds)
                    )
                    log.append({"actor": "player", "escaped": escaped})
                    if escaped:
                        p["battle"] = None
                        p["location"] = self._recovery_location()
                        if (
                            p["route"] == "qingxiao"
                            and p["quests"].get("escort") == "active"
                        ):
                            self._violate("护送任务中擅自脱队")
                        return self._finish_route_turn(
                            skill,
                            log,
                            {"outcome": "escaped", "log": log, "hp": p["hp"]},
                            b,
                        )
                else:
                    outcome = self._apply_skill(
                        p, e, skill, rank, e["realm"], b["cooldowns"], b["round"]
                    )
                    log.append({"actor": "player", **outcome})
                    if outcome.get("escaped"):
                        p["battle"] = None
                        p["location"] = self._recovery_location()
                        if (
                            p["route"] == "qingxiao"
                            and p["quests"].get("escort") == "active"
                        ):
                            self._violate("护送任务中擅自脱队")
                        return self._finish_route_turn(
                            skill,
                            log,
                            {"outcome": "escaped", "log": log, "hp": p["hp"]},
                            b,
                        )
        self._pet_turn(e, log)
        self._end_effects(p)
        self._end_effects(e)
        result = {
            "round": b["round"],
            "log": log,
            "hp": p["hp"],
            "qi": p["qi"],
            "enemyHp": e["hp"],
        }
        if p["hp"] <= 0:
            loss = min(10, p["stones"])
            p["stones"] -= loss
            p["cultivation"] = max(0, p["cultivation"] - 10)
            dropped = {}
            for k in sorted(p["inventory"]):
                if p["inventory"][k] > 0:
                    dropped[k] = 1
                    self._consume(k, 1)
                    break
            p["battle"] = None
            p["location"] = self._recovery_location()
            self._effect(p, "injury", 1, 1, "defeat")
            result.update(
                outcome="defeat",
                stonesLost=loss,
                dropped=dropped,
                message=(
                    "散修被送回客舍，疗伤需付费"
                    if self._is_rogue()
                    else "宗门救回，重伤需闭关疗养"
                ),
            )
        elif e["hp"] <= 0:
            target = b["target"]
            first_kill = p["kills"].get(target, 0) == 0
            p["kills"][target] = p["kills"].get(target, 0) + 1
            paid = self._pays_victory_reward(target, first_kill)
            reward = e["reward"] if paid else 0
            drops = e["drops"] if paid else {}
            p["stones"] += reward
            trackedLoot = self._track_reward(target)
            for k, n in drops.items():
                self._add(k, n)
            if p["location"] == "realm":
                p["realmLoot"].append("boss:" + target)
            if target == "sparring" and self._current_event().get("id") == "tournament":
                p["reputation"] += 1
            p["battle"] = None
            bounty = self._bonus("killBounty")
            if bounty and first_kill:
                p["stones"] += bounty
                result["bounty"] = bounty
            leech = self._bonus("victoryQiLeech")
            if leech and p["qi"] < p["maxQi"]:
                p["qi"] = min(p["maxQi"], p["qi"] + leech)
                result["qiLeeched"] = leech
            result.update(
                outcome="victory",
                loot={**drops, **trackedLoot},
                stones=reward,
            )
            if not paid:
                result["message"] = "此敌曾被击败,这次没有再得到战利品"
        return self._finish_route_turn(skill, log, result, b)

    def use_item(self, item: str):
        p = self.player
        require(item in CONTENT["items"], "未知物品")
        require(p["inventory"].get(item, 0) > 0, "物品不足")
        if CONTENT["items"][item].get("baseItem", item) == "potion":
            if p["battle"]:
                return self._turn(item=item)
            self._consume(item, 1)
            self._restore(item)
        elif item == "forbidden_sword":
            require(p["battle"] is None, "战斗中不能研习禁录")
            self._adopt_discipline("sword")
            self._consume(item, 1)
            if item not in p["techniques"]:
                p["techniques"].append(item)
            if p["route"] == "qingxiao":
                self._violate("私修禁录邪剑")
        elif item in ("manual", "sword_manual"):
            require(p["battle"] is None, "战斗中不能学习")
            t = "verdant" if item == "manual" else "sword_art"
            require(
                self._realm_index() >= CONTENT["techniques"][t]["requiredRealm"],
                "境界不足",
            )
            require(t not in p["techniques"], "已学会")
            self._adopt_discipline(CONTENT["techniques"][t].get("school", "general"))
            self._consume(item, 1)
            p["techniques"].append(t)
            p["skills"] = list(
                dict.fromkeys(
                    p["skills"]
                    + [
                        k
                        for k, v in SKILLS.items()
                        if v.get("school")
                        in ("general", CONTENT["techniques"][t].get("school"))
                    ]
                )
            )
        elif CONTENT["items"][item]["type"] == "法器":
            require(p["battle"] is None, "战斗中不能换装")
            p["equipment"][CONTENT["items"][item]["slot"]] = item
        else:
            raise RuleError("物品不能直接使用")
        return dict(
            used=item,
            hp=p["hp"],
            qi=p["qi"],
            equipment=p["equipment"],
            statusEffects=copy.deepcopy(p["statusEffects"]),
            quality=CONTENT["items"][item].get("quality", "ordinary"),
        )

    def craft(self, recipe: str, amount: int = 1):
        return self._craft_route(recipe, amount)

    def submit_quest(self, quest: str):
        p = self.player
        require(quest in QUESTS and p["quests"].get(quest) == "active", "任务未进行")
        q = QUESTS[quest]
        require(p["location"] == q["location"], "请回任务发布地")
        if self._quest_extra_objective(q):
            pass
        elif "item" in q:
            self._consume(q["item"], q["quantity"])
        elif "kill" in q:
            require(p["kills"].get(q["kill"], 0) >= 1, "尚未击败目标")
        else:
            require(p["explores"] >= q["explores"], "探索次数不足")
        p["quests"][quest] = "completed"
        p["stones"] += q["reward"]
        reputationReward = self._quest_reputation(q)
        p["reputation"] += reputationReward
        self._rogue_quest_completion()
        return dict(stones=p["stones"], reputation=p["reputation"])

    def breakthrough(self):
        p = self.player
        idx = self._realm_index()
        r = CONTENT["realms"][idx]
        require(
            self._can_cultivate() and p["hp"] == p["max_hp"] and not p["statusEffects"],
            "突破需在宗门气血圆满、无异常状态",
        )
        require(self.state["minutes"] >= p["cooldownUntil"], "突破失败后需等待一天")
        cost = r["cost"] * (p["stage"] + 1)
        require(p["cultivation"] >= cost, "修为不足")
        qualityBonus = 0
        if p["stage"] == 3:
            require(idx < 3, "已达元婴圆满")
            next_realm = CONTENT["realms"][idx + 1]
            require(p["reputation"] >= next_realm["reputation"], "声望不足")
            qualityBonus = self._breakthrough_resource(next_realm["pill"])
        chance = min(
            100,
            r["chance"]
            + p["aptitude"] * 2
            + self._stats(p)["spirit"] // 5
            + qualityBonus,
        )
        if self._roll("breakthrough") > chance:
            p["cultivation"] -= cost // 3
            p["hp"] = max(1, p["hp"] - 20 * (idx + 1))
            p["cooldownUntil"] = self.state["minutes"] + 1440
            self._effect(p, "injury", 1, 1, "breakthrough")
            return dict(
                success=False,
                chance=chance,
                hp=p["hp"],
                cooldownUntil=p["cooldownUntil"],
            )
        p["cultivation"] -= cost
        if p["stage"] == 3:
            p["realm"] = CONTENT["realms"][idx + 1]["name"]
            p["stage"] = 0
        else:
            p["stage"] += 1
        p["level"] += 1
        p["strength"] += 3
        p["defense"] += 1
        p["max_hp"] += 20
        p["hp"] = p["max_hp"]
        p["maxQi"] += 10
        p["qi"] = p["maxQi"]
        return dict(success=True, chance=chance, realm=p["realm"], stage=p["stage"])

    def retreat(self, duration: int = 1):
        duration = bounded_int(duration, 1, 72)
        if self.player["battle"]:
            return self._turn(escape=True)
        return self._retreat_route(duration)
