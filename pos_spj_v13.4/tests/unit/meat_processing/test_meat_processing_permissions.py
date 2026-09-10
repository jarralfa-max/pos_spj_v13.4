from backend.application.meat_processing.permissions import (
    ALL_MEAT_PROCESSING_PERMISSIONS,
    MeatProcessingPermissions,
)
from backend.security.permissions.codes import normalize_permission
from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS


def test_all_permission_values_are_unique_and_use_canonical_produccion_module():
    values = [value for name, value in vars(MeatProcessingPermissions).items()
              if not name.startswith("_") and isinstance(value, str)]
    assert len(values) == len(set(values)), "Permission codes must be unique"
    for value in values:
        assert value.startswith("PRODUCCION.")


def test_all_permissions_frozenset_matches_class_constants():
    assert MeatProcessingPermissions.ACCESS in ALL_MEAT_PROCESSING_PERMISSIONS
    assert MeatProcessingPermissions.ORDER_CLOSE in ALL_MEAT_PROCESSING_PERMISSIONS
    assert MeatProcessingPermissions.SLAUGHTER_ACCESS in ALL_MEAT_PROCESSING_PERMISSIONS
    assert len(ALL_MEAT_PROCESSING_PERMISSIONS) >= 50


def test_read_and_mutation_permissions_are_distinct_codes():
    assert MeatProcessingPermissions.ORDER_VIEW != MeatProcessingPermissions.ORDER_CREATE
    assert MeatProcessingPermissions.WEIGHT_VIEW != MeatProcessingPermissions.WEIGHT_CAPTURE
    assert (MeatProcessingPermissions.WEIGHT_CAPTURE
            != MeatProcessingPermissions.WEIGHT_MANUAL_OVERRIDE)


def test_every_permission_action_suffix_is_registered_in_the_canonical_catalog():
    catalog_actions = set(CANONICAL_MODULE_PERMISSIONS["PRODUCCION"])
    for value in ALL_MEAT_PROCESSING_PERMISSIONS:
        module, _, action = value.partition(".")
        assert module == "PRODUCCION"
        assert action in catalog_actions, f"{value} missing from CANONICAL_MODULE_PERMISSIONS"


def test_normalize_permission_matches_catalog_case_insensitive_contract():
    assert normalize_permission(MeatProcessingPermissions.ORDER_CREATE) == "PRODUCCION.ORDEN.CREAR"
