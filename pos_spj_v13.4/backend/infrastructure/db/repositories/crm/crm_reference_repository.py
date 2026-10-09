"""Lecturas de referencia para las pantallas de CRM (CRM-43): usuarios
asignables, nombres para mostrar y el catálogo de etapas.

Sólo lectura. Los ids son UUIDv7 TEXT — nunca se convierten a entero.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase


class CRMReferenceRepository(CRMRepositoryBase):
    def active_users(self) -> list[dict]:
        if not self._table_exists("usuarios"):
            return []
        return self._query(
            "SELECT id, COALESCE(NULLIF(TRIM(nombre),''), usuario) AS name, usuario,"
            " sucursal_id FROM usuarios WHERE activo=1 AND id IS NOT NULL"
            " ORDER BY name")

    def user_names(self, user_ids: tuple[str, ...]) -> dict[str, str]:
        ids = tuple(i for i in dict.fromkeys(user_ids) if i)
        if not ids or not self._table_exists("usuarios"):
            return {}
        marks = ",".join("?" for _ in ids)
        rows = self._query(
            "SELECT id, COALESCE(NULLIF(TRIM(nombre),''), usuario) AS name FROM usuarios"
            f" WHERE id IN ({marks})", ids)
        return {r["id"]: r["name"] for r in rows}

    def customer_names(self, customer_ids: tuple[str, ...]) -> dict[str, str]:
        ids = tuple(i for i in dict.fromkeys(customer_ids) if i)
        if not ids:
            return {}
        marks = ",".join("?" for _ in ids)
        rows = self._query(
            f"SELECT id, display_name FROM customers WHERE id IN ({marks})", ids)
        return {r["id"]: r["display_name"] for r in rows}

    #: tipo de registro relacionado → (tabla, expresión del nombre)
    _RELATED = {
        "CUSTOMER": ("customers", "display_name"),
        "LEAD": ("leads", "display_name"),
        "OPPORTUNITY": ("opportunities", "name"),
        "CASE": ("service_cases", "case_number || ' · ' || subject"),
    }

    def related_names(self, entity_type: str, entity_ids: tuple[str, ...]) -> dict[str, str]:
        spec = self._RELATED.get(entity_type)
        ids = tuple(i for i in dict.fromkeys(entity_ids) if i)
        if spec is None or not ids:
            return {}
        table, expression = spec
        marks = ",".join("?" for _ in ids)
        rows = self._query(f"SELECT id, {expression} AS name FROM {table} WHERE id IN ({marks})",
                           ids)
        return {r["id"]: r["name"] for r in rows}

    def branch_names(self) -> dict[str, str]:
        if not self._table_exists("sucursales"):
            return {}
        return {r["id"]: r["nombre"] for r in self._query("SELECT id, nombre FROM sucursales")}

    def _table_exists(self, name: str) -> bool:
        return self._query_one(
            "SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name=?", (name,)) is not None
