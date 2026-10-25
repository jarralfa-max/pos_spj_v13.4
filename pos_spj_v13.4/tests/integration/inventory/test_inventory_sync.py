"""INV-22 — ingestor idempotente del lado receptor.

El despachador de envío de INV-22 se retiró en el Slice 2 de la arquitectura
híbrida: lo reemplaza el motor de replicación único, probado en
`tests/integration/sync/test_replication_outbox.py`.
"""

import sqlite3

import pytest

from backend.application.inventory.sync import InventoryEventIngestor
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


class TestIngestor:
    def test_applies_once_and_skips_duplicate(self, conn):
        applied = []
        ing = InventoryEventIngestor(conn)
        ev = {"event_id": "e1", "event_name": "X", "operation_id": "o1"}
        assert ing.ingest(ev, lambda e, uow: applied.append(e["event_id"])) is True
        assert ing.ingest(ev, lambda e, uow: applied.append(e["event_id"])) is False
        assert applied == ["e1"]  # effect ran exactly once

    def test_missing_event_id_rejected(self, conn):
        with pytest.raises(ValueError):
            InventoryEventIngestor(conn).ingest({"event_name": "X"})
