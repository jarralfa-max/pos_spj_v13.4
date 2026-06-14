import json
import shutil

from .refactor_control_helpers import BOOTSTRAP, MODULES_DIR, PACKAGE_ROOT, REQUIRED_CONTROL_PATHS, REFACTOR_DIR


def test_refactor_control_files_exist_in_canonical_tree():
    missing = [str(path) for path in REQUIRED_CONTROL_PATHS if not path.is_file()]
    assert not missing
    assert REFACTOR_DIR.is_dir()
    assert MODULES_DIR.is_dir()


def test_bootstrap_refactor_state_is_idempotent_on_canonical_tree():
    result = BOOTSTRAP.bootstrap_refactor_state()
    assert result == {"created": [], "repaired": []}


def test_bootstrap_refactor_state_rejects_external_root_paths():
    outside_package_path = PACKAGE_ROOT.parent / "docs" / "refactor"
    try:
        BOOTSTRAP.bootstrap_refactor_state(outside_package_path)
    except ValueError as exc:
        assert "inside package root" in str(exc)
    else:
        raise AssertionError("external refactor path was accepted")


def test_bootstrap_refactor_state_creates_missing_control_tree():
    package_tmp = PACKAGE_ROOT / ".tmp_refactor_bootstrap_create"
    if package_tmp.exists():
        shutil.rmtree(package_tmp)
    try:
        result = BOOTSTRAP.bootstrap_refactor_state(package_tmp / "docs" / "refactor")
        assert result["created"]
        for path in REQUIRED_CONTROL_PATHS:
            relative = path.relative_to(REFACTOR_DIR)
            assert (package_tmp / "docs" / "refactor" / relative).is_file()
    finally:
        if package_tmp.exists():
            shutil.rmtree(package_tmp)


def test_bootstrap_refactor_state_repairs_invalid_json_with_backup():
    package_tmp = PACKAGE_ROOT / ".tmp_refactor_bootstrap_repair"
    if package_tmp.exists():
        shutil.rmtree(package_tmp)
    try:
        base_path = package_tmp / "docs" / "refactor"
        BOOTSTRAP.bootstrap_refactor_state(base_path)
        state_path = base_path / "refactor_state.json"
        state_path.write_text("{invalid-json", encoding="utf-8")

        result = BOOTSTRAP.bootstrap_refactor_state(base_path)

        assert "refactor_state.json" in "\n".join(result["repaired"])
        assert list(base_path.glob("refactor_state.json.bak.*"))
        assert json.loads(state_path.read_text(encoding="utf-8"))["current_module"] == "CONFIGURACION"
    finally:
        if package_tmp.exists():
            shutil.rmtree(package_tmp)
