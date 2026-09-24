"""Contexto de compra REAL para las pruebas de la compra rápida.

Las pruebas de la compra rápida usaban un producto inventado (`p1`) que no
existía en ningún catálogo, un almacén (`wh-1`) que no existía, y pagaban de
caja chica sin ninguna contabilidad configurada — y pasaban, porque la compra se
confirmaba sin comprobar nada de eso. Eran exactamente los defectos medidos el
2026-09-18 (producto no activo, almacén de otra sucursal, pago sin asiento),
fijados como contrato.

Esto siembra lo mínimo que una instalación real tiene:
* productos ACTIVOS y comprables (las columnas que lee
  `ProcurementProductCatalogAdapter.resolve`);
* un almacén de la sucursal que admite recepción de compras (lo que lee
  `WarehouseDirectoryQueryService`);
* Finanzas con `bootstrap_finance`, que siembra lo mismo que la base real:
  Caja general, Banco, Procesador de pagos y los perfiles contables. NO hay caja
  chica, igual que en la base real.
"""

from __future__ import annotations

from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.infrastructure.db.schema.finance_schema import create_finance_schema


def seed_purchase_context(conn, *, branch_id: str = "br-1", warehouse_id: str = "wh-1",
                          products=(("p1", "Pollo"), ("p2", "Caja"))) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, code TEXT, name TEXT,"
        " base_unit_id TEXT, purchasable INTEGER NOT NULL DEFAULT 1,"
        " lifecycle_status TEXT NOT NULL DEFAULT 'ACTIVE')")
    for product_id, name in products:
        conn.execute("INSERT OR IGNORE INTO products (id, code, name, base_unit_id)"
                     " VALUES (?,?,?,'PZA')", (product_id, product_id.upper(), name))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS warehouses (id TEXT PRIMARY KEY, code TEXT, name TEXT,"
        " branch_id TEXT, status TEXT NOT NULL DEFAULT 'ACTIVE',"
        " allow_purchase_receipt INTEGER NOT NULL DEFAULT 1)")
    conn.execute("INSERT OR IGNORE INTO warehouses (id, code, name, branch_id)"
                 " VALUES (?, 'ALM', 'Almacén', ?)", (warehouse_id, branch_id))
    create_finance_schema(conn)
    bootstrap_finance(conn)
    conn.commit()
