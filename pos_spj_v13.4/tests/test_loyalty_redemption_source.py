# tests/test_loyalty_redemption_source.py — SPJ ERP v13.4
"""
Tests that verify:
1. LoyaltyService.preview_redemption() returns the correct dict structure.
2. LoyaltyService.get_customer_loyalty_summary() returns the full summary.
3. The UI should receive preview data from service (not hardcode it).
4. compute_redemption_discount stays consistent with preview.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pytest
from unittest.mock import MagicMock, patch


# ── Fixture ────────────────────────────────────────────────────────────────────

def _make_loyalty_service(saldo: int = 200, valor_estrella: float = 0.10,
                           min_puntos: int = 0, max_pct: float = 0.5):
    """Build LoyaltyService with an in-memory DB, mocked engine."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE loyalty_pasivo_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, tipo TEXT, estrellas INTEGER,
            valor_unitario REAL, monto_total REAL,
            referencia TEXT, sucursal_id INTEGER
        );
        CREATE TABLE loyalty_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER, tipo TEXT, puntos INTEGER,
            monto_equiv REAL, saldo_post INTEGER,
            referencia TEXT, descripcion TEXT,
            sucursal_id INTEGER, usuario TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE configuraciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT UNIQUE, valor TEXT
        );
    """)
    conn.execute(
        "INSERT INTO configuraciones(clave,valor) VALUES(?,?)",
        ("loyalty_valor_estrella", str(valor_estrella))
    )
    conn.execute(
        "INSERT INTO configuraciones(clave,valor) VALUES(?,?)",
        ("loyalty_min_puntos_canje", str(min_puntos))
    )
    conn.execute(
        "INSERT INTO configuraciones(clave,valor) VALUES(?,?)",
        ("loyalty_max_pct_canje", str(max_pct))
    )
    conn.commit()

    from core.services.loyalty_service import LoyaltyService
    svc = LoyaltyService.__new__(LoyaltyService)
    svc.db = conn
    svc.sucursal_id = 1
    svc._module_config = None
    svc._finance = None
    svc._bus = None

    # Mock engine with controllable saldo
    engine = MagicMock()
    engine.saldo_cliente.return_value = saldo
    svc._engine = engine

    return svc


class TestPreviewRedemption:
    """preview_redemption() must return all required keys with correct values."""

    REQUIRED_KEYS = {
        "enabled", "cliente_id", "puntos_disponibles", "valor_por_punto",
        "min_puntos_canje", "max_pct_canje", "puntos_maximos_canjeables",
        "descuento_maximo", "puntos_solicitados", "descuento",
        "total_original", "total_con_descuento", "nivel", "mensaje",
    }

    def test_returns_all_required_keys(self):
        svc = _make_loyalty_service(saldo=100, valor_estrella=0.10)
        result = svc.preview_redemption(cliente_id=1, subtotal=200.0)
        assert self.REQUIRED_KEYS.issubset(set(result.keys())), \
            f"Missing keys: {self.REQUIRED_KEYS - set(result.keys())}"

    def test_enabled_true_when_enabled(self):
        svc = _make_loyalty_service(saldo=100)
        result = svc.preview_redemption(cliente_id=1, subtotal=200.0)
        assert result["enabled"] is True

    def test_enabled_false_when_no_cliente(self):
        svc = _make_loyalty_service(saldo=100)
        result = svc.preview_redemption(cliente_id=0, subtotal=200.0)
        assert result["enabled"] is False

    def test_puntos_disponibles_matches_saldo(self):
        svc = _make_loyalty_service(saldo=150)
        result = svc.preview_redemption(cliente_id=1, subtotal=300.0)
        assert result["puntos_disponibles"] == 150

    def test_max_pct_cap_applied(self):
        """puntos_maximos_canjeables should be capped by max_pct_canje."""
        svc = _make_loyalty_service(saldo=1000, valor_estrella=0.10, max_pct=0.5)
        # subtotal=100 → max descuento = 50% = $50 → max pts = 500
        result = svc.preview_redemption(cliente_id=1, subtotal=100.0)
        assert result["puntos_maximos_canjeables"] == 500

    def test_descuento_max_consistent_with_pts_max(self):
        svc = _make_loyalty_service(saldo=1000, valor_estrella=0.10)
        result = svc.preview_redemption(cliente_id=1, subtotal=100.0)
        expected = result["puntos_maximos_canjeables"] * 0.10
        assert abs(result["descuento_maximo"] - expected) < 0.01

    def test_puntos_solicitados_custom(self):
        svc = _make_loyalty_service(saldo=200, valor_estrella=0.10)
        result = svc.preview_redemption(
            cliente_id=1, subtotal=200.0, puntos_solicitados=50
        )
        assert result["puntos_solicitados"] == 50
        assert abs(result["descuento"] - 5.0) < 0.01

    def test_total_con_descuento_correct(self):
        svc = _make_loyalty_service(saldo=100, valor_estrella=0.10)
        # Ask for 50 pts → descuento $5
        result = svc.preview_redemption(
            cliente_id=1, subtotal=100.0, puntos_solicitados=50
        )
        assert abs(result["total_con_descuento"] - (100.0 - result["descuento"])) < 0.01

    def test_min_puntos_not_met(self):
        """When saldo < min_puntos_canje, puntos_maximos_canjeables == 0."""
        svc = _make_loyalty_service(saldo=50, min_puntos=100)
        result = svc.preview_redemption(cliente_id=1, subtotal=200.0)
        assert result["puntos_maximos_canjeables"] == 0
        assert result["puntos_solicitados"] == 0
        assert result["descuento"] == 0.0

    def test_no_side_effects(self):
        """Calling preview_redemption must not write to loyalty_ledger."""
        svc = _make_loyalty_service(saldo=100)
        svc.preview_redemption(cliente_id=1, subtotal=200.0)
        rows = svc.db.execute("SELECT COUNT(*) FROM loyalty_ledger").fetchone()
        assert rows[0] == 0, "preview_redemption must not write to loyalty_ledger"

    def test_disabled_returns_empty_dict(self):
        svc = _make_loyalty_service(saldo=100)
        mc = MagicMock()
        mc.is_enabled.return_value = False
        svc._module_config = mc
        result = svc.preview_redemption(cliente_id=1, subtotal=200.0)
        assert result["enabled"] is False
        assert result["descuento"] == 0.0


class TestGetCustomerLoyaltySummary:
    """get_customer_loyalty_summary() returns saldo, nivel, ledger, preview."""

    def test_returns_expected_keys(self):
        svc = _make_loyalty_service(saldo=100)
        result = svc.get_customer_loyalty_summary(cliente_id=1, subtotal=200.0)
        for key in ("enabled", "cliente_id", "saldo", "nivel", "ledger", "preview"):
            assert key in result, f"Missing key: {key}"

    def test_saldo_matches(self):
        svc = _make_loyalty_service(saldo=75)
        result = svc.get_customer_loyalty_summary(cliente_id=1)
        assert result["saldo"] == 75

    def test_preview_none_when_no_subtotal(self):
        svc = _make_loyalty_service(saldo=100)
        result = svc.get_customer_loyalty_summary(cliente_id=1)
        assert result["preview"] is None

    def test_preview_populated_when_subtotal_given(self):
        svc = _make_loyalty_service(saldo=100)
        result = svc.get_customer_loyalty_summary(cliente_id=1, subtotal=200.0)
        assert result["preview"] is not None
        assert "descuento" in result["preview"]

    def test_empty_ledger_when_no_movements(self):
        svc = _make_loyalty_service(saldo=100)
        result = svc.get_customer_loyalty_summary(cliente_id=1)
        assert result["ledger"] == []


class TestPreviewVsComputeRedemptionConsistency:
    """compute_redemption_discount and preview_redemption must agree."""

    def test_descuento_matches_compute_redemption_discount(self):
        svc = _make_loyalty_service(saldo=500, valor_estrella=0.10, max_pct=0.5)
        pts = 100
        subtotal = 300.0
        preview = svc.preview_redemption(
            cliente_id=1, subtotal=subtotal, puntos_solicitados=pts
        )
        compute = svc.compute_redemption_discount(pts, subtotal)
        # Both should give the same discount for the same pts/subtotal
        assert abs(preview["descuento"] - compute) < 0.01, \
            f"preview says {preview['descuento']}, compute says {compute}"
