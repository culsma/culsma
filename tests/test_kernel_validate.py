from __future__ import annotations

from pathlib import Path

import pytest

from culsma.frontend.resolver import resolve_program
from culsma.pipeline.analysis import build_compile_analysis
from culsma.pipeline.compile import compile_ast as _compile_ast
from culsma.pipeline.operation_specs import BUILTIN_OPERATION_SPECS
from culsma.pipeline.validate import _classify_group_binding, validate as _validate
from culsma.parser.parser import parse, parse_file


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures_parser"
LEGACY_FIXTURES = ROOT / "tests" / "fixtures_parser_legacy"


def compile_to_ir(ast):
    return _compile_ast(resolve_program(ast).prepared_program).ir


def compile_ast(ast):
    return _compile_ast(resolve_program(ast).prepared_program)


def _compile_source(source: str):
    return compile_to_ir(parse(source))


def _codes(result) -> list[str]:
    return [d.code for d in result.diagnostics]


def validate(ir, **kwargs):
    kwargs.setdefault("analysis", build_compile_analysis(ir))
    return _validate(ir, **kwargs)


def test_validate_protocol_param_is_bound_name_under_inventory_check():
    ir = _compile_source("protocol T(sample) { img(sample = sample, quantity = fluorescence); }")
    result = validate(ir, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" not in _codes(result)


def test_validate_legacy_enzyme_digestion_fixture_is_rejected_by_current_source_gate():
    ast = parse_file(LEGACY_FIXTURES / "enzyme_digestion.culs")
    with pytest.raises(ValueError, match="legacy-only"):
        compile_to_ir(ast)


def test_validate_legacy_dna_extraction_fixture_is_rejected_by_current_source_gate():
    ast = parse_file(LEGACY_FIXTURES / "dna_extraction.culs")
    with pytest.raises(ValueError, match="staining_method"):
        compile_to_ir(ast)


def test_validate_unknown_step_name():
    ir = _compile_source('protocol T { UnknownOp(a = 1); }')
    result = validate(ir)
    assert "SEM_UNKNOWN_STEP" in _codes(result)
    assert result.diagnostics[0].span is not None


def test_validate_statement_measure_is_unknown_current_step():
    ir = _compile_source('protocol T { Measure(sample = tube_a, method = "UV", device = "NanoDrop", wavelength = 260nm); }')
    result = validate(ir)
    assert "SEM_UNKNOWN_STEP" in _codes(result)


def test_validate_statement_extract_dna_is_unknown_current_step():
    ir = _compile_source('protocol T { ExtractDNA(sample = lysate, method = "Column"); }')
    result = validate(ir)
    assert "SEM_UNKNOWN_STEP" in _codes(result)


def test_validate_statement_htr_is_unknown_current_step():
    with pytest.raises(ValueError, match="legacy-only"):
        _compile_source('protocol T { htr(sample = tube_a, program = htr_program(mode = "flow")); }')


def test_validate_missing_required_arg():
    src = 'protocol T { img(sample = tube_a); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_MISSING_REQUIRED_ARG" in _codes(result)
    assert any("quantity" in d.message for d in result.diagnostics)
    assert all(d.span is not None for d in result.diagnostics)


def test_validate_let_bound_img_missing_required_quantity():
    src = 'protocol T { let obs = img(sample = tube_a); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_MISSING_REQUIRED_ARG" in _codes(result)
    assert any("quantity" in d.message for d in result.diagnostics)


def test_validate_unknown_arg():
    src = (
        'protocol T { img(sample = tube_a, quantity = fluorescence, extra = 2); }'
    )
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_UNKNOWN_ARG" in _codes(result)
    assert any("extra" in d.message for d in result.diagnostics)
    assert all(d.span is not None for d in result.diagnostics)


def test_validate_duplicate_arg():
    src = (
        'protocol T { img(sample = tube_a, sample = tube_b, quantity = fluorescence); }'
    )
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_DUPLICATE_ARG" in _codes(result)
    assert any("sample" in d.message for d in result.diagnostics)
    assert all(d.span is not None for d in result.diagnostics)


@pytest.mark.parametrize(
    ("op", "quantity"),
    [
        ("img", "banana_signal"),
        ("ecp", "banana_ecp"),
        ("phy", "banana_phy"),
    ],
)
def test_validate_readout_quantity_must_be_in_current_reference_set(op: str, quantity: str):
    src = f"protocol T {{ {op}(sample = tube_a, quantity = {quantity}); }}"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INVALID_READOUT_QUANTITY" in _codes(result)


def test_validate_let_bound_readout_quantity_must_be_in_current_reference_set():
    src = "protocol T { let obs = img(sample = tube_a, quantity = banana_signal); }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INVALID_READOUT_QUANTITY" in _codes(result)


@pytest.mark.parametrize(
    "program_name",
    [
        "pipette_program",
        "vortex_program",
        "invert_program",
        "shake_program",
        "plate_shake_program",
        "stir_program",
        "spatula_program",
        "scalpel_program",
        "optical_uv_program",
        "optical_fluor_program",
        "optical_colorimetric_program",
        "gel_readout_program",
        "microscopy_program",
        "ph_program",
        "conductivity_program",
        "dissolved_oxygen_program",
        "orp_program",
        "ion_selective_program",
        "temperature_measure_program",
        "pressure_program",
        "flow_rate_program",
        "mass_measure_program",
        "volume_measure_program",
        "humidity_program",
    ],
)
def test_validate_removed_public_program_constructors_are_rejected(program_name: str):
    src = f"protocol T {{ let p = {program_name}(); }}"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_PROGRAM_KIND_INVALID" in _codes(result)


@pytest.mark.parametrize(
    "program_name",
    [
        "centrifuge_program",
        "magnetic_program",
        "disrupt_program",
        "field_program",
        "filtration_program",
        "phase_partition_program",
        "precipitation_program",
        "density_gradient_program",
        "chromatography_program",
        "thermal_program",
    ],
)
def test_validate_current_program_constructors_can_be_let_bound_as_descriptors(program_name: str):
    args_by_program = {
        "centrifuge_program": "drive = 12000g",
        "field_program": "field = 100V",
        "filtration_program": 'membrane = "silica", drive = pressure',
        "phase_partition_program": 'solvent = "phenol_chloroform"',
        "precipitation_program": "reagent = cleanup_capture",
        "density_gradient_program": "axis = density, order = top_to_bottom, bins = 8",
        "chromatography_program": "axis = retention_time, order = early_to_late, bins = 24",
        "thermal_program": "from = 95C, duration = 30s",
    }
    args = args_by_program.get(program_name, "")
    src = f"protocol T {{ let p = {program_name}({args}); }}"
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_owner_program_arg_accepts_let_bound_program_descriptor_alias():
    src = """
protocol T {
  let p = centrifuge_program(drive = 12000g);
  let g = sep(sample = lysate, program = p);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_builtin_operation_specs_exclude_legacy_portal_steps():
    for name in ("Measure", "Lyse", "ExtractDNA", "PCR", "Electrophoresis"):
        assert name not in BUILTIN_OPERATION_SPECS


def test_validate_sep_sample_requires_prior_binding():
    src = (
        'protocol T { let g = sep(sample = lysate, program = centrifuge_program( drive = 12000g)); }'
    )
    ir = _compile_source(src)
    result = validate(ir, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" in _codes(result)


def test_validate_constructor_defined_name_satisfies_binding_for_current_readout():
    src = (
        'protocol T { '
        'let tube_a = tube(label = "DNA", capacity = 100uL); '
        'let obs = img(sample = tube_a, quantity = fluorescence); '
        '}'
    )
    ir = _compile_source(src)
    result = validate(ir, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" not in _codes(result)


def test_validate_mutation_target_and_source_require_binding():
    src = 'protocol T { tube_a << [buffer_in:1uL]; }'
    ir = _compile_source(src)
    result = validate(ir, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" in _codes(result)


def test_validate_with_env_hold_target_requires_binding():
    src = 'protocol T { with env(thermal = 37C, duration = 10min) { hold(sample = tube_a); } }'
    ir = _compile_source(src)
    result = validate(ir, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" in _codes(result)


def test_validate_with_env_structure_hold_target_checks_root_binding():
    missing = validate(
        _compile_source("protocol T { with env(thermal = 105C, duration = 5min) { hold(pcr_tube.structure.top); } }"),
        enforce_binding=True,
    )
    assert "SEM_UNBOUND_NAME_REFERENCE" in _codes(missing)

    bound_src = """
protocol T {
  let pcr_tube = tube(label = "PCR", capacity = 200uL);
  with env(thermal = 105C, duration = 5min) {
    hold(pcr_tube.structure.top);
  }
}
"""
    bound = validate(_compile_source(bound_src), enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" not in _codes(bound)


def test_validate_container_structure_target_view_paths():
    invalid_namespace = validate(_compile_source("protocol T { let target = pcr_tube.structure; }"))
    assert "SEM_CONTAINER_TARGET_VIEW_INVALID" in _codes(invalid_namespace)

    invalid_facet = validate(_compile_source("protocol T { let target = pcr_tube.structure.upper; }"))
    assert "SEM_CONTAINER_TARGET_VIEW_INVALID" in _codes(invalid_facet)

    invalid_deep = validate(_compile_source("protocol T { let target = pcr_tube.structure.top.inner; }"))
    assert "SEM_CONTAINER_TARGET_VIEW_INVALID" in _codes(invalid_deep)

    valid = validate(_compile_source("protocol T { let target = pcr_tube.structure.sidewall; }"))
    assert "SEM_CONTAINER_TARGET_VIEW_INVALID" not in _codes(valid)


def test_validate_with_env_hold_reports_container_structure_target_view_path_errors():
    invalid_namespace = validate(
        _compile_source("protocol T { with env(thermal = 105C, duration = 5min) { hold(pcr_tube.structure); } }")
    )
    assert "SEM_CONTAINER_TARGET_VIEW_INVALID" in _codes(invalid_namespace)

    invalid_facet = validate(
        _compile_source("protocol T { with env(thermal = 105C, duration = 5min) { hold(pcr_tube.structure.upper); } }")
    )
    assert "SEM_CONTAINER_TARGET_VIEW_INVALID" in _codes(invalid_facet)

    invalid_deep = validate(
        _compile_source(
            "protocol T { with env(thermal = 105C, duration = 5min) { hold(pcr_tube.structure.top.inner); } }"
        )
    )
    assert "SEM_CONTAINER_TARGET_VIEW_INVALID" in _codes(invalid_deep)


def test_validate_with_env_hold_reports_let_bound_container_structure_target_view_path_errors():
    src = """
protocol T {
  let top_target = pcr_tube.structure.upper;
  with env(thermal = 105C, duration = 5min) {
    hold(top_target);
  }
}
"""
    result = validate(_compile_source(src))
    assert "SEM_CONTAINER_TARGET_VIEW_INVALID" in _codes(result)


def test_validate_include_exports_constructor_defined_names_for_binding():
    src = (
        'protocol A { let shared_tube = tube(label = "Shared", capacity = 100uL); } '
        'protocol B { include A; let obs = img(sample = shared_tube, quantity = fluorescence); }'
    )
    compiled = compile_ast(parse(src))
    result = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" not in _codes(result)


def test_validate_unbound_semantic_name_reference_across_ref_protocols():
    src = (
        'protocol A { let buffer_tube = tube(label = "Buffer", capacity = 100uL); } '
        'protocol B { include A; let obs = img(sample = RNA_Solution, quantity = fluorescence); }'
    )
    ir = _compile_source(src)
    result = validate(ir, initial_defined_names={"Buffer", "Water"}, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" in _codes(result)


def test_validate_external_reagent_name_requires_initial_binding():
    src = (
        'protocol T { '
        'let obs = img(sample = MasterMix, quantity = fluorescence); '
        '}'
    )
    ir = _compile_source(src)
    missing_binding = validate(ir, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" in _codes(missing_binding)

    with_binding = validate(ir, initial_defined_names={"MasterMix"}, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" not in _codes(with_binding)


def test_validate_identifier_form_unbound_name_requires_binding():
    src = 'protocol T { let obs = img(sample = tube_x, quantity = fluorescence); }'
    ir = _compile_source(src)
    result = validate(ir, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" in _codes(result)


def test_validate_member_assignment_root_requires_binding():
    src = 'protocol T { unknown.result.hit = true; }'
    with pytest.raises(ValueError, match="previously declared"):
        _compile_source(src)


def test_validate_legacy_lyse_alias_is_no_longer_implicitly_defined():
    src = """
protocol T {
  Lyse(sample = sample_tube, buffer = lysis_input, duration = 10min, temp = 4C);
  let g = sep(sample = Lysate, program = centrifuge_program( drive = 12000g));
}
"""
    ir = _compile_source(src)
    result = validate(ir, enforce_binding=True)
    assert "SEM_UNBOUND_NAME_REFERENCE" in _codes(result)


def test_validate_with_env_scalar_thermal_requires_duration():
    src = "protocol T { with env(thermal = 37C) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_ENV_DURATION_REQUIRED" in _codes(result)


def test_validate_with_env_accepts_day_scale_duration():
    src = "protocol T { with env(thermal = 25C, duration = 3day) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_with_env_requires_at_least_one_dimension():
    src = "protocol T { with env() { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_ENV_THERMAL_REQUIRED" in _codes(result)


def test_validate_with_env_duration_without_thermal_is_rejected():
    src = "protocol T { with env(duration = 10min) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_ENV_DURATION_WITHOUT_THERMAL" in _codes(result)


def test_validate_with_env_field_only_is_accepted():
    src = "protocol T { with env(field = mz_separation) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_with_env_field_duration_is_rejected():
    src = "protocol T { with env(field = mz_separation, duration = 10s) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_ENV_DURATION_WITHOUT_THERMAL" in _codes(result)


def test_validate_with_env_shake_is_unknown_arg():
    src = "protocol T { with env(shake = 300Hz) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_UNKNOWN_ARG" in _codes(result)


def test_validate_ecp_quantity_surface_is_accepted():
    src = """
protocol T {
  let tube = tube(label = "Sample", capacity = 100uL);
  let obs = ecp(sample = tube, quantity = ph);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_with_env_field_rejects_thermal_modifiers():
    src = "protocol T { with env(field = mz_separation, co2 = 5%) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_ENV_ARG_CONFLICT" in _codes(result)


def test_validate_explicit_hold_with_env_is_accepted():
    src = "protocol T { with env(thermal = 37C, duration = 10min) { hold(sample = tube); } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_compile_incubate_requires_sample_arg_at_component_boundary():
    src = "protocol T { Incubate(temp = 37C, duration = 10min); }"
    with pytest.raises(ValueError, match="requires argument 'sample'"):
        _compile_source(src)


def test_validate_let_bound_measure_is_rejected_outside_current_stdlib_scope():
    src = 'protocol T { let obs = Measure(sample = tube_a, method = "UV", device = "NanoDrop", wavelength = 260nm); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_MEASURE_STDLIB_ROUTE_UNSUPPORTED" in _codes(result)


def test_validate_statement_electrophoresis_stdlib_lowering_accepts_img_step():
    src = """
protocol T {
  let gel_lane = tube(label = "Lane", capacity = 100uL, load = [content(kind = "biosample", code = "DNA01", type = "dna_sample"):10uL]);
  let stain_tube = tube(label = "Stain", capacity = 100uL, load = [buffer(code = "STN", type = "gel_stain"):20uL]);
  let gel_obs_schema = data_schema(label = "GelObs", fields = [bands]);
  Electrophoresis(
    sample = gel_lane,
    gel_type = "agarose",
    stain = stain_tube,
    field = 100V,
    duration = 30min,
    readout_schema = gel_obs_schema
  );
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_UNKNOWN_STEP" not in _codes(result)


def test_validate_builtin_method_step_append_is_accepted():
    ir = _compile_source("protocol T { seq_data.items.append(read); }")
    result = validate(ir)
    assert "SEM_UNKNOWN_STEP" not in _codes(result)


def test_validate_let_bound_pcr_is_supported_via_component_return():
    src = 'protocol T { let p = PCR(sample = pcr_well, primers = "Panel", cycles = 35, annealing_temp = 60C); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_PCR_STDLIB_RETURN_UNSUPPORTED" not in _codes(result)


def test_validate_let_bound_extract_dna_precipitation_is_supported_via_component_return():
    src = """
protocol T {
  let dna = ExtractDNAPrecipitation(
    sample = lysate,
    precip_buffer = precip_in,
    wash_inputs = [wash1],
    dissolve_buffer = dissolve_in,
    output = dna_out,
    cleanup_temp = 25C,
    cleanup_duration = 3min
  );
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_EXTRACT_DNA_STDLIB_RETURN_UNSUPPORTED" not in _codes(result)


def test_validate_let_bound_lyse_is_supported_via_component_return():
    src = """
protocol T {
  let lysed = Lyse(sample = sample_tube, buffer = lysis_input, duration = 10min, temp = 4C);
  let g = sep(sample = lysed, program = centrifuge_program( drive = 12000g));
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_LYSE_STDLIB_RETURN_UNSUPPORTED" not in _codes(result)


def test_validate_with_env_thermal_program_forbids_outer_duration():
    src = """
protocol T {
  let tp = thermal_program(from = 95C, duration = 30s);
  with env(thermal = tp, duration = 30min) { hold(sample = tube); }
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_ENV_DURATION_FORBIDDEN_WITH_THERMAL_PROGRAM" in _codes(result)


def test_validate_with_env_thermal_program_rejects_co2():
    src = """
protocol T {
  let tp = thermal_program(from = 95C, duration = 30s);
  with env(thermal = tp, co2 = 5%) { hold(sample = tube); }
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_ENV_ARG_CONFLICT" in _codes(result)


def test_validate_with_env_thermal_program_accepts_let_bound_descriptor_alias():
    src = """
protocol T {
  let tp = thermal_program(from = 95C, duration = 30s);
  with env(thermal = tp) { hold(sample = tube); }
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_let_bound_customized_img_requires_schema_ref():
    src = """
protocol T {
  let obs = img(sample = tube, quantity = customized);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_MISSING_REQUIRED_ARG" in _codes(result)
    assert any("schema_ref" in d.message for d in result.diagnostics)


def test_validate_group_index_base_must_be_group_binding():
    src = """
protocol T {
  let obs = img(sample = tube_a, quantity = fluorescence);
  tube_b << [obs[0]:1uL];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INVALID_GROUP_INDEX_BASE" in _codes(result)


def test_validate_grouped_img_let_binding_is_accepted():
    src = """
protocol T {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  let obs_group = img(sample = plate96[A1:A2], quantity = fluorescence);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_grouped_img_binding_supports_static_index_use():
    src = """
protocol T {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  let obs_group = img(sample = plate96[A1:A2], quantity = fluorescence);
  if obs_group[0].result.signal >= 1000 {
    img(sample = tube_a, quantity = fluorescence);
  }
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_grouped_img_binding_rejects_static_out_of_range_index():
    src = """
protocol T {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  let obs_group = img(sample = plate96[A1:A2], quantity = fluorescence);
  if obs_group[9].result.signal >= 1000 {
    img(sample = tube_a, quantity = fluorescence);
  }
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INDEX_OUT_OF_RANGE" in _codes(result)


def test_validate_sep_group_index_out_of_range():
    src = """
protocol T {
  let g = sep(sample = lysate, program = centrifuge_program( drive = 12000g));
  out_tube << [g[2]:1uL];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INDEX_OUT_OF_RANGE" in _codes(result)


def test_validate_fraction_group_index_requires_static_integer():
    src = """
protocol T {
  let fp = density_gradient_program(axis = density, order = top_to_bottom, bins = 4);
  let fg = frac(sample = source_tube, program = fp);
  out_tube << [fg[idx]:1uL];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INDEX_NOT_STATIC_INTEGER" in _codes(result)


def test_validate_fraction_group_index_must_be_nonnegative_integer():
    src = """
protocol T {
  let fp = density_gradient_program(axis = density, order = top_to_bottom, bins = 4);
  let fg = frac(sample = source_tube, program = fp);
  out_tube << [fg[-1]:1uL];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INDEX_NOT_NONNEGATIVE_INTEGER" in _codes(result)


def test_validate_fraction_group_index_respects_static_bins():
    src = """
protocol T {
  let fp = density_gradient_program(axis = density, order = top_to_bottom, bins = 4);
  let fg = frac(sample = source_tube, program = fp);
  out_tube << [fg[9]:1uL];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INDEX_OUT_OF_RANGE" in _codes(result)


def test_validate_standalone_content_constructor_is_forbidden():
    src = 'protocol T { let stock = content(kind = "biosample", code = "S1", type = "dna_sample"); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_STANDALONE_CONTENT_INIT_FORBIDDEN" in _codes(result)


def test_validate_tube_call_accepts_open_lid_flag():
    src = 'protocol T { let c = tube(label = "Tube", open = true); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_surface_call_is_accepted():
    src = 'protocol T { let s = surface(label = "Detector_Surface"); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_stream_call_requires_unit():
    src = 'protocol T { let events = stream(sample = tube_a); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_MISSING_REQUIRED_ARG" in _codes(result)
    assert any("unit" in d.message for d in result.diagnostics)


def test_validate_data_schema_call_requires_label():
    src = 'protocol T { let s = data_schema(fields = [signal]); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_MISSING_REQUIRED_ARG" in _codes(result)
    assert any("label" in d.message for d in result.diagnostics)


def test_validate_sep_call_requires_program():
    src = 'protocol T { let g = sep(sample = lysate); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_MISSING_REQUIRED_ARG" in _codes(result)
    assert any("program" in d.message for d in result.diagnostics)


def test_validate_keep_source_is_unknown_for_non_centrifuge_program():
    src = """
protocol T {
  let g = sep(sample = lysate, program = filtration_program(membrane = "silica", drive = pressure, keep_source = "pellet"));
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_UNKNOWN_ARG" in _codes(result)


def test_validate_keep_source_only_accepts_supernatant_or_pellet():
    src = """
protocol T {
  let g = sep(sample = lysate, program = centrifuge_program( drive = 12000g, keep_source = "primary"));
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INVALID_PROGRAM_ARG_VALUE" in _codes(result)


def test_validate_program_text_enum_accepts_bare_identifiers():
    src = """
protocol T {
  let fp = density_gradient_program(axis = density, order = top_to_bottom, bins = 8);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_magnetic_program_accepts_current_optional_args():
    src = """
protocol T {
  let g = sep(sample = lysate, program = magnetic_program(duration = 10s));
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_disrupt_program_accepts_current_optional_args():
    src = """
protocol T {
  let g = sep(sample = lysate, program = disrupt_program(duration = 10s));
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_precipitation_program_accepts_current_optional_duration():
    src = """
protocol T {
  let g = sep(sample = lysate, program = precipitation_program(reagent = cleanup_capture, duration = 10s));
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_validate_mutation_without_exec_options_is_accepted():
    src = "protocol T { tube << [feed:1uL]; }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_MUTATION_PROGRAM_REQUIRED" not in _codes(result)


def test_validate_with_constraint_requires_non_empty_body():
    src = "protocol T { with constraint(gentle) { } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_CONSTRAINT_BODY_REQUIRED" in _codes(result)


def test_validate_unknown_requirement_is_rejected():
    src = "protocol T { with constraint(unknown_requirement) { tube << [feed:1uL]; } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_UNKNOWN_REQUIREMENT" in _codes(result)


def test_validate_customized_constraint_requires_schema_ref():
    src = "protocol T { with constraint(customized) { tube << [feed:1uL]; } }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_CONSTRAINT_CUSTOMIZED_SCHEMA_REQUIRED" in _codes(result)


def test_validate_customized_constraint_must_not_mix_with_standard_requirements():
    src = """
protocol T {
  let s = data_schema(label = "X", fields = [signal]);
  with constraint(customized, gentle, schema_ref = s) {
    tube << [feed:1uL];
  }
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_CONSTRAINT_CUSTOMIZED_EXCLUSIVE" in _codes(result)


def test_validate_standard_requirement_disallows_constraint_options():
    src = """
protocol T {
  let s = data_schema(label = "X", fields = [signal]);
  with constraint(gentle, schema_ref = s) {
    tube << [feed:1uL];
  }
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_CONSTRAINT_UNKNOWN_OPTION" in _codes(result)


def test_validate_requirement_action_family_mismatch_is_rejected():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  with constraint(preserve_boundary) {
    let obs = img(sample = tube, quantity = fluorescence);
  }
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH" in _codes(result)


def test_validate_cold_chain_conflicts_with_high_temperature_env():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  with constraint(cold_chain) {
    with env(thermal = 37C, duration = 10min) { hold(sample = tube); }
  }
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_CONSTRAINT_ENV_CONFLICT" in _codes(result)


def test_validate_data_group_ref_classifies_as_group_binding():
    ir = _compile_source("protocol T { let reads = data_group_ref(kind = sequence_read); }")
    let_stmt = ir.protocols[0].statements[0]
    binding = _classify_group_binding(let_stmt.value, literal_bindings={}, expr_bindings={"reads": let_stmt.value})
    assert binding is not None
    assert binding.kind == "data_group"


def test_validate_mutation_disallows_mixed_source_styles():
    src = "protocol T { tube << [feed_a:1uL, feed_b]; }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_MUTATION_QUANTITY_STYLE_CONFLICT" in _codes(result)


def test_validate_source_partition_accepts_sep_family_program_in_mutation_source():
    src = """
protocol T {
  let spin = centrifuge_program(drive = 12000g);
  dst << [src.partition(spin)[0]:120uL];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    codes = _codes(result)
    assert "SEM_SOURCE_PARTITION_CONTEXT_INVALID" not in codes
    assert "SEM_PROGRAM_OWNER_MISMATCH" not in codes
    assert "SEM_INDEX_OUT_OF_RANGE" not in codes


def test_validate_source_partition_rejects_frac_program():
    src = """
protocol T {
  let gradient = density_gradient_program(axis = density, order = top_to_bottom, bins = 8);
  dst << [src.partition(gradient)[0]:120uL];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_PROGRAM_OWNER_MISMATCH" in _codes(result)


def test_validate_source_partition_rejects_out_of_range_index():
    src = """
protocol T {
  let spin = centrifuge_program(drive = 12000g);
  dst << [src.partition(spin)[2]:120uL];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_INDEX_OUT_OF_RANGE" in _codes(result)


def test_validate_source_partition_rejects_non_source_context():
    src = """
protocol T {
  let spin = centrifuge_program(drive = 12000g);
  let portion = src.partition(spin)[0];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_SOURCE_PARTITION_CONTEXT_INVALID" in _codes(result)


def test_validate_standalone_sep_accepts_sep_program():
    src = """
protocol T {
  let sample = tube(label = "Sample", capacity = 100uL);
  sep(sample = sample, program = centrifuge_program(drive = 12000g));
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    codes = _codes(result)
    assert "SEM_UNKNOWN_STEP" not in codes
    assert "SEM_PROGRAM_OWNER_MISMATCH" not in codes


def test_validate_standalone_frac_accepts_frac_program():
    src = """
protocol T {
  let sample = tube(label = "Sample", capacity = 100uL);
  frac(sample = sample, program = density_gradient_program(axis = density, order = top_to_bottom, bins = 3));
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    codes = _codes(result)
    assert "SEM_UNKNOWN_STEP" not in codes
    assert "SEM_PROGRAM_OWNER_MISMATCH" not in codes


def test_validate_container_contents_index_accepts_mutation_source_context():
    src = """
protocol T {
  waste << [tube.contents[1]:120uL];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_CONTAINER_CONTENTS_INDEX_CONTEXT_INVALID" not in _codes(result)
    assert "SEM_INVALID_GROUP_INDEX_BASE" not in _codes(result)


def test_validate_container_contents_index_rejects_non_source_context():
    src = """
protocol T {
  let portion = tube.contents[1];
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_CONTAINER_CONTENTS_INDEX_CONTEXT_INVALID" in _codes(result)


def test_validate_legacy_generic_program_form_is_rejected():
    src = 'protocol T { let g = sep(sample = lysate, program = sep_program(mode = "centrifuge", speed = 12000g, duration = 10min)); }'
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_LEGACY_PROGRAM_FORM_FORBIDDEN" in _codes(result)


def test_validate_with_env_empty_body_is_rejected():
    src = "protocol T { with env(thermal = 37C, duration = 1min) {} }"
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_ENV_BODY_REQUIRED" in _codes(result)


def test_validate_agit_accepts_shake_duration_rate():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = shake, duration = 30s, rate = 800rpm);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_AGIT_MODE_UNKNOWN" not in _codes(result)
    assert "SEM_AGIT_ARG_CONFLICT" not in _codes(result)


def test_validate_agit_rejects_invert_with_duration():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = invert, duration = 30s);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_AGIT_ARG_CONFLICT" in _codes(result)


def test_validate_agit_rejects_shake_with_cycles():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = shake, cycles = 10);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_AGIT_ARG_CONFLICT" in _codes(result)


def test_validate_agit_rejects_unknown_mode():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = spin, duration = 30s);
}
"""
    ir = _compile_source(src)
    result = validate(ir)
    assert "SEM_AGIT_MODE_UNKNOWN" in _codes(result)
