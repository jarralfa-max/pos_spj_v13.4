"""BundleRepository — persistence for bundles / versions / components (PROD-13).

Decimal ↔ str; loads a version with its components. Never commits. Exposes the
ACTIVE version and a component resolver (over ACTIVE versions) for cycle detection.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.products.bundle_enums import BundleType
from backend.domain.products.entities.bundle_component import BundleComponent
from backend.domain.products.entities.bundle_version import BundleVersion
from backend.domain.products.entities.product_bundle import ProductBundle
from backend.domain.products.recipe_enums import RecipeVersionStatus


class BundleRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def save_bundle(self, bundle: ProductBundle) -> None:
        self._conn.execute(
            """INSERT INTO product_bundles (id, product_id, bundle_type, name, active)
               VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, active=excluded.active""",
            (bundle.id, bundle.product_id, bundle.bundle_type.value, bundle.name,
             int(bundle.active)))

    def get_bundle(self, bundle_id: str) -> ProductBundle | None:
        row = self._conn.execute(
            "SELECT * FROM product_bundles WHERE id=?", (bundle_id,)).fetchone()
        if row is None:
            return None
        return ProductBundle(id=row["id"], product_id=row["product_id"],
                             bundle_type=BundleType(row["bundle_type"]), name=row["name"],
                             active=bool(row["active"]))

    def save_version(self, version: BundleVersion) -> None:
        self._conn.execute(
            """INSERT INTO bundle_versions
               (id, bundle_id, version_number, status, effective_from, effective_to,
                approved_by_user_id, reason)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 status=excluded.status, effective_from=excluded.effective_from,
                 effective_to=excluded.effective_to,
                 approved_by_user_id=excluded.approved_by_user_id, reason=excluded.reason""",
            (version.id, version.bundle_id, version.version_number, version.status.value,
             version.effective_from, version.effective_to,
             version.approved_by_user_id, version.reason))
        self._conn.execute("DELETE FROM bundle_components WHERE version_id=?", (version.id,))
        for c in version.components:
            self._conn.execute(
                """INSERT INTO bundle_components
                   (id, version_id, component_product_id, quantity, unit_id,
                    optional, substitutable, sequence)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (c.id, version.id, c.component_product_id, str(c.quantity), c.unit_id,
                 int(c.optional), int(c.substitutable), c.sequence))

    def get_version(self, version_id: str) -> BundleVersion | None:
        row = self._conn.execute(
            "SELECT * FROM bundle_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            return None
        version = BundleVersion(
            id=row["id"], bundle_id=row["bundle_id"], version_number=row["version_number"],
            status=RecipeVersionStatus(row["status"]),
            effective_from=row["effective_from"], effective_to=row["effective_to"],
            approved_by_user_id=row["approved_by_user_id"], reason=row["reason"])
        version.components = [
            BundleComponent(id=r["id"], version_id=r["version_id"],
                            component_product_id=r["component_product_id"],
                            quantity=Decimal(r["quantity"]), unit_id=r["unit_id"],
                            optional=bool(r["optional"]), substitutable=bool(r["substitutable"]),
                            sequence=r["sequence"])
            for r in self._conn.execute(
                "SELECT * FROM bundle_components WHERE version_id=? ORDER BY sequence",
                (version_id,)).fetchall()]
        return version

    def active_version_for_product(self, product_id: str) -> BundleVersion | None:
        row = self._conn.execute(
            """SELECT v.id FROM bundle_versions v
               JOIN product_bundles b ON b.id = v.bundle_id
               WHERE b.product_id=? AND v.status='ACTIVE'
               ORDER BY v.version_number DESC LIMIT 1""", (product_id,)).fetchone()
        return self.get_version(row["id"]) if row else None

    def component_resolver(self):
        def resolve(product_id: str) -> list[str]:
            version = self.active_version_for_product(product_id)
            return version.component_product_ids() if version else []
        return resolve
