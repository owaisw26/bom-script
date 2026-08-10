import subprocess
import sys
from pathlib import Path

from openpyxl import load_workbook


PROJECT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT.parent / "ASM-DOORS INSTALLATION.csv"


def test_supplied_csv_converts_to_expected_workbooks(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "convert_3dx_to_odoo.py", str(SAMPLE), "--output-dir", str(tmp_path)],
        cwd=PROJECT, text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Products created: 5" in completed.stdout
    products = load_workbook(tmp_path / "odoo_products_import.xlsx").active
    boms = load_workbook(tmp_path / "odoo_bom_import.xlsx").active
    report = load_workbook(tmp_path / "conversion_report.xlsx")
    assert products.title == "Products"
    assert boms.title == "Bills of Materials"
    assert products.max_row == 6
    assert boms.max_row == 5
    assert products[1][0].value == "External ID"
    assert [cell.value for cell in boms[1]] == [
        "External ID", "Product/External ID", "Quantity", "BoM Type",
        "BoM Lines/Component", "BoM Lines/Quantity",
        "BoM Lines/Unit", "Reference",
    ]
    product_references = {row[2] for row in products.iter_rows(min_row=2, values_only=True)}
    component_references = {row[4] for row in boms.iter_rows(min_row=2, values_only=True)}
    assert component_references <= product_references
    assert list(products.tables) == ["ProductsImport"]
    assert list(boms.tables) == ["BillsOfMaterialsImport"]
    assert report.sheetnames == ["Summary", "Warnings", "Rejected Rows", "Source Mapping"]
