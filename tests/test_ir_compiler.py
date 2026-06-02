from __future__ import annotations

import json
from pathlib import Path

import pytest
from lark.exceptions import UnexpectedInput

from culsma.common.source import Span
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.analysis import build_compile_analysis
from culsma.pipeline.compile import compile_ast as _compile_ast
from culsma.pipeline.component_expander import expand_component_calls
from culsma.parser.ast_nodes import CallExpr, LetStatement, Program, ProtocolDecl, Quantity
from culsma.parser.parser import parse, parse_file, parse_files


ROOT = Path(__file__).resolve().parents[1]
PARSER_FIXTURES = ROOT / "tests" / "fixtures_parser"
LEGACY_PARSER_FIXTURES = ROOT / "tests" / "fixtures_parser_legacy"
CURRENT_CORE_FIXTURE = PARSER_FIXTURES / "current_frontend_core.culs"
CURRENT_READOUT_FIXTURE = PARSER_FIXTURES / "current_frontend_readout.culs"
IR_FIXTURES = ROOT / "tests" / "fixtures_ir"


def _load_golden(name: str) -> dict:
    return json.loads((IR_FIXTURES / name).read_text(encoding="utf-8"))


def compile_to_ir(ast):
    return _compile_ast(resolve_program(ast).prepared_program).ir


def compile_ast(ast):
    return _compile_ast(resolve_program(ast).prepared_program)


def test_compile_current_frontend_core_fixture_smoke():
    ast = parse_file(CURRENT_CORE_FIXTURE)
    ir = compile_to_ir(ast)
    assert ir.protocols
    assert ir.protocols[0].name == "CurrentFrontendCore"


def test_compile_legacy_dna_extraction_fixture_is_rejected_by_current_source_gate():
    ast = parse_file(LEGACY_PARSER_FIXTURES / "dna_extraction.culs")
    with pytest.raises(ValueError, match="staining_method"):
        compile_to_ir(ast)


def test_compile_current_frontend_core_fixture_preserves_new_ir_shapes():
    ast = parse_file(CURRENT_CORE_FIXTURE)
    ir = compile_to_ir(ast)
    protocol = ir.protocols[0]
    assert [stmt.__class__.__name__ for stmt in protocol.statements] == [
        "IRLet",
        "IRLet",
        "IRLet",
        "IRLet",
        "IRLet",
        "IRWithEnv",
        "IRLet",
        "IRLet",
        "IRLet",
        "IRMutation",
    ]
    with_env = protocol.statements[5]
    assert with_env.__class__.__name__ == "IRWithEnv"
    assert [arg.name for arg in with_env.env_args] == ["thermal", "duration"]
    assert len(with_env.statements) == 3
    assert all(stmt.__class__.__name__ == "IRMutation" for stmt in with_env.statements)
    final_mutation = protocol.statements[9]
    assert final_mutation.__class__.__name__ == "IRMutation"
    assert final_mutation.target.__class__.__name__ == "IRIndex"


def test_compile_current_frontend_readout_fixture_preserves_call_exprs():
    ast = parse_file(CURRENT_READOUT_FIXTURE)
    ir = compile_to_ir(ast)
    protocol = ir.protocols[0]
    thermal_prog_let = protocol.statements[2]
    assert thermal_prog_let.__class__.__name__ == "IRLet"
    assert thermal_prog_let.value.__class__.__name__ == "IRCall"
    assert thermal_prog_let.value.name == "thermal_program"
    img_obs_let = protocol.statements[4]
    assert img_obs_let.value.__class__.__name__ == "IRCall"
    assert img_obs_let.value.name == "img"


def test_compile_removed_htr_flow_program_is_rejected_by_current_source_gate():
    with pytest.raises(ValueError, match="legacy-only"):
        compile_to_ir(parse('protocol T { let h = flow_program(channels = ["FSC"], sort = true, sort_bins = 4); }'))


def test_compile_assignment_lowers_to_irassign():
    ir = compile_to_ir(parse("protocol T { let total = 0uL; total = total + 50uL; }"))
    statements = ir.protocols[0].statements
    assert [stmt.__class__.__name__ for stmt in statements] == ["IRLet", "IRAssign"]
    assert statements[1].target.__class__.__name__ == "IRIdentifier"
    assert statements[1].target.name == "total"
    assert statements[1].value.__class__.__name__ == "IRBinary"


def test_compile_member_assignment_lowers_to_irassign_member_target():
    ir = compile_to_ir(parse('protocol T { let read = data_ref(kind = sequence_read); read.result.hit = true; }'))
    statements = ir.protocols[0].statements
    assert [stmt.__class__.__name__ for stmt in statements] == ["IRLet", "IRAssign"]
    assert statements[1].target.__class__.__name__ == "IRMember"
    assert statements[1].target.member == "hit"
    assert statements[1].target.base.__class__.__name__ == "IRMember"
    assert statements[1].target.base.member == "result"


def test_compile_assignment_requires_prior_declaration():
    with pytest.raises(ValueError, match="previously declared"):
        compile_to_ir(parse("protocol T { total = 50uL; }"))


def test_compile_mutation_without_exec_options_is_accepted():
    ir = compile_to_ir(parse("protocol T { dst << [src:10uL]; }"))
    stmt = ir.protocols[0].statements[0]
    assert stmt.__class__.__name__ == "IRMutation"
    assert not hasattr(stmt, "exec_options")


def test_compile_with_constraint_block_lowers_to_ir_with_constraint():
    ir = compile_to_ir(
        parse(
            """
protocol T {
  with constraint(gentle, preserve_boundary) {
    dst << [src:10uL];
  }
}
"""
        )
    )
    stmt = ir.protocols[0].statements[0]
    assert stmt.__class__.__name__ == "IRWithConstraint"
    assert stmt.requirements == ["gentle", "preserve_boundary"]
    assert len(stmt.statements) == 1
    assert stmt.statements[0].__class__.__name__ == "IRMutation"


def test_compile_trailing_with_constraint_sugar_lowers_to_ir_with_constraint():
    ir = compile_to_ir(
        parse("protocol T { dst << [src:10uL] with constraint(gentle, preserve_boundary); }")
    )
    stmt = ir.protocols[0].statements[0]
    assert stmt.__class__.__name__ == "IRWithConstraint"
    assert stmt.requirements == ["gentle", "preserve_boundary"]
    assert len(stmt.statements) == 1
    assert stmt.statements[0].__class__.__name__ == "IRMutation"


def test_compile_method_call_expression_lowers_to_ircall():
    ir = compile_to_ir(parse("protocol T { let ok = detector_surface.detects(ion); }"))
    stmt = ir.protocols[0].statements[0]
    assert stmt.__class__.__name__ == "IRLet"
    assert stmt.value.__class__.__name__ == "IRCall"
    assert stmt.value.name == "detects"
    assert [arg.name for arg in stmt.value.args] == ["self", "arg0"]


def test_compile_method_call_statement_lowers_to_irstep():
    ir = compile_to_ir(parse("protocol T { seq_data.items.append(read); }"))
    stmt = ir.protocols[0].statements[0]
    assert stmt.__class__.__name__ == "IRStep"
    assert stmt.name == "append"
    assert [arg.name for arg in stmt.args] == ["self", "arg0"]


def test_compile_protocol_returns_contract_is_preserved_in_ir():
    ir = compile_to_ir(
        parse(
            """
protocol T(sample) returns (prepared_out, seq_out) {
  return prepared_out = sample, seq_out = sample;
}
"""
        )
    )
    proto = ir.protocols[0]
    assert proto.returns == ["prepared_out", "seq_out"]


def test_compile_protocol_returns_requires_declared_bindings_match():
    with pytest.raises(ValueError, match="does not bind declared outputs"):
        compile_to_ir(
            parse(
                """
protocol T(sample) returns (prepared_out, seq_out) {
  return prepared_out = sample;
}
"""
            )
        )


def test_compile_component_let_bind_named_multi_return_is_rejected():
    with pytest.raises(ValueError, match="named multi-return"):
        compile_to_ir(
            parse(
                """
protocol Child(sample) returns (a, b) {
  return a = sample, b = sample;
}

protocol Parent(sample) {
  let x = Child(sample = sample);
}
"""
            )
        )


def test_compile_continuous_schedule_wraps_single_window_and_inherits_inner_time_boundary():
    ir = compile_to_ir(
        parse(
            """
protocol T {
  let count = 0;
  repeat perf in schedule(start = 0h, duration = 3h, mode = continuous) {
    repeat t in schedule(start = 1h, step = 1h) {
      count = count + 1;
    }
  }
}
"""
        )
    )
    statements = ir.protocols[0].statements
    assert [stmt.__class__.__name__ for stmt in statements] == ["IRLet", "IRAssign", "IRAssign", "IRAssign"]
    assert statements[1].id.startswith("p0.s1.i0.")
    assert statements[2].id.startswith("p0.s1.i0.")
    assert statements[3].id.startswith("p0.s1.i0.")


def test_compile_continuous_schedule_requires_explicit_mode():
    with pytest.raises(ValueError, match="discrete schedule does not allow duration"):
        compile_to_ir(parse("protocol T { repeat perf in schedule(start = 0h, duration = 3h) { break; } }"))


def test_component_expander_does_not_load_bundled_stdlib_implicitly():
    src = """
protocol T {
  let gel_obs = Electrophoresis(sample = gel_lane, gel_type = "Agarose_1.5pct", stain = stain_input, field = 100V, duration = 30min);
}
"""
    expanded = expand_component_calls(parse(src))
    stmt = expanded.protocols[0].statements[0]
    assert isinstance(stmt, LetStatement)
    assert isinstance(stmt.value, CallExpr)
    assert stmt.value.name == "Electrophoresis"


def test_resolve_program_explicitly_injects_bundled_stdlib_protocols():
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
    prepared = resolve_program(parse(src)).prepared_program
    assert not any(
        isinstance(stmt, LetStatement)
        and isinstance(stmt.value, CallExpr)
        and stmt.value.name == "Electrophoresis"
        for stmt in prepared.protocols[0].statements
    )


def test_compile_let_bound_electrophoresis_stdlib_expands_to_sep_mutation_and_img():
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
    ir = compile_to_ir(parse(src))
    statements = ir.protocols[0].statements
    assert any(getattr(stmt, "value", None) is not None and getattr(stmt.value, "name", None) == "sep" for stmt in statements)
    assert any(stmt.__class__.__name__ == "IRMutation" for stmt in statements)
    assert any(getattr(stmt, "value", None) is not None and getattr(stmt.value, "name", None) == "img" for stmt in statements)
    img_call = next(stmt.value for stmt in statements if getattr(getattr(stmt, "value", None), "name", None) == "img")
    assert any(getattr(arg.value, "name", None) == "customized" for arg in img_call.args if arg.name == "quantity")
    assert any(arg.name == "schema_ref" for arg in img_call.args)
    assert statements[-1].name == "gel_obs"


def test_compile_statement_electrophoresis_stdlib_expands_to_sep_mutation_and_img_step():
    src = """
protocol T {
  let gel_obs_schema = data_schema(label = "GelObs", fields = [bands]);
  Electrophoresis(
    sample = gel_lane,
    gel_type = "Agarose_1.5pct",
    stain = stain_input,
    field = 100V,
    duration = 30min,
    readout_schema = gel_obs_schema
  );
}
"""
    ir = compile_to_ir(parse(src))
    statements = ir.protocols[0].statements
    assert any(getattr(stmt, "value", None) is not None and getattr(stmt.value, "name", None) == "sep" for stmt in statements)
    assert any(stmt.__class__.__name__ == "IRMutation" for stmt in statements)
    assert any(getattr(stmt, "value", None) is not None and getattr(stmt.value, "name", None) == "img" for stmt in statements)


def test_ir_statements_always_have_span():
    ast = parse_file(CURRENT_CORE_FIXTURE)
    ir = compile_to_ir(ast)
    assert ir.span is not None
    assert len(ir.protocols) == 1
    protocol = ir.protocols[0]
    assert protocol.span is not None
    for stmt in protocol.statements:
        assert stmt.span is not None


def test_compile_is_deterministic_for_same_input():
    ast = parse_file(CURRENT_CORE_FIXTURE)
    ir1 = compile_to_ir(ast).to_dict()
    ir2 = compile_to_ir(ast).to_dict()
    assert ir1 == ir2


def test_compile_fails_when_span_is_missing():
    ast = Program(
        protocols=[
            ProtocolDecl(
                name="T",
                statements=[
                    LetStatement(
                        name="x",
                        value=Quantity(value=1.0, unit=None, span=None),
                        span=Span(line=1, col=1, start=0, end=9),
                    )
                ],
                span=Span(line=1, col=1, start=0, end=12),
            )
        ],
        span=Span(line=1, col=1, start=0, end=12),
    )

    with pytest.raises(ValueError, match="Missing span"):
        compile_to_ir(ast)


def test_compile_repeat_unrolls_to_linear_ir_steps():
    # ensure current frontend baseline still compiles before repeat-focused assertions
    assert compile_to_ir(parse_file(CURRENT_CORE_FIXTURE)).protocols

    src = 'protocol T { repeat 3 { Step(v = 1); } }'
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.id for stmt in protocol.statements] == ["p0.s0", "p0.s1", "p0.s2"]
    assert all(stmt.name == "Step" for stmt in protocol.statements)


def test_compile_repeat_accepts_let_bound_count():
    src = 'protocol T { let n = 1 + 2; repeat n { Step(v = 1); } }'
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.id for stmt in protocol.statements] == ["p0.s0", "p0.s1", "p0.s2", "p0.s3"]
    assert protocol.statements[0].__class__.__name__ == "IRLet"


def test_compile_repeat_rejects_non_integer_count():
    src = 'protocol T { repeat 2.5 { Step(v = 1); } }'
    with pytest.raises(ValueError, match="integer"):
        compile_to_ir(parse(src))


def test_compile_repeat_rejects_unit_count():
    src = 'protocol T { repeat 3min { Step(v = 1); } }'
    with pytest.raises(ValueError, match="unitless"):
        compile_to_ir(parse(src))


def test_compile_repeat_schedule_expands_time_points():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  with env(thermal = 37C, duration = 120min) {
    repeat t in schedule(start = 30min, step = 30min) {
      Step(v = t, sample = tube);
    }
  }
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    with_env = protocol.statements[1]
    assert with_env.__class__.__name__ == "IRWithEnv"
    assert len(with_env.statements) == 4
    values = [stmt.args[0].value.value for stmt in with_env.statements]
    units = [stmt.args[0].value.unit for stmt in with_env.statements]
    assert values == [30.0, 60.0, 90.0, 120.0]
    assert units == ["min", "min", "min", "min"]


def test_compile_repeat_schedule_expands_day_time_points():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  with env(thermal = 25C, duration = 3day) {
    repeat t in schedule(start = 1day, step = 1day) {
      Step(v = t, sample = tube);
    }
  }
}
"""
    ir = compile_to_ir(parse(src))
    with_env = ir.protocols[0].statements[1]
    assert with_env.__class__.__name__ == "IRWithEnv"
    assert len(with_env.statements) == 3
    values = [stmt.args[0].value.value for stmt in with_env.statements]
    units = [stmt.args[0].value.unit for stmt in with_env.statements]
    assert values == [1.0, 2.0, 3.0]
    assert units == ["day", "day", "day"]


def test_compile_explicit_hold_with_env_lowers_to_empty_irwithenv_body():
    src = "protocol T { with env(thermal = 37C, duration = 10min) { hold(sample = tube); } }"
    ir = compile_to_ir(parse(src))
    with_env = ir.protocols[0].statements[0]
    assert with_env.__class__.__name__ == "IRWithEnv"
    assert with_env.statements == []


def test_compile_rejects_top_level_hold():
    with pytest.raises(ValueError, match="hold\\(sample = \\.\\.\\.\\) is only valid as the sole statement inside with env"):
        compile_to_ir(parse("protocol T { hold(); }"))


def test_compile_rejects_mixed_hold_with_env_block():
    src = """
protocol T {
  with env(thermal = 37C, duration = 10min) {
    hold(sample = tube);
    Step();
  }
}
"""
    with pytest.raises(ValueError, match="hold\\(sample = \\.\\.\\.\\) must be the only statement inside with env"):
        compile_to_ir(parse(src))


def test_compile_rejects_direct_source_loadcontent_step():
    with pytest.raises(ValueError, match="LoadContent\\(\\.\\.\\.\\) is internal-only"):
        compile_to_ir(parse("protocol T { LoadContent(container = tube_a, content = dna_ref, amount = 10uL); }"))


def test_compile_rejects_legacy_electrophoresis_signature_for_current_stdlib_name():
    src = 'protocol T { Electrophoresis(sample = gel_lane, gel_type = "agarose", staining_method = "SYBR"); }'
    with pytest.raises(ValueError, match="does not accept argument 'staining_method'"):
        compile_to_ir(parse(src))


def test_compile_group_mutation_expands_to_ordered_per_target_mutations():
    src = """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL);
  let t2 = tube(label = "T2", capacity = 500uL);
  let feed = tube(label = "Feed", capacity = 500uL, load = [buffer(code = "B", type = "media"):200uL]);
  let aliquots = group([t1, t2]);
  aliquots << [feed:10uL];
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.__class__.__name__ for stmt in protocol.statements] == [
        "IRLet",
        "IRLet",
        "IRLet",
        "IRLet",
        "IRMutation",
        "IRMutation",
    ]
    group_let = protocol.statements[3]
    assert group_let.value.__class__.__name__ == "IRGroup"
    assert [stmt.target.name for stmt in protocol.statements[4:]] == ["t1", "t2"]


def test_compile_group_mutation_series_expands_positionally():
    src = """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL);
  let t2 = tube(label = "T2", capacity = 500uL);
  let t3 = tube(label = "T3", capacity = 500uL);
  let drug = tube(label = "Drug", capacity = 500uL, load = [buffer(code = "D", type = "drug_stock"):200uL]);
  let aliquots = group([t1, t2, t3]);
  aliquots << [series(drug, [5uL, 10uL, 20uL])];
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    mutations = protocol.statements[5:]
    assert [stmt.__class__.__name__ for stmt in mutations] == ["IRMutation", "IRMutation", "IRMutation"]
    assert [stmt.target.name for stmt in mutations] == ["t1", "t2", "t3"]
    assert [stmt.sources[0].right.value for stmt in mutations] == [5.0, 10.0, 20.0]
    assert all(stmt.sources[0].left.name == "drug" for stmt in mutations)


def test_compile_group_mutation_supports_broadcast_plus_series():
    src = """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL);
  let t2 = tube(label = "T2", capacity = 500uL);
  let media = tube(label = "Media", capacity = 500uL, load = [buffer(code = "M", type = "media"):200uL]);
  let drug = tube(label = "Drug", capacity = 500uL, load = [buffer(code = "D", type = "drug_stock"):200uL]);
  let aliquots = group([t1, t2]);
  aliquots << [media:50uL, series(drug, [5uL, 10uL])];
}
"""
    ir = compile_to_ir(parse(src))
    mutations = ir.protocols[0].statements[5:]
    assert len(mutations) == 2
    assert all(len(stmt.sources) == 2 for stmt in mutations)
    assert [stmt.sources[0].left.name for stmt in mutations] == ["media", "media"]
    assert [stmt.sources[1].left.name for stmt in mutations] == ["drug", "drug"]
    assert [stmt.sources[1].right.value for stmt in mutations] == [5.0, 10.0]


def test_compile_series_rejects_scalar_target():
    src = """
protocol T {
  let tube1 = tube(label = "T1", capacity = 500uL);
  let drug = tube(label = "Drug", capacity = 500uL, load = [buffer(code = "D", type = "drug_stock"):200uL]);
  tube1 << [series(drug, [5uL])];
}
"""
    with pytest.raises(ValueError, match="group-like mutation target"):
        compile_to_ir(parse(src))


def test_compile_series_rejects_length_mismatch():
    src = """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL);
  let t2 = tube(label = "T2", capacity = 500uL);
  let drug = tube(label = "Drug", capacity = 500uL, load = [buffer(code = "D", type = "drug_stock"):200uL]);
  let aliquots = group([t1, t2]);
  aliquots << [series(drug, [5uL, 10uL, 20uL])];
}
"""
    with pytest.raises(ValueError, match="target group cardinality"):
        compile_to_ir(parse(src))


def test_parse_series_rejects_non_mutation_usage():
    src = 'protocol T { let xs = series(drug, [5uL, 10uL]); }'
    with pytest.raises(UnexpectedInput):
        parse(src)


def test_compile_plate_selector_mutation_synthesizes_wells_and_broadcasts():
    src = """
protocol T {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  let media = tube(label = "Media", capacity = 5000uL, load = [buffer(code = "MED", type = "culture_media"):1000uL]);
  plate96[A1:B2] << [media:50uL];
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    kinds = [stmt.__class__.__name__ for stmt in protocol.statements]
    assert kinds == ["IRLet", "IRLet", "IRLet", "IRLet", "IRLet", "IRLet", "IRMutation", "IRMutation", "IRMutation", "IRMutation"]
    synth_lets = protocol.statements[2:6]
    synth_names = [stmt.name for stmt in synth_lets]
    assert synth_names == [
        "__lw_plate_plate96_A1",
        "__lw_plate_plate96_A2",
        "__lw_plate_plate96_B1",
        "__lw_plate_plate96_B2",
    ]
    targets = [stmt.target.name for stmt in protocol.statements[6:]]
    assert targets == synth_names


def test_compile_with_env_on_group_binding_flattens_targets_without_duplicate_env_steps():
    src = """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL);
  let t2 = tube(label = "T2", capacity = 500uL);
  let aliquots = group([t1, t2]);
  with env(thermal = 37C, duration = 10min) {
    hold(sample = aliquots);
  }
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.__class__.__name__ for stmt in protocol.statements] == ["IRLet", "IRLet", "IRLet", "IRWithEnv"]
    with_env = protocol.statements[3]
    assert [target.name for target in with_env.targets] == ["t1", "t2"]


def test_compile_grouped_img_preserves_ir_group_sample():
    src = """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL);
  let t2 = tube(label = "T2", capacity = 500uL);
  let wells = group([t1, t2]);
  let obs_group = img(sample = wells, quantity = fluorescence);
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.__class__.__name__ for stmt in protocol.statements] == ["IRLet", "IRLet", "IRLet", "IRLet"]
    obs_let = protocol.statements[3]
    assert obs_let.value.__class__.__name__ == "IRCall"
    sample_arg = next(arg for arg in obs_let.value.args if arg.name == "sample")
    assert sample_arg.value.__class__.__name__ == "IRGroup"
    assert [element.name for element in sample_arg.value.elements] == ["t1", "t2"]


def test_compile_plate_selector_img_synthesizes_wells_and_group_sample():
    src = """
protocol T {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  let obs_group = img(sample = plate96[A1:B2], quantity = fluorescence);
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    synth_lets = protocol.statements[1:5]
    assert [stmt.name for stmt in synth_lets] == [
        "__lw_plate_plate96_A1",
        "__lw_plate_plate96_A2",
        "__lw_plate_plate96_B1",
        "__lw_plate_plate96_B2",
    ]
    obs_let = protocol.statements[5]
    sample_arg = next(arg for arg in obs_let.value.args if arg.name == "sample")
    assert sample_arg.value.__class__.__name__ == "IRGroup"
    assert [element.name for element in sample_arg.value.elements] == [
        "__lw_plate_plate96_A1",
        "__lw_plate_plate96_A2",
        "__lw_plate_plate96_B1",
        "__lw_plate_plate96_B2",
    ]


def test_compile_plate_selector_let_synthesizes_wells_and_group_value():
    src = """
protocol T {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  let wells = plate96[A1:B2];
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.__class__.__name__ for stmt in protocol.statements] == [
        "IRLet",
        "IRLet",
        "IRLet",
        "IRLet",
        "IRLet",
        "IRLet",
    ]
    synth_lets = protocol.statements[1:5]
    synth_names = [
        "__lw_plate_plate96_A1",
        "__lw_plate_plate96_A2",
        "__lw_plate_plate96_B1",
        "__lw_plate_plate96_B2",
    ]
    assert [stmt.name for stmt in synth_lets] == synth_names
    wells_let = protocol.statements[5]
    assert wells_let.name == "wells"
    assert wells_let.value.__class__.__name__ == "IRGroup"
    assert [element.name for element in wells_let.value.elements] == synth_names


def test_compile_plate_selector_return_synthesizes_wells_and_group_binding():
    src = """
protocol T returns (wells) {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  return wells = plate96[A1:B2];
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.__class__.__name__ for stmt in protocol.statements] == [
        "IRLet",
        "IRLet",
        "IRLet",
        "IRLet",
        "IRLet",
    ]
    synth_names = [
        "__lw_plate_plate96_A1",
        "__lw_plate_plate96_A2",
        "__lw_plate_plate96_B1",
        "__lw_plate_plate96_B2",
    ]
    assert [stmt.name for stmt in protocol.statements[1:5]] == synth_names
    return_binding = protocol.return_bindings[0]
    assert return_binding.name == "wells"
    assert return_binding.value.__class__.__name__ == "IRGroup"
    assert [element.name for element in return_binding.value.elements] == synth_names


def test_compile_group_constructor_rejects_nested_group_binding():
    src = """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL);
  let inner = group([t1]);
  let outer = group([inner]);
  outer << [t1];
}
"""
    with pytest.raises(ValueError, match="Nested groups"):
        compile_to_ir(parse(src))


def test_compile_plate_selector_requires_plate_binding():
    src = """
protocol T {
  let tube_a = tube(label = "A", capacity = 500uL);
  tube_a[A1:A2] << [tube_a:10uL];
}
"""
    with pytest.raises(ValueError, match="must resolve to let-bound plate"):
        compile_to_ir(parse(src))


def test_compile_repeat_schedule_expands_named_points():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  with env(thermal = 37C, duration = 120min) {
    repeat point in schedule(at = [15min, 45min, 120min]) {
      Step(v = point, sample = tube);
    }
  }
}
"""
    ir = compile_to_ir(parse(src))
    with_env = ir.protocols[0].statements[1]
    assert [stmt.args[0].value.value for stmt in with_env.statements] == [15.0, 45.0, 120.0]


def test_compile_repeat_schedule_resolves_point_conditionals():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  with env(thermal = 37C, duration = 120min) {
    repeat point in schedule(at = [15min, 45min, 120min]) {
      if point == 45min {
        Step(v = point, sample = tube);
      }
    }
  }
}
"""
    ir = compile_to_ir(parse(src))
    with_env = ir.protocols[0].statements[1]
    assert len(with_env.statements) == 1
    assert with_env.statements[0].args[0].value.value == 45.0
    assert with_env.statements[0].args[0].value.unit == "min"


def test_compile_repeat_schedule_expands_integer_counts():
    src = """
protocol T {
  repeat count in schedule(start = 1, end = 3, step = 1) {
    Step(v = count);
  }
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.args[0].value.value for stmt in protocol.statements] == [1.0, 2.0, 3.0]


def test_compile_repeat_schedule_rejects_non_schedule_iterable():
    src = 'protocol T { repeat t in 3 { Step(v = t); } }'
    with pytest.raises(ValueError, match="schedule"):
        compile_to_ir(parse(src))


def test_compile_repeat_schedule_rejects_env_boundary_overflow():
    src = """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  with env(thermal = 37C, duration = 120min) {
    repeat t in schedule(start = 30min, end = 150min, step = 30min) {
      Step(v = t, sample = tube);
    }
  }
}
"""
    with pytest.raises(ValueError, match="env boundary"):
        compile_to_ir(parse(src))


def test_compile_if_true_selects_then_branch():
    src = 'protocol T { if true { Step(v = 1); } else { Step(v = 2); } }'
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert len(protocol.statements) == 1
    assert protocol.statements[0].id == "p0.s0"
    assert protocol.statements[0].name == "Step"
    assert protocol.statements[0].args[0].value.value == 1.0


def test_compile_if_false_selects_else_branch():
    src = 'protocol T { if false { Step(v = 1); } else { Step(v = 2); } }'
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert len(protocol.statements) == 1
    assert protocol.statements[0].args[0].value.value == 2.0


def test_compile_if_with_comparison_and_let_binding():
    src = 'protocol T { let n = 3; if n > 2 { Step(v = 9); } else { Step(v = 0); } }'
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.id for stmt in protocol.statements] == ["p0.s0", "p0.s1"]
    assert protocol.statements[1].args[0].value.value == 9.0


def test_compile_if_rejects_non_boolean_condition():
    src = 'protocol T { if 1 { Step(v = 1); } else { Step(v = 2); } }'
    with pytest.raises(ValueError, match="compile-time boolean"):
        compile_to_ir(parse(src))


def test_compile_runtime_if_preserves_conditional_ir():
    src = """
protocol T {
  let obs = img(sample = tube_a, quantity = fluorescence);
  if obs.result.signal >= 1000 {
    Step(v = 1);
  } else {
    Step(v = 2);
  }
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.__class__.__name__ for stmt in protocol.statements] == ["IRLet", "IRConditional"]
    conditional = protocol.statements[1]
    assert conditional.condition.__class__.__name__ == "IRBinary"
    assert conditional.then_statements[0].__class__.__name__ == "IRStep"
    assert conditional.else_statements[0].__class__.__name__ == "IRStep"

def test_compile_break_and_continue_lower_to_ir_control():
    src = 'protocol T { repeat 2 { if obs.result.signal >= 1000 { continue; } break; } }'
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert [stmt.__class__.__name__ for stmt in protocol.statements] == ["IRConditional", "IRControl", "IRConditional", "IRControl"]
    assert protocol.statements[0].then_statements[0].__class__.__name__ == "IRControl"
    assert protocol.statements[0].then_statements[0].action == "continue"
    assert protocol.statements[1].action == "break"
    assert protocol.statements[3].action == "break"


def test_compile_with_env_thermal_program_does_not_duplicate_body():
    src = """
protocol T {
  let tp = thermal_program(from = 95C, duration = 30s);
  with env(thermal = tp) {
    pcr_well << [feed:1uL];
  }
}
"""
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert len(protocol.statements) == 2
    with_env = protocol.statements[1]
    assert with_env.__class__.__name__ == "IRWithEnv"
    assert len(with_env.statements) == 1
    assert with_env.statements[0].__class__.__name__ == "IRMutation"


def test_compile_old_thermal_program_cycles_shape_is_rejected():
    src = 'protocol T { let tp = thermal_program(from = 95C, duration = 30s, cycles = 35); }'
    with pytest.raises(ValueError, match="cycles"):
        compile_to_ir(parse(src))


def test_compile_incubate_statement_expands_to_ir_with_env():
    src = 'protocol T { Incubate(sample = tube_a, temp = 37C, duration = 10min); }'
    ir = compile_to_ir(parse(src))
    protocol = ir.protocols[0]
    assert len(protocol.statements) == 4
    stmt = protocol.statements[-1]
    assert stmt.__class__.__name__ == "IRWithEnv"
    assert [arg.name for arg in stmt.env_args] == ["thermal", "duration"]
    assert stmt.targets[0].__class__.__name__ == "IRIdentifier"
    assert stmt.statements == []


def test_compile_let_bound_local_component_inlines_tail_return():
    src = """
protocol MixAndReturn(sample, diluent) {
  sample << [diluent];
  return sample;
}
protocol T {
  let final_tube = MixAndReturn(sample = tube_a, diluent = buffer_b);
}
"""
    ir = compile_to_ir(parse(src))
    protocol = next(p for p in ir.protocols if p.name == "T")
    assert [stmt.__class__.__name__ for stmt in protocol.statements] == ["IRLet", "IRLet", "IRMutation"]
    assert protocol.statements[0].name == "final_tube"


def test_compile_let_bound_lyse_expands_to_with_env_and_return_binding():
    src = 'protocol T { let lysed = Lyse(sample = sample_tube, buffer = lysis_input, duration = 10min, temp = 4C); let sep_group = sep(sample = lysed, program = centrifuge_program( drive = 12000g)); }'
    ir = compile_to_ir(parse(src))
    statements = ir.protocols[0].statements
    assert statements[0].__class__.__name__ == "IRLet"
    with_env = next(stmt for stmt in statements if stmt.__class__.__name__ == "IRWithEnv")
    assert [arg.name for arg in with_env.env_args] == ["thermal", "duration"]
    assert [nested.__class__.__name__ for nested in with_env.statements] == ["IRMutation", "IRLet", "IRMutation"]
    assert with_env.statements[1].value.name == "sep"
    assert statements[0].name == "lysed"


def test_compile_measure_call_expr_no_longer_has_stdlib_lowering():
    src = 'protocol T { let obs = Measure(sample = dna_tube, method = "UV", device = "NanoDrop", wavelength = 260nm); }'
    ir = compile_to_ir(parse(src))
    stmt = ir.protocols[0].statements[0]
    assert stmt.__class__.__name__ == "IRLet"
    assert stmt.value.__class__.__name__ == "IRCall"
    assert stmt.value.name == "Measure"


def test_compile_statement_pcr_expands_to_with_env_segments():
    src = 'protocol T { PCR(sample = pcr_well, primers = "Panel", cycles = 3, annealing_temp = 60C); }'
    ir = compile_to_ir(parse(src))
    statements = [stmt for stmt in ir.protocols[0].statements if stmt.__class__.__name__ == "IRWithEnv"]
    assert len(statements) == 9
    assert all(stmt.env_args[0].value.name == "thermal_program" for stmt in statements)


def test_compile_statement_extract_dna_precipitation_expands_to_primitive_skeleton():
    src = """
protocol T {
  ExtractDNAPrecipitation(
    sample = lysate,
    precip_buffer = precip_in,
    wash_inputs = [wash1, wash2],
    dissolve_buffer = dissolve_in,
    output = dna_out,
    cleanup_temp = 25C,
    cleanup_duration = 3min
  );
}
"""
    ir = compile_to_ir(parse(src))
    statements = ir.protocols[0].statements
    assert any(stmt.__class__.__name__ == "IRMutation" for stmt in statements)
    assert any(stmt.__class__.__name__ == "IRWithEnv" for stmt in statements)
    cleanup_stmt = next(stmt for stmt in statements if stmt.__class__.__name__ == "IRWithEnv")
    assert [arg.name for arg in cleanup_stmt.env_args] == ["thermal", "duration"]
    assert any(getattr(stmt, "value", None) is not None and getattr(stmt.value, "name", None) == "sep" for stmt in statements)


def test_compile_statement_extract_dna_column_expands_to_primitive_skeleton():
    src = """
protocol T {
  ExtractDNAColumn(
    sample = lysate,
    bind_buffer = bind_in,
    wash_inputs = [wash1, wash2],
    elution_buffer = elute_in,
    column = spin_col,
    waste = waste_tube,
    output = dna_out,
    cleanup_temp = 25C,
    cleanup_duration = 2min
  );
}
"""
    ir = compile_to_ir(parse(src))
    statements = ir.protocols[0].statements
    assert any(stmt.__class__.__name__ == "IRMutation" for stmt in statements)
    assert any(stmt.__class__.__name__ == "IRWithEnv" for stmt in statements)
    assert any(getattr(stmt, "value", None) is not None and getattr(stmt.value, "name", None) == "sep" for stmt in statements)


def test_compile_python_style_module_protocol_call_resolves_to_target_protocol(tmp_path):
    core = tmp_path / "module_core.culs"
    pipeline = tmp_path / "module_pipeline.culs"
    core.write_text("protocol Base { StepBase(); }", encoding="utf-8")
    pipeline.write_text(
        '\n'.join(
            [
                'include "module_core.culs";',
                "protocol Root { module_core.Base(); StepRoot(); }",
            ]
        ),
        encoding="utf-8",
    )
    ast = parse_files([pipeline])
    ir = compile_to_ir(ast)
    root = next(p for p in ir.protocols if p.name == "Root")
    include_stmt = root.statements[0]
    assert include_stmt.__class__.__name__ == "IRInclude"
    assert include_stmt.name == "Base"
    assert include_stmt.args == []


def test_compile_result_records_runtime_exports_and_include_targets():
    src = (
        'protocol A { let shared_tube = tube(label = "Shared", capacity = 100uL); } '
        'protocol B { include A; img(sample = shared_tube, quantity = fluorescence); }'
    )
    result = compile_ast(parse(src))
    protocol_a = next(p for p in result.ir.protocols if p.name == "A")
    protocol_b = next(p for p in result.ir.protocols if p.name == "B")
    include_stmt = protocol_b.statements[0]

    assert "shared_tube" in result.analysis.protocols[protocol_a.id].runtime_exports
    assert result.analysis.protocols[protocol_b.id].include_targets[include_stmt.id] == protocol_a.id
    assert result.analysis == build_compile_analysis(result.ir)


def test_compile_python_style_module_protocol_call_unresolved_keeps_qualified_name():
    src = "protocol Root { unknown_mod.Missing(); }"
    ir = compile_to_ir(parse(src))
    stmt = ir.protocols[0].statements[0]
    assert stmt.__class__.__name__ == "IRInclude"
    assert stmt.name == "unknown_mod.Missing"
    assert stmt.args == []


def test_compile_protocol_params_and_call_args():
    src = """
protocol Base(input, ratio = 0.5) {
  StepA(v = input);
}
protocol Root {
  this.Base(input = 3, ratio = 0.2);
}
"""
    ast = parse(src)
    ast.protocols[0].module = "this"
    ast.protocols[1].module = "this"
    ir = compile_to_ir(ast)
    base = next(p for p in ir.protocols if p.name == "Base")
    root = next(p for p in ir.protocols if p.name == "Root")
    assert [p.name for p in base.params] == ["input", "ratio"]
    assert base.params[0].default is None
    assert base.params[1].default.__class__.__name__ == "IRQuantity"
    call_stmt = root.statements[0]
    assert call_stmt.__class__.__name__ == "IRInclude"
    assert call_stmt.name == "Base"
    assert [a.name for a in call_stmt.args] == ["input", "ratio"]


def test_compile_agit_step_lowers_to_irstep():
    src = "protocol T { agit(sample = tube, mode = shake, duration = 30s, rate = 800rpm); }"
    ir = compile_to_ir(parse(src))
    stmt = ir.protocols[0].statements[0]
    assert stmt.__class__.__name__ == "IRStep"
    assert stmt.name == "agit"
    assert [arg.name for arg in stmt.args] == ["sample", "mode", "duration", "rate"]
