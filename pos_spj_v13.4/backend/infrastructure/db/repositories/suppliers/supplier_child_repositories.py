"""Repositories for supplier child entities (contacts/addresses/bank/terms/products/docs/branches)."""

from __future__ import annotations

from datetime import date

from backend.domain.suppliers.entities import (
    SupplierAddress,
    SupplierBankAccount,
    SupplierBranchAuthorization,
    SupplierCommercialTerms,
    SupplierContact,
    SupplierDocument,
    SupplierProduct,
)
from backend.domain.suppliers.enums import (
    AddressType,
    BankAccountStatus,
    ContactType,
    DocumentStatus,
    DocumentType,
)
from backend.domain.suppliers.value_objects import Money, PaymentTerms
from backend.infrastructure.db.repositories.suppliers.base import SupplierRepositoryBase

from decimal import Decimal


def _d(value) -> date | None:
    return date.fromisoformat(value) if value else None


class SupplierContactRepository(SupplierRepositoryBase):
    _COLS = ("id, supplier_id, name, contact_type, role, phone_e164, email, is_primary,"
             " receives_purchase_orders, receives_payment_receipts,"
             " receives_notifications, active")

    def save(self, c: SupplierContact) -> None:
        self._execute(
            f"INSERT INTO supplier_contacts ({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (c.id, c.supplier_id, c.name, c.contact_type.value, c.role, c.phone_e164,
             c.email, int(c.is_primary), int(c.receives_purchase_orders),
             int(c.receives_payment_receipts), int(c.receives_notifications), int(c.active)))

    def list_by_supplier(self, supplier_id: str) -> list[SupplierContact]:
        return [self._to_entity(r) for r in self._query(
            f"SELECT {self._COLS} FROM supplier_contacts WHERE supplier_id=?"
            " ORDER BY is_primary DESC, name", (supplier_id,))]

    @staticmethod
    def _to_entity(r: dict) -> SupplierContact:
        return SupplierContact(
            id=r["id"], supplier_id=r["supplier_id"], name=r["name"],
            contact_type=ContactType(r["contact_type"]), role=r["role"],
            phone_e164=r["phone_e164"], email=r["email"], is_primary=bool(r["is_primary"]),
            receives_purchase_orders=bool(r["receives_purchase_orders"]),
            receives_payment_receipts=bool(r["receives_payment_receipts"]),
            receives_notifications=bool(r["receives_notifications"]), active=bool(r["active"]))


class SupplierAddressRepository(SupplierRepositoryBase):
    _COLS = ("id, supplier_id, address_type, line, city, state, postal_code, country_code,"
             " latitude, longitude, geocoding_source, validation_state")

    def save(self, a: SupplierAddress) -> None:
        self._execute(
            f"INSERT INTO supplier_addresses ({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.id, a.supplier_id, a.address_type.value, a.line, a.city, a.state,
             a.postal_code, a.country_code, a.latitude, a.longitude,
             a.geocoding_source, a.validation_state))

    def list_by_supplier(self, supplier_id: str) -> list[SupplierAddress]:
        return [SupplierAddress(
            id=r["id"], supplier_id=r["supplier_id"],
            address_type=AddressType(r["address_type"]), line=r["line"], city=r["city"],
            state=r["state"], postal_code=r["postal_code"], country_code=r["country_code"],
            latitude=r["latitude"], longitude=r["longitude"],
            geocoding_source=r["geocoding_source"], validation_state=r["validation_state"])
            for r in self._query(
                f"SELECT {self._COLS} FROM supplier_addresses WHERE supplier_id=?", (supplier_id,))]


class SupplierBankAccountRepository(SupplierRepositoryBase):
    _COLS = ("id, supplier_id, bank_name, account_holder, currency_code, account_type,"
             " account_number, clabe, swift_bic, country_code, status, document_reference,"
             " verified_by_user_id, verified_at")

    def save(self, b: SupplierBankAccount) -> None:
        self._execute(
            f"INSERT INTO supplier_bank_accounts ({self._COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", self._params(b))

    def update(self, b: SupplierBankAccount) -> None:
        self._execute(
            "UPDATE supplier_bank_accounts SET bank_name=?, account_holder=?, currency_code=?,"
            " account_type=?, account_number=?, clabe=?, swift_bic=?, country_code=?, status=?,"
            " document_reference=?, verified_by_user_id=?, verified_at=? WHERE id=?",
            (b.bank_name, b.account_holder, b.currency_code, b.account_type, b.account_number,
             b.clabe, b.swift_bic, b.country_code, b.status.value, b.document_reference,
             b.verified_by_user_id, b.verified_at, b.id))

    def get(self, account_id: str) -> SupplierBankAccount | None:
        row = self._query_one(
            f"SELECT {self._COLS} FROM supplier_bank_accounts WHERE id=?", (account_id,))
        return self._to_entity(row) if row else None

    def list_by_supplier(self, supplier_id: str) -> list[SupplierBankAccount]:
        return [self._to_entity(r) for r in self._query(
            f"SELECT {self._COLS} FROM supplier_bank_accounts WHERE supplier_id=?", (supplier_id,))]

    @staticmethod
    def _params(b: SupplierBankAccount) -> tuple:
        return (b.id, b.supplier_id, b.bank_name, b.account_holder, b.currency_code,
                b.account_type, b.account_number, b.clabe, b.swift_bic, b.country_code,
                b.status.value, b.document_reference, b.verified_by_user_id, b.verified_at)

    @staticmethod
    def _to_entity(r: dict) -> SupplierBankAccount:
        return SupplierBankAccount(
            id=r["id"], supplier_id=r["supplier_id"], bank_name=r["bank_name"],
            account_holder=r["account_holder"], currency_code=r["currency_code"],
            account_type=r["account_type"], account_number=r["account_number"],
            clabe=r["clabe"], swift_bic=r["swift_bic"], country_code=r["country_code"],
            status=BankAccountStatus(r["status"]), document_reference=r["document_reference"],
            verified_by_user_id=r["verified_by_user_id"], verified_at=r["verified_at"])


class SupplierCommercialTermsRepository(SupplierRepositoryBase):
    def upsert(self, t: SupplierCommercialTerms) -> None:
        self._conn.execute("DELETE FROM supplier_commercial_terms WHERE supplier_id=?",
                           (t.supplier_id,))
        pt = t.payment_terms
        self._execute(
            "INSERT INTO supplier_commercial_terms (id, supplier_id, currency_code, price_list,"
            " credit_days, credit_limit, advance_required, advance_percentage,"
            " prompt_payment_discount, min_order_amount, quantity_tolerance, price_tolerance,"
            " lead_time_days, delivery_days, receiving_window_start, receiving_window_end,"
            " accepts_returns, return_window_days) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (t.id, t.supplier_id, t.currency_code, t.price_list, pt.credit_days,
             pt.credit_limit.to_string(), int(pt.advance_required), str(pt.advance_percentage),
             str(pt.prompt_payment_discount), pt.min_order_amount.to_string(),
             str(pt.quantity_tolerance), str(pt.price_tolerance), t.lead_time_days,
             t.delivery_days, t.receiving_window_start, t.receiving_window_end,
             int(t.accepts_returns), t.return_window_days))

    def get_by_supplier(self, supplier_id: str) -> SupplierCommercialTerms | None:
        r = self._query_one(
            "SELECT * FROM supplier_commercial_terms WHERE supplier_id=?", (supplier_id,))
        if r is None:
            return None
        pt = PaymentTerms(
            credit_days=r["credit_days"], credit_limit=Money(Decimal(r["credit_limit"]), r["currency_code"]),
            advance_required=bool(r["advance_required"]),
            advance_percentage=Decimal(r["advance_percentage"]),
            prompt_payment_discount=Decimal(r["prompt_payment_discount"]),
            min_order_amount=Money(Decimal(r["min_order_amount"]), r["currency_code"]),
            quantity_tolerance=Decimal(r["quantity_tolerance"]),
            price_tolerance=Decimal(r["price_tolerance"]))
        return SupplierCommercialTerms(
            id=r["id"], supplier_id=r["supplier_id"], payment_terms=pt,
            price_list=r["price_list"], lead_time_days=r["lead_time_days"],
            delivery_days=r["delivery_days"], receiving_window_start=r["receiving_window_start"],
            receiving_window_end=r["receiving_window_end"],
            accepts_returns=bool(r["accepts_returns"]), return_window_days=r["return_window_days"],
            currency_code=r["currency_code"])


class SupplierProductRepository(SupplierRepositoryBase):
    _COLS = ("id, supplier_id, product_id, supplier_sku, supplier_description, purchase_unit,"
             " conversion_factor, minimum_order_quantity, package_size, lead_time_days,"
             " last_cost, current_cost, currency_code, preferred, active, valid_from, valid_to")

    def upsert(self, p: SupplierProduct) -> None:
        self._conn.execute(
            "DELETE FROM supplier_products WHERE supplier_id=? AND product_id=?",
            (p.supplier_id, p.product_id))
        self._execute(
            f"INSERT INTO supplier_products ({self._COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.id, p.supplier_id, p.product_id, p.supplier_sku, p.supplier_description,
             p.purchase_unit, p.conversion_factor, p.minimum_order_quantity, p.package_size,
             p.lead_time_days, p.last_cost.to_string() if p.last_cost else None,
             p.current_cost.to_string() if p.current_cost else None, p.currency_code,
             int(p.preferred), int(p.active),
             p.valid_from.isoformat() if p.valid_from else None,
             p.valid_to.isoformat() if p.valid_to else None))

    def list_by_supplier(self, supplier_id: str) -> list[SupplierProduct]:
        return [self._to_entity(r) for r in self._query(
            f"SELECT {self._COLS} FROM supplier_products WHERE supplier_id=? AND active=1",
            (supplier_id,))]

    def list_by_product(self, product_id: str) -> list[SupplierProduct]:
        return [self._to_entity(r) for r in self._query(
            f"SELECT {self._COLS} FROM supplier_products WHERE product_id=? AND active=1"
            " ORDER BY preferred DESC", (product_id,))]

    @staticmethod
    def _to_entity(r: dict) -> SupplierProduct:
        cur = r["currency_code"]
        return SupplierProduct(
            id=r["id"], supplier_id=r["supplier_id"], product_id=r["product_id"],
            supplier_sku=r["supplier_sku"], supplier_description=r["supplier_description"],
            purchase_unit=r["purchase_unit"], conversion_factor=r["conversion_factor"],
            minimum_order_quantity=r["minimum_order_quantity"], package_size=r["package_size"],
            lead_time_days=r["lead_time_days"],
            last_cost=Money(Decimal(r["last_cost"]), cur) if r["last_cost"] else None,
            current_cost=Money(Decimal(r["current_cost"]), cur) if r["current_cost"] else None,
            currency_code=cur, preferred=bool(r["preferred"]), active=bool(r["active"]),
            valid_from=_d(r["valid_from"]), valid_to=_d(r["valid_to"]))


class SupplierDocumentRepository(SupplierRepositoryBase):
    _COLS = ("id, supplier_id, document_type, file_reference, status, issued_at, expires_at,"
             " verified_by_user_id, verified_at, notes")

    def save(self, d: SupplierDocument) -> None:
        self._execute(
            f"INSERT INTO supplier_documents ({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (d.id, d.supplier_id, d.document_type.value, d.file_reference, d.status.value,
             d.issued_at.isoformat() if d.issued_at else None,
             d.expires_at.isoformat() if d.expires_at else None,
             d.verified_by_user_id, d.verified_at, d.notes))

    def list_by_supplier(self, supplier_id: str) -> list[SupplierDocument]:
        return [SupplierDocument(
            id=r["id"], supplier_id=r["supplier_id"],
            document_type=DocumentType(r["document_type"]), file_reference=r["file_reference"],
            status=DocumentStatus(r["status"]), issued_at=_d(r["issued_at"]),
            expires_at=_d(r["expires_at"]), verified_by_user_id=r["verified_by_user_id"],
            verified_at=r["verified_at"], notes=r["notes"])
            for r in self._query(
                f"SELECT {self._COLS} FROM supplier_documents WHERE supplier_id=?", (supplier_id,))]


class SupplierBranchAuthorizationRepository(SupplierRepositoryBase):
    _COLS = ("id, supplier_id, branch_id, can_purchase, can_receive, can_pay, preferred, active")

    def upsert(self, a: SupplierBranchAuthorization) -> None:
        self._conn.execute(
            "DELETE FROM supplier_branch_authorizations WHERE supplier_id=? AND branch_id=?",
            (a.supplier_id, a.branch_id))
        self._execute(
            f"INSERT INTO supplier_branch_authorizations ({self._COLS}) VALUES (?,?,?,?,?,?,?,?)",
            (a.id, a.supplier_id, a.branch_id, int(a.can_purchase), int(a.can_receive),
             int(a.can_pay), int(a.preferred), int(a.active)))

    def get(self, supplier_id: str, branch_id: str) -> SupplierBranchAuthorization | None:
        r = self._query_one(
            f"SELECT {self._COLS} FROM supplier_branch_authorizations"
            " WHERE supplier_id=? AND branch_id=?", (supplier_id, branch_id))
        if r is None:
            return None
        return SupplierBranchAuthorization(
            id=r["id"], supplier_id=r["supplier_id"], branch_id=r["branch_id"],
            can_purchase=bool(r["can_purchase"]), can_receive=bool(r["can_receive"]),
            can_pay=bool(r["can_pay"]), preferred=bool(r["preferred"]), active=bool(r["active"]))
