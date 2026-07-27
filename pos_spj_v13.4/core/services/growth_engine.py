# core/services/growth_engine.py — SPJ POS v13.2 (movido desde modulos/ — D7/F)
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
import logging
from backend.shared.ids import new_uuid
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
    Entradas: conexión db, sucursal_id y (opcional) whatsapp_service — NO el
    contenedor de DI (es un servicio de dominio, no recibe el container).
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
        sale_id:    str,
        cajero_id:  int,
        subtotal:   float,
        telefono:   str = "",
        nombre:     str = "",
    ) -> Dict:
        """DEPRECADO (FASE 4 / REGLA CERO).

        La acreditación de puntos por venta es responsabilidad de la ruta
        canónica ``LoyaltyService.acreditar_venta()``, que persiste la
        referencia de venta como UUID en ``loyalty_ledger.referencia``. Esta
        ruta duplicada escribía ``growth_ledger.ticket_id`` y queda retirada
        para que ninguna referencia de venta nueva entre a ``growth_ledger``.
        """
        raise RuntimeError(
            "GrowthEngine.procesar_venta está deprecado: usa "
            "LoyaltyService.acreditar_venta() (loyalty_ledger.referencia es la "
            f"referencia de venta UUID canónica). sale_id={sale_id!r}"
        )

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
        sale_id:     str = "",
        otp_codigo:  str = "",
    ) -> Dict:
        """DEPRECADO (FASE 4 / REGLA CERO).

        El canje canónico lo realiza ``LoyaltyService.canjear()`` con
        ``referencia=str(venta_id)`` (UUID) en ``loyalty_ledger``. Esta ruta
        duplicada escribía ``growth_ledger.ticket_id`` y queda retirada.
        """
        raise RuntimeError(
            "GrowthEngine.canjear_estrellas está deprecado: usa "
            "LoyaltyService.canjear() (loyalty_ledger es el ledger canónico). "
            f"sale_id={sale_id!r}"
        )

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
        meta_id = new_uuid()  # identidad UUIDv7 (sin rowid implícito)
        self.db.execute("""
            INSERT INTO growth_metas
            (id,sucursal_id,nombre,descripcion,umbral,premio,costo_premio,fecha_fin)
            VALUES(?,?,?,?,?,?,?,?)""",
            (meta_id, self.sucursal_id, nombre, descripcion, umbral, premio,
             costo_premio, fecha_fin or None))
        try: self.db.commit()
        except Exception: pass
        return meta_id

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
        mision_id = new_uuid()  # identidad UUIDv7 (sin rowid implícito)
        self.db.execute("""
            INSERT INTO growth_misiones
            (id,nombre,descripcion,condicion_tipo,condicion_n,ventana_dias,premio_estrellas)
            VALUES(?,?,?,?,?,?,?)""",
            (mision_id, nombre, descripcion, condicion_tipo, condicion_n,
             ventana_dias, premio_estrellas))
        try: self.db.commit()
        except Exception: pass
        return mision_id

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
                    # Entrada interna: sin referencia de venta (sale_id=None).
                    self._creditar(cid, -saldo, None, 0,
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


    # ── UI helpers (FASE 6: UI sin SQL directo) ─────────────────────────
    def desactivar_meta(self, meta_id: int) -> None:
        self.db.execute("UPDATE growth_metas SET activa=0 WHERE id=?", (str(meta_id),))
        try: self.db.commit()
        except Exception: pass

    def desactivar_mision(self, mision_id: int) -> None:
        self.db.execute("UPDATE growth_misiones SET activa=0 WHERE id=?", (str(mision_id),))
        try: self.db.commit()
        except Exception: pass

    def get_growth_config(self) -> dict:
        """Compat: devuelve shape growth_* pero lee primero loyalty_* canónicas."""
        def _read(loyalty_key: str, growth_key: str, default: str):
            v = self._cfg(loyalty_key, "")
            return v if str(v or "").strip() else self._cfg(growth_key, default)
        return {
            "growth_expiry_dias": _read("loyalty_expiry_dias", "growth_expiry_dias", "90"),
            "growth_otp_umbral": _read("loyalty_otp_umbral", "growth_otp_umbral", "200"),
            "growth_costo_estrella": _read("loyalty_valor_estrella", "growth_costo_estrella", "0.80"),
            "growth_cap_pct": _read("loyalty_max_pct_canje", "growth_cap_pct", "0.50"),
        }

    def save_growth_config(self, cfg: dict) -> None:
        """Compat temporal: persiste growth_* y loyalty_* canónicas."""
        mapping = {
            "growth_expiry_dias": "loyalty_expiry_dias",
            "growth_otp_umbral": "loyalty_otp_umbral",
            "growth_costo_estrella": "loyalty_valor_estrella",
            "growth_cap_pct": "loyalty_max_pct_canje",
        }
        for k, v in (cfg or {}).items():
            self.db.execute(
                "INSERT INTO configuraciones(clave,valor) VALUES(?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (k, str(v)),
            )
            lk = mapping.get(k)
            if lk:
                self.db.execute(
                    "INSERT INTO configuraciones(clave,valor) VALUES(?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                    (lk, str(v)),
                )
        try: self.db.commit()
        except Exception: pass

    def buscar_cliente_basico(self, buscar: str):
        try:
            return self.db.execute(
                "SELECT id, nombre, COALESCE(apellido,'') as apellido FROM clientes WHERE id=?",
                (int(buscar),),
            ).fetchone()
        except Exception:
            return self.db.execute(
                "SELECT id, nombre, COALESCE(apellido,'') as apellido FROM clientes WHERE nombre LIKE ? LIMIT 1",
                (f"%{buscar}%",),
            ).fetchone()
    # ══════════════════════════════════════════════════════════════════════
    # PRIVADOS
    # ══════════════════════════════════════════════════════════════════════

    def _creditar(self, cliente_id, monto, sale_id, cajero_id,
                  operacion, moneda="estrellas"):
        # REGLA CERO: una referencia de venta debe ser UUID (str). Las entradas
        # internas del motor (p.ej. EXPIRACION) no llevan referencia de venta y
        # pasan sale_id=None. Nunca se acepta un id entero como referencia.
        if sale_id is not None and not isinstance(sale_id, str):
            raise ValueError(
                f"sale_id debe ser str (UUID) o None, no {type(sale_id).__name__}"
            )
        dias_exp = int(self._cfg("growth_expiry_dias", str(EXPIRY_INACTIVIDAD_DIAS)))
        expira = (datetime.now() + timedelta(days=dias_exp)).isoformat() \
                 if monto > 0 else None
        self.db.execute("""
            INSERT INTO growth_ledger
            (cliente_id,sucursal_id,tipo,monto,moneda,ticket_id,cajero_id,operacion,expira_en)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (cliente_id, self.sucursal_id,
             "credito" if monto > 0 else "debito",
             monto, moneda, sale_id, cajero_id, operacion, expira))
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

    def _avanzar_misiones(self, cliente_id: int, sale_id: str) -> List[str]:
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
                        self._creditar(cliente_id, mpremio, sale_id, 0,
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
            pass  # Plan B born-clean: schema canónico en migrations/ (DDL removido)
            try: self.db.commit()
            except Exception: pass
        except Exception: pass
