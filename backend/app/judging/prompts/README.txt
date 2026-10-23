Prompt files of the judging module, one per task, each with a front matter
naming the prompt and its version. `python -m app.judging prompts --freeze
<name>` records their hashes in `freeze.json`; a frozen prompt that changes
afterwards refuses to load (see `app/judging/prompts.py`).

The prompts themselves are written during calibration (WP4 onwards).
