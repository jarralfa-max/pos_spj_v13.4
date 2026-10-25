import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CashOfflineFirstBoundaryTest(unittest.TestCase):
    def test_sync_schema_is_migration_owned(self):
        migration = (ROOT / "migrations/standalone/175_cash_register_bounded_context_schema.py").read_text(encoding="utf-8")
        self.assertIn("cash_sync_devices", migration)
        self.assertIn("cash_sync_envelopes", migration)
        for path in (ROOT / "backend/application/cash_register").glob("*.py"):
            self.assertNotIn("CREATE TABLE", path.read_text(encoding="utf-8").upper(), path)

    def test_transport_is_a_port_and_ui_has_no_sync_sql(self):
        source = (ROOT / "backend/application/cash_register/offline_sync.py").read_text(encoding="utf-8")
        # Slice 2: el puerto es el del motor de replicación único.
        self.assertIn("CashSyncTransport = ReplicationTransport", source)
        self.assertIn("class ReplicationTransport(Protocol)", (
            ROOT / "backend/application/sync/replication_outbox.py").read_text(encoding="utf-8"))

    def test_sync_never_writes_the_finance_outbox(self):
        """El motor viejo marcaba cash_outbox FAILED/DISPATCHED y Finanzas, que
        sólo toma PENDING, nunca asentaba esos movimientos."""
        for ruta in ("backend/application/cash_register/offline_sync.py",
                     "backend/application/sync/replication_outbox.py",
                     "backend/infrastructure/db/repositories/replication/replication_repository.py"):
            texto = (ROOT / ruta).read_text(encoding="utf-8")
            self.assertNotIn("UPDATE cash_outbox", texto, ruta)
        for path in (ROOT / "frontend/desktop/modules/cash_register").rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("cash_sync_envelopes", text, path)

    def test_sequence_is_ordering_not_identity(self):
        migration = (ROOT / "migrations/standalone/175_cash_register_bounded_context_schema.py").read_text(encoding="utf-8").upper()
        self.assertNotIn("AUTOINCREMENT", migration)
        # Forma fuerte: en SQLite una PK TEXT sin NOT NULL acepta un id NULL.
        self.assertIn("ID TEXT NOT NULL PRIMARY KEY", migration)
        self.assertNotIn("ID TEXT PRIMARY KEY", migration)


if __name__ == "__main__": unittest.main()
