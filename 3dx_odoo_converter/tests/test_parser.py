from pathlib import Path

from converter.parser import parse_csv


def write_csv(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "source.csv"
    path.write_text(
        "Level,Title,Enterprise Item Number,Revision,Maturity State,Name\n" + body,
        encoding="utf-8",
    )
    return path


def test_parser_links_a_level_one_component(tmp_path: Path) -> None:
    parsed = parse_csv(write_csv(tmp_path,
        "0,Assembly,ASM-1,A.1,Released,root\n1,Component,CMP-1,A.1,Released,child\n"))
    assert not parsed.errors
    assert len(parsed.items) == 2
    assert parsed.items[1].parent_row_number == 2


def test_parser_rejects_orphan_component(tmp_path: Path) -> None:
    parsed = parse_csv(write_csv(tmp_path, "1,Component,CMP-1,A.1,Released,child\n"))
    assert len(parsed.rejected_rows) == 1
    assert "no parent" in parsed.rejected_rows[0].reason.lower()


def test_parser_requires_expected_columns(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    path.write_text("Level,Title\n0,Assembly\n", encoding="utf-8")
    assert "Missing required column" in parse_csv(path).errors[0]
