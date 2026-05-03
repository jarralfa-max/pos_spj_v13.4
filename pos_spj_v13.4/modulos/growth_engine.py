# modulos/growth_engine.py — SPJ POS v13.2
"""
Growth Engine (Motor de Crecimiento y Fidelidad).
Diseño ROI-primero: no entrega recompensa hasta que el ingreso ya entró.

Mecánicas:
  A. Metas Comunitarias  — umbral de ventas → premio colectivo
  B. Misiones / Rachas   — N compras en ventana TTL → premio individual
  C. Moneda Expirable    — Estrellas (caducan 90/180 días de inactividad)

Protecciones:
  - Ledger inmutable (growth_ledger): sin columna puntos editable
  - Velocity limits (>2 compras/4h misma sucursal → bloquear acumulación)
  - Cap redención 50% del subtotal
  - OTP para canje mayor (configurable umbral)
"""
from __future__ import annotations
from core.services.auto_audit import audit_write
from modulos.spj_styles import spj_btn, apply_btn_styles
import logging
import hashlib
import random
import string
from datetime import datetime, timedelta
from typing import Optional, List, Dict

logger = logging.getLogger("spj.growth_engine")


# ── Constantes configurables ──────────────────────────────────────────────────
CAP_REDENCION_PCT   = 0.50   # max 50% del subtotal puede pagarse con estrellas
VELOCITY_MAX_COMPRAS = 2      # max compras acumulables en la misma sucursal
VELOCITY_VENTANA_H  = 4       # ventana de horas para velocity check
OTP_UMBRAL_DEFAULT  = 200     # estrellas a partir de las cuales exige OTP
OTP_EXPIRY_MIN      = 10      # minutos que dura el OTP
EXPIRY_INACTIVIDAD_DIAS = 90  # días sin compra → estrellas expiran


class GrowthEngine:
    """
    Motor principal. Se instancia por sesión/sucursal.
    Entrada: AppContainer (para db + whatsapp_service).
    """

    def __init__(self, db, sucursal_id: int = 1, whatsapp_service=None):
        self.db             = db
        self.sucursal_id    = sucursal_id
        self.whatsapp_svc   = whatsapp_service
        self._ensure_tables()

    # ══════════════════════════════════════════════════════════════════════
    # API PÚBLICA — llamada desde SalesService post-venta
    # ══════════════════════════════════════════════════════════════════════

    def procesar_venta(
        self,
        cliente_id: int,
        ticket_id:  int,
        cajero_id:  int,
        subtotal:   float,
        telefono:   str = "",
        nombre:     str = "",
    ) -> Dict:
        """
        Punto de entrada principal. Retorna dict con:
          estrellas_ganadas, saldo_actual, misiones_completadas,
          metas_avanzadas, mensaje_gamificacion
        """
        resultado = {
            "estrellas_ganadas":   0,
            "saldo_actual":        0,
            "misiones_completadas":[],
            "metas_avanzadas":     [],
            "mensaje_gamificacion": "",
            "bloqueado":           False,
        }

        # 1. Velocity check (antifraude)
        if self._velocity_check(cliente_id):
            logger.warning("GrowthEngine: velocity limit hit cliente=%s", cliente_id)
            resultado["bloqueado"] = True
            resultado["mensaje_gamificacion"] = "⏳ Acumulación temporalmente pausada."
            return resultado

        # 2. Calcular estrellas (1 estrella por peso MXN gastado, redondeado)
        estrellas = max(1, int(subtotal))
        self._creditar(cliente_id, estrellas, ticket_id, cajero_id,
                       operacion="VENTA", moneda="estrellas")

        # 3. Renovar fecha de expiración (inactividad reset)
        self._renovar_expiracion(cliente_id)

        # 4. Avanzar misiones activas del cliente
        completadas = self._avanzar_misiones(cliente_id, ticket_id)
        resultado["misiones_completadas"] = completadas

        # 5. Avanzar metas comunitarias de la sucursal
        metas_av = self._avanzar_metas(subtotal)
        resultado["metas_avanzadas"] = metas_av

        # 6. Saldo actual
        saldo = self.saldo_cliente(cliente_id)
        resultado["estrellas_ganadas"] = estrellas
        resultado["saldo_actual"]      = saldo

        # 7. Mensaje de gamificación
        resultado["mensaje_gamificacion"] = self._generar_mensaje(
            nombre, estrellas, saldo, completadas)

        return resultado

    def saldo_cliente(self, cliente_id: int) -> int:
        """Saldo de estrellas vigentes (suma del ledger, sin expirados/revertidos)."""
        try:
            row = self.db.execute("""
                SELECT COALESCE(SUM(monto),0)
                FROM growth_ledger
                WHERE cliente_id=? AND revertido=0 AND moneda='estrellas'
                  AND (expira_en IS NULL OR expira_en > datetime('now'))
            """, (cliente_id,)).fetchone()
            return max(0, int(row[0]))
        except Exception:
            return 0

    def canjear_estrellas(
        self,
        cliente_id:  int,
        cajero_id:   int,
        subtotal:    float,
        estrellas_a_canjear: int,
        ticket_id:   int = 0,
        otp_codigo:  str = "",
    ) -> Dict:
        """
        Canjea estrellas como descuento.
        Aplica cap del 50% del subtotal.
        Exige OTP si el monto supera el umbral.
        """
        saldo = self.saldo_cliente(cliente_id)
        if estrellas_a_canjear > saldo:
            return {"ok": False, "error": f"Saldo insuficiente ({saldo} estrellas)"}

        # Cap: máximo 50% del subtotal
        max_canje = int(subtotal * CAP_REDENCION_PCT)
        if estrellas_a_canjear > max_canje:
            estrellas_a_canjear = max_canje

        # OTP si supera el umbral
        umbral_otp = int(self._cfg("growth_otp_umbral", str(OTP_UMBRAL_DEFAULT)))
        if estrellas_a_canjear >= umbral_otp:
            if not otp_codigo:
                return {"ok": False, "requiere_otp": True,
                        "error": "Se requiere PIN enviado al WhatsApp del cliente"}
            if not self._validar_otp(cliente_id, otp_codigo, estrellas_a_canjear):
                return {"ok": False, "error": "PIN incorrecto o expirado"}

        # Debitar
        self._creditar(cliente_id, -estrellas_a_canjear, ticket_id, cajero_id,
                       operacion="CANJE", moneda="estrellas")
        return {
            "ok": True,
            "estrellas_canjeadas": estrellas_a_canjear,
            "descuento_aplicado":  estrellas_a_canjear,
            "saldo_restante":      self.saldo_cliente(cliente_id),
        }

    def generar_otp(self, cliente_id: int, monto_canje: int, telefono: str) -> str:
        """Genera PIN de 4 dígitos, lo guarda y lo envía por WA."""
        codigo = "".join(random.choices(string.digits, k=4))
        expira = datetime.now() + timedelta(minutes=OTP_EXPIRY_MIN)
        try:
            self.db.execute(
                "INSERT INTO growth_otp(cliente_id,codigo,monto_canje,expira_en)"
                " VALUES(?,?,?,?)",
                (cliente_id, codigo, monto_canje, expira.isoformat()))
            try: self.db.commit()
            except Exception: pass
        except Exception as e:
            logger.warning("generar_otp: %s", e)
        # Enviar por WA
        if self.whatsapp_svc and telefono:
            try:
                msg = (f"🔐 Tu PIN de canje SPJ: *{codigo}*\n"
                       f"Válido {OTP_EXPIRY_MIN} minutos. No lo compartas.")
                self.whatsapp_svc.send_message(
                    branch_id=self.sucursal_id, phone_number=telefono, message=msg)
            except Exception as e:
                logger.debug("WA otp: %s", e)
        return codigo

    # ══════════════════════════════════════════════════════════════════════
    # METAS COMUNITARIAS
    # ══════════════════════════════════════════════════════════════════════

    def get_metas_activas(self) -> List[Dict]:
        try:
            rows = self.db.execute("""
                SELECT id,nombre,descripcion,umbral,progreso,premio,
                       costo_premio,fecha_fin,completada
                FROM growth_metas
                WHERE activa=1 AND sucursal_id=?
                  AND (fecha_fin IS NULL OR fecha_fin >= date('now'))
                ORDER BY fecha_fin
            """, (self.sucursal_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def crear_meta(
        self,
        nombre: str,
        umbral: float,
        premio: str,
        costo_premio: float,
        descripcion: str = "",
        fecha_fin: str = "",
    ) -> int:
        cur = self.db.execute("""
            INSERT INTO growth_metas
            (sucursal_id,nombre,descripcion,umbral,premio,costo_premio,fecha_fin)
            VALUES(?,?,?,?,?,?,?)""",
            (self.sucursal_id, nombre, descripcion, umbral, premio,
             costo_premio, fecha_fin or None))
        try: self.db.commit()
        except Exception: pass
        return cur.lastrowid

    # ══════════════════════════════════════════════════════════════════════
    # MISIONES
    # ══════════════════════════════════════════════════════════════════════

    def get_misiones_activas(self) -> List[Dict]:
        try:
            rows = self.db.execute("""
                SELECT id,nombre,descripcion,condicion_tipo,condicion_n,
                       ventana_dias,premio_estrellas
                FROM growth_misiones WHERE activa=1
            """).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def crear_mision(
        self,
        nombre: str,
        condicion_tipo: str,
        condicion_n: int,
        ventana_dias: int,
        premio_estrellas: int,
        descripcion: str = "",
    ) -> int:
        cur = self.db.execute("""
            INSERT INTO growth_misiones
            (nombre,descripcion,condicion_tipo,condicion_n,ventana_dias,premio_estrellas)
            VALUES(?,?,?,?,?,?)""",
            (nombre, descripcion, condicion_tipo, condicion_n,
             ventana_dias, premio_estrellas))
        try: self.db.commit()
        except Exception: pass
        return cur.lastrowid

    def progreso_misiones_cliente(self, cliente_id: int) -> List[Dict]:
        try:
            rows = self.db.execute("""
                SELECT gm.nombre, gm.condicion_n, gmp.progreso,
                       gmp.completada, gmp.expira_en, gm.premio_estrellas
                FROM growth_misiones_progreso gmp
                JOIN growth_misiones gm ON gm.id=gmp.mision_id
                WHERE gmp.cliente_id=?
                  AND (gmp.expira_en IS NULL OR gmp.expira_en > datetime('now'))
                ORDER BY gmp.completada, gmp.expira_en
            """, (cliente_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ══════════════════════════════════════════════════════════════════════
    # EXPIRACIÓN DE ESTRELLAS
    # ══════════════════════════════════════════════════════════════════════

    def ejecutar_expiracion_nocturna(self) -> int:
        """
        Cron job: expira estrellas de clientes inactivos.
        Retorna número de clientes afectados.
        Debe llamarse desde SchedulerService una vez al día.
        """
        corte = (datetime.now() - timedelta(days=EXPIRY_INACTIVIDAD_DIAS)).isoformat()
        try:
            # Clientes sin compra en EXPIRY_INACTIVIDAD_DIAS días con saldo > 0
            rows = self.db.execute("""
                SELECT DISTINCT gl.cliente_id
                FROM growth_ledger gl
                WHERE gl.revertido=0 AND gl.moneda='estrellas'
                  AND gl.monto > 0
                  AND gl.cliente_id NOT IN (
                    SELECT DISTINCT cliente_id FROM growth_ledger
                    WHERE operacion='VENTA' AND created_at > ?
                  )
            """, (corte,)).fetchall()
            count = 0
            for (cid,) in rows:
                saldo = self.saldo_cliente(cid)
                if saldo > 0:
                    self._creditar(cid, -saldo, 0, 0,
                                   operacion="EXPIRACION",
                                   moneda="estrellas")
                    count += 1
            try: self.db.commit()
            except Exception: pass
            return count
        except Exception as e:
            logger.warning("expiracion: %s", e)
            return 0

    def pasivo_financiero(self) -> Dict:
        """
        Calcula el pasivo real del programa de fidelidad.
        L = Σ(E × V × p_red)
        E = estrellas vigentes, V = costo real promedio por estrella,
        p_red = probabilidad histórica de redención.
        """
        try:
            saldo_total = self.db.execute("""
                SELECT COALESCE(SUM(monto),0)
                FROM growth_ledger
                WHERE monto>0 AND revertido=0 AND moneda='estrellas'
                  AND (expira_en IS NULL OR expira_en > datetime('now'))
            """).fetchone()[0]

            canjeado_total = abs(self.db.execute("""
                SELECT COALESCE(SUM(monto),0)
                FROM growth_ledger WHERE operacion='CANJE'
            """).fetchone()[0])

            emitido_total = self.db.execute("""
                SELECT COALESCE(SUM(monto),0)
                FROM growth_ledger WHERE operacion='VENTA' AND monto>0
            """).fetchone()[0]

            p_red = (canjeado_total / emitido_total) if emitido_total > 0 else 0.15
            costo_real_por_estrella = float(
                self._cfg("growth_costo_estrella", "0.80"))
            pasivo = float(saldo_total) * costo_real_por_estrella * p_red

            return {
                "saldo_total_estrellas": int(saldo_total),
                "tasa_redencion_historica": round(p_red, 3),
                "costo_real_por_estrella": costo_real_por_estrella,
                "pasivo_estimado_mxn": round(pasivo, 2),
            }
        except Exception as e:
            return {"error": str(e)}

    # ══════════════════════════════════════════════════════════════════════
    # PRIVADOS
    # ══════════════════════════════════════════════════════════════════════

    def _creditar(self, cliente_id, monto, ticket_id, cajero_id,
                  operacion, moneda="estrellas"):
        dias_exp = int(self._cfg("growth_expiry_dias", str(EXPIRY_INACTIVIDAD_DIAS)))
        expira = (datetime.now() + timedelta(days=dias_exp)).isoformat() \
                 if monto > 0 else None
        self.db.execute("""
            INSERT INTO growth_ledger
            (cliente_id,sucursal_id,tipo,monto,moneda,ticket_id,cajero_id,operacion,expira_en)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (cliente_id, self.sucursal_id,
             "credito" if monto > 0 else "debito",
             monto, moneda, ticket_id, cajero_id, operacion, expira))
        try: self.db.commit()
        except Exception: pass

    def _velocity_check(self, cliente_id: int) -> bool:
        """True = bloqueado (demasiadas compras en poco tiempo)."""
        corte = (datetime.now() - timedelta(hours=VELOCITY_VENTANA_H)).isoformat()
        try:
            n = self.db.execute("""
                SELECT COUNT(*) FROM growth_ledger
                WHERE cliente_id=? AND sucursal_id=? AND operacion='VENTA'
                  AND created_at > ?
            """, (cliente_id, self.sucursal_id, corte)).fetchone()[0]
            return n >= VELOCITY_MAX_COMPRAS
        except Exception:
            return False

    def _renovar_expiracion(self, cliente_id: int):
        """Actualiza expira_en de todas las estrellas vigentes del cliente."""
        dias = int(self._cfg("growth_expiry_dias", str(EXPIRY_INACTIVIDAD_DIAS)))
        nueva = (datetime.now() + timedelta(days=dias)).isoformat()
        try:
            self.db.execute("""
                UPDATE growth_ledger
                SET expira_en=?
                WHERE cliente_id=? AND revertido=0 AND moneda='estrellas'
                  AND monto>0
            """, (nueva, cliente_id))
        except Exception: pass

    def _avanzar_misiones(self, cliente_id: int, ticket_id: int) -> List[str]:
        """Avanza progreso de todas las misiones activas. Retorna nombres completadas."""
        completadas = []
        try:
            misiones = self.db.execute(
                "SELECT id,nombre,condicion_n,ventana_dias,premio_estrellas "
                "FROM growth_misiones WHERE activa=1"
            ).fetchall()
            for m in misiones:
                mid, mnombre, mn, mvent, mpremio = m
                expira = (datetime.now() + timedelta(days=mvent)).isoformat()
                # Upsert progreso
                existing = self.db.execute(
                    "SELECT id,progreso,completada,expira_en FROM growth_misiones_progreso "
                    "WHERE cliente_id=? AND mision_id=?",
                    (cliente_id, mid)
                ).fetchone()
                if existing:
                    pid, prog, comp, exp_en = existing
                    if comp: continue
                    # Expirado?
                    if exp_en and exp_en < datetime.now().isoformat():
                        self.db.execute(
                            "UPDATE growth_misiones_progreso SET progreso=1,expira_en=? WHERE id=?",
                            (expira, pid))
                        continue
                    nuevo_prog = prog + 1
                    if nuevo_prog >= mn:
                        # Completada → otorgar premio
                        self.db.execute(
                            "UPDATE growth_misiones_progreso SET progreso=?,completada=1 WHERE id=?",
                            (nuevo_prog, pid))
                        self._creditar(cliente_id, mpremio, ticket_id, 0,
                                       operacion="MISION", moneda="estrellas")
                        completadas.append(mnombre)
                    else:
                        self.db.execute(
                            "UPDATE growth_misiones_progreso SET progreso=? WHERE id=?",
                            (nuevo_prog, pid))
                else:
                    self.db.execute("""
                        INSERT INTO growth_misiones_progreso
                        (cliente_id,mision_id,progreso,expira_en)
                        VALUES(?,?,1,?)""",
                        (cliente_id, mid, expira))
            try: self.db.commit()
            except Exception: pass
        except Exception as e:
            logger.debug("_avanzar_misiones: %s", e)
        return completadas

    def _avanzar_metas(self, subtotal: float) -> List[str]:
        """Suma subtotal al progreso de metas comunitarias activas."""
        completadas = []
        try:
            metas = self.db.execute("""
                SELECT id,nombre,umbral,progreso,premio
                FROM growth_metas
                WHERE activa=1 AND completada=0 AND sucursal_id=?
                  AND (fecha_fin IS NULL OR fecha_fin >= date('now'))
            """, (self.sucursal_id,)).fetchall()
            for mid, mnombre, umbral, prog, premio in metas:
                nuevo_prog = prog + subtotal
                if nuevo_prog >= umbral:
                    self.db.execute(
                        "UPDATE growth_metas SET progreso=?,completada=1 WHERE id=?",
                        (nuevo_prog, mid))
                    completadas.append(f"{mnombre}: {premio}")
                    logger.info("Meta comunitaria completada: %s", mnombre)
                else:
                    self.db.execute(
                        "UPDATE growth_metas SET progreso=? WHERE id=?",
                        (nuevo_prog, mid))
            try: self.db.commit()
            except Exception: pass
        except Exception as e:
            logger.debug("_avanzar_metas: %s", e)
        return completadas

    def _validar_otp(self, cliente_id: int, codigo: str, monto: int) -> bool:
        try:
            row = self.db.execute("""
                SELECT id FROM growth_otp
                WHERE cliente_id=? AND codigo=? AND usado=0
                  AND expira_en > datetime('now')
                  AND monto_canje >= ?
                LIMIT 1
            """, (cliente_id, codigo, monto)).fetchone()
            if row:
                self.db.execute("UPDATE growth_otp SET usado=1 WHERE id=?", (row[0],))
                try: self.db.commit()
                except Exception: pass
                return True
            return False
        except Exception:
            return False

    def _generar_mensaje(self, nombre, ganadas, saldo, misiones) -> str:
        n = nombre.split()[0] if nombre else "cliente"
        msg = f"⭐ *+{ganadas} estrellas*, {n}! Saldo: *{saldo} estrellas*."
        if misiones:
            msg += f"\n🏆 ¡Misión completada: {misiones[0]}!"
        umbrales = {"1000": "🥈 Plata", "5000": "🥇 Oro", "15000": "💎 Diamante"}
        for umbral, nivel in umbrales.items():
            if saldo < int(umbral):
                faltante = int(umbral) - saldo
                msg += f"\n📈 Te faltan *{faltante} estrellas* para {nivel}."
                break
        return msg

    def _cfg(self, clave: str, default: str = "") -> str:
        try:
            r = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
            ).fetchone()
            return r[0] if r else default
        except Exception:
            return default

    def _ensure_tables(self):
        """Crea tablas si no existen (no depender solo de migración)."""
        try:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS growth_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER NOT NULL,
                    sucursal_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL,
                    monto REAL NOT NULL,
                    moneda TEXT DEFAULT 'estrellas',
                    ticket_id INTEGER,
                    cajero_id INTEGER,
                    operacion TEXT,
                    expira_en DATETIME,
                    revertido INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS growth_metas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sucursal_id INTEGER DEFAULT 1,
                    nombre TEXT NOT NULL,
                    descripcion TEXT,
                    tipo TEXT DEFAULT 'comunitaria',
                    umbral REAL NOT NULL,
                    progreso REAL DEFAULT 0,
                    premio TEXT,
                    costo_premio REAL DEFAULT 0,
                    fecha_inicio DATE,
                    fecha_fin DATE,
                    activa INTEGER DEFAULT 1,
                    completada INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS growth_misiones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    descripcion TEXT,
                    condicion_tipo TEXT DEFAULT 'compras_consecutivas',
                    condicion_n INTEGER DEFAULT 3,
                    ventana_dias INTEGER DEFAULT 7,
                    premio_estrellas INTEGER DEFAULT 100,
                    activa INTEGER DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS growth_misiones_progreso (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER NOT NULL,
                    mision_id INTEGER NOT NULL,
                    progreso INTEGER DEFAULT 0,
                    iniciada_en DATETIME DEFAULT (datetime('now')),
                    expira_en DATETIME,
                    completada INTEGER DEFAULT 0,
                    UNIQUE(cliente_id, mision_id)
                );
                CREATE TABLE IF NOT EXISTS growth_otp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER NOT NULL,
                    codigo TEXT NOT NULL,
                    monto_canje REAL NOT NULL,
                    usado INTEGER DEFAULT 0,
                    expira_en DATETIME NOT NULL,
                    created_at DATETIME DEFAULT (datetime('now'))
                );
            """)
            try: self.db.commit()
            except Exception: pass
        except Exception: pass
