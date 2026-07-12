"""FinanceReadRepository usa fuentes canónicas y guards de existencia."""
from __future__ import annotations

from pathlib import Path

from backend.infrastructure.db.repositories.finance_read_repository import (
    FinanceReadRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

REPO_SRC = (
    Path(__file__).resolve().parents[2]
    / "backend" / "infrastructure" / "db" / "repositories" / "finance_read_repository.py"
)


def test_source_declares_canonical_tables():
    text = REPO_SRC.read_text(encoding="utf-8")
    for canonical in (
        "journal_entries",
        "financial_event_log",
        "cuentas_por_cobrar",
        "treasury_ledger",
        "ventas",
        "compras",
        "cierres_caja",
    ):
        assert canonical in text, f"fuente canónica ausente: {canonical}"
    assert "_table_exists" in text


def test_overdue_receivables_falls_back_to_cxc_when_no_financial_documents():
    conn = make_db()
    conn.execute("DROP TABLE IF EXISTS financial_documents")
    conn.execute(
        "INSERT INTO cuentas_por_cobrar (id, cliente_id, venta_id, monto_original, "
        " saldo_pendiente, estado) VALUES (?, ?, ?, 99.0, 99.0, 'pendiente')",
        (new_uuid(), new_uuid(), new_uuid()),
    )
    repo = FinanceReadRepository(conn)
    assert repo.count_overdue_receivables() == 1


def test_cash_discrepancy_uses_diferencia_not_total_vs_cash():
    """Un corte con tarjeta alta pero diferencia 0 NO es discrepancia."""
    conn = make_db()
    conn.execute(
        "INSERT INTO cierres_caja (id, total_ventas, total_efectivo, total_tarjeta, diferencia) "
        "VALUES (?, 1000.0, 200.0, 800.0, 0.0)",
        (new_uuid(),),
    )
    repo = FinanceReadRepository(conn)
    assert repo.count_cash_discrepancies() == 0
