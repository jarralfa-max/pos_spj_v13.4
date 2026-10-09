"""Crédito del cliente (§37-40, CRM-43): solicitudes, perfiles, exposición,
cuentas por cobrar, historial y alertas.

Antes: seis rutas «en construcción»; el workflow (solicitar → revisar →
aprobar → límite / suspensión / bloqueo) existía sin pantalla, así que no
había forma de autorizar crédito a nadie.

Reglas que NO viven aquí (las aplica el caso de uso): quien solicita no aprueba
su propia solicitud (§73), aprobar exige límite mayor a cero, todo importe es
Decimal. Los importes llegan ya enmascarados según el permiso
(``ver_sensible`` / ``ver_resumen``). CxC es de Finanzas (§40): aquí sólo se
muestra la exposición, no se registran cobros.
"""

from __future__ import annotations

from backend.application.customers.permissions import CustomerPermissions
from frontend.desktop.components import ColumnSpec
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import fmt_date, fmt_datetime, fmt_money
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import event_label, label, options
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    Kpi,
    Row,
)



def _money_or_mask(text) -> str:
    raw = str(text or "")
    return fmt_money(raw) if raw.replace(".", "", 1).replace("-", "", 1).isdigit() else (raw or "—")


def request_credit_dialog(parent, presenter, *, customer_id: str | None = None,
                          customer_label: str = ""):
    return ask(parent, title="Solicitar crédito", submit_text="Enviar solicitud", intro=(
        "La solicitud queda «Por aprobar». La revisa un analista y la aprueba otra persona: "
        "quien solicita no puede aprobar su propia solicitud."), fields=(
        FieldSpec("customer_id", "Cliente", "customer", required=True, default=customer_id,
                  default_label=customer_label),
        FieldSpec("requested_limit", "Límite solicitado", "money", required=True),
        FieldSpec("payment_terms_days", "Plazo de pago (días)", "integer", default=15,
                  maximum=365),
    ), customer_provider=presenter.customer_search_options, on_submit=lambda v: presenter.run(
        "request_credit", customer_id=v["customer_id"], requested_limit=v["requested_limit"],
        payment_terms_days=v["payment_terms_days"]))


def _reason(parent, presenter, command: str, title: str, submit: str, customer_id: str):
    return ask(parent, title=title, submit_text=submit, fields=(
        FieldSpec("reason", "Motivo", "textarea", required=True),
    ), on_submit=lambda v: presenter.run(command, customer_id=customer_id, reason=v["reason"]))


def credit_actions(page, presenter) -> list[Action]:
    p = presenter
    st = lambda r: r.data.profile.status.value  # noqa: E731
    cid = lambda r: r.data.profile.customer_id  # noqa: E731
    return [
        Action("Revisar", lambda r: page.report(ask(
            page, title="Revisar solicitud", submit_text="Pasar a revisión", fields=(
                FieldSpec("risk_level", "Riesgo", "choice", options=tuple(options("risk_level")),
                          default=r.data.profile.risk_level.value),
                FieldSpec("reason", "Observaciones", "textarea")),
            on_submit=lambda v: p.run("review_credit", customer_id=cid(r),
                                      risk_level=v["risk_level"], reason=v["reason"]))),
            enabled=lambda r: st(r) == "PENDING_APPROVAL",
            permission=CustomerPermissions.CREDIT_REVIEW),
        Action("Aprobar", lambda r: page.report(ask(
            page, title="Aprobar crédito", submit_text="Aprobar", fields=(
                FieldSpec("credit_limit", "Límite autorizado", "money", required=True,
                          default=r.data.profile.credit_limit),
                FieldSpec("payment_terms_days", "Plazo de pago (días)", "integer",
                          default=r.data.profile.payment_terms_days, maximum=365),
                FieldSpec("risk_level", "Riesgo", "choice", options=tuple(options("risk_level")),
                          default=r.data.profile.risk_level.value)),
            on_submit=lambda v: p.run("approve_credit", customer_id=cid(r),
                                      credit_limit=v["credit_limit"],
                                      payment_terms_days=v["payment_terms_days"],
                                      risk_level=v["risk_level"]))),
            enabled=lambda r: st(r) == "UNDER_REVIEW",
            permission=CustomerPermissions.CREDIT_APPROVE, primary=True),
        Action("Rechazar", lambda r: page.report(_reason(
            page, p, "reject_credit", "Rechazar crédito", "Rechazar", cid(r))),
            enabled=lambda r: st(r) in ("PENDING_APPROVAL", "UNDER_REVIEW"),
            permission=CustomerPermissions.CREDIT_REJECT),
        Action("Cambiar límite", lambda r: page.report(ask(
            page, title="Cambiar límite de crédito", submit_text="Aplicar", fields=(
                FieldSpec("new_limit", "Nuevo límite", "money", required=True),
                FieldSpec("override", "Aumento extraordinario (requiere permiso especial)",
                          "check"),
                FieldSpec("reason", "Motivo", "textarea", required=True)),
            on_submit=lambda v: p.run("update_credit_limit", customer_id=cid(r),
                                      new_limit=v["new_limit"], override=bool(v["override"]),
                                      reason=v["reason"]))),
            enabled=lambda r: st(r) == "AUTHORIZED",
            permission=CustomerPermissions.CREDIT_LIMIT_EDIT),
        Action("Suspender", lambda r: page.report(_reason(
            page, p, "suspend_credit", "Suspender crédito", "Suspender", cid(r))),
            enabled=lambda r: st(r) == "AUTHORIZED", permission=CustomerPermissions.CREDIT_SUSPEND),
        Action("Bloquear", lambda r: page.report(_reason(
            page, p, "block_credit", "Bloquear crédito", "Bloquear", cid(r))),
            enabled=lambda r: st(r) in ("AUTHORIZED", "SUSPENDED"),
            permission=CustomerPermissions.CREDIT_BLOCK),
        Action("Reabrir", lambda r: page.report(_reason(
            page, p, "reopen_credit", "Reabrir crédito", "Reabrir", cid(r))),
            enabled=lambda r: st(r) in ("SUSPENDED", "BLOCKED"),
            permission=CustomerPermissions.CREDIT_REOPEN),
        Action("Cerrar", lambda r: page.report(_reason(
            page, p, "close_credit", "Cerrar crédito", "Cerrar crédito", cid(r))),
            enabled=lambda r: st(r) in ("AUTHORIZED", "SUSPENDED", "BLOCKED"),
            permission=CustomerPermissions.CREDIT_CLOSE),
    ]


class CreditProfilesPage(CrmWorkbenchPage):
    route_id = "customers.credit_profiles"
    title = "Perfiles de crédito"
    subtitle = "Límite, plazo, riesgo y exposición de cada cliente con crédito."
    icon = Icons.FINANCE
    empty_message = "Ningún cliente tiene crédito todavía. Usa «Solicitar crédito»."
    show_detail = True
    detail_title = "Crédito"
    statuses: tuple[str, ...] = ()
    only_alerts = False
    columns = (ColumnSpec("Cliente", stretch=True), ColumnSpec("Estado", "status"),
               ColumnSpec("Riesgo"), ColumnSpec("Límite", "numeric"),
               ColumnSpec("Exposición", "numeric"), ColumnSpec("Disponible", "numeric"),
               ColumnSpec("Vencido", "numeric"), ColumnSpec("Plazo"),
               ColumnSpec("Alertas"))

    def page_actions(self):
        return [Action("Solicitar crédito", lambda _r: self.report(
            request_credit_dialog(self, self._presenter)),
            permission=CustomerPermissions.CREDIT_REQUEST, primary=True, needs_row=False)]

    def row_actions(self):
        return credit_actions(self, self._presenter)

    def fetch(self, filters):
        items = self._presenter.read("credit_rows", statuses=self.statuses)
        if self.only_alerts:
            items = [i for i in items if i.alerts]
        names = self._presenter.customer_names({i.profile.customer_id for i in items})
        rows = []
        for item in items:
            p, s = item.profile, item.summary
            name = names.get(p.customer_id, "—")
            rows.append(Row(p.id, [
                name, label("credit_status", p.status), label("risk_level", p.risk_level),
                _money_or_mask(s.credit_limit), _money_or_mask(s.current_exposure),
                _money_or_mask(s.available_credit), _money_or_mask(s.overdue_amount),
                f"{p.payment_terms_days} días", ", ".join(item.alerts) or "—"], item, [
                ("Cliente", name), ("Estado", label("credit_status", p.status)),
                ("Riesgo", label("risk_level", p.risk_level)),
                ("Límite", _money_or_mask(s.credit_limit)),
                ("Exposición", _money_or_mask(s.current_exposure)),
                ("Disponible", _money_or_mask(s.available_credit)),
                ("Vencido", _money_or_mask(s.overdue_amount)),
                ("Próximo vencimiento", fmt_date(s.next_due_date)),
                ("Cobranza", label("receivable_status", s.receivable_status)),
                ("Plazo", f"{p.payment_terms_days} días"),
                ("Solicitó", self._presenter.user_name(p.requested_by_user_id)),
                ("Autorizó", self._presenter.user_name(p.authorized_by_user_id)
                 if p.authorized_by_user_id else "—"),
                ("Autorizado el", fmt_datetime(p.authorized_at)),
                ("Alertas", ", ".join(item.alerts) or "Ninguna")], search_text=name))
        return rows

    def kpis(self, rows):
        items = [r.data for r in rows]
        return [
            Kpi("Perfiles", str(len(items))),
            Kpi("Autorizados", str(sum(1 for i in items
                                       if i.profile.status.value == "AUTHORIZED")), "success"),
            Kpi("Por resolver", str(sum(1 for i in items if i.profile.status.value in (
                "PENDING_APPROVAL", "UNDER_REVIEW"))), "info"),
            Kpi("Con alertas", str(sum(1 for i in items if i.alerts)), "warning"),
        ]


class CreditRequestsPage(CreditProfilesPage):
    route_id = "customers.credit_requests"
    title = "Solicitudes de crédito"
    subtitle = "Por aprobar y en revisión. Quien solicita no aprueba su propia solicitud."
    statuses = ("PENDING_APPROVAL", "UNDER_REVIEW")
    empty_message = "No hay solicitudes de crédito pendientes."


class CreditExposurePage(CreditProfilesPage):
    route_id = "customers.credit_exposure"
    title = "Exposición"
    subtitle = "Crédito usado y disponible de los clientes con crédito vigente."
    statuses = ("AUTHORIZED", "SUSPENDED", "BLOCKED")
    empty_message = "No hay clientes con crédito vigente."


class AccountsReceivablePage(CreditProfilesPage):
    route_id = "customers.accounts_receivable"
    title = "Cuentas por cobrar"
    subtitle = ("Saldo, vencido y próximo vencimiento según Finanzas. Los cobros se registran "
                "en Finanzas.")
    statuses = ("AUTHORIZED", "SUSPENDED", "BLOCKED", "CLOSED")
    empty_message = "No hay clientes con crédito y saldo."
    columns = (ColumnSpec("Cliente", stretch=True), ColumnSpec("Exposición", "numeric"),
               ColumnSpec("Vencido", "numeric"), ColumnSpec("Próximo vencimiento", "date"),
               ColumnSpec("Cobranza"), ColumnSpec("Estado del crédito", "status"))

    def page_actions(self):
        return []

    def row_actions(self):
        return []

    def fetch(self, filters):
        rows = super().fetch(filters)
        for row in rows:
            p, s = row.data.profile, row.data.summary
            row.cells = [row.cells[0], _money_or_mask(s.current_exposure),
                         _money_or_mask(s.overdue_amount), fmt_date(s.next_due_date),
                         label("receivable_status", s.receivable_status),
                         label("credit_status", p.status)]
        return rows


class CreditAlertsPage(CreditProfilesPage):
    route_id = "customers.credit_alerts"
    title = "Alertas de crédito"
    subtitle = "Saldo vencido, límite excedido, revisión pendiente y créditos detenidos."
    only_alerts = True
    empty_message = "Sin alertas de crédito."

    def page_actions(self):
        return []


class CreditHistoryPage(CrmWorkbenchPage):
    route_id = "customers.credit_history"
    title = "Historial de crédito"
    subtitle = "Quién solicitó, revisó, aprobó, cambió límites, suspendió o bloqueó, y por qué."
    icon = Icons.MOVEMENTS
    empty_message = "Sin movimientos de crédito."
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Cliente"), ColumnSpec("Movimiento"),
               ColumnSpec("Usuario"), ColumnSpec("Autorizó"), ColumnSpec("Motivo", stretch=True))

    def fetch(self, filters):
        entries = self._presenter.read("credit_history")
        names = self._presenter.customer_names({e.get("customer_id") for e in entries})
        rows = []
        for index, e in enumerate(entries):
            rows.append(Row(f"{index}", [
                fmt_datetime(e.get("created_at")), names.get(e.get("customer_id"), "—"),
                event_label(e.get("action")),
                self._presenter.user_name(e.get("actor_user_id")),
                self._presenter.user_name(e.get("authorized_by_user_id"))
                if e.get("authorized_by_user_id") else "—", e.get("reason") or "—"], e))
        return rows


CREDIT_ROUTE_PAGES = {
    "customers.credit_requests": CreditRequestsPage,
    "customers.credit_profiles": CreditProfilesPage,
    "customers.credit_exposure": CreditExposurePage,
    "customers.accounts_receivable": AccountsReceivablePage,
    "customers.credit_history": CreditHistoryPage,
    "customers.credit_alerts": CreditAlertsPage,
}
