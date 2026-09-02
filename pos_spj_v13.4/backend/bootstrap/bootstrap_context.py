"""BootstrapContext — SHELL-3.

The mutable bag steps read from and write to as they run in sequence (e.g.
`ApplicationPathsStep` resolves `app_paths`, which `DatabaseIntegrityStep`
needs to know where the DB file lives). Deliberately not the same thing as
`CompositionRoot`/`ApplicationContainer` (SHELL-5) — this only carries
bootstrap-time plumbing, never resolved application services.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from backend.security.provisioning.installation import ProvisioningStatus
from backend.shared.app_paths import AppPaths


@dataclass
class BootstrapContext:
    db_path: Path
    app_paths: AppPaths | None = None
    conn: sqlite3.Connection | None = None
    installation_status: ProvisioningStatus | None = None
    extras: dict = field(default_factory=dict)
