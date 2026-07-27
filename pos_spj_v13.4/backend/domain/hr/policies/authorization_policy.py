"""Authorization policy for HR permissions."""

from __future__ import annotations

from backend.domain.hr.exceptions import PermissionDeniedError


class AuthorizationPolicy:
    def require(self, granted_permissions: set[str], required_permission: str) -> None:
        if required_permission not in granted_permissions:
            raise PermissionDeniedError(required_permission)
