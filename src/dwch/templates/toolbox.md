# Toolbox

The user has these commands available. Ask for the ones you need.

| Command | What it does |
|---|---|
| `dwch health` | Check the environment and roadmap state. |
| `dwch bootstrap --clipboard` | Rebuild the opening message. |
| `dwch apply NN` | Write the files of step NN. |
| `dwch verify NN` | Run checks, commit, produce the report. |
| `dwch read PATH --clipboard` | Send a file into the chat. |
| `dwch map --clipboard` | Send the module interface map. |
| `dwch map --tree --clipboard` | Map plus a directory tree. |
| `dwch rollback --yes` | Undo the last step. |
| `dwch new-phase NAME --kind planning` | Start a planning phase. |
| `dwch new-phase NAME --kind development` | Start a development phase. |
| `dwch close --freeze` | Freeze the roadmap at the end of a planning phase. |
| `dwch close` | Finalize the session. |
| `dwch count PATH` | Count tokens in a file or tree. |

## When to ask

- **Read a file**: `dwch read src/foo/bar.py --clipboard`.
- **See the map**: `dwch map --clipboard`.
- **Run something ad hoc**: ask the user to run it and paste the
  output. Do not assume a command exists.
- **Undo**: only when a step is wrong and the next step cannot
  cleanly fix it.

## What you cannot ask for

- Network access. The harness has none.
- File deletion. Steps only write. To remove a file, overwrite it
  with empty content, or ask the user to delete it manually.
- Push, pull, or any remote git operation.
- Anything that opens a UI or a browser.
