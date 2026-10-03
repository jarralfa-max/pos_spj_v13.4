"""291 — retira las tablas legacy de Fidelidad, Growth Engine, Tarjetas y Rifas.

POR QUÉ (medido en la base real el 2026-10-02)
----------------------------------------------
Los contextos canónicos (`loyalty`, `commercial_instruments`, `sweepstakes`,
`loyalty_cards`) tienen sus propias tablas desde LOY-3. Las de abajo son las
que dejó la era anterior (m000, 023, 024, 047, 057, 092, 096, 113, 115):

* NINGUNA tiene escritor en producción (el código que las escribía —`core/`,
  `modulos/`, `repositories/`— se borró con la reconstrucción).
* Sus últimos lectores se retiraron en el mismo cambio que esta migración
  (LOY-29): la doble lectura de saldo sobre `loyalty_ledger`, el resumen de
  Cliente 360 sobre `loyalty_snapshots` y el alta de cliente que escribía
  `tarjetas_fidelidad`.
* En la base real TODAS tenían cero filas, salvo `config_programa_fidelidad`
  con la fila de fábrica `Programa de Puntos / 1 punto por peso` — que ya no
  rige nada: las reglas viven en `configuraciones` (migración 289) y se editan
  en Fidelidad → Configuración.
* Ningún trigger, vista ni llave foránea de otra tabla apunta a ellas.

Mantenerlas era mantener una segunda fuente de verdad latente (§2: "No
conservar tablas legacy", §73: "Un ledger de puntos").

PRUDENCIA: una tabla con filas NO se borra (salvo las de configuración de
fábrica listadas en `_CONFIG_DE_FABRICA`): se deja y se registra en el log.
Borrar historia que alguien aún podría querer migrar no es reversible; dejar una
tabla huérfana sí lo es. En la base real no hay ningún caso así.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.291")

LEGACY_LOYALTY_TABLES: tuple[str, ...] = (
    # Fidelidad / Growth Engine
    "loyalty_ledger", "loyalty_programs", "loyalty_config", "loyalty_snapshots",
    "loyalty_scores", "loyalty_pasivo_log", "loyalty_multiplier_rules",
    "loyalty_redemption_limits", "loyalty_roi_tracking", "loyalty_operations",
    "loyalty_ticket_messages", "loyalty_level_history", "loyalty_challenges",
    "loyalty_challenge_progress", "loyalty_community_goals",
    "loyalty_community_contributions", "config_programa_fidelidad", "historico_puntos",
    "growth_ledger", "growth_metas", "growth_misiones", "growth_misiones_progreso",
    "growth_otp",
    # Tarjetas
    "tarjetas_fidelidad", "card_batches", "card_assignment_history",
    "historico_tarjetas", "lotes_tarjetas_pdf", "config_diseno_tarjetas",
    # Rifas
    "raffle_eligible_branches", "raffle_eligible_categories", "raffle_eligible_products",
    "raffle_financial_ledger", "raffle_prizes", "raffle_rules", "raffle_tickets",
    "raffle_winners", "raffles",
)

#: Configuración legacy cuya única fila es la de fábrica: no es historia.
_CONFIG_DE_FABRICA = frozenset({"config_programa_fidelidad", "loyalty_config",
                                "config_diseno_tarjetas"})


def _existe(conn, nombre: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    ).fetchone() is not None


def run(conn) -> None:
    borradas, conservadas = [], []
    for tabla in LEGACY_LOYALTY_TABLES:
        if not _existe(conn, tabla):
            continue
        filas = conn.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0]
        if filas and tabla not in _CONFIG_DE_FABRICA:
            conservadas.append(f"{tabla}({filas})")
            continue
        conn.execute(f'DROP TABLE "{tabla}"')
        borradas.append(tabla)
    conn.commit()
    logger.info("291: %s tablas legacy de fidelidad retiradas.", len(borradas))
    if conservadas:
        logger.warning(
            "291: tablas legacy CON FILAS conservadas para revisión manual: %s",
            ", ".join(conservadas))


up = run
