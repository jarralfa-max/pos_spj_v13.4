# migrations/standalone/194_crm_automation_rules_schema.py
"""CRM Automation Rules (CRM-26, §56) — declarative trigger→action rules
for the CRM (relationship) bounded context.

Extends the existing `crm` package/schema file rather than creating a
sixth sibling bounded context — same reasoning CRM-10 (segmentation) used:
automations orchestrate CRM's own leads/opportunities/tasks/tags, and
§56 sits directly under the CRM heading in the master prompt, not under
its own bounded-context section.

Only calls `create_crm_schema(conn)` — idempotent (`CREATE TABLE IF NOT
EXISTS`), safe on a database that already has every other `crm` table;
adds `crm_automation_rules`/`crm_automation_executions` for the first time
on databases at this migration.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.crm_schema import create_crm_schema

logger = logging.getLogger("spj.migrations.194")


def run(conn) -> None:
    create_crm_schema(conn)
    conn.commit()
    logger.info("194: crm_automation_rules/crm_automation_executions creadas (CRM-26).")


up = run
