"""StockLocationResolver — Inventario dice DÓNDE entra la existencia producida.

Sucursal, almacén y ubicación son cosas distintas. Ningún contexto debe usar la
sucursal como si fuera una ubicación: cuando otro contexto (Procesamiento) pide
recibir existencia, pregunta aquí.

- La cuarentena NO es una ubicación en este modelo: es un ESTADO del saldo
  (QUARANTINED) en la misma ubicación, igual que `QuarantineStockUseCase` y
  `SetLotQualityStatusUseCase`. Liberar un lote lo pasa a DISPONIBLE ahí mismo.
- Ubicación de existencia: si el almacén ya guarda existencia DISPONIBLE de ese producto en
  una ubicación, ahí mismo — así lo producido cae en la misma fila de saldo que
  ya leen Ventas y Transferencias. Si no guarda ninguna, la ubicación técnica
  `AVAILABLE` del almacén.

Si la ubicación que corresponde no existe, falla con un error funcional claro.
No se inventa una ubicación ni se usa la sucursal en su lugar.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.inventory.use_cases.ensure_technical_locations import technical_code
from backend.domain.inventory.enums import InventoryStatus, TechnicalLocationType
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.infrastructure.db.repositories.inventory.inventory_balance_repository import (
    InventoryBalanceRepository,
)
from backend.infrastructure.db.repositories.inventory.warehouse_repository import (
    WarehouseRepository,
)


class StockLocationNotConfiguredError(InventoryDomainError):
    """El almacén no tiene la ubicación que la operación necesita."""


def _dec(value) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal("0")


class StockLocationResolver:
    def __init__(self, connection) -> None:
        self._warehouses = WarehouseRepository(connection)
        self._balances = InventoryBalanceRepository(connection)

    def technical_location(self, warehouse_id: str,
                           location_type: TechnicalLocationType) -> str:
        fila = self._warehouses.get_location_by_code(warehouse_id, technical_code(location_type))
        if fila is None or str(fila.get("status") or "ACTIVE") != "ACTIVE":
            raise StockLocationNotConfiguredError(
                f"El almacén no tiene la ubicación técnica «{location_type.value}» activa; "
                "configúrala en Inventario → Almacenes antes de producir.")
        return str(fila["id"])

    def available_location(self, *, product_id: str, branch_id: str,
                           warehouse_id: str) -> str:
        ubicaciones: dict[str, Decimal] = {}
        for saldo in self._balances.list_by_product_branch(product_id, branch_id):
            if saldo["warehouse_id"] != warehouse_id:
                continue
            if saldo["inventory_status"] != InventoryStatus.AVAILABLE.value:
                continue
            if not saldo["location_id"]:
                continue
            ubicaciones[saldo["location_id"]] = (
                ubicaciones.get(saldo["location_id"], Decimal("0")) + _dec(saldo["quantity"]))
        if ubicaciones:
            # La que más existencia guarda; empate por id para ser determinista.
            return sorted(ubicaciones.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        return self.technical_location(warehouse_id, TechnicalLocationType.AVAILABLE)
