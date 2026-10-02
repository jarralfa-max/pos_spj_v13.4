"""Visual regression contracts for the two densest Purchasing workspaces.

The test stores deterministic PNG evidence when ``PURCHASING_VISUAL_ARTIFACTS``
is set by CI. Geometry assertions catch clipping even when artifacts are not kept.
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtCore import QPoint  # noqa: E402
from PyQt5.QtWidgets import QApplication, QSplitter  # noqa: E402

from frontend.desktop.modules.purchasing.pages.direct_purchase_create_page import (  # noqa: E402
    DirectPurchaseCreatePage,
)
from frontend.desktop.modules.purchasing.pages.logistics_related_page import (  # noqa: E402
    LogisticsRelatedPage,
)
from frontend.desktop.themes.theme_manager import ThemeManager  # noqa: E402


class _DirectPresenter:
    def supplier_options(self, _search=""):
        return []

    def product_options(self, _search=""):
        return []

    def product_profile(self, _product_id):
        return None

    def totals(self, lines):
        subtotal = sum((line.line_total() for line in lines), Decimal("0"))
        return {"subtotal": subtotal, "tax": Decimal("0"), "total": subtotal}

    # Sucursal/almacén destino pertenecen al documento (2026-09-25): la pantalla
    # los ofrece con estos cuatro métodos del presentador real.
    def branch_options(self):
        return [("br-1", "Sucursal Centro"), ("br-2", "Sucursal Norte")]

    def warehouse_options(self, branch_id):
        return [("wh-1", "ALM · Almacén Principal")] if branch_id == "br-1" else []

    def preselected_destination(self, branch_options):
        return "br-1", "wh-1"

    def preselected_warehouse(self, warehouse_options):
        return warehouse_options[0][0] if len(warehouse_options) == 1 else ""

    def product_label(self, _product_id):
        return "Producto"

    # La pantalla pide estos dos desde que (2026-09-17) el buscador de proveedores
    # explica por qué sale vacío y (2026-09-18) sólo se ofrecen las fuentes de
    # pago que Finanzas sabe asentar. El doble tiene que seguir la interfaz real.
    def supplier_search_reason(self, _search=""):
        return None

    def payment_source_options(self):
        return [("BANK_TRANSFER", "Transferencia bancaria")]

    def capabilities(self):
        # Ya lo pedía la pantalla antes de esos cambios; el doble no lo tenía,
        # así que este caso fallaba sin llegar a medir el recorte.
        from types import SimpleNamespace
        return SimpleNamespace(direct_confirm=True, direct_create=True,
                               direct_authorize=True, direct_reverse=True)


class _OriginPresenter:
    def origin_documents(self, _search=""):
        return []


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _assert_visible_inside(page, widget):
    assert widget.isVisibleTo(page)
    rect = widget.geometry()
    assert rect.width() > 0 and rect.height() > 0
    translated = widget.rect().translated(widget.mapTo(page, QPoint(0, 0)))
    assert page.rect().intersects(translated)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("size", [(1366, 768), (1920, 1080)])
@pytest.mark.parametrize(
    ("name", "factory", "critical"),
    [
        ("direct-create", lambda: DirectPurchaseCreatePage(_DirectPresenter()),
         lambda page: (page.stepper, page.summary, page._continue)),
        ("origin-workspace", lambda: LogisticsRelatedPage(_OriginPresenter()),
         lambda page: (page._document_table, page._tree, page._dispatch)),
    ],
)
def test_purchasing_workspaces_render_without_clipping(app, theme, size, name,
                                                        factory, critical):
    ThemeManager.instance().apply(app, theme)
    page = factory()
    page.resize(*size)
    page.show()
    app.processEvents()

    assert page.size().width() == size[0]
    assert page.size().height() == size[1]
    for widget in critical(page):
        _assert_visible_inside(page, widget)
    splitters = page.findChildren(QSplitter)
    assert splitters and all(sum(splitter.sizes()) > 0 for splitter in splitters)

    artifact_dir = os.getenv("PURCHASING_VISUAL_ARTIFACTS")
    if artifact_dir:
        output = Path(artifact_dir)
        output.mkdir(parents=True, exist_ok=True)
        image = output / f"{name}-{theme}-{size[0]}x{size[1]}.png"
        assert page.grab().save(str(image), "PNG")
        assert image.stat().st_size > 1_000
    page.close()
