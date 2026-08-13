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
        "Operacion",
        "Estado operativo de caja, alertas y pendientes del turno.",
        CashPermissions.ACCESS,
        "module_view",
    ),
    CashRegisterRoute(
        "shifts",
        "Apertura y turnos",
        "Operacion",
        "Abrir, suspender, reanudar y cerrar preliminarmente un turno.",
        CashPermissions.SHIFT_VIEW,
        "shift_view",
    ),
    CashRegisterRoute(
        "ledger",
        "Ledger",
        "Operacion",
        "Movimientos inmutables, reversos y saldo reconstruible.",
        CashPermissions.MOVEMENT_VIEW,
        "movement_view",
    ),
    CashRegisterRoute(
        "blind_count",
        "Conteo ciego",
        "Cortes",
        "Captura de denominaciones sin revelar el esperado.",
        CashPermissions.BLIND_COUNT_VIEW,
        "count_view",
    ),
    CashRegisterRoute(
        "x_cut",
        "Corte X",
        "Cortes",
        "Consulta parcial imprimible sin cierre del turno.",
        CashPermissions.X_CUT_VIEW,
        "x_cut_view",
    ),
    CashRegisterRoute(
        "z_cut",
        "Corte Z",
        "Cortes",
        "Consolidacion, diferencia, cierre, publicacion e impresion.",
        CashPermissions.Z_CUT_VIEW,
        "z_cut_view",
    ),
    CashRegisterRoute(
        "differences",
        "Diferencias",
        "Control",
        "Clasificacion, tolerancias, revision, resolucion y reincidencia.",
        CashPermissions.DIFFERENCE_VIEW,
        "difference_view",
    ),
    CashRegisterRoute(
        "handover",
        "Entrega de valores",
        "Control",
        "Preparacion, doble confirmacion, tesoreria y disputas.",
        CashPermissions.HANDOVER_VIEW,
        "handover_view",
    ),
    CashRegisterRoute(
        "deposits",
        "Depositos preparados",
        "Control",
        "Valores preparados por Caja para entrega posterior a Tesoreria.",
        CashPermissions.DEPOSIT_VIEW,
        "deposit_view",
    ),
    CashRegisterRoute(
        "refunds",
        "Reembolsos",
        "Control",
        "Metodo original, autorizacion, salida fisica y frontera financiera.",
        CashPermissions.REFUND_VIEW,
        "refund_view",
    ),
    CashRegisterRoute(
        "payment_methods",
        "Medios de pago",
        "Administracion",
        "Catalogo operativo de medios de pago y efecto fisico en cajon.",
        CashPermissions.PAYMENT_METHOD_VIEW,
        "payment_method_view",
    ),
    CashRegisterRoute(
        "payment_terminals",
        "Terminales de pago",
        "Administracion",
        "Terminales de pago, estado operativo y conciliacion operacional.",
        CashPermissions.PAYMENT_TERMINAL_VIEW,
        "payment_terminal_view",
    ),
    CashRegisterRoute(
        "drawer_events",
        "Eventos de cajon",
        "Administracion",
        "Aperturas de cajon auditadas con motivo y documento origen.",
        CashPermissions.DRAWER_EVENT_VIEW,
        "drawer_event_view",
    ),
    CashRegisterRoute(
        "hardware",
        "Hardware",
        "Administracion",
        "Cajon, impresora, terminales, drivers, diagnostico y alertas.",
        CashPermissions.HARDWARE_VIEW,
        "hardware_view",
    ),
    CashRegisterRoute(
        "notifications",
        "Notificaciones",
        "Administracion",
        "Policies, destinatarios, alertas in-app, WhatsApp, auditoria e idempotencia.",
        CashPermissions.NOTIFICATIONS_VIEW,
        "notification_view",
    ),
    CashRegisterRoute(
        "audit",
        "Auditoria",
        "Administracion",
        "Bitacora operacional de Caja, autorizaciones, impresion y cambios sensibles.",
        CashPermissions.AUDIT_VIEW,
        "audit_view",
    ),
    CashRegisterRoute(
        "sync",
        "Sincronizacion",
        "Administracion",
        "Outbox, secuencias, reintentos, conflictos y estado offline-first.",
        CashPermissions.SYNC_VIEW,
        "sync_view",
    ),
    CashRegisterRoute(
        "configuration",
        "Configuracion",
        "Administracion",
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
