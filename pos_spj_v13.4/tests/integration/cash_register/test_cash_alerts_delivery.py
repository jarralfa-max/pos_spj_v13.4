"""CASH-26 bloque 2 — los avisos de Caja llegan a alguien, y se entienden.

Medido 2026-10-07: sin reglas ni destinatarios (y sin escritor de
destinatarios), el Corte Z con faltante no avisaba a nadie; el envío sólo
ocurría pulsando «Enviar» en Notificaciones; el texto era el JSON del evento,
UUIDs incluidos; y la shell nunca inyectaba un cliente de WhatsApp.
"""

from __future__ import annotations

import importlib
import re
from decimal import Decimal

import pytest

from backend.application.cash_register.notification_text import describe_cash_event
from tests.integration.cash_register.test_cash_cut_printing import (  # noqa: F401 - fixture
    _caja,
    conn,
)

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}")


class _WhatsApp:
    def __init__(self):
        self.sent = []

    def send_text(self, *, phone_e164, text, idempotency_key):
        self.sent.append((phone_e164, text))
        return idempotency_key


def _run_310(conn):
    importlib.import_module("migrations.standalone.310_seed_cash_difference_alert").run(conn)


def _owner(conn):
    return conn.execute("SELECT id FROM usuarios WHERE usuario='duena'").fetchone()[0]


def _close_with_count(caja, *, opening: str, counted: dict[str, int]):
    caja.open_cash_shift(opening_amount=Decimal(opening))
    caja.begin_cash_shift_closing()
    count = caja.start_blind_count()
    ids = {d.value: d.id for d in caja.denomination_options()}
    for value, quantity in counted.items():
        caja.capture_blind_count_denomination(count_id=count.entity_id,
                                              denomination_id=ids[Decimal(value)],
                                              quantity=quantity)
    caja.confirm_blind_count(count_id=count.entity_id)
    return caja.generate_z_cut()


def test_310_alerts_owners_once_and_respects_an_existing_rule(conn):
    _run_310(conn)
    _run_310(conn)
    rules = conn.execute("SELECT id, channels_json FROM cash_alert_rules").fetchall()
    assert len(rules) == 1 and rules[0][1] == '["IN_APP", "WHATSAPP"]'
    recipients = conn.execute("SELECT user_id FROM cash_in_app_recipients").fetchall()
    assert [r[0] for r in recipients] == [_owner(conn)]
    assert conn.execute("SELECT COUNT(*) FROM cash_whatsapp_recipients").fetchone()[0] == 0


def test_a_short_z_cut_alerts_the_owner_in_app_and_by_whatsapp(conn):
    _run_310(conn)
    whatsapp = _WhatsApp()
    caja = _caja(conn, cash_whatsapp_client=whatsapp)
    rule = caja.alert_rule_options()[0]
    caja.add_cash_alert_recipient(alert_rule_id=rule.id, channel="WHATSAPP",
                                  address="+525512345678", display_name="Duena")
    # Fondo 500, se cuentan 450: faltante de 50 (arriba de la tolerancia de 10).
    z = _close_with_count(caja, opening="500.00", counted={"200": 2, "50": 1})

    folio = conn.execute("SELECT document_number FROM cash_cuts WHERE id=?",
                         (z.entity_id,)).fetchone()[0]
    title, body = conn.execute(
        "SELECT title, body FROM cash_in_app_alerts WHERE recipient_user_id=?",
        (_owner(conn),)).fetchone()
    assert title == "Caja · Diferencia en Corte Z"
    assert f"Faltante de $50.00 en el corte {folio}." in body
    assert "Cajero: Duena." in body and not UUID.search(body)
    assert whatsapp.sent and whatsapp.sent[0][0] == "+525512345678"
    assert "Faltante de $50.00" in whatsapp.sent[0][1]


def test_a_difference_within_tolerance_does_not_alert(conn):
    _run_310(conn)
    caja = _caja(conn, cash_whatsapp_client=_WhatsApp())
    # Se cuentan 495: faltante de 5, dentro de la tolerancia de 10.
    _close_with_count(caja, opening="500.00", counted={"200": 2, "50": 1, "5": 9})
    assert conn.execute("SELECT COUNT(*) FROM cash_differences").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM cash_notification_jobs").fetchone()[0] == 0


def test_recipients_are_validated_and_survive_a_rule_change(conn):
    _run_310(conn)
    caja = _caja(conn)
    rule = caja.alert_rule_options()[0]
    with pytest.raises(ValueError, match="E.164"):
        caja.add_cash_alert_recipient(alert_rule_id=rule.id, channel="WHATSAPP",
                                      address="5512345678", display_name="X")
    added = caja.add_cash_alert_recipient(alert_rule_id=rule.id, channel="WHATSAPP",
                                          address="+525512345678", display_name="Gerente")
    # Cambiar el aviso a sólo WhatsApp lo reemplaza y conserva a los destinatarios.
    caja.configure_cash_catalog(section="alerts", fields={
        "event_name": "CASH_DIFFERENCE_DETECTED", "severity": "CRITICAL",
        "channels": ("WHATSAPP",)})
    nuevo = caja.alert_rule_options()
    assert len(nuevo) == 1 and nuevo[0].id != rule.id and nuevo[0].channels == ("WHATSAPP",)
    assert conn.execute("SELECT COUNT(*) FROM cash_whatsapp_recipients WHERE alert_rule_id=?",
                        (nuevo[0].id,)).fetchone()[0] == 1
    with pytest.raises(ValueError, match="canal"):
        caja.add_cash_alert_recipient(alert_rule_id=nuevo[0].id, channel="IN_APP",
                                      address=_owner(conn))
    caja.deactivate_cash_alert_recipient(row_id=added.entity_id)
    assert conn.execute("SELECT active FROM cash_whatsapp_recipients WHERE id=?",
                        (added.entity_id,)).fetchone()[0] == 0


def test_event_texts_never_show_raw_ids():
    title, body = describe_cash_event(
        "CASH_DIFFERENCE_DETECTED",
        {"amount": "75.5", "z_cut_id": "x", "responsible_user_id": "u", "severity": "CRITICAL",
         "recurrence_count": 3},
        user_name=lambda _id: "Ana", cut_folio=lambda _id: "Z-COR-000007")
    assert title == "Caja · Diferencia en Corte Z"
    assert body.splitlines() == ["Sobrante de $75.50 en el corte Z-COR-000007.",
                                 "Cajero: Ana.", "Severidad: CRÍTICA.",
                                 "Es su diferencia número 3 en el periodo."]
