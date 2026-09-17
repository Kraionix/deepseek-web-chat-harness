# deepseek-web-chat-harness

A minimal agent harness for developing software in a web chat session,
where the model has no read access, no write access, no execution, and
no way to iterate. The user is the sole I/O channel: they copy messages
from the chat, run commands, and paste results back.

`dwch` (the CLI) closes that gap with eleven commands covering the full
session lifecycle: bootstrap the context, apply a step's files, verify
the result, commit, read a file on demand, roll back, start a new phase,
close the session. It also counts tokens precisely (using DeepSeek's
real BPE tokenizer) so the model knows whether a bootstrap fits.

Version 0.2.0 adds **roadmap-driven development**: a planning session
produces a machine-readable roadmap, `close --freeze` locks it, and a
development session executes it step by step, recording every deviation.

## Requirements

- Python 3.11 or newer (uses `tomllib` and `StrEnum`).
- `git` on `PATH` for `verify`, `close`, `new-phase`, and `rollback`.
- Optional: `ruff` if the default lint check is enabled in
  `.harness/config.toml`.
- Network access during `dwch init` to download the tokenizer from
  HuggingFace (about 8 MB). After that, the harness works offline.

## Install

```
pip install -e .
```

Only runtime dependency is `tokenizers` (HuggingFace).

## Quickstart

```
cd /path/to/your/project
dwch init
dwch health
dwch new-phase 00-architecture --kind planning
dwch bootstrap --clipboard
```

Then open a fresh web chat, paste the bootstrap, and let the model
produce design artifacts and a roadmap. When the planning phase is
done:

```
dwch close --freeze
```

Start the development phase:

```
dwch new-phase 01-implementation --kind development
dwch bootstrap --clipboard
```

For each roadmap step:

```
dwch apply 01
dwch verify 01
```

`verify` commits the step, updates state, and writes the report to
`steps/{phase}/report-01.txt`. Paste that report back into the chat.

## What `init` creates

- `.harness/config.toml` — user-editable configuration.
- `.harness/state.toml` — current phase, kind, step counters.
- `.harness/session-protocol.md`, `step-format.md`, `report-format.md`,
  `planning-handoff.md`, `development-handoff.md`,
  `roadmap-format.md`, `deviation-format.md`, `toolbox.md` —
  protocol documents included in every bootstrap.
- `.harness/data/deepseek_tokenizer.json` — downloaded tokenizer.
- `.harness/.gitignore` — ignores only `data/`.
- `steps/.gitignore` — makes `steps/` self-ignoring.

`.harness/` (except `data/`) and `steps/` are meant to be committed
together with the project: they are the session's portable state and
its artifacts. The tokenizer file is local cache.

`.harness/roadmap.toml` appears only after a planning phase writes
it. `.harness/roadmap.lock` appears only after `close --freeze`.

## The eleven commands

| Command | Purpose |
|---|---|
| `dwch init` | Install harness into the current project. |
| `dwch health` | Check environment and project state. |
| `dwch bootstrap` | Build the opening message for a new chat. |
| `dwch apply NN` | Parse a step message and write its files. |
| `dwch verify NN` | Run checks, commit, produce the report. |
| `dwch close` | Finalize the session, optionally freeze the roadmap. |
| `dwch read PATH` | Wrap a file in step markers for the chat. |
| `dwch map` | Print the module interface map. |
| `dwch rollback` | Undo the last step. |
| `dwch new-phase NAME` | Start a new phase (planning or development). |
| `dwch count PATH` | Count tokens in a file or tree. |

## Lifecycle

1. `init` writes the harness into `.harness/` and `steps/`.
2. `new-phase NAME --kind planning` starts a planning phase.
3. Each planning step: `apply` writes files, `verify` checks.
4. `close --freeze` validates the roadmap, writes
   `.harness/roadmap.lock`, marks state frozen, and commits.
5. `new-phase NAME --kind development` starts a development phase.
6. Each development step: `apply` writes files, `verify` runs the
   built-in roadmap checks and commits on success.
7. `close` finalizes the development phase.
8. A new architect session can produce a new roadmap version; the
   old one remains in git history.

## Step message format

The AI's reply for one step is one or more blocks of the form:

```
<<<FILE:relative/path.py>>>
<content verbatim>
