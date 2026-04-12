# tests/test_fase2_loyalty_scanner.py
# Fase 2 — loyalty_ledger, scan_event_log, LoyaltyService métodos, flujo dual ventas
# NO importa PyQt5 — usa SQLite en-memoria y parsing AST/texto.

import sys, os, sqlite3, ast, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import importlib.util


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_migration(filename):
    """Carga dinámicamente una migración standalone (nombres con dígitos)."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "..", "migrations", "standalone", filename)
    spec = importlib.util.spec_from_file_location("_mig", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _db_with_loyalty(apply_ledger=True, apply_scan=True):
    """DB en-memoria con tablas mínimas de Fase 2."""
    conn = _mem_db()
    conn.executescript("""
        CREATE TABLE clientes (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT    NOT NULL,
            telefono TEXT   DEFAULT '',
            puntos  INTEGER DEFAULT 0
        );
        CREATE TABLE configuraciones (
            clave   TEXT PRIMARY KEY,
            valor   TEXT
        );
        INSERT INTO configuraciones VALUES ('loyalty_valor_estrella','0.10');
    """)
    if apply_ledger:
        _load_migration("057_loyalty_ledger_unificado.py").run(conn)
    if apply_scan:
        _load_migration("058_scan_event_log.py").run(conn)
    conn.commit()
    return conn


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1 — Migración 057: loyalty_ledger_unificado
# ══════════════════════════════════════════════════════════════════════════════

class TestMigracion057:

    def test_tabla_loyalty_ledger_creada(self):
        conn = _mem_db()
        _load_migration("057_loyalty_ledger_unificado.py").run(conn)
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='loyalty_ledger'"
        ).fetchone()
        assert row is not None, "La tabla loyalty_ledger debe existir"

    def test_columnas_requeridas(self):
        conn = _mem_db()
        _load_migration("057_loyalty_ledger_unificado.py").run(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(loyalty_ledger)").fetchall()}
        required = {"cliente_id", "tipo", "puntos", "monto_equiv",
                    "saldo_post", "referencia", "descripcion", "sucursal_id",
                    "usuario", "created_at"}
        assert required.issubset(cols), f"Columnas faltantes: {required - cols}"

    def test_insert_tipos_validos(self):
        conn = _mem_db()
        _load_migration("057_loyalty_ledger_unificado.py").run(conn)
        for tipo in ("acumulacion", "canje", "reversa", "ajuste"):
            conn.execute(
                "INSERT INTO loyalty_ledger(cliente_id,tipo,puntos) VALUES(1,?,10)",
                (tipo,))
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM loyalty_ledger").fetchone()[0]
        assert count == 4

    def test_tipo_invalido_rechazado(self):
        conn = _mem_db()
        _load_migration("057_loyalty_ledger_unificado.py").run(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO loyalty_ledger(cliente_id,tipo,puntos) VALUES(1,'invalido',5)")
            conn.commit()

    def test_idempotente(self):
        conn = _mem_db()
        mod = _load_migration("057_loyalty_ledger_unificado.py")
        mod.run(conn)
        mod.run(conn)   # segunda vez no debe lanzar
        conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 — Migración 058: scan_event_log
# ══════════════════════════════════════════════════════════════════════════════

class TestMigracion058:

    def test_tabla_scan_event_log_creada(self):
        conn = _mem_db()
        _load_migration("058_scan_event_log.py").run(conn)
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scan_event_log'"
        ).fetchone()
        assert row is not None

    def test_columnas_requeridas(self):
        conn = _mem_db()
        _load_migration("058_scan_event_log.py").run(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(scan_event_log)").fetchall()}
        required = {"raw_code", "tipo", "contexto", "accion", "payload",
                    "cliente_id", "producto_id", "sucursal_id", "usuario", "created_at"}
        assert required.issubset(cols), f"Columnas faltantes: {required - cols}"

    def test_insert_basico(self):
        conn = _mem_db()
        _load_migration("058_scan_event_log.py").run(conn)
        conn.execute(
            "INSERT INTO scan_event_log(raw_code, tipo) VALUES(?,?)",
            ("TF-ABC123", "tarjeta"))
        conn.commit()
        row = conn.execute(
            "SELECT raw_code FROM scan_event_log LIMIT 1").fetchone()
        assert row[0] == "TF-ABC123"

    def test_idempotente(self):
        conn = _mem_db()
        mod = _load_migration("058_scan_event_log.py")
        mod.run(conn)
        mod.run(conn)
        conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 3 — LoyaltyService: registrar_en_ledger
# ══════════════════════════════════════════════════════════════════════════════

class TestLoyaltyServiceLedger:

    def _make_service(self):
        conn = _db_with_loyalty()
        conn.execute("INSERT INTO clientes(nombre,puntos) VALUES('Ana',50)")
        conn.commit()
        from core.services.loyalty_service import LoyaltyService
        svc = LoyaltyService.__new__(LoyaltyService)
        svc.db = conn
        svc.sucursal_id = 1
        svc._module_config = None
        svc._engine = None
        svc._bus    = None
        return svc, conn

    def test_registrar_acumulacion(self):
        svc, conn = self._make_service()
        ok = svc.registrar_en_ledger(
            cliente_id=1, tipo="acumulacion", puntos=10,
            referencia="V001", descripcion="Compra test", usuario="cajero")
        assert ok is True
        row = conn.execute(
            "SELECT tipo, puntos FROM loyalty_ledger WHERE cliente_id=1"
        ).fetchone()
        assert row["tipo"] == "acumulacion"
        assert row["puntos"] == 10

    def test_registrar_canje_negativo(self):
        svc, conn = self._make_service()
        ok = svc.registrar_en_ledger(
            cliente_id=1, tipo="canje", puntos=-5,
            referencia="V001")
        assert ok is True
        row = conn.execute(
            "SELECT puntos FROM loyalty_ledger WHERE cliente_id=1"
        ).fetchone()
        assert row["puntos"] == -5

    def test_monto_equiv_calculado(self):
        svc, conn = self._make_service()
        svc.registrar_en_ledger(
            cliente_id=1, tipo="acumulacion", puntos=20)
        row = conn.execute(
            "SELECT monto_equiv FROM loyalty_ledger WHERE cliente_id=1"
        ).fetchone()
        # 20 pts * $0.10 = $2.00
        assert abs(row["monto_equiv"] - 2.0) < 0.01


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 4 — LoyaltyService: reversar_canje
# ══════════════════════════════════════════════════════════════════════════════

class TestLoyaltyServiceReversa:

    def _make_service(self):
        conn = _db_with_loyalty()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS loyalty_pasivo_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT (datetime('now')),
                tipo TEXT NOT NULL,
                estrellas INTEGER DEFAULT 0,
                valor_unitario REAL DEFAULT 0.10,
                monto_total REAL DEFAULT 0.0,
                referencia TEXT DEFAULT '',
                sucursal_id INTEGER DEFAULT 1
            );
        """)
        conn.execute("INSERT INTO clientes(nombre,puntos) VALUES('Juan',30)")
        conn.commit()
        from core.services.loyalty_service import LoyaltyService
        svc = LoyaltyService.__new__(LoyaltyService)
        svc.db = conn
        svc.sucursal_id = 1
        svc._module_config = None
        svc._engine = None
        svc._bus    = None
        return svc, conn

    def test_reversar_devuelve_puntos(self):
        svc, conn = self._make_service()
        res = svc.reversar_canje(
            cliente_id=1, puntos_canjeados=10,
            referencia="V001", usuario="gerente")
        assert res["ok"] is True
        assert res["puntos_devueltos"] == 10

    def test_puntos_incrementados_en_clientes(self):
        svc, conn = self._make_service()
        svc.reversar_canje(cliente_id=1, puntos_canjeados=8)
        row = conn.execute(
            "SELECT puntos FROM clientes WHERE id=1").fetchone()
        assert row[0] == 38   # 30 originales + 8 devueltos

    def test_reversa_registrada_en_ledger(self):
        svc, conn = self._make_service()
        svc.reversar_canje(cliente_id=1, puntos_canjeados=5, referencia="V002")
        row = conn.execute(
            "SELECT tipo, puntos FROM loyalty_ledger WHERE referencia='V002'"
        ).fetchone()
        assert row is not None
        assert row["tipo"] == "reversa"
        assert row["puntos"] == 5

    def test_parametros_invalidos_rechazados(self):
        svc, conn = self._make_service()
        res = svc.reversar_canje(cliente_id=1, puntos_canjeados=0)
        assert res["ok"] is False

    def test_cliente_id_cero_rechazado(self):
        svc, conn = self._make_service()
        res = svc.reversar_canje(cliente_id=0, puntos_canjeados=10)
        assert res["ok"] is False


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 5 — LoyaltyService: get_ledger_cliente
# ══════════════════════════════════════════════════════════════════════════════

class TestGetLedgerCliente:

    def _make_service_with_movements(self):
        conn = _db_with_loyalty()
        conn.execute("INSERT INTO clientes(nombre,puntos) VALUES('Maria',100)")
        conn.commit()
        from core.services.loyalty_service import LoyaltyService
        svc = LoyaltyService.__new__(LoyaltyService)
        svc.db = conn
        svc.sucursal_id = 1
        svc._module_config = None
        svc._engine = None
        svc._bus    = None
        # Insertar 3 movimientos
        for i in range(3):
            svc.registrar_en_ledger(
                cliente_id=1, tipo="acumulacion", puntos=10 * (i + 1),
                referencia=f"V00{i}")
        return svc, conn

    def test_retorna_lista(self):
        svc, _ = self._make_service_with_movements()
        result = svc.get_ledger_cliente(1)
        assert isinstance(result, list)
        assert len(result) == 3

    def test_orden_descendente(self):
        svc, _ = self._make_service_with_movements()
        result = svc.get_ledger_cliente(1)
        # Último inserido (puntos=30) debe aparecer primero
        assert result[0]["puntos"] == 30

    def test_limit_respetado(self):
        svc, _ = self._make_service_with_movements()
        result = svc.get_ledger_cliente(1, limit=2)
        assert len(result) == 2

    def test_cliente_sin_movimientos(self):
        svc, conn = self._make_service_with_movements()
        conn.execute("INSERT INTO clientes(nombre,puntos) VALUES('Nuevo',0)")
        conn.commit()
        result = svc.get_ledger_cliente(2)
        assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 6 — ventas.py: _abrir_nuevo_cliente_con_tarjeta y flujo dual (AST)
# ══════════════════════════════════════════════════════════════════════════════

class TestVentasFlujoDualAST:
    """Verifica por lectura de código fuente (sin importar PyQt5)."""

    @pytest.fixture(autouse=True)
    def _src(self):
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, "..", "modulos", "ventas.py")
        self.src = open(path, encoding="utf-8").read()

    def test_metodo_abrir_nuevo_cliente_con_tarjeta_existe(self):
        assert "def _abrir_nuevo_cliente_con_tarjeta" in self.src

    def test_metodo_acepta_codigo_param(self):
        m = re.search(r"def _abrir_nuevo_cliente_con_tarjeta\(self,\s*codigo", self.src)
        assert m is not None, "El parámetro 'codigo' debe estar en la firma"

    def test_flujo_dual_detecta_patron_tarjeta(self):
        # El regex TF|TAR|CARD debe estar presente
        assert re.search(r"TF\|TAR\|CARD", self.src) is not None

    def test_flujo_dual_llama_abrir_nuevo_cliente(self):
        assert "_abrir_nuevo_cliente_con_tarjeta(codigo)" in self.src

    def test_dialogo_agregar_cliente_usado(self):
        assert "DialogoAgregarCliente" in self.src

    def test_txt_tarjeta_id_precargado(self):
        assert "txt_tarjeta_id.setText(codigo)" in self.src

    def test_guardar_nuevo_cliente_llamado(self):
        assert "guardar_nuevo_cliente(cliente_data)" in self.src

    def test_notif_scanner_card_tipo(self):
        # La notificación debe usar tipo "card" (puede estar en línea separada)
        assert re.search(r'_mostrar_notif_scanner\(.*"card"\)', self.src, re.DOTALL) is not None
