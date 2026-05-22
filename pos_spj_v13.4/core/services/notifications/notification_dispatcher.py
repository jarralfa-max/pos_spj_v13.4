# core/services/notifications/notification_dispatcher.py
"""
Despacha notificaciones al canal correcto según política.

CONTRATO:
  - ERP inbox: siempre (para staff)
  - WhatsApp: solo si NotificationPolicyService.is_wa_allowed_for_staff(tipo)
  - El microservicio WA recibe comandos explícitos via POST /api/notify/send

El dispatcher NO decide quién recibe — eso es RecipientResolver.
El dispatcher NO decide si se usa WA — eso es NotificationPolicyService.
El dispatcher ejecuta el despacho.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from core.services.notifications.notification_policy_service import NotificationPolicyService

logger = logging.getLogger("spj.notifications.dispatcher")

_policy = NotificationPolicyService()


class NotificationDispatcher:
    """
    Despacha a ERP inbox y/o WhatsApp según política.

    Inyección:
      db             — conexión SQLite del ERP
      whatsapp_svc   — WhatsAppService (ERP interno) para encolar mensajes
      sucursal_id    — contexto de la sucursal activa
    """

    def __init__(self, db, whatsapp_svc=None, sucursal_id: int = 1) -> None:
        self.db           = db
        self._wa_svc      = whatsapp_svc
        self.sucursal_id  = sucursal_id

    # ── API pública ───────────────────────────────────────────────────────────

    def dispatch_staff(
        self,
        tipo:        str,
        destinatarios: List[Dict],
        titulo:      str,
        mensaje:     str,
        datos:       Optional[Dict] = None,
        sucursal_id: Optional[int] = None,
    ) -> None:
        """
        Despacha a la lista de destinatarios según política:
          - Siempre escribe en ERP inbox.
          - Solo envía WA si la política lo permite para este tipo.

        destinatarios: lista de dicts con al menos {id, telefono}.
        """
        branch = sucursal_id or self.sucursal_id
        wa_ok  = _policy.is_wa_allowed_for_staff(tipo)

        for emp in destinatarios:
            emp_id   = emp.get("id") or emp.get("empleado_id")
            telefono = (emp.get("telefono") or "").strip()
            usuario  = emp.get("usuario")

            # ERP inbox — siempre
            if emp_id:
                self._to_inbox(emp_id, tipo, titulo, datos=datos, usuario=usuario)

            # WhatsApp — solo si política permite Y hay teléfono
            if wa_ok and telefono:
                self._to_whatsapp(branch, telefono, mensaje)
            elif not wa_ok and telefono:
                logger.debug(
                    "dispatcher: tipo=%s → WA bloqueado por política (inbox only)", tipo)

    def dispatch_employee_personal(
        self,
        tipo:        str,
        empleado_id: int,
        telefono:    Optional[str],
        titulo:      str,
        mensaje:     str,
        datos:       Optional[Dict] = None,
        sucursal_id: Optional[int] = None,
        usuario:     Optional[str] = None,
    ) -> None:
        """
        Para notificaciones personales (nómina, vacaciones, descanso).
        Siempre inbox + WA (política permite estos tipos para staff).
        """
        branch = sucursal_id or self.sucursal_id
        self._to_inbox(empleado_id, tipo, titulo, datos=datos, usuario=usuario)
        if telefono:
            wa_ok = _policy.is_wa_allowed_for_staff(tipo)
            if wa_ok:
                self._to_whatsapp(branch, telefono, mensaje)

    def dispatch_customer(
        self,
        telefono: str,
        mensaje:  str,
        sucursal_id: Optional[int] = None,
    ) -> None:
        """Mensajes al cliente — siempre WA, sin inbox."""
        branch = sucursal_id or self.sucursal_id
        if telefono:
            self._to_whatsapp(branch, telefono, mensaje)

    def dispatch_driver(
        self,
        empleado_id: int,
        telefono:    str,
        mensaje:     str,
        datos:       Optional[Dict] = None,
        sucursal_id: Optional[int] = None,
    ) -> None:
        """Notificación al repartidor — inbox + WA (pedido en ruta)."""
        branch = sucursal_id or self.sucursal_id
        tipo = "pedido_asignado_repartidor"
        self._to_inbox(
            empleado_id, tipo, "Pedido asignado — en ruta", datos=datos)
        if telefono:
            self._to_whatsapp(branch, telefono, mensaje)

    # ── Privados ──────────────────────────────────────────────────────────────

    def _to_inbox(
        self,
        empleado_id: int,
        tipo:        str,
        titulo:      str,
        cuerpo:      str = "",
        datos:       Optional[Dict] = None,
        usuario:     Optional[str] = None,
    ) -> None:
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
            # Fallback: schema con columna usuario en lugar de empleado_id
            if usuario:
                try:
                    self.db.execute(
                        """INSERT INTO notification_inbox
                           (usuario, tipo, titulo, cuerpo, sucursal_id)
                           VALUES(?,?,?,?,?)""",
                        (usuario, tipo, titulo, cuerpo, self.sucursal_id)
                    )
                    self.db.commit()
                except Exception as exc2:
                    logger.debug("_to_inbox fallback: %s", exc2)
            else:
                logger.debug("_to_inbox: %s", exc)

    def _to_whatsapp(self, branch_id: int, telefono: str, mensaje: str) -> None:
        if not self._wa_svc or not telefono:
            return
        try:
            self._wa_svc.send_message(
                branch_id=branch_id,
                phone_number=telefono,
                message=mensaje,
            )
        except Exception as exc:
            logger.debug("_to_whatsapp %s: %s", telefono[:6], exc)
