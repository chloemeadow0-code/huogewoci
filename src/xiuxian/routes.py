"""Five cultivation lifestyles: server-owned modifiers and persistent mechanics."""

from __future__ import annotations
import copy
import math
from .rules import require, bounded_int, RuleError


class RouteRules:
    def _upgrade_routes(self):
        p = self.player
        defaults = {
            "route": None,
            "proficiency": {},
            "techniqueLevels": {},
            "mainDisciplines": [],
            "preparedFormation": None,
            "beast": None,
            "counters": {},
            "conduct": {"violations": [], "penalties": []},
            "credibility": {
                "blackmarket": 0,
                "market": 0,
                "alliance": 0,
                "team": 0,
                "wanted": [],
            },
            "blackmarket": {"stock": [], "day": -1},
            "tracked": None,
            "materialRemainders": {},
        }
        for k, v in defaults.items():
            p.setdefault(k, copy.deepcopy(v))
        if p["route"] is None:
            p["sect"] = "待择道"

    def _route(self):
        return self.pack["routes"].get(self.player.get("route"), {})

    def _bonus(self, name):
        return self._route().get("modifiers", {}).get(name, 0)

    def _percent(self, value, percent, ceil=False):
        return (
            math.ceil(value * (100 + percent) / 100)
            if ceil
            else max(0, value * (100 + percent) // 100)
        )

    def _is_rogue(self):
        return self.player.get("route") == "rogue"

    def choose_route(self, route: str):
        require(
            route in self.pack["routes"],
            "未知路线，请使用qingxiao/xuanheng/danxia/fuyao/rogue",
        )
        p = self.player
        require(p["route"] is None, "路线已经确认，不可切换以反复领取资源")
        require(p["battle"] is None, "战斗中不可选择路线")
        r = self.pack["routes"][route]
        p["route"] = route
        p["sect"] = None if route == "rogue" else r["name"]
        p["mainDisciplines"] = r["disciplines"][:2] if route != "rogue" else []
        p["skills"] = list(dict.fromkeys(p["skills"] + r["skills"]))
        if r["technique"]:
            p["techniques"].append(r["technique"])
            p["techniqueLevels"][r["technique"]] = 1
        if route == "xuanheng":
            self._add("array_flag", 3)
            self._add("mechanism_part", 3)
            self._add("paper_talisman", 3)
        p["location"] = "town" if route == "rogue" else "sect"
        p["node"] = "散修盟" if route == "rogue" else "山门"
        return {
            "route": route,
            "sect": p["sect"],
            "description": r,
            "mainDisciplines": p["mainDisciplines"],
        }

    def inspect_route(self):
        return {
            "selected": self.player["route"],
            "routes": self.pack["routes"],
            "disciplines": self.pack["disciplines"],
            "formations": self.pack["formations"],
            "proficiency": self.player["proficiency"],
            "conduct": self.player["conduct"],
            "credibility": self.player["credibility"],
        }

    def _allowed_disciplines(self):
        return 4 if self._is_rogue() else 2

    def _adopt_discipline(self, school):
        if school == "general":
            return
        p = self.player
        require(school in self.pack["disciplines"], "未知修行方向")
        if school not in p["mainDisciplines"]:
            require(
                len(p["mainDisciplines"]) < self._allowed_disciplines(),
                "主要方向已满；宗门弟子2个，散修4个",
            )
            p["mainDisciplines"].append(school)

    def _discipline_rate(self, school):
        school = {"mechanism": "craft", "talisman": "formation"}.get(school, school)
        rate = 100
        p = self.player
        r = self._route()
        if school not in (
            "general",
            *(r.get("disciplines", []) if not self._is_rogue() else []),
        ):
            penalty = self.pack["route_rules"]["crossSchoolPenalty"]
            penalty = self._percent(
                penalty, -self._bonus("crossSchoolPenaltyReduction")
            )
            rate -= penalty
        if self._is_rogue():
            rate -= (
                max(0, len(p["mainDisciplines"]) - 1)
                * self.pack["route_rules"]["extraDisciplinePenalty"]
            )
        return max(20, rate)

    def _gain_proficiency(self, school, base, kind):
        school = {"mechanism": "craft", "talisman": "formation"}.get(school, school)
        p = self.player
        rate = 100 if kind == "cultivation" else self._discipline_rate(school)
        bonus = (
            self._bonus("combatGrowth")
            if kind == "combat"
            else self._bonus("productionGrowth") if kind == "production" else 0
        )
        gained = base * rate * (100 + bonus) // 10000
        p["proficiency"][school] = p["proficiency"].get(school, 0) + gained
        # The active technique gains levels only from real action XP in its school.
        t = self.pack["techniques"][p["method"]]
        if t.get("school") == school:
            p["techniqueLevels"][p["method"]] = min(
                t["maxLevel"],
                1
                + p["proficiency"][school]
                // self.pack["route_rules"]["proficiencyLevelXp"],
            )
        return gained

    def learn_technique(self, technique: str):
        p = self.player
        require(p["battle"] is None, "战斗中不能学习")
        require(technique in self.pack["techniques"], "未知功法")
        require(technique not in p["techniques"], "已经学会")
        require(technique != "forbidden_sword", "禁录功法只能从黑市残卷研习")
        require(p["location"] in ("sect", "town"), "请到藏经阁或坊市寻找传承")
        t = self.pack["techniques"][technique]
        require(self._realm_index() >= t["requiredRealm"], "境界不足")
        if p["location"] == "sect":
            require(not self._is_rogue(), "散修不能使用宗门藏经阁")
        if t.get("route") and t["route"] != p["route"]:
            require(p["location"] == "town", "跨宗门功法需私人传承")
            require(
                p["credibility"]["market"] >= 3 or p["credibility"]["alliance"] >= 3,
                "高级私人传承需坊市或散修盟信誉3",
            )
        self._adopt_discipline(t.get("school", "general"))
        cost = self._percent(
            t.get("tuition", 25),
            (
                self._percent(
                    self.pack["route_rules"]["crossSchoolPenalty"],
                    -self._bonus("crossSchoolPenaltyReduction"),
                )
                if t.get("route") not in (None, p["route"])
                else 0
            ),
            True,
        )
        require(p["stones"] >= cost, "学费不足")
        p["stones"] -= cost
        p["techniques"].append(technique)
        p["techniqueLevels"][technique] = 1
        for sid, s in self.pack["skills"].items():
            if s.get("school") == t.get("school") and sid not in p["skills"]:
                p["skills"].append(sid)
        return {
            "learned": technique,
            "cost": cost,
            "directions": p["mainDisciplines"],
            "growthRate": self._discipline_rate(t.get("school", "general")),
        }

    def _can_cultivate(self):
        return (
            self.player["location"] == "sect"
            and not self._is_rogue()
            or self._is_rogue()
            and self.player["location"] == "town"
        )

    def _route_cultivation_gain(self, gain, method):
        t = self.pack["techniques"][method]
        school = t.get("school", "general")
        self._adopt_discipline(school)
        gain = gain * self._discipline_rate(school) // 100
        self._gain_proficiency(school, gain * 100, "cultivation")
        return gain

    def _can_craft(self):
        return (
            self.player["location"] == "sect"
            and not self._is_rogue()
            or self._is_rogue()
            and self.player["location"] == "town"
        )

    def _craft_route(self, recipe, amount):
        p = self.player
        require(self._can_craft(), "需在宗门工坊或散修坊市租用工坊")
        require(recipe in self.pack["recipes"], "未知配方")
        amount = bounded_int(amount, 1, 20)
        rule = self.pack["recipe_rules"][recipe]
        school = rule["school"]
        require("basic_meditation" in p["techniques"], "需基础控火心法")
        rank = self._realm_index()
        gap = max(0, rule["requiredRealm"] - rank)
        require(gap <= 1, "丹药超出能力过多，无法炼制")
        require(
            gap == 0 or p["route"] == "danxia" and school == "alchemy",
            "仅丹霞谷可冒险尝试高一境丹药",
        )
        xp = p["proficiency"].get(school, 0)
        training_gap = math.ceil(
            max(0, rule["requiredXp"] - xp)
            / self.pack["route_rules"]["proficiencyLevelXp"]
        )
        if self._is_rogue():
            require(p["stones"] >= amount * 2, "工坊租费不足")
            p["stones"] -= amount * 2
        material_bonus = (
            self._bonus("materialCost")
            if school == "formation" or recipe == "mechanism_part"
            else 0
        )
        materials = {
            k: self._material_cost(k, n * amount, material_bonus)
            for k, n in self.pack["recipes"][recipe].items()
        }
        for k, n in materials.items():
            self._consume(k, n)
        chance = (
            self.pack["route_rules"]["baseCraftChance"]
            + p["aptitude"] * 5
            + self._bonus("alchemyChance" if school == "alchemy" else "forgingChance")
        )
        chance = max(5, min(100, chance - gap * 30 - training_gap * 10))
        outcomes = []
        produced = {}
        damage = 0
        for _ in range(amount):
            roll = self._roll("craft")
            if roll > chance:
                risky = (
                    p["route"] == "danxia"
                    and school == "alchemy"
                    and (gap > 0 or training_gap > 0)
                )
                exploded = risky and self._roll("furnace") <= 30
                if exploded:
                    damage += 12 * (gap + 1)
                    self._effect(p, "burn", 2, 2, "furnace")
                else:
                    self._add("scrap", 1)
                    produced["scrap"] = produced.get("scrap", 0) + 1
                outcomes.append({"outcome": "exploded" if exploded else "failed"})
                continue
            quality = "ordinary"
            if p["route"] == "danxia" and school == "alchemy":
                q = self._roll("pill_quality")
                if q <= self.pack["route_rules"]["superiorChance"]:
                    quality = "superior"
                elif q <= self.pack["route_rules"]["qualityChance"]:
                    quality = "fine"
            item = recipe if quality == "ordinary" else recipe + "_" + quality
            self._add(item, 1)
            produced[item] = produced.get(item, 0) + 1
            outcomes.append({"outcome": "success", "item": item, "quality": quality})
        p["hp"] = max(1, p["hp"] - damage)
        gained = self._gain_proficiency(
            school, amount * self.pack["route_rules"]["craftXp"], "production"
        )
        return {
            "recipe": recipe,
            "crafted": sum(o["outcome"] == "success" for o in outcomes),
            "failed": sum(o["outcome"] != "success" for o in outcomes),
            "successChance": chance,
            "materials": materials,
            "produced": produced,
            "outcomes": outcomes,
            "furnaceDamage": damage,
            "proficiencyGained": gained,
        }

    def _material_cost(self, item, quantity, extra):
        if extra == 0:
            return quantity
        p = self.player
        raw = quantity * (100 + extra) + p["materialRemainders"].get(item, 0)
        p["materialRemainders"][item] = raw % 100
        return raw // 100

    def _material_for_skill(self, skill):
        p = self.player
        school = self.pack["skills"][skill].get("school", "general")
        for k, n in self.pack["materials"].get(skill, {}).items():
            extra = (
                self._bonus("materialCost")
                if school in ("formation", "mechanism")
                else 0
            )
            self._consume(k, self._material_cost(k, n, extra))

    def prepare_formation(self, formation: str):
        p = self.player
        require(p["route"] == "xuanheng", "只有玄衡阵门可预阵")
        require(p["battle"] is None, "须开战前布置")
        require(p["preparedFormation"] is None, "已有一个预阵，不能叠加")
        require(formation in self.pack["formations"], "未知预阵")
        require(p["location"] in ("sect", "wild", "realm"), "此处不可布阵")
        cfg = self.pack["formations"][formation]
        for k, n in cfg["materials"].items():
            self._consume(k, self._material_cost(k, n, self._bonus("materialCost")))
        p["preparedFormation"] = {
            "id": formation,
            "location": p["location"],
            "node": p.get("node"),
        }
        return p["preparedFormation"]

    def _begin_route_battle(self, surprise):
        p = self.player
        b = p["battle"]
        b.update(
            surprise=surprise,
            attackStreak=0,
            swordMomentum=False,
            formation=None,
            firstDamage=0,
        )
        prepared = p["preparedFormation"]
        p["preparedFormation"] = None
        if (
            not surprise
            and prepared
            and prepared["location"] == p["location"]
            and prepared["node"] == p.get("node")
        ):
            b["formation"] = prepared["id"]
            f = self.pack["formations"][prepared["id"]]
            value = self._percent(f["value"], self._bonus("formationEffect"))
            if f["effect"] == "firstDamage":
                b["firstDamage"] = value
            else:
                self._effect(
                    b["enemy"] if f["effect"] == "slow" else p,
                    f["effect"],
                    value,
                    f["duration"],
                    "prearray",
                )
        return b

    def _combat_power(self, actor, skill, round_number):
        s = self.pack["skills"][skill]
        power = s["power"]
        accuracy = s["accuracy"]
        info = {}
        if actor is not self.player:
            return power, accuracy, info
        school = s.get("school", "general")
        p = self.player
        b = p["battle"]
        if school in ("formation", "talisman", "mechanism", "charm", "lightning") and s[
            "type"
        ] != "attack":
            power = self._percent(power, self._bonus(school + "Effect"))
        if school != "sword" and s["type"] != "attack":
            power = self._percent(power, self._bonus("nonSwordEffect"))
        if s["type"] == "heal":
            power = self._percent(power, self._bonus("healingEffect"))
        normalized = {"mechanism": "craft", "talisman": "formation"}.get(school, school)
        if s["type"] == "attack":
            power += (
                min(
                    self.pack["route_rules"]["proficiencyMaxLevel"],
                    p["proficiency"].get(normalized, 0)
                    // self.pack["route_rules"]["proficiencyLevelXp"],
                )
                * self.pack["route_rules"]["proficiencyPowerPerLevel"]
            )
        if s["type"] == "attack" and b["firstDamage"]:
            info["formationBonus"] = b["firstDamage"]
            b["firstDamage"] = 0
        if s["type"] == "attack" and b["swordMomentum"]:
            accuracy += self.pack["route_rules"]["swordMomentumHit"]
            info["momentumUsed"] = True
            b["swordMomentum"] = False
        return power, accuracy, info

    def _combat_damage(self, actor, skill, hit, info):
        if actor is not self.player:
            return hit
        p = self.player
        b = p["battle"]
        s = self.pack["skills"][skill]
        if s.get("school") == "sword":
            hit = self._percent(hit, self._bonus("swordDamage"))
        if s.get("school") != "sword":
            hit = self._percent(hit, self._bonus("nonSwordEffect"))
        if s.get("school") in ("formation", "talisman", "mechanism"):
            hit = self._percent(hit, self._bonus(s["school"] + "Effect"))
        hit = self._percent(hit, self._bonus("attackDamage"))
        if (
            b["enemy"]["type"] in ("普通妖兽", "精英妖兽", "Boss")
            and b["enemy"].get("species", "beast") == "beast"
        ):
            hit = self._percent(hit, self._bonus("beastDamage"))
        if b["surprise"] and b["round"] == 1:
            hit = self._percent(hit, self._bonus("surpriseDamage"))
        if info.get("momentumUsed"):
            hit = self._percent(hit, self.pack["route_rules"]["swordMomentumDamage"])
        if info.get("formationBonus"):
            hit += info["formationBonus"]
            info["formationDamage"] = info["formationBonus"]
        return max(1, hit)

    def _finish_route_turn(self, skill, log, result, battle):
        p = self.player
        own = next((x for x in log if x.get("actor") == "player"), {})
        controlled = (
            own.get("skipped") == "controlled"
            or any(
                x.get("actor") == "enemy"
                and x.get("effect") in ("freeze", "stun", "root")
                for x in log
            )
            or any(e["type"] in ("freeze", "stun", "root") for e in p["statusEffects"])
        )
        attacked = (
            skill in self.pack["skills"]
            and self.pack["skills"][skill]["type"] == "attack"
            and not controlled
            and "skill" in own
        )
        if p["route"] == "qingxiao":
            if controlled:
                battle["attackStreak"] = 0
                battle["swordMomentum"] = False
            elif attacked:
                battle["attackStreak"] += 1
                if battle["attackStreak"] >= 2:
                    battle["swordMomentum"] = True
                    battle["attackStreak"] = 0
            else:
                battle["attackStreak"] = 0
            result["swordMomentum"] = battle["swordMomentum"]
        if own.get("skill") and not own.get("skipped"):
            school = self.pack["skills"][own["skill"]].get("school", "general")
            result["proficiencyGained"] = self._gain_proficiency(
                school, self.pack["route_rules"]["combatXp"], "combat"
            )
        if p["battle"] is None:
            p["statusEffects"] = [
                e for e in p["statusEffects"] if e["source"] != "prearray"
            ]
        return result

    def _pill_effects(self, item):
        base = self.pack["items"][item].get("baseItem", item)
        quality = self.pack["items"][item].get("quality", "ordinary")
        factor = self.pack["route_rules"]["qualityEffects"][quality]
        effects = self.pack["items"][base]["effects"]
        return {
            k: self._percent(v * factor // 100, self._bonus("pillEffect"))
            for k, v in effects.items()
        }, max(0, self.pack["route_rules"]["pillSideEffect"] * (200 - factor) // 100)

    def _restore(self, item="potion"):
        p = self.player
        effects, side = self._pill_effects(item)
        if not any(e["type"] == "heal_block" for e in p["statusEffects"]):
            p["hp"] = min(p["max_hp"], p["hp"] + effects.get("hp", 0))
        p["qi"] = min(p["maxQi"], p["qi"] + effects.get("qi", 0))
        if side:
            self._effect(p, "weakness", side, 2, "pill")

    def _breakthrough_resource(self, pill):
        p = self.player
        items = [pill + "_superior", pill + "_fine", pill]
        item = next((i for i in items if p["inventory"].get(i, 0) > 0), None)
        require(item is not None, "突破丹药不足")
        self._consume(item, 1)
        surcharge = (
            self._percent(
                self.pack["prices"][pill], self._bonus("breakthroughCost"), True
            )
            - self.pack["prices"][pill]
        )
        require(p["stones"] >= surcharge, "散修突破材料溢价不足")
        p["stones"] -= surcharge
        quality = self.pack["items"][item].get("quality", "ordinary")
        return 5 if quality == "superior" else 2 if quality == "fine" else 0

    def _recovery_location(self):
        return "town" if self._is_rogue() else "sect"

    def _retreat_route(self, duration):
        p = self.player
        require(self._can_cultivate(), "需在宗门或散修客舍闭关")
        fee = (
            duration * self.pack["route_rules"]["rogueRecoveryHourly"]
            if self._is_rogue()
            else 0
        )
        require(p["stones"] >= fee, "散修没有免费疗伤，客舍费用不足")
        p["stones"] -= fee
        p["hp"] = min(
            p["max_hp"],
            p["hp"] + self._percent(duration * 20, self._bonus("healingEffect")),
        )
        p["qi"] = min(p["maxQi"], p["qi"] + duration * 10)
        p["statusEffects"] = [
            e for e in p["statusEffects"] if e["type"] == "injury" and duration < 8
        ]
        return {"hp": p["hp"], "qi": p["qi"], "duration": duration, "cost": fee}

    def _stock(self):
        p = self.player
        if p["location"] == "sect":
            return (
                self.pack["route_stock"].get(p["route"], list(self.pack["prices"]))
                if not self._is_rogue()
                else []
            )
        if p["location"] == "town" and p.get("node") == "黑市":
            return p["blackmarket"]["stock"]
        return [
            i for i in self.pack["prices"] if i not in self.pack["blackmarket_stock"]
        ]

    def _shop_price(self, item, side, price):
        p = self.player
        if side == "buy":
            require(item in self._stock(), "商店没有这件商品")
            if self._current_event().get("id") == "caravan":
                price = max(1, price * 9 // 10)
            if (
                self._current_event().get("id") == "auction"
                and self.pack["items"][item]["type"] == "法器"
            ):
                price = price * 12 // 10
            extra = self._bonus("purchasePrice") + (
                self._bonus("townPrice") if p["location"] == "town" else 0
            )
            price = self._percent(price, extra, True)
        return price

    def _after_trade(self, item, side):
        p = self.player
        if p["location"] == "town":
            key = "blackmarket" if p.get("node") == "黑市" else "market"
            p["credibility"][key] += 1
        if p["route"] == "danxia" and item == "forbidden_pill" and side == "sell":
            self._violate("私售禁丹" if side == "sell" else "私藏禁丹")
        if (
            p["route"] == "xuanheng"
            and item in ("mechanism_part", "core_array_chart")
            and side == "sell"
            and p["location"] == "town"
        ):
            self._violate("擅自外售宗门机关或阵图")

    def _violate(self, reason):
        p = self.player
        p["conduct"]["violations"].append(
            {"reason": reason, "time": self.state["minutes"]}
        )
        rep_loss = min(p["reputation"], 5)
        fine = min(p["stones"], 10)
        p["stones"] -= fine
        p["reputation"] = max(0, p["reputation"] - 5)
        p["conduct"]["penalties"].append(
            {"reason": reason, "stones": fine, "reputation": rep_loss}
        )
        if self._is_rogue():
            p["credibility"]["wanted"].append(
                {"reason": reason, "time": self.state["minutes"]}
            )

    def _route_quest(self, quest):
        q = self.pack["quests"][quest]
        require(
            q.get("route") in (None, self.player["route"]), "这是其他宗门或路线的任务"
        )
        require(not self._is_rogue() or q["location"] != "sect", "散修无法领取宗门任务")

    def _quest_reputation(self, q):
        return (
            self._percent(q["reputation"], self._bonus("combatReputation"))
            if "kill" in q
            else q["reputation"]
        )

    def _quest_extra_objective(self, q):
        if "counter" in q:
            require(
                self.player["counters"].get(q["counter"], 0) >= q["quantity"],
                "任务条件尚未完成",
            )
            return True
        return False

    def _rogue_quest_completion(self):
        if self._is_rogue():
            for k in ("alliance", "team"):
                self.player["credibility"][k] += 1

    def _route_travel(self, destination, node):
        p = self.player
        if destination == "sect":
            require(not self._is_rogue(), "散修没有宗门驻地，请使用坊市客舍")
        if destination == "sect" and p["route"]:
            require(
                node is None or node in self._route()["nodes"], "所在宗门没有这个节点"
            )
        if p["preparedFormation"] and (
            destination != p["location"] or node is not None and node != p.get("node")
        ):
            p["preparedFormation"] = None

    def _blackmarket_refresh(self):
        p = self.player
        day = self.state["minutes"] // 1440
        if (
            p["location"] == "town"
            and p.get("node") == "黑市"
            and p["blackmarket"]["day"] != day
        ):
            chance = self.pack["route_rules"]["blackmarketChance"] + self._bonus(
                "blackmarketChance"
            )
            p["blackmarket"] = {
                "day": day,
                "stock": [
                    i
                    for i in self.pack["blackmarket_stock"]
                    if self._roll("blackmarket_stock") <= chance
                ],
            }

    def track(self, target: str):
        p = self.player
        require(p["location"] == "wild", "追踪需在野外")
        require(
            target in self.pack["enemies"]
            and self.pack["enemies"][target]["location"] == "wild",
            "未知荒野目标",
        )
        chance = min(
            100, self.pack["route_rules"]["trackChance"] + self._bonus("trackChance")
        )
        success = self._roll("tracking") <= chance
        p["tracked"] = target if success else None
        return {
            "target": target,
            "success": success,
            "chance": chance,
            "nextAction": "fight" if success else "track",
        }

    def _track_reward(self, target):
        if self.player["tracked"] == target:
            self._add("core", 1)
            self.player["tracked"] = None
            return {"core": 1}
        return {}

    def _explore_route_event(self):
        p = self.player
        rules = self.pack["route_rules"]
        if p["location"] == "realm" and self._roll("detect_anomaly") <= rules[
            "anomalyChance"
        ] + self._bonus("anomalyChance"):
            p["counters"]["anomalies"] = p["counters"].get("anomalies", 0) + 1
            return "anomaly"
        if self._roll("adventure") <= rules["adventureChance"] + self._bonus(
            "adventureChance"
        ):
            return "adventure"
        return self.pack["exploration"][
            (self._roll("explore") - 1) % len(self.pack["exploration"])
        ]

    def _explore_extra(self, event, result):
        p = self.player
        rules = self.pack["route_rules"]
        if (
            event in ("herb", "cave")
            and self._bonus("herbExtraChance")
            and self._roll("extra_herb") <= self._bonus("herbExtraChance")
        ):
            self._add("herb", 1)
            result["extraHerb"] = 1
        if event in ("trap", "anomaly"):
            chance = min(100, rules["disarmChance"] + self._bonus("disarmChance"))
            disarmed = self._roll("disarm") <= chance
            result["disarm"] = {"chance": chance, "success": disarmed}
            if disarmed:
                p["counters"]["disarms"] = p["counters"].get("disarms", 0) + 1
                self._add("iron", 1)
                return False
            injury = max(
                0,
                rules["wildInjuryChance"]
                + (self._bonus("wildInjuryChance") if p["location"] == "wild" else 0),
            )
            harmed = self._roll("explore_injury") <= injury
            result["injuryChance"] = injury
            if harmed:
                p["hp"] = max(1, p["hp"] - 8)
                self._effect(p, "bleed", 2, 3, "trap")
            return False
        if event == "adventure":
            self._add("relic_fragment", 1)
            result["loot"] = {"relic_fragment": 1}
            p["credibility"]["alliance"] += 1
        return True

    def _advance_beasts(self, old_minutes, new_minutes):
        for record in self.state["players"].values():
            pet = record.get("beast")
            if not pet:
                continue
            old = pet["lastFed"]
            missed = max(0, (new_minutes - old) // 1440) - max(
                0, (old_minutes - old) // 1440
            )
            if missed:
                pet["loyalty"] = max(0, pet["loyalty"] - missed * 10)
                pet["status"] = "hungry"
                if pet["loyalty"] <= 0:
                    pet["status"] = "released"
                    record["history"].append(
                        {
                            "time": new_minutes,
                            "location": record["location"],
                            "action": "beast_release",
                            "result": {"reason": "长期缺粮", "name": pet["name"]},
                        }
                    )
                    record["conduct"]["violations"].append(
                        {"time": new_minutes, "reason": "未照料契约灵兽"}
                    )
                    record["beast"] = None

    def manage_beast(
        self, action: str, beast: str | None = None, stance: str = "assist"
    ):
        p = self.player
        require(
            p["route"] == "fuyao"
            or self._is_rogue()
            and "beast_lore" in p["techniques"],
            "需伏妖门身份或散修御兽传承",
        )
        require(
            action
            in ("contract", "feed", "heal", "stance", "release", "abuse", "evolve"),
            "未知灵兽动作",
        )
        require(p["battle"] is None, "战斗中不能重新调整契约或养育")
        pet = p["beast"]
        if action == "contract":
            require(pet is None, "只能拥有一个主要契约灵兽")
            require(beast in self.pack["beasts"], "未知灵兽")
            require(
                p["location"] == self._recovery_location(), "须在宗门或散修盟登记契约"
            )
            fee = self.pack["route_rules"]["beastContractCost"]
            require(p["stones"] >= fee, "契约费不足")
            p["stones"] -= fee
            pet = copy.deepcopy(self.pack["beasts"][beast])
            pet.update(
                id=beast,
                level=1,
                xp=0,
                loyalty=70,
                hp=pet["maxHp"],
                injuries=0,
                status="healthy",
                statusEffects=[],
                lastFed=self.state["minutes"],
                stance="assist",
                force=False,
            )
            p["beast"] = pet
        else:
            require(pet is not None, "没有契约灵兽")
            if action == "feed":
                fee = self.pack["route_rules"]["beastFeedCost"]
                require(p["stones"] >= fee, "饲养费不足")
                p["stones"] -= fee
                pet["lastFed"] = self.state["minutes"]
                pet["loyalty"] = min(100, pet["loyalty"] + 10)
                pet["status"] = "injured" if pet["injuries"] else "healthy"
                pet["xp"] += self._percent(1000, self._bonus("petGrowth"))
                self._pet_level(pet)
            elif action == "heal":
                self._consume("potion", 1)
                pet["hp"] = pet["maxHp"]
                pet["injuries"] = 0
                pet["status"] = "healthy"
                p["counters"]["beastCare"] = p["counters"].get("beastCare", 0) + 1
            elif action == "stance":
                require(stance in ("assist", "rest", "forced"), "未知出战策略")
                pet["stance"] = "assist" if stance == "forced" else stance
                pet["force"] = stance == "forced"
            elif action == "abuse":
                pet["loyalty"] = max(0, pet["loyalty"] - 30)
                pet["hp"] = max(0, pet["hp"] - 10)
                pet["injuries"] += 1
                pet["status"] = "injured"
                self._violate("虐待契约灵兽")
            elif action == "release":
                require(
                    p["location"] == self._recovery_location(),
                    "解除契约须回宗门或散修盟登记",
                )
                p["conduct"].setdefault("releases", []).append(
                    {"time": self.state["minutes"], "beast": pet["id"]}
                )
                p["beast"] = None
                return {"released": True, "registered": True}
            elif action == "evolve":
                rules = self.pack["route_rules"]["beastEvolution"]
                stage = pet.get("evolution")
                if not stage:
                    need_level = rules["awakenLevel"]
                    need_crystals = rules["awakenCrystals"]
                    need_stones = rules["awakenStones"]
                    name = "灵醒"
                    hp_gain = rules["awakenMaxHp"]
                    str_gain = rules["awakenStrength"]
                elif stage == "灵醒":
                    need_level = rules["formLevel"]
                    need_crystals = rules["formCrystals"]
                    need_stones = rules["formStones"]
                    name = "化形"
                    hp_gain = rules["formMaxHp"]
                    str_gain = rules["formStrength"]
                else:
                    require(False, "灵兽已至化形,无法再进化")
                require(
                    pet["level"] >= need_level, f"灵兽需 {need_level} 级才能{name}"
                )
                require(pet["injuries"] == 0, "灵兽带伤,先疗伤再进化")
                self._consume(rules["crystalItem"], need_crystals)
                require(p["stones"] >= need_stones, f"进化需 {need_stones} 灵石")
                p["stones"] -= need_stones
                pet["maxHp"] += hp_gain
                pet["hp"] = min(pet["maxHp"], pet["hp"] + hp_gain)
                pet["strength"] += str_gain
                pet["evolution"] = name
                if name == "灵醒" and "guard" not in pet["skills"]:
                    pet["skills"].append("guard")
            if pet["loyalty"] <= 0:
                p["beast"] = None
                return {"released": True, "reason": "忠诚耗尽"}
        return copy.deepcopy(pet)

    def _pet_level(self, pet):
        level = 1 + pet["xp"] // 5000
        if level > pet["level"]:
            diff = level - pet["level"]
            pet["strength"] += diff * 2
            pet["maxHp"] += diff * 5
            pet["hp"] = min(pet["maxHp"], pet["hp"] + diff * 5)
            pet["level"] = level

    def _pet_turn(self, enemy, log):
        p = self.player
        pet = p["beast"]
        if (
            not pet
            or pet["stance"] == "rest"
            or pet["hp"] <= 0
            or enemy["hp"] <= 0
            or p["hp"] <= 0
        ):
            return
        if pet["status"] in ("hungry", "injured") and not pet["force"]:
            log.append({"actor": "beast", "skipped": pet["status"]})
            return
        if pet["force"] and pet["injuries"]:
            pet["loyalty"] = max(0, pet["loyalty"] - 15)
            if pet["loyalty"] == 0:
                p["beast"] = None
                log.append({"actor": "beast", "released": "被迫重伤出战"})
                return
        skill = (
            "strike"
            if pet["personality"] == "勇猛" or pet["hp"] > pet["maxHp"] // 3
            else "guard"
        )
        if skill not in pet["skills"]:
            skill = "strike"
        if skill == "guard":
            log.append({"actor": "beast", "skill": "guard", "damage": 0})
            return
        from .rules import damage, hit_chance

        hit = 0
        if self._roll("beast_hit") <= hit_chance(
            95, pet["agility"], self._stats(enemy)["agility"]
        ):
            hit = damage(100, pet["strength"], self._stats(enemy)["defense"])
        enemy["hp"] = max(0, enemy["hp"] - hit)
        received = (
            0 if enemy["hp"] <= 0 else max(1, enemy["strength"] // 2 - pet["defense"])
        )
        pet["hp"] = max(0, pet["hp"] - received)
        if pet["hp"] == 0:
            pet["injuries"] += 1
            pet["status"] = "injured"
            pet["loyalty"] = max(0, pet["loyalty"] - 10)
        pet["xp"] += self._percent(200, self._bonus("petGrowth"))
        self._pet_level(pet)
        log.append(
            {
                "actor": "beast",
                "skill": skill,
                "damage": hit,
                "received": received,
                "hp": pet["hp"],
            }
        )
        # 化形灵兽的撕咬:命中后按配置概率追加一次半伤连击。
        if (
            hit > 0
            and enemy["hp"] > 0
            and pet.get("evolution") == "化形"
            and self._roll("beast_combo")
            <= self.pack["route_rules"]["beastEvolution"]["formComboChance"]
        ):
            combo = max(1, hit // 2)
            enemy["hp"] = max(0, enemy["hp"] - combo)
            log.append({"actor": "beast", "skill": "combo", "damage": combo})

    def _route_world(self, result):
        p = self.player
        result["routes"] = (
            self.pack["routes"] if p["route"] is None else {p["route"]: self._route()}
        )
        result["routes"] = {
            k: {
                "name": v["name"],
                "position": v["position"],
                "mechanism": v["mechanism"],
            }
            for k, v in result["routes"].items()
        }
        result["selectedRoute"] = p["route"]
        result["shop"] = (
            {
                i: self._shop_price(i, "buy", self.pack["prices"][i])
                for i in self._stock()
            }
            if p["location"] in ("sect", "town")
            else {}
        )
        result["quests"] = {
            k: q
            for k, q in result["quests"].items()
            if q.get("route") in (None, p["route"])
            and not (self._is_rogue() and q["location"] == "sect")
        }
        if p["location"] == "sect" and p["route"]:
            result["location"] = copy.deepcopy(result["location"])
            result["location"]["name"] = self._route()["name"]
            result["location"]["nodes"] = self._route()["nodes"]
            if "elder" in result["npcs"]:
                result["npcs"] = copy.deepcopy(result["npcs"])
                result["npcs"]["elder"]["name"] = self._route()["teacher"]
        result["beast"] = copy.deepcopy(p["beast"])
        result["preparedFormation"] = copy.deepcopy(p["preparedFormation"])
        return result
