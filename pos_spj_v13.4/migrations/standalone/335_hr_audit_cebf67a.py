"""335 — Auditoría directa de RR. HH. (cebf67a), 2026-10-14.

Lleva el esquema de RR. HH. al contrato de las correcciones de la auditoría
(ver docs/refactor/HR-AUD_auditoria_cebf67a.md). Sólo agrega; no reescribe datos:

* ``employee_salary_history`` (HR-09/HR-23): el salario tiene vigencia. Se
  siembra un renglón por empleado existente con su salario ACTUAL vigente desde
  su ingreso (es lo único que el sistema sabía; antes de hoy no había historia).
* ``payroll_coverage`` (HR-10): un día de un empleado lo cubre una sola corrida
  ordinaria viva. Se rellena con las corridas existentes no canceladas; si dos
  ya se solapaban, el solape se REGISTRA en el log y gana la primera (no se
  cancela nada por migración).
* ``payroll_payment_allocations`` (HR-11), ``hr_inbox`` (HR-06).
* columnas: ``payroll_runs.run_type/request_fingerprint/authorized_net_amount``,
  ``payroll_payments.payment_reference``, cancelación en ``leave_requests``.

Idempotente.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.335")


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    if not _tabla(conn, "employees"):
        logger.info("335: sin esquema de RR. HH.; nada que actualizar.")
        return
    create_hr_schema(conn)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    historia = 0
    for emp_id, daily, base, currency, hire in conn.execute(
            "SELECT id, daily_salary, base_salary, currency_code, hire_date FROM employees"
    ).fetchall():
        cur = conn.execute(
            "INSERT OR IGNORE INTO employee_salary_history (id, employee_id, daily_salary,"
            " base_salary, currency_code, effective_from, reason, changed_by_user_id,"
            " operation_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), emp_id, daily, base, currency or "MXN", hire,
             "Salario vigente al migrar (335)", None, new_uuid(), now))
        historia += cur.rowcount or 0

    cobertura, solapes = 0, []
    for run_id, start, end in conn.execute(
            "SELECT id, period_start, period_end FROM payroll_runs"
            " WHERE status<>'CANCELLED' ORDER BY created_at").fetchall():
        empleados = [r[0] for r in conn.execute(
            "SELECT DISTINCT employee_id FROM payroll_lines WHERE payroll_run_id=?", (run_id,))]
        day, last = date.fromisoformat(start), date.fromisoformat(end)
        while day <= last:
            for emp_id in empleados:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO payroll_coverage (id, employee_id, coverage_date,"
                    " payroll_run_id) VALUES (?,?,?,?)",
                    (new_uuid(), emp_id, day.isoformat(), run_id))
                if cur.rowcount:
                    cobertura += 1
                else:
                    owner = conn.execute(
                        "SELECT payroll_run_id FROM payroll_coverage WHERE employee_id=?"
                        " AND coverage_date=?", (emp_id, day.isoformat())).fetchone()
                    if owner and owner[0] != run_id:
                        solapes.append((emp_id, day.isoformat(), run_id, owner[0]))
            day += timedelta(days=1)
    conn.commit()
    for emp_id, day, run_id, owner in solapes[:50]:
        logger.warning("335: solape previo — empleado %s día %s en %s y %s",
                       emp_id, day, run_id, owner)
    logger.info("335: historial salarial %s, días de cobertura %s, solapes previos %s",
                historia, cobertura, len(solapes))


up = run
