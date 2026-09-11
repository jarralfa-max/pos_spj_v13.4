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

from datetime import date
from decimal import Decimal

from backend.application.customer_credit.use_cases.check_credit_sale_eligibility_use_case import (
    CheckCreditSaleEligibilityUseCase,
)
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.use_cases.finance.receivable_use_cases import CreateReceivableUseCase


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

    def register(
        self, *, customer_id: str, sale_id: str, folio: str, amount: Decimal,
        branch_id: str,
    ) -> None:
        """Apunta la deuda de una venta cobrada a crédito.

        Idempotente por `operation_id`: derivado de la venta, así que reintentar
        el cobro no duplica la cuenta por cobrar. Es la misma garantía que daba
        el `INSERT OR IGNORE` del servicio anterior, pero explícita.

        No se fija `due_date`: el plazo depende de las condiciones pactadas con
        el cliente, que viven en su perfil de crédito. Inventarlo aquí —treinta
        días, pongamos— haría que la consulta de vencidos marcara como morosos a
        clientes que no lo son. Queda pendiente de que el cobro lea el plazo del
        perfil.
        """
        CreateReceivableUseCase().execute(
            self._connection, customer_id=customer_id, amount=str(amount),
            document_number=folio or sale_id, issue_date=date.today(),
            branch_id=branch_id, source_module="sales", source_document_id=sale_id,
            operation_id=f"{sale_id}:receivable",
        )
