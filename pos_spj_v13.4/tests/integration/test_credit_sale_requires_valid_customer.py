"""Venta a crédito exige cliente válido con crédito autorizado y suficiente."""
from __future__ import annotations

import pytest

from application.services.customer_credit_service import CustomerCreditService
from backend.shared.ids import new_uuid
from core.services.sales_service import SalesService
from tests.integration._born_clean_db import make_db


def _customer(conn, *, allows=1, limit=1000.0, balance=0.0, activo=1) -> str:
    cid = new_uuid()
    conn.execute(
        "INSERT INTO clientes (id, nombre, activo, allows_credit, credit_limit, credit_balance) "
        "VALUES (?, 'Cliente', ?, ?, ?, ?)",
        (cid, activo, allows, limit, balance),
    )
    return cid


def _sales_service(conn) -> SalesService:
    svc = object.__new__(SalesService)   # sin ejecutar __init__ pesado
    svc.db = conn
    svc.customer_service = CustomerCreditService(conn)
    return svc


def test_credit_sale_without_customer_fails():
    conn = make_db()
    svc = _sales_service(conn)
    with pytest.raises(ValueError, match="cliente con crédito autorizado"):
        svc._validate_payment("Crédito", 100.0, {"credito": 100.0}, client_id=None)


def test_credit_sale_without_credit_service_fails():
    conn = make_db()
    svc = _sales_service(conn)
    svc.customer_service = None
    cid = _customer(conn)
    with pytest.raises(ValueError, match="crédito"):
        svc._validate_payment("Crédito", 100.0, {"credito": 100.0}, client_id=cid)


def test_credit_sale_nonexistent_customer_fails():
    conn = make_db()
    svc = _sales_service(conn)
    with pytest.raises(ValueError, match="no encontrado o inactivo"):
        svc._validate_payment("Crédito", 100.0, {"credito": 100.0}, client_id=new_uuid())


def test_credit_sale_inactive_customer_fails():
    conn = make_db()
    svc = _sales_service(conn)
    cid = _customer(conn, activo=0)
    with pytest.raises(ValueError, match="no encontrado o inactivo"):
        svc._validate_payment("Crédito", 100.0, {"credito": 100.0}, client_id=cid)


def test_credit_sale_customer_without_authorization_fails():
    conn = make_db()
    svc = _sales_service(conn)
    cid = _customer(conn, allows=0)
    with pytest.raises(ValueError, match="no tiene crédito autorizado"):
        svc._validate_payment("Crédito", 100.0, {"credito": 100.0}, client_id=cid)


def test_credit_sale_customer_with_zero_limit_fails():
    conn = make_db()
    svc = _sales_service(conn)
    cid = _customer(conn, allows=1, limit=0.0)
    with pytest.raises(ValueError, match="límite de crédito"):
        svc._validate_payment("Crédito", 100.0, {"credito": 100.0}, client_id=cid)


def test_credit_sale_insufficient_credit_fails():
    conn = make_db()
    svc = _sales_service(conn)
    cid = _customer(conn, allows=1, limit=100.0, balance=50.0)
    with pytest.raises(ValueError, match="Crédito insuficiente"):
        svc._validate_payment("Crédito", 100.0, {"credito": 100.0}, client_id=cid)


def test_credit_sale_valid_customer_passes():
    conn = make_db()
    svc = _sales_service(conn)
    cid = _customer(conn, allows=1, limit=500.0, balance=0.0)
    # No debe lanzar
    svc._validate_payment("Crédito", 100.0, {"credito": 100.0}, client_id=cid)
