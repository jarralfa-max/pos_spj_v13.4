from .refactor_control_helpers import CONTROL_FILE_NAMES, PACKAGE_ROOT, REFACTOR_DIR, REPO_ROOT, REQUIRED_CONTROL_PATHS


def test_refactor_control_files_are_inside_package_refactor_dir():
    for path in REQUIRED_CONTROL_PATHS:
        resolved = path.resolve()
        assert resolved.is_relative_to(REFACTOR_DIR.resolve())
        assert resolved.is_relative_to(PACKAGE_ROOT.resolve())


def test_no_refactor_control_file_copies_exist_in_external_repo_root():
    forbidden = [REPO_ROOT / name for name in CONTROL_FILE_NAMES]
    existing = [str(path) for path in forbidden if path.exists()]
    assert not existing
