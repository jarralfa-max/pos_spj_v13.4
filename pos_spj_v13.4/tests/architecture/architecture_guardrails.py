"""Shared scanners for SPJ architecture guardrail tests.

The rules in this module intentionally allow current technical debt through a
per-file baseline. Future changes must not introduce additional occurrences.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "pos_spj_v13.4"

SKIPPED_DIR_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
}

SOURCE_SUFFIXES = {".py", ".sql"}
PYTHON_SUFFIXES = {".py"}

UI_ROOTS = (
    APP_ROOT / "interfaz",
    APP_ROOT / "modulos",
    APP_ROOT / "labels",
    APP_ROOT / "presentation",
)

MIGRATION_DIR_NAMES = {"migrations"}

ENTITY_TERMS = (
    "producto",
    "product",
    "cliente",
    "customer",
    "proveedor",
    "supplier",
    "empleado",
    "employee",
    "receta",
    "recipe",
    "activo",
    "asset",
    "sucursal",
    "branch",
    "repartidor",
    "driver",
)

PHONE_TERMS = (
    "telefono",
    "teléfono",
    "phone",
    "celular",
    "mobile",
    "whatsapp",
    "wa_",
)

SQL_RE = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|WITH\s+\w+\s+AS|PRAGMA)\b",
    re.IGNORECASE,
)
COMMIT_ROLLBACK_RE = re.compile(r"\.(commit|rollback)\s*\(")
SCHEMA_CHANGE_RE = re.compile(r"\b(CREATE\s+TABLE|ALTER\s+TABLE)\b", re.IGNORECASE)
NUMERIC_DEFAULT_RE = re.compile(
    r"\b(?:setValue|setProperty|setCurrentIndex)\s*\(\s*(?:1|7|10|30|50|100)\s*\)"
    r"|\b(?:default|default_value|initial|initial_value|valor_defecto)\s*=\s*(?:1|7|10|30|50|100)\b",
    re.IGNORECASE,
)
QLINEEDIT_RE = re.compile(r"\bQLineEdit\b")
QCOMBOBOX_RE = re.compile(r"\bQComboBox\b|\.addItems\s*\(|\.addItem\s*\(")
RELATIVE_PATH_RE = re.compile(
    r"\b(?:open|sqlite3\.connect|Path|QPixmap|QIcon)\s*\(\s*[frbuFRBU]*[\"'](?!/|[A-Za-z]:|:memory:|https?://)([^\"']+)[\"']"
    r"|\bos\.path\.join\s*\(\s*[frbuFRBU]*[\"'](?!/|[A-Za-z]:)([^\"']+)[\"']",
)
APPCONTAINER_RE = re.compile(
    r"\bAppContainer\b|\bcontainer\s*:\s*[^,)=]*|\bself\.container\s*=\s*container\b|\bcontainer\s*=\s*container\b",
    re.IGNORECASE,
)
DEPRECATED_SERVICE_LOGIC_RE = re.compile(
    r"\b(execute|executemany|commit|rollback|SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|registrar|procesar|crear|actualizar|eliminar|calculate|apply|generate)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line_number: int
    text: str

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(REPO_ROOT).as_posix()


def _is_skipped(path: Path) -> bool:
    return bool(SKIPPED_DIR_PARTS.intersection(path.parts))


def _is_under(path: Path, roots: Iterable[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots if root.exists())


def iter_files(*, suffixes: set[str], roots: Iterable[Path] | None = None) -> Iterable[Path]:
    search_roots = tuple(roots or (APP_ROOT,))
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in suffixes or _is_skipped(path):
                continue
            yield path


def iter_source_lines(path: Path) -> Iterable[tuple[int, str]]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1")
    for number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield number, line.rstrip()


def collect_regex_violations(
    *,
    pattern: re.Pattern[str],
    roots: Iterable[Path] | None = None,
    suffixes: set[str] = PYTHON_SUFFIXES,
    path_filter: Callable[[Path], bool] | None = None,
    line_filter: Callable[[Path, int, str], bool] | None = None,
) -> list[Violation]:
    violations: list[Violation] = []
    for path in iter_files(suffixes=suffixes, roots=roots):
        if path_filter and not path_filter(path):
            continue
        for line_number, line in iter_source_lines(path):
            if pattern.search(line) and (line_filter is None or line_filter(path, line_number, line)):
                violations.append(Violation(path=path, line_number=line_number, text=line.strip()))
    return violations


def assert_no_new_violations(rule_name: str, violations: Iterable[Violation], allowlist: Mapping[str, int]) -> None:
    actual_counts: dict[str, int] = {}
    examples_by_path: dict[str, list[str]] = {}
    for violation in violations:
        key = violation.relative_path
        actual_counts[key] = actual_counts.get(key, 0) + 1
        examples_by_path.setdefault(key, [])
        if len(examples_by_path[key]) < 5:
            examples_by_path[key].append(f"L{violation.line_number}: {violation.text}")

    new_or_grown = {
        path: count
        for path, count in sorted(actual_counts.items())
        if count > allowlist.get(path, 0)
    }

    if not new_or_grown:
        return

    details = []
    for path, count in new_or_grown.items():
        allowed = allowlist.get(path, 0)
        details.append(f"- {path}: {count} violation(s), allowed {allowed}")
        details.extend(f"    {example}" for example in examples_by_path.get(path, []))

    existing_total = sum(min(actual_counts.get(path, 0), allowed) for path, allowed in allowlist.items())
    raise AssertionError(
        f"{rule_name} detected new architecture violation(s).\n"
        f"Existing allowlist violations still tolerated: {existing_total}.\n"
        "New or increased violations:\n"
        + "\n".join(details)
    )


def is_ui_path(path: Path) -> bool:
    return _is_under(path, UI_ROOTS)


def outside_migrations(path: Path) -> bool:
    relative_parts = path.relative_to(REPO_ROOT).parts
    return not any(part in MIGRATION_DIR_NAMES for part in relative_parts)


def is_service_path(path: Path) -> bool:
    parts = {part.lower() for part in path.relative_to(REPO_ROOT).parts}
    name = path.name.lower()
    return "services" in parts or "service" in name or "use_cases" in parts or "application" in parts


def is_deprecated_service_path(path: Path) -> bool:
    lowered = path.as_posix().lower()
    return ("legacy" in lowered or "deprecated" in lowered) and is_service_path(path)


def has_entity_term(line: str) -> bool:
    lowered = line.lower()
    return any(term in lowered for term in ENTITY_TERMS)


def has_phone_term(line: str) -> bool:
    lowered = line.lower()
    return any(term in lowered for term in PHONE_TERMS)


def is_loose_relative_path_line(path: Path, line_number: int, line: str) -> bool:
    del path, line_number
    if "AppPaths" in line or "__file__" in line or "import" in line:
        return False
    match = RELATIVE_PATH_RE.search(line)
    if not match:
        return False
    literal = next(group for group in match.groups() if group)
    if literal.startswith((".", "..")):
        return True
    return "/" in literal or "\\" in literal or "." in Path(literal).name
