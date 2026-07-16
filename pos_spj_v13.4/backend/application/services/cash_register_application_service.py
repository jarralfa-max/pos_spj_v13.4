"""CashRegisterApplicationService — canonical orchestration for the caja module.

Delegation target for OpenCashShift / RegisterCashMovement / GenerateZCut use
cases. It orchestrates the existing FinanceService turno logic (abrir_turno,
registrar_movimiento_manual, generar_corte_z) — no business rules live here — and
emits the canonical CASH_* domain events with the command's operation_id.

REGLA CERO: the shift identity (turno_id) is a UUIDv7 minted by abrir_turno;
operation_id (the command) and entity_id (the shift) are distinct UUIDs (rule 41).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from backend.application.commands.cash_register_commands import (
    GenerateZCutCommand,
    OpenCashShiftCommand,
    RegisterCashMovementCommand,
)
from backend.application.dto.use_case_result import UseCaseResult
from backend.shared.events.event_names import EventName

logger = logging.getLogger("spj.application.cash_register")

Publisher = Callable[[str, dict], Any]


class CashRegisterApplicationService:
    def __init__(self, finance_service, publisher: Publisher | None = None,
                 *, employee_resolver: Callable[[str], str | None] | None = None) -> None:
        self._fin = finance_service
        self._publish: Publisher = publisher or (lambda *_: None)
        # Resolves user_id → employee_id so CASH_SHIFT_OPENED carries HR identity
        # (never the user name as identity). Injected by the composition root.
        self._resolve_employee = employee_resolver or (lambda _user_id: None)

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _user(cmd) -> str:
        return cmd.user_name or cmd.user_id or "sistema"

    def _open_shift_id(self, cmd) -> str | None:
        estado = self._fin.get_estado_turno(cmd.branch_id, self._user(cmd))
        return estado["id"] if estado else None

    # ── use case handlers ─────────────────────────────────────────────────────
    def open_shift(self, command: OpenCashShiftCommand) -> UseCaseResult:
        shift_id = self._fin.abrir_turno(
            sucursal_id=command.branch_id,
            usuario=self._user(command),
            fondo_inicial=float(command.opening_amount or 0.0),
        )
        from backend.shared.ids import new_uuid
        employee_id = self._resolve_employee(command.user_id) if command.user_id else None
        self._publish(EventName.CASH_SHIFT_OPENED.value, {
            "event_id": new_uuid(),
            "operation_id": command.operation_id,
            "shift_id": shift_id,
            "branch_id": command.branch_id,
            "user_id": command.user_id,
            "employee_id": employee_id,
            "opened_at": None,  # abrir_turno stamps server time; handler defaults to now
            "opening_amount": float(command.opening_amount or 0.0),
            "source": "POS",
        })
        return UseCaseResult(
            success=True, operation_id=command.operation_id, entity_id=str(shift_id),
            message="Turno de caja abierto", data={"shift_id": shift_id},
        )

    def register_movement(self, command: RegisterCashMovementCommand) -> UseCaseResult:
        shift_id = self._open_shift_id(command)
        if not shift_id:
            return UseCaseResult(success=False, operation_id=command.operation_id,
                                 message="No hay turno de caja abierto")
        self._fin.registrar_movimiento_manual(
            turno_id=shift_id, sucursal_id=command.branch_id, usuario=self._user(command),
            tipo=command.movement_type, monto=float(command.amount or 0.0),
            concepto=command.concept,
        )
        self._publish(EventName.CASH_MOVEMENT_RECORDED.value, {
            "operation_id": command.operation_id,
            "shift_id": shift_id,
            "branch_id": command.branch_id,
            "movement_type": command.movement_type,
            "amount": float(command.amount or 0.0),
            "concept": command.concept,
        })
        return UseCaseResult(
            success=True, operation_id=command.operation_id, entity_id=str(shift_id),
            message="Movimiento de caja registrado", data={"shift_id": shift_id},
        )

    def generate_z_cut(self, command: GenerateZCutCommand) -> UseCaseResult:
        shift_id = self._open_shift_id(command)
        if not shift_id:
            return UseCaseResult(success=False, operation_id=command.operation_id,
                                 message="No hay turno de caja abierto")
        efectivo_fisico = float((command.payload or {}).get("efectivo_fisico", 0.0))
        corte = self._fin.generar_corte_z(
            turno_id=shift_id, sucursal_id=command.branch_id,
            usuario=self._user(command), efectivo_fisico=efectivo_fisico,
        )
        diferencia = float((corte or {}).get("diferencia", 0.0))
        self._publish(EventName.CASH_Z_CUT_GENERATED.value, {
            "operation_id": command.operation_id,
            "shift_id": shift_id,
            "branch_id": command.branch_id,
            **(corte or {}),
        })
        if abs(diferencia) > 0.009:
            self._publish(EventName.CASH_DIFFERENCE_DETECTED.value, {
                "operation_id": command.operation_id,
                "shift_id": shift_id,
                "branch_id": command.branch_id,
                "diferencia": diferencia,
            })
        return UseCaseResult(
            success=True, operation_id=command.operation_id, entity_id=str(shift_id),
            message=f"Corte Z generado (diferencia {diferencia:.2f})",
            data=dict(corte or {}),
        )
