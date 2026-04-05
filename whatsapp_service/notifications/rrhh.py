# notifications/rrhh.py — Notificaciones de RRHH
from __future__ import annotations
from messaging.templates import send_event_template
from messaging.sender import send_text


async def notificar_vacaciones_aprobadas(phone: str, nombre: str,
                                          fecha_inicio: str, fecha_fin: str):
    await send_event_template(phone, "rrhh_vacaciones", {
        "nombre": nombre,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    })


async def notificar_descanso(phone: str, nombre: str, fecha: str):
    await send_text(phone,
        f"🗓️ *Recordatorio de descanso*\n"
        f"{nombre}, tu día de descanso es *{fecha}*.")


async def notificar_nomina(phone: str, nombre: str, periodo: str):
    await send_event_template(phone, "rrhh_nomina", {
        "nombre": nombre, "periodo": periodo})
