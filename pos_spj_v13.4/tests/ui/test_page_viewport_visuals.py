"""PageViewport composition at supported desktop sizes, without a database.

Set SPJ_PAGE_VIEWPORT_ARTIFACTS to retain the 30 form captures. Geometry and
scroll reachability are asserted independently of screenshots; offscreen Qt
does not replace validation on physical monitors or with native touch input.
"""

import os
from pathlib import Path

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, QSettings
from PyQt5.QtWidgets import QFormLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.module_layout import ModuleLayout
from frontend.desktop.components.pages import StandardPage
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.standard_window import StandardWindow
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.shell.application_shell.content_host import ContentHost
from frontend.desktop.shell.router.navigation_result import NavigationResult
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import ResponsiveBreakpoints
from tests.ui.shell.conftest import make_context
from tests.ui.test_standard_window_geometry import DesktopScreen, settle


def _rect(widget, owner):
    return QRect(widget.mapTo(owner, QPoint()), widget.size())


def _assert_visible(widget, owner):
    assert widget.isVisible()
    assert owner.rect().contains(_rect(widget, owner))


def _assert_no_scroll(viewport):
    assert viewport.horizontalScrollBar().maximum() == 0
    assert viewport.verticalScrollBar().maximum() == 0


def _workspace(settings, scenario):
    page = StandardPage(
        title="Ficha de trabajo" if scenario == "form" else "Listado de trabajo",
        subtitle="La cabecera y las acciones permanecen disponibles al desplazarse.",
    )
    captured = StandardLineEdit(placeholder="Referencia", keyboard_enabled=False)
    captured.setText("Captura pendiente · conservar al cambiar apariencia")
    if scenario == "form":
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Referencia", captured)
        fields = [captured]
        for index in range(1, 25):
            field = StandardLineEdit(placeholder=f"Observación {index}", keyboard_enabled=False)
            field.setText(f"Texto de prueba de la sección {index}")
            form.addRow(f"Observación {index}", field)
            fields.append(field)
        page.add_content(body)
        last = fields[-1]
        table = None
    else:
        page.add_content(captured)
        table = StandardTable([
            ColumnSpec("Descripción", min_width=300, preferred_width=500),
            ColumnSpec("Referencia", min_width=300, preferred_width=500),
            ColumnSpec("Estado", min_width=300, preferred_width=500),
            ColumnSpec("Observaciones", min_width=300, preferred_width=500),
        ], settings=settings)
        table.load_rows([
            [f"Registro de prueba {index}", f"Referencia {index}", "Pendiente", "Detalle accesible"]
            for index in range(80)
        ])
        page.add_content(table, 1)
        last = table.item(table.rowCount() - 1, table.columnCount() - 1)
    save = create_primary_button(page, "Guardar cambios")
    page.add_action(create_secondary_button(page, "Cancelar"))
    page.add_action(save)
    module = QWidget()
    navigation = SideNav(module, settings=settings)
    navigation.add_section("Ficha", "products")
    navigation.add_section("Movimientos", "inventory")
    navigation.add_section("Configuración", "settings")
    navigation.select(0 if scenario == "form" else 1)
    layout = ModuleLayout(
        module, title="Espacio de trabajo JUANIS", subtitle="Validación del área disponible",
        sidebar=navigation, content=page,
    )
    host = ContentHost()
    host.display(NavigationResult(
        route=RouteDefinition("viewport.workspace", "viewport", "Área de trabajo", "viewport.workspace"),
        view=module, context=make_context(),
    ))
    return host, layout, navigation, page, captured, last, table, save


@pytest.mark.parametrize("size", ResponsiveBreakpoints.VALIDATION_SIZES)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
@pytest.mark.parametrize("scenario", ["form", "table"])
def test_page_viewport_composition_preserves_chrome_and_capture(
        qt_font_resources, ui_tmp_path, monkeypatch, size, theme, density, scenario):
    app = qt_font_resources
    settings = QSettings(str(ui_tmp_path / "viewport.ini"), QSettings.IniFormat)
    manager = ThemeManager(settings)
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    initial_density = "touch" if density != "touch" else "compact"
    manager.apply(app, "dark" if theme == "light" else "light", density=initial_density)
    screen = DesktopScreen(QRect(0, 0, *size))
    monkeypatch.setattr(StandardWindow, "screen", lambda self: screen)
    window = StandardWindow(title="JUANIS · PageViewport")
    host, layout, navigation, page, captured, last, table, save = _workspace(settings, scenario)
    window.setCentralWidget(host)
    window.resize(*size)
    expected_text = captured.text()
    window.show()
    settle(app)
    try:
        manager.apply(app, theme, density=density)
        settle(app)
        assert screen.availableGeometry().contains(window.frameGeometry())
        assert captured.text() == expected_text
        assert host.current_route_id == "viewport.workspace"
        assert layout.viewport.page() is page
        assert app.property("spjTheme") == theme
        assert app.property("spjDensity") == density
        _assert_no_scroll(host.page_viewport)
        _assert_no_scroll(layout.viewport)
        sticky = (layout.header, navigation, page.header, page.actions, save)
        before = [_rect(widget, window) for widget in sticky]
        for widget in sticky:
            _assert_visible(widget, window)

        if table is None:
            assert page.viewport.verticalScrollBar().maximum() > 0
            assert page.viewport.horizontalScrollBar().maximum() == 0
            page.viewport.verticalScrollBar().setValue(page.viewport.verticalScrollBar().maximum())
            settle(app)
            assert page.viewport.viewport().rect().contains(_rect(last, page.viewport.viewport()))
        else:
            _assert_no_scroll(page.viewport)
            assert table.verticalScrollBar().maximum() > 0
            assert table.horizontalScrollBar().maximum() > 0
            table.verticalScrollBar().setValue(table.verticalScrollBar().maximum())
            table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
            settle(app)
            assert table.viewport().rect().contains(table.visualItemRect(last))
            _assert_visible(table.horizontalHeader(), table)

        assert [_rect(widget, window) for widget in sticky] == before
        assert captured.text() == expected_text
        _assert_no_scroll(host.page_viewport)
        _assert_no_scroll(layout.viewport)
        directory = os.environ.get("SPJ_PAGE_VIEWPORT_ARTIFACTS")
        if directory and scenario == "form":
            target = Path(directory)
            target.mkdir(parents=True, exist_ok=True)
            name = f"{theme}-{density}-{size[0]}x{size[1]}-form.png"
            assert window.grab().save(str(target / name))
    finally:
        window.close()
        sip.delete(window)
        settle(app)
