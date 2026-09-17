"""`dwch verify NN` — run checks, commit, produce the report.

The report is written to `steps/report-NN.txt` and optionally copied
to the clipboard. It is the only channel through which the AI learns
what happened, so it is deliberately complete: every check's full
stdout and stderr, and the commit hash on success.

On any required check failing, the commit is skipped but the report
is still written. The AI needs to see the failure to fix it.

On success, `verify` also updates `state.toml` (`current_step`,
`total_steps`, `last_commit_date`) before committing, so the state
file is included in the same commit as the step's files. It does
not touch `last_commit` — that field is refreshed by `close` and
`new-phase`, which know the hash of the commit they just made.
"""

from __future__ import annotations

import io
import sys
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime

from ...domain.models import CheckResult, FileSpec, Report, State
from ...shared.errors import FormatError, HarnessError
from ..config import load_config
from ..deps import Deps
from ..format import (
    parse_step_message,
    render_report,
    summarize_check,
)
from ..state import load_state, save_state


def cmd_verify(args: Namespace, deps: Deps, _config) -> int:
    """Verify a step. Returns 0 on success, 1 on check failure, 2 on error."""
    try:
        config = load_config(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    steps_dir = deps.project_root / config.paths.get("steps", "steps")
    step_file = steps_dir / f"step-{args.step}.txt"
    apply_log_path = steps_dir / f"apply-{args.step}.log"

    if not deps.fs.exists(step_file):
        print(f"error: {step_file} not found; run `apply` first", file=sys.stderr)
        return 2

    step_text = deps.fs.read_text(step_file)
    specs = _parse_step_or_none(step_text)
    if specs is None:
        print(
            f"error: {step_file.name} contains no valid FILE blocks. "
            "The preceding `apply` failed to parse it. "
            "Re-run `apply` with a valid message before verifying.",
            file=sys.stderr,
        )
        return 2

    missing = [
        spec.path for spec in specs if not (deps.project_root / spec.path).is_file()
    ]
    if missing:
        print(
            "error: step references files that do not exist on disk: "
            + ", ".join(missing)
            + ". Run `apply` again.",
            file=sys.stderr,
        )
        return 2

    apply_log = (
        deps.fs.read_text(apply_log_path).rstrip()
        if deps.fs.exists(apply_log_path)
        else ""
    )

    paths = [spec.path for spec in specs]
    checks: list[CheckResult] = []

    # The built-in compile check is named "compile", not "syntax":
    # the default config also defines a command named "syntax"
    # (`compileall`), and having two lines with the same name in the
    # output is confusing.
    compile_check = _run_compile(paths, deps)
    checks.append(compile_check)
    print(summarize_check(compile_check))

    for spec in config.verify_commands:
        check = _run_verify_command(spec, deps)
        checks.append(check)
        print(summarize_check(check))

    all_required_ok = all(c.exit_code == 0 for c in checks if c.required)

    commit_hash = None
    commit_message = None
    if all_required_ok:
        commit_message = f"step {args.step}: applied and verified"
        # Update state before the commit so `.harness/state.toml`
        # is picked up by the same commit. This keeps the working
        # tree clean for the next lifecycle command, all of which
        # refuse to run on a dirty tree.
        _update_state(deps, int(args.step))
        try:
            commit_hash = deps.git.commit_all(deps.project_root, commit_message)
        except HarnessError as exc:
            print(f"warning: commit failed: {exc}", file=sys.stderr)

    if commit_hash:
        print(f"commit: {commit_hash}")
    elif not all_required_ok:
        print("commit: skipped (required check failed)")

    report = Report(
        step_number=int(args.step),
        apply_log=apply_log,
        checks=tuple(checks),
        commit_hash=commit_hash,
        commit_message=commit_message,
        notes="",
        question="",
    )
    rendered = render_report(report)
    (steps_dir / f"report-{args.step}.txt").write_text(
        rendered, encoding="utf-8", newline="\n"
    )
    print(f"report: {steps_dir / f'report-{args.step}.txt'}")

    if args.clipboard:
        if deps.clipboard.write(rendered):
            print("report copied to clipboard", file=sys.stderr)
        else:
            print("warning: clipboard unavailable", file=sys.stderr)

    return 0 if all_required_ok else 1


def _parse_step_or_none(text: str) -> list[FileSpec] | None:
    """Parse a step message, returning `None` on any format error.

    Distinguishes "the message had no FILE blocks" from "the message
    had blocks, but one was malformed". Both are errors for verify,
    but the caller's message benefits from knowing which.
    """
    try:
        return parse_step_message(text)
    except FormatError:
        return None


def _update_state(deps: Deps, step_number: int) -> None:
    """Record progress in `.harness/state.toml`.

    Called before `commit_all` on a successful verify. Failures are
    non-fatal: a corrupt or missing state file only means the
    bootstrap's Progress section is stale, not that the step is
    invalid. The report already records what actually happened.

    `last_commit` is deliberately left as-is: the commit hash is
    not known yet, and amending or a second commit just for one
    field would be worse than a slightly stale value. `close` and
    `new-phase` refresh it with the correct hash.
    """
    try:
        state = load_state(deps.fs, deps.project_root)
    except HarnessError as exc:
        print(f"warning: could not read state: {exc}", file=sys.stderr)
        return
    now = datetime.now(UTC).isoformat(timespec="seconds")
    updated = State(
        harness_version=state.harness_version,
        current_phase=state.current_phase,
        current_step=step_number,
        total_steps=max(state.total_steps, step_number),
        last_commit=state.last_commit,
        last_commit_date=now,
        last_opened=state.last_opened,
        last_closed=state.last_closed,
    )
    try:
        save_state(deps.fs, deps.project_root, updated)
    except HarnessError as exc:
        print(f"warning: could not save state: {exc}", file=sys.stderr)


def _run_compile(paths: list[str], deps: Deps) -> CheckResult:
    """Run `compile()` on every `.py` file listed in the step."""
    py_files = [p for p in paths if p.endswith(".py")]
    if not py_files:
        return CheckResult(
            name="compile",
            command=("compile",),
            exit_code=0,
            stdout="(no python files)",
            stderr="",
            required=True,
        )
    buf = io.StringIO()
    failed = False
    with redirect_stdout(buf), redirect_stderr(buf):
        for rel in py_files:
            target = deps.project_root / rel
            try:
                source = target.read_text(encoding="utf-8")
                compile(source, str(target), "exec")
            except (SyntaxError, ValueError) as exc:
                failed = True
                print(f"{rel}: {exc}")
    return CheckResult(
        name="compile",
        command=("compile",),
        exit_code=1 if failed else 0,
        stdout=buf.getvalue().rstrip(),
        stderr="",
        required=True,
    )


def _run_verify_command(spec: dict, deps: Deps) -> CheckResult:
    name = str(spec.get("name", "unnamed"))
    command = tuple(spec.get("command", []))
    required = bool(spec.get("required", True))
    if not command:
        return CheckResult(
            name=name,
            command=(),
            exit_code=1,
            stdout="",
            stderr="(no command configured)",
            required=required,
        )
    try:
        result = deps.process.run(list(command), cwd=deps.project_root)
    except HarnessError as exc:
        return CheckResult(
            name=name,
            command=command,
            exit_code=127,
            stdout="",
            stderr=str(exc),
            required=required,
        )
    return CheckResult(
        name=name,
        command=command,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        required=required,
    )


__all__ = ["cmd_verify"]
