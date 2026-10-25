"""Shared fixtures for finance bounded-context integration tests."""

import sqlite3
from datetime import date

import pytest

from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.infrastructure.db.schema.finance_schema import create_finance_schema


@pytest.fixture
def finance_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_finance_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def bootstrapped_conn(finance_conn):
    bootstrap_finance(finance_conn, today=date(2026, 7, 16))
    return finance_conn


def register_supplier(conn, *, active: int = 1, blocked: int = 0,
                      bank_account: str = "012180001234567897") -> str:
    """Proveedor en el maestro canónico (``proveedores``): Finanzas valida al
    beneficiario contra él antes de programar o ejecutar un pago (F13)."""
    from backend.shared.ids import new_uuid

    conn.execute(
        "CREATE TABLE IF NOT EXISTS proveedores (id TEXT PRIMARY KEY, nombre TEXT NOT NULL,"
        " activo INTEGER DEFAULT 1, bloqueado_financiero INTEGER DEFAULT 0,"
        " motivo_bloqueo TEXT, cuenta_bancaria TEXT)")
    supplier_id = new_uuid()
    conn.execute(
        "INSERT INTO proveedores (id, nombre, activo, bloqueado_financiero, cuenta_bancaria)"
        " VALUES (?,?,?,?,?)", (supplier_id, "Proveedor de prueba", active, blocked,
                                bank_account))
    conn.commit()
    return supplier_id


def register_customer(conn, name: str = "Cliente de prueba") -> str:
    """Cliente en el maestro canónico (``customers``): Finanzas sólo lee su
    nombre visible para las pantallas de cobranza."""
    from backend.shared.ids import new_uuid

    conn.execute("CREATE TABLE IF NOT EXISTS customers (id TEXT PRIMARY KEY,"
                 " display_name TEXT NOT NULL)")
    customer_id = new_uuid()
    conn.execute("INSERT INTO customers (id, display_name) VALUES (?,?)", (customer_id, name))
    conn.commit()
    return customer_id


def account_id(conn, code: str) -> str:
    return conn.execute("SELECT id FROM accounts WHERE code=?", (code,)).fetchone()[0]


def treasury(conn, account_type):
    """Cuenta de tesorería sembrada de un tipo (``TreasuryAccountType``)."""
    from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
    with FinanceUnitOfWork(conn) as uow:
        return next(a for a in uow.treasury.list_active() if a.account_type is account_type)


def fund(conn, treasury_account_id: str, amount: str, on: date = date(2026, 7, 1)) -> str:
    """Aportación de capital: las salidas de tesorería exigen saldo (§13)."""
    from backend.application.use_cases.finance.register_capital_movement_use_case import (
        RegisterCapitalMovementUseCase,
    )
    from backend.domain.finance.enums import CapitalMovementKind
    from backend.shared.ids import new_uuid
    return RegisterCapitalMovementUseCase().execute(
        conn, kind=CapitalMovementKind.CONTRIBUTION, amount=amount, movement_date=on,
        treasury_account_id=treasury_account_id, counterparty="Socio de prueba",
        operation_id=new_uuid(), created_by="tester")


def approved_budget(conn, *, account_code="6130", planned="10000.00", period="2026-07",
                    year=2026, blocking=True):
    from backend.application.use_cases.finance.approve_budget_use_case import (
        BudgetWorkflowUseCase,
    )
    from backend.application.use_cases.finance.create_budget_use_case import CreateBudgetUseCase
    from backend.shared.ids import new_uuid
    budget = CreateBudgetUseCase().execute(
        conn, name=f"OPEX {new_uuid()[-6:]}", fiscal_year=year, blocking=blocking,
        lines=[{"account_id": account_id(conn, account_code), "period_code": period,
                "planned_amount": planned}], operation_id=new_uuid())
    workflow = BudgetWorkflowUseCase()
    workflow.submit(conn, budget_id=budget.id, submitted_by="ana", operation_id=new_uuid())
    workflow.approve(conn, budget_id=budget.id, approved_by="beto", operation_id=new_uuid())
    return budget
