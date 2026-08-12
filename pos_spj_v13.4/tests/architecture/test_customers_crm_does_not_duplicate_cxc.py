"""CRM-1 (§40, "no crear un ledger financiero paralelo") — CxC lives in Finanzas.

CRM may only *read* an accounts-receivable summary (e.g.
``CustomerAccountsReceivableSummaryQuery``). It must never define its own
CxC/credit-movement table, and never write directly to
``cuentas_por_cobrar``/``movimientos_credito`` (those are Finanzas' tables —
see docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md §4/§11 on the two
existing parallel credit-history tables this guardrail exists to prevent a
third of).
"""

from __future__ import annotations

import re

from .customers_crm_guardrails import (
    ALL_CRM_CODE_ROOTS,
    crm_py_files,
    existing_crm_schema_files,
    relative,
)

_FORBIDDEN_WRITE = re.compile(
    r"(INSERT\s+INTO|UPDATE)\s+(cuentas_por_cobrar|movimientos_credito)\b",
    re.IGNORECASE,
)
_FORBIDDEN_TABLE_DEF = re.compile(
    r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?(cuentas_por_cobrar|movimientos_credito|customer_receivable|crm_receivable)\b",
    re.IGNORECASE,
)


def test_customers_crm_does_not_write_cxc_tables_directly():
    offenders = []
    for path in crm_py_files(ALL_CRM_CODE_ROOTS):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _FORBIDDEN_WRITE.search(line):
                offenders.append(f"{relative(path)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "CRM code writes directly to Finanzas' CxC tables — call the Finanzas "
        "commercial-obligation/receivable use case instead:\n" + "\n".join(offenders)
    )


def test_customers_crm_schema_does_not_define_a_parallel_cxc_table():
    offenders = []
    for schema_file in existing_crm_schema_files():
        for line in schema_file.read_text(encoding="utf-8").splitlines():
            if _FORBIDDEN_TABLE_DEF.search(line):
                offenders.append(f"{relative(schema_file)}: {line.strip()}")
    assert not offenders, (
        "A customers_crm schema file defines a CxC-shaped table — Finanzas "
        "owns receivables; CRM only projects a summary:\n" + "\n".join(offenders)
    )
