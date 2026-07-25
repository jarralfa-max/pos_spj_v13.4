"""PROD-19 paso 8 — puente de permisos legacy → canónico + gating granular."""

from backend.application.products.authorization.permission_bridge import (
    CANONICAL_TO_LEGACY,
    legacy_codes_for,
    make_permission_checker,
)
from backend.application.products.permissions import ProductPermissions
from frontend.desktop.modules.products.presenter import ProductsPresenter


class _Session:
    def __init__(self, perms, es_admin=False):
        self._perms = set(perms)
        self.es_admin = es_admin

    def tiene_permiso(self, code):
        return self.es_admin or code in self._perms


def test_create_maps_to_legacy_crear():
    assert "PRODUCTOS.crear" in legacy_codes_for(ProductPermissions.CREATE)
    assert "CREAR_PRODUCTO" in legacy_codes_for(ProductPermissions.CREATE)


def test_checker_grants_via_legacy_code():
    has = make_permission_checker(_Session({"PRODUCTOS.crear"}))
    assert has(ProductPermissions.CREATE)
    assert not has(ProductPermissions.EDIT)  # no tiene PRODUCTOS.editar


def test_checker_grants_via_canonical_code():
    has = make_permission_checker(_Session({"PRODUCTS_EDIT"}))
    assert has(ProductPermissions.EDIT)


def test_checker_admin_all():
    has = make_permission_checker(_Session(set(), es_admin=True))
    assert has(ProductPermissions.CREATE) and has(ProductPermissions.EDIT)


def test_checker_none_session_denies():
    has = make_permission_checker(None)
    assert not has(ProductPermissions.CREATE)


def test_unmapped_permission_falls_back_to_view():
    assert legacy_codes_for("PRODUCTS_UNKNOWN_XYZ") == ("PRODUCTOS.ver",)


def test_mapping_covers_core_write_permissions():
    for code in (ProductPermissions.VIEW, ProductPermissions.CREATE,
                 ProductPermissions.EDIT, ProductPermissions.DEACTIVATE):
        assert code in CANONICAL_TO_LEGACY


# ── gating en el presenter ───────────────────────────────────────────────
def _presenter(perms, write=True):
    checker = make_permission_checker(_Session(perms))
    return ProductsPresenter(
        read_service_factory=lambda: None,
        write_service_factory=(lambda: None) if write else None,
        permission_checker=checker)


def test_presenter_gates_create_edit_by_permission():
    p = _presenter({"PRODUCTOS.crear"})
    assert p.can_create and not p.can_edit


def test_presenter_denies_when_no_write_factory():
    p = _presenter({"PRODUCTOS.crear"}, write=False)
    assert not p.can_create  # sin write factory no hay escritura aunque tenga permiso


def test_presenter_permissive_without_checker():
    p = ProductsPresenter(read_service_factory=lambda: None,
                          write_service_factory=lambda: None, permission_checker=None)
    assert p.can_create and p.can_edit  # compat: gating del menú ya restringió
