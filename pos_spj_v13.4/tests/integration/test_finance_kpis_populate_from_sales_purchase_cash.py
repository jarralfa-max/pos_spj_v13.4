"""KPIs de Finanzas se pueblan desde las fuentes canónicas reales."""
from __future__ import annotations

from backend.infrastructure.db.repositories.finance_read_repository import (
    FinanceReadRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _seed(conn):
    conn.execute(
        "INSERT INTO ventas (id, folio, total, estado) VALUES (?, 'V-1', 500.0, 'completada')",
        (new_uuid(),),
    )
    conn.execute(
        "INSERT INTO ventas (id, folio, total, estado) VALUES (?, 'V-2', 300.0, 'cancelada')",
        (new_uuid(),),
    )
    conn.execute(
        "INSERT INTO compras (id, folio, total, usuario) VALUES (?, 'C-1', 200.0, 'tester')",
        (new_uuid(),),
    )
    conn.execute(
        "INSERT INTO cierres_caja (id, total_ventas, total_efectivo, diferencia) "
        "VALUES (?, 500.0, 480.0, -20.0)",
        (new_uuid(),),
    )
    conn.execute(
        "INSERT INTO cuentas_por_cobrar (id, cliente_id, venta_id, monto_original, "
        " saldo_pendiente, estado) VALUES (?, ?, ?, 150.0, 150.0, 'pendiente')",
        (new_uuid(), new_uuid(), new_uuid()),
    )


def test_kpis_from_canonical_sources():
    conn = make_db()
    _seed(conn)
    repo = FinanceReadRepository(conn)

    assert repo.sum_sales() == 500.0            # excluye canceladas
    assert repo.sum_purchases() == 200.0
    assert repo.count_cash_discrepancies() == 1  # usa columna diferencia
    assert repo.count_overdue_receivables() == 1  # fallback CxC canónica


def test_recent_activity_merges_sales_purchases_cash():
    conn = make_db()
    _seed(conn)
    repo = FinanceReadRepository(conn)
    feed = repo.get_recent_activity(limit=10)
    tipos = {f["tipo"] for f in feed}
    assert "Venta" in tipos and "Compra" in tipos and "Cierre caja" in tipos
    # Venta cancelada excluida del feed
    assert all(f["concepto"] != "V-2" for f in feed if f["tipo"] == "Venta")
