"""Application service for product catalog state changes."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("spj.products.catalog")


class ProductCatalogService:
    """Canonical application service for product catalog mutations."""

    def __init__(self, db_conn: Any) -> None:
        self._db = db_conn

    def deactivate_product(self, product_id: int, operation_id: str, user_name: str = "") -> dict:
        """Soft-delete a product while preserving history."""
        return self._set_product_state(
            product_id=product_id,
            active=0,
            hidden=1,
            operation_id=operation_id,
            user_name=user_name,
            action="deactivate",
        )

    def restore_product(self, product_id: int, operation_id: str, user_name: str = "") -> dict:
        """Restore a soft-deleted product to the visible catalog."""
        return self._set_product_state(
            product_id=product_id,
            active=1,
            hidden=0,
            operation_id=operation_id,
            user_name=user_name,
            action="restore",
        )

    def set_product_active(self, product_id: int, active: bool, operation_id: str, user_name: str = "") -> dict:
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
        product_id: int,
        active: int,
        hidden: int,
        operation_id: str,
        user_name: str,
        action: str,
    ) -> dict:
        if int(product_id) <= 0:
            raise ValueError("product_id is required")
        if not operation_id:
            raise ValueError("operation_id is required")
        try:
            self._db.execute(
                "UPDATE productos SET oculto = ?, activo = ? WHERE id = ?",
                (int(hidden), int(active), int(product_id)),
            )
            self._db.commit()
        except Exception:
            logger.exception("Product catalog state change failed action=%s product_id=%s", action, product_id)
            try:
                self._db.rollback()
            except Exception:
                logger.exception("Product catalog rollback failed action=%s product_id=%s", action, product_id)
            raise
        return {
            "ok": True,
            "product_id": int(product_id),
            "active": int(active),
            "hidden": int(hidden),
            "operation_id": operation_id,
            "user_name": user_name,
            "action": action,
        }
