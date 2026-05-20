# tests/test_payment_method_normalization.py — SPJ ERP v13.4
"""
Tests for core/services/payment_normalization.py.

Verifies that all known UI variants (with/without accents, mixed case,
aliases) map to the correct canonical backend value.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from core.services.payment_normalization import normalize_payment_method, is_credit_sale, CREDIT_PAYMENT_METHODS


class TestNormalizePaymentMethod:
    """Covers each variant listed in the _MAP table."""

    # ── Efectivo ──────────────────────────────────────────────────────────────

    def test_efectivo_exact(self):
        assert normalize_payment_method("Efectivo") == "Efectivo"

    def test_efectivo_lower(self):
        assert normalize_payment_method("efectivo") == "Efectivo"

    # ── Tarjeta ───────────────────────────────────────────────────────────────

    def test_tarjeta_exact(self):
        assert normalize_payment_method("Tarjeta") == "Tarjeta"

    def test_tarjeta_lower(self):
        assert normalize_payment_method("tarjeta") == "Tarjeta"

    # ── Transferencia ─────────────────────────────────────────────────────────

    def test_transferencia_exact(self):
        assert normalize_payment_method("Transferencia") == "Transferencia"

    def test_transferencia_lower(self):
        assert normalize_payment_method("transferencia") == "Transferencia"

    def test_spei_alias(self):
        assert normalize_payment_method("spei") == "Transferencia"

    # ── Crédito (the critical one — accent vs no accent) ─────────────────────

    def test_credito_with_accent(self):
        """UI sends 'Crédito' (with accent) — backend expects 'Credito'."""
        assert normalize_payment_method("Crédito") == "Credito"

    def test_credito_without_accent(self):
        assert normalize_payment_method("Credito") == "Credito"

    def test_credito_lower_with_accent(self):
        assert normalize_payment_method("crédito") == "Credito"

    def test_credito_lower_without_accent(self):
        assert normalize_payment_method("credito") == "Credito"

    # ── Pago Mixto ────────────────────────────────────────────────────────────

    def test_pago_mixto_exact(self):
        assert normalize_payment_method("Pago Mixto") == "Pago Mixto"

    def test_pago_mixto_lower(self):
        assert normalize_payment_method("pago mixto") == "Pago Mixto"

    def test_mixto_alias(self):
        assert normalize_payment_method("mixto") == "Pago Mixto"

    # ── Mercado Pago ──────────────────────────────────────────────────────────

    def test_mercado_pago_exact(self):
        assert normalize_payment_method("Mercado Pago") == "Mercado Pago"

    def test_mercado_pago_lower(self):
        assert normalize_payment_method("mercado pago") == "Mercado Pago"

    def test_mercadopago_camelcase(self):
        assert normalize_payment_method("MercadoPago") == "Mercado Pago"

    def test_mercadopago_lower_nospace(self):
        assert normalize_payment_method("mercadopago") == "Mercado Pago"

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_unknown_value_passthrough(self):
        """Unknown values pass through unchanged — conservative."""
        assert normalize_payment_method("Bitcoin") == "Bitcoin"

    def test_empty_string_returns_efectivo(self):
        assert normalize_payment_method("") == "Efectivo"

    def test_none_returns_efectivo(self):
        assert normalize_payment_method(None) == "Efectivo"

    def test_leading_trailing_spaces(self):
        assert normalize_payment_method("  Crédito  ") == "Credito"


class TestIsCreditSale:
    """Verifies is_credit_sale() handles all spelling variants."""

    def test_credito_with_accent_is_credit(self):
        assert is_credit_sale("Crédito") is True

    def test_credito_without_accent_is_credit(self):
        assert is_credit_sale("Credito") is True

    def test_credito_lower_accent_is_credit(self):
        assert is_credit_sale("crédito") is True

    def test_efectivo_not_credit(self):
        assert is_credit_sale("Efectivo") is False

    def test_tarjeta_not_credit(self):
        assert is_credit_sale("Tarjeta") is False

    def test_mercado_pago_not_credit(self):
        assert is_credit_sale("Mercado Pago") is False


class TestCreditPaymentMethodsSet:
    """The frozenset includes all accent variants for fast membership testing."""

    def test_accent_in_set(self):
        assert "Crédito" in CREDIT_PAYMENT_METHODS

    def test_no_accent_in_set(self):
        assert "Credito" in CREDIT_PAYMENT_METHODS
