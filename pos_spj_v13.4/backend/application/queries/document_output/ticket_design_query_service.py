"""Qué diseño y qué marca lleva un ticket impreso (comparativa main ↔ ERP, 2026-10-16).

* `active_layout(document_type)`: el diseño de la versión ACTIVA de la plantilla
  de ese tipo y su id — el que de verdad se imprime y el que se anota en el
  `PrintJob`. Sin versión activa (o con un contenido que no es diseño), el
  diseño por omisión e id None: el ticket nunca deja de imprimirse por esto.
* `branding(branch_id)`: encabezado (empresa, sucursal, dirección, teléfono,
  encabezado y pie de la sucursal) y la ruta del logo para impresión — el de la
  sucursal si tiene uno, si no el de la empresa.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.ticket_layout import (
    TicketLayout,
    default_layout,
    layout_for_document_type,
    parse,
)

logger = logging.getLogger("spj.document_output.ticket_design")


@dataclass(frozen=True)
class ActiveTicketLayout:
    layout: TicketLayout
    template_version_id: str | None
    problem: str | None = None


@dataclass(frozen=True)
class TicketBranding:
    header: dict
    logo_path: str | None
    logo_source: str          # "BRANCH" | "COMPANY" | "NONE"


class TicketDesignQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def active_layout(self, document_type: str) -> ActiveTicketLayout:
        kind = layout_for_document_type(document_type)
        try:
            row = self._conn.execute(
                "SELECT v.id, v.content FROM document_template_versions v"
                " JOIN document_templates t ON t.id = v.template_id"
                " WHERE t.document_type=? AND t.active=1 AND v.status='ACTIVE'"
                " ORDER BY v.updated_at DESC, v.version DESC LIMIT 1", (document_type,)).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row is None:
            return ActiveTicketLayout(default_layout(kind), None)
        try:
            layout = parse(row[1])
        except DocumentInvalidValueError as exc:
            # Una versión activa con contenido viejo (texto libre): se imprime el
            # diseño por omisión y se avisa, nunca un ticket vacío.
            logger.warning("Plantilla activa %s no es un diseño de ticket: %s", row[0], exc)
            return ActiveTicketLayout(default_layout(kind), None, str(exc))
        if layout.kind != kind:
            return ActiveTicketLayout(default_layout(kind), None,
                                      "La plantilla activa es de otro tipo de ticket")
        return ActiveTicketLayout(layout, row[0])

    def branding(self, branch_id: str | None) -> TicketBranding:
        header: dict = {}
        company_logo = branch_logo = None
        try:
            empresa = self._conn.execute(
                "SELECT commercial_name, legal_name, logo_asset_id FROM company_profiles"
                " WHERE active=1 LIMIT 1").fetchone()
            if empresa:
                header["company_name"] = (empresa[0] or empresa[1] or "").strip()
                company_logo = empresa[2]
            if branch_id:
                sucursal = self._conn.execute(
                    "SELECT name, address, phone, ticket_header, ticket_footer"
                    " FROM branch_profiles WHERE branch_id=?", (branch_id,)).fetchone()
                if sucursal:
                    header.update({
                        "branch_name": sucursal[0] or "", "address": sucursal[1] or "",
                        "phone": sucursal[2] or "", "header_text": sucursal[3] or "",
                        "footer_text": sucursal[4] or ""})
        except sqlite3.OperationalError:
            logger.info("Sin perfiles de empresa/sucursal: ticket sin encabezado")
        if branch_id:
            try:
                fila = self._conn.execute(
                    "SELECT logo_asset_id FROM branch_branding WHERE branch_id=?",
                    (branch_id,)).fetchone()
                branch_logo = fila[0] if fila else None
            except sqlite3.OperationalError:
                branch_logo = None
        for source, asset_id in (("BRANCH", branch_logo), ("COMPANY", company_logo)):
            path = self._print_path(asset_id)
            if path:
                return TicketBranding(header, path, source)
        return TicketBranding(header, None, "NONE")

    def _print_path(self, asset_id: str | None) -> str | None:
        if not asset_id:
            return None
        try:
            row = self._conn.execute("SELECT print_path FROM branding_assets WHERE id=?",
                                     (asset_id,)).fetchone()
        except sqlite3.OperationalError:
            return None
        import os
        return row[0] if row and row[0] and os.path.isfile(row[0]) else None
