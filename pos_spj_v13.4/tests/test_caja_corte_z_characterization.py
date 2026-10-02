# tests/test_caja_corte_z_characterization.py
"""Corte Z — caracterización de la ruta canónica única.

CajaApplicationService.generar_corte_z (invocado vía FinanceService o
GenerateZCutUseCase) cierra `turnos_caja`, registra `cierres_caja` (historial
de la UI), postea el asiento de diferencia y es idempotente por turno.
"""
import sqlite3

import pytest


@pytest.fixture
def db():
    # Schema completo (todas las migraciones): necesario para financial_event_log
    # (asiento de diferencia) y cierres_caja.turno_id (idempotencia).
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


# ── Ruta canónica: generar_corte_z ───────────────────────────────────────────

class TestCanonicalCorteZ:
    """Tras D1 paso 2b la ruta canónica es un SUPERSET: cierra turnos_caja Y
    registra cierres_caja Y postea el asiento de diferencia."""

    def _fin_venta(self, db):
        from core.services.enterprise.finance_service import FinanceService
        from backend.shared.ids import new_uuid
        fin = FinanceService(db)
        turno_id = fin.abrir_turno(sucursal_id="1", usuario="ana", fondo_inicial=100.0)
        db.execute(
            "INSERT INTO ventas (id, sucursal_id, total, forma_pago, estado, usuario, fecha) "
            "VALUES (?,?,?,?,?,?, datetime('now'))",
            (new_uuid(), "1", 500.0, "Efectivo", "completada", "ana"),
        )
        db.commit()
        return fin, turno_id

    def test_cierra_turno_y_registra_cierres_caja(self, db):
        fin, turno_id = self._fin_venta(db)
        before = db.execute("SELECT COUNT(*) FROM cierres_caja").fetchone()[0]
        res = fin.generar_corte_z(turno_id=turno_id, sucursal_id="1",
                                  usuario="ana", efectivo_fisico=600.0)
        # Cierra el turno canónico.
        estado = db.execute(
            "SELECT estado FROM turnos_caja WHERE id=?", (turno_id,)
        ).fetchone()["estado"]
        assert estado == "cerrado"
        # D1 2b: ahora SÍ registra el corte en cierres_caja (historial de la UI).
        after = db.execute("SELECT COUNT(*) FROM cierres_caja").fetchone()[0]
        assert after == before + 1
        assert "cierre_id" in res and res["cierre_id"]
        row = db.execute(
            "SELECT tipo, total_ventas, total_efectivo, diferencia FROM cierres_caja WHERE id=?",
            (res["cierre_id"],)
        ).fetchone()
        assert row["tipo"] == "Z"
        assert row["total_ventas"] == 500.0
        assert row["total_efectivo"] == 500.0
        # esperado = fondo(100) + efectivo(500) = 600; contado 600 → diferencia 0
        assert row["diferencia"] == 0.0

    def test_idempotente_no_duplica_cierre(self, db):
        # Segunda llamada sobre el mismo turno (ya cerrado) no debe duplicar historial.
        fin, turno_id = self._fin_venta(db)
        r1 = fin.generar_corte_z(turno_id=turno_id, sucursal_id="1",
                                 usuario="ana", efectivo_fisico=600.0)
        n1 = db.execute("SELECT COUNT(*) FROM cierres_caja WHERE turno_id=?", (turno_id,)).fetchone()[0]
        r2 = fin.generar_corte_z(turno_id=turno_id, sucursal_id="1",
                                 usuario="ana", efectivo_fisico=600.0)
        n2 = db.execute("SELECT COUNT(*) FROM cierres_caja WHERE turno_id=?", (turno_id,)).fetchone()[0]
        assert n1 == 1 and n2 == 1, "el corte Z canónico debe ser idempotente por turno"
        assert r1["cierre_id"] == r2["cierre_id"]

    def test_postea_asiento_de_diferencia(self, db):
        # Con diferencia != 0, la ruta canónica postea el asiento (financial_event_log).
        fin, turno_id = self._fin_venta(db)
        fin.generar_corte_z(turno_id=turno_id, sucursal_id="1",
                            usuario="ana", efectivo_fisico=550.0)  # esperado 600 → -50
        n = db.execute(
            "SELECT COUNT(*) FROM financial_event_log WHERE evento='CORTE_Z'"
        ).fetchone()[0]
        assert n == 1


# ── D1 paso 2c — auto-cierre por la ruta canónica (turnos_caja) ─────────────────

class TestAutoCloseCanonical:

    def _uc(self, db):
        """Cablea el GenerateZCutUseCase canónico como el container (publisher no-op)."""
        from core.services.enterprise.finance_service import FinanceService
        from backend.application.services.cash_register_application_service import (
            CashRegisterApplicationService,
        )
        from backend.application.use_cases.generate_z_cut_use_case import GenerateZCutUseCase
        fin = FinanceService(db)
        svc = CashRegisterApplicationService(fin, publisher=lambda *_: None)
        return fin, GenerateZCutUseCase(handler=svc.generate_z_cut)

    def test_cierra_turno_abierto_de_turnos_caja(self, db):
        from core.services.caja_auto_close import auto_close_open_shifts
        from backend.shared.ids import new_uuid
        fin, uc = self._uc(db)
        turno_id = fin.abrir_turno(sucursal_id="1", usuario="ana", fondo_inicial=100.0)
        db.execute(
            "INSERT INTO ventas (id, sucursal_id, total, forma_pago, estado, usuario, fecha) "
            "VALUES (?,?,?,?,?,?, datetime('now'))",
            (new_uuid(), "1", 300.0, "Efectivo", "completada", "ana"),
        )
        db.commit()

        cerrados = auto_close_open_shifts(db, uc)
        assert str(turno_id) in cerrados
        # Turno cerrado en turnos_caja (modelo canónico)
        estado = db.execute("SELECT estado FROM turnos_caja WHERE id=?", (turno_id,)).fetchone()["estado"]
        assert estado == "cerrado"
        # Registró el corte en cierres_caja (superset de 2b)
        n = db.execute("SELECT COUNT(*) FROM cierres_caja WHERE turno_id=?", (turno_id,)).fetchone()[0]
        assert n == 1

    def test_sin_turnos_abiertos_es_noop(self, db):
        from core.services.caja_auto_close import auto_close_open_shifts
        _, uc = self._uc(db)
        assert auto_close_open_shifts(db, uc) == []

    def test_uc_none_es_noop_seguro(self, db):
        from core.services.caja_auto_close import auto_close_open_shifts
        assert auto_close_open_shifts(db, None) == []
