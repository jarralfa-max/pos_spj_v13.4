"""Continuous subprocess-isolated orchestrator for the SPJ refactor.

Each Codex turn runs in a fresh child process. The parent process owns timeout,
heartbeat, retry, state validation, and Windows process-tree termination. This
prevents a blocked SDK notification queue or dead transport from freezing the
full refactor loop indefinitely.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("spj.refactor.runner")

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(os.environ.get("SPJ_PROJECT_ROOT", PACKAGE_ROOT)).resolve()
REFACTOR_DIR = PROJECT_ROOT / "docs" / "refactor"
RUNS_DIR = REFACTOR_DIR / "runs"
STATE_FILE = REFACTOR_DIR / "refactor_state.json"
WORK_QUEUE_FILE = REFACTOR_DIR / "work_queue.json"
SKILL_FILE = PROJECT_ROOT / "docs" / "skills" / "SPJ_REFACTOR_SKILL.md"
WORKER_FILE = PACKAGE_ROOT / "tools" / "refactor_control" / "refactor_turn_worker.py"

DEFAULT_SLEEP_SECONDS = 5.0
DEFAULT_RETRY_SECONDS = 30.0
DEFAULT_MAX_STALLED_ITERATIONS = 2
DEFAULT_TURN_TIMEOUT_SECONDS = 30 * 60
DEFAULT_MAX_TURN_RETRIES = 3
DEFAULT_HEARTBEAT_SECONDS = 60.0


@dataclass(frozen=True)
class ProgressSnapshot:
    """Stable progress markers used to detect stalled Codex iterations."""

    global_status: str
    current_module: str
    current_batch: str
    module_status: str
    module_iteration: int
    batch_status: str
    batch_iteration: int
    batch_completed_actions: int


@dataclass(frozen=True)
class TurnResult:
    """Result produced by one isolated Codex worker process."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    elapsed_seconds: float
    run_id: str


def _ensure_inside_project(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PACKAGE_ROOT.resolve()):
        raise ValueError(f"Refactor orchestrator path must stay inside package root: {resolved}")
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_control_files(
    state_file: Path = STATE_FILE,
    work_queue_file: Path = WORK_QUEUE_FILE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state_path = _ensure_inside_project(state_file)
    work_queue_path = _ensure_inside_project(work_queue_file)

    if not state_path.exists():
        raise FileNotFoundError(f"Missing refactor state file: {state_path}")
    if not work_queue_path.exists():
        raise FileNotFoundError(f"Missing refactor work queue: {work_queue_path}")

    return _read_json(state_path), _read_json(work_queue_path)


def validate_control_state(state: dict[str, Any], queue: dict[str, Any]) -> None:
    """Fail fast when module state and active work queue disagree."""

    current_module = str(state.get("current_module") or "").strip()
    queue_phase = str(queue.get("phase") or "").strip()
    active_batch = str(queue.get("active_batch") or "").strip()

    if not current_module:
        raise ValueError("refactor_state.json does not define current_module")
    if not queue_phase:
        raise ValueError("work_queue.json does not define phase")
    if current_module != queue_phase:
        raise ValueError(
            f"Refactor state mismatch: current_module={current_module!r}, phase={queue_phase!r}"
        )
    if not active_batch:
        raise ValueError("work_queue.json does not define active_batch")

    modules = state.get("modules") or {}
    module_state = modules.get(current_module)
    if not isinstance(module_state, dict):
        raise ValueError(f"Current module {current_module!r} is missing from refactor_state.json")

    batches = queue.get("batches") or []
    active = next((item for item in batches if item.get("id") == active_batch), None)
    if not isinstance(active, dict):
        raise ValueError(f"Active batch {active_batch!r} is missing from work_queue.json")
    if active.get("status") == "DONE":
        raise ValueError(f"Active batch {active_batch!r} is already DONE; select the next batch")


def load_state(
    state_file: Path = STATE_FILE,
    work_queue_file: Path = WORK_QUEUE_FILE,
) -> dict[str, Any]:
    """Load and validate canonical module state plus active batch data."""

    state, queue = _load_control_files(state_file, work_queue_file)
    validate_control_state(state, queue)
    state["current_batch"] = queue["active_batch"]
    return state


def progress_snapshot(
    state_file: Path = STATE_FILE,
    work_queue_file: Path = WORK_QUEUE_FILE,
) -> ProgressSnapshot:
    """Return progress markers without trusting Codex's textual summary."""

    state, queue = _load_control_files(state_file, work_queue_file)
    validate_control_state(state, queue)

    module_name = str(state["current_module"])
    module_state = state["modules"][module_name]
    active_batch = str(queue["active_batch"])
    batch_state = next(item for item in queue["batches"] if item.get("id") == active_batch)

    return ProgressSnapshot(
        global_status=str(state.get("global_status", "UNKNOWN")),
        current_module=module_name,
        current_batch=active_batch,
        module_status=str(module_state.get("status", "UNKNOWN")),
        module_iteration=int(module_state.get("iteration") or 0),
        batch_status=str(batch_state.get("status", "UNKNOWN")),
        batch_iteration=int(batch_state.get("iteration") or 0),
        batch_completed_actions=len(batch_state.get("completed_actions") or []),
    )


def build_instruction(state: dict[str, Any], skill_file: Path = SKILL_FILE) -> str:
    """Build the single-batch instruction sent to Codex."""

    skill_path = _ensure_inside_project(skill_file)
    if not skill_path.exists():
        raise FileNotFoundError(f"Missing SPJ refactor skill: {skill_path}")

    module = state.get("current_module", "UNKNOWN")
    batch = state.get("current_batch", "UNKNOWN")

    return f"""
Lee completamente:

{skill_path}

SPJ_REFACTOR_SKILL.md es la autoridad única.

Estado actual:
- módulo: {module}
- lote: {batch}
- estado global: {state.get('global_status')}

Ejecuta exactamente un lote funcional completo.

Obligatorio:
1. Auditar código real.
2. Identificar causa raíz.
3. Crear tests de protección.
4. Implementar la ruta canónica.
5. Eliminar legacy sustituido.
6. Ejecutar pruebas.
7. Ejecutar búsquedas negativas.
8. Actualizar los archivos de control.
9. Marcar el lote DONE únicamente con cero infracciones.
10. Seleccionar y registrar el siguiente lote.

No crees un PR.
No termines en planificación.
No trabajes solamente en documentación.
No declares DONE con infracciones pendientes.
No repitas acciones ya registradas en forbidden_reselection sin una regresión reproducible.
""".strip()


def is_finished(
    state_file: Path = STATE_FILE,
    work_queue_file: Path = WORK_QUEUE_FILE,
) -> bool:
    """Return True only when the canonical global refactor state is DONE."""

    state, _queue = _load_control_files(state_file, work_queue_file)
    return state.get("global_status") == "DONE"


def _new_run_id(iteration: int, attempt: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-i{iteration:04d}-a{attempt:02d}"


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate the worker and all descendants, including Codex/PowerShell."""

    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def run_codex_turn_subprocess(
    *,
    instruction: str,
    model: str,
    iteration: int,
    attempt: int,
    timeout_seconds: float,
    heartbeat_seconds: float,
    worker_file: Path = WORKER_FILE,
    runs_dir: Path = RUNS_DIR,
) -> TurnResult:
    """Execute one Codex turn in a fresh process with a hard timeout."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be greater than zero")

    worker_path = _ensure_inside_project(worker_file)
    if not worker_path.exists():
        raise FileNotFoundError(f"Missing Codex turn worker: {worker_path}")

    safe_runs_dir = _ensure_inside_project(runs_dir)
    safe_runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = _new_run_id(iteration, attempt)
    instruction_path = safe_runs_dir / f"{run_id}-request.md"
    stdout_path = safe_runs_dir / f"{run_id}-response.log"
    stderr_path = safe_runs_dir / f"{run_id}-stderr.log"
    instruction_path.write_text(instruction, encoding="utf-8")

    command = [
        sys.executable,
        str(worker_path),
        "--model",
        model,
        "--instruction-file",
        str(instruction_path),
    ]

    creationflags = 0
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        **popen_kwargs,
    )

    next_heartbeat = started + heartbeat_seconds
    timed_out = False

    try:
        while process.poll() is None:
            now = time.monotonic()
            elapsed = now - started
            if elapsed >= timeout_seconds:
                timed_out = True
                LOGGER.error(
                    "Turn timeout | run_id=%s | pid=%s | elapsed=%.1fs | limit=%.1fs",
                    run_id,
                    process.pid,
                    elapsed,
                    timeout_seconds,
                )
                _terminate_process_tree(process)
                break

            if now >= next_heartbeat:
                LOGGER.info(
                    "Codex activo | run_id=%s | pid=%s | elapsed=%.1fs | remaining=%.1fs",
                    run_id,
                    process.pid,
                    elapsed,
                    max(0.0, timeout_seconds - elapsed),
                )
                next_heartbeat = now + heartbeat_seconds

            time.sleep(min(1.0, heartbeat_seconds))

        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            stdout, stderr = process.communicate()
    except KeyboardInterrupt:
        _terminate_process_tree(process)
        raise

    elapsed = time.monotonic() - started
    returncode = process.returncode if process.returncode is not None else -1
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")

    return TurnResult(
        returncode=returncode,
        stdout=stdout or "",
        stderr=stderr or "",
        timed_out=timed_out,
        elapsed_seconds=elapsed,
        run_id=run_id,
    )


def run_loop(
    *,
    model: str = "gpt-5.4",
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    retry_seconds: float = DEFAULT_RETRY_SECONDS,
    max_iterations: int | None = None,
    dry_run: bool = False,
    max_stalled_iterations: int = DEFAULT_MAX_STALLED_ITERATIONS,
    turn_timeout_seconds: float = DEFAULT_TURN_TIMEOUT_SECONDS,
    max_turn_retries: int = DEFAULT_MAX_TURN_RETRIES,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
) -> None:
    """Run isolated Codex turns until DONE, limit, stall, or repeated failure."""

    logging.basicConfig(level=logging.INFO)
    initial_state = load_state()

    if dry_run:
        LOGGER.info(
            "DRY RUN | módulo=%s | lote=%s\n%s",
            initial_state.get("current_module"),
            initial_state.get("current_batch"),
            build_instruction(initial_state),
        )
        return

    if max_iterations is not None and max_iterations <= 0:
        raise ValueError("max_iterations must be greater than zero")
    if max_stalled_iterations <= 0:
        raise ValueError("max_stalled_iterations must be greater than zero")
    if max_turn_retries <= 0:
        raise ValueError("max_turn_retries must be greater than zero")

    iteration = 0
    stalled_iterations = 0

    while not is_finished():
        if max_iterations is not None and iteration >= max_iterations:
            LOGGER.info("Iteration limit reached: %s", max_iterations)
            break

        iteration += 1
        state = load_state()
        before = progress_snapshot()
        instruction = build_instruction(state)

        LOGGER.info(
            "Iteración %s | módulo=%s | lote=%s",
            iteration,
            state.get("current_module"),
            state.get("current_batch"),
        )

        successful_turn = False
        last_error = ""

        for attempt in range(1, max_turn_retries + 1):
            result = run_codex_turn_subprocess(
                instruction=instruction,
                model=model,
                iteration=iteration,
                attempt=attempt,
                timeout_seconds=turn_timeout_seconds,
                heartbeat_seconds=heartbeat_seconds,
            )

            if result.returncode == 0 and not result.timed_out:
                LOGGER.info(
                    "Codex turn completed | run_id=%s | elapsed=%.1fs\n%s",
                    result.run_id,
                    result.elapsed_seconds,
                    result.stdout.strip(),
                )
                successful_turn = True
                break

            reason = "TIMEOUT" if result.timed_out else f"EXIT_{result.returncode}"
            last_error = result.stderr.strip() or result.stdout.strip() or reason
            LOGGER.error(
                "Codex turn failed | run_id=%s | reason=%s | attempt=%s/%s\n%s",
                result.run_id,
                reason,
                attempt,
                max_turn_retries,
                last_error[-4000:],
            )

            if attempt < max_turn_retries:
                LOGGER.info("Retrying same batch with a fresh worker in %.1fs", retry_seconds)
                time.sleep(retry_seconds)

        if not successful_turn:
            raise RuntimeError(
                f"Codex turn failed after {max_turn_retries} fresh-process attempts: {last_error}"
            )

        after = progress_snapshot()
        if after == before:
            stalled_iterations += 1
            LOGGER.warning(
                "No canonical progress detected after iteration %s (%s/%s)",
                iteration,
                stalled_iterations,
                max_stalled_iterations,
            )
            if stalled_iterations >= max_stalled_iterations:
                raise RuntimeError(
                    "Refactor orchestrator stalled: state and work queue did not change"
                )
        else:
            stalled_iterations = 0

        time.sleep(sleep_seconds)

    if is_finished():
        LOGGER.info("Refactor global marcado como DONE.")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the continuous SPJ Codex refactor orchestrator")
    parser.add_argument("--model", default="gpt-5.4", help="Codex model name")
    parser.add_argument("--once", action="store_true", help="Execute exactly one Codex iteration")
    parser.add_argument("--max-iterations", type=int, default=None, help="Stop after N iterations")
    parser.add_argument("--dry-run", action="store_true", help="Validate state and print the next instruction")
    parser.add_argument(
        "--max-stalled-iterations",
        type=int,
        default=DEFAULT_MAX_STALLED_ITERATIONS,
        help="Stop after N successful turns without canonical state progress",
    )
    parser.add_argument(
        "--turn-timeout-seconds",
        type=float,
        default=DEFAULT_TURN_TIMEOUT_SECONDS,
        help="Hard timeout for each isolated Codex turn",
    )
    parser.add_argument(
        "--max-turn-retries",
        type=int,
        default=DEFAULT_MAX_TURN_RETRIES,
        help="Fresh-process retries for a failed or timed-out turn",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=DEFAULT_HEARTBEAT_SECONDS,
        help="Interval for active-turn heartbeat logging",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    max_iterations = 1 if args.once else args.max_iterations
    run_loop(
        model=args.model,
        max_iterations=max_iterations,
        dry_run=args.dry_run,
        max_stalled_iterations=args.max_stalled_iterations,
        turn_timeout_seconds=args.turn_timeout_seconds,
        max_turn_retries=args.max_turn_retries,
        heartbeat_seconds=args.heartbeat_seconds,
    )


if __name__ == "__main__":
    main()
