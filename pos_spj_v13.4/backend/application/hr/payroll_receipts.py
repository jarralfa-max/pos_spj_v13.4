"""Recibo de nómina por empleado (2026-10-14).

Arma, con lo que la corrida GUARDÓ (líneas, pago, reparto), el recibo de cada
empleado: percepciones, deducciones, neto, periodo, forma de pago y datos del
expediente. El recibo NO recalcula: es la evidencia de lo que se autorizó y
pagó. Se entrega en PDF (carta, una hoja por empleado) o como ticket ESC/POS
por la impresora que Document Output asigna a «Recibo de nómina».

Un recibo de una corrida no pagada sale marcado PRELIMINAR; cada impresión o
exportación queda en la bitácora y desde la segunda sale como REIMPRESIÓN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.business_dates import resolve_timezone

_CONCEPTS = {
    "BASE_SALARY": "Sueldo", "OVERTIME": "Horas extra", "BONUS": "Bono",
    "COMMISSION": "Comisión", "VACATION": "Vacaciones", "PAID_LEAVE": "Permiso con goce",
    "ABSENCE_DEDUCTION": "Faltas / sin goce", "LATE_DEDUCTION": "Retardos",
    "LOAN_DEDUCTION": "Abono a préstamo", "ADVANCE_DEDUCTION": "Anticipo de sueldo",
    "ADJUSTMENT": "Ajuste", "TAX_WITHHOLDING": "Retención ISR",
    "SOCIAL_SECURITY": "Cuota IMSS",
}
_METHODS = {"CASH": "Efectivo", "BANK_TRANSFER": "Transferencia", "CHECK": "Cheque"}
_RUN_TYPES = {"ORDINARY": "Ordinaria", "COMPLEMENTARY": "Complementaria"}


@dataclass(frozen=True, slots=True)
class PayrollReceiptLine:
    concept: str
    detail: str
    amount: str


@dataclass(frozen=True, slots=True)
class PayrollReceipt:
    folio: str
    company_name: str
    company_tax_id: str
    branch_name: str
    payroll_run_id: str
    run_type: str
    period_start: str
    period_end: str
    employee_id: str
    employee_code: str
    employee_name: str
    tax_identifier: str
    department: str
    position: str
    hire_date: str
    perceptions: tuple[PayrollReceiptLine, ...]
    deductions: tuple[PayrollReceiptLine, ...]
    gross: str
    deductions_total: str
    net: str
    currency: str
    payment_method: str
    payment_reference: str
    paid_at: str
    preliminary: bool
    print_count: int = 0

    @property
    def reprint(self) -> bool:
        return self.print_count > 0


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}"


def _masked(value: str | None) -> str:
    text = str(value or "").strip()
    return text if len(text) <= 4 else "•" * (len(text) - 4) + text[-4:]


class PayrollReceiptService:
    """Lectura de recibos (sin escribir). ``receipts_for_run`` devuelve uno
    por empleado de la corrida, o sólo los pedidos."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = self._conn.execute(sql, params)
        row = cursor.fetchone()
        return dict(zip([c[0] for c in cursor.description], row)) if row else None

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _has(self, table: str) -> bool:
        return self._conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                  (table,)).fetchone() is not None

    def _company(self) -> tuple[str, str]:
        if self._has("company_profiles"):
            row = self._one("SELECT business_name, commercial_name, legal_name, tax_id"
                            " FROM company_profiles WHERE active=1 LIMIT 1")
            if row:
                name = row.get("business_name") or row.get("commercial_name") or row.get("legal_name")
                return str(name or "").strip(), str(row.get("tax_id") or "")
        return "", ""

    def _branch(self, branch_id: str | None) -> str:
        if not branch_id:
            return "Todas las sucursales"
        for table, column in (("branch_profiles", "name"), ("sucursales", "nombre")):
            if self._has(table):
                key = "branch_id" if table == "branch_profiles" else "id"
                row = self._one(f"SELECT {column} AS name FROM {table} WHERE {key}=?", (branch_id,))
                if row and row.get("name"):
                    return str(row["name"])
        return str(branch_id)

    def receipts_for_run(self, payroll_run_id: str, *,
                         employee_ids: list[str] | None = None) -> list[PayrollReceipt]:
        run = self._one("SELECT * FROM payroll_runs WHERE id=?", (payroll_run_id,))
        if run is None:
            return []
        payment = self._one("SELECT * FROM payroll_payments WHERE payroll_run_id=?",
                            (payroll_run_id,))
        company, tax_id = self._company()
        branch = self._branch(run.get("branch_id"))
        zone = resolve_timezone(None)
        paid_at = ""
        if payment and payment.get("paid_at"):
            try:
                paid_at = datetime.fromisoformat(str(payment["paid_at"])).astimezone(
                    zone).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                paid_at = str(payment["paid_at"])
        lines = self._all(
            "SELECT employee_id, concept, amount, currency_code, is_deduction, quantity, notes"
            " FROM payroll_lines WHERE payroll_run_id=? ORDER BY concept", (payroll_run_id,))
        wanted = set(employee_ids) if employee_ids else None
        by_employee: dict[str, list[dict]] = {}
        for line in lines:
            if wanted is None or line["employee_id"] in wanted:
                by_employee.setdefault(line["employee_id"], []).append(line)
        counts = self._print_counts(payroll_run_id)
        receipts = []
        for employee_id, employee_lines in by_employee.items():
            emp = self._one(
                "SELECT e.employee_code, e.first_name, e.last_name, e.tax_identifier,"
                " e.hire_date, d.name AS department, p.name AS position FROM employees e"
                " LEFT JOIN hr_departments d ON d.id=e.department_id"
                " LEFT JOIN hr_positions p ON p.id=e.position_id WHERE e.id=?",
                (employee_id,)) or {}
            perceptions, deductions = [], []
            gross = deductions_total = Decimal("0")
            for line in employee_lines:
                amount = Decimal(str(line["amount"]))
                item = PayrollReceiptLine(
                    _CONCEPTS.get(line["concept"], line["concept"]),
                    str(line.get("notes") or line.get("quantity") or ""), _money(amount))
                if line["is_deduction"]:
                    deductions.append(item)
                    deductions_total += amount
                else:
                    perceptions.append(item)
                    gross += amount
            code = str(emp.get("employee_code") or employee_id[:8])
            receipts.append(PayrollReceipt(
                folio=f"NOM-{str(run['period_start']).replace('-', '')}-{code}",
                company_name=company, company_tax_id=tax_id, branch_name=branch,
                payroll_run_id=payroll_run_id,
                run_type=_RUN_TYPES.get(run.get("run_type") or "ORDINARY", "Ordinaria"),
                period_start=str(run["period_start"]), period_end=str(run["period_end"]),
                employee_id=employee_id, employee_code=code,
                employee_name=f"{emp.get('first_name') or ''} {emp.get('last_name') or ''}".strip(),
                tax_identifier=_masked(emp.get("tax_identifier")),
                department=str(emp.get("department") or ""), position=str(emp.get("position") or ""),
                hire_date=str(emp.get("hire_date") or ""),
                perceptions=tuple(perceptions), deductions=tuple(deductions),
                gross=_money(gross), deductions_total=_money(deductions_total),
                net=_money(gross - deductions_total),
                currency=str(employee_lines[0].get("currency_code") or "MXN"),
                payment_method=_METHODS.get(str((payment or {}).get("payment_method") or ""), ""),
                payment_reference=str((payment or {}).get("payment_reference") or ""),
                paid_at=paid_at, preliminary=run["status"] != "PAID",
                print_count=counts.get(employee_id, 0)))
        return sorted(receipts, key=lambda r: r.employee_name)

    def _print_counts(self, payroll_run_id: str) -> dict[str, int]:
        rows = self._all(
            "SELECT detail FROM hr_audit_log WHERE entity_type='payroll_run' AND entity_id=?"
            " AND action IN ('PAYROLL_RECEIPT_PRINTED','PAYROLL_RECEIPT_EXPORTED')",
            (payroll_run_id,))
        counts: dict[str, int] = {}
        for row in rows:
            for employee_id in str(row["detail"] or "").split(","):
                if employee_id:
                    counts[employee_id] = counts.get(employee_id, 0) + 1
        return counts


class _ReceiptUseCase:
    action = ""

    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def _receipts(self, connection, actor_user_id, payroll_run_id, employee_ids):
        self._auth.require(actor_user_id, HRPermission.PAYROLL_RECEIPT)
        with HRUnitOfWork(connection) as uow:
            run = uow.payroll.get(payroll_run_id)
        if run is None:
            return None, HRResult.fail("La corrida no existe", "NOT_FOUND")
        self._auth.require_branch(actor_user_id, run.branch_id)
        receipts = PayrollReceiptService(connection).receipts_for_run(
            payroll_run_id, employee_ids=employee_ids)
        if not receipts:
            return None, HRResult.fail("La corrida no tiene recibos que emitir", "EMPTY")
        return receipts, None

    def _audit(self, connection, actor_user_id, payroll_run_id, receipts, detail_suffix=""):
        with HRUnitOfWork(connection) as uow:
            uow.audit.record(action=self.action, actor_user_id=actor_user_id,
                             entity_type="payroll_run", entity_id=payroll_run_id,
                             detail=",".join(r.employee_id for r in receipts) + detail_suffix)


class ExportPayrollReceiptsPdfUseCase(_ReceiptUseCase):
    """Escribe en ``path`` un PDF con una hoja por recibo."""

    action = "PAYROLL_RECEIPT_EXPORTED"

    def __init__(self, authorization: AuthorizationPolicy | None = None, *, renderer) -> None:
        super().__init__(authorization)
        self._render = renderer

    def execute(self, connection, *, actor_user_id: str, payroll_run_id: str, path: str,
                employee_ids: list[str] | None = None) -> HRResult:
        receipts, failure = self._receipts(connection, actor_user_id, payroll_run_id,
                                           employee_ids)
        if failure:
            return failure
        written = self._render(receipts, path)
        self._audit(connection, actor_user_id, payroll_run_id, receipts)
        return HRResult.ok(f"{len(receipts)} recibo(s) guardados en PDF", entity_id=payroll_run_id,
                           path=written, count=len(receipts))


class PrintPayrollReceiptTicketUseCase(_ReceiptUseCase):
    """Imprime el/los recibo(s) como ticket por la impresora asignada a
    «Recibo de nómina» en la sucursal (Configuración → Dispositivos)."""

    action = "PAYROLL_RECEIPT_PRINTED"

    def __init__(self, authorization: AuthorizationPolicy | None = None, *, printer) -> None:
        super().__init__(authorization)
        self._printer = printer

    def execute(self, connection, *, actor_user_id: str, payroll_run_id: str,
                employee_ids: list[str] | None = None, branch_id: str | None = None,
                workstation_id: str | None = None) -> HRResult:
        receipts, failure = self._receipts(connection, actor_user_id, payroll_run_id,
                                           employee_ids)
        if failure:
            return failure
        try:
            device = self._printer(receipts, branch_id=branch_id, workstation_id=workstation_id)
        except Exception as exc:  # impresora no asignada / sin papel: mensaje legible
            return HRResult.fail(str(exc), "PRINTER_UNAVAILABLE")
        self._audit(connection, actor_user_id, payroll_run_id, receipts)
        return HRResult.ok(f"{len(receipts)} recibo(s) enviados a {device}",
                           entity_id=payroll_run_id, count=len(receipts))
