"""Shared fixtures for xiuxian regression tests."""


import pytest


@pytest.fixture(autouse=True)
def _fixed_rng_key(monkeypatch):
    """Pin the roll-stream key so replay-style tests stay deterministic.

    Tolerates older trees without the S3 symbols (pre-verification baseline)."""
    import xiuxian.engine as engine
    import xiuxian.db as db

    if hasattr(engine, "new_rng_key"):
        monkeypatch.setattr(engine, "new_rng_key", lambda: "11" * 32)
    if hasattr(db, "new_rng_key"):
        monkeypatch.setattr(db, "new_rng_key", lambda: "11" * 32)
