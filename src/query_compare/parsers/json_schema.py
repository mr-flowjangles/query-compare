"""Parse a JSON column list (the result of the DBeaver helper query) into Columns.

The helper query (see README) returns a single cell containing JSON like:

    [
      {"name": "id",         "type": "integer"},
      {"name": "first_name", "type": "character varying"},
      {"name": "created_at", "type": "timestamp with time zone"}
    ]

This parser is forgiving about leading/trailing junk: DBeaver's "copy with
headers" can prepend a `schema_json` header row. We extract the substring
from the first `[` to the matching last `]` and parse that.
"""

from __future__ import annotations

import json

from query_compare.schema import Column


class ParseError(ValueError):
    pass


def parse_columns(text: str) -> tuple[Column, ...]:
    payload = _extract_json_array(text)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ParseError(f"input is not valid JSON: {e}") from e

    if not isinstance(data, list):
        raise ParseError("expected a JSON array of column objects.")
    if not data:
        raise ParseError("schema JSON is empty — no columns to compare.")

    columns: list[Column] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ParseError(f"column entry #{i} is not an object: {item!r}")
        name = item.get("name") or item.get("column_name")
        col_type = item.get("type") or item.get("data_type")
        if not name or not col_type:
            raise ParseError(
                f"column entry #{i} is missing 'name' or 'type': {item!r}"
            )
        columns.append(Column(name=str(name), raw_type=str(col_type)))

    return tuple(columns)


def _extract_json_array(text: str) -> str:
    """Slice out the JSON array, tolerating header rows or surrounding whitespace."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ParseError(
            "could not find a JSON array in the pasted input. "
            "Make sure you copied the result cell from the helper query."
        )
    return text[start : end + 1]
