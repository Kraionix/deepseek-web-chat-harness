"""Command registry.

Each command is a function `cmd_*(args, deps) -> int`. `args` is
the parsed argparse namespace for that subcommand. `deps` carries
the ports and the project root. The return value is the process
exit code.

The CLI dispatches through `COMMANDS`, keyed by the argparse
subcommand name.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..deps import Deps
from .apply import cmd_apply
from .bootstrap import cmd_bootstrap
from .close import cmd_close
from .count import cmd_count
from .health import cmd_health
from .init import cmd_init
from .map import cmd_map
from .new_phase import cmd_new_phase
from .read import cmd_read
from .rollback import cmd_rollback
from .verify import cmd_verify

CommandFn = Callable[[Any, Deps], int]


COMMANDS: dict[str, CommandFn] = {
    "init": cmd_init,
    "health": cmd_health,
    "bootstrap": cmd_bootstrap,
    "apply": cmd_apply,
    "verify": cmd_verify,
    "close": cmd_close,
    "read": cmd_read,
    "map": cmd_map,
    "rollback": cmd_rollback,
    "new-phase": cmd_new_phase,
    "count": cmd_count,
}


__all__ = ["COMMANDS", "CommandFn"]
