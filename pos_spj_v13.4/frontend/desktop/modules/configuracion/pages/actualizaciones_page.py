"""«Acerca de y actualizaciones» — version, channel, maintenance window,
check/download/install and the update history of THIS station.

Only presentation: every action calls `SoftwareUpdatesPresenter`, which calls
the use cases. The download runs in a worker thread that never touches the
database (the network part of `DownloadUpdateUseCase`); its result is
recorded back on the UI thread.
"""
from __future__ import annotations

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QVBoxLayout, QWidget,
)

from frontend.desktop.components import (
    AlertCard, ColumnSpec, PageHeader, SectionCard, StandardComboBox, StandardTable,
    TimeRangeInput, ViewState, create_primary_button, create_secondary_button,
    create_state_widget, create_warning_button,
)
from frontend.desktop.themes.tokens import Spacing

_HISTORY_COLUMNS = [
    ColumnSpec("Fecha"), ColumnSpec("Evento"), ColumnSpec("De"), ColumnSpec("A"),
    ColumnSpec("Canal"), ColumnSpec("Detalle"),
]

_EVENT_LABELS = {
    "OFFERED": "Actualización disponible",
    "NOT_OFFERED": "Sin actualización",
    "REJECTED": "Rechazada",
    "DOWNLOADED": "Descargada",
    "DOWNLOAD_FAILED": "Descarga fallida",
    "OFFLINE_IMPORTED": "Paquete offline importado",
    "SCHEDULED": "Programada",
    "DEFERRED": "Pospuesta",
    "CANCELLED": "Cancelada",
    "CHANNEL_CHANGED": "Cambio de canal",
    "WINDOW_CHANGED": "Ventana de mantenimiento",
    "INSTALL_COMPLETED": "Instalada",
    "INSTALL_ROLLED_BACK": "Revertida",
    "INSTALL_NEEDS_RECOVERY": "Requiere recuperación",
    "INSTALL_RECOVERED": "Recuperada",
    "INSTALL_CANCELLED": "No aplicada",
}

_CHANNELS = (("stable", "Estable"), ("pilot", "Piloto"))


def _button_row(parent, *buttons) -> QWidget:
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(Spacing.SM)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch(1)
    return row


def _megabytes(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


class _DownloadWorker(QObject):
    progressed = pyqtSignal(int, int)
    finished = pyqtSignal(object)  # None or the exception

    def __init__(self, prepared) -> None:
        super().__init__()
        self._prepared = prepared
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            self._prepared.run(progress=lambda done, total: self.progressed.emit(done, total),
                               cancelled=lambda: self._cancel)
        except Exception as exc:  # reported to the UI thread, which records it
            self.finished.emit(exc)
            return
        self.finished.emit(None)


class ActualizacionesPage(QWidget):
    page_id = "config_actualizaciones"
    title = "Acerca de y actualizaciones"
    subtitle = "Versión instalada, canal, ventana de mantenimiento e historial de esta estación."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter.software_updates
        self._loaded = False
        self._thread: QThread | None = None
        self._worker: _DownloadWorker | None = None
        self._prepared = None
        self.setObjectName("configuracionPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)
        root.addWidget(PageHeader(self, title=self.title, subtitle=self.subtitle))

        self.warnings_card = AlertCard(self, variant="alert")
        self.warnings_label = QLabel(self.warnings_card)
        self.warnings_label.setWordWrap(True)
        self.warnings_card.add(self.warnings_label)
        root.addWidget(self.warnings_card)

        root.addWidget(self._build_installation_card())
        root.addWidget(self._build_update_card())
        root.addWidget(self._build_channel_card())
        root.addWidget(self._build_history_card(), stretch=1)

    # ── construction ──────────────────────────────────────────────────────
    def _build_installation_card(self) -> QWidget:
        card = SectionCard(self, title="Esta instalación")
        holder = QWidget(card)
        form = QFormLayout(holder)
        form.setContentsMargins(0, 0, 0, 0)
        self._facts: dict[str, QLabel] = {}
        for key, label in (
            ("version", "Versión"), ("build", "Compilación"), ("channel", "Canal"),
            ("profile", "Perfil de instalación"), ("capabilities", "Módulos habilitados"),
            ("layout", "Tipo"), ("data_dir", "Carpeta de datos"), ("database", "Base de datos"),
            ("schema", "Esquema de la base"), ("whatsapp", "WhatsApp"),
            ("last_check", "Última búsqueda"),
        ):
            value = QLabel("—", holder)
            value.setWordWrap(True)
            value.setAccessibleName(label)
            self._facts[key] = value
            form.addRow(f"{label}:", value)
        card.add(holder)
        return card

    def _build_update_card(self) -> QWidget:
        card = SectionCard(self, title="Actualización")
        self.offer_label = QLabel("Sin buscar todavía.", card)
        self.offer_label.setWordWrap(True)
        card.add(self.offer_label)
        self.notes_label = QLabel("", card)
        self.notes_label.setWordWrap(True)
        self.notes_label.setProperty("role", "muted")
        card.add(self.notes_label)
        self.progress = QProgressBar(card)
        self.progress.setAccessibleName("Progreso de la descarga")
        self.progress.setVisible(False)
        card.add(self.progress)

        self.check_button = create_secondary_button(card, "Buscar actualizaciones")
        self.download_button = create_primary_button(card, "Descargar")
        self.cancel_download_button = create_warning_button(card, "Cancelar descarga")
        self.install_button = create_primary_button(card, "Instalar ahora")
        self.schedule_button = create_secondary_button(card, "Instalar en la ventana")
        self.cancel_schedule_button = create_warning_button(card, "Cancelar programada")
        self.offline_button = create_secondary_button(card, "Importar paquete offline…")
        card.add(_button_row(card, self.check_button, self.download_button,
                             self.cancel_download_button, self.offline_button))
        card.add(_button_row(card, self.install_button, self.schedule_button,
                             self.cancel_schedule_button))

        self.check_button.clicked.connect(self._on_check)
        self.download_button.clicked.connect(self._on_download)
        self.cancel_download_button.clicked.connect(self._on_cancel_download)
        self.install_button.clicked.connect(self._on_install_now)
        self.schedule_button.clicked.connect(self._on_schedule)
        self.cancel_schedule_button.clicked.connect(self._on_cancel_schedule)
        self.offline_button.clicked.connect(self._on_import_offline)
        return card

    def _build_channel_card(self) -> QWidget:
        card = SectionCard(self, title="Canal y ventana de mantenimiento")
        self.channel_combo = StandardComboBox(card, accessible_name="Canal de actualizaciones")
        for value, label in _CHANNELS:
            self.channel_combo.addItem(label, value)
        self.save_channel_button = create_secondary_button(card, "Guardar canal")
        card.add(_button_row(card, QLabel("Canal:", card), self.channel_combo,
                             self.save_channel_button))
        self.window_input = TimeRangeInput(card, allow_overnight=True)
        self.save_window_button = create_secondary_button(card, "Guardar ventana")
        self.clear_window_button = create_warning_button(card, "Quitar ventana")
        card.add(_button_row(card, QLabel("Ventana diaria:", card), self.window_input,
                             self.save_window_button, self.clear_window_button))
        hint = QLabel(
            "Piloto recibe las versiones antes que el resto de las sucursales. La ventana de "
            "mantenimiento es el horario en que una actualización programada puede cerrar SPJ; "
            "nunca lo hace con una venta, un cobro o un corte en curso.", card)
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        card.add(hint)
        self.save_channel_button.clicked.connect(self._on_save_channel)
        self.save_window_button.clicked.connect(self._on_save_window)
        self.clear_window_button.clicked.connect(self._on_clear_window)
        return card

    def _build_history_card(self) -> QWidget:
        self.history_card = SectionCard(self, title="Historial de esta estación")
        self.history_table = StandardTable(_HISTORY_COLUMNS, self.history_card)
        self.history_table.setAccessibleName("Historial de actualizaciones")
        self.history_card.add(self.history_table)
        self.history_empty = None
        return self.history_card

    # ── loading ───────────────────────────────────────────────────────────
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self, search: str = "") -> None:
        try:
            status = self._presenter.status()
        except Exception as exc:
            QMessageBox.warning(self, self.title, f"No se pudo leer el estado: {exc}")
            return
        self._loaded = True
        self._status = status
        facts = self._facts
        facts["version"].setText(status.app_version)
        facts["build"].setText(status.build_label + ("" if status.signed_build else " — sin firma"))
        facts["channel"].setText(status.channel.label)
        facts["profile"].setText(status.install_profile)
        facts["capabilities"].setText(", ".join(status.enabled_capabilities))
        facts["layout"].setText("Instalada" if status.layout == "installed" else "Código fuente")
        facts["data_dir"].setText(status.data_dir)
        facts["database"].setText(status.database_path)
        facts["schema"].setText(str(status.schema_version or "—"))
        facts["whatsapp"].setText("Servicio local" if status.whatsapp_mode == "local"
                                  else "Servicio remoto")
        facts["last_check"].setText(
            f"{status.last_check_at} — {status.last_check_result}" if status.last_check_at
            else "Nunca")

        warnings = []
        if not status.signing_configured:
            warnings.append("Esta compilación no tiene clave de firma de confianza: no aceptará "
                            "ninguna actualización (ver manual de publicación).")
        if not status.feed_configured:
            warnings.append("No hay servidor de actualizaciones configurado; use paquetes offline.")
        if not status.signed_build and status.layout == "installed":
            warnings.append("Compilación sin firma Authenticode: no apta para producción.")
        self.warnings_label.setText("\n".join(warnings))
        self.warnings_card.setVisible(bool(warnings))

        self.channel_combo.setCurrentIndex(
            max(0, self.channel_combo.findData(status.channel.value)))
        if status.maintenance_window and "-" in status.maintenance_window:
            start, end = status.maintenance_window.split("-", 1)
            self.window_input.set_range(start, end)

        self._render_offer(status)
        self._render_history(status.history)
        self._apply_permissions(status)

    def _render_offer(self, status) -> None:
        available, job = status.available, status.pending_job
        if job is not None:
            when = (f"en la ventana {job.scheduled_window}" if job.scheduled_window
                    else "al cerrar la aplicación")
            self.offer_label.setText(
                f"Versión {job.to_version} programada {when} ({job.state.label}).")
        elif available is not None:
            manifest = available.manifest
            state = "descargada y verificada" if available.downloaded else "lista para descargar"
            mandatory = ""
            if manifest.mandatory:
                mandatory = " Obligatoria" + (
                    f" antes del {manifest.mandatory_deadline:%d/%m/%Y}."
                    if manifest.mandatory_deadline else ".")
            self.offer_label.setText(
                f"Versión {manifest.version} ({manifest.channel.label}, "
                f"{_megabytes(manifest.artifact.size)}) {state}.{mandatory}")
        else:
            self.offer_label.setText(status.last_check_result or "Sin actualizaciones pendientes.")
        self.notes_label.setText(available.manifest.release_notes if available else "")
        self._available, self._job = available, job

    def _render_history(self, history) -> None:
        rows = [[
            str(row.get("occurred_at") or ""),
            _EVENT_LABELS.get(row.get("event_type"), row.get("event_type") or ""),
            row.get("from_version") or "", row.get("to_version") or "",
            row.get("channel") or "", (row.get("detail") or "")[:200],
        ] for row in history]
        self.history_table.load_rows(rows)
        if self.history_empty is not None:
            self.history_empty.setParent(None)
            self.history_empty = None
        if not rows:
            self.history_empty = create_state_widget(
                ViewState.EMPTY, self.history_card,
                message="Aún no hay búsquedas ni instalaciones registradas en esta estación.")
            self.history_card.add(self.history_empty)
        self.history_table.setVisible(bool(rows))

    def _apply_permissions(self, status) -> None:
        downloading = self._thread is not None
        admin = status.can_administer
        available, job = self._available, self._job
        self.check_button.setEnabled(not downloading)
        self.download_button.setVisible(admin)
        self.download_button.setEnabled(
            not downloading and job is None and available is not None and not available.downloaded)
        self.cancel_download_button.setVisible(admin and downloading)
        self.offline_button.setVisible(admin)
        self.offline_button.setEnabled(not downloading and job is None)
        ready = job is None and available is not None and available.downloaded and not downloading
        self.install_button.setVisible(admin)
        self.install_button.setEnabled(ready)
        self.schedule_button.setVisible(admin)
        self.schedule_button.setEnabled(ready and bool(status.maintenance_window))
        self.cancel_schedule_button.setVisible(admin and job is not None)
        for widget in (self.channel_combo, self.save_channel_button, self.window_input,
                       self.save_window_button, self.clear_window_button):
            widget.setEnabled(status.can_change_channel)

    # ── actions ───────────────────────────────────────────────────────────
    def _show(self, ok: bool, message: str) -> None:
        (QMessageBox.information if ok else QMessageBox.warning)(self, self.title, message)

    def _on_check(self) -> None:
        ok, message = self._presenter.check()
        self._show(ok, message)
        self.reload()

    def _on_download(self) -> None:
        prepared, message = self._presenter.prepare_download()
        if prepared is None:
            self._show(False, message)
            return
        self._prepared = prepared
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._thread = QThread(self)
        self._worker = _DownloadWorker(prepared)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finished.connect(self._on_download_finished)
        self._thread.start()
        self._apply_permissions(self._status)

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.progress.setValue(int(done * 100 / total))
            self.progress.setFormat(f"{_megabytes(done)} de {_megabytes(total)}")

    def _on_cancel_download(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _on_download_finished(self, error) -> None:
        thread, self._thread = self._thread, None
        self._worker = None
        if thread is not None:
            thread.quit()
            thread.wait()
        self.progress.setVisible(False)
        ok, message = self._presenter.finish_download(self._prepared, error)
        self._prepared = None
        self._show(ok, message)
        self.reload()

    def _on_install_now(self) -> None:
        answer = QMessageBox.question(
            self, self.title,
            "SPJ se cerrará, respaldará la base de datos e instalará la nueva versión. Windows "
            "pedirá autorización de administrador. Si algo falla, se vuelve a la versión actual.\n\n"
            "¿Continuar?")
        if answer != QMessageBox.Yes:
            return
        ok, message = self._presenter.install_now()
        if not ok:
            self._show(False, message)
            self.reload()

    def _on_schedule(self) -> None:
        self._show(*self._presenter.schedule_for_window())
        self.reload()

    def _on_cancel_schedule(self) -> None:
        self._show(*self._presenter.cancel_scheduled())
        self.reload()

    def _on_import_offline(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Manifiesto del paquete offline (manifest.json)", "", "Manifiesto (manifest.json)")
        if not path:
            return
        self._show(*self._presenter.import_offline(path))
        self.reload()

    def _on_save_channel(self) -> None:
        self._show(*self._presenter.change_channel(str(self.channel_combo.currentData())))
        self.reload()

    def _on_save_window(self) -> None:
        error = self.window_input.validate()
        if error:
            self._show(False, error)
            return
        self._show(*self._presenter.set_maintenance_window(
            f"{self.window_input.start_text()}-{self.window_input.end_text()}"))
        self.reload()

    def _on_clear_window(self) -> None:
        self._show(*self._presenter.set_maintenance_window(""))
        self.reload()


__all__ = ["ActualizacionesPage"]
