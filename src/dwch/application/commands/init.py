"""`dwch init` — install the harness into a project.

Creates `.harness/`, `steps/`, copies `contract.md`, downloads the
tokenizer JSON, and writes an initial state file. Refuses to run
when `.harness/` already exists unless `--force` is given.
"""

from __future__ import annotations

import sys
import urllib.request
from argparse import Namespace
from importlib.resources import files
from pathlib import Path

from ...shared.errors import (
    ConfigError,
    FilesystemError,
    HarnessError,
    TokenizerError,
)
from ...shared.paths import check_safe_root
from ..config import config_to_toml
from ..deps import Deps
from ..state import initial_state, save_state

_TEMPLATES = ("contract.md",)

_TOKENIZER_URL = (
    "https://huggingface.co/deepseek-ai/DeepSeek-V3/resolve/main/tokenizer.json"
)


def cmd_init(args: Namespace, deps: Deps) -> int:
    """Install the harness. Returns 0 on success, 2 on error."""
    root = deps.project_root

    refusal = check_safe_root(root)
    if refusal is not None:
        print(f"error: {refusal}", file=sys.stderr)
        return 2

    harness_dir = root / ".harness"
    data_dir = harness_dir / "data"
    steps_dir = root / "steps"

    if deps.fs.exists(harness_dir) and not args.force:
        print(
            f"error: {harness_dir} already exists. Pass --force to overwrite.",
            file=sys.stderr,
        )
        return 2

    try:
        deps.fs.mkdir(harness_dir, parents=True)
        deps.fs.mkdir(data_dir, parents=True)
        deps.fs.mkdir(steps_dir, parents=True)
        _write_harness_gitignore(deps, harness_dir)
        _write_steps_gitignore(deps, steps_dir)
        _write_templates(deps, harness_dir, force=args.force)
        _write_config(deps, harness_dir, root.name, force=args.force)
        _write_state(deps, root)
        _download_tokenizer(deps, data_dir, force=args.force)
    except (FilesystemError, ConfigError, TokenizerError, HarnessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"initialized harness at {harness_dir}")
    print('next: `dwch health`, then `dwch start "goal"`')
    return 0


def _write_harness_gitignore(deps: Deps, harness_dir: Path) -> None:
    path = harness_dir / ".gitignore"
    if deps.fs.exists(path):
        return
    deps.fs.write_text(
        path,
        "# Harness data (tokenizer, downloaded on init).\ndata/\n",
    )


def _write_steps_gitignore(deps: Deps, steps_dir: Path) -> None:
    path = steps_dir / ".gitignore"
    if deps.fs.exists(path):
        return
    deps.fs.write_text(
        path,
        "# Session artifacts: messages, apply logs, reports.\n*\n!.gitignore\n",
    )


def _write_templates(deps: Deps, harness_dir: Path, *, force: bool) -> None:
    for name in _TEMPLATES:
        target = harness_dir / name
        if deps.fs.exists(target) and not force:
            continue
        template = files("dwch.templates") / name
        try:
            body = template.read_text(encoding="utf-8")
        except OSError as exc:
            raise HarnessError(f"cannot read shipped template {name}: {exc}") from exc
        deps.fs.write_text(target, body)


def _write_config(
    deps: Deps, harness_dir: Path, project_name: str, *, force: bool
) -> None:
    path = harness_dir / "config.toml"
    if deps.fs.exists(path) and not force:
        return
    deps.fs.write_text(path, config_to_toml(project_name))


def _write_state(deps: Deps, root: Path) -> None:
    path = root / ".harness" / "state.toml"
    if deps.fs.exists(path):
        return
    save_state(deps.fs, root, initial_state())


def _download_tokenizer(deps: Deps, data_dir: Path, *, force: bool) -> None:
    target = data_dir / "deepseek_tokenizer.json"
    if deps.fs.exists(target):
        if not force:
            return
        deps.fs.unlink(target)
    print(f"downloading tokenizer from {_TOKENIZER_URL}")
    request = urllib.request.Request(
        _TOKENIZER_URL,
        headers={"User-Agent": "deepseek-web-chat-harness/0.4.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except Exception as exc:
        raise TokenizerError(
            f"could not download tokenizer: {exc}. "
            "Check your network and re-run `dwch init --force`."
        ) from exc
    deps.fs.write_bytes(target, data)
    print(f"saved {target} ({len(data)} bytes)")


__all__ = ["cmd_init"]
