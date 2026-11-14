"""SDLC-ARQ-SYNC-001 — el central ve lo que dos estaciones hacen sobre lo mismo.

Dos estaciones simuladas contra un libro EN MEMORIA que cumple el contrato como
PostgreSQL. La autoridad del inventario es la estación (decisión 2026-11-02): la
sobreventa entre cajas no se previene, se DETECTA. Un turno doble en la misma
caja viola §8 de los requisitos («sin turnos duplicados») y también se detecta.
Detectar no decide quién gana: el hecho se proyecta y el conflicto queda OPEN.
La misma batería contra PostgreSQL real está en
`tests/integration/central_pg/test_central_projection_pg.py` (CI).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.application.sync.central_projection import CentralProjector
from backend.shared.ids import new_uuid

T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
SUCURSAL, CAJA_A, CAJA_B = new_uuid(), new_uuid(), new_uuid()
ALMACEN, PRODUCTO, REGISTRO = new_uuid(), new_uuid(), new_uuid()


class _Central:
    def __init__(self):
        self.hechos: list[dict] = []
        self.registro: dict[str, tuple] = {}
        self.turnos: dict[str, dict] = {}
        self.movimientos: dict[str, dict] = {}
        self.conflictos: list[dict] = []

    def pending_facts(self, *, projector, limit, retry_errors=False):
        return [h for h in self.hechos if h["event_id"] not in self.registro][:limit]

    @contextmanager
    def savepoint(self):
        yield

    def log(self, *, event_id, projector, status, error):
        self.registro[event_id] = (status, error)

    def commit(self):
        pass

    def _estacion(self, event_id):
        return next(h["station_id"] for h in self.hechos if h["event_id"] == event_id)

    def open_cash_shift(self, row):
        self.turnos.setdefault(row["shift_id"], {**row, "status": "OPEN", "closed_at": None})

    def close_cash_shift(self, *, shift_id, closed_at, z_cut_id):
        if shift_id not in self.turnos:
            return False
        self.turnos[shift_id].update(status="CLOSED", closed_at=closed_at)
        return True

    def overlapping_open_shifts(self, *, register_id, shift_id, opened_at):
        return [{"shift_id": t["shift_id"], "station_id": t["station_id"]}
                for t in self.turnos.values()
                if t["register_id"] == register_id and t["shift_id"] != shift_id
                and (t["closed_at"] is None or t["closed_at"] > opened_at)]

    def add_stock_movement(self, rows):
        self.movimientos.setdefault(rows["movement"]["movement_id"], rows)

    def stock_position(self, *, product_id, warehouse_id):
        total, estaciones = Decimal("0"), set()
        for rows in self.movimientos.values():
            for e in rows["effects"]:
                if e["product_id"] == product_id and e["warehouse_id"] == warehouse_id:
                    total += e["quantity_delta"]
                    estaciones.add(self._estacion(rows["movement"]["event_id"]))
        return total, sorted(estaciones)

    def add_conflict(self, *, event_id, kind, details):
        self.conflictos.append({"event_id": event_id, "kind": kind, "details": details})


def _hecho(central, estacion, tipo, payload, *, agregado=None, cuando=T0):
    hecho = {"event_id": new_uuid(), "event_type": tipo, "aggregate_id": agregado or new_uuid(),
             "aggregate_type": "x", "aggregate_version": 1, "branch_id": SUCURSAL,
             "station_id": estacion, "occurred_at": cuando, "payload": payload}
    central.hechos.append(hecho)
    return hecho


def _abrir(central, estacion, *, cuando=T0, caja=REGISTRO):
    return _hecho(central, estacion, "CASH_SHIFT_OPENED",
                  {"opening_amount": "500.00", "register_id": caja,
                   "cashier_user_id": new_uuid()}, cuando=cuando)


def _mover(central, estacion, cantidad):
    return _hecho(central, estacion, "INVENTORY_MOVEMENT_POSTED",
                  {"warehouse_id": ALMACEN, "movement_type": "SALE",
                   "effects": [{"product_id": PRODUCTO, "quantity_delta": cantidad,
                                "weight_delta": "0"}]})


def _tipos(central):
    return [c["kind"] for c in central.conflictos]


# ── turno doble en la misma caja ─────────────────────────────────────────────
def test_two_stations_opening_the_same_register_is_a_visible_conflict():
    central = _Central()
    _abrir(central, CAJA_A)
    segundo = _abrir(central, CAJA_B, cuando=T0 + timedelta(minutes=5))
    CentralProjector(central).run_once()

    assert _tipos(central) == ["DOUBLE_OPEN_SHIFT"]
    conflicto = central.conflictos[0]
    assert conflicto["event_id"] == segundo["event_id"]
    assert conflicto["details"]["register_id"] == REGISTRO
    assert conflicto["details"]["stations"] == sorted([CAJA_A, CAJA_B])
    assert len(central.turnos) == 2          # detectar no oculta ninguno


def test_the_conflict_is_found_whichever_shift_arrives_first():
    central = _Central()
    _abrir(central, CAJA_B, cuando=T0 + timedelta(minutes=5))
    _abrir(central, CAJA_A)
    CentralProjector(central).run_once()
    assert _tipos(central) == ["DOUBLE_OPEN_SHIFT"]


def test_a_shift_opened_after_the_previous_one_closed_is_not_a_conflict():
    central = _Central()
    primero = _abrir(central, CAJA_A)
    _hecho(central, CAJA_A, "CASH_SHIFT_CLOSED",
           {"shift_id": primero["aggregate_id"], "closed_at": T0 + timedelta(hours=1)},
           agregado=primero["aggregate_id"])
    CentralProjector(central).run_once()
    _abrir(central, CAJA_B, cuando=T0 + timedelta(hours=2))
    CentralProjector(central).run_once()
    assert central.conflictos == []


def test_different_registers_never_conflict():
    central = _Central()
    _abrir(central, CAJA_A)
    _abrir(central, CAJA_B, caja=new_uuid())
    CentralProjector(central).run_once()
    assert central.conflictos == []


# ── sobreventa entre estaciones ──────────────────────────────────────────────
def test_two_stations_selling_the_same_stock_below_zero_is_detected():
    central = _Central()
    _mover(central, CAJA_A, "5")
    _mover(central, CAJA_A, "-4")
    sobreventa = _mover(central, CAJA_B, "-3")
    CentralProjector(central).run_once()

    assert _tipos(central) == ["CROSS_STATION_OVERSELL"]
    detalle = central.conflictos[0]["details"]
    assert central.conflictos[0]["event_id"] == sobreventa["event_id"]
    assert detalle["balance"] == "-2"
    assert detalle["stations"] == sorted([CAJA_A, CAJA_B])
    assert len(central.movimientos) == 3     # el movimiento se proyecta igual


def test_a_single_station_going_negative_is_its_own_policy_not_a_conflict():
    """Una estación puede vender en negativo si su política lo permite; el
    conflicto es entre estaciones."""
    central = _Central()
    _mover(central, CAJA_A, "1")
    _mover(central, CAJA_A, "-3")
    CentralProjector(central).run_once()
    assert central.conflictos == []


def test_an_inflow_never_raises_an_oversell_conflict():
    central = _Central()
    _mover(central, CAJA_A, "-3")
    _mover(central, CAJA_B, "1")
    CentralProjector(central).run_once()
    assert central.conflictos == []
