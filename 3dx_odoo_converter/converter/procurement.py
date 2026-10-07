"""Add approved, manually specified purchased parts to released installations."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import OdooBom, OdooBomLine, OdooProduct
from .transformer import product_internal_reference, sanitise
from .validator import ValidationResult

HEADERS = {"Project ID", "Parent Reference", "Internal Reference", "Name", "Quantity", "Unit of Measure", "Status"}


@dataclass
class ProcurementResult:
    rows: list[list[object]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exported: int = 0


def merge_procurement(path: Path, project_id: str, validation: ValidationResult,
                      products: list[OdooProduct], boms: list[OdooBom],
                      product_type: str, bom_type: str) -> ProcurementResult:
    """Only Ready items attached to a fully released parent enter Odoo imports."""
    result = ProcurementResult()
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = HEADERS - set(reader.fieldnames or [])
        if missing:
            result.errors.append("Procurement CSV missing column(s): " + ", ".join(sorted(missing)))
            return result
        source_rows = list(enumerate(reader, start=2))

    included = {product_internal_reference(item): item for item in validation.items}
    product_by_ref = {product.internal_reference: product for product in products}
    bom_by_parent = {bom.product_external_id: bom for bom in boms}
    seen_manual_ids: dict[str, str] = {}
    seen_manual_refs: dict[str, tuple[str, str]] = {}

    for row_number, raw in source_rows:
        row = {key: (value or "").strip() for key, value in raw.items() if key}
        label = f"Procurement row {row_number}"
        reference = row["Internal Reference"]
        parent_ref = row["Parent Reference"]
        name = row["Name"]
        uom = row["Unit of Measure"]
        status = row["Status"].casefold()
        disposition = "Held"
        detail = ""
        external_id = ""
        if row["Project ID"] != project_id:
            detail = "Project ID does not match --project-id"
        elif not reference or not name or not uom:
            detail = "Internal Reference, Name and Unit of Measure are required"
        elif status not in {"draft", "ready"}:
            detail = "Status must be Draft or Ready"
        else:
            try:
                quantity = Decimal(row["Quantity"])
                if not quantity.is_finite() or quantity <= 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                detail = "Quantity must be a positive finite number"
            else:
                if status == "draft":
                    detail = "Draft item; awaiting procurement approval"
                elif not parent_ref:
                    detail = "No Parent Reference; item stays in the manual register"
                elif parent_ref not in included:
                    detail = "Parent is absent from the fully Released 3DX export"
                elif reference in included:
                    detail = "Internal Reference already belongs to a 3DX product"
                else:
                    suffix = sanitise(project_id) + "_" + sanitise(reference)
                    external_id = "manual_product_" + suffix
                    previous_ref = seen_manual_ids.get(external_id)
                    previous_details = seen_manual_refs.get(reference)
                    if not sanitise(project_id) or not sanitise(reference) or previous_ref not in (None, reference):
                        detail = "Generated External ID is empty or collides with another item"
                    elif previous_details not in (None, (name, uom)):
                        detail = "Internal Reference has conflicting Name or Unit of Measure"
                    else:
                        seen_manual_ids[external_id] = reference
                        seen_manual_refs[reference] = (name, uom)
                        if reference not in product_by_ref:
                            product = OdooProduct(external_id, name, reference, product_type,
                                                  False, True, uom, uom)
                            products.append(product)
                            product_by_ref[reference] = product
                        parent = included[parent_ref]
                        parent_product = product_by_ref[parent_ref]
                        bom = bom_by_parent.get(parent_product.external_id)
                        if bom is None:
                            bom_id = (f"3dx_bom_{sanitise(parent.enterprise_item_number or parent.name)}"
                                      f"_{sanitise(parent.revision)}")
                            bom = OdooBom(bom_id, parent_product.external_id, Decimal("1"),
                                          bom_type, f"{parent.enterprise_item_number or parent.title} - Rev {parent.revision}")
                            boms.append(bom)
                            bom_by_parent[parent_product.external_id] = bom
                        line_id = f"{bom.external_id}_line_{sanitise(reference)}"
                        line = next((line for line in bom.lines if line.external_id == line_id), None)
                        if line and line.component_internal_reference != reference:
                            detail = "BoM line ID collides with another component"
                        elif line:
                            line.quantity += quantity
                        else:
                            bom.lines.append(OdooBomLine(line_id, reference, quantity, uom))
                        if not detail:
                            disposition = "Exported"
                            detail = "Added to released parent BoM"
                            result.exported += 1
        if detail and disposition != "Exported" and detail not in {
            "Draft item; awaiting procurement approval", "No Parent Reference; item stays in the manual register",
            "Parent is absent from the fully Released 3DX export"
        }:
            result.errors.append(f"{label}: {detail}")
        result.rows.append([row_number, row["Project ID"], parent_ref, reference, name,
                            row["Quantity"], uom, row["Status"], disposition, detail, external_id])
    return result
