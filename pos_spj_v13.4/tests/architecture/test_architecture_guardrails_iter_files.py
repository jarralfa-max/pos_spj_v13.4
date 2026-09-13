"""Autopruebas del recorrido de archivos que usan las guardias de arquitectura.

POR QUE EXISTE
--------------
`iter_files` recorria cada raiz con `root.rglob("*")`. Sobre un ARCHIVO eso
devuelve un iterador vacio, sin error. Cualquier guardia que pasara un archivo
como raiz quedaba en verde sin haberlo leido.

No era hipotetico: `test_no_int_id_casts_in_permissions_and_session` tenia
cuatro raices y tres eran archivos. Nunca se escanearon, ni cuando existian.

Ninguna guardia comprobaba el propio recorrido, asi que el fallo era invisible
desde cualquier prueba que lo usara: todas veian "cero violaciones".
"""
from __future__ import annotations

import re

from .architecture_guardrails import PYTHON_SUFFIXES, collect_regex_violations, iter_files


def test_a_file_root_is_yielded(tmp_path):
    """El fallo, en su forma minima."""
    archivo = tmp_path / "modulo.py"
    archivo.write_text("x = 1\n", encoding="utf-8")

    assert list(iter_files(suffixes=PYTHON_SUFFIXES, roots=(archivo,))) == [archivo]


def test_a_file_root_reaches_the_pattern(tmp_path):
    """Que el archivo salga del recorrido no basta: tiene que llegar a la regex
    a traves de `collect_regex_violations`, que es lo que llaman las guardias."""
    archivo = tmp_path / "sesion.py"
    archivo.write_text("branch = int(branch_id)\n", encoding="utf-8")

    encontradas = collect_regex_violations(
        pattern=re.compile(r"\bint\(branch_id\)"), roots=(archivo,), code_only=True)

    assert len(encontradas) == 1


def test_a_file_root_with_another_suffix_is_ignored(tmp_path):
    """La rama de archivos aplica los mismos filtros que la de directorios."""
    archivo = tmp_path / "notas.txt"
    archivo.write_text("int(branch_id)\n", encoding="utf-8")

    assert list(iter_files(suffixes=PYTHON_SUFFIXES, roots=(archivo,))) == []


def test_a_directory_root_still_recurses(tmp_path):
    """El arreglo no puede romper el caso de siempre."""
    (tmp_path / "sub").mkdir()
    uno = tmp_path / "a.py"
    dos = tmp_path / "sub" / "b.py"
    uno.write_text("x = 1\n", encoding="utf-8")
    dos.write_text("y = 2\n", encoding="utf-8")

    assert set(iter_files(suffixes=PYTHON_SUFFIXES, roots=(tmp_path,))) == {uno, dos}


def test_a_missing_root_is_still_skipped_silently(tmp_path):
    """Esto se MANTIENE a proposito, y es un riesgo conocido.

    Hacer fallar las raices inexistentes aqui enrojeceria de golpe guardias con
    rutas muertas que son otro asunto (ESC/POS y `lastrowid` tienen varias). Por
    eso la guardia que motivo este archivo no confia en el recorrido: exige ella
    misma que cada raiz aporte archivos antes de buscar nada.
    """
    assert list(iter_files(suffixes=PYTHON_SUFFIXES, roots=(tmp_path / "no_existe",))) == []
