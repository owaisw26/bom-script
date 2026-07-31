"""CSV reading and hierarchy construction. No Odoo-specific logic lives here."""

from __future__ import annotations

import csv
from pathlib import Path

from .models import ParsedSource, RejectedRow, SourceItem

REQUIRED_COLUMNS = {
    "Level", "Name", "Title", "Revision", "Enterprise Item Number", "Maturity State"
}


def clean(value: str | None) -> str:
    """Normalise values commonly exported as blanks by 3DEXPERIENCE."""
    value = (value or "").strip()
    return "" if value.lower() == "none" else value


def parse_csv(path: Path) -> ParsedSource:
    """Read the CSV and link every valid row to its immediate parent."""
    with path.open("r", encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        fieldnames = reader.fieldnames or []
        missing = sorted(REQUIRED_COLUMNS - set(fieldnames))
        if missing:
            return ParsedSource(path.name, fieldnames, [], [], [
                "Missing required column(s): " + ", ".join(missing)
            ])

        items: list[SourceItem] = []
        rejected: list[RejectedRow] = []
        stack: dict[int, SourceItem] = {}

        for row_number, raw_row in enumerate(reader, start=2):
            row = {key: clean(value) for key, value in raw_row.items() if key is not None}
            try:
                level = int(row["Level"])
                if level < 0:
                    raise ValueError
            except ValueError:
                rejected.append(RejectedRow(row_number, row, "Level must be a non-negative integer"))
                continue

            if not row["Title"]:
                rejected.append(RejectedRow(row_number, row, "Title is required"))
                continue
            if not row["Enterprise Item Number"] and not row["Name"]:
                rejected.append(RejectedRow(row_number, row, "Enterprise Item Number or Name is required"))
                continue

            parent = None
            if level > 0:
                parent = stack.get(level - 1)
                if parent is None:
                    rejected.append(RejectedRow(
                        row_number, row, "Component has no parent at the preceding hierarchy level"
                    ))
                    continue

            item = SourceItem(
                row_number=row_number, source_row=row, level=level, title=row["Title"],
                enterprise_item_number=row["Enterprise Item Number"], revision=row["Revision"],
                name=row["Name"], maturity_state=row["Maturity State"],
                parent_row_number=parent.row_number if parent else None,
            )
            # A row starts a new branch; deeper ancestors cannot parent later rows.
            stack = {depth: ancestor for depth, ancestor in stack.items() if depth < level}
            stack[level] = item
            items.append(item)

    errors = [] if any(item.level == 0 for item in items) else ["At least one Level 0 parent assembly is required"]
    return ParsedSource(path.name, fieldnames, items, rejected, errors)
