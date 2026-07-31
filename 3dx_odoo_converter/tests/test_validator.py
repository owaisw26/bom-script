from decimal import Decimal
from pathlib import Path

from converter.parser import parse_csv
from converter.validator import validate


def test_released_only_rejects_an_unreleased_parent(tmp_path: Path) -> None:
    path = tmp_path / "source.csv"
    path.write_text(
        "Level,Title,Enterprise Item Number,Revision,Maturity State,Name\n"
        "0,Assembly,ASM,A.1,In Work,root\n"
        "1,Part,CMP,A.1,Released,part\n", encoding="utf-8"
    )
    result = validate(parse_csv(path), released_only=True, quantity_column=None,
                      default_quantity=Decimal("1"))
    assert any("not Released" in error for error in result.errors)


def test_quantity_column_must_be_positive(tmp_path: Path) -> None:
    path = tmp_path / "source.csv"
    path.write_text(
        "Level,Title,Enterprise Item Number,Revision,Maturity State,Name,Quantity\n"
        "0,Assembly,ASM,A.1,Released,root,\n"
        "1,Part,CMP,A.1,Released,part,0\n", encoding="utf-8"
    )
    result = validate(parse_csv(path), released_only=False, quantity_column="Quantity",
                      default_quantity=Decimal("1"))
    assert result.rejected_rows[0].reason == "Quantity must be a positive number"
