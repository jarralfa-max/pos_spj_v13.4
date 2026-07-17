"""FASE SUP-2 — supplier repository round-trips + UnitOfWork behavior."""

from datetime import date
from decimal import Decimal

import pytest

from backend.domain.suppliers.entities import (
    Supplier,
    SupplierBankAccount,
    SupplierBlock,
    SupplierCommercialTerms,
    SupplierContact,
    SupplierDocument,
    SupplierEvaluation,
    SupplierEvaluationItem,
    SupplierProduct,
)
from backend.domain.suppliers.enums import (
    BankAccountStatus,
    BlockType,
    CommercialCategory,
    ContactType,
    DocumentType,
    EvaluationDimension,
    SupplierClassification,
    SupplierStatus,
)
from backend.domain.suppliers.value_objects import (
    Money,
    PaymentTerms,
    SupplierCode,
    TaxIdentifier,
)
from backend.infrastructure.db.repositories.suppliers.unit_of_work import SupplierUnitOfWork
from backend.shared.ids import new_uuid


def _new_supplier(uow, code=None) -> Supplier:
    supplier = Supplier.create(
        code or uow.suppliers.next_code(), "Distribuidora del Valle SA de CV",
        trade_name="Del Valle", tax_identifier=TaxIdentifier("DVA010203XY1"),
        created_by_user_id="u-capturista",
        classifications={SupplierClassification.GOODS},
        categories={CommercialCategory.POULTRY, CommercialCategory.EGGS})
    return supplier


class TestSupplierMaster:
    def test_save_and_get_with_categories(self, sup_conn):
        with SupplierUnitOfWork(sup_conn) as uow:
            s = _new_supplier(uow)
            uow.suppliers.save(s, operation_id="op-1")
            sid = s.id
        with SupplierUnitOfWork(sup_conn) as uow:
            loaded = uow.suppliers.get(sid)
        assert loaded is not None
        assert str(loaded.code) == "PRV-000001"
        assert SupplierClassification.GOODS in loaded.classifications
        assert CommercialCategory.POULTRY in loaded.categories
        assert loaded.tax_identifier.value == "DVA010203XY1"

    def test_next_code_increments(self, sup_conn):
        with SupplierUnitOfWork(sup_conn) as uow:
            uow.suppliers.save(_new_supplier(uow, SupplierCode.from_sequence(1)))
        with SupplierUnitOfWork(sup_conn) as uow:
            assert str(uow.suppliers.next_code()) == "PRV-000002"

    def test_operation_id_idempotency_guard(self, sup_conn):
        with SupplierUnitOfWork(sup_conn) as uow:
            uow.suppliers.save(_new_supplier(uow), operation_id="op-dup")
        with SupplierUnitOfWork(sup_conn) as uow:
            assert uow.suppliers.get_by_operation_id("op-dup") is not None

    def test_status_and_blocks_roundtrip(self, sup_conn):
        with SupplierUnitOfWork(sup_conn) as uow:
            s = _new_supplier(uow)
            s.submit_for_approval(); s.approve("u-boss")
            s.apply_block(SupplierBlock.create(
                s.id, BlockType.PAYMENT_BLOCK, "banco sin verificar", "u2", new_uuid()))
            uow.suppliers.save(s)
            sid = s.id
        with SupplierUnitOfWork(sup_conn) as uow:
            loaded = uow.suppliers.get(sid)
        assert loaded.status is SupplierStatus.ACTIVE
        assert loaded.has_block(BlockType.PAYMENT_BLOCK)
        assert not loaded.can_pay()

    def test_update_rewrites_blocks(self, sup_conn):
        with SupplierUnitOfWork(sup_conn) as uow:
            s = _new_supplier(uow); s.submit_for_approval(); s.approve("u2")
            s.apply_block(SupplierBlock.create(s.id, BlockType.GENERAL_BLOCK, "x", "u", new_uuid()))
            uow.suppliers.save(s); sid = s.id
        with SupplierUnitOfWork(sup_conn) as uow:
            s = uow.suppliers.get(sid)
            s.remove_block(BlockType.GENERAL_BLOCK)
            uow.suppliers.update(s)
        with SupplierUnitOfWork(sup_conn) as uow:
            assert uow.suppliers.get(sid).status is SupplierStatus.ACTIVE
            assert not uow.suppliers.get(sid).has_block(BlockType.GENERAL_BLOCK)


class TestChildRepositories:
    def _supplier_id(self, sup_conn) -> str:
        with SupplierUnitOfWork(sup_conn) as uow:
            s = _new_supplier(uow)
            uow.suppliers.save(s)
            return s.id

    def test_contact_roundtrip(self, sup_conn):
        sid = self._supplier_id(sup_conn)
        with SupplierUnitOfWork(sup_conn) as uow:
            uow.contacts.save(SupplierContact.create(
                sid, "Ana", ContactType.PURCHASING, phone_e164="+525511112222",
                email="ana@delvalle.mx", is_primary=True))
        with SupplierUnitOfWork(sup_conn) as uow:
            contacts = uow.contacts.list_by_supplier(sid)
        assert len(contacts) == 1 and contacts[0].is_primary

    def test_bank_account_verification_persists(self, sup_conn):
        sid = self._supplier_id(sup_conn)
        with SupplierUnitOfWork(sup_conn) as uow:
            acct = SupplierBankAccount.create(sid, "BBVA", "Del Valle",
                                              clabe="012345678901231234")
            uow.bank_accounts.save(acct); aid = acct.id
        with SupplierUnitOfWork(sup_conn) as uow:
            acct = uow.bank_accounts.get(aid)
            acct.verify("u-tesoreria")
            uow.bank_accounts.update(acct)
        with SupplierUnitOfWork(sup_conn) as uow:
            acct = uow.bank_accounts.get(aid)
        assert acct.status is BankAccountStatus.VERIFIED
        assert acct.masked_clabe().endswith("1234")

    def test_commercial_terms_upsert(self, sup_conn):
        sid = self._supplier_id(sup_conn)
        terms = SupplierCommercialTerms.create(
            sid, PaymentTerms(credit_days=30, credit_limit=Money(Decimal("50000")),
                              advance_required=True, advance_percentage=Decimal("20")),
            lead_time_days=3, receiving_window_start="08:00", receiving_window_end="16:00")
        with SupplierUnitOfWork(sup_conn) as uow:
            uow.terms.upsert(terms)
        with SupplierUnitOfWork(sup_conn) as uow:
            loaded = uow.terms.get_by_supplier(sid)
        assert loaded.payment_terms.credit_days == 30
        assert loaded.payment_terms.credit_limit.amount == Decimal("50000")
        assert loaded.receiving_window_start == "08:00"

    def test_supplier_product_multiple_suppliers_one_preferred(self, sup_conn):
        sid = self._supplier_id(sup_conn)
        product_id = new_uuid()
        with SupplierUnitOfWork(sup_conn) as uow:
            uow.products.upsert(SupplierProduct.create(
                sid, product_id, supplier_sku="SKU-1", preferred=True,
                current_cost=Money(Decimal("12.50"))))
        with SupplierUnitOfWork(sup_conn) as uow:
            rows = uow.products.list_by_product(product_id)
        assert rows and rows[0].preferred and rows[0].current_cost.amount == Decimal("12.50")

    def test_document_roundtrip(self, sup_conn):
        sid = self._supplier_id(sup_conn)
        with SupplierUnitOfWork(sup_conn) as uow:
            uow.documents.save(SupplierDocument.create(
                sid, DocumentType.TAX_STATUS, "file://ref", expires_at=date(2027, 1, 1)))
        with SupplierUnitOfWork(sup_conn) as uow:
            docs = uow.documents.list_by_supplier(sid)
        assert len(docs) == 1 and docs[0].document_type is DocumentType.TAX_STATUS


class TestEvaluationRepository:
    def test_evaluation_roundtrip(self, sup_conn):
        with SupplierUnitOfWork(sup_conn) as uow:
            s = _new_supplier(uow); uow.suppliers.save(s); sid = s.id
        ev = SupplierEvaluation.create(
            sid, "2026-07",
            [SupplierEvaluationItem(EvaluationDimension.QUALITY, 90, Decimal("2")),
             SupplierEvaluationItem(EvaluationDimension.PRICE, 60, Decimal("1"))],
            "u-eval")
        with SupplierUnitOfWork(sup_conn) as uow:
            uow.evaluations.save(ev, operation_id="op-ev")
        with SupplierUnitOfWork(sup_conn) as uow:
            latest = uow.evaluations.latest_for_supplier(sid)
            assert latest.score == 80
            assert uow.evaluations.find_by_operation_id("op-ev") is not None


class TestUnitOfWork:
    def test_rollback_on_exception_leaves_no_row(self, sup_conn):
        with pytest.raises(RuntimeError):
            with SupplierUnitOfWork(sup_conn) as uow:
                uow.suppliers.save(_new_supplier(uow))
                raise RuntimeError("boom")
        count = sup_conn.execute("SELECT COUNT(*) FROM supplier_master").fetchone()[0]
        assert count == 0

    def test_audit_and_outbox_persist(self, sup_conn):
        with SupplierUnitOfWork(sup_conn) as uow:
            s = _new_supplier(uow)
            uow.suppliers.save(s)
            uow.audit.record(action="SUPPLIER_CREATED", actor_user_id="u1",
                             supplier_id=s.id, reason="alta")
            uow.outbox.enqueue(new_uuid(), "SUPPLIER_CREATED", "{}", "op-x")
        assert sup_conn.execute("SELECT COUNT(*) FROM supplier_audit_log").fetchone()[0] == 1
        assert sup_conn.execute(
            "SELECT COUNT(*) FROM supplier_outbox WHERE status='PENDING'").fetchone()[0] == 1
