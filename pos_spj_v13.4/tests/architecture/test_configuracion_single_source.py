"""FASE 5 — single source of truth for CONFIGURACION settings.

Canonical sources (one table + one repository per concept):
- general settings -> ``configuraciones`` (ConfigRepository)
- global module toggles -> ``module_toggles`` (ConfigRepository)
- per-branch menu modules -> ``feature_flags`` (FeatureFlagRepository)
- hardware -> ``hardware_config`` (HardwareConfigRepository)

The legacy ``system_settings`` dual-write store and ``SettingsRepository`` are
gone; the ``configuraciones_hardware`` bridge runs only inside migrations.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

RUNTIME_DIRS = ("repositories", "core", "modulos", "application", "backend", "api")
CONFIG_MODULE_UI = ("modulos/configuracion.py", "modulos/config_modules.py", "modulos/config_hardware.py")


def _runtime_py_files():
    for rel in RUNTIME_DIRS:
        base = PACKAGE_ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            posix = path.relative_to(PACKAGE_ROOT).as_posix()
            if "/migrations/" in f"/{posix}" or posix.startswith("migrations/"):
                continue
            yield posix, path.read_text(encoding="utf-8", errors="ignore")


def test_no_system_settings_runtime_write() -> None:
    rx = re.compile(r"(INSERT\s+INTO|UPDATE)\s+system_settings", re.IGNORECASE)
    offenders = [rel for rel, src in _runtime_py_files() if rx.search(src)]
    assert not offenders, f"system_settings written at runtime: {offenders}"


def test_single_settings_repository_path() -> None:
    # The dead dual-write SettingsRepository must be gone.
    assert not (PACKAGE_ROOT / "repositories" / "settings_repository.py").exists()
    offenders = [rel for rel, src in _runtime_py_files() if "class SettingsRepository" in src]
    assert not offenders, f"SettingsRepository still defined: {offenders}"


def test_no_feature_flags_runtime_write_from_configuracion() -> None:
    rx = re.compile(r"(INSERT\s+INTO|UPDATE|REPLACE\s+INTO)\s+feature_flags", re.IGNORECASE)
    offenders = []
    for rel in CONFIG_MODULE_UI:
        src = (PACKAGE_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        if rx.search(src):
            offenders.append(rel)
    assert not offenders, f"Configuración UI writes feature_flags directly: {offenders}"


def test_no_legacy_hardware_runtime_read() -> None:
    # No runtime caller invokes the legacy configuraciones_hardware bridge, and
    # no runtime code (outside the migration-only bridge method) selects it.
    call_rx = re.compile(r"\.migrate_legacy_configuraciones_hardware\s*\(")
    read_rx = re.compile(r"FROM\s+configuraciones_hardware", re.IGNORECASE)
    bridge_file = "core/repositories/hardware_config_repository.py"
    call_offenders = []
    read_offenders = []
    for rel, src in _runtime_py_files():
        if call_rx.search(src):
            call_offenders.append(rel)
        if rel != bridge_file and read_rx.search(src):
            read_offenders.append(rel)
    assert not call_offenders, f"legacy hardware bridge called at runtime: {call_offenders}"
    assert not read_offenders, f"configuraciones_hardware read at runtime: {read_offenders}"
