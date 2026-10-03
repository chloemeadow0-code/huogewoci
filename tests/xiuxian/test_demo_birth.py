"""Deterministic birth-boundary tests for the demo campaigns.

The demo scripts are fixed action sequences; with random births they used to
die on low-affinity/low-aptitude combinations (insufficient cultivation at
breakthrough, collapse-blocked exploration, boss already slain while
exploring, breakthrough pills running dry). These tests pin the two extreme
births — worst and best — so any demo-flow regression fails deterministically.
The injected randbelow sequences are restored by monkeypatch per test."""

import os

import pytest

from xiuxian.birth import generate_aptitude, generate_root
from xiuxian.engine import CONTENT

BIRTH = CONTENT["birth"]
ELEMENTS = BIRTH["elements"]
# generate_root accumulates countWeights into cumulative bounds 10/35/70/90/100.
COUNT_START = {1: 0, 2: 10, 3: 35, 4: 70, 5: 90}
APT_START = {1: 0, 2: 10, 3: 35, 4: 70, 5: 90}


def seq_for(count, chosen, aptitude):
    rolls = [COUNT_START[count]]
    remaining = list(ELEMENTS)
    for element in chosen:
        idx = remaining.index(element)
        rolls.append(idx)
        remaining.pop(idx)
    rolls.append(APT_START[aptitude])
    return rolls


def fixed_birth(monkeypatch, count, chosen, aptitude):
    seq = seq_for(count, chosen, aptitude)

    def fixed(n):
        value = seq.pop(0)
        assert value < n, f"injected roll {value} out of range {n}"
        return value

    monkeypatch.setattr(
        "xiuxian.birth.secrets.randbelow", fixed, raising=True
    )


def test_demo_worst_birth_reaches_foundation(tmp_path, monkeypatch):
    # Single metal root (no affinity with qingxiao's 木/火) + worst aptitude.
    fixed_birth(monkeypatch, 1, (ELEMENTS[0],), 1)
    from xiuxian.demo import campaign

    result = campaign(tmp_path / "worst.db")
    assert result["self"]["realm"] == "筑基"
    assert any(
        h["action"] == "submit_quest" and h["arguments"].get("quest") == "guardian"
        for h in result["history"]
    )


def test_demo_best_birth_reaches_foundation(tmp_path, monkeypatch):
    # Five roots (includes 木/火 affinity) + best aptitude.
    fixed_birth(monkeypatch, 5, tuple(ELEMENTS), 5)
    from xiuxian.demo import campaign

    result = campaign(tmp_path / "best.db")
    assert result["self"]["realm"] == "筑基"


def test_island_demo_worst_birth_reaches_foundation(tmp_path, monkeypatch):
    # 三灵根 without affinity overlap + worst aptitude (failed on main before the fix).
    fixed_birth(monkeypatch, 3, (ELEMENTS[1], ELEMENTS[3], ELEMENTS[4]), 1)
    from xiuxian.island_demo import campaign

    result = campaign(tmp_path / "island_worst.db")
    assert result["self"]["realm"] == "筑基"


def test_island_demo_best_birth_reaches_foundation(tmp_path, monkeypatch):
    fixed_birth(monkeypatch, 5, tuple(ELEMENTS), 5)
    from xiuxian.island_demo import campaign

    result = campaign(tmp_path / "island_best.db")
    assert result["self"]["realm"] == "筑基"


def test_injection_covers_birth_matrix():
    """PROTECTION: the injected sequences really map to the intended births."""
    import xiuxian.birth as birth

    cases = [(1, (ELEMENTS[0],), 1), (5, tuple(ELEMENTS), 5), (3, (ELEMENTS[1], ELEMENTS[2], ELEMENTS[4]), 1)]
    for count, chosen, apt in cases:
        seq = seq_for(count, chosen, apt)
        it = iter(seq)
        real = birth.secrets.randbelow
        birth.secrets.randbelow = lambda n: next(it)
        try:
            root = generate_root(BIRTH)
            got_apt = generate_aptitude(BIRTH)
        finally:
            birth.secrets.randbelow = real
        assert sorted(root["rootElements"]) == sorted(chosen)
        assert got_apt == apt
