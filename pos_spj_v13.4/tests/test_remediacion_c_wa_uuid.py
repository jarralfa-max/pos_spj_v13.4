# tests/test_remediacion_c_wa_uuid.py
"""Remediación C (parte 1) — UUIDv7 en el borde WhatsApp (DEEP_AUDIT B12).

Bug insignia del audit: whatsapp_service/ai/catalog_entity_extractor.py hacía
`int(product.get("id"))`, que lanza ValueError con IDs UUIDv7 → el except dejaba
el catálogo vacío y NINGÚN producto era reconocido en los mensajes.

Estos tests seedean productos con IDs UUIDv7 reales y verifican que el matcher
y el extractor los manejan como str.
"""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

# ── WA service sys.path setup (igual que tests/test_wa_parser.py) ────────────
_WA_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../whatsapp_service"))
if _WA_ROOT not in sys.path:
    sys.path.insert(0, _WA_ROOT)

pytest.importorskip("rapidfuzz", reason="product_matcher usa rapidfuzz")

UUID_A = "0198c0de-1111-7aaa-8bbb-000000000001"
UUID_B = "0198c0de-2222-7ccc-8ddd-000000000002"

_SCHEMA = """
CREATE TABLE productos(
    id TEXT PRIMARY KEY, nombre TEXT, precio REAL, existencia REAL,
    unidad TEXT, categoria TEXT, activo INTEGER DEFAULT 1, oculto INTEGER DEFAULT 0
);
CREATE TABLE branch_inventory(
    product_id TEXT, branch_id TEXT, quantity REAL
);
"""


@pytest.fixture()
def matcher():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO productos(id,nombre,precio,existencia,unidad,categoria) "
        "VALUES (?,?,?,?,?,?)", (UUID_A, "Pechuga de Pollo", 120.0, 50.0, "kg", "Pollo"),
    )
    conn.execute(
        "INSERT INTO productos(id,nombre,precio,existencia,unidad,categoria) "
        "VALUES (?,?,?,?,?,?)", (UUID_B, "Milanesa de Res", 200.0, 30.0, "kg", "Res"),
    )
    conn.commit()
    from parser.product_matcher import ProductMatcher
    # Sin default '1' — UUIDv7 str.
    return ProductMatcher(conn, sucursal_id="")


def test_matcher_carga_ids_uuid_sin_romper(matcher):
    assert len(matcher._cache) == 2
    assert all(isinstance(p["id"], str) for p in matcher._cache)


def test_get_by_id_uuid(matcher):
    p = matcher.get_by_id(UUID_A)
    assert p is not None and p["nombre"] == "Pechuga de Pollo"
    assert matcher.get_by_id("no-existe") is None


def test_extractor_reconoce_productos_con_id_uuid(matcher):
    """El bug insignia: con IDs UUID el extractor no reconocía nada."""
    from ai.catalog_entity_extractor import CatalogEntityExtractor
    extractor = CatalogEntityExtractor(matcher)
    entidades = extractor.extract_products("quiero 2 kg de pechuga de pollo")
    assert entidades, (
        "El extractor no reconoció el producto con id UUIDv7 — regresión del "
        "bug int(product.get('id'))."
    )
    ids = {str(e.get("id")) for e in entidades}
    assert UUID_A in ids


def test_extractor_no_lanza_valueerror_con_uuid(matcher):
    from ai.catalog_entity_extractor import CatalogEntityExtractor
    extractor = CatalogEntityExtractor(matcher)
    # No debe lanzar ValueError al iterar ids UUID.
    extractor.extract_products("dame milanesa de res y pechuga de pollo")


def test_source_extractor_sin_int_cast_de_id():
    """Guardrail estático: no debe reaparecer int(product...id)."""
    import pathlib
    # parents[2] = raíz del repo; whatsapp_service vive fuera del paquete.
    root = pathlib.Path(__file__).resolve().parents[2]
    src = (root / "whatsapp_service" / "ai" / "catalog_entity_extractor.py").read_text(encoding="utf-8")
    assert 'int(product.get("id"' not in src and "int(product.get('id'" not in src, (
        "Reapareció int(product.get('id')) — rompe con IDs UUIDv7."
    )
