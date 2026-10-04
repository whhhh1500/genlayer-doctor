from genlayer_doctor.header import RECOMMENDED_RUNNERS, fix_source, parse_header

H = RECOMMENDED_RUNNERS["py-genlayer"]
BODY = "from genlayer import *\n\nclass C(gl.Contract):\n    pass\n"


def codes(src):
    return [f.code for f in parse_header(src)[1]]


def test_pinned_header_is_clean():
    assert codes(f'# {{ "Depends": "py-genlayer:{H}" }}\n' + BODY) == []


def test_missing_header():
    assert codes(BODY) == ["GLD001"]


def test_floating_test_and_latest():
    assert codes('# { "Depends": "py-genlayer:test" }\n' + BODY) == ["GLD004"]
    assert codes('# { "Depends": "py-genlayer:latest" }\n' + BODY) == ["GLD004"]


def test_invalid_json():
    assert codes("# { 'Depends': 'py-genlayer:test' }\n" + BODY) == ["GLD002"]


def test_malformed_hash():
    assert codes('# { "Depends": "py-genlayer:abc123" }\n' + BODY) == ["GLD005"]


def test_missing_colon():
    assert codes('# { "Depends": "py-genlayer" }\n' + BODY) == ["GLD005"]


def test_different_but_valid_hash_warns():
    other = "0" * 52
    found = parse_header(f'# {{ "Depends": "py-genlayer:{other}" }}\n' + BODY)[1]
    assert [(f.code, f.severity) for f in found] == [("GLD006", "warning")]


def test_header_not_on_first_line():
    assert codes(f'\n# {{ "Depends": "py-genlayer:{H}" }}\n' + BODY) == ["GLD007"]


def test_unknown_runner_typo():
    assert "GLD008" in codes(f'# {{ "Depends": "py-genlayr:{H}" }}\n' + BODY)


def test_seq_header_collects_all_depends():
    src = '# { "Seq": [ { "Depends": "py-lib-genlayer-embeddings:test" }, { "Depends": "py-genlayer:test" } ] }\n' + BODY
    info, found = parse_header(src)
    assert [d.runner for d in info.dependencies] == ["py-lib-genlayer-embeddings", "py-genlayer"]
    assert [f.code for f in found] == ["GLD004", "GLD004"]


def test_fix_replaces_floating_ref():
    fixed = fix_source('# { "Depends": "py-genlayer:test" }\n' + BODY)
    assert fixed.splitlines()[0] == f'# {{ "Depends": "py-genlayer:{H}" }}'
    assert codes(fixed) == []
    assert fixed.endswith(BODY)


def test_fix_inserts_missing_header_and_is_idempotent():
    fixed = fix_source("\n\n" + BODY)
    assert codes(fixed) == []
    assert fix_source(fixed) == fixed


def test_fix_moves_header_to_top():
    fixed = fix_source(f'\n# {{ "Depends": "py-genlayer:{H}" }}\n' + BODY)
    assert codes(fixed) == []


def test_fix_preserves_other_seq_dependencies():
    src = '# { "Seq": [ { "Depends": "py-lib-genlayer-embeddings:xyz" }, { "Depends": "py-genlayer:test" } ] }\n' + BODY
    first = fix_source(src).splitlines()[0]
    assert "py-lib-genlayer-embeddings:xyz" in first and f"py-genlayer:{H}" in first


def test_fix_custom_runner():
    custom = "a" * 52
    assert f"py-genlayer:{custom}" in fix_source(BODY, custom).splitlines()[0]


def test_fix_replaces_invalid_json_header():
    fixed = fix_source("# { 'Depends': 'py-genlayer:test' }\n" + BODY)
    assert codes(fixed) == []
    assert fixed.count("Depends") == 1
