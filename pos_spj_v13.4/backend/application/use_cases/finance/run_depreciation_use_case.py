"""RunDepreciationUseCase — corrida registrada de depreciación por periodo (§17).

La depreciación acumulada sólo cambia por una corrida: cada corrida queda en
``depreciation_runs`` con su detalle por activo y su asiento. Un activo se
deprecia a lo más una vez por periodo (restricción única + idempotencia del
asiento): repetir la corrida no duplica nada; una corrida posterior del mismo
periodo sólo incluye lo que faltaba (p. ej. un activo capitalizado después).
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.domain.finance.enums import AuditAction, JournalType, PostingPurpose
from backend.domain.finance.services.depreciation_service import DepreciationDomainService
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class RunDepreciationUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()
        self._domain = DepreciationDomainService()

    def execute(self, connection, *, year: int, month: int, operation_id: str,
                created_by: str | None = None) -> list[str]:
        period_code = f"{year:04d}-{month:02d}"
        entry_date = date(year, month, calendar.monthrange(year, month)[1])
        with FinanceUnitOfWork(connection) as uow:
            previous = uow.fixed_assets.find_run_by_operation_id(operation_id)
            if previous is not None:
                return [row["journal_entry_id"]
                        for row in uow.fixed_assets.run_lines(period_code)]
            already = {row["fixed_asset_id"] for row in uow.fixed_assets.run_lines(period_code)}
            lines: list = []
            for asset in self._domain.depreciable_assets(uow.fixed_assets.list_capitalized(),
                                                         period_code):
                if asset.id in already:
                    continue
                amount = self._domain.apply(asset, period_code)
                if amount.is_zero():
                    continue
                entry = self._engine.post(
                    uow, JournalType.FIXED_ASSETS, entry_date,
                    f"Depreciación {period_code} — {asset.name}",
                    PostingReference("finance", f"{asset.id}:{period_code}",
                                     PostingPurpose.DEPRECIATION, new_uuid()),
                    [LineSpec(asset.depreciation_expense_account_id, debit=amount,
                              description=f"Gasto por depreciación {asset.name}",
                              branch_id=asset.branch_id, cost_center_id=asset.cost_center_id,
                              project_id=asset.project_id),
                     LineSpec(asset.accumulated_depreciation_account_id, credit=amount,
                              description="Depreciación acumulada", branch_id=asset.branch_id)],
                    branch_id=asset.branch_id, created_by=created_by)
                uow.fixed_assets.update(asset)
                lines.append((asset.id, amount, entry.id))
            if not lines:
                return []
            currency = lines[0][1].currency_code
            run_id = uow.fixed_assets.save_run(period_code=period_code, lines=lines,
                                               run_by=created_by, operation_id=operation_id,
                                               currency_code=currency)
            total = sum((amount.amount for _, amount, _ in lines), Decimal("0"))
            uow.audit(AuditAction.DEPRECIATION_RUN, entity_type="depreciation_run",
                      entity_id=run_id, operation_id=operation_id, user_id=created_by,
                      after={"period": period_code, "assets": len(lines),
                             "total": format(total, "f")})
            publish_finance_event(uow, EventName.DEPRECIATION_POSTED, {
                "depreciation_run_id": run_id, "period": period_code, "entries": len(lines),
                "total": format(total, "f"),
            }, operation_id=operation_id, entity_id=run_id)
            return [entry_id for _, _, entry_id in lines]
