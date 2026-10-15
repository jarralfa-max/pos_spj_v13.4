"""HRPresenter — the only gateway between the HR UI and the backend.

Receives ALREADY-CONSTRUCTED query services and use cases (wired in
``hr_routes``). It never touches SQL, connections, repositories or the app
container, and returns display-ready view models to the pages.

Auditoría RRHH cebf67a:
- HR-01: el actor es el usuario de la sesión — sin sesión no hay actor (antes
  se escribía "desktop") — y cada lectura exige su permiso ``RRHH.*``.
- HR-02: la sucursal sale de la sesión viva (``active_branch_id``); el
  presentador leía ``branch_id``, que la sesión real no tiene, así que NUNCA
  filtraba y la asistencia manual y las solicitudes fallaban siempre.
- HR-20: el alta lleva la sucursal autorizada de la sesión.
- HR-21: las opciones de turno se arman desde las filas (dict) del servicio.
- HR-24: "hoy" es el de la sucursal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

from backend.application.hr.session_authorization import session_branch_id
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import HRPermission
from backend.shared.ids import new_uuid
from frontend.desktop.modules.hr.hr_view_models import (
    CREDENTIAL_ES,
    TIME_CLOCK_DRIVER_ES,
    TIME_CLOCK_KIND_ES,
    KpiViewModel,
    TableViewModel,
    concept_es,
    leave_type_es,
    local_clock,
    minutes_display,
    money_display,
    status_es,
)

logger = logging.getLogger("spj.hr.presenter")


@dataclass(frozen=True)
class HRCapabilities:
    employee_view: bool = False
    employee_create: bool = False
    employee_update: bool = False
    employee_deactivate: bool = False
    attendance_view: bool = False
    attendance_manual: bool = False
    attendance_adjust: bool = False
    attendance_approve: bool = False
    shift_manage: bool = False
    leave_view: bool = False
    leave_request: bool = False
    leave_approve: bool = False
    payroll_view: bool = False
    payroll_generate: bool = False
    payroll_authorize: bool = False
    payroll_pay: bool = False
    payroll_cancel: bool = False
    payroll_receipt: bool = False
    payroll_complementary: bool = False
    payroll_reverse_payment: bool = False
    input_capture: bool = False
    input_approve: bool = False
    loan_grant: bool = False
    leave_balance_adjust: bool = False
    time_clock_manage: bool = False
    time_clock_punch: bool = False
    settings_manage: bool = False


_CAPABILITY_CODES = {
    "employee_view": HRPermission.EMPLOYEE_VIEW,
    "employee_create": HRPermission.EMPLOYEE_CREATE,
    "employee_update": HRPermission.EMPLOYEE_UPDATE,
    "employee_deactivate": HRPermission.EMPLOYEE_DEACTIVATE,
    "attendance_view": HRPermission.ATTENDANCE_VIEW,
    "attendance_manual": HRPermission.ATTENDANCE_MANUAL,
    "attendance_adjust": HRPermission.ATTENDANCE_ADJUST,
    "attendance_approve": HRPermission.ATTENDANCE_APPROVE_ADJUSTMENT,
    "shift_manage": HRPermission.SHIFT_MANAGE,
    "leave_view": HRPermission.LEAVE_VIEW,
    "leave_request": HRPermission.LEAVE_REQUEST,
    "leave_approve": HRPermission.LEAVE_APPROVE,
    "payroll_view": HRPermission.PAYROLL_VIEW,
    "payroll_generate": HRPermission.PAYROLL_GENERATE,
    "payroll_authorize": HRPermission.PAYROLL_AUTHORIZE,
    "payroll_pay": HRPermission.PAYROLL_PAY,
    "payroll_cancel": HRPermission.PAYROLL_CANCEL,
    "payroll_receipt": HRPermission.PAYROLL_RECEIPT,
    "payroll_complementary": HRPermission.PAYROLL_COMPLEMENTARY,
    "payroll_reverse_payment": HRPermission.PAYROLL_REVERSE_PAYMENT,
    "input_capture": HRPermission.PAYROLL_INPUT_CAPTURE,
    "input_approve": HRPermission.PAYROLL_INPUT_APPROVE,
    "loan_grant": HRPermission.LOAN_GRANT,
    "leave_balance_adjust": HRPermission.LEAVE_BALANCE_ADJUST,
    "time_clock_manage": HRPermission.TIME_CLOCK_MANAGE,
    "time_clock_punch": HRPermission.TIME_CLOCK_PUNCH,
    "settings_manage": HRPermission.SETTINGS_MANAGE,
}

PAYMENT_METHODS = (("CASH", "Efectivo"), ("BANK_TRANSFER", "Transferencia"),
                   ("CHECK", "Cheque"))


class _AllowAllForLegacyCallers:
    """Presentadores construidos a mano en pruebas antiguas sin política:
    las LECTURAS se muestran; los comandos los sigue validando cada caso de uso."""

    def has_permission(self, user_id, code) -> bool:
        return True


class HRPresenter:
    def __init__(self, *, connection_provider, query_services: dict, use_cases: dict,
                 session_context=None, authorization=None, clock=None) -> None:
        self._conn = connection_provider
        self._queries = query_services
        self._use_cases = use_cases
        self._session = session_context
        self._auth = authorization or _AllowAllForLegacyCallers()
        self._clock = clock or datetime.now

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
        return str(user_id).strip() if user_id else ""

    def _branch(self) -> str | None:
        return session_branch_id(self._session) or None

    def _today(self) -> date:
        return self._clock().date()

    def _today_iso(self) -> str:
        return self._today().isoformat()

    def _zone(self):
        return self._clock().tzinfo

    def can(self, permission_code: str) -> bool:
        actor = self._actor()
        return bool(actor) and bool(self._auth.has_permission(actor, permission_code))

    def capabilities(self) -> HRCapabilities:
        return HRCapabilities(**{name: self.can(code)
                                 for name, code in _CAPABILITY_CODES.items()})

    # ── overview ──────────────────────────────────────────────────────────
    def overview_kpis(self) -> list[KpiViewModel]:
        if not self.can(HRPermission.VIEW):
            return []
        data = self._queries["dashboard"].overview(
            work_date=self._today_iso(), branch_id=self._branch())
        return [
            KpiViewModel("Empleados vigentes", str(data["active_employees"]), "primary"),
            KpiViewModel("En turno ahora", str(data.get("on_shift_now", 0)), "success"),
            KpiViewModel("Jornadas terminadas", str(data.get("finished_today", 0)), "success"),
            KpiViewModel("Faltas hoy", str(data["absences_today"]), "warning"),
            KpiViewModel("Ausencias autorizadas",
                         str(data.get("authorized_absences_today", 0)), "primary"),
            KpiViewModel("Retardos hoy", str(data["late_today"]), "warning"),
            KpiViewModel("Solicitudes pendientes", str(data["pending_requests"]), "primary"),
            KpiViewModel("Incidencias abiertas", str(data["pending_incidents"]), "danger"),
            KpiViewModel("Horas extra hoy",
                         minutes_display(data["overtime_minutes"]), "primary"),
        ]

    # ── employees ─────────────────────────────────────────────────────────
    def employees(self, *, search: str | None = None, active_only: bool = True,
                  offset: int = 0, limit: int = 50) -> TableViewModel:
        if not self.can(HRPermission.EMPLOYEE_VIEW):
            return TableViewModel([], [])
        service = self._queries["employees"]
        rows, ids = [], []
        for emp in service.list_employees(
                branch_id=self._branch(), active_only=active_only, search=search,
                limit=limit, offset=offset):
            rows.append([
                emp["employee_code"],
                f"{emp['first_name']} {emp['last_name']}",
                emp.get("department_name") or "—",
                emp.get("position_name") or "—",
                emp.get("hire_date") or "",
                status_es(emp.get("employment_status")),
            ])
            ids.append(emp["id"])
        total = None
        counter = getattr(service, "count_employees", None)
        if counter is not None:
            total = counter(branch_id=self._branch(), active_only=active_only, search=search)
        return TableViewModel(rows, ids, total)

    def create_employee(self, **fields) -> tuple[bool, str]:
        branch = self._branch()
        if not branch:
            return False, "No hay sucursal en el contexto de sesión."
        fields.setdefault("branch_id", branch)
        operation_id = fields.pop("operation_id", None) or new_uuid()
        return self._run(
            self._use_cases["create_employee"].execute, self._conn(),
            actor_user_id=self._actor(), operation_id=operation_id, **fields)

    def employee_detail(self, employee_id: str) -> dict | None:
        if not self.can(HRPermission.EMPLOYEE_VIEW):
            return None
        service = self._queries["employees"]
        detail = service.get_employee(employee_id, branch_id=self._branch())
        if detail is None:
            return None
        detail = dict(detail)
        detail["salary_history"] = service.salary_history(employee_id)
        detail["linked_user"] = service.linked_user(employee_id)
        return detail

    def update_employee(self, employee_id: str, **fields) -> tuple[bool, str]:
        operation_id = fields.pop("operation_id", None) or new_uuid()
        return self._run(
            self._use_cases["update_employee"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id,
            operation_id=operation_id, **fields)

    def deactivate_employee(self, employee_id: str, *, reason: str,
                            termination_date: date | None = None) -> tuple[bool, str]:
        return self._run(
            self._use_cases["deactivate_employee"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id,
            termination_date=termination_date or self._today(), reason=reason,
            operation_id=new_uuid())

    def user_options(self) -> list[tuple[str, str]]:
        if not self.can(HRPermission.EMPLOYEE_UPDATE):
            return []
        return [(u["id"], u["usuario"]) for u in self._queries["employees"].linkable_users()]

    def link_user(self, employee_id: str, user_id: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["link_user"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id, user_id=user_id,
            operation_id=new_uuid())

    def catalog_options(self) -> dict:
        catalogs = self._queries["employees"].catalogs()
        return {"departments": [(d["id"], d["name"]) for d in catalogs["departments"]],
                "positions": [(p["id"], p["name"]) for p in catalogs["positions"]]}

    def search_employees(self, query: str, *, limit: int = 20) -> list[tuple[str, str]]:
        """HR-28: el selector busca por código/nombre DENTRO del alcance; no
        descarga el padrón completo."""
        if not self.can(HRPermission.EMPLOYEE_VIEW):
            return []
        return [(emp["id"], f"{emp['employee_code']} — {emp['first_name']} {emp['last_name']}")
                for emp in self._queries["employees"].list_employees(
                    branch_id=self._branch(), active_only=True, search=query or None,
                    limit=limit)]

    # ── attendance ────────────────────────────────────────────────────────
    def workdays(self, *, work_date: str | None = None, date_from: str | None = None,
                 date_to: str | None = None) -> TableViewModel:
        if not self.can(HRPermission.ATTENDANCE_VIEW):
            return TableViewModel([], [])
        rows, ids = [], []
        for w in self._queries["attendance"].list_workdays(
                work_date=work_date, branch_id=self._branch(), date_from=date_from,
                date_to=date_to):
            rows.append([
                w["employee_name"], w["work_date"],
                local_clock(w["first_entry_at"], self._zone()),
                local_clock(w["last_exit_at"], self._zone()),
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

    def workday_detail(self, workday_id: str) -> dict | None:
        if not self.can(HRPermission.ATTENDANCE_VIEW):
            return None
        return self._queries["attendance"].get_workday(workday_id, branch_id=self._branch())

    def request_adjustment(self, *, workday_id: str, field_name: str, requested_value,
                           reason: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["request_adjustment"].execute, self._conn(),
            actor_user_id=self._actor(), workday_id=workday_id, field_name=field_name,
            requested_value=requested_value, reason=reason, operation_id=new_uuid())

    def pending_adjustments(self) -> TableViewModel:
        if not self.can(HRPermission.ATTENDANCE_VIEW):
            return TableViewModel([], [])
        rows, ids = [], []
        for adj in self._queries["attendance"].pending_adjustments(branch_id=self._branch()):
            rows.append([adj["employee_name"], adj.get("work_date") or "",
                         "Entrada" if adj["field_name"] == "first_entry_at" else "Salida",
                         local_clock(adj.get("previous_value"), self._zone()),
                         local_clock(adj["requested_value"], self._zone()),
                         adj.get("reason") or "", status_es(adj["status"])])
            ids.append(adj["id"])
        return TableViewModel(rows, ids)

    def resolve_adjustment(self, adjustment_id: str, *, approve: bool) -> tuple[bool, str]:
        return self._run(
            self._use_cases["approve_adjustment"].execute, self._conn(),
            actor_user_id=self._actor(), adjustment_id=adjustment_id,
            operation_id=new_uuid(), approve=approve)

    def pending_cash_events(self) -> int:
        if not self.can(HRPermission.ATTENDANCE_VIEW):
            return 0
        lister = getattr(self._queries["attendance"], "pending_cash_events", None)
        return len(lister()) if lister else 0

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
        if not self.can(HRPermission.LEAVE_VIEW):
            return TableViewModel([], [])
        rows, ids = [], []
        for req in self._queries["leave"].list_requests(status=status,
                                                       branch_id=self._branch()):
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

    def cancel_leave(self, leave_id: str, *, reason: str | None = None) -> tuple[bool, str]:
        return self._run(
            self._use_cases["cancel_leave"].execute, self._conn(),
            actor_user_id=self._actor(), leave_id=leave_id, operation_id=new_uuid(),
            reason=reason)

    def vacation_balance_text(self, employee_id: str) -> str:
        query = self._queries.get("vacation_balance")
        if query is None or not self.can(HRPermission.LEAVE_VIEW):
            return ""
        balance = query.execute(self._conn(), employee_id=employee_id, on_date=self._today())
        if not balance:
            return ""
        cycles = "; ".join(f"ciclo {c['cycle_start']}: {c['remaining']} (vence {c['expires_on']})"
                           for c in balance["cycles"])
        return (f"Disponibles {balance['available']} día(s), apartados {balance['reserved']}"
                + (f" — {cycles}" if cycles else ""))

    def adjust_leave_balance(self, employee_id: str, *, days: int,
                             reason: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["adjust_leave_balance"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id, days=days, reason=reason,
            on_date=self._today())

    # ── payroll ───────────────────────────────────────────────────────────
    def payroll_runs(self) -> TableViewModel:
        if not self.can(HRPermission.PAYROLL_VIEW):
            return TableViewModel([], [])
        service = self._queries["payroll"]
        runs = service.list_runs(branch_id=self._branch())
        totals_for = getattr(service, "totals_by_run", None)
        totals = totals_for([r["id"] for r in runs]) if totals_for else {
            r["id"]: service.run_totals(r["id"]) for r in runs}
        rows, ids = [], []
        for run in runs:
            run_totals = totals.get(run["id"], {"gross": "0", "deductions": "0", "net": "0"})
            rows.append([f"{run['period_start']} → {run['period_end']}",
                         money_display(run_totals["gross"]),
                         money_display(run_totals["deductions"]),
                         money_display(run_totals["net"]), status_es(run["status"])])
            ids.append(run["id"])
        return TableViewModel(rows, ids)

    def payroll_lines(self, payroll_run_id: str) -> TableViewModel:
        if not self.can(HRPermission.PAYROLL_VIEW):
            return TableViewModel([], [])
        rows = [
            [line["employee_name"], concept_es(line["concept"]),
             "Deducción" if line["is_deduction"] else "Percepción",
             money_display(line["amount"]), line.get("notes") or ""]
            for line in self._queries["payroll"].run_lines(payroll_run_id)
        ]
        return TableViewModel(rows, [])

    def payroll_detail(self, payroll_run_id: str) -> dict | None:
        """HR-29: lo que el aprobador revisa — neto por empleado, conceptos,
        estado de pago y de contabilización."""
        if not self.can(HRPermission.PAYROLL_VIEW):
            return None
        service = self._queries["payroll"]
        run = service.get_run(payroll_run_id)
        if run is None or (self._branch() and run.get("branch_id")
                           and run["branch_id"] != self._branch()):
            return None
        employees = service.employee_summary(payroll_run_id)
        totals = service.run_totals(payroll_run_id)
        payment = service.payment(payroll_run_id)
        return {
            "run": run, "totals": totals, "status": status_es(run["status"]),
            "employees": TableViewModel(
                [[e["employee_code"], e["employee_name"], money_display(e["gross"]),
                  money_display(e["deductions"]), money_display(e["net"]),
                  "Neto negativo" if e["negative"] else ""] for e in employees],
                [e["employee_id"] for e in employees]),
            "negative_employees": sum(1 for e in employees if e["negative"]),
            "lines": self.payroll_lines(payroll_run_id),
            "payment": payment,
            "accounting": service.accounting_status(payroll_run_id) if payment else "",
        }

    def generate_payroll(self, *, period_start: date, period_end: date,
                         operation_id: str | None = None) -> tuple[bool, str]:
        return self._run(
            self._use_cases["generate_payroll"].execute, self._conn(),
            actor_user_id=self._actor(), period_start=period_start,
            period_end=period_end, operation_id=operation_id or new_uuid(),
            branch_id=self._branch(), today=self._today())

    def authorize_payroll(self, payroll_run_id: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["authorize_payroll"].execute, self._conn(),
            actor_user_id=self._actor(), payroll_run_id=payroll_run_id,
            operation_id=new_uuid())

    def pay_payroll(self, payroll_run_id: str, *, payment_method: str,
                    payment_reference: str | None = None,
                    operation_id: str | None = None) -> tuple[bool, str]:
        result = self._run(
            self._use_cases["pay_payroll"].execute, self._conn(),
            actor_user_id=self._actor(), payroll_run_id=payroll_run_id,
            payment_method=payment_method, payment_reference=payment_reference,
            operation_id=operation_id or new_uuid())
        if result[0]:
            # Auditoría Finanzas F21: PAYROLL_PAID se entrega a contabilidad en
            # el acto; si falla queda pendiente con su error y se reintenta.
            dispatcher = self._use_cases.get("dispatch_outbox")
            if dispatcher is not None:
                try:
                    dispatcher()
                except Exception:
                    logger.exception("despacho de hr_outbox fallido")
        return result

    def cancel_payroll(self, payroll_run_id: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["cancel_payroll"].execute, self._conn(),
            actor_user_id=self._actor(), payroll_run_id=payroll_run_id,
            operation_id=new_uuid())

    # ── recibos, complementaria y reverso ─────────────────────────────────
    def export_receipts_pdf(self, payroll_run_id: str, path: str, *,
                            employee_ids: list[str] | None = None) -> tuple[bool, str]:
        return self._run(
            self._use_cases["receipts_pdf"].execute, self._conn(),
            actor_user_id=self._actor(), payroll_run_id=payroll_run_id, path=path,
            employee_ids=employee_ids)

    def print_receipts(self, payroll_run_id: str, *,
                       employee_ids: list[str] | None = None) -> tuple[bool, str]:
        return self._run(
            self._use_cases["receipts_ticket"].execute, self._conn(),
            actor_user_id=self._actor(), payroll_run_id=payroll_run_id,
            employee_ids=employee_ids, branch_id=self._branch(),
            workstation_id=getattr(self._session, "workstation_id", None))

    def generate_complementary(self, payroll_run_id: str, *, reason: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["complementary_payroll"].execute, self._conn(),
            actor_user_id=self._actor(), original_run_id=payroll_run_id, reason=reason,
            operation_id=new_uuid(), today=self._today())

    def reverse_payment(self, payroll_run_id: str, *, reason: str) -> tuple[bool, str]:
        result = self._run(
            self._use_cases["reverse_payment"].execute, self._conn(),
            actor_user_id=self._actor(), payroll_run_id=payroll_run_id, reason=reason,
            operation_id=new_uuid())
        if result[0] and self._use_cases.get("dispatch_outbox"):
            try:
                self._use_cases["dispatch_outbox"]()
            except Exception:
                logger.exception("despacho de hr_outbox fallido")
        return result

    # ── conceptos capturados y préstamos ──────────────────────────────────
    def payroll_inputs(self) -> TableViewModel:
        if not self.can(HRPermission.PAYROLL_VIEW):
            return TableViewModel([], [])
        rows, ids = [], []
        for row in self._queries["operations"].payroll_inputs(branch_id=self._branch()):
            rows.append([row["employee_name"], concept_es(row["concept"]),
                         money_display(row["amount"]), row["applies_on"], row["reason"],
                         status_es(row["status"])])
            ids.append(row["id"])
        return TableViewModel(rows, ids)

    def capture_input(self, *, employee_id, concept, amount, applies_on,
                      reason) -> tuple[bool, str]:
        return self._run(
            self._use_cases["capture_input"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id, concept=concept,
            amount=amount, applies_on=applies_on, reason=reason, operation_id=new_uuid())

    def resolve_input(self, input_id: str, *, approve: bool) -> tuple[bool, str]:
        return self._run(
            self._use_cases["resolve_input"].execute, self._conn(),
            actor_user_id=self._actor(), input_id=input_id, approve=approve)

    def loans(self) -> TableViewModel:
        if not self.can(HRPermission.PAYROLL_VIEW):
            return TableViewModel([], [])
        rows, ids = [], []
        for row in self._queries["operations"].loans(branch_id=self._branch()):
            rows.append([row["employee_name"],
                         "Anticipo" if row["kind"] == "ADVANCE" else "Préstamo",
                         money_display(row["principal"]), money_display(row["installment"]),
                         money_display(row["balance"]), row["granted_on"],
                         status_es(row["status"])])
            ids.append(row["id"])
        return TableViewModel(rows, ids)

    def grant_loan(self, *, employee_id, kind, principal, installment, payment_method,
                   reason, payment_reference=None) -> tuple[bool, str]:
        result = self._run(
            self._use_cases["grant_loan"].execute, self._conn(),
            actor_user_id=self._actor(), employee_id=employee_id, kind=kind,
            principal=principal, installment=installment, payment_method=payment_method,
            reason=reason, payment_reference=payment_reference, operation_id=new_uuid(),
            granted_on=self._today())
        if result[0] and self._use_cases.get("dispatch_outbox"):
            try:
                self._use_cases["dispatch_outbox"]()
            except Exception:
                logger.exception("despacho de hr_outbox fallido")
        return result

    # ── checador ──────────────────────────────────────────────────────────
    def devices(self) -> TableViewModel:
        if not self.can(HRPermission.ATTENDANCE_VIEW):
            return TableViewModel([], [])
        rows, ids = [], []
        for row in self._queries["operations"].devices(branch_id=self._branch()):
            rows.append([row["code"], row["name"], TIME_CLOCK_KIND_ES.get(row["kind"], row["kind"]),
                         TIME_CLOCK_DRIVER_ES.get(row["driver"], row["driver"]),
                         (row["last_synced_at"] or "—")[:16].replace("T", " "),
                         str(row["unmatched"] or 0), "Activo" if row["active"] else "Inactivo"])
            ids.append(row["id"])
        return TableViewModel(rows, ids)

    def device_options(self) -> list[tuple[str, str]]:
        return [(row["id"], f"{row['code']} — {row['name']}")
                for row in self._queries["operations"].devices(branch_id=self._branch())
                if row["active"]]

    def register_device(self, *, code, name, kind, driver,
                        connection_settings=None) -> tuple[bool, str]:
        branch = self._branch()
        if not branch:
            return False, "No hay sucursal en el contexto de sesión."
        return self._run(
            self._use_cases["register_device"].execute, self._conn(),
            actor_user_id=self._actor(), branch_id=branch, code=code, name=name, kind=kind,
            driver=driver, connection_settings=connection_settings)

    def sync_device(self, device_id: str) -> tuple[bool, str]:
        return self._run(self._use_cases["sync_device"].execute, self._conn(),
                         actor_user_id=self._actor(), device_id=device_id)

    def import_device_file(self, device_id: str, path: str) -> tuple[bool, str]:
        return self._run(self._use_cases["import_device_file"].execute, self._conn(),
                         actor_user_id=self._actor(), device_id=device_id, path=path)

    def kiosk_punch(self, device_id: str, *, credential_type: str,
                    raw_value: str) -> tuple[bool, str]:
        return self._run(self._use_cases["kiosk_punch"].execute, self._conn(),
                         actor_user_id=self._actor(), device_id=device_id,
                         credential_type=credential_type, raw_value=raw_value)

    def credentials(self, employee_id: str) -> TableViewModel:
        rows, ids = [], []
        for row in self._queries["operations"].credentials(employee_id):
            rows.append([CREDENTIAL_ES.get(row["credential_type"], row["credential_type"]),
                         row["label"], row["device_code"],
                         "Activa" if row["active"] else "Dada de baja"])
            ids.append(row["id"])
        return TableViewModel(rows, ids)

    def enroll_credential(self, employee_id: str, *, credential_type: str, raw_value: str,
                          device_id: str | None = None) -> tuple[bool, str]:
        return self._run(self._use_cases["enroll_credential"].execute, self._conn(),
                         actor_user_id=self._actor(), employee_id=employee_id,
                         credential_type=credential_type, raw_value=raw_value,
                         device_id=device_id)

    def revoke_credential(self, credential_id: str, *, reason: str) -> tuple[bool, str]:
        return self._run(self._use_cases["revoke_credential"].execute, self._conn(),
                         actor_user_id=self._actor(), credential_id=credential_id,
                         reason=reason)

    # ── settings (catalogs) ───────────────────────────────────────────────
    def update_catalog_item(self, item_id: str, *, kind: str, name: str,
                            active: bool = True) -> tuple[bool, str]:
        return self._run(self._use_cases["catalog"].update_item, self._conn(),
                         actor_user_id=self._actor(), kind=kind, item_id=item_id, name=name,
                         active=active)

    def create_department(self, *, code: str, name: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["catalog"].create_department, self._conn(),
            actor_user_id=self._actor(), code=code, name=name, branch_id=self._branch())

    def create_position(self, *, code: str, name: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["catalog"].create_position, self._conn(),
            actor_user_id=self._actor(), code=code, name=name)

    def catalog_table(self) -> TableViewModel:
        catalogs = self._queries["employees"].catalogs()
        rows = [["Departamento", d["code"], d["name"]] for d in catalogs["departments"]]
        rows += [["Puesto", p["code"], p["name"]] for p in catalogs["positions"]]
        self._catalog_kinds = {d["id"]: "department" for d in catalogs["departments"]}
        self._catalog_kinds.update({p["id"]: "position" for p in catalogs["positions"]})
        ids = [d["id"] for d in catalogs["departments"]] + [p["id"] for p in catalogs["positions"]]
        return TableViewModel(rows, ids)

    def catalog_kind(self, item_id: str) -> str | None:
        return getattr(self, "_catalog_kinds", {}).get(item_id)

    def employee_options(self) -> list[tuple[str, str]]:
        """Compatibilidad: los diálogos usan ``search_employees``."""
        return self.search_employees("", limit=50)

    def shift_options(self) -> list[tuple[str, str]]:
        return [(shift["id"], shift["name"])
                for shift in self._queries["shifts"].list_active(branch_id=self._branch())]
