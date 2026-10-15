"""337 — Pendientes de RR. HH.: recibo, checador, complementaria, préstamos y
libro de vacaciones (2026-10-14).

Sólo agrega (``create_hr_schema``):

* ``payroll_inputs`` (bonos/comisiones/ajustes capturados y aprobados),
  ``employee_loans`` + ``payroll_loan_applications`` (préstamos y anticipos que se
  abonan en nómina), ``leave_balance_movements`` (libro de vacaciones),
  ``hr_time_clock_devices`` / ``hr_employee_credentials`` / ``hr_device_events``
  (checador; la credencial guarda la referencia del aparato, nunca la plantilla
  biométrica; el PIN sólo como hash);
* columnas de corrida complementaria y de reverso de pago en ``payroll_runs`` y
  ``payroll_payments``.

Siembra las acciones ``RRHH.*`` nuevas con la misma regla que la 336 (vuelve a
ejecutarla: es idempotente). Pasa al libro las solicitudes de vacaciones que ya
existían: las pendientes apartan días y las aprobadas los consumen.

La cuenta 1145 (Préstamos y anticipos a empleados) la agrega Finanzas al arrancar
(``_ensure_late_additions``). Idempotente.
"""

from __future__ import annotations

import importlib
import logging

from backend.infrastructure.db.schema.hr_schema import create_hr_schema

logger = logging.getLogger("spj.migrations.337")


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def _backfill_vacations(conn) -> int:
    from backend.application.hr.leave_balance import LeaveBalanceService
    from backend.domain.hr.enums import LeaveStatus, LeaveType
    from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork

    moved = 0
    with HRUnitOfWork(conn) as uow:
        ledger = LeaveBalanceService()
        employee_ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT employee_id FROM leave_requests WHERE leave_type='VACATION'"
            " AND status IN ('PENDING','APPROVED')")]
        for employee_id in employee_ids:
            employee = uow.employees.get(employee_id)
            if employee is None:
                continue
            for request in sorted(uow.leaves.list_by_employee(employee_id),
                                  key=lambda r: r.start_date):
                if request.leave_type is not LeaveType.VACATION or \
                        request.status not in (LeaveStatus.PENDING, LeaveStatus.APPROVED):
                    continue
                if uow.leave_ledger.by_source("leave", request.id):
                    continue
                try:
                    ledger.reserve(uow, employee, request, actor_user_id=None)
                except Exception as exc:  # saldo histórico insuficiente: se registra
                    logger.warning("337: vacaciones %s sin saldo en el libro: %s",
                                   request.id, exc)
                    continue
                if request.status is LeaveStatus.APPROVED:
                    ledger.consume(uow, request, actor_user_id=None)
                moved += 1
    return moved


def run(conn) -> None:
    if not _tabla(conn, "employees"):
        logger.info("337: sin esquema de RR. HH.; nada que actualizar.")
        return
    create_hr_schema(conn)
    conn.commit()
    importlib.import_module("migrations.standalone.336_seed_hr_granular_permissions").run(conn)
    moved = _backfill_vacations(conn)
    conn.commit()
    logger.info("337: esquema de pendientes de RR. HH. listo; %s solicitud(es) al libro", moved)


up = run
