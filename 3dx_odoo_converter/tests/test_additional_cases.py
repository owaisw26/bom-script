"""Additional acceptance cases kept separate so each scenario is easy to read."""

from decimal import Decimal
from pathlib import Path

from converter.parser import parse_csv
from converter.transformer import transform
from converter.validator import validate


HEADER = "Level,Title,Enterprise Item Number,Revision,Maturity State,Name,Quantity\n"


def test_blank_product_title_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "blank-title.csv"
    source.write_text(HEADER + "0,,ASM,A.1,Released,root,\n", encoding="utf-8")
    parsed = parse_csv(source)
    assert parsed.rejected_rows[0].reason == "Title is required"


def test_multiple_parents_create_multiple_boms(tmp_path: Path) -> None:
    source = tmp_path / "multiple.csv"
    source.write_text(
        HEADER +
        "0,Assembly A,ASM-A,A.1,Released,root-a,\n"
        "1,Part A,CMP-A,A.1,Released,part-a,\n"
        "0,Assembly B,ASM-B,A.1,Released,root-b,\n"
        "1,Part B,CMP-B,A.1,Released,part-b,\n", encoding="utf-8"
    )
    result = validate(parse_csv(source), released_only=False, quantity_column="Quantity",
                      default_quantity=Decimal("1"))
    _, boms = transform(result, product_type="Goods", bom_type="Manufacture this product",
                        default_uom="Units")
    assert len(boms) == 2


def test_quantity_column_combines_source_quantities(tmp_path: Path) -> None:
    source = tmp_path / "quantities.csv"
    source.write_text(
        HEADER +
        "0,Assembly,ASM,A.1,Released,root,\n"
        "1,Part,CMP,A.1,Released,part,2\n"
        "1,Part,CMP,A.1,Released,part,3\n", encoding="utf-8"
    )
    result = validate(parse_csv(source), released_only=False, quantity_column="Quantity",
                      default_quantity=Decimal("1"))
    _, boms = transform(result, product_type="Goods", bom_type="Manufacture this product",
                        default_uom="Units")
    assert boms[0].lines[0].quantity == Decimal("5")
    assert any("Duplicate component rows combined" in warning.message for warning in result.warnings)


def test_non_released_data_warns_without_released_filter(tmp_path: Path) -> None:
    source = tmp_path / "not-released.csv"
    source.write_text(HEADER + "0,Assembly,ASM,A.1,In Work,root,\n", encoding="utf-8")
    result = validate(parse_csv(source), released_only=False, quantity_column=None,
                      default_quantity=Decimal("1"))
    assert not result.errors
    assert any(warning.message == "Item is not released" for warning in result.warnings)
