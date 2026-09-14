"""DeliveryRecordPresenter (PASS 6) — reentregas, cobros, liquidaciones, rutas,
seguimiento, incidencias y alertas.

No arma SQL: pide la página a `DeliveryRecordsQueryService` y le da formato. Las
etiquetas de estado viven aquí, y la página arma su filtro con ellas: el combo y
la columna no pueden llamar distinto al mismo estado.

El repartidor se muestra con id corto: `driver_id` sólo se valida como UUIDv7 y no
se cruza con ninguna tabla de personas, así que no hay de dónde leer un nombre.
"""

from __future__ import annotations

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


_FORMATO = {
    DeliveryRecord.REDELIVERIES: _fila_reentrega,
    DeliveryRecord.CASH_COLLECTIONS: _fila_cobro,
    DeliveryRecord.SETTLEMENTS: _fila_liquidacion,
    DeliveryRecord.ROUTES: _fila_ruta,
    DeliveryRecord.TRACKING: _fila_seguimiento,
    DeliveryRecord.INCIDENTS: _fila_incidencia,
    DeliveryRecord.ALERTS: _fila_alerta,
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
