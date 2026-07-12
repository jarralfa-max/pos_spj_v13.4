"""Finanzas no se rompe cuando faltan tablas opcionales: devuelve 0/listas vacías."""
from __future__ import annotations

import sqlite3

from backend.infrastructure.db.repositories.finance_read_repository import (
    FinanceReadRepository,
)


def test_all_reads_survive_empty_database():
    conn = sqlite3.connect(":memory:")   # sin NINGUNA tabla
    repo = FinanceReadRepository(conn)

    assert repo.count_overdue_payables() == 0
    assert repo.count_overdue_receivables() == 0
    assert repo.count_cash_discrepancies() == 0
    assert repo.sum_sales() == 0.0
    assert repo.sum_purchases() == 0.0
    assert repo.expenses_by_module() == []
    assert repo.list_cash_closures() == []
    assert repo.list_capital_movements() == []
    assert repo.list_treasury_capital() == []
    assert repo.list_treasury_ledger() == []
    assert repo.list_journal_entries() == []
    assert repo.list_financial_event_log() == []
    assert repo.list_active_suppliers() == []
    assert repo.list_customer_credit() == []
    assert repo.get_recent_activity() == []
