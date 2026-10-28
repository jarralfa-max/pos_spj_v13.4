"""Station schema version: one rule for the release build and the stations.

Regression: `scripts/release/_release_common.py::schema_target()` did
`int()` on every `_Migration(...)` id in engine.py and crashed with
`ValueError: invalid literal for int() with base 10: 'p001'` once the
PostgreSQL lane (central server) was added.
"""
from __future__ import annotations

import importlib
from pathlib import Path
import sqlite3
import sys

import pytest

from backend.shared.schema_versions import is_station_migration_id, station_schema_version

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
RELEASE_SCRIPTS = PACKAGE_ROOT / "scripts" / "release"


# ── the rule ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("identifiers, expected", [
    (["000", "001", "016", "353"], 353),          # zero-padded numeric ids
    (["353", "016", "340"], 353),                 # order does not matter
    (["000"], 0),
    (["016", "p001", "p005", "353"], 353),        # PostgreSQL lane ignored
    (["p001", "p002"], None),                     # only the central lane
    ([], None),
    ([" 352 ", "351"], 352),                      # surrounding whitespace
    ([None, "", "  ", "350"], 350),               # empty values ignored
    (["٣٥٤", "²", "350"], 350),                   # non-ASCII digits never count
    (["-5", "3.5", "1e3", "349"], 349),           # signs, decimals, exponents
    (["99999999999999999999", "1"], 99999999999999999999),
    ([353, 354], 354),                            # ints from a DB column
])
def test_station_schema_version(identifiers, expected):
    assert station_schema_version(identifiers) == expected


@pytest.mark.parametrize("identifier, expected", [
    ("353", True), ("000", True), ("p001", False), ("", False), (None, False),
    ("3a", False), ("٣", False),
])
def test_is_station_migration_id(identifier, expected):
    assert is_station_migration_id(identifier) is expected


# ── the migration engine ───────────────────────────────────────────────────
def test_sqlite_lane_ids_are_all_numeric_and_lanes_do_not_overlap():
    """A SQLite migration with a non-numeric id would be IGNORED by the schema
    version and the updater would compare the wrong numbers: fail here."""
    from migrations.engine import MIGRATIONS, PG_MIGRATIONS

    offenders = [m.version for m in MIGRATIONS if not is_station_migration_id(m.version)]
    assert not offenders, f"Migraciones SQLite con id no numérico: {offenders}"
    assert not [m.version for m in PG_MIGRATIONS if is_station_migration_id(m.version)]
    versions = [m.version for m in MIGRATIONS]
    assert len(versions) == len(set(versions)), "ids SQLite repetidos"


def test_target_schema_version_is_the_highest_sqlite_migration():
    from migrations.engine import MIGRATIONS, PG_MIGRATIONS, target_schema_version

    target = target_schema_version()
    assert target == max(int(m.version) for m in MIGRATIONS)
    assert PG_MIGRATIONS, "the regression needs the PostgreSQL lane present"


def test_station_reading_uses_the_same_scale(tmp_path):
    """What a fully migrated station reports == what the build announces,
    even if a central-lane id ever lands in a station's tracking table."""
    from backend.infrastructure.db.sqlite_backup import database_schema_version
    from migrations.engine import MIGRATIONS, target_schema_version

    connection = sqlite3.connect(str(tmp_path / "station.db"))
    connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")
    connection.executemany("INSERT INTO schema_migrations VALUES (?)",
                           [(m.version,) for m in MIGRATIONS] + [("p001",), ("p005",)])
    assert database_schema_version(connection) == target_schema_version()
    connection.close()


# ── the release tooling ────────────────────────────────────────────────────
@pytest.fixture()
def release_common(monkeypatch):
    monkeypatch.syspath_prepend(str(RELEASE_SCRIPTS))
    sys.modules.pop("_release_common", None)
    return importlib.import_module("_release_common")


def test_release_schema_target_no_longer_crashes_on_the_postgresql_lane(release_common):
    from migrations.engine import target_schema_version

    assert release_common.schema_target() == target_schema_version()


def test_manifest_built_with_the_target_is_valid_and_offered(release_common):
    """The number goes into `database_schema.migrates_to`: the manifest must
    validate and a station already on the previous schema must be offered the
    release (not rejected as a schema downgrade)."""
    from backend.domain.software_distribution.eligibility import (
        EligibilityOutcome,
        StationIdentity,
        UpdateEligibilityPolicy,
    )
    from backend.domain.software_distribution.release_manifest import (
        ReleaseChannel,
        ReleaseManifest,
        TargetPlatform,
    )
    from backend.domain.software_distribution.semantic_version import SemanticVersion

    target = release_common.schema_target()
    payload = {
        "format": "spj-release/1", "product": "spj-erp-pos", "version": "99.0.0",
        "channel": "stable", "published_at": "2026-10-25T00:00:00Z",
        "platform": {"os": "windows", "arch": "x64"}, "minimum_installed_version": None,
        "database_schema": {"requires_at_least": 0, "migrates_to": target},
        "artifact": {"kind": "inno-setup", "file_name": "SPJ-Setup-99.0.0-x64.exe",
                     "url": "https://updates.example.test/stable/SPJ-Setup-99.0.0-x64.exe",
                     "size": 1, "sha256": "a" * 64},
        "release_notes": "", "mandatory": False, "mandatory_deadline": None,
        "rollout": {"percent": 100, "branch_ids": [], "workstation_ids": []},
    }
    manifest = ReleaseManifest.from_payload(payload)
    assert manifest.database_schema.migrates_to == target
    station = StationIdentity(
        installed_version=SemanticVersion.parse("13.4.0"), channel=ReleaseChannel.STABLE,
        platform=TargetPlatform("windows", "x64"), database_schema_version=target - 1,
        workstation_id="ws", branch_id="br")
    decision = UpdateEligibilityPolicy(allowed_hosts=frozenset({"updates.example.test"})) \
        .evaluate(station, manifest)
    assert decision.outcome is EligibilityOutcome.OFFERED, decision.message
