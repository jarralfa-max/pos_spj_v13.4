"""Authorization helpers for HR use cases."""

from __future__ import annotations

from collections.abc import Callable

from backend.domain.hr.exceptions import PermissionDeniedError

PermissionChecker = Callable[[str | None, str], bool]


class HRPermissionAuthorizer:
    def __init__(self, permission_checker: PermissionChecker | None = None) -> None:
        self._permission_checker = permission_checker or (lambda _user_id, _permission: True)

    def require(self, user_id: str | None, permission: str) -> None:
        if not self._permission_checker(user_id, permission):
            raise PermissionDeniedError(permission)
