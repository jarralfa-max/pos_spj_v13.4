"""HRPresenter — the only gateway between the HR UI and the backend.

Receives ALREADY-CONSTRUCTED query services and use cases (wired in
``hr_routes``). It never touches SQL, connections, repositories or the app
container, and returns display-ready view models to the pages.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from backend.domain.hr.exceptions import HRDomainError
from backend.shared.ids import new_uuid
from frontend.desktop.modules.hr.hr_view_models import (
    KpiViewModel,
    TableViewModel,
    concept_es,
    leave_type_es,
    minutes_display,
    money_display,
    status_es,
)

logger = logging.getLogger("spj.hr.presenter")


class HRPresenter:
    def __init__(self, *, connection_provider, query_services: dict, use_cases: dict,
                 session_context=None) -> None:
        self._conn = connection_provider
        self._queries = query_services
        self._use_cases = use_cases
        self._session = session_context

    # ── helpers ───────────────────────────────────────────────────────────
    def _run(self, action, *args, **kwargs) -> tuple[bool, str]:
        try:
            result = action(*args, **kwargs)
            # Use cases return HRResult; a falsy .success means a handled failure.
            if result is not None and getattr(result, "success", True) is False:
                return False, getattr(result, "message", "Operación rechazada.")
            message = getattr(result, "message", None) or "Operación registrada correctamente."
            return True, message
        except HRDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("HRPresenter: unexpected error")
            return False, "Error inesperado; revise el log."

    def _actor(self) -> str:
        user_id = getattr(self._session, "user_id", None)
        return str(user_id) if user_id else "desktop"

    def _branch(self) -> str | None:
        branch = getattr(self._session, "branch_id", None)
        return str(branch) if branch else None

    @staticmethod
    def _today_iso() -> str:
        return date.today().isoformat()

    # ── overview ──────────────────────────────────────────────────────────
    def overview_kpis(self) -> list[KpiViewModel]:
        data = self._queries["dashboard"].overview(
            work_date=self._today_iso(), branch_id=self._branch())
        return [
            KpiViewModel("Empleados activos", str(data["active_employees"]), "primary"),
            KpiViewModel("Presentes hoy", str(data["present_today"]), "success"),
            KpiViewModel("Ausencias hoy", str(data["absences_today"]), "warning"),
            KpiViewModel("Retardos hoy", str(data["late_today"]), "warning"),
            KpiViewModel("Solicitudes pendientes", str(data["pending_requests"]), "primary"),
            KpiViewModel("Incidencias abiertas", str(data["pending_incidents"]), "danger"),
            KpiViewModel("Horas extra hoy",
                         minutes_display(data["overtime_minutes"]), "primary"),
        ]

    # ── employees ─────────────────────────────────────────────────────────
    def employees(self, *, search: str | None = None,
                  active_only: bool = True) -> TableViewModel:
        rows, ids = [], []
        for emp in self._queries["employees"].list_employees(
                branch_id=self._branch(), active_only=active_only, search=search):
            rows.append([
                emp["employee_code"],
                f"{emp['first_name']} {emp['last_name']}",
                emp.get("department_name") or "—",
                emp.get("position_name") or "—",
                emp.get("hire_date") or "",
                status_es(emp.get("employment_status")),
            ])
            ids.append(emp["id"])
        return TableViewModel(rows, ids)

    def create_employee(self, **fields) -> tuple[bool, str]:
        return self._run(
            self._use_cases["create_employee"].execute, self._conn(),
            actor_user_id=self._actor(), operation_id=new_uuid(), **fields)

    def deactivate_employee(self, employee_id: str, *, reason: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["deactivate_employee"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id,
            termination_date=date.today(), reason=reason, operation_id=new_uuid())

    # ── attendance ────────────────────────────────────────────────────────
    def workdays(self, *, work_date: str | None = None) -> TableViewModel:
        rows, ids = [], []
        for w in self._queries["attendance"].list_workdays(
                work_date=work_date, branch_id=self._branch()):
            rows.append([
                w["employee_name"], w["work_date"],
                (w["first_entry_at"] or "")[11:16] if w["first_entry_at"] else "—",
                (w["last_exit_at"] or "")[11:16] if w["last_exit_at"] else "—",
                minutes_display(w["worked_minutes"]),
                minutes_display(w["late_minutes"]),
                minutes_display(w["overtime_minutes"]),
                status_es(w["status"]),
            ])
            ids.append(w["id"])
        return TableViewModel(rows, ids)

    def register_manual_attendance(self, *, employee_id: str, punch_type: str,
                                   occurred_at: datetime, reason: str) -> tuple[bool, str]:
        branch = self._branch()
        if not branch:
            return False, "No hay sucursal en el contexto de sesión."
        return self._run(
            self._use_cases["manual_attendance"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id, branch_id=branch,
            punch_type=punch_type, occurred_at=occurred_at, reason=reason,
            operation_id=new_uuid())

    def pending_adjustments(self) -> TableViewModel:
        rows, ids = [], []
        for adj in self._queries["attendance"].pending_adjustments():
            rows.append([adj["employee_name"], adj["field_name"],
                         adj.get("previous_value") or "—", adj["requested_value"],
                         adj.get("reason") or "", status_es(adj["status"])])
            ids.append(adj["id"])
        return TableViewModel(rows, ids)

    def resolve_adjustment(self, adjustment_id: str, *, approve: bool) -> tuple[bool, str]:
        return self._run(
            self._use_cases["approve_adjustment"].execute, self._conn(),
            actor_user_id=self._actor(), adjustment_id=adjustment_id,
            operation_id=new_uuid(), approve=approve)

    # ── schedules / shifts ────────────────────────────────────────────────
    def shifts(self) -> TableViewModel:
        rows, ids = [], []
        for shift in self._queries["shifts"].list_active(branch_id=self._branch()):
            rows.append([shift["name"], (shift["start_time"] or "")[:5],
                         (shift["end_time"] or "")[:5],
                         minutes_display(shift["break_minutes"]),
                         minutes_display(shift["late_tolerance_minutes"])])
            ids.append(shift["id"])
        return TableViewModel(rows, ids)

    def create_shift(self, *, name, start_time, end_time, break_minutes,
                     late_tolerance_minutes) -> tuple[bool, str]:
        return self._run(
            self._use_cases["create_shift"].execute, self._conn(),
            actor_user_id=self._actor(), name=name, start_time=start_time,
            end_time=end_time, break_minutes=break_minutes,
            late_tolerance_minutes=late_tolerance_minutes, branch_id=self._branch(),
            operation_id=new_uuid())

    def assign_shift(self, *, employee_id, work_shift_id, effective_from,
                     weekdays) -> tuple[bool, str]:
        return self._run(
            self._use_cases["assign_shift"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id,
            work_shift_id=work_shift_id, effective_from=effective_from,
            weekdays=weekdays, branch_id=self._branch(), operation_id=new_uuid())

    # ── leave ─────────────────────────────────────────────────────────────
    def leave_requests(self, *, status: str | None = None) -> TableViewModel:
        rows, ids = [], []
        for req in self._queries["leave"].list_requests(status=status):
            rows.append([req["employee_name"], leave_type_es(req["leave_type"]),
                         req["start_date"], req["end_date"], str(req["requested_days"]),
                         status_es(req["status"])])
            ids.append(req["id"])
        return TableViewModel(rows, ids)

    def request_leave(self, *, employee_id, leave_type, start_date, end_date,
                      reason) -> tuple[bool, str]:
        branch = self._branch()
        if not branch:
            return False, "No hay sucursal en el contexto de sesión."
        return self._run(
            self._use_cases["request_leave"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id, branch_id=branch,
            leave_type=leave_type, start_date=start_date, end_date=end_date,
            reason=reason, operation_id=new_uuid())

    def resolve_leave(self, leave_id: str, *, approve: bool) -> tuple[bool, str]:
        return self._run(
            self._use_cases["approve_leave"].execute, self._conn(),
            actor_user_id=self._actor(), leave_id=leave_id, operation_id=new_uuid(),
            approve=approve)

    # ── payroll ───────────────────────────────────────────────────────────
    def payroll_runs(self) -> TableViewModel:
        rows, ids = [], []
        for run in self._queries["payroll"].list_runs():
            totals = self._queries["payroll"].run_totals(run["id"])
            rows.append([f"{run['period_start']} → {run['period_end']}",
                         money_display(totals["gross"]),
                         money_display(totals["deductions"]),
                         money_display(totals["net"]), status_es(run["status"])])
            ids.append(run["id"])
        return TableViewModel(rows, ids)

    def payroll_lines(self, payroll_run_id: str) -> TableViewModel:
        rows = [
            [line["employee_name"], concept_es(line["concept"]),
             "Deducción" if line["is_deduction"] else "Percepción",
             money_display(line["amount"])]
            for line in self._queries["payroll"].run_lines(payroll_run_id)
        ]
        return TableViewModel(rows, [])

    def generate_payroll(self, *, period_start: date, period_end: date) -> tuple[bool, str]:
        return self._run(
            self._use_cases["generate_payroll"].execute, self._conn(),
            actor_user_id=self._actor(), period_start=period_start,
            period_end=period_end, operation_id=new_uuid(), branch_id=self._branch())

    def authorize_payroll(self, payroll_run_id: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["authorize_payroll"].execute, self._conn(),
            actor_user_id=self._actor(), payroll_run_id=payroll_run_id,
            operation_id=new_uuid())

    def pay_payroll(self, payroll_run_id: str, *, payment_method: str = "CASH") -> tuple[bool, str]:
        return self._run(
            self._use_cases["pay_payroll"].execute, self._conn(),
            actor_user_id=self._actor(), payroll_run_id=payroll_run_id,
            payment_method=payment_method, operation_id=new_uuid())

    def cancel_payroll(self, payroll_run_id: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["cancel_payroll"].execute, self._conn(),
            actor_user_id=self._actor(), payroll_run_id=payroll_run_id,
            operation_id=new_uuid())

    # ── settings (catalogs) ───────────────────────────────────────────────
    def create_department(self, *, code: str, name: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["catalog"].create_department, self._conn(),
            actor_user_id=self._actor(), code=code, name=name, branch_id=self._branch())

    def create_position(self, *, code: str, name: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["catalog"].create_position, self._conn(),
            actor_user_id=self._actor(), code=code, name=name)

    def employee_options(self) -> list[tuple[str, str]]:
        return [(emp["id"], f"{emp['employee_code']} — {emp['first_name']} {emp['last_name']}")
                for emp in self._queries["employees"].list_employees(
                    branch_id=self._branch(), active_only=True, limit=500)]

    def shift_options(self) -> list[tuple[str, str]]:
        return [(shift.id, shift.name)
                for shift in self._queries["shifts"].list_active(branch_id=self._branch())]
