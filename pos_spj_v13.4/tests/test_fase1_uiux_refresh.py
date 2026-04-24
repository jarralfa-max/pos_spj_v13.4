import os
import ast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_COMPONENTS = os.path.join(ROOT, 'modulos', 'ui_components.py')
REPORTES = os.path.join(ROOT, 'modulos', 'reportes_bi_v2.py')
COTIZACIONES = os.path.join(ROOT, 'modulos', 'cotizaciones.py')
TRANSFERENCIAS = os.path.join(ROOT, 'modulos', 'transferencias.py')
INVENTARIO_LOCAL = os.path.join(ROOT, 'modulos', 'inventario_local.py')
COMPRAS_PRO = os.path.join(ROOT, 'modulos', 'compras_pro.py')
MERMA = os.path.join(ROOT, 'modulos', 'merma.py')
CLIENTES = os.path.join(ROOT, 'modulos', 'clientes.py')
PRODUCTOS = os.path.join(ROOT, 'modulos', 'productos.py')
PRODUCCION = os.path.join(ROOT, 'modulos', 'produccion.py')
CAJA = os.path.join(ROOT, 'modulos', 'caja.py')
MENU_LATERAL = os.path.join(ROOT, 'interfaz', 'menu_lateral.py')
VENTAS = os.path.join(ROOT, 'modulos', 'ventas.py')
MAIN_WINDOW = os.path.join(ROOT, 'interfaz', 'main_window.py')
MAIN_APP = os.path.join(ROOT, 'main.py')
DELIVERY = os.path.join(ROOT, 'modulos', 'delivery.py')
RRHH = os.path.join(ROOT, 'modulos', 'rrhh.py')
DASHBOARD = os.path.join(ROOT, 'ui', 'dashboard.py')
FINANZAS = os.path.join(ROOT, 'modulos', 'finanzas_unificadas.py')
TARJETAS = os.path.join(ROOT, 'modulos', 'tarjetas.py')
PRODUCT_SEARCH = os.path.join(ROOT, 'modulos', 'spj_product_search.py')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def test_reusable_components_exist():
    src = _read(UI_COMPONENTS)
    for token in [
        'class EmptyStateWidget',
        'class LoadingIndicator',
        'class FilterBar',
        'class DataTableWithFilters',
        'def confirm_action',
        'def create_standard_tabs',
        'def apply_global_theme',
    ]:
        assert token in src

def test_ui_components_exports_new_widgets():
    src = _read(UI_COMPONENTS)
    assert '"FilterBar"' in src
    assert '"DataTableWithFilters"' in src
    assert '"confirm_action"' in src
    assert '"create_standard_tabs"' in src
    assert '"apply_global_theme"' in src


def test_buttons_do_not_expand_full_width_by_default():
    src = _read(UI_COMPONENTS)
    assert "btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)" in src
    assert "btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)" in src


def test_reportes_uses_filter_bar_and_echarts():
    src = _read(REPORTES)
    assert 'FilterBar(' in src
    assert 'DataTableWithFilters' in src
    assert 'QWebEngineView' in src
    assert 'echarts.min.js' in src
    assert 'if (window.echarts)' in src
    assert '"venta_confirmada", "stock_actualizado", "pago_registrado"' in src
    assert 'def set_sucursal(self, sucursal_id: int, nombre_sucursal: str = ""):' in src


def test_uiux_components_applied_to_more_modules():
    cot = _read(COTIZACIONES)
    trf = _read(TRANSFERENCIAS)
    inv = _read(INVENTARIO_LOCAL)
    com = _read(COMPRAS_PRO)
    mer = _read(MERMA)
    cli = _read(CLIENTES)
    pro = _read(PRODUCTOS)
    prd = _read(PRODUCCION)
    caj = _read(CAJA)
    mnu = _read(MENU_LATERAL)
    ven = _read(VENTAS)
    mw = _read(MAIN_WINDOW)
    appm = _read(MAIN_APP)
    dly = _read(DELIVERY)
    rrh = _read(RRHH)
    dsh = _read(DASHBOARD)
    fin = _read(FINANZAS)
    tar = _read(TARJETAS)
    ps = _read(PRODUCT_SEARCH)
    assert 'FilterBar(' in cot and 'LoadingIndicator(' in cot and 'EmptyStateWidget(' in cot
    assert 'confirm_action(' in cot
    assert 'create_secondary_button(self, "🔍 Ver Detalle"' in cot
    assert 'FilterBar(' in trf and 'LoadingIndicator(' in trf and 'EmptyStateWidget(' in trf
    assert 'confirm_action(' in trf
    assert 'FilterBar(' in inv and 'LoadingIndicator(' in inv and 'EmptyStateWidget(' in inv
    assert 'FilterBar(' in com and 'LoadingIndicator(' in com and 'EmptyStateWidget(' in com
    assert 'confirm_action(' in com
    assert 'create_standard_tabs(' in com
    assert 'wrap_in_scroll_area(' in com
    assert 'self._trad_filter = FilterBar(grp_cart' in com
    assert 'self.txt_proveedor = QLineEdit()' in com
    assert 'QCompleter' in com and 'QStringListModel' in com
    assert 'FilterBar(' in mer and 'LoadingIndicator(' in mer and 'EmptyStateWidget(' in mer
    assert 'FilterBar(' in cli and 'LoadingIndicator(' in cli and 'EmptyStateWidget(' in cli
    assert 'confirm_action(' in cli
    assert 'create_standard_tabs(' in cli
    assert 'wrap_in_scroll_area(' in cli
    assert 'LoadingIndicator(' in pro and 'EmptyStateWidget(' in pro
    assert 'FilterBar(' in prd and 'LoadingIndicator(' in prd and 'EmptyStateWidget(' in prd
    assert 'confirm_action(' in caj
    assert 'create_input_field(' in mnu
    assert 'def _filtrar_modulos_menu' in mnu
    assert 'SidebarSearch' in mnu
    assert 'def _normalizar_botones_principales' in ven
    assert 'self._normalizar_botones_principales()' in ven
    assert 'row_docs = QHBoxLayout()' in ven
    assert 'btn.setMinimumWidth(150)' in ven
    assert 'row_login = QHBoxLayout()' in mw
    assert 'self.btn_login.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)' in mw
    assert 'def install_dialog_button_normalizer' in _read(UI_COMPONENTS)
    assert 'install_dialog_button_normalizer(app)' in appm
    assert 'LoadingIndicator(' in dly and 'EmptyStateWidget(' in dly
    assert 'FilterBar(' in rrh and 'confirm_action(' in rrh
    assert 'LoadingIndicator(' in dsh and 'EmptyStateWidget(' in dsh
    assert 'def _normalizar_botones_ui' in fin
    assert 'QPalette.Window' in fin
    assert 'def _create_compact_action_button(self, text: str, variant: str = "primary")' in fin
    assert 'self._create_compact_action_button("💸 Abonar", "primary")' in fin
    assert 'self._create_compact_action_button("💰 Cobrar", "success")' in fin
    assert 'def _normalizar_botones_tarjetas' in tar
    assert 'setAccessibleName(' in tar
    assert 'def _is_dark_mode(self) -> bool:' in ps
    assert 'dark_mode = self._is_dark_mode()' in ps
    assert 'productSearchPopupList' in ps


def test_python_syntax_ok():
    ast.parse(_read(UI_COMPONENTS))
    ast.parse(_read(REPORTES))
    ast.parse(_read(COTIZACIONES))
    ast.parse(_read(TRANSFERENCIAS))
    ast.parse(_read(INVENTARIO_LOCAL))
    ast.parse(_read(COMPRAS_PRO))
    ast.parse(_read(MERMA))
    ast.parse(_read(CLIENTES))
    ast.parse(_read(PRODUCTOS))
    ast.parse(_read(PRODUCCION))
    ast.parse(_read(CAJA))
    ast.parse(_read(MENU_LATERAL))
    ast.parse(_read(VENTAS))
    ast.parse(_read(MAIN_WINDOW))
    ast.parse(_read(MAIN_APP))
    ast.parse(_read(DELIVERY))
    ast.parse(_read(RRHH))
    ast.parse(_read(DASHBOARD))
    ast.parse(_read(FINANZAS))
    ast.parse(_read(TARJETAS))
    ast.parse(_read(PRODUCT_SEARCH))
