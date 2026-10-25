"""Qué operaciones de una transferencia se permiten sin conexión con el servidor
central: política de DOMINIO (la autoridad crítica, como aprobar, nunca se hace
fuera de línea).

El motor receptor que la usaba (`transfers/offline_sync.py`: huecos de
secuencia, huella y versión) se retiró en el Slice 4 de la arquitectura híbrida:
esas verificaciones las hace ahora la ingesta central
(`backend/application/sync/central_ingestion.py`) para TODOS los contextos.
"""

import pytest

from backend.domain.transfers.exceptions import OfflineOperationNotAllowedError
from backend.domain.transfers.policies.offline_transfer_policy import (
    OfflineTransferOperation,
    OfflineTransferPolicy,
)


def test_enabled_operations_pass_and_critical_ones_are_refused():
    politica = OfflineTransferPolicy(frozenset({OfflineTransferOperation.PICK,
                                                OfflineTransferOperation.WEIGH}))
    politica.require_allowed(OfflineTransferOperation.PICK)
    politica.require_allowed(OfflineTransferOperation.WEIGH)
    with pytest.raises(OfflineOperationNotAllowedError):
        politica.require_allowed(OfflineTransferOperation.DISPATCH)
