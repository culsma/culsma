from __future__ import annotations

from pathlib import Path

import pytest

from culsma.frontend.resolver import resolve_files, resolve_program
from culsma.parser.ast_nodes import CallExpr, LetStatement, ProtocolDecl
from culsma.parser.parser import parse


def test_resolve_program_injects_bundled_stdlib_before_component_expansion():
    src = """
protocol T {
  let gel_obs_schema = data_schema(label = "GelObs", fields = [bands]);
  let gel_obs = Electrophoresis(
    sample = gel_lane,
    gel_type = "Agarose_1.5pct",
    stain = stain_input,
    field = 100V,
    duration = 30min,
    readout_schema = gel_obs_schema
  );
}
"""
    bundle = resolve_program(parse(src))
    assert not any(
        isinstance(stmt, LetStatement)
        and isinstance(stmt.value, CallExpr)
        and stmt.value.name == "Electrophoresis"
        for stmt in bundle.prepared_program.protocols[0].statements
    )


def test_resolve_files_loads_imported_library_protocols_from_library_root(tmp_path: Path):
    library = tmp_path / "Bio.culs"
    library.write_text(
        """
protocol Helper(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )

    main = tmp_path / "main.culs"
    main.write_text(
        """
import Bio;
protocol T(sample) {
  Bio.Helper(sample = sample);
}
""",
        encoding="utf-8",
    )

    bundle = resolve_files([main], library_roots=[tmp_path])
    assert any(protocol.name == "Helper" and protocol.module == "Bio" for protocol in bundle.parsed_program.protocols)


def test_resolve_files_reports_missing_library_import_root(tmp_path: Path):
    main = tmp_path / "main.culs"
    main.write_text(
        """
import Bio;
protocol T {}
""",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="LIB_IMPORT_NOT_FOUND"):
        resolve_files([main])


def test_resolve_files_rejects_empty_entry_source_set():
    with pytest.raises(ValueError, match="LOAD_NO_INPUT_SOURCES"):
        resolve_files([])


def test_resolve_files_returns_canonical_entry_sources(tmp_path: Path):
    main = tmp_path / "main.culs"
    main.write_text("protocol T {}", encoding="utf-8")

    bundle = resolve_files([main])
    assert bundle.entry_sources == (main.resolve(),)


def test_resolve_program_can_disable_bundled_stdlib_injection():
    src = """
protocol T {
  let gel_obs = Electrophoresis(sample = gel_lane, gel_type = "Agarose_1.5pct", stain = stain_input, field = 100V, duration = 30min);
}
"""
    bundle = resolve_program(parse(src), include_bundled_stdlib=False)
    stmt = bundle.prepared_program.protocols[0].statements[0]
    assert isinstance(stmt, LetStatement)
    assert isinstance(stmt.value, CallExpr)
    assert stmt.value.name == "Electrophoresis"
    assert bundle.external_protocol_registry == ()


def test_resolve_files_uses_first_matching_library_root(tmp_path: Path):
    root_a = tmp_path / "lib_a"
    root_b = tmp_path / "lib_b"
    root_a.mkdir()
    root_b.mkdir()

    (root_a / "Bio.culs").write_text("protocol First(sample) { return sample; }", encoding="utf-8")
    (root_b / "Bio.culs").write_text("protocol Second(sample) { return sample; }", encoding="utf-8")

    main = tmp_path / "main.culs"
    main.write_text("import Bio; protocol T(sample) { return sample; }", encoding="utf-8")

    bundle = resolve_files([main], library_roots=[root_a, root_b])
    names = [protocol.name for protocol in bundle.parsed_program.protocols]
    assert "First" in names
    assert "Second" not in names


def test_resolve_files_recursively_loads_nested_library_imports(tmp_path: Path):
    (tmp_path / "Bio.culs").write_text(
        """
import Helpers;
protocol BioMain(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )
    (tmp_path / "Helpers.culs").write_text(
        """
protocol Helper(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )
    main = tmp_path / "main.culs"
    main.write_text("import Bio; protocol T(sample) { return sample; }", encoding="utf-8")

    bundle = resolve_files([main], library_roots=[tmp_path])
    protocol_names = {protocol.name for protocol in bundle.parsed_program.protocols}
    assert {"BioMain", "Helper", "T"} <= protocol_names


def test_resolve_files_rejects_library_import_cycle(tmp_path: Path):
    (tmp_path / "Bio.culs").write_text(
        """
import Helpers;
protocol BioMain(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )
    (tmp_path / "Helpers.culs").write_text(
        """
import Bio;
protocol Helper(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )
    main = tmp_path / "main.culs"
    main.write_text("import Bio; protocol T(sample) { return sample; }", encoding="utf-8")

    with pytest.raises(ValueError, match="LIB_IMPORT_CYCLE"):
        resolve_files([main], library_roots=[tmp_path])


def test_resolve_files_deduplicates_repeated_library_imports(tmp_path: Path):
    (tmp_path / "Bio.culs").write_text(
        """
protocol Helper(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )
    main = tmp_path / "main.culs"
    main.write_text(
        """
import Bio;
import Bio;
protocol T(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )

    bundle = resolve_files([main], library_roots=[tmp_path])
    helpers = [protocol for protocol in bundle.parsed_program.protocols if protocol.name == "Helper"]
    assert len(helpers) == 1
    assert helpers[0].module == "Bio"


def test_imported_single_protocol_does_not_create_legacy_entry(tmp_path: Path):
    from culsma.pipeline.compile import compile_ast
    from culsma.pipeline.entrypoints import resolve_entry

    (tmp_path / "Bio.culs").write_text(
        """
protocol OnlyLibraryProtocol {
  StepFromLibrary();
}
""",
        encoding="utf-8",
    )
    main = tmp_path / "main.culs"
    main.write_text("import Bio;\n", encoding="utf-8")

    bundle = resolve_files([main], include_bundled_stdlib=False, library_roots=[tmp_path])
    ir = compile_ast(bundle.prepared_program).ir
    entry = resolve_entry(ir)

    assert entry.kind == "none"
    assert entry.entry_protocol is None
    assert [protocol.source_role for protocol in ir.protocols] == ["dependency"]


def test_resolve_files_rejects_imported_protocol_name_conflict_with_entry_program(tmp_path: Path):
    (tmp_path / "Bio.culs").write_text(
        """
protocol Helper(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )
    main = tmp_path / "main.culs"
    main.write_text(
        """
import Bio;
protocol Helper(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="LIB_PROTOCOL_NAME_CONFLICT"):
        resolve_files([main], library_roots=[tmp_path])


def test_resolve_program_rejects_conflict_between_local_protocol_and_bundled_stdlib():
    program = parse(
        """
protocol Electrophoresis(sample) {
  return sample;
}
"""
    )

    with pytest.raises(ValueError, match="LIB_PROTOCOL_NAME_CONFLICT"):
        resolve_program(program)


def test_resolver_external_registry_contains_bundled_protocols_not_imported_library_protocols(tmp_path: Path):
    (tmp_path / "Bio.culs").write_text(
        """
protocol Helper(sample) {
  return sample;
}
""",
        encoding="utf-8",
    )
    main = tmp_path / "main.culs"
    main.write_text("import Bio; protocol T(sample) { return sample; }", encoding="utf-8")

    bundle = resolve_files([main], library_roots=[tmp_path])
    registry_names = {protocol.name for protocol in bundle.external_protocol_registry}
    assert "Helper" not in registry_names
    assert any(isinstance(protocol, ProtocolDecl) for protocol in bundle.external_protocol_registry)
