
# core/services/sync_service.py
import logging
import json
import threading
import time
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class SyncService:
    """
    Motor de Sincronización Offline-First (Patrón Outbox).
    Garantiza que los datos viajen a la Matriz sin bloquear la UI local.
    """
    def __init__(self, db_conn, api_url: str = "", api_token: str = ""):
        self.db        = db_conn
        # v13.2: read from configuraciones if not passed
        self.api_url   = api_url   or self._cfg("sync_url",     "")
        self.api_token = api_token or self._cfg("sync_api_key", "")
        self.sucursal_id = 1
        # Hilo de fondo (Demonio) que no bloquea la interfaz de PyQt5
        self.is_running = False
        self._thread = None

    def _cfg(self, key: str, default: str = "") -> str:
        try:
            row = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (key,)
            ).fetchone()
            return row[0] if row and row[0] else default
        except Exception:
            return default
    
    def _cursor(self):
        """Obtiene cursor compatible para sqlite3.Connection o wrappers custom."""
        if hasattr(self.db, "cursor"):
            return self.db.cursor()
        if hasattr(self.db, "conn") and hasattr(self.db.conn, "cursor"):
            return self.db.conn.cursor()
        raise AttributeError("DB object has no cursor()")

    def iniciar_demonio(self):
        """Inicia el trabajador en segundo plano que vigilará la bandeja de salida."""
        if not self.is_running:
            self.is_running = True
            self._thread = threading.Thread(target=self._ciclo_sincronizacion, daemon=True)
            self._thread.start()
            logger.info("🚀 Motor de Sincronización Offline-First INICIADO.")

    def detener_demonio(self):
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    # =========================================================
    # 1. GENERACIÓN DE EVENTOS (Llamado por los otros Servicios)
    # =========================================================
    def registrar_evento(self, tabla: str, operacion: str, registro_id: int,
                          payload: dict, cursor=None, sucursal_id: int = None,
                          **kwargs):
        """
        Encola un evento localmente para ser enviado a la matriz.
        Acepta cursor= y sucursal_id= opcionales para compatibilidad con
        llamadas desde dentro de SAVEPOINTs (execute_sale, etc.).
        NO hace commit/rollback — el caller es dueño de la transacción.
        """
        _sucursal = sucursal_id or getattr(self, 'sucursal_id', 1)
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, default=str)
            _cur = cursor if cursor is not None else self._cursor()
            _cur.execute("""
                INSERT INTO sync_outbox
                    (tabla, operacion, registro_id, payload, sucursal_id,
                     enviado, intentos, fecha)
                VALUES (?, ?, ?, ?, ?, 0, 0, datetime('now'))
            """, (tabla, operacion, registro_id, payload_json, _sucursal))

            # Increment Lamport clock (best-effort, never blocks the sale)
            try:
                self._increment_lamport(_cur)
            except Exception:
                pass

            logger.debug("Evento %s en %s encolado.", operacion, tabla)
        except Exception as e:
            # Never re-raise: sync failure must never abort a sale
            logger.error("Fallo al encolar evento en Outbox: %s", e)

    # =========================================================
    # 2. TRABAJADOR SILENCIOSO (El Hilo de Fondo)
    # =========================================================
    def _ciclo_sincronizacion(self):
        """Ciclo infinito que busca internet y envía datos cada 60 segundos."""
        while self.is_running:
            try:
                self._procesar_bandeja_salida()
            except Exception as e:
                logger.error("Error en ciclo de sincronización: %s", e)
                
            # Espera 60 segundos antes de volver a revisar (ahorra CPU)
            time.sleep(60)

    def _procesar_bandeja_salida(self):
        """Toma los registros no enviados y los manda a la API de la Matriz."""
        cursor = self._cursor()
        
        # Tomamos hasta 50 eventos pendientes por lote
        pendientes = cursor.execute("""
            SELECT id, uuid, tabla, operacion, registro_id, payload 
            FROM sync_outbox 
            WHERE enviado = 0 AND intentos < 10
            ORDER BY id ASC LIMIT 50
        """).fetchall()

        if not pendientes:
            return # Nada que enviar

        logger.info(f"Sincronizando {len(pendientes)} eventos con la Matriz...")

        # Preparamos el lote (Batch)
        lote_eventos = []
        ids_pendientes = []
        for row in pendientes:
            ids_pendientes.append(row['id'])
            lote_eventos.append({
                "uuid": row['uuid'],
                "tabla": row['tabla'],
                "operacion": row['operacion'],
                "registro_id": row['registro_id'],
                "payload": json.loads(row['payload']),
                "sucursal_id": self.sucursal_id
            })

        # Intentamos enviar el lote por HTTP
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        
        try:
            # NOTA: Esta URL es ficticia, aquí pondrías la URL de tu servidor real
            respuesta = requests.post(f"{self.api_url}/sync/batch", json={"eventos": lote_eventos}, headers=headers, timeout=10)
            
            if respuesta.status_code == 200:
                # ¡Éxito! La matriz recibió los datos. Marcamos como enviados.
                placeholders = ','.join('?' * len(ids_pendientes))
                cursor.execute(f"UPDATE sync_outbox SET enviado = 1 WHERE id IN ({placeholders})", ids_pendientes)
                self.db.commit()
                logger.info(f"✅ {len(pendientes)} eventos sincronizados correctamente.")
            else:
                raise Exception(f"El servidor respondió con código {respuesta.status_code}")

        except requests.exceptions.RequestException:
            # No hay internet o servidor caído. Incrementamos contador de intentos.
            logger.warning("📶 Sin conexión a la matriz. Los datos se guardan para el próximo intento.")
            placeholders = ','.join('?' * len(ids_pendientes))
            cursor.execute(f"UPDATE sync_outbox SET intentos = intentos + 1 WHERE id IN ({placeholders})", ids_pendientes)
            self.db.commit()
        except Exception as e:
            logger.error("Fallo enviando lote a la matriz: %s", e)
    def _get_lamport(self) -> int:
        """Get current Lamport clock (v13.2: uses shared LAMPORT_KEY='lamport')."""
        try:
            from sync.sync_engine import LAMPORT_KEY
            row = self.db.execute(
                "SELECT value FROM sync_state WHERE key=?", (LAMPORT_KEY,)
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _increment_lamport(self, cursor=None) -> int:
        """Increment Lamport clock (v13.2: uses shared LAMPORT_KEY='lamport')."""
        try:
            from sync.sync_engine import LAMPORT_KEY
            current = self._get_lamport()
            new_val = current + 1
            db = cursor or self.db
            db.execute(
                "INSERT OR REPLACE INTO sync_state(key, value) VALUES(?,?)",
                (LAMPORT_KEY, str(new_val))
            )
            return new_val
        except Exception:
            return 0
