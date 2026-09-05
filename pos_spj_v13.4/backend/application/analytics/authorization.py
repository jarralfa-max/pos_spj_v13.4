"""Analytics/BI authorization — permission gate (BI-2, §104-119).

Every query service, forecast/recommendation/alert use case re-validates the
permission via an injected RBAC checker; the UI never carries authorization
logic (hiding a KPI card is not security). Sensitive financial metrics
(§117: gross sales, margin, profit, cash, CxC/CxP, payroll, capital) must be
gated by their own dedicated code (`FINANCE_SENSITIVE_VIEW` and friends), not
by the general `DASHBOARD_VIEW`/`FINANCE_VIEW` codes — a branch manager can
see the branch dashboard without seeing company cash position.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.analytics.permissions import ALL_ANALYTICS_PERMISSIONS
from backend.domain.analytics.exceptions import AnalyticsPermissionDeniedError


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AnalyticsAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_ANALYTICS_PERMISSIONS:
            raise AnalyticsPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            raise AnalyticsPermissionDeniedError(
                "AuthorizationChecker no configurado; autorización denegada"
            )
        if not user_id:
            raise AnalyticsPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise AnalyticsPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe for UI gating (§119: session + effective
        permissions + scope decide what a user sees — never `if rol == "..."`)."""
        try:
            self.require(user_id, permission_code)
            return True
        except AnalyticsPermissionDeniedError:
            return False
