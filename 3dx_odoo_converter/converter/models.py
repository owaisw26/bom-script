"""Small, typed data structures shared by the converter modules."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class SourceItem:
    row_number: int
    source_row: dict[str, str]
    level: int
    title: str
    enterprise_item_number: str
    revision: str
    name: str
    maturity_state: str
    parent_row_number: int | None = None


@dataclass
class OdooProduct:
    external_id: str
    name: str
    internal_reference: str
    product_type: str
    can_be_sold: bool
    can_be_purchased: bool
    uom: str
    purchase_uom: str


@dataclass
class OdooBomLine:
    component_external_id: str
    quantity: Decimal
    uom: str


@dataclass
class OdooBom:
    external_id: str
    product_external_id: str
    product_quantity: Decimal
    bom_type: str
    reference: str
    lines: list[OdooBomLine] = field(default_factory=list)


@dataclass
class ValidationWarning:
    row_number: int | None
    message: str


@dataclass
class RejectedRow:
    row_number: int | None
    source_row: dict[str, str]
    reason: str


@dataclass
class ParsedSource:
    source_filename: str
    fieldnames: list[str]
    items: list[SourceItem]
    rejected_rows: list[RejectedRow]
    errors: list[str]
