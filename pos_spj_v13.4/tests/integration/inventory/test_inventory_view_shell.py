"""P1-C (§54) — the InventoryView sidebar shell renders the 21 canonical sections.

The shell composes a SideNav with a QStackedWidget, builds pages lazily on first
navigation, and falls back to a DS PlaceholderPage for sections without a built
page. Runs headless under offscreen Qt.
"""

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.modules.inventory.inventory_view import InventoryView  # noqa: E402
from frontend.desktop.modules.inventory.navigation import INVENTORY_NAV  # noqa: E402
from frontend.desktop.modules.inventory.page_registry import build_page_specs  # noqa: E402
from frontend.desktop.modules.inventory.pages import (  # noqa: E402
    AdjustmentsPage,
    AlertsPage,
    AuditPage,
    AvailabilityPage,
    ColdChainPage,
    CountsPage,
    ExpiryPage,
    LotsPage,
    MovementsPage,
    PlaceholderPage,
    QuarantinePage,
    ReceiptsPage,
    ReservationsPage,
    SettingsPage,
    StockPage,
    TraceabilityPage,
    TransfersPage,
    WeightPage,
)
from frontend.desktop.modules.inventory.view_models import (  # noqa: E402
    InventoryCapabilities,
    TableViewModel,
)


class _StubPresenter:
    """Presenter mínimo para páginas de búsqueda por producto (refresh vacío)."""

    def product_options(self, query):
        return []

    def capabilities(self):
        return InventoryCapabilities()

    def lot_stock(self, *, lot_id):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def lot_movements(self, *, lot_id):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def availability_breakdown(self, *, product_id, branch_id=None, warehouse_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def lots(self, *, product_id, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def movements(self, *, branch_id=None, limit=100):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def expiring(self, *, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def traceability(self, *, lot_id):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def stock(self, *, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def quarantines(self, *, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def reservations(self, *, product_id, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def cold_chain_excursions(self, *, warehouse_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def audit(self, *, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def transfers(self, *, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def catch_weight(self, *, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def receipts(self, *, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def counts(self, *, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def adjustments(self, *, branch_id=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def alerts(self, *, branch_id=None, severity=None):
        return TableViewModel(rows=[], row_ids=[], total=0)

    def alert_kpis(self, *, branch_id=None):
        return []

    def settings(self):
        return TableViewModel(rows=[], row_ids=[], total=0)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakePage:
    def __init__(self, presenter):
        from PyQt5.QtWidgets import QLabel
        self.widget = QLabel("ok")
        self.refreshed = 0

    # InventoryView adds the returned QWidget; a plain page needs to BE a widget.


def _fake_specs(n=3):
    from PyQt5.QtWidgets import QLabel
    return [((lambda _p, i=i: QLabel(f"page-{i}")), f"S{i}") for i in range(n)]


def test_registry_builds_one_spec_per_nav_section(app):
    specs = build_page_specs()
    assert len(specs) == len(INVENTORY_NAV) == 21
    titles = [title for _factory, title in specs]
    assert titles == [e.title for e in INVENTORY_NAV]


def test_shell_shows_all_sections_and_lazy_builds(app):
    specs = _fake_specs(4)
    view = InventoryView(presenter=object(), specs=specs)
    assert view.nav.count() == 4
    assert view.stack.count() == 4
    # Sólo la primera sección se construyó (nav.select(0) en el __init__).
    assert view._built.get(0) is True
    assert view._built.get(3) is None
    # Navegar a otra sección la construye.
    view.nav.select(3)
    assert view._built.get(3) is True


def test_every_section_has_a_real_page_no_placeholder(app):
    # P1-C completo: las 21 secciones canónicas tienen página real; ninguna cae al
    # PlaceholderPage. Se verifica en el registro (page_id → página real).
    from frontend.desktop.modules.inventory.page_registry import _REAL_PAGES
    missing = [e.page_id for e in INVENTORY_NAV if e.page_id not in _REAL_PAGES]
    assert missing == []
    assert PlaceholderPage not in set(_REAL_PAGES.values())


def test_disponibilidad_wires_the_real_availability_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Disponibilidad")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, AvailabilityPage)


def test_lotes_wires_the_real_lots_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Lotes")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, LotsPage)


def test_movimientos_wires_the_real_movements_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Movimientos")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, MovementsPage)


def test_caducidades_wires_the_real_expiry_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Caducidades")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, ExpiryPage)


def test_trazabilidad_wires_the_real_traceability_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Trazabilidad")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, TraceabilityPage)


def test_existencias_wires_the_real_stock_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Existencias")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, StockPage)


def test_cuarentena_wires_the_real_quarantine_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Cuarentena")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, QuarantinePage)


def test_reservas_wires_the_real_reservations_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Reservas")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, ReservationsPage)


def test_cadena_de_frio_wires_the_real_cold_chain_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Cadena de frío")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, ColdChainPage)


def test_auditoria_wires_the_real_audit_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Auditoría")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, AuditPage)


def test_transferencias_wires_the_real_transfers_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Transferencias")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, TransfersPage)


def test_peso_variable_wires_the_real_weight_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Peso variable")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, WeightPage)


def test_recepciones_wires_the_real_receipts_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Recepciones")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, ReceiptsPage)


def test_conteos_wires_the_real_counts_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Conteos")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, CountsPage)


def test_ajustes_wires_the_real_adjustments_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Ajustes")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, AdjustmentsPage)


def test_alertas_wires_the_real_alerts_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Alertas")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, AlertsPage)


def test_configuracion_wires_the_real_settings_page(app):
    view = InventoryView(presenter=_StubPresenter(), specs=build_page_specs())
    idx = [e.title for e in INVENTORY_NAV].index("Configuración")
    view.nav.select(idx)
    page = view.stack.widget(idx).layout().itemAt(0).widget()
    assert isinstance(page, SettingsPage)
