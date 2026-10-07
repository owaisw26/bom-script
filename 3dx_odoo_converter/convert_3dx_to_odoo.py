#!/usr/bin/env python3
"""Command-line entry point for converting a 3DEXPERIENCE structure CSV."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from converter.odoo_writer import (BOM_KEYS, PRODUCT_KEYS, load_mapping, write_import_csv,
                                   write_import_workbook)
from converter.parser import parse_csv
from converter.procurement import merge_procurement
from converter.reconciler import load_existing_products, reconcile_existing_products
from converter.report_writer import write_report
from converter.transformer import bom_rows, product_rows, transform
from converter.validator import validate


def positive_decimal(value: str) -> Decimal:
    """argparse converter that rejects zero and negative defaults early."""
    try:
        decimal = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not decimal.is_finite() or decimal <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return decimal


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a 3DEXPERIENCE product-structure CSV to Odoo XLSX imports."
    )
    parser.add_argument("input_csv", type=Path, help="3DEXPERIENCE CSV export")
    parser.add_argument("--output-dir", type=Path, default=Path("."), help="Directory for generated files")
    parser.add_argument("--released-only", action="store_true", help="Kept for compatibility; release gating is now the default")
    parser.add_argument("--project-id", help="Project identifier written to the audit report and BoM reference")
    parser.add_argument("--procurement-csv", type=Path,
                        help="Manual purchased parts CSV; requires --project-id")
    parser.add_argument("--default-quantity", type=positive_decimal, default=Decimal("1"))
    parser.add_argument("--quantity-column", help="Optional source column containing component quantities")
    parser.add_argument("--default-uom", default="Units")
    parser.add_argument("--product-type", default="Goods")
    parser.add_argument("--bom-type", default="Manufacture this product")
    parser.add_argument(
        "--existing-products", type=Path,
        help=("Odoo product export (.csv or .xlsx) containing External ID plus Name and/or "
              "Internal Reference. Existing assemblies are updated instead of duplicated."),
    )
    parser.add_argument(
        "--field-mapping", type=Path,
        default=Path(__file__).with_name("odoo_field_mapping.json"),
        help="Path to the configurable Odoo field-header mapping JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if not args.input_csv.is_file():
        print(f"Error: input CSV not found: {args.input_csv}", file=sys.stderr)
        return 2
    if args.existing_products and not args.existing_products.is_file():
        print(f"Error: existing-products export not found: {args.existing_products}", file=sys.stderr)
        return 2
    if args.procurement_csv and (not args.procurement_csv.is_file() or not args.project_id):
        print("Error: --procurement-csv requires an existing file and --project-id", file=sys.stderr)
        return 2
    try:
        mapping = load_mapping(args.field_mapping)
    except (OSError, ValueError, KeyError) as error:
        print(f"Error: invalid field mapping: {error}", file=sys.stderr)
        return 2

    parsed = parse_csv(args.input_csv)
    result = validate(
        parsed, released_only=True, quantity_column=args.quantity_column,
        default_quantity=args.default_quantity,
    )
    # Transforming valid data lets the report show useful counts even on an atomic failure.
    products, boms = transform(result, product_type=args.product_type, bom_type=args.bom_type,
                               default_uom=args.default_uom)
    procurement_rows: list[list[object]] = []
    procurement_exported = 0
    if args.procurement_csv and args.project_id:
        procurement = merge_procurement(args.procurement_csv, args.project_id, result,
                                        products, boms, args.product_type, args.bom_type)
        procurement_rows = procurement.rows
        procurement_exported = procurement.exported
        result.errors.extend(procurement.errors)
    if args.project_id:
        for bom in boms:
            bom.reference = f"{args.project_id} | {bom.reference}"
    matched_existing_products = 0
    matched_existing_assemblies = 0
    if args.existing_products:
        try:
            existing_products = load_existing_products(args.existing_products, mapping["product"])
            reconciliation = reconcile_existing_products(products, boms, existing_products)
        except (OSError, ValueError) as error:
            result.errors.append(f"Invalid existing-products export: {error}")
        else:
            matched_existing_products = reconciliation.matched_products
            matched_existing_assemblies = reconciliation.matched_assemblies
            result.warnings.extend(reconciliation.warnings)
            result.errors.extend(reconciliation.errors)
    source_rows = len(parsed.items) + len(parsed.rejected_rows)
    non_released = sum(item.maturity_state != "Released" for item in parsed.items)
    missing_item_numbers = sum(not item.enterprise_item_number for item in parsed.items)
    assumed_quantities = sum("Quantity missing; assumed" in warning.message for warning in result.warnings)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "conversion_report.xlsx"
    write_report(
        report_path, source_filename=parsed.source_filename, source_rows=source_rows,
        assemblies=sum(item.level == 0 for item in result.items), products=len(products),
        component_lines=sum(len(bom.lines) for bom in boms), missing_item_numbers=missing_item_numbers,
        assumed_quantities=assumed_quantities, non_released=non_released,
        matched_existing_products=matched_existing_products,
        matched_existing_assemblies=matched_existing_assemblies,
        warnings=result.warnings, rejected_rows=result.rejected_rows, source_headers=parsed.fieldnames,
        product_mapping=mapping["product"], bom_mapping=mapping["bom"],
        project_id=args.project_id or "", procurement_rows=procurement_rows,
        procurement_exported=procurement_exported,
    )

    if result.errors:
        for filename in ("odoo_products_import.xlsx", "odoo_bom_import.xlsx",
                         "odoo_products_import.csv", "odoo_bom_import.csv"):
            (args.output_dir / filename).unlink(missing_ok=True)
        print("Conversion failed. No Odoo import files were created.", file=sys.stderr)
        for error in dict.fromkeys(result.errors):
            print(f"- {error}", file=sys.stderr)
        print(f"Report: {report_path}", file=sys.stderr)
        return 1

    product_headers = [mapping["product"][key] for key in PRODUCT_KEYS]
    bom_headers = [mapping["bom"][key] for key in BOM_KEYS]
    product_data = product_rows(products)
    bom_data = bom_rows(boms)
    write_import_workbook(args.output_dir / "odoo_products_import.xlsx", "Products",
                          product_headers, product_data, "ProductsImport")
    write_import_workbook(args.output_dir / "odoo_bom_import.xlsx", "Bills of Materials",
                          bom_headers, bom_data, "BillsOfMaterialsImport")
    write_import_csv(args.output_dir / "odoo_products_import.csv", product_headers, product_data)
    write_import_csv(args.output_dir / "odoo_bom_import.csv", bom_headers, bom_data)
    print("\nConversion completed.\n")
    print(f"Product rows exported: {len(products)}")
    print(f"BoMs created: {len(boms)}")
    print(f"BoM component lines: {sum(len(bom.lines) for bom in boms)}")
    print(f"Manual procurement rows exported: {procurement_exported}")
    print(f"Existing products matched: {matched_existing_products}")
    print(f"Existing assemblies matched: {matched_existing_assemblies}")
    print(f"Warnings: {len(result.warnings)}")
    print(f"Rejected rows: {len(result.rejected_rows)}\n")
    print("Files:")
    print("- odoo_products_import.xlsx")
    print("- odoo_bom_import.xlsx")
    print("- odoo_products_import.csv")
    print("- odoo_bom_import.csv")
    print("- conversion_report.xlsx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
