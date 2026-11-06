"""Suspend/Resume policies (master prompt §40-41). Pure functions — the
caller (application layer) fetches the current suspended-sale count and the
configured limits; these policies only decide, never query."""

from __future__ import annotations

from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import (
    SaleEmptyCartError,
    SaleInvalidStateError,
    SaleResumeNotAllowedError,
    SaleSuspensionLimitError,
)
from backend.domain.sales.policies.lifecycle_policies import SaleLifecyclePolicy


class SaleSuspensionPolicy:
    @staticmethod
    def ensure_can_suspend(
        *, status: SaleStatus, line_count: int,
        current_suspended_count: int, max_suspended_sales: int,
    ) -> None:
        SaleLifecyclePolicy.ensure_transition(current=status, target=SaleStatus.SUSPENDED)
        if line_count <= 0:
            raise SaleEmptyCartError("No se puede suspender un carrito vacío")
        if max_suspended_sales > 0 and current_suspended_count >= max_suspended_sales:
            raise SaleSuspensionLimitError(
                f"Se alcanzó el máximo de ventas suspendidas ({max_suspended_sales})")


class SaleResumptionPolicy:
    """§41: `allow_cross_workstation_resume` is a configuration flag the
    caller resolves from ModuleSettingsService — this policy only enforces it
    once given.

    SDLC-ARQ-SESS-003: una venta suspendida es de su cajero. Reanudar la de
    otro no es configuración sino una excepción que el caso de uso autoriza
    (permiso o autorización en caliente) antes de pasar
    `allow_cross_user_resume=True`; por defecto se niega."""

    @staticmethod
    def ensure_can_resume(
        *, status: SaleStatus,
        owner_user_id: str, resuming_user_id: str,
        suspended_at_workstation_id: str, resuming_workstation_id: str,
        allow_cross_user_resume: bool = False,
        allow_cross_workstation_resume: bool = True,
    ) -> None:
        try:
            SaleLifecyclePolicy.ensure_transition(current=status, target=SaleStatus.ACTIVE)
        except SaleInvalidStateError as exc:
            raise SaleResumeNotAllowedError(str(exc)) from exc
        if not allow_cross_user_resume and resuming_user_id != owner_user_id:
            raise SaleResumeNotAllowedError(
                "Esta venta suspendida solo puede reanudarla el cajero que la atiende")
        if (not allow_cross_workstation_resume
                and resuming_workstation_id != suspended_at_workstation_id):
            raise SaleResumeNotAllowedError(
                "Esta venta suspendida solo puede reanudarse en la misma estación")
