"""Trusted local relational snapshots; never exposed as player tools."""

import argparse, json, re
from .db import Store, SCHEMA, dumps

TABLES = tuple(
    n
    for n in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA)
    if n != "snapshots"
)


def operate(path, action, name=None):
    storage = Store(path)
    db = storage.db
    try:
        db.execute("BEGIN IMMEDIATE")
        if action == "list":
            result = [
                dict(r)
                for r in db.execute(
                    "SELECT name,created_at FROM snapshots ORDER BY created_at,name"
                )
            ]
        elif action == "save":
            if not db.execute("SELECT 1 FROM world_state").fetchone():
                raise ValueError("请先用新版服务打开旧存档，迁移后再建快照")
            body = {
                "version": 1,
                "tables": {
                    t: [dict(r) for r in db.execute(f'SELECT * FROM "{t}"')]
                    for t in TABLES
                },
            }
            db.execute(
                "INSERT OR REPLACE INTO snapshots VALUES (?,CURRENT_TIMESTAMP,?)",
                (name, dumps(body)),
            )
            result = {"saved": name, "tables": len(TABLES)}
        elif action == "load":
            row = db.execute(
                "SELECT body FROM snapshots WHERE name=?", (name,)
            ).fetchone()
            if row is None:
                raise ValueError("没有这个快照")
            body = json.loads(row[0])
            if body.get("version") != 1 or set(body["tables"]) != set(TABLES):
                raise ValueError("快照结构不兼容")
            for table in reversed(TABLES):
                db.execute(f'DELETE FROM "{table}"')
            for table in TABLES:
                allowed = {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
                for record in body["tables"][table]:
                    if not set(record) <= allowed:
                        raise ValueError("快照字段不兼容")
                    columns = ",".join(f'"{c}"' for c in record)
                    marks = ",".join("?" for _ in record)
                    db.execute(
                        f'INSERT INTO "{table}" ({columns}) VALUES ({marks})',
                        tuple(record.values()),
                    )
            result = {"loaded": name, "tables": len(TABLES)}
        else:
            raise ValueError("未知快照操作")
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="灵汐岛管理员快照；load前须停服务")
    parser.add_argument("--db", default="data/xiuxian.db")
    parser.add_argument("action", choices=["save", "load", "list"])
    parser.add_argument("name", nargs="?")
    args = parser.parse_args()
    if args.action != "list" and not args.name:
        parser.error("save/load requires a name")
    print(dumps(operate(args.db, args.action, args.name)))


if __name__ == "__main__":
    main()
