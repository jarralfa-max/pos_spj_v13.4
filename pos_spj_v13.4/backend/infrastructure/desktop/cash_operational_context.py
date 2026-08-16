"""Desktop operational context resolver for the canonical Caja module.

The frontend must never fabricate cash register, drawer, terminal, shift or
sync-device identifiers. This resolver is owned by the desktop composition
root and translates the current session + canonical database state into the
explicit context consumed by ``CashRegisterPresenter``.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.cash_register.policies.workflow_policies import CashShiftLifecyclePolicy


_ACTIVE_SHIFT_STATUSES = tuple(status.value for status in CashShiftLifecyclePolicy.ACTIVE_STATUSES)


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
    """Resolve Caja active context from session and canonical tables only."""

    def __init__(self, connection, session, composition_root) -> None:
        self._connection = connection
        self._session = session
        self._composition_root = composition_root

    def active_shift_id(self) -> str | None:
        branch_id = self._branch_id()
        user_id = self._user_id()
        cached = getattr(self._composition_root, "active_cash_shift_id", None)
        if cached:
            row = self._current_active_cash_shift(
                branch_id=branch_id,
                cashier_user_id=user_id,
            )
            if row and row["id"] == str(cached):
                return str(cached)
        row = self._current_active_cash_shift(
            branch_id=branch_id,
            cashier_user_id=user_id,
        )
        if row:
            setattr(self._composition_root, "active_cash_shift_id", row["id"])
            return row["id"]
        return None

    def context(self) -> CashOperationalContext:
        branch_id = self._branch_id()
        cash_register_id = (
            self._root_value("active_cash_register_id")
            or self._first_active_cash_device(
                table="cash_registers",
                branch_id=branch_id,
            )
        )
        cash_drawer_id = (
            self._root_value("active_cash_drawer_id")
            or self._first_active_cash_device(
                table="cash_drawers",
                branch_id=branch_id,
                register_id=cash_register_id,
            )
        )
        pos_terminal_id = (
            self._root_value("active_pos_terminal_id")
            or self._first_active_cash_device(
                table="pos_terminals",
                branch_id=branch_id,
                register_id=cash_register_id,
            )
        )
        active_shift = (
            self._current_active_cash_shift(
                branch_id=branch_id,
                cashier_user_id=self._user_id(),
                register_id=cash_register_id,
            )
            or self._current_active_cash_shift(
                branch_id=branch_id,
                cashier_user_id=self._user_id(),
            )
        )
        if active_shift:
            cash_register_id = active_shift["register_id"]
            cash_drawer_id = active_shift["drawer_id"]
            pos_terminal_id = active_shift["terminal_id"]
            setattr(self._composition_root, "active_cash_shift_id", active_shift["id"])
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
            cash_shift_id=active_shift["id"] if active_shift else self.active_shift_id(),
            sync_device_id=sync_device_id,
        )

    def active_count_context(self) -> tuple[str, str, str] | None:
        count_id = self._root_value("active_cash_count_id")
        branch_id = self._branch_id()
        user_id = self._user_id()
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

    def _first_active_cash_device(
        self,
        *,
        table: str,
        branch_id: str | None,
        register_id: str | None = None,
    ) -> str | None:
        if table not in {"cash_registers", "cash_drawers", "pos_terminals"}:
            raise ValueError("Unsupported Caja device table")
        if not branch_id:
            return None
        if register_id and table in {"cash_drawers", "pos_terminals"}:
            row = self._connection.execute(
                f"""SELECT id FROM {table}
                WHERE branch_id=? AND register_id=? AND status='ACTIVE'
                ORDER BY updated_at DESC,id LIMIT 1""",
                (branch_id, register_id),
            ).fetchone()
        else:
            row = self._connection.execute(
                f"""SELECT id FROM {table}
                WHERE branch_id=? AND status='ACTIVE'
                ORDER BY updated_at DESC,id LIMIT 1""",
                (branch_id,),
            ).fetchone()
        return str(row[0]) if row else None

    def _current_active_cash_shift(
        self,
        *,
        branch_id: str | None,
        cashier_user_id: str | None = None,
        register_id: str | None = None,
        drawer_id: str | None = None,
        terminal_id: str | None = None,
    ) -> dict[str, str] | None:
        if not branch_id:
            return None
        placeholders = ",".join("?" for _ in _ACTIVE_SHIFT_STATUSES)
        params: list[str] = [str(branch_id), *_ACTIVE_SHIFT_STATUSES]
        filters = [f"branch_id=? AND status IN ({placeholders})"]
        if cashier_user_id:
            filters.append("cashier_user_id=?")
            params.append(str(cashier_user_id))
        if register_id:
            filters.append("register_id=?")
            params.append(str(register_id))
        if drawer_id:
            filters.append("drawer_id=?")
            params.append(str(drawer_id))
        if terminal_id:
            filters.append("terminal_id=?")
            params.append(str(terminal_id))
        cursor = self._connection.execute(
            f"""SELECT id,branch_id,register_id,drawer_id,terminal_id,cashier_user_id,status
            FROM cash_shifts
            WHERE {' AND '.join(filters)}
            ORDER BY opened_at DESC,id DESC LIMIT 1""",
            tuple(params),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((item[0] for item in cursor.description), map(str, row)))
