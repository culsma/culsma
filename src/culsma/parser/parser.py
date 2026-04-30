"""
Culsma parser — public API.

Usage:
    from culsma.parser.parser import parse
    ast = parse(source_code_string)
"""

from __future__ import annotations

from pathlib import Path

from lark import Lark

from culsma.parser.ast_nodes import Program
from culsma.parser.transformer import CulsmaTransformer

# Load the Lark grammar file (relative to this module).
_GRAMMAR_PATH = Path(__file__).parent / "culsma.lark"

_lark_parser = Lark(
    _GRAMMAR_PATH.read_text(encoding="utf-8"),
    parser="lalr",
    lexer="contextual",
    start="start",
    propagate_positions=True,
)

_transformer = CulsmaTransformer()


def parse(source: str) -> Program:
    """Parse Culsma source code and return an AST.

    Args:
        source: A string containing Culsma source code.

    Returns:
        A Program AST node.

    Raises:
        lark.exceptions.UnexpectedInput: If the source has syntax errors.
    """
    tree = _lark_parser.parse(source)
    return _transformer.transform(tree)


def parse_file(path: str | Path) -> Program:
    """Parse a .culs file and return an AST."""
    canonical_path = Path(path).expanduser().resolve()
    source = canonical_path.read_text(encoding="utf-8")
    program = parse(source)
    _tag_protocol_modules(program, module_name=canonical_path.stem)
    return program


def parse_files(paths: list[str | Path], *, entry_protocol: str | None = None) -> Program:
    """Parse and merge one or more .culs files into one Program."""
    if not paths:
        raise ValueError("LOAD_NO_INPUT_SOURCES: No input source files were provided")

    merged_source_includes = []
    merged_library_imports = []
    merged_protocols = []
    loaded_files: set[Path] = set()
    loading_stack: list[Path] = []
    protocol_first_decl: dict[str, Path] = {}
    module_first_decl: dict[str, Path] = {}

    def canonical(path: str | Path) -> Path:
        return Path(path).expanduser().resolve()

    def load_file(path: str | Path) -> None:
        canonical_path = canonical(path)

        if canonical_path in loading_stack:
            cycle_start = loading_stack.index(canonical_path)
            cycle_paths = loading_stack[cycle_start:] + [canonical_path]
            cycle_text = " -> ".join(str(p) for p in cycle_paths)
            raise ValueError(f"Include cycle detected: {cycle_text}")

        if canonical_path in loaded_files:
            return

        if not canonical_path.exists():
            raise FileNotFoundError(
                f"LOAD_SOURCE_NOT_FOUND: Included source file not found: {canonical_path}"
            )

        loading_stack.append(canonical_path)
        try:
            program = parse(canonical_path.read_text(encoding="utf-8"))
            module_name = canonical_path.stem

            first_module_path = module_first_decl.get(module_name)
            if first_module_path is not None and first_module_path != canonical_path:
                raise ValueError(
                    f"Duplicate module name '{module_name}' from files "
                    f"{first_module_path} and {canonical_path}"
                )
            module_first_decl.setdefault(module_name, canonical_path)
            _tag_protocol_modules(program, module_name=module_name)

            for include_decl in program.source_includes:
                include_path = Path(include_decl.path)
                if not include_path.is_absolute():
                    include_path = canonical_path.parent / include_path
                load_file(include_path)

            for protocol in program.protocols:
                first_decl_file = protocol_first_decl.get(protocol.name)
                if first_decl_file is not None and first_decl_file != canonical_path:
                    raise ValueError(
                        f"LOAD_DUPLICATE_PROTOCOL_NAME: Duplicate protocol name '{protocol.name}' in "
                        f"{first_decl_file} and {canonical_path}"
                    )
                protocol_first_decl.setdefault(protocol.name, canonical_path)

            merged_source_includes.extend(program.source_includes)
            merged_library_imports.extend(program.library_imports)
            merged_protocols.extend(program.protocols)
            loaded_files.add(canonical_path)
        finally:
            loading_stack.pop()

    for input_path in paths:
        load_file(input_path)

    merged = Program(
        source_includes=merged_source_includes,
        library_imports=merged_library_imports,
        protocols=merged_protocols,
        span=None,
    )
    if entry_protocol is not None and not any(p.name == entry_protocol for p in merged.protocols):
        raise ValueError(f"LOAD_ENTRY_PROTOCOL_NOT_FOUND: Entry protocol '{entry_protocol}' not found")
    return merged


def _tag_protocol_modules(program: Program, module_name: str) -> None:
    for protocol in program.protocols:
        protocol.module = module_name
