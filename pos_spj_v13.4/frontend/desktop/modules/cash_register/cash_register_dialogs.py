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
from frontend.desktop.components.selection_controls import StandardCheckBox, StandardComboBox
from frontend.desktop.components.text_inputs import PasswordInput, StandardLineEdit, StandardTextArea
from frontend.desktop.components.tooltip import apply_tooltip
from backend.application.cash_register.notification_text import ALERTABLE_EVENTS
from frontend.desktop.modules.cash_register.presentation import (
    LIMIT_OPERATION_LABELS,
    display_code,
    status_label,
)
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


class CashCatalogDialog(FormDialog):
    """Alta tipada de un catálogo de Caja: cada sección pide SUS campos.

    Reemplaza al diálogo de texto libre «nombre / valor» (medido el 2026-10-07):
    para que un límite aplicara había que saber teclear ``MANUAL_MOVEMENT`` y
    ``1000 / 5000``; motivos y tolerancias ni siquiera tenían escritor. Aquí las
    opciones son listas cerradas, los importes `MoneyInput` y los conteos
    `IntegerInput`; el backend vuelve a validar todo.
    """

    TITLES = {
        "denominations": "Nueva denominacion",
        "reasons": "Nuevo motivo de movimiento",
        "limits": "Nuevo limite de operacion",
        "tolerances": "Nueva politica de diferencias",
        "alerts": "Nuevo aviso",
    }
    LIMIT_OPERATIONS = tuple(LIMIT_OPERATION_LABELS.items())
    REASON_TYPES = (
        ("MANUAL_INCOME", "Ingreso manual"),
        ("MANUAL_WITHDRAWAL", "Retiro manual"),
        ("SAFE_DROP", "Retiro a boveda"),
    )
    CHANNELS = (("IN_APP", "Aviso en el sistema"), ("WHATSAPP", "WhatsApp"))
    SEVERITIES = (("WARNING", "Advertencia"), ("CRITICAL", "Critica"), ("INFO", "Informativa"))

    def __init__(self, parent=None, *, section: str) -> None:
        if section not in self.TITLES:
            raise ValueError(f"Seccion sin alta tipada: {section}")
        super().__init__(parent, title=self.TITLES[section], width=DialogMetrics.WIDTH_MD)
        self._section = section
        self._error = ""
        getattr(self, f"_build_{section}")()
        self.error_label = QLabel("", self)
        self.error_label.setObjectName("formErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.form.addRow(self.error_label)
        self.add_button_box(ok_text="Guardar", cancel_text="Cancelar")

    # ── secciones ────────────────────────────────────────────────────────
    def _build_denominations(self) -> None:
        self.currency = StandardLineEdit(self, placeholder="MXN", max_length=3, required=True)
        self.currency.setText("MXN")
        self.value = MoneyInput(self)
        self.label = StandardLineEdit(self, placeholder="Ej. Billete $500", max_length=60,
                                      required=True)
        self.sort_order = IntegerInput(self, minimum=0, maximum=999)
        apply_tooltip(self.value, "Valor facial; el conteo ciego suma cantidad x valor.")
        apply_tooltip(self.sort_order, "Posicion en el conteo (0 = primero).")
        self.form.addRow("Moneda", self.currency)
        self.form.addRow("Valor", self.value)
        self.form.addRow("Nombre visible", self.label)
        self.form.addRow("Orden", self.sort_order)

    def _build_reasons(self) -> None:
        self.movement_type = StandardComboBox(self, accessible_name="Tipo de movimiento")
        for value, label in self.REASON_TYPES:
            self.movement_type.addItem(label, value)
        self.code = StandardLineEdit(self, placeholder="Ej. DOTACION_CAMBIO", max_length=40,
                                     required=True)
        self.label = StandardLineEdit(self, placeholder="Ej. Dotacion de cambio", max_length=80,
                                      required=True)
        self.requires_authorization = StandardCheckBox(
            "Siempre requiere autorizacion de otra persona", self)
        apply_tooltip(self.code, "Codigo unico del motivo; aparece en auditoria.")
        apply_tooltip(self.requires_authorization,
                      "Aunque el monto este dentro del limite, pedira autorizador con clave.")
        self.form.addRow("Movimiento", self.movement_type)
        self.form.addRow("Codigo", self.code)
        self.form.addRow("Nombre visible", self.label)
        self.form.addRow("", self.requires_authorization)

    def _build_limits(self) -> None:
        self.operation = StandardComboBox(self, accessible_name="Operacion")
        for value, label in self.LIMIT_OPERATIONS:
            self.operation.addItem(label, value)
        self.approval_threshold = MoneyInput(self)
        self.hard_cap = MoneyInput(self)
        apply_tooltip(self.approval_threshold,
                      "Arriba de este monto se pide autorizacion de otra persona.")
        apply_tooltip(self.hard_cap, "Ningun movimiento puede superar este monto.")
        self.form.addRow("Operacion", self.operation)
        self.form.addRow("Autorizacion arriba de", self.approval_threshold)
        self.form.addRow("Tope maximo", self.hard_cap)

    def _build_tolerances(self) -> None:
        self.tolerance = MoneyInput(self)
        self.critical = MoneyInput(self)
        self.window_days = IntegerInput(self, minimum=0, maximum=365)
        self.recurrence = IntegerInput(self, minimum=0, maximum=99)
        self.channels = {}
        apply_tooltip(self.tolerance,
                      "Hasta este monto la diferencia se registra pero no pide revision.")
        apply_tooltip(self.critical, "Desde este monto la diferencia es critica y alerta.")
        apply_tooltip(self.recurrence,
                      "Cuantas diferencias del mismo cajero en la ventana la vuelven critica.")
        self.form.addRow("Tolerancia", self.tolerance)
        self.form.addRow("Critica desde", self.critical)
        self.form.addRow("Ventana de reincidencia (dias)", self.window_days)
        self.form.addRow("Diferencias para reincidencia", self.recurrence)
        for value, label in self.CHANNELS:
            box = StandardCheckBox(label, self)
            box.setChecked(True)
            self.channels[value] = box
            self.form.addRow("Avisar por" if value == "IN_APP" else "", box)

    def _build_alerts(self) -> None:
        self.event = StandardComboBox(self, accessible_name="Evento")
        for value, label in ALERTABLE_EVENTS.items():
            self.event.addItem(label, value)
        self.severity = StandardComboBox(self, accessible_name="Severidad")
        for value, label in self.SEVERITIES:
            self.severity.addItem(label, value)
        self.channels = {}
        apply_tooltip(self.event,
                      "Si ya hay un aviso para este evento, este lo reemplaza y conserva "
                      "a sus destinatarios.")
        self.form.addRow("Avisar cuando", self.event)
        self.form.addRow("Severidad", self.severity)
        for value, label in self.CHANNELS:
            box = StandardCheckBox(label, self)
            box.setChecked(True)
            self.channels[value] = box
            self.form.addRow("Avisar por" if value == "IN_APP" else "", box)

    # ── validación y resultado ───────────────────────────────────────────
    def _problem(self) -> str:
        if self._section == "denominations":
            if len(self.currency.value().strip()) != 3:
                return "La moneda es un codigo de 3 letras (MXN)."
            if self.value.decimal_value() <= 0:
                return "Captura el valor de la denominacion."
            if not self.label.value().strip():
                return "Captura el nombre visible."
        elif self._section == "reasons":
            if not self.code.value().strip() or not self.label.value().strip():
                return "Captura codigo y nombre del motivo."
        elif self._section == "limits":
            if self.hard_cap.decimal_value() <= 0:
                return "Captura el tope maximo."
            if self.hard_cap.decimal_value() < self.approval_threshold.decimal_value():
                return "El tope no puede ser menor que el monto que pide autorizacion."
        elif self._section == "tolerances":
            if self.critical.decimal_value() < self.tolerance.decimal_value():
                return "El monto critico no puede ser menor que la tolerancia."
            if self.window_days.value() < 1 or self.recurrence.value() < 1:
                return "La ventana y el numero de reincidencias deben ser al menos 1."
            if not any(box.isChecked() for box in self.channels.values()):
                return "Elige al menos un canal de aviso."
        elif self._section == "alerts":
            if not any(box.isChecked() for box in self.channels.values()):
                return "Elige al menos un canal de aviso."
        return ""

    def problem(self) -> str:
        return self._problem()

    def accept(self) -> None:
        self._error = self._problem()
        self.error_label.setText(self._error)
        self.error_label.setVisible(bool(self._error))
        if self._error:
            return
        super().accept()

    def result_fields(self) -> dict[str, object]:
        if self._section == "denominations":
            return {"currency_code": self.currency.value().strip().upper(),
                    "value": self.value.decimal_value(),
                    "display_name": self.label.value().strip(),
                    "sort_order": int(self.sort_order.value())}
        if self._section == "reasons":
            return {"movement_type": str(self.movement_type.currentData()),
                    "code": self.code.value().strip().upper(),
                    "display_name": self.label.value().strip(),
                    "requires_authorization": self.requires_authorization.isChecked()}
        if self._section == "limits":
            return {"operation_type": str(self.operation.currentData()),
                    "approval_threshold": self.approval_threshold.decimal_value(),
                    "hard_cap": self.hard_cap.decimal_value()}
        if self._section == "alerts":
            return {"event_name": str(self.event.currentData()),
                    "severity": str(self.severity.currentData()),
                    "channels": tuple(v for v, box in self.channels.items() if box.isChecked())}
        return {"tolerance": self.tolerance.decimal_value(),
                "critical_threshold": self.critical.decimal_value(),
                "recurrence_window_days": int(self.window_days.value()),
                "recurrence_threshold": int(self.recurrence.value()),
                "channels": tuple(v for v, box in self.channels.items() if box.isChecked())}


class CashAlertRecipientDialog(FormDialog):
    """Quién recibe un aviso de Caja: un usuario (aviso en el sistema) o un
    teléfono (WhatsApp). Sólo ofrece los canales que el aviso elegido usa."""

    def __init__(self, parent=None, *, alerts, users) -> None:
        super().__init__(parent, title="Nuevo destinatario", width=DialogMetrics.WIDTH_MD)
        self._alerts = {alert.id: alert for alert in alerts}
        self._error = ""
        self.alert = StandardComboBox(self, accessible_name="Aviso")
        for alert in alerts:
            self.alert.addItem(ALERTABLE_EVENTS.get(alert.event_name, alert.event_name), alert.id)
        self.channel = StandardComboBox(self, accessible_name="Canal")
        self.user = StandardComboBox(self, accessible_name="Usuario")
        for user in users:
            self.user.addItem(user.name, user.id)
        self.phone = StandardLineEdit(self, placeholder="+52 y 10 digitos, ej. +525512345678",
                                      max_length=16)
        self.name = StandardLineEdit(self, placeholder="Nombre de quien recibe", max_length=80)
        apply_tooltip(self.phone, "Numero con lada internacional; sin espacios ni guiones.")
        self.form.addRow("Aviso", self.alert)
        self.form.addRow("Canal", self.channel)
        self.form.addRow("Usuario", self.user)
        self.form.addRow("WhatsApp", self.phone)
        self.form.addRow("Nombre", self.name)
        self.error_label = QLabel("", self)
        self.error_label.setObjectName("formErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.form.addRow(self.error_label)
        self.alert.currentIndexChanged.connect(self._sync_channels)
        self.channel.currentIndexChanged.connect(self._sync_fields)
        self._sync_channels()
        self.add_button_box(ok_text="Agregar", cancel_text="Cancelar")

    def _sync_channels(self, _index: int = 0) -> None:
        alert = self._alerts.get(self.alert.currentData())
        self.channel.clear()
        for value, label in CashCatalogDialog.CHANNELS:
            if alert is not None and value in alert.channels:
                self.channel.addItem(label, value)
        self._sync_fields()

    def _sync_fields(self, _index: int = 0) -> None:
        whatsapp = self.channel.currentData() == "WHATSAPP"
        self.user.setEnabled(not whatsapp)
        self.phone.setEnabled(whatsapp)
        self.name.setEnabled(whatsapp)

    def problem(self) -> str:
        if not self._alerts:
            return "Primero crea un aviso en la pestana Avisos."
        if self.channel.currentData() is None:
            return "Ese aviso no tiene canales."
        if self.channel.currentData() == "WHATSAPP":
            phone = self.phone.value().strip().replace(" ", "")
            if not phone.startswith("+") or not phone[1:].isdigit() or not 8 <= len(phone[1:]) <= 15:
                return "Escribe el WhatsApp con lada internacional, ej. +525512345678."
            if not self.name.value().strip():
                return "Escribe el nombre de quien recibe el WhatsApp."
        elif self.user.currentData() is None:
            return "No hay usuarios activos para elegir."
        return ""

    def accept(self) -> None:
        self._error = self.problem()
        self.error_label.setText(self._error)
        self.error_label.setVisible(bool(self._error))
        if self._error:
            return
        super().accept()

    def result_fields(self) -> dict[str, str]:
        whatsapp = self.channel.currentData() == "WHATSAPP"
        return {
            "alert_rule_id": str(self.alert.currentData()),
            "channel": str(self.channel.currentData()),
            "address": (self.phone.value().strip().replace(" ", "") if whatsapp
                        else str(self.user.currentData())),
            "display_name": self.name.value().strip() if whatsapp else "",
        }


class CashPrintPreviewDialog(StandardDialog):
    """Small themed dialog used before sending X/Z cut documents to a printer."""

    def __init__(self, parent=None, *, title: str, summary: str) -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        label = QLabel(summary, self)
        label.setWordWrap(True)
        label.setProperty("role", "muted")
        self.content_layout().addWidget(label)
        self.add_button_box(ok_text="Imprimir", cancel_text="Cerrar")
