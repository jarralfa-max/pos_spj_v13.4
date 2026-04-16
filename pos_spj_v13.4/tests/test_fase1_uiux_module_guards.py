import ast
from pathlib import Path

TARGETS = [
    'modulos/caja.py',
    'modulos/productos.py',
    'modulos/delivery.py',
    'modulos/compras_pro.py',
    'modulos/etiquetas.py',
    'modulos/finanzas.py',
    'modulos/activos.py',
    'modulos/rrhh.py',
    'modulos/tarjetas.py',
    'modulos/ticket_designer.py',
]


def _ui_components_imported(tree: ast.AST):
    imported = set()
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and n.module == 'modulos.ui_components':
            imported.update(a.name for a in n.names)
    return imported


def _create_helpers_used(tree: ast.AST):
    used = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id.startswith('create_'):
            used.add(n.id)
    return used


def test_uiux_modulos_no_usan_helpers_sin_importar():
    for rel in TARGETS:
        src = Path(rel).read_text(encoding='utf-8')
        tree = ast.parse(src)
        imported = _ui_components_imported(tree)
        used = _create_helpers_used(tree)
        missing = sorted(
            n for n in used
            if n not in imported and n not in {'create_heading_label'}
        )
        assert not missing, f"{rel} usa helpers UI sin importar: {missing}"


def test_ui_components_expose_legacy_aliases():
    src = Path('modulos/ui_components.py').read_text(encoding='utf-8')
    assert 'def create_heading_label' in src
    assert 'def create_accent_button' in src
    assert 'def create_label' in src
    assert 'def __getattr__' in src


def test_ui_components_legacy_dynamic_alias_resolution():
    src = Path('modulos/ui_components.py').read_text(encoding='utf-8')
    assert 'def _resolve_legacy_factory' in src
    assert 'def __getattr__' in src
    assert 'if "button" in n' in src
    assert 'if "heading_label" in n' in src
    assert 'if "table" in n' in src


def test_ui_components_accept_legacy_kwargs_and_flexible_signatures():
    src = Path('modulos/ui_components.py').read_text(encoding='utf-8')
    assert 'def _normalize_button_call' in src
    assert 'if isinstance(text, QPushButton):' in src
    assert 'min_width' in src and 'max_width' in src and 'fixed_width' in src
    assert 'def create_combo(parent=None' in src
    assert 'create_heading(parent=None, text: str = "")' in src
    assert 'create_subheading(parent=None, text: str = "")' in src


def test_rrhh_no_usa_typography_sizes_inexistentes():
    src = Path('modulos/rrhh.py').read_text(encoding='utf-8')
    assert 'Typography.SIZE_72' not in src
    assert 'Typography.SIZE_24' not in src


def test_config_hardware_importa_spacing_module_level():
    src = Path('modulos/config_hardware.py').read_text(encoding='utf-8')
    assert 'from modulos.design_tokens import Colors, Spacing, Typography' in src
