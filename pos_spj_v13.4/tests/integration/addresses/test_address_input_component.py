"""`AddressInput` — el componente estándar de dirección.

Se prueba con un ejecutor síncrono (`SyncRunner`) para no depender de hilos ni
del bucle de eventos; el `ThreadPoolRunner` real se prueba aparte con un solo
caso que sí espera al pool.
"""

import pytest
from PyQt5.QtWidgets import QApplication

from backend.application.addresses import (
    MIN_QUERY_CHARS,
    AddressSearchResult,
    AddressSearchStatus,
    AddressSource,
    StructuredAddress,
)
from frontend.desktop.components.address_input import (
    AddressInput,
    SyncRunner,
    ThreadPoolRunner,
)


@pytest.fixture(scope="module")
def app():
    # A nivel de módulo: crear la QApplication dentro de un test tumba pytest
    # en silencio en este entorno.
    return QApplication.instance() or QApplication([])


_SUGERENCIA = StructuredAddress(
    street="Avenida Juárez", exterior_number="120", neighborhood="Centro",
    municipality="Cuauhtémoc", state="Ciudad de México", postal_code="06050",
    latitude=19.4351, longitude=-99.1478, source=AddressSource.MAPBOX,
    label="Avenida Juárez 120, Centro")


class _Servicio:
    def __init__(self, resultado=None):
        self.consultas = []
        self._resultado = resultado or AddressSearchResult(
            AddressSearchStatus.OK, suggestions=(_SUGERENCIA,), provider_code="MAPBOX",
            attribution="© Mapbox")

    def autocomplete_available(self):
        return True

    def search(self, query, *, interactive):
        self.consultas.append((query, interactive))
        return self._resultado


def _widget(servicio=None, **kw):
    return AddressInput(search_service=servicio, runner=SyncRunner(), debounce_ms=0, **kw)


def _elegir_primera(w):
    w._on_suggestion(w._suggestions.item(0))


class TestSearching:
    def test_nothing_is_searched_below_five_characters(self, app):
        servicio = _Servicio()
        w = _widget(servicio)
        w._search_box.setText("Juár")
        w.search_now(interactive=True)
        assert servicio.consultas == []
        assert str(MIN_QUERY_CHARS) in w._status.text()

    def test_typing_five_characters_arms_the_search(self, app):
        servicio = _Servicio()
        w = _widget(servicio)
        w._search_box.setText("Juáre")
        assert w._timer.isActive()
        w._timer.stop()
        w.search_now(interactive=True)
        assert servicio.consultas == [("Juáre", True)]

    def test_enter_is_an_explicit_search(self, app):
        """La única forma de llegar a Nominatim."""
        servicio = _Servicio()
        w = _widget(servicio)
        w._search_box.setText("Juárez 120")
        w._timer.stop()
        w._search_box.returnPressed.emit()
        assert servicio.consultas[-1] == ("Juárez 120", False)

    def test_suggestions_and_attribution_are_shown(self, app):
        w = _widget(_Servicio())
        w._search_box.setText("Juárez 120")
        w.search_now(interactive=True)
        assert w._suggestions.count() == 1
        assert w._attribution.text() == "© Mapbox"

    def test_a_stale_response_is_discarded(self, app):
        """Una respuesta lenta de una consulta ya superada no puede reemplazar
        a la vigente."""
        w = _widget(_Servicio())
        w._request_id = 7
        w._on_result(6, AddressSearchResult(
            AddressSearchStatus.OK, suggestions=(_SUGERENCIA,)))
        assert w._suggestions.count() == 0

    def test_the_status_message_explains_a_fallback(self, app):
        servicio = _Servicio(AddressSearchResult(
            AddressSearchStatus.NEEDS_EXPLICIT_SEARCH,
            message="Mapbox: sin conexión con el servicio. Presiona Enter para buscar "
                    "con OpenStreetMap."))
        w = _widget(servicio)
        w._search_box.setText("Juárez 120")
        w.search_now(interactive=True)
        assert "Enter" in w._status.text()


class TestFillingAndEditing:
    def test_choosing_a_suggestion_fills_every_field(self, app):
        w = _widget(_Servicio())
        w._search_box.setText("Juárez 120")
        w.search_now(interactive=True)
        _elegir_primera(w)
        v = w.value()
        assert (v.street, v.exterior_number, v.neighborhood, v.postal_code) == (
            "Avenida Juárez", "120", "Centro", "06050")
        assert v.is_geocoded and v.source is AddressSource.MAPBOX

    def test_interior_and_references_typed_before_are_kept(self, app):
        """Ningún proveedor sabe el número interior ni las referencias."""
        w = _widget(_Servicio(), with_references=True)
        w.field("interior_number").setText("4B")
        w.field("references").setText("Portón verde")
        w._search_box.setText("Juárez 120")
        w.search_now(interactive=True)
        _elegir_primera(w)
        assert (w.value().interior_number, w.value().references) == ("4B", "Portón verde")

    def test_correcting_a_locating_field_drops_the_coordinates(self, app):
        """Guardar las coordenadas de una sugerencia sobre una calle corregida a
        mano mandaría al repartidor a otro sitio."""
        w = _widget(_Servicio())
        w._search_box.setText("Juárez 120")
        w.search_now(interactive=True)
        _elegir_primera(w)
        w.field("exterior_number").setText("122")
        w.field("exterior_number").textEdited.emit("122")
        v = w.value()
        assert v.source is AddressSource.MANUAL and not v.is_geocoded
        assert v.exterior_number == "122"

    def test_editing_the_interior_number_keeps_the_coordinates(self, app):
        w = _widget(_Servicio())
        w._search_box.setText("Juárez 120")
        w.search_now(interactive=True)
        _elegir_primera(w)
        w.field("interior_number").textEdited.emit("4")
        assert w.value().is_geocoded

    def test_set_value_accepts_a_single_line(self, app):
        """Lo que guardan los módulos de un solo campo (Configuración)."""
        w = _widget()
        w.set_value("Av. Juárez 120, Centro")
        assert w.value().street == "Av. Juárez 120, Centro"


class TestWithoutService:
    def test_the_fields_still_work_and_the_reason_is_explained(self, app):
        """Sin servicio no hay búsqueda, pero sí dirección."""
        w = _widget(None)
        assert not w._search_box.isEnabled()
        assert "Integraciones" in w._status.text()
        w.field("street").setText("Calle Uno")
        assert w.value().street == "Calle Uno"
        assert w.value().source is AddressSource.MANUAL


class TestThreadPool:
    def test_the_search_runs_off_the_ui_thread_and_comes_back(self, app):
        """El ejecutor real: la búsqueda corre en el pool y la respuesta vuelve
        al hilo de la interfaz."""
        import threading
        from PyQt5.QtCore import QThreadPool

        hilos = []

        class _Registra(_Servicio):
            def search(self, query, *, interactive):
                hilos.append(threading.current_thread())
                return super().search(query, interactive=interactive)

        w = AddressInput(search_service=_Registra(), runner=ThreadPoolRunner(),
                         debounce_ms=0)
        w._search_box.setText("Juárez 120")
        w._timer.stop()
        w.search_now(interactive=True)
        QThreadPool.globalInstance().waitForDone(3000)
        for _ in range(50):
            app.processEvents()
            if w._suggestions.count():
                break
        assert w._suggestions.count() == 1
        assert hilos and hilos[0] is not threading.main_thread()


class TestInsideADialog:
    def test_enter_searches_and_does_not_accept_the_dialog(self, app):
        """Enter es el gesto para buscar con Nominatim. Si la tecla escapara al
        diálogo, se activaría "Aceptar" y la captura se cerraría a medias."""
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

        servicio = _Servicio()
        dialogo = QDialog()
        lay = QVBoxLayout(dialogo)
        w = AddressInput(dialogo, search_service=servicio, runner=SyncRunner(),
                         debounce_ms=0)
        lay.addWidget(w)
        caja = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialogo)
        caja.button(QDialogButtonBox.Ok).setDefault(True)
        caja.accepted.connect(dialogo.accept)
        lay.addWidget(caja)
        aceptado = []
        dialogo.accepted.connect(lambda: aceptado.append(True))
        dialogo.show()
        w._search_box.setText("Juárez 120")
        w._timer.stop()
        QTest.keyClick(w._search_box, Qt.Key_Return)
        assert servicio.consultas[-1] == ("Juárez 120", False)
        assert aceptado == []
        dialogo.close()
