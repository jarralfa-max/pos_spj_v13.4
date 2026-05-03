# core/services/happy_hour_service.py — SPJ POS v12
"""
Motor de Happy Hour y promociones programadas.

- Lee reglas de happy_hour_rules
- Aplica descuentos según hora/día activos
- Envía mensajes WhatsApp a clientes al activarse una promo
- Compatible con PromotionEngine existente
"""
from __future__ import annotations
import logging
from datetime import datetime, time as dtime
from typing import Optional

logger = logging.getLogger("spj.happy_hour")


class HappyHourService:
    """Gestiona promociones por horario y su difusión por WhatsApp."""

    def __init__(self, db_conn, whatsapp_service=None, sucursal_id: int = 1):
        self.db = db_conn
        self.wa  = whatsapp_service
        self.sucursal_id = sucursal_id
        self._activas_cache: list = []
        self._cache_minuto: int = -1

    # ── Consulta de reglas activas ───────────────────────────────────────────

    def get_reglas_activas_ahora(self) -> list:
        """Retorna reglas cuyo rango horario incluye el momento actual."""
        ahora = datetime.now()
        minuto_actual = ahora.hour * 60 + ahora.minute

        if minuto_actual == self._cache_minuto:
            return self._activas_cache

        dia_hoy = str(ahora.weekday())   # 0=lun … 6=dom
        try:
            rows = self.db.execute("""
                SELECT id, nombre, hora_inicio, hora_fin,
                       tipo_descuento, valor, aplica_a, aplica_valor,
                       mensaje_wa
                FROM happy_hour_rules
                WHERE activo=1 AND sucursal_id=?
            """, (self.sucursal_id,)).fetchall()
        except Exception:
            return []

        activas = []
        for r in rows:
            # Filtrar por día de semana
            dias = str(r[4] if len(r) > 4 else "0,1,2,3,4,5,6")
            try:
                dias_row = self.db.execute(
                    "SELECT dias_semana FROM happy_hour_rules WHERE id=?", (r[0],)
                ).fetchone()
                dias = dias_row[0] if dias_row else "0,1,2,3,4,5,6"
            except Exception:
                dias = "0,1,2,3,4,5,6"

            if dia_hoy not in dias.split(","):
                continue

            # Filtrar por horario
            try:
                h_ini = r[2]; h_fin = r[3]
                ini_min = int(h_ini.split(":")[0])*60 + int(h_ini.split(":")[1])
                fin_min = int(h_fin.split(":")[0])*60 + int(h_fin.split(":")[1])
                if ini_min <= minuto_actual <= fin_min:
                    activas.append({
                        "id":             r[0],
                        "nombre":         r[1],
                        "hora_inicio":    r[2],
                        "hora_fin":       r[3],
                        "tipo_descuento": r[4],
                        "valor":          float(r[5]),
                        "aplica_a":       r[6],
                        "aplica_valor":   r[7],
                        "mensaje_wa":     r[8],
                    })
            except Exception:
                continue

        self._activas_cache = activas
        self._cache_minuto  = minuto_actual
        return activas

    def aplicar_a_precio(self, precio: float, producto_id: int = None,
                         categoria: str = None) -> tuple:
        """
        Aplica el descuento happy hour al precio dado.
        Retorna (precio_final, descuento_aplicado, nombre_promo).
        """
        reglas = self.get_reglas_activas_ahora()
        for r in reglas:
            aplica = False
            if r["aplica_a"] == "todos":
                aplica = True
            elif r["aplica_a"] == "categoria" and categoria:
                aplica = r["aplica_valor"] == categoria
            elif r["aplica_a"] == "producto_id" and producto_id:
                aplica = str(r["aplica_valor"]) == str(producto_id)

            if not aplica:
                continue

            if r["tipo_descuento"] == "porcentaje":
                descuento = precio * r["valor"] / 100
            else:
                descuento = min(r["valor"], precio)

            precio_final = max(0, round(precio - descuento, 4))
            return precio_final, round(descuento, 4), r["nombre"]

        return precio, 0.0, ""

    # ── Difusión WhatsApp ────────────────────────────────────────────────────

    def enviar_promo_whatsapp(self, regla_id: int,
                               limite: int = 50) -> int:
        """
        Envía el mensaje de la promo por WhatsApp a clientes activos
        con teléfono registrado. Retorna número de mensajes encolados.
        """
        if not self.wa:
            logger.warning("WhatsApp no configurado — promo no enviada")
            return 0

        try:
            regla = self.db.execute(
                "SELECT nombre, mensaje_wa, hora_inicio, hora_fin, valor "
                "FROM happy_hour_rules WHERE id=?", (regla_id,)
            ).fetchone()
            if not regla or not regla[1]:
                return 0

            nombre_promo = regla[0]
            mensaje_tpl  = regla[1]
            hora_ini     = regla[2]
            hora_fin     = regla[3]
            valor        = float(regla[4])

            clientes = self.db.execute("""
                SELECT nombre, telefono FROM clientes
                WHERE activo=1 AND telefono IS NOT NULL AND telefono != ''
                LIMIT ?
            """, (limite,)).fetchall()

            enviados = 0
            for cli in clientes:
                nombre_cli = cli[0] or "cliente"
                telefono   = cli[1]
                # Personalizar mensaje
                msg = (mensaje_tpl
                       .replace("{nombre}", nombre_cli)
                       .replace("{promo}", nombre_promo)
                       .replace("{valor}", f"{valor:.0f}%")
                       .replace("{hora_ini}", hora_ini)
                       .replace("{hora_fin}", hora_fin))
                try:
                    self.wa.send_message(
                        phone_number=telefono,
                        message=msg
                    )
                    enviados += 1
                except Exception as _e:
                    logger.debug("enviar_promo_wa %s: %s", telefono, _e)

            logger.info("Promo '%s' enviada a %d clientes", nombre_promo, enviados)
            return enviados
        except Exception as e:
            logger.error("enviar_promo_whatsapp: %s", e)
            return 0

    # ── Admin CRUD ────────────────────────────────────────────────────────────

    def crear_regla(self, nombre: str, hora_inicio: str, hora_fin: str,
                    dias: str, tipo: str, valor: float,
                    aplica_a: str = "todos", aplica_valor: str = None,
                    mensaje_wa: str = None) -> int:
        rid = self.db.execute("""
            INSERT INTO happy_hour_rules
                (nombre, hora_inicio, hora_fin, dias_semana,
                 tipo_descuento, valor, aplica_a, aplica_valor,
                 mensaje_wa, sucursal_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (nombre, hora_inicio, hora_fin, dias, tipo, valor,
              aplica_a, aplica_valor, mensaje_wa, self.sucursal_id)).lastrowid
        try: self.db.commit()
        except Exception: pass
        self._cache_minuto = -1   # invalida caché
        return rid

    def toggle_regla(self, regla_id: int, activo: bool) -> None:
        self.db.execute(
            "UPDATE happy_hour_rules SET activo=? WHERE id=?",
            (int(activo), regla_id))
        try: self.db.commit()
        except Exception: pass
        self._cache_minuto = -1

    def get_reglas(self) -> list:
        try:
            rows = self.db.execute(
                "SELECT id,nombre,hora_inicio,hora_fin,dias_semana,"
                "tipo_descuento,valor,aplica_a,aplica_valor,mensaje_wa,activo "
                "FROM happy_hour_rules WHERE sucursal_id=? ORDER BY hora_inicio",
                (self.sucursal_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
