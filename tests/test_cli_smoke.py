from query_compare.cli import build_parser


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
