# Roadmap format

The roadmap is the machine-readable contract between a planning
session and a development session. It lives at
`.harness/roadmap.toml` and is frozen by `dwch close --freeze`.

The roadmap is not a document for humans. `docs/architecture.md` is
that. The roadmap is parsed, validated, hashed, and executed.

## Structure

```toml
[meta]
version = 1
note = "Short description."

[[interfaces]]
name = "Task"
kind = "class"                # "class" | "function" | "constant"
module = "src/todo/models.py"
signature = "class Task"
doc = "One task in the list."

[[steps]]
number = 1
title = "Models and storage"
goal = "Implement Task dataclass and JSON load/save."
files = ["src/todo/models.py", "src/todo/storage.py"]
interfaces = ["Task", "load", "save"]
acceptance = [
  "Task is a frozen dataclass with id, text, done.",
  "load returns [] for missing file.",
]
depends_on = []
```

## Rules

- `[meta].version` is a positive integer. A new roadmap replaces the
  old one; increment the version. A development session running
  under v1 keeps its own `roadmap_step`, which is reset when v2 is
  frozen.
- `[[interfaces]]` names must be unique and must be referenced by at
  least one step.
- `[[steps]].number` must be `1..N` with no gaps.
- `depends_on` must reference earlier steps only.
- `files` are relative to the project root.
- `acceptance` is prose. It is shown to the coder but not parsed.

## Validation

`dwch verify NN` runs a `roadmap-structure` check when the step
writes `roadmap.toml`. `dwch close --freeze` refuses to freeze a
structurally invalid roadmap.
