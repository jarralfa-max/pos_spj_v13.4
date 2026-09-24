from tests.architecture.architecture_guardrails import APP_ROOT


def _source():
    root = (APP_ROOT / "frontend/desktop/modules/transfers")
    return "\n".join(path.read_text() for path in root.rglob("*.py"))


def test_transfers_ui_has_no_database_inline_style_or_legacy_widget_access():
    source = _source()
    for forbidden in ("sqlite3", "repositories.", "core.db", "setStyleSheet(",
                      "QTabWidget", "QGroupBox", "QDoubleSpinBox"):
        assert forbidden not in source


def test_transfers_ui_uses_canonical_components_and_routes():
    source = _source()
    for component in ("PageHeader", "KPIBar", "StandardTable", "FormDialog",
                      "DecimalInput", "BarcodeInput", "HtmlChartView", "ChartCard"):
        assert component in source
    # Re-anclado a `APP_ROOT` el 2026-09-17: la ruta era un literal relativo a
    # la raíz EXTERIOR del repositorio, así que con cwd = directorio interior
    # —que es como corre pytest aquí y en CI— reventaba con FileNotFoundError
    # ANTES de evaluar el assert. Esta mitad de la guardia no protegía nada.
    assert "return None" not in (
        APP_ROOT / "frontend/desktop/modules/transfers/transfers_routes.py"
    ).read_text(encoding="utf-8")
    assert source.count("page_id = \"transfers_") >= 1
