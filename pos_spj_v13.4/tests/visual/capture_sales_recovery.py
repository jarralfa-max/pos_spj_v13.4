"""Reproducible captures of real widgets and in-memory sales, never operational data.

Run from the package: python -m tests.visual.capture_sales_recovery
Optional QT_SCALE_FACTOR=1.25/1.5 exercises Qt device pixel ratios.
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QRect, QSize
from PyQt5.QtGui import QScreen, QFontDatabase
from PyQt5.QtTest import QTest
import pytest

from backend.application.sales.scale_reading_service import ScaleReadingService
from backend.domain.inventory.value_objects.catch_weight import WeightReading
from backend.infrastructure.hardware.scale_gateway import StubScaleGateway
from backend.infrastructure.integrations.sales_customer_display_client import _build_content
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.customer_display_window import CustomerDisplayWindow
from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar
from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel
from frontend.desktop.themes.theme_manager import ThemeManager
from tests.integration.sales.test_sales_pos_screen_flows import conn, pos, _producto, _stub
from tests.unit.shell.sidebar.conftest import make_context


def main():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if os.name == "nt":
        for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / font))
    root = Path(__file__).resolve().parents[2]
    factor = os.environ.get("QT_SCALE_FACTOR", "1")
    out = root / "docs/refactor/evidence/sales_recovery" / f"dpi_{factor}"
    out.mkdir(parents=True, exist_ok=True)
    from frontend.desktop.components.branding import BrandAssetProvider
    media_fixture = out / "official_brand_fixture.png"
    BrandAssetProvider.pixmap("logo_horizontal_light", QSize(640, 240)).save(str(media_fixture))
    database = conn.__wrapped__()
    connection = next(database)
    monkeypatch = pytest.MonkeyPatch()
    # Offscreen Qt exposes an 800x600 monitor. Simulate available desktop bounds;
    # all shell, scroll, table and action layouts remain production widgets.
    monkeypatch.setattr(QScreen, "availableGeometry", lambda _: QRect(0, 0, 2560, 1440))
    fixture = pos.__wrapped__(app, connection, monkeypatch)
    view = next(fixture)
    context = make_context(installation_id=new_uuid(), company_id=new_uuid(),
        branch_id=view._presenter.current_branch_id(), workstation_id=new_uuid(),
        user_id=view._presenter.current_user_id(), session_id=new_uuid())
    router = SimpleNamespace(current_context=context, route_registry=SimpleNamespace(get=lambda _: None))
    sidebar = GlobalSidebar()
    sidebar.set_items(tuple(SidebarItemViewModel(name, name, title, "", "Operación", index,
                       None, index == 0) for index, (name, title) in enumerate(
                       [("sales", "Punto de venta"), ("inventory", "Inventario"), ("settings", "Configuración")])) )
    shell = ApplicationWindow(router=router, sidebar=sidebar)
    shell.content_host._mount(view)
    shell.top_bar.set_breadcrumb(("Operación", "Punto de venta"))
    ThemeManager.instance().apply(app, "light", density="comfortable")
    shell.resize(1366, 768)
    shell.show()
    app.processEvents()
    shell.grab().save(str(out / "pos_empty.png"))
    for weight in ("1.250", "1.500", "1.750", "1.000", "1.000"):
        view.dialogs["weight"] = _stub(weight=Decimal(weight), weight_source="MANUAL")
        view._on_product_selected(_producto(view, "Alas"))
    assert sum(line.quantity for line in view._sale.lines) == Decimal("6.500")
    first = view._sale.lines[0]
    assert view._presenter.apply_line_discount(sale_id=view._sale_id, line_id=first.id,
                                              discount_amount=Decimal("5")).success
    view._refresh()
    scale = ScaleReadingService(StubScaleGateway())
    metrics = []
    for theme in ("light", "dark"):
        for density in ("comfortable", "touch"):
            ThemeManager.instance().apply(app, theme, density=density)
            for width, height in ((1280, 720), (1366, 768), (1600, 900), (1920, 1080)):
                scale.gateway.queue(WeightReading(Decimal(".850")))
                scale.gateway.queue(WeightReading(Decimal(".850")))
                scale.poll()
                view._on_scale_changed(scale.poll())
                shell.resize(width, height)
                QTest.qWait(40)
                table = view.checkout.cart._table
                row_height = sum(table.rowHeight(i) for i in range(3))
                visible_rect = shell.content_host.page_viewport.viewport().rect()
                buttons_visible = all(visible_rect.contains(button.mapTo(
                    shell.content_host.page_viewport.viewport(), button.rect().bottomRight()))
                    for button in (view.checkout.actions.btn_cobrar, view.checkout.actions.btn_suspender,
                                   view.checkout.actions.btn_reanudar, view.checkout.actions.btn_cancelar))
                metrics.append(dict(theme=theme, density=density, requested=[width,height],
                    actual=[shell.width(),shell.height()], module=[view.width(), view.height()],
                    cart_viewport=table.viewport().height(), three_rows=row_height,
                    outer_scroll=shell.content_host.page_viewport.verticalScrollBar().maximum(),
                    outer_horizontal=shell.content_host.page_viewport.horizontalScrollBar().maximum(),
                    buttons_fully_visible=buttons_visible,
                    actions_height=view.checkout.actions.height(),
                    actions_min=view.checkout.actions.minimumHeight(),
                    actions_hint=view.checkout.actions.minimumSizeHint().height(),
                    checkout_height=view.checkout.height(),
                    actions_y=view.checkout.actions.y(),
                    buttons_height=view.checkout.actions.btn_cancelar.height(),
                    buttons_y=view.checkout.actions.btn_cancelar.y(),
                    visible_bounds=[visible_rect.width(), visible_rect.height()],
                    footer_corner=[view.checkout.actions.btn_cancelar.mapTo(shell.content_host.page_viewport.viewport(),
                        view.checkout.actions.btn_cancelar.rect().bottomRight()).x(),
                        view.checkout.actions.btn_cancelar.mapTo(shell.content_host.page_viewport.viewport(),
                        view.checkout.actions.btn_cancelar.rect().bottomRight()).y()],
                    module_scroll=view.module_layout.viewport.verticalScrollBar().maximum()))
                shell.grab().save(str(out / f"pos_{theme}_{density}_{width}x{height}.png"))
    (out / "geometry.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    ThemeManager.instance().apply(app, "light", density="comfortable")
    products = [SimpleNamespace(product_id=new_uuid(), name=name, sku=f"DEMO-{i}", unit="KG",
                effective_price=Decimal("80"), available_quantity=Decimal(qty), priced=True,
                sellable=state != "NOT_SELLABLE", stock_state=state, warnings=(), image_reference=None)
                for i, (name, state, qty) in enumerate([
                    ("Alas", "AVAILABLE", "20"), ("Pechuga", "LOW_STOCK", "5"),
                    ("Muslo", "CRITICAL_STOCK", "1"), ("Pierna", "OUT_OF_STOCK", "0"),
                    ("Producto inactivo", "NOT_SELLABLE", "0")])]
    shell.resize(1600, 900)
    view.catalog._grid.set_products(products)
    app.processEvents()
    shell.grab().save(str(out / "inventory_states.png"))
    assert view._presenter.apply_sale_discount(sale_id=view._sale_id, discount_amount=Decimal("5")).success
    view._refresh()
    app.processEvents()
    shell.grab().save(str(out / "pos_sale_discount.png"))
    public = CustomerDisplayWindow()
    public.resize(1280,720)
    state = view._presenter.customer_display_state(view._sale_id)
    content = _build_content(state)
    content.update(SCALE="Báscula: 0.850 kg · estable", POINTS="Puntos estimados: no aplican sin cliente")
    content["BRANDING"] = {"name": "JUANIS", "tagline": "Calidad que viene de familia"}
    public.render_content("CART", content)
    app.processEvents()
    public.grab().save(str(out / "customer_cart.png"))
    public.render_idle_ad("IMAGE", "Recurso de prueba", "", str(media_fixture), during_sale=True)
    app.processEvents()
    public.grab().save(str(out / "customer_ad.png"))
    public.render_content("PAYMENT_PENDING", {"TOTAL": content["TOTAL"], "PAYMENT": "Estamos procesando tu compra."})
    app.processEvents()
    public.grab().save(str(out / "customer_payment.png"))
    # Presentation fixture: not evidence of a completed transaction or configured brand.
    public.render_content("THANK_YOU", {"MESSAGE": "¡Gracias por tu compra!\n¡Te esperamos pronto!", "POINTS": "Puntos pendientes",
        "TOTAL": content["TOTAL"], "BRANDING": content["BRANDING"]})
    app.processEvents()
    public.grab().save(str(out / "customer_thanks.png"))
    public.close()
    view.close()
    shell.close()
    fixture.close()
    database.close()
    monkeypatch.undo()
    assert all(m["cart_viewport"] >= m["three_rows"] and m["outer_scroll"] == 0
               and m["outer_horizontal"] == 0 and m["module_scroll"] == 0
               and m["buttons_fully_visible"] and m["actual"] == m["requested"] for m in metrics), metrics
    print(f"Saved captures and verified {len(metrics)} shell geometries in {out}")


if __name__ == "__main__":
    main()
