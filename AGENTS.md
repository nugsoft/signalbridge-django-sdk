# Notes for AI coding agents

Guidance for agents working in a project that **uses** this SDK lives in:

    signalbridge/AGENTS.md

It sits inside the package rather than at the repository root so that it is
installed with the wheel and is present in any environment that has the SDK. It
is deliberately the only copy: duplicating it is how guidance drifts out of step
with the code.

## Pointing your agent at it

The installed path depends on the interpreter, so ask Python where it is:

```bash
python -c "import signalbridge, pathlib; print(pathlib.Path(signalbridge.__file__).parent / 'AGENTS.md')"
```

For Claude Code, one line in the project's `CLAUDE.md` is enough, and because the
path stays inside the working directory it needs no approval:

```md
@.venv/lib/python3.12/site-packages/signalbridge/AGENTS.md
```

Claude Code also reads a project's own `AGENTS.md` when there is no `CLAUDE.md`,
so the same line works there. If your environment lives outside the project —
Poetry, pipx, a container — copy the file in instead and re-copy it on upgrade:

```bash
cat "$(python -c 'import signalbridge, pathlib; print(pathlib.Path(signalbridge.__file__).parent / "AGENTS.md")')" >> AGENTS.md
```

For other tools (Cursor, Copilot, Codex, Windsurf), copy the contents into
whatever instructions file they read.

---

Working on the SDK **itself**? Three things are load-bearing:

- `signalbridge/segments.py` must agree with the gateway's
  `BalanceService::calculateSegments()` character for character. When they
  disagree, `estimate_cost()` quotes a figure the invoice will not match. Both
  sides carry the same test cases; change neither alone.
- Nothing in this package may retry a send. `SAFE_RETRY_METHODS` holds reads only:
  the gateway charges a message when it accepts one and there is no idempotency
  key, so a retried `POST` bills and delivers twice.
- Every test fakes the HTTP layer. A test that reaches the real gateway sends a
  real SMS and bills the account.

Run the suite with:

```bash
django-admin test tests --settings=tests.settings --pythonpath=.
```
