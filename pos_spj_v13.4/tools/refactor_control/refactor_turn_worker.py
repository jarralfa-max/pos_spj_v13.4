"""Execute exactly one Codex refactor turn in an isolated process."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def _result_text(result: Any) -> str:
    return str(getattr(result, "final_response", result))


def run_once(*, instruction_file: Path, model: str) -> int:
    instruction_path = instruction_file.resolve()
    if not instruction_path.is_file():
        raise FileNotFoundError(f"Instruction file not found: {instruction_path}")

    instruction = instruction_path.read_text(encoding="utf-8")

    try:
        from openai_codex import Codex, Sandbox
    except ImportError as exc:  # pragma: no cover - depends on local installation.
        raise RuntimeError("Install openai_codex to run the SPJ refactor worker") from exc

    with Codex() as codex:
        thread = codex.thread_start(model=model, sandbox=Sandbox.workspace_write)
        result = thread.run(instruction)

    print(_result_text(result), flush=True)
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one isolated Codex refactor turn")
    parser.add_argument("--model", required=True)
    parser.add_argument("--instruction-file", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    return run_once(instruction_file=args.instruction_file, model=args.model)


if __name__ == "__main__":
    raise SystemExit(main())
