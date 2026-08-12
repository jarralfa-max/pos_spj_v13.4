"""Canonical desktop workspace for Procesamiento Cárnico / Meat Processing.

UI classes are intentionally lazy-imported by the desktop composition root so
pure navigation contracts do not initialize PyQt. Not wired into the live app
yet — the legacy `modulos/produccion.py` (menu button "PRODUCCION") stays the
active entry point until PROC-23/PROC-25 (see docs/refactor/PROC-4_navigation.md).
"""
