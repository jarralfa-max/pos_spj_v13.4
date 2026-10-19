"""Comparativa del ticket main ↔ ERP 968e0bc (2026-10-16) — contrato de aceptación.

«Por cada opción: guardar → activar → previsualizar → imprimir con igual
contenido en 58/80 mm → reimprimir con versión histórica.» Cada prueba mide
BYTES enviados a la impresora (interceptando el transporte), no la pantalla.

Decisiones del usuario: logo de empresa + sucursal opcional; QR = URL
configurable con {folio}; reimpresión = el original, marcado.
"""

from __future__ import annotations

import importlib
import json
import os
import sqlite3
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image, ImageDraw

from backend.application.queries.document_output.ticket_design_query_service import (
    TicketDesignQueryService,
)
from backend.application.use_cases.configuracion.branding_use_cases import (
    ImportLogoUseCase,
    SetBranchLogoUseCase,
    SetCompanyLogoUseCase,
)
from backend.application.use_cases.configuracion.document_template_use_cases import (
    ChangeTemplateVersionStatusUseCase,
    CreateDocumentTemplateUseCase,
    CreateNextTemplateVersionUseCase,
    TemplateVersionAction,
)
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.ticket_layout import (
    TicketBlock,
    default_layout,
    parse,
)
from backend.infrastructure.db.schema.branding_schema import create_branding_schema
from backend.infrastructure.media.branding_asset_storage import BrandingAssetStorage
from backend.infrastructure.printing import escpos
from backend.infrastructure.printing.escpos_preview import render_preview
from backend.infrastructure.printing.ticket_layout_renderer import render_ticket
from backend.infrastructure.printing.ticket_sample import sample_payload
from backend.shared.ids import new_uuid

_342 = importlib.import_module("migrations.standalone.342_ticket_design_branding")


@pytest.fixture
def conn(tmp_path):
    from backend.infrastructure.db.schema.document_output_schema import (
        create_document_output_schema,
    )
    from backend.infrastructure.db.schema.settings_schema import create_company_branch_profile_schema

    c = sqlite3.connect(str(tmp_path / "t.db"))
    create_document_output_schema(c)
    create_company_branch_profile_schema(c)
    create_branding_schema(c)
    c.commit()
    yield c
    c.close()


def _with(layout, **changes):
    """El diseño con bloques cambiados: {tipo: dict(enabled=, align=, options=)}."""
    blocks = []
    for b in layout.blocks:
        change = changes.get(b.type, {})
        blocks.append(TicketBlock(b.type, change.get("enabled", b.enabled),
                                  change.get("align", b.align),
                                  {**b.options, **change.get("options", {})}))
    return layout.with_blocks(blocks)


def _logo(path, *, transparent=True):
    image = Image.new("RGBA", (300, 120), (0, 0, 0, 0) if transparent else (40, 160, 40, 255))
    ImageDraw.Draw(image).rectangle((20, 20, 280, 100), fill=(200, 0, 0, 255))
    image.save(path)
    return str(path)


# ── el diseño (dominio) ───────────────────────────────────────────────────
class TestLayoutRules:
    def test_default_design_round_trips(self):
        layout = default_layout("SALE")
        assert parse(layout.to_json()) == layout

    @pytest.mark.parametrize("content", ["Productos, unidad, cantidad, costo", "{{items}}", ""])
    def test_free_text_is_not_a_design(self, content):
        with pytest.raises(DocumentInvalidValueError, match="diseñador"):
            parse(content)

    def test_unknown_or_repeated_block_is_rejected(self):
        data = json.loads(default_layout().to_json())
        data["blocks"].append({"type": "items"})
        with pytest.raises(DocumentInvalidValueError, match="se repite"):
            parse(json.dumps(data))
        data["blocks"][-1] = {"type": "ticket_number"}      # bloque de boleto en venta
        with pytest.raises(DocumentInvalidValueError, match="desconocido"):
            parse(json.dumps(data))

    def test_qr_needs_a_public_http_url(self):
        with pytest.raises(DocumentInvalidValueError, match="URL"):
            _with(default_layout(), qr={"enabled": True})
        with pytest.raises(DocumentInvalidValueError, match="http"):
            _with(default_layout(), qr={"enabled": True, "options": {"url": "ftp://x"}})
        with pytest.raises(DocumentInvalidValueError, match="cliente_email"):
            _with(default_layout(), qr={"enabled": True,
                                        "options": {"url": "https://a.mx/?e={cliente_email}"}})


# ── el renderizador: cada opción tiene efecto en BYTES ────────────────────
class TestRendererEffects:
    def test_hidden_block_is_not_printed_and_order_is_respected(self):
        layout = _with(default_layout(), payment={"enabled": False})
        data = render_ticket(layout, sample_payload()).data
        assert b"Forma de pago" not in data
        moved = list(layout.blocks)
        thanks = next(b for b in moved if b.type == "thanks")
        moved.remove(thanks)
        moved.insert(0, thanks)
        data = render_ticket(layout.with_blocks(moved), sample_payload()).data
        assert data.index(b"Gracias por su compra") < data.index(b"Pechuga")

    def test_logo_with_transparency_is_rasterized(self, tmp_path):
        layout = _with(default_layout(), logo={"enabled": True})
        rendered = render_ticket(layout, sample_payload(), logo_path=_logo(tmp_path / "l.png"))
        assert b"\x1dv0" in rendered.data and not rendered.warnings

    def test_missing_logo_prints_the_ticket_and_says_why(self):
        layout = _with(default_layout(), logo={"enabled": True})
        rendered = render_ticket(layout, sample_payload(), logo_path=None)
        assert b"\x1dv0" not in rendered.data and rendered.warnings
        assert b"TOTAL" in rendered.data

    @pytest.mark.parametrize("paper", [58, 80])
    def test_barcode_carries_the_commercial_folio(self, paper):
        layout = _with(default_layout(), barcode={"enabled": True})
        rendered = render_ticket(layout, sample_payload(), paper_width_mm=paper)
        dots = escpos.dots_for_paper_width(paper)
        expected = escpos.render_barcode("V-EJE-000001", max_width_dots=int(dots * 0.9),
                                         module_height=7.0)
        assert expected and expected in rendered.data

    def test_qr_encodes_the_configured_url_with_the_folio(self):
        layout = _with(default_layout(), qr={
            "enabled": True, "options": {"url": "https://spj.mx/factura?folio={folio}"}})
        rendered = render_ticket(layout, sample_payload(), paper_width_mm=80)
        expected = escpos.render_qr("https://spj.mx/factura?folio=V-EJE-000001",
                                    max_width_dots=int(576 * 0.6))
        assert expected and expected in rendered.data

    def test_without_graphics_library_the_qr_falls_back_to_text(self, monkeypatch):
        from backend.infrastructure.printing import ticket_layout_renderer as renderer
        monkeypatch.setattr(renderer, "render_qr", lambda *a, **k: b"")
        layout = _with(default_layout(), qr={
            "enabled": True, "options": {"url": "https://spj.mx/f?folio={folio}"}})
        rendered = render_ticket(layout, sample_payload())
        assert b"https://spj.mx/f?folio=V-EJE-000001" in rendered.data
        assert any("QR" in w for w in rendered.warnings)

    def test_message_limits_come_from_the_design(self, monkeypatch):
        from backend.infrastructure.integrations import sales_marketing_client as client
        layout = _with(default_layout(), messages={"options": {"max": {"LOYALTY": 0, "FOMO": 0,
                                                                        "CTA": 0}}})
        assert layout.message_limits() == {"LOYALTY": 0, "FOMO": 0, "CTA": 0}
        monkeypatch.setattr(client.SqliteMarketingCampaignRepository, "list_active",
                            lambda self: (_ for _ in ()).throw(AssertionError("no consultar")))
        assert client.SalesMarketingClient(None).select_ticket_messages(
            subtotal=1, total=1, has_customer=False, points_balance=None,
            max_per_category=layout.message_limits()) == ()

    @pytest.mark.parametrize("paper", [58, 80])
    def test_preview_reads_the_same_bytes(self, paper, tmp_path):
        layout = _with(default_layout(), logo={"enabled": True}, barcode={"enabled": True})
        rendered = render_ticket(layout, sample_payload(), paper_width_mm=paper,
                                 logo_path=_logo(tmp_path / "l.png"))
        preview = render_preview(rendered.data, paper_width_mm=paper)
        assert preview.unknown_commands == [] and preview.cut
        assert preview.image.width == escpos.dots_for_paper_width(paper) + 16

    def test_raffle_ticket_has_its_own_design_with_the_number(self):
        data = render_ticket(default_layout("RAFFLE"), sample_payload("RAFFLE")).data
        assert b"A-000123" in data and b"Gran sorteo de aniversario" in data
        assert b"Folio:" not in data and b"TOTAL" not in data


# ── plantillas: lo ACTIVO gobierna la impresión ───────────────────────────
def _activate(conn, version_id, approver="u-aprueba"):
    uc = ChangeTemplateVersionStatusUseCase(conn)
    uc.execute(version_id=version_id, action=TemplateVersionAction.SUBMIT_FOR_APPROVAL)
    uc.execute(version_id=version_id, action=TemplateVersionAction.APPROVE, actor_user_id=approver)
    uc.execute(version_id=version_id, action=TemplateVersionAction.ACTIVATE, actor_user_id=approver)


class TestTemplatesGovernPrinting:
    def test_free_text_cannot_be_saved_as_a_ticket_template(self, conn):
        with pytest.raises(DocumentInvalidValueError):
            CreateDocumentTemplateUseCase(conn).execute(
                document_type="SALE_TICKET", name="POS-01", module="ventas",
                content_format="ESC_POS", content="Productos, unidad, cantidad, costo",
                created_by_user_id="u1")

    def test_only_the_active_version_changes_the_printed_ticket(self, conn):
        _342.run(conn)
        design = TicketDesignQueryService(conn)
        seeded = design.active_layout("SALE_TICKET")
        assert seeded.template_version_id is not None
        custom = _with(default_layout(), thanks={"options": {"text": "Vuelve pronto"}})
        draft = CreateNextTemplateVersionUseCase(conn).execute(
            version_id=seeded.template_version_id, content=custom.to_json(),
            created_by_user_id="u-disena")
        # Un borrador no cambia nada.
        assert design.active_layout("SALE_TICKET").template_version_id == seeded.template_version_id
        _activate(conn, draft.id)
        active = design.active_layout("SALE_TICKET")
        assert active.template_version_id == draft.id
        assert b"Vuelve pronto" in render_ticket(active.layout, sample_payload()).data

    def test_one_active_ticket_design_per_type(self, conn):
        first, v1 = CreateDocumentTemplateUseCase(conn).execute(
            document_type="SALE_TICKET", name="A", module="ventas", content_format="ESC_POS",
            content=default_layout().to_json(), created_by_user_id="u1")
        second, v2 = CreateDocumentTemplateUseCase(conn).execute(
            document_type="SALE_TICKET", name="B", module="ventas", content_format="ESC_POS",
            content=default_layout().to_json(), created_by_user_id="u1")
        _activate(conn, v1.id)
        _activate(conn, v2.id)
        statuses = dict(conn.execute("SELECT id, status FROM document_template_versions"))
        assert statuses[v2.id] == "ACTIVE" and statuses[v1.id] == "INACTIVE"

    def test_migration_342_seeds_the_default_design_once(self, conn):
        _342.run(conn)
        _342.run(conn)
        rows = conn.execute("SELECT t.document_type, v.status FROM document_templates t"
                            " JOIN document_template_versions v ON v.template_id=t.id").fetchall()
        assert sorted(rows) == [("SALE_TICKET", "ACTIVE"), ("SWEEPSTAKES_TICKET", "ACTIVE")]


# ── logos: empresa + sucursal opcional ────────────────────────────────────
class TestBranding:
    def _company(self, conn):
        from backend.application.use_cases.configuracion.company_branch_use_cases import (
            SaveCompanyProfileUseCase,
        )
        SaveCompanyProfileUseCase(conn).execute(
            legal_name="SPJ SA", commercial_name="Pollería SPJ", default_currency="MXN",
            default_timezone="America/Mexico_City", default_locale="es-MX")

    def test_branch_logo_overrides_company_and_falls_back(self, conn, tmp_path):
        self._company(conn)
        storage = BrandingAssetStorage(tmp_path / "marca")
        company = ImportLogoUseCase(conn, storage).execute(
            source_path=_logo(tmp_path / "e.png"), remove_background=False)
        branch_logo = ImportLogoUseCase(conn, storage).execute(
            source_path=_logo(tmp_path / "s.png", transparent=False), remove_background=False)
        SetCompanyLogoUseCase(conn).execute(asset_id=company.id)
        branch = new_uuid()
        design = TicketDesignQueryService(conn)
        assert design.branding(branch).logo_path == company.print_path       # hereda
        SetBranchLogoUseCase(conn).execute(branch_id=branch, asset_id=branch_logo.id)
        assert design.branding(branch).logo_source == "BRANCH"
        SetBranchLogoUseCase(conn).execute(branch_id=branch, asset_id=None)
        assert design.branding(branch).logo_source == "COMPANY"

    def test_background_removal_keeps_the_original(self, conn, tmp_path):
        source = tmp_path / "fondo.png"
        image = Image.new("RGB", (200, 200), (230, 230, 230))
        ImageDraw.Draw(image).ellipse((50, 50, 150, 150), fill=(10, 10, 120))
        image.save(source)
        asset = ImportLogoUseCase(conn, BrandingAssetStorage(tmp_path / "marca")).execute(
            source_path=str(source), remove_background=True)
        assert os.path.isfile(asset.original_path) and os.path.isfile(asset.print_path)
        with Image.open(asset.original_path) as original:
            assert original.convert("RGB").getpixel((5, 5)) == (230, 230, 230)
        with Image.open(asset.print_path) as printed:
            assert printed.getpixel((5, 5)) >= 250            # el fondo es papel


# ── el impresor de Ventas: bytes reales, foto e histórico ─────────────────
class _Capture:
    def __init__(self):
        self.sent = []


@pytest.fixture
def capture(monkeypatch):
    from backend.infrastructure.printing import routed_printer
    cap = _Capture()
    monkeypatch.setattr(routed_printer, "resolve_routed_device",
                        lambda *a, **k: (SimpleNamespace(), SimpleNamespace(paper_profile="58mm")))
    monkeypatch.setattr(routed_printer, "send",
                        lambda device, profile, data, what="": cap.sent.append(data))
    return cap


class TestSalesPrinter:
    def test_print_ticket_uses_the_active_design_and_branding(self, conn, capture, tmp_path):
        from backend.infrastructure.hardware.sales_ticket_printer import SalesTicketPrinter
        _342.run(conn)
        version = TicketDesignQueryService(conn).active_layout("SALE_TICKET").template_version_id
        custom = _with(default_layout(), logo={"enabled": True},
                       thanks={"options": {"text": "Hasta la vista"}})
        draft = CreateNextTemplateVersionUseCase(conn).execute(
            version_id=version, content=custom.to_json(), created_by_user_id="u-disena")
        _activate(conn, draft.id)
        TestBranding()._company(conn)
        logo = ImportLogoUseCase(conn, BrandingAssetStorage(tmp_path / "m")).execute(
            source_path=_logo(tmp_path / "l.png"), remove_background=False)
        SetCompanyLogoUseCase(conn).execute(asset_id=logo.id)

        printer = SalesTicketPrinter(conn, branch_id=new_uuid())
        printer.print_ticket(sample_payload())

        data = capture.sent[-1]
        assert b"Hasta la vista" in data and b"\x1dv0" in data and b"Polleria SPJ" in data
        assert printer.last_warnings == []

    def test_raffle_ticket_prints_the_number_sweepstakes_sends(self, conn, capture):
        """Antes leía `folio`/`nombre_sorteo` y Sorteos manda `ticket_number`/
        `raffle_name`: el boleto salía sin número."""
        from backend.infrastructure.hardware.sales_ticket_printer import SalesTicketPrinter
        _342.run(conn)
        SalesTicketPrinter(conn).print_raffle_ticket({
            "raffle_name": "Sorteo navideño", "ticket_number": "B-0042", "prize": "Bici",
            "draw_date": "2026-12-24T12:00:00"})
        data = capture.sent[-1]
        assert b"B-0042" in data and b"Sorteo navideno" in data and b"Bici" in data
