from query_compare.dialects.postgres import generate
from query_compare.schema import Column, Schema


def _patient_schema() -> Schema:
    return Schema(
        qualified_name="public.patient",
        kind="table",
        columns=(
            Column("id", "integer"),
            Column("first_name", "character varying(100)"),
            Column("dob", "date"),
            Column("created_at", "timestamp with time zone"),
        ),
    )


def test_header_includes_metadata():
    sql = generate("public.old_v", "public.new_v", ["id"], _patient_schema())
    assert "-- query-compare" in sql
    assert "-- old: public.old_v" in sql
    assert "-- new: public.new_v" in sql
    assert "-- key: id" in sql


def test_qualified_names_are_quoted():
    sql = generate("public.old_v", "public.new_v", ["id"], _patient_schema())
    assert '"public"."old_v"' in sql
    assert '"public"."new_v"' in sql


def test_row_count_section():
    sql = generate("public.old_v", "public.new_v", ["id"], _patient_schema())
    assert 'SELECT COUNT(*) FROM "public"."old_v"' in sql
    assert 'SELECT COUNT(*) FROM "public"."new_v"' in sql


def test_missing_key_sections_use_except():
    sql = generate("public.old_v", "public.new_v", ["id"], _patient_schema())
    assert 'SELECT "id" FROM "public"."old_v"\nEXCEPT' in sql
    assert 'SELECT "id" FROM "public"."new_v"\nEXCEPT' in sql


def test_text_column_uses_coalesce_empty_string():
    sql = generate("public.old_v", "public.new_v", ["id"], _patient_schema())
    assert "COALESCE(\"o_first_name\", '') = COALESCE(\"n_first_name\", '')" in sql


def test_timestamptz_column_normalized_to_utc():
    sql = generate("public.old_v", "public.new_v", ["id"], _patient_schema())
    assert "AT TIME ZONE 'UTC'" in sql
    assert '"o_created_at"' in sql and '"n_created_at"' in sql


def test_other_column_uses_is_not_distinct_from():
    sql = generate("public.old_v", "public.new_v", ["id"], _patient_schema())
    assert '"o_dob" IS NOT DISTINCT FROM "n_dob"' in sql


def test_composite_key_join_clause():
    schema = Schema(
        qualified_name="public.foo",
        kind="table",
        columns=(
            Column("a", "integer"),
            Column("b", "integer"),
            Column("payload", "text"),
        ),
    )
    sql = generate("s.old", "s.new", ["a", "b"], schema)
    assert 'ON o."a" = n."a" AND o."b" = n."b"' in sql
    assert 'SELECT "a", "b" FROM "s"."old"' in sql


def test_skip_column_diff_when_only_key_columns():
    schema = Schema(
        qualified_name="public.foo",
        kind="table",
        columns=(Column("id", "integer"),),
    )
    sql = generate("s.old", "s.new", ["id"], schema)
    assert "no non-key columns to compare" in sql


def test_diff_section_uses_per_row_match_or_pipe_format():
    sql = generate("public.old_v", "public.new_v", ["id"], _patient_schema())
    # Each non-key column wraps to: CASE WHEN ... THEN 'match' ELSE new || ' | ' || old END
    assert "THEN 'match'" in sql
    assert "' | '" in sql
    # Mismatch cell template uses COALESCE(...::text, 'NULL') so NULLs are visible
    assert "COALESCE(\"o_first_name\"::text, 'NULL')" in sql
    assert "COALESCE(\"n_first_name\"::text, 'NULL')" in sql
    # Order is new | old (matches the interactive prompt order)
    assert (
        "COALESCE(\"n_first_name\"::text, 'NULL') || ' | ' || "
        "COALESCE(\"o_first_name\"::text, 'NULL')"
    ) in sql


def test_diff_section_filters_to_rows_with_mismatches():
    sql = generate("public.old_v", "public.new_v", ["id"], _patient_schema())
    # WHERE NOT ( eq AND eq AND eq ) keeps only rows that disagree somewhere
    assert "WHERE NOT (" in sql
    assert "AND" in sql  # multiple equality clauses ANDed


def _assignees_schema() -> Schema:
    return Schema(
        qualified_name="public.tracker",
        kind="view",
        columns=(
            Column("id", "integer"),
            Column("assignees", "text"),
            Column("note", "text"),
        ),
    )


def test_unordered_column_uses_normalized_set_compare():
    sql = generate(
        "public.old_v",
        "public.new_v",
        ["id"],
        _assignees_schema(),
        unordered_columns=frozenset({"assignees"}),
    )
    # The unordered path splits, trims, sorts, and re-joins both sides before comparing.
    assert 'string_to_array("o_assignees", \',\')' in sql
    assert 'string_to_array("n_assignees", \',\')' in sql
    assert "string_agg(trim(t), ', ' ORDER BY trim(t))" in sql
    # Non-unordered text column still uses the plain COALESCE rule.
    assert "COALESCE(\"o_note\", '') = COALESCE(\"n_note\", '')" in sql


def test_unordered_column_does_not_affect_default_text_compare():
    sql = generate(
        "public.old_v",
        "public.new_v",
        ["id"],
        _assignees_schema(),
    )
    # Default: assignees uses plain text equality, no string_to_array anywhere.
    assert "string_to_array" not in sql
    assert "COALESCE(\"o_assignees\", '') = COALESCE(\"n_assignees\", '')" in sql


def test_unordered_column_appears_in_where_clause_too():
    sql = generate(
        "public.old_v",
        "public.new_v",
        ["id"],
        _assignees_schema(),
        unordered_columns=frozenset({"assignees"}),
    )
    # The same normalized expression is used in WHERE NOT (...) so a row that
    # only differs by ordering doesn't get returned.
    where_idx = sql.index("WHERE NOT (")
    assert "string_to_array(\"o_assignees\"" in sql[where_idx:]
