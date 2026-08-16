"""Standard CASH-23 dialogs for cash register workflows.

These dialogs capture UI data only. Authorization, limits, audit and workflow
effects remain in application services/use cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PyQt5.QtWidgets import QLabel, QComboBox, QDialogButtonBox

from frontend.desktop.components.dialogs import FormDialog, StandardDialog
from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.components.text_inputs import PasswordInput, StandardLineEdit, StandardTextArea
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.modules.cash_register.presentation import display_code, scope_label, status_label
from frontend.desktop.themes.tokens import DialogMetrics


def _money(value) -> str:
    return f"${value:,.2f}"


@dataclass(frozen=True)
class CashReasonResult:
    amount: Decimal
    reason: str
    notes: str
    reason_code: str | None = None


@dataclass(frozen=True)
class HotAuthorizationResult:
    authorizer_user: str
    password: str
    reason: str


@dataclass(frozen=True)
class CashDenominationCaptureResult:
    quantities: dict[str, int]


@dataclass(frozen=True)
class CashTextReasonResult:
    reason: str


@dataclass(frozen=True)
class CashHandoverDenominationResult:
    quantities: dict[str, int]


@dataclass(frozen=True)
class CashDeviceDialogResult:
    name: str
    register_id: str | None


@dataclass(frozen=True)
class CashShiftOpeningResult:
    opening_amount: Decimal


@dataclass(frozen=True)
class CashConfigurationDialogResult:
    name: str
    value: str
    scope_type: str
    scope_id: str | None
    effective_from: str | None
    effective_to: str | None


@dataclass(frozen=True)
class CashRefundDialogResult:
    refund_id: str
    sale_id: str
    authorized_by: str
    reason: str
    original_payment_lines: dict[str, Decimal]
    refund_lines: dict[str, Decimal]


class CashReasonDialog(FormDialog):
    """Capture amount, reason and notes for movements, refunds or disputes."""

    def __init__(
        self,
        parent=None,
        *,
        title: str = "Motivo de caja",
        reason_options: tuple[object, ...] = (),
    ) -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        self._reason_options = tuple(reason_options or ())
        self.amount = MoneyInput(self)
        if self._reason_options:
            self.reason = QComboBox(self)
            self.reason.setObjectName("standardComboBox")
            self.reason.addItem("Selecciona un motivo", "")
            for option in self._reason_options:
                label = str(getattr(option, "display_name", ""))
                code = str(getattr(option, "code", ""))
                if code:
                    self.reason.addItem(label or code, code)
        else:
            self.reason = StandardLineEdit(
                self,
                placeholder="Ej. retiro a tesoreria, ajuste autorizado",
                max_length=120,
                required=True,
            )
        self.notes = StandardTextArea(
            self,
            placeholder="Notas operativas visibles para auditoria",
            max_length=500,
        )
        apply_tooltip(self.amount, "Captura el importe exacto de la operacion.")
        apply_tooltip(self.reason, "Motivo corto requerido para auditoria.")
        apply_tooltip(self.notes, "Contexto adicional; evita datos sensibles innecesarios.")
        self.form.addRow("Importe", self.amount)
        self.form.addRow("Motivo", self.reason)
        self.form.addRow("Notas", self.notes)
        self._buttons = self.add_button_box(ok_text="Continuar", cancel_text="Cancelar")

    def _validate(self) -> bool:
        ok = bool(self._reason_value())
        self.reason.setProperty("state", "" if ok else "error")
        self.reason.style().unpolish(self.reason)
        self.reason.style().polish(self.reason)
        if not ok:
            self.reason.setFocus()
        return ok

    def accept(self) -> None:
        if self._validate():
            super().accept()

    def result_value(self) -> CashReasonResult:
        return CashReasonResult(
            amount=self.amount.decimal_value(),
            reason=self._reason_value(),
            notes=self.notes.value(),
            reason_code=self._reason_code(),
        )

    def _reason_value(self) -> str:
        if isinstance(self.reason, QComboBox):
            return self.reason.currentText().strip() if self.reason.currentData() else ""
        return self.reason.value()

    def _reason_code(self) -> str | None:
        if isinstance(self.reason, QComboBox):
            value = self.reason.currentData()
            return str(value) if value else None
        return None


class HotAuthorizationDialog(FormDialog):
    """Capture supervisor credentials for hot authorization."""

    def __init__(self, parent=None, *, title: str = "Autorizacion en caliente") -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_SM)
        self.authorizer = StandardLineEdit(
            self,
            placeholder="Usuario supervisor",
            max_length=80,
            required=True,
        )
        self.password = PasswordInput(self, placeholder="Contrasena")
        self.reason = StandardTextArea(
            self,
            placeholder="Motivo de la autorizacion",
            max_length=300,
        )
        apply_tooltip(self.authorizer, "Usuario con permiso para autorizar esta accion.")
        apply_tooltip(self.password, "La clave no se registra en auditoria.")
        apply_tooltip(self.reason, "Motivo visible para revision posterior.")
        self.form.addRow("Autoriza", self.authorizer)
        self.form.addRow("Clave", self.password)
        self.form.addRow("Motivo", self.reason)
        self.add_button_box(ok_text="Autorizar", cancel_text="Cancelar")

    def result_value(self) -> HotAuthorizationResult:
        return HotAuthorizationResult(
            authorizer_user=self.authorizer.value(),
            password=self.password.value(),
            reason=self.reason.value(),
        )


class CashDenominationDialog(FormDialog):
    """Capture denomination quantities for value handovers."""

    def __init__(
        self,
        parent=None,
        *,
        title: str = "Denominaciones",
        denominations: tuple[object, ...],
    ) -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        self._inputs: dict[str, IntegerInput] = {}
        for denomination in denominations:
            denomination_id = str(getattr(denomination, "id", ""))
            if not denomination_id:
                continue
            label = str(getattr(denomination, "display_name", "")) or str(
                getattr(denomination, "value", "")
            )
            field = IntegerInput(self, minimum=0)
            apply_tooltip(field, f"Cantidad de {label} incluida en la entrega.")
            self._inputs[denomination_id] = field
            self.form.addRow(label, field)
        self.add_button_box(ok_text="Preparar entrega", cancel_text="Cancelar")

    def _validate(self) -> bool:
        ok = any(field.value() > 0 for field in self._inputs.values())
        if not ok and self._inputs:
            first = next(iter(self._inputs.values()))
            first.setFocus()
        return ok

    def accept(self) -> None:
        if self._validate():
            super().accept()

    def result_value(self) -> CashDenominationCaptureResult:
        return CashDenominationCaptureResult(
            quantities={
                denomination_id: int(field.value())
                for denomination_id, field in self._inputs.items()
                if int(field.value()) > 0
            }
        )


class CashTextReasonDialog(FormDialog):
    """Capture a required text reason without monetary data."""

    def __init__(self, parent=None, *, title: str = "Motivo requerido") -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        self.reason = StandardTextArea(
            self,
            placeholder="Describe el motivo operativo para auditoria",
            max_length=500,
        )
        apply_tooltip(self.reason, "Motivo requerido; evita datos sensibles innecesarios.")
        self.form.addRow("Motivo", self.reason)
        self.add_button_box(ok_text="Continuar", cancel_text="Cancelar")

    def _validate(self) -> bool:
        ok = bool(self.reason.value())
        if not ok:
            self.reason.setFocus()
        return ok

    def accept(self) -> None:
        if self._validate():
            super().accept()

    def result_value(self) -> CashTextReasonResult:
        return CashTextReasonResult(reason=self.reason.value())


class SuspendCashShiftDialog(FormDialog):
    """Semantic dialog for suspending an operational shift."""

    def __init__(self, parent=None, *, shift) -> None:
        super().__init__(parent, title="Suspender turno", width=DialogMetrics.WIDTH_MD)
        context = QLabel(
            "\n".join((
                f"Turno: {display_code('TUR', getattr(shift, 'id', ''))}",
                f"Caja: {getattr(shift, 'register_name', '') or 'Caja activa'}",
                f"Cajon: {getattr(shift, 'drawer_name', '') or 'Cajon activo'}",
                f"Terminal: {getattr(shift, 'terminal_name', '') or 'Terminal activa'}",
                f"Cajero: {getattr(shift, 'cashier_name', '') or display_code('USR', getattr(shift, 'cashier_user_id', ''))}",
                f"Estado: {status_label(getattr(shift, 'status', ''))}",
            )),
            self,
        )
        context.setWordWrap(True)
        self.reason = StandardTextArea(
            self,
            placeholder="Indica por que se suspende el turno y cuando se retomara",
            max_length=700,
        )
        self.form.addRow("Contexto", context)
        self.form.addRow("Motivo operativo", self.reason)
        self.add_button_box(ok_text="Suspender turno", cancel_text="Cancelar")

    def accept(self) -> None:
        if not self.reason.value():
            self.reason.setFocus()
            return
        super().accept()

    def result_value(self) -> CashTextReasonResult:
        return CashTextReasonResult(reason=self.reason.value())


class ReprintCashDocumentDialog(FormDialog):
    """Semantic dialog for audited cash document reprints."""

    def __init__(self, parent=None, *, document_type: str, document) -> None:
        super().__init__(parent, title=f"Reimprimir {document_type}", width=DialogMetrics.WIDTH_MD)
        document_number = getattr(document, "document_number", "") or display_code(
            "DOC",
            getattr(document, "id", ""),
        )
        context = QLabel(
            "\n".join((
                f"Documento: {document_number}",
                f"Turno: {display_code('TUR', getattr(document, 'shift_id', ''))}",
                f"Generado: {getattr(document, 'generated_at', '') or 'Sin fecha visible'}",
                f"Final: {'Si' if getattr(document, 'is_final', False) else 'No'}",
            )),
            self,
        )
        context.setWordWrap(True)
        self.reason = StandardTextArea(
            self,
            placeholder="Explica por que se necesita una reimpresion auditada",
            max_length=700,
        )
        self.form.addRow("Contexto", context)
        self.form.addRow("Motivo de reimpresion", self.reason)
        self.add_button_box(ok_text="Reimprimir", cancel_text="Cancelar")

    def accept(self) -> None:
        if not self.reason.value():
            self.reason.setFocus()
            return
        super().accept()

    def result_value(self) -> CashTextReasonResult:
        return CashTextReasonResult(reason=self.reason.value())


class ResolveCashSyncConflictDialog(FormDialog):
    """Semantic dialog for resolving an offline-first sync conflict."""

    _STRATEGY_LABELS = {
        "RETRY_LOCAL": "Reintentar version local",
        "ACCEPT_REMOTE": "Aceptar version remota",
    }

    def __init__(self, parent=None, *, envelope: dict, strategy: str) -> None:
        super().__init__(parent, title="Resolver conflicto de sincronizacion", width=DialogMetrics.WIDTH_MD)
        context = QLabel(
            "\n".join((
                f"Estrategia: {self._STRATEGY_LABELS.get(strategy, strategy)}",
                f"Evento: {envelope.get('event_name', '') or 'Evento de Caja'}",
                f"Operacion: {display_code('OP', envelope.get('operation_id', ''))}",
                f"Secuencia: {envelope.get('sequence_no', '') or 'Sin secuencia visible'}",
                f"Estado: {status_label(envelope.get('state', ''))}",
                f"Ultimo error: {envelope.get('last_error', '') or 'Sin detalle'}",
            )),
            self,
        )
        context.setWordWrap(True)
        self.reason = StandardTextArea(
            self,
            placeholder="Describe el criterio operativo usado para resolver el conflicto",
            max_length=700,
        )
        self.form.addRow("Contexto", context)
        self.form.addRow("Motivo auditado", self.reason)
        self.add_button_box(ok_text="Resolver conflicto", cancel_text="Cancelar")

    def accept(self) -> None:
        if not self.reason.value():
            self.reason.setFocus()
            return
        super().accept()

    def result_value(self) -> CashTextReasonResult:
        return CashTextReasonResult(reason=self.reason.value())


class ExplainCashDifferenceDialog(FormDialog):
    """Semantic dialog for cashier/supervisor explanation of a detected difference."""

    def __init__(self, parent=None, *, difference) -> None:
        super().__init__(parent, title="Explicar diferencia", width=DialogMetrics.WIDTH_MD)
        amount = _money(getattr(difference, "amount", 0))
        expected = _money(getattr(difference, "expected_amount", 0))
        counted = _money(getattr(difference, "counted_amount", 0))
        context = QLabel(
            "\n".join((
                f"Diferencia detectada: {amount}",
                f"Turno: {display_code('TUR', getattr(difference, 'shift_id', ''))}",
                f"Esperado: {expected}",
                f"Contado: {counted}",
                f"Severidad: {status_label(getattr(difference, 'severity', ''))}",
            )),
            self,
        )
        context.setWordWrap(True)
        self.explanation = StandardTextArea(
            self,
            placeholder="Describe que ocurrio y agrega evidencia operacional si aplica",
            max_length=700,
        )
        self.form.addRow("Contexto", context)
        self.form.addRow("Explicacion", self.explanation)
        self.add_button_box(ok_text="Guardar explicacion", cancel_text="Cancelar")

    def accept(self) -> None:
        if not self.explanation.value():
            self.explanation.setFocus()
            return
        super().accept()

    def result_value(self) -> CashTextReasonResult:
        return CashTextReasonResult(reason=self.explanation.value())


class ResolveCashDifferenceDialog(FormDialog):
    """Semantic dialog for resolving a reviewed cash difference."""

    def __init__(self, parent=None, *, difference) -> None:
        super().__init__(parent, title="Resolver diferencia", width=DialogMetrics.WIDTH_MD)
        context = QLabel(
            "\n".join((
                f"Diferencia: {_money(getattr(difference, 'amount', 0))}",
                f"Estado: {status_label(getattr(difference, 'status', ''))}",
                f"Severidad: {status_label(getattr(difference, 'severity', ''))}",
                f"Explicacion previa: {getattr(difference, 'explanation', '') or 'Sin explicacion'}",
                f"Recurrencia: {getattr(difference, 'recurrence_count', 0)}",
            )),
            self,
        )
        context.setWordWrap(True)
        self.resolution = StandardTextArea(
            self,
            placeholder="Indica la resolucion operacional y el criterio aplicado",
            max_length=700,
        )
        self.form.addRow("Contexto", context)
        self.form.addRow("Resolucion", self.resolution)
        self.add_button_box(ok_text="Resolver diferencia", cancel_text="Cancelar")

    def accept(self) -> None:
        if not self.resolution.value():
            self.resolution.setFocus()
            return
        super().accept()

    def result_value(self) -> CashTextReasonResult:
        return CashTextReasonResult(reason=self.resolution.value())


class CashHandoverDenominationDialog(FormDialog):
    """Semantic denomination confirmation for value delivery/reception."""

    def __init__(
        self,
        parent=None,
        *,
        title: str,
        handover,
        denominations: tuple[object, ...],
    ) -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        context = QLabel(
            "\n".join((
                f"Entrega: {display_code('ENT', getattr(handover, 'id', ''))}",
                f"Turno: {display_code('TUR', getattr(handover, 'shift_id', ''))}",
                f"Monto preparado: {_money(getattr(handover, 'amount', 0))}",
                f"Estado: {status_label(getattr(handover, 'status', ''))}",
                f"Preparo: {display_code('USR', getattr(handover, 'prepared_by', ''))}",
            )),
            self,
        )
        context.setWordWrap(True)
        self.form.addRow("Contexto", context)
        self._inputs: dict[str, IntegerInput] = {}
        for denomination in denominations:
            denomination_id = str(getattr(denomination, "id", ""))
            if not denomination_id:
                continue
            label = str(getattr(denomination, "display_name", "")) or str(
                getattr(denomination, "value", "")
            )
            field = IntegerInput(self, minimum=0)
            self._inputs[denomination_id] = field
            self.form.addRow(label, field)
        self.add_button_box(ok_text="Confirmar", cancel_text="Cancelar")

    def accept(self) -> None:
        if not any(field.value() > 0 for field in self._inputs.values()):
            if self._inputs:
                next(iter(self._inputs.values())).setFocus()
            return
        super().accept()

    def result_value(self) -> CashHandoverDenominationResult:
        return CashHandoverDenominationResult(
            quantities={
                denomination_id: int(field.value())
                for denomination_id, field in self._inputs.items()
                if int(field.value()) > 0
            }
        )


class DisputeCashHandoverDialog(FormDialog):
    """Semantic dialog for a disputed value handover."""

    def __init__(self, parent=None, *, handover) -> None:
        super().__init__(parent, title="Reportar disputa", width=DialogMetrics.WIDTH_MD)
        context = QLabel(
            "\n".join((
                f"Entrega: {display_code('ENT', getattr(handover, 'id', ''))}",
                f"Monto: {_money(getattr(handover, 'amount', 0))}",
                f"Estado: {status_label(getattr(handover, 'status', ''))}",
                f"Entrego: {display_code('USR', getattr(handover, 'delivered_by', '')) if getattr(handover, 'delivered_by', '') else 'Pendiente'}",
                f"Recibio: {display_code('USR', getattr(handover, 'received_by', '')) if getattr(handover, 'received_by', '') else 'Pendiente'}",
            )),
            self,
        )
        context.setWordWrap(True)
        self.reason = StandardTextArea(
            self,
            placeholder="Describe la diferencia o disputa detectada",
            max_length=700,
        )
        self.form.addRow("Contexto", context)
        self.form.addRow("Motivo de disputa", self.reason)
        self.add_button_box(ok_text="Reportar disputa", cancel_text="Cancelar")

    def accept(self) -> None:
        if not self.reason.value():
            self.reason.setFocus()
            return
        super().accept()

    def result_value(self) -> CashTextReasonResult:
        return CashTextReasonResult(reason=self.reason.value())


class CashDeviceActionDialog(FormDialog):
    """Semantic reason dialog for hardware lifecycle and drawer override actions."""

    def __init__(
        self,
        parent=None,
        *,
        title: str,
        device,
        placeholder: str,
        ok_text: str = "Continuar",
    ) -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        context = QLabel(
            "\n".join((
                f"Dispositivo: {getattr(device, 'name', '') or 'Seleccionado'}",
                f"Sucursal: {getattr(device, 'branch_name', '') or 'No especificada'}",
                f"Asignacion: {getattr(device, 'assignment', '') or 'Sin asignacion'}",
                f"Estado: {status_label(getattr(device, 'status', ''))}",
                f"Hardware: {getattr(device, 'hardware_status', '') or 'No verificado'}",
            )),
            self,
        )
        context.setWordWrap(True)
        self.reason = StandardTextArea(self, placeholder=placeholder, max_length=700)
        self.form.addRow("Contexto", context)
        self.form.addRow("Motivo", self.reason)
        self.add_button_box(ok_text=ok_text, cancel_text="Cancelar")

    def accept(self) -> None:
        if not self.reason.value():
            self.reason.setFocus()
            return
        super().accept()

    def result_value(self) -> CashTextReasonResult:
        return CashTextReasonResult(reason=self.reason.value())


class CashDeviceDialog(FormDialog):
    """Capture device creation data without exposing UUIDs to the operator."""

    _KIND_LABELS = {
        "register": "Caja",
        "drawer": "Cajón",
        "terminal": "Terminal",
    }

    def __init__(
        self,
        parent=None,
        *,
        kind: str,
        registers: tuple[object, ...] = (),
        title: str = "Nuevo dispositivo",
    ) -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        self._kind = kind
        self.name = StandardLineEdit(
            self,
            placeholder=f"Nombre operativo de {self._KIND_LABELS.get(kind, 'dispositivo').lower()}",
            max_length=120,
            required=True,
        )
        self.register = QComboBox(self)
        self.register.setObjectName("standardComboBox")
        self.register.addItem("Selecciona una caja", "")
        for row in registers:
            register_id = str(getattr(row, "id", "") or "")
            if not register_id:
                continue
            label = str(getattr(row, "name", "") or register_id)
            branch = str(getattr(row, "branch_name", "") or "")
            if branch:
                label = f"{label} — {branch}"
            self.register.addItem(label, register_id)
        apply_tooltip(self.name, "Nombre visible para operación y auditoría.")
        apply_tooltip(self.register, "Caja física a la que quedará asignado este dispositivo.")
        self.form.addRow("Tipo", QLabel(self._KIND_LABELS.get(kind, kind), self))
        self.form.addRow("Nombre", self.name)
        if kind in {"drawer", "terminal"}:
            self.form.addRow("Caja", self.register)
        else:
            self.register.setVisible(False)
        self.add_button_box(ok_text="Crear", cancel_text="Cancelar")

    def _validate(self) -> bool:
        if not self.name.value():
            self.name.setFocus()
            return False
        if self._kind in {"drawer", "terminal"} and not self.register.currentData():
            self.register.setFocus()
            return False
        return True

    def accept(self) -> None:
        if self._validate():
            super().accept()

    def result_value(self) -> CashDeviceDialogResult:
        register_id = self.register.currentData()
        return CashDeviceDialogResult(
            name=self.name.value(),
            register_id=str(register_id) if register_id else None,
        )


class CashShiftOpeningDialog(FormDialog):
    """Capture opening float for the active register/drawer/terminal assignment."""

    def __init__(self, parent=None, *, title: str = "Abrir turno") -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_SM)
        self.opening_amount = MoneyInput(self)
        apply_tooltip(
            self.opening_amount,
            "Fondo inicial recibido para el turno activo; debe coincidir con el documento origen.",
        )
        self.form.addRow("Fondo inicial", self.opening_amount)
        self.add_button_box(ok_text="Abrir turno", cancel_text="Cancelar")

    def result_value(self) -> CashShiftOpeningResult:
        return CashShiftOpeningResult(opening_amount=self.opening_amount.decimal_value())


class CashConfigurationDialog(FormDialog):
    """Capture a canonical, effective Caja configuration entry."""

    def __init__(self, parent=None, *, section: str,
                 title: str = "Nueva configuracion de Caja") -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        self._section = section
        self.name = StandardLineEdit(
            self,
            placeholder="Clave, codigo o evento canonico",
            max_length=120,
            required=True,
        )
        self.value = StandardLineEdit(
            self,
            placeholder="Valor. En limites usa: umbral / maximo",
            max_length=180,
            required=True,
        )
        self.scope_type = QComboBox(self)
        self.scope_type.setObjectName("standardComboBox")
        for value in ("SYSTEM", "COMPANY", "BRANCH", "REGISTER", "USER"):
            self.scope_type.addItem(scope_label(value), value)
        self.scope_id = StandardLineEdit(
            self,
            placeholder="Buscar o seleccionar entidad del alcance",
            max_length=80,
        )
        self.effective_from = StandardLineEdit(
            self,
            placeholder="Vigente desde; vacio = ahora",
            max_length=40,
        )
        self.effective_to = StandardLineEdit(
            self,
            placeholder="Vigente hasta opcional",
            max_length=40,
        )
        apply_tooltip(self.name, "Clave canonica del ajuste, denominacion, medio, limite o alerta.")
        apply_tooltip(self.value, "Valor persistido por Caja; el backend valida formato y alcance.")
        apply_tooltip(self.scope_type, "Jerarquia efectiva de configuracion.")
        apply_tooltip(self.scope_id, "Requerido para alcances especificos como sucursal, caja o usuario.")
        self.form.addRow("Seccion", QLabel(section, self))
        self.form.addRow("Nombre", self.name)
        self.form.addRow("Valor", self.value)
        self.form.addRow("Aplicar en", self.scope_type)
        self.form.addRow("Entidad", self.scope_id)
        self.form.addRow("Vigente desde", self.effective_from)
        self.form.addRow("Vigente hasta", self.effective_to)
        self.scope_type.currentIndexChanged.connect(self._sync_scope_controls)
        self._sync_scope_controls()
        self.add_button_box(ok_text="Guardar", cancel_text="Cancelar")

    def _sync_scope_controls(self) -> None:
        specific = self.scope_type.currentData() != "SYSTEM"
        self.scope_id.setEnabled(specific)
        if not specific:
            self.scope_id.clear()
            self.scope_id.setPlaceholderText("No aplica para todo el sistema")
        else:
            self.scope_id.setPlaceholderText(
                f"Buscar {scope_label(self.scope_type.currentData()).lower()}"
            )

    def _validate(self) -> bool:
        if not self.name.value():
            self.name.setFocus()
            return False
        if not self.value.value():
            self.value.setFocus()
            return False
        if self.scope_type.currentData() != "SYSTEM" and not self.scope_id.value():
            self.scope_id.setFocus()
            return False
        return True

    def accept(self) -> None:
        if self._validate():
            super().accept()

    def result_value(self) -> CashConfigurationDialogResult:
        scope_id = self.scope_id.value() or None
        return CashConfigurationDialogResult(
            name=self.name.value(),
            value=self.value.value(),
            scope_type=str(self.scope_type.currentData() or "SYSTEM"),
            scope_id=scope_id,
            effective_from=self.effective_from.value() or None,
            effective_to=self.effective_to.value() or None,
        )


class CashRefundDialog(FormDialog):
    """Capture the Cash-side execution data for an already authorized sale refund."""

    _SETTLEMENTS = (
        ("CASH", "Efectivo"),
        ("CARD", "Tarjeta"),
        ("BANK_TRANSFER", "Transferencia"),
        ("LOYALTY_POINTS", "Puntos"),
        ("VOUCHER", "Vale"),
        ("STORE_CREDIT", "Saldo a favor"),
    )

    def __init__(self, parent=None, *, title: str = "Ejecutar reembolso") -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        self.refund_id = StandardLineEdit(
            self, placeholder="Buscar autorizacion, folio o ticket", max_length=80, required=True)
        self.sale_id = StandardLineEdit(
            self, placeholder="Venta, folio o ticket seleccionado", max_length=80, required=True)
        self.authorized_by = StandardLineEdit(
            self, placeholder="Nombre del autorizador", max_length=80, required=True)
        self.reason = StandardTextArea(
            self, placeholder="Motivo autorizado por Ventas", max_length=500)
        self._original_inputs: dict[str, MoneyInput] = {}
        self._refund_inputs: dict[str, MoneyInput] = {}
        self.form.addRow("Autorizacion", self.refund_id)
        self.form.addRow("Venta / folio", self.sale_id)
        self.form.addRow("Autorizado por", self.authorized_by)
        self.form.addRow("Motivo", self.reason)
        for code, label in self._SETTLEMENTS:
            original = MoneyInput(self)
            refund = MoneyInput(self)
            self._original_inputs[code] = original
            self._refund_inputs[code] = refund
            self.form.addRow(f"Original {label}", original)
            self.form.addRow(f"Reembolso {label}", refund)
        self.add_button_box(ok_text="Ejecutar", cancel_text="Cancelar")

    def _validate(self) -> bool:
        widgets = (self.refund_id, self.sale_id, self.authorized_by)
        for widget in widgets:
            if not widget.value():
                widget.setFocus()
                return False
        if not self.reason.value():
            self.reason.setFocus()
            return False
        if not any(field.decimal_value() > 0 for field in self._refund_inputs.values()):
            next(iter(self._refund_inputs.values())).setFocus()
            return False
        return True

    def accept(self) -> None:
        if self._validate():
            super().accept()

    def result_value(self) -> CashRefundDialogResult:
        return CashRefundDialogResult(
            refund_id=self.refund_id.value(),
            sale_id=self.sale_id.value(),
            authorized_by=self.authorized_by.value(),
            reason=self.reason.value(),
            original_payment_lines={
                code: field.decimal_value()
                for code, field in self._original_inputs.items()
                if field.decimal_value() > 0
            },
            refund_lines={
                code: field.decimal_value()
                for code, field in self._refund_inputs.items()
                if field.decimal_value() > 0
            },
        )


class CashPrintPreviewDialog(StandardDialog):
    """Small themed dialog used before sending X/Z cut documents to a printer."""

    def __init__(self, parent=None, *, title: str, summary: str) -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        label = QLabel(summary, self)
        label.setWordWrap(True)
        label.setProperty("role", "muted")
        self.content_layout().addWidget(label)
        self.add_button_box(ok_text="Imprimir", cancel_text="Cerrar")
