from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_PATH = PACKAGE_ROOT / "tools" / "refactor_control" / "refactor_orchestrator.py"
WORKER_PATH = PACKAGE_ROOT / "tools" / "refactor_control" / "refactor_turn_worker.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("refactor_orchestrator", ORCHESTRATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_control_files(
    temp_dir: Path,
    *,
    module: str = "CONFIGURACION",
    batch: str = "CONFIGURACION-03-UI",
):
    state_path = temp_dir / "refactor_state.json"
    queue_path = temp_dir / "work_queue.json"
    state_path.write_text(
        json.dumps(
            {
                "global_status": "IN_PROGRESS",
                "current_module": module,
                "modules": {
                    module: {
                        "status": "IMPLEMENTATION",
                        "iteration": 3,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    queue_path.write_text(
        json.dumps(
            {
                "phase": module,
                "active_batch": batch,
                "batches": [
                    {
                        "id": batch,
                        "status": "IN_PROGRESS",
                        "iteration": 2,
                        "completed_actions": ["audit"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return state_path, queue_path


def test_refactor_orchestrator_and_worker_live_inside_canonical_package_tree() -> None:
    assert ORCHESTRATOR_PATH.is_file()
    assert WORKER_PATH.is_file()
    assert ORCHESTRATOR_PATH.resolve().is_relative_to(PACKAGE_ROOT.resolve())
    assert WORKER_PATH.resolve().is_relative_to(PACKAGE_ROOT.resolve())


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
    assert "forbidden_reselection" in instruction


def test_refactor_orchestrator_loads_active_batch_from_work_queue() -> None:
    orchestrator = _load_module()
    temp_dir = PACKAGE_ROOT / ".tmp_refactor_orchestrator"
    temp_dir.mkdir(exist_ok=True)
    state_path, queue_path = _write_control_files(temp_dir)
    try:
        state = orchestrator.load_state(state_path, queue_path)

        assert state["current_module"] == "CONFIGURACION"
        assert state["current_batch"] == "CONFIGURACION-03-UI"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_refactor_orchestrator_rejects_module_queue_mismatch() -> None:
    orchestrator = _load_module()
    temp_dir = PACKAGE_ROOT / ".tmp_refactor_orchestrator_mismatch"
    temp_dir.mkdir(exist_ok=True)
    state_path, queue_path = _write_control_files(temp_dir)
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    queue["phase"] = "MERMA"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="current_module"):
            orchestrator.load_state(state_path, queue_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_refactor_orchestrator_rejects_done_active_batch() -> None:
    orchestrator = _load_module()
    temp_dir = PACKAGE_ROOT / ".tmp_refactor_orchestrator_done"
    temp_dir.mkdir(exist_ok=True)
    state_path, queue_path = _write_control_files(temp_dir)
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    queue["batches"][0]["status"] = "DONE"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="already DONE"):
            orchestrator.load_state(state_path, queue_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_refactor_orchestrator_progress_snapshot_tracks_canonical_state() -> None:
    orchestrator = _load_module()
    temp_dir = PACKAGE_ROOT / ".tmp_refactor_orchestrator_snapshot"
    temp_dir.mkdir(exist_ok=True)
    state_path, queue_path = _write_control_files(temp_dir)
    try:
        snapshot = orchestrator.progress_snapshot(state_path, queue_path)

        assert snapshot.current_module == "CONFIGURACION"
        assert snapshot.current_batch == "CONFIGURACION-03-UI"
        assert snapshot.module_status == "IMPLEMENTATION"
        assert snapshot.module_iteration == 3
        assert snapshot.batch_status == "IN_PROGRESS"
        assert snapshot.batch_iteration == 2
        assert snapshot.batch_completed_actions == 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_refactor_orchestrator_runs_each_turn_in_fresh_subprocess() -> None:
    orchestrator = _load_module()
    temp_dir = PACKAGE_ROOT / ".tmp_refactor_turn_success"
    runs_dir = temp_dir / "runs"
    worker = temp_dir / "worker.py"
    temp_dir.mkdir(exist_ok=True)
    worker.write_text(
        "import argparse\n"
        "p=argparse.ArgumentParser()\n"
        "p.add_argument('--model')\n"
        "p.add_argument('--instruction-file')\n"
        "a=p.parse_args()\n"
        "print(open(a.instruction_file, encoding='utf-8').read())\n",
        encoding="utf-8",
    )
    try:
        result = orchestrator.run_codex_turn_subprocess(
            instruction="execute batch",
            model="test-model",
            iteration=1,
            attempt=1,
            timeout_seconds=5,
            heartbeat_seconds=1,
            worker_file=worker,
            runs_dir=runs_dir,
        )

        assert result.returncode == 0
        assert result.timed_out is False
        assert "execute batch" in result.stdout
        assert list(runs_dir.glob("*-request.md"))
        assert list(runs_dir.glob("*-response.log"))
        assert list(runs_dir.glob("*-stderr.log"))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_refactor_orchestrator_times_out_and_terminates_worker_tree() -> None:
    orchestrator = _load_module()
    temp_dir = PACKAGE_ROOT / ".tmp_refactor_turn_timeout"
    runs_dir = temp_dir / "runs"
    worker = temp_dir / "worker.py"
    temp_dir.mkdir(exist_ok=True)
    worker.write_text(
        "import argparse, time\n"
        "p=argparse.ArgumentParser()\n"
        "p.add_argument('--model')\n"
        "p.add_argument('--instruction-file')\n"
        "p.parse_args()\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    try:
        result = orchestrator.run_codex_turn_subprocess(
            instruction="blocked batch",
            model="test-model",
            iteration=1,
            attempt=1,
            timeout_seconds=0.3,
            heartbeat_seconds=0.1,
            worker_file=worker,
            runs_dir=runs_dir,
        )

        assert result.timed_out is True
        assert result.elapsed_seconds < 10
        assert result.returncode != 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_refactor_orchestrator_cli_supports_timeout_and_retry_controls() -> None:
    orchestrator = _load_module()
    parser = orchestrator.build_argument_parser()

    once = parser.parse_args(["--once"])
    dry_run = parser.parse_args(["--dry-run"])
    limited = parser.parse_args(
        [
            "--max-iterations",
            "3",
            "--max-stalled-iterations",
            "4",
            "--turn-timeout-seconds",
            "900",
            "--max-turn-retries",
            "2",
            "--heartbeat-seconds",
            "30",
        ]
    )

    assert once.once is True
    assert dry_run.dry_run is True
    assert limited.max_iterations == 3
    assert limited.max_stalled_iterations == 4
    assert limited.turn_timeout_seconds == 900
    assert limited.max_turn_retries == 2
    assert limited.heartbeat_seconds == 30


def test_parent_orchestrator_does_not_call_codex_sdk_directly() -> None:
    content = ORCHESTRATOR_PATH.read_text(encoding="utf-8")

    assert "from openai_codex" not in content
    assert "thread.run(" not in content
    assert "subprocess.Popen(" in content
    assert "taskkill" in content


def test_worker_owns_the_single_codex_sdk_turn() -> None:
    content = WORKER_PATH.read_text(encoding="utf-8")

    assert "from openai_codex import Codex, Sandbox" in content
    assert "thread.run(instruction)" in content
