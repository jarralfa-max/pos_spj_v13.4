"""LOY-29 — guardias que impiden volver a lo que la re-auditoría encontró.

* Un solo libro de puntos (§11, §73): ningún código de producción lee ni
  escribe el libro legacy `loyalty_ledger`, ni ninguna otra tabla legacy de
  Fidelidad, Growth Engine, Tarjetas o Rifas que la migración 291 retira.
* Fidelidad no tiene rutas de "en construcción" y Tarjetas no es una entrada
  global aparte (§5-6).
* El QR sólo lleva un prefijo y el token público (§32).
* La UI de Fidelidad no hace SQL ni importa sqlite3 (§7, §13).
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_PRODUCCION = ("backend", "frontend")
_291 = importlib.import_module("migrations.standalone.291_drop_legacy_loyalty_tables")


def _py_files(*roots: str):
    for root in roots:
        for path in (ROOT / root).rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path


def _sql_touches(table: str) -> re.Pattern:
    return re.compile(
        rf"\b(FROM|JOIN|INTO|UPDATE|TABLE)\s+\"?{re.escape(table)}\"?\b", re.IGNORECASE)


def test_no_production_code_reads_or_writes_legacy_loyalty_tables():
    patrones = {t: _sql_touches(t) for t in _291.LEGACY_LOYALTY_TABLES}
    ofensores = []
    for path in _py_files(*_PRODUCCION):
        texto = path.read_text(encoding="utf-8", errors="ignore")
        for tabla, patron in patrones.items():
            if patron.search(texto):
                ofensores.append(f"{path.relative_to(ROOT)} → {tabla}")
    assert not ofensores, "Tablas legacy de fidelidad todavía usadas:\n" + "\n".join(ofensores)


def test_fidelidad_has_no_under_construction_routes():
    carpeta = ROOT / "frontend" / "desktop" / "modules" / "fidelidad"
    for path in carpeta.rglob("*.py"):
        texto = path.read_text(encoding="utf-8").lower()
        assert "seccion en construccion" not in texto, path
        assert "próxima fase)" not in texto, path


def test_loyalty_cards_live_inside_fidelidad_not_as_a_global_entry():
    assert not (ROOT / "frontend" / "desktop" / "modules" / "tarjetas_fidelidad").exists()
    from frontend.desktop.shell.sidebar import migrated_modules_navigation as nav

    ids = {getattr(item, "item_id", "") for item in vars(nav).get("MIGRATED_MODULE_NAVIGATION_ITEMS", ())}
    texto = Path(nav.__file__).read_text(encoding="utf-8")
    assert "nav.tarjetas_fidelidad" not in texto and "nav.tarjetas_fidelidad" not in ids
    from frontend.desktop.modules.fidelidad.fidelidad_routes import FIDELIDAD_ROUTES

    assert any(r.group == "Tarjetas de fidelidad" for r in FIDELIDAD_ROUTES)


def test_card_qr_carries_only_a_prefix_and_the_public_token():
    from backend.application.loyalty_cards.queries.card_render_data_query import (
        LoyaltyCardRenderDataQuery,
    )
    from backend.application.loyalty_cards.queries.resolve_card_query import strip_qr_prefix

    contenido = LoyaltyCardRenderDataQuery.qr_payload("tok123")
    assert contenido == "SPJ-CARD:tok123"
    assert strip_qr_prefix(contenido) == "tok123"


def test_fidelidad_ui_has_no_sql():
    carpeta = ROOT / "frontend" / "desktop" / "modules" / "fidelidad"
    sql = re.compile(r"\b(SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b",
                     re.IGNORECASE)
    for path in carpeta.rglob("*.py"):
        texto = path.read_text(encoding="utf-8")
        assert "import sqlite3" not in texto, path
        assert not sql.search(texto), path


def test_every_published_loyalty_fact_is_audited():
    """`_emit` de los cuatro contextos anota la auditoría (§61)."""
    for contexto in ("loyalty", "commercial_instruments", "sweepstakes", "loyalty_cards"):
        texto = (ROOT / "backend" / "application" / contexto / "use_cases" / "_base.py").read_text(
            encoding="utf-8")
        assert "record_event_audit(" in texto, contexto
