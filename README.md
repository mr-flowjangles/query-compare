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

You provide three things on the command line:

- **`--old`** — fully-qualified name of the old view/table (e.g. `public.patient_view`).
- **`--new`** — fully-qualified name of the new view/table.
- **`--key`** — the column(s) used to match rows between the two. Comma-separated for composite keys.

…and the JSON schema as either a file (`--schema path.json`) or piped via stdin.

### Comparison semantics (locked)

- `NULL` and `''` are treated as equal for text columns.
- Floats compared exactly (no tolerance).
- Strings compared exactly (no trim, case-sensitive).
- Timestamps with time zone are normalized to UTC before compare.
- Plain `date` / `timestamp without time zone` use NULL-safe equality as-is.

## Requirements

- macOS, Linux, or Windows.
- One of: Python 3.12+ (with `uv` or `pip`), **or** Docker.
- The tool itself never connects to a database — you run the SQL it generates.

## Install — three options

### Option A: Docker (best for sharing across a team)

You need Docker (Docker Desktop on Mac/Windows, or the Docker engine on Linux).
Build the image once from a checkout of this repo:

```bash
docker build -t query-compare .
```

Then run it. Pass CLI args after the image name; pipe schema JSON via stdin:

```bash
# Print the helper query
docker run --rm query-compare --print-helper-query

# Generate compare SQL, JSON via stdin, output to stdout
pbpaste | docker run --rm -i query-compare \
    --old public.patient_view --new public.patient_view_v2 --key patient_id

# Output to a file on the host (mount a directory)
mkdir -p out
pbpaste | docker run --rm -i -v "$(pwd)/out:/work" query-compare \
    --old public.patient_view --new public.patient_view_v2 --key patient_id \
    -o /work/compare.sql
# → ./out/compare.sql on the host
```

A convenience shell alias makes it feel native:

```bash
alias query-compare='docker run --rm -i -v "$(pwd):/work" query-compare'
```

### Option B: `uv` (recommended for local dev on the maintainer's machine)

[`uv`](https://docs.astral.sh/uv/) is a fast Python tool installer.

```bash
# install uv (one-time, system-wide)
curl -LsSf https://astral.sh/uv/install.sh | sh

# install query-compare globally so it's on your PATH everywhere
uv tool install .
```

### Option C: `pip` + venv (fallback)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
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
# Pipe via stdin (paste the JSON inline)
pbpaste | query-compare \
    --old public.patient_view \
    --new public.patient_view_v2 \
    --key patient_id \
    -o out/patient_compare.sql
```

Or save the JSON to a file first:

```bash
query-compare \
    --old public.patient_view \
    --new public.patient_view_v2 \
    --key patient_id \
    --schema schemas/patient_view.json \
    -o out/patient_compare.sql
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

Running:

```bash
pbpaste | query-compare --old public.person --new public.person_v2 --key id
```

…produces a `.sql` file with four sections (abbreviated):

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
--    or 'old | new' if not. Only rows with at least one mismatch are returned.
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
         ELSE COALESCE("o_name"::text, 'NULL') || ' | ' || COALESCE("n_name"::text, 'NULL') END AS "name",
    CASE WHEN "o_age" IS NOT DISTINCT FROM "n_age" THEN 'match'
         ELSE COALESCE("o_age"::text, 'NULL') || ' | ' || COALESCE("n_age"::text, 'NULL') END AS "age",
    CASE WHEN "o_shoe_size" IS NOT DISTINCT FROM "n_shoe_size" THEN 'match'
         ELSE COALESCE("o_shoe_size"::text, 'NULL') || ' | ' || COALESCE("n_shoe_size"::text, 'NULL') END AS "shoe_size"
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
  17 | match         | 3 | 2 | match
  42 | Alice | Alyce | match | 9 | 10
 108 | match         | match | NULL | 7
```

Reading this:

- **id 17** — `name` and `shoe_size` match; `age` is `3` in old, `2` in new.
- **id 42** — `age` matches; `name` and `shoe_size` both differ.
- **id 108** — `name` and `age` match; `shoe_size` was NULL in old, `7` in new.

Only rows with at least one mismatch appear, so an empty result set means the
two views agree on every row that exists in both. (Use §1, §2, and §3 to
confirm row counts and to find rows that exist in only one side.)

## CLI reference

| Flag | Required | Default | Notes |
|---|---|---|---|
| `--old` | yes | — | Fully-qualified old view/table name. |
| `--new` | yes | — | Fully-qualified new view/table name. |
| `--key` | yes | — | Comma-separated key columns (e.g. `patient_id` or `patient_id,visit_date`). |
| `--schema` | no | stdin | Path to JSON schema file. If omitted, JSON is read from stdin. |
| `--input-format` | no | `json` | `json` (DBeaver helper query result) or `psql` (output of `\d <name>`). |
| `--dialect` | no | `postgres` | Currently only `postgres`. |
| `-o`, `--output` | no | stdout | Write generated SQL to this path. |
| `--print-helper-query` | no | — | Print the DBeaver helper query and exit. |

## Development

```bash
# install with dev extras
uv pip install -e ".[dev]"

# run tests
uv run pytest -q

# lint
uv run ruff check .
```

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
