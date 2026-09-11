"""FASE 0 — Architecture guard rails for the CONFIGURACION module.

This module documents the *current* architectural violations of the
Configuración scope as a frozen baseline (the established ratchet pattern in
this repository, see ``test_uuidv7_cutover_protection.py``).

Two guarantees are provided:

* ``test_configuracion_scope_has_no_new_violations`` — for every scope file and
  forbidden pattern, the live count must never exceed the documented baseline.
  This blocks regressions while the later phases (FASE 1..8) drive the counts
  down to zero.
* ``test_configuracion_documented_findings_snapshot`` — the live findings must
  match the documented snapshot exactly. When a later phase removes a
  violation, this test forces the baseline to be ratcheted down so progress is
  always recorded.

In FASE 0 no productive code is corrected; only this guard-rail test (and test
helpers) are added. The forbidden surfaces tracked here are:

    SQL in PyQt UI, commit()/rollback() in UI, CREATE TABLE in UI/runtime
    repositories, AUTOINCREMENT / INTEGER PRIMARY KEY for functional config
    tables, lastrowid, int(..._id) casts, CAST(.. AS TEXT) identity fallback,
    branch_id=1 / sucursal_id=1 / "or 1" integer fallbacks, "Principal"
    fallback, currentText()/["id"] used as identity, legacy_/LEGACY_,
    except Exception: pass/return []/return {}, feature_flags written from UI,
    and system_settings written from productive runtime.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Scope inventory (mirrors docs/refactor/modules/configuracion_scope.json)
# ---------------------------------------------------------------------------
# La extinción de la Configuración legacy SE COMPLETÓ: `modulos/configuracion.py`,
# `config_modules.py`, `config_hardware.py`, `core/services/
# configuration_settings_service.py`, `config_service.py`, `core/module_config.py`,
# `repositories/config_repository.py` y `core/repositories/
# hardware_config_repository.py` ya no existen. Sus contadores de línea base se
# retiran con ellos: un trinquete sobre un archivo borrado no puede bajar más.
UI_FILES: list[str] = []

# Lo que queda vivo del alcance, y por eso este archivo no se borra entero.
SERVICE_AND_PERSISTENCE_FILES = [
    "backend/application/commands/settings_commands.py",
    "backend/application/queries/hardware_settings_query_service.py",
]

SCOPE_FILES = UI_FILES + SERVICE_AND_PERSISTENCE_FILES

# ---------------------------------------------------------------------------
# Forbidden pattern catalogue
# ---------------------------------------------------------------------------
PATTERNS: dict[str, re.Pattern[str]] = {
    "sql_select": re.compile(r"\bSELECT\s", re.I),
    "sql_insert": re.compile(r"\bINSERT\s+INTO", re.I),
    "sql_update": re.compile(r"\bUPDATE\s+\w", re.I),
    "sql_delete": re.compile(r"\bDELETE\s+FROM", re.I),
    "create_table": re.compile(r"CREATE\s+TABLE", re.I),
    "commit": re.compile(r"\.commit\(\)"),
    "rollback": re.compile(r"\.rollback\(\)"),
    "cursor_execute": re.compile(r"(cursor|cur|conn|self\.db|self\.conn)\.execute"),
    "autoincrement": re.compile(r"AUTOINCREMENT", re.I),
    "integer_pk": re.compile(r"INTEGER\s+PRIMARY\s+KEY", re.I),
    "lastrowid": re.compile(r"lastrowid", re.I),
    "int_id_cast": re.compile(r"int\(\s*[\w\.]*_id"),
    "cast_as_integer": re.compile(r"CAST\([^)]*AS\s+INTEGER", re.I),
    "cast_as_text": re.compile(r"CAST\([^)]*AS\s+TEXT", re.I),
    "legacy_lower": re.compile(r"legacy"),
    "LEGACY_upper": re.compile(r"LEGACY_"),
    "principal_fallback": re.compile(r"""["']Principal["']"""),
    "branch_id_eq_1": re.compile(r"""branch_id\s*=\s*["']?1["']?\b"""),
    "sucursal_id_eq_1": re.compile(r"""sucursal_id\s*=\s*["']?1["']?\b"""),
    "or_1": re.compile(r"\bor\s+1\b"),
    "currentText": re.compile(r"currentText\(\)"),
    "row_id_index": re.compile(r"""\[["']id["']\]"""),
    "except_return_empty_list": re.compile(r"except\s+Exception[^\n]*:\s*\n\s*return\s*\[\]"),
    "except_return_empty_dict": re.compile(r"except\s+Exception[^\n]*:\s*\n\s*return\s*\{\}"),
    "except_pass": re.compile(r"except\s+Exception[^\n]*:\s*\n\s*pass"),
    "feature_flags": re.compile(r"feature_flags"),
    "system_settings": re.compile(r"system_settings"),
    "uuid4": re.compile(r"uuid4"),
}

# ---------------------------------------------------------------------------
# Documented FASE 0 baseline. Each entry is the live count measured at the
# start of the CONFIGURACION refactor. These numbers MUST only decrease.
# ---------------------------------------------------------------------------
BASELINE: dict[str, dict[str, int]] = {
    "backend/application/commands/settings_commands.py": {},
    # Una sola lectura, documentada: el servicio de consulta de hardware.
    "backend/application/queries/hardware_settings_query_service.py": {
        "sql_select": 1,
    },
}



def _read(relative: str) -> str:
    return (PACKAGE_ROOT / relative).read_text(encoding="utf-8", errors="ignore")


def _measure(relative: str) -> dict[str, int]:
    text = _read(relative)
    counts: dict[str, int] = {}
    for name, rx in PATTERNS.items():
        n = len(rx.findall(text))
        if n:
            counts[name] = n
    return counts


# ---------------------------------------------------------------------------
# Sanity: every documented scope file must exist inside the real package.
# ---------------------------------------------------------------------------
def test_configuracion_scope_files_exist():
    missing = [rel for rel in SCOPE_FILES if not (PACKAGE_ROOT / rel).exists()]
    assert not missing, f"Scope files missing from package: {missing}"


def test_baseline_only_references_scope_files():
    stray = [rel for rel in BASELINE if rel not in SCOPE_FILES]
    assert not stray, f"Baseline references files outside the documented scope: {stray}"


# ---------------------------------------------------------------------------
# Ratchet 1 — no new violations beyond the documented FASE 0 baseline.
# ---------------------------------------------------------------------------
def test_configuracion_scope_has_no_new_violations():
    regressions: list[str] = []
    for relative in SCOPE_FILES:
        live = _measure(relative)
        base = BASELINE.get(relative, {})
        for pattern, count in live.items():
            allowed = base.get(pattern, 0)
            if count > allowed:
                regressions.append(
                    f"{relative}: '{pattern}' {count} > baseline {allowed}"
                )
    assert not regressions, (
        "New CONFIGURACION architecture violations introduced (must not exceed "
        "the FASE 0 baseline):\n" + "\n".join(regressions)
    )


# ---------------------------------------------------------------------------
# Ratchet 2 — documented findings snapshot. Forces the baseline to be lowered
# as later phases remove violations, so progress is always recorded.
# ---------------------------------------------------------------------------
def test_configuracion_documented_findings_snapshot():
    drift: list[str] = []
    for relative in SCOPE_FILES:
        live = _measure(relative)
        base = BASELINE.get(relative, {})
        for pattern in sorted(set(live) | set(base)):
            live_count = live.get(pattern, 0)
            base_count = base.get(pattern, 0)
            if live_count != base_count:
                drift.append(
                    f"{relative}: '{pattern}' live={live_count} baseline={base_count}"
                )
    assert not drift, (
        "CONFIGURACION findings snapshot drifted from the documented baseline. "
        "If you removed a violation, ratchet the baseline DOWN in this file:\n"
        + "\n".join(drift)
    )
# Las cuatro reglas de UI que vivían aquí (sin SQL directo, sin rollback, sin
# CREATE TABLE, sin identidad uuid4) se MUDARON a
# `test_configuracion_ui_guardrails.py`, que mira la Configuración canónica en
# `frontend/desktop/modules/configuracion/`.
#
# No fue una limpieza: `UI_FILES` se quedó sin un solo archivo vivo, y una
# prueba que recorre una lista vacía pasa en verde sin comprobar nada. Cuatro
# guardias decorativas es peor que ninguna, porque dan la señal de que se
# comprobó.
