"""Diseñador de tickets y logos — lo que usa Configuración (comparativa de tickets
main ↔ ERP, 2026-10-16).

* `preview`: los BYTES del renderizador real, con el logo y el encabezado reales
  de la sucursal y datos de ejemplo, interpretados como imagen. Lo que se ve es
  lo que imprime la impresora (a su ancho de papel).
* `print_test`: el diseño que se está editando, a la impresora de la sucursal.
* logos: vista previa antes/después de quitar el fondo, carga a la biblioteca y
  asignación a la empresa o a una sucursal.

El guardado del diseño NO está aquí: es una versión de plantilla más
(`CreateNextTemplateVersionUseCase`), con su aprobación y activación.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.ticket_layout import layout_for_document_type, parse


@dataclass(frozen=True)
class TicketPreview:
    png: bytes
    paper_width_mm: int
    warnings: list[str] = field(default_factory=list)
    logo_source: str = "NONE"


class TicketDesignerService:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── diseño ───────────────────────────────────────────────────────────
    def validate(self, layout_json: str) -> str | None:
        try:
            parse(layout_json)
        except DocumentInvalidValueError as exc:
            return str(exc)
        return None

    def preview(self, layout_json: str, *, document_type: str, branch_id: str | None,
                paper_width_mm: int = 80) -> TicketPreview:
        from backend.application.queries.document_output.ticket_design_query_service import (
            TicketDesignQueryService,
        )
        from backend.infrastructure.printing.escpos_preview import render_preview
        from backend.infrastructure.printing.ticket_layout_renderer import render_ticket
        from backend.infrastructure.printing.ticket_sample import sample_payload

        layout = parse(layout_json)
        branding = TicketDesignQueryService(self._conn).branding(branch_id)
        rendered = render_ticket(layout, sample_payload(layout_for_document_type(document_type)),
                                 header=branding.header, paper_width_mm=paper_width_mm,
                                 logo_path=branding.logo_path)
        image = render_preview(rendered.data, paper_width_mm=rendered.paper_width_mm)
        buffer = io.BytesIO()
        image.image.save(buffer, "PNG")
        warnings = list(rendered.warnings)
        if image.unknown_commands:
            warnings.append("La vista previa no reconoce: " + ", ".join(image.unknown_commands))
        return TicketPreview(buffer.getvalue(), rendered.paper_width_mm, warnings,
                             branding.logo_source)

    def print_test(self, layout_json: str, *, document_type: str, branch_id: str | None,
                   workstation_id: str | None = None) -> list[str]:
        """Lanza `ReceiptPrintFailedError` con el motivo si no se pudo imprimir."""
        from backend.infrastructure.hardware.sales_ticket_printer import SalesTicketPrinter

        parse(layout_json)
        return SalesTicketPrinter(self._conn, branch_id=branch_id,
                                  workstation_id=workstation_id).print_test(
            layout_json, document_type=document_type)

    # ── logos ────────────────────────────────────────────────────────────
    def preview_logo(self, *, source_path: str, remove_background: bool, tolerance=None,
                     preview_dir: str):
        from backend.application.use_cases.configuracion.branding_use_cases import (
            PreviewLogoUseCase,
        )
        return PreviewLogoUseCase().execute(source_path=source_path,
                                            remove_background=remove_background,
                                            tolerance=tolerance, preview_dir=preview_dir)

    def import_logo(self, *, source_path: str, remove_background: bool, tolerance=None,
                    actor_user_id: str = ""):
        from backend.application.use_cases.configuracion.branding_use_cases import (
            ImportLogoUseCase,
        )
        return ImportLogoUseCase(self._conn).execute(
            source_path=source_path, remove_background=remove_background, tolerance=tolerance,
            actor_user_id=actor_user_id)

    def set_company_logo(self, asset_id: str | None) -> None:
        from backend.application.use_cases.configuracion.branding_use_cases import (
            SetCompanyLogoUseCase,
        )
        SetCompanyLogoUseCase(self._conn).execute(asset_id=asset_id)

    def set_branch_logo(self, branch_id: str, asset_id: str | None,
                        actor_user_id: str = "") -> None:
        from backend.application.use_cases.configuracion.branding_use_cases import (
            SetBranchLogoUseCase,
        )
        SetBranchLogoUseCase(self._conn).execute(branch_id=branch_id, asset_id=asset_id,
                                                 actor_user_id=actor_user_id)

    def logo_for(self, branch_id: str | None) -> tuple[str | None, str]:
        """(ruta del logo para impresión, de dónde viene: BRANCH/COMPANY/NONE)."""
        from backend.application.queries.document_output.ticket_design_query_service import (
            TicketDesignQueryService,
        )
        branding = TicketDesignQueryService(self._conn).branding(branch_id)
        return branding.logo_path, branding.logo_source
