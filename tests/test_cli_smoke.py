from unittest.mock import patch

import pytest

from query_compare.cli import (
    _guess_key,
    _interactive_inputs,
    _parse_unordered,
    build_parser,
)


def test_parser_accepts_required_args():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--old", "public.old_view",
            "--new", "public.new_view",
            "--key", "id",
        ]
    )
    assert args.old == "public.old_view"
    assert args.new == "public.new_view"
    assert args.key == "id"
    assert args.dialect == "postgres"
    assert args.input_format == "json"


def test_guess_key_prefers_record_id():
    assert _guess_key(["record_id", "id", "member_id", "name"]) == "record_id"


def test_guess_key_falls_back_to_id():
    assert _guess_key(["id", "member_id", "name"]) == "id"


def test_guess_key_falls_back_to_first_id_suffix():
    assert _guess_key(["member_id", "visit_id", "name"]) == "member_id"


def test_guess_key_returns_none_when_no_id_columns():
    assert _guess_key(["first_name", "last_name", "email"]) is None


def test_interactive_inputs_uses_default_key_on_empty_input():
    json_text = '[{"name":"record_id","type":"character varying"},{"name":"name","type":"text"}]'
    responses = iter([
        json_text,
        "public.v_opt_tracker",
        "public.v_opt_tracker_old",
        "",
        "",
    ])
    with patch("builtins.input", lambda prompt="": next(responses)):
        text, new, old, key, unordered = _interactive_inputs()
    assert text == json_text
    assert new == "public.v_opt_tracker"
    assert old == "public.v_opt_tracker_old"
    assert key == ["record_id"]
    assert unordered == []


def test_interactive_inputs_overrides_default_key():
    json_text = '[{"name":"record_id","type":"text"},{"name":"member_id","type":"text"}]'
    responses = iter([
        json_text,
        "public.new_view",
        "public.old_view",
        "member_id",
        "",
    ])
    with patch("builtins.input", lambda prompt="": next(responses)):
        _, _, _, key, _ = _interactive_inputs()
    assert key == ["member_id"]


def test_interactive_inputs_accepts_composite_key():
    json_text = '[{"name":"member_id","type":"text"},{"name":"visit_date","type":"date"}]'
    responses = iter([
        json_text,
        "public.new_view",
        "public.old_view",
        "member_id, visit_date",
        "",
    ])
    with patch("builtins.input", lambda prompt="": next(responses)):
        _, _, _, key, _ = _interactive_inputs()
    assert key == ["member_id", "visit_date"]


def test_interactive_inputs_collects_unordered_columns():
    json_text = (
        '[{"name":"record_id","type":"text"},'
        '{"name":"assignees","type":"text"},'
        '{"name":"collabusers_sk","type":"text"}]'
    )
    responses = iter([
        json_text,
        "public.new_view",
        "public.old_view",
        "",
        "assignees, collabusers_sk",
    ])
    with patch("builtins.input", lambda prompt="": next(responses)):
        _, _, _, _, unordered = _interactive_inputs()
    assert unordered == ["assignees", "collabusers_sk"]


def test_interactive_inputs_rejects_blank_new_name():
    json_text = '[{"name":"record_id","type":"text"}]'
    responses = iter([json_text, "", "public.old_view", "record_id", ""])
    with (
        patch("builtins.input", lambda prompt="": next(responses)),
        pytest.raises(SystemExit, match="new object name"),
    ):
        _interactive_inputs()


def test_interactive_inputs_surfaces_bad_json():
    responses = iter(["not json", "", "", "", ""])
    with (
        patch("builtins.input", lambda prompt="": next(responses)),
        pytest.raises(SystemExit, match="failed to parse schema"),
    ):
        _interactive_inputs()


def test_parse_unordered_flattens_repeats_and_comma_splits():
    assert _parse_unordered(None) == []
    assert _parse_unordered([]) == []
    assert _parse_unordered(["assignees"]) == ["assignees"]
    assert _parse_unordered(["assignees,collabusers_sk"]) == [
        "assignees",
        "collabusers_sk",
    ]
    assert _parse_unordered(["assignees", "collabusers_sk"]) == [
        "assignees",
        "collabusers_sk",
    ]
    assert _parse_unordered(["assignees, collabusers_sk", "assignees"]) == [
        "assignees",
        "collabusers_sk",
    ]


def test_parser_accepts_unordered_flag():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--old", "public.old",
            "--new", "public.new",
            "--key", "id",
            "--unordered", "assignees",
            "--unordered", "collabusers_sk",
        ]
    )
    assert _parse_unordered(args.unordered) == ["assignees", "collabusers_sk"]
