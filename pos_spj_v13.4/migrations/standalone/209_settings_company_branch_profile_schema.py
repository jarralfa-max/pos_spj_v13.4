# migrations/standalone/209_settings_company_branch_profile_schema.py
"""SET-5 — CompanyProfile / BranchProfile schema.

Creates `company_profiles` (genuinely new — no legacy "empresa" table
exists) and `branch_profiles` (a governance extension keyed 1:1 by the
*existing* `sucursales.id`, not a replacement of it — see
`backend/domain/settings/entities/branch_profile.py`'s docstring for why
a full `sucursales` cutover is out of scope here).

DDL lives in backend/infrastructure/db/schema/settings_schema.py; only
this migration may call create_company_branch_profile_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.settings_schema import create_company_branch_profile_schema

logger = logging.getLogger("spj.migrations.209")


def run(conn) -> None:
    create_company_branch_profile_schema(conn)
    conn.commit()
    logger.info("209: company_profiles + branch_profiles schema created.")


up = run
