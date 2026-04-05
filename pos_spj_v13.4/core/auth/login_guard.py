
# core/auth/login_guard.py — SPJ POS v9
"""
Proteccion de login con limite de intentos y bloqueo temporal.
  5 intentos fallidos -> bloqueo 5 min
 10 intentos          -> bloqueo 30 min
 15+ intentos         -> bloqueo 24 h
Persiste en BD (sobrevive reinicios).
"""
from __future__ import annotations
import time, logging
from core.db.connection import get_connection

logger = logging.getLogger("spj.auth.guard")

POLICY = [
    (5,  5 * 60),
    (10, 30 * 60),
    (15, 24 * 3600),
]


class LoginGuard:
    def __init__(self, conn=None):
        self.conn = conn or get_connection()
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario  TEXT NOT NULL,
                terminal TEXT DEFAULT 'local',
                exitoso  INTEGER DEFAULT 0,
                ip       TEXT,
                fecha    REAL DEFAULT (unixepoch())
            );
            CREATE TABLE IF NOT EXISTS login_blocks (
                usuario         TEXT NOT NULL,
                terminal        TEXT DEFAULT 'local',
                bloqueado_hasta REAL NOT NULL,
                intentos        INTEGER DEFAULT 0,
                PRIMARY KEY (usuario, terminal)
            );
            CREATE INDEX IF NOT EXISTS idx_la_usr
                ON login_attempts(usuario, fecha);
        """)
        try: self.conn.commit()
        except Exception: pass

    def check_blocked(self, usuario: str, terminal: str = "local") -> tuple:
        """Retorna (bloqueado: bool, segundos_restantes: int)."""
        row = self.conn.execute(
            "SELECT bloqueado_hasta FROM login_blocks WHERE usuario=? AND terminal=?",
            (usuario, terminal)
        ).fetchone()
        if not row:
            return False, 0
        if time.time() >= float(row[0]):
            self.conn.execute(
                "DELETE FROM login_blocks WHERE usuario=? AND terminal=?",
                (usuario, terminal))
            try: self.conn.commit()
            except Exception: pass
            return False, 0
        return True, int(float(row[0]) - time.time())

    def record_attempt(self, usuario: str, exitoso: bool,
                       terminal: str = "local", ip: str = None) -> None:
        self.conn.execute(
            "INSERT INTO login_attempts(usuario,terminal,exitoso,ip,fecha) "
            "VALUES(?,?,?,?,?)",
            (usuario, terminal, 1 if exitoso else 0, ip, time.time())
        )
        if exitoso:
            self.conn.execute(
                "DELETE FROM login_blocks WHERE usuario=? AND terminal=?",
                (usuario, terminal))
            logger.info("Login exitoso: %s @ %s", usuario, terminal)
        else:
            window = time.time() - 3600
            row = self.conn.execute(
                "SELECT COUNT(*) FROM login_attempts "
                "WHERE usuario=? AND terminal=? AND exitoso=0 AND fecha>=?",
                (usuario, terminal, window)
            ).fetchone()
            intentos = row[0] if row else 0
            bloqueo = 0
            for umbral, segs in reversed(POLICY):
                if intentos >= umbral:
                    bloqueo = segs
                    break
            if bloqueo:
                self.conn.execute(
                    "INSERT OR REPLACE INTO login_blocks"
                    "(usuario,terminal,bloqueado_hasta,intentos) VALUES(?,?,?,?)",
                    (usuario, terminal, time.time() + bloqueo, intentos))
                logger.warning("Bloqueado: %s — %d intentos — %d min",
                               usuario, intentos, bloqueo // 60)
        try: self.conn.commit()
        except Exception: pass

    def remaining_attempts(self, usuario: str, terminal: str = "local") -> int:
        window = time.time() - 3600
        row = self.conn.execute(
            "SELECT COUNT(*) FROM login_attempts "
            "WHERE usuario=? AND terminal=? AND exitoso=0 AND fecha>=?",
            (usuario, terminal, window)
        ).fetchone()
        intentos = row[0] if row else 0
        for umbral, _ in POLICY:
            if intentos < umbral:
                return umbral - intentos
        return 0

    def unlock_user(self, usuario: str, terminal: str = "local") -> None:
        self.conn.execute(
            "DELETE FROM login_blocks WHERE usuario=? AND terminal=?",
            (usuario, terminal))
        try: self.conn.commit()
        except Exception: pass
        logger.info("Desbloqueado manualmente: %s", usuario)
