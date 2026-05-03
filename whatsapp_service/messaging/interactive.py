# messaging/interactive.py — Constructores de mensajes interactivos
"""
Funciones helper para construir los mensajes con botones y listas
que cubren el 70% de la interacción sin NLP.
"""
from __future__ import annotations
from typing import List, Dict
from messaging.sender import send_buttons, send_list, send_text


async def send_menu_principal(to: str, nombre: str = ""):
    """Menú principal — primer contacto o /menu."""
    saludo = f"¡Hola{' ' + nombre if nombre else ''}! 👋"
    await send_buttons(
        to=to,
        body=f"{saludo}\n¿Qué deseas hacer?",
        buttons=[
            {"id": "menu_pedido", "title": "🛒 Hacer pedido"},
            {"id": "menu_cotizacion", "title": "📋 Cotización"},
            {"id": "menu_estado", "title": "📦 Mi pedido"},
        ],
        footer="SPJ POS • Escribe 'ayuda' en cualquier momento",
    )


async def send_menu_secundario(to: str):
    """Menú con opciones extras."""
    await send_buttons(
        to=to,
        body="Más opciones:",
        buttons=[
            {"id": "menu_repetir", "title": "🔄 Repetir pedido"},
            {"id": "menu_sucursal", "title": "📍 Cambiar sucursal"},
            {"id": "menu_ayuda", "title": "❓ Ayuda"},
        ],
    )


async def send_seleccion_sucursal(to: str, sucursales: List[Dict]):
    """Lista de sucursales para selección."""
    rows = []
    for s in sucursales[:10]:
        rows.append({
            "id": f"suc_{s['id']}",
            "title": s["nombre"][:24],
            "description": s.get("direccion", "")[:72],
        })

    await send_list(
        to=to,
        body="📍 Selecciona tu sucursal para continuar:",
        sections=[{"title": "Sucursales", "rows": rows}],
        button_text="Ver sucursales",
    )


async def send_categorias(to: str, categorias: List[str]):
    """Lista de categorías de productos."""
    rows = []
    for i, cat in enumerate(categorias[:10]):
        rows.append({
            "id": f"cat_{cat.lower().replace(' ', '_')}",
            "title": cat[:24],
        })

    await send_list(
        to=to,
        body="¿Qué categoría te interesa?",
        sections=[{"title": "Categorías", "rows": rows}],
        button_text="Ver categorías",
    )


async def send_productos(to: str, productos: List[Dict], categoria: str = ""):
    """Lista de productos de una categoría."""
    rows = []
    for p in productos[:10]:
        precio_str = f"${p['precio']:.2f}/{p['unidad']}"
        stock_str = f" • Stock: {p['stock']:.0f}" if p.get('stock', 0) > 0 else " • Agotado"
        rows.append({
            "id": f"prod_{p['id']}",
            "title": p["nombre"][:24],
            "description": (precio_str + stock_str)[:72],
        })

    header = f"📦 {categoria}" if categoria else "📦 Productos"
    await send_list(
        to=to,
        body=f"Selecciona un producto:",
        sections=[{"title": header, "rows": rows}],
        button_text="Ver productos",
    )


async def send_cantidad(to: str, producto_nombre: str, unidad: str = "kg"):
    """Botones para seleccionar cantidad."""
    await send_buttons(
        to=to,
        body=f"¿Cuántos {unidad} de *{producto_nombre}*?",
        buttons=[
            {"id": "qty_1", "title": f"1 {unidad}"},
            {"id": "qty_3", "title": f"3 {unidad}"},
            {"id": "qty_5", "title": f"5 {unidad}"},
        ],
        footer="O escribe la cantidad exacta (ej: 2.5)",
    )


async def send_mas_productos(to: str, resumen: str):
    """¿Agregar más o confirmar?"""
    await send_buttons(
        to=to,
        body=f"Tu pedido actual:\n{resumen}\n\n¿Qué deseas hacer?",
        buttons=[
            {"id": "mas_agregar", "title": "➕ Agregar más"},
            {"id": "mas_confirmar", "title": "✅ Confirmar"},
            {"id": "cancel_pedido", "title": "❌ Cancelar"},
        ],
    )


async def send_tipo_entrega(to: str):
    """Selección de tipo de entrega."""
    await send_buttons(
        to=to,
        body="¿Cómo deseas recibir tu pedido?",
        buttons=[
            {"id": "entrega_sucursal", "title": "🏪 En sucursal"},
            {"id": "entrega_domicilio", "title": "🛵 A domicilio"},
        ],
    )


async def send_metodo_pago(to: str, total: float):
    """Selección de método de pago."""
    await send_buttons(
        to=to,
        body=f"Total: *${total:.2f}*\n\n¿Cómo deseas pagar?",
        buttons=[
            {"id": "pago_efectivo", "title": "💵 Efectivo"},
            {"id": "pago_link", "title": "💳 Link de pago"},
            {"id": "pago_terminal", "title": "💳 Terminal"},
        ],
    )


async def send_confirmacion_pedido(to: str, resumen: str, folio: str):
    """Confirmación de pedido creado."""
    await send_text(
        to=to,
        text=f"✅ *Pedido confirmado*\n\n"
             f"Folio: *{folio}*\n\n{resumen}\n\n"
             f"Te avisaremos cuando esté listo. 🔔",
    )


async def send_fuera_de_horario(to: str, proximo: str):
    """Aviso de fuera de horario."""
    await send_buttons(
        to=to,
        body=f"⏰ Estamos cerrados en este momento.\n"
             f"Abrimos: *{proximo}*\n\n"
             f"¿Deseas programar un pedido?",
        buttons=[
            {"id": "menu_pedido", "title": "📅 Programar pedido"},
            {"id": "cancel_ok", "title": "No, gracias"},
        ],
    )


async def send_no_entendi(to: str, intentos: int = 0):
    """Fallback — no se entendió el mensaje."""
    if intentos >= 2:
        await send_text(
            to=to,
            text="🤔 No logro entenderte. Te comunico con un asesor.\n"
                 "Un momento por favor...",
        )
    else:
        await send_buttons(
            to=to,
            body="🤔 No entendí tu mensaje. Usa estas opciones:",
            buttons=[
                {"id": "menu_pedido", "title": "🛒 Hacer pedido"},
                {"id": "menu_cotizacion", "title": "📋 Cotización"},
                {"id": "menu_ayuda", "title": "❓ Ayuda"},
            ],
        )
