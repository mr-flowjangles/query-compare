"""Streamlit UI for query-compare.

Same inputs as the CLI's interactive mode; renders the generated SQL in a code
block with Streamlit's built-in copy button. Run via:

    streamlit run src/query_compare/ui.py

Or from the Makefile:

    make ui
"""

from __future__ import annotations

import streamlit as st

from query_compare.cli import HELPER_QUERY, _guess_key, _parse_key, _parse_unordered
from query_compare.dialects import postgres
from query_compare.parsers import json_schema, psql_describe
from query_compare.schema import Schema


def _parse_schema(text: str, fmt: str, qualified_name: str) -> Schema:
    if fmt == "json":
        cols = json_schema.parse_columns(text)
        return Schema(qualified_name=qualified_name, kind="unknown", columns=cols)
    cols_schema = psql_describe.parse(text)
    return cols_schema


def main() -> None:
    st.set_page_config(page_title="query-compare", layout="wide")
    st.title("query-compare")
    st.caption(
        "Generate SQL that compares two Postgres tables/views row-by-row "
        "and highlights data differences."
    )

    with st.expander("Step 1 — run this helper query in DBeaver to dump the schema"):
        st.code(HELPER_QUERY, language="sql")

    st.subheader("Step 2 — inputs")

    input_format = st.radio(
        "Schema input format",
        options=["json", "psql"],
        index=0,
        horizontal=True,
        help=(
            "`json` = paste the single-cell result of the helper query (default). "
            "`psql` = paste the output of `psql \\d <name>`."
        ),
    )

    schema_text = st.text_area(
        "Schema input",
        height=220,
        placeholder=(
            '[{"name":"record_id","type":"integer"}, '
            '{"name":"created_at","type":"timestamp with time zone"}, ...]'
        ),
    )

    # Try to parse early so we can offer a smart default for the key.
    parsed_columns: list[str] = []
    parse_warning: str | None = None
    if schema_text.strip():
        try:
            if input_format == "json":
                cols = json_schema.parse_columns(schema_text)
                parsed_columns = [c.name for c in cols]
            else:
                s = psql_describe.parse(schema_text)
                parsed_columns = [c.name for c in s.columns]
        except (json_schema.ParseError, psql_describe.ParseError) as e:
            parse_warning = str(e)

    col_a, col_b = st.columns(2)
    with col_a:
        new = st.text_input(
            "New object name",
            placeholder="public.v_opt_tracker",
        )
    with col_b:
        old = st.text_input(
            "Old object name",
            placeholder="public.v_opt_tracker_old",
        )

    default_key = _guess_key(parsed_columns) or ""
    key = st.text_input(
        "Join key (comma-separated for composite)",
        value=default_key,
        placeholder="record_id",
        help="Comma-separated for composite keys (e.g. `patient_id, visit_date`).",
    )

    unordered = st.text_input(
        "Unordered list columns (optional, comma-separated)",
        placeholder="tags, categories",
        help=(
            "Columns whose values are comma-separated lists where member order "
            "doesn't matter (e.g. unsorted `string_agg`). NULL and empty are equal; "
            "members are trimmed; duplicates count."
        ),
    )

    if parse_warning:
        st.warning(f"Could not parse schema yet: {parse_warning}")

    st.subheader("Step 3 — generate")

    generate_clicked = st.button("Generate SQL", type="primary")

    if not generate_clicked:
        return

    # ---- validate ----
    errors: list[str] = []
    if not schema_text.strip():
        errors.append("Schema input is required.")
    if not new.strip():
        errors.append("New object name is required.")
    if not old.strip():
        errors.append("Old object name is required.")
    if not key.strip():
        errors.append("Join key is required.")
    if errors:
        for e in errors:
            st.error(e)
        return

    try:
        key_cols = _parse_key(key)
    except SystemExit as e:
        st.error(str(e))
        return

    unordered_cols = _parse_unordered([unordered]) if unordered.strip() else []

    try:
        schema = _parse_schema(schema_text, input_format, qualified_name=old.strip())
    except (json_schema.ParseError, psql_describe.ParseError) as e:
        st.error(f"Failed to parse schema: {e}")
        return

    missing = [k for k in key_cols if k not in schema.column_names()]
    if missing:
        st.error(f"Key column(s) not found in schema: {', '.join(missing)}")
        return

    unknown_unordered = [u for u in unordered_cols if u not in schema.column_names()]
    if unknown_unordered:
        st.error(
            f"Unordered column(s) not found in schema: {', '.join(unknown_unordered)}"
        )
        return

    sql = postgres.generate(
        old.strip(),
        new.strip(),
        key_cols,
        schema,
        unordered_columns=frozenset(unordered_cols),
    )

    st.success(
        f"Generated SQL for {len(schema.columns)} columns "
        f"({len(schema.non_key_columns(key_cols))} non-key)."
    )
    st.code(sql, language="sql")


if __name__ == "__main__":
    main()
