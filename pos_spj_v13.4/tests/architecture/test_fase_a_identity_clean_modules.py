"""Fase A ratchet for UI modules cleaned of arbitrary sucursal=1 defaults.

The Fase A pass removed arbitrary branch defaults from these PyQt modules
(sucursal must come from the session, never a hardcoded 1 — regla 23, and it
prevents cross-branch data leaks). They must stay at zero.

INT_CLEAN_MODULES additionally have no int(_id) identity casts; the rest still
carry a few casts that are later Fase A work (compras_pro, fidelidad).
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

BRANCH_CLEAN_MODULES = [
    "modulos/caja.py",
    "modulos/inventario_local.py",
    "modulos/transferencias.py",
    "modulos/activos.py",
    "modulos/modulo_growth_engine.py",
    "modulos/cotizaciones.py",
    "modulos/reportes_bi_v2.py",
    "modulos/planeacion_compras.py",
    "modulos/tarjetas.py",
    "modulos/compras_pro.py",
    "modulos/whatsapp/whatsapp_module.py",
    "modulos/etiquetas.py",
    "modulos/clientes.py",
    "modulos/fidelidad_config.py",
    "modulos/configuracion.py",
]

# Subset that is also free of int(_id) identity casts.
INT_CLEAN_MODULES = [
    m for m in BRANCH_CLEAN_MODULES
    # fidelidad_config keeps 3 casts bound to int Qt widgets (QSpinBox /
    # QInputDialog.getInt) — a regla-20 selector redesign, deferred.
    if m not in {"modulos/fidelidad_config.py"}
]

ARBITRARY_BRANCH_DEFAULT = re.compile(
    r"(branch_id|sucursal_id)\s*=\s*1\b"
    r"|(branch_id|sucursal_id)[\"']?\s*,\s*[\"']?1[\"']?"
)
INT_ID_CAST = re.compile(
    r"int\(\s*[\w\.]*_id|int\(\s*getattr\([^,]+,\s*[\"'](sucursal_id|branch_id)"
)


def _read(rel: str) -> str:
    return (PACKAGE_ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_clean_modules_have_no_arbitrary_branch_default():
    bad = {rel: len(ARBITRARY_BRANCH_DEFAULT.findall(_read(rel)))
           for rel in BRANCH_CLEAN_MODULES if ARBITRARY_BRANCH_DEFAULT.findall(_read(rel))}
    assert not bad, f"arbitrary sucursal=1 default reintroduced: {bad}"


def test_int_clean_modules_have_no_int_identity_cast():
    bad = {rel: len(INT_ID_CAST.findall(_read(rel)))
           for rel in INT_CLEAN_MODULES if INT_ID_CAST.findall(_read(rel))}
    assert not bad, f"int(_id) identity cast reintroduced: {bad}"
