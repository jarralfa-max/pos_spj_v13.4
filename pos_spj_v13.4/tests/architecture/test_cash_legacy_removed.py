from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class CashLegacyRemovedTests(unittest.TestCase):
    def test_cash_legacy_runtime_files_are_removed(self):
        self.assertFalse((ROOT / "modulos/caja.py").exists())
        self.assertFalse((ROOT / "repositories/caja.py").exists())
        self.assertFalse((ROOT / "application/services/caja_application_service.py").exists())
        self.assertFalse((ROOT / "core/events/cash_event_bridge.py").exists())
        self.assertFalse((ROOT / "core/services/cierre_caja_service.py").exists())

    def test_cash_module_loader_uses_canonical_factory_only(self):
        loader = _read("core/ui/module_loader.py")
        main_window = _read("interfaz/main_window.py")
        self.assertIn('"caja":', loader)
        self.assertIn("backend.infrastructure.desktop.cash_register_factory", loader)
        self.assertIn("CashRegisterModuleHost", loader)
        self.assertNotIn("modulos.caja", loader)
        self.assertNotIn("ModuloCaja", loader)
        self.assertNotIn("modulos.caja", main_window)
        self.assertNotIn("ModuloCaja", main_window)

    def test_app_container_does_not_construct_legacy_cash_services(self):
        source = _read("core/app_container.py")
        forbidden = (
            "from repositories.caja import",
            "CajaRepository(",
            "caja_repo",
            "from application.services.caja_application_service",
            "CajaApplicationService(",
            "caja_service",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_cash_legacy_events_have_no_runtime_bridge_or_constants(self):
        event_bus = _read("core/events/event_bus.py")
        wiring = _read("core/events/wiring.py")
        for token in (
            "CAJA_MOVIMIENTO",
            "CAJA_TURNO_ABIERTO",
            "CAJA_TURNO_CERRADO",
            "CAJA_CORTE_Z_GENERADO",
            "CAJA_DIFERENCIA_DETECTADA",
            "cash_event_bridge",
            "register_cash_event_bridge",
        ):
            self.assertNotIn(token, event_bus)
            self.assertNotIn(token, wiring)

    def test_cash_runtime_permissions_do_not_use_cash_star_codes(self):
        permissions = _read("backend/application/cash_register/permissions.py")
        catalog = _read("core/security/permission_catalog.py")
        self.assertNotIn("CASH_ACCESS", permissions)
        self.assertNotIn("CASH_SHIFT_OPEN", permissions)
        self.assertNotIn("CASH_Z_CUT_GENERATE", permissions)
        self.assertNotIn("CASH_ACCESS", catalog)
        self.assertIn('"CAJA.ver"', permissions)


if __name__ == "__main__":
    unittest.main()
