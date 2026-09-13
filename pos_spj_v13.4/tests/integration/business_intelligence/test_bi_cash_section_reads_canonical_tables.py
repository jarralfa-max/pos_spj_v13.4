"""La sección Caja del tablero lee el esquema canónico y devuelve cifras reales.

EL FALLO QUE ESTO FIJA
-----------------------
`BiCashQueryService` consultaba `movimientos_caja` y `cierres_caja`, que NO
EXISTEN: el contexto de Caja se reconstruyó con nombres canónicos en inglés y
este servicio se quedó apuntando a los legacy.

Y no se notaba. `_q` traga cualquier excepción y devuelve `[]`, así que la
sección "Caja" pintaba CEROS — exactamente lo mismo que se ve en un negocio que
no movió efectivo. Ni diálogo, ni excepción, ni hueco en la pantalla.

Lo encontró el recorrido de rutas (`test_every_bi_page_opens.py`) al vigilar el
logger `spj.bi`, que era la única señal que el código emitía.

POR QUÉ ESTA PRUEBA SIEMBRA LA CADENA ENTERA
----------------------------------------------
Con las claves foráneas activas, un corte Z exige turno, caja registradora,
cajón, terminal y un conteo ciego. Sembrar sólo la tabla final con FKs apagadas
habría "pasado" igual, pero no demostraría que los datos que el dominio escribe
de verdad son los que estas consultas saben leer —que es justo lo que falló—.

Las cifras se afirman a mano, no se recalculan con la misma consulta que se
está probando: 250 + 75 de entrada, 40 de salida, saldo 285.
"""
from __future__ import annotations

import logging
import sqlite3

import pytest

from backend.application.analytics.queries.bi_cash_query_service import (
    BiCashQueryService,
)
from backend.shared.ids import new_uuid

FECHA = "2026-09-01"
FUERA_DE_RANGO = "2026-08-01"


class _Filtros:
    """Lo que `DashboardFilters.resolved()` entrega a las consultas: rango de
    fechas y sucursal opcional."""

    def __init__(self, *, branch_id=None, date_from=FECHA, date_to=FECHA):
        self.branch_id = branch_id
        self.date_from = date_from
        self.date_to = date_to


@pytest.fixture
def conn():
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    base.up(c)
    c.commit()
    migrator.up(c)
    c.commit()
    # Activas a proposito: sin ellas se podria sembrar cualquier cosa y la
    # prueba no diria nada sobre datos que el dominio pueda escribir de verdad.
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


@pytest.fixture
def vigilante(caplog):
    """`_q` traga los fallos en `spj.bi.cash`; sin mirar el log, una consulta
    rota se lee como un dia sin movimientos."""
    caplog.set_level(logging.WARNING, logger="spj.bi.cash")
    return caplog


def _sucursal(conn, branch_id):
    """Caja registradora, cajon y terminal de una sucursal.

    Los nombres llevan sufijo unico porque el esquema exige que no se repitan
    dentro de una sucursal, y algunas pruebas abren dos turnos en la misma.

    El sufijo sale de la COLA del uuid, no de la cabeza: en UUIDv7 los primeros
    caracteres son la marca de tiempo, asi que dos generados en el mismo
    milisegundo la comparten y `reg[:8]` chocaba.
    """
    reg, drawer, term = new_uuid(), new_uuid(), new_uuid()
    sufijo = reg[-12:]
    ahora = f"{FECHA}T07:00:00+00:00"
    conn.execute("INSERT INTO cash_registers (id,branch_id,name,status,created_at,"
                 "updated_at) VALUES (?,?,?,'ACTIVE',?,?)",
                 (reg, branch_id, f"Caja {sufijo}", ahora, ahora))
    conn.execute("INSERT INTO cash_drawers (id,branch_id,register_id,name,status,"
                 "created_at,updated_at) VALUES (?,?,?,?,'ACTIVE',?,?)",
                 (drawer, branch_id, reg, f"Cajon {sufijo}", ahora, ahora))
    conn.execute("INSERT INTO pos_terminals (id,branch_id,register_id,name,status,"
                 "created_at,updated_at) VALUES (?,?,?,?,'ACTIVE',?,?)",
                 (term, branch_id, reg, f"Terminal {sufijo}", ahora, ahora))
    return reg, drawer, term


def _turno(conn, branch_id, user_id):
    """Un turno abierto. `cashier_user_id` es UNICO: el esquema impide que un
    mismo cajero tenga dos turnos a la vez, asi que abrir un segundo turno
    exige otro cajero —regla de dominio, no un estorbo de la prueba—."""
    reg, drawer, term = _sucursal(conn, branch_id)
    shift = new_uuid()
    conn.execute(
        "INSERT INTO cash_shifts (id,branch_id,register_id,drawer_id,terminal_id,"
        "cashier_user_id,opening_amount,opening_operation_id,status,opened_at)"
        " VALUES (?,?,?,?,?,?,?,?,'OPEN',?)",
        (shift, branch_id, reg, drawer, term, user_id, "1000", new_uuid(),
         f"{FECHA}T08:00:00+00:00"))
    return shift


def _movimiento(conn, shift, branch_id, user_id, *, direccion, monto,
                tipo=None, fecha=FECHA):
    """Un asiento del libro de caja. El tipo por defecto respeta el CHECK que
    liga `movement_type` con `direction`."""
    if tipo is None:
        tipo = "MANUAL_INCOME" if direccion == "INFLOW" else "MANUAL_WITHDRAWAL"
    conn.execute(
        "INSERT INTO cash_ledger_entries (id,shift_id,branch_id,movement_type,"
        "direction,amount,operation_id,recorded_by,concept,recorded_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (new_uuid(), shift, branch_id, tipo, direccion, str(monto), new_uuid(),
         user_id, "prueba", f"{fecha}T10:00:00+00:00"))


def _corte(conn, shift, branch_id, user_id, *, tipo="Z", esperado="1500",
           contado="1480", diferencia="-20", fecha=FECHA):
    """Un corte. Los Z exigen conteo ciego y cifras contadas (CHECK del
    esquema); los X no pueden tenerlas."""
    conteo = None
    if tipo == "Z":
        conteo = new_uuid()
        # `confirmed_at` no es decorativo: hay un CHECK que exige fecha si el
        # conteo se declara confirmado.
        conn.execute(
            "INSERT INTO cash_counts (id,shift_id,branch_id,counter_user_id,"
            "operation_id,total_counted,status,confirmed_at)"
            " VALUES (?,?,?,?,?,?,'CONFIRMED',?)",
            (conteo, shift, branch_id, user_id, new_uuid(), contado,
             f"{fecha}T21:55:00+00:00"))
    conn.execute(
        "INSERT INTO cash_cuts (id,shift_id,branch_id,cut_type,document_number,"
        "generated_by,expected_cash,counted_cash,difference,blind_count_id,"
        "operation_id,is_final,generated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (new_uuid(), shift, branch_id, tipo, f"DOC-{tipo}-{fecha}", user_id,
         esperado, contado if tipo == "Z" else None,
         diferencia if tipo == "Z" else None, conteo, new_uuid(),
         1 if tipo == "Z" else 0, f"{fecha}T22:00:00+00:00"))


@pytest.fixture
def caja(conn):
    """Un dia de caja: 250 + 75 de entrada, 40 de salida, un corte Z."""
    branch, user = new_uuid(), new_uuid()
    shift = _turno(conn, branch, user)
    _movimiento(conn, shift, branch, user, direccion="INFLOW", monto="250.00")
    _movimiento(conn, shift, branch, user, direccion="INFLOW", monto="75.50")
    _movimiento(conn, shift, branch, user, direccion="OUTFLOW", monto="40.25")
    _corte(conn, shift, branch, user)
    conn.commit()
    return {"branch": branch, "user": user, "shift": shift}


# -- lo que estaba roto ----------------------------------------------------
def test_the_totals_are_real_numbers_not_zeros(conn, caja, vigilante):
    """El fallo entero, en una linea: antes esto devolvia ceros."""
    totales = BiCashQueryService(conn).cash_totals(_Filtros())

    assert totales["ingresos"] == pytest.approx(325.50)
    assert totales["egresos"] == pytest.approx(40.25)
    assert totales["saldo"] == pytest.approx(285.25)
    assert totales["num_cortes"] == 1
    assert not vigilante.records, (
        f"la consulta trago un fallo: {[r.getMessage() for r in vigilante.records]}")


def test_no_query_falls_back_to_the_silent_empty(conn, caja, vigilante):
    """Las tres consultas, en una sola pasada: si alguna volviera a nombrar una
    tabla inexistente, `_q` lo taparia y solo se veria aqui."""
    servicio = BiCashQueryService(conn)
    servicio.cash_totals(_Filtros())
    servicio.daily_behavior(_Filtros())
    servicio.recent_cortes(_Filtros())

    assert not vigilante.records, (
        f"alguna consulta trago un fallo: "
        f"{[r.getMessage() for r in vigilante.records]}")


# -- el comportamiento diario ----------------------------------------------
def test_the_daily_behavior_groups_by_day(conn, caja, vigilante):
    branch, user = caja["branch"], caja["user"]
    otro_cajero = new_uuid()          # el primero ya tiene turno abierto
    otro = _turno(conn, branch, otro_cajero)
    _movimiento(conn, otro, branch, otro_cajero, direccion="INFLOW",
                monto="10.00", fecha="2026-09-02")
    conn.commit()

    dias = BiCashQueryService(conn).daily_behavior(
        _Filtros(date_from=FECHA, date_to="2026-09-02"))

    assert [d for d, _, _ in dias] == ["09-01", "09-02"]
    assert dias[0][1] == pytest.approx(325.50)
    assert dias[0][2] == pytest.approx(40.25)
    assert dias[1][1] == pytest.approx(10.00)


def test_movements_outside_the_range_are_excluded(conn, caja, vigilante):
    """Sin esto, el filtro de fechas podria no existir y la prueba de arriba
    pasaria igual."""
    branch = caja["branch"]
    otro_cajero = new_uuid()          # el primero ya tiene turno abierto
    viejo = _turno(conn, branch, otro_cajero)
    _movimiento(conn, viejo, branch, otro_cajero, direccion="INFLOW",
                monto="999.00", fecha=FUERA_DE_RANGO)
    conn.commit()

    assert BiCashQueryService(conn).cash_totals(
        _Filtros())["ingresos"] == pytest.approx(325.50)


def test_another_branch_is_excluded(conn, caja, vigilante):
    """El filtro por sucursal es la razon de que `_branch` exista; antes miraba
    `sucursal_id`, una columna que el esquema canonico no tiene."""
    otra, user = new_uuid(), new_uuid()
    turno = _turno(conn, otra, user)
    _movimiento(conn, turno, otra, user, direccion="INFLOW", monto="999.00")
    conn.commit()

    servicio = BiCashQueryService(conn)
    assert servicio.cash_totals(
        _Filtros(branch_id=caja["branch"]))["ingresos"] == pytest.approx(325.50)
    assert servicio.cash_totals(
        _Filtros(branch_id=otra))["ingresos"] == pytest.approx(999.00)
    # Sin sucursal se suman las dos.
    assert servicio.cash_totals(_Filtros())["ingresos"] == pytest.approx(1324.50)


# -- las tres decisiones del arreglo ---------------------------------------
def test_the_direction_column_decides_inflow_not_a_text_guess(conn, caja, vigilante):
    """DECISION 1. El codigo anterior adivinaba con
    `LOWER(tipo) IN ('ingreso','entrada',...)`. Un tipo canonico como
    `AUTHORIZED_PAID_OUT` no estaba en ninguna de las dos listas, asi que no
    contaba ni como ingreso ni como egreso: desaparecia del tablero.
    """
    branch, user, shift = caja["branch"], caja["user"], caja["shift"]
    _movimiento(conn, shift, branch, user, direccion="OUTFLOW", monto="30.00",
                tipo="AUTHORIZED_PAID_OUT")
    conn.commit()

    assert BiCashQueryService(conn).cash_totals(
        _Filtros())["egresos"] == pytest.approx(70.25)


def test_only_closing_cuts_are_counted(conn, caja, vigilante):
    """DECISION 2. Un corte X es una lectura intermedia, no un cierre. Contarlo
    inflaria el KPI de "Cortes" con lecturas que nadie cerro.
    """
    _corte(conn, caja["shift"], caja["branch"], caja["user"], tipo="X")
    conn.commit()

    servicio = BiCashQueryService(conn)
    assert servicio.cash_totals(_Filtros())["num_cortes"] == 1
    assert len(servicio.recent_cortes(_Filtros())) == 1


def test_the_cut_reports_expected_counted_and_difference(conn, caja, vigilante):
    """DECISION 3. `cash_cuts` no guarda la venta del periodo: guarda lo que
    DEBERIA haber en el cajon. Se exponen las tres cifras que un corte compara
    de verdad, en vez de llamar "Ventas" a `expected_cash`.
    """
    corte = BiCashQueryService(conn).recent_cortes(_Filtros())[0]

    assert corte["esperado"] == pytest.approx(1500.0)
    assert corte["contado"] == pytest.approx(1480.0)
    assert corte["diferencia"] == pytest.approx(-20.0)
    assert corte["fecha"].startswith(FECHA)
    assert "total_ventas" not in corte, (
        "'Ventas' no existe en un corte de caja; no debe reaparecer")


def test_an_x_cut_never_reports_invented_zeros(conn, vigilante):
    """Sin la decision 2, un corte X —que por CHECK no tiene `counted_cash` ni
    `difference`— saldria en la tabla con $0.00 en las dos, que se lee como un
    arqueo cuadrado cuando no hubo arqueo ninguno."""
    branch, user = new_uuid(), new_uuid()
    shift = _turno(conn, branch, user)
    _corte(conn, shift, branch, user, tipo="X")
    conn.commit()

    assert BiCashQueryService(conn).recent_cortes(_Filtros()) == []


# -- el estado vacio sigue siendo legitimo ---------------------------------
def test_an_empty_day_reports_zeros_without_swallowing(conn, vigilante):
    """Una caja sin movimientos SI da cero. La diferencia con el fallo es que
    ahora ese cero es un dato y no un error tapado —y el log lo distingue."""
    totales = BiCashQueryService(conn).cash_totals(_Filtros())

    assert totales == {"ingresos": 0.0, "egresos": 0.0, "saldo": 0.0,
                       "num_cortes": 0}
    assert BiCashQueryService(conn).daily_behavior(_Filtros()) == []
    assert not vigilante.records
