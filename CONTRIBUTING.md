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
CI job; on a laptop it is a safe default. The default `addopts` do
not enable parallelism: a bare `pytest` should behave the same
everywhere.

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

## The contract

`.harness/contract.md` is the harness's user-facing contract. It
is shipped verbatim as the L1 bootstrap layer and is never
truncated. It carries:

- the block grammar (FILE / DELETE / MOVE, path safety, limits);
- the `plan.toml` schema (meta, interfaces, tasks);
- the `task` schema (id, title, goal, files, interfaces,
  acceptance, depends_on, removes, moves);
- the `deviation` schema (three types only);
- the `state.toml` schema (as seen by the AI);
- the six behavioral rules;
- the tool categories (Request / Produce / Suggest);
- the command list;
- the notes-vs-contract rule.

If you change the shape of the plan, task, deviation, or state,
update `contract.md` in the same commit. A regression test
(`tests/integration/test_template_consistency.py`) extracts every
field of `Task`, `Plan`, `Deviation`, and `State` from
`domain.models` and asserts it appears in `contract.md`. A missing
field is a failing test.

`contract.md` is the only template shipped by `init`. Older
templates (`session-protocol.md`, `step-format.md`,
`report-format.md`, the two handoffs, `roadmap-format.md`,
`deviation-format.md`, `toolbox.md`) were merged into it in 0.4.0
and are gone.

## Phase transitions

Every phase runs in its own chat. The contract is the phase's
intent; `state.toml` is the phase's state. There is no handoff and
no summary: the plan and the state are the whole cross-phase
record, and both are committed together with the code.

Two invariants guard the transition:

- `start` refuses to run while the previous phase is open. A phase
  is open when `state.phase_status == "open"`; it becomes closed
  when `done` finalizes the last task, or `abandon` marks it
  abandoned.
- `done` requires `state.verify.ok` for the current task. A
  re-`apply` resets the flag: a task that has been re-applied is
  not verified in its new form.

Both invariants are checked in a fixed order so a malformed state
cannot be papered over by skipping a step.

## Task ids

A task id is a slug: `^[a-z][a-z0-9-]*$`, unique within a plan,
≤40 chars. The id becomes a directory name under
`steps/{phase}/{task_id}/`, so the regex is stricter than the
filesystem would require on POSIX. Do not relax it: a task id that
contains a separator or a Windows-reserved name would corrupt the
steps tree.

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
- `apply` is atomic: validate everything before any write; roll
  back on partial failure.
- `save_state` is atomic: write temp, then rename.
- Lifecycle timestamps go through `state.now_iso`, which applies
  `state.TIMESTAMP_TIMESPEC`. Do not call `datetime.now` directly
  in a command.
