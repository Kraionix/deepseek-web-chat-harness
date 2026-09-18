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

## Deletions and renames

Two optional keys make deletions and renames visible to the
planner. Both default to `[]`.

```toml
[[steps]]
number = 3
title = "Move storage out of models"
goal = "..."
files   = ["src/todo/storage.py"]
removes = ["src/todo/legacy.py"]
moves = [
  { from = "src/todo/models.py", to = "src/todo/models/__init__.py" },
]
interfaces = ["save", "load"]
acceptance = []
depends_on = [1]
```

`moves` is a list of inline tables `{ from, to }`, not pairs.
Readable, extensible if a third field ever becomes necessary.

## Rules

- `[meta].version` is a positive integer. A new roadmap replaces
  the old one; increment the version. A development session
  running under v1 keeps its own `roadmap_step`, which is reset
  when v2 is frozen.
- `[[interfaces]]` names must be unique and must be referenced by
  at least one step.
- `[[steps]].number` must be `1..N` with no gaps.
- `depends_on` must reference earlier steps only.
- `files`, `removes`, and `moves` use paths relative to the
  project root, POSIX-style.
- `acceptance` is prose. It is shown to the coder but not parsed.

### Intersection rules

Within one step:

- `removes` must not intersect `files`.
- `moves.from` must not intersect `files`.
- `moves.to` must not intersect `files`.
- `moves.from` must not intersect `removes`.
- `moves.from` values are unique; `moves.to` values are unique.
- No `from` equals a `to` (no chains `a→b`, `b→c`).

All comparisons are by normalized path.

## Validation

`dwch verify NN` runs a `roadmap-structure` check when the step
writes `roadmap.toml`. `dwch close --freeze` refuses to freeze a
structurally invalid roadmap.
