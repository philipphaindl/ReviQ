"""Entry point, so Creel is runnable the way the CLI used to be.

    python -m app.retrieval run "AI maturity model" --pages 5

The `glr` console script is gone with the standalone repository. This keeps the
same surface without a packaging step, and it is the form the retrieval job in
`app/routers/` will spawn.
"""

from .cli import main

raise SystemExit(main())
