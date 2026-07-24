from pathlib import Path


def _source():
    root = Path("pos_spj_v13.4/frontend/desktop/modules/transfers")
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
    assert "return None" not in Path(
        "pos_spj_v13.4/frontend/desktop/modules/transfers/transfers_routes.py").read_text()
    assert source.count("page_id = \"transfers_") >= 1
