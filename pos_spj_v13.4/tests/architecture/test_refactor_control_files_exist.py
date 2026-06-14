from .refactor_control_helpers import MODULES_DIR, REQUIRED_CONTROL_PATHS, REFACTOR_DIR


def test_refactor_control_files_exist_in_canonical_tree():
    missing = [str(path) for path in REQUIRED_CONTROL_PATHS if not path.is_file()]
    assert not missing
    assert REFACTOR_DIR.is_dir()
    assert MODULES_DIR.is_dir()
