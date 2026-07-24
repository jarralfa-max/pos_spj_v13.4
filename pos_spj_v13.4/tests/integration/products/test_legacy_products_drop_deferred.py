"""PROD-19 — DROP diferido de legacy de Productos: env-guard + no registrado."""

import importlib
import sqlite3

import pytest

_drop = importlib.import_module("migrations.deferred.legacy_products_drop")


def _seed_legacy(c):
    for t in ("productos", "recetas", "rendimiento_pollo", "branch_products",
              "cortes_caja_erp"):
        c.execute(f"CREATE TABLE {t} (id TEXT)")
    c.commit()


def test_refuses_without_env_guard(monkeypatch):
    monkeypatch.delenv("PRODUCTS_ALLOW_LEGACY_DROP", raising=False)
    c = sqlite3.connect(":memory:")
    _seed_legacy(c)
    with pytest.raises(RuntimeError):
        _drop.run(c)
    # nada se elimina
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='productos'").fetchone()
    c.close()


def test_drops_with_env_guard(monkeypatch):
    monkeypatch.setenv("PRODUCTS_ALLOW_LEGACY_DROP", "1")
    c = sqlite3.connect(":memory:")
    _seed_legacy(c)
    dropped = _drop.run(c)
    assert "productos" in dropped and "recetas" in dropped
    remaining = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "productos" not in remaining and "rendimiento_pollo" not in remaining
    c.close()


def test_not_registered_in_engine():
    from migrations import engine
    names = [m.module for m in engine.MIGRATIONS] if hasattr(engine, "MIGRATIONS") else []
    src = "\n".join(names)
    assert "legacy_products_drop" not in src


def test_idempotent_drop(monkeypatch):
    monkeypatch.setenv("PRODUCTS_ALLOW_LEGACY_DROP", "1")
    c = sqlite3.connect(":memory:")
    _seed_legacy(c)
    _drop.run(c)
    _drop.run(c)  # segunda vez: DROP IF EXISTS, sin error
    c.close()
