from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


logger = logging.getLogger("spj.tickets.message_engine")


@dataclass
class TicketMessage:
    code: str
    text: str
    priority: int = 0
    category: str = "info"


@dataclass
class TicketMessageResult:
    loyalty_messages: List[TicketMessage] = field(default_factory=list)
    fomo_messages: List[TicketMessage] = field(default_factory=list)
    cta_messages: List[TicketMessage] = field(default_factory=list)
    qr_content: str = ""

    @property
    def all_messages(self) -> List[TicketMessage]:
        return self.loyalty_messages + self.fomo_messages + self.cta_messages


class TicketMessageEngine:
    """Builds loyalty/FOMO/CTA ticket messages from business context/services."""

    def __init__(
        self,
        loyalty_service=None,
        growth_engine=None,
        promotion_engine=None,
        campaign_service=None,
        customer_service=None,
        config_service=None,
    ):
        self.loyalty_service = loyalty_service
        self.growth_engine = growth_engine
        self.promotion_engine = promotion_engine
        self.campaign_service = campaign_service
        self.customer_service = customer_service
        self.config_service = config_service

    def _cfg(self, key: str, default: str) -> str:
        try:
            if self.config_service is None:
                return default
            v = self.config_service.get(key, default)
            return v if v not in (None, "") else default
        except Exception:
            return default

    def build_messages(self, sale_context: Dict[str, Any], customer_context: Optional[Dict[str, Any]] = None) -> TicketMessageResult:
        ctx = dict(customer_context or {})
        result = TicketMessageResult()

        max_fomo = int(self._cfg("ticket_fomo_max_messages", "2") or 2)
        raw_points_gained = sale_context.get("puntos_ganados")
        raw_points_total = sale_context.get("puntos_totales")
        points_gained = int(raw_points_gained or 0) if raw_points_gained not in (None, "") else 0
        points_total = int(raw_points_total or 0) if raw_points_total not in (None, "") else None
        cliente_id = ctx.get("cliente_id") or sale_context.get("cliente_id")

        # Complementar contextos desde servicios de negocio si falta data.
        if cliente_id and points_total is None and self.loyalty_service:
            try:
                if hasattr(self.loyalty_service, "saldo_cliente"):
                    points_total = int(self.loyalty_service.saldo_cliente(str(cliente_id)))
                elif hasattr(self.loyalty_service, "saldo"):
                    points_total = int(self.loyalty_service.saldo(str(cliente_id)))
            except Exception as exc:
                logger.warning("Saldo de puntos no disponible para ticket cliente=%s: %s", cliente_id, exc)

        if cliente_id and "goal_remaining" not in ctx and self.growth_engine:
            try:
                if hasattr(self.growth_engine, "get_metas_activas"):
                    metas = self.growth_engine.get_metas_activas() or []
                    # Heurística: próxima meta activa con menor faltante.
                    pending = []
                    for m in metas:
                        umbral = float(m.get("umbral", 0) or 0)
                        progreso = float(m.get("progreso", 0) or 0)
                        faltan = max(0, int(round(umbral - progreso)))
                        if faltan > 0:
                            pending.append(faltan)
                    if pending:
                        ctx["goal_remaining"] = min(pending)
            except Exception:
                pass

        if "promo_days_left" not in ctx and self.promotion_engine:
            try:
                if hasattr(self.promotion_engine, "get_expiring_promo"):
                    promo = self.promotion_engine.get_expiring_promo(cliente_id=cliente_id) or {}
                    if promo:
                        ctx["promo_days_left"] = int(promo.get("days_left", 0) or 0)
                        ctx["promo_name"] = promo.get("name", "tu promoción")
            except Exception:
                pass

        if points_gained > 0:
            result.loyalty_messages.append(TicketMessage("points_gained", f"Ganaste {points_gained} puntos.", 100, "loyalty"))
        if (points_total or 0) > 0:
            result.loyalty_messages.append(TicketMessage("points_total", f"Tu saldo actual es {points_total} puntos.", 90, "loyalty"))

        goal_remaining = ctx.get("goal_remaining")
        if goal_remaining is not None and int(goal_remaining) > 0 and int(goal_remaining) <= 5:
            tpl = self._cfg("ticket_msg_goal_near", "Estás a {remaining} compras de tu recompensa.")
            result.fomo_messages.append(TicketMessage("goal_near", tpl.format(remaining=int(goal_remaining)), 95, "fomo"))

        points_to_reward = ctx.get("points_to_reward")
        if points_to_reward is not None and int(points_to_reward) > 0 and int(points_to_reward) <= 50:
            result.fomo_messages.append(TicketMessage("points_near_reward", f"Te faltan {int(points_to_reward)} puntos para tu siguiente recompensa.", 85, "fomo"))

        promo_days_left = ctx.get("promo_days_left")
        promo_name = ctx.get("promo_name", "tu promoción")
        if promo_days_left is not None and int(promo_days_left) >= 0 and int(promo_days_left) <= 4:
            tpl = self._cfg("ticket_msg_promo_expiring", "Últimos {days} días de {promo}.")
            result.fomo_messages.append(TicketMessage("promo_expiring", tpl.format(days=int(promo_days_left), promo=promo_name), 98, "fomo"))

        if (points_total or 0) > 0 and ctx.get("can_redeem", False):
            tpl = self._cfg("ticket_msg_points_available", "Ya puedes canjear tus puntos en tu próxima compra.")
            result.cta_messages.append(TicketMessage("points_available", tpl, 80, "cta"))

        if not cliente_id:
            result.cta_messages.append(TicketMessage("new_customer", self._cfg("ticket_msg_new_customer", "Regístrate para acumular puntos en tu próxima compra."), 70, "cta"))
            result.cta_messages.append(TicketMessage("register_cta", self._cfg("ticket_msg_register_cta", "Pide al cajero tu alta al programa de fidelidad."), 60, "cta"))

        # tolerant to optional services
        try:
            if self.campaign_service and hasattr(self.campaign_service, "get_ticket_qr"):
                result.qr_content = self.campaign_service.get_ticket_qr(cliente_id=cliente_id) or ""
        except Exception:
            pass

        result.fomo_messages = sorted(result.fomo_messages, key=lambda m: m.priority, reverse=True)[:max_fomo]
        return result
