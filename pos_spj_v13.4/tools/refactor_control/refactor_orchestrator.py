"""Continuous Codex orchestrator for the SPJ refactor loop.

This runner lives outside the application runtime. It reads the canonical
refactor control files, validates their consistency, starts a Codex thread, and
asks the agent to execute one functional batch per iteration until the global
state is marked ``DONE``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

LOGGER = logging.getLogger("spj.refactor.runner")

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(os.environ.get("SPJ_PROJECT_ROOT", PACKAGE_ROOT)).resolve()
REFACTOR_DIR = PROJECT_ROOT / "docs" / "refactor"
STATE_FILE = REFACTOR_DIR / "refactor_state.json"
WORK_QUEUE_FILE = REFACTOR_DIR / "work_queue.json"
SKILL_FILE = PROJECT_ROOT / "docs" / "skills" / "SPJ_REFACTOR_SKILL.md"
DEFAULT_SLEEP_SECONDS = 5.0
DEFAULT_RETRY_SECONDS = 30.0
DEFAULT_MAX_STALLED_ITERATIONS = 2


class CodexThread(Protocol):
    def run(self, instruction: str) -> Any:
        """Run one Codex instruction and return the SDK result."""


class CodexClient(Protocol):
    def __enter__(self) -> "CodexClient":
        """Enter the SDK context manager."""

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> object:
        """Exit the SDK context manager."""

    def thread_start(self, *, model: str, sandbox: Any) -> CodexThread:
        """Start a Codex thread."""


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


def _start_thread(codex_client: CodexClient, model: str) -> CodexThread:
    """Start a Codex SDK thread using workspace-write sandboxing."""

    try:
        from openai_codex import Sandbox
    except ImportError as exc:  # pragma: no cover - depends on local runner installation.
        raise RuntimeError("Install openai_codex to run the SPJ refactor orchestrator") from exc
    return codex_client.thread_start(model=model, sandbox=Sandbox.workspace_write)


def _result_text(result: Any) -> str:
    return str(getattr(result, "final_response", result))


def run_loop(
    *,
    codex_client: CodexClient | None = None,
    model: str = "gpt-5.4",
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    retry_seconds: float = DEFAULT_RETRY_SECONDS,
    max_iterations: int | None = None,
    dry_run: bool = False,
    max_stalled_iterations: int = DEFAULT_MAX_STALLED_ITERATIONS,
) -> None:
    """Run Codex iterations until DONE, a configured limit, or a stall."""

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

    if codex_client is None:
        try:
            from openai_codex import Codex
        except ImportError as exc:  # pragma: no cover - depends on local runner installation.
            raise RuntimeError("Install openai_codex to run the SPJ refactor orchestrator") from exc
        codex_client = Codex()

    with codex_client as codex:
        thread = _start_thread(codex, model)
        iteration = 0
        stalled_iterations = 0

        while not is_finished():
            if max_iterations is not None and iteration >= max_iterations:
                LOGGER.info("Iteration limit reached: %s", max_iterations)
                break

            iteration += 1
            state = load_state()
            before = progress_snapshot()

            LOGGER.info(
                "Iteración %s | módulo=%s | lote=%s",
                iteration,
                state.get("current_module"),
                state.get("current_batch"),
            )

            try:
                result = thread.run(build_instruction(state))
                LOGGER.info("Respuesta Codex:\n%s", _result_text(result))
            except KeyboardInterrupt:
                LOGGER.warning("Ejecución detenida por el usuario.")
                raise
            except Exception:
                LOGGER.exception(
                    "Falló la iteración %s. Reintentando en %s segundos.",
                    iteration,
                    retry_seconds,
                )
                time.sleep(retry_seconds)
                continue

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
        help="Stop after N iterations without canonical state progress",
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
    )


if __name__ == "__main__":
    main()
