"""Parse the text output of psql's `\\d <name>` command into a Schema.

Handles both tables and views. Output looks like:

                              Table "public.patient"
       Column     |            Type             | Collation | Nullable | Default
    --------------+-----------------------------+-----------+----------+---------
     id           | integer                     |           | not null |
     first_name   | character varying(100)      |           |          |
     created_at   | timestamp with time zone    |           |          |
    Indexes:
        "patient_pkey" PRIMARY KEY, btree (id)

We only need the qualified name (from the title line) and the column rows.
Everything after the column block (Indexes, View definition, etc.) is ignored.
"""

from __future__ import annotations

import re

from query_compare.schema import Column, Schema

_TITLE_RE = re.compile(r'^\s*(Table|View|Materialized view|Foreign table)\s+"([^"]+)"\s*$')

# Section headers that mark the end of the column block.
_END_SECTIONS = (
    "Indexes:",
    "Foreign-key constraints:",
    "Check constraints:",
    "Triggers:",
    "Inherits:",
    "Partition of:",
    "Partition key:",
    "Partitions:",
    "Referenced by:",
    "View definition:",
    "Access method:",
    "Options:",
    "Statistics objects:",
    "Publications:",
    "Tablespace:",
    "Number of partitions:",
    "Rules:",
)


class ParseError(ValueError):
    """Raised when the input does not look like psql `\\d` output."""


def parse(text: str) -> Schema:
    lines = text.splitlines()

    title_idx, qualified_name, kind = _find_title(lines)
    header_idx = _find_header(lines, start=title_idx + 1)
    separator_idx = header_idx + 1
    if separator_idx >= len(lines) or not _is_separator(lines[separator_idx]):
        raise ParseError(
            "Expected a `---+---` separator line directly after the column header."
        )

    columns = _parse_columns(lines, start=separator_idx + 1)
    if not columns:
        raise ParseError("No columns found in `\\d` output.")

    return Schema(qualified_name=qualified_name, kind=kind, columns=tuple(columns))


def _find_title(lines: list[str]) -> tuple[int, str, str]:
    for i, line in enumerate(lines):
        m = _TITLE_RE.match(line)
        if m:
            kind_word = m.group(1).lower()
            kind = "view" if "view" in kind_word else "table"
            return i, m.group(2), kind
    raise ParseError(
        'Could not find a `Table "..."` or `View "..."` header. '
        "Paste the full output of psql `\\d <name>`."
    )


def _find_header(lines: list[str], start: int) -> int:
    """Find the `Column | Type | ...` header line."""
    for i in range(start, len(lines)):
        line = lines[i]
        if "|" not in line:
            continue
        cells = [c.strip().lower() for c in line.split("|")]
        if len(cells) >= 2 and cells[0] == "column" and cells[1] == "type":
            return i
    raise ParseError("Could not find the `Column | Type` header line.")


def _is_separator(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # Separator is made of '-' and '+' (and spaces around column boundaries).
    return all(ch in "-+" for ch in stripped.replace(" ", ""))


def _parse_columns(lines: list[str], start: int) -> list[Column]:
    columns: list[Column] = []
    for i in range(start, len(lines)):
        line = lines[i]
        stripped = line.strip()

        # Blank line ends the column block.
        if not stripped:
            break

        # Section headers (Indexes:, View definition:, etc.) end the block.
        if any(stripped.startswith(s) for s in _END_SECTIONS):
            break

        # Lines without `|` are not column rows.
        if "|" not in line:
            break

        # `(N rows)` summary lines.
        if re.match(r"^\(\d+ rows?\)\s*$", stripped):
            break

        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 2:
            break

        name, raw_type = cells[0], cells[1]
        if not name or not raw_type:
            break

        columns.append(Column(name=name, raw_type=raw_type))

    return columns
