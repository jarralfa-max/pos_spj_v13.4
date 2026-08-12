"""Presenter bridge between Caja desktop UI and backend services.

The workspace remains a thin PyQt shell: it asks this presenter for session
state, capabilities and backend query/use-case dependencies. No SQL, no commits
and no legacy permission translation live here.
"""

from __future__ import annotations

from collections.abc import Callable

from frontend.desktop.modules.cash_register.capability_resolver import resolve_cash_capabilities
from frontend.desktop.modules.cash_register.view_models import CashCapabilities


class CashRegisterPresenter:
    def __init__(
        self,
        *,
        session_context,
        query_services: dict[str, object] | None = None,
        use_cases: dict[str, object] | None = None,
        active_shift_provider: Callable[[], str | None] | None = None,
        active_count_context_provider: Callable[[], tuple[str, str, str] | None] | None = None,
    ) -> None:
        self._session = session_context
        self._query_services = dict(query_services or {})
        self._use_cases = dict(use_cases or {})
        self._active_shift_provider = active_shift_provider or (lambda: None)
        self._active_count_context_provider = active_count_context_provider or (lambda: None)

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> CashCapabilities:
        return resolve_cash_capabilities(self.can)

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
                             or ""),
            "branch": str(getattr(self._session, "active_branch_name", None)
                          or getattr(self._session, "sucursal_nombre", None)
                          or ""),
        }

    def active_shift_id(self) -> str | None:
        value = self._active_shift_provider()
        return str(value) if value else None

    def active_count_context(self) -> tuple[str, str, str] | None:
        return self._active_count_context_provider()

    def query_service(self, key: str):
        return self._query_services.get(key)

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
        connected = [
            name for name in bindings
            if name in self._query_services or name in self._use_cases
        ]
        if connected:
            return "Conectada al backend: " + ", ".join(connected)
        return "Sin binding backend disponible en este entorno."

    def status_cards(self) -> dict[str, object]:
        sync_state = "Lista"
        if "sync" in self._query_services or "sync" in self._use_cases:
            sync_state = "Conectada"
        return {
            "shift": self.active_shift_id() or "Sin turno activo",
            "sync": sync_state,
            "alerts": 0,
        }
