"""MeatProcessingUnitOfWork — one transaction boundary for the meat processing
context. Mirrors backend/infrastructure/db/repositories/inventory/unit_of_work.py.

Repositories never commit; the UoW commits on clean exit and rolls back on any
exception. Events enqueued in the outbox are published only after a successful
commit.

When ``owns_transaction=False`` the UoW writes on a connection whose transaction
boundary is owned by an *outer* flow (e.g. Inventory posting a consumption inside
its own SAVEPOINT and committing consumption + stock atomically). In that mode
``commit()``/``rollback()`` do NOT touch the connection.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.meat_processing.equipment_assignment_repository import (
    EquipmentAssignmentRepository,
)
from backend.infrastructure.db.repositories.meat_processing.material_consumption_repository import (
    MaterialConsumptionRepository,
)
from backend.infrastructure.db.repositories.meat_processing.material_requirement_repository import (
    MaterialRequirementRepository,
)
from backend.infrastructure.db.repositories.meat_processing.operator_assignment_repository import (
    OperatorAssignmentRepository,
)
from backend.infrastructure.db.repositories.meat_processing.packaging_execution_repository import (
    PackagingExecutionRepository,
)
from backend.infrastructure.db.repositories.meat_processing.process_execution_repository import (
    ProcessExecutionRepository,
)
from backend.infrastructure.db.repositories.meat_processing.process_genealogy_link_repository import (
    ProcessGenealogyLinkRepository,
)
from backend.infrastructure.db.repositories.meat_processing.process_incident_repository import (
    ProcessIncidentRepository,
)
from backend.infrastructure.db.repositories.meat_processing.process_output_repository import (
    ProcessOutputRepository,
)
from backend.infrastructure.db.repositories.meat_processing.process_step_execution_repository import (
    ProcessStepExecutionRepository,
)
from backend.infrastructure.db.repositories.meat_processing.process_weighing_repository import (
    ProcessWeighingRepository,
)
from backend.infrastructure.db.repositories.meat_processing.processing_batch_repository import (
    ProcessingBatchRepository,
)
from backend.infrastructure.db.repositories.meat_processing.processing_order_repository import (
    ProcessingOrderRepository,
)
from backend.infrastructure.db.repositories.meat_processing.production_area_repository import (
    ProductionAreaRepository,
)
from backend.infrastructure.db.repositories.meat_processing.production_equipment_repository import (
    ProductionEquipmentRepository,
)
from backend.infrastructure.db.repositories.meat_processing.production_label_repository import (
    ProductionLabelRepository,
)
from backend.infrastructure.db.repositories.meat_processing.production_station_repository import (
    ProductionStationRepository,
)
from backend.infrastructure.db.repositories.meat_processing.rework_order_repository import (
    ReworkOrderRepository,
)
from backend.infrastructure.db.repositories.meat_processing.support_repositories import (
    MeatProcessingAuditRepository,
    MeatProcessingAuthorizationLogRepository,
    MeatProcessingOutboxRepository,
    MeatProcessingProcessedEventRepository,
)
from backend.infrastructure.db.repositories.meat_processing.work_center_repository import (
    WorkCenterRepository,
)
from backend.infrastructure.db.repositories.meat_processing.yield_reconciliation_repository import (
    YieldReconciliationRepository,
)


class MeatProcessingUnitOfWork:
    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
        self.orders = ProcessingOrderRepository(connection)
        self.batches = ProcessingBatchRepository(connection)
        self.executions = ProcessExecutionRepository(connection)
        self.consumptions = MaterialConsumptionRepository(connection)
        self.outputs = ProcessOutputRepository(connection)
        self.weighings = ProcessWeighingRepository(connection)
        self.yield_reconciliations = YieldReconciliationRepository(connection)
        self.material_requirements = MaterialRequirementRepository(connection)
        self.operator_assignments = OperatorAssignmentRepository(connection)
        self.steps = ProcessStepExecutionRepository(connection)
        self.incidents = ProcessIncidentRepository(connection)
        self.packaging_executions = PackagingExecutionRepository(connection)
        self.production_labels = ProductionLabelRepository(connection)
        self.rework_orders = ReworkOrderRepository(connection)
        self.genealogy_links = ProcessGenealogyLinkRepository(connection)
        self.production_areas = ProductionAreaRepository(connection)
        self.work_centers = WorkCenterRepository(connection)
        self.production_stations = ProductionStationRepository(connection)
        self.equipment = ProductionEquipmentRepository(connection)
        self.equipment_assignments = EquipmentAssignmentRepository(connection)
        self.authorization_log = MeatProcessingAuthorizationLogRepository(connection)
        self.audit = MeatProcessingAuditRepository(connection)
        self.outbox = MeatProcessingOutboxRepository(connection)
        self.processed_events = MeatProcessingProcessedEventRepository(connection)
        self._completed = False

    def __enter__(self) -> "MeatProcessingUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        if self._owns_transaction:
            self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        if self._owns_transaction:
            rollback = getattr(self.connection, "rollback", None)
            if rollback is not None:
                rollback()
        self._completed = True
