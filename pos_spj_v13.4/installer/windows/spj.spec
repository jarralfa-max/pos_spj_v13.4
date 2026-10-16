# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — SPJ ERP/POS desktop, ONE-FOLDER bundle.

Built by `scripts/release/build_windows_release.py`, which first writes into
`SPJ_BUILD_DIR`:

* `build_info.json`   — version, commit, build number, signed flag (bundled at
                         the resource root; read by `app_version.build_metadata`);
* `version_info.txt`  — Windows version resource for both executables;
* `spj.ico`           — rendered from the official `assets/branding/app_icon.svg`
                         (format conversion only; the asset folder stays original).

Two executables share one `_internal` folder:

* `SPJ.exe`           — the desktop (windowed). `SPJ.exe --self-test` runs the
                         headless start check used by the updater and CI.
* `spj_whatsapp.exe`  — the OPTIONAL local WhatsApp service host
                         (`whatsapp_service/service_host.py`), console, run as
                         a Windows service only when the installer component
                         is chosen.

Everything is bundled in phase 1 ("same core for every profile"); install
profiles enable capabilities, they do not remove files.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
PACKAGE_ROOT = SPEC_DIR.parents[1]          # .../pos_spj_v13.4/pos_spj_v13.4
REPO_ROOT = PACKAGE_ROOT.parent             # .../pos_spj_v13.4
BUILD_DIR = Path(os.environ.get("SPJ_BUILD_DIR", REPO_ROOT / "build" / "windows")).resolve()

PATHEX = [str(PACKAGE_ROOT), str(REPO_ROOT)]
# `collect_submodules` imports packages in a helper process that inherits this
# `sys.path`: without both roots, `whatsapp_service` subpackages that import
# `backend` cannot be listed.
import sys
for _root in reversed(PATHEX):
    if _root not in sys.path:
        sys.path.insert(0, _root)

# Imported by string at runtime (migration engine, permission catalog, lazy
# module activators, the WhatsApp service routers): PyInstaller's static
# analysis cannot see them, so every submodule is listed explicitly.
HIDDEN = sorted(set(
    collect_submodules("backend")
    + collect_submodules("frontend")
    + collect_submodules("migrations")
    + collect_submodules("security")
    + collect_submodules("utils")
))
# Fail the BUILD, not the till: the first local build (2026-10-15) shipped
# without a single migration because this list came back empty, and only
# `SPJ.exe --self-test` noticed.
_REQUIRED = {"migrations.m000_base_schema", "migrations.engine",
             "backend.bootstrap.self_test", "frontend.desktop.app"}
_missing = _REQUIRED - set(HIDDEN)
if _missing or len([m for m in HIDDEN if m.startswith("migrations.")]) < 100:
    raise SystemExit(f"spj.spec: módulos dinámicos sin recolectar: {sorted(_missing)}")

WHATSAPP_HIDDEN = sorted(set(
    collect_submodules("whatsapp_service", filter=lambda name: ".tests" not in name)
    + collect_submodules("uvicorn")
    + ["win32timezone"]
))

DATAS = [
    (str(PACKAGE_ROOT / "assets"), "assets"),
    (str(BUILD_DIR / "build_info.json"), "."),
]
for package in ("frontend", "backend", "migrations"):
    DATAS += collect_data_files(package, include_py_files=False,
                                excludes=["**/__pycache__/**", "**/tests/**"])

EXCLUDES = [
    "pytest", "_pytest", "tests", "IPython", "jupyter", "notebook",
    "tkinter",  # only the single-file updater uses it
]

ICON = str(BUILD_DIR / "spj.ico") if (BUILD_DIR / "spj.ico").exists() else None
VERSION_FILE = str(BUILD_DIR / "version_info.txt")

desktop = Analysis(
    [str(PACKAGE_ROOT / "main.py")],
    pathex=PATHEX,
    hiddenimports=HIDDEN,
    datas=DATAS,
    excludes=EXCLUDES,
    noarchive=False,
)
whatsapp = Analysis(
    [str(REPO_ROOT / "whatsapp_service" / "service_host.py")],
    pathex=PATHEX,
    hiddenimports=WHATSAPP_HIDDEN,
    datas=[(str(BUILD_DIR / "build_info.json"), ".")],
    excludes=EXCLUDES + ["PyQt5"],
    noarchive=False,
)

# The PyQtWebEngine hook drags in the whole QML tree (~21 MB, the deepest
# paths of the bundle). SPJ has no QML: QtWebEngineWidgets renders without it
# (`--self-test-ui` checks WebEngine on every build).
def _without_qml(entries):
    return [e for e in entries if not e[0].replace("\\", "/").startswith("PyQt5/Qt5/qml/")]


desktop.datas = _without_qml(desktop.datas)
desktop.binaries = _without_qml(desktop.binaries)

desktop_pyz = PYZ(desktop.pure)
whatsapp_pyz = PYZ(whatsapp.pure)

desktop_exe = EXE(
    desktop_pyz, desktop.scripts, [],
    exclude_binaries=True,
    name="SPJ",
    console=False,
    icon=ICON,
    version=VERSION_FILE,
    uac_admin=False,
    upx=False,
)
whatsapp_exe = EXE(
    whatsapp_pyz, whatsapp.scripts, [],
    exclude_binaries=True,
    name="spj_whatsapp",
    console=True,
    icon=ICON,
    version=VERSION_FILE,
    upx=False,
)

COLLECT(
    desktop_exe, desktop.binaries, desktop.datas,
    whatsapp_exe, whatsapp.binaries, whatsapp.datas,
    name="SPJ",
    upx=False,
)
