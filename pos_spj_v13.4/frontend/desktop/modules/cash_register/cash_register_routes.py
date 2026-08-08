"""Navigation model for the cash register desktop workspace.

The route list is presentation metadata only: labels, tooltips, grouping and
feature keys. Pages decide how to resolve their own QueryService/UseCase
dependencies outside this file.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CashRegisterRoute:
    key: str
    label: str
    group: str
    tooltip: str
    required_permission: str


CASH_REGISTER_ROUTES: tuple[CashRegisterRoute, ...] = (
    CashRegisterRoute(
        "overview",
        "Resumen",
        "Operacion",
        "Estado operativo de caja, alertas y pendientes del turno.",
        "cash_register.view",
    ),
    CashRegisterRoute(
        "shifts",
        "Apertura y turnos",
        "Operacion",
        "Abrir, suspender, reanudar y cerrar preliminarmente un turno.",
        "cash_register.shift.view",
    ),
    CashRegisterRoute(
        "ledger",
        "Ledger",
        "Operacion",
        "Movimientos inmutables, reversos y saldo reconstruible.",
        "cash_register.ledger.view",
    ),
    CashRegisterRoute(
        "blind_count",
        "Conteo ciego",
        "Cortes",
        "Captura de denominaciones sin revelar el esperado.",
        "cash_register.count.view",
    ),
    CashRegisterRoute(
        "x_cut",
        "Corte X",
        "Cortes",
        "Consulta parcial imprimible sin cierre del turno.",
        "cash_register.x_cut.view",
    ),
    CashRegisterRoute(
        "z_cut",
        "Corte Z",
        "Cortes",
        "Consolidacion, diferencia, cierre, publicacion e impresion.",
        "cash_register.z_cut.view",
    ),
    CashRegisterRoute(
        "differences",
        "Diferencias",
        "Control",
        "Clasificacion, tolerancias, revision, resolucion y reincidencia.",
        "cash_register.difference.view",
    ),
    CashRegisterRoute(
        "handover",
        "Entrega de valores",
        "Control",
        "Preparacion, doble confirmacion, tesoreria y disputas.",
        "cash_register.handover.view",
    ),
    CashRegisterRoute(
        "refunds",
        "Reembolsos",
        "Control",
        "Metodo original, autorizacion, salida fisica y frontera financiera.",
        "cash_register.refund.view",
    ),
    CashRegisterRoute(
        "hardware",
        "Hardware",
        "Administracion",
        "Cajon, impresora, terminales, drivers, diagnostico y alertas.",
        "cash_register.hardware.view",
    ),
    CashRegisterRoute(
        "configuration",
        "Configuracion",
        "Administracion",
        "Jerarquia, vigencias, denominaciones, limites, alertas y permisos.",
        "cash_register.configuration.view",
    ),
)


def grouped_routes() -> list[tuple[str, list[CashRegisterRoute]]]:
    groups: list[tuple[str, list[CashRegisterRoute]]] = []
    for route in CASH_REGISTER_ROUTES:
        if not groups or groups[-1][0] != route.group:
            groups.append((route.group, []))
        groups[-1][1].append(route)
    return groups
