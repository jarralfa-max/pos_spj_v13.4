"""DeliveryActionDispatcher — single entry point for all delivery UI actions.

Both Kanban cards and the List detail panel call this dispatcher.
No action logic is duplicated between the two views.
"""
from __future__ import annotations

import logging
from typing import Any

from core.delivery.domain.value_objects import DeliveryAction, DeliveryStatus

logger = logging.getLogger("spj.delivery.application.action_dispatcher")


class DeliveryActionDispatcher:
    """Dispatches UI action requests to the appropriate use cases.

    All kwargs are forwarded to the use case. The caller (UI) never knows
    which use case runs — it only knows the action key.
    """

    def __init__(
        self,
        *,
        change_status_uc: Any,
        assign_driver_uc: Any,
        adjust_item_uc: Any,
        cancel_uc: Any | None = None,
        ticket_printer: Any | None = None,
        payment_link_service: Any | None = None,
        whatsapp_service: Any | None = None,
    ) -> None:
        self._change_status_uc = change_status_uc
        self._assign_driver_uc = assign_driver_uc
        self._adjust_item_uc = adjust_item_uc
        self._cancel_uc = cancel_uc
        self._ticket_printer = ticket_printer
        self._payment_link_service = payment_link_service
        self._whatsapp_service = whatsapp_service

    def execute(
        self,
        action: DeliveryAction,
        order_id: str,
        *,
        usuario: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Dispatch action to the correct use case.

        Args:
            action:   DeliveryAction enum value.
            order_id: Order identifier (UUID string — no int casts).
            usuario:  User performing the action.
            **kwargs: Action-specific parameters forwarded to use cases.

        Returns:
            Dict with at minimum {"ok": True/False} and any use case result.

        Raises:
            ValueError: If the action is not handled.
        """
        logger.debug(
            "dispatch: action=%s order_id=%s usuario=%s kwargs=%s",
            action, order_id, usuario, list(kwargs.keys()),
        )

        if action == DeliveryAction.START_PREPARATION:
            return self._dispatch_start_preparation(order_id, usuario=usuario, **kwargs)

        elif action == DeliveryAction.CONFIRM_PREPARATION:
            return self._dispatch_confirm_preparation(order_id, usuario=usuario, **kwargs)

        elif action == DeliveryAction.ADJUST_ITEM:
            return self._dispatch_adjust_item(order_id, usuario=usuario, **kwargs)

        elif action == DeliveryAction.ASSIGN_DRIVER:
            return self._dispatch_assign_driver(order_id, usuario=usuario, **kwargs)

        elif action == DeliveryAction.START_ROUTE:
            return self._dispatch_change_status(order_id, DeliveryStatus.IN_TRANSIT.value, usuario=usuario, **kwargs)

        elif action == DeliveryAction.COMPLETE_DELIVERY:
            return self._dispatch_change_status(order_id, DeliveryStatus.DELIVERED.value, usuario=usuario, **kwargs)

        elif action == DeliveryAction.CANCEL:
            return self._dispatch_cancel(order_id, usuario=usuario, **kwargs)

        elif action == DeliveryAction.SEND_PAYMENT_LINK:
            return self._dispatch_payment_link(order_id, usuario=usuario, **kwargs)

        elif action in (
            DeliveryAction.VIEW_DETAIL,
            DeliveryAction.PRINT_TICKET,
            DeliveryAction.RESEND_RECEIPT,
        ):
            return self._dispatch_read_only(action, order_id, usuario=usuario, **kwargs)

        else:
            raise ValueError(f"Unhandled delivery action: {action!r}")

    # ── Private dispatch methods ──────────────────────────────────────────────

    def _dispatch_start_preparation(
        self, order_id: str, *, usuario: str, **kwargs: Any
    ) -> dict[str, Any]:
        self._change_status_uc.execute(
            order_id,
            DeliveryStatus.PREPARING.value,
            usuario=usuario,
            observacion=kwargs.get("observacion", ""),
        )
        return {"ok": True, "action": "start_preparation"}

    def _dispatch_confirm_preparation(
        self, order_id: str, *, usuario: str, **kwargs: Any
    ) -> dict[str, Any]:
        # The actual next status (listo_entrega vs listo_envio) is determined
        # by the state machine inside ChangeDeliveryStatusUseCase based on
        # workflow_type / delivery_type stored on the order.
        # We pass the canonical "listo_envio" and let the UC resolve.
        # For counter orders the UC will set listo_entrega.
        # However for simplicity we pass a special sentinel and let
        # the service decide; or the UI passes the resolved status.
        target = kwargs.get("target_status", DeliveryStatus.READY_FOR_DISPATCH.value)
        self._change_status_uc.execute(
            order_id,
            target,
            usuario=usuario,
            observacion=kwargs.get("observacion", ""),
        )
        return {"ok": True, "action": "confirm_preparation"}

    def _dispatch_adjust_item(
        self, order_id: str, *, usuario: str, **kwargs: Any
    ) -> dict[str, Any]:
        item_id = kwargs.get("item_id")
        prepared_qty = kwargs.get("prepared_qty")
        if not item_id or prepared_qty is None:
            raise ValueError("adjust_item requires item_id and prepared_qty")
        self._adjust_item_uc.execute(
            order_id=order_id,
            item_id=item_id,
            prepared_qty=prepared_qty,
            prepared_by=usuario,
            adjustment_reason=kwargs.get("adjustment_reason", ""),
            unit=kwargs.get("unit", ""),
        )
        return {"ok": True, "action": "adjust_item"}

    def _dispatch_assign_driver(
        self, order_id: str, *, usuario: str, **kwargs: Any
    ) -> dict[str, Any]:
        driver_id = kwargs.get("driver_id")
        if not driver_id:
            raise ValueError("assign_driver requires driver_id")
        result = self._assign_driver_uc.execute(
            order_id,
            driver_id=driver_id,
            tiempo_estimado=str(kwargs.get("tiempo_estimado") or ""),
            notas=kwargs.get("notas") or "",
            usuario=usuario,
        )
        return {"ok": True, "action": "assign_driver", **result}

    def _dispatch_change_status(
        self, order_id: str, target_status: str, *, usuario: str, **kwargs: Any
    ) -> dict[str, Any]:
        self._change_status_uc.execute(
            order_id,
            target_status,
            usuario=usuario,
            responsable=kwargs.get("responsable", usuario if target_status == DeliveryStatus.DELIVERED.value else ""),
            observacion=kwargs.get("observacion", ""),
            pago_metodo=kwargs.get("pago_metodo", ""),
            pago_monto=float(kwargs.get("pago_monto") or 0),
        )
        return {"ok": True, "action": target_status}

    def _dispatch_cancel(
        self, order_id: str, *, usuario: str, **kwargs: Any
    ) -> dict[str, Any]:
        if self._cancel_uc is not None:
            self._cancel_uc.execute(
                order_id,
                usuario=usuario,
                motivo=kwargs.get("motivo", ""),
            )
        else:
            self._change_status_uc.execute(
                order_id,
                DeliveryStatus.CANCELLED.value,
                usuario=usuario,
                observacion=kwargs.get("motivo", ""),
            )
        return {"ok": True, "action": "cancel"}

    def _dispatch_payment_link(
        self, order_id: str, *, usuario: str, **kwargs: Any
    ) -> dict[str, Any]:
        if self._payment_link_service is not None:
            link = self._payment_link_service.create_link(order_id=order_id)
            return {"ok": True, "action": "send_payment_link", "link": link}
        return {"ok": False, "action": "send_payment_link", "reason": "no_payment_service"}

    def _dispatch_read_only(
        self, action: DeliveryAction, order_id: str, *, usuario: str, **kwargs: Any
    ) -> dict[str, Any]:
        if action == DeliveryAction.PRINT_TICKET and self._ticket_printer is not None:
            self._ticket_printer.print_both(order_id)
        elif action == DeliveryAction.RESEND_RECEIPT and self._whatsapp_service is not None:
            self._whatsapp_service.resend_receipt(order_id=order_id)
        return {"ok": True, "action": action.value}
