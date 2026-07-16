"""CashRegisterApplicationService — canonical orchestration for the caja module.

Open/close cash shifts are now identified by user_id and employee_id, and HR
attendance is integrated through CASH_SHIFT_* events consumed by HR handlers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from backend.application.commands.cash_register_commands import (
    CloseCashShiftCommand,
    GenerateZCutCommand,
    OpenCashShiftCommand,
    RegisterCashMovementCommand,
)
from backend.application.dto.use_case_result import UseCaseResult
from backend.domain.hr.exceptions import EmployeeInactiveError, EmployeeNotFoundError, PermissionDeniedError, UserEmployeeLinkRequiredError
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.application.cash_register")

Publisher = Callable[[str, dict], Any]
PermissionChecker = Callable[[str | None, str], bool]


class CashRegisterApplicationService:
    def __init__(
        self,
        finance_service,
        publisher: Publisher | None = None,
        permission_checker: PermissionChecker | None = None,
    ) -> None:
        self._fin = finance_service
        self._db = getattr(finance_service, "db", None)
        self._publish: Publisher = publisher or (lambda *_: None)
        self._permission_checker = permission_checker or (lambda _user_id, _permission: True)
        self._employee_repository = SQLiteEmployeeRepository(self._db) if self._db is not None else None

    def _cash_identity(self, cmd) -> str:
        if not cmd.user_id:
            raise UserEmployeeLinkRequiredError("cash shift requires canonical user_id")
        return str(cmd.user_id)

    def _open_shift_id(self, cmd) -> str | None:
        estado = self._fin.get_estado_turno(cmd.branch_id, self._cash_identity(cmd))
        return estado["id"] if estado else None

    def _require_cash_permission(self, user_id: str | None, permission: str) -> None:
        if not self._permission_checker(user_id, permission):
            raise PermissionDeniedError(permission)

    def _resolve_employee_id(self, command) -> str:
        user_id = self._cash_identity(command)
        employee_id = str(getattr(command, "employee_id", "") or "").strip()
        row = None
        if self._db is not None:
            row = self._db.execute(
                "SELECT id, employee_id, activo, sucursal_id FROM usuarios WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is not None:
            user_row = dict(row)
            if int(user_row.get("activo") or 0) != 1:
                raise PermissionDeniedError("cash.user.active")
            linked_employee_id = str(user_row.get("employee_id") or "").strip()
            if not linked_employee_id:
                raise UserEmployeeLinkRequiredError(user_id)
            if employee_id and employee_id != linked_employee_id:
                raise PermissionDeniedError("cash.user.employee_link")
            employee_id = linked_employee_id
            user_branch = str(user_row.get("sucursal_id") or "").strip()
            if user_branch and user_branch != str(command.branch_id):
                raise PermissionDeniedError("cash.branch.authorized")
        if not employee_id:
            raise UserEmployeeLinkRequiredError(user_id)
        if self._employee_repository is not None:
            employee = self._employee_repository.get(employee_id)
            if employee is None:
                raise EmployeeNotFoundError(employee_id)
            if not employee.active:
                raise EmployeeInactiveError(employee_id)
        return employee_id

    def open_shift(self, command: OpenCashShiftCommand) -> UseCaseResult:
        command.validate_context()
        self._require_cash_permission(command.user_id, "caja.abrir")
        employee_id = self._resolve_employee_id(command)
        opened_at = datetime.now(UTC)
        existing_shift_id = self._open_shift_id(command)
        if existing_shift_id:
            payload = self._cash_opened_payload(command, existing_shift_id, employee_id, opened_at)
            payload["idempotent"] = True
            self._publish(EventName.CASH_SHIFT_OPENED.value, payload)
            return UseCaseResult(
                success=True,
                operation_id=command.operation_id,
                entity_id=str(existing_shift_id),
                message="Caja abierta correctamente.\nYa existía una entrada laboral registrada; no se creó un duplicado.",
                data={"shift_id": existing_shift_id, "employee_id": employee_id, "attendance_message": "Ya existía una entrada laboral registrada; no se creó un duplicado."},
            )
        shift_id = self._fin.abrir_turno(
            sucursal_id=command.branch_id,
            usuario=self._cash_identity(command),
            fondo_inicial=float(command.opening_amount or 0.0),
        )
        self._publish(EventName.CASH_SHIFT_OPENED.value, self._cash_opened_payload(command, shift_id, employee_id, opened_at))
        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=str(shift_id),
            message=f"Caja abierta correctamente.\nTu entrada se registró a las {opened_at.strftime('%H:%M')}.",
            data={"shift_id": shift_id, "employee_id": employee_id, "attendance_message": f"Tu entrada se registró a las {opened_at.strftime('%H:%M')}."},
        )

    def close_shift(self, command: CloseCashShiftCommand) -> UseCaseResult:
        command.validate_context()
        self._require_cash_permission(command.user_id, "caja.cerrar")
        employee_id = self._resolve_employee_id(command)
        shift_id = command.shift_id or self._open_shift_id(command)
        if not shift_id:
            return UseCaseResult(success=False, operation_id=command.operation_id, message="No hay turno de caja abierto")
        closed_at = datetime.now(UTC)
        corte = self._fin.generar_corte_z(
            turno_id=str(shift_id),
            sucursal_id=str(command.branch_id),
            usuario=self._cash_identity(command),
            efectivo_fisico=float(command.counted_cash or 0.0),
        )
        difference = float((corte or {}).get("diferencia", command.cash_difference or 0.0))
        z_cut_id = str(command.z_cut_id or (corte or {}).get("cierre_id") or shift_id)
        self._publish(EventName.CASH_Z_CUT_GENERATED.value, {
            "event_id": new_uuid(),
            "operation_id": command.operation_id,
            "entity_id": z_cut_id,
            "shift_id": str(shift_id),
            "branch_id": command.branch_id,
            "user_id": command.user_id,
            "employee_id": employee_id,
            **dict(corte or {}),
        })
        self._publish(EventName.CASH_SHIFT_CLOSED.value, {
            "event_id": new_uuid(),
            "operation_id": command.operation_id,
            "entity_id": str(shift_id),
            "shift_id": str(shift_id),
            "branch_id": command.branch_id,
            "user_id": command.user_id,
            "employee_id": employee_id,
            "closed_at": closed_at.isoformat(),
            "z_cut_id": z_cut_id,
            "cash_difference": difference,
            "source": "POS",
        })
        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=str(shift_id),
            message=f"Caja cerrada correctamente.\nTu salida se registró a las {closed_at.strftime('%H:%M')}.",
            data={"shift_id": shift_id, "z_cut_id": z_cut_id, "cash_difference": difference, "employee_id": employee_id, **dict(corte or {})},
        )

    def register_movement(self, command: RegisterCashMovementCommand) -> UseCaseResult:
        shift_id = self._open_shift_id(command)
        if not shift_id:
            return UseCaseResult(success=False, operation_id=command.operation_id, message="No hay turno de caja abierto")
        self._fin.registrar_movimiento_manual(
            turno_id=shift_id,
            sucursal_id=command.branch_id,
            usuario=self._cash_identity(command),
            tipo=command.movement_type,
            monto=float(command.amount or 0.0),
            concepto=command.concept,
        )
        self._publish(EventName.CASH_MOVEMENT_RECORDED.value, {
            "event_id": new_uuid(),
            "operation_id": command.operation_id,
            "entity_id": str(shift_id),
            "shift_id": shift_id,
            "branch_id": command.branch_id,
            "user_id": command.user_id,
            "movement_type": command.movement_type,
            "amount": float(command.amount or 0.0),
            "concept": command.concept,
        })
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=str(shift_id), message="Movimiento de caja registrado", data={"shift_id": shift_id})

    def generate_z_cut(self, command: GenerateZCutCommand) -> UseCaseResult:
        shift_id = self._open_shift_id(command)
        if not shift_id:
            return UseCaseResult(success=False, operation_id=command.operation_id, message="No hay turno de caja abierto")
        efectivo_fisico = float((command.payload or {}).get("efectivo_fisico", 0.0))
        corte = self._fin.generar_corte_z(
            turno_id=shift_id,
            sucursal_id=command.branch_id,
            usuario=self._cash_identity(command),
            efectivo_fisico=efectivo_fisico,
        )
        diferencia = float((corte or {}).get("diferencia", 0.0))
        self._publish(EventName.CASH_Z_CUT_GENERATED.value, {
            "event_id": new_uuid(),
            "operation_id": command.operation_id,
            "entity_id": str((corte or {}).get("cierre_id") or shift_id),
            "shift_id": shift_id,
            "branch_id": command.branch_id,
            "user_id": command.user_id,
            **(corte or {}),
        })
        if abs(diferencia) > 0.009:
            self._publish(EventName.CASH_DIFFERENCE_DETECTED.value, {
                "event_id": new_uuid(),
                "operation_id": command.operation_id,
                "entity_id": str(shift_id),
                "shift_id": shift_id,
                "branch_id": command.branch_id,
                "user_id": command.user_id,
                "diferencia": diferencia,
            })
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=str(shift_id), message=f"Corte Z generado (diferencia {diferencia:.2f})", data=dict(corte or {}))

    def _cash_opened_payload(self, command: OpenCashShiftCommand, shift_id: str, employee_id: str, opened_at: datetime) -> dict:
        return {
            "event_id": new_uuid(),
            "operation_id": command.operation_id,
            "entity_id": str(shift_id),
            "shift_id": str(shift_id),
            "branch_id": command.branch_id,
            "user_id": command.user_id,
            "employee_id": employee_id,
            "opened_at": opened_at.isoformat(),
            "opening_amount": float(command.opening_amount or 0.0),
            "source": "POS",
        }
