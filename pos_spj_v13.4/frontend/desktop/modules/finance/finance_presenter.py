"""FinancePresenter — la única puerta entre la UI de Finanzas y el backend.

Recibe YA construidos los query services y el ``FinanceCommandService``
(composición en ``finance_routes``). No toca SQL, conexiones ni el
contenedor; entrega a las páginas view models listos para mostrar.

Todo comando pasa por ``FinanceCommandService``: actor autenticado y permiso
``FINANZAS.<accion>`` (§28). Sin servicio de comandos, todo comando se rechaza.
Cada comando devuelve ``(ok, mensaje)``; los rechazos de negocio llegan con su
causa (excepciones del catálogo §34), nunca como un error genérico.
"""

from __future__ import annotations

import logging
from dataclasses import fields
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable

from backend.application.finance.permissions import FinancePermissions as P
from backend.domain.finance.enums import (
    AccountType,
    CapitalMovementKind,
    CashFlowCategory,
    FixedAssetStatus,
    JournalType,
    PaymentPriority,
    PurchaseDebitNature,
    TaxDirection,
    TaxKind,
    TreasuryAccountType,
    TreasuryMovementKind,
)
from backend.domain.finance.exceptions import FinanceDomainError
from frontend.desktop.modules.finance.finance_view_models import (
    AGING_ES,
    INSTRUMENT_ES,
    TREASURY_TYPE_ES,
    AlertViewModel,
    KpiViewModel,
    TableViewModel,
    account_type_es,
    money_display,
    status_es,
    yes_no,
)

logger = logging.getLogger("spj.finance.presenter")

Option = tuple[str, str]

#: Etiquetas de los parámetros editables (§24: nada configurable queda en código).
SETTING_LABELS = {
    "base_currency_code": "Moneda base",
    "rounding_account_id": "Cuenta de redondeo",
    "journal_review_required": "Asientos manuales requieren validación previa",
    "payment_dual_control": "Quien autoriza un pago no puede ejecutarlo",
    "payment_second_authorization_threshold": "Importe que exige segunda autorización de pago",
    "statement_importer_cannot_adjust": "Quien importa un estado no registra sus ajustes",
    "budget_warning_percent": "Porcentaje de consumo que dispara advertencia presupuestal",
    "reconciliation_amount_tolerance": "Tolerancia de importe al conciliar",
    "reconciliation_date_window_days": "Ventana de días para sugerir conciliaciones",
    "close_materiality_threshold": "Umbral de materialidad del cierre",
    "receivable_write_off_threshold": "Castigo de CxC: importe que exige autorización",
    "cash_projection_weeks": "Semanas de la proyección de flujo",
    "payroll_history_months": "Meses de historia para estimar nómina",
    "upcoming_payments_days": "Días para 'pagos próximos'",
    "dashboard_trend_months": "Meses de tendencia en el tablero",
}

DEBIT_NATURE_ES = {
    "INVENTORY": "Inventario",
    "OPERATING_EXPENSE": "Gasto operativo",
    "PREPAID_EXPENSE": "Gasto anticipado",
    "FIXED_ASSET": "Activo fijo",
    "OTHER_ASSET": "Otro activo",
}

PROFITABILITY_DIMENSIONS: list[Option] = [
    ("branch", "Sucursal"), ("product", "Producto"), ("category", "Categoría"),
    ("customer", "Cliente"), ("channel", "Canal"), ("order", "Pedido"), ("route", "Ruta"),
]


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _short(value: str | None) -> str:
    return (value or "")[-8:]


class FinancePresenter:
    def __init__(self, *, query_services: dict, commands=None,
                 statement_reader: Callable | None = None,
                 manual_statement_parser: Callable | None = None,
                 crm_summary: Callable[[str], object] | None = None,
                 embedded_presenters: dict | None = None,
                 today: Callable[[], date] = date.today) -> None:
        self._q = query_services
        self._commands = commands
        self._read_statement = statement_reader
        self._parse_manual = manual_statement_parser
        self._crm_summary = crm_summary
        self._embedded = embedded_presenters or {}
        self._today = today

    # ── submódulos compuestos (Proveedores vive dentro de Finanzas) ────────
    def embedded_presenter(self, name: str):
        value = self._embedded.get(name)
        if callable(value) and not hasattr(value, "ensure_loaded"):
            try:
                value = value()
            except Exception:
                logger.exception("No se pudo componer el submódulo %s", name)
                return None
            self._embedded[name] = value
        return value

    # ── comandos ─────────────────────────────────────────────────────────
    def _command(self, name: str, *args, done: str = "Operación registrada.",
                 **kwargs) -> tuple[bool, str]:
        if self._commands is None:
            return False, "Finanzas no tiene servicio de comandos autorizado; operación rechazada."
        try:
            result = getattr(self._commands, name)(*args, **kwargs)
        except FinanceDomainError as exc:
            return False, str(exc)
        except ValueError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("FinancePresenter: error inesperado en %s", name)
            return False, "Error inesperado; revise el log."
        return True, done(result) if callable(done) else done

    def can(self, permission: str) -> bool:
        """Para habilitar acciones en pantalla; la decisión real la vuelve a
        tomar el servicio de comandos."""
        return bool(self._commands is not None and self._commands.can(permission))

    def today(self) -> date:
        return self._today()

    def month_bounds(self) -> tuple[date, date]:
        today = self._today()
        return today.replace(day=1), today

    # ── opciones para selectores ─────────────────────────────────────────
    def postable_accounts(self, *types: str) -> list[Option]:
        return [(r["id"], f"{r['code']} — {r['name']}")
                for r in self._q["accounts"].postable_accounts(account_types=tuple(types))]

    def summary_accounts(self) -> list[Option]:
        return [(r["id"], f"{r['code']} — {r['name']}")
                for r in self._q["accounts"].summary_accounts()]

    def expense_accounts(self) -> list[Option]:
        return self.postable_accounts("EXPENSE", "OTHER_EXPENSE", "COST_OF_SALES")

    def treasury_accounts(self, *, money_only: bool = False) -> list[Option]:
        """Nombre, disponible y moneda visibles (F24)."""
        return [(row["id"], f"{row['name']} — disponible {money_display(row['available'])}"
                            f" {row['currency_code']}")
                for row in self._q["treasury"].treasury_position()
                if not money_only or row["account_type"] != TreasuryAccountType.DIGITAL_WALLET.value]

    def bank_accounts(self) -> list[Option]:
        return [(row["id"], row["name"]) for row in self._q["treasury"].treasury_position()
                if row["account_type"] == TreasuryAccountType.BANK.value]

    def customer_options(self, text: str) -> list[Option]:
        return [(r["id"], r["name"]) for r in self._q["receivables"].search_customers(text)]

    def supplier_options(self, text: str) -> list[Option]:
        return [(r["id"], r["name"]) for r in self._q["payables"].search_suppliers(text)]

    def journal_type_options(self) -> list[Option]:
        return [(r["journal_type"], r["name"]) for r in self._q["journal"].journals()]

    def dimension_options(self, kind: str) -> list[Option]:
        return [(r["id"], f"{r['code']} — {r['name']}")
                for r in self._q["settings"].dimensions().get(kind, [])]

    def asset_category_options(self) -> list[Option]:
        return [(r["id"], r["name"]) for r in self._q["assets"].categories()]

    def base_currency(self) -> str:
        return self._q["ledger"].base_currency()

    def currency_options(self) -> list[Option]:
        return [(r["code"], f"{r['code']} — {r['name']}")
                for r in self._q["settings"].currencies() if r["active"]]

    @staticmethod
    def enum_options(enum, labels: dict | None = None) -> list[Option]:
        labels = labels or {}
        return [(member.value, labels.get(member.value, member.value)) for member in enum]

    def account_type_options(self) -> list[Option]:
        return [(t.value, account_type_es(t.value)) for t in AccountType]

    def cash_flow_options(self) -> list[Option]:
        return self.enum_options(CashFlowCategory, {
            "NONE": "No aplica", "OPERATING": "Operación", "INVESTING": "Inversión",
            "FINANCING": "Financiamiento"})

    def treasury_type_options(self) -> list[Option]:
        return self.enum_options(TreasuryAccountType, TREASURY_TYPE_ES)

    def debit_nature_options(self) -> list[Option]:
        return self.enum_options(PurchaseDebitNature, DEBIT_NATURE_ES)

    def priority_options(self) -> list[Option]:
        return self.enum_options(PaymentPriority, {"CRITICAL": "Crítica", "HIGH": "Alta",
                                                   "NORMAL": "Normal", "LOW": "Baja"})

    def movement_kind_options(self) -> list[Option]:
        return self.enum_options(TreasuryMovementKind, {
            "DEPOSIT": "Depósito", "WITHDRAWAL": "Retiro", "BANK_CHARGE": "Comisión bancaria",
            "BANK_INTEREST": "Interés ganado"})

    def capital_kind_options(self) -> list[Option]:
        return self.enum_options(CapitalMovementKind, {
            "CONTRIBUTION": "Aportación de socios", "WITHDRAWAL": "Retiro de socios",
            "LOAN_RECEIVED": "Préstamo recibido", "LOAN_REPAYMENT": "Pago de préstamo"})

    def tax_kind_options(self) -> list[Option]:
        return self.enum_options(TaxKind, {"VAT": "IVA", "WITHHOLDING_VAT": "Retención de IVA",
                                           "WITHHOLDING_INCOME": "Retención de ISR",
                                           "EXCISE": "IEPS"})

    def tax_direction_options(self) -> list[Option]:
        return self.enum_options(TaxDirection, {"SALES": "Ventas (trasladado)",
                                                "PURCHASES": "Compras (acreditable/retenido)"})

    def open_loans(self) -> list[Option]:
        return [(r["id"], f"{r['lender_name']} — saldo {money_display(r['outstanding_principal'])}")
                for r in self._q["assets"].loans() if r["status"] == "ACTIVE"]

    # ── resumen (§29.2) ──────────────────────────────────────────────────
    def dashboard(self):
        """DTO del tablero: 12 KPIs, alertas y las 10 gráficas (ChartDataDTO)."""
        return self._q["dashboard"].dashboard(today=self._today())

    @staticmethod
    def kpis(dashboard) -> list[KpiViewModel]:
        return [KpiViewModel(k.label,
                             money_display(k.value) if k.is_money else k.value, k.variant)
                for k in dashboard.kpis]

    @staticmethod
    def alerts(dashboard) -> list[AlertViewModel]:
        return [AlertViewModel(a.label, a.count, a.severity, a.route) for a in dashboard.alerts]

    # ── plan de cuentas ──────────────────────────────────────────────────
    def chart_of_accounts(self, search: str = "") -> TableViewModel:
        needle = search.strip().lower()
        rows, ids = [], []
        for a in self._q["accounts"].chart_of_accounts():
            if needle and needle not in a["code"].lower() and needle not in a["name"].lower():
                continue
            indent = "    " * a["level"]
            rows.append([a["code"], f"{indent}{a['name']}", account_type_es(a["account_type"]),
                         "Acumulativa" if not a["posting_allowed"] else "Detalle",
                         yes_no(a["reconciliation_required"]), yes_no(a["has_movements"]),
                         "Activa" if a["active"] else "Inactiva"])
            ids.append(a["id"])
        return TableViewModel(rows, ids)

    def account(self, account_id: str) -> dict | None:
        return next((a for a in self._q["accounts"].chart_of_accounts()
                     if a["id"] == account_id), None)

    def create_account(self, **data) -> tuple[bool, str]:
        data["account_type"] = AccountType(data["account_type"])
        data["cash_flow_category"] = CashFlowCategory(data.get("cash_flow_category") or "NONE")
        return self._command("create_account", done="Cuenta creada.", **data)

    def update_account(self, account_id: str, **changes) -> tuple[bool, str]:
        if changes.get("account_type"):
            changes["account_type"] = AccountType(changes["account_type"])
        if changes.get("cash_flow_category"):
            changes["cash_flow_category"] = CashFlowCategory(changes["cash_flow_category"])
        return self._command("update_account", account_id, done="Cuenta actualizada.",
                             **changes)

    def set_account_active(self, account_id: str, active: bool,
                           reason: str) -> tuple[bool, str]:
        return self._command("update_account", account_id, active=active, reason=reason,
                             done="Cuenta activada." if active else "Cuenta desactivada.")

    # ── asientos ─────────────────────────────────────────────────────────
    def journal_entries(self, *, status: str | None = None, search: str = "",
                        date_from: date | None = None, date_to: date | None = None,
                        limit: int = 50, offset: int = 0) -> TableViewModel:
        query = self._q["journal"]
        filters = {"status": status, "search": search or None,
                   "date_from": _iso(date_from), "date_to": _iso(date_to)}
        rows, ids = [], []
        for e in query.list_entries(limit=limit, offset=offset, **filters):
            rows.append([e["entry_number"], e["posting_date"] or e["entry_date"],
                         e["description"], e["journal_name"], e["source_module"],
                         money_display(e["total"]), status_es(e["status"])])
            ids.append(e["id"])
        return TableViewModel(rows, ids, total=query.count_entries(**filters))

    def journal_entry(self, journal_entry_id: str) -> dict:
        header = self._q["journal"].entry_header(journal_entry_id) or {}
        lines = self._q["journal"].entry_lines(journal_entry_id)
        return {
            "header": header,
            "status": header.get("status", ""),
            "lines": TableViewModel(
                [[l["account_code"], l["account_name"], l["description"] or "",
                  _side(l["base_debit_amount"]), _side(l["base_credit_amount"]),
                  l["currency_code"], "Redondeo" if l["line_role"] == "ROUNDING" else ""]
                 for l in lines], [str(l["line_index"]) for l in lines]),
        }

    def create_journal_entry(self, **data) -> tuple[bool, str]:
        data["journal_type"] = JournalType(data.get("journal_type") or "GENERAL")
        return self._command("create_journal_entry", **data,
                             done=lambda e: f"Asiento {e.entry_number} guardado en borrador.")

    def validate_journal_entry(self, journal_entry_id: str) -> tuple[bool, str]:
        return self._command("validate_journal_entry", journal_entry_id,
                             done="Asiento validado; listo para contabilizar.")

    def post_journal_entry(self, journal_entry_id: str) -> tuple[bool, str]:
        return self._command("post_journal_entry", journal_entry_id,
                             done=lambda e: f"Asiento {e.entry_number} contabilizado.")

    def cancel_journal_entry(self, journal_entry_id: str, reason: str) -> tuple[bool, str]:
        return self._command("cancel_journal_entry", journal_entry_id, reason=reason,
                             done="Borrador cancelado.")

    def reverse_entry(self, journal_entry_id: str, reason: str) -> tuple[bool, str]:
        return self._command("reverse_entry", journal_entry_id, reason=reason,
                             done=lambda e: f"Asiento de reversión {e.entry_number} contabilizado.")

    # ── libro mayor / auxiliar / balanza ─────────────────────────────────
    def account_auxiliary(self, account_id: str, date_from: date, date_to: date) -> dict:
        data = self._q["ledger"].account_auxiliary(account_id, date_from=date_from.isoformat(),
                                                   date_to=date_to.isoformat())
        rows = [[l["entry_date"], l["entry_number"], l["description"] or l["entry_description"],
                 money_display(l["debit_amount"]), money_display(l["credit_amount"]),
                 money_display(l["running_balance"])] for l in data.get("lines", [])]
        return {"table": TableViewModel(rows, [l["journal_entry_id"] for l in data.get("lines", [])]),
                "opening": money_display(data.get("opening_balance", "0")),
                "closing": money_display(data.get("closing_balance", "0"))}

    def trial_balance(self, date_from: date, date_to: date) -> dict:
        data = self._q["trial_balance"].trial_balance(date_from=date_from.isoformat(),
                                                      date_to=date_to.isoformat())
        rows = [[r.account_code, r.account_name, account_type_es(r.account_type),
                 money_display(r.debit_total), money_display(r.credit_total),
                 money_display(r.balance)] for r in data["rows"]]
        return {"table": TableViewModel(rows, [r.account_id for r in data["rows"]]),
                "debits": money_display(data["total_debits"]),
                "credits": money_display(data["total_credits"])}

    # ── periodos y cierre ────────────────────────────────────────────────
    def fiscal_periods(self) -> TableViewModel:
        rows, ids = [], []
        for p in self._q["periods"].fiscal_periods():
            rows.append([f"{p['year']:04d}-{p['month']:02d}", status_es(p["status"]),
                         p["soft_closed_at"] or "", p["closed_at"] or "",
                         p["reopened_at"] or "", p["reopen_reason"] or ""])
            ids.append(f"{p['year']:04d}-{p['month']:02d}")
        return TableViewModel(rows, ids)

    def close_checklist(self, year: int, month: int) -> tuple[bool, TableViewModel | str]:
        if self._commands is None:
            return False, "Finanzas no tiene servicio de comandos autorizado."
        try:
            items = self._commands.close_checklist(year, month)
        except FinanceDomainError as exc:
            return False, str(exc)
        return True, TableViewModel(
            [[i.label, status_es(i.status), i.detail] for i in items], [i.key for i in items])

    def close_exceptions(self) -> TableViewModel:
        rows, ids = [], []
        for e in self._q["periods"].open_close_exceptions():
            rows.append([e["period_code"], e["check_type"], e["subject"],
                         money_display(e["expected_amount"]), money_display(e["actual_amount"]),
                         money_display(e["difference"])])
            ids.append(e["id"])
        return TableViewModel(rows, ids)

    def open_period(self, year: int, month: int) -> tuple[bool, str]:
        return self._command("open_period", year, month, done="Periodo abierto.")

    def close_period(self, year: int, month: int, *, soft: bool) -> tuple[bool, str]:
        return self._command("close_period", year, month, soft=soft,
                             done="Pre-cierre aplicado." if soft else "Periodo cerrado.")

    def reopen_period(self, year: int, month: int, reason: str) -> tuple[bool, str]:
        return self._command("reopen_period", year, month, reason=reason,
                             done="Periodo reabierto (queda en la auditoría).")

    def authorize_close_exception(self, exception_id: str, reason: str) -> tuple[bool, str]:
        return self._command("authorize_close_exception", exception_id, reason=reason,
                             done="Diferencia autorizada.")

    # ── cuentas por cobrar ───────────────────────────────────────────────
    def open_receivables(self, *, customer_id: str | None = None,
                         search: str = "") -> TableViewModel:
        rows, ids = [], []
        for r in self._q["receivables"].open_receivables(customer_id=customer_id,
                                                         search=search or None):
            rows.append([r["document_number"], r.get("customer_name") or _short(r["customer_id"]),
                         r["issue_date"], r["due_date"] or "Sin vencimiento",
                         money_display(r["original_amount"]),
                         money_display(r["outstanding_amount"]), status_es(r["status"])])
            ids.append(r["id"])
        return TableViewModel(rows, ids)

    def receivable_customer(self, receivable_id: str) -> tuple[str, str] | None:
        """``(customer_id, nombre visible)`` del documento elegido."""
        for r in self._q["receivables"].open_receivables():
            if r["id"] == receivable_id:
                return r["customer_id"], r.get("customer_name") or _short(r["customer_id"])
        return None

    def open_receivables_of(self, customer_id: str) -> list[dict]:
        return [{"id": r["id"], "label": f"{r['document_number']} — saldo "
                                          f"{money_display(r['outstanding_amount'])}",
                 "outstanding": r["outstanding_amount"]}
                for r in self._q["receivables"].open_receivables(customer_id=customer_id)]

    def receivable_aging(self) -> TableViewModel:
        rows = [[AGING_ES.get(r["bucket"], r["bucket"]), str(r["documents"]),
                 money_display(r["amount"])]
                for r in self._q["receivables"].aging_summary(self._today().isoformat())]
        return TableViewModel(rows, [])

    def collection_history(self, *, search: str = "", limit: int = 200,
                           offset: int = 0) -> TableViewModel:
        rows, ids = [], []
        for c in self._q["receivables"].collection_history(search=search or None, limit=limit,
                                                           offset=offset):
            rows.append([c["collection_date"], c["reference"] or "",
                         c.get("customer_name") or _short(c["customer_id"]),
                         money_display(c["amount"]), money_display(c["applied_amount"]),
                         money_display(c["unapplied"]), c["treasury_account_name"] or "",
                         c["entry_number"] or "", status_es(c["status"])])
            ids.append(c["id"])
        return TableViewModel(rows, ids)

    def customer_credit_balances(self) -> TableViewModel:
        rows, ids = [], []
        for c in self._q["receivables"].customer_credit_balances():
            rows.append([c["collection_date"], c["reference"] or "",
                         c.get("customer_name") or _short(c["customer_id"]),
                         money_display(c["amount"]), money_display(c["available"])])
            ids.append(c["id"])
        return TableViewModel(rows, ids)

    def credit_balance(self, collection_id: str) -> dict | None:
        """Saldo a favor elegido: cliente, nombre y disponible."""
        for c in self._q["receivables"].customer_credit_balances():
            if c["id"] == collection_id:
                return {"customer_id": c["customer_id"],
                        "customer_name": c.get("customer_name") or _short(c["customer_id"]),
                        "available": c["available"]}
        return None

    def crm_receivable_summary(self, customer_id: str) -> dict | None:
        """Resumen de exposición de crédito que publica Clientes (CRM-21)."""
        if self._crm_summary is None:
            return None
        try:
            summary = self._crm_summary(str(customer_id))
        except Exception:
            logger.exception("Resumen de crédito no disponible para %s", customer_id)
            return None
        if summary is None:
            return None
        return {"customer_id": summary.customer_id,
                "current_exposure": money_display(summary.current_exposure),
                "overdue_amount": money_display(summary.overdue_amount),
                "next_due_date": summary.next_due_date,
                "receivable_status": summary.receivable_status}

    def create_receivable(self, **data) -> tuple[bool, str]:
        return self._command("create_receivable", **data, done="CxC registrada.")

    def register_collection(self, **data) -> tuple[bool, str]:
        def done(collection):
            unapplied = Decimal(collection.amount.to_string()) - Decimal(
                collection.applied_amount.to_string())
            suffix = (f" Queda saldo a favor por {money_display(unapplied)}."
                      if unapplied > 0 else "")
            return f"Cobro registrado.{suffix}"
        return self._command("register_collection", **data, done=done)

    def apply_collection(self, collection_id: str, applications: list[dict]) -> tuple[bool, str]:
        return self._command("apply_collection", collection_id=collection_id,
                             applications=applications, done="Saldo a favor aplicado.")

    def write_off_receivable(self, receivable_id: str, reason: str) -> tuple[bool, str]:
        return self._command("write_off_receivable", receivable_id, reason=reason,
                             done="CxC castigada con su asiento.")

    def dispute_receivable(self, receivable_id: str, reason: str) -> tuple[bool, str]:
        return self._command("dispute_receivable", receivable_id, reason=reason,
                             done="CxC en disputa.")

    def resolve_receivable_dispute(self, receivable_id: str,
                                   resolution: str) -> tuple[bool, str]:
        return self._command("resolve_receivable_dispute", receivable_id,
                             resolution=resolution, done="Disputa resuelta.")

    def register_payment_promise(self, receivable_id: str, **data) -> tuple[bool, str]:
        return self._command("register_payment_promise", receivable_id, **data,
                             done="Promesa de pago registrada.")

    def payment_promises(self, receivable_id: str) -> TableViewModel:
        rows = [[p["promised_date"], money_display(p["promised_amount"]), p["note"] or "",
                 status_es(p["status"])]
                for p in self._q["receivables"].payment_promises(receivable_id)]
        return TableViewModel(rows, [])

    def mark_overdue_documents(self) -> tuple[bool, str]:
        return self._command("mark_overdue_documents",
                             done=lambda r: f"Vencidos: {r.receivables} CxC y {r.payables} CxP.")

    # ── cuentas por pagar y pagos ────────────────────────────────────────
    def open_payables(self, *, search: str = "", blocked_only: bool = False) -> TableViewModel:
        rows, ids = [], []
        for p in self._q["payables"].open_payables(search=search or None,
                                                   blocked_only=blocked_only):
            state = status_es(p["status"])
            if p["blocked"]:
                state = f"{state} · Bloqueada"
            rows.append([p["document_number"], p.get("supplier_name") or _short(p["supplier_id"]),
                         p["issue_date"], p["due_date"] or "Sin vencimiento",
                         status_es(p["priority"]) if p["priority"] else "",
                         money_display(p["original_amount"]),
                         money_display(p["outstanding_amount"]), state])
            ids.append(p["id"])
        return TableViewModel(rows, ids)

    def payable_summary(self, payable_id: str) -> dict | None:
        return next((p for p in self._q["payables"].open_payables()
                     if p["id"] == payable_id), None)

    def payable_aging(self) -> TableViewModel:
        rows = [[AGING_ES.get(r["bucket"], r["bucket"]), str(r["documents"]),
                 money_display(r["amount"])]
                for r in self._q["payables"].aging(self._today().isoformat())]
        return TableViewModel(rows, [])

    def supplier_payments(self, *, status: str | None = None) -> TableViewModel:
        rows, ids = [], []
        for p in self._q["payables"].payments(status=status):
            stage = status_es(p["status"])
            if p["awaiting_second_authorization"]:
                stage = f"{stage} · Falta 2ª autorización"
            rows.append([p["document_number"], p.get("supplier_name") or _short(p["supplier_id"]),
                         p["scheduled_date"], money_display(p["amount"]),
                         p["treasury_account_name"] or "", stage,
                         _short(p["authorized_by"]), p["execution_reference"] or ""])
            ids.append(p["id"])
        return TableViewModel(rows, ids)

    def payment_status(self, payment_id: str) -> str:
        return next((p["status"] for p in self._q["payables"].payments()
                     if p["id"] == payment_id), "")

    def upcoming_payments(self) -> TableViewModel:
        days = self._q["settings"].settings().upcoming_payments_days
        rows, ids = [], []
        for p in self._q["payables"].upcoming_payments(as_of=self._today().isoformat(),
                                                       days=days):
            rows.append([p["due_date"], p["document_number"],
                         p.get("supplier_name") or _short(p["supplier_id"]),
                         money_display(p["outstanding_amount"]), status_es(p["status"])])
            ids.append(p["id"])
        return TableViewModel(rows, ids)

    def supplier_advances(self) -> TableViewModel:
        rows, ids = [], []
        for a in self._q["payables"].supplier_advances():
            rows.append([a["advance_date"], a.get("supplier_name") or _short(a["supplier_id"]),
                         a["reference"] or "", money_display(a["amount"]),
                         money_display(a["available"]), status_es(a["status"])])
            ids.append(a["id"])
        return TableViewModel(rows, ids)

    def advances_of(self, supplier_id: str) -> list[Option]:
        return [(a["id"], f"{a['advance_date']} — disponible {money_display(a['available'])}")
                for a in self._q["payables"].supplier_advances(supplier_id=supplier_id)]

    def create_payable(self, **data) -> tuple[bool, str]:
        data["debit_nature"] = PurchaseDebitNature(data["debit_nature"])
        if data.get("priority"):
            data["priority"] = PaymentPriority(data["priority"])
        return self._command("create_payable", **data, done="CxP registrada.")

    def schedule_supplier_payment(self, **data) -> tuple[bool, str]:
        def done(payment):
            if payment.second_authorization_required:
                return "Pago programado; por su importe requiere dos autorizaciones."
            return "Pago programado; falta autorizarlo."
        return self._command("schedule_payment", **data, done=done)

    def authorize_supplier_payment(self, payment_id: str) -> tuple[bool, str]:
        def done(payment):
            if payment.status.value == "AUTHORIZED":
                return "Pago autorizado; listo para ejecutar."
            return "Primera autorización registrada; falta la segunda."
        return self._command("authorize_payment", payment_id, done=done)

    def execute_supplier_payment(self, payment_id: str,
                                 execution_reference: str) -> tuple[bool, str]:
        return self._command("execute_payment", payment_id,
                             execution_reference=execution_reference,
                             done="Pago ejecutado y contabilizado.")

    def cancel_supplier_payment(self, payment_id: str, reason: str) -> tuple[bool, str]:
        return self._command("cancel_payment", payment_id, reason=reason,
                             done="Pago cancelado; la CxP vuelve a quedar abierta.")

    def block_payable(self, payable_id: str, reason: str) -> tuple[bool, str]:
        return self._command("block_payable", payable_id, reason=reason, done="CxP bloqueada.")

    def unblock_payable(self, payable_id: str, reason: str) -> tuple[bool, str]:
        return self._command("unblock_payable", payable_id, reason=reason,
                             done="CxP desbloqueada.")

    def dispute_payable(self, payable_id: str, reason: str) -> tuple[bool, str]:
        return self._command("dispute_payable", payable_id, reason=reason,
                             done="CxP en disputa.")

    def resolve_payable_dispute(self, payable_id: str, resolution: str) -> tuple[bool, str]:
        return self._command("resolve_payable_dispute", payable_id, resolution=resolution,
                             done="Disputa resuelta.")

    def register_supplier_advance(self, **data) -> tuple[bool, str]:
        return self._command("register_supplier_advance", **data,
                             done="Anticipo a proveedor registrado.")

    def apply_supplier_advance(self, **data) -> tuple[bool, str]:
        return self._command("apply_supplier_advance", **data, done="Anticipo aplicado.")

    # ── tesorería ────────────────────────────────────────────────────────
    def treasury_position(self) -> TableViewModel:
        rows, ids = [], []
        for a in self._q["treasury"].treasury_position():
            balance = money_display(a["balance"])
            if a["shared_mirror"]:
                balance = f"{balance} (espejo compartido)"
            rows.append([a["name"], TREASURY_TYPE_ES.get(a["account_type"], a["account_type"]),
                         a["masked_account_number"] or "", a["currency_code"], balance,
                         money_display(a["committed"]), money_display(a["available"]),
                         money_display(a["reconciled_balance"]) if a["reconciled_balance"] else "",
                         a["reconciled_as_of"] or ""])
            ids.append(a["id"])
        return TableViewModel(rows, ids)

    def treasury_totals(self) -> list[KpiViewModel]:
        totals = self._q["treasury"].treasury_total()
        available = self._q["treasury"].available_total()
        kpis = [KpiViewModel(f"Saldo {c}", money_display(v)) for c, v in totals.items()]
        kpis += [KpiViewModel(f"Disponible {c}", money_display(v), "success")
                 for c, v in available.items()]
        return kpis

    def treasury_movements(self) -> TableViewModel:
        rows, ids = [], []
        for m in self._q["treasury"].movements():
            rows.append([m["movement_date"], m["treasury_account_name"],
                         dict(self.movement_kind_options()).get(m["kind"], m["kind"]),
                         money_display(m["amount"]), m["reference"] or "",
                         f"{m['counterpart_code']} — {m['counterpart_name']}",
                         m["entry_number"] or ""])
            ids.append(m["id"])
        return TableViewModel(rows, ids)

    def register_treasury_transfer(self, *, source_id: str, target_id: str, amount: str,
                                   reference: str = "") -> tuple[bool, str]:
        return self._command("treasury_transfer", source_id=source_id, target_id=target_id,
                             amount=amount, reference=reference,
                             done="Transferencia registrada y contabilizada.")

    def register_treasury_movement(self, **data) -> tuple[bool, str]:
        data["kind"] = TreasuryMovementKind(data["kind"])
        return self._command("treasury_movement", **data, done="Movimiento registrado.")

    def create_treasury_account(self, **data) -> tuple[bool, str]:
        data["account_type"] = TreasuryAccountType(data["account_type"])
        return self._command("create_treasury_account", **data,
                             done="Cuenta de tesorería creada.")

    def update_treasury_account(self, treasury_account_id: str, **changes) -> tuple[bool, str]:
        return self._command("update_treasury_account", treasury_account_id, **changes,
                             done="Cuenta de tesorería actualizada.")

    # ── conciliación ─────────────────────────────────────────────────────
    def reconciliations(self) -> TableViewModel:
        rows, ids = [], []
        for r in self._q["reconciliation"].list_reconciliations():
            rows.append([r["treasury_account_name"], r["statement_date"],
                         status_es(r["status"]), str(r["pending_lines"]),
                         _short(r["completed_by"]), r["completed_at"] or "",
                         r["difference_reason"] or r["revert_reason"] or ""])
            ids.append(r["id"])
        return TableViewModel(rows, ids)

    def reconciliation_status(self, reconciliation_id: str) -> str:
        return next((r["status"] for r in self._q["reconciliation"].list_reconciliations()
                     if r["id"] == reconciliation_id), "")

    def pending_statements(self) -> list[Option]:
        return [(s["id"], f"{s['treasury_account_name']} — {s['statement_date']}")
                for s in self._q["reconciliation"].statements_without_reconciliation()]

    def read_statement_file(self, path: str) -> tuple[bool, dict | str]:
        """CSV/XLSX → partidas listas para revisar antes de importar (§15)."""
        if self._read_statement is None:
            return False, "La lectura de archivos de estado de cuenta no está disponible."
        try:
            return True, self._read_statement(path)
        except (ValueError, FinanceDomainError, OSError) as exc:
            return False, str(exc)

    def parse_manual_statement(self, text: str) -> tuple[bool, list[dict] | str]:
        if self._parse_manual is None:
            return False, "La captura manual de estados no está disponible."
        try:
            return True, self._parse_manual(text)
        except (ValueError, FinanceDomainError) as exc:
            return False, str(exc)

    def import_bank_statement(self, **data) -> tuple[bool, str]:
        return self._command("import_statement", **data,
                             done=lambda s: f"Estado importado con {len(s.lines)} partidas.")

    def start_reconciliation(self, bank_statement_id: str) -> tuple[bool, str]:
        return self._command("start_reconciliation", bank_statement_id,
                             done="Conciliación iniciada.")

    def suggest_matches(self, reconciliation_id: str) -> tuple[bool, str]:
        return self._command("suggest_matches", reconciliation_id,
                             done=lambda n: f"Sugerencias encontradas: {n}.")

    def reconciliation_candidates(self, reconciliation_id: str) -> dict:
        """``{"statement": TableViewModel, "ledger": TableViewModel}`` lado a lado."""
        empty = {"statement": TableViewModel([], []), "ledger": TableViewModel([], [])}
        if self._commands is None:
            return empty
        try:
            data = self._commands.reconciliation_candidates(reconciliation_id)
        except FinanceDomainError:
            return empty
        statement = TableViewModel(
            [[l["transaction_date"], l["description"], money_display(l["amount"]),
              l["external_reference"], status_es(l["status"])]
             for l in data["statement_lines"]],
            [l["id"] for l in data["statement_lines"]])
        ledger = TableViewModel(
            [[l["entry_date"], l["entry_number"], l["description"] or "",
              money_display(l["debit_amount"]), money_display(l["credit_amount"])]
             for l in data["ledger_lines"]],
            [l["journal_line_id"] for l in data["ledger_lines"]])
        return {"statement": statement, "ledger": ledger,
                "suggested": {l["id"]: l["suggested_journal_line_id"]
                              for l in data["statement_lines"]
                              if l["suggested_journal_line_id"]}}

    def match_reconciliation(self, **data) -> tuple[bool, str]:
        def done(exact):
            return ("Partida conciliada." if exact else
                    "Partida conciliada con diferencia dentro de tolerancia.")
        return self._command("match", **data, done=done)

    def ignore_statement_line(self, **data) -> tuple[bool, str]:
        return self._command("ignore_statement_line", **data, done="Partida ignorada.")

    def reconciliation_adjustment(self, **data) -> tuple[bool, str]:
        if data.get("kind"):
            data["kind"] = TreasuryMovementKind(data["kind"])
        return self._command("reconciliation_adjustment", **data,
                             done="Ajuste de conciliación contabilizado.")

    def complete_reconciliation(self, reconciliation_id: str,
                                difference_reason: str = "") -> tuple[bool, str]:
        return self._command("complete_reconciliation", reconciliation_id,
                             difference_reason=difference_reason or None,
                             done="Conciliación completada.")

    def revert_reconciliation(self, reconciliation_id: str, reason: str) -> tuple[bool, str]:
        return self._command("revert_reconciliation", reconciliation_id, reason=reason,
                             done="Conciliación revertida; las partidas quedan libres.")

    # ── presupuestos ─────────────────────────────────────────────────────
    def budgets(self) -> TableViewModel:
        rows, ids = [], []
        for b in self._q["budgets"].list_budgets():
            rows.append([b["name"], str(b["fiscal_year"]), f"v{b['version']}",
                         "Bloqueante" if b["blocking"] else "Informativo",
                         status_es(b["status"]), _short(b["approved_by"]),
                         b["rejection_reason"] or ""])
            ids.append(b["id"])
        return TableViewModel(rows, ids)

    def budget_execution(self, fiscal_year: int,
                         budget_id: str | None = None) -> TableViewModel:
        rows, ids = [], []
        for r in self._q["budgets"].budget_execution(fiscal_year, budget_id=budget_id):
            rows.append([r["period_code"], f"{r['account_code']} — {r['account_name']}",
                         money_display(r["planned_amount"]), money_display(r["committed_amount"]),
                         money_display(r["accrued_amount"]), money_display(r["paid_amount"]),
                         money_display(r["available"]),
                         f"{r['consumed_percent']} %" if r["consumed_percent"] else "",
                         status_es(r["control_level"])])
            ids.append(r["line_id"])
        return TableViewModel(rows, ids)

    def create_budget(self, **data) -> tuple[bool, str]:
        return self._command("create_budget", **data, done="Presupuesto creado en borrador.")

    def create_budget_version(self, budget_id: str) -> tuple[bool, str]:
        return self._command("create_budget_version", budget_id,
                             done=lambda b: f"Versión {b.version} creada en borrador.")

    def budget_action(self, budget_id: str, action: str, reason: str = "") -> tuple[bool, str]:
        labels = {"submit": "Presupuesto enviado a aprobación.",
                  "approve": "Presupuesto aprobado.", "reject": "Presupuesto rechazado.",
                  "activate": "Presupuesto activo.", "close": "Presupuesto cerrado.",
                  "cancel": "Presupuesto cancelado."}
        return self._command("budget_action", budget_id, action, reason=reason,
                             done=labels.get(action, "Hecho."))

    # ── gastos ───────────────────────────────────────────────────────────
    def expense_requests(self, *, status: str | None = None) -> TableViewModel:
        rows, ids = [], []
        for e in self._q["budgets"].expense_requests(status=status):
            rows.append([e["created_at"][:10], f"{e['account_code']} — {e['account_name']}",
                         e["category"] or "", e["description"] or "",
                         money_display(e["amount"]), money_display(e["accrued_amount"]),
                         money_display(e["settled_amount"]),
                         f"{e['approvals']}/{e['required_approvals']}", status_es(e["status"])])
            ids.append(e["id"])
        return TableViewModel(rows, ids)

    def expense_status(self, expense_request_id: str) -> str:
        return next((e["status"] for e in self._q["budgets"].expense_requests()
                     if e["id"] == expense_request_id), "")

    def approval_rules(self) -> TableViewModel:
        rows, ids = [], []
        for r in self._q["budgets"].approval_rules():
            rows.append([r["name"], money_display(r["min_amount"]), r["category"] or "Todas",
                         str(r["required_approvals"]), str(r["priority"])])
            ids.append(r["id"])
        return TableViewModel(rows, ids)

    def register_expense_request(self, **data) -> tuple[bool, str]:
        return self._command("expense_request", **data,
                             done="Solicitud registrada; falta aprobarla.")

    def approve_expense(self, expense_request_id: str, *, reason: str = "",
                        authorize_excess: bool = False) -> tuple[bool, str]:
        def done(fully):
            return ("Gasto aprobado y comprometido en el presupuesto." if fully else
                    "Aprobación registrada; faltan aprobaciones.")
        return self._command("approve_expense", expense_request_id, reason=reason,
                             authorize_excess=authorize_excess, done=done)

    def reject_expense(self, expense_request_id: str, reason: str) -> tuple[bool, str]:
        return self._command("reject_expense", expense_request_id, reason=reason,
                             done="Solicitud rechazada.")

    def accrue_expense(self, expense_request_id: str, **data) -> tuple[bool, str]:
        return self._command("accrue_expense", expense_request_id, **data,
                             done="Gasto devengado y contabilizado.")

    def cancel_expense(self, expense_request_id: str, reason: str) -> tuple[bool, str]:
        return self._command("cancel_expense", expense_request_id, reason=reason,
                             done="Solicitud cancelada; el compromiso se liberó.")

    def create_expense_rule(self, **rule) -> tuple[bool, str]:
        return self._command("create_expense_rule", **rule, done="Regla de aprobación creada.")

    # ── capital, préstamos y CAPEX ───────────────────────────────────────
    def capital_transactions(self) -> TableViewModel:
        labels = dict(self.capital_kind_options())
        rows, ids = [], []
        for c in self._q["assets"].capital_transactions():
            rows.append([c["transaction_date"], labels.get(c["kind"], c["kind"]),
                         c["counterparty"] or "", money_display(c["amount"]),
                         money_display(c["interest_amount"]) if c["interest_amount"] else "",
                         c["treasury_account_name"], c["entry_number"] or ""])
            ids.append(c["id"])
        return TableViewModel(rows, ids)

    def loans(self) -> TableViewModel:
        rows, ids = [], []
        for l in self._q["assets"].loans():
            rows.append([l["lender_name"], money_display(l["principal_amount"]),
                         money_display(l["outstanding_principal"]), l["start_date"],
                         l["maturity_date"] or "", status_es(l["status"])])
            ids.append(l["id"])
        return TableViewModel(rows, ids)

    def capex_by_project(self) -> TableViewModel:
        rows = [[p["code"], p["name"], money_display(p["capex"])]
                for p in self._q["assets"].capex_by_project()]
        return TableViewModel(rows, [])

    def register_capital_movement(self, **data) -> tuple[bool, str]:
        data["kind"] = CapitalMovementKind(data["kind"])
        return self._command("capital_movement", **data, done="Movimiento de capital registrado.")

    def register_capital_contribution(self, *, amount: str, treasury_account_id: str,
                                      contributor: str = "") -> tuple[bool, str]:
        return self._command("capital_contribution", amount=amount,
                             treasury_account_id=treasury_account_id, contributor=contributor,
                             done="Aportación registrada.")

    def cash_projection(self) -> dict:
        settings = self._q["settings"].settings()
        data = self._q["projection"].projection(as_of=self._today().isoformat(),
                                                weeks=settings.cash_projection_weeks,
                                                payroll_months=settings.payroll_history_months)
        rows = [[w["week_start"], money_display(w["inflows"]), money_display(w["outflows"]),
                 money_display(w["net"]), money_display(w["closing_balance"])]
                for w in data["weeks"]]
        return {"table": TableViewModel(rows, []),
                "opening": money_display(data["opening_balance"]),
                "payroll": money_display(data["estimated_monthly_payroll"])}

    # ── activos fijos ────────────────────────────────────────────────────
    def fixed_assets(self, *, status: str | None = None) -> TableViewModel:
        rows, ids = [], []
        for a in self._q["assets"].list_assets(status=status):
            rows.append([a["asset_code"] or "", a["name"], a["category_name"] or "",
                         a["capitalization_date"] or "", money_display(a["acquisition_cost"]),
                         money_display(a["accumulated_depreciation"]),
                         money_display(a["net_book_value"]), status_es(a["status"]),
                         a["last_depreciated_period"] or ""])
            ids.append(a["id"])
        return TableViewModel(rows, ids)

    def asset_status(self, asset_id: str) -> str:
        return next((a["status"] for a in self._q["assets"].list_assets()
                     if a["id"] == asset_id), "")

    def depreciation_runs(self) -> TableViewModel:
        rows, ids = [], []
        for r in self._q["assets"].depreciation_runs():
            rows.append([r["period_code"], str(r["asset_count"]), money_display(r["total_amount"]),
                         _short(r["run_by"]), r["run_at"]])
            ids.append(r["id"])
        return TableViewModel(rows, ids)

    def capitalize_asset(self, **data) -> tuple[bool, str]:
        return self._command("capitalize_asset", **data,
                             done=lambda a: f"Activo {a.name} capitalizado.")

    def run_depreciation(self, year: int, month: int) -> tuple[bool, str]:
        return self._command("run_depreciation", year, month,
                             done=lambda ids: f"Depreciación contabilizada ({len(ids)} asientos).")

    def dispose_asset(self, asset_id: str, *, outcome: str, reason: str,
                      proceeds: str | None = None,
                      treasury_account_id: str | None = None) -> tuple[bool, str]:
        return self._command("dispose_asset", asset_id, outcome=FixedAssetStatus(outcome),
                             reason=reason, proceeds=proceeds,
                             treasury_account_id=treasury_account_id,
                             done="Baja del activo contabilizada.")

    def suspend_asset(self, asset_id: str, reason: str) -> tuple[bool, str]:
        return self._command("suspend_asset", asset_id, reason=reason,
                             done="Activo suspendido; no se deprecia mientras tanto.")

    def resume_asset(self, asset_id: str) -> tuple[bool, str]:
        return self._command("resume_asset", asset_id, done="Activo reactivado.")

    # ── instrumentos comerciales ─────────────────────────────────────────
    def commercial_obligations(self) -> TableViewModel:
        rows, ids = [], []
        for o in self._q["obligations"].open_obligations():
            rows.append([INSTRUMENT_ES.get(o["instrument_type"], o["instrument_type"]),
                         _short(o["source_instrument_id"]), money_display(o["recognized_amount"]),
                         money_display(o["redeemed_amount"]), money_display(o["outstanding"]),
                         status_es(o["status"]), o["expires_at"] or ""])
            ids.append(o["id"])
        return TableViewModel(rows, ids)

    def instrument_summary(self) -> TableViewModel:
        rows = [[INSTRUMENT_ES.get(r["instrument_type"], r["instrument_type"]),
                 str(r["instruments"]), money_display(r["recognized"]),
                 money_display(r["redeemed"]), money_display(r["released"]),
                 money_display(r["outstanding"])]
                for r in self._q["obligations"].summary_by_instrument()]
        return TableViewModel(rows, [])

    def integration_exceptions(self) -> TableViewModel:
        rows = [[r["event_name"], _short(r["event_id"]), r["processed_at"]]
                for r in self._q["obligations"].events_without_entry()]
        return TableViewModel(rows, [])

    # ── estados financieros y análisis ───────────────────────────────────
    def statements(self, date_from: date, date_to: date) -> dict:
        q = self._q["statements"]
        start, end = date_from.isoformat(), date_to.isoformat()
        return {
            "income": q.income_statement(date_from=start, date_to=end),
            "balance": q.balance_sheet(as_of=end),
            "cash_flow": q.cash_flow_statement(date_from=start, date_to=end),
            "equity": q.equity_changes(
                opening_to=date.fromordinal(date_from.toordinal() - 1).isoformat(),
                closing_to=end),
        }

    @staticmethod
    def statement_table(statement: dict, lines: list[tuple[str, str]]) -> TableViewModel:
        return TableViewModel([[label, money_display(statement.get(key, ""))]
                               for key, label in lines], [])

    @staticmethod
    def statement_detail(statement: dict) -> TableViewModel:
        rows = []
        for section in statement.get("sections", []):
            rows.append([account_type_es(section["account_type"]), "",
                         money_display(section["total"])])
            for r in section["rows"]:
                rows.append([f"    {r['code']}", r["name"], money_display(r["balance"])])
        return TableViewModel(rows, [])

    def comparative_income(self, date_from: date, date_to: date) -> TableViewModel:
        length = (date_to - date_from).days + 1
        previous_to = date_from.toordinal() - 1
        prev_end = date.fromordinal(previous_to)
        prev_start = date.fromordinal(previous_to - length + 1)
        data = self._q["statements"].comparative_income_statement(
            current_from=date_from.isoformat(), current_to=date_to.isoformat(),
            previous_from=prev_start.isoformat(), previous_to=prev_end.isoformat())
        rows = [[line["key"], money_display(line["current"]), money_display(line["previous"]),
                 money_display(line["change"]),
                 f"{line['change_percent']} %" if line["change_percent"] else ""]
                for line in data["lines"]]
        return TableViewModel(rows, [])

    @staticmethod
    def profitability_dimensions() -> list[Option]:
        return list(PROFITABILITY_DIMENSIONS)

    def profitability(self, dimension: str, date_from: date, date_to: date) -> TableViewModel:
        rows = []
        for r in self._q["profitability"].by_dimension(dimension, date_from=date_from.isoformat(),
                                                       date_to=date_to.isoformat()):
            rows.append([r["name"] or _short(r["key"]), r["quantity"],
                         money_display(r["net_revenue"]), money_display(r["discounts"]),
                         money_display(r["cost_of_sales"]), money_display(r["waste"]),
                         money_display(r["direct_costs"]), money_display(r["gross_margin"]),
                         money_display(r["contribution_margin"]),
                         f"{r['contribution_percent']} %" if r["contribution_percent"] else ""])
        return TableViewModel(rows, [])

    def branch_results(self, date_from: date, date_to: date) -> TableViewModel:
        rows = [[_short(r["branch_id"]), money_display(r["net_revenue"]),
                 money_display(r["gross_profit"]), money_display(r["operating_income"]),
                 money_display(r["net_income"])]
                for r in self._q["profitability"].branch_results(date_from=date_from.isoformat(),
                                                                 date_to=date_to.isoformat())]
        return TableViewModel(rows, [])

    # ── configuración ────────────────────────────────────────────────────
    def settings_rows(self) -> TableViewModel:
        settings = self._q["settings"].settings()
        stored = settings.as_storage()
        accounts = {a["id"]: f"{a['code']} — {a['name']}"
                    for a in self._q["accounts"].chart_of_accounts()}
        rows, ids = [], []
        for f in fields(settings):
            value = stored[f.name]
            if f.name == "rounding_account_id":
                value = accounts.get(value, value)
            elif isinstance(getattr(settings, f.name), bool):
                value = yes_no(getattr(settings, f.name))
            rows.append([SETTING_LABELS.get(f.name, f.name), value or "Sin definir"])
            ids.append(f.name)
        return TableViewModel(rows, ids)

    def setting_value(self, key: str) -> str:
        return self._q["settings"].settings().as_storage().get(key, "")

    @staticmethod
    def setting_is_bool(key: str) -> bool:
        return key in ("journal_review_required", "payment_dual_control",
                       "statement_importer_cannot_adjust")

    def update_setting(self, key: str, value: str, reason: str) -> tuple[bool, str]:
        return self._command("update_settings", {key: value}, reason=reason,
                             done="Parámetro actualizado (queda en la auditoría).")

    def posting_profiles(self) -> TableViewModel:
        rows, ids = [], []
        for p in self._q["settings"].posting_profiles():
            for role in p["roles"]:
                rows.append([p["profile_key"], p["description"], role["role"],
                             f"{role['account_code']} — {role['account_name']}",
                             p["effective_from"], p["effective_to"] or "Vigente",
                             "Vigente" if p["current"] else "Histórico"])
                ids.append(f"{p['id']}|{role['role']}")
        return TableViewModel(rows, ids)

    def profile_accounts(self, profile_id: str) -> dict[str, str]:
        for p in self._q["settings"].posting_profiles():
            if p["id"] == profile_id:
                return {r["role"]: r["account_id"] for r in p["roles"]}
        return {}

    def update_posting_profile(self, profile_id: str, role: str, account_id: str,
                               effective_from: date, reason: str) -> tuple[bool, str]:
        accounts = self.profile_accounts(profile_id)
        accounts[role] = account_id
        return self._command("update_posting_profile", profile_id, accounts=accounts,
                             effective_from=effective_from, reason=reason,
                             done="Perfil contable versionado; los asientos pasados no cambian.")

    def taxes(self) -> TableViewModel:
        rows, ids = [], []
        for t in self._q["settings"].taxes():
            rules = ", ".join(r["scope"] for r in t["rules"]) or "Sin reglas"
            rows.append([t["code"], t["name"], t["kind"],
                         dict(self.tax_direction_options()).get(t["direction"], t["direction"]),
                         f"{t['rate_percent']} %" if t["rate_percent"] != "" else "",
                         rules, "Activo" if t["active"] else "Inactivo"])
            ids.append(t["id"])
        return TableViewModel(rows, ids)

    def create_tax_code(self, **data) -> tuple[bool, str]:
        data["kind"] = TaxKind(data["kind"])
        data["direction"] = TaxDirection(data["direction"])
        return self._command("create_tax_code", **data, done="Impuesto creado.")

    def currencies_and_rates(self) -> dict:
        currencies = TableViewModel(
            [[c["code"], c["name"], str(c["decimal_places"]), yes_no(c["active"])]
             for c in self._q["settings"].currencies()], [])
        rates = TableViewModel(
            [[r["effective_date"], r["from_currency"], r["to_currency"], r["rate"],
              r["source"] or ""] for r in self._q["settings"].exchange_rates()], [])
        return {"currencies": currencies, "rates": rates}

    def register_exchange_rate(self, **data) -> tuple[bool, str]:
        return self._command("register_exchange_rate", **data, done="Tipo de cambio registrado.")

    def dimensions(self) -> TableViewModel:
        labels = {"cost_centers": "Centro de costo", "profit_centers": "Centro de utilidad",
                  "projects": "Proyecto", "departments": "Departamento"}
        rows, ids = [], []
        for kind, items in self._q["settings"].dimensions().items():
            for item in items:
                extra = "CAPEX" if item.get("is_capex") else ""
                rows.append([labels.get(kind, kind), item["code"], item["name"], extra])
                ids.append(item["id"])
        return TableViewModel(rows, ids)

    def create_dimension(self, **data) -> tuple[bool, str]:
        return self._command("create_dimension", **data, done="Dimensión creada.")

    def audit_log(self, *, entity_type: str | None = None, search: str = "",
                  limit: int = 50, offset: int = 0) -> TableViewModel:
        rows, ids = [], []
        needle = search.strip().lower()
        for e in self._q["audit"].entries(entity_type=entity_type, limit=limit, offset=offset):
            text = f"{e['action']} {e['entity_type']} {e['reason'] or ''}".lower()
            if needle and needle not in text:
                continue
            rows.append([e["occurred_at"][:19].replace("T", " "), e["action"], e["entity_type"],
                         _short(e["entity_id"]), _short(e["user_id"]), e["reason"] or "",
                         _changes(e["before"], e["after"])])
            ids.append(e["id"])
        return TableViewModel(rows, ids)

    def record_export(self, what: str, file_name: str, rows: int) -> tuple[bool, str]:
        return self._command("record_export", what=what, file_name=file_name, rows=rows,
                             done=f"Exportación registrada: {rows} renglones.")


def _side(value) -> str:
    """Importe del lado debe/haber: el lado vacío se deja en blanco."""
    try:
        return "" if Decimal(str(value or "0")) == 0 else money_display(value)
    except InvalidOperation:
        return str(value)


def _changes(before: dict, after: dict) -> str:
    keys = sorted(set(before) | set(after))
    parts = [f"{k}: {before.get(k, '—')} → {after.get(k, '—')}" for k in keys
             if before.get(k) != after.get(k)]
    return "; ".join(parts)[:300]


def decimal_text(value) -> str:
    """Texto decimal canónico para enviar al backend (sin float)."""
    try:
        return format(Decimal(str(value)), "f")
    except (InvalidOperation, ValueError):
        return str(value)
