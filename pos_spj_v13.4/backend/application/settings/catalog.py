"""Catálogo de parámetros gobernados — la ÚNICA lista de lo que se configura.

Ningún parámetro existe sin estar aquí (§5: "No debe almacenar parámetros
arbitrarios sin definición previa"). Cada entrada declara tipo, valor por
omisión, ámbitos permitidos y si el cambio exige aprobación. La migración que
crea las definiciones (`sync_configuration_catalog`) se basa en esta lista, y
`ConfigurationReader` sólo resuelve claves que estén en ella.

Agregar un parámetro: una entrada nueva aquí y una migración que llame a
`sync_configuration_catalog` (es idempotente).

Los valores por omisión son los mismos que usaba cada contexto antes del corte
(2026-10-04): cambiarlos alteraría en silencio una instalación sin valor
guardado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.costing.services.joint_cost_allocation import AllocationMethod
from backend.domain.loyalty_cards.policies.privacy_policy import CardNameMode
from backend.domain.settings.entities.configuration_definition import ConfigurationDefinition
from backend.domain.settings.enums import ScopeType, ValueType

_G = ScopeType.GLOBAL
_PROCUREMENT_SCOPES = frozenset({_G, ScopeType.SUPPLIER})


@dataclass(frozen=True)
class SettingSpec:
    key: str
    module: str
    section: str
    label: str
    value_type: ValueType
    default_value: object
    description: str = ""
    allowed_scopes: frozenset[ScopeType] = field(default_factory=lambda: frozenset({_G}))
    allowed_values: tuple[str, ...] | None = None
    validation_schema: dict | None = None
    approval_required: bool = False
    sensitive: bool = False
    restart_required: bool = False


SETTINGS_CATALOG: tuple[SettingSpec, ...] = (
    *(SettingSpec(f"customer_display.{key}", "customer_display", "Pantalla del cliente", label,
                  ValueType.BOOLEAN, default,
                  allowed_scopes=frozenset({_G, ScopeType.COMPANY, ScopeType.BRANCH, ScopeType.WORKSTATION}))
      for key, label, default in (
          ("enabled", "Habilitar pantalla del cliente", True),
          ("fullscreen", "Pantalla completa", False),
          ("show_items", "Mostrar carrito", True),
          ("show_unit_price", "Mostrar precio unitario", True),
          ("show_discounts", "Mostrar descuentos", True),
          ("show_tax", "Mostrar impuestos", True),
          ("show_points", "Mostrar puntos", True),
          ("show_scale", "Mostrar lectura de báscula", True),
          ("show_change", "Mostrar cambio confirmado", True),
          ("ads_during_sale", "Publicidad durante la venta", True))),
    SettingSpec("customer_display.screen_name", "customer_display", "Pantalla del cliente",
                "Nombre de pantalla física (vacío: automática)", ValueType.STRING, "",
                allowed_scopes=frozenset({_G, ScopeType.BRANCH, ScopeType.WORKSTATION})),
    SettingSpec("customer_display.thank_you_seconds", "customer_display", "Pantalla del cliente",
                "Segundos del agradecimiento", ValueType.INTEGER, 8,
                validation_schema={"min": 1, "max": 120},
                allowed_scopes=frozenset({_G, ScopeType.COMPANY, ScopeType.BRANCH, ScopeType.WORKSTATION})),
    SettingSpec("customer_display.thank_you_message", "customer_display", "Pantalla del cliente",
                "Mensaje de agradecimiento", ValueType.STRING, "¡Gracias por tu compra!\n¡Te esperamos pronto!",
                allowed_scopes=frozenset({_G, ScopeType.COMPANY, ScopeType.BRANCH, ScopeType.WORKSTATION})),
    SettingSpec("customer_display.welcome_message", "customer_display", "Pantalla del cliente",
                "Mensaje de bienvenida", ValueType.STRING, "Bienvenido",
                allowed_scopes=frozenset({_G, ScopeType.COMPANY, ScopeType.BRANCH, ScopeType.WORKSTATION})),
    SettingSpec("sales.scale_stale_seconds", "sales", "Báscula", "Vigencia de lectura (segundos)",
                ValueType.DECIMAL, Decimal("3"), validation_schema={"min": 1, "max": 30},
                allowed_scopes=frozenset({_G, ScopeType.BRANCH, ScopeType.DEVICE})),
    # ── Fidelidad: programa de puntos ────────────────────────────────────
    SettingSpec(
        "loyalty.pesos_per_point", "loyalty", "Programa de puntos", "Pesos por punto",
        ValueType.DECIMAL, Decimal("10"), "Cuántos pesos de compra acumulan un punto.",
        validation_schema={"min": 0.01}),
    SettingSpec(
        "loyalty.credit_earns", "loyalty", "Programa de puntos",
        "Las ventas a crédito acumulan al cobrarse", ValueType.BOOLEAN, True,
        "Auditoría 968e0bc FID-04: lo vendido a crédito no acumula al vender; con esto "
        "activo acumula cuando el cliente lo paga, en proporción a lo cobrado."),
    SettingSpec(
        "loyalty.points_expiration_months", "loyalty", "Programa de puntos",
        "Vigencia de los puntos (meses)", ValueType.INTEGER, 12,
        "0 = los puntos no caducan.", validation_schema={"min": 0, "max": 120}),
    SettingSpec(
        "loyalty.point_value", "loyalty", "Programa de puntos", "Valor del punto al canjear",
        ValueType.MONEY, Decimal("0.10"), validation_schema={"min": 0.01}),
    SettingSpec(
        "loyalty.min_points_to_redeem", "loyalty", "Programa de puntos",
        "Mínimo de puntos para canjear", ValueType.INTEGER, 0, validation_schema={"min": 0}),
    SettingSpec(
        "loyalty.benefit_min_margin_percent", "loyalty", "Programa de puntos",
        "Margen mínimo protegido (%)", ValueType.DECIMAL, Decimal("10"),
        "Auditoría 968e0bc FID-03: puntos, cupones, promociones y descuentos de una venta "
        "nunca dejan menos de este margen sobre el costo. Se puede fijar otro por "
        "categoría o producto en Fidelidad → Beneficios.",
        validation_schema={"min": 0, "max": 90}),
    SettingSpec(
        "loyalty.manual_adjust_max_points", "loyalty", "Programa de puntos",
        "Tope de una corrección manual (puntos)", ValueType.INTEGER, 500,
        "Auditoría 968e0bc FID-05: más que esto no se corrige a mano, aunque lo "
        "autorice otra persona.", validation_schema={"min": 1, "max": 1000000}),
    SettingSpec(
        "loyalty.manual_adjust_daily_max_points", "loyalty", "Programa de puntos",
        "Tope diario de correcciones manuales a favor por cliente (puntos)",
        ValueType.INTEGER, 1000, validation_schema={"min": 1, "max": 10000000}),
    SettingSpec(
        "loyalty.max_redeem_fraction", "loyalty", "Programa de puntos",
        "Parte máxima del ticket pagadera con puntos", ValueType.DECIMAL, Decimal("0.5"),
        "Fracción del subtotal: 0.5 = la mitad.", validation_schema={"min": 0.01, "max": 1}),
    # ── Tarjetas de fidelidad: privacidad ────────────────────────────────
    SettingSpec(
        "loyalty_cards.printed_name_mode", "loyalty_cards", "Privacidad de tarjetas",
        "Nombre impreso en la tarjeta", ValueType.ENUM, CardNameMode.FULL_NAME.value,
        allowed_values=tuple(m.value for m in CardNameMode)),
    SettingSpec(
        "loyalty_cards.print_points_balance", "loyalty_cards", "Privacidad de tarjetas",
        "Imprimir el saldo de puntos", ValueType.BOOLEAN, False),
    # ── Procesamiento cárnico: tolerancias de rendimiento ────────────────
    SettingSpec(
        "meat_processing.yield.warning_pct", "meat_processing", "Tolerancias de rendimiento",
        "Aviso de rendimiento (%)", ValueType.PERCENT, Decimal("2"),
        validation_schema={"min": 0}),
    SettingSpec(
        "meat_processing.yield.tolerance_pct", "meat_processing", "Tolerancias de rendimiento",
        "Tolerancia de rendimiento (%)", ValueType.PERCENT, Decimal("5"),
        "Se afina por empresa, sucursal, planta, área, centro de trabajo, categoría, "
        "especie, proceso o producto.",
        allowed_scopes=frozenset({
            _G, ScopeType.COMPANY, ScopeType.BRANCH, ScopeType.PLANT, ScopeType.PRODUCTION_AREA,
            ScopeType.WORK_CENTER, ScopeType.PRODUCT_CATEGORY, ScopeType.SPECIES,
            ScopeType.PROCESS, ScopeType.PRODUCT}),
        validation_schema={"min": 0}),
    SettingSpec(
        "meat_processing.yield.critical_pct", "meat_processing", "Tolerancias de rendimiento",
        "Rendimiento crítico (%)", ValueType.PERCENT, Decimal("10"),
        validation_schema={"min": 0}),
    # ── Costeo ───────────────────────────────────────────────────────────
    SettingSpec(
        "costing.cost_policy", "costing", "Política de costo", "Costo multi-sucursal",
        ValueType.ENUM, "GLOBAL", "GLOBAL: un costo para la empresa; PER_BRANCH: por sucursal.",
        allowed_values=("GLOBAL", "PER_BRANCH")),
    SettingSpec(
        "costing.processing.allocation_method", "costing", "Costeo de procesamiento",
        "Método de reparto del costo conjunto", ValueType.ENUM,
        AllocationMethod.RELATIVE_SALES_VALUE.value,
        allowed_values=tuple(m.value for m in AllocationMethod)),
    SettingSpec(
        "costing.processing.allocation_factors", "costing", "Costeo de procesamiento",
        "Factores de reparto por producto", ValueType.JSON_SCHEMA, {},
        "Producto → factor, para el método por factor configurado."),
    SettingSpec(
        "costing.processing.separable_costs", "costing", "Costeo de procesamiento",
        "Costos separables por producto", ValueType.JSON_SCHEMA, {}),
    # ── Compras: tolerancias de factura (afinables por proveedor) ───────
    SettingSpec(
        "procurement.tolerance.quantity", "procurement", "Tolerancias de factura",
        "Tolerancia de cantidad (%)", ValueType.PERCENT, Decimal("0"),
        allowed_scopes=_PROCUREMENT_SCOPES, validation_schema={"min": 0}),
    SettingSpec(
        "procurement.tolerance.price", "procurement", "Tolerancias de factura",
        "Tolerancia de precio (%)", ValueType.PERCENT, Decimal("0"),
        allowed_scopes=_PROCUREMENT_SCOPES, validation_schema={"min": 0}),
    SettingSpec(
        "procurement.tolerance.tax", "procurement", "Tolerancias de factura",
        "Tolerancia de impuestos (%)", ValueType.PERCENT, Decimal("0"),
        allowed_scopes=_PROCUREMENT_SCOPES, validation_schema={"min": 0}),
    # ── Productos (PROD-22, §45): sólo lo que el código lee ──────────────
    SettingSpec(
        "products.defaults.product_type", "products", "Valores por omisión",
        "Tipo de producto al dar de alta", ValueType.ENUM, "RESALE_PRODUCT",
        "Tipo con el que abre la ficha de un producto nuevo.",
        allowed_values=(
            "RESALE_PRODUCT", "RAW_MATERIAL", "LIVE_ANIMAL", "CARCASS", "HALF_CARCASS",
            "QUARTER", "PRIMARY_CUT", "SECONDARY_CUT", "TRIM", "GROUND_MEAT", "OFFAL",
            "BY_PRODUCT", "CO_PRODUCT", "WASTE", "SEMI_FINISHED_GOOD", "FINISHED_GOOD",
            "PRODUCTION_COMPONENT", "PACKAGING_MATERIAL", "CONSUMABLE", "MRO_MATERIAL",
            "SPARE_PART", "SERVICE", "VIRTUAL_BUNDLE", "STOCKED_KIT",
            "RETURNABLE_CONTAINER")),
    SettingSpec(
        "products.defaults.base_unit_code", "products", "Valores por omisión",
        "Unidad base al dar de alta (código)", ValueType.STRING, "",
        "Código de la unidad (p. ej. KG). Vacío = sin unidad preseleccionada."),
    # Exigencias ADICIONALES para activar (decisión del usuario, 2026-10-10:
    # «sólo endurecer»). Las prohibiciones del §7 —especie en cárnicos, no
    # autoaprobar, código activo único, revisión de datos externos— son fijas y
    # NO están aquí. Apagadas por omisión: nada cambia hasta que se encienden.
    SettingSpec(
        "products.require.meat_classification", "products", "Exigencias para activar",
        "Clasificación cárnica (categoría o corte) en productos cárnicos",
        ValueType.BOOLEAN, False),
    SettingSpec(
        "products.require.shelf_life_for_perishables", "products", "Exigencias para activar",
        "Vida útil en productos que controlan caducidad o son perecederos",
        ValueType.BOOLEAN, False),
    SettingSpec(
        "products.require.quality_profile_for_meat", "products", "Exigencias para activar",
        "Perfil de calidad en productos cárnicos", ValueType.BOOLEAN, False),
    SettingSpec(
        "products.require.catch_weight_range", "products", "Exigencias para activar",
        "Rango de peso en productos de peso variable", ValueType.BOOLEAN, False),
    SettingSpec(
        "products.yield.default_tolerance_pct", "products", "Valores por omisión",
        "Tolerancia de rendimiento por omisión (%)", ValueType.PERCENT, Decimal("0"),
        "Con la que abre un perfil de rendimiento nuevo.",
        validation_schema={"min": 0, "max": 100}),
    SettingSpec(
        "products.alerts.enabled", "products", "Alertas",
        "Avisar datos faltantes al guardar un producto", ValueType.BOOLEAN, False,
        "Las alertas del §35 (incompleto, cárnico sin especie, perecedero sin vida "
        "útil…) llegan a la campana de los roles indicados."),
    SettingSpec(
        "products.alerts.recipient_roles", "products", "Alertas",
        "Roles que reciben las alertas", ValueType.STRING, "system_owner,admin,gerente",
        "Nombres de rol separados por coma."),
    SettingSpec(
        "products.alerts.whatsapp_enabled", "products", "Alertas",
        "Enviar por WhatsApp las alertas de alto impacto", ValueType.BOOLEAN, False,
        "Sólo las críticas (bloqueo de calidad, cárnico sin perfil sanitario…)."),
    SettingSpec(
        "products.alerts.whatsapp_phones", "products", "Alertas",
        "Teléfonos para WhatsApp", ValueType.STRING, "",
        "Números con lada, separados por coma.", sensitive=True),
)

CATALOG_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SETTINGS_CATALOG}


def build_definition(spec: SettingSpec, *, existing_id: str | None = None) -> ConfigurationDefinition:
    """La definición de dominio de una entrada; conserva el id si ya existía."""
    definition = ConfigurationDefinition.create(
        spec.key, module=spec.module, label=spec.label, value_type=spec.value_type,
        allowed_scopes=spec.allowed_scopes, section=spec.section, description=spec.description,
        default_value=spec.default_value, validation_schema=spec.validation_schema,
        allowed_values=spec.allowed_values, approval_required=spec.approval_required,
        sensitive=spec.sensitive, restart_required=spec.restart_required,
    )
    if existing_id:
        definition.id = existing_id
    return definition


def sync_configuration_catalog(connection) -> int:
    """Crea o actualiza en la base la definición de cada entrada. Idempotente.

    No hace commit: lo llama una migración, que confirma al final.
    """
    from backend.infrastructure.db.repositories.settings.configuration_definition_repository import (  # noqa: E501
        SqliteConfigurationDefinitionRepository,
    )

    repository = SqliteConfigurationDefinitionRepository(connection)
    count = 0
    for spec in SETTINGS_CATALOG:
        existing = repository.get_by_key(spec.key)
        repository.save(build_definition(spec, existing_id=existing.id if existing else None))
        count += 1
    return count

