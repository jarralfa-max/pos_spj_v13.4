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


def test_shell_exposes_enterprise_information_architecture():
    shell = source("purchasing_module_shell.py")
    for label in (
        "Resumen", "Solicitudes", "Cotizaciones", "Adjudicaciones",
        "Órdenes de compra", "Compra directa", "CARGA EN ORIGEN",
        "NAVEGACIÓN", "RECEPCIÓN RELACIONADA", "FACTURACIÓN", "ANALÍTICA", "CONFIGURACIÓN",
    ):
        assert label in shell


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


def test_purchasing_ui_has_no_inline_styles_or_direct_buttons():
    files = [MODULE / "purchasing_module_shell.py", MODULE / "document_detail.py"]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "setStyleSheet" not in combined
    assert "QPushButton" not in combined
