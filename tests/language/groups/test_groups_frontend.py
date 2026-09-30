"""Source-level group indexing regressions, using the real frontend."""

from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.analysis import build_compile_analysis
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate as _validate


def _compile_source(source):
    return compile_ast(resolve_program(parse(source)).prepared_program).ir


def validate(ir):
    return _validate(ir, analysis=build_compile_analysis(ir))


def _codes(result):
    return [diagnostic.code for diagnostic in result.diagnostics]


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


def test_validate_plate_selector_group_rejects_static_out_of_range_index():
    src = """
protocol T {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  let selected_wells = plate96[A3:A5];
  let missing_well = selected_wells[3];
}
"""
    ir = _compile_source(src)
    result = validate(ir)

    assert "SEM_INDEX_OUT_OF_RANGE" in _codes(result)


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

