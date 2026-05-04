# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

Generate SQL that verifies two Postgres tables/views produce the same data, and
highlights row-level and column-level differences. The motivating workflow is
replacing slow legacy views with faster rewrites without silently changing the
data they return. The tool is **generate-only** — it emits SQL to stdout/file,
it does not connect to a database.

## Commands

The `Makefile` is the canonical entry point — `make help` lists every target
and the standard workflow. Prefer `make <target>` over the raw commands below
when one exists.

All raw commands assume `uv` is on the `PATH` (`$HOME/.local/bin`). The
`.venv` is created by `uv venv` (or `make install`) and is the canonical
environment.

```bash
# install (editable) with dev extras
uv pip install -e ".[dev]"

# run all tests
uv run pytest -q

# run a single test file or test
uv run pytest tests/test_postgres_generator.py -q
uv run pytest tests/test_postgres_generator.py::test_text_column_uses_coalesce_empty_string -q

# lint
uv run ruff check .

# print the DBeaver helper query (paste this into DBeaver, run, copy result cell)
uv run query-compare --print-helper-query

# generate compare SQL from a JSON schema paste (default --input-format json)
uv run query-compare --old public.old_view --new public.new_view --key id --schema /path/to/schema.json
echo '[{"name":"id","type":"integer"}, ...]' | uv run query-compare --old ... --new ... --key id

# psql `\d` paste path is still supported as a fallback
psql -c '\d public.old_view' | uv run query-compare --old ... --new ... --key id --input-format psql

# install globally so `query-compare` is on PATH everywhere
uv tool install .

# Docker (for sharing the tool with teammates)
docker build -t query-compare .
pbpaste | docker run --rm -i query-compare --old ... --new ... --key id
```

The `Dockerfile` is `python:3.12-slim` + `pip install .`, with `query-compare`
as the `ENTRYPOINT` and `/work` as the working directory (mount your host
output dir there to capture `-o` files).

## Architecture

The tool is a four-stage pipeline. Reading these in order is the fastest way
to understand the codebase:

1. **`cli.py`** — argparse entry point. Reads schema text from `--schema` or
   stdin, parses the `--key` (comma-separated for composite keys), validates
   that every key column exists in the parsed schema, then dispatches to the
   chosen dialect.

2. **`parsers/json_schema.py`** (default) — parses a JSON column array
   produced by the DBeaver helper query (see `HELPER_QUERY` in `cli.py` or
   `--print-helper-query`). Tolerates DBeaver's "copy with headers" leading
   junk by extracting the first `[` … last `]` substring before parsing.
   Returns a tuple of `Column`s; the CLI wraps that into a `Schema` using
   `--old` as the (cosmetic) `qualified_name`.

   **`parsers/psql_describe.py`** (fallback, `--input-format psql`) — text
   parser for psql `\d <name>` output. Recognizes both `Table "..."` and
   `View "..."` headers, finds the `Column | Type | ...` block, and stops
   at known section headers. Returns a full `Schema` (parses the
   qualified_name from the title line).

   **Adding a new input format = a sibling module here that produces a
   `Schema` (or column tuple)** and a `--input-format` choice in `cli.py`.

3. **`schema.py`** — the contract between parsers and dialects. `Schema`
   holds `(qualified_name, kind, columns)`. Each `Column` carries a raw
   Postgres type string and a `category` property that classifies it as
   `TEXT`, `TIMESTAMP_TZ`, or `OTHER`. **The category is what drives
   comparison-rule selection in the generator** — to handle a new type
   correctly, update `categorize()` (and its sets), not the generator.

4. **`dialects/postgres.py`** — SQL generator. Produces a four-section
   script: row counts, keys-in-old-not-new, keys-in-new-not-old, and a
   per-column diff CTE that returns `(key…, column_name, old_value,
   new_value)` rows for every mismatched cell. Comparison expressions per
   category:
   - `TEXT` → `COALESCE(o, '') = COALESCE(n, '')` (treats NULL and '' as equal)
   - `TIMESTAMP_TZ` → `(o AT TIME ZONE 'UTC') IS NOT DISTINCT FROM (n AT TIME ZONE 'UTC')`
   - `OTHER` → `o IS NOT DISTINCT FROM n` (NULL-safe equality)

   All identifiers are double-quoted via `quote_ident` /
   `quote_qualified` — never interpolate raw names into SQL.

The dialect layer is set up to grow: `dialects/postgres.py` is currently the
only implementation, but the `--dialect` flag and `dialects/` package exist
so a second engine (MySQL, Snowflake, etc.) can be dropped in without
restructuring callers. A new dialect needs the same `generate(old, new, key,
schema) -> str` entry point.

## Comparison semantics (locked)

These were agreed up front and tests pin them. Don't loosen them without
checking with the user:

- NULL and `''` are equal for text columns.
- Floats compared exactly (no tolerance).
- Strings compared exactly (no trim, case-sensitive).
- Timestamps with time zone are normalized to UTC before compare.
- Plain `date` and `timestamp without time zone` use NULL-safe equality
  as-is — they are *not* tz-normalized.

## Conventions worth knowing

- Python 3.12+ only. `pyproject.toml` is hatchling-built, src layout
  (`src/query_compare/`).
- Tests live in `tests/` and import from `query_compare.*`. The CLI is
  exposed as both `python -m query_compare` and the `query-compare` script
  entry.
- `ParseError` is the parser's only public exception; CLI catches it and
  exits with code 2. Dialect-level invariants (e.g. unknown dialect, key
  not in schema) also exit 2 with a stderr message.
