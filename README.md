# query-compare

Generate SQL that verifies two Postgres tables/views produce the same data and
highlights the differences. Built for replacing slow legacy views with faster
rewrites without silently changing what they return.

The tool is **generate-only**: it emits a `.sql` script. It does not connect
to your database. You run the generated script yourself in DBeaver (or any
SQL client) against the database that has both views.

## How it works

```
   ┌──────────────────────────┐
   │ DBeaver (your DB)        │
   │                          │
   │  helper query  ─────────────────►  copy the result cell (JSON)
   │  (one cell of JSON)      │
   └──────────────────────────┘                      │
                                                     │ paste
                                                     ▼
   ┌──────────────────────────────────────────────────────┐
   │ query-compare (this CLI, runs locally on your Mac)   │
   │                                                      │
   │   parse JSON  ─►  classify column types  ─►  emit    │
   │                                              SQL     │
   └──────────────────────────────────────────────────────┘
                                                     │
                                                     │ save .sql
                                                     ▼
   ┌──────────────────────────────────────────────────────┐
   │ DBeaver again — paste & run the generated SQL.       │
   │                                                      │
   │   §1  Row-count check (old vs new totals)            │
   │   §2  Keys in OLD but missing from NEW               │
   │   §3  Keys in NEW but missing from OLD               │
   │   §4  Per-column diff: one row per mismatched cell   │
   └──────────────────────────────────────────────────────┘
```

After `make compare`, the tool prompts you for four things in sequence:

1. **Schema JSON** — paste the result cell from the helper query and press Enter.
2. **New object name** — fully-qualified, e.g. `public.v_opt_tracker`.
3. **Old object name** — fully-qualified, e.g. `public.v_opt_tracker_old`.
4. **Join key** — defaults to `record_id` if it's in the schema, otherwise the first `*_id` column. Comma-separated for composite keys.

For scripted runs, the same inputs can be passed as flags via `make compare-file` (see [Quickstart](#quickstart)).

### Comparison semantics (locked)

- `NULL` and `''` are treated as equal for text columns.
- Floats compared exactly (no tolerance).
- Strings compared exactly (no trim, case-sensitive).
- Timestamps with time zone are normalized to UTC before compare.
- Plain `date` / `timestamp without time zone` use NULL-safe equality as-is.

## Quickstart

The tool runs entirely in Docker. The Makefile is the single entry point —
`make help` lists every target and walks through the workflow.

```bash
make build                # one-time (and after code changes)
make helper-query         # → paste into DBeaver, run, copy result cell
make compare              # interactive: prompts for JSON, new name, old name, key
# open out/compare.sql in DBeaver and run each section
```

If you'd rather track the JSON paste in version control or run non-interactively
(CI, scripts), use `compare-file` with a saved schema:

```bash
# save DBeaver result to schemas/old_view.json
make compare-file OLD=public.v_opt_tracker_old \
                  NEW=public.v_opt_tracker \
                  KEY=record_id \
                  SCHEMA=schemas/old_view.json
```

The rest of this README covers what the tool does and the comparison
semantics. If you want to run it without Docker (e.g. for local dev), see
[Development](#development).

## Requirements

- Docker (Docker Desktop on Mac/Windows, or the Docker engine on Linux).
- That's it. The tool itself never connects to a database — you run the SQL it generates in DBeaver.

## Raw `docker run` (without `make`)

`make` is a thin wrapper. If you'd rather call Docker directly:

```bash
docker build -t query-compare .

# Print the helper query
docker run --rm query-compare --print-helper-query

# Interactive (the daily driver) — note the -it flags so prompts work
docker run --rm -it -v "$(pwd):/work" query-compare -o /work/out/compare.sql

# Non-interactive (scripted)
docker run --rm -v "$(pwd):/work" query-compare \
    --old public.v_opt_tracker_old --new public.v_opt_tracker --key record_id \
    --schema /work/schemas/old_view.json -o /work/out/compare.sql
```

## Walkthrough

Suppose you're rewriting `public.patient_view` as `public.patient_view_v2`
and want to verify the row data matches. The natural key is `patient_id`.

### 1. Get the helper query

```bash
query-compare --print-helper-query
```

Output:

```sql
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
```

### 2. Run the helper query in DBeaver

Open the SQL editor in DBeaver, paste the helper query, change the
`table_schema` / `table_name` to point at *one* of the views (either old or
new — they should have the same column shape):

```sql
... WHERE table_schema = 'public' AND table_name = 'patient_view';
```

Run it. You get a single-cell result that looks like:

```json
[{"name":"patient_id","type":"integer"},{"name":"first_name","type":"character varying"},{"name":"dob","type":"date"},{"name":"created_at","type":"timestamp with time zone"}]
```

Click the cell → copy.

### 3. Generate the compare SQL

```bash
make compare
```

The tool prompts you for four things:

```
Paste the JSON output of the helper query, then press Enter.
Schema JSON: [paste the JSON, hit Enter]
New object name (e.g. public.v_opt_tracker): public.patient_view_v2
Old object name (e.g. public.v_opt_tracker_old): public.patient_view
Join key [patient_id] (comma-separated for composite): [Enter to accept default]
→ wrote out/compare.sql
```

The default join key is auto-suggested from the schema (`record_id` if present,
otherwise `id`, otherwise the first `*_id` column). Hit Enter to accept it, or
type a different column name (or `a,b` for a composite key).

If you'd rather pass everything as flags (e.g. from a script):

```bash
make compare-file \
    OLD=public.patient_view \
    NEW=public.patient_view_v2 \
    KEY=patient_id \
    SCHEMA=schemas/patient_view.json
```

### 4. Run the generated SQL in DBeaver

Open `out/patient_compare.sql` and run each numbered section:

- **§1** — old vs. new total row counts.
- **§2** — keys in OLD that are missing from NEW.
- **§3** — keys in NEW that are missing from OLD.
- **§4** — per-column diff: one row per `(patient_id, column_name, old_value,
  new_value)` mismatch.

§4 is the one you'll usually care about most: it tells you exactly which
column on which row differs.

## Sample input and output

### Sample input — JSON from the helper query

You ran the helper query against `public.person` and copied the result cell.
The clipboard now contains:

```json
[
  {"name": "id",        "type": "integer"},
  {"name": "name",      "type": "text"},
  {"name": "age",       "type": "integer"},
  {"name": "shoe_size", "type": "integer"}
]
```

You also know:

- `--old public.person`
- `--new public.person_v2`
- `--key id`

### Sample output — generated SQL

Running `make compare` and feeding it the inputs above produces a `.sql` file
with four sections (abbreviated):

```sql
-- 1. Row count check
SELECT
    (SELECT COUNT(*) FROM "public"."person")    AS old_count,
    (SELECT COUNT(*) FROM "public"."person_v2") AS new_count;

-- 2. Keys in OLD but missing from NEW
SELECT "id" FROM "public"."person"
EXCEPT
SELECT "id" FROM "public"."person_v2";

-- 3. Keys in NEW but missing from OLD
SELECT "id" FROM "public"."person_v2"
EXCEPT
SELECT "id" FROM "public"."person";

-- 4. Per-row diff: each non-key column shows 'match' if equal,
--    or 'new | old' if not. Only rows with at least one mismatch are returned.
WITH joined AS (
    SELECT
        o."id" AS "id",
        o."name"      AS "o_name",      n."name"      AS "n_name",
        o."age"       AS "o_age",       n."age"       AS "n_age",
        o."shoe_size" AS "o_shoe_size", n."shoe_size" AS "n_shoe_size"
    FROM "public"."person" o
    INNER JOIN "public"."person_v2" n ON o."id" = n."id"
)
SELECT
    "id",
    CASE WHEN COALESCE("o_name", '') = COALESCE("n_name", '') THEN 'match'
         ELSE COALESCE("n_name"::text, 'NULL') || ' | ' || COALESCE("o_name"::text, 'NULL') END AS "name",
    CASE WHEN "o_age" IS NOT DISTINCT FROM "n_age" THEN 'match'
         ELSE COALESCE("n_age"::text, 'NULL') || ' | ' || COALESCE("o_age"::text, 'NULL') END AS "age",
    CASE WHEN "o_shoe_size" IS NOT DISTINCT FROM "n_shoe_size" THEN 'match'
         ELSE COALESCE("n_shoe_size"::text, 'NULL') || ' | ' || COALESCE("o_shoe_size"::text, 'NULL') END AS "shoe_size"
FROM joined
WHERE NOT (
        COALESCE("o_name", '') = COALESCE("n_name", '')
        AND "o_age" IS NOT DISTINCT FROM "n_age"
        AND "o_shoe_size" IS NOT DISTINCT FROM "n_shoe_size"
    )
ORDER BY "id";
```

### Sample result — what §4 returns when you run it

Suppose `public.person` and `public.person_v2` agree on most rows but
disagree on a couple. Running §4 in DBeaver returns something like:

```
 id  | name          | age   | shoe_size
-----+---------------+-------+-----------
  17 | match         | 2 | 3 | match
  42 | Alyce | Alice | match | 10 | 9
 108 | match         | match | 7 | NULL
```

Reading this (cells are `new | old`):

- **id 17** — `name` and `shoe_size` match; `age` is `2` in new, `3` in old.
- **id 42** — `age` matches; `name` and `shoe_size` both differ.
- **id 108** — `name` and `age` match; `shoe_size` is `7` in new, was NULL in old.

Only rows with at least one mismatch appear, so an empty result set means the
two views agree on every row that exists in both. (Use §1, §2, and §3 to
confirm row counts and to find rows that exist in only one side.)

## CLI reference

When run from a TTY with no `--old`, `--new`, `--key`, or `--schema`, the CLI
enters interactive mode and prompts for each input. Otherwise, it reads from
flags:

| Flag | Required (flag mode) | Default | Notes |
|---|---|---|---|
| `--old` | yes | — | Fully-qualified old view/table name. |
| `--new` | yes | — | Fully-qualified new view/table name. |
| `--key` | yes | — | Comma-separated key columns (e.g. `record_id` or `patient_id,visit_date`). |
| `--schema` | no | stdin | Path to JSON schema file. If omitted, JSON is read from stdin. |
| `--input-format` | no | `json` | `json` (DBeaver helper query result) or `psql` (output of `\d <name>`). |
| `--dialect` | no | `postgres` | Currently only `postgres`. |
| `-o`, `--output` | no | stdout | Write generated SQL to this path. |
| `--print-helper-query` | no | — | Print the DBeaver helper query and exit. |

## Development

If you're modifying the source, you'll likely want a local Python install for
fast test/lint loops (Docker rebuilds are slower than running `pytest`
directly).

```bash
# install uv once, system-wide
curl -LsSf https://astral.sh/uv/install.sh | sh

# from this repo:
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest -q
uv run ruff check .
```

Then `make build` to rebuild the Docker image when you're ready to ship.

## Project layout

```
query_compare_tool/
├── pyproject.toml                       # Python 3.12+, hatchling build
├── README.md
├── CLAUDE.md                            # notes for Claude Code sessions
└── src/query_compare/
    ├── __main__.py                      # python -m query_compare
    ├── cli.py                           # argparse + helper query constant
    ├── schema.py                        # Column / Schema / type categorizer
    ├── parsers/
    │   ├── json_schema.py               # JSON paste from DBeaver helper query (default)
    │   └── psql_describe.py             # psql `\d` paste (fallback)
    └── dialects/
        └── postgres.py                  # SQL generator
```

Adding a new SQL dialect = drop a new module under `dialects/` with the
same `generate(old, new, key, schema) -> str` signature, then add it to
`--dialect` choices in `cli.py`.
