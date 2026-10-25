"""Caja de prueba del Slice 6: una base SQLite con Finanzas, Fidelidad, Crédito y
Caja que produce, por sus casos de uso y constructores REALES, una venta a
crédito, una cuenta de crédito, puntos (gana, reserva, confirma) y un turno."""
import importlib
import json
import sqlite3
from datetime import date
from decimal import Decimal

from backend.shared.ids import new_uuid


def build_station(station_id: str, branch_id: str):
    from backend.application.event_handlers.finance.sale_completed_handler import (
        SaleCompletedHandler,
    )
    from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
    from backend.application.loyalty.use_cases.ledger_use_cases import (
        AccrueLoyaltyPointsUseCase, ConfirmReservedLoyaltyPointsUseCase,
        ReserveLoyaltyPointsUseCase,
    )
    from backend.application.services.finance.finance_bootstrap import bootstrap_finance
    from backend.application.sync.replication_outbox import ReplicationOutboxService
    from backend.domain.cash_register.events import CashEvents, cash_event_payload
    from backend.domain.customer_credit.events import build_event_payload as credit_event
    from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
    from backend.infrastructure.db.repositories.cash_register.unit_of_work import (
        CashRegisterUnitOfWork,
    )
    from backend.infrastructure.db.repositories.loyalty.account_repository import (
        LoyaltyAccountRepository,
    )
    from backend.infrastructure.db.schema.customer_credit_schema import (
        create_customer_credit_schema,
    )
    from backend.infrastructure.db.schema.finance_schema import create_finance_schema
    from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

    caja = sqlite3.connect(":memory:")
    caja.row_factory = sqlite3.Row
    create_finance_schema(caja)
    bootstrap_finance(caja, today=date(2026, 7, 16))
    create_loyalty_schema(caja)
    create_customer_credit_schema(caja)
    caja.execute("CREATE TABLE IF NOT EXISTS configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(caja)
    importlib.import_module("migrations.standalone.350_replication_engine").run(caja)
    caja.commit()
    ReplicationOutboxService.register_station(caja, station_id=station_id, branch_id=branch_id)

    cliente = new_uuid()
    # Finanzas: venta a crédito de $100 al cliente.
    SaleCompletedHandler(caja).handle({
        "event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": new_uuid(),
        "customer_id": cliente, "occurred_at": "2026-07-16T12:00:00",
        "gross_total": "100.00", "net_total": "100.00",
        "settlements": [{"type": "ON_CREDIT", "amount": "100.00"}]})
    # Crédito: aprobado con límite $5,000.
    perfil = new_uuid()
    evento = credit_event("CUSTOMER_CREDIT_APPROVED", operation_id=new_uuid(),
                          customer_id=cliente, profile_id=perfil, user_id=new_uuid(),
                          credit_limit="5000.00")
    caja.execute("INSERT INTO customer_credit_outbox (id, event_id, event_name, payload_json,"
                 " operation_id, status, created_at) VALUES (?,?,?,?,?,'PENDING',?)",
                 (new_uuid(), evento["event_id"], evento["event_name"], json.dumps(evento),
                  evento["operation_id"], evento["timestamp"]))
    caja.commit()
    # Fidelidad: gana 100, reserva y confirma 30.
    auth = LoyaltyAuthorizationPolicy.permissive_for_tests()
    cuenta = LoyaltyAccount.create(customer_id=cliente)
    LoyaltyAccountRepository(caja).save(cuenta)
    caja.commit()
    comun = dict(actor_user_id=new_uuid(), actor_branch_id=branch_id)
    assert AccrueLoyaltyPointsUseCase(auth).execute(
        caja, loyalty_account_id=cuenta.id, points_amount=Decimal("100"), operation_id=new_uuid(),
        source_module="sales", source_document_id=new_uuid(), sale_id=new_uuid(), **comun).success
    reserva = ReserveLoyaltyPointsUseCase(auth).execute(
        caja, loyalty_account_id=cuenta.id, points_amount=Decimal("30"), operation_id=new_uuid(),
        source_module="sales", **comun)
    assert reserva.success
    assert ConfirmReservedLoyaltyPointsUseCase(auth).execute(
        caja, transaction_id=reserva.entity_id, operation_id=new_uuid(), **comun).success
    # Caja: turno, venta en efectivo, retiro a caja fuerte y corte Z.
    turno = new_uuid()
    for tipo, datos in (
            (CashEvents.SHIFT_OPENED, dict(entity_id=turno, opening_amount="500.00",
                                           register_id=new_uuid(), cashier_user_id=new_uuid())),
            (CashEvents.MOVEMENT_RECORDED, dict(entity_id=new_uuid(), shift_id=turno,
                                                movement_type="CASH_SALE", direction="INFLOW",
                                                amount="150.00")),
            (CashEvents.SAFE_DROP_RECORDED, dict(entity_id=new_uuid(), shift_id=turno,
                                                 amount="100.00")),
            (CashEvents.Z_CUT_GENERATED, dict(entity_id=new_uuid(), shift_id=turno,
                                              document_number="Z-1", expected_cash="550.00",
                                              counted_cash="549.50", difference="-0.50"))):
        entidad = datos.pop("entity_id")
        ev = cash_event_payload(tipo, operation_id=new_uuid(), entity_id=entidad,
                                branch_id=branch_id, user_id=new_uuid(), **datos)
        with CashRegisterUnitOfWork(caja) as uow:
            uow.events.add(ev)
            uow.outbox.enqueue(ev)
    return caja, {"customer_id": cliente, "shift_id": turno, "profile_id": perfil}
