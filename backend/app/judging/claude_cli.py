"""A judge backend that runs the Claude Code CLI in print mode (`claude -p`).

Philipp, 23.10.2026: the judges run with Claude, but without API calls from
this code. The CLI is Anthropic's own client and runs on the machine of the
person whose subscription it uses; this module only starts it, one process per
request, and stores what comes back in the same cache as any other backend.

What the flags buy, and why each is there:

- `--system-prompt` replaces Claude Code's own system prompt with the frozen
  prompt file, so the judge sees the instructions of the study and nothing else.
- `--tools ""` gives the judge no tools: it reads the record it is handed and
  cannot fetch anything else.
- `--json-schema` asks for output that validates against the task's schema.
- `--output-format json` returns one JSON object with the result and the token
  usage; it is stored verbatim.
- `--no-session-persistence` keeps no transcript of thousands of one-off calls.
- `--model` takes the exact model id from the study configuration; `config`
  refuses aliases.

`--bare` is deliberately absent: it restricts authentication to an API key,
which is exactly what this backend exists to avoid.

What this cannot do, compared with the API: no sampling parameters, no batch
discount, and throughput bounded by the subscription's usage limits. The cache
makes every answer replayable all the same, and run-to-run stability is
measured rather than assumed. The shape of the CLI's JSON output is taken from
a real run before the first study call (tests/judging/fixtures/); until then
only the raw text is relied on.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from .cache import Request, Response

DEFAULT_BINARY = "claude"
TIMEOUT_SECONDS = 300


class ClaudeCliError(RuntimeError):
    pass


def command(request: Request, system_prompt: str, schema: dict | None,
            binary: str = DEFAULT_BINARY) -> list[str]:
    argv = [binary, "-p", "--model", request.model, "--system-prompt", system_prompt,
            "--tools", "", "--output-format", "json", "--no-session-persistence"]
    effort = request.params.get("effort")
    if effort:
        argv += ["--effort", str(effort)]
    if schema is not None:
        argv += ["--json-schema", json.dumps(schema, separators=(",", ":"), sort_keys=True)]
    return argv


def user_message(request: Request) -> str:
    """The record goes in as data, tagged, never into the instructions: a source
    text that says 'ignore the above' is material to judge, not an order."""
    payload = json.dumps(request.input, ensure_ascii=False, sort_keys=True)
    return f"<record>\n{payload}\n</record>"


def _usage(raw: str) -> tuple[int | None, int | None]:
    try:
        usage = json.loads(raw).get("usage") or {}
    except (ValueError, AttributeError):
        return None, None
    return usage.get("input_tokens"), usage.get("output_tokens")


class ClaudeCli:
    """Implements `providers.Provider` with the Claude Code CLI."""

    name = "claude-cli"

    def __init__(self, system_prompt: str, schema: dict | None = None,
                 binary: str = DEFAULT_BINARY, runner=subprocess.run) -> None:
        if runner is subprocess.run and shutil.which(binary) is None:
            raise ClaudeCliError(f"{binary!r} not found; install Claude Code and log in first")
        self._system_prompt = system_prompt
        self._schema = schema
        self._binary = binary
        self._run = runner

    def call(self, request: Request) -> Response:
        result = self._run(
            command(request, self._system_prompt, self._schema, self._binary),
            input=user_message(request), capture_output=True, text=True,
            timeout=TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            # stderr can carry account details; keep it short and out of the cache.
            raise ClaudeCliError(f"claude exited with {result.returncode}: "
                                 f"{(result.stderr or '').strip()[:200]}")
        input_tokens, output_tokens = _usage(result.stdout)
        # No per-call price under a subscription; cost stays empty, tokens are kept.
        return Response(raw=result.stdout, input_tokens=input_tokens,
                        output_tokens=output_tokens, cost_usd=None)
