import pytest

from query_compare.parsers.json_schema import ParseError, parse_columns


def test_parses_clean_json_array():
    text = '[{"name":"id","type":"integer"},{"name":"first_name","type":"character varying"}]'
    cols = parse_columns(text)
    assert [c.name for c in cols] == ["id", "first_name"]
    assert [c.raw_type for c in cols] == ["integer", "character varying"]


def test_tolerates_dbeaver_header_row():
    text = "schema_json\n[{\"name\":\"id\",\"type\":\"integer\"}]\n"
    cols = parse_columns(text)
    assert cols[0].name == "id"


def test_tolerates_pretty_printed_json_with_whitespace():
    text = """
    [
      {"name": "id",   "type": "integer"},
      {"name": "name", "type": "text"}
    ]
    """
    cols = parse_columns(text)
    assert len(cols) == 2


def test_accepts_information_schema_column_names_too():
    text = '[{"column_name":"id","data_type":"integer"}]'
    cols = parse_columns(text)
    assert cols[0].name == "id"
    assert cols[0].raw_type == "integer"


def test_raises_on_non_json():
    with pytest.raises(ParseError):
        parse_columns("not json at all")


def test_raises_on_empty_array():
    with pytest.raises(ParseError):
        parse_columns("[]")


def test_raises_on_missing_keys():
    with pytest.raises(ParseError):
        parse_columns('[{"name":"id"}]')
