# Contributing

## Development install

```powershell
git clone https://github.com/Kraionix/deepseek-web-chat-harness
cd deepseek-web-chat-harness
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

`[dev]` adds `ruff`, `pytest`, `pytest-cov`, and `pytest-xdist`. No
other setup is needed: the test suite uses a real filesystem and a
real `git` in temporary directories, and never hits the network.

## Checks

```powershell
ruff check .
ruff format --check .
pytest -q
```

All three must pass. CI runs the same on Python 3.11 and 3.12, with
`pytest -n 4`.

## Test speed

The suite parallelizes through `pytest-xdist`. `-n 4` matches the
CI job; on a laptop it is a safe default, and on a machine with
more cores `-n auto` usually helps but is likelier to hit disk I/O
contention on Windows. The default `addopts` do not enable
parallelism: a bare `pytest` should behave the same everywhere.

End-to-end tests are marked `slow`. They exercise a full phase
transition and are the only place a lifecycle regression shows up;
run them before a commit. While iterating on a single module, skip
them:

```powershell
pytest -m "not slow"
```

The marker is registered in `pyproject.toml`; `--strict-markers` is
on, so an unregistered marker fails collection.

Setup cost is dominated by git. `tests/conftest.py` builds one
repository per session and copies it into every test's `tmp_path`,
and sets `GIT_AUTHOR_*` / `GIT_COMMITTER_*` in the environment so
no test pays for a `git config` call. Do not reintroduce
`git init` or `git config user.*` in a fixture: it costs roughly
125 ms per test on Windows.

## Coverage

`pytest --cov=dwch -q` prints a coverage report. There is no
enforced threshold yet; write tests that assert behaviour, not
coverage numbers.

## Style

- English only: code, comments, docstrings, commits.
- `from __future__ import annotations` at module top.
- `logging.getLogger(__name__)` at module level in library code.
- One concept per module. No `utils.py`, `helpers.py`, `base.py`.
- `X | None`, not `Optional[X]`. `list[X]`, not `List[X]`.
- Conventional Commits, no scope, prose body.

## Tests

- Real adapters on `tmp_path` for filesystem and git. No
  `InMemoryFilesystem`.
- Small fakes for clipboard, process, and tokenizer live in
  `tests/fakes.py`.
- One file per module under test. Cross-module scenarios go in
  `tests/integration/`.
- Docstring on every test, one line, saying what is checked.

## Handoff and summary contracts

Two documents carry intent across a phase boundary.

- **`.harness/handoff.md`** — written by the AI at the start of a
  phase. The file has two parts: the `harness:begin` ...
  `harness:end` block, owned by the harness and rewritten on every
  `close`, `new-phase`, and `apply`; and everything outside it,
  owned by the AI. Never edit inside the block; the harness will
  overwrite it. A handoff without the markers is repaired by
  `ensure_metadata`, which inserts the block at the top. A handoff
  with only one of the two markers, or with duplicate markers, is
  also repaired: the stray marker lines are removed and a fresh
  block is prepended.
- **`.harness/summaries/{phase}.md`** — written by the AI at the
  end of a phase via `dwch apply summary`. The harness refuses to
  overwrite an existing summary; delete the file first if you need
  to rewrite it. `dwch close` refuses to run without one.

`state.summary_phase` and `state.summary_written_at` record the
most recent summary. The bootstrap renders it as
`previous_summary`.

## Phase transitions

Every phase runs in its own chat. The handoff is the phase's
intent; the summary is the phase's outcome. The next phase's
bootstrap shows the most recent summary as `previous_summary`,
which is the only cross-phase context the AI receives.

Two invariants guard the transition:

- `new-phase` refuses to run while the previous phase is open,
  where "open" means `state.last_closed` is unset or is older than
  `state.last_opened`. The predicate is
  `rules.is_phase_closed`.
- `close` refuses to run twice on the same phase, and refuses to
  run without a summary file on disk.

Both invariants are checked in a fixed order so a malformed state
cannot be papered over by skipping a step.

## Step numbers

A step number is a positive integer. `1`, `01`, and `001` name the
same step. Every command that builds a step filename goes through
`format.format_step`, so `apply 1` and `verify 01` agree on
`step-01.txt`. Deviations use the same two-digit form.

## Architecture invariants

Do not break these without discussion:

- `domain` imports only stdlib.
- `application` imports `domain`, `shared`, its own submodules.
  Never `adapters`, never `cli`.
- `adapters` import `shared`, `application.ports`, and siblings.
  Never `application.commands`, never `cli`.
- `cli` imports everything.
- Ports are `Protocol`. Adapters satisfy them structurally.
- No Pydantic. Dataclasses for domain models.
- `apply` and `close` are atomic: validate everything before any
  write; rollback on partial failure.
- `save_state` is atomic: write temp, then rename.
- Lifecycle timestamps go through `state.now_iso`, which applies
  `state.TIMESTAMP_TIMESPEC`. Do not call `datetime.now` directly
  in a command.
