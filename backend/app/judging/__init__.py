"""LLM-assisted judging for ReviQ studies (docs/aiqm-study/PLAN.md).

A command line tool next to creel rather than a part of the web interface:
judging runs cost money and have to be citable as a protocol, which a command
with a configuration file is and a button is not. The judges are ordinary
reviewers to ReviQ; their votes enter through the decision import and the
conflict endpoint, so ReviQ's own behaviour does not change.
"""

__version__ = "0.1.0"
