# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/).

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
- Atomic `state.toml` writes: temp file then rename, so a crash
  mid-write never leaves a partial state file.
- `steps/` is self-ignoring: session artifacts (step messages,
  apply logs, reports) do not leak into step commits.
- `verify` commits `state.toml` together with the step's files, and
  refuses a step whose message contained no FILE blocks.
- `apply` prints the first 200 characters of the message on parse
  error, so an empty or malformed clipboard is diagnosable.
- Windows, Linux, and macOS clipboard support.
- `new-phase`, `close`, and `rollback` commit their own bookkeeping,
  keeping the working tree clean between commands.