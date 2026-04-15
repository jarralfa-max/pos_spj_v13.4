# tests/test_fase0_login_ui.py
# Fase 0 — Bug 1: QSizePolicy importado correctamente en main_window.py
# Verifica que el módulo no tiene el NameError de QSizePolicy en el login dialog.
import sys, os, ast
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

MAIN_WINDOW_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "interfaz", "main_window.py"
)


def _read_source():
    with open(MAIN_WINDOW_PATH, encoding="utf-8") as f:
        return f.read()


def test_main_window_syntax_valid():
    """El archivo main_window.py debe tener sintaxis Python válida."""
    source = _read_source()
    ast.parse(source)  # Lanza SyntaxError si hay problema


def test_qsizepolicy_in_top_level_import():
    """QSizePolicy debe estar presente en el bloque from PyQt5.QtWidgets import."""
    source = _read_source()
    assert "QSizePolicy" in source, "QSizePolicy debe estar importado en main_window.py"
    # El import de QtWidgets es multi-línea; verificamos que el bloque completo
    # contiene QSizePolicy antes del cierre de paréntesis.
    # Reconstruir el bloque de import de QtWidgets
    lines = source.splitlines()
    in_qtwidgets_block = False
    block_text = ""
    for line in lines:
        if "from PyQt5.QtWidgets import" in line:
            in_qtwidgets_block = True
        if in_qtwidgets_block:
            block_text += line + "\n"
            if ")" in line:
                break
    assert "QSizePolicy" in block_text, (
        f"QSizePolicy debe estar en el bloque from PyQt5.QtWidgets import.\n"
        f"Bloque encontrado:\n{block_text}"
    )


def test_no_qtcore_qsizepolicy_import():
    """No debe existir 'from PyQt5.QtCore import QSizePolicy' en el archivo."""
    source = _read_source()
    for line in source.splitlines():
        stripped = line.strip()
        assert not (
            "from PyQt5.QtCore import" in stripped and "QSizePolicy" in stripped
        ), f"Import incorrecto encontrado: {stripped!r}"


def test_logo_minheight_set():
    """El código del logo debe configurar setMinimumHeight(80) para evitar cortes."""
    source = _read_source()
    assert "setMinimumHeight(80)" in source, (
        "lbl_logo.setMinimumHeight(80) debe estar presente en _configurar_ui de DialogoLogin"
    )


def test_logo_scaled_120():
    """El logo debe escalarse a máximo 120x120 con KeepAspectRatio."""
    source = _read_source()
    assert "scaled(120, 120" in source, (
        "El pixmap del logo debe escalar a 120x120 con KeepAspectRatio"
    )
