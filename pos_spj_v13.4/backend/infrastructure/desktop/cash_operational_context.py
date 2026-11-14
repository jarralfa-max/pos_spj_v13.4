"""Desktop operational context resolver for the canonical Caja module.

The frontend must never fabricate cash register, drawer, terminal, shift or
sync-device identifiers. This resolver is owned by the desktop composition
root and translates the current session + canonical database state into the
explicit context consumed by ``CashRegisterPresenter``.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.cash_register.active_shift_resolver import (
    ActiveShift,
    ActiveShiftResolver,
)


@dataclass(frozen=True, slots=True)
class CashOperationalContext:
    branch_id: str | None = None
    cash_register_id: str | None = None
    cash_drawer_id: str | None = None
    pos_terminal_id: str | None = None
    cash_shift_id: str | None = None
    sync_device_id: str | None = None

    def as_presenter_dict(self) -> dict[str, object | None]:
        return {
            "branch_id": self.branch_id,
            "cash_register_id": self.cash_register_id,
            "cash_drawer_id": self.cash_drawer_id,
            "pos_terminal_id": self.pos_terminal_id,
            "cash_shift_id": self.cash_shift_id,
            "sync_device_id": self.sync_device_id,
        }


class DesktopCashOperationalContextResolver:
    """Resolve Caja active context from session and canonical tables only.

    SDLC-ARQ-SHIFT-001: el turno activo sale de `ActiveShiftResolver` (la
    misma fuente que POS, devoluciones y cierre financiero), sin caché en el
    `composition_root`: cada consulta lee la base."""

    def __init__(self, connection, session, composition_root) -> None:
        self._connection = connection
        self._session = session
        self._composition_root = composition_root
        self._shifts = ActiveShiftResolver(connection)

    def active_shift_id(self) -> str | None:
        shift = self._active_shift()
        return shift.id if shift else None

    def _active_shift(self) -> ActiveShift | None:
        branch_id, user_id = self._branch_id(), self._user_id()
        if not branch_id or not user_id:
            return None
        return self._shifts.for_cashier(cashier_user_id=user_id, branch_id=branch_id)

    def available_registers(self) -> list[dict]:
        """Cajas ACTIVAS de la sucursal con su cajón y terminal activos, y si
        ya las ocupa un turno (auditoría CJA-07: se elige por nombre, nunca «la
        primera activa»)."""
        branch_id = self._branch_id()
        if not branch_id:
            return []
        rows = self._connection.execute(
            """SELECT r.id, r.name,
                      (SELECT d.id FROM cash_drawers d WHERE d.register_id=r.id
                         AND d.branch_id=r.branch_id AND d.status='ACTIVE'
                       ORDER BY d.updated_at DESC, d.id LIMIT 1),
                      (SELECT d.name FROM cash_drawers d WHERE d.register_id=r.id
                         AND d.branch_id=r.branch_id AND d.status='ACTIVE'
                       ORDER BY d.updated_at DESC, d.id LIMIT 1),
                      (SELECT t.id FROM pos_terminals t WHERE t.register_id=r.id
                         AND t.branch_id=r.branch_id AND t.status='ACTIVE'
                       ORDER BY t.updated_at DESC, t.id LIMIT 1),
                      (SELECT t.name FROM pos_terminals t WHERE t.register_id=r.id
                         AND t.branch_id=r.branch_id AND t.status='ACTIVE'
                       ORDER BY t.updated_at DESC, t.id LIMIT 1)
               FROM cash_registers r
               WHERE r.branch_id=? AND r.status='ACTIVE' ORDER BY r.name""",
            (branch_id,)).fetchall()
        busy = self._shifts.busy_register_ids(branch_id=branch_id)
        return [{"register_id": str(r[0]), "register_name": str(r[1] or ""),
                 "drawer_id": r[2], "drawer_name": str(r[3] or ""),
                 "terminal_id": r[4], "terminal_name": str(r[5] or ""),
                 "busy": str(r[0]) in busy}
                for r in rows if r[2] and r[4]]

    def _chosen_register(self) -> dict | None:
        """La caja elegida en esta estación si sigue siendo válida (de la
        sucursal, activa y libre); si no, la ÚNICA libre; si hay varias, ninguna
        (el cajero elige). Antes: la primera activa, aunque fuera de otra
        persona o de otra sucursal."""
        options = [o for o in self.available_registers() if not o["busy"]]
        chosen = self._root_value("active_cash_register_id")
        match = next((o for o in options if o["register_id"] == chosen), None)
        if match is not None:
            return match
        return options[0] if len(options) == 1 else None

    def choose_register(self, register_id: str | None) -> None:
        setattr(self._composition_root, "active_cash_register_id", register_id or None)

    def context(self) -> CashOperationalContext:
        branch_id = self._branch_id()
        chosen = self._chosen_register()
        cash_register_id = chosen["register_id"] if chosen else None
        cash_drawer_id = chosen["drawer_id"] if chosen else None
        pos_terminal_id = chosen["terminal_id"] if chosen else None
        active_shift = self._active_shift()
        if active_shift:
            cash_register_id = active_shift.register_id
            cash_drawer_id = active_shift.drawer_id
            pos_terminal_id = active_shift.terminal_id
        sync_device_id = (
            self._root_value("active_cash_sync_device_id")
            or self._session_value("active_cash_sync_device_id")
            or self._session_value("device_id")
            or pos_terminal_id
            or cash_register_id
        )
        return CashOperationalContext(
            branch_id=branch_id,
            cash_register_id=cash_register_id,
            cash_drawer_id=cash_drawer_id,
            pos_terminal_id=pos_terminal_id,
            cash_shift_id=active_shift.id if active_shift else None,
            sync_device_id=sync_device_id,
        )

    def active_count_context(self) -> tuple[str, str, str] | None:
        count_id = self._root_value("active_cash_count_id")
        branch_id = self._branch_id()
        user_id = self._user_id()
        if not count_id and branch_id and user_id:
            # El conteo abierto vive en la base, no sólo en memoria: si Caja se
            # reabre a mitad del arqueo, el cajero debe poder continuarlo.
            shift_id = self.active_shift_id()
            row = self._connection.execute(
                "SELECT id FROM cash_counts WHERE shift_id=? AND branch_id=? AND status='OPEN'",
                (shift_id, branch_id),
            ).fetchone() if shift_id else None
            if row is not None:
                count_id = str(row[0])
                setattr(self._composition_root, "active_cash_count_id", count_id)
        if count_id and branch_id and user_id:
            return str(count_id), branch_id, user_id
        return None

    def _branch_id(self) -> str | None:
        return (
            self._session_value("active_branch_id")
            or self._session_value("branch_id")
            or self._root_value("sucursal_id")
        )

    def _user_id(self) -> str | None:
        return self._session_value("user_id")

    def _session_value(self, name: str) -> str | None:
        value = getattr(self._session, name, None)
        text = str(value or "").strip()
        return text or None

    def _root_value(self, name: str) -> str | None:
        value = getattr(self._composition_root, name, None)
        text = str(value or "").strip()
        return text or None
