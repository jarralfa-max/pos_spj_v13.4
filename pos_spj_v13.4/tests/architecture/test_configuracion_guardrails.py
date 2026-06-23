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
UI_FILES = [
    "modulos/configuracion.py",
    "modulos/config_modules.py",
    "modulos/config_hardware.py",
    "modulos/config_interfaz.py",
]

SERVICE_AND_PERSISTENCE_FILES = [
    "core/services/configuration_settings_service.py",
    "core/services/config_service.py",
    "core/module_config.py",
    "repositories/config_repository.py",
    "repositories/settings_repository.py",
    "core/repositories/hardware_config_repository.py",
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
    "modulos/configuracion.py": {
        # FASE 1 removed `cmb_sucursal.currentData() or 1` integer branch fallback.
        "currentText": 1,     # role identity taken from a combobox label -> FASE 2/4
        "row_id_index": 1,    # rule["id"] used as identity -> FASE 2/4
        "system_settings": 4,
    },
    "modulos/config_modules.py": {
        # FASE 1 removed all SQL, commit, "Principal" fallback and direct
        # feature_flags usage; toggles now go through FeatureFlagService.
        "except_pass": 1,     # menu-refresh swallow -> FASE 8
    },
    "modulos/config_hardware.py": {
        # FASE 1 removed commit()x3, sucursal_id=1 and ensure_schema/seed_defaults
        # from the UI; persistence now goes through HardwareSettingsService.
        "currentText": 17,    # device value reads -> FASE 4
        "except_pass": 1,     # ticket tipo_idx swallow -> FASE 8
    },
    "modulos/config_interfaz.py": {
        "currentText": 2,     # theme value reads -> FASE 4
        "except_pass": 1,     # prefs load swallow -> FASE 8
    },
    "core/services/configuration_settings_service.py": {
        # FASE 3: the application service owns the transaction boundary and
        # commits via ConnectionUnitOfWork (uow.commit()) before publishing
        # events. These are the canonical commits — not UI/repository commits.
        "commit": 4,
        "system_settings": 24,
    },
    "core/services/config_service.py": {},
    "core/module_config.py": {
        "except_pass": 1,
    },
    "repositories/config_repository.py": {
        # FASE 2 added tolerant label resolvers (username_for_id/role_name_for_id
        # via _resolve_label) so events carry names, not integer ids: +1 select,
        # +1 execute vs the FASE 0 baseline.
        "sql_select": 43,
        "sql_insert": 11,
        "sql_update": 11,
        "sql_delete": 2,
        # FASE 3 removed _commit() (and its except: pass) — the repository no
        # longer commits/rolls back; services own the UnitOfWork boundary.
        "cursor_execute": 65,
        "lastrowid": 1,       # transitional pre-101 fallback -> migration 200 cutover
        "int_id_cast": 1,     # int(..._id) cast of a functional id
        "cast_as_text": 1,    # CAST(h.sucursal_id AS TEXT) pre-103 fallback
        "legacy_lower": 1,    # comment accepting legacy integer ids
        "principal_fallback": 1,
    },
    "repositories/settings_repository.py": {
        "sql_select": 1,
        "sql_insert": 1,
        "sql_update": 3,
        "cursor_execute": 4,
        "system_settings": 5,
    },
    "core/repositories/hardware_config_repository.py": {
        "sql_select": 3,
        "sql_insert": 1,
        "sql_update": 1,
        "create_table": 1,    # runtime CREATE TABLE outside migrations
        "cursor_execute": 6,
        "autoincrement": 1,   # id INTEGER PRIMARY KEY AUTOINCREMENT
        "integer_pk": 1,
        "legacy_lower": 2,    # migrate_legacy_configuraciones_hardware bridge
    },
    "backend/application/commands/settings_commands.py": {},
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


# ---------------------------------------------------------------------------
# Explicit, human-readable headline guard rails (already-clean surfaces are
# pinned to hard zero so they can never regress).
# ---------------------------------------------------------------------------
def test_configuracion_main_ui_has_no_direct_sql():
    """modulos/configuracion.py and config_interfaz.py must stay SQL-free."""
    offenders = []
    for relative in ("modulos/configuracion.py", "modulos/config_interfaz.py"):
        live = _measure(relative)
        for pattern in ("cursor_execute", "sql_insert", "sql_update", "sql_delete"):
            if live.get(pattern):
                offenders.append(f"{relative}:{pattern}={live[pattern]}")
    assert not offenders, f"Direct SQL appeared in clean config UI files: {offenders}"


def test_configuracion_ui_has_no_rollback():
    """No UI scope file may call rollback() (none do today)."""
    offenders = [rel for rel in UI_FILES if _measure(rel).get("rollback")]
    assert not offenders, f"rollback() introduced in UI files: {offenders}"


def test_configuracion_ui_does_not_introduce_create_table():
    """PyQt UI must never create schema."""
    offenders = [rel for rel in UI_FILES if _measure(rel).get("create_table")]
    assert not offenders, f"CREATE TABLE introduced in UI files: {offenders}"


def test_configuracion_ui_has_no_uuid4_identity():
    """UI must not mint identity with uuid4 (use backend.shared.ids.new_uuid)."""
    offenders = [rel for rel in UI_FILES if _measure(rel).get("uuid4")]
    assert not offenders, f"uuid4 identity introduced in UI files: {offenders}"
