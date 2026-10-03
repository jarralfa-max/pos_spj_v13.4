"""Catálogo de páginas de registros de Tarjetas de fidelidad (LOY-29).

Mismo mecanismo declarativo que `records/catalog.py`. Los permisos son los de
`TARJETAS_FIDELIDAD` (§59); las reglas —segregación al aprobar plantillas y
lotes, reposición que rota el QR, reimpresión con motivo que no crea tarjeta—
las aplican los casos de uso.
"""

from __future__ import annotations

from backend.application.loyalty.queries.records_query_service import LoyaltyRecord as R
from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions as CP
from backend.domain.loyalty_cards.enums import (
    CardReplacementReason,
    LoyaltyCardBatchStatus,
    LoyaltyCardPrintJobStatus,
    LoyaltyCardStatus,
    LoyaltyCardTemplateStatus,
    LoyaltyCardTemplateTargetType,
    LoyaltyCardTemplateVersionStatus,
    LoyaltyCardType,
    SheetOrientation,
)
from frontend.desktop.modules.fidelidad.records.specs import (
    ActionSpec as A,
    ColumnDef as C,
    FieldKind as K,
    FieldSpec as F,
    RecordPageSpec as P,
    TabbedSpec,
)

_MOTIVO = F("reason", "Motivo", K.MULTILINE)

_CARD_COLUMNS = (
    C("Número", "card_number"), C("Tipo", "card_type", "enum", LoyaltyCardType),
    C("Cliente", "customer_name"), C("Estado", "status", "status"),
    C("Emitida", "issued_at", "date"), C("Activada", "activated_at", "date"),
    C("Vence", "expires_at", "date"))

CARDS = P(
    key="cards", title="Tarjetas", record=R.CARDS, status_enum=LoyaltyCardStatus,
    subtitle="La tarjeta no es la cuenta: reponerla conserva puntos, nivel y movimientos.",
    columns=_CARD_COLUMNS,
    actions=(
        A("issue_card", "Emitir tarjeta", CP.CARD_CREATE, variant="primary", fields=(
            F("membership_id", "Membresía", K.RECORD, record=R.MEMBERSHIPS,
              record_label=("customer_name", "program_name"),
              record_filters={"status": "ACTIVE"}),
            F("card_type", "Tipo", K.CHOICE, enum=LoyaltyCardType, default="PHYSICAL")),
          success="Tarjeta emitida con su QR."),
        A("assign_card", "Asignar", CP.CARD_ASSIGN, selection_param="card_id", fields=(
            F("membership_id", "Membresía", K.RECORD, record=R.MEMBERSHIPS,
              record_label=("customer_name", "program_name"),
              record_filters={"status": "ACTIVE"}),
            F("reason", "Motivo", required=False)),
          success="Tarjeta asignada; actívala al entregarla."),
        A("activate_card", "Activar", CP.CARD_ACTIVATE, selection_param="card_id",
          success="Tarjeta activa."),
        A("block_card", "Bloquear", CP.CARD_BLOCK, selection_param="card_id", variant="danger",
          fields=(_MOTIVO,), success="Tarjeta bloqueada."),
        A("unblock_card", "Desbloquear", CP.CARD_BLOCK, selection_param="card_id",
          success="Tarjeta desbloqueada."),
        A("replace_card", "Reponer", CP.CARD_REPLACE, selection_param="card_id",
          fields=(F("reason", "Motivo", K.CHOICE, enum=CardReplacementReason),),
          confirm="Se bloquea esta tarjeta, se revoca su QR y se emite una nueva con QR nuevo. "
                  "Puntos y nivel se conservan.",
          success="Tarjeta repuesta."),
        A("rotate_card_token", "Rotar QR", CP.QR_ROTATE, selection_param="card_id",
          confirm="El QR actual deja de funcionar y se genera uno nuevo. La tarjeta impresa "
                  "debe reimprimirse.", success="QR rotado."),
        A("cancel_card", "Cancelar", CP.CARD_CANCEL, selection_param="card_id",
          variant="danger", fields=(_MOTIVO,), success="Tarjeta cancelada."),
    ),
    empty_message="Sin tarjetas emitidas.")

TEMPLATES = P(
    key="card_templates", title="Plantillas", record=R.CARD_TEMPLATES,
    status_enum=LoyaltyCardTemplateStatus,
    subtitle="Toda modificación crea una versión nueva; la aprueba otra persona.",
    columns=(C("Código", "code"), C("Nombre", "name"),
             C("Para", "target_type", "enum", LoyaltyCardTemplateTargetType),
             C("Estado", "status", "status"), C("Versión activa", "active_version", "numeric"),
             C("Versiones", "versions", "numeric")),
    actions=(
        A("create_card_template", "Nueva plantilla", CP.TEMPLATE_CREATE, variant="primary",
          fields=(F("code", "Código"), F("name", "Nombre"),
                  F("target_type", "Para", K.CHOICE, enum=LoyaltyCardTemplateTargetType,
                    default="PHYSICAL"),
                  F("description", "Descripción", K.MULTILINE, required=False)),
          success="Plantilla creada y enviada a aprobación. Diséñala en «Diseñador»."),
        A("import_card_design", "Importar diseño", CP.TEMPLATE_IMPORT,
          selection_param="template_id", fields=(
              F("file_path", "Archivo (PNG, JPEG o SVG)", K.FILE,
                file_filter="Diseños (*.png *.jpg *.jpeg *.svg)",
                helper="Se valida tipo, tamaño (10 MB), dimensiones y que el SVG no traiga "
                       "scripts ni enlaces externos. Crea una versión nueva por aprobar."),),
          success="Diseño importado como versión nueva; complétalo en el Diseñador."),
        A("approve_card_template", "Aprobar", CP.TEMPLATE_APPROVE, selection_param="template_id",
          confirm="Quien creó la plantilla no puede aprobarla.", success="Plantilla aprobada."),
        A("archive_card_template", "Archivar", CP.TEMPLATE_ARCHIVE, selection_param="template_id",
          variant="danger", confirm="La plantilla deja de poder usarse en lotes nuevos.",
          success="Plantilla archivada."),
    ),
    empty_message="Sin plantillas.")

TEMPLATE_VERSIONS = P(
    key="card_template_versions", title="Versiones", record=R.CARD_TEMPLATE_VERSIONS,
    status_enum=LoyaltyCardTemplateVersionStatus,
    subtitle="Versiones de diseño. Sólo una versión aprobada puede activarse.",
    columns=(C("Plantilla", "template_name"), C("Versión", "version_number", "numeric"),
             C("Estado", "status", "status"), C("Creada", "created_at", "date"),
             C("Activada", "activated_at", "date")),
    actions=(
        A("approve_card_template_version", "Aprobar versión", CP.TEMPLATE_APPROVE,
          selection_param="version_id", confirm="Quien diseñó la versión no puede aprobarla.",
          success="Versión aprobada."),
        A("activate_card_template_version", "Activar versión", CP.TEMPLATE_ACTIVATE,
          selection_param="version_id", success="Versión activa."),
    ),
    empty_message="Sin versiones. Crea una desde el Diseñador.")

TEMPLATES_TABS = TabbedSpec(key="card_templates", title="Plantillas",
                            subtitle="Plantillas y sus versiones de diseño.",
                            tabs=(("Plantillas", TEMPLATES), ("Versiones", TEMPLATE_VERSIONS)))

SHEETS = P(
    key="card_sheets", title="Pliegos", record=R.CARD_SHEETS, status_enum=SheetOrientation,
    subtitle="Medidas del pliego en milímetros (12 × 18 pulgadas = 304.8 × 457.2 mm).",
    columns=(C("Código", "code"), C("Nombre", "name"), C("Ancho (mm)", "width_mm", "numeric"),
             C("Alto (mm)", "height_mm", "numeric"), C("Orientación", "orientation", "status"),
             C("Margen sup. (mm)", "margin_top_mm", "numeric"),
             C("Margen izq. (mm)", "margin_left_mm", "numeric"), C("Activo", "active", "bool")),
    actions=(
        A("create_standard_sheet", "Pliego 12 × 18 pulgadas", CP.SHEET_MANAGE, variant="primary",
          confirm="Se crea el perfil estándar SHEET_12X18_IN (304.8 × 457.2 mm).",
          success="Pliego 12 × 18 creado."),
        A("create_sheet", "Pliego personalizado", CP.SHEET_MANAGE, fields=(
            F("code", "Código"), F("name", "Nombre"),
            F("width_mm", "Ancho (mm)", K.DECIMAL), F("height_mm", "Alto (mm)", K.DECIMAL),
            F("orientation", "Orientación", K.CHOICE, enum=SheetOrientation, default="PORTRAIT"),
            F("margin_top_mm", "Margen superior (mm)", K.DECIMAL, required=False),
            F("margin_bottom_mm", "Margen inferior (mm)", K.DECIMAL, required=False),
            F("margin_left_mm", "Margen izquierdo (mm)", K.DECIMAL, required=False),
            F("margin_right_mm", "Margen derecho (mm)", K.DECIMAL, required=False)),
          success="Pliego creado."),
    ),
    empty_message="Sin pliegos. Crea el estándar 12 × 18.")

IMPOSITIONS = P(
    key="card_impositions", title="Imposición", record=R.CARD_IMPOSITIONS,
    subtitle="Cuántas tarjetas caben por pliego; filas y columnas las calcula el sistema.",
    columns=(C("Pliego", "sheet_name"), C("Tarjeta ancho (mm)", "card_width_mm", "numeric"),
             C("Tarjeta alto (mm)", "card_height_mm", "numeric"),
             C("Columnas", "columns", "numeric"), C("Filas", "rows", "numeric"),
             C("Sangrado (mm)", "bleed_mm", "numeric"),
             C("Área segura (mm)", "safe_area_mm", "numeric")),
    actions=(
        A("create_imposition", "Nueva imposición", CP.FORMAT_MANAGE, variant="primary", fields=(
            F("sheet_profile_id", "Pliego", K.RECORD, record=R.CARD_SHEETS,
              record_label=("name", "code")),
            F("card_width_mm", "Ancho de tarjeta (mm)", K.DECIMAL, default="85.6",
              helper="CR80 estándar: 85.6 × 53.98 mm."),
            F("card_height_mm", "Alto de tarjeta (mm)", K.DECIMAL, default="53.98"),
            F("bleed_mm", "Sangrado (mm)", K.DECIMAL, required=False, default="3"),
            F("safe_area_mm", "Área segura (mm)", K.DECIMAL, required=False, default="3"),
            F("gutter_horizontal_mm", "Separación horizontal (mm)", K.DECIMAL, required=False),
            F("gutter_vertical_mm", "Separación vertical (mm)", K.DECIMAL, required=False)),
          success="Imposición calculada."),
    ),
    empty_message="Sin perfiles de imposición.")

SHEETS_TABS = TabbedSpec(key="card_sheets", title="Formatos y pliegos",
                         subtitle="Pliegos de impresión y su imposición sin traslapes.",
                         tabs=(("Pliegos", SHEETS), ("Imposición", IMPOSITIONS)))

BATCHES = P(
    key="card_batches", title="Lotes", record=R.CARD_BATCHES, status_enum=LoyaltyCardBatchStatus,
    subtitle="Quien genera un lote no lo aprueba. Cada tarjeta del lote nace con su QR único.",
    columns=(C("Creado", "created_at", "date"), C("Plantilla", "template_name"),
             C("Tarjetas", "item_count", "numeric"), C("Por pliego", "cards_per_sheet", "numeric"),
             C("Impresas", "printed", "numeric"), C("Estado", "status", "status")),
    actions=(
        A("create_card_batch", "Nuevo lote", CP.BATCH_CREATE, variant="primary", fields=(
            F("program_id", "Programa", K.RECORD, record=R.PROGRAMS,
              record_label=("name", "code"), record_filters={"status": "ACTIVE"},
              helper="Se emite una tarjeta para cada membresía activa sin tarjeta vigente."),
            F("template_id", "Plantilla", K.RECORD, record=R.CARD_TEMPLATES,
              record_label=("name", "code"), record_filters={"status": "ACTIVE"}),
            F("imposition_profile_id", "Imposición", K.RECORD, record=R.CARD_IMPOSITIONS,
              record_label=("sheet_name", "columns", "rows"))),
          success="Lote creado."),
        A("create_preprinted_batch", "Lote preimpreso", CP.BATCH_CREATE, fields=(
            F("blank_quantity", "Cantidad de tarjetas", K.INTEGER,
              helper="Tarjetas con número y QR, sin cliente; se asignan al entregarlas."),
            F("template_id", "Plantilla", K.RECORD, record=R.CARD_TEMPLATES,
              record_label=("name", "code"), record_filters={"status": "ACTIVE"}),
            F("imposition_profile_id", "Imposición", K.RECORD, record=R.CARD_IMPOSITIONS,
              record_label=("sheet_name", "columns", "rows"))),
          success="Lote preimpreso creado."),
        A("submit_card_batch", "Enviar a aprobación", CP.BATCH_CREATE, selection_param="batch_id",
          success="Lote enviado a aprobación."),
        A("approve_card_batch", "Aprobar", CP.BATCH_APPROVE, selection_param="batch_id",
          confirm="Quien generó el lote no puede aprobarlo.", success="Lote aprobado."),
        A("start_card_batch_printing", "Iniciar impresión", CP.BATCH_PRINT,
          selection_param="batch_id", success="Lote en impresión."),
        A("cancel_card_batch", "Cancelar", CP.BATCH_CREATE, selection_param="batch_id",
          variant="danger", confirm="El lote se cancela.", success="Lote cancelado."),
    ),
    empty_message="Sin lotes.")

_JOB_COLUMNS = (
    C("Solicitado", "requested_at", "date"), C("Plantilla", "template_name"),
    C("Pliego", "only_sheet_number", "numeric"), C("Estado", "status", "status"),
    C("Motivo de reimpresión", "reprint_reason"), C("Falla", "failure_reason"),
    C("Solicitó", "requested_by"))

PRINT_JOBS = P(
    key="card_print_jobs", title="Impresión", record=R.CARD_PRINT_JOBS,
    status_enum=LoyaltyCardPrintJobStatus,
    subtitle="Cada impresión es un trabajo registrado; nada se imprime directo desde la pantalla.",
    columns=_JOB_COLUMNS,
    actions=(
        A("render_card_batch", "Generar impresión", CP.BATCH_PRINT, variant="primary", fields=(
            F("batch_id", "Lote", K.RECORD, record=R.CARD_BATCHES,
              record_label=("template_name", "item_count", "created_at"),
              record_filters={"status": "PRINTING"}),),
          success="Impresión generada.", output_pdf=True),
        A("reprint_card_batch", "Reimprimir", CP.REPRINT, selection_param="original_job_id",
          fields=(_MOTIVO,), success="Reimpresión generada: mismas tarjetas, mismos QR.",
          output_pdf=True),
    ),
    empty_message="Sin trabajos de impresión.")

REPRINTS = P(
    key="card_reprints", title="Reimpresiones", record=R.CARD_REPRINTS,
    status_enum=LoyaltyCardPrintJobStatus,
    subtitle="Reimprimir no crea tarjetas ni QR nuevos; siempre lleva motivo y usuario.",
    columns=_JOB_COLUMNS, empty_message="Sin reimpresiones.")

DIGITAL = P(
    key="digital_cards", title="Tarjetas digitales", record=R.DIGITAL_CARDS,
    subtitle="Proyección para WhatsApp y pantalla de cliente; el QR es el de la tarjeta.",
    columns=(C("Número", "card_number"), C("Cliente", "customer_name"),
             C("Actualizada", "last_refreshed_at", "date")),
    actions=(
        A("publish_digital_card", "Publicar / actualizar", CP.CARD_ACTIVATE, variant="primary",
          fields=(F("card_id", "Tarjeta", K.RECORD, record=R.CARDS,
                    record_label=("card_number", "customer_name"),
                    record_filters={"status": "ACTIVE", "card_type": "DIGITAL"}),),
          success="Tarjeta digital actualizada."),
    ),
    empty_message="Sin tarjetas digitales publicadas.")

ASSIGNMENTS = P(
    key="card_assignments", title="Asignaciones", record=R.CARD_ASSIGNMENTS,
    status_enum=LoyaltyCardStatus,
    subtitle="A quién se entregó cada tarjeta preimpresa, quién la asignó y por qué.",
    columns=(C("Fecha", "assigned_at", "date"), C("Tarjeta", "card_number"),
             C("Cliente", "customer_name"), C("Motivo", "assignment_reason"),
             C("Asignó", "assigned_by"), C("Estado de la tarjeta", "card_status", "status")),
    empty_message="Sin asignaciones. Asigna tarjetas preimpresas desde «Tarjetas».")

CARD_AUDIT = P(
    key="card_audit", title="Auditoría de tarjetas", record=R.CARD_AUDIT,
    subtitle="Emisión, activación, bloqueo, reposición, impresión y rotación de QR.",
    columns=(C("Fecha", "fecha", "date"), C("Usuario", "usuario"), C("Acción", "accion"),
             C("Entidad", "entidad"), C("Referencia", "entidad_id")),
    empty_message="Sin registros de auditoría de tarjetas.")

CARD_RECORD_ROUTES: dict[str, P | TabbedSpec] = {
    "cards.cards": CARDS,
    "cards.templates": TEMPLATES_TABS,
    "cards.sheets": SHEETS_TABS,
    "cards.batches": BATCHES,
    "cards.assignments": ASSIGNMENTS,
    "cards.printing": PRINT_JOBS,
    "cards.reprints": REPRINTS,
    "cards.digital": DIGITAL,
    "cards.audit": CARD_AUDIT,
}

__all__ = ["CARD_RECORD_ROUTES"]
