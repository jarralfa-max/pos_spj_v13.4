"""CRM-27 — Finance/Crédito cutover hacia Customer Master, parte 1.

Cubre:
1. Migración 196: backfilla `customer_credit_profiles` AUTHORIZED desde
   `clientes.allows_credit/credit_limit` para clientes legacy ya
   habilitados, bridgeados vía `customers.legacy_customer_id` (CRM-21).
2. `CustomerCreditService.get_customer()`/`validate_credit()` prefieren ese
   perfil cuando existe (el workflow moderno CRM-8 ahora tiene efecto real
   en el gate de checkout — antes estaba desconectado).
3. Fallback a las columnas legacy de `clientes` cuando no hay perfil
   bridgeado (cliente nuevo aún no backfillado, o un `customer_credit_
   profiles` inexistente) — nunca una dependencia dura.
"""
from __future__ import annotations

import sqlite3

import pytest

from application.services.customer_credit_service import CustomerCreditService
from backend.shared.ids import new_uuid


def _full_db() -> sqlite3.Connection:
    from migrations import engine

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    engine.up(conn)
    return conn


def _run_196(conn) -> None:
    import importlib

    module = importlib.import_module("migrations.standalone.196_customer_credit_profile_backfill")
    module.run(conn)


def _legacy_customer(conn, *, allows=1, limit=1000.0, activo=1) -> str:
    cid = new_uuid()
    conn.execute(
        "INSERT INTO clientes (id, nombre, activo, allows_credit, credit_limit, credit_balance)"
        " VALUES (?, 'Cliente CRM-27', ?, ?, ?, 0)",
        (cid, activo, allows, limit),
    )
    conn.commit()
    return cid


class TestMigration196Backfill:
    def test_migration_runs_via_engine_and_backfills(self):
        conn = _full_db()
        cid = _legacy_customer(conn, allows=1, limit=5000.0)

        _run_196(conn)

        bridged = conn.execute(
            "SELECT id FROM customers WHERE legacy_customer_id=?", (cid,)
        ).fetchone()
        assert bridged is not None, "clientes row debe quedar bridgeado a customers"

        profile = conn.execute(
            "SELECT status, credit_limit FROM customer_credit_profiles WHERE customer_id=?",
            (bridged[0],),
        ).fetchone()
        assert profile is not None, "debe crearse un customer_credit_profiles AUTHORIZED"
        assert profile[0] == "AUTHORIZED"
        assert float(profile[1]) == 5000.0

    def test_does_not_backfill_customer_without_credit(self):
        conn = _full_db()
        cid = _legacy_customer(conn, allows=0, limit=0.0)

        _run_196(conn)

        bridged = conn.execute(
            "SELECT id FROM customers WHERE legacy_customer_id=?", (cid,)
        ).fetchone()
        assert bridged is not None
        profile = conn.execute(
            "SELECT 1 FROM customer_credit_profiles WHERE customer_id=?", (bridged[0],),
        ).fetchone()
        assert profile is None, "sin allows_credit/limit no debe crearse perfil"

    def test_idempotent_on_rerun(self):
        conn = _full_db()
        cid = _legacy_customer(conn, allows=1, limit=2000.0)

        _run_196(conn)
        _run_196(conn)  # segunda corrida no debe duplicar

        bridged = conn.execute(
            "SELECT id FROM customers WHERE legacy_customer_id=?", (cid,)
        ).fetchone()[0]
        count = conn.execute(
            "SELECT COUNT(*) FROM customer_credit_profiles WHERE customer_id=?", (bridged,),
        ).fetchone()[0]
        assert count == 1

    def test_does_not_overwrite_existing_profile(self):
        """Si el workflow moderno ya tomó una decisión (p.ej. SUSPENDED), la
        migración nunca debe pisarla."""
        conn = _full_db()
        cid = _legacy_customer(conn, allows=1, limit=3000.0)

        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            ResolveLegacyCustomerUseCase,
        )
        from backend.domain.customer_credit.entities.customer_credit_profile import (
            CustomerCreditProfile,
        )
        from backend.infrastructure.db.repositories.customer_credit.unit_of_work import (
            CustomerCreditUnitOfWork,
        )
        from decimal import Decimal

        customer_id = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id=cid)
        profile = CustomerCreditProfile.request(customer_id, "tester", requested_limit=Decimal("1"))
        profile.review()
        profile.approve("tester", credit_limit=Decimal("1"))
        profile.suspend("prueba")
        with CustomerCreditUnitOfWork(conn) as uow:
            uow.profiles.save(profile, operation_id="manual-test-op")

        _run_196(conn)

        row = conn.execute(
            "SELECT status FROM customer_credit_profiles WHERE customer_id=?", (customer_id,)
        ).fetchone()
        assert row[0] == "SUSPENDED", "la migración no debe pisar una decisión ya tomada"


class TestCustomerCreditServicePrefersProfile:
    def test_uses_profile_limit_over_legacy_column(self):
        """Backfill crea perfil con límite 5000; si luego alguien cambia el
        límite legacy sin tocar el perfil, el gate debe seguir el perfil
        (fuente de verdad = Customer Master), no la columna legacy."""
        conn = _full_db()
        cid = _legacy_customer(conn, allows=1, limit=5000.0)
        _run_196(conn)

        # Drift deliberado: la columna legacy queda desactualizada.
        conn.execute("UPDATE clientes SET credit_limit=1.0 WHERE id=?", (cid,))
        conn.commit()

        svc = CustomerCreditService(conn)
        customer = svc.get_customer(cid)
        assert customer["allows_credit"] is True
        assert customer["credit_limit"] == 5000.0, (
            "debe leer el límite del customer_credit_profiles bridgeado, no el legacy")

    def test_suspended_profile_blocks_credit_even_if_legacy_allows(self):
        conn = _full_db()
        cid = _legacy_customer(conn, allows=1, limit=1000.0)
        _run_196(conn)

        from backend.infrastructure.db.repositories.customer_credit.unit_of_work import (
            CustomerCreditUnitOfWork,
        )
        with CustomerCreditUnitOfWork(conn) as uow:
            profile = uow.profiles.get_by_customer_id(
                conn.execute(
                    "SELECT id FROM customers WHERE legacy_customer_id=?", (cid,)
                ).fetchone()[0]
            )
            profile.suspend("mora")
            uow.profiles.update(profile)

        ok, msg = CustomerCreditService(conn).validate_credit(cid, 100.0)
        assert ok is False
        assert "crédito autorizado" in msg

    def test_falls_back_to_legacy_when_no_profile_bridged(self):
        """Cliente nuevo, migración 196 nunca corrida para él (o bridge no
        existe todavía): el gate debe seguir funcionando con las columnas
        legacy — nunca debe bloquear por la sola ausencia del perfil."""
        conn = _full_db()
        cid = _legacy_customer(conn, allows=1, limit=800.0)
        # Deliberadamente NO se corre la migración 196 / no hay bridge.

        ok, msg = CustomerCreditService(conn).validate_credit(cid, 500.0)
        assert ok is True, f"debe aprobar con datos legacy si no hay perfil bridgeado: {msg}"

    def test_falls_back_on_isolated_schema_without_customer_master_tables(self):
        """Mismo esquema ad-hoc que tests/test_credit_sale_cxc.py — sin
        tablas customers/customer_credit_profiles en absoluto."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE clientes (
                id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER DEFAULT 1,
                allows_credit INTEGER DEFAULT 0, credit_limit REAL DEFAULT 0,
                credit_balance REAL DEFAULT 0, puntos INTEGER DEFAULT 0
            );
            CREATE TABLE cuentas_por_cobrar (
                id TEXT PRIMARY KEY, cliente_id TEXT NOT NULL, venta_id TEXT,
                folio TEXT, monto_original REAL, saldo_pendiente REAL,
                estado TEXT DEFAULT 'pendiente', sucursal_id TEXT, fecha DATETIME
            );
            """
        )
        cid = new_uuid()
        conn.execute(
            "INSERT INTO clientes (id, nombre, activo, allows_credit, credit_limit)"
            " VALUES (?, 'Cliente', 1, 1, 500)", (cid,))
        conn.commit()

        ok, msg = CustomerCreditService(conn).validate_credit(cid, 200.0)
        assert ok is True, f"debe funcionar sin ninguna tabla de Customer Master: {msg}"
