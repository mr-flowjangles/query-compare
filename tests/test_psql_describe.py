import textwrap

import pytest

from query_compare.parsers.psql_describe import ParseError, parse


TABLE_SAMPLE = textwrap.dedent(
    """\
                                  Table "public.patient"
       Column   |            Type             | Collation | Nullable |     Default
    ------------+-----------------------------+-----------+----------+-------------------
     id         | integer                     |           | not null | nextval('seq'::r)
     first_name | character varying(100)      |           |          |
     last_name  | character varying(100)      |           |          |
     dob        | date                        |           |          |
     created_at | timestamp with time zone    |           | not null | now()
    Indexes:
        "patient_pkey" PRIMARY KEY, btree (id)
    """
)


VIEW_SAMPLE = textwrap.dedent(
    """\
                       View "public.patient_summary"
       Column   |          Type            | Collation | Nullable | Default
    ------------+--------------------------+-----------+----------+---------
     id         | integer                  |           |          |
     full_name  | text                     |           |          |
     visit_cnt  | bigint                   |           |          |

    View definition:
     SELECT p.id, p.first_name || ' ' || p.last_name AS full_name,
            count(v.*) AS visit_cnt
       FROM patient p
       LEFT JOIN visit v ON v.patient_id = p.id
      GROUP BY p.id;
    """
)


def test_parses_table():
    schema = parse(TABLE_SAMPLE)
    assert schema.qualified_name == "public.patient"
    assert schema.kind == "table"
    names = [c.name for c in schema.columns]
    assert names == ["id", "first_name", "last_name", "dob", "created_at"]
    types = [c.raw_type for c in schema.columns]
    assert types == [
        "integer",
        "character varying(100)",
        "character varying(100)",
        "date",
        "timestamp with time zone",
    ]


def test_parses_view_and_skips_definition():
    schema = parse(VIEW_SAMPLE)
    assert schema.qualified_name == "public.patient_summary"
    assert schema.kind == "view"
    assert [c.name for c in schema.columns] == ["id", "full_name", "visit_cnt"]


def test_raises_on_missing_title():
    with pytest.raises(ParseError):
        parse("just some text without a header")


def test_raises_on_missing_column_header():
    with pytest.raises(ParseError):
        parse('Table "public.foo"\n(no header here)\n')
