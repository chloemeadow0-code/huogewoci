"""Snapshot key-handling tests: default round-trip fidelity vs --redact-key."""

import json
import logging

import pytest

from xiuxian.island import IslandGame
from xiuxian.operator import operate


@pytest.fixture
def island(tmp_path):
    g = IslandGame(tmp_path / "snap.db", player_key="test", player_name="快照修士")
    assert g.call("choose_route", route="qingxiao")["ok"]
    yield g
    g.close()


def test_default_save_load_roundtrip_keeps_rng_key(island):
    key = island.state["rngKey"]
    operate(island.path, "save", "plain")
    island.call("rename", name="改名后")
    operate(island.path, "load", "plain")
    island.state = island.storage.load()
    assert island.state["rngKey"] == key
    body = json.loads(
        island.db.execute("SELECT body FROM snapshots WHERE name='plain'").fetchone()[0]
    )
    for row in body["tables"]["world_state"]:
        assert row["rng_key"] == key  # faithful snapshot carries the key


def test_redact_save_nulls_key_and_omits_it_from_body(island):
    key = island.state["rngKey"]
    operate(island.path, "save", "shared", redact_key=True)
    body = json.loads(
        island.db.execute("SELECT body FROM snapshots WHERE name='shared'").fetchone()[0]
    )
    for row in body["tables"]["world_state"]:
        assert row["rng_key"] is None
    assert key not in json.dumps(body)  # raw key never appears in snapshot JSON
    assert island.storage.load()["rngKey"] == key  # live database untouched


def test_redact_snapshot_load_generates_new_key(island, monkeypatch):
    old_key = island.state["rngKey"]
    operate(island.path, "save", "shared", redact_key=True)
    island.close()
    import xiuxian.db as db

    monkeypatch.setattr(db, "new_rng_key", lambda: "22" * 32)
    operate(island.path, "load", "shared")
    g = IslandGame(island.path, player_key="test")
    try:
        assert g.state["rngKey"] == "22" * 32
        assert g.state["rngKey"] != old_key
        assert (
            g.db.execute("SELECT rng_key FROM world_state WHERE id=1").fetchone()[0]
            == "22" * 32
        )
        assert g.call("cultivate", duration=1)["ok"]  # world keeps running
    finally:
        g.close()


def test_legacy_snapshot_without_key_loads(island, monkeypatch):
    import xiuxian.db as db

    monkeypatch.setattr(db, "new_rng_key", lambda: "33" * 32)
    operate(island.path, "save", "legacy")
    island.close()
    # forge a pre-S3 snapshot body without the rng_key field
    import sqlite3

    con = sqlite3.connect(island.path)
    body = json.loads(
        con.execute("SELECT body FROM snapshots WHERE name='legacy'").fetchone()[0]
    )
    for record in body["tables"]["world_state"]:
        record.pop("rng_key", None)
    con.execute(
        "UPDATE snapshots SET body=? WHERE name='legacy'",
        (json.dumps(body, ensure_ascii=False, separators=(",", ":")),),
    )
    con.commit()
    con.close()
    operate(island.path, "load", "legacy")
    g = IslandGame(island.path, player_key="test")
    try:
        assert g.state["rngKey"] == "33" * 32  # regenerated, not leaked from anywhere
        assert g.call("cultivate", duration=1)["ok"]
    finally:
        g.close()


def test_default_save_warns_redact_silent(island, caplog):
    key = island.state["rngKey"]
    with caplog.at_level(logging.WARNING, logger="xiuxian.operator"):
        operate(island.path, "save", "plain")
        assert any(
            "rng_key" in r.getMessage() and "--redact-key" in r.getMessage()
            for r in caplog.records
        )
        assert key not in caplog.text  # the key value itself is never logged
        caplog.clear()
        operate(island.path, "save", "shared", redact_key=True)
        assert not caplog.records  # redacted save stays silent


def test_operate_error_is_logged_without_key(island, caplog):
    key = island.state["rngKey"]
    with caplog.at_level(logging.ERROR, logger="xiuxian.operator"):
        try:
            operate(island.path, "save", "no-world")  # nothing raises here, so force one
            operate(":memory:", "save", "broken")
        except Exception:
            pass
    assert any(
        "action=save" in r.getMessage() and "name=broken" in r.getMessage()
        and r.exc_info
        for r in caplog.records
    )
    assert key not in caplog.text
