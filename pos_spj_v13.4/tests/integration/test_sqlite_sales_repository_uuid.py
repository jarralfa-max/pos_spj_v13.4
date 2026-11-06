"""Las ventas nacen con identidad UUIDv7 (REGLA CERO), sin `lastrowid`.

SDLC-CORE-007: este archivo importaba `infrastructure.persistence.sqlite_sales_repository`,
borrado en `a35b8bab`, y abortaba la colección de todo `tests/integration`. Mismo
contrato, sobre el agregado canónico que sustituyó a ese repositorio: venta y línea
con UUIDv7 propios, distintos entre sí y del `operation_id`, sin conversión a entero.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import is_uuidv7, new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    c.commit()
    yield c
    c.close()


def _venta(conn):
    auth = SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())
    sucursal, cajero, operacion = new_uuid(), new_uuid(), new_uuid()
    sale_id = StartSaleUseCase(auth).execute(
        conn, branch_id=sucursal, cashier_user_id=cajero, operation_id=operacion,
        actor_user_id=cajero).entity_id
    return auth, sale_id, sucursal, cajero, operacion


def test_a_sale_is_born_with_its_own_uuidv7(conn):
    _auth, sale_id, sucursal, _cajero, operacion = _venta(conn)

    assert is_uuidv7(sale_id)
    assert sale_id != operacion                 # entity_id != operation_id (regla 41)
    venta = SaleRepository(conn).get(sale_id)
    assert venta is not None and venta.id == sale_id
    assert venta.branch_id == sucursal          # la sucursal viaja como UUID, sin cast


def test_each_line_gets_its_own_uuidv7(conn):
    auth, sale_id, _sucursal, cajero, _operacion = _venta(conn)
    for _ in range(2):
        AddSaleLineUseCase(auth).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("10.00"), actor_user_id=cajero, operation_id=new_uuid())

    lineas = SaleRepository(conn).get(sale_id).lines

    identidades = {linea.id for linea in lineas}
    assert len(identidades) == 2 and sale_id not in identidades
    assert all(is_uuidv7(identidad) for identidad in identidades)
