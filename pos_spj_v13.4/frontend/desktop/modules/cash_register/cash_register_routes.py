"""Navigation model for the cash register desktop workspace.

The route list is presentation metadata only: labels, tooltips, grouping and
feature keys. Pages decide how to resolve their own QueryService/UseCase
dependencies outside this file.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.cash_register.permissions import CashPermissions
from frontend.desktop.modules.cash_register.view_models import CashCapabilities


@dataclass(frozen=True)
class CashRegisterRoute:
    key: str
    label: str
    group: str
    tooltip: str
    required_permission: str
    capability: str


CASH_REGISTER_ROUTES: tuple[CashRegisterRoute, ...] = (
    CashRegisterRoute(
        "overview",
        "Resumen",
        "OPERACION",
        "Estado operativo de caja, alertas y pendientes del turno.",
        CashPermissions.ACCESS,
        "module_view",
    ),
    CashRegisterRoute(
        "shifts",
        "Mi turno",
        "OPERACION",
        "Apertura y turnos: abrir, suspender, reanudar y cerrar preliminarmente.",
        CashPermissions.SHIFT_VIEW,
        "shift_view",
    ),
    CashRegisterRoute(
        "ledger",
        "Movimientos",
        "OPERACION",
        "Ledger operacional: entradas, salidas y saldo actual del turno.",
        CashPermissions.MOVEMENT_VIEW,
        "movement_view",
    ),
    CashRegisterRoute(
        "blind_count",
        "Arqueo y cierre",
        "CIERRE Y CONTROL",
        "Conteo ciego: captura de denominaciones sin revelar el esperado.",
        CashPermissions.BLIND_COUNT_VIEW,
        "count_view",
    ),
    CashRegisterRoute(
        "x_cut",
        "Corte X",
        "CIERRE Y CONTROL",
        "Consulta parcial imprimible sin cierre del turno.",
        CashPermissions.X_CUT_VIEW,
        "x_cut_view",
    ),
    CashRegisterRoute(
        "z_cut",
        "Corte Z",
        "CIERRE Y CONTROL",
        "Consolidacion, diferencia, cierre, publicacion e impresion.",
        CashPermissions.Z_CUT_VIEW,
        "z_cut_view",
    ),
    CashRegisterRoute(
        "differences",
        "Diferencias",
        "CIERRE Y CONTROL",
        "Clasificacion, tolerancias, revision, resolucion y reincidencia.",
        CashPermissions.DIFFERENCE_VIEW,
        "difference_view",
    ),
    CashRegisterRoute(
        "handover",
        "Entregas",
        "CIERRE Y CONTROL",
        "Entrega de valores: preparacion, doble confirmacion, tesoreria y disputas.",
        CashPermissions.HANDOVER_VIEW,
        "handover_view",
    ),
    CashRegisterRoute(
        "deposits",
        "Depositos preparados",
        "CIERRE Y CONTROL",
        "Valores preparados por Caja para entrega posterior a Tesoreria.",
        CashPermissions.DEPOSIT_VIEW,
        "deposit_view",
    ),
    CashRegisterRoute(
        "refunds",
        "Reembolsos",
        "CIERRE Y CONTROL",
        "Metodo original, autorizacion, salida fisica y frontera financiera.",
        CashPermissions.REFUND_VIEW,
        "refund_view",
    ),
    CashRegisterRoute(
        "payment_methods",
        "Medios de pago",
        "ADMINISTRACION",
        "Catalogo operativo de medios de pago y efecto fisico en cajon.",
        CashPermissions.PAYMENT_METHOD_VIEW,
        "payment_method_view",
    ),
    CashRegisterRoute(
        "payment_terminals",
        "Terminales de pago",
        "ADMINISTRACION",
        "Terminales de pago, estado operativo y conciliacion operacional.",
        CashPermissions.PAYMENT_TERMINAL_VIEW,
        "payment_terminal_view",
    ),
    CashRegisterRoute(
        "drawer_events",
        "Eventos de cajon",
        "ADMINISTRACION",
        "Aperturas de cajon auditadas con motivo y documento origen.",
        CashPermissions.DRAWER_EVENT_VIEW,
        "drawer_event_view",
    ),
    CashRegisterRoute(
        "hardware",
        "Hardware",
        "ADMINISTRACION",
        "Cajon, impresora, terminales, drivers, diagnostico y alertas.",
        CashPermissions.HARDWARE_VIEW,
        "hardware_view",
    ),
    CashRegisterRoute(
        "notifications",
        "Notificaciones",
        "ADMINISTRACION",
        "Policies, destinatarios, alertas in-app, WhatsApp, auditoria e idempotencia.",
        CashPermissions.NOTIFICATIONS_VIEW,
        "notification_view",
    ),
    CashRegisterRoute(
        "audit",
        "Auditoria",
        "ADMINISTRACION",
        "Bitacora operacional de Caja, autorizaciones, impresion y cambios sensibles.",
        CashPermissions.AUDIT_VIEW,
        "audit_view",
    ),
    CashRegisterRoute(
        "sync",
        "Sincronizacion",
        "ADMINISTRACION",
        "Outbox, secuencias, reintentos, conflictos y estado offline-first.",
        CashPermissions.SYNC_VIEW,
        "sync_view",
    ),
    CashRegisterRoute(
        "configuration",
        "Configuracion",
        "ADMINISTRACION",
        "Jerarquia, vigencias, denominaciones, limites, alertas y permisos.",
        CashPermissions.SETTINGS_VIEW,
        "settings_view",
    ),
)


def visible_routes(capabilities: CashCapabilities) -> tuple[CashRegisterRoute, ...]:
    """Return routes authorized by UI capabilities, not raw route permissions."""

    if not capabilities.module_view:
        return ()
    return tuple(
        route for route in CASH_REGISTER_ROUTES
        if bool(getattr(capabilities, route.capability, False))
    )


def grouped_routes(
    routes: tuple[CashRegisterRoute, ...] | list[CashRegisterRoute] | None = None,
) -> list[tuple[str, list[CashRegisterRoute]]]:
    groups: list[tuple[str, list[CashRegisterRoute]]] = []
    for route in CASH_REGISTER_ROUTES if routes is None else routes:
        if not groups or groups[-1][0] != route.group:
            groups.append((route.group, []))
        groups[-1][1].append(route)
    return groups
