"""Contrato de lectura de Compras sobre el maestro canónico de proveedores."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from backend.application.suppliers.queries.supplier_search_query_service import (
    INACTIVE_STATUSES as _INACTIVE_STATUSES,
    SupplierDirectorySearchQueryService,
)


@dataclass(frozen=True, slots=True)
class SupplierEligibility:
    supplier_id: str
    active: bool
    purchasing_enabled: bool
    financially_blocked: bool


class SupplierDirectoryQueryService:
    """Elegibilidad del proveedor para comprar — sobre el MAESTRO CANÓNICO.

    LEÍA `proveedores`, la tabla heredada. Era la otra mitad del mismo problema
    que el buscador: aunque el selector ofreciera un proveedor canónico, esta
    puerta lo rechazaba con "El proveedor canónico no existe", porque miraba una
    tabla en la que ese proveedor nunca estuvo. Buscador y puerta tenían que
    moverse juntos, y por eso comparten AHORA la misma definición de
    "comprable" (`is_purchasable`): un selector que ofrece lo que la puerta
    rechaza hace perder el trabajo justo al final, con la compra ya capturada.

    Las dos marcas heredadas (`compras_habilitadas`, `bloqueado_financiero`) se
    conservan en el modelo canónico como filas de `supplier_blocks`; la
    migración 263 las tradujo al copiar, para no desbloquear a nadie en silencio.
    """

    def __init__(self, connection) -> None:
        self._connection = connection
        self._suppliers = SupplierDirectorySearchQueryService(connection)

    def get_eligibility(self, supplier_id: str) -> SupplierEligibility | None:
        try:
            if not self._suppliers.exists(supplier_id):
                return None
            comprable = self._suppliers.is_purchasable(supplier_id)
            row = self._connection.execute(
                "SELECT status FROM supplier_master WHERE id=?", (supplier_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            # Sin el maestro (la 119 no corrió) no se puede afirmar nada sobre
            # la elegibilidad. Devolver None hace que `require_eligible` falle
            # ruidosamente, que es lo correcto: inventar que sí es elegible
            # dejaría pasar compras a proveedores que nadie pudo comprobar.
            return None
        estado = str((row[0] if row else "") or "")
        return SupplierEligibility(
            supplier_id=str(supplier_id),
            active=estado not in _INACTIVE_STATUSES,
            # El maestro no separa "compras deshabilitadas" de "bloqueo
            # financiero" con dos columnas: los distingue por tipo de bloqueo.
            # `is_purchasable` ya evalúa ambos, así que aquí se proyecta la
            # misma respuesta en los dos campos en vez de fingir un detalle que
            # esta consulta no resuelve.
            purchasing_enabled=comprable,
            financially_blocked=not comprable and estado == "ACTIVE")

    def require_eligible(self, supplier_id: str) -> None:
        from backend.domain.procurement.exceptions import SupplierNotEligibleError

        eligibility = self.get_eligibility(supplier_id)
        if eligibility is None:
            raise SupplierNotEligibleError("El proveedor canónico no existe")
        if (not eligibility.active or not eligibility.purchasing_enabled
                or eligibility.financially_blocked):
            raise SupplierNotEligibleError("El proveedor no está habilitado para compras")
