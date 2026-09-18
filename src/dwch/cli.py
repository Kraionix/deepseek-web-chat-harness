"""Command-line entry point.

Parses argv, constructs the adapters, dispatches to the chosen
command, and returns its exit code. This is the only module that
knows about concrete adapter classes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapters.clipboard import pick_clipboard
from .adapters.filesystem import LocalFilesystem
from .adapters.git import CliGit
from .adapters.process import SubprocessRunner
from .adapters.tokenizer import DeepseekTokenizer
from .application.commands import COMMANDS
from .application.config import load_config
from .application.deps import Deps
from .shared.errors import HarnessError


def main(argv: list[str] | None = None) -> int:
    """Parse argv and run the requested command. Returns an exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    project_root = Path.cwd()

    # Adapters are constructed once; the tokenizer path is passed
    # to `init` even before the harness is initialized, because the
    # counter is not used during init.
    fs = LocalFilesystem()
    process = SubprocessRunner()
    git = CliGit(process)
    clipboard = pick_clipboard()

    # Try to read the config for the tokenizer path. Before `init`,
    # the config does not exist; the counter is then loaded with a
    # default path, which will fail loudly only when actually used.
    try:
        config = load_config(fs, project_root)
        counter = DeepseekTokenizer(config.tokenizer_path)
    except HarnessError:
        counter = DeepseekTokenizer(
            project_root / ".harness" / "data" / "deepseek_tokenizer.json"
        )

    deps = Deps(
        fs=fs,
        clipboard=clipboard,
        process=process,
        git=git,
        counter=counter,
        project_root=project_root,
    )

    command = COMMANDS.get(args.command)
    if command is None:
        parser.print_help()
        return 2

    try:
        return command(args, deps)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dwch",
        description=("Minimal agent harness for AI-driven development in web chat."),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Install harness into this project.")
    p_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing .harness/ directory.",
    )

    sub.add_parser("health", help="Check environment and project state.")

    p_boot = sub.add_parser("bootstrap", help="Build the opening message.")
    p_boot.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy the message to the clipboard instead of printing.",
    )

    p_apply = sub.add_parser(
        "apply",
        help=(
            "Parse and write a step, or `apply summary` to write "
            "the current phase's summary."
        ),
    )
    p_apply.add_argument(
        "step",
        help="Two-digit step number, or `summary` to write the phase summary.",
    )
    p_apply.add_argument(
        "--from-file",
        default=None,
        help=(
            "Read the message from a file instead of the clipboard. "
            "Relative paths are resolved against the project root."
        ),
    )

    p_verify = sub.add_parser("verify", help="Run checks and produce a report.")
    p_verify.add_argument("step", help="Two-digit step number.")
    p_verify.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy the report to the clipboard.",
    )

    p_close = sub.add_parser("close", help="Finalize the session.")
    p_close.add_argument(
        "--tag",
        action="store_true",
        help="Create a git tag for this session.",
    )
    p_close.add_argument(
        "--freeze",
        action="store_true",
        help=(
            "Freeze the roadmap: compute hashes of roadmap.toml and "
            "architecture documents, write .harness/roadmap.lock, and "
            "mark state as frozen. Valid only in a planning phase."
        ),
    )

    p_read = sub.add_parser("read", help="Wrap a file in step markers.")
    p_read.add_argument("path", help="File, glob, or directory.")
    p_read.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy the output to the clipboard.",
    )

    p_map = sub.add_parser("map", help="Print the module interface map.")
    p_map.add_argument("--root", default=None, help="Root of the map.")
    p_map.add_argument("--full", action="store_true", help="Include docstrings.")
    p_map.add_argument("--tree", action="store_true", help="Also print a tree.")
    p_map.add_argument("--private", action="store_true", help="Include _names.")
    p_map.add_argument("--clipboard", action="store_true")

    p_rb = sub.add_parser("rollback", help="Undo the last step.")
    p_rb.add_argument("--yes", action="store_true", help="Confirm.")

    p_np = sub.add_parser("new-phase", help="Start a new phase.")
    p_np.add_argument("name", help="Phase name (no spaces).")
    p_np.add_argument(
        "--kind",
        choices=["planning", "development"],
        default="development",
        help=(
            "Kind of phase. Planning sessions produce a roadmap; "
            "development sessions execute a frozen one."
        ),
    )

    p_count = sub.add_parser("count", help="Count tokens.")
    p_count.add_argument("path", help="File or directory.")

    return parser


__all__ = ["main"]
