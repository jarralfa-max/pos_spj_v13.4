"""SET-1: Settings/Device Management/Document Output/Customer Display must
register unified dotted `MODULE.action` permission codes in
`core/security/permission_catalog.py`, following the majority convention
already used by POS, CAJA, CRM, FINANZAS, PRODUCTOS, COMPRAS — not the flat
`CASH_*`-style codes (decision recorded in
docs/refactor/settings_refactor_execution_plan.md, "Avance SET-1").
"""
from backend.security.permissions.codes import module_view_permission, normalize_permission, permission_code
from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS

NEW_BOUNDED_CONTEXT_MODULES = ("CONFIGURACION", "DISPOSITIVOS", "DOCUMENTOS", "PANTALLA_CLIENTE")


def test_new_bounded_context_modules_are_registered() -> None:
    missing = [module for module in NEW_BOUNDED_CONTEXT_MODULES if module not in CANONICAL_MODULE_PERMISSIONS]
    assert not missing, "Missing canonical module permissions: " + ", ".join(missing)


def test_new_modules_have_no_duplicate_actions() -> None:
    for module in NEW_BOUNDED_CONTEXT_MODULES:
        actions = CANONICAL_MODULE_PERMISSIONS[module]
        assert len(actions) == len(set(actions)), f"{module} has duplicate actions"
        assert all(action == action.strip().lower() for action in actions), (
            f"{module} actions must be lowercase, no surrounding whitespace"
        )


def test_new_modules_use_dotted_module_action_codes() -> None:
    # Sanity check the shared helpers produce the same MODULE.action shape
    # already used by every other migrated bounded context (POS.ver, CRM.editar, ...).
    assert permission_code("configuracion", "valor.aprobar") == "CONFIGURACION.valor.aprobar"
    assert permission_code("dispositivos", "probar") == "DISPOSITIVOS.probar"
    assert module_view_permission("configuracion") == "CONFIGURACION.ver"
    assert normalize_permission("configuracion.valor.aprobar") == "CONFIGURACION.VALOR.APROBAR"


def test_configuracion_covers_settings_governance_scope_and_company_branch_station() -> None:
    actions = set(CANONICAL_MODULE_PERMISSIONS["CONFIGURACION"])
    # Configuration Governance value lifecycle (draft -> approve -> activate -> rollback)
    for expected in ("valor.crear", "valor.aprobar", "valor.activar", "valor.rollback"):
        assert expected in actions
    # Empresa/Sucursales/Estaciones
    for expected in ("empresa.editar", "sucursal.crear", "estacion.bloquear"):
        assert expected in actions
    # Integraciones/Feature flags/Apariencia live under Settings per the
    # execution plan (not split into their own top-level bounded contexts).
    for expected in ("integracion.secretos", "webhook.gestionar", "flag.activar", "tema.activar"):
        assert expected in actions


def test_dispositivos_covers_device_management_scope() -> None:
    actions = set(CANONICAL_MODULE_PERMISSIONS["DISPOSITIVOS"])
    for expected in ("asignar", "probar", "diagnostico.ver"):
        assert expected in actions


def test_documentos_covers_document_and_label_output_scope() -> None:
    actions = set(CANONICAL_MODULE_PERMISSIONS["DOCUMENTOS"])
    for expected in ("plantilla.aprobar", "trabajo.reintentar", "reimprimir_sensible", "etiqueta.imprimir"):
        assert expected in actions


def test_pantalla_cliente_covers_customer_display_and_advertising_scope() -> None:
    actions = set(CANONICAL_MODULE_PERMISSIONS["PANTALLA_CLIENTE"])
    for expected in ("contenido.aprobar", "campana.programar", "publicidad.gestionar"):
        assert expected in actions


def test_legacy_config_stub_keys_are_unchanged_menu_still_gates_on_them() -> None:
    # interfaz/menu_lateral.py's three existing buttons must keep working
    # until the unified CONFIGURACION navigation replaces them (later SET
    # phase) — this test guards against silently renaming/removing the
    # stub keys as a side effect of adding the new unified ones.
    assert CANONICAL_MODULE_PERMISSIONS["CONFIG_HARDWARE"] == ["ver"]
    assert CANONICAL_MODULE_PERMISSIONS["CONFIG_MODULOS"] == ["ver"]
    assert CANONICAL_MODULE_PERMISSIONS["CONFIG_SEGURIDAD"] == ["ver", "editar"]
