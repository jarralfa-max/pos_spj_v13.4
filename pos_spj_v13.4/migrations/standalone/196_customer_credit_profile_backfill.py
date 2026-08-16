# migrations/standalone/196_customer_credit_profile_backfill.py
"""CRM-27 — Finance/Crédito cutover hacia Customer Master (parte 1 de N).

Contexto: `application/services/customer_credit_service.py` (el único
enforcement real del límite de crédito en checkout, `container.
customer_credit_service.validate_credit`) leía la autorización/límite
directamente de `clientes.allows_credit`/`clientes.credit_limit` — la
identidad legacy. El bounded context moderno `customer_credit` (CRM-8,
migración 188) ya tiene un workflow completo (request/review/approve/
suspend/block/reopen/close, permission-gated, con SoD) sobre
`customer_credit_profiles`, keyed por `customers.id` — pero estaba
completamente desconectado del gate real: nadie que aprobara crédito por
ese workflow veía ningún efecto en POS. CRM-25 documentó esto como el
bloqueador explícito para migrar el gate ("switching this gate to the new
Customer Master today would silently compute zero exposure").

Esta migración cierra la mitad de datos de ese gap: crea un
`customer_credit_profiles` AUTHORIZED para todo `clientes` legacy que hoy
tiene `allows_credit=1 AND credit_limit>0`, bridged por
`customers.legacy_customer_id` (CRM-21). La otra mitad — hacer que
`CustomerCreditService.get_customer()` prefiera este perfil cuando existe —
se hace en código (ver ese archivo), no aquí.

No migra `cuentas_por_cobrar`/`clientes.credit_balance` — la exposición
(saldo actual) sigue siendo propiedad de Finanzas sin cambios (mismo
criterio ya documentado por
`backend/domain/customer_credit/entities/customer_credit_profile.py`: un
`current_exposure` cacheado en este bounded context iría stale en cuanto
Ventas registre una venta; no se crea ese campo aquí tampoco).

Bypassa el workflow de permisos (`RequestCustomerCreditUseCase`/
`ApproveCustomerCreditUseCase`, que exige SoD real: quien solicita no
puede autoprobarse) porque esto no es una decisión de negocio nueva — es
un espejo 1:1 de un estado que ya existía en `clientes`, mismo criterio
que `ResolveLegacyCustomerUseCase` ya usa para bypassear
`CustomerDuplicatePolicy` al crear el bridge.

Idempotente: no crea un perfil si el cliente ya tiene uno (por
`legacy_customer_id` bridgeado), sin importar su estado actual — nunca
sobrescribe una decisión ya tomada por el workflow moderno (p.ej. si ya
fue SUSPENDED/BLOCKED manualmente, dejar como está).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
    BackfillLegacyCustomersUseCase,
)
from backend.domain.customer_credit.entities.customer_credit_profile import CustomerCreditProfile
from backend.infrastructure.db.repositories.customer_credit.unit_of_work import (
    CustomerCreditUnitOfWork,
)
from backend.infrastructure.db.schema.customer_credit_schema import create_customer_credit_schema

logger = logging.getLogger("spj.migrations.196")

_SYSTEM_ACTOR = "SYSTEM_MIGRATION_196"


def _backfill_legacy_bridge(conn) -> None:
    backfill = BackfillLegacyCustomersUseCase()
    while True:
        result = backfill.execute(conn, batch_size=1000)
        if result["created"] == 0:
            break
    conn.commit()


def _backfill_credit_profiles(conn) -> int:
    rows = conn.execute(
        "SELECT c.id, cust.id AS customer_id, c.credit_limit"
        " FROM clientes c"
        " JOIN customers cust ON cust.legacy_customer_id = c.id"
        " WHERE COALESCE(c.allows_credit, 0) = 1 AND COALESCE(c.credit_limit, 0) > 0"
    ).fetchall()

    created = 0
    with CustomerCreditUnitOfWork(conn) as uow:
        for legacy_id, customer_id, credit_limit in rows:
            if uow.profiles.get_by_customer_id(customer_id) is not None:
                continue
            operation_id = f"backfill-196-{customer_id}"
            if uow.profiles.get_by_operation_id(operation_id) is not None:
                continue
            profile = CustomerCreditProfile.request(
                customer_id, _SYSTEM_ACTOR,
                requested_limit=Decimal(str(credit_limit)),
                operation_id=operation_id,
            )
            profile.review()
            profile.approve(_SYSTEM_ACTOR, credit_limit=Decimal(str(credit_limit)))
            uow.profiles.save(profile, operation_id=operation_id)
            uow.audit.record(
                action="CREDIT_PROFILE_BACKFILLED", actor_user_id=_SYSTEM_ACTOR,
                customer_id=customer_id, profile_id=profile.id,
                reason=f"backfill migración 196 desde clientes.id={legacy_id}",
                operation_id=operation_id,
            )
            created += 1
    return created


def run(conn) -> None:
    create_customer_credit_schema(conn)
    _backfill_legacy_bridge(conn)
    created = _backfill_credit_profiles(conn)
    logger.info("196: %d customer_credit_profiles creados desde clientes legacy.", created)


up = run
