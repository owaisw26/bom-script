"""Map validated source items into Odoo's product and BoM records."""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from .models import OdooBom, OdooBomLine, OdooProduct, SourceItem
from .validator import ValidationResult, identity


DEFAULT_SPEEDPAK_SUFFIX = re.compile(r"\s*\(\s*default_speedpak\s*\)\s*$", re.IGNORECASE)


def product_name(item: SourceItem) -> str:
    """Return the user-facing title without 3DEXPERIENCE representation metadata."""
    return DEFAULT_SPEEDPAK_SUFFIX.sub("", item.title).strip()


def sanitise(value: str) -> str:
    """Make a stable External ID suffix from a 3DEXPERIENCE identifier."""
    value = re.sub(r"[\s-]+", "_", value.strip())
    value = re.sub(r"[^A-Za-z0-9_]", "", value)
    return re.sub(r"_+", "_", value).strip("_")


def product_external_id(item: SourceItem) -> str:
    return "3dx_product_" + sanitise(identity(item))


def product_internal_reference(item: SourceItem) -> str:
    """Return the unique reference Odoo exposes on the product variant."""
    return item.enterprise_item_number or f"3DX-{item.name}"


def _decimal_value(value: Decimal) -> int | float:
    """Keep whole quantities tidy in Excel while preserving fractional quantities."""
    return int(value) if value == value.to_integral_value() else float(value)


def transform(result: ValidationResult, *, product_type: str, bom_type: str,
              default_uom: str) -> tuple[list[OdooProduct], list[OdooBom]]:
    """Create deduplicated products and one BoM for every parent with children."""
    items_by_row = {item.row_number: item for item in result.items}
    products_by_identity: dict[str, OdooProduct] = {}
    component_rows = {item.row_number for item in result.items if item.parent_row_number is not None}

    for item in result.items:
        key = identity(item)
        if key not in products_by_identity:
            products_by_identity[key] = OdooProduct(
                external_id=product_external_id(item), name=product_name(item),
                internal_reference=product_internal_reference(item),
                product_type=product_type, can_be_sold=False,
                # Only a Level 0-only record is an assembly-only product.
                can_be_purchased=item.level > 0, uom=default_uom, purchase_uom=default_uom,
            )
        elif item.row_number in component_rows:
            products_by_identity[key].can_be_purchased = True

    # A root product may be seen first, then later re-used as a component.
    for item in result.items:
        if item.row_number in component_rows:
            products_by_identity[identity(item)].can_be_purchased = True

    children: dict[int, list[SourceItem]] = defaultdict(list)
    for item in result.items:
        if item.parent_row_number in items_by_row:
            children[item.parent_row_number].append(item)

    boms: list[OdooBom] = []
    for parent_row, child_items in children.items():
        parent = items_by_row[parent_row]
        combined: dict[str, Decimal] = defaultdict(Decimal)
        for child in child_items:
            combined[product_internal_reference(child)] += result.quantities[child.row_number]
        lines = [OdooBomLine(component_reference, quantity, default_uom)
                 for component_reference, quantity in sorted(combined.items())]
        reference = f"{parent.enterprise_item_number or parent.title} - Rev {parent.revision}"
        boms.append(OdooBom(
            external_id=f"3dx_bom_{sanitise(identity(parent))}_{sanitise(parent.revision)}",
            product_external_id=product_external_id(parent), product_quantity=Decimal("1"),
            bom_type=bom_type, reference=reference, lines=lines,
        ))
    return list(products_by_identity.values()), boms


def product_rows(products: list[OdooProduct]) -> list[list[object]]:
    return [[p.external_id, p.name, p.internal_reference, p.product_type, str(p.can_be_sold),
             str(p.can_be_purchased), p.uom, p.purchase_uom] for p in products]


def bom_rows(boms: list[OdooBom]) -> list[list[object]]:
    rows: list[list[object]] = []
    for bom in boms:
        for line in bom.lines:
            rows.append([bom.external_id, bom.product_external_id, _decimal_value(bom.product_quantity),
                         bom.bom_type, line.component_internal_reference, _decimal_value(line.quantity),
                         line.uom, bom.reference])
    return rows
