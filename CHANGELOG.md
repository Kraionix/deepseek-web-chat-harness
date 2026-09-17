# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/).

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
