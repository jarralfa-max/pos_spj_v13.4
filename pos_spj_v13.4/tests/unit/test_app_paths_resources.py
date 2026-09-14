"""Installed binaries, bundled resources and writable data have distinct roots."""
from pathlib import Path
import sys

import pytest

from backend.shared.app_paths import AppPaths


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = PACKAGE_ROOT / ".test_tmp" / "branding-path-contract"


@pytest.fixture(autouse=True)
def path_environment(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("SPJ_APP_DATA_DIR", str(CONTRACT_ROOT / "user-data"))


@pytest.mark.parametrize("factory", [AppPaths, AppPaths.from_environment])
def test_source_resources_do_not_follow_working_directory(factory, monkeypatch):
    monkeypatch.chdir(PACKAGE_ROOT.parent)

    paths = factory()

    assert paths.root == PACKAGE_ROOT
    assert paths.resource_root == PACKAGE_ROOT
    assert paths.user_data_dir == CONTRACT_ROOT / "user-data"


@pytest.mark.parametrize("factory", [AppPaths, AppPaths.from_environment])
@pytest.mark.parametrize("bundle", ["temporary/_MEI12345", "installed/_internal"])
def test_frozen_resources_use_bundle_without_moving_binary_or_data(factory, bundle, monkeypatch):
    install_root = CONTRACT_ROOT / "installed"
    bundle_root = CONTRACT_ROOT / bundle
    monkeypatch.setattr(sys, "frozen", True)
    monkeypatch.setattr(sys, "executable", str(install_root / "spj.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_root), raising=False)

    paths = factory()

    assert paths.resource_root == bundle_root
    assert paths.root == install_root
    assert paths.user_data_dir == CONTRACT_ROOT / "user-data"
    assert paths.sqlite_database_path() == CONTRACT_ROOT / "user-data" / "db" / "spj.sqlite3"
    assert paths.backups_dir == CONTRACT_ROOT / "user-data" / "backups"
    assert paths.downloads_dir == CONTRACT_ROOT / "user-data" / "updater" / "downloads"


@pytest.mark.parametrize("factory", [AppPaths, AppPaths.from_environment])
def test_frozen_installation_without_extraction_uses_binary_root(factory, monkeypatch):
    install_root = CONTRACT_ROOT / "installed"
    monkeypatch.setattr(sys, "frozen", True)
    monkeypatch.setattr(sys, "executable", str(install_root / "spj.exe"))

    paths = factory()

    assert paths.resource_root == install_root
    assert paths.root == install_root


def test_explicit_resource_directory_overrides_bundle_and_base(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True)
    monkeypatch.setattr(sys, "_MEIPASS", str(CONTRACT_ROOT / "bundle"), raising=False)
    paths = AppPaths(
        base_dir=CONTRACT_ROOT / "binary",
        resource_dir=CONTRACT_ROOT / "artwork",
        data_dir=CONTRACT_ROOT / "persistent",
    )

    assert paths.resource_root == CONTRACT_ROOT / "artwork"
    assert paths.root == CONTRACT_ROOT / "binary"
    assert paths.user_data_dir == CONTRACT_ROOT / "persistent"


def test_explicit_base_directory_is_a_complete_bundle_override(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True)
    monkeypatch.setattr(sys, "_MEIPASS", str(CONTRACT_ROOT / "bundle"), raising=False)
    paths = AppPaths(base_dir=CONTRACT_ROOT / "test-installation")

    assert paths.resource_root == paths.root == CONTRACT_ROOT / "test-installation"


def test_unfrozen_process_ignores_stray_extraction_attribute(monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(CONTRACT_ROOT / "stray"), raising=False)

    assert AppPaths.from_environment().resource_root == PACKAGE_ROOT


def test_environment_paths_keep_resolved_bundle_after_environment_changes(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True)
    monkeypatch.setattr(sys, "executable", str(CONTRACT_ROOT / "installed" / "spj.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(CONTRACT_ROOT / "bundle"), raising=False)
    paths = AppPaths.from_environment()
    monkeypatch.setattr(sys, "_MEIPASS", str(CONTRACT_ROOT / "changed"))

    assert paths.resource_root == CONTRACT_ROOT / "bundle"
    assert paths.root == CONTRACT_ROOT / "installed"


def test_ensure_directories_never_creates_or_writes_bundle(monkeypatch):
    created = []
    monkeypatch.setattr(Path, "mkdir", lambda path, **kwargs: created.append(path))
    paths = AppPaths(
        base_dir=CONTRACT_ROOT / "binary",
        resource_dir=CONTRACT_ROOT / "bundle",
        data_dir=CONTRACT_ROOT / "persistent",
    )

    assert paths.ensure_directories() is paths
    assert created
    assert all(path == paths.user_data_dir or paths.user_data_dir in path.parents for path in created)
    assert paths.root not in created
    assert paths.resource_root not in created
