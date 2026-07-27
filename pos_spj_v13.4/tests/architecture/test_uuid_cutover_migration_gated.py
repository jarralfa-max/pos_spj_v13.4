"""Migration 200 (UUID cutover) must stay gated: never auto-run, refuse without
explicit confirmation and a complete spec."""

from __future__ import annotations

import importlib

import pytest


def _mod():
    return importlib.import_module("migrations.standalone.200_uuid_identity_cutover")


def test_200_is_not_registered_in_engine():
    import migrations.engine as engine
    versions = {v for v, _ in engine.MIGRATIONS}
    assert "200" not in versions, "the destructive UUID cutover must not auto-run"


def test_200_refuses_without_confirmation(monkeypatch):
    monkeypatch.delenv("SPJ_UUID_CUTOVER_CONFIRMED", raising=False)
    with pytest.raises(RuntimeError, match="gated"):
        _mod().run(object())


def test_200_refuses_when_spec_incomplete(monkeypatch):
    monkeypatch.setenv("SPJ_UUID_CUTOVER_CONFIRMED", "1")
    mod = _mod()
    assert mod.SPEC_IS_COMPLETE is False
    with pytest.raises(RuntimeError, match="incompleto"):
        mod.run(object())


def test_generated_spec_is_referentially_closed():
    """Every FK parent referenced in CUTOVER_SPECS must itself be a spec'd table —
    a parent typo/miss would corrupt the cut."""
    mod = _mod()
    names = {s.name for s in mod.CUTOVER_SPECS}
    dangling = {
        f"{s.name}.{col} -> {parent}"
        for s in mod.CUTOVER_SPECS
        for col, parent in s.fks.items()
        if parent not in names
    }
    assert not dangling, f"FK parents not in spec set: {sorted(dangling)}"


def test_generated_spec_has_no_duplicate_tables():
    mod = _mod()
    names = [s.name for s in mod.CUTOVER_SPECS]
    assert len(names) == len(set(names))
