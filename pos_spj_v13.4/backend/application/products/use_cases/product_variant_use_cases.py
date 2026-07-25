"""GenerateProductVariantsUseCase (P1-03) — genera productos hijo por combinación.

A partir de un producto padre y un conjunto de ejes (atributo → opciones), crea un
producto hijo en DRAFT por cada combinación aún inexistente. Los hijos **heredan** la
configuración del padre (tipo, unidad base, categoría, marca, especie, capacidades);
el código se genera automáticamente y las asignaciones de atributo se registran. Exige
``PRODUCTS_VARIANTS_GENERATE`` (fail-closed) y es dueño de la transacción: o se crean
todas las variantes solicitadas o ninguna.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_variant_commands import (
    GenerateVariantsCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_code_query_service import (
    reserve_next_code,
)
from backend.domain.products.entities.product import Product  # noqa: F401 (doc ref)
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.policies.product_variant_policy import (
    cartesian_combinations,
)
from backend.infrastructure.db.repositories.products.attribute_repository import (
    ProductAttributeRepository,
)
from backend.infrastructure.db.repositories.products.product_master_repository import (
    _CAP_FLAGS,
    ProductMasterRepository,
)
from backend.infrastructure.db.repositories.products.variant_repository import (
    ProductVariantRepository,
)

logger = logging.getLogger("spj.products.variant_use_cases")


@dataclass(frozen=True)
class VariantResult:
    success: bool
    generated: int
    skipped: int
    message: str


def _normalized(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


class GenerateProductVariantsUseCase:
    name = "GenerateProductVariantsUseCase"

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._master = ProductMasterRepository(connection)
        self._attrs = ProductAttributeRepository(connection)
        self._variants = ProductVariantRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy()

    def execute(self, command: GenerateVariantsCommand) -> VariantResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.VARIANTS_GENERATE)
        parent = self._master.get(command.parent_product_id)
        if parent is None:
            return VariantResult(False, 0, 0, "El producto padre no existe")

        # Resolver ejes en orden estable; validar atributos/opciones (LISTA, activos).
        try:
            axes, option_meta = self._resolve_axes(command.axes)
            combos = cartesian_combinations(axes)
        except ProductsDomainError as exc:
            return VariantResult(False, 0, 0, str(exc))

        existing = self._variants.existing_combos(command.parent_product_id)
        generated = skipped = 0
        try:
            for combo in combos:
                if frozenset(combo) in existing:
                    skipped += 1
                    continue
                self._create_variant(parent, combo, option_meta)
                generated += 1
            if generated:
                self._emit_generated(command, generated, skipped)
            self._conn.commit()
        except Exception:
            _rollback(self._conn)
            logger.exception("variant generation failed op=%s", command.operation_id)
            raise
        return VariantResult(True, generated, skipped,
                             f"{generated} variantes creadas, {skipped} ya existían")

    # ── helpers ────────────────────────────────────────────────────────────
    def _resolve_axes(self, axes: dict[str, list[str]]):
        """Valida atributos/opciones y devuelve (ejes_ordenados, meta_opciones)."""
        resolved: list[tuple[str, list[str]]] = []
        meta: dict[str, dict] = {}
        for attribute_id, option_ids in axes.items():
            attribute = self._attrs.get(attribute_id)
            if attribute is None:
                raise ProductsDomainError(f"Atributo inexistente: {attribute_id}")
            attribute.ensure_accepts_options()  # sólo LISTA define variantes
            valid = {o.id: o for o in self._attrs.list_options(attribute_id,
                                                              active_only=True)}
            chosen = [oid for oid in option_ids if oid in valid]
            if not chosen:
                raise ProductsDomainError(
                    f"El atributo {attribute.name} no tiene opciones válidas")
            for oid in chosen:
                meta[oid] = {"attribute_name": attribute.name,
                             "label": valid[oid].label, "code": valid[oid].code}
            resolved.append((attribute_id, chosen))
        return resolved, meta

    def _create_variant(self, parent: dict, combo, option_meta: dict) -> None:
        from backend.shared.ids import new_uuid
        code = reserve_next_code(self._conn, product_type=parent["product_type"],
                                 category_id=parent.get("category_id"))
        suffix = " / ".join(option_meta[oid]["label"] for _attr, oid in combo)
        name = f"{parent['name']} - {suffix}"
        child_id = new_uuid()
        row = {
            "id": child_id, "code": code, "name": name,
            "name_normalized": _normalized(name),
            "short_name": parent.get("short_name"),
            "description": parent.get("description"),
            "product_type": parent["product_type"], "lifecycle_status": "DRAFT",
            "category_id": parent.get("category_id"),
            "brand_id": parent.get("brand_id"),
            "parent_product_id": parent["id"],
            "species_id": parent.get("species_id"),
            "base_unit_id": parent["base_unit_id"],
            "created_by": parent.get("created_by"),
        }
        row.update({f: parent.get(f) for f in _CAP_FLAGS})
        self._master.create(row)
        for attribute_id, option_id in combo:
            self._variants.record_assignment(
                assignment_id=new_uuid(), product_id=child_id,
                attribute_id=attribute_id, option_id=option_id)
        _enqueue_outbox(self._conn, ProductEvents.PRODUCT_CREATED, child_id,
                        {"product_id": child_id, "code": code, "name": name,
                         "parent_product_id": parent["id"]})

    def _emit_generated(self, command, generated: int, skipped: int) -> None:
        _enqueue_outbox(self._conn, ProductEvents.PRODUCT_VARIANT_GENERATED,
                        command.parent_product_id,
                        {"parent_product_id": command.parent_product_id,
                         "generated": generated, "skipped": skipped},
                        operation_id=command.operation_id)


def _rollback(conn) -> None:
    rb = getattr(conn, "rollback", None)
    if rb is not None:
        rb()


def _enqueue_outbox(conn, event_name: str, entity_id: str, extra: dict,
                    *, operation_id: str | None = None) -> None:
    from backend.shared.ids import new_uuid
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    op_id = operation_id or new_uuid()
    payload = {"event_id": event_id, "event_name": event_name,
               "operation_id": op_id, "entity_id": entity_id}
    payload.update(extra)
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, op_id, entity_id, json.dumps(payload)))
