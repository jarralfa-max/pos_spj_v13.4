"""Datos para emitir, imprimir y publicar tarjetas (LOY-29, §36, §44, §50).

Las tarjetas no consultan tablas al renderizar (§36): reciben los valores ya
resueltos. Esta consulta los arma, cruzando —sólo para leer— Fidelidad (cuenta,
membresía, programa, nivel) y Clientes (nombre visible), y aplica la política
de privacidad (§37) al nombre y a los puntos.

También resuelve las dos preguntas que las pantallas de Tarjetas necesitan y
que no son de ninguna tabla de tarjetas: de qué cliente es una membresía, y qué
membresías activas de un programa aún no tienen tarjeta vigente (los
destinatarios de un lote, §43-44).
"""

from __future__ import annotations

from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.domain.loyalty_cards.policies.privacy_policy import (
    CardNameMode,
    LoyaltyCardPrivacyPolicy,
    LoyaltyCardPrivacySettings,
)
from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
    LoyaltyTransactionRepository,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork
from backend.infrastructure.loyalty_cards.token_codec import card_token_codec_for

NAME_MODE_KEY = "loyalty_tarjeta_nombre_impreso"
PRINT_POINTS_KEY = "loyalty_tarjeta_imprime_puntos"

#: Estados en los que una tarjeta "vigente" impide emitir otra en un lote.
_VIGENTES = ("ISSUED", "ACTIVE", "BLOCKED")


class LoyaltyCardRenderDataQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── configuración de privacidad ─────────────────────────────────────────
    def privacy_settings(self) -> LoyaltyCardPrivacySettings:
        modo = self._config(NAME_MODE_KEY)
        puntos = self._config(PRINT_POINTS_KEY)
        try:
            name_mode = CardNameMode(modo) if modo else CardNameMode.FULL_NAME
        except ValueError:
            name_mode = CardNameMode.FULL_NAME
        return LoyaltyCardPrivacySettings(
            name_mode=name_mode,
            print_points_balance=str(puntos or "").strip().lower() in ("1", "true", "si", "sí"))

    # ── destinatarios ───────────────────────────────────────────────────────
    def customer_for_membership(self, membership_id: str) -> str | None:
        fila = self._conn.execute(
            "SELECT a.customer_id FROM loyalty_memberships m"
            " JOIN loyalty_accounts a ON a.id = m.loyalty_account_id WHERE m.id = ?",
            (membership_id,)).fetchone()
        return str(fila[0]) if fila else None

    def owner_of_membership(self, membership_id: str) -> tuple[str, str] | None:
        """(customer_id, loyalty_account_id) de una membresía, o None."""
        fila = self._conn.execute(
            "SELECT a.customer_id, a.id FROM loyalty_memberships m"
            " JOIN loyalty_accounts a ON a.id = m.loyalty_account_id WHERE m.id = ?",
            (membership_id,)).fetchone()
        return (str(fila[0]), str(fila[1])) if fila else None

    def recipients_without_card(self, program_id: str) -> list[tuple[str, str]]:
        """(customer_id, membership_id) de cada membresía ACTIVA del programa
        sin una tarjeta vigente — nunca dos tarjetas vigentes por lote (§12)."""
        marcas = ",".join("?" for _ in _VIGENTES)
        filas = self._conn.execute(
            "SELECT a.customer_id, m.id FROM loyalty_memberships m"
            " JOIN loyalty_accounts a ON a.id = m.loyalty_account_id"
            " WHERE m.program_id = ? AND m.status = 'ACTIVE' AND NOT EXISTS ("
            f"   SELECT 1 FROM loyalty_cards k WHERE k.membership_id = m.id AND k.status IN ({marcas}))"
            " ORDER BY m.enrolled_at, m.id", (program_id, *_VIGENTES)).fetchall()
        return [(str(c), str(m)) for c, m in filas]

    # ── valores impresos ────────────────────────────────────────────────────
    def placeholders_for_card(self, card_id: str) -> dict[str, str]:
        settings = self.privacy_settings()
        with LoyaltyCardsUnitOfWork(self._conn, owns_transaction=False) as uow:
            card = uow.cards.get(card_id)
            if card is None:
                return {}
            token = uow.tokens.get_active_for_card(card_id)
        datos = self._membership_data(card.membership_id)
        return {
            "card_number": card.card_number,
            "card_token": (self.qr_payload(token.raw_token(card_token_codec_for(self._conn)))
                           if token is not None else ""),
            "customer_name": LoyaltyCardPrivacyPolicy.printed_name(datos["display_name"], settings),
            "program_name": datos["program_name"] or "",
            "membership_tier": datos["tier_name"] or "",
            "expiry_date": (card.expires_at or "")[:10],
            "points_balance": LoyaltyCardPrivacyPolicy.printed_points(
                datos["points"], settings),
        }

    def placeholders_for_batch(self, batch_id: str) -> dict[str, dict[str, str]]:
        with LoyaltyCardsUnitOfWork(self._conn, owns_transaction=False) as uow:
            items = uow.batch_items.list_for_batch(batch_id)
        return {item.card_id: self.placeholders_for_card(item.card_id) for item in items}

    def display_fields_for_card(self, card_id: str) -> dict[str, str]:
        """Lo que muestra la tarjeta digital (§48): sin token, sin teléfono,
        sin saldo salvo que la política lo permita."""
        valores = self.placeholders_for_card(card_id)
        return {k: v for k, v in valores.items() if k != "card_token" and v}

    def design_for_template(self, template_id: str) -> tuple[int, str] | None:
        """(número de versión, esquema JSON) de la versión ACTIVA de la plantilla,
        o de la más reciente si aún no tiene activa. None si no tiene versiones."""
        fila = self._conn.execute(
            "SELECT v.version_number, v.design_schema_json FROM loyalty_card_template_versions v"
            " JOIN loyalty_card_templates t ON t.id = v.template_id WHERE v.template_id = ?"
            " ORDER BY (v.id = t.active_version_id) DESC, v.version_number DESC LIMIT 1",
            (template_id,)).fetchone()
        return (int(fila[0]), str(fila[1])) if fila else None

    def batch_for_print_job(self, job_id: str) -> str | None:
        with LoyaltyCardsUnitOfWork(self._conn, owns_transaction=False) as uow:
            job = uow.print_jobs.get(job_id)
        return job.batch_id if job is not None else None

    def has_digital_projection(self, card_id: str) -> bool:
        with LoyaltyCardsUnitOfWork(self._conn, owns_transaction=False) as uow:
            return uow.digital_projections.get_by_card(card_id) is not None

    @staticmethod
    def qr_payload(raw_token: str) -> str:
        """Lo que va dentro del QR (§32): un prefijo y el token público. Nunca
        un id interno, un teléfono ni un saldo."""
        return f"SPJ-CARD:{raw_token}"

    # ── internos ────────────────────────────────────────────────────────────
    def _membership_data(self, membership_id: str) -> dict:
        fila = self._conn.execute(
            "SELECT a.id, cu.display_name, p.name, t.name FROM loyalty_memberships m"
            " JOIN loyalty_accounts a ON a.id = m.loyalty_account_id"
            " LEFT JOIN customers cu ON cu.id = a.customer_id"
            " LEFT JOIN loyalty_program_definitions p ON p.id = m.program_id"
            " LEFT JOIN loyalty_tiers t ON t.id = m.current_tier_id WHERE m.id = ?",
            (membership_id,)).fetchone()
        if fila is None:
            return {"display_name": "", "program_name": "", "tier_name": "", "points": None}
        cuenta, nombre, programa, nivel = fila
        puntos = int(LoyaltyBalancePolicy.balance(
            LoyaltyTransactionRepository(self._conn).list_for_account(cuenta)))
        return {"display_name": nombre, "program_name": programa, "tier_name": nivel,
                "points": max(puntos, 0)}

    def _config(self, key: str) -> str | None:
        fila = self._conn.execute(
            "SELECT valor FROM configuraciones WHERE clave = ? LIMIT 1", (key,)).fetchone()
        return None if fila is None else str(fila[0] or "").strip() or None


__all__ = ["LoyaltyCardRenderDataQuery", "NAME_MODE_KEY", "PRINT_POINTS_KEY"]
