# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/).

## [0.2.2] - 2026-09-17

### Fixed

- `config._validate_relative_path` raises `ConfigError` instead of
  `TypeError` on a non-string value (e.g. `paths.steps = 5`).
- `config` validates the shape of `verify.commands` and
  `verify.planning_commands`: each entry must be a table with
  `command` as a list of strings. A string command such as
  `command = "ruff check"` is rejected at load time instead of
  being silently split into characters by `tuple(...)`.
- `verify` no longer silently drops a malformed roadmap. It warns
  on stderr, symmetric with `bootstrap`, and continues without the
  roadmap checks.
- `verify` refuses to run past the end of a frozen roadmap.
  `check_roadmap_step` now takes the roadmap and reports a missing
  expected step instead of skipping `roadmap-files` and
  `roadmap-interfaces` silently.
- `verify` converts a non-integer step argument into exit code 2
  with a message, instead of raising `ValueError` with a traceback.
- `apply` does the same for its step argument. Previously
  `dwch apply abc` created `step-abc.txt`.
- `verify._planning_checks` compares roadmap paths as
  `PurePosixPath` on both sides, so `.harness//roadmap.toml` is
  recognized as the same file as `.harness/roadmap.toml`.
- `health` no longer crashes on a malformed `.harness/roadmap.lock`;
  the failure is reported as a failed `roadmap` line.
- `map._walk` reads directory entries through the filesystem port
  instead of calling `Path.is_dir()` / `Path.is_file()` directly.
- `parse_step_message` rejects duplicate paths with `FormatError`.
- `roadmap.validate` reports duplicate interface names.

### Changed

- Three unused predicates are removed from `rules.py`:
  `can_verify_step`, `is_step_number_valid`, `roadmap_step_valid`.
  `is_roadmap_frozen` is kept and now used by `new-phase` and
  `verify` instead of reading `state.roadmap_frozen` directly.

### Internal

- `detect_marker_collision`'s docstring now states that a literal
  `<<<FILE:...>>>` inside content is safe: the parser tracks block
  state, so only a bare `<<<END>>>` line collides.
- `config._validate_commands` is a new helper that normalizes and
  validates the shape of `verify.commands` and
  `verify.planning_commands` in one place.
- `verify._load_roadmap_or_none` is a new helper that centralizes
  the warn-and-continue behaviour.
- `README.md` no longer refers to 0.2.0 as the version that
  introduced roadmap-driven development.

## [0.2.1] - 2026-09-17

### Fixed

- `apply` rollback now deletes files created by the failed
  operation instead of attempting a `git checkout` that silently
  fails for untracked paths.
- TOML serialization in `lock` and `deviations` now escapes the
  full basic-string character set, including DEL. A `reason`
  containing a newline or a control character no longer produces
  an unparseable file.
- `config` validation now covers every path-typed key
  (`context.essential`, `context.references`, `context.map_root`,
  `paths.*`, `roadmap.*`), not only `context.architecture`.
- `roadmap.validate` rejects absolute paths and `..` in
  `step.files` and `interface.module`.
- `new-phase` converts a `HarnessError` from roadmap resolution
  into exit code 2 instead of propagating.
- `bootstrap` warns on stderr when a roadmap file exists but
  cannot be parsed, instead of silently dropping the section.
- `apply --from-file` resolves relative paths against the project
  root, not the current working directory.
- `module_map` now reports module-level `AnnAssign` constants.
- `verify`'s `check_compile` reads through the filesystem port
  and drops dead stdout/stderr redirects.

### Changed

- Commands no longer receive a `Config` parameter; each loads
  what it needs. `CommandFn` is now `Callable[[Args, Deps], int]`.
- `verify` and `apply` go through `FilesystemPort` for all file
  operations. Previously four call sites bypassed the port.
- Phase-kind checks use `rules.is_planning_phase` /
  `is_development_phase` / `is_unset_phase` uniformly instead of
  string comparisons scattered across commands.
- `GitPort` gains `try_head`, replacing two identical private
  helpers in `close` and `new_phase`.
- `context` uses `deps.git.try_head` for the header instead of
  its own try/except.

### Removed

- `templates/config.toml` and `templates/state.toml`. Neither was
  read by code; the authoritative renderers are `config_to_toml`
  and `state._render_state`.

### Internal

- `is_state_consistent` is now used by `health`; it also validates
  `phase_kind` against the enum.
- `_HARNESS_VERSION` renamed to `_CONFIG_FORMAT_VERSION` and
  `_STATE_FORMAT_VERSION` to reflect what it versions. Values
  remain `"0.2.0"` — the file formats did not change.
- New `shared/toml.py` with `escape_basic_string`, used by
  `lock.render` and `deviations.render`.
- Late imports in `context`, `init`, and `verify_checks` lifted
  to module top.

## [0.2.0] - 2026-09-17

### Added

- Roadmap-driven development. A planning phase produces
  `.harness/roadmap.toml`; `close --freeze` validates and locks it;
  a development phase executes it step by step.
- `new-phase --kind {planning,development}`. The phase kind drives
  the bootstrap and verify behaviour and is stored in `state.toml`.
- `close --freeze`. Writes `.harness/roadmap.lock`, a TOML file with
  SHA-256 hashes of the roadmap and architecture documents, and
  marks state as frozen.
- Four new application modules: `roadmap.py`, `lock.py`,
  `deviations.py`, `verify_checks.py`.
- Deviations. The coder records departures from the roadmap as TOML
  files under `.harness/deviations/`; `verify` writes auto-detected
  file-set mismatches.
- New built-in verify checks: `roadmap-step` (required),
  `roadmap-files`, `roadmap-interfaces`, `architecture-lock`,
  `roadmap-structure` (planning only).
- New bootstrap sections in a development phase: `architecture`,
  `current_step`, `interfaces`, `roadmap_summary`,
  `deviations_summary`.
- Two handoff templates: `planning-handoff.md` and
  `development-handoff.md`, chosen by `new-phase --kind`.
- `roadmap-format.md` and `deviation-format.md` protocol documents.
- `state.toml` gains `[phase].kind`, `[roadmap]`, `[rollback]`.
- `config.toml` gains `[roadmap]`, `context.architecture`, and
  `verify.planning_commands`.

### Changed

- **Breaking:** step artifacts live under `steps/{phase}/`.
  `state.current_step` is reset by `new-phase`, while
  `state.roadmap_step` is reset only by `close --freeze`.
- **Breaking:** `state.toml` no longer has `[step].total`.
- **Breaking:** `config.toml` requires `[harness].version = "0.2.0"`.
  Old configs are rejected; run `dwch init --force`.
- **Breaking:** `handoff.md` is split into `planning-handoff.md` and
  `development-handoff.md`. The metadata block gains `kind`,
  `roadmap_version`, `roadmap_step`, and `frozen` fields.
- `verify` delegates to `verify_checks.py`. Checks now include the
  roadmap ones, in a fixed order.
- `rollback` reloads state from disk after `git reset --hard` and
  increments `state.rollback_count` so the marker commit is
  non-empty.
- `health` prints a `roadmap` line and includes `kind` in the
  `state` line.

### Removed

- `.harness/phase.toml` is no longer written or read.
- `templates/handoff.md` is replaced by `development-handoff.md`.

## [0.1.0] - 2026-09-17

### Added

- Initial release.
- Eleven CLI commands: `init`, `health`, `bootstrap`, `apply`,
  `verify`, `close`, `read`, `map`, `rollback`, `new-phase`, `count`.
- Four-layer architecture (`shared`, `domain`, `application`,
  `adapters`) with dependency inversion through ports.
- Five ports: filesystem, clipboard, process, git, tokenizer.
- DeepSeek BPE token counter for accurate context sizing.
- Seven project-side templates installed by `init`.
- Atomic `apply` and `close` operations with best-effort rollback.
- Atomic `state.toml` writes: temp file then rename.
- `steps/` is self-ignoring.
- `verify` commits `state.toml` together with the step's files.
- Windows, Linux, and macOS clipboard support.
