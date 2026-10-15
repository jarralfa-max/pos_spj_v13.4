"""The independently installed channel must not depend on import order."""
import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
CHANNEL = ROOT / "whatsapp_service"


def test_channel_uses_qualified_imports():
    local = {p.name for p in CHANNEL.iterdir() if p.is_dir()} | {"phone_number"}
    violations = []
    for path in CHANNEL.rglob("*.py"):
        if "tests" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom) and not node.level:
                if (node.module or "").split(".")[0] in local | {"core"}:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.module}")
    assert not violations, "\n".join(violations)


def test_import_is_independent_of_desktop_and_does_not_change_python_path():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; before = list(sys.path); "
         "import whatsapp_service.main; "
         "import whatsapp_service.router.message_router; "
         "assert sys.path == before; "
         "assert not any(m.startswith(('PyQt5', 'core.')) for m in sys.modules)"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
