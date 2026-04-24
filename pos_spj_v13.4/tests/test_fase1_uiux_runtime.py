import os
import sys
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

def _app():
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)
    QApplication = QtWidgets.QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_filter_bar_values_and_clear():
    _app()
    from modulos.ui_components import FilterBar
    bar = FilterBar(None, placeholder='Buscar...', combo_filters={'estado': ['Activo', 'Inactivo']})
    bar.search.setText('juan')
    bar._combos['estado'].setCurrentText('Inactivo')

    vals = bar.values()
    assert vals['search'] == 'juan'
    assert vals['estado'] == 'Inactivo'

    bar.clear()
    vals2 = bar.values()
    assert vals2['search'] == ''
    assert vals2['estado'] == ''


def test_data_table_with_filters_hides_non_matching_rows():
    _app()
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)
    QTableWidgetItem = QtWidgets.QTableWidgetItem
    from modulos.ui_components import DataTableWithFilters
    widget = DataTableWithFilters(headers=['Nombre', 'Monto'])
    widget.table.setRowCount(2)
    widget.table.setItem(0, 0, QTableWidgetItem('Ana'))
    widget.table.setItem(0, 1, QTableWidgetItem('$100'))
    widget.table.setItem(1, 0, QTableWidgetItem('Pedro'))
    widget.table.setItem(1, 1, QTableWidgetItem('$200'))

    widget._apply_filter({'search': 'pedro'})
    assert widget.table.isRowHidden(0) is True
    assert widget.table.isRowHidden(1) is False
    assert widget.empty_state.isVisible() is False

    widget._apply_filter({'search': 'zzz'})
    assert widget.table.isRowHidden(0) is True
    assert widget.table.isRowHidden(1) is True
    assert widget.empty_state.isVisible() is True


def test_confirm_action_returns_bool_with_mocked_exec(monkeypatch):
    _app()
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)
    QMessageBox = QtWidgets.QMessageBox
    from modulos.ui_components import confirm_action

    monkeypatch.setattr(QMessageBox, "exec_", lambda self: QMessageBox.Yes)
    result_yes = confirm_action(None, "t", "m")
    assert isinstance(result_yes, bool)
    assert result_yes is True

    monkeypatch.setattr(QMessageBox, "exec_", lambda self: QMessageBox.No)
    result_no = confirm_action(None, "t", "m")
    assert isinstance(result_no, bool)
    assert result_no is False
