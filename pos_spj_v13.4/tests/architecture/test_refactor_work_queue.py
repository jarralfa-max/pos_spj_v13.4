from __future__ import annotations

import json
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REFACTOR_DIR = PACKAGE_ROOT / "docs" / "refactor"
WORK_QUEUE_PATH = REFACTOR_DIR / "work_queue.json"
ALLOWED_BATCH_STATES = {"PENDING", "IN_PROGRESS", "BLOCKED", "DONE"}
EXPECTED_CONFIG_BATCH_ORDER = [
    "CONFIGURACION-01-SCOPE",
    "CONFIGURACION-02-IDENTITY",
    "CONFIGURACION-03-UI",
    "CONFIGURACION-04-QUERIES",
    "CONFIGURACION-05-MUTATIONS",
    "CONFIGURACION-06-DOMAIN_RULES",
    "CONFIGURACION-07-PERSISTENCE",
    "CONFIGURACION-08-TRANSACTIONS",
    "CONFIGURACION-09-EVENTS",
    "CONFIGURACION-10-PERMISSIONS",
    "CONFIGURACION-11-INTEGRATIONS",
    "CONFIGURACION-12-API_READINESS",
    "CONFIGURACION-13-SQLITE_POSTGRESQL",
    "CONFIGURACION-14-LEGACY_REMOVAL",
    "CONFIGURACION-15-TESTS",
    "CONFIGURACION-16-MANUAL_VALIDATION",
    "CONFIGURACION-17-FINAL_GATES",
]


def _load_work_queue() -> dict:
    return json.loads(WORK_QUEUE_PATH.read_text(encoding="utf-8"))


def test_module_work_queue_exists_inside_refactor_tree():
    assert WORK_QUEUE_PATH.is_file()
    assert WORK_QUEUE_PATH.resolve().is_relative_to(REFACTOR_DIR.resolve())


def test_configuracion_work_queue_has_required_batch_order_and_active_batch():
    queue = _load_work_queue()
    assert queue["phase"] == "CONFIGURACION"
    assert queue["status"] == "IN_PROGRESS"
    assert [batch["id"] for batch in queue["batches"]] == EXPECTED_CONFIG_BATCH_ORDER
    active = [batch for batch in queue["batches"] if batch["status"] == "IN_PROGRESS"]
    assert len(active) == 1
    assert queue["active_batch"] == active[0]["id"] == "CONFIGURACION-06-DOMAIN_RULES"
    by_id = {batch["id"]: batch for batch in queue["batches"]}
    assert by_id["CONFIGURACION-01-SCOPE"]["status"] == "DONE"
    assert by_id["CONFIGURACION-01-SCOPE"]["violations"] == 0
    assert by_id["CONFIGURACION-02-IDENTITY"]["status"] == "DONE"
    assert by_id["CONFIGURACION-02-IDENTITY"]["violations"] == 0
    assert by_id["CONFIGURACION-03-UI"]["status"] == "DONE"
    assert by_id["CONFIGURACION-03-UI"]["violations"] == 0
    assert by_id["CONFIGURACION-04-QUERIES"]["status"] == "DONE"
    assert by_id["CONFIGURACION-04-QUERIES"]["violations"] == 0
    assert by_id["CONFIGURACION-05-MUTATIONS"]["status"] == "DONE"
    assert by_id["CONFIGURACION-05-MUTATIONS"]["violations"] == 0


def test_configuracion_batch_dependencies_reference_prior_batches():
    queue = _load_work_queue()
    seen = set()
    for batch in queue["batches"]:
        assert batch["status"] in ALLOWED_BATCH_STATES
        assert set(batch["dependencies"]).issubset(seen)
        seen.add(batch["id"])


def test_historical_uuidv7_artifacts_remain_available_but_not_active_work_queue():
    assert (REFACTOR_DIR / "UUIDV7_SCHEMA_GRAPH.json").is_file()
    assert (REFACTOR_DIR / "UUIDV7_SCHEMA_CLASSIFICATION.json").is_file()
    assert _load_work_queue()["phase"] != "UUIDV7_CUTOVER"
