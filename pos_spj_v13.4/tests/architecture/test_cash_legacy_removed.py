"""Caja legacy retirada: sus archivos no existen y nada vivo vuelve a ellos.

POR QUÉ CAMBIÓ ESTE ARCHIVO
----------------------------
Cuatro de sus cinco pruebas leían archivos borrados —`core/ui/module_loader.py`,
`interfaz/main_window.py`, `core/app_container.py`, `core/events/event_bus.py`,
`core/events/wiring.py`, `core/security/permission_catalog.py`— y fallaban con
FileNotFoundError, que no dice nada sobre Caja.

Lo que vigilaban sigue teniendo sentido, pero una prohibición sobre UN archivo
sólo protege ese archivo: al borrarlo se quedó sin objeto. Reescrita sobre todo
el código que corre, sobrevive al próximo reordenamiento.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]

#: Donde vive el código que corre; a esto se suman los scripts de la raíz.
_RUNTIME_ROOTS = ("backend", "frontend")

#: Archivos que TIENEN que estar en el escaneo. Si alguno falta, el escaneo no
#: está leyendo donde se compone la aplicación y "cero tokens" no demostraría
#: nada: es la no-vacuidad de estas pruebas, anclada a lo que importa en vez de
#: a un número de archivos.
_MUST_BE_SCANNED = (
    "main.py",
    "backend/bootstrap/composition_root.py",
    "frontend/desktop/shell/desktop_shell_window_composition.py",
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _runtime_sources() -> list:
    files = [p for raiz in _RUNTIME_ROOTS for p in (ROOT / raiz).rglob("*.py")
             if "__pycache__" not in p.parts]
    return files + sorted(ROOT.glob("*.py"))


def _scan(test: unittest.TestCase, pattern) -> list:
    files = _runtime_sources()
    presentes = {p.relative_to(ROOT).as_posix() for p in files}
    faltan = [f for f in _MUST_BE_SCANNED if f not in presentes]
    test.assertFalse(faltan, f"El escaneo no lee donde se compone la app: {faltan}")
    hits = []
    for path in files:
        texto = path.read_text(encoding="utf-8", errors="ignore")
        for numero, linea in enumerate(texto.splitlines(), 1):
            if pattern.search(linea):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{numero}: {linea.strip()}")
    return hits


class CashLegacyRemovedTests(unittest.TestCase):
    def test_cash_legacy_runtime_files_are_removed(self):
        self.assertFalse((ROOT / "modulos/caja.py").exists())
        self.assertFalse((ROOT / "repositories/caja.py").exists())
        self.assertFalse((ROOT / "application/services/caja_application_service.py").exists())
        self.assertFalse((ROOT / "core/events/cash_event_bridge.py").exists())
        self.assertFalse((ROOT / "core/services/cierre_caja_service.py").exists())

    def test_no_live_code_references_the_legacy_cash_module(self):
        """Antes: `core/ui/module_loader.py` e `interfaz/main_window.py` no
        nombraban el módulo legacy. Ambos se borraron; la prohibición pasa a
        todo el runtime. El lado positivo —que el shell cablea Caja por la vía
        canónica— lo fija `test_cash_register_composition_root.py`."""
        hits = _scan(self, re.compile(r"\bmodulos\.caja\b|\bModuloCaja\b"))
        self.assertFalse(hits, "Referencias al módulo legacy de Caja:\n" + "\n".join(hits))

    def test_no_live_code_constructs_legacy_cash_services(self):
        """Antes se miraba sólo `core/app_container.py`, borrado. La app se
        compone hoy en `backend/bootstrap/composition_root.py` y en el shell;
        `_MUST_BE_SCANNED` garantiza que ambos entran en el escaneo."""
        hits = _scan(self, re.compile(
            r"from\s+repositories\.caja\s+import|\bCajaRepository\s*\(|\bcaja_repo\b"
            r"|from\s+application\.services\.caja_application_service"
            r"|\bCajaApplicationService\s*\(|\bcaja_service\b"))
        self.assertFalse(hits, "Construcción de servicios legacy de Caja:\n" + "\n".join(hits))

    def test_cash_legacy_events_have_no_runtime_bridge_or_constants(self):
        """Antes: `core/events/event_bus.py` y `wiring.py`, borrados. El bus
        vive en `backend/shared/events/`.

        Cada constante legacy tiene sucesor canónico en `event_names.py`, y se
        exige que exista: sin eso, "no quedan CAJA_*" podría significar también
        "Caja dejó de emitir eventos"."""
        hits = _scan(self, re.compile(
            r"\bCAJA_MOVIMIENTO\b|\bCAJA_TURNO_ABIERTO\b|\bCAJA_TURNO_CERRADO\b"
            r"|\bCAJA_CORTE_Z_GENERADO\b|\bCAJA_DIFERENCIA_DETECTADA\b"
            r"|\bregister_cash_event_bridge\b|\bcash_event_bridge\b"))
        self.assertFalse(hits, "Eventos o puente legacy de Caja:\n" + "\n".join(hits))

        nombres = _read("backend/shared/events/event_names.py")
        for sucesor in ("CASH_MOVEMENT_RECORDED", "CASH_SHIFT_OPENED", "CASH_SHIFT_CLOSED",
                        "CASH_Z_CUT_GENERATED", "CASH_DIFFERENCE_DETECTED"):
            self.assertIn(f'{sucesor} = "{sucesor}"', nombres,
                          f"falta el evento canónico {sucesor}")

    def test_cash_runtime_permissions_do_not_use_cash_star_codes(self):
        permissions = _read("backend/application/cash_register/permissions.py")
        # Antes `core/security/permission_catalog.py`, borrado. El catálogo
        # canónico no copia los códigos: importa el `permissions.py` de cada
        # contexto. Se exige que importe el de Caja; si no, "sin CASH_* en el
        # catálogo" sería trivialmente cierto.
        catalog = _read("backend/application/security/permission_catalog.py")
        self.assertNotIn("CASH_ACCESS", permissions)
        self.assertNotIn("CASH_SHIFT_OPEN", permissions)
        self.assertNotIn("CASH_Z_CUT_GENERATE", permissions)
        self.assertNotIn("CASH_ACCESS", catalog)
        self.assertIn('"backend.application.cash_register.permissions",', catalog)
        self.assertIn('"CAJA.ver"', permissions)


if __name__ == "__main__":
    unittest.main()
