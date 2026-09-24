"""Contado/crédito y forma de pago preferida — dominio, persistencia, migración.

Las formas de pago válidas son una decisión del negocio (Transferencia SPEI y
Efectivo, 2026-09-17), no algo deducible del código: antes de esto no existía
ningún enum de formas de pago en todo `backend`.
"""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.domain.suppliers.enums import PaymentMethod
from backend.domain.suppliers.exceptions import InvalidCommercialTermsError
from backend.domain.suppliers.value_objects import Money, PaymentTerms
from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema

_migracion = importlib.import_module(
    "migrations.standalone.262_supplier_payment_terms_mode")


# ── dominio ─────────────────────────────────────────────────────────────────
def test_sin_bandera_se_deriva_de_los_dias_de_credito():
    """Compatibilidad: las condiciones capturadas antes de la bandera siguen
    siendo válidas sin reescribirlas."""
    assert PaymentTerms(credit_days=30).is_credit is True
    assert PaymentTerms(credit_days=0).is_credit is False


def test_credito_sin_dias_es_incoherente():
    with pytest.raises(InvalidCommercialTermsError):
        PaymentTerms(is_credit=True, credit_days=0)


def test_contado_con_dias_de_credito_es_incoherente():
    with pytest.raises(InvalidCommercialTermsError):
        PaymentTerms(is_credit=False, credit_days=15)


def test_la_forma_de_pago_llega_como_enum():
    assert PaymentTerms(preferred_payment_method="TRANSFER").preferred_payment_method \
        is PaymentMethod.TRANSFER


def test_solo_se_aceptan_las_formas_de_pago_del_negocio():
    """Cheque y domiciliación se descartaron a propósito."""
    assert {m.value for m in PaymentMethod} == {"TRANSFER", "CASH"}
    with pytest.raises(InvalidCommercialTermsError):
        PaymentTerms(preferred_payment_method="CHEQUE")


# ── persistencia ────────────────────────────────────────────────────────────
@pytest.fixture
def presenter():
    from frontend.desktop.modules.finance.suppliers.supplier_routes import (
        build_supplier_presenter,
    )

    class _Session:
        is_active = True
        user_id = "user-1"
        active_branch_id = "branch-1"

        def tiene_permiso(self, code):
            return code.startswith("PROVEEDORES.")

    conn = sqlite3.connect(":memory:")
    create_supplier_schema(conn)
    yield build_supplier_presenter(conn, _Session())
    conn.close()


def _proveedor(presenter):
    ok, msg, _ = presenter.create_supplier(
        legal_name="Distribuidora del Valle SA de CV", tax_identifier="DVA010203XY1",
        trade_name="Del Valle")
    assert ok, msg
    return presenter.suppliers().row_ids[0]


def test_las_condiciones_se_guardan_y_se_vuelven_a_ver(presenter):
    """Antes la pestaña Condiciones mostraba un texto FIJO: se guardaban y no
    se veían nunca."""
    sid = _proveedor(presenter)
    ok, msg, _ = presenter.update_terms(
        supplier_id=sid, is_credit=True, credit_days=30, credit_limit="50000",
        preferred_payment_method="TRANSFER")
    assert ok, msg

    resumen = presenter.terms_summary(sid)
    assert "Crédito — 30 días" in resumen
    assert "Transferencia (SPEI)" in resumen


def test_contado_en_efectivo(presenter):
    sid = _proveedor(presenter)
    ok, msg, _ = presenter.update_terms(
        supplier_id=sid, is_credit=False, credit_days=0,
        preferred_payment_method="CASH")
    assert ok, msg

    resumen = presenter.terms_summary(sid)
    assert "Tipo de pago: Contado" in resumen
    assert "Efectivo" in resumen


def test_sin_condiciones_lo_dice(presenter):
    assert presenter.terms_summary(_proveedor(presenter)) == "Sin condiciones registradas."


# ── migración 262 ───────────────────────────────────────────────────────────
def _tabla_antigua(conn):
    conn.execute(
        "CREATE TABLE supplier_commercial_terms (id TEXT PRIMARY KEY, supplier_id TEXT,"
        " currency_code TEXT NOT NULL DEFAULT 'MXN', credit_days INTEGER NOT NULL DEFAULT 0)")
    conn.execute("INSERT INTO supplier_commercial_terms (id, supplier_id, credit_days)"
                 " VALUES ('t1','s1',30), ('t2','s2',0)")
    conn.commit()


def test_la_migracion_rellena_credito_donde_el_dato_ya_lo_decia():
    """Sin el relleno, una condición con `credit_days=30` se leería como
    "contado con días de crédito", que el dominio rechaza: la ficha de ese
    proveedor dejaría de abrir."""
    conn = sqlite3.connect(":memory:")
    _tabla_antigua(conn)

    _migracion.run(conn)
    _migracion.run(conn)  # idempotente

    filas = dict(conn.execute(
        "SELECT supplier_id, is_credit FROM supplier_commercial_terms").fetchall())
    assert filas == {"s1": 1, "s2": 0}
    assert conn.execute(
        "SELECT preferred_payment_method FROM supplier_commercial_terms"
        " WHERE supplier_id='s1'").fetchone()[0] is None


def test_una_instalacion_nueva_ya_trae_las_columnas():
    conn = sqlite3.connect(":memory:")
    create_supplier_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(supplier_commercial_terms)")}
    assert {"is_credit", "preferred_payment_method"} <= cols
    _migracion.run(conn)  # no-op, no revienta


def test_sin_tabla_no_revienta():
    _migracion.run(sqlite3.connect(":memory:"))
