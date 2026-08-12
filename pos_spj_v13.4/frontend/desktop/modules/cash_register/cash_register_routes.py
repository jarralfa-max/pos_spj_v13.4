"""Navigation model for the cash register desktop workspace.

The route list is presentation metadata only: labels, tooltips, grouping and
feature keys. Pages decide how to resolve their own QueryService/UseCase
dependencies outside this file.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.cash_register.permissions import CashPermissions


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
        CashPermissions.ACCESS,
    ),
    CashRegisterRoute(
        "shifts",
        "Apertura y turnos",
        "Operacion",
        "Abrir, suspender, reanudar y cerrar preliminarmente un turno.",
        CashPermissions.SHIFT_VIEW,
    ),
    CashRegisterRoute(
        "ledger",
        "Ledger",
        "Operacion",
        "Movimientos inmutables, reversos y saldo reconstruible.",
        CashPermissions.MOVEMENT_VIEW,
    ),
    CashRegisterRoute(
        "blind_count",
        "Conteo ciego",
        "Cortes",
        "Captura de denominaciones sin revelar el esperado.",
        CashPermissions.BLIND_COUNT_VIEW,
    ),
    CashRegisterRoute(
        "x_cut",
        "Corte X",
        "Cortes",
        "Consulta parcial imprimible sin cierre del turno.",
        CashPermissions.X_CUT_VIEW,
    ),
    CashRegisterRoute(
        "z_cut",
        "Corte Z",
        "Cortes",
        "Consolidacion, diferencia, cierre, publicacion e impresion.",
        CashPermissions.Z_CUT_VIEW,
    ),
    CashRegisterRoute(
        "differences",
        "Diferencias",
        "Control",
        "Clasificacion, tolerancias, revision, resolucion y reincidencia.",
        CashPermissions.DIFFERENCE_VIEW,
    ),
    CashRegisterRoute(
        "handover",
        "Entrega de valores",
        "Control",
        "Preparacion, doble confirmacion, tesoreria y disputas.",
        CashPermissions.HANDOVER_VIEW,
    ),
    CashRegisterRoute(
        "refunds",
        "Reembolsos",
        "Control",
        "Metodo original, autorizacion, salida fisica y frontera financiera.",
        CashPermissions.REFUND_VIEW,
    ),
    CashRegisterRoute(
        "hardware",
        "Hardware",
        "Administracion",
        "Cajon, impresora, terminales, drivers, diagnostico y alertas.",
        CashPermissions.HARDWARE_VIEW,
    ),
    CashRegisterRoute(
        "configuration",
        "Configuracion",
        "Administracion",
        "Jerarquia, vigencias, denominaciones, limites, alertas y permisos.",
        CashPermissions.SETTINGS_VIEW,
    ),
)


def grouped_routes() -> list[tuple[str, list[CashRegisterRoute]]]:
    groups: list[tuple[str, list[CashRegisterRoute]]] = []
    for route in CASH_REGISTER_ROUTES:
        if not groups or groups[-1][0] != route.group:
            groups.append((route.group, []))
        groups[-1][1].append(route)
    return groups
