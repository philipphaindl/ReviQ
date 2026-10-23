"""The study configuration: strict keys, pinned models, a priori thresholds."""

import copy
import tomllib

import pytest

from app.judging import config

RAW = tomllib.loads(config.DEFAULT_PATH.read_text(encoding="utf-8"))


def _raw():
    return copy.deepcopy(RAW)


def test_the_shipped_configuration_loads_with_the_thresholds_fixed_in_the_plan():
    study = config.load()
    assert study.mode == "studie"
    assert study.jury["tau_exclude"] == 0.02 and study.jury["tau_include"] == 0.5
    assert study.jury["max_rounds"] == 4 and study.jury["anchor_sample"] == 100
    assert study.audit_eps == 0.01
    assert {j.family for j in study.judges} == set(config.FAMILIES)


def test_an_unknown_key_is_an_error_not_a_silently_ignored_typo():
    raw = _raw()
    raw["jury"]["tau_exlude"] = 0.1
    with pytest.raises(config.ConfigError, match="unknown key"):
        config.parse(raw)


def test_an_alias_is_refused_because_it_is_a_different_model_next_month():
    raw = _raw()
    raw["judge"][0]["ladder"][0]["model"] = "claude-sonnet-latest"
    with pytest.raises(config.ConfigError, match="alias"):
        config.parse(raw)


def test_thresholds_must_be_ordered():
    raw = _raw()
    raw["jury"]["tau_exclude"] = 0.6
    with pytest.raises(config.ConfigError, match="tau_exclude < tau_include"):
        config.parse(raw)


def test_fewer_than_three_families_is_refused():
    raw = _raw()
    raw["judge"] = [j for j in raw["judge"] if j["family"] in ("anthropic", "openai")]
    with pytest.raises(config.ConfigError, match="three model families"):
        config.parse(raw)


def test_a_role_cannot_belong_to_two_judges():
    raw = _raw()
    raw["judge"][1]["role"] = raw["judge"][0]["role"]
    with pytest.raises(config.ConfigError, match="used twice"):
        config.parse(raw)


def test_freezing_needs_every_chosen_rung_pinned():
    study = config.load()
    with pytest.raises(config.ConfigError, match="not pinned"):
        config.require_pinned(study, {})
    raw = _raw()
    for judge in raw["judge"]:
        for rung in judge["ladder"]:
            rung["model"] = f"{judge['family']}-model-2026-10-01"
            if "digest" in rung:
                rung["digest"] = "sha256:" + "0" * 64
    config.require_pinned(config.parse(raw), {})


def test_the_review_mode_uses_its_own_audit_target():
    raw = _raw()
    raw["study"]["mode"] = "review"
    assert config.parse(raw).audit_eps == 0.02
