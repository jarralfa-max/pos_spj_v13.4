from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


CHARS_BY_PAPER_WIDTH = {58: 32, 72: 42, 80: 48}


@dataclass
class TicketItem:
    nombre: str
    cantidad: float
    precio_unitario: float
    total: float
    unidad: str = "pz"


@dataclass
class TicketTotals:
    subtotal: float = 0.0
    descuento: float = 0.0
    total_final: float = 0.0


@dataclass
class TicketPaymentInfo:
    forma_pago: str = ""
    efectivo_recibido: float = 0.0
    cambio: float = 0.0


@dataclass
class TicketBranding:
    brand_name: str = "SPJ POS"
    address: str = ""
    phone: str = ""
    slogan: str = ""
    rfc: str = ""
    logo_b64: str = ""


@dataclass
class TicketLoyaltyInfo:
    puntos_ganados: int = 0
    puntos_totales: int = 0
    nivel: str = ""


@dataclass
class TicketFomoMessage:
    code: str
    message: str
    priority: int = 0


@dataclass
class TicketQRCodeInfo:
    content: str
    enabled: bool = True


@dataclass
class TicketLayoutConfig:
    paper_width_mm: int = 80
    chars_per_line: int = 48
    show_logo: bool = True
    logo_size: str = "md"
    logo_alignment: str = "center"
    show_brand_name: bool = True
    show_slogan: bool = True
    show_address: bool = True
    show_phone: bool = True
    show_rfc: bool = False
    show_customer: bool = True
    show_loyalty: bool = True
    show_fomo: bool = True
    show_qr: bool = True
    show_barcode: bool = False
    cut_type: str = "partial"
    feed_lines: int = 4
    block_order: List[str] = field(default_factory=lambda: [
        "logo", "brand_header", "sale_info", "customer", "items", "totals", "payment", "loyalty", "fomo", "qr", "footer"
    ])

    def __post_init__(self) -> None:
        if self.paper_width_mm in CHARS_BY_PAPER_WIDTH:
            self.chars_per_line = CHARS_BY_PAPER_WIDTH[self.paper_width_mm]


@dataclass
class TicketPrintModel:
    ticket_type: str
    folio: str
    fecha: str
    cajero: str
    cliente_nombre: str
    items: List[TicketItem]
    totals: TicketTotals
    payment: TicketPaymentInfo
    branding: TicketBranding
    loyalty: Optional[TicketLoyaltyInfo] = None
    fomo_messages: List[TicketFomoMessage] = field(default_factory=list)
    qr: Optional[TicketQRCodeInfo] = None
    footer_message: str = ""
    layout: TicketLayoutConfig = field(default_factory=TicketLayoutConfig)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Legacy adapter keys for current renderer/services.
        data["cliente"] = data.pop("cliente_nombre", "")
        data["totales"] = data.pop("totals", {})
        data["pago"] = data.pop("payment", {})
        data["empresa"] = data.get("branding", {}).get("brand_name", "SPJ POS")
        data["direccion"] = data.get("branding", {}).get("address", "")
        data["telefono"] = data.get("branding", {}).get("phone", "")
        loyalty = data.get("loyalty") or {}
        data["puntos_ganados"] = loyalty.get("puntos_ganados", 0)
        data["puntos_totales"] = loyalty.get("puntos_totales", 0)
        if self.qr and self.qr.enabled:
            data["qr_content"] = self.qr.content
        return data

    @classmethod
    def from_dict(cls, src: Dict[str, Any]) -> "TicketPrintModel":
        items = [
            TicketItem(
                nombre=str(it.get("nombre", "")),
                cantidad=float(it.get("cantidad", it.get("qty", 0)) or 0),
                precio_unitario=float(it.get("precio_unitario", it.get("unit_price", 0)) or 0),
                total=float(it.get("total", it.get("subtotal", 0)) or 0),
                unidad=str(it.get("unidad", "pz")),
            )
            for it in (src.get("items") or [])
        ]
        totals_src = src.get("totales") or src.get("totals") or {}
        payment_src = src.get("pago") or src.get("payment") or {}
        branding_src = src.get("branding") or {}
        layout_src = src.get("layout") or {}

        loyalty = None
        if src.get("puntos_ganados") or src.get("puntos_totales"):
            loyalty = TicketLoyaltyInfo(
                puntos_ganados=int(src.get("puntos_ganados", 0) or 0),
                puntos_totales=int(src.get("puntos_totales", 0) or 0),
            )

        qr = None
        qr_content = src.get("qr_content", "")
        if qr_content:
            qr = TicketQRCodeInfo(content=str(qr_content), enabled=True)

        return cls(
            ticket_type=str(src.get("ticket_type", "sale")),
            folio=str(src.get("folio", "")),
            fecha=str(src.get("fecha", "")),
            cajero=str(src.get("cajero", "")),
            cliente_nombre=str(src.get("cliente", src.get("cliente_nombre", ""))),
            items=items,
            totals=TicketTotals(
                subtotal=float(totals_src.get("subtotal", 0) or 0),
                descuento=float(totals_src.get("descuento", 0) or 0),
                total_final=float(totals_src.get("total_final", totals_src.get("subtotal", 0)) or 0),
            ),
            payment=TicketPaymentInfo(
                forma_pago=str(payment_src.get("forma_pago", src.get("forma_pago", ""))),
                efectivo_recibido=float(payment_src.get("efectivo_recibido", 0) or 0),
                cambio=float(payment_src.get("cambio", 0) or 0),
            ),
            branding=TicketBranding(
                brand_name=str(branding_src.get("brand_name", src.get("empresa", "SPJ POS"))),
                address=str(branding_src.get("address", src.get("direccion", ""))),
                phone=str(branding_src.get("phone", src.get("telefono", ""))),
                slogan=str(branding_src.get("slogan", "")),
                rfc=str(branding_src.get("rfc", "")),
                logo_b64=str(branding_src.get("logo_b64", src.get("logo_b64", ""))),
            ),
            loyalty=loyalty,
            qr=qr,
            footer_message=str(src.get("mensaje_psicologico", src.get("footer_message", ""))),
            layout=TicketLayoutConfig(**layout_src) if isinstance(layout_src, dict) else TicketLayoutConfig(),
        )
