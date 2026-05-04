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

    key = _parse_key(args.key)
    text = _read_schema_text(args.schema)

    try:
        schema = _parse_schema(text, args.input_format, qualified_name=args.old)
    except (json_schema.ParseError, psql_describe.ParseError) as e:
        print(f"error: failed to parse schema: {e}", file=sys.stderr)
        return 2

    missing = [k for k in key if k not in schema.column_names()]
    if missing:
        print(
            f"error: --key column(s) not found in schema: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    if args.dialect != "postgres":
        print(f"error: unsupported dialect {args.dialect!r}", file=sys.stderr)
        return 2

    sql = postgres.generate(args.old, args.new, key, schema)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(sql)
        print(f"wrote {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(sql)

    return 0
