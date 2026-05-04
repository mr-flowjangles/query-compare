"""Postgres SQL generator for view/table comparison.

Produces a single .sql script with four sections:

  1. Row count check (old vs new totals).
  2. Keys present in OLD but missing from NEW.
  3. Keys present in NEW but missing from OLD.
  4. Per-column diff for matched rows: one row per (key, column) where the
     value differs, with old/new cast to text for easy reading.

Comparison rules:
  - text-like columns: COALESCE(col, '') equality (NULL == '')
  - timestamptz / timetz: cast to UTC before compare
  - everything else: IS NOT DISTINCT FROM (NULL-safe)
"""

from __future__ import annotations

from query_compare.schema import Column, Schema, TypeCategory


def quote_ident(name: str) -> str:
    """Double-quote a Postgres identifier and escape any embedded quotes."""
    return '"' + name.replace('"', '""') + '"'


def quote_qualified(qualified: str) -> str:
    """Quote each part of a possibly-schema-qualified name: schema.table -> "schema"."table"."""
    return ".".join(quote_ident(p) for p in qualified.split("."))


def _equal_expr(left: str, right: str, category: TypeCategory) -> str:
    """SQL expression that is TRUE when the two values are considered equal."""
    if category == TypeCategory.TEXT:
        return f"COALESCE({left}, '') = COALESCE({right}, '')"
    if category == TypeCategory.TIMESTAMP_TZ:
        return (
            f"({left} AT TIME ZONE 'UTC') IS NOT DISTINCT FROM "
            f"({right} AT TIME ZONE 'UTC')"
        )
    return f"{left} IS NOT DISTINCT FROM {right}"


def generate(
    old: str,
    new: str,
    key: list[str],
    schema: Schema,
) -> str:
    """Render the full comparison .sql script as a single string."""
    old_q = quote_qualified(old)
    new_q = quote_qualified(new)

    key_columns = [quote_ident(k) for k in key]
    key_csv = ", ".join(key_columns)

    non_key = schema.non_key_columns(key)

    parts: list[str] = []
    parts.append(_header(old, new, key, schema))
    parts.append(_section_row_count(old_q, new_q))
    parts.append(_section_missing_keys(old_q, new_q, key_csv, "OLD", "NEW"))
    parts.append(_section_missing_keys(new_q, old_q, key_csv, "NEW", "OLD"))
    parts.append(_section_per_column_diff(old_q, new_q, key, non_key))
    return "\n".join(parts)


def _header(old: str, new: str, key: list[str], schema: Schema) -> str:
    return (
        f"-- query-compare\n"
        f"-- old: {old}\n"
        f"-- new: {new}\n"
        f"-- key: {', '.join(key)}\n"
        f"-- schema source: {schema.qualified_name} ({schema.kind}, "
        f"{len(schema.columns)} columns)\n"
    )


def _section_row_count(old_q: str, new_q: str) -> str:
    return (
        "-- 1. Row count check\n"
        "SELECT\n"
        f"    (SELECT COUNT(*) FROM {old_q}) AS old_count,\n"
        f"    (SELECT COUNT(*) FROM {new_q}) AS new_count;\n"
    )


def _section_missing_keys(
    src_q: str, other_q: str, key_csv: str, src_label: str, other_label: str
) -> str:
    section_num = 2 if src_label == "OLD" else 3
    return (
        f"-- {section_num}. Keys in {src_label} but missing from {other_label}\n"
        f"SELECT {key_csv} FROM {src_q}\n"
        f"EXCEPT\n"
        f"SELECT {key_csv} FROM {other_q};\n"
    )


def _section_per_column_diff(
    old_q: str, new_q: str, key: list[str], non_key: list[Column]
) -> str:
    """Per-row diff: each non-key column either shows 'match' or 'old | new'.

    Only returns rows where at least one column disagrees, so the result set
    stays small even on large views.
    """
    if not non_key:
        return (
            "-- 4. Per-row diff\n"
            "-- (skipped: no non-key columns to compare)\n"
        )

    join_clause = " AND ".join(
        f"o.{quote_ident(k)} = n.{quote_ident(k)}" for k in key
    )

    cte_lines = [f"o.{quote_ident(k)} AS {quote_ident(k)}" for k in key]
    for c in non_key:
        col = quote_ident(c.name)
        cte_lines.append(f"o.{col} AS {quote_ident('o_' + c.name)}")
        cte_lines.append(f"n.{col} AS {quote_ident('n_' + c.name)}")
    cte_select = ",\n        ".join(cte_lines)

    eq_exprs: list[str] = []
    case_lines: list[str] = []
    for c in non_key:
        ocol = quote_ident("o_" + c.name)
        ncol = quote_ident("n_" + c.name)
        eq = _equal_expr(ocol, ncol, c.category)
        eq_exprs.append(eq)
        case_lines.append(
            f"CASE WHEN {eq} THEN 'match' "
            f"ELSE COALESCE({ocol}::text, 'NULL') || ' | ' || "
            f"COALESCE({ncol}::text, 'NULL') END AS {quote_ident(c.name)}"
        )

    key_select = ", ".join(quote_ident(k) for k in key)
    case_block = ",\n    ".join(case_lines)
    where_clause = "NOT (\n        " + "\n        AND ".join(eq_exprs) + "\n    )"
    order_keys = ", ".join(quote_ident(k) for k in key)

    return (
        "-- 4. Per-row diff: each non-key column shows 'match' if equal,\n"
        "--    or 'old | new' if not. Only rows with at least one mismatch are returned.\n"
        "WITH joined AS (\n"
        "    SELECT\n"
        f"        {cte_select}\n"
        f"    FROM {old_q} o\n"
        f"    INNER JOIN {new_q} n ON {join_clause}\n"
        ")\n"
        "SELECT\n"
        f"    {key_select},\n"
        f"    {case_block}\n"
        "FROM joined\n"
        f"WHERE {where_clause}\n"
        f"ORDER BY {order_keys};\n"
    )
