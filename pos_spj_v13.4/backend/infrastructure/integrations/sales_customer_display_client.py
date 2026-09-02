"""SalesCustomerDisplayClient — Sales' integration point onto the real
Customer Display capability (SET-17 cutover). Mirrors
`sales_sweepstakes_client.py`'s shape: thin, delegates entirely to the
owning context's real domain (`backend/domain/customer_display/`) and
its real repositories.

**Lazy bootstrap, same discipline SET-16's `next_number()` established**:
no `CustomerDisplay` or `DisplayLayout` exists in a fresh install — both
get a real, persisted default on first use rather than requiring new
admin CRUD this round (Configuración's own "Pantalla del cliente" page
is already real, just read-only — whatever gets bootstrapped here shows
up there unmodified). `LOGO` stays disabled in the default layout — no
real logo-asset infrastructure exists yet (confirmed by the Empresa
round), so this never fabricates content for a feature that isn't real.

**Correction to the original SET-17 plan, found while writing this
round's integration tests**: `customer_displays.workstation_id` has a
real `REFERENCES workstations(id)` foreign key (migration 217) — minting
an orphan UUIDv7 with no backing `Workstation` row, as the plan
originally proposed, fails loudly with `sqlite3.IntegrityError` the
instant `foreign_keys` enforcement is on (it always is in this
codebase). A `Workstation` itself FKs to `sucursales(id)` (migration
210) — but every live sale already requires a real `branch_id`
(`SalesPosPresenter.current_branch_id()`, sourced from the active
session), so that branch is guaranteed to exist. When no active
`Workstation` exists yet, this client bootstraps one real, minimal row
against that already-real branch — not a second orphan — mirroring the
exact same "bootstrap a real persisted row on first use" discipline as
the `DisplayLayout`/`CustomerDisplay` bootstraps right below. Only when
no `branch_id` is available at all (defensive — should not happen for a
live sales session) does this raise `CustomerDisplayBootstrapError`
rather than attempt an insert already known to violate the FK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.domain.customer_display.entities.customer_display import CustomerDisplay
from backend.domain.customer_display.entities.display_layout import DisplayLayout
from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.customer_display.policies.display_layout_resolution_policy import resolve_layout
from backend.domain.customer_display.policies.display_state_push_policy import push_state
from backend.domain.customer_display.value_objects.display_section import DisplaySection
from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationType
from backend.infrastructure.db.repositories.customer_display.customer_display_repository import (
    SqliteCustomerDisplayRepository,
)
from backend.infrastructure.db.repositories.customer_display.display_layout_repository import (
    SqliteDisplayLayoutRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import SqliteWorkstationRepository
from backend.shared.ids import new_uuid

if TYPE_CHECKING:
    from backend.application.sales.dto import CustomerDisplayStateDTO
    from backend.domain.customer_display.gateway_ports import CustomerDisplayGatewayPort

_DEFAULT_DISPLAY_NAME = "Pantalla del cliente"
_DEFAULT_WORKSTATION_NAME = "Estación POS"


class CustomerDisplayBootstrapError(Exception):
    """Raised when no `CustomerDisplay` exists yet and no `branch_id` was
    given to bootstrap the `Workstation` it must reference — a defensive
    guard, not expected in real use (a live sale always carries a real
    branch)."""

# All real CustomerDisplaySectionCode values, enabled by default except
# LOGO (no real logo-asset infrastructure exists yet — never fabricated).
_DEFAULT_SECTION_ORDER = (
    CustomerDisplaySectionCode.CUSTOMER_NAME,
    CustomerDisplaySectionCode.ITEMS,
    CustomerDisplaySectionCode.SUBTOTAL,
    CustomerDisplaySectionCode.DISCOUNT,
    CustomerDisplaySectionCode.TOTAL,
    CustomerDisplaySectionCode.MESSAGE,
    CustomerDisplaySectionCode.LOGO,
)
_DISABLED_BY_DEFAULT = {CustomerDisplaySectionCode.LOGO}


class SalesCustomerDisplayClient:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._displays = SqliteCustomerDisplayRepository(connection)
        self._layouts = SqliteDisplayLayoutRepository(connection)

    def push_sale_state(
        self, gateway: "CustomerDisplayGatewayPort", *, state: "CustomerDisplayStateDTO | None",
        branch_id: str | None = None,
    ) -> None:
        mode = CustomerDisplayMode(state.screen) if state is not None else CustomerDisplayMode.IDLE
        display = self._resolve_or_bootstrap_display(branch_id)
        layout = self._resolve_or_bootstrap_layout(mode)

        display.set_mode(mode)
        self._displays.save(display)
        self._connection.commit()

        push_state(gateway, display=display, layout=layout, content=_build_content(state))

    # internals -----------------------------------------------------------------
    def _resolve_or_bootstrap_display(self, branch_id: str | None) -> CustomerDisplay:
        active = self._displays.list_active()
        if active:
            return active[0]
        workstation_id = self._resolve_or_bootstrap_workstation_id(branch_id)
        display = CustomerDisplay.create(workstation_id=workstation_id, name=_DEFAULT_DISPLAY_NAME)
        self._displays.save(display)
        self._connection.commit()
        return display

    def _resolve_or_bootstrap_workstation_id(self, branch_id: str | None) -> str:
        workstation_repo = SqliteWorkstationRepository(self._connection)
        workstations = workstation_repo.list_active()
        if workstations:
            return workstations[0].id
        if not branch_id:
            raise CustomerDisplayBootstrapError(
                "No hay Workstation activa y no se proporcionó branch_id para crear una.")
        workstation = Workstation.create(
            branch_id=branch_id, code=f"POS-{new_uuid()[:8]}", name=_DEFAULT_WORKSTATION_NAME,
            workstation_type=WorkstationType.POS,
        )
        workstation_repo.save(workstation)
        self._connection.commit()
        return workstation.id

    def _resolve_or_bootstrap_layout(self, mode: CustomerDisplayMode) -> DisplayLayout:
        existing = self._layouts.get_active_for_mode(mode)
        if existing is not None:
            return existing
        sections = tuple(
            DisplaySection.create(code=code, order=order, enabled=code not in _DISABLED_BY_DEFAULT)
            for order, code in enumerate(_DEFAULT_SECTION_ORDER)
        )
        layout = DisplayLayout.create(mode=mode, sections=sections)
        self._layouts.save(layout)
        self._connection.commit()
        return resolve_layout([layout], mode)


def _build_content(state: "CustomerDisplayStateDTO | None") -> dict:
    if state is None:
        return {}
    content: dict = {
        CustomerDisplaySectionCode.CUSTOMER_NAME.value: state.customer_name or "",
        CustomerDisplaySectionCode.ITEMS.value: [
            {
                "name": line.name, "quantity": str(line.quantity), "unit_price": str(line.unit_price),
                "line_total": str(line.line_total),
            }
            for line in state.lines
        ],
        CustomerDisplaySectionCode.SUBTOTAL.value: str(state.subtotal),
        CustomerDisplaySectionCode.DISCOUNT.value: str(state.discount_total),
        CustomerDisplaySectionCode.TOTAL.value: str(state.total),
        CustomerDisplaySectionCode.MESSAGE.value: state.message,
    }
    return content
