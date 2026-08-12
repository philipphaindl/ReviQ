"""Query set parsing.

A search protocol that silently ignores a typo is a silently wrong review, so
unknown keys are errors rather than warnings. These tests pin that.
"""

import pytest

from app.retrieval.batch import ConfigError, parse_config


def _toml(text):
    import tomllib
    return tomllib.loads(text)


def test_defaults_apply_to_every_query():
    specs = parse_config(_toml("""
        [defaults]
        pages = 10
        gl = "at"
        [[query]]
        q = "AI maturity assessment model"
        [[query]]
        q = "AI readiness framework"
    """))
    assert len(specs) == 2
    assert all(s.params["pages"] == 10 and s.params["gl"] == "at" for s in specs)


def test_a_query_can_override_a_default():
    specs = parse_config(_toml("""
        [defaults]
        pages = 10
        [[query]]
        q = "a"
        [[query]]
        q = "b"
        pages = 3
    """))
    assert [s.params["pages"] for s in specs] == [10, 3]


def test_built_in_defaults_fill_the_gaps():
    specs = parse_config(_toml('[[query]]\nq = "a"'))
    assert specs[0].params["pages"] == 5
    assert specs[0].params["engine"] == "google"
    assert specs[0].params["snowball_depth"] == 0
    assert specs[0].params["render_js"] is False


def test_unknown_key_in_a_query_is_an_error():
    """A typo like `page` for `pages` must not pass silently."""
    with pytest.raises(ConfigError) as exc:
        parse_config(_toml('[[query]]\nq = "a"\npage = 3'))
    assert "page" in str(exc.value)


def test_unknown_key_in_defaults_is_an_error():
    with pytest.raises(ConfigError):
        parse_config(_toml('[defaults]\ncountry = "at"\n[[query]]\nq = "a"'))


def test_unknown_section_is_an_error():
    with pytest.raises(ConfigError):
        parse_config(_toml('[settings]\npages = 3\n[[query]]\nq = "a"'))


def test_defaults_may_not_carry_a_query():
    with pytest.raises(ConfigError):
        parse_config(_toml('[defaults]\nq = "a"\n[[query]]\nq = "b"'))


def test_at_least_one_query_is_required():
    with pytest.raises(ConfigError):
        parse_config(_toml('[defaults]\npages = 3'))


def test_empty_query_is_rejected():
    with pytest.raises(ConfigError):
        parse_config(_toml('[[query]]\nq = "   "'))


def test_duplicate_queries_are_rejected():
    """Two identical queries would issue the same search twice and quietly
    double the cost."""
    with pytest.raises(ConfigError):
        parse_config(_toml('[[query]]\nq = "a"\n[[query]]\nq = "a"'))


def test_queries_are_stripped():
    specs = parse_config(_toml('[[query]]\nq = "  spaced  "'))
    assert specs[0].q == "spaced"


def test_the_shipped_example_parses():
    from app.retrieval.batch import EXAMPLE

    specs = parse_config(_toml(EXAMPLE))
    assert len(specs) == 3
    assert specs[0].params["pages"] == 10
    assert specs[2].params["pages"] == 5
