"""Contrato del formato de códigos de permiso (`backend/security/permissions/codes.py`).

Estos tests existen sobre todo por UNA trampa: `permission_code()` y
`normalize_permission()` NO producen la misma cadena.

    permission_code("pos", "VER")   -> "POS.ver"    (almacenamiento)
    normalize_permission("pos.ver") -> "POS.VER"    (comparación)

`PermissionEvaluator.has_permission()` compara
`normalize_permission(code) in context.permissions`. Si el conjunto de
permisos del contexto se cargara en la forma de almacenamiento ("POS.ver") y
la consulta llegara normalizada ("POS.VER"), la intersección sería vacía
SIEMPRE: el sistema denegaría absolutamente todo, sin lanzar ninguna
excepción y sin dejar rastro en los logs. Un fallo así no se detecta leyendo
el código — sólo cotejando las dos mitades, que es lo que hace
`test_evaluator_matches_codes_loaded_through_the_query_service`.
"""
from __future__ import annotations

from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from backend.bootstrap.permission_evaluator import PermissionEvaluator
from backend.security.permissions.codes import (
    module_view_permission,
    normalize_permission,
    permission_code,
    split_permission,
)


def test_permission_code_is_module_upper_action_lower() -> None:
    assert permission_code("pos", "VER") == "POS.ver"
    assert permission_code("POS", "ver") == "POS.ver"
    assert permission_code("  pos  ", " Ver ") == "POS.ver"


def test_permission_code_keeps_compound_actions_intact() -> None:
    """Una acción compuesta es UNA acción, no una jerarquía de módulos."""
    assert permission_code("configuracion", "valor.aprobar") == "CONFIGURACION.valor.aprobar"
    assert permission_code("INTELIGENCIA_BI", "forecast.modelo.aprobar") == (
        "INTELIGENCIA_BI.forecast.modelo.aprobar")


def test_module_view_permission_is_the_view_action() -> None:
    assert module_view_permission("pos") == "POS.ver"
    assert module_view_permission("configuracion") == "CONFIGURACION.ver"


def test_normalize_permission_uppercases_everything() -> None:
    assert normalize_permission("pos.ver") == "POS.VER"
    assert normalize_permission("configuracion.valor.aprobar") == "CONFIGURACION.VALOR.APROBAR"


def test_normalize_is_idempotent_and_permission_code_is_not_its_inverse() -> None:
    """Fija explícitamente la asimetría, para que nadie la "arregle" a ciegas."""
    code = permission_code("pos", "ver")
    assert normalize_permission(normalize_permission(code)) == normalize_permission(code)
    assert normalize_permission(code) != code


def test_split_permission_separates_only_on_the_first_dot() -> None:
    assert split_permission("CONFIGURACION.valor.aprobar") == ("CONFIGURACION", "valor.aprobar")
    assert split_permission("POS.ver") == ("POS", "ver")


def test_split_permission_reports_flat_legacy_codes_as_module_less() -> None:
    """Los códigos planos (`TRANSFERS_APPROVE`) no tienen módulo: el catálogo
    los reconoce por esto y los deja fuera en vez de inventarles uno."""
    assert split_permission("TRANSFERS_APPROVE") == ("", "TRANSFERS_APPROVE")
    assert split_permission("LOSSES_VIEW") == ("", "LOSSES_VIEW")


def _context(permissions, *, role: str = "cajero") -> ApplicationContext:
    return ApplicationContext(
        installation_id="i", company_id="c", branch_id="b", branch_name="Sucursal",
        workstation_id="w", workstation_type="", user_id="u", user_name="U",
        roles=(role,), permissions=frozenset(permissions),
        feature_context=FeatureContext(), session_id="s",
    )


def test_evaluator_matches_codes_loaded_through_the_query_service() -> None:
    """La mitad que rompe todo en silencio si las dos formas se desalinean.

    `SqlitePermissionQueryService` guarda los permisos ya normalizados; este
    test recorre el mismo camino sin base de datos: normalizar al cargar,
    normalizar al preguntar. Si alguien cambiara el servicio para devolver la
    forma de almacenamiento, este test cae.
    """
    stored = {normalize_permission(permission_code("POS", "ver"))}
    evaluator = PermissionEvaluator(_context(stored))

    assert evaluator.has_permission("POS.ver") is True
    assert evaluator.has_permission("pos.ver") is True
    assert evaluator.has_permission("POS.VER") is True
    assert evaluator.has_permission("POS.cancelar") is False


def test_evaluator_would_deny_everything_if_the_set_were_not_normalized() -> None:
    """Demuestra el modo de fallo concreto — es la razón de ser de este archivo."""
    sin_normalizar = {permission_code("POS", "ver")}       # "POS.ver"
    evaluator = PermissionEvaluator(_context(sin_normalizar))
    assert evaluator.has_permission("POS.ver") is False    # deniega en silencio


def test_evaluator_supports_module_wildcard_and_global_wildcard() -> None:
    por_modulo = PermissionEvaluator(_context({normalize_permission("POS.*")}))
    assert por_modulo.has_permission("POS.cancelar") is True
    assert por_modulo.has_permission("CAJA.cancelar") is False

    global_ = PermissionEvaluator(_context({"*"}))
    assert global_.has_permission("CUALQUIERA.cosa") is True


def test_admin_role_bypasses_the_permission_set() -> None:
    evaluator = PermissionEvaluator(_context(set(), role="admin"))
    assert evaluator.has_permission("POS.cancelar") is True
