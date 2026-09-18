# Tests

The layout mirrors `src/dwch/`: a test file lives next to the module
it exercises.

- `shared/`, `domain/`, `application/` — unit tests for the module
  of the same name. No subprocess, no network.
- `application/commands/` — one file per `cmd_*` function.
- `integration/` — tests that span more than one module:
  `template_consistency.py` checks that the renderers produce
  parseable files; `lifecycle.py` runs a full session end to end.

`conftest.py` holds the shared fixtures:

- `project_root` — a real git repository in `tmp_path / "repo"`,
  copied from a session-scoped template. `core.autocrlf=false` and
  the git author/committer identity come from environment variables
  set at conftest import time, so no test pays for `git init` or
  `git config`.
- `harness_root` — the same, plus `.harness/config.toml` and a fresh
  state. Does not run `init`: no tokenizer is downloaded.
- `deps` — `Deps` with real filesystem and git, fakes for clipboard,
  process, and tokenizer.
- `broken_deps` — `deps` with a git port whose `commit_all` always
  raises. Used by tests that assert a lifecycle command restores
  state when the commit fails.

`fakes.py` holds five small helpers:

- `InMemoryClipboard`, `InMemoryProcess`, `InMemoryCounter` — the
  three port fakes used by every command test.
- `RenameFails` — a `LocalFilesystem` subclass whose `rename` raises,
  used to test the atomicity of `save_state`.
- `CommitFails` — a `CliGit` subclass whose `commit_all` raises, used
  to test state restoration in `verify`, `close`, and `new-phase`.

## Running

```powershell
pytest -q
```

For a parallel run:

```powershell
pytest -n 4 -q
```

For fast iteration, skipping the twenty end-to-end tests marked
`slow`:

```powershell
pytest -m "not slow"
```

The marker is registered in `pyproject.toml`. `--strict-markers` is
on, so an unregistered marker fails collection.
