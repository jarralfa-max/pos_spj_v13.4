"""SalesLoyaltyClient — el punto por donde Ventas habla con Fidelidad.

Tres operaciones: consultar saldo para el ticket, previsualizar un canje
mientras el cajero cobra, y ejecutarlo.

QUÉ CAMBIÓ
----------
Envolvía `core/services/loyalty_service.py::LoyaltyService`, borrado con la
carpeta `core/`. No se reconstruyó esa clase: el contexto acotado canónico
`loyalty` ya tiene libro de puntos, cuentas y casos de uso. Lo que faltaba eran
las REGLAS DE CANJE del punto de venta (mínimo, tope del 50 %, conversión a
pesos), que ahora viven en
`backend/domain/loyalty/policies/redemption_policy.py`.

Esas reglas no se inventaron: su contrato completo —campos, topes y
aritmética— sobrevive en `tests/test_loyalty_redemption_source.py`, y sus
parámetros son filas de `configuraciones` que ese mismo test siembra.

Desaparecen dos conversiones de frontera que este archivo hacía y documentaba
como deuda:

  identidad  `customers.id` → `clientes.id` con `EnsureLegacyCustomerBridgeUseCase`
             en CADA llamada. La cuenta canónica ya se resuelve por
             `customers.id`; el puente sobra.
  números    Decimal → float, porque el servicio legacy hablaba en float. La
             política canónica trabaja en Decimal de extremo a extremo.

EL SALDO SUMA LOS DOS LIBROS. `loyalty_ledger` (legacy, sin escritores desde la
reconstrucción pero con saldo real) y `loyalty_transactions` (canónico). Ver
`LoyaltyPointsBalanceRepository`: leer sólo el canónico dejaría en cero a todo
cliente que acumuló antes, sin ningún error visible.

FORMA DEL RESULTADO. `preview_redemption` sigue devolviendo el diccionario en
español que sus dos consumidores ya leen (`benefit_evaluation_service`,
`sales_pos`). Traducirlo aquí, en la frontera, es más barato y menos arriesgado
que cambiar a la vez el servicio, la pantalla y sus pruebas — y es exactamente
para lo que existe un adaptador.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.application.loyalty.queries.redemption_preview_query import (
    LoyaltyRedemptionPreviewQuery,
)
from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.domain.document_output.value_objects.loyalty_summary import LoyaltySummary


class SalesLoyaltyClient:
    def __init__(
        self, connection, *, actor_branch_id: str = "",
        authorization: LoyaltyAuthorizationPolicy | None = None,
    ) -> None:
        self._connection = connection
        self._actor_branch_id = actor_branch_id
        self._query = LoyaltyRedemptionPreviewQuery(connection)
        # Sin política explícita no se concede nada: el caso de uso lanza en
        # cuanto se usa. Nunca una permisiva por omisión (§23). Consultar saldo
        # y previsualizar no pasan por aquí — son lecturas sin efecto.
        self._authorization = authorization or LoyaltyAuthorizationPolicy()

    # ── lectura ──────────────────────────────────────────────────────────
    def peek_loyalty_summary(self, *, customer_id: str) -> LoyaltySummary:
        """Saldo para imprimir en el ticket. No acumula ni descuenta nada.

        `points_earned` se queda en `None` a propósito: el cobro canónico no
        tiene todavía acumulación de puntos, y un cero ahí se leería en el
        ticket como "esta compra no generó puntos" en vez de "aún no se
        calcula". Nunca se fabrica ese número.
        """
        balance = self._query.balance(customer_id) if str(customer_id or "").strip() else 0
        return LoyaltySummary.create(
            points_balance=balance, tier="", available=balance > 0)

    def preview_redemption(self, *, customer_id: str, subtotal: Decimal) -> dict[str, Any]:
        """Qué podría canjear el cliente. Sin efectos secundarios."""
        return self._as_legacy_shape(
            self._query.preview(customer_id=customer_id, subtotal=subtotal),
            customer_id=customer_id)

    def _as_legacy_shape(self, preview, *, customer_id: str) -> dict[str, Any]:
        settings = self._query.settings()
        return {
            "enabled": bool(str(customer_id or "").strip()) and preview.available_points > 0,
            "cliente_id": customer_id,
            "puntos_disponibles": preview.available_points,
            "valor_por_punto": float(settings.point_value),
            "min_puntos_canje": settings.min_points,
            "max_pct_canje": float(settings.max_percent),
            "puntos_maximos_canjeables": preview.max_redeemable_points,
            "descuento_maximo": float(preview.max_discount),
            "puntos_solicitados": preview.requested_points,
            "descuento": float(preview.discount),
            "total_original": float(preview.subtotal),
            "total_con_descuento": float(preview.total_after_discount),
            "nivel": "",
            "mensaje": "",
        }

    # ── canje ────────────────────────────────────────────────────────────
    def redeem(
        self, *, customer_id: str, sale_id: str, subtotal: Decimal, points: int,
        actor_user_id: str,
    ) -> dict[str, Any]:
        """El canje de verdad: descuenta puntos del libro canónico.

        Se previsualiza PRIMERO y se canjea la cantidad que sale de ahí, nunca
        la que pidió quien llama. La previsualización es la única que aplica el
        mínimo, el tope de porcentaje y el saldo; usar el número crudo del
        llamador saltaría los tres sin que nada lo impidiera.

        IDEMPOTENTE POR VENTA, y no por el camino que parecería. El contexto de
        fidelidad exige que `operation_id` sea un UUIDv7 canónico, así que no
        puede derivarse del `sale_id` como se hace en inventario. Fabricar un
        UUID con forma de v7 a partir de un hash pasaría la validación pero
        mentiría: un v7 lleva un instante dentro, y ése no correspondería a
        ninguno.

        En su lugar se comprueba lo que ya está escrito: la transacción guarda
        su `sale_id`, así que un canje previo de ESTA venta se reconoce y se
        devuelve tal cual en vez de descontar otra vez.
        """
        preview = self._query.preview(
            customer_id=customer_id, subtotal=subtotal, requested_points=points)
        if preview.requested_points <= 0:
            return self._rejected(
                "Canje de fidelidad no disponible para este cliente o importe")

        account_id = self._account_id(customer_id)
        if not account_id:
            return self._rejected("El cliente no tiene cuenta de fidelidad")

        ya_canjeado = self._existing_redemption(account_id, sale_id)
        if ya_canjeado is not None:
            return ya_canjeado

        from backend.application.loyalty.use_cases.ledger_use_cases import (
            RedeemLoyaltyPointsUseCase,
        )
        from backend.shared.ids import new_uuid

        result = RedeemLoyaltyPointsUseCase(self._authorization).execute(
            self._connection, loyalty_account_id=account_id,
            points_amount=Decimal(preview.requested_points),
            operation_id=new_uuid(),
            actor_user_id=actor_user_id, actor_branch_id=self._actor_branch_id,
            source_module="sales", sale_id=sale_id,
        )
        if not result.success:
            return self._rejected(result.message or "Canje rechazado")
        return {
            "approved": True,
            "points_redeemed": preview.requested_points,
            "discount_amount": preview.discount,
            "reason": "",
        }

    def _existing_redemption(self, account_id: str, sale_id: str) -> dict[str, Any] | None:
        """El canje ya aplicado a esta venta, si lo hubo.

        Devuelve el MISMO resultado que la primera vez —puntos y descuento
        incluidos— en lugar de un rechazo: para quien cobra, reintentar una
        operación que ya salió bien tiene que verse como que salió bien.
        """
        from backend.domain.loyalty.enums import TransactionType
        from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
            LoyaltyTransactionRepository,
        )

        for transaction in LoyaltyTransactionRepository(self._connection).list_for_account(
                account_id):
            if (transaction.sale_id == sale_id
                    and transaction.transaction_type is TransactionType.REDEEM):
                puntos = int(abs(transaction.points_amount))
                return {
                    "approved": True, "points_redeemed": puntos,
                    "discount_amount": puntos * self._query.settings().point_value,
                    "reason": "",
                }
        return None

    def _account_id(self, customer_id: str) -> str:
        from backend.infrastructure.db.repositories.loyalty.account_repository import (
            LoyaltyAccountRepository,
        )

        account = LoyaltyAccountRepository(self._connection).get_by_customer_id(customer_id)
        return account.id if account else ""

    @staticmethod
    def _rejected(reason: str) -> dict[str, Any]:
        return {
            "approved": False, "points_redeemed": 0,
            "discount_amount": Decimal("0"), "reason": reason,
        }
