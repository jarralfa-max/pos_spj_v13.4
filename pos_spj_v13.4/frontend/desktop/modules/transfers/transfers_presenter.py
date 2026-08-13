"""Presentation orchestration; business calculations stay in QueryServices."""
from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.transfers.commands.transfer_request_commands import (
    CreateTransferRequestCommand, TransferRequestLineCommand,
)
from backend.application.transfers.queries.workspace_query_service import (
    TransferPageViewModel, TransfersWorkspaceQueryService,
)
from backend.domain.transfers.enums import TransferNodeType, TransferType
from backend.domain.transfers.exceptions import TransferError
from backend.domain.transfers.value_objects.transfer_node import TransferNode
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.transfers.presenter")


class TransfersPresenter:
    def __init__(self, query_service: TransfersWorkspaceQueryService, *,
                 connection=None, create_transfer_request_uc=None,
                 session_context=None) -> None:
        self._query_service = query_service
        self._connection = connection
        self._create_transfer_request_uc = create_transfer_request_uc
        self._session = session_context

    def load_page(self, page_id: str, search: str = "") -> TransferPageViewModel:
        return self._query_service.page(page_id=page_id, search=search)

    # session -----------------------------------------------------------------
    # Identidad NO se fabrica: sin sesión válida, el actor queda vacío y la
    # política real (fail-closed) niega la mutación aguas abajo.
    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", None) or "")

    # option providers ----------------------------------------------------------
    def branch_options(self):
        from frontend.desktop.components.search_selector import SearchOption
        try:
            options = self._query_service.list_active_branches()
        except Exception:
            logger.exception("TransfersPresenter.branch_options failed")
            return []
        return [SearchOption(id=o.id, label=o.name) for o in options]

    def product_options(self, query: str):
        from backend.application.products.queries.product_selection_query_service import (
            SearchTransferableProductsQueryService,
        )
        from frontend.desktop.components.search_selector import SearchOption
        if self._connection is None:
            return []
        try:
            results = SearchTransferableProductsQueryService(self._connection).search(query=query)
        except Exception:
            logger.exception("TransfersPresenter.product_options failed")
            return []
        return [SearchOption(id=r.product_id,
                             label=f"{r.code} — {r.name}" if r.code else r.name,
                             subtitle=r.short_name or "")
                for r in results]

    # commands ------------------------------------------------------------------
    def create_transfer_request(self, *, origin_branch_id: str, destination_branch_id: str,
                                product_id: str, quantity, weight="0") -> tuple[bool, str, dict]:
        """Crea una solicitud de transferencia sucursal→sucursal, línea única
        (INV-12: vertical slice — sólo Create; edición/aprobación quedan para
        una fase posterior)."""
        if self._create_transfer_request_uc is None:
            return False, "Creación de solicitudes no disponible.", {}
        origin = str(origin_branch_id or "").strip()
        destination = str(destination_branch_id or "").strip()
        pid = str(product_id or "").strip()
        if not origin or not destination:
            return False, "Selecciona sucursal de origen y destino.", {}
        if origin == destination:
            return False, "Origen y destino deben ser distintos.", {}
        if not pid:
            return False, "Selecciona un producto.", {}
        if not quantity or Decimal(str(quantity)) <= 0:
            return False, "Captura una cantidad mayor a cero.", {}
        unit_id = self._query_service.product_base_unit_id(pid)
        if not unit_id:
            return False, "El producto seleccionado no tiene unidad base configurada.", {}
        try:
            command = CreateTransferRequestCommand(
                requested_by_user_id=self._actor(), operation_id=new_uuid(),
                transfer_type=TransferType.BRANCH_TO_BRANCH,
                origin_node=TransferNode(TransferNodeType.BRANCH, branch_id=origin),
                destination_node=TransferNode(TransferNodeType.BRANCH, branch_id=destination),
                lines=(TransferRequestLineCommand(
                    product_id=pid, unit_id=unit_id, requested_quantity=Decimal(str(quantity)),
                    requested_weight=Decimal(str(weight or "0"))),))
            dto = self._create_transfer_request_uc.execute(command)
            return True, f"Solicitud {dto.transfer_number} creada.", {
                "transfer_id": dto.transfer_id, "transfer_number": dto.transfer_number}
        except TransferError as exc:
            return False, str(exc), {}
        except Exception:
            logger.exception("TransfersPresenter.create_transfer_request failed")
            return False, "Error inesperado; revise el log.", {}
