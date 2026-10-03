"""Especificaciones de lectura de cada registro del módulo de Fidelidad.

Una entrada por pantalla. El nombre del cliente se lee de Customer Master con un
LEFT JOIN de SOLO LECTURA y sólo `display_name`: Fidelidad no copia identidad
(§52) ni muestra teléfono, correo o domicilio (§37/§53). Un cliente borrado o
inexistente aparece vacío, nunca rompe la lista.

Lo que NO se lee aquí, a propósito:
* saldos (de puntos y de vales): se derivan del libro con la política de dominio
  en la capa de aplicación, no con un SUM en SQL que duplicaría la regla;
* el token del QR: nunca sale a una pantalla.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.loyalty_records.engine import RecordSpec

_CLIENTE = "LEFT JOIN customers {a} ON {a}.id = {col}"
_PROGRAMA = "LEFT JOIN loyalty_program_definitions p ON p.id = {col}"


def _cliente(alias: str, col: str) -> str:
    return _CLIENTE.format(a=alias, col=col)


# ── Fidelidad ──────────────────────────────────────────────────────────────
PROGRAMS = RecordSpec(
    columns=(("id", "p.id"), ("code", "p.code"), ("name", "p.name"),
             ("currency_name", "p.currency_name"), ("status", "p.status"),
             ("created_by_user_id", "p.created_by_user_id"), ("created_at", "p.created_at")),
    source="loyalty_program_definitions p", order="p.created_at DESC, p.id DESC",
    status="p.status", search_in=("p.code", "p.name"))

MEMBERSHIPS = RecordSpec(
    columns=(("id", "m.id"), ("customer_name", "cu.display_name"),
             ("customer_id", "a.customer_id"), ("account_id", "a.id"),
             ("program_name", "p.name"), ("program_id", "m.program_id"),
             ("tier_name", "t.name"), ("status", "m.status"), ("enrolled_at", "m.enrolled_at")),
    source=("loyalty_memberships m JOIN loyalty_accounts a ON a.id = m.loyalty_account_id "
            + _cliente("cu", "a.customer_id") + " " + _PROGRAMA.format(col="m.program_id")
            + " LEFT JOIN loyalty_tiers t ON t.id = m.current_tier_id"),
    order="m.enrolled_at DESC, m.id DESC", status="m.status",
    search_in=("cu.display_name", "cu.customer_number", "p.name"),
    filters={"program_id": "m.program_id", "customer_id": "a.customer_id"})

ACCOUNTS = RecordSpec(
    columns=(("id", "a.id"), ("customer_name", "cu.display_name"),
             ("customer_number", "cu.customer_number"), ("customer_id", "a.customer_id"),
             ("status", "a.status"), ("created_at", "a.created_at")),
    source="loyalty_accounts a " + _cliente("cu", "a.customer_id"),
    order="a.created_at DESC, a.id DESC", status="a.status",
    search_in=("cu.display_name", "cu.customer_number"),
    filters={"customer_id": "a.customer_id"})

LEDGER = RecordSpec(
    columns=(("id", "x.id"), ("created_at", "x.created_at"),
             ("customer_name", "cu.display_name"), ("account_id", "x.loyalty_account_id"),
             ("transaction_type", "x.transaction_type"), ("points_amount", "x.points_amount"),
             ("status", "x.status"), ("reason_code", "x.reason_code"),
             ("source_module", "x.source_module"), ("source_document_id", "x.source_document_id"),
             ("expires_at", "x.expires_at"), ("created_by_user_id", "x.created_by_user_id")),
    source=("loyalty_transactions x JOIN loyalty_accounts a ON a.id = x.loyalty_account_id "
            + _cliente("cu", "a.customer_id")),
    order="x.created_at DESC, x.id DESC", status="x.transaction_type",
    search_in=("cu.display_name", "x.reason_code", "x.source_document_id"),
    filters={"account_id": "x.loyalty_account_id", "customer_id": "a.customer_id"})

TIERS = RecordSpec(
    columns=(("id", "t.id"), ("program_name", "p.name"), ("program_id", "t.program_id"),
             ("code", "t.code"), ("name", "t.name"), ("rank", "t.rank"),
             ("minimum_points", "t.minimum_points"), ("minimum_spend", "t.minimum_spend"),
             ("minimum_visits", "t.minimum_visits"), ("evaluation_method", "t.evaluation_method"),
             ("benefit_multiplier", "t.benefit_multiplier"), ("active", "t.active")),
    source="loyalty_tiers t " + _PROGRAMA.format(col="t.program_id"),
    order="p.name, t.rank, t.id", status="t.evaluation_method",
    search_in=("t.code", "t.name", "p.name"), filters={"program_id": "t.program_id"})

REWARDS = RecordSpec(
    columns=(("id", "r.id"), ("program_name", "p.name"), ("program_id", "r.program_id"),
             ("code", "r.code"), ("name", "r.name"), ("reward_type", "r.reward_type"),
             ("points_cost", "r.points_cost"), ("value", "r.value"), ("active", "r.active")),
    source="loyalty_rewards r " + _PROGRAMA.format(col="r.program_id"),
    order="p.name, r.points_cost, r.id", status="r.reward_type",
    search_in=("r.code", "r.name"), filters={"program_id": "r.program_id"})

REWARD_REDEMPTIONS = RecordSpec(
    columns=(("id", "x.id"), ("requested_at", "x.requested_at"),
             ("customer_name", "cu.display_name"), ("reward_name", "r.name"),
             ("points_cost", "r.points_cost"), ("status", "x.status"),
             ("confirmed_at", "x.confirmed_at"), ("cancelled_at", "x.cancelled_at")),
    source=("loyalty_reward_redemptions x LEFT JOIN loyalty_rewards r ON r.id = x.reward_id "
            "LEFT JOIN loyalty_accounts a ON a.id = x.loyalty_account_id "
            + _cliente("cu", "a.customer_id")),
    order="x.requested_at DESC, x.id DESC", status="x.status",
    search_in=("cu.display_name", "r.name"))

CHALLENGES = RecordSpec(
    columns=(("id", "c.id"), ("program_name", "p.name"), ("code", "c.code"),
             ("name", "c.name"), ("mode", "c.mode"), ("criteria_type", "c.criteria_type"),
             ("target_value", "c.target_value"), ("points_reward", "c.points_reward"),
             ("status", "c.status"), ("start_date", "c.start_date"), ("end_date", "c.end_date"),
             ("completed", "(SELECT COUNT(*) FROM loyalty_challenge_member_progress g"
                           " WHERE g.challenge_id = c.id AND g.completed = 1)")),
    source="loyalty_challenge_definitions c " + _PROGRAMA.format(col="c.program_id"),
    order="c.created_at DESC, c.id DESC", status="c.status",
    search_in=("c.code", "c.name"), filters={"program_id": "c.program_id"})

REFERRALS = RecordSpec(
    columns=(("id", "r.id"), ("registered_at", "r.registered_at"),
             ("referrer_name", "rc.display_name"), ("referred_name", "dc.display_name"),
             ("program_name", "p.name"), ("status", "r.status"),
             ("referrer_bonus_points", "r.referrer_bonus_points"),
             ("referred_bonus_points", "r.referred_bonus_points"),
             ("minimum_purchase_amount", "r.minimum_purchase_amount"),
             ("expires_at", "r.expires_at")),
    source=("loyalty_referrals r "
            "LEFT JOIN loyalty_memberships m ON m.id = r.referrer_membership_id "
            "LEFT JOIN loyalty_accounts a ON a.id = m.loyalty_account_id "
            + _cliente("rc", "a.customer_id") + " " + _cliente("dc", "r.referred_customer_id")
            + " " + _PROGRAMA.format(col="r.program_id")),
    order="r.registered_at DESC, r.id DESC", status="r.status",
    search_in=("rc.display_name", "dc.display_name"))

CAMPAIGNS = RecordSpec(
    columns=(("id", "c.id"), ("code", "c.code"), ("name", "c.name"),
             ("campaign_type", "c.campaign_type"), ("status", "c.status"),
             ("start_at", "c.start_at"), ("end_at", "c.end_at"),
             ("budget_limit", "c.budget_limit"), ("benefit_type", "c.benefit_type"),
             ("created_by_user_id", "c.created_by_user_id")),
    source="loyalty_campaigns c", order="c.created_at DESC, c.id DESC", status="c.status",
    search_in=("c.code", "c.name"))

RETENTION_CAMPAIGNS = RecordSpec(
    columns=CAMPAIGNS.columns, source=CAMPAIGNS.source, order=CAMPAIGNS.order,
    status=CAMPAIGNS.status, search_in=CAMPAIGNS.search_in,
    where="c.campaign_type IN ('RETENTION', 'WIN_BACK')")

BIRTHDAYS = RecordSpec(
    columns=(("id", "b.id"), ("program_name", "p.name"), ("program_id", "b.program_id"),
             ("enabled", "b.enabled"), ("benefit_type", "b.benefit_type"),
             ("points_amount", "b.points_amount"), ("days_before", "b.days_before"),
             ("days_after", "b.days_after"), ("notification_channel", "b.notification_channel")),
    source="loyalty_birthday_configs b " + _PROGRAMA.format(col="b.program_id"),
    order="p.name, b.id", status="b.benefit_type", search_in=("p.name",))

FRAUD_CASES = RecordSpec(
    columns=(("id", "f.id"), ("opened_at", "f.opened_at"), ("subject_type", "f.subject_type"),
             ("subject_id", "f.subject_id"), ("customer_name", "cu.display_name"),
             ("reason", "f.reason"), ("status", "f.status"),
             ("opened_by_user_id", "f.opened_by_user_id"), ("resolved_at", "f.resolved_at"),
             ("resolution_notes", "f.resolution_notes")),
    source="loyalty_fraud_cases f " + _cliente("cu", "f.customer_id"),
    order="f.opened_at DESC, f.id DESC", status="f.status",
    search_in=("cu.display_name", "f.reason", "f.subject_type"))


def _audit(module: str) -> RecordSpec:
    return RecordSpec(
        columns=(("id", "l.id"), ("fecha", "l.fecha"), ("usuario", "COALESCE(u.nombre, l.usuario)"),
                 ("accion", "l.accion"), ("entidad", "l.entidad"), ("entidad_id", "l.entidad_id"),
                 ("detalles", "l.detalles")),
        source="audit_logs l LEFT JOIN usuarios u ON u.id = l.usuario",
        order="l.fecha DESC, l.id DESC", status="l.entidad",
        search_in=("l.accion", "l.entidad_id", "u.nombre"),
        where=f"l.modulo = '{module}'")


LOYALTY_AUDIT = _audit("GROWTH_ENGINE")

# ── Instrumentos comerciales ─────────────────────────────────────────────────
COUPON_DEFINITIONS = RecordSpec(
    columns=(("id", "d.id"), ("code", "d.code"), ("name", "d.name"),
             ("coupon_type", "d.coupon_type"), ("benefit_type", "d.benefit_type"),
             ("benefit_value", "d.benefit_value"), ("valid_from", "d.valid_from"),
             ("valid_to", "d.valid_to"), ("active", "d.active"),
             ("issued", "(SELECT COUNT(*) FROM coupon_instances i WHERE i.definition_id = d.id)")),
    source="coupon_definitions d", order="d.created_at DESC, d.id DESC",
    status="d.coupon_type", search_in=("d.code", "d.name"))

COUPONS = RecordSpec(
    columns=(("id", "i.id"), ("code", "i.code"), ("definition_name", "d.name"),
             ("customer_name", "cu.display_name"), ("status", "i.status"),
             ("issued_at", "i.issued_at"), ("redeemed_at", "i.redeemed_at"),
             ("sale_id", "i.sale_id")),
    source=("coupon_instances i LEFT JOIN coupon_definitions d ON d.id = i.definition_id "
            + _cliente("cu", "i.customer_id")),
    order="i.issued_at DESC, i.id DESC", status="i.status",
    search_in=("i.code", "cu.display_name", "d.name"),
    filters={"definition_id": "i.definition_id", "customer_id": "i.customer_id"})

VOUCHER_DEFINITIONS = RecordSpec(
    columns=(("id", "d.id"), ("code", "d.code"), ("name", "d.name"),
             ("voucher_type", "d.voucher_type"), ("active", "d.active"),
             ("issued", "(SELECT COUNT(*) FROM voucher_instances i WHERE i.definition_id = d.id)")),
    source="voucher_definitions d", order="d.created_at DESC, d.id DESC",
    status="d.voucher_type", search_in=("d.code", "d.name"))

VOUCHERS = RecordSpec(
    columns=(("id", "i.id"), ("code", "i.code"), ("definition_name", "d.name"),
             ("customer_name", "cu.display_name"), ("status", "i.status"),
             ("issued_at", "i.issued_at"), ("expires_at", "i.expires_at")),
    source=("voucher_instances i LEFT JOIN voucher_definitions d ON d.id = i.definition_id "
            + _cliente("cu", "i.customer_id")),
    order="i.issued_at DESC, i.id DESC", status="i.status",
    search_in=("i.code", "cu.display_name", "d.name"),
    filters={"definition_id": "i.definition_id", "customer_id": "i.customer_id"})

# ── Sorteos ─────────────────────────────────────────────────────────────────
SWEEPSTAKES_CAMPAIGNS = RecordSpec(
    columns=(("id", "c.id"), ("code", "c.code"), ("name", "c.name"), ("status", "c.status"),
             ("starts_at", "c.starts_at"), ("ends_at", "c.ends_at"),
             ("created_by_user_id", "c.created_by_user_id"),
             ("entries", "(SELECT COUNT(*) FROM sweepstakes_entries e WHERE e.campaign_id = c.id)"),
             ("tickets", "(SELECT COUNT(*) FROM sweepstakes_tickets t WHERE t.campaign_id = c.id)"),
             ("prizes", "(SELECT COUNT(*) FROM sweepstakes_prizes z WHERE z.campaign_id = c.id)")),
    source="sweepstakes_campaigns c", order="c.created_at DESC, c.id DESC", status="c.status",
    search_in=("c.code", "c.name"))

SWEEPSTAKES_ENTRIES = RecordSpec(
    columns=(("id", "e.id"), ("created_at", "e.created_at"), ("campaign_name", "c.name"),
             ("campaign_id", "e.campaign_id"), ("customer_name", "cu.display_name"),
             ("entry_method", "e.entry_method"), ("chances_granted", "e.chances_granted"),
             ("source_sale_id", "e.source_sale_id"),
             ("tickets", "(SELECT COUNT(*) FROM sweepstakes_tickets t WHERE t.entry_id = e.id)")),
    source=("sweepstakes_entries e LEFT JOIN sweepstakes_campaigns c ON c.id = e.campaign_id "
            + _cliente("cu", "e.customer_id")),
    order="e.created_at DESC, e.id DESC", status="e.entry_method",
    search_in=("cu.display_name", "c.name"), filters={"campaign_id": "e.campaign_id"})

SWEEPSTAKES_TICKETS = RecordSpec(
    columns=(("id", "t.id"), ("ticket_number", "t.ticket_number"), ("campaign_name", "c.name"),
             ("campaign_id", "t.campaign_id"), ("customer_name", "cu.display_name"),
             ("status", "t.status"), ("print_count", "t.print_count"),
             ("last_printed_at", "t.last_printed_at"), ("created_at", "t.created_at")),
    source=("sweepstakes_tickets t LEFT JOIN sweepstakes_campaigns c ON c.id = t.campaign_id "
            + _cliente("cu", "t.customer_id")),
    order="t.created_at DESC, t.id DESC", status="t.status",
    search_in=("t.ticket_number", "cu.display_name"), filters={"campaign_id": "t.campaign_id"})

SWEEPSTAKES_PRIZES = RecordSpec(
    columns=(("id", "z.id"), ("campaign_name", "c.name"), ("rank", "z.rank"), ("name", "z.name"),
             ("quantity", "z.quantity"), ("estimated_cost", "z.estimated_cost"),
             ("status", "z.status")),
    source="sweepstakes_prizes z LEFT JOIN sweepstakes_campaigns c ON c.id = z.campaign_id",
    order="c.name, z.rank, z.id", status="z.status", search_in=("z.name", "c.name"),
    filters={"campaign_id": "z.campaign_id"})

SWEEPSTAKES_DRAWS = RecordSpec(
    columns=(("id", "d.id"), ("campaign_name", "c.name"), ("campaign_id", "d.campaign_id"),
             ("status", "d.status"), ("scheduled_at", "d.scheduled_at"),
             ("executed_at", "d.executed_at"), ("ticket_pool_size", "d.ticket_pool_size"),
             ("random_seed", "d.random_seed"), ("pool_hash", "d.pool_hash"),
             ("executed_by_user_id", "d.executed_by_user_id")),
    source="sweepstakes_draws d LEFT JOIN sweepstakes_campaigns c ON c.id = d.campaign_id",
    order="COALESCE(d.executed_at, d.scheduled_at) DESC, d.id DESC", status="d.status",
    search_in=("c.name",), filters={"campaign_id": "d.campaign_id"})

SWEEPSTAKES_WINNERS = RecordSpec(
    columns=(("id", "w.id"), ("selected_at", "w.selected_at"), ("campaign_name", "c.name"),
             ("ticket_number", "t.ticket_number"), ("customer_name", "cu.display_name"),
             ("prize_name", "z.name"), ("rank", "w.rank"), ("status", "w.status"),
             ("delivered_at", "w.delivered_at")),
    source=("sweepstakes_winners w LEFT JOIN sweepstakes_campaigns c ON c.id = w.campaign_id "
            "LEFT JOIN sweepstakes_tickets t ON t.id = w.ticket_id "
            "LEFT JOIN sweepstakes_prizes z ON z.id = w.prize_id "
            + _cliente("cu", "w.customer_id")),
    order="w.selected_at DESC, w.rank, w.id", status="w.status",
    search_in=("cu.display_name", "t.ticket_number", "c.name"),
    filters={"campaign_id": "w.campaign_id"})

# ── Tarjetas ────────────────────────────────────────────────────────────────
CARDS = RecordSpec(
    columns=(("id", "k.id"), ("card_number", "k.card_number"), ("card_type", "k.card_type"),
             ("customer_name", "cu.display_name"), ("customer_id", "k.customer_id"),
             ("membership_id", "k.membership_id"), ("status", "k.status"),
             ("issued_at", "k.issued_at"), ("activated_at", "k.activated_at"),
             ("expires_at", "k.expires_at"), ("replaces_card_id", "k.replaces_card_id")),
    source="loyalty_cards k " + _cliente("cu", "k.customer_id"),
    order="k.created_at DESC, k.id DESC", status="k.status",
    search_in=("k.card_number", "cu.display_name"),
    filters={"customer_id": "k.customer_id", "card_type": "k.card_type"})

CARD_REPLACEMENTS = RecordSpec(
    columns=CARDS.columns, source=CARDS.source, order=CARDS.order, status=CARDS.status,
    search_in=CARDS.search_in, where="(k.replaces_card_id IS NOT NULL OR k.replaced_by_card_id IS NOT NULL)")

CARD_TEMPLATES = RecordSpec(
    columns=(("id", "t.id"), ("code", "t.code"), ("name", "t.name"),
             ("target_type", "t.target_type"), ("status", "t.status"),
             ("active_version", "(SELECT v.version_number FROM loyalty_card_template_versions v"
                                " WHERE v.id = t.active_version_id)"),
             ("versions", "(SELECT COUNT(*) FROM loyalty_card_template_versions v"
                          " WHERE v.template_id = t.id)"),
             ("created_by_user_id", "t.created_by_user_id")),
    source="loyalty_card_templates t", order="t.created_at DESC, t.id DESC", status="t.status",
    search_in=("t.code", "t.name"))

CARD_TEMPLATE_VERSIONS = RecordSpec(
    columns=(("id", "v.id"), ("template_name", "t.name"), ("template_id", "v.template_id"),
             ("version_number", "v.version_number"), ("status", "v.status"),
             ("created_by_user_id", "v.created_by_user_id"), ("activated_at", "v.activated_at"),
             ("created_at", "v.created_at")),
    source="loyalty_card_template_versions v JOIN loyalty_card_templates t ON t.id = v.template_id",
    order="t.name, v.version_number DESC", status="v.status", search_in=("t.name",),
    filters={"template_id": "v.template_id"})

CARD_SHEETS = RecordSpec(
    columns=(("id", "s.id"), ("code", "s.code"), ("name", "s.name"),
             ("width_mm", "s.width_mm"), ("height_mm", "s.height_mm"),
             ("orientation", "s.orientation"), ("margin_top_mm", "s.margin_top_mm"),
             ("margin_left_mm", "s.margin_left_mm"), ("active", "s.active")),
    source="loyalty_card_sheet_profiles s", order="s.created_at DESC, s.id DESC",
    status="s.orientation", search_in=("s.code", "s.name"))

CARD_IMPOSITIONS = RecordSpec(
    columns=(("id", "i.id"), ("sheet_name", "s.name"), ("sheet_profile_id", "i.sheet_profile_id"),
             ("card_width_mm", "i.card_width_mm"), ("card_height_mm", "i.card_height_mm"),
             ("columns", "i.columns"), ("rows", "i.rows"), ("bleed_mm", "i.bleed_mm"),
             ("safe_area_mm", "i.safe_area_mm"), ("created_at", "i.created_at")),
    source=("loyalty_card_imposition_profiles i "
            "LEFT JOIN loyalty_card_sheet_profiles s ON s.id = i.sheet_profile_id"),
    order="i.created_at DESC, i.id DESC", search_in=("s.name",),
    filters={"sheet_profile_id": "i.sheet_profile_id"})

CARD_BATCHES = RecordSpec(
    columns=(("id", "b.id"), ("created_at", "b.created_at"), ("template_name", "t.name"),
             ("item_count", "b.item_count"), ("cards_per_sheet", "b.cards_per_sheet"),
             ("status", "b.status"), ("created_by_user_id", "b.created_by_user_id"),
             ("printed", "(SELECT COUNT(*) FROM loyalty_card_batch_items x"
                         " WHERE x.batch_id = b.id AND x.status = 'PRINTED')")),
    source="loyalty_card_batches b LEFT JOIN loyalty_card_templates t ON t.id = b.template_id",
    order="b.created_at DESC, b.id DESC", status="b.status", search_in=("t.name",))

CARD_PRINT_JOBS = RecordSpec(
    columns=(("id", "j.id"), ("requested_at", "j.requested_at"), ("batch_id", "j.batch_id"),
             ("template_name", "t.name"), ("only_sheet_number", "j.only_sheet_number"),
             ("status", "j.status"), ("reprint_of_job_id", "j.reprint_of_job_id"),
             ("reprint_reason", "j.reprint_reason"), ("failure_reason", "j.failure_reason"),
             ("requested_by", "COALESCE(u.nombre, j.requested_by_user_id)")),
    source=("loyalty_card_print_jobs j LEFT JOIN loyalty_card_batches b ON b.id = j.batch_id "
            "LEFT JOIN loyalty_card_templates t ON t.id = b.template_id "
            "LEFT JOIN usuarios u ON u.id = j.requested_by_user_id"),
    order="j.requested_at DESC, j.id DESC", status="j.status", search_in=("t.name",),
    filters={"batch_id": "j.batch_id"})

CARD_REPRINTS = RecordSpec(
    columns=CARD_PRINT_JOBS.columns, source=CARD_PRINT_JOBS.source, order=CARD_PRINT_JOBS.order,
    status=CARD_PRINT_JOBS.status, search_in=CARD_PRINT_JOBS.search_in,
    where="j.reprint_of_job_id IS NOT NULL")

DIGITAL_CARDS = RecordSpec(
    columns=(("id", "d.id"), ("card_number", "d.card_number"), ("card_id", "d.card_id"),
             ("customer_name", "cu.display_name"), ("last_refreshed_at", "d.last_refreshed_at"),
             ("created_at", "d.created_at")),
    source="loyalty_digital_card_projections d " + _cliente("cu", "d.customer_id"),
    order="d.last_refreshed_at DESC, d.id DESC", search_in=("d.card_number", "cu.display_name"))

CARD_AUDIT = _audit("TARJETAS_FIDELIDAD")
