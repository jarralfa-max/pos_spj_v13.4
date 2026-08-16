"""CASH-19 offline-first synchronization page.

The page renders operational sync state and delegates every mutation to the
presenter. It has no SQL, no repository imports and no direct transport calls.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.cash_register.cash_register_dialogs import ResolveCashSyncConflictDialog
from frontend.desktop.modules.cash_register.presentation import display_code, status_label, user_facing_error


class CashSyncPage(QWidget):
    """Expose outbox delivery, retries and conflict handling for Caja."""

    def __init__(self, *, presenter, parent=None):
        super().__init__(parent)
        self._presenter = presenter
        root = QVBoxLayout(self)

        caps = presenter.capabilities()
        run_sync = create_primary_button(
            self,
            "Sincronizar ahora",
            tooltip="Ejecuta un ciclo de entrega ordenada del outbox de Caja.",
        )
        mark_online = create_secondary_button(
            self,
            "Marcar online",
            tooltip="Permite reanudar intentos de sincronizacion para el dispositivo.",
        )
        mark_offline = create_secondary_button(
            self,
            "Marcar offline",
            tooltip="Pausa el envio remoto sin perder eventos locales.",
        )
        retry_local = create_secondary_button(
            self,
            "Reintentar local",
            tooltip="Resuelve el conflicto reintentando la version local con nueva revision.",
        )
        accept_remote = create_secondary_button(
            self,
            "Aceptar remoto",
            tooltip="Resuelve el conflicto aceptando la revision remota.",
        )
        refresh = create_secondary_button(self, "Actualizar")
        for button in (run_sync, mark_online, mark_offline, retry_local, accept_remote):
            button.setEnabled(bool(caps.sync_manage))

        run_sync.clicked.connect(self._run_sync)
        mark_online.clicked.connect(lambda: self._set_connectivity(True))
        mark_offline.clicked.connect(lambda: self._set_connectivity(False))
        retry_local.clicked.connect(lambda: self._resolve_conflict("RETRY_LOCAL"))
        accept_remote.clicked.connect(lambda: self._resolve_conflict("ACCEPT_REMOTE"))
        refresh.clicked.connect(self.refresh)

        root.addWidget(PageHeader(
            self,
            title="Sincronizacion offline-first",
            subtitle="Outbox canonico, secuencias locales, reintentos, conflictos y estado del dispositivo.",
            actions=[refresh, accept_remote, retry_local, mark_offline, mark_online, run_sync],
        ))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._table = StandardTable([
            ColumnSpec("Secuencia", "numeric"),
            ColumnSpec("Evento"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Intentos", "numeric"),
            ColumnSpec("Siguiente intento", "date"),
            ColumnSpec("Revision remota"),
            ColumnSpec("Operacion"),
            ColumnSpec("Error"),
        ], self)
        self._rows_by_id = {}
        root.addWidget(self._table)
        self.refresh()

    def refresh(self) -> None:
        try:
            state = self._presenter.cash_sync_state()
            rows = self._presenter.cash_sync_records()
        except (CashRegisterError, RuntimeError, ValueError, LookupError) as exc:
            self._show_error(user_facing_error(exc))
            self._rows_by_id = {}
            self._kpis.set_cards([
                KPIDTO("state", "Estado", "No disponible"),
                KPIDTO("pending", "Pendientes", "0"),
                KPIDTO("conflicts", "Conflictos", "0"),
                KPIDTO("synced", "Sincronizados", "0"),
            ])
            self._table.load_rows([])
            return
        self._rows_by_id = {str(row.get("id", "")): row for row in rows}
        self._kpis.set_cards([
            KPIDTO("state", "Estado", f"{status_label(state.get('connectivity'))} / {status_label(state.get('sync_status'))}"),
            KPIDTO("pending", "Pendientes", str(state.get("pending_count", 0))),
            KPIDTO("conflicts", "Conflictos", str(state.get("conflict_count", 0))),
            KPIDTO("synced", "Sincronizados", str(state.get("synced_count", 0))),
        ])
        self._table.load_rows(
            [
                [
                    row.get("sequence_no", ""),
                    row.get("event_name", ""),
                    status_label(row.get("state", "")),
                    row.get("attempt_count", ""),
                    row.get("next_attempt_at", ""),
                    row.get("remote_revision", ""),
                    display_code("OP", row.get("operation_id", "")),
                    user_facing_error(row.get("last_error", "")) if row.get("last_error") else "",
                ]
                for row in rows
            ],
            row_ids=[str(row.get("id", "")) for row in rows],
        )

    def _selected_envelope_id(self) -> str | None:
        return self._table.selected_row_id()

    def _run_sync(self) -> None:
        self._run(lambda: self._presenter.run_cash_sync_cycle(), "Ciclo de sincronizacion ejecutado.")

    def _set_connectivity(self, online: bool) -> None:
        message = "Dispositivo online." if online else "Dispositivo offline."
        self._run(lambda: self._presenter.set_cash_sync_connectivity(online=online), message)

    def _resolve_conflict(self, strategy: str) -> None:
        envelope_id = self._selected_envelope_id()
        if not envelope_id:
            self._show_error("Selecciona un conflicto de sincronizacion.")
            return
        dialog = ResolveCashSyncConflictDialog(
            self,
            envelope=self._rows_by_id.get(envelope_id, {}),
            strategy=strategy,
        )
        if dialog.exec_() != dialog.Accepted:
            return
        reason = dialog.result_value().reason
        self._run(
            lambda: self._presenter.resolve_cash_sync_conflict(
                envelope_id=envelope_id,
                strategy=strategy,
                reason=reason,
            ),
            "Conflicto de sincronizacion resuelto.",
        )

    def _run(self, command, success: str) -> None:
        try:
            result = command()
        except (CashRegisterError, RuntimeError, ValueError, LookupError) as exc:
            self._show_error(user_facing_error(exc))
            return
        if result is not None and hasattr(result, "status"):
            self._show_result(
                f"{success} Estado={result.status}, enviados={result.sent}, "
                f"ok={result.synced}, reintentos={result.retries}, conflictos={result.conflicts}"
            )
        else:
            self._show_result(success)
        self.refresh()

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", user_facing_error(message or "No fue posible completar la operacion."))
