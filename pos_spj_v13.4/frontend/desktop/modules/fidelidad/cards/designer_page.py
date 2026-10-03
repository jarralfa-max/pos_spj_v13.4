"""Loyalty Card Studio — diseñador declarativo de tarjetas (LOY-29, §34-36).

El diseño es DATOS: una lista de capas por cara (anverso `elements`, reverso
`back_elements`) con tipo, posición y tamaño en milímetros. No hay código, HTML
ni scripts: el dominio (`validate_design_schema`) valida contra una lista
blanca antes de guardar, y guardar SIEMPRE crea una versión nueva de la
plantilla (§33) que otra persona aprueba.

La vista previa dibuja la tarjeta a escala con valores de ejemplo, el área
segura y las capas en su orden. El QR y el código de barras se muestran como
marcadores: los reales los genera el renderizador con el token de cada tarjeta.
"""

from __future__ import annotations

import json

from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from backend.application.loyalty.queries.records_query_service import LoyaltyRecord
from frontend.desktop.modules.fidelidad.cards.card_preview import DEFAULT_CANVAS, CardPreview
from frontend.desktop.components import (
    ColumnSpec,
    FormField,
    SearchableComboBox,
    StandardTable,
)
from frontend.desktop.components.buttons import (
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.components.pages import StandardPage
from frontend.desktop.themes.tokens import Spacing

VARIABLES = (
    ("customer_name", "Nombre del cliente"), ("card_number", "Número de tarjeta"),
    ("program_name", "Programa"), ("membership_tier", "Nivel"),
    ("expiry_date", "Vigencia"), ("points_balance", "Puntos (sólo si la política lo permite)"),
)

_PLANTILLAS = {
    "TEXT": {"type": "TEXT", "content": "Texto", "align": "LEFT",
             "x_mm": "5", "y_mm": "5", "width_mm": "40", "height_mm": "6"},
    "VARIABLE": {"type": "TEXT", "content": "{{customer_name}}", "align": "LEFT",
                 "x_mm": "5", "y_mm": "40", "width_mm": "50", "height_mm": "6"},
    "QR": {"type": "QR", "data_source": "CARD_TOKEN",
           "x_mm": "60", "y_mm": "25", "width_mm": "20", "height_mm": "20"},
    "BARCODE": {"type": "BARCODE", "format": "CODE128", "data_source": "CARD_NUMBER",
                "x_mm": "5", "y_mm": "44", "width_mm": "45", "height_mm": "7"},
    "RECTANGLE": {"type": "SHAPE", "shape_type": "RECTANGLE",
                  "x_mm": "2", "y_mm": "2", "width_mm": "81", "height_mm": "49"},
    "LINE": {"type": "SHAPE", "shape_type": "LINE",
             "x_mm": "5", "y_mm": "20", "width_mm": "75", "height_mm": "0.5"},
    "LOGO": {"type": "IMAGE", "source": "LOGO",
             "x_mm": "5", "y_mm": "5", "width_mm": "20", "height_mm": "10"},
}

_ETIQUETAS = {"TEXT": "Texto", "QR": "QR", "BARCODE": "Código de barras",
              "SHAPE": "Figura", "IMAGE": "Imagen"}

_CARAS = (("elements", "Anverso"), ("back_elements", "Reverso"))


class CardDesignerPage(StandardPage):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent, title="Diseñador", subtitle="Diseño declarativo: capas, variables y guías. Guardar crea una versión nueva.")
        self.setObjectName("fidelidadCardDesignerPage")
        self.setAccessibleName("Diseñador de tarjetas")
        self._presenter = presenter
        self._canvas = dict(DEFAULT_CANVAS)
        self._faces: dict[str, list[dict]] = {"elements": [], "back_elements": []}
        self._face = "elements"
        self._loaded = False

        layout = self.content_layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        barra = QHBoxLayout()
        self.template = SearchableComboBox(self, placeholder="Elige una plantilla")
        barra.addWidget(self.template, stretch=2)
        cargar = create_secondary_button(self, "Cargar diseño")
        cargar.clicked.connect(self.load_design)
        barra.addWidget(cargar)
        self.face = SearchableComboBox(self, placeholder="Cara")
        self.face.set_options(list(_CARAS))
        self.face.set_current_id("elements")
        self.face.selection_changed.connect(self._change_face)
        barra.addWidget(self.face)
        layout.addLayout(barra)
        # Validar y guardar viven en la barra fija de acciones de la página: siempre
        # visibles, sin importar el ancho de la ventana.
        validar = create_secondary_button(self, "Validar")
        validar.clicked.connect(self.validate)
        self.add_action(validar)
        self.save_button = create_primary_button(self, "Guardar versión")
        self.save_button.clicked.connect(self.save)
        self.add_action(self.save_button)

        self.notice = QLabel("", self)
        self.notice.setObjectName("fidelidadDesignerNotice")
        self.notice.setWordWrap(True)
        self.notice.hide()
        layout.addWidget(self.notice)

        cuerpo = QSplitter(self)
        izquierda = QWidget(cuerpo)
        col = QVBoxLayout(izquierda)
        col.setContentsMargins(0, 0, 0, 0)
        self.layers = StandardTable([
            ColumnSpec("Capa", "numeric"), ColumnSpec("Tipo"), ColumnSpec("Contenido")],
            izquierda)
        self.layers.itemSelectionChanged.connect(self._select_layer)
        col.addWidget(self.layers, stretch=1)
        agregar = QGridLayout()
        agregar.setHorizontalSpacing(Spacing.SM)
        agregar.setVerticalSpacing(Spacing.XS)
        for indice, (clave, texto) in enumerate((
                ("TEXT", "Texto"), ("VARIABLE", "Variable"), ("QR", "QR"),
                ("BARCODE", "Código de barras"), ("RECTANGLE", "Rectángulo"),
                ("LINE", "Línea"), ("LOGO", "Logo"))):
            boton = create_secondary_button(izquierda, texto)
            boton.setObjectName(f"fidelidadDesignerAdd_{clave}")
            boton.clicked.connect(lambda _=False, k=clave: self.add_element(k))
            agregar.addWidget(boton, indice // 4, indice % 4)
        col.addLayout(agregar)
        orden = QHBoxLayout()
        for texto, accion in (("Subir capa", -1), ("Bajar capa", 1)):
            boton = create_secondary_button(izquierda, texto)
            boton.clicked.connect(lambda _=False, d=accion: self.move_layer(d))
            orden.addWidget(boton)
        quitar = create_secondary_button(izquierda, "Quitar capa")
        quitar.clicked.connect(self.remove_layer)
        orden.addWidget(quitar)
        orden.addStretch(1)
        col.addLayout(orden)

        derecha = QWidget(cuerpo)
        col2 = QVBoxLayout(derecha)
        col2.setContentsMargins(0, 0, 0, 0)
        self.preview = CardPreview(derecha)
        col2.addWidget(self.preview, stretch=1)
        self.x_mm, self.y_mm = DecimalInput(derecha), DecimalInput(derecha)
        self.w_mm, self.h_mm = DecimalInput(derecha), DecimalInput(derecha)
        self.content = StandardLineEdit(derecha)
        self.variable = SearchableComboBox(derecha, placeholder="Insertar variable")
        self.variable.set_options(list(VARIABLES))
        self.variable.selection_changed.connect(self._insert_variable)
        self.align = SearchableComboBox(derecha, placeholder="Alineación")
        self.align.set_options([("LEFT", "Izquierda"), ("CENTER", "Centro"), ("RIGHT", "Derecha")])
        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(Spacing.SM)
        rejilla.setVerticalSpacing(Spacing.XS)
        for indice, (etiqueta, campo) in enumerate((
                ("X (mm)", self.x_mm), ("Y (mm)", self.y_mm), ("Ancho (mm)", self.w_mm),
                ("Alto (mm)", self.h_mm))):
            rejilla.addWidget(FormField(etiqueta, campo, derecha), indice // 2, indice % 2)
        rejilla.addWidget(FormField("Texto", self.content, derecha), 2, 0, 1, 2)
        rejilla.addWidget(FormField("Variable", self.variable, derecha), 3, 0)
        rejilla.addWidget(FormField("Alineación", self.align, derecha), 3, 1)
        col2.addLayout(rejilla)
        aplicar = create_secondary_button(derecha, "Aplicar cambios a la capa")
        aplicar.clicked.connect(self.apply_properties)
        col2.addWidget(aplicar)
        cuerpo.addWidget(izquierda)
        cuerpo.addWidget(derecha)
        layout.addWidget(cuerpo, stretch=1)
        self._refresh()

    # ── ciclo de vida ──────────────────────────────────────────────────────
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.template.set_options(self._presenter.record_options(
                LoyaltyRecord.CARD_TEMPLATES, ("name", "code")))
            self._loaded = True

    def design_schema(self) -> dict:
        esquema = {"canvas": dict(self._canvas), "elements": list(self._faces["elements"])}
        if self._faces["back_elements"]:
            esquema["back_elements"] = list(self._faces["back_elements"])
        return esquema

    def design_json(self) -> str:
        return json.dumps(self.design_schema(), ensure_ascii=False)

    # ── acciones ───────────────────────────────────────────────────────────
    def load_design(self) -> None:
        template_id = self.template.current_id()
        if not template_id:
            self._notify(False, "Elige una plantilla.")
            return
        encontrado = self._presenter.card_design(template_id)
        if encontrado is None:
            self._canvas = dict(DEFAULT_CANVAS)
            self._faces = {"elements": [], "back_elements": []}
            self._notify(True, "La plantilla aún no tiene diseño: empieza desde cero (CR80).")
        else:
            version, texto = encontrado
            esquema = json.loads(texto)
            self._canvas = esquema.get("canvas", dict(DEFAULT_CANVAS))
            self._faces = {"elements": list(esquema.get("elements", [])),
                           "back_elements": list(esquema.get("back_elements", []))}
            self._notify(True, f"Versión {version} cargada. Guardar creará una versión nueva.")
        self._refresh()

    def add_element(self, kind: str) -> None:
        self._faces[self._face].append(dict(_PLANTILLAS[kind]))
        self._refresh(select=len(self._faces[self._face]) - 1)

    def remove_layer(self) -> None:
        indice = self._current_index()
        if indice is not None:
            del self._faces[self._face][indice]
            self._refresh()

    def move_layer(self, delta: int) -> None:
        indice = self._current_index()
        capas = self._faces[self._face]
        if indice is None or not 0 <= indice + delta < len(capas):
            return
        capas[indice], capas[indice + delta] = capas[indice + delta], capas[indice]
        self._refresh(select=indice + delta)

    def apply_properties(self) -> None:
        indice = self._current_index()
        if indice is None:
            self._notify(False, "Selecciona una capa.")
            return
        capa = self._faces[self._face][indice]
        for clave, campo in (("x_mm", self.x_mm), ("y_mm", self.y_mm),
                             ("width_mm", self.w_mm), ("height_mm", self.h_mm)):
            valor = campo.decimal_value()
            if valor is not None:
                capa[clave] = str(valor)
        if capa.get("type") == "TEXT":
            capa["content"] = self.content.text()
            if self.align.current_id():
                capa["align"] = self.align.current_id()
        self._refresh(select=indice)

    def validate(self) -> bool:
        ok, mensaje = self._presenter.validate_card_design(self.design_json())
        self._notify(ok, mensaje)
        return ok

    def save(self) -> None:
        template_id = self.template.current_id()
        if not template_id:
            self._notify(False, "Elige la plantilla a la que pertenece el diseño.")
            return
        if not self.validate():
            return
        resultado = self._presenter.run_command(
            "save_card_design", template_id=template_id, design_schema_json=self.design_json())
        ok = bool(getattr(resultado, "success", False))
        self._notify(ok, (resultado.message or "Versión guardada; queda por aprobar.")
                     if ok else (resultado.message or "No se pudo guardar."))

    # ── internos ───────────────────────────────────────────────────────────
    def _change_face(self, face) -> None:
        if face in self._faces:
            self._face = face
            self._refresh()

    def _insert_variable(self, clave) -> None:
        if clave:
            self.content.setText(self.content.text() + "{{" + clave + "}}")

    def _current_index(self) -> int | None:
        fila = self.layers.currentRow()
        return fila if 0 <= fila < len(self._faces[self._face]) else None

    def _select_layer(self) -> None:
        indice = self._current_index()
        if indice is None or indice >= len(self._faces[self._face]):
            return
        capa = self._faces[self._face][indice]
        self.x_mm.set_decimal(capa.get("x_mm"))
        self.y_mm.set_decimal(capa.get("y_mm"))
        self.w_mm.set_decimal(capa.get("width_mm"))
        self.h_mm.set_decimal(capa.get("height_mm"))
        self.content.setText(capa.get("content", ""))
        if capa.get("align"):
            self.align.set_current_id(capa["align"])
        self.preview.show_design(self._canvas, self._faces[self._face], indice)

    def _refresh(self, select: int | None = None) -> None:
        capas = self._faces[self._face]
        self.layers.load_rows(
            [[str(i + 1), _ETIQUETAS.get(c.get("type"), c.get("type", "")),
              c.get("content") or c.get("shape_type") or c.get("source") or c.get("format") or ""]
             for i, c in enumerate(capas)],
            row_ids=[str(i) for i in range(len(capas))])
        if select is not None and 0 <= select < len(capas):
            self.layers.selectRow(select)
        self.preview.show_design(self._canvas, capas, select)

    def _notify(self, ok: bool, mensaje: str) -> None:
        self.notice.setProperty("state", "SUCCESS" if ok else "WARNING")
        self.notice.setText(mensaje)
        self.notice.show()


__all__ = ["CardDesignerPage"]
