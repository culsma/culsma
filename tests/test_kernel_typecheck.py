from __future__ import annotations

from culsma.frontend.resolver import resolve_program
from culsma.pipeline.analysis import build_compile_analysis
from culsma.pipeline.compile import compile_ast as _compile_ast
from culsma.pipeline.typecheck import _classify_local_expr_type, typecheck
from culsma.pipeline.validate import validate as _validate
from culsma.parser.parser import parse


def compile_to_ir(ast):
    return _compile_ast(resolve_program(ast).prepared_program).ir


def _compile_source(source: str):
    return compile_to_ir(parse(source))


def validate(ir, **kwargs):
    kwargs.setdefault("analysis", build_compile_analysis(ir))
    return _validate(ir, **kwargs)


def _codes(result) -> list[str]:
    return [d.code for d in result.diagnostics]


def test_typecheck_passes_valid_duration_temp_volume_or_mass():
    src = (
        'protocol T { '
        'tube_a << [feed:5uL]; '
        'Incubate(sample = tube_a, temp = 37C, duration = 10min); '
        '}'
    )
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_protocol_param_defaults_participate_in_env_units():
    duration_ir = _compile_source(
        'protocol T(duration = 10uL) { '
        'let tube_a = tube(label = "A", capacity = 100uL); '
        'with env(thermal = 37C, duration = duration) { hold(sample = tube_a); } '
        '}'
    )
    thermal_ir = _compile_source(
        'protocol T(temp = 10min) { '
        'let tube_a = tube(label = "A", capacity = 100uL); '
        'with env(thermal = temp, duration = 10min) { hold(sample = tube_a); } '
        '}'
    )

    assert "TYPE_ENV_DURATION_DIMENSION_MISMATCH" in _codes(typecheck(duration_ir))
    assert "TYPE_ENV_THERMAL_DIMENSION_MISMATCH" in _codes(typecheck(thermal_ir))


def test_typecheck_detects_duration_dimension_mismatch():
    src = 'protocol T { Incubate(sample = "A", temp = 37C, duration = 200uL); }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_ENV_DURATION_DIMENSION_MISMATCH" in _codes(result)
    assert all(d.span is not None for d in result.diagnostics)


def test_typecheck_detects_temperature_dimension_mismatch():
    src = 'protocol T { Incubate(sample = "A", temp = 10min, duration = 10min); }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_ENV_THERMAL_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_detects_unknown_unit():
    src = 'protocol T { Incubate(sample = "A", temp = 37X, duration = 10min); }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_UNKNOWN_UNIT" in _codes(result)


def test_typecheck_detects_non_quantity_where_quantity_expected():
    src = 'protocol T { Incubate(sample = "A", temp = "hot", duration = 10min); }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_ENV_THERMAL_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_defers_identifier_without_symbol_resolution():
    src = 'protocol T { let t = 37C; Incubate(sample = "A", temp = t, duration = 10min); }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_with_env_thermal_requires_temperature_dimension():
    src = "protocol T { with env(thermal = 37min, duration = 10min) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_ENV_THERMAL_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_with_env_duration_requires_time_dimension():
    src = "protocol T { with env(thermal = 37C, duration = 10uL) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_ENV_DURATION_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_with_env_duration_accepts_day_units():
    src = "protocol T { with env(thermal = 37C, duration = 2day) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_thermal_program_duration_accepts_day_unit():
    src = "protocol T { let tp = thermal_program(from = 25C, duration = 1day); }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_time_unit_legacy_aliases_warn():
    src = """
protocol T {
  with env(thermal = 37C, duration = 1hr) { hold(sample = tube); }
  let tp = thermal_program(from = 95C, duration = 30sec);
}
"""
    ir = _compile_source(src)
    result = typecheck(ir)
    warnings = [d for d in result.diagnostics if d.code == "TYPE_UNIT_LEGACY_ALIAS"]
    assert result.ok
    assert [d.severity for d in warnings] == ["warning", "warning"]
    assert "use canonical unit 'h'" in warnings[0].message
    assert "use canonical unit 's'" in warnings[1].message


def test_typecheck_let_bound_program_legacy_alias_warns_once():
    src = "protocol T { let p = magnetic_program(duration = 30sec); }"
    ir = _compile_source(src)
    result = typecheck(ir)
    warnings = [d for d in result.diagnostics if d.code == "TYPE_UNIT_LEGACY_ALIAS"]
    assert result.ok
    assert len(warnings) == 1
    assert "use canonical unit 's'" in warnings[0].message


def test_typecheck_canonical_time_units_do_not_warn():
    src = """
protocol T {
  with env(thermal = 37C, duration = 1h) { hold(sample = tube); }
  let tp = thermal_program(from = 95C, duration = 30s);
}
"""
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok
    assert "TYPE_UNIT_LEGACY_ALIAS" not in _codes(result)


def test_typecheck_volume_and_percent_legacy_aliases_warn():
    src = """
protocol T {
  let tube = tube(label = "T", capacity = 1ml);
  tube << [feed:1ul];
  with env(thermal = 37C, co2 = 5pct, duration = 1h) { hold(sample = tube); }
}
"""
    ir = _compile_source(src)
    result = typecheck(ir)
    warnings = [d for d in result.diagnostics if d.code == "TYPE_UNIT_LEGACY_ALIAS"]
    assert result.ok
    assert [d.severity for d in warnings] == ["warning", "warning", "warning"]
    assert [message for message in (d.message for d in warnings)] == [
        "Unit 'ml' is a legacy alias for constructor capacity for 'tube'; use canonical unit 'mL' to avoid this warning.",
        "Unit 'ul' is a legacy alias for mutation quantified source; use canonical unit 'uL' to avoid this warning.",
        "Unit 'pct' is a legacy alias for with env arg 'co2'; use canonical unit '%' to avoid this warning.",
    ]


def test_typecheck_canonical_volume_and_percent_units_do_not_warn():
    src = """
protocol T {
  let tube = tube(label = "T", capacity = 1mL);
  tube << [feed:1uL];
  with env(thermal = 37C, co2 = 5%, duration = 1h) { hold(sample = tube); }
}
"""
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok
    assert "TYPE_UNIT_LEGACY_ALIAS" not in _codes(result)


def test_typecheck_with_env_accepts_negative_temperature_quantity():
    src = "protocol T { with env(thermal = -20C, duration = 10min) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_incubate_accepts_negative_temperature_quantity():
    src = 'protocol T { Incubate(sample = "A", temp = -20C, duration = 10min); }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_with_env_co2_requires_percent_dimension():
    src = "protocol T { with env(thermal = 37C, co2 = 10min, duration = 10min) { hold(sample = tube); } }"
    ir = _compile_source(src)
    sem = validate(ir)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    result = typecheck(sem.ir)
    assert "TYPE_ENV_PERCENT_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_with_env_accepts_percent_dimension():
    src = "protocol T { with env(thermal = 37C, co2 = 5%, rh = 95%, duration = 10min) { hold(sample = tube); } }"
    ir = _compile_source(src)
    sem = validate(ir)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    result = typecheck(sem.ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_typecheck_accepts_valid_thermal_program():
    src = "protocol T { let tp = thermal_program(from = 95C, duration = 30s); with env(thermal = tp) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_accepts_negative_temperature_in_thermal_program():
    src = "protocol T { let tp = thermal_program(from = -20C, duration = 30s); with env(thermal = tp) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_thermal_program_from_requires_temperature():
    src = "protocol T { let tp = thermal_program(from = 37min, duration = 30s); }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_ENV_THERMAL_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_thermal_program_duration_requires_time():
    src = "protocol T { let tp = thermal_program(from = 37C, duration = 30uL); }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_ENV_DURATION_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_mutation_quantified_source_requires_unit():
    src = "protocol T { tube << [feed:1]; }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_MUTATION_QUANTITY_UNIT_REQUIRED" in _codes(result)


def test_typecheck_mutation_quantified_source_requires_volume_or_mass():
    src = "protocol T { tube << [feed:30min]; }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_MUTATION_QUANTITY_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_source_partition_program_fields_are_checked():
    src = """
protocol T {
  dst << [src.partition(centrifuge_program(drive = 30uL))[0]:10uL];
}
"""
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_PROGRAM_FIELD_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_centrifugal_filtration_program_accepts_drive_and_duration():
    src = """
protocol T {
  let g = sep(
    sample = column,
    program = centrifugal_filtration_program(
      membrane = "silica",
      drive = 8000g,
      duration = 1min
    )
  );
}
"""
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_typecheck_centrifugal_filtration_program_rejects_invalid_drive_dimension():
    src = """
protocol T {
  let g = sep(
    sample = column,
    program = centrifugal_filtration_program(
      membrane = "silica",
      drive = 8000uL
    )
  );
}
"""
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_PROGRAM_FIELD_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_centrifugal_filtration_program_rejects_invalid_duration_dimension():
    src = """
protocol T {
  let g = sep(
    sample = column,
    program = centrifugal_filtration_program(
      membrane = "silica",
      drive = 8000g,
      duration = 1uL
    )
  );
}
"""
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_PROGRAM_FIELD_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_mutation_accepts_let_bound_quantity():
    src = "protocol T { let vol = 5uL; tube << [feed:vol]; }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_constructor_capacity_requires_volume_dimension():
    src = 'protocol T { let tube_a = tube(label = "A", capacity = 5min); }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_CONTAINER_CAPACITY_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_constructor_load_quantity_requires_volume_or_mass():
    src = 'protocol T { let tube_a = tube(label = "A", load = [content(kind = "biosample", code = "S1", type = "dna_sample"):5s]); }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_LOAD_QUANTITY_DIMENSION_MISMATCH" in _codes(result)


def test_typecheck_rejects_structure_facet_as_mutation_target():
    src = "protocol T { tube.structure.top << [feed:1uL]; }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_CONTAINER_TARGET_VIEW_POSITION_INVALID" in _codes(result)


def test_typecheck_rejects_structure_facet_as_readout_sample():
    src = "protocol T { let obs = img(sample = tube.structure.sidewall, quantity = fluorescence); }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_CONTAINER_TARGET_VIEW_POSITION_INVALID" in _codes(result)


def test_typecheck_rejects_contents_view_as_material_container_alias():
    src = "protocol T { let obs = img(sample = tube.contents, quantity = fluorescence); }"
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_CONTAINER_TARGET_VIEW_POSITION_INVALID" in _codes(result)


def test_typecheck_rejects_let_bound_target_view_as_material_container_alias():
    src = """
protocol T {
  let wall = tube.structure.sidewall;
  let obs = img(sample = wall, quantity = fluorescence);
}
"""
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_CONTAINER_TARGET_VIEW_POSITION_INVALID" in _codes(result)


def test_typecheck_local_assignment_rejects_container_target():
    src = 'protocol T { let reactor = tube(label = "R", capacity = 500uL); reactor = tube(label = "B", capacity = 500uL); }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_LOCAL_ASSIGN_TARGET_FORBIDDEN" in _codes(result)


def test_typecheck_local_assignment_requires_type_compatibility():
    src = 'protocol T { let total = 0uL; total = "bad"; }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_LOCAL_ASSIGN_MISMATCH" in _codes(result)


def test_typecheck_member_assignment_accepts_data_result_field_write():
    src = 'protocol T { let read = data_ref(kind = sequence_read); read.result.hit = true; }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert result.ok


def test_typecheck_member_assignment_rejects_non_data_root():
    src = 'protocol T { let tube_a = tube(label = "A", capacity = 50uL); tube_a.result.hit = true; }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_MEMBER_ASSIGN_TARGET_FORBIDDEN" in _codes(result)


def test_typecheck_member_assignment_rejects_non_result_path():
    src = 'protocol T { let read = data_ref(kind = sequence_read); read.schema_ref = "x"; }'
    ir = _compile_source(src)
    result = typecheck(ir)
    assert "TYPE_MEMBER_ASSIGN_PATH_FORBIDDEN" in _codes(result)


def test_typecheck_classifies_v2_reference_shell_calls():
    ir = _compile_source(
        """
protocol T {
  let panel = markers(["CD3", "CD19"]);
  let schema = data_schema(label = "SeqSignal", fields = [signal]);
  let events = stream(sample = tube_a, unit = single_cell, panel = panel);
  let read = data_ref(kind = sequence_read, subject_ref = tube_a, schema_ref = schema);
  let reads = data_group_ref(kind = sequence_read);
}
"""
    )
    bindings = {}
    for stmt in ir.protocols[0].statements:
        if getattr(stmt, "value", None) is not None:
            bindings[stmt.name] = stmt.value
    assert _classify_local_expr_type(bindings["panel"], expr_bindings=bindings) == "marker_panel_ref"
    assert _classify_local_expr_type(bindings["schema"], expr_bindings=bindings) == "data_schema_ref"
    assert _classify_local_expr_type(bindings["events"], expr_bindings=bindings) == "unit_stream_ref"
    assert _classify_local_expr_type(bindings["read"], expr_bindings=bindings) == "data_ref"
    assert _classify_local_expr_type(bindings["reads"], expr_bindings=bindings) == "data_group_ref"
