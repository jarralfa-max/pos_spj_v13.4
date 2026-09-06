"""§9: ninguna columna monetaria puede declararse REAL/FLOAT/DOUBLE.

Existían cinco guardrules de Decimal por contexto (assets, customers/crm,
inventory, pricing, transfers) pero **ninguno global**, de modo que un contexto
nuevo podía nacer con dinero en coma flotante sin que nada lo detectara. Eso
fue justamente lo que pasó con `whatsapp_order_draft_lines` /
`whatsapp_quote_draft_lines`, que declaraban `quantity REAL` y `unit_price REAL`.

IEEE 754 no puede representar 0.1 ni 2.675 exactamente. Un `REAL` devuelve un
valor distinto del guardado y `round(x, 2)` sobre binario redondea hacia abajo
en los casos .5 — un centavo perdido por línea, sistemático y silencioso.

Este guard cubre el esquema canónico completo. `latitude`/`longitude` son la
única excepción legítima: son coordenadas geográficas, no importes, y la coma
flotante es el tipo correcto para ellas.
"""

from __future__ import annotations

import re

from .architecture_guardrails import APP_ROOT

# Columnas cuyo nombre denota dinero, cantidad o cualquier magnitud que se
# multiplica por dinero. Los nombres siguen la convención del repositorio
# (español e inglés conviven en el esquema por su origen legacy).
_MONETARY_TOKENS = (
    "price", "precio", "amount", "monto", "total", "subtotal", "cost", "costo",
    "importe", "saldo", "balance", "credit", "credito", "debit", "debito",
    "payment", "pago", "discount", "descuento", "tax", "impuesto", "iva",
    "fee", "comision", "commission", "quantity", "cantidad", "weight", "peso",
    "unit_price", "valor", "value",
)

# `latitude`/`longitude` son coordenadas, no importes: REAL es correcto para
# ellas y no deben contarse como deuda.
_GEO_EXEMPT = ("latitude", "longitude", "latitud", "longitud")

_FLOAT_COLUMN_RE = re.compile(
    r"^\s*([a-z_][a-z0-9_]*)\s+(REAL|FLOAT|DOUBLE(?:\s+PRECISION)?)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _monetary_float_columns() -> list[str]:
    offenders: list[str] = []
    schema_root = APP_ROOT / "backend" / "infrastructure" / "db" / "schema"
    for path in sorted(schema_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for match in _FLOAT_COLUMN_RE.finditer(source):
            column = match.group(1).lower()
            if column in _GEO_EXEMPT:
                continue
            if not any(token in column for token in _MONETARY_TOKENS):
                continue
            line = source.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(APP_ROOT).as_posix()}:{line}: {match.group(0).strip()}")
    return offenders


# Deuda legacy medida por este mismo detector: `migrations/` declara 379 columnas
# REAL de dinero o de magnitudes que se multiplican por dinero, la mayoría en
# `m000_base_schema.py` (credit_limit, precio, precio_compra, limite_credito,
# saldo_pendiente… las que §9 del prompt maestro enumera). De ellas, 292 son
# importes en sentido estricto y el resto son cantidades/pesos: ambas contaminan
# el resultado en cuanto se multiplican, así que el detector las trata igual.
#
# NO se convierten en esta fase, y la razón es de semántica, no de tamaño: pasar
# esas columnas a TEXT cambia el resultado de cada `SUM(precio)`, `AVG(total)` y
# comparación numérica que el SQL legacy hace sobre ellas — silenciosamente y sin
# que ninguna prueba lo note. Es un corte con su propia migración y su propia
# validación, no una sustitución de tipos. Mientras tanto queda medida y
# congelada: puede bajar, nunca subir.
_MIGRATIONS_LEGACY_BASELINE = 379


def test_no_monetary_real_columns_in_canonical_schema() -> None:
    offenders = _monetary_float_columns()
    assert not offenders, (
        "Columnas monetarias en coma flotante (§9 exige TEXT decimal / NUMERIC):\n"
        + "\n".join(offenders)
    )


def _migration_monetary_float_columns() -> list[str]:
    offenders: list[str] = []
    for path in sorted((APP_ROOT / "migrations").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for match in _FLOAT_COLUMN_RE.finditer(source):
            column = match.group(1).lower()
            if column in _GEO_EXEMPT:
                continue
            if not any(token in column for token in _MONETARY_TOKENS):
                continue
            line = source.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(APP_ROOT).as_posix()}:{line}: {match.group(0).strip()}")
    return offenders


def test_legacy_migration_monetary_real_debt_does_not_increase() -> None:
    offenders = _migration_monetary_float_columns()
    assert len(offenders) <= _MIGRATIONS_LEGACY_BASELINE, (
        f"La deuda de dinero REAL en migrations/ AUMENTÓ: {len(offenders)} "
        f"(base {_MIGRATIONS_LEGACY_BASELINE}). El esquema nuevo debe usar TEXT decimal.\n"
        + "\n".join(offenders[_MIGRATIONS_LEGACY_BASELINE:])
    )


def test_legacy_migration_baseline_is_not_stale() -> None:
    """Si un corte reduce la deuda, hay que registrarlo bajando la base."""
    offenders = _migration_monetary_float_columns()
    assert len(offenders) == _MIGRATIONS_LEGACY_BASELINE, (
        f"Baseline desactualizado: real {len(offenders)}, base {_MIGRATIONS_LEGACY_BASELINE}. "
        f"Ajusta _MIGRATIONS_LEGACY_BASELINE a {len(offenders)} para dejar constancia del avance."
    )


def test_geographic_coordinates_stay_exempt() -> None:
    """La exención de lat/long no puede ampliarse a importes por descuido."""
    assert not any("latitude" in offender or "longitude" in offender
                   for offender in _monetary_float_columns())


def test_detector_still_flags_a_real_money_column() -> None:
    """El guard no puede degenerar en un no-op al ajustar la lista de tokens."""
    assert _FLOAT_COLUMN_RE.search("        unit_price REAL NOT NULL")
    assert _FLOAT_COLUMN_RE.search("        total_amount DOUBLE PRECISION")
    assert _FLOAT_COLUMN_RE.search("        precio FLOAT,")
    # y no confunde una columna TEXT decimal con una flotante
    assert not _FLOAT_COLUMN_RE.search("        unit_price TEXT NOT NULL")
