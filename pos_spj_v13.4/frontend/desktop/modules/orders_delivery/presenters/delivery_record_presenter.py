"""DeliveryRecordPresenter (PASS 6) — reentregas, cobros, liquidaciones y rutas.

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


_FORMATO = {
    DeliveryRecord.REDELIVERIES: _fila_reentrega,
    DeliveryRecord.CASH_COLLECTIONS: _fila_cobro,
    DeliveryRecord.SETTLEMENTS: _fila_liquidacion,
    DeliveryRecord.ROUTES: _fila_ruta,
}


class DeliveryRecordPresenter:
    def __init__(self, connection, *, branch_id: str, record: DeliveryRecord,
                 page_size: int = 50) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._record = DeliveryRecord(record)
        self._page_size = page_size

    @property
    def record(self) -> DeliveryRecord:
        return self._record

    def rows(self, *, query: str = "", status: str | None = None,
             page: int = 0) -> OrdersTableModel:
        pagina = DeliveryRecordsQueryService(self._conn).list_records(
            self._branch_id, self._record, status=status, query=query, page=page,
            page_size=self._page_size)
        formato = _FORMATO[self._record]
        estados = STATUS_LABELS[self._record]
        return OrdersTableModel(
            rows=[formato(fila, estados) for fila in pagina.rows],
            row_ids=[fila["id"] for fila in pagina.rows], total=pagina.total)
