# deepseek-web-chat-harness

A minimal agent harness for developing software in a web chat
session, where the model has no read access, no write access, no
execution, and no way to iterate. The user is the sole I/O channel:
they copy messages from the chat, run commands, and paste results
back.

`dwch` (the CLI) closes that gap with sixteen commands covering the
full session lifecycle: bootstrap the context, apply a task's
files, verify the result, commit, read a file on demand, roll back,
start a new phase, close the session. It also counts tokens
precisely (using DeepSeek's real BPE tokenizer) so the model knows
whether a bootstrap fits.

## What 0.4.0 is

0.4.0 turns the harness from a protocol description into an agent
workspace.

- **`state.toml` is the single source of truth.** There is no
  `handoff.md` and no separate lock file. The frozen plan's hash
  lives in state.
- **The bootstrap is six ordered layers.** L0 meta, L1 contract,
  L2 tools, L3 session state, L4 context, L5 current task, L6
  notes. L1 is never truncated.
- **A plan is a list of tasks keyed by id**, not numbered steps.
  The AI decides task granularity; the contract explains the
  rule.
- **A failed verification is a working state.** `verify` writes
  the report, increments `state.failure.count`, and puts a short
  hint on the clipboard. `dwch fix` produces a fix-bootstrap for a
  fresh chat. At three consecutive failures, a warning is added to
  both.
- **One contract document.** `contract.md` carries the block
  grammar, the plan/task/deviation schemas, the behavioral rules,
  the tool categories, and the notes-vs-contract rule. It is
  never truncated.

## Requirements

- Python 3.11 or newer (uses `tomllib` and `StrEnum`).
- `git` on `PATH` for `done`, `start`, `abandon`, `rollback`,
  `log`, and any command that reads HEAD.
- Optional: `ruff` if the default lint check is enabled in
  `.harness/config.toml`.
- Network access during `dwch init` to download the tokenizer from
  HuggingFace (about 8 MB). After that, the harness works offline.

## Install

```
pip install -e .
```

Only runtime dependency is `tokenizers` (HuggingFace).

For development, install the dev extras:

```
pip install -e ".[dev]"
```

This adds `ruff`, `pytest`, and `pytest-cov`. Run the checks with:

```
ruff check .
ruff format --check .
pytest -q
```

The test suite uses real filesystem and git adapters on a temporary
directory and never touches the network.

## Quickstart

```
cd /path/to/your/project
dwch init
dwch health
dwch start "design the API"
dwch next
```

`dwch next` copies a bootstrap to the clipboard. Open a fresh web
chat, paste it, and let the model produce design artifacts and a
plan. For each task:

```
dwch apply          # reads the message from the clipboard
dwch verify         # runs checks; hints to clipboard on failure
dwch done           # commits task {id}: applied and verified
```

When the last task in a planning phase is done, the plan is
hashed and frozen automatically; when it is done in a development
phase, the plan position advances.

## What `init` creates

- `.harness/config.toml` — user-editable configuration.
- `.harness/state.toml` — phase, plan position, verify result.
- `.harness/contract.md` — the contract, included in every
  bootstrap as L1.
- `.harness/data/deepseek_tokenizer.json` — downloaded tokenizer.
- `.harness/.gitignore` — ignores only `data/`.
- `steps/.gitignore` — makes `steps/` self-ignoring.

`.harness/` (except `data/`) and `steps/` are meant to be committed
together with the project: they are the session's portable state
and its artifacts. The tokenizer file is local cache.

`dwch init --force` regenerates the files the harness owns and can
safely rebuild: `config.toml`, `contract.md`, and the tokenizer
cache. It does not touch `state.toml` or `.harness/.gitignore`.

## The sixteen commands

| Command | Purpose |
|---|---|
| `dwch init` | Install harness into the current project. |
| `dwch start "goal"` | Begin a phase. Kind inferred unless `--kind`. |
| `dwch next` | Assemble the current task's bootstrap; copy to clipboard. |
| `dwch apply` | Parse a block message and execute its ops. |
| `dwch verify` | Run checks, write the report, hint on failure. |
| `dwch done` | Commit the current task; close the phase on the last one. |
| `dwch fix` | Assemble a fix-bootstrap for the last failure. |
| `dwch abandon` | Mark the phase abandoned; leave the files. |
| `dwch status` | Print the current state. |
| `dwch log [N]` | Recent lifecycle events from git. |
| `dwch health` | Environment and project sanity. |
| `dwch read PATH` | Wrap a file in block markers for the chat. |
| `dwch map [ROOT]` | Module interface map. |
| `dwch tree [ROOT]` | Directory tree. |
| `dwch count PATH` | Count tokens in a file or tree. |
| `dwch rollback` | Undo the last `task ...` commit. |

## Lifecycle

1. `init` writes the harness into `.harness/` and `steps/`.
2. `start "goal"` opens a planning phase.
3. Each task: `apply` writes files, `verify` checks.
4. `done` commits. When the plan is on disk and valid, the phase
   closes and the plan is frozen.
5. `start "goal"` (now inferred as development) opens the
   development phase.
6. Each task: `apply`, `verify`, `done`. On the last task, the
   phase closes.
7. `start "goal"` opens a fresh planning phase for the next
   version.

## Block message format

A message contains one or more blocks. Three block kinds exist:
file, delete, and move.

A file block opens with `<<<FILE:relative/path.py>>>`, with the
file content verbatim, and closes with a line containing only
`<<<END>>>`.

A delete block opens with `<<<DELETE:relative/path.py>>>`, with an
empty body (whitespace only), and closes with the end marker.

A move block opens with `<<<MOVE:relative/from.py:relative/to.py>>>`,
with an empty body, and closes with the end marker. `MOVE` takes
exactly two paths separated by a single colon.

Every path is checked before any write: relative, no `..`, no
symlink components, no reserved names. A task that touches a
tracked file with uncommitted changes is refused.

## Bootstrap layers

```
L0  Meta           ~50 tokens         never truncated
L1  Contract       ~1200 tokens       never truncated
L2  Tools          ~200 tokens        never truncated
L3  Session state  facts              never truncated
L4  Context        variable           truncated first
L5  Current task   variable           never truncated
L6  Notes          variable           truncated second
```

Truncation order: L6 first, then L4 (notes, essential, module_map,
commits, reports). L1 is never truncated: the contract always
fits.
