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
dwch bootstrap --clipboard
```

Then open a fresh web chat, paste the bootstrap, and let the model
generate steps. For each step:

```
dwch apply 05
dwch verify 05
```

`verify` commits the step, updates state, and writes the report to
`steps/report-05.txt`. Paste that report back into the chat. When the
phase is done:

```
dwch close
```

## What `init` creates

- `.harness/config.toml` — user-editable configuration.
- `.harness/state.toml` — current phase, step, commit timestamps.
- `.harness/handoff.md` — task description for the next chat.
- `.harness/session-protocol.md`, `step-format.md`, `report-format.md`,
  `toolbox.md` — protocol documents included in every bootstrap.
- `.harness/data/deepseek_tokenizer.json` — downloaded tokenizer.
- `.harness/.gitignore` — ignores only `data/`.
- `steps/.gitignore` — makes `steps/` self-ignoring.

`.harness/` (except `data/`) and `steps/` are meant to be committed
together with the project: they are the session's portable state and
its artifacts. The tokenizer file is local cache.

## The eleven commands

| Command | Purpose |
|---|---|
| `dwch init` | Install harness into the current project. |
| `dwch health` | Check environment and project state. |
| `dwch bootstrap` | Build the opening message for a new chat. |
| `dwch apply NN` | Parse a step message and write its files. |
| `dwch verify NN` | Run checks, commit, produce the report. |
| `dwch close` | Finalize the session, update state. |
| `dwch read PATH` | Wrap a file in step markers for the chat. |
| `dwch map` | Print the module interface map. |
| `dwch rollback` | Undo the last step. |
| `dwch new-phase NAME` | Start a new phase. |
| `dwch count PATH` | Count tokens in a file or tree. |

## Lifecycle

1. `init` writes the harness into `.harness/` and `steps/`.
2. `bootstrap` assembles the opening message from `.harness/` and
   the project source.
3. Each step: `apply` writes files, `verify` checks and commits.
4. `close` finalizes the phase, commits state, optionally tags.
5. `new-phase` starts the next phase.

`apply`, `verify`, `new-phase`, `close`, and `rollback` leave the
working tree clean. `verify` commits `state.toml` together with the
step's files; `new-phase` and `close` commit their own transitions.
`rollback` discards the last step's commit and commits the state
change on top.

## Step message format

The AI's reply for one step is one or more blocks of the form:

```
<<<FILE:relative/path.py>>>
<content verbatim>
<<<END>>>
```

Prose outside blocks is ignored. One step per AI message. Copy the
message, run `dwch apply NN`, then `dwch verify NN`, paste the report
back.

## Troubleshooting

- **`health` reports `git FAIL`** — the working tree has uncommitted
  changes. Run `git status` and resolve.
- **`apply` reports `parse error: no FILE blocks`** — the clipboard
  contained text without `<<<FILE:...>>>` markers. The command prints
  the first 200 characters of what it saw.
- **`bootstrap` prints `(no modules)`** — `map_root` in
  `.harness/config.toml` points at a directory that does not exist.
- **`verify` reports `commit skipped (required check failed)`** —
  a required check exited non-zero. The full report is in
  `steps/report-NN.txt`.
- **`close` or `new-phase` refuses with `working tree is dirty`** —
  commit or stash first. These commands assume a clean tree.

## What it is not

Not a build system. Not a test runner. Not a git wrapper. It does not
know your domain. It knows about files, steps, reports, and phases.

## License

MIT. See `LICENSE`.