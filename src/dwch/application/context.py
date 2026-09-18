"""Build the bootstrap message for a new chat session.

The bootstrap is the only channel through which the AI learns the
project state. It must contain everything the AI needs to start
work, without exceeding the model's context window. Sections are
measured with the token counter; optional sections are dropped on a
fixed priority order when the budget is exceeded.

The section set depends on `state.phase_kind`. A planning session
receives a planning-oriented bootstrap (no roadmap, no reports, no
commits). A development session receives the frozen architecture,
the current step, the interfaces, the roadmap summary, and the
deviations summary. When the roadmap is exhausted, the
`current_step` section is replaced by `roadmap_complete`.

Cross-phase continuity comes from `state.summary_phase`: the
bootstrap shows `.harness/summaries/{summary_phase}.md` as
`previous_summary`. That summary is the only artifact carried from
the previous phase's chat.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.resources import files

from ..domain.models import BootstrapResult, Config, Roadmap, State
from ..domain.rules import is_development_phase
from . import deviations as dev_mod
from . import roadmap as roadmap_mod
from .deps import Deps
from .module_map import build_module_map, render_module_map
from .token_counter import count_sections

# Optional sections are dropped in this order when the total
# exceeds `max_tokens`. Anything not listed here is mandatory.
# Sections that only appear in one phase kind are naturally
# skipped when they are absent from the dict.
#
# `previous_summary` drops last: cross-phase intent is more
# important than any within-phase fact.
_TRUNCATION_PRIORITY = (
    "recent_reports",
    "module_map",
    "commits",
    "roadmap_summary",
    "deviations_summary",
    "previous_summary",
)


def build_bootstrap(
    deps: Deps,
    config: Config,
    state: State,
    roadmap: Roadmap | None = None,
) -> BootstrapResult:
    """Assemble the opening message for a new web chat.

    Pre:  `deps`, `config`, and `state` are fully loaded. `roadmap`
          may be None if the project has no roadmap yet.
    Post: a `BootstrapResult` whose `text` is a markdown document,
          `breakdown` lists per-section token counts, and
          `truncated` is True if any optional section was dropped.
    """
    sections = _collect_sections(deps, config, state, roadmap)
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


def _collect_sections(
    deps: Deps,
    config: Config,
    state: State,
    roadmap: Roadmap | None,
) -> dict[str, str]:
    """Build the ordered dict of bootstrap sections.

    Planning and development phases get different section sets. In
    a planning phase there is no roadmap and no code yet, so the
    roadmap, module-map, recent-reports, and commits sections would
    only add noise. `previous_summary` appears in both kinds: the
    phase's starting point is relevant whether the phase plans or
    codes.
    """
    is_development = is_development_phase(state)
    roadmap_complete = (
        is_development
        and roadmap is not None
        and state.roadmap_step >= len(roadmap.steps)
    )

    sections: dict[str, str] = {}
    sections["header"] = _header(deps, config, state)
    sections["protocol"] = _read_template(deps, "session-protocol.md")

    previous = _previous_summary(deps, state)
    if previous is not None:
        sections["previous_summary"] = previous

    sections["task"] = _task(deps)
    sections["essential"] = _essential(deps, config)

    if is_development:
        sections["architecture"] = _architecture(deps, config)
        if roadmap is not None:
            if roadmap_complete:
                sections["roadmap_complete"] = _roadmap_complete(roadmap)
            else:
                current = roadmap_mod.find_step(roadmap, state.roadmap_step + 1)
                if current is not None:
                    sections["current_step"] = roadmap_mod.render_current(current)
            sections["interfaces"] = roadmap_mod.render_interfaces(roadmap)
            sections["roadmap_summary"] = roadmap_mod.render_summary(roadmap, state)
        sections["deviations_summary"] = _deviations_summary(deps, config)

    sections["progress"] = _progress(state)

    if is_development:
        sections["recent_reports"] = _current_phase_reports(deps, config, state)
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
    head = deps.git.try_head(deps.project_root) or "(no commits)"
    now = datetime.now(UTC).isoformat(timespec="seconds")
    return (
        f"# Bootstrap — {config.project_name}\n"
        f"\n"
        f"- Phase: `{state.current_phase}` ({state.phase_kind})\n"
        f"- Step: `{state.current_step}`\n"
        f"- Roadmap: v{state.roadmap_version}, step `{state.roadmap_step}`"
        f"{' (frozen)' if state.roadmap_frozen else ''}\n"
        f"- Git HEAD: `{head}`\n"
        f"- Generated: {now}\n"
    )


def _previous_summary(deps: Deps, state: State) -> str | None:
    """Render the previous phase's summary, or None when there is none.

    `state.summary_phase` is empty until the first `close`. When it
    names a phase whose file is missing, that is reported explicitly
    rather than silently omitted: the next session must know that
    its cross-phase context is incomplete.
    """
    if not state.summary_phase:
        return None
    path = deps.project_root / ".harness" / "summaries" / f"{state.summary_phase}.md"
    if not deps.fs.exists(path):
        return f"## Previous summary ({state.summary_phase})\n\n(missing)"
    body = deps.fs.read_text(path).rstrip()
    return f"## Previous summary ({state.summary_phase})\n\n{body}"


def _task(deps: Deps) -> str:
    path = deps.project_root / ".harness" / "handoff.md"
    if not deps.fs.exists(path):
        return "## Task\n\nNo handoff file. Describe the current phase."
    text = deps.fs.read_text(path)
    return f"## Task\n\n{text.strip()}"


def _essential(deps: Deps, config: Config) -> str:
    parts: list[str] = ["## Essential context"]
    found = False
    for name in config.context.get("essential", []):
        path = deps.project_root / name
        if not deps.fs.exists(path):
            continue
        found = True
        parts.append(f"\n### {name}\n")
        parts.append(deps.fs.read_text(path).rstrip())
    if not found:
        parts.append("\n(none)")
    return "\n".join(parts)


def _architecture(deps: Deps, config: Config) -> str:
    """Render the frozen architecture documents listed in config.

    When the list is empty or none of the listed files exist, the
    section still appears, with an explicit `(none ...)` note, so
    the reader knows the section was not silently dropped.
    """
    parts: list[str] = ["## Architecture"]
    found = False
    for name in config.context.get("architecture", []):
        path = deps.project_root / name
        if not deps.fs.exists(path):
            continue
        found = True
        parts.append(f"\n### {name}\n")
        parts.append(deps.fs.read_text(path).rstrip())
    if not found:
        parts.append("\n(none configured or all listed files missing)")
    return "\n".join(parts)


def _deviations_summary(deps: Deps, config: Config) -> str:
    n = int(config.bootstrap.get("recent_deviations", 10))
    dir_path = deps.project_root / config.roadmap.get(
        "deviations_path", ".harness/deviations"
    )
    recent = dev_mod.load_recent(deps.fs, dir_path, n)
    return dev_mod.summarize(recent, n)


def _roadmap_complete(roadmap: Roadmap) -> str:
    """Render a placeholder when every roadmap step has been done."""
    return (
        "## Roadmap complete\n"
        f"\n"
        f"All {len(roadmap.steps)} step(s) of roadmap "
        f"v{roadmap.meta.version} are done.\n"
        f"\n"
        f"The correct next action is to close this phase and start a "
        f"new planning phase that produces a new roadmap version. Do "
        f"not send substantive files in this phase.\n"
    )


def _progress(state: State) -> str:
    return (
        "## Progress\n"
        f"\n"
        f"- Phase: `{state.current_phase}` ({state.phase_kind})\n"
        f"- Phase step: `{state.current_step}`\n"
        f"- Roadmap step: `{state.roadmap_step}` "
        f"(v{state.roadmap_version})\n"
        f"- Frozen: `{state.roadmap_frozen}`\n"
        f"- Last commit: `{state.last_commit or '(none)'}`\n"
    )


def _current_phase_reports(deps: Deps, config: Config, state: State) -> str:
    """Render the most recent reports written in the current phase.

    Scoped to `steps/{state.current_phase}/`. Reports from earlier
    phases are not shown: their intent lives in the previous phase's
    summary, and their details are not relevant to the current step.
    """
    n = int(config.bootstrap.get("reports_current_phase", 1))
    steps_dir = (
        deps.project_root / config.paths.get("steps", "steps") / state.current_phase
    )
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
    template = files("dwch.templates") / name
    return template.read_text(encoding="utf-8").rstrip()


__all__ = ["build_bootstrap"]
