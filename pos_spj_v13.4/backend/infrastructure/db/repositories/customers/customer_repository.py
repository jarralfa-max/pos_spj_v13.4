"""CustomerRepository — persists the Customer aggregate (master row only;
children live in customer_child_repositories.py). Mirrors
backend/infrastructure/db/repositories/suppliers/supplier_repository.py.
"""

from __future__ import annotations

from backend.domain.customers.entities.customer import Customer
from backend.domain.customers.enums import CustomerStatus, CustomerType, LifecycleStage
from backend.domain.customers.value_objects.customer_code import CustomerCode
from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase

_MASTER_COLS = (
    "id, customer_number, customer_type, display_name, legal_name, first_name,"
    " last_name, second_last_name, commercial_name, status, lifecycle_stage,"
    " source, origin_branch_id, primary_contact_id, default_billing_address_id,"
    " default_delivery_address_id, account_owner_user_id, territory_id,"
    " created_by_user_id, operation_id, version, created_at, updated_at,"
    " activated_at, suspended_at, blocked_at, closed_at, last_purchase_at,"
    " purchase_count"
)


class CustomerRepository(CustomerRepositoryBase):
    def next_code(self) -> CustomerCode:
        last = self._scalar(
            "SELECT customer_number FROM customers"
            " ORDER BY CAST(SUBSTR(customer_number, 5) AS INTEGER) DESC LIMIT 1")
        seq = (int(last.split("-")[1]) + 1) if last else 1
        return CustomerCode.from_sequence(seq)

    def save(self, customer: Customer, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customers ({_MASTER_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(customer, operation_id or customer.operation_id))

    def update(self, customer: Customer) -> None:
        self._execute(
            "UPDATE customers SET display_name=?, legal_name=?, first_name=?, last_name=?,"
            " second_last_name=?, commercial_name=?, status=?, lifecycle_stage=?, source=?,"
            " origin_branch_id=?, primary_contact_id=?, default_billing_address_id=?,"
            " default_delivery_address_id=?, account_owner_user_id=?, territory_id=?,"
            " version=?, updated_at=?, activated_at=?, suspended_at=?, blocked_at=?,"
            " closed_at=?, last_purchase_at=?, purchase_count=? WHERE id=?",
            (customer.display_name, customer.legal_name, customer.first_name,
             customer.last_name, customer.second_last_name, customer.commercial_name,
             customer.status.value, customer.lifecycle_stage.value, customer.source,
             customer.origin_branch_id, customer.primary_contact_id,
             customer.default_billing_address_id, customer.default_delivery_address_id,
             customer.account_owner_user_id, customer.territory_id, customer.version,
             customer.updated_at, customer.activated_at, customer.suspended_at,
             customer.blocked_at, customer.closed_at, customer.last_purchase_at,
             customer.purchase_count, customer.id))

    def get(self, customer_id: str) -> Customer | None:
        row = self._query_one(f"SELECT {_MASTER_COLS} FROM customers WHERE id=?", (customer_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> Customer | None:
        row = self._query_one(
            f"SELECT {_MASTER_COLS} FROM customers WHERE customer_number=?", (code,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> Customer | None:
        row = self._query_one(
            f"SELECT {_MASTER_COLS} FROM customers WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def find_duplicate_rows(self) -> list[dict]:
        """Lightweight rows for CustomerDuplicatePolicy (never loads full aggregates)."""
        return self._query(
            "SELECT c.id, c.display_name, c.legal_name, t.tax_identifier,"
            " ct.phone_e164, ct.email"
            " FROM customers c"
            " LEFT JOIN customer_tax_profiles t ON t.customer_id=c.id"
            " LEFT JOIN customer_contacts ct ON ct.customer_id=c.id AND ct.is_primary=1")

    def list_active(self, *, limit: int = 200, offset: int = 0) -> list[Customer]:
        rows = self._query(
            f"SELECT {_MASTER_COLS} FROM customers WHERE status='ACTIVE'"
            " ORDER BY display_name LIMIT ? OFFSET ?", (limit, offset))
        return [self._hydrate(r) for r in rows]

    def list_owned_by(self, owner_user_ids: tuple[str, ...], *,
                       limit: int = 200, offset: int = 0) -> list[Customer]:
        """Filter for CustomerDataScope(axis=OWN/TEAM) — reads by owner set."""
        if not owner_user_ids:
            return []
        placeholders = ",".join("?" for _ in owner_user_ids)
        rows = self._query(
            f"SELECT {_MASTER_COLS} FROM customers WHERE account_owner_user_id IN"
            f" ({placeholders}) ORDER BY display_name LIMIT ? OFFSET ?",
            (*owner_user_ids, limit, offset))
        return [self._hydrate(r) for r in rows]

    def list_by_branch(self, branch_id: str, *, limit: int = 200, offset: int = 0) -> list[Customer]:
        rows = self._query(
            f"SELECT {_MASTER_COLS} FROM customers WHERE origin_branch_id=?"
            " ORDER BY display_name LIMIT ? OFFSET ?", (branch_id, limit, offset))
        return [self._hydrate(r) for r in rows]

    def search_lookup(self, query: str, *, limit: int = 20) -> list[dict]:
        """CRM-12: lightweight rows for CustomerLookupQueryService's fast
        typeahead — never hydrates a full Customer aggregate (unlike
        find_duplicate_rows, which loads the whole base for one-shot batch
        matching, this runs per-keystroke and must stay cheap)."""
        pattern = f"%{query}%"
        return self._query(
            "SELECT c.id, c.customer_number, c.display_name, c.legal_name, c.status,"
            " ct.phone_e164, ct.email"
            " FROM customers c"
            " LEFT JOIN customer_contacts ct ON ct.customer_id=c.id AND ct.is_primary=1"
            " WHERE c.status NOT IN ('CLOSED','MERGED','ANONYMIZED')"
            " AND (c.display_name LIKE ? OR c.legal_name LIKE ?"
            " OR ct.phone_e164 LIKE ? OR ct.email LIKE ?)"
            " ORDER BY c.display_name LIMIT ?",
            (pattern, pattern, pattern, pattern, limit))

    def list_by_territory(self, territory_id: str, *, limit: int = 200, offset: int = 0) -> list[Customer]:
        rows = self._query(
            f"SELECT {_MASTER_COLS} FROM customers WHERE territory_id=?"
            " ORDER BY display_name LIMIT ? OFFSET ?", (territory_id, limit, offset))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(customer: Customer, operation_id: str | None) -> tuple:
        return (
            customer.id, str(customer.code), customer.customer_type.value,
            customer.display_name, customer.legal_name, customer.first_name,
            customer.last_name, customer.second_last_name, customer.commercial_name,
            customer.status.value, customer.lifecycle_stage.value, customer.source,
            customer.origin_branch_id, customer.primary_contact_id,
            customer.default_billing_address_id, customer.default_delivery_address_id,
            customer.account_owner_user_id, customer.territory_id,
            customer.created_by_user_id, operation_id, customer.version,
            customer.created_at, customer.updated_at, customer.activated_at,
            customer.suspended_at, customer.blocked_at, customer.closed_at,
            customer.last_purchase_at, customer.purchase_count,
        )

    @staticmethod
    def _hydrate(row: dict) -> Customer:
        return Customer(
            id=row["id"], code=CustomerCode(row["customer_number"]),
            customer_type=CustomerType(row["customer_type"]),
            display_name=row["display_name"], legal_name=row["legal_name"] or "",
            first_name=row["first_name"] or "", last_name=row["last_name"] or "",
            second_last_name=row["second_last_name"] or "",
            commercial_name=row["commercial_name"] or "",
            status=CustomerStatus(row["status"]),
            lifecycle_stage=LifecycleStage(row["lifecycle_stage"]),
            source=row["source"] or "", origin_branch_id=row["origin_branch_id"],
            primary_contact_id=row["primary_contact_id"],
            default_billing_address_id=row["default_billing_address_id"],
            default_delivery_address_id=row["default_delivery_address_id"],
            account_owner_user_id=row["account_owner_user_id"],
            territory_id=row["territory_id"], created_by_user_id=row["created_by_user_id"],
            operation_id=row["operation_id"], version=row["version"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            activated_at=row["activated_at"], suspended_at=row["suspended_at"],
            blocked_at=row["blocked_at"], closed_at=row["closed_at"],
            last_purchase_at=row["last_purchase_at"],
            purchase_count=row["purchase_count"] or 0,
        )
