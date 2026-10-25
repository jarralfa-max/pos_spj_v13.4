"""Puertos de Finanzas hacia otros contextos (implementados en infraestructura).

Finanzas no lee tablas de otros módulos desde sus casos de uso: la
composición le entrega estos adaptadores. Sin adaptador, el caso de uso no se
puede construir (no hay "fallback" que lea por su cuenta).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SupplierPaymentEligibility:
    eligible: bool
    reason: str = ""
    name: str = ""
    bank_account: str = ""


class SupplierDirectoryPort(Protocol):
    def payment_eligibility(self, supplier_id: str) -> SupplierPaymentEligibility: ...


@dataclass(frozen=True, slots=True)
class OperationalCloseStatus:
    """Lo que otros módulos dejaron pendiente de llegar al mayor en un periodo."""

    open_cash_shifts: int = 0
    pending_sales_events: int = 0
    pending_purchase_events: int = 0
    pending_payroll_events: int = 0
    pending_inventory_events: int = 0


class OperationalCloseSourcesPort(Protocol):
    def status(self, *, period_start: date, period_end: date) -> OperationalCloseStatus: ...


class NoOperationalSources:
    """Para un contexto financiero aislado (pruebas, herramientas): nada pendiente."""

    def status(self, *, period_start: date, period_end: date) -> OperationalCloseStatus:
        return OperationalCloseStatus()


class PartyDirectoryPort(Protocol):
    """Nombres visibles de clientes o proveedores para las pantallas de Finanzas."""

    def display_names(self, ids: list[str]) -> dict[str, str]: ...

    def search(self, text: str, limit: int = 20) -> list[dict]: ...
