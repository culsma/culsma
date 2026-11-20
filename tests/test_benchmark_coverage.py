"""Coverage gaps remain authoritative even beside implementing statements."""
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
assess = runpy.run_path(str(ROOT / "benchmarks/reproduce.py"))["assess"]


def test_gap_before_or_after_transfer_excludes_only_its_step(tmp_path):
    (tmp_path / "source.md").write_text("## Steps\n1. First transfer.\n2. Second transfer.\n3. Third transfer.\n")
    (tmp_path / "protocol.culs").write_text(
        "// Source step S1: First transfer.\n// COVERAGE GAP: delivery mode.\na << [b];\n"
        "// Source step S2: Second transfer.\nc << [d];\n// COVERAGE GAP: delivery mode.\n"
        "// Source step S3: Third transfer.\ne << [f];\n")
    result = assess(tmp_path, None, "1.0.7")
    assert result["matched_steps"] == 1
    assert result["issues"] == [
        {"step": 1, "reason": "coverage_gap"},
        {"step": 2, "reason": "coverage_gap"},
    ]


def test_corrected_transfection_and_remaining_plate_tapping_gap():
    modules = ROOT / "benchmarks/modules"
    corrected = assess(modules / "01-cell-transfection", None, "1.0.7")
    assert corrected["matched_steps"] == corrected["total_steps"] == 13
    assert corrected["issues"] == []
    elisa = assess(modules / "07-sandwich-elisa", None, "1.0.7")
    assert elisa["matched_steps"] == 41
    assert elisa["issues"] == [{"step": 37, "reason": "coverage_gap"}]
