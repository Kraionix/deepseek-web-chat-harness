"""Build a module interface map by parsing Python source with `ast`.

The map is a compact summary of every module's public surface: the
list of symbols it exports, with signatures for classes and
functions. It is what the AI uses as a substitute for reading the
code, so the extraction is deliberately structural — no docstrings
beyond the module's first line, no bodies, no private symbols.
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

    Preconditions: `root` is a directory.
    Postconditions: a list sorted by path. Empty when `root` has no
    Python files, or when `root` does not exist.

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
            for target in node.targets:
                if isinstance(target, ast.Name) and _is_public(
                    target.id, include_private
                ):
                    out.append(
                        SymbolInfo(
                            name=target.id,
                            kind="constant",
                            signature=f"{target.id} = ...",
                        )
                    )
    return out


def _is_public(name: str, include_private: bool) -> bool:
    if include_private:
        return True
    return not name.startswith("_")


def _render_function(node: ast.AST) -> str:
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
    parts: list[str] = []
    for arg in args.posonlyargs:
        parts.append(arg.arg)
    if args.posonlyargs:
        parts.append("/")
    for arg in args.args:
        parts.append(arg.arg)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    for arg in args.kwonlyargs:
        parts.append(arg.arg)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)


__all__ = ["build_module_map", "render_module_map"]
