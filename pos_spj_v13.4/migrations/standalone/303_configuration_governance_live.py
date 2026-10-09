"""303 — El gobierno de configuración entra en servicio (SET-26, 2026-10-04).

Hasta aquí `configuration_definitions`/`configuration_values` existían (208)
con 0 filas, y cada contexto leía y escribía sus parámetros como texto suelto
en `configuraciones`. Esta migración:

0. Si `configuration_values` nació antes de los ámbitos nuevos (SPECIES,
   WORK_CENTER, PRODUCTION_AREA, PLANT, SUPPLIER), reconstruye su CHECK: la
   tolerancia de rendimiento de Cárnico se afina por los niveles de planta y la
   de factura de Compras por proveedor.
1. Sincroniza el catálogo de parámetros (`backend/application/settings/catalog.py`).
2. Pasa cada valor guardado en `configuraciones` a una versión 1 ACTIVA en
   ámbito GLOBAL, ya tipada. Las claves de Fidelidad cambian de nombre porque
   el formato canónico es `modulo.parametro` (las anteriores no tenían punto).
   Un valor ilegible NO se migra: se avisa y rige el de omisión, que es el
   mismo respaldo que usaba cada lector al encontrarlo.
   Las tolerancias de Cárnico por nivel (`meat_processing.yield.tolerance_pct@NIVEL:ref`)
   y las de factura por proveedor (`procurement.tolerance.<tipo>.supplier.<id>`)
   pasan a valores del mismo parámetro en el ámbito de ese nivel. Las de factura
   por "naturaleza" se reportan y se retiran: ningún llamador las pedía.
3. Borra de `configuraciones` las claves migradas: una sola fuente (§76).
Los parámetros se editan en la pantalla de su módulo con el permiso de ese
módulo; Configuración no tiene pantalla para ellos (decisión del usuario).

Idempotente: una clave ya migrada no está en `configuraciones`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.303")

#: Clave anterior en `configuraciones` → clave del catálogo.
KEY_MAP = {
    "loyalty_pesos_por_punto": "loyalty.pesos_per_point",
    "loyalty_credito_acumula": "loyalty.credit_earns",
    "loyalty_meses_caducidad": "loyalty.points_expiration_months",
    "loyalty_valor_estrella": "loyalty.point_value",
    "loyalty_min_puntos_canje": "loyalty.min_points_to_redeem",
    "loyalty_max_pct_canje": "loyalty.max_redeem_fraction",
    "loyalty_tarjeta_nombre_impreso": "loyalty_cards.printed_name_mode",
    "loyalty_tarjeta_imprime_puntos": "loyalty_cards.print_points_balance",
    "meat_processing.yield.warning_pct": "meat_processing.yield.warning_pct",
    "meat_processing.yield.tolerance_pct": "meat_processing.yield.tolerance_pct",
    "meat_processing.yield.critical_pct": "meat_processing.yield.critical_pct",
    "costing.cost_policy": "costing.cost_policy",
    "costing.processing.allocation_method": "costing.processing.allocation_method",
    "costing.processing.allocation_factors": "costing.processing.allocation_factors",
    "costing.processing.separable_costs": "costing.processing.separable_costs",
    "procurement.tolerance.quantity.default": "procurement.tolerance.quantity",
    "procurement.tolerance.price.default": "procurement.tolerance.price",
    "procurement.tolerance.tax.default": "procurement.tolerance.tax",
}

#: Nivel de las claves `...tolerance_pct@NIVEL:ref` → ámbito de configuración.
_YIELD_LEVEL_SCOPE = {
    "PRODUCT": "PRODUCT", "PROCESS": "PROCESS", "SPECIES": "SPECIES",
    "CATEGORY": "PRODUCT_CATEGORY", "WORK_CENTER": "WORK_CENTER", "AREA": "PRODUCTION_AREA",
    "PLANT": "PLANT", "BRANCH": "BRANCH", "COMPANY": "COMPANY",
}
_YIELD_OVERRIDE_PREFIX = "meat_processing.yield.tolerance_pct@"

def _migrate_values(conn) -> tuple[int, list[str]]:
    from backend.application.settings.value_coercion import coerce_value
    from backend.domain.settings.entities.configuration_value import ConfigurationValue
    from backend.domain.settings.enums import ConfigurationValueStatus
    from backend.domain.settings.policies.configuration_validation_policy import (
        validate_against_definition,
    )
    from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
    from backend.domain.settings.value_objects.effective_period import EffectivePeriod
    from backend.domain.settings.value_objects.version_number import VersionNumber
    from backend.infrastructure.db.repositories.settings.configuration_definition_repository import (  # noqa: E501
        SqliteConfigurationDefinitionRepository,
    )
    from backend.infrastructure.db.repositories.settings.configuration_value_repository import (
        SqliteConfigurationValueRepository,
    )

    definitions = SqliteConfigurationDefinitionRepository(conn)
    values = SqliteConfigurationValueRepository(conn)
    migrated, skipped = 0, []
    for old_key, new_key in KEY_MAP.items():
        row = conn.execute("SELECT valor FROM configuraciones WHERE clave=?", (old_key,)).fetchone()
        if row is None:
            continue
        definition = definitions.get_by_key(new_key)
        scope = ConfigurationScope.global_scope()
        raw = str(row[0] if row[0] is not None else "").strip()
        try:
            if not raw:
                raise ValueError("vacío")
            typed = coerce_value(definition.value_type, raw)
            validate_against_definition(definition, typed)
        except Exception as exc:  # noqa: BLE001 — un valor ilegible se reporta, no se migra
            skipped.append(f"{old_key}={raw!r} ({exc})")
            conn.execute("DELETE FROM configuraciones WHERE clave=?", (old_key,))
            continue
        if values.latest_in_lineage(definition.id, scope) is None:
            values.save(ConfigurationValue(
                id=new_uuid(), definition_id=definition.id, scope=scope, value=typed,
                effective_period=EffectivePeriod.create(datetime.now(timezone.utc)),
                version=VersionNumber.first(), status=ConfigurationValueStatus.ACTIVE,
                reason=f"Migrado de configuraciones ({old_key})"))
            migrated += 1
        conn.execute("DELETE FROM configuraciones WHERE clave=?", (old_key,))
    return migrated, skipped


def _rebuild_values_scope_check(conn) -> bool:
    fila = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='configuration_values'").fetchone()
    if fila is None or "SUPPLIER" in (fila[0] or ""):
        return False
    from backend.infrastructure.db.schema.settings_schema import _INDEXES, _VALUES_DDL

    nueva = _VALUES_DDL.replace(
        "CREATE TABLE IF NOT EXISTS configuration_values (",
        "CREATE TABLE configuration_values__new (", 1)
    conn.commit()
    previo = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
    conn.execute("PRAGMA legacy_alter_table=ON")
    try:
        conn.execute(nueva)
        conn.execute("INSERT INTO configuration_values__new SELECT * FROM configuration_values")
        conn.execute("DROP TABLE configuration_values")
        conn.execute("ALTER TABLE configuration_values__new RENAME TO configuration_values")
        for ddl in _INDEXES:
            if "configuration_values" in ddl:
                conn.execute(ddl)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table={'ON' if previo else 'OFF'}")
    return True


def _scoped_overrides(conn) -> list[tuple[str, str, str, str, str]]:
    """(clave anterior, valor, clave del catálogo, ámbito, ref) de cada ajuste
    por nivel que hay que migrar."""
    salida = []
    for clave, valor in conn.execute(
            "SELECT clave, valor FROM configuraciones WHERE clave LIKE ?",
            (_YIELD_OVERRIDE_PREFIX + "%",)).fetchall():
        nivel, _, ref = clave[len(_YIELD_OVERRIDE_PREFIX):].partition(":")
        salida.append((clave, valor, "meat_processing.yield.tolerance_pct",
                       _YIELD_LEVEL_SCOPE.get(nivel, ""), ref))
    for clave, valor in conn.execute(
            "SELECT clave, valor FROM configuraciones WHERE clave LIKE 'procurement.tolerance.%.supplier.%'"
    ).fetchall():
        _p, _t, kind, _s, ref = clave.split(".", 4)
        salida.append((clave, valor, f"procurement.tolerance.{kind}", "SUPPLIER", ref))
    for clave, valor in conn.execute(
            "SELECT clave, valor FROM configuraciones WHERE clave LIKE 'procurement.tolerance.%.nature.%'"
    ).fetchall():
        salida.append((clave, valor, "", "", ""))
    return salida


def _migrate_scoped_overrides(conn) -> tuple[int, list[str]]:
    from decimal import Decimal

    from backend.domain.settings.entities.configuration_value import ConfigurationValue
    from backend.domain.settings.enums import ConfigurationValueStatus, ScopeType
    from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
    from backend.domain.settings.value_objects.effective_period import EffectivePeriod
    from backend.domain.settings.value_objects.version_number import VersionNumber
    from backend.infrastructure.db.repositories.settings.configuration_definition_repository import (  # noqa: E501
        SqliteConfigurationDefinitionRepository,
    )
    from backend.infrastructure.db.repositories.settings.configuration_value_repository import (
        SqliteConfigurationValueRepository,
    )

    definitions = SqliteConfigurationDefinitionRepository(conn)
    values = SqliteConfigurationValueRepository(conn)
    migrated, skipped = 0, []
    for clave, valor, key, scope_type, ref in _scoped_overrides(conn):
        try:
            if not key:
                raise ValueError("nivel retirado: ningún llamador lo pedía")
            definition = definitions.get_by_key(key)
            scope = ConfigurationScope.create(ScopeType(scope_type), ref)
            numero = Decimal(str(valor).strip())
            if numero < 0:
                raise ValueError("negativa")
        except Exception as exc:  # noqa: BLE001 — se reporta y no se migra
            skipped.append(f"{clave}={valor!r} ({exc})")
            conn.execute("DELETE FROM configuraciones WHERE clave=?", (clave,))
            continue
        if values.latest_in_lineage(definition.id, scope) is None:
            values.save(ConfigurationValue(
                id=new_uuid(), definition_id=definition.id, scope=scope, value=numero,
                effective_period=EffectivePeriod.create(datetime.now(timezone.utc)),
                version=VersionNumber.first(), status=ConfigurationValueStatus.ACTIVE,
                reason=f"Migrado de configuraciones ({clave})"))
            migrated += 1
        conn.execute("DELETE FROM configuraciones WHERE clave=?", (clave,))
    return migrated, skipped


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def run(conn) -> None:
    from backend.application.settings.catalog import sync_configuration_catalog

    rebuilt = _rebuild_values_scope_check(conn)
    synced = sync_configuration_catalog(conn)
    migrated, skipped = 0, []
    if _table_exists(conn, "configuraciones"):
        migrated, skipped = _migrate_values(conn)
        extra, skipped_extra = _migrate_scoped_overrides(conn)
        migrated += extra
        skipped += skipped_extra
    conn.commit()
    logger.info("303: %s definiciones, %s valores migrados%s.", synced, migrated,
                "; CHECK de ámbitos reconstruido" if rebuilt else "")
    for item in skipped:
        logger.warning("303: valor ilegible no migrado; rige el de omisión: %s", item)


up = run
