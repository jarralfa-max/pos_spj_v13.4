"""DesktopRouter errors — SHELL-10.

`RouteNotFoundError`/`ViewFactoryNotFoundError` (SHELL-9, `routing.errors`)
are reused as-is for unknown ids — this module only adds the errors that
are specific to *navigation-time* policy enforcement (permission, feature
flag, offline), which didn't exist before there was a router to enforce
them.
"""
from __future__ import annotations


class NavigationDeniedError(RuntimeError):
    """Base class for every reason `DesktopRouter.navigate()` can refuse to
    complete a navigation that resolved to a real, registered route."""


class NavigationPermissionDeniedError(NavigationDeniedError):
    """The current `ApplicationContext` lacks the route's
    `required_permission`."""


class NavigationFeatureDisabledError(NavigationDeniedError):
    """The route's `feature_flag` isn't enabled for the current context's
    branch."""


class NavigationRequiresOnlineError(NavigationDeniedError):
    """The route's `offline_policy` is `REQUIRES_ONLINE` and the current
    context reports no connectivity."""


class NoNavigationHistoryError(RuntimeError):
    """`go_back()`/`go_forward()` was called with nothing on the
    corresponding stack."""
