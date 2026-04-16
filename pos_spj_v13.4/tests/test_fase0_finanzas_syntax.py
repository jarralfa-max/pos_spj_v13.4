"""
Fase 0 — Hotfix: módulo finanzas debe ser sintácticamente válido
y estar protegido por importación segura en main_window.
"""

import ast
from pathlib import Path


def test_finanzas_py_syntax_valid():
    src = Path("modulos/finanzas.py").read_text(encoding="utf-8")
    ast.parse(src)


def test_main_window_importa_finanzas_en_bloque_seguro():
    src = Path("interfaz/main_window.py").read_text(encoding="utf-8")
    assert "from modulos.finanzas import ModuloFinanzas" in src
    assert "ModuloFinanzas = None" in src
    assert "Error cargando ModuloFinanzas" in src


def test_finanzas_no_tiene_lambda_rota_de_refresh():
    src = Path("modulos/finanzas.py").read_text(encoding="utf-8")
    assert "_vself" not in src
    assert "_vs=s" not in src
    assert "_vdf" not in src
    assert "_vd=d" not in src
