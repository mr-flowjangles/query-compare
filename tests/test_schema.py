from query_compare.schema import Column, TypeCategory, categorize


def test_categorize_text_types():
    for t in [
        "text", "varchar", "character varying(100)",
        "char(10)", "character(5)", "citext",
    ]:
        assert categorize(t) == TypeCategory.TEXT, t


def test_categorize_timestamp_tz():
    for t in [
        "timestamp with time zone",
        "timestamptz",
        "time with time zone",
        "timetz",
    ]:
        assert categorize(t) == TypeCategory.TIMESTAMP_TZ, t


def test_categorize_other():
    for t in [
        "integer", "bigint", "numeric(10,2)", "double precision",
        "boolean", "date", "timestamp without time zone", "uuid",
        "jsonb", "integer[]",
    ]:
        assert categorize(t) == TypeCategory.OTHER, t


def test_column_category_property():
    assert Column("a", "text").category == TypeCategory.TEXT
    assert Column("b", "integer").category == TypeCategory.OTHER
