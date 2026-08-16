"""NavigationIntent — canonical cross-module navigation payload (CRM-32,
master prompt Fase 3: "Customer 360 + conectividad entre ventanas").

The problem this solves: `frontend/desktop/modules/customers_crm/
customers_crm_workspace.py` already has a real intra-module navigation
mechanism (`select_route(route_id)` + a `QStackedWidget`) — CRM-14 through
CRM-18 built it. What's missing is a way to jump OUT of one module (e.g.
Customer Profile) INTO another (e.g. Ventas) while carrying the customer
that was already selected, so the destination screen doesn't make the
user search for the same customer again.

`interfaz/main_window.py` already has the primitive this reuses: modules
that expose an `abrir_modulo` PyQt signal get auto-wired by `_conectar()`
to switch `self.stack`'s current index. That signal only carries a bare
module code (`pyqtSignal(str)`), with no room for a payload — extending
its signature would break every existing `abrir_modulo.connect(lambda k:
...)` wiring across every module that already uses it. `NavigationIntent`
plus a NEW, additive `navigation_requested = pyqtSignal(object)` signal
(see `customer_profile_page.py`) is the payload-carrying sibling of that
same mechanism — never a competing, parallel navigation system.

Deliberately NOT a PyQt object — a plain dataclass, constructible and
testable without a QApplication, same discipline as
`frontend/desktop/components`'s other value objects (e.g. `ColumnSpec`).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NavigationIntent:
    """route: a stable string key (e.g. ``"sales.new"``) resolved by the
    receiving shell (today: `interfaz/main_window.py`'s
    ``_NAVIGATION_ROUTES``) to a concrete module code.

    context: whatever the destination screen needs to pick up where the
    source left off. Minimally ``{"customer_id": ...}`` — the Customer
    Master UUID, not any module's own legacy identifier; each destination
    is responsible for resolving that id into whatever its own bounded
    context needs (see ``ModuloVentas.aplicar_contexto`` for the
    legacy-bridge resolution this requires for Ventas specifically)."""

    route: str
    context: dict = field(default_factory=dict)
