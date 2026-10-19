"""Transformación directa (auditoría de Producción 32cfbf): lote recibido →
pesos reales de cada corte → una sola acción.

Sin SQL ni reglas: la lista de lotes y lo esperado salen de
`DirectTransformationQueryService`; la acción, de
`ExecuteDirectTransformationUseCase`. El presentador sólo conserva el
`operation_id` del intento en curso para que reintentar (p. ej. tras la
autorización de un rendimiento fuera de tolerancia) RETOME la misma
transformación en vez de crear otra orden.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.meat_processing.direct_transformation_presenter")


class DirectTransformationPresenter:
    def __init__(self, *, connection_provider, query_factory, execute_uc, session_context,
                 context_provider, credentials_verifier=None, dispatch=None) -> None:
        self._conn = connection_provider
        self._query = query_factory
        self._execute_uc = execute_uc
        self._session = session_context
        self._context = context_provider
        self._verify = credentials_verifier
        self._dispatch = dispatch
        #: (lot_id, kg) → operation_id del intento en curso.
        self._attempt: tuple[tuple[str, str], str] | None = None

    def _branch(self) -> str:
        return str(getattr(self._session, "active_branch_id", "") or "")

    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", "") or "")

    def unavailable_reason(self) -> str | None:
        try:
            return self._query(self._conn()).unavailable_reason(self._branch())
        except Exception:
            logger.exception("transformación directa: motivo no disponible")
            return "No se pudo consultar la existencia; revise el log."

    def lots(self):
        try:
            return self._query(self._conn()).lots(self._branch())
        except Exception:
            logger.exception("transformación directa: lotes no disponibles")
            return []

    def preview(self, product_id: str, input_kg):
        return self._query(self._conn()).preview(product_id, input_kg)

    def transform(self, *, lot_id: str, input_kg, outputs: list[dict],
                estimated_product_ids=(), estimate_reason=None,
                variance_authorizer_user_id=None, variance_reason=None,
                ) -> tuple[bool, str, dict]:
        clave = (lot_id, str(Decimal(str(input_kg or 0))))
        if self._attempt is None or self._attempt[0] != clave:
            self._attempt = (clave, new_uuid())
        operation_id = self._attempt[1]
        try:
            result = self._execute_uc.execute(
                self._conn(), operation_id=operation_id, branch_id=self._branch(),
                lot_id=lot_id, input_weight=input_kg, outputs=outputs,
                actor_user_id=self._actor(),
                estimated_product_ids=tuple(estimated_product_ids or ()),
                estimate_reason=estimate_reason,
                variance_authorizer_user_id=variance_authorizer_user_id,
                variance_reason=variance_reason, context=self._context())
        except Exception:
            logger.exception("DirectTransformationPresenter.transform failed")
            return False, "Error inesperado; revise el log.", {}
        if result.success:
            self._attempt = None
            if self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
        datos = dict(result.data)
        if result.error_code:
            datos["error_code"] = result.error_code
        return bool(result.success), result.message, datos

    def verify_authorizer(self, usuario: str, clave: str) -> tuple[str | None, str]:
        if self._verify is None:
            return None, "Verificación de autorizador no disponible."
        return self._verify(usuario, clave)
