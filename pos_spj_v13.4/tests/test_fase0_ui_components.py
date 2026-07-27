# tests/test_fase0_ui_components.py
# Fase 0 — Bug 2: QSize importado correctamente en ui_components.py
# Verifica que create_icon_button() no lanza NameError y QSize está disponible.
import sys, os, ast
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

UI_COMPONENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "modulos", "ui_components.py"
)


def _read_source():
    with open(UI_COMPONENTS_PATH, encoding="utf-8") as f:
        return f.read()


def test_ui_components_syntax_valid():
    """ui_components.py debe tener sintaxis Python válida."""
    source = _read_source()
    ast.parse(source)


def test_qsize_in_qtcore_import():
    """QSize debe estar en el import de PyQt5.QtCore."""
    source = _read_source()
    qtcore_line = next(
        (line for line in source.splitlines()
         if "from PyQt5.QtCore import" in line and "QSize" in line),
        None
    )
    assert qtcore_line is not None, (
        "QSize debe importarse desde PyQt5.QtCore en ui_components.py"
    )


def test_create_icon_button_defined():
    """La función create_icon_button debe estar definida en ui_components.py."""
    source = _read_source()
    assert "def create_icon_button" in source, (
        "create_icon_button debe estar definida en ui_components.py"
    )


def test_qsize_used_in_set_icon_size():
    """QSize(18, 18) debe usarse en setIconSize."""
    source = _read_source()
    assert "QSize(18, 18)" in source, (
        "setIconSize debe usar QSize(18, 18) en create_icon_button"
    )


def test_import_module_no_name_error():
    """Importar ui_components no debe lanzar NameError ni ImportError de PyQt5."""
    # Verificar que el módulo tiene sintaxis válida y los imports están correctos
    # sin necesidad de display (verificación estática)
    source = _read_source()
    tree = ast.parse(source)

    # Recopilar todos los nombres importados en el nivel de módulo
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.col_offset == 0:
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import) and node.col_offset == 0:
            for alias in node.names:
                imported_names.add(alias.asname or alias.name.split('.')[0])

    assert "QSize" in imported_names, (
        f"QSize no está en los imports de nivel de módulo. Imports encontrados: {imported_names}"
    )
