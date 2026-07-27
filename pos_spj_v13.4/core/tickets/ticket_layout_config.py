from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from typing import Any, Dict, List

CHARS_BY_PAPER_WIDTH = {58: 32, 72: 42, 80: 48}
DEFAULT_BLOCK_ORDER = [
    "logo", "brand_header", "sale_info", "customer", "items", "totals", "payment", "loyalty", "fomo", "qr", "barcode", "footer", "legal"
]
RAFFLE_BLOCK_ORDER = [
    "logo", "brand_header", "raffle_title", "ticket_number", "customer", "sale_info", "prize", "draw_date", "qr", "barcode", "footer", "legal"
]


@dataclass
class TicketLayoutBlock:
    enabled: bool = True
    order: int = 0
    alignment: str = "left"
    style: str = "normal"
    priority: int = 0


@dataclass
class TicketLayoutConfig:
    paper_width_mm: int = 80
    chars_per_line: int = 48
    show_logo: bool = True
    logo_size: str = "md"
    logo_alignment: str = "center"
    ticket_debug_logo: bool = False
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
    footer_message: str = ""
    legal_message: str = ""
    block_order: List[str] = field(default_factory=lambda: list(DEFAULT_BLOCK_ORDER))
    blocks: Dict[str, TicketLayoutBlock] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.paper_width_mm = int(self.paper_width_mm or 80)
        self.chars_per_line = CHARS_BY_PAPER_WIDTH.get(self.paper_width_mm, int(self.chars_per_line or 48))

        if not self.blocks:
            self.blocks = {
                b: TicketLayoutBlock(enabled=self._default_block_enabled(b), order=i)
                for i, b in enumerate(self.block_order)
            }
        else:
            # Ensure every configured block has an order and every ordered name has a block config.
            # Missing per-block settings must inherit the global show_* flags so compact
            # layouts from Ticket Design such as {"show_barcode": true} still render.
            for i, name in enumerate(self.block_order):
                self.blocks.setdefault(name, TicketLayoutBlock(enabled=self._default_block_enabled(name), order=i))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["blocks"] = {k: asdict(v) for k, v in self.blocks.items()}
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TicketLayoutConfig":
        data = dict(data or {})
        valid = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in valid and k != "blocks"}
        obj = cls(**kwargs)
        raw_blocks = data.get("blocks") or {}
        if raw_blocks:
            obj.blocks = {}
            for k, v in raw_blocks.items():
                if isinstance(v, TicketLayoutBlock):
                    obj.blocks[k] = v
                elif isinstance(v, dict):
                    valid_block = {f.name for f in fields(TicketLayoutBlock)}
                    obj.blocks[k] = TicketLayoutBlock(**{bk: bv for bk, bv in v.items() if bk in valid_block})
                else:
                    obj.blocks[k] = TicketLayoutBlock()
            for i, name in enumerate(obj.block_order):
                obj.blocks.setdefault(name, TicketLayoutBlock(enabled=obj._default_block_enabled(name), order=i))
        return obj

    def _default_block_enabled(self, block_name: str) -> bool:
        flag_map = {
            "logo": self.show_logo,
            "brand_header": self.show_brand_name,
            "customer": self.show_customer,
            "loyalty": self.show_loyalty,
            "fomo": self.show_fomo,
            "qr": self.show_qr,
            "barcode": self.show_barcode,
        }
        return bool(flag_map.get(block_name, True))

    @classmethod
    def for_layout_type(cls, layout_type: str = "sale_ticket") -> "TicketLayoutConfig":
        if str(layout_type or "sale_ticket") == "raffle_ticket":
            cfg = cls(
                block_order=list(RAFFLE_BLOCK_ORDER),
                show_loyalty=False,
                show_fomo=False,
                show_qr=True,
                show_barcode=True,
                footer_message="Gracias por participar",
                legal_message="Conserve este boleto para reclamar su premio.",
            )
            cfg.blocks = {b: TicketLayoutBlock(enabled=True, order=i) for i, b in enumerate(RAFFLE_BLOCK_ORDER)}
            return cfg
        return cls()

    @classmethod
    def from_legacy_config(cls, legacy: Dict[str, Any]) -> "TicketLayoutConfig":
        paper_w = int(legacy.get("ticket_paper_width", 80) or 80)
        logo_pos = str(legacy.get("ticket_logo_pos", "Centrado"))
        pos_map = {"Centrado": "center", "Izquierda": "left", "Derecha": "right"}
        cfg = cls(
            paper_width_mm=paper_w,
            show_qr=str(legacy.get("ticket_qr_enabled", "0")) == "1",
            show_barcode=str(legacy.get("ticket_bc_enabled", "0")) == "1",
            logo_alignment=pos_map.get(logo_pos, "center"),
            logo_size=str(legacy.get("ticket_logo_width", "150")),
        )
        if "barcode" in cfg.blocks:
            cfg.blocks["barcode"].enabled = cfg.show_barcode
        if "qr" in cfg.blocks:
            cfg.blocks["qr"].enabled = cfg.show_qr
        return cfg
