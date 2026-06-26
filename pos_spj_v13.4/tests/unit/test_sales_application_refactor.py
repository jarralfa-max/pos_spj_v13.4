from __future__ import annotations

import uuid
from dataclasses import dataclass

from backend.application.commands.sales_commands import CreateSaleCommand
from backend.application.services.sales_application_service import SalesApplicationService
from backend.application.use_cases.create_sale_use_case import CreateSaleUseCase
from backend.shared.events.event_bus import InMemoryEventBus
from backend.shared.events.event_names import EventName
from core.use_cases.venta import ResultadoVenta

# Post-cut identity: every functional id is a UUIDv7 TEXT string (REGLA CERO).
BRANCH_ID = str(uuid.uuid4())
CUSTOMER_ID = str(uuid.uuid4())
RESERVATION_ID = str(uuid.uuid4())
PRODUCT_ID = str(uuid.uuid4())
SALE_ID = str(uuid.uuid4())
OPERATION_ID = str(uuid.uuid4())


@dataclass
class SaleProcessorSpy:
    result: ResultadoVenta

    def __post_init__(self) -> None:
        self.calls = []

    def ejecutar(self, items, datos_pago, sucursal_id, usuario):
        self.calls.append((items, datos_pago, sucursal_id, usuario))
        return self.result


def _command() -> CreateSaleCommand:
    return CreateSaleCommand(
        operation_id=OPERATION_ID,
        branch_id=BRANCH_ID,
        user_name="ana",
        items=(
            {"product_id": PRODUCT_ID, "quantity": 2, "unit_price": 25.5, "name": "Taco", "is_composite": 0},
        ),
        payment={"payment_method": "Efectivo", "amount_paid": 60.0, "discount": 1.0},
        customer_id=CUSTOMER_ID,
        notes="Venta POS Mostrador",
        reservation_id=RESERVATION_ID,
    )


def test_create_sale_use_case_delegates_with_uuid_identity_and_event() -> None:
    bus = InMemoryEventBus()
    events = []
    bus.subscribe(EventName.SALE_COMPLETED, events.append)
    processor = SaleProcessorSpy(
        ResultadoVenta(ok=True, venta_id=SALE_ID, folio="V-99", total=50.0, cambio=10.0, operation_id=OPERATION_ID)
    )
    use_case = CreateSaleUseCase(app_service=SalesApplicationService(sale_processor=processor, event_bus=bus))

    result = use_case.execute(_command())

    assert result.success is True
    assert result.operation_id == OPERATION_ID
    assert result.entity_id == SALE_ID                     # UUIDv7 sale identity, no int cast
    assert result.operation_id != result.entity_id          # rule 41
    assert result.message == "SALE_COMPLETED"
    assert len(events) == 1
    assert events[0].operation_id == OPERATION_ID
    assert events[0].entity_id == SALE_ID
    assert events[0].payload["sale_id"] == SALE_ID
    assert events[0].payload["folio"] == "V-99"

    # Identity flows through as the original UUID string — never int()-cast.
    items, datos_pago, sucursal_id, usuario = processor.calls[0]
    assert sucursal_id == BRANCH_ID and isinstance(sucursal_id, str)
    assert usuario == "ana"
    assert items[0].producto_id == PRODUCT_ID and isinstance(items[0].producto_id, str)
    assert items[0].cantidad == 2
    assert datos_pago.operation_id == OPERATION_ID
    assert datos_pago.cliente_id == CUSTOMER_ID
    assert datos_pago.reserva_id == RESERVATION_ID
    assert datos_pago.sucursal_id == BRANCH_ID


def test_create_sale_use_case_blocks_empty_items_before_legacy_flow() -> None:
    processor = SaleProcessorSpy(ResultadoVenta(ok=True, venta_id=SALE_ID, folio="V-1", operation_id="sale-op-empty"))
    use_case = CreateSaleUseCase(app_service=SalesApplicationService(sale_processor=processor))
    command = CreateSaleCommand(operation_id="sale-op-empty", branch_id=BRANCH_ID, user_name="ana")

    result = use_case.execute(command)

    assert result.success is False
    assert result.message == "SALE_ITEMS_REQUIRED"
    assert processor.calls == []
