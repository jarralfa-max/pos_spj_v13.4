"""Repository ports for the Customer Credit bounded context (§10). Protocol
only — implementation lives in
``backend/infrastructure/db/repositories/customer_credit/``. Mirrors
backend/domain/customer_service/repository_ports.py.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.customer_credit.entities.customer_credit_profile import CustomerCreditProfile


class CustomerCreditProfileRepositoryPort(Protocol):
    def save(self, profile: CustomerCreditProfile, *, operation_id: str | None = None) -> None: ...
    def update(self, profile: CustomerCreditProfile) -> None: ...
    def get(self, profile_id: str) -> CustomerCreditProfile | None: ...
    def get_by_customer_id(self, customer_id: str) -> CustomerCreditProfile | None: ...
    def get_by_operation_id(self, operation_id: str) -> CustomerCreditProfile | None: ...
    def list_by_status(self, status: str, *,
                        limit: int = 200, offset: int = 0) -> list[CustomerCreditProfile]: ...
