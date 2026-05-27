from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

CHARS_BY_PAPER_WIDTH = {58: 32, 72: 42, 80: 48}
DEFAULT_BLOCK_ORDER = [
    "logo", "brand_header", "sale_info", "customer", "items", "totals", "payment", "loyalty", "fomo", "qr", "barcode", "footer", "legal"
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
    block_order: List[str] = field(default_factory=lambda: list(DEFAULT_BLOCK_ORDER))
    blocks: Dict[str, TicketLayoutBlock] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.chars_per_line = CHARS_BY_PAPER_WIDTH.get(self.paper_width_mm, self.chars_per_line)
        if not self.blocks:
            self.blocks = {
                b: TicketLayoutBlock(enabled=(b not in {"barcode"}), order=i)
                for i, b in enumerate(self.block_order)
            }

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["blocks"] = {k: asdict(v) for k, v in self.blocks.items()}
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TicketLayoutConfig":
        obj = cls(**{k: v for k, v in (data or {}).items() if k != "blocks"})
        raw_blocks = (data or {}).get("blocks") or {}
        if raw_blocks:
            obj.blocks = {k: TicketLayoutBlock(**v) if isinstance(v, dict) else TicketLayoutBlock() for k, v in raw_blocks.items()}
        return obj

    @classmethod
    def from_legacy_config(cls, legacy: Dict[str, Any]) -> "TicketLayoutConfig":
        paper_w = int(legacy.get("ticket_paper_width", 80) or 80)
        logo_pos = str(legacy.get("ticket_logo_pos", "Centrado"))
        pos_map = {"Centrado": "center", "Izquierda": "left", "Derecha": "right"}
        return cls(
            paper_width_mm=paper_w,
            show_qr=str(legacy.get("ticket_qr_enabled", "0")) == "1",
            show_barcode=str(legacy.get("ticket_bc_enabled", "0")) == "1",
            logo_alignment=pos_map.get(logo_pos, "center"),
            logo_size=str(legacy.get("ticket_logo_width", "150")),
        )
