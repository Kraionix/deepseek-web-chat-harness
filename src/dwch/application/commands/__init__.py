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
from .abandon import cmd_abandon
from .apply import cmd_apply
from .count import cmd_count
from .done import cmd_done
from .fix import cmd_fix
from .health import cmd_health
from .init import cmd_init
from .log import cmd_log
from .map import cmd_map
from .next import cmd_next
from .read import cmd_read
from .rollback import cmd_rollback
from .start import cmd_start
from .status import cmd_status
from .tree import cmd_tree
from .verify import cmd_verify

CommandFn = Callable[[Any, Deps], int]


COMMANDS: dict[str, CommandFn] = {
    "init": cmd_init,
    "start": cmd_start,
    "next": cmd_next,
    "apply": cmd_apply,
    "verify": cmd_verify,
    "done": cmd_done,
    "fix": cmd_fix,
    "abandon": cmd_abandon,
    "status": cmd_status,
    "log": cmd_log,
    "health": cmd_health,
    "read": cmd_read,
    "map": cmd_map,
    "tree": cmd_tree,
    "count": cmd_count,
    "rollback": cmd_rollback,
}


__all__ = ["COMMANDS", "CommandFn"]
