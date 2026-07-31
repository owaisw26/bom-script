"""Validation, release filtering, and quantity interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .models import ParsedSource, RejectedRow, SourceItem, ValidationWarning
from .parser import clean


@dataclass
class ValidationResult:
    items: list[SourceItem]
    quantities: dict[int, Decimal]
    warnings: list[ValidationWarning]
    rejected_rows: list[RejectedRow]
    errors: list[str]


def identity(item: SourceItem) -> str:
    """Return the documented product identity priority."""
    return item.enterprise_item_number or item.name or " ".join(item.title.lower().split())


def _sanitised_identifier(value: str) -> str:
    """Mirror the transformer's ID-safe character rule without importing it."""
    import re
    value = re.sub(r"[\s-]+", "_", value.strip())
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_]", "", value)).strip("_")


def _quantity(item: SourceItem, column: str | None, default: Decimal,
              warnings: list[ValidationWarning], rejected: list[RejectedRow]) -> Decimal | None:
    value = clean(item.source_row.get(column, "")) if column else ""
    if not value:
        warnings.append(ValidationWarning(item.row_number, "Quantity missing; assumed quantity " + str(default)))
        return default
    try:
        quantity = Decimal(value)
        if quantity <= 0:
            raise InvalidOperation
        return quantity
    except InvalidOperation:
        rejected.append(RejectedRow(item.row_number, item.source_row, "Quantity must be a positive number"))
        return None


def validate(parsed: ParsedSource, *, released_only: bool, quantity_column: str | None,
             default_quantity: Decimal) -> ValidationResult:
    """Validate source records. Errors prevent import workbooks from being written."""
    warnings: list[ValidationWarning] = []
    rejected = list(parsed.rejected_rows)
    errors = list(parsed.errors)
    if default_quantity <= 0:
        errors.append("Default quantity must be a positive number")
    if quantity_column and quantity_column not in parsed.fieldnames:
        errors.append(f"Configured quantity column '{quantity_column}' is not present in the CSV")

    excluded_rows: set[int] = set()
    roots = [item for item in parsed.items if item.level == 0]
    if released_only:
        for root in roots:
            if root.maturity_state != "Released":
                errors.append(f"Parent assembly on row {root.row_number} is not Released")
        for item in parsed.items:
            parent_excluded = item.parent_row_number in excluded_rows
            if item.maturity_state != "Released":
                excluded_rows.add(item.row_number)
                if item.level > 0:
                    warnings.append(ValidationWarning(item.row_number, "Item is not released; component excluded"))
            elif parent_excluded:
                excluded_rows.add(item.row_number)
                warnings.append(ValidationWarning(item.row_number, "Item excluded because its parent is not released"))
    else:
        for item in parsed.items:
            if item.maturity_state != "Released":
                warnings.append(ValidationWarning(item.row_number, "Item is not released"))

    items = [item for item in parsed.items if item.row_number not in excluded_rows]
    for item in items:
        if not item.enterprise_item_number:
            warnings.append(ValidationWarning(
                item.row_number, "Enterprise Item Number missing; used 3DX Name as fallback"
            ))
    grouped: dict[str, SourceItem] = {}
    for item in items:
        key = identity(item)
        existing = grouped.get(key)
        if existing and (existing.title != item.title or existing.revision != item.revision):
            errors.append(f"Conflicting name or revision for product identity '{key}'")
            for conflict in (existing, item):
                rejected.append(RejectedRow(conflict.row_number, conflict.source_row,
                    f"Conflicting product identity '{key}'"))
        else:
            grouped[key] = item

    external_ids: dict[str, str] = {}
    internal_references: dict[str, str] = {}
    for key, item in grouped.items():
        external_id = "3dx_product_" + _sanitised_identifier(key)
        internal_reference = item.enterprise_item_number or f"3DX-{item.name}"
        for label, value, seen in (
            ("External ID", external_id, external_ids),
            ("Internal Reference", internal_reference, internal_references),
        ):
            other = seen.get(value)
            if other is not None and other != key:
                errors.append(f"Generated {label} '{value}' is not unique")
            else:
                seen[value] = key

    quantities: dict[int, Decimal] = {}
    for item in items:
        if item.level > 0:
            quantity = _quantity(item, quantity_column, default_quantity, warnings, rejected)
            if quantity is not None:
                quantities[item.row_number] = quantity

    duplicate_components: dict[tuple[int, str], list[SourceItem]] = {}
    for item in items:
        if item.parent_row_number is not None:
            duplicate_components.setdefault((item.parent_row_number, identity(item)), []).append(item)
    for duplicates in duplicate_components.values():
        if len(duplicates) > 1:
            warnings.append(ValidationWarning(
                duplicates[0].row_number,
                f"Duplicate component rows combined ({len(duplicates)} occurrences)",
            ))

    by_row = {item.row_number: item for item in items}
    for item in items:
        if item.parent_row_number is not None and item.parent_row_number in by_row:
            if identity(item) == identity(by_row[item.parent_row_number]):
                errors.append(f"Component on row {item.row_number} references itself")
                rejected.append(RejectedRow(item.row_number, item.source_row, "Component cannot reference itself"))

    if rejected:
        errors.append("One or more source rows were rejected")
    return ValidationResult(items, quantities, warnings, rejected, errors)
