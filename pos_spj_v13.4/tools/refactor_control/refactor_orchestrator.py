"""Continuous Codex orchestrator for the SPJ refactor loop.

This runner is intentionally outside the application runtime. It reads the
canonical refactor control files, starts a Codex thread, and asks the agent to
execute one functional batch per iteration until the global state is marked
``DONE``.
"""

from __future__ import annotations

import json
import logging
import os
import time
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


def _ensure_inside_project(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PACKAGE_ROOT.resolve()):
        raise ValueError(f"Refactor orchestrator path must stay inside package root: {resolved}")
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_state(state_file: Path = STATE_FILE, work_queue_file: Path = WORK_QUEUE_FILE) -> dict[str, Any]:
    """Load canonical state and merge active-batch data from work_queue.json.

    ``refactor_state.json`` is the module-level source of truth. The currently
    selected executable batch lives in ``work_queue.json`` in the existing
    control tree, so this function exposes both to the orchestrator prompt.
    """

    state_path = _ensure_inside_project(state_file)
    work_queue_path = _ensure_inside_project(work_queue_file)

    if not state_path.exists():
        return {
            "global_status": "IN_PROGRESS",
            "current_module": "CONFIGURACION",
            "current_batch": "CONFIGURACION-01-SCOPE",
        }

    state = _read_json(state_path)
    if work_queue_path.exists():
        queue = _read_json(work_queue_path)
        state.setdefault("current_module", queue.get("phase", "CONFIGURACION"))
        state["current_batch"] = queue.get("active_batch", state.get("current_batch", "UNKNOWN"))
    else:
        state.setdefault("current_batch", "UNKNOWN")
    return state


def build_instruction(state: dict[str, Any], skill_file: Path = SKILL_FILE) -> str:
    """Build the single-batch instruction sent to Codex."""

    skill_path = _ensure_inside_project(skill_file)
    module = state.get("current_module", "UNKNOWN")
    batch = state.get("current_batch", "UNKNOWN")

    return f"""
Lee completamente:

{skill_path}

SPJ_REFACTOR_SKILL.md es la autoridad única.

Estado actual:
- módulo: {module}
- lote: {batch}
- estado global: {state.get("global_status")}

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
""".strip()


def is_finished(state_file: Path = STATE_FILE, work_queue_file: Path = WORK_QUEUE_FILE) -> bool:
    """Return True only when the canonical global refactor state is DONE."""

    return load_state(state_file, work_queue_file).get("global_status") == "DONE"


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
) -> None:
    """Run Codex iterations until ``global_status`` becomes ``DONE``."""

    logging.basicConfig(level=logging.INFO)

    if codex_client is None:
        try:
            from openai_codex import Codex
        except ImportError as exc:  # pragma: no cover - depends on local runner installation.
            raise RuntimeError("Install openai_codex to run the SPJ refactor orchestrator") from exc
        codex_client = Codex()

    with codex_client as codex:
        thread = _start_thread(codex, model)
        iteration = 0

        while not is_finished():
            iteration += 1
            state = load_state()

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

            time.sleep(sleep_seconds)

    LOGGER.info("Refactor global marcado como DONE.")


def main() -> None:
    run_loop()


if __name__ == "__main__":
    main()
