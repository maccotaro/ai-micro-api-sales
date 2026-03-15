"""Markdown table validator and fixer.

LLM-generated Markdown tables often have structural issues that prevent
proper rendering. This module detects and repairs common problems:

- Missing separator row (|---|---|)
- Inconsistent column counts across rows
- Missing leading/trailing pipe characters
- Malformed separator cells
"""

import re
from typing import Optional


_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{1,}:?$")
# Matches cells that look like a broken separator: only dashes, spaces, colons
# e.g. "- --", "-- -", ": ---", "- - -"
_MALFORMED_SEPARATOR_CELL_RE = re.compile(r"^[:\- ]+$")


def fix_markdown_tables(markdown: str) -> str:
    """Fix all Markdown tables in the given text.

    Processes line-by-line, grouping consecutive table rows into blocks,
    then validates and repairs each block.
    """
    lines = markdown.split("\n")
    result: list[str] = []
    table_block: list[str] = []

    for line in lines:
        if _is_table_row(line):
            table_block.append(line)
        else:
            if table_block:
                # Ensure a blank line before the table so that Markdown
                # parsers (remark-gfm / ReactMarkdown) recognise it.
                if result and result[-1].strip():
                    result.append("")
                result.extend(_fix_table_block(table_block))
                # Ensure a blank line after the table as well.
                if line.strip():
                    result.append("")
                table_block = []
            result.append(line)

    if table_block:
        if result and result[-1].strip():
            result.append("")
        result.extend(_fix_table_block(table_block))

    return "\n".join(result)


def _is_table_row(line: str) -> bool:
    """Check if a line looks like a Markdown table row.

    Only matches lines that start and end with ``|`` (the standard format).
    Lines with inner pipes but no outer pipes are too ambiguous to detect
    reliably without false positives on regular prose.
    """
    stripped = line.strip()
    if not stripped:
        return False
    return bool(_TABLE_ROW_RE.match(stripped))


def _parse_cells(row: str) -> list[str]:
    """Parse a table row into cell contents."""
    stripped = row.strip()
    # Remove leading/trailing pipes
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_separator_row(row: str) -> bool:
    """Check if a row is a valid separator (|---|---|)."""
    cells = _parse_cells(row)
    if not cells:
        return False
    return all(_SEPARATOR_CELL_RE.match(cell) for cell in cells if cell)


def _is_malformed_separator_row(row: str) -> bool:
    """Check if a row is a broken separator (e.g. ``| --- | - -- |``).

    A malformed separator is a row where every cell contains only dashes,
    spaces, and colons but at least one cell fails the strict separator
    pattern (e.g. contains spaces between dashes).
    """
    if _is_separator_row(row):
        return False  # It's a valid separator, not malformed
    cells = _parse_cells(row)
    if not cells:
        return False
    non_empty = [c for c in cells if c]
    if not non_empty:
        return False
    return all(_MALFORMED_SEPARATOR_CELL_RE.match(cell) for cell in non_empty)


def _build_row(cells: list[str], col_count: int) -> str:
    """Build a properly formatted table row with exact column count."""
    # Pad or truncate to match column count
    padded = cells[:col_count]
    while len(padded) < col_count:
        padded.append("")
    return "| " + " | ".join(padded) + " |"


def _build_separator(col_count: int) -> str:
    """Build a separator row with the given column count."""
    return "| " + " | ".join(["---"] * col_count) + " |"


def _fix_table_block(rows: list[str]) -> list[str]:
    """Validate and fix a block of table rows."""
    if not rows:
        return rows

    # First pass: drop malformed separator rows (e.g. "| --- | - -- |")
    cleaned_rows = [r for r in rows if not _is_malformed_separator_row(r)]
    if not cleaned_rows:
        return rows

    parsed_rows: list[list[str]] = []
    separator_indices: list[int] = []
    original_separator_cells: dict[int, list[str]] = {}

    for i, row in enumerate(cleaned_rows):
        if _is_separator_row(row):
            separator_indices.append(i)
            original_separator_cells[i] = _parse_cells(row)
            parsed_rows.append([])  # placeholder
        else:
            parsed_rows.append(_parse_cells(row))

    # Determine target column count from data rows (exclude separators)
    data_col_counts = [
        len(cells) for i, cells in enumerate(parsed_rows)
        if i not in separator_indices and cells
    ]
    if not data_col_counts:
        return rows

    col_count = max(data_col_counts)

    # Build fixed output
    fixed: list[str] = []
    has_separator = len(separator_indices) > 0
    has_header = len(parsed_rows) > 0 and 0 not in separator_indices

    for i, cells in enumerate(parsed_rows):
        if i in separator_indices:
            # Preserve original alignment markers, pad if needed
            orig = original_separator_cells[i]
            padded = orig[:col_count]
            while len(padded) < col_count:
                padded.append("---")
            fixed.append("| " + " | ".join(padded) + " |")
        else:
            fixed.append(_build_row(cells, col_count))
            # Insert separator after first data row if missing
            if i == 0 and has_header and not has_separator:
                fixed.append(_build_separator(col_count))
                has_separator = True

    return fixed
