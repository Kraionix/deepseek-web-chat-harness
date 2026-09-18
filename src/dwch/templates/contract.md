# Harness contract

## Block grammar

Three block kinds. Each opens on its own line, closes with a line containing only `<<<END>>>` (trailing whitespace tolerated).

- `<<<FILE:relative/path>>>` — body is the file content verbatim.
- `<<<DELETE:relative/path>>>` — body must be empty.
- `<<<MOVE:src:dst>>>` — body must be empty. Exactly one `:` separating two non-empty relative paths.

Paths: relative, no leading `/`, no `..`, no `.` component, no component starting or ending with a space or ending with a dot, no `< > : " | ? *`, no control characters, no Windows reserved names (CON, NUL, COM1...), ≤255 bytes per component, no symlinks. Any path may appear in at most one op.

Limits: 50 MiB per message, 10 MiB per file.

## Plan schema

`plan.toml` is the contract between planning and development.

    [meta]
    version = 1
    note = "Short description."

    [[interfaces]]
    name = "load_schema"
    kind = "function"
    module = "src/x/schema.py"
    signature = "def load_schema(path: Path) -> Schema"
    doc = "One line."

    [[tasks]]
    id = "models"
    title = "Short title"
    goal = "What this task achieves."
    files = ["src/x/schema.py"]
    interfaces = ["load_schema"]
    acceptance = ["Schema is a frozen dataclass."]
    depends_on = []
    removes = []
    moves = []

Rules: `meta.version` ≥ 1, increments per plan. Every interface used by ≥1 task. `depends_on` refers to existing ids, no cycles. Within a task, `removes`, `moves.from`, `moves.to` do not intersect `files`; `moves.from` does not intersect `removes`; `moves.from` unique; `moves.to` unique; no `from == to`; no chains.

Task `id` matches `^[a-z][a-z0-9-]*$`, unique, ≤40 chars.

## Task schema

Fields: `id`, `title`, `goal`, `files`, `interfaces`, `acceptance`, `depends_on`, `removes`, `moves`.

Plan fields: `meta` (with `version`, `note`), `interfaces`, `tasks`.

Interface fields: `name`, `kind`, `module`, `signature`, `doc`.

Task granularity is your call. One task per logical change. Split a task when it exceeds ~10 files, touches more than two modules, or has heterogeneous acceptance criteria.

## Deviation schema

One file per task: `.harness/deviations/{task_id}.toml`.

    [[deviation]]
    type = "assumption"
    affected = ["src/x/foo.py"]
    reason = "Why."
    detail = ""

Fields: `type`, `affected`, `reason`, `detail`. An internal `auto` flag exists on the model for historical reasons and is always false in 0.4.0; you never write it.

- `blocker` — task impossible. Task closes deviated; follow-up queued.
- `assumption` — spec incomplete, you decided. Task is done.
- `plan-correction` — spec wrong. Task closes deviated; next phase must be planning.

No other types. File-set mismatches (extra/missing/extra-removal/missing-removal/extra-move/missing-move) are check failures, not deviations.

## State schema

State lives in `.harness/state.toml`, written by the harness. You see a projection in the session-state layer. The full set of fields:

- Phase: `phase_name`, `phase_kind`, `phase_status`, `phase_opened_at`, `phase_closed_at`.
- Plan: `plan_version`, `plan_sha256`, `plan_position`, `plan_frozen`.
- Verify: `verify_ok`, `verify_task_id`, `verify_at`.
- Failure: `failure_task_id`, `failure_check_name`, `failure_excerpt`, `failure_count`.
- Rollback: `rollback_count`.
- Session: `last_commit`, `last_commit_date`.
- Harness: `harness_version`.

You do not write state; the harness does.

## Behavioral rules

1. Emit only FILE/DELETE/MOVE blocks. Never describe an edit in prose.
2. Never ask the user to edit files by hand.
3. To read a file, ask for `dwch read PATH`.
4. Declare deviations explicitly. Do not hide failures.
5. Notes are softer than this contract. If they conflict, the contract wins; say so.
6. One task at a time. Do not advance without `dwch done`.

## Tool categories

- Request (read-only): `read`, `map`, `tree`, `status`, `log`, `count`.
- Produce (your output is applied): `apply`.
- Suggest (you propose; user decides): `verify`, `done`, `fix`, `abandon`.

You have no access to `init`, `rollback`, `git`, or direct file editing.

## Commands

`init`, `start`, `next`, `apply`, `verify`, `done`, `fix`, `abandon`, `status`, `log`, `health`, `read`, `map`, `tree`, `count`, `rollback`.

## Notes vs contract

Notes (`.harness/notes.md`) describe the project: conventions, external APIs, style. This contract describes the harness: block grammar, schemas, path safety. A note cannot override the block grammar. If notes require something the contract forbids, follow the contract and tell the user.
