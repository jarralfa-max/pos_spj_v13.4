"""SalesCreditClient — el punto por donde Ventas habla con Crédito y CxC.

Dos preguntas, y sólo dos: ¿puede este cliente llevarse esto a crédito?, y
—cuando la venta se cobra a crédito— apunta la deuda.

QUÉ CAMBIÓ Y POR QUÉ
--------------------
Antes envolvía `application.services.customer_credit_service.CustomerCreditService`,
que desapareció con la carpeta `application/`. No se reconstruyó: el contexto
acotado canónico `customer_credit` ya responde a la primera pregunta mejor, y
Finanzas a la segunda.

    legacy CustomerCreditService      canónico
    ─────────────────────────────     ──────────────────────────────────────
    sí/no a secas                     lista TODAS las reglas incumplidas
    exposición de un valor guardado   la calcula viva desde CxC
    hablaba en `clientes.id`          habla en `customers.id`
    montos en float                   Decimal

El cambio de identidad borra un puente entero: la versión anterior traducía
`customers.id` → `clientes.id` con `EnsureLegacyCustomerBridgeUseCase` en CADA
llamada, porque el servicio legacy sólo entendía la tabla vieja. El contexto
canónico trabaja directamente sobre Customer Master, así que el puente sobra.

LO QUE ESTABA ROTO, Y NO ERA EVIDENTE
-------------------------------------
El límite de crédito no se estaba aplicando. `CustomerAccountsReceivableSummaryQuery`
calcula la exposición leyendo `cuentas_por_cobrar`, y desde que desapareció el
servicio legacy NADIE escribe esa tabla: la exposición de cualquier cliente
daba cero, así que toda venta a crédito resultaba elegible por mucho que el
cliente ya debiera.

Por eso `register()` apunta la deuda en el modelo canónico (`receivables`, vía
`CreateReceivableUseCase`) Y la consulta de exposición pasó a leer las dos
fuentes. Escribir en la canónica sin cambiar la lectura habría dejado el agujero
exactamente igual de abierto, sólo que más difícil de ver.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.application.customer_credit.use_cases.check_credit_sale_eligibility_use_case import (
    CheckCreditSaleEligibilityUseCase,
)
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.use_cases.finance.register_sale_credit_charge_use_case import (
    RegisterSaleCreditChargeUseCase,
    VoidSaleCreditChargeUseCase,
)


class SalesCreditClient:
    def __init__(
        self, connection, *, actor_user_id: str = "",
        authorization: CustomerAuthorizationPolicy | None = None,
    ) -> None:
        self._connection = connection
        self._actor_user_id = actor_user_id
        # Igual que en el cliente de inventario: sin política explícita se
        # construye una sin verificador, que no concede nada. Nunca una
        # permisiva por omisión (§23).
        self._authorization = authorization or CustomerAuthorizationPolicy()

    def validate(self, *, customer_id: str, amount: Decimal) -> tuple[bool, str]:
        """`(True, "")` si el cliente puede llevarse `amount` a crédito.

        Nunca lanza por un rechazo de negocio: un cliente sin crédito
        suficiente no es un error del programa, es una respuesta. Cuando hay
        varias reglas incumplidas se devuelven todas en el motivo — el cajero
        necesita saber si es el límite, la documentación o la sucursal, no sólo
        que "no se puede".
        """
        result = CheckCreditSaleEligibilityUseCase(self._authorization).execute(
            self._connection, actor_user_id=self._actor_user_id, customer_id=customer_id,
            amount=Decimal(str(amount)),
            operation_id=f"{customer_id}:credit-check:{amount}",
        )
        if result.success:
            return True, ""
        violaciones = result.data.get("violations") or []
        return False, "; ".join(str(v) for v in violaciones) or result.message

    def _due_date(self, customer_id: str, issued: date) -> date | None:
        from backend.infrastructure.db.repositories.customer_credit.unit_of_work import (
            CustomerCreditUnitOfWork,
        )
        if not self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table'"
                " AND name='customer_credit_profiles'").fetchone():
            return None  # sin perfiles de crédito no hay plazo pactado que fijar
        profile = CustomerCreditUnitOfWork(self._connection).profiles.get_by_customer_id(
            customer_id)
        if profile is None:
            return None
        return issued + timedelta(days=int(profile.payment_terms_days or 0))

    def register(
        self, *, customer_id: str, sale_id: str, folio: str, amount: Decimal,
        branch_id: str, payment_id: str,
    ) -> None:
        """Apunta la deuda de un pago a crédito de una venta.

        Idempotente por PAGO (auditoría de Finanzas F03): antes la clave era
        sólo la venta, así que un segundo pago a crédito de la misma venta se
        tomaba por reintento del primero y la deuda quedaba en el primer
        importe. Ahora cada pago suma su cargo; reintentar un pago no lo duplica.

        `due_date` (auditoría CRM F23): el plazo pactado VIGENTE del perfil de
        crédito del cliente al momento de la venta, fijo en el documento. Si
        después cambian las condiciones del cliente, esta deuda conserva su
        vencimiento. Nunca un plazo inventado: sin perfil, no se fija.
        """
        today = date.today()
        RegisterSaleCreditChargeUseCase().execute(
            self._connection, customer_id=customer_id, sale_id=sale_id,
            payment_id=payment_id, folio=folio or sale_id, amount=str(amount),
            issue_date=today, due_date=self._due_date(customer_id, today),
            branch_id=branch_id,
            # Se llama dentro de la transacción del cobro (SalesUnitOfWork): la
            # deuda vive o muere con la venta (auditoría CRM F01).
            owns_transaction=False,
        )

    def void(self, *, sale_id: str, payment_id: str) -> None:
        """Retira de CxC el cargo de un pago a crédito anulado antes de cerrar la
        venta (auditoría de Ventas V02). Dentro de la transacción del cobro."""
        VoidSaleCreditChargeUseCase().execute(
            self._connection, sale_id=sale_id, payment_id=payment_id,
            owns_transaction=False)
