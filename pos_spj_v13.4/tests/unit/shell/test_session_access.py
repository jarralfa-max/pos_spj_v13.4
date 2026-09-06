"""`frontend/desktop/shell/modules/session_access.py` — la derivación que
antes estaba copiada, y rota, en varios `shell_registration.py`.

Las dos sesiones vivas se representan con dobles que exponen exactamente el
subconjunto real: `SessionContext` y `LegacySessionAdapter` hablan
`tiene_permiso`/`permisos`/`active_branch_id`, nunca
`has_permission`/`permissions`/`branch_id`.
"""
from __future__ import annotations

from frontend.desktop.shell.modules.session_access import (
    active_branch_id,
    actor_user_id,
    sidebar_permission_checker,
)


class _SpanishApiSession:
    """Forma de `SessionContext` y de `LegacySessionAdapter`."""

    user_id = "u1"
    active_branch_id = "b1"
    sucursal_id = "b1"

    def __init__(self, permisos=frozenset()):
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


class _CodesOnlySession:
    """Sesión que expone `permisos` pero no `tiene_permiso` — el respaldo."""

    def __init__(self, permisos=frozenset()):
        self.permisos = frozenset(permisos)


class _EnglishApiSession:
    """La forma que el código roto SUPONÍA. No existe en producción; se
    conserva para probar que el respaldo por códigos no la resucita."""

    def __init__(self, permissions=frozenset()):
        self.permissions = frozenset(permissions)

    def has_permission(self, code):
        return code in self.permissions


def test_no_session_grants_nothing():
    assert sidebar_permission_checker(None)("CUALQUIERA") is False
    assert active_branch_id(None) is None
    assert actor_user_id(None) is None


def test_spanish_api_session_is_honoured():
    """El defecto original: esto devolvía False y vaciaba el sidebar."""
    checker = sidebar_permission_checker(_SpanishApiSession({"BI_VIEW"}))
    assert checker("BI_VIEW") is True
    assert checker("OTRO") is False


def test_permission_codes_are_the_fallback_when_there_is_no_method():
    checker = sidebar_permission_checker(_CodesOnlySession({"bi_view"}))
    assert checker("BI_VIEW") is True, "el respaldo compara sin distinguir mayúsculas"
    assert checker("OTRO") is False


def test_wildcard_grants_everything_in_the_fallback():
    assert sidebar_permission_checker(_CodesOnlySession({"*"}))("LO_QUE_SEA") is True


def test_an_english_api_session_is_not_silently_trusted():
    """No se añade soporte para una forma que ninguna sesión real tiene:
    sin `tiene_permiso` ni `permisos`, se niega."""
    assert sidebar_permission_checker(_EnglishApiSession({"BI_VIEW"}))("BI_VIEW") is False


def test_branch_prefers_the_canonical_attribute():
    class _Divergent:
        active_branch_id = "canonica"
        sucursal_id = "espejo"
        branch_id = "otra"

    assert active_branch_id(_Divergent()) == "canonica"


def test_branch_falls_back_through_the_legacy_names():
    class _OnlyMirror:
        active_branch_id = ""
        sucursal_id = "espejo"

    assert active_branch_id(_OnlyMirror()) == "espejo"

    class _OnlyEnglish:
        branch_id = "otra"

    assert active_branch_id(_OnlyEnglish()) == "otra"


def test_empty_values_do_not_leak_as_strings():
    class _Empty:
        active_branch_id = ""
        sucursal_id = ""
        user_id = ""

    assert active_branch_id(_Empty()) is None
    assert actor_user_id(_Empty()) is None


def test_actor_is_read_and_stringified():
    assert actor_user_id(_SpanishApiSession()) == "u1"
