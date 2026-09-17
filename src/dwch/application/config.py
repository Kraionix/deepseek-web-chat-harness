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

# Version of the config file format. Independent of the package
# version: a patch release that does not change the format keeps
# this value, and existing `.harness/config.toml` files keep working.
_CONFIG_FORMAT_VERSION = "0.2.0"


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
    if version != _CONFIG_FORMAT_VERSION:
        raise ConfigError(
            f"config version {version!r} does not match harness "
            f"version {_CONFIG_FORMAT_VERSION!r}. Run `dwch init --force` "
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

    _validate_paths(config=paths, context=context, roadmap=roadmap)

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
version = "{_CONFIG_FORMAT_VERSION}"

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


def _validate_paths(*, config: dict, context: dict, roadmap: dict) -> None:
    """Reject absolute paths and parent traversal in every path field.

    Pre:  `config`, `context`, `roadmap` are the merged dicts from
          `load_config`.
    Post: returns None on success.
    Raises: `ConfigError` if any path-typed value is not relative.
    """
    for key, value in config.items():
        _validate_relative_path(value, f"paths.{key}")

    for key in ("essential", "references", "architecture"):
        for entry in context.get(key, []):
            _validate_relative_path(str(entry), f"context.{key}")

    # `map_root` may be empty: an empty value means "no map". Only
    # a non-empty value is validated.
    map_root = context.get("map_root", "")
    if map_root:
        _validate_relative_path(str(map_root), "context.map_root")

    for key in ("path", "lock_path", "deviations_path"):
        value = roadmap.get(key, "")
        if value:
            _validate_relative_path(str(value), f"roadmap.{key}")


def _validate_relative_path(value: str, label: str) -> None:
    """Reject an absolute path or a path containing `..`.

    Pre:  `value` is a string; `label` names the config key.
    Post: returns None on success.
    Raises: `ConfigError` if the path is not a safe relative path.
    """
    p = Path(value)
    if p.is_absolute():
        raise ConfigError(f"{label}: absolute path not allowed: {value!r}")
    if ".." in p.parts:
        raise ConfigError(f"{label}: parent traversal not allowed: {value!r}")


__all__ = ["config_to_toml", "load_config"]
