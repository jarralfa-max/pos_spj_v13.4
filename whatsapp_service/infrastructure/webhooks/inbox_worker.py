# infrastructure/webhooks/inbox_worker.py — WA-6 (§20 del prompt maestro)
"""
InboxWorker — drena `whatsapp_inbox` y procesa cada job con un `handler`
inyectado. La lógica real de "qué hacer con un mensaje entrante" (motor
conversacional, resolución de intención) todavía no existe — WA-7
(Conversation Engine) y WA-8 (Intent Resolution) la construyen. Este
worker solo prueba el mecanismo (reclamar → invocar handler → completar/
reintentar/dead-letter) contra un `handler` intercambiable; el handler por
defecto es un no-op explícito, no una implementación fingida.

No es un scheduler — no corre en un hilo/loop propio. Exponer
`run_once()` como una función invocable (por un cron, un endpoint admin,
o eventualmente un loop real) es una decisión de despliegue fuera de
alcance de esta fase.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from domain.whatsapp.entities.inbox_job import InboundMessageJob

logger = logging.getLogger("wa.inbox_worker")

# Reintentos agotados antes de mover a dead letter — mismo orden de
# magnitud que el backoff legacy (`whatsapp_queue`, máx 5 intentos).
MAX_ATTEMPTS = 5

InboxJobHandler = Callable[[InboundMessageJob], Awaitable[None]]


async def _noop_handler(job: InboundMessageJob) -> None:
    """Handler por defecto — completa el job sin hacer nada real. Explícito
    a propósito: no finge resolución de intención que WA-7/WA-8 todavía no
    construyen."""
    return None


class InboxWorker:
    def __init__(self, root, *, handler: Optional[InboxJobHandler] = None) -> None:
        self._root = root
        self._handler = handler or _noop_handler

    async def run_once(self, *, limit: int = 10) -> int:
        """Reclama hasta `limit` jobs pendientes y los procesa. Retorna
        cuántos se reclamaron (no cuántos tuvieron éxito — ver logs para
        eso)."""
        inbox = self._root.inbox
        jobs = inbox.claim_pending(limit=limit)
        for job in jobs:
            await self._process_one(job)
        return len(jobs)

    async def _process_one(self, job: InboundMessageJob) -> None:
        inbox = self._root.inbox
        try:
            await self._handler(job)
        except Exception as exc:
            job.fail(str(exc))
            logger.warning("InboundMessageJob %s falló (intento %d): %s", job.id, job.attempts, exc)
            if job.attempts >= MAX_ATTEMPTS:
                job.move_to_dead_letter(str(exc))
            else:
                job.schedule_retry()
            inbox.save(job)
            return

        job.complete()
        inbox.save(job)
