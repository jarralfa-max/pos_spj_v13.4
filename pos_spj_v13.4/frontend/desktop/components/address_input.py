"""AddressInput — EL componente de dirección de todo el ERP.

Clientes, Proveedores, Delivery y Configuración capturan la dirección con este
mismo widget. Antes había tres formas distintas (seis campos en Delivery, cinco
en Proveedores, uno en Configuración) y ésta no la usaba ninguna pantalla.

CÓMO SE COMPORTA
----------------
* **Busca a partir del 5.º carácter** (decisión del usuario). La cifra NO vive
  aquí: se importa de `backend.application.addresses.MIN_QUERY_CHARS`, la única
  fuente. Además espera a que se deje de escribir (`debounce_ms`) para no lanzar
  una consulta por tecla.
* **Nunca bloquea la interfaz.** La consulta corre en un hilo del `QThreadPool`;
  cada una lleva un `request_id` y las respuestas de consultas ya superadas se
  DESCARTAN — sin eso, una respuesta lenta de "Av. Juá" podía llegar después de
  la de "Av. Juárez 120" y reemplazarla (el parpadeo que ya resolvía la versión
  perdida en `42f0ed01`).
* **Elegir una sugerencia RELLENA los campos**, que siguen siendo editables: los
  campos son también la captura manual, siempre disponible. El número interior y
  las referencias que ya se hubieran escrito se conservan: ningún proveedor los
  sabe.
* **Corregir a mano lo que ubica la dirección descarta las coordenadas.** Si se
  cambia calle, número exterior, colonia, municipio, estado o C.P. después de
  elegir una sugerencia, las coordenadas ya no corresponden a lo escrito y
  guardarlas mandaría al repartidor a otro sitio. Interior y referencias no
  mueven el punto, así que no las invalidan.
* **Enter busca explícitamente.** Es la única forma de consultar a Nominatim,
  cuya política prohíbe el autocompletado (ver `address_search.py`).
* **Sin servicio no hay búsqueda, pero sí dirección**: el cuadro de búsqueda se
  deshabilita, se explica por qué, y los campos funcionan igual.

`value()` devuelve un `StructuredAddress` completo —con coordenadas y origen—,
no una etiqueta. La versión anterior devolvía sólo el texto y tiraba lat/lon.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.application.addresses.address_search import (
    MIN_QUERY_CHARS,
    AddressSearchResult,
    AddressSearchStatus,
    AddressSource,
    StructuredAddress,
)
from frontend.desktop.components.virtual_keyboard import attach_virtual_keyboard_action

#: Campos que UBICAN la dirección: corregirlos a mano invalida las coordenadas.
_LOCATING_FIELDS = ("street", "exterior_number", "neighborhood", "municipality",
                    "state", "postal_code")

_FIELD_LABELS = (
    ("street", "Calle"), ("exterior_number", "Núm. exterior"),
    ("interior_number", "Núm. interior"), ("neighborhood", "Colonia"),
    ("municipality", "Municipio / Ciudad"), ("state", "Estado"),
    ("postal_code", "C.P."),
)


# ── ejecución de la búsqueda ─────────────────────────────────────────────────

class SyncRunner:
    """Ejecuta en el mismo hilo. Para pruebas: con él no hace falta esperar a
    ningún hilo ni bucle de eventos."""

    def submit(self, work, on_done) -> None:
        on_done(_safe(work))


def _safe(work) -> AddressSearchResult:
    """Un fallo inesperado no puede dejar la pantalla en "Buscando…" para
    siempre: se convierte en un resultado que la pantalla sabe explicar."""
    try:
        return work()
    except Exception:
        import logging
        logging.getLogger("spj.address_input").exception("Búsqueda de dirección reventó")
        return AddressSearchResult(
            AddressSearchStatus.UNAVAILABLE,
            message="No se pudo buscar la dirección. Captúrala manualmente.")


class _Signals(QObject):
    done = pyqtSignal(object)


class _Job(QRunnable):
    def __init__(self, work, signals: _Signals) -> None:
        super().__init__()
        self._work = work
        self._signals = signals

    def run(self) -> None:  # hilo del pool
        self._signals.done.emit(_safe(self._work))


class ThreadPoolRunner:
    """La ejecución real: fuera del hilo de la interfaz."""

    def __init__(self, pool: QThreadPool | None = None) -> None:
        self._pool = pool or QThreadPool.globalInstance()
        self._vivos: set = set()

    def submit(self, work, on_done) -> None:
        senales = _Signals()
        # Conexión EN COLA: `on_done` toca widgets y tiene que correr en el hilo
        # de la interfaz, no en el del pool que emite.
        senales.done.connect(on_done, Qt.QueuedConnection)
        # Retener la referencia hasta que llegue la respuesta; si Python recoge
        # el objeto antes, la señal nunca se entrega.
        self._vivos.add(senales)
        senales.done.connect(lambda _r, s=senales: self._vivos.discard(s),
                             Qt.QueuedConnection)
        self._pool.start(_Job(work, senales))


class _SearchLineEdit(QLineEdit):
    """Buscador que SE QUEDA con el Enter.

    `QLineEdit` emite `returnPressed` y luego deja pasar la tecla al diálogo,
    que la interpreta como "Aceptar". Como Enter es justo el gesto para buscar
    con Nominatim, sin esto buscar una dirección cerraría el diálogo de
    Proveedores, Clientes o Configuración a medio capturar.
    """

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _Relay(QObject):
    """Receptor hijo del widget: si el widget se destruye con una búsqueda en
    vuelo, el relé muere con él y Qt descarta la respuesta en vez de entregarla
    a un objeto borrado."""

    def __init__(self, parent, callback) -> None:
        super().__init__(parent)
        self._callback = callback

    @pyqtSlot(object)
    def deliver(self, payload) -> None:
        self._callback(*payload)


# ── el componente ────────────────────────────────────────────────────────────

class AddressInput(QWidget):
    #: Se eligió una sugerencia; lleva el `StructuredAddress`.
    selected = pyqtSignal(object)
    #: Cambió cualquier dato de la dirección (elección o edición).
    changed = pyqtSignal()

    def __init__(self, parent=None, *, search_service=None, runner=None,
                 with_references: bool = False, debounce_ms: int = 400) -> None:
        super().__init__(parent)
        self.setObjectName("addressInput")
        self._service = search_service
        self._runner = runner or ThreadPoolRunner()
        self._request_id = 0
        self._source = AddressSource.MANUAL
        self._lat: float | None = None
        self._lon: float | None = None
        self._country = "MX"
        self._relay = _Relay(self, self._on_result)
        #: Última respuesta entregada (la usan las pruebas y el registro).
        self.last_result: AddressSearchResult | None = None

        self._search_box = _SearchLineEdit(self)
        self._search_box.setObjectName("addressSearchBox")
        self._search_box.setPlaceholderText(
            f"Buscar dirección (desde {MIN_QUERY_CHARS} caracteres)…")
        self._search_box.setAccessibleName("Buscar dirección")
        attach_virtual_keyboard_action(self._search_box)

        self._status = QLabel("", self)
        self._status.setObjectName("addressSearchStatus")
        self._status.setWordWrap(True)
        self._status.setProperty("role", "hint")

        self._suggestions = QListWidget(self)
        self._suggestions.setObjectName("addressSuggestions")
        self._suggestions.setAccessibleName("Sugerencias de dirección")
        self._suggestions.setVisible(False)

        self._attribution = QLabel("", self)
        self._attribution.setProperty("role", "caption")
        self._attribution.setVisible(False)

        self._fields: dict[str, QLineEdit] = {}
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        etiquetas = list(_FIELD_LABELS)
        if with_references:
            etiquetas.append(("references", "Referencias"))
        for nombre, etiqueta in etiquetas:
            campo = QLineEdit(self)
            campo.setPlaceholderText(etiqueta)
            campo.setAccessibleName(etiqueta)
            attach_virtual_keyboard_action(campo)
            # `textEdited` y no `textChanged`: sólo lo que TECLEA el usuario
            # invalida coordenadas; rellenar desde una sugerencia no.
            campo.textEdited.connect(lambda _t, n=nombre: self._on_field_edited(n))
            self._fields[nombre] = campo
            form.addRow(etiqueta, campo)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._search_box)
        layout.addWidget(self._status)
        layout.addWidget(self._suggestions)
        layout.addWidget(self._attribution)
        layout.addLayout(form)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, int(debounce_ms)))
        self._timer.timeout.connect(lambda: self.search_now(interactive=True))

        self._search_box.textChanged.connect(self._on_query_changed)
        self._search_box.returnPressed.connect(lambda: self.search_now(interactive=False))
        self._suggestions.itemActivated.connect(self._on_suggestion)
        self._suggestions.itemClicked.connect(self._on_suggestion)

        if self._service is None:
            self._search_box.setEnabled(False)
            self._show(
                "La búsqueda de direcciones no está configurada "
                "(Configuración → Integraciones). Captura la dirección en los campos.")

    # ── búsqueda ─────────────────────────────────────────────────────────
    def _on_query_changed(self, texto: str) -> None:
        self._timer.stop()
        consulta = texto.strip()
        if len(consulta) < MIN_QUERY_CHARS:
            # Una consulta en vuelo de un texto que ya no está escrito no debe
            # aparecer: se invalida subiendo el identificador.
            self._request_id += 1
            self._clear_suggestions()
            self._show(f"Escribe al menos {MIN_QUERY_CHARS} caracteres para buscar."
                       if consulta else "")
            return
        if self._service is not None:
            self._timer.start()

    def search_now(self, *, interactive: bool) -> None:
        """Lanza la búsqueda con lo que haya escrito. `interactive=False` es la
        de Enter: la única que puede llegar a Nominatim."""
        self._timer.stop()
        if self._service is None:
            return
        consulta = self._search_box.text().strip()
        if len(consulta) < MIN_QUERY_CHARS:
            self._show(f"Escribe al menos {MIN_QUERY_CHARS} caracteres para buscar.")
            return
        self._request_id += 1
        solicitud = self._request_id
        self._show("Buscando…")
        servicio = self._service
        self._runner.submit(
            lambda: servicio.search(consulta, interactive=interactive),
            lambda resultado: self._relay.deliver((solicitud, resultado)))

    def _on_result(self, solicitud: int, resultado: AddressSearchResult) -> None:
        if solicitud != self._request_id:
            return  # respuesta de una consulta ya superada
        self._clear_suggestions()
        for sugerencia in resultado.suggestions:
            item = QListWidgetItem(sugerencia.label or sugerencia.one_line())
            item.setData(Qt.UserRole, sugerencia)
            self._suggestions.addItem(item)
        self._suggestions.setVisible(bool(resultado.suggestions))
        if resultado.suggestions and resultado.attribution:
            self._attribution.setText(resultado.attribution)
            self._attribution.setVisible(True)
        self._show(resultado.message)
        self.last_result = resultado

    def _on_suggestion(self, item: QListWidgetItem) -> None:
        sugerencia = item.data(Qt.UserRole)
        if not isinstance(sugerencia, StructuredAddress):
            return
        actual = self.value()
        self.set_value(sugerencia.with_changes(
            interior_number=actual.interior_number or sugerencia.interior_number,
            references=actual.references or sugerencia.references))
        self._clear_suggestions()
        self._show("")
        self.selected.emit(self.value())

    # ── edición manual ───────────────────────────────────────────────────
    def _on_field_edited(self, nombre: str) -> None:
        if nombre in _LOCATING_FIELDS and self._source is not AddressSource.MANUAL:
            self._source = AddressSource.MANUAL
            self._lat = self._lon = None
            self._show("Corregiste la dirección a mano: se guardará sin coordenadas.")
        self.changed.emit()

    # ── valor ────────────────────────────────────────────────────────────
    def value(self) -> StructuredAddress:
        datos = {nombre: campo.text() for nombre, campo in self._fields.items()}
        return StructuredAddress(
            **datos, country_code=self._country, latitude=self._lat,
            longitude=self._lon, source=self._source)

    def set_value(self, direccion) -> None:
        """Acepta `StructuredAddress`, un diccionario con sus campos, una sola
        línea de texto (lo que guardan los módulos de un campo) o `None`."""
        if direccion is None:
            direccion = StructuredAddress()
        elif isinstance(direccion, str):
            direccion = StructuredAddress.from_one_line(direccion)
        elif isinstance(direccion, dict):
            direccion = StructuredAddress.from_mapping(direccion)
        for nombre, campo in self._fields.items():
            campo.setText(getattr(direccion, nombre, "") or "")
        self._source = direccion.source
        self._lat, self._lon = direccion.latitude, direccion.longitude
        self._country = direccion.country_code or "MX"
        self.changed.emit()

    def clear(self) -> None:
        self._search_box.clear()
        self.set_value(None)
        self._clear_suggestions()
        self._show("")

    def is_empty(self) -> bool:
        return self.value().is_empty

    def field(self, nombre: str) -> QLineEdit:
        """Acceso a un campo, para que cada módulo marque los obligatorios."""
        return self._fields[nombre]

    # ── interno ──────────────────────────────────────────────────────────
    def _clear_suggestions(self) -> None:
        self._suggestions.clear()
        self._suggestions.setVisible(False)
        self._attribution.setVisible(False)

    def _show(self, mensaje: str) -> None:
        self._status.setText(mensaje or "")
        self._status.setVisible(bool(mensaje))
