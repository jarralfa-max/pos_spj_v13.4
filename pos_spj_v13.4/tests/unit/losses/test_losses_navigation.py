from backend.application.losses.permissions import LossPermissions
from frontend.desktop.modules.losses.navigation.losses_sidebar import (
    LOSSES_NAV, visible_entries,
)


EXPECTED_TITLES = (
    "Resumen", "Registro", "Pendientes", "Producción", "Inventario",
    "Caducidad y daño", "Calidad y decomisos", "Rendimientos",
    "Recuperación", "Disposición", "Investigaciones",
    "Acciones correctivas", "Alertas", "Análisis", "Auditoría",
    "Configuración",
)


def test_losses_has_one_canonical_internal_navigation_contract():
    assert tuple(entry.title for entry in LOSSES_NAV) == EXPECTED_TITLES
    assert len({entry.page_id for entry in LOSSES_NAV}) == len(LOSSES_NAV)
    assert all(entry.permission.startswith("LOSSES_") for entry in LOSSES_NAV)


def test_visible_entries_are_least_privilege_and_badges_are_external():
    grants = {LossPermissions.OVERVIEW_VIEW, LossPermissions.PENDING_VIEW}
    entries = visible_entries(
        lambda permission: permission in grants,
        {"pending_review": 7, "critical_alerts": 99},
    )
    assert [(entry.title, badge) for entry, badge in entries] == [
        ("Resumen", None), ("Pendientes", 7),
    ]


def test_read_access_does_not_infer_sensitive_sections():
    entries = visible_entries(lambda permission: permission == LossPermissions.VIEW)
    assert entries == ()
