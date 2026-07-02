from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from core.services.notification_sound_service import NotificationSoundService


class DesktopNotificationService:
    """Central ERP desktop notification service with dedupe + severity."""

    def __init__(self, db, sound_service: Optional[NotificationSoundService] = None):
        self.db = db
        self.sound_service = sound_service or NotificationSoundService()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        pass  # Plan B born-clean: schema canónico en migrations/ (DDL removido)
        pass  # Plan B born-clean: schema canónico en migrations/ (DDL removido)
        self.db.commit()

    def create_notification(
        self,
        *,
        branch_id: int,
        title: str,
        message: str,
        dedupe_key: str,
        severity: str = "info",
        tipo: str = "pedido_whatsapp_nuevo",
        data: Optional[Dict[str, Any]] = None,
        empleado_id: Optional[int] = None,
    ) -> bool:
        if dedupe_key:
            row = self.db.execute("SELECT 1 FROM notification_inbox WHERE dedupe_key=? LIMIT 1", (dedupe_key,)).fetchone()
            if row:
                return False

        from backend.shared.ids import new_uuid
        self.db.execute(
            """
            INSERT INTO notification_inbox
            (id, empleado_id, tipo, titulo, cuerpo, datos, sucursal_id, dedupe_key, severity, leido, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
            """,
            (
                new_uuid(),
                empleado_id,
                tipo,
                title,
                message,
                json.dumps(data or {}, ensure_ascii=False, default=str),
                str(branch_id),
                dedupe_key,
                severity,
            ),
        )
        self.db.commit()
        self.sound_service.play_for_notification(dedupe_key=dedupe_key, severity=severity)
        return True

    def notify_new_order(self, *, branch_id: int, sale_id: int, folio: str, total: float) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Nuevo pedido WhatsApp",
            message=f"Folio {folio} · Total ${float(total):.2f}",
            dedupe_key=f"new_order:{sale_id}",
            severity="info",
            tipo="pedido_whatsapp_nuevo",
            data={"sale_id": sale_id, "folio": folio, "total": total, "created_at": datetime.now().isoformat()},
        )

    def notify_scheduled_order(self, *, branch_id: int, sale_id: int, folio: str, scheduled_at: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido programado",
            message=f"Folio {folio} · Fecha programada: {scheduled_at}",
            dedupe_key=f"scheduled_order:{sale_id}",
            severity="warning",
            tipo="pedido_whatsapp_programado",
            data={"sale_id": sale_id, "folio": folio, "scheduled_at": scheduled_at},
        )

    def get_unread_notifications(self, *, branch_id: int, limit: int = 50):
        rows = self.db.execute(
            """
            SELECT id, tipo, titulo, cuerpo, datos, sucursal_id, dedupe_key, severity, created_at
            FROM notification_inbox
            WHERE COALESCE(sucursal_id,1)=? AND COALESCE(leido,0)=0
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(branch_id), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_as_read(self, *, notification_id: str) -> None:
        self.db.execute(
            "UPDATE notification_inbox SET leido=1, leido_at=datetime('now') WHERE id=?",
            (str(notification_id),),
        )
        self.db.commit()

    def notify_quote_converted(self, *, branch_id: int, quote_id: int, sale_id: int, folio: str, total: float) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Cotización aceptada",
            message=f"Cotización #{quote_id} convertida a venta {folio} · Total ${float(total):.2f}",
            dedupe_key=f"quote_converted:{quote_id}:{sale_id}",
            severity="success",
            tipo="cotizacion_convertida",
            data={"quote_id": quote_id, "sale_id": sale_id, "folio": folio, "total": total},
        )

    def notify_order_cancelled(self, *, branch_id: int, sale_id: int, folio: str, reason: str = "") -> bool:
        reason_txt = f" Motivo: {reason}" if reason else ""
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido cancelado",
            message=f"Pedido {folio} cancelado.{reason_txt}",
            dedupe_key=f"order_cancelled:{sale_id}",
            severity="critical",
            tipo="pedido_cancelado",
            data={"sale_id": sale_id, "folio": folio, "reason": reason},
        )

    def notify_adjustment_required(self, *, branch_id: int, delivery_order_id: int, item_id: int, folio: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Ajuste pendiente de autorización",
            message=f"Pedido {folio}: el ajuste del item {item_id} requiere respuesta del cliente.",
            dedupe_key=f"adjustment_required:{delivery_order_id}:{item_id}",
            severity="warning",
            tipo="ajuste_pendiente",
            data={"delivery_order_id": delivery_order_id, "item_id": item_id, "folio": folio},
        )

    def notify_adjustment_accepted(self, *, branch_id: int, delivery_order_id: int, item_id: int, folio: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Cliente aceptó ajuste",
            message=f"Pedido {folio}: ajuste del item {item_id} aceptado por el cliente.",
            dedupe_key=f"adjustment_accepted:{delivery_order_id}:{item_id}",
            severity="success",
            tipo="ajuste_aceptado",
            data={"delivery_order_id": delivery_order_id, "item_id": item_id, "folio": folio},
        )

    def notify_adjustment_rejected(self, *, branch_id: int, delivery_order_id: int, item_id: int, folio: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Cliente rechazó ajuste",
            message=f"Pedido {folio}: ajuste del item {item_id} rechazado por el cliente.",
            dedupe_key=f"adjustment_rejected:{delivery_order_id}:{item_id}",
            severity="warning",
            tipo="ajuste_rechazado",
            data={"delivery_order_id": delivery_order_id, "item_id": item_id, "folio": folio},
        )

    def notify_advance_paid(self, *, branch_id: int, sale_id: int, folio: str, amount: float) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Anticipo pagado",
            message=f"Pedido {folio}: anticipo recibido por ${float(amount):.2f}.",
            dedupe_key=f"advance_paid:{sale_id}",
            severity="success",
            tipo="anticipo_pagado",
            data={"sale_id": sale_id, "folio": folio, "amount": amount},
        )

    def notify_order_ready_counter(self, *, branch_id: int, sale_id: int, folio: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido listo para mostrador",
            message=f"Pedido {folio} listo para entrega en mostrador.",
            dedupe_key=f"ready_counter:{sale_id}",
            severity="info",
            tipo="pedido_listo_mostrador",
            data={"sale_id": sale_id, "folio": folio, "workflow_type": "counter"},
        )

    def notify_order_ready_delivery(self, *, branch_id: int, sale_id: int, folio: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido listo para reparto",
            message=f"Pedido {folio} listo para salida a ruta.",
            dedupe_key=f"ready_delivery:{sale_id}",
            severity="info",
            tipo="pedido_listo_reparto",
            data={"sale_id": sale_id, "folio": folio, "workflow_type": "delivery"},
        )

    def notify_scheduled_order_due_soon(self, *, branch_id: int, sale_id: int, folio: str, scheduled_at: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido programado próximo",
            message=f"Pedido {folio} programado para {scheduled_at}.",
            dedupe_key=f"scheduled_due_soon:{sale_id}",
            severity="warning",
            tipo="pedido_programado_proximo",
            data={"sale_id": sale_id, "folio": folio, "scheduled_at": scheduled_at},
        )

    def notify_quote_created(self, *, branch_id: int, quote_id: int, folio: str, total: float) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Nueva cotización WhatsApp",
            message=f"Cotización {folio} generada por ${float(total):.2f}.",
            dedupe_key=f"quote_created:{quote_id}",
            severity="info",
            tipo="cotizacion_creada",
            data={"quote_id": quote_id, "folio": folio, "total": total},
        )

    def notify_order_delayed(self, *, branch_id: int, sale_id: int, folio: str, reason: str = "") -> bool:
        reason_txt = f" Motivo: {reason}" if reason else ""
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido retrasado",
            message=f"Pedido {folio} presenta retraso.{reason_txt}",
            dedupe_key=f"order_delayed:{sale_id}",
            severity="warning",
            tipo="pedido_retrasado",
            data={"sale_id": sale_id, "folio": folio, "reason": reason},
        )

    def notify_order_cancelled_by_customer(self, *, branch_id: int, sale_id: int, folio: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido cancelado por cliente",
            message=f"Pedido {folio} cancelado por el cliente.",
            dedupe_key=f"order_cancelled_customer:{sale_id}",
            severity="critical",
            tipo="pedido_cancelado_cliente",
            data={"sale_id": sale_id, "folio": folio},
        )

    def notify_quote_rejected(self, *, branch_id: int, quote_id: int, folio: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Cotización rechazada",
            message=f"Cotización {folio} fue rechazada por el cliente.",
            dedupe_key=f"quote_rejected:{quote_id}",
            severity="warning",
            tipo="cotizacion_rechazada",
            data={"quote_id": quote_id, "folio": folio},
        )

    def notify_order_in_route(self, *, branch_id: int, sale_id: int, folio: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido en reparto",
            message=f"Pedido {folio} salió a ruta de reparto.",
            dedupe_key=f"order_in_route:{sale_id}",
            severity="info",
            tipo="pedido_en_reparto",
            data={"sale_id": sale_id, "folio": folio, "status": "out_for_delivery"},
        )

    def notify_order_delivered(self, *, branch_id: int, sale_id: int, folio: str) -> bool:
        return self.create_notification(
            branch_id=branch_id,
            title="Pedido entregado",
            message=f"Pedido {folio} marcado como entregado.",
            dedupe_key=f"order_delivered:{sale_id}",
            severity="success",
            tipo="pedido_entregado",
            data={"sale_id": sale_id, "folio": folio, "status": "delivered"},
        )
