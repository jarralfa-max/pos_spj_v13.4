"""Presenter bridge between Caja desktop UI and backend services.

The workspace remains a thin PyQt shell: it asks this presenter for session
state, capabilities and backend query/use-case dependencies. No SQL, no commits
and no legacy permission translation live here.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from frontend.desktop.modules.cash_register.capability_resolver import resolve_cash_capabilities
from frontend.desktop.modules.cash_register.view_models import CashCapabilities


class CashContextError(RuntimeError):
    """Raised when a Caja operation lacks required session/device context."""


class CashRegisterPresenter:
    def __init__(
        self,
        *,
        session_context,
        query_services: dict[str, object] | None = None,
        use_cases: dict[str, object] | None = None,
        command_handlers: dict[str, Callable[..., object]] | None = None,
        active_context_provider: Callable[[], dict[str, object | None]] | None = None,
        active_shift_provider: Callable[[], str | None] | None = None,
        active_count_context_provider: Callable[[], tuple[str, str, str] | None] | None = None,
    ) -> None:
        self._session = session_context
        self._query_services = dict(query_services or {})
        self._use_cases = dict(use_cases or {})
        self._command_handlers = dict(command_handlers or {})
        self._active_context_provider = active_context_provider or (lambda: {})
        self._active_shift_provider = active_shift_provider or (lambda: None)
        self._active_count_context_provider = active_count_context_provider or (lambda: None)

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> CashCapabilities:
        return resolve_cash_capabilities(self.can)

    def session_summary(self) -> dict[str, str]:
        return {
            "user_id": str(getattr(self._session, "user_id", "") or ""),
            "user": str(getattr(self._session, "display_name", None)
                        or getattr(self._session, "nombre_completo", None)
                        or getattr(self._session, "username", None)
                        or getattr(self._session, "usuario", None)
                        or "Sesion activa"),
            "branch_id": str(getattr(self._session, "active_branch_id", None)
                             or getattr(self._session, "branch_id", None)
                             or ""),
            "branch": str(getattr(self._session, "active_branch_name", None)
                          or getattr(self._session, "sucursal_nombre", None)
                          or ""),
        }

    def _require(self, value: object | None, label: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise CashContextError(f"Contexto de Caja requerido no disponible: {label}")
        return text

    def _context_value(self, key: str) -> object | None:
        context = self._active_context_provider() or {}
        return context.get(key)

    def actor_user_id(self) -> str:
        if not bool(getattr(self._session, "is_active", False)):
            raise CashContextError("Contexto de Caja requerido no disponible: sesion activa")
        return self._require(getattr(self._session, "user_id", None), "usuario")

    def active_branch_id(self) -> str:
        return self._require(
            getattr(self._session, "active_branch_id", None)
            or getattr(self._session, "branch_id", None)
            or self._context_value("branch_id"),
            "sucursal activa",
        )

    def active_register_id(self) -> str:
        return self._require(self._context_value("cash_register_id"), "caja activa")

    def active_drawer_id(self) -> str:
        return self._require(self._context_value("cash_drawer_id"), "cajon activo")

    def active_terminal_id(self) -> str:
        return self._require(self._context_value("pos_terminal_id"), "terminal activa")

    def active_sync_device_id(self) -> str:
        return self._require(self._context_value("sync_device_id"), "dispositivo de sincronizacion")

    def optional_active_shift_id(self) -> str | None:
        value = self._active_shift_provider()
        return str(value) if value else None

    def active_shift_id(self) -> str:
        return self._require(
            self._context_value("cash_shift_id") or self.optional_active_shift_id(),
            "turno activo",
        )

    def active_count_context(self) -> tuple[str, str, str] | None:
        return self._active_count_context_provider()

    def query_service(self, key: str):
        return self._query_services.get(key)

    def start_blind_count(self):
        handler = self._command_handlers.get("start_blind_count")
        if handler is None:
            raise CashContextError("Comando de conteo no disponible: iniciar")
        return handler(
            shift_id=self.active_shift_id(),
            branch_id=self.active_branch_id(),
            counter_user_id=self.actor_user_id(),
        )

    def capture_blind_count_denomination(self, *, count_id: str,
                                         denomination_id: str, quantity: int):
        handler = self._command_handlers.get("capture_blind_count_denomination")
        if handler is None:
            raise CashContextError("Comando de conteo no disponible: capturar")
        return handler(
            count_id=count_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            denomination_id=denomination_id,
            quantity=quantity,
        )

    def confirm_blind_count(self, *, count_id: str):
        handler = self._command_handlers.get("confirm_blind_count")
        if handler is None:
            raise CashContextError("Comando de conteo no disponible: confirmar")
        return handler(
            count_id=count_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def create_cash_device(self, *, kind: str, name: str,
                           register_id: str | None = None):
        handler = self._command_handlers.get("create_cash_device")
        if handler is None:
            raise CashContextError("Comando de hardware no disponible: crear")
        return handler(
            kind=kind,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            name=name,
            register_id=register_id,
        )

    def configure_cash_register(
        self,
        *,
        section: str,
        name: str,
        value: str,
        scope_type: str = "SYSTEM",
        scope_id: str | None = None,
        effective_from: str | None = None,
        effective_to: str | None = None,
    ):
        handler = self._command_handlers.get("configure_cash_register")
        if handler is None:
            raise CashContextError("Comando de configuracion no disponible")
        return handler(
            section=section,
            name=name,
            value=value,
            scope_type=scope_type,
            scope_id=scope_id,
            effective_from=effective_from,
            effective_to=effective_to,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def set_cash_device_status(self, *, kind: str, device_id: str,
                               activate: bool, reason: str = "",
                               target_status: str | None = None):
        handler = self._command_handlers.get("set_cash_device_status")
        if handler is None:
            raise CashContextError("Comando de hardware no disponible: estado")
        return handler(
            kind=kind,
            device_id=device_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            activate=activate,
            reason=reason,
            target_status=target_status,
        )

    def diagnose_cash_hardware(self, *, device_id: str):
        handler = self._command_handlers.get("diagnose_cash_hardware")
        if handler is None:
            raise CashContextError("Comando de hardware no disponible: diagnosticar")
        return handler(
            device_id=device_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def open_cash_drawer_hardware(self, *, drawer_id: str, reason: str,
                                  sale_id: str | None = None):
        handler = self._command_handlers.get("open_cash_drawer_hardware")
        if handler is None:
            raise CashContextError("Comando de cajon no disponible: abrir")
        return handler(
            drawer_id=drawer_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            reason=reason,
            sale_id=sale_id,
        )

    def register_cash_movement(
        self,
        *,
        movement_type: str,
        amount: Decimal,
        concept: str,
        reason_code: str | None = None,
        authorized_by: str | None = None,
    ):
        handler = self._command_handlers.get("register_cash_movement")
        if handler is None:
            raise CashContextError("Comando de ledger no disponible: registrar movimiento")
        return handler(
            shift_id=self.active_shift_id(),
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            movement_type=movement_type,
            amount=amount,
            concept=concept,
            reason_code=reason_code,
            authorized_by=authorized_by,
        )

    def open_cash_shift(self, *, opening_amount: Decimal):
        handler = self._command_handlers.get("open_cash_shift")
        if handler is None:
            raise CashContextError("Comando de turno no disponible: apertura")
        return handler(
            branch_id=self.active_branch_id(),
            register_id=self.active_register_id(),
            drawer_id=self.active_drawer_id(),
            terminal_id=self.active_terminal_id(),
            cashier_user_id=self.actor_user_id(),
            actor_user_id=self.actor_user_id(),
            opening_amount=opening_amount,
        )

    def suspend_cash_shift(self, *, shift_id: str | None = None, reason: str):
        handler = self._command_handlers.get("suspend_cash_shift")
        if handler is None:
            raise CashContextError("Comando de turno no disponible: suspender")
        return handler(
            shift_id=shift_id or self.active_shift_id(),
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            reason=reason,
        )

    def resume_cash_shift(self, *, shift_id: str | None = None):
        handler = self._command_handlers.get("resume_cash_shift")
        if handler is None:
            raise CashContextError("Comando de turno no disponible: reanudar")
        return handler(
            shift_id=shift_id or self.active_shift_id(),
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def begin_cash_shift_closing(self, *, shift_id: str | None = None):
        handler = self._command_handlers.get("begin_cash_shift_closing")
        if handler is None:
            raise CashContextError("Comando de turno no disponible: pre-cierre")
        return handler(
            shift_id=shift_id or self.active_shift_id(),
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def reverse_cash_movement(
        self,
        *,
        entry_id: str,
        authorized_by: str,
        reason: str,
    ):
        handler = self._command_handlers.get("reverse_cash_movement")
        if handler is None:
            raise CashContextError("Comando de ledger no disponible: reversar movimiento")
        return handler(
            entry_id=entry_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            authorized_by=authorized_by,
            reason=reason,
        )

    def prepare_cash_handover(self, *, safe_drop_entry_id: str, denominations: dict[str, int]):
        handler = self._command_handlers.get("prepare_cash_handover")
        if handler is None:
            raise CashContextError("Comando de entrega no disponible: preparar entrega")
        return handler(
            safe_drop_entry_id=safe_drop_entry_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            denominations=denominations,
        )

    def deliver_cash_handover(self, *, handover_id: str, denominations: dict[str, int]):
        handler = self._command_handlers.get("deliver_cash_handover")
        if handler is None:
            raise CashContextError("Comando de entrega no disponible: entregar valores")
        return handler(
            handover_id=handover_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            denominations=denominations,
        )

    def receive_cash_handover(self, *, handover_id: str, denominations: dict[str, int]):
        handler = self._command_handlers.get("receive_cash_handover")
        if handler is None:
            raise CashContextError("Comando de entrega no disponible: recibir valores")
        return handler(
            handover_id=handover_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            denominations=denominations,
        )

    def dispute_cash_handover(self, *, handover_id: str, reason: str):
        handler = self._command_handlers.get("dispute_cash_handover")
        if handler is None:
            raise CashContextError("Comando de entrega no disponible: disputar entrega")
        return handler(
            handover_id=handover_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            reason=reason,
        )

    def execute_cash_refund(
        self,
        *,
        refund_id: str,
        sale_id: str,
        authorized_by: str,
        original_payment_lines: dict[str, Decimal],
        refund_lines: dict[str, Decimal],
        reason: str,
    ):
        handler = self._command_handlers.get("execute_cash_refund")
        if handler is None:
            raise CashContextError("Comando de reembolso no disponible")
        return handler(
            refund_id=refund_id,
            sale_id=sale_id,
            branch_id=self.active_branch_id(),
            cashier_user_id=self.actor_user_id(),
            authorized_by=authorized_by,
            original_payment_lines=original_payment_lines,
            refund_lines=refund_lines,
            reason=reason,
        )

    def explain_cash_difference(self, *, difference_id: str, explanation: str):
        handler = self._command_handlers.get("explain_cash_difference")
        if handler is None:
            raise CashContextError("Comando de diferencia no disponible: explicar")
        return handler(
            difference_id=difference_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            explanation=explanation,
        )

    def review_cash_difference(self, *, difference_id: str):
        handler = self._command_handlers.get("review_cash_difference")
        if handler is None:
            raise CashContextError("Comando de diferencia no disponible: revisar")
        return handler(
            difference_id=difference_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def resolve_cash_difference(self, *, difference_id: str, resolution: str):
        handler = self._command_handlers.get("resolve_cash_difference")
        if handler is None:
            raise CashContextError("Comando de diferencia no disponible: resolver")
        return handler(
            difference_id=difference_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            resolution=resolution,
        )

    def generate_x_cut(self, *, shift_id: str | None = None):
        handler = self._command_handlers.get("generate_x_cut")
        if handler is None:
            raise CashContextError("Comando de Corte X no disponible: generar")
        return handler(
            shift_id=shift_id or self.active_shift_id(),
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def print_x_cut(self, *, cut_id: str, reprint: bool = False,
                    original_print_id: str | None = None,
                    reprint_reason: str | None = None):
        handler = self._command_handlers.get("print_x_cut")
        if handler is None:
            raise CashContextError("Comando de impresion no disponible: Corte X")
        return handler(
            cut_id=cut_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            reprint=reprint,
            original_print_id=original_print_id,
            reprint_reason=reprint_reason,
        )

    def generate_z_cut(self, *, shift_id: str | None = None):
        handler = self._command_handlers.get("generate_z_cut")
        if handler is None:
            raise CashContextError("Comando de Corte Z no disponible: generar")
        return handler(
            shift_id=shift_id or self.active_shift_id(),
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def print_z_cut(self, *, cut_id: str, reprint: bool = False,
                    original_print_id: str | None = None,
                    reprint_reason: str | None = None):
        handler = self._command_handlers.get("print_z_cut")
        if handler is None:
            raise CashContextError("Comando de impresion no disponible: Corte Z")
        return handler(
            cut_id=cut_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            reprint=reprint,
            original_print_id=original_print_id,
            reprint_reason=reprint_reason,
        )

    def notify_z_cut(self, *, cut_id: str):
        handler = self._command_handlers.get("notify_z_cut")
        if handler is None:
            raise CashContextError("Comando de notificacion no disponible: Corte Z")
        return handler(
            cut_id=cut_id,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def cash_sync_state(self) -> dict[str, object]:
        service = self._query_services.get("sync")
        if service is None:
            raise CashContextError("Consulta de sincronizacion no disponible")
        return service.get(
            device_id=self.active_sync_device_id(),
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def cash_sync_records(self, *, limit: int = 100) -> list[dict]:
        service = self._query_services.get("sync")
        if service is None:
            raise CashContextError("Consulta de sincronizacion no disponible")
        if hasattr(service, "list_envelopes"):
            return service.list_envelopes(
                device_id=self.active_sync_device_id(),
                branch_id=self.active_branch_id(),
                actor_user_id=self.actor_user_id(),
                limit=limit,
            )
        return []

    def resolve_cash_sync_conflict(self, *, envelope_id: str, strategy: str, reason: str):
        handler = self._command_handlers.get("resolve_cash_sync_conflict")
        if handler is None:
            raise CashContextError("Comando de sincronizacion no disponible: resolver conflicto")
        return handler(
            envelope_id=envelope_id,
            strategy=strategy,
            reason=reason,
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def set_cash_sync_connectivity(self, *, online: bool):
        handler = self._command_handlers.get("set_cash_sync_connectivity")
        if handler is None:
            raise CashContextError("Comando de sincronizacion no disponible: conectividad")
        return handler(
            device_id=self.active_sync_device_id(),
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
            online=online,
        )

    def run_cash_sync_cycle(self):
        handler = self._command_handlers.get("run_cash_sync_cycle")
        if handler is None:
            raise CashContextError("Comando de sincronizacion no disponible: ejecutar ciclo")
        return handler(
            device_id=self.active_sync_device_id(),
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def cash_notifications_dashboard(self) -> dict[str, int]:
        service = self._query_services.get("notifications")
        if service is None:
            raise CashContextError("Consulta de notificaciones no disponible")
        return service.dashboard(
            user_id=self.actor_user_id(),
            branch_id=self.active_branch_id(),
        )

    def cash_notification_alerts(self) -> list[dict]:
        service = self._query_services.get("notifications")
        if service is None:
            raise CashContextError("Consulta de notificaciones no disponible")
        return service.unread(
            user_id=self.actor_user_id(),
            branch_id=self.active_branch_id(),
        )

    def cash_notification_jobs(self, *, limit: int = 100) -> list[dict]:
        service = self._query_services.get("notifications")
        if service is None:
            raise CashContextError("Consulta de notificaciones no disponible")
        return service.recent_jobs(
            user_id=self.actor_user_id(),
            branch_id=self.active_branch_id(),
            limit=limit,
        )

    def dispatch_cash_notifications(self):
        handler = self._command_handlers.get("dispatch_cash_notifications")
        if handler is None:
            raise CashContextError("Comando de notificaciones no disponible: despachar")
        return handler(
            branch_id=self.active_branch_id(),
            actor_user_id=self.actor_user_id(),
        )

    def cash_overview_dashboard(self):
        service = self._query_services.get("overview")
        if service is None:
            raise CashContextError("Consulta BI de Caja no disponible")
        return service.dashboard(
            branch_id=self.active_branch_id(),
            requester_user_id=self.actor_user_id(),
        )

    def cash_operational_section(self, section_key: str, *, limit: int = 100):
        service = self._query_services.get("operational_read")
        if service is None:
            raise CashContextError("Consulta operativa de Caja no disponible")
        return service.section(
            section_key=section_key,
            branch_id=self.active_branch_id(),
            requester_user_id=self.actor_user_id(),
            limit=limit,
        )

    def backend_binding(self, key: str) -> str:
        bindings = {
            "overview": ("overview",),
            "shifts": (
                "cash_open_shift_uc",
                "cash_suspend_shift_uc",
                "cash_resume_shift_uc",
                "cash_begin_shift_closing_uc",
            ),
            "ledger": ("ledger", "cash_register_movement_uc", "cash_reverse_movement_uc"),
            "blind_count": (
                "blind_count",
                "cash_start_blind_count_uc",
                "cash_capture_blind_count_uc",
                "cash_confirm_blind_count_uc",
            ),
            "x_cut": ("x_cut", "cash_generate_x_cut_uc"),
            "z_cut": ("z_cut", "cash_generate_z_cut_uc"),
            "differences": (),
            "handover": (),
            "refunds": (),
            "hardware": (
                "hardware",
                "cash_device_create_uc",
                "cash_device_status_uc",
                "cash_hardware_diagnose_uc",
                "cash_open_drawer_hardware_uc",
            ),
            "configuration": ("configuration",),
            "sync": (
                "sync",
                "cash_sync_service",
                "cash_sync_connectivity_uc",
                "cash_sync_conflict_resolution_uc",
            ),
            "notifications": (
                "notifications",
                "cash_prepare_notifications_uc",
                "cash_dispatch_notifications_uc",
            ),
            "deposits": ("operational_read",),
            "payment_methods": ("operational_read",),
            "payment_terminals": ("operational_read",),
            "drawer_events": ("operational_read",),
            "audit": ("operational_read",),
        }.get(key, ())
        connected = [
            name for name in bindings
            if name in self._query_services or name in self._use_cases
        ]
        if connected:
            return "Conectada al backend: " + ", ".join(connected)
        return "Sin binding backend disponible en este entorno."

    def movement_reason_options(self, movement_type: str):
        service = self._query_services.get("movement_reasons")
        if service is None:
            return ()
        return service.list_active(movement_type)

    def denomination_options(self):
        service = self._query_services.get("denominations")
        if service is None:
            return ()
        return service.list_active()

    def status_cards(self) -> dict[str, object]:
        sync_state = "Lista"
        if "sync" in self._query_services:
            try:
                state = self.cash_sync_state()
                sync_state = (
                    f"{state.get('connectivity', 'ONLINE')} / "
                    f"{state.get('sync_status', 'IDLE')} "
                    f"P:{state.get('pending_count', 0)} C:{state.get('conflict_count', 0)}"
                )
            except Exception:
                sync_state = "No disponible"
        alerts = 0
        if "notifications" in self._query_services:
            try:
                alerts = int(self.cash_notifications_dashboard().get("unread", 0))
            except Exception:
                alerts = 0
        return {
            "shift": self.optional_active_shift_id() or "Sin turno activo",
            "sync": sync_state,
            "alerts": alerts,
        }
