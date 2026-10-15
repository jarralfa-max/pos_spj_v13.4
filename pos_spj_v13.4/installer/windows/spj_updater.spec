# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — `spj_updater.exe`, the external updater, SINGLE FILE.

Single file on purpose: the desktop copies it to a private temporary folder
and runs the copy, so the installer can replace everything in the
installation folder while the updater waits. It bundles only what the
transaction needs (job journal, SQLite backup, instance lock, package check,
process control) and Tkinter for the small "Actualizando SPJ" window — no Qt,
no ERP modules, no cryptography (`test_external_updater_does_not_load_qt_or_the_erp`).
"""
import os
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
PACKAGE_ROOT = SPEC_DIR.parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
BUILD_DIR = Path(os.environ.get("SPJ_BUILD_DIR", REPO_ROOT / "build" / "windows")).resolve()

ICON = str(BUILD_DIR / "spj.ico") if (BUILD_DIR / "spj.ico").exists() else None

updater = Analysis(
    [str(PACKAGE_ROOT / "backend" / "infrastructure" / "updater" / "updater_main.py")],
    pathex=[str(PACKAGE_ROOT)],
    hiddenimports=[],
    excludes=["PyQt5", "frontend", "cryptography", "numpy", "pandas", "scipy",
              "pytest", "_pytest"],
    noarchive=False,
)
pyz = PYZ(updater.pure)
EXE(
    pyz, updater.scripts, updater.binaries, updater.datas, [],
    name="spj_updater",
    console=False,
    icon=ICON,
    version=str(BUILD_DIR / "version_info.txt"),
    upx=False,
    runtime_tmpdir=None,
)
