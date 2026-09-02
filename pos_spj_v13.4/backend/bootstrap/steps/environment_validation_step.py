"""EnvironmentValidationStep — SHELL-3.

Fails fast if the interpreter itself can't run this app correctly — no
point resolving paths or touching the database on a Python too old for the
syntax already in use throughout the codebase (`X | Y` unions, etc.).
"""
from __future__ import annotations

import sqlite3
import sys

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult

MINIMUM_PYTHON = (3, 10)


class EnvironmentValidationStep:
    name = "environment_validation"
    resulting_state = BootstrapState.ENVIRONMENT_VALIDATING

    def run(self, context: BootstrapContext) -> BootstrapStepResult:
        if sys.version_info < MINIMUM_PYTHON:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.REQUIRED_DEPENDENCY_MISSING,
                f"Se requiere Python {'.'.join(map(str, MINIMUM_PYTHON))}+ "
                f"(actual: {sys.version_info[0]}.{sys.version_info[1]}).",
            )
        if sqlite3.sqlite_version_info < (3, 24, 0):
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.REQUIRED_DEPENDENCY_MISSING,
                f"Se requiere SQLite 3.24+ (actual: {sqlite3.sqlite_version}) — "
                f"necesario para UPSERT (ON CONFLICT).",
            )
        return BootstrapStepResult.ok(
            self.name,
            f"Python {sys.version_info[0]}.{sys.version_info[1]}, "
            f"SQLite {sqlite3.sqlite_version}.",
        )
