from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "pos_spj_v13.4"

EXTERNAL_REFACTOR_DIRS = ["frontend", "backend", "tests", "docs"]
REQUIRED_PACKAGE_DIRS = ["frontend", "backend", "tests", "docs"]


def test_refactor_directories_are_inside_real_package() -> None:
    external = [name for name in EXTERNAL_REFACTOR_DIRS if (REPO_ROOT / name).exists()]
    missing = [name for name in REQUIRED_PACKAGE_DIRS if not (PACKAGE_ROOT / name).exists()]

    assert not external, "Refactor directories outside package: " + ", ".join(external)
    assert not missing, "Expected directories inside package: " + ", ".join(missing)
