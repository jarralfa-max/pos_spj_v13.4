"""Declaración de las páginas de registros de Fidelidad (LOY-29).

Cada página es DATOS: qué registro lista, qué columnas muestra, qué acciones
ofrece y qué pide cada acción. La página genérica (`record_page.py`) y el
diálogo genérico (`action_dialog.py`) los interpretan; ninguna página contiene
reglas de negocio ni SQL (§7, §63). Las reglas —transiciones válidas,
segregación de funciones, saldos— las aplica el caso de uso, y su mensaje es lo
que ve el usuario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from backend.application.loyalty.queries.records_query_service import LoyaltyRecord


class FieldKind(str, Enum):
    TEXT = "text"
    MULTILINE = "multiline"
    INTEGER = "integer"
    DECIMAL = "decimal"          # admite signo (ajustes)
    MONEY = "money"
    DATE = "date"
    CHOICE = "choice"
    BOOL = "bool"
    CUSTOMER = "customer"        # buscador estándar de Clientes
    RECORD = "record"            # elegir una fila de otro registro (programa, plantilla…)
    AUTHORIZER = "authorizer"    # usuario y clave de OTRA persona; entrega su id verificado


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: FieldKind = FieldKind.TEXT
    required: bool = True
    #: CHOICE: opciones de un Enum (valor → etiqueta en `labels.py`).
    enum: type[Enum] | None = None
    #: CHOICE: limitar a estos valores del Enum.
    only: tuple[str, ...] = ()
    #: RECORD: de qué registro y con qué columnas armar la etiqueta.
    record: LoyaltyRecord | None = None
    record_label: tuple[str, ...] = ("name",)
    record_filters: Mapping[str, str] = field(default_factory=dict)
    default: Any = None
    helper: str = ""


@dataclass(frozen=True)
class ActionSpec:
    command: str
    label: str
    permission: str
    fields: tuple[FieldSpec, ...] = ()
    #: Si actúa sobre la fila seleccionada, en qué parámetro la recibe.
    selection_param: str | None = None
    #: Columna de la fila cuyo valor se pasa en lugar del id (p. ej. campaign_id).
    selection_column: str = "id"
    #: Otros parámetros que salen de la fila: parámetro → columna.
    selection_extra: Mapping[str, str] = field(default_factory=dict)
    variant: str = "secondary"   # primary | secondary | danger
    confirm: str = ""
    fixed: Mapping[str, Any] = field(default_factory=dict)
    success: str = "Listo."
    #: La acción devuelve un PDF (`pdf_bytes`) que se ofrece guardar.
    output_pdf: bool = False


@dataclass(frozen=True)
class ColumnDef:
    header: str
    key: str
    kind: str = "text"           # text | numeric | date | status | money | bool | enum
    #: kind="enum": de qué Enum traducir el valor (kind="status" usa el de la página).
    enum: type[Enum] | None = None


@dataclass(frozen=True)
class RecordPageSpec:
    key: str
    title: str
    subtitle: str
    record: LoyaltyRecord
    columns: tuple[ColumnDef, ...]
    status_enum: type[Enum] | None = None
    actions: tuple[ActionSpec, ...] = ()
    empty_message: str = "Sin registros."
    searchable: bool = True


@dataclass(frozen=True)
class TabbedSpec:
    """Una ruta con varios registros relacionados, una pestaña cada uno."""

    key: str
    title: str
    subtitle: str
    tabs: tuple[tuple[str, RecordPageSpec], ...]


__all__ = ["ActionSpec", "ColumnDef", "FieldKind", "FieldSpec", "RecordPageSpec", "TabbedSpec"]
