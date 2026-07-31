#!/usr/bin/env python3
"""Command-line entry point for converting a 3DEXPERIENCE structure CSV."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from converter.odoo_writer import BOM_KEYS, PRODUCT_KEYS, load_mapping, write_import_workbook
from converter.parser import parse_csv
from converter.report_writer import write_report
from converter.transformer import bom_rows, product_rows, transform
from converter.validator import validate


def positive_decimal(value: str) -> Decimal:
    """argparse converter that rejects zero and negative defaults early."""
    try:
        decimal = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if decimal <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return decimal


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a 3DEXPERIENCE product-structure CSV to Odoo XLSX imports."
    )
    parser.add_argument("input_csv", type=Path, help="3DEXPERIENCE CSV export")
    parser.add_argument("--output-dir", type=Path, default=Path("."), help="Directory for generated files")
    parser.add_argument("--released-only", action="store_true", help="Import only Released records")
    parser.add_argument("--default-quantity", type=positive_decimal, default=Decimal("1"))
    parser.add_argument("--quantity-column", help="Optional source column containing component quantities")
    parser.add_argument("--default-uom", default="Units")
    parser.add_argument("--product-type", default="Goods")
    parser.add_argument("--bom-type", default="Manufacture this product")
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
    try:
        mapping = load_mapping(args.field_mapping)
    except (OSError, ValueError, KeyError) as error:
        print(f"Error: invalid field mapping: {error}", file=sys.stderr)
        return 2

    parsed = parse_csv(args.input_csv)
    result = validate(
        parsed, released_only=args.released_only, quantity_column=args.quantity_column,
        default_quantity=args.default_quantity,
    )
    # Transforming valid data lets the report show useful counts even on an atomic failure.
    products, boms = transform(result, product_type=args.product_type, bom_type=args.bom_type,
                               default_uom=args.default_uom)
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
        warnings=result.warnings, rejected_rows=result.rejected_rows, source_headers=parsed.fieldnames,
        product_mapping=mapping["product"], bom_mapping=mapping["bom"],
    )

    if result.errors:
        print("Conversion failed. No Odoo import files were created.", file=sys.stderr)
        for error in dict.fromkeys(result.errors):
            print(f"- {error}", file=sys.stderr)
        print(f"Report: {report_path}", file=sys.stderr)
        return 1

    write_import_workbook(args.output_dir / "odoo_products_import.xlsx", "Products",
                          [mapping["product"][key] for key in PRODUCT_KEYS],
                          product_rows(products), "ProductsImport")
    write_import_workbook(args.output_dir / "odoo_bom_import.xlsx", "Bills of Materials",
                          [mapping["bom"][key] for key in BOM_KEYS],
                          bom_rows(boms), "BillsOfMaterialsImport")
    print("\\nConversion completed.\\n")
    print(f"Products created: {len(products)}")
    print(f"BoMs created: {len(boms)}")
    print(f"BoM component lines: {sum(len(bom.lines) for bom in boms)}")
    print(f"Warnings: {len(result.warnings)}")
    print(f"Rejected rows: {len(result.rejected_rows)}\\n")
    print("Files:")
    print("- odoo_products_import.xlsx")
    print("- odoo_bom_import.xlsx")
    print("- conversion_report.xlsx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
