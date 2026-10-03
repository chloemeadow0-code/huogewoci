"""Trusted local relational snapshots; never exposed as player tools."""

import argparse
import json
import logging
import re
from .db import Store, SCHEMA, dumps

logger = logging.getLogger(__name__)

TABLES = tuple(
    n
    for n in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA)
    if n != "snapshots"
)


def operate(path, action, name=None, redact_key=False):
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
            if redact_key:
                # Opt-in: strip the server-side roll key from the snapshot so
                # it cannot be shared by accident. Loading such a snapshot
                # regenerates a fresh key; the original roll sequence is no
                # longer reproducible (documented trade-off).
                for row in body["tables"]["world_state"]:
                    if "rng_key" in row:
                        row["rng_key"] = None
            db.execute(
                "INSERT OR REPLACE INTO snapshots VALUES (?,CURRENT_TIMESTAMP,?)",
                (name, dumps(body)),
            )
            result = {"saved": name, "tables": len(TABLES)}
            if not redact_key:
                logger.warning(
                    "快照包含随机数密钥 rng_key，请按机密保管；如需分享请使用 --redact-key"
                )
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
        logger.exception("snapshot operation failed: action=%s name=%s", action, name)
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="灵汐岛管理员快照；load前须停服务")
    parser.add_argument("--db", default="data/xiuxian.db")
    parser.add_argument("action", choices=["save", "load", "list"])
    parser.add_argument("name", nargs="?")
    parser.add_argument(
        "--redact-key",
        action="store_true",
        help="仅 save 可用：把快照里的 rng_key 置空；load 后世界生成新密钥，"
        "原随机序列不可复现",
    )
    args = parser.parse_args()
    if args.action != "list" and not args.name:
        parser.error("save/load requires a name")
    if args.redact_key and args.action != "save":
        parser.error("--redact-key 只能与 save 一起使用")
    logging.basicConfig()
    print(dumps(operate(args.db, args.action, args.name, redact_key=args.redact_key)))


if __name__ == "__main__":
    main()
