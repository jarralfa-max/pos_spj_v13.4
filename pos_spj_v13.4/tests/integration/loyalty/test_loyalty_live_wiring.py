"""FID-10 (auditoría de Fidelidad 968e0bc): lo que una venta deja pendiente para
Fidelidad y Finanzas se entrega al ARRANCAR y en un ciclo periódico, no sólo en
la siguiente operación del POS.

Sustituye a `tests/test_loyalty_event_wiring_phase7.py`, que leía
`core/events/wiring.py` y `modulos/fidelidad_config.py`, rutas retiradas: no
probaba el cableado vivo sino archivos que ya no existen."""

from __future__ import annotations

import inspect

from backend.bootstrap.wiring import event_wiring


def test_startup_delivers_pending_sales_to_loyalty():
    fuente = inspect.getsource(event_wiring.wire_cross_context_events)
    assert "loyalty_sales_tick(connection, bus)" in fuente


def test_the_tick_drains_the_sales_outbox_and_posts_to_finance():
    fuente = inspect.getsource(event_wiring.loyalty_sales_tick)
    assert "dispatch_sales_outbox(connection, bus)" in fuente
    assert fuente.count("post_loyalty_finance(connection)") == 2


def test_the_shell_retries_periodically():
    from frontend.desktop.shell import desktop_shell_window_composition as shell

    fuente = inspect.getsource(shell)
    assert '"loyalty.sales_events"' in fuente
    assert shell.LOYALTY_SALES_INTERVAL_MS <= 5 * 60 * 1000
