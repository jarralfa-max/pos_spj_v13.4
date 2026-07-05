# tests/test_caja_corte_z_characterization.py
"""Remediación D1 (paso 2) — Red de seguridad: caracteriza las DOS rutas de corte Z.

Objetivo: fijar el comportamiento ACTUAL de las dos implementaciones de corte Z
antes de unificarlas, para que la unificación no pierda lógica de negocio
(Prioridad 0). Estas pruebas documentan la divergencia real:

  · Ruta scheduler  — CierreCajaService.corte_z  (auto-cierre de medianoche):
      opera sobre `turno_actual` (flag abierto) + escribe un registro en
      `cierres_caja`; postea asiento de diferencia SOLO si recibe finance_service
      (el scheduler NO se lo pasa → sin asiento).
  · Ruta canónica UI — finance_service.generar_corte_z (vía CashRegister):
      opera sobre `turnos_caja` (estado) y NO escribe `cierres_caja` ni postea
      asiento de diferencia. El historial de la UI lee `cierres_caja`.

⇒ Un re-ruteo ingenuo del scheduler a la ruta canónica PERDERÍA el registro en
`cierres_caja`. La unificación debe primero completar la ruta canónica.
Ver migrations/MIGRATION_LOG.md (D1).
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


def _seed_turno_actual(conn, sucursal_id="1", usuario="SISTEMA", fondo=100.0):
    conn.execute(
        "INSERT OR REPLACE INTO turno_actual "
        "(sucursal_id, usuario, turno, fondo_inicial, fecha_apertura, abierto) "
        "VALUES (?,?,?,?, datetime('now','-2 hours'), 1)",
        (sucursal_id, usuario, "Mañana", fondo),
    )
    conn.commit()


def _seed_ventas(conn, sucursal_id="1"):
    from backend.shared.ids import new_uuid
    filas = [
        ("Efectivo", 200.0, "completada"),
        ("Tarjeta", 150.0, "completada"),
        ("Transferencia", 50.0, "completada"),
        ("Efectivo", 30.0, "cancelada"),
    ]
    for forma, total, estado in filas:
        conn.execute(
            "INSERT INTO ventas (id, sucursal_id, total, forma_pago, estado, usuario, fecha) "
            "VALUES (?,?,?,?,?,?, datetime('now'))",
            (new_uuid(), sucursal_id, total, forma, estado, "SISTEMA"),
        )
    conn.commit()


# ── Ruta scheduler: CierreCajaService.corte_z ───────────────────────────────────

class TestSchedulerCorteZ:

    def _svc(self, conn, finance_service=None):
        from core.services.cierre_caja_service import CierreCajaService
        return CierreCajaService(conn=conn, sucursal_id="1", usuario="SISTEMA",
                                 finance_service=finance_service)

    def test_escribe_registro_en_cierres_caja(self, db):
        _seed_turno_actual(db)
        _seed_ventas(db)
        resumen = self._svc(db).corte_z(efectivo_contado=0.0, comentarios="auto")
        row = db.execute(
            "SELECT tipo, total_ventas, total_efectivo, total_tarjeta, num_anulaciones "
            "FROM cierres_caja WHERE id=?", (resumen["cierre_id"],)
        ).fetchone()
        assert row is not None, "el corte Z del scheduler DEBE escribir cierres_caja"
        assert row["tipo"] == "Z"
        assert row["total_ventas"] == 400.0       # 200+150+50 (canceladas excluidas)
        assert row["total_efectivo"] == 200.0
        assert row["total_tarjeta"] == 150.0
        assert row["num_anulaciones"] == 1

    def test_cierra_turno_actual(self, db):
        _seed_turno_actual(db)
        _seed_ventas(db)
        self._svc(db).corte_z(efectivo_contado=0.0)
        abierto = db.execute(
            "SELECT abierto FROM turno_actual WHERE sucursal_id='1'"
        ).fetchone()["abierto"]
        assert abierto == 0, "el corte Z DEBE cerrar el turno_actual"

    def test_diferencia_blind_close(self, db):
        # Auto-cierre a ciegas: efectivo_contado=0 → diferencia = 0 - efectivo - fondo.
        _seed_turno_actual(db, fondo=100.0)
        _seed_ventas(db)
        resumen = self._svc(db).corte_z(efectivo_contado=0.0)
        assert resumen["diferencia"] == round(0.0 - 200.0 - 100.0, 2)  # -300.0

    def test_sin_finance_no_postea_asiento(self, db):
        # El scheduler NO inyecta finance_service → no se intenta ningún asiento.
        _seed_turno_actual(db)
        _seed_ventas(db)
        svc = self._svc(db, finance_service=None)
        resumen = svc.corte_z(efectivo_contado=0.0)  # no debe lanzar
        assert "cierre_id" in resumen

    def test_con_finance_postea_asiento_de_diferencia(self, db):
        # Con finance_service y diferencia != 0, la ruta legacy SÍ postea el asiento
        # de diferencia de caja (lógica que la ruta canónica hoy NO tiene).
        _seed_turno_actual(db, fondo=100.0)
        _seed_ventas(db)

        class _SpyFinance:
            def __init__(self):
                self.calls = []
            def registrar_asiento(self, **kw):
                self.calls.append(kw)

        spy = _SpyFinance()
        self._svc(db, finance_service=spy).corte_z(efectivo_contado=0.0)
        assert len(spy.calls) == 1, "debe postear exactamente un asiento de diferencia"
        call = spy.calls[0]
        # diferencia = 0 - 200 (efectivo) - 100 (fondo) = -300 → faltante
        assert call["monto"] == 300.0
        assert call["debe"] == "999-diferencias-caja"   # faltante
        assert call["haber"] == "110-caja"
        assert call["evento"] == "CORTE_Z"


# ── Ruta canónica UI: finance_service.generar_corte_z ───────────────────────────

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
