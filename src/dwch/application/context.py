"""Build the bootstrap message for a new chat session.

The bootstrap is the only channel through which the AI learns the
project state. It must contain everything the AI needs to start
work, without exceeding the model's context window. Sections are
measured with the token counter; optional sections are dropped on a
fixed priority order when the budget is exceeded.
"""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime

from ..domain.models import BootstrapResult, Config, State
from .deps import Deps
from .module_map import build_module_map, render_module_map
from .token_counter import count_sections

# Optional sections are dropped in this order when the total
# exceeds `max_tokens`. Anything not listed here is mandatory.
_TRUNCATION_PRIORITY = (
    "recent_reports",
    "module_map",
    "phase_plan",
)


def build_bootstrap(deps: Deps, config: Config, state: State) -> BootstrapResult:
    """Assemble the opening message for a new web chat.

    Preconditions: `deps`, `config`, and `state` are fully loaded.
    Postconditions: a `BootstrapResult` whose `text` is a markdown
    document, `breakdown` lists per-section token counts, and
    `truncated` is True if any optional section was dropped.
    """
    sections = _collect_sections(deps, config, state)
    total, breakdown = count_sections(deps.counter, sections)

    max_tokens = int(config.bootstrap.get("max_tokens", 10000))
    truncated = False
    if total > max_tokens and config.bootstrap.get("truncate", True):
        sections, breakdown, total, truncated = _truncate(
            deps, sections, breakdown, total, max_tokens
        )

    text = "\n\n".join(
        f"<!-- section: {name} -->\n{body}" for name, body in sections.items()
    )
    return BootstrapResult(
        text=text,
        breakdown=breakdown,
        total_tokens=total,
        truncated=truncated,
    )


def _collect_sections(deps: Deps, config: Config, state: State) -> dict[str, str]:
    """Build the ordered dict of bootstrap sections.

    Section order is fixed: header, protocol, task, essential,
    phase_plan, progress, recent_reports, module_map, commits,
    format, toolbox. The order reflects reading priority for the AI.
    """
    sections: dict[str, str] = {}
    sections["header"] = _header(deps, config, state)
    sections["protocol"] = _read_template(deps, "session-protocol.md")
    sections["task"] = _task(deps)
    sections["essential"] = _essential(deps, config)
    sections["phase_plan"] = _phase_plan(deps)
    sections["progress"] = _progress(state)
    sections["recent_reports"] = _recent_reports(deps, config)
    sections["module_map"] = _module_map(deps, config)
    sections["commits"] = _recent_commits(deps)
    sections["format"] = _read_template(deps, "step-format.md")
    sections["toolbox"] = _read_template(deps, "toolbox.md")
    return sections


def _truncate(
    deps: Deps,
    sections: dict[str, str],
    breakdown: dict[str, int],
    total: int,
    max_tokens: int,
) -> tuple[dict[str, str], dict[str, int], int, bool]:
    """Drop optional sections until the total fits `max_tokens`."""
    for name in _TRUNCATION_PRIORITY:
        if total <= max_tokens:
            break
        if name not in sections:
            continue
        total -= breakdown.pop(name, 0)
        sections.pop(name)
    return sections, breakdown, total, True


def _header(deps: Deps, config: Config, state: State) -> str:
    head = _git_head(deps)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    return (
        f"# Bootstrap — {config.project_name}\n"
        f"\n"
        f"- Phase: `{state.current_phase}`\n"
        f"- Step: `{state.current_step}` of `{state.total_steps}`\n"
        f"- Git HEAD: `{head}`\n"
        f"- Generated: {now}\n"
    )


def _git_head(deps: Deps) -> str:
    try:
        return deps.git.rev_parse(deps.project_root, "HEAD")
    except Exception:
        # An empty git history is legal for a fresh project.
        return "(no commits)"


def _task(deps: Deps) -> str:
    path = deps.project_root / ".harness" / "handoff.md"
    if not deps.fs.exists(path):
        return "## Task\n\nNo handoff file. Describe the current phase."
    text = deps.fs.read_text(path)
    return f"## Task\n\n{text.strip()}"


def _essential(deps: Deps, config: Config) -> str:
    parts: list[str] = ["## Essential context"]
    for name in config.context.get("essential", []):
        path = deps.project_root / name
        if not deps.fs.exists(path):
            continue
        parts.append(f"\n### {name}\n")
        parts.append(deps.fs.read_text(path).rstrip())
    return "\n".join(parts)


def _phase_plan(deps: Deps) -> str:
    path = deps.project_root / ".harness" / "phase.toml"
    if not deps.fs.exists(path):
        return "## Phase plan\n\nNo phase.toml present."
    data = tomllib.loads(deps.fs.read_text(path))
    steps = data.get("steps", [])
    lines = ["## Phase plan"]
    for step in steps:
        num = step.get("number", "?")
        title = step.get("title", "untitled")
        status = step.get("status", "pending")
        lines.append(f"- Step {num}: {title} — *{status}*")
    return "\n".join(lines)


def _progress(state: State) -> str:
    return (
        "## Progress\n"
        f"\n"
        f"- Last successful step: `{state.current_step}`\n"
        f"- Last commit: `{state.last_commit or '(none)'}`\n"
    )


def _recent_reports(deps: Deps, config: Config) -> str:
    n = int(config.bootstrap.get("recent_reports", 1))
    steps_dir = deps.project_root / config.paths.get("steps", "steps")
    if not deps.fs.is_dir(steps_dir):
        return "## Recent reports\n\n(none)"
    reports = sorted(deps.fs.glob(steps_dir, "report-*.txt"))
    if not reports:
        return "## Recent reports\n\n(none)"
    parts = ["## Recent reports"]
    for path in reports[-n:]:
        parts.append(f"\n### {path.name}\n")
        parts.append(deps.fs.read_text(path).rstrip())
    return "\n".join(parts)


def _module_map(deps: Deps, config: Config) -> str:
    if not config.bootstrap.get("include_module_map", True):
        return "## Module map\n\n(disabled)"
    root_name = config.context.get("map_root", "")
    if not root_name:
        return "## Module map\n\n(map_root not configured)"
    root = deps.project_root / root_name
    modules = build_module_map(deps.fs, root)
    return "## Module map\n\n" + render_module_map(modules, full=False)


def _recent_commits(deps: Deps) -> str:
    try:
        log = deps.git.log_oneline(deps.project_root, 5)
    except Exception:
        log = []
    lines = ["## Recent commits"]
    if not log:
        lines.append("\n(none)")
    else:
        lines.append("")
        for entry in log:
            lines.append(f"- {entry}")
    return "\n".join(lines)


def _read_template(deps: Deps, name: str) -> str:
    """Read one of the shipped templates from the package."""
    from importlib.resources import files

    template = files("dwch.templates") / name
    return template.read_text(encoding="utf-8").rstrip()


__all__ = ["build_bootstrap"]
