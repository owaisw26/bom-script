from pathlib import Path

from openpyxl import Workbook

from converter.models import OdooBom, OdooProduct
from converter.reconciler import ExistingProduct, load_existing_products, reconcile_existing_products


def product(name: str, reference: str, external_id: str) -> OdooProduct:
    return OdooProduct(external_id, name, reference, "Goods", False, False, "Units", "Units")


def test_existing_products_can_be_loaded_from_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "existing_products.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["External ID", "Name", "Internal Reference"])
    sheet.append(["__export__.product_template_42", "Assembly", "ASM-42"])
    workbook.save(path)

    products = load_existing_products(path, {
        "external_id": "External ID", "name": "Name", "internal_reference": "Internal Reference",
    })

    assert products == [ExistingProduct("__export__.product_template_42", "Assembly", "ASM-42", 2)]


def test_odoo_technical_export_headers_are_supported(tmp_path: Path) -> None:
    path = tmp_path / "odoo_export.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["id", "name", "default_code", "id"])
    sheet.append([
        "__import__.3dx_product_prd_root", "Assembly", "3DX-prd-root",
        "__import__.3dx_product_prd_root",
    ])
    workbook.save(path)

    products = load_existing_products(path, {
        "external_id": "External ID", "name": "Name", "internal_reference": "Internal Reference",
    })

    assert products == [ExistingProduct(
        "__import__.3dx_product_prd_root", "Assembly", "3DX-prd-root", 2,
    )]


def test_existing_assembly_external_id_is_reused_in_product_and_bom() -> None:
    products = [product("Assembly", "3DX-prd-root", "3dx_product_prd_root")]
    boms = [OdooBom("3dx_bom_root_A1", "3dx_product_prd_root", 1, "Manufacture this product",
                    "Assembly - Rev A.1")]
    existing = [ExistingProduct("__export__.product_template_42", "Assembly", "", 2)]

    result = reconcile_existing_products(products, boms, existing)

    assert result.errors == []
    assert result.matched_products == 1
    assert result.matched_assemblies == 1
    assert products[0].external_id == "__export__.product_template_42"
    assert boms[0].product_external_id == "__export__.product_template_42"


def test_missing_existing_assembly_is_an_error() -> None:
    products = [product("Assembly", "ASM-1", "3dx_product_ASM_1")]
    boms = [OdooBom("3dx_bom_ASM_1_A1", "3dx_product_ASM_1", 1, "Manufacture this product",
                    "ASM-1 - Rev A.1")]
    existing = [ExistingProduct("__export__.product_template_9", "Other Assembly", "ASM-9", 2)]

    result = reconcile_existing_products(products, boms, existing)

    assert result.matched_products == 0
    assert result.matched_assemblies == 0
    assert "refusing to create a duplicate" in result.errors[0]


def test_internal_reference_match_takes_priority_and_conflicts_are_rejected() -> None:
    products = [product("Assembly", "ASM-1", "3dx_product_ASM_1")]
    boms = [OdooBom("3dx_bom_ASM_1_A1", "3dx_product_ASM_1", 1, "Manufacture this product",
                    "ASM-1 - Rev A.1")]
    existing = [
        ExistingProduct("__export__.product_template_1", "Renamed Assembly", "ASM-1", 2),
        ExistingProduct("__export__.product_template_2", "Assembly", "ASM-2", 3),
    ]

    result = reconcile_existing_products(products, boms, existing)

    assert "matches different Odoo stubs" in result.errors[0]
