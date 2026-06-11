from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.sales_commands import CreateSaleCommand
from backend.application.services.sales_application_service import SalesApplicationService
from backend.application.use_cases.create_sale_use_case import CreateSaleUseCase
from backend.shared.events.event_bus import InMemoryEventBus
from backend.shared.events.event_names import EventName
from core.use_cases.venta import ResultadoVenta


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
        operation_id="sale-op-1",
        branch_id="1",
        user_name="ana",
        items=(
            {"product_id": 10, "quantity": 2, "unit_price": 25.5, "name": "Taco", "is_composite": 0},
        ),
        payment={"payment_method": "Efectivo", "amount_paid": 60.0, "discount": 1.0},
        customer_id=7,
        notes="Venta POS Mostrador",
        reservation_id=3,
    )


def test_create_sale_use_case_delegates_to_sales_application_service_with_operation_id_event() -> None:
    bus = InMemoryEventBus()
    events = []
    bus.subscribe(EventName.SALE_COMPLETED, events.append)
    processor = SaleProcessorSpy(ResultadoVenta(ok=True, venta_id=99, folio="V-99", total=50.0, cambio=10.0, operation_id="sale-op-1"))
    use_case = CreateSaleUseCase(app_service=SalesApplicationService(sale_processor=processor, event_bus=bus))

    result = use_case.execute(_command())

    assert result.success is True
    assert result.operation_id == "sale-op-1"
    assert result.entity_id == "99"
    assert result.message == "SALE_COMPLETED"
    assert len(events) == 1
    assert events[0].operation_id == "sale-op-1"
    assert events[0].payload["folio"] == "V-99"

    items, datos_pago, sucursal_id, usuario = processor.calls[0]
    assert sucursal_id == 1
    assert usuario == "ana"
    assert items[0].producto_id == 10
    assert items[0].cantidad == 2
    assert datos_pago.operation_id == "sale-op-1"
    assert datos_pago.cliente_id == 7
    assert datos_pago.reserva_id == 3


def test_create_sale_use_case_blocks_empty_items_before_legacy_flow() -> None:
    processor = SaleProcessorSpy(ResultadoVenta(ok=True, venta_id=1, folio="V-1", operation_id="sale-op-empty"))
    use_case = CreateSaleUseCase(app_service=SalesApplicationService(sale_processor=processor))
    command = CreateSaleCommand(operation_id="sale-op-empty", branch_id="1", user_name="ana")

    result = use_case.execute(command)

    assert result.success is False
    assert result.message == "SALE_ITEMS_REQUIRED"
    assert processor.calls == []
