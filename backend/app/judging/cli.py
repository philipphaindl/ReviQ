"""Command line interface.

    python -m app.judging check-config
    python -m app.judging init-study
    python -m app.judging estimate --records 7000
    python -m app.judging prompts [--freeze NAME ...]

Every command that will cost money gets `--dry-run` when it is added; the
commands so far cost nothing.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from . import __version__, config, costs, prompts, setup


def _database_url() -> str:
    """The same file the review and creel use. Mirrors `retrieval.cli.default_db`:
    `DATABASE_URL` when it is set, otherwise `DATA_DIR/reviq.db` — never the
    container-shaped default of `app.database`, which is a read-only path
    outside Docker."""

    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    return f"sqlite:///{Path(os.environ.get('DATA_DIR', 'data')) / 'reviq.db'}"


def _session(url: str | None = None) -> Session:
    import app.models  # noqa: F401  (registers the review tables)
    from . import models  # noqa: F401  (registers the judging tables)

    url = url or _database_url()
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})
    # Adds missing tables only; existing ones, ReviQ's included, are untouched.
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def cmd_check_config(args: argparse.Namespace) -> int:
    study = config.load(args.config)
    print(f"study {study.name}, mode {study.mode}, seed {study.seed}")
    print(f"jury: anchor {study.jury['anchor_sample']}, tau_E {study.jury['tau_exclude']}, "
          f"tau_I {study.jury['tau_include']}, max rounds {study.jury['max_rounds']}")
    print(f"audit: eps {study.audit_eps} -> n = {round(3 / study.audit_eps)}")
    for judge in study.judges:
        rungs = ", ".join(f"{r.model}{'' if r.pinned else ' (not pinned)'}" for r in judge.ladder)
        print(f"{judge.key} {judge.role} {judge.family}{' local' if judge.local else ''}: {rungs}")
    return 0


def cmd_init_study(args: argparse.Namespace) -> int:
    study = config.load(args.config)
    with _session(args.db) as session:
        report = setup.init_study(session, study)
    for title in report.created_projects:
        print(f"created project {title!r}")
    for line in report.added:
        print(f"added {line}")
    if not report.changed:
        print("nothing to do: projects, criteria and reviewers already present")
    return 0


def cmd_estimate(args: argparse.Namespace) -> int:
    study = config.load(args.config)
    profile = {"screening": costs.SCREENING, "full-text": costs.FULL_TEXT}[args.phase]
    commercial = [j for j in study.judges if not j.local]
    votes = costs.adaptive_votes(args.records, len(study.judges),
                                 int(study.jury["anchor_sample"]), args.extra_share)
    print(f"{args.phase}: {args.records} records, about {votes} votes in total "
          f"(anchor {int(study.jury['anchor_sample'])} x {len(study.judges)} judges, "
          f"2 judges on the rest, +{args.extra_share:.0%} further rounds)")
    total_standard = total_batch = 0.0
    # Votes beyond the anchor sample are spread evenly over the judges; the
    # local judge costs time, not money.
    per_judge = round(votes / len(study.judges))
    for judge in commercial:
        rung = judge.ladder[0]
        est = costs.estimate(per_judge, profile, rung)
        total_standard += est.usd_standard
        total_batch += est.usd_batch
        print(f"  {judge.key} {rung.model}: {est.calls} calls, "
              f"{est.tokens_in / 1e6:.1f}M in / {est.tokens_out / 1e6:.1f}M out, "
              f"${est.usd_standard:.2f} standard, ${est.usd_batch:.2f} batch")
    print(f"  total: ${total_standard:.2f} standard, ${total_batch:.2f} batch "
          "(estimate; nothing was called)")
    return 0


def cmd_prompts(args: argparse.Namespace) -> int:
    if args.freeze:
        prompts.freeze(args.freeze, args.prompt_dir)
    frozen = prompts.frozen_names(args.prompt_dir)
    names = prompts.available(args.prompt_dir)
    if not names:
        print("no prompts yet")
    for name in names:
        prompt = prompts.load(name, args.prompt_dir)
        state = "frozen" if name in frozen else "draft"
        print(f"{name} v{prompt.version} {prompt.sha256[:12]} {state}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.judging")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, default=config.DEFAULT_PATH,
                        help="study configuration (TOML)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-config", help="validate and print the study configuration")

    p_init = sub.add_parser("init-study", help="create the ReviQ projects of the study")
    p_init.add_argument("--db", default=None, metavar="URL",
                        help="database URL (default: DATABASE_URL or DATA_DIR/reviq.db)")

    p_est = sub.add_parser("estimate", help="estimate the cost of a jury phase")
    p_est.add_argument("--records", type=int, required=True)
    p_est.add_argument("--phase", choices=("screening", "full-text"), default="screening")
    p_est.add_argument("--extra-share", type=float, default=0.25,
                       help="share of records needing a further round (default 0.25)")

    p_prompts = sub.add_parser("prompts", help="list prompts, or freeze some")
    p_prompts.add_argument("--freeze", nargs="+", metavar="NAME", default=None)
    p_prompts.add_argument("--prompt-dir", type=Path, default=prompts.PROMPT_DIR)
    return parser


COMMANDS = {
    "check-config": cmd_check_config,
    "init-study": cmd_init_study,
    "estimate": cmd_estimate,
    "prompts": cmd_prompts,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (config.ConfigError, prompts.PromptError) as exc:
        print(f"error: {exc}")
        return 2
