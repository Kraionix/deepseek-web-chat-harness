# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/).

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
