"""Component gallery (FASE DS-7) — the official visual reference.

Builds a scrollable reference with palette, controls, tables and states.
The complete public catalog lives in component_contracts.py. Run standalone:

    python -m frontend.desktop.design_system.component_gallery

``build_gallery(theme)`` returns a QWidget so the gallery is smoke-testable
headless (both themes) without a display.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    ColumnSpec, StandardTable, StandardLineEdit, PasswordInput, MoneyInput,
    DecimalInput, IntegerInput, WeightInput, EmailInput, DateInput,
    StandardComboBox, StandardCheckBox, StandardRadioButton,
    PageViewport, StandardWindow, Toolbar,
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
    create_ghost_button, create_icon_button,
    create_primary_button,
    create_secondary_button,
    create_state_widget,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.brand_palette import BrandColors
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import Spacing


def _swatch(name: str, key: str, hex_value: str) -> QWidget:
    box = QFrame()
    box.setObjectName("standardCard")
    box.setProperty("cardVariant", "standard")
    lay = QVBoxLayout(box)
    color = QFrame(box)
    color.setObjectName("brandSwatch")
    color.setProperty("brandColor", key)
    color.setMinimumHeight(Spacing.XXL)
    lay.addWidget(color)
    lay.addWidget(QLabel(name))
    lay.addWidget(QLabel(hex_value))
    return box


def _section(title: str) -> tuple[SectionCard, QVBoxLayout]:
    card = SectionCard(title=title)
    return card, card.body()


def build_gallery(theme: str = "light", density: str = "comfortable") -> QWidget:
    manager = ThemeManager.instance()
    manager.apply(QApplication.instance(), theme, density=density)

    root = QWidget()
    root.setObjectName("componentGallery")
    root.setProperty("overflowPolicy", "auto")
    outer = QVBoxLayout(root)
    outer.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
    outer.setSpacing(Spacing.LG)

    outer.addWidget(PageHeader(title="Design System SPJ — JUANIS",
                               subtitle="Referencia visual oficial", icon=Icons.SETTINGS))

    controls = Toolbar(title="Apariencia")
    theme_control = StandardComboBox(accessible_name="Tema")
    for label, value in (("Claro", "light"), ("Oscuro", "dark")):
        theme_control.addItem(label, value)
    theme_control.setCurrentIndex(theme_control.findData(theme))
    theme_control.currentIndexChanged.connect(lambda _index: manager.set_theme(theme_control.currentData(), app=QApplication.instance()))
    density_control = StandardComboBox(accessible_name="Densidad")
    for label, value in (("Compacta", "compact"), ("Cómoda", "comfortable"), ("Táctil", "touch")):
        density_control.addItem(label, value)
    density_control.setCurrentIndex(density_control.findData(density))
    density_control.currentIndexChanged.connect(lambda _index: manager.set_density(density_control.currentData(), app=QApplication.instance()))
    controls.addWidget(QLabel("Tema"))
    controls.addWidget(theme_control)
    controls.addSeparator()
    controls.addWidget(QLabel("Densidad"))
    controls.addWidget(density_control)
    outer.addWidget(controls)

    scroll = PageViewport()
    content = QWidget()
    col = QVBoxLayout(content)
    col.setSpacing(Spacing.LG)

    # palette
    pal_card, pal = _section("Paleta JUANIS")
    grid = QGridLayout()
    for i, (name, key, value) in enumerate([
        ("Verde profundo", "green", BrandColors.FOREST_GREEN),
        ("Blanco", "white", BrandColors.WHITE),
        ("Dorado cálido", "gold", BrandColors.PREMIUM_GOLD),
        ("Rojo profundo", "red", BrandColors.TRADITIONAL_RED),
        ("Carbón", "charcoal", BrandColors.CHARCOAL),
        ("Blanco cálido", "warm_white", BrandColors.WARM_WHITE),
    ]):
        grid.addWidget(_swatch(name, key, value), 0, i)
    pal.addLayout(grid)
    col.addWidget(pal_card)

    # buttons
    btn_card, btns = _section("Botones")
    row = QHBoxLayout()
    row.addWidget(create_primary_button(text="Primario"))
    row.addWidget(create_secondary_button(text="Secundario"))
    row.addWidget(create_danger_button(text="Eliminar"))
    row.addWidget(create_ghost_button(text="Consultar"))
    row.addWidget(create_icon_button(None, Icons.REFRESH, "Actualizar"))
    disabled = create_primary_button(text="No disponible")
    disabled.setEnabled(False)
    row.addWidget(disabled)
    btns.addLayout(row)
    col.addWidget(btn_card)

    # KPIs
    kpi_card, kpis = _section("KPIs")
    kpis.addWidget(KPIBar(cards=[
        KPIDTO("a", "Ventas netas", "$125,430.00", icon=Icons.SALES, variant="success",
               trend_value="8.4%", trend_direction="up", trend_label="vs. ayer"),
        KPIDTO("b", "Ticket promedio", "$182.10", icon=Icons.CASH, variant="primary"),
        KPIDTO("c", "Cargando", "$0.00", state=KPIState.LOADING),
        KPIDTO("d", "Incidencias", "3", variant="danger"),
    ], responsive=True))
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

    table_card, table_body = _section("Tabla operativa")
    table = StandardTable([
        ColumnSpec("Producto", key="name", min_width=220, preferred_width=280),
        ColumnSpec("Existencia", "numeric", key="stock", min_width=100),
        ColumnSpec("Precio", "numeric", key="price", min_width=100),
        ColumnSpec("Estado", "status", key="state", min_width=120),
        ColumnSpec("Notas", key="notes", priority=1, hide_below=900),
    ])
    table.load_rows([
        ["Pechuga de pollo", "125.500", "$95.00", "Disponible", "Venta por kilogramo"],
        ["Pierna y muslo", "48.250", "$75.00", "Disponible", "Refrigerado"],
        ["Producto de temporada", "0", "$120.00", "Agotado", "Reposición pendiente"],
    ])
    table.setSortingEnabled(True)
    table.setMinimumHeight(Spacing.XXL * 7)
    table_body.addWidget(table)
    col.addWidget(table_card)

    # inputs
    input_card, inputs = _section("Inputs especializados")
    fields = QGridLayout()
    for index, (label, widget) in enumerate((
        ("Nombre", StandardLineEdit(placeholder="Nombre completo")),
        ("Contraseña", PasswordInput()), ("Correo", EmailInput()),
        ("Importe", MoneyInput()), ("Cantidad", IntegerInput()),
        ("Decimal", DecimalInput()), ("Peso", WeightInput()),
        ("Fecha", DateInput()), ("Hora", TimeInput()),
    )):
        field = QWidget()
        field_layout = QVBoxLayout(field)
        field_label = QLabel(label)
        field_label.setBuddy(widget)
        field_layout.addWidget(field_label)
        field_layout.addWidget(widget)
        widget.setAccessibleName(label)
        fields.addWidget(field, index // 3, index % 3)
    inputs.addLayout(fields)
    inputs.addWidget(StandardCheckBox("Recibir avisos"))
    inputs.addWidget(StandardRadioButton("Venta de mostrador"))
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
    scroll.set_page(content)
    outer.addWidget(scroll, stretch=1)
    return root


def main() -> None:  # pragma: no cover - manual launch
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    ThemeManager.instance().apply(app, "light")
    window = StandardWindow()
    window.setWindowTitle("Componentes JUANIS — SPJ")
    window.setCentralWidget(build_gallery("light"))
    window.resize(1280, 720)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":  # pragma: no cover
    main()
