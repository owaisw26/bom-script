from decimal import Decimal
from pathlib import Path

from converter.parser import parse_csv
from converter.transformer import (
    bom_rows,
    product_external_id,
    product_internal_reference,
    product_name,
    transform,
)
from converter.validator import validate


def test_ids_are_stable_and_duplicates_are_combined(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text(
        "Level,Title,Enterprise Item Number,Revision,Maturity State,Name\n"
        "0,Assembly,None,A.1,Released,prd-root\n"
        "1,Part,CMP-1,A.1,Released,prd-part\n"
        "1,Part,CMP-1,A.1,Released,prd-part\n", encoding="utf-8"
    )
    parsed = parse_csv(source)
    result = validate(parsed, released_only=False, quantity_column=None, default_quantity=Decimal("1"))
    products, boms = transform(result, product_type="Goods", bom_type="Manufacture this product",
                               default_uom="Units")
    assert product_external_id(parsed.items[0]) == "3dx_product_prd_root"
    assert product_internal_reference(parsed.items[1]) == "CMP-1"
    assert len(products) == 2
    assert len(boms) == 1
    assert bom_rows(boms)[0][4] == "3dx_bom_prd_root_A1_line_CMP_1"
    assert bom_rows(boms)[0][5] == "CMP-1"
    assert bom_rows(boms)[0][6] == 2


def test_missing_engineering_number_uses_name_reference(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text(
        "Level,Title,Enterprise Item Number,Revision,Maturity State,Name\n"
        "0,Assembly,None,A.1,Released,prd-root\n", encoding="utf-8"
    )
    parsed = parse_csv(source)
    result = validate(parsed, released_only=False, quantity_column=None, default_quantity=Decimal("1"))
    products, _ = transform(result, product_type="Goods", bom_type="Manufacture this product",
                            default_uom="Units")
    assert products[0].internal_reference == "3DX-prd-root"
    assert product_internal_reference(parsed.items[0]) == "3DX-prd-root"


def test_default_speedpak_suffix_is_removed_from_product_name(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text(
        "Level,Title,Enterprise Item Number,Revision,Maturity State,Name\n"
        "0,ASM-OCCUPANT CELL(Default_speedpak),None,A.1,Released,prd-root\n",
        encoding="utf-8",
    )
    parsed = parse_csv(source)
    result = validate(parsed, released_only=False, quantity_column=None, default_quantity=Decimal("1"))
    products, _ = transform(result, product_type="Goods", bom_type="Manufacture this product",
                            default_uom="Units")

    assert product_name(parsed.items[0]) == "ASM-OCCUPANT CELL"
    assert products[0].name == "ASM-OCCUPANT CELL"
