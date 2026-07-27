from __future__ import annotations

import json
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent
SCOPE_PATH = PACKAGE_ROOT / "docs" / "refactor" / "modules" / "configuracion_scope.json"
WORK_QUEUE_PATH = PACKAGE_ROOT / "docs" / "refactor" / "work_queue.json"

REQUIRED_CANONICAL_FILES = {
    "modulos/configuracion.py",
    "core/services/configuration_settings_service.py",
    "repositories/config_repository.py",
    "core/module_config.py",
    "modulos/config_hardware.py",
    "modulos/config_interfaz.py",
    "modulos/config_modules.py",
    "core/repositories/hardware_config_repository.py",
    "backend/application/queries/hardware_settings_query_service.py",
    "backend/application/queries/ticket_settings_query_service.py",
    "migrations/m050_hardware_config_canonical.py",
    "migrations/standalone/096_configuration_services_schema.py",
}


def _load_scope() -> dict:
    return json.loads(SCOPE_PATH.read_text(encoding="utf-8"))


def _load_work_queue() -> dict:
    return json.loads(WORK_QUEUE_PATH.read_text(encoding="utf-8"))


def test_configuracion_scope_inventory_is_done_and_points_to_identity_batch() -> None:
    scope = _load_scope()

    assert scope["module"] == "CONFIGURACION"
    assert scope["batch"] == "CONFIGURACION-01-SCOPE"
    assert scope["status"] == "DONE"
    assert scope["remaining_scope_violations"] == 0
    assert scope["next_batch"] == "CONFIGURACION-02-IDENTITY"


def test_configuracion_scope_canonical_files_exist_inside_real_package() -> None:
    scope = _load_scope()
    canonical_files = set(scope["canonical_files"])

    assert REQUIRED_CANONICAL_FILES.issubset(canonical_files)
    for relative_path in canonical_files:
        path = PACKAGE_ROOT / relative_path
        assert path.exists(), relative_path
        assert path.resolve().is_relative_to(PACKAGE_ROOT.resolve())


def test_configuracion_scope_classifies_shared_non_owned_configuration_surfaces() -> None:
    scope = _load_scope()
    shared_paths = {entry["path"]: entry["owner"] for entry in scope["shared_dependencies"]}

    assert shared_paths["core/repositories/whatsapp_config_repository.py"] == "WHATSAPP"
    assert shared_paths["modulos/ticket_designer.py"] == "TICKETS"
    assert shared_paths["modulos/fidelidad_config.py"] == "FIDELIDAD"
    assert shared_paths["modulos/rrhh_turnos.py"] == "RRHH"


def test_configuracion_work_queue_closed_scope_and_selected_identity() -> None:
    queue = _load_work_queue()
    batches = {batch["id"]: batch for batch in queue["batches"]}

    assert queue["phase"] == "CONFIGURACION"
    assert queue["active_batch"] == "CONFIGURACION-05-MUTATIONS"
    assert batches["CONFIGURACION-01-SCOPE"]["status"] == "DONE"
    assert batches["CONFIGURACION-01-SCOPE"]["violations"] == 0
    assert batches["CONFIGURACION-01-SCOPE"]["completed_actions"]
    assert batches["CONFIGURACION-01-SCOPE"]["forbidden_reselection"]
    assert batches["CONFIGURACION-02-IDENTITY"]["status"] == "DONE"
    assert batches["CONFIGURACION-02-IDENTITY"]["violations"] == 0
    assert batches["CONFIGURACION-03-UI"]["status"] == "DONE"
    assert batches["CONFIGURACION-03-UI"]["violations"] == 0
    assert batches["CONFIGURACION-03-UI"]["completed_actions"]
    assert batches["CONFIGURACION-03-UI"]["forbidden_reselection"]
    assert batches["CONFIGURACION-04-QUERIES"]["status"] == "DONE"
    assert batches["CONFIGURACION-04-QUERIES"]["violations"] == 0
    assert batches["CONFIGURACION-04-QUERIES"]["completed_actions"]
    assert batches["CONFIGURACION-04-QUERIES"]["forbidden_reselection"]


def test_no_configuracion_control_or_module_copy_exists_in_external_repo_root() -> None:
    external_duplicates = [
        REPO_ROOT / "docs" / "refactor" / "modules" / "configuracion_scope.json",
        REPO_ROOT / "modulos" / "configuracion.py",
        REPO_ROOT / "core" / "services" / "configuration_settings_service.py",
        REPO_ROOT / "repositories" / "config_repository.py",
    ]

    assert all(not path.exists() for path in external_duplicates)
