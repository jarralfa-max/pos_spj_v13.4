"""Auditoría externa de Clientes/CRM sobre d9f2bca (2026-10-09) — hallazgos de crédito.

* F01 (P0): la cuenta por cobrar de un cobro a crédito se confirmaba aunque la
  venta fallara después.
* F02 (P0): la deuda histórica se consultaba con el id canónico y daba 0.
* F23: el vencimiento se recalculaba con el plazo ACTUAL del perfil, y la
  elegibilidad daba por verificadas documentación y sucursal.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.shared.ids import new_uuid
from tests.integration.crm43.conftest import branch_id, new_customer, presenter_for


def _authorized(conn, customer, *, limit="1000", terms=15):
    conn.execute(
        "INSERT INTO customer_credit_profiles (id, customer_id, status, credit_limit,"
        " payment_terms_days, risk_level, version, created_at, updated_at)"
        " VALUES (?,?,'AUTHORIZED',?,?,'MEDIUM',1,'2026-01-01','2026-01-01')",
        (new_uuid(), customer, limit, terms))
    conn.commit()


def _receivables(conn, customer):
    return conn.execute("SELECT outstanding_amount, due_date FROM receivables"
                        " WHERE customer_id=?", (customer,)).fetchall()


class TestF01ReceivableJoinsTheSaleTransaction:
    def test_failed_sale_leaves_no_debt(self, conn):
        from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
        from backend.infrastructure.integrations.sales_credit_client import SalesCreditClient

        owner, owner_id = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        _authorized(conn, customer)
        with pytest.raises(RuntimeError):
            with SalesUnitOfWork(conn):
                SalesCreditClient(conn, actor_user_id=owner_id).register(
                    customer_id=customer, sale_id=new_uuid(), folio="V-1",
                    amount=Decimal("500"), branch_id=branch_id(conn), payment_id=new_uuid())
                raise RuntimeError("falló guardar la venta")
        assert _receivables(conn, customer) == []

    def test_successful_sale_keeps_the_debt_once(self, conn):
        from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
        from backend.infrastructure.integrations.sales_credit_client import SalesCreditClient

        owner, owner_id = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        _authorized(conn, customer, terms=15)
        sale, payment = new_uuid(), new_uuid()
        for _ in range(2):  # reintento del mismo pago: no duplica
            with SalesUnitOfWork(conn):
                SalesCreditClient(conn, actor_user_id=owner_id).register(
                    customer_id=customer, sale_id=sale, folio="V-2", amount=Decimal("500"),
                    branch_id=branch_id(conn), payment_id=payment)
        rows = _receivables(conn, customer)
        assert len(rows) == 1
        assert rows[0][1][:10] == (date.today() + timedelta(days=15)).isoformat()


class TestF02LegacyDebtIsFoundByCanonicalId:
    def test_legacy_balance_counts_toward_exposure(self, conn):
        from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
            CustomerAccountsReceivableSummaryQuery,
        )
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        legacy = new_uuid()
        conn.execute("UPDATE customers SET legacy_customer_id=? WHERE id=?", (legacy, customer))
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO cuentas_por_cobrar (id, cliente_id, folio, monto_original,"
                     " saldo_pendiente, estado, fecha) VALUES (?,?,?,?,?,?,?)",
                     (new_uuid(), legacy, "L-1", 900, 900, "pendiente", "2026-01-10"))
        conn.commit()

        summary = CustomerAccountsReceivableSummaryQuery(conn).get_summary(customer)
        assert summary.current_exposure == Decimal("900")

    def test_eligibility_sees_the_legacy_debt(self, conn):
        owner, owner_id = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        _authorized(conn, customer, limit="1000")
        legacy = new_uuid()
        conn.execute("UPDATE customers SET legacy_customer_id=? WHERE id=?", (legacy, customer))
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO cuentas_por_cobrar (id, cliente_id, folio, monto_original,"
                     " saldo_pendiente, estado, fecha) VALUES (?,?,?,?,?,?,?)",
                     (new_uuid(), legacy, "L-2", 900, 900, "pendiente", date.today().isoformat()))
        conn.commit()
        from backend.application.customer_credit.use_cases.check_credit_sale_eligibility_use_case import (
            CheckCreditSaleEligibilityUseCase,
        )
        from backend.application.customers.authorization import CustomerAuthorizationPolicy
        from backend.application.customers.session_authorization import (
            CustomerSessionPermissionChecker,
        )
        from tests.integration.crm43.conftest import session_for
        auth = CustomerAuthorizationPolicy(CustomerSessionPermissionChecker(
            session_for(conn, owner_id, "system_owner")))
        result = CheckCreditSaleEligibilityUseCase(auth).execute(
            conn, actor_user_id=owner_id, customer_id=customer, amount="500",
            operation_id=new_uuid())
        assert not result.success
        assert "disponible $100.00" in result.message


class TestF23AgreedDueDate:
    def test_document_keeps_its_due_date_when_terms_change(self, conn):
        from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
            CustomerAccountsReceivableSummaryQuery,
        )
        from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
        from backend.infrastructure.integrations.sales_credit_client import SalesCreditClient

        owner, owner_id = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        _authorized(conn, customer, terms=15)
        with SalesUnitOfWork(conn):
            SalesCreditClient(conn, actor_user_id=owner_id).register(
                customer_id=customer, sale_id=new_uuid(), folio="V-3", amount=Decimal("200"),
                branch_id=branch_id(conn), payment_id=new_uuid())
        conn.execute("UPDATE customer_credit_profiles SET payment_terms_days=30"
                     " WHERE customer_id=?", (customer,))
        conn.commit()
        summary = CustomerAccountsReceivableSummaryQuery(conn).get_summary(
            customer, payment_terms_days=30)
        assert summary.next_due_date == date.today() + timedelta(days=15)

    def test_unmodelled_checks_are_not_reported_as_passed_or_failed(self):
        from backend.domain.customer_credit.policies.credit_sale_eligibility_policy import (
            CreditSaleEligibilityPolicy,
        )
        result = CreditSaleEligibilityPolicy().evaluate(
            None, amount=Decimal("10"), is_public_customer=False,
            available_credit=Decimal("0"))
        assert not any("documentos" in v or "sucursal" in v for v in result.violations)
        refused = CreditSaleEligibilityPolicy().evaluate(
            None, amount=Decimal("10"), is_public_customer=False,
            available_credit=Decimal("0"), documents_current=False, branch_allowed=False)
        assert any("documentos" in v for v in refused.violations)
        assert any("sucursal" in v for v in refused.violations)
