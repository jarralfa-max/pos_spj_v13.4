"""PRC-8 — DROP diferido de tablas de precio legacy (env-guard + idempotencia)."""

import importlib
import sqlite3

import pytest

_mig = importlib.import_module("migrations.deferred.legacy_pricing_drop")

_LEGACY = ("listas_precio", "precios_lista", "precios_volumen",
           "clientes_lista_precio", "historial_precios")


def _legacy_db():
    c = sqlite3.connect(":memory:")
    for t in _LEGACY:
        c.execute(f"CREATE TABLE {t} (id TEXT)")
    c.commit()
    return c


def _tables(c):
    return {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def test_refuses_without_env_guard(monkeypatch):
    monkeypatch.delenv("PRICING_ALLOW_LEGACY_DROP", raising=False)
    c = _legacy_db()
    with pytest.raises(RuntimeError):
        _mig.run(c)
    assert _tables(c) == set(_LEGACY)  # nada eliminado
    c.close()


def test_drops_with_env_guard(monkeypatch):
    monkeypatch.setenv("PRICING_ALLOW_LEGACY_DROP", "1")
    c = _legacy_db()
    dropped = _mig.run(c)
    assert set(dropped) == set(_LEGACY)
    assert _tables(c) == set()
    c.close()


def test_idempotent_partial_schema(monkeypatch):
    monkeypatch.setenv("PRICING_ALLOW_LEGACY_DROP", "1")
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE precios_lista (id TEXT)")  # esquema parcial
    c.commit()
    _mig.run(c)  # DROP IF EXISTS no revienta con tablas faltantes
    assert "precios_lista" not in _tables(c)
    c.close()


def test_not_registered_in_engine():
    from migrations.engine import MIGRATIONS
    modules = {m.module for m in MIGRATIONS}
    assert "migrations.deferred.legacy_pricing_drop" not in modules
