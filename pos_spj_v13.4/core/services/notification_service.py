
# core/services/notification_service.py — SPJ POS v12
# ── Servicio Central de Notificaciones ────────────────────────────────────────
#
# RESPONSABILIDADES:
#   • Enrutar notificaciones al canal correcto según destinatario y tipo
#   • Clientes: ticket digital + gamificación + branding psicológico
#   • Empleados: rol determina qué alertas reciben (cajero ≠ gerente ≠ inventario)
#   • Universal a empleados: nómina, vacaciones aprobadas, recordatorio descanso
#   • Canal WhatsApp: vía WhatsAppService (queue offline-first)
#   • Canal POS inbox: tabla notification_inbox (leída al iniciar sesión)
#   • Anomalías en tiempo real: venta cancelada, diferencia en caja → gerente/admin
#
# DISEÑO:
#   • Sin acoplamiento directo — recibe WhatsAppService por inyección
#   • Nunca bloquea el hilo principal — todo asíncrono via queue
#   • Falla silenciosamente por canal — un canal roto no cancela el otro
#
from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime
from typing import Dict, List, Optional

logger = logging.getLogger("spj.notifications")

# ── Categorías de notificación ─────────────────────────────────────────────────
CAT_CLIENTE   = "cliente"
CAT_EMPLEADO  = "empleado"
CAT_GERENTE   = "gerente"
CAT_ADMIN     = "admin"
CAT_UNIVERSAL = "universal"   # todos los empleados sin excepción

# ── Tipos de notificación ──────────────────────────────────────────────────────
TIPO_TICKET          = "ticket_digital"
TIPO_PUNTOS          = "puntos_ganados"
TIPO_NIVEL           = "nivel_subido"
TIPO_BRANDING        = "branding_psicologico"
TIPO_NOMINA          = "nomina_pagada"
TIPO_VACACIONES      = "vacaciones_recordatorio"
TIPO_DESCANSO        = "descanso_recordatorio"
TIPO_STOCK_BAJO      = "stock_bajo"
TIPO_CORTE_Z         = "corte_z"
TIPO_VENTA_CANCELADA = "venta_cancelada"
TIPO_DIFF_CAJA       = "diferencia_caja"
TIPO_DIFF_RECEPCION  = "diferencia_recepcion"
TIPO_CADUCIDAD       = "caducidad_proxima"
TIPO_BACKUP_FALLO    = "backup_fallido"
TIPO_PEDIDO_WA       = "pedido_whatsapp_nuevo"
TIPO_PEDIDO_ASIGNADO = "pedido_asignado_repartidor"

# ── Matriz: qué roles reciben cada tipo ───────────────────────────────────────
# Roles en security/rbac.py: admin, gerente, cajero, inventario, delivery, marketing, finanzas
_ROL_MATRIX: Dict[str, List[str]] = {
    TIPO_STOCK_BAJO:      ["admin", "gerente", "inventario"],
    TIPO_CORTE_Z:         ["admin", "gerente", "cajero"],
    TIPO_VENTA_CANCELADA: ["admin", "gerente"],
    TIPO_DIFF_CAJA:       ["admin", "gerente"],
    TIPO_DIFF_RECEPCION:  ["admin", "gerente", "inventario"],
    TIPO_CADUCIDAD:       ["admin", "gerente", "inventario"],
    TIPO_BACKUP_FALLO:    ["admin"],
    TIPO_PEDIDO_WA:       ["admin", "gerente", "cajero"],
    TIPO_PEDIDO_ASIGNADO: ["delivery"],
}

# Tipos universales a TODOS los empleados (no filtran por rol)
_UNIVERSAL_TYPES = {TIPO_NOMINA, TIPO_VACACIONES, TIPO_DESCANSO}


class NotificationService:
    """
    Servicio central de notificaciones.
    Orquesta WhatsApp + inbox POS según tipo de destinatario y rol.
    """

    def __init__(self, db, whatsapp_service=None, sucursal_id: int = 1):
        self.db               = db
        self.whatsapp_service = whatsapp_service
        self.sucursal_id      = sucursal_id

    # ══════════════════════════════════════════════════════════════════════════
    # API PÚBLICA — CLIENTES
    # ══════════════════════════════════════════════════════════════════════════

    def notificar_venta_cliente(
        self,
        telefono:    str,
        nombre:      str,
        folio:       str,
        total:       float,
        items:       List[Dict],
        puntos_ganados: int     = 0,
        puntos_total:   int     = 0,
        nivel_actual:   str     = "bronce",
        nivel_anterior: str     = "",
        branch_id:      int     = 1,
    ) -> None:
        """
        Notificación post-venta al cliente:
          1. Ticket digital con desglose
          2. Gamificación (puntos, nivel)
          3. Branding psicológico (comunidad)
        Bloques separados para legibilidad en WhatsApp.
        """
        if not telefono:
            return

        mensajes = []

        # ── Bloque 1: Ticket digital ──────────────────────────────────────────
        lineas = [f"🧾 *Ticket #{folio}* — {datetime.now().strftime('%d/%m/%Y %H:%M')}"]
        lineas.append("─" * 28)
        for item in items[:15]:
            nombre_p  = item.get("nombre", item.get("name", "Producto"))
            qty       = float(item.get("qty", item.get("cantidad", 1)))
            precio    = float(item.get("unit_price", item.get("precio_unitario", 0)))
            subtotal  = qty * precio
            lineas.append(f"  {nombre_p[:22]:<22} ${subtotal:>7.2f}")
        if len(items) > 15:
            lineas.append(f"  … y {len(items)-15} productos más")
        lineas.append("─" * 28)
        lineas.append(f"  *Total pagado:  ${total:>10.2f}*")
        mensajes.append("\n".join(lineas))

        # ── Bloque 2: Gamificación ────────────────────────────────────────────
        if puntos_ganados > 0:
            gaming_lines = [f"⭐ *{nombre.split()[0]}, ganaste {puntos_ganados} puntos*"]
            gaming_lines.append(f"Tu saldo: *{puntos_total} puntos* acumulados")

            if nivel_anterior and nivel_anterior != nivel_actual:
                gaming_lines.append(
                    f"🏆 ¡Subiste a nivel *{nivel_actual.upper()}*! "
                    f"Nuevos beneficios activos."
                )
            else:
                # Progreso hacia el siguiente nivel
                umbrales = {"bronce": 1000, "plata": 5000, "oro": 15000, "diamante": 99999}
                siguiente_umbral = umbrales.get(nivel_actual.lower(), 1000)
                faltante = max(0, siguiente_umbral - puntos_total)
                if faltante > 0:
                    gaming_lines.append(
                        f"📈 Te faltan *{faltante} puntos* para el siguiente nivel"
                    )
                else:
                    gaming_lines.append("🎯 ¡Estás en el nivel máximo!")

            mensajes.append("\n".join(gaming_lines))

        # ── Bloque 3: Branding psicológico ────────────────────────────────────
        branding = self._generar_branding(nombre, total)
        mensajes.append(branding)

        # Enviar los 3 bloques como un solo mensaje unificado
        mensaje_final = "\n\n".join(mensajes)
        self._enviar_whatsapp(branch_id, telefono, mensaje_final)

    # ══════════════════════════════════════════════════════════════════════════
    # API PÚBLICA — EMPLEADOS (UNIVERSAL)
    # ══════════════════════════════════════════════════════════════════════════

    def notificar_nomina(
        self,
        empleado_id: int,
        nombre:      str,
        monto_neto:  float,
        periodo:     str,
        metodo_pago: str,
        sucursal_id: int = 1,
    ) -> None:
        """Recibo de nómina — va a TODOS los empleados sin filtro de rol."""
        telefono = self._get_telefono_empleado(empleado_id)
        mensaje = (
            f"💰 *Pago de nómina procesado*\n"
            f"Hola {nombre}, tu pago del periodo *{periodo}* "
            f"por *${monto_neto:.2f}* vía {metodo_pago} ha sido procesado.\n"
            f"Cualquier duda, consulta con RRHH. ¡Gracias por tu trabajo! 🙌"
        )
        if telefono:
            self._enviar_whatsapp(sucursal_id, telefono, mensaje)
        self._inbox_empleado(
            empleado_id, TIPO_NOMINA,
            f"Nómina {periodo} — ${monto_neto:.2f} via {metodo_pago}",
            datos={"monto": monto_neto, "periodo": periodo, "metodo": metodo_pago}
        )

    def notificar_vacaciones_recordatorio(
        self,
        empleado_id: int,
        nombre:      str,
        fecha_inicio: str,
        fecha_fin:    str,
        dias:         int,
        sucursal_id:  int = 1,
    ) -> None:
        """Recordatorio de vacaciones aprobadas — universal a todos los empleados."""
        telefono = self._get_telefono_empleado(empleado_id)
        mensaje = (
            f"🌴 *Recordatorio de vacaciones*\n"
            f"Hola {nombre}, tus vacaciones aprobadas son:\n"
            f"📅 Del *{fecha_inicio}* al *{fecha_fin}* ({dias} días)\n"
            f"¡Que las disfrutes! 😎"
        )
        if telefono:
            self._enviar_whatsapp(sucursal_id, telefono, mensaje)
        self._inbox_empleado(
            empleado_id, TIPO_VACACIONES,
            f"Vacaciones {fecha_inicio} → {fecha_fin} ({dias} días)",
            datos={"inicio": fecha_inicio, "fin": fecha_fin, "dias": dias}
        )

    def notificar_descanso_recordatorio(
        self,
        empleado_id: int,
        nombre:      str,
        fecha:       str,
        motivo:      str = "Día de descanso",
        sucursal_id: int = 1,
    ) -> None:
        """Recordatorio de día de descanso — universal."""
        telefono = self._get_telefono_empleado(empleado_id)
        mensaje = (
            f"😴 *{motivo}*\n"
            f"Hola {nombre}, recuerda que el *{fecha}* es tu día de descanso.\n"
            f"¡Aprovéchalo bien! 🙂"
        )
        if telefono:
            self._enviar_whatsapp(sucursal_id, telefono, mensaje)
        self._inbox_empleado(
            empleado_id, TIPO_DESCANSO,
            f"{motivo}: {fecha}",
            datos={"fecha": fecha, "motivo": motivo}
        )

    # ══════════════════════════════════════════════════════════════════════════
    # API PÚBLICA — ANOMALÍAS EN TIEMPO REAL (gerente/admin)
    # ══════════════════════════════════════════════════════════════════════════

    def notificar_venta_cancelada(
        self,
        folio:      str,
        total:      float,
        motivo:     str,
        cancelado_por: str,
        sucursal_id: int = 1,
    ) -> None:
        """Alerta inmediata a gerente y admin cuando se cancela una venta."""
        mensaje = (
            f"⚠️ *Venta cancelada*\n"
            f"Folio: *{folio}* | Total: ${total:.2f}\n"
            f"Canceló: {cancelado_por}\n"
            f"Motivo: {motivo or 'No especificado'}"
        )
        self._notificar_por_roles(
            TIPO_VENTA_CANCELADA, mensaje, sucursal_id,
            datos={"folio": folio, "total": total, "motivo": motivo}
        )

    def notificar_diferencia_caja(
        self,
        diferencia:   float,
        turno:        str,
        cajero:       str,
        sucursal_id:  int = 1,
    ) -> None:
        """Alerta cuando el corte Z tiene diferencia entre sistema y efectivo contado."""
        signo = "+" if diferencia > 0 else ""
        mensaje = (
            f"{'🔴' if abs(diferencia) > 50 else '🟡'} *Diferencia en caja*\n"
            f"Turno: {turno} | Cajero: {cajero}\n"
            f"Diferencia: *{signo}${diferencia:.2f}*\n"
            f"{'⚠️ Requiere revisión urgente' if abs(diferencia) > 50 else 'Diferencia menor registrada'}"
        )
        self._notificar_por_roles(
            TIPO_DIFF_CAJA, mensaje, sucursal_id,
            datos={"diferencia": diferencia, "cajero": cajero, "turno": turno}
        )

    def notificar_stock_bajo(
        self,
        productos:   List[Dict],
        sucursal_id: int = 1,
    ) -> None:
        """Alerta de stock bajo a gerente e inventario."""
        if not productos:
            return
        lineas = ["📦 *Stock bajo — acción requerida*"]
        for p in productos[:10]:
            lineas.append(
                f"  • {p.get('nombre','?')}: "
                f"{float(p.get('existencia',0)):.1f} {p.get('unidad','kg')} "
                f"(mín: {float(p.get('stock_minimo',0)):.1f})"
            )
        if len(productos) > 10:
            lineas.append(f"  … y {len(productos)-10} más")
        mensaje = "\n".join(lineas)
        self._notificar_por_roles(
            TIPO_STOCK_BAJO, mensaje, sucursal_id,
            datos={"count": len(productos)}
        )

    def notificar_corte_z(
        self,
        folio:        str,
        total_ventas: float,
        total_caja:   float,
        diferencia:   float,
        cajero:       str,
        sucursal_id:  int = 1,
    ) -> None:
        """
        Notifica el cierre de turno:
          - Cajero: resumen simple
          - Gerente/Admin: resumen completo con diferencia
        """
        # Versión cajero
        msg_cajero = (
            f"✅ *Tu turno ha cerrado*\n"
            f"Folio corte: {folio}\n"
            f"Total en tu turno: *${total_ventas:.2f}*\n"
            f"¡Buen trabajo! 💪"
        )
        # Versión gerente/admin
        diferencia_txt = f"{'🔴' if abs(diferencia) > 50 else '✅'} Diferencia: ${diferencia:+.2f}"
        msg_admin = (
            f"📊 *Corte Z generado*\n"
            f"Folio: {folio} | Cajero: {cajero}\n"
            f"Ventas del turno: *${total_ventas:.2f}*\n"
            f"Efectivo contado: ${total_caja:.2f}\n"
            f"{diferencia_txt}"
        )
        self._notificar_por_roles_multi(
            TIPO_CORTE_Z, sucursal_id,
            mensajes_por_rol={
                "cajero":  msg_cajero,
                "gerente": msg_admin,
                "admin":   msg_admin,
            },
            cajero_username=cajero,
            datos={"folio": folio, "total": total_ventas, "diferencia": diferencia}
        )

    def notificar_diferencia_recepcion(
        self,
        uuid_qr:     str,
        diferencia:  float,
        proveedor:   str,
        sucursal_id: int = 1,
    ) -> None:
        """Alerta cuando hay diferencia en recepción de QR de proveedor."""
        mensaje = (
            f"📦 *Diferencia en recepción*\n"
            f"Contenedor: {uuid_qr[:12]}…\n"
            f"Proveedor: {proveedor}\n"
            f"Diferencia: *{diferencia:+.3f} kg*"
        )
        self._notificar_por_roles(
            TIPO_DIFF_RECEPCION, mensaje, sucursal_id,
            datos={"uuid_qr": uuid_qr, "diferencia": diferencia}
        )

    def notificar_backup_fallido(self, error: str, sucursal_id: int = 1) -> None:
        """Alerta crítica solo para admin cuando falla el backup automático."""
        mensaje = (
            f"🔴 *Backup automático FALLIDO*\n"
            f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            f"Error: {error[:200]}\n"
            f"⚠️ Realiza un backup manual de inmediato."
        )
        self._notificar_por_roles(
            TIPO_BACKUP_FALLO, mensaje, sucursal_id,
            datos={"error": error[:500]}
        )

    def notificar_pedido_wa_nuevo(
        self,
        folio:      str,
        cliente:    str,
        total:      float,
        sucursal_id: int = 1,
    ) -> None:
        """Nuevo pedido WhatsApp — alerta a cajero y gerente."""
        mensaje = (
            f"📲 *Nuevo pedido WhatsApp*\n"
            f"Folio: {folio} | Cliente: {cliente}\n"
            f"Total: ${total:.2f}\n"
            f"Atiéndelo desde el módulo Ventas."
        )
        self._notificar_por_roles(
            TIPO_PEDIDO_WA, mensaje, sucursal_id,
            datos={"folio": folio, "cliente": cliente, "total": total}
        )

    # ══════════════════════════════════════════════════════════════════════════
    # INBOX POS — leer mensajes pendientes al iniciar sesión
    # ══════════════════════════════════════════════════════════════════════════

    def get_inbox_empleado(self, empleado_id: int, solo_no_leidos: bool = True) -> List[Dict]:
        """Retorna mensajes del inbox POS del empleado (se muestra al hacer login)."""
        try:
            where = "WHERE ni.empleado_id=?"
            if solo_no_leidos:
                where += " AND ni.leido=0"
            rows = self.db.execute(
                f"""SELECT ni.id, ni.tipo, ni.titulo, ni.cuerpo,
                           ni.datos, ni.leido, ni.created_at
                    FROM notification_inbox ni
                    {where}
                    ORDER BY ni.created_at DESC LIMIT 50""",
                (empleado_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.debug("get_inbox: %s", exc)
            return []

    def marcar_inbox_leido(self, notif_id: int = None, empleado_id: int = None) -> None:
        """Marca como leído(s) los mensajes del inbox."""
        try:
            if notif_id:
                self.db.execute(
                    "UPDATE notification_inbox SET leido=1, leido_at=datetime('now') WHERE id=?",
                    (notif_id,)
                )
            elif empleado_id:
                self.db.execute(
                    "UPDATE notification_inbox SET leido=1, leido_at=datetime('now') "
                    "WHERE empleado_id=? AND leido=0",
                    (empleado_id,)
                )
            self.db.commit()
        except Exception as exc:
            logger.debug("marcar_inbox_leido: %s", exc)

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVADOS
    # ══════════════════════════════════════════════════════════════════════════

    def _generar_branding(self, nombre: str, total: float) -> str:
        """
        Genera mensaje de branding psicológico combinando:
        - Frase de comunidad / apoyo negocio local
        - Referencia al impacto personal de la compra
        """
        nombre_corto = nombre.split()[0] if nombre else "cliente"
        frases_comunidad = [
            f"🐔 ¡Gracias {nombre_corto}! Cada compra sostiene a familias locales.",
            f"❤️ {nombre_corto}, tu preferencia hace crecer nuestra comunidad.",
            f"🌟 ¡Gracias por elegir lo local, {nombre_corto}! Juntos somos más fuertes.",
            f"🤝 {nombre_corto}, eres parte de algo más grande. ¡Gracias por tu confianza!",
            f"🏡 Comprar local es invertir en tu comunidad. ¡Gracias {nombre_corto}!",
        ]
        frase = random.choice(frases_comunidad)
        # Refuerzo de valor si la compra es significativa
        if total >= 500:
            frase += f"\n💎 Con ${total:.0f} hoy, llevas lo mejor para tu familia."
        return frase

    def _notificar_por_roles(
        self,
        tipo:        str,
        mensaje:     str,
        sucursal_id: int,
        datos:       Dict = None,
    ) -> None:
        """Envía la notificación a todos los empleados con roles autorizados para ese tipo."""
        roles_destino = _ROL_MATRIX.get(tipo, [])
        if not roles_destino:
            return
        empleados = self._get_empleados_por_roles(roles_destino, sucursal_id)
        for emp in empleados:
            if emp.get("telefono"):
                self._enviar_whatsapp(sucursal_id, emp["telefono"], mensaje)
            self._inbox_empleado(
                emp["id"], tipo, self._titulo_de_tipo(tipo), datos=datos
            )

    def _notificar_por_roles_multi(
        self,
        tipo:              str,
        sucursal_id:       int,
        mensajes_por_rol:  Dict[str, str],
        cajero_username:   str = "",
        datos:             Dict = None,
    ) -> None:
        """Envía mensajes diferenciados por rol (ej: cajero ve resumen, admin ve detalles)."""
        for rol, mensaje in mensajes_por_rol.items():
            if rol == "cajero" and cajero_username:
                emp = self._get_empleado_por_usuario(cajero_username)
                if emp:
                    if emp.get("telefono"):
                        self._enviar_whatsapp(sucursal_id, emp["telefono"], mensaje)
                    self._inbox_empleado(
                        emp["id"], tipo, self._titulo_de_tipo(tipo), datos=datos
                    )
            else:
                empleados = self._get_empleados_por_roles([rol], sucursal_id)
                for emp in empleados:
                    # No duplicar al cajero si ya fue notificado arriba
                    if cajero_username and emp.get("usuario") == cajero_username:
                        continue
                    if emp.get("telefono"):
                        self._enviar_whatsapp(sucursal_id, emp["telefono"], mensaje)
                    self._inbox_empleado(
                        emp["id"], tipo, self._titulo_de_tipo(tipo), datos=datos
                    )

    def _enviar_whatsapp(self, branch_id: int, telefono: str,
                         mensaje: str, canal: str = "clientes") -> None:
        """
        Encola mensaje WhatsApp por el canal correcto.
        canal: 'clientes' (ventas/branding) | 'rrhh' (nómina/vacaciones) | 'alertas' (gerente)
        Si el canal 'rrhh' tiene número propio configurado, lo usa. Si no, usa el global.
        """
        if not self.whatsapp_service or not telefono:
            return
        try:
            # Para RRHH: intentar obtener config específica del canal
            if canal in ("rrhh", "alertas"):
                from core.services.whatsapp_service import WhatsAppConfig
                cfg_canal = WhatsAppConfig(
                    conn=self.db, canal=canal, sucursal_id=branch_id
                )
                if cfg_canal.activo and cfg_canal.meta_phone_id !=                    self.whatsapp_service.config.meta_phone_id:
                    # Hay número diferente para este canal → enviar directo
                    from core.services.whatsapp_service import WhatsAppService
                    svc_canal = WhatsAppService(
                        conn=self.db, feature_service=None
                    )
                    svc_canal.config = cfg_canal
                    svc_canal.send_message(
                        branch_id=branch_id, phone_number=telefono, message=mensaje
                    )
                    return
            # Canal unificado (o sin config específica) → usar servicio global
            self.whatsapp_service.send_message(
                branch_id=branch_id,
                phone_number=telefono,
                message=mensaje,
            )
        except Exception as exc:
            logger.debug("_enviar_whatsapp %s canal=%s: %s", telefono[:6], canal, exc)

    def _inbox_empleado(
        self,
        empleado_id: int,
        tipo:        str,
        titulo:      str,
        cuerpo:      str = "",
        datos:       Dict = None,
    ) -> None:
        """Inserta mensaje en notification_inbox para lectura al iniciar sesión."""
        try:
            self.db.execute(
                """INSERT INTO notification_inbox
                   (empleado_id, tipo, titulo, cuerpo, datos, sucursal_id)
                   VALUES(?,?,?,?,?,?)""",
                (
                    empleado_id, tipo, titulo, cuerpo,
                    json.dumps(datos or {}, ensure_ascii=False),
                    self.sucursal_id,
                )
            )
            self.db.commit()
        except Exception as exc:
            logger.debug("_inbox_empleado: %s", exc)

    def _get_telefono_empleado(self, empleado_id: int) -> Optional[str]:
        try:
            row = self.db.execute(
                "SELECT telefono FROM personal WHERE id=? AND activo=1",
                (empleado_id,)
            ).fetchone()
            return row[0] if row and row[0] else None
        except Exception:
            return None

    def _get_empleados_por_roles(
        self, roles: List[str], sucursal_id: int
    ) -> List[Dict]:
        """
        Retorna empleados activos que tengan alguno de los roles indicados.
        Busca en usuarios_roles (RBAC) y en usuarios.rol (legacy).
        Incluye su teléfono desde la tabla personal si existe.
        """
        if not roles:
            return []
        try:
            placeholders = ",".join("?" * len(roles))
            # Intentar con RBAC completo primero
            try:
                rows = self.db.execute(
                    f"""SELECT DISTINCT u.id, u.usuario, u.nombre,
                               COALESCE(p.telefono, u_tel.telefono) AS telefono
                        FROM usuarios u
                        JOIN usuarios_roles ur ON ur.usuario_id = u.id
                        JOIN roles r ON r.id = ur.rol_id
                        LEFT JOIN personal p ON LOWER(p.nombre) LIKE '%' || LOWER(u.nombre) || '%'
                        LEFT JOIN (
                            SELECT nombre, NULL AS telefono FROM usuarios
                        ) u_tel ON FALSE
                        WHERE r.nombre IN ({placeholders})
                          AND (ur.sucursal_id = ? OR ur.sucursal_id = 0)
                          AND u.activo = 1""",
                    (*roles, sucursal_id)
                ).fetchall()
                if rows:
                    return [dict(r) for r in rows]
            except Exception:
                pass
            # Fallback: columna legacy usuarios.rol
            rows = self.db.execute(
                f"""SELECT u.id, u.usuario, u.nombre,
                           p.telefono
                    FROM usuarios u
                    LEFT JOIN personal p ON LOWER(p.nombre) LIKE '%' || LOWER(u.nombre) || '%'
                    WHERE LOWER(u.rol) IN ({placeholders})
                      AND (u.sucursal_id = ? OR u.sucursal_id IS NULL)
                      AND u.activo = 1""",
                (*[r.lower() for r in roles], sucursal_id)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.debug("_get_empleados_por_roles: %s", exc)
            return []

    def _get_empleado_por_usuario(self, username: str) -> Optional[Dict]:
        try:
            row = self.db.execute(
                """SELECT u.id, u.usuario, u.nombre, p.telefono
                   FROM usuarios u
                   LEFT JOIN personal p ON LOWER(p.nombre) LIKE '%' || LOWER(u.nombre) || '%'
                   WHERE u.usuario=? AND u.activo=1 LIMIT 1""",
                (username,)
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    @staticmethod
    def _titulo_de_tipo(tipo: str) -> str:
        """Texto de título legible para el inbox."""
        titulos = {
            TIPO_TICKET:          "Tu ticket de compra",
            TIPO_PUNTOS:          "Puntos ganados",
            TIPO_NIVEL:           "¡Subiste de nivel!",
            TIPO_NOMINA:          "Pago de nómina procesado",
            TIPO_VACACIONES:      "Recordatorio de vacaciones",
            TIPO_DESCANSO:        "Día de descanso",
            TIPO_STOCK_BAJO:      "⚠️ Stock bajo mínimo",
            TIPO_CORTE_Z:         "Corte Z — Cierre de turno",
            TIPO_VENTA_CANCELADA: "⚠️ Venta cancelada",
            TIPO_DIFF_CAJA:       "⚠️ Diferencia en caja",
            TIPO_DIFF_RECEPCION:  "Diferencia en recepción",
            TIPO_CADUCIDAD:       "⚠️ Productos próximos a vencer",
            TIPO_BACKUP_FALLO:    "🔴 Backup fallido",
            TIPO_PEDIDO_WA:       "Nuevo pedido WhatsApp",
            TIPO_PEDIDO_ASIGNADO: "Pedido asignado",
        }
        return titulos.get(tipo, tipo)
