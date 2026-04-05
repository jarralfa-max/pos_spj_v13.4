
# sync/sync_engine.py — SPJ POS v9
"""
Motor de sincronización multi-sucursal con cola persistente.
Arquitectura offline-first:
  1. Todas las escrituras se loguean en sync_outbox (tabla local)
  2. SyncWorker envía el outbox al servidor central cada N segundos
  3. SyncWorker descarga cambios del servidor e integra localmente
  4. Conflictos resueltos por: last-write-wins con lamport clock
"""
from __future__ import annotations
import threading, time, json, logging, uuid, hashlib
from datetime import datetime
from core.db.connection import get_connection, close_thread_connection

logger = logging.getLogger("spj.sync")

LAMPORT_KEY = "lamport"  # v13.2: shared constant — also used by SyncService

TABLAS_SINCRONIZABLES = [
    "productos", "clientes", "ventas", "detalles_venta",
    "movimientos_inventario", "movimientos_caja",
    "ordenes_compra", "delivery_orders",
]


class SyncEngine:
    """Gestiona el outbox local y la integración de cambios remotos."""

    def __init__(self, conn, sucursal_id: int = 1):
        self.conn = conn
        self.sucursal_id = sucursal_id
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sync_outbox (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid        TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
                tabla       TEXT NOT NULL,
                operacion   TEXT NOT NULL,   -- INSERT / UPDATE / DELETE
                registro_id INTEGER,
                payload     TEXT,            -- JSON del registro
                sucursal_id INTEGER,
                lamport_ts  INTEGER DEFAULT 0,
                enviado     INTEGER DEFAULT 0,
                intentos    INTEGER DEFAULT 0,
                error_msg   TEXT,
                fecha       REAL DEFAULT (unixepoch())
            );
            CREATE TABLE IF NOT EXISTS sync_inbox (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid        TEXT UNIQUE,
                tabla       TEXT NOT NULL,
                operacion   TEXT NOT NULL,
                registro_id INTEGER,
                payload     TEXT,
                sucursal_origen INTEGER,
                lamport_ts  INTEGER DEFAULT 0,
                integrado   INTEGER DEFAULT 0,
                fecha_recibido REAL DEFAULT (unixepoch())
            );
            CREATE TABLE IF NOT EXISTS sync_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_pendiente
                ON sync_outbox(enviado, fecha) WHERE enviado=0;
        """)
        try: self.conn.commit()
        except Exception: pass

    # ── Lamport clock ──────────────────────────────────────────────────────
    def _get_lamport(self) -> int:
        row = self.conn.execute(
            "SELECT value FROM sync_state WHERE key=?", (LAMPORT_KEY,)).fetchone()
        return int(row[0]) if row else 0

    def _tick_lamport(self) -> int:
        """Atomic increment via BEGIN IMMEDIATE (v13.2: fixes race on multi-terminal)."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            ts = self._get_lamport() + 1
            self.conn.execute(
                "INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)",
                (LAMPORT_KEY, str(ts)))
            try: self.conn.execute("COMMIT")

            except Exception: pass
            return ts
        except Exception:
            try: self.conn.execute("ROLLBACK")
            except Exception: pass
            # Fallback: non-atomic increment
            ts = self._get_lamport() + 1
            self.conn.execute(
                "INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)",
                (LAMPORT_KEY, str(ts)))
            return ts

    # ── Registrar cambio local en outbox ──────────────────────────────────
    def record_change(self, tabla: str, operacion: str,
                      registro_id: int, payload: dict) -> None:
        if tabla not in TABLAS_SINCRONIZABLES:
            return
        ts = self._tick_lamport()
        self.conn.execute(
            """INSERT INTO sync_outbox
               (tabla, operacion, registro_id, payload, sucursal_id, lamport_ts)
               VALUES(?,?,?,?,?,?)""",
            (tabla, operacion, registro_id,
             json.dumps(payload, default=str),
             self.sucursal_id, ts))
        try: self.conn.commit()
        except Exception: pass

    # ── Obtener pendientes para enviar ────────────────────────────────────
    def get_pending(self, limit: int = 100) -> list:
        rows = self.conn.execute(
            """SELECT id, uuid, tabla, operacion, registro_id, payload, lamport_ts
               FROM sync_outbox WHERE enviado=0
               ORDER BY lamport_ts ASC LIMIT ?""",
            (limit,)).fetchall()
        return [dict(r) for r in rows]

    def mark_sent(self, outbox_ids: list) -> None:
        for oid in outbox_ids:
            self.conn.execute(
                "UPDATE sync_outbox SET enviado=1 WHERE id=?", (oid,))
        try: self.conn.commit()
        except Exception: pass

    def mark_failed(self, outbox_id: int, error: str) -> None:
        self.conn.execute(
            "UPDATE sync_outbox SET intentos=intentos+1, error_msg=? WHERE id=?",
            (error[:200], outbox_id))
        try: self.conn.commit()
        except Exception: pass

    # ── Integrar cambio remoto ────────────────────────────────────────────
    def integrate_remote(self, item: dict) -> bool:
        """
        Integra un cambio recibido del servidor.
        v13.2: Idempotencia por uuid — skip si ya fue aplicado.
        Resolución de conflictos: last-write-wins por lamport_ts.
        """
        uuid_val = item.get("uuid", "")
        if uuid_val:
            already = self.conn.execute(
                "SELECT 1 FROM sync_inbox WHERE uuid=? AND integrado=1",
                (uuid_val,)
            ).fetchone()
            if already:
                logger.debug("integrate_remote: uuid=%s ya aplicado — skip", uuid_val[:8])
                return True

        tabla      = item["tabla"]
        operacion  = item["operacion"]
        reg_id     = item["registro_id"]
        payload    = json.loads(item["payload"]) if isinstance(item["payload"], str) else item["payload"]
        remote_ts  = item.get("lamport_ts", 0)

        if tabla not in TABLAS_SINCRONIZABLES:
            return False
        try:
            if operacion == "DELETE":
                self.conn.execute(f"DELETE FROM {tabla} WHERE id=?", (reg_id,))
            else:
                cols = list(payload.keys())
                if not cols:
                    return False

                # v13.2: domain-aware conflict resolution
                existing_row = self.conn.execute(
                    f"SELECT * FROM {tabla} WHERE id=?", (reg_id,)
                ).fetchone()
                if existing_row:
                    from sync.conflict_resolver import ConflictResolver
                    from sync.domain_validators import get_default_validators
                    resolver = ConflictResolver(self.conn, validators=get_default_validators())
                    resolved = resolver.resolve(
                        event_id=uuid_val,
                        tabla=tabla,
                        local_payload=dict(existing_row),
                        remote_payload=payload,
                    )
                    if resolved is None:
                        # MANUAL_REVIEW — do not apply
                        resolver.save_manual_conflict(
                            uuid_val, tabla, dict(existing_row), payload
                        )
                        return False
                    payload = resolved
                    cols = list(payload.keys())

                placeholders = ",".join("?" * len(cols))
                updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
                sql = (f"INSERT INTO {tabla}({','.join(cols)}) VALUES({placeholders})"
                       f" ON CONFLICT(id) DO UPDATE SET {updates}")
                self.conn.execute(sql, list(payload.values()))
            # Update lamport
            local_ts = self._get_lamport()
            if remote_ts > local_ts:
                self.conn.execute(
                    "INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)",
                    (LAMPORT_KEY, str(remote_ts + 1)))
            # Mark as applied for idempotency
            if uuid_val:
                try:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO sync_inbox"
                        "(uuid,tabla,operacion,registro_id,integrado,fecha_recibido)"
                        " VALUES(?,?,?,?,1,unixepoch())",
                        (uuid_val, tabla, operacion, reg_id))
                except Exception:
                    pass
            try: self.conn.commit()
            except Exception: pass
            return True
        except Exception as e:
            logger.warning("integrate_remote error (%s/%s): %s", tabla, reg_id, e)
            return False

    # ── Stats ──────────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        pending = self.conn.execute(
            "SELECT COUNT(*) FROM sync_outbox WHERE enviado=0").fetchone()[0]
        sent    = self.conn.execute(
            "SELECT COUNT(*) FROM sync_outbox WHERE enviado=1").fetchone()[0]
        failed  = self.conn.execute(
            "SELECT COUNT(*) FROM sync_outbox WHERE intentos>=3").fetchone()[0]
        last_ts = self.conn.execute(
            "SELECT value FROM sync_state WHERE key='lamport'").fetchone()
        return {
            "pendientes": pending,
            "enviados": sent,
            "fallidos": failed,
            "lamport_ts": int(last_ts[0]) if last_ts else 0,
        }


class SyncWorker(threading.Thread):
    """
    Worker thread que sincroniza periodicamente.
    En modo LOCAL (sin servidor): solo loggea el outbox.
    En modo SERVIDOR: envia via HTTP al central.
    """
    def __init__(self, db_path: str, sucursal_id: int = 1,
                 server_url: str = None, interval: int = 30):
        super().__init__(daemon=True, name="SyncWorker")
        self.db_path     = db_path
        self.sucursal_id = sucursal_id
        self.server_url  = server_url   # None = modo local
        self.interval    = interval
        self._stop       = threading.Event()

    def run(self):
        logger.info("SyncWorker iniciado — modo %s — intervalo %ds",
                    "HTTP" if self.server_url else "LOCAL", self.interval)
        while not self._stop.wait(self.interval):
            try:
                conn = get_connection(self.db_path)
                engine = SyncEngine(conn, self.sucursal_id)
                pending = engine.get_pending(100)
                if pending:
                    if self.server_url:
                        self._sync_http(engine, pending)
                    else:
                        logger.debug("Sync LOCAL: %d cambios pendientes (sin servidor)", len(pending))
            except Exception as e:
                logger.error("SyncWorker error: %s", e)

    def _sync_http(self, engine: SyncEngine, pending: list):
        """Envía el outbox al servidor central via HTTP."""
        try:
            import urllib.request, json as _json
            body = _json.dumps({
                "sucursal_id": engine.sucursal_id,
                "changes": pending
            }).encode()
            req = urllib.request.Request(
                f"{self.server_url}/api/sync/push",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = _json.loads(resp.read())
                sent_ids = result.get("accepted_ids", [r["id"] for r in pending])
                engine.mark_sent(sent_ids)
                logger.info("Sync: %d cambios enviados al servidor", len(sent_ids))
        except Exception as e:
            for item in pending:
                engine.mark_failed(item["id"], str(e))
            logger.warning("Sync HTTP fallido: %s", e)

    def stop(self):
        self._stop.set()
        close_thread_connection()
