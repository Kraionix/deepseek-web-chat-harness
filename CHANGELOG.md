# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/).

## [0.3.2] - 2026-09-18

Test-infrastructure release. No user-facing behaviour changes:
`config.toml` and `state.toml` keep the `"0.3.0"` format version,
and no command behaves differently. The point is the test suite.

### Changed

- Test suite runs 3.5× faster on a full `pytest -n 4` run and
  5.8× faster with `-m "not slow" -n 4`. On Windows the sequence
  is 28.1 s (baseline) → 17.2 s (serial) → 7.9 s (parallel) →
  4.9 s (fast parallel). `pytest-xdist` parallelizes with `-n 4`
  (matching the CI job); a session-scoped git template replaces
  the per-test `git init` plus three `git config` calls; git
  identity and `core.autocrlf` are supplied through environment
  variables.
- New `slow` pytest marker on the twenty end-to-end tests that the
  0.3.1 benchmark put above 0.2 seconds. `pytest -m "not slow"`
  runs 297 of 317 tests in a fraction of the time, for local
  iteration.
- CI runs `pytest -n 4 -q`.
- `[dev]` extras gain `pytest-xdist>=3.5`.

### Internal

- `tests/conftest.py` builds one git repository per session
  (`_git_template`) and `copytree`s it into each test's
  `tmp_path / "repo"`. The per-test git cost drops from six
  subprocesses to a directory copy.
- `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and
  `GIT_COMMITTER_EMAIL` are set at conftest import time through
  `os.environ.setdefault`, and `core.autocrlf=false` is appended to
  `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_*`/`GIT_CONFIG_VALUE_*`, so no
  test pays for a `git config` call.
- The template copies are made writable (`_make_writable`) to clear
  the read-only bit that git sets on loose objects and `copytree`
  preserves.
- `slow` is registered in `[tool.pytest.ini_options].markers`;
  `--strict-markers` is on, so an unregistered marker fails
  collection.

## [0.3.1] - 2026-09-18

Patch release. No format changes: `config.toml` and `state.toml`
keep the `"0.3.0"` format version, and existing projects keep
working after upgrading the package.

### Fixed

- **Malformed user TOML could crash four commands with a
  traceback.** `roadmap.load`, `lock.load`, and `deviations.parse`
  iterated list-typed fields without checking their shape. A string
  where a list was expected produced an `AttributeError`, which is
  not a `HarnessError` and was not caught. `dwch health`,
  `dwch bootstrap`, `dwch verify`, and `dwch close --freeze` all
  crashed on such a file. All three parsers now coerce through
  `shared.toml.list_of_tables` / `list_of_strings` and raise their
  own error type.
- **`rollback` could roll back a lifecycle commit.**
  `current_step` in a resumed development phase is greater than
  zero, so the old guard (`current_step <= 0`) let `rollback` reset
  past a `chore: start ... phase ...` or a `chore: close phase ...`
  commit, taking the phase with it. `rollback` now checks the
  subject line of `HEAD` and only accepts a commit whose subject
  starts with `step `.
- **Step filenames were inconsistent across commands.**
  `apply 1` wrote `step-1.txt`, `verify 01` looked for
  `step-01.txt`, and `deviations.load_step` always used
  `step-01.toml`. A deviation written as `step-1.toml` was silently
  ignored. Every command now goes through `format.format_step`.
- **Reports were sorted lexicographically.** `report-2.txt` sorted
  after `report-10.txt`; `[-n:]` picked the wrong "most recent"
  reports. The sort key now extracts the numeric step.
- **`dwch init --force` did not do what it promised.**
  `_write_config` and `_write_templates` returned early when the
  target existed, so a version-mismatch error that told the user to
  run `init --force` could not be resolved that way. `--force` now
  overwrites `config.toml` and the shipped templates, and
  re-downloads the tokenizer instead of trusting a possibly
  truncated cache. `state.toml`, `.harness/.gitignore`, and
  `.harness/handoff.md` are still preserved.
- **`dwch init` printed errors to stdout.** Two call sites in
  `cmd_init` used plain `print`. They now write to stderr, matching
  every other command.
- **`dwch apply summary` overwrote existing summaries.**
  `CONTRIBUTING.md` promised append-only behaviour. `_apply_summary`
  now refuses to write when the target file exists.
- **`handoff.ensure_metadata` accumulated stale blocks.** The
  `partition`-based implementation left a stray `BEGIN` or `END`
  marker in place when the AI produced only one of the two, and
  did not handle duplicate markers. The regex-based version removes
  every stray marker line and inserts a single fresh block.
- **`rollback` wrote a second-precision timestamp.** Every other
  command uses `state.now_iso`, which applies
  `state.TIMESTAMP_TIMESPEC` (microseconds). All commands now share
  the constant.
- **Phase name validation missed control characters.**
  `_INVALID_NAME_CHARS` did not include `\n`, `\t`, or other C0
  control characters. A name such as `"a\nb"` passed and corrupted
  `handoff.md` and `state.toml`. Validation moved to
  `rules.phase_name_error`, which rejects any control character.
- **`bootstrap` could report `(truncated)` without truncating.**
  `_truncate` returned `truncated=True` unconditionally. It now
  reports True only when at least one section was removed.
- **`[-n:]` with `n == 0` returned the whole list.** Affected
  `context._current_phase_reports`, `deviations.load_recent`, and
  `deviations.summarize`. A config with
  `bootstrap.reports_current_phase = 0` now shows none, as the
  user asked.
- **`lock.check` could read files outside the project.** A
  hand-edited `roadmap.lock` with a `path = "../../etc/passwd"`
  entry was read and hashed. Unsafe paths are now reported as
  drift without being opened.
- **`health` reported a failure for a git worktree.** A linked
  worktree or a submodule has a `.git` file, not a directory.
  `_check_git` now accepts either.
- **`verify` could leave the tree dirty after a failed commit.**
  State had already been saved and auto-deviations written. On
  commit failure, state is now restored and the auto file removed;
  the command exits non-zero and the report still explains the
  checks.
- **`close` could leave the tree dirty after a failed commit.**
  Same pattern; state and the handoff block are restored and the
  command exits 2.
- **`new-phase` wrote `handoff.md` before saving state.** A
  failure between the two left the handoff from the new phase and
  the state from the old. The order is now state first, then
  handoff, and a failed commit restores both.
- **`verify` did not re-validate paths from the on-disk step file.**
  A step message edited by hand after `apply` was parsed without
  the path checks that `apply` applies. `validate_paths` runs
  again.
- **`verify` silently skipped roadmap checks when the file was
  missing.** If `state.roadmap_frozen` was true but
  `roadmap.toml` had been deleted, all roadmap checks were
  skipped. A required `roadmap-missing` check now fails the step
  and appears in the report.
- **`read` mishandled absolute glob patterns.** `dwch read
  "/tmp/*.py"` went through `Path.glob`, which does not support
  absolute patterns. It now fails with one clear message.
- **`module_map` lost parameter annotations and defaults.**
  `def f(a: int, b: str = "x") -> None` rendered as
  `def f(a, b) -> None`. The map now includes annotations,
  positional defaults, and keyword-only defaults. Tuple targets
  in `a, b = 1, 2` are also recognized.
- **`config` had an unused `phases` key.** Removed from
  `_DEFAULT_PATHS` and from the rendered config template.

### Changed

- `apply summary` is append-only and refuses to overwrite.
- `apply`, `verify`, and `read` accept any positive integer step
  number and canonicalize it.
- `init --force` now overwrites `config.toml`, the templates, and
  the tokenizer cache.
- `init` uses a `User-Agent` header when downloading the tokenizer.
- Step message parser tolerates trailing whitespace on marker
  lines.
- `context._task` strips the `harness:begin`/`harness:end` block
  from the handoff before embedding it in the bootstrap: `header`
  already shows the same values.
- `context._recent_commits` catches `HarnessError`, not
  `Exception`.
- `adapters/clipboard.py` no longer imports `ClipboardError` for a
  no-op re-export.
- `README.md` and `session-protocol.md` say "twelve commands" to
  match the README table.
- `CONTRIBUTING.md` rewords the summary contract to match the code
  and documents step-number canonicalization and the timestamp
  invariant.

## [0.3.0] - 2026-09-18

### Added

- Phase summaries. Each phase ends with a file at
  `.harness/summaries/{phase}.md` written by the AI. The next
  phase's bootstrap shows the most recent summary as the only
  cross-phase context.
- `dwch apply summary`, a second form of the existing `apply` that
  writes the phase summary from a single file block.
- `bootstrap.previous_summary`, a new section rendering the summary
  named by `state.summary_phase`. It appears in both planning and
  development bootstraps.
- `handoff.ensure_metadata`, which guarantees the
  `harness:begin` block is present and current. It inserts the
  block at the top when the markers are missing, and replaces it
  in place when they are present.
- `health` reports the summary state on a non-critical line.
- `rules.is_phase_closed`, a pure predicate over `State` shared by
  `close` and `new-phase`.

### Changed

- **Breaking:** `state.toml` gains a `[summary]` section with
  `phase` and `written_at`. `State` gains `summary_phase` and
  `summary_written_at`. `load_state` rejects a file whose
  `[harness].version` does not match.
- **Breaking:** `config.toml` requires
  `[harness].version = "0.3.0"`. `bootstrap.recent_reports` is
  replaced by `bootstrap.reports_current_phase`, scoped to the
  current phase.
- **Breaking:** `close` requires a summary for the current phase
  and refuses to run twice on the same phase.
- **Breaking:** `new-phase` refuses to run while the previous
  phase is open, and refuses to reuse an existing phase name.
- **Breaking:** `is_substantive` exempts `.harness/handoff.md` and
  `.harness/summaries/` in addition to `.harness/deviations/`. A
  step that only rewrites the handoff or the summary does not
  advance `roadmap_step`.
- The bootstrap's `recent_reports` section is now scoped to the
  current phase. Cross-phase reports are no longer shown; the
  previous phase's summary carries the cross-phase context
  instead.
- `_TRUNCATION_PRIORITY` drops `previous_summary` last, after
  `recent_reports`, `module_map`, `commits`, `roadmap_summary`,
  and `deviations_summary`. Cross-phase intent is more important
  than any within-phase fact.
- Handoff templates lose the `## Next` section and gain an HTML
  comment above `harness:begin` explaining the block's ownership.
- `session-protocol.md` gains a "Phase transitions" section.
- `toolbox.md` gains a row for `dwch apply summary`.

### Removed

- Config key `bootstrap.recent_reports`. Use
  `bootstrap.reports_current_phase`.
- Template section `## Next` from both handoff templates.
- `handoff.update_metadata`; replaced by `handoff.ensure_metadata`.

## [0.2.3] - 2026-09-17

### Added

- Test suite covering every module under `src/dwch/` and every
  command, plus a full lifecycle test from `init` through
  `close --freeze` to a second phase. Uses real filesystem and git
  adapters on `tmp_path`; three small fakes for clipboard, process,
  and tokenizer.
- GitHub Actions workflow running ruff, ruff format check, and
  pytest on Python 3.11 and 3.12.
- `CONTRIBUTING.md` with the dev workflow and the architectural
  invariants.
- `pytest`, `pytest-cov` as dev dependencies; `[tool.pytest.ini_options]`
  with `testpaths`, `addopts`, and `pythonpath`.

### Fixed

- **Commands could not be imported.** Six modules imported
  `..rules` (resolving to the nonexistent
  `dwch.application.rules`) instead of `...domain.rules`. The bug
  lived since 0.2.0 and was invisible to ruff, which does not
  resolve imports. Affected: `apply`, `close`, `health`,
  `new_phase`, `verify`, and `context`.
- **Absolute paths were accepted on Windows.** `Path("/abs").is_absolute()`
  returns False on Windows, so config values like
  `paths.steps = "/abs"`, roadmap `module = "/abs.py"`, and step
  message paths starting with `/` slipped past validation. The
  three validators now reject a leading `/` or `\` explicitly, on
  every platform.

### Changed

- No user-facing behaviour changes beyond the two fixes above.

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
