"""Shared fixtures for CRM (relationship) integration tests (CRM-4/5/6)."""

import importlib
import sqlite3

import pytest

from backend.infrastructure.db.schema.customer_service_schema import create_customer_service_schema
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema

# Run the CRM migrations in their real bootstrap order: 183 creates the
# Opportunities tables AND seeds the default 6-stage pipeline
# (crm_stage_definitions); 185 creates Activities/Tasks/Notes/Reminders and
# the crm_audit_log columns they need. create_crm_schema() is idempotent
# (CREATE TABLE IF NOT EXISTS) so calling it twice via both migrations is
# safe — this mirrors exactly what a real sequential bootstrap does, unlike
# calling 185 alone, which would create the pipeline-stage table but never
# run 183's seed step.
_run_183 = importlib.import_module("migrations.standalone.183_crm_opportunities_schema").run
_run_185 = importlib.import_module("migrations.standalone.185_crm_activities_schema").run


def _seed_crm_schema(conn) -> None:
    _run_183(conn)
    _run_185(conn)


@pytest.fixture
def crm_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_crm_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def crm_and_customers_conn():
    """ConvertLeadUseCase/CreateOpportunityFromLeadUseCase span both bounded
    contexts — need both schemas on the same connection."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_crm_schema(conn)
    create_customers_crm_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def crm_and_service_conn():
    """CRM-15: CustomerDashboardQueryService composes leads/opportunities/
    activities/tasks (crm schema) with SLA breach status (customer_service
    schema) — needs both on one connection."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_crm_schema(conn)
    create_customer_service_schema(conn)
    yield conn
    conn.close()
