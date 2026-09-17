# Tests

The layout mirrors `src/dwch/`: a test file lives next to the module
it exercises.

- `shared/`, `domain/`, `application/` — unit tests for the module
  of the same name. No subprocess, no network.
- `application/commands/` — one file per `cmd_*` function.
- `integration/` — tests that span more than one module:
  `template_consistency.py` checks that the renderers produce
  parseable files; `lifecycle.py` runs a full session end to end.

`conftest.py` holds the shared fixtures: `project_root` (a real git
repository in `tmp_path`), `harness_root` (the same, plus
`.harness/config.toml` and a fresh state), and `deps` (`Deps` with
real filesystem and git, fakes for clipboard, process, and
tokenizer).

`fakes.py` holds the three small fakes plus `RenameFails`, a
`LocalFilesystem` subclass whose `rename` raises, used to test the
atomicity of `save_state`.

Run everything with:

```powershell
pytest -q
```
