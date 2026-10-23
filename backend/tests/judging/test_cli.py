"""The judging CLI end to end on a file database."""

from sqlmodel import Session, create_engine, select

from app.judging.cli import main
from app.models import Project


def test_init_study_creates_the_projects_once(tmp_path, capsys):
    url = f"sqlite:///{tmp_path / 'reviq.db'}"
    assert main(["init-study", "--db", url]) == 0
    assert "created project" in capsys.readouterr().out
    assert main(["init-study", "--db", url]) == 0
    assert "nothing to do" in capsys.readouterr().out
    with Session(create_engine(url)) as session:
        assert len(session.exec(select(Project)).all()) == 3


def test_check_config_names_unpinned_models(capsys):
    assert main(["check-config"]) == 0
    out = capsys.readouterr().out
    assert "claude-sonnet-5-5" in out and "(not pinned)" in out


def test_estimate_prints_a_total_and_calls_nothing(capsys):
    assert main(["estimate", "--records", "7000"]) == 0
    out = capsys.readouterr().out
    assert "total:" in out and "nothing was called" in out


def test_a_broken_configuration_is_reported_not_raised(tmp_path, capsys):
    broken = tmp_path / "study.toml"
    broken.write_text("[study]\nname = 1\n", encoding="utf-8")
    assert main(["--config", str(broken), "check-config"]) == 2
    assert "error:" in capsys.readouterr().out
