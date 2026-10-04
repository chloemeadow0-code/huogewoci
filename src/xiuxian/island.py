"""Lingxi Island: reuse cultivation/combat rules, add relational world lifecycles."""

from __future__ import annotations
import copy
import hashlib
import json
import logging
from pathlib import Path
from .engine import Game, CONTENT, TOOLS, READ_ONLY, LOCK, ENEMIES
from .db import Store, dumps
from .rules import require, RuleError, bounded_int

logger = logging.getLogger(__name__)

ISLAND = json.loads(
    (Path(__file__).resolve().parents[2] / "systems/xiuxian/island.json").read_text(
        encoding="utf-8"
    )
)
EXTRA = (
    "quest_list",
    "quest_step",
    "incident_list",
    "incident_resolve",
    "item_ledger",
    "world_log",
    "market_catalog",
    "market_bid",
    "beast_train",
    "npc_list",
    "sect_hall",
    "redeem",
)
for name in EXTRA:
    if name not in TOOLS:
        # engine validates against its module-level tuple, while MCP exposes only bundles.
        import xiuxian.engine as _engine

        _engine.TOOLS += (name,)
READ_ONLY.update(
    {
        "quest_list",
        "incident_list",
        "item_ledger",
        "world_log",
        "market_catalog",
        "npc_list",
        "sect_hall",
    }
)


class IslandGame(Game):
    def __init__(self, db_path, player_key=None, player_name="无名修士"):
        self.path = str(Path(db_path).resolve())
        self.key = player_key or "local"
        self.storage = Store(self.path)
        self.db = self.storage.db
        self.sid = 0
        self._in_action = False
        with LOCK:
            self.db.execute("BEGIN IMMEDIATE")
            self.state = self.storage.load()
            for p in self.state["players"].values():
                self._island_defaults(p)
            if self.key not in self.state["players"]:
                self.state["players"][self.key] = self.new_player(player_name)
            self._upgrade()
            self._island_defaults(self.player)
            self._store()
            for key, q in ISLAND["quests"].items():
                self.db.execute(
                    "INSERT OR REPLACE INTO quests VALUES (?,?,?,?)",
                    (key, q["name"], q["location"], dumps(q)),
                )
            self.db.commit()

    def _island_defaults(self, p):
        logical = p.get("location", "sect")
        where = p.get("islandLocation") or {
            "sect": (
                p.get("route") if p.get("route") not in (None, "rogue") else "market"
            ),
            "town": "market",
            "wild": "bamboo",
            "realm": "secret",
        }.get(logical, "market")
        p.setdefault("islandLocation", where)
        if "skills" in p:
            p["skills"] = list(
                dict.fromkeys(p["skills"] + ["calm", "weaken", "escape_step"])
            )
        if "relationships" in p:
            old_npcs = {
                "elder": (p.get("route") or "qingxiao") + "_mentor",
                "alchemist": "danxia_mentor",
                "hermit": "guide",
            }
            for old, new in old_npcs.items():
                if old in p["relationships"] and old != new:
                    p["relationships"].setdefault(new, p["relationships"].pop(old))
        for key, val in {
            "incidents": [],
            "questStages": {},
            "ledgers": [],
            "contribution": 0,
            "sectReputation": p.get("reputation", 0),
        }.items():
            p.setdefault(key, copy.deepcopy(val))
        if p.get("beast"):
            self._beast_fields(p)

    def _beast_fields(self, p):
        pet = p["beast"]
        pet.setdefault("species", pet["id"])
        pet["contract_owner"] = p["id"]
        pet["hunger"] = max(0, (self.state["minutes"] - pet["lastFed"]) // 60)

    def manage_beast(self, action, beast=None, stance="assist"):
        result = super().manage_beast(action, beast, stance)
        if self.player.get("beast"):
            self._beast_fields(self.player)
            return copy.deepcopy(self.player["beast"])
        return result

    def _load_state(self):
        if not self.db.in_transaction:
            self.db.execute("BEGIN IMMEDIATE")
        return self.storage.load()

    def _store(self):
        self.storage.save(self.state)
        if not self._in_action:
            self.db.commit()

    def call(self, tool, request_id=None, **kwargs):
        with LOCK:
            self._in_action = True
            try:
                self.state = self._load_state()
                fingerprint = hashlib.sha256(
                    json.dumps(
                        [tool, kwargs], ensure_ascii=False, sort_keys=True
                    ).encode()
                ).hexdigest()
                if request_id is not None:
                    require(
                        isinstance(request_id, str) and 1 <= len(request_id) <= 128,
                        "请求编号须为1至128字",
                    )
                    cached = self.db.execute(
                        "SELECT fingerprint,response FROM idempotency WHERE cultivator_id=? AND request_id=?",
                        (self.key, request_id),
                    ).fetchone()
                    if cached:
                        require(
                            cached[0] == fingerprint, "相同请求编号不能用于不同操作"
                        )
                        self.db.rollback()
                        return json.loads(cached[1])
                before = copy.deepcopy(self.player)
                oldtime = self.state["minutes"]
                old_events = len(self.state["events"])
                # Unhandled incidents remain blocking until a successful explicit resolution.
                for incident in self.player["incidents"]:
                    if incident["status"] == "open":
                        require(
                            tool not in ISLAND["incidents"][incident["type"]]["blocks"],
                            "待处理事件限制了此行动，请查看灾档并选择处置",
                        )
                response = super().call(tool, **kwargs)
                if response["ok"] and tool not in READ_ONLY:
                    if self.player["history"]:
                        self.player["history"][-1]["location"] = before[
                            "islandLocation"
                        ]
                    self._after_action(tool, response["result"], before)
                    delta = {
                        "hp": self.player["hp"] - before["hp"],
                        "qi": self.player["qi"] - before["qi"],
                        "money": self.player["stones"] - before["stones"],
                        "cultivation": self.player["cultivation"]
                        - before["cultivation"],
                        "minutes": self.state["minutes"] - oldtime,
                    }
                    response.update(
                        changes=delta,
                        new_events=copy.deepcopy(self.state["events"][old_events:]),
                        available_actions=self.available_actions(),
                    )
                    self.db.execute(
                        "INSERT INTO world_logs(tick,time,actor,action,summary) VALUES (?,?,?,?,?)",
                        (self.state["tick"], oldtime, self.key, tool, dumps(delta)),
                    )
                    self._store()
                else:
                    response.update(
                        changes={},
                        new_events=[],
                        available_actions=self.available_actions(),
                    )
                # Only successful responses are replayable: a failed request
                # leaves no state change, so a corrected retry under the same
                # id must not be pinned to the failure.
                if request_id and response["ok"]:
                    self.db.execute(
                        "INSERT INTO idempotency VALUES (?,?,?,?)",
                        (self.key, request_id, fingerprint, dumps(response)),
                    )
                self.db.commit()
                return response
            except RuleError as exc:
                self.db.rollback()
                return {
                    "ok": False,
                    "error": str(exc),
                    "changes": {},
                    "new_events": [],
                    "available_actions": self.available_actions(),
                }
            except Exception:
                logger.exception(
                    "island call failed: tool=%s player=%s request_id=%s kwargs=%s",
                    tool,
                    self.key,
                    request_id,
                    kwargs,
                )
                self.db.rollback()
                raise
            finally:
                self._in_action = False

    def available_actions(self):
        result = super().available_actions()
        result.extend(
            [
                "quest_list",
                "incident_list",
                "item_ledger",
                "world_log",
                "market_catalog",
                "npc_list",
                "sect_hall",
            ]
        )
        if not self.player.get("battle"):
            result.extend(
                ["quest_step", "incident_resolve", "market_bid", "beast_train"]
            )
            if self.player.get("beast"):
                result.append("beast_evolve")
            if self.player.get("route"):
                if self._local_enemies():
                    result.append("fight")
                if self.player["islandLocation"] == self.player.get("route"):
                    result.append("redeem")
                if any(
                    q["location"] == self.player["islandLocation"]
                    for q in ISLAND["quests"].values()
                ):
                    result.extend(["accept_quest", "submit_quest"])
        blocked = {
            action
            for e in self.player.get("incidents", [])
            if e["status"] == "open"
            for action in ISLAND["incidents"][e["type"]]["blocks"]
        }
        if self.player["location"] == "sect" and self.player[
            "islandLocation"
        ] != self.player.get("route"):
            blocked.update(
                {
                    "cultivate",
                    "retreat",
                    "breakthrough",
                    "craft",
                    "learn_technique",
                    "prepare_formation",
                    "manage_beast",
                }
            )
        return list(dict.fromkeys(a for a in result if a not in blocked))

    def get_self(self):
        p = super().get_self()
        p.update(
            location=p["islandLocation"],
            realm_stage=p["realmStage"],
            cultivation_required=p["cultivationRequired"],
            max_qi=p["maxQi"],
            spirit_root=p["root"],
            money=p["stones"],
            status_effects=p["statusEffects"],
            injuries=[e for e in p["incidents"] if e["status"] == "open"],
            sect_reputation=p["sectReputation"],
        )
        return p

    def choose_route(self, route):
        result = super().choose_route(route)
        self.player["islandLocation"] = "market" if route == "rogue" else route
        return result

    def _can_cultivate(self):
        return self.player["islandLocation"] == (
            "market" if self._is_rogue() else self.player.get("route")
        )

    def breakthrough(self):
        p = self.player
        require(p["method"] in p["techniques"], "突破需已学会当前功法")
        require(
            self._realm_index() >= CONTENT["techniques"][p["method"]]["requiredRealm"],
            "当前境界不能驾驭此功法",
        )
        return super().breakthrough()

    def _open_auctions(self):
        """Open listings with the bidder identity redacted; the raw owner stays
        in the database for escrow settlement, clients get has_bid/is_mine."""
        rows = self.db.execute(
            "SELECT * FROM market_listings WHERE quantity>0 AND ends>?",
            (self.state["minutes"],),
        )
        auctions = []
        for r in rows:
            details = json.loads(r["details"])
            owner = details.pop("owner", None)
            auctions.append(
                dict(r)
                | {
                    "details": details,
                    "has_bid": owner is not None,
                    "is_mine": owner == self.key,
                }
            )
        return auctions

    def get_world(self):
        where = self.player["islandLocation"]
        loc = ISLAND["locations"][where]
        data = super().get_world()
        data.update(
            name="灵汐岛",
            region=where,
            location=copy.deepcopy(loc),
            map=ISLAND["locations"],
            npcs={k: v for k, v in ISLAND["npcs"].items() if self._npc_present(k)},
            enemies=self._local_enemies(),
            quests={
                k: v for k, v in ISLAND["quests"].items() if v["location"] == where
            },
            incidents=self.incident_list(),
            world_flags=self.state.get("flags", {}),
            villain_signals={
                k: {
                    "name": v["name"],
                    "faction": v["faction"],
                    "stage": self.player["questStages"]
                    .get("villain_" + k, {})
                    .get("stage", 0),
                }
                for k, v in ISLAND["villains"].items()
                if where in v["locations"]
            },
        )
        for key, status in self.player["quests"].items():
            if (
                key not in ISLAND["quests"]
                and key in CONTENT["quests"]
                and status == "active"
            ):
                data["quests"][key] = CONTENT["quests"][key] | {
                    "stages": [],
                    "kind": "旧档委托",
                    "legacy": True,
                }
        data["auctions"] = self._open_auctions()
        data["sectHall"] = self.sect_hall()
        return data

    def travel(self, destination, node=None):
        aliases = {
            "sect": self.player.get("route") or "qingxiao",
            "town": "market",
            "wild": "bamboo",
            "realm": "secret",
        }
        destination = aliases.get(destination, destination)
        p = self.player
        current = p["islandLocation"]
        require(destination in ISLAND["locations"], "未知岛上地点")
        require(
            destination == current
            or destination in ISLAND["locations"][current]["exits"],
            "须沿地图相邻道路行走",
        )
        loc = ISLAND["locations"][destination]
        require(self._realm_index() >= loc["requiredRealm"], "此处需筑基后才能安全进入")
        require(
            node is None or node in CONTENT["locations"][loc["area"]]["nodes"],
            "未知场景节点",
        )
        if destination == "secret" and current != "secret":
            require(self.state["minutes"] % (7 * 1440) < 2 * 1440, "潮生秘境尚未开启")
            require(p["realmVisit"] != self.state["realm"]["cycle"], "本周期已进入秘境")
            p["realmVisit"] = self.state["realm"]["cycle"]
            p["realmLoot"] = []
        p["preparedFormation"] = None
        p["islandLocation"] = destination
        p["location"] = loc["area"]
        p["node"] = node or (
            "黑市"
            if destination == "blackmarket"
            else CONTENT["locations"][loc["area"]]["nodes"][0]
        )
        self._blackmarket_refresh()
        return {"location": destination, "name": loc["name"], "node": p["node"]}

    def _stock(self):
        if self.player["location"] == "sect" and self.player[
            "islandLocation"
        ] != self.player.get("route"):
            return []
        return super()._stock()

    def _current_event(self):
        event = copy.deepcopy(super()._current_event())
        for key, v in ISLAND["villains"].items():
            phase = (
                self.state.get("flags", {}).get("villain_" + key, {}).get("stage", 0)
            )
            if 1 <= phase < 4 and self.player["islandLocation"] in v["locations"]:
                event["exploreDamage"] = event.get("exploreDamage", 0) + 2
        return event

    def _npc_present(self, npc):
        n = ISLAND["npcs"].get(npc)
        return bool(
            n
            and n["location"] == self.player["islandLocation"]
            and self._current_event().get("missingNpc") != npc
        )

    def npc_list(self):
        return {
            k: v
            | {
                "relationship": self.player["relationships"].get(
                    k, v["initialRelationship"]
                )
            }
            for k, v in ISLAND["npcs"].items()
            if self._npc_present(k)
        }

    def talk(self, npc, topic="greeting", item=None):
        aliases = {
            "elder": (self.player.get("route") or "qingxiao") + "_mentor",
            "alchemist": "danxia_mentor",
            "hermit": "guide",
        }
        npc = aliases.get(npc, npc)
        taught_reputation = 0
        require(self._npc_present(npc), "人物不在此处")
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
        n = ISLAND["npcs"][npc]
        r = self.player["relationships"].setdefault(
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
            require("teach" in n["functions"] and r["hostility"] < 3, "此人暂不愿传授")
            require(
                self.player["islandLocation"] in (self.player.get("route"), "market"),
                "跨宗门传承需坊市信誉",
            )
            day = self.state["minutes"] // 1440
            teach_day_key = "teach_day:" + npc
            if self.player["counters"].get(teach_day_key) != day:
                self.player["counters"][teach_day_key] = day
                taught_reputation = 2
                self.player["reputation"] += 2
            r["trust"] += 1
            technique = n.get("technique")
            if technique and technique not in self.player["techniques"]:
                self.player["techniques"].append(technique)
                self.player["techniqueLevels"][technique] = 1
                self.player["skills"] = list(
                    dict.fromkeys(
                        self.player["skills"]
                        + CONTENT["routes"].get(n["location"], {}).get("skills", [])
                    )
                )
        elif topic == "help":
            require("heal" in n["functions"], "这位修士不提供诊疗")
            require(self.player["stones"] >= 5, "诊疗需5灵石")
            self.player["stones"] -= 5
            self.player["hp"] = self.player["max_hp"]
        elif topic == "spar":
            return self._open_battle("sparring")
        else:
            r["friendliness"] += 1
            r["trust"] += 1
        r["dialogueState"].append({"time": self.state["minutes"], "topic": topic})
        event_key = "npc_event:" + npc
        if r["trust"] >= 5 and not self.player["counters"].get(event_key):
            self.player["counters"][event_key] = True
            self.player["reputation"] += 1
            self.state.setdefault("flags", {})[event_key] = {
                "name": n["specialEvent"],
                "time": self.state["minutes"],
            }
        return {
            "npc": npc,
            "name": n["name"],
            "message": (
                n["background"]
                if topic in ("greeting", "rumor")
                else "你们交换了见闻，这次交谈已经记下。"
            ),
            "relationship": copy.deepcopy(r),
            "quest": n["personalQuest"],
            "reputation_gained": taught_reputation,
        }

    def _local_enemies(self):
        where = self.player["islandLocation"]
        keys = {
            "qingxiao": ["sparring"],
            "xuanheng": ["sparring"],
            "danxia": ["sparring"],
            "fuyao": ["sparring"],
            "hehuan": ["sparring"],
            "taixu": ["sparring"],
            "youming": ["sparring"],
            "wanxiang": ["sparring"],
            "tiangong": ["sparring"],
            "canglang": ["sparring"],
            "fentian": ["sparring"],
            "xingluo": ["sparring"],
            "bamboo": ["wolf"],
            "mist": ["wolf", "bandit"],
            "ridge": ["wolf", "protected_deer"],
            "lake": ["wolf"],
            "ruins": ["bandit"],
            "secret": ["guardian"],
        }.get(where, [])
        enemies = {k: ENEMIES[k] for k in keys}
        enemies.update(
            {
                k: v["enemy"]
                for k, v in ISLAND["villains"].items()
                if where in v["locations"]
                and self._realm_index() >= v["enemy"]["realm"]
            }
        )
        return enemies

    def _pays_victory_reward(self, target, first_kill):
        # First takedown of a villain pays; later kills still count for
        # quest progress but yield nothing, so story order never locks up.
        return first_kill or target not in ISLAND["villains"]

    def _open_battle(self, target, surprise=False):
        p = self.player
        require(target in self._local_enemies(), "目标不在此处")
        require(p["battle"] is None and p["hp"] > 0, "当前不能开战")
        if p["location"] == "realm":
            require("boss:" + target not in p["realmLoot"], "此敌本周期已击败")
        e = copy.deepcopy(self._local_enemies()[target])
        e.update(max_hp=e["hp"], spirit=8, statusEffects=[], cooldowns={})
        p["battle"] = {"target": target, "enemy": e, "round": 0, "cooldowns": {}}
        self._begin_route_battle(surprise)
        return copy.deepcopy(p["battle"])

    def fight(self, target):
        return self._open_battle(target)

    def explore(self):
        p = self.player
        require(p["location"] in ("wild", "realm") and p["hp"] > 10, "当前无法探索")
        require(
            self._current_event().get("blocked") != p["location"],
            "区域因坍塌暂时无法探索",
        )
        if p["location"] == "realm":
            require(self.state["minutes"] % (7 * 1440) < 2 * 1440, "秘境关闭，请离开")
            require(p["node"] not in p["realmLoot"], "此节点本周期已探索")
            p["realmLoot"].append(p["node"])
        p["explores"] += 1
        event = self._explore_route_event()
        result = {"event": event, "islandLocation": p["islandLocation"]}
        if event == "enemy":
            normal = [k for k in self._local_enemies() if k not in ISLAND["villains"]]
            target = normal[(self._roll("encounter") - 1) % len(normal)]
            result["battle"] = self._open_battle(target, True)
        elif event in ("herb", "cave"):
            self._add(
                "herb",
                2 if event == "cave" else 1 + self._current_event().get("extraHerb", 0),
            )
            result["item"] = "herb"
        elif event == "chest":
            self._add("iron", 1)
            p["stones"] += 8
            result["loot"] = {"iron": 1, "stones": 8}
            if p["location"] == "realm":
                # 潮汐宝藏:秘境里的宝箱额外凝出一枚进化晶核。
                self._add("evolution_crystal", 1)
                result["loot"]["evolution_crystal"] = 1
        self._explore_extra(event, result)
        p["hp"] = max(1, p["hp"] - self._current_event().get("exploreDamage", 0))
        return result

    def _advance(self, tool, args, in_battle=False):
        for record in self.state["players"].values():
            pet = record.get("beast")
            if pet and pet.get("status") == "released":
                record["beast"] = None
        old = len(self.state["events"])
        super()._advance(tool, args, in_battle)
        for record in self.state["players"].values():
            if record.get("beast"):
                self._beast_fields(record)
        for i in range(old, len(self.state["events"])):
            day = self.state["events"][i]["day"]
            event = copy.deepcopy(
                ISLAND["events"][
                    (self._roll("island_world_pulse") - 1) % len(ISLAND["events"])
                ]
            )
            event["day"] = day
            self.state["events"][i] = event
            self.state.setdefault("flags", {})[event["id"]] = {
                "day": day,
                "active": True,
            }
        if (
            self.player["location"] in ("town", "sect")
            and self.player["battle"] is None
        ):
            # Realm-cycle listing: no generated infinite supply or bidder-controlled prices.
            self.db.execute(
                "INSERT OR IGNORE INTO market_listings VALUES (?,?,?,?,?,?)",
                (
                    "auction:" + str(self.state["realm"]["cycle"]),
                    "sword",
                    45,
                    1,
                    (self.state["realm"]["cycle"] + 1) * 7 * 1440,
                    dumps({"name": "一柄旧剑的来路", "source": "坊市鉴器师"}),
                ),
            )

        for listing in list(
            self.db.execute(
                "SELECT * FROM market_listings WHERE quantity>0 AND ends<=?",
                (self.state["minutes"],),
            )
        ):
            details = json.loads(listing["details"])
            owner = details.get("owner")
            if owner in self.state["players"]:
                receiver = self.state["players"][owner]
                receiver["inventory"][listing["item"]] = (
                    receiver["inventory"].get(listing["item"], 0) + 1
                )
                receiver["ledgers"].append(
                    {
                        "id": len(receiver["ledgers"]) + 1,
                        "item": listing["item"],
                        "status": "held",
                        "entries": [
                            {
                                "date": self.state["minutes"],
                                "place": "market",
                                "source": "auction",
                                "event": "竞价成交",
                            }
                        ],
                    }
                )
            self.db.execute(
                "UPDATE market_listings SET quantity=0 WHERE id=?", (listing["id"],)
            )

    def _after_action(self, tool, result, before):
        p = self.player
        if (
            before.get("battle")
            and not p["battle"]
            and result.get("outcome") in ("escaped", "defeat")
        ):
            p["islandLocation"] = "market" if self._is_rogue() else p["route"]
            p["node"] = CONTENT["locations"][p["location"]]["nodes"][0]
        if tool == "breakthrough" and result.get("success") is False:
            self._open_incident("meridians")
        if tool == "cultivate" and self._roll("cultivation_incident") <= 2:
            self._open_incident("deviation")
        if tool == "explore" and self._roll("island_incident") <= 8:
            kind = (
                "trapped"
                if p["location"] == "realm"
                else "poison" if p["islandLocation"] == "mist" else "ambush"
            )
            self._open_incident(kind)
        if tool == "craft" and (
            result.get("exploded")
            or any(r.get("outcome") == "exploded" for r in result.get("outcomes", []))
        ):
            self._open_incident("furnace")
        if tool == "prepare_formation" and self._roll("formation_incident") <= 3:
            self._open_incident("formation")
        if (
            tool in ("use_skill", "use_item", "retreat")
            and result.get("outcome") == "defeat"
        ):
            self._open_incident("artifact")
        if p.get("beast") and p["beast"].get("injuries"):
            self._open_incident("beast_injury")
        if self._current_event().get("id") == "array_fault" and tool == "craft":
            self._open_incident("sect_accident")
        # Important objects have per-instance birth and consumption records.
        important = {
            i
            for i, v in CONTENT["items"].items()
            if v["type"] in ("法器", "功法")
            or v.get("quality") in ("fine", "superior")
            or i in ("foundation_pill", "golden_pill", "soul_pill", "beast_egg")
        }
        for item in important:
            change = p["inventory"].get(item, 0) - before["inventory"].get(item, 0)
            if change > 0:
                for _ in range(change):
                    p["ledgers"].append(
                        {
                            "id": len(p["ledgers"]) + 1,
                            "item": item,
                            "status": "held",
                            "entries": [
                                {
                                    "date": self.state["minutes"],
                                    "place": p["islandLocation"],
                                    "source": tool,
                                    "event": "获得",
                                }
                            ],
                        }
                    )
            elif change < 0:
                for record in [
                    e
                    for e in p["ledgers"]
                    if e["item"] == item and e["status"] == "held"
                ][: abs(change)]:
                    record["status"] = "sold" if tool == "trade" else "used"
                    record["entries"].append(
                        {
                            "date": self.state["minutes"],
                            "place": p["islandLocation"],
                            "source": tool,
                            "event": record["status"],
                        }
                    )

    def _open_incident(self, kind):
        p = self.player
        if any(e["type"] == kind and e["status"] == "open" for e in p["incidents"]):
            return
        p["incidents"].append(
            {
                "id": len(p["incidents"]) + 1,
                "type": kind,
                "name": ISLAND["incidents"][kind]["name"],
                "status": "open",
                "opened": self.state["minutes"],
            }
        )

    def incident_list(self):
        return [
            e
            | {
                "options": ISLAND["incidents"][e["type"]]["options"],
                "blocks": ISLAND["incidents"][e["type"]]["blocks"],
            }
            for e in self.player["incidents"][-30:]
        ]

    def incident_resolve(self, incident: int, choice: str):
        e = next((e for e in self.player["incidents"] if e["id"] == incident), None)
        require(e and e["status"] == "open", "事件已结案或不存在")
        options = ISLAND["incidents"][e["type"]]["options"]
        require(choice in options, "未知处理选项")
        option = options[choice]
        p = self.player
        require(
            p["stones"] >= option.get("stones", 0) and p["qi"] >= option.get("qi", 0),
            "处置资源不足",
        )
        if option.get("item"):
            self._consume(option["item"], option["quantity"])
        p["stones"] -= option.get("stones", 0)
        p["qi"] -= option.get("qi", 0)
        self._extra_minutes = option["hours"] * 60
        closed = self.state["minutes"] + self._extra_minutes
        success = self._roll("incident_resolution") <= option["success"]
        if success:
            e.update(status="closed", closed=closed, choice=choice)
            if e["type"] in ("meridians", "deviation", "poison"):
                p["statusEffects"] = []
            if e["type"] == "beast_injury" and p.get("beast"):
                p["beast"]["injuries"] = 0
                p["beast"]["hp"] = p["beast"]["maxHp"]
                p["beast"]["status"] = "healthy"
        return {
            "incident": incident,
            "success": success,
            "status": e["status"],
            "choice": choice,
        }

    def item_ledger(self, item=None):
        return [e for e in self.player["ledgers"] if item is None or e["item"] == item][
            -30:
        ]

    def world_log(self, limit=20):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT time,action,summary FROM world_logs ORDER BY id DESC LIMIT ?",
                (bounded_int(limit, 1, 50),),
            )
        ]

    def quest_list(self):
        return {
            k: q
            | {
                "progress": self.player["questStages"].get(k),
                "status": self.player["quests"].get(k, "available"),
            }
            for k, q in ISLAND["quests"].items()
            if q["location"] == self.player["islandLocation"]
            or k in self.player["questStages"]
        }

    def accept_quest(self, quest):
        if quest not in ISLAND["quests"]:
            return super().accept_quest(quest)
        q = ISLAND["quests"][quest]
        p = self.player
        sect = q.get("sect")
        require(sect is None or p.get("route") == sect, "这是其他宗门的任务")
        require(q["location"] == p["islandLocation"], "请到任务发布地")
        require(quest not in p["quests"], "已领取任务")
        p["quests"][quest] = "active"
        p["questStages"][quest] = {
            "stage": 0,
            "branch": "",
            "since": len(p["history"]),
            "kills": copy.deepcopy(p["kills"]),
        }
        return {"quest": quest, "name": q["name"], "next": q["stages"][0]}

    def quest_step(self, quest, branch=None):
        require(
            quest in ISLAND["quests"] and self.player["quests"].get(quest) == "active",
            "阶段任务未进行",
        )
        q = ISLAND["quests"][quest]
        p = self.player
        progress = p["questStages"][quest]
        index = progress["stage"]
        require(index < len(q["stages"]), "目标已达成，请交付任务")
        stage = q["stages"][index]
        history = p["history"][progress["since"] :]
        kind = stage["type"]
        condition = False
        if kind == "talk":
            condition = any(
                h["action"] == "talk" and (h["result"].get("npc") == stage["npc"])
                for h in history
            )
        if kind == "explore":
            condition = (
                sum(
                    h["action"] == "explore"
                    and h["result"].get("islandLocation") == stage["location"]
                    for h in history
                )
                >= stage["count"]
            )
        if kind == "kill":
            condition = p["kills"].get(stage["target"], 0) > progress["kills"].get(
                stage["target"], 0
            )
        if kind == "return":
            condition = p["islandLocation"] == stage["location"]
        if kind == "realm":
            condition = self._realm_index() >= next(
                i
                for i, r in enumerate(CONTENT["realms"])
                if r["name"] == stage["realm"]
            )
        require(condition, "阶段目标尚未达成，需完成实际行动")
        if index == len(q["stages"]) - 1:
            require(
                branch in q["branches"],
                "请选择report（如实报告）或protect（保护并善后）",
            )
            require(p["stones"] >= q["branches"][branch]["cost"], "善后灵石不足")
            p["stones"] -= q["branches"][branch]["cost"]
            progress["branch"] = branch
        progress["stage"] += 1
        if quest.startswith("villain_"):
            self.state.setdefault("flags", {})[quest] = {
                "stage": progress["stage"],
                "branch": progress["branch"],
            }
        return {
            "quest": quest,
            "stage": progress["stage"],
            "next": (
                q["stages"][progress["stage"]]
                if progress["stage"] < len(q["stages"])
                else "交付领取奖励"
            ),
        }

    def submit_quest(self, quest):
        if quest not in ISLAND["quests"]:
            return super().submit_quest(quest)
        q = ISLAND["quests"][quest]
        p = self.player
        require(
            p["quests"].get(quest) == "active" and p["islandLocation"] == q["location"],
            "任务未进行或不在交付地点",
        )
        stage = p["questStages"][quest]
        require(stage["stage"] == len(q["stages"]), "任务阶段尚未完成")
        reward = q["reward"] + q["branches"][stage["branch"]]["rewardBonus"]
        p["stones"] += reward
        p["quests"][quest] = "completed"
        reputation = (
            self._percent(q["reputation"], self._bonus("combatReputation"))
            if any(s["type"] == "kill" for s in q["stages"])
            else q["reputation"]
        )
        p["reputation"] += reputation
        p["sectReputation"] += reputation
        p["contribution"] += q["contribution"]
        return {
            "quest": quest,
            "reward": reward,
            "contribution": q["contribution"],
            "branch": stage["branch"],
        }

    def _hall_catalog(self):
        catalog = dict(self.pack["sect_hall"])
        catalog.update(
            self.pack.get("route_hall", {}).get(self.player.get("route"), {})
        )
        return catalog

    def sect_hall(self):
        return {
            "contribution": self.player["contribution"],
            "catalog": self._hall_catalog(),
            "note": "用贡献兑换,需回本宗驻地;散修没有宗门贡献殿",
        }

    def redeem(self, item: str, amount: int = 1):
        amount = bounded_int(amount, 1, 10)
        p = self.player
        require(p.get("route"), "散修没有宗门贡献殿")
        require(p["islandLocation"] == p["route"], "请回本宗驻地兑换")
        catalog = self._hall_catalog()
        require(item in catalog, "贡献殿没有这件物品")
        cost = catalog[item] * amount
        require(p["contribution"] >= cost, f"贡献不足,需 {cost}")
        p["contribution"] -= cost
        self._add(item, amount)
        return {
            "item": item,
            "amount": amount,
            "cost": cost,
            "contribution": p["contribution"],
        }

    def market_catalog(self):
        return {
            "shop": self.get_world()["shop"],
            "auctions": self._open_auctions(),
        }

    def market_bid(self, listing, amount: int):
        require(self.player["islandLocation"] == "market", "拍卖在灵汐坊市")
        amount = bounded_int(amount, 1, 100000)
        r = self.db.execute(
            "SELECT * FROM market_listings WHERE id=? AND quantity>0 AND ends>?",
            (listing, self.state["minutes"]),
        ).fetchone()
        require(
            r
            and amount
            >= r["price"] + (1 if json.loads(r["details"]).get("owner") else 0),
            "竞价低于当前报价或拍品已经结束",
        )
        require(self.player["stones"] >= amount, "灵石不足")
        details = json.loads(r["details"])
        require(details.get("owner") != self.key, "已是最高出价者")
        if details.get("owner"):
            self.state["players"][details["owner"]]["stones"] += r["price"]
        self.player["stones"] -= amount
        details["owner"] = self.key
        self.db.execute(
            "UPDATE market_listings SET price=?,details=? WHERE id=?",
            (amount, dumps(details), listing),
        )
        return {
            "listing": listing,
            "bid": amount,
            "ends": r["ends"],
            "message": "出价已托管，到期结算；被超价会退回灵石。",
        }

    def beast_train(self):
        p = self.player
        pet = p.get("beast")
        require(pet and pet["hp"] > 0 and not pet["injuries"], "灵兽需健康才可训练")
        require(p["stones"] >= 4, "训练需4灵石")
        p["stones"] -= 4
        pet["xp"] += self._percent(500, self._bonus("petGrowth"))
        self._pet_level(pet)
        if pet["level"] >= 3 and "guard" not in pet["skills"]:
            pet["skills"].append("guard")
        if pet["level"] >= 5:
            pet["evolution"] = "灵性觉醒"
        return copy.deepcopy(pet)
