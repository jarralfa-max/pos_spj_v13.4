"""DeliveryRecordPresenter (PASS 6) — reentregas, cobros, liquidaciones, rutas,
seguimiento, incidencias y alertas.

No arma SQL: pide la página a `DeliveryRecordsQueryService` y le da formato. Las
etiquetas de estado viven aquí, y la página arma su filtro con ellas: el combo y
la columna no pueden llamar distinto al mismo estado.

El repartidor se muestra con id corto: `driver_id` sólo se valida como UUIDv7 y no
se cruza con ninguna tabla de personas, así que no hay de dónde leer un nombre.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.orders_delivery.queries.delivery_records_query_service import (
    DeliveryRecord,
    DeliveryRecordsQueryService,
)
from frontend.desktop.modules.orders_delivery.presenters.orders_list_presenter import (
    OrdersTableModel,
)

DELIVERY_STATUS_LABELS: dict[str, str] = {
    "PENDING_ASSIGNMENT": "Sin repartidor", "ASSIGNED": "Asignada",
    "READY_TO_DISPATCH": "Lista para salir", "DISPATCHED": "Despachada",
    "IN_TRANSIT": "En camino", "ARRIVED": "En domicilio", "DELIVERY_ATTEMPT": "Entregando",
    "DELIVERED": "Entregada", "FAILED": "Fallida", "REDELIVERY_PENDING": "Reentrega pendiente",
    "RETURNING": "Regresando", "RETURNED_TO_BRANCH": "Devuelta a sucursal",
    "CANCELLED": "Cancelada", "CLOSED": "Cerrada",
}

AUDIT_ACTION_LABELS: dict[str, str] = {
    # eventos de pedido
    "ORDER_CREATED": "Pedido creado", "ORDER_CONFIRMED": "Pedido confirmado",
    "ORDER_SCHEDULED": "Pedido programado",
    "ORDER_SCHEDULE_ACTIVATED": "Programación activada",
    "ORDER_RESERVATION_REQUESTED": "Reserva solicitada",
    "ORDER_RESERVED": "Inventario reservado", "ORDER_RESERVATION_FAILED": "Reserva fallida",
    "ORDER_PREPARATION_STARTED": "Preparación iniciada",
    "ORDER_ITEM_WEIGHT_ADJUSTED": "Peso ajustado",
    "ORDER_CUSTOMER_APPROVAL_REQUIRED": "Aprobación del cliente requerida",
    "ORDER_CUSTOMER_ADJUSTMENT_ACCEPTED": "Ajuste aceptado por el cliente",
    "ORDER_CUSTOMER_ADJUSTMENT_REJECTED": "Ajuste rechazado por el cliente",
    "ORDER_SUBSTITUTION_PROPOSED": "Sustitución propuesta",
    "ORDER_SUBSTITUTION_ACCEPTED": "Sustitución aceptada",
    "ORDER_SUBSTITUTION_REJECTED": "Sustitución rechazada",
    "ORDER_READY": "Pedido listo", "ORDER_CANCELLED": "Pedido cancelado",
    "ORDER_CLOSED": "Pedido cerrado", "ORDER_REVERSED": "Pedido reversado",
    "ORDER_SALE_PROJECTED": "Venta generada", "ORDER_PAYMENT_RECORDED": "Pago registrado",
    "ORDER_REFUNDED": "Reembolso",
    # eventos de reparto
    "DELIVERY_JOB_CREATED": "Entrega creada", "DELIVERY_DRIVER_ASSIGNED": "Repartidor asignado",
    "DELIVERY_ROUTE_ASSIGNED": "Ruta asignada", "DELIVERY_DISPATCHED": "Entrega despachada",
    "DELIVERY_OUT_FOR_DELIVERY": "En camino", "DELIVERY_ARRIVED": "Llegada al domicilio",
    "DELIVERY_ATTEMPT_STARTED": "Intento de entrega iniciado",
    "DELIVERY_COMPLETED": "Entrega completada", "DELIVERY_FAILED": "Entrega fallida",
    "DELIVERY_REDELIVERY_REQUESTED": "Reentrega aprobada",
    "DELIVERY_RETURNED_TO_BRANCH": "Devuelta a sucursal",
    "DELIVERY_CANCELLED": "Entrega cancelada", "DELIVERY_CLOSED": "Entrega cerrada",
    "DELIVERY_CASH_COLLECTION_RECORDED": "Cobro registrado",
    "DRIVER_SETTLEMENT_CREATED": "Liquidación creada",
    "DRIVER_SETTLEMENT_DIFFERENCE_DETECTED": "Diferencia en liquidación",
    "DRIVER_SETTLEMENT_CLOSED": "Liquidación cerrada",
    # acciones sin evento
    "ORDER_DELIVERY_ADDRESS_SET": "Dirección de entrega registrada",
    "ORDER_RESCHEDULED": "Pedido reprogramado",
    "ORDER_INVENTORY_RELEASED": "Reserva liberada",
    "ORDER_PREPARATION_ASSIGNED": "Preparación asignada",
    "ORDER_LINE_PREPARED": "Cantidad preparada", "ORDER_PACKAGE_CREATED": "Paquete creado",
    "ORDER_PACKAGE_SEALED": "Paquete sellado", "ORDER_READY_FOR_PICKUP": "Listo para recoger",
    "ORDER_PICKUP_COMPLETED": "Entregado en mostrador",
    "DRIVER_PROFILE_REGISTERED": "Repartidor registrado",
    "DRIVER_ASSIGNMENT_PROPOSED": "Asignación propuesta",
    "DRIVER_ASSIGNMENT_REJECTED": "Asignación rechazada",
    "DELIVERY_ROUTE_CREATED": "Ruta creada", "DELIVERY_ROUTE_STOP_ADDED": "Parada agregada",
    "DELIVERY_ROUTE_PLANNED": "Ruta planificada",
    "REDELIVERY_REQUEST_CREATED": "Reentrega solicitada",
    "REDELIVERY_REQUEST_REJECTED": "Reentrega rechazada",
    "CASH_COLLECTION_REQUESTED": "Cobro solicitado",
    "DRIVER_SETTLEMENT_SUBMITTED_FOR_REVIEW": "Liquidación enviada a revisión",
    "DRIVER_SETTLEMENT_APPROVED": "Liquidación aprobada",
    "DELIVERY_ZONE_CREATED": "Zona creada", "DELIVERY_ZONE_UPDATED": "Zona actualizada",
    "DELIVERY_ZONE_ACTIVATED": "Zona activada", "DELIVERY_ZONE_DEACTIVATED": "Zona desactivada",
}

AUDIT_ENTITY_LABELS: dict[str, str] = {
    "CustomerOrder": "Pedido", "DeliveryJob": "Entrega", "DeliveryZone": "Zona",
    "DriverCashCollection": "Cobro", "DriverOperationalProfile": "Repartidor",
    "DeliveryAssignment": "Asignación", "OrderPackage": "Paquete",
    "RedeliveryRequest": "Reentrega", "DeliveryRoute": "Ruta",
    "DriverSettlement": "Liquidación",
}

STATUS_LABELS: dict[DeliveryRecord, dict[str, str]] = {
    DeliveryRecord.REDELIVERIES: {
        "PENDING": "Pendiente", "APPROVED": "Aprobada", "REJECTED": "Rechazada",
        "COMPLETED": "Completada", "CANCELLED": "Cancelada",
    },
    DeliveryRecord.CASH_COLLECTIONS: {
        "EXPECTED": "Por cobrar", "COLLECTED": "Cobrado",
        "PARTIALLY_COLLECTED": "Cobro parcial", "FAILED": "No cobrado",
        "PENDING_SETTLEMENT": "Por liquidar", "SETTLED": "Liquidado", "DISPUTED": "En disputa",
    },
    DeliveryRecord.SETTLEMENTS: {
        "OPEN": "Abierta", "PENDING_REVIEW": "En revisión", "BALANCED": "Cuadrada",
        "WITH_DIFFERENCE": "Con diferencia", "APPROVED": "Aprobada",
        "POSTED": "Contabilizada", "CLOSED": "Cerrada",
    },
    DeliveryRecord.ROUTES: {
        "DRAFT": "Borrador", "PLANNED": "Planificada", "ASSIGNED": "Asignada",
        "ACTIVE": "En curso", "COMPLETED": "Completada", "CANCELLED": "Cancelada",
    },
    DeliveryRecord.TRACKING: DELIVERY_STATUS_LABELS,
    # En incidencias el "estado" del filtro es el motivo de la falla.
    DeliveryRecord.INCIDENTS: {
        "CUSTOMER_NOT_HOME": "Cliente ausente", "ADDRESS_NOT_FOUND": "Domicilio no encontrado",
        "CUSTOMER_REJECTED": "Cliente rechazó", "PAYMENT_FAILED": "Pago fallido",
        "PRODUCT_DAMAGED": "Producto dañado", "TEMPERATURE_FAILURE": "Falla de temperatura",
        "SECURITY_RISK": "Riesgo de seguridad", "VEHICLE_FAILURE": "Falla del vehículo",
        "WRONG_ADDRESS": "Domicilio incorrecto", "CONTACT_UNAVAILABLE": "Contacto no disponible",
        "OTHER": "Otro",
    },
    DeliveryRecord.ALERTS: {"UNREAD": "Sin leer", "READ": "Leída"},
    DeliveryRecord.AUDIT: AUDIT_ACTION_LABELS,
}

PAYMENT_METHOD_LABELS: dict[str, str] = {
    "CASH": "Efectivo", "CARD_TERMINAL": "Terminal", "TRANSFER": "Transferencia",
    "PAYMENT_LINK": "Liga de pago", "MIXED": "Mixto", "CREDIT": "Crédito",
    "PREPAID": "Prepagado",
}


def _texto(valor, vacio: str = "—") -> str:
    return str(valor) if valor not in (None, "") else vacio


def _corto(valor, vacio: str = "—") -> str:
    return str(valor)[:8] if valor else vacio


def _fecha(valor) -> str:
    return str(valor)[:16].replace("T", " ") if valor else "—"


def _decimal(valor) -> Decimal:
    return Decimal(str(valor) if valor not in (None, "") else "0")


def _dinero(valor) -> str:
    return f"${_decimal(valor):,.2f}"


def _diferencia(cantidad: Decimal) -> str:
    signo = "+" if cantidad > 0 else "-" if cantidad < 0 else ""
    return f"{signo}${abs(cantidad):,.2f}"


def _fila_reentrega(fila: dict, estados: dict[str, str]) -> list[str]:
    return [
        _fecha(fila["created_at"]), _texto(fila["delivery_number"]),
        _texto(fila["order_number"]), _texto(fila["contact_name"]), _texto(fila["reason"]),
        _dinero(fila["additional_fee"]), estados.get(fila["status"], fila["status"]),
        _corto(fila["new_delivery_job_id"]),
    ]


def _fila_cobro(fila: dict, estados: dict[str, str]) -> list[str]:
    return [
        _texto(fila["delivery_number"]), _texto(fila["order_number"]),
        _texto(fila["contact_name"]), _corto(fila["driver_id"]),
        PAYMENT_METHOD_LABELS.get(fila["payment_method"], fila["payment_method"]),
        _dinero(fila["expected_amount"]), _dinero(fila["collected_amount"]),
        estados.get(fila["status"], fila["status"]), _fecha(fila["collected_at"]),
    ]


def _fila_liquidacion(fila: dict, estados: dict[str, str]) -> list[str]:
    esperado = _decimal(fila["expected_total"])
    entregado = _decimal(fila["collected_total"])
    return [
        _fecha(fila["created_at"]), _corto(fila["driver_id"]), str(fila["collection_count"]),
        _dinero(esperado), _dinero(entregado), _diferencia(entregado - esperado),
        estados.get(fila["status"], fila["status"]),
    ]


def _fila_ruta(fila: dict, estados: dict[str, str]) -> list[str]:
    return [
        _corto(fila["id"]), estados.get(fila["status"], fila["status"]),
        _corto(fila["assigned_driver_id"], "Sin asignar"), str(fila["stop_count"]),
        _fecha(fila["created_at"]), _fecha(fila["updated_at"]),
    ]


def _fila_seguimiento(fila: dict, estados: dict[str, str]) -> list[str]:
    return [
        _texto(fila["order_number"]), _texto(fila["contact_name"]),
        _texto(fila["contact_phone"]), _texto(fila["order_status"]),
        estados.get(fila["job_status"], fila["job_status"]),
        _corto(fila["assigned_driver_id"], "Sin asignar"),
        _fecha(fila["dispatched_at"]), _fecha(fila["estimated_arrival_at"]),
        # Una entrega termina entregada O fallida; nunca las dos.
        _fecha(fila["delivered_at"] or fila["failed_at"]), str(fila["attempts"]),
    ]


def _fila_incidencia(fila: dict, estados: dict[str, str]) -> list[str]:
    return [
        _fecha(fila["attempted_at"]), _texto(fila["delivery_number"]),
        _texto(fila["order_number"]), _texto(fila["contact_name"]),
        _corto(fila["driver_id"], "Sin asignar"),
        estados.get(fila["failure_reason"], _texto(fila["failure_reason"])),
        _texto(fila["notes"]),
        DELIVERY_STATUS_LABELS.get(fila["job_status"], fila["job_status"]),
    ]


def _fila_alerta(fila: dict, estados: dict[str, str]) -> list[str]:
    return [
        _fecha(fila["created_at"]), _texto(fila["title"]), _texto(fila["body"]),
        estados.get(fila["status"], fila["status"]), _fecha(fila["read_at"]),
    ]


def _resumen(valor_json) -> str:
    """El "después" de la auditoría en una línea: `clave: valor; …`."""
    try:
        datos = json.loads(valor_json) if valor_json else {}
    except ValueError:
        return _texto(valor_json)
    if not isinstance(datos, dict) or not datos:
        return "—"
    return "; ".join(f"{clave}: {valor}" for clave, valor in datos.items())


def _fila_auditoria(fila: dict, estados: dict[str, str]) -> list[str]:
    return [
        _fecha(fila["occurred_at"]), _corto(fila["actor"]),
        estados.get(fila["action"], fila["action"]),
        AUDIT_ENTITY_LABELS.get(fila["entity"], _texto(fila["entity"])),
        _corto(fila["entity_id"]), _resumen(fila["after"]),
    ]


_FORMATO = {
    DeliveryRecord.REDELIVERIES: _fila_reentrega,
    DeliveryRecord.CASH_COLLECTIONS: _fila_cobro,
    DeliveryRecord.SETTLEMENTS: _fila_liquidacion,
    DeliveryRecord.ROUTES: _fila_ruta,
    DeliveryRecord.TRACKING: _fila_seguimiento,
    DeliveryRecord.INCIDENTS: _fila_incidencia,
    DeliveryRecord.ALERTS: _fila_alerta,
    DeliveryRecord.AUDIT: _fila_auditoria,
}


class DeliveryRecordPresenter:
    def __init__(self, connection, *, branch_id: str, record: DeliveryRecord,
                 recipient_user_id: str | None = None, page_size: int = 50) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._record = DeliveryRecord(record)
        self._recipient_user_id = recipient_user_id
        self._page_size = page_size

    @property
    def record(self) -> DeliveryRecord:
        return self._record

    def rows(self, *, query: str = "", status: str | None = None,
             page: int = 0) -> OrdersTableModel:
        pagina = DeliveryRecordsQueryService(self._conn).list_records(
            self._branch_id, self._record, status=status, query=query, page=page,
            page_size=self._page_size, recipient_user_id=self._recipient_user_id)
        formato = _FORMATO[self._record]
        estados = STATUS_LABELS[self._record]
        return OrdersTableModel(
            rows=[formato(fila, estados) for fila in pagina.rows],
            row_ids=[fila["id"] for fila in pagina.rows], total=pagina.total)
