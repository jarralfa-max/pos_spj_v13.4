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
    # ── Fidelidad: programa de puntos ────────────────────────────────────
    SettingSpec(
        "loyalty.pesos_per_point", "loyalty", "Programa de puntos", "Pesos por punto",
        ValueType.DECIMAL, Decimal("10"), "Cuántos pesos de compra acumulan un punto.",
        validation_schema={"min": 0.01}),
    SettingSpec(
        "loyalty.credit_earns", "loyalty", "Programa de puntos", "Las ventas a crédito acumulan",
        ValueType.BOOLEAN, True),
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

