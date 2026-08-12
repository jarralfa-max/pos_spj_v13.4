from backend.application.meat_processing.permissions import MeatProcessingPermissions
from frontend.desktop.modules.meat_processing.navigation.meat_processing_sidebar import (
    MEAT_PROCESSING_NAV,
    SLAUGHTER_FEATURE_FLAG,
    visible_entries,
)


EXPECTED_STANDARD_TITLES = (
    "Resumen", "Plan de producción", "Órdenes", "Preparación", "En proceso",
    "Pesajes y consumos", "Despiece", "Productos derivados",
    "Empaque y etiquetado", "Lotes producidos", "Rendimientos", "Calidad",
    "Reprocesos", "Incidencias", "Trazabilidad", "Alertas", "Análisis",
    "Auditoría", "Configuración",
)

EXPECTED_SLAUGHTER_TITLES = (
    "Recepción de animales", "Lotes de animales", "Ante mortem",
    "Órdenes de sacrificio", "Faena", "Canales", "Post mortem",
    "Enfriamiento", "Clasificación de canales", "Decomisos",
)


def test_meat_processing_has_one_canonical_internal_navigation_contract():
    titles = tuple(entry.title for entry in MEAT_PROCESSING_NAV)
    assert titles == EXPECTED_STANDARD_TITLES + EXPECTED_SLAUGHTER_TITLES
    assert len({entry.page_id for entry in MEAT_PROCESSING_NAV}) == len(MEAT_PROCESSING_NAV)
    assert all(entry.permission.startswith("PRODUCCION.") for entry in MEAT_PROCESSING_NAV)


def test_standard_sections_have_no_feature_flag():
    standard = MEAT_PROCESSING_NAV[:len(EXPECTED_STANDARD_TITLES)]
    assert all(entry.feature_flag is None for entry in standard)


def test_slaughter_sections_are_all_gated_by_the_same_feature_flag():
    slaughter = MEAT_PROCESSING_NAV[len(EXPECTED_STANDARD_TITLES):]
    assert len(slaughter) == len(EXPECTED_SLAUGHTER_TITLES)
    assert all(entry.feature_flag == SLAUGHTER_FEATURE_FLAG for entry in slaughter)


def test_slaughter_sections_are_hidden_by_default_even_with_full_permissions():
    grant_everything = lambda permission: True  # noqa: E731
    entries = visible_entries(grant_everything)
    assert set(entry.title for entry, _badge in entries) == set(EXPECTED_STANDARD_TITLES)


def test_slaughter_sections_appear_once_flag_and_permission_are_both_granted():
    grant_everything = lambda permission: True  # noqa: E731
    enable_slaughter = lambda flag: flag == SLAUGHTER_FEATURE_FLAG  # noqa: E731
    entries = visible_entries(grant_everything, has_feature=enable_slaughter)
    titles = {entry.title for entry, _badge in entries}
    assert titles == set(EXPECTED_STANDARD_TITLES) | set(EXPECTED_SLAUGHTER_TITLES)


def test_visible_entries_are_least_privilege_and_badges_are_external():
    grants = {MeatProcessingPermissions.DASHBOARD_VIEW, MeatProcessingPermissions.ORDER_VIEW}
    entries = visible_entries(
        lambda permission: permission in grants,
        {"orders_needing_attention": 3, "critical_alerts": 99},
    )
    assert [(entry.title, badge) for entry, badge in entries] == [
        ("Resumen", None), ("Órdenes", 3),
    ]


def test_read_access_does_not_infer_sensitive_sections():
    entries = visible_entries(lambda permission: permission == MeatProcessingPermissions.VIEW)
    assert entries == ()


def test_feature_flag_alone_without_permission_does_not_reveal_slaughter_sections():
    enable_slaughter = lambda flag: True  # noqa: E731
    entries = visible_entries(lambda permission: False, has_feature=enable_slaughter)
    assert entries == ()
