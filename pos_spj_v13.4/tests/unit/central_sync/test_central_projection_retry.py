"""SDLC-SYNC-003 — la proyección central no pierde hechos fuera de orden.

Libro en MEMORIA (simulación) que cumple el contrato como lo cumple PostgreSQL:
`pending_facts` devuelve lo no proyectado y, al final del lote, lo que quedó
esperando su dependencia; `set_sale_status`/`close_cash_shift` dicen si tocaron
una fila. La misma batería contra PostgreSQL real está en
`tests/integration/central_pg/test_central_projection_pg.py` (CI).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.application.sync.central_projection import PROJECTOR, CentralProjector
from backend.shared.ids import new_uuid

T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
SUCURSAL, ESTACION, OTRA_ESTACION = new_uuid(), new_uuid(), new_uuid()


class _Libro:
    def __init__(self):
        self.hechos: list[dict] = []
        self.registro: dict[str, tuple[str, str | None]] = {}
        self.ventas: dict[str, dict] = {}
        self.turnos: dict[str, dict] = {}
        self.movimientos: dict[str, dict] = {}
        self.creditos: dict[str, dict] = {}
        self.puntos: dict[str, dict] = {}
        self.unidades: dict[str, dict] = {}

    def pending_facts(self, *, projector, limit, retry_errors=False):
        def reintentable(estado):
            return estado[0] == "ERROR" and (
                retry_errors or str(estado[1] or "").startswith("DEPENDENCY_MISSING"))
        nuevos = [h for h in self.hechos if h["event_id"] not in self.registro]
        esperando = [h for h in self.hechos if h["event_id"] in self.registro
                     and reintentable(self.registro[h["event_id"]])]
        return (nuevos + esperando)[:limit]

    @contextmanager
    def savepoint(self):
        yield

    def log(self, *, event_id, projector, status, error):
        assert projector == PROJECTOR
        self.registro[event_id] = (status, error)

    def commit(self):
        pass

    def upsert_sale(self, rows):
        self.ventas.setdefault(rows["sale"]["sale_id"], {"status": "COMPLETED"})

    def set_sale_status(self, *, sale_id, status, event_id):
        if sale_id not in self.ventas:
            return False
        self.ventas[sale_id]["status"] = status
        return True

    def open_cash_shift(self, row):
        self.turnos.setdefault(row["shift_id"], {"status": "OPEN"})

    def close_cash_shift(self, *, shift_id, closed_at, z_cut_id):
        if shift_id not in self.turnos:
            return False
        self.turnos[shift_id]["status"] = "CLOSED"
        return True

    def add_cash_movement(self, row):
        self.movimientos.setdefault(row["movement_id"], row)

    def cash_movement_signed(self, movement_id):
        fila = self.movimientos.get(movement_id)
        return None if fila is None else fila["signed_amount"]

    def _ultimo(self, tabla, llave):
        fila = tabla.get(llave)
        if fila is None:
            return None
        hecho = next(h for h in self.hechos if h["event_id"] == fila["last_event_id"])
        return {k: hecho[k] for k in ("station_id", "aggregate_type", "aggregate_id",
                                      "aggregate_version")}

    def last_projected_event(self, kind, key):
        tabla = {"credit_account": self.creditos, "loyalty_transaction": self.puntos,
                 "org_unit": self.unidades}[kind]
        return self._ultimo(tabla, key)

    def upsert_credit_account(self, row):
        self.creditos[row["profile_id"]] = {"credit_limit": row["credit_limit"],
                                            "status": row["status"],
                                            "last_event_id": row["event_id"]}

    def upsert_loyalty_transaction(self, row):
        self.puntos[row["transaction_id"]] = {"status": row["status"],
                                              "last_event_id": row["event_id"]}

    def upsert_org_unit(self, row):
        actual = self.unidades.get(row["unit_id"])
        if actual is None or actual["updated_at"] <= row["updated_at"]:
            self.unidades[row["unit_id"]] = {"name": row["name"], "updated_at": row["updated_at"],
                                             "last_event_id": row["event_id"]}


def _hecho(libro, tipo, payload, *, agregado=None, tipo_agregado="sales.sale", version=1,
           estacion=ESTACION):
    hecho = {"event_id": new_uuid(), "event_type": tipo, "aggregate_id": agregado or new_uuid(),
             "aggregate_type": tipo_agregado, "aggregate_version": version,
             "branch_id": SUCURSAL, "station_id": estacion, "occurred_at": T0,
             "payload": payload}
    libro.hechos.append(hecho)
    return hecho


def _venta(libro, venta_id):
    return _hecho(libro, "SALE_COMPLETED", {"total": "100.00", "lines": [], "payments": []},
                  agregado=venta_id)


def _estado(libro, hecho):
    return libro.registro[hecho["event_id"]]


# ── dependencias que llegan tarde ────────────────────────────────────────────
def test_a_cancellation_before_its_sale_is_not_recorded_ok_and_projects_later():
    libro, venta_id = _Libro(), new_uuid()
    cancelacion = _hecho(libro, "SALE_CANCELLED", {}, agregado=venta_id)
    CentralProjector(libro).run_once()
    estado, error = _estado(libro, cancelacion)
    assert estado == "ERROR" and error.startswith("DEPENDENCY_MISSING")

    _venta(libro, venta_id)
    corrida = CentralProjector(libro).run_once()

    assert corrida.errors == 0
    assert libro.ventas[venta_id]["status"] == "CANCELLED"
    assert _estado(libro, cancelacion)[0] == "OK"


def test_the_dependency_in_the_same_batch_is_projected_first():
    libro, venta_id = _Libro(), new_uuid()
    cancelacion = _hecho(libro, "SALE_REVERSED", {}, agregado=venta_id)
    CentralProjector(libro).run_once()
    _venta(libro, venta_id)
    CentralProjector(libro).run_once()
    assert libro.ventas[venta_id]["status"] == "REVERSED"
    assert _estado(libro, cancelacion)[0] == "OK"


def test_closing_a_shift_that_has_not_arrived_waits_for_it():
    libro, turno = _Libro(), new_uuid()
    cierre = _hecho(libro, "CASH_SHIFT_CLOSED", {"shift_id": turno}, agregado=turno,
                    tipo_agregado="cash_register.cash")
    CentralProjector(libro).run_once()
    assert _estado(libro, cierre)[1].startswith("DEPENDENCY_MISSING")
    _hecho(libro, "CASH_SHIFT_OPENED", {"opening_amount": "500.00"}, agregado=turno,
           tipo_agregado="cash_register.cash")
    CentralProjector(libro).run_once()
    assert libro.turnos[turno]["status"] == "CLOSED"


def test_a_cash_reversal_before_its_movement_projects_when_the_movement_arrives():
    libro, original = _Libro(), new_uuid()
    reversa = _hecho(libro, "CASH_MOVEMENT_REVERSED",
                     {"amount": "50.00", "reversal_of_id": original},
                     tipo_agregado="cash_register.cash")
    CentralProjector(libro).run_once()
    assert _estado(libro, reversa)[1].startswith("DEPENDENCY_MISSING")
    _hecho(libro, "CASH_MOVEMENT_RECORDED", {"amount": "50.00", "direction": "INFLOW"},
           agregado=original, tipo_agregado="cash_register.cash")
    CentralProjector(libro).run_once()
    assert libro.movimientos[reversa["aggregate_id"]]["signed_amount"] == Decimal("-50.00")


def test_a_permanent_error_is_retried_only_on_request():
    libro = _Libro()
    mala = _hecho(libro, "SALE_COMPLETED", {"total": 1.5})            # float → ERROR
    CentralProjector(libro).run_once()
    assert CentralProjector(libro).run_once().errors == 0             # no se reintenta solo
    assert CentralProjector(libro).run_once(retry_errors=True).errors == 1
    assert _estado(libro, mala)[0] == "ERROR"


# ── orden del agregado en crédito, puntos y unidades ─────────────────────────
def _credito(libro, perfil, limite, version, *, estacion=ESTACION):
    return _hecho(libro, "CUSTOMER_CREDIT_LIMIT_UPDATED",
                  {"profile_id": perfil, "customer_id": new_uuid(), "credit_limit": limite},
                  agregado=perfil, tipo_agregado="customer_credit.credit_account",
                  version=version, estacion=estacion)


def test_an_older_credit_event_does_not_overwrite_a_newer_one():
    libro, perfil = _Libro(), new_uuid()
    _credito(libro, perfil, "5000.00", 2)
    CentralProjector(libro).run_once()
    viejo = _credito(libro, perfil, "1000.00", 1)          # p. ej. reintentado tarde
    corrida = CentralProjector(libro).run_once()
    assert libro.creditos[perfil]["credit_limit"] == Decimal("5000.00")
    assert corrida.skipped == 1
    estado, motivo = _estado(libro, viejo)
    assert estado == "SKIPPED" and motivo.startswith("SUPERSEDED")


def test_a_newer_credit_event_still_applies():
    libro, perfil = _Libro(), new_uuid()
    _credito(libro, perfil, "1000.00", 1)
    _credito(libro, perfil, "5000.00", 2)
    CentralProjector(libro).run_once()
    assert libro.creditos[perfil]["credit_limit"] == Decimal("5000.00")


def test_an_older_loyalty_event_does_not_rewrite_the_transaction():
    libro, membresia, transaccion = _Libro(), new_uuid(), new_uuid()

    def puntos(estado, version):
        return _hecho(libro, "LOYALTY_POINTS_REDEEMED",
                      {"ledger": {"transaction_id": transaccion, "loyalty_account_id": new_uuid(),
                                  "status": estado, "points_amount": "10",
                                  "transaction_type": "REDEEM"}},
                      agregado=membresia, tipo_agregado="loyalty.membership", version=version)

    puntos("CONFIRMED", 3)
    CentralProjector(libro).run_once()
    puntos("RESERVED", 2)
    CentralProjector(libro).run_once()
    assert libro.puntos[transaccion]["status"] == "CONFIRMED"


def test_an_older_org_unit_version_loses_even_with_a_later_station_clock():
    libro, unidad = _Libro(), new_uuid()

    def foto(nombre, version, updated_at):
        return _hecho(libro, "ORG_UNIT_UPDATED",
                      {"unit_id": unidad, "company_id": new_uuid(), "unit_type": "RETAIL_BRANCH",
                       "code": "PRI", "name": nombre, "status": "ACTIVE",
                       "updated_at": updated_at},
                      agregado=unidad, tipo_agregado="organization.org_unit", version=version)

    foto("Nueva", 2, (T0).isoformat())
    CentralProjector(libro).run_once()
    foto("Vieja", 1, (T0 + timedelta(hours=1)).isoformat())   # reloj adelantado
    CentralProjector(libro).run_once()
    assert libro.unidades[unidad]["name"] == "Nueva"


def test_another_station_is_not_ordered_by_version_here():
    """Las versiones de dos estaciones no se comparan entre sí: detectar esa
    concurrencia es SDLC-ARQ-SYNC-001."""
    libro, perfil = _Libro(), new_uuid()
    _credito(libro, perfil, "5000.00", 7)
    CentralProjector(libro).run_once()
    _credito(libro, perfil, "2000.00", 1, estacion=OTRA_ESTACION)
    CentralProjector(libro).run_once()
    assert libro.creditos[perfil]["credit_limit"] == Decimal("2000.00")
