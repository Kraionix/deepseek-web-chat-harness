"""Build a module interface map by parsing Python source with `ast`.

The map is a compact summary of every module's public surface: the
list of symbols it exports, with signatures for classes and
functions. It is what the AI uses as a substitute for reading the
code, so the extraction is deliberately structural — no docstrings
beyond the module's first line, no bodies, no private symbols.

Signature rendering keeps annotations and defaults: the AI reads
the map instead of the source, so `def f(a: int, b: str = "x")`
must not degrade to `def f(a, b)`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..domain.models import ModuleInfo, SymbolInfo
from ..shared.errors import FilesystemError
from .ports import FilesystemPort


def build_module_map(
    fs: FilesystemPort,
    root: Path,
    *,
    include_private: bool = False,
) -> list[ModuleInfo]:
    """Return interface summaries for every `.py` file under `root`.

    Pre:  `root` is a directory.
    Post: a list sorted by path. Empty when `root` has no Python
          files, or when `root` does not exist.

    A file that fails to parse is skipped silently. Parse failures
    are a symptom of the module's state, not a harness error.
    """
    if not fs.is_dir(root):
        return []
    files = sorted(fs.glob(root, "**/*.py"))
    result: list[ModuleInfo] = []
    for path in files:
        info = _analyze_file(fs, path, root, include_private)
        if info is not None:
            result.append(info)
    return result


def extract_public_symbols(fs: FilesystemPort, path: Path) -> set[str]:
    """Return the set of public symbol names in one Python file.

    Used by `verify_checks` to compare what the coder actually wrote
    against the roadmap's declared interfaces. Returns an empty set
    if the file cannot be read or parsed — the caller decides how to
    report that.
    """
    try:
        source = fs.read_text(path)
    except FilesystemError:
        return set()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return set()
    return {sym.name for sym in _public_symbols(tree, include_private=False)}


def render_module_map(modules: list[ModuleInfo], *, full: bool = False) -> str:
    """Render the map as markdown.

    In brief mode, each module becomes two lines: path with line
    count, then the list of symbol signatures. In full mode, the
    module docstring is included as well.
    """
    if not modules:
        return "(no modules)\n"
    lines: list[str] = []
    for module in modules:
        lines.append(f"### {module.path} ({module.size_lines} lines)")
        if full and module.docstring:
            lines.append(module.docstring)
        for sym in module.symbols:
            if sym.signature:
                lines.append(f"  {sym.signature}")
            else:
                lines.append(f"  {sym.kind} {sym.name}")
        lines.append("")
    return "\n".join(lines)


def _analyze_file(
    fs: FilesystemPort,
    path: Path,
    root: Path,
    include_private: bool,
) -> ModuleInfo | None:
    try:
        source = fs.read_text(path)
    except FilesystemError:
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None

    rel = str(path.relative_to(root)).replace("\\", "/")
    size_lines = source.count("\n") + 1
    docstring = _module_docstring(tree)
    symbols = tuple(_public_symbols(tree, include_private=include_private))
    return ModuleInfo(
        path=rel,
        size_lines=size_lines,
        docstring=docstring,
        symbols=symbols,
    )


def _module_docstring(tree: ast.Module) -> str:
    doc = ast.get_docstring(tree, clean=True) or ""
    if not doc:
        return ""
    return doc.split("\n", 1)[0].strip()


def _public_symbols(tree: ast.Module, *, include_private: bool) -> list[SymbolInfo]:
    out: list[SymbolInfo] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _is_public(node.name, include_private):
                continue
            out.append(
                SymbolInfo(
                    name=node.name,
                    kind="function",
                    signature=_render_function(node),
                )
            )
        elif isinstance(node, ast.ClassDef):
            if not _is_public(node.name, include_private):
                continue
            out.append(
                SymbolInfo(
                    name=node.name,
                    kind="class",
                    signature=_render_class(node),
                )
            )
        elif isinstance(node, ast.Assign):
            for name in _assign_names(node.targets):
                if _is_public(name, include_private):
                    out.append(_constant_symbol(name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if _is_public(node.target.id, include_private):
                out.append(_constant_symbol(node.target.id))
    return out


def _assign_names(targets: list[ast.expr]) -> list[str]:
    """Return every `Name` bound by a tuple/list/name assignment.

    `a, b = 1, 2` binds two names, but `ast.Assign.targets` holds a
    single `ast.Tuple`. Without recursion the two names would be
    invisible to the map.
    """
    out: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            out.append(target.id)
        elif isinstance(target, ast.Tuple | ast.List):
            for elt in target.elts:
                if isinstance(elt, ast.Name):
                    out.append(elt.id)
    return out


def _constant_symbol(name: str) -> SymbolInfo:
    """SymbolInfo for a module-level constant.

    Annotated and unannotated assignments produce the same shape:
    the harness does not surface the type in the map. The constant
    is reported by name only.
    """
    return SymbolInfo(name=name, kind="constant", signature=f"{name} = ...")


def _is_public(name: str, include_private: bool) -> bool:
    if include_private:
        return True
    return not name.startswith("_")


def _render_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = _render_args(node.args)
    ret = ""
    if node.returns is not None:
        ret = f" -> {ast.unparse(node.returns)}"
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({args}){ret}"


def _render_class(node: ast.ClassDef) -> str:
    bases = ", ".join(ast.unparse(b) for b in node.bases)
    if bases:
        return f"class {node.name}({bases})"
    return f"class {node.name}"


def _render_args(args: ast.arguments) -> str:
    """Render an argument list with annotations and defaults.

    The positional and positional-only arguments share the
    `defaults` list, which is right-aligned: `def f(a, b=1)` has
    `args=[a, b]` and `defaults=[1]`, so `a` has no default and `b`
    does. Keyword-only defaults live in `kw_defaults`, where `None`
    means "required".
    """
    pos = [*args.posonlyargs, *args.args]
    pad = len(pos) - len(args.defaults)
    defaulted: list[str | None] = [None] * pad + [ast.unparse(d) for d in args.defaults]

    parts: list[str] = []
    for i, arg in enumerate(args.posonlyargs):
        parts.append(_render_arg(arg, defaulted[i]))
    if args.posonlyargs:
        parts.append("/")
    offset = len(args.posonlyargs)
    for i, arg in enumerate(args.args):
        parts.append(_render_arg(arg, defaulted[offset + i]))
    if args.vararg:
        parts.append("*" + _render_arg(args.vararg, None))
    elif args.kwonlyargs:
        parts.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        parts.append(
            _render_arg(arg, None if default is None else ast.unparse(default))
        )
    if args.kwarg:
        parts.append("**" + _render_arg(args.kwarg, None))
    return ", ".join(parts)


def _render_arg(arg: ast.arg, default: str | None) -> str:
    """Render one `ast.arg` with its annotation and default, if any."""
    text = arg.arg
    if arg.annotation is not None:
        text += f": {ast.unparse(arg.annotation)}"
    if default is not None:
        text += f" = {default}"
    return text


__all__ = ["build_module_map", "extract_public_symbols", "render_module_map"]
