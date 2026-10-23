"""Versioned prompts and the freeze (A.3.2)."""

import json

import pytest

from app.judging import prompts


def _write(directory, name="screening", version="0.1", body="Screen one record."):
    (directory / f"{name}.md").write_text(
        f"---\nname: {name}\nversion: {version}\n---\n{body}\n", encoding="utf-8")


def test_a_prompt_loads_with_its_version_and_hash(tmp_path):
    _write(tmp_path)
    prompt = prompts.load("screening", tmp_path)
    assert prompt.version == "0.1" and prompt.text == "Screen one record.\n"
    assert len(prompt.sha256) == 64


def test_a_frozen_prompt_refuses_to_load_after_its_text_changed(tmp_path):
    _write(tmp_path)
    prompts.freeze(["screening"], tmp_path)
    prompts.load("screening", tmp_path)
    _write(tmp_path, body="Screen one record, generously.")
    with pytest.raises(prompts.PromptFrozen, match="protocol deviation"):
        prompts.load("screening", tmp_path)


def test_a_new_version_number_does_not_unfreeze_a_prompt(tmp_path):
    _write(tmp_path)
    prompts.freeze(["screening"], tmp_path)
    _write(tmp_path, version="0.2", body="Another text.")
    with pytest.raises(prompts.PromptFrozen):
        prompts.load("screening", tmp_path)


def test_freezing_records_hash_version_and_time_and_keeps_the_first_freeze(tmp_path):
    _write(tmp_path)
    prompts.freeze(["screening"], tmp_path)
    first = json.loads((tmp_path / prompts.FREEZE_FILE).read_text())
    prompts.freeze(["screening"], tmp_path)
    second = json.loads((tmp_path / prompts.FREEZE_FILE).read_text())
    assert first == second
    assert second["prompts"]["screening"]["version"] == "0.1"


def test_unfrozen_prompts_stay_editable(tmp_path):
    _write(tmp_path)
    _write(tmp_path, name="extraction")
    prompts.freeze(["screening"], tmp_path)
    _write(tmp_path, name="extraction", body="Changed during calibration.")
    assert prompts.load("extraction", tmp_path).text == "Changed during calibration.\n"
    assert prompts.frozen_names(tmp_path) == {"screening"}


@pytest.mark.parametrize("content, message", [
    ("Screen one record.\n", "missing front matter"),
    ("---\nname: screening\n", "not closed"),
    ("---\nname: screening\n---\ntext\n", "needs 'version'"),
    ("---\nname: other\nversion: 1\n---\ntext\n", "names 'other'"),
])
def test_malformed_front_matter_is_an_error(tmp_path, content, message):
    (tmp_path / "screening.md").write_text(content, encoding="utf-8")
    with pytest.raises(prompts.PromptError, match=message):
        prompts.load("screening", tmp_path)


def test_the_shipped_prompt_directory_lists_only_prompt_files():
    for name in prompts.available():
        prompts.load(name)
