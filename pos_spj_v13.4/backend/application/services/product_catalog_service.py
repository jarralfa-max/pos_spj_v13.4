"""Application service for product catalog state changes."""

from __future__ import annotations

import logging
from typing import Any

from backend.application.dto.use_case_result import UseCaseResult
from backend.domain.services.product_type_policy import ProductTypePolicy
from backend.shared.events.event_contracts import create_domain_event
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.products.catalog")


class ProductCatalogService:
    """Canonical application service for product catalog mutations."""

    def __init__(self, db_conn: Any = None, *, repository: Any = None, event_bus: Any = None) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._db = db_conn if db_conn is not None and repository is None else (
            getattr(repository, "_connection", None) if repository is not None else None
        )

    def create_product(self, command: Any) -> UseCaseResult:
        """Create a product through the canonical catalog service."""
        if not getattr(command, "name", ""):
            raise ValueError("product name is required")

        canonical_type = ProductTypePolicy.canonical_from_label(getattr(command, "product_type", "simple"))
        rules = ProductTypePolicy.rules_for(canonical_type)

        if self._repository is not None:
            product_data = {
                "name": command.name,
                "sku": getattr(command, "sku", None) or getattr(command, "code", None),
                "barcode": getattr(command, "barcode", ""),
                "category": command.category,
                "sale_price": float(getattr(command, "sale_price", None) or getattr(command, "price", 0)),
                "purchase_price": float(command.purchase_price or 0),
                "minimum_sale_price": float(command.minimum_sale_price or 0),
                "unit": command.unit,
                "minimum_stock": float(getattr(command, "minimum_stock", None) or getattr(command, "stock_minimum", 0)),
                "product_type": canonical_type,
                "is_composite": 1 if rules.is_composite else 0,
                "is_byproduct": 1 if rules.is_byproduct else 0,
                "image_path": getattr(command, "image_path", None),
                "active": 1 if getattr(command, "active", True) else 0,
            }
            try:
                product_id_str = self._repository.create(product_data)
                self._repository._connection.commit()
            except Exception:
                logger.exception("Product catalog create failed operation_id=%s", getattr(command, "operation_id", ""))
                try:
                    self._repository._connection.rollback()
                except Exception:
                    pass
                raise
        else:
            product_uuid = new_uuid()
            # Auto-generate SKU from uuid suffix when not provided
            sku = getattr(command, "sku", None) or getattr(command, "code", None)
            if not sku:
                sku = "SKU-" + product_uuid.replace("-", "")[:8].upper()
            cursor = self._db.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO productos (
                        id, nombre, codigo, codigo_barras, categoria, precio, precio_compra, precio_minimo_venta,
                        unidad, stock_minimo, tipo_producto, es_compuesto, es_subproducto,
                        imagen_path, existencia, oculto, activo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
                    """,
                    (
                        product_uuid,
                        command.name,
                        sku,
                        getattr(command, "barcode", ""),
                        command.category,
                        float(getattr(command, "sale_price", None) or getattr(command, "price", 0)),
                        float(command.purchase_price or 0),
                        float(command.minimum_sale_price or 0),
                        command.unit,
                        float(getattr(command, "minimum_stock", None) or getattr(command, "stock_minimum", 0)),
                        canonical_type,
                        1 if rules.is_composite else 0,
                        1 if rules.is_byproduct else 0,
                        getattr(command, "image_path", None),
                        1 if getattr(command, "active", True) else 0,
                    ),
                )
                self._db.commit()
                product_id_str = product_uuid
            except Exception:
                logger.exception("Product catalog create failed operation_id=%s", getattr(command, "operation_id", ""))
                try:
                    self._db.rollback()
                except Exception:
                    pass
                raise

        recipe_pending = rules.allows_recipe
        data = {
            "recipe_pending": recipe_pending,
            "product_type": canonical_type,
        }

        if self._event_bus is not None:
            try:
                event = create_domain_event(
                    event_name=EventName.PRODUCT_CREATED,
                    operation_id=command.operation_id,
                    entity_id=product_id_str,
                    branch_id=getattr(command, "branch_id", "") or "",
                    source_module="product_catalog",
                    user_name=getattr(command, "user_name", None) or "system",
                    payload={**data, "name": command.name},
                )
                self._event_bus.publish(event)
            except Exception:
                logger.exception("Failed to publish PRODUCT_CREATED event operation_id=%s", command.operation_id)

        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=product_id_str,
            message="PRODUCT_CREATED",
            data=data,
        )

    def update_product(self, command: Any) -> UseCaseResult:
        """Update a product through the canonical catalog service."""
        product_id = getattr(command, "product_id", None)
        if not product_id:
            raise ValueError("product_id is required")

        canonical_type = ProductTypePolicy.canonical_from_label(getattr(command, "product_type", "simple"))
        rules = ProductTypePolicy.rules_for(canonical_type)

        if self._repository is not None:
            product_data = {
                "name": command.name,
                "sku": getattr(command, "sku", None) or getattr(command, "code", None),
                "barcode": getattr(command, "barcode", ""),
                "category": command.category,
                "sale_price": float(getattr(command, "sale_price", None) or getattr(command, "price", 0)),
                "purchase_price": float(command.purchase_price or 0),
                "minimum_sale_price": float(command.minimum_sale_price or 0),
                "unit": command.unit,
                "minimum_stock": float(getattr(command, "minimum_stock", None) or getattr(command, "stock_minimum", 0)),
                "product_type": canonical_type,
                "is_composite": 1 if rules.is_composite else 0,
                "is_byproduct": 1 if rules.is_byproduct else 0,
                "image_path": getattr(command, "image_path", None),
                "active": 1 if getattr(command, "active", True) else 0,
            }
            try:
                self._repository.update(product_id, product_data)
                self._repository._connection.commit()
            except Exception:
                logger.exception("Product catalog update failed product_id=%s", product_id)
                try:
                    self._repository._connection.rollback()
                except Exception:
                    pass
                raise
        else:
            try:
                self._db.execute(
                    """
                    UPDATE productos SET
                        nombre=?, codigo=?, codigo_barras=?, categoria=?, precio=?, precio_compra=?, precio_minimo_venta=?,
                        unidad=?, stock_minimo=?, tipo_producto=?, es_compuesto=?, es_subproducto=?, activo=?,
                        imagen_path=?, ultima_actualizacion=datetime('now')
                    WHERE id=?
                    """,
                    (
                        command.name,
                        getattr(command, "sku", None) or getattr(command, "code", None),
                        getattr(command, "barcode", ""),
                        command.category,
                        float(getattr(command, "sale_price", None) or getattr(command, "price", 0)),
                        float(command.purchase_price or 0),
                        float(command.minimum_sale_price or 0),
                        command.unit,
                        float(getattr(command, "minimum_stock", None) or getattr(command, "stock_minimum", 0)),
                        canonical_type,
                        1 if rules.is_composite else 0,
                        1 if rules.is_byproduct else 0,
                        1 if getattr(command, "active", True) else 0,
                        getattr(command, "image_path", None),
                        product_id,
                    ),
                )
                self._db.commit()
            except Exception:
                logger.exception("Product catalog update failed product_id=%s", product_id)
                try:
                    self._db.rollback()
                except Exception:
                    pass
                raise

        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=str(product_id),
            message="PRODUCT_UPDATED",
            data={"product_type": canonical_type},
        )

    def deactivate_product(self, product_id: str, operation_id: str, user_name: str = "") -> dict:
        """Soft-delete a product while preserving history."""
        return self._set_product_state(
            product_id=product_id,
            active=0,
            hidden=1,
            operation_id=operation_id,
            user_name=user_name,
            action="deactivate",
        )

    def restore_product(self, product_id: str, operation_id: str, user_name: str = "") -> dict:
        """Restore a soft-deleted product to the visible catalog."""
        return self._set_product_state(
            product_id=product_id,
            active=1,
            hidden=0,
            operation_id=operation_id,
            user_name=user_name,
            action="restore",
        )

    def set_product_active(self, product_id: str, active: bool, operation_id: str, user_name: str = "") -> dict:
        """Toggle product POS visibility without deleting catalog history."""
        return self._set_product_state(
            product_id=product_id,
            active=1 if active else 0,
            hidden=0 if active else 1,
            operation_id=operation_id,
            user_name=user_name,
            action="activate" if active else "hide",
        )

    def _set_product_state(
        self,
        *,
        product_id: str,
        active: int,
        hidden: int,
        operation_id: str,
        user_name: str,
        action: str,
    ) -> dict:
        if not str(product_id or "").strip():
            raise ValueError("product_id is required")
        if not operation_id:
            raise ValueError("operation_id is required")
        db = self._db or (getattr(self._repository, "_connection", None) if self._repository else None)
        try:
            db.execute(
                "UPDATE productos SET oculto = ?, activo = ? WHERE id = ?",
                (int(hidden), int(active), product_id),
            )
            db.commit()
        except Exception:
            logger.exception("Product catalog state change failed action=%s product_id=%s", action, product_id)
            try:
                db.rollback()
            except Exception:
                pass
            raise
        return {
            "ok": True,
            "product_id": product_id,
            "active": int(active),
            "hidden": int(hidden),
            "operation_id": operation_id,
            "user_name": user_name,
            "action": action,
        }
