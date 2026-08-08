from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "frontend" / "desktop" / "modules" / "purchasing"


def source(name: str) -> str:
    return (MODULE / name).read_text(encoding="utf-8")


def test_purchasing_root_is_sidebar_shell_not_tab_widget():
    shell = source("purchasing_module_shell.py")
    compatibility = source("enterprise_view.py")
    assert "class PurchasingModuleShell" in shell
    assert "SideNav" in shell and "QStackedWidget" in shell
    assert "ContextFilters" in shell and "AlertsBar" in shell and "KPIBar" in shell
    assert "Sin almacén seleccionado" not in shell
    assert "purchasingWarehouseNotice" in shell
    assert "QTabWidget" not in shell + compatibility


def test_shell_exposes_only_implemented_permission_gated_routes():
    shell = source("purchasing_module_shell.py")
    navigation = source("navigation.py")
    for label in (
        "Resumen", "Solicitudes", "Cotizaciones", "Órdenes de compra", "Nueva compra",
        "Historial", "COMPRA EN ORIGEN", "RECEPCIONES", "FACTURACIÓN",
    ):
        assert label in navigation
    for unfinished in (
        "Adjudicaciones", "Compras móviles",
        "Contenedores asignados", "Políticas y tolerancias",
    ):
        assert unfinished not in shell + navigation
    assert "visible_routes(capabilities)" in shell


def test_dashboard_has_quick_actions_and_clickable_implemented_flow():
    dashboard = source("pages/procurement_dashboard_page.py")
    assert "procurementQuickActions" in dashboard
    assert "procurementProcessFlow" in dashboard
    assert "route_requested" in dashboard
    assert all(label in dashboard for label in (
        "Nueva solicitud", "Nueva orden de compra", "Nueva compra directa",
        "Capturar factura", "Carga en origen", "Recepción",
    ))


def test_dashboard_uses_canonical_charts_with_visual_hierarchy():
    dashboard = source("pages/procurement_dashboard_page.py")
    assert "HtmlChartView" in dashboard
    assert "KPIBar" in dashboard
    assert "(self._cards[0], 2), (self._cards[1], 1)" in dashboard
    assert "QMessageBox" not in dashboard


def test_orders_have_master_detail_timeline_and_contextual_actions():
    pages = source("pages/enterprise_pages.py")
    detail = source("document_detail.py")
    assert "QSplitter" in pages and "OrderDetailPanel" in pages
    assert "itemSelectionChanged" in pages
    assert "class DocumentTimeline" in detail
    assert all(step in detail for step in ("PR", "RFQ", "Embarque", "Recepción", "Factura", "CxP", "Pago"))
    assert "QMessageBox" not in pages


def test_requisitions_have_master_detail_and_real_sourcing_actions():
    pages = source("pages/enterprise_pages.py")
    detail = source("document_detail.py")
    routes = (ROOT / "frontend/desktop/modules/purchasing/enterprise_routes.py").read_text(
        encoding="utf-8")
    assert "RequisitionDetailPanel" in pages + detail
    assert all(action in pages for action in (
        "Crear RFQ", "Crear orden", "Compra directa"))
    assert "CreateRfqUseCase" in routes
    assert "direct_purchase_requested" in pages
    assert "set_events" in detail


def test_receipts_and_invoices_are_real_master_detail_workspaces():
    receipts = source("pages/purchase_history_page.py")
    invoices = source("pages/enterprise_pages.py")
    dialogs = source("dialogs/enterprise_dialogs.py")
    assert all(label in receipts for label in (
        "Recepciones relacionadas", "Aceptado", "Rechazado", "Diferencias",
        "Conciliación"))
    assert all(label in invoices for label in (
        "Aceptado", "Facturado", "Precio acordado", "Precio factura", "Impuesto"))
    assert "document_provider" in dialogs and "direct_purchase_line_id" in dialogs
    assert "__unknown__" not in invoices


def test_purchasing_ui_has_no_inline_styles_or_direct_buttons():
    files = [MODULE / "purchasing_module_shell.py", MODULE / "document_detail.py"]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "setStyleSheet" not in combined
    assert "QPushButton" not in combined
