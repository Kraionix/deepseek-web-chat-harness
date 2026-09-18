"""Assemble the bootstrap message from six ordered layers.

L0  Meta            ~50 tokens   never truncated
L1  Contract        ~1200       never truncated
L2  Tools           ~200        never truncated
L3  Session state   facts       never truncated
L4  Context         variable    truncated first
L5  Current task    variable    never truncated
L6  Notes           variable    truncated second

L4 is a bundle: `essential`, `module_map`, `commits`, and
`reports` are separate sections, dropped in that order when the
budget is exceeded. L5 is either the current task's spec or — in a
fix-bootstrap — a description of the failure.

Sections are joined with `<!-- section: name -->` markers on their
own line.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from importlib.resources import files

from ..domain.models import BootstrapResult, Config, Plan, State, Task
from . import plan as plan_mod
from .deps import Deps
from .token_counter import count_sections

# Optional sections are dropped in this order when the total
# exceeds `max_tokens`. Anything not listed here is mandatory.
_TRUNCATION_ORDER = (
    "notes",
    "essential",
    "module_map",
    "commits",
    "reports",
)

# L2 content. Kept as a constant because it is stable, small, and
# never varies by project. The full block grammar lives in
# `contract.md` (L1); this is a short reminder of who may do what.
_TOOLS_SECTION = """\
## Tools

You have no access to `init`, `rollback`, `git`, or direct file
editing. Your output is applied by `dwch apply`. To read: `dwch
read PATH`, `dwch map`, `dwch tree`, `dwch status`, `dwch log`,
`dwch count PATH`. To propose a state change: `dwch verify`,
`dwch done`, `dwch fix`, `dwch abandon` — the user decides.
"""

_REPORT_RE = re.compile(r"^report-(\d+)\.txt$")


def build_bootstrap(
    deps: Deps,
    config: Config,
    state: State,
    plan: Plan | None = None,
    mode: str = "task",
) -> BootstrapResult:
    """Assemble the opening message for a new web chat.

    Pre:  `deps`, `config`, and `state` are fully loaded. `plan`
          may be None if the project has no plan yet. `mode` is
          `"task"` for a normal bootstrap or `"fix"` for a
          fix-bootstrap.
    Post: a `BootstrapResult` whose `text` is a markdown document,
          `breakdown` lists per-section token counts, and
          `truncated` is True if any optional section was dropped.
    """
    sections = _collect_sections(deps, config, state, plan, mode)
    total, breakdown = count_sections(deps.counter, sections)

    max_tokens = int(config.bootstrap.get("max_tokens", 5000))
    truncated = False
    if total > max_tokens and config.bootstrap.get("truncate", True):
        sections, breakdown, total, truncated = _truncate(
            sections, breakdown, total, max_tokens
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
    plan: Plan | None,
    mode: str,
) -> dict[str, str]:
    """Build the ordered dict of bootstrap sections.

    Layers appear in fixed order. Optional sections are absent (not
    empty) when they have nothing to show: absence is what the
    truncation step consults.
    """
    sections: dict[str, str] = {}
    sections["meta"] = _meta(deps, config, state, plan)
    sections["contract"] = _read_template(deps, "contract.md")
    sections["tools"] = _TOOLS_SECTION.strip()
    sections["session"] = _session(state)

    essential = _essential(deps, config)
    if essential is not None:
        sections["essential"] = essential

    module_map = _module_map(deps, config)
    if module_map is not None:
        sections["module_map"] = module_map

    commits = _recent_commits(deps)
    if commits is not None:
        sections["commits"] = commits

    reports = _recent_reports(deps, config, state, plan, mode)
    if reports is not None:
        sections["reports"] = reports

    if mode == "fix":
        sections["failure"] = _failure_block(deps, config, state)
    else:
        sections["task"] = _current_task(plan, state)

    notes = _notes(deps, config)
    if notes is not None:
        sections["notes"] = notes

    return sections


def _truncate(
    sections: dict[str, str],
    breakdown: dict[str, int],
    total: int,
    max_tokens: int,
) -> tuple[dict[str, str], dict[str, int], int, bool]:
    """Drop optional sections until the total fits `max_tokens`.

    `truncated` is True only if at least one section was actually
    removed.
    """
    dropped = False
    for name in _TRUNCATION_ORDER:
        if total <= max_tokens:
            break
        if name not in sections:
            continue
        total -= breakdown.pop(name, 0)
        sections.pop(name)
        dropped = True
    return sections, breakdown, total, dropped


def _meta(deps: Deps, config: Config, state: State, plan: Plan | None) -> str:
    """L0 — always present, never truncated.

    A warning is prepended when the current task has failed at least
    three times in a row: the fix loop is not converging, and the
    right action may be a plan correction or abandonment.
    """
    head = deps.git.try_head(deps.project_root) or "(no commits)"
    now = datetime.now(UTC).isoformat(timespec="seconds")
    total = len(plan.tasks) if plan is not None else 0

    lines: list[str] = []
    if state.failure_count >= 3:
        lines.append(
            f"warning: {state.failure_count}rd consecutive failure on "
            f'"{state.failure_task_id}". Consider plan-correction or abandon.'
        )
        lines.append("")
    lines.append(f"# Bootstrap — {config.project_name}")
    lines.append("")
    lines.append(
        f"- Phase: `{state.phase_name}` ({state.phase_kind}, {state.phase_status})"
    )
    lines.append(
        f"- Plan: v{state.plan_version}, position {state.plan_position}/{total}"
    )
    lines.append(f"- Frozen: `{state.plan_frozen}`")
    lines.append(f"- Git HEAD: `{head}`")
    lines.append(f"- Generated: {now}")
    return "\n".join(lines)


def _session(state: State) -> str:
    """L3 — session-state facts, never truncated."""
    lines = ["## Session state", ""]
    lines.append(f"- Phase: `{state.phase_name}` ({state.phase_kind})")
    lines.append(f"- Status: `{state.phase_status}`")
    lines.append(f"- Opened: {state.phase_opened_at or '(never)'}")
    if state.phase_closed_at:
        lines.append(f"- Closed: {state.phase_closed_at}")
    sha = state.plan_sha256[:12] if state.plan_sha256 else ""
    lines.append(
        f"- Plan: v{state.plan_version} sha `{sha or '(none)'}` "
        f"frozen=`{state.plan_frozen}` position={state.plan_position}"
    )
    lines.append(
        f"- Verify: ok=`{state.verify_ok}` task=`{state.verify_task_id}` "
        f"at=`{state.verify_at}`"
    )
    if state.failure_count:
        lines.append(
            f"- Failure: task=`{state.failure_task_id}` "
            f"check=`{state.failure_check_name}` count={state.failure_count}"
        )
    lines.append(f"- Rollbacks: {state.rollback_count}")
    lines.append(
        f"- Last commit: `{state.last_commit or '(none)'}` "
        f"at `{state.last_commit_date or '(never)'}`"
    )
    return "\n".join(lines)


def _essential(deps: Deps, config: Config) -> str | None:
    """L4a — essential context files. Skipped when none are present."""
    parts: list[str] = []
    for name in config.context.get("essential", []):
        path = deps.project_root / name
        if not deps.fs.exists(path):
            continue
        parts.append(f"### {name}\n")
        parts.append(deps.fs.read_text(path).rstrip())
    if not parts:
        return None
    return "## Essential context\n\n" + "\n".join(parts)


def _module_map(deps: Deps, config: Config) -> str | None:
    """L4b — module interface map. Skipped when disabled or empty."""
    if not config.bootstrap.get("include_module_map", True):
        return None
    root_name = config.context.get("map_root", "")
    if not root_name:
        return None
    from .module_map import build_module_map, render_module_map

    root = deps.project_root / root_name
    modules = build_module_map(deps.fs, root)
    if not modules:
        return None
    return "## Module map\n\n" + render_module_map(modules, full=False)


def _recent_commits(deps: Deps) -> str | None:
    """L4c — the five most recent commits. Skipped when none exist."""
    from ..shared.errors import HarnessError

    try:
        log = deps.git.log_oneline(deps.project_root, 5)
    except HarnessError:
        log = []
    if not log:
        return None
    lines = ["## Recent commits", ""]
    for entry in log:
        lines.append(f"- {entry}")
    return "\n".join(lines)


def _recent_reports(
    deps: Deps,
    config: Config,
    state: State,
    plan: Plan | None,
    mode: str,
) -> str | None:
    """L4d — reports for the current (or failed) task.

    Reports live under `steps/{phase}/{task_id}/report-N.txt`. Only
    the current task's reports are shown.
    """
    n = int(config.bootstrap.get("reports_current_phase", 1))
    if n <= 0:
        return None
    task_id = _task_id_for_state(plan, state, mode)
    if not task_id:
        return None
    steps_dir = (
        deps.project_root
        / config.paths.get("steps", "steps")
        / state.phase_name
        / task_id
    )
    if not deps.fs.is_dir(steps_dir):
        return None
    reports = sorted(deps.fs.glob(steps_dir, "report-*.txt"), key=_report_key)
    if not reports:
        return None
    parts = ["## Recent reports"]
    for path in reports[-n:]:
        parts.append(f"\n### {path.name}\n")
        parts.append(deps.fs.read_text(path).rstrip())
    return "\n".join(parts)


def _report_key(path) -> int:
    """Numeric sort key for `report-N.txt`; non-matching names go first."""
    m = _REPORT_RE.match(path.name)
    return int(m.group(1)) if m else -1


def _current_task(plan: Plan | None, state: State) -> str:
    """L5 — the current task's spec."""
    task = _task_at(plan, state.plan_position)
    if task is None:
        if state.phase_kind == "planning":
            return (
                "## Current task\n\n"
                "Planning phase. Produce design artifacts and "
                "`.harness/plan.toml`. No production code."
            )
        return "## Current task\n\n(no plan, or position past the end)"
    return plan_mod.render_task(task)


def _failure_block(deps: Deps, config: Config, state: State) -> str:
    """L5 (fix mode) — description of the last failure."""
    task_id = state.failure_task_id or "(unknown)"
    count = state.failure_count or 1
    check = state.failure_check_name or "(unknown)"
    excerpt = state.failure_excerpt or ""
    report_dir = (
        deps.project_root
        / config.paths.get("steps", "steps")
        / state.phase_name
        / task_id
    )
    try:
        report_rel = report_dir.relative_to(deps.project_root).as_posix()
    except ValueError:
        report_rel = report_dir.as_posix()

    lines = [
        f"Task: {task_id} (FAILED, attempt {count})",
        "Failure:",
        f"  check: {check}",
    ]
    for ln in excerpt.splitlines():
        lines.append(f"  {ln}")
    lines.append(f"Full report: {report_rel}/")
    lines.append(
        f"Fix and re-submit, or declare a deviation at "
        f".harness/deviations/{task_id}.toml"
    )
    return "\n".join(lines)


def _notes(deps: Deps, config: Config) -> str | None:
    """L6 — project notes. Skipped when the file does not exist."""
    rel = config.notes_path
    if not rel:
        return None
    path = deps.project_root / rel
    if not deps.fs.exists(path):
        return None
    body = deps.fs.read_text(path).rstrip()
    if not body:
        return None
    return f"## Notes\n\n{body}"


def _task_id_for_state(plan: Plan | None, state: State, mode: str) -> str:
    """Return the task id the bootstrap is about, or empty string."""
    if mode == "fix":
        return state.failure_task_id
    task = _task_at(plan, state.plan_position)
    if task is not None:
        return task.id
    if state.phase_kind == "planning":
        return "planning"
    return ""


def _task_at(plan: Plan | None, position: int) -> Task | None:
    """Return the task at `position`, or None when out of range."""
    if plan is None:
        return None
    if position < 0 or position >= len(plan.tasks):
        return None
    return plan.tasks[position]


def _read_template(deps: Deps, name: str) -> str:
    """Read one of the shipped templates from the package."""
    template = files("dwch.templates") / name
    return template.read_text(encoding="utf-8").rstrip()


__all__ = ["build_bootstrap"]
