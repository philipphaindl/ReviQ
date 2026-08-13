"""What the command line accepts, and where.

Nothing covered `cli.py` until `adopt data/glr.sqlite3 --project 1` failed with
`unrecognized arguments`. The flag was on the top-level parser, so it had to come
*before* the subcommand while every other option comes after — and the README
managed to write it both ways in one file, which is what a surface nobody tests
looks like.

The argument-placement half is easy to re-break, so it is pinned here. The
harder half is pinned too: the subcommands that *offer* `--project` must be
exactly the ones that *read* it. A fourth reader added without a fourth
declaration would otherwise take `None` forever and file its runs under no
review at all — silently, because argparse has no opinion about a flag nobody
declared.
"""

import argparse
import ast
import inspect

import pytest

from app.retrieval import cli

# The three that record a run and take the review it belongs to.
TAKES_PROJECT = ("run", "batch", "adopt")

# The rest. `report`, `export-json`, `refetch` and `reextract` derive the
# project from the runs they were asked to read (D28) — asking again would be a
# second chance to answer wrong. `init`, `init-config` and `export` have no
# project at all.
NO_PROJECT = ("init", "init-config", "refetch", "reextract", "report",
              "export", "export-json")

# A minimal, valid invocation of each subcommand: enough positional arguments to
# parse, and nothing that touches the network or a database.
INVOCATIONS = {
    "init": ["init"],
    "init-config": ["init-config"],
    "run": ["run", "AI maturity model"],
    "batch": ["batch", "queries.toml"],
    "refetch": ["refetch", "run-1"],
    "reextract": ["reextract", "run-1"],
    "report": ["report", "run-1"],
    "adopt": ["adopt", "old.sqlite3"],
    "export": ["export", "run-1"],
    "export-json": ["export-json", "run-1"],
}


@pytest.fixture
def parser():
    """Only the surface. `parse_args` never calls the `func` it selects."""
    return cli.build_parser()


def test_the_invocation_table_covers_every_subcommand(parser):
    """Guards the guard: a new subcommand must be listed above, or the tests
    below would quietly stop covering the CLI as it grows."""
    actions = [a for a in parser._actions
               if isinstance(a, argparse._SubParsersAction)]
    assert len(actions) == 1
    declared = set(actions[0].choices)

    assert declared == set(INVOCATIONS)
    assert declared == set(TAKES_PROJECT) | set(NO_PROJECT)


@pytest.mark.parametrize("command", TAKES_PROJECT)
def test_project_is_accepted_after_the_subcommand(parser, command):
    """Where every other option goes. This is the exact line that failed."""
    args = parser.parse_args(INVOCATIONS[command] + ["--project", "1"])

    assert args.project == 1
    assert args.command == command


@pytest.mark.parametrize("command", TAKES_PROJECT)
def test_project_defaults_to_none(parser, command):
    """Retrieval outside a review stays possible, and means what it says: the
    runs belong to nobody and their snapshots stay visible to everyone."""
    assert parser.parse_args(INVOCATIONS[command]).project is None


@pytest.mark.parametrize("command", NO_PROJECT)
def test_project_is_refused_where_it_would_do_nothing(parser, command):
    """Rejected rather than swallowed. A flag accepted and ignored is worse
    than one that is not accepted: the caller believes it took effect."""
    with pytest.raises(SystemExit):
        parser.parse_args(INVOCATIONS[command] + ["--project", "1"])


def test_project_is_no_longer_a_global_flag(parser):
    """The old spelling must fail, not keep working alongside the new one.
    Two ways to say the same thing is how the README came to say both."""
    with pytest.raises(SystemExit):
        parser.parse_args(["--project", "1", "adopt", "old.sqlite3"])


@pytest.mark.parametrize("command", sorted(INVOCATIONS))
def test_db_is_global_and_applies_to_every_subcommand(parser, command):
    """`--db` genuinely does apply everywhere, which is why it stays where it
    is. The asymmetry with `--project` is the point, not an oversight."""
    args = parser.parse_args(["--db", "some.sqlite3"] + INVOCATIONS[command])

    assert str(args.db) == "some.sqlite3"


def test_db_defaults_to_none_so_main_can_derive_it(parser):
    """`main` fills it from `DATABASE_URL` when it is None. A default baked
    into the parser would read the environment at import time, before a test or
    a caller had a chance to set it."""
    assert parser.parse_args(["report", "run-1"]).db is None


# --- the surface matches the code -----------------------------------------


def commands_reading_project() -> set[str]:
    """Which `cmd_*` functions look at `args.project`, read out of the source.

    Read rather than called: calling them opens databases and spends credits.
    The mapping from subcommand to function comes from `set_defaults(func=...)`
    in `build_parser`, so a renamed handler is caught here too.
    """
    source = inspect.getsource(cli)
    tree = ast.parse(source)

    reads: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("cmd_"):
            continue
        for inner in ast.walk(node):
            # args.project
            if (isinstance(inner, ast.Attribute) and inner.attr == "project"
                    and isinstance(inner.value, ast.Name) and inner.value.id == "args"):
                reads.add(node.name)
            # getattr(args, "project", None)
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                    and inner.func.id == "getattr" and len(inner.args) >= 2
                    and isinstance(inner.args[1], ast.Constant)
                    and inner.args[1].value == "project"):
                reads.add(node.name)
    return reads


def test_the_commands_that_offer_project_are_the_ones_that_read_it():
    """The half argparse cannot catch. A `cmd_*` that reads `args.project`
    without its subparser declaring `--project` gets `None` on every run and
    files its work under no review — with no error anywhere."""
    parser = cli.build_parser()
    subparsers = next(a for a in parser._actions
                      if isinstance(a, argparse._SubParsersAction))

    offering = set()
    for name, sub in subparsers.choices.items():
        if any(o == "--project" for a in sub._actions for o in a.option_strings):
            offering.add(name)

    handler_names = {
        name: sub.get_default("func").__name__
        for name, sub in subparsers.choices.items()
    }
    reading_handlers = commands_reading_project()
    reading = {name for name, handler in handler_names.items()
               if handler in reading_handlers}

    assert offering == set(TAKES_PROJECT)
    assert offering == reading, (
        f"offered by {sorted(offering)}, read by {sorted(reading)} — a command "
        f"that reads --project without declaring it always sees None"
    )
