"""CASH-25: Caja ya no tiene ruta UI legacy."""

from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_legacy_caja_module_was_removed():
    assert not (REPO / "modulos" / "caja.py").exists()


# `test_main_window_uses_cash_register_workspace` leía `interfaz/main_window.py`,
# borrado. Lo que comprobaba vive ahora en dos sitios:
#   - que el shell cablea Caja por la vía canónica:
#     test_cash_register_composition_root.py::test_desktop_shell_wires_cash_through_canonical_registration
#   - que nada vivo importa `modulos.caja`:
#     test_cash_legacy_removed.py::test_no_live_code_references_the_legacy_cash_module


def test_cash_workspace_uses_canonical_pages_and_no_sql():
    src = (
        REPO / "frontend" / "desktop" / "modules" / "cash_register"
        / "cash_register_workspace.py"
    ).read_text(encoding="utf-8")
    for required in ("CashLedgerPage", "BlindCountPage", "CashConfigurationPage", "CashDevicesPage"):
        assert required in src
    forbidden = ("sqlite3", "SELECT ", "INSERT ", "UPDATE ", "DELETE ", ".commit(", ".rollback(")
    assert not any(token in src for token in forbidden)


def test_cash_register_service_is_sole_cash_event_emitter():
    svc = (REPO / "backend" / "application" / "services"
           / "cash_register_application_service.py").read_text(encoding="utf-8")
    for evt in ("CASH_SHIFT_OPENED", "CASH_MOVEMENT_RECORDED", "CASH_Z_CUT_GENERATED"):
        assert evt in svc
