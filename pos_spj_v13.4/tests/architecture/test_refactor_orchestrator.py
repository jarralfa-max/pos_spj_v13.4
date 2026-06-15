from __future__ import annotations

import importlib.util
import json
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_PATH = PACKAGE_ROOT / "tools" / "refactor_control" / "refactor_orchestrator.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("refactor_orchestrator", ORCHESTRATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refactor_orchestrator_lives_inside_canonical_package_tree() -> None:
    assert ORCHESTRATOR_PATH.is_file()
    assert ORCHESTRATOR_PATH.resolve().is_relative_to(PACKAGE_ROOT.resolve())


def test_refactor_orchestrator_builds_single_batch_instruction_from_state() -> None:
    orchestrator = _load_module()

    instruction = orchestrator.build_instruction(
        {
            "global_status": "IN_PROGRESS",
            "current_module": "CONFIGURACION",
            "current_batch": "CONFIGURACION-02-IDENTITY",
        }
    )

    assert str(orchestrator.SKILL_FILE) in instruction
    assert "SPJ_REFACTOR_SKILL.md es la autoridad única" in instruction
    assert "Ejecuta exactamente un lote funcional completo" in instruction
    assert "módulo: CONFIGURACION" in instruction
    assert "lote: CONFIGURACION-02-IDENTITY" in instruction
    assert "No crees un PR" in instruction


def test_refactor_orchestrator_loads_active_batch_from_work_queue() -> None:
    orchestrator = _load_module()
    temp_dir = PACKAGE_ROOT / ".tmp_refactor_orchestrator"
    temp_dir.mkdir(exist_ok=True)
    state_path = temp_dir / "refactor_state.json"
    queue_path = temp_dir / "work_queue.json"
    try:
        state_path.write_text(
            json.dumps({"global_status": "IN_PROGRESS", "current_module": "CONFIGURACION"}),
            encoding="utf-8",
        )
        queue_path.write_text(
            json.dumps({"phase": "CONFIGURACION", "active_batch": "CONFIGURACION-03-UI"}),
            encoding="utf-8",
        )

        state = orchestrator.load_state(state_path, queue_path)

        assert state["current_module"] == "CONFIGURACION"
        assert state["current_batch"] == "CONFIGURACION-03-UI"
    finally:
        for path in (state_path, queue_path):
            if path.exists():
                path.unlink()
        if temp_dir.exists():
            temp_dir.rmdir()


def test_refactor_orchestrator_has_late_openai_codex_imports() -> None:
    content = ORCHESTRATOR_PATH.read_text(encoding="utf-8")

    assert "from openai_codex import Codex" not in content.split("\n\n", 1)[0]
    assert "from openai_codex import Sandbox" not in content.split("\n\n", 1)[0]
