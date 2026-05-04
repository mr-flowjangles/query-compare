"""CLI entry point for query-compare."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from query_compare.dialects import postgres
from query_compare.parsers import json_schema, psql_describe
from query_compare.schema import Schema


HELPER_QUERY = """\
-- query-compare schema dump.
-- Edit the schema/table name on the WHERE clause, then run in DBeaver.
-- Result is one cell containing JSON. Copy that cell and paste it to query-compare.
SELECT json_agg(
    json_build_object('name', column_name, 'type', data_type)
    ORDER BY ordinal_position
) AS schema_json
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name   = 'YOUR_TABLE_OR_VIEW';
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="query-compare",
        description=(
            "Generate SQL that compares two tables/views row-by-row "
            "and highlights data differences."
        ),
    )
    parser.add_argument(
        "--old",
        help="Fully-qualified name of the OLD table or view (e.g. public.old_view).",
    )
    parser.add_argument(
        "--new",
        help="Fully-qualified name of the NEW table or view (e.g. public.new_view).",
    )
    parser.add_argument(
        "--key",
        help="Key column(s) used to match rows. Comma-separated for composite keys.",
    )
    parser.add_argument(
        "--schema",
        help=(
            "Path to a file containing the schema input. "
            "If omitted, schema is read from stdin."
        ),
    )
    parser.add_argument(
        "--input-format",
        default="json",
        choices=["json", "psql"],
        help=(
            "Schema input format. 'json' = paste from the DBeaver helper query "
            "(default). 'psql' = paste output of psql `\\d <name>`."
        ),
    )
    parser.add_argument(
        "--dialect",
        default="postgres",
        choices=["postgres"],
        help="SQL dialect to generate. (More dialects to come.)",
    )
    parser.add_argument(
        "--unordered",
        action="append",
        default=None,
        help=(
            "Column to compare as an unordered comma-separated list "
            "(e.g. an unsorted string_agg). NULL and empty are equal; "
            "members are trimmed; duplicates count. Repeatable; also "
            "accepts comma-separated names in a single value."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write generated SQL to this file. Defaults to stdout.",
    )
    parser.add_argument(
        "--print-helper-query",
        action="store_true",
        help=(
            "Print the SQL query you should run in DBeaver to dump a "
            "table/view's schema, then exit."
        ),
    )
    return parser


def _read_schema_text(schema_path: str | None) -> str:
    if schema_path:
        return Path(schema_path).read_text()
    if sys.stdin.isatty():
        raise SystemExit(
            "error: no schema input. Provide --schema <file> or pipe the "
            "helper-query result via stdin."
        )
    return sys.stdin.read()


def _parse_key(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        raise SystemExit("error: --key must name at least one column.")
    return parts


def _parse_unordered(raw: list[str] | None) -> list[str]:
    """Flatten repeated --unordered flags + comma-split each into a clean list."""
    if not raw:
        return []
    out: list[str] = []
    for entry in raw:
        for p in entry.split(","):
            p = p.strip()
            if p and p not in out:
                out.append(p)
    return out


def _guess_key(column_names: list[str]) -> str | None:
    """Pick a sensible default join key from the parsed column list."""
    if "record_id" in column_names:
        return "record_id"
    if "id" in column_names:
        return "id"
    id_cols = [n for n in column_names if n.endswith("_id")]
    return id_cols[0] if id_cols else None


def _interactive_inputs() -> tuple[str, str, str, list[str], list[str]]:
    """Prompt for the inputs. Returns (json_text, new, old, key, unordered)."""
    print("Paste the JSON output of the helper query, then press Enter.", file=sys.stderr)
    json_text = input("Schema JSON: ").strip()

    try:
        cols = json_schema.parse_columns(json_text)
    except json_schema.ParseError as e:
        raise SystemExit(f"error: failed to parse schema: {e}") from None
    column_names = [c.name for c in cols]

    new = input("New object name (e.g. public.v_opt_tracker): ").strip()
    if not new:
        raise SystemExit("error: new object name is required.")
    old = input("Old object name (e.g. public.v_opt_tracker_old): ").strip()
    if not old:
        raise SystemExit("error: old object name is required.")

    default_key = _guess_key(column_names)
    prompt = (
        f"Join key [{default_key}] (comma-separated for composite): "
        if default_key
        else "Join key (comma-separated for composite, e.g. record_id): "
    )
    raw = input(prompt).strip() or (default_key or "")
    if not raw:
        raise SystemExit("error: join key is required.")

    unordered_raw = input(
        "Unordered list columns (comma-separated, blank for none): "
    ).strip()
    unordered = _parse_unordered([unordered_raw]) if unordered_raw else []

    return json_text, new, old, _parse_key(raw), unordered


def _parse_schema(text: str, fmt: str, qualified_name: str) -> Schema:
    if fmt == "json":
        cols = json_schema.parse_columns(text)
        return Schema(qualified_name=qualified_name, kind="unknown", columns=cols)
    if fmt == "psql":
        return psql_describe.parse(text)
    raise SystemExit(f"error: unknown --input-format {fmt!r}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.print_helper_query:
        sys.stdout.write(HELPER_QUERY)
        return 0

    interactive = (
        not args.old
        and not args.new
        and not args.key
        and not args.schema
        and sys.stdin.isatty()
    )

    if interactive:
        text, new, old, key, unordered = _interactive_inputs()
    else:
        missing_required = [
            f"--{name}" for name, val in (("old", args.old), ("new", args.new), ("key", args.key))
            if not val
        ]
        if missing_required:
            print(
                f"error: the following arguments are required: {', '.join(missing_required)}",
                file=sys.stderr,
            )
            return 2
        new = args.new
        old = args.old
        key = _parse_key(args.key)
        unordered = _parse_unordered(args.unordered)
        text = _read_schema_text(args.schema)

    try:
        schema = _parse_schema(text, args.input_format, qualified_name=old)
    except (json_schema.ParseError, psql_describe.ParseError) as e:
        print(f"error: failed to parse schema: {e}", file=sys.stderr)
        return 2

    missing = [k for k in key if k not in schema.column_names()]
    if missing:
        print(
            f"error: key column(s) not found in schema: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    unknown_unordered = [u for u in unordered if u not in schema.column_names()]
    if unknown_unordered:
        print(
            f"error: --unordered column(s) not found in schema: "
            f"{', '.join(unknown_unordered)}",
            file=sys.stderr,
        )
        return 2

    if args.dialect != "postgres":
        print(f"error: unsupported dialect {args.dialect!r}", file=sys.stderr)
        return 2

    sql = postgres.generate(
        old, new, key, schema, unordered_columns=frozenset(unordered)
    )

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(sql)
        print(f"wrote {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(sql)

    return 0
