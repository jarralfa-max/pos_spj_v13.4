# tests/test_refactor_v133.py — SPJ POS v13.3
"""
Tests para los componentes del refactoring incremental v13.3.

Cubre:
  1. DomainEvent — inmutabilidad, hash, serialización
  2. DomainValidators — inventario, ventas, producción
  3. ConflictResolver con validadores
  4. EventBus wiring (smoke test)

Ejecutar:
  python -m pytest tests/test_refactor_v133.py -v
"""
import json
import sqlite3
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_db():
    """Base de datos en memoria con tablas mínimas para sync."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sync_conflicts (
            id TEXT PRIMARY KEY,
            event_id TEXT,
            conflict_type TEXT,
            local_version INTEGER DEFAULT 0,
            remote_version INTEGER DEFAULT 0,
            remote_hash TEXT,
            computed_hash TEXT,
            resolved INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accion TEXT, modulo TEXT, entidad TEXT,
            entidad_id INTEGER, usuario TEXT,
            sucursal_id INTEGER, detalles TEXT, fecha TEXT
        );
        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE, tipo TEXT, entidad TEXT,
            entidad_id INTEGER, payload TEXT,
            payload_hash TEXT, sucursal_id INTEGER DEFAULT 1,
            usuario TEXT DEFAULT 'test',
            origin_device_id TEXT DEFAULT 'test-device',
            device_version INTEGER DEFAULT 0,
            event_version INTEGER DEFAULT 1,
            synced INTEGER DEFAULT 0,
            operation_id TEXT DEFAULT '',
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sync_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT, tabla TEXT, operacion TEXT,
            registro_id INTEGER, payload TEXT,
            sucursal_id INTEGER, lamport_ts INTEGER DEFAULT 0,
            enviado INTEGER DEFAULT 0, fecha REAL
        );
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY, value TEXT
        );
    """)
    yield conn
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# 1. DomainEvent
# ══════════════════════════════════════════════════════════════════════════════

class TestDomainEvent:

    def test_create_event_generates_uuid(self):
        from core.domain.events import DomainEvent
        e = DomainEvent(event_type="TEST", data={"x": 1})
        assert len(e.event_id) == 36  # UUID format
        assert e.event_type == "TEST"

    def test_event_is_frozen(self):
        from core.domain.events import DomainEvent
        e = DomainEvent(event_type="TEST")
        with pytest.raises(AttributeError):
            e.event_type = "MODIFIED"

    def test_payload_hash_deterministic(self):
        from core.domain.events import DomainEvent
        data = {"venta_id": 42, "total": 350.00, "folio": "V-001"}
        e1 = DomainEvent(event_type="VENTA", data=data)
        e2 = DomainEvent(event_type="VENTA", data=data)
        assert e1.payload_hash == e2.payload_hash

    def test_payload_hash_changes_with_data(self):
        from core.domain.events import DomainEvent
        e1 = DomainEvent(event_type="VENTA", data={"total": 100})
        e2 = DomainEvent(event_type="VENTA", data={"total": 200})
        assert e1.payload_hash != e2.payload_hash

    def test_to_dict_includes_hash(self):
        from core.domain.events import DomainEvent
        e = DomainEvent(event_type="TEST", data={"key": "value"})
        d = e.to_dict()
        assert "payload_hash" in d
        assert "event_id" in d
        assert "timestamp" in d
        assert d["event_type"] == "TEST"

    def test_to_dict_is_json_serializable(self):
        from core.domain.events import DomainEvent
        e = DomainEvent(
            event_type="VENTA_COMPLETADA",
            sucursal_id=2,
            usuario="cajero01",
            data={"venta_id": 42, "total": 350.00},
        )
        # Must not raise
        json_str = json.dumps(e.to_dict(), ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["sucursal_id"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# 2. DomainValidators
# ══════════════════════════════════════════════════════════════════════════════

class TestInventoryValidator:

    def test_accepts_valid_stock(self):
        from sync.domain_validators.inventory_validator import InventoryValidator
        v = InventoryValidator(allow_negative=False)
        err = v.validate(
            "branch_inventory",
            {"existencia": 10.0, "costo_promedio": 50.0},
            {"existencia": 12.0},
            {"existencia": 10.0},
        )
        assert err is None

    def test_rejects_negative_stock(self):
        from sync.domain_validators.inventory_validator import InventoryValidator
        v = InventoryValidator(allow_negative=False)
        err = v.validate(
            "branch_inventory",
            {"existencia": -5.0, "producto_id": 42},
            {"existencia": 10.0},
            {"existencia": -5.0},
        )
        assert err is not None
        assert "negativo" in err.lower()

    def test_allows_negative_when_configured(self):
        from sync.domain_validators.inventory_validator import InventoryValidator
        v = InventoryValidator(allow_negative=True)
        err = v.validate(
            "branch_inventory",
            {"existencia": -5.0},
            {"existencia": 10.0},
            {"existencia": -5.0},
        )
        assert err is None

    def test_rejects_zero_cost_with_positive_stock(self):
        from sync.domain_validators.inventory_validator import InventoryValidator
        v = InventoryValidator()
        err = v.validate(
            "movimientos_inventario",
            {"existencia": 10.0, "costo_promedio": 0.0},
            {"existencia": 10.0, "costo_promedio": 50.0},
            {"existencia": 10.0, "costo_promedio": 0.0},
        )
        assert err is not None
        assert "costo" in err.lower()

    def test_ignores_non_inventory_tables(self):
        from sync.domain_validators.inventory_validator import InventoryValidator
        v = InventoryValidator()
        err = v.validate("clientes", {"existencia": -99}, {}, {})
        assert err is None


class TestSalesValidator:

    def test_accepts_valid_sale(self):
        from sync.domain_validators.sales_validator import SalesValidator
        v = SalesValidator()
        err = v.validate(
            "ventas",
            {"total": 100.0, "cancelada": 0},
            {"total": 100.0, "cancelada": 0},
            {"total": 100.0, "cancelada": 0},
        )
        assert err is None

    def test_rejects_uncancellation(self):
        from sync.domain_validators.sales_validator import SalesValidator
        v = SalesValidator()
        err = v.validate(
            "ventas",
            {"total": 100.0, "cancelada": 0},
            {"total": 100.0, "cancelada": 1, "folio": "V-001"},
            {"total": 100.0, "cancelada": 0},
        )
        assert err is not None
        assert "cancelada" in err.lower()

    def test_rejects_suspicious_total_delta(self):
        from sync.domain_validators.sales_validator import SalesValidator
        v = SalesValidator(max_total_delta_pct=10.0)
        err = v.validate(
            "ventas",
            {"total": 500.0, "folio": "V-002"},
            {"total": 100.0, "folio": "V-002"},
            {"total": 500.0},
        )
        assert err is not None
        assert "delta" in err.lower()

    def test_ignores_non_sales_tables(self):
        from sync.domain_validators.sales_validator import SalesValidator
        v = SalesValidator()
        err = v.validate("productos", {"cancelada": 1}, {}, {})
        assert err is None


class TestProductionValidator:

    def test_accepts_valid_batch(self):
        from sync.domain_validators.production_validator import ProductionValidator
        v = ProductionValidator()
        err = v.validate(
            "production_batches",
            {"estado": "cerrado", "source_weight": 100, "total_output_weight": 85},
            {"estado": "abierto"},
            {"estado": "cerrado", "source_weight": 100, "total_output_weight": 85},
        )
        assert err is None

    def test_rejects_reopening_closed_batch(self):
        from sync.domain_validators.production_validator import ProductionValidator
        v = ProductionValidator()
        err = v.validate(
            "production_batches",
            {"estado": "abierto"},
            {"estado": "cerrado", "folio": "L-001"},
            {"estado": "abierto"},
        )
        assert err is not None
        assert "cerrado" in err.lower()

    def test_rejects_extreme_merma(self):
        from sync.domain_validators.production_validator import ProductionValidator
        v = ProductionValidator(max_merma_pct=50.0)
        err = v.validate(
            "production_batches",
            {"estado": "cerrado", "source_weight": 100, "total_output_weight": 10,
             "folio": "L-002"},
            {"source_weight": 100, "total_output_weight": 85},
            {"source_weight": 100, "total_output_weight": 10},
        )
        assert err is not None
        assert "peso" in err.lower()

    def test_ignores_non_production_tables(self):
        from sync.domain_validators.production_validator import ProductionValidator
        v = ProductionValidator()
        err = v.validate("ventas", {"estado": "cerrado"}, {}, {})
        assert err is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. ConflictResolver con validadores
# ══════════════════════════════════════════════════════════════════════════════

class TestConflictResolverWithValidators:

    def test_resolver_without_validators_works(self, mem_db):
        from sync.conflict_resolver import ConflictResolver
        r = ConflictResolver(mem_db)
        result = r.resolve(
            "evt-1", "clientes",
            {"nombre": "Local", "device_version": 1},
            {"nombre": "Remote", "device_version": 2},
        )
        assert result is not None
        assert result["nombre"] == "Remote"  # LWW

    def test_validator_can_reject_resolution(self, mem_db):
        from sync.conflict_resolver import ConflictResolver
        from sync.domain_validators.inventory_validator import InventoryValidator

        r = ConflictResolver(mem_db, validators=[InventoryValidator()])
        result = r.resolve(
            "evt-2", "branch_inventory",
            {"existencia": 10.0, "producto_id": 5, "device_version": 1},
            {"existencia": -5.0, "producto_id": 5, "device_version": 2},
        )
        # Validator should reject negative stock → None
        assert result is None

        # Verify conflict was saved
        row = mem_db.execute(
            "SELECT conflict_type FROM sync_conflicts WHERE event_id='evt-2'"
        ).fetchone()
        assert row is not None
        assert "DOMAIN_VALIDATION" in row[0]

    def test_validator_accepts_valid_resolution(self, mem_db):
        from sync.conflict_resolver import ConflictResolver
        from sync.domain_validators.sales_validator import SalesValidator

        r = ConflictResolver(mem_db, validators=[SalesValidator()])
        result = r.resolve(
            "evt-3", "ventas",
            {"total": 100.0, "cancelada": 0, "device_version": 1},
            {"total": 105.0, "cancelada": 0, "device_version": 2},
        )
        assert result is not None  # 5% delta is within tolerance

    def test_multiple_validators_all_must_pass(self, mem_db):
        from sync.conflict_resolver import ConflictResolver
        from sync.domain_validators import get_default_validators

        validators = get_default_validators(allow_negative_stock=False)
        r = ConflictResolver(mem_db, validators=validators)

        # Valid inventory update — should pass all validators
        result = r.resolve(
            "evt-4", "branch_inventory",
            {"existencia": 20.0, "costo_promedio": 50.0, "device_version": 1},
            {"existencia": 15.0, "costo_promedio": 48.0, "device_version": 2},
        )
        assert result is not None

    def test_additive_strategy_preserved(self, mem_db):
        from sync.conflict_resolver import ConflictResolver
        r = ConflictResolver(mem_db)
        # movimientos_inventario is ADDITIVE
        result = r.resolve(
            "evt-5", "movimientos_inventario",
            {"cantidad": 20, "device_version": 1},
            {"cantidad": 17, "device_version": 2},
        )
        assert result is not None

    def test_server_auth_strategy_preserved(self, mem_db):
        from sync.conflict_resolver import ConflictResolver
        r = ConflictResolver(mem_db)
        # ventas is SERVER_AUTH
        result = r.resolve(
            "evt-6", "ventas",
            {"total": 100, "device_version": 1},
            {"total": 200, "device_version": 2},
        )
        assert result is not None
        assert result["total"] == 200  # server wins


# ══════════════════════════════════════════════════════════════════════════════
# 4. EventBus smoke test
# ══════════════════════════════════════════════════════════════════════════════

class TestEventBusSmoke:

    def test_publish_subscribe_works(self):
        from core.events.event_bus import EventBus
        # Use fresh instance for test isolation
        bus = EventBus.__new__(EventBus)
        bus._handlers = {}
        bus._lock = __import__("threading").RLock()
        bus._executor = __import__("concurrent.futures").ThreadPoolExecutor(
            max_workers=1
        )

        received = []
        bus.subscribe("TEST_EVENT", lambda d: received.append(d))
        bus.publish("TEST_EVENT", {"value": 42})
        assert len(received) == 1
        assert received[0]["value"] == 42

    def test_priority_order(self):
        from core.events.event_bus import EventBus
        bus = EventBus.__new__(EventBus)
        bus._handlers = {}
        bus._lock = __import__("threading").RLock()
        bus._executor = __import__("concurrent.futures").ThreadPoolExecutor(
            max_workers=1
        )

        order = []
        bus.subscribe("PRI", lambda d: order.append("low"), priority=10)
        bus.subscribe("PRI", lambda d: order.append("high"), priority=100)
        bus.publish("PRI", {})
        assert order == ["high", "low"]

    def test_handler_failure_doesnt_block_others(self):
        from core.events.event_bus import EventBus
        bus = EventBus.__new__(EventBus)
        bus._handlers = {}
        bus._lock = __import__("threading").RLock()
        bus._executor = __import__("concurrent.futures").ThreadPoolExecutor(
            max_workers=1
        )

        results = []

        def failing_handler(d):
            raise RuntimeError("boom")

        def ok_handler(d):
            results.append("ok")

        bus.subscribe("FAIL_TEST", failing_handler, priority=100)
        bus.subscribe("FAIL_TEST", ok_handler, priority=50)
        bus.publish("FAIL_TEST", {})
        assert results == ["ok"]  # second handler still ran
