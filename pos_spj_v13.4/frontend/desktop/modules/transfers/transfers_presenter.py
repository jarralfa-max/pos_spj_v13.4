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
                 session_context=None, cycle_service=None,
                 credentials_verifier=None) -> None:
        self._query_service = query_service
        self._connection = connection
        self._create_transfer_request_uc = create_transfer_request_uc
        self._session = session_context
        #: `TransferCycleService` (integración Logística 32cfbf).
        self._cycle = cycle_service
        self._verify_credentials = credentials_verifier

    def load_page(self, page_id: str, search: str = "") -> TransferPageViewModel:
        return self._query_service.page(page_id=page_id, search=search)

    # session -----------------------------------------------------------------
    # Identidad NO se fabrica: sin sesión válida, el actor queda vacío y la
    # política real (fail-closed) niega la mutación aguas abajo.
    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", None) or "")

    # option providers ----------------------------------------------------------
    def branch_options(self):
        """Sucursales que este usuario PUEDE ver.

        Antes devolvía todas las activas sin filtrar, y el diálogo las pintaba
        en los combos de origen y destino: cualquiera que abriera Solicitudes
        veía el nombre de todas las sucursales. El orden correcto es
        `usuario -> permitidas -> consulta -> resultados`; filtrar aquí en la
        pantalla habría dejado la fuga intacta, porque el dato ya habría
        viajado.
        """
        from backend.application.security.branch_scope_query_service import (
            BranchScopeQueryService, BranchSearchQuery,
        )
        from frontend.desktop.components.search_selector import SearchOption
        if self._connection is None:
            return []
        try:
            options = BranchScopeQueryService(self._connection).search(
                BranchSearchQuery(allowed_for_user=self._actor(), page_size=200))
        except Exception:
            logger.exception("TransfersPresenter.branch_options failed")
            return []
        return [SearchOption(id=o.branch_id, label=o.name) for o in options]

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

    # ── ciclo completo (integración Logística 32cfbf) ─────────────────────────
    # La orquestación y la atomicidad viven en `TransferCycleService`
    # (aplicación); aquí sólo se pasa la identidad de la sesión.
    def can_run(self, action: str) -> bool:
        return self._cycle is not None and self._cycle.available(action)

    def detail(self, transfer_id: str) -> dict | None:
        if self._cycle is None:
            return None
        try:
            return self._cycle.detail(transfer_id)
        except Exception:
            logger.exception("TransfersPresenter.detail failed")
            return None

    def verify_verifier(self, usuario: str, clave: str) -> tuple[str | None, str]:
        if self._verify_credentials is None:
            return None, "La verificación de credenciales no está disponible."
        from backend.security.authentication.errors import AuthenticationFailedError
        from backend.security.sessions.errors import AccountLockedError
        try:
            return self._verify_credentials(username=usuario, password=clave), ""
        except (AuthenticationFailedError, AccountLockedError) as exc:
            return None, str(exc)

    def _run(self, action: str, *args, **kwargs):
        if not self.can_run(action):
            return False, "Acción no disponible en este equipo.", {}
        return getattr(self._cycle, action)(*args, **kwargs)

    def submit(self, transfer_id: str):
        return self._run("submit", transfer_id, self._actor())

    def approve(self, transfer_id: str):
        return self._run("approve", transfer_id, self._actor())

    def reject(self, transfer_id: str, reason: str):
        return self._run("reject", transfer_id, self._actor(), reason)

    def prepare(self, transfer_id: str):
        return self._run("prepare", transfer_id, self._actor())

    def dispatch(self, transfer_id: str, **fields):
        return self._run("dispatch", transfer_id, self._actor(), **fields)

    def receive(self, transfer_id: str, shipment_id: str, lines: list[dict]):
        return self._run("receive", transfer_id, self._actor(), shipment_id, lines)
