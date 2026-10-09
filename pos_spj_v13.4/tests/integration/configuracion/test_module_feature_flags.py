"""Módulos por sucursal: flag `modulo.<id>` (migración 305) + regla de sucursal.

Antes no había forma de apagar un módulo en una sucursal: la barra global
sabía ocultar por flag, pero ningún módulo declaraba uno.
"""

from __future__ import annotations

import importlib

import pytest

from backend.application.feature_flags.branch_feature_flags_query import BranchFeatureFlagsQuery
from backend.application.feature_flags.module_flags import module_disabled
from backend.bootstrap.application_context import FeatureContext
from backend.domain.feature_flags.entities.feature_flag_rule import FeatureFlagRule
from backend.domain.feature_flags.enums import FeatureFlagScopeType
from backend.infrastructure.db.repositories.feature_flags.feature_flag_repository import (
    SqliteFeatureFlagRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_rule_repository import (
    SqliteFeatureFlagRuleRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

_m305 = importlib.import_module("migrations.standalone.305_seed_module_feature_flags")


@pytest.fixture
def conn():
    c = make_db()
    _m305.run(c)
    _m305.run(c)  # idempotente
    yield c
    c.close()


def _context(conn, branch_id) -> FeatureContext:
    query = BranchFeatureFlagsQuery(SqliteFeatureFlagRepository(conn),
                                    SqliteFeatureFlagRuleRepository(conn))
    return FeatureContext.from_flags_dict(query.flags_for(branch_id))


def test_every_module_gets_a_flag_that_starts_on_and_configuracion_gets_none(conn):
    codes = {r[0] for r in conn.execute("SELECT code FROM ff_flags WHERE code LIKE 'modulo.%'")}
    assert len(codes) == len(_m305.MODULES) and "modulo.configuracion" not in codes
    contexto = _context(conn, new_uuid())
    assert not any(module_disabled(contexto, m) for m, _ in _m305.MODULES)


def test_a_branch_rule_switches_a_module_off_only_in_that_branch(conn):
    apagada, otra = new_uuid(), new_uuid()
    flag = SqliteFeatureFlagRepository(conn).get_by_code("modulo.meat_processing")
    SqliteFeatureFlagRuleRepository(conn).save(FeatureFlagRule.create(
        flag_id=flag.id, scope_type=FeatureFlagScopeType.BRANCH, scope_id=apagada, enabled=False))
    conn.commit()
    assert module_disabled(_context(conn, apagada), "meat_processing")
    assert not module_disabled(_context(conn, otra), "meat_processing")
    assert not module_disabled(_context(conn, apagada), "sales_pos")
