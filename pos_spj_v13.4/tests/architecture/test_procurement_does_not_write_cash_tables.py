"""PUR-13.11 — procurement never writes cash/treasury tables directly.

Immediate payment is scheduled via SUPPLIER_PAYMENT_SCHEDULED from an authorized
financial source (never POS operative cash), consumed by the Treasury context.
The canonical procurement code must not touch caja/tesorería nor call
registrar_egreso.

POR QUÉ SE REFORZÓ
-------------------
Esta guardia leía archivos de verdad, pero buscaba nombres MUERTOS:
`INSERT INTO caja`, `UPDATE tesoreria`, `registrar_egreso(`. La Caja canónica
escribe `cash_ledger_entries` a través de `CashRegisterUnitOfWork`, y Tesorería
vive en `treasury_*`/`bank_*`. Si Compras hubiera empezado a registrar pagos en
el libro de caja canónico, esta prueba no lo habría visto.

Había además una segunda guardia, `test_no_purchase_writes_to_movimientos_caja`,
con la misma regla y peor estado: 5 de sus 6 raíces se habían borrado (4 eran
archivos, que el recorrido de entonces ni siquiera leía) y buscaba otra tabla
que tampoco existe ya. Sus dos nombres legacy —`movimientos_caja` y
`registrar_movimiento_manual`— se incorporan aquí, y sus dos raíces vivas
—`purchase_commands.py` y `purchase_planning_commands.py`— también.

La regla se aplica además en el dominio: `ImmediatePaymentPolicy.enforce_source`
rechaza `POS_CASH`/`POS_OPERATIVE_CASH`/`CAJA_POS`. Esta prueba vigila la otra
puerta: que el código de Compras no escriba Caja por su cuenta.
"""

from __future__ import annotations

import re
from pathlib import Path

from .architecture_guardrails import code_only_source_lines

REPO = Path(__file__).resolve().parents[2]
PROCUREMENT_ROOTS = [
    REPO / "backend" / "domain" / "procurement",
    REPO / "backend" / "application" / "procurement",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "procurement",
    REPO / "frontend" / "desktop" / "modules" / "purchasing",
    # Archivos sueltos: `backend/application/commands/` es un catálogo de todos
    # los contextos —incluye `cash_register_commands.py`, que sí es de Caja—, así
    # que no se puede tomar el directorio entero.
    REPO / "backend" / "application" / "commands" / "purchase_commands.py",
    REPO / "backend" / "application" / "commands" / "purchase_planning_commands.py",
]

#: Escrituras SQL sobre caja o tesorería, con nombres legacy y canónicos, más las
#: llamadas y tablas legacy. Texto crudo: el SQL vive dentro de cadenas.
_CASH_SQL = re.compile(
    r"(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM)\s+"
    r"(?:caja\b|movimientos_caja\b|tesoreria\w*|cash_\w+|treasury_\w+|bank_\w+|petty_cash\w*)"
    r"|registrar_egreso\s*\("
    r"|\bregistrar_movimiento_manual\b"
    r"|\bmovimientos_caja\b",
    re.IGNORECASE,
)

#: El API de escritura de Caja usado desde Compras. Son identificadores: se
#: buscan sólo en código, no en comentarios ni docstrings.
_CASH_API = re.compile(
    r"(?:from|import)\s+backend\.[\w.]*cash_register\b"
    r"|\bCashLedgerEntry\b|\bRegisterCashMovementUseCase\b|\bReverseCashMovementUseCase\b"
    r"|\bCashRegisterUnitOfWork\b|\buow\.ledger\b"
)


def _files_of(root: Path):
    """Acepta directorios Y archivos: el recorrido anterior sólo miraba
    directorios, y una raíz-archivo se habría saltado sin avisar."""
    if root.is_file():
        if root.suffix == ".py":
            yield root
    elif root.is_dir():
        for p in root.rglob("*.py"):
            if "__pycache__" not in p.parts:
                yield p


def test_procurement_does_not_write_cash_tables():
    vacias = [r.relative_to(REPO).as_posix() for r in PROCUREMENT_ROOTS
              if not any(True for _ in _files_of(r))]
    assert not vacias, (
        "Raíces de Compras que no aportan ningún archivo; la prueba pasaría sin "
        "leerlas:\n  " + "\n  ".join(vacias))

    offenders = []
    for root in PROCUREMENT_ROOTS:
        for path in _files_of(root):
            rel = path.relative_to(REPO).as_posix()
            for m in _CASH_SQL.finditer(path.read_text(encoding="utf-8")):
                offenders.append(f"{rel}: {m.group(0)!r}")
            for numero, linea in code_only_source_lines(path):
                for m in _CASH_API.finditer(linea):
                    offenders.append(f"{rel}:{numero}: {m.group(0)!r}")
    assert not offenders, (
        "Compras no escribe caja/tesorería directamente; emite "
        "SUPPLIER_PAYMENT_SCHEDULED hacia Tesorería:\n" + "\n".join(offenders))
