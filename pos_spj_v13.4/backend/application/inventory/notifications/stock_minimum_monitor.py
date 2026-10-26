"""Vigila el mínimo canónico por producto, sucursal y almacén.

La lectura de existencias proviene del ledger proyectado. La identidad del aviso
es el UUID de la regla: evita que una tienda silencie el faltante de otra.
La entrega usa la campana y la cola de WhatsApp existentes de Productos.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from backend.application.products.notifications.notification_service import (
    ProductNotificationService,
)
from backend.application.products.queries.product_settings_query import ProductSettingsQuery
from backend.domain.products.notification_enums import NotificationChannel, ProductAlertType
from backend.infrastructure.notifications.product_notification_gateway import (
    FanOutProductNotificationGateway,
)


class StockMinimumMonitor:
    def __init__(self, connection) -> None:
        self._conn = connection

    def run_once(self) -> int:
        settings_query = ProductSettingsQuery(self._conn)
        settings = settings_query.current()
        if not settings.alerts_enabled:
            return 0
        phones = settings.whatsapp_phones if settings.whatsapp_enabled else ()
        if not settings.alert_roles and not phones:
            return 0
        try:
            rules = self._conn.execute(
                "SELECT r.id, r.product_id, r.branch_id, r.warehouse_id, "
                "r.reorder_point, p.name, w.name FROM inventory_replenishment_rule r "
                "JOIN products p ON p.id=r.product_id "
                "JOIN warehouses w ON w.id=r.warehouse_id AND w.branch_id=r.branch_id "
                "WHERE r.active=1 AND r.reorder_point != '0' "
                "AND w.status='ACTIVE' AND p.lifecycle_status='ACTIVE'"
            ).fetchall()
        except sqlite3.OperationalError:
            return 0
        notifier = ProductNotificationService(
            self._conn, gateway=FanOutProductNotificationGateway(self._conn),
            throttle_seconds=24 * 60 * 60)
        total = 0
        for rule_id, product_id, branch_id, warehouse_id, threshold, product, warehouse in rules:
            users = settings_query.alert_user_ids(settings, branch_id=branch_id)
            rows = self._conn.execute(
                "SELECT quantity, reserved_quantity FROM inventory_balances "
                "WHERE product_id=? AND branch_id=? AND warehouse_id=? "
                "AND inventory_status='AVAILABLE'",
                (product_id, branch_id, warehouse_id),
            ).fetchall()
            available = sum((Decimal(str(q)) - Decimal(str(reserved))
                             for q, reserved in rows), Decimal("0"))
            minimum = Decimal(str(threshold))
            if available > minimum:
                continue
            alert = ProductAlertType.STOCK_OUT if available <= 0 else ProductAlertType.STOCK_LOW
            message = (f"Stock {'agotado' if available <= 0 else 'bajo'}: {product} "
                       f"en {warehouse}. Disponible {available}; mínimo {minimum}.")
            context = {"branch_id": branch_id, "warehouse_id": warehouse_id,
                       "product_id": product_id}
            if users:
                outcome = notifier.notify(
                    alert, entity_id=rule_id, message=message, recipients=users,
                    context=context, only_channels={NotificationChannel.IN_APP})
                total += outcome.sent
            if phones:
                outcome = notifier.notify(
                    alert, entity_id=rule_id, message=message, recipients=list(phones),
                    context=context, only_channels={NotificationChannel.WHATSAPP})
                total += outcome.sent
        self._conn.commit()
        return total
