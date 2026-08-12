"""Presenter bridge between Caja desktop UI and backend services.

The workspace remains a thin PyQt shell: it asks this presenter for session
state, capabilities and backend query/use-case dependencies. No SQL, no commits
and no legacy permission translation live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.application.cash_register.permissions import CashPermissions


@dataclass(frozen=True, slots=True)
class CashRegisterCapabilities:
    module_view: bool
    shift_view: bool
    ledger_view: bool
    blind_count_view: bool
    x_cut_view: bool
    z_cut_view: bool
    difference_view: bool
    handover_view: bool
    refund_view: bool
    hardware_view: bool
    configuration_view: bool


def resolve_cash_register_capabilities(can: Callable[[str], bool]) -> CashRegisterCapabilities:
    P = CashPermissions
    return CashRegisterCapabilities(
        module_view=can(P.ACCESS),
        shift_view=can(P.SHIFT_VIEW),
        ledger_view=can(P.MOVEMENT_VIEW),
        blind_count_view=can(P.BLIND_COUNT_START),
        x_cut_view=can(P.X_CUT_VIEW),
        z_cut_view=can(P.Z_CUT_VIEW),
        difference_view=can(P.DIFFERENCE_VIEW),
        handover_view=can(P.HANDOVER_PREPARE),
        refund_view=can(P.REFUND_REQUEST),
        hardware_view=can(P.HARDWARE_DIAGNOSE),
        configuration_view=can(P.SETTINGS_VIEW),
    )


class CashRegisterPresenter:
    def __init__(self, *, container, session_context=None) -> None:
        self._container = container
        self._session = session_context or getattr(container, "session", None)

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> CashRegisterCapabilities:
        return resolve_cash_register_capabilities(self.can)

    def session_summary(self) -> dict[str, str]:
        return {
            "user_id": str(getattr(self._session, "user_id", "") or ""),
            "user": str(getattr(self._session, "display_name", None)
                        or getattr(self._session, "nombre_completo", None)
                        or getattr(self._session, "username", None)
                        or getattr(self._session, "usuario", None)
                        or "Sesion activa"),
            "branch_id": str(getattr(self._session, "active_branch_id", None)
                             or getattr(self._session, "branch_id", None)
                             or getattr(self._container, "sucursal_id", "") or ""),
            "branch": str(getattr(self._session, "active_branch_name", None)
                          or getattr(self._session, "sucursal_nombre", None)
                          or getattr(self._container, "sucursal_nombre", "") or ""),
        }

    def active_shift_id(self) -> str | None:
        value = getattr(self._container, "active_cash_shift_id", None)
        return str(value) if value else None

    def active_count_context(self) -> tuple[str, str, str] | None:
        count_id = getattr(self._container, "active_cash_count_id", None)
        summary = self.session_summary()
        if count_id and summary["branch_id"] and summary["user_id"]:
            return str(count_id), summary["branch_id"], summary["user_id"]
        return None

    def query_service(self, key: str):
        candidates = {
            "configuration": ("cash_configuration_query_service",),
            "hardware": ("cash_devices_query_service", "cash_device_query_service"),
            "ledger": ("cash_ledger_query_service",),
            "blind_count": ("cash_blind_count_query_service", "blind_count_query_service"),
        }.get(key, ())
        for name in candidates:
            service = getattr(self._container, name, None)
            if service is not None:
                return service
        return None

    def backend_binding(self, key: str) -> str:
        bindings = {
            "overview": ("session", "cash_authorization_policy"),
            "shifts": (
                "cash_open_shift_uc",
                "cash_suspend_shift_uc",
                "cash_resume_shift_uc",
                "cash_begin_shift_closing_uc",
            ),
            "ledger": ("cash_ledger_query_service", "cash_register_movement_uc"),
            "blind_count": ("cash_blind_count_query_service",),
            "x_cut": ("cash_authorization_policy",),
            "z_cut": ("generate_z_cut_uc", "cash_authorization_policy"),
            "differences": ("cash_authorization_policy",),
            "handover": ("cash_authorization_policy",),
            "refunds": ("cash_authorization_policy",),
            "hardware": ("cash_devices_query_service", "cash_device_create_uc"),
            "configuration": ("cash_configuration_query_service",),
        }.get(key, ())
        connected = [name for name in bindings if getattr(self._container, name, None) is not None]
        if connected:
            return "Conectada al backend: " + ", ".join(connected)
        return "Sin binding backend disponible en este entorno."

    def status_cards(self) -> dict[str, object]:
        sync_state = "Lista"
        sync_repo = getattr(getattr(self._container, "cash_register_uow", None), "sync", None)
        if sync_repo is not None:
            sync_state = "Conectada"
        return {
            "shift": self.active_shift_id() or "Sin turno activo",
            "sync": sync_state,
            "alerts": 0,
        }
