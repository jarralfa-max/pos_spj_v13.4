"""Consumer-side integration ports for the Assets/EAM bounded context (ASSET-15, §28, §52-58).

Activos never administers suppliers, employees, device drivers, or file
storage — it only *consumes* lookups/gateways from the modules that own
those concerns (Compras, RRHH, Configuración/Device Management, Document
Output). These Protocols are the contracts Activos' application layer (a
later phase) depends on; the concrete adapters are implemented and wired by
whichever infrastructure/bootstrap layer composes the whole app, exactly the
same shape as ``whatsapp_service/erp/erp_ports.py``'s formal ports wrapping
``ERPBridge`` (see [[assets_eam_enterprise_transformation]] for that
precedent) — Activos wraps what other bounded contexts already expose,
it never reimplements their logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SupplierRef:
    """§28: Compras owns the supplier master. Activos only reads a thin ref
    for external maintenance providers (MaintenanceProviderType.EXTERNAL)."""

    id: str
    name: str
    active: bool


class SupplierLookupPort(Protocol):
    def find_by_id(self, supplier_id: str) -> SupplierRef | None: ...
    def search(self, query: str, *, limit: int = 20) -> list[SupplierRef]: ...


@dataclass(frozen=True, slots=True)
class EmployeeRef:
    """§56: RRHH owns the employee master. Activos reads a thin ref for
    custodians, responsible employees, technicians, drivers — never
    duplicates the employee record."""

    id: str
    name: str
    active: bool


class EmployeeLookupPort(Protocol):
    def find_by_id(self, employee_id: str) -> EmployeeRef | None: ...
    def search(self, query: str, *, limit: int = 20) -> list[EmployeeRef]: ...


class DeviceRegistrationLookupPort(Protocol):
    """§57: a physical asset (e.g. "báscula") may reference a device
    registration for its driver configuration, but Activos never manages the
    COM port / driver settings themselves — Device Management owns that."""

    def exists(self, device_registration_id: str) -> bool: ...


class DocumentStorageGatewayPort(Protocol):
    """§42-43: backs ``AssetDocument.storage_reference`` (ASSET-9) — Activos
    never stores a raw filesystem path, only the opaque reference this
    gateway returns."""

    def store(self, content: bytes, *, mime_type: str, filename: str) -> str: ...
    def retrieve(self, storage_reference: str) -> bytes: ...
    def delete(self, storage_reference: str) -> None: ...


class PrintJobGatewayPort(Protocol):
    """§49-51: tag/label and PDF report printing goes through Document
    Output's PrintJob abstraction — Activos never calls a printing library
    (e.g. FPDF) directly, unlike the legacy `modulos/activos.py`."""

    def submit(self, template_id: str, payload: dict) -> str: ...
    def get_status(self, print_job_id: str) -> str: ...
