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

- `project_root` — a real git repository in `tmp_path`, with one
  commit. `core.autocrlf=false` keeps line endings stable across
  hosts.
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

Run everything with:

```powershell
pytest -q
```
