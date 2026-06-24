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
