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
from .shared.paths import check_safe_root


def main(argv: list[str] | None = None) -> int:
    """Parse argv and run the requested command. Returns an exit code."""
    project_root = Path.cwd()

    refusal = check_safe_root(project_root)
    if refusal is not None:
        print(f"error: {refusal}", file=sys.stderr)
        return 2

    parser = _build_parser()
    args = parser.parse_args(argv)

    fs = LocalFilesystem()
    process = SubprocessRunner()
    git = CliGit(process)
    clipboard = pick_clipboard()

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

    p_start = sub.add_parser("start", help="Begin a phase.")
    p_start.add_argument("goal", help="Short goal; becomes the phase name.")
    p_start.add_argument(
        "--kind",
        choices=["planning", "development"],
        default=None,
        help=(
            "Kind of phase. Default: infer from state "
            "(frozen plan → development, otherwise planning)."
        ),
    )

    sub.add_parser(
        "next",
        help="Assemble the current task's bootstrap and copy it to the clipboard.",
    )

    p_apply = sub.add_parser("apply", help="Parse and write the current task's files.")
    p_apply.add_argument(
        "--from-file",
        default=None,
        help=(
            "Read the message from a file instead of the clipboard. "
            "Relative paths are resolved against the project root."
        ),
    )

    p_verify = sub.add_parser(
        "verify",
        help="Run checks for the current task and produce the report.",
    )
    p_verify.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy the report to the clipboard on success.",
    )

    sub.add_parser("done", help="Close the current task and commit.")
    sub.add_parser("fix", help="Assemble a fix-bootstrap for the last failure.")

    p_abandon = sub.add_parser("abandon", help="Mark the current phase abandoned.")
    p_abandon.add_argument("--yes", action="store_true", help="Confirm.")

    sub.add_parser("status", help="Print the current state.")

    p_log = sub.add_parser("log", help="Recent lifecycle events.")
    p_log.add_argument("n", nargs="?", type=int, default=10, help="How many commits.")

    sub.add_parser("health", help="Check environment and project state.")

    p_read = sub.add_parser("read", help="Wrap a file in block markers.")
    p_read.add_argument("path", help="File, glob, or directory.")
    p_read.add_argument("--clipboard", action="store_true")

    p_map = sub.add_parser("map", help="Print the module interface map.")
    p_map.add_argument("--root", default=None, help="Root of the map.")
    p_map.add_argument("--full", action="store_true", help="Include docstrings.")
    p_map.add_argument("--private", action="store_true", help="Include _names.")
    p_map.add_argument("--clipboard", action="store_true")

    p_tree = sub.add_parser("tree", help="Print a directory tree.")
    p_tree.add_argument("root", nargs="?", default=None, help="Root of the tree.")

    p_count = sub.add_parser("count", help="Count tokens.")
    p_count.add_argument("path", help="File or directory.")

    p_rb = sub.add_parser("rollback", help="Undo the last task commit.")
    p_rb.add_argument("--yes", action="store_true", help="Confirm.")

    return parser


__all__ = ["main"]
