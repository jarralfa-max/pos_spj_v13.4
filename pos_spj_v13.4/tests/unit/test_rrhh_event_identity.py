from pathlib import Path
import sys
import uuid

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "pos_spj_v13.4"))

from core.rrhh.events import new_operation_id


def test_rrhh_operation_ids_use_canonical_uuidv7_without_legacy_prefixes() -> None:
    operation_id = new_operation_id("nomina")

    parsed = uuid.UUID(operation_id)
    assert parsed.version == 7
    assert operation_id == operation_id.lower()
    assert not operation_id.startswith("nomina-")


def test_rrhh_events_do_not_import_or_call_uuid4_for_operation_identity() -> None:
    content = (REPO_ROOT / "pos_spj_v13.4" / "core" / "rrhh" / "events.py").read_text(encoding="utf-8")

    assert "from backend.shared.ids import new_uuid" in content
    assert "from uuid import uuid4" not in content
    assert "uuid4(" not in content
