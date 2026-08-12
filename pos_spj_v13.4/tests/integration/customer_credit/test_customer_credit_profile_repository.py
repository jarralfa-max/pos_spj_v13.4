"""CRM-8 — CustomerCreditProfile repository round-trips."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.customer_credit.entities.customer_credit_profile import CustomerCreditProfile
from backend.infrastructure.db.repositories.customer_credit.unit_of_work import (
    CustomerCreditUnitOfWork,
)


class TestCustomerCreditProfileRepository:
    def test_save_and_get_by_customer_id(self, cc_conn):
        with CustomerCreditUnitOfWork(cc_conn) as uow:
            profile = CustomerCreditProfile.request("cust-1", "u1", requested_limit="5000",
                                                     payment_terms_days=15, operation_id="op-1")
            uow.profiles.save(profile, operation_id="op-1")
        with CustomerCreditUnitOfWork(cc_conn) as uow2:
            fetched = uow2.profiles.get_by_customer_id("cust-1")
            assert fetched.credit_limit == Decimal("5000")
            assert fetched.payment_terms_days == 15
            assert fetched.status.value == "PENDING_APPROVAL"

    def test_get_by_operation_id_is_idempotency_lookup(self, cc_conn):
        with CustomerCreditUnitOfWork(cc_conn) as uow:
            profile = CustomerCreditProfile.request("cust-1", "u1", operation_id="op-dup")
            uow.profiles.save(profile, operation_id="op-dup")
        with CustomerCreditUnitOfWork(cc_conn) as uow2:
            found = uow2.profiles.get_by_operation_id("op-dup")
            assert found is not None and found.id == profile.id

    def test_update_persists_status_and_version(self, cc_conn):
        with CustomerCreditUnitOfWork(cc_conn) as uow:
            profile = CustomerCreditProfile.request("cust-1", "u1", operation_id="op-1")
            uow.profiles.save(profile, operation_id="op-1")
        with CustomerCreditUnitOfWork(cc_conn) as uow2:
            profile = uow2.profiles.get_by_customer_id("cust-1")
            profile.review()
            profile.approve("u-gerente", credit_limit="8000")
            uow2.profiles.update(profile)
        with CustomerCreditUnitOfWork(cc_conn) as uow3:
            reloaded = uow3.profiles.get_by_customer_id("cust-1")
            assert reloaded.status.value == "AUTHORIZED"
            assert reloaded.credit_limit == Decimal("8000")
            assert reloaded.version == 3

    def test_one_profile_per_customer_unique_constraint(self, cc_conn):
        import sqlite3

        import pytest

        with CustomerCreditUnitOfWork(cc_conn) as uow:
            profile = CustomerCreditProfile.request("cust-1", "u1", operation_id="op-1")
            uow.profiles.save(profile, operation_id="op-1")
        with pytest.raises(sqlite3.IntegrityError):
            with CustomerCreditUnitOfWork(cc_conn) as uow2:
                dup = CustomerCreditProfile.request("cust-1", "u2", operation_id="op-2")
                uow2.profiles.save(dup, operation_id="op-2")

    def test_list_by_status(self, cc_conn):
        with CustomerCreditUnitOfWork(cc_conn) as uow:
            p1 = CustomerCreditProfile.request("cust-1", "u1", operation_id="op-1")
            uow.profiles.save(p1, operation_id="op-1")
            p2 = CustomerCreditProfile.request("cust-2", "u1", operation_id="op-2")
            uow.profiles.save(p2, operation_id="op-2")
            p2.review()
            uow.profiles.update(p2)
        with CustomerCreditUnitOfWork(cc_conn) as uow2:
            pending = uow2.profiles.list_by_status("PENDING_APPROVAL")
            under_review = uow2.profiles.list_by_status("UNDER_REVIEW")
        assert [p.id for p in pending] == [p1.id]
        assert [p.id for p in under_review] == [p2.id]

    def test_rollback_on_exception_discards_all_writes(self, cc_conn):
        try:
            with CustomerCreditUnitOfWork(cc_conn) as uow:
                profile = CustomerCreditProfile.request("cust-1", "u1", operation_id="op-1")
                uow.profiles.save(profile, operation_id="op-1")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        count = cc_conn.execute("SELECT COUNT(*) FROM customer_credit_profiles").fetchone()[0]
        assert count == 0
