"""Frontend library resolution before core AST -> IR compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from culsma.parser.ast_nodes import LibraryImportDecl, Program, ProtocolDecl
from culsma.parser.parser import parse_file, parse_files
from culsma.pipeline.component_expander import expand_component_calls


_STDLIB_PATH = Path(__file__).resolve().parents[1] / "stdlib" / "current_stdlib.culs"


@dataclass(frozen=True)
class ResolveRequest:
    entry_files: tuple[Path, ...] = ()
    entry_protocol: str | None = None
    include_bundled_stdlib: bool = True
    library_roots: tuple[Path, ...] = ()


@dataclass(frozen=True)
class FrontendBundle:
    entry_sources: tuple[Path, ...]
    parsed_program: Program
    prepared_program: Program
    external_protocol_registry: tuple[ProtocolDecl, ...] = ()


class SourceResolver:
    def resolve_local_sources(self, request: ResolveRequest) -> Program:
        if not request.entry_files:
            raise ValueError("LOAD_NO_INPUT_SOURCES: No input source files were provided")
        return parse_files(list(request.entry_files), entry_protocol=request.entry_protocol)


class LibraryResolver:
    @lru_cache(maxsize=1)
    def load_bundled_stdlib(self) -> tuple[ProtocolDecl, ...]:
        if not _STDLIB_PATH.exists():
            return ()
        stdlib_program = parse_file(_STDLIB_PATH)
        return tuple(stdlib_program.protocols)

    def resolve_imports(
        self,
        program: Program,
        *,
        request: ResolveRequest,
    ) -> tuple[ProtocolDecl, ...]:
        loaded_names: set[str] = set()
        loaded_paths: set[Path] = set()
        stack: list[str] = []
        collected: list[ProtocolDecl] = []

        def visit_import(import_decl: LibraryImportDecl) -> None:
            import_name = import_decl.name
            if import_name in stack:
                cycle = " -> ".join([*stack, import_name])
                raise ValueError(f"LIB_IMPORT_CYCLE: {cycle}")
            if import_name in loaded_names:
                return

            path = self._resolve_import_path(import_name, request.library_roots)
            if path in loaded_paths:
                loaded_names.add(import_name)
                return

            stack.append(import_name)
            try:
                imported_program = parse_files([path])
                self._tag_protocol_modules(imported_program.protocols, module_name=import_name)
                for nested_import in imported_program.library_imports:
                    visit_import(nested_import)
                collected.extend(imported_program.protocols)
                loaded_paths.add(path)
                loaded_names.add(import_name)
            finally:
                stack.pop()

        for import_decl in program.library_imports:
            visit_import(import_decl)

        return tuple(collected)

    def _resolve_import_path(self, import_name: str, library_roots: tuple[Path, ...]) -> Path:
        if not library_roots:
            raise FileNotFoundError(
                f"LIB_IMPORT_NOT_FOUND: No library roots configured for import '{import_name}'"
            )
        for root in library_roots:
            candidate = root / f"{import_name}.culs"
            if candidate.exists():
                return candidate.resolve()
        roots_text = ", ".join(str(root) for root in library_roots)
        raise FileNotFoundError(
            f"LIB_IMPORT_NOT_FOUND: Library import '{import_name}' was not found under roots: {roots_text}"
        )

    def _tag_protocol_modules(self, protocols: Iterable[ProtocolDecl], *, module_name: str) -> None:
        for protocol in protocols:
            protocol.module = module_name


class NamespaceAssembler:
    def build_external_protocol_registry(
        self,
        *,
        bundled_protocols: Iterable[ProtocolDecl],
    ) -> tuple[ProtocolDecl, ...]:
        registry: list[ProtocolDecl] = []
        seen_protocol_names: set[str] = set()
        for protocol in bundled_protocols:
            if protocol.name in seen_protocol_names:
                raise ValueError(
                    f"LIB_PROTOCOL_NAME_CONFLICT: Duplicate external protocol name '{protocol.name}'"
                )
            registry.append(protocol)
            seen_protocol_names.add(protocol.name)
        return tuple(registry)

    def merge_programs(
        self,
        entry_program: Program,
        *,
        imported_protocols: Iterable[ProtocolDecl],
    ) -> Program:
        merged_protocols = list(entry_program.protocols)
        seen_protocol_names = {protocol.name for protocol in merged_protocols}
        for protocol in imported_protocols:
            if protocol.name in seen_protocol_names:
                raise ValueError(
                    f"LIB_PROTOCOL_NAME_CONFLICT: Imported protocol name '{protocol.name}' conflicts with existing protocol"
                )
            merged_protocols.append(protocol)
            seen_protocol_names.add(protocol.name)
        return Program(
            source_includes=list(entry_program.source_includes),
            library_imports=list(entry_program.library_imports),
            protocols=merged_protocols,
            span=entry_program.span,
        )

    def ensure_no_external_conflicts(
        self,
        program: Program,
        *,
        external_protocol_registry: Iterable[ProtocolDecl],
    ) -> None:
        local_names = {protocol.name for protocol in program.protocols}
        for protocol in external_protocol_registry:
            if protocol.name in local_names:
                raise ValueError(
                    f"LIB_PROTOCOL_NAME_CONFLICT: Protocol name '{protocol.name}' conflicts with bundled stdlib"
                )


class FrontendResolver:
    def __init__(self) -> None:
        self._source_resolver = SourceResolver()
        self._library_resolver = LibraryResolver()
        self._namespace_assembler = NamespaceAssembler()

    def resolve(self, request: ResolveRequest) -> FrontendBundle:
        parsed_program = self._source_resolver.resolve_local_sources(request)
        return self._build_bundle(parsed_program, request=request)

    def resolve_program(
        self,
        program: Program,
        *,
        include_bundled_stdlib: bool = True,
        library_roots: Iterable[str | Path] = (),
    ) -> FrontendBundle:
        request = ResolveRequest(
            entry_files=(),
            entry_protocol=None,
            include_bundled_stdlib=include_bundled_stdlib,
            library_roots=tuple(Path(root).expanduser().resolve() for root in library_roots),
        )
        return self._build_bundle(program, request=request)

    def _build_bundle(self, parsed_program: Program, *, request: ResolveRequest) -> FrontendBundle:
        bundled_protocols = (
            self._library_resolver.load_bundled_stdlib() if request.include_bundled_stdlib else ()
        )
        imported_protocols = self._library_resolver.resolve_imports(parsed_program, request=request)
        resolved_program = self._namespace_assembler.merge_programs(
            parsed_program,
            imported_protocols=imported_protocols,
        )
        external_registry = self._namespace_assembler.build_external_protocol_registry(
            bundled_protocols=bundled_protocols,
        )
        self._namespace_assembler.ensure_no_external_conflicts(
            resolved_program,
            external_protocol_registry=external_registry,
        )
        prepared_program = expand_component_calls(
            resolved_program,
            external_protocols=external_registry,
        )
        return FrontendBundle(
            entry_sources=request.entry_files,
            parsed_program=resolved_program,
            prepared_program=prepared_program,
            external_protocol_registry=external_registry,
        )


def resolve_files(
    entry_files: Iterable[str | Path],
    *,
    entry_protocol: str | None = None,
    include_bundled_stdlib: bool = True,
    library_roots: Iterable[str | Path] = (),
) -> FrontendBundle:
    request = ResolveRequest(
        entry_files=tuple(Path(path).expanduser().resolve() for path in entry_files),
        entry_protocol=entry_protocol,
        include_bundled_stdlib=include_bundled_stdlib,
        library_roots=tuple(Path(root).expanduser().resolve() for root in library_roots),
    )
    return FrontendResolver().resolve(request)


def resolve_program(
    program: Program,
    *,
    include_bundled_stdlib: bool = True,
    library_roots: Iterable[str | Path] = (),
) -> FrontendBundle:
    return FrontendResolver().resolve_program(
        program,
        include_bundled_stdlib=include_bundled_stdlib,
        library_roots=library_roots,
    )
