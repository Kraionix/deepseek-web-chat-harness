"""Load `.harness/config.toml` into a `Config` model.

The config file is user-edited; the harness only reads it. Missing
sections fall back to the defaults below. All paths are resolved
relative to the project root.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from ..domain.models import Config
from ..shared.errors import ConfigError
from .ports import FilesystemPort

# Defaults applied when a section or key is missing from the config.
# Kept in one place so the loader and the template agree on what an
# "empty" config means.
_DEFAULT_PATHS = {
    "steps": "steps",
    "phases": "phases",
}

_DEFAULT_CONTEXT = {
    "essential": ["AGENTS.md", "STATE.md"],
    "references": [],
    "architecture": [],
    "map_root": "",
}

_DEFAULT_ROADMAP = {
    "path": ".harness/roadmap.toml",
    "lock_path": ".harness/roadmap.lock",
    "deviations_path": ".harness/deviations",
    "lock_required": False,
}

_DEFAULT_BOOTSTRAP = {
    "max_tokens": 10000,
    "recent_reports": 1,
    "recent_deviations": 10,
    "include_module_map": True,
    "truncate": True,
}

_DEFAULT_TOKENIZER_URL = (
    "https://huggingface.co/deepseek-ai/DeepSeek-V3/resolve/main/tokenizer.json"
)

_DEFAULT_READ_MAX_TOKENS = 6000

_HARNESS_VERSION = "0.2.0"


def load_config(fs: FilesystemPort, project_root: Path) -> Config:
    """Load and validate `.harness/config.toml`.

    Pre:  `project_root` is a directory.
    Post: returns a `Config` with every field populated. Missing
          sections fall back to defaults.
    Raises: `ConfigError` when the file is missing, malformed, or
          when `harness_version` is incompatible with this build.
    """
    config_path = project_root / ".harness" / "config.toml"
    if not fs.exists(config_path):
        raise ConfigError(f"config not found: {config_path}. Run `dwch init` first.")

    try:
        raw = fs.read_text(config_path)
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {config_path}: {exc}") from exc

    harness = data.get("harness", {})
    version = str(harness.get("version", ""))
    if version != _HARNESS_VERSION:
        raise ConfigError(
            f"config version {version!r} does not match harness "
            f"version {_HARNESS_VERSION!r}. Run `dwch init --force` "
            "or update the config by hand."
        )

    project = data.get("project", {})
    project_name = str(project.get("name", "unnamed"))

    paths = {**_DEFAULT_PATHS, **data.get("paths", {})}
    context = {**_DEFAULT_CONTEXT, **data.get("context", {})}
    roadmap = {**_DEFAULT_ROADMAP, **data.get("roadmap", {})}
    bootstrap = {**_DEFAULT_BOOTSTRAP, **data.get("bootstrap", {})}
    verify_commands = tuple(data.get("verify", {}).get("commands", []))
    planning_commands = tuple(data.get("verify", {}).get("planning_commands", []))

    _validate_relative_paths(context.get("architecture", []), "context.architecture")

    tokenizer = data.get("tokenizer", {})
    tokenizer_url = str(tokenizer.get("url", _DEFAULT_TOKENIZER_URL))

    # Tokenizer data lives under `.harness/data/` inside the project.
    # The config may override the filename; any override is resolved
    # relative to the data directory.
    tokenizer_filename = str(tokenizer.get("filename", "deepseek_tokenizer.json"))
    tokenizer_path = project_root / ".harness" / "data" / tokenizer_filename

    read_section = data.get("read", {})
    read_max_tokens = int(read_section.get("max_tokens", _DEFAULT_READ_MAX_TOKENS))

    return Config(
        harness_version=version,
        project_name=project_name,
        paths=paths,
        context=context,
        verify_commands=verify_commands,
        planning_commands=planning_commands,
        roadmap=roadmap,
        bootstrap=bootstrap,
        tokenizer_path=tokenizer_path,
        tokenizer_url=tokenizer_url,
        read_max_tokens=read_max_tokens,
    )


def config_to_toml(project_name: str) -> str:
    """Render the default config as a TOML string.

    Used by `init` to write `.harness/config.toml` from scratch. The
    rendered string is human-editable; the loader accepts it as-is.
    """
    return f"""# dwch configuration for {project_name}.
# Edit by hand as needed; `dwch` only reads this file.

[harness]
version = "{_HARNESS_VERSION}"

[project]
name = "{project_name}"

[paths]
steps = "steps"
phases = "phases"

[context]
# Files copied verbatim into the bootstrap.
essential = ["AGENTS.md", "STATE.md"]
# Files listed by name only; the AI asks for them on demand.
references = ["docs/decisions.md"]
# Frozen architecture documents included in every development bootstrap.
architecture = ["docs/architecture.md"]
# Root of the module interface map.
map_root = "src"

[roadmap]
path = ".harness/roadmap.toml"
lock_path = ".harness/roadmap.lock"
deviations_path = ".harness/deviations"
lock_required = false

[verify]
# Commands run by `dwch verify` in order. `required = false` means a
# non-zero exit is recorded but does not block the commit.
commands = [
    {{ name = "syntax", command = ["python", "-m", "compileall", "-q", "src"] }},
    {{ name = "lint", command = ["ruff", "check", "."] }},
]
# Extra commands run only during a planning phase.
planning_commands = []

[bootstrap]
max_tokens = {_DEFAULT_BOOTSTRAP["max_tokens"]}
recent_reports = {_DEFAULT_BOOTSTRAP["recent_reports"]}
recent_deviations = {_DEFAULT_BOOTSTRAP["recent_deviations"]}
include_module_map = {str(_DEFAULT_BOOTSTRAP["include_module_map"]).lower()}
truncate = {str(_DEFAULT_BOOTSTRAP["truncate"]).lower()}

[tokenizer]
# Downloaded by `dwch init` into .harness/data/.
url = "{_DEFAULT_TOKENIZER_URL}"

[read]
max_tokens = {_DEFAULT_READ_MAX_TOKENS}
"""


def _validate_relative_paths(paths: list, label: str) -> None:
    """Reject absolute paths and parent traversal in a config list.

    Pre:  `paths` is a list of strings; `label` names the config key
          for the error message.
    Post: returns None on success.
    Raises: `ConfigError` if any entry is not a relative path.
    """
    for entry in paths:
        p = Path(str(entry))
        if p.is_absolute():
            raise ConfigError(f"{label}: absolute path not allowed: {entry!r}")
        if ".." in p.parts:
            raise ConfigError(f"{label}: parent traversal not allowed: {entry!r}")


__all__ = ["config_to_toml", "load_config"]
