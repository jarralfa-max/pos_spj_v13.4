"""p005 — Estructura organizacional central (auditoría enterprise, cierre de la
Fase 1).

Las estaciones mandan una foto completa de cada unidad (`ORG_UNIT_*` desde
`org_outbox`). Aquí queda la más reciente por `updated_at`, con sus
capacidades. Es la vista consolidada de la organización: qué sitios existen,
de quién dependen y qué pueden hacer, sin importar qué estación los dio de alta.

La vista `central_org_sites` lista sólo los sitios de operación (los que tienen
fila de `sucursales` en las estaciones, `branch_id` = `unit_id`). Idempotente.
"""

from __future__ import annotations

DDL = (
    """
    CREATE TABLE IF NOT EXISTS central_org_units (
        unit_id           UUID PRIMARY KEY,
        company_id        UUID NOT NULL,
        parent_id         UUID,
        unit_type         TEXT NOT NULL CHECK (unit_type IN ('RETAIL_BRANCH',
                              'PRODUCTION_PLANT', 'DISTRIBUTION_CENTER', 'WAREHOUSE',
                              'CORPORATE_OFFICE', 'LOGISTICS_OPERATION', 'REGION')),
        code              TEXT NOT NULL,
        name              TEXT NOT NULL,
        status            TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'CLOSED')),
        closed_at         TIMESTAMPTZ,
        capabilities      TEXT[] NOT NULL DEFAULT '{}',
        source_branch_id  UUID NOT NULL,
        last_event_id     UUID NOT NULL REFERENCES sync_inbox (event_id),
        updated_at        TIMESTAMPTZ NOT NULL,
        CHECK (parent_id IS NULL OR parent_id <> unit_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_org_units_parent ON central_org_units (parent_id)",
    """
    CREATE OR REPLACE VIEW central_org_sites AS
    SELECT unit_id AS branch_id, company_id, parent_id, unit_type, code, name, status,
           capabilities
    FROM central_org_units
    WHERE unit_type <> 'REGION'
    """,
)


def run(conn) -> None:
    with conn.cursor() as cur:
        for sentencia in DDL:
            cur.execute(sentencia)


up = run
