from core.tickets.ticket_message_engine import TicketMessageEngine


class _Cfg:
    def __init__(self, d=None):
        self.d = d or {}

    def get(self, k, default=None):
        return self.d.get(k, default)


def test_cliente_con_meta_cercana():
    eng = TicketMessageEngine(config_service=_Cfg())
    r = eng.build_messages({"puntos_ganados": 25, "puntos_totales": 180}, {"cliente_id": 1, "goal_remaining": 3})
    codes = [m.code for m in r.fomo_messages]
    assert "goal_near" in codes


def test_promocion_por_vencer():
    eng = TicketMessageEngine(config_service=_Cfg())
    r = eng.build_messages({}, {"cliente_id": 1, "promo_days_left": 2, "promo_name": "Puntos dobles"})
    assert any("Últimos" in m.text for m in r.fomo_messages)


def test_cliente_sin_fidelidad():
    eng = TicketMessageEngine(config_service=_Cfg())
    r = eng.build_messages({}, {"cliente_id": 1})
    assert len(r.loyalty_messages) == 0


def test_cliente_con_puntos_suficientes():
    eng = TicketMessageEngine(config_service=_Cfg())
    r = eng.build_messages({"puntos_totales": 220}, {"cliente_id": 1, "can_redeem": True})
    assert any(m.code == "points_available" for m in r.cta_messages)


def test_cliente_nuevo():
    eng = TicketMessageEngine(config_service=_Cfg())
    r = eng.build_messages({}, {})
    codes = [m.code for m in r.cta_messages]
    assert "new_customer" in codes and "register_cta" in codes


def test_servicio_no_disponible_no_rompe():
    eng = TicketMessageEngine(campaign_service=object(), config_service=_Cfg())
    r = eng.build_messages({}, {"cliente_id": 1})
    assert r is not None


def test_maximo_mensajes_y_prioridad():
    cfg = _Cfg({"ticket_fomo_max_messages": "2"})
    eng = TicketMessageEngine(config_service=cfg)
    r = eng.build_messages(
        {"puntos_totales": 100},
        {"cliente_id": 1, "goal_remaining": 2, "promo_days_left": 1, "promo_name": "Promo", "points_to_reward": 20},
    )
    assert len(r.fomo_messages) == 2
    assert r.fomo_messages[0].priority >= r.fomo_messages[1].priority


class _Loyalty:
    def saldo_cliente(self, _cliente_id):
        return 321


class _Growth:
    def get_metas_activas(self):
        return [{"umbral": 10, "progreso": 8}, {"umbral": 50, "progreso": 5}]


class _Promo:
    def get_expiring_promo(self, cliente_id=None):
        return {"days_left": 3, "name": "Happy Hour"}


def test_complementa_desde_servicios_de_negocio():
    eng = TicketMessageEngine(
        loyalty_service=_Loyalty(),
        growth_engine=_Growth(),
        promotion_engine=_Promo(),
        config_service=_Cfg(),
    )
    r = eng.build_messages({"cliente_id": 7}, {"cliente_id": 7})
    codes = [m.code for m in r.fomo_messages]
    assert any(m.code == "points_total" for m in r.loyalty_messages)
    assert "goal_near" in codes
    assert "promo_expiring" in codes
