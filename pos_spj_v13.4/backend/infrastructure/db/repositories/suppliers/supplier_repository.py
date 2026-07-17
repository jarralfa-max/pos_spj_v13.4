"""SupplierRepository — persists the Supplier aggregate (master + blocks + categories)."""

from __future__ import annotations

from backend.domain.suppliers.entities import Supplier, SupplierBlock
from backend.domain.suppliers.enums import (
    BlockType,
    CommercialCategory,
    SupplierClassification,
    SupplierStatus,
)
from backend.domain.suppliers.value_objects import SupplierCode, TaxIdentifier
from backend.infrastructure.db.repositories.suppliers.base import (
    SupplierRepositoryBase,
    normalize_name,
)
from backend.shared.ids import new_uuid

_MASTER_COLS = (
    "id, supplier_code, legal_name, trade_name, normalized_name, tax_identifier,"
    " person_type, tax_regime, country_code, preferred_currency, language, website,"
    " notes, status, risk_level, rating_grade, rating_score, created_by_user_id,"
    " approved_by_user_id, has_history, active, operation_id, created_at, updated_at"
)
_BLOCK_COLS = (
    "id, supplier_id, block_type, reason, effective_at, expires_at,"
    " created_by_user_id, approved_by_user_id, operation_id, active"
)

_INACTIVE_STATES = {SupplierStatus.INACTIVE, SupplierStatus.REJECTED}


def _active_flag(supplier: Supplier) -> int:
    """Denormalized 'active' column, derived from status (not an entity field)."""
    return 0 if supplier.status in _INACTIVE_STATES else 1


class SupplierRepository(SupplierRepositoryBase):
    def next_code(self) -> SupplierCode:
        last = self._scalar(
            "SELECT supplier_code FROM supplier_master"
            " ORDER BY CAST(SUBSTR(supplier_code, 5) AS INTEGER) DESC LIMIT 1")
        seq = (int(last.split("-")[1]) + 1) if last else 1
        return SupplierCode.from_sequence(seq)

    def save(self, supplier: Supplier, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO supplier_master ({_MASTER_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._master_params(supplier, operation_id))
        self._save_children(supplier)

    def update(self, supplier: Supplier) -> None:
        # risk_level / rating_* are denormalized projections owned by SUP-7
        # (update_risk / update_rating); the aggregate update never clobbers them.
        self._execute(
            "UPDATE supplier_master SET legal_name=?, trade_name=?, normalized_name=?,"
            " tax_identifier=?, person_type=?, tax_regime=?, country_code=?,"
            " preferred_currency=?, language=?, website=?, notes=?, status=?,"
            " approved_by_user_id=?, has_history=?, active=?, updated_at=? WHERE id=?",
            (supplier.legal_name, supplier.trade_name, normalize_name(supplier.legal_name),
             str(supplier.tax_identifier) if supplier.tax_identifier else None,
             supplier.tax_identifier.person_type.value if (supplier.tax_identifier
                and supplier.tax_identifier.person_type) else None,
             supplier.tax_regime, supplier.country_code, supplier.preferred_currency,
             supplier.language, supplier.website, supplier.notes, supplier.status.value,
             supplier.approved_by_user_id, int(supplier.has_history), _active_flag(supplier),
             supplier.updated_at, supplier.id))
        self._conn.execute("DELETE FROM supplier_blocks WHERE supplier_id=?", (supplier.id,))
        self._conn.execute("DELETE FROM supplier_category_links WHERE supplier_id=?", (supplier.id,))
        self._save_children(supplier)

    def update_risk(self, supplier_id: str, risk_level: str | None) -> None:
        self._execute("UPDATE supplier_master SET risk_level=? WHERE id=?",
                      (risk_level, supplier_id))

    def update_rating(self, supplier_id: str, grade: str | None, score: int | None) -> None:
        self._execute("UPDATE supplier_master SET rating_grade=?, rating_score=? WHERE id=?",
                      (grade, score, supplier_id))

    def get(self, supplier_id: str) -> Supplier | None:
        row = self._query_one(
            f"SELECT {_MASTER_COLS} FROM supplier_master WHERE id=?", (supplier_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> Supplier | None:
        row = self._query_one(
            f"SELECT {_MASTER_COLS} FROM supplier_master WHERE supplier_code=?", (code,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> Supplier | None:
        row = self._query_one(
            f"SELECT {_MASTER_COLS} FROM supplier_master WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def find_duplicate_rows(self) -> list[dict]:
        """Lightweight rows for the duplicate policy (never loads full aggregates)."""
        return self._query(
            "SELECT m.id, m.tax_identifier, m.legal_name, m.trade_name,"
            " c.phone_e164, c.email, b.clabe, b.account_number"
            " FROM supplier_master m"
            " LEFT JOIN supplier_contacts c ON c.supplier_id=m.id AND c.is_primary=1"
            " LEFT JOIN supplier_bank_accounts b ON b.supplier_id=m.id")

    def list_active(self, *, limit: int = 200, offset: int = 0) -> list[Supplier]:
        rows = self._query(
            f"SELECT {_MASTER_COLS} FROM supplier_master WHERE status='ACTIVE'"
            " ORDER BY legal_name LIMIT ? OFFSET ?", (limit, offset))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _master_params(supplier: Supplier, operation_id: str | None) -> tuple:
        tax = supplier.tax_identifier
        return (
            supplier.id, str(supplier.code), supplier.legal_name, supplier.trade_name,
            normalize_name(supplier.legal_name), str(tax) if tax else None,
            (tax.person_type.value if tax and tax.person_type else None),
            supplier.tax_regime, supplier.country_code, supplier.preferred_currency,
            supplier.language, supplier.website, supplier.notes, supplier.status.value,
            None, None, None,   # risk_level, rating_grade, rating_score (SUP-7 projections)
            supplier.created_by_user_id, supplier.approved_by_user_id,
            int(supplier.has_history), _active_flag(supplier),
            operation_id or supplier.id, supplier.created_at, supplier.updated_at)

    def _save_children(self, supplier: Supplier) -> None:
        for block in supplier.blocks:
            self._execute(
                f"INSERT INTO supplier_blocks ({_BLOCK_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (block.id, block.supplier_id, block.block_type.value, block.reason,
                 block.effective_at, block.expires_at, block.created_by_user_id,
                 block.approved_by_user_id, block.operation_id, int(block.active)))
        for classification in supplier.classifications:
            self._execute(
                "INSERT INTO supplier_category_links (id, supplier_id, category_type,"
                " category_code) VALUES (?,?,?,?)",
                (new_uuid(), supplier.id, "CLASSIFICATION", classification.value))
        for category in supplier.categories:
            self._execute(
                "INSERT INTO supplier_category_links (id, supplier_id, category_type,"
                " category_code) VALUES (?,?,?,?)",
                (new_uuid(), supplier.id, "COMMERCIAL", category.value))

    def _hydrate(self, row: dict) -> Supplier:
        blocks = [
            SupplierBlock(
                id=b["id"], supplier_id=b["supplier_id"],
                block_type=BlockType(b["block_type"]), reason=b["reason"],
                created_by_user_id=b["created_by_user_id"], operation_id=b["operation_id"],
                effective_at=b["effective_at"], expires_at=b["expires_at"],
                approved_by_user_id=b["approved_by_user_id"], active=bool(b["active"]))
            for b in self._query(
                f"SELECT {_BLOCK_COLS} FROM supplier_blocks WHERE supplier_id=? AND active=1",
                (row["id"],))
        ]
        links = self._query(
            "SELECT category_type, category_code FROM supplier_category_links"
            " WHERE supplier_id=?", (row["id"],))
        classifications = {SupplierClassification(l["category_code"]) for l in links
                           if l["category_type"] == "CLASSIFICATION"}
        categories = {CommercialCategory(l["category_code"]) for l in links
                      if l["category_type"] == "COMMERCIAL"}
        supplier = Supplier(
            id=row["id"], code=SupplierCode(row["supplier_code"]),
            legal_name=row["legal_name"], trade_name=row["trade_name"],
            tax_identifier=TaxIdentifier(row["tax_identifier"]) if row["tax_identifier"] else None,
            status=SupplierStatus(row["status"]), tax_regime=row["tax_regime"],
            country_code=row["country_code"], preferred_currency=row["preferred_currency"],
            language=row["language"], website=row["website"], notes=row["notes"] or "",
            classifications=classifications, categories=categories, blocks=blocks,
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"],
            has_history=bool(row["has_history"]),
            created_at=row["created_at"], updated_at=row["updated_at"])
        return supplier
