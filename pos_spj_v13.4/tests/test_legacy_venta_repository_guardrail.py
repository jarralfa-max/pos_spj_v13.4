import os
import sqlite3

from repositories.ventas import VentaRepository


def _repo():
    db = sqlite3.connect(":memory:")
    return VentaRepository(db)


def test_venta_repository_create_sale_blocked_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_LEGACY_VENTA_REPOSITORY_WRITES", raising=False)
    repo = _repo()
    try:
        repo.create_sale({"branch_id": 1, "usuario": "u", "items": [{"producto_id": 1, "cantidad": 1, "precio_unitario": 10}]})
        assert False, "Expected RuntimeError guardrail"
    except RuntimeError as exc:
        assert "ALLOW_LEGACY_VENTA_REPOSITORY_WRITES=1" in str(exc)


def test_venta_repository_create_sale_allows_legacy_when_flag_enabled(monkeypatch):
    monkeypatch.setenv("ALLOW_LEGACY_VENTA_REPOSITORY_WRITES", "1")
    repo = _repo()
    assert os.getenv("ALLOW_LEGACY_VENTA_REPOSITORY_WRITES") == "1"
    # We only assert guard is bypassed; downstream schema may fail in this isolated test.
    try:
        repo.create_sale({"branch_id": 1, "usuario": "u", "items": [{"producto_id": 1, "cantidad": 1, "precio_unitario": 10}]})
    except Exception as exc:
        assert "bloqueado por seguridad" not in str(exc)
