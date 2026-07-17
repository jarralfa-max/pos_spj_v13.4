"""Component gallery (FASE DS-7) — the official visual reference.

Builds a scrollable page showing the JUANIS palette and every canonical
component in the current theme. Run it standalone:

    QT_QPA_PLATFORM=  python -m frontend.desktop.design_system.component_gallery

``build_gallery(theme)`` returns a QWidget so the gallery is smoke-testable
headless (both themes) without a display.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    KPIBar,
    KPIDTO,
    KPIState,
    PageHeader,
    SectionCard,
    StatusBadge,
    TimeInput,
    TimeRangeInput,
    ViewState,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
    create_state_widget,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.brand_palette import BrandColors
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import Spacing


def _swatch(name: str, hex_value: str) -> QWidget:
    box = QFrame()
    box.setObjectName("standardCard")
    box.setProperty("cardVariant", "standard")
    box.setMinimumSize(150, 60)
    lay = QVBoxLayout(box)
    lay.addWidget(QLabel(name))
    lay.addWidget(QLabel(hex_value))
    return box


def _section(title: str) -> tuple[SectionCard, QVBoxLayout]:
    card = SectionCard(title=title)
    return card, card.body()


def build_gallery(theme: str = "light") -> QWidget:
    ThemeManager.instance().set_theme(theme)

    root = QWidget()
    outer = QVBoxLayout(root)
    outer.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
    outer.setSpacing(Spacing.LG)

    outer.addWidget(PageHeader(title="Design System SPJ — JUANIS",
                               subtitle="Referencia visual oficial", icon=Icons.SETTINGS))

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    col = QVBoxLayout(content)
    col.setSpacing(Spacing.LG)

    # palette
    pal_card, pal = _section("Paleta JUANIS")
    grid = QGridLayout()
    for i, (name, value) in enumerate([
        ("Verde Bosque", BrandColors.FOREST_GREEN),
        ("Rojo Tradicional", BrandColors.TRADITIONAL_RED),
        ("Dorado Premium", BrandColors.PREMIUM_GOLD),
        ("Crema Suave", BrandColors.SOFT_CREAM),
        ("Café Tierra", BrandColors.EARTH_BROWN),
    ]):
        grid.addWidget(_swatch(name, value), 0, i)
    pal.addLayout(grid)
    col.addWidget(pal_card)

    # buttons
    btn_card, btns = _section("Botones")
    row = QHBoxLayout()
    row.addWidget(create_primary_button(text="Primario"))
    row.addWidget(create_secondary_button(text="Secundario"))
    row.addWidget(create_danger_button(text="Eliminar"))
    btns.addLayout(row)
    col.addWidget(btn_card)

    # KPIs
    kpi_card, kpis = _section("KPIs")
    kpis.addWidget(KPIBar(cards=[
        KPIDTO("a", "Ventas netas", "$125,430.00", variant="success",
               trend_value="8.4%", trend_direction="up", trend_label="vs. ayer"),
        KPIDTO("b", "Ticket promedio", "$182.10", variant="primary"),
        KPIDTO("c", "Cargando", "$0.00", state=KPIState.LOADING),
        KPIDTO("d", "Incidencias", "3", variant="danger"),
    ], responsive=False))
    col.addWidget(kpi_card)

    # badges
    badge_card, badges = _section("Insignias de estado")
    brow = QHBoxLayout()
    for status, text in [("success", "Pagado"), ("warning", "Pendiente"),
                         ("danger", "Rechazado"), ("info", "En proceso"),
                         ("neutral", "Borrador")]:
        brow.addWidget(StatusBadge(text, status=status))
    badges.addLayout(brow)
    col.addWidget(badge_card)

    # inputs
    input_card, inputs = _section("Inputs especializados")
    inputs.addWidget(QLabel("Hora (HH:mm)"))
    inputs.addWidget(TimeInput())
    inputs.addWidget(QLabel("Rango horario"))
    trange = TimeRangeInput(allow_overnight=True)
    trange.set_range("08:00", "20:00")
    inputs.addWidget(trange)
    col.addWidget(input_card)

    # states
    state_card, states = _section("Estados de vista")
    for st in (ViewState.LOADING, ViewState.EMPTY, ViewState.ERROR,
               ViewState.NO_PERMISSION, ViewState.OFFLINE):
        states.addWidget(create_state_widget(st))
    col.addWidget(state_card)

    col.addStretch(1)
    scroll.setWidget(content)
    outer.addWidget(scroll, stretch=1)
    return root


def main() -> None:  # pragma: no cover - manual launch
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    ThemeManager.instance().apply(app, "light")
    window = build_gallery("light")
    window.resize(1100, 800)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":  # pragma: no cover
    main()
