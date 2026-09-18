# Step message format

A step message contains one or more blocks. Three block kinds
exist: file, delete, and move.

## File block

A file block opens with `<<<FILE:` followed by a relative path,
followed by `>>>`, on its own line. The file content follows
verbatim, one line per line. The block closes with a line
containing only the end marker.

Example (illustrative; the end marker is written as
`<<<END>>>`):

    <<<FILE:src/app.py>>>
    def main() -> None:
        print("hi")

## Delete block

A delete block opens with `<<<DELETE:` followed by a relative
path, followed by `>>>`. The body must be empty (whitespace
only). The block closes with the end marker.

Example:

    <<<DELETE:src/legacy.py>>>

## Move block

A move block opens with `<<<MOVE:` followed by a relative source
path, a single colon, a relative destination path, and `>>>`. The
body must be empty. The block closes with the end marker.

Example:

    <<<MOVE:src/old.py:src/new.py>>>

## Rules

- The keyword is uppercase: `FILE`, `DELETE`, `MOVE`. Lowercase
  is a format error.
- Every block ends with a line containing only the end marker
  (`<<<END>>>`). Trailing whitespace on a marker line is
  tolerated.
- `MOVE` takes exactly two paths separated by `:`. Since `:` is
  forbidden in paths, a second `:` is a format error.
- Each path may appear in at most one op per step, in any role:
  write target, delete target, move source, move destination.
- A step that only deletes or moves a file is still substantive
  and advances `roadmap_step`.
- The step message is bounded: 50 MiB total, 10 MiB per file.

## Path safety

Every path in a step is checked before any write:

- relative, no leading `/` or `\`;
- no `..`, no `.`;
- no component starting or ending with a space or dot;
- no `< > : " | ? *`, no control characters;
- no Windows reserved name (`CON`, `NUL`, `COM1`, ...);
- no component longer than 255 UTF-8 bytes;
- no symlink component;
- the resolved path must stay inside the project root.

A step that touches a tracked file with uncommitted changes is
refused: commit or stash first.
