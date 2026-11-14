"""Toda migración standalone nueva está registrada en `migrations/engine.py`.

Integración ronda 1 (2026-11-13): al resolver los conflictos de los PR #337-#346
se tomó un solo lado de `engine.py` y quedaron sin registrar 354, 357, 358, 359,
360, 368, 374, 380, 381, 388 y 392 — los archivos existían, pero el motor nunca
los corría. `tests/test_migration_audit.py` no lo detectaba: sólo comprueba que
los escáneres de `scripts/audit_migrations.py` encuentran archivos, no que todo
archivo esté registrado.

Desde 354 (la primera de ese grupo) la regla es estricta. Las anteriores tienen
huérfanos históricos documentados (p. ej. 030) y no se tocan aquí. Una migración
retirada a propósito se agrega a ``RETIRADAS`` con la entrada del
`MIGRATION_LOG.md` que lo decide.
"""
from __future__ import annotations

import re
from pathlib import Path

from migrations.engine import MIGRATIONS

PKG = Path(__file__).resolve().parents[2]
STANDALONE = PKG / "migrations" / "standalone"
DESDE = 354
#: versión -> motivo (entrada del MIGRATION_LOG que la retira).
RETIRADAS: dict[str, str] = {}


def _archivos_desde(desde: int) -> dict[str, str]:
    out = {}
    for ruta in STANDALONE.glob("*.py"):
        m = re.match(r"^(\d{3})_\w+\.py$", ruta.name)
        if m and int(m.group(1)) >= desde:
            out[m.group(1)] = f"migrations.standalone.{ruta.stem}"
    return out


def test_every_standalone_migration_from_354_is_registered():
    registradas = {m.version: m.module for m in MIGRATIONS}
    faltan = sorted(
        f"{v} ({mod})" for v, mod in _archivos_desde(DESDE).items()
        if v not in RETIRADAS and registradas.get(v) != mod
    )
    assert not faltan, f"migraciones sin registrar en engine.py: {faltan}"


def test_the_sqlite_lane_stays_in_numeric_order():
    numericas = [m.version for m in MIGRATIONS if m.version.isdigit()]
    desde = [v for v in numericas if int(v) >= DESDE]
    assert desde == sorted(desde), "engine.MIGRATIONS debe ir en orden numérico desde 354"
