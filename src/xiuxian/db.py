"""Lingxi relational storage; core state is stored in independent SQLite tables."""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path

from .rules import new_rng_key


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


STATS = "stage cultivation hp max_hp qi maxQi spirit strength agility defense aptitude reputation stones level explores realmVisit cooldownUntil".split()
CORE = "name sect realm location node method root createdAt".split()
CHILD = {
    "inventory",
    "equipment",
    "techniques",
    "skills",
    "relationships",
    "quests",
    "statusEffects",
    "history",
    "battle",
    "beast",
    "incidents",
    "questStages",
    "ledgers",
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS world_state(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER,tick INTEGER,minutes INTEGER,rng INTEGER,cycle INTEGER,rng_key TEXT);
CREATE TABLE IF NOT EXISTS cultivators(id TEXT PRIMARY KEY,name TEXT,sect TEXT,realm TEXT,location TEXT,node TEXT,method TEXT,root TEXT,createdAt TEXT);
CREATE TABLE IF NOT EXISTS cultivator_stats(cultivator_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS cultivator_meta(cultivator_id TEXT,key TEXT,value TEXT,PRIMARY KEY(cultivator_id,key));
CREATE TABLE IF NOT EXISTS cultivator_inventory(cultivator_id TEXT,item TEXT,quantity INTEGER,PRIMARY KEY(cultivator_id,item));
CREATE TABLE IF NOT EXISTS cultivator_equipment(cultivator_id TEXT,slot TEXT,item TEXT,PRIMARY KEY(cultivator_id,slot));
CREATE TABLE IF NOT EXISTS cultivator_techniques(cultivator_id TEXT,technique TEXT,position INTEGER,level INTEGER,PRIMARY KEY(cultivator_id,technique));
CREATE TABLE IF NOT EXISTS cultivator_skills(cultivator_id TEXT,skill TEXT,position INTEGER,PRIMARY KEY(cultivator_id,skill));
CREATE TABLE IF NOT EXISTS cultivator_status(cultivator_id TEXT,position INTEGER,type TEXT,value INTEGER,duration INTEGER,source TEXT,details TEXT,PRIMARY KEY(cultivator_id,position));
CREATE TABLE IF NOT EXISTS npc_relationships(cultivator_id TEXT,npc TEXT,friendliness INTEGER,trust INTEGER,hostility INTEGER,dialogue TEXT,PRIMARY KEY(cultivator_id,npc));
CREATE TABLE IF NOT EXISTS quest_progress(cultivator_id TEXT,quest TEXT,status TEXT,stage INTEGER,branch TEXT,details TEXT,PRIMARY KEY(cultivator_id,quest));
CREATE TABLE IF NOT EXISTS histories(cultivator_id TEXT,position INTEGER,tick INTEGER,time INTEGER,location TEXT,action TEXT,arguments TEXT,result TEXT,changes TEXT,random TEXT,PRIMARY KEY(cultivator_id,position));
CREATE TABLE IF NOT EXISTS world_events(position INTEGER PRIMARY KEY,event_id TEXT,day INTEGER,details TEXT);
CREATE TABLE IF NOT EXISTS world_flags(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS world_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,tick INTEGER,time INTEGER,actor TEXT,action TEXT,summary TEXT);
CREATE TABLE IF NOT EXISTS incidents(cultivator_id TEXT,id INTEGER,type TEXT,status TEXT,opened INTEGER,closed INTEGER,choice TEXT,details TEXT,PRIMARY KEY(cultivator_id,id));
CREATE TABLE IF NOT EXISTS item_ledgers(cultivator_id TEXT,id INTEGER,item TEXT,status TEXT,details TEXT,PRIMARY KEY(cultivator_id,id));
CREATE TABLE IF NOT EXISTS battles(cultivator_id TEXT PRIMARY KEY,target TEXT,round INTEGER,enemy_hp INTEGER,enemy_qi INTEGER,details TEXT);
CREATE TABLE IF NOT EXISTS battle_turns(cultivator_id TEXT,tick INTEGER,round INTEGER,details TEXT,PRIMARY KEY(cultivator_id,tick));
CREATE TABLE IF NOT EXISTS spirit_beasts(cultivator_id TEXT PRIMARY KEY,species TEXT,name TEXT,level INTEGER,hp INTEGER,loyalty INTEGER,personality TEXT,status TEXT,details TEXT);
CREATE TABLE IF NOT EXISTS sect_members(cultivator_id TEXT PRIMARY KEY,sect TEXT,contribution INTEGER);
CREATE TABLE IF NOT EXISTS sect_reputation(cultivator_id TEXT,sect TEXT,reputation INTEGER,PRIMARY KEY(cultivator_id,sect));
CREATE TABLE IF NOT EXISTS event_rolls(cultivator_id TEXT,tick INTEGER,position INTEGER,purpose TEXT,value INTEGER,PRIMARY KEY(cultivator_id,tick,position));
CREATE TABLE IF NOT EXISTS exploration_logs(cultivator_id TEXT,tick INTEGER,location TEXT,details TEXT,PRIMARY KEY(cultivator_id,tick));
CREATE TABLE IF NOT EXISTS market_listings(id TEXT PRIMARY KEY,item TEXT,price INTEGER,quantity INTEGER,ends INTEGER,details TEXT);
CREATE TABLE IF NOT EXISTS quests(id TEXT PRIMARY KEY,name TEXT,location TEXT,details TEXT);
CREATE TABLE IF NOT EXISTS snapshots(name TEXT PRIMARY KEY,created_at TEXT,body TEXT);
CREATE TABLE IF NOT EXISTS idempotency(cultivator_id TEXT,request_id TEXT,fingerprint TEXT,response TEXT,PRIMARY KEY(cultivator_id,request_id));
CREATE TABLE IF NOT EXISTS migrations(name TEXT PRIMARY KEY,applied_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(world_state)")}
        if "rng_key" not in columns:
            self.db.execute("ALTER TABLE world_state ADD COLUMN rng_key TEXT")
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(cultivator_stats)")}
        for column in STATS:
            if column not in columns:
                self.db.execute(
                    f'ALTER TABLE cultivator_stats ADD COLUMN "{column}" INTEGER'
                )
        self.db.commit()

    def load(self):
        world = self.db.execute("SELECT * FROM world_state WHERE id=1").fetchone()
        if not world:
            if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='session_meta'"
            ).fetchone():
                row = self.db.execute(
                    "SELECT value FROM session_meta WHERE key='xiuxian_state' ORDER BY session_id DESC LIMIT 1"
                ).fetchone()
                if row:
                    self.db.execute(
                        "INSERT OR IGNORE INTO migrations(name) VALUES ('qingyun_json_to_relational')"
                    )
                    state = json.loads(row[0])
                    state.setdefault("rngKey", new_rng_key())
                    return state
            return {
                "version": 1,
                "tick": 0,
                "minutes": 0,
                "rng": 1234567,
                "rngKey": new_rng_key(),
                "realm": {"cycle": 0},
                "players": {},
                "events": [],
            }
        state = {k: world[k] for k in ("version", "tick", "minutes", "rng")}
        state["rngKey"] = world["rng_key"] or new_rng_key()
        state.update(realm={"cycle": world["cycle"]}, events=[], players={})
        state["events"] = [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT details FROM world_events ORDER BY position"
            )
        ]
        state["flags"] = {
            r[0]: json.loads(r[1])
            for r in self.db.execute("SELECT key,value FROM world_flags")
        }
        for row in self.db.execute("SELECT * FROM cultivators"):
            owner = row["id"]
            p = {k: row[k] for k in CORE}
            p["id"] = owner
            stats = self.db.execute(
                "SELECT * FROM cultivator_stats WHERE cultivator_id=?", (owner,)
            ).fetchone()
            p.update({k: stats[k] for k in STATS})
            p.update(
                {
                    r[0]: json.loads(r[1])
                    for r in self.db.execute(
                        "SELECT key,value FROM cultivator_meta WHERE cultivator_id=?",
                        (owner,),
                    )
                }
            )
            p["islandLocation"] = p["location"]
            p["location"] = p.pop(
                "legacyArea",
                (
                    "sect"
                    if p["location"] in ("qingxiao", "xuanheng", "danxia", "fuyao")
                    else (
                        "town"
                        if p["location"] in ("market", "blackmarket")
                        else "realm" if p["location"] == "secret" else "wild"
                    )
                ),
            )
            for key, table, keycol, valcol in [
                ("inventory", "cultivator_inventory", "item", "quantity"),
                ("equipment", "cultivator_equipment", "slot", "item"),
            ]:
                p[key] = {
                    r[0]: r[1]
                    for r in self.db.execute(
                        f"SELECT {keycol},{valcol} FROM {table} WHERE cultivator_id=?",
                        (owner,),
                    )
                }
            for key, table, keycol in [
                ("techniques", "cultivator_techniques", "technique"),
                ("skills", "cultivator_skills", "skill"),
            ]:
                p[key] = [
                    r[0]
                    for r in self.db.execute(
                        f"SELECT {keycol} FROM {table} WHERE cultivator_id=? ORDER BY position",
                        (owner,),
                    )
                ]
            p["relationships"] = {
                r["npc"]: {
                    "friendliness": r["friendliness"],
                    "trust": r["trust"],
                    "hostility": r["hostility"],
                    "dialogueState": json.loads(r["dialogue"]),
                }
                for r in self.db.execute(
                    "SELECT * FROM npc_relationships WHERE cultivator_id=?", (owner,)
                )
            }
            qr = list(
                self.db.execute(
                    "SELECT * FROM quest_progress WHERE cultivator_id=?", (owner,)
                )
            )
            p["quests"] = {r["quest"]: r["status"] for r in qr}
            p["questStages"] = {
                r["quest"]: json.loads(r["details"]) for r in qr if r["details"] != "{}"
            }
            p["statusEffects"] = [
                json.loads(r[0])
                for r in self.db.execute(
                    "SELECT details FROM cultivator_status WHERE cultivator_id=? ORDER BY position",
                    (owner,),
                )
            ]
            p["history"] = [
                {k: r[k] for k in ("tick", "time", "location", "action")}
                | {
                    k: json.loads(r[k])
                    for k in ("arguments", "result", "changes", "random")
                }
                for r in self.db.execute(
                    "SELECT * FROM histories WHERE cultivator_id=? ORDER BY position",
                    (owner,),
                )
            ]
            for key, table in [("battle", "battles"), ("beast", "spirit_beasts")]:
                r = self.db.execute(
                    f"SELECT details FROM {table} WHERE cultivator_id=?", (owner,)
                ).fetchone()
                p[key] = json.loads(r[0]) if r else None
            for key, table in [("incidents", "incidents"), ("ledgers", "item_ledgers")]:
                p[key] = [
                    json.loads(r[0])
                    for r in self.db.execute(
                        f"SELECT details FROM {table} WHERE cultivator_id=? ORDER BY id",
                        (owner,),
                    )
                ]
            state["players"][owner] = p
        return state

    def save(self, state):
        db = self.db
        db.execute(
            "INSERT OR REPLACE INTO world_state"
            " (id,version,tick,minutes,rng,cycle,rng_key) VALUES (1,?,?,?,?,?,?)",
            tuple(state[k] for k in ("version", "tick", "minutes", "rng"))
            + (state["realm"]["cycle"], state.get("rngKey") or new_rng_key()),
        )
        db.execute("DELETE FROM world_events")
        db.executemany(
            "INSERT INTO world_events VALUES (?,?,?,?)",
            [
                (i, e.get("id", "event"), e.get("day", 0), dumps(e))
                for i, e in enumerate(state["events"])
            ],
        )
        db.execute("DELETE FROM world_flags")
        db.executemany(
            "INSERT INTO world_flags VALUES (?,?)",
            [(k, dumps(v)) for k, v in state.get("flags", {}).items()],
        )
        for owner, p in state["players"].items():
            db.execute(
                "INSERT OR REPLACE INTO cultivators VALUES (?,?,?,?,?,?,?,?,?)",
                (owner,)
                + tuple(
                    p.get("islandLocation", p.get(k)) if k == "location" else p.get(k)
                    for k in CORE
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO cultivator_stats VALUES ("
                + ",".join("?" for _ in range(len(STATS) + 1))
                + ")",
                (owner,) + tuple(p.get(k, 0) for k in STATS),
            )
            tables = [
                "cultivator_meta",
                "cultivator_inventory",
                "cultivator_equipment",
                "cultivator_techniques",
                "cultivator_skills",
                "cultivator_status",
                "npc_relationships",
                "quest_progress",
                "histories",
                "incidents",
                "item_ledgers",
                "battles",
                "spirit_beasts",
            ]
            for table in tables:
                db.execute(f"DELETE FROM {table} WHERE cultivator_id=?", (owner,))
            db.executemany(
                "INSERT INTO cultivator_meta VALUES (?,?,?)",
                [
                    (owner, k, dumps(v))
                    for k, v in (p | {"legacyArea": p["location"]}).items()
                    if k not in {*CORE, *STATS, *CHILD, "id"}
                ],
            )
            for key, table in [
                ("inventory", "cultivator_inventory"),
                ("equipment", "cultivator_equipment"),
            ]:
                db.executemany(
                    f"INSERT INTO {table} VALUES (?,?,?)",
                    [(owner, k, v) for k, v in p[key].items()],
                )
            db.executemany(
                "INSERT INTO cultivator_techniques VALUES (?,?,?,?)",
                [
                    (owner, k, i, p.get("techniqueLevels", {}).get(k, 1))
                    for i, k in enumerate(p["techniques"])
                ],
            )
            db.executemany(
                "INSERT INTO cultivator_skills VALUES (?,?,?)",
                [(owner, k, i) for i, k in enumerate(p["skills"])],
            )
            db.executemany(
                "INSERT INTO cultivator_status VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        owner,
                        i,
                        e["type"],
                        e.get("value", 0),
                        e.get("duration", 0),
                        e.get("source", ""),
                        dumps(e),
                    )
                    for i, e in enumerate(p["statusEffects"])
                ],
            )
            db.executemany(
                "INSERT INTO npc_relationships VALUES (?,?,?,?,?,?)",
                [
                    (
                        owner,
                        k,
                        r.get("friendliness", 0),
                        r.get("trust", 0),
                        r.get("hostility", 0),
                        dumps(r.get("dialogueState", [])),
                    )
                    for k, r in p["relationships"].items()
                ],
            )
            db.executemany(
                "INSERT INTO quest_progress VALUES (?,?,?,?,?,?)",
                [
                    (
                        owner,
                        k,
                        status,
                        p.get("questStages", {}).get(k, {}).get("stage", 0),
                        p.get("questStages", {}).get(k, {}).get("branch", ""),
                        dumps(p.get("questStages", {}).get(k, {})),
                    )
                    for k, status in p["quests"].items()
                ],
            )
            db.executemany(
                "INSERT INTO histories VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        owner,
                        i,
                        h.get("tick", 0),
                        h.get("time", 0),
                        h.get("location", ""),
                        h["action"],
                        dumps(h.get("arguments", {})),
                        dumps(h.get("result", {})),
                        dumps(h.get("changes", {})),
                        dumps(h.get("random", [])),
                    )
                    for i, h in enumerate(p["history"])
                ],
            )
            for e in p.get("incidents", []):
                db.execute(
                    "INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?)",
                    (
                        owner,
                        e["id"],
                        e["type"],
                        e["status"],
                        e["opened"],
                        e.get("closed"),
                        e.get("choice"),
                        dumps(e),
                    ),
                )
            for e in p.get("ledgers", []):
                db.execute(
                    "INSERT INTO item_ledgers VALUES (?,?,?,?,?)",
                    (owner, e["id"], e["item"], e["status"], dumps(e)),
                )
            b = p.get("battle")
            if b:
                db.execute(
                    "INSERT INTO battles VALUES (?,?,?,?,?,?)",
                    (
                        owner,
                        b["target"],
                        b["round"],
                        b["enemy"]["hp"],
                        b["enemy"]["qi"],
                        dumps(b),
                    ),
                )
            pet = p.get("beast")
            if pet:
                db.execute(
                    "INSERT INTO spirit_beasts VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        owner,
                        pet.get("species", pet.get("id", "")),
                        pet.get("name", "灵兽"),
                        pet["level"],
                        pet["hp"],
                        pet["loyalty"],
                        pet.get("personality", ""),
                        pet.get("status", ""),
                        dumps(pet),
                    ),
                )
            db.execute(
                "INSERT OR REPLACE INTO sect_members VALUES (?,?,?)",
                (owner, p.get("route"), p.get("contribution", 0)),
            )
            db.execute(
                "INSERT OR REPLACE INTO sect_reputation VALUES (?,?,?)",
                (
                    owner,
                    p.get("route", "rogue"),
                    p.get("sectReputation", p["reputation"]),
                ),
            )
            for h in p["history"]:
                tick = h.get("tick", 0)
                if h["action"] == "explore":
                    db.execute(
                        "INSERT OR IGNORE INTO exploration_logs VALUES (?,?,?,?)",
                        (owner, tick, h.get("location", ""), dumps(h["result"])),
                    )
                if h["action"] in ("use_skill", "fight"):
                    db.execute(
                        "INSERT OR IGNORE INTO battle_turns VALUES (?,?,?,?)",
                        (
                            owner,
                            tick,
                            h.get("result", {}).get("round", 0),
                            dumps(h["result"]),
                        ),
                    )
                for i, r in enumerate(h.get("random", [])):
                    db.execute(
                        "INSERT OR IGNORE INTO event_rolls VALUES (?,?,?,?,?)",
                        (
                            owner,
                            tick,
                            i,
                            r.get("purpose", ""),
                            r.get("roll", r.get("value", 0)),
                        ),
                    )
